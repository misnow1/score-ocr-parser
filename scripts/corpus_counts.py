"""Print per-score counts for a folder of scores so two runs can be compared.

Local helper. Numbers only: one row per score (by sorted position), with
counts of instruments, features, features with no bar, features with no
instrument, features with no rehearsal mark, features whose mark is carried
from an earlier page, and warnings. With a parts folder (--parts-dir or
$SCORE_PARTS_DIR, the `parts/<instrument folder>/<song>.pdf` tree) it adds the
number of parts found for the score and the solos read in them. Writes nothing.
Pass --names to also print each file name.

    uv run python scripts/corpus_counts.py [DIR] [--parts-dir PARTS]    # default: $SCORE_CORPUS_DIR
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tests" / "corpus"))

from part_lookup import parts_of_score  # noqa: E402
from score_parser import parse_score  # noqa: E402

COLUMNS = ("instruments", "features", "no_bar", "no_instrument", "no_mark", "carried", "warnings")
PART_COLUMNS = ("parts", "part_solos")


def counts(report) -> tuple[int, ...]:
    features = report.features
    return (
        len(report.instrumentation),
        len(features),
        sum(f.bar is None for f in features),
        sum(f.instrument is None for f in features),
        sum(f.rehearsal_mark is None for f in features),
        sum(f.mark_carried_from is not None for f in features),
        len(report.warnings),
    )


def part_counts(parts_dir: Path, pdf: Path) -> tuple[int, int]:
    """(parts found for the score, solos read in them); the parts are read in place."""
    reports = parts_of_score(parts_dir, pdf.stem)
    return len(reports), sum(len(r.features) for r in reports)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", nargs="?", default=os.environ.get("SCORE_CORPUS_DIR"))
    ap.add_argument("--parts-dir", default=os.environ.get("SCORE_PARTS_DIR"), help="parts tree: also count each score's parts and part solos")
    ap.add_argument("--names", action="store_true", help="also print each file name")
    args = ap.parse_args(argv)
    if not args.folder:
        ap.error("give a folder or set SCORE_CORPUS_DIR")
    parts_dir = Path(args.parts_dir) if args.parts_dir else None
    columns = COLUMNS + (PART_COLUMNS if parts_dir else ())
    pdfs = sorted(p for p in Path(args.folder).iterdir() if p.suffix.lower() == ".pdf")
    print("#   " + "  ".join(f"{c:>13}" for c in columns))
    totals = [0] * len(columns)
    for i, pdf in enumerate(pdfs, 1):
        try:
            row = counts(parse_score(pdf)) + (part_counts(parts_dir, pdf) if parts_dir else ())
        except Exception:  # a crash is a result too; keep the run going
            print(f"{i:<3} FAILED" + (f"  {pdf.name}" if args.names else ""))
            continue
        totals = [t + n for t, n in zip(totals, row)]
        print(f"{i:<3} " + "  ".join(f"{n:>13}" for n in row) + (f"  {pdf.name}" if args.names else ""))
    print("sum " + "  ".join(f"{n:>13}" for n in totals))
    return 0


if __name__ == "__main__":
    sys.exit(main())
