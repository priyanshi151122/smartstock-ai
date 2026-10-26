# Forecasting methodology & evaluation

This document describes exactly what `backend/app/services/forecasting.py` does, what it does not
do, and how the numbers reported in the UI are produced.

## 1. Input series

* Source: `sales_records` grouped by `(product_id, sale_date)` → `SUM(quantity)`.
* Scope filters: product list, category, `data_source=actual|demo`.
* A product needs ≥ **8 distinct sale days** for the seasonal-naive baseline; below
  `MIN_HISTORY_DAYS_FOR_ML` (default 42 observations) machine-learning models are skipped for that
  product and the baseline is used with an explicit warning.

### Missing observations vs. genuine zero sales

The series is re-indexed onto a continuous daily calendar.

| Case | Meaning | Handling (`missing_day_policy`) |
|---|---|---|
| A date with a stored row and `quantity > 0` | sales happened | used as-is |
| A date with a stored row and `quantity = 0` | **genuine zero-sale record** | kept as 0 |
| A date with **no row at all** | **missing observation** | `zero` → 0, `interpolate` → linear between neighbours |

The distinction matters: treating “shop closed / not recorded” the same as “sold nothing” biases
the weekday pattern. The UI lets you pick the policy per run and the run notes record how many days
of each kind were present.

## 2. Features (no leakage)

Built from `series.shift(1)` and earlier only:

| Feature | Definition |
|---|---|
| `dow`, `dom`, `month`, `is_weekend` | calendar attributes of the target day |
| `lag1`, `lag7`, `lag14` | values 1, 7 and 14 days before the target |
| `roll7`, `roll7_std`, `roll14` | mean/std of the 7 (14) days *before* the target |

`tests/test_forecasting.py::test_features_only_use_past_values` mutates the future portion of a
series and asserts that no feature at or before the split changes.

## 3. Models

| Name | Implementation | Notes |
|---|---|---|
| `seasonal_naive` | today = same weekday last week (recursive) | the baseline, always evaluated |
| `hist_gradient_boosting` | `HistGradientBoostingRegressor(max_iter=160, lr=0.08, max_depth=4, min_samples_leaf=5)` | in `auto` |
| `ridge` | `StandardScaler` + `Ridge(alpha=1)` pipeline | in `auto` |
| `xgboost` | `XGBRegressor(n_estimators=160, lr=0.08, max_depth=3, tree_method="hist")` | in `auto` when installed and history ≥ 120 days |
| `random_forest` | `RandomForestRegressor(n_estimators=80, max_depth=8)` | explicit request only (recursive prediction is slow) |

All models are seeded with `random_state=42` and `n_jobs=1` so results are reproducible and do not
oversubscribe the host.

**Recursive multi-step forecasting.** For each future day, lag and rolling features are computed
from *previously predicted* values only; the prediction is appended to the history buffer and the
loop continues. No actual future observation is ever consumed.

## 4. Validation protocol

Rolling-origin (walk-forward) back-testing with up to 3 folds:

```
fold 0: [-------- train --------][-- 42-day validation --]
fold 1: [------ train ------)          [-- 42-day validation --]
fold 2: [---- train ---)                          [-- 42-day validation --]
```

* Validation length = `max(7, min(horizon, floor(n/6)))`; folds are dropped when training would fall
  below 24 observations.
* Each fold refits from scratch on the truncated history; the validation slice is never in the
  training index (asserted by `test_backtest_never_scores_on_training_days`).
* Predictions from all folds are pooled and scored once.

## 5. Metrics

```
MAE  = mean(|ŷ − y|)
RMSE = sqrt(mean((ŷ − y)²))
WAPE = Σ|ŷ − y| / Σ|y|
```

* **WAPE is `null` when Σ|y| = 0** — the ratio is undefined, and reporting 0 % would be a lie. The
  UI renders such rows as `n/a` with a tooltip.
* Per product, per model. Aggregates shown on the dashboard are the **mean MAE/RMSE** and a
  **validation-day weighted WAPE** across the selected models.
* Baseline metrics are stored alongside model metrics (`is_baseline = 1`), so a review can always
  compare like-for-like.

## 6. Model selection

```
best_model = argmin_WAPE(models)
if WAPE(best_model) < WAPE(baseline):  use best_model
else:                                  use baseline, record the reason in run notes
```

The run summary stores `products_baseline_better_or_equal`, so it is visible when the baseline wins.
Nothing is reported as “accurate”; the app only reports measured error.

## 7. Persistence

| Table | Contents |
|---|---|
| `forecast_runs` | horizon, requested/used model, baseline, status, products forecasted/insufficient, train & validation windows, aggregate metrics JSON, warnings, notes, duration |
| `forecast_results` | one row per product per future day: predicted units, residual-based lower/upper bounds, model, `is_baseline` |
| `forecast_metrics` | one row per product per model: MAE, RMSE, WAPE, validation days, train observations, observed/missing days, note, `is_selected` |

Prediction intervals use `1.645 × residual std` from the validation folds; they are approximations,
not calibrated quantiles — stated in the limitations list shown in the UI.

## 8. Reference results

Dataset: `data/samples/sales_demo_12_months.csv` (synthetic, seed 20240517, 24 products, 6
categories, 365 days, 7,734 rows; weekly + annual seasonality, per-product noise σ = 0.12–0.34,
occasional promo spikes, ~12 % of days missing).

Command: `POST /api/forecasts/run {"horizon_days": 14, "model": "auto"}`

| Model / aggregate | mean MAE | mean RMSE | WAPE |
|---|---|---|---|
| Selected (per-product best) | 6.67 | 8.94 | **35.1 %** |
| Seasonal-naive baseline | 7.39 | 9.87 | 38.6 % |
| Improvement | | | **+10.3 %** |

* 24/24 products forecast, 0 insufficient history.
* 1,008 pooled validation days (24 products × 42 days).
* Duration ≈ 13 s on a single core.

### Reading the numbers honestly

A WAPE of ~35 % on this dataset means roughly one third of day-to-day demand remains unexplained by
calendar + lag structure — expected, because the synthetic generator injects large multiplicative
noise and promo spikes that the model cannot observe. On real shop data with stable weekday
patterns, WAPE commonly lands lower; the correct action is to re-run on your own data and read the
per-product table, not to assume the demo figures transfer.

## 9. Limitations (also returned by the API)

1. Recent patterns are assumed to continue; promotions, price changes, festivals, weather are not
   modelled.
2. Historical stockouts depress recorded demand → forecasts can be too low for unavailable products.
3. Metrics come from a short hold-out / few folds → indicative, not a guarantee.
4. Intervals are residual-based approximations.
5. Weekday/month seasonality only; no holiday calendar.
