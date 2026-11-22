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
    tops: tuple[int, ...] = (110, 480),
) -> None:
    """Stacked systems of staff labels. Sibelius-style: the clef/rest glyphs are
    ordinary ASCII characters ('&', '?') set in an Opus-named font, so only the
    font name tells them apart from text. `instructions` maps a first-system
    label to a text instruction drawn above its staff."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((200, 60), "Synthetic Tune", fontname="helv", fontsize=24)
    spacing = 36
    for n, (top, labels) in enumerate(zip(tops, systems)):
        page.insert_text((140, top - 14), str(1 + 16 * n), fontname="helv", fontsize=7)
        for i, text in enumerate(labels):
            y = top + i * spacing
            page.insert_text((30, y), text, fontname="helv", fontsize=9)
            page.insert_text(
                (125, y), "&?", fontfile=str(opus_font), fontname="OpusStd", fontsize=14
            )
            page.draw_line((140, y), (580, y))
            if n == 0 and text in instructions:
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
MISMATCH_FIRST = ["Alto Saxophone 1", "Trumpet in Bb 1-4", "Trombone 1-4", "Guitar", "Drums"]
MISMATCH_LATER = ["A. Sx. 1", "Tpt. 1-4", "Tbn. 1-5", "Vln.", "Zork."]


# The first system (most resolving labels) has no bass; two later systems do.
LATER_ONLY_FIRST = ["Alto Saxophone 1", "Trumpet in Bb 1-4", "Trombone 1-4", "Piano", "Guitar", "Drums"]
LATER_ONLY_SECOND = ["A. Sx. 1", "Tpt. 1-4", "Tbn. 1-4", "Bass"]
LATER_ONLY_THIRD = ["A. Sx. 1", "Tpt. 1-4", "Tbn. 1-5", "E.B.", "Vln.", "Zork."]
VARIANT_FIRST = ["Alto Saxophone 1", "Electric Bass", "Drums"]
VARIANT_LATER = ["A. Sx. 1", "Bass", "Dr."]


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


def repeated_solos(music_font: Path, out: Path) -> None:
    """A solo printed above every staff, reminders on later systems, a chord
    symbol in front of a solo, page numbers in the margin and a system split in
    two stacks (the top staff alone, so the bar row sits above that stack)."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Repeat Tune", fontname="helv", fontsize=24)
    _system(p1, 150, FULL, music_font, [
        (150, 120, "1", 7), (300, 120, "9", 7),
        *[(320, ys_at(150, i) - 12, "ALTO SOLO", 9) for i in range(5)],
        (200, ys_at(150, 2) - 12, "G7 TBN SOLO", 9),
    ])
    _system(p1, 400, ABBR, music_font, [
        (150, 370, "17", 7), (180, ys_at(400, 0) - 12, "ALTO SOLO", 9),
    ])
    p2 = doc.new_page(width=612, height=792)
    _system(p2, 120, ABBR[:1], music_font, [
        (150, 100, "33", 7), (300, 108, "TBN SOLO", 9),
    ])
    _system(p2, 231, ABBR[2:], music_font, [
        *[(300, ys_at(231, i) - 12, "TBN SOLO", 9) for i in range(3)],
    ])
    p3 = doc.new_page(width=612, height=792)
    _system(p3, 150, ABBR, music_font, [
        (150, 120, "49", 7), (20, 120, "3", 7),
        (320, ys_at(150, 0) - 12, "ALTO SOLO", 9),
        (100, ys_at(150, 3) - 12, "SOLO", 9),
    ])
    doc.save(out)


CHAIR_FULL = ["Alto Saxophone", "Trumpet in Bb 3", "Guitar 1", "Guitar 2"]
CHAIR_ABBR = ["A. Sx.", "B Tpt. 3", "Gtrs."]


