"""Turn a product URL into rows: upsert the product, compare, store the price."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import requests
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from price_intel.db.models import PriceHistory, Product, ScrapeStatus, Source
from price_intel.scrapers import flipkart
from price_intel.scrapers.base import BlockedError, ParseError

# One entry per host adapter. Amazon will be added here when built.
_ADAPTERS = {Source.FLIPKART: flipkart}


@dataclass(slots=True)
class ScrapeResult:
    url: str
    status: ScrapeStatus
    price: Decimal | None = None
    mrp: Decimal | None = None
    title: str | None = None
    detail: str | None = None


def upsert_product(session: Session, url: str, source: Source) -> Product:
    product = session.execute(select(Product).where(Product.url == url)).scalar_one_or_none()
    if product is None:
        product = Product(url=url, source=source)
        session.add(product)
        session.flush()
    return product


def scrape_url(session: Session, url: str, source: Source = Source.FLIPKART) -> ScrapeResult:
    adapter = _ADAPTERS.get(source)
    if adapter is None:
        raise ValueError(f"no adapter for source {source!r}")

    canonical = adapter.canonical_url(url)
    product = upsert_product(session, canonical, source)
    attempted_at = datetime.now(UTC)

    try:
        parsed = adapter.parse_product(adapter.fetch_html(canonical))
    except (BlockedError, requests.RequestException) as exc:
        return _record_failure(
            session, product, canonical, ScrapeStatus.BLOCKED, attempted_at, str(exc)
        )
    except ParseError as exc:
        return _record_failure(
            session, product, canonical, ScrapeStatus.PARSE_FAILED, attempted_at, str(exc)
        )

    product.title = parsed.title
    product.last_scraped_at = attempted_at

    if not parsed.available:
        product.last_scrape_status = ScrapeStatus.UNAVAILABLE
        return ScrapeResult(canonical, ScrapeStatus.UNAVAILABLE, title=parsed.title)

    last_price = session.execute(
        select(PriceHistory.price)
        .where(PriceHistory.product_id == product.id)
        .order_by(PriceHistory.scraped_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    status = ScrapeStatus.UNCHANGED if last_price == parsed.price else ScrapeStatus.OK

    # on_conflict_do_nothing makes a retry of the same instant harmless.
    session.execute(
        pg_insert(PriceHistory)
        .values(
            product_id=product.id,
            price=parsed.price,
            mrp=parsed.mrp,
            currency=parsed.currency,
            scraped_at=attempted_at,
        )
        .on_conflict_do_nothing(constraint="uq_price_history_product_scraped")
    )
    product.last_scrape_status = status
    return ScrapeResult(
        canonical,
        status,
        price=parsed.price,
        mrp=parsed.mrp,
        title=parsed.title,
    )


def _record_failure(
    session: Session,
    product: Product,
    url: str,
    status: ScrapeStatus,
    attempted_at: datetime,
    detail: str,
) -> ScrapeResult:
    # A failed attempt updates the status but writes no price row, so
    # price_history only ever contains real observations.
    product.last_scraped_at = attempted_at
    product.last_scrape_status = status
    return ScrapeResult(url, status, detail=detail)
