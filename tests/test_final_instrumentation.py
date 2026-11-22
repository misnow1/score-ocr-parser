"""Features and doubling instructions use the final instrumentation: variants,
recurring instruments and every part of a combined label."""

import pymupdf

from score_parser import parse_score

FIRST = ["Alto Saxophone 1", "Electric Bass", "Trombone 1-4", "Tuba", "Drums"]


def make_score(path, systems):
    """systems: (top, labels, texts); texts are (x, y, string) drawn beside the staves."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    for top, labels, texts in systems:
        for i, label in enumerate(labels):
            page.insert_text((30, top + i * 30), label, fontname="helv", fontsize=9)
            page.draw_line((140, top + i * 30), (580, top + i * 30))
        for x, y, text in texts:
            page.insert_text((x, y), text, fontname="helv", fontsize=9)
    doc.save(path)
    return path


def solos(report):
    return [(f.instrument, f.raw_text) for f in report.features]


def entry(report, name):
    return next(e for e in report.instrumentation if e.instrument == name)


def test_bass_solo_is_kept_when_the_instrumentation_has_electric_bass(tmp_path):
    pdf = make_score(tmp_path / "s.pdf", [(150, FIRST, [(300, 175, "BASS SOLO")])])
    report = parse_score(pdf)
    assert solos(report) == [("Electric Bass", "BASS SOLO")]
    assert report.warnings == []


def test_solo_on_a_recurring_later_only_instrument_is_kept(tmp_path):
    later = ["Gtr. 2", "Dr."]
    systems = [
        (150, FIRST, []),
        (400, later, [(300, 395, "GUITAR SOLO")]),
        (600, later, []),
    ]
    report = parse_score(make_score(tmp_path / "s.pdf", systems))
    assert solos(report) == [("Guitar", "GUITAR SOLO")]
    assert report.warnings == []


def test_solo_above_a_variant_staff_with_a_stray_chair_keeps_the_instrument(tmp_path):
    systems = [(150, FIRST, []), (400, ["Bass 2"], [(300, 395, "Solo")])]
    report = parse_score(make_score(tmp_path / "s.pdf", systems))
    assert solos(report) == [("Electric Bass", "Solo")]
    assert any("chairs [2]" in w for w in report.warnings)


def test_solo_above_a_combined_label_staff_does_not_guess_a_part(tmp_path):
    systems = [(150, FIRST, []), (400, ["Trb. 1, Tba."], [(300, 395, "Solo")])]
    report = parse_score(make_score(tmp_path / "s.pdf", systems))
    assert solos(report) == [(None, "Solo")]
    assert report.warnings == []


def test_doubling_instruction_next_to_a_variant_label_reaches_the_entry(tmp_path):
    systems = [(150, FIRST, []), (400, ["Bass"], [(300, 400, "to Flute")])]
    report = parse_score(make_score(tmp_path / "s.pdf", systems))
    assert entry(report, "Electric Bass").doublings == ["Flute"]


def test_doubling_instruction_next_to_a_combined_label_reaches_its_parts(tmp_path):
    systems = [(150, FIRST, []), (400, ["Trb. 3, Tba."], [(300, 400, "to Flute")])]
    report = parse_score(make_score(tmp_path / "s.pdf", systems))
    assert entry(report, "Trombone").doublings == ["Flute"]
    assert entry(report, "Tuba").doublings == ["Flute"]
