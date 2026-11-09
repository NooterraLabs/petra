"""Every geometric fact the parts rules state, measured exactly once per model. Trusted.

The engine reads the lowered models and the registry's hi ends, so it knows how far to
search, and returns exact rationals in millimetres. build.py states each fact as a design
value beside the tolerance premises it is compared with, so every verdict names both.

The assembly model (docs/parts.md, "Fit under tolerance"):

- Each body's true surface lies within its allowance `a` of its nominal surface: the
  profile tolerance plus a finish's buildup. Against a screw a printed body's allowance
  also holds half its hole shrink, because holes come out smaller.
- Bodies go in in place-line order. The first is the base; every other arrives along its
  insert axis and stops on the faces it touches there whose triangles lie wholly ahead of
  its own along the travel (its stops). Its position along that axis then floats by
  F = max over its stops of (F_stop + a_stop + a_self), and not at all across it.
- A mover's path is swept from its start to its place and on by its float, back by it
  too. Every triangle pair but its stops must keep apart by the two allowances, and by
  the other body's float when the two floats run along different axes.
- A screw is the circumscribed 32-sided prism of its shank, with its head's prism over a
  socket head. Its axis is the hole its thread enters; its head sits at the first hole's
  mouth. It may overlap only that last body.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from math import ceil, floor, lcm
from typing import Mapping

import numpy as np

from ...registry import Registry
from . import exact
from .exact import Body, make_body
from .lower import Assembly, Fasten, Hole, PartDesign
from .mesh import Point
from .space import Axis, Placement, Solid

Q = Fraction
MM = 1000                       # registry metres to millimetres


# --- Allowances, read at their hi ends ---------------------------------------------


def tolerance_hi(part: PartDesign, registry: Registry) -> Q | None:
    """The part's profile tolerance (mm, hi end), or None when neither a tolerance line
    nor a process preset gives one."""
    if part.tolerance is not None:
        return part.tolerance.range.value.hi * MM
    if part.preset is not None and "tolerance" in registry.processes[part.preset].props:
        return registry.processes[part.preset].props["tolerance"].value.hi * MM
    return None


def shrink_hi(part: PartDesign, registry: Registry) -> Q:
    if part.hole_shrink is not None:
        return part.hole_shrink.range.value.hi * MM
    if part.preset is not None and "hole_shrink" in registry.processes[part.preset].props:
        return registry.processes[part.preset].props["hole_shrink"].value.hi * MM
    return Q(0)


def allowance_hi(part: PartDesign, registry: Registry, against_screw: bool = False) -> Q:
    """The hi end of the part's allowance (mm); a part with no tolerance counts zero here
    and build.py reports it as a gap."""
    a = tolerance_hi(part, registry) or Q(0)
    if part.finish is not None:
        a += registry.processes[part.finish].props["buildup"].value.hi * MM
    if against_screw:
        a += shrink_hi(part, registry) / 2
    return a


# --- Rational polygons ---------------------------------------------------------------

_QUARTER = ((Q(1), Q(0)), (Q(24, 25), Q(7, 25)), (Q(15, 17), Q(8, 17)), (Q(4, 5), Q(3, 5)), (Q(21, 29), Q(20, 29)),
            (Q(3, 5), Q(4, 5)), (Q(8, 17), Q(15, 17)), (Q(7, 25), Q(24, 25)))
NORMALS = tuple((c * sx - s * sy, c * sy + s * sx) for sx, sy in ((1, 0), (0, 1), (-1, 0), (0, -1)) for c, s in _QUARTER)
"""32 rational unit vectors around the circle, at most 16.26 degrees apart (inferred
from the Pythagorean triples 7-24-25, 8-15-17, 3-4-5 and 20-21-29)."""


def circumscribed(r: Q) -> tuple[tuple[Q, Q], ...]:
    """A 32-gon whose sides touch the circle of radius r, so it holds the circle; its
    corners lie within r / cos(8.13 deg), about 1.0102 r, of the centre (inferred)."""
    out = []
    for k in range(len(NORMALS)):
        (a, b), (c, d) = NORMALS[k], NORMALS[(k + 1) % len(NORMALS)]
        f = r / (1 + a * c + b * d)
        out.append(((a + c) * f, (b + d) * f))
    return tuple(out)


def inscribed(r: Q) -> tuple[tuple[Q, Q], ...]:
    """A 32-gon whose corners lie on the circle of radius r, so the circle holds it."""
    return tuple((r * a, r * b) for a, b in NORMALS)


def _frame(axis: tuple[int, int, int]) -> tuple[int, int, int]:
    """(k, i, j): the axis's coordinate and the two across it."""
    k = next(m for m in range(3) if axis[m])
    return k, (k + 1) % 3, (k + 2) % 3


