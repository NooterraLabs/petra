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
V12 = "In v1.2, with the Chapter K HSS connections (docs/steel_connections.md §3)."

TABLE: tuple[Provision, ...] = (
    Provision("J1.1", "Design Basis", "rule", note="Every check is phi Rn (LRFD) or Rn / Omega (ASD), by the design's "
              "basis. The factors are registry constants of the clause that sets them (`checks.Ctx.available`)."),
    Provision("J1.2", "Simple Connections", "check", ("ductility", "extended_ductility"),
              "Rotation capacity of single plates. The other shear connections are flexible by their Manual "
              "configuration, which is a premise of each kind."),
    Provision("J1.3", "Moment Connections", "excluded", note=f"FR moment connections are in {V11}."),
    Provision("J1.4", "Compression Members with Bearing Joints", "excluded", note=f"Column splices are in {V11}."),
    Provision("J1.5", "Splices in Heavy Sections", "excluded", note=f"Groove-welded splices are in {V11}."),
    Provision("J1.6", "Weld Access Holes", "premise", ("cope_buckling",),
              "The catalogue has no weld access holes. A cope's reentrant corners are cut to the J1.6 radius, as the "
              "cope-buckling model states."),
    Provision("J1.7", "Placement of Welds and Bolts", "premise",
              note="v1.0 has no axially loaded members that end in a connection. A hanger's bolts are symmetric about "
              "its stem by the kind's geometry."),
    Provision("J1.8", "Bolts in Combination with Welds", "rule",
              note="Each side of a connection (`support_side`, `beam_side`) is bolted or welded, never both, so bolts "
              "and welds share no load."),
    Provision("J1.9", "Welded Alterations to Structures with Existing Rivets or Bolts", "excluded",
              note="Existing structures are out of scope (docs/steel_connections.md §4)."),
    Provision("J1.10", "High-Strength Bolts in Combination with Existing Rivets", "excluded",
              note="Existing structures and rivets are out of scope (docs/steel_connections.md §4)."),
    Provision("J2.1", "Groove Welds", "excluded", note=f"v1.0 has no groove welds. CJP flange welds are in {V11}."),
    Provision("J2.2a", "Fillet Welds: Effective Area", "check", ("weld",),
              "The effective throat of an equal-leg fillet, 0.707 w."),
    Provision("J2.2b", "Fillet Welds: Limitations", "check", ("fillet_size", "weld"),
              "Minimum size (Table J2.4), length at least 4 w, and maximum size along a lapped part's edge. Welds are "
              "continuous, with no intermittent fillets. A lapped bracket's lap is its weld return. Item (d), the "
              "end-loaded length of Eq J2-1, applies to a seat stiffener's welds, because the reaction loads them from "
              "their end, as at a bearing stiffener. Commentary J2.2b counts the welds of beam web angles and shear "
              "plates as not end-loaded. A seat angle's welds run along a leg of at most 12 in (the Shapes Database's "
              "longest), with a fillet of at least Table J2.4's least size, 1/8 in, so they never pass 100 w. A "
              "smaller fillet fails `fillet_size`."),
    Provision("J2.3", "Plug and Slot Welds", "excluded", note="The v1.0 catalogue uses no plug or slot welds."),
    Provision("J2.4", "Strength", "check", ("weld", "weld_base_metal"),
              "Eq J2-4 with kds = 1. The directional increase of Eq J2-5 and the group rule of Eq J2-6 are "
              "permitted, not required. The deck does not take them, and leaving them out errs safe."),
    Provision("J2.5", "Combination of Welds", "excluded",
              note="v1.0's welded joints are fillet welds only. No joint combines weld types."),
    Provision("J2.6", "Filler Metal Requirements", "premise", ("weld",),
              "Matching filler metal (Table J2.5), as the weld model states."),
    Provision("J2.7", "Mixed Weld Metal", "premise", ("weld",),
              "One electrode per joint, as declared. No notch-toughness requirement applies to v1.0's statically "
              "loaded shear connections."),
    Provision("J3.1", "Common Bolts", "rule", note="A307 bolts are installed snug-tight. `lower.py` rejects any other "
              "joint type."),
    Provision("J3.2", "High-Strength Bolts", "check", ("joint_type",),
              "Bolt groups and their strengths are registry rows (Tables J3.1 and J3.2). Pretension is checked where "
              "the joint's use requires it."),
    Provision("J3.3", "Size and Use of Holes", "check", ("hole_use",), "Hole dimensions are registry rows (Table J3.3)."),
    Provision("J3.4", "Minimum Spacing", "check", ("spacing_min",)),
    Provision("J3.5", "Minimum Edge Distance", "check", ("edge_min",),
              "The Table J3.5 increment for oversized and slotted holes is an unchecked premise of the model."),
    Provision("J3.6", "Maximum Spacing and Edge Distance", "check", ("spacing_max", "edge_max")),
    Provision("J3.7", "Tensile and Shear Strength of Bolts and Threaded Parts", "check",
              ("bolts", "bolt_tension", "prying"), "Prying uses the Manual Part 9 T-stub model."),
    Provision("J3.8", "Combined Tension and Shear in Bearing-Type Connections", "check", ("bolt_combined",)),
    Provision("J3.9", "High-Strength Bolts in Slip-Critical Connections", "check", ("slip", "bolts", "bolt_combined"),
              "The faying-surface class is a premise of the slip model. Slip-critical joints are also checked for "
              "the bearing-type limit states."),
    Provision("J3.10", "Combined Tension and Shear in Slip-Critical Connections", "check", ("slip",),
              "ksc of Eqs J3-5a and J3-5b."),
    Provision("J3.11a", "Bearing and Tearout: Snug-Tightened or Pretensioned High-Strength Bolted Connections",
              "check", ("bolts",), "Per hole, the least of shear, bearing and tearout per bolt."),
    Provision("J3.11b", "Bearing and Tearout: Bolts or Rods Through an Unstiffened Box Member or HSS", "excluded",
              note=V12),
    Provision("J3.12", "Special Fasteners", "excluded",
              note="Special fasteners are out of scope in v1 (docs/steel_connections.md §4)."),
    Provision("J3.13", "Wall Strength at Tension Fasteners", "excluded", note=V12),
    Provision("J4.1", "Strength of Elements in Tension", "check", ("tension_yield", "tension_rupture")),
    Provision("J4.2", "Strength of Elements in Shear", "check", ("shear_yield", "shear_rupture")),
    Provision("J4.3", "Block Shear Strength", "check", ("block_shear",), "Every enumerated block of the hole pattern."),
    Provision("J4.4", "Strength of Elements in Compression", "check", ("compression", "bracket_edge"),
              "The checked elements are a seat stiffener and a shaped bracket's free edge. The free edge takes J4.4's "
              "factors with the Manual's Q."),
    Provision("J4.5", "Strength of Elements in Flexure", "check",
              ("flexural_yield", "flexural_rupture", "cope_buckling", "plate_buckling", "seat_flexure", "bracket_edge"),
              "The checked elements are connecting plates, coped webs (Manual Part 9), extended plates and "
              "rectangular bracket plates (F11), seats, and bracket edges (Part 15)."),
    Provision("J5.1", "Fillers in Welded Connections", "excluded", note="v1.0's welded joints have no fillers."),
    Provision("J5.2", "Fillers in Bolted Bearing-Type Connections", "check", ("bolts", "bolt_combined"),
              "A declared filler applies J5.2(a)'s least factor, 0.85, to the bolts' shear strength, because the "
              "grammar gives no filler thickness. The factor applies in slip-critical joints' bearing checks too. An "
              "undeclared filler is taken to be absent."),
    Provision("J6", "Splices", "excluded", note=f"Beam and column splices are in {V11}."),
    Provision("J7", "Bearing Strength", "check", ("bearing",),
              "A stiffened seat's fitted stiffener edge and the seat plate on it, each surface at its own Fy."),
    Provision("J8", "Column Bases and Bearing on Concrete", "excluded", note=f"Base plates are in {V11}."),
    Provision("J9", "Anchor Rods and Embedments", "excluded", note=f"Anchor rods are in {V11}."),
    Provision("J10.1", "Flange Local Bending", "check", ("flange_local_bending",),
              "The deck does not take the exemption for a load narrower than 0.15 bf across the flange, because the "
              "design declares no such width."),
    Provision("J10.2", "Web Local Yielding", "check", ("web_local_yielding",)),
    Provision("J10.3", "Web Local Crippling", "check", ("web_crippling",)),
    Provision("J10.4", "Web Sidesway Buckling", "check", ("web_sidesway_buckling",)),
    Provision("J10.5", "Web Compression Buckling", "check", ("web_compression_buckling",)),
    Provision("J10.6", "Web Panel-Zone Shear", "check", ("panel_zone",)),
    Provision("J10.7", "Unframed Ends of Beams and Girders", "check", ("j10_stiffeners",),
              "A flange force at a member end states whether the end is restrained against twisting about its axis "
              "(`end_twist`). A free end requires the unmodelled `j10_stiffeners` mode, because the deck draws no "
              "stiffeners, so the result is UNKNOWN. A framed connection frames its beam's end, and a seat's top "
              "angle restrains the beam's end."),
    Provision("J10.8", "Additional Stiffener Requirements for Concentrated Forces", "rule",
              note="A J10 force beyond the unstiffened strength fails its check. The deck designs no stiffeners "
              "(`j10_stiffeners` is unmodelled), so it rejects a stiffened design and never passes one."),
    Provision("J10.9", "Additional Doubler Plate Requirements for Concentrated Forces", "rule",
              note="As for J10.8, panel-zone shear beyond the unreinforced web's strength fails. The deck does not "
              "model doublers."),
    Provision("J10.10", "Transverse Forces on Plate Elements", "check", ("prying",),
              "A hanger's tee flange and the support flange under the same bolts, each checked by the prying model."),
    Provision("K1", "General Provisions and Parameters for HSS Connections", "excluded", note=V12),
    Provision("K2", "Concentrated Forces on HSS", "excluded", note=V12),
    Provision("K3", "HSS-to-HSS Truss Connections", "excluded", note=V12),
    Provision("K4", "HSS-to-HSS Moment Connections", "excluded", note=V12),
    Provision("K5", "Welds of Plates and Branches to HSS", "excluded", note=V12),
)
"""Every Chapter J and K provision of AISC 360-22, in SPEC_SECTIONS order."""

