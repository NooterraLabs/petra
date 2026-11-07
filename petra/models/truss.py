"""Domain: pin-jointed 2D trusses. Trusted physics; appears in footprints as the
validated_model premises "model:truss.*@<hash>".

Component kind `truss`. Its attribute lines, one per line inside the block, are GRAMMAR
below (`petra kinds truss` prints them).

Sections are circular hollow sections (registry props D, t, A, I and buckling_alpha, the
imperfection factor of the section's EN 1993-1-1 buckling curve), so one second moment
serves buckling about every axis. Materials need fy, E and density, and belong to the
family of the section's own material, since a buckling curve is drawn for one.

Load fields: fx and fy on `<truss>.<node>`. Claim paths: `<truss>.<qoi>` and
`<truss>.member(<member>).<qoi>`.

Self-weight. The y axis points up and gravity acts in -y. Each member weighs
g rho A L (g the registry's earth.gravity, a range that holds at every site; rho the
material's density), half carried at each end node, and that weight is in every load
case of every statement below. The load factor of a claim multiplies the load case
only: the weight is the weight. Pi in A and the square root in L stay kernel Exprs,
which every rule encloses rigorously, so no rounding of the weight is needed.

Lumped at the nodes, the weight gives each member one force N, the mean along it. Two
bounds cover what lumping leaves out (_Terms.end_excess, _Terms.sag):
    v_i = g rho A |dy| / 2       the force varies by this much either side of N along an
                                 inclined member, so a check reads |N| + v at the worse end
    s_i = A M / W_el             M = g rho A |dx| L / 8, the midspan bending; a tension or
                                 yield check adds it, by the linear interaction of
                                 EN 1993-1-1 6.2.1(7)
How that bending lowers a compression member's buckling resistance is not checked, and
every model's premise says so.

Everything is written in force densities q_i = N_i / L_i, because with rational node
coordinates the equilibrium matrix in force densities is exact:

    sum over members at node n of  q_i (x_other - x_n)  +  f_n  =  0     (free DOFs only)

so B has entries x_j - x_i, y_j - y_i, and lengths enter only through L_i^2 (rational)
and Sqrt(L_i^2) inside capacity Exprs, which the kernel encloses rigorously. Node
coordinates enter those Exprs as design-value hypotheses. Every builder states one
obligation per load case.

Mapping onto kernel goals:
  plastic collapse   R1  LinearFeasible: B q = lambda f(h) + w;  -C_i/L_i <= q_i <= T_i/L_i
                         T_i = A_i fy_i - v_i - s_i ;  C_i = N_b,i - v_i, with N_b,i the
                         flexural buckling resistance below
                         lambda is the claimed factor as a constant, since R1 needs b
                         affine in the hypotheses. The weight w is not: it carries Sqrt and
                         Pi. So w moves into the bounds through an exact rational right
                         inverse R of B (B R = I): q_w = R w carries w alone, and
                         B (q - q_w) = lambda f(h) with each bound moved by q_w. A truss
                         whose B has no right inverse is a mechanism; there w stays in b,
                         which the kernel can refute but never prove. The goal also asks
                         for a field that carries w alone (a second copy of the system with
                         b = 0): a claim lambda covers every factor in [0, lambda], the
                         factors a truss carries form an interval, and with a weight the
                         factor 0 is no longer free. Mechanism FAIL = FarkasRay.
  elastic response   R3  QuadraticProblem(B, f(h), w_i = L_i^3 E_0 / (E_i A_i)): the
                         complementary energy sum q^2 L^3 / (E A) scaled by E_0, the first
                         member's modulus. A positive scale leaves the minimiser unchanged
                         and cancels a modulus every member shares, so the member forces of
                         a one-material truss do not inherit the range of E.
                         R3 needs f affine too, so the weight enters by superposition: one
                         more problem per free y DOF k, a unit downward load there, whose
                         minimiser gives U_ik, the force in member i per newton at k. Then
                           N_i = N_i(load) + (g / 2) sum_k U_ik sum_{j at k} rho_j A_j L_j
                         with N_i(load) and every U_ik DefinedHyps (R3 lemmas in the
                         evidence). Claims on elastic forces are R4 goals over N_i:
                         stress (|N_i| + v_i + s_i) / A_i <= X, compliance
                         sum N_i^2 L_i / (E_i A_i) <= X.
  global stability   R2  GramPositiveDefinite over free DOFs:
                         sum_i (E_i A_i / L_i^3) d_i d_i^T                  (material)
                       + sum_i c_i / L_i H_i H_i^T                          (geometric, H = [I; -I])
                         c_i = min(0, lambda N_i(load)) + min(0, N_i(weight)). Dropping
                         tension stiffening this way covers every factor t in [0, lambda]:
                         t N_i(load) + N_i(weight) >= c_i, and the Loewner sum falls with
                         each coefficient.
  member buckling    R4  AllNonpositive: -N_i + v_i - u N_b,i <= 0, one obligation per
                         member so a FAIL names the member.
                         buckling_utilisation = -N / N_b, negative in tension.

Flexural buckling resistance, EN 1993-1-1:2005 6.3.1.2 with gamma_M1 = 1:
    N_b = chi A fy,  chi = min(1, 1 / (Phi + sqrt(Phi^2 - lambda^2)))
    Phi = (1 + alpha (lambda - 0.2) + lambda^2) / 2,  lambda^2 = A fy / N_cr,  N_cr = pi^2 E I / L^2
with alpha the section's buckling_alpha and buckling length L (pin-ended). The truss is
taken to be braced out of its plane at every node, so L is the buckling length about
every axis; each model that uses N_b states that bracing as a premise.

Validity rows, each stated beside every obligation whose model has it (models/base.py):
  below yield        R4  |N_i| + v_i + s_i <= A_i fy_i: the elastic model holds only below
                         yield.
  small strain       R4  |N_i| + v_i <= 0.002 E_i A_i.
  section class      R4  AllNonpositive: D fy - 90 (235 MPa) t <= 0 per section, EN 1993-1-1
                         Table 5.2 class 3 for tubes, so A fy is reached in compression.
  determinate        R2  GramPositiveDefinite of B^T B beside B B^T: as many free DOFs as
                         members and B invertible, so equilibrium alone fixes every member
                         force. The plastic model's static field is then the truss's own,
                         reached with no redistribution, which a buckled member could not
                         follow. A singular one is refuted by the direction at which its
                         exact LDL^T stops.
The two elastic rows are stated at the load case itself, factor 1, also beside a
stability obligation: its factor scales a reference elastic state.
"""
from __future__ import annotations

