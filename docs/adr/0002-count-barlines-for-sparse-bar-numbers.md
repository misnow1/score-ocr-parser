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
- A copy on a later row only merges into a feature as a reminder when it sits in that row's first bar; further in, it is a new feature. (Without counted barlines, a copy on the next system always merges, as before.)
- OCR pages have no drawn rules. They keep the previous behaviour (the nearest printed number) with lower confidence and a reason saying the bar may be earlier than the true one. A text-layer page with no drawn barlines behaves the same, without the confidence penalty.
- Confidence: a counted bar scores as a printed one; a bar continued from the previous system, assumed first bar and OCR bar score less.

## Consequences

- Real scores checked in place: counting from printed numbers agrees with the numbering across page breaks (the last bar of one page plus one is the next page's printed number).
- Jingle Bells trombone p8: the cue copies ("TBN SOLO") sit in bar 45, the printed number centred on the barline that starts it. The trombone's own staff carries a bare "SOLO" one bar earlier, in bar 44, which is the verified fact; it merges into the feature as a second location (`locations` lists 45 and 44). The feature keeps the best-evidenced copy (bar 45). Placing a feature at its earliest copy was tried and dropped: on Jingle Bells p5 it moved the alto solo from the verified 29 to 28 (a bare "SOLO" on the alto staff a bar before the "ALTO SOLO" cue), so the verified facts do not follow one rule here. The p8 trombone fact stays an expected failure.
- Jingle Bells p9 and p10: the baritone solos at 49 and 57 are found by counting (p10 prints no number and continues from p9). The trombone cue on p9 starts bar 53 by count, with 52 printed one barline before it, where the verified fact says 52. The counts of p8, p9 and p10 agree with each other and with p11's printed 61, so a pickup or an own-staff marking a bar early is the suspect, not the count. Expected failure in `tests/corpus/expected.yaml`.
- A score whose barlines are not drawn as vector rules (some exports draw them as font glyphs) falls back to the old behaviour.
- Repeats, voltas and bars of a different drawing style (multi-bar rests with no barline) can miscount; a printed number on a later system re-anchors the count.
