"""Exact plane geometry for boards: segments, arcs and circles, the closed loops they make,
and polygons that bound each loop. Trusted.

Points are exact rationals in millimetres in KiCad's board frame, x to the right and y down.
An arc's centre is rational, because it is the centre of three rational points, but its
radius is the square root of a rational. Where a question meets a circle the answer has the
form u + v*sqrt(d), and `_sign` decides its sign exactly. No float decides anything here;
floats only propose polygon corners, and exact checks accept or refuse each proposal.

A `Loop` is a closed curve that does not cross or touch itself, oriented so its region lies
on its left: x dy - y dx summed around it is positive. KiCad's y axis points down, so that is
clockwise on KiCad's screen. docs/boards.md, "Polygons that bound a loop", gives the argument
that `bounds` is sound.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from math import isqrt

Point = tuple[Fraction, Fraction]

TOLERANCE = Fraction(1, 100)
"""How far, in mm, a bounding polygon may stray from its curve unless the caller asks for
less. It sets the size of a mesh and is no fact about a board: every bound holds at any
tolerance."""

SPOT_GRID = Fraction(1, 10 ** 9)
"""The decimal grid, mm, for points and polygons turned by an angle that is not a multiple
of 90 degrees."""


class ShapeError(ValueError):
    """Geometry Petra will not take: a loop that is open, branches, crosses itself or cannot
    be bounded by polygons. The board reader adds the file and layer."""


@dataclass(frozen=True)
class Segment:
    start: Point
    end: Point


@dataclass(frozen=True)
class Arc:
    """The circular arc from `start` through `mid` to `end`."""

    start: Point
    mid: Point
    end: Point


@dataclass(frozen=True)
class Circle:
    """A whole circle: its centre and a point on it, as KiCad writes one."""

    center: Point
    through: Point


Item = Segment | Arc | Circle


@dataclass(frozen=True)
class Loop:
    """A closed simple curve with its region on its left. Only `loop` builds one."""

    items: tuple[Item, ...]


@dataclass(frozen=True)
class Bounds:
    """`inner` lies inside a region and `outer` contains it. Both are simple, positively
    oriented polygons with decimal corners. Each polygon's boundary and the region's true
    boundary lie within `deviation` mm of each other."""

    inner: tuple[Point, ...]
    outer: tuple[Point, ...]
    deviation: Fraction


@dataclass(frozen=True)
class Spot:
    """A point known to within `error` mm: the true point lies within that distance of
    `point`. An error of 0 means the point is exact."""

    point: Point
    error: Fraction


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _mul(a, k):
    return (a[0] * k, a[1] * k)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _sgn(x) -> int:
    return (x > 0) - (x < 0)


def show(p: Point) -> str:
    return f"({float(p[0]):g}, {float(p[1]):g})"


def _sign(u: Fraction, v: Fraction, d: Fraction) -> int:
    """The sign of u + v*sqrt(d), for d >= 0."""
    su, sv = _sgn(u), _sgn(v)
    if sv == 0 or d == 0:
        return su
    if su in (0, sv):
        return sv
    return su * _sgn(u * u - v * v * d)


def _root(x: Fraction) -> Fraction | None:
    """The rational square root of x, or None when it is irrational."""
    n, m = isqrt(x.numerator), isqrt(x.denominator)
    return Fraction(n, m) if n * n == x.numerator and m * m == x.denominator else None


_PLACES = 10 ** 12


def sqrt_lo(x: Fraction) -> Fraction:
    return Fraction(isqrt(math.floor(x * _PLACES ** 2)), _PLACES)


def sqrt_hi(x: Fraction) -> Fraction:
    lo = sqrt_lo(x)
    return lo if lo * lo == x else lo + Fraction(1, _PLACES)


def area2(poly) -> Fraction:
    """Twice the signed area of a polygon: positive when its region lies on its left."""
    return sum((_cross(poly[i - 1], poly[i]) for i in range(len(poly))), Fraction(0))


# --- Arcs as quarter-turn bends ---------------------------------------------------------


@dataclass(frozen=True)
class _Bend:
    """An arc of at most a quarter turn about `center`, counter-clockwise in the file's
    coordinates when `ccw`."""

    center: Point
    r2: Fraction
    start: Point
    end: Point
    ccw: bool

    def holds(self, x: Point) -> bool:
        c, s = self.center, 1 if self.ccw else -1
        xc = _sub(x, c)
        return (_dot(xc, xc) == self.r2 and s * _cross(_sub(self.start, c), xc) >= 0
                and s * _cross(xc, _sub(self.end, c)) >= 0)


def center(a: Arc) -> Point:
    """The centre of the circle through an arc's three points."""
    b, c = _sub(a.mid, a.start), _sub(a.end, a.start)
    d = 2 * _cross(b, c)
    bb, cc = _dot(b, b), _dot(c, c)
    return (a.start[0] + (c[1] * bb - b[1] * cc) / d, a.start[1] + (b[0] * cc - c[0] * bb) / d)


