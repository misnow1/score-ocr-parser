"""score-parser: instrumentation and solos from big-band score PDFs."""

from pathlib import Path

from .clean import clean
from .instruments import build_instrumentation
from .models import PageInfo, ParseOptions, ScoreReport
from .source import read_pages

__all__ = ["parse_score", "ParseOptions", "ScoreReport"]


def parse_score(path: str | Path, options: ParseOptions | None = None) -> ScoreReport:
    """Read one score PDF in place and return its report."""
    path = Path(path)
    pages = [clean(p) for p in read_pages(path)]
    instrumentation, unknown, warnings = build_instrumentation(pages)
    return ScoreReport(
        title=path.stem,
        title_source="filename",
        instrumentation=instrumentation,
        unknown_labels=unknown,
        warnings=warnings,
        pages=[PageInfo(p.number, p.source) for p in pages],
    )
