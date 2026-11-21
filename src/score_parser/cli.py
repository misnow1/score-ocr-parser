"""Command line interface: a thin wrapper around parse_score."""

import argparse
import json
import sys
from pathlib import Path

from . import parse_score
from .clean import clean
from .layout import first_system_labels, lines
from .source import read_pages


def _parse(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pdfs: list[Path] = []
    for p in map(Path, args.paths):
        pdfs.extend(sorted(p.glob("*.pdf")) if p.is_dir() else [p])
    for pdf in pdfs:
        report = parse_score(pdf)
        (out / f"{pdf.stem}.json").write_text(json.dumps(report.to_dict(), indent=2) + "\n")
        print(
            f"{pdf.name}: {len(report.instrumentation)} instruments, "
            f"{len(report.unknown_labels)} unknown labels"
        )
    return 0


def _inspect(args: argparse.Namespace) -> int:
    """Print only. Never writes files (scores are unlicensed)."""
    pages = read_pages(Path(args.path))
    if not 1 <= args.page <= len(pages):
        print(f"page {args.page} out of range (1-{len(pages)})", file=sys.stderr)
        return 1
    page = clean(pages[args.page - 1])
    if args.layout:
        print("labels (first system):")
        for label in first_system_labels(page):
            print(f"  {label}")
        print("lines:")
        for ln in lines(page.tokens):
            print(f"  y={ln[0].yc:7.1f}  {' '.join(t.text for t in ln)}")
    else:
        for t in page.tokens:
            print(f"{t.x0:7.1f} {t.y0:7.1f} {t.x1:7.1f} {t.y1:7.1f}  {t.font:<20} {t.text}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="score-parser")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("parse", help="parse score PDFs and write JSON reports")
    p.add_argument("paths", nargs="+", help="PDF files or folders of PDFs")
    p.add_argument("--out", default="out", help="output directory (default: out)")
    p.set_defaults(func=_parse)

    i = sub.add_parser("inspect", help="print one page's tokens or layout to stdout")
    i.add_argument("path")
    i.add_argument("--page", type=int, default=1)
    view = i.add_mutually_exclusive_group()
    view.add_argument("--tokens", action="store_true", help="positioned words (default)")
    view.add_argument("--layout", action="store_true", help="label column and lines")
    i.set_defaults(func=_inspect)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
