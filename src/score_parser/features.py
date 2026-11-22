"""Interpret stage: solo and feature markings with their locations.

Three steps: `collect_candidates` reads every solo wording on every system,
`merge_candidates` joins copies (a solo printed above every staff, reminders on
the next systems and pages), `build_feature` turns each group into one Feature.
"""

import re
from dataclasses import dataclass, replace
from typing import Literal, NamedTuple

from .layout import is_chord_symbol, running_headers
from .instruments import Roster, resolve, resolve_against_first_system
from .models import Feature, FeatureKind, Location, Page, Participant, Voice
from .measures import BarKind, count_bars, current_mark, drop_out_of_sequence
from .systems import Phrase, System, find_systems
from .vocal import lead_text, voice_staff

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
BAR_GUESSED = 0.05
# Evidence for the bar by how it was found; a bar not found earns nothing.
BAR_EVIDENCE: dict[BarKind, float] = {
    "counted": BAR_FOUND,  # barlines counted from a printed number
    "nearest": BAR_FOUND,
    "continued": BAR_GUESSED,  # counted on from the previous system, no number here
    "assumed": BAR_GUESSED,  # text sits left of every bar number
    "ocr": BAR_GUESSED,  # barlines cannot be counted on a scan
    "missing": 0.0,
}
INSTRUMENT_ABSENT = 0.1  # named in the text but not in the instrumentation: a possible feature
VOICE_NAMED = 0.3  # a vocal lead whose text names the voice ("Female Lead")
VOICE_FROM_STAFF = 0.15  # a bare "solo" above a Voice Lead F/M staff
VOICE_STAFF_CUE = 0.15  # a bare "solo" above a choir or other voice staff: a vocal lead, no voice


def _named_instrument(
    prefix: str, roster: Roster, notes: list[str]
) -> tuple[str, bool, int | None] | None:
    """(instrument, inferred, chair) named by the words just before the solo
    wording; the chair is the number after the instrument, when there is one.
    A named instrument the report's instrumentation lacks is returned only
    when no present one is named (see `_absent_instrument`), with a note."""
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


def _absent_instrument(prefix: str) -> str | None:
    """The instrument the text names that the instrumentation lacks, by the
    roster-free resolve; the staff label is never used."""
    words = re.findall(r"[A-Za-z][A-Za-z.]*", _TEXT_CHAIR.sub("", prefix))
    for n in (2, 1):
        if len(words) >= n:
            hit = resolve(" ".join(words[-n:]))
            if hit and not hit.also:
                return hit.name
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
    voice: Voice | None = None  # vocal leads merge by voice


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
    row: int  # the row of bars it sits on (stacks of one system share a row)
    opens_row: bool  # in the first bar of its row, or bars are not counted
    x: float
    bar: int | None
    bar_kind: BarKind
    mark: str | None
    staff: str  # the staff below the text; empty when the text names an absent instrument
    chair: int | None = None
    chair_from: "ChairFrom | None" = None
    chair_ambiguous: bool = False  # the staff is shared by several chairs
    voice: Voice | None = None  # vocal leads only
    section: str | None = None  # vocal leads only
    slot: int = -1  # position of the staff below the text in its system
    staff_count: int = 0  # staves in that system
    named: bool = False  # the instrument comes from the marking text
    voice_system_index: int | None = None  # vocal leads only: position among the systems that have voice staves

    @property
    def neighbour_index(self) -> int:
        """Where the system sits for deciding what is next to what. A vocal lead is
        printed on the voice systems alone, so the rhythm-section system between
        two of them (a page's second stack) does not separate them."""
        return self.system_index if self.voice_system_index is None else self.voice_system_index

    @property
    def key(self) -> MergeKey:
        """Copies of one solo share it."""
        if self.kind == "vocal lead":
            return MergeKey(self.kind, None, "", "", None, self.voice)
        if self.instrument:
            return MergeKey(
                self.kind, self.instrument, "", "",
                self.chair if self.chair_from == "text" else None,
            )
        return MergeKey(self.kind, None, self.text.lower(), self.staff)

    @property
    def confidence(self) -> float:
        return self.evidence + BAR_EVIDENCE[self.bar_kind]


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
        # The text names an instrument the score lacks (its part is a separate
        # file): keep it as a possible feature. The staff it sits above is not
        # the soloist's (copies are printed above every staff).
        instrument = _absent_instrument(prefix)
        staff_label = ""
        if instrument:
            evidence += INSTRUMENT_ABSENT
            reasons.append(
                f"possible feature: {instrument} named in text is not in this score's "
                "instrumentation (a separate part?)"
            )
        else:
            reasons.append("named instrument is not in the instrumentation; instrument unknown")
    elif staff.voice:
        reasons.append(f"staff '{staff.label}' is a voice staff, not an instrument")
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
    reading = system.bar_at(phrase.x0)
    reasons.append(reading.reason)
    return Candidate(
        kind=kind,
        text=text,
        instrument=instrument,
        evidence=evidence,
        reasons=reasons + notes,
        page=system.page,
        system_index=context.index,
        row=system.row,
        opens_row=system.opens_row(phrase.x0),
        x=phrase.x0,
        bar=reading.bar,
        bar_kind=reading.kind,
        mark=current_mark(context.systems, system, phrase.x0),
        staff=staff_label,
        chair=chair,
        chair_from=chair_from,
        chair_ambiguous=ambiguous,
        slot=next((i for i, s in enumerate(system.staves) if s is staff), -1),
        staff_count=len(system.staves),
        named=bool(named and not named[1]),
    )


