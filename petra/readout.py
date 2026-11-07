"""Numbers for people: what each obligation of a checked report says, in the design's
units. Tooling.

Nothing here decides a verdict. `findings(report)` reads every outcome of a report after
its verdict is assembled, and gives one Finding each: the obligation, its outcome, rule
and statement hash, what an open item needs, and what a person fixing a design needs.
Where the evidence came from is left out, so a report replayed from stored certificates
reads as the run that solved it:

- its terms, each `demand - capacity <= 0` of the goal, as demand, capacity and
  utilisation (demand / capacity) in the design's units: at the counterexample or margin
  point when there is one, otherwise enclosed over the box (the largest demand against
  the least capacity, an upper bound on the utilisation anywhere in it);
- for a claim, its quantity there against its bound;
- that point, each coordinate as a decimal in the design's units beside the exact
  rational the kernel checked.

A domain with a reader of its own names its terms (READERS: the steel deck's calc.read,
in kips and inches). Any other R4 goal is read term by term from the statement: a term
`a - b` gives demand a and capacity b, named and dimensioned by TERMS when its mode is
listed there, with each quantity a lemma defines (a member force) over the range the
theorem proved, or at a point over the range its lemma solver gives there. A FACTORED
R1 goal reads as its load factor at the point. Other R1, R2 and R3 goals are not read.
Units follow the domain (READERS) or else readable SI. A reader that fails costs only
its numbers: the finding keeps its outcome and says why.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from functools import cache
from typing import TYPE_CHECKING, Any, Callable, Mapping

from .ir import Design, Rel
from .kernel import GOAL_RULE, Add, Const, DefinedHyp, Expr, Interval, KernelArithmeticError, Neg, RangeHyp, Refutation, Statement, enclose, statement_hash
from .kernel.rules.r1_linear import LinearFeasible
from .kernel.rules.r4_enclosure import AllNonpositive
from .models import KINDS
from .models.base import ClaimOrigin, Criterion, Requirement
from .premises import LabelKind, input_label, label_kind, param_label
from .registry import Registry
from .units import (CURRENT, CUSTOMARY, DIMENSIONLESS, FORCE, I2T, TEMPERATURE, UNITS, VOLTAGE, Dim, Quantity,
                    format_quantity, si_unit)
from .verdict import COVERAGE_ENTRY, Discharged, Open, Outcome, Refuted, Waived, WithinMargin, describe_need

if TYPE_CHECKING:
    from .pipeline import Report


@dataclass(frozen=True)
class Value:
    """One term: the demand against the capacity it is held to, both in `unit` (None
    when the term's dimension is unknown: SI base units). Over a box, the largest demand
    and the least capacity; at a point, their values there. `excused`: a guard of the
    clause excuses the term (everywhere in the box, or at the point). `claimed`: the term
    holds the claimed quantity against the claim's bound, so for a claim that quantity is
    the bound times the utilisation."""

    what: str
    unit: str | None
    demand: float
    capacity: float
    excused: bool
    claimed: bool

    @property
    def utilisation(self) -> float:
        if self.excused:
            return 0.0
        if self.capacity <= 0:
            return float("inf") if self.demand > 0 else 0.0
        return self.demand / self.capacity


@dataclass(frozen=True)
class Readout:
    """What a reader made of one obligation: its terms, the dimension of each design value
    ("dsg:" label) it knows, and why there are no terms, or fewer than the goal has."""

    values: tuple[Value, ...]
    dims: Mapping[str, Dim]
    note: str | None


Reader = Callable[[Requirement, Statement, Design, Registry, "Mapping[str, Fraction] | None"], Readout]


@dataclass(frozen=True)
class Domain:
    read: Reader
    units: Mapping[Dim, str]   # the unit each dimension prints in; any other prints in readable SI


@cache
def _steel() -> Domain:
    from .models.steel import calc
    return Domain(calc.read, calc.DISPLAY)


READERS: Mapping[str, Callable[[], Domain]] = {"steel": _steel}
"""Domain name (models.DOMAINS) -> its reader, imported when first needed."""

TERMS: Mapping[str, tuple[tuple[str, Dim, bool], ...]] = {
    "wire.steady_temperature": (("conductor temperature", TEMPERATURE, True),
                                ("thermal runaway, a alpha against 1", DIMENSIONLESS, False)),
    "wire.voltage_drop": (("voltage drop at the far end", VOLTAGE, True),),
    "wire.short_circuit": (("let-through energy against the conductor's withstand k^2 S^2", I2T, True),
                           ("prospective fault current against the breaking capacity", CURRENT, True)),
    "wire.overload_protection": (("design current I_B against the rated current I_n", CURRENT, True),
                                 ("conductor temperature at I_n", TEMPERATURE, False),
                                 ("thermal runaway at I_n", DIMENSIONLESS, False),
                                 ("conductor temperature at the tripping current I_2 / 1.45", TEMPERATURE, False),
                                 ("thermal runaway at I_2 / 1.45", DIMENSIONLESS, False)),
    "bolt.tension": (("bolt tension against its limit", FORCE, True),),
    "truss.member_buckling": (("compression against the flexural buckling resistance", FORCE, True),),
}
"""Mode id -> (name, dimension, claimed) for each term of its R4 goal, in order, for
modes whose builders state a fixed number of terms (tests/test_readout.py holds each to
its builder). A goal of another length reads as unnamed terms of unknown dimension."""

FACTORED: frozenset[str] = frozenset({"truss.plastic_collapse"})
"""Modes whose R1 goal states a claimed load factor f as A x = f b, b the load
(models/truss.py build_plastic_collapse), so the factor carried at a point is f times
the largest multiple of the right-hand side that stays feasible there."""


@dataclass(frozen=True)
class Coordinate:
    """One value of a point: `exact`, the kernel's rational in SI base units (degC for
    temperature), and `decimal`, the same in `unit`, the design's unit for its dimension
    (None when the dimension is unknown). `varies`: the statement lets it range, so the
    point chose it, as it does a load inside its signed bounds."""

    symbol: str
    label: str
    exact: Fraction
    si_unit: str | None
    decimal: str
    unit: str | None
    varies: bool

    @property
    def shown(self) -> str:
        return self.decimal if self.unit in (None, "1") else f"{self.decimal} {self.unit}"

    def to_json(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "label": self.label, "value": self.decimal, "unit": self.unit,
                "exact": str(self.exact), "si_unit": self.si_unit, "varies": self.varies}


@dataclass(frozen=True)
class Claimed:
    """A claim's quantity where its terms were read, against the claim's bound."""

    claim: str
    quantity: str
    value: float
    bound: float
    unit: str

    def text(self) -> str:
        unit = "" if self.unit == "1" else f" {self.unit}"
        return f"{self.claim}: {self.quantity} is {_number(self.value)}{unit} here, against its bound {_number(self.bound)}{unit}"


OUTCOMES: Mapping[type, str] = {Discharged: "certified", Refuted: "refuted", WithinMargin: "marginal", Waived: "waived", Open: "open"}


@dataclass(frozen=True)
class Finding:
    """One outcome of a report, read for a person. `values` are evaluated `at` "point"
    (the counterexample of a refuted obligation, or the point within the margin of a
    marginal one or of an open item that found one) or over the "box"; `at` is None when
    no term was read, and `note` says why. `point` is that point."""

    requirement: str
    entry: str
    outcome: str
    rule: str | None
    statement_hash: str | None
    describe: str
    values: tuple[Value, ...]
    at: str | None
    claim: Claimed | None
    point: tuple[Coordinate, ...]
    needs: tuple[str, ...]
    note: str | None

    @property
    def governing(self) -> Value | None:
        """The term with the highest utilisation that no guard excuses."""
        live = [v for v in self.values if not v.excused]
        return max(live, key=lambda v: v.utilisation) if live else None

    def lines(self) -> list[str]:
        """The text under a refuted obligation or a margin point: the governing term, any
        other term over its capacity, the claim's quantity, then the point. Coordinates
        the statement fixes (design values, registry constants) are counted, not listed;
        inputs and params are always listed."""
        g = self.governing
        out = [f"governing  {_value_text(g)}" if g is not None else f"numbers    not read: {self.note}"]
        over = sorted((v for v in self.values if v is not g and not v.excused and v.utilisation > 1), key=lambda v: -v.utilisation)
        out += [f"also over  {v.what}: utilisation {_ratio(v.utilisation)}" for v in over]
        if self.claim is not None:
            out.append(f"claim      {self.claim.text()}")
        shown = [c for c in self.point if c.varies or label_kind(c.label) in (LabelKind.INPUT, LabelKind.PARAM)]
        width = max((len(c.symbol) for c in shown), default=0)
        out += [f"{'at' if i == 0 else '':<10} {c.symbol:<{width}} = {c.shown}   ({c.label})" for i, c in enumerate(shown)]
        fixed = len(self.point) - len(shown)
        if fixed:
            out.append(f"fixed      {fixed} more values, as the design and the registry state them (--json lists each)")
        return out

    def to_json(self) -> dict[str, Any]:
        g = self.governing
        point = [c.to_json() for c in self.point] if self.point else None
        claim = self.claim
        return {
            "requirement": self.requirement,
            "entry": self.entry,
            "outcome": self.outcome,
            "rule": self.rule,
            "statement_hash": self.statement_hash,
            "describe": self.describe,
            "at": self.at,
            "governing": None if g is None else g.what,
            "demand": None if g is None else g.demand,
            "capacity": None if g is None else g.capacity,
            "unit": None if g is None else g.unit,
            "utilisation": None if g is None else _finite(g.utilisation),
            "checks": [{"check": v.what, "demand": v.demand, "capacity": v.capacity, "unit": v.unit,
                        "utilisation": _finite(v.utilisation), "excused": v.excused} for v in self.values],
            "claim": None if claim is None else {"claim": claim.claim, "quantity": claim.quantity, "value": claim.value,
                                                 "bound": claim.bound, "unit": claim.unit},
            "counterexample": point if self.outcome == "refuted" else None,
            "margin_point": point if self.outcome != "refuted" else None,
            "needs": list(self.needs),
            "note": self.note,
        }


def findings(report: Report) -> tuple[Finding, ...]:
    """One Finding per outcome of `report`, in order. A report built without its design
    and registry gives findings with no terms and no units."""
    context = _Context(report.ir, report.registry) if report.ir is not None and report.registry is not None else None
    return tuple(_finding(o, context) for o in report.outcomes)


class _Context:
    """What reading a design's outcomes needs once: the dimension of every signed input and
    param, and each domain's reader."""

    def __init__(self, design: Design, registry: Registry) -> None:
        from .pipeline import lower_components, signed_inputs

        self.design, self.registry = design, registry
        self.dims: dict[str, Dim] = {param_label(design.name, p.name): p.range.dim for p in design.params.values()}
        for inp in signed_inputs(design, lower_components(design, registry)):
            self.dims[input_label(design.name, inp.name)] = inp.range.dim
            self.dims[input_label(design.name, f"{inp.name}.mean")] = inp.range.dim
        for record in design.tests.values():
            for field in ("trials", "failures"):
                self.dims[input_label(design.name, f"tests.{record.name}.{field}")] = DIMENSIONLESS

    def domain(self, requirement: Requirement) -> tuple[str | None, Domain | None]:
        component = self.design.components.get(requirement.subject[0]) if requirement.subject else None
        name = KINDS[component.kind].name if component is not None and component.kind in KINDS else None
        return name, READERS[name]() if name in READERS else None

    def registry_unit(self, label: str) -> tuple[Dim | None, str | None]:
        """A registry value's dimension when its unit is an SI unit Petra parses, and the
        unit as the registry writes it."""
        try:
            unit = self.registry.fact(label[len("reg:"):]).unit
        except LookupError:
            return None, None
        found = UNITS.get(unit)
        return (found[1] if found is not None and found[0] == 1 else None), unit


