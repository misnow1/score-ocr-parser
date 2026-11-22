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


def _name_of(f) -> str | None:
    """A vocal lead has no instrument; facts call it "Vocal"."""
    return "Vocal" if f.kind == "vocal lead" else f.instrument


def _kind_of(f) -> str:
    return "vocal" if _name_of(f) == "Vocal" else "instrument"


def _names_of(f) -> list[str | None]:
    """Every instrument a feature names: the lead one and those sharing it."""
    return [_name_of(f), *(p.instrument for p in getattr(f, "shared_with", []))]


def _located(f, want: dict) -> bool:
    """Exact match on the keys the fact gives: page, bar and rehearsal mark."""
    return all(
        getattr(f, attr) == want[key]
        for key, attr in (("page", "page"), ("bar", "bar"), ("mark", "rehearsal_mark"))
        if key in want
    )


def _open_problem(report, want: dict) -> str | None:
    """An open fact: a feature with no instrument (and no shared ones) at the place."""
    place = ", ".join(f"{k} {want[k]}" for k in ("page", "bar", "mark") if k in want) or "anywhere"
    hits = [
        f for f in report.features
        if f.kind != "vocal lead" and f.instrument is None and not f.shared_with and _located(f, want)
    ]
    return None if hits else f"no open solo (no instrument) at {place}"


def _feature_problem(report, want: dict) -> str | None:
    if want.get("open"):
        return _open_problem(report, want)
    names = want.get("instruments") or [want["instrument"]]
    shared = want.get("kind") == "shared"
    place = ", ".join(f"{k} {want[k]}" for k in ("page", "bar", "mark") if k in want) or "anywhere"
    if shared and len(names) < 2:
        return f"shared feature {names[0]!r} needs several instruments"
    for name in names:
        hits = [f for f in report.features if name in _names_of(f) and _located(f, want)]
        if "voice" in want:
            hits = [f for f in hits if getattr(f, "voice", None) == want["voice"]]
        if "chair" in want:
            hits = [f for f in hits if getattr(f, "chair", None) == want["chair"]]
        if "kind" in want and not shared:
            hits = [f for f in hits if _kind_of(f) == want["kind"]]
        if not hits:
            chair = f" chair {want['chair']}" if "chair" in want else ""
            return f"no {name} feature at {place}{chair}"
    return None


def _absent_problem(report, want: dict) -> str | None:
    hits = [f for f in report.features if want["instrument"] in _names_of(f) and _located(f, want)]
    if not hits:
        return None
    return f"unexpected {want['instrument']} feature at page {hits[0].page} bar {hits[0].bar}"


def _fact_label(fact: dict) -> str:
    name = fact.get("name") or fact.get("instrument") or ("open solo" if fact.get("open") else None) or " + ".join(fact.get("instruments", []))
    return f"fact {name!r}"


def _with_xfail(fact: dict, problem: str | None) -> list[str]:
    """An expected-to-fail fact must keep failing; it is flagged once it passes."""
    reason = fact.get("xfail")
    if not reason:
        return [problem] if problem else []
    return [] if problem else [f"{_fact_label(fact)} now passes; remove its xfail ({reason})"]


def check_facts(report, facts: dict) -> list[str]:
    """Return a list of human-readable mismatches (empty when all facts hold).

    Keys: instruments (names or {name, chairs, xfail}; chairs match exactly); features (exact page, bar, mark,
    kind, chair, voice, one `instrument` or several `instruments`, or `open: true`
    for a feature with no instrument; `xfail: reason`
    marks a known gap); not_features (must be absent); max_features.
    Bars and pages match exactly.
    """
    problems: list[str] = []
    have = {e.instrument: e.chairs for e in report.instrumentation}
    for item in facts.get("instruments", []):
        fact = item if isinstance(item, dict) else {"name": item}
        missing = None
        if fact["name"] not in have:
            missing = f"instrument {fact['name']!r} missing"
        elif "chairs" in fact and have[fact["name"]] != fact["chairs"]:
            missing = f"instrument {fact['name']!r} has chairs {have[fact['name']]}, expected {fact['chairs']}"
        problems += _with_xfail(fact, missing)
    for want in facts.get("features", []):
        problems += _with_xfail(want, _feature_problem(report, want))
    for want in facts.get("not_features", []):
        problems += _with_xfail(want, _absent_problem(report, want))
    cap = facts.get("max_features")
    if cap is not None and len(report.features) > cap:
        problems.append(f"{len(report.features)} features found, at most {cap} expected")
    return problems


@pytest.fixture(scope="module")
def solos_report():
    return parse_score(FIXTURES / "finale_solos.pdf")


def feature_fact(**fact):
    return {"features": [fact]}


def test_facts_checker_passes_and_fails_on_a_synthetic_score(solos_report):
    good = {"instruments": ["Alto Sax"], "features": [{"instrument": "Alto Sax", "page": 1, "bar": 29}]}
    bad = {"instruments": ["Tuba"], "features": [{"instrument": "Alto Sax", "page": 1, "bar": 90}]}
    assert check_facts(solos_report, good) == []
    assert len(check_facts(solos_report, bad)) == 2


def test_bar_is_exact_with_no_tolerance(solos_report):
    assert check_facts(solos_report, feature_fact(instrument="Alto Sax", bar=29)) == []
    assert check_facts(solos_report, feature_fact(instrument="Alto Sax", bar=30))
    assert check_facts(solos_report, feature_fact(instrument="Alto Sax", bar=28))


def test_page_must_match_exactly(solos_report):
    assert check_facts(solos_report, feature_fact(instrument="Alto Sax", page=1, bar=29)) == []
    assert check_facts(solos_report, feature_fact(instrument="Alto Sax", page=2, bar=29))


