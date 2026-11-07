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

Each obligation is a strength check or a detailing check (DETAILING_MODES), and
`governing(findings)` names the governing check of each across a whole report, so a
PASS says how close it came. A detailing RULE (hole use, joint type) is met or not and
carries no numbers. A capacity made of parts, such as a bolt group's, names what sets
each part (Part): the limit state and ply that make a bolt the weakest.

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

import dataclasses
import functools
import math
import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping

from . import coverage
from .ir import Design, Input, InputKind, LoadCase, LoadEntry, Rel, Signature, Span
from .kernel import (GOAL_RULE, Abs, Add, Const, DefinedHyp, Div, Expr, Interval, KernelArithmeticError, Max, Min, Mul, Neg,
                     PowInt, RangeHyp, Refutation, Sqrt, Statement, Sym, enclose, statement_hash)
from .kernel.rules.r1_linear import LinearFeasible
from .kernel.rules.r4_enclosure import AllNonpositive
from .models import KINDS
from .models.base import ClaimOrigin, Criterion, FailureMode, Grammar, OutsideValidity, Requirement
from .premises import LabelKind, input_label, label_kind, param_label
from .registry import Registry
from .registry.model import render
from .units import (AREA, CURRENT, CUSTOMARY, DIMENSIONLESS, FORCE, I2T, TEMPERATURE, UNITS, VOLTAGE, Dim, Quantity,
                    format_quantity, si_unit)
from .verdict import COVERAGE_ENTRY, Discharged, Open, Outcome, Refuted, Waived, WithinMargin, describe_need

if TYPE_CHECKING:
    from .pipeline import Report


@dataclass(frozen=True)
class Limit:
    """One limit state of a part, such as one bolt's tearout of one ply, with its strength
    in the unit of the check it belongs to. A tearout's `what` gives its clear distance lc."""

    what: str
    capacity: float

    def to_json(self) -> dict[str, Any]:
        return {"limit": self.what, "capacity": self.capacity}


@dataclass(frozen=True)
class Part:
    """`count` alike parts of a capacity made of parts, such as the bolts in one row of a
    bolt group, each as strong as the least of its `limits`: `capacity`, set by the limit
    `governing` names."""

    what: str
    count: int
    limits: tuple[Limit, ...]
    capacity: float = field(init=False)
    governing: Limit = field(init=False)

    def __post_init__(self) -> None:
        weakest = min(self.limits, key=lambda limit: limit.capacity)
        object.__setattr__(self, "governing", weakest)
        object.__setattr__(self, "capacity", weakest.capacity)

    def text(self, unit: str | None, every: bool) -> str:
        """Its strength and the limit that sets it, then, if `every`, each other limit,
        weakest first."""
        u = _unit_text(unit)
        out = f"{self.what}: {_number(self.capacity)}{u}, set by {self.governing.what}"
        if every:
            out += "".join(f"; {limit.what} {_number(limit.capacity)}{u}" for limit in sorted(self.limits, key=lambda limit: limit.capacity)
                           if limit is not self.governing)
        return out

    def to_json(self) -> dict[str, Any]:
        return {"part": self.what, "count": self.count, "capacity": self.capacity, "governing": self.governing.what,
                "limits": [limit.to_json() for limit in self.limits]}


@dataclass(frozen=True)
class Value:
    """One term: the demand against the capacity it is held to, both in `unit` (None
    when the term's dimension is unknown: SI base units). Over a box, the largest demand
    and the least capacity; at a point, their values there. `excused`: a guard of the
    clause excuses the term (everywhere in the box, or at the point). `claimed`: the term
    holds the claimed quantity against the claim's bound, so for a claim that quantity is
    the bound times the utilisation.

    A rule (DETAILING_MODES) has no demand, capacity, unit or utilisation, only `met`, which is
    None for every other term. `parts`: what a capacity made of parts is made of, weakest
    first (the bolts of a bolt group, by row); empty otherwise. `utilisation` is demand /
    capacity: 0 when excused or when the demand acts the other way (a truss member in
    tension against its buckling resistance), infinite for a positive demand on no
    capacity. `ratio` is demand / capacity with its sign, which a claim's quantity is
    read back from. `excuse`: for an excused term, the condition that excuses it with its
    numbers where the term was read. A reader may word it; otherwise `findings` reads it
    from the guard in the statement (_excuse)."""

    what: str
    unit: str | None
    demand: float | None
    capacity: float | None
    excused: bool
    claimed: bool
    met: bool | None
    parts: tuple[Part, ...]
    excuse: str | None = None
    utilisation: float | None = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "parts", tuple(sorted(self.parts, key=lambda p: p.capacity)))
        ratio = self.ratio
        object.__setattr__(self, "utilisation", None if ratio is None else max(0.0, ratio))

    @property
    def ratio(self) -> float | None:
        return _ratio_of(self.demand, self.capacity, self.excused)

    def to_json(self) -> dict[str, Any]:
        return {"check": self.what, "demand": self.demand, "capacity": self.capacity, "unit": self.unit,
                "utilisation": _finite(self.utilisation), "excused": self.excused, "excuse": self.excuse, "met": self.met,
                "parts": [p.to_json() for p in self.parts]}


