"""Does a part file's title name a score's song? (`--parts-dir`)

Both titles are reduced to plain words, then compared word by word. The rule is
deliberately stricter than the `--numbers-dir` match (matching.py): a part
that goes to the wrong song is worse than one reported as matching no song.
A title is the same song when it has the same words, or the same number of
words each a typo of the other's (long words only, never a number: "Medley 1",
"Medley 2" and "Medley II" are three songs), or is a known alias of it; the part
file may add an instrument in front of the title, and after it only the part's
own labelling (instruments, description phrases, noise words), never other
words. Editable data: `title_aliases.yaml`.
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
_PLAIN_DATE = re.compile(r"\b(?:0?[1-9]|1[0-2]) (?:0?[1-9]|[12]\d|3[01]) (?:[23]\d|20\d\d)\b")  # 11 3 26
_CLOSING_TIME = re.compile(r"\b(?:0?[1-9]|1[0-2]) (?:1[3-9]|[2-5]\d)$")  # a closing 10 15
_SCORE_WORD = re.compile(r"\bscores?\d*\b")  # "score", "score1"
_PARENTHESIS = re.compile(r"[(\[][^)\]]*[)\]]?")  # a bracketed group, also one left open
_DIGIT_THEN_CAPITAL = re.compile(r"(?<=\d)(?=[A-Z][a-z])")  # a digit glued to the next word
_WINDOW = 3  # words of a title tried as one instrument name
_MIN_TYPO_LENGTH = 6  # only words this long may carry a typo ("night" is not "knight")
_MIN_CUT_OFF = 3  # letters of a noise word that show a file name cut short
_LEADING_ARTICLES = ("the", "a", "he")  # after a leading instrument; "he" is a "the" cut short
_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_ROMAN = re.compile(r"^(?:i{1,3}|iv|vi{0,3}|ix|x{1,3}i{0,3})$")
_NO_VOWEL = re.compile(r"^[^aeiouy]{2,3}$")  # initials: a tag, not a word


@cache
def _data() -> dict:
    return load("title_aliases.yaml")


@cache
def _noise() -> frozenset[str]:
    return frozenset(_data()["title_noise"])


@cache
def _phrases() -> list[list[str]]:
    """The description phrases, longest first."""
    return sorted((p.split() for p in _data()["part_descriptions"]), key=len, reverse=True)


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


def _same_word(a: str, b: str) -> bool:
    """Equal, or a typo of each other: both long words, no number, plain
    similarity of MIN_SCORE."""
    if a == b:
        return True
    long_words = min(len(a), len(b)) >= _MIN_TYPO_LENGTH
    return long_words and not _is_number(a) and not _is_number(b) and fuzz.ratio(a, b) >= MIN_SCORE


def _plain_words(text: str) -> list[str]:
    """Normalised words, "score" and the noise words dropped, and plain dates
    dropped ("11 3 26", a closing "10 15"). A number that is part of a title stays."""
    words = [w for w in _SCORE_WORD.sub(" ", _normalise(text)).split() if w not in _noise()]
    plain = _CLOSING_TIME.sub("", _PLAIN_DATE.sub(" ", " ".join(words)))
    return plain.split()


def _instrument_at(words: list[str], i: int, seen: set[str]) -> tuple[int, str]:
    """(how many words from `i` name an instrument not yet in `seen`, its name)."""
    for n in range(min(_WINDOW, len(words) - i), 0, -1):
        hit = resolve(" ".join(words[i : i + n]))
        if hit and hit.name not in seen:
            return n, hit.name
    return 0, ""


def _phrase_at(words: list[str], i: int) -> int:
    """How many words from `i` are a description phrase (a long word may carry a typo)."""
    for phrase in _phrases():
        window = words[i : i + len(phrase)]
        if len(window) == len(phrase) and all(_same_word(w, p) for w, p in zip(window, phrase)):
            return len(phrase)
    return 0


def _is_labelling(words: list[str], cut_off: int = _MIN_CUT_OFF) -> bool:
    """Whether every word is a part's own labelling: an instrument (each one
    once, with chair numbers: "Tenor sax 1 2"; after one listed under
    `free_text_after` any words may follow, a patch name or a note), a phrase of
    `part_descriptions` ("lyrics only", "lead sheet"), a number that follows
    another word, initials as the last word (two or three letters, no vowel), or
    as the last word the start of a noise word of at least `cut_off` letters (a
    file name cut short; never a number)."""
    seen: set[str] = set()
    i = 0
    while i < len(words):
        taken, name = _instrument_at(words, i, seen)
        if taken:
            if name in _data()["free_text_after"]:
                return True
            seen.add(name)
            i += taken
            continue
        word, last = words[i], i == len(words) - 1
        if phrase := _phrase_at(words, i):
            i += phrase
        elif word.isdigit() and i > 0:
            i += 1
        elif last and not _is_number(word) and (
            _NO_VOWEL.match(word) or (len(word) >= cut_off and any(n.startswith(word) for n in _noise()))
        ):
            i += 1
        else:
            return False
    return True


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
    """The same number of words, each the same or a typo of the other's."""
    wa, wb = a.split(), b.split()
    return len(wa) == len(wb) and all(_same_word(x, y) for x, y in zip(wa, wb))


def _without_labelling(key: str) -> set[str]:
    """The key, and the key without a tail that is only labelling or a score
    status word ("not"): a score's file name carries them too ("Short Tune pno"
    also names "Short Tune")."""
    words = key.split()
    status = set(_data()["score_status_words"])
    return {
        key,
        *(
            " ".join(words[:k])
            for k in range(1, len(words))
            if set(words[k:]) <= status or _is_labelling(words[k:])
        ),
    }


def _names_song(key: str, name: str) -> bool:
    """Whether the file title `key` is the title `name` (or a typo of it),
    optionally led by an instrument ("Trumpet 1 Short Tune") and followed by
    nothing but the part's own labelling."""
    words = key.split()
    leads = [0, *(n for n in range(1, min(_WINDOW, len(words)) + 1) if resolve(" ".join(words[:n])))]
    for lead in leads:
        rests = [words[lead:]]
        if lead and len(rests[0]) > 1 and rests[0][0] in _LEADING_ARTICLES:
            rests.append(rests[0][1:])  # also without the article: "Trumpet 1 The Short Tune"
        for rest in rests:
            cut_off = 1 if lead else _MIN_CUT_OFF  # after a leading instrument a lone letter is a cut-off tag
            for end in range(1, len(rest) + 1):
                head = " ".join(rest[:end])
                if (head == name or _typo_of(head, name)) and (end == len(rest) or _is_labelling(rest[end:], cut_off)):
                    return True
    return False


def same_song(file_title: str, score_title: str) -> bool:
    """Whether a part file's cleaned title names the score's song (see the
    module doc). A title that is only a year or only noise words matches nothing."""
    key = _song_key(file_title)
    wanted = _song_key(score_title)
    names = {*_without_labelling(wanted), *(n for group in _alias_groups() if wanted in group for n in group)}
    return bool(key) and any(_names_song(key, n) for n in names if n)
