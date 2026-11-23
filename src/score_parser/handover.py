"""Vocal lead handover: who sings alone, bar by bar, read from the lyric words
under the "Voice Lead F" and "Voice Lead M" staves (no wording needed).

A lead staff sings in a bar when enough lyric words sit under it there. A bar
where exactly one lead staff sings and the other is quiet belongs to that
voice, when the voice sings alone again within a few bars (not a one-bar
fill). The voice comes from the staff label alone, never guessed. Needs drawn
barlines and lyrics; a scan, or a score whose voices sing no words, has none.
"""

import re

from .models import Voice
from .systems import System
from .vocal import voice_staff

SUNG_WORDS = 5  # lyric words under a lead staff in one bar that make it a singing bar
QUIET_WORDS = 2  # fewer than this under the other lead staff: quiet
MAX_FILL_GAP = 3  # bars: a voice must sing alone twice this close, or its one bar is a fill
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


def _bar_edges(system: System) -> list[tuple[float, float, float]]:
    """(left, right, x just inside the bar) for each bar of `system`. The first bar
    runs from the left of the system when its left edge was not read as a barline."""
    lines = sorted(system.barlines)
    if not lines:
        return []
    edges = [(float("-inf"), lines[0], lines[0] - 1)]
    edges += [(left, right, left + 1) for left, right in zip(lines, lines[1:])]
    return edges


def sole_leads(system: System) -> list[tuple[float, Voice, str]]:
    """(x just inside the bar, voice, staff label) for each bar of `system`, left
    to right, that belongs to one voice: its lead staff has at least SUNG_WORDS
    words, every other lead staff fewer than QUIET_WORDS, and it sings again
    within MAX_FILL_GAP bars with the other leads quiet all the way (a one-bar
    fill while the other voice holds a note is no handover)."""
    leads = lead_staves(system)
    bars = _bar_edges(system) if leads else []
    words = [{v: _words_under(system, i, left, right) for v, i in leads.items()} for left, right, _ in bars]

    def alone(k: int) -> Voice | None:
        sung = [v for v, n in words[k].items() if n >= SUNG_WORDS and all(m < QUIET_WORDS for w, m in words[k].items() if w != v)]
        return sung[0] if len(sung) == 1 else None

    def quiet_others(voice: Voice, a: int, b: int) -> bool:
        return all(m < QUIET_WORDS for k in range(a, b + 1) for w, m in words[k].items() if w != voice)

    found = []
    for k, (_, _, x) in enumerate(bars):
        voice = alone(k)
        if voice is None:
            continue
        near = range(max(0, k - MAX_FILL_GAP), min(len(bars), k + MAX_FILL_GAP + 1))
        if any(j != k and alone(j) == voice and quiet_others(voice, min(j, k), max(j, k)) for j in near):
            found.append((x, voice, system.staves[leads[voice]].label))
    return found
