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
    """Exact match on the keys the fact gives: page, bar and rehearsal mark
    (`section` is the same mark: the one the flow draft groups by)."""
    return all(
        getattr(f, attr) == want[key]
        for key, attr in (("page", "page"), ("bar", "bar"), ("mark", "rehearsal_mark"), ("section", "rehearsal_mark"))
        if key in want
    )


_PLACE_KEYS = ("page", "bar", "mark", "section")


def _place(want: dict) -> str:
    return ", ".join(f"{k} {want[k]}" for k in _PLACE_KEYS if k in want) or "anywhere"


def _open_problem(report, want: dict) -> str | None:
    """An open fact: a feature with no instrument (and no shared ones) at the place."""
    place = _place(want)
    hits = [
        f for f in report.features
        if f.kind != "vocal lead" and f.instrument is None and not f.shared_with and _located(f, want)
    ]
    return None if hits else f"no open solo (no instrument) at {place}"


def _matches(report, name: str, want: dict) -> list[int]:
    """Indices (in report order) of the features named `name` that meet the fact's keys."""
    shared = want.get("kind") == "shared"
    hits = [(i, f) for i, f in enumerate(report.features) if name in _names_of(f) and _located(f, want)]
    if "voice" in want:
        hits = [(i, f) for i, f in hits if getattr(f, "voice", None) == want["voice"]]
    if "chair" in want:
        hits = [(i, f) for i, f in hits if getattr(f, "chair", None) == want["chair"]]
    if "kind" in want and not shared:
        hits = [(i, f) for i, f in hits if _kind_of(f) == want["kind"]]
    return [i for i, _ in hits]


def _feature_problem(report, want: dict) -> str | None:
    if want.get("open"):
        return _open_problem(report, want)
    names = want.get("instruments") or [want["instrument"]]
    shared = want.get("kind") == "shared"
    place = _place(want)
    if shared and len(names) < 2:
        return f"shared feature {names[0]!r} needs several instruments"
    for name in names:
        if not _matches(report, name, want):
            chair = f" chair {want['chair']}" if "chair" in want else ""
            return f"no {name} feature at {place}{chair}"
    return None


_ORDER_REJECTED = ("instruments", "open", "xfail")


def shape_problems(facts: dict) -> list[str]:
    """Facts that are malformed rather than unmet: an `order` entry must name
    one instrument (it takes no `instruments`, `open`, `kind: shared` or
    `xfail`: a chain of entries cannot be partly expected to fail), and a
    fact giving both `mark` and `section` must give the same value."""
    problems = []
    for want in facts.get("features", []) + facts.get("not_features", []) + facts.get("order", []):
        if "mark" in want and "section" in want and want["mark"] != want["section"]:
            problems.append(f"fact {want}: mark and section are the same key and differ")
    for want in facts.get("order", []):
        if "instrument" not in want:
            problems.append(f"order entry {want} needs an instrument")
        for key in _ORDER_REJECTED:
            if key in want:
                problems.append(f"order entry {want} takes no {key!r}")
        if want.get("kind") == "shared":
            problems.append(f"order entry {want} takes no kind 'shared'")
    return problems


