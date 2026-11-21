"""score-parser: instrumentation and solos from big-band score PDFs."""

from pathlib import Path

from .clean import clean
from .features import find_features
from .instruments import build_instrumentation
from .models import PageInfo, ParseOptions, ScoreReport
from .source import read_pages, scan_warnings

__all__ = ["parse_score", "ParseOptions", "ScoreReport"]


def parse_score(path: str | Path, options: ParseOptions | None = None) -> ScoreReport:
    """Read one score PDF in place and return its report."""
    path = Path(path)
    options = options or ParseOptions()
    pages = [clean(p) for p in read_pages(path, force_ocr=options.force_ocr)]
    instrumentation, unknown, label_warnings = build_instrumentation(pages)
    warnings = [w for p in pages for w in scan_warnings(p)] + label_warnings
    return ScoreReport(
        title=path.stem,
        title_source="filename",
        instrumentation=instrumentation,
        features=find_features(pages),
        unknown_labels=unknown,
        pages=[PageInfo(p.number, p.source, p.ocr_confidence, p.dpi) for p in pages],
        warnings=warnings,
    )
