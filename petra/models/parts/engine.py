"""Every geometric fact the parts rules state, measured exactly once per model. Trusted.

The engine reads the lowered models and the registry's hi ends, so it knows how far to
search, and returns exact rationals in millimetres. build.py states each fact as a design
value beside the tolerance premises it is compared with, so every verdict names both.

The assembly model (docs/parts.md, "Fit under tolerance"):

- Each body's true surface lies within its allowance `a` of its nominal surface: the
  profile tolerance plus a finish's buildup. Against a screw a printed body's allowance
  also holds half its hole shrink, because holes come out smaller.
- Bodies go in in place-line order. The first is the base; every other arrives along its
  insert axis from beyond every body placed before it, so its start is outside them, and
  stops on the faces it touches there that lie wholly ahead of its own along the travel
  (its stops). A face is a flat region of triangles joined edge to edge, so how a face
  is split into triangles does not change what stops. Its position along that axis then
  floats by F = max over its stops of (F_stop + a_stop + a_self), and not at all across it.
- A mover's path is swept from its start to its place and on by its float, back by it
  too. Every triangle pair but its stops must keep apart by the two allowances, and by
  the other body's float when the two floats run along different axes. Each edge-joined
  piece of each body is probed for lying inside the other.
- A screw is the circumscribed 32-sided prism of its shank at its greatest diameter and
  length, with its head's prism. Its axis is the hole its thread enters, which may sit
  off nominal by that body's allowance; its head sits at the first hole's mouth, or below
  it in a countersink. It arrives from beyond every body. It may overlap the last body
  only past that hole's mouth, and no other screw.
- A press pin sits in its hole when it crosses the hole's slab, holds the hole's axis,
  and the hole's wall lies inside it; its interference is read from the two meshes.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from math import ceil, floor, isqrt, lcm
from typing import Callable, Mapping

import numpy as np

from ...registry import Registry
from . import exact
from .exact import Body, make_body
from .lower import Assembly, Fasten, Hole, PartDesign, Press
from .mesh import Mesh, Point, pieces
from .space import Axis, Placement, Solid

Q = Fraction
MM = 1000                       # registry metres to millimetres
FAR = Q(10 ** 12)               # mm^2 that stands for nothing found


# --- Allowances, read at their hi ends ---------------------------------------------


def span(mesh: Mesh) -> Q:
    """An upper bound on the mesh's largest dimension, mm: the diagonal of its box, rounded up."""
    lo, hi = mesh.bounds()
    return root_up(sum((h - l) ** 2 for l, h in zip(lo, hi)))


def tolerance_hi(part: PartDesign, registry: Registry) -> Q | None:
    """The part's profile tolerance (mm, hi end), or None when neither a tolerance line
    nor a process preset gives one. A preset with a tolerance rate holds the larger of its
    floor and the rate times the part's span."""
    if part.tolerance is not None:
        return part.tolerance.range.value.hi * MM
    if part.preset is not None and "tolerance" in registry.processes[part.preset].props:
        props = registry.processes[part.preset].props
        t = props["tolerance"].value.hi * MM
        if "tolerance_rate" in props:
            t = max(t, props["tolerance_rate"].value.hi * span(part.mesh))
        return t
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


def root_up(x: Q, scale: int = 10 ** 9) -> Q:
    """A rational at least sqrt(x), within 1/scale of it."""
    n = ceil(x * scale * scale)
    r = isqrt(n)
    return Q(r if r * r == n else r + 1, scale)


def root_down(x: Q, scale: int = 10 ** 9) -> Q:
    """A rational at most sqrt(x), within 1/scale of it."""
    return Q(isqrt(floor(x * scale * scale)), scale)


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
    if any(c * den != int(c * den) for t in tris for p in t for c in p):
        raise ValueError("the denominator does not hold the polygon")
    return make_body(name, den, [[[int(c * den) for c in p] for p in t] for t in tris])


@lru_cache(maxsize=None)
def polygon_denominator() -> int:
    return exact.denominator([c for p in circumscribed(Q(1)) + inscribed(Q(1)) for c in p])


# --- Holes, read from the mesh -------------------------------------------------------


@dataclass(frozen=True)
class Bore:
    """A hole's profile over a slab along its axis, mm^2. `lo2` is the least squared
    distance from the axis to any surface in the slab (FAR when none). The wall is the
    smallest set of surfaces nearest the axis that no other surface comes inside: `hi2` is
    its greatest squared distance from the axis when the material around it is solid, so
    the hole lies within that radius, else None; `out2` is the least squared distance of
    any surface beyond the wall (None when there is none), so the material around the wall
    reaches that far. `open` says the axis runs through empty space. `wall` holds the
    wall's triangle indices. Triangles lying in either end plane are left out."""

    lo2: Q
    hi2: Q | None
    out2: Q | None
    open: bool
    wall: frozenset[int]