import functools
import sys
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from typing import Callable, Mapping

from ..ir import Component, Design, Exceeds, Fixed, Input, Punct, Ref, Rel, Span, Vec
from ..kernel import Add, Const, Div, Expr, Interval, Matrix, Max, Min, Mul, Neg, Pi, PowInt, Sqrt
from ..kernel.rules.r1_linear import LinearFeasible
from ..kernel.rules.r2_definite import GramPositiveDefinite, GramTerm
from ..kernel.rules.r3_hypercircle import MinimizerComponent, QuadraticProblem
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
    Field,
    Gap,
    Grammar,
    ModelSpec,
    NeedsInputBound,
    NoRuleForQuantity,
    Obligation,
    Ports,
    Requirement,
    Statement,
    StatementBuilder,
    ValidityRow,
    model_spec,
    validity_obligation,
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
_SECTION_PROPS = ("D", "t", "A", "I", "buckling_alpha")
_MATERIAL_PROPS = ("fy", "E", "density")
_LOAD_FIELDS = {"fx": "x", "fy": "y"}

GRAVITY = "earth.gravity"
"""The registry constant self-weight is computed with, a range that holds at every site."""

GRAMMAR = Grammar(
    required=(
        Field("node", "<name> at (<x>, <y>) [support pinned|roller_x|roller_y]", "length", (),
              "a joint at exact coordinates, one line per node, y pointing up (the members' own weight "
              "acts in -y); a support fixes x and y (pinned), y only (roller_x) or x only (roller_y)"),
        Field("member", "<name>: <node> -- <node> [section <id>] [material <id>]", "", ("chs.", "steel."),
              "a pin-ended bar between two nodes, one line per member; its options override the defaults"),
    ),
    optional=(
        Field("material", "<registry material id>", "", ("steel.",),
              "the material of every member that names none; it needs fy, E and density and the section's "
              "material family"),
        Field("section", "<registry section id>", "", ("chs.",),
              "the circular hollow section of every member that names none"),
    ),
    target="<truss>.<node>",
    loads=tuple(_LOAD_FIELDS),
)


def lower_truss(component: Component, design: Design, registry: Registry) -> Truss:
    """Parse the attribute lines in the module docstring. Rejects (ComponentError):
    duplicate names, a member naming an unknown node, a zero-length member, a node with
    no member, coordinates that are not exact lengths, registry ids of the wrong kind, a
    section that is not a circular hollow section, a material without fy and E, a load
    field other than fx and fy, a load on an unknown node, a claim qoi not in QOIS or on
    the wrong path, a probability claim or tests record (trusses have neither in v0), and
    a waiver on anything but the truss or one of its members. A material needs fy, E and
    density."""
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
            problem(attr.span, f"unknown truss attribute '{attr.key}'; expected {_listed(GRAMMAR.names, 'or')}")

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
    if not problems:
        for member in members:
            made_of = registry.part(member.section, PartKind.SECTION).material
            if registry.material(made_of).family != registry.material(member.material).family:
                problem(component.span, f"member {member.name}: section {member.section} is made of {made_of}, "
                                        f"so its buckling curve does not hold for {member.material}")
    _check_references(name, nodes, lines, design, problem)
    if problems:
        raise ComponentError(tuple(problems))
    return Truss(name, tuple(nodes.values()), tuple(members), component.span)


