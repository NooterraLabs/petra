"""Failure modes, model premises and validity rows of the steel deck. Trusted.

One FailureMode per limit state, each with one ModelSpec naming its clause. The model
premise's source_hash covers every trusted module of the package (lower, limits, checks,
geometry, build, vocab, domain, path) and the mechanics layer under them (petra/mechanics), so
editing any of the physics changes every steel premise label.
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

TRUSTED = ("lower", "limits", "checks", "geometry", "build", "vocab", "domain", "path", "cyclic", "fatigue")
"""The package modules whose source is the physics, path's and cyclic's limit lists included
(they decide what coverage demands). generate, twin, faults, breaker and package are
tooling and cannot change a verdict. tests/test_steel_principles.py holds this to its
builder list."""

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
     "eccentric group holds C times its weakest bolt, C the larger of the elastic method's and the instantaneous "
     "center method's (Manual Part 7, R = Rult (1 - e^(-10 Delta))^0.55 with Delta = 0.34 in at the farthest bolt), "
     "the latter as a certified lower bound, and for a conventional single plate in Manual Table 10-9's "
     "configuration also C at e = a/2 (one column of at most 5 rows in standard or short-slotted holes, a at most "
     "3-1/2 in, welds on both faces at least 5/8 tp, Leh at least 2d on the plate and the beam web, and with "
     "standard holes the plate or the beam web at most d/2 + 1/16 in thick); a bracket's group holds the larger "
     "over the two methods of C times its weakest bolt, each bolt's tearout along its force about that method's "
     "centre (J3.11a), the least over centres at or beyond it and over the edges and holes the force can point at: "
     "the top edge and, where the force can point down, the bottom edge, at the edge distance; the back edge from "
     "a bolt above the centroid and the front edge or a shaped plate's sloping edge from one below, along the "
     "force; the next hole above, below, behind or ahead, at the clear spacing; a long slot either way takes the "
     "perpendicular slot's coefficients; a hanger's card fixes no direction in its plies' plane, so a slot there "
     "takes its length along the force and a long one the perpendicular slot's coefficients, and its group holds "
     "the lesser of its shear along the tee and across it, where each flange's outer line tears toward its side "
     "edge; through declared "
     "fillers the shear strength times 0.85, J5.2(a)'s least "
     "factor, since the grammar gives no filler thickness",
     "bolts of one group, size and installation; holes of the declared type; threads included or excluded as "
     "declared; both methods take the connected part as rigid, the elastic method rotating it about the group "
     "centroid with equal bolt springs, the instantaneous center method about the centre that balances the load "
     "with Crawford and Kulak's load-deformation curve; a bracket's support takes the opposite force at its holes "
     "and its edges are not declared",
     f"{AISC} Sections J3.7 and J3.11a, Table J3.2; {MANUAL} Part 7 (elastic and instantaneous center methods) and "
     f"Part 10 (Table 10-9)", ()),
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
     "slip resistance Rn = mu Du hf Tb ns ksc per bolt (Eqs J3-4, J3-5a/b), with the resistance factor of the hole type; "
     "in an eccentric bracket group, whose bolt forces turn across the depth along a plain slot, a plain slot takes "
     "the factor of a slot parallel to the load, and so does a slot under a hanger's shear, which its card gives no "
     "direction in the plies' plane",
     "faying surfaces prepared to the declared class; bolts pretensioned to at least Table J3.1; fillers as declared",
     f"{AISC} Sections J3.9 and J3.10; RCSC 2025 Section 5.4", ()),
    ("shear_yield",
     "shear yielding of the gross section of each connected element, Rn = 0.60 Fy Agv (Eq J4-3)",
     "the element's gross shear plane runs the length of its bolt line or weld; a beam web's runs its depth less the "
     "copes, bolted or welded (Companion II.A-5)",
     f"{AISC} Section J4.2(a)", ()),
    ("shear_rupture",
     "shear rupture of the net section of each connected element, Rn = 0.60 Fu Anv (Eq J4-4), holes 1/16 in wider "
     "than nominal (B4.3b); a slot in a hanger's flange takes its length along the section, since the card fixes no "
     "direction for it",
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
     "the directional increase of Eq J2-5 and the group rule of Eq J2-6 are permitted, not required, and taken only "
     "within the instantaneous center method; two eccentric groups by the instantaneous center method (each element "
     "kds f(p) of Fnw Aw per unit length, kds = 1 + 0.50 sin^1.5 theta, f(p) = [p (1.9 - 0.9 p)]^0.3, Delta_m = "
     "0.209 (theta + 2)^-0.32 w, Delta_u = 1.087 (theta + 6)^-0.65 w <= 0.17 w), as a certified lower bound on C, "
     "or the elastic method where its C is the larger: a bracket plate set on edge with a fillet on each face, its "
     "load at e past L/8 from the weld line (Manual Table 8-4's k = 0), and a lapped bracket plate's C, a line L long "
     "with returns kl at most 2 L at both ends toward the load, its load at e past L/8 from the C's centroid (Manual "
     "Table 8-8); every other eccentric group (a single fillet along a plate on edge, or a C with a shorter lever or "
     "longer returns) by the elastic method on its line properties, at its most stressed point; a C's centroid lies "
     "kl^2 / (2 kl + L) from its line toward the load (Manual Part 8); a seat angle's two "
     "lines, its vertical leg bearing on the support below them, by the Manual's seat-weld form f = R sqrt(L^2 + 20.25 "
     "e^2) / (2 L^2) (Table 10-6, Companion II.A-16); a seat stiffener's welds, which the reaction loads from their end "
     "as at a bearing stiffener (Commentary J2.2b), also over their effective length past 100 w, beta l with beta = 1.2 "
     "- 0.002 l / w and 180 w past 300 w (Section J2.2b(d), Eq J2-1)",
     "matching filler metal (Table J2.5); welds of the declared size and length; both methods assume a rigid "
     "connected part, the instantaneous center method turning it about the centre that balances the load, whose "
     "element nearest its deformation limit lies at an end of one of its welds; support-side welds as Manual Table 10-2 welds B, each line carrying its share at the outstanding "
     "leg's width (a single angle's reaction at the beam web's centre, the leg plus tw/2, Companion II.A-29; a tee's "
     "flange-tip lines at half the flange width, Companion II.A-31)",
     f"{AISC} Sections J2.2b(d) and J2.4, Table J2.5; {MANUAL} Part 8 (elastic and instantaneous center methods)", ()),
    ("weld_base_metal",
     "shear rupture of the base metal along each fusion face, 0.60 Fu t per unit length against the weld force it "
     "carries (Section J2.4(a) with Eq J4-4); under the instantaneous center method against the force along the "
     "weld, at most 1.04 times P / (lines L C) per unit length, the load's measure of Fnw Aw, since an element's "
     "share along the weld, kds f(p) cos theta in units of Fnw Aw, peaks at 1.035; the share across the weld pulls the part across its edge, and the "
     "Specification's shear planes are those of longitudinal shear (Commentary J2.4, Fig. C-J2.10)",
     "the base metal's thickness is uniform along the weld",
     f"{AISC} Sections J2.4(a) and J4.2(b)", ()),
    ("bearing",
     "bearing on the fitted bearing area of a stiffener, Rn = 1.8 Fy Apb (Eq J7-1), for each surface in contact at "
     "its own Fy: the stiffener's top edge and the seat plate on it, so the lesser Fy governs",
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
     "(Eqs J10-9, J10-10), against the panel's required shear, the declared panel_shear: the flange forces of the "
     "moment connections at the joint less the story shear (Commentary Eq C-J10-3), which the one flange force "
     "declared does not give; Pr is the declared axial force's magnitude, tension or compression. Demanded at every "
     "flange force, since the grammar does not say whether the force is one flange of a moment connection's "
     "couple (J10.6's double-concentrated forces); a case that gives no panel_shear or no axial leaves it open "
     "naming the load, since no value is safe over either's range, and a force with no couple closes it with a "
     "signed panel_shear of zero",
     "the effect of panel-zone deformation on frame stability is not considered in the analysis",
     f"{AISC} Section J10.6 and Commentary J10.6", ()),
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
     "with Q from tc, alpha' and delta = 1 - d'/p (d' the hole's length along the flange, a slot's length, since the "
     "card fixes no direction for it in the flange's plane), for the tee's flange and for the support's flange under "
     "the same bolts "
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
    ("edge_min", "edge distance from each hole centre at least Table J3.4's value for the bolt size, plus Table J3.5's "
     "C2 for an oversized hole and for a slot whose length points at the edge (a slot along the edge adds none, and "
     "a shaped bracket's sloping edge takes a slot's full C2, as does every edge of a hanger's plies, in whose plane "
     "the card fixes no direction)", "edges sheared or rolled as fabricated; measured to "
     "the hole centre; slots of the full length Table J3.3 allows", f"{AISC} Section J3.5, Tables J3.4 and J3.5"),
    ("spacing_max", "longitudinal spacing of bolts, the pitch along a bolt line, at most 24 t and 12 in (14 t and 7 in "
     "for unpainted weathering steel); the gauge across the force is not limited, since J3.6 limits the longitudinal "
     "spacing only (Commentary J3.6)", "the thinner connected part sets the limit", f"{AISC} Section J3.6"),
    ("edge_max", "edge distance at most 12 t and 6 in", "the connected part's own thickness sets the limit",
     f"{AISC} Section J3.6"),
    ("fillet_size", "fillet size at least Table J2.4's minimum for the thinner part joined, length at least four "
     "times the size", "fillet welds in T-joints; the size limit along edges applies to lap joints, which the "
     "catalogue's shear connections do not use", f"{AISC} Section J2.2b, Table J2.4",
     ("weld access and torch angle are not checked: the catalogue's fillets join a plate, angle or tee to an open "
      "face, and a weld between a column's flanges assumes the flanges leave the welder room",)),
    ("hole_use", "oversized holes and slots parallel to the force only in slip-critical joints; in an eccentric "
     "bracket group, whose bolt forces turn across the depth along a plain slot, any slot only in a slip-critical "
     "joint, and so under a hanger's shear, which its card gives no direction in the plies' plane (J3.3(e) and (f): "
     "in a bearing-type joint a slot lies normal to the load)", "holes as declared on "
     "each ply", f"{AISC} Section J3.3; RCSC 2025 Section 3.3"),
    ("joint_type", "the joint's installation meets the RCSC requirements its use imposes: at least snug-tight, "
     "Group 150 and 200 bolts in tension pretensioned, and in a cyclic case every joint pretensioned, excused where "
     "nSR <= 20,000 (J3.2(a)(2) allows snug-tight bolts in tension only where fatigue is no design consideration, "
     "J3.2(b)(1) defers to RCSC 4.2, and Appendix 3 considers and permits pretensioned joints only, Commentary 3.4); "
     "the holes that need a slip-critical joint are hole_use's rule",
     "the joint carries the loads declared",
     "RCSC 2025 Sections 4.1 and 4.2; AISC 360-22 Section J3.2, Commentary Section 3.4"),
    ("clearance", "room to tighten each bolt: the distance from the bolt to the nearest obstruction at least half the "
     "nut's width across corners plus a socket allowance", "a standard impact wrench socket on a heavy hex nut",
     f"{MANUAL} Part 7 (entering and tightening clearances, method encoded with a judged allowance)",
     ("bolt lengths are not checked: the fabricator orders each length from the grip by the Manual's rule, and the "
      "catalogue's grips are well inside the stocked lengths",)),
    ("beam_fit", "the parts on the beam fit it and the beam fits its support, each check need <= have in inches "
     "(geometry.py): a plate, angle or tee bolted to the beam web spans from Lev above its top row, `top` below the "
     "beam's top, to Lev below its bottom row, (rows - 1) s lower; its top edge is at least (d - T)/2 below the "
     "beam's top and its bottom edge at most (d + T)/2, the beam's flat web, T deep and centred on the web (Manual "
     "Part 1), except at a flange whose cope is at least (d - T)/2 deep and runs past the part: the cope starts at "
     "the beam end (the bolt line less "
     "the beam's end distance, a - Leh for a plate or a tee, the beam gauge less Leh for angles) or at the setback "
     "where that is farther out, and must reach the part's far edge (a plate's a + (columns - 1) g + its Leh, an "
     "angle's leg on the beam, a tee's stem, half its parent's depth); the beam web's holes, dh/2 above the top row "
     "and below the bottom row (dh the beam hole's size along the force, Table J3.3), lie at least (d - T)/2 below "
     "the top, or the top cope's depth where that is deeper, and at most d less (d - T)/2 or the bottom cope's depth "
     "where deeper; an end plate's welds, (rows - 1) s + 2 Lev - 2 w long, fit d less the larger of (d - T)/2 and "
     "each cope's depth at each flange ((d - T)/2 alone at an uncoped flange); the beam end stands clear of the "
     "support: the beam's "
     "end distance at most a (a shear tab), at most the beam gauge (angles), and with the tee flange's thickness at "
     "most a (a tee); and a seated beam's end, its setback as detailed, lies short of the seat angle's outstanding "
     "leg or the stiffener's width by more than petra.strict.length",
     "T, the workable flat depth between the toes of the fillets that the shapes table lists, bounds the flat web a "
     "part can bear on and a bolt can seat on, so each fillet reaches (d - T)/2 from its flange's outer face (kdes, "
     "k for design calculations, reaches less far in every W row and is not read here); a part's corner on a "
     "fillet, or on the fillet a shallow cope leaves, counts as not fitting, since the deck does not model clipped "
     "corners; where the lines leave a position open (the cope's start, an end plate's place down the web) the "
     "reading most favourable to fit is taken", f"{MANUAL} Part 1 (T); plain geometry of the drawn parts",
     ("whether the stated setback agrees with the beam end the bolt line and end distance draw is not checked",
      "a beam framing to a girder, whose flanges its own may meet, is not checked: the deck reads every support as a "
      "column")),
    ("flange_fit", "the parts on the support's flange fit it, each check need <= have in inches (geometry.py), with "
     "dh the support hole's size across the force (Table J3.3) and every position the lines leave open taken where "
     "it fits best: a pair of bolt lines, centred on the member at gauge g, spans g + dh <= bf and leaves g - dh >= "
     "tw between its holes for the web; a single angle's bolt line, beside the beam web, spans the beam's tw + the "
     "support gauge + dh/2 <= bf; welds on the face span: a plate or stiffener set on edge and welded on `sides` "
     "faces, t + sides w; a C-shaped weld's returns, kl + w; angles welded at their outstanding legs' toes, 2 leg + "
     "tw + 2 w (one angle, leg + tw + w); a tee welded at its flange tips, bf + 2 w; a seat angle welded at its "
     "ends, L + 2 w; each <= bf; a bracket's bolt columns, columns at gauge g, either all on one side of the web, "
     "(columns - 1) g + dh <= (bf - tw)/2, or split across it, g - dh >= tw, (columns - 1) g + dh <= bf and "
     "(ceil(columns/2) - 1) g + dh <= (bf - tw)/2 (the one-sided check, excused where the split fits); and a seat "
     "angle's bolt holes on its vertical leg, the top hole's edge, Lev - dh/2 below the heel (dh along the force), "
     "at least the angle's thickness, the bottom hole's, Lev + (rows - 1) s + dh/2, at most the leg",
     "a part's body may overhang the flange's tips, since nothing stands beyond them; bolts and welds must lie on "
     "the flange; a pair of bolt lines is centred on the member, as the grammar's gauge across the web reads",
     "plain geometry of the drawn parts",
     ("wrench clearance to the web is the clearance mode's; the flange's fillet under a bolt near the web is not "
      "checked beyond the holes clearing the web",)),
    ("web_fit", "the parts on a column's web fit it, each check need <= have in inches (geometry.py), the web's room "
     "being its flat between the fillets, T (Manual Part 1), and every position the lines leave open "
     "taken where it fits best: a pair of bolt lines spans g + dh; a single angle's bolt line, beside the beam web, "
     "tw + the support gauge + dh/2; parts: the outstanding legs, 2 leg + tw (one angle, leg + tw), a tee's flange "
     "bf, an end plate's width, a seat angle's length L, a bracket's bolt columns (columns - 1) g + dh and its plate "
     "(columns - 1) g + 2 Leh; welds as on a flange (flange_fit); each <= T; a seat angle's bolt holes on "
     "its vertical leg as on a flange; and the beam's flange, bf, passes between the column's flanges, d - 2 tf of "
     "the column, except where the beam end lies at or past the flange tips, (bf - tw)/2 of the column out from the "
     "web: the beam end at a - Leh (a plate, a tee), the beam gauge less Leh (angles), the end plate's thickness, or "
     "the setback (seats)",
     "the support is a column met on its web, the beam framing between its flanges (an assumed premise: a support "
     "on its web is read as a column, never a girder); a part or weld on the web's fillets counts as not fitting",
     f"{MANUAL} Part 1 (T); plain geometry of the drawn parts",
     ("a girder support, whose web a beam meets with its own depth between the girder's flanges or a cope, is not "
      "modelled: the premise reads every web support as a column",
      "the beam flange's corners against the column's web-to-flange fillets are not checked")),
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
    "fatigue_bolt_tension": (
        _row("fatigue_bolt_tension", "no_prying", "each flange the bolts bend is at least tmin = sqrt(4 T b' / (phi p "
             "Fu)) thick under the peak cyclic tension per bolt T, at each bolt's tributary length p, so the bolts carry "
             "no prying force", f"{MANUAL} Part 9, Eq 9-20a; {AISC} Appendix 3, Section 3.2 and Commentary 3.4 (the "
             "category holds only where prying is small)"),
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
    "tee_ductility": "Eqs 9-51, 9-52 and 9-53 state no range of their own; as the flexible width b vanishes their "
                     "first terms grow without bound and the caps, 5/8 ts and 0.115 sqrt(Fy ts), govern, which the "
                     "check takes with b floored at a millionth of an inch",
    "spacing_min": _RULE, "edge_min": _RULE, "spacing_max": _RULE, "edge_max": _RULE, "fillet_size": _RULE,
    "hole_use": _RULE, "joint_type": _RULE, "clearance": _RULE,
    "beam_fit": _RULE, "flange_fit": _RULE, "web_fit": _RULE,
    "fatigue_bolted": f"Eq A-3-1 {_OWN}; Section 3.1's floor of 20,000 cycles and the threshold FTH are branches of "
                      "the check",
    "fatigue_weld": f"Eq A-3-2 {_OWN}; Section 3.1's floor of 20,000 cycles and the 8 ksi threshold are branches of "
                    "the check",
    "fatigue_weld_end": f"Eqs A-3-1, A-3-5 and A-3-6 {_THEIR}; the floor of 20,000 cycles, the threshold and RFIL "
                        "reaching 1, past which the toe governs, are branches of the check",
    "fatigue_cope": f"Eq A-3-1 {_OWN}; Section 3.1's floor of 20,000 cycles and the threshold FTH are branches of "
                    "the check",
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
    ("tee_ductility", "rotational ductility of a shear tee: its flange bends before its bolts or welds to the "
     "support fracture, so the bolts are at least dmin = 0.0941 tf sqrt((Fy p / b)(b^2 / l^2 + 2)) <= 0.115 sqrt(Fy ts) "
     "in diameter (Manual Eq 9-52) or the flange-tip fillets at least wmin = 0.0155 (Fy tf^2 / b)(b^2 / l^2 + 2) <= "
     "(5/8) ts (Eq 9-51), Fy in ksi and lengths in inches, with b the flange's flexible width (Figure 9-6) and p the "
     "flange length a bolt acts on (Figure 9-4); or, the alternate where the stem is bolted to the beam, the stem or "
     "the beam web at most d/2 + 1/16 in thick (Eq 9-53) (Companion II.A-30, II.A-31)",
     "the tee's stem is bolted to the beam web and its flange bolted or welded to the support, so the beam end's "
     "rotation bends the flange; the bolt gauge is centred on the beam web, so b is the smaller of the tee's two",
     f"{MANUAL} Part 9 (shear tees, rotational ductility)"),
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


# --- Fatigue (Appendix 3) --------------------------------------------------------------------
# A load case that names cycles on the connection is cyclic (lower.CYCLES): its loads are
# service loads that vary inside their intervals, so each interval's width is the load's
# range and its larger magnitude the peak. cyclic.py says which details owe which mode.

APPENDIX3 = f"{AISC} Appendix 3"
EQ_A31 = "FSR = 1000 (Cf / nSR)^0.333 ksi, at least FTH (Eq A-3-1)"
FLOOR = "each check excused where nSR <= 20,000 (Section 3.1)"
PEAK = "the stress from the peak cyclic load, on the section the range is taken on, at most 0.66 Fy (Section 3.1)"
PRINCIPAL = ("the stress at a section is bounded by its extreme-fibre bending stress M / S plus its peak shear "
             "stress 3 V / (2 t d), which bounds the largest principal stress anywhere on it, a conservative bound; on "
             "a net section d is the depth less the holes and S the net section's, I / (d / 2) about the gross "
             "section's middle, each hole 1/16 in larger than its size along the line (Section B4.3b) and the holes "
             "centred on the depth at the pitch")
SERVICE = ("elastic analysis with no stress concentration factor (Section 3.2); the cyclic case states service loads; "
           "suitable corrosion protection or a mildly corrosive atmosphere (Section 3.1)")
NOT_CHECKED: dict[str, tuple[str, ...]] = {
    "": ("temperatures at most 300 F (Section 3.1)",),
    "fatigue_weld": ("end returns of two to four times the fillet's size where it is loaded normal to an angle's "
                     "outstanding leg or along an end plate's outer edge (Section 3.5)",),
    "fatigue_cope": ("the cope's corners cut to a radius of at least 3/8 in, which Case 1.3 asks of E' and Section 3.5 "
                     "of every reentrant corner",
                     "thermally cut edges no rougher than 1,000 micro-inches (Section 3.5)"),
}
"""The numeric premises of each fatigue model that no validity row states: the deck reads no
temperature, and the cope radius, the cut edges and the end returns are fabrication. The
package prints each as not checked; "" lists those every fatigue model has."""

FATIGUE: tuple[tuple[str, str, str, str], ...] = (
    ("fatigue_bolted",
     f"the stress range of the material a slip-critical or pretensioned bolt group connects, against category B's {EQ_A31}, "
     "Cf = 12 and FTH = 16 ksi (Section 3.4(a)): a slip-critical joint's on the gross section (Table A-3.1 Case 2.1), a "
     "pretensioned joint's on the net section through the line of holes (Case 2.2); each ply carries the bolt group's "
     f"shear on its section along the bolt line, and a ply that bends also its flexural checks' moment; {PRINCIPAL}; "
     f"{PEAK}; {FLOOR}",
     f"{SERVICE}; the joint meets its slip-critical or pretensioned requirements, which the bolts, slip and joint_type "
     "checks hold it to; the support's face under the bolts is the support member's, whose own stress range the "
     "connection does not know",
     f"{APPENDIX3}, Sections 3.1, 3.2 and 3.4(a), Table A-3.1 Cases 2.1 and 2.2"),
    ("fatigue_bolt_tension",
     "the tensile stress range of each bolt on its tensile stress area At = (pi / 4) (db - 0.9743 / n)^2, n threads per "
     f"inch (Eq A-3-7), against category G's {EQ_A31}, Cf = 0.39 and FTH = 7 ksi (Section 3.4(b), Table A-3.1 Case "
     "8.5): snug-tight bolts carry the whole range of the applied tension; pretensioned and slip-critical bolts, with "
     f"only steel in the grip, carry 20% of the peak applied tension (Section 3.4(b)); {FLOOR}",
     f"{SERVICE}; the tension is shared equally by the bolts; the grip holds only steel, a tee's flange and the "
     "support's; prying is negligible, which the row no_prying holds each flange to",
     f"{APPENDIX3}, Sections 3.1, 3.2 and 3.4(b), Eq A-3-7, Table A-3.1 Case 8.5; {MANUAL} Part 9"),
    ("fatigue_weld",
     "the shear stress range on each fillet's throat, w / sqrt 2, at its most stressed point as the weld check finds "
     "it (the elastic method for an eccentric group, the end-loaded effective length past 100 w), against category F's "
     f"FSR = 100 (1.5 / nSR)^0.167 ksi, at least 8 ksi (Eq A-3-2, Table A-3.1 Case 8.2); {FLOOR}",
     SERVICE,
     f"{APPENDIX3}, Sections 3.1, 3.3(b) and 3.5, Eq A-3-2, Table A-3.1 Case 8.2"),
    ("fatigue_weld_end",
     "a plate set on edge against the support and welded with a pair of fillets, one on each face (Table A-3.1 Case "
     "5.7): the plate's stress range across the welds, M / S + 3 V / (2 t L) with S = t L^2 / 6 over the weld length L, "
     f"against category C at the weld toe, {EQ_A31}, Cf = 4.4 and FTH = 10 ksi (Section 3.3(c)(1)), and at the weld "
     "root FSR = 1000 RFIL (4.4 / nSR)^0.333 ksi with no threshold (Eq A-3-5), RFIL = (0.06 + 0.72 w / tp) / tp^0.167 "
     "with w and tp in inches (Eq A-3-6), the root check excused where RFIL >= 1, past which the toe governs; "
     f"{PEAK}; {FLOOR}",
     f"{SERVICE}; the moment at the weld line is a single plate's V times the distance from the weld line to its "
     "bolt group's centroid, a + (columns - 1) g / 2, the most elastic analysis puts there with the beam end free to "
     "rotate at the bolts; a seat stiffener's V times 0.8 W and a bracket's V e, its flexural checks'; the side the "
     "moment puts in tension governs",
     f"{APPENDIX3}, Sections 3.1 and 3.3(c), Eqs A-3-1, A-3-5 and A-3-6, Table A-3.1 Case 5.7"),
    ("fatigue_cope",
     "a beam coped at both flanges: the stress range at the bottom cope's reentrant corner, M / S + 3 V / (2 tw hc) on "
     "the web the copes leave, S = tw hc^2 / 6 and M = V (c + setback), against category E' (E prime), "
     f"{EQ_A31}, Cf = 0.39 and FTH = 2.6 ksi (Table A-3.1 Case 1.3); {PEAK}; {FLOOR}",
     f"{SERVICE}; the top cope's corner, which the beam end's moment compresses, is no fatigue case (Commentary 3.2)",
     f"{APPENDIX3}, Sections 3.1, 3.3(a) and 3.5, Eq A-3-1, Table A-3.1 Case 1.3"),
)
"""The fatigue modes the deck checks. Their constants are petra/registry/steel_fatigue.py's."""

