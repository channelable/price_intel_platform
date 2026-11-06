"""Scrape products once and print the outcome.

    python scripts/scrape_once.py <url> [<url> ...]
"""

import random
import sys
import time

from price_intel.db.base import session_scope
from price_intel.scrapers.runner import scrape_url

DELAY_RANGE_SECONDS = (2.5, 4.5)


def main(urls: list[str]) -> None:
    for index, url in enumerate(urls):
        with session_scope() as session:
            result = scrape_url(session, url)
        print(
            f"{result.status.value:14} price={result.price} mrp={result.mrp} "
            f"title={result.title!r}"
            + (f" detail={result.detail!r}" if result.detail else ""),
            flush=True,
        )
        if index < len(urls) - 1:
            time.sleep(random.uniform(*DELAY_RANGE_SECONDS))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python scripts/scrape_once.py <url> [<url> ...]")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main(sys.argv[1:])
