"""Interpret stage: staff label text to canonical instruments."""

import re
from functools import cache
from importlib.resources import files

import yaml

from .models import InstrumentEntry

_CHAIRS = re.compile(r"\s*(\d+)(?:\s*[-–]\s*(\d+))?\s*$")
_TRANSPOSITION = re.compile(r"\bin\s+[a-g][b#♭♯]?(?=\s|$)", re.I)


@cache
def _table() -> dict[str, tuple[str, str]]:
    data = yaml.safe_load(files("score_parser.data").joinpath("aliases.yaml").read_text())
    return {
        alias: (inst["name"], inst["family"])
        for inst in data["instruments"]
        for alias in inst["aliases"]
    }


def _normalise(text: str) -> str:
    return " ".join(text.lower().replace(".", " ").split())


def resolve(label: str) -> tuple[str, str, list[int]] | None:
    """(instrument, family, chairs), or None when the label is not recognised."""
    text = _TRANSPOSITION.sub("", label)
    chairs: list[int] = []
    m = _CHAIRS.search(text)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
        chairs = list(range(lo, hi + 1))
        text = text[: m.start()]
    hit = _table().get(_normalise(text))
    if hit is None:
        return None
    return hit[0], hit[1], chairs or [1]


def build_instrumentation(labels: list[str]) -> tuple[list[InstrumentEntry], list[str]]:
    entries: dict[str, InstrumentEntry] = {}
    unknown: list[str] = []
    for label in labels:
        hit = resolve(label)
        if hit is None:
            unknown.append(label)
            continue
        name, family, chairs = hit
        entry = entries.setdefault(name, InstrumentEntry(name, family, [], []))
        entry.chairs = sorted(set(entry.chairs) | set(chairs))
        entry.labels.append(label)
    return list(entries.values()), unknown


def vocabulary() -> list[str]:
    """Every alias, as a custom vocabulary for OCR."""
    return sorted(_table())
