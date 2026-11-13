"""One-off curation tool: collect candidate Flipkart product URLs.

    python scripts/collect_seed_urls.py [--per-category 20] [--out seeds/products.csv]

Fetches one public search page per category, extracts canonical product links,
and merges them into the seed CSV. It does not touch the database and is not
part of the scheduled pipeline. Review the output before running
seed_products.py.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
import time
from pathlib import Path

import requests

from price_intel.scrapers.base import BlockedError
from price_intel.scrapers.discovery import extract_product_links, product_slug
from price_intel.scrapers.flipkart import fetch_html

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "seeds" / "products.csv"
DELAY_RANGE_SECONDS = (2.5, 5.5)
CATEGORY_ORDER = ["smartphones", "laptops", "audio", "wearables", "tv"]
SEARCH_URLS = {
    "smartphones": "https://www.flipkart.com/search?q=smartphones",
    "laptops": "https://www.flipkart.com/search?q=laptops",
    "audio": "https://www.flipkart.com/search?q=bluetooth+earphones",
    "wearables": "https://www.flipkart.com/search?q=smartwatches",
    "tv": "https://www.flipkart.com/search?q=televisions",
}


def load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [
            {
                "category": (row.get("category") or "").strip(),
                "source": (row.get("source") or "flipkart").strip(),
                "url": (row.get("url") or "").strip(),
            }
            for row in csv.DictReader(handle)
            if (row.get("url") or "").strip()
        ]


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["category", "source", "url"])
        writer.writeheader()
        writer.writerows(rows)


def collect(per_category: int) -> dict[str, list[str]]:
    collected: dict[str, list[str]] = {}
    categories = list(SEARCH_URLS.items())
    for index, (category, search_url) in enumerate(categories):
        try:
            html = fetch_html(search_url)
            links = extract_product_links(html)[:per_category]
        except (BlockedError, requests.RequestException) as exc:
            print(f"{category}: fetch failed: {exc}", file=sys.stderr, flush=True)
            links = []
        collected[category] = links
        print(f"{category}: {len(links)} candidate(s) from {search_url}", flush=True)
        if index < len(categories) - 1:
            time.sleep(random.uniform(*DELAY_RANGE_SECONDS))
    return collected


def merge(
    existing: list[dict[str, str]], collected: dict[str, list[str]]
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in existing:
        key = product_slug(row["url"]) or row["url"]
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    for category in CATEGORY_ORDER:
        for url in collected.get(category, []):
            key = product_slug(url) or url
            if key in seen:
                continue
            seen.add(key)
            rows.append({"category": category, "source": "flipkart", "url": url})
    order = {category: index for index, category in enumerate(CATEGORY_ORDER)}
    rows.sort(key=lambda row: (order.get(row["category"], len(order)), row["url"]))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--per-category",
        type=int,
        default=20,
        help="maximum candidates to keep per category (default: 20)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_CSV,
        help=f"seed CSV to merge into (default: {DEFAULT_CSV})",
    )
    args = parser.parse_args()
    if args.per_category <= 0:
        parser.error("--per-category must be positive")

    existing = load_rows(args.out)
    collected = collect(args.per_category)
    merged = merge(existing, collected)
    write_rows(args.out, merged)

    print(f"\nwrote {len(merged)} rows to {args.out}", flush=True)
    for category in CATEGORY_ORDER:
        count = sum(1 for row in merged if row["category"] == category)
        print(f"  {category:12} {count}", flush=True)

    short = [
        category
        for category in CATEGORY_ORDER
        if len(collected.get(category, [])) < args.per_category
    ]
    if short:
        print(
            f"\nwarning: fewer than {args.per_category} candidates for: "
            f"{', '.join(short)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
