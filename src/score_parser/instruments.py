"""Interpret stage: staff label text to canonical instruments."""

import re
from dataclasses import dataclass
from functools import cache

import pymupdf

from .data import load
from .layout import TextLine, instruction_lines, label_stacks, running_headers
from .models import InstrumentEntry, Page, Token

_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5}
_NUM = r"(?:\d+|i{1,3}|iv|v)"
_CHAIRS = re.compile(rf"(?:\s+|(?<=\.))({_NUM}(?:\s*(?:-|–|&|,|and)\s*{_NUM})*)\s*$", re.I)
_CHAIR_PART = re.compile(rf"({_NUM})|(-|–)", re.I)
_TRANSPOSITION = re.compile(r"\bin\s+[a-g][b#♭♯]?(?=\s|$)", re.I)
_PARENS = re.compile(r"\(([^)]*)\)")


@dataclass
class Resolved:
    name: str
    family: str
    chairs: list[int]
    doublings: list[str]


@cache
def _data() -> list[dict]:
    return load("aliases.yaml")["instruments"]


@cache
def _table() -> dict[str, tuple[str, str]]:
    return {alias: (i["name"], i["family"]) for i in _data() for alias in i["aliases"]}


@cache
def _bare_doubling_aliases() -> list[tuple[str, str]]:
    pairs = [(a, i["name"]) for i in _data() if i.get("bare_doubling") for a in i["aliases"]]
    return sorted(pairs, key=lambda p: -len(p[0]))


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
    chairs: list[int] = []
    m = _CHAIRS.search(text)
    if m:
        chairs = _chairs(m.group(1))
        text = text[: m.start()]
    hit = _table().get(_normalise(text))
    if hit is None:
        return None
    return Resolved(hit[0], hit[1], chairs or [1], doublings)


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


def resolve_against_first_system(label: str, first_chairs: dict[str, set[int]]) -> LabelCheck:
    """Resolve a staff label and cross-check it against the first system.

    `first_chairs` maps each first-system instrument to its chairs. The one rule
    for later-system labels and for labels that features take instruments from."""
    hit = resolve(label)
    if hit is None:
        return LabelCheck(None, f"label '{label}' is not recognised")
    if hit.name not in first_chairs:
        return LabelCheck(
            hit, f"label '{label}' ({hit.name}) is not in the first-system instrumentation"
        )
    if not set(hit.chairs) <= first_chairs[hit.name]:
        return LabelCheck(
            hit,
            f"label '{label}' has chairs {hit.chairs} outside "
            f"the first system's {sorted(first_chairs[hit.name])} for {hit.name}",
        )
    return LabelCheck(hit, None)


@dataclass
class Instrumentation:
    entries: list[InstrumentEntry]
    unknown_labels: list[str]
    warnings: list[str]

    @property
    def first_chairs(self) -> dict[str, set[int]]:
        return {e.instrument: set(e.chairs) for e in self.entries}


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


def build_instrumentation(pages: list[Page]) -> Instrumentation:
    """First system's full names, cross-checked against abbreviated labels on
    later systems."""
    entries: dict[str, InstrumentEntry] = {}
    unknown: list[str] = []
    warnings: dict[str, None] = {}

    headers = running_headers(pages)
    stacks = [(p.number, st) for p in pages for st in label_stacks(p, headers)]
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
            add(line.text, hit)

    first_chairs = {name: set(e.chairs) for name, e in entries.items()}
    for number, stack in (st for i, st in enumerate(stacks) if i != first):
        for line in stack:
            check = resolve_against_first_system(line.text, first_chairs)
            if check.hit is None and line.text not in unknown:
                unknown.append(line.text)
            if check.problem:
                warnings[f"Page {number}: {check.problem}"] = None
            else:
                add(line.text, check.hit)

    for page in pages:
        page_labels = [ln for n, st in stacks if n == page.number for ln in st]
        if not page_labels:
            continue
        for ins in instruction_lines(page, headers):
            doubled = instruction_doublings(ins.text)
            owner = resolve(_nearest(page_labels, ins.yc).text) if doubled else None
            entry = entries.get(owner.name) if owner else None
            if entry:
                entry.doublings += [
                    d for d in doubled if d != entry.instrument and d not in entry.doublings
                ]
    return Instrumentation(list(entries.values()), unknown, list(warnings))


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
