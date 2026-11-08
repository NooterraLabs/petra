"""Runs every rule a part or assembly demands, once, and keeps the answers. Trusted.

One query serves fit and reach: can this body move along this direction without
entering those bodies, and how much room does it keep. `ask` dispatches it on the
mover's placement. A mover at one placement (a placed Solid, or a Placed profile at a
Point: a board on its insertion path, a screw driver, a pin in a hole, a plug) goes to
exact.clearance and gets an exact Bracket or an Overlap. A mover Placed Everywhere (a
cutter, a laser's beam, a mold's pull) goes to the grid and gets a Bracket whose ends
may differ.

The grid's cell side is a solver budget, held here in code. It is no premise: a sound
grid at any side gives the same PASS and FAIL and differs only in how often it says
UNKNOWN. Because the budget is fixed in code, and this module's source is hashed into
every grid model, the statement stays a pure function of the design (decision 1).

Refinement, per part:

    h = budget.start * the smallest tolerance a grid rule of the part reads
    grid = classify(solids, h, stock)
    loop
        answer every grid rule of the part on grid
        open = the rules whose Bracket straddles their bound
        if open is empty or h / 2 < budget.floor * that tolerance: stop
        grid = refine(grid, solids, the cells an open rule counts in hi but not lo, halo)
        h = h / 2

A rule still open at the floor stays an UNKNOWN that names its unsure cells.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Union

from ...kernel import Q
from .deck import Deck
from .grid import CellGrid
from .lower import Assembly, PartDesign, PcbDesign
from .space import Answer, Bracket, Sweep


@dataclass(frozen=True)
class GridBudget:
    """Solver settings, not premises. Both sides are fractions of the smallest tolerance a
    grid rule reads, rounded down to a power of two in mm so refinements nest."""

    start: Q                 # 1 (guess)
    floor: Q                 # 1/4 (guess): the coarsest side at which a cleanly made face passes reach
    cells: int               # most cells one part's grids may hold at once, 2^27 (guess)


BUDGET = GridBudget(start=Q(1), floor=Q(1, 4), cells=2 ** 27)

Subject = tuple[str, ...]     # ("unit", "case") for a part rule; ("unit", "f1") for a fasten rule
Model = Union[PartDesign, PcbDesign, Assembly]


@dataclass(frozen=True)
class Cost:
    """What a costlier rule measured, always shown in the readout: support area (mm^2),
    setups, side actions, special tools. It fails only against a budget the design or
    the preset states."""

    rule: str
    subject: Subject
    value: Bracket
    unit: str


@dataclass(frozen=True)
class Run:
    """Every answer for one top-level model, keyed by (rule id, subject)."""

    answers: Mapping[tuple[str, Subject], Answer]
    costs: tuple[Cost, ...]
    grids: Mapping[str, CellGrid]          # part name -> the finest grid it reached, for the readout


def ask(sweep: Sweep, grid: CellGrid | None) -> Answer:
    """One query. A mover at one placement goes to exact.clearance and ignores `grid`; a
    mover Placed Everywhere goes to reach.reach on `grid`, which must classify every
    obstacle of the sweep. Raises ValueError for a Placed Everywhere mover with no grid."""
    raise NotImplementedError


def engine(model: Model, decks: Mapping[str, Deck], budget: GridBudget = BUDGET) -> Run:
    """Answer every rule `model` demands. `decks` maps each body's name to its deck. An
    assembly's run holds its own fit answers and each placed part's process answers, so
    a part placed in two assemblies is measured once. Memoised on (model, decks, budget)."""
    raise NotImplementedError
