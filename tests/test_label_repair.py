"""Label column repair, through parse_score on synthetic fixtures."""

import sys
from pathlib import Path

import pytest

from score_parser import parse_score

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"
macos_only = pytest.mark.skipif(sys.platform != "darwin", reason="Apple Vision OCR is macOS-only")


def labels_of(report):
    return {label for e in report.instrumentation for label in e.labels}


def test_dropped_labels_are_recovered_and_group_labels_are_not_staves():
    report = parse_score(FIXTURES / "label_repair_missing.pdf")

    assert {"A. Sx. I & II", "T. Sx. I & II", "1&2 B Tpt."} <= labels_of(report)
    assert report.unknown_labels == []
    assert report.warnings == []  # "TBNS" would be an unrecognised label on every page


def test_feel_cue_and_only_notes_are_not_staves():
    report = parse_score(FIXTURES / "label_repair_noise.pdf")

    assert report.unknown_labels == []
    assert report.warnings == []  # no false staves-vs-labels warning either
    (solo,) = report.features
    assert solo.instrument == "Alto Sax"
    assert solo.rehearsal_mark == "A"  # the feel line no longer hides mark A


def test_unlabeled_staff_warns_and_title_text_is_not_a_staff_label():
    report = parse_score(FIXTURES / "label_repair_unlabeled.pdf")

    assert any("no label" in w and "Page 1" in w for w in report.warnings)
    assert "Piano" not in {e.instrument for e in report.instrumentation}


def chairs_of(report):
    return {e.instrument: e.chairs for e in report.instrumentation}


def test_misread_chair_one_bar_number_and_later_chair_are_repaired():
    report = parse_score(FIXTURES / "label_repair_ocr_misreads.pdf")

    # "TRUMPETI" and "TENOR SAXI" are chair 1; "TROMBONE 29" is a bar number, not a chair;
    # the later page's full-name "TRUMPET 4" and "TROMBONE 4" join their sections.
    assert chairs_of(report) == {"Tenor Sax": [1], "Trumpet": [1, 2, 3, 4], "Trombone": [1, 2, 3, 4]}
    assert report.unknown_labels == []
    assert report.warnings == []


@macos_only
def test_scanned_misread_labels_are_repaired():
    report = parse_score(FIXTURES / "scan_label_misreads.pdf")

    assert report.pages[0].source == "ocr"
    assert chairs_of(report)["Trumpet"] == [1, 2, 3]
    assert 29 not in chairs_of(report)["Trombone"]


def test_overprinted_labels_are_separated():
    report = parse_score(FIXTURES / "label_repair_overprint.pdf")

    assert {e.instrument for e in report.instrumentation} == {
        "Piccolo",
        "Alto Sax",
        "Tenor Sax",
        "Drums",
    }
    assert report.unknown_labels == []
