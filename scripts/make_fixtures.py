"""Generate the synthetic score fixtures in tests/fixtures/synthetic/.

Everything here is invented; no real score content is used. Run with:
    uv run python scripts/make_fixtures.py
"""

import tempfile
from pathlib import Path

import pymupdf
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "synthetic"
MUSIC_GLYPHS = ""  # private-use codepoints (clef, notehead, rest)

LABELS = [
    "Alto Saxophone 1",
    "Tenor Saxophone 1",
    "Trumpet in Bb 1-4",
    "Trombone 1-4",
    "Piano",
    "Bass",
    "Drums",
    "Zorblax Section",  # deliberately unknown
]


def build_music_font(path: Path) -> None:
    """A tiny TrueType font whose only glyphs are private-use 'music' squares."""
    names = [".notdef"] + [f"uni{ord(c):04X}" for c in MUSIC_GLYPHS]
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({ord(c): f"uni{ord(c):04X}" for c in MUSIC_GLYPHS})
    glyphs = {}
    for n in names:
        pen = TTGlyphPen(None)
        pen.moveTo((100, 0))
        pen.lineTo((100, 700))
        pen.lineTo((600, 700))
        pen.lineTo((600, 0))
        pen.closePath()
        glyphs[n] = pen.glyph()
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({n: (700, 100) for n in names})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "SyntheticMusic", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    fb.save(str(path))


def finale_style(music_font: Path, out: Path) -> None:
    """One system: full instrument labels, music glyphs, a bar number."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((200, 60), "Synthetic Tune", fontname="helv", fontsize=24)
    for i, text in enumerate(LABELS):
        y = 150 + i * 60
        page.insert_text((30, y), text, fontname="helv", fontsize=9)
        page.draw_line((140, y), (580, y))
        page.insert_text(
            (150, y - 5), MUSIC_GLYPHS, fontfile=str(music_font), fontname="SynMusic", fontsize=14
        )
    page.insert_text((140, 135), "1", fontname="helv", fontsize=7)
    doc.save(out)


def scanned(src: Path, out: Path, dpi: int) -> None:
    """An image-only PDF: the source page rendered at `dpi`, no text layer."""
    with pymupdf.open(src) as doc:
        pix = doc[0].get_pixmap(dpi=dpi, alpha=False)
        rect = doc[0].rect
    scan = pymupdf.open()
    page = scan.new_page(width=rect.width, height=rect.height)
    page.insert_image(rect, stream=pix.tobytes("png"))
    scan.save(out, deflate=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        font = Path(tmp) / "SyntheticMusic.ttf"
        build_music_font(font)
        finale_style(font, OUT / "finale_full_labels.pdf")
    for dpi in (300, 90):
        scanned(OUT / "finale_full_labels.pdf", OUT / f"scan_{dpi}dpi.pdf", dpi)


if __name__ == "__main__":
    main()
