"""Sync the versioned product catalog into the database.

    python scripts/seed_products.py [path/to/products.csv]

Additive and idempotent. Missing products are inserted as active; existing
products only have their category updated, so titles, prices, statuses, and
manual deactivations are preserved.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select

from price_intel.db.base import session_scope
from price_intel.db.models import Product, Source
from price_intel.scrapers.runner import get_adapter

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "seeds" / "products.csv"
CATEGORIES = frozenset({"smartphones", "laptops", "audio", "wearables", "tv"})


class SeedError(ValueError):
    """A row in the catalog file is invalid."""


@dataclass(frozen=True, slots=True)
class SeedRow:
    source: Source
    category: str
    url: str


def load_rows(path: Path) -> list[SeedRow]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"source", "category", "url"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SeedError(f"{path} is missing columns: {', '.join(sorted(missing))}")

        rows: list[SeedRow] = []
        seen: dict[str, int] = {}
        for line_no, raw in enumerate(reader, start=2):
            source_text = (raw.get("source") or "").strip().lower()
            category = (raw.get("category") or "").strip().lower()
            url = (raw.get("url") or "").strip()

            if not source_text or not category or not url:
                raise SeedError(f"line {line_no}: source, category, and url are required")
            try:
                source = Source(source_text)
            except ValueError as exc:
                raise SeedError(f"line {line_no}: unknown source {source_text!r}") from exc
            if category not in CATEGORIES:
                raise SeedError(
                    f"line {line_no}: category {category!r} must be one of {sorted(CATEGORIES)}"
                )
            parts = urlsplit(url)
            if parts.scheme not in {"http", "https"} or not parts.netloc:
                raise SeedError(f"line {line_no}: not an absolute http(s) URL: {url!r}")

            try:
                adapter = get_adapter(source)
            except ValueError as exc:
                raise SeedError(f"line {line_no}: {exc}") from exc
            canonical = adapter.canonical_url(url)
            if canonical in seen:
                raise SeedError(
                    f"line {line_no}: duplicate of line {seen[canonical]} after canonicalization"
                )
            seen[canonical] = line_no
            rows.append(SeedRow(source=source, category=category, url=canonical))

    if not rows:
        raise SeedError(f"{path} has no product rows")
    return rows


def sync(rows: list[SeedRow]) -> tuple[int, int, int]:
    added = updated = unchanged = 0
    with session_scope() as session:
        for row in rows:
            product = session.execute(
                select(Product).where(Product.url == row.url)
            ).scalar_one_or_none()
            if product is None:
                session.add(
                    Product(
                        url=row.url,
                        source=row.source,
                        category=row.category,
                        is_active=True,
                    )
                )
                added += 1
            elif product.category != row.category:
                product.category = row.category
                updated += 1
            else:
                unchanged += 1
    return added, updated, unchanged


def main(path: Path) -> int:
    try:
        rows = load_rows(path)
    except (OSError, SeedError) as exc:
        print(f"seed error: {exc}", file=sys.stderr)
        return 1

    added, updated, unchanged = sync(rows)
    print(
        f"seed: {len(rows)} rows, {added} added, {updated} updated, {unchanged} unchanged",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV
    sys.exit(main(target))
