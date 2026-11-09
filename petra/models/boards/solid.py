"""The board as an exact solid, and the room a part keeps over its courtyard. Trusted.

A mesh cannot hold an arc, so each solid is built from the polygons of `plane.bounds` on one
side of the drawn geometry, the side `Errs` names. OVER holds the true solid and UNDER lies
inside it. The board's region is its boundary loop less its cutouts and drilled holes, so
OVER takes the outer polygon of the boundary with the inner polygons of the cutouts and
holes, and UNDER the reverse. Both bound the board the file draws. How far the board as made
strays from it is a premise for the enclosure deck (features.EDGE, HOLES and THICKNESS).

Mesh frame: x is the board's x, y is minus the board's y, and z points out of the top face,
so the frame is right-handed and the top face seen from above looks as KiCad draws it. The
board fills 0 <= z <= thickness.

Each face is cut into triangles by joining every hole to the boundary with a bridge and
clipping ears. The cut is not trusted on its own: `_triangulate` checks exactly that every
triangle turns positively and that the triangles' edges cancel in pairs but for the region's
boundary, each boundary edge once in its own direction. Then the triangles cover each point
of the region once and no point outside it (docs/boards.md, "Solids").
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from math import lcm

import numpy as np

from ..parts.mesh import Mesh, MeshError, _solid
from . import plane
from .kicad import Board, Courtyard, Footprint, Pad, Side, Via
from .plane import TOLERANCE, Bounds, Point, ShapeError
from .sexpr import BoardError


class Errs(Enum):
    OVER = "over"
    UNDER = "under"


@dataclass(frozen=True)
class Prism:
    """A region swept from z = low to z = high, as a mesh in the mesh frame. Its walls lie
    within `deviation` mm of the true solid's walls, on the side `errs` names."""

    mesh: Mesh
    errs: Errs
    low: Fraction
    high: Fraction
    deviation: Fraction


def thickness_of(board: Board, thickness: Fraction | None = None) -> Fraction:
    """The thickness given, else the one the file states. A board file that states none
    needs one given: Petra assumes no default."""
    if thickness is not None:
        if Fraction(thickness) <= 0:
            raise ValueError(f"a board is thicker than 0 mm, not {thickness}")
        return Fraction(thickness)
    if board.thickness is None:
        raise BoardError(board.path, "states no thickness, so its solid needs one given as a premise")
    return board.thickness.value


def hole(item: Pad | Via, tolerance: Fraction = TOLERANCE) -> Bounds:
    """Bounds of a drilled hole's section. An oval drill is a slot along the pad's x axis
    when it is wider than tall, else along its y axis, turned by the pad's angle."""
    if isinstance(item, Via):
        return plane.stadium(item.at, item.at, item.drill / 2, Fraction(0), tolerance)
    drill, at = item.drill, item.at
    if drill.width == drill.height:
        return plane.stadium(at.point, at.point, drill.width / 2, at.error, tolerance)
    radius = min(drill.width, drill.height) / 2
    half = max(drill.width, drill.height) / 2 - radius
    axis = (half, Fraction(0)) if drill.width > drill.height else (Fraction(0), half)
    p = plane.place(axis, at.point, item.angle)
    q = plane.place((-axis[0], -axis[1]), at.point, item.angle)
    return plane.stadium(p.point, q.point, radius, at.error + max(p.error, q.error), tolerance)


def _finest(make, tolerance: Fraction) -> Bounds:
    for t in (tolerance, tolerance / 10, tolerance / 100):
        try:
            return make(t)
        except ShapeError as err:
            last = err
    raise last