def bore(body: Body, at: Point, k: int, z0: Q, z1: Q) -> Bore:
    """The hole about the line through `at` (mm) along axis k, between levels z0 and z1.

    Each triangle is clipped to the slab and measured by its least and greatest squared
    distance from the line. The wall grows from the nearest triangle: every triangle that
    comes nearer than the wall's farthest corner joins it, until none does. Then no surface
    lies between the wall's farthest corner and the nearest surface beyond it, so that
    shell is all solid or all empty, and one probe inside it decides which."""
    den = body.den
    i, j = (k + 1) % 3, (k + 2) % 3
    lo_z, hi_z = min(z0, z1) * den, max(z0, z1) * den
    c = (at[i] * den, at[j] * den)
    mid = list(at)
    mid[k] = (z0 + z1) / 2
    axis_open = _inside_scaled(body, mid) is False
    polys = []
    for idx in np.flatnonzero((body.hi[:, k] >= floor(lo_z)) & (body.lo[:, k] <= ceil(hi_z))).tolist():
        t = body.pts[idx]
        zs = [p[k] for p in t]
        if all(z == lo_z for z in zs) or all(z == hi_z for z in zs):
            continue
        poly = _clip_slab([tuple(Q(x) for x in p) for p in t], k, lo_z, hi_z)
        if not poly:
            continue
        flat2 = [(p[i], p[j]) for p in poly]
        polys.append((idx, _poly_dist2(flat2, c), max((x - c[0]) ** 2 + (y - c[1]) ** 2 for x, y in flat2)))
    if not polys:
        return Bore(FAR, None, None, axis_open, frozenset())
    lo2 = min(d for _, d, _ in polys)
    h = max(m for _, d, m in polys if d <= lo2)
    while True:
        grown = max(m for _, d, m in polys if d <= h)
        if grown == h:
            break
        h = grown
    wall = frozenset(idx for idx, d, _ in polys if d <= h)
    beyond = [d for _, d, _ in polys if d > h]
    out2 = min(beyond) if beyond else None
    rho = _between(h, out2)
    solid = False
    if rho is not None:
        probe = list(mid)
        probe[i] = at[i] + rho / den
        solid = _inside_scaled(body, probe) is True
    scale = den * den
    return Bore(lo2 / scale, h / scale if solid else None, None if out2 is None else out2 / scale,
                lo2 > 0 and axis_open, wall)


def _between(lo2: Q, hi2: Q | None) -> Q | None:
    """A rational r with lo2 < r^2 < hi2 (hi2 None: no upper limit), or None."""
    for bits in range(0, 96, 4):
        s = 1 << bits
        r = Q(isqrt(floor(lo2 * s * s)) + 1, s)
        if hi2 is None or r * r < hi2:
            return r
    return None


def axis_run(body: Body, at: Point, axis: tuple[int, int, int]) -> Q | None:
    """How far the axis runs from `at` (mm) along `axis` before it enters material: the
    least distance to a triangle it meets that faces back toward `at`, or that lies along
    the axis itself. None when it meets none."""
    den = body.den
    k, i, j = _frame(axis)
    s = axis[k]
    c = (at[i] * den, at[j] * den)
    z0 = at[k] * den
    best = None
    hit = np.flatnonzero((body.lo[:, i] <= ceil(c[0])) & (body.hi[:, i] >= floor(c[0])) &
                         (body.lo[:, j] <= ceil(c[1])) & (body.hi[:, j] >= floor(c[1])))
    for idx in hit.tolist():
        t = body.pts[idx]
        n = exact.normal(t)
        if s * n[k] > 0:
            continue
        if n[k] == 0:
            if n[i] * (c[0] - t[0][i]) + n[j] * (c[1] - t[0][j]) != 0 or not _on_segment2(c, t, i, j):
                continue
            ahead = [s * (p[k] - z0) for p in t]
            if max(ahead) < 0:
                continue
            d = max(Q(0), Q(min(ahead)))
        else:
            if not _in_tri2(c, t, i, j):
                continue
            z = t[0][k] - Q(n[i] * (c[0] - t[0][i]) + n[j] * (c[1] - t[0][j]), n[k])
            d = s * (z - z0)
            if d < 0:
                continue
        best = d if best is None or d < best else best
    return None if best is None else Q(best) / den


def _on_segment2(c, t, i, j) -> bool:
    """c lies within the box of t's corners in coordinates i and j (t projects to a segment)."""
    return (min(p[i] for p in t) <= c[0] <= max(p[i] for p in t)) and (min(p[j] for p in t) <= c[1] <= max(p[j] for p in t))


def approach_clear(body: Body, at: Point, axis: tuple[int, int, int], r: Q, reach: Q) -> Q | None:
    """The least squared distance (mm^2) from the circumscribed prism of radius r, running
    from the hole's mouth `at` back against `axis` to beyond the body, to the body's
    material on that side of the mouth's plane; None when nothing comes within `reach` mm.
    Triangles are clipped to that side, and what lies in the mouth's plane itself (the face
    round the mouth, the rim of the hole's wall) is left out, so material any thickness
    before the mouth is found."""
    den = body.den
    k, i, j = _frame(axis)
    s = axis[k]
    lo, hi = body.bounds()
    far = hi[k] if s < 0 else lo[k]
    length = abs(Q(far, den) - at[k]) + reach + 1
    prism = frustum(at, tuple(-c for c in axis), circumscribed(r), circumscribed(r), length)
    pts = [tuple(c * den for c in p) for t in prism for p in t]
    plo = [min(p[m] for p in pts) - reach * den for m in range(3)]
    phi = [max(p[m] for p in pts) + reach * den for m in range(3)]
    mouth = at[k] * den
    best = None
    near = np.flatnonzero(np.all((body.hi >= np.array([floor(x) for x in plo])) &
                                 (body.lo <= np.array([ceil(x) for x in phi])), axis=1))
    tris = [tuple(tuple(c * den for c in p) for p in t) for t in prism]
    for idx in near.tolist():
        t = [tuple(Q(x) for x in p) for p in body.pts[idx]]
        bound = (mouth - 10 ** 30, mouth) if s > 0 else (mouth, mouth + 10 ** 30)
        poly = _clip_slab(t, k, *bound)
        if len(poly) < 3 or all(p[k] == mouth for p in poly):
            continue
        for m in range(1, len(poly) - 1):
            piece = (poly[0], poly[m], poly[m + 1])
            if exact.normal(piece) == (0, 0, 0):
                continue
            for u in tris:
                d = exact.tri_tri2(piece, u)
                if d <= (reach * den) ** 2 and (best is None or d < best):
                    best = d
                if best == 0:
                    return Q(0)
    return None if best is None else best / (den * den)


