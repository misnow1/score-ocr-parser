"""Opt-in corpus tests against the real local score folder.

Skipped unless SCORE_CORPUS_DIR points at a folder of score PDFs (the part facts
need SCORE_PARTS_DIR, the `parts/<instrument folder>/<song>.pdf` tree). Never run
in CI. The scores and parts are read in place; nothing from them is written
anywhere. Expected facts live in expected.yaml and hold no music content.
"""

import importlib.util
import os
import shutil
from pathlib import Path

import pytest
import yaml

from score_parser import find_parts, parse_part, parse_score
from score_parser.title import clean_filename

EXPECTED = Path(__file__).with_name("expected.yaml")
FIXTURES = Path(__file__).parents[1] / "fixtures" / "synthetic"
CORPUS_DIR = os.environ.get("SCORE_CORPUS_DIR")

PARTS_DIR = os.environ.get("SCORE_PARTS_DIR")

needs_corpus = pytest.mark.skipif(not CORPUS_DIR, reason="SCORE_CORPUS_DIR is not set")
needs_parts = pytest.mark.skipif(not PARTS_DIR, reason="SCORE_PARTS_DIR is not set")


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


def _with_xfail(fact: dict, problem: str | None, label: str | None = None) -> list[str]:
    """An expected-to-fail fact must keep failing; it is flagged once it passes."""
    reason = fact.get("xfail")
    if not reason:
        return [problem] if problem else []
    return [] if problem else [f"{label or _fact_label(fact)} now passes; remove its xfail ({reason})"]


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


_PART_KEYS = ("slot", "instrument", "chairs", "relation", "solos", "max_solos", "xfail")
_SOLO_KEYS = ("page", "mark", "bar", "xfail")
_RELATIONS = ("same", "doubling", "unexplained", "unknown")


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _solo_shape_problems(slot, solo) -> list[str]:
    if not isinstance(solo, dict):
        return [f"solo {solo!r} of part {slot} must be a mapping"]
    problems = [f"solo {solo} takes no {key!r}" for key in solo if key not in _SOLO_KEYS]
    if "page" not in solo:
        problems.append(f"solo {solo} of part {slot} needs a page")
    for key in ("page", "bar"):
        if key in solo and not _is_int(solo[key]):
            problems.append(f"solo {solo}: {key} must be a number")
    if "mark" in solo and not (isinstance(solo["mark"], str) and solo["mark"]):
        problems.append(f"solo {solo}: mark must be text")
    if "xfail" in solo and not (isinstance(solo["xfail"], str) and solo["xfail"]):
        problems.append(f"solo {solo}: xfail needs a reason")
    return problems


def _part_shape_problems(fact) -> list[str]:
    if not isinstance(fact, dict):
        return [f"part {fact!r} must be a mapping"]
    problems = []
    for key in ("slot", "instrument"):
        if not (isinstance(fact.get(key), str) and fact[key]):
            problems.append(f"part {fact} needs a {key} (text)")
    problems += [f"part {fact} takes no {key!r}" for key in fact if key not in _PART_KEYS]
    chairs = fact.get("chairs", [])
    if not isinstance(chairs, list) or not all(_is_int(c) for c in chairs):
        problems.append(f"part {fact}: chairs must be a list of numbers")
    if fact.get("relation", "same") not in _RELATIONS:
        problems.append(f"part {fact}: relation must be one of {', '.join(_RELATIONS)}")
    if "max_solos" in fact and not (_is_int(fact["max_solos"]) and fact["max_solos"] >= 0):
        problems.append(f"part {fact}: max_solos must be a number, 0 or more")
    if "xfail" in fact and not (isinstance(fact["xfail"], str) and fact["xfail"]):
        problems.append(f"part {fact}: xfail needs a reason")
    solos = fact.get("solos", [])
    if not isinstance(solos, list):
        problems.append(f"part {fact}: solos must be a list")
        solos = []
    for solo in solos:
        problems += _solo_shape_problems(fact.get("slot"), solo)
    return problems


def part_shape_problems(facts: dict) -> list[str]:
    """Part facts that are malformed rather than unmet. `parts` is a list of mappings;
    a part names a `slot` (its instrument folder) and an `instrument`, takes only the
    keys of the schema with the right types, and an `xfail` needs a reason; a solo needs
    a `page` and takes `mark`, `bar`, `xfail`. Two facts for the same slot, instrument
    and chairs are one part stated twice."""
    parts = facts.get("parts")
    if parts is None:
        return []
    if not isinstance(parts, list):
        return [f"parts must be a list of part facts, not {type(parts).__name__}"]
    problems = [p for fact in parts for p in _part_shape_problems(fact)]
    if not problems:
        seen = set()
        for fact in parts:
            key = (fact["slot"], fact["instrument"], tuple(fact["chairs"]) if "chairs" in fact else None)
            if key in seen:
                problems.append(f"part {fact['slot']}/{fact['instrument']} is given twice")
            seen.add(key)
    return problems


