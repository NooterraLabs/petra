"""Metamorphic relations over the steel gate's stream: `python scripts/metamorphic.py
[--n 10000] [--seed 1] [--workers 6] [--relation NAME ...] [--no-twin] [--out docs]`.

A relation changes one thing in a generated design and says how each check must answer.
A thicker part, one more bolt or a higher Fy must not raise any check's utilisation at the
same load. A change of units must change nothing. The bolt group reflected about the beam's
mid-depth must keep every check's numbers, and a positional check its outcome. Each
relation is read per check, never per verdict, so a rule that rightly turns a PASS into a
FAIL (Table J2.4's least fillet for a thicker part, Manual Part 10's thickest single plate)
is named in EXEMPT with its clause. A reading of Petra's or the twin's that breaks a
relation for a reason outside its clause is named in DEFECTS: reported, never excused.

Petra is read through its calculation readout (petra.models.steel.calc) and its kernel
verdict. The clean-room twin (twin/, frozen) is read through its JSON report, with its
shape and grade tables patched in memory for the relations that change them. Writes
docs/metamorphic.md and docs/metamorphic_log.jsonl. Untrusted tooling; it never changes a
verdict. Exits 1 when Petra breaks a relation outside EXEMPT and DEFECTS.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import re
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass, replace
from fractions import Fraction
from multiprocessing import Pool
from pathlib import Path
from typing import Callable, ContextManager, Iterable, Mapping
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import twin.card  # noqa: E402
import twin.data  # noqa: E402
import twin.run  # noqa: E402
from petra.kernel import Interval  # noqa: E402
from petra.lang import parse_design  # noqa: E402
from petra.models.steel import calc  # noqa: E402
from petra.models.steel.domain import required  # noqa: E402
from petra.models.steel.fatigue import GENERATORS  # noqa: E402
from petra.models.steel.gate import deck_outcomes  # noqa: E402
from petra.models.steel.generate import Generated, generate  # noqa: E402
from petra.models.steel.lower import tee_parent  # noqa: E402
from petra.pipeline import check_design  # noqa: E402
from petra.registry import Registry, build_registry  # noqa: E402
from petra.registry.steel import INCH, STOCK_PLATES  # noqa: E402
from petra.solvers import SolverSource  # noqa: E402
from petra.units import CUSTOMARY  # noqa: E402
from petra.verdict import STATUS  # noqa: E402

CASE = "gate"
MONOTONE, INVARIANT, MIRROR = "monotone", "invariant", "mirror"
POINT, BOX = 1e-9, 1e-3
"""Relative slack on a utilisation. A design with a toleranced length is read over its box
by a search that stops within 1/2000 of a point it reached (calc.TOLERANCE), so two such
reads may differ by twice that."""


Key = tuple[str, str, int]
"""(mode, the check's name, which occurrence of that name in the mode)."""


@dataclass(frozen=True)
class Check:
    u: float
    excused: bool
    demand: float | None
    capacity: float | None


@dataclass(frozen=True)
class Read:
    """One oracle's reading of one card. Petra's status is its verdict and `failing` the
    modes the kernel did not discharge; the twin's status is checked, unsupported or
    input_error."""

    status: str
    checks: Mapping[Key, Check]
    failing: tuple[str, ...] = ()


@dataclass(frozen=True)
class Variant:
    """A changed design: its card, the registry Petra reads it with, and a context that
    patches the twin's tables while the twin reads it."""

    text: str
    registry: Registry
    twin: Callable[[], ContextManager] = contextlib.nullcontext


@dataclass(frozen=True)
class Relation:
    name: str
    kind: str
    change: str
    make: Callable[[str, Registry], Variant | None]


CAPACITY, NOTHING = "capacity", "nothing"


@dataclass(frozen=True)
class Exemption:
    """A check that may move the wrong way under `relations`, because its clause says so.
    `check` is searched in the check's name, within `modes` only. `holds` is what the
    relation still asks of it: CAPACITY when only its demand may rise, so its capacity
    must not fall; NOTHING when its clause lowers the capacity itself."""

    relations: tuple[str, ...]
    oracle: str
    modes: tuple[str, ...]
    check: str
    holds: str
    clause: str
    why: str


@dataclass(frozen=True)
class Defect:
    """A reading of Petra's or the twin's that breaks a relation for a reason outside its
    clause. A break it matches is still counted and logged, as known. A Petra break it
    matches does not fail the run, and a design the twin breaks a relation on stays
    undecided under docs/keystone_protocol.md."""

    relations: tuple[str, ...]
    oracle: str
    modes: tuple[str, ...]
    check: str
    finding: str


# --- Readers ---------------------------------------------------------------------------

def petra_read(text: str, registry: Registry) -> Read:
    """Every check Petra generates for c1 under the gate case, as its readout prints them,
    and the kernel's verdict."""
    design = parse_design(text, "metamorphic.petra", registry)
    conn = calc.connection(design, "c1", registry)
    checks: dict[Key, Check] = {}
    for mode in required(conn, design):
        if mode not in GENERATORS:
            continue
        seen: Counter = Counter()
        for v in calc.values(conn, design, registry, mode, CASE):
            checks[(mode, v.what, seen[v.what])] = Check(v.utilisation, v.excused, v.demand, v.capacity)
            seen[v.what] += 1
    report = check_design(design, registry, (SolverSource(),))
    modes, _ = deck_outcomes(report)
    return Read(STATUS[type(report.verdict)], checks, tuple(sorted(m for m, s in modes.items() if s != "pass")))


def twin_read(text: str) -> Read:
    try:
        components = twin.run.check_text(text)["components"]
    except twin.card.CardError as e:
        return Read(f"input_error: {e}", {})
    found = next(c for c in components if c["name"] == "c1")
    if found["status"] != "checked":
        reason = found.get("reason", "").removeprefix("c1: ")
        return Read(f"{found['status']}: {reason}" if reason else found["status"], {})
    checks: dict[Key, Check] = {}
    seen: Counter = Counter()
    for c in found["checks"]:
        u = c["utilisation"]
        checks[(c["mode"], c["name"], seen[(c["mode"], c["name"])])] = Check(
            math.inf if u is None else u, False, c["demand"], c["available"])
        seen[(c["mode"], c["name"])] += 1
    return Read("checked", checks)


# --- Changes to a design ---------------------------------------------------------------

def _decimal(x: Fraction) -> str:
    """x as an exact decimal; x must have one."""
    for places in range(40):
        scaled = abs(x) * 10**places
        if scaled.denominator == 1:
            whole, frac = divmod(scaled.numerator, 10**places)
            digits = f".{frac:0{places}d}".rstrip("0").rstrip(".") if places else ""
            return f"{'-' if x < 0 else ''}{whole}{digits}"
    raise ValueError(f"{x} has no exact decimal")


def _ratio(x: Fraction) -> str:
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


def _mixed(text: str) -> Fraction:
    """ "1-1/8" -> 9/8, "3/16" -> 3/16: a shop deck thickness in inches."""
    whole, _, frac = text.partition("-")
    return Fraction(whole) + (Fraction(frac) if frac else 0)


def _kind(text: str) -> str:
    return re.search(r"^(\w+) c1 \{$", text, re.M).group(1)


def _sub(text: str, m: re.Match, line: str) -> str:
    return text[:m.start()] + line + text[m.end():]


STOCK = sorted(_mixed(t) for t in STOCK_PLATES)


def _thicker_plate(line: str) -> Callable[[str, Registry], Variant | None]:
    def make(text: str, registry: Registry) -> Variant | None:
        m = re.search(rf"^  {line} (\S+) thickness ([0-9.]+) inch$", text, re.M)
        up = next((s for s in STOCK if s > Fraction(m.group(2))), None) if m else None
        return None if up is None else Variant(_sub(text, m, f"  {line} {m.group(1)} thickness {_decimal(up)} inch"), registry)
    return make


def angle_thicker(text: str, registry: Registry) -> Variant | None:
    m = re.search(r"^  (angles?) (L\S+) grade", text, re.M)
    if m is None:
        return None
    dims = lambda shape: tuple(registry.constants[f"aisc_shapes_v16.{shape}.{p}"].value.lo for p in "dbt")  # noqa: E731
    d, b, t = dims(m.group(2))
    shapes = {k.split(".")[1] for k in registry.constants if k.startswith("aisc_shapes_v16.L") and k.endswith(".t")}
    thicker = sorted((dims(s)[2], s) for s in shapes if dims(s)[:2] == (d, b) and dims(s)[2] > t)
    if not thicker:
        return None
    return Variant(text[:m.start(2)] + thicker[0][1] + text[m.end(2):], registry)


def _count(key: str) -> Callable[[str, Registry], Variant | None]:
    def make(text: str, registry: Registry) -> Variant | None:
        m = re.search(rf"^  {key} (\d+)$", text, re.M)
        return None if m is None else Variant(_sub(text, m, f"  {key} {int(m.group(1)) + 1}"), registry)
    return make


def grade_up(text: str, registry: Registry) -> Variant | None:
    raised = re.sub(r"\bsteel\.A36\b", "steel.A572_50", text)
    return None if raised == text else Variant(raised, registry)


def _members(text: str) -> tuple[set[str], set[str]]:
    """The design's W shapes, each tee's parent among them, and its tees."""
    shapes = set(re.findall(r"^  (?:beam|support|member) (W\S+) ", text, re.M))
    tees = set(re.findall(r"^  tee (WT\S+) ", text, re.M))
    return shapes | {tee_parent(t) for t in tees}, tees


SIXTEENTH = Fraction(1, 16)


def _thicker_members(prop: str) -> Callable[[str, Registry], Variant | None]:
    """Every W shape's `prop` (tw or tf) 1/16 in more, each tee's with its parent's."""
    def make(text: str, registry: Registry) -> Variant | None:
        shapes, tees = _members(text)
        if not shapes:
            return None
        constants = dict(registry.constants)
        for shape in shapes:
            c = constants[f"aisc_shapes_v16.{shape}.{prop}"]
            constants[c.name] = replace(c, value=Interval(c.value.lo + SIXTEENTH * INCH, c.value.hi + SIXTEENTH * INCH))
        table = dict(twin.data._table())
        for name in (shapes | tees) & set(table):
            table[name] = {**table[name], prop: str(Fraction(table[name][prop]) + SIXTEENTH)}
        return Variant(text, replace(registry, constants=constants),
                       lambda: mock.patch.object(twin.data, "_table", lambda: table))
    return make


FY_STEP = 4
GRADES = ("steel.A36", "steel.A572_50", "steel.A992")


def fy_up(text: str, registry: Registry) -> Variant:
    """Every grade's Fy FY_STEP ksi more, its Fu held."""
    step = FY_STEP * CUSTOMARY["ksi"][0]
    materials = dict(registry.materials)
    for grade in GRADES:
        m = materials[grade]
        fy = m.props["fy"]
        materials[grade] = replace(m, props={**m.props, "fy": replace(fy, value=Interval(fy.value.lo + step, fy.value.hi + step))})
    grades = {g: (fy + FY_STEP, fu) for g, (fy, fu) in twin.data.GRADES.items()}
    return Variant(text, replace(registry, materials=materials), lambda: mock.patch.dict(twin.data.GRADES, grades))


_QUANTITY = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?) (inch|kip)\b")
MM_PER_INCH = Fraction("25.4")
KN_PER_KIP = Fraction("4.4482216152605")
"""Exact by definition: 1 in = 25.4 mm, and 1 lbf = 0.45359237 kg x 9.80665 m/s2."""


