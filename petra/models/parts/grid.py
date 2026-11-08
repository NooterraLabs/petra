"""The three-valued cell grid: which cells are surely material, surely empty, or unsure. Trusted.

A cell is IN when the closed cell lies inside the part, OUT when it misses the part, and
ON when it meets the surface. Classification is exact: a separating-axis test of each
closed cell against each closed triangle in integer coordinates, then 6-connected
components of the non-ON cells, then one parity ray per component. Every measure the grid
serves (reach.py) counts ON against the part, so a coarse grid can only turn an answer
into UNKNOWN, never into a wrong PASS or FAIL.

The cell side is a solver budget, not a premise: no verdict rests on it, because a sound
grid at any side gives the same PASS and FAIL. engine.py chooses it and refines where a
rule stays undecided.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import numpy as np

from ...kernel import Q
from .space import Solid


class Cell(IntEnum):
    OUT = 0
    IN = 1
    ON = 2


@dataclass(frozen=True)
class CellGrid:
    """Built only by `classify` or `refine`, with read-only arrays."""

    solids: tuple[str, ...]            # the mesh sha256 of each solid it classifies, in order
    h: Q                               # cell side, mm, a power of two
    origin: tuple[int, int, int]       # in cells of the coarsest side, so refinements nest
    state: np.ndarray                  # (nx, ny, nz) uint8 of Cell, read-only
    owner: np.ndarray                  # (nx, ny, nz) int16: which solid an IN or ON cell belongs to, -1 for OUT
    stock: np.ndarray                  # (nx, ny, nz) bool: cells material must be removed from when OUT
    parent: "CellGrid | None"          # a refinement window reads columns that leave it here


def classify(solids: tuple[Solid, ...], h: Q, stock: tuple[tuple[Q, Q, Q], tuple[Q, Q, Q]]) -> CellGrid:
    """Classify every cell of the stock box, padded by one cell, against the placed solids.
    The candidate cells of a triangle come from a slab scan along its dominant axis, so
    the cost follows the surface cells and not the triangle's bounding box. The
    separating-axis test uses int64 when every product stays below 2^62 (checked per
    triangle) and Python integers otherwise."""
    raise NotImplementedError


def refine(grid: CellGrid, solids: tuple[Solid, ...], region: np.ndarray, halo: Q) -> CellGrid:
    """A window at h/2 over `region` grown by `halo` mm. An IN or OUT parent passes its
    state to its eight children exactly; only ON parents run the separating-axis test
    again, against the triangles that met them. Columns that leave the window read their
    obstacle heights from `grid`, the pessimistic end for the pessimistic count and the
    optimistic end for the optimistic count."""
    raise NotImplementedError