def _is_part(report, fact: dict) -> bool:
    info = report.part
    return (
        (info.player_slot, info.instrument) == (fact["slot"], fact["instrument"])
        and ("chairs" not in fact or info.chairs == fact["chairs"])
        and ("relation" not in fact or info.relation == fact["relation"])
    )


def _solo_order_problem(report, solos: list[dict]) -> str | None:
    """The solos that are expected to be met must appear in this order in the part
    (first match after the one before); a missing one is reported on its own."""
    after = -1
    for want in solos:
        found = [i for i, f in enumerate(report.features) if _located(f, want)]
        if want.get("xfail") or not found:
            continue
        later = [i for i in found if i > after]
        if not later:
            return f"solo order: {_place(want)} is not after the solo listed before it"
        after = later[0]
    return None


def _part_problems(report, fact: dict) -> tuple[list[str], list[str]]:
    """(unmet facts, stale solo xfails) of one part against its fact."""
    unmet, stale = [], []
    solos = fact.get("solos", [])
    for want in solos:
        hit = any(_located(f, want) for f in report.features)
        if want.get("xfail"):
            if hit:
                stale.append(f"solo at {_place(want)} now passes; remove its xfail ({want['xfail']})")
        elif not hit:
            unmet.append(f"no solo at {_place(want)}")
    order = _solo_order_problem(report, solos)
    if order:
        unmet.append(order)
    cap = fact.get("max_solos")
    if cap is not None and len(report.features) > cap:
        unmet.append(f"{len(report.features)} solos found, at most {cap} expected")
    return unmet, stale


def _part_fact_problems(reports: list, fact: dict) -> tuple[list[str], list[str]]:
    candidates = [r for r in reports if _is_part(r, fact)]
    if not candidates:
        chairs = f" chairs {fact['chairs']}" if "chairs" in fact else ""
        relation = f" ({fact['relation']})" if "relation" in fact else ""
        return [f"no {fact['instrument']} part{chairs}{relation} in player slot {fact['slot']}"], []
    return min((_part_problems(r, fact) for r in candidates), key=lambda p: (len(p[0]), len(p[1])))


def check_part_facts(reports: list, facts: list[dict]) -> list[str]:
    """Mismatches between a score's parts (`PartReport`s) and its `parts:` facts.

    A part fact names the `slot` (the instrument folder the file sits in) and the
    `instrument` of the filename, optionally `chairs` (exact list), `relation`
    (same, doubling, unexplained, unknown), `solos` (each `page`, `mark` and `bar`
    as given, matched exactly against every feature of the part whatever its kind;
    the listed solos must appear in that order, not necessarily adjacent),
    `max_solos` (a cap on every feature of the part, vocal leads included) and
    `xfail: reason`. A solo takes its own `xfail` and then leaves the order check.
    Facts the tool does not meet yet keep failing until their xfail is removed; a
    solo's stale xfail is reported even inside an xfail part.
    """
    problems = part_shape_problems({"parts": facts})
    if problems:
        return problems
    for fact in facts:
        label = f"part {fact['slot']}/{fact['instrument']}"
        unmet, stale = _part_fact_problems(reports, fact)
        problems += _with_xfail(fact, "; ".join(unmet) if unmet else None, label)
        problems += stale
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


PART = FIXTURES / "part_one_staff.pdf"  # Trumpet 1: solos at page 1 bar 6 mark A, page 2 bar 16 mark B


def place_part(root: Path, folder: str, name: str) -> Path:
    target = root / folder / f"{name}.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(PART, target)
    return target


@pytest.fixture
def trumpet_part(tmp_path):
    return [parse_part(place_part(tmp_path, "trumpet-1", "Synthetic Tune Trpt1"))]


def part_fact(**fact):
    return {"slot": "trumpet-1", "instrument": "Trumpet", **fact}


def test_part_fact_passes_on_slot_instrument_chairs_and_solos(trumpet_part):
    fact = part_fact(chairs=[1], solos=[{"page": 1, "mark": "A", "bar": 6}, {"page": 2, "mark": "B"}])
    assert check_part_facts(trumpet_part, [fact]) == []
    assert check_part_facts(trumpet_part, [part_fact()]) == []  # chairs and solos are optional


