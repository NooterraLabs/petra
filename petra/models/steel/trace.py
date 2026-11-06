"""Clause traceability of the steel deck (docs/steel_connections.md §6). Tooling.

Every provision of AISC 360-22 Chapters J and K, as the Specification's table of contents
numbers them, maps to exactly one treatment:

  check     the modes (vocab.MODES short names) whose checks encode it;
  rule      enforced where the design is read or the strength is factored (lower.py's
            consistency checks, the registry's tables, the design basis);
  premise   a stated assumption the deck does not check, with the model statement or
            document that carries it;
  excluded  outside v1.0, with its reason and release; a design that needs it is
            rejected at lowering or its requirement stays UNKNOWN.

Provisions from outside the Specification that the deck also encodes (RCSC installation,
the Manual's tightening clearances, the shop deck's stock) close the table. The test
tests/test_steel_trace.py fails when a provision is unmapped, mapped twice, or names a mode
the deck does not have, when a mode of the deck is not named by any provision, and when
docs/steel_traceability.md is not the table rendered.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Provision:
    section: str          # "J3.4", "J2.2b", "K1", "RCSC 4.2"
    title: str
    treatment: str        # check | rule | premise | excluded
    modes: tuple[str, ...] = ()
    note: str = ""


TREATMENTS = ("check", "rule", "premise", "excluded")

SPEC_SECTIONS: tuple[tuple[str, str], ...] = (
    ("J1.1", "Design Basis"), ("J1.2", "Simple Connections"), ("J1.3", "Moment Connections"),
    ("J1.4", "Compression Members with Bearing Joints"), ("J1.5", "Splices in Heavy Sections"),
    ("J1.6", "Weld Access Holes"), ("J1.7", "Placement of Welds and Bolts"),
    ("J1.8", "Bolts in Combination with Welds"),
    ("J1.9", "Welded Alterations to Structures with Existing Rivets or Bolts"),
    ("J1.10", "High-Strength Bolts in Combination with Existing Rivets"),
    ("J2.1", "Groove Welds"), ("J2.2a", "Fillet Welds: Effective Area"), ("J2.2b", "Fillet Welds: Limitations"),
    ("J2.3", "Plug and Slot Welds"), ("J2.4", "Strength"), ("J2.5", "Combination of Welds"),
    ("J2.6", "Filler Metal Requirements"), ("J2.7", "Mixed Weld Metal"),
    ("J3.1", "Common Bolts"), ("J3.2", "High-Strength Bolts"), ("J3.3", "Size and Use of Holes"),
    ("J3.4", "Minimum Spacing"), ("J3.5", "Minimum Edge Distance"), ("J3.6", "Maximum Spacing and Edge Distance"),
    ("J3.7", "Tensile and Shear Strength of Bolts and Threaded Parts"),
    ("J3.8", "Combined Tension and Shear in Bearing-Type Connections"),
    ("J3.9", "High-Strength Bolts in Slip-Critical Connections"),
    ("J3.10", "Combined Tension and Shear in Slip-Critical Connections"),
    ("J3.11a", "Bearing and Tearout: Snug-Tightened or Pretensioned High-Strength Bolted Connections"),
    ("J3.11b", "Bearing and Tearout: Bolts or Rods Through an Unstiffened Box Member or HSS"),
    ("J3.12", "Special Fasteners"), ("J3.13", "Wall Strength at Tension Fasteners"),
    ("J4.1", "Strength of Elements in Tension"), ("J4.2", "Strength of Elements in Shear"),
    ("J4.3", "Block Shear Strength"), ("J4.4", "Strength of Elements in Compression"),
    ("J4.5", "Strength of Elements in Flexure"),
    ("J5.1", "Fillers in Welded Connections"), ("J5.2", "Fillers in Bolted Bearing-Type Connections"),
    ("J6", "Splices"), ("J7", "Bearing Strength"), ("J8", "Column Bases and Bearing on Concrete"),
    ("J9", "Anchor Rods and Embedments"),
    ("J10.1", "Flange Local Bending"), ("J10.2", "Web Local Yielding"), ("J10.3", "Web Local Crippling"),
    ("J10.4", "Web Sidesway Buckling"), ("J10.5", "Web Compression Buckling"), ("J10.6", "Web Panel-Zone Shear"),
    ("J10.7", "Unframed Ends of Beams and Girders"),
    ("J10.8", "Additional Stiffener Requirements for Concentrated Forces"),
    ("J10.9", "Additional Doubler Plate Requirements for Concentrated Forces"),
    ("J10.10", "Transverse Forces on Plate Elements"),
    ("K1", "General Provisions and Parameters for HSS Connections"), ("K2", "Concentrated Forces on HSS"),
    ("K3", "HSS-to-HSS Truss Connections"), ("K4", "HSS-to-HSS Moment Connections"),
    ("K5", "Welds of Plates and Branches to HSS"),
)
"""AISC 360-22's Chapter J and K provisions, by its table of contents."""

