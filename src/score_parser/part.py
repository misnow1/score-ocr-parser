"""Part mode: read one part file (a single instrument, no label column).

The instrument comes from the filename's trailing part word, through the alias
table; the instrument folder the part sits in is its player slot (who plays
it). A folder that names a different instrument is reported as a doubling when
the slot's player is known to cover it, else as an unexplained disagreement,
never corrected: only show knowledge can say who plays what. `show_context` is
where that knowledge will plug in (a future release); it is not read yet.
"""

import re
from functools import cache
from pathlib import Path

from .clean import clean
from .data import load
from .features import features_in
from .instruments import Resolved, Roster, resolve
from .models import InstrumentFrom, PageInfo, ParseOptions, PartInfo, PartReport, SlotRelation
from .source import read_pages, scan_warnings
from .part_systems import find_part_systems
from .title import clean_filename

MAX_PART_WORDS = 4  # the part word is at most this many trailing words ("Sleigh Bells")
_DIGIT_AFTER_LETTER = re.compile(r"(?<=[A-Za-z])(?=\d)")  # "Trpt1", "sax1-2"


@cache
def _known_doublings() -> dict[str, frozenset[str]]:
    return {slot: frozenset(names) for slot, names in load("part_doublings.yaml")["doublings"].items()}


def _part_word(stem: str) -> tuple[Resolved, str] | None:
    """(the instrument named by the trailing words of a filename, the words
    before them). The longest run of trailing words that resolves wins, so "Bass
    Gtr" is not "Gtr"; a run that starts with a bare number is no part word."""
    words = re.split(r"[\s_]+|\s*[-–]\s+", stem.strip())
    for n in range(min(MAX_PART_WORDS, len(words)), 0, -1):
        tail = words[-n:]
        if tail[0].isdigit():
            continue
        hit = resolve(_DIGIT_AFTER_LETTER.sub(" ", " ".join(tail)))
        if hit and not hit.also:
            return hit, " ".join(words[:-n])
    return None


def _slot(folder: str) -> Resolved | None:
    """The instrument and chair an instrument folder ("alto-sax-1") stands for."""
    name = re.sub(r"-(?=\D)", " ", folder)
    return resolve(re.sub(r"-(?=\d)", " ", name, count=1))


def _relation(slot: Resolved | None, folder: str, instrument: str) -> tuple[SlotRelation, str]:
    """How the player slot relates to the part's instrument, with a note for a
    doubling or an unexplained disagreement."""
    if slot is None:
        return "unknown", ""
    if slot.name == instrument:
        return "same", ""
    where = f"player slot {folder} ({slot.name})"
    if instrument in _known_doublings().get(slot.name, ()):
        return "doubling", f"{where} plays {instrument}"
    return "unexplained", f"{where} holds a {instrument} part: unexplained disagreement, left as filed"


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
    relation, note = _relation(slot, folder, hit.name) if named else ("same", "")
    chairs = hit.chairs if hit.chairs_given else []
    return PartInfo(hit.name, chairs, source, folder, slot.name if slot else None, relation, note), title


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
        systems = [s for page in pages for s in find_part_systems(page, label)]
        if not systems:
            warnings.append("no staves found: the part has no drawn staff lines to read solos from")
        features, found = features_in(systems, roster)
        warnings += found
    return PartReport(title, info, features, [PageInfo.from_page(p) for p in pages], warnings)
