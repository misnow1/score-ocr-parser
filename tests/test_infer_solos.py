"""Inferring unmarked solos from which parts are resting (ticket #66), through
the public seams: parse_part (the bars a part plays and rests) and parse_score
with a parts dir. The synthetic score has marks A to E, eight bars apart (bars 1,
9, 17, 25, 33), one system per page, and the staves Alto Sax 1, Tenor Sax 1,
Baritone Sax, Trumpet 1, Trombone 1, Piano and Drums. A synthetic part is a plan,
a letter per section A to E: p = played, r = an eight-bar multi-bar rest, h = three
bars played then a five-bar rest, u = only a five-bar rest (its bars cover five of
the eight)."""

import shutil
from pathlib import Path

from score_parser import ParseOptions, parse_part, parse_score
from score_parser.flow import render_yaml
from score_parser.models import BarRun

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"
TUNE = "Synthetic Infer Tune"

# (folder, part word): the part's player slot and its instrument
SAX = ("alto-sax-1", "Alto Sax 1")
TENOR = ("tenor-sax-1", "Tenor Sax 1")
BARI = ("bari", "Baritone Sax")
TRUMPET = ("trumpet-1", "Trumpet 1")
TROMBONE = ("trombone-1", "Trombone 1")
WINDS = [SAX, TENOR, BARI, TRUMPET, TROMBONE]

LONE = "rpppp"  # rests at A, plays B to E
OTHERS = "prppp"  # plays A, rests at B, plays C to E


def band(lone: str = LONE, others: str = OTHERS, **plans: str) -> dict[tuple[str, str], str]:
    """The alto sax is the wind that plays; the other four rest at B and play elsewhere.
    `plans` replaces a player's plan: tenor="phppp"."""
    names = {"sax": SAX, "tenor": TENOR, "bari": BARI, "trumpet": TRUMPET, "trombone": TROMBONE}
    found = {SAX: lone, **{w: others for w in WINDS[1:]}}
    return {**found, **{names[k]: plan for k, plan in plans.items()}}


def infer(tmp_path: Path, plans: dict[tuple[str, str], str], score: str = "finale_infer"):
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


def not_inferred(report) -> list[str]:
    return [w for w in report.warnings if w.startswith("unmarked solos not inferred")]


def test_a_part_reports_the_bars_it_plays_and_the_bars_it_rests(tmp_path):
    part = tmp_path / "trumpet-1" / f"{TUNE} Trumpet 1.pdf"
    part.parent.mkdir()
    shutil.copy(FIXTURES / "part_infer_prppp.pdf", part)

    assert parse_part(part).bars == [BarRun(1, 8, False), BarRun(9, 16, True), BarRun(17, 40, False)]


def test_one_wind_playing_while_the_other_winds_rest_is_a_possible_solo(tmp_path):
    report = infer(tmp_path, band())

    [solo] = inferred(report)
    assert (solo.kind, solo.instrument, solo.chair, solo.rehearsal_mark, solo.page, solo.bar) == (
        "solo", "Alto Sax", 1, "B", 2, 9
    )
    assert solo.confidence == 0.5
    assert any("inferred from the other parts resting" in r for r in solo.reasons)
    assert report.features == [solo]  # nothing else is marked in the score
    assert not_inferred(report) == []


def test_the_flow_draft_flags_an_inferred_solo_for_review(tmp_path):
    report = infer(tmp_path, band())

    [step] = report.flow
    assert step.mark == "B" and step.todo and "inferred from the other parts resting" in step.todo
    assert "TODO(score-parser)" in render_yaml(report.flow)


def test_a_doubling_part_stands_for_its_player_slot_and_names_the_instrument_it_plays(tmp_path):
    plans = band()
    del plans[SAX]
    report = infer(tmp_path, {("alto-sax-1", "Clarinet"): LONE, **plans})  # the Alto Sax 1 player's part

    [solo] = inferred(report)
    assert (solo.instrument, solo.rehearsal_mark, solo.bar) == ("Clarinet", "B", 9)


def test_the_rhythm_section_is_not_counted_either_way(tmp_path):
    report = infer(tmp_path, {**band(), ("piano", "Piano"): "ppppp", ("drums", "Drums"): "ppppp"})

    assert [f.instrument for f in inferred(report)] == ["Alto Sax"]


