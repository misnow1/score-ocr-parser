"""Find a score's parts in the planner's parts tree (`--parts-dir`).

The tree is `parts/<instrument folder>/<song file>.pdf`; the conductor scores in
`scores/` are skipped. A file belongs to the song when its cleaned title (the
filename without its part word and noise) names the score's song. Matched files
are read with part mode, in place. Nothing is written.
"""

from pathlib import Path

from .matching import same_song
from .models import ParseOptions, PartReport, PartsReport
from .part import parse_part, read_part_info

SCORES_FOLDER = "scores"


def _part_files(parts_dir: Path) -> list[Path]:
    """Every PDF one level down in an instrument folder, sorted, `scores/` skipped."""
    return [
        pdf
        for folder in sorted(parts_dir.iterdir())
        if folder.is_dir() and folder.name.lower() != SCORES_FOLDER
        for pdf in sorted(folder.iterdir())
        if pdf.suffix.lower() == ".pdf" and pdf.is_file()
    ]


def find_parts(parts_dir: Path, title: str, options: ParseOptions) -> PartsReport:
    """The parts in `parts_dir` for the song `title`, each read with part mode."""
    report = PartsReport()
    for pdf in _part_files(parts_dir):
        if not same_song(read_part_info(pdf)[1], title):
            report.other_files.append(f"{pdf.parent.name}/{pdf.name}")
            continue
        try:
            report.parts.append(parse_part(pdf, options=options))
        except Exception as exc:  # one bad part must not lose the others
            report.parts.append(_failed(pdf, exc))
    return report


def _failed(pdf: Path, exc: Exception) -> PartReport:
    info, title = read_part_info(pdf)
    msg = " ".join(f"{type(exc).__name__}: {exc}".split())
    return PartReport(title, info, warnings=[f"could not be read: {msg}"], file=f"{pdf.parent.name}/{pdf.name}")


def parts_warnings(parts: PartsReport) -> list[str]:
    """Messages for the score's warnings: a song with no parts, and each part's
    own warnings (an unexplained disagreement, an unreadable instrument)."""
    if not parts.parts:
        return ["no parts found for this song in the parts directory"]
    return [f"part {p.file}: {w}" for p in parts.parts for w in p.warnings]
