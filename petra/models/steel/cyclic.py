"""Which fatigue checks (AISC 360-22 Appendix 3) a connection owes. Trusted.

A load case that names `cycles` on a connection (lower.CYCLES) is cyclic. Its other loads
on the connection are the cyclic load: each varies inside its interval, so the interval's
width is its range and its larger magnitude its peak. Coverage then demands the fatigue
mode of every detail on the connection's load path (path.py), by the role each element
plays there:

  bolts in shear       the connected material at the holes, category B (Table A-3.1 Cases
                       2.1 and 2.2): fatigue_bolted. Snug-tight bolts owe none: a joint under
                       a cyclic load is pretensioned (J3.2, RCSC 4.2), which joint_type
                       checks (fatigue.gen_joint_type), so a snug-tight one fails there.
  bolts in tension     the bolts' tensile stress area, category G (Case 8.5):
                       fatigue_bolt_tension.
  a fillet weld        its throat in shear, category F (Case 8.2): fatigue_weld. At the end
                       of a plate welded with a pair of fillets on opposite faces, the plate's
                       tensile stress across them, C at the toe and C'' at the root (Case
                       5.7): fatigue_weld_end.
  a beam coped at both flanges   the bottom cope's reentrant corner, E' (Case 1.3):
                       fatigue_cope.

A detail the deck draws but whose category it does not encode (a single fillet at an
angle's or a tee's toe, a seat angle, a hanger's tee, a member flange under a tensile
force) owes fatigue_detail, which is unmodelled: the verdict is UNKNOWN, never PASS. A connection with no cyclic case owes no fatigue mode, and `reasons`
says so for each.
"""
from __future__ import annotations

from typing import Mapping

from ...ir import Design
from .lower import CYCLES, Bolts, Conn, Cope, Weld
from .path import Link, path

ENCODED = ("fatigue_bolted", "fatigue_bolt_tension", "fatigue_weld", "fatigue_weld_end", "fatigue_cope")
"""The fatigue modes with checks (fatigue.GENERATORS)."""

UNENCODED = ("fatigue_detail",)
"""The fatigue mode the deck demands and cannot check: unmodelled, so UNKNOWN."""

FATIGUE = (*ENCODED, *UNENCODED)

PLATE_ENDS: Mapping[str, str] = {
    "plate to support": "plate",
    "stiffener to support": "stiffener",
    "bracket weld": "bracket plate",
}
"""Weld groups at the end of a plate set on edge against the support, by the name of the
plate's flexure (checks.Flexure): the moment it carries puts the plate's end in tension
across the welds (Case 5.7) when they are a pair, one on each face."""


def cyclic_cases(conn: Conn, design: Design) -> tuple[str, ...]:
    """The load cases that name cycles on the connection, in design order."""
    return tuple(case.name for case in design.loads.values()
                 if any(e.target == (conn.name,) and e.field == CYCLES for e in case.entries))


def _fields(conn: Conn, design: Design) -> set[str]:
    return {e.field for case in design.loads.values() for e in case.entries if e.target == (conn.name,)}


def _joint(conn: Conn) -> str | None:
    bolts = conn.get("bolts")
    return bolts.joint if isinstance(bolts, Bolts) else None


def paired(conn: Conn) -> bool:
    """The plate-end weld is a pair of fillets, one on each face, with no return."""
    weld = conn.get("weld")
    return isinstance(weld, Weld) and weld.sides == 2 and conn.get("weld_return") is None


def _link(conn: Conn, link: Link) -> tuple[str, ...]:
    """The fatigue modes one element on the path owes in its role."""
    role = link.role
    if role in ("shear_bolts", "bracket_bolts"):
        # a seat's bolted leg is the seat's detail, which fatigue_detail takes
        return () if _joint(conn) == "snug" or conn.kind == "seated" else ("fatigue_bolted",)
    if role == "tension_bolts":
        return ("fatigue_bolt_tension",)
    if role == "fillet":
        if link.element in PLATE_ENDS:
            return ("fatigue_weld", "fatigue_weld_end" if paired(conn) else "fatigue_detail")
        if link.element == "end plate to beam web":
            return ("fatigue_weld",)
        return ("fatigue_weld", "fatigue_detail")
    if role == "cope":
        cope = conn.get("cope")
        return ("fatigue_cope",) if isinstance(cope, Cope) and cope.flanges == "both" else ()
    if role in ("seat", "tension_element", "tension_flange", "j10_flange_bending"):
        return ("fatigue_detail",)
    return ()


def _details(conn: Conn, design: Design) -> tuple[str, ...]:
    """The fatigue modes of the elements on the load path, in path order, each once."""
    return tuple(dict.fromkeys(m for link in path(conn, _fields(conn, design)) for m in _link(conn, link)))


