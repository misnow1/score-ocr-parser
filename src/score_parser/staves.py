"""Staff assignment: which system and which staff a token belongs to.

A staff band is the vertical position of one staff, taken from its label. The
label column gives each system its bands; text between or above them is
assigned by vertical position alone.
"""

from dataclasses import dataclass
from typing import Protocol

from .clefs import clef_ys, unlabeled_clefs
from .layout import LINE_TOLERANCE, label_stacks, label_tokens, running_headers
from .models import Page


@dataclass
class Staff:
    label: str
    yc: float
    voice: bool = False  # a voice staff (or a vocal group label): never an instrument


class HasStaves(Protocol):
    staves: list[Staff]


def staff_at(staves: list[Staff], yc: float) -> Staff:
    """The staff a text above a staff belongs to: the first one at or below it."""
    return next((s for s in staves if s.yc >= yc - LINE_TOLERANCE), staves[-1])


def _distance(staves: list[Staff], yc: float) -> float:
    """Zero inside the system's staff span; text above a system belongs to it."""
    top, bottom = staves[0].yc, staves[-1].yc
    if yc > bottom:
        return yc - bottom + 1000  # below a system: prefer the system underneath
    return max(0.0, top - yc)


def owning_system[S: HasStaves](systems: list[S], yc: float) -> S:
    """The system a text line at yc belongs to."""
    return min(systems, key=lambda s: _distance(s.staves, yc))


def unlabeled_staff_warnings(pages: list[Page]) -> list[str]:
    """A warning when a staff (a clef) has no label near it: the first page where
    it happens, and how many more pages repeat it. Pages without clef glyphs
    (scans) or without labels are not judged."""
    headers = running_headers(pages)
    found: list[str] = []
    for page in pages:
        stacks = label_stacks(page, headers)
        labels = [ln.yc for stack in stacks for ln in stack]
        if not labels:
            continue
        clefs = clef_ys(page, max(t.x1 for t in label_tokens(stacks)))
        missing = unlabeled_clefs(labels, clefs)
        if missing:
            where = ", ".join(f"y={y:.0f}" for y in missing)
            found.append(
                f"Page {page.number}: {len(missing)} staff with no label ({where}); "
                f"{len(clefs)} staves, {len(labels)} labels"
            )
    if len(found) > 1:
        found[0] += f" (and {len(found) - 1} more pages)"
    return found[:1]
