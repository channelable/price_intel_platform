from datetime import UTC, datetime

from price_intel.freshness import Freshness


def _freshness(**overrides) -> Freshness:
    values = {
        "active": 100,
        "stale": 0,
        "failed": 0,
        "with_price": 99,
        "unavailable": 1,
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


def test_failures_within_budget_are_tolerated():
    freshness = _freshness(failed=5, with_price=94)
    assert freshness.failure_budget_ok is True
    assert freshness.problems() == []


def test_failures_above_budget_are_reported():
    problems = _freshness(failed=6, with_price=93).problems()
    assert problems == [
        "6/100 active product(s) blocked or parse_failed, above 5% budget"
    ]


def test_category_failure_cluster_fails_even_when_overall_budget_is_ok():
    problems = _freshness(
        failed=3,
        with_price=96,
        category_active={"smartphones": 80, "tv": 20},
        category_failed={"tv": 3},
    ).problems()
    assert problems == ["tv: 3/20 blocked or parse_failed, above 10% category budget"]


def test_single_category_failure_is_tolerated():
    freshness = _freshness(
        failed=1,
        with_price=98,
        category_active={"smartphones": 99, "tv": 1},
        category_failed={"tv": 1},
    )
    assert freshness.problems() == []


def test_category_failures_at_threshold_are_tolerated():
    freshness = _freshness(
        failed=2,
        with_price=97,
        category_active={"smartphones": 80, "tv": 20},
        category_failed={"tv": 2},
    )
    assert freshness.problems() == []


def test_unavailable_is_not_a_failure():
    freshness = _freshness(unavailable=10, with_price=89)
    assert freshness.problems() == []


def test_no_active_products_is_a_failure():
    problems = _freshness(active=0, with_price=0, unavailable=0).problems()
    assert "no active products" in problems


def test_no_current_price_is_a_failure():
    problems = _freshness(with_price=0, unavailable=0).problems()
    assert "no active product has a current price" in problems
