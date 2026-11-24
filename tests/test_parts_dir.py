"""--parts-dir (ticket #54): find a score's parts in the planner's
`parts/<instrument folder>/<song file>.pdf` tree, through parse_score on a
synthetic score and a temp tree of synthetic one-staff parts."""

import shutil
from pathlib import Path

from score_parser import ParseOptions, find_part_files, parse_score
from score_parser.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"
PART = FIXTURES / "part_one_staff.pdf"
SCORE = FIXTURES / "finale_solos.pdf"


def score_named(tmp_path: Path, title: str) -> Path:
    path = tmp_path / "scores_in" / f"{title} SCORE.pdf"
    path.parent.mkdir(exist_ok=True)
    shutil.copy(SCORE, path)
    return path


def tree(tmp_path: Path, files: list[str]) -> Path:
    """parts/<folder>/<name> for each "folder/name": a .pdf is a synthetic part,
    anything else a stray text file."""
    root = tmp_path / "parts"
    for rel in files:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.suffix.lower() == ".pdf":
            shutil.copy(PART, target)
        else:
            target.write_text("stray")
    return root


def parts_of(tmp_path, title, files):
    root = tree(tmp_path, files)
    return parse_score(score_named(tmp_path, title), ParseOptions(parts_dir=root))


def test_parts_of_a_song_are_found_across_every_instrument_folder_except_scores(tmp_path):
    report = parts_of(tmp_path, "Synthetic Tune", [
        "trumpet-1/Synthetic Tune Trpt1.pdf",
        "trombone-2/Synthetic Tune Trombone2.pdf",
        "drums/Synthetic Tune Drums.pdf",
        "scores/Synthetic Tune SCORE.pdf",  # the conductor score is not a part
        "drums/notes.txt",  # a stray file is ignored
        "trumpet-1/Other Song Trpt1.pdf",
    ])

    found = sorted((p.part.player_slot, p.part.instrument, tuple(p.part.chairs)) for p in report.parts.parts)
    assert found == [("drums", "Drums", ()), ("trombone-2", "Trombone", (2,)), ("trumpet-1", "Trumpet", (1,))]
    assert report.parts.other_files == ["trumpet-1/Other Song Trpt1.pdf"]


def test_without_parts_dir_nothing_is_searched(tmp_path):
    assert parse_score(score_named(tmp_path, "Synthetic Tune")).parts is None


def test_doublings_and_unexplained_disagreements_are_reported_and_nothing_is_corrected(tmp_path):
    report = parts_of(tmp_path, "Synthetic Tune", [
        "alto-sax-1/Synthetic Tune Alto sax1.pdf",
        "alto-sax-1/Synthetic Tune Clarinet.pdf",  # a doubling of the alto 1 player
        "tenor-sax-1/Synthetic Tune soprano sax.pdf",  # another
        "tenor-sax-2/Synthetic Tune Trombone.pdf",  # a misfile, or not: left as filed
        "tenor-sax-2/Synthetic Tune Tenor sax1-2.pdf",  # a combined file
    ])

    parts = report.parts
    assert [(p.part.player_slot, p.part.instrument) for p in parts.doublings] == [
        ("alto-sax-1", "Clarinet"),
        ("tenor-sax-1", "Soprano Sax"),
    ]
    assert [(p.part.player_slot, p.part.instrument) for p in parts.unexplained] == [("tenor-sax-2", "Trombone")]
    assert [(p.part.instrument, p.part.chairs) for p in parts.parts if p.file.endswith("1-2.pdf")] == [
        ("Tenor Sax", [1, 2])
    ]
    assert report.warnings.count(
        "part tenor-sax-2/Synthetic Tune Trombone.pdf: player slot tenor-sax-2 (Tenor Sax) holds a Trombone "
        "part: unexplained disagreement, left as filed"
    ) == 1


def test_a_file_whose_instrument_cannot_be_read_is_reported(tmp_path):
    report = parts_of(tmp_path, "Synthetic Tune", [
        "misc/Synthetic Tune.pdf",  # no part word, and the folder names no instrument
        "trumpet-1/Synthetic Tune Trpt1.pdf",
    ])

    assert [p.file for p in report.parts.unreadable] == ["misc/Synthetic Tune.pdf"]
    assert "part misc/Synthetic Tune.pdf: instrument unknown: neither the filename nor the folder 'misc' names one" in report.warnings


def test_a_song_with_no_parts_says_so(tmp_path):
    report = parts_of(tmp_path, "Synthetic Tune", ["trumpet-1/Other Song Trpt1.pdf"])

    assert report.parts.parts == []
    assert report.parts.other_files == ["trumpet-1/Other Song Trpt1.pdf"]
    assert "no parts found for this song in the parts directory" in report.warnings