def _bends(item: Arc | Circle) -> list[_Bend]:
    """The arc cut at the points a quarter, a half and three quarters of a turn from its start
    that lie strictly inside it. Each of those points is rational: the start turned by 90
    degrees about a rational centre."""
    if isinstance(item, Circle):
        c, v = item.center, _sub(item.through, item.center)
        if v == (0, 0):
            raise ShapeError(f"the circle at {show(c)} has radius 0")
        points = [item.through]
        for _ in range(3):
            v = (-v[1], v[0])
            points.append(_add(c, v))
        points.append(item.through)
        return [_Bend(c, _dot(v, v), a, b, True) for a, b in zip(points, points[1:])]
    if _cross(_sub(item.mid, item.start), _sub(item.end, item.mid)) == 0:
        raise ShapeError(f"the arc from {show(item.start)} through {show(item.mid)} to {show(item.end)} "
                         "has its three points on one line")
    c = center(item)
    ccw = _cross(_sub(item.mid, item.start), _sub(item.end, item.mid)) > 0
    chord = _sub(item.end, item.start)
    side = _sgn(_cross(chord, _sub(item.mid, item.start)))
    v = _sub(item.start, c)
    points = [item.start]
    for _ in range(3):
        v = (-v[1], v[0]) if ccw else (v[1], -v[0])
        q = _add(c, v)
        if _sgn(_cross(chord, _sub(q, item.start))) != side:
            break
        points.append(q)
    points.append(item.end)
    r2 = _dot(_sub(item.start, c), _sub(item.start, c))
    return [_Bend(c, r2, a, b, ccw) for a, b in zip(points, points[1:])]


def _pieces(items) -> list[Segment | _Bend]:
    out: list[Segment | _Bend] = []
    for item in items:
        if isinstance(item, Segment):
            if item.start == item.end:
                raise ShapeError(f"a line starts and ends at {show(item.start)}")
            out.append(item)
        else:
            out += _bends(item)
    return out


# --- Where two pieces meet --------------------------------------------------------------

_OVERLAP = "overlap"


def _seg_seg(a: Segment, b: Segment):
    p, d1, d2 = a.start, _sub(a.end, a.start), _sub(b.end, b.start)
    qp = _sub(b.start, p)
    den = _cross(d1, d2)
    if den == 0:
        if _cross(qp, d1) != 0:
            return []
        dd = _dot(d1, d1)
        t0, t1 = _dot(qp, d1) / dd, _dot(_sub(b.end, p), d1) / dd
        lo, hi = max(Fraction(0), min(t0, t1)), min(Fraction(1), max(t0, t1))
        if lo > hi:
            return []
        return [_add(p, _mul(d1, lo))] if lo == hi else _OVERLAP
    t, s = _cross(qp, d2) / den, _cross(qp, d1) / den
    return [_add(p, _mul(d1, t))] if 0 <= t <= 1 and 0 <= s <= 1 else []


def _roots(p: Point, w: Point, b: _Bend) -> list[tuple[Fraction, Fraction, Fraction]]:
    """The parameters t where p + t*w meets the bend's circle, each as (u, v, d) meaning
    u + v*sqrt(d). A rational root has v = 0."""
    pc = _sub(p, b.center)
    qa, qb, qc = _dot(w, w), 2 * _dot(w, pc), _dot(pc, pc) - b.r2
    disc = qb * qb - 4 * qa * qc
    if disc < 0:
        return []
    root = _root(disc)
    zero = Fraction(0)
    if root is not None:
        return [(t, zero, zero) for t in {(-qb + root) / (2 * qa), (-qb - root) / (2 * qa)}]
    return [(-qb / (2 * qa), 1 / (2 * qa), disc), (-qb / (2 * qa), -1 / (2 * qa), disc)]


