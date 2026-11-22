"""Layout stage: group tokens into lines, find label stacks and instruction text.

Staff labels sit in a column left of the staves. Notation programs either
left-align or right-align them, so the column is found from a shared left edge
or a shared right edge, whichever lines up more labels. Each line is cut to its
label at the first big gap, glyph residue, chord symbol or time signature.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache

from .data import load
from .clefs import clef_ys, stray_labels
from .models import Page, Token
from .vocal import voice_staff

LINE_TOLERANCE = 3.0
EDGE_TOLERANCE = 3.0  # labels in one column share an edge to within this
COLUMN_SLACK = 40.0  # later labels may start this far right of the column found first
LABEL_GAP = 8.0  # a horizontal gap this wide ends the label
STACK_GAP_FACTOR = 2.5
MAX_LABEL_WORDS = 6
OVERPRINT_FRACTION = 0.3  # words overlapping this much of the narrower one are overprinted
MIN_OVERPRINT_STEP = 0.5  # and must sit at different heights
MIN_HEADER_WORDS = 3  # a repeated line this long is a running title, not a label
MIN_HEADER_PAGES = 2
MIN_EXTRA_COLUMN = 3  # labels needed to accept a second column on a page

_TIME_SIGNATURE = re.compile(r"^(?:\d{1,2}/\d{1,2}|(?:[2-9]|1[0-2])[248])$")
_CHORD_BODY = (
    r"[A-G][#b♭♯]?(?:maj|min|dim|aug|sus|add|m|M|\+|°|ø)?\d*(?:[#b♭♯]\d+|\([#b♭♯]?\d+\)?)*(?:/[A-G][#b♭♯]?)?"
)
_CHORD = re.compile(rf"^{_CHORD_BODY}$")
_DOTS = re.compile(r"\.{3,}|…")
_BARE_ROOT = re.compile(r"^[A-G][#b♭♯]?$")
_BARE_RUN = re.compile(r"^(?:[A-G][#b♭♯]?)+$")
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
    separated: list[list[Token]] = []
    for ln in grouped:
        ln.sort(key=lambda t: t.x0)
        separated += _split_overprint(ln)
    return separated


def _overlaps(a: Token, b: Token) -> bool:
    """Whether two words are printed over each other (more than a third of the
    narrower one), as opposed to touching."""
    overlap = min(a.x1, b.x1) - max(a.x0, b.x0)
    return overlap > OVERPRINT_FRACTION * min(a.x1 - a.x0, b.x1 - b.x0)


def _split_overprint(ln: list[Token]) -> list[list[Token]]:
    """One visual line, or two when words in it are printed over each other:
    the words are cut at the biggest vertical step between them, upper line
    first, so an overprinted label is read as two labels."""
    if len(ln) < 2 or not any(_overlaps(a, b) for a, b in zip(ln, ln[1:])):
        return [ln]
    by_y = sorted(ln, key=lambda t: t.yc)
    steps = [b.yc - a.yc for a, b in zip(by_y, by_y[1:])]
    if max(steps) < MIN_OVERPRINT_STEP:
        return [ln]
    cut = steps.index(max(steps)) + 1
    return [sorted(part, key=lambda t: t.x0) for part in (by_y[:cut], by_y[cut:])]


def _text_lines(page: Page) -> list[list[Token]]:
    """Lines that are not bare bar numbers."""
    return [ln for ln in lines(page.tokens) if not all(t.text.isdigit() for t in ln)]


def _as_line(ln: list[Token]) -> TextLine:
    return TextLine(" ".join(t.text for t in ln), ln[0].yc, ln)


# --- cutting a line down to its label ---------------------------------------


def _is_chord_or_glyph(text: str) -> bool:
    """Whether a token reads as notation, not a label word: a chord symbol, or
    glyph residue (a lone one- or two-letter word, or one letter repeated)."""
    return _CHORD.match(text) is not None or _is_glyph_residue(text)


def _is_transposition_letter(previous: Token, following: Token | None) -> bool:
    """"1&2 B Tpt.": a bare B between a chair and a word is the instrument's
    key, not a chord."""
    return (
        following is not None
        and any(c.isdigit() for c in previous.text)
        and len(following.text.strip(".")) >= 3
        and following.text.strip(".").isalpha()
    )


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
    if _BARE_ROOT.match(text) and _is_transposition_letter(previous, following):
        return False
    if _CHORD.match(text):
        return True
    if len(text) == 1 and text.isalpha():  # a letter that is not a chair numeral is a notation glyph
        return text not in _CHAIR_LETTERS or (following is not None and following.text == text)
    return False


def _is_voice_part(label: list[Token], tok: Token) -> bool:
    """The F or M closing a vocal staff label ("Voice Lead F"), which would
    otherwise be cut as glyph residue."""
    return (
        label[0].text.lower() == "voice"
        and label[-1].text.lower() in {"lead", "bck", "back"}
        and tok.text in {"F", "M"}
    )


def _label_prefix(row: list[Token]) -> list[Token]:
    """The leading tokens of a line that form a staff label."""
    label = [row[0]]
    for i in range(1, len(row)):
        tok = row[i]
        if tok.x0 - label[-1].x1 > LABEL_GAP:
            break
        following = row[i + 1] if i + 1 < len(row) else None
        if _is_voice_part(label, tok):
            label.append(tok)
            break
        if _ends_label(tok, label[-1], following):
            break
        label.append(tok)
    return label


def strip_chord_run(text: str) -> str:
    """The word without chord symbols glued to it: "F#min7(b5)/EE9" (two chords
    run together) -> "", "E9Solo" -> "Solo". Anything left must start a
    capitalised word; a run of bare roots ("BEAD") is not chord text."""
    for end in range(len(text), 0, -1):
        head, rest = text[:end], text[end:]
        if rest and not (rest[0].isupper() and rest.isalpha() and len(rest) > 1):
            continue
        if re.fullmatch(rf"(?:{_CHORD_BODY})+", head) and not _BARE_RUN.match(head):
            return rest
    return text


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


def _words_key(text: str) -> str:
    """`_words` joined: the form used to compare repeated lines and group words."""
    return " ".join(_words(text))


def _is_glyph_residue(text: str) -> bool:
    """A lone word of one or two letters, or one letter repeated: a notation
    glyph that came through as text ("YU", "oooo"), not an instrument."""
    word = text.strip()
    return word.isalpha() and (len(word) <= 2 or len(set(word.lower())) == 1)


def _is_note_line(text: str) -> bool:
    """A line that is a cue or note, not a label: wholly in parentheses, or
    trailing dots ("Drums only......")."""
    stripped = text.strip()
    return (stripped.startswith("(") and stripped.endswith(")")) or bool(_DOTS.search(stripped))


def _is_not_a_label(text: str) -> bool:
    words = _words(text)
    if not words:
        return True  # nothing but numbers and punctuation
    filters = _filters()
    return (
        _is_chord_or_glyph(text)  # a lone chord symbol, letter or glyph
        or text.lower().strip(".") in filters["markings"]
        or _words_key(text) in filters["group_words"]
        or filters["instruction_words"].intersection(words)
        or _is_note_line(text)
        or words[0] in ("score", "conductor")
        or words[0] in filters["header_words"]
        or len(text.split()) > MAX_LABEL_WORDS
    )


def _is_title_like(key: str) -> bool:
    """A repeated line reads as a running title when it has several words, at
    least two of them real words ("Synthetic Tune Two"), not abbreviations and
    chair numerals ("A. Sx. I & II" repeats too, and is a label)."""
    words = key.split()
    if voice_staff(key):  # "Voice Lead F" repeats on every page and is a staff
        return False
    return len(words) >= MIN_HEADER_WORDS and sum(len(w) >= 4 for w in words) >= 2


def running_headers(pages: list[Page]) -> frozenset[str]:
    """Keys of long lines that repeat on several pages: running titles."""
    seen: dict[str, set[int]] = {}
    for page in pages:
        for ln in _text_lines(page):
            key = _words_key(" ".join(t.text for t in _label_prefix(ln)))
            if _is_title_like(key):
                seen.setdefault(key, set()).add(page.number)
    return frozenset(k for k, nums in seen.items() if len(nums) >= MIN_HEADER_PAGES)


# --- the label column -------------------------------------------------------


def _edge_cluster(
    labels: list[list[Token]], edge: Callable[[list[Token]], float]
) -> list[list[Token]]:
    """The largest set of labels whose `edge` agrees to within the tolerance."""
    best: list[list[Token]] = []
    for anchor in labels:
        group = [lb for lb in labels if abs(edge(lb) - edge(anchor)) <= EDGE_TOLERANCE]
        if len(group) > len(best):
            best = group
    return best


def _label_column(labels: list[list[Token]]) -> list[list[Token]]:
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
        label = _label_prefix(row)
        text = " ".join(t.text for t in label)
        if _is_not_a_label(text) or _words_key(text) in headers:
            continue
        labels.append(label)
    column = _label_column(labels)
    clefs = clef_ys(page, max((lb[-1].x1 for lb in column), default=0.0))
    stray = stray_labels([lb[0].yc for lb in column], clefs)
    return [lb for lb in column if lb[0].yc not in stray]


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


def label_tokens(stacks: list[list[TextLine]]) -> list[Token]:
    """Every token that belongs to a staff label."""
    return [t for stack in stacks for ln in stack for t in ln.tokens]


def label_token_ids(stacks: list[list[TextLine]]) -> set[int]:
    """Identities of the tokens that belong to a staff label."""
    return {id(t) for t in label_tokens(stacks)}


def lines_without(tokens: list[Token], ids: set[int]) -> list[list[Token]]:
    """Visual lines of `tokens` with the tokens whose id is in `ids` removed;
    lines left empty are dropped."""
    return [rest for ln in lines(tokens) if (rest := [t for t in ln if id(t) not in ids])]


def instruction_lines(page: Page, headers: frozenset[str] = frozenset()) -> list[TextLine]:
    """Text lines with the staff labels taken out (instructions, markings)."""
    label_ids = label_token_ids(label_stacks(page, headers))
    text_tokens = [t for row in _text_lines(page) for t in row]
    return [_as_line(row) for row in lines_without(text_tokens, label_ids)]


def first_system_labels(page: Page) -> list[str]:
    """Label strings from the first stack on a page."""
    stacks = label_stacks(page)
    return [ln.text for ln in stacks[0]] if stacks else []
