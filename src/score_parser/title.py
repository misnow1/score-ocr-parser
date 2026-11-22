"""Score title: cleaned from the filename, else the large text on page 1."""

import re
from pathlib import Path

from .instruments import resolve
from .layout import lines
from .models import Page

_DATE = re.compile(
    r"\b(\d{4}[-./_]\d{1,2}[-./_]\d{1,2}|\d{1,2}[-./_]\d{1,2}[-./_]\d{2,4}|\d{8})\b"
)
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_PARENS_COPY = re.compile(r"[(\[]\s*(copy|\d+)(\s+\d+)?\s*[)\]]", re.I)
_NOISE_WORDS = re.compile(
    r"\b(scores?|copy|copies|ajc|full|conductor|final|draft)\b", re.I
)
_LARGE = 0.85  # a token this fraction of the tallest counts as "large text"


_TRAILING_PART = re.compile(r"\s[-–]\s*([^-–]+)$")


def _drop_part_word(text: str) -> str:
    """Drop a trailing " - Piano" style part name (only after a dash)."""
    match = _TRAILING_PART.search(text)
    if match and resolve(match.group(1).strip()):
        return text[: match.start()]
    return text


def clean_filename(stem: str) -> str:
    text = _drop_part_word(stem.replace("_", " "))
    for pattern in (_PARENS_COPY, _DATE, _YEAR, _NOISE_WORDS):
        text = pattern.sub(" ", text)
    text = re.sub(r"[\s\-–,]+", " ", text).strip(" -–.")
    return text


def page_one_title(page: Page) -> str | None:
    words = [t for t in page.tokens if re.search(r"[A-Za-z]", t.text)]
    if not words:
        return None
    tallest = max(t.y1 - t.y0 for t in words)
    large = [t for t in words if t.y1 - t.y0 >= tallest * _LARGE]
    top = min(large, key=lambda t: t.y0)
    line = [t for ln in lines(large) for t in ln if abs(t.yc - top.yc) < tallest]
    return " ".join(t.text for t in sorted(line, key=lambda t: t.x0)) or None


def score_title(path: Path, pages: list[Page]) -> tuple[str, str]:
    """(title, source) where source is "filename" or "page 1"."""
    cleaned = clean_filename(path.stem)
    if re.search(r"[A-Za-z]", cleaned):
        return cleaned, "filename"
    fallback = page_one_title(pages[0]) if pages else None
    return (fallback, "page 1") if fallback else (path.stem, "filename")
