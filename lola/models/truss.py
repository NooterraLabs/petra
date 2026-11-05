"""Domain: pin-jointed 2D trusses. Trusted physics; appears in footprints as the
validated_model premises "model:truss.*@<hash>".

Component kind `truss`. Attribute lines, one per line inside the block:

    material <registry material id>                default for every member
    section <registry section id>                  default for every member
    node <name> at (<x>, <y>) [support pinned|roller_x|roller_y]     lengths, exact
    member <name>: <node> -- <node> [section <id>] [material <id>]

Sections are circular hollow sections (registry props D, t, A, I), so one second moment
serves buckling about every axis. Materials need fy and E.

Load fields: fx and fy on `<truss>.<node>`. Claim paths: `<truss>.<qoi>` and
`<truss>.member(<member>).<qoi>`.

Everything is written in force densities q_i = N_i / L_i, because with rational node
coordinates the equilibrium matrix in force densities is exact:

    sum over members at node n of  q_i (x_other - x_n)  +  f_n  =  0     (free DOFs only)

so B has entries x_j - x_i, y_j - y_i, and lengths enter only through L_i^2 (rational)
and Sqrt(L_i^2) inside capacity Exprs, which the kernel encloses rigorously. Node
coordinates enter those Exprs as design-value hypotheses. Every builder states one
obligation per load case.

Mapping onto kernel goals:
  plastic collapse   R1  LinearFeasible: B q = lambda f(h);  -C_i/L_i <= q_i <= T_i/L_i
                         T_i = A_i fy_i ;  C_i = min(A_i fy_i, pi^2 E_i I_i / L_i^2)
                         lambda is the claimed factor as a constant, since R1 needs b
                         affine in the hypotheses. Mechanism FAIL = FarkasRay.
  elastic response   R3  QuadraticProblem(B, f(h), w_i = L_i^3 E_0 / (E_i A_i)): the
                         complementary energy sum q^2 L^3 / (E A) scaled by E_0, the first
                         member's modulus. A positive scale leaves the minimiser unchanged
                         and cancels a modulus every member shares, so the member forces of
                         a one-material truss do not inherit the range of E.
                         stress = q_i L_i / A_i ; strain = q_i L_i / (E_i A_i) ;
                         compliance = energy / E_0.
  global stability   R2  GramPositiveDefinite over free DOFs:
                         sum_i (E_i A_i / L_i^3) d_i d_i^T                  (material)
                       + sum_i min(0, lambda N_i / L_i) H_i H_i^T           (geometric, H = [I; -I])
                         N_i are DefinedHyps naming the elastic member forces (R3 lemma in
                         the evidence). min(0, .) drops tension stiffening, so the statement
                         covers every factor in [0, lambda]: for those factors
                         factor * q_i >= min(0, lambda q_i) in the Loewner sum.
  member buckling    R4  AllNonpositive: -N_i - u pi^2 E_i I_i / L_i^2 <= 0, with N_i a
                         DefinedHyp, one obligation per member so a FAIL names the member.
                         buckling_utilisation = -N / (pi^2 E I / L^2), negative in tension.
  small strain       R3  ComponentBound strain_i in [-eps_max, eps_max]: the elastic model's
                         validity range, checked rather than stated, and attached to every
                         elastic obligation.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from typing import Callable, Mapping

from ..ir import Component, Design, Exceeds, Fixed, Input, Punct, Ref, Rel, Span, Vec
from ..kernel import Add, Const, Div, Expr, Interval, Matrix, Min, Mul, Neg, Pi, PowInt, Sqrt
from ..kernel.rules.r1_linear import LinearFeasible
from ..kernel.rules.r2_definite import GramPositiveDefinite, GramTerm
from ..kernel.rules.r3_hypercircle import ComponentBound, MinimizerBound, MinimizerComponent, QuadraticProblem
from ..kernel.rules.r4_enclosure import AllNonpositive
from ..registry import OutsideMakeableSet, PartKind, Registry
from ..units import DIMENSIONLESS, ENERGY, FORCE, LENGTH, STRESS, Dim, Quantity, format_quantity
from .base import (
    NO_PORTS,
    ComponentError,
    CoverageRule,
    Criterion,
    DomainSpec,
    Elaborated,
    EnergyDomain,
    FailureMode,
    Feature,
    FeatureKind,
    Gap,
    ModelSpec,
    NeedsInputBound,
    NoRuleForQuantity,
    Obligation,
    Ports,
    Requirement,
    StatementBuilder,
    model_spec,
)

# --- Typed model, produced by lower_truss ------------------------------------------


class Support(Enum):
    FREE = "free"
    PINNED = "pinned"
    ROLLER_X = "roller_x"   # moves along x, restrained in y
    ROLLER_Y = "roller_y"   # moves along y, restrained in x


@dataclass(frozen=True, slots=True)
class Node:
    name: str
    x: Fraction   # metres, exact
    y: Fraction
    support: Support


@dataclass(frozen=True, slots=True)
class Member:
    name: str
    start: str
    end: str
    section: str    # registry part id, kind SECTION
    material: str   # registry material id


@dataclass(frozen=True, slots=True)
class Truss:
    name: str
    nodes: tuple[Node, ...]
    members: tuple[Member, ...]
    span: Span


_SUPPORTS = {s.value: s for s in Support if s is not Support.FREE}
_FIXES = {Support.FREE: (), Support.PINNED: ("x", "y"), Support.ROLLER_X: ("y",), Support.ROLLER_Y: ("x",)}
_SECTION_PROPS = ("D", "t", "A", "I")
_MATERIAL_PROPS = ("fy", "E")
_LOAD_FIELDS = {"fx": "x", "fy": "y"}


def lower_truss(component: Component, design: Design, registry: Registry) -> Truss:
    """Parse the attribute lines in the module docstring. Rejects (ComponentError):
    duplicate names, a member naming an unknown node, a zero-length member, a node with
    no member, coordinates that are not exact lengths, registry ids of the wrong kind, a
    section that is not a circular hollow section, a material without fy and E, a load
    field other than fx and fy, a load on an unknown node, a claim qoi not in QOIS or on
    the wrong path, a probability claim or tests record (trusses have neither in v0), and
    a waiver on anything but the truss or one of its members."""
    problems: list[str] = []
    name = component.name

    def problem(span: Span, message: str) -> None:
        problems.append(f"{span.path}:{span.line}:{span.col}: {message}")

    defaults: dict[str, str] = {}
    nodes: dict[str, Node] = {}
    lines: dict[str, tuple[str, str, dict[str, str], Span]] = {}
    for attr in component.attrs:
        if attr.key in ("material", "section"):
            ident = _dotted(attr.args[0]) if len(attr.args) == 1 else None
            if ident is None:
                problem(attr.span, f"expected `{attr.key} <registry id>`")
            elif attr.key in defaults:
                problem(attr.span, f"{name} gives its default {attr.key} twice")
            else:
                defaults[attr.key] = ident
        elif attr.key == "node":
            node = _node(attr.args)
            if isinstance(node, str):
                problem(attr.span, node)
            elif node.name in nodes:
                problem(attr.span, f"node {node.name} is declared twice")
            else:
                nodes[node.name] = node
        elif attr.key == "member":
            member = _member(attr.args)
            if isinstance(member, str):
                problem(attr.span, member)
            elif member[0] in lines:
                problem(attr.span, f"member {member[0]} is declared twice")
            else:
                lines[member[0]] = (*member[1:], attr.span)
        else:
            problem(attr.span, f"unknown truss attribute '{attr.key}'; expected material, section, node or member")

    members: list[Member] = []
    for member_name, (start, end, options, span) in lines.items():
        section = options.get("section", defaults.get("section"))
        material = options.get("material", defaults.get("material"))
        unknown = [n for n in (start, end) if n not in nodes]
        if unknown:
            problem(span, f"member {member_name} names unknown node {unknown[0]}")
        elif (nodes[start].x, nodes[start].y) == (nodes[end].x, nodes[end].y):
            problem(span, f"member {member_name} has zero length")
        if section is None or material is None:
            missing = "section" if section is None else "material"
            problem(span, f"member {member_name} has no {missing}; give a default {missing} line or a member option")
        members.append(Member(member_name, start, end, section, material))
    if not lines:
        problem(component.span, f"truss {name} has no members")
    connected = {n for start, end, _, _ in lines.values() for n in (start, end)}
    for node in nodes.values():
        if node.name not in connected:
            problem(component.span, f"node {node.name} has no member")
    for section in sorted({m.section for m in members} - {None}):
        found = _entry_problem(lambda i: registry.part(i, PartKind.SECTION), section, _SECTION_PROPS, "a circular hollow section")
        if found:
            problem(component.span, found)
    for material in sorted({m.material for m in members} - {None}):
        found = _entry_problem(registry.material, material, _MATERIAL_PROPS, "a structural material")
        if found:
            problem(component.span, found)
    _check_references(name, nodes, lines, design, problem)
    if problems:
        raise ComponentError(tuple(problems))
    return Truss(name, tuple(nodes.values()), tuple(members), component.span)


def _word(arg: object) -> str | None:
    return arg.parts[0] if isinstance(arg, Ref) and len(arg.parts) == 1 else None


def _dotted(arg: object) -> str | None:
    return ".".join(arg.parts) if isinstance(arg, Ref) else None


def _node(args: tuple) -> Node | str:
    usage = "expected `node <name> at (<x>, <y>) [support pinned|roller_x|roller_y]`"
    if not (len(args) in (3, 5) and _word(args[0]) and _word(args[1]) == "at" and isinstance(args[2], Vec) and len(args[2].items) == 2):
        return usage
    support = Support.FREE
    if len(args) == 5:
        if _word(args[3]) != "support":
            return usage
        if _word(args[4]) not in _SUPPORTS:
            return f"unknown support {_dotted(args[4])}; expected pinned, roller_x or roller_y"
        support = _SUPPORTS[_word(args[4])]
    x, y = args[2].items
    if any(q.dim != LENGTH or q.value.lo != q.value.hi for q in (x, y)):
        return f"node {_word(args[0])}: coordinates must be exact lengths"
    return Node(_word(args[0]), x.value.lo, y.value.lo, support)


def _member(args: tuple) -> tuple[str, str, str, dict[str, str]] | str:
    """(name, start, end, options) or the problem text."""
    usage = "expected `member <name>: <node> -- <node> [section <id>] [material <id>]`"
    shape = (
        len(args) >= 5 and len(args) % 2 == 1 and _word(args[0]) and isinstance(args[1], Punct) and args[1].text == ":"
        and _word(args[2]) and isinstance(args[3], Punct) and args[3].text == "--" and _word(args[4])
    )
    if not shape:
        return usage
    options: dict[str, str] = {}
    for key, value in zip(args[5::2], args[6::2]):
        if _word(key) not in ("section", "material") or _dotted(value) is None or _word(key) in options:
            return usage
        options[_word(key)] = _dotted(value)
    return (_word(args[0]), _word(args[2]), _word(args[4]), options)


def _entry_problem(lookup: Callable, ident: str, props: tuple[str, ...], what: str) -> str | None:
    try:
        entry = lookup(ident)
    except OutsideMakeableSet as exc:
        return str(exc)
    missing = [p for p in props if p not in entry.props]
    return f"{ident} is not {what}: it has no {', '.join(missing)}" if missing else None


def _check_references(name: str, nodes: Mapping, members: Mapping, design: Design, problem: Callable) -> None:
    """Every load entry, claim, probability claim, tests record and waiver on the truss."""
    for case in design.loads.values():
        for entry in case.entries:
            if entry.target[0] != name:
                continue
            span = entry.value.span if isinstance(entry.value, Input) else case.span
            target = ".".join(entry.target)
            if len(entry.target) != 2 or entry.target[1] not in nodes:
                problem(span, f"load {case.name} targets {target}, which is not a node of {name}")
            if entry.field not in _LOAD_FIELDS:
                problem(span, f"load {case.name} on {target} has field {entry.field}; a truss node takes fx and fy")
            value = entry.value.range if isinstance(entry.value, Input) else design.params[entry.value.name].range
            if value.dim != FORCE:
                problem(span, f"load {case.name} on {target}.{entry.field} must be a force")
    for claim in design.claims:
        path, qoi = claim.qoi.path, claim.qoi.name
        if path[0] != name:
            continue
        if qoi not in QOIS:
            problem(claim.span, f"claim {claim.name}: {name} has no quantity {qoi}; known: {', '.join(sorted(QOIS))}")
            continue
        dim, per_member = _QOI_FORMS[qoi]
        if per_member and not (len(path) == 2 and path[1] in members):
            problem(claim.span, f"claim {claim.name}: {qoi} is claimed on {name}.member(<member>)")
        elif not per_member and len(path) != 1:
            problem(claim.span, f"claim {claim.name}: {qoi} is claimed on {name} itself")
        if claim.bound.dim != dim:
            problem(claim.span, f"claim {claim.name}: {qoi} is bounded by a {_DIM_TEXT[dim]} quantity")
    for pc in design.probability_claims:
        subject = pc.event.qoi.path if isinstance(pc.event, Exceeds) else pc.event.subject
        if subject[0] == name:
            problem(pc.span, f"probability claim {pc.name}: trusses have no probability model in v0")
    for record in design.tests.values():
        if record.subject[0] == name:
            problem(record.span, f"tests {record.name}: trusses have no tested failure model in v0")
    for waiver in design.waivers:
        if waiver.subject[0] == name and not (len(waiver.subject) == 1 or (len(waiver.subject) == 2 and waiver.subject[1] in members)):
            problem(waiver.span, f"a waiver on {'.'.join(waiver.subject)} names neither {name} nor one of its members")


# --- Modes, quantities, model premises -----------------------------------------------

PLASTIC_COLLAPSE = FailureMode("truss.plastic_collapse")
GLOBAL_STABILITY = FailureMode("truss.global_stability")
MEMBER_BUCKLING = FailureMode("truss.member_buckling")
ELASTIC_STRESS = FailureMode("truss.elastic_stress")
COMPLIANCE = FailureMode("truss.compliance")
SMALL_STRAIN = FailureMode("truss.small_strain")

SMALL_STRAIN_LIMIT = Fraction(1, 500)
"""|strain| <= 0.002: the range inside which the linear elastic model is used."""

_MAINTAINERS = "lola-maintainers"
_EULER_CAVEAT = (
    "the compression capacity is the bare Euler load pi^2 E I / L^2 with no imperfection "
    "reduction, which is unconservative against design codes (EN 1993-1-1 6.3.1 reduces it "
    "with a buckling curve)"
)
_PLASTIC = model_spec(
    sys.modules[__name__], "truss.plastic",
    "rigid-perfectly-plastic pin-jointed 2D truss, static (lower-bound) theorem",
    "joints are frictionless pins; members are prismatic and loaded only at their ends; "
    "displacements are small; the tension capacity is A fy; " + _EULER_CAVEAT,
    _MAINTAINERS, "lower-bound theorem of plastic collapse (Gvozdev 1938; Neal, The Plastic Methods of Structural Analysis)",
)
_ELASTIC = model_spec(
    sys.modules[__name__], "truss.elastic",
    "linear elastic pin-jointed 2D truss: member forces minimise the complementary energy sum N^2 L / (E A)",
    "joints are frictionless pins; members are prismatic, linear elastic and loaded only at "
    "their ends; |strain| <= 0.002 in every member (checked by the small-strain bound)",
    _MAINTAINERS, "principle of minimum complementary energy; Prager and Synge (1947) hypercircle bounds",
)
_STABILITY = model_spec(
    sys.modules[__name__], "truss.stability",
    "linear prebuckling of a pin-jointed 2D truss, Green-strain geometric stiffness of the elastic member forces",
    "member forces come from the linear elastic model and scale with the load factor; "
    "tension stiffening is ignored, which is conservative; buckling of a member between "
    "its joints is checked separately by truss.euler",
    _MAINTAINERS, "linearised buckling eigenproblem (K + lambda K_G) of a pin-jointed truss",
)
_EULER = model_spec(
    sys.modules[__name__], "truss.euler",
    "pin-ended prismatic Euler column: compression N <= u pi^2 E I / L^2",
    "members are straight, prismatic, pin-ended and elastic, with one second moment about "
    "every axis (circular hollow sections), carrying the linear elastic member force; "
    "no imperfection reduction is applied, so the bare Euler load is unconservative "
    "against EN 1993-1-1 6.3.1 buckling curves",
    _MAINTAINERS, "Euler (1744) critical load of a pin-ended column",
)

MODELS: Mapping[FailureMode, ModelSpec] = {
    PLASTIC_COLLAPSE: _PLASTIC,
    ELASTIC_STRESS: _ELASTIC,
    COMPLIANCE: _ELASTIC,
    SMALL_STRAIN: _ELASTIC,
    GLOBAL_STABILITY: _STABILITY,
    MEMBER_BUCKLING: _EULER,
}

QOIS: Mapping[str, FailureMode] = {
    "collapse_factor": PLASTIC_COLLAPSE,
    "stability_factor": GLOBAL_STABILITY,
    "stress": ELASTIC_STRESS,
    "compliance": COMPLIANCE,
    "buckling_utilisation": MEMBER_BUCKLING,
}
"""Claimable quantities. `frame.collapse_factor >= 1.5`, `frame.member(m3).stress <= 200 MPa`."""

_QOI_FORMS: Mapping[str, tuple[Dim, bool]] = {
    "collapse_factor": (DIMENSIONLESS, False),
    "stability_factor": (DIMENSIONLESS, False),
    "stress": (STRESS, True),
    "compliance": (ENERGY, False),
    "buckling_utilisation": (DIMENSIONLESS, True),
}
"""Per qoi: the dimension of its bound, and whether the claim path names a member."""

_DIM_TEXT = {DIMENSIONLESS: "dimensionless", STRESS: "stress", ENERGY: "energy"}

# --- Elaboration -------------------------------------------------------------------------


@dataclass(frozen=True)
class TrussGeometry:
    """Exact geometry derived once per truss. Pure function of the typed model."""

    dofs: tuple[tuple[str, str], ...]            # (node, "x"|"y") for free DOFs, in order
    B: Matrix                                    # len(dofs) x len(members), force-density form
    diff: tuple[tuple[Fraction, Fraction], ...]  # (x_end - x_start, y_end - y_start) per member
    length_sq: tuple[Fraction, ...]
    material_dir: tuple[Matrix, ...]             # d_i embedded in free DOFs, n x 1
    geometric_dir: tuple[Matrix, ...]            # [I; -I] embedded in free DOFs, n x 2


def geometry(truss: Truss) -> TrussGeometry:
    """Free DOFs in node order, x before y (PINNED fixes x and y, ROLLER_X fixes y,
    ROLLER_Y fixes x). B q = f is nodal equilibrium with tension positive: column i holds
    +diff_i at the end node's free DOFs and -diff_i at the start node's."""
    dofs = tuple((n.name, axis) for n in truss.nodes for axis in ("x", "y") if axis not in _FIXES[n.support])
    row = {dof: i for i, dof in enumerate(dofs)}
    at = {n.name: (n.x, n.y) for n in truss.nodes}
    diffs, entries, material, geometric = [], [], [], []
    for j, m in enumerate(truss.members):
        diff = (at[m.end][0] - at[m.start][0], at[m.end][1] - at[m.start][1])
        diffs.append(diff)
        column, h = [], []
        for k, axis in enumerate(("x", "y")):
            for node, sign in ((m.start, -1), (m.end, 1)):
                i = row.get((node, axis))
                if i is not None:
                    h.append((i, k, Fraction(-sign)))
                    if diff[k]:
                        column.append((i, sign * diff[k]))
        column.sort()
        entries += [(i, j, v) for i, v in column]
        material.append(Matrix(len(dofs), 1, tuple((i, 0, v) for i, v in column)))
        geometric.append(Matrix(len(dofs), 2, tuple(sorted(h))))
    return TrussGeometry(
        dofs=dofs,
        B=Matrix(len(dofs), len(truss.members), tuple(sorted(entries))),
        diff=tuple(diffs),
        length_sq=tuple(dx * dx + dy * dy for dx, dy in diffs),
        material_dir=tuple(material),
        geometric_dir=tuple(geometric),
    )


@dataclass(frozen=True)
class _Terms:
    """One member's premise expressions inside one statement."""

    length_sq: Expr
    length: Expr
    area: Expr
    second_moment: Expr
    modulus: Expr
    yield_strength: Expr

    @property
    def euler(self) -> Expr:
        return Div(Mul((PowInt(Pi(), 2), self.modulus, self.second_moment)), self.length_sq)


