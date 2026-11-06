"""Failure modes, model premises and validity rows of the steel deck. Trusted.

One FailureMode per limit state, each with one ModelSpec naming its clause. The model
premise's source_hash covers every trusted module of the package (lower, limits, checks,
build, vocab, domain), so editing any of the physics changes every steel premise label.
A mode's validity rows are the method's applicability limits the kernel decides over the
design's box (checks.ROWS states each).
"""
from __future__ import annotations

import hashlib
import os
from typing import Mapping

from ..base import FailureMode, ModelSpec, ValidityRow

TRUSTED = ("lower", "limits", "checks", "build", "vocab", "domain")
"""The package modules whose source is the physics. generate, twin, faults, breaker and
package are tooling and cannot change a verdict."""


def _source_hash() -> str:
    """sha256 over the trusted modules' sources in TRUSTED order, read from disk so that
    vocab can be imported before the others."""
    here = os.path.dirname(__file__)
    digest = hashlib.sha256()
    for name in TRUSTED:
        with open(os.path.join(here, f"{name}.py"), encoding="utf-8") as f:
            digest.update(f.read().encode("utf-8"))
    return digest.hexdigest()[:16]


SOURCE_HASH = _source_hash()
OWNER = "lola-maintainers"
AISC = "AISC 360-22"
MANUAL = "AISC Steel Construction Manual, 16th ed. (method encoded, not its text)"


def _mode(short: str) -> FailureMode:
    return FailureMode(f"steel.{short}")


def _spec(short: str, form: str, validity: str, source: str, rows: tuple[ValidityRow, ...] = (),
          unchecked: tuple[str, ...] = ()) -> ModelSpec:
    return ModelSpec(f"steel.{short}", form, validity, OWNER, source, SOURCE_HASH, rows, unchecked)


def _row(short: str, name: str, text: str, source: str) -> ValidityRow:
    return ValidityRow(f"steel.{short}.{name}", text, source)


# --- Strength limit states -------------------------------------------------------------------

