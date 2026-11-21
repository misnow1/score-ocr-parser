"""Layout stage: group tokens into lines, find label stacks and instruction text.

Staff labels sit in a column left of the staves. Notation programs either
left-align or right-align them, so the column is found from a shared left edge
or a shared right edge, whichever lines up more labels. Each line is cut to its
label at the first big gap, glyph residue, chord symbol or time signature.
"""

import re
from dataclasses import dataclass, field
from functools import cache

from .data import load
from .models import Page, Token

LINE_TOLERANCE = 3.0
EDGE_TOLERANCE = 3.0  # labels in one column share an edge to within this
COLUMN_SLACK = 40.0  # later labels may start this far right of the column found first
LABEL_GAP = 8.0  # a horizontal gap this wide ends the label
STACK_GAP_FACTOR = 2.5
MAX_LABEL_WORDS = 6
MIN_HEADER_WORDS = 3  # a repeated line this long is a running title, not a label
MIN_HEADER_PAGES = 2
MIN_EXTRA_COLUMN = 3  # labels needed to accept a second column on a page

_TIME_SIGNATURE = re.compile(r"^(?:\d{1,2}/\d{1,2}|(?:[2-9]|1[0-2])[248])$")
_CHORD = re.compile(
    r"^[A-G][#b♭♯]?(?:maj|min|dim|aug|sus|add|m|M|\+|°|ø)?\d*(?:[#b♭♯(]\d+\)?)*(?:/[A-G][#b♭♯]?)?$"
)
_BARE_ROOT = re.compile(r"^[A-G][#b♭♯]?$")
_CONNECTORS = frozenset({"&", "-", "–", ",", "+"})  # between chairs: "1 & 2"
_CHAIR_LETTERS = frozenset("iIvVxX")  # roman numeral chairs


@dataclass
class TextLine:
    text: str
    yc: float
    tokens: list[Token] = field(default_factory=list)

    @property
    def x0(self) -> float:
        return self.tokens[0].x0

    @property
    def x1(self) -> float:
        return self.tokens[-1].x1


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
    return TextLine(" ".join(t.text for t in ln), ln[0].yc, ln)


# --- cutting a line down to its label ---------------------------------------


def _ends_label(tok: Token, previous: Token, following: Token | None) -> bool:
    """Whether `tok` (not the first of its line) starts what follows a label:
    a time signature, a chord symbol or glyph residue."""
    text = tok.text
    if _TIME_SIGNATURE.match(text):
        return True
    if not any(c.isalnum() for c in text) and text not in _CONNECTORS:
        return True
    if previous.text.lower() == "in":  # "Trumpet in Bb": a transposition, not a chord
        return False
    if _CHORD.match(text):
        return True
    if len(text) == 1 and text.isalpha() and text not in _CHAIR_LETTERS:
        return True  # a notation glyph that came through as a letter
    return len(text) == 1 and text.isalpha() and following is not None and following.text == text


def _cut(row: list[Token]) -> list[Token]:
    """The leading tokens of a line that form a staff label."""
    label = [row[0]]
    for i in range(1, len(row)):
        tok = row[i]
        if tok.x0 - label[-1].x1 > LABEL_GAP:
            break
        following = row[i + 1] if i + 1 < len(row) else None
        if _ends_label(tok, label[-1], following):
            break
        label.append(tok)
    return label


def is_chord_symbol(text: str) -> bool:
    """A chord symbol with a quality, number or bass ("F6", "G7", "Cm", "D/F#").
    A bare root ("B", "Bb") is not: it may be a rehearsal mark or a transposition."""
    return _CHORD.match(text) is not None and _BARE_ROOT.match(text) is None


# --- headers, footers and group labels --------------------------------------


@cache
def _filters() -> dict[str, frozenset[str]]:
    data = load("label_filters.yaml")
    return {k: frozenset(w.lower() for w in v) for k, v in data.items()}


def _words(text: str) -> list[str]:
    """Lower-case words with digits and punctuation removed."""
    return re.sub(r"[^a-z\s]", " ", text.lower()).split()


