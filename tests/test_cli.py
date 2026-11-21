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


def test_inspect_prints_to_stdout_and_writes_no_files(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert main(["inspect", str(PDF), "--page", "1", "--tokens"]) == 0
    assert "Saxophone" in capsys.readouterr().out
    assert main(["inspect", str(PDF), "--page", "1", "--layout"]) == 0
    assert "Zorblax Section" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []
