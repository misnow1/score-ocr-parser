"""Flow draft: planner `numbers/*.yaml` flow steps built from features.

Steps carry only `section`, `instrument` and `note`. The planner owns whether a
number is vocal or instrumental (`kind`) and downstage positions (`position`),
so this module never emits either. Steps come in score order; the rendered
draft puts a comment header before each run of steps under one rehearsal mark.
"""

import json

from .models import Feature, FlowStep

LOW_CONFIDENCE = 0.8  # below this a step gets a TODO(score-parser) comment
NO_SECTION = "(no section)"  # header over steps with no rehearsal mark
NO_MARK_TODO = "no rehearsal mark found: section unknown"


def _named(instrument: str, chair: int | None) -> str:
    return f"{instrument} {chair}" if chair else instrument


def _rehearsal(f: Feature) -> str:
    """The note's rehearsal-mark part, saying where a carried mark is printed."""
    carried = f" (carried from page {f.mark_carried_from})" if f.mark_carried_from else ""
    return f"rehearsal {f.rehearsal_mark}{carried}"


def _shared_step(f: Feature) -> FlowStep:
    """One step naming every instrument (and chair) the marking is shared by."""
    names = [_named(f.instrument or "Unknown instrument", f.chair)]
    names += [_named(p.instrument, p.chair) for p in f.shared_with]
    ambiguous = [n for n, c in zip(names, [f.chair_ambiguous, *(p.chair_ambiguous for p in f.shared_with)]) if c]
    section = f"{', '.join(names[:-1])} and {names[-1]} {f.kind}"
    section += f" ({f.rehearsal_mark})" if f.rehearsal_mark else ""
    where = [f"page {f.page}"]
    if f.bar is not None:
        where.append(f"bar {f.bar}")
    if f.rehearsal_mark:
        where.append(_rehearsal(f))
    if ambiguous:
        where.append(f"chair ambiguous for {', '.join(ambiguous)} (shared staff)")
    note = f"{', '.join(where)}; confidence {f.confidence:g}"
    todo = None
    if f.confidence < LOW_CONFIDENCE:
        todo = f"low confidence ({f.confidence:g}): " + "; ".join(f.reasons)
    elif ambiguous:
        todo = "chair ambiguous: " + "; ".join(f.reasons)
    return FlowStep(section, ", ".join(n.lower() for n in names), note, todo, f.rehearsal_mark)


def _step(f: Feature) -> FlowStep:
    if f.shared_with:
        return _shared_step(f)
    vocal = f.kind == "vocal lead"
    if vocal:
        who = f"{f.voice.capitalize()} vocal lead" if f.voice else "Vocal lead"
        who += f", {f.section}" if f.section else ""
    else:
        who = f"{f.instrument or 'Unknown instrument'} {f.kind}"
    section = who + (f" ({f.rehearsal_mark})" if f.rehearsal_mark else "")
    where = [f"page {f.page}"]
    if f.bar is not None:
        where.append(f"bar {f.bar}")
    if f.rehearsal_mark:
        where.append(_rehearsal(f))
    if f.chair:
        where.append(f"chair {f.chair}")
    elif f.chair_ambiguous:
        where.append("chair ambiguous (shared staff)")
    note = f"{', '.join(where)}; confidence {f.confidence:g}"
    todo = None
    if f.confidence < LOW_CONFIDENCE or (f.instrument is None and not vocal):
        todo = f"low confidence ({f.confidence:g}): " + "; ".join(f.reasons)
    elif f.chair_ambiguous:
        todo = "chair ambiguous: " + "; ".join(f.reasons)
    who = "vocal" if vocal else (f.instrument or "unknown").lower()
    return FlowStep(section, who, note, todo, f.rehearsal_mark)


def _flag_no_section(step: FlowStep) -> FlowStep:
    """A step with no rehearsal mark gets a TODO (added to any other)."""
    if step.mark is None:
        step.todo = f"{step.todo}; {NO_MARK_TODO}" if step.todo else NO_MARK_TODO
    return step


def build_flow(features: list[Feature]) -> list[FlowStep]:
    return [_flag_no_section(_step(f)) for f in features]


def render_yaml(flow: list[FlowStep], header: str = "") -> str:
    """The draft file text. JSON strings are valid YAML double-quoted scalars."""
    lines = [f"# {ln}" for ln in header.splitlines()]
    lines.append("flow:")
    for i, s in enumerate(flow):
        if i == 0 or s.mark != flow[i - 1].mark:  # a new run of steps under one mark
            lines.append(f"  # Section {s.mark}" if s.mark else f"  # {NO_SECTION}")
        q = json.dumps
        lines.append(
            f"  - {{ section: {q(s.section)}, instrument: {q(s.instrument)}, note: {q(s.note)} }}"
        )
        if s.todo:
            lines.append(f"    # TODO(score-parser): {s.todo}")
    if not flow:
        lines[-1] = "flow: []"
    return "\n".join(lines) + "\n"