def _on(b: _Bend, p: Point, w: Point, r) -> bool:
    """Whether the circle point p + t*w, t the root r, lies on the bend."""
    u, v, d = r
    s = 1 if b.ccw else -1
    sc, ec, pc = _sub(b.start, b.center), _sub(b.end, b.center), _sub(p, b.center)
    k0, k1 = _cross(sc, pc), _cross(sc, w)
    m0, m1 = _cross(pc, ec), _cross(w, ec)
    return s * _sign(k0 + k1 * u, k1 * v, d) >= 0 and s * _sign(m0 + m1 * u, m1 * v, d) >= 0


def _within(r) -> bool:
    u, v, d = r
    return _sign(u, v, d) >= 0 and _sign(1 - u, -v, d) >= 0


def _at(p: Point, w: Point, r) -> Point | None:
    return _add(p, _mul(w, r[0])) if r[1] == 0 else None


def _meet(a, b):
    """The points where two pieces meet, each a Point or None for an irrational point, or
    _OVERLAP when they share more than finitely many points."""
    if isinstance(a, Segment) and isinstance(b, Segment):
        return _seg_seg(a, b)
    if isinstance(a, _Bend) and isinstance(b, Segment):
        a, b = b, a
    if isinstance(a, Segment):
        w = _sub(a.end, a.start)
        return [_at(a.start, w, r) for r in _roots(a.start, w, b) if _within(r) and _on(b, a.start, w, r)]
    if a.center == b.center:
        if a.r2 != b.r2:
            return []
        if {a.start, a.end} == {b.start, b.end}:
            return _OVERLAP
        found = []
        for x, other in ((a.start, b), (a.end, b), (b.start, a), (b.end, a)):
            if other.holds(x):
                if x not in (other.start, other.end):
                    return _OVERLAP
                found.append(x)
        return list(dict.fromkeys(found))
    n = _sub(b.center, a.center)
    k = _dot(b.center, b.center) - _dot(a.center, a.center) - b.r2 + a.r2
    p = _add(a.center, _mul(n, (k - 2 * _dot(n, a.center)) / (2 * _dot(n, n))))
    w = (-n[1], n[0])
    return [_at(p, w, r) for r in _roots(p, w, a) if _on(a, p, w, r) and _on(b, p, w, r)]


def _box(piece) -> tuple[float, float, float, float]:
    """A float box sure to hold the piece: grown by a micrometre, far beyond float error."""
    if isinstance(piece, Segment):
        xs, ys = (piece.start[0], piece.end[0]), (piece.start[1], piece.end[1])
        lo, hi = (float(min(xs)), float(min(ys))), (float(max(xs)), float(max(ys)))
    else:
        r = float(sqrt_hi(piece.r2))
        lo = (float(piece.center[0]) - r, float(piece.center[1]) - r)
        hi = (float(piece.center[0]) + r, float(piece.center[1]) + r)
    return lo[0] - 1e-3, lo[1] - 1e-3, hi[0] + 1e-3, hi[1] + 1e-3


def _boxes_meet(a, b) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _self_meeting(pieces) -> str | None:
    """The first place a closed run of pieces meets itself beyond the joints of neighbours."""
    n, boxes = len(pieces), [_box(p) for p in pieces]
    for i in range(n):
        for j in range(i + 1, n):
            if not _boxes_meet(boxes[i], boxes[j]):
                continue
            found = _meet(pieces[i], pieces[j])
            allowed = set()
            if j == i + 1:
                allowed.add(pieces[i].end)
            if i == 0 and j == n - 1:
                allowed.add(pieces[0].start)
            if found == _OVERLAP:
                return f"runs back over itself near {show(pieces[i].start)}"
            for x in found:
                if x is None or x not in allowed:
                    return f"crosses or touches itself near {show(x if x is not None else pieces[i].start)}"
    return None


def meeting(loops) -> str | None:
    """Where two of the loops meet, or None when they keep apart."""
    runs = [_pieces(lp.items) for lp in loops]
    boxes = [[_box(p) for p in run] for run in runs]
    for i in range(len(runs)):
        for j in range(i + 1, len(runs)):
            for a, ba in zip(runs[i], boxes[i]):
                for b, bb in zip(runs[j], boxes[j]):
                    if _boxes_meet(ba, bb) and _meet(a, b):
                        return f"two loops meet near {show(a.start)}"
    return None


# --- Loops ------------------------------------------------------------------------------


