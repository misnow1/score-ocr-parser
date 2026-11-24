"""Cross-reference part solos into the score's features (ADR 0004, `--parts-dir`).

The score stays the structure (sections, order, pages); a part supplies who plays
what. Each part solo is matched to a score feature by rehearsal mark first and
bar second (the score's sections are the ranges between its mark printings, so a
reused letter is told apart by bar), and then:

- a feature that already names the part's instrument is confirmed, under any
  mark when the bars are close (a part may letter a section differently), and a
  chair is filled in; two chairs that both carry it are both named;
- an open feature (a "(SOLOS)" over every staff, no instrument) or a feature
  found from parts gets the instrument and chair as a soloist; a shared feature
  takes further soloists;
- a solo at a mark the score prints, in that mark's bar range and with no feature
  there, is added as a feature found only in a part, on the page of its bar.

Real parts are noisy, so a part solo is trusted only where it matches the
score: its solos are de-duplicated, the mark must be one the score prints and
its bar must lie in that mark's range, the instrument must be one the score
has, and a vocal part or one with more than MAX_PART_SOLOS solos of its own never
names a soloist or adds a feature (it can only confirm one the score already
names). A solo that OPEN_MIN_PARTS or more parts mark in one place is the whole
band's: it stays an open feature and names no one. A "<instrument> solo" cue
printed in another part is supporting evidence for that instrument's feature,
never a solo of the part's own instrument. Everything not trusted, and every
score feature a present part does not carry, becomes a warning: nothing is
dropped silently.
"""

from dataclasses import dataclass, field
from functools import cache

from .flow import LOW_CONFIDENCE
from .instruments import present_as, resolve
from .models import Feature, InstrumentEntry, Location, Participant, PartReport, PartsReport, ScoreMap

# Bar windows. A part and the score count bars independently (repeats, rests,
# cues), so a few bars of drift are normal; a section is told by its mark first.
NEAR_BARS = 4  # part solos this close at one mark are one solo; also "another instrument's solo is there"
NAMED_WINDOW = 10  # a part solo this close to a score feature naming its instrument is that solo, under any mark
OPEN_WINDOW = 4  # ... this close to an open or shared feature of another mark, it is that feature's
# A named soloist set is rarely more than four players (a section of four chairs
# at most). Five or more parts marking one solo is the band's open solo, not
# five soloists, so it stays open.
OPEN_MIN_PARTS = 5
# A real part has a solo or two; a lyrics-heavy part (vocal score, piano on the
# vocal lines) reads as dozens, and more than this is noise.
MAX_PART_SOLOS = 4
PART_NAMED = 0.3  # evidence: the soloist comes from a part, like a name in the marking's text
OPEN_NAMED_CAP = round(LOW_CONFIDENCE - 0.05, 2)  # part evidence never lifts an open feature past the flow draft's TODO
FOUND_IN_PART = 0.7  # confidence of a feature only a part shows (below the flow draft's TODO threshold)
_UNREADABLE = ("could not be read", "no staves found")


@dataclass
class Claim:
    """One de-duplicated solo of one part, for the part's own instrument."""

    part: PartReport
    index: int  # of the part in the parts report
    feature: Feature
    instrument: str
    chair: int | None
    ambiguous: bool
    noise: str | None  # why the part's solos are not to be trusted to name or add soloists
    band: bool = False  # OPEN_MIN_PARTS or more parts mark a solo at this mark and bar

    @property
    def mark(self) -> str | None:
        return self.feature.rehearsal_mark

    @property
    def bar(self) -> int | None:
        return self.feature.bar

    @property
    def untrusted(self) -> str | None:
        """Why this part's solos can only confirm, never name or add a soloist."""
        if _is_vocal(self.part):
            return "a vocal part's solo markings are trusted only where the score names the voice"
        return self.noise

    @property
    def where(self) -> str:
        return _where(self.feature)

    @property
    def who(self) -> Participant:
        return Participant(self.instrument, self.chair, self.ambiguous)


