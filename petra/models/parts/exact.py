"""The exact evaluator: every question about one placement, on exact rational coordinates. Trusted.

Each measure reduces to orientation signs and squared distances between triangles,
segments and points, all rational for rational vertices. A `Body` holds one placed
body's triangles as integers over a common denominator `den` (1/den mm), Python integers
carry every predicate, and numpy only gathers candidates and compares integer boxes. No
float enters a result.

Candidates come from a broad phase over closed integer boxes grown by the distance that
matters. Two triangles whose grown boxes miss are farther apart than the question asks
about, so the broad phase only drops pairs that cannot matter. That completeness, the
parity count, and the choice of which pair is closest are what the engine is trusted for.

The primitives:

    tri_tri2(T, U)        the least squared distance of two closed triangles, 0 when they meet
    tri_prism2(T, U, v)   the least squared distance of T to U swept by the vector v, the
                          convex hull of U and U + v: an insertion path, or a float range
    inside(p, body)       parity of a ray from p that misses every edge and vertex
    surface_problem(m)    the first pair of a mesh's triangles that cross, touch, or lie on
                          each other (a zero-thickness wall or an internal face)
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import lcm
from typing import Iterable, Sequence

import numpy as np

from ..base import ComponentError
from .mesh import LIMIT, Mesh, pieces
from .space import Solid

V = tuple[int, int, int]
T = tuple[V, V, V]


# --- Vector algebra on integers --------------------------------------------------


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def orient(a, b, c, d) -> int:
    """Six times the signed volume of (a, b, c, d): positive when d lies on the side the
    normal (b - a) x (c - a) points to."""
    return _dot(_cross(_sub(b, a), _sub(c, a)), _sub(d, a))


def _sign(x) -> int:
    return (x > 0) - (x < 0)


def normal(t: T) -> V:
    return _cross(_sub(t[1], t[0]), _sub(t[2], t[0]))


# --- Squared distances ---------------------------------------------------------------


def point_seg2(p, a, b) -> Fraction:
    d, w = _sub(b, a), _sub(p, a)
    t, dd = _dot(w, d), _dot(d, d)
    if t <= 0:
        return Fraction(_dot(w, w))
    if t >= dd:
        e = _sub(p, b)
        return Fraction(_dot(e, e))
    return Fraction(_dot(w, w) * dd - t * t, dd)


def point_tri2(p, t: T) -> Fraction:
    a, b, c = t
    n = normal(t)
    if (_dot(_cross(_sub(b, a), _sub(p, a)), n) >= 0 and _dot(_cross(_sub(c, b), _sub(p, b)), n) >= 0
            and _dot(_cross(_sub(a, c), _sub(p, c)), n) >= 0):
        h = _dot(_sub(p, a), n)
        return Fraction(h * h, _dot(n, n))
    return min(point_seg2(p, a, b), point_seg2(p, b, c), point_seg2(p, c, a))


def seg_seg2(p0, p1, q0, q1) -> Fraction:
    u, v, w = _sub(p1, p0), _sub(q1, q0), _sub(p0, q0)
    a, b, c, d, e = _dot(u, u), _dot(u, v), _dot(v, v), _dot(u, w), _dot(v, w)
    den = a * c - b * b
    best = min(point_seg2(p0, q0, q1), point_seg2(p1, q0, q1), point_seg2(q0, p0, p1), point_seg2(q1, p0, p1))
    if den > 0:
        s, t = b * e - c * d, a * e - b * d
        if 0 < s < den and 0 < t < den:
            x = tuple(Fraction(w[k] * den + s * u[k] - t * v[k], den) for k in range(3))
            best = min(best, x[0] * x[0] + x[1] * x[1] + x[2] * x[2])
    return best


def _drop(n: V) -> tuple[int, int]:
    """The two coordinates kept when projecting along the largest component of n."""
    k = max(range(3), key=lambda i: abs(n[i]))
    return ((1, 2), (2, 0), (0, 1))[k]


def _o2(a, b, c, i, j) -> int:
    return (b[i] - a[i]) * (c[j] - a[j]) - (b[j] - a[j]) * (c[i] - a[i])


def _seg2_meet(p, q, a, b, i, j) -> bool:
    """Closed segments pq and ab meet, in the plane of coordinates i and j."""
    d1, d2, d3, d4 = _o2(a, b, p, i, j), _o2(a, b, q, i, j), _o2(p, q, a, i, j), _o2(p, q, b, i, j)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True

    def on(x, y, z):
        return min(x[i], y[i]) <= z[i] <= max(x[i], y[i]) and min(x[j], y[j]) <= z[j] <= max(x[j], y[j])

    return ((d1 == 0 and on(a, b, p)) or (d2 == 0 and on(a, b, q)) or (d3 == 0 and on(p, q, a))
            or (d4 == 0 and on(p, q, b)))


def _in_tri2(p, t: T, i, j) -> bool:
    s = [_o2(t[k], t[(k + 1) % 3], p, i, j) for k in range(3)]
    return all(x >= 0 for x in s) or all(x <= 0 for x in s)


def seg_meets_tri(p, q, t: T) -> bool:
    """The closed segment pq meets the closed triangle t."""
    a, b, c = t
    dp, dq = orient(a, b, c, p), orient(a, b, c, q)
    if (dp > 0 and dq > 0) or (dp < 0 and dq < 0):
        return False
    if dp == 0 and dq == 0:
        i, j = _drop(normal(t))
        return (_in_tri2(p, t, i, j) or _in_tri2(q, t, i, j)
                or any(_seg2_meet(p, q, t[k], t[(k + 1) % 3], i, j) for k in range(3)))
    s1, s2, s3 = orient(p, q, a, b), orient(p, q, b, c), orient(p, q, c, a)
    return (s1 >= 0 and s2 >= 0 and s3 >= 0) or (s1 <= 0 and s2 <= 0 and s3 <= 0)


def seg_tri2(p, q, t: T) -> Fraction:
    if seg_meets_tri(p, q, t):
        return Fraction(0)
    return min(point_tri2(p, t), point_tri2(q, t), *(seg_seg2(p, q, t[k], t[(k + 1) % 3]) for k in range(3)))


def tri_tri2(t: T, u: T) -> Fraction:
    """The least squared distance between two closed triangles. If they meet, an edge of
    one meets the other; if not, the closest pair has a point on an edge of one."""
    best = None
    for x, y in ((t, u), (u, t)):
        for k in range(3):
            d = seg_tri2(x[k], x[(k + 1) % 3], y)
            if d == 0:
                return d
            best = d if best is None or d < best else best
    return best


def prism_faces(u: T, v: V) -> list[T]:
    """The faces of the convex hull of u and u + v, as triangles (the hull of a swept
    triangle). A side face is the parallelogram an edge sweeps, split in two."""
    w = tuple(_add(p, v) for p in u)
    faces = [u, w]
    for k in range(3):
        a, b = u[k], u[(k + 1) % 3]
        faces.append((a, b, w[(k + 1) % 3]))
        faces.append((a, w[(k + 1) % 3], w[k]))
    return faces


def _in_prism(p, u: T, v: V) -> bool:
    """p lies in the closed hull of u and u + v: the line through p along v meets u at a
    point p - s v with 0 <= s <= 1. v crosses u's plane, so the line test holds at s = 0 too."""
    n = normal(u)
    nv = _dot(n, v)
    if nv == 0:
        return False
    s = Fraction(_dot(n, _sub(p, u[0])), nv)
    if not 0 <= s <= 1:
        return False
    q = _add(p, v)
    s1, s2, s3 = orient(p, q, u[0], u[1]), orient(p, q, u[1], u[2]), orient(p, q, u[2], u[0])
    return (s1 >= 0 and s2 >= 0 and s3 >= 0) or (s1 <= 0 and s2 <= 0 and s3 <= 0)


