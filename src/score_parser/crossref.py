"""Cross-reference part solos into the score's features (ADR 0004, `--parts-dir`).

The score stays the structure (sections, order, pages); a part supplies who plays
what. Each part solo is matched to a score feature by rehearsal mark first and bar
second. The score's sections are the bar ranges between its mark printings (a
reused letter is told apart by bar), and a part solo belongs to the section its
mark and bar point to. In two passes, the claim's own section first:

1. in its own section, a solo confirms a feature that names its instrument, names
   the soloist of an open feature, or is another soloist of a shared feature;
2. a solo that found nothing there may match under another mark, within a bar
   window (a part may letter a section differently), but never a feature the same
   part already carries from its own section: that is another solo. When the
   solo agrees with a section of the score, a match into another section is a
   warning.

What is left is added as a feature found only in a part when the part's mark is
printed in the score and its bar lies in that mark's range; the solos are
clustered first (bars within NEAR_BARS, whatever the order of the parts), then the
cluster is one feature: open when OPEN_MIN_PARTS or more parts mark it, else named.

Real parts are noisy, so a part solo is trusted only where it matches the
score: its solos are de-duplicated, the mark must be one the score prints and
its bar must lie in that mark's range, the instrument must be one the score
has, and a vocal part or one with more than MAX_PART_SOLOS solos of its own never
names a soloist or adds a feature (it can only confirm one the score already
names). A solo that OPEN_MIN_PARTS or more parts mark in one place is the whole
band's: it stays an open feature and names no one. A named solo has at most
MAX_NAMED players (each chair of an instrument is a player). A "<instrument>
solo" cue printed in another part is supporting evidence for that instrument's
feature, never a solo of the part's own instrument. Everything not trusted, and
every score feature a present part does not carry, becomes a warning: nothing is
dropped silently.
"""

from dataclasses import dataclass, field
from functools import cache

from .flow import LOW_CONFIDENCE
from .instruments import present_as, resolve
from .models import Feature, InstrumentEntry, Location, Participant, PartReport, PartsReport, ScoreMap, ScoreMark

# Bar windows. A part and the score count bars independently (repeats, rests,
# cues), so a few bars of drift are normal; a section is told by its mark first.
NEAR_BARS = 4  # part solos this close at one mark are one solo; also "another instrument's solo is there", and the slack before a mark's first bar
NAMED_WINDOW = 10  # a part solo this close to a score feature naming its instrument is that solo, under another mark
OPEN_WINDOW = 4  # ... this close to an open or shared feature of another mark, it is that feature's
# A named soloist set is rarely more than four players (a section of four chairs
# at most). Five or more parts marking one solo is the band's open solo, not
# five soloists, so it stays open.
OPEN_MIN_PARTS = 5
MAX_NAMED = OPEN_MIN_PARTS - 1  # players (instrument and chair each) a named or shared feature may hold
# A real part has a solo or two; a lyrics-heavy part (vocal score, piano on the
# vocal lines) reads as dozens, and more than this is noise.
MAX_PART_SOLOS = 4
MAX_REASONS = 3  # a feature lists the parts that carry it by name up to this many; more are one reason with a count
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
    section: ScoreMark | None = None  # the score section its mark and bar point to
    band: bool = False  # OPEN_MIN_PARTS or more parts mark a solo at this mark, bars chained within NEAR_BARS

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

    @property
    def player(self) -> tuple[str, int | None]:
        return (self.instrument, self.chair)


@cache
def _vocal_name(instrument: str | None) -> bool:
    hit = resolve(instrument) if instrument else None
    return hit is not None and hit.family == "Vocal"


def _is_vocal(part: PartReport) -> bool:
    """A vocal part, or the accompaniment in a vocal player slot (the vocal score)."""
    info = part.part
    return _vocal_name(info.instrument) or (info.relation == "doubling" and _vocal_name(info.slot_instrument))


def part_names(part: PartReport) -> list[str]:
    return [n for n in (part.part.instrument, *part.part.also) if n]


