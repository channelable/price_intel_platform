"""Load a sampled subset of the Kaggle price-history dataset.

The dataset is a development stand-in, not production data. Kaggle rows get a
``kaggle://`` URL and stay inactive so the live scraper never tries to fetch
them. The loader is idempotent: re-running the same sample does not duplicate
products or price points.
"""

from __future__ import annotations

import csv
import random
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from price_intel.db.base import session_scope
from price_intel.db.models import PriceHistory, Product, ScrapeStatus, Source

KAGGLE_URL_PREFIX = "kaggle://"
DEFAULT_CSV = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "raw"
    / "kaggle"
    / "data"
    / "splits"
    / "ecommerce_test.csv"
)


@dataclass(frozen=True, slots=True)
class ListingMeta:
    """One product listed on one platform."""

    platform: str
    external_id: str
    title: str
    category: str
    first_seen: datetime
    last_seen: datetime
    row_count: int


@dataclass(frozen=True, slots=True)
class PriceRow:
    platform: str
    external_id: str
    scraped_at: datetime
    price: Decimal
    mrp: Decimal | None


@dataclass(slots=True)
class _ListingAccumulator:
    platform: str
    external_id: str
    title: str
    category: str
    first_seen: datetime
    last_seen: datetime
    row_count: int


@dataclass(frozen=True, slots=True)
class LoadStats:
    products: int
    listings: int
    rows_expected: int
    rows_inserted: int | None = None

    @property
    def rows_skipped(self) -> int | None:
        if self.rows_inserted is None:
            return None
        return self.rows_expected - self.rows_inserted


def product_url(platform: str, external_id: str) -> str:
    """Stable synthetic URL used to identify a Kaggle listing."""
    return f"{KAGGLE_URL_PREFIX}{platform}/{external_id}"


def parse_product_url(url: str) -> tuple[str, str]:
    """Return ``(platform, external_id)`` for a Kaggle product URL."""
    parts = urlsplit(url)
    external_id = parts.path.strip("/")
    if parts.scheme != "kaggle" or not parts.netloc or not external_id:
        raise ValueError(f"not a Kaggle product URL: {url!r}")
    return parts.netloc, external_id


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip())
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_decimal(value: str) -> Decimal:
    text = value.strip()
    if not text:
        raise ValueError("missing required price")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal value {value!r}") from exc


def _parse_optional_decimal(value: str) -> Decimal | None:
    return _parse_decimal(value) if value.strip() else None


def read_listings(csv_path: Path) -> dict[tuple[str, str], ListingMeta]:
    """First pass: collect one metadata record per platform/product pair."""
    listings: dict[tuple[str, str], _ListingAccumulator] = {}
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"product_id", "platform", "title", "category", "timestamp"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{csv_path} is missing columns: {', '.join(sorted(missing))}")

        for row in reader:
            key = (row["platform"].strip().lower(), row["product_id"].strip())
            timestamp = _parse_timestamp(row["timestamp"])
            existing = listings.get(key)
            if existing is None:
                listings[key] = _ListingAccumulator(
                    platform=key[0],
                    external_id=key[1],
                    title=row["title"].strip(),
                    category=row["category"].strip(),
                    first_seen=timestamp,
                    last_seen=timestamp,
                    row_count=1,
                )
                continue

            existing.first_seen = min(existing.first_seen, timestamp)
            existing.last_seen = max(existing.last_seen, timestamp)
            existing.row_count += 1

    return {
        key: ListingMeta(
            platform=item.platform,
            external_id=item.external_id,
            title=item.title,
            category=item.category,
            first_seen=item.first_seen,
            last_seen=item.last_seen,
            row_count=item.row_count,
        )
        for key, item in listings.items()
    }


def sample_product_ids(
    listings: dict[tuple[str, str], ListingMeta],
    max_products: int,
    seed: int,
) -> set[str]:
    """Stratified, reproducible sample of Kaggle product IDs by category."""
    by_category: dict[str, set[str]] = defaultdict(set)
    for listing in listings.values():
        by_category[listing.category].add(listing.external_id)

    if not by_category:
        raise ValueError("CSV has no product rows")
    if max_products < len(by_category):
        raise ValueError(
            f"max_products={max_products} is smaller than the {len(by_category)} categories"
        )

    rng = random.Random(seed)
    selected: set[str] = set()
    categories = sorted(by_category)
    base, remainder = divmod(max_products, len(categories))
    for index, category in enumerate(categories):
        quota = base + (1 if index < remainder else 0)
        candidates = sorted(by_category[category])
        selected.update(candidates if quota >= len(candidates) else rng.sample(candidates, quota))
    return selected