def _listed(words: tuple[str, ...], last: str) -> str:
    return f"{', '.join(words[:-1])} {last} {words[-1]}" if len(words) > 1 else words[0]


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
                problem(span, f"load {case.name} on {target} has field {entry.field}; a truss node takes {_listed(GRAMMAR.loads, 'and')}")
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

SMALL_STRAIN_LIMIT = Fraction(1, 500)
"""|strain| <= 0.002: the range inside which the linear elastic model is used."""

BELOW_YIELD = ValidityRow(
    "truss.elastic.below_yield",
    "every member's elastic force stays within its yield load, |N| <= A fy, under each load case",
    "a linear elastic material law holds only below yield (EN 1993-1-1:2005 5.4.2, elastic global analysis)",
)
SMALL_STRAIN = ValidityRow(
    "truss.elastic.small_strain",
    "every member's elastic strain stays within 0.002, |N| / (E A) <= 0.002, under each load case",
    "small-displacement theory of the pin-jointed truss; the 0.002 limit is the maintainers' choice",
)
SECTION_CLASS = ValidityRow(
    "truss.section.class3",
    "every member's circular hollow section is class 3 or better in compression, D / t <= 90 (235 MPa / fy)",
    "EN 1993-1-1:2005 Table 5.2 (sheet 3), tubular sections: class 3 when d / t <= 90 eps^2, eps^2 = 235 / fy",
)
DETERMINATE = ValidityRow(
    "truss.plastic.determinate",
    "the truss is statically determinate: as many free degrees of freedom as members, and equilibrium alone "
    "fixes every member force (B^T B and B B^T positive definite)",
    "the static theorem assumes every member holds its capacity while load redistributes, which a buckled "
    "member does not; with no state of self-stress there is nothing to redistribute, so the static field is "
    "the truss's own force field (Neal, The Plastic Methods of Structural Analysis; docs/design.md, the truss model)",
)

_SELF_WEIGHT = ("the y axis points up and gravity acts in -y; each member's weight loads its two end joints, half at "
                "each; along an inclined member the force is taken at its worse end, and a tension or yield check "
                "adds the bending the weight causes at midspan by the linear interaction of EN 1993-1-1 6.2.1(7); "
                "how that bending lowers a compression member's buckling resistance is not checked")
_BRACING = ("every joint is braced against displacement out of the plane of the truss, so a member's buckling "
            "length about every axis is its length L")

_MAINTAINERS = "petra-maintainers"
_PLASTIC = model_spec(
    sys.modules[__name__], "truss.plastic",
    "rigid-perfectly-plastic pin-jointed 2D truss, static (lower-bound) theorem; tension capacity A fy, "
    "compression capacity the flexural buckling resistance chi A fy",
    f"joints are frictionless pins; members are prismatic, steel, and loaded only at their ends; {_SELF_WEIGHT}; "
    f"{_BRACING}; displacements are small; a member at its compression capacity is taken to hold it, which "
    "asks no redistribution of a statically determinate truss",
    _MAINTAINERS, "lower-bound theorem of plastic collapse (Gvozdev 1938; Neal, The Plastic Methods of Structural Analysis); "
                  "EN 1993-1-1:2005 6.3.1.2 for the compression capacity",
    rows=(SECTION_CLASS, DETERMINATE),
)
_ELASTIC = model_spec(
    sys.modules[__name__], "truss.elastic",
    "linear elastic pin-jointed 2D truss: member forces minimise the complementary energy sum N^2 L / (E A)",
    f"joints are frictionless pins; members are prismatic, linear elastic and loaded only at their ends; {_SELF_WEIGHT}",
    _MAINTAINERS, "principle of minimum complementary energy; Prager and Synge (1947) hypercircle bounds",
    rows=(BELOW_YIELD, SMALL_STRAIN),
)
_STABILITY = model_spec(
    sys.modules[__name__], "truss.stability",
    "linear prebuckling of a pin-jointed 2D truss, Green-strain geometric stiffness of the elastic member forces",
    "member forces come from the linear elastic model at the load case, the load's share scaling with the load "
    f"factor and the weight's not; {_SELF_WEIGHT}; tension stiffening is ignored, which is conservative; the "
    "check is in the plane of the truss, and out of it every joint is held by bracing; buckling of a member "
    "between its joints is checked separately by truss.flexural_buckling",
    _MAINTAINERS, "linearised buckling eigenproblem (K + lambda K_G) of a pin-jointed truss",
    rows=(BELOW_YIELD, SMALL_STRAIN),
)
_BUCKLING = model_spec(
    sys.modules[__name__], "truss.flexural_buckling",
    "flexural buckling of a pin-ended uniform member, EN 1993-1-1 6.3.1.2: compression N <= u chi A fy, "
    "chi from the section's buckling curve, lambda^2 = A fy / N_cr, N_cr = pi^2 E I / L^2",
    "members are straight within the EN 1090-2 tolerances the buckling curves assume, prismatic, pin-ended "
    "and steel, with one second moment about every axis (circular hollow sections), and carry the linear "
    f"elastic member force; {_BRACING}; {_SELF_WEIGHT}; the resistance is characteristic (gamma_M1 = 1)",
    _MAINTAINERS, "EN 1993-1-1:2005 6.3.1.2 and Tables 6.1 and 6.2",
    rows=(BELOW_YIELD, SMALL_STRAIN, SECTION_CLASS),
)