def _reverse(item: Item) -> Item:
    if isinstance(item, Segment):
        return Segment(item.end, item.start)
    if isinstance(item, Arc):
        return Arc(item.end, item.mid, item.start)
    return item


def _reversed(items) -> tuple[Item, ...]:
    return tuple(_reverse(i) for i in reversed(items))


def chain(items) -> list[tuple[Item, ...]]:
    """Join lines and arcs end to end into closed runs, each item met at both ends by exactly
    one other. A circle is a run of its own."""
    runs: list[tuple[Item, ...]] = [(i,) for i in items if isinstance(i, Circle)]
    open_items = [i for i in items if not isinstance(i, Circle)]
    ends: dict[Point, list[int]] = {}
    for k, item in enumerate(open_items):
        if item.start == item.end:
            raise ShapeError(f"an item starts and ends at {show(item.start)}")
        for p in (item.start, item.end):
            ends.setdefault(p, []).append(k)
    for p, ks in ends.items():
        if len(ks) == 1:
            raise ShapeError(f"is open: the end at {show(p)} meets no other line or arc")
        if len(ks) > 2:
            raise ShapeError(f"branches: {len(ks)} ends meet at {show(p)}")
    used = [False] * len(open_items)
    for first in range(len(open_items)):
        if used[first]:
            continue
        run, k, at = [], first, open_items[first].start
        while not used[k]:
            used[k] = True
            item = open_items[k] if open_items[k].start == at else _reverse(open_items[k])
            run.append(item)
            at = item.end
            k = next((j for j in ends[at] if j != k), k)
        runs.append(tuple(run))
    return runs


def loop(items) -> Loop:
    """The closed run `items` as a Loop, turned to positive orientation. Raises ShapeError
    when it crosses or touches itself or cannot be bounded by polygons."""
    pieces = _pieces(items)
    problem = _self_meeting(pieces)
    if problem:
        raise ShapeError(f"the loop through {show(pieces[0].start)} {problem}")
    first = Loop(tuple(items)) if area2([p.start for p in pieces]) > 0 else Loop(_reversed(items))
    for tolerance in (TOLERANCE, TOLERANCE / 10, TOLERANCE / 100):
        for candidate in (first, Loop(_reversed(first.items))):
            try:
                bounds(candidate, tolerance)
                return candidate
            except ShapeError:
                pass
    raise ShapeError(f"the loop through {show(pieces[0].start)} cannot be bounded by polygons: an arc "
                     f"comes within {float(TOLERANCE / 100):g} mm of another edge, or two edges meet at a zero angle")


def start(lp: Loop) -> Point:
    """A point on the loop."""
    item = lp.items[0]
    return item.through if isinstance(item, Circle) else item.start


def inside(x: Point, lp: Loop) -> bool:
    """Whether x, a point off the loop, lies in its region."""
    for tolerance in (TOLERANCE, TOLERANCE / 10, TOLERANCE / 100, TOLERANCE / 1000):
        b = bounds(lp, tolerance)
        if where(x, b.inner) > 0:
            return True
        if where(x, b.outer) < 0:
            return False
    raise ShapeError(f"{show(x)} lies within {float(TOLERANCE / 1000):g} mm of the loop through {show(start(lp))}")


# --- Polygons that bound a loop ---------------------------------------------------------


def _grid(tolerance: Fraction) -> Fraction:
    g = Fraction(1)
    while g > tolerance / 100:
        g /= 10
    return g


def _snap(x: float, g: Fraction) -> Fraction:
    return Fraction(round(x / g)) * g


def _polar(b: _Bend) -> tuple[float, float, float, float, float]:
    cx, cy = float(b.center[0]), float(b.center[1])
    a0 = math.atan2(float(b.start[1]) - cy, float(b.start[0]) - cx)
    a1 = math.atan2(float(b.end[1]) - cy, float(b.end[0]) - cx)
    sweep = (a1 - a0) % (2 * math.pi)
    return cx, cy, math.sqrt(float(b.r2)), a0, sweep if b.ccw else sweep - 2 * math.pi


def _steps(sweep: float, cosine: float) -> int:
    """The fewest equal steps over `sweep` whose half-step has at least this cosine."""
    return max(1, math.ceil(abs(sweep) / (2 * math.acos(min(1.0, max(-1.0, cosine))) - 1e-12)))


