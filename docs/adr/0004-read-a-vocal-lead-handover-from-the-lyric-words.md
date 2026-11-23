# 0004. Read a vocal lead handover from the lyric words under the lead staves

Status: accepted

## Context

Winter Wonderland hands the lead from the female to the male at rehearsal mark H with no wording at all: no "Male Lead" text and no "solo" over a staff. The female, the male and both backing staves are printed on every system, so the staves alone name no change. The first idea was to read notes and rests from the music font glyphs. That did not hold up: the glyph codes depend on the font (Opus, Maestro, Finale private-use codes), notes above a staff fall outside its band, and rests and notes share one band when staves sit 27 pt apart.

Lyrics are plain text in the text layer, in the same place under every score's voice staves. In the real score the lead that sings has 5 to 12 words under its staff in a bar, a staff that is resting has none, and a backing staff sings fewer.

## Decision

- **Evidence.** A lead staff (a "Voice Lead F" or "Voice Lead M" label, the only labels that name a voice) sings in a bar when at least 5 lyric words sit in the band 0.2 to 0.55 of the staff gap below its centre, between two drawn barlines. A word has a letter and is not a dynamic ("mf", "cresc."). Annotation text printed above the next staff sits lower in that gap and stays out.
- **Sole lead.** A bar belongs to one voice when that lead staff sings and every other lead staff has fewer than 2 words. Backing staves do not count: a male lead over singing backings is still a male lead.
- **Handover.** The lead at any point is the voice of the last lead marked in text on an earlier system, else the last voice that sang alone. A bar whose sole lead differs from it is a handover: a vocal lead for the new voice, voice from the staff label only, confidence 0.1 under a bare solo over a Voice Lead staff (0.7 with a counted bar), so the flow draft gets a TODO. The first voice to sing alone starts the count and gets no feature, since nothing was handed over.
- **One feature.** Handover candidates join the normal merge. When the handover has text ("Male Lead Verse 2") the text candidate and the handover are one feature, with the text's confidence.
- **Page turn.** A vocal lead restated on the next page's voice system joins the feature before it anywhere in the row (not only in its first bar), within 16 bars, unless another voice's lead was marked in between.

## Consequences

- Scores with no "Voice Lead" pair (a choir label, a "VOCALS" group) never get a handover: the voice would be a guess. Measured in place on the real corpus, only Winter Wonderland has the pair, so no other score changes.
- Scans have no drawn barlines and no handover. A score whose voices sing "oo" and "ah" counts those as words; one that prints no lyrics gets none.
- The two thresholds (5 and 2 words) fit one score. A ballad with fewer than 5 syllables a bar under the singing staff is missed (no feature, never a wrong one). Real bars with all voices active are never sole, so no lead is invented there.
- An alternation inside a verse (call and response, one voice answering the other, 5 words each) would report each answer as a handover. None occurs in the real corpus today.
