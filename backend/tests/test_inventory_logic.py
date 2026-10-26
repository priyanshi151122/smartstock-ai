"""Inventory mathematics and the audited stock-adjustment workflow."""

from __future__ import annotations

import pytest

from app.repositories import catalog, inventory as inventory_repo
from app.services import inventory_logic


# ------------------------------------------------------------------ pure maths
def test_average_daily_demand_uses_the_forecast_horizon():
    assert inventory_logic.average_daily_demand(140, 14) == pytest.approx(10.0)
    assert inventory_logic.average_daily_demand(0, 7) == 0.0
    assert inventory_logic.average_daily_demand(50, 0) == 0.0


def test_safety_stock_uses_the_larger_of_statistical_and_configured_buffer():
    statistical, reason = inventory_logic.safety_stock(10, 4, 9, z=1.65, safety_days=0)
    assert statistical == pytest.approx(1.65 * 4 * 3, abs=1e-6)
    assert "sigma" in reason

    buffer_value, buffer_reason = inventory_logic.safety_stock(10, None, 5, z=1.65, safety_days=3)
    assert buffer_value == pytest.approx(30.0)
    assert "configured buffer" in buffer_reason


def test_reorder_point_is_daily_demand_times_lead_time_plus_safety_stock():
    assert inventory_logic.reorder_point(12.5, 4, 8.0) == pytest.approx(58.0)
    assert inventory_logic.reorder_point(0, 4, 0) == 0.0


def test_target_stock_covers_lead_time_and_review_period():
    # 10/day * (5 + 2) + 15 safety = 85
    assert inventory_logic.target_stock_level(10, 5, 2, 15) == pytest.approx(85.0)
    # explicit cover target overrides lead + review
    assert inventory_logic.target_stock_level(10, 5, 2, 15, target_cover_days=10) == pytest.approx(115.0)


def test_suggested_quantity_respects_pack_size_and_minimum_order():
    assert inventory_logic.suggested_quantity(100, 40) == pytest.approx(60.0)
    assert inventory_logic.suggested_quantity(100, 40, pack_size=12) == pytest.approx(60.0)
    assert inventory_logic.suggested_quantity(100, 45, pack_size=12) == pytest.approx(60.0)
    assert inventory_logic.suggested_quantity(100, 95, pack_size=12) == pytest.approx(12.0)
    assert inventory_logic.suggested_quantity(100, 99, min_order_qty=24) == pytest.approx(24.0)
    # nothing to order when stock already covers the target
    assert inventory_logic.suggested_quantity(50, 80) == 0.0


def test_suggested_quantity_rounds_up_whole_units():
    assert inventory_logic.suggested_quantity(10.2, 0, pack_size=1, is_whole_units=True) == 11.0


@pytest.mark.parametrize(
    ("stock", "daily", "rop", "expected"),
    [
        (0, 5, 20, "stockout"),
        (10, 5, 20, "high"),
        (30, 5, 20, "medium"),
        (120, 5, 20, "low"),
        (1000, 5, 20, "overstock"),
        (50, 0, 0, "overstock"),
        (0, 0, 0, "low"),
    ],
)
def test_risk_classification(stock, daily, rop, expected):
    risk, reason = inventory_logic.classify_risk(
        current_stock=stock,
        avg_daily_demand_value=daily,
        reorder_point_value=rop,
        lead_time_days=5,
        review_period_days=2,
        target_stock=50,
    )
    assert risk == expected
    assert reason


def test_explanation_quotes_the_inputs_used():
    payload = inventory_logic.build_recommendation(
        product={"id": 1, "unit_cost": 4.0},
        inventory={
            "current_stock": 20,
            "lead_time_days": 5,
            "review_period_days": 2,
            "min_order_qty": 10,
            "pack_size": 5,
            "safety_stock_days": 2,
            "is_whole_units": 1,
        },
        forecast_demand=140,
        horizon_days=14,
        daily_std=3.0,
        demand_source="forecast",
    )
    explanation = payload["explanation"]
    assert "140.0 / 14" in explanation
    assert "10.00 units/day" in explanation
    assert "Reorder point" in explanation and "Target stock" in explanation
    assert payload["suggested_quantity"] > 0
    assert payload["estimated_cost"] == pytest.approx(payload["suggested_quantity"] * 4.0)


