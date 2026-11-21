"""Opt-in corpus tests against the real local score folder.

Skipped unless SCORE_CORPUS_DIR points at a folder of score PDFs. Never run in
CI. The scores are read in place; nothing from them is written anywhere.
Expected facts live in expected.yaml and hold no music content.
"""

import os
from pathlib import Path

import pytest
import yaml

from score_parser import parse_score

EXPECTED = Path(__file__).with_name("expected.yaml")
FIXTURES = Path(__file__).parents[1] / "fixtures" / "synthetic"
CORPUS_DIR = os.environ.get("SCORE_CORPUS_DIR")

needs_corpus = pytest.mark.skipif(not CORPUS_DIR, reason="SCORE_CORPUS_DIR is not set")


def load_expected(path: Path = EXPECTED) -> dict:
    return (yaml.safe_load(path.read_text()) or {}).get("scores") or {}


def check_facts(report, facts: dict) -> list[str]:
    """Return a list of human-readable mismatches (empty when all facts hold)."""
    problems = []
    have = {e.instrument for e in report.instrumentation}
    for name in facts.get("instruments", []):
        if name not in have:
            problems.append(f"instrument {name!r} missing")
    for want in facts.get("features", []):
        tol = want.get("tolerance", 0)
        hit = any(
            f.instrument == want["instrument"] and f.bar is not None and abs(f.bar - want["bar"]) <= tol
            for f in report.features
        )
        if not hit:
            problems.append(f"no {want['instrument']} feature within {tol} bars of {want['bar']}")
    return problems


def test_facts_checker_passes_and_fails_on_a_synthetic_score():
    report = parse_score(FIXTURES / "finale_solos.pdf")

    good = {"instruments": ["Alto Sax"], "features": [{"instrument": "Alto Sax", "bar": 30, "tolerance": 2}]}
    bad = {"instruments": ["Tuba"], "features": [{"instrument": "Alto Sax", "bar": 90, "tolerance": 2}]}
    assert check_facts(report, good) == []
    assert len(check_facts(report, bad)) == 2


def test_expected_facts_file_loads_as_a_mapping():
    # Ships as an empty placeholder; approved facts are added by hand.
    assert isinstance(load_expected(), dict)


@needs_corpus
def test_every_corpus_score_parses_without_crashing():
    pdfs = sorted(Path(CORPUS_DIR).glob("*.pdf"))
    assert pdfs, f"no PDFs in {CORPUS_DIR}"
    for pdf in pdfs:
        parse_score(pdf)


@needs_corpus
@pytest.mark.parametrize("stem", sorted(load_expected()))
def test_corpus_score_matches_approved_facts(stem):
    pdf = Path(CORPUS_DIR) / f"{stem}.pdf"
    assert pdf.exists(), f"{pdf.name} not found in SCORE_CORPUS_DIR"
    assert check_facts(parse_score(pdf), load_expected()[stem]) == []
