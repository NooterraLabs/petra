"""Domain: bolted joints. Trusted physics; footprint premises "model:bolt.*@<hash>".

Component kind `joint`. Its attribute lines, one per line inside the block, are GRAMMAR
below (`petra kinds joint` prints them).

Load field: force on `<joint>`. Claim path: `<joint>.<qoi>`.

The joint diagram, simplified from VDI 2230 Part 1 for a concentric axial load, per bolt:
    F_V  = T / (K d)                   torque-tension preload
    F_KR = F_V - (1 - Phi) * F_A / n   residual clamp force, the plates' share taken off it
    F_bolt = F_V + Phi * F_A / n       while F_KR >= 0: the plates stay clamped
    F_bolt = F_A / n                   once F_KR < 0: the plates part, and statics leaves
                                       each bolt its whole share
T is the signed tightening torque range, K the nut factor (measured or judged input),
Phi the joint load factor (judged input), F_A the signed external load, n the bolt count.
The two branches meet where F_KR = 0, and on each side the one that applies is the
larger, so, exactly, clamped or open,
    F_bolt = max(F_V + Phi * F_A / n, F_A / n).

Bolt tension (TENSION), every claim on the bolt and the proof-load coverage demand (R4):
    goal  F_bolt - u * S * As <= 0     (u = claimed utilisation, default 1)
As comes from the registry derivation over ISO 724 geometry. S is the property class's
proof stress Sp (ISO 898-1), or its 0.2 % proof strength Rp02_min where the class states
no Sp (ISO 3506-1 stainless), a sanctioned premise either way. A bolt_tension claim
bounds F_bolt itself. The bound holds on both sides of opening, so a proof and a
counterexample each say what the bolt carries, and the model has no validity row.

Joint separation (SEPARATION), demanded of every joint (R4):
    goal  (1 - Phi) * F_A / n - F_V <= 0     the residual clamp force stays at least zero
VDI 2230 Part 1 never designs an opened joint: it splits the load by Phi (R3) only while
the joint is clamped, and sizes the least assembly preload (R5) so that the residual
clamp load stays at least the required clamp load (R2). The grammar draws no transverse
load, seal or eccentric load, so the required clamp load here is zero. The goal is worst
at the least preload T_lo / (K_hi d), the least load share and the largest force, so a
joint that can open anywhere in its box fails here, however strong its bolt.

A coated bolt or plate touches its neighbours with the coating's surface material
(Registry.surface), so the contact pairs the galvanic rule reads name that material.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Mapping

from ..ir import Arg, Bound, Component, Design, Exceeds, Fixed, Input, ParamRef, Ref, Rel, Span, Value
from ..kernel import Add, Const, Div, Expr, Interval, Max, Mul, Neg
from ..kernel.rules.r4_enclosure import AllNonpositive
from ..registry import OutsideMakeableSet, PartKind, ProcessKind, Registry
from ..units import DIMENSIONLESS, FORCE, LENGTH, TORQUE, Dim, Quantity
from .base import (
    CONTACT_PAIR,
    NO_PORTS,
    GIVEN_BOUND,
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
    GapNeed,
    Grammar,
    ModelSpec,
    NeedsInputBound,
    NoRuleForQuantity,
    Obligation,
    Ports,
    Requirement,
    StatementBuilder,
    model_spec,
)

# --- Typed model, produced by lower_joint --------------------------------------------


@dataclass(frozen=True, slots=True)
class Plate:
    material: str
    thickness: Value
    process: str | None = None   # e.g. "process.mig_weld_6xxx" or "process.zinc_plate"


@dataclass(frozen=True, slots=True)
class BoltedJoint:
    name: str
    bolt: str            # registry part id, kind BOLT (thread + property class + coating)
    count: int
    plates: tuple[Plate, ...]
    torque: Input | None
    nut_factor: Input | None
    load_share: Input | None   # joint load factor Phi (VDI 2230 notation)
    span: Span


INPUTS: Mapping[str, tuple[Dim, str]] = {
    "torque": (TORQUE, "Nm"),
    "nut_factor": (DIMENSIONLESS, "1"),
    "load_share": (DIMENSIONLESS, "1"),
}
"""The signed inputs a joint takes: field -> (dimension, unit a gap asks for)."""

GRAMMAR = Grammar(
    required=(
        Field("bolt", "<registry bolt id> count <n>", "count", ("bolt.",),
              "the bolts, exactly one line: a metric bolt (thread, property class, coating) and how many share the load"),
        Field("plate", "<registry material id> thickness <length> [process <registry process id>]", "length",
              ("aluminium.", "steel.", "stainless.", "process."),
              "a clamped plate, one line per plate, at least two; a coating, weld or cut process changes its surface "
              "or its strength"),
    ),
    optional=(
        Field("torque", GIVEN_BOUND, "torque", (),
              "the tightening torque; without it the tension check is UNKNOWN"),
        Field("nut_factor", GIVEN_BOUND, "dimensionless", (),
              "the nut factor K of the torque-tension relation, positive; without it the tension check is UNKNOWN"),
        Field("load_share", GIVEN_BOUND, "dimensionless", (),
              "the joint load factor Phi, the share of the external force the bolts take, within [0, 1]; without "
              "it the tension check is UNKNOWN"),
    ),
    target="<joint>",
    loads=("force",),
)

_PLATE_PROCESSES = frozenset({ProcessKind.COATING, ProcessKind.WELD, ProcessKind.CUT})


def lower_joint(component: Component, design: Design, registry: Registry) -> BoltedJoint:
    """Parse the attribute lines in the module docstring. Names the bounds
    "<joint>.torque", "<joint>.nut_factor" and "<joint>.load_share". Rejects
    (ComponentError): a missing or repeated bolt line, fewer than two plates, registry ids
    of the wrong kind, a plate process that is not a coating, weld or cut, a load field
    other than force, and a claim qoi not in QOIS."""
    problems: list[str] = []
    name = component.name
    bolts: list[tuple[str, int]] = []
    plates: list[Plate] = []
    inputs: dict[str, Input] = {}
    for attr in component.attrs:
        say = _reporter(problems, attr.span, f"{name}.{attr.key}")
        if attr.key == "bolt":
            found = _bolt(attr.args, registry, say)
            if found is not None:
                bolts.append(found)
        elif attr.key == "plate":
            plate = _plate(attr.args, design, registry, say)
            if plate is not None:
                plates.append(plate)
        elif attr.key in INPUTS:
            if attr.key in inputs:
                say("is given twice")
            value = _input(f"{name}.{attr.key}", attr.key, attr.args, say)
            if value is not None:
                inputs[attr.key] = value
        else:
            say(f"unknown attribute; a joint takes {', '.join(sorted(GRAMMAR.names))}")
    here = _reporter(problems, component.span, name)
    if len(bolts) != 1:
        here(f"a joint has exactly one bolt line, not {len(bolts)}")
    if len(plates) < 2:
        here(f"a joint clamps at least two plates, not {len(plates)}")
    _check_references(name, design, problems)
    if problems:
        raise ComponentError(tuple(problems))
    (bolt, count), = bolts
    return BoltedJoint(name, bolt, count, tuple(plates), inputs.get("torque"), inputs.get("nut_factor"),
                       inputs.get("load_share"), component.span)


Say = Callable[[str], None]


def _reporter(problems: list[str], span: Span, what: str) -> Say:
    return lambda message: problems.append(f"{span.path}:{span.line}:{span.col}: {what}: {message}")


def _registry_id(arg: Arg | None) -> str | None:
    return ".".join(arg.parts) if isinstance(arg, Ref) else None


def _keyword(arg: Arg | None, word: str) -> bool:
    return arg == Ref((word,))


def _bolt(args: tuple[Arg, ...], registry: Registry, say: Say) -> tuple[str, int] | None:
    count = args[2] if len(args) == 3 and _keyword(args[1], "count") else None
    pid = _registry_id(args[0]) if args else None
    if pid is None or not isinstance(count, Fixed):
        say("reads `bolt <registry bolt id> count <n>`")
        return None
    n = count.quantity.value
    if count.quantity.dim != DIMENSIONLESS or n.lo != n.hi or n.lo.denominator != 1 or n.lo < 1:
        say("count is a whole number of bolts, at least 1")
        return None
    try:
        registry.part(pid, PartKind.BOLT)
    except OutsideMakeableSet as e:
        say(str(e))
        return None
    return pid, int(n.lo)


def _plate(args: tuple[Arg, ...], design: Design, registry: Registry, say: Say) -> Plate | None:
    shape = len(args) in (3, 5) and _keyword(args[1], "thickness") and (len(args) == 3 or _keyword(args[3], "process"))
    if not shape:
        say("reads `plate <registry material id> thickness <value> [process <registry process id>]`")
        return None
    material, thickness = _registry_id(args[0]), args[2]
    process = _registry_id(args[4]) if len(args) == 5 else None
    ok = True
    try:
        registry.material(material or "")
    except OutsideMakeableSet as e:
        say(str(e))
        ok = False
    if not _is_length(thickness, design):
        say("thickness needs a positive length or a param")
        ok = False
    if len(args) == 5:
        found = registry.processes.get(process or "")
        if found is None:
            say(registry.unknown(str(process), "process", registry.processes))
            ok = False
        elif found.kind not in _PLATE_PROCESSES:
            kinds = sorted(k.value for k in _PLATE_PROCESSES)
            say(f"a plate takes a {', '.join(kinds[:-1])} or {kinds[-1]} process; {process} is {found.kind.value}")
            ok = False
    return Plate(material, thickness, process) if ok else None


def _is_length(arg: Arg, design: Design) -> bool:
    if isinstance(arg, Fixed):
        return arg.quantity.dim == LENGTH and arg.quantity.value.lo > 0
    return isinstance(arg, ParamRef) and arg.name in design.params and design.params[arg.name].range.dim == LENGTH


def _input(name: str, field: str, args: tuple[Arg, ...], say: Say) -> Input | None:
    dim, _ = INPUTS[field]
    bound = args[0] if len(args) == 1 else None
    if not (isinstance(bound, Bound) and bound.range.dim == dim):
        say(f"needs one signed {'torque' if dim == TORQUE else 'dimensionless'} bound")
        return None
    lo, hi = bound.range.value.lo, bound.range.value.hi
    if field == "torque" and lo < 0:
        say("a tightening torque is not negative")
        return None
    if field == "nut_factor" and lo <= 0:
        say("a nut factor is positive")
        return None
    if field == "load_share" and not (0 <= lo and hi <= 1):
        say("a load share is a fraction of the external force, within [0, 1]")
        return None
    return Input(name, bound.range, bound.signature, bound.kind, bound.span, bound.mean)


def _check_references(joint: str, design: Design, problems: list[str]) -> None:
    for case in design.loads.values():
        say = _reporter(problems, case.span, f"load {case.name}")
        entries = [e for e in case.entries if e.target[0] == joint]
        if len(entries) > 1:
            say(f"{joint}: one force per load case")
        for entry in entries:
            if len(entry.target) != 1:
                say(f"{'.'.join(entry.target)}: a joint load acts on the joint itself, as in `on {joint} force ...`")
            elif entry.field not in GRAMMAR.loads:
                say(f"{joint}: a joint's load field is {', '.join(GRAMMAR.loads)}, not {entry.field}")
            elif _dim(entry.value, design) != FORCE:
                say(f"{joint}: force needs a force range")
    for claim in design.claims:
        if claim.qoi.path[0] != joint:
            continue
        say = _reporter(problems, claim.span, f"claim {claim.name}")
        if len(claim.qoi.path) != 1:
            say(f"a joint claim names the joint, as in {joint}.tension_utilisation")
        elif claim.qoi.name not in QOIS:
            say(f"unknown joint quantity '{claim.qoi.name}'; known: {', '.join(sorted(QOIS))}")
        elif claim.bound.dim != CRITERION_DIMS[claim.qoi.name]:
            say(f"{claim.qoi.name} is bounded by a {'force' if claim.qoi.name == 'bolt_tension' else 'fraction'}")
    for claim in design.probability_claims:
        path = claim.event.qoi.path if isinstance(claim.event, Exceeds) else claim.event.subject
        if path[0] == joint:
            _reporter(problems, claim.span, f"claim {claim.name}")("v0 states no probability claim on a joint")
    for tests in design.tests.values():
        if tests.subject[0] == joint:
            _reporter(problems, tests.span, f"tests {tests.name}")("v0 reads no tests records on a joint")
    for waiver in design.waivers:
        if waiver.subject[0] == joint and len(waiver.subject) != 1:
            _reporter(problems, waiver.span, "waiver")(f"a joint's requirements are on {joint} itself")


def _dim(value: Input | ParamRef, design: Design) -> Dim:
    return value.range.dim if isinstance(value, Input) else design.params[value.name].range.dim


# --- Modes, quantities, model premises -----------------------------------------------

TENSION = FailureMode("bolt.tension")
SEPARATION = FailureMode("bolt.separation")
PLATE_BEARING = FailureMode("bolt.plate_bearing")

_JOINT_DIAGRAM = ("concentric axial external load shared equally by the bolts; linear joint diagram with joint load "
                  "factor Phi; no prying, bending, embedding loss or thermal change of preload; the nut factor covers "
                  "thread and bearing friction")

_TIGHTENING = ("the bolt stays elastic while it is tightened, though the thread torque adds torsion to the preload's "
               "axial stress (VDI 2230 Part 1:2015 R7); no input gives the thread friction, and F_V = T / (K d) holds "
               "only below yield")

TENSION_MODEL = model_spec(
    sys.modules[__name__], "bolt.tension",
    "the joint diagram's bolt force max(F_V + Phi F_A / n, F_A / n), F_V = T / (K d): the load share Phi while the "
    "plates stay clamped, the whole share once they part, against the property class's proof stress (or 0.2 % proof "
    "strength) times the ISO 724 stress area",
    _JOINT_DIAGRAM,
    "petra-maintainers", "VDI 2230 Part 1:2015 (simplified joint diagram); ISO 898-1:2013; ISO 3506-1:2020; ISO 724",
    unchecked=(_TIGHTENING,),
)

SEPARATION_MODEL = model_spec(
    sys.modules[__name__], "bolt.separation",
    "the joint diagram's residual clamp force F_V - (1 - Phi) F_A / n, F_V = T / (K d), against the required "
    "clamp load",
    f"{_JOINT_DIAGRAM}; no transverse load, seal or eccentric load, so the required clamp load is zero",
    "petra-maintainers",
    "VDI 2230 Part 1:2015 (simplified): the operating load splits by Phi only while the joint is clamped (R3), and "
    "the minimum assembly preload keeps the residual clamp load at least the required clamp load (R2, R5)",
    unchecked=(_TIGHTENING,),
)

MODELS: Mapping[FailureMode, ModelSpec] = {TENSION: TENSION_MODEL, SEPARATION: SEPARATION_MODEL}

QOIS: Mapping[str, FailureMode] = {
    "bolt_tension": TENSION,
    "tension_utilisation": TENSION,
}

CRITERION_DIMS: Mapping[str, Dim] = {"bolt_tension": FORCE, "tension_utilisation": DIMENSIONLESS}

# --- Elaboration -------------------------------------------------------------------------


def preload(sb: StatementBuilder, joint: BoltedJoint) -> Expr:
    """F_V = T / (K d), the torque-tension relation."""
    return Div(sb.input(joint.torque), Mul((sb.input(joint.nut_factor), sb.registry(joint.bolt, "d"))))


def per_bolt(sb: StatementBuilder, joint: BoltedJoint, external: Expr) -> Expr:
    """external / n: one bolt's share of the external force."""
    count = sb.value(Fixed(Quantity(Interval(Fraction(joint.count), Fraction(joint.count)), DIMENSIONLESS)), f"{joint.name}.count")
    return Div(external, count)