def sink_depth(part: PartDesign, hole: Hole, head_lo: Q, a: Q) -> Q | None:
    """How deep below the mouth the top of a 90 degree countersunk head at least `head_lo`
    mm across can sink, read from the mesh: the countersink is cut into eight slabs of
    its declared depth and on below it, and the head's top cannot enter the first slab
    whose hole, grown by the allowance `a`, is narrower than the head. None when no slab
    within twice the declared depth stops it."""
    body = exact.body_of_mesh(part.name, part.mesh)
    axis = hole.along.value
    k = _frame(axis)[0]
    s = axis[k]
    depth = (hole.countersink - hole.diameter) / 2 if hole.countersink is not None else hole.diameter
    step = depth / 8
    for m in range(16):
        b = bore(body, hole.at, k, hole.at[k] + s * step * m, hole.at[k] + s * step * (m + 1))
        if b.hi2 is not None and root_up(b.hi2) + a < head_lo / 2:
            return step * m
    return None


@dataclass(frozen=True)
class HoleFacts:
    """For one declared hole: whether its axis runs through empty space (`open`), the
    least squared distance of material from its axis over its depth (`free2`, mm^2), and
    for a countersink whether its circumscribed cone is free (`sink`)."""

    open: bool
    free2: Q
    sink: bool | None


def hole_slab(part: PartDesign, hole: Hole, length: Q | None) -> tuple[int, Q, Q]:
    """(k, z0, z1): the hole's axis coordinate and the slab from its mouth `length` mm in,
    or by its declared depth, or to the mesh's far side."""
    axis = hole.along.value
    k = _frame(axis)[0]
    s = axis[k]
    z0 = hole.at[k]
    if length is not None:
        return k, z0, z0 + s * length
    lo, hi = part.mesh.bounds()
    return k, z0, z0 + s * hole.depth if hole.depth is not None else (hi[k] if s > 0 else lo[k])


def hole_bore(part: PartDesign, hole: Hole, length: Q | None) -> Bore:
    key = (id(part.mesh), hole, length)
    hit = _BORES.get(key)
    if hit is not None and hit[0] is part.mesh:
        return hit[1]
    k, z0, z1 = hole_slab(part, hole, length)
    found = bore(exact.body_of_mesh(part.name, part.mesh), hole.at, k, z0, z1)
    _BORES[key] = (part.mesh, found)
    return found


_BORES: dict = {}


MOUTH = Q(1, 1000)              # mm: the slab below a hole's mouth that a head is read against


def mouth_bore(part: PartDesign, hole: Hole) -> Bore:
    """The hole in the slab MOUTH mm deep below its mouth, where a head meets it."""
    return hole_bore(part, hole, MOUTH)


def hole_run(part: PartDesign, hole: Hole) -> Q | None:
    """How far the hole's axis runs from its mouth before it meets material (mm), or None."""
    return axis_run(exact.body_of_mesh(part.name, part.mesh), hole.at, hole.along.value)


