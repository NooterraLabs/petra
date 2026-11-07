"""Numbers for people: each check's demand, available strength and utilisation. Tooling.

Nothing here decides a verdict. `values` rebuilds a mode's checks for one connection and
load case exactly as build.py does, then encloses each demand and available strength over
the design's box with the kernel's own interval evaluator, or at one point of it. Reports,
the calculation package and the tests read it; the kernel decides the obligations
themselves. `read` is the steel deck's reader for petra.readout: one obligation's checks
at its counterexample, or over its box, in kips and inches.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Mapping

from ...ir import Design, Fixed, Value as DesignValue
from ...kernel import Expr, Interval, Sqrt, Statement, enclose
from ...kernel.rules.r4_enclosure import AllNonpositive
from ...mechanics import add, sq
from ...premises import design_label
from ...readout import Readout, Value
from ...registry import Registry
from ...units import AREA, CUSTOMARY, FORCE, LENGTH, STRESS, TORQUE, Dim
from ..base import Criterion, Requirement, StatementBuilder
from .build import load_cases, term
from .checks import GENERATORS, GEOMETRY, Check, Ctx
from .lower import Conn, lower_conn

INCH, KIP = CUSTOMARY["inch"][0], CUSTOMARY["kip"][0]
UNITS = {"kip": KIP, "kip-in": KIP * INCH, "kip/in": KIP / INCH, "in": INCH, "1": Fraction(1)}

DISPLAY: Mapping[Dim, str] = {FORCE: "kip", LENGTH: "inch", AREA: "inch2", STRESS: "ksi", TORQUE: "kip_in"}
"""The unit each dimension prints in: AISC 360 is written in kips and inches."""

PREFIX = "steel."


def connection(design: Design, name: str, registry: Registry) -> Conn:
    return lower_conn(design.components[name], design, registry)


class _Recording(StatementBuilder):
    """A StatementBuilder that keeps the dimension of each design value it is given, so a
    report can print "3 inch" where the statement holds 381/5000."""

    def __init__(self, design: Design, registry: Registry) -> None:
        super().__init__(design, registry)
        self.design_name = design.name
        self.dims: dict[str, Dim] = {}

    def value(self, v: DesignValue, name: str):
        if isinstance(v, Fixed):
            self.dims[design_label(self.design_name, name)] = v.quantity.dim
        return super().value(v, name)


def _available(ctx: Ctx, check: Check) -> Expr:
    if check.group is None:
        return check.capacity
    return ctx.available(check.capacity, check.group, check.suffix)


def _magnitude(check: Check) -> Expr:
    return check.demand[0] if len(check.demand) == 1 else Sqrt(add(*(sq(d) for d in check.demand)))


def _evaluate(conn: Conn, design: Design, registry: Registry, mode: str, case: str,
              at: Mapping[str, Fraction] | None) -> tuple[list[Value], dict[str, Dim]]:
    ctx = Ctx(conn, design, registry, case)
    ctx.sb = _Recording(design, registry)
    checks = GENERATORS[mode](ctx, GEOMETRY[conn.kind](ctx))
    exprs = [(_magnitude(c), _available(ctx, c), c.guards) for c in checks]
    flat = tuple(e for demand, available, guards in exprs for e in (demand, available, *guards))
    if not flat:
        return [], ctx.sb.dims
    statement = ctx.sb.finish(AllNonpositive(flat))
    point = at or {}
    box = {h.sym: Interval(point[h.label], point[h.label]) if h.label in point else Interval(h.lo, h.hi) for h in statement.hyps}
    out = []
    for check, (demand, available, guards) in zip(checks, exprs):
        scale = UNITS[check.unit]
        d, a = enclose(demand, box), enclose(available, box)
        excused = any(enclose(g, box).hi <= 0 for g in guards)
        out.append(Value(check.what, check.unit, float(d.hi / scale), float(a.lo / scale), excused, True))
    return out, ctx.sb.dims


def values(conn: Conn, design: Design, registry: Registry, mode: str, case: str,
           at: Mapping[str, Fraction] | None = None) -> list[Value]:
    """Every check of `mode` (a short name, such as "block_shear") under `case`: over the
    design's box, or with each hypothesis whose label `at` names fixed at that value."""
    return _evaluate(conn, design, registry, mode, case, at)[0]


def governing(conn: Conn, design: Design, registry: Registry, mode: str, case: str) -> Value | None:
    found = values(conn, design, registry, mode, case)
    return max(found, key=lambda v: v.utilisation) if found else None


def _case(conn: Conn, design: Design, registry: Registry, requirement: Requirement, statement: Statement, mode: str,
          u: Fraction) -> str | None:
    """The load case the statement was built for: the one whose statement, rebuilt as
    build.py builds it, is this one."""
    for case in load_cases(requirement, conn, design)[0]:
        ctx = Ctx(conn, design, registry, case)
        checks = GENERATORS[mode](ctx, GEOMETRY[conn.kind](ctx))
        if checks and ctx.sb.finish(AllNonpositive(tuple(term(ctx, c, u) for c in checks))) == statement:
            return case
    return None


def read(requirement: Requirement, statement: Statement, design: Design, registry: Registry,
         at: Mapping[str, Fraction] | None) -> Readout:
    """The checks of the obligation `statement` states for `requirement`, at the point `at`
    (label -> value) or over its box. A claim of utilisation u holds each demand against u
    times its available strength, so the capacity reported is that, and the utilisation
    is the demand's share of it."""
    criterion = requirement.criterion
    u = criterion.bound.value.lo if isinstance(criterion, Criterion) else Fraction(1)
    mode = requirement.mode.id.removeprefix(PREFIX)
    conn = connection(design, requirement.subject[0], registry)
    case = _case(conn, design, registry, requirement, statement, mode, u)
    if case is None:
        return Readout((), {}, "no load case of the design rebuilds this statement")
    found, dims = _evaluate(conn, design, registry, mode, case, at)
    if u != 1:
        found = [Value(f"{v.what}, against {float(u):g} of its available strength", v.unit, v.demand, float(u) * v.capacity, v.excused, True) for v in found]
    return Readout(tuple(found), dims, None)
