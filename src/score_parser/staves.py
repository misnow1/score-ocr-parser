"""Staff assignment: which system and which staff a token belongs to.

A staff band is the vertical position of one staff, taken from its label. The
label column gives each system its bands; text between or above them is
assigned by vertical position alone.
"""

from dataclasses import dataclass
from typing import Protocol

from .layout import LINE_TOLERANCE


@dataclass
class Staff:
    label: str
    yc: float


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