STRENGTH: tuple[tuple[str, str, str, str, tuple[ValidityRow, ...]], ...] = (
    ("bolts",
     "bolt shear rupture (Eq J3-1) and bearing and tearout at every hole (Eq J3-6a-f), taken per bolt as the least of "
     "its shear strength and its bearing or tearout strength in each ply, summed over a concentric group; an "
     "eccentric group by the elastic method against the weakest bolt",
     "bolts of one group, size and installation; holes of the declared type; threads included or excluded as "
     "declared; the elastic method assumes a rigid connected part rotating about the group centroid",
     f"{AISC} Sections J3.7 and J3.11a, Table J3.2; {MANUAL} Part 7 (elastic method)", ()),
    ("bolt_tension",
     "bolt tensile rupture, Rn = Fnt Ab (Eq J3-1), with the tension shared equally by the bolts",
     "tension shared equally by the bolts of the group, after any prying the prying check adds",
     f"{AISC} Section J3.7, Table J3.2", ()),
    ("bolt_combined",
     "combined tension and shear in a bearing-type connection, F'nt = 1.3 Fnt - Fnt/(phi Fnv) frv <= Fnt (Eqs J3-3a/b), "
     "with the exemption when either stress is a small fraction of its available stress",
     "shear and tension shared equally by the bolts of the group",
     f"{AISC} Section J3.8", ()),
    ("slip",
     "slip resistance Rn = mu Du hf Tb ns ksc per bolt (Eqs J3-4, J3-5a/b), with the resistance factor of the hole type",
     "faying surfaces prepared to the declared class; bolts pretensioned to at least Table J3.1; fillers as declared",
     f"{AISC} Sections J3.9 and J3.10; RCSC 2025 Section 5.4", ()),
    ("shear_yield",
     "shear yielding of the gross section of each connected element, Rn = 0.60 Fy Agv (Eq J4-3)",
     "the element's gross shear plane runs the length of its bolt line or weld",
     f"{AISC} Section J4.2(a)", ()),
    ("shear_rupture",
     "shear rupture of the net section of each connected element, Rn = 0.60 Fu Anv (Eq J4-4), holes 1/16 in wider "
     "than nominal (B4.3b)",
     "the net shear plane runs through one line of holes",
     f"{AISC} Sections J4.2(b) and B4.3b", ()),
    ("block_shear",
     "block shear rupture over every tear-out path the hole pattern admits: blocks of the first k rows and j columns "
     "from the free edges carry their share k j / (rows cols) of a concentric force, or for an eccentric group the "
     "elastic method's resultant of the forces on the block's bolts (Manual Part 7), against Rn = 0.60 Fu Anv + "
     "Ubs Fu Ant <= 0.60 Fy Agv + Ubs Fu Ant (Eq J4-5), Ubs = 1 for one column and 0.5 for more",
     "each block is bounded by the free edges the element has; the block's capacity is taken for tear-out in the "
     "direction of the applied force, whatever the direction of the resultant on its bolts",
     f"{AISC} Section J4.3", ()),
    ("tension_yield",
     "tensile yielding of the gross section, Rn = Fy Ag (Eq J4-1)",
     "the element's gross section carries the tension uniformly",
     f"{AISC} Section J4.1(a)", ()),
    ("tension_rupture",
     "tensile rupture of the net section, Rn = Fu Ae (Eq J4-2), Ae = An <= 0.85 Ag for a bolted splice plate",
     "the net section through one line of holes carries the tension",
     f"{AISC} Section J4.1(b)", ()),
    ("flexural_yield",
     "flexural yielding of a connecting plate under the moment of its eccentricity, Mn = Fy Z (Section J4.5)",
     "the plate bends about its strong axis at the bolt or weld line nearest the support",
     f"{AISC} Section J4.5; {MANUAL} Part 10", ()),
    ("flexural_rupture",
     "flexural rupture of the net section of a connecting plate, Mn = Fu Znet (Section J4.5)",
     "the net section through the line of holes nearest the support",
     f"{AISC} Section J4.5; {MANUAL} Part 15", ()),
    ("weld",
     "fillet weld strength Rn = 0.60 FEXX Awe kds (Eq J2-4), kds by the line's direction, longitudinal and transverse "
     "lines combined by Eq J2-6; an eccentric pair of lines by the elastic method",
     "matching filler metal (Table J2.5); welds of the declared size and length; the elastic method assumes a rigid "
     "connected part",
     f"{AISC} Section J2.4, Table J2.5; {MANUAL} Part 8 (elastic method)", ()),
    ("weld_base_metal",
     "shear rupture of the base metal along each fusion face, 0.60 Fu t per unit length against the weld force it "
     "carries (Section J2.4(a) with Eq J4-4)",
     "the base metal's thickness is uniform along the weld",
     f"{AISC} Sections J2.4(a) and J4.2(b)", ()),
    ("bearing",
     "bearing on the fitted bearing area of a stiffener, Rn = 1.8 Fy Apb (Eq J7-1)",
     "the bearing surface is milled or fitted",
     f"{AISC} Section J7", ()),
    ("web_local_yielding",
     "web local yielding under a concentrated force, Rn = Fyw tw (5k + lb), or (2.5k + lb) within d of the member end "
     "(Eqs J10-2, J10-3)",
     "a rolled W shape with no stiffener at the force",
     f"{AISC} Section J10.2", ()),
    ("web_crippling",
     "web local crippling under a compressive concentrated force (Eqs J10-4, J10-5a, J10-5b, Qf = 1)",
     "a rolled W shape with no stiffener at the force; the force bears on one flange",
     f"{AISC} Section J10.3", ()),
    ("flange_local_bending",
     "flange local bending under a tensile concentrated force, Rn = 6.25 Fyf tf^2, halved within 10 tf of the end "
     "(Eq J10-1); not required when the loaded length across the flange is small",
     "a rolled W shape with no stiffener at the force",
     f"{AISC} Section J10.1", ()),
    ("web_sidesway_buckling",
     "web sidesway buckling under a compressive single force (Eqs J10-6, J10-7), where the slenderness ratio makes it "
     "apply",
     "the loaded and the opposite flange are not both restrained against relative lateral movement at the force",
     f"{AISC} Section J10.4", ()),
    ("web_compression_buckling",
     "web compression buckling under a pair of compressive forces on both flanges, Rn = 24 tw^3 sqrt(E Fyw) / h, "
     "halved within d/2 of the end (Eq J10-8)",
     "the two forces act at the same section on opposite flanges",
     f"{AISC} Section J10.5", ()),
    ("panel_zone",
     "panel-zone web shear, Rn = 0.60 Fy dc tw, reduced by (1.4 - alpha Pr/Py) above alpha Pr = 0.4 Py "
     "(Eqs J10-9, J10-10)",
     "the effect of panel-zone deformation on frame stability is not considered in the analysis",
     f"{AISC} Section J10.6", ()),
    ("seat_flexure",
     "flexural yielding of an unstiffened seat angle's outstanding leg at the critical section, Mn = Fy L t^2 / 4, under "
     "the beam reaction at the middle of its bearing length",
     "the critical section lies a judged offset beyond the angle thickness from the back of the vertical leg; the "
     "bearing length is the outstanding leg less the setback",
     f"{MANUAL} Part 10 (unstiffened seated connections)", ()),
    ("prying",
     "bolt tension with prying action by the Struik-de Back T-stub model in the Manual's form: available tension per "
     "bolt B Q with Q from tc, alpha' and delta",
     "a T-stub flange in double curvature between the bolt line and the stem; bolts in one line on each side of the stem",
     f"{MANUAL} Part 9; Kulak, Fisher and Struik (1987) Sections 17.5-17.6", ()),
)

