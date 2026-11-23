"""Part-filename spellings (#57): run-together words, abbreviations and chairs
resolve to canonical instruments through parse_score; "Rhythm" never guesses;
choir labels stay unrecognised; a parody title matches its planner slug."""

import shutil
from pathlib import Path

import pymupdf
import pytest

from score_parser import ParseOptions, parse_score
from score_parser.instruments import resolve

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"
NUMBERS = FIXTURES / "numbers"  # synthetic stand-ins for planner number files
FILLER = ["Piano", "Bass", "Drums"]


def make_score(path, label):
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    for i, text in enumerate([label, *FILLER]):
        y = 150 + i * 30
        page.insert_text((30, y), text, fontname="helv", fontsize=9)
        page.draw_line((140, y), (580, y))
    doc.save(path)
    return path


def read(tmp_path, label):
    report = parse_score(make_score(tmp_path / "s.pdf", label))
    return {e.instrument: e.chairs for e in report.instrumentation}, report


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("BariSax", {"Baritone Sax": [1]}),
        ("Keyboard", {"Keyboard": [1]}),
        ("KEYS", {"Keyboard": [1]}),
        ("KeyboardSynth", {"Keyboard": [1], "Synthesizer": [1]}),
        ("KeyboardOrgan", {"Keyboard": [1], "Organ": [1]}),
        ("Keyboard/Synth", {"Keyboard": [1], "Synthesizer": [1]}),
        ("AltoSaxes1-2", {"Alto Sax": [1, 2]}),
        ("AltoSax1/2", {"Alto Sax": [1, 2]}),
        ("TenSaxes1-2", {"Tenor Sax": [1, 2]}),
        ("TenSax 1", {"Tenor Sax": [1]}),
        ("AcoustGuitar", {"Guitar": [1]}),
        ("ElecGuitar", {"Guitar": [1]}),
        ("Flts1,2", {"Flute": [1, 2]}),
        ("Piccolo Trpt", {"Piccolo Trumpet": [1]}),
        ("Cello:Bass", {"Cello-Bass": [1]}),
    ],
)
def test_part_filename_spelling_resolves(tmp_path, label, expected):
    found, report = read(tmp_path, label)

    assert expected.items() <= found.items()
    assert report.unknown_labels == []


@pytest.mark.parametrize(
    ("label", "instrument", "chairs"),
    [
        ("FlugelHorn 1/2", "Flugelhorn", [1, 2]),  # a staff label "1/2" reads as a time signature, so look up directly
        ("Alto Sax 1/2", "Alto Sax", [1, 2]),
        ("Rhythm", "Rhythm", [1]),
    ],
)
def test_lookup_reads_slash_chairs_and_rhythm(label, instrument, chairs):
    hit = resolve(label)

    assert (hit.name, hit.chairs) == (instrument, chairs)


def test_rhythm_is_a_rhythm_part_with_no_instrument_guessed(tmp_path):
    found, report = read(tmp_path, "RHYTHMN")

    assert found.keys() == {"Rhythm", "Piano", "Bass", "Drums"}  # nothing added beside the fillers
    assert any(w.startswith("Rhythm:") and "review" in w for w in report.warnings)
    assert report.unknown_labels == []


@pytest.mark.parametrize("label", ["SATB", "Choir", "Soprano"])
def test_choir_and_voice_labels_stay_out_of_the_instrument_table(tmp_path, label):
    found, _ = read(tmp_path, label)

    assert found.keys() == set(FILLER)


@pytest.mark.parametrize(
    "filename",
    [
        "MERRY SUPER CHRISTMAS- lyrics only .pdf",
        "Merry Super Christmas.pdf",
        "Super Christmas.pdf",
    ],
)
def test_super_christmas_titles_match_the_superstition_slug(tmp_path, filename):
    path = tmp_path / filename
    shutil.copy(FIXTURES / "finale_solos.pdf", path)

    report = parse_score(path, ParseOptions(numbers_dir=NUMBERS))

    assert report.matched_slug == "superstition"
