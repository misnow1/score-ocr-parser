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


def chord_text_solos(music_font: Path, out: Path) -> None:
    """Chord symbols beside and glued to solo wording: glued chords on a bare
    "Solo" over a guitar staff (not a feature), a chord glued to a named solo,
    chords beside a named solo, chord text alone, and one chord before a bare "SOLO"."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Chord Tune", fontname="helv", fontsize=24)
    _system(p1, 150, ["Alto Saxophone", "Trombone", "Guitar"], music_font, [
        (150, 120, "1", 7), (400, 120, "9", 7),
        (200, ys_at(150, 2) - 12, "Bbmaj7(b5)/GA9 Solo", 9),
        (320, ys_at(150, 1) - 12, "E9 Dm7 TBN SOLO", 9),
        (450, ys_at(150, 0) - 12, "Bbmaj7(b5)/GA9 ALTO SOLO", 9),
        (250, ys_at(150, 0) - 12, "G7C", 9),
    ])
    _system(p1, 400, ["Alto Saxophone", "Trombone", "Guitar"], music_font, [
        (150, 370, "17", 7),
        (200, ys_at(400, 2) - 12, "E9 Dm7Solo", 9),
        (320, ys_at(400, 1) - 12, "A7TBN SOLO", 9),
    ])
    p2 = doc.new_page(width=612, height=792)
    _system(p2, 150, ["Alto Saxophone", "Trombone", "Guitar"], music_font, [
        (150, 120, "33", 7),
        (200, ys_at(150, 2) - 12, "G7 SOLO", 9),  # one chord, bare "Solo": a possible feature
        (400, ys_at(150, 1) - 12, "Dm7", 9),
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


HANDOVER_LABELS = [
    "Alto Saxophone 1", "Trumpet in Bb 1-4", "Voice Lead F", "Voice Lead M", "Voice bck F", "Voice bck M", "Drums",
]
HANDOVER_BARS = (140, 210, 280, 350, 420, 490, 560)  # six bars, 70 pt each
F, M, BCK_F, BCK_M = 2, 3, 4, 5  # staff indices in HANDOVER_LABELS


def _sing(page, top: float, bar: int, staves: tuple[int, ...], words: int = 6) -> None:
    """Lyric words ("la") under the given voice staves in bar `bar` (0-based) of a HANDOVER system."""
    left, right = HANDOVER_BARS[bar], HANDOVER_BARS[bar + 1]
    step = (right - left - 12) / words
    for staff in staves:
        for k in range(words):
            page.insert_text((left + 6 + k * step, ys_at(top, staff) + 12), "la", fontname="helv", fontsize=7)


def _handover_system(page, music_font: Path, first_bar: int, texts=(), left_edge: bool = True) -> None:
    """A HANDOVER system with drawn barlines (not the left edge, when `left_edge` is false)."""
    top = 150
    _system(page, top, HANDOVER_LABELS, music_font, [(150, top - 30, str(first_bar), 7), *texts])
    _barlines(page, top, len(HANDOVER_LABELS), HANDOVER_BARS if left_edge else HANDOVER_BARS[1:])


def vocal_handover(music_font: Path, out: Path) -> None:
    """The lead vocal changes with no wording, read from lyric words under the voice staves.
    Page 1 (bars 1-6, mark B at bar 3): the female and both backing staves sing bars 1-2, the male
    alone sings bars 3-4 (a handover to the male), the female alone sings bars 5-6 (back to the
    female). Page 2 (bars 7-12): every voice staff sings every bar, and in bar 12 only the two leads
    sing together, so no lead is invented. Page 3 (bars 13-18): the female sings, then the male alone
    from bar 15, where a "Male Lead Verse 2" text is printed too (one feature). Page 4 (bars 19-24):
    the male sings, the female alone sings bar 21 only (a one-bar fill, no handover), the male again."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Handover Tune", fontname="helv", fontsize=24)
    _handover_system(p1, music_font, 1, [(270, 120, "B", 12)])
    _sing(p1, 150, 0, (F, BCK_F, BCK_M))
    _sing(p1, 150, 1, (F, BCK_F, BCK_M))
    _sing(p1, 150, 2, (M,))
    _sing(p1, 150, 3, (M,))
    _sing(p1, 150, 4, (F,))
    _sing(p1, 150, 5, (F,))
    p2 = doc.new_page(width=612, height=792)
    _handover_system(p2, music_font, 7)
    for bar in range(5):
        _sing(p2, 150, bar, (F, M, BCK_F, BCK_M))
    _sing(p2, 150, 5, (F, M))
    p3 = doc.new_page(width=612, height=792)
    _handover_system(p3, music_font, 13, [(290, ys_at(150, M) - 10, "Male Lead Verse 2", 9)])
    _sing(p3, 150, 0, (F,))
    _sing(p3, 150, 1, (F,))
    _sing(p3, 150, 2, (M,))
    _sing(p3, 150, 3, (M,))
    p4 = doc.new_page(width=612, height=792)
    _handover_system(p4, music_font, 19)
    for bar, staff in ((0, M), (1, M), (2, F), (3, M), (4, M)):
        _sing(p4, 150, bar, (staff,))
    doc.save(out)


