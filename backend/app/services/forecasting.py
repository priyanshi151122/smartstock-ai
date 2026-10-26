"""Demand forecasting engine.

Pipeline
--------
1. Aggregate daily per-product demand from persisted sales rows.
2. Re-index onto a continuous daily calendar so that *missing observations* are
   explicitly distinguished from *genuine zero sales*.
3. Build calendar + lag + rolling features (only from strictly past values, so no
   future information can leak into the past).
4. Back-test a seasonal-naive baseline and one or more machine-learning models
   using rolling-origin (chronological) splits.
5. Select a model honestly: the baseline wins whenever the ML model does not
   measurably beat it, and every product carries its own validation metrics.
6. Refit the selected approach on the full history and predict 7/14/30 days.

Nothing in this module ever trains on data that is chronologically after the
point being predicted, and no metric is reported for a product without an
evaluation window.
"""

from __future__ import annotations

import math
import time
from datetime import date, timedelta
from typing import Any, Callable

import numpy as np
import pandas as pd

from app.config import get_settings
from app.db import Database
from app.repositories import catalog, forecasts as forecast_repo, inventory as inventory_repo, sales as sales_repo
from app.utils import json_dumps, json_loads, round2, utcnow_iso

MIN_BASELINE_DAYS = 8
MIN_TRAIN_OBSERVATIONS = 24
SEASON_LENGTH = 7
FEATURE_COLUMNS = [
    "dow", "dom", "month", "is_weekend",
    "lag1", "lag7", "lag14", "roll7", "roll7_std", "roll14",
]

LIMITATIONS = [
    "Forecasts assume the recent sales pattern continues; promotions, price changes, "
    "festivals and stockouts in the history are not modelled explicitly.",
    "A stockout in the historical window depresses recorded demand, so the model may "
    "under-forecast products that were unavailable.",
    "Metrics come from a single short hold-out (or a few rolling folds) and are "
    "therefore indicative rather than a guarantee of future accuracy.",
    "Prediction intervals are residual-based approximations, not calibrated quantiles.",
    "Calendars use weekday/month seasonality only; no holiday calendar is applied.",
]


class InsufficientHistory(Exception):
    """Raised when a product cannot support a naive baseline either."""


