"""Vocal lead handover: who sings alone, bar by bar, read from the lyric words
under the "Voice Lead F" and "Voice Lead M" staves (no wording needed).

A lead staff sings in a bar when enough lyric words sit under it there. A bar
where exactly one lead staff sings and the other is quiet belongs to that
voice. The voice comes from the staff label alone, never guessed. Needs drawn
barlines and lyrics; a scan, or a score whose voices sing no words, has none.
"""

import re

from .models import Voice
from .systems import System
from .vocal import voice_staff

SUNG_WORDS = 5  # lyric words under a lead staff in one bar that make it a singing bar
QUIET_WORDS = 2  # fewer than this under the other lead staff: quiet
LYRIC_BAND = (0.2, 0.55)  # of the gap to the next staff, below a staff's centre: where its lyrics sit
_DYNAMIC = re.compile(r"^(?:[mfpsz]{1,4}|cresc|decresc|dim)\.?$", re.I)


def _is_word(text: str) -> bool:
    """A lyric syllable: some letters, and not a dynamic marking ("mf", "cresc.")."""
    return bool(re.search(r"[A-Za-z]", text)) and not _DYNAMIC.match(text)


def lead_staves(system: System) -> dict[Voice, int]:
    """Voice -> index of its "Voice Lead" staff, only when the system has two or
    more voices (one lead staff alone has nobody to hand over from)."""
    found: dict[Voice, int] = {}
    for i, staff in enumerate(system.staves):
        role = voice_staff(staff.label) if staff.voice else None
        if role and role[0] == "lead" and role[1]:
            found.setdefault(role[1], i)
    return found if len(found) >= 2 else {}


def _words_under(system: System, index: int, left: float, right: float) -> int:
    """Lyric words under staff `index` between two x positions."""
    staves = system.staves
    top = staves[index].yc
    gap = staves[index + 1].yc - top if index + 1 < len(staves) else top - staves[index - 1].yc
    lo, hi = top + LYRIC_BAND[0] * gap, top + LYRIC_BAND[1] * gap
    return sum(1 for t in system.tokens if lo <= t.yc < hi and left <= t.x0 < right and _is_word(t.text))


def sole_leads(system: System) -> list[tuple[float, Voice, str]]:
    """(x just inside the bar, voice, staff label) for each bar of `system`, left
    to right, in which one lead staff sings alone: it has at least SUNG_WORDS
    words and every other lead staff fewer than QUIET_WORDS."""
    leads = lead_staves(system)
    edges = sorted(system.barlines)
    found = []
    for left, right in zip(edges, edges[1:]):
        words = {v: _words_under(system, i, left, right) for v, i in leads.items()}
        singing = [v for v, n in words.items() if n >= SUNG_WORDS and all(m < QUIET_WORDS for w, m in words.items() if w != v)]
        if len(singing) == 1:
            found.append((left + 1, singing[0], system.staves[leads[singing[0]]].label))
    return found