def _ratio_of(demand: float | None, capacity: float | None, excused: bool) -> float | None:
    if demand is None or capacity is None:
        return None
    if excused:
        return 0.0
    if capacity <= 0:
        return float("inf") if demand > 0 else 0.0
    return demand / capacity


def _rank(v: Value) -> tuple[bool, float]:
    """Governing order: a rule not met first, then the highest utilisation."""
    return v.met is False, v.utilisation if v.utilisation is not None else 0.0


def _ranked(values: Iterable[Value]) -> Value | None:
    """The value that governs: of those no guard excuses, a rule not met or the highest
    utilisation; None when none has a utilisation and every rule is met."""
    live = [v for v in values if not v.excused and (v.utilisation is not None or v.met is False)]
    return max(live, key=_rank) if live else None


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


@functools.cache
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
    "bolt.separation": (("the plates' share of the force against the preload", FORCE, False),),
    "truss.member_buckling": (("compression against the flexural buckling resistance", FORCE, True),),
}
"""Mode id -> (name, dimension, claimed) for each term of its R4 goal, in order, for
modes whose builders state a fixed number of terms (tests/test_readout.py holds each to
its builder). A goal of another length reads as unnamed terms of unknown dimension."""

PORT_QUANTITIES: Mapping[str, Dim] = {"current": CURRENT, "temperature": TEMPERATURE, "voltage": VOLTAGE,
                                       "force": FORCE, "conductor_area": AREA}
"""A port contract's quantity (the last part of its requirement id, models/contracts.py)
-> its dimension. A contract states the guarantee's upper end against the rated maximum,
then the rated minimum against the guarantee's lower end, each where the rating states
it, so a two-term goal names both and a one-term goal names the rating it has."""


def _port_terms(requirement: Requirement, count: int) -> tuple[tuple[str, Dim, bool], ...] | None:
    quantity = requirement.id.rpartition("/")[2]
    dim = PORT_QUANTITIES.get(quantity)
    if requirement.mode.id != "port.contract" or dim is None or count not in (1, 2):
        return None
    q = quantity.replace("_", " ")
    if count == 1:
        return ((f"{q} guaranteed against the rating", dim, False),)
    return ((f"largest {q} guaranteed against the rated maximum", dim, False),
            (f"rated minimum against the smallest {q} guaranteed", dim, False))


FACTORED: frozenset[str] = frozenset({"truss.plastic_collapse"})
"""Modes whose R1 goal states a claimed load factor f as A x = f b, b the load
(models/truss.py build_plastic_collapse), so the factor carried at a point is f times
the largest multiple of the right-hand side that stays feasible there."""

STRENGTH, DETAILING = "strength", "detailing"
MEASURED, RULE = "measured", "rule"