# ------------------------------------------------------------------- data load
def load_daily_demand(
    db: Database,
    *,
    product_ids: list[int] | None = None,
    category: str | None = None,
    data_source: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[int, dict[str, Any]]:
    """Daily units per product, plus product metadata, in one query."""
    clauses, params = ["p.is_active = 1"], []
    if product_ids:
        ids = [int(pid) for pid in product_ids]
        clauses.append(f"s.product_id IN ({','.join('?' for _ in ids)})")
        params += ids
    if category:
        clauses.append("p.category = ?")
        params.append(category)
    if data_source == "demo":
        clauses.append("s.is_demo = 1")
    elif data_source == "actual":
        clauses.append("s.is_demo = 0")
    if start_date:
        clauses.append("s.sale_date >= ?")
        params.append(str(start_date))
    if end_date:
        clauses.append("s.sale_date <= ?")
        params.append(str(end_date))

    rows = db.query(
        f"""
        SELECT s.product_id, s.sale_date, SUM(s.quantity) AS units,
               p.name, p.sku, p.category
        FROM sales_records s
        JOIN products p ON p.id = s.product_id
        WHERE {' AND '.join(clauses)}
        GROUP BY s.product_id, s.sale_date, p.name, p.sku, p.category
        ORDER BY s.product_id, s.sale_date
        """,
        params,
    )
    grouped: dict[int, dict[str, Any]] = {}
    for row in rows:
        pid = int(row["product_id"])
        bucket = grouped.setdefault(
            pid,
            {
                "product_id": pid,
                "name": row["name"],
                "sku": row["sku"],
                "category": row["category"],
                "observed": {},
            },
        )
        bucket["observed"][date.fromisoformat(str(row["sale_date"]))] = float(row["units"] or 0)
    return grouped


def build_series(
    observed: dict[date, float], *, missing_day_policy: str = "zero"
) -> dict[str, Any]:
    """Create a calendar-continuous daily series from sparse observations."""
    if not observed:
        raise InsufficientHistory("No dated sales were found for this product.")
    ordered = sorted(observed.items())
    start, end = ordered[0][0], ordered[-1][0]
    index = pd.date_range(start=start, end=end, freq="D")
    raw = pd.Series(index=index, dtype="float64")
    for day, units in ordered:
        raw.loc[pd.Timestamp(day)] = float(units)

    observed_mask = raw.notna()
    missing_days = int((~observed_mask).sum())
    observed_days = int(observed_mask.sum())

    filled = raw.copy()
    if missing_days:
        if missing_day_policy == "interpolate" and observed_days >= 2:
            filled = raw.interpolate(method="linear", limit_direction="both")
        else:
            filled = raw.fillna(0.0)
    filled = filled.clip(lower=0)

    zero_sales_days = int(((raw == 0)).sum())
    return {
        "raw": raw,
        "filled": filled,
        "start": start,
        "end": end,
        "observed_days": observed_days,
        "missing_days": missing_days,
        "zero_sales_days": zero_sales_days,
        "policy": missing_day_policy,
    }


# -------------------------------------------------------------------- features
def design_matrix(series: pd.Series) -> pd.DataFrame:
    """Calendar + strictly-lagged features (never uses same-day or future values)."""
    frame = pd.DataFrame({"y": series.astype(float)})
    index = series.index
    frame["dow"] = index.dayofweek
    frame["dom"] = index.day
    frame["month"] = index.month
    frame["is_weekend"] = (index.dayofweek >= 5).astype(int)
    frame["lag1"] = series.shift(1)
    frame["lag7"] = series.shift(7)
    frame["lag14"] = series.shift(14)
    frame["roll7"] = series.shift(1).rolling(7).mean()
    frame["roll7_std"] = series.shift(1).rolling(7).std()
    frame["roll14"] = series.shift(1).rolling(14).mean()
    return frame


def supervised_frame(series: pd.Series) -> pd.DataFrame:
    frame = design_matrix(series)
    return frame.dropna(subset=FEATURE_COLUMNS)


# ---------------------------------------------------------------------- models
def _model_factories() -> dict[str, Callable[[], Any]]:
    from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    def make_hist() -> Any:
        return HistGradientBoostingRegressor(
            max_iter=160, learning_rate=0.08, max_depth=4, min_samples_leaf=5, random_state=42, early_stopping=False
        )

    def make_rf() -> Any:
        return RandomForestRegressor(
            n_estimators=80, min_samples_leaf=2, max_depth=8, random_state=42, n_jobs=1
        )

    def make_ridge() -> Any:
        return Pipeline([("scale", StandardScaler()), ("ridge", Ridge(alpha=1.0))])

    factories: dict[str, Callable[[], Any]] = {
        "hist_gradient_boosting": make_hist,
        "random_forest": make_rf,
        "ridge": make_ridge,
    }

    try:  # XGBoost is optional: only used when the dependency is installed.
        from xgboost import XGBRegressor

        def make_xgb() -> Any:
            return XGBRegressor(
                n_estimators=160,
                learning_rate=0.08,
                max_depth=3,
                tree_method="hist",
                subsample=0.9,
                colsample_bytree=0.9,
                random_state=42,
                n_jobs=1,
                verbosity=0,
            )

        factories["xgboost"] = make_xgb
    except Exception:  # pragma: no cover - depends on optional install
        pass
    return factories


def available_models() -> list[str]:
    return sorted(_model_factories())


def seasonal_naive_forecast(series: pd.Series, horizon: int, season: int = SEASON_LENGTH) -> np.ndarray:
    """Baseline: today equals the same weekday last week (recursive)."""
    history = list(series.astype(float).values)
    predictions: list[float] = []
    for step in range(horizon):
        value = history[-season] if len(history) >= season else (history[-1] if history else 0.0)
        value = max(0.0, float(value))
        predictions.append(value)
        history.append(value)
    return np.array(predictions)


def iterative_mean_forecast(series: pd.Series, horizon: int) -> np.ndarray:
    """Last-resort baseline when even one season of history is unavailable."""
    history = series.astype(float)
    mean_value = float(history.tail(min(len(history), 28)).mean() or 0.0)
    return np.full(horizon, max(0.0, mean_value))


def recursive_ml_forecast(model: Any, series: pd.Series, horizon: int) -> np.ndarray:
    """Multi-step forecast feeding predictions back as lags (never uses actuals).

    Implemented on a NumPy buffer because this loop runs once per validation fold
    and once per product; rebuilding a DataFrame on every step dominated runtime.
    """
    values = series.astype(float).to_numpy()
    last_date = series.index[-1]
    if len(values) < 14:
        raise ValueError("at least 14 observations are required for lag features")
    predictions: list[float] = []
    for step in range(horizon):
        next_date = last_date + pd.Timedelta(days=step + 1)
        recent7 = values[-7:]
        recent14 = values[-14:]
        row = [
            float(next_date.dayofweek),
            float(next_date.day),
            float(next_date.month),
            1.0 if next_date.dayofweek >= 5 else 0.0,
            float(values[-1]),
            float(values[-7]),
            float(values[-14]),
            float(recent7.mean()),
            float(recent7.std(ddof=1)) if len(recent7) > 1 else 0.0,
            float(recent14.mean()),
        ]
        value = float(max(0.0, model.predict(np.asarray([row], dtype=float))[0]))
        predictions.append(value)
        values = np.append(values, value)
    return np.asarray(predictions, dtype=float)


# --------------------------------------------------------------------- metrics
def compute_metrics(actual: np.ndarray | list[float], predicted: np.ndarray | list[float]) -> dict[str, Any]:
    """MAE, RMSE and WAPE with explicit validity checks.

    WAPE is undefined when the observed demand over the evaluation window is zero,
    in which case ``None`` is returned instead of a misleading zero.
    """
    actual_arr = np.asarray(actual, dtype=float).ravel()
    predicted_arr = np.asarray(predicted, dtype=float).ravel()
    if actual_arr.size != predicted_arr.size or actual_arr.size == 0:
        return {"mae": None, "rmse": None, "wape": None, "n": 0, "note": "no overlapping observations"}
    errors = predicted_arr - actual_arr
    mae = float(np.mean(np.abs(errors)))
    rmse = float(math.sqrt(np.mean(errors ** 2)))
    denominator = float(np.sum(np.abs(actual_arr)))
    wape = float(np.sum(np.abs(errors)) / denominator) if denominator > 0 else None
    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "wape": round(wape, 4) if wape is not None else None,
        "n": int(actual_arr.size),
        "actual_total": round(float(np.sum(actual_arr)), 4),
        "note": None if wape is not None else "WAPE undefined: zero observed demand in the validation window",
    }


