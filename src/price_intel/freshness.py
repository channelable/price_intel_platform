"""Freshness checks for scraped price data.

A green scrape job should mean "fresh, usable data", not just "the cron
fired". The CLI wrapper is scripts/check_freshness.py; the API can reuse
get_freshness() for its /health endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from price_intel.db.models import Product, ScrapeStatus

DEFAULT_MAX_AGE_HOURS = 8.0


@dataclass(frozen=True, slots=True)
class Freshness:
    active: int
    stale: int
    failed: int
    with_price: int
    last_attempt: datetime | None
    max_age_hours: float

    def problems(self) -> list[str]:
        issues: list[str] = []
        if self.active == 0:
            issues.append("no active products")
        if self.stale:
            issues.append(
                f"{self.stale} active product(s) older than {self.max_age_hours:g}h"
            )
        if self.failed:
            issues.append(f"{self.failed} active product(s) blocked or parse_failed")
        if self.with_price == 0:
            issues.append("no active product has a current price")
        return issues

    @property
    def ok(self) -> bool:
        return not self.problems()


def get_freshness(
    session: Session, max_age_hours: float = DEFAULT_MAX_AGE_HOURS
) -> Freshness:
    """Summarize how recently active products were attempted and what happened."""
    cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
    row = session.execute(
        select(
            func.count().label("active"),
            func.count()
            .filter(
                Product.last_scraped_at.is_(None) | (Product.last_scraped_at < cutoff)
            )
            .label("stale"),
            func.count()
            .filter(
                Product.last_scrape_status.in_(
                    [ScrapeStatus.BLOCKED, ScrapeStatus.PARSE_FAILED]
                )
            )
            .label("failed"),
            func.count()
            .filter(
                Product.last_scrape_status.in_(
                    [ScrapeStatus.OK, ScrapeStatus.UNCHANGED]
                )
            )
            .label("with_price"),
            func.max(Product.last_scraped_at).label("last_attempt"),
        ).where(Product.is_active.is_(True))
    ).one()
    return Freshness(
        active=row.active,
        stale=row.stale,
        failed=row.failed,
        with_price=row.with_price,
        last_attempt=row.last_attempt,
        max_age_hours=max_age_hours,
    )