def test_the_part_files_of_each_instrument_are_read_with_part_mode(tmp_path):
    report = parts_of(tmp_path, "Synthetic Tune", ["trumpet-1/Synthetic Tune Trpt1.pdf"])

    (trumpet,) = report.parts.parts
    assert [(f.page, f.bar, f.rehearsal_mark) for f in trumpet.features] == [(1, 6, "A"), (2, 16, "B")]


def test_short_or_similar_titles_never_match_the_wrong_song(tmp_path):
    report = parts_of(tmp_path, "Sing", [
        "trumpet-1/Sing Trpt1.pdf",
        "trumpet-1/Sing Sing Sing Trpt1.pdf",  # a longer title that contains it
        "trumpet-2/Singing In The Rain Trpt2.pdf",
        "trumpet-3/Sink Trpt3.pdf",  # a short near miss
    ])

    assert [p.file for p in report.parts.parts] == ["trumpet-1/Sing Trpt1.pdf"]


def test_a_title_inside_a_longer_one_or_with_another_number_is_another_song(tmp_path):
    report = parts_of(tmp_path, "Christmas Is", [
        "bass/Christmas Is Bass.pdf",
        "bass/Christmas Is Coming Bass.pdf",
        "drums/Christmas Is 2 Drums.pdf",
    ])

    assert [p.file for p in report.parts.parts] == ["bass/Christmas Is Bass.pdf"]


def test_the_title_matches_whatever_the_case_the_article_or_a_typo(tmp_path):
    report = parts_of(tmp_path, "The Jingle Bells", [
        "trumpet-1/JINGLE BELLS Trpt1.pdf",
        "trumpet-2/Jingle Bels Trpt2.pdf",  # a typo
        "trumpet-3/Jingle Bell Rock Trpt3.pdf",  # another song
    ])

    assert [p.file for p in report.parts.parts] == ["trumpet-1/JINGLE BELLS Trpt1.pdf", "trumpet-2/Jingle Bels Trpt2.pdf"]


def test_parse_cli_reports_parts_per_song_and_files_that_match_no_song(tmp_path, capsys):
    root = tree(tmp_path, [
        "trumpet-1/Synthetic Tune Trpt1.pdf",
        "alto-sax-1/Synthetic Tune Clarinet.pdf",
        "trumpet-1/Second Song Trpt1.pdf",
        "trumpet-1/Nobody Wants This Trpt1.pdf",
    ])
    first, second = score_named(tmp_path, "Synthetic Tune"), score_named(tmp_path, "Second Song")
    third = score_named(tmp_path, "Third Song")  # no parts

    code = main(["parse", str(first), str(second), str(third), "--out", str(tmp_path / "out"),
                 "--parts-dir", str(root)])

    out = capsys.readouterr().out
    assert code == 0
    rows = {line.split("  ")[0].strip(): line.split() for line in out.splitlines()}
    assert rows["Synthetic Tune SCORE.pdf"][-4:] == ["2", "1", "0", "0"]  # parts, doublings, unexplained, unreadable
    assert rows["Second Song SCORE.pdf"][-4:] == ["1", "0", "0", "0"]
    assert rows["Third Song SCORE.pdf"][-4:] == ["0", "0", "0", "0"]
    assert "files matching no song: 1" in out
    assert "trumpet-1/Nobody Wants This Trpt1.pdf" in out


def test_without_parts_dir_the_cli_prints_no_parts_summary(tmp_path, capsys):
    main(["parse", str(score_named(tmp_path, "Synthetic Tune")), "--out", str(tmp_path / "out")])

    assert "parts" not in capsys.readouterr().out


def test_parse_refuses_to_write_into_the_parts_directory(tmp_path):
    root = tree(tmp_path, ["trumpet-1/Synthetic Tune Trpt1.pdf"])

    code = main(["parse", str(score_named(tmp_path, "Synthetic Tune")), "--out", str(root / "out"),
                 "--parts-dir", str(root)])

    assert code == 2
    assert not (root / "out").exists()


def test_dates_year_tags_and_the_parts_own_labelling_after_the_title_do_not_hide_the_song(tmp_path):
    report = parts_of(tmp_path, "Synthetic Tune 10-3-26", [
        "trumpet-1/Synthetic Tune 10:3:26 Trpt1.pdf",  # a date, punctuated another way
        "trumpet-2/Synthetic Tune JC2026 Trpt2.pdf",  # a year tag
        "violin/Synthetic Tune2022 Violin.pdf",  # a year glued on
        "pno/Synthetic Tune TBN 1 2.pdf",  # an unreadable part word still names an instrument
        "vocals/Synthetic Tune (lead vocal).pdf",
        "vocals/Synthetic Tune Background.pdf",
        "bass/Synthetic Tune Reprise Bass.pdf",  # "Reprise" is not a part: another song
    ])

    assert sorted(p.file for p in report.parts.parts) == [
        "pno/Synthetic Tune TBN 1 2.pdf",
        "trumpet-1/Synthetic Tune 10:3:26 Trpt1.pdf",
        "trumpet-2/Synthetic Tune JC2026 Trpt2.pdf",
        "violin/Synthetic Tune2022 Violin.pdf",
        "vocals/Synthetic Tune (lead vocal).pdf",
        "vocals/Synthetic Tune Background.pdf",
    ]


