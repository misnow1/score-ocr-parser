"""Layout stage: group tokens into lines and find the first system's labels."""

from .models import Page, Token

LINE_TOLERANCE = 3.0
MARGIN_SLACK = 20.0


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


def first_system_labels(page: Page) -> list[str]:
    """Label strings from the left-margin column, top stack only."""
    rows = lines(page.tokens)
    if not rows:
        return []
    left = min(ln[0].x0 for ln in rows)
    column = [ln for ln in rows if ln[0].x0 <= left + MARGIN_SLACK]
    gaps = [b[0].yc - a[0].yc for a, b in zip(column, column[1:])]
    if gaps:
        median = sorted(gaps)[len(gaps) // 2]
        cut = next((i for i, g in enumerate(gaps) if g > 2.5 * median), None)
        if cut is not None:
            column = column[: cut + 1]
    return [" ".join(t.text for t in ln) for ln in column]
