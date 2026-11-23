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
    report = parse_part(place(tmp_path, "AJC 2026", "Synthetic Tune"))

    assert report.part.instrument is None
    assert report.features == []
    assert any("instrument unknown" in w for w in report.warnings)


def test_folder_that_names_no_instrument_is_an_unknown_slot_not_a_disagreement(tmp_path):
    report = parse_part(place(tmp_path, "AJC 2026", "Synthetic Tune - Violin"))

    assert (report.part.instrument, report.part.relation) == ("Violin", "unknown")
    assert report.warnings == []


def test_page_without_drawn_staves_warns_instead_of_reading_nothing_silently(tmp_path):
    report = parse_part(place(tmp_path, "trumpet-1", "Synthetic Tune Trpt1", FIXTURES / "scan_300dpi.pdf"))

    assert report.features == []
    assert any(w.startswith("no staves found") for w in report.warnings)


def test_a_part_given_to_score_mode_behaves_as_before(tmp_path):
    report = parse_score(place(tmp_path, "trumpet-1", "Synthetic Tune Trpt1"))

    assert report.instrumentation == []  # no label column: the score reader finds no instruments
    assert "no instrumentation found: the first system's labels could not be read" in report.warnings
