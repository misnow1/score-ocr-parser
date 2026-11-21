"""Instrument abbreviations on later systems resolve through parse_score."""

import pymupdf
import pytest

from score_parser import parse_score

FIRST = [
    "Guitar",
    "Double Bass",
    "Trombone 1-4",
    "Tuba",
    "Soprano Saxophone",
    "Synthesizer",
    "Sleigh Bells",
    "Lead Vocal",
    "Acoustic Guitar",
]


def make_score(path, systems):
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    for top, labels in systems:
        for i, label in enumerate(labels):
            page.insert_text((30, top + i * 30), label, fontname="helv", fontsize=9)
            page.draw_line((140, top + i * 30), (580, top + i * 30))
    doc.save(path)
    return path


def chairs(report):
    return {e.instrument: e.chairs for e in report.instrumentation}


@pytest.mark.parametrize(
    ("label", "instrument"),
    [
        ("Gtrs.", "Guitar"),
        ("Db.", "Bass"),
        ("Synth.", "Synthesizer"),
        ("Sop. Sax.", "Soprano Sax"),
        ("S.Bells", "Sleigh Bells"),
        ("VCLS", "Lead Vocal"),
        ("Guitars", "Guitar"),
        ("Ac. Gtr.", "Guitar"),
    ],
)
def test_abbreviation_resolves_to_canonical_instrument(tmp_path, label, instrument):
    pdf = make_score(tmp_path / "s.pdf", [(150, FIRST), (500, [label])])
    report = parse_score(pdf)
    assert not any("not recognised" in w for w in report.warnings)
    assert instrument in chairs(report)
    assert report.unknown_labels == []


def test_trb_abbreviation_with_chair_range(tmp_path):
    pdf = make_score(tmp_path / "s.pdf", [(150, FIRST), (500, ["Trb. 1-2"])])
    report = parse_score(pdf)
    assert report.warnings == []
    assert chairs(report)["Trombone"] == [1, 2, 3, 4]


def test_combined_label_resolves_to_both_parts(tmp_path):
    pdf = make_score(tmp_path / "s.pdf", [(150, FIRST), (500, ["Trb. 3, Tba."])])
    report = parse_score(pdf)
    assert report.warnings == []
    assert report.unknown_labels == []
    assert chairs(report)["Trombone"] == [1, 2, 3, 4]
    tuba = next(e for e in report.instrumentation if e.instrument == "Tuba")
    assert "Trb. 3, Tba." in tuba.labels


def test_combined_label_chair_outside_first_system_warns(tmp_path):
    first = ["Trombone 1-2", "Tuba", "Drums", "Piano"]
    pdf = make_score(tmp_path / "s.pdf", [(150, first), (500, ["Trb. 3, Tba."])])
    report = parse_score(pdf)
    assert any("chairs [3]" in w for w in report.warnings)


def test_combined_label_with_unknown_part_stays_unrecognised(tmp_path):
    pdf = make_score(tmp_path / "s.pdf", [(150, FIRST), (500, ["Trb. 3, Zzz."])])
    report = parse_score(pdf)
    assert any("not recognised" in w for w in report.warnings)


@pytest.mark.parametrize("label", ["SATB", "Choir", "Voice Lead", "Voice bck", "A.", "Bar."])
def test_choir_and_ambiguous_labels_stay_unrecognised(tmp_path, label):
    pdf = make_score(tmp_path / "s.pdf", [(150, FIRST), (500, [label])])
    report = parse_score(pdf)
    assert any(f"'{label}' is not recognised" in w for w in report.warnings)
