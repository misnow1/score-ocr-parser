"""Inferring unmarked solos from which parts are resting (ticket #66), through
the public seams: parse_part (the bars a part plays and rests) and parse_score
with a parts dir. The synthetic score has marks A to E, eight bars apart (bars 1,
9, 17, 25, 33) and the staves Alto Sax 1, Tenor Sax 1, Trumpet 1, Trombone 1,
Piano and Drums. A synthetic part is described by a plan, a letter per section A
to E: p = played, r = a multi-bar rest, x = the section is left out of the part."""

import shutil
from pathlib import Path

from score_parser import ParseOptions, parse_part, parse_score
from score_parser.flow import render_yaml
from score_parser.models import BarRun

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"
TUNE = "Synthetic Infer Tune"
FULL = "ppppp"  # plays through every section

# folder, part word: the part's player slot and its instrument
SAX = ("alto-sax-1", "Alto Sax 1")
TENOR = ("tenor-sax-1", "Tenor Sax 1")
TRUMPET = ("trumpet-1", "Trumpet 1")
TROMBONE = ("trombone-1", "Trombone 1")


def infer(tmp_path: Path, plans: dict[tuple[str, str], str], score: str = "finale_infer") -> object:
    """parse_score on a copy of the score with a parts tree built from {(folder, part word): plan}."""
    root = tmp_path / "parts"
    copy = tmp_path / f"{TUNE} SCORE.pdf"
    shutil.copy(FIXTURES / f"{score}.pdf", copy)
    for (folder, word), plan in plans.items():
        target = root / folder / f"{TUNE} {word}.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIXTURES / f"part_infer_{plan}.pdf", target)
    return parse_score(copy, ParseOptions(parts_dir=root))


def inferred(report) -> list:
    return [f for f in report.features if any("inferred" in r for r in f.reasons)]


def test_a_part_reports_the_bars_it_plays_and_the_bars_it_rests(tmp_path):
    part = tmp_path / "trumpet-1" / f"{TUNE} Trumpet 1.pdf"
    part.parent.mkdir()
    shutil.copy(FIXTURES / "part_infer_prppp.pdf", part)

    assert parse_part(part).bars == [BarRun(1, 8, False), BarRun(9, 16, True), BarRun(17, 40, False)]


def test_one_wind_playing_while_the_other_winds_rest_is_a_possible_solo(tmp_path):
    report = infer(tmp_path, {SAX: FULL, TENOR: "prppp", TRUMPET: "prppp", TROMBONE: "prppp"})

    [solo] = inferred(report)
    assert (solo.kind, solo.instrument, solo.rehearsal_mark, solo.page, solo.bar) == ("solo", "Alto Sax", "B", 1, 9)
    assert solo.confidence <= 0.6
    assert any("inferred from the other parts resting" in r for r in solo.reasons)
    assert report.features == [solo]  # nothing else is marked in the score


def test_the_flow_draft_flags_an_inferred_solo_for_review(tmp_path):
    report = infer(tmp_path, {SAX: FULL, TENOR: "prppp", TRUMPET: "prppp", TROMBONE: "prppp"})

    [step] = report.flow
    assert step.mark == "B" and step.todo and "inferred from the other parts resting" in step.todo
    assert "TODO(score-parser)" in render_yaml(report.flow)


def test_a_doubling_part_stands_for_its_player_slot_and_names_the_instrument_it_plays(tmp_path):
    clarinet = ("alto-sax-1", "Clarinet")  # the Alto Sax 1 player's part, a doubling
    report = infer(tmp_path, {clarinet: FULL, TENOR: "prppp", TRUMPET: "prppp", TROMBONE: "prppp"})

    [solo] = inferred(report)
    assert (solo.instrument, solo.rehearsal_mark, solo.bar) == ("Clarinet", "B", 9)


def test_two_winds_playing_together_are_no_solo(tmp_path):
    report = infer(tmp_path, {SAX: FULL, TENOR: FULL, TRUMPET: "prppp", TROMBONE: "prppp"})

    assert report.features == []


def test_no_solo_is_inferred_when_the_winds_that_rest_never_play(tmp_path):
    """One wind carrying the whole song over the rhythm section is the arrangement, not a solo."""
    report = infer(tmp_path, {SAX: FULL, TENOR: "rrrrr", TRUMPET: "rrrrr", TROMBONE: "rrrrr"})

    assert report.features == []


def test_a_missing_part_means_the_inference_is_not_possible(tmp_path):
    report = infer(tmp_path, {SAX: FULL, TENOR: "prppp", TRUMPET: "prppp"})  # no trombone part

    assert report.features == []
    assert any("not inferred" in w and "Trombone" in w for w in report.warnings)


def test_a_part_whose_bars_are_not_read_in_a_stretch_makes_it_not_possible(tmp_path):
    report = infer(tmp_path, {SAX: FULL, TENOR: "prppp", TRUMPET: "prppp", TROMBONE: "pxppp"})  # no staff for B

    assert report.features == []
    assert any("not inferred at mark B" in w for w in report.warnings)


def test_a_marked_solo_is_never_duplicated_or_overruled(tmp_path):
    report = infer(
        tmp_path, {SAX: FULL, TENOR: "prppp", TRUMPET: "prppp", TROMBONE: "prppp"}, score="finale_infer_marked"
    )

    [marked] = report.features
    assert (marked.instrument, marked.rehearsal_mark) == ("Trombone", "B")
    assert inferred(report) == []


def test_without_a_parts_dir_nothing_is_inferred():
    assert parse_score(FIXTURES / "finale_infer.pdf").features == []
