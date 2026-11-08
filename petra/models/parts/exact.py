"""The exact evaluator: every question about one placement, on exact rational coordinates. Trusted.

Each measure reduces to finitely many orientation signs and squared distances between
triangles, segments and points, all rational for rational vertices. Python integers carry
them; numpy only gathers candidates. No float enters a result.

Candidates come from a broad phase over closed axis-aligned boxes, grown by the distance
that matters. Two triangles whose grown boxes miss cannot matter, so the broad phase only
ever drops pairs that are farther apart than the question asks about. That completeness,
the parity count, and the choice of which pair is closest are what the engine is trusted
for; the kernel re-checks each witness's geometry over its premises' ranges (build.py).
"""
from __future__ import annotations

from typing import Iterator

from ...kernel import Q
from .mesh import Mesh, Point
from .space import Axis, Bracket, Crossing, Overlap, Solid, Sweep


def candidates(a: Solid, b: Solid, pad: Q) -> Iterator[tuple[int, int]]:
    """Pairs (triangle of a, triangle of b) whose closed bounding boxes, each grown by
    `pad` mm, meet. Every pair closer than `pad` is among them."""
    raise NotImplementedError


def self_crossing(mesh: Mesh) -> Crossing | None:
    """The first pair of the mesh's own triangles that cross properly, or None. Triangles
    that share an edge or a vertex meet there and do not count."""
    raise NotImplementedError


def overlap(a: Solid, b: Solid) -> Overlap:
    """Whether the interiors of a and b overlap. A proper crossing (an edge of one through
    the open interior of a triangle of the other, with the two orientation signs strict)
    is overlap. Coplanar faces with opposite outward sides are contact and are not. When
    no pair crosses, a vertex of each body is tested for parity inside the other. A
    contact the signs cannot classify (an edge lying on a face, coplanar faces with the
    same side) leaves the answer undecided, which the engine reports as a Gap."""
    raise NotImplementedError


def gap(a: Solid, b: Solid, within: Q) -> Bracket:
    """The least distance between a and b when it is below `within` mm, exactly: a
    bracket of squared distance (mm^2) with lo == hi and a Near witness. When every pair
    is at least `within` apart the bracket is [within^2, within^2] with no witness. Bodies
    that touch give 0."""
    raise NotImplementedError


def clearance(sweep: Sweep) -> Bracket | Overlap:
    """Answer a Sweep whose mover has one placement: a Solid, or a Placed profile at a
    point (a pin through a declared hole, a driver down to a screw head). The mover is
    swept along the axis over the travel. A proper crossing between the swept mover and an
    obstacle is an Overlap. Otherwise the answer is the least sideways distance squared
    (mm^2) between the two bodies' open cross-sections at any common level, as a bracket
    with lo == hi and a Near witness; for a profile, its band radius is subtracted before
    squaring. Pairs whose open extents along the axis share no level never meet sideways,
    which is why a seat at the end of the travel is not a clash."""
    raise NotImplementedError


def seat(solid: Solid, centre: Point, facing: Axis, inner: Q, outer: Q) -> Bracket:
    """How much of a bearing ring misses the part: the ring between radii `inner` and
    `outer` (mm) about `centre`, in the plane normal to `facing`, must lie in the union of
    the part's faces that face `facing` in that plane. The answer is the widest radial
    gap (mm) where a boundary edge of that union crosses the open ring, 0 when none does."""
    raise NotImplementedError


def slopes(solid: Solid, up: Axis, ratio: Q, plate: Q | None) -> Bracket:
    """Faces whose outward normal points against `up` more steeply than `ratio` allows:
    |n_side|^2 < ratio^2 n_up^2 with n_up < 0. Faces on the plate (every vertex at height
    `plate`) are skipped. The answer is their total area projected on the plane normal to
    `up` (mm^2), which is rational, with the largest such face as the witness. Overhang
    for printing and draft for molding read this with their own rows."""
    raise NotImplementedError


def prism(mesh: Mesh, normal: Axis, thickness: Q) -> Bracket:
    """How far the mesh departs from an extrusion of `thickness` mm along `normal`: every
    vertex at one of two levels `thickness` apart, and every face either in one of those
    levels or parallel to `normal`. The answer is 0 for a true prism, else the largest
    distance (mm) of an offending vertex from the nearer level, with its spot."""
    raise NotImplementedError


def extent(solid: Solid) -> tuple[Point, Point]:
    """The closed bounding box of the placed solid, exact."""
    raise NotImplementedError
