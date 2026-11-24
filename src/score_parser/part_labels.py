"""Staff-start bar numbers of a part that prints them both above and under a staff.

A part prints the bar a staff starts at near its left end, usually above the
staff. Some also print it under the staff, and then the number under one staff
and the number above the next can sit in one spot, one on top of the other
(a "B" number below: one that sits in both the band above a staff and the band
under the staff before it). Read top to bottom, the gap between two staves of
different systems holds:

- two different B numbers (an overprinted pair): the lower is the staff above's
  and the higher the next staff's. The pair is accepted only on evidence that
  the lower is a bar number and not a stray digit (a volta, a cue's chair, a
  tempo): it is the staff above's own label, or counting the staff before it
  reaches it, or counting the staff above from it reaches the higher. When that
  last count does reach the higher, the pair is confirmed;
- one B number that repeats the label of the staff above and sits closer to that
  staff than to the next: that staff's own number, printed twice.

Staves of one system (joined by barlines) share their bars, so they never make
a pair or a repeat. Every other number is left to the plain bar-row reading,
which reads a number above a staff as its label.
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
    confirmed: bool = False  # the staff above counted from the lower number reaches the higher


def bars_in(barlines: list[float], rests: list[tuple[float, int]]) -> int:
    """The bars of one staff: its barline intervals, a multi-bar rest counting as many as it holds."""
    count = BarCount(barlines)
    for x, bars in rests:
        count.add_rest(x, bars)
    return count.bar_count


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
    staves: list[Staff], numbers: list[Token], lengths: list[int], joined: list[bool]
) -> tuple[list[StartLabel | None], list[list[Token]], list[Token]]:
    """(the label of each staff, None when it prints none; the numbers placed at
    each staff's start by the pair rule; every number the pair and repeat rules
    consumed). `lengths` are the bars of each staff and `joined[i]` says that
    staff i shares its bars with the staff before. A number outside the rules
    is in none of the lists, and the plain bar-row reading handles it."""
    gaps: dict[int, list[tuple[Token, bool]]] = {}
    for tok in numbers:
        if _is_number(tok) and (found := _gap_of(staves, tok)):
            gaps.setdefault(found[0], []).append((tok, found[1]))
    labels: list[StartLabel | None] = [None] * len(staves)
    placed: list[list[Token]] = [[] for _ in staves]
    consumed: list[Token] = []

    def label(index: int, tok: Token, pair: tuple[int, int] | None = None, confirmed: bool = False) -> None:
        if labels[index] is None or pair or int(tok.text) > labels[index].number:
            labels[index] = StartLabel(tok, int(tok.text), pair, confirmed)

    def place(index: int, tok: Token) -> None:
        placed[index].append(tok)
        consumed.append(tok)

    def counts_to(index: int, number: int) -> bool:
        """Whether the staff before `index` has a label that counts on to `number`."""
        before = labels[index - 1] if index > 0 else None
        return before is not None and before.number + lengths[index - 1] == number

    for k in sorted(gaps):
        j = k - 1
        under = [t for t, below in gaps[k] if below]
        values = sorted({int(t.text) for t in under})
        own = labels[j].number if j >= 0 and labels[j] else None
        if j >= 0 and not joined[k]:
            if len(values) == 2:
                low, high = values
                reaches = low + lengths[j] == high
                if own == low or counts_to(j, low) or reaches:
                    for tok in sorted(under, key=lambda t: t.x0):
                        if int(tok.text) == high:
                            place(k, tok)
                            label(k, tok, (low, high), reaches)
                        else:
                            place(j, tok)
                            label(j, tok)
            elif values and own == values[0]:
                near = [t for t in under if t.y0 - staves[j].bottom < staves[k].top - t.y1]
                consumed.extend(near)  # printed twice: the staff above's own number
        for tok, below in gaps[k]:
            if not below:
                label(k, tok)
    return labels, placed, consumed
