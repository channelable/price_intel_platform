from datetime import UTC, datetime

from price_intel.freshness import Freshness


def _freshness(**overrides) -> Freshness:
    values = {
        "active": 3,
        "stale": 0,
        "failed": 0,
        "with_price": 2,
        "last_attempt": datetime.now(UTC),
        "max_age_hours": 1.0,
    }
    values.update(overrides)
    return Freshness(**values)


def test_healthy_snapshot_has_no_problems():
    freshness = _freshness()
    assert freshness.problems() == []
    assert freshness.ok is True


def test_stale_products_are_reported():
    problems = _freshness(stale=2).problems()
    assert problems == ["2 active product(s) older than 1h"]


def test_failed_products_are_reported():
    problems = _freshness(failed=1).problems()
    assert problems == ["1 active product(s) blocked or parse_failed"]


def test_no_active_products_is_a_failure():
    problems = _freshness(active=0, with_price=0).problems()
    assert "no active products" in problems


def test_no_current_price_is_a_failure():
    problems = _freshness(with_price=0).problems()
    assert "no active product has a current price" in problems
