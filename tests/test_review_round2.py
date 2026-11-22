"""Behaviour fixed after the second code review. Scores are drawn at test time
from invented text (never committed)."""

import shutil
import sys
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest

from score_parser import ParseOptions, parse_score
from score_parser.clean import clean
from score_parser.models import Page, Token

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"
NUMBERS = FIXTURES / "numbers"
FULL = ["Alto Saxophone 1", "Trombone 1-4", "Drums"]


def make_score(path, systems, texts=()):
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    for top, labels in systems:
        for i, label in enumerate(labels):
            page.insert_text((30, top + i * 30), label, fontname="helv", fontsize=9)
            page.draw_line((140, top + i * 30), (580, top + i * 30))
    for x, y, text in texts:
        page.insert_text((x, y), text, fontname="helv", fontsize=9)
    doc.save(path)
    return path


def ocr_page(*words):
    toks = [Token(w, 10 + 40 * i, 10, 40 + 40 * i, 20, 1, "", "ocr", 0.9) for i, w in enumerate(words)]
    return Page(1, 612, 792, toks, "ocr")


@pytest.mark.parametrize("word", ["&", "-", "+", ".", "|", "?", ">", "’", "ã", "Ó", "œ"])
def test_ocr_tokens_are_never_dropped_as_music_glyphs(word):
    assert [t.text for t in clean(ocr_page("Alto", word, "Sax")).tokens] == ["Alto", word, "Sax"]


def test_ordinals_are_not_split_into_number_and_suffix():
    out = clean(ocr_page("1ST", "2ND", "3RD", "4TH", "29ALTO"))
    assert [t.text for t in out.tokens] == ["1ST", "2ND", "3RD", "4TH", "29", "ALTO"]


def test_text_page_with_few_words_keeps_its_text_layer(tmp_path):
    pdf = make_score(tmp_path / "few.pdf", [(150, ["Drums"])])
    report = parse_score(pdf)
    assert report.pages[0].source == "text"
    assert not any("no text" in w for w in report.warnings)


def test_missing_ocr_is_a_warning_not_a_crash(tmp_path, monkeypatch):
    doc = pymupdf.open()
    doc.new_page(width=612, height=792)
    doc.save(tmp_path / "blank.pdf")
    monkeypatch.setitem(sys.modules, "Vision", None)
    report = parse_score(tmp_path / "blank.pdf")
    assert any("page 1" in w and "no text" in w for w in report.warnings)


def match(tmp_path, name):
    path = tmp_path / name
    shutil.copy(FIXTURES / "finale_solos.pdf", path)
    return parse_score(path, ParseOptions(numbers_dir=NUMBERS)).matched_slug


def test_short_title_does_not_partial_match_a_longer_one(tmp_path):
    assert match(tmp_path, "Jingle.pdf") is None
    assert match(tmp_path, "Bells.pdf") is None


@pytest.mark.parametrize(
    "filename, title",
    [
        ("The Final Countdown.pdf", "The Final Countdown"),
        ("Full Moon.pdf", "Full Moon"),
        ("Copy Cat score.pdf", "Copy Cat"),
        ("Moon River - Full Score.pdf", "Moon River"),
        ("Moon River (Final).pdf", "Moon River"),
        ("Final Moon River.pdf", "Final Moon River"),
    ],
)
def test_noise_words_inside_a_title_are_kept(tmp_path, filename, title):
    path = tmp_path / filename
    shutil.copy(FIXTURES / "finale_solos.pdf", path)
    assert parse_score(path).title == title


VOCAL = FULL + ["Voice Lead F"]


def vocal_features(tmp_path, texts):
    pdf = make_score(
        tmp_path / "v.pdf",
        [(150, VOCAL), (400, VOCAL)],
        [(150, 120, "1"), (150, 370, "5"), *texts],
    )
    return [f for f in parse_score(pdf).features if f.kind == "vocal lead"]


def test_vocal_leads_with_different_sections_stay_separate(tmp_path):
    feats = vocal_features(tmp_path, [
        (300, 222, "Female Lead Verse 1"), (300, 228, "solo"),
        (300, 472, "Female Lead Verse 2"), (300, 478, "solo"),
    ])
    assert [f.section for f in feats] == ["Verse 1", "Verse 2"]


def test_cross_page_reminder_does_not_relocate_the_feature(tmp_path):
    doc = pymupdf.open()
    for number in range(2):
        pg = doc.new_page(width=612, height=792)
        for i, label in enumerate(FULL):
            pg.insert_text((30, 150 + i * 30), label, fontname="helv", fontsize=9)
            pg.draw_line((140, 150 + i * 30), (580, 150 + i * 30))
        pg.insert_text((300, 138), "ALTO SOLO", fontname="helv", fontsize=9)
        if number == 1:
            pg.insert_text((150, 120), "9", fontname="helv", fontsize=7)
    doc.save(tmp_path / "r.pdf")
    (feature,) = parse_score(tmp_path / "r.pdf").features
    assert len(feature.locations) == 2
    assert feature.page == feature.locations[0].page == 1
