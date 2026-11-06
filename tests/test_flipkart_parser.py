from decimal import Decimal
from pathlib import Path

import pytest

from price_intel.scrapers.base import ParseError
from price_intel.scrapers.flipkart import canonical_url, parse_product

FIXTURE = Path(__file__).parent / "fixtures" / "flipkart" / "iphone17-black-256gb.html"


def test_parses_price_mrp_and_metadata():
    parsed = parse_product(FIXTURE.read_text(encoding="utf-8"))

    assert parsed.title == "Apple iPhone 17 (Black, 256 GB)"
    assert parsed.price == Decimal("97300")
    assert parsed.mrp == Decimal("99900")
    assert parsed.currency == "INR"
    assert parsed.sku == "MOBHQV9YCUG4ZQZK"
    assert parsed.available is True


def test_rejects_page_without_product_json_ld():
    with pytest.raises(ParseError):
        parse_product("<html><body>no structured data here</body></html>")


def test_canonical_url_drops_tracking_keeps_pid():
    messy = "https://www.flipkart.com/x/p/itm123?pid=ABC123&q=apple&otracker=search"
    assert canonical_url(messy) == "https://www.flipkart.com/x/p/itm123?pid=ABC123"
