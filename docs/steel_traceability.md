# Steel deck: clause traceability

Generated from `lola/models/steel/trace.py` by `python -m lola.models.steel.trace`; `tests/test_steel_trace.py` fails when this file is stale or a provision is unmapped.

Treatments: **check** (the modes whose checks encode it), **rule** (enforced where the design is read or factored), **premise** (stated, not checked), **excluded** (outside v1.0).

| Provision | Title | Treatment | Modes | Note |
|---|---|---|---|---|
| J1.1 | Design Basis | rule |  | every check is phi Rn (LRFD) or Rn / Omega (ASD) by the design's basis, the factors registry constants of the clause that sets them (checks.Ctx.available) |
| J1.2 | Simple Connections | check | `ductility`, `extended_ductility` | rotation capacity of single plates; the other shear connections are flexible by their Manual configuration, a premise of each kind |
| J1.3 | Moment Connections | excluded |  | FR moment connections are v1.1 (docs/steel_connections.md §3) |
| J1.4 | Compression Members with Bearing Joints | excluded |  | column splices are v1.1 (docs/steel_connections.md §3) |
| J1.5 | Splices in Heavy Sections | excluded |  | groove-welded splices are v1.1 (docs/steel_connections.md §3) |
| J1.6 | Weld Access Holes | premise | `cope_buckling` | the catalogue has no weld access holes; a cope's reentrant corners are cut to the J1.6 radius, stated in the cope-buckling model |
| J1.7 | Placement of Welds and Bolts | premise |  | v1.0 has no axially loaded members ending in a connection; a hanger's bolts are symmetric about its stem by the kind's geometry |
| J1.8 | Bolts in Combination with Welds | rule |  | each side of a connection is bolted or welded (support_side, beam_side), never both, so no load is shared between bolts and welds |
| J1.9 | Welded Alterations to Structures with Existing Rivets or Bolts | excluded |  | existing structures are out of scope (§4) |
| J1.10 | High-Strength Bolts in Combination with Existing Rivets | excluded |  | existing structures and rivets are out of scope (§4) |
| J2.1 | Groove Welds | excluded |  | no groove welds in v1.0; CJP flange welds are v1.1 (docs/steel_connections.md §3) |
| J2.2a | Fillet Welds: Effective Area | check | `weld` | effective throat 0.707 w of an equal-leg fillet |
| J2.2b | Fillet Welds: Limitations | check | `fillet_size`, `weld` | minimum size (Table J2.4), length at least 4 w, maximum along a lapped part's edge; welds are continuous (no intermittent fillets); a lapped bracket's lap is its weld return; (d) the end-loaded length of Eq J2-1 for a seat stiffener's welds, which the reaction loads from their end as at a bearing stiffener; Commentary J2.2b counts the welds of beam web angles and shear plates as not end-loaded, and a seat angle's welds, along a leg of at most 12 in (the Shapes Database's longest) with a fillet of at least Table J2.4's least size, 1/8 in, never pass 100 w; a smaller fillet fails fillet_size |
| J2.3 | Plug and Slot Welds | excluded |  | not used by the v1.0 catalogue |
| J2.4 | Strength | check | `weld`, `weld_base_metal` | Eq J2-4 with kds = 1: the directional increase of Eq J2-5 and the group rule of Eq J2-6 are permitted, not required, and not taken, which errs safe |
| J2.5 | Combination of Welds | excluded |  | v1.0's welded joints are fillet welds only; no joint combines weld types |
| J2.6 | Filler Metal Requirements | premise | `weld` | matching filler metal (Table J2.5), stated in the weld model |
| J2.7 | Mixed Weld Metal | premise | `weld` | one electrode per joint as declared; no notch-toughness requirement applies to v1.0's statically loaded shear connections |
| J3.1 | Common Bolts | rule |  | A307 bolts are installed snug-tight (lower.py rejects another joint type) |
| J3.2 | High-Strength Bolts | check | `joint_type` | bolt groups and their strengths are registry rows (Tables J3.1, J3.2); pretension where the joint's use requires it |
| J3.3 | Size and Use of Holes | check | `hole_use` | hole dimensions are registry rows (Table J3.3) |
| J3.4 | Minimum Spacing | check | `spacing_min` |  |
| J3.5 | Minimum Edge Distance | check | `edge_min` | the Table J3.5 increment for oversized and slotted holes is an unchecked premise of the model |
| J3.6 | Maximum Spacing and Edge Distance | check | `spacing_max`, `edge_max` |  |
| J3.7 | Tensile and Shear Strength of Bolts and Threaded Parts | check | `bolts`, `bolt_tension`, `prying` | prying by the Manual Part 9 T-stub model |
| J3.8 | Combined Tension and Shear in Bearing-Type Connections | check | `bolt_combined` |  |
| J3.9 | High-Strength Bolts in Slip-Critical Connections | check | `slip`, `bolts`, `bolt_combined` | the faying-surface class is a premise of the slip model; slip-critical joints are checked for the bearing-type limit states too |
| J3.10 | Combined Tension and Shear in Slip-Critical Connections | check | `slip` | ksc of Eqs J3-5a/b |
| J3.11a | Bearing and Tearout: Snug-Tightened or Pretensioned High-Strength Bolted Connections | check | `bolts` | per hole, the least of shear, bearing and tearout per bolt |
| J3.11b | Bearing and Tearout: Bolts or Rods Through an Unstiffened Box Member or HSS | excluded |  | v1.2, Chapter K HSS connections (docs/steel_connections.md §3) |
| J3.12 | Special Fasteners | excluded |  | special fasteners are out of scope in v1 (§4) |
| J3.13 | Wall Strength at Tension Fasteners | excluded |  | v1.2, Chapter K HSS connections (docs/steel_connections.md §3) |
| J4.1 | Strength of Elements in Tension | check | `tension_yield`, `tension_rupture` |  |
| J4.2 | Strength of Elements in Shear | check | `shear_yield`, `shear_rupture` |  |
| J4.3 | Block Shear Strength | check | `block_shear` | every enumerated block of the hole pattern |
| J4.4 | Strength of Elements in Compression | check | `compression`, `bracket_edge` | a seat stiffener; a shaped bracket's free edge takes J4.4's factors with the Manual's Q |
| J4.5 | Strength of Elements in Flexure | check | `flexural_yield`, `flexural_rupture`, `cope_buckling`, `plate_buckling`, `seat_flexure`, `bracket_edge` | connecting plates, coped webs (Manual Part 9), extended plates (F11), seats, bracket edges (Part 15) |
| J5.1 | Fillers in Welded Connections | excluded |  | no fillers in v1.0's welded joints |
| J5.2 | Fillers in Bolted Bearing-Type Connections | check | `bolts`, `bolt_combined` | a declared filler takes (a)'s least factor, 0.85, on the bolts' shear strength (the grammar gives no thickness), in slip-critical joints' bearing checks too; an undeclared filler is taken to be absent |
| J6 | Splices | excluded |  | beam and column splices are v1.1 (docs/steel_connections.md §3) |
| J7 | Bearing Strength | check | `bearing` | a stiffened seat's stiffener on the beam flange |
| J8 | Column Bases and Bearing on Concrete | excluded |  | base plates are v1.1 (docs/steel_connections.md §3) |
| J9 | Anchor Rods and Embedments | excluded |  | anchor rods are v1.1 (docs/steel_connections.md §3) |
| J10.1 | Flange Local Bending | check | `flange_local_bending` | the exemption for a load narrower than 0.15 bf across the flange is not taken (no such width is declared) |
| J10.2 | Web Local Yielding | check | `web_local_yielding` |  |
| J10.3 | Web Local Crippling | check | `web_crippling` |  |
| J10.4 | Web Sidesway Buckling | check | `web_sidesway_buckling` |  |
| J10.5 | Web Compression Buckling | check | `web_compression_buckling` |  |
| J10.6 | Web Panel-Zone Shear | check | `panel_zone` |  |
| J10.7 | Unframed Ends of Beams and Girders | premise |  | a member end under a concentrated force is framed or restrained against rotation about its axis; the deck has no inputs for end stiffeners (j10_stiffeners is unmodelled) |
| J10.8 | Additional Stiffener Requirements for Concentrated Forces | rule |  | a J10 force beyond the unstiffened strength fails its check; the deck designs no stiffeners (j10_stiffeners, unmodelled), so a stiffened design is rejected, never passed |
| J10.9 | Additional Doubler Plate Requirements for Concentrated Forces | rule |  | as J10.8: panel-zone shear beyond the unreinforced web fails; doublers are not modelled |
| J10.10 | Transverse Forces on Plate Elements | check | `prying` | a hanger's tee flange and the support flange under the same bolts, each by the prying model |
| K1 | General Provisions and Parameters for HSS Connections | excluded |  | v1.2, Chapter K HSS connections (docs/steel_connections.md §3) |
| K2 | Concentrated Forces on HSS | excluded |  | v1.2, Chapter K HSS connections (docs/steel_connections.md §3) |
| K3 | HSS-to-HSS Truss Connections | excluded |  | v1.2, Chapter K HSS connections (docs/steel_connections.md §3) |
| K4 | HSS-to-HSS Moment Connections | excluded |  | v1.2, Chapter K HSS connections (docs/steel_connections.md §3) |
| K5 | Welds of Plates and Branches to HSS | excluded |  | v1.2, Chapter K HSS connections (docs/steel_connections.md §3) |
| RCSC 4 | Joint types and installation | check | `joint_type` | at least snug-tight; Group 150 and 200 bolts in tension pretensioned; the holes that need a slip-critical joint are J3.3's (hole_use) |
| Manual Part 7 | Entering and tightening clearances | check | `clearance` | the socket allowance is a judged registry row |
| Manual Part 9 | Coped beams and prying action | check | `cope_buckling`, `prying` | prying by the T-stub model with each bolt's tributary length by Figure 9-4 |
| Manual Part 10 | Single-plate, seated and tee connections | check | `ductility`, `extended_ductility`, `plate_buckling`, `seat_flexure`, `compression`, `flexural_yield` | a seat stiffener's width-to-thickness limit is checked with its compression; an extended plate's shear and flexural yielding interaction (Eq 10-8) with its flexural yielding |
| Manual Part 15 | Bracket plates | check | `bracket_edge` |  |
| Shop deck | Stock plate thicknesses and bolt lengths | rule |  | a fixed plate thickness must be stocked (registry shop_deck.plate.*), checked at lowering; bolt lengths are an unchecked premise of the clearance model |
| Connection kinds | Force components without a checked path | check | `load_path` | an axial force on a v1.0 shear connection requires the unmodelled load-path mode: UNKNOWN |

AISC 360-22 Chapters J and K: 58 provisions, 28 check, 5 rule, 5 premise, 20 excluded.
