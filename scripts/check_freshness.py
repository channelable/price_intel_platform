"""Fail if the latest scrape did not produce fresh, usable data.

    python scripts/check_freshness.py [--max-age-hours 1]

Run immediately after scrape_all.py. Exits 1 if any active product is stale,
blocked, or parse_failed, or if no active product has a current price.
"""

from __future__ import annotations

import argparse
import sys

from price_intel.db.base import session_scope
from price_intel.freshness import DEFAULT_MAX_AGE_HOURS, get_freshness


def main(max_age_hours: float) -> int:
    with session_scope() as session:
        freshness = get_freshness(session, max_age_hours)

    problems = freshness.problems()
    last_attempt = (
        freshness.last_attempt.isoformat() if freshness.last_attempt else "never"
    )
    result = "OK" if not problems else "FAIL: " + "; ".join(problems)
    print(
        f"freshness: active={freshness.active} stale={freshness.stale} "
        f"failed={freshness.failed} with_price={freshness.with_price} "
        f"last_attempt={last_attempt} max_age={max_age_hours:g}h -> {result}",
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
    args = parser.parse_args()
    if args.max_age_hours <= 0:
        parser.error("--max-age-hours must be positive")
    return args


if __name__ == "__main__":
    sys.exit(main(parse_args().max_age_hours))
