"""Shared types for scrapers."""

from dataclasses import dataclass
from decimal import Decimal


class ScrapeError(Exception):
    """Base class for scrape failures."""


class BlockedError(ScrapeError):
    """The site refused the request (403, 429, captcha)."""


class ParseError(ScrapeError):
    """The page was fetched but the expected data was not in it."""


@dataclass(frozen=True, slots=True)
class ScrapedProduct:
    title: str
    price: Decimal
    mrp: Decimal | None
    currency: str
    sku: str | None
    available: bool
