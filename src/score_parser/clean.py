"""Clean stage: remove music-font junk from tokens."""

from dataclasses import replace
from functools import cache
from importlib.resources import files

import yaml

from .models import Page


@cache
def _music_fonts() -> tuple[str, ...]:
    data = yaml.safe_load(files("score_parser.data").joinpath("music_fonts.yaml").read_text())
    return tuple(f.lower() for f in data["music_fonts"])


def _is_private_use(ch: str) -> bool:
    cp = ord(ch)
    return 0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0x10FFFF


def clean(page: Page) -> Page:
    kept = []
    for tok in page.tokens:
        if any(m in tok.font.lower() for m in _music_fonts()):
            continue
        text = "".join(c for c in tok.text if not _is_private_use(c)).strip()
        if text:
            kept.append(replace(tok, text=text))
    return replace(page, tokens=kept)
