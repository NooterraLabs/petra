"""J3.11a's clear distance lc along any direction, in a plate with holes.

J3.11a measures lc in the direction of the force, from the edge of the hole to the edge of the
adjacent hole or of the material. Here that is taken along the force's line through the bolt's
center: from where the line leaves the bolt's own hole to where it first meets the plate's edge or
another hole.

A hole is a stadium, a disk of the short dimension drawn out along the long axis, with `along`
its vertical and `across` its horizontal dimension, as twin.data.Hole gives them. The plate is an
intersection of half-planes (nx, ny, c), each holding the points with nx x + ny y <= c, so a line
from inside leaves through the nearest half-plane it faces. Floats throughout.
"""

import math

_EPS = 1e-12


def clear_distances(centers, directions, hole, edges=()):
    """lc for each bolt along its own unit direction, or None where the line meets no edge and no
    other hole."""
    shapes = [_stadium(hole, c) for c in centers]
    out = []
    for i, ((px, py), (ux, uy)) in enumerate(zip(centers, directions)):
        reach = _leave_plate(px, py, ux, uy, edges)
        for j, shape in enumerate(shapes):
            if j != i:
                t = _enter(px, py, ux, uy, shape)
                if t is not None:
                    reach = min(reach, t)
        out.append(None if math.isinf(reach) else reach - _leave(px, py, ux, uy, shapes[i]))
    return out


def _stadium(hole, center):
    """((cx, cy), (ax, ay), h, r): the center, the unit long axis, the half-length of the straight
    part and the radius."""
    along, across = float(hole.along), float(hole.across)
    r = min(along, across) / 2
    h = abs(along - across) / 2
    axis = (0.0, 1.0) if along > across else (1.0, 0.0)
    return center, axis, h, r


def _pieces(shape):
    """A stadium as two disks and, when it is a slot, the rectangle between them."""
    (cx, cy), (ax, ay), h, r = shape
    disks = [((cx + ax * h, cy + ay * h), r), ((cx - ax * h, cy - ay * h), r)]
    return disks, (shape if h > 0 else None)


def _disk_span(px, py, ux, uy, center, r):
    dx, dy = px - center[0], py - center[1]
    b = dx * ux + dy * uy
    disc = b * b - (dx * dx + dy * dy - r * r)
    if disc < 0:
        return None
    root = math.sqrt(disc)
    return -b - root, -b + root


def _box_span(px, py, ux, uy, shape):
    (cx, cy), (ax, ay), h, r = shape
    lo, hi = -math.inf, math.inf
    for (kx, ky), half in (((ax, ay), h), ((-ay, ax), r)):
        p = (px - cx) * kx + (py - cy) * ky
        u = ux * kx + uy * ky
        if abs(u) < _EPS:
            if abs(p) > half:
                return None
            continue
        t1, t2 = (-half - p) / u, (half - p) / u
        lo, hi = max(lo, min(t1, t2)), min(hi, max(t1, t2))
    return (lo, hi) if lo <= hi else None


def _spans(px, py, ux, uy, shape):
    disks, box = _pieces(shape)
    spans = [_disk_span(px, py, ux, uy, c, r) for c, r in disks]
    if box is not None:
        spans.append(_box_span(px, py, ux, uy, box))
    return [s for s in spans if s is not None]


def _enter(px, py, ux, uy, shape):
    """Where a line from outside a stadium first enters it ahead of the start, or None."""
    starts = [lo for lo, hi in _spans(px, py, ux, uy, shape) if hi >= 0]
    return max(0.0, min(starts)) if starts else None


def _leave(px, py, ux, uy, shape):
    """Where a line from a stadium's center leaves it. The stadium is convex, so that is the
    farthest exit of its pieces."""
    return max(hi for _, hi in _spans(px, py, ux, uy, shape))


def _leave_plate(px, py, ux, uy, edges):
    reach = math.inf
    for nx, ny, c in edges:
        toward = nx * ux + ny * uy
        if toward > _EPS:
            reach = min(reach, (c - nx * px - ny * py) / toward)
    return reach
