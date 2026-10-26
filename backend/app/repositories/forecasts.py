"""Forecast runs/results/metrics and reorder recommendation persistence."""

from __future__ import annotations

from typing import Any

from app.db import Database
from app.utils import json_dumps, json_loads, sanitize_text, utcnow_iso


# --------------------------------------------------------------------- run rows
def create_run(
    db: Database,
    *,
    horizon_days: int,
    model_requested: str,
    data_source: str,
    params: dict[str, Any],
) -> int:
    return int(
        db.execute(
            """
            INSERT INTO forecast_runs (horizon_days, model_requested, status, data_source, params, created_at)
            VALUES (?, ?, 'running', ?, ?, ?)
            """,
            (int(horizon_days), model_requested, data_source, json_dumps(params), utcnow_iso()),
        )
    )


def finalise_run(db: Database, run_id: int, fields: dict[str, Any]) -> None:
    allowed = {
        "model_used",
        "baseline_used",
        "status",
        "products_forecasted",
        "products_insufficient",
        "train_start",
        "train_end",
        "validation_start",
        "validation_end",
        "summary_metrics",
        "warnings",
        "notes",
        "duration_ms",
    }
    updates = {}
    for key, value in fields.items():
        if key not in allowed or value is None:
            continue
        updates[key] = json_dumps(value) if isinstance(value, (dict, list)) else value
    if not updates:
        return
    assignments = ", ".join(f"{column} = ?" for column in updates)
    db.execute(f"UPDATE forecast_runs SET {assignments} WHERE id = ?", list(updates.values()) + [run_id])


def get_run(db: Database, run_id: int) -> dict[str, Any] | None:
    row = db.query_one("SELECT * FROM forecast_runs WHERE id = ?", (run_id,))
    if not row:
        return None
    row["summary_metrics"] = json_loads(row.get("summary_metrics"), {})
    row["warnings"] = json_loads(row.get("warnings"), [])
    row["params"] = json_loads(row.get("params"), {})
    return row


def latest_run(db: Database, *, data_source: str | None = None) -> dict[str, Any] | None:
    if data_source:
        row = db.query_one(
            "SELECT * FROM forecast_runs WHERE status = 'completed' AND data_source = ? ORDER BY id DESC LIMIT 1",
            (data_source,),
        )
    else:
        row = db.query_one(
            "SELECT * FROM forecast_runs WHERE status = 'completed' ORDER BY id DESC LIMIT 1"
        )
    if not row:
        return None
    row["summary_metrics"] = json_loads(row.get("summary_metrics"), {})
    row["warnings"] = json_loads(row.get("warnings"), [])
    row["params"] = json_loads(row.get("params"), {})
    return row


def list_runs(db: Database, limit: int = 25) -> list[dict[str, Any]]:
    rows = db.query("SELECT * FROM forecast_runs ORDER BY id DESC LIMIT ?", (int(limit),))
    for row in rows:
        row["summary_metrics"] = json_loads(row.get("summary_metrics"), {})
        row["warnings"] = json_loads(row.get("warnings"), [])
        row["params"] = json_loads(row.get("params"), {})
    return rows


