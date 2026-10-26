"""Shared pytest fixtures.

Every test gets its own throw-away SQLite database and data directory, so tests
never touch the development database and are order-independent.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Environment must be configured before app modules read settings.
_BASE_TMP = Path(tempfile.mkdtemp(prefix="smartstock-tests-"))
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SERVE_FRONTEND", "false")
os.environ["DATABASE_URL"] = f"sqlite:///{_BASE_TMP}/bootstrap.db"
os.environ["DATA_DIR"] = str(_BASE_TMP)

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_database, reset_database_cache  # noqa: E402

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "samples"


def _use_temp_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/smartstock-test.db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    reset_database_cache()
    database = get_database()
    return database


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """A fresh, fully migrated database for a single test."""
    database = _use_temp_database(tmp_path, monkeypatch)
    yield database
    reset_database_cache()
    get_settings.cache_clear()


@pytest.fixture()
def client(db) -> TestClient:
    """TestClient bound to the throw-away database (lifespan runs schema setup)."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def demo_db(db):
    """Database pre-loaded with the synthetic demo dataset."""
    from app.services.demo import seed_demo_data

    seed_demo_data(db, seed=777)
    return db


@pytest.fixture()
def client_with_demo(demo_db) -> TestClient:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def sample_csv() -> Path:
    path = SAMPLES_DIR / "sales_sample_template.csv"
    assert path.exists(), f"missing sample dataset at {path}"
    return path


@pytest.fixture()
def broken_csv() -> Path:
    path = SAMPLES_DIR / "sales_validation_test.csv"
    assert path.exists(), f"missing validation test dataset at {path}"
    return path


@pytest.fixture()
def small_sales_db(db):
    """Two products with a short but fully controlled daily history."""
    from datetime import date, timedelta

    from app.repositories import catalog, sales as sales_repo

    product_a = catalog.create_product(
        db, sku="TEST-A", name="Test Product A", category="Testing",
        unit_cost=10.0, selling_price=20.0, stock=100, reorder_threshold=20,
        lead_time_days=5, min_order_qty=10, pack_size=5, safety_stock_days=2,
    )
    product_b = catalog.create_product(
        db, sku="TEST-B", name="Test Product B", category="Testing",
        unit_cost=5.0, selling_price=12.0, stock=40, reorder_threshold=10,
        lead_time_days=3, min_order_qty=1, pack_size=1, safety_stock_days=1,
    )
    start = date.today() - timedelta(days=59)
    rows = []
    for offset in range(60):
        current = start + timedelta(days=offset)
        quantity_a = 10 + (offset % 7)  # clear weekly pattern
        rows.append(
            (
                product_a, current.isoformat(), float(quantity_a), 20.0,
                quantity_a * 20.0, "Main", f"ORD-{offset:03d}", None, 0,
                "2026-01-01T00:00:00+00:00",
            )
        )
        if offset % 2 == 0:  # product B sells every other day (missing observations)
            rows.append(
                (
                    product_b, current.isoformat(), 4.0, 12.0, 48.0,
                    "Main", f"ORD-{offset:03d}", None, 0, "2026-01-01T00:00:00+00:00",
                )
            )
    sales_repo.insert_sales_rows(db, rows)
    return {"db": db, "product_a": product_a, "product_b": product_b, "days": 60}
