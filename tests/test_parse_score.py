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
