"""Features shared by several instruments, through parse_score on a synthetic fixture."""

from pathlib import Path

from score_parser import parse_score
from score_parser.flow import render_yaml

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"


def shared(report):
    return [f for f in report.features if f.shared_with]


def test_one_marking_over_several_staves_is_one_feature_naming_all_instruments_and_chairs():
    report = parse_score(FIXTURES / "finale_shared_solos.pdf")

    [feature] = shared(report)
    names = [(feature.instrument, feature.chair)] + [(p.instrument, p.chair) for p in feature.shared_with]
    assert names == [("Soprano Sax", None), ("Clarinet", None), ("Trumpet", 3)]
    assert (feature.page, feature.bar, feature.rehearsal_mark) == (1, 9, "A")
    assert [(loc.page, loc.bar) for loc in feature.locations] == [(1, 9)]


def test_single_instrument_features_are_unaffected_and_distant_markings_stay_apart():
    report = parse_score(FIXTURES / "finale_shared_solos.pdf")

    alone = [f for f in report.features if not f.shared_with]
    assert sorted((f.instrument, f.page) for f in alone) == [
        ("Alto Sax", 1),
        ("Clarinet", 1),  # bare "SOLO" on the next system, two systems on, 200 pt apart
        ("Soprano Sax", 1),
    ]


def test_flow_draft_has_one_step_naming_every_instrument_and_chair():
    report = parse_score(FIXTURES / "finale_shared_solos.pdf")

    step = next(s for s in report.flow if "Trumpet 3" in s.section)
    assert step.section == "Soprano Sax, Clarinet and Trumpet 3 solo (A)"
    assert step.instrument == "soprano sax, clarinet, trumpet 3"
    assert "page 1, bar 9" in step.note
    assert "Soprano Sax, Clarinet and Trumpet 3 solo" in render_yaml(report.flow)