def frustum(centre: Point, axis: tuple[int, int, int], top: tuple, bottom: tuple, height: Q) -> list:
    """Triangles of the solid between polygon `top` at `centre` and polygon `bottom` at
    `centre + height * axis` (same corner count), mm, as exact rational points."""
    k, i, j = _frame(axis)
    s = axis[k]

    def point(p2, h):
        p = [Q(0), Q(0), Q(0)]
        p[k], p[i], p[j] = centre[k] + s * h, centre[i] + p2[0], centre[j] + p2[1]
        return tuple(p)

    n = len(top)
    up = [point(p, Q(0)) for p in top]
    down = [point(p, height) for p in bottom]
    tris = [(up[0], up[m], up[m + 1]) for m in range(1, n - 1)]
    tris += [(down[0], down[m + 1], down[m]) for m in range(1, n - 1)]
    for m in range(n):
        a, b = m, (m + 1) % n
        tris += [(up[a], down[a], down[b]), (up[a], down[b], up[b])]
    return tris


def body_of(name: str, den: int, tris: list) -> Body:
    arr = np.array([[[int(c * den) for c in p] for p in t] for t in tris], dtype=np.int64)
    if any(c * den != int(c * den) for t in tris for p in t for c in p):
        raise ValueError("the denominator does not hold the polygon")
    return make_body(name, den, arr)


@lru_cache(maxsize=None)
def polygon_denominator() -> int:
    return exact.denominator([c for p in circumscribed(Q(1)) + inscribed(Q(1)) for c in p])


# --- Assembly layout ---------------------------------------------------------------


@dataclass(frozen=True)
class Approach:
    """The closest one mover comes to one other body outside its stops: `d2` mm^2, or
    None when nothing lies within `reach` mm. `crude` says the two floats run along
    different axes, so build.py adds the other body's float to the allowance."""

    other: str
    d2: Q | None
    reach: Q
    triangles: tuple[int, int]
    crude: bool


@dataclass(frozen=True)
class Arrival:
    mover: str
    approaches: tuple[Approach, ...]
    stops: tuple[str, ...]           # the bodies it rests on
    inside: tuple[str, ...]          # bodies a piece of it lies inside, or that lie inside it, with no surface met


@dataclass(frozen=True)
class Seating:
    """A fastener's seat: for a socket head, how many boundary edges of the seat face
    cross the bearing ring and whether the ring lies on that face; for a countersunk head,
    whether the circumscribed cone of the declared countersink is free of material."""

    uncovered: int
    reason: str


@dataclass(frozen=True)
class Layout:
    den: int
    axes: Mapping[str, Axis | None]           # each body's insert axis in the assembly frame
    floats: Mapping[str, Q]                   # hi end, mm
    arrivals: Mapping[str, Arrival]           # by body name, then by fasten id
    gaps: Mapping[tuple[str, str], Approach]
    touching: frozenset[frozenset[str]]
    grips: Mapping[str, tuple[Q, Q | None]]   # fasten id -> (engaged length, depth left below the tip or None)
    seats: Mapping[str, Seating]