def _units(length: str, of_inch: Callable[[Fraction], str], force: str, of_kip: Callable[[Fraction], str]):
    def make(text: str, registry: Registry) -> Variant:
        def restate(m: re.Match) -> str:
            x = Fraction(m.group(1))
            return f"{of_inch(x)} {length}" if m.group(2) == "inch" else f"{of_kip(x)} {force}"
        return Variant(_QUANTITY.sub(restate, text), registry)
    return make


MIRRORED = ("shear_tab", "double_angle", "single_angle", "shear_tee")
"""The kinds whose bolt group sits at `top` on the beam web."""


def mirror(text: str, registry: Registry) -> Variant | None:
    """The bolt group reflected about an uncoped beam's mid-depth: top becomes d - top -
    (rows - 1) pitch. A coped beam has no mirror the grammar states, since only its top
    flange may be coped alone."""
    if _kind(text) not in MIRRORED or re.search(r"^  cope ", text, re.M):
        return None
    top = re.search(r"^  top ([0-9.]+) inch$", text, re.M)
    pitch = re.search(r"^  pitch ([0-9.]+) inch$", text, re.M)
    rows = re.search(r"^  rows (\d+)$", text, re.M)
    beam = re.search(r"^  beam (W\S+) grade", text, re.M)
    if not (top and pitch and rows and beam):
        return None
    d = registry.constants[f"aisc_shapes_v16.{beam.group(1)}.d"].value.lo / INCH
    flipped = d - Fraction(top.group(1)) - (int(rows.group(1)) - 1) * Fraction(pitch.group(1))
    return Variant(_sub(text, top, f"  top {_decimal(flipped)} inch"), registry) if flipped > 0 else None


