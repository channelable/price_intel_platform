"""Scrape every active product once. Intended to be run by the scheduler."""

from __future__ import annotations

import logging
import random
import sys
import time
from pathlib import Path

from sqlalchemy import select

from price_intel.db.base import session_scope
from price_intel.db.models import Product, ScrapeStatus
from price_intel.scrapers.runner import scrape_url

DELAY_RANGE_SECONDS = (2.5, 5.5)
LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "scrape.log"


def configure_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def main() -> int:
    with session_scope() as session:
        targets = session.execute(
            select(Product.id, Product.url, Product.source)
            .where(Product.is_active.is_(True))
            .order_by(Product.id)
        ).all()

    logging.info("run start: %d active products", len(targets))
    failures = 0

    for index, (product_id, url, source) in enumerate(targets):
        with session_scope() as session:
            result = scrape_url(session, url, source)
        logging.info(
            "product_id=%s status=%s price=%s mrp=%s",
            product_id,
            result.status.value,
            result.price,
            result.mrp,
        )
        if result.status in (ScrapeStatus.BLOCKED, ScrapeStatus.PARSE_FAILED):
            failures += 1
        if index < len(targets) - 1:
            time.sleep(random.uniform(*DELAY_RANGE_SECONDS))

    logging.info("run done: %d/%d failed", failures, len(targets))
    return 1 if failures else 0


if __name__ == "__main__":
    configure_logging()
    sys.exit(main())
