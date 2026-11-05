"""Safe envelopes: the widest interval of one input, around an anchor value, over which
every obligation that depends on that input is proved.

    lola envelope FILE --input NAME --from LO --to HI [--at X] [--resolution R] [--max-probes N]

Untrusted. This module only chooses which designs to check. Each probe is the design with
the one input's range replaced by an interval, checked by pipeline.check_design like any
other design, so every interval reported as proved is a PASS the pipeline assembled from
kernel theorems.

Why bisection is sound. A claim is a statement for all values of its inputs, so a proof
over [a, b] proves it over every interval inside [a, b], and proofs over [a, m] and
[m, b] together prove it over [a, b]. Whether [anchor, x] passes is therefore monotone
in x, and a binary search on x finds the end of the proved interval to within the
resolution. A counterexample or a margin point fixes the input at some value v, and
every interval that holds v contains that point, so no interval through v passes: the
search stops growing there at once. None of this needs the design to be monotone in the
input.

The input is replaced by an assumption that names this command as its owner, never by
the owner's signature: the owner signed the range the design states, not the one being
probed. A probe range may run past the signed one; that is how the envelope tells how
much headroom the design has.

Obligations whose statements do not mention the input cannot change from probe to probe,
so they are set aside and reported once ("elsewhere"). The probe statuses, and the
envelope, count only the obligations that depend on the input. An input that declares a
mean is refused, since a probe interval need not contain it.

The search is bounded. It runs at most `max_probes` checks (anchor and confirm included;
the rest split between the two sides), and the resolution is never finer than the probe
range over 2^20, since a gap of 1e-25 near a limit can cost one probe minutes of box
search. A side the cap stops says so, with its undecided gap.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType
from typing import Iterable

from .ir import Bound, Design, Input, InputKind, Signature, Span
from .kernel import Interval, RangeHyp, Statement
from .models.base import ComponentError
from .pipeline import EvidenceSource, Report, check_design, lower_components, signed_inputs
from .premises import input_label, param_label
from .registry import Registry
from .units import Dim, Quantity, quantity_text, si_unit
from .verdict import SEVERITY, Discharged, Open, Outcome, Refuted, Waived, WithinMargin

PROBE_OWNER = "lola envelope"
"""The owner named on a probed input's premise."""

DEFAULT_STEPS = 64
"""Without --resolution, the resolution is the probe range's width over this."""

FINEST_STEPS = 2 ** 20
"""The resolution is never finer than the probe range's width over this."""

DEFAULT_MAX_PROBES = 64
"""Without --max-probes, the most checks one envelope runs."""


class EnvelopeError(ValueError):
    """The request cannot be answered: an unknown input, a probe range of the wrong
    dimension, an anchor outside it, or an input no obligation depends on. The CLI
    reports it as an input error."""


@dataclass(frozen=True)
class Target:
    """The input or param being probed, as the design states it."""

    name: str
    label: str
    dim: Dim
    stated: Interval
    span: Span | None       # the bound's place in the source; None for a param

    @property
    def unit(self) -> str:
        return si_unit(self.dim)


@dataclass(frozen=True)
class Probe:
    """One check of the design with the input over [lo, hi]. `status` is the most severe
    status among the obligations that depend on the input, or "INVALID" when the probed
    design does not lower (a component refuses the range). `at` is the input's value at
    the counterexample or margin point that set the status, when there is one."""

    lo: Fraction
    hi: Fraction
    status: str
    why: str
    at: Fraction | None
    report: Report | None


@dataclass(frozen=True)
class Side:
    """How far the proved interval reaches on one side of the anchor. `proved` is its end;
    `limit` is the nearest value known not to pass, or the probe range's end when the
    whole side passed; `blocker` is the probe that set `limit`, None in that case."""

    proved: Fraction
    limit: Fraction
    blocker: Probe | None
    capped: bool = False    # the probe limit stopped the bisection before the resolution


@dataclass(frozen=True)
class Envelope:
    target: Target
    lo: Fraction
    hi: Fraction
    anchor: Fraction
    resolution: Fraction
    start: Probe                  # the probe at the anchor alone
    below: Side | None            # None when the anchor itself does not pass
    above: Side | None
    confirm: Probe | None         # one check over the whole proved interval
    elsewhere: str                # the status of the obligations that do not depend on the input
    elsewhere_open: tuple[str, ...]   # those of them that are not proved
    probes: tuple[Probe, ...]
    max_probes: int = DEFAULT_MAX_PROBES
    notes: tuple[str, ...] = ()   # a raised resolution or a side the probe limit stopped

    @property
    def safe(self) -> tuple[Fraction, Fraction] | None:
        return None if self.below is None or self.above is None else (self.below.proved, self.above.proved)


