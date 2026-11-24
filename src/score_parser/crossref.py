"""Cross-reference part solos into the score's features (ADR 0004, `--parts-dir`).

The score stays the structure (sections, order); a part supplies who plays what.
Each part solo is matched to a score feature by rehearsal mark first and bar
second, and then:

- a feature that already names the part's instrument is confirmed (and a missing
  chair filled in);
- an open feature (a "(SOLOS)" over every staff, no instrument) or a feature
  found from parts gets the instrument and chair as a soloist;
- a solo at a mark the score prints, with no feature there, is added as a feature
  found only in a part.

Real parts are noisy, so a part solo is trusted only where it matches the
score: its solos are de-duplicated, the mark must be one the score prints, the
instrument must be one the score has, and a vocal part never names a soloist or
adds a feature (it can only confirm one the score already names). A
"<instrument> solo" cue printed in another part is supporting evidence for that
instrument's feature, never a solo of the part's own instrument. Everything
that is not trusted, and every score feature a present part does not carry,
becomes a warning: nothing is dropped silently.
"""

from dataclasses import dataclass, field
from functools import cache

from .instruments import present_as, resolve
from .models import Feature, InstrumentEntry, Location, Participant, PartReport, PartsReport, ScoreMark

NEAR_BARS = 4  # solos this close, at one mark, are one solo
OPEN_JOIN_BARS = 6  # a part solo this close to an open feature's bar names its soloist
MAX_PART_SOLOS = 4  # a part with more distinct solos than this is noise: it can only confirm
PART_NAMED = 0.3  # evidence: the soloist comes from a part, like a name in the marking's text
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
    """Why a part's distinct solos read as noise: far too many."""
    if len(solos) > MAX_PART_SOLOS:
        return f"the part has too many solos ({len(solos)}) to be trusted to name or add soloists"
    return None


def _claim_of(part: PartReport, index: int, feature: Feature, noise: str | None) -> Claim:
    chairs = part.part.chairs
    chair = chairs[0] if len(chairs) == 1 else None
    return Claim(part, index, feature, part.part.instrument or "", chair, len(chairs) > 1, noise)


def _gap(bar: int | None, other: int | None) -> int | None:
    return abs(bar - other) if bar is not None and other is not None else None


def _near(bar: int | None, other: int | None) -> bool:
    gap = _gap(bar, other)
    return gap is None or gap <= NEAR_BARS


def _nearest(features: list[Feature], bar: int | None) -> Feature:
    """The feature closest in bar (the first, in score order, when bars are unknown)."""
    return min(features, key=lambda f: (_gap(f.bar, bar) if _gap(f.bar, bar) is not None else 10**6))


def _label(p: Participant) -> str:
    return f"{p.instrument} {p.chair}" if p.chair else p.instrument


