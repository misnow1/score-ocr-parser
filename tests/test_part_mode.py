"""Part mode (ticket #53): one part file read through parse_part, on the synthetic
one-staff part placed in a temp `parts/<player slot>/<file>.pdf` tree."""

import shutil
from pathlib import Path

import pytest

from score_parser import parse_part, parse_score

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"
PART = FIXTURES / "part_one_staff.pdf"


def place(tmp_path: Path, folder: str, name: str, source: Path = PART) -> Path:
    """`source` copied to tmp_path/parts/<folder>/<name>.pdf."""
    target = tmp_path / "parts" / folder / f"{name}.pdf"
    target.parent.mkdir(parents=True)
    shutil.copy(source, target)
    return target


def solos(report):
    return [(f.page, f.bar, f.rehearsal_mark) for f in report.features]


def test_part_reports_instrument_chair_and_solos_with_page_bar_and_mark(tmp_path):
    report = parse_part(place(tmp_path, "trumpet-1", "Synthetic Tune Trpt1"))

    assert (report.part.instrument, report.part.chairs) == ("Trumpet", [1])
    assert solos(report) == [(1, 6, "A"), (2, 16, "B")]
    assert {f.instrument for f in report.features} == {"Trumpet"}
    assert all(f.confidence > 0.5 and f.reasons for f in report.features)
    assert report.features[1].mark_carried_from == 1


def test_title_verse_words_and_glyph_junk_never_become_labels_or_features(tmp_path):
    report = parse_part(place(tmp_path, "trumpet-1", "Synthetic Tune Trpt1"))

    assert len(report.features) == 2  # the title says "Solo": not a feature
    assert report.warnings == []
    assert not hasattr(report, "unknown_labels")
    assert report.title == "Synthetic Tune"


@pytest.mark.parametrize(
    ("name", "instrument", "chairs"),
    [
        ("Synthetic Tune Trpt1", "Trumpet", [1]),
        ("Synthetic Tune Trombone2", "Trombone", [2]),
        ("Synthetic Tune Tenor sax1-2", "Tenor Sax", [1, 2]),
        ("Synthetic Tune Trumpet 4-6", "Trumpet", [4, 5, 6]),
        ("Synthetic Tune Alto sax", "Alto Sax", []),
        ("Synthetic Tune Sleigh Bells", "Sleigh Bells", []),
        ("Synthetic Tune - Violin", "Violin", []),
    ],
)
def test_instrument_and_chairs_come_from_the_filenames_trailing_part_word(tmp_path, name, instrument, chairs):
    report = parse_part(place(tmp_path, "somewhere", name))

    assert (report.part.instrument, report.part.chairs) == (instrument, chairs)
    assert report.part.instrument_from == "filename"


def test_combined_chairs_file_keeps_its_chairs_and_marks_solo_chair_ambiguous(tmp_path):
    report = parse_part(place(tmp_path, "tenor-sax-2", "Synthetic Tune Tenor sax1-2"))

    assert report.part.chairs == [1, 2]
    assert [(f.instrument, f.chair, f.chair_ambiguous) for f in report.features] == [("Tenor Sax", None, True)] * 2


def test_part_in_its_own_player_slot_is_not_a_doubling(tmp_path):
    report = parse_part(place(tmp_path, "trombone-2", "Synthetic Tune Trombone2"))

    assert (report.part.player_slot, report.part.relation, report.part.note) == ("trombone-2", "same", "")
    assert report.warnings == []


def test_clarinet_part_in_the_alto_sax_1_folder_is_a_doubling_not_a_warning(tmp_path):
    report = parse_part(place(tmp_path, "alto-sax-1", "Synthetic Tune Clarinet"))

    assert report.part.instrument == "Clarinet"
    assert report.part.player_slot == "alto-sax-1"
    assert report.part.slot_instrument == "Alto Sax"
    assert report.part.relation == "doubling"
    assert report.part.note == "player slot alto-sax-1 (Alto Sax) plays Clarinet"
    assert report.warnings == []
    assert {f.instrument for f in report.features} == {"Clarinet"}  # the instrument is the filename's


@pytest.mark.parametrize(
    ("folder", "name"),
    [("tenor-sax-1", "soprano sax"), ("trombone-3", "Tuba"), ("flute", "Piccolo"), ("trumpet-2", "Flugelhorn")],
)
def test_the_known_doublings_are_doublings(tmp_path, folder, name):
    report = parse_part(place(tmp_path, folder, f"Synthetic Tune {name}"))

    assert report.part.relation == "doubling"
    assert report.warnings == []