def insert_forecast_results(db: Database, rows: list[tuple[Any, ...]]) -> int:
    if not rows:
        return 0
    return db.execute_many(
        """
        INSERT INTO forecast_results (run_id, product_id, forecast_date, predicted_units,
                                      lower_bound, upper_bound, model_name, is_baseline)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def insert_forecast_metrics(db: Database, rows: list[tuple[Any, ...]]) -> int:
    if not rows:
        return 0
    return db.execute_many(
        """
        INSERT INTO forecast_metrics (run_id, product_id, model_name, is_baseline, is_selected,
                                      mae, rmse, wape, validation_days, train_observations,
                                      observed_days, missing_days, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def get_metrics(db: Database, run_id: int, *, product_id: int | None = None) -> list[dict[str, Any]]:
    where = "WHERE m.run_id = ?"
    params: list[Any] = [run_id]
    if product_id:
        where += " AND m.product_id = ?"
        params.append(int(product_id))
    return db.query(
        f"""
        SELECT m.*, p.sku, p.name AS product_name, p.category
        FROM forecast_metrics m
        JOIN products p ON p.id = m.product_id
        {where}
        ORDER BY p.name, m.is_baseline DESC
        """,
        params,
    )


def get_results(
    db: Database,
    run_id: int,
    *,
    product_id: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    where = "WHERE r.run_id = ?"
    params: list[Any] = [run_id]
    if product_id:
        where += " AND r.product_id = ?"
        params.append(int(product_id))
    limit_sql = f"LIMIT {int(limit)}" if limit else ""
    return db.query(
        f"""
        SELECT r.*, p.sku, p.name AS product_name
        FROM forecast_results r
        JOIN products p ON p.id = r.product_id
        {where}
        ORDER BY r.forecast_date, p.name
        {limit_sql}
        """,
        params,
    )


def forecast_totals(db: Database, run_id: int) -> dict[int, dict[str, Any]]:
    rows = db.query(
        """
        SELECT product_id,
               SUM(predicted_units) AS total_demand,
               COUNT(*) AS horizon_days,
               MIN(forecast_date) AS start_date,
               MAX(forecast_date) AS end_date,
               MAX(model_name) AS model_name,
               MAX(is_baseline) AS is_baseline
        FROM forecast_results
        WHERE run_id = ?
        GROUP BY product_id
        """,
        (run_id,),
    )
    return {
        int(row["product_id"]): {
            "total_demand": float(row["total_demand"] or 0),
            "horizon_days": int(row["horizon_days"] or 0),
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "model_name": row["model_name"],
            "is_baseline": bool(row["is_baseline"]),
        }
        for row in rows
    }


def metrics_summary(db: Database, run_id: int) -> dict[str, Any]:
    rows = db.query(
        """
        SELECT model_name, is_baseline,
               COUNT(*) AS products,
               AVG(mae) AS avg_mae, AVG(rmse) AS avg_rmse, AVG(wape) AS avg_wape,
               SUM(CASE WHEN wape IS NOT NULL THEN 1 ELSE 0 END) AS wape_products
        FROM forecast_metrics
        WHERE run_id = ?
        GROUP BY model_name, is_baseline
        """,
        (run_id,),
    )
    return {"by_model": rows}


# ------------------------------------------------------------- recommendations
RECO_SELECT = """
SELECT r.*, p.sku, p.name AS product_name, p.category, s.name AS supplier_name
FROM reorder_recommendations r
JOIN products p ON p.id = r.product_id
LEFT JOIN suppliers s ON s.id = p.supplier_id
"""


def insert_recommendations(db: Database, rows: list[tuple[Any, ...]]) -> int:
    if not rows:
        return 0
    return db.execute_many(
        """
        INSERT INTO reorder_recommendations (
            product_id, run_id, status, risk_level, current_stock, forecast_horizon_days,
            forecast_demand, avg_daily_demand, demand_std, safety_stock, reorder_point,
            target_stock, suggested_quantity, estimated_cost, lead_time_days, min_order_qty,
            pack_size, coverage_days, explanation, demand_source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def replace_open_recommendations(db: Database, run_id: int | None) -> int:
    """Drop previous *pending* rows so the table always reflects the latest run.

    Approved/dismissed decisions are historical and are preserved for audit.
    """
    return db.execute(
        "DELETE FROM reorder_recommendations WHERE status = 'pending'"
    )


def list_recommendations(
    db: Database,
    *,
    status: str | None = None,
    risk_level: str | None = None,
    category: str | None = None,
    search: str | None = None,
    sort_by: str = "risk_priority",
    sort_dir: str = "asc",
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    clauses, params = ["1 = 1"], []
    if status:
        clauses.append("r.status = ?")
        params.append(status)
    if risk_level:
        clauses.append("r.risk_level = ?")
        params.append(risk_level)
    if category:
        clauses.append("p.category = ?")
        params.append(category)
    if search:
        needle = f"%{search.strip().lower()}%"
        clauses.append("(LOWER(p.name) LIKE ? OR LOWER(p.sku) LIKE ?)")
        params += [needle, needle]
    where = " WHERE " + " AND ".join(clauses)
    total = int(
        db.scalar(
            f"SELECT COUNT(*) AS c FROM reorder_recommendations r JOIN products p ON p.id = r.product_id{where}",
            params,
            0,
        )
        or 0
    )
    columns = {
        "risk_priority": (
            "CASE r.risk_level WHEN 'stockout' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 "
            "WHEN 'low' THEN 3 WHEN 'overstock' THEN 4 ELSE 5 END"
        ),
        "product_name": "p.name",
        "sku": "p.sku",
        "current_stock": "r.current_stock",
        "forecast_demand": "r.forecast_demand",
        "safety_stock": "r.safety_stock",
        "reorder_point": "r.reorder_point",
        "suggested_quantity": "r.suggested_quantity",
        "estimated_cost": "r.estimated_cost",
        "lead_time_days": "r.lead_time_days",
        "coverage_days": "r.coverage_days",
        "created_at": "r.created_at",
    }
    order_column = columns.get(sort_by, columns["risk_priority"])
    direction = "DESC" if str(sort_dir).lower() == "desc" else "ASC"
    offset = max(0, (page - 1) * page_size)
    rows = db.query(
        f"{RECO_SELECT}{where} ORDER BY {order_column} {direction}, r.id DESC LIMIT ? OFFSET ?",
        params + [page_size, offset],
    )
    return rows, total


def get_recommendation(db: Database, reco_id: int) -> dict[str, Any] | None:
    return db.query_one(f"{RECO_SELECT} WHERE r.id = ?", (reco_id,))


def decide_recommendation(
    db: Database,
    reco_id: int,
    *,
    status: str,
    actor: str,
    note: str | None = None,
    order_draft_ref: str | None = None,
) -> bool:
    db.execute(
        """
        UPDATE reorder_recommendations
        SET status = ?, decided_at = ?, decided_by = ?, decision_note = ?, order_draft_ref = ?
        WHERE id = ?
        """,
        (
            status,
            utcnow_iso(),
            sanitize_text(actor, 80) or "store-manager",
            sanitize_text(note, 400),
            sanitize_text(order_draft_ref, 80),
            reco_id,
        ),
    )
    return True