def tri_prism2(t: T, u: T, v: V) -> Fraction:
    """The least squared distance of the closed triangle t to the hull of u and u + v."""
    if not any(v) or _dot(normal(u), v) == 0 and _cross(normal(u), v) == (0, 0, 0):
        return tri_tri2(t, u)
    if _in_prism(t[0], u, v):
        return Fraction(0)
    best = None
    for face in prism_faces(u, v):
        if normal(face) == (0, 0, 0):
            continue
        d = tri_tri2(t, face)
        if d == 0:
            return d
        best = d if best is None or d < best else best
    return best


# --- Coplanar overlap ----------------------------------------------------------------


def _clip_area2(t: T, u: T, i: int, j: int) -> Fraction:
    """Twice the area of t clipped to u, both projected on coordinates i and j."""
    poly = [(Fraction(p[i]), Fraction(p[j])) for p in t]
    sign = _sign(_o2(u[0], u[1], u[2], i, j))
    for k in range(3):
        a, b = (u[k][i], u[k][j]), (u[(k + 1) % 3][i], u[(k + 1) % 3][j])

        def side(p):
            return sign * ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]))

        out = []
        for m in range(len(poly)):
            p, q = poly[m], poly[(m + 1) % len(poly)]
            sp, sq = side(p), side(q)
            if sp >= 0:
                out.append(p)
            if (sp > 0 and sq < 0) or (sp < 0 and sq > 0):
                r = sp / (sp - sq)
                out.append((p[0] + r * (q[0] - p[0]), p[1] + r * (q[1] - p[1])))
        poly = out
        if len(poly) < 3:
            return Fraction(0)
    return abs(sum(poly[m][0] * poly[(m + 1) % len(poly)][1] - poly[(m + 1) % len(poly)][0] * poly[m][1]
                   for m in range(len(poly))))