def _order_problem(report, entries: list[dict]) -> str | None:
    """Each entry must match a feature later in the report than the one before
    (the first match after it; other features may sit between). An entry names
    one instrument, plus page, bar, mark or section, chair, kind, voice; a
    feature shared by several instruments matches by any of them."""
    after = -1
    previous = None
    for want in entries:
        name = want["instrument"]
        found = _matches(report, name, want)
        where = f"{name} at {_place(want)}"
        if not found:
            return f"order: no {where} feature"
        later = [i for i in found if i > after]
        if not later:
            return f"order: no {where} feature after {previous}"
        after, previous = later[0], where
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

    Keys: instruments (names or {name, chairs, xfail}; chairs match exactly); features (exact page, bar, mark
    (or `section`, the same mark), kind, chair, voice, one `instrument` or several `instruments`, or `open: true`
    for a feature with no instrument; `xfail: reason`
    marks a known gap); not_features (must be absent); order (single-instrument feature
    entries that must appear in this order in the report, not necessarily adjacent;
    the report is in score order, so this asserts order without exact bars); max_features.
    Bars and pages match exactly.
    """
    problems: list[str] = shape_problems(facts)
    if problems:
        return problems
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
    problem = _order_problem(report, facts.get("order", []))
    if problem:
        problems.append(problem)
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


def test_section_key_is_the_rehearsal_mark_the_flow_groups_by():
    report = parse_score(FIXTURES / "finale_mark_carry.pdf")

    assert check_facts(report, feature_fact(instrument="Guitar", section="A")) == []  # carried from page 1
    assert check_facts(report, feature_fact(instrument="Guitar", section="B"))
    assert check_facts(report, feature_fact(instrument="Drums", section="B", page=3)) == []


def test_order_fact_needs_features_in_that_relative_order():
    report = parse_score(FIXTURES / "finale_score_order.pdf")  # Guitar, Alto Sax, Trombone, Trumpet

    ordered = {"order": [{"instrument": "Guitar"}, {"instrument": "Trombone"}, {"instrument": "Trumpet", "page": 2}]}
    assert check_facts(report, ordered) == []  # not adjacent: Alto Sax sits between
    swapped = {"order": [{"instrument": "Alto Sax"}, {"instrument": "Guitar"}]}
    problems = check_facts(report, swapped)
    assert len(problems) == 1 and "Guitar" in problems[0] and "after" in problems[0]


def test_order_entries_match_on_page_section_and_chair_like_features():
    report = parse_score(FIXTURES / "finale_mark_carry.pdf")  # Trombone (no mark), Alto A, Guitar A, Drums B, Trumpet B

    assert check_facts(report, {"order": [{"instrument": "Alto Sax", "section": "A"}, {"instrument": "Trumpet", "section": "B"}]}) == []
    assert check_facts(report, {"order": [{"instrument": "Alto Sax", "page": 1}, {"instrument": "Guitar", "page": 1}]})
    assert check_facts(report, {"order": [{"instrument": "Guitar", "section": "A"}, {"instrument": "Alto Sax", "section": "A"}]})


def test_malformed_order_entries_are_rejected_not_ignored():
    report = parse_score(FIXTURES / "finale_score_order.pdf")

    for entry in (
        {"instrument": "Guitar", "xfail": "later"},
        {"instruments": ["Guitar", "Alto Sax"]},
        {"open": True},
        {"instrument": "Guitar", "kind": "shared"},
        {},
    ):
        assert check_facts(report, {"order": [entry]}), entry


def test_a_shared_feature_matches_an_order_entry_by_any_of_its_instruments():
    report = parse_score(FIXTURES / "finale_shared_solos.pdf")  # Soprano Sax, Clarinet, Trumpet share a solo at page 1

    shared = next(f for f in report.features if f.shared_with)
    lead = shared.instrument
    other = shared.shared_with[0].instrument
    assert check_facts(report, {"order": [{"instrument": other, "page": 1}]}) == []
    assert check_facts(report, {"order": [{"instrument": lead, "page": 1}, {"instrument": "Alto Sax", "page": 1}]}) == []


def test_mark_and_section_must_agree_when_both_are_given():
    report = parse_score(FIXTURES / "finale_mark_carry.pdf")

    assert check_facts(report, feature_fact(instrument="Guitar", mark="A", section="A")) == []
    problems = check_facts(report, feature_fact(instrument="Guitar", mark="A", section="B"))
    assert len(problems) == 1 and "same key" in problems[0]
    assert check_facts(report, {"order": [{"instrument": "Guitar", "mark": "A", "section": "B"}]})


def test_order_fact_reports_a_missing_feature():
    report = parse_score(FIXTURES / "finale_score_order.pdf")

    problems = check_facts(report, {"order": [{"instrument": "Guitar"}, {"instrument": "Tuba"}]})
    assert len(problems) == 1 and "Tuba" in problems[0]


def test_order_matches_each_entry_to_the_first_feature_after_the_one_before():
    report = parse_score(FIXTURES / "finale_vocal_leads.pdf")  # two female leads, page 1 then page 3

    ordered = {"order": [{"instrument": "Vocal", "voice": "female", "page": 1}, {"instrument": "Vocal", "voice": "female", "page": 3}]}
    assert check_facts(report, ordered) == []


def test_expected_facts_file_loads_and_each_entry_is_well_formed():
    expected = load_expected()
    assert isinstance(expected, dict)
    for stem, facts in expected.items():
        for want in facts.get("features", []) + facts.get("not_features", []):
            assert "instrument" in want or "instruments" in want or want.get("open"), f"{stem}: {want}"
            if "xfail" in want:
                assert want["xfail"], f"{stem}: xfail needs a reason"
        assert shape_problems(facts) == [], stem


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
