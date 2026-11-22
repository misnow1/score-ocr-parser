# 0001. Text OCR plus layout analysis instead of OMR

Status: accepted

## Context

We need two facts from each big-band conductor score: the instrumentation and where the solos and features fall. Both are text plus position (staff labels, "ALTO SOLO", bar numbers, rehearsal marks). Neither needs notes, rhythms or chords.

## Decision

Read positioned words, from the PDF text layer or from text OCR on scans, and interpret them with layout analysis. Do not use optical music recognition (OMR).

## Consequences

- Both input kinds become the same token stream, so one layout parser serves both.
- Music-font glyphs are junk to remove, not content to read.
- Notation (MusicXML, rhythms) is out of scope. A later OMR source could plug in at the token or report level.
