"""Fixes from the review of tickets #29-#37. Scores are drawn at test time from
invented text and parsed through parse_score."""

import pymupdf
import pytest

from score_parser import parse_score

SIX = ["Alto Saxophone", "Tenor Saxophone", "Trumpet", "Trombone", "Piano", "Drums"]
TOP = 150


def make_score(path, systems, texts=(), barlines=(), under=()):
    """systems: (top, labels); texts: (x, y, text); barlines: x positions drawn
    through every system; under: (x, dy below the bottom staff, text)."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    for top, labels in systems:
        for i, label in enumerate(labels):
            page.insert_text((30, top + i * 30), label, fontname="helv", fontsize=9)
            page.draw_line((140, top + i * 30), (580, top + i * 30))
        for x in barlines:
            page.draw_line((x, top - 8), (x, top + (len(labels) - 1) * 30 + 4))
        for x, dy, text in under:
            page.insert_text((x, top + (len(labels) - 1) * 30 + dy), text, fontname="helv", fontsize=8)
    for x, y, text in texts:
        page.insert_text((x, y), text, fontname="helv", fontsize=9)
    doc.save(path)
    return path


def over(slot, x, text, top=TOP):
    return (x, top + slot * 30 - 12, text)


def summary(report):
    return sorted((f.kind, f.instrument, f.page) for f in report.features)


def test_solos_at_different_places_over_four_staves_stay_four_features(tmp_path):
    texts = [over(i, 160 + 100 * i, "Solo") for i in range(4)]
    report = parse_score(make_score(tmp_path / "a.pdf", [(TOP, SIX)], texts))

    assert sorted(f.instrument for f in report.features) == ["Alto Sax", "Tenor Sax", "Trombone", "Trumpet"]


def test_bare_solo_at_one_place_over_four_of_six_staves_is_shared_not_open(tmp_path):
    texts = [over(i, 300, "SOLO") for i in range(4)]
    report = parse_score(make_score(tmp_path / "a.pdf", [(TOP, SIX)], texts))

    [feature] = report.features
    assert feature.instrument == "Alto Sax"
    assert [p.instrument for p in feature.shared_with] == ["Tenor Sax", "Trumpet", "Trombone"]


def test_bare_solo_over_every_staff_is_an_open_solo(tmp_path):
    texts = [over(i, 300, "SOLO") for i in range(6)]
    report = parse_score(make_score(tmp_path / "a.pdf", [(TOP, SIX)], texts))

    [feature] = report.features
    assert (feature.instrument, feature.shared_with) == (None, [])


def test_generic_wording_over_four_of_six_staves_is_still_open(tmp_path):
    texts = [over(i, 300, "(SOLOS)") for i in range(4)]
    report = parse_score(make_score(tmp_path / "a.pdf", [(TOP, SIX)], texts))

    [feature] = report.features
    assert feature.instrument is None


def test_text_named_absent_instrument_over_every_staff_is_never_made_open(tmp_path):
    texts = [over(i, 300, "VIOLIN SOLO") for i in range(6)]
    report = parse_score(make_score(tmp_path / "a.pdf", [(TOP, SIX)], texts))

    [feature] = report.features
    assert feature.instrument == "Violin"
    assert any("possible feature" in r for r in feature.reasons)


def test_separate_solo_beside_an_open_solo_survives_whether_or_not_bars_are_known(tmp_path):
    systems = [(TOP, SIX + ["Bass"])]
    texts = [over(i, 300, "(SOLOS)") for i in range(5)] + [over(5, 500, "Solo")]
    report = parse_score(make_score(tmp_path / "a.pdf", systems, texts))

    assert sorted(f.instrument or "open" for f in report.features) == ["Drums", "open"]


def test_two_text_leads_on_far_apart_systems_without_voice_staves_are_two_features(tmp_path):
    systems = [(100, ["Alto Saxophone", "Piano"])] + [(top, ["A. Sx.", "Pno."]) for top in (300, 500, 700)]
    texts = [(160, 100 - 12, "Female Lead"), (160, 700 - 12, "Female Lead")]
    report = parse_score(make_score(tmp_path / "a.pdf", systems, texts))

    assert [f.kind for f in report.features] == ["vocal lead", "vocal lead"]


@pytest.mark.parametrize("wording, voice_label", [("Tenor Solo", "SATB"), ("Bass Solo", "SATB")])
def test_voice_part_solo_over_a_choir_staff_is_a_vocal_lead_not_a_sax_or_bass(tmp_path, wording, voice_label):
    labels = ["Alto Saxophone", "Tenor Saxophone", voice_label, "Piano", "Bass"]
    report = parse_score(make_score(tmp_path / "a.pdf", [(TOP, labels)], [over(2, 300, wording)]))

    [feature] = report.features
    assert (feature.kind, feature.instrument) == ("vocal lead", None)


def test_instrument_named_solo_over_a_choir_staff_keeps_its_instrument(tmp_path):
    labels = ["Alto Saxophone", "Tenor Saxophone", "SATB", "Piano"]
    report = parse_score(make_score(tmp_path / "a.pdf", [(TOP, labels)], [over(2, 300, "Tenor Sax Solo")]))

    assert [(f.kind, f.instrument) for f in report.features] == [("solo", "Tenor Sax")]


def test_feature_wording_over_a_choir_staff_is_not_a_vocal_lead(tmp_path):
    labels = ["Alto Saxophone", "SATB", "Piano"]
    report = parse_score(make_score(tmp_path / "a.pdf", [(TOP, labels)], [over(1, 300, "Feature")]))

    assert [f.kind for f in report.features] == ["feature"]


def test_several_chords_before_a_bare_solo_are_dropped_with_a_warning(tmp_path):
    labels = ["Alto Saxophone", "Guitar"]
    report = parse_score(make_score(tmp_path / "a.pdf", [(TOP, labels)], [over(1, 300, "Cmaj7 Dm7 Solo")]))

    assert report.features == []
    assert any("Page 1" in w and "chord" in w for w in report.warnings)


def test_chord_only_penalty_survives_an_open_solo(tmp_path):
    texts = [over(i, 300, "G7 SOLO") for i in range(6)]
    report = parse_score(make_score(tmp_path / "a.pdf", [(TOP, SIX)], texts))

    [feature] = report.features
    assert feature.confidence < 0.5


UNDER_LABELS = ["Alto Saxophone", "Trumpet", "Piano", "Drums"]


def two_systems(tmp_path, under):
    texts = [over(0, 300, "ALTO SOLO", 150), over(0, 300, "TPT SOLO", 450)]
    systems = [(150, UNDER_LABELS), (450, UNDER_LABELS)]
    path = make_score(tmp_path / "a.pdf", systems, texts, barlines=(150, 280, 410, 540), under=under)
    return [(f.instrument, f.bar) for f in parse_score(path).features]


def test_tuplet_threes_under_the_bottom_staff_are_not_bar_numbers(tmp_path):
    assert two_systems(tmp_path, [(200, 12, "3"), (330, 12, "3"), (460, 12, "3")]) == [
        ("Alto Sax", 2),
        ("Trumpet", 5),
    ]


def test_lone_time_signature_digit_under_the_bottom_staff_is_not_a_bar_number(tmp_path):
    assert two_systems(tmp_path, [(155, 5, "4")]) == [("Alto Sax", 2), ("Trumpet", 5)]


def test_rising_numbers_under_the_bottom_staff_are_still_bar_numbers(tmp_path):
    found = two_systems(tmp_path, [(150, 12, "1"), (280, 12, "2"), (410, 12, "3"), (540, 12, "4")])
    assert found[0] == ("Alto Sax", 2)


def labels_report(tmp_path, labels, later=None):
    systems = [(150, labels)] + ([(450, later)] if later else [])
    return parse_score(make_score(tmp_path / "a.pdf", systems))


def test_unknown_label_on_pages_one_to_three_counts_all_three_pages(tmp_path):
    doc = pymupdf.open()
    for _ in range(3):
        page = doc.new_page(width=612, height=792)
        for i, label in enumerate(["Alto Saxophone", "Kazoo"]):
            page.insert_text((30, 150 + i * 30), label, fontname="helv", fontsize=9)
            page.draw_line((140, 150 + i * 30), (580, 150 + i * 30))
    doc.save(tmp_path / "k.pdf")
    report = parse_score(tmp_path / "k.pdf")

    assert any("'Kazoo'" in w and "on 3 pages" in w for w in report.warnings)


@pytest.mark.parametrize("label, chair", [("Gtr.l", [1]), ("Gtr.1", [1]), ("Drums1", [1]), ("Pianol", [1])])
def test_glued_chair_is_read_off_a_name_or_an_abbreviation(tmp_path, label, chair):
    report = labels_report(tmp_path, ["Alto Saxophone", label])

    [entry] = [e for e in report.instrumentation if e.instrument != "Alto Sax"]
    assert entry.chairs == chair


def test_acoustic_bass_label_is_never_a_choir_label_even_when_ocr_drops_its_dots():
    from score_parser.vocal import is_choir_label

    assert not is_choir_label("A.B.")
    assert not is_choir_label("AB")
    assert is_choir_label("SATB")