def board_solid(board: Board, errs: Errs, *, thickness: Fraction | None = None,
                tolerance: Fraction = TOLERANCE, holes: bool = True) -> Prism:
    """The board as a solid on the side `errs` names. With `holes` it cuts every drilled
    hole: each pad's drill, each via for UNDER, and each through via for OVER. An OVER solid
    without holes still holds the board; an UNDER one would not lie inside it, so UNDER
    always cuts them. Raises BoardError when the bounds of two voids meet, or a void's meet
    the edge, as a hole cut by the board's edge does."""
    if errs is Errs.UNDER and not holes:
        raise ValueError("an UNDER solid cuts every hole, or it would hold room the board does not fill")
    t = thickness_of(board, thickness)
    edge = _finest(lambda tol: plane.bounds(board.outline.boundary, tol), tolerance)
    voids = [(f"the cutout through {plane.show(plane.start(c))}", _finest(lambda tol, c=c: plane.bounds(c, tol), tolerance))
             for c in board.outline.cutouts]
    if holes:
        voids += [(f"the hole of pad {p.number} of {f.reference}", _finest(lambda tol, p=p: hole(p, tol), tolerance))
                  for f in board.footprints for p in f.pads if p.drill]
        voids += [(f"the via at {plane.show(v.at)}", _finest(lambda tol, v=v: hole(v, tol), tolerance))
                  for v in board.vias if v.through or errs is Errs.UNDER]
    over = errs is Errs.OVER
    try:
        mesh = _extrude(f"{board.path}#board-{errs.value}", board.sha256, edge.outer if over else edge.inner,
                        [(name, b.inner if over else b.outer) for name, b in voids], Fraction(0), t)
    except ShapeError as err:
        raise BoardError(board.path, f"the {errs.value} solid: {err}") from None
    return Prism(mesh, errs, Fraction(0), t, max([edge.deviation] + [b.deviation for _, b in voids]))


def keepout(board: Board, footprint: Footprint, low: Fraction, high: Fraction, errs: Errs, *,
            face: Side | None = None, thickness: Fraction | None = None) -> tuple[Prism, ...]:
    """The room over a footprint's courtyard from `low` to `high` mm out from a board face,
    the footprint's own face unless `face` names the other: one prism per courtyard loop.
    The heights are premises. A board file holds none."""
    face = face or footprint.side
    yard = footprint.courtyard(face)
    if not isinstance(yard, Courtyard):
        raise BoardError(board.path, f"{footprint.reference} has no courtyard on its {face.value} face: {yard.reason}")
    low, high = Fraction(low), Fraction(high)
    if not 0 <= low < high:
        raise ValueError(f"a keep-out runs from a height at least 0 to a greater one, not {low} to {high}")
    t = thickness_of(board, thickness)
    z0, z1 = (t + low, t + high) if face is Side.TOP else (-high, -low)
    out = []
    for k, b in enumerate(yard.board):
        try:
            mesh = _extrude(f"{board.path}#{footprint.reference}-{face.value}-{k}", board.sha256,
                            b.outer if errs is Errs.OVER else b.inner, [], z0, z1)
        except ShapeError as err:
            raise BoardError(board.path, f"the keep-out of {footprint.reference}: {err}") from None
        out.append(Prism(mesh, errs, z0, z1, b.deviation))
    return tuple(out)


# --- Extrusion --------------------------------------------------------------------------


def _extrude(path: str, sha256: str, outer, voids, low: Fraction, high: Fraction) -> Mesh:
    """The region inside `outer` and outside every void polygon, swept from low to high."""
    _apart(outer, voids)
    rings = [[(x, -y) for x, y in reversed(outer)]] + [[(x, -y) for x, y in v] for _, v in voids]
    pts, boundary, tris = _triangulate(rings)
    n = len(pts)
    coords = [c for x, y in pts for c in (x, y, low)] + [c for x, y in pts for c in (x, y, high)]
    faces = [(a + n, b + n, c + n) for a, b, c in tris] + [(a, c, b) for a, b, c in tris]
    faces += [f for u, v in boundary for f in ((u, v, v + n), (u, v + n, u + n))]
    try:
        return _solid(path, sha256, coords, np.array(faces, dtype=np.int64), Fraction(1))
    except MeshError as err:
        raise ShapeError(str(err)) from None


