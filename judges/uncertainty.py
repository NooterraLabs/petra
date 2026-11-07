"""A demand's capacity against its own tests: does an overload claim survive a tested failure?

Petra's range-and-mean bound reads the capacity as a hard range, every use's capacity at
least its lower end C_lo. A `tests` record on the same demand with a failure at a level L
below C_lo shows a part that broke under less than C_lo, so the stated range is false at
its low end; the highest capacity consistent with that failure is L. The judge computes
the bound itself and flags a P(utilisation > u) <= p claim that holds with the capacity
at C_lo and fails with it at L, and leaves a claim its own bound already breaks
undecided.

Over every distribution of a force X on [a, b] with mean m, the least upper bound of
P(X > t) is 1 when t < m, (m - a) / (t - a) when m <= t < b, and 0 when t >= b: the mass
sits at a and just above t. The threshold is u C at the least u and C, as Petra takes it.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from petra.ir import Bound, Component, Design, Exceeds, Input, RangeMean


@dataclass(frozen=True)
class TestedBelow:
    subject: str
    p: Fraction
    stated: Fraction       # the bound at the stated capacity's lower end
    witnessed: Fraction    # the bound at the tested failure level
    capacity: Fraction     # N
    level: Fraction        # N
    tests: str

    def check(self) -> tuple[str, str] | None:
        if self.stated <= self.p < self.witnessed:
            return "uncertain.capacity.tested", (
                f"tests {self.tests} broke a part at {float(self.level) / 1000:g} kN, below the stated capacity's "
                f"{float(self.capacity) / 1000:g} kN; at that capacity the probability bound is {float(self.witnessed):.4g}, "
                f"above the claimed {float(self.p):g} ({float(self.stated):.4g} at the stated capacity)")
        return None


def exceedance(a: Fraction, b: Fraction, m: Fraction, t: Fraction) -> Fraction:
    """sup P(X > t) over distributions on [a, b] with mean m."""
    if t >= b:
        return Fraction(0)
    if t < m:
        return Fraction(1)
    return Fraction(0) if t == a else (m - a) / (t - a)


def facts(component: Component, design: Design) -> tuple[list[TestedBelow], list[str]]:
    name = component.name
    bounds = [a.args[0] for a in component.attrs if a.key == "capacity" and len(a.args) == 1 and isinstance(a.args[0], Bound)]
    if len(bounds) != 1:
        return [], [f"{name}: no single capacity bound"]
    capacity = bounds[0].range.value.lo
    broke = [(t.level.value.hi, t.name) for t in design.tests.values() if t.subject == (name,) and t.failures > 0]
    if not broke:
        return [], []
    level, tests = min(broke)
    if level >= capacity:
        return [], []
    out, undecided = [], []
    for claim in design.probability_claims:
        event = claim.event
        if not (isinstance(claim.method, RangeMean) and isinstance(event, Exceeds) and event.qoi.path == (name,)):
            continue
        force = next((e.value for e in design.loads[event.under].entries if e.target == (name,)), None)
        subject = f"{name} claim {claim.name} under {event.under}"
        if not isinstance(force, Input) or force.mean is None:
            undecided.append(f"{subject}: the load has no signed range and mean")
            continue
        a, b, m, u = force.range.value.lo, force.range.value.hi, force.mean.value.lo, event.threshold.value.lo
        stated, witnessed = exceedance(a, b, m, u * capacity), exceedance(a, b, m, u * level)
        if stated > claim.p:
            undecided.append(f"{subject}: the judge's own bound at the stated capacity, {float(stated):.4g}, already "
                             f"exceeds {float(claim.p):g}")
            continue
        out.append(TestedBelow(subject, claim.p, stated, witnessed, capacity, level, tests))
    return out, undecided
