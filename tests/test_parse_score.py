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