V11 = "v1.1 (docs/steel_connections.md §3)"
V12 = "v1.2, Chapter K HSS connections (docs/steel_connections.md §3)"

TABLE: tuple[Provision, ...] = (
    Provision("J1.1", "Design Basis", "rule", note="every check is phi Rn (LRFD) or Rn / Omega (ASD) by the design's "
              "basis, the factors registry constants of the clause that sets them (checks.Ctx.available)"),
    Provision("J1.2", "Simple Connections", "check", ("ductility", "extended_ductility"),
              "rotation capacity of single plates; the other shear connections are flexible by their Manual "
              "configuration, a premise of each kind"),
    Provision("J1.3", "Moment Connections", "excluded", note=f"FR moment connections are {V11}"),
    Provision("J1.4", "Compression Members with Bearing Joints", "excluded", note=f"column splices are {V11}"),
    Provision("J1.5", "Splices in Heavy Sections", "excluded", note=f"groove-welded splices are {V11}"),
    Provision("J1.6", "Weld Access Holes", "premise", ("cope_buckling",),
              "the catalogue has no weld access holes; a cope's reentrant corners are cut to the J1.6 radius, stated "
              "in the cope-buckling model"),
    Provision("J1.7", "Placement of Welds and Bolts", "premise",
              note="v1.0 has no axially loaded members ending in a connection; a hanger's bolts are symmetric about "
              "its stem by the kind's geometry"),
    Provision("J1.8", "Bolts in Combination with Welds", "rule",
              note="each side of a connection is bolted or welded (support_side, beam_side), never both, so no load is "
              "shared between bolts and welds"),
    Provision("J1.9", "Welded Alterations to Structures with Existing Rivets or Bolts", "excluded",
              note="existing structures are out of scope (§4)"),
    Provision("J1.10", "High-Strength Bolts in Combination with Existing Rivets", "excluded",
              note="existing structures and rivets are out of scope (§4)"),
    Provision("J2.1", "Groove Welds", "excluded", note=f"no groove welds in v1.0; CJP flange welds are {V11}"),
    Provision("J2.2a", "Fillet Welds: Effective Area", "check", ("weld",),
              "effective throat 0.707 w of an equal-leg fillet"),
    Provision("J2.2b", "Fillet Welds: Limitations", "check", ("fillet_size", "weld"),
              "minimum size (Table J2.4), length at least 4 w, maximum along a lapped part's edge; welds are "
              "continuous (no intermittent fillets); a lapped bracket's lap is its weld return; (d) the end-loaded "
              "length of Eq J2-1 for a seat stiffener's welds, which the reaction loads from their end as at a bearing "
              "stiffener; Commentary J2.2b counts the welds of beam web angles and shear plates as not end-loaded, and "
              "a seat angle's welds, along a leg of at most 12 in (the Shapes Database's longest) with a fillet of at "
              "least Table J2.4's least size, 1/8 in, never pass 100 w; a smaller fillet fails fillet_size"),
    Provision("J2.3", "Plug and Slot Welds", "excluded", note="not used by the v1.0 catalogue"),
    Provision("J2.4", "Strength", "check", ("weld", "weld_base_metal"),
              "Eq J2-4 with kds = 1: the directional increase of Eq J2-5 and the group rule of Eq J2-6 are "
              "permitted, not required, and not taken, which errs safe"),
    Provision("J2.5", "Combination of Welds", "excluded",
              note="v1.0's welded joints are fillet welds only; no joint combines weld types"),
    Provision("J2.6", "Filler Metal Requirements", "premise", ("weld",),
              "matching filler metal (Table J2.5), stated in the weld model"),
    Provision("J2.7", "Mixed Weld Metal", "premise", ("weld",),
              "one electrode per joint as declared; no notch-toughness requirement applies to v1.0's statically "
              "loaded shear connections"),
    Provision("J3.1", "Common Bolts", "rule", note="A307 bolts are installed snug-tight (lower.py rejects another "
              "joint type)"),
    Provision("J3.2", "High-Strength Bolts", "check", ("joint_type",),
              "bolt groups and their strengths are registry rows (Tables J3.1, J3.2); pretension where the joint's "
              "use requires it"),
    Provision("J3.3", "Size and Use of Holes", "check", ("hole_use",), "hole dimensions are registry rows (Table J3.3)"),
    Provision("J3.4", "Minimum Spacing", "check", ("spacing_min",)),
    Provision("J3.5", "Minimum Edge Distance", "check", ("edge_min",),
              "the Table J3.5 increment for oversized and slotted holes is an unchecked premise of the model"),
    Provision("J3.6", "Maximum Spacing and Edge Distance", "check", ("spacing_max", "edge_max")),
    Provision("J3.7", "Tensile and Shear Strength of Bolts and Threaded Parts", "check",
              ("bolts", "bolt_tension", "prying"), "prying by the Manual Part 9 T-stub model"),
    Provision("J3.8", "Combined Tension and Shear in Bearing-Type Connections", "check", ("bolt_combined",)),
    Provision("J3.9", "High-Strength Bolts in Slip-Critical Connections", "check", ("slip", "bolts", "bolt_combined"),
              "the faying-surface class is a premise of the slip model; slip-critical joints are checked for the "
              "bearing-type limit states too"),
    Provision("J3.10", "Combined Tension and Shear in Slip-Critical Connections", "check", ("slip",),
              "ksc of Eqs J3-5a/b"),
    Provision("J3.11a", "Bearing and Tearout: Snug-Tightened or Pretensioned High-Strength Bolted Connections",
              "check", ("bolts",), "per hole, the least of shear, bearing and tearout per bolt"),
    Provision("J3.11b", "Bearing and Tearout: Bolts or Rods Through an Unstiffened Box Member or HSS", "excluded",
              note=V12),
    Provision("J3.12", "Special Fasteners", "excluded", note="special fasteners are out of scope in v1 (§4)"),
    Provision("J3.13", "Wall Strength at Tension Fasteners", "excluded", note=V12),
    Provision("J4.1", "Strength of Elements in Tension", "check", ("tension_yield", "tension_rupture")),
    Provision("J4.2", "Strength of Elements in Shear", "check", ("shear_yield", "shear_rupture")),
    Provision("J4.3", "Block Shear Strength", "check", ("block_shear",), "every enumerated block of the hole pattern"),
    Provision("J4.4", "Strength of Elements in Compression", "check", ("compression", "bracket_edge"),
              "a seat stiffener; a shaped bracket's free edge takes J4.4's factors with the Manual's Q"),
    Provision("J4.5", "Strength of Elements in Flexure", "check",
              ("flexural_yield", "flexural_rupture", "cope_buckling", "plate_buckling", "seat_flexure", "bracket_edge"),
              "connecting plates, coped webs (Manual Part 9), extended plates and rectangular bracket plates (F11), "
              "seats, bracket edges (Part 15)"),
    Provision("J5.1", "Fillers in Welded Connections", "excluded", note="no fillers in v1.0's welded joints"),
    Provision("J5.2", "Fillers in Bolted Bearing-Type Connections", "check", ("bolts", "bolt_combined"),
              "a declared filler takes (a)'s least factor, 0.85, on the bolts' shear strength (the grammar gives no "
              "thickness), in slip-critical joints' bearing checks too; an undeclared filler is taken to be absent"),
    Provision("J6", "Splices", "excluded", note=f"beam and column splices are {V11}"),
    Provision("J7", "Bearing Strength", "check", ("bearing",), "a stiffened seat's stiffener on the beam flange"),
    Provision("J8", "Column Bases and Bearing on Concrete", "excluded", note=f"base plates are {V11}"),
    Provision("J9", "Anchor Rods and Embedments", "excluded", note=f"anchor rods are {V11}"),
    Provision("J10.1", "Flange Local Bending", "check", ("flange_local_bending",),
              "the exemption for a load narrower than 0.15 bf across the flange is not taken (no such width is "
              "declared)"),
    Provision("J10.2", "Web Local Yielding", "check", ("web_local_yielding",)),
    Provision("J10.3", "Web Local Crippling", "check", ("web_crippling",)),
    Provision("J10.4", "Web Sidesway Buckling", "check", ("web_sidesway_buckling",)),
    Provision("J10.5", "Web Compression Buckling", "check", ("web_compression_buckling",)),
    Provision("J10.6", "Web Panel-Zone Shear", "check", ("panel_zone",)),
    Provision("J10.7", "Unframed Ends of Beams and Girders", "premise",
              note="a member end under a concentrated force is framed or restrained against rotation about its axis; "
              "the deck has no inputs for end stiffeners (j10_stiffeners is unmodelled)"),
    Provision("J10.8", "Additional Stiffener Requirements for Concentrated Forces", "rule",
              note="a J10 force beyond the unstiffened strength fails its check; the deck designs no stiffeners "
              "(j10_stiffeners, unmodelled), so a stiffened design is rejected, never passed"),
    Provision("J10.9", "Additional Doubler Plate Requirements for Concentrated Forces", "rule",
              note="as J10.8: panel-zone shear beyond the unreinforced web fails; doublers are not modelled"),
    Provision("J10.10", "Transverse Forces on Plate Elements", "check", ("prying",),
              "a hanger's tee flange and the support flange under the same bolts, each by the prying model"),
    Provision("K1", "General Provisions and Parameters for HSS Connections", "excluded", note=V12),
    Provision("K2", "Concentrated Forces on HSS", "excluded", note=V12),
    Provision("K3", "HSS-to-HSS Truss Connections", "excluded", note=V12),
    Provision("K4", "HSS-to-HSS Moment Connections", "excluded", note=V12),
    Provision("K5", "Welds of Plates and Branches to HSS", "excluded", note=V12),
)
"""Every Chapter J and K provision of AISC 360-22, in SPEC_SECTIONS order."""

