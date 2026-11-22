"""Print per-score counts for a folder of scores so two runs can be compared.

Local helper. Numbers only: one row per score (by sorted position), with
counts of instruments, features, features with no bar, features with no
instrument and warnings. Writes nothing. Pass --names to also print each
file name.

    uv run python scripts/corpus_counts.py [DIR]    # default: $SCORE_CORPUS_DIR
"""

import argparse
import os
import sys
from pathlib import Path

from score_parser import parse_score

COLUMNS = ("instruments", "features", "no_bar", "no_instrument", "warnings")


def counts(report) -> tuple[int, ...]:
    features = report.features
    return (
        len(report.instrumentation),
        len(features),
        sum(f.bar is None for f in features),
        sum(f.instrument is None for f in features),
        len(report.warnings),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", nargs="?", default=os.environ.get("SCORE_CORPUS_DIR"))
    ap.add_argument("--names", action="store_true", help="also print each file name")
    args = ap.parse_args(argv)
    if not args.folder:
        ap.error("give a folder or set SCORE_CORPUS_DIR")
    pdfs = sorted(p for p in Path(args.folder).iterdir() if p.suffix.lower() == ".pdf")
    print("#   " + "  ".join(f"{c:>13}" for c in COLUMNS))
    totals = [0] * len(COLUMNS)
    for i, pdf in enumerate(pdfs, 1):
        try:
            row = counts(parse_score(pdf))
        except Exception:  # a crash is a result too; keep the run going
            print(f"{i:<3} FAILED" + (f"  {pdf.name}" if args.names else ""))
            continue
        totals = [t + n for t, n in zip(totals, row)]
        print(f"{i:<3} " + "  ".join(f"{n:>13}" for n in row) + (f"  {pdf.name}" if args.names else ""))
    print("sum " + "  ".join(f"{n:>13}" for n in totals))
    return 0


if __name__ == "__main__":
    sys.exit(main())