OTHER: tuple[Provision, ...] = (
    Provision("RCSC 4", "Joint types and installation", "check", ("joint_type",),
              "Joints are at least snug-tight. Group 150 and 200 bolts in tension are pretensioned. J3.3 sets the "
              "holes that need a slip-critical joint (`hole_use`)."),
    Provision("Manual Part 1", "Dimensions and properties: the flat web T = d - 2 kdes", "check", ("beam_fit", "web_fit"),
              "A part, weld or bolt hole on a beam's or a column's web lies on the web's flat, between the fillets "
              "that kdes bounds. A part on a fillet does not fit (`geometry.py`)."),
    Provision("Manual Part 7", "Entering and tightening clearances", "check", ("clearance",),
              "The socket allowance is a judged registry row."),
    Provision("Manual Part 9", "Coped beams, prying action and shear tee ductility", "check",
              ("cope_buckling", "prying", "tee_ductility"),
              "Prying uses the T-stub model, with each bolt's tributary length from Figure 9-4. A shear tee's "
              "rotational ductility uses Eqs 9-51 and 9-52, or the alternate Eq 9-53, as Companion II.A-30 and "
              "II.A-31 apply them."),
    Provision("Manual Part 10", "Single-plate, seated and tee connections", "check",
              ("ductility", "extended_ductility", "plate_buckling", "seat_flexure", "compression", "flexural_yield"),
              "A seat stiffener's width-to-thickness limit is checked with its compression. An extended plate's "
              "shear and flexural yielding interaction (Eq 10-8) is checked with its flexural yielding. In the "
              "strength checks (`block_shear`, `seat_flexure`, `web_local_yielding`, `web_crippling`, `weld`), the "
              "1/4 in beam underrun comes off a beam web's end distance and is added to a seat's setback, as the "
              "Companion takes it."),
    Provision("Manual Part 15", "Bracket plates", "check", ("bracket_edge",)),
    Provision("Shop deck", "Stock plate thicknesses and bolt lengths", "rule",
              note="A fixed plate thickness must be stocked (registry `shop_deck.plate.*`), and lowering checks it. "
              "Bolt lengths are an unchecked premise of the clearance model."),
    Provision("Geometry", "Fit of the drawn parts", "check", ("beam_fit", "flange_fit", "web_fit"),
              "`geometry.py` places the parts that each kind's lines draw in one frame per connection. The beam end "
              "clears the support and lands on a seat, holes and welds lie on the support's flange and clear its "
              "web, a seat's holes lie on its leg, and a beam's flange passes between a column's flanges. Positions "
              "the lines leave open are taken where they fit best."),
    Provision("Connection kinds", "Force components without a checked path", "check", ("load_path",),
              "An axial force on a v1.0 shear connection requires the unmodelled `load_path` mode, so the result is "
              "UNKNOWN."),
)