def vocal_lead_order(music_font: Path, out: Path) -> None:
    """Leads in the order they sit along the bars, wording and handovers together.
    Page 1: a "solo" over Voice Lead F in bar 5. Page 2 (bars 7-12): the male alone sings bars 7-8
    (no wording), the F "solo" returns in bar 11. Page 3 (bars 40-45): "Female Lead" in bar 40, the
    male alone from bar 42, the female alone from bar 44. Page 4 (bars 100-105): the female alone sings
    bars 100-101 (the lead already). Page 5 (bars 106-111): "Male Lead" in bar 106 with the male
    singing, the female alone from bar 109. Page 6 (bars 112-117): nobody sings. Page 7 (bars 200-205):
    the female alone sings bars 200-201 (still the lead). Page 8 (bars 300-305, no barline drawn at the
    left edge): the male alone sings the first two bars."""
    doc = pymupdf.open()

    def page(first_bar, texts=(), sing=(), left_edge=True, title=None):
        pg = doc.new_page(width=612, height=792)
        if title:
            pg.insert_text((200, 60), title, fontname="helv", fontsize=24)
        _handover_system(pg, music_font, first_bar, texts, left_edge)
        for bar, staves in sing:
            _sing(pg, 150, bar, staves)

    page(1, [(430, ys_at(150, F) - 12, "solo", 9)], title="Synthetic Order Tune")
    page(7, [(430, ys_at(150, F) - 12, "solo", 9)], [(0, (M,)), (1, (M,))])
    page(40, [(160, ys_at(150, F) - 12, "Female Lead", 9)], [(2, (M,)), (3, (M,)), (4, (F,)), (5, (F,))])
    page(100, sing=[(0, (F,)), (1, (F,))])
    page(106, [(160, ys_at(150, M) - 10, "Male Lead", 9)], [(0, (M,)), (1, (M,)), (3, (F,)), (4, (F,))])
    page(112)
    page(200, sing=[(0, (F,)), (1, (F,))])
    page(300, sing=[(0, (M,)), (1, (M,))], left_edge=False)
    doc.save(out)


