"""Part layout: the staves of a part page, one system each.

A part has no label column, so its staves are found from the long horizontal
rules drawn for staff lines, and its barlines from the short vertical rules
that run from a staff's top line to its bottom line. A part prints a bar number
at the start of each staff only, and a multi-bar rest as a staff-sized numeral.
A percussion part may draw one-line staves, accepted only when asked for.
"""

from dataclasses import dataclass

from .layout import lines
from .measures import BAR_ROW_REACH, merge_barlines, page_number_zone, share_barlines
from .models import Page, Token
from .part_labels import START_REACH, StartLabel, bars_in, read_start_labels
from .staves import Staff
from .systems import StartNote, System, place_rows

STAFF_LINE_GAP = 12.0  # staff lines are closer than this; the next staff is further
MIN_STAFF_LINES = 3  # a run of fewer long rules is a rule under a title, not a staff
BARLINE_END_TOLERANCE = 2.0  # a barline runs from the top staff line to the bottom one
ONE_LINE_HALF = 10.0  # a one-line staff is taken as this far above and below its line
MIN_ONE_LINE_BARLINES = 2  # a lone rule with fewer barlines through it is no staff
TIME_SIGNATURE_REACH = 80.0  # staff-sized digits this near the staff's left end are the meter
REST_NUMERAL_HEIGHT = 1.5  # a digit this many staff heights tall is a multi-bar rest's count on the staff
REST_ABOVE_HEIGHT = 0.95  # ...and this many when it sits just above the staff, as most parts print it
REST_ABOVE_REACH = 6.0  # a digit that ends this far above the top line (or less) sits on the staff
REST_CROSS = 2.0  # ...and one may cross the top line by this much (some fonts do)


@dataclass
class PartStaff:
    top: float
    bottom: float
    left: float
    one_line: bool = False

    @property
    def centre(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def height(self) -> float:
        return self.bottom - self.top

    def overlap(self, tok: Token) -> float:
        """How far a token's box reaches into the staff's vertical span."""
        return min(tok.y1, self.bottom) - max(tok.y0, self.top)

    def barlines(self, page: Page) -> list[float]:
        """The x of every rule that is a barline of this staff."""
        if self.one_line:
            return [
                x for x, y0, y1 in page.short_rules
                if y0 - BARLINE_END_TOLERANCE <= self.centre <= y1 + BARLINE_END_TOLERANCE
                and y1 - y0 <= 2 * ONE_LINE_HALF
            ]
        return [
            x for x, y0, y1 in page.short_rules
            if abs(y0 - self.top) <= BARLINE_END_TOLERANCE and abs(y1 - self.bottom) <= BARLINE_END_TOLERANCE
        ]


def part_staves(page: Page, one_line: bool = False) -> list[PartStaff]:
    """Each staff on a part page, top to bottom: a run of at least
    MIN_STAFF_LINES long horizontal rules, each within STAFF_LINE_GAP of the last.
    With `one_line`, a single rule with barlines through it is a staff too."""
    runs: list[list[tuple[float, float, float]]] = []
    for line in sorted(page.staff_lines):
        if runs and line[0] - runs[-1][-1][0] <= STAFF_LINE_GAP:
            runs[-1].append(line)
        else:
            runs.append([line])
    staves = []
    for run in runs:
        left = min(x0 for _, x0, _ in run)
        if len(run) >= MIN_STAFF_LINES:
            staves.append(PartStaff(run[0][0], run[-1][0], left))
        elif one_line and len(run) == 1:
            y = run[0][0]
            staff = PartStaff(y - ONE_LINE_HALF, y + ONE_LINE_HALF, left, one_line=True)
            if len(merge_barlines(staff.barlines(page))) >= MIN_ONE_LINE_BARLINES:
                staves.append(staff)
    return staves


def _rest_numerals(page: Page, staves: list[PartStaff]) -> list[tuple[Token, int]]:
    """(token, staff index) of each staff-sized digit sitting on a staff or just
    above its top line: the count of a multi-bar rest, whether set in a music
    font (a glyph) or not. Text-sized digits (tuplets, bar numbers) are not, and
    neither is a digit near the staff's left end, where the time signature sits."""
    found = []
    for tok in [*page.tokens, *page.glyphs]:
        if not (tok.text.isdigit() and len(tok.text) <= 2):
            continue
        index = max(range(len(staves)), key=lambda i: staves[i].overlap(tok))
        staff = staves[index]
        centre = (tok.x0 + tok.x1) / 2
        height = tok.y1 - tok.y0
        # A time signature sits on the staff, never above it; a bar number sits above it.
        on_staff = (
            staff.overlap(tok) > 0
            and height >= REST_NUMERAL_HEIGHT * staff.height
            and centre >= staff.left + TIME_SIGNATURE_REACH
        )
        above_staff = (
            -REST_CROSS <= staff.top - tok.y1 <= REST_ABOVE_REACH
            and height >= REST_ABOVE_HEIGHT * staff.height
            and centre >= staff.left + START_REACH
        )
        if on_staff or above_staff:
            found.append((tok, index))
    return found


def find_part_systems(page: Page, label: str, one_line: bool = False) -> list[System]:
    """The staves of a part page, one system each, every staff labelled `label`.
    Text above the first staff by more than a bar number's reach (the title, the
    instrument heading) is page furniture and is left out; a printed number
    counts as a bar number only at the start of its staff."""
    staves = part_staves(page, one_line)
    if not staves:
        return []
    systems = []
    for i, staff in enumerate(staves):
        systems.append(System(
            page.number, i, [Staff(label, staff.centre)], source=page.source,
            barlines=merge_barlines([staff.left, *staff.barlines(page)]), rule_y=staff.centre,
        ))
    for above, below in zip(systems, systems[1:]):
        below.joins_previous = share_barlines(page.barlines, above.rule_y, below.rule_y)
    rests = _rest_numerals(page, staves)
    for tok, i in rests:
        systems[i].rests.append(((tok.x0 + tok.x1) / 2, int(tok.text)))
    skip = {id(tok) for tok, _ in rests}
    lengths = [bars_in(system.barlines, system.rests) for system in systems]
    joined = [system.joins_previous for system in systems]
    starts, placed, read = read_start_labels(staves, [t for t in page.tokens if id(t) not in skip], lengths, joined)
    skip |= {id(tok) for tok in read}
    furniture = staves[0].centre - BAR_ROW_REACH
    rows = [row for ln in lines(page.tokens) if (row := [t for t in ln if id(t) not in skip]) and row[0].yc >= furniture]
    place_rows(systems, rows, page_number_zone(page, 0.0))
    for system, staff in zip(systems, staves):
        system.bars = [bar for bar in system.bars if bar[0] <= staff.left + START_REACH]
    for i, (system, start) in enumerate(zip(systems, starts)):
        system.bars = sorted([*system.bars, *((t.x0, int(t.text), t.x1) for t in placed[i])])
        if start and start.pair:
            system.start_note = _overprint_note(start)
    return systems


def _overprint_note(label: StartLabel) -> StartNote:
    """What to say of a staff-start number that was one of an overprinted pair,
    and whether counting the staff before from the lower number reached it."""
    low, high = label.pair or (0, label.number)
    said = f"staff-start label overprinted: {low} and {high} read as two numbers, {high} for this staff"
    if label.confirmed:
        return StartNote(f"{said}; counting the staff before from {low} (multi-bar rests included) reaches {high}", True)
    return StartNote(
        f"{said}; not confirmed by counting the staff before from {low} (multi-bar rests included), so the bar may be off",
        False,
    )
