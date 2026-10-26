"""Load (or clear) the synthetic demo dataset directly from the command line.

Usage
-----
    python scripts/seed_demo.py            # load demo data (idempotent)
    python scripts/seed_demo.py --clear    # remove demo rows and demo products
    python scripts/seed_demo.py --forecast # load demo data, then run a 14-day forecast
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.db import get_database  # noqa: E402
from app.services import demo, forecasting, inventory_logic  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clear", action="store_true", help="remove the demo dataset")
    parser.add_argument("--seed", type=int, default=demo.DEMO_SEED)
    parser.add_argument("--forecast", action="store_true", help="run a forecast + recommendations after seeding")
    parser.add_argument("--horizon", type=int, default=14, choices=[7, 14, 30])
    args = parser.parse_args()

    database = get_database()
    if args.clear:
        print(demo.clear_demo_data(database))
        return 0

    result = demo.seed_demo_data(database, seed=args.seed)
    print(result["message"])
    if result.get("inserted_rows"):
        print(f"rows={result['inserted_rows']:,} products={result['products']} seed={args.seed}")

    if args.forecast:
        run = forecasting.run_forecast(database, horizon_days=args.horizon, model="auto", data_source="demo")
        summary = run["summary_metrics"]["selected"]
        print(
            f"forecast run #{run['run']['id']} · model={run['run']['model_used']} · "
            f"products={run['run']['products_forecasted']} · "
            f"MAE={summary.get('mean_mae')} RMSE={summary.get('mean_rmse')} WAPE={summary.get('wape')}"
        )
        reco = inventory_logic.generate_recommendations(database, run_id=int(run["run"]["id"]))
        print(f"recommendations created: {reco['created']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