MODELS: Mapping[FailureMode, ModelSpec] = {
    PLASTIC_COLLAPSE: _PLASTIC,
    ELASTIC_STRESS: _ELASTIC,
    COMPLIANCE: _ELASTIC,
    GLOBAL_STABILITY: _STABILITY,
    MEMBER_BUCKLING: _BUCKLING,
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
    diameter: Expr
    thickness: Expr
    alpha: Expr
    density: Expr
    gravity: Expr
    run: Fraction    # |x_end - x_start|
    rise: Fraction   # |y_end - y_start|

    @property
    def mass(self) -> Expr:
        """rho A L, the member's mass; g times it is its weight."""
        return Mul((self.density, self.area, self.length))

    @property
    def end_excess(self) -> Expr | None:
        """g rho A |dy| / 2. The lumped model gives a member one force N, the mean along
        it; the weight's component along an inclined member makes the force vary
        linearly between the ends, by this much either side of N. None when level."""
        return Mul((Const(self.rise / 2), self.gravity, self.density, self.area)) if self.rise else None

    @property
    def sag(self) -> Expr | None:
        """A M / W_el, the axial force the self-weight bending at midspan is worth at the
        extreme fibre: M = g rho A |dx| L / 8 (the weight's transverse component on a
        pin-ended span), W_el = 2 I / D for a tube. With the linear interaction
        N / (A fy) + M / (W_el fy) <= 1 of EN 1993-1-1:2005 6.2.1(7), conservative for every
        class, a section holds N and M when |N| + A M / W_el <= A fy. None when vertical."""
        if not self.run:
            return None
        moment = Mul((Const(self.run / 8), self.gravity, self.density, self.area, self.length))
        return Div(Mul((self.area, moment, self.diameter)), Mul((Const(Fraction(2)), self.second_moment)))

    @property
    def squash(self) -> Expr:
        """A fy."""
        return Mul((self.area, self.yield_strength))

    @property
    def euler(self) -> Expr:
        """N_cr = pi^2 E I / L^2."""
        return Div(Mul((PowInt(Pi(), 2), self.modulus, self.second_moment)), self.length_sq)

    @property
    def buckling_resistance(self) -> Expr:
        """N_b = chi A fy, EN 1993-1-1:2005 6.3.1.2 (6.47, 6.49) with gamma_M1 = 1:
        min(A fy, A fy / (Phi + sqrt(Phi^2 - lambda^2))), with lambda = sqrt(A fy / N_cr) and
        Phi = (1 + eta + lambda^2) / 2, eta = alpha (lambda - 0.2).

        Phi^2 - lambda^2 is written (Phi - lambda)(Phi + lambda), Phi -+ lambda =
        ((lambda -+ 1)^2 + eta) / 2, so that every occurrence of lambda rises with it once
        lambda >= 1 - alpha / 2: the kernel's interval enclosure is then exact over a range of
        E, as R1, which encloses a capacity over the whole box, needs. Both factors are
        positive for alpha < 3.2; Max(0, .) only keeps a wide enclosure from dipping below 0."""
        slender = Sqrt(Div(self.squash, self.euler))
        eta = Mul((self.alpha, Add((slender, Const(Fraction(-1, 5))))))
        half = Const(Fraction(1, 2))
        phi = Mul((half, Add((Const(Fraction(1)), eta, PowInt(slender, 2)))))
        below = Mul((half, Add((PowInt(Add((slender, Const(Fraction(-1)))), 2), eta))))
        above = Mul((half, Add((PowInt(Add((slender, Const(Fraction(1)))), 2), eta))))
        chi_inverse = Add((phi, Sqrt(Max((Const(Fraction(0)), Mul((below, above)))))))
        return Min((self.squash, Div(self.squash, chi_inverse)))


def _terms(truss: Truss, sb: StatementBuilder) -> tuple[_Terms, ...]:
    nodes = {n.name: n for n in truss.nodes}

    def coordinate(node: Node, axis: str) -> Expr:
        value = node.x if axis == "x" else node.y
        return sb.value(Fixed(Quantity(Interval(value, value), LENGTH)), f"{truss.name}.{node.name}.{axis}")

    gravity = sb.constant(GRAVITY)
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
            diameter=sb.registry(m.section, "D"),
            thickness=sb.registry(m.section, "t"),
            alpha=sb.registry(m.section, "buckling_alpha"),
            density=sb.registry(m.material, "density"),
            gravity=gravity,
            run=abs(end.x - start.x),
            rise=abs(end.y - start.y),
        ))
    return tuple(out)


