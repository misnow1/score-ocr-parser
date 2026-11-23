# 0004. Part files supplement the score; the score is the structure

Status: accepted

## Context

A conductor score prints solo markings over every staff, and its staff names can be ambiguous, so it often hides who plays a solo (see open solos and shared features in the glossary). A part has one instrument, so a solo marked in it is that instrument's.

The parts live in the mic-assignment planner repo, in a tree organised by instrument, with the conductor scores in `scores/`:

```
parts/<instrument-folder>/<song file>.pdf
```

Downloading and organising that tree is the planner repo's job, not this repo's.

The folder and the file do not always agree. A Clarinet part in the alto 1 folder, a piccolo part in the flute folder, a tuba part in a trombone folder and a flugelhorn part in a trumpet folder are doublings, not misfiles. Real misfiles also exist, and only knowledge of the show can tell the two apart.

## Decision

- **Parts add who plays what; the score stays the structure.** Sections (rehearsal marks), order and instrumentation come from the conductor score. A part supplies the instrument behind a solo.
- **Cross-reference by rehearsal mark first, bar second.** This follows the flow sheet rule of ADR 0003: section and order matter more than exact bar numbers.
- **The instrument folder is the player slot** (who plays it). **The filename is the instrument.** When they differ the part is read as a doubling of that player slot, not as a misfile.
- **The tool does not guess misfiles.** The person-to-chair/part mapping will come from the mic-assignment planner as metadata handed to this tool before parsing (a future release). Until then a folder and filename that disagree are recorded as a doubling.
- **Licensing.** Part files are unlicensed copies, like the scores. They are read in place only and never copied, rendered, committed or stored, and nothing quoted from them goes into tests, fixtures or docs. Tests use synthetic fixtures.

## Consequences

- The tool reads parts as a separate mode and merges their solos into the score's features. Without parts nothing changes: a score parses as it did before.
- A part can name a soloist the score only marks as an open solo or a shared feature. The score still decides the section and the order.
- A real misfile can put a solo on the wrong player until the planner metadata arrives. That is accepted over guessing.
- This repo never builds or fills the `parts/` tree. It reads a part from where the planner repo keeps it.
