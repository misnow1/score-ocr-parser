"""Data model shared by the pipeline stages and the public report."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

Source = Literal["text", "ocr"]
# Why a page was read the way it was (see source.classify_page).
PageReason = Literal["text", "image", "pattern", "empty"]
TitleSource = Literal["filename", "page 1"]
# A feature's kind: "solo" for solo wording, "feature" for "feature" wording
# (a featured passage), "vocal lead" for a lead vocalist (kept apart from
# instrument solos). The glossary's Feature is every kind.
FeatureKind = Literal["solo", "feature", "vocal lead"]
Voice = Literal["female", "male"]


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
    reason: PageReason = "text"
    # Degrees clockwise the scanned content is printed rotated (0, 90 or 270).
    # Tokens and width/height are already in the upright frame.
    rotation: int = 0
    # Vertical rules drawn on a text-layer page as (x, y0, y1); empty on OCR pages.
    barlines: list[tuple[float, float, float]] = field(default_factory=list)
    # Long horizontal rules (staff lines) as (y, x0, x1) and short vertical ones
    # (barlines, stems) as (x, y0, y1); text-layer pages only. Used by part mode.
    staff_lines: list[tuple[float, float, float]] = field(default_factory=list)
    short_rules: list[tuple[float, float, float]] = field(default_factory=list)
    # Music-font glyphs the clean stage took out of `tokens` (clefs, notes).
    glyphs: list[Token] = field(default_factory=list)


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
    reason: PageReason = "text"
    rotation: int = 0

    @classmethod
    def from_page(cls, page: "Page") -> "PageInfo":
        return cls(
            page.number, page.source, page.ocr_confidence, page.dpi, page.reason, page.rotation
        )


@dataclass
class Location:
    """Where a feature is marked: its first appearance and any reminders."""

    page: int
    bar: int | None


@dataclass
class Participant:
    """An instrument (with its chair) that shares a feature with the lead one."""

    instrument: str
    chair: int | None = None
    chair_ambiguous: bool = False


@dataclass
class Feature:
    """A solo or feature, with its locations (`page` and `bar` are the first).
    One marking over several staves is one Feature: `instrument` and `chair`
    name the first (topmost) instrument, `shared_with` the others."""

    kind: FeatureKind
    instrument: str | None
    page: int
    bar: int | None
    rehearsal_mark: str | None
    raw_text: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    locations: list[Location] = field(default_factory=list)
    chair: int | None = None  # from the marking text or a numbered staff
    chair_ambiguous: bool = False  # on a staff shared by several chairs ("Gtrs.")
    voice: Voice | None = None  # vocal leads only
    section: str | None = None  # vocal leads only: "Verse 1", when the marking gives it
    shared_with: list[Participant] = field(default_factory=list)  # other instruments, staff order
    mark_carried_from: int | None = None  # page the rehearsal mark is printed on, when it is carried onto this one


@dataclass
class FlowStep:
    """One draft `flow:` step in the planner's shape (never kind or position)."""

    section: str
    instrument: str
    note: str
    todo: str | None = None  # set on low-confidence steps
    mark: str | None = None  # the rehearsal mark the step falls under (None: no section); groups the draft


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
    parts: "PartsReport | None" = None  # with parts_dir: the parts found for this song

    def to_dict(self) -> dict:
        return asdict(self)


# How a part's player slot (its instrument folder) relates to the instrument its
# filename names: the same, a doubling (the slot's player also plays it), an
# unexplained disagreement (left as it is, never corrected), or unknown (the
# folder names no instrument, or the part has none).
SlotRelation = Literal["same", "doubling", "unexplained", "unknown"]
InstrumentFrom = Literal["filename", "folder"]


@dataclass
class PartInfo:
    """Who a part is for. `instrument` and `chairs` come from the filename's
    trailing part word (else the folder); `player_slot` is the folder name."""

    instrument: str | None
    chairs: list[int]
    instrument_from: InstrumentFrom | None
    player_slot: str
    slot_instrument: str | None = None  # what the folder name resolves to
    relation: SlotRelation = "unknown"
    note: str = ""  # "player slot alto-sax-1 (Alto Sax) plays Clarinet" for a doubling
    also: list[str] = field(default_factory=list)  # further instruments of a combined name ("KeyboardSynth")


@dataclass
class PartReport:
    """The report of one part file: its instrument and chairs, and its solos."""

    title: str
    part: PartInfo
    features: list[Feature] = field(default_factory=list)
    pages: list[PageInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    file: str = ""  # "<player slot folder>/<file name>": where the part was read from

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PartsReport:
    """A score's parts found in a parts tree (`--parts-dir`): the parts matched
    to the song, in folder then file order, and the files of the tree that are
    for other songs (or none). Only the song title is matched; every part is
    read with part mode."""

    parts: list[PartReport] = field(default_factory=list)
    other_files: list[str] = field(default_factory=list)  # "<folder>/<file>" not matching this song

    @property
    def doublings(self) -> list[PartReport]:
        return [p for p in self.parts if p.part.relation == "doubling"]

    @property
    def unexplained(self) -> list[PartReport]:
        return [p for p in self.parts if p.part.relation == "unexplained"]

    @property
    def unreadable(self) -> list[PartReport]:
        """Matched files whose instrument could not be read."""
        return [p for p in self.parts if p.part.instrument is None]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParseOptions:
    """Options for parse_score."""

    force_ocr: bool = False
    numbers_dir: Path | None = None  # planner numbers/ dir, read-only
    parts_dir: Path | None = None  # planner parts/ tree, read-only: find this score's parts
