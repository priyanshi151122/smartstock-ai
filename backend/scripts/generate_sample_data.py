"""Write the sample/demo CSV files shipped with the project.

Usage
-----
    python scripts/generate_sample_data.py
    python scripts/generate_sample_data.py --days 400 --seed 1234

Outputs (in ``<project>/data/samples``):
    sales_demo_12_months.csv   ~7.7k synthetic line items, 24 products, 6 categories
    sales_sample_template.csv  minimal template matching the expected schema
    sales_validation_test.csv  deliberately broken file used by the tests/demo
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings  # noqa: E402
from app.services.demo import (  # noqa: E402
    DEMO_DAYS,
    DEMO_SEED,
    build_validation_test_frame,
    generate_demo_frame,
)
from app.services.imports import sample_template_frame  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=DEMO_DAYS)
    parser.add_argument("--seed", type=int, default=DEMO_SEED)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    settings = get_settings()
    destination = Path(args.output_dir) if args.output_dir else settings.data_path / "samples"
    destination.mkdir(parents=True, exist_ok=True)

    demo = generate_demo_frame(seed=args.seed, days=args.days)
    demo_path = destination / "sales_demo_12_months.csv"
    demo.to_csv(demo_path, index=False)

    template = sample_template_frame()
    template_path = destination / "sales_sample_template.csv"
    template.to_csv(template_path, index=False)

    broken = build_validation_test_frame()
    broken_path = destination / "sales_validation_test.csv"
    broken.to_csv(broken_path, index=False)

    print(f"demo     : {demo_path} ({len(demo):,} rows, {demo['sku'].nunique()} products, "
          f"{demo['date'].min()} → {demo['date'].max()})")
    print(f"template : {template_path} ({len(template)} rows)")
    print(f"broken   : {broken_path} ({len(broken)} rows with intentional data-quality problems)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