def _terms(truss: Truss, sb: StatementBuilder) -> tuple[_Terms, ...]:
    nodes = {n.name: n for n in truss.nodes}

    def coordinate(node: Node, axis: str) -> Expr:
        value = node.x if axis == "x" else node.y
        return sb.value(Fixed(Quantity(Interval(value, value), LENGTH)), f"{truss.name}.{node.name}.{axis}")

    out = []
    for m in truss.members:
        start, end = nodes[m.start], nodes[m.end]
        length_sq = Add(tuple(PowInt(Add((coordinate(end, a), Neg(coordinate(start, a)))), 2) for a in ("x", "y")))
        out.append(_Terms(
            length_sq=length_sq,
            length=Sqrt(length_sq),
            area=sb.registry(m.section, "A"),
            second_moment=sb.registry(m.section, "I"),
            modulus=sb.registry(m.material, "E"),
            yield_strength=sb.registry(m.material, "fy"),
        ))
    return tuple(out)


def load_vector(truss: Truss, design: Design, sb: StatementBuilder, under: tuple[str, ...], factor: Fraction) -> tuple:
    """f(h) over free DOFs, the sum of every load entry on the truss in the named load
    cases, each a signed input (or a family's param) hypothesis, scaled by the constant
    `factor`. A load on a restrained DOF goes straight into its support and is dropped."""
    row = {dof: i for i, dof in enumerate(geometry(truss).dofs)}
    sums: list[list[Expr]] = [[] for _ in row]
    for case in under:
        for entry in design.loads[case].entries:
            i = row.get((entry.target[-1], _LOAD_FIELDS.get(entry.field))) if entry.target[0] == truss.name else None
            if i is not None:
                value = entry.value
                sums[i].append(sb.input(value) if isinstance(value, Input) else sb.param(design.params[value.name]))
    out = []
    for terms in sums:
        total = Const(Fraction(0)) if not terms else terms[0] if len(terms) == 1 else Add(tuple(terms))
        out.append(total if factor == 1 or not terms else Mul((Const(Fraction(factor)), total)))
    return tuple(out)


