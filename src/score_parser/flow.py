"""Flow draft: planner `numbers/*.yaml` flow steps built from features.

Steps carry only `section`, `instrument` and `note`. The planner owns whether a
number is vocal or instrumental (`kind`) and downstage positions (`position`),
so this module never emits either.
"""

import json

from .models import Feature, FlowStep

LOW_CONFIDENCE = 0.8  # below this a step gets a TODO(score-parser) comment


def _step(f: Feature) -> FlowStep:
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
        where.append(f"rehearsal {f.rehearsal_mark}")
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
    return FlowStep(section, who, note, todo)


def build_flow(features: list[Feature]) -> list[FlowStep]:
    return [_step(f) for f in features]


def render_yaml(flow: list[FlowStep], header: str = "") -> str:
    """The draft file text. JSON strings are valid YAML double-quoted scalars."""
    lines = [f"# {ln}" for ln in header.splitlines()]
    lines.append("flow:")
    for s in flow:
        q = json.dumps
        lines.append(
            f"  - {{ section: {q(s.section)}, instrument: {q(s.instrument)}, note: {q(s.note)} }}"
        )
        if s.todo:
            lines.append(f"    # TODO(score-parser): {s.todo}")
    if not flow:
        lines[-1] = "flow: []"
    return "\n".join(lines) + "\n"
