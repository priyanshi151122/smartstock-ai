"""FastAPI application entry point for SmartStock AI."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.db import get_database
from app.routers import analytics, forecasts, imports, inventory, products, recommendations, reports, settings as settings_router
from app.schemas import HealthResponse
from app.utils import utcnow_iso

logger = logging.getLogger("smartstock")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

config = get_settings()

DESCRIPTION = """
**SmartStock AI** turns a shop's own sales history into demand forecasts, inventory
risk assessments and explainable reorder recommendations.

* **Import** — upload CSV/XLSX exports, map columns, review validation issues per row,
  apply cleaning rules and persist only valid records.
* **Analyse** — revenue, units, category mix, product performance, ABC classes and
  period-over-period growth computed directly from the stored rows.
* **Forecast** — a seasonal-naive baseline is compared against gradient-boosted /
  random-forest / ridge models on chronological rolling-origin splits; MAE, RMSE and
  WAPE are stored with every run, and the baseline wins unless a model truly beats it.
* **Act** — reorder points, safety stock and order quantities with a written
  explanation of every input value. Approving a recommendation creates a *draft*
  purchase order record; no supplier order is ever sent automatically.

All demo data is synthetic, seeded and labelled `is_demo = 1`. Filter every endpoint
with `data_source=actual` to exclude it.
"""

@asynccontextmanager
async def lifespan(_: FastAPI):
    database = get_database()
    counts = database.query_one(
        "SELECT (SELECT COUNT(*) FROM products) AS products, (SELECT COUNT(*) FROM sales_records) AS sales"
    ) or {}
    logger.info(
        "SmartStock AI %s ready · dialect=%s · products=%s · sales_rows=%s",
        config.app_version,
        database.dialect,
        counts.get("products", 0),
        counts.get("sales", 0),
    )
    yield


app = FastAPI(
    lifespan=lifespan,
    title="SmartStock AI — Sales & Demand Forecasting API",
    description=DESCRIPTION,
    version=config.app_version,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    contact={"name": "SmartStock AI", "url": "https://example.local/smartstock"},
    license_info={"name": "MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config.cors_origins),
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|.*\.e2b\.app)(:\d+)?",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


# --------------------------------------------------------------- error handling
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "message" in detail:
        message, extra = detail["message"], detail
    else:
        message, extra = detail, None
    payload: dict[str, Any] = {
        "error": {
            "status": exc.status_code,
            "message": message,
            "path": request.url.path,
            "timestamp": utcnow_iso(),
        }
    }
    if extra:
        payload["error"]["detail"] = extra
    return JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    issues = [
        {
            "field": ".".join(str(part) for part in error.get("loc", []) if part != "body"),
            "message": error.get("msg", "Invalid value"),
            "type": error.get("type", "validation_error"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "status": 422,
                "message": "The request could not be validated. Check the highlighted fields.",
                "issues": issues,
                "path": request.url.path,
                "timestamp": utcnow_iso(),
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never leak internal paths or stack traces to the client; log them server-side.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "status": 500,
                "message": "Something went wrong while processing this request. "
                "The error has been logged; please retry or check the server logs.",
                "path": request.url.path,
                "timestamp": utcnow_iso(),
            }
        },
    )


# ---------------------------------------------------------------------- routers
app.include_router(analytics.router)
app.include_router(imports.router)
app.include_router(products.router)
app.include_router(inventory.router)
app.include_router(forecasts.router)
app.include_router(recommendations.router)
app.include_router(reports.router)
app.include_router(settings_router.router)


@app.get("/api/health", response_model=HealthResponse, tags=["System"], summary="Service health and row counts")
def health() -> dict[str, Any]:
    database = get_database()
    return {
        "status": "ok",
        "version": config.app_version,
        "database": database.dialect,
        "environment": config.environment,
        "products": int(database.scalar("SELECT COUNT(*) AS c FROM products", None, 0) or 0),
        "sales_records": int(database.scalar("SELECT COUNT(*) AS c FROM sales_records", None, 0) or 0),
    }


@app.get("/api", tags=["System"], summary="API index")
def api_index() -> dict[str, Any]:
    return {
        "name": config.app_name,
        "version": config.app_version,
        "docs": "/api/docs",
        "openapi": "/api/openapi.json",
        "endpoints": {
            "dashboard": "/api/analytics/dashboard",
            "imports": "/api/imports/upload",
            "forecasts": "/api/forecasts/run",
            "inventory": "/api/inventory",
            "recommendations": "/api/recommendations",
            "reports": "/api/reports",
            "settings": "/api/settings",
        },
    }


# -------------------------------------------------------------------- frontend
frontend_dist = config.frontend_dist
if config.serve_frontend and frontend_dist.exists():
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str) -> Any:
        """Serve the built SPA, falling back to index.html for client-side routes."""
        if full_path.startswith("api/"):
            return JSONResponse(
                status_code=404,
                content={"error": {"status": 404, "message": f"Unknown API route '/{full_path}'."}},
            )
        candidate = (frontend_dist / full_path).resolve()
        if full_path and candidate.is_file() and frontend_dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        index = frontend_dist / "index.html"
        if index.exists():
            return FileResponse(index)
        return HTMLResponse(
            "<h1>Frontend build not found</h1><p>Run <code>npm run build</code> in the frontend directory.</p>",
            status_code=200,
        )
else:

    @app.get("/", include_in_schema=False)
    def root() -> HTMLResponse:
        return HTMLResponse(
            "<h1>SmartStock AI API</h1>"
            f"<p>Version {config.app_version}. The API is running.</p>"
            "<p>Open <a href='/api/docs'>/api/docs</a> for the interactive API documentation, "
            "or start the Vite dev server in <code>frontend/</code> for the UI.</p>",
            status_code=200,
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    database = get_database()
    counts = database.query_one(
        "SELECT (SELECT COUNT(*) FROM products) AS products, (SELECT COUNT(*) FROM sales_records) AS sales"
    ) or {}
    logger.info(
        "SmartStock AI %s ready · dialect=%s · products=%s · sales_rows=%s",
        config.app_version,
        database.dialect,
        counts.get("products", 0),
        counts.get("sales", 0),
    )
    yield