_LAYOUTS: dict[int, tuple[Assembly, Layout]] = {}


def layout(asm: Assembly, registry: Registry) -> Layout:
    """The assembly's geometry, memoised on the model's identity."""
    hit = _LAYOUTS.get(id(asm))
    if hit is not None and hit[0] is asm:
        return hit[1]
    result = _layout(asm, registry)
    _LAYOUTS[id(asm)] = (asm, result)
    return result


def _vec(axis: Axis) -> tuple[int, int, int]:
    return axis.value


def _layout(asm: Assembly, registry: Registry) -> Layout:
    parts = {p.body.name: p.body for p in asm.places}
    alw = {n: allowance_hi(p, registry) for n, p in parts.items()}
    alw_screw = {n: allowance_hi(p, registry, against_screw=True) for n, p in parts.items()}
    values = [Q(1, m.body.mesh.scale) for m in asm.places] + [c for m in asm.places for c in m.placement.offset]
    values += [i.travel for i in asm.inserts] + list(alw.values()) + list(alw_screw.values())
    screws = {f.id: _screw(asm, f, registry) for f in asm.fastens}
    for s in screws.values():
        values += [s["head_h"], s["length"], *s["mouth"], *s["tip"]]
    den = exact.denominator(values)
    if asm.fastens:
        den = lcm(den, polygon_denominator() * exact.denominator([s["r"] for s in screws.values()] +
                                                                  [s["head_r"] for s in screws.values()]))
    bodies = {p.body.name: exact.place(Solid(p.body.name, p.body.mesh, p.placement), den) for p in asm.places}
    inserts = {i.body: i for i in asm.inserts}
    axes: dict[str, Axis | None] = {asm.places[0].body.name: None}
    floats: dict[str, Q] = {asm.places[0].body.name: Q(0)}
    pressed = {frozenset((p.pin, p.body)) for p in asm.presses}
    arrivals: dict[str, Arrival] = {}
    touching = set()
    order = [p.body.name for p in asm.places]
    for n, a in enumerate(order):
        for b in order[:n]:
            if exact.touching(bodies[a], bodies[b]):
                touching.add(frozenset((a, b)))
    for n, name in enumerate(order[1:], start=1):
        ins = inserts[name]
        axes[name] = ins.along
        v = _vec(ins.along)
        k = next(m for m in range(3) if v[m])
        mover = bodies[name]
        stops: list[str] = []
        skips: dict[str, set] = {}
        bound = max(floats[o] + alw[o] + alw[name] for o in order[:n])
        for other in order[:n]:
            pad = int((alw[name] + alw[other] + bound + floats[other] + Q(1, 2)) * den) + 1
            level, rests = _level_pairs(mover, bodies[other], k, -v[k], pad)
            skips[other] = level if rests else set()
            if rests or frozenset((name, other)) in pressed:
                stops.append(other)
        floats[name] = max((floats[o] + alw[o] + alw[name] for o in stops), default=Q(0))
        approaches, inside = [], []
        for other in order[:n]:
            if frozenset((name, other)) in pressed:
                continue
            same = axes[other] is None or axes[other].value[k] != 0
            f = floats[name] + (floats[other] if same else Q(0))
            reach = alw[name] + alw[other] + floats[name] + floats[other] + Q(1, 2)
            approaches.append(_approach(mover, bodies[other], other, v, ins.travel, f, reach, den, skips[other], not same))
            if _contained(mover, bodies[other]):
                inside.append(other)
        arrivals[name] = Arrival(name, tuple(approaches), tuple(stops), tuple(inside))
    grips, seats = {}, {}
    for f in asm.fastens:
        s = screws[f.id]
        last, first = f.stack[-1][0], f.stack[0][0]
        f_screw = floats[first] + alw[first]
        axis, back = s["axis"], s["length"] + s["head_h"]
        k = next(m for m in range(3) if axis[m])
        start = tuple(s["mouth"][m] - back * axis[m] for m in range(3))
        approaches = []
        for other in order:
            if other == last:
                continue
            same = axes[other] is None or axes[other].value[k] != 0
            fl = f_screw + (floats[other] if same else Q(0))
            reach = alw_screw[other] + f_screw + floats[other] + Q(1, 2)
            # The screw's path along its own axis is its prism made longer: the shank from
            # where it starts to its tip pushed on by the float, the head from the seat back.
            shank = body_of(f"{f.id}.shank", den, frustum(start, axis, circumscribed(s["r"]), circumscribed(s["r"]),
                                                          back + s["length"] + fl))
            best = _static(shank, bodies[other], other, reach, den, set(), not same)
            if not s["csk"]:
                head = body_of(f"{f.id}.head", den, frustum(s["mouth"], tuple(-c for c in axis), circumscribed(s["head_r"]),
                                                            circumscribed(s["head_r"]), s["head_h"] + back + fl))
                skip = _level_pairs(head, bodies[other], k, -axis[k], int(reach * den) + 1)[0] if other == first else set()
                found = _static(head, bodies[other], other, reach, den, skip, not same)
                if found.d2 is not None and (best.d2 is None or found.d2 < best.d2):
                    best = found
            approaches.append(best)
        arrivals[f.id] = Arrival(f.id, tuple(approaches), (first,), ())
        grips[f.id] = (s["engaged"], s["left"])
        seats[f.id] = _seat(asm, f, s, bodies[first], den, alw[first])
    gaps = {}
    for g in asm.gaps:
        same = axes[g.a] is None or axes[g.b] is None or axes[g.a].value == axes[g.b].value \
            or axes[g.a].value == axes[g.b].opposite.value
        v = (axes[g.b] or axes[g.a] or Axis.TOP).value
        f = floats[g.a] + floats[g.b] if same else floats[g.b]
        reach = g.least + alw[g.a] + alw[g.b] + floats[g.a] + floats[g.b] + Q(1, 2)
        gaps[(g.a, g.b)] = _approach(bodies[g.b], bodies[g.a], g.a, v, Q(0), f, reach, den, set(), not same)
    return Layout(den, axes, floats, arrivals, gaps, frozenset(touching), grips, seats)


