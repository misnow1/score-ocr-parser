"""Voice staves are not instruments, through parse_score on a synthetic fixture."""

from pathlib import Path

from score_parser import parse_score

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"


def test_alto_under_a_vocals_group_is_not_alto_sax():
    report = parse_score(FIXTURES / "finale_voice_staves.pdf")

    names = [e.instrument for e in report.instrumentation]
    assert names == ["Flute", "Trumpet", "Drums"]  # no Alto Sax, and the group label is no Lead Vocal


def test_choir_and_vocal_part_labels_are_not_unknown_labels():
    report = parse_score(FIXTURES / "finale_voice_staves.pdf")

    assert report.unknown_labels == []
    assert not any(w for w in report.warnings if "SATB" in w or "'A.'" in w or "'Bar.'" in w)


def test_voice_staves_stay_out_of_the_instrument_table():
    report = parse_score(FIXTURES / "finale_voice_staves.pdf")

    labels = [lb for e in report.instrumentation for lb in e.labels]
    assert not {"SATB", "A.", "Bar.", "VOCALS", "Alto"} & set(labels)
