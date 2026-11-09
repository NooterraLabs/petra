# Clause traceability of the steel deck

`py -3.11 scripts/source_docs.py` generates this file from `petra/models/steel/trace.py` and `docs/sources/`. `tests/test_sources.py` fails when it is stale, and `tests/test_steel_trace.py` fails when a provision is unmapped. Every count here is measured from those files.

Each row gives its provision one treatment:

- **check** means the checks of the modes in the row encode the provision.
- **rule** means the deck enforces the provision where it reads the design or factors the strength.
- **premise** means the deck states the provision as an assumption and does not check it.
- **excluded** means the provision is outside v1.0.

The values column counts the registry values, equations and coded rules whose clause names the provision. The values section lists each one with the page that states it.

| Provision | Title | Treatment | Modes | Values | Note |
|---|---|---|---|---|---|
| J1.1 | Design Basis | rule |  | 0 | Every check is phi Rn (LRFD) or Rn / Omega (ASD), by the design's basis. The factors are registry constants of the clause that sets them (`checks.Ctx.available`). |
| J1.2 | Simple Connections | check | `ductility`, `extended_ductility` | 0 | Rotation capacity of single plates. The other shear connections are flexible by their Manual configuration, which is a premise of each kind. |
| J1.3 | Moment Connections | excluded |  | 0 | FR moment connections are in v1.1 (docs/steel_connections.md §3). |
| J1.4 | Compression Members with Bearing Joints | excluded |  | 0 | Column splices are in v1.1 (docs/steel_connections.md §3). |
| J1.5 | Splices in Heavy Sections | excluded |  | 0 | Groove-welded splices are in v1.1 (docs/steel_connections.md §3). |
| J1.6 | Weld Access Holes | premise | `cope_buckling` | 0 | The catalogue has no weld access holes. A cope's reentrant corners are cut to the J1.6 radius, as the cope-buckling model states. |
| J1.7 | Placement of Welds and Bolts | premise |  | 0 | v1.0 has no axially loaded members that end in a connection. A hanger's bolts are symmetric about its stem by the kind's geometry. |
| J1.8 | Bolts in Combination with Welds | rule |  | 0 | Each side of a connection (`support_side`, `beam_side`) is bolted or welded, never both, so bolts and welds share no load. |
| J1.9 | Welded Alterations to Structures with Existing Rivets or Bolts | excluded |  | 0 | Existing structures are out of scope (docs/steel_connections.md §4). |
| J1.10 | High-Strength Bolts in Combination with Existing Rivets | excluded |  | 0 | Existing structures and rivets are out of scope (docs/steel_connections.md §4). |
| J2.1 | Groove Welds | excluded |  | 0 | v1.0 has no groove welds. CJP flange welds are in v1.1 (docs/steel_connections.md §3). |
| J2.2a | Fillet Welds: Effective Area | check | `weld` | 1 | The effective throat of an equal-leg fillet, 0.707 w. |
| J2.2b | Fillet Welds: Limitations | check | `fillet_size`, `weld` | 15 | Minimum size (Table J2.4), length at least 4 w, and maximum size along a lapped part's edge. Welds are continuous, with no intermittent fillets. A lapped bracket's lap is its weld return. Item (d), the end-loaded length of Eq J2-1, applies to a seat stiffener's welds, because the reaction loads them from their end, as at a bearing stiffener. Commentary J2.2b counts the welds of beam web angles and shear plates as not end-loaded. A seat angle's welds run along a leg of at most 12 in (the Shapes Database's longest), with a fillet of at least Table J2.4's least size, 1/8 in, so they never pass 100 w. A smaller fillet fails `fillet_size`. |
| J2.3 | Plug and Slot Welds | excluded |  | 0 | The v1.0 catalogue uses no plug or slot welds. |
| J2.4 | Strength | check | `weld`, `weld_base_metal` | 9 | Eq J2-4 with kds = 1. The directional increase of Eq J2-5 and the group rule of Eq J2-6 are permitted, not required. The deck does not take them, and leaving them out errs safe. |
| J2.5 | Combination of Welds | excluded |  | 0 | v1.0's welded joints are fillet welds only. No joint combines weld types. |
| J2.6 | Filler Metal Requirements | premise | `weld` | 0 | Matching filler metal (Table J2.5), as the weld model states. |
| J2.7 | Mixed Weld Metal | premise | `weld` | 0 | One electrode per joint, as declared. No notch-toughness requirement applies to v1.0's statically loaded shear connections. |
| J3.1 | Common Bolts | rule |  | 4 | A307 bolts are installed snug-tight. `lower.py` rejects any other joint type. |
| J3.2 | High-Strength Bolts | check | `joint_type` | 23 | Bolt groups and their strengths are registry rows (Tables J3.1 and J3.2). Pretension is checked where the joint's use requires it, a cyclic load included (J3.2(a)(2) and (b)(1)). |
| J3.3 | Size and Use of Holes | check | `hole_use` | 56 | Hole dimensions are registry rows (Table J3.3). |
| J3.4 | Minimum Spacing | check | `spacing_min` | 1 |  |
| J3.5 | Minimum Edge Distance | check | `edge_min` | 30 | Table J3.5's increment C2 is added to Table J3.4's distance at each edge it applies to. An oversized hole takes it at every edge, and a slot at an edge its length runs toward. A sloping edge takes it in full. A beam coped at both flanges holds its bottom row from the bottom cope's cut. |
| J3.6 | Maximum Spacing and Edge Distance | check | `spacing_max`, `edge_max` | 6 | The maximum is to a bolt's nearest edge. A bottom cope takes none, since the beam end's own limit already bounds the bottom row's nearest edge. |
| J3.7 | Tensile and Shear Strength of Bolts and Threaded Parts | check | `bolts`, `bolt_tension`, `prying` | 18 | Prying uses the Manual Part 9 T-stub model. |
| J3.8 | Combined Tension and Shear in Bearing-Type Connections | check | `bolt_combined` | 4 |  |
| J3.9 | High-Strength Bolts in Slip-Critical Connections | check | `slip`, `bolts`, `bolt_combined` | 13 | The faying-surface class is a premise of the slip model. Slip-critical joints are also checked for the bearing-type limit states. A plain slot in an eccentric bracket group takes the factor of a slot parallel to the load, since the bracket's bolts push along it. |
| J3.10 | Combined Tension and Shear in Slip-Critical Connections | check | `slip` | 4 | ksc of Eqs J3-5a and J3-5b. |
| J3.11a | Bearing and Tearout: Snug-Tightened or Pretensioned High-Strength Bolted Connections | check | `bolts` | 14 | Per hole, the least of shear, bearing and tearout per bolt. A bracket's bolt tears out along its own force, which turns about the centre of the method that loads it. |
| J3.11b | Bearing and Tearout: Bolts or Rods Through an Unstiffened Box Member or HSS | excluded |  | 0 | In v1.2, with the Chapter K HSS connections (docs/steel_connections.md §3). |
| J3.12 | Special Fasteners | excluded |  | 0 | Special fasteners are out of scope in v1 (docs/steel_connections.md §4). |
| J3.13 | Wall Strength at Tension Fasteners | excluded |  | 0 | In v1.2, with the Chapter K HSS connections (docs/steel_connections.md §3). |
| J4.1 | Strength of Elements in Tension | check | `tension_yield`, `tension_rupture` | 6 |  |
| J4.2 | Strength of Elements in Shear | check | `shear_yield`, `shear_rupture` | 7 |  |
| J4.3 | Block Shear Strength | check | `block_shear` | 6 | Every enumerated block of the hole pattern. |
| J4.4 | Strength of Elements in Compression | check | `compression`, `bracket_edge` | 3 | The checked elements are a seat stiffener and a shaped bracket's free edge. The free edge takes J4.4's factors with the Manual's Q. |
| J4.5 | Strength of Elements in Flexure | check | `flexural_yield`, `flexural_rupture`, `cope_buckling`, `plate_buckling`, `seat_flexure`, `bracket_edge` | 4 | The checked elements are connecting plates, coped webs (Manual Part 9), extended plates and rectangular bracket plates (F11), seats, and bracket edges (Part 15). |
| J5.1 | Fillers in Welded Connections | excluded |  | 0 | v1.0's welded joints have no fillers. |
| J5.2 | Fillers in Bolted Bearing-Type Connections | check | `bolts`, `bolt_combined` | 1 | A declared filler applies J5.2(a)'s least factor, 0.85, to the bolts' shear strength, because the grammar gives no filler thickness. The factor applies in slip-critical joints' bearing checks too. An undeclared filler is taken to be absent. |
| J6 | Splices | excluded |  | 0 | Beam and column splices are in v1.1 (docs/steel_connections.md §3). |
| J7 | Bearing Strength | check | `bearing` | 4 | A stiffened seat's fitted stiffener edge and the seat plate on it, each surface at its own Fy. |
| J8 | Column Bases and Bearing on Concrete | excluded |  | 0 | Base plates are in v1.1 (docs/steel_connections.md §3). |
| J9 | Anchor Rods and Embedments | excluded |  | 0 | Anchor rods are in v1.1 (docs/steel_connections.md §3). |
| J10.1 | Flange Local Bending | check | `flange_local_bending` | 6 | The deck does not take the exemption for a load narrower than 0.15 bf across the flange, because the design declares no such width. |
| J10.2 | Web Local Yielding | check | `web_local_yielding` | 8 |  |
| J10.3 | Web Local Crippling | check | `web_crippling` | 11 |  |
| J10.4 | Web Sidesway Buckling | check | `web_sidesway_buckling` | 9 |  |
| J10.5 | Web Compression Buckling | check | `web_compression_buckling` | 5 |  |
| J10.6 | Web Panel-Zone Shear | check | `panel_zone` | 9 |  |
| J10.7 | Unframed Ends of Beams and Girders | check | `j10_stiffeners` | 0 | A flange force at a member end states whether the end is restrained against twisting about its axis (`end_twist`). A free end requires the unmodelled `j10_stiffeners` mode, because the deck draws no stiffeners, so the result is UNKNOWN. A framed connection frames its beam's end, and a seat's top angle restrains the beam's end. |
| J10.8 | Additional Stiffener Requirements for Concentrated Forces | rule |  | 0 | A J10 force beyond the unstiffened strength fails its check. The deck designs no stiffeners (`j10_stiffeners` is unmodelled), so it rejects a stiffened design and never passes one. |
| J10.9 | Additional Doubler Plate Requirements for Concentrated Forces | rule |  | 0 | As for J10.8, panel-zone shear beyond the unreinforced web's strength fails. The deck does not model doublers. |
| J10.10 | Transverse Forces on Plate Elements | check | `prying` | 0 | A hanger's tee flange and the support flange under the same bolts, each checked by the prying model. |
| K1 | General Provisions and Parameters for HSS Connections | excluded |  | 0 | In v1.2, with the Chapter K HSS connections (docs/steel_connections.md §3). |
| K2 | Concentrated Forces on HSS | excluded |  | 0 | In v1.2, with the Chapter K HSS connections (docs/steel_connections.md §3). |
| K3 | HSS-to-HSS Truss Connections | excluded |  | 0 | In v1.2, with the Chapter K HSS connections (docs/steel_connections.md §3). |
| K4 | HSS-to-HSS Moment Connections | excluded |  | 0 | In v1.2, with the Chapter K HSS connections (docs/steel_connections.md §3). |
| K5 | Welds of Plates and Branches to HSS | excluded |  | 0 | In v1.2, with the Chapter K HSS connections (docs/steel_connections.md §3). |
| App. 3.1 | General Provisions: cycles, threshold and peak stress | check | `fatigue_bolted`, `fatigue_bolt_tension`, `fatigue_weld`, `fatigue_weld_end`, `fatigue_cope` | 2 | A load case that names cycles on a connection (`on c1 cycles in [lo, hi]`) states the cyclic load. Its other loads vary inside their intervals, so each interval's width is the load's range and its larger magnitude the peak. Every fatigue check is excused at 20,000 cycles or fewer. Its allowable range is at least FTH, and the stress from the peak load is at most 0.66 Fy. A connection's loads are magnitudes whose sense the connection fixes, so no range reverses. |
| App. 3.1 | General Provisions: HSS under wind loads | excluded |  |  | In v1.2, with the Chapter K HSS connections (docs/steel_connections.md §3). |
| App. 3.1 | General Provisions: the details and cyclic loads the engineer of record states | rule |  |  | A design states every part and weld size. Lowering rejects a connection without them, and a cyclic case states the load range and the number of cycles. |
| App. 3.1 | General Provisions: corrosion and temperature | premise | `fatigue_bolted`, `fatigue_bolt_tension`, `fatigue_weld`, `fatigue_weld_end`, `fatigue_cope` |  | Each fatigue model states that the steel has suitable corrosion protection or sits in a mildly corrosive atmosphere, and stays at or below 300 F. The deck does not check either. |
| App. 3.2 | Calculation of Maximum Stresses and Stress Ranges | check | `fatigue_bolted`, `fatigue_bolt_tension`, `fatigue_weld`, `fatigue_weld_end`, `fatigue_cope` | 1 | Stresses come from elastic analysis with no stress concentration factor. An eccentric bolt or weld group's force takes its eccentricity, by the elastic method. A section's stress is bounded by its extreme-fibre bending stress plus its peak shear stress. A bolt's tension includes no prying, and the validity row `no_prying` holds each flange thick enough for that. |
| App. 3.2 | Calculation of Maximum Stresses and Stress Ranges: axially loaded angle members | excluded |  |  | v1.0 draws no axially loaded angle member. An axial force on a connection requires `load_path`. |
| App. 3.3a | Plain Material and Welded Joints: categories A to E', Eq A-3-1 | check | `fatigue_bolted`, `fatigue_bolt_tension`, `fatigue_weld_end`, `fatigue_cope` | 11 | Categories B (Cases 2.1 and 2.2), C (Case 5.7's toe), E' (Case 1.3) and G (Case 8.5, by Section 3.4). |
| App. 3.3b | Plain Material and Welded Joints: category F, Eq A-3-2 | check | `fatigue_weld` | 5 |  |
| App. 3.3c | Tension-loaded plate ends: weld toe, and the roots of a pair of fillets, Eqs A-3-5 and A-3-6 | check | `fatigue_weld_end` | 6 | The toe is category C. The root is C'' with RFIL, and the root check is excused where RFIL reaches 1. |
| App. 3.3c | Tension-loaded plate ends: PJP groove welds, Eqs A-3-3 and A-3-4 | excluded |  |  | v1.0 has no groove welds (J2.1). |
| App. 3.4a | Bolts and Threaded Parts: connections loaded in shear | check | `fatigue_bolted`, `joint_type` | 0 | Slip-critical and pretensioned joints use Table A-3.1 Section 2. Appendix 3 considers and permits pretensioned joints only (Commentary 3.4), and RCSC 4.2 requires them under a fatigue load, so `joint_type` fails a snug-tight joint in a cyclic case. |
| App. 3.4b | Bolts and Threaded Parts: bolts in tension, Eq A-3-7 | check | `fatigue_bolt_tension`, `joint_type` | 3 | Snug-tight bolts carry the whole range, though `joint_type` fails them in a cyclic case (J3.2(a)(2)). Pretensioned bolts with only steel in the grip carry 20% of the peak load, the Section's alternative to a stiffness analysis. Anchor rods are excluded with J9. |
| App. 3.5 | Fabrication and Erection Requirements: reentrant corners, cut edges and end returns | premise | `fatigue_cope`, `fatigue_weld` | 0 | A cope's corners are cut to a radius of at least 3/8 in, and thermally cut edges are no rougher than 1,000 micro-inches. A fillet loaded normal to an angle's outstanding leg or along an end plate's outer edge has end returns of two to four times its size. The models state these and the deck does not check them. |
| App. 3.5 | Fabrication and Erection Requirements: backing, CJP reinforcing fillets and weld tabs | excluded |  |  | v1.0 has no groove welds (J2.1). |
| App. 3.6 | Nondestructive Examination Requirements for Fatigue | excluded |  | 0 | The section applies to CJP groove welds. v1.0 has no groove welds (J2.1). |
| Table A-3.1 Cases 1.1, 1.2, 1.4 and 1.5 | Plain material away from welds, weld access holes and member holes | excluded |  | 0 | A member's base metal away from its connections belongs to its member design. The deck draws no weld access holes. Bolt holes in a connection are connected material, which Section 2 covers. |
| Table A-3.1 Case 1.3 | Reentrant corners at copes, cuts and block-outs | check | `fatigue_cope` | 0 | A beam coped at both flanges is checked at its bottom corner as category E', for a radius of at least 3/8 in. The top corner is in compression (Commentary 3.2). |
| Table A-3.1 Case 2.1 | Gross section of base metal in slip-critical bolted lap joints | check | `fatigue_bolted` | 0 |  |
| Table A-3.1 Case 2.2 | Net section of base metal in pretensioned bolted lap joints | check | `fatigue_bolted` | 0 |  |
| Table A-3.1 Cases 2.3 and 2.4 | Riveted joints, eyebars and pin plates | excluded |  | 0 | v1.0 has no rivets, eyebars or pins. |
| Table A-3.1 Section 3 | Welded joints joining components of built-up members | excluded |  | 0 | v1.0 draws no built-up member. |
| Table A-3.1 Section 4 | Longitudinal fillet-welded end connections | excluded |  | 0 | The section covers axially loaded members, and v1.0 draws none. |
| Table A-3.1 Cases 5.1 to 5.6 | Groove-welded joints transverse to the stress | excluded |  | 0 | v1.0 has no groove welds (J2.1). |
| Table A-3.1 Case 5.7 | A pair of fillet welds at a tension-loaded plate's end | check | `fatigue_weld_end` | 0 | A single plate, a seat stiffener or a bracket plate welded to the support on both faces. A plate welded on one face requires `fatigue_detail`. |
| Table A-3.1 Case 5.8 | Base metal at the toe of a transverse stiffener's fillets | excluded |  | 0 | v1.0 draws no transverse stiffener on a member. J10.8's stiffeners are never credited. |
| Table A-3.1 Section 6 | Base metal at welded transverse member connections | excluded |  | 0 | v1.0 draws no member welded across another with a transition radius. |
| Table A-3.1 Section 7 | Base metal at short attachments | premise |  | 0 | A connection's plate or stiffener welded to its support is a short attachment on the support member. The member's own stress range there belongs to its member design, which the connection does not know. |
| Table A-3.1 Case 8.1 | Steel headed stud anchors | excluded |  | 0 | v1.0 draws no stud anchors. |
| Table A-3.1 Case 8.2 | Shear on the throat of fillet welds | check | `fatigue_weld` | 0 |  |
| Table A-3.1 Cases 8.3 and 8.4 | Plug and slot welds | excluded |  | 0 | The v1.0 catalogue uses no plug or slot welds (J2.3). |
| Table A-3.1 Case 8.5 | Bolts and threaded rods in tension | check | `fatigue_bolt_tension` | 0 |  |
| RCSC 4 | Joint types and installation | check | `joint_type` | 3 | Joints are at least snug-tight. Group 150 and 200 bolts in tension are pretensioned, and so is every joint under a cyclic load past 20,000 cycles (Section 4.2's joints under a fatigue load). J3.3 sets the holes that need a slip-critical joint (`hole_use`). |
| Manual Part 1 | Dimensions and properties: the workable flat depth T of a W's web | check | `beam_fit`, `web_fit` | 21 | A part, weld or bolt hole on a beam's or a column's web lies on the web's flat, T deep between the toes of the fillets and centred on the web. A part on a fillet does not fit (`geometry.py`). kdes, k for design calculations, reaches less far than (d - T)/2 in every W row, so the deck does not read it for fit. |
| Manual Part 7 | Entering and tightening clearances | check | `clearance` | 5 | The socket allowance is a judged registry row. |
| Manual Part 7 | Eccentrically loaded bolt groups | check | `bolts` |  | The instantaneous center method with Part 7's load-deformation curve, or the elastic method, whichever holds more. A float search places the centre, and the kernel proves what the group holds about it (`ic.py`). A conventional single plate in Table 10-9's configuration takes its eccentricity as a/2. |
| Manual Part 8 | Eccentrically loaded weld groups | check | `weld`, `weld_base_metal` | 14 | A bracket plate on edge, welded on both faces with e past L/8, takes the instantaneous center method with Table 8-4's k = 0. Its base metal takes the force along the weld that the method puts there. Every other eccentric weld group takes the elastic method. |
| Manual Part 9 | Coped beams, prying action and shear tee ductility | check | `cope_buckling`, `prying`, `tee_ductility` | 27 | Prying uses the T-stub model, with each bolt's tributary length from Figure 9-4. A shear tee's rotational ductility uses Eqs 9-51 and 9-52, or the alternate Eq 9-53, as Companion II.A-30 and II.A-31 apply them. |
| Manual Part 10 | Single-plate, seated and tee connections | check | `ductility`, `extended_ductility`, `plate_buckling`, `seat_flexure`, `compression`, `flexural_yield` | 15 | A seat stiffener's width-to-thickness limit is checked with its compression. An extended plate's shear and flexural yielding interaction (Eq 10-8) is checked with its flexural yielding. In the strength checks (`block_shear`, `seat_flexure`, `web_local_yielding`, `web_crippling`, `weld`), the 1/4 in beam underrun comes off a beam web's end distance and is added to a seat's setback, as the Companion takes it. |
| Manual Part 15 | Bracket plates | check | `bracket_edge` | 13 |  |
| Shop deck | Stock plate thicknesses and bolt lengths | rule |  | 0 | A fixed plate thickness must be stocked (registry `shop_deck.plate.*`), and lowering checks it. Bolt lengths are an unchecked premise of the clearance model. |
| Geometry | Fit of the drawn parts | check | `beam_fit`, `flange_fit`, `web_fit` | 0 | `geometry.py` places the parts that each kind's lines draw in one frame per connection. The beam end clears the support and lands on a seat, holes and welds lie on the support's flange and clear its web, a seat's holes lie on its leg, and a beam's flange passes between a column's flanges. Positions the lines leave open are taken where they fit best. |
| Connection kinds | Force components without a checked path | check | `load_path` | 0 | An axial force on a v1.0 shear connection requires the unmodelled `load_path` mode, so the result is UNKNOWN. |
| Connection kinds | Cyclic details without an encoded category | check | `fatigue_detail` |  | Under a cyclic load, a detail whose Table A-3.1 category the deck does not encode requires the unmodelled `fatigue_detail` mode: a single fillet at an angle's or a tee's toe, a plate welded on one face, a lapped plate's C-shaped fillet, a seat angle, a hanger's tee, and a member's flange under a tensile force. The result is UNKNOWN (`cyclic.py`). |

The table maps 58 provisions of AISC 360-22 Chapters J and K. The deck checks 29, enforces 5 as rules, states 4 as premises and excludes 20. It maps 31 provisions of Appendix 3, Fatigue, and checks 13, enforces 1 as a rule, states 3 as premises and excludes 14.

## Coverage of Chapters J and K

Petra encodes 34 of the 58 provisions of Chapters J and K (59%) as checks or rules. That is 34 of Chapter J's 53 (64%) and none of Chapter K's 5. It states 4 as premises (J1.6, J1.7, J2.6 and J2.7) and excludes 20 (J1.3, J1.4, J1.5, J1.9, J1.10, J2.1, J2.3, J2.5, J3.11b, J3.12, J3.13, J5.1, J6, J8, J9, K1, K2, K3, K4 and K5).

AISC 360-22 numbers 101 equations in Chapters J and K, 46 in J and 55 in K (`docs/sources/equations.json`). The inventory cites 33 of Chapter J's (72%) and none of Chapter K's. The rest of Chapter J's are J2-2, J2-3 and J2-6 in J2.4 (check); J3-2 in J3.8 (check); J3-6g, J3-6h and J3-6i in J3.11b (excluded); J7-2 and J7-3 in J7 (check); J8-1 and J8-2 in J8 (excluded); J10-11 and J10-12 in J10.6 (check).

## Values

A value's page is where `docs/sources/anchors.jsonl` anchors it, and `scripts/verify_sources.py` checks the page against the document. A value can name several provisions and is listed under each.

### J2.2a

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `code.fillet_throat` | w / sqrt 2 | the throat, from the root to the weld's face | AISC 360-22 p. 194 |

### J2.2b

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc360.j2_2b.beta_intercept` | 1.2 | 1.2 | AISC 360-22 p. 195, from the page image |
| `const.aisc360.j2_2b.beta_slope` | 0.002 | 0.002 | AISC 360-22 p. 195, from the page image |
| `const.aisc360.j2_2b.edge_less` | 1/16 in | 1/16 | AISC 360-22 p. 195, from the page image |
| `const.aisc360.j2_2b.edge_t` | 1/4 in | 1/4 | AISC 360-22 p. 195, from the page image |
| `const.aisc360.j2_2b.end_loaded_cap` | 300 | 300 | AISC 360-22 p. 195 |
| `const.aisc360.j2_2b.end_loaded_ratio` | 100 | 100 | AISC 360-22 p. 195 |
| `const.aisc360.j2_2b.length_ratio` | 4 | 4 | AISC 360-22 p. 195, from the page image |
| `const.aisc360.j2_2b.t1` | 1/4 in | 1/4 | AISC 360-22 p. 196 |
| `const.aisc360.j2_2b.t2` | 1/2 in | 1/2 | AISC 360-22 p. 196 |
| `const.aisc360.j2_2b.t3` | 3/4 in | 3/4 | AISC 360-22 p. 196 |
| `const.aisc360.j2_2b.w1` | 1/8 in | 1/8 | AISC 360-22 p. 196 |
| `const.aisc360.j2_2b.w2` | 3/16 in | 3/16 | AISC 360-22 p. 196 |
| `const.aisc360.j2_2b.w3` | 1/4 in | 1/4 | AISC 360-22 p. 196 |
| `const.aisc360.j2_2b.w4` | 5/16 in | 5/16 | AISC 360-22 p. 196 |
| `eq.aisc360.J2-1` | `end_loaded_length` | beta = 1.2 - 0.002(l/w) <= 1.0 | AISC 360-22 p. 195, from the page image |

### J2.4

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `code.kds_one` | 1 | 1.0 | AISC 360-22 p. 198 |
| `const.aisc360.j2_4.fnw` | 0.6 | 0.60 | AISC 360-22 p. 200 |
| `const.aisc360.j2_4.kds` | 0.5 | 0.50 | AISC 360-22 p. 198 |
| `const.aisc360.j2_4.kds_power` | 1.5 | 1.5 | AISC 360-22 p. 198 |
| `const.aisc360.j2_4.omega` | 2 | 2.00 | AISC 360-22 p. 200 |
| `const.aisc360.j2_4.phi` | 0.75 | 0.75 | AISC 360-22 p. 200 |
| `const.petra.weld_ic.along_peak` | 1.04 |  | absent: Petra's own value; no standard states it |
| `eq.aisc360.J2-4` | `fillet_line` | Rn = Fnw Awe kds | AISC 360-22 p. 198 |
| `eq.aisc360.J2-5` | `ic_weld_bounds` | kds = (1.0 + 0.50 sin^1.5 theta) | AISC 360-22 p. 198 |

### J3.1

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `bolt_group.120.fu` | 120 ksi | 120 | its name |
| `bolt_group.144.fu` | 144 ksi | 144 | its name |
| `bolt_group.150.fu` | 150 ksi | 150 | its name |
| `bolt_group.200.fu` | 200 ksi | 200 | its name |

### J3.2

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `bolt_group.120.fu` | 120 ksi | 120 | its name |
| `bolt_group.144.fu` | 144 ksi | 144 | its name |
| `bolt_group.150.fu` | 150 ksi | 150 | its name |
| `bolt_group.200.fu` | 200 ksi | 200 | its name |
| `code.tm_definition` | Tm = 0.70 Fu As | 0.70 | AISC 360-22 p. 204 |
| `const.bolt_us.1.Tm_g120` | 51 kips | 51 | AISC 360-22 p. 204 |
| `const.bolt_us.1.Tm_g150` | 64 kips | 64 | AISC 360-22 p. 204 |
| `const.bolt_us.1_1_2.Tm_g120` | 118 kips | 118 | AISC 360-22 p. 204 |
| `const.bolt_us.1_1_2.Tm_g150` | 148 kips | 148 | AISC 360-22 p. 204 |
| `const.bolt_us.1_1_4.Tm_g120` | 81 kips | 81 | AISC 360-22 p. 204 |
| `const.bolt_us.1_1_4.Tm_g150` | 102 kips | 102 | AISC 360-22 p. 204 |
| `const.bolt_us.1_1_8.Tm_g120` | 64 kips | 64 | AISC 360-22 p. 204 |
| `const.bolt_us.1_1_8.Tm_g150` | 80 kips | 80 | AISC 360-22 p. 204 |
| `const.bolt_us.1_2.Tm_g120` | 12 kips | 12 | AISC 360-22 p. 204 |
| `const.bolt_us.1_2.Tm_g150` | 15 kips | 15 | AISC 360-22 p. 204 |
| `const.bolt_us.1_3_8.Tm_g120` | 97 kips | 97 | AISC 360-22 p. 204 |
| `const.bolt_us.1_3_8.Tm_g150` | 121 kips | 121 | AISC 360-22 p. 204 |
| `const.bolt_us.3_4.Tm_g120` | 28 kips | 28 | AISC 360-22 p. 204 |
| `const.bolt_us.3_4.Tm_g150` | 35 kips | 35 | AISC 360-22 p. 204 |
| `const.bolt_us.5_8.Tm_g120` | 19 kips | 19 | AISC 360-22 p. 204 |
| `const.bolt_us.5_8.Tm_g150` | 24 kips | 24 | AISC 360-22 p. 204 |
| `const.bolt_us.7_8.Tm_g120` | 39 kips | 39 | AISC 360-22 p. 204 |
| `const.bolt_us.7_8.Tm_g150` | 49 kips | 49 | AISC 360-22 p. 204 |

### J3.3

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `code.holes_large` | `holes_for` | d + 1/8 | AISC 360-22 p. 205 |
| `const.aisc360.j3_3.long_slot_plies` | 1 | one | AISC 360-22 p. 206 |
| `const.bolt_us.1.lsl_l` | 2-1/2 in | 2-1/2 | AISC 360-22 p. 205, from the page image |
| `const.bolt_us.1.lsl_w` | 1-1/8 in | 1-1/8 | AISC 360-22 p. 205, from the page image |
| `const.bolt_us.1.ovs` | 1-1/4 in | 1-1/4 | AISC 360-22 p. 205, from the page image |
| `const.bolt_us.1.ssl_l` | 1-5/16 in | 1-5/16 | AISC 360-22 p. 205, from the page image |
| `const.bolt_us.1.ssl_w` | 1-1/8 in | 1-1/8 | AISC 360-22 p. 205, from the page image |
| `const.bolt_us.1.std` | 1-1/8 in | 1-1/8 | AISC 360-22 p. 205, from the page image |
| `const.bolt_us.1_1_2.lsl_l` | 3-3/4 in | 2.5 d | AISC 360-22 p. 205 |
| `const.bolt_us.1_1_2.lsl_w` | 1-5/8 in | d + 1/8 | AISC 360-22 p. 205 |
| `const.bolt_us.1_1_2.ovs` | 1-13/16 in | d + 5/16 | AISC 360-22 p. 205 |
| `const.bolt_us.1_1_2.ssl_l` | 1-7/8 in | d + 3/8 | AISC 360-22 p. 205 |
| `const.bolt_us.1_1_2.ssl_w` | 1-5/8 in | d + 1/8 | AISC 360-22 p. 205 |
| `const.bolt_us.1_1_2.std` | 1-5/8 in | d + 1/8 | AISC 360-22 p. 205 |
| `const.bolt_us.1_1_4.lsl_l` | 3-1/8 in | 2.5 d | AISC 360-22 p. 205 |
| `const.bolt_us.1_1_4.lsl_w` | 1-3/8 in | d + 1/8 | AISC 360-22 p. 205 |
| `const.bolt_us.1_1_4.ovs` | 1-9/16 in | d + 5/16 | AISC 360-22 p. 205 |
| `const.bolt_us.1_1_4.ssl_l` | 1-5/8 in | d + 3/8 | AISC 360-22 p. 205 |
| `const.bolt_us.1_1_4.ssl_w` | 1-3/8 in | d + 1/8 | AISC 360-22 p. 205 |
| `const.bolt_us.1_1_4.std` | 1-3/8 in | d + 1/8 | AISC 360-22 p. 205 |
| `const.bolt_us.1_1_8.lsl_l` | 2-13/16 in | 2.5 d | AISC 360-22 p. 205 |
| `const.bolt_us.1_1_8.lsl_w` | 1-1/4 in | d + 1/8 | AISC 360-22 p. 205 |
| `const.bolt_us.1_1_8.ovs` | 1-7/16 in | d + 5/16 | AISC 360-22 p. 205 |
| `const.bolt_us.1_1_8.ssl_l` | 1-1/2 in | d + 3/8 | AISC 360-22 p. 205 |
| `const.bolt_us.1_1_8.ssl_w` | 1-1/4 in | d + 1/8 | AISC 360-22 p. 205 |
| `const.bolt_us.1_1_8.std` | 1-1/4 in | d + 1/8 | AISC 360-22 p. 205 |
| `const.bolt_us.1_2.lsl_l` | 1-1/4 in | 1-1/4 | AISC 360-22 p. 205, from the page image |
| `const.bolt_us.1_2.lsl_w` | 9/16 in | 9/16 | AISC 360-22 p. 205 |
| `const.bolt_us.1_2.ovs` | 5/8 in | 5/8 | AISC 360-22 p. 205 |
| `const.bolt_us.1_2.ssl_l` | 11/16 in | 11/16 | AISC 360-22 p. 205 |
| `const.bolt_us.1_2.ssl_w` | 9/16 in | 9/16 | AISC 360-22 p. 205 |
| `const.bolt_us.1_2.std` | 9/16 in | 9/16 | AISC 360-22 p. 205 |
| `const.bolt_us.1_3_8.lsl_l` | 3-7/16 in | 2.5 d | AISC 360-22 p. 205 |
| `const.bolt_us.1_3_8.lsl_w` | 1-1/2 in | d + 1/8 | AISC 360-22 p. 205 |
| `const.bolt_us.1_3_8.ovs` | 1-11/16 in | d + 5/16 | AISC 360-22 p. 205 |
| `const.bolt_us.1_3_8.ssl_l` | 1-3/4 in | d + 3/8 | AISC 360-22 p. 205 |
| `const.bolt_us.1_3_8.ssl_w` | 1-1/2 in | d + 1/8 | AISC 360-22 p. 205 |
| `const.bolt_us.1_3_8.std` | 1-1/2 in | d + 1/8 | AISC 360-22 p. 205 |
| `const.bolt_us.3_4.lsl_l` | 1-7/8 in | 1-7/8 | AISC 360-22 p. 205, from the page image |
| `const.bolt_us.3_4.lsl_w` | 13/16 in | 13/16 | AISC 360-22 p. 205 |
| `const.bolt_us.3_4.ovs` | 15/16 in | 15/16 | AISC 360-22 p. 205 |
| `const.bolt_us.3_4.ssl_l` | 1 in | 1 | AISC 360-22 p. 205 |
| `const.bolt_us.3_4.ssl_w` | 13/16 in | 13/16 | AISC 360-22 p. 205 |
| `const.bolt_us.3_4.std` | 13/16 in | 13/16 | AISC 360-22 p. 205 |
| `const.bolt_us.5_8.lsl_l` | 1-9/16 in | 1-9/16 | AISC 360-22 p. 205, from the page image |
| `const.bolt_us.5_8.lsl_w` | 11/16 in | 11/16 | AISC 360-22 p. 205 |
| `const.bolt_us.5_8.ovs` | 13/16 in | 13/16 | AISC 360-22 p. 205 |
| `const.bolt_us.5_8.ssl_l` | 7/8 in | 7/8 | AISC 360-22 p. 205 |
| `const.bolt_us.5_8.ssl_w` | 11/16 in | 11/16 | AISC 360-22 p. 205 |
| `const.bolt_us.5_8.std` | 11/16 in | 11/16 | AISC 360-22 p. 205 |
| `const.bolt_us.7_8.lsl_l` | 2-3/16 in | 2-3/16 | AISC 360-22 p. 205, from the page image |
| `const.bolt_us.7_8.lsl_w` | 15/16 in | 15/16 | AISC 360-22 p. 205 |
| `const.bolt_us.7_8.ovs` | 1-1/16 in | 1-1/16 | AISC 360-22 p. 205, from the page image |
| `const.bolt_us.7_8.ssl_l` | 1-1/8 in | 1-1/8 | AISC 360-22 p. 205, from the page image |
| `const.bolt_us.7_8.ssl_w` | 15/16 in | 15/16 | AISC 360-22 p. 205 |
| `const.bolt_us.7_8.std` | 15/16 in | 15/16 | AISC 360-22 p. 205 |

### J3.4

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc360.j3_4.spacing_ratio` | 8/3 | 2-2/3 | AISC 360-22 p. 206, from the page image |

### J3.5

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `code.c2_rows` | up to 7/8 in; 1 in; 1-1/8 in and over in | 1/8 | AISC 360-22 p. 208 |
| `code.edge_large` | 1.25 d in | 1-1/4 d | AISC 360-22 p. 207, from the page image |
| `const.aisc360.j3_5.c2_lsl` | 0.75 | 3/4 d | AISC 360-22 p. 208 |
| `const.bolt_us.1.c2_ovs` | 1/8 in | 1/8 | AISC 360-22 p. 208 |
| `const.bolt_us.1.c2_ssl` | 1/8 in | 1/8 | AISC 360-22 p. 208 |
| `const.bolt_us.1.edge_min` | 1-1/4 in | 1-1/4 | AISC 360-22 p. 207, from the page image |
| `const.bolt_us.1_1_2.c2_ovs` | 1/8 in | 1/8 | AISC 360-22 p. 208 |
| `const.bolt_us.1_1_2.c2_ssl` | 3/16 in | 3/16 | AISC 360-22 p. 208 |
| `const.bolt_us.1_1_2.edge_min` | 1-7/8 in | 1-1/4 d | AISC 360-22 p. 207, from the page image |
| `const.bolt_us.1_1_4.c2_ovs` | 1/8 in | 1/8 | AISC 360-22 p. 208 |
| `const.bolt_us.1_1_4.c2_ssl` | 3/16 in | 3/16 | AISC 360-22 p. 208 |
| `const.bolt_us.1_1_4.edge_min` | 1-5/8 in | 1-5/8 | AISC 360-22 p. 207, from the page image |
| `const.bolt_us.1_1_8.c2_ovs` | 1/8 in | 1/8 | AISC 360-22 p. 208 |
| `const.bolt_us.1_1_8.c2_ssl` | 3/16 in | 3/16 | AISC 360-22 p. 208 |
| `const.bolt_us.1_1_8.edge_min` | 1-1/2 in | 1-1/2 | AISC 360-22 p. 207, from the page image |
| `const.bolt_us.1_2.c2_ovs` | 1/16 in | 1/16 | AISC 360-22 p. 208 |
| `const.bolt_us.1_2.c2_ssl` | 1/8 in | 1/8 | AISC 360-22 p. 208 |
| `const.bolt_us.1_2.edge_min` | 3/4 in | 3/4 | AISC 360-22 p. 207 |
| `const.bolt_us.1_3_8.c2_ovs` | 1/8 in | 1/8 | AISC 360-22 p. 208 |
| `const.bolt_us.1_3_8.c2_ssl` | 3/16 in | 3/16 | AISC 360-22 p. 208 |
| `const.bolt_us.1_3_8.edge_min` | 1-23/32 in | 1-1/4 d | AISC 360-22 p. 207, from the page image |
| `const.bolt_us.3_4.c2_ovs` | 1/16 in | 1/16 | AISC 360-22 p. 208 |
| `const.bolt_us.3_4.c2_ssl` | 1/8 in | 1/8 | AISC 360-22 p. 208 |
| `const.bolt_us.3_4.edge_min` | 1 in | 1 | AISC 360-22 p. 207 |
| `const.bolt_us.5_8.c2_ovs` | 1/16 in | 1/16 | AISC 360-22 p. 208 |
| `const.bolt_us.5_8.c2_ssl` | 1/8 in | 1/8 | AISC 360-22 p. 208 |
| `const.bolt_us.5_8.edge_min` | 7/8 in | 7/8 | AISC 360-22 p. 207 |
| `const.bolt_us.7_8.c2_ovs` | 1/16 in | 1/16 | AISC 360-22 p. 208 |
| `const.bolt_us.7_8.c2_ssl` | 1/8 in | 1/8 | AISC 360-22 p. 208 |
| `const.bolt_us.7_8.edge_min` | 1-1/8 in | 1-1/8 | AISC 360-22 p. 207, from the page image |

### J3.6

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc360.j3_6.edge_max` | 6 in | 6 | AISC 360-22 p. 208 |
| `const.aisc360.j3_6.edge_t` | 12 | 12 | AISC 360-22 p. 208 |
| `const.aisc360.j3_6.pitch_max` | 12 in | 12 | AISC 360-22 p. 208 |
| `const.aisc360.j3_6.pitch_t` | 24 | 24 | AISC 360-22 p. 208 |
| `const.aisc360.j3_6.weathering_pitch_max` | 7 in | 7 | AISC 360-22 p. 208 |
| `const.aisc360.j3_6.weathering_pitch_t` | 14 | 14 | AISC 360-22 p. 208 |

### J3.7

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `bolt_group.120.Fnt` | 90 ksi | 90 | AISC 360-22 p. 205 |
| `bolt_group.120.Fnv_N` | 54 ksi | 54 | AISC 360-22 p. 205 |
| `bolt_group.120.Fnv_X` | 68 ksi | 68 | AISC 360-22 p. 205 |
| `bolt_group.144.Fnt` | 108 ksi | 108 | AISC 360-22 p. 205 |
| `bolt_group.144.Fnv_N` | 65 ksi | 65 | AISC 360-22 p. 205 |
| `bolt_group.144.Fnv_X` | 81 ksi | 81 | AISC 360-22 p. 205 |
| `bolt_group.150.Fnt` | 113 ksi | 113 | AISC 360-22 p. 205 |
| `bolt_group.150.Fnv_N` | 68 ksi | 68 | AISC 360-22 p. 205 |
| `bolt_group.150.Fnv_X` | 84 ksi | 84 | AISC 360-22 p. 205 |
| `bolt_group.200.Fnt` | 150 ksi | 150 | AISC 360-22 p. 205 |
| `bolt_group.200.Fnv_N` | 90 ksi | 90 | AISC 360-22 p. 205 |
| `bolt_group.200.Fnv_X` | 113 ksi | 113 | AISC 360-22 p. 205 |
| `bolt_group.A307.Fnt` | 45 ksi | 45 | AISC 360-22 p. 205 |
| `bolt_group.A307.Fnv_N` | 27 ksi | 27 | AISC 360-22 p. 205 |
| `code.bolt_area` | Ab = pi d^2 / 4 | Ab, the area of the bolt's unthreaded body | AISC 360-22 p. 209 |
| `const.rcsc2025.s5_1.omega` | 2 | 2.00 | AISC 360-22 p. 209 |
| `const.rcsc2025.s5_1.phi` | 0.75 | 0.75 | AISC 360-22 p. 209 |
| `eq.aisc360.J3-1` | `bolt_shear, bolt_tension` | Rn = Fn Ab | AISC 360-22 p. 209 |

### J3.8

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc360.j3_8.exemption` | 0.3 | 30% | AISC 360-22 p. 210 |
| `const.aisc360.j3_8.intercept` | 1.3 | 1.3 | AISC 360-22 p. 209, from the page image |
| `eq.aisc360.J3-3a` | `combined_fnt` | F'nt = 1.3 Fnt - (Fnt / (phi Fnv)) frv <= Fnt | AISC 360-22 p. 209, from the page image |
| `eq.aisc360.J3-3b` | `combined_fnt` | F'nt = 1.3 Fnt - (Omega Fnt / Fnv) frv <= Fnt | AISC 360-22 p. 209, from the page image |

### J3.9

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `code.tm_definition` | Tm = 0.70 Fu As | 0.70 | AISC 360-22 p. 204 |
| `const.rcsc2025.s5_4.Du` | 1.13 | 1.13 | AISC 360-22 p. 210 |
| `const.rcsc2025.s5_4.hf_one` | 1 | 1.0 | AISC 360-22 p. 210 |
| `const.rcsc2025.s5_4.hf_two` | 0.85 | 0.85 | AISC 360-22 p. 210 |
| `const.rcsc2025.s5_4.mu_a` | 0.3 | 0.30 | AISC 360-22 p. 210 |
| `const.rcsc2025.s5_4.mu_b` | 0.5 | 0.50 | AISC 360-22 p. 211 |
| `const.rcsc2025.s5_4.omega_lsl` | 2.14 | 2.14 | AISC 360-22 p. 210 |
| `const.rcsc2025.s5_4.omega_ovs` | 1.76 | 1.76 | AISC 360-22 p. 210 |
| `const.rcsc2025.s5_4.omega_std` | 1.5 | 1.50 | AISC 360-22 p. 210 |
| `const.rcsc2025.s5_4.phi_lsl` | 0.7 | 0.70 | AISC 360-22 p. 210 |
| `const.rcsc2025.s5_4.phi_ovs` | 0.85 | 0.85 | AISC 360-22 p. 210 |
| `const.rcsc2025.s5_4.phi_std` | 1 | 1.00 | AISC 360-22 p. 210 |
| `eq.aisc360.J3-4` | `slip` | Rn = mu Du hf Tb ns | AISC 360-22 p. 210 |

### J3.10

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `code.ksc_lrfd` | 1 | 1 | AISC 360-22 p. 211, from the page image |
| `const.aisc360.j3_10.ksc_asd` | 1.5 | 1.5 | AISC 360-22 p. 211, from the page image |
| `eq.aisc360.J3-5a` | `slip_ksc` | ksc = 1 - Tu / (Du Tb nb) >= 0 | AISC 360-22 p. 211, from the page image |
| `eq.aisc360.J3-5b` | `slip_ksc` | ksc = 1 - 1.5 Ta / (Du Tb nb) >= 0 | AISC 360-22 p. 211, from the page image |

### J3.11a

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc360.j3_11a.bearing_considered` | 2.4 | 2.4 | AISC 360-22 p. 211 |
| `const.aisc360.j3_11a.bearing_lsl_perpendicular` | 2 | 2.0 | AISC 360-22 p. 212 |
| `const.aisc360.j3_11a.bearing_not_considered` | 3 | 3.0 | AISC 360-22 p. 211 |
| `const.aisc360.j3_11a.tearout_considered` | 1.2 | 1.2 | AISC 360-22 p. 212 |
| `const.aisc360.j3_11a.tearout_lsl_perpendicular` | 1 | 1.0 | AISC 360-22 p. 212 |
| `const.aisc360.j3_11a.tearout_not_considered` | 1.5 | 1.5 | AISC 360-22 p. 212 |
| `const.rcsc2025.s5_3.omega` | 2 | 2.00 | AISC 360-22 p. 211 |
| `const.rcsc2025.s5_3.phi` | 0.75 | 0.75 | AISC 360-22 p. 211 |
| `eq.aisc360.J3-6a` | `bearing` | Rn = 2.4 d t Fu | AISC 360-22 p. 211 |
| `eq.aisc360.J3-6b` | `bearing` | Rn = 3.0 d t Fu | AISC 360-22 p. 211 |
| `eq.aisc360.J3-6c` | `tearout` | Rn = 1.2 lc t Fu | AISC 360-22 p. 212 |
| `eq.aisc360.J3-6d` | `tearout` | Rn = 1.5 lc t Fu | AISC 360-22 p. 212 |
| `eq.aisc360.J3-6e` | `bearing` | Rn = 2.0 d t Fu | AISC 360-22 p. 212 |
| `eq.aisc360.J3-6f` | `tearout` | Rn = 1.0 lc t Fu | AISC 360-22 p. 212 |

### J4.1

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc360.j4_1.omega_r` | 2 | 2.00 | AISC 360-22 p. 213 |
| `const.aisc360.j4_1.omega_y` | 1.67 | 1.67 | AISC 360-22 p. 213 |
| `const.aisc360.j4_1.phi_r` | 0.75 | 0.75 | AISC 360-22 p. 213 |
| `const.aisc360.j4_1.phi_y` | 0.9 | 0.90 | AISC 360-22 p. 213 |
| `eq.aisc360.J4-1` | `tension_yield` | Rn = Fy Ag | AISC 360-22 p. 213 |
| `eq.aisc360.J4-2` | `tension_rupture` | Rn = Fu Ae | AISC 360-22 p. 213 |

### J4.2

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc360.j4_2.omega_r` | 2 | 2.00 | AISC 360-22 p. 214 |
| `const.aisc360.j4_2.omega_y` | 1.5 | 1.50 | AISC 360-22 p. 213 |
| `const.aisc360.j4_2.phi_r` | 0.75 | 0.75 | AISC 360-22 p. 214 |
| `const.aisc360.j4_2.phi_y` | 1 | 1.00 | AISC 360-22 p. 213 |
| `const.aisc360.j4_2.shear` | 0.6 | 0.60 | AISC 360-22 p. 213 |
| `eq.aisc360.J4-3` | `shear_yield` | Rn = 0.60 Fy Agv | AISC 360-22 p. 213 |
| `eq.aisc360.J4-4` | `shear_rupture` | Rn = 0.60 Fu Anv | AISC 360-22 p. 214 |

### J4.3

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `code.ubs_uniform` | 1 | 1 | AISC 360-22 p. 214 |
| `const.aisc360.j4_3.omega` | 2 | 2.00 | AISC 360-22 p. 214 |
| `const.aisc360.j4_3.phi` | 0.75 | 0.75 | AISC 360-22 p. 214 |
| `const.aisc360.j4_3.shear` | 0.6 | 0.60 | AISC 360-22 p. 214, from the page image |
| `const.aisc360.j4_3.ubs_nonuniform` | 0.5 | 0.5 | AISC 360-22 p. 214 |
| `eq.aisc360.J4-5` | `block_shear` | Rn = 0.60 Fu Anv + Ubs Fu Ant <= 0.60 Fy Agv + Ubs Fu Ant | AISC 360-22 p. 214, from the page image |

### J4.4

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc360.j4_4.omega` | 1.67 | 1.67 | AISC 360-22 p. 214 |
| `const.aisc360.j4_4.phi` | 0.9 | 0.90 | AISC 360-22 p. 214 |
| `eq.aisc360.J4-6` | `compression` | Pn = Fy Ag | AISC 360-22 p. 214 |

### J4.5

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc360.j4_5.omega_r` | 2 | 2.00 | AISC 360-22 p. 577, from the page image |
| `const.aisc360.j4_5.omega_y` | 1.67 | 1.67 | AISC 360-22 p. 120 |
| `const.aisc360.j4_5.phi_r` | 0.75 | 0.75 | AISC 360-22 p. 577 |
| `const.aisc360.j4_5.phi_y` | 0.9 | 0.90 | AISC 360-22 p. 120 |

### J5.2

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc360.j5_2.floor` | 0.85 | 0.85 | AISC 360-22 p. 215 |

### J7

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc360.j7.milled` | 1.8 | 1.8 | AISC 360-22 p. 216 |
| `const.aisc360.j7.omega` | 2 | 2.00 | AISC 360-22 p. 216 |
| `const.aisc360.j7.phi` | 0.75 | 0.75 | AISC 360-22 p. 216 |
| `eq.aisc360.J7-1` | `bearing_milled` | Rn = 1.8 Fy Apb | AISC 360-22 p. 216 |

### J10.1

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `code.j10_1_end_half` | 1/2 | 50% | AISC 360-22 p. 218 |
| `const.aisc360.j10_1.coefficient` | 6.25 | 6.25 | AISC 360-22 p. 218, from the page image |
| `const.aisc360.j10_1.end_distance` | 10 | 10 | AISC 360-22 p. 218 |
| `const.aisc360.j10_1.omega` | 1.67 | 1.67 | AISC 360-22 p. 218 |
| `const.aisc360.j10_1.phi` | 0.9 | 0.90 | AISC 360-22 p. 218 |
| `eq.aisc360.J10-1` | `flange_local_bending` | Rn = 6.25 Fyf tf^2 | AISC 360-22 p. 218, from the page image |

### J10.2

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `code.j10_2_end` | d | d | AISC 360-22 p. 219, from the page image |
| `const.aisc360.j10_2.end` | 2.5 | 2.5 | AISC 360-22 p. 219, from the page image |
| `const.aisc360.j10_2.interior` | 5 | 5 | AISC 360-22 p. 219, from the page image |
| `const.aisc360.j10_2.omega` | 1.5 | 1.50 | AISC 360-22 p. 219 |
| `const.aisc360.j10_2.phi` | 1 | 1.00 | AISC 360-22 p. 219 |
| `const.petra.strict.length` | 0.000001 in |  | absent: Petra's own value; no standard states it |
| `eq.aisc360.J10-2` | `web_local_yielding` | Rn = Fyw tw (5k + lb) | AISC 360-22 p. 219, from the page image |
| `eq.aisc360.J10-3` | `web_local_yielding` | Rn = Fyw tw (2.5k + lb) | AISC 360-22 p. 219, from the page image |

### J10.3

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `code.j10_3_end` | d/2 | d/2 | AISC 360-22 p. 219, from the page image |
| `const.aisc360.j10_3.bearing` | 3 | 3 | AISC 360-22 p. 219, from the page image |
| `const.aisc360.j10_3.end` | 0.4 | 0.40 | AISC 360-22 p. 219, from the page image |
| `const.aisc360.j10_3.interior` | 0.8 | 0.80 | AISC 360-22 p. 219, from the page image |
| `const.aisc360.j10_3.long_bearing` | 4 | 4 | AISC 360-22 p. 220, from the page image |
| `const.aisc360.j10_3.long_offset` | 0.2 | 0.2 | AISC 360-22 p. 220, from the page image |
| `const.aisc360.j10_3.omega` | 2 | 2.00 | AISC 360-22 p. 219 |
| `const.aisc360.j10_3.phi` | 0.75 | 0.75 | AISC 360-22 p. 219 |
| `eq.aisc360.J10-4` | `web_crippling` | Rn = 0.80 tw^2 [1 + 3 (lb/d)(tw/tf)^1.5] sqrt(E Fyw tf / tw) Qf | AISC 360-22 p. 219, from the page image |
| `eq.aisc360.J10-5a` | `web_crippling` | Rn = 0.40 tw^2 [1 + 3 (lb/d)(tw/tf)^1.5] sqrt(E Fyw tf / tw) Qf | AISC 360-22 p. 219, from the page image |
| `eq.aisc360.J10-5b` | `web_crippling` | Rn = 0.40 tw^2 [1 + (4 lb/d - 0.2)(tw/tf)^1.5] sqrt(E Fyw tf / tw) Qf | AISC 360-22 p. 220, from the page image |

### J10.4

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc360.j10_4.coefficient` | 0.4 | 0.4 | AISC 360-22 p. 220, from the page image |
| `const.aisc360.j10_4.cr_at_my` | 480000 ksi | 480,000 | AISC 360-22 p. 221 |
| `const.aisc360.j10_4.cr_below_my` | 960000 ksi | 960,000 | AISC 360-22 p. 221 |
| `const.aisc360.j10_4.omega` | 1.76 | 1.76 | AISC 360-22 p. 220 |
| `const.aisc360.j10_4.phi` | 0.85 | 0.85 | AISC 360-22 p. 220 |
| `const.aisc360.j10_4.restrained_limit` | 2.3 | 2.3 | AISC 360-22 p. 220, from the page image |
| `const.aisc360.j10_4.unrestrained_limit` | 1.7 | 1.7 | AISC 360-22 p. 220, from the page image |
| `eq.aisc360.J10-6` | `web_sidesway` | Rn = (Cr tw^3 tf / h^2) [1 + 0.4 ((h/tw)/(Lb/bf))^3] | AISC 360-22 p. 220, from the page image |
| `eq.aisc360.J10-7` | `web_sidesway` | Rn = (Cr tw^3 tf / h^2) [0.4 ((h/tw)/(Lb/bf))^3] | AISC 360-22 p. 220, from the page image |

### J10.5

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `code.j10_5_end_half` | 1/2 | 50% | AISC 360-22 p. 221 |
| `const.aisc360.j10_5.coefficient` | 24 | 24 | AISC 360-22 p. 221, from the page image |
| `const.aisc360.j10_5.omega` | 1.67 | 1.67 | AISC 360-22 p. 221 |
| `const.aisc360.j10_5.phi` | 0.9 | 0.90 | AISC 360-22 p. 221 |
| `eq.aisc360.J10-8` | `web_compression_buckling` | Rn = (24 tw^3 sqrt(E Fyw) / h) Qf | AISC 360-22 p. 221, from the page image |

### J10.6

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `code.panel_alpha_lrfd` | 1.0 | 1.0 | AISC 360-22 p. 222 |
| `code.panel_zone_threshold` | 0.4 | 0.4 | AISC 360-22 p. 222 |
| `const.aisc360.j10_6.alpha_asd` | 1.6 | 1.6 | AISC 360-22 p. 222 |
| `const.aisc360.j10_6.coefficient` | 0.6 | 0.60 | AISC 360-22 p. 222 |
| `const.aisc360.j10_6.intercept` | 1.4 | 1.4 | AISC 360-22 p. 222, from the page image |
| `const.aisc360.j10_6.omega` | 1.67 | 1.67 | AISC 360-22 p. 222 |
| `const.aisc360.j10_6.phi` | 0.9 | 0.90 | AISC 360-22 p. 222 |
| `eq.aisc360.J10-10` | `panel_zone` | Rn = 0.60 Fy dc tw (1.4 - alpha Pr / Py) | AISC 360-22 p. 222, from the page image |
| `eq.aisc360.J10-9` | `panel_zone` | Rn = 0.60 Fy dc tw | AISC 360-22 p. 222 |

### App. 3.1

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc360.app3.cycles_min` | 20000 | 20,000 | AISC 360-22 p. 272 |
| `const.aisc360.app3.peak` | 0.66 | 0.66 | AISC 360-22 p. 272 |

### App. 3.2

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `code.section_stress` | M / S + 3 V / (2 t d) | elastic analysis, no stress concentration factor | AISC 360-22 p. 273 |

### App. 3.3a

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc360.app3.a3_1` | 1000 ksi | 1,000 | AISC 360-22 p. 273, from the page image |
| `const.aisc360.app3.a3_1_exponent` | 0.333 | 0.333 | AISC 360-22 p. 273, from the page image |
| `const.aisc360.app3.cat_b.cf` | 12 | 12 | AISC 360-22 p. 280 |
| `const.aisc360.app3.cat_b.fth` | 16 ksi | 16 | AISC 360-22 p. 280 |
| `const.aisc360.app3.cat_c.cf` | 4.4 | 4.4 | AISC 360-22 p. 278 |
| `const.aisc360.app3.cat_c.fth` | 10 ksi | 10 | AISC 360-22 p. 278 |
| `const.aisc360.app3.cat_e_prime.cf` | 0.39 | 0.39 | AISC 360-22 p. 278 |
| `const.aisc360.app3.cat_e_prime.fth` | 2.6 ksi | 2.6 | AISC 360-22 p. 278 |
| `const.aisc360.app3.cat_g.cf` | 0.39 | 0.39 | AISC 360-22 p. 296 |
| `const.aisc360.app3.cat_g.fth` | 7 ksi | 7 | AISC 360-22 p. 296 |
| `eq.aisc360.A-3-1` | `fsr` | FSR = 1,000 (Cf / nSR)^0.333 >= FTH | AISC 360-22 p. 273, from the page image |

### App. 3.3b

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc360.app3.a3_2` | 100 ksi | 100 | AISC 360-22 p. 273, from the page image |
| `const.aisc360.app3.a3_2_cf` | 1.5 | 1.5 | AISC 360-22 p. 273, from the page image |
| `const.aisc360.app3.a3_2_exponent` | 0.167 | 0.167 | AISC 360-22 p. 273, from the page image |
| `const.aisc360.app3.a3_2_threshold` | 8 ksi | 8 | AISC 360-22 p. 273, from the page image |
| `eq.aisc360.A-3-2` | `fsr_f` | FSR = 100 (1.5 / nSR)^0.167 >= 8 ksi | AISC 360-22 p. 273, from the page image |

### App. 3.3c

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc360.app3.a3_1_exponent` | 0.333 | 0.333 | AISC 360-22 p. 273, from the page image |
| `const.aisc360.app3.a3_6_exponent` | 0.167 | 0.167 | AISC 360-22 p. 275, from the page image |
| `const.aisc360.app3.a3_6_intercept` | 0.06 | 0.06 | AISC 360-22 p. 275, from the page image |
| `const.aisc360.app3.a3_6_slope` | 0.72 | 0.72 | AISC 360-22 p. 275, from the page image |
| `eq.aisc360.A-3-5` | `fsr_root` | FSR = 1,000 RFIL (4.4 / nSR)^0.333 | AISC 360-22 p. 275, from the page image |
| `eq.aisc360.A-3-6` | `rfil` | RFIL = (0.06 + 0.72 (w / tp)) / tp^0.167 <= 1.0 | AISC 360-22 p. 275, from the page image |

### App. 3.4b

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc360.app3.a3_7_thread` | 0.9743 | 0.9743 | AISC 360-22 p. 275, from the page image |
| `const.aisc360.app3.s3_4_share` | 0.2 | 20% | AISC 360-22 p. 276 |
| `eq.aisc360.A-3-7` | `tensile_stress_area` | At = (pi / 4) (db - 0.9743 / n)^2 | AISC 360-22 p. 275, from the page image |

### RCSC 4

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.rcsc2025.joint_level.pretensioned` | 1 |  | absent: Petra's own value; no standard states it |
| `const.rcsc2025.joint_level.slip_critical` | 2 |  | absent: Petra's own value; no standard states it |
| `const.rcsc2025.joint_level.snug` | 0 |  | absent: Petra's own value; no standard states it |

### Manual Part 1

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.shop_deck.plate.t1` | 1 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t1_1_2` | 1-1/2 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t1_1_4` | 1-1/4 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t1_1_8` | 1-1/8 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t1_2` | 1/2 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t1_3_4` | 1-3/4 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t1_3_8` | 1-3/8 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t1_4` | 1/4 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t2` | 2 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t2_1_2` | 2-1/2 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t2_1_4` | 2-1/4 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t2_3_4` | 2-3/4 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t3` | 3 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t3_16` | 3/16 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t3_4` | 3/4 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t3_8` | 3/8 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t5_16` | 5/16 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t5_8` | 5/8 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t7_16` | 7/16 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t7_8` | 7/8 in |  | absent: the Companion states no plate thickness increments |
| `const.shop_deck.plate.t9_16` | 9/16 in |  | absent: the Companion states no plate thickness increments |

### Manual Part 7

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc_manual.clearance.socket` | 1/2 in |  | absent: not stated in the documents on disk; Petra cites AISC Manual 16th ed. Part 7 |
| `const.aisc_manual.p7.ic_delta_max` | 0.34 in |  | absent: the Companion reads C from Manual Table 7-6 and states no load-deformation curve |
| `const.aisc_manual.p7.ic_lambda` | 0.55 |  | absent: the Companion reads C from Manual Table 7-6 and states no load-deformation curve |
| `const.aisc_manual.p7.ic_mu` | 10 |  | absent: the Companion reads C from Manual Table 7-6 and states no load-deformation curve |
| `const.petra.switch.length` | 0.000000000000001 in |  | absent: Petra's own value; no standard states it |

### Manual Part 8

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc_manual.p8.ic_curve_a` | 1.9 |  | absent: the Companion reads C from Manual Table 8-4 or 8-8 and states no load-deformation curve |
| `const.aisc_manual.p8.ic_curve_b` | 0.9 |  | absent: the Companion reads C from Manual Table 8-4 or 8-8 and states no load-deformation curve |
| `const.aisc_manual.p8.ic_curve_power` | 0.3 |  | absent: the Companion reads C from Manual Table 8-4 or 8-8 and states no load-deformation curve |
| `const.aisc_manual.p8.ic_delta_m` | 0.209 |  | absent: the Companion reads C from Manual Table 8-4 or 8-8 and states no load-deformation curve |
| `const.aisc_manual.p8.ic_delta_m_offset` | 2 |  | absent: the Companion reads C from Manual Table 8-4 or 8-8 and states no load-deformation curve |
| `const.aisc_manual.p8.ic_delta_m_power` | 0.32 |  | absent: the Companion reads C from Manual Table 8-4 or 8-8 and states no load-deformation curve |
| `const.aisc_manual.p8.ic_delta_u` | 1.087 |  | absent: the Companion reads C from Manual Table 8-4 or 8-8 and states no load-deformation curve |
| `const.aisc_manual.p8.ic_delta_u_cap` | 0.17 |  | absent: the Companion reads C from Manual Table 8-4 or 8-8 and states no load-deformation curve |
| `const.aisc_manual.p8.ic_delta_u_offset` | 6 |  | absent: the Companion reads C from Manual Table 8-4 or 8-8 and states no load-deformation curve |
| `const.aisc_manual.p8.ic_delta_u_power` | 0.65 |  | absent: the Companion reads C from Manual Table 8-4 or 8-8 and states no load-deformation curve |
| `const.petra.switch.length` | 0.000000000000001 in |  | absent: Petra's own value; no standard states it |
| `const.petra.weld_ic.a_min` | 0.125 |  | absent: Petra's own value; no standard states it |
| `const.petra.weld_ic.along_peak` | 1.04 |  | absent: Petra's own value; no standard states it |
| `const.petra.weld_ic.k_max` | 2 |  | absent: Petra's own value; no standard states it |

### Manual Part 9

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc_manual.p9.a_limit` | 1.25 | 1.25 | Companion vol. 1 p. 919 |
| `const.aisc_manual.p9.cb_intercept` | 3 | 3 | Companion vol. 1 p. 638 |
| `const.aisc_manual.p9.cb_min` | 1.84 | 1.84 | Companion vol. 1 p. 638 |
| `const.aisc_manual.p9.cope_depth` | 0.5 |  | absent: not stated in the documents on disk; Petra cites AISC Manual 16th ed. Part 9 |
| `const.aisc_manual.p9.cope_length` | 2 |  | absent: not stated in the documents on disk; Petra cites AISC Manual 16th ed. Part 9 |
| `const.aisc_manual.p9.k1_min` | 1.61 | 1.61 | Companion vol. 1 p. 612 |
| `const.aisc_manual.p9.k_coefficient` | 2.2 | 2.2 | Companion vol. 1 p. 612 |
| `const.aisc_manual.p9.k_exponent` | 1.65 | 1.65 | Companion vol. 1 p. 612 |
| `const.aisc_manual.p9.lambda_p` | 0.475 | 0.475 | Companion vol. 1 p. 612, from the page image |
| `const.aisc_manual.p9.tc` | 4 | 4 | Companion vol. 1 p. 920 |
| `const.aisc_manual.p9.tee_bolt_cap` | 0.115 | 0.115 | Companion vol. 1 p. 835 |
| `const.aisc_manual.p9.tee_bolt_coefficient` | 0.0941 | 0.0941 | Companion vol. 1 p. 835 |
| `const.aisc_manual.p9.tee_flexibility` | 2 | 2 | Companion vol. 1 p. 842 |
| `const.aisc_manual.p9.tee_stem_allowance` | 1/16 in | 1/16 | Companion vol. 1 p. 835, from the page image |
| `const.aisc_manual.p9.tee_weld_cap` | 0.625 | 5/8 | Companion vol. 1 p. 842, from the page image |
| `const.aisc_manual.p9.tee_weld_coefficient` | 0.0155 | 0.0155 | Companion vol. 1 p. 842 |
| `const.aisc_manual.p9.tributary` | 1.75 | 1.75 | Companion vol. 1 p. 919 |
| `eq.manual.9-10` | `cope_inelastic` |  | absent: no Companion example cites Manual Eq. 9-10 |
| `eq.manual.9-11` | `cope_elastic, cope_inelastic` | Mn = Mp - (Mp - My)(lambda/lambda_p - 1) | Companion vol. 1 p. 613 |
| `eq.manual.9-14` | `cope_k1` | k1 = f k >= 1.61 | Companion vol. 1 p. 612 |
| `eq.manual.9-18` | `cope_lambda_p` | lambda_p = 0.475 sqrt(k1 E / Fy) | Companion vol. 1 p. 612, from the page image |
| `eq.manual.9-19` | `cope_k1` | k = 2.2 (hc/c)^1.65 | Companion vol. 1 p. 612 |
| `eq.manual.9-20` | `cope_k1` | f = 2 (c/d) | Companion vol. 1 p. 612 |
| `eq.manual.9-21` | `double_cope_cb` | Cb = [3 + ln(Lb/d)](1 - dct/d) >= 1.84 | Companion vol. 1 p. 638 |
| `eq.manual.9-30a` | `_row_no_prying` | tc = sqrt(4 Tc b' / (phi_b p Fu)) | Companion vol. 1 p. 920 |
| `eq.manual.9-51` | `tee_flexibility, tee_weld_min` | wmin = 0.0155 (Fy tf^2 / b)(b^2/l^2 + 2) <= (5/8) tsw | Companion vol. 1 p. 842, from the page image |
| `eq.manual.9-52` | `tee_bolt_min, tee_flexibility` | dmin = 0.0941 tf sqrt((Fy p / b)(b^2/l^2 + 2)) <= 0.115 sqrt(Fy tsw) | Companion vol. 1 p. 835 |

### Manual Part 10

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc_manual.p10.conventional_a` | 3-1/2 in |  | absent: not stated in the documents on disk; Petra cites AISC Manual 16th ed. Part 10 |
| `const.aisc_manual.p10.conventional_rows` | 12 |  | absent: not stated in the documents on disk; Petra cites AISC Manual 16th ed. Part 10, Table 10-9 |
| `const.aisc_manual.p10.ductile_allowance` | 1/16 in | 1/16 | Companion vol. 1 p. 715, from the page image |
| `const.aisc_manual.p10.edge_ratio` | 2 | 2 | Companion vol. 1 p. 715 |
| `const.aisc_manual.p10.extended_cb` | 1.84 | 1.84 | Companion vol. 1 p. 750 |
| `const.aisc_manual.p10.fnv_divisor` | 0.9 | 0.90 | Companion vol. 1 p. 747 |
| `const.aisc_manual.p10.underrun` | 1/4 in | 1/4 | Companion vol. 1 p. 614, from the page image |
| `const.aisc_manual.p10.weld_ratio` | 0.625 | 5/8 | Companion vol. 1 p. 715 |
| `const.aisc_manual.seat.critical_offset` | 3/8 in |  | absent: not stated in the documents on disk; Petra cites AISC Manual 16th ed. Part 10 |
| `const.aisc_manual.seat.stiffener_clip` | 1/2 in |  | absent: not stated in the documents on disk; Petra cites AISC Manual 16th ed. Part 10 |
| `const.aisc_manual.t10_6.lever` | 2.25 |  | absent: not stated in the documents on disk; Petra cites AISC Manual 16th ed. Part 10, Table 10-6 |
| `const.aisc_manual.t10_8.eccentricity` | 0.8 |  | absent: not stated in the documents on disk; Petra cites AISC Manual 16th ed. Part 10, Table 10-8 |
| `const.aisc_manual.t10_9.eccentricity` | 0.5 | 2 | Companion vol. 1 p. 714 |
| `const.aisc_manual.t10_9.rows` | 5 |  | absent: not stated in the documents on disk; Petra cites AISC Manual 16th ed. Part 10, Table 10-9 |
| `const.petra.switch.length` | 0.000000000000001 in |  | absent: Petra's own value; no standard states it |

### Manual Part 15

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc_manual.p15.lambda_coefficient` | 5 | 5 | Companion vol. 1 p. 786 |
| `const.aisc_manual.p15.lambda_intercept` | 475 | 475 | Companion vol. 1 p. 786 |
| `const.aisc_manual.p15.lambda_slender` | 1.41 | 1.41 | Companion vol. 1 p. 786 |
| `const.aisc_manual.p15.lambda_slope` | 1120 | 1,120 | Companion vol. 1 p. 786 |
| `const.aisc_manual.p15.q_intercept` | 1.34 | 1.34 | Companion vol. 1 p. 794 |
| `const.aisc_manual.p15.q_slender` | 1.3 | 1.30 | Companion vol. 1 p. 787 |
| `const.aisc_manual.p15.q_slope` | 0.486 | 0.486 | Companion vol. 1 p. 794 |
| `eq.manual.15-13` | `bracket_q_stocky` | Fcr = Fy | Companion vol. 1 p. 786 |
| `eq.manual.15-14` | `bracket_q_stocky` | Fcr = Q Fy | Companion vol. 1 p. 786 |
| `eq.manual.15-15` | `bracket_q_stocky` | Q = 1.34 - 0.486 lambda | Companion vol. 1 p. 794 |
| `eq.manual.15-16` | `bracket_q_slender` | Q = 1.30 / lambda^2 | Companion vol. 1 p. 787 |
| `eq.manual.15-17` | `bracket_section` | a' = a / cos(theta) | Companion vol. 1 p. 784 |
| `eq.manual.15-18` | `bracket_lambda` | lambda = ((b'/t) sqrt(Fy)) / (5 sqrt(475 + 1,120 (b'/a')^2)) | Companion vol. 1 p. 786 |

### Other clauses

These values' clauses name no traced provision, as a member's slenderness limit in Table B4.1a.

| Item | Petra | Printed | Stated at |
|---|---|---|---|
| `const.aisc360.E` | 29000 ksi | 29,000 | AISC 360-22 p. 35 |
| `const.aisc360.b4_1a.case1` | 0.56 | 0.56 | AISC 360-22 p. 89, from the page image |
| `const.aisc360.b4_3b.hole_allowance` | 1/16 in | 1/16 | AISC 360-22 p. 92, from the page image |
| `const.aisc360.f1.cantilever_cb` | 1 | 1.0 | AISC 360-22 p. 120 |
| `const.aisc360.f11.elastic` | 1.9 | 1.9 | AISC 360-22 p. 139, from the page image |
| `const.aisc360.f11.inelastic_intercept` | 1.52 | 1.52 | AISC 360-22 p. 139, from the page image |
| `const.aisc360.f11.inelastic_limit` | 1.9 | 1.9 | AISC 360-22 p. 139, from the page image |
| `const.aisc360.f11.inelastic_slope` | 0.274 | 0.274 | AISC 360-22 p. 139, from the page image |
| `const.aisc360.nu` | 0.3 | 0.3 | AISC 360-22 p. 435 |
| `const.petra.strict.ratio` | 0.000000001 |  | absent: Petra's own value; no standard states it |
| `eq.aisc360.F11-1` | `bar_ltb` | Mn = Mp = Fy Z <= 1.5 Fy Sx | AISC 360-22 p. 139 |
| `eq.aisc360.F11-3` | `bar_ltb` | Mn = Cb [1.52 - 0.274 (Lb d/t^2) Fy/E] My <= Mp | AISC 360-22 p. 139, from the page image |
| `eq.aisc360.F11-4` | `bar_ltb` | Mn = Fcr Sx <= Mp | AISC 360-22 p. 139 |

The Shapes Database gives 240 more values, the dimensions of the deck's W shapes. 240 of them are anchored to their workbook cells.
