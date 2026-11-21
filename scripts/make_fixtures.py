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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        font = Path(tmp) / "SyntheticMusic.ttf"
        build_music_font(font)
        finale_style(font, OUT / "finale_full_labels.pdf")
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


if __name__ == "__main__":
    main()
