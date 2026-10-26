"""Tests for the forecasting pipeline: metrics, leakage guards and persistence."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.repositories import forecasts as forecast_repo
from app.services import forecasting
from app.services.forecasting import InsufficientHistory


def _series(days: int = 90, pattern=None) -> pd.Series:
    index = pd.date_range(end=date(2026, 5, 1), periods=days, freq="D")
    values = pattern if pattern is not None else [30 + 6 * (i % 7) for i in range(days)]
    return pd.Series(np.asarray(values, dtype=float), index=index)


# --------------------------------------------------------------------- metrics
def test_mae_rmse_wape_are_computed_correctly():
    metrics = forecasting.compute_metrics([10, 20, 30], [12, 18, 33])
    assert metrics["n"] == 3
    assert metrics["mae"] == pytest.approx(7 / 3, abs=1e-4)         # (2+2+3)/3
    assert metrics["rmse"] == pytest.approx(np.sqrt(17 / 3), abs=1e-4)  # sqrt((4+4+9)/3)
    assert metrics["wape"] == pytest.approx(7 / 60, abs=1e-4)        # 7 / 60 total demand


def test_wape_is_none_when_observed_demand_is_zero():
    metrics = forecasting.compute_metrics([0, 0, 0], [1, 2, 3])
    assert metrics["wape"] is None
    assert "undefined" in (metrics["note"] or "")
    assert metrics["mae"] == pytest.approx(2.0)


def test_metrics_report_no_overlap_when_shapes_differ():
    metrics = forecasting.compute_metrics([1, 2], [1, 2, 3])
    assert metrics["n"] == 0
    assert metrics["mae"] is None


# ------------------------------------------------------------ chronological CV
def test_backtest_folds_are_chronological_and_disjoint():
    series = _series(120)
    folds = forecasting._folds(len(series), horizon=14, max_folds=3)
    assert len(folds) == 3
    previous_start = None
    for train_end, valid_end in folds:
        assert train_end < valid_end <= len(series)
        assert train_end >= forecasting.MIN_TRAIN_OBSERVATIONS
        if previous_start is not None:
            assert valid_end <= previous_start  # newer folds stay in the future
        previous_start = train_end


def test_backtest_never_scores_on_training_days():
    """A fold's validation window must start after its training window ends."""
    series = _series(90)
    metrics = forecasting.backtest(series, horizon=14, factory=None, max_folds=2)
    for fold in metrics["fold_details"]:
        assert fold["validation_start"] > fold["train_end"]


def test_features_only_use_past_values():
    series = _series(40)
    frame = forecasting.design_matrix(series)
    position = 20
    assert frame["lag1"].iloc[position] == series.iloc[position - 1]
    assert frame["lag7"].iloc[position] == series.iloc[position - 7]
    assert frame["roll7"].iloc[position] == pytest.approx(series.iloc[position - 7:position].mean())
    # Mutating the future must not change any feature at or before `position`.
    mutated = series.copy()
    mutated.iloc[position + 1:] = mutated.iloc[position + 1:] + 1000
    mutated_frame = forecasting.design_matrix(mutated)
    pd.testing.assert_series_equal(
        frame.iloc[: position + 1]["lag1"], mutated_frame.iloc[: position + 1]["lag1"]
    )
    pd.testing.assert_series_equal(
        frame.iloc[: position + 1]["roll7"], mutated_frame.iloc[: position + 1]["roll7"]
    )


def test_seasonal_naive_baseline_repeats_the_same_weekday():
    series = pd.Series(
        [float(value) for value in range(1, 15)],
        index=pd.date_range("2026-01-01", periods=14, freq="D"),
    )
    predictions = forecasting.seasonal_naive_forecast(series, horizon=7)
    assert list(predictions) == [8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0]