def is_readable(part: PartReport) -> bool:
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


def _clusters(claims: list[Claim], key) -> list[list[Claim]]:
    """Group claims by `key`, then chain each group's claims whose bars are within
    NEAR_BARS of the one before (single linkage, so the order of the parts does
    not matter). Claims with no bar are left out."""
    groups: dict[object, list[Claim]] = {}
    for c in claims:
        if c.bar is not None:
            groups.setdefault(key(c), []).append(c)
    out = []
    for group in groups.values():
        group.sort(key=lambda c: c.bar)
        cluster: list[Claim] = []
        for c in group:
            if cluster and c.bar - cluster[-1].bar > NEAR_BARS:
                out.append(cluster)
                cluster = []
            cluster.append(c)
        out.append(cluster)
    return out


def _mark_bands(claims: list[Claim]) -> None:
    """Flag the claims of every solo that OPEN_MIN_PARTS or more trusted parts
    mark at one mark (bars chained within NEAR_BARS): the band's solo."""
    trusted = [c for c in claims if c.mark and not c.untrusted]
    for cluster in _clusters(trusted, lambda c: c.mark):
        if len({c.index for c in cluster}) >= OPEN_MIN_PARTS:
            for c in cluster:
                c.band = True


def insert_in_score_order(features: list[Feature], f: Feature) -> None:
    """Put a feature a part showed into the score's features in score order
    (ADR 0003): by page, then bar; a feature with no bar follows the barred ones on its page."""
    after = [i for i, g in enumerate(features) if (g.page, g.bar is None, g.bar or 0) <= (f.page, False, f.bar or 0)]
    features.insert(after[-1] + 1 if after else 0, f)


