"""Interpret stage: solo and feature markings with their locations."""

import re

from .instruments import resolve
from .models import Feature, Page
from .systems import Phrase, System, find_systems

_KEYWORD = re.compile(r"\b(solos?|feature)\b", re.I)
_REPEAT = re.compile(r"^\s*\d+\s*x\s*[-–:]?\s*", re.I)
_VAMP_FOR = re.compile(r"^\s*vamp\s+for\s+", re.I)
_VOCAL = re.compile(r"\b(vocals?|male|female|vox)\b", re.I)


def _named_instrument(prefix: str) -> str | None:
    if _VOCAL.search(prefix):
        return "Vocal"
    words = re.findall(r"[A-Za-z][A-Za-z.]*", prefix)
    for n in (2, 1):
        if len(words) < n:
            continue
        candidate = " ".join(words[-n:])
        for form in (candidate, candidate + "s"):
            hit = resolve(form)
            if hit:
                return hit[0]
    return None


def _match(phrase: Phrase) -> tuple[str, str | None, str] | None:
    """(kind, instrument named in the text, matched pattern) or None."""
    m = _KEYWORD.search(phrase.text)
    if not m:
        return None
    kind = "feature" if m.group(1).lower() == "feature" else "solo"
    prefix = _VAMP_FOR.sub("", _REPEAT.sub("", phrase.text[: m.start()]))
    return kind, _named_instrument(prefix), "pattern"


def _current_mark(systems: list[System], system: System, x: float) -> str | None:
    """Latest rehearsal mark at or before (page, system, x) in reading order."""
    current = None
    for s in systems:
        if (s.page, s.index) > (system.page, system.index):
            break
        for mx, text in s.marks:
            if (s.page, s.index) < (system.page, system.index) or mx <= x + 2:
                current = text
    return current


def find_features(pages: list[Page]) -> list[Feature]:
    systems = [s for page in pages for s in find_systems(page)]
    features = []
    for system in systems:
        for phrase in system.texts:
            hit = _match(phrase)
            if hit is None:
                continue
            kind, named, _ = hit
            staff = system.staff_for(phrase.yc)
            reasons = [f"matched {kind} wording"]
            confidence = 0.5
            instrument = named
            if named:
                confidence += 0.3
                reasons.append("instrument named in text")
            else:
                staff_hit = resolve(staff.label)
                if staff_hit:
                    instrument = staff_hit[0]
                    confidence += 0.15
                    reasons.append(f"instrument taken from staff '{staff.label}'")
                else:
                    reasons.append(f"staff '{staff.label}' not recognised; instrument unknown")
            bar = system.bar_at(phrase.x0)
            if bar is None:
                reasons.append("no bar number found on this system")
            else:
                confidence += 0.1
                reasons.append(f"nearest bar number {bar}")
            features.append(
                Feature(
                    kind=kind,
                    instrument=instrument,
                    page=system.page,
                    bar=bar,
                    rehearsal_mark=_current_mark(systems, system, phrase.x0),
                    raw_text=phrase.text,
                    confidence=round(confidence, 2),
                    reasons=reasons,
                )
            )
    return features
