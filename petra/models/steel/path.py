"""Each connection's load path and the limit states every element on it owes. Trusted.

A connection carries its force from the supported member to the support through a chain
of elements: a beam web, a bolt group, a plate, a weld, the support's face. `path` gives
that chain for one connection as Links, each an element (the name its checks carry, as
in "plate: shear yielding of the gross section") and a role. ROLE_LIMITS gives each role
the fixed list of limit states every element in that role must satisfy. Coverage demands
the union along the path (domain.required), so limit-state completeness is set inclusion
twice over: every element of the kind is on its path, and every limit state of its role
is demanded. The tests check the converse: every element on the path gets a check of
every limit state its role lists.

Every connection with a support ends at the support's face, in role flange_face or
web_face: the parts drawn on it must fit it. Every beam web owes beam_fit, the parts drawn
on the beam and its end against the support.

A force the path cannot carry (an axial force on a shear connection) adds the element
"connection" in role "axial", whose one limit state, the load path, is unmodelled: the
deck reports it UNKNOWN rather than passing a connection whose axial path nobody checked.
So does a flange force at a member end free to twist about its axis, whose J10.7
stiffeners the deck does not draw.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .lower import Bolts, Conn

EDGES = ("edge_min", "edge_max", "hole_use")
SHEAR_PLY = ("shear_yield", "shear_rupture", "block_shear", *EDGES)

ROLE_LIMITS: Mapping[str, tuple[str, ...]] = {
    # a beam web the bolts bear on; uncoped, its top bolt cannot tear out through the flange.
    # Every beam web owes beam_fit: the parts on it, and its end against the support.
    "web": ("shear_yield", "shear_rupture", *EDGES, "beam_fit"),
    "coped_web": ("shear_yield", "shear_rupture", "block_shear", *EDGES, "beam_fit"),
    "welded_web": ("shear_yield", "beam_fit"),
    "cope": ("cope_buckling",),
    # a connecting element with bolt holes, loaded in shear
    "ply": SHEAR_PLY,
    # one whose bolt line sits away from its support, so it also bends
    "bent_ply": (*SHEAR_PLY, "flexural_yield", "flexural_rupture"),
    "conventional_plate": ("ductility",),
    "extended_plate": ("plate_buckling", "extended_ductility"),
    # a bracket plate welded to its support: no holes, so no rupture section
    "welded_bracket": ("shear_yield", "flexural_yield"),
    # a shaped bracket's sloped free edge (Manual Part 15); a rectangular one, a cantilever
    # whose free end can buckle sideways (F11)
    "shaped_bracket": ("bracket_edge",),
    "rectangular_bracket": ("plate_buckling",),
    # a seat leg under a beam end, and the beam web bearing on it
    "seat": ("seat_flexure", "shear_yield"),
    "seat_leg": EDGES,
    "bearing_web": ("web_local_yielding", "web_crippling", "beam_fit"),
    "stiffener": ("bearing", "compression"),
    # bolt groups
    "shear_bolts": ("bolts", "spacing_min", "spacing_max", "joint_type", "clearance"),
    "bracket_bolts": ("bolts", "spacing_min", "spacing_max", "joint_type"),
    "tension_bolts": ("bolt_tension", "prying", "spacing_min", "spacing_max", "joint_type", "clearance"),
    "tension_shear_bolts": ("bolts", "bolt_combined"),
    "slip_critical": ("slip",),
    "fillet": ("weld", "weld_base_metal", "fillet_size"),
    # the support's face under the bolts; its bearing and tearout are in the bolt group's check
    "face": ("hole_use",),
    # the support's face as a room: what is drawn on it must fit it (geometry.py)
    "flange_face": ("flange_fit",),
    "web_face": ("web_fit",),
    "tension_element": ("tension_yield", "tension_rupture"),
    # a hanger's flange, carrying the bolts' tension to the stem in shear
    "tension_flange": ("shear_yield", "shear_rupture", *EDGES),
    # a member flange under a concentrated force (J10)
    "j10_web_yielding": ("web_local_yielding",),
    "j10_crippling": ("web_crippling",),
    "j10_flange_bending": ("flange_local_bending",),
    "j10_compression_buckling": ("web_compression_buckling",),
    "j10_sidesway": ("web_sidesway_buckling",),
    "panel": ("panel_zone",),
    # a member end free to twist about its axis, which J10.7 stiffens; the deck draws no
    # stiffeners, so the mode is unmodelled and the verdict UNKNOWN
    "unframed_end": ("j10_stiffeners",),
    "axial": ("load_path",),
}


@dataclass(frozen=True)
class Link:
    element: str
    role: str


SHEAR_KINDS = ("shear_tab", "double_angle", "single_angle", "shear_tee", "shear_end_plate", "seated", "stiffened_seat")


def _beam_web(conn: Conn) -> tuple[Link, ...]:
    if conn.get("cope") is None:
        return (Link("beam web", "web"),)
    return (Link("beam web", "coped_web"), Link("beam web", "cope"))


def _bolts(conn: Conn, element: str, role: str) -> tuple[Link, ...]:
    bolts = conn.get("bolts")
    slip = isinstance(bolts, Bolts) and bolts.joint == "slip_critical"
    return (Link(element, role),) + ((Link(element, "slip_critical"),) if slip else ())


def _shaped(conn: Conn) -> tuple[Link, ...]:
    return (Link("bracket plate", "shaped_bracket" if conn.get("free_edge") is not None else "rectangular_bracket"),)


def _face(conn: Conn) -> Link:
    return Link(f"support {conn.attrs['support'].face}", "face")


def path(conn: Conn, fields: set[str]) -> tuple[Link, ...]:
    """The chain of elements from the supported member to the support, in order."""
    kind = conn.kind
    bolted_support = conn.get("support_side") == "bolted"
    links: tuple[Link, ...]
    if kind == "shear_tab":
        form = conn.get("form")
        links = (*_beam_web(conn), *_bolts(conn, "beam side", "shear_bolts"), Link("plate", "bent_ply"),
                 Link("plate", f"{form}_plate"), Link("plate to support", "fillet"))
    elif kind in ("double_angle", "single_angle"):
        key = "angles" if kind == "double_angle" else "angle"
        links = (*_beam_web(conn), *_bolts(conn, "beam side", "shear_bolts"), Link(key, "ply"))
        if bolted_support:
            # One angle's support leg bends under the eccentric reaction; two share it symmetrically.
            outstanding = "ply" if kind == "double_angle" else "bent_ply"
            links += (Link(f"{key} outstanding", outstanding), *_bolts(conn, "support side", "shear_bolts"), _face(conn))
        else:
            links += (Link(f"{key} to support", "fillet"),)
    elif kind == "shear_tee":
        links = (*_beam_web(conn), *_bolts(conn, "beam side", "shear_bolts"), Link("tee stem", "bent_ply"))
        if bolted_support:
            links += (Link("tee flange", "ply"), *_bolts(conn, "support side", "shear_bolts"), _face(conn))
        else:
            links += (Link("tee flange to support", "fillet"),)
    elif kind == "shear_end_plate":
        cope = (Link("beam web", "cope"),) if conn.get("cope") is not None else ()
        links = (Link("beam web", "welded_web"), *cope, Link("end plate to beam web", "fillet"), Link("end plate", "ply"),
                 *_bolts(conn, "support side", "shear_bolts"), _face(conn))
    elif kind == "seated":
        links = (Link("beam web", "bearing_web"), Link("seat angle", "seat"))
        if bolted_support:
            links += (Link("seat angle", "seat_leg"), *_bolts(conn, "seat to support", "shear_bolts"), _face(conn))
        else:
            links += (Link("seat to support", "fillet"),)
    elif kind == "stiffened_seat":
        links = (Link("beam web", "bearing_web"), Link("stiffener", "stiffener"), Link("stiffener to support", "fillet"))
    elif kind == "flange_force":
        links = (Link("member web", "j10_web_yielding"),)
        if conn.attrs["force_kind"] == "tensile":
            links += (Link("member flange", "j10_flange_bending"),)
        else:
            links += (Link("member web", "j10_crippling"),)
            if conn.get("pair") == "double":
                links += (Link("member web", "j10_compression_buckling"),)
            elif "flange_restrained" in conn.attrs and "unbraced_length" in conn.attrs:
                links += (Link("member web", "j10_sidesway"),)
        # Whatever loads the design declares, a flange force may be one flange of a moment
        # connection's couple, which shears the panel zone (J10.6); build.NEEDS says what
        # its check reads that the force alone does not give.
        links += (Link("member web", "panel"),)
        if conn.attrs["location"] == "end" and conn.get("end_twist") == "free":
            links += (Link("member end", "unframed_end"),)
    elif kind == "bolt_bracket":
        links = (Link("bracket plate", "bent_ply"), *_shaped(conn), *_bolts(conn, "bracket bolts", "bracket_bolts"), _face(conn))
    elif kind == "weld_bracket":
        links = (Link("bracket plate", "welded_bracket"), *_shaped(conn), Link("bracket weld", "fillet"))
    elif kind == "hanger":
        links = (Link("tee stem", "tension_element"), Link("tee flange", "tension_flange"),
                 Link("hanger bolts", "tension_bolts"))
        if "shear" in fields:
            links += _bolts(conn, "hanger bolts", "tension_shear_bolts")
        links += (_face(conn),)
    else:
        raise ValueError(f"no load path for kind {kind}")
    support = conn.attrs.get("support")
    if support is not None:
        links += (Link(f"support {support.face}", f"{support.face}_face"),)
    if kind in SHEAR_KINDS and "axial" in fields:
        links += (Link("connection", "axial"),)
    return links
