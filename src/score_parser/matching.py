"""Match a score title to an existing planner number slug (read-only)."""

import re
from pathlib import Path

import yaml
from rapidfuzz import fuzz, process

from .data import load

MIN_SCORE = 85


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _normalise(text: str) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower().replace("-", " "))
    return re.sub(r"^(the|a) ", "", " ".join(text.split()))


def _known_aliases() -> dict[str, list[str]]:
    """slug -> alternative titles, from data/title_aliases.yaml."""
    return load("title_aliases.yaml")["aliases"]


def _names_for(slug: str, numbers_dir: Path, aliases: dict[str, list[str]]) -> set[str]:
    names = {_normalise(slug), *(_normalise(a) for a in aliases.get(slug, []))}
    try:
        title = yaml.safe_load((numbers_dir / f"{slug}.yaml").read_text()).get("title")
    except (OSError, yaml.YAMLError, AttributeError):
        title = None
    if isinstance(title, str):
        names.add(_normalise(title))
    return names


def match_slug(title: str, numbers_dir: Path) -> str | None:
    """Slug of the planner number this title belongs to, or None. Read-only."""
    aliases = _known_aliases()
    candidates: dict[str, str] = {}  # normalised name -> slug
    for path in sorted(numbers_dir.glob("*.yaml")):
        for name in _names_for(path.stem, numbers_dir, aliases):
            candidates.setdefault(name, path.stem)
    wanted = _normalise(title)
    if wanted in candidates:
        return candidates[wanted]
    hit = process.extractOne(wanted, list(candidates), scorer=fuzz.WRatio, score_cutoff=MIN_SCORE)
    return candidates[hit[0]] if hit else None
