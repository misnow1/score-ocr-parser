"""Label column repair, through parse_score on synthetic fixtures."""

from pathlib import Path

from score_parser import parse_score

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"


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


def test_overprinted_labels_are_separated():
    report = parse_score(FIXTURES / "label_repair_overprint.pdf")

    assert {e.instrument for e in report.instrumentation} == {
        "Piccolo",
        "Alto Sax",
        "Tenor Sax",
        "Drums",
    }
    assert report.unknown_labels == []