def chair_solos(music_font: Path, out: Path) -> None:
    """Chairs on features: named in the text (Guitar 1 and Guitar 2 side by side),
    taken from a numbered staff (Trumpet 3), and a shared "Gtrs." staff."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Chair Tune", fontname="helv", fontsize=24)
    _system(p1, 150, CHAIR_FULL, music_font, [
        (150, 120, "1", 7), (400, 120, "9", 7),
        (200, ys_at(150, 2) - 12, "GUITAR 1 SOLO", 9),
        (300, ys_at(150, 3) - 12, "GUITAR 2 SOLO", 9),
        (250, ys_at(150, 1) - 12, "SOLO", 9),
    ])
    _system(p1, 400, CHAIR_ABBR, music_font, [
        (150, 370, "17", 7),
        (250, ys_at(400, 2) - 12, "SOLO", 9),
    ])
    p2 = doc.new_page(width=612, height=792)
    _system(p2, 150, ["A. Sx.", "B Tpt. 3"], music_font, [(150, 120, "25", 7)])
    p3 = doc.new_page(width=612, height=792)
    _system(p3, 150, ["A. Sx.", "Gtr. 1", "Gtr. 2"], music_font, [
        (150, 120, "33", 7),
        # "GUITAR SOLO" above every staff but Gtr. 2's, which carries a bare "SOLO"
        (300, ys_at(150, 0) - 12, "GUITAR SOLO", 9),
        (300, ys_at(150, 1) - 12, "GUITAR SOLO", 9),
        (299, ys_at(150, 2) - 12, "SOLO", 9),
    ])
    doc.save(out)


def distinct_solos(music_font: Path, out: Path) -> None:
    """Solos of one instrument on neighbouring systems that are not copies: a
    trombone solo at bar 9 and another at bar 41 on the next system, and a
    guitar solo above "Gtr. 1" (restated on the next system, a reminder) followed
    by one above "Gtr. 2" on the next page (a different chair)."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Distinct Tune", fontname="helv", fontsize=24)
    _system(p1, 150, FULL, music_font, [
        (150, 120, "1", 7), (300, 120, "9", 7),
        (320, ys_at(150, 2) - 12, "TBN SOLO", 9),
    ])
    _system(p1, 400, ABBR, music_font, [
        (150, 370, "41", 7), (180, ys_at(400, 2) - 12, "TBN SOLO", 9),
    ])
    gtrs = ["A. Sx.", "Gtr. 1", "Gtr. 2"]
    p2 = doc.new_page(width=612, height=792)
    _system(p2, 120, gtrs, music_font, [
        (150, 100, "49", 7), (200, ys_at(120, 1) - 12, "SOLO", 9),
    ])
    _system(p2, 400, gtrs, music_font, [
        (150, 380, "57", 7), (180, ys_at(400, 1) - 12, "SOLO", 9),
    ])
    p3 = doc.new_page(width=612, height=792)
    _system(p3, 150, gtrs, music_font, [
        (150, 120, "65", 7), (200, ys_at(150, 2) - 12, "SOLO", 9),
    ])
    doc.save(out)


SHARED_FULL = ["Soprano Saxophone", "Alto Saxophone", "Clarinet in Bb", "Trumpet in Bb 3"]
SHARED_ABBR = ["S. Sx.", "A. Sx.", "Cl.", "B Tpt. 3"]


def shared_solos(music_font: Path, out: Path) -> None:
    """One marking over several instruments: a bare "SOLO" at the same place
    above the Soprano Sax, Clarinet and Trumpet 3 staves (marker A, bar 9), an
    "ALTO SOLO" that stays a single-instrument feature, and, on the next
    system but one, a bare "SOLO" over two staves at different places (two features)."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Shared Tune", fontname="helv", fontsize=24)
    _system(p1, 150, SHARED_FULL, music_font, [
        (150, 120, "1", 7), (200, 105, "A", 12), (400, 120, "9", 7),
        (400, ys_at(150, 0) - 12, "SOLO", 9),
        (400, ys_at(150, 2) - 12, "SOLO", 9),
        (400, ys_at(150, 3) - 12, "SOLO", 9),
        (500, ys_at(150, 1) - 12, "ALTO SOLO", 9),
    ])
    _system(p1, 330, SHARED_ABBR, music_font, [(150, 300, "17", 7)])
    _system(p1, 560, SHARED_ABBR, music_font, [
        (150, 530, "25", 7),
        (250, ys_at(560, 0) - 12, "SOLO", 9),
        (450, ys_at(560, 2) - 12, "SOLO", 9),
    ])
    doc.save(out)


VOCAL_LABELS = FULL + ["Voice Lead F", "Voice Lead M", "Voice bck F"]


def vocal_leads(music_font: Path, out: Path) -> None:
    """Vocal lead markings: "Female Lead Verse 1" with a bare "solo" above the
    Voice Lead F staff, a "Male Lead Verse 2" text whose "solo" sits above a
    backing vocal staff, a bare "solo" above the Voice Lead M staff (next page: the same voice on the
    next system is one feature), a lone one above Voice Lead F, and an
    instrument solo that must stay one."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Vocal Tune", fontname="helv", fontsize=24)
    _system(p1, 150, VOCAL_LABELS, music_font, [
        (150, 120, "1", 7), (200, 105, "B", 12),
        (200, ys_at(150, 0) - 12, "ALTO SOLO", 9),
        (300, ys_at(150, 5) - 18, "Female Lead Verse 1", 9),
        (300, ys_at(150, 5) - 12, "solo", 9),
        (450, ys_at(150, 6) - 15, "Male Lead Verse 2", 9),
        (450, ys_at(150, 7) - 12, "solo", 9),
    ])
    p2 = doc.new_page(width=612, height=792)
    _system(p2, 150, VOCAL_LABELS, music_font, [
        (150, 120, "9", 7),
        (300, ys_at(150, 6) - 12, "solo", 9),
    ])
    p3 = doc.new_page(width=612, height=792)
    _system(p3, 150, VOCAL_LABELS, music_font, [
        (150, 120, "17", 7),
        (300, ys_at(150, 5) - 12, "solo", 9),
    ])
    doc.save(out)


