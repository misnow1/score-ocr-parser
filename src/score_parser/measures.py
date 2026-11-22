"""Measure and mark lookup: bar numbers and rehearsal marks by position.

Bar numbers and marks are read from the text above a system's top staff. The
lookups turn (page, system, x position) into a bar number or current mark.
"""

import re
from collections.abc import Callable
from functools import cache
from typing import Protocol

from .data import load
from .models import Page, Token

X_SLACK = 2.0  # horizontal tolerance when comparing positions
PAGE_NUMBER_MARGIN = 0.9  # right margin starts at this fraction of the page width
BAR_ROW_REACH = 60.0  # how far above the top staff a bar number may sit
BAR_ROW_MIN = 6.0  # a bar number sits above the staff; a time signature sits on it
_NUMBER = re.compile(r"^\d{1,3}$")
_CAPITAL = re.compile(r"^[A-Z]$")


class HasMarks(Protocol):
    page: int
    index: int
    marks: list[tuple[float, str]]


class HasBars(Protocol):
    bars: list[tuple[float, int]]


@cache
def _rehearsal_words() -> frozenset[str]:
    data = load("rehearsal_words.yaml")
    return frozenset(w.lower() for w in data["rehearsal_words"])


def bar_at(bars: list[tuple[float, int]], x: float) -> tuple[int | None, bool]:
    """(bar number, certain). The last bar number at or left of x; when the
    text sits left of every bar number, the first bar with certain False."""
    before = [b for bx, b in bars if bx <= x + X_SLACK]
    if before:
        return before[-1], True
    return (bars[0][1], False) if bars else (None, True)


def drop_out_of_sequence(systems: list[HasBars]) -> None:
    """Bar numbers rise through a score, so a number that breaks the longest
    non-decreasing run in reading order (a triplet 3 among bars in the 40s) is
    not a bar number. Drops those from each system in place."""
    flat = [(i, entry) for i, s in enumerate(systems) for entry in s.bars]
    keep = _longest_non_decreasing([entry[1] for _, entry in flat])
    for s in systems:
        s.bars.clear()
    for k in keep:
        i, entry = flat[k]
        systems[i].bars.append(entry)


def _longest_non_decreasing(values: list[int]) -> list[int]:
    """Indices of a longest non-decreasing subsequence of `values` (O(n^2))."""
    best: list[list[int]] = []
    for i, v in enumerate(values):
        prefix: list[int] = []
        for chain in best:
            if values[chain[-1]] <= v and len(chain) > len(prefix):
                prefix = chain
        best.append([*prefix, i])
    return max(best, key=len, default=[])


def current_mark(systems: list[HasMarks], system: HasMarks, x: float) -> str | None:
    """The mark in force at (page, system, x): the latest one at or before it in
    reading order on the same page. A mark never carries onto another page."""
    current = None
    for s in systems:
        if s.page != system.page:
            continue
        if s.index > system.index:
            break
        for mx, text in s.marks:
            if s.index < system.index or mx <= x + X_SLACK:
                current = text
    return current


def page_number_zone(page: Page, label_right: float) -> Callable[[str, float], bool]:
    """Whether a number at x0 sits where a page number does: in the label
    column or the right margin. Only a number equal to the page's own is dropped."""

    def is_page_number_here(text: str, x0: float) -> bool:
        return text == str(page.number) and (x0 < label_right or x0 > PAGE_NUMBER_MARGIN * page.width)

    return is_page_number_here


def read_phrase(
    phrase: list[Token], top: float, is_page_number: Callable[[str, float], bool]
) -> tuple[tuple[float, int] | None, tuple[float, str] | None, list[Token] | None]:
    """Split one phrase near a system whose top staff is at `top` into
    (bar number, rehearsal mark, remaining text phrase). A glued "29ALTO SOLO"
    yields the bar and the rest; a lone number yields only a bar (or nothing)."""
    yc = phrase[0].yc
    bar = None
    if _NUMBER.match(phrase[0].text):
        first = phrase[0]
        fits = top - BAR_ROW_REACH <= yc <= top - BAR_ROW_MIN and not is_page_number(first.text, first.x0)
        if fits:
            bar = (first.x0, int(first.text))
        if len(phrase) == 1:
            return bar, None, None
        phrase = phrase[1:]  # glued "29ALTO SOLO": the number is split off
    if yc < top:
        word = _mark_prefix(phrase)
        if word:
            rest = phrase[len(word):]
            return bar, (phrase[0].x0, " ".join(t.text for t in word)), rest or None
    return bar, None, phrase


def _mark_prefix(phrase: list[Token]) -> list[Token]:
    """The leading tokens of a phrase that form a rehearsal mark (a single
    capital, or the whole phrase when it is a section word), so a mark printed beside a digit or text line
    is split off it; empty when the phrase does not start with one."""
    if _CAPITAL.match(phrase[0].text):
        return phrase[:1]
    text = " ".join(t.text for t in phrase)
    return phrase if text.lower() in _rehearsal_words() else []
