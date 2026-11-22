"""Interpret stage: staff label text to canonical instruments."""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from functools import cache

import pymupdf

from .data import load
from .layout import TextLine, instruction_lines, label_stacks, running_headers
from .models import InstrumentEntry, Page, Token
from .vocal import voice_lines

_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5}
_NUM = r"(?:\d+|i{1,3}|iv|v)"
_CHAIRS = re.compile(rf"(?:\s+|(?<=\.))({_NUM}(?:\s*(?:-|–|&|,|and)\s*{_NUM})*)\s*$", re.I)
_LEADING_CHAIRS = re.compile(rf"^({_NUM}(?:\s*(?:-|–|&|,)\s*{_NUM})*)\s+(?=[a-z])", re.I)  # "1&2 B Tpt."
_CHAIR_PART = re.compile(rf"({_NUM})|(-|–)", re.I)
_TRANSPOSITION = re.compile(r"\bin\s+[a-g][b#♭♯]?(?=\s|$)", re.I)
_PARENS = re.compile(r"\(([^)]*)\)")
_COMBINED = re.compile(r",\s*(?=[a-z])", re.I)  # "Trb. 3, Tba.": a comma before a name, not a chair


@dataclass
class Resolved:
    name: str
    family: str
    chairs: list[int]
    doublings: list[str]
    also: list["Resolved"] = field(default_factory=list)  # further parts of a combined label
    chairs_given: bool = False  # the label printed a chair; `chairs` is [1] otherwise
    shared: bool = False  # one staff for every chair ("Gtrs."), or several chairs given

    @property
    def single_chair(self) -> int | None:
        """The one chair the label states, or None (none printed, or several)."""
        return self.chairs[0] if self.chairs_given and len(self.chairs) == 1 else None

    def parts(self) -> list["Resolved"]:
        """This instrument and the further parts of a combined label."""
        return [self, *self.also]


@cache
def _data() -> list[dict]:
    return load("aliases.yaml")["instruments"]


@cache
def _table() -> dict[str, tuple[str, str]]:
    return {alias: (i["name"], i["family"]) for i in _data() for alias in i["aliases"]}


@cache
def _shared_aliases() -> frozenset[str]:
    return frozenset(a for i in _data() for a in i.get("shared_aliases", []))


@cache
def _bare_doubling_aliases() -> list[tuple[str, str]]:
    pairs = [(a, i["name"]) for i in _data() if i.get("bare_doubling") for a in i["aliases"]]
    return sorted(pairs, key=lambda p: -len(p[0]))


@cache
def _variant_groups() -> list[frozenset[str]]:
    return [frozenset(g) for g in load("instrument_variants.yaml")["variants"]]


def present_as(name: str, present: Iterable[str]) -> str | None:
    """The instrument in `present` that `name` counts as: itself, else a
    canonical-name variant of it (Bass and Electric Bass), else None. The one
    rule for variants."""
    present = list(present)
    if name in present:
        return name
    return next((p for g in _variant_groups() if name in g for p in present if p in g), None)


def _normalise(text: str) -> str:
    return " ".join(text.lower().replace(".", " ").split())


def _chairs(spec: str) -> list[int]:
    chairs: list[int] = []
    prev: int | None = None
    ranged = False
    for m in _CHAIR_PART.finditer(spec):
        if m.group(2):
            ranged = True
            continue
        word = m.group(1).lower()
        n = int(word) if word.isdigit() else _ROMAN[word]
        chairs += range(prev + 1, n + 1) if ranged and prev is not None else [n]
        prev, ranged = n, False
    return sorted(set(chairs))


def resolve(label: str) -> Resolved | None:
    """Canonical instrument, chairs and label doublings, or None if unrecognised."""
    doublings: list[str] = []
    for group in _PARENS.findall(label):
        for part in re.split(r"[,/]", group):
            hit = _table().get(_normalise(part))
            if hit and hit[0] not in doublings:
                doublings.append(hit[0])
    text = _TRANSPOSITION.sub("", _PARENS.sub(" ", label))
    parts = [_resolve_part(part) for part in _COMBINED.split(text)]
    if not parts[0] or None in parts:
        return None
    first, *rest = parts
    first.doublings = doublings
    first.also = rest
    return first