def bolt_force(sb: StatementBuilder, joint: BoltedJoint, external: Expr) -> Expr:
    """max(F_V + Phi * external / n, external / n): the bolt force of the joint diagram,
    the load share while the plates stay clamped and the whole share once they part."""
    share = per_bolt(sb, joint, external)
    return Max((Add((preload(sb, joint), Mul((sb.input(joint.load_share), share)))), share))


def clamp_lost(sb: StatementBuilder, joint: BoltedJoint, external: Expr) -> Expr:
    """(1 - Phi) * external / n - F_V: the plates' share of the external force less the
    preload, the residual clamp force negated, at most 0 while the joint stays clamped."""
    relief = Add((Const(Fraction(1)), Neg(sb.input(joint.load_share))))
    return Add((Mul((relief, per_bolt(sb, joint, external))), Neg(preload(sb, joint))))


def _external(sb: StatementBuilder, force: Input | ParamRef | Fixed, case: str) -> Expr:
    return sb.input(force) if isinstance(force, Input) else sb.value(force, case)


def capacity(sb: StatementBuilder, joint: BoltedJoint, registry: Registry) -> Expr:
    """The class's proof stress (Sp, else Rp02_min) times the stress area As."""
    part = registry.part(joint.bolt, PartKind.BOLT)
    stress = sb.registry(joint.bolt, "Sp" if "Sp" in part.props else "Rp02_min")
    return Mul((stress, sb.registry(joint.bolt, "As")))