RELATIONS: tuple[Relation, ...] = (
    Relation("plate_thicker", MONOTONE, "the plate one stocked thickness thicker", _thicker_plate("plate")),
    Relation("stiffener_thicker", MONOTONE, "the seat stiffener one stocked thickness thicker", _thicker_plate("stiffener")),
    Relation("angle_thicker", MONOTONE, "the angle or angles at the next thickness with the same legs", angle_thicker),
    Relation("web_thicker", MONOTONE, "every W shape's web 1/16 in thicker, a tee's stem with its parent's",
             _thicker_members("tw")),
    Relation("flange_thicker", MONOTONE, "every W shape's flanges 1/16 in thicker, a tee's flange with its parent's",
             _thicker_members("tf")),
    Relation("rows_plus_one", MONOTONE, "one more row of bolts", _count("rows")),
    Relation("columns_plus_one", MONOTONE, "one more column of bolts", _count("columns")),
    Relation("grade_up", MONOTONE, "every A36 part in A572 Grade 50 (Fy 36 to 50 ksi, Fu 58 to 65 ksi)", grade_up),
    Relation("fy_up", MONOTONE, f"every grade's Fy {FY_STEP} ksi higher, its Fu held", fy_up),
    Relation("units_mm_kn", INVARIANT, "lengths in mm and forces in kN, converted exactly",
             _units("mm", lambda x: _decimal(x * MM_PER_INCH), "kN", lambda x: _decimal(x * KN_PER_KIP))),
    Relation("units_ft_lbf", INVARIANT, "lengths in ft as exact fractions and forces in lbf",
             _units("ft", lambda x: _ratio(x / 12), "lbf", lambda x: _decimal(x * 1000))),
    Relation("mirror", MIRROR, "the bolt group reflected about an uncoped beam's mid-depth", mirror),
)
BY_NAME = {r.name: r for r in RELATIONS}

THICKER = ("plate_thicker", "stiffener_thicker", "angle_thicker", "web_thicker", "flange_thicker")
MORE_BOLTS = ("rows_plus_one", "columns_plus_one")
STRONGER = ("grade_up", "fy_up")

MANUAL = "AISC Steel Construction Manual, 16th ed."
FIT = f"{MANUAL} Part 1 (d, tf, tw, T); docs/steel_connections.md section 5a"
SINGLE_ANGLE = (f"{MANUAL} Part 10, single-angle connections, with the support leg's eccentricity the gauge plus tw/2 "
                "(Companion II.A-28A, and the leg plus tw/2 for its welds, II.A-29)")
SINGLE_PLATE = f"{MANUAL} Part 10, single-plate connections"

