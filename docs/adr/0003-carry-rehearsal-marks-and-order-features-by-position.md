# 0003. Carry rehearsal marks across pages and order features by position

Status: accepted

## Context

The flow draft needs, for each feature, the section it falls in (verse, chorus, bridge: the rehearsal mark) and its order among the other features. Exact bar numbers matter less than getting section and order right.

Since #23 a rehearsal mark never carried onto a page where none was printed. That fixed a stale B shown on a page far past it, but it was a workaround for marks the tool could not yet read. A feature on a page with no printed mark ended up with no section, so a vocal lead in a real score had none.

`report.features` was in reading order: systems page by page, and within a system by staff row, then x. A solo on a lower staff could come before an earlier one on a higher staff.

## Decision

- **Carry the mark.** The mark in force for a feature is the last one printed before it in reading order, on its own page or any earlier one. A feature before the first mark of the score has no mark. This reverses the page-scoped rule of #23.
- **Flag a carried mark.** A feature whose mark is printed on an earlier page has `mark_carried_from` set to that page, the reason "mark carried from p15", and confidence 0.05 lower. The flow note reads "rehearsal C (carried from page 15)".
- **Order by position.** Features are sorted by page, then bar, then x position of the first location, once, in `find_features`. A feature with no bar follows the barred ones on its page, by x. A shared or merged feature sorts by its first location. The sort is stable, so ties keep reading order.
- **Group the flow by section.** The flow keeps one step per feature in score order. The rendered draft puts a comment header before each run of steps under one mark (`# Section B`); a feature with no mark goes under `# (no section)` with a TODO. Steps keep the planner's shape (`section`, `instrument`, `note`): no `kind`, `position` or DS fields.
- **Corpus facts** can assert order and section without exact bars: `order` (features in this relative order) and `section` (the mark).

## Consequences

- A feature can report a mark that is no longer current, if the score prints no mark for a long stretch or a mark is missed by the reader. The `carried` flag, reason and lower confidence make this visible; a missed mark is still a reading gap to fix at its source.
- A score whose marks restart (the same letter reused after a repeat) groups as consecutive runs, in score order, not as one group per letter.
- Mixed bar-known and bar-unknown features on one page order the barred ones first. Scans with bar numbers missing everywhere fall back to page and x.
- Exact bars stay secondary: the Jingle Bells trombone at bars 44 versus 45 and 52 versus 53 keeps its order and section either way.
