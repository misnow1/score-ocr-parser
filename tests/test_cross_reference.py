"""Cross-referencing part solos into the score's features (ticket #55), through
parse_score with a parts dir: a synthetic score (mark A with an open "(SOLOS)"
at bar 9, mark B with a "TBN SOLO" at bar 17, mark C with nothing) and a temp
`parts/<instrument folder>/` tree of synthetic one-staff parts."""

import shutil
from pathlib import Path

from score_parser import ParseOptions, parse_score
from score_parser.flow import render_yaml

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"
SCORE = FIXTURES / "finale_cross_reference.pdf"
TUNE = "Synthetic Cross Tune"


def parse_with(tmp_path: Path, parts: dict[str, str], score: Path = SCORE, tune: str = TUNE):
    """parse_score on the score with a tree built from {"folder/Part word": fixture name}."""
    root = tmp_path / "parts"
    copy = tmp_path / f"{tune} SCORE.pdf"
    shutil.copy(score, copy)
    score = copy
    for rel, fixture in parts.items():
        target = root / f"{rel.split('/')[0]}" / f"{tune} {rel.split('/')[1]}.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIXTURES / f"part_xref_{fixture}.pdf", target)
    return parse_score(score, ParseOptions(parts_dir=root))


def named(feature):
    return [(feature.instrument, feature.chair)] + [(p.instrument, p.chair) for p in feature.shared_with]


def at(report, mark):
    return [f for f in report.features if f.rehearsal_mark == mark]


def test_without_parts_the_open_solo_stays_open():
    [open_solo, trombone] = parse_score(SCORE).features

    assert (open_solo.instrument, open_solo.shared_with, open_solo.rehearsal_mark) == (None, [], "A")
    assert trombone.instrument == "Trombone"


def test_an_open_solo_names_the_instruments_and_chairs_of_the_parts_that_carry_it(tmp_path):
    report = parse_with(tmp_path, {
        "alto-sax-1/Clarinet": "a_and_c",  # a doubling in the alto 1 folder
        "trumpet-3/Trpt3": "a",
        "trombone-1/Trombone1": "none",
    })

    [feature] = at(report, "A")
    assert named(feature) == [("Clarinet", None), ("Trumpet", 3)]  # staff order of the score
    assert (feature.page, feature.bar, feature.kind) == (1, 9, "solo")  # the score keeps the structure
    assert feature.confidence > 0.6
    assert any("Clarinet part" in r for r in feature.reasons)


def test_the_flow_draft_uses_the_named_instruments_and_chairs(tmp_path):
    report = parse_with(tmp_path, {"alto-sax-1/Clarinet": "a_and_c", "trumpet-3/Trpt3": "a"})

    step = next(s for s in report.flow if s.mark == "A")
    assert step.section == "Clarinet and Trumpet 3 solo (A)"
    assert step.instrument == "clarinet, trumpet 3"
    assert "Clarinet and Trumpet 3 solo (A)" in render_yaml(report.flow)


def test_a_single_part_names_a_single_soloist(tmp_path):
    report = parse_with(tmp_path, {"trumpet-3/Trpt3": "a"})

    [feature] = at(report, "A")
    assert (feature.instrument, feature.chair, feature.shared_with) == ("Trumpet", 3, [])
    step = next(s for s in report.flow if s.mark == "A")
    assert (step.section, step.instrument) == ("Trumpet solo (A)", "trumpet")


def test_a_solo_found_only_in_a_part_is_added_in_score_order(tmp_path):
    report = parse_with(tmp_path, {"alto-sax-1/Clarinet": "a_and_c"})

    assert [(f.rehearsal_mark, f.instrument, f.bar) for f in report.features] == [
        ("A", "Clarinet", 9),
        ("B", "Trombone", 17),
        ("C", "Clarinet", 34),  # in the Clarinet part only; the score marks nothing at C
    ]
    added = at(report, "C")[0]
    assert added.page == 2  # where the score prints mark C
    assert added.confidence < 0.8 and any("only in the Clarinet part" in r for r in added.reasons)
    assert [s.mark for s in report.flow] == ["A", "B", "C"]


def test_parts_that_find_the_same_added_solo_share_it(tmp_path):
    report = parse_with(tmp_path, {"trumpet-3/Trpt3": "a_and_c", "alto-sax-1/Clarinet": "a_and_c"})

    [added] = at(report, "C")
    assert named(added) == [("Clarinet", None), ("Trumpet", 3)]  # one feature, staff order of the score


def test_a_score_feature_whose_present_part_does_not_carry_it_is_a_warning_not_a_drop(tmp_path):
    report = parse_with(tmp_path, {"trombone-1/Trombone1": "none", "trombone-2/Trombone2": "c"})

    [trombone] = at(report, "B")
    assert trombone.instrument == "Trombone"  # kept
    assert "the score marks a Trombone solo (mark B, bar 17) that the Trombone part does not carry" in report.warnings


def test_a_feature_is_not_a_disagreement_when_no_part_of_the_instrument_is_present(tmp_path):
    report = parse_with(tmp_path, {"trumpet-3/Trpt3": "a"})

    assert not any("does not carry" in w for w in report.warnings)


