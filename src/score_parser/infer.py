"""Infer unmarked solos from which parts are resting (ADR 0006, `--parts-dir`).

A solo is not always marked: a conductor score may print nothing where one wind
plays alone and the others lay out. The parts show it, because each part counts
its multi-bar rests (part mode). A stretch of the score between two rehearsal
marks is a *possible solo* of one wind when:

- every wind the score has is covered by a readable part (else the others'
  activity is unknown, and nothing is inferred: a warning says so, when a
  stretch looked like a solo);
- exactly one melodic player (a wind or a string; the rhythm section and the
  vocals are not counted) plays the stretch, and at least MIN_RESTING other
  players rest through it, none of them half-playing or unreadable there. A
  player is a player slot (a folder): the parts of a doubler are one player;
- at least MIN_ACTIVE of the resting players play in another stretch, so the
  silence is a contrast and not an arrangement for one lone wind;
- the score marks nothing in the stretch, and no vocal lead in it or the one
  before: a marked feature is never duplicated or overruled (ADR 0004), and a
  wind over a vocal lead is a backing, not a solo.

A part that prints no multi-bar rest anywhere is unknown, not playing: a part
that lays out in single empty bars or cue notes cannot be told from one that
plays. The score needs at least MIN_MARKS distinct rehearsal marks.

The feature is kept low on purpose: INFERRED_CONFIDENCE is under the flow
draft's TODO threshold, and its reason says it was inferred from the other parts
resting. Stretches are the score's: a part is read by bar number against the
mark's bar range (ADR 0003: sections first; the bar only tells the part where
in the section a rest is).
"""

from dataclasses import dataclass, field

from .crossref import insert_in_score_order, is_readable, part_names
from .flow import LOW_CONFIDENCE
from .instruments import present_as, resolve
from .models import Feature, InstrumentEntry, Location, PartReport, PartsReport, ScoreMap, ScoreMark

WINDS = frozenset({"Woodwind", "Saxophone", "Trumpet", "Brass", "Trombone"})
MELODIC = WINDS | {"Strings"}  # the families whose parts count as playing; Rhythm and Vocal never do
MIN_SECTION_BARS = 4  # a shorter stretch is a bar count's noise, not a section
MIN_MARKS = 2  # a score with fewer distinct rehearsal marks has no sections to tell apart
COVERAGE = 0.75  # a part is known in a stretch when its bars cover this share of it
PLAY_SHARE = 0.5  # a part plays a stretch when it is not inside a multi-bar rest for this share of it
REST_SHARE = 0.75  # ... and rests it when a multi-bar rest covers this share
MIN_RESTING = 3  # fewer resting players than this is a small group playing, not a wind alone
MIN_ACTIVE = 2  # of the resting players, this many play somewhere else in the song
INFERRED_CONFIDENCE = round(LOW_CONFIDENCE - 0.3, 2)  # 0.5: well under the flow draft's TODO threshold

PLAY, REST, MIXED, UNKNOWN = "plays", "rests", "partly plays", "unknown"
_PRECEDENCE = (PLAY, UNKNOWN, MIXED, REST)  # a player with several parts: the first status any part has


@dataclass
class _Part:
    """One melodic part and the bars it plays and rests."""

    part: PartReport
    played: set[int] = field(default_factory=set)
    rested: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        for run in self.part.bars:
            (self.rested if run.rest else self.played).update(range(run.first, run.last + 1))

    @property
    def name(self) -> str:
        return self.part.part.instrument or ""

    def status(self, bars: range) -> str:
        """Whether the part plays, rests or half-plays the bars, or its bars there are not read.
        A part with no multi-bar rest at all is unknown: nothing shows where it lays out."""
        if not self.rested:
            return UNKNOWN
        playing = sum(b in self.played for b in bars)
        resting = sum(b in self.rested and b not in self.played for b in bars)
        if playing + resting < COVERAGE * len(bars):
            return UNKNOWN
        if resting >= REST_SHARE * len(bars):
            return REST
        return PLAY if playing >= PLAY_SHARE * len(bars) else MIXED


@dataclass
class _Player:
    """One player slot: its melodic parts (a doubler has one per instrument)."""

    parts: list[_Part] = field(default_factory=list)

    def status(self, bars: range) -> str:
        found = [p.status(bars) for p in self.parts]
        return next(s for s in _PRECEDENCE if s in found)

    def playing(self, bars: range) -> _Part:
        """The part that plays most of the bars."""
        return max(self.parts, key=lambda p: sum(b in p.played for b in bars))


def _melodic(part: PartReport) -> _Part | None:
    hit = resolve(part.part.instrument) if part.part.instrument else None
    return _Part(part) if is_readable(part) and hit and hit.family in MELODIC else None


def _players(parts: list[PartReport]) -> list[_Player]:
    """The melodic players: the parts of one folder are one player, except that two parts of
    one instrument in a folder ("trumpet-4-5-6") are two players."""
    players: list[_Player] = []
    by_folder: dict[str, list[_Player]] = {}
    for found in filter(None, map(_melodic, parts)):
        slot = by_folder.setdefault(found.part.part.player_slot, [])
        home = next((p for p in slot if not any(present_as(found.name, [q.name]) for q in p.parts)), None)
        if home is None:
            home = _Player()
            slot.append(home)
            players.append(home)
        home.parts.append(found)
    return players


