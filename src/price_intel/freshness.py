"""Freshness checks for scraped price data.

A green scrape job should mean "fresh, usable data", not just "the cron
fired". The CLI wrapper is scripts/check_freshness.py; the API can reuse
get_freshness() for its /health endpoint.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from price_intel.db.models import Product, ScrapeStatus

DEFAULT_MAX_AGE_HOURS = 8.0
DEFAULT_MAX_FAILED_PCT = 5.0
DEFAULT_MAX_CATEGORY_FAILED_PCT = 10.0
MIN_CATEGORY_FAILURES = 2


@dataclass(frozen=True, slots=True)
class Freshness:
    active: int
    stale: int
    failed: int
    with_price: int
    unavailable: int
    last_attempt: datetime | None
    max_age_hours: float
    max_failed_pct: float = DEFAULT_MAX_FAILED_PCT
    max_category_failed_pct: float = DEFAULT_MAX_CATEGORY_FAILED_PCT
    category_active: Mapping[str, int] = field(default_factory=dict)
    category_failed: Mapping[str, int] = field(default_factory=dict)

    @property
    def failure_budget_ok(self) -> bool:
        if self.active == 0:
            return True
        return self.failed / self.active <= self.max_failed_pct / 100

    def problems(self) -> list[str]:
        issues: list[str] = []
        if self.active == 0:
            issues.append("no active products")
        if self.stale:
            issues.append(
                f"{self.stale} active product(s) older than {self.max_age_hours:g}h"
            )
        if self.failed and not self.failure_budget_ok:
            issues.append(
                f"{self.failed}/{self.active} active product(s) blocked or "
                f"parse_failed, above {self.max_failed_pct:g}% budget"
            )
        for category in sorted(self.category_failed):
            failed = self.category_failed[category]
            active = self.category_active.get(category, 0)
            if failed < MIN_CATEGORY_FAILURES or active == 0:
                continue
            if failed / active > self.max_category_failed_pct / 100:
                issues.append(
                    f"{category}: {failed}/{active} blocked or parse_failed, "
                    f"above {self.max_category_failed_pct:g}% category budget"
                )
        if self.with_price == 0:
            issues.append("no active product has a current price")
        return issues

    @property
    def ok(self) -> bool:
        return not self.problems()


def get_freshness(
    session: Session,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    max_failed_pct: float = DEFAULT_MAX_FAILED_PCT,
    max_category_failed_pct: float = DEFAULT_MAX_CATEGORY_FAILED_PCT,
) -> Freshness:
    """Summarize how recently active products were attempted and what happened."""
    if max_age_hours <= 0:
        raise ValueError("max_age_hours must be positive")
    if not 0 <= max_failed_pct <= 100:
        raise ValueError("max_failed_pct must be between 0 and 100")
    if not 0 <= max_category_failed_pct <= 100:
        raise ValueError("max_category_failed_pct must be between 0 and 100")

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
            func.count()
            .filter(Product.last_scrape_status == ScrapeStatus.UNAVAILABLE)
            .label("unavailable"),
            func.max(Product.last_scraped_at).label("last_attempt"),
        ).where(Product.is_active.is_(True))
    ).one()

    category_rows = session.execute(
        select(
            Product.category,
            func.count().label("active"),
            func.count()
            .filter(
                Product.last_scrape_status.in_(
                    [ScrapeStatus.BLOCKED, ScrapeStatus.PARSE_FAILED]
                )
            )
            .label("failed"),
        )
        .where(Product.is_active.is_(True))
        .group_by(Product.category)
    ).all()

    category_active = {
        (category_row.category or "uncategorized"): category_row.active
        for category_row in category_rows
    }
    category_failed = {
        (category_row.category or "uncategorized"): category_row.failed
        for category_row in category_rows
        if category_row.failed
    }

    return Freshness(
        active=row.active,
        stale=row.stale,
        failed=row.failed,
        with_price=row.with_price,
        unavailable=row.unavailable,
        last_attempt=row.last_attempt,
        max_age_hours=max_age_hours,
        max_failed_pct=max_failed_pct,
        max_category_failed_pct=max_category_failed_pct,
        category_active=category_active,
        category_failed=category_failed,
    )