def vocal_page_turn(music_font: Path, out: Path) -> None:
    """A lead restated mid-row after a page turn is the same lead; another voice's lead in between
    makes it a new one. Pages 1-2: a bare "solo" over Voice Lead F in bar 5, and again in bar 2 of
    page 2 (one feature over two pages). Pages 3-4 (bars 60 on): a solo over F in bar 2, over M in
    bar 5, and over F again in bar 2 of page 4 (three features). Pages 5-6: a bare "Solo" over an SATB
    choir staff in bar 5, and again in bar 2 of page 6 (no voice, so two cues, not one). Pages 7-8: a
    male lead with no section, then "Male Lead Verse 2". Pages 9-10: a solo over F, then one under a new mark."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Turn Tune", fontname="helv", fontsize=24)
    _handover_system(p1, music_font, 1, [(430, ys_at(150, F) - 12, "solo", 9)])
    p2 = doc.new_page(width=612, height=792)
    _handover_system(p2, music_font, 7, [(220, ys_at(150, F) - 12, "solo", 9)])
    p3 = doc.new_page(width=612, height=792)
    _handover_system(p3, music_font, 60, [(220, ys_at(150, F) - 12, "solo", 9), (430, ys_at(150, M) - 12, "solo", 9)])
    p4 = doc.new_page(width=612, height=792)
    _handover_system(p4, music_font, 66, [(220, ys_at(150, F) - 12, "solo", 9)])
    for number, first_bar, x in ((5, 100, 430), (6, 106, 220)):  # voiceless choir cues stay apart
        page = doc.new_page(width=612, height=792)
        labels = ["Alto Saxophone 1", "Drums", "SATB", "Piano"]
        _system(page, 150, labels, music_font, [(150, 120, str(first_bar), 7), (x, ys_at(150, 2) - 12, "Solo", 9)])
        _barlines(page, 150, len(labels), HANDOVER_BARS)
    # An unsectioned male lead, then "Male Lead Verse 2" on the next page: two features; a lead
    # restated under a new rehearsal mark (B printed before it on page 10): two features.
    for first_bar, texts in (
        (150, [(200, ys_at(150, M) - 12, "Male Lead", 9)]),
        (156, [(220, ys_at(150, M) - 12, "Male Lead Verse 2", 9)]),
        (200, [(170, 120, "A", 12), (200, ys_at(150, F) - 12, "solo", 9)]),
        (206, [(170, 120, "B", 12), (220, ys_at(150, F) - 12, "solo", 9)]),
    ):
        _handover_system(doc.new_page(width=612, height=792), music_font, first_bar, texts)
    doc.save(out)


CUE_LABELS = ["Alto Saxophone 1", "Trumpet in Bb 1-4", "Drums", "SATB", "Piano"]


def vocal_cues(music_font: Path, out: Path) -> None:
    """Vocal cues over a choir staff (no voice): a bare "Solo" that carries over a page turn
    as "Verse 1x - Solo" (one feature), a "Solo or All" many bars on (another), a "(Solo)"
    printed just under the SATB label, between its two staves, which sits far above the Piano
    staff (still a vocal cue, not a Piano solo), and an instrument solo that must stay one."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Cue Tune", fontname="helv", fontsize=24)
    _system(p1, 150, CUE_LABELS, music_font, [
        (150, 120, "1", 7),
        (200, ys_at(150, 0) - 12, "ALTO SOLO", 9),
        (300, ys_at(150, 3) - 12, "Solo", 9),
    ])
    _system(p1, 400, ["A. Sx. 1", "Drums"], music_font, [])  # a rhythm stack between the choir systems
    p2 = doc.new_page(width=612, height=792)
    _system(p2, 150, CUE_LABELS, music_font, [
        (150, 120, "9", 7),
        (200, ys_at(150, 3) - 12, "Verse 1x - Solo", 9),
    ])
    _system(p2, 400, ["A. Sx. 1", "Drums"], music_font, [])
    p3 = doc.new_page(width=612, height=792)
    _system(p3, 150, CUE_LABELS, music_font, [
        (150, 120, "40", 7),
        (300, ys_at(150, 3) - 12, "Solo or All", 9),
    ])
    p4 = doc.new_page(width=612, height=792)
    _system(p4, 150, CUE_LABELS, music_font, [
        (150, 120, "60", 7),
        (300, ys_at(150, 3) + 8, "(Solo)", 9),
    ])
    doc.save(out)


