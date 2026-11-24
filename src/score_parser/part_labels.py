"""Staff-start bar numbers of a part that prints them both above and under a staff.

A part prints the bar a staff starts at near its left end, usually above the
staff. Some also print it under the staff, and then the number under one staff
and the number above the next can sit in one spot, one on top of the other
(a "B" number below: one that sits in both the band above a staff and the band
under the staff before it). Read top to bottom, a gap between two staves holds:

- two different B numbers (an overprinted pair): the lower is the staff above's
  and the higher the next staff's. The higher is checked by counting the bars of
  the staff above from its own number, multi-bar rests included;
- one B number that repeats the label of the staff above: that staff's own
  number, printed twice, and not the next staff's.

Every other number is left to the plain bar-row reading, which reads a number
above a staff as its label.
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


def _gap_of(staves: list[Staff], tok: Token) -> tuple[int, bool] | None:
    """(the staff below, whether it also sits under the staff before) for a
    number at the left end of a staff, in the band above that staff, or None. A
    number inside a staff's span is the time signature or a key, not a label."""
    yc = tok.yc
    k = next((i for i, s in enumerate(staves) if yc < s.top), len(staves))
    j = k - 1
    if j >= 0 and yc <= staves[j].bottom:
        return None
    if k == len(staves) or not above_top(staves[k].top, yc) or tok.x0 > staves[k].left + START_REACH:
        return None
    return k, j >= 0 and below_bottom(staves[j].bottom, yc) and tok.x0 <= staves[j].left + START_REACH


def read_start_labels(
    staves: list[Staff], numbers: list[Token]
) -> tuple[list[StartLabel | None], list[list[Token]], list[Token]]:
    """(the label of each staff, None when it prints none; the numbers placed at
    each staff's start by the pair and repeat rules above; every number those
    rules consumed, repeats included). A number outside them is in none of the
    lists, and the plain bar-row reading handles it."""
    gaps: dict[int, list[tuple[Token, bool]]] = {}
    for tok in numbers:
        if _is_number(tok) and (found := _gap_of(staves, tok)):
            gaps.setdefault(found[0], []).append((tok, found[1]))
    labels: list[StartLabel | None] = [None] * len(staves)
    placed: list[list[Token]] = [[] for _ in staves]
    consumed: list[Token] = []

    def label(index: int, tok: Token, pair: tuple[int, int] | None = None, place: bool = True) -> None:
        if place:
            placed[index].append(tok)
            consumed.append(tok)
        if labels[index] is None or pair or int(tok.text) > labels[index].number:
            labels[index] = StartLabel(tok, int(tok.text), pair)

    for k in sorted(gaps):
        j = k - 1
        above = [t for t, under in gaps[k] if not under]
        under = [t for t, under in gaps[k] if under]
        values = sorted({int(t.text) for t in under})
        own = labels[j].number if j >= 0 and labels[j] else None
        if len(values) >= 2:
            for tok in sorted(under, key=lambda t: t.x0):
                if int(tok.text) == values[-1]:
                    label(k, tok, (values[0], values[-1]))
                elif own in (None, int(tok.text)):
                    label(j, tok)
        elif values and own == values[0]:
            consumed.extend(under)  # printed twice: the staff above's own number
        for tok in above:
            label(k, tok, place=False)
    return labels, placed, consumed


def confirmed(label: StartLabel, previous: StartLabel | None, barlines: list[float], rests: list[tuple[float, int]]) -> bool:
    """Whether counting the bars of the staff before from its own number reaches
    an overprinted pair's higher number."""
    if previous is None or label.pair is None:
        return False
    count = BarCount(barlines)
    for x, bars in rests:
        count.add_rest(x, bars)
    return previous.number + count.bar_count == label.number