def hole_facts(part: PartDesign, hole: Hole, a_hi: Q) -> HoleFacts:
    mesh = part.mesh
    den = mesh.scale
    axis = hole.along.value
    found = hole_bore(part, hole, None)
    sink = None
    if hole.countersink is not None:
        top = hole.countersink / 2 - a_hi
        bottom = hole.diameter / 2 - a_hi
        if bottom <= 0 or top <= bottom:
            sink = False
        else:
            body = exact.body_of_mesh(part.name, mesh)
            cone = frustum(hole.at, axis, circumscribed(top), circumscribed(bottom), top - bottom)
            d = exact.denominator([c for t in cone for p in t for c in p], [Q(1, den)])
            near = exact.nearest(exact.scaled(body, d // den), body_of("sink", d, cone), 1)
            sink = near.d2 is None
    return HoleFacts(found.open, found.lo2, sink)


# --- Assembly layout ---------------------------------------------------------------


@dataclass(frozen=True)
class Approach:
    """The closest one mover comes to one other body outside its stops: `d2` mm^2, or
    None when nothing lies within `reach` mm. `crude` says the two floats run along
    different axes, so build.py adds the other body's float to the allowance. `screw`
    names the other screw when the other body is one, whose axis shift adds too."""

    other: str
    d2: Q | None
    reach: Q
    triangles: tuple[int, int]
    crude: bool
    screw: str | None = None


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
    whether the mesh's countersink stops the head."""

    uncovered: int
    reason: str


@dataclass(frozen=True)
class Grip:
    """A fastener's thread, mm: the engaged length at its least and greatest (None when
    the mesh's countersink does not stop the head), how far the last hole's axis runs from
    its mouth before it meets material (None: through), the length of thread the bore was
    read over, and the bore there for a tap or form hole."""

    engaged_lo: Q
    engaged_hi: Q | None
    run: Q | None
    zone: Q
    bore: Bore | None


@dataclass(frozen=True)
class PressFit:
    """A press, read from the two meshes over the length where the pin meets the hole:
    why the pin does not sit in the hole ("" when it does), the least squared distance
    from the hole's wall to the pin's surface (`grip2`), the greatest squared radius of the
    pin there (`pin2`) and the least of the hole (`hole2`), mm^2."""

    seated: str
    grip2: Q
    pin2: Q
    hole2: Q
    wall: frozenset[int]
    core: frozenset[int]             # the pin's triangles within the fit's reach of the axis


@dataclass(frozen=True)
class Layout:
    den: int
    axes: Mapping[str, Axis | None]           # each body's insert axis in the assembly frame
    floats: Mapping[str, Q]                   # hi end, mm
    arrivals: Mapping[str, Arrival]           # by body name, then by fasten id
    gaps: Mapping[tuple[str, str], Approach]
    touching: frozenset[frozenset[str]]
    grips: Mapping[str, Grip]
    seats: Mapping[str, Seating]
    presses: Mapping[str, PressFit]
    clears: Mapping[str, Q | None]            # fasten id -> squared distance of the last body's material before its mouth
    screws: Mapping[str, tuple]               # fasten id -> (the screw's measures, its axis shift, its float), mm


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
    screws = {f.id: _screw(asm, f, registry, alw) for f in asm.fastens}
    values = [Q(1, m.body.mesh.scale) for m in asm.places] + [c for m in asm.places for c in m.placement.offset]
    values += [i.travel for i in asm.inserts] + list(alw.values()) + list(alw_screw.values())
    for s in screws.values():
        values += [s["head_h"], s["reach"], *s["mouth"]]
    values += [c for p in asm.presses for c in _placed_hole(asm, p.body, asm.hole(p.body, p.hole))[0]]
    den = exact.denominator(values)
    if asm.fastens:
        den = lcm(den, polygon_denominator() * exact.denominator([s["r"] for s in screws.values()] +
                                                                  [s["head_r"] for s in screws.values()]))
    bodies = {p.body.name: exact.place(Solid(p.body.name, p.body.mesh, p.placement), den) for p in asm.places}
    owners = {p.body.name: pieces(p.body.mesh) for p in asm.places}
    inserts = {i.body: i for i in asm.inserts}
    axes: dict[str, Axis | None] = {asm.places[0].body.name: None}
    floats: dict[str, Q] = {asm.places[0].body.name: Q(0)}
    presses = {p.id: _press(asm, p, bodies, alw, den) for p in asm.presses}
    pressed = {frozenset((p.pin, p.body)): p for p in asm.presses}
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
            press = pressed.get(frozenset((name, other)))
            if rests or (press is not None and not presses[press.id].seated):
                stops.append(other)
        floats[name] = max((floats[o] + alw[o] + alw[name] for o in stops), default=Q(0))
        travel = max(ins.travel, _out(mover, [bodies[o] for o in order[:n]], v, den))
        approaches, inside = [], []
        for other in order[:n]:
            same = axes[other] is None or axes[other].value[k] != 0
            f = floats[name] + (floats[other] if same else Q(0))
            reach = alw[name] + alw[other] + floats[name] + floats[other] + Q(1, 2)
            skip = _skipper(skips[other], name, other, pressed, presses)
            approaches.append(_approach(mover, bodies[other], other, v, travel, f, reach, den, skip, not same))
            press = pressed.get(frozenset((name, other)))
            fit = presses[press.id] if press is not None else None
            core_m = fit.core if fit is not None and press.pin == name else fit.wall if fit is not None else frozenset()
            core_o = fit.core if fit is not None and press.pin == other else fit.wall if fit is not None else frozenset()
            if _contained(mover, bodies[other], owners[name], owners[other], core_m, core_o):
                inside.append(other)
        arrivals[name] = Arrival(name, tuple(approaches), tuple(stops), tuple(inside))
    grips, seats, clears, placed = {}, {}, {}, {}
    paths = {f.id: (alw_screw[f.stack[-1][0]], floats[f.stack[0][0]] + alw[f.stack[0][0]]) for f in asm.fastens}
    for f in asm.fastens:
        s = screws[f.id]
        last, first = f.stack[-1][0], f.stack[0][0]
        e, f_screw = paths[f.id]
        axis = s["axis"]
        k = next(m for m in range(3) if axis[m])
        u = axis[k]
        low = min((int(b.lo[:, k].min()) if u > 0 else -int(b.hi[:, k].max())) for b in bodies.values())
        mouth_u = u * s["mouth"][k]
        back = max(s["reach"] + s["head_h"], mouth_u - Q(low, den) + 1)
        start = tuple(s["mouth"][m] - back * axis[m] for m in range(3))
        approaches = []
        for other in order:
            same = axes[other] is None or axes[other].value[k] != 0
            fl = f_screw + (floats[other] if same else Q(0))
            reach = alw_screw[other] + e + f_screw + floats[other] + Q(1, 2)
            # The screw's path along its own axis is its prism made longer: the shank from
            # beyond every body to its tip pushed on by the float, the head from the seat back.
            shank = body_of(f"{f.id}.shank", den, frustum(start, axis, circumscribed(s["r"]), circumscribed(s["r"]),
                                                          back + s["reach"] + fl))
            head = body_of(f"{f.id}.head", den, frustum(s["mouth"], tuple(-c for c in axis), circumscribed(s["head_r"]),
                                                        circumscribed(s["head_r"]), s["head_h"] + back + fl))
            best = Approach(other, None, reach, (-1, -1), not same)
            if other != last:
                best = _static(shank, bodies[other], other, reach, den, set(), not same)
            if other == first:
                level = int(s["mouth"][k] * den)
                skip = (lambda i, j, lv=level: _in_plane(bodies[first], i, k, lv, -u)) if s["csk"] else \
                    _level_pairs(head, bodies[other], k, -u, int(reach * den) + 1)[0]
            else:
                skip = set()
            found = _static(head, bodies[other], other, reach, den, skip, not same)
            if found.d2 is not None and (best.d2 is None or found.d2 < best.d2):
                best = found
            approaches.append(best)
        placed[f.id] = (s, e, f_screw)
        # Against a screw fastened before it, its path; against one fastened after, where it
        # ends up, so two screws that end up crossing fail both.
        path = (body_of(f"{f.id}.shank", den, frustum(start, axis, circumscribed(s["r"]), circumscribed(s["r"]),
                                                     back + s["reach"] + f_screw)),
                body_of(f"{f.id}.head", den, frustum(s["mouth"], tuple(-c for c in axis), circumscribed(s["head_r"]),
                                                    circumscribed(s["head_r"]), s["head_h"] + back + f_screw)))
        end = (_placed_screw(s, den, f"{f.id}.shank", f_screw), _placed_screw(s, den, f"{f.id}.head", f_screw))
        before = True
        for g in asm.fastens:
            if g.id == f.id:
                before = False
                continue
            own = path if before else end
            g_e, g_float = paths[g.id]
            reach = e + g_e + Q(1, 2)
            best = Approach(g.id, None, reach, (-1, -1), False, g.id)
            for mine in own:
                for theirs in (_placed_screw(screws[g.id], den, f"{g.id}.shank", g_float),
                               _placed_screw(screws[g.id], den, f"{g.id}.head", g_float)):
                    found = _static(mine, theirs, g.id, reach, den, set(), False)
                    if found.d2 is not None and (best.d2 is None or found.d2 < best.d2):
                        best = Approach(g.id, found.d2, reach, found.triangles, False, g.id)
            approaches.append(best)
        arrivals[f.id] = Arrival(f.id, tuple(approaches), (first,), ())
        grips[f.id] = s["grip"]
        clears[f.id] = s["clear"]
        seats[f.id] = _seat(asm, f, s, bodies[first], den, alw[first], e)
    gaps = {}
    for g in asm.gaps:
        same = axes[g.a] is None or axes[g.b] is None or axes[g.a].value == axes[g.b].value \
            or axes[g.a].value == axes[g.b].opposite.value
        v = (axes[g.b] or axes[g.a] or Axis.TOP).value
        f = floats[g.a] + floats[g.b] if same else floats[g.b]
        reach = g.least + alw[g.a] + alw[g.b] + floats[g.a] + floats[g.b] + Q(1, 2)
        gaps[(g.a, g.b)] = _approach(bodies[g.b], bodies[g.a], g.a, v, Q(0), f, reach, den, set(), not same)
    return Layout(den, axes, floats, arrivals, gaps, frozenset(touching), grips, seats, presses, clears, placed)


def screw_span(lay: Layout, fid: str, k: int) -> tuple[Q, Q]:
    """Where the screw's centre of mass can lie along coordinate k, mm: on its axis between
    its head's top and its tip, at either end of its float, and off the axis by its shift."""
    s, e, fl = lay.screws[fid]
    axis = s["axis"]
    top = s["mouth"][k] - (s["head_h"] + fl) * axis[k]
    tip = s["mouth"][k] + (s["reach"] + fl) * axis[k]
    lo, hi = min(top, tip), max(top, tip)
    return (lo, hi) if axis[k] else (lo - e, hi + e)


def surface(mesh: Mesh) -> tuple[Q, Q, int]:
    """(area mm^2, ridge mm, corners), each at least the true value: the area of the
    triangles, the length of the edges where the surface bends (the two triangles on an
    edge are not coplanar facing the same way), and the vertices on such edges. Away from
    the ridge the surface is flat, so a point nearest to it lies along a face's normal."""
    hit = _SURFACES.get(id(mesh))
    if hit is not None and hit[0] is mesh:
        return hit[1]
    v = [tuple(int(c) for c in row) for row in mesh.vertices.tolist()]
    tris = [tuple(int(x) for x in t) for t in mesh.triangles.tolist()]
    normals = []
    area = Q(0)
    scale2 = mesh.scale ** 2
    for a, b, c in tris:
        n = exact._cross(exact._sub(v[b], v[a]), exact._sub(v[c], v[a]))
        normals.append(n)
        area += root_up(Q(exact._dot(n, n), 4 * scale2 * scale2))
    edges: dict[tuple[int, int], list[int]] = {}
    for idx, t in enumerate(tris):
        for m in range(3):
            a, b = t[m], t[(m + 1) % 3]
            edges.setdefault((min(a, b), max(a, b)), []).append(idx)
    ridge, corners = Q(0), set()
    for (a, b), owners in edges.items():
        flat = len(owners) == 2 and exact._cross(normals[owners[0]], normals[owners[1]]) == (0, 0, 0)             and exact._dot(normals[owners[0]], normals[owners[1]]) > 0
        if not flat:
            d = exact._sub(v[b], v[a])
            ridge += root_up(Q(exact._dot(d, d), scale2))
            corners |= {a, b}
    found = (area, ridge, len(corners))
    _SURFACES[id(mesh)] = (mesh, found)
    return found


_SURFACES: dict = {}


def _out(mover: Body, others: list[Body], v, den: int) -> Q:
    """How far back along -v the mover must start so every point of it lies behind every
    point of the bodies before it, mm: from there nothing stands between it and outside."""
    k = next(m for m in range(3) if v[m])
    s = v[k]
    front = int(mover.hi[:, k].max()) if s > 0 else -int(mover.lo[:, k].min())
    behind = min((int(b.lo[:, k].min()) if s > 0 else -int(b.hi[:, k].max())) for b in others)
    return max(Q(0), Q(front - behind + 1, den))


def _skipper(level: set, name: str, other: str, pressed, presses) -> set | Callable:
    """The pairs (other index, mover index) an approach leaves out: the stops, and for a
    seated press the pin's core against the hole's wall."""
    press = pressed.get(frozenset((name, other)))
    if press is None or presses[press.id].seated:
        return level
    fit = presses[press.id]
    if press.pin == name:
        return lambda i, j: (i, j) in level or (i in fit.wall and j in fit.core)
    return lambda i, j: (i, j) in level or (i in fit.core and j in fit.wall)


def _in_plane(body: Body, idx: int, k: int, level: int, s: int) -> bool:
    """Triangle idx lies in the plane x_k = level and faces direction s along axis k."""
    if not (body.lo[idx, k] == level and body.hi[idx, k] == level):
        return False
    return exact._sign(exact.normal(body.pts[idx])[k]) == s


def faces(body: Body) -> list[int]:
    """The flat face of each triangle, as the least triangle index in it: triangles joined
    through shared edges to neighbours that lie in their plane and face the same way."""
    parent = list(range(len(body)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    normals = [exact.normal(t) for t in body.pts]
    owner: dict[frozenset, int] = {}
    for i, t in enumerate(body.pts):
        for m in range(3):
            j = owner.setdefault(frozenset((t[m], t[(m + 1) % 3])), i)
            n, o = normals[i], normals[j]
            if j != i and exact._cross(n, o) == (0, 0, 0) and exact._dot(n, o) > 0:
                a, b = root(i), root(j)
                parent[max(a, b)] = min(a, b)
    return [root(i) for i in range(len(body))]


def _face_extremes(body: Body, k: int, s: int, pick) -> list[int]:
    """Each triangle's face's least (`pick` min) or greatest (max) value of s * x_k."""
    face = faces(body)
    best: dict[int, int] = {}
    for i, t in enumerate(body.pts):
        v = pick(s * p[k] for p in t)
        best[face[i]] = v if face[i] not in best else pick(best[face[i]], v)
    return [best[face[i]] for i in range(len(body))]


def _level_pairs(mover: Body, other: Body, k: int, s: int, pad: int) -> tuple[set, bool]:
    """The triangle pairs (other index, mover index) within `pad` whose faces' facing
    extremes along axis k meet at one level, the mover's face wholly behind (direction s),
    and whether any of them touch: the mover rests on `other` when one does. Such pairs lie
    on either side of the contact plane, so the float along the axis moves the mover with
    it, never into it. Faces, not triangles, decide, so splitting a face changes nothing."""
    low, high = _face_extremes(mover, k, s, min), _face_extremes(other, k, s, max)
    level, rests = set(), False
    for i, j in exact.candidates(mover.lo, mover.hi, other.lo, other.hi, pad).tolist():
        if low[i] == high[j]:
            level.add((j, i))
            rests = rests or exact.tri_tri2(mover.pts[i], other.pts[j]) == 0
    return level, rests


def _skip_fn(skip):
    if callable(skip):
        return skip
    return (lambda i, j: (i, j) in skip) if skip else None


def _static(mover: Body, other: Body, name: str, reach: Q, den: int, skip, crude: bool) -> Approach:
    found = exact.nearest(other, mover, int(reach * den) + 1, skip=_skip_fn(skip))
    return Approach(name, None if found.d2 is None else found.d2 / den ** 2, reach, (found.j, found.i), crude)


def _approach(mover: Body, other: Body, name: str, v, travel: Q, float_: Q, reach: Q, den: int, skip,
              crude: bool) -> Approach:
    """The mover swept from `float_` past its place back to `travel + float_` before it,
    against the other body; pairs `skip` names (other index, mover index) are its stops."""
    ahead = tuple(int(c * float_ * den) for c in v)
    if max(abs(c) for c in ahead) >= exact.LIMIT:
        raise exact.too_large(mover.name, den, max(abs(c) for c in ahead))
    start = make_body(mover.name, den, mover.tris + np.array(ahead, dtype=np.int64)) if float_ else mover
    back = tuple(-int(c * (travel + 2 * float_) * den) for c in v)
    within = int(reach * den) + 1
    found = exact.nearest(other, start, within, skip=_skip_fn(skip), sweep=back if any(back) else None)
    d2 = None if found.d2 is None else found.d2 / den ** 2
    return Approach(name, d2, reach, (found.j, found.i), crude)


def _contained(a: Body, b: Body, owner_a: list[int], owner_b: list[int], skip_a=frozenset(), skip_b=frozenset()) -> bool:
    """Some edge-joined piece of a lies inside b, or one of b inside a. Each piece is
    probed at the centroid of its triangles in turn, past any in `skip_*`, until one lies
    off the other's surface. Only called where the bodies' nearest approach is tested too,
    so a piece whose every probe lies on a surface is a contact that the approach reports."""
    for x, y, owner, skip in ((a, b, owner_a, skip_a), (b, a, owner_b, skip_b)):
        thrice = exact.scaled(y, 3)
        done = set()
        for idx, piece in enumerate(owner):
            if piece in done or idx in skip:
                continue
            probe = tuple(sum(p[m] for p in x.pts[idx]) for m in range(3))
            got = exact.inside(probe, thrice)
            if got is None:
                continue
            if got:
                return True
            done.add(piece)
    return False


def _placed_hole(asm: Assembly, body: str, hole: Hole) -> tuple[Point, tuple[int, int, int]]:
    placement = asm.place(body).placement
    return placement.apply(hole.at), placement.turn.apply(hole.along.value)


def _screw(asm: Assembly, f: Fasten, registry: Registry, alw: Mapping[str, Q]) -> dict:
    """The screw's axis, the mouth its head seats at, its radii at their greatest, the
    farthest its tip reaches past the mouth, the thread's grip and the last body's
    material before its hole's mouth, mm. A countersunk head's top sits in its
    countersink as deep as the mesh lets its least head sink."""
    part = registry.parts[f.screw]
    props = part.props
    d = props["d"].value.hi * MM
    head_lo, head_hi = props["head_d"].value.lo * MM, props["head_d"].value.hi * MM
    head_h = props["head_h"].value.hi * MM
    length_lo, length_hi = props["length"].value.lo * MM, props["length"].value.hi * MM
    csk = "csk_angle" in props
    last_body, last_id = f.stack[-1]
    first_body, first_id = f.stack[0]
    last, first = asm.hole(last_body, last_id), asm.hole(first_body, first_id)
    c_last, axis = _placed_hole(asm, last_body, last)
    c_first, axis_first = _placed_hole(asm, first_body, first)
    level = sum((c_first[m] - c_last[m]) * axis[m] for m in range(3))
    mouth = tuple(c_last[m] + level * axis[m] for m in range(3))
    sink = Q(0)
    if csk and first.countersink is not None:
        found = sink_depth(asm.place(first_body).body, first, head_lo, alw[first_body])
        sink = found if found is not None else (first.countersink - first.diameter)
    else:
        found = Q(0)
    engaged_lo = length_lo + level
    engaged_hi = None if found is None else length_hi + level + sink
    last_part = asm.place(last_body).body
    zone = Q(0)
    thread = None
    if last.role in ("tap", "form"):
        zone = registry.constants[f"parts.engagement.{last.role}"].value.hi * d
        thread = hole_bore(last_part, last, zone)
    run = hole_run(last_part, last)
    clear = approach_clear(exact.body_of_mesh(last_part.name, last_part.mesh), last.at, last.along.value, d / 2,
                           allowance_hi(last_part, registry, against_screw=True) * 2 + 1)
    return {"axis": axis, "aligned": axis == axis_first, "mouth": mouth, "r": d / 2, "head_r": head_hi / 2,
            "head_lo": head_lo / 2, "head_h": head_h, "reach": length_hi + sink, "length_hi": length_hi, "csk": csk,
            "grip": Grip(engaged_lo, engaged_hi, run, zone, thread), "clear": clear, "sunk": found is not None}


def _placed_screw(s: dict, den: int, which: str, float_: Q) -> Body:
    """A screw where it ends up, either way along its axis by its float: its shank from the
    head's top to its tip, or its head (a countersunk head down to as deep as it sinks)."""
    axis = s["axis"]
    top = tuple(s["mouth"][m] - (s["head_h"] + float_) * axis[m] for m in range(3))
    if which.endswith("shank"):
        return body_of(which, den, frustum(top, axis, circumscribed(s["r"]), circumscribed(s["r"]),
                                           s["head_h"] + s["reach"] + 2 * float_))
    depth = s["head_h"] + 2 * float_ + (s["reach"] - s["length_hi"] + s["head_h"] if s["csk"] else 0)
    return body_of(which, den, frustum(top, axis, circumscribed(s["head_r"]), circumscribed(s["head_r"]), depth))


def _press(asm: Assembly, p: Press, bodies: Mapping[str, Body], alw: Mapping[str, Q], den: int) -> PressFit:
    """Read a press from the meshes over the length where the pin crosses the hole's slab."""
    pin, block = bodies[p.pin], bodies[p.body]
    hole = asm.hole(p.body, p.hole)
    centre, axis = _placed_hole(asm, p.body, hole)
    k, i, j = _frame(axis)
    s = axis[k]
    ins = next((x for x in asm.inserts if x.body == p.pin), None)
    if ins is None or ins.along.value[k] == 0:
        return _unseated("the pin does not travel along the hole's axis")
    lo, hi = block.bounds()
    far = Q(hi[k] if s > 0 else lo[k], den)
    ends = sorted((centre[k], centre[k] + s * hole.depth if hole.depth is not None else far))
    plo, phi = pin.bounds()
    z0, z1 = max(ends[0], Q(plo[k], den)), min(ends[1], Q(phi[k], den))
    if z0 >= z1:
        return _unseated("the pin does not reach into the hole")
    found = bore(block, centre, k, z0, z1)
    mid = list(centre)
    mid[k] = (z0 + z1) / 2
    if not found.open:
        return _unseated("the hole's axis meets the block's material where the pin reaches")
    if found.hi2 is None:
        return _unseated("the block's mesh gives the hole no wall with material round it")
    if _inside_scaled(pin, mid) is not True:
        return _unseated("the pin does not hold the hole's axis")
    c = (centre[i] * den, centre[j] * den)
    cap = (root_up(found.hi2) + p.hi / 2 + alw[p.pin] + alw[p.body] + Q(1, den)) * den
    core = frozenset(idx for idx, t in enumerate(pin.pts) if all((q[i] - c[0]) ** 2 + (q[j] - c[1]) ** 2 <= cap * cap for q in t))
    pin2 = max(((q[i] - c[0]) ** 2 + (q[j] - c[1]) ** 2 for idx in core for q in pin.pts[idx]), default=Q(0))
    if found.out2 is not None and pin2 >= found.out2 * den * den:
        return _unseated("the pin reaches past the hole's wall to the block's far surface")
    # The interference is radial, so the wall is measured against the pin's faces that are
    # not level: a level face (a flush end) is never what a point inside the pin reaches
    # first going straight out from the axis.
    sides = [t for t in pin.pts if exact.normal(t)[i] != 0 or exact.normal(t)[j] != 0]
    pieces = []
    for idx in found.wall:
        poly = _clip_slab([tuple(Q(x) for x in q) for q in block.pts[idx]], k, z0 * den, z1 * den)
        if len(poly) < 3:
            continue
        pieces += [t for t in ((poly[0], poly[m], poly[m + 1]) for m in range(1, len(poly) - 1))
                   if exact.normal(t) != (0, 0, 0)]
        centroid = tuple(sum(q[m] for q in poly) / len(poly) for m in range(3))
        if _inside_scaled(pin, tuple(x / den for x in centroid)) is not True:
            return _unseated("the hole's wall does not lie inside the pin")
    grip2 = _least2(pieces, sides)
    wall = frozenset(idx for idx in range(len(block.pts))
                     if _within_slab(block, idx, k, ends, den) and (exact.normal(block.pts[idx])[k] == 0 or
                                                                   _in_plane(block, idx, k, int(centre[k] * den), -s)))
    return PressFit("", (grip2 or Q(0)) / den ** 2, pin2 / den ** 2, found.lo2, wall, core)


def _least2(pieces: list, tris: list) -> Q | None:
    """The least squared distance from any of `pieces` (rational corners) to any of `tris`
    (integer corners), exact: both scaled to integers over the pieces' common denominator,
    each piece's partners taken in order of their boxes' distance until a box lies farther
    than the best pair found."""
    if not pieces or not tris:
        return None
    scale = lcm(*(Q(c).denominator for t in pieces for q in t for c in q))
    ours = [tuple(tuple(int(c * scale) for c in q) for q in t) for t in pieces]
    theirs = [tuple(tuple(c * scale for c in q) for q in t) for t in tris]
    boxes = [(tuple(min(q[m] for q in t) for m in range(3)), tuple(max(q[m] for q in t) for m in range(3)))
             for t in theirs]
    best = None
    for t in ours:
        lo, hi = tuple(min(q[m] for q in t) for m in range(3)), tuple(max(q[m] for q in t) for m in range(3))
        for gap, n in sorted((exact.box_dist2(lo, hi, *boxes[n]), n) for n in range(len(theirs))):
            if best is not None and gap >= best:
                break
            d = exact.tri_tri2(t, theirs[n])
            best = d if best is None or d < best else best
    return Q(best, scale * scale)


def _unseated(why: str) -> PressFit:
    return PressFit(why, Q(0), FAR, Q(0), frozenset(), frozenset())


def _within_slab(body: Body, idx: int, k: int, ends, den: int) -> bool:
    return ends[0] * den <= int(body.lo[idx, k]) and int(body.hi[idx, k]) <= ends[1] * den


def _seat(asm: Assembly, f: Fasten, s: dict, body: Body, den: int, a: Q, e: Q) -> Seating:
    """A socket head bears on a ring from the first hole's radius to the head's, which must
    lie on faces of the first body facing back along the screw; the head's centre may sit
    off by the axis shift e, so the ring reaches its greatest radius plus e. A countersunk
    head needs the hole's countersink, and the mesh's countersink must narrow below the
    head's least diameter so the head stops."""
    first_body, first_id = f.stack[0]
    hole = asm.hole(first_body, first_id)
    if not s["aligned"]:
        return Seating(1, "the holes of the stack run along different axes")
    k, i, j = _frame(s["axis"])
    if s["csk"]:
        if hole.countersink is None:
            return Seating(1, f"{first_body}.{first_id} declares no countersink for a countersunk head")
        if not s["sunk"]:
            return Seating(1, f"the mesh's countersink at {first_body}.{first_id} does not narrow below the head's least "
                              f"diameter, {float(2 * s['head_lo']):g} mm, so nothing stops the head")
        return Seating(0, "")
    level = int(s["mouth"][k] * den)
    faces = exact.faces_toward(body, k, -s["axis"][k], level)
    edges = exact.boundary_edges(body, faces)
    centre = (s["mouth"][i] * den, s["mouth"][j] * den)
    r_in2, r_out2 = ((hole.diameter / 2 + a) * den) ** 2, ((s["head_r"] + e + a) * den) ** 2
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
                       f"the head's bearing ring, {float(hole.diameter + 2 * a):g} to {float(2 * (s['head_r'] + e + a)):g} mm "
                       f"across, is not all on a face of {first_body} facing the head ({crossing} face edges cross it)")
    return Seating(0, "")


def _in_tri2(p, t, i, j) -> bool:
    s = [(t[(m + 1) % 3][i] - t[m][i]) * (p[1] - t[m][j]) - (t[(m + 1) % 3][j] - t[m][j]) * (p[0] - t[m][i]) for m in range(3)]
    return all(x >= 0 for x in s) or all(x <= 0 for x in s)


# --- Part facts ------------------------------------------------------------------------


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
    return exact.inside(tuple(int(c * d) for c in point), exact.scaled(body, d // body.den))


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