def required(conn: Conn, design: Design) -> tuple[str, ...]:
    """The fatigue modes the connection owes: its details' when a load case is cyclic,
    else none."""
    return _details(conn, design) if cyclic_cases(conn, design) else ()


# --- Why a fatigue mode is not owed ------------------------------------------------------

NOT_CYCLIC = ("no load case names cycles on the connection: Appendix 3 checks a cyclic load, which a case declares "
              "with `on <conn> cycles in [lo, hi]`")
NO_BOLTS = "no bolt is drawn on the connection"
NO_WELD = "no weld is drawn on the connection"
NO_TENSION = ("no bolt is in tension: bolts in shear have no history of fatigue failure, only the material they "
              "connect (Commentary 3.4), which fatigue_bolted checks")
SNUG = ("the bolts are snug-tight: Table A-3.1 Section 2 has categories for slip-critical and pretensioned joints only, "
        "and in a cyclic case joint_type requires the joint pretensioned (J3.2, RCSC 4.2; Commentary 3.4)")


def _bolt_reasons(conn: Conn) -> dict[str, str]:
    joint, kind = _joint(conn), conn.kind
    if joint is None:
        return {"fatigue_bolted": NO_BOLTS, "fatigue_bolt_tension": NO_BOLTS}
    out = {"fatigue_bolt_tension": NO_TENSION}
    if joint == "snug":
        out["fatigue_bolted"] = SNUG
    if kind == "seated":
        out["fatigue_bolted"] = ("the seat angle's bolted leg is part of the seat, whose detail fatigue_detail takes; the "
                                 "support's face under the bolts is the support member's")
    if kind == "hanger":
        out["fatigue_bolted"] = ("the bolts pull the tee flange out of its plane: the flange is fatigue_detail's, the "
                                 "bolts' tension fatigue_bolt_tension's")
        out.pop("fatigue_bolt_tension")
    return out


def _weld_reasons(conn: Conn) -> dict[str, str]:
    welds = {link.element for link in path(conn, set()) if link.role == "fillet"}
    if not welds:
        return {"fatigue_weld": NO_WELD, "fatigue_weld_end": NO_WELD}
    if "end plate to beam web" in welds:
        return {"fatigue_weld_end": "the fillets carry the reaction along the beam web, parallel to them: no tensile "
                                    "stress crosses them, which Case 5.7 needs; their throat is fatigue_weld's"}
    if welds & set(PLATE_ENDS):
        if conn.get("weld_return") is not None:
            return {"fatigue_weld_end": "a lapped plate's C-shaped fillet is not a pair at a plate's end (Case 5.7): "
                                        "fatigue_detail takes it"}
        if not paired(conn):
            return {"fatigue_weld_end": "the plate is welded on one face: Case 5.7 is a pair of fillets on opposite "
                                        "faces, and fatigue_detail takes the single fillet"}
        return {}
    return {"fatigue_weld_end": "the welds are single fillets at the toes of a leg or a flange, not a pair at a "
                                "plate's end (Case 5.7): fatigue_detail takes them"}


def _cope_reason(conn: Conn) -> dict[str, str]:
    cope = conn.get("cope")
    if not isinstance(cope, Cope):
        return {"fatigue_cope": "no coped beam is drawn"}
    if cope.flanges == "top":
        return {"fatigue_cope": "the top cope's reentrant corner is at the top of the web, which the beam end's moment "
                                "compresses: a stress range wholly in compression is not a fatigue case (Commentary 3.2)"}
    return {}


def _detail_reason(conn: Conn, owed: set[str]) -> dict[str, str]:
    if "fatigue_detail" in owed:
        return {}
    if conn.kind == "flange_force":
        return {"fatigue_detail": "the force is compressive: a stress range wholly in compression is not a fatigue "
                                  "case (Commentary 3.2); the part that delivers it is another connection's"}
    return {"fatigue_detail": "each detail drawn has a category the deck checks; the support's own base metal at the "
                              "connection is the support member's design (Table A-3.1 Section 7)"}


def reasons(conn: Conn, design: Design) -> dict[str, str]:
    """Why each fatigue mode the connection does not owe cannot arise for it: a mode its
    details would owe under a cyclic load is not owed because no case is cyclic; any other
    because no detail of the connection carries it."""
    details = set(_details(conn, design))
    why = {**_bolt_reasons(conn), **_weld_reasons(conn), **_cope_reason(conn), **_detail_reason(conn, details)}
    out = {m: r for m, r in why.items() if m not in details}
    if not cyclic_cases(conn, design):
        out.update({m: NOT_CYCLIC for m in details})
    return out
