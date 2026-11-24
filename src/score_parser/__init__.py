"""score-parser: instrumentation and solos from big-band score PDFs."""

from pathlib import Path

from .clean import clean
from .features import find_features
from .flow import build_flow
from .instruments import build_instrumentation, vocabulary_hits
from .matching import draft_name, match_slug
from .models import PageInfo, ParseOptions, PartReport, ScoreReport
from .part import parse_part
from .parts import find_parts, parts_warnings
from .staves import unlabeled_staff_warnings
from .source import read_pages, scan_warnings
from .title import score_title

__all__ = ["parse_score", "parse_part", "ParseOptions", "ScoreReport", "PartReport"]


def parse_score(path: str | Path, options: ParseOptions | None = None) -> ScoreReport:
    """Read one score PDF in place and return its report."""
    path = Path(path)
    options = options or ParseOptions()
    pages = [clean(p) for p in read_pages(path, options.force_ocr, vocabulary_hits)]
    instrumentation = build_instrumentation(pages)
    warnings = [w for p in pages for w in scan_warnings(p)] + instrumentation.warnings
    warnings += unlabeled_staff_warnings(pages)
    if not instrumentation.entries:
        warnings.append("no instrumentation found: the first system's labels could not be read")
    title, title_source = score_title(path, pages)
    features, feature_warnings = find_features(pages, instrumentation.roster)
    warnings += feature_warnings
    parts = find_parts(Path(options.parts_dir), title, options) if options.parts_dir else None
    if parts is not None:
        warnings += parts_warnings(parts)
    slug = match_slug(title, Path(options.numbers_dir)) if options.numbers_dir else None
    name, unmatched = draft_name(title, slug, options.numbers_dir)
    return ScoreReport(
        title=title,
        title_source=title_source,
        matched_slug=slug,
        draft_name=name,
        unmatched=unmatched,
        instrumentation=instrumentation.entries,
        features=features,
        flow=build_flow(features),
        unknown_labels=instrumentation.unknown_labels,
        pages=[PageInfo.from_page(p) for p in pages],
        warnings=warnings,
        parts=parts,
    )
