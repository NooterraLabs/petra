"""A KiCad board file to exact board geometry. Trusted; the boundary for `.kicad_pcb` files.

A reader in the sense of docs/plan.md P6: it fills the design and never decides a verdict.
It reads KiCad 6 and later (file version 20211014 or newer) with the standard library
only, because the format is S-expressions. It reads:

    the board outline   Edge.Cuts lines, arcs, circles, rectangles and polygons, chained
                        into closed loops; the outermost loop is the outline, the rest
                        are cutouts
    the thickness       (general (thickness ...))
    the holes           every pad with a drill, plated or not, and every mounting hole
    the keep-outs       each footprint's courtyard (F.CrtYd or B.CrtYd) and its side

KiCad's y axis points down the screen. The reader turns it up, so the board frame has x
right, y up and z up from the board's bottom face. A footprint or pad turned by a multiple
of 90 degrees is placed exactly. Any other angle is placed with a rational rotation within
2^-30 rad of it, and the reader moves every affected edge by that bound toward the side
that makes a fit harder: keep-outs grow and drills shrink.

Component heights are not in the file. A footprint property named `Height` (mm), when the
board's author set one, is read as the design's value. Otherwise the `pcb` block states
the height as a signed bound (lower.py), and a component with neither is a Gap needing
NeedsInputBound, never a default.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Union

from ...kernel import Q
from ..base import ComponentError

Point2 = tuple[Q, Q]
"""Exact board-frame coordinates in millimetres."""


class BoardError(ComponentError):
    """A board file Petra refuses: a hash that differs from the design's, a file version
    older than KiCad 6, unbalanced parentheses or a bad string escape, an outline that
    does not close, two outer loops, or a drill outside the outline. The message names
    the file, the line and the S-expression."""


@dataclass(frozen=True)
class Form:
    """One parenthesised S-expression: its head symbol and its arguments. A number is an
    exact Fraction of its decimal text; a symbol and a quoted string are both str."""

    head: str
    args: tuple[Union["Form", str, Q], ...]

    def find(self, head: str) -> tuple["Form", ...]:
        """The direct child forms with this head, in file order."""
        raise NotImplementedError


def parse_sexpr(text: str) -> Form:
    """Parse one top-level S-expression. Raises BoardError on unbalanced parentheses, an
    unterminated string or a bad escape, naming the line."""
    raise NotImplementedError


@dataclass(frozen=True)
class Segment:
    a: Point2
    b: Point2


@dataclass(frozen=True)
class Arc:
    """A circular arc through start, mid and end. The centre is rational (the circle
    through three rational points); the radius may not be, so its square is kept."""

    start: Point2
    mid: Point2
    end: Point2
    centre: Point2
    radius2: Q


Edge = Union[Segment, Arc]


@dataclass(frozen=True)
class Loop:
    """A closed chain of edges, each ending where the next starts, exactly."""

    edges: tuple[Edge, ...]


class Side(Enum):
    TOP = "top"
    BOTTOM = "bottom"


@dataclass(frozen=True)
class Drill:
    """A drilled hole: a round drill has width == length; an oval one is a slot along x
    of the pad's own frame, turned with the pad."""

    ref: str            # the footprint's reference, "H1", "J1"
    pad: str            # the pad's number, "" for a mounting hole's single pad
    centre: Point2
    width: Q
    length: Q
    turn: Q             # degrees, the pad's absolute angle
    plated: bool


@dataclass(frozen=True)
class Keepout:
    """Where one footprint's body stands: its courtyard on its side of the board, and the
    height the file gives, if any."""

    ref: str
    side: Side
    courtyard: tuple[Loop, ...]
    height: Q | None


@dataclass(frozen=True)
class Board:
    path: str
    sha256: str
    thickness: Q
    outline: Loop
    cutouts: tuple[Loop, ...]
    drills: tuple[Drill, ...]
    keepouts: tuple[Keepout, ...]


def read_board(path: Path, sha256: str) -> Board:
    """Read the file, check its sha256, and build the Board above. A footprint with no
    courtyard keeps `courtyard == ()`: its body has no drawn extent, so its keep-out check
    is a Gap until the design waives it (a fiducial, a logo). Memoised on (path, sha256).
    Raises BoardError."""
    raise NotImplementedError