def _turning(b: _Bend, path) -> bool:
    """The path's corners turn strictly one way about the centre, inside the bend's wedge."""
    c, s = b.center, 1 if b.ccw else -1
    rel = [_sub(p, c) for p in path]
    return (all(s * _cross(p, q) > 0 for p, q in zip(rel, rel[1:]))
            and all(s * _cross(rel[0], p) > 0 and s * _cross(p, rel[-1]) > 0 for p in rel[1:-1]))


def _d2(a: Point, b: Point) -> Fraction:
    d = _sub(a, b)
    return _dot(d, d)


def point_segment2(x: Point, p: Point, q: Point) -> Fraction:
    """The squared distance from x to the segment pq."""
    d = _sub(q, p)
    dd = _dot(d, d)
    t = min(Fraction(1), max(Fraction(0), _dot(_sub(x, p), d) / dd)) if dd else Fraction(0)
    return _d2(x, _add(p, _mul(d, t)))


def segment_segment2(p: Point, q: Point, r: Point, s: Point) -> Fraction:
    if p != q and r != s and _seg_seg(Segment(p, q), Segment(r, s)):
        return Fraction(0)
    return min(point_segment2(p, r, s), point_segment2(q, r, s), point_segment2(r, p, q), point_segment2(s, p, q))


def _chord(b: _Bend, tolerance: Fraction) -> tuple[list[Point], Fraction]:
    """Corners strictly inside the circle, turning one way inside the bend's wedge: with the
    bend's ends they make a path inside the closed disc."""
    cx, cy, r, a0, sweep = _polar(b)
    n = _steps(sweep, 1 - float(tolerance) / (2 * r))
    radius, g = r - min(float(tolerance) / 4, r / 4), _grid(tolerance)
    pts = [(_snap(cx + radius * math.cos(a0 + sweep * k / n), g), _snap(cy + radius * math.sin(a0 + sweep * k / n), g))
           for k in range(1, n)]
    path = [b.start, *pts, b.end]
    if any(_d2(p, b.center) >= b.r2 for p in pts) or not _turning(b, path):
        raise ShapeError(f"the arc at {show(b.start)} is too small for a {float(tolerance):g} mm grid")
    near = min(point_segment2(b.center, p, q) for p, q in zip(path, path[1:]))
    return pts, (b.r2 - near) / (sqrt_lo(b.r2) + sqrt_lo(near))


def _tangent(b: _Bend, tolerance: Fraction) -> tuple[list[Point], Fraction]:
    """Corners outside the circle, turning one way inside the bend's wedge, whose path misses
    the closed disc but for the bend's two ends."""
    cx, cy, r, a0, sweep = _polar(b)
    n = _steps(sweep, 1 / (1 + float(tolerance) / (2 * r)))
    step, g = sweep / n, _grid(tolerance)
    radius = r / math.cos(step / 2) + min(float(tolerance) / 4, r / 4)
    pts = [(_snap(cx + radius * math.cos(a0 + step * (k + 0.5)), g), _snap(cy + radius * math.sin(a0 + step * (k + 0.5)), g))
           for k in range(n)]
    c, r2 = b.center, b.r2
    clear = (all(_d2(p, c) > r2 for p in pts)
             and _dot(_sub(pts[0], c), _sub(b.start, c)) > r2 and _dot(_sub(pts[-1], c), _sub(b.end, c)) > r2
             and all(_cross(_sub(q, p), _sub(c, p)) ** 2 > r2 * _d2(p, q) for p, q in zip(pts, pts[1:])))
    if not clear or not _turning(b, [b.start, *pts, b.end]):
        raise ShapeError(f"the arc at {show(b.start)} is too small for a {float(tolerance):g} mm grid")
    far = max(_d2(p, c) for p in pts)
    return pts, (far - r2) / (2 * sqrt_lo(r2))


def _tidy(poly) -> tuple[Point, ...]:
    """The polygon without repeated corners and without corners that lie between their
    neighbours on one line."""
    pts = list(poly)
    i = 0
    while i < len(pts) and len(pts) > 3:
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
        if a == b or (_cross(_sub(b, a), _sub(c, b)) == 0 and _dot(_sub(b, a), _sub(c, b)) > 0):
            del pts[i]
            i = max(i - 1, 0)
        else:
            i += 1
    return tuple(pts)