@cache
def _vocal_name(instrument: str | None) -> bool:
    hit = resolve(instrument) if instrument else None
    return hit is not None and hit.family == "Vocal"


def _is_vocal(part: PartReport) -> bool:
    """A vocal part, or the accompaniment in a vocal player slot (the vocal score)."""
    info = part.part
    return _vocal_name(info.instrument) or (info.relation == "doubling" and _vocal_name(info.slot_instrument))


def _names(part: PartReport) -> list[str]:
    return [n for n in (part.part.instrument, *part.part.also) if n]


def _readable(part: PartReport) -> bool:
    return bool(part.part.instrument) and not any(w.startswith(_UNREADABLE) for w in part.warnings)


def distinct_solos(features: list[Feature]) -> list[Feature]:
    """A part's solos without repeats: the same kind, mark and bar once, and a
    solo with no bar dropped when another at that page and mark has one."""
    barred = {(f.page, f.rehearsal_mark) for f in features if f.bar is not None}
    seen: set[tuple] = set()
    kept = []
    for f in features:
        if f.bar is None and (f.page, f.rehearsal_mark) in barred:
            continue
        key = (f.kind, f.rehearsal_mark, f.bar, f.page if f.bar is None else None)
        if key not in seen:
            seen.add(key)
            kept.append(f)
    return kept


def _where(f: Feature) -> str:
    """"mark A, bar 9": where a feature is, short."""
    found = ([f"mark {f.rehearsal_mark}"] if f.rehearsal_mark else []) + ([f"bar {f.bar}"] if f.bar is not None else [])
    return ", ".join(found) or f"page {f.page}"


def _noise(solos: list[Feature]) -> str | None:
    """Why a part's own distinct solos read as noise: far too many."""
    if len(solos) > MAX_PART_SOLOS:
        return f"the part has too many solos ({len(solos)}) to be trusted to name or add soloists"
    return None


def _claim_of(part: PartReport, index: int, feature: Feature, noise: str | None) -> Claim:
    chairs = part.part.chairs
    chair = chairs[0] if len(chairs) == 1 else None
    return Claim(part, index, feature, part.part.instrument or "", chair, len(chairs) > 1, noise)


def _gap(bar: int | None, other: int | None) -> int | None:
    return abs(bar - other) if bar is not None and other is not None else None


def _within(f: Feature, bar: int | None, window: int) -> bool:
    """Bars known on both sides and no further apart than `window`."""
    gap = _gap(f.bar, bar)
    return gap is not None and gap <= window


def _nearest(features: list[Feature], bar: int | None) -> Feature:
    """The feature closest in bar (the first, in score order, when bars are unknown)."""
    return min(features, key=lambda f: (_gap(f.bar, bar) if _gap(f.bar, bar) is not None else 10**6))


def _label(p: Participant) -> str:
    return f"{p.instrument} {p.chair}" if p.chair else p.instrument


def _mark_bands(claims: list[Claim]) -> None:
    """Flag the claims of every solo that OPEN_MIN_PARTS or more trusted parts
    mark at one mark (bars chained within NEAR_BARS): the band's solo."""
    by_mark: dict[str, list[Claim]] = {}
    for c in claims:
        if c.mark and c.bar is not None and not c.untrusted:
            by_mark.setdefault(c.mark, []).append(c)
    for group in by_mark.values():
        group.sort(key=lambda c: c.bar)
        cluster: list[Claim] = []
        for c in [*group, None]:
            if cluster and (c is None or c.bar - cluster[-1].bar > NEAR_BARS):
                if len({k.index for k in cluster}) >= OPEN_MIN_PARTS:
                    for k in cluster:
                        k.band = True
                cluster = []
            if c is not None:
                cluster.append(c)