EXEMPT: tuple[Exemption, ...] = (
    # Detailing rules whose demand is the thickness or the count the relation raises.
    Exemption(("plate_thicker",), "petra", ("ductility", "extended_ductility"),
              r"^plate: fillet at least 5/8 of the plate thickness", CAPACITY, SINGLE_PLATE,
              "The fillet must reach 5/8 of the plate's thickness."),
    Exemption(("plate_thicker", "web_thicker"), "petra", ("ductility",), r"^plate: plate or beam web at most d/2 \+ 1/16",
              CAPACITY, SINGLE_PLATE + ", conventional configuration",
              "The thinner of the plate and the beam web must stay thin enough to rotate."),
    Exemption(("plate_thicker",), "petra", ("extended_ductility",), r"^plate: no thicker than tmax", CAPACITY,
              SINGLE_PLATE + ", extended configuration", "The plate must stay thinner than tmax."),
    Exemption(STRONGER + ("rows_plus_one",), "petra", ("extended_ductility",), r"^plate: no thicker than tmax", NOTHING,
              SINGLE_PLATE + ", extended configuration, tmax = 6 Mmax / (Fy L^2)",
              "tmax falls as Fy rises, and another row lengthens L faster than it raises Mmax."),
    Exemption(("web_thicker",), "petra", ("compression",), r"^stiffener: at least the beam web's thickness", CAPACITY,
              f"{MANUAL} Part 10, stiffened seated connections", "The stiffener must be at least tw Fyb / Fys thick."),
    Exemption(("web_thicker",), "petra", ("tee_ductility",), r"^tee flange( to support)?: (bolts|fillet) at least Eq "
              r"9-5[12]'s (dmin|wmin)", NOTHING, f"{MANUAL} Part 9, Eqs 9-51 to 9-53",
              "A stem or beam web thicker than d/2 + 1/16 in no longer meets Eq 9-53, so dmin or wmin comes into force."),
    Exemption(THICKER, "petra", ("fillet_size",), r": minimum fillet size for the thinner part", CAPACITY,
              "AISC 360-22 J2.2b, Table J2.4",
              "The least fillet steps up with the thinner part joined, and the step for its new thickness comes into force."),
    # Room on the support and on the beam (makeability, docs/steel_connections.md section 5a).
    Exemption(("angle_thicker", "web_thicker", "flange_thicker", "columns_plus_one"), "petra", ("clearance",),
              r": room to tighten, clear of ", NOTHING, f"{MANUAL} Part 7, entering and tightening clearances",
              "A thicker leg, flange, web or stem, or another column of bolts, leaves less room for the wrench."),
    Exemption(("web_thicker",), "petra", ("flange_fit",), r"^support flange: (the bolt lines' holes clear of the web|some "
              r"placement of the bracket's bolt columns)", NOTHING, FIT,
              "A thicker column web leaves less flange beside it for the holes."),
    Exemption(("flange_thicker",), "petra", ("web_fit",), r"^support web: the beam's flange passes between the column's "
              r"flanges", NOTHING, FIT, "Thicker column flanges leave less room, d - 2 tf, between them."),
    Exemption(("plate_thicker", "stiffener_thicker", "web_thicker"), "petra", ("web_fit", "flange_fit"),
              r"^support (web|flange): the (plate and its welds|stiffener and its welds|welds at the outstanding legs' toes|"
              r"outstanding legs|beam web and the (outstanding leg|angle's bolt line)) within", CAPACITY, FIT,
              "A thicker part, or a thicker beam web between the angles, needs more of the face."),
    Exemption(("columns_plus_one",), "petra", ("flange_fit",), r"^support flange: some placement of the bracket's bolt "
              r"columns", CAPACITY, FIT, "Another column widens the group the flange must hold."),
    Exemption(("flange_thicker",), "petra", ("beam_fit",), r"the tee flange's thickness at most the bolt line's distance",
              CAPACITY, FIT, "A thicker tee flange takes more of the bolt line's distance from the support."),
    Exemption(("angle_thicker",), "petra", ("flange_fit", "web_fit"), r"^seat angle: top bolt hole on its vertical leg",
              CAPACITY, FIT, "A thicker outstanding leg reaches further down the vertical leg."),
    Exemption(("rows_plus_one",), "petra", ("flange_fit", "web_fit"), r"^seat angle: bottom bolt hole on its vertical leg",
              CAPACITY, FIT, "Another row reaches further down the seat's vertical leg."),
    Exemption(("rows_plus_one",), "petra", ("beam_fit",), r"^(.*: bottom (edge|bolt hole) on the|beam web: the end "
              r"plate's welds within the) (beam's )?flat web", CAPACITY, FIT, "Another row lengthens the part down the web."),
    # Eccentricity that the change moves.
    Exemption(("web_thicker",), "petra", ("slip",), r"^support side: slip at the most loaded bolt", CAPACITY,
              SINGLE_ANGLE, "The beam web's centreline, where the load acts, moves off the support leg's bolts."),
    Exemption(("web_thicker",), "petra", ("bolts",), r"^support side: the eccentric group by the instantaneous center",
              NOTHING, SINGLE_ANGLE + f"; {MANUAL} Part 7, instantaneous centre of rotation",
              "The beam web's centreline, where the load acts, moves off the support leg's bolts, and the coefficient C "
              "falls as the eccentricity grows."),
    Exemption(("plate_thicker", "web_thicker"), "petra", ("bolts",), r"^beam side: the eccentric group by the "
              r"instantaneous center", NOTHING, f"{SINGLE_PLATE}, Table 10-9 and its conventional configuration",
              "Table 10-9's eccentricity, a/2, holds only while the fillet is at least 5/8 of the plate's thickness and "
              "the plate or the beam web is at most d/2 + 1/16 in thick. A thicker plate or web can leave that "
              "configuration, and the group then takes its own eccentricity."),
    Exemption(("web_thicker",), "petra", ("block_shear", "flexural_yield", "flexural_rupture", "fatigue_bolted"),
              r"^angle outstanding( \(support side\))?: ", CAPACITY, SINGLE_ANGLE,
              "The moment on the support leg, V e, grows with e."),
    Exemption(("web_thicker",), "petra", ("weld", "weld_base_metal"), r"^angle to support: ", CAPACITY, SINGLE_ANGLE,
              "As for the bolts."),
    Exemption(("web_thicker",), "petra", ("edge_max",), r"^angles outstanding: outstanding toe edge distance at most",
              CAPACITY, "AISC 360-22 J3.6, with support_gauge read across the beam web (petra kinds steel)",
              "The stated gauge between the bolt lines spans the web, so a thicker web moves each line toward the heel "
              "and the toe's edge distance grows."),
    Exemption(MORE_BOLTS, "petra", ("block_shear",), r"^(plate|beam web|tee stem|bracket plate|angle outstanding): block of",
              CAPACITY, f"AISC 360-22 J4.3, with {MANUAL} Part 7's elastic method",
              "On an eccentric group a block's force is the elastic resultant over its bolts. Another row or column "
              "moves the centroid away from the block, and a block that held every bolt then holds a part."),
    Exemption(MORE_BOLTS, "petra", ("bracket_edge",), r"^bracket plate: normal force and moment on the free-edge section "
              r"B-B", CAPACITY, f"{MANUAL} Part 15, Eqs 15-8 to 15-18",
              "Another row deepens the plate, which lengthens section B-B and its slenderness. The stated eccentricity "
              "runs from the group's centroid, so another column moves section A-A toward the load. The moment on B-B, "
              "P (e - cos(theta) b'/2), grows in size where that arm is under cos(theta) b'/2."),
    Exemption(("rows_plus_one",), "petra", ("edge_min",), r"^bracket plate: plate free edge distance at least", NOTHING,
              f"{MANUAL} Part 15, Figure 15-2(a), with AISC 360-22 J3.5",
              "A shaped plate's free edge slopes from the bottom of section A-A to b in front of the top edge. Another "
              "row deepens the plate, which steepens that edge and brings it nearer the front column's bottom bolt."),
    Exemption(("columns_plus_one",), "petra", ("fatigue_weld_end",), r"^plate: stress", CAPACITY,
              f"AISC 360-22 Appendix 3, Table A-3.1 Case 5.7, with {SINGLE_PLATE}",
              "The welds carry V e, e from the support to the group's centroid, and another column moves the centroid "
              "out."),
    # A clause whose capacity, or whose regime, moves with the change.
    Exemption(("flange_thicker",), "petra", ("web_crippling",), r"web local crippling", NOTHING,
              "AISC 360-22 J10.3, Eqs J10-4 and J10-5", "The term (tw/tf)^1.5 falls as tf rises."),
    Exemption(("web_thicker",), "petra", ("web_sidesway_buckling",), r"web sidesway buckling", NOTHING, "AISC 360-22 J10.4",
              "The check applies only where (h/tw)/(Lb/bf) is under 2.3 or 1.7, and a thicker web brings it under."),
    Exemption(("plate_thicker", "web_thicker", "rows_plus_one") + STRONGER, "petra", ("plate_buckling", "cope_buckling"),
              r"lateral-torsional buckling.*, Lb d/t\^2 (<=|>) 1.9 E/Fy", CAPACITY,
              "AISC 360-22 F11.2(b) and (c), Eqs F11-3 and F11-4",
              "Each side of Lb d/t^2 = 1.9 E/Fy is its own check. A change that moves the plate or web across it brings "
              "the other side's check into force."),
    Exemption(("plate_thicker", "stiffener_thicker"), "petra", ("fatigue_weld_end",), r"from the weld root, RFIL", NOTHING,
              "AISC 360-22 Appendix 3, Table A-3.1 Case 5.7, RFIL",
              "RFIL falls as the part thickens, so the root's allowable stress range falls."),
    Exemption(("rows_plus_one",), "petra", ("shear_rupture",), r"^beam web: shear rupture of the net section", NOTHING,
              "AISC 360-22 J4.2(b)", "The beam web's depth is fixed, and each row takes a hole out of its net area."),
    Exemption(("rows_plus_one",), "petra", ("fatigue_bolted",), r"^beam web \(beam side\): .* net section through the "
              r"holes", CAPACITY, "AISC 360-22 Appendix 3, Table A-3.1 Case 2.2",
              "Each row takes a hole out of the beam web's net section, so its stress rises."),
    Exemption(STRONGER, "petra", ("compression",), r"^stiffener: width-to-thickness at most 0.56 sqrt\(E / Fy\)", NOTHING,
              "AISC 360-22 Table B4.1a Case 1, as Manual Part 10 applies it to a seat stiffener",
              "The limit 0.56 sqrt(E/Fy) falls as Fy rises."),
    Exemption(("mirror",), "petra", ("bolts",), r"^beam side: ", NOTHING, "AISC 360-22 J3.11a, Eqs J3-6c and J3-6d",
              "Tearout runs in the direction of the force. The load acts down, so the bolts push the beam web up and its "
              "top bolt tears out toward the beam's top, which the reflection moves. The load is not reflected."),
    # The twin.
    Exemption(("web_thicker",), "twin", ("bolts", "bearing", "slip"), r"support leg", NOTHING,
              SINGLE_ANGLE + f"; {MANUAL} Part 7, instantaneous centre of rotation",
              "The coefficient C falls as the eccentricity grows."),
    Exemption(("web_thicker",), "twin", ("flexural_yield", "flexural_rupture"), r"support leg", CAPACITY, SINGLE_ANGLE,
              "The moment on the support leg, V e, grows with e."),
    Exemption(("rows_plus_one",), "twin", ("shear_rupture",), r"coped section", NOTHING, "AISC 360-22 J4.2(b)",
              "The coped web's depth is fixed, and each row takes a hole out of its net area."),
    Exemption(("mirror",), "twin", ("edge_min", "bearing", "bolts"), r"^(edge distance along the force, beam web, |"
              r"bearing and tearout, beam web, |bolt group effective strength, (beam side|beam leg|stem)$)", NOTHING,
              "AISC 360-22 J3.11a, Eqs J3-6c and J3-6d, and J3.5",
              "The twin reads the beam web's tearout toward the beam's top, and J3.5 at the edge that tearout reads. The "
              "load acts down, so the bolts push the web up toward the top, which the reflection moves. The load is not "
              "reflected."),
    Exemption(("rows_plus_one",), "twin", ("edge_min",), r"^edge distance along the force, beam web, bottom cope$",
              NOTHING, "AISC 360-22 J3.5, Table J3.4",
              "The bottom cope stays where it is, and another row brings the bottom bolt nearer it."),
    Exemption(("rows_plus_one",), "twin", ("block_shear",), r", partial path$", CAPACITY,
              "AISC 360-22 J4.3, against the share of the demand on the block's rows",
              "The partial path is the weakest block through fewer rows than the column has. Another row adds the block "
              "through every old row to those blocks, and it carries more of the demand than any block the old column "
              "had short of all of it."),
)

