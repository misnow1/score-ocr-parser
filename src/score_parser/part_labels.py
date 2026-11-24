"""Staff-start bar numbers of a part, read as a sequence down the page.

A part prints the bar a staff starts at near its left end. Some parts print it
above the staff and some under the staff before it, and when both are printed
the pair can sit in one spot: a number under one staff and the number above the
next, one on top of the other. A single number in the gap between two staves is
then either the next staff's label or the first staff's, so the gaps are read
top to bottom: a number that repeats the label of the staff above it is that
staff's, and two different numbers in one gap are the first staff's (the lower)
and the next staff's (the higher). Whether the pair is right is checked by
counting the bars of the first staff (multi-bar rests included) from its number
to the next one.
"""

from dataclasses import dataclass
from typing import Protocol

from .measures import BarCount, above_top, below_bottom
from .models import Token

START_REACH = 30.0  # a bar number this near the staff's left end numbers its first bar


class Staff(Protocol):
    """What the labels need of a staff: its span and its left end."""

    top: float
    bottom: float
    left: float


@dataclass
class StartLabel:
    token: Token
    number: int
    pair: tuple[int, int] | None = None  # (lower, higher) when the label was overprinted


def _is_number(tok: Token) -> bool:
    return tok.text.isdigit() and len(tok.text) <= 3


def _gap_of(staves: list[Staff], tok: Token) -> tuple[int, bool, bool] | None:
    """(gap, above, under) for a number at the left end of a staff, or None. The
    gap is the index of the staff below the number (len(staves) under the last
    one); `above` and `under` say whether it sits in the band above that staff
    and in the band under the staff before it. A number inside a staff's span
    is the time signature or a key, not a label."""
    yc = tok.yc
    k = next((i for i, s in enumerate(staves) if yc < s.top), len(staves))
    j = k - 1
    if j >= 0 and yc <= staves[j].bottom:
        return None
    above = k < len(staves) and above_top(staves[k].top, yc) and tok.x0 <= staves[k].left + START_REACH
    under = j >= 0 and below_bottom(staves[j].bottom, yc) and tok.x0 <= staves[j].left + START_REACH
    if not (above or under):
        return None
    return k, above, under


def read_start_labels(staves: list[Staff], numbers: list[Token]) -> tuple[list[StartLabel | None], list[Token]]:
    """(the label of each staff, None when it prints none; every number read as
    a staff-start number, repeats of a label included) from the numbers near
    the staves' left ends."""
    gaps: dict[int, list[tuple[Token, bool, bool]]] = {}
    read = []
    for tok in numbers:
        if _is_number(tok) and (found := _gap_of(staves, tok)):
            gaps.setdefault(found[0], []).append((tok, found[1], found[2]))
            read.append(tok)
    labels: list[StartLabel | None] = [None] * len(staves)

    def give(index: int, tok: Token, pair: tuple[int, int] | None = None) -> None:
        if 0 <= index < len(staves) and labels[index] is None:
            labels[index] = StartLabel(tok, int(tok.text), pair)

    for k in sorted(gaps):
        j = k - 1
        values = sorted({int(t.text) for t, _, _ in gaps[k]})
        own = labels[j].number if j >= 0 and labels[j] else None
        for tok, above, under in sorted(gaps[k], key=lambda e: e[0].x0):
            value = int(tok.text)
            if not under:
                give(k, tok)
            elif not above:
                if own in (None, value):
                    give(j, tok)
            elif len(values) > 1:
                if value == values[-1]:
                    give(k, tok, (values[0], value))
                elif own in (None, value):
                    give(j, tok)
            elif own != value:
                give(k, tok)
    return labels, read


def confirmed(label: StartLabel, previous: StartLabel | None, barlines: list[float], rests: list[tuple[float, int]]) -> bool:
    """Whether counting the bars of the staff before from its own number reaches
    an overprinted pair's higher number."""
    if previous is None or label.pair is None:
        return False
    count = BarCount(barlines)
    for x, bars in rests:
        count.add_rest(x, bars)
    return previous.number + count.bar_count == label.number
