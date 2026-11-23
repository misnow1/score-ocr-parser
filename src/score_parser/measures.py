"""Measure and mark lookup: bar numbers and rehearsal marks by position.

Bar numbers and marks are read from the text above a system's top staff. The
lookups turn (page, system, x position) into a bar number or current mark.
"""

import re
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from typing import Literal, NamedTuple, Protocol

from .data import load
from .models import Page, Token

X_SLACK = 2.0  # horizontal tolerance when comparing positions
PAGE_NUMBER_MARGIN = 0.9  # right margin starts at this fraction of the page width
BAR_ROW_REACH = 60.0  # how far above the top staff a bar number may sit
BAR_ROW_MIN = 6.0  # a bar number sits above the staff; a time signature sits on it
BAR_ROW_BELOW_MIN = 4.0  # numbers printed under a system start this far under its bottom staff...
BAR_ROW_BELOW_REACH = 25.0  # ...and end this far under it
BARLINE_MERGE = 4.0  # rules this close are one barline (double and final barlines)
SPAN_TOLERANCE = 4.0  # slack when asking whether a drawn rule crosses a staff
IN_BAR_MARGIN = 6.0  # a number this far clear of both barlines of a bar sits inside it, not on a barline
SNAP_REACH = 25.0  # a bar number sits within this of the barline it numbers
_NUMBER = re.compile(r"^\d{1,3}$")
_CAPITAL = re.compile(r"^[A-Z]$")


class HasMarks(Protocol):
    page: int
    index: int
    marks: list[tuple[float, str]]


class HasBars(Protocol):
    bars: list[tuple[float, int, float]]  # (x0, number, x1)


# How a bar was found: counted from a printed number by barlines, continued from
# the previous system, read as the nearest printed number (text sits left of
# every number: "assumed"), the same on an OCR page, or not found.
BarKind = Literal["counted", "continued", "nearest", "assumed", "ocr", "missing"]


class BarReading(NamedTuple):
    bar: int | None
    kind: BarKind
    reason: str


@cache
def _rehearsal_words() -> frozenset[str]:
    data = load("rehearsal_words.yaml")
    return frozenset(w.lower() for w in data["rehearsal_words"])


def bar_at(bars: list[tuple[float, int, float]], x: float) -> BarReading:
    """The last bar number at or left of x; when the text sits left of every
    bar number, the first bar, assumed."""
    before = [b for bx, b, _ in bars if bx <= x + X_SLACK]
    if before:
        return BarReading(before[-1], "nearest", f"nearest bar number {before[-1]}")
    if bars:
        first = bars[0][1]
        return BarReading(first, "assumed", f"text sits left of every bar number; assumed first bar {first}")
    return BarReading(None, "missing", "no bar number found on this system")


def merge_barlines(xs: list[float]) -> list[float]:
    """Sorted barline positions, rules within BARLINE_MERGE merged (the left one kept)."""
    merged: list[float] = []
    for x in sorted(xs):
        if not merged or x - merged[-1] > BARLINE_MERGE:
            merged.append(x)
    return merged


def barlines_through(rules: list[tuple[float, float, float]], ys: list[float]) -> tuple[list[float], float]:
    """(barlines, y) of a system whose staves sit at `ys`: the drawn vertical
    rules crossing the first staff that two or more cross. A label that is no
    staff (a tempo mark above the first one) has none. Staff by staff, not the
    union: stems drawn as rules cross some staves and are not barlines."""
    for y in ys:
        xs = merge_barlines([x for x, y0, y1 in rules if y0 - SPAN_TOLERANCE <= y <= y1 + SPAN_TOLERANCE])
        if len(xs) >= 2:
            return xs, y
    return [], ys[0]


def share_barlines(rules: list[tuple[float, float, float]], upper: float, lower: float) -> bool:
    """Whether two stacks, with top staves at `upper` and `lower`, are one row of
    bars: at least two distinct rules run unbroken from one to the other (one
    alone may be a connector line along the left edge)."""
    spanning = [x for x, y0, y1 in rules if y0 - SPAN_TOLERANCE <= upper and y1 + SPAN_TOLERANCE >= lower]
    return len(merge_barlines(spanning)) >= 2