DETAILING_MODES: Mapping[str, str] = {
    "steel.edge_min": MEASURED, "steel.edge_max": MEASURED, "steel.spacing_min": MEASURED, "steel.spacing_max": MEASURED,
    "steel.clearance": MEASURED, "steel.fillet_size": MEASURED, "steel.ductility": MEASURED,
    "steel.extended_ductility": MEASURED, "steel.hole_use": RULE, "steel.joint_type": RULE,
    "steel.beam_fit": MEASURED, "steel.flange_fit": MEASURED, "steel.web_fit": MEASURED,
}
"""Mode id -> how its checks read, for the modes that check how a design is detailed:
edge distance, spacing, room to tighten, fillet size, the proportions that keep a
connection ductile, hole use, joint type, and whether the drawn parts fit the beam and the
support's face. Every other mode checks a strength. A
report ranks the two apart, so the governing strength check is never an edge distance.
A MEASURED check has a demand and a capacity as a strength does. A RULE's demand and
capacity are levels and counts (the joint type a hole needs against the joint's), so a
report says only whether each is met."""


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
    """One outcome of a report, read for a person. `category` is "strength" or
    "detailing" (DETAILING_MODES). `values` are evaluated `at` "point" (the
    counterexample of a refuted obligation, or the point within the margin of a marginal
    one or of an open item that found one) or over the "box"; `at` is None when no term
    was read, and `note` says why. `point` is that point. `governing` is the term no guard
    excuses with the highest utilisation, or a rule that is not met, and `utilisation` is
    its utilisation: None when no term has one."""

    requirement: str
    entry: str
    category: str
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
    governing: Value | None = field(init=False)
    utilisation: float | None = field(init=False)

    def __post_init__(self) -> None:
        g = _ranked(self.values)
        object.__setattr__(self, "governing", g)
        object.__setattr__(self, "utilisation", None if g is None else g.utilisation)

    def row(self) -> str:
        """The utilisation at the end of the obligation's table row, `excused` when a
        guard excuses every term, or nothing."""
        if self.utilisation is None:
            return "  excused" if self.values and all(v.excused for v in self.values) else ""
        return f"  utilisation {_ratio(self.utilisation)}"

    def lines(self) -> list[str]:
        """The text under a refuted obligation or a margin point: the governing term and
        what its capacity is made of, any other term over its capacity or rule not met,
        the claim's quantity, then the point. Coordinates the statement fixes (design
        values, registry constants) are counted, not listed; inputs and params are
        always listed."""
        g = self.governing
        out = [f"governing  {_value_text(g)}" if g is not None else f"numbers    not read: {self.note}"]
        if g is not None:
            out += _parts_lines(g)
        over = sorted((v for v in self.values if v is not g and not v.excused and _rank(v) > (False, 1)), key=_rank, reverse=True)
        out += [f"also over  {_value_text(v) if v.met is False else f'{v.what}: utilisation {_ratio(v.utilisation)}'}" for v in over]
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
            "category": self.category,
            "outcome": self.outcome,
            "rule": self.rule,
            "statement_hash": self.statement_hash,
            "describe": self.describe,
            "at": self.at,
            "governing": None if g is None else g.what,
            "demand": None if g is None else g.demand,
            "capacity": None if g is None else g.capacity,
            "unit": None if g is None else g.unit,
            "utilisation": _finite(self.utilisation),
            "checks": [v.to_json() for v in self.values],
            "claim": None if claim is None else {"claim": claim.claim, "quantity": claim.quantity, "value": claim.value,
                                                 "bound": claim.bound, "unit": claim.unit},
            "counterexample": point if self.outcome == "refuted" else None,
            "margin_point": point if self.outcome != "refuted" else None,
            "needs": list(self.needs),
            "note": self.note,
        }


@dataclass(frozen=True)
class Governing:
    """A report's governing check of one category: of the terms of every obligation in
    it, the one a Finding would call governing, and the requirement it belongs to."""

    category: str
    requirement: str
    value: Value

    def text(self) -> str:
        weakest = self.value.parts[0].text(self.value.unit, False) if self.value.parts else None
        return f"{self.requirement}: {_value_text(self.value)}" + (f"; weakest {weakest}" if weakest else "")

    def to_json(self) -> dict[str, Any]:
        return {"requirement": self.requirement, **self.value.to_json()}


def findings(report: Report) -> tuple[Finding, ...]:
    """One Finding per outcome of `report`, in order. A report built without its design
    and registry gives findings with no terms and no units."""
    context = _Context(report.ir, report.registry) if report.ir is not None and report.registry is not None else None
    return tuple(_finding(o, context) for o in report.outcomes)