def _header_key(text: str) -> str:
    return " ".join(_words(text))


def _is_glyph_residue(text: str) -> bool:
    """A lone word of one or two letters, or one letter repeated: a notation
    glyph that came through as text ("YU", "oooo"), not an instrument."""
    word = text.strip()
    return word.isalpha() and (len(word) <= 2 or len(set(word.lower())) == 1)


def _is_not_a_label(text: str) -> bool:
    words = _words(text)
    if not words:
        return True  # nothing but numbers and punctuation
    filters = _filters()
    return (
        _CHORD.match(text) is not None  # a lone chord symbol or letter
        or _is_glyph_residue(text)
        or text.lower().strip(".") in filters["markings"]
        or " ".join(words) in filters["group_words"]
        or filters["instruction_words"].intersection(words)
        or words[0] in ("score", "conductor")
        or words[0] in filters["header_words"]
        or len(text.split()) > MAX_LABEL_WORDS
    )


def running_headers(pages: list[Page]) -> frozenset[str]:
    """Keys of long lines that repeat on several pages: running titles."""
    seen: dict[str, set[int]] = {}
    for page in pages:
        for ln in _text_lines(page):
            key = _header_key(" ".join(t.text for t in _cut(ln)))
            if len(key.split()) >= MIN_HEADER_WORDS:
                seen.setdefault(key, set()).add(page.number)
    return frozenset(k for k, nums in seen.items() if len(nums) >= MIN_HEADER_PAGES)


# --- the label column -------------------------------------------------------


def _edge_cluster(labels: list[list[Token]], edge) -> list[list[Token]]:
    """The largest set of labels whose `edge` agrees to within the tolerance."""
    best: list[list[Token]] = []
    for anchor in labels:
        group = [lb for lb in labels if abs(edge(lb) - edge(anchor)) <= EDGE_TOLERANCE]
        if len(group) > len(best):
            best = group
    return best


def _column(labels: list[list[Token]]) -> list[list[Token]]:
    """Labels that line up on a shared left or right edge, taking the best
    alignment first and repeating for labels left over that start inside the
    column (the first system often has a different edge from later ones)."""
    column: list[list[Token]] = []
    rest = labels
    while rest:
        left = _edge_cluster(rest, lambda lb: lb[0].x0)
        right = _edge_cluster(rest, lambda lb: lb[-1].x1)
        best = left if len(left) > len(right) else right
        if len(best) < 2 and (column or len(labels) > 1):
            break
        if column and len(best) < MIN_EXTRA_COLUMN:
            break
        column += best
        reach = max(lb[-1].x1 for lb in column) + COLUMN_SLACK
        rest = [lb for lb in rest if lb not in best and lb[0].x0 < reach]
    return sorted(column, key=lambda lb: lb[0].yc)


def _stack_labels(page: Page, headers: frozenset[str]) -> list[list[Token]]:
    labels = []
    for row in _text_lines(page):
        label = _cut(row)
        text = " ".join(t.text for t in label)
        if _is_not_a_label(text) or _header_key(text) in headers:
            continue
        labels.append(label)
    return _column(labels)


def label_stacks(page: Page, headers: frozenset[str] = frozenset()) -> list[list[TextLine]]:
    """Staff labels from the label column, one stack per system, top to bottom.
    `headers` are the document's running titles (see `running_headers`)."""
    column = _stack_labels(page, headers)
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


def instruction_lines(page: Page, headers: frozenset[str] = frozenset()) -> list[TextLine]:
    """Text lines with the staff labels taken out (instructions, markings)."""
    label_ids = {id(t) for stack in label_stacks(page, headers) for ln in stack for t in ln.tokens}
    rows = []
    for row in _text_lines(page):
        rest = [t for t in row if id(t) not in label_ids]
        if rest:
            rows.append(_as_line(rest))
    return rows


def first_system_labels(page: Page) -> list[str]:
    """Label strings from the first stack on a page."""
    stacks = label_stacks(page)
    return [ln.text for ln in stacks[0]] if stacks else []
