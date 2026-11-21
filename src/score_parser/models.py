"""Data model shared by the pipeline stages and the public report."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

Source = Literal["text", "ocr"]
TitleSource = Literal["filename", "page 1"]
# A feature's kind: "solo" for solo wording, "feature" for "feature" wording
# (a featured passage). The glossary's Feature is both kinds.
FeatureKind = Literal["solo", "feature"]


@dataclass
class Token:
    """A positioned word."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    page: int
    font: str = ""
    source: Source = "text"
    confidence: float | None = None

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class Page:
    number: int
    width: float
    height: float
    tokens: list[Token] = field(default_factory=list)
    source: Source = "text"
    ocr_confidence: float | None = None  # mean over OCR words
    dpi: float | None = None  # native resolution of the scanned image


@dataclass
class InstrumentEntry:
    instrument: str
    family: str
    chairs: list[int]
    labels: list[str]
    doublings: list[str] = field(default_factory=list)


@dataclass
class PageInfo:
    page: int
    source: Source
    ocr_confidence: float | None = None
    dpi: float | None = None


@dataclass
class Feature:
    """A solo or feature marking with its location."""

    kind: FeatureKind
    instrument: str | None
    page: int
    bar: int | None
    rehearsal_mark: str | None
    raw_text: str
    confidence: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class FlowStep:
    """One draft `flow:` step in the planner's shape (never kind or position)."""

    section: str
    instrument: str
    note: str
    todo: str | None = None  # set on low-confidence steps


@dataclass
class ScoreReport:
    title: str
    title_source: TitleSource
    matched_slug: str | None = None  # planner number slug, with numbers_dir
    draft_name: str = ""  # file stem for the flow draft
    unmatched: bool = False  # numbers_dir was given and no slug matched
    instrumentation: list[InstrumentEntry] = field(default_factory=list)
    features: list[Feature] = field(default_factory=list)
    flow: list[FlowStep] = field(default_factory=list)
    unknown_labels: list[str] = field(default_factory=list)
    pages: list[PageInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParseOptions:
    """Options for parse_score."""

    force_ocr: bool = False
    numbers_dir: Path | None = None  # planner numbers/ dir, read-only
