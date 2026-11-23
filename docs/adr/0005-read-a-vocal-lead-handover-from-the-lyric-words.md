# 0005. Read a vocal lead handover from the lyric words under the lead staves

Status: accepted

## Context

Winter Wonderland hands the lead from the female to the male at rehearsal mark H with no wording at all: no "Male Lead" text and no "solo" over a staff. The female, the male and both backing staves are printed on every system, so the staves alone name no change. The first idea was to read notes and rests from the music font glyphs. That did not hold up: the glyph codes depend on the font (Opus, Maestro, Finale private-use codes), notes above a staff fall outside its band, and rests and notes share one band when staves sit 27 pt apart.

Lyrics are plain text in the text layer, in the same place under every score's voice staves. In the real score the lead that sings has 5 to 12 words under its staff in a bar, a staff that is resting has none, and a backing staff sings fewer.

## Decision

- **Evidence.** A lead staff (a "Voice Lead F" or "Voice Lead M" label, the only labels that name a voice) sings in a bar when at least 5 lyric words sit in the band 0.2 to 0.55 of the staff gap below its centre, between two drawn barlines. A word has a letter and is not a dynamic ("mf", "cresc."). Annotation text printed above the next staff sits lower in that gap (about 0.6 of it) and stays out.
- **Sole lead.** A bar belongs to one voice when that lead staff sings and every other lead staff has fewer than 2 words. Backing staves do not count: a male lead over singing backings is still a male lead. The voice must sing alone in a second bar within 3 bars, with the other lead quiet in every bar between, so a one-bar fill (the male singing one bar over a held female note) is no handover. In Winter Wonderland the male at H sings bars 1 and 3 of his run with a near-empty bar between, which passes. The first bar of a system is read even when its left edge was not read as a barline.
- **Handover.** Leads marked in text (a voice, from wording or a bare solo over a Voice Lead staff) and bars sung alone make one stream in reading order, system then x. The lead at any point is the voice of the latest event before it, whichever kind: a text lead early on a system does not hide a handover later on it. A sole bar whose voice differs from the lead is a handover: a vocal lead for the new voice, voice from the staff label only, confidence 0.1 under a bare solo over a Voice Lead staff (0.7 with a counted bar), so the flow draft gets a TODO. The first voice to sing alone starts the count and gets no feature, since nothing was handed over.
- **One feature.** Handover candidates join the normal merge. When the handover has text ("Male Lead Verse 2") the text candidate and the handover are one feature, with the text's confidence.
- **Interleaving.** Voiced leads of one system are ordered by x, and a voiced lead is never a reminder of a group when another voice's lead came after that group: a voice returning after the other voice's lead is a new feature, on every path (same row, next row, page turn).
- **Page turn.** A voiced vocal lead restated on the next page's voice system joins the feature before it anywhere in the row (not only in its first bar), within 16 bars. It does not join under a new rehearsal mark, nor when it names a section the earlier copy lacks. Voiceless cues keep the first-bar rule.

## Consequences

- Scores with no "Voice Lead" pair (a choir label, a "VOCALS" group) never get a handover: the voice would be a guess. Measured in place on the real corpus, only Winter Wonderland has the pair, so no other score changes.
- Scans have no drawn barlines and no handover. A score whose voices sing "oo" and "ah" counts those as words; one that prints no lyrics gets none.
- The two thresholds (5 and 2 words) fit one score. A ballad with fewer than 5 syllables a bar under the singing staff is missed (no feature, never a wrong one). Real bars with all voices active are never sole, so no lead is invented there.
- An alternation inside a verse (call and response, one voice answering the other, 5 words each) would report each answer as a handover. None occurs in the real corpus today.
- A system that hides the empty staves of one lead voice (a Voice Lead M staff dropped where the male does not sing) has no pair to compare: no handover is read there, and the lead before stays as it was.
- Systems with no voice staves between two leads do not count as in between: a lead restated on the next voice system after an instrumental page is still the same feature, within the bar, mark and section limits.
- The bar of a handover in a first bar with no drawn left edge is approximate: bar counting starts at the first drawn barline.
