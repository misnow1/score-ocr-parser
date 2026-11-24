"""Find the part files of a song in a local parts tree (read-only).

The tree is `parts/<instrument-folder>/<song file>.pdf` (ADR 0004). A song's
parts are found by matching the cleaned song title of each filename to the
score's title across every instrument folder; the `scores/` folder holds the
conductor scores and is skipped. Nothing is written. Shared by the corpus tests
and scripts/corpus_counts.py.
"""

from pathlib import Path

from score_parser import PartReport, parse_part
from rapidfuzz import fuzz

from score_parser.matching import MIN_LENGTH_RATIO, MIN_SCORE, _normalise
from score_parser.part import read_part_info
from score_parser.title import clean_filename

SCORES_FOLDER = "scores"


def _words(title: str) -> str:
    """The normalised title without words that hold a digit: a date left in a filename
    ("11:3:26") or a year-tagged name ("JC2026") must not keep a title from matching,
    or give another one a match."""
    return " ".join(w for w in _normalise(title).split() if not any(c.isdigit() for c in w))


def _same_song(a: str, b: str) -> bool:
    a, b = _words(a), _words(b)
    if not (a and b):
        return False
    if min(len(a), len(b)) < MIN_LENGTH_RATIO * max(len(a), len(b)):
        return False
    # Whole-title similarity, not the partial one --numbers-dir uses: a short title
    # ("Holiday In") sits inside a longer one ("Away In A Manger") without being it.
    return fuzz.token_sort_ratio(a, b) >= MIN_SCORE


def find_parts(parts_root: Path, title: str) -> list[Path]:
    """The part PDFs under `parts_root` whose cleaned song title matches `title`, sorted."""
    root = Path(parts_root)
    if not root.is_dir():
        return []
    return sorted(
        pdf
        for folder in root.iterdir()
        if folder.is_dir() and folder.name != SCORES_FOLDER
        for pdf in folder.iterdir()
        if pdf.suffix.lower() == ".pdf" and _same_song(read_part_info(pdf)[1], title)
    )


def parts_of_score(parts_root: Path, score_stem: str) -> list[PartReport]:
    """Read in place every part of the score whose file name (without .pdf) is `score_stem`."""
    return [parse_part(pdf) for pdf in find_parts(parts_root, clean_filename(score_stem))]
