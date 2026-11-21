import subprocess
import sys
from pathlib import Path

import pytest

from score_parser import ParseOptions, parse_score

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"


def by_name(report):
    return {i.instrument: i for i in report.instrumentation}


def test_full_labels_resolve_to_canonical_instruments():
    report = parse_score(FIXTURES / "finale_full_labels.pdf")

    found = by_name(report)
    assert set(found) == {
        "Alto Sax",
        "Tenor Sax",
        "Trumpet",
        "Trombone",
        "Piano",
        "Bass",
        "Drums",
    }
    assert found["Alto Sax"].chairs == [1]
    assert found["Trumpet"].chairs == [1, 2, 3, 4]
    assert found["Trombone"].chairs == [1, 2, 3, 4]


def test_unknown_labels_are_reported_not_guessed():
    report = parse_score(FIXTURES / "finale_full_labels.pdf")

    assert report.unknown_labels == ["Zorblax Section"]
    assert "Zorblax Section" not in {l for i in report.instrumentation for l in i.labels}


def test_music_glyphs_never_become_labels_and_page_source_is_text():
    report = parse_score(FIXTURES / "finale_full_labels.pdf")

    labels = report.unknown_labels + [l for i in report.instrumentation for l in i.labels]
    assert labels and all(ord(c) < 0xE000 for l in labels for c in l)
    assert [(p.page, p.source) for p in report.pages] == [(1, "text")]


def all_labels(report):
    return report.unknown_labels + [l for i in report.instrumentation for l in i.labels]


def test_sibelius_opus_glyphs_are_dropped_by_font_name():
    report = parse_score(FIXTURES / "sibelius_abbreviated.pdf")

    labels = all_labels(report)
    assert labels
    assert not any("?" in l or l.rstrip().endswith("&") for l in labels)
    assert "Trombone 1-4" in labels


def test_chair_ranges_expand_including_roman_numerals():
    found = by_name(parse_score(FIXTURES / "sibelius_abbreviated.pdf"))

    assert found["Alto Sax"].chairs == [1, 2]
    assert found["Trumpet"].chairs == [1, 2, 3, 4]
    assert found["Flute"].chairs == [1, 2, 3]
    assert found["Guitar"].chairs == [1, 2]


def test_non_standard_instruments_are_recognised():
    report = parse_score(FIXTURES / "sibelius_nonstandard.pdf")

    assert set(by_name(report)) == {
        "Violin",
        "Viola",
        "Cello",
        "Organ",
        "Lead Vocal",
        "Flugelhorn",
    }
    assert report.unknown_labels == []


def test_doublings_come_from_labels_and_instruction_text_not_mutes():
    found = by_name(parse_score(FIXTURES / "sibelius_abbreviated.pdf"))

    assert found["Flute"].doublings == ["Oboe"]
    assert found["Alto Sax"].doublings == ["Flute"]
    assert found["Trumpet"].doublings == ["Piccolo Trumpet"]
    assert found["Trombone"].doublings == []


def test_abbreviated_labels_on_later_systems_agree_with_first_system():
    report = parse_score(FIXTURES / "sibelius_abbreviated.pdf")

    found = by_name(report)
    assert set(found) == {
        "Flute", "Alto Sax", "Trumpet", "Trombone", "Guitar", "Electric Bass", "Drums",
    }
    assert "E.B." in found["Electric Bass"].labels
    assert "D. S." in found["Drums"].labels
    assert report.warnings == []
    assert report.unknown_labels == []


def test_later_systems_that_disagree_with_first_system_raise_warnings():
    report = parse_score(FIXTURES / "sibelius_mismatch.pdf")

    text = "\n".join(report.warnings)
    assert "Tbn. 1-5" in text
    assert "Vln." in text
    assert "Zork." in text
    assert "Zork." in report.unknown_labels
    assert "Violin" not in by_name(report)


# Scanned pages go through Apple Vision OCR, which only exists on macOS.
macos_only = pytest.mark.skipif(sys.platform != "darwin", reason="Apple Vision OCR is macOS-only")


@macos_only
def test_image_only_page_is_routed_to_ocr_and_resolves_instruments():
    report = parse_score(FIXTURES / "scan_300dpi.pdf")

    page = report.pages[0]
    assert page.source == "ocr"
    assert page.ocr_confidence is not None and page.ocr_confidence > 0.5
    found = by_name(report)
    assert {"Alto Sax", "Tenor Sax", "Trumpet", "Trombone", "Piano"} <= set(found)
    assert found["Trumpet"].chairs == [1, 2, 3, 4]
    assert report.warnings == []


@macos_only
def test_low_dpi_scan_warns():
    report = parse_score(FIXTURES / "scan_90dpi.pdf")

    assert report.pages[0].source == "ocr"
    assert any("dpi" in w and "page 1" in w for w in report.warnings)


@macos_only
def test_force_ocr_overrides_detection_on_text_pdf():
    auto = parse_score(FIXTURES / "finale_full_labels.pdf")
    forced = parse_score(FIXTURES / "finale_full_labels.pdf", ParseOptions(force_ocr=True))

    assert auto.pages[0].source == "text"
    assert forced.pages[0].source == "ocr"
    assert forced.pages[0].ocr_confidence is not None


def test_text_layer_path_does_not_import_macos_modules():
    code = (
        "import sys; from score_parser import parse_score; "
        f"parse_score({str(FIXTURES / 'finale_full_labels.pdf')!r}); "
        "sys.exit(any(m in sys.modules for m in ('Vision', 'Quartz', 'objc')))"
    )
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


@macos_only
def test_pattern_fill_scan_is_rendered_and_ocrd():
    report = parse_score(FIXTURES / "scan_pattern.pdf")

    page = report.pages[0]
    assert page.source == "ocr"
    assert page.reason == "pattern"
    assert {"Alto Sax", "Trumpet", "Piano"} <= set(by_name(report))
    assert report.warnings == []


def test_text_page_reports_text_reason():
    report = parse_score(FIXTURES / "finale_full_labels.pdf")

    assert report.pages[0].reason == "text"


def test_empty_page_and_empty_instrumentation_warn(tmp_path, monkeypatch):
    import types

    import pymupdf

    blank = tmp_path / "blank.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(blank)
    # OCR is macOS-only; stand in for it so this runs everywhere.
    stub = types.SimpleNamespace(recognise=lambda png, rect, page: [])
    monkeypatch.setitem(sys.modules, "score_parser.ocr", stub)

    report = parse_score(blank)

    assert report.pages[0].source == "ocr"
    assert report.pages[0].reason == "empty"
    assert any("page 1" in w and "no text" in w for w in report.warnings)
    assert any("instrumentation" in w for w in report.warnings)