def test_a_part_that_carries_the_score_feature_confirms_it_and_fills_in_its_chair(tmp_path):
    report = parse_with(tmp_path, {"trombone-2/Trombone2": "cue_tbn"})

    [trombone] = at(report, "B")
    assert (trombone.instrument, trombone.chair, trombone.bar) == ("Trombone", 2, 17)
    assert any("carried by the Trombone part" in r for r in trombone.reasons)
    assert not any("does not carry" in w for w in report.warnings)


def test_a_part_solo_at_a_mark_the_score_does_not_print_is_a_warning_and_adds_nothing(tmp_path):
    report = parse_with(tmp_path, {"trumpet-3/Trpt3": "noisy"})

    assert [(f.rehearsal_mark, f.instrument, f.chair, f.bar) for f in report.features] == [
        ("A", "Trumpet", 3, 9),  # the same solo read twice names the soloist once
        ("B", "Trombone", None, 17),
        ("C", "Trumpet", 3, 34),
    ]
    assert any("ignored 1 solo (mark Z, bar 40): Z is not a rehearsal mark of the score" in w for w in report.warnings)


def test_a_vocal_part_never_names_a_soloist_or_adds_a_feature(tmp_path):
    report = parse_with(tmp_path, {"vocals/Vocals": "noisy"})

    assert [(f.rehearsal_mark, f.instrument) for f in report.features] == [("A", None), ("B", "Trombone")]
    [warning] = [w for w in report.warnings if "ignored" in w]
    assert "ignored 3 solos (mark A, bar 9, mark C, bar 34, mark Z, bar 40)" in warning
    assert "vocal" in warning


def test_a_part_whose_instrument_the_score_lacks_adds_nothing(tmp_path):
    report = parse_with(tmp_path, {"cello/Cello": "a_and_c"})

    assert [(f.rehearsal_mark, f.instrument) for f in report.features] == [("A", None), ("B", "Trombone")]
    assert any("Cello is not in the score's instrumentation" in w for w in report.warnings)


def test_a_cue_for_another_instrument_supports_its_solo_and_is_never_the_parts_own(tmp_path):
    report = parse_with(tmp_path, {"drums/Drums": "cue_tbn"})

    assert [(f.rehearsal_mark, f.instrument) for f in report.features] == [("A", None), ("B", "Trombone")]
    assert any("a 'Trombone solo' cue is printed in the Drums part" in r for r in at(report, "B")[0].reasons)
    assert not any("ignored" in w for w in report.warnings)


def test_a_part_solo_where_the_score_marks_another_instrument_is_a_warning(tmp_path):
    report = parse_with(tmp_path, {"piano/Piano": "b_at_17"})

    assert [(f.rehearsal_mark, f.instrument) for f in report.features] == [("A", None), ("B", "Trombone")]
    assert any("the score marks the Trombone solo there, not Piano" in w for w in report.warnings)


def test_a_part_solo_with_no_mark_matches_the_score_by_bar(tmp_path):
    report = parse_with(tmp_path, {"trumpet-3/Trpt3": "unmarked"})

    [feature] = at(report, "A")
    assert (feature.instrument, feature.chair, feature.bar) == ("Trumpet", 3, 9)


def test_an_unreadable_part_changes_nothing(tmp_path):
    report = parse_with(tmp_path, {"misc/(1)": "a"})  # no part word, and the folder names no instrument

    assert [p.part.instrument for p in report.parts.parts] == [None]
    assert [(f.rehearsal_mark, f.instrument) for f in report.features] == [("A", None), ("B", "Trombone")]


def test_a_part_with_far_too_many_solos_is_noise_and_adds_or_names_nothing(tmp_path):
    report = parse_with(tmp_path, {"trumpet-3/Trpt3": "many"})

    assert [(f.rehearsal_mark, f.instrument) for f in report.features] == [("A", None), ("B", "Trombone")]
    assert any("ignored 7 solos" in w and "too many solos" in w for w in report.warnings)


def test_a_part_solo_in_the_marks_range_names_the_open_solo_whatever_the_bars(tmp_path):
    report = parse_with(tmp_path, {"trumpet-3/Trpt3": "a_far"})  # bar 2 of mark A; the score's open solo is at bar 9

    [feature] = at(report, "A")
    assert (feature.instrument, feature.chair, feature.bar) == ("Trumpet", 3, 9)


def test_two_chairs_in_one_section_share_the_open_solo(tmp_path):
    report = parse_with(tmp_path, {"trumpet-2/Trpt2": "a_far", "trumpet-3/Trpt3": "a"})

    [feature] = at(report, "A")
    assert named(feature) == [("Trumpet", 2), ("Trumpet", 3)]


def test_open_solo_named_by_parts_stays_below_the_flow_drafts_todo_threshold(tmp_path):
    report = parse_with(tmp_path, {"trumpet-3/Trpt3": "a"})

    [feature] = at(report, "A")
    assert feature.confidence < 0.8
    assert next(s for s in report.flow if s.mark == "A").todo