def voice_staves(music_font: Path, out: Path) -> None:
    """Voice staves: a "VOCALS" group label printed between two staves both labelled "Alto"
    (vocal parts, not the sax) on page 1, and on page 2 an "SATB" choir staff and a run of vocal
    part abbreviations ("A.", "Bar.") under the instrument staves."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Choir Tune", fontname="helv", fontsize=24)
    _system(p1, 150, ["Alto", "Alto", "Flute", "Trumpet in Bb", "Drums"], music_font, [
        (30, ys_at(150, 0) + STAFF_GAP / 2, "VOCALS", 9),
    ])
    p2 = doc.new_page(width=612, height=792)
    _system(p2, 150, ["Fl.", "Bb Tpt.", "SATB", "Dr."], music_font, [])
    _system(p2, 400, ["Fl.", "A.", "Bar."], music_font, [])
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


def bar_numbers_below(music_font: Path, out: Path) -> None:
    """Bar numbers printed under each system, below its bottom staff, one per bar,
    centred in the bar rather than on its barline (far from the staff of the
    system underneath). A row of triplet 3s sits
    inside the first system and is not a bar number."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((200, 60), "Synthetic Below Tune", fontname="helv", fontsize=24)
    for top, labels, first, texts in (
        (150, FULL, 41, [(345, ys_at(150, 2) - 12, "TBN SOLO", 9), (250, 190, "3 3 3", 7)]),
        (450, ABBR, 45, [(145, ys_at(450, 0) - 12, "ALTO SOLO", 9)]),
    ):
        _system(page, top, labels, music_font, texts)
        _barlines(page, top, len(labels), BAR_XS)
        y = ys_at(top, len(labels) - 1) + 16
        for i, x in enumerate(BAR_XS[:-1]):
            page.insert_text((x + 46, y), str(first + i), fontname="helv", fontsize=7)
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


def _repair_system(page, music_font, rows, right=130.0, glyph_x=140.0) -> None:
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
        page.draw_line((max(150, glyph_x + 10), y), (580, y))
        page.insert_text((glyph_x, y), MUSIC_GLYPHS, fontfile=str(music_font), fontname="SynMusic", fontsize=14)


def label_repair_ocr_misreads(music_font: Path, out: Path) -> None:
    """Staff labels as OCR misreads them: a capital I glued to the name for chair 1
    ("TRUMPETI", "TENOR SAXI"), a bar number beside a label ("TROMBONE 29"), and a
    later page repeating the full name with a chair the first system lacks."""
    doc = pymupdf.open()
    first = ["TENOR SAXI", "TRUMPETI", "TRUMPET 2", "TRUMPET 3", "TROMBONEI", "TROMBONE 29", "TROMBONE 3"]
    later = ["TENOR SAXI", "TRUMPETI", "TRUMPET 2", "TRUMPET 3", "TRUMPET 4", "TROMBONE 2", "TROMBONE 4"]
    for labels in (first, later):
        page = doc.new_page(width=612, height=792)
        page.insert_text((200, 60), "Synthetic Misread Tune", fontname="helv", fontsize=14)
        page.insert_text((160, 95), "1", fontname="helv", fontsize=7)
        # Clefs sit well right of the labels so OCR does not read them as label text.
        _repair_system(page, music_font, [(120 + i * 36.0, t) for i, t in enumerate(labels)], glyph_x=165.0)
    doc.save(out)


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
    "VERSE 2", and a page with no mark at all (C carries onto it)."""
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


def mark_carry(music_font: Path, out: Path) -> None:
    """Four pages, one system each. A trombone solo sits before the first mark
    (no mark), mark A is printed on page 1, page 2 has none (A carries over),
    mark B is printed on page 3, and page 4 has none (B carries over)."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Carry Tune", fontname="helv", fontsize=24)
    _system(p1, 150, FULL, music_font, [
        (150, 120, "1", 7),
        (400, 105, "A", 12),
        (450, ys_at(150, 0) - 12, "ALTO SOLO", 9),
        (200, ys_at(150, 2) - 12, "TBN SOLO", 9),
    ])
    p2 = doc.new_page(width=612, height=792)
    _system(p2, 150, ABBR, music_font, [
        (150, 120, "33", 7),
        (250, ys_at(150, 3) - 12, "GUITAR SOLO", 9),
    ])
    p3 = doc.new_page(width=612, height=792)
    _system(p3, 150, ABBR, music_font, [
        (150, 120, "65", 7), (200, 105, "B", 12),
        (300, ys_at(150, 4) - 12, "DRUM SOLO", 9),
    ])
    p4 = doc.new_page(width=612, height=792)
    _system(p4, 150, ABBR, music_font, [
        (150, 120, "97", 7),
        (250, ys_at(150, 1) - 12, "TRUMPET SOLO", 9),
    ])
    doc.save(out)