def _finding(outcome: Outcome, context: _Context | None) -> Finding:
    requirement = outcome.requirement if isinstance(outcome, (Waived, Open)) else outcome.obligation.requirement
    entry = requirement.origin.claim if isinstance(requirement.origin, ClaimOrigin) else COVERAGE_ENTRY
    kind = OUTCOMES[type(outcome)]
    statement, refutation, rule = _parts(outcome)
    describe = outcome.obligation.describe if isinstance(outcome, (Discharged, Refuted, WithinMargin)) else requirement.id
    needs = tuple(describe_need(n) for n in outcome.needs) if isinstance(outcome, Open) else ()
    digest = None if statement is None else (outcome.theorem.statement_hash if isinstance(outcome, Discharged) else statement_hash(statement))
    if statement is None or context is None:
        note = "nothing was stated to read" if statement is None else "the report carries no design to read it against"
        return Finding(requirement.id, entry, kind, rule, digest, describe, (), None, None, (), needs, note)
    name, domain = context.domain(requirement)
    units = domain.units if domain is not None else {}
    at = None if refutation is None else _at_labels(refutation)
    defined = dict(outcome.theorem.defined_ranges) if isinstance(outcome, Discharged) else {}
    try:
        readout = domain.read(requirement, statement, context.design, context.registry, at) if domain is not None else \
            _generic(requirement, statement, at, defined, units)
    except Exception as exc:  # a reader is tooling: its failure costs its numbers, never the report
        readout = Readout((), {}, f"the {name} reader failed: {type(exc).__name__}: {exc}")
    point = () if refutation is None else _coordinates(refutation, context, readout.dims, units)
    where = None if not readout.values else ("box" if refutation is None else "point")
    claim = _claimed(requirement, readout.values, units)
    return Finding(requirement.id, entry, kind, rule, digest, describe, readout.values, where, claim, point, needs, readout.note)