def test_two_winds_playing_together_are_no_solo(tmp_path):
    report = infer(tmp_path, band(tenor=LONE))

    assert report.features == []


def test_a_part_that_half_plays_is_no_clean_rest(tmp_path):
    report = infer(tmp_path, band(tenor="phppp"))  # three bars played at B, then a five-bar rest

    assert report.features == []
    assert not_inferred(report) == []  # a half-playing part is a judgement, not a missing read


def test_a_wind_that_plays_only_a_few_bars_of_the_stretch_is_no_solo(tmp_path):
    report = infer(tmp_path, band(lone="rhppp"))  # three bars of the eight, then a rest

    assert report.features == []


def test_the_inference_needs_three_players_resting(tmp_path):
    plans = {SAX: LONE, TENOR: OTHERS, TRUMPET: OTHERS}
    report = infer(tmp_path, plans, score="finale_infer_three")  # one wind, two others

    assert report.features == []


def test_the_parts_of_a_doubler_are_one_player(tmp_path):
    plans = {SAX: LONE, TENOR: OTHERS, ("tenor-sax-1", "Clarinet"): OTHERS, TRUMPET: OTHERS}
    report = infer(tmp_path, plans, score="finale_infer_three")  # two players rest, three parts

    assert report.features == []


def test_no_solo_is_inferred_when_the_winds_that_rest_never_play(tmp_path):
    """One wind carrying the whole song over the rhythm section is the arrangement, not a solo."""
    report = infer(tmp_path, band(others="rrrrr"))

    assert report.features == []


def test_the_resting_winds_must_play_somewhere_else_in_the_song(tmp_path):
    report = infer(tmp_path, band(others="rrrrr", tenor=OTHERS))  # only one of them is ever heard

    assert report.features == []


def test_a_missing_part_means_the_inference_is_not_possible(tmp_path):
    plans = band()
    del plans[TROMBONE]
    report = infer(tmp_path, plans)

    assert report.features == []
    [warning] = not_inferred(report)
    assert "Trombone" in warning and "mark B" in warning


def test_a_missing_part_is_not_reported_when_no_stretch_looked_like_a_solo(tmp_path):
    plans = band(tenor=LONE)
    del plans[TROMBONE]

    assert not_inferred(infer(tmp_path, plans)) == []


def test_a_part_whose_bars_are_not_read_in_a_stretch_makes_it_not_possible(tmp_path):
    report = infer(tmp_path, band(trombone="puppp"))  # five of the eight bars of B

    assert report.features == []
    assert any("not inferred at mark B" in w for w in not_inferred(report))


def test_a_part_with_no_multi_bar_rest_is_unknown_not_playing(tmp_path):
    """A part that lays out in single empty bars or cue notes would read as playing."""
    report = infer(tmp_path, band(tenor="ppppp"))

    assert report.features == []
    assert any("not inferred at mark B" in w for w in not_inferred(report))


def test_a_marked_solo_is_never_duplicated_or_overruled(tmp_path):
    report = infer(tmp_path, band(), score="finale_infer_marked")

    [marked] = report.features
    assert (marked.instrument, marked.rehearsal_mark) == ("Trombone", "B")
    assert inferred(report) == []


def test_two_marks_printed_together_are_one_stretch(tmp_path):
    report = infer(tmp_path, band(), score="finale_infer_twin")

    assert len(inferred(report)) == 1 and len(report.flow) == 1


def test_a_wind_in_or_after_the_stretch_of_a_vocal_lead_is_a_backing(tmp_path):
    report = infer(tmp_path, band(), score="finale_infer_vocal")  # the lead starts at A; the wind is alone at B

    assert any(f.kind == "vocal lead" for f in report.features)
    assert inferred(report) == []


def test_a_wind_two_stretches_after_a_vocal_lead_is_a_possible_solo(tmp_path):
    report = infer(tmp_path, band(lone="rrprr", others="pprpp"), score="finale_infer_vocal")

    [solo] = inferred(report)
    assert (solo.rehearsal_mark, solo.bar) == ("C", 17)


def test_a_score_with_one_mark_has_no_stretches_to_tell_apart(tmp_path):
    report = infer(tmp_path, band(), score="finale_infer_one_mark")

    assert report.features == [] and not_inferred(report) == []


def test_without_a_parts_dir_nothing_is_inferred():
    assert parse_score(FIXTURES / "finale_infer.pdf").features == []