def score_order(music_font: Path, out: Path) -> None:
    """Solos on one system whose staff order is not their order along the bars:
    the guitar (lower staff) solos first, then the alto, then the trombone."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Order Tune", fontname="helv", fontsize=24)
    _system(p1, 150, FULL, music_font, [
        (150, 120, "1", 7), (250, 120, "9", 7), (350, 120, "17", 7), (450, 120, "25", 7),
        (200, ys_at(150, 3) - 12, "GUITAR SOLO", 9),
        (300, ys_at(150, 0) - 12, "ALTO SOLO", 9),
        (400, ys_at(150, 2) - 12, "TBN SOLO", 9),
    ])
    p2 = doc.new_page(width=612, height=792)
    _system(p2, 150, ABBR, music_font, [
        (150, 120, "33", 7),
        (400, ys_at(150, 1) - 12, "TRUMPET SOLO", 9),
    ])
    doc.save(out)


def unnumbered_order(music_font: Path, out: Path) -> None:
    """No bar numbers anywhere: solos order by system, then x. The alto solo on
    the first system has a reminder at a smaller x on the second, which also
    holds a trumpet solo further left than the alto's first appearance."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Unnumbered Tune", fontname="helv", fontsize=24)
    _system(p1, 150, FULL, music_font, [
        (400, ys_at(150, 0) - 12, "ALTO SOLO", 9),
        (250, ys_at(150, 3) - 12, "GUITAR SOLO", 9),
    ])
    _system(p1, 400, ABBR, music_font, [
        (200, ys_at(400, 1) - 12, "TRUMPET SOLO", 9),
        (160, ys_at(400, 0) - 12, "ALTO SOLO", 9),
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


def folded_solos(music_font: Path, out: Path) -> None:
    """Copies of one marking across the staves of one system. Page 1: a generic
    "Instrumental Solo" over five of six staves (an open solo, no instrument);
    a bare "SOLO" over a Piano staff and two staves of unusable labels (one
    Piano solo). Page 2: "GUITAR SOLO" over every staff (a Guitar solo)."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Folded Tune", fontname="helv", fontsize=24)
    full = FULL + ["Piano"]
    _system(p1, 150, full, music_font, [
        (150, 120, "1", 7), (300, 120, "9", 7),
        *[(300, ys_at(150, i) - 12, "Instrumental Solo", 9) for i in range(5)],
    ])
    _system(p1, 400, ["Gtr.", "Pno.", "Vocal cue", "Vocal cue"], music_font, [
        (150, 370, "17", 7),
        *[(300, ys_at(400, i) - 12, "SOLO", 9) for i in (1, 2, 3)],
    ])
    p2 = doc.new_page(width=612, height=792)
    p2.insert_text((200, 60), "Synthetic Folded Tune", fontname="helv", fontsize=24)
    _system(p2, 150, ["Gtr.", "Pno.", "Dr.", "A. Sx. 1"], music_font, [
        (150, 120, "25", 7),
        *[(300, ys_at(150, i) - 12, "GUITAR SOLO", 9) for i in range(4)],
    ])
    doc.save(out)


PART_STAFF_TOP = 150
PART_BARLINES = (60, 220, 320, 400, 480, 560)  # five bars per system


def _part_system(page, top: float, glyph_font: Path, texts, barlines=PART_BARLINES) -> None:
    """One staff of a part: five lines, barlines, a clef-and-key glyph run
    ("&bb") in a font the music-font list does not know, and texts."""
    for i in range(5):
        page.draw_line((60, top + 6 * i), (560, top + 6 * i))
    for x in barlines:
        page.draw_line((x, top), (x, top + 24))
    page.insert_text((62, top + 20), "&bb", fontfile=str(glyph_font), fontname="SynGlyphs", fontsize=14)
    for x, y, text, size in texts:
        page.insert_text((x, y), text, fontname="helv", fontsize=size)


def one_staff_part(glyph_font: Path, out: Path) -> None:
    """A one-instrument part, no label column: a title with the word Solo in it
    and an instrument heading above the first staff, then three staves. The
    first holds a four-bar rest (a staff-sized "4"), mark A beside the words
    "VERSE 1" and a solo in its third interval (bar 6); the second prints
    bar number 9 at its start and mark B; the staff on page 2 prints 14, carries
    mark B and holds a solo in its third interval (bar 16)."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((200, 60), "Synthetic Solo Tune", fontname="helv", fontsize=24)
    p1.insert_text((50, 95), "Trumpet 1", fontname="helv", fontsize=14)
    top = PART_STAFF_TOP
    _part_system(p1, top, glyph_font, [
        (100, top + 14, "44", 40),  # a time signature set staff-sized: not a rest
        (165, top + 14, "4", 40),  # a four-bar rest
        (200, top - 18, "A", 12), (230, top - 18, "VERSE 1", 10),
        (340, top - 8, "SOLO", 9),
    ])
    _part_system(p1, top + 150, glyph_font, [
        (50, top + 139, "9", 7),
        (200, top + 132, "B", 12), (230, top + 132, "VERSE 2", 10),
        (400, top + 160, "3", 9),  # a text-sized digit inside the staff span: a tuplet, not a rest
    ])
    p2 = doc.new_page(width=612, height=792)
    _part_system(p2, top, glyph_font, [
        (50, top - 11, "14", 7),
        (340, top - 8, "SOLO", 9),
    ])
    doc.save(out)


def overprinted_labels_part(glyph_font: Path, out: Path, rests: tuple[int, int, int] = (7, 8, 8)) -> None:
    """A part that prints each staff's first bar under the staff, and the next
    staff's number above it, one on top of the other (as 33 and 56 below).
    Four staves 63 pt apart: the first starts at bar 33 and holds three multi-bar
    rests (`rests`, set above the staff, with mid-staff numbers 40 and 48); the
    second starts at 56 (numbers 33 and 56 overprinted) with a "SOLO" in its
    first bar; the third starts at 60 and the fourth at 64 (60 and 64
    overprinted), with a "SOLO" in its second bar (bar 65). Each staff has four
    bars after the first, so 56 + 4 = 60 and 60 + 4 = 64 confirm the numbers."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((200, 60), "Synthetic Overprint Tune", fontname="helv", fontsize=24)
    tops = [150 + 87 * i for i in range(4)]
    four_bars = (60, 200, 340, 480, 560)
    rest_x = (150, 290, 450)
    _part_system(page, tops[0], glyph_font, [
        *((x, tops[0] - 8, str(n), 24) for x, n in zip(rest_x, rests)),
        (225, tops[0] - 14, "40", 15), (385, tops[0] - 14, "48", 15),
    ], barlines=(60, 220, 380, 540))
    _part_system(page, tops[1], glyph_font, [
        (90, tops[1] - 6, "SOLO", 9), (130, tops[1] - 12, "Dmin7", 12), (230, tops[1] - 12, "G7", 12),
    ], barlines=four_bars)
    _part_system(page, tops[2], glyph_font, [(130, tops[2] - 12, "F6", 12)], barlines=four_bars)
    _part_system(page, tops[3], glyph_font, [(300, tops[3] - 6, "SOLO", 9)], barlines=four_bars)
    for top, below, above in zip(tops, (33, 56, 60, 64), (None, 56, None, 64)):
        page.insert_text((50, top + 24 + 19), str(below), fontname="helv", fontsize=12)  # under the staff
        if above:
            page.insert_text((47, top - 44), str(above), fontname="helv", fontsize=15)
    doc.save(out)


def one_line_part(out: Path) -> None:
    """A percussion part: one-line staves with short barlines, and a long rule
    under the title that is no staff. Mark A on the first staff; the second
    prints bar number 6 at its start and holds a solo in its second bar (bar 7)."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((200, 60), "Synthetic Bells Tune", fontname="helv", fontsize=24)
    page.draw_line((50, 80), (560, 80))  # a rule under the title
    for y, texts in ((200, [(200, 178, "A", 12)]), (350, [(50, 339, "6", 7), (180, 338, "SOLO", 9)])):
        page.draw_line((60, y), (560, y))
        for x in (60, 160, 260, 360, 460, 560):
            page.draw_line((x, y - 5), (x, y + 5))
        for x, ty, text, size in texts:
            page.insert_text((x, ty), text, fontname="helv", fontsize=size)
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
        chord_text_solos(font, OUT / "finale_chord_text_solos.pdf")
        right_aligned(font, OUT / "finale_right_aligned.pdf")
        repeated_solos(font, OUT / "finale_repeated_solos.pdf")
        label_repair_missing(font, OUT / "label_repair_missing.pdf")
        label_repair_noise(font, OUT / "label_repair_noise.pdf")
        label_repair_ocr_misreads(font, OUT / "label_repair_ocr_misreads.pdf")
        label_repair_unlabeled(font, OUT / "label_repair_unlabeled.pdf")
        label_repair_overprint(font, OUT / "label_repair_overprint.pdf")
        rehearsal_marks(font, OUT / "rehearsal_marks.pdf")
        mark_carry(font, OUT / "finale_mark_carry.pdf")
        score_order(font, OUT / "finale_score_order.pdf")
        unnumbered_order(font, OUT / "finale_unnumbered_order.pdf")
        chair_solos(font, OUT / "finale_chair_solos.pdf")
        non_bar_numbers(font, OUT / "finale_non_bar_numbers.pdf")
        sparse_bar_numbers(font, OUT / "finale_sparse_bar_numbers.pdf")
        bar_numbers_below(font, OUT / "finale_bar_numbers_below.pdf")
        vocal_leads(font, OUT / "finale_vocal_leads.pdf")
        voice_staves(font, OUT / "finale_voice_staves.pdf")
        vocal_cues(font, OUT / "finale_vocal_cues.pdf")
        vocal_handover(font, OUT / "finale_vocal_handover.pdf")
        vocal_lead_order(font, OUT / "finale_vocal_lead_order.pdf")
        vocal_page_turn(font, OUT / "finale_vocal_page_turn.pdf")
        distinct_solos(font, OUT / "finale_distinct_solos.pdf")
        shared_solos(font, OUT / "finale_shared_solos.pdf")
        absent_instrument_solo(font, OUT / "finale_absent_instrument_solo.pdf")
        folded_solos(font, OUT / "finale_folded_solos.pdf")
        glyphs = Path(tmp) / "SynGlyphs.ttf"
        build_music_font(glyphs, family="SynGlyphs", chars="&b")
        one_staff_part(glyphs, OUT / "part_one_staff.pdf")
        one_line_part(OUT / "part_one_line.pdf")
        overprinted_labels_part(glyphs, OUT / "part_overprinted_labels.pdf")
        overprinted_labels_part(glyphs, OUT / "part_overprinted_unconfirmed.pdf", rests=(7, 8, 7))
    for dpi in (300, 90):
        scanned(OUT / "finale_full_labels.pdf", OUT / f"scan_{dpi}dpi.pdf", dpi)
    scanned(OUT / "label_repair_ocr_misreads.pdf", OUT / "scan_label_misreads.pdf", 300)
    pattern_scanned(OUT / "finale_full_labels.pdf", OUT / "scan_pattern.pdf")
    for rotation in (90, 270):
        rotated_scan(OUT / "finale_full_labels.pdf", OUT / f"scan_rotated_{rotation}.pdf", rotation)


if __name__ == "__main__":
    main()