def _parts(outcome: Outcome) -> tuple[Statement | None, Refutation | None, str | None]:
    """(the claim's statement, the point's refutation, the rule)."""
    match outcome:
        case Discharged():
            return outcome.obligation.statement, None, outcome.theorem.rule
        case Refuted():
            return outcome.obligation.statement, outcome.refutation, outcome.refutation.rule
        case WithinMargin():
            return outcome.obligation.statement, outcome.refutation, outcome.refutation.rule
        case Open() if outcome.statement is not None:
            near = outcome.near.refutation if outcome.near is not None else None
            return outcome.statement, near, GOAL_RULE[type(outcome.statement.goal)].id
    return None, None, None


def _claimed(requirement: Requirement, values: tuple[Value, ...], units: Mapping[Dim, str]) -> Claimed | None:
    """A claim's quantity q where the terms were read, from the claimed term with the
    highest utilisation u: a claim `q <= bound` holds q against the bound or a capacity
    scaled by it, so q = bound u; a claim `q >= bound` holds the bound against q, so
    q = bound / u. None for a coverage requirement or when no term carries q."""
    criterion = requirement.criterion
    if not isinstance(requirement.origin, ClaimOrigin) or not isinstance(criterion, Criterion) or criterion.rel not in (Rel.LE, Rel.GE):
        return None
    carried = [v.utilisation for v in values if v.claimed and not v.excused and math.isfinite(v.utilisation)]
    if not carried or (criterion.rel is Rel.GE and max(carried) <= 0):
        return None
    bound = criterion.bound.value.lo if criterion.rel is Rel.LE else criterion.bound.value.hi
    unit = _unit(criterion.bound.dim, abs(bound), units)
    shown = float(bound / _factor(unit))
    top = max(carried)
    quantity = requirement.qoi.name if requirement.qoi is not None else requirement.mode.id
    return Claimed(requirement.origin.claim, quantity, shown * top if criterion.rel is Rel.LE else shown / top, shown, unit)


