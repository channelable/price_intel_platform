from __future__ import annotations

import csv
from datetime import UTC
from decimal import Decimal
from pathlib import Path

import pytest

from price_intel.datasets.kaggle import (
    iter_price_rows,
    parse_product_url,
    product_url,
    read_listings,
    sample_product_ids,
)

COLUMNS = [
    "product_id",
    "platform",
    "title",
    "category",
    "timestamp",
    "price",
    "original_price",
]


def write_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    rows = [
        {
            "product_id": "P1",
            "platform": "amazon",
            "title": "Alpha",
            "category": "Electronics",
            "timestamp": "2024-01-01T00:00:00",
            "price": "100.00",
            "original_price": "120.00",
        },
        {
            "product_id": "P1",
            "platform": "amazon",
            "title": "Alpha",
            "category": "Electronics",
            "timestamp": "2024-01-02T00:00:00",
            "price": "95.00",
            "original_price": "120.00",
        },
        {
            "product_id": "P1",
            "platform": "flipkart",
            "title": "Alpha",
            "category": "Electronics",
            "timestamp": "2024-01-01T00:00:00",
            "price": "90.00",
            "original_price": "110.00",
        },
        {
            "product_id": "P2",
            "platform": "amazon",
            "title": "Beta",
            "category": "Electronics",
            "timestamp": "2024-01-01T00:00:00",
            "price": "200.00",
            "original_price": "250.00",
        },
        {
            "product_id": "P3",
            "platform": "amazon",
            "title": "Gamma",
            "category": "Fashion",
            "timestamp": "2024-01-01T00:00:00",
            "price": "50.00",
            "original_price": "60.00",
        },
        {
            "product_id": "P4",
            "platform": "amazon",
            "title": "Delta",
            "category": "Fashion",
            "timestamp": "2024-01-01T00:00:00",
            "price": "60.00",
            "original_price": "70.00",
        },
        {
            "product_id": "P5",
            "platform": "amazon",
            "title": "Epsilon",
            "category": "Books",
            "timestamp": "2024-01-01T00:00:00",
            "price": "10.00",
            "original_price": "12.00",
        },
        {
            "product_id": "P6",
            "platform": "amazon",
            "title": "Zeta",
            "category": "Books",
            "timestamp": "2024-01-01T00:00:00",
            "price": "11.00",
            "original_price": "13.00",
        },
    ]
    return write_csv(tmp_path / "prices.csv", rows)


def test_product_url_round_trip() -> None:
    url = product_url("flipkart", "P0000001")
    assert url == "kaggle://flipkart/P0000001"
    assert parse_product_url(url) == ("flipkart", "P0000001")


def test_parse_product_url_rejects_non_kaggle_url() -> None:
    with pytest.raises(ValueError):
        parse_product_url("https://www.flipkart.com/item")


def test_read_listings_collects_metadata(sample_csv: Path) -> None:
    listings = read_listings(sample_csv)

    assert len(listings) == 7
    assert len({item.external_id for item in listings.values()}) == 6
    amazon_p1 = listings[("amazon", "P1")]
    assert amazon_p1.row_count == 2
    assert amazon_p1.first_seen.day == 1
    assert amazon_p1.last_seen.day == 2
    assert amazon_p1.first_seen.tzinfo is UTC


def test_sample_is_stratified_and_reproducible(sample_csv: Path) -> None:
    listings = read_listings(sample_csv)

    first = sample_product_ids(listings, max_products=3, seed=7)
    second = sample_product_ids(listings, max_products=3, seed=7)

    assert first == second
    selected_categories = {
        item.category for item in listings.values() if item.external_id in first
    }
    assert selected_categories == {"Electronics", "Fashion", "Books"}


def test_sample_rejects_too_few_products(sample_csv: Path) -> None:
    listings = read_listings(sample_csv)

    with pytest.raises(ValueError, match="smaller than the 3 categories"):
        sample_product_ids(listings, max_products=2, seed=7)


def test_iter_price_rows_filters_and_parses(sample_csv: Path) -> None:
    rows = list(iter_price_rows(sample_csv, {"P1"}))

    assert len(rows) == 3
    assert rows[0].price == Decimal("100.00")
    assert rows[0].mrp == Decimal("120.00")
    assert rows[0].scraped_at.tzinfo is UTC
    assert {row.platform for row in rows} == {"amazon", "flipkart"}


def test_missing_price_raises(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "bad.csv",
        [
            {
                "product_id": "P1",
                "platform": "amazon",
                "title": "Alpha",
                "category": "Electronics",
                "timestamp": "2024-01-01T00:00:00",
                "price": "",
                "original_price": "120.00",
            }
        ],
    )

    with pytest.raises(ValueError, match="missing required price"):
        list(iter_price_rows(path, {"P1"}))