@dataclass
class _CrossReference:
    features: list[Feature]
    parts: PartsReport
    marks: dict[str, ScoreMark]
    known: list[str]  # the score's instruments, doublings included
    order: dict[str, int]  # an instrument's place in the score's staff order
    original: set[int] = field(default_factory=set)  # ids of the features the score showed
    from_parts: dict[int, list[Participant]] = field(default_factory=dict)  # soloists of open or added features
    carried: dict[int, set[int]] = field(default_factory=dict)  # feature -> indices of the parts that carry it
    ignored: dict[tuple[int, str], list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.original = {id(f) for f in self.features}

    # -- who a feature names -------------------------------------------------
    def who(self, f: Feature) -> list[Participant]:
        if id(f) in self.from_parts:
            return self.from_parts[id(f)]
        return [Participant(f.instrument, f.chair, f.chair_ambiguous), *f.shared_with] if f.instrument else []

    def names(self, f: Feature, c: Claim) -> Participant | None:
        return next((p for p in self.who(f) if present_as(c.instrument, [p.instrument])), None)

    def plausible(self, c: Claim) -> bool:
        info = c.part.part
        slot = [info.slot_instrument] if info.relation == "doubling" and info.slot_instrument else []
        return any(present_as(n, self.known) for n in [*_names(c.part), *slot])

    # -- matching ----------------------------------------------------------------
    def candidates(self, c: Claim) -> list[Feature]:
        same_kind = [f for f in self.features if f.kind == c.feature.kind]
        if c.mark is not None:
            return [f for f in same_kind if f.rehearsal_mark == c.mark]
        return [f for f in same_kind if _gap(f.bar, c.bar) is not None and _near(f.bar, c.bar)]

    def place(self, c: Claim) -> None:
        cands = self.candidates(c)
        confirming = [f for f in cands if self.names(f, c)]
        if confirming:
            return self.confirm(_nearest(confirming, c.bar), c)
        if c.untrusted:
            return self.ignore(c, c.untrusted)
        if not self.plausible(c):
            return self.ignore(c, f"{c.instrument} is not in the score's instrumentation")
        joinable = [
            f for f in cands
            if (id(f) in self.from_parts and _near(f.bar, c.bar))
            or (id(f) not in self.from_parts and f.instrument is None and not f.shared_with and self.close(f, c))
        ]
        if joinable:
            return self.join(_nearest(joinable, c.bar), c)
        taken = [f for f in cands if self.who(f) and _gap(f.bar, c.bar) is not None and _near(f.bar, c.bar)]
        if taken:
            who = " and ".join(_label(p) for p in self.who(taken[0]))
            return self.ignore(c, f"the score marks the {who} solo there, not {c.instrument}")
        if c.mark is None:
            return self.ignore(c, "no rehearsal mark and no score solo near its bar")
        if c.mark not in self.marks:
            return self.ignore(c, f"{c.mark} is not a rehearsal mark of the score")
        if c.bar is None:
            return self.ignore(c, "no bar to place it by")
        self.add(c)

    @staticmethod
    def close(f: Feature, c: Claim) -> bool:
        gap = _gap(f.bar, c.bar)
        return gap is None or gap <= OPEN_JOIN_BARS

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
        if id(f) in self.from_parts:
            return self.name(f, c)
        known = self.names(f, c)
        if known and c.chair and not c.ambiguous and (known.chair is None or known.chair_ambiguous):
            if any(known is p for p in f.shared_with):
                known.chair, known.chair_ambiguous = c.chair, False
            else:
                f.chair, f.chair_ambiguous = c.chair, False

    def name(self, f: Feature, c: Claim) -> None:
        soloists = self.from_parts[id(f)]
        if not any(p.instrument == c.instrument and p.chair == c.chair for p in soloists):
            soloists.append(c.who)

    def join(self, f: Feature, c: Claim) -> None:
        if id(f) not in self.from_parts:
            self.from_parts[id(f)] = []
            f.confidence = round(min(1.0, f.confidence + PART_NAMED), 2)
        self.evidence(f, c, "soloist named by the")
        self.name(f, c)

    def add(self, c: Claim) -> None:
        mark = self.marks[c.mark]
        found = c.feature
        f = Feature(
            kind=found.kind, instrument=c.instrument, page=mark.page, bar=c.bar, rehearsal_mark=c.mark,
            raw_text=found.raw_text, confidence=min(found.confidence, FOUND_IN_PART),
            reasons=[f"found only in the {c.instrument} part: the score marks no {found.kind} at mark {c.mark}"],
            locations=[Location(mark.page, c.bar)], chair=c.chair, chair_ambiguous=c.ambiguous,
        )
        self.from_parts[id(f)] = [c.who]
        self.evidence(f, c, "marked in the")
        place = (mark.page, c.bar if c.bar is not None else mark.bar if mark.bar is not None else 10**6)
        after = [i for i, g in enumerate(self.features) if (g.page, g.bar if g.bar is not None else 10**6) <= place]
        self.features.insert(after[-1] + 1 if after else 0, f)

    # -- the whole pass --------------------------------------------------------------
    def claims(self) -> list[Claim]:
        found = []
        for index, part in enumerate(self.parts.parts):
            if not _readable(part):
                continue
            solos = distinct_solos(part.features)
            for f in solos:
                if f.kind != "vocal lead" and (f.instrument is None or present_as(f.instrument, _names(part))):
                    found.append(_claim_of(part, index, f, _noise(solos)))
        return sorted(found, key=lambda c: (self.order.get(c.instrument, 10**6), c.chair or 0, c.index))

    def cues(self) -> None:
        """A '<X> solo' cue printed in another part supports X's feature."""
        for index, part in enumerate(self.parts.parts):
            if not _readable(part):
                continue
            for f in distinct_solos(part.features):
                if f.kind == "vocal lead" or f.instrument is None or present_as(f.instrument, _names(part)):
                    continue
                for feature in self.features:
                    if (
                        id(feature) in self.original and feature.kind == f.kind
                        and any(present_as(f.instrument, [p.instrument]) for p in self.who(feature))
                        and (f.rehearsal_mark == feature.rehearsal_mark or _gap(f.bar, feature.bar) is not None and _near(f.bar, feature.bar))
                    ):
                        reason = f"a '{f.instrument} solo' cue is printed in the {part.part.instrument} part (part page {f.page})"
                        if reason not in feature.reasons:
                            feature.reasons.append(reason)

    def uncarried(self) -> None:
        """Score features naming an instrument whose part is present but does not carry them."""
        for f in self.features:
            if id(f) not in self.original or f.kind == "vocal lead":
                continue
            for p in self.who(f):
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
        """Soloists found from parts become the feature's instrument and the others it is shared with."""
        for f in self.features:
            soloists = self.from_parts.get(id(f))
            if soloists:
                first, *rest = soloists
                f.instrument, f.chair, f.chair_ambiguous = first.instrument, first.chair, first.chair_ambiguous
                f.shared_with = rest
        for (index, reason), where in self.ignored.items():
            n = len(where)
            self.warnings.append(
                f"part {self.parts.parts[index].file}: ignored {n} solo{'s' if n > 1 else ''} ({', '.join(where)}): {reason}"
            )


def cross_reference(
    features: list[Feature], parts: PartsReport, marks: list[ScoreMark], instrumentation: list[InstrumentEntry]
) -> tuple[list[Feature], list[str]]:
    """(the score's features with the part solos merged in, warnings for every
    disagreement). The features keep the score's order."""
    known = [n for e in instrumentation for n in (e.instrument, *e.doublings)]
    order = {e.instrument: i for i, e in enumerate(instrumentation)}
    run = _CrossReference(list(features), parts, {m.text: m for m in marks}, known, order)
    for claim in run.claims():
        run.place(claim)
    run.cues()
    run.uncarried()
    run.finish()
    return run.features, run.warnings