def _plus(a: Expr, b: Expr | None) -> Expr:
    return a if b is None else Add((a, b))


def _less(a: Expr, b: Expr | None) -> Expr:
    return a if b is None else Add((a, Neg(b)))


def _weight_rows(truss: Truss) -> tuple[tuple[int, str, tuple[int, ...]], ...]:
    """(row, node, members meeting there) for each free y DOF, the rows the self-weight
    loads: gravity acts in -y and half of each member's weight goes to each end node, so
    the load at that row is (g / 2) times the mass of the members meeting there,
    downward. A node restrained in y passes its share straight into the support."""
    return tuple(
        (k, node, tuple(j for j, m in enumerate(truss.members) if node in (m.start, m.end)))
        for k, (node, axis) in enumerate(geometry(truss).dofs) if axis == "y"
    )


def _sum(exprs: tuple[Expr, ...]) -> Expr:
    return exprs[0] if len(exprs) == 1 else Add(exprs)


def _node_mass(terms: tuple[_Terms, ...], members: tuple[int, ...]) -> Expr:
    """The mass of the members meeting at a node; half of it, times g, loads the node."""
    return _sum(tuple(terms[j].mass for j in members))


def _weight_load(truss: Truss, sb: StatementBuilder, terms: tuple[_Terms, ...]) -> dict[int, Expr]:
    """Row -> the self-weight at that free y DOF, -(g / 2) times the node's mass."""
    rows = _weight_rows(truss)
    if not rows:
        return {}
    gravity = sb.constant(GRAVITY)
    return {k: Mul((Const(Fraction(-1, 2)), gravity, _node_mass(terms, members))) for k, _, members in rows}


@functools.cache
def _right_inverse(B: Matrix) -> tuple[tuple[Fraction, ...], ...] | None:
    """R, cols x rows, with B R = I exactly: R = B^T (B B^T)^-1, which is B^-1 for a
    square B. None when the rows of B are dependent (a mechanism): then no R exists.
    The product is checked exactly before R is returned."""
    n, m = B.rows, B.cols
    dense = [[Fraction(0)] * m for _ in range(n)]
    for i, j, v in B.entries:
        dense[i][j] = Fraction(v)
    gram = [[sum((dense[a][k] * dense[b][k] for k in range(m)), Fraction(0)) for b in range(n)] for a in range(n)]
    inverse = _inverse(gram)
    if inverse is None:
        return None
    R = tuple(tuple(sum((dense[k][i] * inverse[k][c] for k in range(n)), Fraction(0)) for c in range(n)) for i in range(m))
    for a in range(n):
        for c in range(n):
            if sum((dense[a][i] * R[i][c] for i in range(m)), Fraction(0)) != (1 if a == c else 0):
                raise ArithmeticError("B R != I")
    return R


def _inverse(M: list[list[Fraction]]) -> list[list[Fraction]] | None:
    """The exact inverse of a square matrix by Gauss-Jordan elimination, or None when it is singular."""
    n = len(M)
    work = [row[:] + [Fraction(int(i == j)) for j in range(n)] for i, row in enumerate(M)]
    for c in range(n):
        pivot = next((r for r in range(c, n) if work[r][c] != 0), None)
        if pivot is None:
            return None
        work[c], work[pivot] = work[pivot], work[c]
        p = work[c][c]
        work[c] = [v / p for v in work[c]]
        for r in range(n):
            if r != c and work[r][c] != 0:
                factor = work[r][c]
                work[r] = [a - factor * b for a, b in zip(work[r], work[c])]
    return [row[n:] for row in work]