def _at_labels(refutation: Refutation) -> dict[str, Fraction]:
    labels = {h.sym: h.label for h in refutation.statement.hyps if isinstance(h, RangeHyp)}
    return {labels[sym]: value for sym, value in refutation.point if sym in labels}


def _coordinates(refutation: Refutation, context: _Context, dsg: Mapping[str, Dim], units: Mapping[Dim, str]) -> tuple[Coordinate, ...]:
    hyps = {h.sym: h for h in refutation.statement.hyps if isinstance(h, RangeHyp)}
    out = []
    for sym, value in refutation.point:
        hyp = hyps[sym]
        kind = label_kind(hyp.label)
        written = None
        if kind is LabelKind.REGISTRY:
            dim, written = context.registry_unit(hyp.label)
        else:
            dim = (dsg if kind is LabelKind.DESIGN else context.dims).get(hyp.label)
        if dim is not None:
            unit, si = _unit(dim, abs(value), units), si_unit(dim)
            decimal = _decimal(value / _factor(unit))
        else:
            unit = si = written
            decimal = _decimal(value)
        out.append(Coordinate(sym, hyp.label, value, si, decimal, unit, hyp.lo != hyp.hi))
    return tuple(out)


def _generic(requirement: Requirement, statement: Statement, at: Mapping[str, Fraction] | None,
             defined: Mapping[str, Interval], units: Mapping[Dim, str]) -> Readout:
    """Each `a - b` term of an R4 goal at the point, or over the box with the ranges the
    theorem proved for its defined quantities; for a FACTORED mode, its load factor at
    the point."""
    goal = statement.goal
    box: dict[str, Interval] = {}
    for h in statement.hyps:
        if isinstance(h, RangeHyp):
            box[h.sym] = Interval(at[h.label], at[h.label]) if at is not None and h.label in at else Interval(h.lo, h.hi)
    if isinstance(goal, LinearFeasible) and requirement.mode.id in FACTORED:
        return _load_factor(requirement, goal, box, at is not None)
    if not isinstance(goal, AllNonpositive):
        return Readout((), {}, f"an {GOAL_RULE[type(goal)].id} statement has no demand and capacity terms to read")
    names = TERMS.get(requirement.mode.id)
    if names is not None and len(names) != len(goal.exprs):
        names = None
    if at is not None:
        defined = {**_defined_at(statement, box), **defined}
    box.update((h.sym, defined[h.sym]) for h in statement.hyps if isinstance(h, DefinedHyp) and h.sym in defined)
    out, shapeless, undefined = [], 0, 0
    for k, expr in enumerate(goal.exprs):
        sides = _sides(expr)
        if sides is None:
            shapeless += 1
            continue
        try:
            a, b = (enclose(e, box) for e in sides)
        except (KeyError, KernelArithmeticError):
            undefined += 1
            continue
        what, dim, claimed = names[k] if names is not None else (f"term {k + 1} of the goal", None, False)
        demand, capacity = a.hi, b.lo
        unit = _unit(dim, max(abs(demand), abs(capacity)), units) if dim is not None else None
        factor = _factor(unit) if unit is not None else Fraction(1)
        out.append(Value(what, unit, float(demand / factor), float(capacity / factor), False, claimed))
    reasons = [f"{shapeless} not of the form demand - capacity"] if shapeless else []
    if undefined:
        reasons.append(f"{undefined} reading a quantity a lemma defines (such as a member force), which no lemma solver "
                       "ranged here")
    note = f"{shapeless + undefined} of {len(goal.exprs)} terms not read: {'; '.join(reasons)}" if reasons else None
    return Readout(tuple(out), {}, note)