MAKEABILITY: tuple[tuple, ...] = (
    ("spacing_min", "centre-to-centre spacing of holes at least 2-2/3 d", "standard, oversized or slotted holes of the "
     "declared sizes", f"{AISC} Section J3.4"),
    ("edge_min", "edge distance from each hole centre at least Table J3.4's value for the bolt size", "edges sheared or "
     "rolled as fabricated; measured to the hole centre", f"{AISC} Section J3.5, Table J3.4",
     ("the Table J3.5 increment C2 for oversized and slotted holes is not added to the minimum edge distance",)),
    ("spacing_max", "spacing of bolts in the line of force at most 24 t and 12 in (14 t and 7 in for unpainted "
     "weathering steel)", "the thinner connected part sets the limit", f"{AISC} Section J3.6"),
    ("edge_max", "edge distance at most 12 t and 6 in", "the connected part's own thickness sets the limit",
     f"{AISC} Section J3.6"),
    ("fillet_size", "fillet size at least Table J2.4's minimum for the thinner part joined, length at least four "
     "times the size", "fillet welds in T-joints; the size limit along edges applies to lap joints, which the "
     "catalogue's shear connections do not use", f"{AISC} Section J2.2b, Table J2.4",
     ("weld access and torch angle are not checked: the catalogue's fillets join a plate, angle or tee to an open "
      "face, and a weld between a column's flanges assumes the flanges leave the welder room",)),
    ("hole_use", "oversized holes and slots parallel to the force only in slip-critical joints", "holes as declared on "
     "each ply", f"{AISC} Section J3.3; RCSC 2025 Section 3.3"),
    ("joint_type", "the joint's installation meets the RCSC requirements its use imposes: Group 150 and 200 bolts in "
     "tension pretensioned; oversized holes and parallel slots slip-critical", "the joint carries the loads declared",
     "RCSC 2025 Sections 4.2 and 4.3; AISC 360-22 Section J3.2"),
    ("clearance", "room to tighten each bolt: the distance from the bolt to the nearest obstruction at least half the "
     "nut's width across corners plus a socket allowance", "a standard impact wrench socket on a heavy hex nut",
     f"{MANUAL} Part 7 (entering and tightening clearances, method encoded with a judged allowance)",
     ("bolt lengths are not checked: the fabricator orders each length from the grip by the Manual's rule, and the "
      "catalogue's grips are well inside the stocked lengths",)),
)
"""Plate thicknesses are makeable by catalogue membership, which lowering checks: a fixed
plate, stiffener or seat thickness must be one the registry's shop deck stocks
(shop_deck.plate.*)."""


