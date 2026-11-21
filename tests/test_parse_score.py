from pathlib import Path

from score_parser import parse_score

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"


def by_name(report):
    return {i.instrument: i for i in report.instrumentation}


def test_full_labels_resolve_to_canonical_instruments():
    report = parse_score(FIXTURES / "finale_full_labels.pdf")

    found = by_name(report)
    assert set(found) == {
        "Alto Sax",
        "Tenor Sax",
        "Trumpet",
        "Trombone",
        "Piano",
        "Bass",
        "Drums",
    }
    assert found["Alto Sax"].chairs == [1]
    assert found["Trumpet"].chairs == [1, 2, 3, 4]
    assert found["Trombone"].chairs == [1, 2, 3, 4]


def test_unknown_labels_are_reported_not_guessed():
    report = parse_score(FIXTURES / "finale_full_labels.pdf")

    assert report.unknown_labels == ["Zorblax Section"]
    assert "Zorblax Section" not in {l for i in report.instrumentation for l in i.labels}


def test_music_glyphs_never_become_labels_and_page_source_is_text():
    report = parse_score(FIXTURES / "finale_full_labels.pdf")

    labels = report.unknown_labels + [l for i in report.instrumentation for l in i.labels]
    assert labels and all(ord(c) < 0xE000 for l in labels for c in l)
    assert [(p.page, p.source) for p in report.pages] == [(1, "text")]


def all_labels(report):
    return report.unknown_labels + [l for i in report.instrumentation for l in i.labels]


def test_sibelius_opus_glyphs_are_dropped_by_font_name():
    report = parse_score(FIXTURES / "sibelius_abbreviated.pdf")

    labels = all_labels(report)
    assert labels
    assert not any("?" in l or l.rstrip().endswith("&") for l in labels)
    assert "Trombone 1-4" in labels


def test_chair_ranges_expand_including_roman_numerals():
    found = by_name(parse_score(FIXTURES / "sibelius_abbreviated.pdf"))

    assert found["Alto Sax"].chairs == [1, 2]
    assert found["Trumpet"].chairs == [1, 2, 3, 4]
    assert found["Flute"].chairs == [1, 2, 3]
    assert found["Guitar"].chairs == [1, 2]


def test_non_standard_instruments_are_recognised():
    report = parse_score(FIXTURES / "sibelius_nonstandard.pdf")

    assert set(by_name(report)) == {
        "Violin",
        "Viola",
        "Cello",
        "Organ",
        "Lead Vocal",
        "Flugelhorn",
    }
    assert report.unknown_labels == []


def test_doublings_come_from_labels_and_instruction_text_not_mutes():
    found = by_name(parse_score(FIXTURES / "sibelius_abbreviated.pdf"))

    assert found["Flute"].doublings == ["Oboe"]
    assert found["Alto Sax"].doublings == ["Flute"]
    assert found["Trumpet"].doublings == ["Piccolo Trumpet"]
    assert found["Trombone"].doublings == []


def test_abbreviated_labels_on_later_systems_agree_with_first_system():
    report = parse_score(FIXTURES / "sibelius_abbreviated.pdf")

    found = by_name(report)
    assert set(found) == {
        "Flute", "Alto Sax", "Trumpet", "Trombone", "Guitar", "Electric Bass", "Drums",
    }
    assert "E.B." in found["Electric Bass"].labels
    assert "D. S." in found["Drums"].labels
    assert report.warnings == []
    assert report.unknown_labels == []


def test_later_systems_that_disagree_with_first_system_raise_warnings():
    report = parse_score(FIXTURES / "sibelius_mismatch.pdf")

    text = "\n".join(report.warnings)
    assert "Tbn. 1-5" in text
    assert "Vln." in text
    assert "Zork." in text
    assert "Zork." in report.unknown_labels
    assert "Violin" not in by_name(report)