def _resolve_part(text: str) -> Resolved | None:
    chairs: list[int] = []
    m = _CHAIRS.search(text)
    lead = _LEADING_CHAIRS.match(text.strip())
    if m:
        chairs = _chairs(m.group(1))
        text = text[: m.start()]
    elif lead:
        chairs = _chairs(lead.group(1))
        text = text.strip()[lead.end() :]
    alias = _normalise(text)
    hit = _table().get(alias)
    if hit is None:
        return None
    shared = len(chairs) > 1 or alias in _shared_aliases()
    return Resolved(hit[0], hit[1], chairs or [1], [], chairs_given=bool(chairs), shared=shared)


def instruction_doublings(text: str) -> list[str]:
    """Doublings named in instruction text: "to Flute", or a bare "piccolo trpt"."""
    found: list[str] = []
    m = re.search(r"\bto\s+(.+)", text, re.I)
    if m and (hit := resolve(m.group(1))):
        found.append(hit.name)
    norm = f" {_normalise(text)} "
    for alias, name in _bare_doubling_aliases():
        if f" {alias} " in norm and name not in found:
            found.append(name)
            break
    return found


def _nearest(labels: list[TextLine], y: float) -> TextLine:
    return min(labels, key=lambda ln: abs(ln.yc - y))


@dataclass
class LabelCheck:
    """A staff label compared with the first system's instrumentation."""

    hit: Resolved | None
    problem: str | None  # why the label disagrees with the first system, or None

    @property
    def accepted(self) -> bool:
        return self.hit is not None and self.problem is None


@dataclass(frozen=True)
class Roster:
    """What a later-system label is checked against: the first system's chairs
    per instrument, and the instruments the first system lacks that recur
    across later systems (accepted without a warning)."""

    first_chairs: dict[str, set[int]]
    recurring: tuple[str, ...] = ()

    def __contains__(self, name: str) -> bool:
        return name in self.first_chairs or name in self.recurring


def _check_part(part: Resolved, label: str, roster: Roster) -> tuple[Resolved, str | None]:
    """(part under the roster's name for it, the problem or None)."""
    same = present_as(part.name, roster.first_chairs)
    if same is None and (rec := present_as(part.name, roster.recurring)):
        return replace(part, name=rec), None  # recurring: a normal instrument of the score
    if same is not None:
        part = replace(part, name=same)
    if part.name not in roster.first_chairs:
        return part, f"label '{label}' ({part.name}) is not in the first-system instrumentation"
    if not set(part.chairs) <= roster.first_chairs[part.name]:
        return part, (
            f"label '{label}' has chairs {part.chairs} outside "
            f"the first system's {sorted(roster.first_chairs[part.name])} for {part.name}"
        )
    return part, None


def resolve_against_first_system(label: str, roster: Roster) -> LabelCheck:
    """Resolve a staff label and cross-check it against the first system.

    The one rule for later-system labels and for labels that features take
    instruments from. Every part of a combined label is checked; the returned
    hit carries the roster's names (variants, recurring instruments)."""
    hit = resolve(label)
    if hit is None:
        return LabelCheck(None, f"label '{label}' is not recognised")
    parts: list[Resolved] = []
    problem = None
    for part in hit.parts():
        checked, found = _check_part(part, label, roster)
        parts.append(checked)
        if found and problem is None:
            problem = found
    return LabelCheck(replace(parts[0], also=parts[1:]), problem)


@dataclass
class Instrumentation:
    entries: list[InstrumentEntry]
    unknown_labels: list[str]
    warnings: list[str]

    roster: Roster = field(default_factory=lambda: Roster({}))


def _first_system(stacks: list[tuple[int, list[TextLine]]]) -> int:
    """Index of the first system: on the first page with any resolving label
    (else the first page), the stack with the most labels that resolve; the
    earliest stack wins a tie."""

    def score(i: int) -> int:
        return sum(resolve(ln.text) is not None for ln in stacks[i][1])

    pages = list(dict.fromkeys(number for number, _ in stacks))
    page = next((n for n in pages if any(score(i) for i, (m, _) in enumerate(stacks) if m == n)), pages[0])
    candidates = [i for i, (number, _) in enumerate(stacks) if number == page]
    return max(candidates, key=lambda i: (score(i), -i))


