"""Source stage: PDF text layer to Pages of Tokens."""

from pathlib import Path

import pymupdf

from .models import Page, Token


def read_pages(path: Path) -> list[Page]:
    pages = []
    with pymupdf.open(path) as doc:
        for i, pg in enumerate(doc, start=1):
            spans = [
                (pymupdf.Rect(s["bbox"]), s["font"])
                for b in pg.get_text("dict")["blocks"]
                for ln in b.get("lines", [])
                for s in ln["spans"]
            ]
            tokens = []
            for x0, y0, x1, y1, text, *_ in pg.get_text("words"):
                centre = pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2)
                font = next((f for r, f in spans if centre in r), "")
                tokens.append(Token(text, x0, y0, x1, y1, i, font))
            pages.append(Page(i, pg.rect.width, pg.rect.height, tokens))
    return pages
