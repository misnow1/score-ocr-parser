"""Infer unmarked solos from which parts are resting (ADR 0006, `--parts-dir`).

A solo is not always marked: a conductor score may print nothing where one wind
plays alone and the others lay out. The parts show it, because each part counts
its multi-bar rests (part mode). A stretch of the score between two rehearsal
marks is a *possible solo* of one wind when:

- every wind the score has is covered by a readable part (else the others'
  activity is unknown, and nothing is inferred: a warning says so);
- exactly one melodic part (a wind or a string; the rhythm section and the
  vocals are not counted) plays the stretch, and at least MIN_RESTING others
  rest through it, none of them half-playing or unreadable there;
- at least MIN_ACTIVE of the resting parts play in another stretch, so the
  silence is a contrast and not an arrangement for one lone wind;
- the score marks nothing in the stretch (no solo, feature or vocal lead): a
  marked feature is never duplicated or overruled (ADR 0004), and a wind over a
  vocal lead is a backing, not a solo.

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
COVERAGE = 0.75  # a part is known in a stretch when its bars cover this share of it
PLAY_SHARE = 0.5  # a part plays a stretch when it is not inside a multi-bar rest for this share of it
REST_SHARE = 0.75  # ... and rests it when a multi-bar rest covers this share
MIN_RESTING = 3  # fewer resting parts than this is a small group playing, not a wind alone
MIN_ACTIVE = 2  # of the resting parts, this many play somewhere else in the song
INFERRED_CONFIDENCE = round(LOW_CONFIDENCE - 0.3, 2)  # 0.5: well under the flow draft's TODO threshold

PLAY, REST, MIXED, UNKNOWN = "plays", "rests", "partly plays", "unknown"


@dataclass
class _Player:
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
        """Whether the part plays, rests or half-plays the bars, or its bars there are not read."""
        playing = sum(b in self.played for b in bars)
        resting = sum(b in self.rested and b not in self.played for b in bars)
        if playing + resting < COVERAGE * len(bars):
            return UNKNOWN
        if resting >= REST_SHARE * len(bars):
            return REST
        return PLAY if playing >= PLAY_SHARE * len(bars) else MIXED


def _player_of(part: PartReport) -> _Player | None:
    hit = resolve(part.part.instrument) if part.part.instrument else None
    return _Player(part) if is_readable(part) and hit and hit.family in MELODIC else None


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
    return [m for m in score.marks if m.bar is not None and m.end is not None and m.end - m.bar >= MIN_SECTION_BARS]


def _marked(f: Feature, m: ScoreMark, score: ScoreMap) -> bool:
    """Whether the score has a feature in the section (of any kind: a vocal lead counts)."""
    if f.bar is not None and m.bar <= f.bar < m.end:
        return True
    return f.rehearsal_mark == m.text and score.in_force(f.rehearsal_mark, f.bar) is m


def _feature(lone: _Player, m: ScoreMark, resting: int) -> Feature:
    chairs = lone.part.part.chairs
    return Feature(
        kind="solo", instrument=lone.name, page=m.page, bar=m.bar, rehearsal_mark=m.text,
        raw_text="", confidence=INFERRED_CONFIDENCE,
        reasons=[
            f"inferred from the other parts resting, not marked in the score: the {lone.name} part plays "
            f"mark {m.text} (bars {m.bar}-{m.end - 1}) while {resting} other parts rest"
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
    missing = uncovered(instrumentation, parts.parts)
    if missing:
        return features, [
            f"unmarked solos not inferred: no readable part for {', '.join(missing)}, so who plays is unknown"
        ]
    players = [p for part in parts.parts if (p := _player_of(part))]
    states = [[p.status(range(m.bar, m.end)) for p in players] for m in sections]
    found: list[Feature] = []
    unread: list[str] = []
    for i, (m, status) in enumerate(zip(sections, states)):
        playing = [p for p, s in zip(players, status) if s == PLAY]
        resting = [(j, p) for j, (p, s) in enumerate(zip(players, status)) if s == REST]
        others = len(resting) + status.count(UNKNOWN)  # a part whose bars are not read might rest
        if len(playing) != 1 or others < MIN_RESTING or any(_marked(f, m, score) for f in features):
            continue
        if UNKNOWN in status:
            unread.append(m.text)
            continue
        if MIXED in status:  # a part that half plays is no clean rest
            continue
        active = sum(any(states[k][j] == PLAY for k in range(len(sections)) if k != i) for j, _ in resting)
        if active >= MIN_ACTIVE:
            found.append(_feature(playing[0], m, len(resting)))
    warnings = []
    if unread:
        warnings.append(
            f"unmarked solos not inferred at mark{'s' if len(unread) > 1 else ''} {', '.join(unread)}: "
            "the bars of some parts could not be read there"
        )
    for f in found:
        insert_in_score_order(features, f)
    return features, warnings
