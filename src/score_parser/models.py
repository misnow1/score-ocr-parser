"""Data model shared by the pipeline stages and the public report."""

from dataclasses import asdict, dataclass, field


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
    source: str = "text"
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
    source: str = "text"
    ocr_confidence: float | None = None  # mean over OCR words
    dpi: float | None = None  # native resolution of the scanned image


@dataclass
class InstrumentEntry:
    instrument: str
    family: str
    chairs: list[int]
    labels: list[str]


@dataclass
class PageInfo:
    page: int
    source: str
    ocr_confidence: float | None = None
    dpi: float | None = None


@dataclass
class ScoreReport:
    title: str
    title_source: str
    instrumentation: list[InstrumentEntry] = field(default_factory=list)
    unknown_labels: list[str] = field(default_factory=list)
    pages: list[PageInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParseOptions:
    """Options for parse_score."""

    force_ocr: bool = False