def iter_price_rows(csv_path: Path, product_ids: set[str]) -> Iterator[PriceRow]:
    """Second pass: parse only the selected products' price points."""
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"product_id", "platform", "timestamp", "price"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{csv_path} is missing columns: {', '.join(sorted(missing))}")
        for row in reader:
            external_id = row["product_id"].strip()
            if external_id not in product_ids:
                continue
            yield PriceRow(
                platform=row["platform"].strip().lower(),
                external_id=external_id,
                scraped_at=_parse_timestamp(row["timestamp"]),
                price=_parse_decimal(row["price"]),
                mrp=_parse_optional_decimal(row.get("original_price", "")),
            )


def upsert_products(
    session: Session,
    listings: dict[tuple[str, str], ListingMeta],
    product_ids: set[str],
) -> dict[str, int]:
    """Insert or refresh the selected Kaggle listings. Returns URL -> product ID."""
    selected = [item for item in listings.values() if item.external_id in product_ids]
    urls = [product_url(item.platform, item.external_id) for item in selected]
    existing = {
        product.url: product
        for product in session.scalars(select(Product).where(Product.url.in_(urls))).all()
    }

    for item in selected:
        url = product_url(item.platform, item.external_id)
        product = existing.get(url)
        if product is None:
            product = Product(url=url, source=Source.OTHER)
            session.add(product)
            existing[url] = product
        product.source = Source.OTHER
        product.title = item.title
        product.category = item.category
        product.currency = "USD"
        # Never let the live scraper pick up a synthetic Kaggle URL.
        product.is_active = False
        product.last_scraped_at = item.last_seen
        product.last_scrape_status = ScrapeStatus.OK

    session.flush()
    return {url: product.id for url, product in existing.items()}


def insert_price_rows(
    session: Session,
    product_ids: dict[str, int],
    rows: Iterable[PriceRow],
    *,
    batch_size: int = 1_000,
) -> int:
    """Insert price points, skipping points that already exist."""
    inserted = 0
    batch: list[dict[str, object]] = []
    for row in rows:
        batch.append(
            {
                "product_id": product_ids[product_url(row.platform, row.external_id)],
                "price": row.price,
                "mrp": row.mrp,
                "currency": "USD",
                "scraped_at": row.scraped_at,
            }
        )
        if len(batch) >= batch_size:
            inserted += _insert_batch(session, batch)
            batch.clear()
    if batch:
        inserted += _insert_batch(session, batch)
    return inserted


def _insert_batch(session: Session, batch: list[dict[str, object]]) -> int:
    statement = (
        insert(PriceHistory)
        .values(batch)
        .on_conflict_do_nothing(index_elements=["product_id", "scraped_at"])
        .returning(PriceHistory.id)
    )
    result = session.execute(statement)
    # rowcount is unreliable for multi-row INSERT ... ON CONFLICT, so count
    # the returned IDs instead.
    return len(result.scalars().all())


def load_sample(
    csv_path: Path,
    *,
    max_products: int = 200,
    seed: int = 42,
    dry_run: bool = False,
) -> LoadStats:
    """Read the CSV, sample products, and optionally write them to Postgres."""
    listings = read_listings(csv_path)
    product_ids = sample_product_ids(listings, max_products, seed)
    selected = [item for item in listings.values() if item.external_id in product_ids]
    rows_expected = sum(item.row_count for item in selected)

    if dry_run:
        return LoadStats(
            products=len(product_ids),
            listings=len(selected),
            rows_expected=rows_expected,
        )

    with session_scope() as session:
        product_ids_by_url = upsert_products(session, listings, product_ids)
        rows_inserted = insert_price_rows(
            session,
            product_ids_by_url,
            iter_price_rows(csv_path, product_ids),
        )

    return LoadStats(
        products=len(product_ids),
        listings=len(selected),
        rows_expected=rows_expected,
        rows_inserted=rows_inserted,
    )