def find_target(design: Design, registry: Registry, name: str) -> Target:
    """A param by its name, or a signed input by its label stem: "ambient", a component
    field such as "lighting.supply.fault_current", or a load entry such as
    "lamp_draw.lighting.lamps.current"."""
    if name in design.params:
        p = design.params[name]
        return Target(name, param_label(design.name, name), p.range.dim, p.range.value, None)
    inputs = tuple(signed_inputs(design, lower_components(design, registry)))
    found = {i.span: i for i in inputs if i.name == name}
    if not found:
        known = sorted({i.name for i in inputs} | set(design.params))
        raise EnvelopeError(f"{design.name} has no input or param named {name!r}; it has {', '.join(known) or 'none'}")
    if len(found) > 1:
        raise EnvelopeError(f"{name!r} names {len(found)} bounds in {design.name}; an envelope probes one")
    (inp,) = found.values()
    if inp.mean is not None:
        raise EnvelopeError(f"{name} declares a mean, which a probe interval need not contain; an envelope over it is not supported")
    return Target(name, input_label(design.name, name), inp.range.dim, inp.range.value, inp.span)


def narrow(design: Design, target: Target, lo: Fraction, hi: Fraction) -> Design:
    """The design with the target's range replaced by [lo, hi], assumed by PROBE_OWNER."""
    q = Quantity(Interval(lo, hi), target.dim)
    if target.span is None:
        p = design.params[target.name]
        return dataclasses.replace(design, params=MappingProxyType({**design.params, target.name: dataclasses.replace(p, range=q)}))
    signature = Signature(PROBE_OWNER, f"probe of {target.name} over {quantity_text(q)}")
    hits = 0

    def swap(value):
        nonlocal hits
        if isinstance(value, (Input, Bound)) and value.span == target.span:
            hits += 1
            return dataclasses.replace(value, range=q, signature=signature, kind=InputKind.ASSUMED)
        return value

    ambient = swap(design.ambient)
    loads = {
        name: dataclasses.replace(case, entries=tuple(dataclasses.replace(e, value=swap(e.value)) for e in case.entries))
        for name, case in design.loads.items()
    }
    components = {
        name: dataclasses.replace(c, attrs=tuple(dataclasses.replace(a, args=tuple(swap(x) for x in a.args)) for a in c.attrs))
        for name, c in design.components.items()
    }
    if hits != 1:
        raise EnvelopeError(f"the bound of {target.name} was found {hits} times in {design.name}, not once")
    return dataclasses.replace(design, ambient=ambient, loads=MappingProxyType(loads), components=MappingProxyType(components))


