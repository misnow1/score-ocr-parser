"""Interpret stage: solo and feature markings with their locations.

Three steps: `collect_candidates` reads every solo wording on every system,
`merge_candidates` joins copies (a solo printed above every staff, reminders on
the next systems and pages), `build_feature` turns each group into one Feature.
"""

import re
from dataclasses import dataclass
from typing import Literal, NamedTuple

from .layout import is_chord_symbol, running_headers
from .instruments import Roster, resolve, resolve_against_first_system
from .models import Feature, FeatureKind, Location, Page
from .measures import current_mark, drop_out_of_sequence
from .systems import Phrase, System, find_systems

_KEYWORD = re.compile(r"\b(solos?|feature)\b", re.I)
_REPEAT = re.compile(r"^\s*\d+\s*x\s*[-–:]?\s*", re.I)
_VAMP_FOR = re.compile(r"^\s*vamp\s+for\s+", re.I)
_TEXT_CHAIR = re.compile(r"\s(\d)\s*$")  # "GUITAR 1 " before the solo wording
# The vocal word must sit directly before the solo wording ("male vocal solo").
_VOCAL_TIED = re.compile(r"\b(?:(male|female)(?:\s+(?:vocals?|vox))?|vocals?|vox)\s*$", re.I)

# Confidence: a base for matching the wording, plus evidence for the instrument and bar.
BASE = 0.5
INSTRUMENT_NAMED = 0.3
INSTRUMENT_INFERRED = 0.15  # from the staff, or from "male"/"female" alone
BAR_FOUND = 0.1
BAR_GUESSED = 0.05  # text sits left of every bar number


def _named_instrument(
    prefix: str, roster: Roster, notes: list[str]
) -> tuple[str, bool, int | None] | None:
    """(instrument, inferred, chair) named by the words just before the solo
    wording; the chair is the number after the instrument, when there is one.
    A named instrument the report's instrumentation lacks is dropped with a note."""
    vocal = _VOCAL_TIED.search(prefix)
    if vocal:
        return "Vocal", not re.search(r"vocals?|vox", vocal.group(0), re.I), None
    chair_match = _TEXT_CHAIR.search(prefix)
    chair = int(chair_match.group(1)) if chair_match else None
    if chair_match:
        prefix = prefix[: chair_match.start()]
    words = re.findall(r"[A-Za-z][A-Za-z.]*", prefix)
    for n in (2, 1):
        if len(words) < n:
            continue
        candidate = " ".join(words[-n:])
        for form in (candidate, candidate + "s"):
            check = resolve_against_first_system(form, roster)
            if check.hit is None:
                continue
            if check.hit.name in roster:
                return check.hit.name, False, chair
            notes.append(check.problem)
    return None


def strip_chords(text: str) -> str:
    """The phrase without chord symbols ("F6 TENOR SOLO" -> "TENOR SOLO")."""
    return " ".join(w for w in text.split() if not is_chord_symbol(w))


def _match(text: str) -> tuple[FeatureKind, str] | None:
    """(kind, the text before the solo wording) or None."""
    m = _KEYWORD.search(text)
    if not m:
        return None
    kind: FeatureKind = "feature" if m.group(1).lower() == "feature" else "solo"
    return kind, _VAMP_FOR.sub("", _REPEAT.sub("", text[: m.start()]))


@dataclass(frozen=True)
class MergeKey:
    """What copies of one solo share: the instrument when one could be named;
    otherwise the text and staff (copies of a named text share a key whatever
    staff they sit above)."""

    kind: FeatureKind
    instrument: str | None
    text: str  # empty when the instrument is named
    staff: str  # empty when the instrument is named
    chair: int | None = None  # a chair named in the text; chairs are separate features


# Where a chair came from, strongest first: the marking text ("GUITAR 1 SOLO"),
# an unnumbered "GUITAR SOLO" printed above that instrument's own numbered
# staff, or the staff of a bare "SOLO".
ChairFrom = Literal["text", "own staff", "staff"]
_CHAIR_RANK: dict[ChairFrom, int] = {"text": 3, "own staff": 2, "staff": 1}


