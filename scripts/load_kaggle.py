"""Load a reproducible sample of the Kaggle price dataset into Postgres.

    python scripts/load_kaggle.py --dry-run
    python scripts/load_kaggle.py --products 200 --seed 42
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from price_intel.datasets.kaggle import DEFAULT_CSV, load_sample


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Kaggle CSV to load")
    parser.add_argument(
        "--products",
        type=int,
        default=200,
        help="Number of product IDs to sample across categories (default: 200)",
    )
    parser.add_argument("--seed", type=int, default=42, help="Sampling seed (default: 42)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the sample size without writing to the database",
    )
    return parser.parse_args()


def main(args: argparse.Namespace) -> int:
    try:
        stats = load_sample(
            args.csv,
            max_products=args.products,
            seed=args.seed,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError) as exc:
        print(f"kaggle load error: {exc}", file=sys.stderr)
        return 1

    print(
        f"kaggle: {stats.products} products, {stats.listings} listings, "
        f"{stats.rows_expected} price rows expected",
        flush=True,
    )
    if stats.rows_inserted is not None:
        print(
            f"kaggle: {stats.rows_inserted} inserted, {stats.rows_skipped} already present",
            flush=True,
        )
    else:
        print("dry run: no database changes", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(parse_args()))
