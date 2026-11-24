"""Does a part file's title name a score's song? (`--parts-dir`)

Both titles are reduced to plain words, then compared word by word. The rule is
deliberately stricter than the `--numbers-dir` match (matching.py): a part
that goes to the wrong song is worse than one reported as matching no song.
A title is the same song when it has the same words, or the same number of
words each a typo of the other's (never a number: "Medley 1" and "Medley 2"
and "Medley II" are three songs), or is a known alias of it; the part file may
add an instrument in front of the title, and after it only the part's own
labelling (instruments, file descriptions, noise words), never other words.
Editable data: `title_aliases.yaml`.
"""

import re
from functools import cache

from rapidfuzz import fuzz

from .data import load
from .instruments import resolve
from .matching import MIN_SCORE, _known_aliases, _normalise

_INITIALS_YEAR = re.compile(r"\b[a-z]{1,3}(?:19|20)\d{2}\b")  # a year tag, no part of the title
_GLUED_YEAR = re.compile(r"(?<=[a-z])(?:19|20)\d{2}\b")  # a year glued to the last word
_YEAR_BEFORE_WORD = re.compile(r"\b(?:19|20)\d{2}(?=[a-z])")  # a year glued to the next word
_SEPARATED_DATE = re.compile(r"\b\d{1,2}(?:[:/._-]\d{1,2}){1,2}\b")  # 10:15, 11:3:26
_SCORE_WORD = re.compile(r"\bscores?\d*\b")  # "score", "score1"
_PARENTHESIS = re.compile(r"[(\[][^)\]]*[)\]]?")  # a bracketed group, also one left open
_DIGIT_THEN_CAPITAL = re.compile(r"(?<=\d)(?=[A-Z][a-z])")  # a digit glued to the next word
_WINDOW = 3  # words of a title tried as one instrument name
_MIN_TAIL_TYPO_LENGTH = 6  # a label word this long may carry a typo
_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_ROMAN = re.compile(r"^(?:i{1,3}|iv|vi{0,3}|ix|xi{0,3})$")


@cache
def _data() -> dict:
    return load("title_aliases.yaml")


@cache
def _noise() -> frozenset[str]:
    return frozenset(_data()["title_noise"])


@cache
def _label_words() -> frozenset[str]:
    return frozenset(_data()["part_descriptions"])


@cache
def _alias_groups() -> list[frozenset[str]]:
    """The names of each song that has aliases, as comparable keys."""
    return [
        frozenset(k for k in (_song_key(name) for name in (slug, *alternatives)) if k)
        for slug, alternatives in _known_aliases().items()
    ]


def _is_number(word: str) -> bool:
    """A digit, a roman numeral or a spelled-out small number: a word that tells
    two numbered songs apart and so never counts as a typo."""
    return word.isdigit() or word in _NUMBERS or bool(_ROMAN.match(word))


def _plain_words(text: str) -> list[str]:
    """Normalised words, "score" and the noise words dropped, plain dates
    dropped ("11 3 26", a closing "10 15": a month and a day, a month and a
    day-sized number, or a time). A number that is part of a title stays."""
    words = [w for w in _SCORE_WORD.sub(" ", _normalise(text)).split() if w not in _noise()]
    kept: list[str] = []
    i = 0
    while i < len(words):
        a, b, c = (words[i + k] if i + k < len(words) else "" for k in range(3))
        if a.isdigit() and b.isdigit() and c.isdigit() and 1 <= int(a) <= 12 and 1 <= int(b) <= 31 and (
            20 <= int(c) <= 39 or 2000 <= int(c) <= 2099
        ):
            i += 3
        elif i == len(words) - 2 and a.isdigit() and b.isdigit() and 1 <= int(a) <= 12 and 13 <= int(b) <= 59:
            i += 2
        else:
            kept.append(words[i])
            i += 1
    return kept


