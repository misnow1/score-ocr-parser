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
_NUMBER = re.compile(r"^\d{1,3}$")
_CAPITAL = re.compile(r"^[A-Z]$")


class HasMarks(Protocol):
    page: int
    index: int
    marks: list[tuple[float, str]]


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


def current_mark(systems: list[HasMarks], system: HasMarks, x: float) -> str | None:
    """Latest rehearsal mark at or before (page, system, x) in reading order."""
    current = None
    for s in systems:
        if (s.page, s.index) > (system.page, system.index):
            break
        for mx, text in s.marks:
            if (s.page, s.index) < (system.page, system.index) or mx <= x + X_SLACK:
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
    if _NUMBER.match(phrase[0].text) and len(phrase) > 1:
        bar = (phrase[0].x0, int(phrase[0].text))  # glued "29ALTO SOLO"
        phrase = phrase[1:]
    elif len(phrase) == 1 and _NUMBER.match(phrase[0].text):
        if top - BAR_ROW_REACH <= yc <= top and not is_page_number(phrase[0].text, phrase[0].x0):
            bar = (phrase[0].x0, int(phrase[0].text))
        return bar, None, None
    text = " ".join(t.text for t in phrase)
    if yc < top and (_CAPITAL.match(text) or text.lower() in _rehearsal_words()):
        return bar, (phrase[0].x0, text), None
    return bar, None, phrase
