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


@pytest.mark.parametrize("label", ["SATB", "Choir", "Voice Lead", "Voice bck"])
def test_choir_and_voice_labels_are_voice_staves_not_warnings(tmp_path, label):
    pdf = make_score(tmp_path / "s.pdf", [(150, FIRST), (500, [label])])
    report = parse_score(pdf)
    assert report.warnings == [] and report.unknown_labels == []
    assert label not in [lb for e in report.instrumentation for lb in e.labels]


@pytest.mark.parametrize("label", ["VCLS", "A.", "Bar."])
def test_ambiguous_labels_stay_unrecognised(tmp_path, label):
    pdf = make_score(tmp_path / "s.pdf", [(150, FIRST), (500, [label])])
    report = parse_score(pdf)
    assert any(f"'{label}' is not recognised" in w for w in report.warnings)


def test_combined_label_part_recurring_later_is_accepted_without_warning(tmp_path):
    first = ["Alto Saxophone 1", "Trombone 1-4", "Drums", "Piano", "Guitar"]
    systems = [(150, first), (400, ["Trb. 3, Tba."]), (600, ["Trb. 3, Tba."])]
    report = parse_score(make_score(tmp_path / "s.pdf", systems))
    assert report.warnings == []
    assert "Tuba" in chairs(report)


def test_combined_label_with_recurring_part_still_warns_for_chair_outside_first_system(tmp_path):
    first = ["Alto Saxophone 1", "Trombone 1-2", "Drums", "Piano", "Guitar"]
    systems = [(150, first), (400, ["Trb. 3, Tba."]), (600, ["Trb. 3, Tba."])]
    report = parse_score(make_score(tmp_path / "s.pdf", systems))
    assert any("chairs [3]" in w and "Trombone" in w for w in report.warnings)
    assert chairs(report)["Trombone"] == [1, 2]


def test_one_off_combined_label_part_missing_from_first_system_still_warns(tmp_path):
    first = ["Trombone 1-4", "Drums", "Piano"]
    report = parse_score(make_score(tmp_path / "s.pdf", [(150, first), (500, ["Trb. 3, Tba."])]))
    assert any("Tuba" in w and "not in the first-system" in w for w in report.warnings)


def test_chair_range_resolves_from_the_label_itself(tmp_path):
    first = ["Trombone 1-2", "Drums", "Piano"]
    ok = parse_score(make_score(tmp_path / "ok.pdf", [(150, first), (500, ["Trb. 1-2"])]))
    assert ok.warnings == []
    assert chairs(ok)["Trombone"] == [1, 2]
    wide = parse_score(make_score(tmp_path / "wide.pdf", [(150, first), (500, ["Trb. 1-3"])]))
    assert any("chairs [1, 2, 3]" in w for w in wide.warnings)


@pytest.mark.parametrize(
    ("label", "instrument"),
    [
        ("W BL", "Wood Block"),
        ("W. Bl.", "Wood Block"),
        ("Wood Block", "Wood Block"),
        ("C BL", "Cowbell"),
        ("C. Bl.", "Cowbell"),
        ("Cowbell", "Cowbell"),
    ],
)
def test_wood_block_and_cowbell_resolve(tmp_path, label, instrument):
    # Not on the first system: recurring on two later systems, so it joins.
    pdf = make_score(tmp_path / "s.pdf", [(150, FIRST), (400, [label]), (550, [label])])
    report = parse_score(pdf)
    assert instrument in chairs(report)
    assert report.unknown_labels == []


def make_pages(path, pages):
    doc = pymupdf.open()
    for systems in pages:
        page = doc.new_page(width=612, height=792)
        for top, labels in systems:
            for i, label in enumerate(labels):
                page.insert_text((30, top + i * 30), label, fontname="helv", fontsize=9)
                page.draw_line((140, top + i * 30), (580, top + i * 30))
    doc.save(path)
    return path


def test_unrecognised_label_on_several_pages_warns_once_with_page_count(tmp_path):
    pages = [[(150, FIRST)]] + [[(150, ["Kazoo", "Guitar"])] for _ in range(3)]
    report = parse_score(make_pages(tmp_path / "s.pdf", pages))
    hits = [w for w in report.warnings if "'Kazoo' is not recognised" in w]
    assert len(hits) == 1
    assert "3 pages" in hits[0]
    assert report.unknown_labels.count("Kazoo") == 1


def test_capitalised_bass_label_is_an_instrument_not_a_choir_label(tmp_path):
    report = parse_score(make_score(tmp_path / "s.pdf", [(150, FIRST + ["BASS"])]))
    assert "Bass" in chairs(report)