def snap_to_barline(barlines: list[float], x0: float, x1: float) -> int | None:
    """Index of the barline that starts the bar a number numbers, or None when
    none is near. Numbers are centred on a barline or start just right of it
    (the nearest barline); some scores centre each number inside its bar (the
    barline to its left, when the number is clear of both)."""
    inside = max(0, bisect_right(barlines, x0) - 1)
    if inside + 1 < len(barlines) and x0 - barlines[inside] >= IN_BAR_MARGIN and barlines[inside + 1] - x1 >= IN_BAR_MARGIN:
        return inside
    centre = (x0 + x1) / 2
    best = min(range(len(barlines)), key=lambda i: abs(barlines[i] - centre), default=None)
    if best is None or abs(barlines[best] - centre) > SNAP_REACH:
        return None
    return best


def _interval(barlines: list[float], x: float) -> int:
    """Index of the bar (counted from the first barline) that x falls in."""
    return max(0, bisect_right(barlines, x + X_SLACK) - 1)


@dataclass
class BarCount:
    """Bar numbers by counting barlines on one row of bars. Bar i starts at
    barline i. `anchors` are the printed numbers as (barline index, number);
    with none, `carried` is the number of bar 0 continued from the row before."""

    barlines: list[float]
    anchors: list[tuple[int, int]] = field(default_factory=list)
    carried: int | None = None
    carried_from: str = "the previous system"
    # Parts: a multi-bar rest is one interval that holds several bars; this
    # maps the interval to the extra bars it holds.
    skipped: dict[int, int] = field(default_factory=dict)

    def add_rest(self, x: float, bars: int) -> None:
        """A rest of `bars` bars drawn at x fills the interval it sits in."""
        i = _interval(self.barlines, x)
        self.skipped[i] = max(self.skipped.get(i, 0), bars - 1)

    def _extra_before(self, i: int) -> int:
        return sum(extra for k, extra in self.skipped.items() if k < i)

    def bars_after(self, idx: int) -> int:
        """Bars from the start of interval `idx` to the end of the row."""
        return len(self.barlines) - 1 - idx + sum(e for k, e in self.skipped.items() if k >= idx)

    def bar_at(self, x: float) -> BarReading | None:
        i = _interval(self.barlines, x)
        if self.anchors:
            before = [a for a in self.anchors if a[0] <= i]
            idx, number = before[-1] if before else self.anchors[0]
            bar = number + (i - idx) + self._extra_before(i) - self._extra_before(idx)
            away = abs(i - idx)
            if away == 0:
                return BarReading(bar, "counted", f"nearest bar number {number}")
            plural = "barline" if away == 1 else "barlines"
            direction = "back from" if i < idx else "from"
            rests = abs(self._extra_before(i) - self._extra_before(idx))
            plus = f" plus {rests} bars of multi-bar rests" if rests else ""
            return BarReading(bar, "counted", f"counted {away} {plural}{plus} {direction} printed bar {number}: bar {bar}")
        if self.carried is not None:
            bar = self.carried + i + self._extra_before(i)
            rests = self._extra_before(i)
            plus = f" plus {rests} bars of multi-bar rests" if rests else ""
            return BarReading(
                bar, "continued",
                f"no bar number printed here; counted barlines{plus} on from {self.carried_from}: bar {bar}",
            )
        return None

    def in_first_bar(self, x: float) -> bool:
        return _interval(self.barlines, x) == 0

    @property
    def bar_count(self) -> int:
        return self.bars_after(0)


class HasRow(Protocol):
    bars: list[tuple[float, int, float]]
    rests: list[tuple[float, int]]
    barlines: list[float]
    joins_previous: bool
    count: BarCount | None
    row: int