def _box(poly) -> tuple[Fraction, Fraction, Fraction, Fraction]:
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def _apart(outer, voids) -> None:
    """Every void lies inside `outer`, and no two voids meet or nest."""
    for name, v in voids:
        if plane.polygons_meet(v, outer) or any(plane.where(p, outer) <= 0 for p in v):
            raise ShapeError(f"the bounds of {name} reach the bounds of the board's edge")
    boxes = [_box(v) for _, v in voids]
    for i, (a_name, a) in enumerate(voids):
        for j in range(i + 1, len(voids)):
            b_name, b = voids[j]
            ba, bb = boxes[i], boxes[j]
            if ba[0] > bb[2] or bb[0] > ba[2] or ba[1] > bb[3] or bb[1] > ba[3]:
                continue
            if plane.polygons_meet(a, b) or plane.where(a[0], b) >= 0 or plane.where(b[0], a) >= 0:
                raise ShapeError(f"the bounds of {a_name} and {b_name} meet")


# --- Triangulation ----------------------------------------------------------------------


def _o(a, b, c) -> int:
    v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return (v > 0) - (v < 0)


def _between(p, q, x) -> bool:
    return min(p[0], q[0]) <= x[0] <= max(p[0], q[0]) and min(p[1], q[1]) <= x[1] <= max(p[1], q[1])


def _strays(m, p, a, b) -> bool:
    """Whether segment mp meets segment ab anywhere but at an end the two share."""
    o1, o2, o3, o4 = _o(m, p, a), _o(m, p, b), _o(a, b, m), _o(a, b, p)
    if o1 == o2 == 0:
        k = 0 if m[0] != p[0] else 1
        lo = max(min(m[k], p[k]), min(a[k], b[k]))
        hi = min(max(m[k], p[k]), max(a[k], b[k]))
        if lo != hi:
            return lo < hi
        return not any(x[k] == lo and x in (a, b) for x in (m, p))
    if o1 * o2 < 0 and o3 * o4 < 0:
        return True
    return any(on and not shared for on, shared in (
        (o1 == 0 and _between(m, p, a), a in (m, p)), (o2 == 0 and _between(m, p, b), b in (m, p)),
        (o3 == 0 and _between(a, b, m), m in (a, b)), (o4 == 0 and _between(a, b, p), p in (a, b))))


def _wedge(cycle, i: int, target, ip) -> bool:
    """Whether the direction from vertex i of the cycle toward `target` points strictly into
    the region, which lies on the cycle's left."""
    a, b, c = ip[cycle[i - 1]], ip[cycle[i]], ip[cycle[(i + 1) % len(cycle)]]
    turn = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
    ahead = (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1])
    left_of_out, right_of_back = _o(b, c, target) > 0, _o(b, target, a) > 0
    if turn > 0 or (turn == 0 and ahead > 0):
        return left_of_out and right_of_back
    return left_of_out or right_of_back


def _bridge(ring: list[int], hole: list[int], ip, others) -> list[int]:
    """The ring with the hole spliced in along a segment from a hole vertex to a ring
    vertex that meets no edge but at its two ends, the nearest such pair from the hole's
    rightmost vertices first."""
    edges = [(ip[ring[i - 1]], ip[ring[i]]) for i in range(len(ring))]
    edges += [(ip[hole[i - 1]], ip[hole[i]]) for i in range(len(hole))] + others
    lo = np.array([[min(a[0], b[0]), min(a[1], b[1])] for a, b in edges], dtype=object)
    hi = np.array([[max(a[0], b[0]), max(a[1], b[1])] for a, b in edges], dtype=object)
    for h in sorted(range(len(hole)), key=lambda k: -ip[hole[k]][0]):
        m = ip[hole[h]]
        for r in sorted(range(len(ring)), key=lambda k: (ip[ring[k]][0] - m[0]) ** 2 + (ip[ring[k]][1] - m[1]) ** 2):
            p = ip[ring[r]]
            if not (_wedge(ring, r, m, ip) and _wedge(hole, h, p, ip)):
                continue
            near = np.flatnonzero((lo[:, 0] <= max(m[0], p[0])) & (hi[:, 0] >= min(m[0], p[0]))
                                  & (lo[:, 1] <= max(m[1], p[1])) & (hi[:, 1] >= min(m[1], p[1])))
            if not any(_strays(m, p, *edges[k]) for k in near.tolist()):
                return ring[:r + 1] + hole[h:] + hole[:h + 1] + ring[r:]
    raise ShapeError("a hole cannot be joined to the boundary")