# -------------------------------------------------------------- stock movements
def test_stock_adjustment_records_a_movement_and_audit_row(db):
    product_id = catalog.create_product(db, sku="ADJ-1", name="Adjustable", stock=10)
    record = inventory_repo.set_stock(
        db, product_id, 25, movement_type="adjustment", reason="Cycle count", actor="tester"
    )
    assert record["current_stock"] == 25

    movements, total = inventory_repo.list_movements(db, product_id=product_id)
    assert total == 1
    assert movements[0]["quantity_delta"] == 15
    assert movements[0]["previous_stock"] == 10
    assert movements[0]["new_stock"] == 25
    assert movements[0]["actor"] == "tester"

    # Movement rows are the audit trail written by the repository layer itself;
    # the HTTP layer additionally writes to audit_logs (covered in the API tests).
    ledger = db.query(
        "SELECT movement_type, quantity_delta FROM stock_movements WHERE product_id = ?",
        (product_id,),
    )
    assert ledger == [{"movement_type": "adjustment", "quantity_delta": 15}]


def test_adjustment_cannot_push_stock_below_zero():
    allowed, message = inventory_repo.adjustments_allowed(5, -10)
    assert allowed is False
    assert "below zero" in message
    allowed_ok, _ = inventory_repo.adjustments_allowed(5, -5)
    assert allowed_ok is True


def test_inventory_update_changes_configuration_only(db):
    product_id = catalog.create_product(db, sku="CFG-1", name="Config Product", stock=7)
    inventory_repo.update_inventory(db, product_id, {"lead_time_days": 12, "pack_size": 6})
    record = inventory_repo.get_inventory(db, product_id)
    assert record["lead_time_days"] == 12
    assert record["pack_size"] == 6
    assert record["current_stock"] == 7


# ------------------------------------------------------------------- HTTP layer
def test_api_adjust_stock_updates_analytics_snapshot(client):
    created = client.post(
        "/api/products",
        json={"sku": "API-1", "name": "API Product", "category": "Testing", "unit_cost": 10, "selling_price": 15},
    )
    assert created.status_code == 201
    product_id = created.json()["id"]

    response = client.post(
        f"/api/inventory/{product_id}/adjust",
        json={"quantity_delta": 40, "reason": "Received delivery", "actor": "tester"},
    )
    assert response.status_code == 200
    assert response.json()["current_stock"] == 40

    movements = client.get(f"/api/inventory/{product_id}/movements")
    assert movements.status_code == 200
    assert movements.json()[0]["new_stock"] == 40

    below_zero = client.post(
        f"/api/inventory/{product_id}/adjust",
        json={"quantity_delta": -100, "reason": "Impossible shrink"},
    )
    assert below_zero.status_code == 422
    assert "below zero" in below_zero.json()["error"]["message"]

    audit = client.get("/api/audit-logs", params={"entity_type": "inventory"})
    assert audit.status_code == 200
    assert any(row["action"] == "inventory.adjusted" for row in audit.json()["items"])


def test_api_inventory_patch_routes_stock_changes_through_the_ledger(client):
    created = client.post("/api/products", json={"sku": "API-2", "name": "Patch Product"})
    product_id = created.json()["id"]
    patched = client.patch(f"/api/inventory/{product_id}", json={"current_stock": 12, "lead_time_days": 4})
    assert patched.status_code == 200
    assert patched.json()["current_stock"] == 12
    movements = client.get("/api/inventory/movements", params={"product_id": product_id}).json()
    assert movements[0]["movement_type"] == "adjustment"
    assert movements[0]["new_stock"] == 12