def _folds(length: int, horizon: int, max_folds: int = 3) -> list[tuple[int, int]]:
    """Rolling-origin folds as (train_end, valid_end) exclusive indices."""
    usable_horizon = max(7, min(horizon, max(7, length // 6)))
    folds: list[tuple[int, int]] = []
    for fold in range(max_folds):
        train_end = length - usable_horizon * (fold + 1)
        if train_end < MIN_TRAIN_OBSERVATIONS:
            break
        folds.append((train_end, train_end + usable_horizon))
    return folds


def backtest(
    series: pd.Series,
    *,
    horizon: int,
    factory: Callable[[], Any] | None,
    max_folds: int = 3,
) -> dict[str, Any]:
    """Chronological rolling-origin back-test for one model (or the baseline)."""
    folds = _folds(len(series), horizon, max_folds)
    actuals: list[float] = []
    predictions: list[float] = []
    fold_details: list[dict[str, Any]] = []
    failures = 0

    for train_end, valid_end in folds:
        train = series.iloc[:train_end]
        valid = series.iloc[train_end:valid_end]
        if len(valid) == 0:
            continue
        try:
            if factory is None:
                predicted = seasonal_naive_forecast(train, len(valid))
            else:
                frame = supervised_frame(train)
                if len(frame) < 10:
                    continue
                model = factory()
                model.fit(frame[FEATURE_COLUMNS].to_numpy(), frame["y"].to_numpy())
                predicted = recursive_ml_forecast(model, train, len(valid))
        except Exception:  # pragma: no cover - defensive: never fail the whole run
            failures += 1
            continue
        actual_values = valid.to_numpy(dtype=float)
        actuals.extend(actual_values.tolist())
        predictions.extend(np.asarray(predicted, dtype=float).tolist())
        fold_details.append(
            {
                "train_end": str(train.index[-1].date()),
                "validation_start": str(valid.index[0].date()),
                "validation_end": str(valid.index[-1].date()),
                "metrics": compute_metrics(actual_values, predicted),
            }
        )

    metrics = compute_metrics(actuals, predictions)
    metrics["folds"] = len(fold_details)
    metrics["fold_details"] = fold_details
    metrics["failures"] = failures
    residuals = np.asarray(predictions, dtype=float) - np.asarray(actuals, dtype=float)
    metrics["residual_std"] = round(float(np.std(residuals)), 4) if residuals.size > 1 else None
    return metrics


# ------------------------------------------------------------------ per product
def forecast_product(
    product: dict[str, Any],
    *,
    horizon_days: int,
    model_choice: str = "auto",
    missing_day_policy: str = "zero",
    min_history_days: int | None = None,
    reference_date: date | None = None,
) -> dict[str, Any]:
    """Forecast one product, returning predictions, metrics, warnings and notes."""
    settings = get_settings()
    min_history = int(min_history_days or settings.min_history_days_for_ml)
    series_info = build_series(product["observed"], missing_day_policy=missing_day_policy)
    series: pd.Series = series_info["filled"]
    n_obs = int(series_info["observed_days"])
    warnings: list[str] = []
    notes: list[str] = []

    if n_obs < MIN_BASELINE_DAYS:
        raise InsufficientHistory(
            f"Only {n_obs} distinct sales days were found; at least {MIN_BASELINE_DAYS} are needed "
            "for even a weekly-naive baseline."
        )
    if series_info["missing_days"]:
        notes.append(
            f"{series_info['missing_days']} calendar day(s) had no observation and were treated as "
            f"{'interpolated values' if missing_day_policy == 'interpolate' else 'zero demand'}; "
            f"{series_info['zero_sales_days']} day(s) were genuine zero-sale records."
        )

    baseline_metrics = backtest(series, horizon=horizon_days, factory=None)
    if baseline_metrics["n"] == 0:
        warnings.append("Baseline could not be evaluated on a validation window; metrics unavailable.")

    factories = _model_factories()
    candidates: list[str] = []
    if model_choice == "auto":
        # Keep the automatic comparison focused: two strong, fast learners plus
        # XGBoost only for long histories. Explicit requests always win.
        candidates = [name for name in ("hist_gradient_boosting", "ridge") if name in factories]
        if "xgboost" in factories and len(series) >= 120:
            candidates.append("xgboost")
        # Random forests are supported on request but excluded from "auto":
        # per-row recursive prediction makes them an order of magnitude slower.
    elif model_choice in factories:
        candidates = [model_choice]
    elif model_choice == "seasonal_naive":
        candidates = []
    else:
        warnings.append(f"Requested model '{model_choice}' is not installed; the baseline was used instead.")

    ml_results: dict[str, dict[str, Any]] = {}
    if n_obs < min_history:
        if candidates:
            warnings.append(
                f"Only {n_obs} days of history (below the {min_history}-day threshold for machine "
                "learning); a seasonal-naive baseline was used. Import more history for a trained model."
            )
    else:
        for name in candidates:
            result = backtest(series, horizon=horizon_days, factory=factories[name])
            if result["n"] == 0 or result.get("failures"):
                warnings.append(
                    f"{name} could not be validated on this series and was excluded."
                )
                continue
            ml_results[name] = result

    # ------------------------------------------------- model selection (honest)
    chosen_model: str | None = None
    if ml_results:
        def score(metrics: dict[str, Any]) -> float:
            value = metrics.get("wape")
            if value is None:
                value = (metrics.get("mae") or 0) / max(1.0, metrics.get("actual_total") or 1.0)
            return float(value)

        best_name = min(ml_results, key=lambda name: score(ml_results[name]))
        best_metrics = ml_results[best_name]
        baseline_score = score(baseline_metrics) if baseline_metrics["n"] else float("inf")
        if score(best_metrics) < baseline_score:
            chosen_model = best_name
        else:
            notes.append(
                f"No machine-learning model beat the seasonal-naive baseline on the validation "
                f"window ({best_name} WAPE {score(best_metrics):.3f} vs baseline "
                f"{baseline_score:.3f}); the baseline is used."
            )
    elif model_choice != "seasonal_naive" and not candidates:
        notes.append("Seasonal-naive baseline used (no ML model requested or available).")

    use_baseline = chosen_model is None
    selected_metrics = baseline_metrics if use_baseline else ml_results[chosen_model]

    # -------------------------------------------------------------- final model
    horizon_start = (reference_date or series.index[-1].date()) + timedelta(days=1)
    if use_baseline:
        predictions = seasonal_naive_forecast(series, horizon_days)
        model_name = "seasonal_naive"
    else:
        frame = supervised_frame(series)
        model = factories[chosen_model]()
        model.fit(frame[FEATURE_COLUMNS].to_numpy(), frame["y"].to_numpy())
        predictions = recursive_ml_forecast(model, series, horizon_days)
        model_name = str(chosen_model)

    residual_std = selected_metrics.get("residual_std")
    if residual_std is None:
        residual_std = float(series.std(ddof=0)) if len(series) > 2 else 0.0
    band = 1.645 * float(residual_std or 0.0)

    dates = [horizon_start + timedelta(days=offset) for offset in range(horizon_days)]
    forecast_rows = [
        {
            "product_id": int(product["product_id"]),
            "forecast_date": day.isoformat(),
            "predicted_units": round(float(max(0.0, value)), 3),
            "lower_bound": round(float(max(0.0, value - band)), 3),
            "upper_bound": round(float(max(0.0, value + band)), 3),
            "model_name": model_name,
            "is_baseline": use_baseline,
        }
        for day, value in zip(dates, predictions)
    ]

    metric_rows = [
        {
            "product_id": int(product["product_id"]),
            "model_name": "seasonal_naive",
            "is_baseline": True,
            "is_selected": use_baseline,
            "mae": baseline_metrics["mae"],
            "rmse": baseline_metrics["rmse"],
            "wape": baseline_metrics["wape"],
            "validation_days": baseline_metrics["n"],
            "note": "Seasonal-naive (same weekday last week)."
            + (f" {baseline_metrics['note']}" if baseline_metrics.get("note") else ""),
        }
    ]
    for name, result in ml_results.items():
        metric_rows.append(
            {
                "product_id": int(product["product_id"]),
                "model_name": name,
                "is_baseline": False,
                "is_selected": (not use_baseline) and name == chosen_model,
                "mae": result["mae"],
                "rmse": result["rmse"],
                "wape": result["wape"],
                "validation_days": result["n"],
                "note": f"{result['folds']} rolling-origin fold(s), {result['n']} validation days."
                + (f" {result['note']}" if result.get("note") else ""),
            }
        )

    return {
        "product_id": int(product["product_id"]),
        "forecast_rows": forecast_rows,
        "metric_rows": metric_rows,
        "model_name": model_name,
        "is_baseline": use_baseline,
        "metrics": selected_metrics,
        "baseline_metrics": baseline_metrics,
        "observed_days": n_obs,
        "missing_days": series_info["missing_days"],
        "zero_sales_days": series_info["zero_sales_days"],
        "history_start": series_info["start"].isoformat(),
        "history_end": series_info["end"].isoformat(),
        "train_observations": int(len(supervised_frame(series))) if not use_baseline else int(len(series)),
        "warnings": warnings,
        "notes": notes,
        "limitations": list(LIMITATIONS),
    }


# ------------------------------------------------------------------- orchestration
def run_forecast(
    db: Database,
    *,
    horizon_days: int = 14,
    model: str = "auto",
    product_ids: list[int] | None = None,
    category: str | None = None,
    data_source: str | None = None,
    missing_day_policy: str = "zero",
) -> dict[str, Any]:
    """Execute a full forecasting run and persist runs, results and metrics."""
    settings = get_settings()
    started = time.perf_counter()
    dataset = load_daily_demand(
        db, product_ids=product_ids, category=category, data_source=data_source
    )
    if not dataset:
        raise InsufficientHistory(
            "No sales records matched the requested scope. Import sales data before forecasting."
        )

    resolved_source = data_source or (
        "demo"
        if db.scalar("SELECT COUNT(*) AS c FROM sales_records WHERE is_demo = 0", None, 0) == 0
        else "actual"
    )
    run_id = forecast_repo.create_run(
        db,
        horizon_days=horizon_days,
        model_requested=model,
        data_source=resolved_source,
        params={
            "product_ids": product_ids,
            "category": category,
            "missing_day_policy": missing_day_policy,
            "min_history_days_for_ml": settings.min_history_days_for_ml,
            "season_length": SEASON_LENGTH,
            "features": FEATURE_COLUMNS,
        },
    )

    # Use one shared forecast origin so every product covers the same future window.
    anchor = max(max(product["observed"].keys()) for product in dataset.values())

    result_rows: list[tuple[Any, ...]] = []
    metric_rows: list[tuple[Any, ...]] = []
    warnings: list[str] = []
    notes: list[str] = []
    insufficient: list[str] = []
    products_forecasted = 0
    models_used: set[str] = set()
    comparison: list[dict[str, Any]] = []
    train_starts, train_ends = [], []
    validation_starts, validation_ends = [], []

    for pid, product in dataset.items():
        try:
            outcome = forecast_product(
                product,
                horizon_days=horizon_days,
                model_choice=model,
                missing_day_policy=missing_day_policy,
                min_history_days=settings.min_history_days_for_ml,
                reference_date=anchor,
            )
        except InsufficientHistory as exc:
            insufficient.append(f"{product['name']}: {exc}")
            continue

        products_forecasted += 1
        models_used.add(outcome["model_name"])
        train_starts.append(outcome["history_start"])
        train_ends.append(outcome["history_end"])
        for fold in outcome["metrics"].get("fold_details", []):
            validation_starts.append(fold["validation_start"])
            validation_ends.append(fold["validation_end"])
        warnings.extend(outcome["warnings"])
        notes.extend(outcome["notes"])
        comparison.append(
            {
                "product": product["name"],
                "model": outcome["model_name"],
                "model_wape": outcome["metrics"].get("wape"),
                "baseline_wape": outcome["baseline_metrics"].get("wape"),
                "validation_days": outcome["metrics"].get("n"),
            }
        )

        for row in outcome["forecast_rows"]:
            result_rows.append(
                (
                    run_id,
                    row["product_id"],
                    row["forecast_date"],
                    row["predicted_units"],
                    row["lower_bound"],
                    row["upper_bound"],
                    row["model_name"],
                    1 if row["is_baseline"] else 0,
                )
            )
        for row in outcome["metric_rows"]:
            metric_rows.append(
                (
                    run_id,
                    row["product_id"],
                    row["model_name"],
                    1 if row["is_baseline"] else 0,
                    1 if row["is_selected"] else 0,
                    row["mae"],
                    row["rmse"],
                    row["wape"],
                    row["validation_days"],
                    outcome["train_observations"],
                    outcome["observed_days"],
                    outcome["missing_days"],
                    row["note"],
                )
            )

    if products_forecasted == 0:
        forecast_repo.finalise_run(
            db,
            run_id,
            {
                "status": "failed",
                "notes": "No product had enough history to forecast.",
                "warnings": insufficient,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            },
        )
        raise InsufficientHistory(
            "No product had enough history to forecast. At least "
            f"{MIN_BASELINE_DAYS} days of sales per product are required. "
            + (insufficient[0] if insufficient else "")
        )

    forecast_repo.insert_forecast_results(db, result_rows)
    forecast_repo.insert_forecast_metrics(db, metric_rows)

    # --------------------------------------------------- aggregate evaluation
    def aggregate(selected_only: bool) -> dict[str, Any]:
        rows = db.query(
            """
            SELECT m.mae, m.rmse, m.wape, m.validation_days
            FROM forecast_metrics m WHERE m.run_id = ?
            """ + (" AND m.is_selected = 1" if selected_only else ""),
            (run_id,),
        )
        wape_rows = [row for row in rows if row["wape"] is not None and row["validation_days"]]
        total_weight = sum(int(row["validation_days"]) for row in wape_rows)
        weighted_wape = (
            sum(float(row["wape"]) * int(row["validation_days"]) for row in wape_rows) / total_weight
            if total_weight
            else None
        )
        mae_values = [float(row["mae"]) for row in rows if row["mae"] is not None]
        rmse_values = [float(row["rmse"]) for row in rows if row["rmse"] is not None]
        return {
            "products": len(rows),
            "mean_mae": round(sum(mae_values) / len(mae_values), 4) if mae_values else None,
            "mean_rmse": round(sum(rmse_values) / len(rmse_values), 4) if rmse_values else None,
            "wape": round(weighted_wape, 4) if weighted_wape is not None else None,
            "validation_days": total_weight,
        }

    selected_summary = aggregate(selected_only=True)
    baseline_summary = aggregate(selected_only=False)
    improvement = None
    if (
        selected_summary.get("wape") is not None
        and baseline_summary.get("wape")
        and baseline_summary["wape"] > 0
    ):
        improvement = round((baseline_summary["wape"] - selected_summary["wape"]) / baseline_summary["wape"] * 100, 1)

    summary_metrics = {
        "selected": selected_summary,
        "all_models": baseline_summary,
        "wape_improvement_vs_baseline_pct": improvement,
        "models_used": sorted(models_used),
        "products_compared": len(comparison),
        "products_baseline_better_or_equal": sum(
            1
            for row in comparison
            if row["baseline_wape"] is not None
            and (row["model_wape"] is None or row["baseline_wape"] <= row["model_wape"])
        ),
    }

    duration_ms = int((time.perf_counter() - started) * 1000)
    forecast_repo.finalise_run(
        db,
        run_id,
        {
            "model_used": ", ".join(sorted(models_used)),
            "baseline_used": "seasonal_naive",
            "status": "completed",
            "products_forecasted": products_forecasted,
            "products_insufficient": len(insufficient),
            "train_start": min(train_starts) if train_starts else None,
            "train_end": max(train_ends) if train_ends else None,
            "validation_start": min(validation_starts) if validation_starts else None,
            "validation_end": max(validation_ends) if validation_ends else None,
            "summary_metrics": summary_metrics,
            "warnings": sorted(set(warnings))[:20] + insufficient[:10],
            "notes": " ".join(sorted(set(notes))[:10]),
            "duration_ms": duration_ms,
        },
    )

    from app.repositories import audit

    audit.log(
        db,
        action="forecast.completed",
        entity_type="forecast_run",
        entity_id=run_id,
        actor="forecasting-engine",
        details={
            "horizon_days": horizon_days,
            "products": products_forecasted,
            "models": sorted(models_used),
            "data_source": resolved_source,
            "wape": selected_summary.get("wape"),
        },
    )

    run = forecast_repo.get_run(db, run_id) or {}
    return {
        "run": run,
        "summary_metrics": summary_metrics,
        "insufficient": insufficient,
        "horizon_days": horizon_days,
        "data_source": resolved_source,
    }


def run_detail(db: Database, run_id: int) -> dict[str, Any]:
    run = forecast_repo.get_run(db, run_id)
    if not run:
        raise ValueError(f"Forecast run {run_id} was not found.")
    metrics = forecast_repo.get_metrics(db, run_id)
    results = forecast_repo.get_results(db, run_id)
    horizon_days = int(run["horizon_days"])
    return {
        "id": run["id"],
        "horizon_days": horizon_days,
        "model_requested": run["model_requested"],
        "model_used": run["model_used"],
        "baseline_used": run["baseline_used"],
        "status": run["status"],
        "data_source": run["data_source"],
        "products_forecasted": run["products_forecasted"],
        "products_insufficient": run["products_insufficient"],
        "train_start": run.get("train_start"),
        "train_end": run.get("train_end"),
        "validation_start": run.get("validation_start"),
        "validation_end": run.get("validation_end"),
        "summary_metrics": run.get("summary_metrics"),
        "warnings": run.get("warnings") or [],
        "notes": run.get("notes"),
        "duration_ms": run.get("duration_ms"),
        "created_at": run["created_at"],
        "metrics": metrics,
        "results": results,
        "limitations": LIMITATIONS,
    }


def product_detail(db: Database, run_id: int, product_id: int) -> dict[str, Any]:
    run = forecast_repo.get_run(db, run_id)
    if not run:
        raise ValueError(f"Forecast run {run_id} was not found.")
    product = catalog.get_product(db, product_id)
    if not product:
        raise ValueError(f"Product {product_id} was not found.")
    metrics = forecast_repo.get_metrics(db, run_id, product_id=product_id)
    forecast_rows = forecast_repo.get_results(db, run_id, product_id=product_id)
    observed = load_daily_demand(db, product_ids=[product_id], data_source=run["data_source"]).get(product_id)
    history: list[dict[str, Any]] = []
    if observed:
        info = build_series(observed["observed"])
        raw = info["raw"]
        window = raw.tail(90)
        history = [
            {
                "period": index.date().isoformat(),
                "actual": (None if pd.isna(value) else round(float(value), 3)),
                "forecast": None,
            }
            for index, value in window.items()
        ]
    for row in forecast_rows:
        history.append(
            {
                "period": row["forecast_date"],
                "actual": None,
                "forecast": round(float(row["predicted_units"]), 3),
            }
        )
    return {
        "run": {
            "id": run["id"],
            "horizon_days": run["horizon_days"],
            "model_requested": run["model_requested"],
            "model_used": run["model_used"],
            "baseline_used": run["baseline_used"],
            "status": run["status"],
            "data_source": run["data_source"],
            "products_forecasted": run["products_forecasted"],
            "products_insufficient": run["products_insufficient"],
            "train_start": run.get("train_start"),
            "train_end": run.get("train_end"),
            "validation_start": run.get("validation_start"),
            "validation_end": run.get("validation_end"),
            "summary_metrics": run.get("summary_metrics"),
            "warnings": run.get("warnings") or [],
            "notes": run.get("notes"),
            "duration_ms": run.get("duration_ms"),
            "created_at": run["created_at"],
        },
        "product_id": product_id,
        "sku": product["sku"],
        "product_name": product["name"],
        "history": history,
        "forecast": forecast_rows,
        "metrics": metrics,
        "limitations": LIMITATIONS,
    }