for short, form, validity, source in FATIGUE:
    MODES[short] = _mode(short)
    MODELS[MODES[short]] = _spec(short, form, validity, source, ROWS.get(short, ()),
                                 (*NOT_CHECKED[""], *NOT_CHECKED.get(short, ())))

FATIGUE_DETAIL = _mode("fatigue_detail")
"""A detail under cyclic load whose Table A-3.1 category the deck does not encode: a single
fillet at an angle's or a tee's toe, a plate welded on one face, a lapped plate's C-shaped
fillet, a seat angle, a hanger's tee stem and flange, a member's flange under a cyclic
tensile force. Unmodelled: the verdict is UNKNOWN, never PASS."""

LOAD_PATH = _mode("load_path")
"""An axial or other force component a v1.0 connection type has no checked path for.
Unmodelled: requiring it yields a Gap needing NoModel, so the verdict is UNKNOWN."""

STIFFENED_FORCE = _mode("j10_stiffeners")
"""The pair of full-depth transverse stiffeners J10.7 requires at an unframed member end
not otherwise restrained against twisting about its axis: demanded at a flange force whose
end is declared free (end_twist free). The deck draws no stiffeners, so the mode is
unmodelled and the verdict UNKNOWN. J10.8 and J10.9's stiffeners and doublers are never
credited: a force past a J10 limit state's unstiffened strength fails that check."""

UNMODELLED = frozenset({LOAD_PATH, STIFFENED_FORCE, FATIGUE_DETAIL})

QOIS: Mapping[str, FailureMode] = {short: mode for short, mode in MODES.items()}
"""A claim names a mode by its short name: `st1.block_shear <= 1`."""