DEFECTS: tuple[Defect, ...] = (
    Defect(("plate_thicker", "rows_plus_one") + STRONGER, "petra", ("flexural_yield",),
           r"^plate: shear and flexural yielding interaction \(Manual Eq 10-8\)",
           "An extended single plate's Mc in Eq 10-8 is the least of Mp and both F11 branches, each read outside its "
           "own range (checks.gen_flexural_yield). Past Lb d/t^2 = 3.65 E/Fy, where the two branches cross again "
           "(inferred from their formulas), the least is Eq F11-3, which falls as Fy or the plate's depth rises. Past "
           "5.55 E/Fy it is negative, and the check reads its size, so a thicker plate reads weaker. Companion "
           "II.A-19A takes Mc as the plate's flexural yielding strength and checks lateral-torsional buckling apart."),
    Defect(MORE_BOLTS, "petra", ("bolts",), r"^bracket bolts: the eccentric group by the instantaneous center",
           "A bracket's eccentric group is held to C times its weakest bolt (checks.bolt_capacity), and each bolt's "
           "tearout is read along that bolt's own force about the instantaneous center. Another row or column turns a "
           "corner bolt's force toward a nearer edge, and that one bolt's tearout then sets every bolt's strength, so "
           "a larger group can read weaker. Manual Part 7's coefficient C takes every bolt at one strength. The twin "
           "scales the sum of each bolt's least strength by C/n instead."),
)

POSITIONAL = ("beam_fit",)
"""Modes whose checks compare positions on the beam web. A reflection swaps each check at
the top for its partner at the bottom and keeps its outcome, not its ratio."""


# --- Judging ---------------------------------------------------------------------------

