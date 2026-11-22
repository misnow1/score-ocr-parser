from pathlib import Path

from score_parser import parse_score

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"


def test_chair_comes_from_the_text_or_the_staff_and_is_never_guessed():
    report = parse_score(FIXTURES / "finale_chair_solos.pdf")

    got = {(f.instrument, f.chair, f.chair_ambiguous, f.page, f.bar) for f in report.features}
    assert got == {
        ("Guitar", 1, False, 1, 1),  # "GUITAR 1 SOLO": chair from the text
        ("Guitar", 2, False, 1, 1),  # Guitar 1 and 2 stay two features
        ("Trumpet", 3, False, 1, 1),  # bare "SOLO" above the Trumpet 3 staff
        ("Guitar", None, True, 1, 17),  # bare "SOLO" above the shared "Gtrs." staff
        # unnumbered "GUITAR SOLO" above Gtr. 1's staff beats the bare "SOLO" above Gtr. 2's
        ("Guitar", 1, False, 3, 33),
    }


def test_flow_draft_notes_the_chair_or_that_it_is_ambiguous():
    report = parse_score(FIXTURES / "finale_chair_solos.pdf")

    notes = [s.note for s in report.flow]
    assert any("bar 1" in n and "chair 2" in n for n in notes)
    shared = next(s for s in report.flow if "bar 17" in s.note)
    assert "chair ambiguous" in shared.note
    assert shared.todo