def envelope(
    design: Design,
    registry: Registry,
    name: str,
    lo: Quantity,
    hi: Quantity,
    sources: tuple[EvidenceSource, ...],
    at: Quantity | None = None,
    resolution: Quantity | None = None,
    max_probes: int = DEFAULT_MAX_PROBES,
) -> Envelope:
    """Probe the anchor, then grow the proved interval down to `lo` and up to `hi` by
    bisection until each side's undecided gap is at most the resolution or the probe
    limit is reached, then check the whole proved interval once more. The anchor defaults
    to the middle of the input's stated range when that lies in [lo, hi], else to the
    middle of [lo, hi]. `max_probes` is at least 4: the anchor, one probe per side and
    the confirming check."""
    target = find_target(design, registry, name)
    for what, q in (("--from", lo), ("--to", hi), ("--at", at), ("--resolution", resolution)):
        if q is not None and q.dim != target.dim:
            raise EnvelopeError(f"{what} must be in {target.unit}, the unit of {name}")
    a, b = lo.value.lo, hi.value.lo
    if not a < b:
        raise EnvelopeError(f"the probe range must run upward, got {quantity_text(lo)} to {quantity_text(hi)}")
    middle = (target.stated.lo + target.stated.hi) / 2
    anchor = at.value.lo if at is not None else middle if a <= middle <= b else (a + b) / 2
    if not a <= anchor <= b:
        raise EnvelopeError(f"the anchor {quantity_text(Quantity(Interval(anchor, anchor), target.dim))} lies outside the probe range")
    step = resolution.value.lo if resolution is not None else (b - a) / DEFAULT_STEPS
    if step <= 0:
        raise EnvelopeError("the resolution must be positive")
    if max_probes < 4:
        raise EnvelopeError(f"--max-probes must be at least 4 (the anchor, one probe per side and the confirming check), got {max_probes}")
    notes: list[str] = []
    finest = (b - a) / FINEST_STEPS
    if step < finest:
        notes.append(f"resolution raised from {quantity_text(Quantity(Interval(step, step), target.dim))} to {quantity_text(Quantity(Interval(finest, finest), target.dim))}, the probe range over 2^20")
        step = finest

    probes: list[Probe] = []

    def probe(x: Fraction, y: Fraction) -> Probe:
        try:
            report = check_design(narrow(design, target, x, y), registry, sources)
        except ComponentError as exc:
            p = Probe(x, y, "INVALID", "; ".join(exc.problems), None, None)
        else:
            p = Probe(x, y, *_assess(report.outcomes, target.label), report)
        probes.append(p)
        return p

    start = probe(anchor, anchor)
    if start.report is not None and not any(_depends(o, target.label) for o in start.report.outcomes):
        raise EnvelopeError(f"no obligation of {design.name} depends on {name}")
    elsewhere, elsewhere_open = _elsewhere(() if start.report is None else start.report.outcomes, target.label)
    if start.status != "PASS":
        return Envelope(target, a, b, anchor, step, start, None, None, None, elsewhere, elsewhere_open, tuple(probes), max_probes, tuple(notes))
    budget = max_probes - 2
    below = _grow(lambda x: probe(x, anchor), anchor, a, step, -1, budget // 2)
    above = _grow(lambda x: probe(anchor, x), anchor, b, step, +1, max_probes - 1 - len(probes))
    for name, side in (("below", below), ("above", above)):
        if side.capped:
            gap = quantity_text(Quantity(Interval(abs(side.limit - side.proved), abs(side.limit - side.proved)), target.dim))
            notes.append(f"the {name} side stopped at the limit of {max_probes} checks with {gap} undecided; raise --max-probes or --resolution")
    confirm = probe(below.proved, above.proved) if below.proved < above.proved else None
    return Envelope(target, a, b, anchor, step, start, below, above, confirm, elsewhere, elsewhere_open, tuple(probes), max_probes, tuple(notes))


def _grow(probe, anchor: Fraction, end: Fraction, step: Fraction, sign: int, budget: int) -> Side:
    """Bisect for the farthest x toward `end` such that the interval from the anchor to x
    passes, with at most `budget` probes (at least one). `probe(x)` checks that
    interval."""
    if end == anchor:
        return Side(anchor, anchor, None)
    first = probe(end)
    if first.status == "PASS":
        return Side(end, end, None)
    good, bad, blocker = anchor, _limit(first, anchor, end, sign), first
    used = 1
    while abs(bad - good) > step:
        if used >= budget:
            return Side(good, bad, blocker, capped=True)
        mid = (good + bad) / 2
        p = probe(mid)
        used += 1
        if p.status == "PASS":
            good = mid
        else:
            bad, blocker = _limit(p, good, mid, sign), p
    return Side(good, bad, blocker)


def _limit(p: Probe, good: Fraction, x: Fraction, sign: int) -> Fraction:
    """The nearest value known not to pass: the input's value at the probe's point when
    it lies past the proved end, else the probe's far end."""
    if p.at is not None and (good < p.at <= x if sign > 0 else x <= p.at < good):
        return p.at
    return x


_STATUS = {Discharged: "PASS", WithinMargin: "MARGINAL", Open: "UNKNOWN", Refuted: "FAIL"}


def _statement(outcome: Outcome) -> Statement | None:
    if isinstance(outcome, (Discharged, Refuted, WithinMargin)):
        return outcome.obligation.statement
    return outcome.statement if isinstance(outcome, Open) else None


def _depends(outcome: Outcome, label: str) -> bool:
    statement = _statement(outcome)
    return statement is not None and any(isinstance(h, RangeHyp) and h.label == label for h in statement.hyps)


def _assess(outcomes: Iterable[Outcome], label: str) -> tuple[str, str, Fraction | None]:
    """(status, why, the input's value at its point) over the outcomes that depend on the
    input: the first outcome of the most severe status."""
    worst: Outcome | None = None
    for o in outcomes:
        if _depends(o, label) and (worst is None or SEVERITY[_STATUS[type(o)]] > SEVERITY[_STATUS[type(worst)]]):
            worst = o
    if worst is None:
        return "PASS", "", None
    status = _STATUS[type(worst)]
    if isinstance(worst, Discharged):
        return status, "", None
    if isinstance(worst, Open) and worst.near is None:
        return status, f"{worst.requirement.id} is neither proved nor refuted", None
    refutation = worst.near.refutation if isinstance(worst, Open) else worst.refutation
    point = dict(refutation.point)
    sym = next(h.sym for h in refutation.statement.hyps if isinstance(h, RangeHyp) and h.label == label)
    what = ("is refuted" if isinstance(worst, Refuted) else "is proved and comes within its margin" if isinstance(worst, WithinMargin)
            else "is neither proved nor refuted, and comes within its margin")
    return status, f"{_id(worst)} {what} at this point", point[sym]


def _elsewhere(outcomes: Iterable[Outcome], label: str) -> tuple[str, tuple[str, ...]]:
    rest = [o for o in outcomes if not isinstance(o, Waived) and not _depends(o, label)]
    if not rest:
        return "NONE", ()
    status = max((_STATUS[type(o)] for o in rest), key=SEVERITY.__getitem__)
    return status, tuple(dict.fromkeys(_id(o) for o in rest if not isinstance(o, Discharged)))


def _id(outcome: Outcome) -> str:
    return outcome.requirement.id if isinstance(outcome, Open) else outcome.obligation.requirement.id


# --- Reports -------------------------------------------------------------------------


def _q(env: Envelope, x: Fraction) -> str:
    return quantity_text(Quantity(Interval(x, x), env.target.dim))


def _iv(env: Envelope, x: Fraction, y: Fraction) -> str:
    return quantity_text(Quantity(Interval(x, y), env.target.dim))


def _side_text(env: Envelope, side: Side) -> str:
    if side.blocker is None:
        return f"proved to {_q(env, side.proved)}, the end of the probe range"
    p = side.blocker
    where = f" with {env.target.name} = {_q(env, p.at)}" if p.at is not None else ""
    why = f" ({p.why}{where})" if p.why else ""
    gap = abs(side.limit - side.proved)
    capped = ", stopped at the probe limit" if side.capped else ""
    return f"proved to {_q(env, side.proved)}; {_q(env, side.limit)} is not: {p.status}{why}; {_q(env, gap)} undecided{capped}"


def render(env: Envelope) -> str:
    t = env.target
    lines = []
    if env.safe is None:
        why = f" ({env.start.why}{f' with {t.name} = {_q(env, env.start.at)}' if env.start.at is not None else ''})" if env.start.why else ""
        lines.append(f"envelope   none: at {t.name} = {_q(env, env.anchor)} the design is {env.start.status}{why}")
    else:
        lo, hi = env.safe
        confirmed = "one check over the whole interval passes" if env.confirm is not None and env.confirm.status == "PASS" else (
            f"the check over the whole interval is {env.confirm.status}, so it rests on the two checks either side of the anchor" if env.confirm is not None
            else "a single point")
        lines.append(f"envelope   {t.name} in {_iv(env, lo, hi)}: every obligation that depends on it is proved ({confirmed})")
    lines.append(f"input      {t.label}, stated {_iv(env, t.stated.lo, t.stated.hi)}; probed {_iv(env, env.lo, env.hi)} from {_q(env, env.anchor)}, resolution {_q(env, env.resolution)}")
    if env.below is not None and env.above is not None:
        lines.append(f"below      {_side_text(env, env.below)}")
        lines.append(f"above      {_side_text(env, env.above)}")
    if env.elsewhere != "NONE":
        others = f": {', '.join(env.elsewhere_open)}" if env.elsewhere_open else ""
        lines.append(f"elsewhere  the obligations that do not depend on {t.name} are {env.elsewhere}{others}")
    lines += [f"note       {n}" for n in env.notes]
    lines.append(f"probes     {len(env.probes)} checks (limit {env.max_probes})")
    for p in env.probes:
        lines.append(f"  {_iv(env, p.lo, p.hi):<32} {p.status}")
    return "\n".join(lines)


def to_json(env: Envelope) -> dict:
    """Values are exact rationals in SI base units (degC for temperature), as strings."""
    t = env.target

    def side(s: Side | None) -> dict | None:
        if s is None:
            return None
        b = s.blocker
        return {"proved": str(s.proved), "limit": str(s.limit), "status": None if b is None else b.status,
                "why": None if b is None else b.why, "at": None if b is None or b.at is None else str(b.at), "capped": s.capped}

    safe = env.safe
    return {
        "design": None if env.start.report is None else env.start.report.design,
        "input": t.name,
        "label": t.label,
        "unit": t.unit,
        "stated": [str(t.stated.lo), str(t.stated.hi)],
        "probe": [str(env.lo), str(env.hi)],
        "anchor": str(env.anchor),
        "resolution": str(env.resolution),
        "anchor_status": env.start.status,
        "safe": None if safe is None else [str(safe[0]), str(safe[1])],
        "confirmed": None if env.confirm is None else env.confirm.status,
        "below": side(env.below),
        "above": side(env.above),
        "elsewhere": {"status": env.elsewhere, "open": list(env.elsewhere_open)},
        "notes": list(env.notes),
        "max_probes": env.max_probes,
        "probes": [{"range": [str(p.lo), str(p.hi)], "status": p.status} for p in env.probes],
    }
