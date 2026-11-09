"""Turns the engine's measures into obligations the kernel checks. Trusted.

One builder per rule. Each states an R4 goal over three kinds of premise: the exact
geometry the engine measured, as design values labelled dsg:<design>.<name>; the
registry rows and constants it compares them with, labelled reg:; and the design's signed
bounds (tolerance, hole shrink, heat), labelled in:. The kernel then checks
the goal at every point of the box, so a check passes only at the worst-case extreme of
every tolerance, and a refutation names that extreme.

Squares keep every goal rational: a distance d against an allowance a is stated as
a^2 - d^2 <= 0 with d^2 an exact sum of squares. Lengths are in metres, as the registry's.
"""
from __future__ import annotations

import sys
from fractions import Fraction
from typing import Callable, Mapping

from ...ir import Design, Fixed, Input, ParamRef, Rel
from ...kernel import Add, Const, Expr, Interval, Max, Mul, Neg, PowInt
from ...kernel.rules.r4_enclosure import AllNonpositive
from ...registry import Registry
from ...units import AREA, DIMENSIONLESS, LENGTH, MASS, Dim, Quantity
from ..base import (Criterion, Elaborated, FailureMode, Gap, ModelSpec, NeedsInputBound, NoRuleForQuantity, Obligation,
                    Requirement, StatementBuilder, model_spec)
from . import engine
from .lower import Assembly, Hole, PartDesign
from .rules import RULE_BY_ID, Evaluator

Q = Fraction
M = Q(1, 1000)                    # mm to m
VOLUME = Dim(m=3)

_FIT = ("each part is rigid and its true surface lies within its allowance of the mesh, both ways; a part's place "
        "is exact across its insert axis and floats along it by what it rests on; screws are the circumscribed "
        "polygonal prisms of their shank and socket head")
MODELS: Mapping[Evaluator, ModelSpec] = {
    Evaluator.GEOMETRY: model_spec(sys.modules[__name__], "parts.geometry",
                                   "exact rational geometry of the placed meshes: swept triangle distances, ray parity, "
                                   "and slab distances from a declared hole's axis", _FIT, "petra-maintainers",
                                   "docs/parts.md, Fit under tolerance"),
    Evaluator.DECLARED: model_spec(sys.modules[__name__], "parts.declared",
                                   "arithmetic on declared hole, screw, insert and press diameters and lengths",
                                   "the declared values describe the mesh; fit.hole checks each hole against it",
                                   "petra-maintainers", "docs/parts.md, Rules"),
    Evaluator.THERMAL: model_spec(sys.modules[__name__], "parts.thermal",
                                  "the part's temperature is the ambient plus the declared local rise",
                                  "the heat deflection temperature at the lower ISO 75-2 stress marks where a lightly "
                                  "loaded part softens; creep under sustained load is not checked", "petra-maintainers",
                                  "ISO 75-2 method B; docs/parts.md, What a verdict means"),
}


def _value(sb: StatementBuilder, name: str, lo: Q, hi: Q | None = None, dim: Dim = LENGTH) -> Expr:
    return sb.value(Fixed(Quantity(Interval(lo, lo if hi is None else hi), dim)), name)


def _sq(e: Expr) -> Expr:
    return PowInt(e, 2)


def _sum(terms: list[Expr]) -> Expr:
    terms = [t for t in terms if t is not None]
    return Const(Q(0)) if not terms else terms[0] if len(terms) == 1 else Add(tuple(terms))


def allowance(sb: StatementBuilder, part: PartDesign, registry: Registry, against_screw: bool = False) -> Expr | None:
    """The part's allowance in metres: its tolerance, a finish's buildup, and against a
    screw half its hole shrink. None when nothing gives its tolerance."""
    if part.tolerance is not None:
        terms = [sb.input(part.tolerance)]
    elif part.preset is not None and "tolerance" in registry.processes[part.preset].props:
        terms = [sb.registry(part.preset, "tolerance")]
    else:
        return None
    if part.finish is not None:
        terms.append(sb.registry(part.finish, "buildup"))
    if against_screw:
        shrink = shrink_of(sb, part, registry)
        if shrink is not None:
            terms.append(Mul((Const(Q(1, 2)), shrink)))
    return _sum(terms)


