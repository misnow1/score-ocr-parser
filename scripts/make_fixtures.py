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


def build_music_font(path: Path, family: str = "SyntheticMusic", chars: str = MUSIC_GLYPHS) -> None:
    """A tiny TrueType font whose only glyphs are 'music' squares for `chars`."""
    names = [".notdef"] + [f"uni{ord(c):04X}" for c in chars]
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({ord(c): f"uni{ord(c):04X}" for c in chars})
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
    fb.setupNameTable({"familyName": family, "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    fb.save(str(path))


def finale_style(music_font: Path, out: Path, glyphs: str = MUSIC_GLYPHS, glyph_x: float = 150) -> None:
    """One system: full instrument labels, music glyphs, a bar number."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((200, 60), "Synthetic Tune", fontname="helv", fontsize=24)
    for i, text in enumerate(LABELS):
        y = 150 + i * 60
        page.insert_text((30, y), text, fontname="helv", fontsize=9)
        page.draw_line((140, y), (580, y))
        page.insert_text(
            (glyph_x, y - (5 if glyph_x >= 150 else 0)), glyphs, fontfile=str(music_font), fontname="SynMusic", fontsize=14
        )
    page.insert_text((140, 135), "1", fontname="helv", fontsize=7)
    doc.save(out)


def sibelius_style(
    opus_font: Path,
    systems: list[list[str]],
    instructions: dict[str, str],
    out: Path,
) -> None:
    """Stacked systems of staff labels. Sibelius-style: the clef/rest glyphs are
    ordinary ASCII characters ('&', '?') set in an Opus-named font, so only the
    font name tells them apart from text. `instructions` maps a first-system
    label to a text instruction drawn above its staff."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((200, 60), "Synthetic Tune", fontname="helv", fontsize=24)
    spacing = 36
    tops = [110, 480]
    for top, labels in zip(tops, systems):
        page.insert_text((140, top - 14), "1" if top == tops[0] else "17", fontname="helv", fontsize=7)
        for i, text in enumerate(labels):
            y = top + i * spacing
            page.insert_text((30, y), text, fontname="helv", fontsize=9)
            page.insert_text(
                (125, y), "&?", fontfile=str(opus_font), fontname="OpusStd", fontsize=14
            )
            page.draw_line((140, y), (580, y))
            if top == tops[0] and text in instructions:
                page.insert_text((200, y - 12), instructions[text], fontname="helv", fontsize=8)
    doc.save(out)


def multispan_style(one: Path, two: Path, out: Path) -> None:
    """Sibelius/PrimoPDF-style: each glyph word is two glyphs in two unlisted
    fonts, adjacent so they form one word spanning two spans."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((200, 60), "Synthetic Tune", fontname="helv", fontsize=24)
    page.insert_text((140, 136), "1", fontname="helv", fontsize=7)
    for i, text in enumerate(LABELS):
        y = 150 + i * 60
        page.insert_text((30, y), text, fontname="helv", fontsize=9)
        page.draw_line((140, y), (580, y))
        page.insert_text((118, y), "&", fontfile=str(one), fontname="GlyphOne", fontsize=14)
        page.insert_text((118 + 14 * 0.7, y), "?", fontfile=str(two), fontname="GlyphTwo", fontsize=14)
    doc.save(out)


SIBELIUS_FULL = [
    "Flute (Oboe) 1-3",
    "Alto Saxophone i & II",
    "Trumpet in Bb 1-4",
    "Trombone 1-4",
    "Guitar 1",
    "Guitar 2",
    "Electric Bass",
    "Drum Set",
]
SIBELIUS_ABBREVIATED = [
    "Fl. (Ob.) 1-3",
    "A. Sx. i & II",
    "Tpt. 1-4",
    "Tbn. 1-4",
    "Gtr. 1",
    "Gtr. 2",
    "E.B.",
    "D. S.",
]
SIBELIUS_INSTRUCTIONS = {
    "Alto Saxophone i & II": "to Flute",
    "Trumpet in Bb 1-4": "piccolo trpt",
    "Trombone 1-4": "Mute",
}
NONSTANDARD = ["Violin", "Viola", "Cello", "Organ", "Lead Vocal", "Flugelhorn"]
NONSTANDARD_ABBREVIATED = ["Vln.", "Vla.", "Vc.", "Org.", "L. Voc.", "Flgh."]
MISMATCH_FIRST = ["Alto Saxophone 1", "Trumpet in Bb 1-4", "Trombone 1-4"]
MISMATCH_LATER = ["A. Sx. 1", "Tpt. 1-4", "Tbn. 1-5", "Vln.", "Zork."]


FULL = ["Alto Saxophone 1", "Trumpet in Bb 1-4", "Trombone 1-4", "Guitar", "Drums"]
ABBR = ["A. Sx. 1", "Tpt. 1-4", "Tbn. 1-4", "Gtr.", "Dr."]
STAFF_GAP = 30


def ys_at(top: float, index: int) -> float:
    return top + index * STAFF_GAP


def _system(page, top, labels, music_font, texts) -> None:
    """Draw one system (labels, rules, glyphs); texts are (x, y, string, fontsize)."""
    for i, text in enumerate(labels):
        y = ys_at(top, i)
        page.insert_text((30, y), text, fontname="helv", fontsize=9)
        page.draw_line((140, y), (580, y))
        page.insert_text(
            (150, y - 5), MUSIC_GLYPHS, fontfile=str(music_font), fontname="SynMusic", fontsize=14
        )
    for x, y, text, size in texts:
        page.insert_text((x, y), text, fontname="helv", fontsize=size)


def finale_solos(music_font: Path, out: Path) -> None:
    """Two systems on page 1 and one on page 2, with solos, bars and rehearsal marks."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Tune Two", fontname="helv", fontsize=24)
    _system(p1, 150, FULL, music_font, [
        (150, 120, "1", 7), (300, 120, "9", 7),
        (150, 105, "VERSE", 10),
        (400, 138, "Swing", 9),
        (320, ys_at(150, 2) - 12, "TBN SOLO", 9),
    ])
    _system(p1, 400, ABBR, music_font, [
        (150, 370, "17", 7), (200, 345, "B", 12),
        (350, 388, "29ALTO SOLO", 9),
        (250, ys_at(400, 3) - 12, "GUITAR SOLO", 9),
    ])
    p2 = doc.new_page(width=612, height=792)
    _system(p2, 150, ABBR, music_font, [
        (150, 120, "33", 7), (200, 105, "C", 12),
        (200, ys_at(150, 4) - 12, "1x - Solo", 9),
        (350, ys_at(150, 4) - 12, "vamp for drum feature", 9),
        (250, ys_at(150, 3) - 12, "Male vocal solo", 9),
    ])
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
        jazz = Path(tmp) / "Jazz.ttf"
        build_music_font(jazz, family="Jazz", chars="\u0153&\u2019\u00e3")
        finale_style(jazz, OUT / "finale_jazz_glyphs.pdf", glyphs="\u0153&\u2019\u00e3", glyph_x=118)
        one, two = Path(tmp) / "One.ttf", Path(tmp) / "Two.ttf"
        build_music_font(one, family="Glyph One", chars="&")
        build_music_font(two, family="Glyph Two", chars="?")
        multispan_style(one, two, OUT / "sibelius_multispan_glyphs.pdf")
        opus = Path(tmp) / "Opus.ttf"
        build_music_font(opus, family="Opus Std", chars="&?")
        sibelius_style(
            opus,
            [SIBELIUS_FULL, SIBELIUS_ABBREVIATED],
            SIBELIUS_INSTRUCTIONS,
            OUT / "sibelius_abbreviated.pdf",
        )
        sibelius_style(
            opus,
            [NONSTANDARD, NONSTANDARD_ABBREVIATED],
            {},
            OUT / "sibelius_nonstandard.pdf",
        )
        sibelius_style(
            opus,
            [MISMATCH_FIRST, MISMATCH_LATER],
            {},
            OUT / "sibelius_mismatch.pdf",
        )
        finale_solos(font, OUT / "finale_solos.pdf")
    for dpi in (300, 90):
        scanned(OUT / "finale_full_labels.pdf", OUT / f"scan_{dpi}dpi.pdf", dpi)


if __name__ == "__main__":
    main()