def _loading(req: Requirement, joint: BoltedJoint, design: Design) -> tuple[list[GapNeed], dict[str, Input | ParamRef], tuple[str, ...]]:
    """(NeedsInputBound for each of torque, nut_factor, load_share the joint lacks and for
    a force when a case req is checked under puts none on it, each load case's force on
    the joint, the cases req is checked under)."""
    needs: list[GapNeed] = [NeedsInputBound((joint.name,), field, unit)
                            for field, (_, unit) in INPUTS.items() if getattr(joint, field) is None]
    forces = {case.name: e.value for case in design.loads.values() for e in case.entries if e.target == (joint.name,)}
    cases = req.under or tuple(forces)
    if not cases or any(case not in forces for case in cases):
        needs.append(NeedsInputBound((joint.name,), "force", "N"))
    return needs, forces, cases


def build_tension(req: Requirement, joint: BoltedJoint, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """One obligation per load case, F_bolt - limit <= 0, or a Gap naming what `_loading`
    finds missing and a GE claim (NoRuleForQuantity)."""
    criterion = req.criterion
    qoi = req.qoi.name if req.qoi is not None else "tension_utilisation"
    needs: list[GapNeed] = []
    if isinstance(criterion, Criterion) and criterion.rel is Rel.GE:
        needs.append(NoRuleForQuantity(qoi, "a bolt's tension is bounded from above only"))
    missing, forces, cases = _loading(req, joint, design)
    needs += missing
    if needs:
        return (Gap(req, tuple(needs)),)
    bound = criterion.bound.value.lo if isinstance(criterion, Criterion) else Fraction(1)
    out = []
    for case in cases:
        sb = StatementBuilder(design, registry)
        tension = bolt_force(sb, joint, _external(sb, forces[case], case))
        if qoi == "bolt_tension":
            limit, what = Const(bound), f"{float(bound) / 1000:g} kN"
        else:
            limit = capacity(sb, joint, registry)
            limit, what = (limit if bound == 1 else Mul((Const(bound), limit))), f"{float(bound):g} of its proof capacity"
        out.append(Obligation(req, sb.finish(AllNonpositive((Add((tension, Neg(limit))),))), TENSION_MODEL,
                              f"the bolt in {joint.name} stays at or below {what} under {case}, clamped or open"))
    return tuple(out)


def build_separation(req: Requirement, joint: BoltedJoint, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """One obligation per load case, (1 - Phi) F_A / n - F_V <= 0, or a Gap naming what
    `_loading` finds missing."""
    needs, forces, cases = _loading(req, joint, design)
    if needs:
        return (Gap(req, tuple(needs)),)
    out = []
    for case in cases:
        sb = StatementBuilder(design, registry)
        lost = clamp_lost(sb, joint, _external(sb, forces[case], case))
        out.append(Obligation(req, sb.finish(AllNonpositive((lost,))), SEPARATION_MODEL,
                              f"the plates of {joint.name} stay clamped under {case}, even at the least preload"))
    return tuple(out)


# --- Coverage ------------------------------------------------------------------------

BOLTED_JOINT = FeatureKind("bolt.joint")


def features(joint: BoltedJoint, design: Design, registry: Registry) -> tuple[Feature, ...]:
    """One BOLTED_JOINT feature naming the base materials, and one CONTACT_PAIR per pair
    of surfaces in contact (bolt against each plate, plate against plate), plus the
    environment. A pair names each part's exposed surface (Registry.surface), the
    coating's material on a coated part, since that is what the galvanic rule in
    petra/coverage.py must read. Every feature's subject is the joint, so a joint has one
    galvanic requirement however many of its pairs are dissimilar."""
    bolt = registry.parts[joint.bolt]
    plates = [p.material for p in joint.plates]
    shown = registry.surface(bolt.material, bolt.process)
    surfaces = [registry.surface(p.material, p.process) for p in joint.plates]
    subject = (joint.name,)
    contact = frozenset({EnergyDomain.MECHANICAL, EnergyDomain.CHEMICAL})
    pairs = [(shown, s) for s in surfaces] + list(zip(surfaces, surfaces[1:]))
    return (
        Feature(subject, BOLTED_JOINT, tuple(dict.fromkeys((bolt.material, *plates))), frozenset({EnergyDomain.MECHANICAL}), design.environment),
        *(Feature(subject, CONTACT_PAIR, pair, contact, design.environment) for pair in dict.fromkeys(pairs)),
    )


def _is_joint(feature: Feature, registry: Registry) -> bool:
    return feature.kind == BOLTED_JOINT


def _default_criterion(mode: FailureMode, feature: Feature) -> Criterion | None:
    """Tension utilisation <= 1 (proof load). None for SEPARATION, whose required clamp
    load is fixed by the model, and for PLATE_BEARING, which is unmodelled."""
    if mode == TENSION:
        return Criterion(Rel.LE, Quantity(Interval(Fraction(1), Fraction(1)), DIMENSIONLESS))
    return None


COVERAGE: tuple[CoverageRule, ...] = (
    CoverageRule(
        id="bolt.tension",
        when=_is_joint,
        demands=(TENSION,),
        default=_default_criterion,
        note="every bolt stays below its proof load",
    ),
    CoverageRule(
        id="bolt.separation",
        when=_is_joint,
        demands=(SEPARATION,),
        default=_default_criterion,
        note="every joint stays clamped under its load, even at the least preload",
    ),
    CoverageRule(
        id="bolt.bearing",
        when=_is_joint,
        demands=(PLATE_BEARING,),
        default=_default_criterion,
        note="every plate carries the bolt's bearing load",
    ),
)


def ports(joint: BoltedJoint, registry: Registry) -> Ports:
    return NO_PORTS


DOMAIN = DomainSpec(
    name="bolt",
    kinds={"joint": lower_joint},
    builders={TENSION: build_tension, SEPARATION: build_separation},
    unmodelled=frozenset({PLATE_BEARING}),
    qois=QOIS,
    probability={},
    coverage=COVERAGE,
    models=MODELS,
    features=features,
    ports=ports,
    grammars={"joint": GRAMMAR},
)