def non_bar_numbers(music_font: Path, out: Path) -> None:
    """Numbers that are not bar numbers: a time signature at the start of the
    system, a running header with a page number ("10 Score"), and triplet 3s
    (one alone above the staff, one glued to a second 3 inside the system)."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Number Tune", fontname="helv", fontsize=24)
    _system(p1, 150, FULL, music_font, [
        (150, 120, "1", 7), (300, 120, "9", 7),
        (125, 150, "44", 9),
        (130, ys_at(150, 0) - 12, "ALTO SOLO", 9),
    ])
    p2 = doc.new_page(width=612, height=792)
    _system(p2, 120, ABBR, music_font, [
        (54, 57, "10 Score", 9),
        (150, 100, "33", 7),
        (100, ys_at(120, 2) - 12, "TBN SOLO", 9),
    ])
    p3 = doc.new_page(width=612, height=792)
    _system(p3, 150, ABBR, music_font, [
        (150, 120, "49", 7), (400, 120, "57", 7),
        (250, 125, "3", 7), (255, ys_at(150, 2) + 5, "3 3", 7),
        (260, ys_at(150, 3) - 12, "GUITAR SOLO", 9),
    ])
    doc.save(out)


def _barlines(page, top: float, labels: int, xs: tuple[float, ...]) -> None:
    """Vertical barlines through every staff of a system (drawn, as a text-layer score does)."""
    for x in xs:
        page.draw_line((x, top - 8), (x, ys_at(top, labels - 1) + 8))


BAR_XS = (140, 240, 340, 440, 540)  # four bars; the first and last lines are the system edges


def sparse_bar_numbers(music_font: Path, out: Path) -> None:
    """Bar numbers printed sparsely: one on page 1 (centred on its barline) and
    none on page 2, so a solo mid-system needs barline counting and a system
    without numbers continues from the one before."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Sparse Tune", fontname="helv", fontsize=24)
    _system(p1, 150, FULL, music_font, [
        (237, 120, "5", 7),  # bar 5 starts at the second barline
        (145, ys_at(150, 0) - 12, "ALTO SOLO", 9),  # bar 4: left of the printed number
        (345, ys_at(150, 2) - 12, "TBN SOLO", 9),  # bar 6: one barline past the number
    ])
    _barlines(p1, 150, len(FULL), BAR_XS)
    p2 = doc.new_page(width=612, height=792)
    _system(p2, 150, ABBR, music_font, [
        (445, ys_at(150, 3) - 12, "GUITAR SOLO", 9),  # no number on the page: bar 8 + 3
        (145, ys_at(150, 0) - 12, "ALTO SOLO", 9),  # first bar of the row: a reminder of page 1's
        (345, ys_at(150, 2) - 12, "TBN SOLO", 9),  # mid-row on the next row: a new solo, bar 10
    ])
    _barlines(p2, 150, len(ABBR), BAR_XS)
    doc.save(out)


