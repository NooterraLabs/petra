"""Failure modes, model premises and validity rows of the steel deck. Trusted.

One FailureMode per limit state, each with one ModelSpec naming its clause. The model
premise's source_hash covers every trusted module of the package (lower, limits, checks,
build, vocab, domain) and the mechanics layer under them (petra/mechanics), so editing any
of the physics changes every steel premise label.
A mode's validity rows are the method's applicability limits the kernel decides over the
design's box (checks.ROWS states each). A mode with no row says why in UNBOUNDED, and its
model's validity words end with that reason (docs/principles.md D3).
"""
from __future__ import annotations

import hashlib
import os
from typing import Mapping

from ... import mechanics
from ..base import FailureMode, ModelSpec, ValidityRow

TRUSTED = ("lower", "limits", "checks", "build", "vocab", "domain")
"""The package modules whose source is the physics. generate, twin, faults, breaker and
package are tooling and cannot change a verdict."""

HASHED = (*(os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py") for name in TRUSTED),
          *mechanics.SOURCES)
"""The files the premise hash reads: the trusted modules in TRUSTED order, then the
mechanics layer's (petra.mechanics.SOURCES), whose formulas the trusted modules state."""


def _source_hash() -> str:
    """sha256 over HASHED's sources, read from disk so that vocab can be imported before
    the others."""
    digest = hashlib.sha256()
    for path in HASHED:
        with open(path, encoding="utf-8") as f:
            digest.update(f.read().encode("utf-8"))
    return digest.hexdigest()[:16]


SOURCE_HASH = _source_hash()
OWNER = "petra-maintainers"
AISC = "AISC 360-22"
MANUAL = "AISC Steel Construction Manual, 16th ed. (method encoded, not its text)"


def _mode(short: str) -> FailureMode:
    return FailureMode(f"steel.{short}")


def _spec(short: str, form: str, validity: str, source: str, rows: tuple[ValidityRow, ...],
          unchecked: tuple[str, ...]) -> ModelSpec:
    """A mode's model; one with no validity row carries its UNBOUNDED reason in its words."""
    words = validity if rows else f"{validity}. Unbounded: {UNBOUNDED[short]}"
    return ModelSpec(f"steel.{short}", form, words, OWNER, source, SOURCE_HASH, rows, unchecked)


def _row(short: str, name: str, text: str, source: str) -> ValidityRow:
    return ValidityRow(f"steel.{short}.{name}", text, source)


# --- Strength limit states -------------------------------------------------------------------

STRENGTH: tuple[tuple[str, str, str, str, tuple[ValidityRow, ...]], ...] = (
    ("bolts",
     "bolt shear rupture (Eq J3-1) and bearing and tearout at every hole (Eq J3-6a-f), taken per bolt as the least of "
     "its shear strength and its bearing or tearout strength in each ply, summed over a concentric group; an "
     "eccentric group by the elastic method against the weakest bolt; through declared fillers the shear strength "
     "times 0.85, J5.2(a)'s least factor, since the grammar gives no filler thickness",
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
     "the element's gross shear plane runs the length of its bolt line or weld; a beam web's runs its depth less the "
     "copes, bolted or welded (Companion II.A-5)",
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
     "Ubs Fu Ant <= 0.60 Fy Agv + Ubs Fu Ant (Eq J4-5), Ubs = 1 for one column and 0.5 for more; a beam web's "
     "block runs to the beam end less the 1/4 in the beam may be delivered short (Companion II.A-4)",
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
     "the plate bends about its strong axis at the bolt or weld line nearest the load (a bracket's section A-A); a "
     "rectangular bracket plate's buckling is plate_buckling's, a shaped bracket's free edge bracket_edge's",
     f"{AISC} Section J4.5; {MANUAL} Parts 10 and 15", ()),
    ("flexural_rupture",
     "flexural rupture of the net section of a connecting plate, Mn = Fu Znet (Section J4.5)",
     "the net section through the line of holes nearest the support; with an odd number of rows the middle hole on the "
     "axis removes its own t dh'^2 / 4 (Companion II.A-17B)",
     f"{AISC} Section J4.5; {MANUAL} Part 15", ()),
    ("weld",
     "fillet weld strength Rn = 0.60 FEXX Awe (Eq J2-4) with kds = 1, every concentric group being longitudinal lines; "
     "the directional increase of Eq J2-5 and the group rule of Eq J2-6 are permitted, not required, and not taken; "
     "an eccentric group (parallel lines, or a line with returns in a C) by the elastic method on its line properties, "
     "at its most stressed point; a seat angle's two "
     "lines, its vertical leg bearing on the support below them, by the Manual's seat-weld form f = R sqrt(L^2 + 20.25 "
     "e^2) / (2 L^2) (Table 10-6, Companion II.A-16); a seat stiffener's welds, which the reaction loads from their end "
     "as at a bearing stiffener (Commentary J2.2b), also over their effective length past 100 w, beta l with beta = 1.2 "
     "- 0.002 l / w and 180 w past 300 w (Section J2.2b(d), Eq J2-1)",
     "matching filler metal (Table J2.5); welds of the declared size and length; the elastic method assumes a rigid "
     "connected part; support-side welds as Manual Table 10-2 welds B, each line carrying its share at the outstanding "
     "leg's width (a single angle's reaction at the beam web's centre, the leg plus tw/2, Companion II.A-29; a tee's "
     "flange-tip lines at half the flange width, Companion II.A-31)",
     f"{AISC} Sections J2.2b(d) and J2.4, Table J2.5; {MANUAL} Part 8 (elastic method)", ()),
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
     "(Eqs J10-2, J10-3); on a seat, lb is the seat less the setback and the 1/4 in underrun (Companion II.A-14)",
     "a rolled W shape with no stiffener at the force",
     f"{AISC} Section J10.2", ()),
    ("web_crippling",
     "web local crippling under a compressive concentrated force (Eqs J10-4, J10-5a, J10-5b, Qf = 1); on a seat, lb "
     "is the seat less the setback and the 1/4 in underrun (Companion II.A-14)",
     "a rolled W shape with no stiffener at the force; the force bears on one flange",
     f"{AISC} Section J10.3", ()),
    ("flange_local_bending",
     "flange local bending under a tensile concentrated force, Rn = 6.25 Fyf tf^2, halved within 10 tf of the end "
     "(Eq J10-1); J10.1's exemption for a load narrower than 0.15 bf across the flange is not taken, since the "
     "grammar declares no width across the flange",
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
     "the beam reaction at the middle of the bearing length it needs: the least of the outstanding leg less the setback "
     "(with the 1/4 in underrun) and the length web local yielding and crippling require (J10.2, J10.3), not less than "
     "kdes (Manual Table 10-5, Companion II.A-12A)",
     "the critical section lies a judged offset beyond the angle thickness from the back of the vertical leg",
     f"{MANUAL} Part 10 (unstiffened seated connections)", ()),
    ("prying",
     "bolt tension with prying action by the Struik-de Back T-stub model in the Manual's form: available tension per "
     "bolt B Q, B = phi F'nt Ab reduced for the group's shear by Eq J3-3 (F'nt = Fnt without it; Companion II.A-1B), "
     "with Q from tc, alpha' and delta = 1 - d'/p (d' the hole's length along the flange), for the tee's flange and for the support's flange under the same bolts "
     "(each taken against a rigid partner, as the Companion checks a column flange in II.C-1); each bolt's tributary "
     "length p by Manual Figure 9-4, at most 1.75 b either side of it: an end bolt min(le, 1.75 b) + min(s/2, 1.75 b), "
     "an inner bolt 2 min(s/2, 1.75 b) (Companion II.D-1), the support's flange with the tee's le and s and its own b",
     "a T-stub flange in double curvature between the bolt line and the stem; bolts in one line on each side of the "
     "stem, centred on the support's web",
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
    ("joint_type", "the joint's installation meets the RCSC requirements its use imposes: at least snug-tight, and "
     "Group 150 and 200 bolts in tension pretensioned (the holes that need a slip-critical joint are hole_use's rule)",
     "the joint carries the loads declared", "RCSC 2025 Sections 4.1 and 4.2; AISC 360-22 Section J3.2"),
    ("clearance", "room to tighten each bolt: the distance from the bolt to the nearest obstruction at least half the "
     "nut's width across corners plus a socket allowance", "a standard impact wrench socket on a heavy hex nut",
     f"{MANUAL} Part 7 (entering and tightening clearances, method encoded with a judged allowance)",
     ("bolt lengths are not checked: the fabricator orders each length from the grip by the Manual's rule, and the "
      "catalogue's grips are well inside the stocked lengths",)),
)
"""Plate thicknesses are makeable by catalogue membership, which lowering checks: a fixed
plate, stiffener or seat thickness must be one the registry's shop deck stocks
(shop_deck.plate.*)."""


BOTH_FACES = "the plate is welded to the support with a fillet on each face, as the five-eighths rule assumes"

ROWS: Mapping[str, tuple[ValidityRow, ...]] = {
    "cope_buckling": (
        _row("cope_buckling", "cope_length", "cope length c <= 2 d", f"{MANUAL} Part 9, limits of the cope-buckling method"),
        _row("cope_buckling", "cope_depth", "each cope depth <= d / 2", f"{MANUAL} Part 9, limits of the top-cope "
             "method; for both flanges coped, a maintainers' bound the Companion's Example II.A-7 (dct = 0.22 d) lies "
             "inside"),
    ),
    "ductility": (
        _row("ductility", "conventional_a", "a conventional single plate has its bolt line at most 3.5 in from the "
             "weld line", f"{MANUAL} Part 10, conventional configuration"),
        _row("ductility", "conventional_rows", "a conventional single plate has at most 12 bolt rows",
             f"{MANUAL} Part 10, conventional configuration"),
        _row("ductility", "both_faces", BOTH_FACES, f"{MANUAL} Part 10, conventional configuration (Companion II.A-17A)"),
    ),
    "extended_ductility": (
        _row("extended_ductility", "both_faces", BOTH_FACES, f"{MANUAL} Part 10, extended configuration"),
    ),
    "prying": (
        _row("prying", "bolt_clear_of_stem", "each bolt line lies outside the web its flange bends about (the tee's "
             "stem, the support's web) by more than half a bolt diameter (b' > 0)", "Kulak, Fisher and Struik (1987) "
             "Section 17.5"),
    ),
}


_RULE = "a detailing rule: the check is the limit itself, so there is no range outside which it stops applying"
_OWN = "states no range of its own"
_THEIR = "state no range of their own"

UNBOUNDED: Mapping[str, str] = {
    "bolts": f"Eqs J3-1 and J3-6 {_THEIR}; Table J3.2's reduction of Fnv for long end-loaded joints does not arise, "
             "since every catalogue bolt group is a shear connection's, a bracket's or a hanger's, which Commentary J3.7 "
             "exempts",
    "bolt_tension": f"Eq J3-1 {_OWN}",
    "bolt_combined": f"Eqs J3-3a and J3-3b {_THEIR}; the exemption for a small stress is a branch of the check",
    "slip": f"Eqs J3-4, J3-5a and J3-5b {_THEIR}; ksc and the hole type's factors are branches of the check",
    "shear_yield": f"Eq J4-3 {_OWN}",
    "shear_rupture": f"Eq J4-4 {_OWN}",
    "block_shear": f"Eq J4-5 {_OWN}; Ubs is a branch of the check",
    "tension_yield": f"Eq J4-1 {_OWN}",
    "tension_rupture": f"Eq J4-2 {_OWN}",
    "flexural_yield": f"Section J4.5 {_OWN} for a plate's yielding",
    "flexural_rupture": f"Section J4.5 {_OWN} for a plate's rupture",
    "weld": f"Eq J2-4 {_OWN}; J2.2b(d)'s end-loaded length is a branch of the check",
    "weld_base_metal": f"Section J2.4(a) with Eq J4-4 {_OWN}",
    "bearing": f"Eq J7-1 {_OWN}",
    "web_local_yielding": f"Eqs J10-2 and J10-3 {_THEIR}; the force's distance to the member end chooses between them",
    "web_crippling": f"Eqs J10-4, J10-5a and J10-5b {_THEIR}; the end distance and lb / d choose between them",
    "flange_local_bending": f"Eq J10-1 {_OWN}; the end distance halves it inside the check",
    "web_sidesway_buckling": f"Eqs J10-6 and J10-7 {_THEIR}; the slenderness ratio that decides whether the limit "
                             "state applies is a branch of the check",
    "web_compression_buckling": f"Eq J10-8 {_OWN}; the end distance halves it inside the check",
    "panel_zone": f"Eqs J10-9 and J10-10 {_THEIR}; the axial ratio chooses between them",
    "seat_flexure": "the Manual's unstiffened-seat method states no range beyond its configuration",
    "compression": "J4.4(a)'s slenderness condition holds by the configuration: the stiffener is welded to the "
                   "support along its full length, so it has no laterally unbraced length",
    "plate_buckling": "Section F11's branches by Lb d / t^2 are taken inside the check, and F11 states no other range",
    "bracket_edge": "the Manual's bracket-plate method states no range beyond its configuration; Q's branches by "
                    "lambda are taken inside the check",
    "spacing_min": _RULE, "edge_min": _RULE, "spacing_max": _RULE, "edge_max": _RULE, "fillet_size": _RULE,
    "hole_use": _RULE, "joint_type": _RULE, "clearance": _RULE,
}
"""Why each mode with no validity row needs none (docs/principles.md D3): its clause states
no applicability range, its branches are inside its checks, or it is a detailing rule whose
check is the limit. tests/test_steel_principles.py holds every mode to a row or a reason."""


MODES: dict[str, FailureMode] = {}
MODELS: dict[FailureMode, ModelSpec] = {}

for short, form, validity, source, rows in STRENGTH:
    MODES[short] = _mode(short)
    MODELS[MODES[short]] = _spec(short, form, validity, source, rows or ROWS.get(short, ()), ())

for short, form, validity, source, *unchecked in MAKEABILITY:
    MODES[short] = _mode(short)
    MODELS[MODES[short]] = _spec(short, form, validity, source, (), unchecked[0] if unchecked else ())

for short, form, validity, source in (
    ("compression", "compressive yielding of a seat stiffener's section under the seat, Rn = Fy Ag (Eq J4-6), and its "
     "width-to-thickness ratio W / t at most 0.56 sqrt(E / Fy), and its thickness at least the beam web's times "
     "Fy of the beam over Fy of the stiffener (Companion II.A-14)",
     "the stiffener is welded to the support along its full length, so it cannot buckle as a column; the Manual's "
     "width-to-thickness limit, a check of this mode beside the yielding check, excludes local buckling",
     f"{AISC} Section J4.4; {MANUAL} Part 10 (stiffened seated connections)"),
    ("cope_buckling", "flexural yielding and local buckling of a coped beam web against the moment at the cope "
     "face: a top cope by the Manual's slenderness method on the remaining tee (Mn = Mp to My over lambda_p < "
     "hc/tw <= 2 lambda_p, elastic buckling above); both flanges coped by Section F11 on the remaining web with "
     "Lb = c and the Manual's Cb", "the reaction acts at the support face, e = c + setback; the tee's fillets are "
     "neglected; both copes have the same length; the cope's reentrant corners are cut to the radius Section J1.6 "
     "requires, a fabrication premise the deck does not check", f"{MANUAL} Part 9, Eqs 9-9 to 9-21; {AISC} Section F11"),
    ("plate_buckling", "lateral-torsional buckling of a plate as a rectangular bar, Section F11: an extended single "
     "plate with Lb = a and Cb = 1.84 against the moment at the weld line; a rectangular bracket plate as a cantilever "
     "from section A-A, Lb the arm to the load and Cb = 1 (Section F1(c)), against the moment at A-A",
     "an extended plate is unstiffened between the weld and the bolt line, and its beam is braced against rotation "
     "about its axis; nothing braces a bracket plate's loaded end against moving sideways",
     f"{MANUAL} Part 10; {AISC} Sections F1 and F11"),
    ("ductility", "rotational ductility of a conventional single-plate connection: plate or beam web thin enough "
     "(t <= d/2 + 1/16 in) to yield before the bolts fracture, the fillet on each face of the plate at least "
     "five-eighths of its thickness so the plate yields before the weld, and the horizontal edge distance at least "
     "2d on the plate and the beam web (Companion II.A-17A)", "the connection is a conventional single plate, so the simple "
     "beam's end rotation is accommodated by bolt deformation and plate yielding", f"{MANUAL} Part 10"),
    ("bracket_edge", "a shaped bracket plate's free-edge section B-B, normal to its sloped edge: shear yielding, "
     "Vn = 0.60 Fy t b' against P sin theta, and the normal force and moment on it, N/Nc + M/Mc <= 1 with N = P cos "
     "theta and M = P e - N b'/2, at Fcr = Q Fy reduced for the edge's local buckling by its slenderness lambda",
     "a triangular or trapezoidal plate, unstiffened along its free edge, loaded in its plane at its top edge; the "
     "Manual's Q is continuous to 0.9998 at lambda = 0.70, where the deck's least-of form takes it", f"{MANUAL} Part 15, "
     "Eqs 15-6 to 15-18 (bracket plates)"),
    ("extended_ductility", "rotational ductility of an extended single-plate connection: the plate no thicker than "
     "tmax = 6 Mmax / (Fy L^2), Mmax = (Fnv / 0.90) Ab C' with C' the bolt group's elastic moment coefficient, so it "
     "yields before the bolts fracture, and the fillet on each face of the plate at least five-eighths of its thickness",
     "the connection is an extended single plate whose rotation the plate's yielding accommodates", f"{MANUAL} Part 10"),
):
    MODES[short] = _mode(short)
    MODELS[MODES[short]] = _spec(short, form, validity, source, ROWS.get(short, ()), ())

LOAD_PATH = _mode("load_path")
"""An axial or other force component a v1.0 connection type has no checked path for.
Unmodelled: requiring it yields a Gap needing NoModel, so the verdict is UNKNOWN."""

STIFFENED_FORCE = _mode("j10_stiffeners")
"""Transverse stiffeners and doublers at a concentrated force (J10.7-J10.9). Unmodelled in
v1.0."""

UNMODELLED = frozenset({LOAD_PATH, STIFFENED_FORCE})

QOIS: Mapping[str, FailureMode] = {short: mode for short, mode in MODES.items()}
"""A claim names a mode by its short name: `st1.block_shear <= 1`."""
