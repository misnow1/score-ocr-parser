"""Layout stage: systems and their text phrases.

Each stack of labels at the left margin (split at a large vertical gap) is one
system. Staff assignment lives in `staves`, bar and mark lookup in `measures`.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from .layout import label_stacks, label_token_ids, label_tokens, lines_without
from .measures import bar_at, page_number_zone, read_phrase
from .models import Page, Token
from .staves import Staff, owning_system, staff_at

PHRASE_GAP = 20.0  # horizontal gap that separates two annotations on one line


@dataclass
class Phrase:
    text: str
    x0: float
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
        return staff_at(self.staves, yc)

    def bar_at(self, x: float) -> tuple[int | None, bool]:
        return bar_at(self.bars, x)


def _phrases(row: list[Token]) -> list[list[Token]]:
    groups = [[row[0]]]
    for tok in row[1:]:
        if tok.x0 - groups[-1][-1].x1 > PHRASE_GAP:
            groups.append([tok])
        else:
            groups[-1].append(tok)
    return groups


def find_systems(page: Page, headers: frozenset[str] = frozenset()) -> list[System]:
    stacks = label_stacks(page, headers)
    if not stacks:
        return []
    label_ids = label_token_ids(stacks)
    other_rows = lines_without(page.tokens, label_ids)
    systems = [
        System(page.number, i, [Staff(ln.text, ln.yc) for ln in stack])
        for i, stack in enumerate(stacks)
    ]
    label_right = max(t.x1 for t in label_tokens(stacks))
    is_page_number = page_number_zone(page, label_right)
    for row in other_rows:
        owner = owning_system(systems, row[0].yc)
        _place(owner, row, is_page_number)
    return systems


def _place(system: System, row: list[Token], is_page_number: Callable[[str, float], bool]) -> None:
    top = system.staves[0].yc
    for phrase in _phrases(row):
        bar, mark, rest = read_phrase(phrase, top, is_page_number)
        if bar:
            system.bars.append(bar)
        if mark:
            system.marks.append(mark)
        if rest:
            system.texts.append(Phrase(" ".join(t.text for t in rest), rest[0].x0, rest[0].yc))
    system.bars.sort()
    system.marks.sort()
