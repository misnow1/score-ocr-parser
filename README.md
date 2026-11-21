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

Current scope: text-layer PDFs; the report lists the instruments on the first system, with chairs. Unrecognised labels go to `unknown_labels`. `report.features` lists every solo or feature marking ("ALTO SOLO", "1x - Solo", "Male vocal solo", "vamp for drum feature") with kind, instrument (from the text, else from the staff it sits on), page, nearest bar number, current rehearsal mark, raw text, confidence and reasons. Layout analysis finds systems (stacks of left-margin labels), staff bands, bar numbers and rehearsal marks (single capitals and section words listed in `data/rehearsal_words.yaml`), and splits glued tokens such as "29ALTO SOLO". Music-font glyphs are removed before reading. The alias table and music-font list are editable data in `src/score_parser/data/`.

## Licensing

Scores are unlicensed copies. Never copy, render, commit or store scores or excerpts. `.gitignore` excludes PDFs, images and `out/`; only the synthetic fixtures in `tests/fixtures/synthetic/` are committed. Regenerate them with `uv run python scripts/make_fixtures.py`.

See `docs/adr/` for decisions and `GLOSSARY.md` for terms.
