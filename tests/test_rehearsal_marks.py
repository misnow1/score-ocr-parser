"""Rehearsal mark recovery, through parse_score on a synthetic fixture."""

from pathlib import Path

from score_parser import parse_score

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"


def marks_by_instrument(name: str) -> dict[str, str | None]:
    report = parse_score(FIXTURES / name)
    return {f.instrument: f.rehearsal_mark for f in report.features}


def test_mark_below_a_tempo_line_is_read():
    assert marks_by_instrument("rehearsal_marks.pdf")["Trombone"] == "A"


def test_mark_beside_a_digit_or_text_is_separated_and_recognised():
    assert marks_by_instrument("rehearsal_marks.pdf")["Guitar"] == "C"


def test_mark_carries_onto_a_page_where_none_is_printed():
    assert marks_by_instrument("rehearsal_marks.pdf")["Drums"] == "C"


def feature_of(report, instrument):
    return next(f for f in report.features if f.instrument == instrument)


def test_mark_carries_across_pages_until_the_next_mark_resets_it():
    marks = marks_by_instrument("finale_mark_carry.pdf")

    assert marks["Alto Sax"] == "A"  # printed on its own page
    assert marks["Guitar"] == "A"  # page 2 prints none: carried from page 1
    assert marks["Drums"] == "B"  # page 3 prints B: the new mark replaces A
    assert marks["Trumpet"] == "B"  # page 4 prints none: B carried, not A


def test_feature_before_the_first_mark_of_the_score_has_none():
    assert marks_by_instrument("finale_mark_carry.pdf")["Trombone"] is None


def test_carried_mark_is_reported_with_its_page_a_reason_and_lower_confidence():
    report = parse_score(FIXTURES / "finale_mark_carry.pdf")
    carried, printed = feature_of(report, "Guitar"), feature_of(report, "Alto Sax")

    assert carried.mark_carried_from == 1
    assert "mark carried from p1" in carried.reasons
    assert printed.mark_carried_from is None
    assert not any("carried" in r for r in printed.reasons)
    assert printed.confidence == 0.9
    assert carried.confidence == 0.85  # same wording and evidence, five points less
    assert feature_of(report, "Trumpet").mark_carried_from == 3
