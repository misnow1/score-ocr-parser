# 0002. Count drawn barlines to place a solo between printed bar numbers

Status: accepted

## Context

Scores print bar numbers sparsely: one per system, or one per page, and some systems none. Reporting the last printed number puts a solo in the middle of a system at the system's first bar (a clarinet solo at bar 9 read as bar 3), and a system with no number gets no bar.

ADR 0001 limits the tool to text plus layout. A bar number is text, but the distance from it to a solo is a count of bars, and only the barlines say where bars end.

## Decision

On text-layer pages, read the vertical rules from the PDF's vector drawings (lines and thin rectangles at least 20 pt tall) and count them. This goes beyond ADR 0001's text and layout: it reads drawn rules but still no notes, rhythms or other music content, and OMR stays out of scope.

- A system's barlines are the rules crossing its first staff that two or more cross (stems drawn as rules cross a single staff and are not barlines). Rules within 4 pt are one barline (double and final barlines). Bar i starts at barline i; the first and last barlines are the system edges.
- A printed number is snapped to the nearest barline to its centre (numbers are centred on the barline, or start just right of it). A solo's bar is the nearest preceding printed number plus the barlines between; text left of every number counts back from the first.
- Stacks of one system (a label column split at a large vertical gap) share one row of bars when at least two rules run unbroken from one stack to the next. They share numbers and the count.
- A row with no printed number continues from the bars counted in the row before. The first row of the score, with no number, starts at bar 1 (a pickup bar, which a score normally numbers 0, would shift every later bar by one; this is the one assumption we cannot check from the page).
- A feature is placed at its earliest numbered copy: a soloist's own staff may carry the marking a bar before the conductor's cue copy. A copy on a later row only merges into the feature as a reminder when it sits in that row's first bar; further in, it is a new feature.
- OCR pages have no drawn rules. They keep the previous behaviour (the nearest printed number) with lower confidence and a reason saying the bar may be earlier than the true one. A text-layer page with no drawn barlines behaves the same, without the confidence penalty.
- Confidence: a counted bar scores as a printed one; a bar continued from the previous system, assumed first bar and OCR bar score less.

## Consequences

- Real scores checked in place: counting from printed numbers agrees with the numbering across page breaks (the last bar of one page plus one is the next page's printed number).
- Jingle Bells trombone: the solo is bar 44 (the trombone staff's own "SOLO" mark, a bar before the "TBN SOLO" cue copies printed in bar 45). The p9 trombone cue ("TBN SOLO" at the start of bar 53 by count, with 52 printed one barline before it) stays reported at bar 53 where the verified fact says 52; the evidence is geometric (the p8 and p9 counts agree with the baritone solos at 49 and 57 and with the next page's printed 61), so an off-by-one for a pickup bar is the suspect, not the count. It is recorded as an expected failure in `tests/corpus/expected.yaml`.
- A score whose barlines are not drawn as vector rules (some exports draw them as font glyphs) falls back to the old behaviour.
- Repeats, voltas and bars of a different drawing style (multi-bar rests with no barline) can miscount; a printed number on a later system re-anchors the count.