class _Dropped:
    """Marker: a solo over a backing vocal staff, which is no feature."""


_DROPPED = _Dropped()


def _vocal_candidate(
    context: SystemContext,
    phrase: Phrase,
    text: str,
    voice: Voice | None,
    section: str | None,
    evidence: float,
    why: str,
) -> Candidate:
    """A vocal lead, with the evidence for its voice (which may be none)."""
    system = context.system
    reading = system.bar_at(phrase.x0)
    reasons = ["matched vocal lead wording", why, reading.reason]
    return Candidate(
        kind="vocal lead",
        text=text,
        instrument=None,
        evidence=BASE + evidence,
        reasons=reasons,
        page=system.page,
        system_index=context.index,
        row=system.row,
        opens_row=system.opens_row(phrase.x0),
        x=phrase.x0,
        bar=reading.bar,
        bar_kind=reading.kind,
        mark=current_mark(context.systems, system, phrase.x0),
        staff="",
        voice=voice,
        section=section,
        voice_system_index=sum(
            any(st.voice for st in sys.staves) for sys in context.systems[: context.index + 1]
        ),
    )


def _vocal_wording(
    context: SystemContext, phrase: Phrase, text: str, roster: Roster
) -> "Candidate | _Dropped | None":
    """The vocal lead a phrase marks, else None: "Female Lead Verse 1", a bare
    solo above a Voice Lead staff, or a bare solo above any other voice staff
    (a choir: a lead with no voice). A solo above a backing vocal staff is
    printed for the lead text beside it and is dropped."""
    lead = lead_text(text)
    if lead:
        return _vocal_candidate(context, phrase, text, lead[0], lead[1], VOICE_NAMED, "voice named in text")
    hit = _match(text)
    below = context.system.staff_for(phrase.yc)
    if hit is None or not below.voice or _named_instrument(hit[1], roster, []):
        return None
    staff = voice_staff(below.label)
    if staff is None:
        why = f"voice staff '{below.label}' below: a vocal lead with no voice"
        return _vocal_candidate(context, phrase, text, None, None, VOICE_STAFF_CUE, why)
    if staff[0] == "backing":
        return _DROPPED
    return _vocal_candidate(
        context, phrase, text, staff[1], None, VOICE_FROM_STAFF, "voice taken from the Voice Lead staff below"
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
            context = SystemContext(systems, index, roster)
            vocal = _vocal_wording(context, phrase, text, roster)
            if vocal is _DROPPED:
                continue
            if vocal:
                candidates.append(vocal)
                continue
            hit = _match(text)
            if hit is None:
                continue
            notes: list[str] = []
            kind, prefix = hit
            candidates.append(
                _candidate(kind, prefix, text, context, phrase, notes)
            )
            for note in notes:
                warnings[f"Page {system.page}: solo/feature '{text}': {note}"] = None
    return candidates, list(warnings)


SHARED_X_TOLERANCE = 3.0  # pt: markings this close are printed at the same place
MAX_REMINDER_GAP = 16  # bars: a reminder sits on the next system, one row of bars on


def _is_reminder_of(c: Candidate, group: list[Candidate]) -> bool:
    """Whether `c` restates the solo in `group` rather than starting another:
    it is on the same or the next system, in the first bar of a later row,
    on no other chair (on a later system), and no more than a row of bars on."""
    last = group[-1]
    if c.neighbour_index - last.neighbour_index > 1:
        return False
    if c.row != last.row and not c.opens_row:
        return False
    # Copies on one system may name different chairs (one above each staff);
    # a restatement on the next system keeps its chair.
    chairs = {g.chair for g in group if g.chair is not None}
    if c.system_index != last.system_index and c.chair is not None and chairs and c.chair not in chairs:
        return False
    sections = {g.section for g in group if g.section}
    if c.section and sections and c.section not in sections:  # "Verse 1" then "Verse 2"
        return False
    return c.bar is None or last.bar is None or abs(c.bar - last.bar) <= MAX_REMINDER_GAP


MIN_OPEN_COPIES = 4  # copies of one marking on one system that make it a marking over every staff
_STAFF_REASONS = ("instrument taken", "chair", "staff '", "possible feature", "named instrument")


def _open_copy(c: Candidate, text: str) -> Candidate:
    """The copy of a generic marking with no instrument: the staff it sits
    above is not the soloist's. `text` is the marking's wording."""
    reasons = [r for r in c.reasons if not r.startswith(_STAFF_REASONS)]
    reasons.append("generic marking printed over every staff: an open solo, instrument unknown")
    return replace(
        c, text=text, instrument=None, staff="", chair=None, chair_from=None, chair_ambiguous=False,
        evidence=BASE, reasons=reasons,
    )


def _folded(c: Candidate, lead: Candidate) -> Candidate:
    """A copy with no instrument joins the copy of the same marking that has one."""
    reasons = c.reasons + [f"copy of the {lead.instrument} marking on another staff"]
    return replace(c, instrument=lead.instrument, staff="", reasons=reasons)


def fold_copies(candidates: list[Candidate]) -> list[Candidate]:
    """Copies of one marking across the staves of one system, whether or not
    they name an instrument. A generic wording (no instrument in its text) on
    more than half of the staves is an open solo: every copy loses its staff's
    instrument. Otherwise copies with no instrument join a copy that has one,
    at the same place."""
    wide: dict[tuple[int, int, str], list[int]] = {}
    for i, c in enumerate(candidates):
        if c.kind != "vocal lead":
            wide.setdefault((c.page, c.system_index, c.text.lower()), []).append(i)
    out = list(candidates)
    open_systems: dict[tuple[int, int], list[Candidate]] = {}
    for members in wide.values():
        copies = [candidates[i] for i in members]
        slots = {c.slot for c in copies}
        if (
            not any(c.named for c in copies)
            and len(slots) >= MIN_OPEN_COPIES
            and len(slots) * 2 > copies[0].staff_count
        ):
            for i in members:
                out[i] = _open_copy(candidates[i], copies[0].text)
            open_systems.setdefault((copies[0].page, copies[0].system_index), []).append(out[members[0]])
            continue
        for i in members:
            c = candidates[i]
            lead = next(
                (
                    o for o in copies
                    if o.instrument and abs(o.x - c.x) <= SHARED_X_TOLERANCE
                ),
                None,
            )
            if c.instrument is None and lead:
                out[i] = _folded(c, lead)
    dropped: set[int] = set()
    for i, c in enumerate(out):
        for open_copy in open_systems.get((c.page, c.system_index), []):
            if c.kind == "vocal lead" and c.text.lower() == open_copy.text.lower():
                dropped.add(i)  # the copy over a voice staff is the same open marking
                continue
            if c.kind != "vocal lead" and not c.named and c.instrument and _near(c, open_copy):
                out[i] = _open_copy(c, open_copy.text)
    return [c for i, c in enumerate(out) if i not in dropped]


def _near(c: Candidate, other: Candidate) -> bool:
    return c.bar is None or other.bar is None or abs(c.bar - other.bar) <= MAX_REMINDER_GAP


def _restated(c: Candidate, latest: dict[MergeKey, list[Candidate]]) -> list[Candidate] | None:
    """The group an instrument-less copy restates: the same wording at the same
    place on a later system, over a staff that names no instrument."""
    return next(
        (
            g for g in latest.values()
            if g[-1].text.lower() == c.text.lower()
            and g[-1].kind == c.kind
            and abs(g[-1].x - c.x) <= SHARED_X_TOLERANCE
            and _is_reminder_of(c, g)
        ),
        None,
    )


def merge_candidates(candidates: list[Candidate]) -> list[list[Candidate]]:
    """Groups of copies, in reading order. A candidate joins the group with its
    key when it is a reminder of it (see `_is_reminder_of`): a copy on another
    staff, or a restatement on the next system or page. A solo by the same
    instrument on another chair or many bars on is a new feature."""
    groups: list[list[Candidate]] = []
    latest: dict[MergeKey, list[Candidate]] = {}
    for c in candidates:
        group = latest.get(c.key)
        if group is None and c.instrument is None and c.kind != "vocal lead":
            group = _restated(c, latest)
        if group is None or not _is_reminder_of(c, group):
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


def _coincide(a: list[Candidate], b: list[Candidate]) -> bool:
    """Whether two groups of different instruments hold the same wording at the
    same place: one bare marking over several staves, not two soloists."""
    return any(
        x.kind != "vocal lead"
        and x.instrument != y.instrument
        and x.system_index == y.system_index
        and x.text.lower() == y.text.lower()
        and abs(x.x - y.x) <= SHARED_X_TOLERANCE
        and x.bar == y.bar
        for x in a
        for y in b
    )


def join_shared(groups: list[list[Candidate]]) -> list[list[list[Candidate]]]:
    """Sets of groups that are one marking shared by several instruments, in
    reading order (a lone group is a set of one). Only groups with an instrument
    join; a group joins the first set it coincides with."""
    sets: list[list[list[Candidate]]] = []
    for group in groups:
        home = next(
            (s for s in sets if group[0].instrument and any(_coincide(group, g) for g in s)),
            None,
        )
        if home is None:
            sets.append([group])
        else:
            home.append(group)
    return sets


def _participant(group: list[Candidate]) -> Participant:
    chair, ambiguous = _group_chair(group)
    return Participant(group[0].instrument or "", chair, ambiguous)


def build_feature(group: list[Candidate], others: list[list[Candidate]] | None = None) -> Feature:
    """One Feature from a group of copies; the best-evidenced copy leads the
    score, reasons and text, while page, bar and mark are those of the first
    appearance (a later reminder never relocates the feature). `others`
    are the groups of the other instruments the same marking is printed over."""
    others = others or []
    everything = group + [c for g in others for c in g]
    lead = max(group, key=lambda c: c.confidence)
    reasons = list(lead.reasons)
    locations = _locations(everything)
    first_page, first_bar = locations[0].page, locations[0].bar
    first = next(c for c in group if (c.page, c.bar) == (first_page, first_bar))
    chair, ambiguous = _group_chair(group)
    if len(group) > 1:
        reasons.append(f"merged {len(group)} copies of the same marking")
    if others:
        names = ", ".join(p.instrument for p in map(_participant, others))
        reasons.append(f"shared with {names}: the same wording at the same place on several staves")
    return Feature(
        kind=lead.kind,
        instrument=lead.instrument,
        chair=chair,
        chair_ambiguous=ambiguous,
        page=first_page,
        bar=first_bar,
        rehearsal_mark=first.mark,
        raw_text=lead.text,
        confidence=round(lead.confidence, 2),
        reasons=reasons,
        locations=locations,
        voice=lead.voice,
        section=next((c.section for c in group if c.section), None),
        shared_with=[_participant(g) for g in others],
    )


def find_features(
    pages: list[Page], roster: Roster
) -> tuple[list[Feature], list[str]]:
    """(features, warnings). Instruments come only from the score's
    instrumentation (`roster`: first system, variants, recurring instruments);
    a solo's own text may also name a missing instrument (a possible feature)."""
    headers = running_headers(pages)
    systems = [s for page in pages for s in find_systems(page, headers)]
    drop_out_of_sequence(systems)
    count_bars(systems)
    candidates, warnings = collect_candidates(systems, roster)
    sets = join_shared(merge_candidates(fold_copies(candidates)))
    return [build_feature(s[0], s[1:]) for s in sets], warnings
