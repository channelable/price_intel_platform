"""Fail if the latest scrape did not produce fresh, usable data.

    python scripts/check_freshness.py [--max-age-hours 1]
        [--max-failed-pct 5] [--max-category-failed-pct 10]

Run immediately after scrape_all.py. Exits 1 if any active product is stale,
if the overall or per-category failure budget is exceeded, or if no active
product has a current price. `unavailable` is a stock state, not a failure.
"""

from __future__ import annotations

import argparse
import sys

from price_intel.db.base import session_scope
from price_intel.freshness import (
    DEFAULT_MAX_AGE_HOURS,
    DEFAULT_MAX_CATEGORY_FAILED_PCT,
    DEFAULT_MAX_FAILED_PCT,
    get_freshness,
)


def main(
    max_age_hours: float,
    max_failed_pct: float,
    max_category_failed_pct: float,
) -> int:
    with session_scope() as session:
        freshness = get_freshness(
            session,
            max_age_hours,
            max_failed_pct,
            max_category_failed_pct,
        )

    problems = freshness.problems()
    if freshness.failed and not problems:
        print(
            f"warning: {freshness.failed}/{freshness.active} failed, "
            f"within {max_failed_pct:g}% budget",
            file=sys.stderr,
            flush=True,
        )

    last_attempt = (
        freshness.last_attempt.isoformat() if freshness.last_attempt else "never"
    )
    result = "OK" if not problems else "FAIL: " + "; ".join(problems)
    print(
        f"freshness: active={freshness.active} stale={freshness.stale} "
        f"failed={freshness.failed} with_price={freshness.with_price} "
        f"unavailable={freshness.unavailable} last_attempt={last_attempt} "
        f"max_age={max_age_hours:g}h "
        f"failed_budget={max_failed_pct:g}% "
        f"category_budget={max_category_failed_pct:g}% -> {result}",
        flush=True,
    )
    return 0 if not problems else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=DEFAULT_MAX_AGE_HOURS,
        help=(
            "fail if an active product was not attempted in this many hours "
            f"(default: {DEFAULT_MAX_AGE_HOURS:g})"
        ),
    )
    parser.add_argument(
        "--max-failed-pct",
        type=float,
        default=DEFAULT_MAX_FAILED_PCT,
        help=(
            "tolerate this percentage of active products blocked/parse_failed "
            f"(default: {DEFAULT_MAX_FAILED_PCT:g})"
        ),
    )
    parser.add_argument(
        "--max-category-failed-pct",
        type=float,
        default=DEFAULT_MAX_CATEGORY_FAILED_PCT,
        help=(
            "fail if one category exceeds this failure percentage, with at "
            f"least 2 failures (default: {DEFAULT_MAX_CATEGORY_FAILED_PCT:g})"
        ),
    )
    args = parser.parse_args()
    if args.max_age_hours <= 0:
        parser.error("--max-age-hours must be positive")
    if not 0 <= args.max_failed_pct <= 100:
        parser.error("--max-failed-pct must be between 0 and 100")
    if not 0 <= args.max_category_failed_pct <= 100:
        parser.error("--max-category-failed-pct must be between 0 and 100")
    return args


if __name__ == "__main__":
    args = parse_args()
    sys.exit(
        main(
            args.max_age_hours,
            args.max_failed_pct,
            args.max_category_failed_pct,
        )
    )
