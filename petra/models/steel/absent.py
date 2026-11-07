"""Why a steel mode is not on a connection's load path. Readout only: nothing here changes a
verdict.

`domain.required` lists the modes the elements on a connection's load path owe (path.py).
`reasons` gives every other mode of the domain a one-line reason for that connection: the
part that would fail by it is not drawn, the force that would load it so is not there, or
the source's method takes it as its premise, said so. `domain.absent` hands them to the
readout (DomainSpec.absent), which prints the reason where the mode is not checked, in
place of "not demanded by the coverage table". tests/test_steel_coverage.py holds every
mode of every connection to one or the other, so a mode on no path and with no reason here
fails the suite.

A mode a declared load would add (an axial force, a hanger's shear) also has a reason
here; the readout prints its own load reason first, naming the load.
"""
from __future__ import annotations

from .lower import Bolts, Conn

FRAMED = ("shear_tab", "double_angle", "single_angle", "shear_tee", "shear_end_plate")
SEATS = ("seated", "stiffened_seat")
BRACKETS = ("bolt_bracket", "weld_bracket")

BOLT_MODES = ("bolts", "bolt_tension", "bolt_combined", "slip", "prying", "spacing_min", "spacing_max", "edge_min",
              "edge_max", "hole_use", "joint_type", "clearance", "block_shear")
WELD_MODES = ("weld", "weld_base_metal", "fillet_size")
J10 = ("web_local_yielding", "web_crippling", "flange_local_bending", "web_sidesway_buckling", "web_compression_buckling")

# --- Shared reasons ---------------------------------------------------------------------

NO_FITTED = "no milled or fitted surface carries load: it passes through bolts and welds (J7 is a fitted part's)"
UNTENSIONED = {
    "prying": "no bolt is in tension, so none is pried (Manual Part 9)",
    "bolt_combined": "no bolt is in tension, so no shear combines with tension (J3.8)",
}
ROTATION = ("rotational ductility is checked for a single plate and a shear tee, the sources' cases (Manual Parts 9 "
            "and 10); the Manual's flexibility practice for {what} is not encoded")
NO_COUPLE = "{what} delivers no flange couple to the support, so it does not shear the support's panel zone (J10.6)"


def _not_drawn(conn: Conn) -> dict[str, str]:
    """Parts some kinds draw and this one does not."""
    kind = conn.kind
    out = {
        "seat_flexure": "no seat angle is drawn",
        "compression": "no seat stiffener is drawn",
        "cope_buckling": "the beam is not coped: its full section reaches the connection" if kind in FRAMED
        else "no coped beam is drawn",
        "bracket_edge": "no shaped bracket plate is drawn",
        "plate_buckling": "no extended single plate or rectangular bracket plate, the parts that buckle sideways, is drawn",
        "extended_ductility": "no extended single plate is drawn",
        "tee_ductility": "no shear tee is drawn",
        "beam_fit": "no beam is drawn: the load is given at the support",
        "ductility": "no single plate framing a beam is drawn",
    }
    if kind == "shear_tab":
        extended = conn.get("form") == "extended"
        out["tee_ductility"] = "a single plate, not a tee: its rotational ductility is ductility's or extended_ductility's"
        out["ductility"] = "an extended single plate: its rotational ductility is extended_ductility's (Manual Part 10)"
        out["extended_ductility"] = "a conventional single plate: extended_ductility is an extended plate's (Manual Part 10)"
        if not extended:
            out["plate_buckling"] = ("a conventional single plate, its bolt line within 3-1/2 in of the weld: the Manual "
                                     "takes lateral buckling only of an extended plate (Part 10)")
    if kind in ("double_angle", "single_angle"):
        out["ductility"] = ROTATION.format(what="connection angles")
    if kind == "shear_end_plate":
        out["ductility"] = ROTATION.format(what="a shear end plate")
    if kind in SEATS:
        out["ductility"] = ROTATION.format(what="the top angle that lets a seated beam's end rotate")
        out["cope_buckling"] = "a seated beam is not coped: it bears on the seat with its full section"
    if kind == "stiffened_seat":
        out["seat_flexure"] = "the seat plate rests on the stiffener's fitted edge, which carries the reaction; no seat angle bends"
    if kind == "hanger":
        out["tee_ductility"] = "the hanger's tee is pulled along its stem; it is not a shear tee rotating with a beam end"
    if kind in BRACKETS:
        shaped = conn.get("free_edge") is not None
        if shaped:
            out["plate_buckling"] = "a shaped bracket: its free edge's buckling is bracket_edge's (Manual Part 15)"
        else:
            out["bracket_edge"] = "a rectangular bracket has no sloped free edge; its sideways buckling is plate_buckling's (F11)"
    return out