def render() -> str:
    """docs/steel_traceability.md."""
    lines = [
        "# Clause traceability of the steel deck",
        "",
        "`python -m petra.models.steel.trace` generates this file from `petra/models/steel/trace.py`. "
        "`tests/test_steel_trace.py` fails when this file is stale or a provision is unmapped.",
        "",
        "Each row gives its provision one treatment:",
        "",
        "- **check** means the checks of the modes in the row encode the provision.",
        "- **rule** means the deck enforces the provision where it reads the design or factors the strength.",
        "- **premise** means the deck states the provision as an assumption and does not check it.",
        "- **excluded** means the provision is outside v1.0.",
        "",
        "| Provision | Title | Treatment | Modes | Note |",
        "|---|---|---|---|---|",
    ]
    for p in (*TABLE, *OTHER):
        modes = ", ".join(f"`{m}`" for m in p.modes)
        lines.append(f"| {p.section} | {p.title} | {p.treatment} | {modes} | {p.note} |")
    counts = {t: sum(1 for p in TABLE if p.treatment == t) for t in TREATMENTS}
    lines += ["", f"The table maps {len(TABLE)} provisions of AISC 360-22 Chapters J and K: "
              + ", ".join(f"{n} {t}" for t, n in counts.items()) + "."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import pathlib

    target = pathlib.Path(__file__).resolve().parents[3] / "docs" / "steel_traceability.md"
    target.write_text(render(), encoding="utf-8", newline="\n")
    print(f"wrote {target}")
