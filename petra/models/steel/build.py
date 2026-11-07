"""Requirement -> obligations for the steel deck. Trusted.

One builder per mode. For each load case the requirement is checked under, it states one
obligation: the mode's checks (checks.GENERATORS) as the terms of one AllNonpositive goal,
each term `|demand| - u * available` with u the claimed utilisation (1 for coverage), and
one validity obligation per row of the mode's model (checks.ROWS), stated over the same
load case in a builder of its own.

A term's available strength is phi Rn (LRFD) or Rn / Omega (ASD); the ASD form is stated
as Omega |demand| - u Rn, which has the same sign. A term with guards is Min(term, guards),
which is <= 0 where the term holds or where any guard is <= 0, the region where the
clause excuses the formula.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Callable

from ...ir import Design, Rel
from ...kernel import Const, Expr, Min, Sqrt
from ...kernel.rules.r4_enclosure import AllNonpositive
from ...mechanics import add, mul, sq, sub
from ...registry import Registry
from ..base import Criterion, Elaborated, Gap, GapNeed, NeedsInputBound, NoRuleForQuantity, Obligation, Requirement, validity_obligation
from .checks import GENERATORS, GEOMETRY, ROWS, Check, Ctx
from .lower import KIND_SPECS, Conn
from .vocab import MODELS, MODES


def term(ctx: Ctx, check: Check, u: Fraction) -> Expr:
    """The check as one expression that is <= 0 exactly where it holds or is excused."""
    demand = check.demand[0] if len(check.demand) == 1 else Sqrt(add(*(sq(d) for d in check.demand)))
    scale = (lambda e: e) if u == 1 else (lambda e: mul(Const(u), e))
    if check.group is None:
        expr = sub(demand, scale(check.capacity))
    elif ctx.lrfd:
        expr = sub(demand, scale(mul(ctx.factor(check.group, check.suffix), check.capacity)))
    else:
        expr = sub(mul(ctx.factor(check.group, check.suffix), demand), scale(check.capacity))
    return Min((expr, *check.guards)) if check.guards else expr


NEEDS: dict[str, tuple[str, ...]] = {
    "panel_zone": ("panel_shear", "axial"),
}
"""Load fields a mode's checks read that each of its cases must give, beyond the kind's
primary one, because no value is safe over the field's whole range: the panel's required
shear takes the flange forces of every moment connection at the joint less the story shear
(Commentary Eq C-J10-3), which the one force a flange_force declares does not give, and
Eq J10-10 falls without bound as the column's axial force grows. A case that leaves one
out leaves the mode open, naming it."""


def load_cases(req: Requirement, conn: Conn, design: Design) -> tuple[tuple[str, ...], tuple[GapNeed, ...]]:
    """The cases the requirement is checked under: those it names, else every case that
    loads the connection. Each must give the kind's primary load field and the fields
    NEEDS lists for the mode."""
    fields = (KIND_SPECS[conn.kind].loads[0], *NEEDS.get(req.mode.id.removeprefix("steel."), ()))
    acting = [case.name for case in design.loads.values() if any(e.target == (conn.name,) for e in case.entries)]
    cases = tuple(req.under) if req.under else tuple(acting)
    given = {(case.name, e.field) for case in design.loads.values() for e in case.entries if e.target == (conn.name,)}
    missing = [f for f in fields if not cases or any((case, f) not in given for case in cases)]
    return cases, tuple(NeedsInputBound((conn.name,), f, "kip") for f in missing)


def describe(conn: Conn, short: str, case: str, checks: list[Check], u: Fraction) -> str:
    bound = "" if u == 1 else f" at utilisation {float(u):g}"
    return f"{conn.name} ({conn.kind}) holds every {short.replace('_', ' ')} check{bound} under {case}: " + \
        "; ".join(c.what for c in checks)


def builder(short: str) -> Callable[[Requirement, Conn, Design, Registry], tuple[Elaborated, ...]]:
    mode = MODES[short]
    model = MODELS[mode]

    def build(req: Requirement, conn: Conn, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
        criterion = req.criterion
        needs: list[GapNeed] = []
        if isinstance(criterion, Criterion) and criterion.rel is Rel.GE:
            needs.append(NoRuleForQuantity(short, "a connection's utilisation is bounded from above only"))
        cases, missing = load_cases(req, conn, design)
        needs += missing
        if needs:
            return (Gap(req, tuple(needs)),)
        u = criterion.bound.value.lo if isinstance(criterion, Criterion) else Fraction(1)
        out: list[Elaborated] = []
        for case in cases:
            ctx = Ctx(conn, design, registry, case)
            checks = GENERATORS[short](ctx, GEOMETRY[conn.kind](ctx))
            if not checks:
                continue
            statement = ctx.sb.finish(AllNonpositive(tuple(term(ctx, c, u) for c in checks)))
            validity = []
            for row in model.rows:
                row_ctx = Ctx(conn, design, registry, case)
                exprs, what = ROWS[row.id](row_ctx, GEOMETRY[conn.kind](row_ctx))
                validity.append(validity_obligation(req, model, row, row_ctx.sb.finish(AllNonpositive(exprs)),
                                                    f"{conn.name}: {what} under {case}"))
            out.append(Obligation(req, statement, model, describe(conn, short, case, checks, u), tuple(validity)))
        if not out:
            return (Gap(req, (NoRuleForQuantity(short, f"a {conn.kind} as declared has no {short.replace('_', ' ')} check"),)),)
        return tuple(out)

    return build


BUILDERS = {mode: builder(short) for short, mode in MODES.items()}