def test_a_misfiled_part_is_an_unexplained_disagreement_and_is_not_corrected(tmp_path):
    report = parse_part(place(tmp_path, "tenor-sax-2", "Synthetic Tune Trombone"))

    assert report.part.instrument == "Trombone"  # the filename still wins
    assert report.part.player_slot == "tenor-sax-2"
    assert report.part.relation == "unexplained"
    assert report.warnings == [
        "player slot tenor-sax-2 (Tenor Sax) holds a Trombone part: unexplained disagreement, left as filed"
    ]
    assert {f.instrument for f in report.features} == {"Trombone"}


def test_folder_gives_the_instrument_when_the_filename_names_none(tmp_path):
    report = parse_part(place(tmp_path, "trumpet-3", "Synthetic Tune"))

    assert (report.part.instrument, report.part.chairs) == ("Trumpet", [3])
    assert (report.part.instrument_from, report.part.relation) == ("folder", "same")
    assert report.warnings == []
    assert report.title == "Synthetic Tune"


def test_part_with_neither_a_part_word_nor_an_instrument_folder_warns_and_reads_no_solos(tmp_path):
    report = parse_part(place(tmp_path, "loose files", "Synthetic Tune"))

    assert report.part.instrument is None
    assert report.features == []
    assert any("instrument unknown" in w for w in report.warnings)


def test_folder_that_names_no_instrument_is_an_unknown_slot_not_a_disagreement(tmp_path):
    report = parse_part(place(tmp_path, "loose files", "Synthetic Tune - Violin"))

    assert (report.part.instrument, report.part.relation) == ("Violin", "unknown")
    assert report.warnings == []


def test_page_without_drawn_staves_warns_instead_of_reading_nothing_silently(tmp_path):
    report = parse_part(place(tmp_path, "trumpet-1", "Synthetic Tune Trpt1", FIXTURES / "scan_300dpi.pdf"))

    assert report.features == []
    assert any(w.startswith("no staves found") for w in report.warnings)


@pytest.mark.parametrize(
    ("name", "instrument", "chairs"),
    [
        ("Synthetic Tune Tuba copy", "Tuba", []),
        ("Synthetic Tune Tuba (copy)", "Tuba", []),
        ("Synthetic Tune Tuba.pdf", "Tuba", []),
        ("Synthetic Tune Trombone II", "Trombone", [2]),
        ("Synthetic Tune Tenor sax 1 & 2", "Tenor Sax", [1, 2]),
        ("Synthetic Tune - Trumpet 1 2026", "Trumpet", [1]),
        ("Synthetic Tune Bass Gtr", "Electric Bass", []),
        ("Synthetic Tune AltoSaxes1-2", "Alto Sax", [1, 2]),
        ("Synthetic Tune BariSax", "Baritone Sax", []),
    ],
)
def test_noise_after_the_part_word_and_chair_tokens_do_not_hide_it(tmp_path, name, instrument, chairs):
    report = parse_part(place(tmp_path, "somewhere", name))

    assert (report.part.instrument, report.part.chairs, report.part.instrument_from) == (instrument, chairs, "filename")
    assert report.title == "Synthetic Tune"


def test_the_filename_wins_over_the_folder_even_with_a_copy_suffix(tmp_path):
    report = parse_part(place(tmp_path, "trombone-3", "Synthetic Tune Tuba copy"))

    assert (report.part.instrument, report.part.relation) == ("Tuba", "doubling")
    assert report.part.note == "player slot trombone-3 (Trombone) plays Tuba"


def test_both_chairs_of_a_combined_file_in_one_chairs_folder_are_kept(tmp_path):
    report = parse_part(place(tmp_path, "alto-sax-2", "Synthetic Tune AltoSaxes1-2"))

    assert (report.part.chairs, report.part.relation) == ([1, 2], "same")


@pytest.mark.parametrize(
    ("folder", "name", "relation"),
    [
        ("bass", "Bass Guitar", "same"),  # Bass and Electric Bass are one seat
        ("bass", "Bass Gtr", "same"),
        ("keys", "Keyboard", "same"),
        ("keys", "piano", "doubling"),
        ("keys", "Organ", "doubling"),
        ("piano", "KeyboardSynth", "doubling"),
        ("viola", "Violin", "doubling"),
        ("piano", "Rhythm", "doubling"),  # a generic rhythm part fits any rhythm-section slot
        ("vocals", "piano", "doubling"),  # the vocal score's accompaniment
        ("tenor-sax-2", "Trombone", "unexplained"),
        ("trumpet-3", "Trombone3", "unexplained"),
        ("guitar", "Bass Guitar", "unexplained"),
    ],
)
def test_same_family_pairs_are_never_unexplained_but_cross_family_ones_are(tmp_path, folder, name, relation):
    report = parse_part(place(tmp_path, folder, f"Synthetic Tune {name}"))

    assert report.part.relation == relation
    assert (report.warnings == []) == (relation != "unexplained")