def _bolts(conn: Conn) -> dict[str, str]:
    """The bolt modes: no bolts, or bolts in shear only, or a joint that is not slip-critical."""
    kind = conn.kind
    bolts = conn.get("bolts")
    if not isinstance(bolts, Bolts):
        why = {
            "seated": "the seat angle is welded to the support and the beam bears on it: no bolt carries the reaction",
            "stiffened_seat": "the seat plate and stiffener are welded to the support and the beam bears on them: no bolt "
                              "carries the reaction",
            "flange_force": "the force is given at the member's flange: the part that delivers it, its bolts and welds, "
                            "are another connection's",
            "weld_bracket": "the bracket plate is welded to its support: no bolt carries the load",
        }[kind]
        return {m: why for m in BOLT_MODES}
    out = dict(UNTENSIONED)
    if kind in FRAMED:
        out["bolt_tension"] = ("a simple shear connection carries the beam's reaction, not a moment, so its bolts are in "
                               "shear; an axial force, which would pull them, is load_path's")
    elif kind == "seated":
        out["bolt_tension"] = "the seat's bolts carry the reaction in shear; the Manual's seat method takes none in tension (Part 10)"
    elif kind == "bolt_bracket":
        out["bolt_tension"] = ("the load acts in the plane of the bracket's bolt group, so the bolts carry it in shear, "
                               "its eccentricity by the elastic method")
    if bolts.joint != "slip_critical":
        out["slip"] = (f"the joint is {bolts.joint.replace('_', '-')}, not slip-critical: a bearing joint may slip into "
                       "bearing, which the bolts check takes (J3.9 binds slip-critical joints)")
    elif kind == "hanger":
        out["slip"] = "slip-critical bolts in tension alone carry nothing across the faying surface; a shear load adds slip"
    if kind == "hanger":
        out["bolts"] = "the bolts carry the hanger's tension; a declared shear load adds their shear checks"
        out["bolt_combined"] = "the bolts carry tension alone; a declared shear load adds its combination (J3.8)"
        out["block_shear"] = ("the bolts pull the tee flange out of its plane: its shear either side of the stem is "
                              "shear_yield's and shear_rupture's, and no block tears out in its plane (J4.3)")
    if kind == "seated":
        out["block_shear"] = ("the bolts hold the seat up, so a block of its leg could tear out only up through the heel, "
                              "where the outstanding leg continues it; each bolt's tearout toward the heel is the bolts check's")
    return out


def _welds(conn: Conn) -> dict[str, str]:
    kind = conn.kind
    why = {
        "double_angle": "the angles are bolted to the support; no weld is drawn",
        "single_angle": "the angle is bolted to the support; no weld is drawn",
        "shear_tee": "the tee is bolted to the support; no weld is drawn",
        "seated": "the seat angle is bolted to the support; no weld is drawn",
        "flange_force": "the force is given at the member's flange: the part that delivers it, its bolts and welds, "
                        "are another connection's",
        "bolt_bracket": "the bracket plate is bolted to its support; no weld is drawn",
        "hanger": "the tee is bolted to the support's flange; what hangs from its stem is not drawn",
    }.get(kind)
    return {m: why for m in WELD_MODES} if why else {}