OTHER: tuple[Provision, ...] = (
    Provision("RCSC 4", "Joint types and installation", "check", ("joint_type",),
              "at least snug-tight; Group 150 and 200 bolts in tension pretensioned; the holes that need a "
              "slip-critical joint are J3.3's (hole_use)"),
    Provision("Manual Part 7", "Entering and tightening clearances", "check", ("clearance",),
              "the socket allowance is a judged registry row"),
    Provision("Manual Part 9", "Coped beams and prying action", "check", ("cope_buckling", "prying"),
              "prying by the T-stub model with each bolt's tributary length by Figure 9-4"),
    Provision("Manual Part 10", "Single-plate, seated and tee connections", "check",
              ("ductility", "extended_ductility", "plate_buckling", "seat_flexure", "compression", "flexural_yield"),
              "a seat stiffener's width-to-thickness limit is checked with its compression; an extended plate's "
              "shear and flexural yielding interaction (Eq 10-8) with its flexural yielding; the 1/4 in beam underrun "
              "comes off a beam web's end distance and onto a seat's setback in the strength checks (block_shear, "
              "seat_flexure, web_local_yielding, web_crippling, weld), as the Companion takes it"),
    Provision("Manual Part 15", "Bracket plates", "check", ("bracket_edge",)),
    Provision("Shop deck", "Stock plate thicknesses and bolt lengths", "rule",
              note="a fixed plate thickness must be stocked (registry shop_deck.plate.*), checked at lowering; bolt "
              "lengths are an unchecked premise of the clearance model"),
    Provision("Connection kinds", "Force components without a checked path", "check", ("load_path",),
              "an axial force on a v1.0 shear connection requires the unmodelled load-path mode: UNKNOWN"),
)