@dataclass
class Candidate:
    """One solo wording on one system, before copies are merged."""

    kind: FeatureKind
    text: str  # the phrase, chord symbols stripped
    instrument: str | None
    evidence: float  # confidence earned by the instrument
    reasons: list[str]
    page: int
    system_index: int  # position of the system in reading order
    x: float
    bar: int | None
    bar_certain: bool
    mark: str | None
    staff: str  # the staff below the text; empty when the text names an absent instrument
    chair: int | None = None
    chair_from: "ChairFrom | None" = None
    chair_ambiguous: bool = False  # the staff is shared by several chairs

    @property
    def key(self) -> MergeKey:
        """Copies of one solo share it."""
        if self.instrument:
            return MergeKey(
                self.kind, self.instrument, "", "",
                self.chair if self.chair_from == "text" else None,
            )
        return MergeKey(self.kind, None, self.text.lower(), self.staff)

    @property
    def confidence(self) -> float:
        if self.bar is None:
            return self.evidence
        return self.evidence + (BAR_FOUND if self.bar_certain else BAR_GUESSED)


class SystemContext(NamedTuple):
    """Where a wording was found: the document's systems, which of them, and
    the roster that instruments are checked against."""

    systems: list[System]
    index: int
    roster: Roster

    @property
    def system(self) -> System:
        return self.systems[self.index]


def _candidate(
    kind: FeatureKind,
    prefix: str,
    text: str,
    context: SystemContext,
    phrase: Phrase,
    notes: list[str],
) -> Candidate:
    system, roster = context.system, context.roster
    staff = system.staff_for(phrase.yc)
    reasons = [f"matched {kind} wording"]
    evidence = BASE
    instrument = None
    chair = None
    chair_from: ChairFrom | None = None
    ambiguous = False
    staff_label = staff.label
    named = _named_instrument(prefix, roster, notes)
    if named and not named[1]:
        instrument, chair = named[0], named[2]
        evidence += INSTRUMENT_NAMED
        reasons.append("instrument named in text")
        if chair:
            chair_from = "text"
            reasons.append(f"chair {chair} named in text")
        else:
            own = resolve(staff.label)
            if own and own.name == instrument and not own.also and own.single_chair:
                chair, chair_from = own.single_chair, "own staff"
                reasons.append(f"chair {chair} taken from the {instrument} staff '{staff.label}' below")
    elif named:
        instrument = named[0]
        evidence += INSTRUMENT_INFERRED
        reasons.append("instrument inferred from 'male'/'female' without a vocal word")
    elif notes:
        # The text names an instrument the score lacks: the staff it sits above
        # is not the soloist's (copies are printed above every staff).
        reasons.append("named instrument is not in the instrumentation; instrument unknown")
        staff_label = ""
    else:
        check = resolve_against_first_system(staff.label, roster)
        if check.hit and check.hit.also:
            reasons.append(f"staff '{staff.label}' names several instruments; instrument unknown")
        elif check.hit and check.hit.name in roster:
            instrument = check.hit.name
            evidence += INSTRUMENT_INFERRED
            reasons.append(f"instrument taken from staff '{staff.label}'")
            chair = check.hit.single_chair
            chair_from = "staff" if chair else None
            ambiguous = check.hit.shared
            if chair:
                reasons.append(f"chair {chair} taken from staff '{staff.label}'")
            elif ambiguous:
                reasons.append(f"staff '{staff.label}' is shared by several chairs; chair ambiguous")
        else:
            reasons.append(f"staff '{staff.label}' not usable; instrument unknown")
            if check.problem:
                notes.append(check.problem)
    bar, certain = system.bar_at(phrase.x0)
    if bar is None:
        reasons.append("no bar number found on this system")
    elif certain:
        reasons.append(f"nearest bar number {bar}")
    else:
        reasons.append(f"text sits left of every bar number; assumed first bar {bar}")
    return Candidate(
        kind=kind,
        text=text,
        instrument=instrument,
        evidence=evidence,
        reasons=reasons + notes,
        page=system.page,
        system_index=context.index,
        x=phrase.x0,
        bar=bar,
        bar_certain=certain,
        mark=current_mark(context.systems, system, phrase.x0),
        staff=staff_label,
        chair=chair,
        chair_from=chair_from,
        chair_ambiguous=ambiguous,
    )


