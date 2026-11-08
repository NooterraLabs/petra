"""A part's mesh: STL or 3MF bytes to exact coordinates. Trusted; the boundary for mesh files.

The part is the parity solid of the triangle set: the points a generic ray from them
crosses an odd number of times. Every edge is used an even number of times, so that set
does not depend on the ray. Lowering (lower.py) also refuses a surface that crosses
itself, because a mesh made by concatenating two overlapping bodies would otherwise read
as their symmetric difference.

Coordinates are exact. A float32 in a binary STL is read as the shortest decimal that
round-trips to it (numpy's `format_float_positional` with `unique=True`), so a CAD export
of 25.1 mm reads as 251/10 mm, the same rational a design line `25.1 mm` gives, and two
parts drawn to touch do touch. ASCII STL and 3MF decimals are read as written. Every
coordinate is then an integer over one power of ten, `Mesh.scale`.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np

from ...kernel import Q
from ..base import ComponentError

Point = tuple[Q, Q, Q]
"""Exact coordinates in millimetres. Statements convert to metres at their boundary (build.py)."""


class Unit(Enum):
    """The unit a mesh file's numbers are in. STL carries none, so the design names it."""

    MM = "mm"
    INCH = "inch"


class MeshError(ComponentError):
    """A mesh file Petra refuses: a hash that differs from the design's, an unknown format,
    a non-finite coordinate, an edge used an odd number of times, a 3MF with more than one
    object, or a coordinate too fine or too large for int64 at the file's scale. The
    message names the file, the rule broken and the first offending edge or coordinate."""


@dataclass(frozen=True)
class Mesh:
    """A closed (mod 2) triangle mesh with exact coordinates. Only `read_mesh` builds one."""

    path: str
    sha256: str
    scale: int                 # coordinates are integers in units of 1/scale mm; a power of ten
    vertices: np.ndarray       # (n, 3) int64, read-only; equal points merged
    triangles: np.ndarray      # (m, 3) int64 indices into vertices, read-only

    def point(self, index: int) -> Point:
        """Vertex `index` in millimetres, exact."""
        raise NotImplementedError

    def bounds(self) -> tuple[Point, Point]:
        """The closed axis-aligned box of the vertices, low corner then high corner."""
        raise NotImplementedError


def read_mesh(path: Path, sha256: str, unit: Unit) -> Mesh:
    """Read a binary or ASCII STL (sniffed) or a 3MF (a zip with one object, its build
    transform applied exactly from the decimal text). Check the sha256 of the file bytes,
    convert to millimetres exactly (an inch is 127/5 mm), merge equal vertices, and require
    every edge to be used an even number of times. Memoised on (path, sha256, unit), so an
    assembly that places a part reads its file once. Raises MeshError."""
    raise NotImplementedError
