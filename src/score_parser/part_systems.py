"""Part layout: the staves of a part page, one system each.

A part has no label column, so its staves are found from the long horizontal
rules drawn for staff lines, and its barlines from the short vertical rules
that run from a staff's top line to its bottom line. A part prints a bar number
at the start of each staff only, and a multi-bar rest as a staff-sized numeral.
"""

from dataclasses import dataclass

from .layout import lines
from .measures import BAR_ROW_REACH, merge_barlines, page_number_zone, share_barlines
from .models import Page, Token
from .staves import Staff
from .systems import System, place_rows

STAFF_LINE_GAP = 12.0  # staff lines are closer than this; the next staff is further
MIN_STAFF_LINES = 3  # a run of fewer long rules is a rule under a title, not a staff
BARLINE_END_TOLERANCE = 2.0  # a barline runs from the top staff line to the bottom one
START_REACH = 30.0  # a bar number this near the staff's left end numbers its first bar
REST_NUMERAL_HEIGHT = 1.5  # a digit this many staff heights tall is a multi-bar rest's count


@dataclass
class PartStaff:
    top: float
    bottom: float
    left: float

    @property
    def centre(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def height(self) -> float:
        return self.bottom - self.top

    def overlap(self, tok: Token) -> float:
        """How far a token's box reaches into the staff's vertical span."""
        return min(tok.y1, self.bottom) - max(tok.y0, self.top)


def part_staves(page: Page) -> list[PartStaff]:
    """Each staff on a part page, top to bottom: a run of at least
    MIN_STAFF_LINES long horizontal rules, each within STAFF_LINE_GAP of the last."""
    runs: list[list[tuple[float, float, float]]] = []
    for line in sorted(page.staff_lines):
        if runs and line[0] - runs[-1][-1][0] <= STAFF_LINE_GAP:
            runs[-1].append(line)
        else:
            runs.append([line])
    return [
        PartStaff(run[0][0], run[-1][0], min(x0 for _, x0, _ in run))
        for run in runs
        if len(run) >= MIN_STAFF_LINES
    ]


def _rest_numerals(page: Page, staves: list[PartStaff]) -> list[tuple[Token, int]]:
    """(token, staff index) of each staff-sized digit sitting on a staff: the
    count of a multi-bar rest, whether set in a music font (a glyph) or not.
    Text-sized digits (tuplets, bar numbers) are not."""
    found = []
    for tok in [*page.tokens, *page.glyphs]:
        if not (tok.text.isdigit() and len(tok.text) <= 2):
            continue
        index = max(range(len(staves)), key=lambda i: staves[i].overlap(tok))
        staff = staves[index]
        if staff.overlap(tok) > 0 and tok.y1 - tok.y0 >= REST_NUMERAL_HEIGHT * staff.height:
            found.append((tok, index))
    return found


def find_part_systems(page: Page, label: str) -> list[System]:
    """The staves of a part page, one system each, every staff labelled `label`.
    Text above the first staff by more than a bar number's reach (the title, the
    instrument heading) is page furniture and is left out; a printed number
    counts as a bar number only at the start of its staff."""
    staves = part_staves(page)
    if not staves:
        return []
    systems = []
    for i, staff in enumerate(staves):
        ends = [
            x for x, y0, y1 in page.short_rules
            if abs(y0 - staff.top) <= BARLINE_END_TOLERANCE and abs(y1 - staff.bottom) <= BARLINE_END_TOLERANCE
        ]
        systems.append(System(
            page.number, i, [Staff(label, staff.centre)], source=page.source,
            barlines=merge_barlines([staff.left, *ends]), rule_y=staff.centre,
        ))
    for above, below in zip(systems, systems[1:]):
        below.joins_previous = share_barlines(page.barlines, above.rule_y, below.rule_y)
    rests = _rest_numerals(page, staves)
    for tok, i in rests:
        systems[i].rests.append(((tok.x0 + tok.x1) / 2, int(tok.text)))
    skip = {id(tok) for tok, _ in rests}
    furniture = staves[0].centre - BAR_ROW_REACH
    rows = [row for ln in lines(page.tokens) if (row := [t for t in ln if id(t) not in skip]) and row[0].yc >= furniture]
    place_rows(systems, rows, page_number_zone(page, 0.0))
    for system, staff in zip(systems, staves):
        system.bars = [bar for bar in system.bars if bar[0] <= staff.left + START_REACH]
    return systems