def _level_pairs(mover: Body, other: Body, k: int, s: int, pad: int) -> tuple[set, bool]:
    """The triangle pairs (other index, mover index) within `pad` whose facing extremes
    along axis k meet at one level, the mover's wholly behind (direction s), and whether
    any of them touch: the mover rests on `other` when one does. Such pairs lie on the
    contact plane, so the float along the axis moves the mover with it, never into it."""
    level, rests = set(), False
    for i, j in exact.candidates(mover.lo, mover.hi, other.lo, other.hi, pad).tolist():
        t, u = mover.pts[i], other.pts[j]
        if min(s * p[k] for p in t) == max(s * p[k] for p in u):
            level.add((j, i))
            rests = rests or exact.tri_tri2(t, u) == 0
    return level, rests


def _static(mover: Body, other: Body, name: str, reach: Q, den: int, skip: set, crude: bool) -> Approach:
    found = exact.nearest(other, mover, int(reach * den) + 1, skip=(lambda i, j: (i, j) in skip) if skip else None)
    return Approach(name, None if found.d2 is None else found.d2 / den ** 2, reach, (found.j, found.i), crude)


def _approach(mover: Body, other: Body, name: str, v, travel: Q, float_: Q, reach: Q, den: int, skip: set,
              crude: bool) -> Approach:
    """The mover swept from `float_` past its place back to `travel + float_` before it,
    against the other body; pairs in `skip` (mover index, other index) are its stops."""
    ahead = tuple(int(c * float_ * den) for c in v)
    start = make_body(mover.name, den, mover.tris + np.array(ahead, dtype=np.int64)) if float_ else mover
    back = tuple(-int(c * (travel + 2 * float_) * den) for c in v)
    within = int(reach * den) + 1
    found = exact.nearest(other, start, within, skip=(lambda i, j: (i, j) in skip) if skip else None,
                          sweep=back if any(back) else None)
    d2 = None if found.d2 is None else found.d2 / den ** 2
    return Approach(name, d2, reach, (found.j, found.i), crude)