def _weight_shift(truss: Truss, sb: StatementBuilder, terms: tuple[_Terms, ...]) -> tuple[Expr | None, ...] | None:
    """q_w = R w, force densities that carry the self-weight w alone (B q_w = w exactly),
    one Expr per member, None where it is zero. None for a truss with no right inverse.

    With m_j = rho_j A_j L_j and c_ij the sum of R_ik over the free y rows k at member j's
    ends, q_w,i = -(g / 2) sum_j c_ij m_j: g appears once, so its range encloses tightly."""
    R = _right_inverse(geometry(truss).B)
    if R is None:
        return None
    rows = _weight_rows(truss)
    if not rows:
        return tuple(None for _ in truss.members)
    gravity = sb.constant(GRAVITY)
    at = {j: [k for k, _, members in rows if j in members] for j in range(len(truss.members))}
    out: list[Expr | None] = []
    for i in range(len(truss.members)):
        parts = []
        for j, ks in at.items():
            c = sum((R[i][k] for k in ks), Fraction(0))
            if c:
                parts.append(terms[j].mass if c == 1 else Mul((Const(c), terms[j].mass)))
        out.append(Mul((Const(Fraction(-1, 2)), gravity, _sum(tuple(parts)))) if parts else None)
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


@dataclass(frozen=True)
class _Force:
    """One member's elastic force under a load case and the self-weight, as Exprs over
    DefinedHyps: N = load + weight. `weight` is None when no free y DOF takes weight."""

    load: Expr
    weight: Expr | None

    @property
    def total(self) -> Expr:
        return self.load if self.weight is None else Add((self.load, self.weight))


def _forces(truss: Truss, design: Design, sb: StatementBuilder, case: str, terms: tuple[_Terms, ...], which: tuple[int, ...]) -> dict[int, _Force]:
    """The elastic force in each member index of `which` under load case `case`.

    N_i(load) = L_i q_i* of elastic_problem, a DefinedHyp. The weight part is
    superposed from unit loads: for each free y DOF k, the problem with B and the same
    weights and f = one newton downward at k, whose minimiser gives U_ik (a DefinedHyp,
    newtons per newton). N_i(weight) = (g / 2) sum_k U_ik m_k, m_k the mass of the
    members meeting at node k. Superposition is exact for the linear elastic model."""
    problem = elastic_problem(truss, design, sb, (case,))
    rows = _weight_rows(truss)
    n = len(problem.f)
    units = tuple(
        QuadraticProblem(problem.B, tuple(Const(Fraction(-1 if r == k else 0)) for r in range(n)), problem.w) for k, _, _ in rows
    )
    gravity = sb.constant(GRAVITY) if rows else None
    out = {}
    for i in which:
        member, length = truss.members[i].name, terms[i].length
        load = sb.defined(f"{truss.name}.{member}.N_load", MinimizerComponent(problem, i, length))
        weight = None
        if rows:
            per = tuple(
                Mul((_node_mass(terms, members), sb.defined(f"{truss.name}.{member}.N_per_down.{node}", MinimizerComponent(unit, i, length))))
                for (_, node, members), unit in zip(rows, units)
            )
            weight = Mul((Const(Fraction(1, 2)), gravity, _sum(per)))
        out[i] = _Force(load, weight)
    return out


def _magnitude(force: Expr, excess: Expr | None, limit: Expr) -> tuple[Expr, Expr]:
    """|force| + excess <= limit as two R4 terms, (force + excess) - limit and
    (-force + excess) - limit, each `demand - capacity`."""
    return Add((_plus(force, excess), Neg(limit))), Add((_plus(Neg(force), excess), Neg(limit)))


def _both(a: Expr | None, b: Expr | None) -> Expr | None:
    return a if b is None else b if a is None else Add((a, b))


def _extreme(t: _Terms) -> Expr | None:
    """What the self-weight adds to |N| at the member's worst section: the end excess and
    the midspan sag, summed, which bounds the larger of the two."""
    return _both(t.end_excess, t.sag)


def _below_yield(truss: Truss, design: Design, sb: StatementBuilder, case: str) -> tuple[Statement, str]:
    """|N| + g rho A |dy| / 2 + A M / W_el <= A fy per member (_Terms.end_excess, .sag)."""
    terms = _terms(truss, sb)
    forces = _forces(truss, design, sb, case, terms, tuple(range(len(terms))))
    exprs = tuple(e for i, t in enumerate(terms) for e in _magnitude(forces[i].total, _extreme(t), t.squash))
    return sb.finish(AllNonpositive(exprs)), f"every member of {truss.name} stays below yield under load case {case} and the self-weight"


def _small_strain(truss: Truss, design: Design, sb: StatementBuilder, case: str) -> tuple[Statement, str]:
    terms = _terms(truss, sb)
    forces = _forces(truss, design, sb, case, terms, tuple(range(len(terms))))
    eps = SMALL_STRAIN_LIMIT
    exprs = tuple(e for i, t in enumerate(terms) for e in _magnitude(forces[i].total, t.end_excess, Mul((Const(eps), t.modulus, t.area))))
    return (sb.finish(AllNonpositive(exprs)),
            f"every member strain of {truss.name} stays within {_text(eps)} under load case {case} and the self-weight")