def shrink_of(sb: StatementBuilder, part: PartDesign, registry: Registry) -> Expr | None:
    if part.hole_shrink is not None:
        return sb.input(part.hole_shrink)
    if part.preset is not None and "hole_shrink" in registry.processes[part.preset].props:
        return sb.registry(part.preset, "hole_shrink")
    return None


def _float(sb: StatementBuilder, name: str, lay: engine.Layout, asm: Assembly, registry: Registry) -> Expr:
    """A body's float along its insert axis: the largest over its stops of the stop's own
    float plus both allowances. The base floats not at all."""
    arrival = lay.arrivals.get(name)
    if arrival is None or not arrival.stops:
        return Const(Q(0))
    own = allowance(sb, asm.place(name).body, registry)
    terms = [_sum([_float(sb, o, lay, asm, registry), allowance(sb, asm.place(o).body, registry), own])
             for o in arrival.stops]
    return terms[0] if len(terms) == 1 else Max(tuple(terms))


def _missing(asm: Assembly, names) -> tuple[NeedsInputBound, ...]:
    return tuple(NeedsInputBound((n,), "tolerance", "mm") for n in dict.fromkeys(names)
                 if asm.place(n).body.tolerance is None and asm.place(n).body.preset is None)


def _clearances(sb, approaches, own: Callable[[str], Expr], tag: str, lay, asm, registry):
    """One goal term per approach: (allowances, plus the other's float when the two
    float along different axes)^2 - d^2."""
    exprs, notes = [], []
    for ap in approaches:
        need = [own(ap.other)]
        if ap.crude:
            need.append(_float(sb, ap.other, lay, asm, registry))
        if ap.d2 is None:
            d2 = _value(sb, f"{tag}.{ap.other}.reach2", (ap.reach * M) ** 2, dim=AREA)
            notes.append(f"{ap.other} beyond {float(ap.reach):.3g} mm")
        else:
            d2 = _value(sb, f"{tag}.{ap.other}.clear2", ap.d2 * M * M, dim=AREA)
            notes.append(f"{ap.other} at {float(ap.d2) ** 0.5:.4g} mm (triangles {ap.triangles[0]} and {ap.triangles[1]})")
        exprs.append(Add((_sq(_sum(need)), Neg(d2))))
    return exprs, notes


