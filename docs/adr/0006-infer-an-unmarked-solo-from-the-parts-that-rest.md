# 0006. Infer an unmarked solo from the parts that rest around one wind

Status: accepted

## Context

A solo is not always marked. The approved corpus facts (`tests/corpus/expected.yaml`) hold one: a Clarinet solo at one rehearsal mark that has no wording in the score and none in the Clarinet part: it is implied, because from the mark to almost the next one the Clarinet is the only wind playing and every other wind rests. The parts show this, since each part counts its multi-bar rests (part mode, ADR 0004).

This is the first feature the tool invents without a marking, so the risk is false positives: a quiet ballad, a verse under a vocal lead, a feature the score marks in words, a part that prints its rests another way, or a part that is not in the tree must never produce a solo. A solo that is not reported is cheap (the planner's flow sheet has it hand-edited); a solo that is invented costs a review.

## Decision

A stretch of the score is a **possible solo** of one instrument only when all of these hold. The stretch is the score's: the bars from one rehearsal-mark printing to the next, at least 4 bars, the last printing having no end (ADR 0003: sections and order first; a part is read by bar number against that range only to see where its rests fall).

- **The others are known.** Every wind of the score (woodwind, saxophone, trumpet, trombone, brass; strings count as melodic too) and every chair the score has is covered by a readable part. A part stands for its own instrument and chairs and for its player slot's (a Clarinet part in the alto 1 folder also stands for Alto Sax 1). If any is missing or unreadable, nothing is inferred and a warning says which winds had no part.
- **The stretch is read in every part.** A part's bars (`PartReport.bars`, runs of played and rested bars, a bar being rested when a multi-bar rest covers it) must cover at least 75% of the stretch. A part that does not (a staff the reader missed, a rest it did not count) makes the stretch not assessable: nothing is inferred and a warning says at which marks.
- **Exactly one melodic part plays, the others rest.** The one plays at least half of the stretch; every other melodic part rests at least 75% of it (a part that half plays is no clean rest), and at least 3 parts rest. The rhythm section and the vocals are not counted either way: a wind over the rhythm section alone is exactly the shape of a solo.
- **The silence is a contrast.** At least 2 of the resting parts play in another stretch of the song. Where the other winds never play at all, one wind carrying the song over the rhythm section is the arrangement, not a solo.
- **The score marks nothing there.** A stretch holding any score feature (a solo, a feature, an open solo, a vocal lead) is never inferred: a marked solo stays authoritative and is never duplicated (ADR 0004), and a wind over a vocal lead is a backing.

The feature is a `solo` of the playing part's instrument (its chair when the part names one), on the mark's page at the mark's first bar, in score order. Its confidence is 0.5, under the flow draft's TODO threshold, so every inferred solo carries a TODO; its reason says it was inferred from the other parts resting and from which bars. It only runs with a parts directory; without one the output is the same as before.

## Consequences

- Measured in place on the 21 real scores with parts: 5 stretches have exactly one melodic part playing and two or more resting, and one passes every condition (the Clarinet at the mark of the expected-failure fact that motivated this). The other four are stopped by a part that half plays (three) and by several conditions at once (one: missing parts, an unreadable part, a half-playing part and a marked feature). 8 of the 21 scores have no rehearsal-mark stretch to read, and 11 lack a part for some wind of the score, which turns the inference off for them. No false positive was seen.

- Without `--parts-dir` nothing changes: the scores' reports and flow drafts are byte-identical.
- That corpus fact stays an expected failure in score-only mode (the score alone cannot show it); with parts the Clarinet at that mark is reported as a possible solo. A new corpus fact needs the user's approval; this change adds none.
- Real songs often fail the first condition: a tree that lacks a part (a flute, a cello, a bass trombone) turns the inference off for that song, and the warning says why. This is deliberate: an absent part could be playing.
- A player who doubles has one part per instrument and plays only one at a time. If the tree has only one of a player's parts, a rest in it can hide that the player plays the other (an absent alto part while the clarinet part rests). The first condition covers the player by slot, not by instrument, so this residual risk stays; it is the reason the confidence is low.
- Parts that print rests another way (ticket #74) or count bars differently from the score read as unknown, never as resting: the stretch is skipped with a warning.
- The last stretch of a score has no end bar and is never inferred. A solo that spans several marks is inferred once per stretch it fills, each its own possible solo.
