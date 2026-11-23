"""Vocal lead handover without wording, and a lead over a page turn, through parse_score on synthetic fixtures."""

from pathlib import Path

from score_parser import parse_score
from score_parser.flow import LOW_CONFIDENCE

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"


def leads(report, page=None):
    return [f for f in report.features if f.kind == "vocal lead" and page in (None, f.page)]


def test_a_lead_staff_change_with_no_wording_is_a_lead_for_the_new_voice():
    report = parse_score(FIXTURES / "finale_vocal_handover.pdf")

    got = [(f.voice, f.page, f.bar, f.rehearsal_mark) for f in leads(report, 1)]
    assert got == [
        ("male", 1, 3, "B"),  # the male alone sings bar 3, the female and both backings stop
        ("female", 1, 5, "B"),  # the female alone sings bars 5-6 after the male
    ]
    assert all(f.instrument is None for f in leads(report))


def test_a_handover_is_less_sure_than_a_voice_named_in_text_and_gets_a_flow_todo():
    report = parse_score(FIXTURES / "finale_vocal_handover.pdf")

    handover = leads(report, 1)[0]
    assert handover.confidence < LOW_CONFIDENCE
    assert any("Voice Lead M" in r for r in handover.reasons)
    step = next(s for s in report.flow if s.section.startswith("Male vocal lead (B)"))
    assert step.todo and "low confidence" in step.todo


def test_no_lead_is_invented_where_the_voice_staves_all_sing():
    report = parse_score(FIXTURES / "finale_vocal_handover.pdf")

    assert leads(report, 2) == []  # every voice staff sings, then both leads sing together


def test_a_handover_with_the_wording_printed_is_one_feature_with_the_text_evidence():
    report = parse_score(FIXTURES / "finale_vocal_handover.pdf")

    (male,) = leads(report, 3)
    assert (male.voice, male.section, male.bar) == ("male", "Verse 2", 15)
    assert male.raw_text == "Male Lead Verse 2"
    assert male.confidence >= LOW_CONFIDENCE
    # the text and the handover read from the staves are merged copies of one marking
    assert "merged 2 copies of the same marking" in male.reasons


def test_a_one_bar_fill_by_the_other_lead_is_no_handover():
    report = parse_score(FIXTURES / "finale_vocal_handover.pdf")

    assert leads(report, 4) == []  # the female alone sings bar 21 only, between male bars


def test_wording_and_handovers_count_in_the_order_they_sit_along_the_bars():
    report = parse_score(FIXTURES / "finale_vocal_lead_order.pdf")

    got = [(f.voice, f.page, f.bar) for f in leads(report) if f.page < 8]
    assert got == [
        ("female", 1, 5),  # "solo" over Voice Lead F
        ("male", 2, 7),  # handover: the male alone sings bars 7-8
        ("female", 2, 11),  # the F "solo" returns after the male: a new lead, not a reminder of page 1
        ("female", 3, 40),  # "Female Lead" in bar 40
        ("male", 3, 42),  # handover
        ("female", 3, 44),  # the female returns after the male on the same system: her own feature
        ("male", 5, 106),  # "Male Lead" (the male singing from the first bar: one feature)
        ("female", 5, 109),  # handover back to the female after the text lead
    ]


def test_a_text_lead_early_on_a_system_does_not_wipe_out_a_handover_later_on_it():
    report = parse_score(FIXTURES / "finale_vocal_lead_order.pdf")

    # page 5 ends with the female alone; the female alone on page 7 is the lead already
    assert leads(report, 7) == []
    assert leads(report, 4) == []


def test_the_first_bar_is_read_when_its_left_edge_is_not_a_barline():
    report = parse_score(FIXTURES / "finale_vocal_lead_order.pdf")

    # the bar is only approximate here (the first bar has no barline to count from)
    assert [f.voice for f in leads(report, 8)] == ["male"]


def test_a_lead_restated_after_a_page_turn_is_one_feature():
    report = parse_score(FIXTURES / "finale_vocal_page_turn.pdf")

    first = leads(report, 1)[0]
    assert (first.voice, first.page, first.bar) == ("female", 1, 5)
    assert [(loc.page, loc.bar) for loc in first.locations] == [(1, 5), (2, 8)]
    assert leads(report, 2) == []


def test_voiceless_choir_cues_on_successive_pages_stay_separate():
    report = parse_score(FIXTURES / "finale_vocal_page_turn.pdf")

    got = [(f.voice, f.page, f.bar) for f in report.features if f.page in (5, 6)]
    assert got == [(None, 5, 104), (None, 6, 107)]


def test_another_voice_leading_in_between_makes_the_restated_lead_a_new_feature():
    report = parse_score(FIXTURES / "finale_vocal_page_turn.pdf")

    got = [(f.voice, f.page, f.bar) for f in report.features if 3 <= f.page <= 4]
    assert got == [("female", 3, 61), ("male", 3, 64), ("female", 4, 67)]


def test_an_unsectioned_lead_and_a_later_one_naming_a_section_are_two_features():
    report = parse_score(FIXTURES / "finale_vocal_page_turn.pdf")

    got = [(f.voice, f.section, f.page) for f in report.features if f.page in (7, 8)]
    assert got == [("male", None, 7), ("male", "Verse 2", 8)]


def test_a_lead_restated_under_a_new_rehearsal_mark_is_a_new_feature():
    report = parse_score(FIXTURES / "finale_vocal_page_turn.pdf")

    got = [(f.voice, f.page, f.rehearsal_mark) for f in report.features if f.page in (9, 10)]
    assert got == [("female", 9, "A"), ("female", 10, "B")]