# ---------------------------------------------------------------- data handling
def test_build_series_separates_missing_days_from_zero_sales():
    observed = {
        date(2026, 1, 1): 5.0,
        date(2026, 1, 2): 0.0,   # genuine zero-sale record
        date(2026, 1, 4): 7.0,   # 2026-01-03 is a missing observation
    }
    info = forecasting.build_series(observed, missing_day_policy="zero")
    assert info["observed_days"] == 3
    assert info["missing_days"] == 1
    assert info["zero_sales_days"] == 1
    assert info["filled"].loc["2026-01-03"] == 0.0

    interpolated = forecasting.build_series(observed, missing_day_policy="interpolate")
    assert interpolated["filled"].loc["2026-01-03"] == pytest.approx(3.5)


def test_insufficient_history_raises_a_clear_error():
    product = {
        "product_id": 1,
        "name": "Sparse",
        "sku": "SP-1",
        "category": "Testing",
        "observed": {date(2026, 1, 1) + timedelta(days=i): 2.0 for i in range(4)},
    }
    with pytest.raises(InsufficientHistory):
        forecasting.forecast_product(product, horizon_days=7)


def test_forecast_product_returns_horizon_rows_and_metrics():
    product = {
        "product_id": 7,
        "name": "Steady",
        "sku": "ST-7",
        "category": "Testing",
        "observed": {
            (date(2026, 1, 1) + timedelta(days=i)): float(20 + 5 * (i % 7)) for i in range(120)
        },
    }
    outcome = forecasting.forecast_product(product, horizon_days=14, model_choice="ridge")
    assert len(outcome["forecast_rows"]) == 14
    assert outcome["model_name"] in {"ridge", "seasonal_naive"}
    assert outcome["baseline_metrics"]["n"] > 0
    assert outcome["metrics"]["mae"] is not None
    for row in outcome["forecast_rows"]:
        assert row["predicted_units"] >= 0
        assert row["lower_bound"] <= row["predicted_units"] <= row["upper_bound"]


def test_short_history_falls_back_to_baseline_with_a_warning():
    product = {
        "product_id": 8,
        "name": "Young",
        "sku": "YG-8",
        "category": "Testing",
        "observed": {
            (date(2026, 1, 1) + timedelta(days=i)): float(5 + (i % 3)) for i in range(20)
        },
    }
    outcome = forecasting.forecast_product(product, horizon_days=7, model_choice="auto")
    assert outcome["is_baseline"] is True
    assert any("below the" in message for message in outcome["warnings"])


# ------------------------------------------------------------------ persistence
def test_run_forecast_persists_results_and_metrics(small_sales_db):
    db = small_sales_db["db"]
    result = forecasting.run_forecast(db, horizon_days=7, model="seasonal_naive")
    run_id = int(result["run"]["id"])

    run = forecast_repo.get_run(db, run_id)
    assert run is not None
    assert run["status"] == "completed"
    assert run["horizon_days"] == 7
    assert run["baseline_used"] == "seasonal_naive"
    assert run["products_forecasted"] == 2
    assert run["train_start"] and run["train_end"]
    assert run["validation_start"] and run["validation_end"]

    results = forecast_repo.get_results(db, run_id)
    assert len(results) == 14  # 2 products x 7 days
    assert all(row["is_baseline"] == 1 for row in results)

    metrics = forecast_repo.get_metrics(db, run_id)
    assert len(metrics) == 2
    assert all(row["mae"] is not None for row in metrics)
    # Forecast horizon must start after the last observed day.
    first_forecast = min(row["forecast_date"] for row in results)
    last_actual = db.scalar("SELECT MAX(sale_date) AS d FROM sales_records")
    assert first_forecast > last_actual

    summary = run["summary_metrics"]
    assert summary["selected"]["wape"] is not None
    assert summary["products_compared"] == 2


def test_forecast_run_without_data_reports_a_clear_error(db):
    with pytest.raises(InsufficientHistory):
        forecasting.run_forecast(db, horizon_days=7, model="auto")


def test_available_models_always_include_the_baseline_options():
    models = forecasting.available_models()
    assert "hist_gradient_boosting" in models
    assert "ridge" in models
    assert "seasonal_naive" not in models  # baseline is handled separately