def _contained(a: Body, b: Body) -> bool:
    """A vertex of a lies inside b, or one of b inside a, decided at a vertex off the
    other's surface. Only called where the bodies' nearest approach is tested too, so a
    vertex on a surface is a contact that the approach already reports."""
    for x, y in ((a, b), (b, a)):
        for t in x.pts[: min(len(x.pts), 64)]:
            got = exact.inside(t[0], y)
            if got is not None:
                if got:
                    return True
                break
    return False


def _placed_hole(asm: Assembly, body: str, hole: Hole) -> tuple[Point, tuple[int, int, int]]:
    placement = asm.place(body).placement
    return placement.apply(hole.at), placement.turn.apply(hole.along.value)


def _screw(asm: Assembly, f: Fasten, registry: Registry) -> dict:
    """The screw's axis, mouth, tip, engaged length and the depth its tip leaves, mm."""
    part = registry.parts[f.screw]
    hi = {p: part.props[p].value.hi * MM for p in ("d", "head_d", "head_h", "length")}
    last_body, last_id = f.stack[-1]
    first_body, first_id = f.stack[0]
    last = asm.hole(last_body, last_id)
    c_last, axis = _placed_hole(asm, last_body, last)
    c_first, axis_first = _placed_hole(asm, first_body, asm.hole(first_body, first_id))
    level = sum((c_first[m] - c_last[m]) * axis[m] for m in range(3))
    mouth = tuple(c_last[m] + level * axis[m] for m in range(3))
    tip = tuple(mouth[m] + hi["length"] * axis[m] for m in range(3))
    engaged = hi["length"] + level
    left = None if last.depth is None else last.depth - engaged
    return {"axis": axis, "aligned": axis == axis_first, "mouth": mouth, "tip": tip, "r": hi["d"] / 2,
            "head_r": hi["head_d"] / 2, "head_h": hi["head_h"], "length": hi["length"], "csk": "csk_angle" in part.props,
            "engaged": engaged, "left": left}


def _seat(asm: Assembly, f: Fasten, s: dict, body: Body, den: int, a: Q) -> Seating:
    """A socket head bears on a ring from the first hole's radius to the head's, which must
    lie on faces of the first body facing back along the screw. A countersunk head needs
    the hole's countersink."""
    first_body, first_id = f.stack[0]
    hole = asm.hole(first_body, first_id)
    if not s["aligned"]:
        return Seating(1, "the holes of the stack run along different axes")
    k, i, j = _frame(s["axis"])
    if s["csk"]:
        if hole.countersink is None:
            return Seating(1, f"{first_body}.{first_id} declares no countersink for a countersunk head")
        return Seating(0, "")
    level = int(s["mouth"][k] * den)
    faces = exact.faces_toward(body, k, -s["axis"][k], level)
    edges = exact.boundary_edges(body, faces)
    centre = (s["mouth"][i] * den, s["mouth"][j] * den)
    if s["head_r"] - a <= hole.diameter / 2 + a:
        return Seating(1, f"the head, {float(2 * s['head_r']):g} mm across, can pass the {float(hole.diameter):g} mm hole "
                          f"at the tolerance's extreme")
    r_in2, r_out2 = ((hole.diameter / 2 + a) * den) ** 2, ((s["head_r"] + a) * den) ** 2
    crossing = 0
    for p, q in edges:
        d_min = exact.point_seg2((centre[0], centre[1], 0), (p[i], p[j], 0), (q[i], q[j], 0))
        d_max = max((p[i] - centre[0]) ** 2 + (p[j] - centre[1]) ** 2, (q[i] - centre[0]) ** 2 + (q[j] - centre[1]) ** 2)
        if d_min < r_out2 and d_max > r_in2:
            crossing += 1
    probe = (centre[0] + (hole.diameter / 2 + s["head_r"]) / 2 * den + a * den, centre[1])
    covered = any(_in_tri2(probe, body.pts[t], i, j) for t in faces)
    if crossing or not covered:
        return Seating(crossing + (0 if covered else 1),
                       f"the head's bearing ring, {float(hole.diameter + 2 * a):g} to {float(2 * (s['head_r'] + a)):g} mm across, "
                       f"is not all on a face of {first_body} facing the head ({crossing} face edges cross it)")
    return Seating(0, "")