@dataclass
class _CrossReference:
    features: list[Feature]
    parts: PartsReport
    score: ScoreMap
    known: list[str]  # the score's instruments, doublings included
    order: dict[str, int]  # an instrument's place in the score's staff order
    original: set[int] = field(default_factory=set)  # ids of the features the score showed
    joined: dict[int, list[Claim]] = field(default_factory=dict)  # open feature -> the part solos that name its soloists
    extras: dict[int, list[Participant]] = field(default_factory=dict)  # soloists a shared feature took
    chaired: set[int] = field(default_factory=set)  # features whose chair a part filled in
    carried: dict[int, set[int]] = field(default_factory=dict)  # feature -> indices of the parts that carry it
    proof: dict[int, list[tuple[str, Claim]]] = field(default_factory=dict)  # feature -> (what, claim) for its reasons
    ignored: dict[tuple[int, str], list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.original = {id(f) for f in self.features}

    # -- who a feature names -------------------------------------------------
    def base(self, f: Feature) -> list[Participant]:
        return [Participant(f.instrument, f.chair, f.chair_ambiguous), *f.shared_with] if f.instrument else []

    def who(self, f: Feature) -> list[Participant]:
        """Everyone the feature names so far: the score's, the parts' joined soloists, the extras taken."""
        named = self.base(f)
        for c in self.joined.get(id(f), []):
            if not any((p.instrument, p.chair) == c.player for p in named):
                named.append(c.who)
        return named + self.extras.get(id(f), [])

    def names(self, f: Feature, c: Claim) -> Participant | None:
        return next((p for p in self.who(f) if present_as(c.instrument, [p.instrument])), None)

    def plausible(self, c: Claim) -> bool:
        info = c.part.part
        slot = [info.slot_instrument] if info.relation == "doubling" and info.slot_instrument else []
        return any(present_as(n, self.known) for n in [*part_names(c.part), *slot])

    def is_open(self, f: Feature) -> bool:
        return id(f) in self.original and f.instrument is None and not f.shared_with

    def is_shared(self, f: Feature) -> bool:
        return id(f) in self.original and f.instrument is not None and bool(f.shared_with)

    # -- matching ----------------------------------------------------------------
    def reach(self, f: Feature, c: Claim, bars: int | None) -> bool:
        """Whether the claim points at the feature: in the claim's own section
        (`bars` None), or, for a feature of another mark, within `bars` bars and
        not one the same part already carries."""
        if bars is None:
            return (
                c.section is not None
                and f.rehearsal_mark == c.mark
                and self.score.in_force(f.rehearsal_mark, f.bar) is c.section
            )
        return _within(f, c.bar, bars) and c.index not in self.carried.get(id(f), ())

    def match(self, c: Claim, across_marks: bool) -> bool:
        """Confirm, name or share a score feature, in the claim's own section or
        (`across_marks`) near its bar under another mark; True when it found one."""
        cands = [f for f in self.features if f.kind != "vocal lead"]

        def bars(window: int) -> int | None:
            return window if across_marks else None

        confirming = [f for f in cands if self.names(f, c) and self.reach(f, c, bars(NAMED_WINDOW))]
        if confirming:
            self.hit(self.confirm, _nearest(confirming, c.bar), c, across_marks)
            return True
        if c.untrusted or not self.plausible(c):
            return False
        if c.band and not across_marks and c.section is None:  # bars the score cannot place: the mark's open solo
            opened = [f for f in cands if self.is_open(f) and f.rehearsal_mark == c.mark]
        else:
            opened = [f for f in cands if self.is_open(f) and self.reach(f, c, bars(OPEN_WINDOW))]
        if opened:
            self.hit(self.join, _nearest(opened, c.bar), c, across_marks)
            return True
        shared = [f for f in cands if self.is_shared(f) and self.reach(f, c, bars(OPEN_WINDOW))]
        if shared:
            self.hit(self.take, _nearest(shared, c.bar), c, across_marks)
            return True
        return False

    def hit(self, action, f: Feature, c: Claim, across_marks: bool) -> None:
        """Apply what a match does, and note that the claim's part carries the feature.
        A match from a section of the score into a feature of another is a warning."""
        action(f, c)
        self.carried.setdefault(id(f), set()).add(c.index)
        if across_marks and c.section is not None:
            who = " and ".join(_label(p) for p in self.who(f)) or "open"
            self.warnings.append(
                f"part {c.part.file}: its solo ({c.where}) was matched to the score's {who} solo "
                f"({_where(f)}) across a section boundary: check that it is the same solo"
            )

    def unmatched(self, c: Claim) -> str | None:
        """Why a claim that found no score feature cannot be added, or None when it can."""
        if c.untrusted:
            return c.untrusted
        if not self.plausible(c):
            return f"{c.instrument} is not in the score's instrumentation"
        cands = [
            f for f in self.features
            if f.kind != "vocal lead" and _within(f, c.bar, NEAR_BARS)
            and self.base(f) and not any(present_as(c.instrument, [p.instrument]) for p in self.base(f))
        ]
        if cands:
            f = _nearest(cands, c.bar)
            who = " and ".join(_label(p) for p in self.base(f))
            return f"the score marks the {who} solo ({_where(f)}) there, not {c.instrument}"
        if c.mark is None:
            return "no rehearsal mark and no score solo near its bar"
        if not self.score.sections(c.mark):
            return f"{c.mark} is not a rehearsal mark of the score"
        if c.bar is None:
            return "no bar to place it by"
        if c.section is None:
            return f"its bar is outside the range of mark {c.mark} in the score"
        return None

    def ignore(self, c: Claim, reason: str) -> None:
        self.ignored.setdefault((c.index, reason), []).append(c.where)

    # -- what a match does ---------------------------------------------------------
    def evidence(self, f: Feature, c: Claim, what: str) -> None:
        """Remember that a part's solo supports the feature; `finish` writes the reasons."""
        self.proof.setdefault(id(f), []).append((what, c))

    def confirm(self, f: Feature, c: Claim) -> None:
        if id(f) in self.joined:
            return self.join(f, c)
        mine = [p for p in self.base(f) if present_as(c.instrument, [p.instrument])]
        if not mine:  # named by an extra soloist: another chair of it is another extra
            return self.take(f, c)
        self.evidence(f, c, "carried by the")
        if not c.chair or c.ambiguous or any(p.chair == c.chair for p in mine):
            return
        blank = next((p for p in mine if p.chair is None or p.chair_ambiguous), None)
        if blank is not None:
            if any(blank is p for p in f.shared_with):
                blank.chair, blank.chair_ambiguous = c.chair, False
            else:
                f.chair, f.chair_ambiguous = c.chair, False
            self.chaired.add(id(f))
        elif id(f) in self.chaired:  # another chair also carries what the score names with none
            self.take(f, c)

    def join(self, f: Feature, c: Claim) -> None:
        """An open feature's soloist, kept until the whole picture is known (finish)."""
        self.joined.setdefault(id(f), []).append(c)

    def take(self, f: Feature, c: Claim) -> None:
        """A shared feature takes one more soloist, while it has room."""
        here = self.who(f)
        if any((p.instrument, p.chair) == c.player for p in here):
            return
        if len(here) >= MAX_NAMED:
            self.warnings.append(
                f"part {c.part.file}: not added to the shared feature ({_where(f)}): it already names {len(here)} "
                f"players, the most a named solo has ({MAX_NAMED}); more are the band's"
            )
            return
        self.evidence(f, c, "another soloist, from the")
        self.extras.setdefault(id(f), []).append(c.who)

    def add(self, group: list[Claim]) -> None:
        """One feature found only in parts, from claims at one mark and place."""
        first = min(group, key=lambda c: (c.bar, self.order.get(c.instrument, 10**6)))
        section = first.section
        players = sorted({c.player for c in group}, key=lambda p: (self.order.get(p[0], 10**6), p[1] or 0))
        # A bar a little before the mark's first bar (the slack) is placed at the mark's first bar, so the
        # feature stays inside its section in score order (ADR 0003).
        bar = max(first.bar, section.bar) if section.bar is not None else first.bar
        page = self.score.page_of(bar, section.page)
        kind = first.feature.kind
        names = ", ".join(sorted({c.instrument for c in group}, key=lambda n: self.order.get(n, 10**6)))
        band = len({c.index for c in group}) >= OPEN_MIN_PARTS
        who = None if band else [next(c.who for c in group if c.player == p) for p in players]
        f = Feature(
            kind=kind, instrument=who[0].instrument if who else None, page=page, bar=bar,
            rehearsal_mark=first.mark, raw_text=first.feature.raw_text,
            confidence=min(first.feature.confidence, FOUND_IN_PART),
            reasons=[
                f"found only in parts: the score marks no {kind} at mark {first.mark}"
                + (f"; {len({c.index for c in group})} parts mark it: the band's open solo, no one is named" if band else f" ({names})")
            ]
            + ([f"the part reads bar {first.bar}, before the mark's first bar: placed at bar {bar}"] if bar != first.bar else []),
            locations=[Location(page, bar)],
            chair=who[0].chair if who else None, chair_ambiguous=who[0].chair_ambiguous if who else False,
            shared_with=who[1:] if who else [],
        )
        insert_in_score_order(self.features, f)

    # -- the whole pass --------------------------------------------------------------
    def claims(self) -> list[Claim]:
        found = []
        for index, part in enumerate(self.parts.parts):
            if not is_readable(part):
                continue
            own = [
                f for f in distinct_solos(part.features)
                if f.kind != "vocal lead" and (f.instrument is None or present_as(f.instrument, part_names(part)))
            ]
            found += [_claim_of(part, index, f, _noise(own)) for f in own]
        for c in found:
            c.section = self.score.containing(c.mark, c.bar, NEAR_BARS) if c.mark else None
        _mark_bands(found)
        return sorted(found, key=lambda c: (self.order.get(c.instrument, 10**6), c.chair or 0, c.index))

    def run(self) -> None:
        claims = self.claims()
        left = [c for c in claims if not self.match(c, across_marks=False)]
        left = [c for c in left if not self.match(c, across_marks=True)]
        pending = []
        for c in left:
            reason = self.unmatched(c)
            if reason:
                self.ignore(c, reason)
            else:
                pending.append(c)
        for group in _clusters(pending, lambda c: (c.mark, id(c.section))):
            self.add(group)
        self.cues()
        self.uncarried()
        self.finish()

    def cues(self) -> None:
        """A '<X> solo' cue printed in another part supports X's feature."""
        for part in self.parts.parts:
            if not is_readable(part):
                continue
            for f in distinct_solos(part.features):
                if f.kind == "vocal lead" or f.instrument is None or present_as(f.instrument, part_names(part)):
                    continue
                for feature in self.features:
                    if (
                        id(feature) in self.original and feature.kind != "vocal lead"
                        and any(present_as(f.instrument, [p.instrument]) for p in self.base(feature))
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
                    if is_readable(part) and present_as(p.instrument, part_names(part))
                    and (p.chair is None or not part.part.chairs or p.chair in part.part.chairs)
                ]
                if present and not set(present) & self.carried.get(id(f), set()):
                    self.warnings.append(
                        f"the score marks a {_label(p)} {f.kind} ({_where(f)}) that the {p.instrument} part does not carry"
                    )

    def finish(self) -> None:
        """Soloists parts named on an open feature become its instrument and the others
        it is shared with, unless the band marks it: then it stays open."""
        for f in self.features:
            claims = self.joined.get(id(f))
            if claims:
                players = {c.index for c in claims}
                if len(players) >= OPEN_MIN_PARTS:
                    f.reasons.append(f"{len(players)} parts mark a solo here: the band's open solo, no one is named")
                else:
                    self.apply(f, claims)
            if self.extras.get(id(f)):
                f.shared_with += self.extras[id(f)]
        for f in self.features:
            self.write_reasons(f)
        for (index, reason), where in self.ignored.items():
            n = len(where)
            self.warnings.append(
                f"part {self.parts.parts[index].file}: ignored {n} solo{'s' if n > 1 else ''} ({', '.join(where)}): {reason}"
            )

    def write_reasons(self, f: Feature) -> None:
        """The parts' evidence as reasons: one line per part, or one line with a
        count when many parts carry the feature."""
        by_what: dict[str, list[Claim]] = {}
        for what, c in self.proof.get(id(f), []):
            by_what.setdefault(what, []).append(c)
        for what, claims in by_what.items():
            parts = {c.index: c for c in claims}.values()
            if len(parts) > MAX_REASONS:
                f.reasons.append(f"{what} {len(parts)} parts")
                continue
            for c in parts:
                bar = f", bar {c.bar}" if c.bar is not None else ""
                f.reasons.append(f"{what} {c.instrument} part (part page {c.feature.page}{bar})")

    def apply(self, f: Feature, claims: list[Claim]) -> None:
        who: list[Participant] = []
        for c in claims:
            self.evidence(f, c, "soloist named by the")
            if not any((p.instrument, p.chair) == c.player for p in who):
                who.append(c.who)
        first, *rest = who
        f.instrument, f.chair, f.chair_ambiguous = first.instrument, first.chair, first.chair_ambiguous
        f.shared_with = rest
        # An open feature named by parts is still worth a look in the flow draft.
        f.confidence = max(f.confidence, min(round(f.confidence + PART_NAMED, 2), OPEN_NAMED_CAP))


def cross_reference(
    features: list[Feature], parts: PartsReport, score: ScoreMap, instrumentation: list[InstrumentEntry]
) -> tuple[list[Feature], list[str]]:
    """(the score's features with the part solos merged in, warnings for every
    disagreement). The features keep the score's order."""
    known = [n for e in instrumentation for n in (e.instrument, *e.doublings)]
    order = {e.instrument: i for i, e in enumerate(instrumentation)}
    run = _CrossReference(list(features), parts, score, known, order)
    run.run()
    return run.features, run.warnings