def test_a_scores_filename_noise_and_a_parenthesis_do_not_hide_the_song(tmp_path):
    report = parts_of(tmp_path, "Synthetic Tune Score1 (expanded instrumentation)", [
        "trumpet-1/Synthetic Tune Trpt1.pdf",
        "trumpet-2/SYNTHETIC TUNE (lead vocal).pdf",
        "violin/Synthetic Tune Violin Solo 1.pdf",
        "drums/Syntetic Tune Drums.pdf",  # a typo in the file name
        "alto-sax-1/Synthetic Tune Reprise Alto sax.pdf",  # another song
    ])

    assert sorted(p.file for p in report.parts.parts) == [
        "drums/Syntetic Tune Drums.pdf",
        "trumpet-1/Synthetic Tune Trpt1.pdf",
        "trumpet-2/SYNTHETIC TUNE (lead vocal).pdf",
        "violin/Synthetic Tune Violin Solo 1.pdf",
    ]


def test_numbered_and_similar_titles_stay_apart(tmp_path):
    medley_1 = find_part_files(tree(tmp_path, [
        "trumpet-1/Medley 1 Trpt1.pdf",
        "trumpet-2/Medley 2 Trpt2.pdf",  # another number: another song
        "bass/Holiday In Bass.pdf",
        "drums/Away In A Manger Drums.pdf",
    ]), "Medley 1")
    holiday = find_part_files(tmp_path / "parts", "Holiday In 11-3-26")

    assert [p.name for p in medley_1.matched] == ["Medley 1 Trpt1.pdf"]
    assert [p.name for p in holiday.matched] == ["Holiday In Bass.pdf"]  # not Away In A Manger


def test_filename_noise_words_of_a_score_or_part_do_not_hide_the_song(tmp_path):
    files = find_part_files(tree(tmp_path, [
        "trumpet-1/Synthetic Tune Trpt1 EPRINT.pdf",
        "trombone-3/TROMBONE 3Synthetic Tune E.pdf",  # a digit glued to the title, a cut-off tag
        "drums/Synthetic Tune extended version Drums.pdf",
        "bass/Synthetic Tune first Bass.pdf",
    ]), "Synthetic Tune Revised Extended Expanded Instr")

    assert len(files.matched) == 4 and files.other == []


def test_find_part_files_is_the_pure_lookup_behind_the_option(tmp_path, capsys):
    root = tree(tmp_path, [
        "trumpet-1/Synthetic Tune Trpt1.pdf",
        "scores/Synthetic Tune SCORE.pdf",
        "trumpet-1/Other Song Trpt1.pdf",
        "drums/Synthetic Tune Drums.pdf",
    ])

    files = find_part_files(root, "Synthetic Tune")

    assert [(p.parent.name, p.name) for p in files.matched] == [
        ("drums", "Synthetic Tune Drums.pdf"),
        ("trumpet-1", "Synthetic Tune Trpt1.pdf"),
    ]
    assert [p.name for p in files.other] == ["Other Song Trpt1.pdf"]
    assert capsys.readouterr().out == ""


def test_a_leading_instrument_name_does_not_hide_the_song(tmp_path):
    report = parts_of(tmp_path, "Synthetic Tune", [
        "trumpet-1/TRUMPET 1 Synthetic Tune.pdf",
        "trumpet-2/Trumpet Synthetic Tune Reprise.pdf",  # another song
    ])

    assert [p.file for p in report.parts.parts] == ["trumpet-1/TRUMPET 1 Synthetic Tune.pdf"]


def test_a_parody_title_is_an_alias_of_the_song(tmp_path):
    report = parts_of(tmp_path, "Superstition", [
        "vocals/MERRY SUPER CHRISTMAS - lyrics only.pdf",
        "trumpet-1/Super Christmas Trpt1.pdf",
        "trumpet-2/Superman Trpt2.pdf",
    ])

    assert sorted(p.file for p in report.parts.parts) == [
        "trumpet-1/Super Christmas Trpt1.pdf",
        "vocals/MERRY SUPER CHRISTMAS - lyrics only.pdf",
    ]