def coplanar(t: T, u: T) -> bool:
    return all(orient(t[0], t[1], t[2], p) == 0 for p in u)


def overlap_area2(t: T, u: T) -> Fraction:
    """For coplanar triangles, twice the area their closed sets share, projected."""
    i, j = _drop(normal(t))
    return _clip_area2(t, u, i, j)


# --- Bodies and the broad phase --------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Body:
    """One placed body's triangles as integers over `den` (units of 1/den mm). `tris` is
    (m, 3, 3) int64; `pts` the same as Python tuples; `lo` and `hi` each triangle's box."""

    name: str
    den: int
    tris: np.ndarray
    pts: tuple[T, ...]
    lo: np.ndarray
    hi: np.ndarray

    def __len__(self) -> int:
        return len(self.pts)

    def bounds(self) -> tuple[V, V]:
        return tuple(int(x) for x in self.lo.min(axis=0)), tuple(int(x) for x in self.hi.max(axis=0))


def make_body(name: str, den: int, tris) -> Body:
    """A body from (m, 3, 3) integer coordinates: Python integers, or an int64 array that
    is a sum of two arrays already held under LIMIT. Raises ComponentError when a
    coordinate reaches LIMIT, so no int64 sum or difference of two coordinates, pads or
    sweeps ever wraps."""
    if isinstance(tris, np.ndarray):
        rows = tris.astype(object).tolist()
    else:
        rows = [[[int(c) for c in p] for p in t] for t in tris]
    big = max((abs(c) for t in rows for p in t for c in p), default=0)
    if big >= LIMIT:
        raise too_large(name, den, big)
    arr = np.array(rows, dtype=np.int64).reshape(-1, 3, 3)
    pts = tuple(tuple(tuple(p) for p in t) for t in rows)
    return Body(name, den, arr, pts, arr.min(axis=1), arr.max(axis=1))


def too_large(name: str, den: int, value: int) -> ComponentError:
    return ComponentError((f"{name}: a coordinate, pad or sweep reaches {value} units of 1/{den} mm, past the 2^60 the "
                           "exact evaluator holds in int64; write the meshes with fewer decimals or place the parts "
                           "nearer the origin",))


def scaled(body: Body, factor: int) -> Body:
    """The same body over the denominator `factor` times finer, in Python integers."""
    return make_body(body.name, body.den * factor, [[[c * factor for c in p] for p in t] for t in body.pts])


def denominator(*values: Iterable[Fraction | int]) -> int:
    """The least common denominator of every value given (mesh scales count as 1/scale)."""
    d = 1
    for group in values:
        for x in group:
            d = lcm(d, Fraction(x).denominator)
    return d


def place(solid: Solid, den: int) -> Body:
    """The solid's triangles in the assembly frame at denominator `den`."""
    mesh = solid.mesh
    if den % mesh.scale:
        raise ValueError(f"denominator {den} does not hold the mesh scale {mesh.scale}")
    k = den // mesh.scale
    rows = solid.placement.turn.rows
    off = [Fraction(c) * den for c in solid.placement.offset]
    if any(c.denominator != 1 for c in off):
        raise ValueError("the denominator does not hold the placement offset")
    verts = [tuple(sum(r[m] * v[m] for m in range(3)) * k + int(off[n]) for n, r in enumerate(rows))
             for v in mesh.vertices.tolist()]
    return make_body(solid.name, den, [[verts[i] for i in t] for t in mesh.triangles.tolist()])


def body_of_mesh(name: str, mesh: Mesh) -> Body:
    return make_body(name, mesh.scale, mesh.vertices[mesh.triangles])