def elastic_problem(truss: Truss, design: Design, sb: StatementBuilder, under: tuple[str, ...]) -> QuadraticProblem:
    """The one QuadraticProblem for this truss and load set. R3 goals and every DefinedHyp
    use this exact term, so their definitions are equal by hash. Weights carry the scale
    E_0 of the module docstring."""
    terms = _terms(truss, sb)
    modulus = terms[0].modulus
    weights = tuple(
        Div(PowInt(t.length, 3), t.area) if t.modulus == modulus
        else Div(Mul((PowInt(t.length, 3), modulus)), Mul((t.modulus, t.area)))
        for t in terms
    )
    return QuadraticProblem(geometry(truss).B, load_vector(truss, design, sb, under, Fraction(1)), weights)


def _cases(req: Requirement, truss: Truss, design: Design) -> tuple[str, ...]:
    """The load cases named by the requirement, or every case that loads the truss."""
    if req.under:
        return req.under
    return tuple(name for name, case in design.loads.items() if any(e.target[0] == truss.name for e in case.entries))


def _limit(req: Requirement, rel: Rel) -> Fraction | None:
    """The strictest end of the criterion's bound when its relation is `rel`."""
    c = req.criterion
    if not isinstance(c, Criterion) or c.rel is not rel:
        return None
    return c.bound.value.lo if rel is Rel.LE else c.bound.value.hi


