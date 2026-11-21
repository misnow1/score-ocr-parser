"""Layout stage: systems, staff bands, bar numbers, rehearsal marks and text phrases.

Staff bands come from the label column at the left margin; each stack of labels
(split at a large vertical gap) is one system.
"""

import re
from dataclasses import dataclass, field
from functools import cache

from .layout import LINE_TOLERANCE, label_stacks, lines
from .data import load
from .models import Page, Token

PHRASE_GAP = 20.0  # horizontal gap that separates two annotations on one line
X_SLACK = 2.0  # horizontal tolerance when comparing positions
BAR_ROW_REACH = 60.0  # how far above the top staff a bar number may sit
_NUMBER = re.compile(r"^\d{1,3}$")
_CAPITAL = re.compile(r"^[A-Z]$")


@dataclass
class Phrase:
    text: str
    x0: float
    yc: float


@dataclass
class Staff:
    label: str
    yc: float


@dataclass
class System:
    page: int
    index: int
    staves: list[Staff]
    bars: list[tuple[float, int]] = field(default_factory=list)
    marks: list[tuple[float, str]] = field(default_factory=list)
    texts: list[Phrase] = field(default_factory=list)

    def staff_for(self, yc: float) -> Staff:
        """The staff a text above a staff belongs to: the first one at or below it."""
        return next((s for s in self.staves if s.yc >= yc - LINE_TOLERANCE), self.staves[-1])

    def bar_at(self, x: float) -> tuple[int | None, bool]:
        """(bar number, certain). The last bar number at or left of x; when the
        text sits left of every bar number, the first bar with certain False."""
        before = [b for bx, b in self.bars if bx <= x + X_SLACK]
        if before:
            return before[-1], True
        return (self.bars[0][1], False) if self.bars else (None, True)


@cache
def _rehearsal_words() -> frozenset[str]:
    data = load("rehearsal_words.yaml")
    return frozenset(w.lower() for w in data["rehearsal_words"])


def _phrases(row: list[Token]) -> list[list[Token]]:
    groups = [[row[0]]]
    for tok in row[1:]:
        if tok.x0 - groups[-1][-1].x1 > PHRASE_GAP:
            groups.append([tok])
        else:
            groups[-1].append(tok)
    return groups


def find_systems(page: Page) -> list[System]:
    stacks = label_stacks(page)
    if not stacks:
        return []
    label_tokens = {id(t) for stack in stacks for ln in stack for t in ln.tokens}
    other_rows = [
        ln for ln in lines(page.tokens) if not any(id(t) in label_tokens for t in ln)
    ]
    systems = [
        System(page.number, i, [Staff(ln.text, ln.yc) for ln in stack])
        for i, stack in enumerate(stacks)
    ]
    for row in other_rows:
        owner = min(systems, key=lambda s: _distance(s, row[0].yc))
        _place(owner, row)
    return systems


def _distance(system: System, yc: float) -> float:
    """Zero inside the system's staff span; text above a system belongs to it."""
    top, bottom = system.staves[0].yc, system.staves[-1].yc
    if yc > bottom:
        return yc - bottom + 1000  # below a system: prefer the system underneath
    return max(0.0, top - yc)


def _place(system: System, row: list[Token]) -> None:
    top = system.staves[0].yc
    for phrase in _phrases(row):
        yc = phrase[0].yc
        if _NUMBER.match(phrase[0].text) and len(phrase) > 1:
            system.bars.append((phrase[0].x0, int(phrase[0].text)))  # glued "29ALTO SOLO"
            phrase = phrase[1:]
        elif len(phrase) == 1 and _NUMBER.match(phrase[0].text):
            if top - BAR_ROW_REACH <= yc <= top:
                system.bars.append((phrase[0].x0, int(phrase[0].text)))
            continue
        text = " ".join(t.text for t in phrase)
        if yc < top and (_CAPITAL.match(text) or text.lower() in _rehearsal_words()):
            system.marks.append((phrase[0].x0, text))
            continue
        system.texts.append(Phrase(text, phrase[0].x0, yc))
    system.bars.sort()
    system.marks.sort()
