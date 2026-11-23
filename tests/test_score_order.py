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


def test_features_with_no_bar_are_ordered_by_page_then_system_then_x():
    report = parse_score(FIXTURES / "finale_unnumbered_order.pdf")

    assert [f.bar for f in report.features] == [None, None, None]
    # Guitar x250 and Alto x400 are on system 1; the Trumpet is on system 2 at x200,
    # left of the alto, but a later system never sorts before an earlier one
    assert [f.instrument for f in report.features] == ["Guitar", "Alto Sax", "Trumpet"]


def test_a_reminder_on_a_later_system_does_not_pull_a_feature_earlier():
    report = parse_score(FIXTURES / "finale_unnumbered_order.pdf")

    alto = next(f for f in report.features if f.instrument == "Alto Sax")
    assert len(alto.locations) == 1  # the reminder (x160 on system 2) merged, bar unknown
    assert [f.instrument for f in report.features][:2] == ["Guitar", "Alto Sax"]  # x400 first appearance, not x160


def test_flow_steps_follow_the_feature_order():
    report = parse_score(FIXTURES / "finale_score_order.pdf")

    assert [s.instrument for s in report.flow] == ["guitar", "alto sax", "trombone", "trumpet"]
