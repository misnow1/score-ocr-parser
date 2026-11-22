"""One marking printed over the staves of a system is one feature, through
parse_score on a synthetic fixture."""

from pathlib import Path

from score_parser import parse_score
from score_parser.flow import render_yaml

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"


def test_generic_marking_over_every_staff_is_one_open_solo_with_no_instrument():
    report = parse_score(FIXTURES / "finale_folded_solos.pdf")

    [open_solo] = [f for f in report.features if "instrumental" in f.raw_text.lower()]
    assert (open_solo.instrument, open_solo.page, open_solo.bar) == (None, 1, 9)
    assert open_solo.shared_with == []
    step = next(s for s in report.flow if s.instrument == "unknown" and "page 1, bar 9" in s.note)
    assert step.todo
    assert "TODO(score-parser)" in render_yaml(report.flow)


def test_copies_with_and_without_an_instrument_fold_into_the_named_one():
    report = parse_score(FIXTURES / "finale_folded_solos.pdf")

    solos = [f for f in report.features if f.raw_text == "SOLO"]
    assert [(f.instrument, f.page) for f in solos] == [("Piano", 1)]


def test_named_marking_over_every_staff_is_one_feature_of_that_instrument():
    report = parse_score(FIXTURES / "finale_folded_solos.pdf")

    guitar = [f for f in report.features if f.page == 2]
    assert [(f.instrument, f.shared_with) for f in guitar] == [("Guitar", [])]


def test_whole_fixture_reports_three_features():
    report = parse_score(FIXTURES / "finale_folded_solos.pdf")

    assert len(report.features) == 3
