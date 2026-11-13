"""One-off catalog discovery helpers.

Used by scripts/collect_seed_urls.py to pull candidate product URLs from
Flipkart search pages. Not used by the scheduled scraper.
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qs, urljoin, urlsplit

from price_intel.scrapers.flipkart import canonical_url

_PRODUCT_LINK_RE = re.compile(r'href="([^"]*?/p/[^"]+)"')


def extract_product_links(
    html: str, base_url: str = "https://www.flipkart.com"
) -> list[str]:
    """Return canonical product URLs from a search page, one per product slug."""
    links: list[str] = []
    seen_slugs: set[str] = set()
    for raw in _PRODUCT_LINK_RE.findall(html):
        absolute = urljoin(base_url, unescape(raw))
        parts = urlsplit(absolute)
        if not _is_flipkart_host(parts.netloc):
            continue
        if not parse_qs(parts.query).get("pid"):
            continue
        slug = product_slug(absolute)
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        links.append(canonical_url(absolute))
    return links


def product_slug(url: str) -> str:
    """Return the product path segment before /p/, which identifies the SKU."""
    path = urlsplit(url).path
    before_p, _, _ = path.partition("/p/")
    return before_p.strip("/")


def _is_flipkart_host(netloc: str) -> bool:
    host = netloc.lower().split(":", 1)[0]
    return host == "flipkart.com" or host.endswith(".flipkart.com")