def test_combined_name_reports_its_first_instrument_and_the_others(tmp_path):
    report = parse_part(place(tmp_path, "keys", "Synthetic Tune KeyboardSynth"))

    assert (report.part.instrument, report.part.also) == ("Keyboard", ["Synthesizer"])


def test_right_instrument_in_the_wrong_chair_folder_is_noted_not_warned(tmp_path):
    report = parse_part(place(tmp_path, "trumpet-3", "Synthetic Tune Trpt1"))

    assert report.part.relation == "same"
    assert report.part.note == "player slot trumpet-3 is chair 3; the part is chair 1"
    assert report.warnings == []


def test_time_signature_is_not_a_multi_bar_rest_but_a_real_rest_still_counts(tmp_path):
    report = parse_part(place(tmp_path, "trumpet-1", "Synthetic Tune Trpt1"))

    # The staff holds a staff-sized "44" (meter) and a staff-sized "4" (a four-bar rest).
    assert solos(report)[0] == (1, 6, "A")
    assert "plus 3 bars of multi-bar rests" in " ".join(report.features[0].reasons)


ONE_LINE = FIXTURES / "part_one_line.pdf"


def test_percussion_part_with_one_line_staves_is_read(tmp_path):
    report = parse_part(place(tmp_path, "percussion", "Synthetic Tune Sleigh Bells", ONE_LINE))

    assert report.warnings == []
    assert solos(report) == [(1, 7, "A")]
    assert {f.instrument for f in report.features} == {"Sleigh Bells"}


def test_a_lone_rule_is_no_staff_for_a_non_percussion_part(tmp_path):
    report = parse_part(place(tmp_path, "trumpet-1", "Synthetic Tune Trpt1", ONE_LINE))

    assert report.features == []
    assert any(w.startswith("no staves found") for w in report.warnings)


def test_a_part_given_to_score_mode_behaves_as_before(tmp_path):
    report = parse_score(place(tmp_path, "trumpet-1", "Synthetic Tune Trpt1"))

    assert report.instrumentation == []  # no label column: the score reader finds no instruments
    assert "no instrumentation found: the first system's labels could not be read" in report.warnings


OVERPRINTED = FIXTURES / "part_overprinted_labels.pdf"
UNCONFIRMED = FIXTURES / "part_overprinted_unconfirmed.pdf"


def test_overprinted_staff_start_labels_are_two_numbers_and_the_solo_is_at_its_true_bar(tmp_path):
    # Staff 1 starts at bar 33 and holds rests of 7, 8 and 8 bars; staff 2's number 56 is
    # printed on top of the 33 (from underneath), and the next pair is 60 and 64.
    report = parse_part(place(tmp_path, "violin", "Synthetic Tune - Violin", OVERPRINTED))

    assert [(f.page, f.bar) for f in report.features] == [(1, 56), (1, 65)]  # no solo at bar 33
    reasons = " ".join(report.features[0].reasons)
    assert "overprinted" in reasons and "33" in reasons and "56" in reasons


def test_overprinted_labels_confirmed_by_the_rest_count_keep_full_bar_confidence(tmp_path):
    report = parse_part(place(tmp_path, "violin", "Synthetic Tune - Violin", OVERPRINTED))

    assert [f.confidence for f in report.features] == [0.75, 0.75]  # the same as a plainly counted bar
    assert "not confirmed" not in " ".join(report.features[0].reasons)


def test_overprinted_labels_the_rests_do_not_confirm_keep_the_later_number_with_a_reason(tmp_path):
    # The rests add up to 7 + 8 + 7: 33 + 22 bars is 55, not the 56 printed.
    report = parse_part(place(tmp_path, "violin", "Synthetic Tune - Violin", UNCONFIRMED))

    assert [(f.page, f.bar) for f in report.features] == [(1, 56), (1, 65)]
    first = report.features[0]
    assert first.confidence == 0.7  # 0.05 below a counted bar
    assert "not confirmed by counting the multi-bar rests" in " ".join(first.reasons)
    assert report.features[1].confidence == 0.75  # the later pair (60, 64) still counts out
