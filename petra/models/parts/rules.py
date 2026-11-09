"""The one table of fit, fabrication and thermal checks. Trusted.

Each row is one failure mode: the feature it is demanded on, what failing it means, the
evaluator that measures it, and what it holds. Coverage rules and failure modes derive
from RULES (domain.py), so adding a check is adding a row. A row whose evaluator is
UNMODELLED is still demanded: its requirement is UNKNOWN, needing a waiver, until a
builder exists, so a verdict never hides a check nobody ran.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Consequence(Enum):
    IMPOSSIBLE = "impossible"   # the part cannot be made or the assembly cannot be put together
    WORSE = "worse"             # it can, worse: a weak boss, a soft part, a fit that binds


class Evaluator(Enum):
    GEOMETRY = "geometry"       # exact rational geometry of the meshes (exact.py, engine.py)
    DECLARED = "declared"       # declared features and registry rows; the statement is the whole check
    THERMAL = "thermal"         # ambient plus a declared rise against a material limit
    UNMODELLED = "unmodelled"   # demanded, and no builder yet: a Gap needing NoModel


class Applies(Enum):
    """The feature a rule is demanded on."""

    PRINT = "parts.part.print"
    POWDER = "parts.part.powder"
    SHEET = "parts.part.sheet"
    MILL = "parts.part.mill"
    POLYMER = "parts.part"           # any part whose material's family is polymer
    HOLE = "parts.hole"              # every declared hole
    INSERT_HOLE = "parts.hole.insert"
    MOVER = "parts.mover"            # every placed part but the base
    BODY = "parts.body"              # every placed part
    FASTEN = "parts.fasten"
    GAP = "parts.gap"
    PRESS = "parts.press"


@dataclass(frozen=True)
class Rule:
    id: str
    applies: Applies
    consequence: Consequence
    evaluator: Evaluator
    text: str


_I, _W = Consequence.IMPOSSIBLE, Consequence.WORSE
_G, _D, _T, _U = Evaluator.GEOMETRY, Evaluator.DECLARED, Evaluator.THERMAL, Evaluator.UNMODELLED
_A = Applies

RULES: tuple[Rule, ...] = (
    # Fit, decided at the worst-case extreme of every declared tolerance.
    Rule("fit.insert", _A.MOVER, _I, _G,
         "the part travels its insert path to its place, rests on what it touches ahead of it, and keeps its own "
         "and each other part's allowance from every part already placed"),
    Rule("fit.connected", _A.BODY, _I, _G, "the part touches, is fastened to or is pressed into the parts placed before it"),
    Rule("fit.gap", _A.GAP, _I, _G, "two parts keep the stated gap beyond their allowances and floats"),
    Rule("fit.fastener", _A.FASTEN, _I, _G,
         "the screw travels its axis through the clear holes and enters no part but the one its thread enters, "
         "keeping each part's allowance with half its hole shrink"),
    Rule("fit.seat", _A.FASTEN, _I, _G,
         "a socket head's bearing ring lies on a face of the first part; a countersunk head fits its countersink"),
    Rule("fit.grip", _A.FASTEN, _I, _D,
         "the thread engages the last part over its least engagement and does not bottom in a blind hole"),
    Rule("fit.press", _A.PRESS, _I, _D, "the diametral interference stays in the declared range over both tolerances"),
    Rule("fit.hole", _A.HOLE, _I, _G,
         "the mesh holds the declared hole: its axis runs through empty space and no material comes nearer the "
         "axis than the declared radius less the tolerance; a countersink holds its cone"),
    Rule("fit.driver", _A.FASTEN, _I, _U, "a driver reaches the screw head along its axis from outside"),
    # Heat-set inserts in printed or moulded parts.
    Rule("insert.hole_size", _A.INSERT_HOLE, _I, _D,
         "the hole as made, its modelled diameter less its shrink, lies in the insert catalogue's range"),
    Rule("insert.depth", _A.INSERT_HOLE, _I, _D, "the hole runs at least the insert's length"),
    Rule("insert.boss_wall", _A.INSERT_HOLE, _W, _G,
         "material outside the hole wall reaches at least the catalogue's least wall over the insert's length"),
    # Temperature.
    Rule("part.temperature", _A.POLYMER, _I, _T,
         "the ambient's high end plus the declared local rise stays at or below the material's heat deflection "
         "temperature at 0.45 MPa"),
    # Material extrusion (FDM).
    Rule("print.volume", _A.PRINT, _I, _G, "the part, in its mesh frame with +z up, fits the printer's build volume"),
    Rule("print.min_feature", _A.PRINT, _I, _U, "every feature is at least one extrusion line wide"),
    Rule("print.thin_wall", _A.PRINT, _W, _U, "every wall is at least the preset's wall thickness"),
    Rule("print.min_hole", _A.PRINT, _I, _U, "every hole and slot is wide enough to stay open"),
    Rule("print.overhang", _A.PRINT, _W, _U, "no face past the overhang slope prints without support"),
    Rule("print.bridge", _A.PRINT, _W, _G,
         "every face printed over air, with +z up, spans at most the preset's bridge between the edges that hold it"),
    Rule("print.support_access", _A.PRINT, _I, _U, "every support can be reached and removed"),
    # Powder-bed fusion.
    Rule("powder.volume", _A.POWDER, _I, _G, "the part, in its mesh frame with +z up, fits the build volume"),
    Rule("powder.min_feature", _A.POWDER, _I, _U, "every feature is at least the minimum feature"),
    Rule("powder.escape", _A.POWDER, _I, _U, "powder escapes every closed void"),
    # Profiles cut from sheet.
    Rule("sheet.bed", _A.SHEET, _I, _G, "the part, lying in its mesh frame's xy plane, fits the machine's bed"),
    Rule("sheet.prism", _A.SHEET, _I, _G,
         "the part is a flat profile of the stock's thickness: every vertex lies on its two level faces and every "
         "other face is upright; a bent part fails, since v0 reads no bend lines"),
    Rule("sheet.min_web", _A.SHEET, _I, _U, "every web between cuts is at least the preset's minimum"),
    # 3-axis milling.
    Rule("mill.reach", _A.MILL, _I, _U, "some tool reaches every stock point to remove"),
    Rule("mill.min_feature", _A.MILL, _I, _U, "every feature is at least the minimum feature"),
    # Mass properties, for claims.
)

RULE_BY_ID: dict[str, Rule] = {r.id: r for r in RULES}
if len(RULE_BY_ID) != len(RULES):
    raise RuntimeError("parts.rules: a rule id appears twice")