def render() -> str:
    """docs/steel_traceability.md."""
    lines = [
        "# Steel deck: clause traceability",
        "",
        "Generated from `petra/models/steel/trace.py` by `python -m petra.models.steel.trace`; "
        "`tests/test_steel_trace.py` fails when this file is stale or a provision is unmapped.",
        "",
        "Treatments: **check** (the modes whose checks encode it), **rule** (enforced where the design is read "
        "or factored), **premise** (stated, not checked), **excluded** (outside v1.0).",
        "",
        "| Provision | Title | Treatment | Modes | Note |",
        "|---|---|---|---|---|",
    ]
    for p in (*TABLE, *OTHER):
        modes = ", ".join(f"`{m}`" for m in p.modes)
        lines.append(f"| {p.section} | {p.title} | {p.treatment} | {modes} | {p.note} |")
    counts = {t: sum(1 for p in TABLE if p.treatment == t) for t in TREATMENTS}
    lines += ["", f"AISC 360-22 Chapters J and K: {len(TABLE)} provisions, "
              + ", ".join(f"{n} {t}" for t, n in counts.items()) + "."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import pathlib

    target = pathlib.Path(__file__).resolve().parents[3] / "docs" / "steel_traceability.md"
    target.write_text(render(), encoding="utf-8", newline="\n")
    print(f"wrote {target}")
