# score-ocr-parser

Extract the instrumentation (and, in later tickets, solos and features) from big-band conductor score PDFs. Runs locally; the PDFs are read in place and never copied.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run pytest
```

## Usage

```
uv run score-parser parse SCORE.pdf [FOLDER ...] --out out
uv run score-parser inspect SCORE.pdf --page 1 [--tokens | --layout]
```

- `parse` writes `<score>.json` per PDF into the output directory (default `out/`, git-ignored) and prints a one-line summary per score.
- `inspect` prints one page's cleaned tokens (default) or the label column and lines to stdout. It never writes files.

Library use:

```python
from score_parser import parse_score
report = parse_score("SCORE.pdf")
report.instrumentation, report.unknown_labels
```

Current scope: text-layer PDFs. The report lists the instruments on the first system (full names), with:

- chairs, expanded from ranges ("1-4", "i & II");
- doublings, from labels ("Flute (Oboe) 1-3") and from instruction text ("to Flute", "piccolo trpt"; a "Mute" marking is ignored). An instruction is attached to the staff label nearest to it vertically;
- non-standard instruments (violin, viola, cello, organ, guitars, lead vocal, flugelhorn, piccolo trumpet, and others in the alias table).

Abbreviated labels on later systems ("A. Sx. 1", "Tbn. 1-4", "E.B.", "D. S.") are cross-checked against the first system. A label for an instrument or chair the first system lacks, or one that cannot be resolved, adds a message to `warnings`. Unresolved labels also go to `unknown_labels`, never guessed.

Music-font glyphs are removed before reading: private-use characters, and any token set in a font listed in `music_fonts.yaml` (Sibelius Opus glyphs look like plain ASCII, so only the font name identifies them). The alias table (`aliases.yaml`) and music-font list are editable data in `src/score_parser/data/`.

## Licensing

Scores are unlicensed copies. Never copy, render, commit or store scores or excerpts. `.gitignore` excludes PDFs, images and `out/`; only the synthetic fixtures in `tests/fixtures/synthetic/` are committed. Regenerate them with `uv run python scripts/make_fixtures.py`.

See `docs/adr/` for decisions and `GLOSSARY.md` for terms.
