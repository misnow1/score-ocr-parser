"""Clean stage: remove music-font junk from tokens."""

import re
from dataclasses import replace
from functools import cache

from .data import load
from .models import Page, Token


@cache
def _music_fonts() -> tuple[str, ...]:
    data = load("music_fonts.yaml")
    return tuple(f.lower() for f in data["music_fonts"])


def _is_private_use(ch: str) -> bool:
    cp = ord(ch)
    return 0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0x10FFFF


_GLUED = re.compile(r"^(\d{1,3})([A-Z]{2}.*)$")


def _split_glued(tok: Token) -> list[Token]:
    """'29ALTO' becomes '29' and 'ALTO', the box divided in proportion to length."""
    m = _GLUED.match(tok.text)
    if not m:
        return [tok]
    bar, rest = m.groups()
    mid = tok.x0 + (tok.x1 - tok.x0) * len(bar) / len(tok.text)
    return [replace(tok, text=bar, x1=mid), replace(tok, text=rest, x0=mid)]


def clean(page: Page) -> Page:
    kept = []
    for tok in page.tokens:
        if any(m in tok.font.lower() for m in _music_fonts()):
            continue
        text = "".join(c for c in tok.text if not _is_private_use(c)).strip()
        if text:
            kept.extend(_split_glued(replace(tok, text=text)))
    return replace(page, tokens=kept)
