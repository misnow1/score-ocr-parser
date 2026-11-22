import shutil
from pathlib import Path

import pytest

from score_parser import parse_score

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"


def parse_as(tmp_path, name, fixture="finale_solos.pdf"):
    """Parse a copy of a synthetic fixture under a (messy) filename."""
    path = tmp_path / name
    shutil.copy(FIXTURES / fixture, path)
    return parse_score(path)


@pytest.mark.parametrize(
    "filename, title",
    [
        ("Jingle Bells SCORE.pdf", "Jingle Bells"),
        ("SCORE - Jingle Bells 11-21-2026.pdf", "Jingle Bells"),
        ("Jingle_Bells_AJC 2026 copy.pdf", "Jingle Bells"),
        ("AJC 2026 Jingle Bells (copy 2).pdf", "Jingle Bells"),
        ("Jingle Bells score 2026-11-21 Copy.pdf", "Jingle Bells"),
        ("jingle bells 20261121.pdf", "jingle bells"),
        ("ERGUE A CASA - Piano.pdf", "ERGUE A CASA"),
        ("Jingle Bells - Trumpet 1.pdf", "Jingle Bells"),
        ("Piano Man.pdf", "Piano Man"),
    ],
)
def test_filename_noise_is_removed(tmp_path, filename, title):
    report = parse_as(tmp_path, filename)

    assert report.title == title
    assert report.title_source == "filename"


def test_page_one_large_text_is_the_fallback_when_filename_is_all_noise(tmp_path):
    report = parse_as(tmp_path, "SCORE 2026 copy.pdf", "finale_full_labels.pdf")

    assert report.title == "Synthetic Tune"
    assert report.title_source == "page 1"
