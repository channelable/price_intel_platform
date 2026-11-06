"""Flipkart adapter: fetch a product page and parse its embedded data.

Two independent sources are used:
  * JSON-LD (``@type: Product``) for title, SKU, selling price, stock status.
  * The page's ``__INITIAL_STATE__`` -> ``"ppd"`` block for the listed MRP,
    which JSON-LD does not expose.

Both are read from the HTML the server returns; no JavaScript execution needed.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from price_intel.scrapers.base import BlockedError, ParseError, ScrapedProduct

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}

_JSON_LD_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL
)
_PPD_RE = re.compile(r'"ppd":\{([^}]*)\}')
_MRP_RE = re.compile(r'"mrp":(\d+)')

_session = requests.Session()
_session.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=2,
            backoff_factor=3,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
    ),
)


def canonical_url(url: str) -> str:
    """Drop tracking params but keep Flipkart's product id (pid).

    Storing the canonical form keeps the unique ``products.url`` stable even if
    the link is copied from a search result with a different tracking suffix.
    """
    parts = urlsplit(url)
    pid = parse_qs(parts.query).get("pid", [None])[0]
    base = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return f"{base}?pid={pid}" if pid else base


def fetch_html(url: str, *, timeout: float = 30.0) -> str:
    response = _session.get(url, headers=HEADERS, timeout=timeout)
    if response.status_code in (403, 429):
        raise BlockedError(f"HTTP {response.status_code}")
    response.raise_for_status()
    return response.text


def parse_product(html: str) -> ScrapedProduct:
    product = _find_product_json_ld(html)
    if product is None:
        raise ParseError("no Product JSON-LD block found")

    offers = product.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    if not isinstance(offers, dict):
        raise ParseError("JSON-LD has no offers object")

    price = _to_decimal(offers.get("price"))
    if price is None or price <= 0:
        raise ParseError(f"unusable price: {offers.get('price')!r}")

    name = product.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ParseError("JSON-LD has no product name")

    return ScrapedProduct(
        title=name.strip(),
        price=price,
        mrp=_extract_mrp(html),
        currency=offers.get("priceCurrency") or "INR",
        sku=product.get("sku"),
        available=str(offers.get("availability", "")).endswith("InStock"),
    )


def _find_product_json_ld(html: str) -> dict | None:
    for block in _JSON_LD_RE.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item
    return None


def _extract_mrp(html: str) -> Decimal | None:
    match = _PPD_RE.search(html)
    if match is None:
        return None
    mrp = _MRP_RE.search(match.group(1))
    return _to_decimal(mrp.group(1)) if mrp else None


def _to_decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None
