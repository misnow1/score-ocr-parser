"""score-parser: instrumentation and solos from big-band score PDFs."""

from pathlib import Path

from .clean import clean
from .features import find_features
from .flow import build_flow
from .instruments import build_instrumentation
from .matching import match_slug, slugify
from .models import PageInfo, ParseOptions, ScoreReport
from .source import read_pages, scan_warnings
from .title import score_title

__all__ = ["parse_score", "ParseOptions", "ScoreReport"]


def parse_score(path: str | Path, options: ParseOptions | None = None) -> ScoreReport:
    """Read one score PDF in place and return its report."""
    path = Path(path)
    options = options or ParseOptions()
    pages = [clean(p) for p in read_pages(path, force_ocr=options.force_ocr)]
    instrumentation, unknown, label_warnings = build_instrumentation(pages)
    warnings = [w for p in pages for w in scan_warnings(p)] + label_warnings
    title, title_source = score_title(path, pages)
    features = find_features(pages)
    slug = match_slug(title, Path(options.numbers_dir)) if options.numbers_dir else None
    if slug:
        draft_name = slug
    elif options.numbers_dir:
        draft_name = f"UNMATCHED-{slugify(title)}"
    else:
        draft_name = slugify(title)
    return ScoreReport(
        title=title,
        title_source=title_source,
        matched_slug=slug,
        draft_name=draft_name,
        instrumentation=instrumentation,
        features=features,
        flow=build_flow(features),
        unknown_labels=unknown,
        pages=[PageInfo(p.number, p.source, p.ocr_confidence, p.dpi) for p in pages],
        warnings=warnings,
    )
