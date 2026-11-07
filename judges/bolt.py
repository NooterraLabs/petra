"""Bolted-joint separation: does a tension claim survive the joint opening?

Petra's joint model shares a concentric external force F between the bolts and the
clamped plates, F_bolt = F_V + Phi F / n, which holds only while the plates stay pressed
together. Once the force takes back the whole preload, (1 - Phi) F / n > F_V, the plates
part and each bolt carries F / n, whatever Phi says. So the bolt force at every point of
the design's box is max(F_V + Phi F / n, F / n), and its upper end is
max(sup (F_V + Phi F / n), F_hi / n). The judge flags a tension claim that holds on the
first and fails on the second, and leaves a claim its own linear sum already breaks
undecided, since then it cannot isolate the opening.

The grammar draws a joint as a bolt id, a count and the plates' material and thickness,
with no bolt length, hole, edge distance or washer, so grip, edge and pull-through fit are
not decided, and no load share is too small, since a force put in near the interface
takes Phi toward 0. Separation is the condition the lines do decide.

The judge reads the thread from the bolt's id (M12 -> d = 12 mm) with the ISO 261 coarse
pitch and takes the stress area from ISO 724, As = pi / 4 ((d2 + d3) / 2)^2. A claim's
utilisation is a fraction of the class's proof stress times As (ISO 898-1 Sp, else the
ISO 3506-1 0.2 % proof strength), which the judge reads from the registry as the claim's
meaning. Without a tension claim it judges the proof load, utilisation 1, which Petra's
coverage demands of every joint.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction

from petra.ir import Bound, Component, Design, Fixed, Input, ParamRef, Ref, Rel
from petra.registry import Registry

COARSE_PITCH_MM = {6: Fraction(1), 8: Fraction(5, 4), 10: Fraction(3, 2), 12: Fraction(7, 4), 16: Fraction(2),
                   20: Fraction(5, 2), 24: Fraction(3), 30: Fraction(7, 2), 36: Fraction(4)}
"""ISO 261 coarse pitch by nominal diameter, mm."""


@dataclass(frozen=True)
class Opening:
    subject: str
    limit: float          # N: the claim's bound on the bolt force
    clamped: float        # N: the linear sum's upper end, joint closed
    opened: float         # N: F_hi / n, the bolt force once the joint opens
    preload: float        # N: the least preload, T_lo / (K_hi d)

    def check(self) -> tuple[str, str] | None:
        if self.clamped <= self.limit < self.opened:
            return "bolt.tension.separation", (
                f"preload down to {self.preload / 1000:.4g} kN lets the joint open, so each bolt carries "
                f"{self.opened / 1000:.4g} kN, above the claimed {self.limit / 1000:.4g} kN (the linear share gives "
                f"{self.clamped / 1000:.4g} kN)")
        return None


class Unread(Exception):
    """A line the judge cannot read as the joint grammar gives it."""


def _bound(component: Component, key: str) -> tuple[Fraction, Fraction]:
    for attr in component.attrs:
        if attr.key == key and len(attr.args) == 1 and isinstance(attr.args[0], Bound):
            value = attr.args[0].range.value
            return value.lo, value.hi
    raise Unread(f"no `{key}` bound")


def _range(value: object, design: Design) -> tuple[Fraction, Fraction]:
    if isinstance(value, Input):
        v = value.range.value
    elif isinstance(value, ParamRef) and value.name in design.params:
        v = design.params[value.name].range.value
    else:
        raise Unread(f"load value {value} is not a range")
    return v.lo, v.hi


def _bolt(component: Component) -> tuple[str, int]:
    for attr in component.attrs:
        if attr.key == "bolt" and len(attr.args) == 3 and isinstance(attr.args[0], Ref) and isinstance(attr.args[2], Fixed):
            return ".".join(attr.args[0].parts), int(attr.args[2].quantity.value.lo)
    raise Unread("no `bolt <id> count <n>` line")


def stress_area(d_mm: int) -> float:
    """ISO 724: As = pi / 4 ((d2 + d3) / 2)^2 in m2, d2 = d - 0.649519 P, d3 = d - 1.226869 P."""
    p = float(COARSE_PITCH_MM[d_mm])
    d2, d3 = d_mm - 0.649519 * p, d_mm - 1.226869 * p
    return math.pi / 4 * ((d2 + d3) / 2) ** 2 * 1e-6


def facts(component: Component, design: Design, registry: Registry) -> tuple[list[Opening], list[str]]:
    name = component.name
    try:
        bolt, n = _bolt(component)
        match = re.fullmatch(r"bolt\.M([0-9]+)_.*", bolt)
        if match is None or int(match.group(1)) not in COARSE_PITCH_MM or bolt not in registry.parts:
            raise Unread(f"{bolt} is not a metric coarse bolt the judge reads")
        d_mm = int(match.group(1))
        torque, nut, share = (_bound(component, k) for k in ("torque", "nut_factor", "load_share"))
    except Unread as e:
        return [], [f"{name}: {e}"]
    props = registry.parts[bolt].props
    proof = float((props["Sp"] if "Sp" in props else props["Rp02_min"]).value.lo) * stress_area(d_mm)
    d = d_mm / 1000
    preload_lo, preload_hi = float(torque[0]) / (float(nut[1]) * d), float(torque[1]) / (float(nut[0]) * d)
    forces = {case.name: _range(e.value, design) for case in design.loads.values() for e in case.entries
              if e.target == (name,) and e.field == "force"}
    limits = [(f"claim {c.name}", c.under or tuple(forces), float(c.bound.value.lo) * (proof if c.qoi.name == "tension_utilisation" else 1))
              for c in design.claims
              if c.qoi.path == (name,) and c.qoi.name in ("tension_utilisation", "bolt_tension") and c.rel is Rel.LE]
    limits = limits or [("proof load", tuple(forces), proof)]
    out, undecided = [], []
    for what, cases, limit in limits:
        for case in cases:
            if case not in forces:
                continue
            lo, hi = (float(x) for x in forces[case])
            clamped = preload_hi + max(s * f for s in (float(share[0]), float(share[1])) for f in (lo, hi)) / n
            subject = f"{name} {what} under {case}"
            if clamped > limit:
                undecided.append(f"{subject}: the judge's own linear bolt force, {clamped / 1000:.4g} kN, already exceeds "
                                 f"{limit / 1000:.4g} kN, so it cannot isolate the opening")
                continue
            out.append(Opening(subject, limit, clamped, hi / n, preload_lo))
    return out, undecided
