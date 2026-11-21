"""Packaged YAML data (alias table, music fonts, rehearsal words, title aliases)."""

from importlib.resources import files

import yaml


def load(name: str) -> dict:
    """Parse the packaged data file `name` (for example "aliases.yaml")."""
    return yaml.safe_load(files(__package__).joinpath(name).read_text())