@pytest.mark.parametrize(
    "fact",
    [
        {"slot": "trumpet-2", "instrument": "Trumpet"},  # another player slot
        {"slot": "trumpet-1", "instrument": "Trombone"},
        part_fact(chairs=[2]),
        part_fact(chairs=[1, 2]),
        part_fact(relation="doubling"),
    ],
)
def test_part_fact_reports_a_part_that_is_not_there(trumpet_part, fact):
    assert len(check_part_facts(trumpet_part, [fact])) == 1


def test_part_relation_to_the_slot_can_be_asserted(trumpet_part):
    assert check_part_facts(trumpet_part, [part_fact(relation="same")]) == []


def test_part_solo_page_mark_and_bar_must_match_exactly(trumpet_part):
    for solo in ({"page": 1, "mark": "B"}, {"page": 3, "mark": "A"}, {"page": 1, "mark": "A", "bar": 7}):
        problems = check_part_facts(trumpet_part, [part_fact(solos=[solo])])
        assert len(problems) == 1 and "solo" in problems[0], solo


def test_part_solos_must_appear_in_the_listed_order(trumpet_part):
    inverted = [{"page": 2, "mark": "B"}, {"page": 1, "mark": "A"}]
    problems = check_part_facts(trumpet_part, [part_fact(solos=inverted)])
    assert len(problems) == 1 and "order" in problems[0]


def test_max_solos_caps_the_part_solo_count(trumpet_part):
    assert check_part_facts(trumpet_part, [part_fact(max_solos=2)]) == []
    assert check_part_facts(trumpet_part, [part_fact(max_solos=1)])


def test_expected_to_fail_part_and_solo_facts_must_keep_failing(trumpet_part):
    gone = {"slot": "tuba", "instrument": "Tuba", "xfail": "the part is not found yet"}
    assert check_part_facts(trumpet_part, [gone]) == []
    here = part_fact(xfail="stale")
    problems = check_part_facts(trumpet_part, [here])
    assert len(problems) == 1 and "now passes" in problems[0]
    wrong = part_fact(solos=[{"page": 1, "mark": "C", "xfail": "known gap"}])
    assert check_part_facts(trumpet_part, [wrong]) == []
    right = part_fact(solos=[{"page": 1, "mark": "A", "xfail": "stale"}])
    assert "now passes" in check_part_facts(trumpet_part, [right])[0]


def test_an_expected_to_fail_solo_does_not_break_the_order_of_the_others(trumpet_part):
    solos = [{"page": 1, "mark": "C", "xfail": "known gap"}, {"page": 2, "mark": "B"}]
    assert check_part_facts(trumpet_part, [part_fact(solos=solos)]) == []


def test_two_parts_in_one_slot_are_told_apart_by_instrument_and_chair(tmp_path):
    reports = [
        parse_part(place_part(tmp_path, "trumpet-1", "Synthetic Tune Trpt1")),
        parse_part(place_part(tmp_path, "trumpet-1", "Synthetic Tune Flugelhorn")),
    ]
    assert check_part_facts(reports, [part_fact(), {"slot": "trumpet-1", "instrument": "Flugelhorn"}]) == []


def test_malformed_part_facts_are_rejected_not_ignored(trumpet_part):
    for fact in (
        {"instrument": "Trumpet"},  # no slot
        {"slot": "trumpet-1"},  # no instrument
        part_fact(solos=[{"mark": "A"}]),  # no page
        part_fact(solos=[{"page": 1, "colour": "red"}]),
        part_fact(colour="red"),
        part_fact(relation="friends"),
        part_fact(chairs=1),
        part_fact(xfail=""),
        part_fact(solos=[{"page": 1, "xfail": ""}]),
        "Trumpet",  # not a mapping
        part_fact(solos=3),
        part_fact(solos={"page": 1}),
        part_fact(solos=["page"]),
        part_fact(max_solos="two"),
        part_fact(max_solos=True),
        part_fact(max_solos=-1),
        part_fact(solos=[{"page": "1"}]),
        part_fact(solos=[{"page": 1, "bar": "6"}]),
        part_fact(solos=[{"page": 1, "mark": 1}]),
        part_fact(chairs=[True]),
        part_fact(xfail=3),
        {"slot": 1, "instrument": "Trumpet"},
    ):
        assert check_part_facts(trumpet_part, [fact]), fact
        assert part_shape_problems({"parts": [fact]}), fact