def collect_candidates(
    systems: list[System], roster: Roster
) -> tuple[list[Candidate], list[str]]:
    """(candidates, warnings): every solo wording on every system, in reading order."""
    candidates: list[Candidate] = []
    warnings: dict[str, None] = {}
    for index, system in enumerate(systems):
        for phrase in system.texts:
            text = strip_chords(phrase.text)
            hit = _match(text)
            if hit is None:
                continue
            notes: list[str] = []
            kind, prefix = hit
            candidates.append(
                _candidate(
                    kind, prefix, text, SystemContext(systems, index, roster), phrase, notes
                )
            )
            for note in notes:
                warnings[f"Page {system.page}: solo/feature '{text}': {note}"] = None
    return candidates, list(warnings)


def merge_candidates(candidates: list[Candidate]) -> list[list[Candidate]]:
    """Groups of copies, in reading order. A candidate joins the group with its
    key when that group was last seen on the same system or the one before it
    (a copy on another staff, or a reminder on the next system or page)."""
    groups: list[list[Candidate]] = []
    latest: dict[MergeKey, list[Candidate]] = {}
    for c in candidates:
        group = latest.get(c.key)
        if group is None or c.system_index - group[-1].system_index > 1:
            group = latest[c.key] = []
            groups.append(group)
        group.append(c)
    return groups


def _locations(group: list[Candidate]) -> list[Location]:
    """Distinct (page, bar) in reading order; a page's unnumbered copies add nothing
    when the page has a numbered one."""
    numbered = {c.page for c in group if c.bar is not None}
    seen: dict[tuple[int, int | None], None] = {}
    for c in group:
        if c.bar is None and c.page in numbered:
            continue
        seen[(c.page, c.bar)] = None
    return [Location(page, bar) for page, bar in seen]


def _group_chair(group: list[Candidate]) -> tuple[int | None, bool]:
    """(chair, ambiguous) for merged copies: the strongest source wins; copies
    of one source that name different chairs, or only shared staves, are ambiguous."""
    named = [c for c in group if c.chair is not None and c.chair_from]
    if named:
        best = max(_CHAIR_RANK[c.chair_from] for c in named if c.chair_from)
        chairs = {c.chair for c in named if c.chair_from and _CHAIR_RANK[c.chair_from] == best}
        if len(chairs) == 1:
            return chairs.pop(), False
        return None, True
    return None, any(c.chair_ambiguous for c in group)


def build_feature(group: list[Candidate]) -> Feature:
    """One Feature from a group of copies; the best-evidenced copy leads."""
    lead = max(group, key=lambda c: c.confidence)
    reasons = list(lead.reasons)
    chair, ambiguous = _group_chair(group)
    if len(group) > 1:
        reasons.append(f"merged {len(group)} copies of the same marking")
    return Feature(
        kind=lead.kind,
        instrument=lead.instrument,
        chair=chair,
        chair_ambiguous=ambiguous,
        page=lead.page,
        bar=lead.bar,
        rehearsal_mark=lead.mark,
        raw_text=lead.text,
        confidence=round(lead.confidence, 2),
        reasons=reasons,
        locations=_locations(group),
    )


def find_features(
    pages: list[Page], roster: Roster
) -> tuple[list[Feature], list[str]]:
    """(features, warnings). Instruments come only from the score's
    instrumentation (`roster`: first system, variants, recurring instruments);
    anything else is dropped with a warning."""
    headers = running_headers(pages)
    systems = [s for page in pages for s in find_systems(page, headers)]
    drop_out_of_sequence(systems)
    candidates, warnings = collect_candidates(systems, roster)
    return [build_feature(g) for g in merge_candidates(candidates)], warnings