def _recurring_names(
    first_chairs: dict[str, set[int]], later: list[tuple[int, list[TextLine]]]
) -> list[str]:
    """Instruments the first system lacks that label two or more later systems:
    a normal instrument of the score, not a stray label. Variants of one
    instrument count together, named by their first appearance."""
    systems_of: dict[str, int] = {}
    names: list[str] = []
    for _, stack in later:
        seen: set[str] = set()
        for line in stack:
            hit = resolve(line.text)
            for part in hit.parts() if hit else []:
                if present_as(part.name, first_chairs):
                    continue
                name = present_as(part.name, names)
                if name is None:
                    names.append(name := part.name)
                seen.add(name)
        for name in seen:
            systems_of[name] = systems_of.get(name, 0) + 1
    return [n for n in names if systems_of[n] >= 2]


def _without_voices(stack: list[TextLine]) -> list[TextLine]:
    """The stack's instrument staves: voice staves are not instruments and are
    neither listed nor reported as unknown labels."""
    voices = voice_lines([ln.text for ln in stack], [ln.yc for ln in stack])
    return [ln for i, ln in enumerate(stack) if i not in voices]


def build_instrumentation(pages: list[Page]) -> Instrumentation:
    """First system's full names, cross-checked against abbreviated labels on
    later systems."""
    entries: dict[str, InstrumentEntry] = {}
    unknown: list[str] = []
    warnings: dict[str, None] = {}

    headers = running_headers(pages)
    stacks = [(p.number, _without_voices(st)) for p in pages for st in label_stacks(p, headers)]
    if not stacks:
        return Instrumentation([], [], [])
    first = _first_system(stacks)

    def add(label: str, hit: Resolved) -> InstrumentEntry:
        entry = entries.setdefault(hit.name, InstrumentEntry(hit.name, hit.family, [], [], []))
        entry.chairs = sorted(set(entry.chairs) | set(hit.chairs))
        if label not in entry.labels:
            entry.labels.append(label)
        entry.doublings += [d for d in hit.doublings if d not in entry.doublings]
        return entry

    for line in stacks[first][1]:
        hit = resolve(line.text)
        if hit is None:
            unknown.append(line.text)
        else:
            for part in hit.parts():
                add(line.text, part)

    first_chairs = {name: set(e.chairs) for name, e in entries.items()}
    later = [st for i, st in enumerate(stacks) if i != first]
    roster = Roster(first_chairs, tuple(_recurring_names(first_chairs, later)))
    for number, stack in later:
        for line in stack:
            check = resolve_against_first_system(line.text, roster)
            if check.hit is None and line.text not in unknown:
                unknown.append(line.text)
            if check.problem:
                warnings[f"Page {number}: {check.problem}"] = None
            else:
                for part in check.hit.parts():
                    add(line.text, part)

    for page in pages:
        page_labels = [ln for n, st in stacks if n == page.number for ln in st]
        if not page_labels:
            continue
        for ins in instruction_lines(page, headers):
            doubled = instruction_doublings(ins.text)
            owner = resolve(_nearest(page_labels, ins.yc).text) if doubled else None
            for part in owner.parts() if owner else []:
                name = present_as(part.name, entries)
                if name is None:
                    continue
                entry = entries[name]
                entry.doublings += [
                    d for d in doubled if d != entry.instrument and d not in entry.doublings
                ]
    return Instrumentation(list(entries.values()), unknown, list(warnings), roster)


def vocabulary() -> list[str]:
    """Every alias, as a custom vocabulary for OCR."""
    return sorted(_table())


def vocabulary_hits(tokens: list[Token], frame: pymupdf.Rect) -> tuple[int, int]:
    """(hits in the left half, all hits): upright instrument words in the alias
    table. Vision reads sideways and upside-down text too, so only words set
    horizontally count, and staff labels sit left of the staves, so an
    upside-down page finds its labels on the right. Scores an OCR orientation."""
    hits = [t for t in tokens if t.x1 - t.x0 > t.y1 - t.y0 and resolve(t.text)]
    left = [t for t in hits if (t.x0 + t.x1) / 2 < frame.x0 + frame.width / 2]
    return len(left), len(hits)
