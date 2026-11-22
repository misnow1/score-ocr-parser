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


def test_repeated_solo_merges_into_one_feature_with_its_locations():
    report = parse_score(FIXTURES / "finale_repeated_solos.pdf")

    got = [(f.kind, f.instrument, f.page, f.bar) for f in report.features]
    assert sorted(got, key=str) == sorted(
        [
            ("solo", "Alto Sax", 1, 9),  # five copies on one system, a reminder on the next
            ("solo", "Trombone", 1, 1),
            ("solo", "Trombone", 2, 33),  # top staff in its own stack, copies below it
            ("solo", "Alto Sax", 3, 49),  # a system without the solo in between: new feature
            ("solo", "Guitar", 3, 49),  # bare SOLO; the page number is not a bar
        ],
        key=str,
    )
    alto = next(f for f in report.features if f.instrument == "Alto Sax" and f.page == 1)
    assert [(loc.page, loc.bar) for loc in alto.locations] == [(1, 9), (1, 17)]


def test_chord_symbols_are_stripped_from_phrases():
    report = parse_score(FIXTURES / "finale_repeated_solos.pdf")

    assert not any("G7" in f.raw_text for f in report.features)
    assert feature_at(report, "TBN SOLO").raw_text == "TBN SOLO"


def test_numbers_that_are_not_bars_are_not_taken_as_bars():
    report = parse_score(FIXTURES / "finale_non_bar_numbers.pdf")

    got = {(f.instrument, f.page, f.bar) for f in report.features}
    # time signature "44" (p1), header "10 Score" (p2), triplet 3s (p3)
    assert got == {("Alto Sax", 1, 1), ("Trombone", 2, 33), ("Guitar", 3, 49)}


def test_solos_are_placed_by_counting_barlines_from_the_nearest_printed_number():
    report = parse_score(FIXTURES / "finale_sparse_bar_numbers.pdf")

    got = {(f.instrument, f.page, f.bar) for f in report.features}
    # bar "5" is printed once on page 1; page 2 prints none and continues the count
    assert got == {("Alto Sax", 1, 4), ("Trombone", 1, 6), ("Trombone", 2, 10), ("Guitar", 2, 11)}
    alto = next(f for f in report.features if f.instrument == "Alto Sax")
    assert [(loc.page, loc.bar) for loc in alto.locations] == [(1, 4), (2, 8)]  # reminder at the row start
    tbn = next(f for f in report.features if f.instrument == "Trombone" and f.page == 1)
    assert any("counted" in r and "bar 5" in r for r in tbn.reasons)
    guitar = feature_at(report, "GUITAR SOLO")
    assert any("previous system" in r for r in guitar.reasons)
    assert guitar.confidence < tbn.confidence