@lru_cache(maxsize=4096)
def bounds(lp: Loop, tolerance: Fraction = TOLERANCE) -> Bounds:
    """The inner and outer polygons of a loop's region. Each arc is cut into bends of at most a
    quarter turn. A bend turning with the loop bulges out of the region's chord polygon, so
    `inner` takes its chord path and `outer` its tangent path; a bend turning against the loop
    takes the opposite two. Raises ShapeError when either polygon is not simple and positive,
    which `loop` reads as the wrong orientation or too coarse a tolerance."""
    inner: list[Point] = []
    outer: list[Point] = []
    deviation = Fraction(0)
    for p in _pieces(lp.items):
        inner.append(p.start)
        outer.append(p.start)
        if isinstance(p, _Bend):
            chord, tangent = _chord(p, tolerance), _tangent(p, tolerance)
            ins, outs = (chord, tangent) if p.ccw else (tangent, chord)
            inner += ins[0]
            outer += outs[0]
            deviation = max(deviation, ins[1], outs[1])
    result = Bounds(_tidy(inner), _tidy(outer), deviation)
    for name, poly in (("inner", result.inner), ("outer", result.outer)):
        problem = polygon_problem(poly)
        if problem:
            raise ShapeError(f"the {name} polygon of the loop through {show(inner[0])} {problem}")
    return result


# --- Polygons ---------------------------------------------------------------------------


def polygon_problem(poly) -> str | None:
    """Why the polygon is not simple and positively oriented, or None."""
    n = len(poly)
    if n < 3:
        return "has fewer than three corners"
    if area2(poly) <= 0:
        return "is not positively oriented"
    edges = [Segment(poly[i], poly[(i + 1) % n]) for i in range(n)]
    boxes = [_box(e) for e in edges]
    for i in range(n):
        for j in range(i + 1, n):
            if not _boxes_meet(boxes[i], boxes[j]):
                continue
            found = _seg_seg(edges[i], edges[j])
            if j == i + 1 or (i == 0 and j == n - 1):
                shared = edges[i].end if j == i + 1 else edges[i].start
                if found == _OVERLAP or found != [shared]:
                    return f"folds back at {show(shared)}"
            elif found:
                return f"crosses itself near {show(edges[i].start)}"
    return None


def where(x: Point, poly) -> int:
    """1 when x lies inside the polygon, 0 on its boundary, -1 outside."""
    odd = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i - 1], poly[i]
        if not min(y1, y2) <= x[1] <= max(y1, y2):
            continue
        if point_segment2(x, poly[i - 1], poly[i]) == 0:
            return 0
        if (y1 > x[1]) != (y2 > x[1]) and x[0] < x1 + (x[1] - y1) * (x2 - x1) / (y2 - y1):
            odd = not odd
    return 1 if odd else -1


def polygons_meet(a, b) -> bool:
    """Whether the boundaries of two polygons share a point."""
    ea = [Segment(a[i - 1], a[i]) for i in range(len(a))]
    eb = [Segment(b[i - 1], b[i]) for i in range(len(b))]
    bb = [_box(e) for e in eb]
    for e in ea:
        box = _box(e)
        if any(_boxes_meet(box, f_box) and _seg_seg(e, f) for f, f_box in zip(eb, bb)):
            return True
    return False


# --- Turns ------------------------------------------------------------------------------

_PI_LO = Fraction("3.1415926535897932384626433832795028841971")
_PI_HI = _PI_LO + Fraction(1, 10 ** 40)
_FINE = Fraction(1, 10 ** 24)


def _series(x: Fraction, odd: int, direction: int) -> Fraction:
    """A lower (direction -1) or upper (+1) bound on sin x (odd 1) or cos x (odd 0), for
    0 <= x < 1.6: thirty terms of the series, moved by the first term left out. From there
    on the terms alternate and shrink, so that term bounds the tail."""
    term, total = (x if odd else Fraction(1)), Fraction(0)
    for j in range(30):
        total += term
        term = -term * x * x / ((2 * j + 1 + odd) * (2 * j + 2 + odd))
    return total + direction * abs(term)


