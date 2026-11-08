"""The grid evaluator: every question about every placement. Trusted.

Three measures, each computed twice. The pessimistic count takes ON cells as obstacles
when blocking and as unreached when covering, and can only prove PASS. The optimistic
count takes IN cells only, and can only prove FAIL. Between them lies the doubt, which
engine.py refines or reports as UNKNOWN.

    reach      a Sweep whose mover is Placed Everywhere: per direction, a height field of
               the obstacles, max-filtered by each band's stencil and min-filtered by the
               cut's, gives the first layer each column is reached from. Milling cutters,
               router bits, a laser's beam and a mold's pull are all this.
    thickness  the opening of the material (or of the empty space) by a body: a ball, or
               a flat disk one layer thick for a printer's line. Slivers, ribs, minimum
               walls, minimum webs and holes too small for a laser are all this.
    passage    the widest ball that can travel from one region to another through empty
               space. A guard must pass no ball of its test size; a powder-bed part must
               pass a ball of its escape size from every closed void.

Every max or min filter is a max over centred rectangles of two 1-D filters, so the cost
is linear in cells per stencil rectangle.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from ...kernel import Q
from .grid import CellGrid
from .mesh import Point
from .space import Bracket, Sweep


@dataclass(frozen=True)
class Stencil:
    """Disk offsets in cells as a union of centred rectangles, and the closed-form R4
    statement that certifies them. One function makes both, so they cannot drift."""

    radius: Q
    h: Q
    side: Literal["outer", "inner", "strict"]
    rectangles: tuple[tuple[int, int], ...]


def stencil(radius: Q, h: Q, side: Literal["outer", "inner", "strict"]) -> Stencil:
    """outer: every cell a disk of `radius` centred anywhere in cell 0 meets. inner: the
    cells inside the disk centred at cell 0's centre. strict: the cells every such disk
    overlaps in their interior."""
    raise NotImplementedError


@dataclass(frozen=True)
class Reached:
    """For one Sweep (one tool, one direction), per column, the first layer from which
    every cell is reached. pess <= truth <= opt holds cell by cell, which the twin and
    MR3 test."""

    grid: CellGrid
    sweep: Sweep
    pess: np.ndarray       # (n1, n2) int32 in the direction's frame
    opt: np.ndarray


def reach(grid: CellGrid, sweep: Sweep) -> Reached:
    """Answer a Sweep whose mover is Placed Everywhere, along `sweep.along`. A setup, a
    pull, its opposite and a sheet's normal are each one Sweep."""
    raise NotImplementedError


def unreached(reached: tuple[Reached, ...], tolerance: Q) -> Bracket:
    """The deepest stock cell that no Reached covers, as a distance from the part (mm),
    with the cell witnesses. Pass one Reached per (tool, direction) the rule allows."""
    raise NotImplementedError


def thickness(grid: CellGrid, radius: Q, height: Q | None, empty: bool) -> Bracket:
    """The deepest point (mm) of the material, or of the empty space when `empty`, that
    no body of `radius` (a ball, or a disk `height` thick when given) fitting inside it
    reaches. Computed in the band within radius + h sqrt(3) of the other side, by exact
    squared distances between cell boxes."""
    raise NotImplementedError


def ratio(grid: CellGrid, thin: Q) -> Bracket:
    """The worst thin wall's free height over its thickness, for walls thinner than `thin`
    mm: chatter when milling, sink when molding."""
    raise NotImplementedError


def directions_needed(reached: tuple[Reached, ...], tolerance: Q) -> Bracket:
    """The fewest directions whose reach covers the stock, trying every subset of the
    allowed ones (at most 64 for six directions)."""
    raise NotImplementedError


def passage(grid: CellGrid, start: tuple[Point, Point], goal: tuple[Point, Point]) -> Bracket:
    """The diameter (mm) of the widest ball that can travel through empty space from the
    `start` box to the `goal` box. Pessimistic and optimistic free spaces come from the
    outer and strict stencils of each candidate radius; the widest path is a
    maximum-bottleneck search over cells. The witness is the narrowest cell of the path."""
    raise NotImplementedError
