"""Directions, turns and placements. Trusted.

Directions are the six part-frame axes and placements turn only by the 24 rotations that
map axes to axes, so every placed coordinate stays exact.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
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