def _defined_at(statement: Statement, point: Mapping[str, Interval]) -> dict[str, Interval]:
    """The range of each quantity a lemma defines (a member force, say) at a point, as
    the lemma solver proposes it: the solver the evidence came from, run again at the
    counterexample the kernel checked with such ranges. Empty when there is none or the
    solver cannot range one."""
    from .solvers import LEMMA_SOLVERS

    defined = [h for h in statement.hyps if isinstance(h, DefinedHyp)]
    found: dict[str, Interval] = {}
    for solve in dict.fromkeys(LEMMA_SOLVERS.get(type(h.definition)) for h in defined):
        if solve is None:
            continue
        try:
            found.update((r.sym, Interval(r.lo, r.hi)) for r in solve(statement, point))
        except (ValueError, ArithmeticError, KernelArithmeticError):
            continue
    return found


def _load_factor(requirement: Requirement, goal: LinearFeasible, box: Mapping[str, Interval], at_point: bool) -> Readout:
    """A claim `factor >= f` stated as A x = f b within the bounds (FACTORED): at the
    point, the largest t for which A x = t f b is feasible there, by linear programming in
    floating point, so the factor the design carries is t f against the claimed f."""
    criterion = requirement.criterion
    if not at_point:
        return Readout((), {}, "a load factor is read at a counterexample or margin point, not over the box")
    if not isinstance(criterion, Criterion) or criterion.rel is not Rel.GE or criterion.bound.value.hi <= 0:
        return Readout((), {}, "the claim states no positive load factor to read against")
    import numpy as np
    from scipy.optimize import linprog

    from .solvers.r1_linear import dense

    claimed = criterion.bound.value.hi
    b = np.array([float(enclose(e, box).lo) for e in goal.b])
    lower = [None if e is None else float(enclose(e, box).hi) for e in goal.lower]
    upper = [None if e is None else float(enclose(e, box).lo) for e in goal.upper]
    A = dense(goal.A)
    cols = A.shape[1]
    objective = np.zeros(cols + 1)
    objective[-1] = -1.0   # maximise t
    found = linprog(objective, A_eq=np.hstack([A, -b[:, None]]), b_eq=np.zeros(A.shape[0]),
                    bounds=[*zip(lower, upper), (0, None)], method="highs")
    if found.status == 3:
        carried = math.inf
    elif found.status != 0:
        return Readout((), {}, f"the load factor could not be computed here: {found.message}")
    else:
        carried = float(claimed) * float(found.x[-1])
    what = "load factor: the claimed factor against the largest one a static field within every member's capacity carries"
    return Readout((Value(what, "1", float(claimed), carried, False, True),), {}, None)


