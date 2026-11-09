"""Turns the engine's measures into obligations the kernel checks. Trusted.

One builder per rule. Each states an R4 goal over three kinds of premise: the exact
geometry the engine measured, as design values labelled dsg:<design>.<name>; the
registry rows and constants it compares them with, labelled reg:; and the design's signed
bounds (tolerance, hole shrink, fill, mass, heat), labelled in:. The kernel then checks
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
from ...kernel import Add, Const, Expr, Interval, Max, Mul, Neg, PowInt, enclose
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
        "polygonal prisms of their shank and head, their axis on the hole their thread enters; a thread holds in a "
        "bore inside its basic pitch diameter")
MODELS: Mapping[Evaluator, ModelSpec] = {
    Evaluator.GEOMETRY: model_spec(sys.modules[__name__], "parts.geometry",
                                   "exact rational geometry of the placed meshes: swept triangle distances, ray parity, "
                                   "and bores read in slabs about a declared hole's axis", _FIT, "petra-maintainers",
                                   "docs/parts.md, Fit under tolerance"),
    Evaluator.THERMAL: model_spec(sys.modules[__name__], "parts.thermal",
                                  "the part's temperature is the ambient plus the declared local rise",
                                  "the heat deflection temperature at the lower ISO 75-2 stress marks where a lightly "
                                  "loaded part softens; creep under sustained load is not checked", "petra-maintainers",
                                  "ISO 75-2 method B; docs/parts.md, What a verdict means"),
    Evaluator.MASS: model_spec(sys.modules[__name__], "parts.mass",
                               "mass is volume, moved by the shell within the allowance of the surface, times "
                               "density times fill, plus a finish's coat, or a bought part's declared mass, plus every "
                               "screw and insert; the centre of mass weighs each solid part's centroid moved by its "
                               "float and shell, a declared cg line moved by its float, and each screw and insert "
                               "anywhere along its axis",
                               "solid parts have uniform density; a printed part's infill only lowers its mass, so an "
                               "unfilled printed part bounds mass from above and needs a cg line for its centre",
                               "petra-maintainers", "docs/parts.md, What a verdict means"),
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
    screw half its hole shrink. None when nothing gives its tolerance. A preset with a
    tolerance rate holds the larger of its floor and the rate times the part's span."""
    if part.tolerance is not None:
        terms = [sb.input(part.tolerance)]
    elif part.preset is not None and "tolerance" in registry.processes[part.preset].props:
        floor_ = sb.registry(part.preset, "tolerance")
        if "tolerance_rate" in registry.processes[part.preset].props:
            span = _value(sb, f"{part.name}.span", engine.span(part.mesh) * M)
            floor_ = Max((floor_, Mul((sb.registry(part.preset, "tolerance_rate"), span))))
        terms = [floor_]
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


def _bodies(approaches) -> list[str]:
    return [a.other for a in approaches if a.screw is None]