def governing(found: tuple[Finding, ...]) -> dict[str, Governing | None]:
    """The governing strength check and the governing detailing check of a report's
    findings, each None when no term of that category has a utilisation or is a rule
    that is not met. Among equals, the first in report order."""
    out: dict[str, Governing | None] = {}
    for category in (STRENGTH, DETAILING):
        candidates = [f for f in found if f.category == category and f.governing is not None]
        best = max(candidates, key=lambda f: _rank(f.governing), default=None)
        out[category] = None if best is None else Governing(category, best.requirement, best.governing)
    return out


def summary(governs: Mapping[str, Governing | None]) -> list[str]:
    """The lines after the report's `checked` line: the governing strength check, or
    `none` when no strength check has a utilisation, then the governing detailing check
    when the design has one."""
    return [f"governing  {category:<10} " + (g.text() if g is not None else f"none: no {category} check here has a utilisation")
            for category, g in governs.items() if g is not None or category == STRENGTH]


# --- What a report did not check ------------------------------------------------------------

NOT_DEMANDED = "not demanded by the coverage table"
CLAIM_ONLY = "only a claim demands it; the coverage table never does"


@dataclass(frozen=True)
class Unchecked:
    """A mode the subject's domain declares that no requirement of the report names on
    the subject (a component), and why: the load whose absence leaves it undemanded, that
    only a claim demands it, or NOT_DEMANDED when the coverage table records no reason."""

    subject: str
    mode: str
    reason: str

    def to_json(self) -> dict[str, Any]:
        return {"subject": self.subject, "mode": self.mode, "reason": self.reason}


def unchecked(report: Report) -> tuple[Unchecked, ...]:
    """For each component, in design order, each mode of its domain (DomainSpec.modes) that
    no outcome's requirement names on it, by mode id. A report without its design and
    registry gives none.

    The reason comes from the coverage table itself. A load field the component's kind
    takes (Grammar.loads, on a kind whose loads target the component) and the design does
    not declare is added in a probe load case, and coverage.generate runs again: each mode
    it then demands gets "no <field> load is declared; one would demand it". A mode no
    coverage rule of its domain demands is CLAIM_ONLY. Any other is NOT_DEMANDED. The
    probe is a copy of the design read only here, so it cannot change what the report
    demands or decides; a probe that raises costs only its reason."""
    design, registry = report.ir, report.registry
    if design is None or registry is None:
        return ()
    from . import models as domains  # read at call time, as pipeline.lower_components reads it
    from .pipeline import lower_components

    named = {(r.subject[0], r.mode) for r in map(_requirement, report.outcomes) if r.subject}
    models = lower_components(design, registry)
    out: list[Unchecked] = []
    for name, component in design.components.items():
        spec = domains.KINDS[component.kind]
        left = sorted((m for m in spec.modes if (name, m) not in named), key=lambda m: m.id)
        if not left:
            continue
        loads = _load_reasons(name, spec.grammars.get(component.kind), design, models, registry, named)
        ruled = {m for rule in spec.coverage for m in rule.demands}
        out += [Unchecked(name, m.id, loads.get(m) or (NOT_DEMANDED if m in ruled else CLAIM_ONLY)) for m in left]
    return tuple(out)


PROBE = "petra.probe"
"""The name of the load case a probe adds; a .petra load name cannot contain a dot."""


def _load_reasons(name: str, grammar: Grammar | None, design: Design, models: Mapping[str, Any], registry: Registry,
                  named: set[tuple[str, FailureMode]]) -> dict[FailureMode, str]:
    if grammar is None or "." in grammar.target:  # no grammar, or loads that target a part of the component
        return {}
    declared = {e.field for case in design.loads.values() for e in case.entries if e.target == (name,)}
    fields: dict[FailureMode, list[str]] = {}
    for load in grammar.loads:
        if load in declared:
            continue
        try:
            found = coverage.generate(_probe(design, name, load), models, registry)
        except Exception:  # the probe is tooling: a domain hook that refuses it costs only this reason
            continue
        for r in found:
            if r.subject and r.subject[0] == name and (name, r.mode) not in named:
                fields.setdefault(r.mode, []).append(load)
    return {mode: f"no {' or '.join(dict.fromkeys(f))} load is declared; one would demand it" for mode, f in fields.items()}