def _sides(expr: Expr) -> tuple[Expr, Expr] | None:
    """`a - b` as the builders write it, Add((a, Neg(b))) or Add((a, Const(-c))), as (a, b)."""
    if isinstance(expr, Add) and len(expr.args) == 2:
        a, b = expr.args
        if isinstance(b, Neg):
            return a, b.arg
        if isinstance(b, Const) and b.value < 0:
            return a, Const(-b.value)
    return None


def _unit(dim: Dim, size: Fraction, units: Mapping[Dim, str]) -> str:
    """`units`' unit for the dimension, else the readable SI one (units.readable_text's
    choice): the largest factor that leaves `size` at least 1, the SI unit among equal
    factors and for zero, never "%"."""
    if dim in units:
        return units[dim]
    si = si_unit(dim)
    found = [(factor, name == si, name) for name, (factor, d) in UNITS.items() if d == dim and name != "%"]
    if not found or size == 0:
        return si
    fitting = [f for f in found if f[0] <= size]
    return max(fitting or [min(found)])[2]


def _factor(unit: str) -> Fraction:
    """An SI spelling with no entry, such as "m^4", has factor 1 by definition."""
    found = UNITS.get(unit) or CUSTOMARY.get(unit)
    return found[0] if found is not None else Fraction(1)


def _decimal(x: Fraction) -> str:
    return format_quantity(Quantity(Interval(x, x), DIMENSIONLESS), "1")


def _number(x: float) -> str:
    """Four significant digits, written out in full between 1e-4 and 1e9 (10000, not
    1e+04)."""
    if x == 0 or not math.isfinite(x) or not 1e-4 <= abs(x) < 1e9:
        return f"{x:.4g}"
    places = max(3 - math.floor(math.log10(abs(x))), 0)
    text = f"{x:.{places}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _ratio(x: float) -> str:
    return "unbounded" if math.isinf(x) else f"{x:.3g}"


def _finite(x: float) -> float | None:
    return x if math.isfinite(x) else None


def _value_text(v: Value) -> str:
    unit = "" if v.unit in (None, "1") else f" {v.unit}"
    base = " (SI base units)" if v.unit is None else ""
    return f"{v.what}: demand {_number(v.demand)}{unit}, capacity {_number(v.capacity)}{unit}, utilisation {_ratio(v.utilisation)}{base}"


__all__ = ["Claimed", "Coordinate", "Finding", "Readout", "Value", "findings", "READERS", "TERMS"]