def build_insert(req: Requirement, asm: Assembly, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    name = req.subject[1]
    lay = engine.layout(asm, registry)
    arrival = lay.arrivals[name]
    needs = _missing(asm, [name, *(a.other for a in arrival.approaches)])
    if needs:
        return (Gap(req, needs),)
    sb = StatementBuilder(design, registry)
    tag = f"{asm.name}.{name}"
    a_m = allowance(sb, asm.place(name).body, registry)
    exprs, notes = _clearances(sb, arrival.approaches, lambda o: _sum([a_m, allowance(sb, asm.place(o).body, registry)]),
                               tag, lay, asm, registry)
    exprs.append(Add((Const(Q(1)), Neg(_value(sb, f"{tag}.stops", Q(len(arrival.stops)), dim=DIMENSIONLESS)))))
    exprs.append(_value(sb, f"{tag}.inside", Q(len(arrival.inside)), dim=DIMENSIONLESS))
    ins = next(i for i in asm.inserts if i.body == name)
    rests = f"rests on {', '.join(arrival.stops)}" if arrival.stops else "rests on nothing, so nothing stops it at its place"
    inside = f"; it lies inside {', '.join(arrival.inside)}" if arrival.inside else ""
    return (Obligation(req, sb.finish(AllNonpositive(tuple(exprs))), MODELS[Evaluator.GEOMETRY],
                       f"{name} travels {float(ins.travel):g} mm along {ins.along.name.lower()} and {rests}{inside}; "
                       f"nearest: {'; '.join(notes) or 'nothing placed before it'}"),)


def build_connected(req: Requirement, asm: Assembly, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    name = req.subject[1]
    lay = engine.layout(asm, registry)
    links = {frozenset(p) for p in lay.touching}
    links |= {frozenset((f.stack[i][0], f.stack[j][0])) for f in asm.fastens for i in range(len(f.stack))
              for j in range(i)}
    links |= {frozenset((p.pin, p.body)) for p in asm.presses}
    reached, frontier = {asm.places[0].body.name}, [asm.places[0].body.name]
    while frontier:
        here = frontier.pop()
        for link in links:
            if here in link:
                for other in link - {here}:
                    if other not in reached:
                        reached.add(other)
                        frontier.append(other)
    sb = StatementBuilder(design, registry)
    loose = Q(0 if name in reached else 1)
    goal = AllNonpositive((_value(sb, f"{asm.name}.{name}.unconnected", loose, dim=DIMENSIONLESS),))
    what = "is held: it touches, is fastened to or is pressed into the base's group" if not loose else \
        f"touches no part of {asm.places[0].body.name}'s group and no fastener or press holds it there"
    return (Obligation(req, sb.finish(goal), MODELS[Evaluator.GEOMETRY], f"{name} {what}"),)


def build_gap(req: Requirement, asm: Assembly, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    a, b = req.subject[1].split("~")
    lay = engine.layout(asm, registry)
    needs = _missing(asm, [a, b])
    if needs:
        return (Gap(req, needs),)
    gap = next(g for g in asm.gaps if (g.a, g.b) == (a, b))
    sb = StatementBuilder(design, registry)
    least = _value(sb, f"{asm.name}.{a}~{b}.least", gap.least * M)
    both = _sum([allowance(sb, asm.place(a).body, registry), allowance(sb, asm.place(b).body, registry), least])
    exprs, notes = _clearances(sb, (lay.gaps[(a, b)],), lambda o: both, f"{asm.name}.{a}~{b}", lay, asm, registry)
    return (Obligation(req, sb.finish(AllNonpositive(tuple(exprs))), MODELS[Evaluator.GEOMETRY],
                       f"{a} and {b} keep {float(gap.least):g} mm apart beyond their allowances; {notes[0]}"),)


def build_fastener(req: Requirement, asm: Assembly, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    fid = req.subject[1]
    lay = engine.layout(asm, registry)
    arrival = lay.arrivals[fid]
    needs = _missing(asm, [a.other for a in arrival.approaches])
    if needs:
        return (Gap(req, needs),)
    f = next(x for x in asm.fastens if x.id == fid)
    sb = StatementBuilder(design, registry)
    exprs, notes = _clearances(sb, arrival.approaches,
                               lambda o: allowance(sb, asm.place(o).body, registry, against_screw=True),
                               f"{asm.name}.{fid}", lay, asm, registry)
    return (Obligation(req, sb.finish(AllNonpositive(tuple(exprs))), MODELS[Evaluator.GEOMETRY],
                       f"{f.screw} travels into {f.stack[-1][0]}.{f.stack[-1][1]} clear of every other part; "
                       f"nearest: {'; '.join(notes)}"),)


def build_seat(req: Requirement, asm: Assembly, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    fid = req.subject[1]
    lay = engine.layout(asm, registry)
    f = next(x for x in asm.fastens if x.id == fid)
    seat = lay.seats[fid]
    first, hid = f.stack[0]
    part, hole = asm.place(first).body, asm.hole(first, hid)
    sb = StatementBuilder(design, registry)
    exprs = [_value(sb, f"{asm.name}.{fid}.seat_uncovered", Q(seat.uncovered), dim=DIMENSIONLESS)]
    what = seat.reason or "the head's bearing ring lies on the first part's face"
    if "csk_angle" in registry.parts[f.screw].props and hole.countersink is not None:
        a = allowance(sb, part, registry)
        if a is None:
            return (Gap(req, _missing(asm, [first])),)
        sink = _value(sb, f"{first}.{hid}.countersink", hole.countersink * M)
        exprs.append(Add((sb.registry(f.screw, "head_d"), Neg(sink), Mul((Const(Q(2)), a)))))
        what = (f"the countersunk head, at most its catalogue diameter, sits at or below the surface in the "
                f"{float(hole.countersink):g} mm countersink less twice the allowance")
    return (Obligation(req, sb.finish(AllNonpositive(tuple(exprs))), MODELS[Evaluator.GEOMETRY], what),)


def build_grip(req: Requirement, asm: Assembly, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    fid = req.subject[1]
    lay = engine.layout(asm, registry)
    f = next(x for x in asm.fastens if x.id == fid)
    engaged, left = lay.grips[fid]
    last = asm.hole(*f.stack[-1])
    sb = StatementBuilder(design, registry)
    e = _value(sb, f"{asm.name}.{fid}.engaged", engaged * M)
    exprs = [Add((Mul((sb.constant(f"parts.engagement.{last.role}"), sb.registry(f.screw, "d"))), Neg(e)))]
    tail = ""
    if last.depth is not None:
        exprs.append(Add((e, Neg(_value(sb, f"{f.stack[-1][0]}.{last.id}.depth", last.depth * M)))))
        tail = f", inside the hole's {float(last.depth):g} mm depth"
    return (Obligation(req, sb.finish(AllNonpositive(tuple(exprs))), MODELS[Evaluator.DECLARED],
                       f"{f.screw} engages {float(engaged):g} mm of {f.stack[-1][0]}.{last.id} ({last.role}){tail}"),)


def build_press(req: Requirement, asm: Assembly, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    p = next(x for x in asm.presses if x.id == req.subject[1])
    needs = _missing(asm, [p.pin, p.body])
    if needs:
        return (Gap(req, needs),)
    hole = asm.hole(p.body, p.hole)
    sb = StatementBuilder(design, registry)
    tol = Mul((Const(Q(2)), _sum([allowance(sb, asm.place(p.pin).body, registry),
                                  allowance(sb, asm.place(p.body).body, registry)])))
    shrink = shrink_of(sb, asm.place(p.body).body, registry)
    nominal = _sum([_value(sb, f"{asm.name}.{p.id}.pin_d", p.diameter * M),
                    Neg(_value(sb, f"{p.body}.{p.hole}.diameter", hole.diameter * M)), shrink])
    lo, hi = _value(sb, f"{asm.name}.{p.id}.least", p.lo * M), _value(sb, f"{asm.name}.{p.id}.most", p.hi * M)
    goal = AllNonpositive((Add((lo, Neg(nominal), tol)), Add((nominal, tol, Neg(hi)))))
    return (Obligation(req, sb.finish(goal), MODELS[Evaluator.DECLARED],
                       f"{p.pin} presses into {p.body}.{p.hole} with between {float(p.lo):g} and {float(p.hi):g} mm of "
                       f"diametral interference at both ends of the tolerances"),)


def build_hole(req: Requirement, part: PartDesign, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    hole = next(h for h in part.holes if h.id == req.subject[1])
    a_hi = engine.tolerance_hi(part, registry)
    if a_hi is None:
        return (Gap(req, (NeedsInputBound((part.name,), "tolerance", "mm"),)),)
    facts = engine.hole_facts(part, hole, a_hi, None)
    sb = StatementBuilder(design, registry)
    tag = f"{part.name}.{hole.id}"
    a = allowance(sb, part, registry)
    radius = _value(sb, f"{tag}.radius", hole.diameter / 2 * M)
    exprs = [Add((_sq(Add((radius, Neg(a)))), Neg(_value(sb, f"{tag}.free2", facts.free2 * M * M, dim=AREA)))),
             _value(sb, f"{tag}.blocked", Q(0 if facts.open else 1), dim=DIMENSIONLESS)]
    if facts.sink is not None:
        exprs.append(_value(sb, f"{tag}.sink_blocked", Q(0 if facts.sink else 1), dim=DIMENSIONLESS))
    free = f"{float(facts.free2) ** 0.5:.4g} mm" if facts.free2 < 10 ** 12 else "no material"
    what = (f"{part.name}.{hole.id}: the axis {'runs through empty space' if facts.open else 'runs through material'}; "
            f"the nearest material to it lies {free} away against a {float(hole.diameter):g} mm hole")
    if facts.sink is not None:
        what += f"; the countersink {'holds' if facts.sink else 'does not hold'} its cone"
    return (Obligation(req, sb.finish(AllNonpositive(tuple(exprs))), MODELS[Evaluator.GEOMETRY], what),)


def build_insert_hole(req: Requirement, part: PartDesign, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    hole = next(h for h in part.holes if h.id == req.subject[1])
    sb = StatementBuilder(design, registry)
    tag = f"{part.name}.{hole.id}"
    made = _sum([_value(sb, f"{tag}.diameter", hole.diameter * M), *(
        [Neg(s)] if (s := shrink_of(sb, part, registry)) is not None else [])])
    goal = AllNonpositive((Add((sb.registry(hole.insert, "hole_min"), Neg(made))),
                           Add((made, Neg(sb.registry(hole.insert, "hole_max"))))))
    return (Obligation(req, sb.finish(goal), MODELS[Evaluator.DECLARED],
                       f"{tag} as made, {float(hole.diameter):g} mm less its shrink, suits {hole.insert}"),)


def build_insert_depth(req: Requirement, part: PartDesign, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    hole = next(h for h in part.holes if h.id == req.subject[1])
    run = hole.depth
    if run is None:
        k = next(m for m in range(3) if hole.along.value[m])
        lo, hi = part.mesh.bounds()
        run = (hi[k] - hole.at[k]) if hole.along.value[k] > 0 else (hole.at[k] - lo[k])
    sb = StatementBuilder(design, registry)
    goal = AllNonpositive((Add((sb.registry(hole.insert, "length"), Neg(_value(sb, f"{part.name}.{hole.id}.run", run * M)))),))
    return (Obligation(req, sb.finish(goal), MODELS[Evaluator.DECLARED],
                       f"{part.name}.{hole.id} runs {float(run):g} mm, against {hole.insert}'s length"),)


def build_boss(req: Requirement, part: PartDesign, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    hole = next(h for h in part.holes if h.id == req.subject[1])
    a_hi = engine.tolerance_hi(part, registry)
    if a_hi is None:
        return (Gap(req, (NeedsInputBound((part.name,), "tolerance", "mm"),)),)
    length = registry.parts[hole.insert].props["length"].value.hi * 1000
    facts = engine.hole_facts(part, hole, a_hi, length)
    sb = StatementBuilder(design, registry)
    tag = f"{part.name}.{hole.id}"
    reach = Add((_value(sb, f"{tag}.radius", hole.diameter / 2 * M), sb.registry(hole.insert, "wall_min")))
    goal = AllNonpositive((Add((_sq(reach), Neg(_value(sb, f"{tag}.wall2", facts.wall2 * M * M, dim=AREA)))),))
    wall = float(facts.wall2) ** 0.5 - float(hole.diameter) / 2 if facts.wall2 < 10 ** 12 else None
    return (Obligation(req, sb.finish(goal), MODELS[Evaluator.GEOMETRY],
                       f"{tag}: the wall around {hole.insert} is "
                       f"{f'{wall:.3g} mm' if wall is not None else 'unbounded'} over its {float(length):g} mm"),)


def build_temperature(req: Requirement, part: PartDesign, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    if design.ambient is None and design.environment is None:
        return (Gap(req, (NeedsInputBound((design.name,), "ambient", "degC"),)),)
    sb = StatementBuilder(design, registry)
    if isinstance(design.ambient, Input):
        ambient = sb.input(design.ambient)
    elif isinstance(design.ambient, ParamRef):
        ambient = sb.value(design.ambient, "ambient")
    else:
        ambient = sb.registry(design.environment, "ambient")
    terms = [ambient, Neg(sb.registry(part.material, "hdt"))]
    if part.heat is not None:
        terms.insert(1, sb.input(part.heat))
    heat = "its declared local rise" if part.heat is not None else "no declared local heat source"
    return (Obligation(req, sb.finish(AllNonpositive((Add(tuple(terms)),))), MODELS[Evaluator.THERMAL],
                       f"{part.name} at the ambient's high end with {heat} stays at or below the heat deflection "
                       f"temperature of {part.material}"),)


def build_extent(req: Requirement, part: PartDesign, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """The mesh's extent, grown by its allowance on both sides, against the machine's."""
    lo, hi = part.mesh.bounds()
    rows = ("bed_x", "bed_y") if part.kind.value == "sheet" else ("build_x", "build_y", "build_z")
    sb = StatementBuilder(design, registry)
    a = allowance(sb, part, registry)
    if a is None:
        return (Gap(req, (NeedsInputBound((part.name,), "tolerance", "mm"),)),)
    exprs = [Add((_value(sb, f"{part.name}.extent_{'xyz'[k]}", (hi[k] - lo[k]) * M), Mul((Const(Q(2)), a)),
                  Neg(sb.registry(part.preset, row))))
             for k, row in enumerate(rows)]
    size = " x ".join(f"{float(hi[k] - lo[k]):g}" for k in range(3))
    return (Obligation(req, sb.finish(AllNonpositive(tuple(exprs))), MODELS[Evaluator.GEOMETRY],
                       f"{part.name}, {size} mm in its mesh frame, fits {part.preset}"),)


def build_flat(req: Requirement, part: PartDesign, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """A sheet part is a flat profile exactly the stock's thickness. A bent part fails:
    its bends need bend lines, radii and a bend allowance, which v0 does not read."""
    thickness, problem = engine.flat(part)
    sb = StatementBuilder(design, registry)
    stock = sb.registry(part.preset, "thickness")
    t = _value(sb, f"{part.name}.thickness", thickness * M)
    exprs = [Add((t, Neg(stock))), Add((stock, Neg(t)))]
    if problem is not None:
        exprs.append(_value(sb, f"{part.name}.off_profile", Q(1), dim=DIMENSIONLESS))
        what = f"{part.name} is not a flat profile: {problem}; a bent part needs bend lines, which v0 does not read"
    else:
        what = f"{part.name} is a flat profile {float(thickness):g} mm thick"
    return (Obligation(req, sb.finish(AllNonpositive(tuple(exprs))), MODELS[Evaluator.GEOMETRY], what),)


def build_bridge(req: Requirement, part: PartDesign, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """Every face printed over air spans at most the bridge row. A face narrower than the
    bridge's low end and held on every edge passes: lines laid across its narrower side
    span at most that side. A face with a point farther than half the bridge from all its
    edges fails: every straight line through that point spans more. Any other face,
    including one with a free edge, which is an overhang, leaves the rule UNKNOWN."""
    sb = StatementBuilder(design, registry)
    row = registry.processes[part.preset].props["bridge"].value
    lo = row.lo * 1000
    bridge = sb.registry(part.preset, "bridge")
    passes, fails, open_ = [], [], []
    for n, b in enumerate(engine.bridges(part)):
        if 4 * b.far2 > lo * lo:
            far2 = _value(sb, f"{part.name}.bridge{n}.far2", b.far2 * M * M, dim=AREA)
            fails.append((Add((Mul((Const(Q(4)), far2)), Neg(_sq(bridge)))), b))
        elif not b.free and b.width <= lo:
            passes.append(Add((_value(sb, f"{part.name}.bridge{n}.width", b.width * M), Neg(bridge))))
        else:
            open_.append(b)
    if fails:
        b = fails[0][1]
        what = (f"{part.name}'s face over air at z {float(b.level):g} mm spans at least {2 * float(b.far2) ** 0.5:.3g} mm "
                f"through ({float(b.witness[0]):g}, {float(b.witness[1]):g}) mm, past the bridge")
        return (Obligation(req, sb.finish(AllNonpositive(tuple(e for e, _ in fails) + tuple(passes))),
                           MODELS[Evaluator.GEOMETRY], what),)
    if open_:
        b = open_[0]
        why = "has an edge with nothing below it, an overhang" if b.free else f"is {float(b.width):g} mm across"
        return (Gap(req, (NoRuleForQuantity(req.id, f"{part.name}'s face over air at z {float(b.level):g} mm {why}; "
                                                    "v0 does not find its longest span"),)),)
    held = len(passes)
    if not passes:
        passes.append(_value(sb, f"{part.name}.faces_over_air", Q(0), dim=DIMENSIONLESS))
    return (Obligation(req, sb.finish(AllNonpositive(tuple(passes))), MODELS[Evaluator.GEOMETRY],
                       f"{part.name} has {held} faces over air, each held on every edge and narrower than the bridge"),)


BUILDERS: Mapping[str, Callable] = {
    "fit.insert": build_insert, "fit.connected": build_connected, "fit.gap": build_gap,
    "fit.fastener": build_fastener, "fit.seat": build_seat, "fit.grip": build_grip, "fit.press": build_press,
    "fit.hole": build_hole, "insert.hole_size": build_insert_hole, "insert.depth": build_insert_depth,
    "insert.boss_wall": build_boss, "part.temperature": build_temperature, "print.volume": build_extent,
    "powder.volume": build_extent, "sheet.bed": build_extent, "sheet.prism": build_flat, "print.bridge": build_bridge,
}
if set(BUILDERS) != {r.id for r in RULE_BY_ID.values() if r.evaluator is not Evaluator.UNMODELLED}:
    raise RuntimeError("parts.build: every modelled rule has one builder")


def build(requirement: Requirement, model, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    return BUILDERS[requirement.mode.id](requirement, model, design, registry)


def mode_models() -> Mapping[FailureMode, ModelSpec]:
    return {FailureMode(r.id): MODELS[r.evaluator] for r in RULE_BY_ID.values() if r.evaluator is not Evaluator.UNMODELLED}
