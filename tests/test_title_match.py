"""--numbers-dir: match score titles to planner number slugs and name the draft."""

import shutil
from pathlib import Path

import pytest

from score_parser import ParseOptions, parse_score
from score_parser.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"
NUMBERS = FIXTURES / "numbers"  # synthetic stand-ins for planner number files


def score_named(tmp_path, name):
    path = tmp_path / "in" / name
    path.parent.mkdir(exist_ok=True)
    shutil.copy(FIXTURES / "finale_solos.pdf", path)
    return path


@pytest.mark.parametrize(
    "filename, slug",
    [
        ("First Noel SCORE.pdf", "first-noel"),
        ("The First Nowell - score 2026.pdf", "first-noel"),  # known alias
        ("Super Christmas AJC 2026.pdf", "superstition"),  # known alias
        ("Jingle Bels copy.pdf", "jingle-bells"),  # typo
        ("Bleak Midwinter.pdf", "in-the-bleak-midwinter"),
    ],
)
def test_title_matches_planner_slug_including_aliases_and_typos(tmp_path, filename, slug):
    report = parse_score(score_named(tmp_path, filename), ParseOptions(numbers_dir=NUMBERS))

    assert report.matched_slug == slug
    assert report.draft_name == slug


def test_without_numbers_dir_nothing_is_matched(tmp_path):
    report = parse_score(score_named(tmp_path, "First Noel.pdf"))

    assert report.matched_slug is None
    assert report.draft_name == "first-noel"


def test_draft_file_is_named_for_the_matched_slug(tmp_path):
    pdf = score_named(tmp_path, "The First Nowell SCORE.pdf")
    out = tmp_path / "out"

    assert main(["parse", str(pdf), "--out", str(out), "--format", "both",
                 "--numbers-dir", str(NUMBERS)]) == 0

    assert (out / "first-noel.yaml").exists()
    assert (out / "The First Nowell SCORE.json").exists()


def test_no_match_leaves_a_clearly_labelled_unmatched_draft(tmp_path):
    pdf = score_named(tmp_path, "Zorblax Rhapsody SCORE.pdf")
    out = tmp_path / "out"

    main(["parse", str(pdf), "--out", str(out), "--format", "yaml", "--numbers-dir", str(NUMBERS)])

    draft = out / "UNMATCHED-zorblax-rhapsody.yaml"
    assert "UNMATCHED" in draft.read_text().splitlines()[0]
    assert parse_score(pdf, ParseOptions(numbers_dir=NUMBERS)).matched_slug is None


def test_tool_refuses_to_write_into_the_numbers_dir(tmp_path):
    numbers = tmp_path / "numbers"
    shutil.copytree(NUMBERS, numbers)
    before = sorted(p.name for p in numbers.iterdir())
    pdf = score_named(tmp_path, "First Noel.pdf")

    code = main(["parse", str(pdf), "--out", str(numbers), "--format", "both",
                 "--numbers-dir", str(numbers)])

    assert code != 0
    assert sorted(p.name for p in numbers.iterdir()) == before
