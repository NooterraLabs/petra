"""Run every steel component of a card through its kind's limit states and report JSON."""

from fractions import Fraction as F

from twin.card import parse
from twin.fields import FieldError, Lines
from twin.kinds import KINDS, Out


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


def check_component(component, loads):
    head = {"name": component.name, "kind": component.kind}
    if component.kind not in KINDS:
        return {**head, "status": "unsupported", "reason": f"the twin has no model for {component.kind}"}
    run, field = KINDS[component.kind]
    lines = Lines(component)
    demands = envelope(loads, component.name)
    try:
        basis = lines.word("basis")
        if basis not in ("lrfd", "asd"):
            raise FieldError(f"{component.name}: basis is lrfd or asd")
        out = Out(demands.get(field, F(0)), basis == "lrfd")
        run(lines, out, demands)
    except (FieldError, KeyError) as err:
        return {**head, "status": "input_error", "reason": str(err).strip("'\"")}
    handled = {field, "shear"} if component.kind == "hanger" else {field}
    for extra in sorted(set(demands) - handled):
        out.unsupported.append(f"load field `{extra}` is not modeled; its checks are absent")
    rendered = [_render(c, out.lrfd) for c in out.checks]
    governing = max((r for r in rendered if r["utilisation"] is not None),
                    key=lambda r: r["utilisation"], default=None)
    return {
        **head,
        "status": "checked",
        "basis": basis,
        "demand": {k: float(v) for k, v in sorted(demands.items())},
        "checks": rendered,
        "governing": None if governing is None else {"name": governing["name"], "utilisation": governing["utilisation"]},
        "notes": out.notes,
        "unsupported": out.unsupported,
    }


def check_text(text):
    card = parse(text)
    return {"twin": "clean-room AISC 360-22 connection twin", "components": [check_component(c, card.loads) for c in card.components]}