def _clearances(sb, approaches, own: Callable[[engine.Approach], Expr], tag: str, lay, asm, registry):
    """One goal term per approach: (allowances, plus the other's float when the two
    float along different axes)^2 - d^2. Surfaces that meet fail whatever the allowance,
    since a zero distance cannot tell touching from crossing."""
    exprs, notes = [], []
    for ap in approaches:
        need = [own(ap)]
        if ap.crude:
            need.append(_float(sb, ap.other, lay, asm, registry))
        what = f"screw {ap.other}" if ap.screw is not None else ap.other
        if ap.d2 is None:
            d2 = _value(sb, f"{tag}.{ap.other}.reach2", (ap.reach * M) ** 2, dim=AREA)
            notes.append(f"{what} beyond {float(ap.reach):.3g} mm")
        else:
            d2 = _value(sb, f"{tag}.{ap.other}.clear2", ap.d2 * M * M, dim=AREA)
            notes.append(f"{what} at {float(ap.d2) ** 0.5:.4g} mm (triangles {ap.triangles[0]} and {ap.triangles[1]})")
            if ap.d2 == 0:
                exprs.append(_value(sb, f"{tag}.{ap.other}.met", Q(1), dim=DIMENSIONLESS))
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
    exprs, notes = _clearances(sb, arrival.approaches,
                               lambda ap: _sum([a_m, allowance(sb, asm.place(ap.other).body, registry)]),
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
    exprs, notes = _clearances(sb, (lay.gaps[(a, b)],), lambda ap: both, f"{asm.name}.{a}~{b}", lay, asm, registry)
    return (Obligation(req, sb.finish(AllNonpositive(tuple(exprs))), MODELS[Evaluator.GEOMETRY],
                       f"{a} and {b} keep {float(gap.least):g} mm apart beyond their allowances; {notes[0]}"),)


def build_fastener(req: Requirement, asm: Assembly, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """The screw's path from beyond every body, against every body but the last, the last
    before its hole's mouth, and every screw fastened before it. The screw's axis follows
    the hole its thread enters, so it may sit off nominal by that body's allowance, which
    adds to every clearance."""
    fid = req.subject[1]
    lay = engine.layout(asm, registry)
    arrival = lay.arrivals[fid]
    f = next(x for x in asm.fastens if x.id == fid)
    last = f.stack[-1][0]
    needs = _missing(asm, [*_bodies(arrival.approaches), last])
    if needs:
        return (Gap(req, needs),)
    sb = StatementBuilder(design, registry)
    shift = allowance(sb, asm.place(last).body, registry, against_screw=True)

    def own(ap: engine.Approach) -> Expr:
        if ap.screw is not None:
            g = next(x for x in asm.fastens if x.id == ap.screw)
            return _sum([shift, allowance(sb, asm.place(g.stack[-1][0]).body, registry, against_screw=True)])
        return _sum([allowance(sb, asm.place(ap.other).body, registry, against_screw=True), shift])

    tag = f"{asm.name}.{fid}"
    exprs, notes = _clearances(sb, arrival.approaches, own, tag, lay, asm, registry)
    clear = lay.clears[fid]
    hole = f"{last}.{f.stack[-1][1]}"
    if clear is None:
        notes.append(f"nothing of {last} before {hole}'s mouth")
    else:
        exprs.append(Add((_sq(_sum([shift, shift])), Neg(_value(sb, f"{tag}.{last}.before2", clear * M * M, dim=AREA)))))
        notes.append(f"{last}'s material before {hole}'s mouth at {float(clear) ** 0.5:.4g} mm")
        if clear == 0:
            exprs.append(_value(sb, f"{tag}.{last}.before_met", Q(1), dim=DIMENSIONLESS))
    return (Obligation(req, sb.finish(AllNonpositive(tuple(exprs))), MODELS[Evaluator.GEOMETRY],
                       f"{f.screw} travels from outside into {hole} clear of every other part and screw; "
                       f"nearest: {'; '.join(notes)}"),)


def build_seat(req: Requirement, asm: Assembly, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """The head against the first hole as the mesh has it just below its mouth, grown by
    the allowance on both sides, with the head off the hole's axis by the shift of the hole
    its thread enters. A socket head at its least diameter still overhangs the hole at its
    widest there. A countersunk head at its greatest fits inside the countersink at its
    narrowest there, so it sits at or below the surface."""
    fid = req.subject[1]
    lay = engine.layout(asm, registry)
    f = next(x for x in asm.fastens if x.id == fid)
    seat = lay.seats[fid]
    first, hid = f.stack[0]
    last = f.stack[-1][0]
    needs = _missing(asm, [first, last])
    if needs:
        return (Gap(req, needs),)
    part, hole = asm.place(first).body, asm.hole(first, hid)
    sb = StatementBuilder(design, registry)
    exprs = [_value(sb, f"{asm.name}.{fid}.seat_uncovered", Q(seat.uncovered), dim=DIMENSIONLESS)]
    what = seat.reason or "the head's bearing ring lies on the first part's face and the head covers the hole"
    a = allowance(sb, part, registry)
    shift = allowance(sb, asm.place(last).body, registry, against_screw=True)
    grow = _sum([Mul((Const(Q(2)), a)), Mul((Const(Q(2)), shift))])
    b = engine.mouth_bore(part, hole)
    tag = f"{first}.{hid}"
    if "csk_angle" in registry.parts[f.screw].props:
        if b.lo2 >= engine.FAR:
            exprs.append(_value(sb, f"{tag}.no_mouth", Q(1), dim=DIMENSIONLESS))
            what = f"{tag}'s mouth meets no surface of {first}, so nothing holds the head there"
        else:
            narrow = engine.root_down(b.lo2)
            exprs.append(_sum([sb.registry(f.screw, "head_d"), grow, Neg(_value(sb, f"{tag}.sink_d", 2 * narrow * M))]))
            if not seat.reason:
                what = (f"the countersunk head, at most its catalogue diameter, fits the countersink, at least "
                        f"{float(2 * narrow):.4g} mm across at the mouth in the mesh, less the allowance and the shift")
    elif b.hi2 is None or not b.open:
        exprs.append(_value(sb, f"{tag}.mouth_unbounded", Q(1), dim=DIMENSIONLESS))
        what = f"the mesh gives {tag} no solid wall at its mouth, so nothing bounds the hole under the head"
    else:
        wide = engine.root_up(b.hi2)
        exprs.append(_sum([_value(sb, f"{tag}.mouth_d", 2 * wide * M), grow, Neg(sb.registry(f.screw, "head_d"))]))
        if not seat.reason:
            what += f", {float(2 * wide):.4g} mm across at its mouth in the mesh before the allowance and the shift"
    return (Obligation(req, sb.finish(AllNonpositive(tuple(exprs))), MODELS[Evaluator.GEOMETRY], what),)


def build_grip(req: Requirement, asm: Assembly, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """The thread engages the last part over its least engagement, read from the mesh. A
    tap or form hole holds the thread when the bore as made, at its widest over that
    length, stays inside the thread's basic pitch diameter (d - 0.6495 P, ISO 724, taken as
    d - 0.65 P) and solid material reaches past the crest; an insert must take the screw's
    size and be as long as the engagement. In a blind hole the tip, at the screw's
    greatest length and deepest seat, stops short of the floor the mesh's axis meets."""
    fid = req.subject[1]
    lay = engine.layout(asm, registry)
    f = next(x for x in asm.fastens if x.id == fid)
    grip = lay.grips[fid]
    last_body, last_id = f.stack[-1]
    last = asm.hole(last_body, last_id)
    needs = _missing(asm, [last_body])
    if needs:
        return (Gap(req, needs),)
    part = asm.place(last_body).body
    sb = StatementBuilder(design, registry)
    tag = f"{asm.name}.{fid}"
    a = allowance(sb, part, registry)
    d = sb.registry(f.screw, "d")
    exprs, notes = [], []
    if last.role not in ("tap", "form", "insert"):
        exprs.append(_value(sb, f"{tag}.no_thread", Q(1), dim=DIMENSIONLESS))
        notes.append(f"a {last.role} hole holds no thread")
    else:
        least = Mul((sb.constant(f"parts.engagement.{last.role}"), d))
        exprs.append(Add((least, Neg(_value(sb, f"{tag}.engaged", grip.engaged_lo * M)))))
        notes.append(f"engages {float(grip.engaged_lo):g} mm of {last_body}.{last_id} ({last.role}) at the least")
    if last.role in ("tap", "form"):
        b = grip.bore
        if b is None or b.hi2 is None or not b.open:
            exprs.append(_value(sb, f"{tag}.bore_unbounded", Q(1), dim=DIMENSIONLESS))
            notes.append(f"the mesh gives the hole no solid wall over the thread's {float(grip.zone):.3g} mm")
        else:
            bore = engine.root_up(b.hi2)
            pitch_d = Add((sb.registry(f.screw, "thread_d"), Neg(Mul((Const(Q(13, 20)), sb.registry(f.screw, "pitch"))))))
            exprs.append(Add((_value(sb, f"{tag}.bore", 2 * bore * M), Mul((Const(Q(2)), a)), Neg(pitch_d))))
            notes.append(f"the bore is at most {float(2 * bore):.4g} mm across over {float(grip.zone):.3g} mm")
            if b.out2 is not None:
                exprs.append(Add((_sq(Add((Mul((Const(Q(1, 2)), d)), a))),
                                  Neg(_value(sb, f"{tag}.wall2", b.out2 * M * M, dim=AREA)))))
    elif last.role == "insert":
        size, takes = sb.registry(f.screw, "thread_d"), sb.registry(last.insert, "thread_d")
        exprs += [Add((size, Neg(takes))), Add((takes, Neg(size))),
                  Add((Mul((sb.constant("parts.engagement.insert"), d)), Neg(sb.registry(last.insert, "length"))))]
        notes.append(f"{last.insert} takes the thread over its length")
    if grip.run is not None:
        run = _value(sb, f"{last_body}.{last_id}.run", grip.run * M)
        if grip.engaged_hi is None:
            exprs.append(_value(sb, f"{tag}.seat_unbounded", Q(1), dim=DIMENSIONLESS))
            notes.append("the countersink does not stop the head, so the tip's reach is unbounded")
        else:
            exprs.append(Add((_value(sb, f"{tag}.reach", grip.engaged_hi * M), a, Neg(run))))
            notes.append(f"the tip reaches {float(grip.engaged_hi):.4g} mm at the most, against a floor "
                         f"{float(grip.run):.4g} mm in")
    return (Obligation(req, sb.finish(AllNonpositive(tuple(exprs))), MODELS[Evaluator.GEOMETRY],
                       f"{f.screw}: {'; '.join(notes)}"),)


def build_press(req: Requirement, asm: Assembly, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """The interference read from the two meshes over the length where the pin meets the
    hole: at least twice the least distance from the hole's wall to the pin's surface, at
    most twice the pin's greatest radius less the hole's least, each moved by both
    allowances and the hole's shrink. A pin that does not sit in its hole fails."""
    p = next(x for x in asm.presses if x.id == req.subject[1])
    needs = _missing(asm, [p.pin, p.body])
    if needs:
        return (Gap(req, needs),)
    lay = engine.layout(asm, registry)
    fit = lay.presses[p.id]
    sb = StatementBuilder(design, registry)
    tag = f"{asm.name}.{p.id}"
    if fit.seated:
        goal = AllNonpositive((_value(sb, f"{tag}.unseated", Q(1), dim=DIMENSIONLESS),))
        return (Obligation(req, sb.finish(goal), MODELS[Evaluator.GEOMETRY], f"{p.pin} does not sit in {p.body}.{p.hole}: "
                                                                              f"{fit.seated}"),)
    tol = Mul((Const(Q(2)), _sum([allowance(sb, asm.place(p.pin).body, registry),
                                  allowance(sb, asm.place(p.body).body, registry)])))
    shrink = shrink_of(sb, asm.place(p.body).body, registry)
    least = 2 * engine.root_down(fit.grip2)
    most = 2 * (engine.root_up(fit.pin2) - engine.root_down(fit.hole2))
    lo_ = _sum([_value(sb, f"{tag}.grip", least * M), shrink, Neg(tol)])
    hi_ = _sum([_value(sb, f"{tag}.spread", most * M), shrink, tol])
    lo, hi = _value(sb, f"{tag}.least", p.lo * M), _value(sb, f"{tag}.most", p.hi * M)
    goal = AllNonpositive((Add((lo, Neg(lo_))), Add((hi_, Neg(hi)))))
    return (Obligation(req, sb.finish(goal), MODELS[Evaluator.GEOMETRY],
                       f"{p.pin} presses into {p.body}.{p.hole}: the meshes give {float(least):.4g} to {float(most):.4g} mm "
                       f"of diametral interference before tolerances, against {float(p.lo):g} to {float(p.hi):g} mm"),)


def build_hole(req: Requirement, part: PartDesign, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    hole = next(h for h in part.holes if h.id == req.subject[1])
    if engine.tolerance_hi(part, registry) is None:
        return (Gap(req, (NeedsInputBound((part.name,), "tolerance", "mm"),)),)
    facts = engine.hole_facts(part, hole, engine.allowance_hi(part, registry))
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


def _insert_bore(part: PartDesign, hole: Hole, registry: Registry) -> tuple[engine.Bore, Q]:
    length = registry.parts[hole.insert].props["length"].value.hi * 1000
    return engine.hole_bore(part, hole, length), length


def build_insert_hole(req: Requirement, part: PartDesign, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """The hole as made, read from the mesh over the insert's length, lies in the
    catalogue's range: at its narrowest, less the allowance on each side and its shrink,
    it is at least the least hole; at its widest, plus the allowance on each side, less
    its shrink, at most the greatest."""
    hole = next(h for h in part.holes if h.id == req.subject[1])
    if engine.tolerance_hi(part, registry) is None:
        return (Gap(req, (NeedsInputBound((part.name,), "tolerance", "mm"),)),)
    b, length = _insert_bore(part, hole, registry)
    sb = StatementBuilder(design, registry)
    tag = f"{part.name}.{hole.id}"
    if not b.open or b.hi2 is None:
        goal = AllNonpositive((_value(sb, f"{tag}.bore_unbounded", Q(1), dim=DIMENSIONLESS),))
        why = "its axis meets material" if not b.open else "the mesh gives it no solid wall"
        return (Obligation(req, sb.finish(goal), MODELS[Evaluator.GEOMETRY],
                           f"{tag} over {float(length):g} mm: {why}"),)
    a = allowance(sb, part, registry)
    shrink = shrink_of(sb, part, registry) or Const(Q(0))
    narrow, wide = engine.root_down(b.lo2), engine.root_up(b.hi2)
    least = _value(sb, f"{tag}.narrowest", 2 * narrow * M)
    most = _value(sb, f"{tag}.widest", 2 * wide * M)
    two_a = Mul((Const(Q(2)), a))
    goal = AllNonpositive((_sum([sb.registry(hole.insert, "hole_min"), shrink, two_a, Neg(least)]),
                           _sum([most, two_a, Neg(shrink), Neg(sb.registry(hole.insert, "hole_max"))])))
    return (Obligation(req, sb.finish(goal), MODELS[Evaluator.GEOMETRY],
                       f"{tag} measures {float(2 * narrow):.4g} to {float(2 * wide):.4g} mm across over the insert's "
                       f"{float(length):g} mm, against {hole.insert}'s range"),)


def build_insert_depth(req: Requirement, part: PartDesign, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """The hole's axis runs at least the insert's length, plus the allowance, before it
    meets material; a hole the axis runs through needs a solid wall over the length."""
    hole = next(h for h in part.holes if h.id == req.subject[1])
    if engine.tolerance_hi(part, registry) is None:
        return (Gap(req, (NeedsInputBound((part.name,), "tolerance", "mm"),)),)
    sb = StatementBuilder(design, registry)
    tag = f"{part.name}.{hole.id}"
    run = engine.hole_run(part, hole)
    if run is None:
        b, length = _insert_bore(part, hole, registry)
        walled = b.open and b.hi2 is not None
        goal = AllNonpositive((_value(sb, f"{tag}.unwalled", Q(0 if walled else 1), dim=DIMENSIONLESS),))
        return (Obligation(req, sb.finish(goal), MODELS[Evaluator.GEOMETRY],
                           f"{tag} runs through the part, {'with' if walled else 'without'} a solid wall over "
                           f"{hole.insert}'s {float(length):g} mm"),)
    goal = AllNonpositive((_sum([sb.registry(hole.insert, "length"), allowance(sb, part, registry),
                                 Neg(_value(sb, f"{tag}.run", run * M))]),))
    return (Obligation(req, sb.finish(goal), MODELS[Evaluator.GEOMETRY],
                       f"{tag}'s axis runs {float(run):g} mm before it meets material, against {hole.insert}'s length"),)


def build_boss(req: Requirement, part: PartDesign, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """Solid material reaches from the hole's widest, read from the mesh, out past the
    catalogue's least wall, over the insert's length, with the allowance on both faces."""
    hole = next(h for h in part.holes if h.id == req.subject[1])
    if engine.tolerance_hi(part, registry) is None:
        return (Gap(req, (NeedsInputBound((part.name,), "tolerance", "mm"),)),)
    b, length = _insert_bore(part, hole, registry)
    sb = StatementBuilder(design, registry)
    tag = f"{part.name}.{hole.id}"
    if not b.open or b.hi2 is None:
        goal = AllNonpositive((_value(sb, f"{tag}.bore_unbounded", Q(1), dim=DIMENSIONLESS),))
        return (Obligation(req, sb.finish(goal), MODELS[Evaluator.GEOMETRY],
                           f"{tag}: the mesh gives the hole no solid wall over {float(length):g} mm"),)
    wide = engine.root_up(b.hi2)
    if b.out2 is None:
        goal = AllNonpositive((_value(sb, f"{tag}.outer", Q(0), dim=DIMENSIONLESS),))
        return (Obligation(req, sb.finish(goal), MODELS[Evaluator.GEOMETRY],
                           f"{tag}: no surface lies beyond the hole's wall over {float(length):g} mm"),)
    a = allowance(sb, part, registry)
    reach = _sum([_value(sb, f"{tag}.widest_r", wide * M), Mul((Const(Q(2)), a)), sb.registry(hole.insert, "wall_min")])
    goal = AllNonpositive((Add((_sq(reach), Neg(_value(sb, f"{tag}.wall2", b.out2 * M * M, dim=AREA)))),))
    wall = float(b.out2) ** 0.5 - float(wide)
    return (Obligation(req, sb.finish(goal), MODELS[Evaluator.GEOMETRY],
                       f"{tag}: the wall around {hole.insert} is {wall:.3g} mm over its {float(length):g} mm before "
                       f"the allowance"),)


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


# --- Mass ----------------------------------------------------------------------------


def _printed(part: PartDesign) -> bool:
    return part.kind is not None and part.kind.value == "print"


def _shell(sb: StatementBuilder, part: PartDesign, a: Expr) -> Expr:
    """An upper bound (m^3) on the volume within the allowance a of the part's surface on
    either side: every such point lies within a of a face's inside, of an edge where the
    faces bend, or of a corner, so the shell holds at most area a + 4 length a^2 +
    5 corners a^3 (pi < 4, 4 pi / 3 < 5)."""
    area, ridge, corners = engine.surface(part.mesh)
    return _sum([Mul((_value(sb, f"{part.name}.area", area * M * M, dim=AREA), a)),
                 Mul((Const(Q(4)), _value(sb, f"{part.name}.ridge", ridge * M), _sq(a))),
                 Mul((Const(Q(5)), _value(sb, f"{part.name}.corners", Q(corners), dim=DIMENSIONLESS), PowInt(a, 3)))])


def _masses(sb: StatementBuilder, model, registry: Registry, axis: int | None, bound: Q = Q(0)) -> tuple[list, list]:
    """([(mass hi, mass lo, moment hi, moment lo, part or None)] for every part, screw and
    insert of the model, the needs that stop it), Exprs in kg and kg m; a moment is about
    the plane at `bound` (m) across `axis`, None without an axis.

    A solid part's mass is its density (times its fill) times its volume, moved by the
    shell within its allowance of its surface, and a finish's coat weighs at most its
    density times twice that shell. Its centre moves along its insert axis by its float.
    Material added beyond the plane, or taken away before it, raises its moment by at most
    the shell times the farthest the part reaches past the plane on that side. A printed part's mass needs its fill unless only an upper bound
    is asked (fill then counts as 1); its centre, and a bought part's, needs a cg line.
    Screws and inserts are uniform, their centres on their axes anywhere along their length
    and off it by the hole's shift."""
    asm = isinstance(model, Assembly)
    places = [(p.body, p.placement) for p in model.places] if asm else [(model, None)]
    lay = engine.layout(model, registry) if asm and axis is not None else None
    out, needs = [], []
    plane = Const(bound)

    def slack(name: str) -> Q:
        if lay is None or lay.axes.get(name) is None or lay.axes[name].value[axis] == 0:
            return Q(0)
        return lay.floats[name]

    def moments(hi: Expr, lo: Expr, c_lo: Q, c_hi: Q, tag: str) -> tuple[Expr, Expr]:
        """Bounds on the moment of a mass in [lo, hi] whose centre lies in [c_lo, c_hi] mm."""
        up = Add((_value(sb, f"{tag}_hi", c_hi * M), Neg(plane)))
        down = Add((_value(sb, f"{tag}_lo", c_lo * M), Neg(plane)))
        return Mul((hi if c_hi * M >= bound else lo, up)), Mul((lo if c_lo * M >= bound else hi, down))

    for part, placement in places:
        move = placement.apply if placement is not None else (lambda q: q)
        sl = slack(part.name)
        shell = dens = volume = a = None
        if part.mass is not None:
            hi = lo = sb.input(part.mass)
        else:
            a = allowance(sb, part, registry)
            if a is None:
                needs.append(NeedsInputBound((part.name,), "tolerance", "mm"))
                continue
            volume = _value(sb, f"{part.name}.volume", part.mesh.volume() * M ** 3, dim=VOLUME)
            shell = _shell(sb, part, a)
            dens = sb.registry(part.material, "density")
            if part.fill is not None:
                dens = Mul((dens, sb.input(part.fill)))
            coat = Mul((Const(Q(2)), sb.registry(part.finish, "density"), shell)) if part.finish is not None else None
            hi = _sum([Mul((dens, Add((volume, shell)))), coat])
            lo = Mul((dens, Add((volume, Neg(shell)))))
        mom_hi = mom_lo = None
        if axis is not None:
            name = f"{part.name}.cg_{'xyz'[axis]}"
            solid = part.mass is None and (not _printed(part) or (part.fill is not None and part.fill.range.value.lo == 1))
            if part.cg is not None:
                c = move(part.cg)[axis]
                mom_hi, mom_lo = moments(hi, lo, c - sl, c + sl, name)
            elif solid:
                c = move(part.mesh.centroid())[axis]
                ends = [move(p)[axis] for p in _box_corners(part.mesh)]
                low = _value(sb, f"{part.name}.low_{'xyz'[axis]}", (min(ends) - sl) * M)
                high = _value(sb, f"{part.name}.high_{'xyz'[axis]}", (max(ends) + sl) * M)
                past = Max((Add((high, Neg(plane), a)), Const(Q(0))))
                short = Max((Add((plane, Neg(low), a)), Const(Q(0))))
                spread = Mul((shell, Add((past, short))))
                coat = Mul((Const(Q(2)), sb.registry(part.finish, "density"), shell)) if part.finish else None
                up = Mul((volume, Add((_value(sb, f"{name}_hi", (c + sl) * M), Neg(plane)))))
                down = Mul((volume, Add((_value(sb, f"{name}_lo", (c - sl) * M), Neg(plane)))))
                mom_hi = _sum([Mul((dens, Add((up, spread)))), None if coat is None else Mul((coat, past))])
                mom_lo = _sum([Mul((dens, Add((down, Neg(spread))))), None if coat is None else Neg(Mul((coat, short)))])
            else:
                needs.append(NeedsInputBound((part.name,), "cg", "mm"))
        out.append((hi, lo, mom_hi, mom_lo, part))
        for h in part.holes:
            if h.insert is not None:
                m = sb.registry(h.insert, "mass")
                mom = (None, None)
                if axis is not None:
                    length = registry.parts[h.insert].props["length"].value.hi * 1000
                    ends = [move(h.at)[axis], move(tuple(h.at[n] + length * h.along.value[n] for n in range(3)))[axis]]
                    off = sl + engine.allowance_hi(part, registry)
                    mom = moments(m, m, min(ends) - off, max(ends) + off, f"{part.name}.{h.id}.insert_{'xyz'[axis]}")
                out.append((m, m, *mom, None))
    if asm:
        for f in model.fastens:
            m = sb.registry(f.screw, "mass")
            mom = (None, None)
            if axis is not None:
                c_lo, c_hi = engine.screw_span(lay, f.id, axis)
                mom = moments(m, m, c_lo, c_hi, f"{model.name}.{f.id}.screw_{'xyz'[axis]}")
            out.append((m, m, *mom, None))
    return out, needs


def _box_corners(mesh) -> list:
    lo, hi = mesh.bounds()
    return [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]


def build_mass(req: Requirement, model, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """Mass against a claim, over the tolerance: a <= claim reads every item's upper bound
    and a >= claim its lower. A printed part with no fill line counts as solid, which only
    bounds its mass from above: so a <= claim is stated only when it holds that way, and
    otherwise, like any >= claim, needs the fill."""
    criterion = req.criterion
    if not isinstance(criterion, Criterion):
        return (Gap(req, (NoRuleForQuantity(req.id, "a mass is checked against a claim's bound"),)),)
    sb = StatementBuilder(design, registry)
    terms, needs = _masses(sb, model, registry, axis=None)
    if needs:
        return (Gap(req, tuple(dict.fromkeys(needs))),)
    unfilled = [p for *_, p in terms if p is not None and _printed(p) and p.fill is None and p.mass is None]
    bound = criterion.bound.value.lo
    le = criterion.rel is Rel.LE
    if unfilled:
        box = sb.box()
        upper = sum(enclose(t[0], box).hi for t in terms)
        if not le or upper > bound:
            return (Gap(req, tuple(NeedsInputBound((p.name,), "fill", "1") for p in unfilled)),)
    total = _sum([t[0] if le else t[1] for t in terms])
    expr = Add((total, Neg(Const(bound)))) if le else Add((Const(bound), Neg(total)))
    solid = f", counting {', '.join(p.name for p in unfilled)} as solid" if unfilled else ""
    return (Obligation(req, sb.finish(AllNonpositive((expr,))), MODELS[Evaluator.MASS],
                       f"{model.name}'s mass, {len(terms)} items over the tolerance, is {criterion.rel.value} "
                       f"{float(bound) * 1000:g} g{solid}"),)


def build_cg(req: Requirement, model: Assembly, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    criterion = req.criterion
    if not isinstance(criterion, Criterion) or req.qoi is None:
        return (Gap(req, (NoRuleForQuantity(req.id, "a centre of mass is checked against a claim's bound"),)),)
    axis = "xyz".index(req.qoi.name[-1])
    sb = StatementBuilder(design, registry)
    bound = criterion.bound.value.lo
    terms, needs = _masses(sb, model, registry, axis=axis, bound=bound)
    needs += [NeedsInputBound((p.name,), "fill", "1") for *_, p in terms
              if p is not None and _printed(p) and p.fill is None and p.mass is None]
    if needs:
        return (Gap(req, tuple(dict.fromkeys(needs))),)
    le = criterion.rel is Rel.LE
    total = _sum([t[2] if le else Neg(t[3]) for t in terms])
    return (Obligation(req, sb.finish(AllNonpositive((total,))), MODELS[Evaluator.MASS],
                       f"{model.name}'s centre of mass along {'xyz'[axis]} is {criterion.rel.value} "
                       f"{float(bound) * 1000:g} mm, weighing {len(terms)} items over the tolerance"),)


BUILDERS: Mapping[str, Callable] = {
    "fit.insert": build_insert, "fit.connected": build_connected, "fit.gap": build_gap,
    "fit.fastener": build_fastener, "fit.seat": build_seat, "fit.grip": build_grip, "fit.press": build_press,
    "fit.hole": build_hole, "insert.hole_size": build_insert_hole, "insert.depth": build_insert_depth,
    "insert.boss_wall": build_boss, "part.temperature": build_temperature, "print.volume": build_extent,
    "powder.volume": build_extent, "sheet.bed": build_extent, "sheet.prism": build_flat, "print.bridge": build_bridge, "parts.mass": build_mass, "parts.cg": build_cg,
}
if set(BUILDERS) != {r.id for r in RULE_BY_ID.values() if r.evaluator is not Evaluator.UNMODELLED}:
    raise RuntimeError("parts.build: every modelled rule has one builder")


def build(requirement: Requirement, model, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    return BUILDERS[requirement.mode.id](requirement, model, design, registry)


def mode_models() -> Mapping[FailureMode, ModelSpec]:
    return {FailureMode(r.id): MODELS[r.evaluator] for r in RULE_BY_ID.values() if r.evaluator is not Evaluator.UNMODELLED}
