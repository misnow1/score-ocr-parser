"""Part mode: read one part file (a single instrument, no label column).

The instrument comes from the filename's trailing part word, through the alias
table; the instrument folder the part sits in is its player slot (who plays
it). A folder that names a different instrument is reported as a doubling when
the two are in one family or listed together, else as an unexplained
disagreement, never corrected: only show knowledge can say who plays what.
`show_context` is where that knowledge will plug in (a future release); it is
not read yet.
"""

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from .clean import clean
from .data import load
from .features import features_in
from .instruments import Resolved, Roster, present_as, resolve
from .models import InstrumentFrom, PageInfo, ParseOptions, PartInfo, PartReport, SlotRelation
from .part_systems import find_part_systems
from .source import read_pages, scan_warnings
from .title import clean_filename

MAX_PART_WORDS = 6  # the part word is at most this many trailing words, chair tokens included ("Tenor sax 1 & 2")
_DIGIT_AFTER_LETTER = re.compile(r"(?<=[A-Za-z])(?=\d)")  # "Trpt1", "sax1-2"
_PDF_REMNANT = re.compile(r"(?:\.pdf)+$", re.I)
_PAREN_NOISE = re.compile(r"[(\[]\s*(?:copy|\d+)\s*[)\]]", re.I)
_NOISE_WORD = re.compile(r"^(?:copy|score|part|parts|final|draft|ajc|(?:19|20)\d{2})$", re.I)
_DASHES = ("-", "–")


@dataclass
class _Word:
    text: str
    start: int  # where it starts in the filename stem


@cache
def _doubling_data() -> dict:
    data = load("part_doublings.yaml")
    return {
        "families": [frozenset(f) for f in data["families"]],
        "pairs": {slot: frozenset(names) for slot, names in data["pairs"].items()},
        "generic": frozenset(data["generic_parts"]),
        "one_line": frozenset(data["one_line_staves"]),
    }


def _words(stem: str) -> list[_Word]:
    """The words of a filename stem that may name a part: noise words (copy,
    score, part, a year), "(copy)" and "(1)", dashes and a ".pdf" remnant are out."""
    stem = _PDF_REMNANT.sub("", stem)
    blanked = _PAREN_NOISE.sub(lambda m: " " * len(m.group()), stem)
    return [
        _Word(m.group(), m.start())
        for m in re.finditer(r"[^\s_]+", blanked)
        if m.group() not in _DASHES and not _NOISE_WORD.match(m.group())
    ]


def _part_word(stem: str) -> tuple[Resolved, str] | None:
    """(the instrument named at the end of a filename, the stem before it).
    Windows end at the last word or the one before it; the longest run of
    words that resolves wins, so "Bass Gtr" is not "Gtr", and a run that starts
    with a bare number is no part word."""
    words = _words(stem)
    for end in (len(words), len(words) - 1):
        for n in range(min(MAX_PART_WORDS, end), 0, -1):
            window = words[end - n : end]
            if window[0].text.isdigit():
                continue
            hit = resolve(_DIGIT_AFTER_LETTER.sub(" ", " ".join(w.text for w in window)))
            if hit:
                return hit, stem[: window[0].start]
    return None


def _slot(folder: str) -> Resolved | None:
    """The instrument and chair an instrument folder ("alto-sax-1") stands for."""
    name = re.sub(r"-(?=\D)", " ", folder)
    return resolve(re.sub(r"-(?=\d)", " ", name, count=1))


def _rank(slot: Resolved, instrument: Resolved) -> int:
    """0: the slot's own instrument (or a variant of it); 1: a doubling (one
    family, a listed pair, or a generic part of the slot's family); 2: no
    known relation."""
    data = _doubling_data()
    if present_as(instrument.name, [slot.name]):
        return 0
    generic = instrument.name in data["generic"] and instrument.family == slot.family
    listed = instrument.name in data["pairs"].get(slot.name, ())
    if generic or listed or any(slot.name in f and instrument.name in f for f in data["families"]):
        return 1
    return 2


def _relation(slot: Resolved | None, folder: str, parts: list[Resolved]) -> tuple[SlotRelation, str]:
    """How the player slot relates to the part's instruments (the closest one
    counts), with a note for a doubling or an unexplained disagreement."""
    if slot is None:
        return "unknown", ""
    rank, name = min((_rank(slot, p), p.name) for p in parts)
    where = f"player slot {folder} ({slot.name})"
    if rank == 0:
        return "same", ""
    if rank == 1:
        return "doubling", f"{where} plays {name}"
    return "unexplained", f"{where} holds a {name} part: unexplained disagreement, left as filed"


def _chair_note(slot: Resolved | None, folder: str, chairs: list[int]) -> str:
    """A note when the part's chairs and the slot's chair share none."""
    if slot is None or not slot.chairs_given or not chairs or set(slot.chairs) & set(chairs):
        return ""
    return f"player slot {folder} is chair {', '.join(map(str, slot.chairs))}; the part is chair {', '.join(map(str, chairs))}"


def _label(name: str, chairs: list[int]) -> str:
    """A staff label for a part's staves ("Trumpet 1", "Tenor Sax 1-2")."""
    if not chairs:
        return name
    if len(chairs) > 1 and chairs == list(range(chairs[0], chairs[-1] + 1)):
        return f"{name} {chairs[0]}-{chairs[-1]}"
    return f"{name} {'&'.join(map(str, chairs))}"


def read_part_info(path: Path) -> tuple[PartInfo, str]:
    """(who the part is for, the song title from its filename)."""
    folder = path.parent.name
    slot = _slot(folder)
    named = _part_word(path.stem)
    hit: Resolved | None = named[0] if named else slot
    source: InstrumentFrom | None = "filename" if named else "folder" if slot else None
    title = clean_filename(named[1] if named else path.stem)
    if hit is None:
        return PartInfo(None, [], None, folder, relation="unknown"), title
    chairs = hit.chairs if hit.chairs_given else []
    relation, note = _relation(slot, folder, hit.parts()) if named else ("same", "")
    if relation == "same":
        note = _chair_note(slot, folder, chairs)
    info = PartInfo(
        hit.name, chairs, source, folder, slot.name if slot else None, relation, note,
        also=[p.name for p in hit.also],
    )
    return info, title


def parse_part(
    path: str | Path, show_context: dict | None = None, options: ParseOptions | None = None
) -> PartReport:
    """Read one part PDF in place and return its report. `show_context` is the
    planner's person-to-part metadata (future release); it is accepted and not
    read yet."""
    path = Path(path)
    options = options or ParseOptions()
    info, title = read_part_info(path)
    warnings: list[str] = []
    if info.instrument is None:
        warnings.append(f"instrument unknown: neither the filename nor the folder '{info.player_slot}' names one")
    if info.relation == "unexplained":
        warnings.append(info.note)
    pages = [clean(p) for p in read_pages(path, options.force_ocr)]
    for page in pages:
        warnings += scan_warnings(page)
    features = []
    if info.instrument:
        roster = Roster({info.instrument: set(info.chairs) or {1}})
        label = _label(info.instrument, info.chairs)
        one_line = bool({info.instrument, *info.also} & _doubling_data()["one_line"])
        systems = [s for page in pages for s in find_part_systems(page, label, one_line)]
        if not systems:
            warnings.append("no staves found: the part has no drawn staff lines to read solos from")
        features, found = features_in(systems, roster)
        warnings += found
    return PartReport(
        title, info, features, [PageInfo.from_page(p) for p in pages], warnings, file=f"{path.parent.name}/{path.name}"
    )
