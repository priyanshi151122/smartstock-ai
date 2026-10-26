"""Report generation for CSV, XLSX and PDF exports.

Every report is built from the same filtered queries that power the dashboards, so
an export always reflects what the user is looking at.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from app.config import get_settings
from app.db import Database
from app.repositories import catalog, forecasts as forecast_repo, sales as sales_repo
from app.services import analytics, inventory_logic
from app.utils import sanitize_spreadsheet_cell, utcnow_iso

REPORT_LABELS = {
    "sales_summary": "Sales Summary",
    "product_performance": "Product Performance",
    "demand_forecast": "Demand Forecast",
    "inventory_risk": "Inventory Risk",
    "reorder_recommendations": "Reorder Recommendations",
}


class ReportError(Exception):
    pass


def _reports_dir() -> Path:
    settings = get_settings()
    settings.ensure_directories()
    return settings.report_dir


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60]


# ------------------------------------------------------------------- dataframes
def _sales_summary_frames(db: Database, filters: dict[str, Any]) -> dict[str, pd.DataFrame]:
    start, end = analytics.resolve_period(filters.get("start_date"), filters.get("end_date"), filters.get("data_source"), db)
    base = {
        "start_date": start,
        "end_date": end,
        "category": filters.get("category"),
        "product_id": filters.get("product_id"),
        "data_source": filters.get("data_source"),
    }
    kpis = analytics.compute_kpis(
        db,
        start_date=start,
        end_date=end,
        category=filters.get("category"),
        product_id=filters.get("product_id"),
        data_source=filters.get("data_source"),
    )
    summary = pd.DataFrame(
        [
            {
                "Metric": card["label"],
                "Value": card["formatted"],
                "Available": "yes" if card["available"] else "no",
                "Note": card.get("note") or "",
            }
            for card in kpis["cards"]
        ]
    )
    daily = pd.DataFrame(sales_repo.time_series(db, granularity="day", **base))
    if not daily.empty:
        daily = daily.rename(
            columns={"period": "Date", "revenue": "Revenue", "units": "Units", "orders": "Orders"}
        )
    by_category = pd.DataFrame(sales_repo.by_category(db, **base)).rename(
        columns={"category": "Category", "revenue": "Revenue", "units": "Units"}
    )
    by_product = pd.DataFrame(sales_repo.by_product(db, **base)).rename(
        columns={
            "sku": "SKU",
            "name": "Product",
            "category": "Category",
            "revenue": "Revenue",
            "units": "Units",
            "orders": "Orders",
            "avg_price": "Avg price",
        }
    )
    keep = [c for c in ["SKU", "Product", "Category", "Units", "Revenue", "Orders", "Avg price"] if c in by_product.columns]
    return {
        "Summary": summary,
        "Daily sales": daily,
        "Revenue by category": by_category,
        "Product totals": by_product[keep] if keep else by_product,
    }


def _performance_frames(db: Database, filters: dict[str, Any]) -> dict[str, pd.DataFrame]:
    payload = analytics.product_performance(
        db,
        start_date=filters.get("start_date"),
        end_date=filters.get("end_date"),
        category=filters.get("category"),
        product_id=filters.get("product_id"),
        data_source=filters.get("data_source"),
    )
    items = pd.DataFrame(payload["items"])
    if not items.empty:
        items = items.rename(
            columns={
                "sku": "SKU",
                "name": "Product",
                "category": "Category",
                "units": "Units",
                "revenue": "Revenue",
                "abc_class": "ABC class",
                "growth_pct": "Growth %",
                "gross_margin": "Gross margin",
                "gross_margin_pct": "Gross margin %",
                "cost_data_available": "Cost data available",
                "demand_variability": "Demand CV",
                "days_of_cover": "Days of cover",
                "slow_moving": "Slow moving",
            }
        )
    abc = pd.DataFrame(payload["abc_summary"]).rename(
        columns={"abc_class": "ABC class", "products": "Products", "revenue": "Revenue", "units": "Units"}
    )
    return {
        "Product performance": items,
        "ABC summary": abc,
        "Category summary": pd.DataFrame(payload["category_summary"]),
    }


def _forecast_frames(db: Database, filters: dict[str, Any]) -> dict[str, pd.DataFrame]:
    run_id = filters.get("run_id")
    run = forecast_repo.get_run(db, int(run_id)) if run_id else forecast_repo.latest_run(db)
    if not run:
        raise ReportError("No completed forecast run is available to export. Generate a forecast first.")
    results = forecast_repo.get_results(db, int(run["id"]))
    metrics = forecast_repo.get_metrics(db, int(run["id"]))
    frame = pd.DataFrame(results)
    if not frame.empty:
        frame = frame.rename(
            columns={
                "sku": "SKU",
                "product_name": "Product",
                "forecast_date": "Forecast date",
                "predicted_units": "Forecast units",
                "lower_bound": "Lower bound",
                "upper_bound": "Upper bound",
                "model_name": "Model",
                "is_baseline": "Baseline",
            }
        )
    metric_frame = pd.DataFrame(metrics)
    if not metric_frame.empty:
        metric_frame = metric_frame.rename(
            columns={
                "sku": "SKU",
                "product_name": "Product",
                "model_name": "Model",
                "is_baseline": "Baseline",
                "is_selected": "Selected",
                "mae": "MAE",
                "rmse": "RMSE",
                "wape": "WAPE",
                "validation_days": "Validation days",
                "train_observations": "Train observations",
                "note": "Note",
            }
        )
    meta = pd.DataFrame(
        [
            {"Field": "Forecast run", "Value": run["id"]},
            {"Field": "Horizon (days)", "Value": run["horizon_days"]},
            {"Field": "Model(s) used", "Value": run["model_used"]},
            {"Field": "Baseline", "Value": run["baseline_used"]},
            {"Field": "Training period", "Value": f"{run.get('train_start')} to {run.get('train_end')}"},
            {"Field": "Validation period", "Value": f"{run.get('validation_start')} to {run.get('validation_end')}"},
            {"Field": "Products forecasted", "Value": run["products_forecasted"]},
            {"Field": "Products with insufficient history", "Value": run["products_insufficient"]},
            {"Field": "Data source", "Value": run["data_source"]},
            {"Field": "Generated at", "Value": utcnow_iso()},
        ]
    )
    summary = run.get("summary_metrics") or {}
    summary_rows = pd.DataFrame(
        [
            {"Field": "Selected model WAPE", "Value": (summary.get("selected") or {}).get("wape")},
            {"Field": "Selected model MAE", "Value": (summary.get("selected") or {}).get("mean_mae")},
            {"Field": "Selected model RMSE", "Value": (summary.get("selected") or {}).get("mean_rmse")},
            {"Field": "WAPE improvement vs baseline (%)", "Value": summary.get("wape_improvement_vs_baseline_pct")},
        ]
    )
    return {
        "Run metadata": meta,
        "Evaluation summary": summary_rows,
        "Forecast values": frame,
        "Model metrics": metric_frame,
    }


def _inventory_frames(db: Database, filters: dict[str, Any]) -> dict[str, pd.DataFrame]:
    overview = inventory_logic.inventory_overview(
        db,
        category=filters.get("category"),
        page=1,
        page_size=10_000,
        sort_by="name",
        sort_dir="asc",
        data_source=filters.get("data_source"),
    )
    frame = pd.DataFrame(overview["items"])
    if not frame.empty:
        frame = frame.rename(
            columns={
                "sku": "SKU",
                "name": "Product",
                "category": "Category",
                "supplier_name": "Supplier",
                "current_stock": "Current stock",
                "reorder_threshold": "Reorder threshold",
                "lead_time_days": "Lead time (days)",
                "safety_stock_days": "Safety stock (days)",
                "stock_value": "Stock value",
                "recent_daily_demand": "Avg daily demand",
                "days_of_cover": "Days of cover",
                "risk_level": "Risk level",
                "risk_reason": "Risk reason",
            }
        )
    summary = pd.DataFrame(
        [
            {"Metric": key, "Value": value}
            for key, value in {
                **(overview["summary"].get("counts") or {}),
                "products": overview["summary"].get("products"),
                "inventory_value": overview["summary"].get("inventory_value"),
                "avg_cover_days": overview["summary"].get("avg_cover_days"),
                "demand_source": overview["summary"].get("demand_source"),
            }.items()
        ]
    )
    return {"Inventory risk": frame, "Risk summary": summary}


def _reorder_frames(db: Database, filters: dict[str, Any]) -> dict[str, pd.DataFrame]:
    rows, total = forecast_repo.list_recommendations(
        db,
        status=None,
        category=filters.get("category"),
        page=1,
        page_size=5000,
    )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.rename(
            columns={
                "sku": "SKU",
                "product_name": "Product",
                "category": "Category",
                "supplier_name": "Supplier",
                "status": "Status",
                "risk_level": "Risk level",
                "current_stock": "Current stock",
                "forecast_horizon_days": "Horizon (days)",
                "forecast_demand": "Forecast demand",
                "avg_daily_demand": "Avg daily demand",
                "safety_stock": "Safety stock",
                "reorder_point": "Reorder point",
                "target_stock": "Target stock",
                "suggested_quantity": "Suggested quantity",
                "estimated_cost": "Estimated cost",
                "lead_time_days": "Lead time (days)",
                "min_order_qty": "Min order qty",
                "pack_size": "Pack size",
                "coverage_days": "Days of cover",
                "explanation": "Explanation",
                "demand_source": "Demand source",
            }
        )
        frame = frame.drop(columns=[c for c in ("id", "product_id", "run_id") if c in frame.columns])
    return {"Reorder recommendations": frame}


FRAME_BUILDERS: dict[str, Callable[[Database, dict[str, Any]], dict[str, pd.DataFrame]]] = {
    "sales_summary": _sales_summary_frames,
    "product_performance": _performance_frames,
    "demand_forecast": _forecast_frames,
    "inventory_risk": _inventory_frames,
    "reorder_recommendations": _reorder_frames,
}


# ----------------------------------------------------------------------- export
def _sanitize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame.applymap(sanitize_spreadsheet_cell)


def generate_report(
    db: Database,
    *,
    report_type: str,
    file_format: str,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if report_type not in FRAME_BUILDERS:
        raise ReportError(f"Unknown report type '{report_type}'.")
    if file_format not in {"csv", "xlsx", "pdf"}:
        raise ReportError(f"Unsupported export format '{file_format}'.")
    filters = filters or {}
    frames = FRAME_BUILDERS[report_type](db, filters)
    label = REPORT_LABELS[report_type]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{_slug(label)}-{stamp}-{uuid.uuid4().hex[:6]}.{file_format}"
    destination = _reports_dir() / filename
    settings = catalog.get_settings_map(db)

    period = {
        "start_date": filters.get("start_date"),
        "end_date": filters.get("end_date"),
        "generated_at": utcnow_iso(),
        "category": filters.get("category"),
        "data_source": filters.get("data_source"),
    }

    if file_format == "csv":
        primary = next(iter(frames.values()))
        _sanitize_frame(primary).to_csv(destination, index=False)
    elif file_format == "xlsx":
        with pd.ExcelWriter(destination, engine="openpyxl") as writer:
            _sanitize_frame(
                pd.DataFrame(
                    [
                        {"Field": "Report", "Value": label},
                        {"Field": "Generated at", "Value": period["generated_at"]},
                        {"Field": "Reporting period", "Value": f"{period['start_date']} to {period['end_date']}"},
                        {"Field": "Category filter", "Value": period["category"] or "all"},
                        {"Field": "Data source", "Value": period["data_source"] or "all"},
                    ]
                )
            ).to_excel(writer, sheet_name="Report info", index=False)
            for sheet, frame in frames.items():
                if frame.empty:
                    pd.DataFrame([{"Note": "No rows matched the selected filters."}]).to_excel(
                        writer, sheet_name=sheet[:31], index=False
                    )
                else:
                    _sanitize_frame(frame).to_excel(writer, sheet_name=sheet[:31], index=False)
    else:
        _write_pdf(
            destination,
            report_type=report_type,
            label=label,
            frames=frames,
            filters=filters,
            settings=settings,
            period=period,
        )

    size = destination.stat().st_size
    return {
        "filename": filename,
        "report_type": report_type,
        "file_format": file_format,
        "size_bytes": size,
        "created_at": period["generated_at"],
        "download_url": f"/api/reports/download/{filename}",
    }


# --------------------------------------------------------------------------- PDF
def _write_pdf(
    destination: Path,
    *,
    report_type: str,
    label: str,
    frames: dict[str, pd.DataFrame],
    filters: dict[str, Any],
    settings: dict[str, str],
    period: dict[str, Any],
) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.lineplots import LinePlot
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    store = settings.get("store_name", "SmartStock AI")
    symbol = settings.get("currency_symbol", "\u20b9")
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleX", parent=styles["Title"], fontSize=18, spaceAfter=6, textColor=colors.HexColor("#0f172a")
    )
    h2 = ParagraphStyle("H2X", parent=styles["Heading2"], fontSize=11.5, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("BodyX", parent=styles["BodyText"], fontSize=8.6, leading=11)

    flow: list[Any] = []
    flow.append(Paragraph(f"{store} — {label}", title_style))
    flow.append(
        Paragraph(
            f"Reporting period: {period.get('start_date') or 'start of history'} to "
            f"{period.get('end_date') or 'latest record'}<br/>"
            f"Generated at: {period.get('generated_at')}<br/>"
            f"Data source: {period.get('data_source') or 'all persisted sales records'}"
            + (f"<br/>Category filter: {period.get('category')}" if period.get("category") else ""),
            body,
        )
    )
    flow.append(Spacer(1, 6))

    def render_frame(frame: pd.DataFrame, max_rows: int = 18) -> None:
        if frame is None or frame.empty:
            flow.append(Paragraph("No rows matched the selected filters.", body))
            return
        subset = frame.head(max_rows)
        subset = subset.where(pd.notna(subset), "")
        data = [[str(col)[:22] for col in subset.columns]]
        for row in subset.itertuples(index=False):
            data.append([str(value)[:30] for value in row])
        table = Table(data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 6.6),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        flow.append(table)
        if len(frame) > max_rows:
            flow.append(Paragraph(f"Showing first {max_rows} of {len(frame)} rows — see XLSX/CSV for the full data.", body))

    # ----- chart 1: sales over time (or forecast values) --------------------
    chart_frame = None
    for key in ("Daily sales", "Forecast values", "Inventory risk", "Product performance", "Reorder recommendations"):
        if key in frames and not frames[key].empty:
            chart_frame = frames[key]
            chart_key = key
            break
    if chart_frame is not None:
        flow.append(Paragraph("Trend", h2))
        drawing = Drawing(470, 150)
        try:
            if chart_key == "Daily sales" and {"Date", "Revenue"} <= set(chart_frame.columns):
                values = [float(v) for v in chart_frame["Revenue"].tolist()]
                chart = LinePlot()
                chart.height = 110
                chart.width = 450
                chart.x = 25
                chart.y = 20
                chart.data = [list(zip(range(len(values)), values))]
                chart.lines[0].strokeColor = colors.HexColor("#2563eb")
                chart.lines[0].strokeWidth = 1.2
                drawing.add(chart)
            else:
                numeric = chart_frame.select_dtypes("number")
                if numeric.empty:
                    raise ValueError("no numeric column")
                column = numeric.columns[0]
                series = numeric[column].head(14).fillna(0).tolist()
                chart = VerticalBarChart()
                chart.height = 110
                chart.width = 450
                chart.x = 25
                chart.y = 20
                chart.data = [[float(v) for v in series]]
                chart.bars[0].fillColor = colors.HexColor("#2563eb")
                drawing.add(chart)
            flow.append(drawing)
        except Exception:
            flow.append(Paragraph("Chart could not be rendered for this dataset.", body))

    # ----- KPI / summary tables -------------------------------------------
    for name, frame in frames.items():
        flow.append(Paragraph(name, h2))
        render_frame(frame, max_rows=18 if name != "Summary" else 12)

    flow.append(Spacer(1, 8))
    flow.append(
        Paragraph(
            f"All values are computed from persisted records on {period.get('generated_at')}. "
            "Forecasts are statistical estimates and carry the validation metrics shown above; "
            "they are not guarantees of future demand.",
            body,
        )
    )

    doc = SimpleDocTemplate(
        str(destination),
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"{store} — {label}",
        author="SmartStock AI",
    )
    doc.build(flow)


def list_reports(limit: int = 50) -> list[dict[str, Any]]:
    directory = _reports_dir()
    files = sorted(directory.glob("*"), key=lambda path: path.stat().st_mtime, reverse=True)[:limit]
    items = []
    for path in files:
        if not path.is_file():
            continue
        stat = path.stat()
        items.append(
            {
                "filename": path.name,
                "report_type": _guess_type(path.name),
                "file_format": path.suffix.lstrip("."),
                "size_bytes": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
                "download_url": f"/api/reports/download/{path.name}",
            }
        )
    return items


def _guess_type(filename: str) -> str:
    for key, label in REPORT_LABELS.items():
        if _slug(label) in filename:
            return key
    return "unknown"


def safe_report_path(filename: str) -> Path:
    """Resolve a download path inside the reports directory only."""
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        raise ReportError("Invalid report filename.")
    candidate = (_reports_dir() / filename).resolve()
    if _reports_dir().resolve() not in candidate.parents or not candidate.exists():
        raise ReportError("Report file was not found.")
    return candidate
