"""Match a score title to an existing planner number slug (read-only)."""

import re
from pathlib import Path

import yaml
from rapidfuzz import fuzz, process

from .data import load
from .instruments import resolve

MIN_SCORE = 85
# A title much shorter than a candidate is not a match however well it sits
# inside it ("Sing" in "Sing Sing Sing"): the lengths must be this close.
MIN_LENGTH_RATIO = 0.6


def _similar_length(a: str, b: str) -> bool:
    return min(len(a), len(b)) >= MIN_LENGTH_RATIO * max(len(a), len(b))


def _similarity(a: str, b: str, **_) -> float:
    return fuzz.WRatio(a, b) if _similar_length(a, b) else 0.0


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _normalise(text: str) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower().replace("-", " "))
    return re.sub(r"^(the|a) ", "", " ".join(text.split()))


def _known_aliases() -> dict[str, list[str]]:
    """slug -> alternative titles, from data/title_aliases.yaml."""
    return load("title_aliases.yaml")["aliases"]


def _names_for(slug: str, numbers_dir: Path, aliases: dict[str, list[str]]) -> set[str]:
    names = {_normalise(slug), *(_normalise(a) for a in aliases.get(slug, []))}
    try:
        title = yaml.safe_load((numbers_dir / f"{slug}.yaml").read_text()).get("title")
    except (OSError, yaml.YAMLError, AttributeError):
        title = None
    if isinstance(title, str):
        names.add(_normalise(title))
    return names


def draft_name(title: str, slug: str | None, numbers_dir: Path | None) -> tuple[str, bool]:
    """(file stem for the flow draft, unmatched). Unmatched means a numbers dir
    was given but no slug matched, so the stem carries an UNMATCHED- prefix."""
    if slug:
        return slug, False
    if numbers_dir:
        return f"UNMATCHED-{slugify(title)}", True
    return slugify(title), False


def match_slug(title: str, numbers_dir: Path) -> str | None:
    """Slug of the planner number this title belongs to, or None. Read-only."""
    aliases = _known_aliases()
    candidates: dict[str, str] = {}  # normalised name -> slug
    for path in sorted(numbers_dir.glob("*.yaml")):
        for name in _names_for(path.stem, numbers_dir, aliases):
            candidates.setdefault(name, path.stem)
    wanted = _normalise(title)
    if wanted in candidates:
        return candidates[wanted]
    hit = process.extractOne(wanted, list(candidates), scorer=_similarity, score_cutoff=MIN_SCORE)
    return candidates[hit[0]] if hit else None


_INITIALS_YEAR = re.compile(r"\b[a-z]{1,3}(?:19|20)\d{2}\b")  # "jc2026": a year tag, no part of the title
_GLUED_YEAR = re.compile(r"(?<=[a-z])(?:19|20)\d{2}\b")  # "christmas2022"
_YEAR_BEFORE_WORD = re.compile(r"\b(?:19|20)\d{2}(?=[a-z])")  # "2026alto"
_SCORE_WORD = re.compile(r"\bscores?\d*\b")  # "score", "score1"
_PARENTHESIS = re.compile(r"[(\[][^)\]]*[)\]]?")  # "(expanded instrumentation)", also one left open
_DATE_RUN = re.compile(r"(?:\b\d{1,2}\b\s*){2,}")  # "10 3 26": a date, however it was punctuated
_RESIDUE_WINDOW = 3  # words of a title's tail tried as an instrument name


def _song_key(title: str) -> str:
    """A title as words to compare: normalised, with dates and year tags dropped."""
    text = _PARENTHESIS.sub(" ", title.lower())
    for pattern in (_INITIALS_YEAR, _GLUED_YEAR, _YEAR_BEFORE_WORD):
        text = pattern.sub(" ", text)
    return " ".join(_SCORE_WORD.sub(" ", _DATE_RUN.sub(" ", _normalise(text))).split())


def _names_of_song(key: str) -> set[str]:
    """The key and, when it is a known alias group's name, the whole group."""
    names = {key}
    for slug, alternatives in _known_aliases().items():
        group = {_song_key(slug), *(_song_key(a) for a in alternatives)}
        if key in group:
            names |= group
    return names


def _typo_of(a: str, b: str) -> bool:
    """Same words but for a typo: the same numbers, similar length, and a plain
    (never partial) similarity of MIN_SCORE."""
    same_numbers = re.findall(r"\d+", a) == re.findall(r"\d+", b)
    return same_numbers and _similar_length(a, b) and fuzz.ratio(a, b) >= MIN_SCORE


def _is_part_residue(words: list[str]) -> bool:
    """Whether the words left after a song's title look like a part's own
    labelling: an instrument ("Violin", "TBN 1 2") or a description of the file
    ("background", "lyrics only"; `part_descriptions` in data/title_aliases.yaml)."""
    tail = " ".join(words)
    if any(tail.startswith(_song_key(d)) for d in load("title_aliases.yaml")["part_descriptions"]):
        return True
    return any(resolve(" ".join(words[:n])) for n in range(1, min(_RESIDUE_WINDOW, len(words)) + 1))


def _names_song(key: str, name: str) -> bool:
    """Whether the file title `key` is the title `name` (or a typo of it),
    optionally led by an instrument ("Trumpet 1 Christmas Is") and followed by
    a part's own labelling."""
    words = key.split()
    leads = [0, *(n for n in range(1, min(_RESIDUE_WINDOW, len(words)) + 1) if resolve(" ".join(words[:n])))]
    for lead in leads:
        rest = words[lead:]
        for end in range(1, len(rest) + 1):
            head = " ".join(rest[:end])
            if (head == name or _typo_of(head, name)) and (end == len(rest) or _is_part_residue(rest[end:])):
                return True
    return False


def same_song(file_title: str, score_title: str) -> bool:
    """Whether a part file's cleaned title names the score's song: the same
    title (case, "the", punctuation, dates and year tags aside), a known alias
    of it, a typo of either, or the title followed by the part's own labelling
    ("Christmas Is Violin"). Stricter than match_slug: a title that merely sits
    inside another ("Christmas Is" in "Christmas Is Coming", "Sing" in "Sing Sing
    Sing") is a different song."""
    key = _song_key(file_title)
    return bool(key) and any(_names_song(key, n) for n in _names_of_song(_song_key(score_title)) if n)