def _determinate(truss: Truss, design: Design, sb: StatementBuilder, case: str) -> tuple[Statement, str]:
    """B^T B (members) beside B B^T (free DOFs) in one Gram matrix of size m + n: positive
    definite exactly when B is square and invertible. B^T B is the sum over rows r of
    b_r b_r^T, B B^T the sum over columns c of b_c b_c^T, every weight 1. No hypothesis
    enters, and no load, so every load case states the same statement."""
    B = geometry(truss).B
    m, n = B.cols, B.rows
    rows: dict[int, list[tuple[int, int, Fraction]]] = {}
    cols: dict[int, list[tuple[int, int, Fraction]]] = {}
    for i, j, v in B.entries:
        rows.setdefault(i, []).append((j, 0, v))
        cols.setdefault(j, []).append((m + i, 0, v))
    terms = tuple(GramTerm(Const(Fraction(1)), Matrix(m + n, 1, tuple(sorted(e)))) for e in (*rows.values(), *cols.values()))
    return (sb.finish(GramPositiveDefinite(m + n, terms)),
            f"{truss.name} is statically determinate: {n} free degrees of freedom, {m} members, and B invertible")


def _section_class(truss: Truss, design: Design, sb: StatementBuilder, case: str) -> tuple[Statement, str]:
    """One expression per distinct (section, material), in member order: D fy <= 90 (235 MPa) t.
    No load enters, so every load case states the same statement."""
    terms = _terms(truss, sb)
    limit = Mul((sb.constant("en1993_1_1.class3_tube_limit"), sb.constant("en1993_1_1.epsilon_reference_fy")))
    seen, exprs = set(), []
    for m, t in zip(truss.members, terms):
        if (m.section, m.material) not in seen:
            seen.add((m.section, m.material))
            exprs.append(Add((Mul((t.diameter, t.yield_strength)), Neg(Mul((limit, t.thickness))))))
    return sb.finish(AllNonpositive(tuple(exprs))), f"every section of {truss.name} is class 3 or better in compression"


_ROWS: Mapping[str, Callable[[Truss, Design, StatementBuilder, str], tuple[Statement, str]]] = {
    BELOW_YIELD.id: _below_yield,
    SMALL_STRAIN.id: _small_strain,
    SECTION_CLASS.id: _section_class,
    DETERMINATE.id: _determinate,
}


def _obligation(req: Requirement, model: ModelSpec, statement: Statement, describe: str, truss: Truss, design: Design, registry: Registry, case: str) -> Obligation:
    """The obligation with one validity obligation per row of `model`, over load case `case`."""
    validity = []
    for row in model.rows:
        row_statement, row_describe = _ROWS[row.id](truss, design, StatementBuilder(design, registry), case)
        validity.append(validity_obligation(req, model, row, row_statement, row_describe))
    return Obligation(req, statement, model, describe, tuple(validity))


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


def _stacked(B: Matrix) -> Matrix:
    """diag(B, B): two copies of the equilibrium system side by side."""
    return Matrix(2 * B.rows, 2 * B.cols, (*B.entries, *((i + B.rows, j + B.cols, v) for i, j, v in B.entries)))