def test_rehearsal_mark_must_match(solos_report):
    assert check_facts(solos_report, feature_fact(instrument="Alto Sax", mark="B")) == []
    assert check_facts(solos_report, feature_fact(instrument="Alto Sax", mark="C"))


def test_kind_distinguishes_instrument_and_vocal(solos_report):
    assert check_facts(solos_report, feature_fact(instrument="Vocal", kind="vocal")) == []
    assert check_facts(solos_report, feature_fact(instrument="Alto Sax", kind="instrument")) == []
    assert check_facts(solos_report, feature_fact(instrument="Alto Sax", kind="vocal"))
    assert check_facts(solos_report, feature_fact(instrument="Vocal", kind="instrument"))


def test_vocal_lead_fact_matches_by_voice_and_location():
    report = parse_score(FIXTURES / "finale_vocal_leads.pdf")
    fact = {"instrument": "Vocal", "kind": "vocal", "page": 1, "bar": 1, "mark": "B"}
    assert check_facts(report, feature_fact(**fact, voice="female")) == []
    assert check_facts(report, feature_fact(**fact, voice="male")) == []
    assert check_facts(report, feature_fact(**{**fact, "page": 2}, voice="female"))
    assert check_facts(report, feature_fact(instrument="Vocal", kind="vocal", voice="female", page=1, bar=1, mark="C"))


def test_open_fact_needs_a_feature_with_no_instrument():
    report = parse_score(FIXTURES / "finale_folded_solos.pdf")

    assert check_facts(report, feature_fact(open=True, page=1, bar=9)) == []
    assert check_facts(report, feature_fact(open=True, page=1, bar=17))  # no feature there
    assert check_facts(report, feature_fact(open=True, page=2, bar=25))  # that one has an instrument


def test_shared_feature_needs_every_listed_instrument_at_the_same_place(solos_report):
    shared = {"instruments": ["Vocal", "Drums"], "kind": "shared", "page": 2, "bar": 33}
    assert check_facts(solos_report, {"features": [shared]}) == []
    apart = {"instruments": ["Alto Sax", "Drums"], "kind": "shared", "page": 2, "bar": 33}
    assert check_facts(solos_report, {"features": [apart]})
    assert check_facts(solos_report, feature_fact(instrument="Drums", kind="shared"))


def test_chair_fact_must_match_the_reported_chair(solos_report):
    assert check_facts(solos_report, feature_fact(instrument="Alto Sax", chair=1)) == []
    assert check_facts(solos_report, feature_fact(instrument="Alto Sax", chair=2))
    assert check_facts(solos_report, feature_fact(instrument="Drums", chair=1))  # reported no chair


def test_max_features_caps_the_feature_count(solos_report):
    assert check_facts(solos_report, {"max_features": len(solos_report.features)}) == []
    assert check_facts(solos_report, {"max_features": len(solos_report.features) - 1})


def test_features_that_must_be_absent(solos_report):
    assert check_facts(solos_report, {"not_features": [{"instrument": "Alto Sax", "page": 5}]}) == []
    assert check_facts(solos_report, {"not_features": [{"instrument": "Alto Sax", "page": 1}]})


def test_expected_to_fail_fact_is_tolerated_until_it_starts_passing(solos_report):
    wrong = feature_fact(instrument="Alto Sax", bar=44, xfail="known wrong bar")
    assert check_facts(solos_report, wrong) == []
    right = feature_fact(instrument="Alto Sax", bar=29, xfail="stale reason")
    problems = check_facts(solos_report, right)
    assert len(problems) == 1 and "now passes" in problems[0]


def test_expected_to_fail_applies_to_instruments_and_absent_features(solos_report):
    assert check_facts(solos_report, {"instruments": [{"name": "Tuba", "xfail": "not found yet"}]}) == []
    gone = {"not_features": [{"instrument": "Alto Sax", "page": 1, "xfail": "false positive"}]}
    assert check_facts(solos_report, gone) == []


def test_instrument_chairs_match_exactly(solos_report):
    chairs = next(e.chairs for e in solos_report.instrumentation if e.instrument == "Alto Sax")
    assert check_facts(solos_report, {"instruments": [{"name": "Alto Sax", "chairs": chairs}]}) == []
    wrong = {"instruments": [{"name": "Alto Sax", "chairs": [*chairs, 9]}]}
    assert "chairs" in check_facts(solos_report, wrong)[0]


def test_expected_facts_file_loads_and_each_entry_is_well_formed():
    expected = load_expected()
    assert isinstance(expected, dict)
    for stem, facts in expected.items():
        for want in facts.get("features", []) + facts.get("not_features", []):
            assert "instrument" in want or "instruments" in want or want.get("open"), f"{stem}: {want}"
            if "xfail" in want:
                assert want["xfail"], f"{stem}: xfail needs a reason"


@needs_corpus
def test_every_corpus_score_parses_without_crashing():
    pdfs = sorted(p for p in Path(CORPUS_DIR).iterdir() if p.suffix.lower() == ".pdf")
    assert pdfs, f"no PDFs in {CORPUS_DIR}"
    for pdf in pdfs:
        parse_score(pdf)


@needs_corpus
@pytest.mark.parametrize("stem", sorted(load_expected()))
def test_corpus_score_matches_approved_facts(stem):
    pdf = Path(CORPUS_DIR) / f"{stem}.pdf"
    assert pdf.exists(), f"{pdf.name} not found in SCORE_CORPUS_DIR"
    assert check_facts(parse_score(pdf), load_expected()[stem]) == []
