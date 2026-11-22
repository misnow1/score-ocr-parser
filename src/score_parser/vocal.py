"""Vocal lead markings: the voice and section read from text or a staff label.

A vocal lead is a feature, never an instrument. Two things mark one: a text
such as "Female Lead Verse 1", and a bare "solo" above a "Voice Lead F" or
"Voice Lead M" staff. A "Voice bck" (backing vocal) staff is not a lead.

Voice staves are the staves of a vocal part: a "Voice Lead F" staff, a choir
label ("SATB", "TB"), a run of part abbreviations ("A.", "Bar.") and the staves
printed under a "VOCALS" group label. They are never instruments: `voice_lines`
is the one place that decides which lines of a label stack are voice staves.
"""

import re
from collections.abc import Sequence
from statistics import median
from typing import Literal

from .models import Voice

_LEAD_TEXT = re.compile(r"^\s*(female|male)\s+lead\b\s*(.*?)\s*$", re.I)
_VOICE_STAFF = re.compile(r"^\s*voice\s+(lead|bck|back)\b\s*([FM])?\s*$", re.I)
_VOICES: dict[str, Voice] = {"f": "female", "m": "male", "female": "female", "male": "male"}

StaffRole = Literal["lead", "backing"]


def lead_text(text: str) -> tuple[Voice, str | None] | None:
    """(voice, section) for "Female Lead Verse 1"; section is None when absent."""
    m = _LEAD_TEXT.match(text)
    if not m:
        return None
    section = re.sub(r"\s*\bsolo\b\s*$", "", m.group(2), flags=re.I).strip()
    return _VOICES[m.group(1).lower()], section or None


def voice_staff(label: str) -> tuple[StaffRole, Voice | None] | None:
    """(role, voice) for a "Voice Lead F" or "Voice bck M" staff label, else None."""
    m = _VOICE_STAFF.match(label)
    if not m:
        return None
    role: StaffRole = "lead" if m.group(1).lower() == "lead" else "backing"
    return role, _VOICES[m.group(2).lower()] if m.group(2) else None


_CHOIR_WORD = re.compile(r"^\s*(?:choir|chorus|voices)\s*$", re.I)
_CHOIR_LETTERS = re.compile(r"^(?=[SATB ]{2,})S*\s*A*\s*T*\s*B*$")  # SATB, TB, TTBB in voice order, capitals only: "BASS" is not one
_VOICE_PART = re.compile(r"^\s*(?:s|a|t|b|sop|alt|ten|bar|baritone)\.?\s*$", re.I)
_GROUP = re.compile(r"^\s*(?:vocals?|voices?|vox)\s*$", re.I)
_GROUP_TIGHTNESS = 0.75  # a group label sits closer to its staves than staves sit to each other


def is_choir_label(label: str) -> bool:
    """A choir label ("SATB", "TB", "Choir"). Always a voice staff."""
    return bool(_CHOIR_WORD.match(label) or _CHOIR_LETTERS.match(label.strip()))


def voice_lines(labels: Sequence[str], ys: Sequence[float]) -> set[int]:
    """Indices of the lines of one label stack (top to bottom, `ys` their vertical
    centres) that are voice staves or the group label above them.

    A line is a voice line when it is a Voice Lead/bck staff or a choir label; when
    it is one of two or more neighbouring part abbreviations ("A.", "Bar."); or
    when it is a "VOCALS" group label printed between two staves, closer to both
    than staves are to each other (the staves above and below it are the group's).
    A lone "Vocals" staff at the usual spacing is the lead vocal instrument."""
    found = {i for i, text in enumerate(labels) if voice_staff(text) or is_choir_label(text)}
    parts = [bool(_VOICE_PART.match(text)) for text in labels]
    found |= {i for i, p in enumerate(parts) if p and (i > 0 and parts[i - 1] or i + 1 < len(parts) and parts[i + 1])}
    gaps = [b - a for a, b in zip(ys, ys[1:])]
    typical = median(gaps) if gaps else 0.0
    for i, text in enumerate(labels):
        if _GROUP.match(text) and 0 < i < len(labels) - 1:
            if max(ys[i] - ys[i - 1], ys[i + 1] - ys[i]) < _GROUP_TIGHTNESS * typical:
                found |= {i - 1, i, i + 1}
    return found
