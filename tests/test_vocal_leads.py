"""Vocal lead features, through parse_score on a synthetic fixture."""

from pathlib import Path

from score_parser import parse_score
from score_parser.flow import render_yaml

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"


def leads(report):
    return [f for f in report.features if f.kind == "vocal lead"]


def test_vocal_leads_carry_voice_section_and_location():
    report = parse_score(FIXTURES / "finale_vocal_leads.pdf")

    got = [(f.voice, f.section, f.page, f.bar, f.rehearsal_mark) for f in leads(report)]
    assert got == [
        ("female", "Verse 1", 1, 1, "B"),  # text plus a bare solo above Voice Lead F: one feature
        ("male", "Verse 2", 1, 1, "B"),  # the solo above the backing staff adds nothing
        ("female", None, 3, 17, None),  # a bare solo above Voice Lead F; no mark printed on this page
    ]
    male = next(f for f in leads(report) if f.voice == "male")
    # the bare solo above Voice Lead M on the next page is the same lead, a reminder
    assert [(loc.page, loc.bar) for loc in male.locations] == [(1, 1), (2, 9)]
    assert all(f.instrument is None for f in leads(report))


def test_instrument_solos_are_unaffected_and_no_instrumentless_solos_remain():
    report = parse_score(FIXTURES / "finale_vocal_leads.pdf")

    others = [f for f in report.features if f.kind != "vocal lead"]
    assert [(f.kind, f.instrument) for f in others] == [("solo", "Alto Sax")]


def test_voice_lead_staves_are_not_added_to_the_instruments():
    report = parse_score(FIXTURES / "finale_vocal_leads.pdf")

    assert not any("Voice" in e.instrument or e.instrument == "Vocal" for e in report.instrumentation)


def test_flow_draft_has_a_step_per_vocal_lead_with_a_todo_only_when_unsure():
    report = parse_score(FIXTURES / "finale_vocal_leads.pdf")

    steps = [s for s in report.flow if "vocal lead" in s.section]
    assert [s.section for s in steps] == [
        "Female vocal lead, Verse 1 (B)",
        "Male vocal lead, Verse 2 (B)",
        "Female vocal lead",
    ]
    assert all(s.instrument == "vocal" for s in steps)
    # a voice named in the text is trusted; one read from the staff only gets a TODO
    assert [s.todo is None for s in steps] == [True, True, False]
    assert "kind:" not in render_yaml(report.flow)