def count_bars(systems: list[HasRow]) -> None:
    """Give each system its `count`, in reading order. Stacks on one row of bars
    share a count and their printed numbers. A row without a printed number
    continues from the bars of the row before; a row with no barlines (OCR, or
    none drawn) has no count and breaks that chain."""
    rows: list[list[HasRow]] = []
    for s in systems:
        if rows and s.joins_previous:
            rows[-1].append(s)
        else:
            rows.append([s])
    for number, row in enumerate(rows):
        for s in row:
            s.row = number
    running: int | None = 1  # the number the next row's first bar has, when known
    for row in rows:
        barlines = row[0].barlines
        if len(barlines) < 2:
            running = None
            continue
        anchors = sorted(
            (idx, n)
            for s in row
            for x0, n, x1 in s.bars
            if (idx := snap_to_barline(barlines, x0, x1)) is not None
        )
        count = BarCount(barlines, anchors)
        for s in row:
            for x, bars in s.rests:
                count.add_rest(x, bars)
        if anchors:
            idx, n = anchors[-1]
            running = n + count.bars_after(idx)
        elif running is not None:
            count.carried = running
            if row is rows[0]:
                count.carried_from = "the start of the score (bar 1)"
            running += count.bar_count
        for s in row:
            s.count = count if (count.anchors or count.carried is not None) else None


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


class MarkReading(NamedTuple):
    text: str
    page: int  # where it is printed; before the feature's own page when carried


def current_mark(systems: list[HasMarks], system: HasMarks, x: float) -> MarkReading | None:
    """The mark in force at (page, system, x): the latest one at or before it in
    reading order, on this page or an earlier one (ADR 0003). None before the
    first mark of the score."""
    current = None
    for s in systems:
        order, here = (s.page, s.index), (system.page, system.index)  # `index` counts per page
        if order > here:
            break
        for mx, text in s.marks:
            if order < here or mx <= x + X_SLACK:
                current = MarkReading(text, s.page)
    return current


def below_bottom(staves_bottom: float, yc: float) -> bool:
    """Whether a text line at yc sits in the band of bar numbers under a staff at `staves_bottom`."""
    return staves_bottom + BAR_ROW_BELOW_MIN <= yc <= staves_bottom + BAR_ROW_BELOW_REACH


def above_top(top: float, yc: float) -> bool:
    """Whether a text line at yc sits in the band of bar numbers above a staff at `top`."""
    return top - BAR_ROW_REACH <= yc <= top - BAR_ROW_MIN


def page_number_zone(page: Page, label_right: float) -> Callable[[str, float], bool]:
    """Whether a number at x0 sits where a page number does: in the label
    column or the right margin. Only a number equal to the page's own is dropped."""

    def is_page_number_here(text: str, x0: float) -> bool:
        return text == str(page.number) and (x0 < label_right or x0 > PAGE_NUMBER_MARGIN * page.width)

    return is_page_number_here


def read_phrase(
    phrase: list[Token], top: float, is_page_number: Callable[[str, float], bool], bottom: float | None = None
) -> tuple[tuple[float, int, float] | None, tuple[float, str] | None, list[Token] | None]:
    """Split one phrase near a system whose top staff is at `top` into
    (bar number, rehearsal mark, remaining text phrase). With `bottom` (the
    bottom staff's y), a number counts when it sits just under that staff, not
    above the top one. A glued "29ALTO SOLO"
    yields the bar and the rest; a lone number yields only a bar (or nothing)."""
    yc = phrase[0].yc
    bar = None
    if _NUMBER.match(phrase[0].text):
        first = phrase[0]
        if bottom is None:
            in_band = top - BAR_ROW_REACH <= yc <= top - BAR_ROW_MIN
        else:
            in_band = bottom + BAR_ROW_BELOW_MIN <= yc <= bottom + BAR_ROW_BELOW_REACH
        fits = in_band and not is_page_number(first.text, first.x0)
        if fits:
            bar = (first.x0, int(first.text), first.x1)
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