def test_a_part_that_letters_the_section_differently_confirms_the_score_feature_nearby(tmp_path):
    report = parse_with(tmp_path, {"trombone-2/Trombone2": "a_at_16"})  # the score marks the trombone at B, bar 17

    assert [(f.rehearsal_mark, f.instrument, f.chair, f.bar) for f in report.features] == [
        ("A", None, None, 9),  # a trombone solo at bar 16 is not the open solo at bar 9: no one named there
        ("B", "Trombone", 2, 17),  # confirmed under another mark: no duplicate
    ]
    assert not any("does not carry" in w for w in report.warnings)


def test_a_part_solo_outside_its_marks_bar_range_is_not_added(tmp_path):
    report = parse_with(tmp_path, {"trumpet-3/Trpt3": "a_at_40"})  # mark A covers bars 1-16 in the score

    assert [(f.rehearsal_mark, f.instrument) for f in report.features] == [("A", None), ("B", "Trombone")]
    assert any("ignored 1 solo (mark A, bar 40): its bar is outside the range of mark A" in w for w in report.warnings)


def test_a_part_solo_with_no_bar_is_never_added(tmp_path):
    report = parse_with(tmp_path, {"trumpet-3/Trpt3": "barless"})

    assert [(f.rehearsal_mark, f.instrument) for f in report.features] == [("A", None), ("B", "Trombone")]
    assert any("ignored 1 solo (mark C): no bar to place it by" in w for w in report.warnings)


def test_many_parts_marking_one_solo_are_the_bands_open_solo_and_name_no_one(tmp_path):
    report = parse_with(tmp_path, {
        "trumpet-1/Trpt1": "a", "trumpet-2/Trpt2": "a", "trumpet-3/Trpt3": "a",
        "piano/Piano": "a", "drums/Drums": "a",
    })

    [feature] = at(report, "A")
    assert (feature.instrument, feature.shared_with) == (None, [])
    assert any("5 parts mark a solo here" in r for r in feature.reasons)
    assert not any("ignored" in w for w in report.warnings)


def test_four_parts_marking_one_solo_are_named(tmp_path):
    report = parse_with(tmp_path, {
        "trumpet-1/Trpt1": "a", "trumpet-2/Trpt2": "a", "trumpet-3/Trpt3": "a", "piano/Piano": "a",
    })

    assert named(at(report, "A")[0]) == [("Trumpet", 1), ("Trumpet", 2), ("Trumpet", 3), ("Piano", None)]


def test_two_chairs_that_both_carry_a_chairless_score_feature_are_both_named(tmp_path):
    report = parse_with(tmp_path, {"trombone-1/Trombone1": "cue_tbn", "trombone-3/Trombone3": "cue_tbn"})

    [trombone] = at(report, "B")
    assert named(trombone) == [("Trombone", 1), ("Trombone", 3)]
    assert not any("does not carry" in w for w in report.warnings)


SHARED = FIXTURES / "finale_cross_reference_shared.pdf"
SHARED_TUNE = "Synthetic Shared Cross Tune"


def test_a_shared_feature_takes_another_instrument_whose_part_carries_the_solo(tmp_path):
    report = parse_with(tmp_path, {"piano/Piano": "a"}, SHARED, SHARED_TUNE)

    [feature] = at(report, "A")
    assert named(feature) == [("Clarinet", None), ("Trumpet", None), ("Trombone", None), ("Piano", None)]
    assert feature.page == 1 and feature.bar == 9


def test_a_shared_feature_does_not_grow_into_the_whole_band(tmp_path):
    report = parse_with(tmp_path, {"piano/Piano": "a", "drums/Drums": "a"}, SHARED, SHARED_TUNE)

    [feature] = at(report, "A")
    assert named(feature) == [("Clarinet", None), ("Trumpet", None), ("Trombone", None)]
    assert sum("not added to the shared feature" in w for w in report.warnings) == 2


REUSED = FIXTURES / "finale_cross_reference_reused.pdf"
REUSED_TUNE = "Synthetic Reuse Tune"


def test_a_reused_mark_letter_is_told_apart_by_bar(tmp_path):
    report = parse_with(tmp_path, {"trumpet-3/Trpt3": "a_at_41"}, REUSED, REUSED_TUNE)

    assert [(f.page, f.bar, f.rehearsal_mark, f.instrument) for f in report.features] == [
        (1, 9, "A", None),  # the first A section is not the part's
        (2, 41, "A", "Trumpet"),
    ]


def test_an_added_solo_goes_on_the_page_of_its_bar_in_score_order(tmp_path):
    report = parse_with(tmp_path, {"alto-sax-1/Clarinet": "b_at_28"}, REUSED, REUSED_TUNE)

    assert [(f.page, f.bar, f.rehearsal_mark, f.instrument) for f in report.features] == [
        (1, 9, "A", None),
        (2, 28, "B", "Clarinet"),  # mark B is printed on page 1; bar 28 is on page 2
        (2, 41, "A", None),
    ]