def exemption(relation: str, oracle: str, key: Key) -> int | None:
    mode, name, _ = key
    return next((i for i, e in enumerate(EXEMPT)
                 if relation in e.relations and e.oracle == oracle and mode in e.modes and re.search(e.check, name)), None)


def defect(relation: str, oracle: str, key: Key) -> int | None:
    mode, name, _ = key
    return next((i for i, d in enumerate(DEFECTS)
                 if relation in d.relations and d.oracle == oracle and mode in d.modes and re.search(d.check, name)), None)


def _close(a: float | None, b: float | None, slack: float) -> bool:
    if a is None or b is None or math.isinf(a) or math.isinf(b):
        return a == b
    return abs(a - b) <= slack * max(abs(a), abs(b))


def _same(b: Check, n: Check, slack: float) -> bool:
    return (b.excused == n.excused and _close(b.u, n.u, slack) and _close(b.demand, n.demand, slack)
            and _close(b.capacity, n.capacity, slack))


def _swap(name: str) -> str:
    return re.sub(r"\b(top|bottom)\b", lambda m: "bottom" if m.group(1) == "top" else "top", name)


def _fell(b: Check | None, n: Check | None, slack: float) -> bool:
    """Whether the check's capacity fell, or cannot be compared."""
    if b is None or n is None or b.capacity is None or n.capacity is None:
        return True
    return n.capacity < b.capacity * (1 - slack) - 1e-12


def _over(c: Check, slack: float) -> bool | None:
    """Whether the check fails, or None within slack of 1."""
    if c.excused:
        return False
    return None if abs(c.u - 1) <= slack else c.u > 1


@dataclass
class Judged:
    broken: list[dict]
    exempt: Counter
    flip: bool = False


def judge(relation: Relation, oracle: str, base: Read, new: Read, slack: float) -> Judged:
    """Where `new` breaks `relation` against `base`, outside EXEMPT, and how often each
    exemption absorbed a check that moved."""
    out = Judged([], Counter())
    moved: set[Key] = set()

    def flag(key: Key, what: str, b: Check | None, n: Check | None) -> None:
        i = exemption(relation.name, oracle, key)
        if i is not None and (EXEMPT[i].holds == NOTHING or not _fell(b, n, slack)):
            out.exempt[i] += 1
            return
        moved.add(key)
        entry = {"mode": key[0], "check": key[1], "what": what if i is None else f"{what}, capacity fell",
                 "base": None if b is None else b.u, "new": None if n is None else n.u}
        d = defect(relation.name, oracle, key)
        out.broken.append(entry if d is None else {**entry, "defect": d})

    if relation.kind == MONOTONE:
        for key in base.checks.keys() & new.checks.keys():
            b, n = base.checks[key], new.checks[key]
            if n.excused:
                continue
            if b.excused and n.u > 0:
                flag(key, "came into force", b, n)
            elif not b.excused and n.u > b.u * (1 + slack) + 1e-12:
                flag(key, "rose", b, n)
    else:
        mapped = {(k[0], _swap(k[1]) if relation.kind == MIRROR and k[0] in POSITIONAL else k[1], k[2]): c
                  for k, c in new.checks.items()}
        for key in base.checks.keys() | mapped.keys():
            b, n = base.checks.get(key), mapped.get(key)
            if b is None or n is None:
                flag(key, "missing", b, n)
            elif relation.kind == MIRROR and key[0] in POSITIONAL:
                if None not in (_over(b, slack), _over(n, slack)) and _over(b, slack) != _over(n, slack):
                    flag(key, "outcome changed", b, n)
            elif not _same(b, n, slack):
                flag(key, "changed", b, n)
    if oracle != "petra":
        return out
    if relation.kind == MONOTONE:
        out.flip = base.status == "PASS" and new.status != "PASS"
        for mode in new.failing if out.flip else ():
            if not any(k[0] == mode and not c.excused and c.u > 1 and (k in moved or exemption(relation.name, oracle, k) is not None)
                       for k, c in new.checks.items()):
                out.broken.append({"mode": mode, "check": "", "what": "verdict", "base": base.status, "new": new.status})
    elif (base.status, base.failing) != (new.status, new.failing):
        out.broken.append({"mode": ",".join(new.failing), "check": "", "what": "verdict",
                           "base": f"{base.status} {','.join(base.failing)}", "new": f"{new.status} {','.join(new.failing)}"})
    return out


def _slack(relation: Relation, toleranced: bool) -> float:
    if relation.kind == INVARIANT:
        return 0.0
    return BOX if toleranced else POINT


def assess(g: Generated, registry: Registry, relations: Iterable[Relation], with_twin: bool = True) -> dict:
    """One log row: the design, and for each relation that applies, what Petra and the twin
    did under it."""
    base = petra_read(g.text, registry)
    twin_base = twin_read(g.text) if with_twin else None
    row = {"name": g.name, "kind": g.kind, "status": base.status, "toleranced": g.toleranced, "free": g.free,
           "twin": None if twin_base is None else twin_base.status, "relations": {}}
    for relation in relations:
        variant = relation.make(g.text, registry)
        if variant is None:
            continue
        found: dict = {}
        try:
            new = petra_read(variant.text, variant.registry)
        except ValueError as e:
            broken = [{"mode": "", "check": "", "what": "rejected", "base": base.status, "new": str(e)[:300]}]
            found["petra"] = {"status": "REJECTED", "broken": broken if relation.kind != MONOTONE else [], "exempt": {},
                              "flip": False, "reason": str(e)[:300]}
        else:
            j = judge(relation, "petra", base, new, _slack(relation, g.toleranced))
            found["petra"] = {"status": new.status, "broken": j.broken, "exempt": dict(j.exempt), "flip": j.flip}
        if twin_base is not None and twin_base.status == "checked":
            with variant.twin():
                twin_new = twin_read(variant.text)
            if twin_new.status != "checked":
                broken = [{"mode": "", "check": "", "what": "unread", "base": "checked", "new": twin_new.status}]
                found["twin"] = {"status": twin_new.status, "broken": broken if relation.kind != MONOTONE else [],
                                 "exempt": {}}
            else:
                j = judge(relation, "twin", twin_base, twin_new, 0.0 if relation.kind == INVARIANT else POINT)
                found["twin"] = {"status": "checked", "broken": j.broken, "exempt": dict(j.exempt)}
        row["relations"][relation.name] = found
    return row


