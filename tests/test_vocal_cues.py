"""Vocal cues over choir staves become vocal leads, through parse_score on a synthetic fixture."""

from pathlib import Path

from score_parser import parse_score

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"


def test_solo_cues_over_a_choir_staff_are_voiceless_vocal_leads():
    report = parse_score(FIXTURES / "finale_vocal_cues.pdf")

    got = [(f.kind, f.instrument, f.voice, f.page, f.bar) for f in report.features if f.kind == "vocal lead"]
    assert got == [
        ("vocal lead", None, None, 1, 1),  # "Solo", carried on to page 2 as "Verse 1x - Solo"
        ("vocal lead", None, None, 3, 40),  # "Solo or All"
        ("vocal lead", None, None, 4, 60),  # "(Solo)" between the SATB staves, far above Piano
    ]


def test_a_cue_across_a_page_turn_is_one_feature():
    report = parse_score(FIXTURES / "finale_vocal_cues.pdf")

    first = next(f for f in report.features if f.kind == "vocal lead")
    assert [(loc.page, loc.bar) for loc in first.locations] == [(1, 1), (2, 9)]


def test_instrument_solos_are_unaffected_and_the_choir_is_no_instrument():
    report = parse_score(FIXTURES / "finale_vocal_cues.pdf")

    others = [f for f in report.features if f.kind != "vocal lead"]
    assert [(f.kind, f.instrument) for f in others] == [("solo", "Alto Sax")]
    assert "SATB" not in [lb for e in report.instrumentation for lb in e.labels]
