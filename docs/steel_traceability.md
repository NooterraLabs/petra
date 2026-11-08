# Clause traceability of the steel deck

`python -m petra.models.steel.trace` generates this file from `petra/models/steel/trace.py`. `tests/test_steel_trace.py` fails when this file is stale or a provision is unmapped.

Each row gives its provision one treatment:

- **check** means the checks of the modes in the row encode the provision.
- **rule** means the deck enforces the provision where it reads the design or factors the strength.
- **premise** means the deck states the provision as an assumption and does not check it.
- **excluded** means the provision is outside v1.0.

| Provision | Title | Treatment | Modes | Note |
|---|---|---|---|---|
| J1.1 | Design Basis | rule |  | Every check is phi Rn (LRFD) or Rn / Omega (ASD), by the design's basis. The factors are registry constants of the clause that sets them (`checks.Ctx.available`). |
| J1.2 | Simple Connections | check | `ductility`, `extended_ductility` | Rotation capacity of single plates. The other shear connections are flexible by their Manual configuration, which is a premise of each kind. |
| J1.3 | Moment Connections | excluded |  | FR moment connections are in v1.1 (docs/steel_connections.md §3). |
| J1.4 | Compression Members with Bearing Joints | excluded |  | Column splices are in v1.1 (docs/steel_connections.md §3). |
| J1.5 | Splices in Heavy Sections | excluded |  | Groove-welded splices are in v1.1 (docs/steel_connections.md §3). |
| J1.6 | Weld Access Holes | premise | `cope_buckling` | The catalogue has no weld access holes. A cope's reentrant corners are cut to the J1.6 radius, as the cope-buckling model states. |
| J1.7 | Placement of Welds and Bolts | premise |  | v1.0 has no axially loaded members that end in a connection. A hanger's bolts are symmetric about its stem by the kind's geometry. |
| J1.8 | Bolts in Combination with Welds | rule |  | Each side of a connection (`support_side`, `beam_side`) is bolted or welded, never both, so bolts and welds share no load. |
| J1.9 | Welded Alterations to Structures with Existing Rivets or Bolts | excluded |  | Existing structures are out of scope (docs/steel_connections.md §4). |
| J1.10 | High-Strength Bolts in Combination with Existing Rivets | excluded |  | Existing structures and rivets are out of scope (docs/steel_connections.md §4). |
| J2.1 | Groove Welds | excluded |  | v1.0 has no groove welds. CJP flange welds are in v1.1 (docs/steel_connections.md §3). |
| J2.2a | Fillet Welds: Effective Area | check | `weld` | The effective throat of an equal-leg fillet, 0.707 w. |
| J2.2b | Fillet Welds: Limitations | check | `fillet_size`, `weld` | Minimum size (Table J2.4), length at least 4 w, and maximum size along a lapped part's edge. Welds are continuous, with no intermittent fillets. A lapped bracket's lap is its weld return. Item (d), the end-loaded length of Eq J2-1, applies to a seat stiffener's welds, because the reaction loads them from their end, as at a bearing stiffener. Commentary J2.2b counts the welds of beam web angles and shear plates as not end-loaded. A seat angle's welds run along a leg of at most 12 in (the Shapes Database's longest), with a fillet of at least Table J2.4's least size, 1/8 in, so they never pass 100 w. A smaller fillet fails `fillet_size`. |
| J2.3 | Plug and Slot Welds | excluded |  | The v1.0 catalogue uses no plug or slot welds. |
| J2.4 | Strength | check | `weld`, `weld_base_metal` | Eq J2-4 with kds = 1. The directional increase of Eq J2-5 and the group rule of Eq J2-6 are permitted, not required. The deck does not take them, and leaving them out errs safe. |
| J2.5 | Combination of Welds | excluded |  | v1.0's welded joints are fillet welds only. No joint combines weld types. |
| J2.6 | Filler Metal Requirements | premise | `weld` | Matching filler metal (Table J2.5), as the weld model states. |
| J2.7 | Mixed Weld Metal | premise | `weld` | One electrode per joint, as declared. No notch-toughness requirement applies to v1.0's statically loaded shear connections. |
| J3.1 | Common Bolts | rule |  | A307 bolts are installed snug-tight. `lower.py` rejects any other joint type. |
| J3.2 | High-Strength Bolts | check | `joint_type` | Bolt groups and their strengths are registry rows (Tables J3.1 and J3.2). Pretension is checked where the joint's use requires it, a cyclic load included (J3.2(a)(2) and (b)(1)). |
| J3.3 | Size and Use of Holes | check | `hole_use` | Hole dimensions are registry rows (Table J3.3). |
| J3.4 | Minimum Spacing | check | `spacing_min` |  |
| J3.5 | Minimum Edge Distance | check | `edge_min` | Table J3.5's increment C2 is added to Table J3.4's distance at each edge it applies to. An oversized hole takes it at every edge, and a slot at an edge its length runs toward. A sloping edge takes it in full. |
| J3.6 | Maximum Spacing and Edge Distance | check | `spacing_max`, `edge_max` |  |
| J3.7 | Tensile and Shear Strength of Bolts and Threaded Parts | check | `bolts`, `bolt_tension`, `prying` | Prying uses the Manual Part 9 T-stub model. |
| J3.8 | Combined Tension and Shear in Bearing-Type Connections | check | `bolt_combined` |  |
| J3.9 | High-Strength Bolts in Slip-Critical Connections | check | `slip`, `bolts`, `bolt_combined` | The faying-surface class is a premise of the slip model. Slip-critical joints are also checked for the bearing-type limit states. |
| J3.10 | Combined Tension and Shear in Slip-Critical Connections | check | `slip` | ksc of Eqs J3-5a and J3-5b. |
| J3.11a | Bearing and Tearout: Snug-Tightened or Pretensioned High-Strength Bolted Connections | check | `bolts` | Per hole, the least of shear, bearing and tearout per bolt. A bracket's bolt tears out along its own force, which turns about the centre of the method that loads it. |
| J3.11b | Bearing and Tearout: Bolts or Rods Through an Unstiffened Box Member or HSS | excluded |  | In v1.2, with the Chapter K HSS connections (docs/steel_connections.md §3). |
| J3.12 | Special Fasteners | excluded |  | Special fasteners are out of scope in v1 (docs/steel_connections.md §4). |
| J3.13 | Wall Strength at Tension Fasteners | excluded |  | In v1.2, with the Chapter K HSS connections (docs/steel_connections.md §3). |
| J4.1 | Strength of Elements in Tension | check | `tension_yield`, `tension_rupture` |  |
| J4.2 | Strength of Elements in Shear | check | `shear_yield`, `shear_rupture` |  |
| J4.3 | Block Shear Strength | check | `block_shear` | Every enumerated block of the hole pattern. |
| J4.4 | Strength of Elements in Compression | check | `compression`, `bracket_edge` | The checked elements are a seat stiffener and a shaped bracket's free edge. The free edge takes J4.4's factors with the Manual's Q. |
| J4.5 | Strength of Elements in Flexure | check | `flexural_yield`, `flexural_rupture`, `cope_buckling`, `plate_buckling`, `seat_flexure`, `bracket_edge` | The checked elements are connecting plates, coped webs (Manual Part 9), extended plates and rectangular bracket plates (F11), seats, and bracket edges (Part 15). |
| J5.1 | Fillers in Welded Connections | excluded |  | v1.0's welded joints have no fillers. |
| J5.2 | Fillers in Bolted Bearing-Type Connections | check | `bolts`, `bolt_combined` | A declared filler applies J5.2(a)'s least factor, 0.85, to the bolts' shear strength, because the grammar gives no filler thickness. The factor applies in slip-critical joints' bearing checks too. An undeclared filler is taken to be absent. |
| J6 | Splices | excluded |  | Beam and column splices are in v1.1 (docs/steel_connections.md §3). |
| J7 | Bearing Strength | check | `bearing` | A stiffened seat's fitted stiffener edge and the seat plate on it, each surface at its own Fy. |
| J8 | Column Bases and Bearing on Concrete | excluded |  | Base plates are in v1.1 (docs/steel_connections.md §3). |
| J9 | Anchor Rods and Embedments | excluded |  | Anchor rods are in v1.1 (docs/steel_connections.md §3). |
| J10.1 | Flange Local Bending | check | `flange_local_bending` | The deck does not take the exemption for a load narrower than 0.15 bf across the flange, because the design declares no such width. |
| J10.2 | Web Local Yielding | check | `web_local_yielding` |  |
| J10.3 | Web Local Crippling | check | `web_crippling` |  |
| J10.4 | Web Sidesway Buckling | check | `web_sidesway_buckling` |  |
| J10.5 | Web Compression Buckling | check | `web_compression_buckling` |  |
| J10.6 | Web Panel-Zone Shear | check | `panel_zone` |  |
| J10.7 | Unframed Ends of Beams and Girders | check | `j10_stiffeners` | A flange force at a member end states whether the end is restrained against twisting about its axis (`end_twist`). A free end requires the unmodelled `j10_stiffeners` mode, because the deck draws no stiffeners, so the result is UNKNOWN. A framed connection frames its beam's end, and a seat's top angle restrains the beam's end. |
| J10.8 | Additional Stiffener Requirements for Concentrated Forces | rule |  | A J10 force beyond the unstiffened strength fails its check. The deck designs no stiffeners (`j10_stiffeners` is unmodelled), so it rejects a stiffened design and never passes one. |
| J10.9 | Additional Doubler Plate Requirements for Concentrated Forces | rule |  | As for J10.8, panel-zone shear beyond the unreinforced web's strength fails. The deck does not model doublers. |
| J10.10 | Transverse Forces on Plate Elements | check | `prying` | A hanger's tee flange and the support flange under the same bolts, each checked by the prying model. |
| K1 | General Provisions and Parameters for HSS Connections | excluded |  | In v1.2, with the Chapter K HSS connections (docs/steel_connections.md §3). |
| K2 | Concentrated Forces on HSS | excluded |  | In v1.2, with the Chapter K HSS connections (docs/steel_connections.md §3). |
| K3 | HSS-to-HSS Truss Connections | excluded |  | In v1.2, with the Chapter K HSS connections (docs/steel_connections.md §3). |
| K4 | HSS-to-HSS Moment Connections | excluded |  | In v1.2, with the Chapter K HSS connections (docs/steel_connections.md §3). |
| K5 | Welds of Plates and Branches to HSS | excluded |  | In v1.2, with the Chapter K HSS connections (docs/steel_connections.md §3). |
| App. 3.1 | General Provisions: cycles, threshold and peak stress | check | `fatigue_bolted`, `fatigue_bolt_tension`, `fatigue_weld`, `fatigue_weld_end`, `fatigue_cope` | A load case that names cycles on a connection (`on c1 cycles in [lo, hi]`) states the cyclic load. Its other loads vary inside their intervals, so each interval's width is the load's range and its larger magnitude the peak. Every fatigue check is excused at 20,000 cycles or fewer. Its allowable range is at least FTH, and the stress from the peak load is at most 0.66 Fy. A connection's loads are magnitudes whose sense the connection fixes, so no range reverses. |
| App. 3.1 | General Provisions: HSS under wind loads | excluded |  | In v1.2, with the Chapter K HSS connections (docs/steel_connections.md §3). |
| App. 3.1 | General Provisions: the details and cyclic loads the engineer of record states | rule |  | A design states every part and weld size. Lowering rejects a connection without them, and a cyclic case states the load range and the number of cycles. |
| App. 3.1 | General Provisions: corrosion and temperature | premise | `fatigue_bolted`, `fatigue_bolt_tension`, `fatigue_weld`, `fatigue_weld_end`, `fatigue_cope` | Each fatigue model states that the steel has suitable corrosion protection or sits in a mildly corrosive atmosphere, and stays at or below 300 F. The deck does not check either. |
| App. 3.2 | Calculation of Maximum Stresses and Stress Ranges | check | `fatigue_bolted`, `fatigue_bolt_tension`, `fatigue_weld`, `fatigue_weld_end`, `fatigue_cope` | Stresses come from elastic analysis with no stress concentration factor. An eccentric bolt or weld group's force takes its eccentricity, by the elastic method. A section's stress is bounded by its extreme-fibre bending stress plus its peak shear stress. A bolt's tension includes no prying, and the validity row `no_prying` holds each flange thick enough for that. |
| App. 3.2 | Calculation of Maximum Stresses and Stress Ranges: axially loaded angle members | excluded |  | v1.0 draws no axially loaded angle member. An axial force on a connection requires `load_path`. |
| App. 3.3a | Plain Material and Welded Joints: categories A to E', Eq A-3-1 | check | `fatigue_bolted`, `fatigue_bolt_tension`, `fatigue_weld_end`, `fatigue_cope` | Categories B (Cases 2.1 and 2.2), C (Case 5.7's toe), E' (Case 1.3) and G (Case 8.5, by Section 3.4). |
| App. 3.3b | Plain Material and Welded Joints: category F, Eq A-3-2 | check | `fatigue_weld` |  |
| App. 3.3c | Tension-loaded plate ends: weld toe, and the roots of a pair of fillets, Eqs A-3-5 and A-3-6 | check | `fatigue_weld_end` | The toe is category C. The root is C'' with RFIL, and the root check is excused where RFIL reaches 1. |
| App. 3.3c | Tension-loaded plate ends: PJP groove welds, Eqs A-3-3 and A-3-4 | excluded |  | v1.0 has no groove welds (J2.1). |
| App. 3.4a | Bolts and Threaded Parts: connections loaded in shear | check | `fatigue_bolted`, `joint_type` | Slip-critical and pretensioned joints use Table A-3.1 Section 2. Appendix 3 considers and permits pretensioned joints only (Commentary 3.4), and RCSC 4.2 requires them under a fatigue load, so `joint_type` fails a snug-tight joint in a cyclic case. |
| App. 3.4b | Bolts and Threaded Parts: bolts in tension, Eq A-3-7 | check | `fatigue_bolt_tension`, `joint_type` | Snug-tight bolts carry the whole range, though `joint_type` fails them in a cyclic case (J3.2(a)(2)). Pretensioned bolts with only steel in the grip carry 20% of the peak load, the Section's alternative to a stiffness analysis. Anchor rods are excluded with J9. |
| App. 3.5 | Fabrication and Erection Requirements: reentrant corners, cut edges and end returns | premise | `fatigue_cope`, `fatigue_weld` | A cope's corners are cut to a radius of at least 3/8 in, and thermally cut edges are no rougher than 1,000 micro-inches. A fillet loaded normal to an angle's outstanding leg or along an end plate's outer edge has end returns of two to four times its size. The models state these and the deck does not check them. |
| App. 3.5 | Fabrication and Erection Requirements: backing, CJP reinforcing fillets and weld tabs | excluded |  | v1.0 has no groove welds (J2.1). |
| App. 3.6 | Nondestructive Examination Requirements for Fatigue | excluded |  | The section applies to CJP groove welds. v1.0 has no groove welds (J2.1). |
| Table A-3.1 Cases 1.1, 1.2, 1.4 and 1.5 | Plain material away from welds, weld access holes and member holes | excluded |  | A member's base metal away from its connections belongs to its member design. The deck draws no weld access holes. Bolt holes in a connection are connected material, which Section 2 covers. |
| Table A-3.1 Case 1.3 | Reentrant corners at copes, cuts and block-outs | check | `fatigue_cope` | A beam coped at both flanges is checked at its bottom corner as category E', for a radius of at least 3/8 in. The top corner is in compression (Commentary 3.2). |
| Table A-3.1 Case 2.1 | Gross section of base metal in slip-critical bolted lap joints | check | `fatigue_bolted` |  |
| Table A-3.1 Case 2.2 | Net section of base metal in pretensioned bolted lap joints | check | `fatigue_bolted` |  |
| Table A-3.1 Cases 2.3 and 2.4 | Riveted joints, eyebars and pin plates | excluded |  | v1.0 has no rivets, eyebars or pins. |
| Table A-3.1 Section 3 | Welded joints joining components of built-up members | excluded |  | v1.0 draws no built-up member. |
| Table A-3.1 Section 4 | Longitudinal fillet-welded end connections | excluded |  | The section covers axially loaded members, and v1.0 draws none. |
| Table A-3.1 Cases 5.1 to 5.6 | Groove-welded joints transverse to the stress | excluded |  | v1.0 has no groove welds (J2.1). |
| Table A-3.1 Case 5.7 | A pair of fillet welds at a tension-loaded plate's end | check | `fatigue_weld_end` | A single plate, a seat stiffener or a bracket plate welded to the support on both faces. A plate welded on one face requires `fatigue_detail`. |
| Table A-3.1 Case 5.8 | Base metal at the toe of a transverse stiffener's fillets | excluded |  | v1.0 draws no transverse stiffener on a member. J10.8's stiffeners are never credited. |
| Table A-3.1 Section 6 | Base metal at welded transverse member connections | excluded |  | v1.0 draws no member welded across another with a transition radius. |
| Table A-3.1 Section 7 | Base metal at short attachments | premise |  | A connection's plate or stiffener welded to its support is a short attachment on the support member. The member's own stress range there belongs to its member design, which the connection does not know. |
| Table A-3.1 Case 8.1 | Steel headed stud anchors | excluded |  | v1.0 draws no stud anchors. |
| Table A-3.1 Case 8.2 | Shear on the throat of fillet welds | check | `fatigue_weld` |  |
| Table A-3.1 Cases 8.3 and 8.4 | Plug and slot welds | excluded |  | The v1.0 catalogue uses no plug or slot welds (J2.3). |
| Table A-3.1 Case 8.5 | Bolts and threaded rods in tension | check | `fatigue_bolt_tension` |  |
| RCSC 4 | Joint types and installation | check | `joint_type` | Joints are at least snug-tight. Group 150 and 200 bolts in tension are pretensioned, and so is every joint under a cyclic load past 20,000 cycles (Section 4.2's joints under a fatigue load). J3.3 sets the holes that need a slip-critical joint (`hole_use`). |
| Manual Part 1 | Dimensions and properties: the workable flat depth T of a W's web | check | `beam_fit`, `web_fit` | A part, weld or bolt hole on a beam's or a column's web lies on the web's flat, T deep between the toes of the fillets and centred on the web. A part on a fillet does not fit (`geometry.py`). kdes, k for design calculations, reaches less far than (d - T)/2 in every W row, so the deck does not read it for fit. |
| Manual Part 7 | Entering and tightening clearances | check | `clearance` | The socket allowance is a judged registry row. |
| Manual Part 7 | Eccentrically loaded bolt groups | check | `bolts` | The instantaneous center method with Part 7's load-deformation curve, or the elastic method, whichever holds more. A float search places the centre, and the kernel proves what the group holds about it (`ic.py`). A conventional single plate in Table 10-9's configuration takes its eccentricity as a/2. |
| Manual Part 8 | Eccentrically loaded weld groups | check | `weld`, `weld_base_metal` | A bracket plate on edge, welded on both faces with e past L/8, takes the instantaneous center method with Table 8-4's k = 0. Its base metal takes the force along the weld that the method puts there. Every other eccentric weld group takes the elastic method. |
| Manual Part 9 | Coped beams, prying action and shear tee ductility | check | `cope_buckling`, `prying`, `tee_ductility` | Prying uses the T-stub model, with each bolt's tributary length from Figure 9-4. A shear tee's rotational ductility uses Eqs 9-51 and 9-52, or the alternate Eq 9-53, as Companion II.A-30 and II.A-31 apply them. |
| Manual Part 10 | Single-plate, seated and tee connections | check | `ductility`, `extended_ductility`, `plate_buckling`, `seat_flexure`, `compression`, `flexural_yield` | A seat stiffener's width-to-thickness limit is checked with its compression. An extended plate's shear and flexural yielding interaction (Eq 10-8) is checked with its flexural yielding. In the strength checks (`block_shear`, `seat_flexure`, `web_local_yielding`, `web_crippling`, `weld`), the 1/4 in beam underrun comes off a beam web's end distance and is added to a seat's setback, as the Companion takes it. |
| Manual Part 15 | Bracket plates | check | `bracket_edge` |  |
| Shop deck | Stock plate thicknesses and bolt lengths | rule |  | A fixed plate thickness must be stocked (registry `shop_deck.plate.*`), and lowering checks it. Bolt lengths are an unchecked premise of the clearance model. |
| Geometry | Fit of the drawn parts | check | `beam_fit`, `flange_fit`, `web_fit` | `geometry.py` places the parts that each kind's lines draw in one frame per connection. The beam end clears the support and lands on a seat, holes and welds lie on the support's flange and clear its web, a seat's holes lie on its leg, and a beam's flange passes between a column's flanges. Positions the lines leave open are taken where they fit best. |
| Connection kinds | Force components without a checked path | check | `load_path` | An axial force on a v1.0 shear connection requires the unmodelled `load_path` mode, so the result is UNKNOWN. |
| Connection kinds | Cyclic details without an encoded category | check | `fatigue_detail` | Under a cyclic load, a detail whose Table A-3.1 category the deck does not encode requires the unmodelled `fatigue_detail` mode: a single fillet at an angle's or a tee's toe, a plate welded on one face, a lapped plate's C-shaped fillet, a seat angle, a hanger's tee, and a member's flange under a tensile force. The result is UNKNOWN (`cyclic.py`). |

The table maps 58 provisions of AISC 360-22 Chapters J and K: 29 check, 5 rule, 4 premise, 20 excluded. It maps 31 provisions of Appendix 3, Fatigue: 13 check, 1 rule, 3 premise, 14 excluded.