def build_plastic_collapse(req: Requirement, truss: Truss, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """One R1 statement per load case at the claimed factor, with the self-weight. A
    collapse factor is >= 0 by definition, so a bound below 0 is stated at 0.

    The goal is two copies of the system, diag(B, B) (q, q0) = (factor f + w, w), each
    copy within the capacities: the first carries the claimed factor of the load case on
    top of the weight, the second the weight alone. The factors a truss carries form an
    interval, so the two ends prove every factor between. The weight moves into the
    bounds through the right inverse (module docstring), or stays in b for a mechanism."""
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
        b = load_vector(truss, design, sb, (case,), factor)
        alone = tuple(Const(Fraction(0)) for _ in b)
        lower = tuple(Div(_plus(Neg(t.buckling_resistance), t.end_excess), t.length) if t.end_excess is not None
                      else Neg(Div(t.buckling_resistance, t.length)) for t in terms)
        upper = tuple(Div(_less(t.squash, _extreme(t)), t.length) if _extreme(t) is not None
                      else Div(t.squash, t.length) for t in terms)
        shift = _weight_shift(truss, sb, terms)
        if shift is None:
            weight = _weight_load(truss, sb, terms)
            b = tuple(Add((v, weight[k])) if k in weight else v for k, v in enumerate(b))
            alone = tuple(weight.get(k, v) for k, v in enumerate(alone))
        else:
            lower = tuple(lo if s is None else Add((lo, Neg(s))) for lo, s in zip(lower, shift))
            upper = tuple(hi if s is None else Add((hi, Neg(s))) for hi, s in zip(upper, shift))
        goal = LinearFeasible(A=_stacked(B), b=b + alone, lower=lower + lower, upper=upper + upper)
        describe = (f"a static field within every member's capacity carries the self-weight of {truss.name}, alone and "
                    f"with {_text(factor)} times load case {case}")
        out.append(_obligation(req, MODELS[PLASTIC_COLLAPSE], sb.finish(goal), describe, truss, design, registry, case))
    return tuple(out)


def build_elastic(req: Requirement, truss: Truss, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """Stress and compliance requirements become R4 goals over the elastic member forces
    with the self-weight (_forces). Stress is bounded in magnitude, |N| / A <= X;
    compliance is sum N^2 L / (E A) <= X, the work the loads and the weight do. The
    elastic model's validity rows ride beside each obligation."""
    limit = _limit(req, Rel.LE)
    if limit is None:
        return _no_rule(req, f"v0 bounds {req.mode.id} from above only")
    cases = _cases(req, truss, design)
    if not cases:
        return _unloaded(req, truss)
    index = [m.name for m in truss.members].index(req.subject[1]) if req.mode == ELASTIC_STRESS else None
    out = []
    for case in cases:
        sb = StatementBuilder(design, registry)
        terms = _terms(truss, sb)
        if req.mode == ELASTIC_STRESS:
            force = _forces(truss, design, sb, case, terms, (index,))[index].total
            t = terms[index]
            excess = _extreme(t)
            exprs = _magnitude(Div(force, t.area), None if excess is None else Div(excess, t.area), Const(limit))
            what = f"the stress magnitude in {truss.name}.{req.subject[1]} stays within {_text(limit, 'MPa')}"
        else:
            forces = _forces(truss, design, sb, case, terms, tuple(range(len(terms))))
            work = _sum(tuple(Div(Mul((PowInt(forces[i].total, 2), t.length)), Mul((t.modulus, t.area))) for i, t in enumerate(terms)))
            exprs = (Add((work, Neg(Const(limit)))),)
            what = f"the compliance of {truss.name} stays within {_text(limit, 'J')}"
        describe = f"{what} under load case {case} and the self-weight"
        out.append(_obligation(req, MODELS[req.mode], sb.finish(AllNonpositive(exprs)), describe, truss, design, registry, case))
    return tuple(out)


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
    zero = Const(Fraction(0))
    out = []
    for case in cases:
        sb = StatementBuilder(design, registry)
        terms = _terms(truss, sb)
        forces = _forces(truss, design, sb, case, terms, tuple(range(len(terms))))
        material = tuple(
            GramTerm(Div(Mul((t.modulus, t.area)), PowInt(t.length, 3)), d) for t, d in zip(terms, geom.material_dir)
        )

        def coefficient(i: int, t: _Terms) -> Expr:
            """(min(0, factor N(load)) + min(0, N(weight))) / L."""
            loaded = Min((zero, Mul((Const(factor), forces[i].load))))
            weight = forces[i].weight
            return Div(loaded if weight is None else Add((loaded, Min((zero, weight)))), t.length)

        geometric = tuple(GramTerm(coefficient(i, t), h) for i, (t, h) in enumerate(zip(terms, geom.geometric_dir)))
        goal = GramPositiveDefinite(len(geom.dofs), material + geometric)
        describe = (f"{truss.name} stays stable in linear prebuckling under its self-weight and every load factor up to "
                    f"{_text(factor)} times load case {case}")
        out.append(_obligation(req, MODELS[GLOBAL_STABILITY], sb.finish(goal), describe, truss, design, registry, case))
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
        force = _forces(truss, design, sb, case, terms, (index,))[index].total
        t = terms[index]
        goal = AllNonpositive((Add((_plus(Neg(force), t.end_excess), Neg(Mul((Const(limit), t.buckling_resistance))))),))
        describe = (f"the compression in {truss.name}.{req.subject[1]} is at most {_text(limit)} times its flexural "
                    f"buckling resistance under load case {case} and the self-weight")
        out.append(_obligation(req, MODELS[MEMBER_BUCKLING], sb.finish(goal), describe, truss, design, registry, case))
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
}


def _default_criterion(mode: FailureMode, feature: Feature) -> Criterion | None:
    """Collapse and stability factor >= 1, buckling utilisation <= 1."""
    found = _DEFAULTS.get(mode)
    if found is None:
        return None
    rel, bound = found
    return Criterion(rel, Quantity(Interval(bound, bound), DIMENSIONLESS))


COVERAGE: tuple[CoverageRule, ...] = (
    CoverageRule(
        id="truss.frame",
        when=_is_frame,
        demands=(PLASTIC_COLLAPSE, GLOBAL_STABILITY),
        default=_default_criterion,
        note="every truss can collapse or destabilise",
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
    grammars={"truss": GRAMMAR},
)
