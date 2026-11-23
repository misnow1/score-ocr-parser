"""Features come out in score order (page, then bar, then x), through parse_score."""

from pathlib import Path

from score_parser import parse_score

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"


def order_of(name: str) -> list[str | None]:
    return [f.instrument for f in parse_score(FIXTURES / name).features]


def test_features_are_ordered_by_bar_not_by_staff_row():
    # the guitar sits on a lower staff than the alto and trombone but solos first
    assert order_of("finale_score_order.pdf") == ["Guitar", "Alto Sax", "Trombone", "Trumpet"]


def test_page_comes_before_bar():
    report = parse_score(FIXTURES / "finale_score_order.pdf")

    assert [f.page for f in report.features] == [1, 1, 1, 2]


def test_features_with_no_bar_are_ordered_by_page_and_x():
    report = parse_score(FIXTURES / "finale_unnumbered_order.pdf")

    assert [f.bar for f in report.features] == [None, None]
    assert [f.instrument for f in report.features] == ["Guitar", "Alto Sax"]  # x 250 before x 400


def test_flow_steps_follow_the_feature_order():
    report = parse_score(FIXTURES / "finale_score_order.pdf")

    assert [s.instrument for s in report.flow] == ["guitar", "alto sax", "trombone", "trumpet"]
