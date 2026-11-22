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
# Always noise: "score", "AJC". Words that can also be part of a title ("Final
# Countdown", "Full Moon", "Copy Cat") go only when set off by a dash or
# brackets, at the end of the name, or next to a sure noise word or a date.
_SURE_NOISE = re.compile(r"\b(scores?|ajc)\b", re.I)
_MAYBE = r"(?:copy|copies|full|conductor|final|draft)"
_MAYBE_SET_OFF = re.compile(
    rf"[(\[]\s*{_MAYBE}\s*[)\]]"
    rf"|(?<=[-–])\s*\b{_MAYBE}\b(?=\s*(?:[-–]|$))"
    rf"|(?:(?<=\s)|^)\b{_MAYBE}\b(?=\s*[-–])"
    rf"|\s\b{_MAYBE}\s*$",
    re.I,
)
_MARK = "\0"
_MAYBE_BESIDE_MARK = re.compile(rf"{_MARK}\s*\b{_MAYBE}\b|\b{_MAYBE}\b\s*{_MARK}", re.I)
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
    text = _MAYBE_SET_OFF.sub(" ", _PARENS_COPY.sub(" ", text))
    for pattern in (_DATE, _YEAR, _SURE_NOISE):
        text = pattern.sub(_MARK, text)
    while (stripped := _MAYBE_BESIDE_MARK.sub(_MARK, text)) != text:
        text = stripped
    text = text.replace(_MARK, " ")
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
