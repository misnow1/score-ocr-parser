"""Layout stage: group tokens into lines, find label stacks and instruction text."""

from dataclasses import dataclass

from .models import Page, Token

LINE_TOLERANCE = 3.0
MARGIN_SLACK = 20.0
STACK_GAP_FACTOR = 2.5


@dataclass
class TextLine:
    text: str
    yc: float


def lines(tokens: list[Token]) -> list[list[Token]]:
    """Tokens grouped into visual lines, top to bottom, each left to right."""
    grouped: list[list[Token]] = []
    for tok in sorted(tokens, key=lambda t: (t.yc, t.x0)):
        if grouped and abs(grouped[-1][0].yc - tok.yc) <= LINE_TOLERANCE:
            grouped[-1].append(tok)
        else:
            grouped.append([tok])
    for ln in grouped:
        ln.sort(key=lambda t: t.x0)
    return grouped


def _text_lines(page: Page) -> list[list[Token]]:
    """Lines that are not bare bar numbers."""
    return [ln for ln in lines(page.tokens) if not all(t.text.isdigit() for t in ln)]


def _as_line(ln: list[Token]) -> TextLine:
    return TextLine(" ".join(t.text for t in ln), ln[0].yc)


def _split(page: Page) -> tuple[list[list[Token]], list[list[Token]]]:
    """(left-margin lines, all other lines)."""
    rows = _text_lines(page)
    if not rows:
        return [], []
    left = min(ln[0].x0 for ln in rows)
    margin = [ln for ln in rows if ln[0].x0 <= left + MARGIN_SLACK]
    rest = [ln for ln in rows if ln[0].x0 > left + MARGIN_SLACK]
    return margin, rest


def label_stacks(page: Page) -> list[list[TextLine]]:
    """Staff labels from the left-margin column, one stack per system, top to bottom."""
    column, _ = _split(page)
    if not column:
        return []
    gaps = [b[0].yc - a[0].yc for a, b in zip(column, column[1:])]
    cuts: list[int] = []
    if gaps:
        median = sorted(gaps)[len(gaps) // 2]
        cuts = [i + 1 for i, g in enumerate(gaps) if g > STACK_GAP_FACTOR * median]
    stacks, start = [], 0
    for cut in [*cuts, len(column)]:
        stacks.append([_as_line(ln) for ln in column[start:cut]])
        start = cut
    return stacks


def instruction_lines(page: Page) -> list[TextLine]:
    """Text lines outside the label column (instructions, markings)."""
    _, rest = _split(page)
    return [_as_line(ln) for ln in rest]


def first_system_labels(page: Page) -> list[str]:
    """Label strings from the first system on a page."""
    stacks = label_stacks(page)
    return [ln.text for ln in stacks[0]] if stacks else []
