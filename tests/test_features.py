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


def test_same_instrument_at_clearly_different_measures_stays_separate():
    report = parse_score(FIXTURES / "finale_distinct_solos.pdf")

    trombones = [f for f in report.features if f.instrument == "Trombone"]
    assert [(f.page, f.bar) for f in trombones] == [(1, 9), (1, 41)]


def test_different_chairs_stay_separate_and_a_restated_chair_merges():
    report = parse_score(FIXTURES / "finale_distinct_solos.pdf")

    guitars = [f for f in report.features if f.instrument == "Guitar"]
    got = [(f.chair, f.page, f.bar, [(loc.page, loc.bar) for loc in f.locations]) for f in guitars]
    assert got == [(1, 2, 49, [(2, 49), (2, 57)]), (2, 3, 65, [(3, 65)])]


def test_bar_numbers_printed_below_each_system_are_read():
    report = parse_score(FIXTURES / "finale_bar_numbers_below.pdf")

    got = {(f.instrument, f.bar) for f in report.features}
    # 41-44 sit under the first system, 45-48 under the second; the 3 3 3 inside it are triplets
    assert got == {("Trombone", 43), ("Alto Sax", 45)}

def test_solo_naming_an_instrument_missing_from_the_score_is_kept_as_a_possible_feature():
    report = parse_score(FIXTURES / "finale_absent_instrument_solo.pdf")

    (feature,) = report.features
    assert feature.instrument == "Violin"  # named by the text, not guessed from the Piano staff
    assert feature.confidence < 0.8
    assert any("not in this score's instrumentation" in r for r in feature.reasons)
    assert "Violin" not in {e.instrument for e in report.instrumentation}


def test_possible_feature_gets_a_todo_in_the_flow_draft(tmp_path):
    from score_parser.cli import main

    out = tmp_path / "out"
    pdf = FIXTURES / "finale_absent_instrument_solo.pdf"
    assert main(["parse", str(pdf), "--out", str(out), "--format", "yaml"]) == 0
    (path,) = out.glob("*.yaml")
    text = path.read_text()
    assert "violin" in text.lower()
    assert "# TODO(score-parser)" in text and "not in this score's instrumentation" in text


def test_chord_text_glued_to_solo_wording_is_stripped_and_never_makes_a_feature():
    report = parse_score(FIXTURES / "finale_chord_text_solos.pdf")

    got = sorted((f.instrument, f.page, f.raw_text) for f in report.features)
    # several chords before a bare "Solo" (glued "Bbmaj7(b5)/GA9 Solo", "E9 Dm7Solo" is one) are a chart label, not a feature,
    # nor is a lone chord ("G7C"); named solos keep their wording without the chords
    assert got == [
        ("Alto Sax", 1, "ALTO SOLO"),
        ("Guitar", 2, "SOLO"),  # one chord before a bare SOLO: kept, see the next test
        ("Trombone", 1, "TBN SOLO"),
    ]


def test_one_chord_before_a_bare_solo_is_a_low_confidence_possible_feature():
    report = parse_score(FIXTURES / "finale_chord_text_solos.pdf")

    guitar = next(f for f in report.features if f.page == 2)
    assert guitar.confidence < 0.8
    assert any("only chord text plus 'Solo'" in r for r in guitar.reasons)
    assert any(step.todo for step in report.flow if "Guitar" in step.section)