ROWS: Mapping[str, tuple[ValidityRow, ...]] = {
    "cope_buckling": (
        _row("cope_buckling", "cope_length", "cope length c <= 2 d", f"{MANUAL} Part 9, limits of the cope-buckling method"),
        _row("cope_buckling", "cope_depth", "each cope depth <= d / 2", f"{MANUAL} Part 9, limits of the top-cope "
             "method; for both flanges coped, a maintainers' bound the Companion's Example II.A-7 (dct = 0.22 d) lies "
             "inside"),
    ),
    "compression": (
        _row("compression", "width_thickness", "seat stiffener width-to-thickness W / ts <= 0.56 sqrt(E / Fy)",
             f"{MANUAL} Part 10 (stiffened seated connections); {AISC} Section J4.4"),
    ),
    "ductility": (
        _row("ductility", "conventional_a", "a conventional single plate has its bolt line at most 3.5 in from the "
             "weld line", f"{MANUAL} Part 10, conventional configuration"),
        _row("ductility", "conventional_rows", "a conventional single plate has at most 12 bolt rows",
             f"{MANUAL} Part 10, conventional configuration"),
    ),
    "prying": (
        _row("prying", "bolt_clear_of_stem", "the bolt line lies outside the stem face by more than half a bolt "
             "diameter (b' > 0)", "Kulak, Fisher and Struik (1987) Section 17.5"),
    ),
}


MODES: dict[str, FailureMode] = {}
MODELS: dict[FailureMode, ModelSpec] = {}

for short, form, validity, source, rows in STRENGTH:
    MODES[short] = _mode(short)
    MODELS[MODES[short]] = _spec(short, form, validity, source, rows or ROWS.get(short, ()))

for short, form, validity, source, *unchecked in MAKEABILITY:
    MODES[short] = _mode(short)
    MODELS[MODES[short]] = _spec(short, form, validity, source, unchecked=unchecked[0] if unchecked else ())

for short, form, validity, source in (
    ("compression", "compressive yielding of a seat stiffener's section under the seat, Rn = Fy Ag (Eq J4-6)",
     "the stiffener is welded to the support along its full length, so it cannot buckle as a column; its width-to-"
     "thickness row excludes local buckling, the Manual's form of the short-element condition", f"{AISC} Section J4.4"),
    ("cope_buckling", "flexural yielding and local buckling of a coped beam web against the moment at the cope "
     "face: a top cope by the Manual's slenderness method on the remaining tee (Mn = Mp to My over lambda_p < "
     "hc/tw <= 2 lambda_p, elastic buckling above); both flanges coped by Section F11 on the remaining web with "
     "Lb = c and the Manual's Cb", "the reaction acts at the support face, e = c + setback; the tee's fillets are "
     "neglected; both copes have the same length; the cope's reentrant corners are cut to the radius Section J1.6 "
     "requires, a fabrication premise the deck does not check", f"{MANUAL} Part 9, Eqs 9-9 to 9-21; {AISC} Section F11"),
    ("plate_buckling", "lateral-torsional buckling of an extended single plate as a rectangular bar, Section F11 "
     "with Lb = a and Cb = 1.84, against the moment at the weld line", "the plate is unstiffened between the weld "
     "and the bolt line; the beam is braced against rotation about its axis", f"{MANUAL} Part 10; {AISC} Section F11"),
    ("ductility", "rotational ductility of a conventional single-plate connection: plate or beam web thin enough "
     "(t <= d/2 + 1/16 in) to yield before the bolts fracture, and the weld at least five-eighths of the plate "
     "thickness so the plate yields before the weld", "the connection is a conventional single plate, so the simple "
     "beam's end rotation is accommodated by bolt deformation and plate yielding", f"{MANUAL} Part 10"),
    ("extended_ductility", "rotational ductility of an extended single-plate connection: the plate no thicker than "
     "tmax = 6 Mmax / (Fy L^2), Mmax = (Fnv / 0.90) Ab C' with C' the bolt group's elastic moment coefficient, so it "
     "yields before the bolts fracture, and the weld at least five-eighths of the plate thickness",
     "the connection is an extended single plate whose rotation the plate's yielding accommodates", f"{MANUAL} Part 10"),
):
    MODES[short] = _mode(short)
    MODELS[MODES[short]] = _spec(short, form, validity, source, ROWS.get(short, ()))

LOAD_PATH = _mode("load_path")
"""An axial or other force component a v1.0 connection type has no checked path for.
Unmodelled: requiring it yields a Gap needing NoModel, so the verdict is UNKNOWN."""

STIFFENED_FORCE = _mode("j10_stiffeners")
"""Transverse stiffeners and doublers at a concentrated force (J10.7-J10.9). Unmodelled in
v1.0."""

UNMODELLED = frozenset({LOAD_PATH, STIFFENED_FORCE})

QOIS: Mapping[str, FailureMode] = {short: mode for short, mode in MODES.items()}
"""A claim names a mode by its short name: `st1.block_shear <= 1`."""