def test_a_parts_section_that_is_not_a_list_is_rejected():
    assert part_shape_problems({"parts": part_fact()})
    assert part_shape_problems({"parts": "Trumpet"})
    assert part_shape_problems({}) == [] and part_shape_problems({"parts": None}) == []


def test_duplicate_part_facts_are_reported(trumpet_part):
    problems = check_part_facts(trumpet_part, [part_fact(), part_fact(solos=[{"page": 1}])])
    assert len(problems) == 1 and "twice" in problems[0]
    assert part_shape_problems({"parts": [part_fact(chairs=[1]), part_fact(chairs=[2])]}) == []  # told apart by chairs


def test_a_stale_solo_xfail_inside_an_expected_to_fail_part_is_still_reported(trumpet_part):
    fact = part_fact(xfail="part gap", max_solos=0, solos=[{"page": 1, "mark": "A", "xfail": "stale"}])
    problems = check_part_facts(trumpet_part, [fact])
    assert len(problems) == 1 and "solo at page 1, mark A now passes" in problems[0]


def parts_of_score(parts_root: Path, score_stem: str) -> list:
    """The parts of the score with this file name (without .pdf), read in place by the library lookup."""
    return find_parts(parts_root, clean_filename(score_stem)).parts


def test_parts_of_a_score_are_found_by_the_cleaned_score_file_name(tmp_path):
    place_part(tmp_path, "trumpet-1", "Synthetic Tune Trpt1")
    place_part(tmp_path, "scores", "Synthetic Tune - Score")  # a conductor score is not a part
    place_part(tmp_path, "trumpet-2", "Another Number Trpt2")  # another song
    parts = parts_of_score(tmp_path, "Synthetic Tune 11.3.26 - Score ")
    assert [(r.part.player_slot, r.part.instrument) for r in parts] == [("trumpet-1", "Trumpet")]


def test_expected_facts_file_loads_and_each_entry_is_well_formed():
    expected = load_expected()
    assert isinstance(expected, dict)
    for stem, facts in expected.items():
        for want in facts.get("features", []) + facts.get("not_features", []):
            assert "instrument" in want or "instruments" in want or want.get("open"), f"{stem}: {want}"
            if "xfail" in want:
                assert want["xfail"], f"{stem}: xfail needs a reason"
        assert shape_problems(facts) == [], stem
        assert part_shape_problems(facts) == [], stem


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


@needs_parts
@pytest.mark.parametrize("stem", sorted(s for s, facts in load_expected().items() if facts.get("parts")))
def test_corpus_score_parts_match_approved_facts(stem):
    reports = parts_of_score(Path(PARTS_DIR), stem)
    facts = load_expected()[stem]["parts"]
    if any(not fact.get("xfail") for fact in facts):  # a song whose part facts all xfail may have no parts yet
        assert reports, f"no parts found in SCORE_PARTS_DIR for {stem!r}"
    assert check_part_facts(reports, facts) == []


def _corpus_counts_main():
    spec = importlib.util.spec_from_file_location("corpus_counts", Path(__file__).parents[2] / "scripts" / "corpus_counts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


def test_corpus_counts_adds_parts_found_and_part_solos_per_score(tmp_path, capsys):
    scores = tmp_path / "scores"
    scores.mkdir()
    shutil.copy(FIXTURES / "finale_solos.pdf", scores / "Synthetic Tune - Score.pdf")
    parts = tmp_path / "parts"
    place_part(parts, "trumpet-1", "Synthetic Tune Trpt1")
    place_part(parts, "trumpet-2", "Synthetic Tune Trpt2")
    place_part(parts, "trumpet-3", "Other Song Trpt3")

    before = sorted(tmp_path.rglob("*"))
    assert _corpus_counts_main()([str(scores), "--parts-dir", str(parts)]) == 0
    lines = capsys.readouterr().out.splitlines()

    assert lines[0].split()[-2:] == ["parts", "part_solos"]
    assert lines[1].split()[-2:] == ["2", "4"]  # two parts, two solos each
    assert lines[-1].split()[-2:] == ["2", "4"]
    assert sorted(tmp_path.rglob("*")) == before  # writes nothing


def test_corpus_counts_without_a_parts_folder_keeps_its_columns(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("SCORE_PARTS_DIR", raising=False)
    shutil.copy(FIXTURES / "finale_solos.pdf", tmp_path / "Synthetic Tune - Score.pdf")

    assert _corpus_counts_main()([str(tmp_path), "--parts-dir", ""]) == 0
    assert "parts" not in capsys.readouterr().out.splitlines()[0]
