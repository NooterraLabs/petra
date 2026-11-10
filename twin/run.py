"""Run every steel component of a design through its kind's limit states, under the loads of
the card it answers, and report JSON."""

import itertools
from dataclasses import replace
from fractions import Fraction as F

from twin.card import parse
from twin.checks import DETAILING
from twin.fields import FieldError, Lines
from twin.kinds import KINDS, Out

MAX_INTERVALS = 8  # each interval doubles the runs: 2^8 = 256 at most


def envelope(loads, name):
    """Largest magnitude of each load field on one component, over every load case."""
    out = {}
    for entry in loads:
        if entry.target != name:
            continue
        magnitude = max(abs(entry.lo.value), abs(entry.hi.value))
        out[entry.field] = max(out.get(entry.field, F(0)), magnitude)
    return out


def _number(x):
    return None if x is None else float(x)


def _render(check, lrfd):
    available = check.available(lrfd)
    utilisation = check.demand / available if available else None
    return {
        "name": check.name,
        "mode": check.mode,
        "element": check.element,
        "clause": check.clause,
        "unit": check.unit,
        "nominal": _number(check.nominal),
        "available": _number(available),
        "demand": _number(check.demand),
        "utilisation": _number(utilisation),
        **({"note": check.note} if check.note else {}),
    }


def worst(runs):
    """One Out from the runs at every end of the component's intervals: each check where its
    utilisation is highest (its available strength lowest under no demand), with the notes and
    unsupported entries of every run."""
    if len(runs) == 1:
        return runs[0][1]
    first = runs[0][1]
    merged = Out(first.demand, first.lrfd)
    picked = {}
    for ends, out in runs:
        for check in out.checks:
            available = check.available(out.lrfd)
            score = (check.demand / available if available > 0 else float("inf"), -available)
            if check.name not in picked or score > picked[check.name][0]:
                picked[check.name] = (score, check, ends)
        merged.notes += [n for n in out.notes if n not in merged.notes]
        merged.unsupported += [u for u in out.unsupported if u not in merged.unsupported]
    for _, check, ends in picked.values():
        at = ", ".join(f"{var} {end}" for var, end in ends.items())
        note = "; ".join(filter(None, [check.note, f"worst of {len(runs)} interval ends, at {at}"]))
        merged.checks.append(replace(check, note=note))
    return merged


def check_component(component, loads, params=None):
    head = {"name": component.name, "kind": component.kind}
    if component.kind not in KINDS:
        return {**head, "status": "unsupported", "reason": f"the twin has no model for {component.kind}"}
    run, field = KINDS[component.kind]
    demands = envelope(loads, component.name)
    try:
        lines = Lines(component, params)
        basis = lines.word("basis")
        if basis not in ("lrfd", "asd"):
            raise FieldError(f"{component.name}: basis is lrfd or asd")
        intervals = lines.intervals()
        if len(intervals) > MAX_INTERVALS:
            return {**head, "status": "unsupported",
                    "reason": f"{len(intervals)} interval lengths; the twin checks every end of at most {MAX_INTERVALS}"}
        runs = []
        for pick in itertools.product(("lo", "hi"), repeat=len(intervals)):
            ends = dict(zip(intervals, pick))
            out = Out(demands.get(field, F(0)), basis == "lrfd")
            run(Lines(component, params, ends), out, demands)
            runs.append((ends, out))
    except (FieldError, KeyError) as err:
        return {**head, "status": "input_error", "reason": str(err).strip("'\"")}
    out = worst(runs)
    handled = {field, "shear"} if component.kind == "hanger" else {field}
    for extra in sorted(set(demands) - handled):
        out.unsupported.append(f"load field `{extra}` is not modeled; its checks are absent")
    rendered = [_render(c, out.lrfd) for c in out.checks]
    governing = max((r for c, r in zip(out.checks, rendered) if r["utilisation"] is not None
                     and (c.factor not in DETAILING or r["utilisation"] > 1)),
                    key=lambda r: r["utilisation"], default=None)
    return {
        **head,
        "status": "checked",
        "basis": basis,
        "demand": {k: float(v) for k, v in sorted(demands.items())},
        **({"intervals": {var: [float(i.lo), float(i.hi)] for var, i in intervals.items()}} if intervals else {}),
        "checks": rendered,
        "governing": None if governing is None else {"name": governing["name"], "utilisation": governing["utilisation"]},
        "notes": out.notes,
        "unsupported": out.unsupported,
    }


def check_text(card, design):
    """The report for the text of a card and of the design that answers it."""
    pair = parse(card, design)
    return {"twin": "clean-room AISC 360-22 connection twin",
            "components": [check_component(c, pair.loads, pair.params) for c in pair.components]}
