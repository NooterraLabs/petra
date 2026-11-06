"""Numbers for people: each check's demand, available strength and utilisation. Tooling.

Nothing here decides a verdict. `values` rebuilds a mode's checks for one connection and
load case exactly as build.py does, then encloses each demand and available strength over
the design's box with the kernel's own interval evaluator. Reports, the calculation
package and the tests read it; the kernel decides the obligations themselves.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from ...ir import Design
from ...kernel import Expr, Interval, Sqrt, enclose
from ...kernel.rules.r4_enclosure import AllNonpositive
from ...mechanics import add, sq
from ...registry import Registry
from ...units import CUSTOMARY
from .checks import GENERATORS, GEOMETRY, Check, Ctx
from .lower import Conn, lower_conn

INCH, KIP = CUSTOMARY["inch"][0], CUSTOMARY["kip"][0]
UNITS = {"kip": KIP, "kip-in": KIP * INCH, "kip/in": KIP / INCH, "in": INCH, "1": Fraction(1)}


@dataclass(frozen=True)
class Value:
    """One check over the design's box, in the check's display unit: the largest demand,
    the least available strength, their ratio, and whether a guard excuses the check
    everywhere in the box."""

    what: str
    unit: str
    demand: float
    available: float
    excused: bool

    @property
    def utilisation(self) -> float:
        if self.excused:
            return 0.0
        if self.available <= 0:
            return float("inf") if self.demand > 0 else 0.0
        return self.demand / self.available


def connection(design: Design, name: str, registry: Registry) -> Conn:
    return lower_conn(design.components[name], design, registry)


def _available(ctx: Ctx, check: Check) -> Expr:
    if check.group is None:
        return check.capacity
    return ctx.available(check.capacity, check.group, check.suffix)


def _magnitude(check: Check) -> Expr:
    return check.demand[0] if len(check.demand) == 1 else Sqrt(add(*(sq(d) for d in check.demand)))


def values(conn: Conn, design: Design, registry: Registry, mode: str, case: str) -> list[Value]:
    """Every check of `mode` (a short name, such as "block_shear") under `case`."""
    ctx = Ctx(conn, design, registry, case)
    checks = GENERATORS[mode](ctx, GEOMETRY[conn.kind](ctx))
    exprs = [(_magnitude(c), _available(ctx, c), c.guards) for c in checks]
    flat = tuple(e for demand, available, guards in exprs for e in (demand, available, *guards))
    if not flat:
        return []
    statement = ctx.sb.finish(AllNonpositive(flat))
    box = {h.sym: Interval(h.lo, h.hi) for h in statement.hyps}
    out = []
    for check, (demand, available, guards) in zip(checks, exprs):
        scale = UNITS[check.unit]
        d, a = enclose(demand, box), enclose(available, box)
        excused = any(enclose(g, box).hi <= 0 for g in guards)
        out.append(Value(check.what, check.unit, float(d.hi / scale), float(a.lo / scale), excused))
    return out


def governing(conn: Conn, design: Design, registry: Registry, mode: str, case: str) -> Value | None:
    found = values(conn, design, registry, mode, case)
    return max(found, key=lambda v: v.utilisation) if found else None