def _is_labelling(words: list[str], cut_off: bool = False) -> bool:
    """Whether every word is a part's own labelling: an instrument (each one
    once, with its chair numbers: "Tenor sax 1 2"), a word of
    `part_descriptions` in data/title_aliases.yaml ("lyrics only", "lead sheet"),
    a number that follows another word, a close spelling of a long such word,
    or, when `cut_off`, the start of a noise word (a file name cut short)."""
    seen: set[str] = set()
    i = 0
    while i < len(words):
        word = words[i]
        taken = 0
        for n in range(min(_WINDOW, len(words) - i), 0, -1):
            hit = resolve(" ".join(words[i : i + n]))
            if hit and hit.name not in seen:
                seen.add(hit.name)
                taken = n
                break
        if taken:
            i += taken
            continue
        if not (
            word in _label_words()
            or (word.isdigit() and i > 0)
            or _close_to_label_word(word)
            or (cut_off and i == len(words) - 1 and any(n.startswith(word) for n in _noise()))
        ):
            return False
        i += 1
    return True


def _close_to_label_word(word: str) -> bool:
    return len(word) >= _MIN_TAIL_TYPO_LENGTH and any(
        len(w) >= _MIN_TAIL_TYPO_LENGTH and fuzz.ratio(word, w) >= MIN_SCORE for w in _label_words()
    )


@cache
def _song_key(title: str) -> str:
    """A title as the words to compare: case, "the", punctuation, dates, year
    tags, "score", filename noise words and bracketed labelling dropped.
    Brackets that hold other words ("(Part 1)", a subtitle) are part of the title."""
    text = _SEPARATED_DATE.sub(" ", _DIGIT_THEN_CAPITAL.sub(" ", title).lower())
    for pattern in (_INITIALS_YEAR, _GLUED_YEAR, _YEAR_BEFORE_WORD):
        text = pattern.sub(" ", text)

    def unwrap(match: re.Match) -> str:
        inner = _plain_words(match.group())
        return " " if not inner or _is_labelling(inner) else match.group()

    return " ".join(_plain_words(_PARENTHESIS.sub(unwrap, text)))


def _typo_of(a: str, b: str) -> bool:
    """The same number of words, each equal or a close spelling of the other's
    (a plain similarity of MIN_SCORE), and no number among the ones that differ."""
    wa, wb = a.split(), b.split()
    if len(wa) != len(wb):
        return False
    return all(x == y or (not _is_number(x) and not _is_number(y) and fuzz.ratio(x, y) >= MIN_SCORE) for x, y in zip(wa, wb))


def _without_labelling(key: str) -> set[str]:
    """The key, and the key without a tail that is only labelling: a score's file
    name carries one too ("Short Tune pno" also names "Short Tune")."""
    words = key.split()
    return {key, *(" ".join(words[:k]) for k in range(1, len(words)) if _is_labelling(words[k:], cut_off=True))}


def _names_song(key: str, name: str) -> bool:
    """Whether the file title `key` is the title `name` (or a typo of it),
    optionally led by an instrument ("Trumpet 1 Short Tune") and followed by
    nothing but the part's own labelling."""
    words = key.split()
    leads = [0, *(n for n in range(1, min(_WINDOW, len(words)) + 1) if resolve(" ".join(words[:n])))]
    for lead in leads:
        rest = words[lead:]
        if lead and rest and (rest[0] == "a" or "the".endswith(rest[0])):  # "Trumpet 1 The Title", "Trumpet 1 he Title"
            rest = rest[1:]
        for end in range(1, len(rest) + 1):
            head = " ".join(rest[:end])
            if (head == name or _typo_of(head, name)) and (end == len(rest) or _is_labelling(rest[end:], cut_off=True)):
                return True
    return False


def same_song(file_title: str, score_title: str) -> bool:
    """Whether a part file's cleaned title names the score's song (see the
    module doc). A title that is only a year or only noise words matches nothing."""
    key = _song_key(file_title)
    wanted = _song_key(score_title)
    names = {*_without_labelling(wanted), *(n for group in _alias_groups() if wanted in group for n in group)}
    return bool(key) and any(_names_song(key, n) for n in names if n)
