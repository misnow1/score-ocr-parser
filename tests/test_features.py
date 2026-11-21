from pathlib import Path

from score_parser import parse_score

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"


def feature_at(report, text):
    return next(f for f in report.features if text.lower() in f.raw_text.lower())


def test_every_solo_and_feature_is_found_with_location():
    report = parse_score(FIXTURES / "finale_solos.pdf")

    got = {(f.kind, f.instrument, f.page, f.bar, f.rehearsal_mark) for f in report.features}
    assert got == {
        ("solo", "Trombone", 1, 9, "VERSE"),
        ("solo", "Alto Sax", 1, 29, "B"),
        ("solo", "Guitar", 1, 17, "B"),
        ("solo", "Drums", 2, 33, "C"),
        ("feature", "Drums", 2, 33, "C"),
        ("solo", "Vocal", 2, 33, "C"),
    }


def test_glued_bar_number_is_split_from_solo_text():
    report = parse_score(FIXTURES / "finale_solos.pdf")

    alto = feature_at(report, "alto solo")
    assert (alto.instrument, alto.bar) == ("Alto Sax", 29)
    assert not any("29ALTO" in f.raw_text for f in report.features)


def test_instrument_from_staff_scores_lower_than_named_instrument():
    report = parse_score(FIXTURES / "finale_solos.pdf")

    named = feature_at(report, "TBN SOLO")
    from_staff = feature_at(report, "1x - Solo")
    assert from_staff.instrument == "Drums"
    assert from_staff.confidence < named.confidence
    assert named.reasons and from_staff.reasons
    assert 0 <= from_staff.confidence <= named.confidence <= 1


def test_non_solo_text_is_not_reported():
    report = parse_score(FIXTURES / "finale_solos.pdf")

    assert not any("swing" in f.raw_text.lower() for f in report.features)