def chunk(job: tuple[int, int, int, tuple[str, ...], bool]) -> list[dict]:
    """A worker's slice of the stream: (seed, start, count, relation names, with_twin)."""
    seed, start, count, names, with_twin = job
    registry = build_registry()
    relations = [BY_NAME[n] for n in names]
    return [assess(g, registry, relations, with_twin) for g in generate(count, seed, registry, start)]


# --- Summary and report ----------------------------------------------------------------

@dataclass
class Tally:
    designs: int = 0
    rejected: int = 0
    broken: int = 0
    known: int = 0
    flips: int = 0
    twin_compared: int = 0
    twin_unread: int = 0
    twin_broken: int = 0


def unexplained(found: dict) -> list[dict]:
    """Petra's breaks of one relation on one design that no known defect accounts for."""
    return [b for b in found["petra"]["broken"] if "defect" not in b]


def summarise(rows: list[dict], names: Iterable[str]) -> tuple[dict[str, Tally], Counter, Counter, Counter]:
    """Per relation its tally; uses of each exemption by (index, oracle) and of each defect
    by (index, "defect"); Petra's and the twin's broken checks by (relation, mode, check,
    what, defect index or None)."""
    tallies = {n: Tally() for n in names}
    used, petra, twins = Counter(), Counter(), Counter()
    for row in rows:
        for name, found in row["relations"].items():
            t = tallies[name]
            t.designs += 1
            p = found["petra"]
            t.rejected += p["status"] == "REJECTED"
            t.broken += bool(unexplained(found))
            t.known += bool(p["broken"]) and not unexplained(found)
            t.flips += p["flip"]
            for i, n in p["exempt"].items():
                used[(int(i), "petra")] += n
            for b in p["broken"]:
                petra[(name, b["mode"], b["check"], b["what"], b.get("defect"))] += 1
                if "defect" in b:
                    used[(b["defect"], "defect")] += 1
            tw = found.get("twin")
            if tw is None:
                continue
            t.twin_compared += tw["status"] == "checked"
            t.twin_unread += tw["status"] != "checked"
            t.twin_broken += bool(tw["broken"])
            for i, n in tw["exempt"].items():
                used[(int(i), "twin")] += n
            for b in tw["broken"]:
                twins[(name, b["mode"], b["check"], b["what"], b.get("defect"))] += 1
                if "defect" in b:
                    used[(b["defect"], "defect")] += 1
    return tallies, used, petra, twins


def log_lines(rows: list[dict]) -> list[str]:
    """One line per oracle and relation with a break. Status and new status are that
    oracle's, on the design and on the changed design."""
    out = []
    for row in rows:
        for name, found in row["relations"].items():
            for oracle, status in (("petra", row["status"]), ("twin", row["twin"])):
                f = found.get(oracle)
                if f and f["broken"]:
                    out.append(json.dumps({"design": row["name"], "kind": row["kind"], "toleranced": row["toleranced"],
                                           "relation": name, "oracle": oracle, "status": status,
                                           "new_status": f["status"], "broken": f["broken"]}))
    return out


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def commit(paths: tuple[str, ...]) -> str:
    """The last commit that touched `paths`, and whether the checkout changes them."""
    git = lambda *a: subprocess.run(["git", *a, "--", *paths], cwd=ROOT, capture_output=True, text=True).stdout.strip()  # noqa: E731
    last = git("log", "-1", "--format=%h") or "unknown"
    return f"`{last}`" + (", with uncommitted changes" if git("status", "--porcelain") else ", clean")


def _command(args: argparse.Namespace) -> str:
    flags = f"--n {args.n} --seed {args.seed}" + (f" --start {args.start}" if args.start else "")
    flags += f" --workers {args.workers}" + (" --no-twin" if args.no_twin else "")
    return flags + (f" --relation {' '.join(args.relation)}" if args.relation else "")


