"""score-parser: instrumentation and solos from big-band score PDFs."""

from pathlib import Path

from .clean import clean
from .features import find_features
from .instruments import build_instrumentation
from .layout import first_system_labels
from .models import PageInfo, ParseOptions, ScoreReport
from .source import read_pages

__all__ = ["parse_score", "ParseOptions", "ScoreReport"]


def parse_score(path: str | Path, options: ParseOptions | None = None) -> ScoreReport:
    """Read one score PDF in place and return its report."""
    path = Path(path)
    pages = [clean(p) for p in read_pages(path)]
    labels = first_system_labels(pages[0]) if pages else []
    instrumentation, unknown = build_instrumentation(labels)
    return ScoreReport(
        title=path.stem,
        title_source="filename",
        instrumentation=instrumentation,
        features=find_features(pages),
        unknown_labels=unknown,
        pages=[PageInfo(p.number, p.source) for p in pages],
    )