def _probe(design: Design, name: str, load: str) -> Design:
    """The design with one more load case, giving `load` on component `name` as zero."""
    span = Span("<probe>", 0, 0)
    value = Input(f"{PROBE}.{name}.{load}", Quantity(Interval(Fraction(0), Fraction(0)), DIMENSIONLESS),
                  Signature("petra", "a load the design does not declare, added to see what coverage would demand"),
                  InputKind.ASSUMED, span)
    return dataclasses.replace(design, loads={**design.loads, PROBE: LoadCase(PROBE, (LoadEntry((name,), load, value),), span)})


def _requirement(outcome: Outcome) -> Requirement:
    return outcome.requirement if isinstance(outcome, (Waived, Open)) else outcome.obligation.requirement


def edge(found: tuple[Finding, ...], left: tuple[Unchecked, ...]) -> list[str]:
    """The lines after the obligation table that say where the checking stopped. One
    `excused` line per check a guard excuses, by obligation (subject/mode) and check name,
    its conditions joined by "; " and each said once across load cases. Then one `not
    checked` line per reason and set of components, naming the modes; a reason that names
    a load comes first, then CLAIM_ONLY, then NOT_DEMANDED."""
    excused: dict[tuple[str, str], list[str]] = {}
    for f in found:
        where = "/".join(f.requirement.split("/")[:2])
        for v in f.values:
            if v.excused:
                excused.setdefault((where, v.what), []).append(v.excuse or "a guard of its clause excuses it")
    lines = [f"excused    {where}: {what}: {'; '.join(dict.fromkeys(why))}" for (where, what), why in excused.items()]
    subjects: dict[tuple[str, str], list[str]] = {}
    for u in left:
        subjects.setdefault((u.reason, u.mode), []).append(u.subject)
    modes: dict[tuple[str, tuple[str, ...]], list[str]] = {}
    for (reason, mode), names in subjects.items():
        modes.setdefault((reason, tuple(names)), []).append(mode)
    order = {CLAIM_ONLY: 1, NOT_DEMANDED: 2}
    for reason, names in sorted(modes, key=lambda k: order.get(k[0], 0)):
        lines.append(f"not checked  {', '.join(modes[reason, names])} on {', '.join(names)}: {reason}")
    return lines


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
    requirement = _requirement(outcome)
    entry = requirement.origin.claim if isinstance(requirement.origin, ClaimOrigin) else COVERAGE_ENTRY
    kind = OUTCOMES[type(outcome)]
    category = DETAILING if requirement.mode.id in DETAILING_MODES else STRENGTH
    statement, refutation, rule = _parts(outcome)
    describe = outcome.obligation.describe if isinstance(outcome, (Discharged, Refuted, WithinMargin)) else requirement.id
    needs = tuple(describe_need(n) for n in outcome.needs) if isinstance(outcome, Open) else ()
    digest = None if statement is None else (outcome.theorem.statement_hash if isinstance(outcome, Discharged) else statement_hash(statement))
    outside = isinstance(outcome, Open) and any(isinstance(n, OutsideValidity) for n in outcome.needs)
    if statement is None or context is None or outside:
        note = ("nothing was stated to read" if statement is None else
                "its model is used outside its validity range, so the model's numbers say nothing here" if outside else
                "the report carries no design to read it against")
        return Finding(requirement.id, entry, category, kind, rule, digest, describe, (), None, None, (), needs, note)
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
    values = tuple(map(_rule, readout.values)) if DETAILING_MODES.get(requirement.mode.id) == RULE else readout.values
    values = _excused(values, statement, at, context, readout.dims, units)
    where = None if not values else ("box" if refutation is None else "point")
    claim = _claimed(requirement, values, units)
    return Finding(requirement.id, entry, category, kind, rule, digest, describe, values, where, claim, point, needs, readout.note)


def _rule(v: Value) -> Value:
    """A rule's term as met or not, by the levels or counts the reader gave."""
    met = v.demand is not None and v.capacity is not None and v.demand <= v.capacity
    return Value(v.what, None, None, None, v.excused, v.claimed, met, (), v.excuse)


# --- Why a term is excused ----------------------------------------------------------------