@dataclass
class _CrossReference:
    features: list[Feature]
    parts: PartsReport
    score: ScoreMap
    known: list[str]  # the score's instruments, doublings included
    order: dict[str, int]  # an instrument's place in the score's staff order
    original: set[int] = field(default_factory=set)  # ids of the features the score showed
    soloists: dict[int, list[tuple[Participant, int]]] = field(default_factory=dict)  # open or added: who, by part
    extras: dict[int, list[tuple[Participant, int]]] = field(default_factory=dict)  # soloists a shared feature takes
    chaired: set[int] = field(default_factory=set)  # features whose chair a part filled in
    carried: dict[int, set[int]] = field(default_factory=dict)  # feature -> indices of the parts that carry it
    ignored: dict[tuple[int, str], list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.original = {id(f) for f in self.features}

    # -- who a feature names -------------------------------------------------
    def base(self, f: Feature) -> list[Participant]:
        return [Participant(f.instrument, f.chair, f.chair_ambiguous), *f.shared_with] if f.instrument else []

    def who(self, f: Feature) -> list[Participant]:
        named = [p for p, _ in self.soloists[id(f)]] if id(f) in self.soloists else self.base(f)
        return named + [p for p, _ in self.extras.get(id(f), [])]

    def names(self, f: Feature, c: Claim) -> Participant | None:
        return next((p for p in self.who(f) if present_as(c.instrument, [p.instrument])), None)

    def plausible(self, c: Claim) -> bool:
        info = c.part.part
        slot = [info.slot_instrument] if info.relation == "doubling" and info.slot_instrument else []
        return any(present_as(n, self.known) for n in [*_names(c.part), *slot])

    def is_open(self, f: Feature) -> bool:
        return id(f) in self.original and f.instrument is None and not f.shared_with

    def is_shared(self, f: Feature) -> bool:
        return id(f) in self.original and f.instrument is not None and bool(f.shared_with)

    # -- matching ----------------------------------------------------------------
    def here(self, f: Feature, c: Claim, section) -> bool:
        """The feature is in the section the claim's mark and bar point to."""
        return (
            section is not None
            and f.rehearsal_mark == c.mark
            and self.score.in_force(f.rehearsal_mark, f.bar) is section
        )

    def place(self, c: Claim) -> None:
        section = self.score.containing(c.mark, c.bar) if c.mark else None
        cands = [f for f in self.features if f.kind == c.feature.kind]
        confirming = [
            f for f in cands
            if self.names(f, c)
            and (
                _within(f, c.bar, NEAR_BARS) if id(f) not in self.original
                else self.here(f, c, section) or _within(f, c.bar, NAMED_WINDOW)
            )
        ]
        if confirming:
            return self.confirm(_nearest(confirming, c.bar), c)
        if c.untrusted:
            return self.ignore(c, c.untrusted)
        if not self.plausible(c):
            return self.ignore(c, f"{c.instrument} is not in the score's instrumentation")
        opened = [
            f for f in cands if self.is_open(f)
            and (
                f.rehearsal_mark == c.mark if c.band
                else self.here(f, c, section) or _within(f, c.bar, OPEN_WINDOW)
            )
        ]
        found = [f for f in cands if id(f) in self.soloists and id(f) not in self.original and _within(f, c.bar, NEAR_BARS)]
        if opened or found:
            return self.join(_nearest(opened or found, c.bar), c)
        shared = [f for f in cands if self.is_shared(f) and (self.here(f, c, section) or _within(f, c.bar, OPEN_WINDOW))]
        if shared:
            return self.take(_nearest(shared, c.bar), c)
        taken = [f for f in cands if self.who(f) and _within(f, c.bar, NEAR_BARS)]
        if taken:
            who = " and ".join(_label(p) for p in self.who(taken[0]))
            return self.ignore(c, f"the score marks the {who} solo there, not {c.instrument}")
        self.add(c, section)

    def ignore(self, c: Claim, reason: str) -> None:
        self.ignored.setdefault((c.index, reason), []).append(c.where)

    # -- what a match does ---------------------------------------------------------
    def evidence(self, f: Feature, c: Claim, what: str) -> None:
        part = f"{c.instrument} part (part page {c.feature.page}" + (f", bar {c.bar})" if c.bar is not None else ")")
        reason = f"{what} {part}"
        if reason not in f.reasons:
            f.reasons.append(reason)
        self.carried.setdefault(id(f), set()).add(c.index)

    def confirm(self, f: Feature, c: Claim) -> None:
        self.evidence(f, c, "carried by the")
        if id(f) in self.soloists:
            return self.name(f, c)
        if not c.chair or c.ambiguous:
            return
        mine = [p for p in self.base(f) if present_as(c.instrument, [p.instrument])]
        if any(p.chair == c.chair for p in mine):
            return
        blank = next((p for p in mine if p.chair is None or p.chair_ambiguous), None)
        if blank is not None:
            if any(blank is p for p in f.shared_with):
                blank.chair, blank.chair_ambiguous = c.chair, False
            else:
                f.chair, f.chair_ambiguous = c.chair, False
            self.chaired.add(id(f))
        elif id(f) in self.chaired:  # another chair also carries what the score names with none
            f.shared_with.append(Participant(c.instrument, c.chair))

    def name(self, f: Feature, c: Claim) -> None:
        soloists = self.soloists[id(f)]
        if not any(p.instrument == c.instrument and p.chair == c.chair for p, _ in soloists):
            soloists.append((c.who, c.index))
        else:  # the same player again: the part still counts toward who carries it
            soloists.append((next(p for p, _ in soloists if p.instrument == c.instrument and p.chair == c.chair), c.index))

    def join(self, f: Feature, c: Claim) -> None:
        self.soloists.setdefault(id(f), [])
        self.evidence(f, c, "soloist named by the")
        self.name(f, c)

    def take(self, f: Feature, c: Claim) -> None:
        """A shared feature takes one more soloist."""
        self.evidence(f, c, "another soloist, from the")
        extras = self.extras.setdefault(id(f), [])
        if not any(p.instrument == c.instrument and p.chair == c.chair for p, _ in extras):
            extras.append((c.who, c.index))

    def add(self, c: Claim, section) -> None:
        if c.mark is None:
            return self.ignore(c, "no rehearsal mark and no score solo near its bar")
        if not self.score.sections(c.mark):
            return self.ignore(c, f"{c.mark} is not a rehearsal mark of the score")
        if c.bar is None:
            return self.ignore(c, "no bar to place it by")
        if section is None:
            return self.ignore(c, f"its bar is outside the range of mark {c.mark} in the score")
        found = c.feature
        page = self.score.page_of(c.bar, section.page)
        f = Feature(
            kind=found.kind, instrument=c.instrument, page=page, bar=c.bar, rehearsal_mark=c.mark,
            raw_text=found.raw_text, confidence=min(found.confidence, FOUND_IN_PART),
            reasons=[f"found only in the {c.instrument} part: the score marks no {found.kind} at mark {c.mark}"],
            locations=[Location(page, c.bar)], chair=c.chair, chair_ambiguous=c.ambiguous,
        )
        self.soloists[id(f)] = [(c.who, c.index)]
        self.evidence(f, c, "marked in the")
        key = (page, c.bar)
        after = [i for i, g in enumerate(self.features) if (g.page, g.bar if g.bar is not None else 10**6) <= key]
        self.features.insert(after[-1] + 1 if after else 0, f)

    # -- the whole pass --------------------------------------------------------------
    def claims(self) -> list[Claim]:
        found = []
        for index, part in enumerate(self.parts.parts):
            if not _readable(part):
                continue
            own = [
                f for f in distinct_solos(part.features)
                if f.kind != "vocal lead" and (f.instrument is None or present_as(f.instrument, _names(part)))
            ]
            found += [_claim_of(part, index, f, _noise(own)) for f in own]
        _mark_bands(found)
        return sorted(found, key=lambda c: (self.order.get(c.instrument, 10**6), c.chair or 0, c.index))

    def cues(self) -> None:
        """A '<X> solo' cue printed in another part supports X's feature."""
        for part in self.parts.parts:
            if not _readable(part):
                continue
            for f in distinct_solos(part.features):
                if f.kind == "vocal lead" or f.instrument is None or present_as(f.instrument, _names(part)):
                    continue
                for feature in self.features:
                    if (
                        id(feature) in self.original and feature.kind == f.kind
                        and any(present_as(f.instrument, [p.instrument]) for p in self.who(feature))
                        and (f.rehearsal_mark == feature.rehearsal_mark or _within(feature, f.bar, NEAR_BARS))
                    ):
                        reason = f"a '{f.instrument} solo' cue is printed in the {part.part.instrument} part (part page {f.page})"
                        if reason not in feature.reasons:
                            feature.reasons.append(reason)

    def uncarried(self) -> None:
        """Score features naming an instrument whose part is present but does not carry them."""
        for f in self.features:
            if id(f) not in self.original or f.kind == "vocal lead":
                continue
            for p in self.base(f):
                present = [
                    i for i, part in enumerate(self.parts.parts)
                    if _readable(part) and present_as(p.instrument, _names(part))
                    and (p.chair is None or not part.part.chairs or p.chair in part.part.chairs)
                ]
                if present and not set(present) & self.carried.get(id(f), set()):
                    self.warnings.append(
                        f"the score marks a {_label(p)} {f.kind} ({_where(f)}) that the {p.instrument} part does not carry"
                    )

    def finish(self) -> None:
        """Soloists found from parts become the feature's instrument and the others
        it is shared with, unless the band marks it: then it stays open."""
        for f in self.features:
            soloists = self.soloists.get(id(f))
            if soloists:
                players = {i for _, i in soloists}
                if len(players) >= OPEN_MIN_PARTS:
                    self.keep_open(f, len(players))
                else:
                    self.apply(f, [p for p, _ in soloists])
            extras = self.extras.get(id(f))
            if extras:
                total = len(self.base(f)) + len({(p.instrument, p.chair) for p, _ in extras})
                if total >= OPEN_MIN_PARTS:
                    for p, i in extras:
                        self.ignore_extra(f, p, i)
                else:
                    f.shared_with += [p for p, _ in extras]
        for (index, reason), where in self.ignored.items():
            n = len(where)
            self.warnings.append(
                f"part {self.parts.parts[index].file}: ignored {n} solo{'s' if n > 1 else ''} ({', '.join(where)}): {reason}"
            )

    def apply(self, f: Feature, who: list[Participant]) -> None:
        first, *rest = who
        f.instrument, f.chair, f.chair_ambiguous = first.instrument, first.chair, first.chair_ambiguous
        f.shared_with = rest
        if id(f) in self.original:  # an open feature: named by parts, still worth a look in the flow draft
            f.confidence = max(f.confidence, min(round(f.confidence + PART_NAMED, 2), OPEN_NAMED_CAP))

    def keep_open(self, f: Feature, players: int) -> None:
        f.reasons.append(f"{players} parts mark a solo here: the band's open solo, no one is named")
        if id(f) not in self.original:
            f.instrument, f.chair, f.chair_ambiguous, f.shared_with = None, None, False, []

    def ignore_extra(self, f: Feature, p: Participant, index: int) -> None:
        self.warnings.append(
            f"part {self.parts.parts[index].file}: not added to the shared feature ({_where(f)}): "
            f"it already names {len(self.base(f))} instruments, so more are the band's"
        )


def cross_reference(
    features: list[Feature], parts: PartsReport, score: ScoreMap, instrumentation: list[InstrumentEntry]
) -> tuple[list[Feature], list[str]]:
    """(the score's features with the part solos merged in, warnings for every
    disagreement). The features keep the score's order."""
    known = [n for e in instrumentation for n in (e.instrument, *e.doublings)]
    order = {e.instrument: i for i, e in enumerate(instrumentation)}
    run = _CrossReference(list(features), parts, score, known, order)
    for claim in run.claims():
        run.place(claim)
    run.cues()
    run.uncarried()
    run.finish()
    return run.features, run.warnings
