"""Interpret stage: staff label text to canonical instruments."""

import re
from dataclasses import dataclass
from functools import cache
from importlib.resources import files

import yaml

from .layout import TextLine, instruction_lines, label_stacks
from .models import InstrumentEntry, Page

_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5}
_NUM = r"(?:\d+|i{1,3}|iv|v)"
_CHAIRS = re.compile(rf"\s+({_NUM}(?:\s*(?:-|–|&|,|and)\s*{_NUM})*)\s*$", re.I)
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
    return yaml.safe_load(files("score_parser.data").joinpath("aliases.yaml").read_text())[
        "instruments"
    ]


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


def build_instrumentation(
    pages: list[Page],
) -> tuple[list[InstrumentEntry], list[str], list[str]]:
    """(instrumentation, unknown labels, warnings) from the first system's full
    names, cross-checked against abbreviated labels on later systems."""
    entries: dict[str, InstrumentEntry] = {}
    unknown: list[str] = []
    warnings: dict[str, None] = {}

    stacks = [(p.number, st) for p in pages for st in label_stacks(p)]
    if not stacks:
        return [], [], []

    def add(label: str, hit: Resolved) -> InstrumentEntry:
        entry = entries.setdefault(hit.name, InstrumentEntry(hit.name, hit.family, [], [], []))
        entry.chairs = sorted(set(entry.chairs) | set(hit.chairs))
        if label not in entry.labels:
            entry.labels.append(label)
        entry.doublings += [d for d in hit.doublings if d not in entry.doublings]
        return entry

    for line in stacks[0][1]:
        hit = resolve(line.text)
        if hit is None:
            unknown.append(line.text)
        else:
            add(line.text, hit)

    first_chairs = {name: set(e.chairs) for name, e in entries.items()}
    for number, stack in stacks[1:]:
        for line in stack:
            hit = resolve(line.text)
            if hit is None:
                if line.text not in unknown:
                    unknown.append(line.text)
                warnings[f"Page {number}: label '{line.text}' is not recognised"] = None
            elif hit.name not in first_chairs:
                warnings[
                    f"Page {number}: label '{line.text}' ({hit.name}) is not in the "
                    "first-system instrumentation"
                ] = None
            elif not set(hit.chairs) <= first_chairs[hit.name]:
                warnings[
                    f"Page {number}: label '{line.text}' has chairs {hit.chairs} outside "
                    f"the first system's {sorted(first_chairs[hit.name])} for {hit.name}"
                ] = None
            else:
                add(line.text, hit)

    for page in pages:
        page_labels = [ln for n, st in stacks if n == page.number for ln in st]
        if not page_labels:
            continue
        for ins in instruction_lines(page):
            doubled = instruction_doublings(ins.text)
            owner = resolve(_nearest(page_labels, ins.yc).text) if doubled else None
            entry = entries.get(owner.name) if owner else None
            if entry:
                entry.doublings += [
                    d for d in doubled if d != entry.instrument and d not in entry.doublings
                ]
    return list(entries.values()), unknown, list(warnings)


def vocabulary() -> list[str]:
    """Every alias, as a custom vocabulary for OCR."""
    return sorted(_table())