RA_CUE = ["Piano", "Bass", "Drum Set"]
RA_FULL = [
    "Piccolo",
    "Alto Saxophone 1",
    "Baritone Saxophone",
    "Trumpet in Bb 1",
    "Trumpet in Bb 2",
    "Trombone 1",
    "Violins",
    "Piano",
    "Bass",
    "Drum Set",
]
RA_ABBR = ["Picc.", "A. Sx. 1", "Bari. Sax.", "B Tpt. 1", "B Tpt. 2", "Tbn. 1", "Vlns.", "Pno.", "Bass", "D. S."]


def _right_label(page, right: float, y: float, text: str, size: float = 9) -> float:
    """Draw `text` so that it ends at x=`right`; returns its left edge."""
    x = right - pymupdf.get_text_length(text, fontname="helv", fontsize=size)
    page.insert_text((x, y), text, fontname="helv", fontsize=size)
    return x


def right_aligned(music_font: Path, out: Path) -> None:
    """Right-aligned staff labels, as a notation program exports them. Page 1: a
    short two-staff cue system above the full system, a bare "Score" tag, a
    group label ("Trumpets") and a time signature after each label (glued to the
    baritone's). Page 2: a running title, "Score 2", abbreviations that include
    "Vlns." and "B Tpt.", and chord symbols on the piano's line."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Right Aligned Tune", fontname="helv", fontsize=24)
    for i, text in enumerate(RA_CUE):
        y = 120 + i * 30
        _right_label(p1, 90, y, text)
        p1.draw_line((100, y), (580, y))
    _right_label(p1, 110, 215, "Score")
    for i, text in enumerate(RA_FULL):
        y = 260 + i * 30
        _right_label(p1, 110, y, text)
        p1.draw_line((120, y), (580, y))
        p1.insert_text((126, y), MUSIC_GLYPHS, fontfile=str(music_font), fontname="SynMusic", fontsize=14)
        gap = 3 if text.startswith("Baritone") else 30
        p1.insert_text((110 + gap, y), "44", fontname="helv", fontsize=9 if gap == 3 else 14)
        if text.startswith("Trumpet in Bb 1"):
            _right_label(p1, 110, y - 15, "Trumpets")
    p2 = doc.new_page(width=612, height=792)
    p2.insert_text((20, 30), "2 Synthetic Right Aligned Tune", fontname="helv", fontsize=9)
    _right_label(p2, 70, 75, "Score 2")
    for i, text in enumerate(RA_ABBR):
        y = 120 + i * 30
        x = _right_label(p2, 70, y, text)
        p2.draw_line((80, y), (580, y))
        if text == "Pno.":
            p2.insert_text((74, y), "D D A7", fontname="helv", fontsize=9)
    doc.save(out)


def _repair_system(page, music_font, rows, right=130.0) -> None:
    """Right-aligned label rows (label text or None for a staff without a label,
    or ("noise", text) for a non-label line that has no staff). Each staff gets a
    clef glyph at x=140 and a rule."""
    y = rows[0][0]
    for top, row in rows:
        y = top
        if isinstance(row, tuple):  # text in the label column with no staff beside it
            _right_label(page, right, y, row[1])
            continue
        if row is not None:
            _right_label(page, right, y, row)
        page.draw_line((150, y), (580, y))
        page.insert_text((140, y), MUSIC_GLYPHS, fontfile=str(music_font), fontname="SynMusic", fontsize=14)


def label_repair_missing(music_font: Path, out: Path) -> None:
    """Pages 2-3 repeat abbreviated labels that were once dropped: two 3-word
    labels (read as running titles because they repeat), a "1&2 B Tpt." whose
    transposition letter ends the label, and the group label "TBNS"."""
    doc = pymupdf.open()
    full = ["Alto Saxophone i & II", "Tenor Saxophone I & II", "Baritone Saxophone",
            "Trumpet 1&2 in Bb", "Trombone 1&2", "Drum Set"]
    short = ["A. Sx. I & II", "T. Sx. I & II", "B. Sx.", "1&2 B Tpt.", "TBNS", "Tbn.1&2", "D. S."]
    for number, labels in enumerate([full, short, short], start=1):
        page = doc.new_page(width=612, height=792)
        page.insert_text((200, 60), "Synthetic Repair Tune", fontname="helv", fontsize=14)
        page.insert_text((160, 95), "1", fontname="helv", fontsize=7)
        rows = [(120 + i * 36.0, text) for i, text in enumerate(labels)]
        if number > 1:  # the group label sits between the trumpet and trombone staves
            rows = [(y, ("noise", t) if t == "TBNS" else t) for y, t in rows]
        _repair_system(page, music_font, rows)
    doc.save(out)


def label_repair_noise(music_font: Path, out: Path) -> None:
    """Non-label lines in the label column: a feel marking above the top staff, a
    parenthesised cue and a "...only" note between staves. Rehearsal mark A and a
    solo sit on the top staff, which the feel line used to hide."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((200, 60), "Synthetic Noise Tune", fontname="helv", fontsize=14)
    labels = ["Soprano Saxophone", "Alto Saxophone", "Trumpet 1", ("noise", "(Memory out front)"),
              "Trombone 1", "Piano", ("noise", "Drums only......"), "Drum Set"]
    rows = [(150.0, ("noise", "Swing Feel in 8ths"))]
    rows += [(180 + i * 36.0, t) for i, t in enumerate(labels)]
    _repair_system(page, music_font, rows)
    page.insert_text((220, 125), "A", fontname="helv", fontsize=12)
    page.insert_text((160, 135), "9", fontname="helv", fontsize=7)
    page.insert_text((300, 208), "ALTO SOLO", fontname="helv", fontsize=9)
    doc.save(out)


