"""Layout stage: systems and their text phrases.

Each stack of labels at the left margin (split at a large vertical gap) is one
system. Staff assignment lives in `staves`, bar and mark lookup in `measures`.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from .layout import label_stacks, label_token_ids, label_tokens, lines_without
from .measures import (
    BarCount,
    BarReading,
    bar_at,
    barlines_through,
    page_number_zone,
    read_phrase,
    share_barlines,
)
from .models import Page, Source, Token
from .staves import Staff, owning_system, staff_at
from .vocal import voice_lines

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
    bars: list[tuple[float, int, float]] = field(default_factory=list)
    marks: list[tuple[float, str]] = field(default_factory=list)
    texts: list[Phrase] = field(default_factory=list)
    source: Source = "text"
    barlines: list[float] = field(default_factory=list)  # drawn barlines; text-layer pages only
    rule_y: float = 0.0  # a staff the barlines cross
    joins_previous: bool = False  # on the same row of bars as the system before
    count: BarCount | None = None  # set by measures.count_bars
    row: int = 0  # which row of bars this stack is on, in reading order (set with `count`)

    def staff_for(self, yc: float) -> Staff:
        return staff_at(self.staves, yc)

    def opens_row(self, x: float) -> bool:
        """Whether x is in the first bar of its row (true when bars are not counted)."""
        return self.count is None or self.count.in_first_bar(x)

    def bar_at(self, x: float) -> BarReading:
        """The bar at x: counted by barlines when possible, else the nearest
        printed number (on an OCR page, flagged as less certain)."""
        counted = self.count.bar_at(x) if self.count else None
        if counted:
            return counted
        reading = bar_at(self.bars, x)
        if self.source == "ocr" and reading.bar is not None:
            note = "OCR page: barlines cannot be counted, so the bar may be earlier than the true one"
            return BarReading(reading.bar, "ocr", f"{reading.reason}; {note}")
        return reading


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
    systems = []
    for i, stack in enumerate(stacks):
        barlines, rule_y = barlines_through(page.barlines, [ln.yc for ln in stack])
        voices = voice_lines([ln.text for ln in stack], [ln.yc for ln in stack])
        staves = [Staff(ln.text, ln.yc, i in voices) for i, ln in enumerate(stack)]
        systems.append(System(page.number, i, staves, source=page.source, barlines=barlines, rule_y=rule_y))
    for above, below in zip(systems, systems[1:]):
        below.joins_previous = share_barlines(page.barlines, above.rule_y, below.rule_y)
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