def candidates(lo_a: np.ndarray, hi_a: np.ndarray, lo_b: np.ndarray, hi_b: np.ndarray, pad: int) -> np.ndarray:
    """Index pairs (i, j), i into a and j into b, whose closed boxes, a's grown by `pad`,
    meet. Every pair closer than `pad` is among them. A uniform grid of cells gathers them;
    a box that spans many cells is tested against every box of the other side."""
    if not len(lo_a) or not len(lo_b):
        return np.zeros((0, 2), dtype=np.int64)
    if abs(pad) >= LIMIT:
        raise too_large("the broad phase", 1, pad)
    la, ha = lo_a - pad, hi_a + pad
    ext = np.concatenate((ha - la, hi_b - lo_b)).max(axis=1)
    cell = max(int(np.percentile(ext, 75)), 1)
    base = np.minimum(la.min(axis=0), lo_b.min(axis=0))
    ca0, ca1 = (la - base) // cell, (ha - base) // cell
    cb0, cb1 = (lo_b - base) // cell, (hi_b - base) // cell
    span = np.maximum(ca1.max(axis=0), cb1.max(axis=0)) + 1
    big_a = np.prod(ca1 - ca0 + 1, axis=1) > 64
    big_b = np.prod(cb1 - cb0 + 1, axis=1) > 64
    out = []
    ia, ka = _cells(np.flatnonzero(~big_a), ca0, ca1, span)
    ib, kb = _cells(np.flatnonzero(~big_b), cb0, cb1, span)
    if len(ka) and len(kb):
        order = np.argsort(kb, kind="stable")
        kb, ib = kb[order], ib[order]
        ub, start, count = np.unique(kb, return_index=True, return_counts=True)
        pos = np.searchsorted(ub, ka)
        ok = pos < len(ub)
        ok[ok] = ub[pos[ok]] == ka[ok]
        ia, pos = ia[ok], pos[ok]
        n = count[pos]
        if n.sum():
            first = np.repeat(start[pos], n) + np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
            out.append(np.stack((np.repeat(ia, n), ib[first]), axis=1))
    for i in np.flatnonzero(big_a):
        out.append(np.stack((np.full(len(lo_b), i), np.arange(len(lo_b))), axis=1))
    for j in np.flatnonzero(big_b):
        out.append(np.stack((np.arange(len(lo_a)), np.full(len(lo_a), j)), axis=1))
    if not out:
        return np.zeros((0, 2), dtype=np.int64)
    pairs = np.unique(np.concatenate(out), axis=0)
    i, j = pairs[:, 0], pairs[:, 1]
    meet = np.all((la[i] <= hi_b[j]) & (lo_b[j] <= ha[i]), axis=1)
    return pairs[meet]