def _clip(ring: list[int], ip, fp: np.ndarray) -> list[tuple[int, int, int]]:
    """Ear clipping. A float pass picks the vertices that may lie in an ear, with a margin a
    million times float error, and an exact pass decides."""
    margin = -1e-9 * (1 + float(np.abs(fp).max())) ** 2
    ring, tris, i, idle = list(ring), [], 0, 0
    while len(ring) > 3:
        n = len(ring)
        if idle > n:
            raise ShapeError("a face cannot be cut into triangles")
        i %= n
        a, b, c = ring[i - 1], ring[i], ring[(i + 1) % n]
        if _ear(a, b, c, ring, ip, fp, margin):
            tris.append((a, b, c))
            del ring[i]
            i, idle = max(i - 1, 0), 0
        else:
            i, idle = i + 1, idle + 1
    tris.append(tuple(ring))
    return tris


def _ear(a: int, b: int, c: int, ring, ip, fp, margin: float) -> bool:
    A, B, C = ip[a], ip[b], ip[c]
    if _o(A, B, C) <= 0:
        return False
    idx = np.array(ring, dtype=np.int64)
    x, y = fp[idx, 0], fp[idx, 1]
    fa, fb, fc = fp[a], fp[b], fp[c]
    maybe = (((fb[0] - fa[0]) * (y - fa[1]) - (fb[1] - fa[1]) * (x - fa[0]) >= margin)
             & ((fc[0] - fb[0]) * (y - fb[1]) - (fc[1] - fb[1]) * (x - fb[0]) >= margin)
             & ((fa[0] - fc[0]) * (y - fc[1]) - (fa[1] - fc[1]) * (x - fc[0]) >= margin))
    for k in idx[maybe].tolist():
        X = ip[k]
        if X not in (A, B, C) and _o(A, B, X) >= 0 and _o(B, C, X) >= 0 and _o(C, A, X) >= 0:
            return False
    return True


def _triangulate(rings) -> tuple[list[Point], list[tuple[int, int]], list[tuple[int, int, int]]]:
    """Triangles over the region the rings bound: rings[0] counter-clockwise, the rest
    clockwise holes inside it that do not meet. Returns the points, the boundary edges with
    the region on their left, and the triangles, each checked as the module docstring says."""
    pts: list[Point] = []
    cycles: list[list[int]] = []
    for ring in rings:
        cycles.append(list(range(len(pts), len(pts) + len(ring))))
        pts += ring
    scale = 1
    for d in {c.denominator for p in pts for c in p}:
        scale = lcm(scale, d)
    ip = [(int(x * scale), int(y * scale)) for x, y in pts]
    fp = np.array([(float(x), float(y)) for x, y in pts])
    boundary = [(c[i - 1], c[i]) for c in cycles for i in range(len(c))]
    holes = sorted(cycles[1:], key=lambda c: -max(ip[k][0] for k in c))
    ring = cycles[0]
    for k, h in enumerate(holes):
        others = [(ip[c[i - 1]], ip[c[i]]) for c in holes[k + 1:] for i in range(len(c))]
        ring = _bridge(ring, h, ip, others)
    tris = _clip(ring, ip, fp)
    if any(_o(ip[a], ip[b], ip[c]) <= 0 for a, b, c in tris):
        raise ShapeError("a face cut into triangles holds one that does not turn positively")
    used = Counter((u, v) for a, b, c in tris for u, v in ((a, b), (b, c), (c, a)))
    left = {e for e, k in used.items() if k - used.get((e[1], e[0]), 0) > 0}
    if max(used.values()) > 1 or left != set(boundary):
        raise ShapeError("a face cut into triangles does not have the region's boundary as its own")
    return pts, boundary, tris
