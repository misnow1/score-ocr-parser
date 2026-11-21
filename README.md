# score-ocr-parser

Extract the instrumentation (and, in later tickets, solos and features) from big-band conductor score PDFs. Runs locally; the PDFs are read in place and never copied.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run pytest
```

OCR tests are macOS-only and are skipped elsewhere; CI runs them on a macOS runner.

## Usage

```
uv run score-parser parse SCORE.pdf [FOLDER ...] --out out [--force-ocr]
uv run score-parser inspect SCORE.pdf --page 1 [--tokens | --layout] [--force-ocr]
```

- `parse` writes `<score>.json` per PDF into the output directory (default `out/`, git-ignored) and prints a one-line summary per score.
- `inspect` prints one page's cleaned tokens (default) or the label column and lines to stdout. It never writes files.

Library use:

```python
from score_parser import parse_score
report = parse_score("SCORE.pdf")
report.instrumentation, report.unknown_labels
```

Scanned (image-only) pages are detected automatically (almost no text words plus a page-sized image) and read with Apple Vision OCR (macOS only, via pyobjc; installed on macOS only). OCR yields the same positioned words as a text layer. The embedded image is read at native resolution; pages under about 300 dpi are upscaled to 300 dpi. Recognition is accurate-level with language correction off and the alias table as custom vocabulary. `--force-ocr` (CLI) or `ParseOptions(force_ocr=True)` OCRs every page regardless of text layer. `report.pages` records each page's `source` (`text` or `ocr`), `ocr_confidence` and `dpi`; pages under 150 dpi or below 0.5 mean OCR confidence add entries to `report.warnings` (the CLI prints them). The text-layer path imports nothing macOS-specific, so it stays cross-platform.

Current scope: text-layer PDFs and scans. The report lists the instruments on the first system (full names), with:

- chairs, expanded from ranges ("1-4", "i & II");
- doublings, from labels ("Flute (Oboe) 1-3") and from instruction text ("to Flute", "piccolo trpt"; a "Mute" marking is ignored). An instruction is attached to the staff label nearest to it vertically;
- non-standard instruments (violin, viola, cello, organ, guitars, lead vocal, flugelhorn, piccolo trumpet, and others in the alias table).

Abbreviated labels on later systems ("A. Sx. 1", "Tbn. 1-4", "E.B.", "D. S.") are cross-checked against the first system. A label for an instrument or chair the first system lacks, or one that cannot be resolved, adds a message to `warnings`. Unresolved labels also go to `unknown_labels`, never guessed.

Music-font glyphs are removed before reading: private-use characters, and any token set in a font listed in `music_fonts.yaml` (Sibelius Opus glyphs look like plain ASCII, so only the font name identifies them). The alias table (`aliases.yaml`) and music-font list are editable data in `src/score_parser/data/`.

## Licensing

Scores are unlicensed copies. Never copy, render, commit or store scores or excerpts. `.gitignore` excludes PDFs, images and `out/`; only the synthetic fixtures in `tests/fixtures/synthetic/` are committed. Regenerate them with `uv run python scripts/make_fixtures.py`.

See `docs/adr/` for decisions and `GLOSSARY.md` for terms.
