# score-ocr-parser

Extract the instrumentation and solos and features, and draft a planner flow, from big-band conductor score PDFs. Runs locally; the PDFs are read in place and never copied.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run pytest
```

OCR tests are macOS-only and are skipped elsewhere; CI runs them on a macOS runner.

## Usage

```
uv run score-parser parse SCORE.pdf [FOLDER ...] --out out [--format json|yaml|both] [--numbers-dir DIR] [--force-ocr]
uv run score-parser inspect SCORE.pdf --page 1 [--tokens | --layout] [--force-ocr]
```

- `parse` writes, per PDF, the JSON report `<score>.json` and/or the flow draft `<name>.yaml` into the output directory (default `out/`, git-ignored), chosen by `--format` (`json` default, `yaml`, or `both`), and prints a summary table (see Folder runs).
- `inspect` prints one page's cleaned tokens (default) or the label stacks and lines to stdout. It never writes files.

Library use:

```python
from score_parser import parse_score
report = parse_score("SCORE.pdf")
report.instrumentation, report.unknown_labels
```

The JSON report (`report.to_dict()`) has these fields:

- `title`, `title_source`, `matched_slug`, `draft_name`, `unmatched`;
- `instrumentation[]`: `instrument`, `family`, `chairs`, `labels`, `doublings`;
- `features[]`: `kind` (`solo` or `feature`), `instrument`, `page`, `bar`, `rehearsal_mark`, `raw_text`, `confidence`, `reasons`, and `locations[]` (each `{page, bar}`: the first appearance of a merged feature, then its reminders);
- `flow[]`: the draft steps (`section`, `instrument`, `note`, `todo`);
- `unknown_labels`, `warnings`;
- `pages[]`: `page`, `source` (`text` or `ocr`), `ocr_confidence`, `dpi`, `reason` (`text`, `image`, `pattern` or `empty`: why the page was read that way) and `rotation` (degrees clockwise the scan is printed rotated: 0, 90 or 270; 0 for text pages).

Each page is classified with a reason, recorded as `report.pages[].reason`: `text` (has a text layer), `image` (almost no text words plus a page-sized image), `pattern` (almost no text words and the page draws its content as a tiling-pattern fill, which hides the image from image detection) or `empty` (almost no text words and nothing else). Every page but `text` is sent to OCR automatically; `pattern` and `empty` pages are rendered whole at 300 dpi first. A page that yields no tokens, and a score whose instrumentation comes back empty, add entries to `report.warnings`, so zero results are never silent. Scans are read with Apple Vision OCR (macOS only, via pyobjc; installed on macOS only). OCR yields the same positioned words as a text layer. The embedded image is read at native resolution; pages under about 300 dpi are upscaled to 300 dpi. Recognition is accurate-level with language correction off and the alias table as custom vocabulary. `--force-ocr` (CLI) or `ParseOptions(force_ocr=True)` OCRs every page regardless of text layer. `report.pages` records each page's `source` (`text` or `ocr`), `ocr_confidence` and `dpi`; pages under 150 dpi or below 0.5 mean OCR confidence add entries to `report.warnings` (the CLI prints them). Scans printed sideways are handled by trying three orientations per page (content rotated 0, 90 or 270 degrees clockwise): the image is turned upright for each, OCR runs, and the best wins by instrument-word hits in the left half of the upright page (staff labels sit left of the staves, and Vision also reads upside-down text, so it can't pick by confidence alone), then total hits, then mean confidence. Tokens come back in the upright frame and `Page` width and height are swapped for a turned scan, so layout sees an upright page. The chosen rotation is recorded as `report.pages[].rotation` (0 for text pages). The text-layer path imports nothing macOS-specific, so it stays cross-platform.

Current scope: text-layer PDFs and scans. The report lists the instruments on the first system (full names), with:

- chairs, expanded from ranges ("1-4", "1–4", "Tbn.1-4", "i & II");
- combined labels: "Trb. 3, Tba." gives Trombone chair 3 and Tuba chair 1. Each part must resolve, or the whole label is unrecognised; each part is then cross-checked like a single label (see the later-system rule below);
- doublings, from labels ("Flute (Oboe) 1-3") and from instruction text ("to Flute", "piccolo trpt"; a "Mute" marking is ignored). An instruction is attached to the staff label nearest to it vertically;
- non-standard instruments (violin, viola, cello, organ, guitars, french horn, tuba, percussion, synthesizer, sleigh bells, wood block ("W BL", "W. Bl."), cowbell ("C BL", "C. Bl."), lead vocal, flugelhorn, piccolo trumpet, and others in the alias table).

Staff labels are found as a column at the left of the staves. Notation programs right-align them (short names such as "Piano" or "Picc." start further right), so the column is found from labels sharing a right edge, or a left edge for left-aligned scores, whichever lines up more labels. Each line is cut to its label at the first gap of 8 pt or more, glyph residue, chord symbol ("Pno. D D A7") or time signature ("Baritone Saxophone 44": the 44 is never read as a chair). Running titles (a long line repeating on several pages), score and group tags ("Score 5", "Trumpets"), credit and footer lines, lone chords and dynamics, and one- or two-letter glyph residue are not labels (`data/label_filters.yaml`). The first system is the stack with the most resolving labels on the first page that has any, not simply the topmost stack.

Abbreviated labels on later systems ("A. Sx. 1", "Tbn. 1-4", "E.B.", "D. S.") are cross-checked against the first system. The first system is only a heuristic pick, so an instrument it lacks is still a normal instrument of the score when its labels recur: one that appears on two or more later systems joins the instrumentation without a warning. Canonical-name variants count as one instrument (Bass and Electric Bass, listed in `data/instrument_variants.yaml`, applied by `present_as`); a variant label is filed under the entry already present. A label for an instrument that appears on only one later system, a chair outside the first system's chairs for an instrument it has, or a label that cannot be resolved adds a message to `warnings`. Unresolved labels also go to `unknown_labels`, never guessed. Choir and voice labels ("SATB", "Choir", "Voice Lead", "VCLS") and ambiguous ones (a lone "A." or "Bar.", which can be a vocal part) are deliberately not in the alias table. A combined label ("Trb. 3, Tba.") counts as each of its instruments: every part is checked on its own, so a part that recurs is accepted while another part with a chair outside the first system's still warns.

Music-font glyphs are removed before reading. A word's font comes from its own characters (empty when they span several fonts). A token is dropped when it is set in a font listed in `music_fonts.yaml` (Sibelius Opus and Finale Jazz, Maestro and BroadwayCopyist glyphs look like plain characters, so only the font name identifies them; fonts whose name contains `text` are kept), or when its font is empty and it holds only glyph characters (`music_glyphs` in the same file) or any non-ASCII one, or private-use characters. The alias table (`aliases.yaml`) and `music_fonts.yaml` are editable data in `src/score_parser/data/`.

Solo and feature detection: `report.features` lists every solo or feature marking ("ALTO SOLO", "1x - Solo", "Male vocal solo", "vamp for drum feature") with kind, instrument (from the text, else from the staff it sits on; only instruments in the first-system instrumentation, anything else is dropped with a warning), page, nearest bar number, current rehearsal mark, raw text, confidence and reasons. Layout analysis finds systems (stacks of staff labels from the label column), staff bands, bar numbers and rehearsal marks (single capitals and section words listed in `data/rehearsal_words.yaml`), and splits glued tokens such as "29ALTO SOLO". A vocal feature needs the word male, female, vocal or vox directly before the solo wording; "male" or "female" alone scores lower than "vocal" or "vox". Bar numbers are printed sparsely, so on text-layer pages a feature's bar is counted: the drawn barlines (vertical rules from the PDF's vector drawings, at least 20 pt tall) between the nearest printed number and the text are added to that number, so a solo mid-system gets its own bar, not the system's first (ADR 0002). Stacks of one system share one row of bars; a row with no printed number continues from the bars of the row before, and the first row of the score starts at bar 1. A solo's `page` and `bar` are those of its earliest numbered copy, and a reminder on a later row only joins a feature when it sits in that row's first bar. OCR pages have no drawn rules: they keep the nearest printed number, with lower confidence and a reason saying the bar may be earlier than the true one; a text-layer page with no drawn barlines does the same without the penalty. Text left of every bar number on a system with no barlines takes the first bar with lower confidence and a reason saying so. Copies are merged: a solo printed above every staff, and reminders on later systems and pages, become one feature (same kind and instrument on the same or the next system; a system without it in between starts a new one). `locations` lists each distinct page and bar; `page` and `bar` come from the earliest numbered copy (confidence and reasons from the best-evidenced copy). Chord symbols ("F6", "G7") are stripped from `raw_text`. A solo text that names an instrument missing from the instrumentation gets no instrument (the staff it sits above is not the soloist's). Text containing "solo" or "feature" is never taken as a staff label, a number equal to the page number in the label column or right margin is not a bar number. A number is accepted as a bar number only when it sits in the bar row (6 to 60 pt above the top staff's label line), which rules out time signatures on the staff, running headers ("10 Score") and triplet numbers inside the system; bar numbers must also rise through the score, so a number that breaks the longest non-decreasing run in reading order (a triplet 3 among bars in the 40s) is dropped. A feature with no accepted bar nearby keeps `bar: null`; it is never dropped.

Flow draft (`--format yaml`, or `report.flow`): a `flow:` block in the shape mic-assignment-planner uses in `numbers/*.yaml`. One step per feature, each with `section` ("Alto Sax solo (B)"), `instrument` (lower case) and a `note` giving page, bar, rehearsal mark and confidence. Steps below 0.8 confidence, or with no instrument, are followed by a `# TODO(score-parser)` comment giving the reasons. The draft never contains `kind` (vocal or instrumental) or `position` (DS1-DS5); those stay with the planner.

Title: the filename with noise removed ("SCORE", dates, years, "AJC", "copy", "(1)" and similar) and a trailing part name after a dash ("ERGUE A CASA - Piano" gives "ERGUE A CASA"; only a dash-separated instrument name is dropped, so "Piano Man" is kept); if nothing is left, the largest text on page 1. `report.title_source` says which (`filename` or `page 1`).

`--numbers-dir DIR` (or `ParseOptions(numbers_dir=...)`) points at the planner's `numbers/` folder, which is only read. The title is fuzzy-matched (rapidfuzz) against the slugs, each file's `title:` and the known aliases in `data/title_aliases.yaml` (First Noel = First Nowell, Superstition = Super Christmas). A match names the draft `<slug>.yaml` (`report.matched_slug`). With no match the draft is named `UNMATCHED-<title-slug>.yaml` and starts with an `UNMATCHED` comment. Without `--numbers-dir` the draft is named for the title slug. `parse` refuses an output directory inside the numbers directory, so it never writes into the planner repo.

Folder runs: `parse` accepts folders (every `*.pdf` in them, any letter case) and files together. After the run it prints a summary table with one row per score: instrument count, feature count and warning count, so charts that need a manual look stand out. If two scores would write the same output file name (for example the same matched slug), the later one gets `-2`, `-3` and so on, and a warning says so. Warning text goes to stderr. A score that fails to parse does not stop the run: its row shows `FAILED`, the error goes to stderr, and the exit code is 1 (0 when every score parsed).

## Corpus tests

`tests/corpus/` holds opt-in tests against the real local score folder. They are skipped unless `SCORE_CORPUS_DIR` is set, and are never run in CI:

```
SCORE_CORPUS_DIR=/path/to/scores uv run pytest tests/corpus
```

The scores are read in place; nothing is copied or written. One test checks that every PDF in the folder parses. The others compare each score with the approved facts in `tests/corpus/expected.yaml`. Pages and bars match exactly (no tolerance), so a bar one off fails.

To add facts, first get the user's approval for each one, then add an entry keyed by the PDF file name without `.pdf`:

```yaml
scores:
  some-score-file-stem:
    instruments: [Alto Sax, {name: Wood Block, xfail: "why the tool misses it"}]
    max_features: 13                  # at most this many features in the report
    features:
      - {instrument: Alto Sax, page: 5, bar: 29}
      - {instrument: Guitar, chair: 2, page: 24, bar: 143}
      - {instruments: [Clarinet, Trumpet], kind: shared, page: 1, bar: 9, mark: A}
      - {instrument: Vocal, kind: vocal, page: 3, mark: B, xfail: "vocal lead not recognised"}
    not_features:                     # false positives that must not appear
      - {instrument: Baritone Sax, page: 5}
```

- Feature keys, all optional except the instrument: `page`, `bar` and `mark` (rehearsal mark) match exactly; `chair` (the feature must carry that chair; the tool does not report one yet, so such facts are marked `xfail`); `kind` is `instrument`, `vocal` (instrument `Vocal`) or `shared`; `instruments` lists several instruments that must each have a feature at the same page, bar and mark (use it with `kind: shared`).
- `xfail: reason` records a fact the tool does not meet yet. It must keep failing: once it passes, the test fails and asks you to remove the `xfail`.
- `not_features` lists instrument features that must not be found (given `page`, `bar` or `mark` to narrow them down).

Facts stay short and hold no music content: instrument names, page, bar and marker only.

`scripts/corpus_counts.py [DIR]` (default `$SCORE_CORPUS_DIR`) prints per-score counts to stdout: instruments, features, features with no bar, features with no instrument and warnings, so two runs can be compared. Rows are numbered by sorted position; `--names` adds the file names. It prints numbers only and writes nothing.

## Licensing

Scores are unlicensed copies. Never copy, render, commit or store scores or excerpts. `.gitignore` excludes PDFs, images and `out/`; only the synthetic fixtures in `tests/fixtures/synthetic/` are committed. Regenerate them with `uv run python scripts/make_fixtures.py`.

See `docs/adr/` for decisions and `GLOSSARY.md` for terms.

Open question (Jingle Bells): the left-margin words "Bls." (once per page, at the bottom of the page, from p2) and "HEY!" (beside most staves on p4, p9, p15, p20 and p28) are not in the alias table. "HEY!" is a shouted cue, not a staff label. "Bls." may be a bells staff (Sleigh Bells would be "S. Bells"), but that is unconfirmed, so it stays unrecognised until the planner decides.
