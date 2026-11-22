"""Flow draft: planner `numbers/*.yaml` flow shape, via parse_score and `parse` output."""

from pathlib import Path

import yaml

from score_parser import parse_score
from score_parser.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"
SOLOS = FIXTURES / "finale_solos.pdf"


def written_yaml(tmp_path, *extra, pdf=SOLOS):
    out = tmp_path / "out"
    assert main(["parse", str(pdf), "--out", str(out), "--format", "yaml", *extra]) == 0
    (path,) = out.glob("*.yaml")
    return path, path.read_text()


def test_each_feature_becomes_a_step_with_section_instrument_and_location_note(tmp_path):
    _, text = written_yaml(tmp_path)

    flow = yaml.safe_load(text)["flow"]
    assert len(flow) == len(parse_score(SOLOS).features) == 6
    for step in flow:
        assert set(step) == {"section", "instrument", "note"}
    alto = next(s for s in flow if s["instrument"] == "alto sax")
    assert alto["section"] == "Alto Sax solo (B)"
    assert "page 1" in alto["note"] and "bar 29" in alto["note"]
    assert "rehearsal B" in alto["note"] and "confidence 0.9" in alto["note"]


def test_low_confidence_steps_carry_todo_comments_and_confident_ones_do_not(tmp_path):
    _, text = written_yaml(tmp_path)

    report = parse_score(SOLOS)
    low = [f for f in report.features if f.confidence < 0.8]
    assert 0 < len(low) < len(report.features)
    assert text.count("# TODO(score-parser)") == len(low)
    assert "TODO" not in next(ln for ln in text.splitlines() if "Alto Sax solo" in ln)


def test_draft_never_sets_kind_or_position(tmp_path):
    _, text = written_yaml(tmp_path)

    data = yaml.safe_load(text)
    assert "kind" not in data
    for step in data["flow"]:
        assert "kind" not in step and "position" not in step
    assert not any(f"DS{n}" in text for n in range(1, 6))


def test_yaml_is_written_only_when_asked_and_json_alongside_with_both(tmp_path):
    out = tmp_path / "out"
    main(["parse", str(SOLOS), "--out", str(out)])
    assert [p.suffix for p in out.iterdir()] == [".json"]

    main(["parse", str(SOLOS), "--out", str(out), "--format", "both"])
    assert sorted(p.suffix for p in out.iterdir()) == [".json", ".yaml"]
