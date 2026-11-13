from decimal import Decimal
from pathlib import Path

import pytest

from price_intel.scrapers.base import ParseError
from price_intel.scrapers.flipkart import canonical_url, parse_product

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "flipkart"

CATEGORY_FIXTURES = [
    pytest.param(
        "iphone17-black-256gb.html",
        "Apple iPhone 17 (Black, 256 GB)",
        Decimal("97300"),
        Decimal("99900"),
        "MOBHQV9YCUG4ZQZK",
        id="smartphones",
    ),
    pytest.param(
        "laptops-asus-tuf-a15.html",
        (
            "ASUS TUF Gaming A15 (2026) AMD Ryzen 7 170 - (16 GB/512 GB SSD/"
            "Windows 11 Home/4 GB Graphics/NVIDIA GeForce RTX 3050/144 Hz) "
            "FA506NCQ-IN080W Gaming Laptop"
        ),
        Decimal("92990"),
        Decimal("141990"),
        "COMHZEEDEP4E92NJ",
        id="laptops",
    ),
    pytest.param(
        "audio-boat-airdopes-131.html",
        "boAt Airdopes 131 Gen 2, 13mm Drivers, 70H Battery, ENx, App Bluetooth",
        Decimal("1222"),
        Decimal("2990"),
        "ACCHDYCG92CUSJFT",
        id="audio",
    ),
    pytest.param(
        "wearables-noise-colorfit-icon-2.html",
        (
            "Noise Colorfit Icon 2 1.8'' Display with Bluetooth Calling, "
            "AI Voice Assistant Smartwatch"
        ),
        Decimal("1499"),
        Decimal("5999"),
        "SMWGEH7VGYMGCP3V",
        id="wearables",
    ),
    pytest.param(
        "tv-samsung-crystal-43.html",
        (
            "Samsung Crystal 4K Vision AI 108 cm (43 inch) Ultra HD (4K) LED "
            "Smart Tizen TV 2026 Edition with 30W Speakers 4K Upscaling HDR 10+ "
            "Football Mode Voice Assistance Remote Control PurColor Slim Look "
            "Samsung Knox Security 150+ Free Channels"
        ),
        Decimal("34000"),
        Decimal("49999"),
        "TVSHMHKP5GFWZFAZ",
        id="tv",
    ),
]


@pytest.mark.parametrize(
    "filename, expected_title, expected_price, expected_mrp, expected_sku",
    CATEGORY_FIXTURES,
)
def test_parses_supported_categories(
    filename: str,
    expected_title: str,
    expected_price: Decimal,
    expected_mrp: Decimal,
    expected_sku: str,
) -> None:
    parsed = parse_product((FIXTURE_DIR / filename).read_text(encoding="utf-8"))

    assert parsed.title == expected_title
    assert parsed.price == expected_price
    assert parsed.mrp == expected_mrp
    assert parsed.currency == "INR"
    assert parsed.sku == expected_sku
    assert parsed.available is True


def test_rejects_page_without_product_json_ld():
    with pytest.raises(ParseError):
        parse_product("<html><body>no structured data here</body></html>")


def test_canonical_url_drops_tracking_keeps_pid():
    messy = "https://www.flipkart.com/x/p/itm123?pid=ABC123&q=apple&otracker=search"
    assert canonical_url(messy) == "https://www.flipkart.com/x/p/itm123?pid=ABC123"