def _covers(part: PartReport) -> list[tuple[str, int | None]]:
    """The (instrument, chair) players a part stands for: its own, and the slot's
    (a Clarinet part in the alto 1 folder stands for the Alto Sax 1 player too)."""
    info = part.part
    own = [(n, c) for n in part_names(part) for c in info.chairs or [None]]
    slot = [(info.slot_instrument, c) for c in info.slot_chairs or [None]] if info.slot_instrument else []
    return own + slot


def uncovered(entries: list[InstrumentEntry], parts: list[PartReport]) -> list[str]:
    """The winds (instrument and chair) of the score that no readable part stands for."""
    covers = [c for part in parts if is_readable(part) for c in _covers(part)]
    missing = []
    for entry in entries:
        if entry.family not in MELODIC:
            continue
        for chair in entry.chairs if len(entry.chairs) > 1 else [None]:
            if not any(present_as(entry.instrument, [name]) and (chair is None or c == chair) for name, c in covers):
                missing.append(f"{entry.instrument} {chair}" if chair else entry.instrument)
    return missing


def _sections(score: ScoreMap) -> list[ScoreMark]:
    """The stretches to read, in score order: printings with a known start and end of at least
    MIN_SECTION_BARS bars, one per (start, end) (two marks printed together are one stretch).
    None when the score has fewer than MIN_MARKS distinct marks."""
    if len({m.text for m in score.marks}) < MIN_MARKS:
        return []
    seen: set[tuple[int, int]] = set()
    found = []
    for m in score.marks:
        if m.bar is None or m.end is None or m.end - m.bar < MIN_SECTION_BARS or (m.bar, m.end) in seen:
            continue
        seen.add((m.bar, m.end))
        found.append(m)
    return found


def _marked(f: Feature, m: ScoreMark, score: ScoreMap) -> bool:
    """Whether the feature is in the section (of any kind: a vocal lead counts)."""
    if f.bar is not None and m.bar <= f.bar < m.end:
        return True
    return f.rehearsal_mark == m.text and score.in_force(f.rehearsal_mark, f.bar) is m


def _vetoed(features: list[Feature], sections: list[ScoreMark], i: int, score: ScoreMap) -> bool:
    """The score marks something in the stretch, or a vocal lead in it or the one before (a lead
    runs on past the mark it starts at)."""
    nearby = sections[max(i - 1, 0) : i + 1]
    return any(
        _marked(f, sections[i], score) or (f.kind == "vocal lead" and any(_marked(f, m, score) for m in nearby))
        for f in features
    )


def _feature(lone: _Part, m: ScoreMark, resting: int) -> Feature:
    chairs = lone.part.part.chairs
    return Feature(
        kind="solo", instrument=lone.name, page=m.page, bar=m.bar, rehearsal_mark=m.text,
        raw_text="", confidence=INFERRED_CONFIDENCE,
        reasons=[
            f"inferred from the other parts resting, not marked in the score: the {lone.name} part plays "
            f"mark {m.text} (bars {m.bar}-{m.end - 1}) while {resting} other players rest"
        ],
        locations=[Location(m.page, m.bar)],
        chair=chairs[0] if len(chairs) == 1 else None, chair_ambiguous=len(chairs) > 1,
    )


def infer_unmarked_solos(
    features: list[Feature], parts: PartsReport, score: ScoreMap, instrumentation: list[InstrumentEntry]
) -> tuple[list[Feature], list[str]]:
    """(the features with the inferred solos added in score order, warnings when
    the inference was not possible). Nothing is inferred without parts."""
    sections = _sections(score)
    if not parts.parts or not sections:
        return features, []
    players = _players(parts.parts)
    states = [[p.status(range(m.bar, m.end)) for p in players] for m in sections]
    found: list[Feature] = []
    unread: list[str] = []
    for i, (m, status) in enumerate(zip(sections, states)):
        playing = [p for p, s in zip(players, status) if s == PLAY]
        resting = [j for j, s in enumerate(status) if s == REST]
        others = len(resting) + status.count(UNKNOWN)  # a player whose bars are not read might rest
        if len(playing) != 1 or others < MIN_RESTING or _vetoed(features, sections, i, score):
            continue
        if UNKNOWN in status:
            unread.append(m.text)
            continue
        if MIXED in status:  # a player that half plays is no clean rest
            continue
        active = sum(any(states[k][j] == PLAY for k in range(len(sections)) if k != i) for j in resting)
        if active >= MIN_ACTIVE:
            found.append(_feature(playing[0].playing(range(m.bar, m.end)), m, len(resting)))
    missing = uncovered(instrumentation, parts.parts)
    if missing:  # a part that is not in the tree might be playing; say so only when it mattered
        if not found:
            return features, []
        marks = ", ".join(f.rehearsal_mark for f in found)
        return features, [
            f"unmarked solos not inferred: no readable part for {', '.join(missing)}, so who plays is unknown "
            f"(a possible solo at mark{'s' if len(found) > 1 else ''} {marks})"
        ]
    for f in found:
        insert_in_score_order(features, f)
    if not unread:
        return features, []
    return features, [
        f"unmarked solos not inferred at mark{'s' if len(unread) > 1 else ''} {', '.join(unread)}: "
        "the bars of some parts could not be read there"
    ]