def _excused(values: tuple[Value, ...], statement: Statement, at: Mapping[str, Fraction] | None, context: _Context,
             dsg: Mapping[str, Dim], units: Mapping[Dim, str]) -> tuple[Value, ...]:
    """Each excused term the reader left unworded, with the condition that excuses it read
    from the statement (_excuse). The reader's terms are the goal's, in order, so a goal
    of another length leaves them as they are."""
    goal = statement.goal
    if not any(v.excused and v.excuse is None for v in values) or not isinstance(goal, AllNonpositive) or len(goal.exprs) != len(values):
        return values
    hyps = [h for h in statement.hyps if isinstance(h, RangeHyp)]
    box = {h.sym: Interval(at[h.label], at[h.label]) if at is not None and h.label in at else Interval(h.lo, h.hi) for h in hyps}
    dims = {h.sym: _label_dim(h.label, context, dsg) for h in hyps}
    kinds = {h.sym: label_kind(h.label) for h in hyps}
    return tuple(dataclasses.replace(v, excuse=_excuse(term, box, dims, kinds, units)) if v.excused and v.excuse is None else v
                 for v, term in zip(values, goal.exprs))


def _label_dim(label: str, context: _Context, dsg: Mapping[str, Dim]) -> Dim | None:
    kind = label_kind(label)
    if kind is LabelKind.REGISTRY:
        return context.registry_unit(label)[0]
    return (dsg if kind is LabelKind.DESIGN else context.dims).get(label)


def _excuse(term: Expr, box: Mapping[str, Interval], dims: Mapping[str, Dim | None], kinds: Mapping[str, LabelKind],
            units: Mapping[Dim, str]) -> str | None:
    """A guarded term is Min((check, *guards)), as the steel deck's builder writes it
    (models/steel/build.term): it holds where the check holds or where any guard is <= 0,
    the region where the clause excuses the formula. Each guard <= 0 over the box (or at
    the point) gives its condition (_condition), joined by "; ". None when the term is no
    such Min or no guard is <= 0 there."""
    if not isinstance(term, Min):
        return None
    try:
        found = [g for g in term.args[1:] if enclose(g, box).hi <= 0]
        return "; ".join(_condition(g, box, dims, kinds, units) for g in found) or None
    except (KeyError, KernelArithmeticError):
        return None


def _condition(guard: Expr, box: Mapping[str, Interval], dims: Mapping[str, Dim | None], kinds: Mapping[str, LabelKind],
               units: Mapping[Dim, str]) -> str:
    """`guard <= 0` as `a = x <= b = y`, its positive summands against its negated ones,
    each side's value over the box in the design's unit for its dimension. The side that
    names an input or a design value comes first: "ff1.distance = 20 inch >= W14x90.d / 2
    = 7 inch". Symbols print by their last two dotted parts (W14x90.d), or in full where
    two would print alike."""
    summands = list(_summands(guard))
    a = _sum([t for t in summands if not _negative(t)])
    b = _sum([t.arg if isinstance(t, Neg) else Const(-t.value) for t in summands if _negative(t)])
    full = _names(guard)
    short = {n: ".".join(n.removeprefix("const.").split(".")[-2:]) for n in full}
    shown = {n: s if list(short.values()).count(s) == 1 else n.removeprefix("const.") for n, s in short.items()}

    def side(e: Expr) -> str:
        return f"{_NAME.sub(lambda m: shown.get(m[0], m[0]), render(e))} = {_amount(e, box, dims, units)}"

    if not any(_negative(t) for t in summands):
        return f"{side(guard)} <= 0"
    design = {LabelKind.DESIGN, LabelKind.INPUT, LabelKind.PARAM}
    if any(kinds.get(n) in design for n in _names(b)) and not any(kinds.get(n) in design for n in _names(a)):
        return f"{side(b)} >= {side(a)}"
    return f"{side(a)} <= {side(b)}"


_NAME = re.compile(r"[A-Za-z_][\w.]*")
"""A symbol, or a function name, in the text `render` writes."""


def _names(expr: Expr) -> set[str]:
    return set(_NAME.findall(render(expr)))


def _summands(expr: Expr):
    if isinstance(expr, Add):
        for a in expr.args:
            yield from _summands(a)
    else:
        yield expr


def _negative(term: Expr) -> bool:
    return isinstance(term, Neg) or (isinstance(term, Const) and term.value < 0)


def _sum(terms: list[Expr]) -> Expr:
    return Const(Fraction(0)) if not terms else terms[0] if len(terms) == 1 else Add(tuple(terms))


