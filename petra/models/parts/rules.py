"""The one table of fit and fabrication checks. Trusted.

Each row is one failure mode: the feature it is demanded on, what failing it means, the
measure it reads, the query that measure needs, and the row it is held to. Coverage rules,
failure modes, builders and the rows each process preset must hold all derive from RULES
(domain.py), so adding a check is adding a row.

A rule's bound names a row. Where the row lives follows from `applies`: a part rule reads
the part's process preset (with the design's overrides); a pair, insert or gap rule reads
both bodies' presets and takes the stricter value; a fasten rule reads the fastener's
registry part and the presets of the parts it passes through; a guard or opening rule
reads the sphere its line names. None means the bound is zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from ...registry import ProcessKind


class Consequence(Enum):
    """What failing a rule means. Every refutation makes the design FAIL. An impossible
    one refuses a waiver at lowering; a worse one may be waived with a signature; a
    costlier one is always a cost line and fails only against a budget the design or the
    preset states."""

    IMPOSSIBLE = "impossible"   # the part cannot be made or the assembly cannot be put together
    WORSE = "worse"             # it can, worse: chatter, sink, warp, a fit that binds
    COSTLIER = "costlier"       # it can, dearer: supports, setups, special tools


class Evaluator(Enum):
    EXACT = "exact"             # one placement, exact rational coordinates (exact.py)
    DECLARED = "declared"       # declared features only; the statement is the whole check
    GRID = "grid"               # every placement, the three-valued grid (reach.py)


class Measure(Enum):
    """What a rule measures, and which evaluator measures it."""

    OVERLAP = ("overlap", Evaluator.EXACT)        # do two placed bodies' interiors overlap
    GAP = ("gap", Evaluator.EXACT)                # least distance between bodies that must not touch
    CLEARANCE = ("clearance", Evaluator.EXACT)    # least sideways clearance of a mover along its travel
    SEAT = ("seat", Evaluator.EXACT)              # widest part of a bearing ring off the part's face
    SLOPE = ("slope", Evaluator.EXACT)            # projected area of faces past a slope limit
    PRISM = ("prism", Evaluator.EXACT)            # departure from an extrusion of the stock thickness
    EXTENT = ("extent", Evaluator.EXACT)          # bounding box past a build volume or bed
    ALIGN = ("align", Evaluator.DECLARED)         # hole centres apart against the room the holes leave
    GRIP = ("grip", Evaluator.DECLARED)           # a fastener's thread against the material it enters
    OPENING = ("opening", Evaluator.DECLARED)     # a declared opening against a test sphere
    UNREACHED = ("unreached", Evaluator.GRID)     # deepest stock no placement of the tools reaches
    THIN = ("thin", Evaluator.GRID)               # deepest material (or space) no fitting body reaches
    RATIO = ("ratio", Evaluator.GRID)             # worst thin wall's free height over thickness
    DIRECTIONS = ("directions", Evaluator.GRID)   # fewest directions whose reach covers the stock
    PASSAGE = ("passage", Evaluator.GRID)         # widest ball that travels between two regions

    @property
    def evaluator(self) -> Evaluator:
        return self.value[1]


class Applies(Enum):
    """The feature a rule is demanded on. A part rule names its process kind."""

    PRINT = "part.print"
    POWDER = "part.powder"
    SHEET = "part.sheet"
    MILL = "part.mill"
    MOLD = "part.mold"
    HOLE = "hole"            # a hole a part declares
    SEAT = "seat"            # a seat a part declares
    PAIR = "pair"            # every two bodies an assembly places
    KEEPOUT = "keepout"      # every footprint of a placed board, against every other body
    FASTEN = "fasten"
    INSERT = "insert"
    ACCESS = "access"
    GAP = "gap"
    GUARD = "guard"          # a guard over placed meshes
    OPENING = "opening"      # a guard over declared openings (bars, slots, holes)

    @property
    def process(self) -> ProcessKind | None:
        return ProcessKind(self.value.split(".")[1]) if self.value.startswith("part.") else None


@dataclass(frozen=True)
class QuerySpec:
    """How a rule's Sweep or body is built from its feature and its rows. Data, so a new
    process is new rows."""

    mover: Literal["each_tool", "standard_tools", "ray", "pin", "driver", "body", "plug", "ball", "disk"]
    along: Literal["setups", "pull", "sheet_normal", "feature", "any"]
    side: Literal["material", "empty"]


@dataclass(frozen=True)
class Rule:
    id: str                       # the failure mode id, "fit.overlap", "print.overhang"
    applies: Applies
    consequence: Consequence
    measure: Measure
    query: QuerySpec | None       # None for measures that build no Sweep or body
    bound: str | None             # the row the measure is held to; None: zero
    text: str


_I, _W, _C = Consequence.IMPOSSIBLE, Consequence.WORSE, Consequence.COSTLIER
_M = Measure
_A = Applies


def _q(mover, along, side="material") -> QuerySpec:
    return QuerySpec(mover, along, side)


RULES: tuple[Rule, ...] = (
    # Fit. Exact on one placement, or on declared features.
    Rule("fit.overlap", _A.PAIR, _I, _M.OVERLAP, None, None,
         "the two bodies' interiors do not overlap; touching faces are allowed"),
    Rule("fit.keepout", _A.KEEPOUT, _I, _M.OVERLAP, None, None,
         "a component's body, its courtyard raised to its height, overlaps no other body"),
    Rule("fit.gap", _A.GAP, _I, _M.GAP, None, "fit.clearance",
         "two bodies that must not touch keep the clearance apart everywhere"),
    Rule("fit.insert", _A.INSERT, _I, _M.CLEARANCE, _q("body", "feature"), None,
         "the body travels its insertion path without entering another body"),
    Rule("fit.insert_clearance", _A.INSERT, _W, _M.CLEARANCE, _q("body", "feature"), "fit.clearance",
         "along its insertion path the body keeps the process clearance sideways"),
    Rule("fit.access", _A.ACCESS, _I, _M.CLEARANCE, _q("plug", "feature"), None,
         "a mating plug travels from outside to its connector without entering a body"),
    Rule("fit.hole", _A.HOLE, _I, _M.CLEARANCE, _q("pin", "feature"), None,
         "a pin of the declared diameter, less the process tolerance, passes the declared depth"),
    Rule("fit.seat", _A.SEAT, _I, _M.SEAT, None, None,
         "the bearing ring of the declared head or washer lies on the part's face"),
    Rule("fit.align", _A.FASTEN, _I, _M.ALIGN, None, "tolerance",
         "the fastener passes every hole of its stack at the placed positions over the tolerances"),
    Rule("fit.grip", _A.FASTEN, _I, _M.GRIP, None, "engagement",
         "the thread engages enough of the last part and does not bottom out in it"),
    Rule("fit.driver", _A.FASTEN, _I, _M.CLEARANCE, _q("driver", "feature"), None,
         "the fastener's driver reaches its head along its axis from outside"),
    Rule("fit.passage", _A.GUARD, _I, _M.PASSAGE, _q("ball", "any", "empty"), None,
         "no ball of the guard's test size travels from outside to the hazard"),
    Rule("fit.opening", _A.OPENING, _I, _M.OPENING, None, None,
         "no declared opening passes a ball of the guard's test size"),
    # Material extrusion (FDM).
    Rule("print.volume", _A.PRINT, _I, _M.EXTENT, None, "build", "the part fits the build volume"),
    Rule("print.min_feature", _A.PRINT, _I, _M.THIN, _q("disk", "any"), "line_width",
         "every point of the part lies in a disk one line wide and one layer thick inside it"),
    Rule("print.thin_wall", _A.PRINT, _W, _M.THIN, _q("disk", "any"), "wall",
         "every wall is at least the preset's wall thickness"),
    Rule("print.min_hole", _A.PRINT, _I, _M.THIN, _q("disk", "any", "empty"), "hole_min",
         "every hole and slot is wide enough to stay open"),
    Rule("print.overhang", _A.PRINT, _C, _M.SLOPE, None, "overhang",
         "faces past the overhang slope need support; their area is the cost"),
    # Powder-bed fusion (SLS, MJF).
    Rule("powder.volume", _A.POWDER, _I, _M.EXTENT, None, "build", "the part fits the build volume"),
    Rule("powder.min_feature", _A.POWDER, _I, _M.THIN, _q("ball", "any"), "min_feature",
         "every point of the part lies in a ball of the minimum feature inside it"),
    Rule("powder.thin_wall", _A.POWDER, _W, _M.THIN, _q("ball", "any"), "wall",
         "every wall is at least the preset's wall thickness"),
    Rule("powder.min_hole", _A.POWDER, _I, _M.THIN, _q("ball", "any", "empty"), "hole_min",
         "every hole and slot is wide enough for the powder to clear"),
    Rule("powder.escape", _A.POWDER, _I, _M.PASSAGE, _q("ball", "any", "empty"), "escape",
         "a ball of the escape size travels from every closed void to outside"),
    # Profiles cut from sheet (laser, waterjet, router).
    Rule("sheet.prism", _A.SHEET, _I, _M.PRISM, None, "thickness",
         "the part is an extrusion of the stock thickness along the sheet normal"),
    Rule("sheet.bed", _A.SHEET, _I, _M.EXTENT, None, "bed", "the part fits the machine's bed"),
    Rule("sheet.corner", _A.SHEET, _I, _M.UNREACHED, _q("each_tool", "sheet_normal"), "reach_tolerance",
         "the cutter or beam reaches every inside corner and slot within the tolerance"),
    Rule("sheet.min_web", _A.SHEET, _I, _M.THIN, _q("ball", "any"), "min_web",
         "every web between cuts is at least the preset's minimum"),
    Rule("sheet.min_hole", _A.SHEET, _I, _M.THIN, _q("ball", "any", "empty"), "min_hole",
         "every hole is at least the preset's minimum"),
    # 3-axis milling.
    Rule("mill.reach", _A.MILL, _I, _M.UNREACHED, _q("each_tool", "setups"), "reach_tolerance",
         "some tool of the deck reaches every stock point farther than the tolerance from the part"),
    Rule("mill.special_tools", _A.MILL, _C, _M.UNREACHED, _q("standard_tools", "setups"), "reach_tolerance",
         "the standard tools alone reach the stock; otherwise special tools are a cost"),
    Rule("mill.setups", _A.MILL, _C, _M.DIRECTIONS, _q("each_tool", "setups"), "setups.budget",
         "the setups needed are within the budget"),
    Rule("mill.min_feature", _A.MILL, _I, _M.THIN, _q("ball", "any"), "min_feature",
         "every point of the part lies in a ball of the minimum feature inside it"),
    Rule("mill.chatter", _A.MILL, _W, _M.RATIO, _q("ball", "any"), "chatter.ratio",
         "no thin wall stands taller than the ratio times its thickness"),
    # Injection molding.
    Rule("mold.undercut", _A.MOLD, _I, _M.UNREACHED, _q("ray", "pull"), "reach_tolerance",
         "every point outside the part is reached by the pull or its opposite"),
    Rule("mold.draft", _A.MOLD, _W, _M.SLOPE, None, "draft",
         "faces along the pull carry at least the draft angle"),
    Rule("mold.side_actions", _A.MOLD, _C, _M.DIRECTIONS, _q("ray", "setups"), "side_actions.budget",
         "the side actions needed are within the budget"),
    Rule("mold.min_wall", _A.MOLD, _I, _M.THIN, _q("ball", "any"), "min_wall",
         "every wall is at least the minimum wall"),
    Rule("mold.sink", _A.MOLD, _W, _M.RATIO, _q("ball", "any"), "sink.ratio",
         "no section is thicker than the nominal wall by more than the ratio"),
)

RULE_BY_ID: dict[str, Rule] = {r.id: r for r in RULES}
if len(RULE_BY_ID) != len(RULES):
    raise RuntimeError("parts.rules: a rule id appears twice")


def rows_read(kind: ProcessKind) -> frozenset[str]:
    """Every preset row the rules of `kind` read, bounds and query rows both (a tool deck's
    tool.<id>.radius, reach and holder_radius; a print preset's layer for its disk). The
    registry check in domain.py refuses a preset of `kind` that lacks one or holds another."""
    raise NotImplementedError