def _in_tri2(p, t, i, j) -> bool:
    s = [(t[(m + 1) % 3][i] - t[m][i]) * (p[1] - t[m][j]) - (t[(m + 1) % 3][j] - t[m][j]) * (p[0] - t[m][i]) for m in range(3)]
    return all(x >= 0 for x in s) or all(x <= 0 for x in s)


# --- Part facts ------------------------------------------------------------------------


@dataclass(frozen=True)
class HoleFacts:
    """For one declared hole: whether its axis runs through empty space (`open`), the
    least radius of material around its axis over its depth (`free2`, mm^2), the least
    radius of material outside the hole wall over an insert's length (`wall2`, mm^2, or
    None), and for a countersink whether its circumscribed cone is free (`sink`)."""

    open: bool
    free2: Q
    wall2: Q | None
    sink: bool | None


def hole_facts(part: PartDesign, hole: Hole, a_hi: Q, insert_length: Q | None) -> HoleFacts:
    mesh = part.mesh
    body = exact.body_of_mesh(part.name, mesh)
    den = mesh.scale
    axis = hole.along.value
    k, i, j = _frame(axis)
    s = axis[k]
    z0 = hole.at[k]
    lo, hi = mesh.bounds()
    far = hi[k] if s > 0 else lo[k]
    z1 = z0 + s * hole.depth if hole.depth is not None else far
    mid = [hole.at[0], hole.at[1], hole.at[2]]
    mid[k] = (z0 + z1) / 2
    probe = tuple(int(c * den) for c in mid) if all(c * den == int(c * den) for c in mid) else None
    inside = exact.inside(probe, body) if probe is not None else None
    if probe is None:
        inside = _inside_scaled(body, mid)
    free2 = _radial2(body, hole.at, k, i, j, z0, z1, None, den)
    wall2 = None
    if insert_length is not None:
        zl = z0 + s * insert_length
        wall2 = _radial2(body, hole.at, k, i, j, z0, zl, (hole.diameter / 2 + a_hi) ** 2, den)
    sink = None
    if hole.countersink is not None:
        top = hole.countersink / 2 - a_hi
        bottom = hole.diameter / 2 - a_hi
        if bottom <= 0 or top <= bottom:
            sink = False
        else:
            cone = frustum(hole.at, axis, circumscribed(top), circumscribed(bottom), top - bottom)
            d = exact.denominator([c for t in cone for p in t for c in p], [Q(1, den)])
            scaled = exact.make_body(part.name, d, body.tris * (d // den))
            near = exact.nearest(scaled, body_of("sink", d, cone), 1)
            sink = near.d2 is None
    return HoleFacts(inside is False, free2, wall2, sink)


def flat(part: PartDesign) -> tuple[Q, str | None]:
    """The part's thickness along z in mm, and why it is not a flat profile of that
    thickness, or None when it is. A closed surface whose every vertex lies on its two
    level faces and whose every other face is upright is a prism along z: faces in two
    upright planes meet only on upright edges, so every cross-section is the same."""
    mesh = part.mesh
    z = mesh.vertices[:, 2]
    lo, hi = int(z.min()), int(z.max())
    thickness = Q(hi - lo, mesh.scale)
    off = np.nonzero((z != lo) & (z != hi))[0]
    if len(off):
        at = tuple(float(c) for c in mesh.point(int(off[0])))
        return thickness, f"vertex {at} lies between its faces at z {float(Q(lo, mesh.scale)):g} and {float(Q(hi, mesh.scale)):g} mm"
    t = mesh.vertices[mesh.triangles].astype(object)
    e1, e2 = t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]
    upright = (e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) == 0
    level = (t[:, 0, 2] == t[:, 1, 2]) & (t[:, 1, 2] == t[:, 2, 2])
    slant = np.nonzero(~(upright | level))[0]
    if len(slant):
        return thickness, f"triangle {int(slant[0])} slopes between its faces"
    return thickness, None


@dataclass(frozen=True)
class Bridge:
    """One connected downward-facing level region above the bed, printed over air. Each
    boundary edge is anchored when the face across it falls below it, and free when it
    rises. `width` is the region's narrower box side; `far2` is the squared distance
    from `witness`, a point of the region, to its nearest boundary edge, so every
    straight span through the witness is at least 2 sqrt(far2) long. All in mm."""

    level: Q
    width: Q
    free: bool
    witness: tuple[Q, Q]
    far2: Q


def bridges(part: PartDesign) -> tuple[Bridge, ...]:
    """Every region of downward-facing level triangles above the mesh's lowest level."""
    mesh = part.mesh
    v, tri = mesh.vertices, mesh.triangles
    z = v[:, 2]
    t = v[tri].astype(object)
    e1, e2 = t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]
    nz = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    level = (t[:, 0, 2] == t[:, 1, 2]) & (t[:, 1, 2] == t[:, 2, 2])
    down = [int(i) for i in np.nonzero(level & (nz < 0) & (t[:, 0, 2] > int(z.min())))[0]]
    owner = {(int(tri[i][k]), int(tri[i][(k + 1) % 3])): i for i in range(len(tri)) for k in range(3)}
    root = {i: i for i in down}

    def find(i: int) -> int:
        while root[i] != i:
            root[i] = root[root[i]]
            i = root[i]
        return i

    for i in down:
        for k in range(3):
            j = owner[(int(tri[i][(k + 1) % 3]), int(tri[i][k]))]
            if j in root:
                root[find(i)] = find(j)
    regions: dict[int, list[int]] = {}
    for i in down:
        regions.setdefault(find(i), []).append(i)
    s = mesh.scale
    out = []
    for members in regions.values():
        inner = set(members)
        lvl = int(z[tri[members[0]][0]])
        edges, free, mids = [], False, []
        for i in members:
            for k in range(3):
                a, b = int(tri[i][k]), int(tri[i][(k + 1) % 3])
                j = owner[(b, a)]
                if j in inner:
                    mids.append(((Q(int(v[a][0]) + int(v[b][0]), 2)), Q(int(v[a][1]) + int(v[b][1]), 2)))
                    continue
                edges.append((a, b))
                c = next(int(x) for x in tri[j] if int(x) not in (a, b))
                free = free or int(z[c]) >= lvl
        xy = v[[p for i in members for p in tri[i]]][:, :2]
        (x0, y0), (x1, y1) = xy.min(axis=0), xy.max(axis=0)
        width = Q(int(min(x1 - x0, y1 - y0)), s)
        points = mids + [(Q(sum(int(v[p][0]) for p in tri[i]), 3), Q(sum(int(v[p][1]) for p in tri[i]), 3)) for i in members]
        segs = np.array([[v[a][0], v[a][1], v[b][0], v[b][1]] for a, b in edges], dtype=float)
        best = max(points, key=lambda p: _seg_dist2(np.array([float(p[0]), float(p[1])]), segs))
        far2 = min(exact.point_seg2((best[0], best[1], 0), (int(v[a][0]), int(v[a][1]), 0), (int(v[b][0]), int(v[b][1]), 0))
                   for a, b in edges)
        out.append(Bridge(Q(lvl, s), width, free, (best[0] / s, best[1] / s), far2 / (s * s)))
    return tuple(out)


