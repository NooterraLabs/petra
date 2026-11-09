"""Placements, moving bodies, the one query fit and reach share, and its answers. Trusted.

The query is `Sweep`: can a mover travel along an axis without entering the obstacles,
keeping a clearance from them sideways? The mover is a placed mesh (a board sliding into
its case, a lid, a plug body) or a body of revolution (a pin through a hole, a driver to a
screw head, a cutter, a mold's pull). A mover with one placement goes to the exact
evaluator; a profile placed `Everywhere` is the reach question and goes to the grid. The
caller never picks the evaluator: engine.ask reads it from the mover's placement.

Directions are the six part-frame axes and placements turn only by the 24 rotations that
map axes to axes, so every placed coordinate stays exact.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Union

from ...kernel import Q
from .mesh import Mesh, Point


class Axis(Enum):
    """The six part-frame directions. Top is +z."""

    TOP = (0, 0, 1)
    BOTTOM = (0, 0, -1)
    RIGHT = (1, 0, 0)
    LEFT = (-1, 0, 0)
    BACK = (0, 1, 0)
    FRONT = (0, -1, 0)

    @property
    def opposite(self) -> Axis:
        return Axis(tuple(-c for c in self.value))


@dataclass(frozen=True)
class Turn:
    """A rotation that maps axes to axes: a signed permutation matrix with determinant +1.
    Built by `turn`. Mirrors are refused, because no placement mirrors a real part."""

    rows: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]

    def apply(self, p: Point) -> Point:
        return tuple(r[0] * p[0] + r[1] * p[1] + r[2] * p[2] for r in self.rows)

    def axis(self, a: Axis) -> Axis:
        return Axis(self.apply(a.value))


def turn(top: Axis, front: Axis) -> Turn:
    """The rotation that takes a body's own top to `top` and its own front to `front`.
    Raises ValueError when the two are parallel. Its columns are the images of +x, +y and
    +z: +z goes to `top`, +y (the body's back) to the opposite of `front`, and +x to their
    cross product, so the determinant is +1."""
    t, b = top.value, front.opposite.value
    if sum(i * j for i, j in zip(t, b)):
        raise ValueError(f"a placement's top ({top.value}) and front ({front.value}) must be perpendicular")
    x = (b[1] * t[2] - b[2] * t[1], b[2] * t[0] - b[0] * t[2], b[0] * t[1] - b[1] * t[0])
    return Turn(tuple((x[k], b[k], t[k]) for k in range(3)))


IDENTITY = Turn(((1, 0, 0), (0, 1, 0), (0, 0, 1)))


@dataclass(frozen=True)
class Placement:
    """Where a body sits in an assembly: turned about its own origin, then moved by `offset` (mm)."""

    turn: Turn
    offset: Point

    def apply(self, p: Point) -> Point:
        q = self.turn.apply(p)
        return (q[0] + self.offset[0], q[1] + self.offset[1], q[2] + self.offset[2])


@dataclass(frozen=True)
class Solid:
    """A part's or a board's mesh where an assembly places it."""

    name: str
    mesh: Mesh
    placement: Placement


@dataclass(frozen=True)
class Band:
    depth: Q       # mm along the sweep direction, back from the tip, where this band starts
    radius: Q      # mm, the body's radius from that depth on


@dataclass(frozen=True)
class Profile:
    """A body of revolution about the sweep direction: the union of the semi-infinite
    cylinders of its bands, ended at `span` when one is given. Depths rise strictly from 0
    and radii never fall, so every profile is a union of semi-infinite cylinders and a
    height field decides where it fits."""

    bands: tuple[Band, ...]
    span: Q | None

    def __post_init__(self) -> None:
        if not self.bands or self.bands[0].depth != 0:
            raise ValueError("a profile's first band starts at its tip")
        for a, b in zip(self.bands, self.bands[1:]):
            if not (a.depth < b.depth and a.radius <= b.radius):
                raise ValueError("band depths must rise and radii must not fall")


@dataclass(frozen=True)
class Cut:
    """The part of a profile that removes material: radius 0 is a ray (a mold's pull);
    corner 0 is a flat end and corner == radius a ball end."""

    radius: Q
    corner: Q


@dataclass(frozen=True)
class Everywhere:
    """Every placement of a profile's axis over the stock: the reach question."""

    stock: tuple[Point, Point]


@dataclass(frozen=True)
class Placed:
    """A profile with its tip at `at`, or at every placement, cutting with `cut` (None for
    a pin, a driver or a plug, which cut nothing)."""

    profile: Profile
    at: Point | Everywhere
    cut: Cut | None


@dataclass(frozen=True)
class Sweep:
    """Can `mover` come `travel` mm back along `along` (None: from outside every obstacle)
    to where it is placed, entering no obstacle's interior and keeping at least
    `clearance` mm from each sideways? Sideways means in the plane normal to `along`,
    between the open cross-sections of the two bodies at one level, so faces that meet
    head on at the end of the travel (a board on its standoffs) are a seat, not a clash."""

    mover: Solid | Placed
    along: Axis
    travel: Q | None
    obstacles: tuple[Solid, ...]
    clearance: Q


# --- Answers -------------------------------------------------------------------------


@dataclass(frozen=True)
class Spot:
    """A point on one triangle of one body, in the assembly frame, exact."""

    body: str
    triangle: int
    point: Point


@dataclass(frozen=True)
class Crossing:
    """An edge of a triangle of one body passes through the open interior of a triangle of
    another, so the two bodies' interiors overlap near `at`. The kernel re-checks the
    orientation signs (build.py)."""

    edge: tuple[Spot, Spot]
    face: Spot
    at: Point


@dataclass(frozen=True)
class Near:
    """Two spots at squared distance `dist2` (mm^2): the pair that sets a bracket's end."""

    a: Spot
    b: Spot
    dist2: Q


@dataclass(frozen=True)
class Cells:
    """A grid witness: the deciding cell, its side, and the boxes that bound its measure.
    For a PASS, `neighbour` is the non-OUT cell that bounds the depth; for a FAIL,
    `obstructers` are the merged IN boxes every placement through the cell hits."""

    cell: tuple[int, int, int]
    h: Q
    neighbour: tuple[int, int, int] | None
    obstructers: tuple[tuple[Point, Point], ...]
    unreached_by: tuple[tuple[str, Axis], ...]


Witness = Union[Crossing, Near, Cells]


@dataclass(frozen=True)
class Bracket:
    """The true value of a measure lies in [lo, hi] (mm, mm^2 or 1, by measure). The exact
    evaluator returns lo == hi; the grid returns the optimistic count as lo and the
    pessimistic count, with unsure cells against the part, as hi. `worst` sets hi and its
    geometry becomes the PASS lemma; `witness` sets lo and becomes the FAIL lemma."""

    lo: Q
    hi: Q
    worst: Witness | None
    witness: Witness | None

    def __post_init__(self) -> None:
        if self.lo > self.hi:
            raise ValueError("a bracket's lo exceeds its hi")


@dataclass(frozen=True)
class Overlap:
    """Whether two placed bodies' interiors overlap. Touching faces do not. `witness` is a
    crossing pair, or a vertex of one body that lies inside the other by parity when no
    surfaces cross; None when the evaluator proved the interiors disjoint."""

    witness: Crossing | Spot | None


Answer = Union[Bracket, Overlap]