@lru_cache(maxsize=1024)
def turn(degrees: Fraction) -> tuple[Fraction, Fraction, Fraction]:
    """(c, s, e): decimals with |cos t - c| + |sin t - s| <= e, for the angle t of `degrees`.
    A multiple of 90 degrees is exact, with e = 0."""
    quarter, rest = divmod(Fraction(degrees) % 360, 90)
    c, s, e = Fraction(1), Fraction(0), Fraction(0)
    if rest:
        lo, hi = rest * _PI_LO / 180, rest * _PI_HI / 180
        sin_lo, sin_hi = _series(lo, 1, -1), Fraction(1) if 2 * hi >= _PI_LO else _series(hi, 1, 1)
        cos_lo, cos_hi = _series(hi, 0, -1), _series(lo, 0, 1)
        c = Fraction(round((cos_lo + cos_hi) / 2 / _FINE)) * _FINE
        s = Fraction(round((sin_lo + sin_hi) / 2 / _FINE)) * _FINE
        e = math.ceil((max(cos_hi - c, c - cos_lo) + max(sin_hi - s, s - sin_lo)) / _FINE ** 2) * _FINE ** 2
    for _ in range(int(quarter)):
        c, s = -s, c
    return c, s, e


def _image(p: Point, at: Point, c: Fraction, s: Fraction) -> Point:
    """KiCad's rotation of p by the angle with cosine c and sine s, then the move to `at`:
    x' = x c + y s, y' = -x s + y c. A positive angle turns counter-clockwise on KiCad's
    screen, whose y axis points down."""
    return (at[0] + p[0] * c + p[1] * s, at[1] - p[0] * s + p[1] * c)


def place(local: Point, at: Point, degrees: Fraction) -> Spot:
    """Where a point of a footprint lands on the board: turned by `degrees` about the
    footprint's origin, then moved to `at`."""
    c, s, e = turn(degrees)
    exact = _image(local, at, c, s)
    if e == 0:
        return Spot(exact, Fraction(0))
    near = (_snap_q(exact[0]), _snap_q(exact[1]))
    error = e * (abs(local[0]) + abs(local[1])) + abs(near[0] - exact[0]) + abs(near[1] - exact[1])
    return Spot(near, math.ceil(error / _ERROR_GRID) * _ERROR_GRID)


_ERROR_GRID = Fraction(1, 10 ** 15)
"""A Spot's error is rounded up to this grid, mm, so it stays sound and short."""


def _snap_q(x: Fraction) -> Fraction:
    return Fraction(round(x / SPOT_GRID)) * SPOT_GRID


def moved(b: Bounds, at: Point, degrees: Fraction) -> Bounds:
    """The bounds of a region turned by `degrees` about the origin and moved to `at`. A
    multiple of 90 degrees maps each corner exactly. Any other angle turns each polygon with
    the decimal cosine and sine of `turn`, which moves no point by more than `reach`, then
    grows `outer` and shrinks `inner` by more than that, checking exactly that every edge
    keeps further than `reach` from the polygon it came from."""
    c, s, e = turn(degrees)
    inner = tuple(_image(p, at, c, s) for p in b.inner)
    outer = tuple(_image(p, at, c, s) for p in b.outer)
    if e == 0:
        return Bounds(inner, outer, b.deviation)
    reach = e * max(abs(x) + abs(y) for x, y in b.inner + b.outer)
    grown, d_out = _offset(outer, reach, 1)
    shrunk, d_in = _offset(inner, reach, -1)
    return Bounds(shrunk, grown, b.deviation + reach + max(d_out, d_in))


def _offset(poly, reach: Fraction, sign: int) -> tuple[tuple[Point, ...], Fraction]:
    """A polygon whose boundary keeps further than `reach` from poly's, outside it (sign 1)
    or inside it (sign -1), and a bound on how far the two boundaries lie apart."""
    n = len(poly)
    f = [(float(x), float(y)) for x, y in poly]
    for k in range(4):
        d = float(reach + 4 * SPOT_GRID) * 2 ** k
        out = []
        for i in range(n):
            a, b, c = f[i - 1], f[i], f[(i + 1) % n]
            n1, n2 = _normal(a, b), _normal(b, c)
            m = 1 + n1[0] * n2[0] + n1[1] * n2[1]
            out.append((_snap_q(Fraction(b[0] + sign * d * (n1[0] + n2[0]) / m)),
                        _snap_q(Fraction(b[1] + sign * d * (n1[1] + n2[1]) / m))))
        moved_poly = tuple(out)
        if _keeps_apart(poly, moved_poly, reach, sign):
            far = max(max(point_segment2(moved_poly[i], poly[i], poly[(i + 1) % n]),
                          point_segment2(moved_poly[(i + 1) % n], poly[i], poly[(i + 1) % n]),
                          point_segment2(poly[i], moved_poly[i], moved_poly[(i + 1) % n]),
                          point_segment2(poly[(i + 1) % n], moved_poly[i], moved_poly[(i + 1) % n])) for i in range(n))
            return moved_poly, sqrt_hi(far)
    raise ShapeError(f"cannot keep a turned polygon at {show(poly[0])} apart from its offset")