def _amount(expr: Expr, box: Mapping[str, Interval], dims: Mapping[str, Dim | None], units: Mapping[Dim, str]) -> str:
    """Its value over the box, `lo to hi` where it ranges, in the unit `_unit` picks for
    its dimension; a bare SI number when the dimension is unknown."""
    value = enclose(expr, box)
    dim = _dim_of(expr, dims)
    unit = None if dim is None else _unit(dim, max(abs(value.lo), abs(value.hi)), units)
    scale = Fraction(1) if unit is None else _factor(unit)
    lo, hi = _number(float(value.lo / scale)), _number(float(value.hi / scale))
    return f"{lo if lo == hi else f'{lo} to {hi}'}{_unit_text(unit)}"


def _dim_of(expr: Expr, dims: Mapping[str, Dim | None]) -> Dim | None:
    """The dimension of an expression over symbols of known dimension, or None."""
    match expr:
        case Sym(name=name):
            return dims.get(name)
        case Const():
            return DIMENSIONLESS
        case Neg(arg=a) | Abs(arg=a):
            return _dim_of(a, dims)
        case Add(args=args) | Min(args=args) | Max(args=args):
            found = {_dim_of(a, dims) for a in args}
            return found.pop() if len(found) == 1 else None
        case Mul(args=args):
            return functools.reduce(lambda x, y: _power(x, y, 1), (_dim_of(a, dims) for a in args), DIMENSIONLESS)
        case Div(num=n, den=d):
            return _power(_dim_of(n, dims), _dim_of(d, dims), -1)
        case PowInt(base=b, exponent=k):
            return _power(DIMENSIONLESS, _dim_of(b, dims), k)
        case Sqrt(arg=a):
            inner = _dim_of(a, dims)
            if inner is not None and not any(e % 2 for e in dataclasses.astuple(inner)):
                return Dim(*(e // 2 for e in dataclasses.astuple(inner)))
    return None


def _power(a: Dim | None, b: Dim | None, k: int) -> Dim | None:
    """a times b to the k."""
    if a is None or b is None:
        return None
    return Dim(*(x + k * y for x, y in zip(dataclasses.astuple(a), dataclasses.astuple(b))))


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
    carried = [v.ratio for v in values if v.claimed and not v.excused and v.ratio is not None and math.isfinite(v.ratio)]
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
    names = TERMS.get(requirement.mode.id) or _port_terms(requirement, len(goal.exprs))
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
        out.append(Value(what, unit, float(demand / factor), float(capacity / factor), False, claimed, None, ()))
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
    what = "load factor: the claimed factor against the largest one a static field within every member's capacity carries"
    if found.status == 2:   # infeasible at every t >= 0, t = 0 included: the self-weight alone is not carried
        what += "; none, since no static field carries the self-weight alone"
        carried = 0.0
    elif found.status == 3:
        carried = math.inf
    elif found.status != 0:
        return Readout((), {}, f"the load factor could not be computed here: {found.message}")
    else:
        carried = float(claimed) * float(found.x[-1])
    return Readout((Value(what, "1", float(claimed), carried, False, True, None, ()),), {}, None)


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


def _finite(x: float | None) -> float | None:
    return x if x is not None and math.isfinite(x) else None


def _unit_text(unit: str | None) -> str:
    return "" if unit in (None, "1") else f" {unit}"


def _value_text(v: Value) -> str:
    if v.demand is None or v.capacity is None:
        return f"{v.what}: {'met' if v.met else 'not met'}"
    unit = _unit_text(v.unit)
    base = " (SI base units)" if v.unit is None else ""
    return f"{v.what}: demand {_number(v.demand)}{unit}, capacity {_number(v.capacity)}{unit}, utilisation {_ratio(v.utilisation)}{base}"


def _parts_lines(v: Value) -> list[str]:
    """What a capacity made of parts is made of: the weakest part with every limit, then
    each other part with the limit that sets it."""
    if not v.parts:
        return []
    weakest, *rest = v.parts
    return [f"weakest    {weakest.text(v.unit, True)}", *(f"part       {p.text(v.unit, False)}" for p in rest)]


__all__ = ["Claimed", "Coordinate", "Finding", "Governing", "Limit", "Part", "Readout", "Unchecked", "Value", "edge", "findings",
           "governing", "summary", "unchecked", "CLAIM_ONLY", "DETAILING_MODES", "NOT_DEMANDED", "READERS", "TERMS"]
