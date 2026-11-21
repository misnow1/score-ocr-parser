"""Behaviour fixed after code review, through parse_score and the CLI.

Scores here are drawn at test time from invented text (never committed)."""

import shutil
import subprocess
from pathlib import Path

import pymupdf

from score_parser import parse_score
from score_parser.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"
REPO = Path(__file__).resolve().parent.parent
FULL = ["Alto Saxophone 1", "Trombone 1-4", "Drums"]


def make_score(path, systems, texts=()):
    """systems: [(top_y, labels)]; texts: (page_x, y, string) drawn on page 1."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    for top, labels in systems:
        for i, label in enumerate(labels):
            page.insert_text((30, top + i * 30), label, fontname="china-s" if "–" in label else "helv", fontsize=9)
            page.draw_line((140, top + i * 30), (580, top + i * 30))
    for x, y, text in texts:
        page.insert_text((x, y), text, fontname="helv", fontsize=9)
    doc.save(path)
    return path


def trombone(report):
    return next(e for e in report.instrumentation if e.instrument == "Trombone")


def test_chair_range_accepted_without_space_or_with_en_dash(tmp_path):
    pdf = make_score(
        tmp_path / "a.pdf",
        [(150, FULL), (400, ["A. Sx. 1", "Tbn.1-4", "Dr."])],
    )
    report = parse_score(pdf)
    assert report.warnings == []
    assert trombone(report).chairs == [1, 2, 3, 4]

    pdf = make_score(tmp_path / "b.pdf", [(150, FULL), (400, ["A. Sx. 1", "Tbn 1–4", "Dr."])])
    report = parse_score(pdf)
    assert report.warnings == [] and trombone(report).chairs == [1, 2, 3, 4]


def solo_report(tmp_path, text, labels=FULL, x=300):
    pdf = make_score(tmp_path / "s.pdf", [(150, labels)], [(150, 120, "1"), (x, 138, text)])
    (feature,) = parse_score(pdf).features
    return feature


def test_vocal_word_must_be_tied_to_the_solo_wording(tmp_path):
    tied = solo_report(tmp_path, "Female vocal solo")
    assert tied.instrument == "Vocal"
    loose = solo_report(tmp_path, "Vocal intro then solo")
    assert loose.instrument == "Alto Sax"  # taken from the staff, not the vocal word
    assert loose.confidence < tied.confidence


def test_vocal_inferred_from_male_alone_scores_lower_than_named(tmp_path):
    named = solo_report(tmp_path, "Male vocal solo")
    inferred = solo_report(tmp_path, "Male solo")
    assert inferred.instrument == "Vocal"
    assert inferred.confidence < named.confidence


def test_feature_never_names_an_instrument_the_instrumentation_lacks(tmp_path):
    pdf = make_score(
        tmp_path / "t.pdf",
        [(150, ["Alto Saxophone 1", "Drums"])],
        [(150, 120, "1"), (300, 138, "TBN SOLO")],
    )
    report = parse_score(pdf)
    (feature,) = report.features
    assert feature.instrument != "Trombone"
    assert any("Trombone" in w and "first-system" in w for w in report.warnings)


def test_text_left_of_every_bar_number_lowers_confidence_and_says_so(tmp_path):
    after = solo_report(tmp_path, "ALTO SOLO", x=300)
    before = solo_report(tmp_path, "ALTO SOLO", x=100)  # bar "1" is at x=150
    assert before.bar == after.bar == 1
    assert before.confidence < after.confidence
    assert any("left of every bar" in r for r in before.reasons)


def test_folder_matches_pdf_extension_in_any_case(tmp_path, capsys):
    folder = tmp_path / "scores"
    folder.mkdir()
    shutil.copy(FIXTURES / "finale_solos.pdf", folder / "Upper.PDF")
    out = tmp_path / "out"
    assert main(["parse", str(folder), "--out", str(out)]) == 0
    assert (out / "Upper.json").exists()
    assert "Upper.PDF" in capsys.readouterr().out


def test_two_scores_with_the_same_slug_do_not_overwrite_each_others_draft(tmp_path, capsys):
    folder = tmp_path / "scores"
    folder.mkdir()
    for name in ("First Noel SCORE.pdf", "First Noel 2026.pdf"):
        shutil.copy(FIXTURES / "finale_solos.pdf", folder / name)
    out = tmp_path / "out"
    numbers = FIXTURES / "numbers"
    assert main(["parse", str(folder), "--out", str(out), "--format", "yaml",
                 "--numbers-dir", str(numbers)]) == 0
    assert sorted(p.name for p in out.glob("*.yaml")) == ["first-noel-2.yaml", "first-noel.yaml"]
    assert "already written" in capsys.readouterr().err


def test_parse_run_leaves_git_status_free_of_pdfs_and_images(tmp_path):
    """Outputs land in git-ignored paths; run in a scratch repo with the real .gitignore."""
    work = tmp_path / "work"
    work.mkdir()
    shutil.copy(REPO / ".gitignore", work / ".gitignore")
    subprocess.run(["git", "init", "-q"], cwd=work, check=True)
    shutil.copy(FIXTURES / "finale_solos.pdf", work / "Score.pdf")
    (work / "page.png").write_bytes(b"x")
    assert main(["parse", str(work / "Score.pdf"), "--out", str(work / "out"), "--format", "both"]) == 0
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=work, capture_output=True, text=True, check=True,
    ).stdout
    assert ".pdf" not in status and ".png" not in status and "out/" not in status