def _normal(a, b) -> tuple[float, float]:
    """The unit normal on the right of a to b: outward for a positive polygon."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    return dy / length, -dx / length


def _keeps_apart(poly, other, reach: Fraction, sign: int) -> bool:
    """`other` is simple and positive, holds poly (sign 1) or lies in it (sign -1), and no edge
    of one comes within `reach` of an edge of the other. Then every point of the inner one
    lies further than `reach` from the outer one's boundary."""
    if polygon_problem(other):
        return False
    outer, inner = (other, poly) if sign > 0 else (poly, other)
    if any(where(p, outer) <= 0 for p in inner):
        return False
    r2 = reach * reach
    boxes = [_box(Segment(outer[j - 1], outer[j])) for j in range(len(outer))]
    for i in range(len(inner)):
        box = _box(Segment(inner[i - 1], inner[i]))
        for j in range(len(outer)):
            if _boxes_meet(box, boxes[j]) and segment_segment2(inner[i - 1], inner[i], outer[j - 1], outer[j]) <= r2:
                return False
    return True


# --- Holes ------------------------------------------------------------------------------


def stadium(p: Point, q: Point, radius: Fraction, error: Fraction, tolerance: Fraction = TOLERANCE) -> Bounds:
    """Bounds of the points within `radius` of the segment pq, a round hole when p = q, when p
    and q may each be off by `error`. `inner` is convex with every corner nearer than
    radius - error to pq, so it lies in the true region. `outer` is convex with every edge's
    line further than radius + error from both p and q, on the inner side, so it holds the
    true region."""
    lo, hi = radius - error, radius + error
    if lo <= 0:
        raise ShapeError(f"the hole at {show(p)} is smaller than the error {float(error):g} mm of its place")
    px, py, qx, qy = float(p[0]), float(p[1]), float(q[0]), float(q[1])
    axis = math.atan2(qy - py, qx - px) if p != q else 0.0
    g = _grid(tolerance)

    def ring(r: float, n: int, corners: list[float]) -> tuple[Point, ...]:
        pts = []
        for cx, cy, a in ((qx, qy, axis - math.pi / 2), (px, py, axis + math.pi / 2)):
            pts += [(_snap(cx + r * math.cos(a + k * math.pi / n), g), _snap(cy + r * math.sin(a + k * math.pi / n), g))
                    for k in corners]
        return _tidy(pts)

    n_in = _steps(math.pi, 1 - float(tolerance) / (2 * float(lo)))
    inner = ring(float(lo) - min(float(tolerance) / 4, float(lo) / 4), n_in, [k for k in range(n_in + 1)])
    n_out = _steps(math.pi, 1 / (1 + float(tolerance) / (2 * float(hi))))
    outer = ring(float(hi) / math.cos(math.pi / (2 * n_out)) + min(float(tolerance) / 4, float(hi) / 4), n_out,
                 [k + 0.5 for k in range(n_out)])
    ok = (_convex(inner) and _convex(outer) and where(p, inner) > 0 and where(q, inner) > 0
          and all(point_segment2(v, p, q) < lo * lo for v in inner)
          and all(_cross(_sub(b, a), _sub(x, a)) > 0 and _cross(_sub(b, a), _sub(x, a)) ** 2 > hi * hi * _d2(a, b)
                  for a, b in zip(outer, outer[1:] + outer[:1]) for x in (p, q)))
    if not ok:
        raise ShapeError(f"cannot bound the hole at {show(p)} at a {float(tolerance):g} mm grid")
    near = min(segment_segment2(a, b, p, q) for a, b in zip(inner, inner[1:] + inner[:1]))
    far = max(point_segment2(v, p, q) for v in outer)
    return Bounds(inner, outer, max(hi - sqrt_lo(near), sqrt_hi(far) - lo))


def _convex(poly) -> bool:
    n = len(poly)
    return (n >= 3 and polygon_problem(poly) is None
            and all(_cross(_sub(poly[i], poly[i - 1]), _sub(poly[(i + 1) % n], poly[i])) > 0 for i in range(n)))
