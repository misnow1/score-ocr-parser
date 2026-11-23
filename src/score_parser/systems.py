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
    above_top,
    bar_at,
    below_bottom,
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
    rests: list[tuple[float, int]] = field(default_factory=list)  # multi-bar rests as (x, bars); parts only
    tokens: list[Token] = field(default_factory=list)  # every word placed on the system, lyrics included
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
    place_rows(systems, other_rows, page_number_zone(page, label_right))
    return systems


def place_rows(
    systems: list[System], rows: list[list[Token]], is_page_number: Callable[[str, float], bool]
) -> None:
    """Hand each line of text to the system it belongs to."""
    for row in rows:
        owner = owning_system(systems, row[0].yc)
        under = _numbered_under(systems, owner, row)
        _place(under or owner, row, is_page_number, below=under is not None)


def _numbered_under(systems: list[System], owner: System, row: list[Token]) -> System | None:
    """The system whose bottom staff a line of bare numbers sits just under, when
    the line is not in the band above its owner (some scores print bar numbers
    under the system, where text belongs to the system beneath). A row of bar
    numbers has two or more numbers that rise left to right: a lone digit (a
    time signature) or repeats (tuplet 3s) under a staff are not bar numbers."""
    yc = row[0].yc
    if not all(t.text.isdigit() for t in row) or above_top(owner.staves[0].yc, yc):
        return None
    numbers = [int(t.text) for t in sorted(row, key=lambda t: t.x0)]
    if len(numbers) < 2 or any(a >= b for a, b in zip(numbers, numbers[1:])):
        return None
    return next((s for s in systems if below_bottom(s.staves[-1].yc, yc)), None)


def _place(
    system: System, row: list[Token], is_page_number: Callable[[str, float], bool], below: bool = False
) -> None:
    top = system.staves[0].yc
    bottom = system.staves[-1].yc if below else None
    system.tokens.extend(row)
    for phrase in _phrases(row):
        bar, mark, rest = read_phrase(phrase, top, is_page_number, bottom)
        if bar:
            system.bars.append(bar)
        if mark:
            system.marks.append(mark)
        if rest:
            system.texts.append(Phrase(" ".join(t.text for t in rest), rest[0].x0, rest[0].yc))
    system.bars.sort()
    system.marks.sort()