def _cells(index: np.ndarray, c0: np.ndarray, c1: np.ndarray, span: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if not len(index):
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
    lo, size = c0[index], c1[index] - c0[index] + 1
    n = np.prod(size, axis=1)
    owner = np.repeat(index, n)
    k = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
    s = np.repeat(size, n, axis=0)
    x = np.repeat(lo, n, axis=0) + np.stack((k // (s[:, 1] * s[:, 2]), (k // s[:, 2]) % s[:, 1], k % s[:, 2]), axis=1)
    return owner, (x[:, 0] * span[1] + x[:, 1]) * span[2] + x[:, 2]


def box_dist2(lo_a, hi_a, lo_b, hi_b) -> int:
    d = 0
    for k in range(3):
        g = max(int(lo_b[k]) - int(hi_a[k]), int(lo_a[k]) - int(hi_b[k]), 0)
        d += g * g
    return d


# --- Containment by parity -------------------------------------------------------------

_RAYS: tuple[V, ...] = ((1_000_003, 1_009, 7), (7, 1_000_033, 1_013), (1_019, 11, 1_000_037), (-1_000_039, 13, 1_021),
                        (17, -1_000_081, 1_031), (1_033, 19, -1_000_099), (999_983, 999_979, 1_049))


def inside(p: V, body: Body) -> bool | None:
    """Whether p lies in the solid `body` bounds, by the parity of a ray from p that meets
    no edge, vertex or plane of a triangle edgewise. None when p lies on the surface."""
    for r in _RAYS:
        hits = _ray(p, r, body)
        if hits == "surface":
            return None
        if hits is not None:
            return hits % 2 == 1
    raise RuntimeError("every ray met an edge; the body is degenerate near the point")


def _ray(p: V, r: V, body: Body):
    big = max(abs(c) for c in r)
    k = [abs(c) for c in r].index(big)
    reach = (int(body.hi[:, k].max()) - p[k]) if r[k] > 0 else (p[k] - int(body.lo[:, k].min()))
    if reach < 0:
        return 0
    slack = [(abs(r[m]) * reach) // big + 1 for m in range(3)]
    lo, hi = list(p), list(p)
    for m in range(3):
        if m == k:
            lo[m], hi[m] = (p[m], p[m] + reach) if r[k] > 0 else (p[m] - reach, p[m])
        else:
            lo[m] = p[m] - slack[m] if r[m] <= 0 else p[m]
            hi[m] = p[m] + slack[m] if r[m] >= 0 else p[m]
    near = np.flatnonzero(np.all((body.lo <= np.array(hi)) & (np.array(lo) <= body.hi), axis=1))
    q = _add(p, r)
    count = 0
    for idx in near.tolist():
        a, b, c = body.pts[idx]
        s1, s2, s3 = orient(p, q, a, b), orient(p, q, b, c), orient(p, q, c, a)
        if not ((s1 >= 0 and s2 >= 0 and s3 >= 0) or (s1 <= 0 and s2 <= 0 and s3 <= 0)):
            continue
        h = orient(a, b, c, p)
        if s1 == 0 or s2 == 0 or s3 == 0:
            if h == 0 and seg_meets_tri(p, p, (a, b, c)):
                return "surface"
            return None
        nr = _dot(normal((a, b, c)), r)
        if nr == 0:
            return None
        if h == 0:
            return "surface"
        if _sign(-h) == _sign(nr):
            count += 1
    return count


# --- Pair searches -------------------------------------------------------------------------


@dataclass(frozen=True)
class Closest:
    """The least squared distance (in 1/den mm units squared) between triangle `i` of one
    body and triangle `j` of the other, or None when every pair is at least `within` apart."""

    d2: Fraction | None
    i: int
    j: int


def nearest(a: Body, b: Body, within: int, skip=None, sweep: V | None = None) -> Closest:
    """The closest pair of triangles, one of `a` and one of `b`, closer than `within`
    (1/den mm), skipping any pair `skip(i, j)` names. With `sweep`, each triangle of b is
    swept by that vector first, so the answer is the closest approach of a to b anywhere
    on the straight path from b to b + sweep. Pairs are taken in order of their boxes'
    distance and dropped once a box is farther than the best pair found."""
    lo_b, hi_b = b.lo, b.hi
    reach = max([abs(within), *(abs(c) for c in sweep or ())])
    if reach >= LIMIT:
        raise too_large(b.name, b.den, reach)
    if sweep is not None:
        moved = b.tris + np.array(sweep, dtype=np.int64)
        lo_b, hi_b = np.minimum(b.lo, moved.min(axis=1)), np.maximum(b.hi, moved.max(axis=1))
    pairs = candidates(a.lo, a.hi, lo_b, hi_b, within)
    best = Closest(None, -1, -1)
    limit = Fraction(within * within)
    if not len(pairs):
        return best
    gap = np.maximum(np.maximum(lo_b[pairs[:, 1]] - a.hi[pairs[:, 0]], a.lo[pairs[:, 0]] - hi_b[pairs[:, 1]]), 0).astype(float)
    order = np.argsort((gap * gap).sum(axis=1), kind="stable")
    for i, j in pairs[order].tolist():
        if skip is not None and skip(i, j):
            continue
        if box_dist2(a.lo[i], a.hi[i], lo_b[j], hi_b[j]) >= (limit if best.d2 is None else best.d2):
            continue
        d = tri_tri2(a.pts[i], b.pts[j]) if sweep is None else tri_prism2(a.pts[i], b.pts[j], sweep)
        if d < limit and (best.d2 is None or d < best.d2):
            best = Closest(d, i, j)
            if d == 0 and skip is None:
                break
    return best


def touching(a: Body, b: Body) -> list[tuple[int, int]]:
    """Every pair of triangles, one of a and one of b, that meet."""
    return [(i, j) for i, j in candidates(a.lo, a.hi, b.lo, b.hi, 0).tolist() if tri_tri2(a.pts[i], b.pts[j]) == 0]


def separable(t: T, u: T, k: int, s: int) -> bool:
    """Every point of t lies at or beyond every point of u along axis k in direction s
    (s = 1 for +, -1 for -): moving t that way parts them."""
    return min(s * p[k] for p in t) >= max(s * p[k] for p in u)


# --- One mesh's own surface ------------------------------------------------------------------


def surface_problem(mesh: Mesh) -> str | None:
    """The first defect of a mesh's surface its edge rules cannot see, or None: two
    triangles that share no vertex and meet (the surface crosses or touches itself), two
    that lie on each other facing opposite ways (a zero-thickness wall or an internal face
    between two bodies that touch), two neighbours folded onto each other, or a piece whose
    orientation disagrees with its nesting (a void facing outward, a body facing in)."""
    body = body_of_mesh(mesh.path, mesh)
    tris = mesh.triangles.tolist()
    found = []
    for i, j in candidates(body.lo, body.hi, body.lo, body.hi, 0).tolist():
        if i >= j:
            continue
        t, u = body.pts[i], body.pts[j]
        shared = len(set(tris[i]) & set(tris[j]))
        if shared == 0:
            if tri_tri2(t, u) != 0:
                continue
            if coplanar(t, u) and overlap_area2(t, u) > 0:
                if _dot(normal(t), normal(u)) < 0:
                    return (f"triangles {i} and {j} lie on each other facing opposite ways: a wall of zero thickness, "
                            "or an internal face where two bodies touch")
                return f"triangles {i} and {j} lie on each other facing the same way: the surface overlaps itself"
            found.append(f"triangles {i} and {j} meet though they share no vertex: the surface crosses or touches itself")
        if shared == 2 and coplanar(t, u):
            a, b = (v for v in tris[i] if v in tris[j])
            ci = next(v for v in tris[i] if v not in (a, b))
            cj = next(v for v in tris[j] if v not in (a, b))
            p = mesh.vertices
            pa, pb = tuple(int(x) for x in p[a]), tuple(int(x) for x in p[b])
            n = normal(t)
            side_i = _dot(_cross(_sub(pb, pa), _sub(tuple(int(x) for x in p[ci]), pa)), n)
            side_j = _dot(_cross(_sub(pb, pa), _sub(tuple(int(x) for x in p[cj]), pa)), n)
            if _sign(side_i) == _sign(side_j):
                found.append(f"triangles {i} and {j} share an edge and fold onto each other")
    return found[0] if found else _nesting_problem(mesh, body)


def _nesting_problem(mesh: Mesh, body: Body) -> str | None:
    owner = pieces(mesh)
    groups: dict[int, list[int]] = {}
    for k, piece in enumerate(owner):
        groups.setdefault(piece, []).append(k)
    if len(groups) == 1:
        return None
    signed = {}
    for piece, idx in groups.items():
        signed[piece] = sum(orient((0, 0, 0), *body.pts[k]) for k in idx)
    for piece, idx in groups.items():
        probe = body.pts[idx[0]][0]
        depth = 0
        for other, oidx in groups.items():
            if other == piece:
                continue
            sub = make_body("piece", body.den, body.tris[oidx])
            if inside(probe, sub):
                depth += 1
        if (depth % 2 == 0) != (signed[piece] > 0):
            return (f"the piece holding triangle {idx[0]} is nested {depth} deep and faces "
                    f"{'outward' if signed[piece] > 0 else 'inward'}: a void must face inward and a body outward")
    return None


def extent(body: Body) -> tuple[tuple[Fraction, ...], tuple[Fraction, ...]]:
    """The closed bounding box of the body, mm, exact."""
    lo, hi = body.bounds()
    return tuple(Fraction(c, body.den) for c in lo), tuple(Fraction(c, body.den) for c in hi)


def faces_toward(body: Body, k: int, s: int, level: int) -> list[int]:
    """The triangles lying in the plane x_k = level whose outward normal points along
    axis k in direction s."""
    out = []
    for idx in np.flatnonzero((body.lo[:, k] == level) & (body.hi[:, k] == level)).tolist():
        n = normal(body.pts[idx])
        if _sign(n[k]) == s:
            out.append(idx)
    return out


def boundary_edges(body: Body, idx: Sequence[int]) -> list[tuple[V, V]]:
    """The edges of the triangles `idx` that no other triangle of `idx` shares in the
    opposite direction: the boundary of their union."""
    directed = {}
    for t in (body.pts[i] for i in idx):
        for k in range(3):
            directed[(t[k], t[(k + 1) % 3])] = True
    return [(a, b) for (a, b) in directed if (b, a) not in directed]