def _seg_dist2(p: np.ndarray, segs: np.ndarray) -> float:
    """The least squared distance from p to the segments, in floats; it only picks which
    witness to try, and the exact distance from that witness is what the rule states."""
    a, d = segs[:, :2], segs[:, 2:] - segs[:, :2]
    t = np.clip(((p - a) * d).sum(axis=1) / np.maximum((d * d).sum(axis=1), 1e-300), 0, 1)
    return float((((a + d * t[:, None]) - p) ** 2).sum(axis=1).min())


def _inside_scaled(body: Body, point) -> bool | None:
    d = exact.denominator(point, [Q(1, body.den)])
    scaled = exact.make_body(body.name, d, body.tris * (d // body.den))
    return exact.inside(tuple(int(c * d) for c in point), scaled)


def _radial2(body: Body, at: Point, k: int, i: int, j: int, z0: Q, z1: Q, exclude_r2: Q | None, den: int) -> Q:
    """The least squared distance (mm^2) from the line through `at` along axis k to any
    triangle's part between levels z0 and z1, skipping triangles lying in either end
    plane and, with `exclude_r2`, triangles whose corners all lie within that squared
    radius of the line (the hole's own wall)."""
    lo_z, hi_z = min(z0, z1) * den, max(z0, z1) * den
    c = (at[i] * den, at[j] * den)
    best = None
    near = np.flatnonzero((body.hi[:, k] >= floor(lo_z)) & (body.lo[:, k] <= ceil(hi_z)))
    for idx in near.tolist():
        t = body.pts[idx]
        zs = [p[k] for p in t]
        if all(z == lo_z for z in zs) or all(z == hi_z for z in zs):
            continue
        if exclude_r2 is not None and all((p[i] - c[0]) ** 2 + (p[j] - c[1]) ** 2 <= exclude_r2 * den * den for p in t):
            continue
        poly = _clip_slab([tuple(Q(x) for x in p) for p in t], k, lo_z, hi_z)
        if not poly:
            continue
        d = _poly_dist2([(p[i], p[j]) for p in poly], c)
        best = d if best is None or d < best else best
        if best == 0:
            break
    return Q(10 ** 12) if best is None else best / den ** 2


def _clip_slab(poly, k, lo, hi):
    for bound, sign in ((lo, 1), (hi, -1)):
        out = []
        for m in range(len(poly)):
            p, q = poly[m], poly[(m + 1) % len(poly)]
            sp, sq = sign * (p[k] - bound), sign * (q[k] - bound)
            if sp >= 0:
                out.append(p)
            if (sp > 0 > sq) or (sp < 0 < sq):
                r = sp / (sp - sq)
                out.append(tuple(p[n] + r * (q[n] - p[n]) for n in range(3)))
        poly = out
        if not poly:
            return []
    return poly


def _poly_dist2(poly, c) -> Q:
    n = len(poly)
    signs = set()
    for m in range(n):
        (x0, y0), (x1, y1) = poly[m], poly[(m + 1) % n]
        cr = (x1 - x0) * (c[1] - y0) - (y1 - y0) * (c[0] - x0)
        signs.add((cr > 0) - (cr < 0))
    if n >= 3 and not ({1, -1} <= signs) and signs != {0}:
        return Q(0)
    best = None
    for m in range(n):
        (x0, y0), (x1, y1) = poly[m], poly[(m + 1) % n]
        d = exact.point_seg2((c[0], c[1], 0), (x0, y0, 0), (x1, y1, 0))
        best = d if best is None or d < best else best
    return best