def _members(conn: Conn) -> dict[str, str]:
    """J10, the panel zone, J10.7's end stiffeners, sections in tension and flexure, J7."""
    kind = conn.kind
    out: dict[str, str] = {}
    if kind in FRAMED:
        out.update({m: "no force acts across a member's flange: the beam frames by its web and the reaction runs along "
                       "the support's face (J10)" for m in J10})
        out["panel_zone"] = NO_COUPLE.format(what="a simple shear connection")
        out["j10_stiffeners"] = ("the beam end is framed: its web is bolted or welded to the support, which holds it "
                                 "against twisting about its axis (J10.7 asks stiffeners only at an unframed end)")
        out["bearing"] = NO_FITTED
        out["tension_yield"] = out["tension_rupture"] = ("no part is pulled: the reaction loads the parts in shear and "
                                                         "bending; an axial force, which would, is load_path's")
        if kind in ("double_angle", "single_angle") and conn.get("support_side") == "welded":
            bent = ("welded at the toe, the outstanding leg hands the reaction's eccentricity to the weld, the weaker: a "
                    "fillet no larger than the leg is thick (fillet_size) fails before the leg yields in flexure")
        elif kind == "double_angle":
            bent = ("the angles share the reaction either side of the beam web, so neither bends out of its plane, and "
                    "the Manual's double-angle method neglects its small eccentricity in it (Part 10)")
        elif kind == "shear_end_plate":
            bent = ("the end plate takes the reaction from the beam web at its middle and hands it to bolt lines either "
                    "side alike: it carries it in shear, not in bending")
        else:
            bent = ""
        out["flexural_yield"] = out["flexural_rupture"] = bent
        out["load_path"] = "the connection carries the beam's reaction by the checked path; an axial load would add load_path"
    elif kind in SEATS:
        out["flange_local_bending"] = "the seat pushes up on the beam's flange, a compressive force: J10.1 is a tensile force's"
        out["web_sidesway_buckling"] = ("the seat and the top angle hold both of the beam's flanges at its end, so they "
                                        "cannot move sideways relative to each other (J10.4 applies only where they can)")
        out["web_compression_buckling"] = "the seat pushes on one flange only; J10.5 is a pair of compressive forces on both"
        out["panel_zone"] = NO_COUPLE.format(what="a seat")
        out["j10_stiffeners"] = ("the top angle holds the beam's top flange, restraining its end against twisting about "
                                 "its axis (J10.7 asks stiffeners only at an unframed end)")
        out["tension_yield"] = out["tension_rupture"] = "no part is pulled: the beam bears on the seat, which carries the reaction"
        out["load_path"] = "the seat carries the beam's reaction by the checked path; an axial load would add load_path"
        if kind == "seated":
            out["bearing"] = ("the beam bears on the seat angle's leg, neither milled nor fitted: its bearing checks are "
                              "J10's on the web and the leg's own (J7 is a fitted part's)")
            out["shear_rupture"] = ("the leg the beam bears on has no holes and the beam web none: their shear sections are "
                                    "gross, which shear_yield checks")
            out["flexural_yield"] = out["flexural_rupture"] = "the seat angle's bending is seat_flexure's (Manual Part 10)"
        else:
            out["shear_rupture"] = out["flexural_rupture"] = ("no part has holes: every section is gross, which yielding "
                                                              "checks")
    elif kind in BRACKETS:
        out.update({m: "the bracket's load runs in the plane of the support's face, along it; no force acts across a "
                       "member's flange (J10)" for m in J10})
        out["panel_zone"] = ("the bracket's moment acts in the plane of the support's face, not as a flange couple across "
                             "its panel (J10.6)")
        out["j10_stiffeners"] = "no member end is drawn: J10.7's stiffeners are an unframed end's"
        out["bearing"] = NO_FITTED
        out["tension_yield"] = out["tension_rupture"] = "the load acts in the bracket plate's plane, in shear and bending; nothing pulls it"
        out["load_path"] = "the bracket carries its one load, in its plane, by the checked path"
        if kind == "weld_bracket":
            out["shear_rupture"] = out["flexural_rupture"] = ("the plate is welded, with no holes: its gross section is "
                                                              "its net, which yielding checks")
    elif kind == "hanger":
        out["flange_local_bending"] = ("the bolts load the support's flange at points, not through a plate welded across "
                                       "it (J10.1's case): its bending under them is the support flange's prying check")
        for m in ("web_crippling", "web_sidesway_buckling", "web_compression_buckling"):
            out[m] = "the hanger pulls on the support's flange: crippling and buckling of its web are a compressive force's (J10.3 to J10.5)"
        out["panel_zone"] = NO_COUPLE.format(what="a hanger's single tension")
        out["j10_stiffeners"] = ("the hanger loads the support where it hangs; whether the support's end is framed is the "
                                 "support's own connection's (J10.7)")
        out["bearing"] = "no part bears: the tension passes through the bolts (J7 is a fitted part's)"
        out["flexural_yield"] = out["flexural_rupture"] = ("the tee flange's and the support flange's bending under the "
                                                           "bolts is prying's T-stub model (Manual Part 9)")
        out["load_path"] = "the hanger's tension and shear are the loads its path carries"
    elif kind == "flange_force":
        force = conn.attrs["force_kind"]
        pair = conn.get("pair")
        if force == "tensile":
            out["web_crippling"] = "the force is tensile: web crippling is a compressive force's (J10.3)"
            out["web_sidesway_buckling"] = "the force is tensile: web sidesway buckling is a compressive force's (J10.4)"
            out["web_compression_buckling"] = "the force is tensile: web compression buckling is a compressive pair's (J10.5)"
        else:
            out["flange_local_bending"] = "the force is compressive: flange local bending is a tensile force's (J10.1)"
            if pair == "double":
                out["web_sidesway_buckling"] = "a pair on both flanges, whose web is J10.5's: J10.4 is a single force's"
            else:
                out["web_compression_buckling"] = "a single force: J10.5 is a pair of compressive forces on both flanges"
        if conn.attrs["location"] == "interior":
            out["j10_stiffeners"] = "the force is away from the member end: J10.7's stiffeners are an unframed end's"
        else:
            out["j10_stiffeners"] = ("the member end is declared restrained against twisting about its axis (end_twist "
                                     "restrained): J10.7 asks no stiffeners there")
        given = "the force is given at the member's flange: no connecting part is drawn"
        for m in ("shear_yield", "shear_rupture", "seat_flexure", "compression", "cope_buckling", "plate_buckling",
                  "ductility", "extended_ductility", "tee_ductility", "bracket_edge"):
            out[m] = given
        out["shear_yield"] = out["shear_rupture"] = "the member's web in shear is its panel zone's (J10.6); no connecting part is drawn"
        out["tension_yield"] = out["tension_rupture"] = out["flexural_yield"] = out["flexural_rupture"] = (
            "the member's own tension and flexure are its member design (Chapters D and F), not the force's local checks")
        out["bearing"] = "the force's bearing on the flange is given as its length lb; no fitted part is drawn (J7)"
        out["beam_fit"] = out["flange_fit"] = out["web_fit"] = "nothing is drawn on the member to fit: the force is given at its flange"
        out["load_path"] = "the force is the whole load: J10 takes it, and the panel zone reads the member's axial load"
    return {m: why for m, why in out.items() if why}


def _faces(conn: Conn) -> dict[str, str]:
    support = conn.attrs.get("support")
    if support is None:
        return {}
    if support.face == "flange":
        return {"web_fit": "the support is met on its flange: nothing is drawn on its web or between its flanges"}
    return {"flange_fit": "the support is met on its web: nothing is drawn on its flanges"}


def reasons(conn: Conn) -> dict[str, str]:
    """A reason, by mode short name, for each mode that can be off this connection's path."""
    return {**_not_drawn(conn), **_bolts(conn), **_welds(conn), **_members(conn), **_faces(conn)}
