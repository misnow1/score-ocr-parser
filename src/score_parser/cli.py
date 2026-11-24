"""Command line interface: a thin wrapper around parse_score."""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from . import ParseOptions, parse_score
from .clean import clean
from .flow import render_yaml
from .instruments import vocabulary_hits
from .layout import first_system_labels, lines
from .models import ScoreReport
from .source import read_pages


@dataclass
class SummaryRow:
    score: str
    instruments: str
    features: str
    warnings: str


def _print_summary(rows: list[SummaryRow]) -> None:
    """Per-score table: instrument count, feature count, warning count."""
    header = SummaryRow("score", "instruments", "features", "warnings")
    width = max(len(r.score) for r in [header, *rows])
    for r in [header, *rows]:
        print(f"{r.score:<{width}}  {r.instruments:>11}  {r.features:>8}  {r.warnings:>8}")


def _print_parts_summary(reports: list[tuple[str, ScoreReport]], failed: int) -> None:
    """Per-score parts found, the files two songs both match (the risk of a
    title match), and the files that match no song. When a score failed its
    parts are unknown, so the files matching no song cannot be told."""
    found = [(name, r.parts) for name, r in reports if r.parts is not None]
    if not found:
        return
    rows = [(name, *(len(x) for x in (p.parts, p.doublings, p.unexplained, p.unreadable))) for name, p in found]
    header = ("score", "parts", "doublings", "unexplained", "unreadable")
    width = max(len(row[0]) for row in [header, *rows])
    print()
    for row in [header, *rows]:
        print(f"{row[0]:<{width}}  {row[1]:>5}  {row[2]:>9}  {row[3]:>11}  {row[4]:>10}")
    songs_of: dict[str, list[str]] = {}
    for name, p in found:
        for part in p.parts:
            songs_of.setdefault(part.file, []).append(name)
    twice = {file: names for file, names in songs_of.items() if len(names) > 1}
    print(f"files matching more than one song: {len(twice)}")
    for file, names in sorted(twice.items()):
        print(f"  {file}: {', '.join(names)}")
    if failed:
        print(f"files matching no song: not counted, {failed} of the scores failed")
        return
    unmatched = sorted({f for _, p in found for f in p.other_files} - songs_of.keys())
    print(f"files matching no song: {len(unmatched)}")
    for name in unmatched:
        print(f"  {name}")


def _collect_pdfs(paths: list[str]) -> list[Path]:
    """Files as given; folders expand to their PDFs (any letter case), sorted."""
    pdfs: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            pdfs.extend(sorted(f for f in p.iterdir() if f.suffix.lower() == ".pdf" and f.is_file()))
        else:
            pdfs.append(p)
    return pdfs


def _free_name(stem: str, suffix: str, taken: set[str]) -> str:
    """`stem+suffix`, or `stem-2+suffix`, `stem-3+suffix`... when an earlier score
    in this run already wrote that file name."""
    candidate, n = stem + suffix, 1
    while candidate in taken:
        n += 1
        candidate = f"{stem}-{n}{suffix}"
    taken.add(candidate)
    return candidate


def _write_outputs(
    report: ScoreReport, pdf: Path, out: Path, fmt: str, taken: set[str]
) -> list[str]:
    """Write the requested files; returns warnings for names that had to change."""
    notes: list[str] = []

    def target(stem: str, suffix: str) -> Path:
        name = _free_name(stem, suffix, taken)
        if name != stem + suffix:
            notes.append(f"{stem + suffix} was already written by another score; wrote {name}")
        return out / name

    if fmt in ("json", "both"):
        target(pdf.stem, ".json").write_text(json.dumps(report.to_dict(), indent=2) + "\n")
    if fmt in ("yaml", "both"):
        header = ""
        if report.unmatched:
            header = f"UNMATCHED: no planner number matches the title {report.title!r}; name this file by hand."
        target(report.draft_name, ".yaml").write_text(render_yaml(report.flow, header))
    return notes


def _parse(args: argparse.Namespace) -> int:
    out = Path(args.out)
    numbers_dir = Path(args.numbers_dir) if args.numbers_dir else None
    parts_dir = Path(args.parts_dir) if args.parts_dir else None
    for planner_dir, what in ((numbers_dir, "numbers"), (parts_dir, "parts")):
        if planner_dir and (out.resolve() == planner_dir.resolve() or planner_dir.resolve() in out.resolve().parents):
            print(f"refusing to write into the planner {what} directory", file=sys.stderr)
            return 2
    if parts_dir and not parts_dir.is_dir():
        print(f"--parts-dir {parts_dir} is not a directory", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    pdfs = _collect_pdfs(args.paths)
    rows: list[SummaryRow] = []
    reports: list[tuple[str, ScoreReport]] = []
    taken: set[str] = set()
    failed = 0
    for pdf in pdfs:
        try:
            report = parse_score(
                pdf, ParseOptions(force_ocr=args.force_ocr, numbers_dir=numbers_dir, parts_dir=parts_dir)
            )
            report.warnings += _write_outputs(report, pdf, out, args.format, taken)
        except Exception as exc:  # one bad score must not stop the run
            failed += 1
            msg = " ".join(f"{type(exc).__name__}: {exc}".split())
            rows.append(SummaryRow(pdf.name, "FAILED", "-", "-"))
            print(f"{pdf.name}: FAILED {msg}", file=sys.stderr)
            continue
        reports.append((pdf.name, report))
        rows.append(
            SummaryRow(pdf.name, str(len(report.instrumentation)), str(len(report.features)), str(len(report.warnings)))
        )
        for w in report.warnings:
            print(f"  warning ({pdf.name}): {w}", file=sys.stderr)
    _print_summary(rows)
    _print_parts_summary(reports, failed)
    if failed:
        print(f"{failed} of {len(pdfs)} scores failed", file=sys.stderr)
        return 1
    return 0


def _inspect(args: argparse.Namespace) -> int:
    """Print only. Never writes files (scores are unlicensed)."""
    pages = read_pages(Path(args.path), args.force_ocr, vocabulary_hits)
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
    p.add_argument(
        "--format", choices=["json", "yaml", "both"], default="json",
        help="json report, yaml flow draft, or both (default: json)",
    )
    p.add_argument("--numbers-dir", help="planner numbers/ directory (read-only): match titles to slugs")
    p.add_argument(
        "--parts-dir", help="planner parts/ tree (read-only): find each score's parts by song title"
    )
    p.add_argument("--force-ocr", action="store_true", help="OCR every page, ignoring any text layer")
    p.set_defaults(func=_parse)

    i = sub.add_parser("inspect", help="print one page's tokens or layout to stdout")
    i.add_argument("path")
    i.add_argument("--page", type=int, default=1)
    view = i.add_mutually_exclusive_group()
    view.add_argument("--tokens", action="store_true", help="positioned words (default)")
    view.add_argument("--layout", action="store_true", help="label stacks and lines")
    i.add_argument("--force-ocr", action="store_true", help="OCR the page, ignoring any text layer")
    i.set_defaults(func=_inspect)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
