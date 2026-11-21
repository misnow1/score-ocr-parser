"""Interpret stage: solo and feature markings with their locations."""

import re

from .layout import running_headers
from .instruments import resolve_against_first_system
from .models import Feature, FeatureKind, Page
from .systems import X_SLACK, Phrase, System, find_systems

_KEYWORD = re.compile(r"\b(solos?|feature)\b", re.I)
_REPEAT = re.compile(r"^\s*\d+\s*x\s*[-–:]?\s*", re.I)
_VAMP_FOR = re.compile(r"^\s*vamp\s+for\s+", re.I)
# The vocal word must sit directly before the solo wording ("male vocal solo").
_VOCAL_TIED = re.compile(r"\b(?:(male|female)(?:\s+(?:vocals?|vox))?|vocals?|vox)\s*$", re.I)

# Confidence: a base for matching the wording, plus evidence for the instrument and bar.
BASE = 0.5
INSTRUMENT_NAMED = 0.3
INSTRUMENT_INFERRED = 0.15  # from the staff, or from "male"/"female" alone
BAR_FOUND = 0.1
BAR_GUESSED = 0.05  # text sits left of every bar number


def _named_instrument(
    prefix: str, first_chairs: dict[str, set[int]], notes: list[str]
) -> tuple[str, bool] | None:
    """(instrument, inferred) named by the words just before the solo wording.
    A named instrument the report's instrumentation lacks is dropped with a note."""
    vocal = _VOCAL_TIED.search(prefix)
    if vocal:
        return "Vocal", not re.search(r"vocals?|vox", vocal.group(0), re.I)
    words = re.findall(r"[A-Za-z][A-Za-z.]*", prefix)
    for n in (2, 1):
        if len(words) < n:
            continue
        candidate = " ".join(words[-n:])
        for form in (candidate, candidate + "s"):
            check = resolve_against_first_system(form, first_chairs)
            if check.hit is None:
                continue
            if check.hit.name in first_chairs:
                return check.hit.name, False
            notes.append(check.problem)
    return None


def _match(phrase: Phrase) -> tuple[FeatureKind, str] | None:
    """(kind, the text before the solo wording) or None."""
    m = _KEYWORD.search(phrase.text)
    if not m:
        return None
    kind: FeatureKind = "feature" if m.group(1).lower() == "feature" else "solo"
    return kind, _VAMP_FOR.sub("", _REPEAT.sub("", phrase.text[: m.start()]))


def _current_mark(systems: list[System], system: System, x: float) -> str | None:
    """Latest rehearsal mark at or before (page, system, x) in reading order."""
    current = None
    for s in systems:
        if (s.page, s.index) > (system.page, system.index):
            break
        for mx, text in s.marks:
            if (s.page, s.index) < (system.page, system.index) or mx <= x + X_SLACK:
                current = text
    return current


def find_features(
    pages: list[Page], first_chairs: dict[str, set[int]]
) -> tuple[list[Feature], list[str]]:
    """(features, warnings). Instruments come only from the first system's
    instrumentation (`first_chairs`); anything else is dropped with a warning."""
    headers = running_headers(pages)
    systems = [s for page in pages for s in find_systems(page, headers)]
    features: list[Feature] = []
    warnings: dict[str, None] = {}
    for system in systems:
        for phrase in system.texts:
            hit = _match(phrase)
            if hit is None:
                continue
            kind, prefix = hit
            notes: list[str] = []
            named = _named_instrument(prefix, first_chairs, notes)
            staff = system.staff_for(phrase.yc)
            reasons = [f"matched {kind} wording"]
            confidence = BASE
            instrument = None
            if named and not named[1]:
                instrument = named[0]
                confidence += INSTRUMENT_NAMED
                reasons.append("instrument named in text")
            elif named:
                instrument = named[0]
                confidence += INSTRUMENT_INFERRED
                reasons.append("instrument inferred from 'male'/'female' without a vocal word")
            else:
                check = resolve_against_first_system(staff.label, first_chairs)
                if check.hit and check.hit.name in first_chairs:
                    instrument = check.hit.name
                    confidence += INSTRUMENT_INFERRED
                    reasons.append(f"instrument taken from staff '{staff.label}'")
                else:
                    reasons.append(f"staff '{staff.label}' not usable; instrument unknown")
                    if check.problem:
                        notes.append(check.problem)
            for note in notes:
                reasons.append(note)
                warnings[f"Page {system.page}: solo/feature '{phrase.text}': {note}"] = None
            bar, certain = system.bar_at(phrase.x0)
            if bar is None:
                reasons.append("no bar number found on this system")
            elif certain:
                confidence += BAR_FOUND
                reasons.append(f"nearest bar number {bar}")
            else:
                confidence += BAR_GUESSED
                reasons.append(f"text sits left of every bar number; assumed first bar {bar}")
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
    return features, list(warnings)