def _no_rule(req: Requirement, reason: str) -> tuple[Elaborated, ...]:
    return (Gap(req, (NoRuleForQuantity(req.qoi.name if req.qoi is not None else req.mode.id, reason),)),)


def _unloaded(req: Requirement, truss: Truss) -> tuple[Elaborated, ...]:
    return (Gap(req, (NeedsInputBound((truss.name,), "load", "N"),)),)


def _text(x: Fraction, unit: str = "1") -> str:
    dim = {"1": DIMENSIONLESS, "MPa": STRESS, "J": ENERGY}[unit]
    return format_quantity(Quantity(Interval(x, x), dim), unit)


def build_plastic_collapse(req: Requirement, truss: Truss, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """One R1 statement per load case at the claimed factor. A collapse factor is >= 0 by
    definition, so a bound below 0 is stated at 0."""
    factor = _limit(req, Rel.GE)
    if factor is None:
        return _no_rule(req, "v0 proves lower bounds on a collapse factor only")
    cases = _cases(req, truss, design)
    if not cases:
        return _unloaded(req, truss)
    factor = max(factor, Fraction(0))
    B = geometry(truss).B
    out = []
    for case in cases:
        sb = StatementBuilder(design, registry)
        terms = _terms(truss, sb)
        squash = [Mul((t.area, t.yield_strength)) for t in terms]
        goal = LinearFeasible(
            A=B,
            b=load_vector(truss, design, sb, (case,), factor),
            lower=tuple(Neg(Div(Min((p, t.euler)), t.length)) for p, t in zip(squash, terms)),
            upper=tuple(Div(p, t.length) for p, t in zip(squash, terms)),
        )
        describe = f"a static field within every member's capacity carries {_text(factor)} times load case {case} on {truss.name}"
        out.append(Obligation(req, sb.finish(goal), MODELS[PLASTIC_COLLAPSE], describe))
    return tuple(out)


def build_elastic(req: Requirement, truss: Truss, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """Stress, compliance and small-strain requirements all become MinimizerBound goals
    on elastic_problem; the small-strain bound is attached to every elastic obligation.
    Stress is bounded in magnitude, |N| / A <= X."""
    limit = _limit(req, Rel.LE)
    if limit is None:
        return _no_rule(req, f"v0 bounds {req.mode.id} from above only")
    cases = _cases(req, truss, design)
    if not cases:
        return _unloaded(req, truss)
    eps = limit if req.mode == SMALL_STRAIN else SMALL_STRAIN_LIMIT
    index = [m.name for m in truss.members].index(req.subject[1]) if req.mode == ELASTIC_STRESS else None
    out = []
    for case in cases:
        sb = StatementBuilder(design, registry)
        terms = _terms(truss, sb)
        problem = elastic_problem(truss, design, sb, (case,))
        strain = tuple(
            ComponentBound(i, Div(t.length, Mul((t.modulus, t.area))), Const(-eps), Const(eps)) for i, t in enumerate(terms)
        )
        bounds, energy, what = strain, None, f"every member strain of {truss.name} stays within {_text(eps)}"
        if req.mode == ELASTIC_STRESS:
            t = terms[index]
            bounds = (ComponentBound(index, Div(t.length, t.area), Const(-limit), Const(limit)),) + strain
            what = f"the stress magnitude in {truss.name}.{req.subject[1]} stays within {_text(limit, 'MPa')} and {what}"
        elif req.mode == COMPLIANCE:
            energy = Mul((Const(limit), terms[0].modulus))
            what = f"the compliance of {truss.name} stays within {_text(limit, 'J')} and {what}"
        describe = f"{what} under load case {case}"
        out.append(Obligation(req, sb.finish(MinimizerBound(problem, bounds, energy)), MODELS[req.mode], describe))
    return tuple(out)


def _force(truss: Truss, sb: StatementBuilder, problem: QuadraticProblem, terms: tuple[_Terms, ...], index: int) -> Expr:
    """DefinedHyp N_i = L_i q_i*, the elastic force in member `index`."""
    member = truss.members[index].name
    return sb.defined(f"{truss.name}.{member}.N", MinimizerComponent(problem, index, terms[index].length))


def build_global_stability(req: Requirement, truss: Truss, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """A statically indeterminate truss whose lemma ranges lose too much correlation is
    still stated; a solver that cannot prove it leaves NeedsCertificate."""
    factor = _limit(req, Rel.GE)
    if factor is None:
        return _no_rule(req, "v0 proves lower bounds on a stability factor only")
    cases = _cases(req, truss, design)
    if not cases:
        return _unloaded(req, truss)
    factor = max(factor, Fraction(0))
    geom = geometry(truss)
    out = []
    for case in cases:
        sb = StatementBuilder(design, registry)
        terms = _terms(truss, sb)
        problem = elastic_problem(truss, design, sb, (case,))
        material = tuple(
            GramTerm(Div(Mul((t.modulus, t.area)), PowInt(t.length, 3)), d) for t, d in zip(terms, geom.material_dir)
        )
        geometric = tuple(
            GramTerm(Min((Const(Fraction(0)), Div(Mul((Const(factor), _force(truss, sb, problem, terms, i))), t.length))), h)
            for i, (t, h) in enumerate(zip(terms, geom.geometric_dir))
        )
        goal = GramPositiveDefinite(len(geom.dofs), material + geometric)
        describe = f"{truss.name} stays stable in linear prebuckling for every load factor up to {_text(factor)} times load case {case}"
        out.append(Obligation(req, sb.finish(goal), MODELS[GLOBAL_STABILITY], describe))
    return tuple(out)


def build_member_buckling(req: Requirement, truss: Truss, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    limit = _limit(req, Rel.LE)
    if limit is None:
        return _no_rule(req, "v0 bounds a buckling utilisation from above only")
    cases = _cases(req, truss, design)
    if not cases:
        return _unloaded(req, truss)
    index = [m.name for m in truss.members].index(req.subject[1])
    out = []
    for case in cases:
        sb = StatementBuilder(design, registry)
        terms = _terms(truss, sb)
        force = _force(truss, sb, elastic_problem(truss, design, sb, (case,)), terms, index)
        goal = AllNonpositive((Add((Neg(force), Neg(Mul((Const(limit), terms[index].euler))))),))
        describe = f"the compression in {truss.name}.{req.subject[1]} is at most {_text(limit)} times its Euler load under load case {case}"
        out.append(Obligation(req, sb.finish(goal), MODELS[MEMBER_BUCKLING], describe))
    return tuple(out)


# --- Coverage ------------------------------------------------------------------------

FRAME = FeatureKind("truss.frame")
AXIAL_MEMBER = FeatureKind("truss.axial_member")


def features(truss: Truss, design: Design, registry: Registry) -> tuple[Feature, ...]:
    """One FRAME feature for the truss and one AXIAL_MEMBER feature per member, with
    their materials, energy {MECHANICAL} and the environment. Trusses report no contact
    pairs in v0."""
    energy = frozenset({EnergyDomain.MECHANICAL})
    frame = Feature((truss.name,), FRAME, tuple(sorted({m.material for m in truss.members})), energy, design.environment)
    return (frame, *(Feature((truss.name, m.name), AXIAL_MEMBER, (m.material,), energy, design.environment) for m in truss.members))


def _is_frame(feature: Feature, registry: Registry) -> bool:
    return feature.kind == FRAME


def _is_axial_member(feature: Feature, registry: Registry) -> bool:
    return feature.kind == AXIAL_MEMBER


_DEFAULTS: Mapping[FailureMode, tuple[Rel, Fraction]] = {
    PLASTIC_COLLAPSE: (Rel.GE, Fraction(1)),
    GLOBAL_STABILITY: (Rel.GE, Fraction(1)),
    MEMBER_BUCKLING: (Rel.LE, Fraction(1)),
    SMALL_STRAIN: (Rel.LE, SMALL_STRAIN_LIMIT),
}


def _default_criterion(mode: FailureMode, feature: Feature) -> Criterion | None:
    """Collapse and stability factor >= 1, buckling utilisation <= 1, strain within the
    elastic model's validity range."""
    found = _DEFAULTS.get(mode)
    if found is None:
        return None
    rel, bound = found
    return Criterion(rel, Quantity(Interval(bound, bound), DIMENSIONLESS))


COVERAGE: tuple[CoverageRule, ...] = (
    CoverageRule(
        id="truss.frame",
        when=_is_frame,
        demands=(PLASTIC_COLLAPSE, GLOBAL_STABILITY, SMALL_STRAIN),
        default=_default_criterion,
        note="every truss can collapse or destabilise, and its stability and buckling checks "
             "use elastic member forces, which hold only inside the small-strain range",
    ),
    CoverageRule(
        id="truss.axial_member",
        when=_is_axial_member,
        demands=(MEMBER_BUCKLING,),
        default=_default_criterion,
        note="every axial member can buckle between its joints",
    ),
)


def ports(truss: Truss, registry: Registry) -> Ports:
    """No ports in v0. Trusses connect to the world through supports and signed loads."""
    return NO_PORTS


DOMAIN = DomainSpec(
    name="truss",
    kinds={"truss": lower_truss},
    builders={
        PLASTIC_COLLAPSE: build_plastic_collapse,
        ELASTIC_STRESS: build_elastic,
        COMPLIANCE: build_elastic,
        SMALL_STRAIN: build_elastic,
        GLOBAL_STABILITY: build_global_stability,
        MEMBER_BUCKLING: build_member_buckling,
    },
    unmodelled=frozenset(),
    qois=QOIS,
    probability={},
    coverage=COVERAGE,
    models=MODELS,
    features=features,
    ports=ports,
)
