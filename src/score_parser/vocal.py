"""Vocal lead markings: the voice and section read from text or a staff label.

A vocal lead is a feature, never an instrument. Two things mark one: a text
such as "Female Lead Verse 1", and a bare "solo" above a "Voice Lead F" or
"Voice Lead M" staff. A "Voice bck" (backing vocal) staff is not a lead.
"""

import re
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