def render(rows: list[dict], names: tuple[str, ...], args: argparse.Namespace, seconds: float,
           provenance: Mapping[str, str]) -> str:
    tallies, used, petra, twins = summarise(rows, names)
    n = len(rows)
    statuses = Counter(r["status"] for r in rows)
    read = sum(r["twin"] == "checked" for r in rows)
    unmodelled = [r["kind"] for r in rows if (r["twin"] or "").startswith("unsupported")]
    refused = Counter(r["twin"].removeprefix("input_error: ") for r in rows if (r["twin"] or "").startswith("input_error"))
    broken_designs = {r["name"] for r in rows for f in r["relations"].values() if f["petra"]["broken"]}
    open_designs = {r["name"] for r in rows for f in r["relations"].values() if unexplained(f)}
    twin_designs = {r["name"] for r in rows for f in r["relations"].values() if f.get("twin") and f["twin"]["broken"]}
    twin_open = {r["name"] for r in rows for f in r["relations"].values()
                 if f.get("twin") and any("defect" not in b for b in f["twin"]["broken"])}
    twin = (f"The clean-room twin in `twin/` is read through its JSON report, with its shape and grade tables patched "
            f"in memory for the relations that change them. It read {read} of the {n} designs (measured). It does not "
            f"model {' or '.join(sorted(set(unmodelled))) or 'every kind'} ({len(unmodelled)} designs). It refused "
            f"{sum(refused.values())} cards."
            + "".join(f" The reason it gave was \"{_cell(why)}\" for {k} of them." for why, k in refused.most_common())
            if not args.no_twin else "The clean-room twin was not run.")
    lines = [
        "# Metamorphic relations",
        "",
        f"Generated by `python scripts/metamorphic.py {_command(args)}`, in {seconds / 60:.1f} minutes of wall time. "
        "Do not edit by hand; re-run the script.",
        "",
        "| Measured | Last commit touching it |",
        "|---|---|",
        f"| Petra, `petra/` | {provenance['petra']} |",
        f"| The clean-room twin, `twin/` | {provenance['twin']} |",
        f"| This harness, `scripts/metamorphic.py` | {provenance['harness']} |",
        "",
        "A **relation** changes one thing in a design, keeps its loads, and says how every check must answer. A "
        "**monotone** relation makes a part thicker, adds a bolt or raises a strength, so no check's utilisation may "
        "rise. An **invariant** relation restates the design in other units, so every check must read exactly the "
        "same. The **mirror** reflects the bolt group about an uncoped beam's mid-depth. A positional check swaps top "
        "for bottom and keeps its outcome, and every other check keeps its numbers.",
        "",
        "Each relation is read per check, never per verdict. A check whose clause lets it move the wrong way is in "
        "the exemption table below, with that clause. A PASS that a monotone relation turns into a FAIL must be "
        "carried by a check that broke the relation or by an exempt check above 1. An invariant relation and the "
        "mirror must also keep the verdict and the modes that fail. A design whose card gives a length as a range is "
        "read over its box by a search that stops within 1/2000 of a point, so a monotone relation or the mirror "
        "allows it a relative slack of 1/1000. Other designs get 1e-9, and an invariant relation gets none.",
        "",
        f"The designs are the first {n} of seed {args.seed}'s stream, the designs `scripts/steel_gate.py` checks"
        + (f", from index {args.start}" if args.start else "")
        + f". Petra passed {statuses['PASS']} and failed {statuses['FAIL']} (measured). Petra is read through its "
        "calculation readout, `petra/models/steel/calc.py`, and its kernel verdict. " + twin,
        "",
        "## Relations",
        "",
        "Designs counts the designs a relation applies to. A changed design Petra will not read counts as rejected. "
        "It breaks an invariant relation or the mirror, and it leaves a monotone one untested. Petra broke it counts "
        "the designs with a break that no known defect accounts for, and Known defect the designs whose every break "
        "is one.",
        "",
        "| Relation | Type | Change | Designs | Petra rejected | Petra broke it | Known defect | PASS to FAIL | "
        "Twin read | Twin unread | Twin broke it |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name in names:
        r, t = BY_NAME[name], tallies[name]
        lines.append(f"| {name} | {r.kind} | {r.change} | {t.designs} | {t.rejected} | {t.broken} | {t.known} | "
                     f"{t.flips} | {t.twin_compared} | {t.twin_unread} | {t.twin_broken} |")
    lines += [
        "",
        f"Petra broke a relation outside the exemption table on {len(broken_designs)} designs. On "
        f"{len(broken_designs) - len(open_designs)} of them every break is a known defect, so {len(open_designs)} are "
        f"unexplained. The twin broke one on {len(twin_designs)} designs. On "
        f"{len(twin_designs) - len(twin_open)} of them every break is a known defect of the twin's. Under "
        "`docs/keystone_protocol.md` a design on which the twin breaks a relation is undecided, known defect or not.",
        "",
        "## Known defects",
        "",
        "A known defect is a reading of Petra's or the twin's that breaks a relation for a reason outside its clause. "
        "It is not excused. Its breaks are counted and logged, and the run does not fail on them. Breaks counts the "
        "checks it accounts for in this run.",
        "",
        "| # | Relations | Oracle | Modes | Check | Finding | Breaks |",
        "|---|---|---|---|---|---|---|",
        *(f"| {i} | {', '.join(d.relations)} | {d.oracle} | {', '.join(d.modes)} | `{_cell(d.check)}` | {d.finding} | "
          f"{used[(i, 'defect')]} |" for i, d in enumerate(DEFECTS)),
        "",
        "## Exemptions",
        "",
        "Check is a pattern searched in the check's name, within the modes named. Holds is what the relation still "
        "asks of the check. Capacity means only its demand may rise, so its capacity must not fall. Nothing means its "
        "clause lowers the capacity itself. Uses counts the checks each exemption excused in this run.",
        "",
        "| # | Relations | Oracle | Modes | Check | Holds | Clause | Why | Uses |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, e in enumerate(EXEMPT):
        lines.append(f"| {i} | {', '.join(e.relations)} | {e.oracle} | {', '.join(e.modes)} | `{_cell(e.check)}` | "
                     f"{e.holds} | {e.clause} | {e.why} | {used[(i, e.oracle)]} |")
    for title, broken in (("Petra", petra), ("The twin", twins)):
        if not broken:
            continue
        lines += ["", f"## {title}: checks that broke a relation", "",
                  "| Relation | Mode | Check | How | Known defect | Times |", "|---|---|---|---|---|---|"]
        lines += [f"| {r} | {m} | {_cell(c)} | {w} | {'' if d is None else d} | {k} |"
                  for (r, m, c, w, d), k in broken.most_common()]
    lines += ["", "`docs/metamorphic_log.jsonl` holds every broken relation, with the design and both readings.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="metamorphic relations over the steel gate's stream")
    parser.add_argument("--n", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--relation", nargs="*", choices=tuple(BY_NAME), help="run only these relations")
    parser.add_argument("--no-twin", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT / "docs")
    args = parser.parse_args(argv)
    names = tuple(args.relation or BY_NAME)
    start = time.time()
    step = 25
    jobs = [(args.seed, i, min(step, args.start + args.n - i), names, not args.no_twin)
            for i in range(args.start, args.start + args.n, step)]
    rows: list[dict] = []
    with Pool(args.workers) as pool:
        for done, part in enumerate(pool.imap(chunk, jobs), 1):
            rows.extend(part)
            if done % 20 == 0:
                print(f"{len(rows)} designs, {time.time() - start:.0f} s", flush=True)
    seconds = time.time() - start
    provenance = {"petra": commit(("petra",)), "twin": commit(("twin",)), "harness": commit(("scripts/metamorphic.py",))}
    args.out.mkdir(parents=True, exist_ok=True)
    report = render(rows, names, args, seconds, provenance)
    (args.out / "metamorphic.md").write_text(report, encoding="utf-8", newline="\n")
    lines = log_lines(rows)
    (args.out / "metamorphic_log.jsonl").write_text("".join(f"{line}\n" for line in lines), encoding="utf-8", newline="\n")
    print(report.split("## Exemptions", 1)[0])
    return 1 if any(unexplained(f) for r in rows for f in r["relations"].values()) else 0


if __name__ == "__main__":
    sys.exit(main())
