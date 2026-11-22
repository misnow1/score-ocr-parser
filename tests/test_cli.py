"""Thin smoke tests for the CLI wrapper around parse_score."""

import json
from pathlib import Path

from score_parser.cli import main

PDF = Path(__file__).parent / "fixtures" / "synthetic" / "finale_full_labels.pdf"


def test_parse_writes_json_report_to_output_dir(tmp_path):
    out = tmp_path / "out"

    assert main(["parse", str(PDF), "--out", str(out)]) == 0

    report = json.loads((out / "finale_full_labels.json").read_text())
    assert {i["instrument"] for i in report["instrumentation"]} >= {"Alto Sax", "Drums"}
    assert report["unknown_labels"] == ["Zorblax Section"]


def make_folder(tmp_path):
    folder = tmp_path / "scores"
    folder.mkdir()
    for name in ("finale_full_labels.pdf", "finale_solos.pdf"):
        (folder / name).write_bytes((PDF.parent / name).read_bytes())
    (folder / "broken.pdf").write_bytes(b"not a pdf")
    return folder


def test_folder_run_prints_summary_table_and_reports_a_failing_score(tmp_path, capsys):
    folder = make_folder(tmp_path)
    out = tmp_path / "out"

    assert main(["parse", str(folder), "--out", str(out)]) == 1

    text = capsys.readouterr().out
    lines = text.splitlines()
    header = next(ln for ln in lines if ln.startswith("score"))
    assert header.split() == ["score", "instruments", "features", "warnings"]
    rows = {ln.split()[0]: ln for ln in lines if ln.split() and ln.split()[0].endswith(".pdf")}
    assert set(rows) == {"broken.pdf", "finale_full_labels.pdf", "finale_solos.pdf"}
    assert "FAILED" in rows["broken.pdf"]
    solos = rows["finale_solos.pdf"].split()
    assert solos[2] == "6"  # features column
    # the good scores were still processed after the failure
    assert (out / "finale_solos.json").exists() and (out / "finale_full_labels.json").exists()
    assert not (out / "broken.json").exists()


def test_inspect_prints_to_stdout_and_writes_no_files(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert main(["inspect", str(PDF), "--page", "1", "--tokens"]) == 0
    assert "Saxophone" in capsys.readouterr().out
    assert main(["inspect", str(PDF), "--page", "1", "--layout"]) == 0
    assert "Zorblax Section" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []
