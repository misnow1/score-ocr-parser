# Glossary

- **Score**: a conductor score PDF (text-layer export or image-only scan). Scores are unlicensed copies and are never copied or committed.
- **Token**: a positioned word with text, bounding box, page, font name, source and OCR confidence.
- **Text layer**: words embedded in a PDF. **OCR** produces the same tokens from page images.
- **Music-font glyph**: a clef, note, rest or accidental drawn from a notation font (private-use characters, or Opus-style fonts). Removed in the clean stage.
- **Staff label**: the instrument name at the left of a staff. Full names appear on the first system, abbreviations on later ones.
- **System**: one row of staves across the page.
- **Chair**: a numbered seat within a section ("Trumpet 2"). Not an instrument.
- **Canonical instrument**: the normalised name from the alias table ("Alto Sax").
- **Unknown label**: a staff label the alias table cannot resolve. Reported, never guessed.
- **Doubling**: a second instrument a player picks up.
- **Feature**: a solo or featured passage.
- **Report**: the `ScoreReport` returned by `parse_score`.
