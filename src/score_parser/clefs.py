"""Staff starts: where the clef glyphs sit, used to count staves against labels.

Clefs are music-font glyphs, removed from a page's tokens by the clean stage
and kept in `Page.glyphs`. The staves of a page start at the same x, so the
glyphs sharing that x are its staves. Scanned pages carry no glyphs: nothing is
found, and no staff count is checked.
"""

from statistics import median

from .models import Page, Token

X_TOLERANCE = 3.0  # clefs of one column share an x to within this
SAME_STAFF = 3.0  # glyphs this close vertically are one staff
MIN_STAVES = 2
COVER_FACTOR = 0.6  # a clef within this many label gaps of a label belongs to it
STRAY_FACTOR = 1.5  # a lone label this many label gaps from any clef is not by a staff


def clef_ys(page: Page, label_right: float) -> list[float]:
    """Vertical centres of the clefs right of the label column, top to bottom;
    empty when the page has no usable clef column."""
    glyphs = [g for g in page.glyphs if g.x0 > label_right]
    best: list[Token] = []
    for anchor in sorted(glyphs, key=lambda g: g.x0):
        group = [g for g in glyphs if abs(g.x0 - anchor.x0) <= X_TOLERANCE]
        if len(group) > len(best):
            best = group
    ys: list[float] = []
    for y in sorted(g.yc for g in best):
        if not ys or y - ys[-1] > SAME_STAFF:
            ys.append(y)
    return ys if len(ys) >= MIN_STAVES else []


def label_gap(label_ys: list[float]) -> float:
    """Typical vertical step between neighbouring labels."""
    steps = [b - a for a, b in zip(label_ys, label_ys[1:])]
    return median(steps) if steps else 0.0


def unlabeled_clefs(label_ys: list[float], clefs: list[float]) -> list[float]:
    """Clefs with no label near them. Only judged when the page has at least as
    many clefs as labels (else some staves are simply not drawn with a clef).
    A label may sit between the two clefs of a grand staff, so "near" is
    most of a label step."""
    gap = label_gap(label_ys)
    if not clefs or gap == 0 or len(clefs) < len(label_ys):
        return []
    return [c for c in clefs if min(abs(c - y) for y in label_ys) > COVER_FACTOR * gap]


def stray_labels(label_ys: list[float], clefs: list[float]) -> set[float]:
    """Label positions that stand alone and far from every staff: text printed
    near the title that reads as a label."""
    gap = label_gap(label_ys)
    if not clefs or gap == 0:
        return set()
    stray = set()
    for i, y in enumerate(label_ys):
        neighbours = [abs(y - o) for j, o in enumerate(label_ys) if j != i]
        lonely = min(neighbours) >= STRAY_FACTOR * gap
        far = min(abs(y - c) for c in clefs) > STRAY_FACTOR * gap
        if lonely and far:
            stray.add(y)
    return stray
