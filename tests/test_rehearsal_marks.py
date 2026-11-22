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


def test_mark_is_not_carried_to_a_page_where_it_does_not_appear():
    assert marks_by_instrument("rehearsal_marks.pdf")["Drums"] is None