def label_repair_unlabeled(music_font: Path, out: Path) -> None:
    """One staff in the middle has no label, and the text "Piano" is printed by
    the title, not beside a staff."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((200, 60), "Synthetic Unlabeled Tune", fontname="helv", fontsize=14)
    _right_label(page, 130, 80, "Piano")
    labels = ["Trumpet in Bb", "Alto Saxophone", "Trombone", None, "Organ", "Drum Set"]
    _repair_system(page, music_font, [(180 + i * 45.0, t) for i, t in enumerate(labels)])
    doc.save(out)


def label_repair_overprint(music_font: Path, out: Path) -> None:
    """The Piccolo label is printed over the Alto Sax label on one line."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((200, 60), "Synthetic Overprint Tune", fontname="helv", fontsize=14)
    _repair_system(page, music_font, [(150.0, "Piccolo"), (190.0, "Tenor Saxophone"), (226.0, "Drum Set")])
    _right_label(page, 130, 152, "Alto Saxophone I & II")  # 2 pt below the Piccolo line
    page.draw_line((150, 152), (580, 152))
    page.insert_text((140, 152), MUSIC_GLYPHS, fontfile=str(music_font), fontname="SynMusic", fontsize=14)
    doc.save(out)


def rehearsal_marks(music_font: Path, out: Path) -> None:
    """Mark A printed below a tempo line, mark C in one row with the words
    "VERSE 2", and a page with no mark at all (the mark must not carry over)."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Marks Tune", fontname="helv", fontsize=24)
    _system(p1, 150, FULL, music_font, [
        (150, 120, "1", 7), (300, 120, "9", 7),
        (150, 90, "Moderate swing", 10),
        (200, 105, "A", 12),
        (320, ys_at(150, 2) - 12, "TBN SOLO", 9),
    ])
    _system(p1, 400, ABBR, music_font, [
        (150, 370, "17", 7),
        (200, 350, "C", 12), (216, 350, "VERSE", 10), (252, 350, "2", 10),
        (350, ys_at(400, 3) - 12, "GUITAR SOLO", 9),
    ])
    p2 = doc.new_page(width=612, height=792)
    _system(p2, 150, ABBR, music_font, [
        (150, 120, "33", 7),
        (250, ys_at(150, 4) - 12, "DRUM SOLO", 9),
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


def rotated_scan(src: Path, out: Path, rotation: int, dpi: int = 300) -> None:
    """An image-only PDF whose pixels hold the content turned `rotation` degrees
    clockwise, on a page with rotation entry 0 (as a sideways scan is stored)."""
    with pymupdf.open(src) as doc:
        pix = doc[0].get_pixmap(dpi=dpi, alpha=False)
        w, h = doc[0].rect.width, doc[0].rect.height
    turner = pymupdf.open()
    tp = turner.new_page(width=h, height=w)
    tp.insert_image(tp.rect, stream=pix.tobytes("png"), rotate=(360 - rotation) % 360)  # counter-clockwise
    turned = tp.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
    scan = pymupdf.open()
    page = scan.new_page(width=h, height=w)
    page.insert_image(page.rect, stream=turned.tobytes("png"))
    scan.save(out, deflate=True)


def pattern_scanned(src: Path, out: Path, dpi: int = 300) -> None:
    """A scan drawn as a tiling-pattern fill: no image on the page, no text layer."""
    with pymupdf.open(src) as doc:
        pix = doc[0].get_pixmap(dpi=dpi, alpha=False)
        rect = doc[0].rect
    w, h = rect.width, rect.height
    scan = pymupdf.open()
    page = scan.new_page(width=w, height=h)
    image = page.insert_image(rect, stream=pix.tobytes("png"))
    pattern = scan.get_new_xref()
    scan.update_object(
        pattern,
        f"<< /Type /Pattern /PatternType 1 /PaintType 1 /TilingType 1 "
        f"/BBox [0 0 {w} {h}] /XStep {w} /YStep {h} "
        f"/Resources << /XObject << /Im0 {image} 0 R >> >> >>",
    )
    scan.update_stream(pattern, f"q {w} 0 0 {h} 0 0 cm /Im0 Do Q".encode())
    # Replace the page's own image drawing with a pattern-filled rectangle.
    scan.update_stream(page.get_contents()[0], f"/Pattern cs /P0 scn 0 0 {w} {h} re f".encode())
    scan.xref_set_key(page.xref, "Resources", f"<< /Pattern << /P0 {pattern} 0 R >> >>")
    scan.save(out, deflate=True)


def absent_instrument_solo(music_font: Path, out: Path) -> None:
    """A "VIOLIN SOLO" on a score whose instrumentation has no violin, and a bare "SOLO"."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Tune Absent", fontname="helv", fontsize=24)
    _system(p1, 150, ["Alto Saxophone 1", "Piano"], music_font, [
        (150, 120, "1", 7), (300, 120, "9", 7),
        (320, ys_at(150, 1) - 12, "VIOLIN SOLO", 9),
    ])
    doc.save(out)


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
        sibelius_style(
            opus,
            [LATER_ONLY_FIRST, LATER_ONLY_SECOND, LATER_ONLY_THIRD],
            {},
            OUT / "sibelius_later_only_instrument.pdf",
            tops=(110, 330, 550),
        )
        sibelius_style(
            opus,
            [VARIANT_FIRST, VARIANT_LATER],
            {},
            OUT / "sibelius_bass_variant.pdf",
        )
        finale_solos(font, OUT / "finale_solos.pdf")
        right_aligned(font, OUT / "finale_right_aligned.pdf")
        repeated_solos(font, OUT / "finale_repeated_solos.pdf")
        label_repair_missing(font, OUT / "label_repair_missing.pdf")
        label_repair_noise(font, OUT / "label_repair_noise.pdf")
        label_repair_unlabeled(font, OUT / "label_repair_unlabeled.pdf")
        label_repair_overprint(font, OUT / "label_repair_overprint.pdf")
        rehearsal_marks(font, OUT / "rehearsal_marks.pdf")
        chair_solos(font, OUT / "finale_chair_solos.pdf")
        non_bar_numbers(font, OUT / "finale_non_bar_numbers.pdf")
        sparse_bar_numbers(font, OUT / "finale_sparse_bar_numbers.pdf")
        vocal_leads(font, OUT / "finale_vocal_leads.pdf")
        distinct_solos(font, OUT / "finale_distinct_solos.pdf")
        shared_solos(font, OUT / "finale_shared_solos.pdf")
        absent_instrument_solo(font, OUT / "finale_absent_instrument_solo.pdf")
    for dpi in (300, 90):
        scanned(OUT / "finale_full_labels.pdf", OUT / f"scan_{dpi}dpi.pdf", dpi)
    pattern_scanned(OUT / "finale_full_labels.pdf", OUT / "scan_pattern.pdf")
    for rotation in (90, 270):
        rotated_scan(OUT / "finale_full_labels.pdf", OUT / f"scan_rotated_{rotation}.pdf", rotation)


if __name__ == "__main__":
    main()
