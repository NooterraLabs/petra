# Steel connections deck specification, AISC 360-22

Written 2026-11-05. This is the build specification for the steel connections deck, the first domain Petra aims to cover completely. Steel connections came first because, of the decks open to Petra, they have the most designs. A tag in square brackets says how a statement is known: [verified] against its source, [inference] drawn from sources but not checked, or [check sources] and [check method source] for statements still to check.

The deck's symbols and code names are in [steel_glossary.md](steel_glossary.md). The clause traceability table is [steel_traceability.md](steel_traceability.md).

## 0. The claim

> Petra checks every provision of AISC 360-22 Chapters J and K, for every connection type in its catalogue. Every verdict covers the whole tolerance and material range, and every result is re-checkable by the kernel.

The claim covers connections that fabricators and connection engineers design every day, and that AI connection tools are starting to produce.

The niche can be finished completely for three reasons.

- **Forces are signed inputs.** The engineer of record gives the required strengths at each connection, so no building-wide analysis is needed.
- **The rules are free and finite.** Chapters J and K list every limit state in a free document.
- **The kernel's existing rules suffice.** Almost every check is a closed-form inequality over a box, which R4 handles. Load distribution in bolt and weld groups is a linear program, which R1 handles. The first release needs no new kernel rule, with one possible exception that §7 notes.

## 1. Sources

| Source | Role | Access |
|---|---|---|
| AISC 360-22, Chapters J and K, and Chapters B to H for supporting members | The provisions | Free PDF [verified] |
| AISC 360-22 vs 360-16 comparison | Change list. It confirms the 360-22 section numbering used in §4 | Free [verified] |
| AISC Design Examples (Companion), v16 | Ground truth: Chapter J and K examples, plus the Part II connection examples | Free [verified] |
| AISC Shapes Database v16 | Section dimensions | Free [verified] |
| RCSC Specification for Structural Joints Using High-Strength Bolts (2025) | Bolt installation types, joint types, faying surfaces | Free from boltcouncil.org [verified] |
| Kulak, Fisher and Struik, *Guide to Design Criteria for Bolted and Riveted Joints*, 2nd ed. | The research and test data behind the bolt rules. It is the least processed source, and an outside judge (§8) | Free from boltcouncil.org [verified] |
| AISC 303-22 Code of Standard Practice | Fabrication and erection tolerances | [check: free download] |
| AISC Steel Construction Manual, 16th ed., Parts 7 to 15 | Design procedures: prying, eccentric groups, copes, uniform force method, conventional shear-tab configurations | Paid. The deck encodes the methods, not the text, or derives them from the free research they cite |
| AISC Design Guides 1, 4, 16, 29 | Base plates, end plates, bracing connections | [check: free to members only] |
| AWS D1.1 | Prequalified weld details | Paid. Enters as `assumed` premises |
| ACI 318 Chapter 17 | Concrete anchorage | Paid and out of scope. Enters as premises from ICC-ES reports |

## 2. The requirements card (inputs)

| Input | Example | Premise tag |
|---|---|---|
| Required strengths per load combination (LRFD or ASD) | Vu in [0, 62] kips and Tu in [0, 15] kips | `assumed`, signed by the engineer of record |
| Cyclic loads, when fatigue applies (§4a) | V in [2, 10] kips for nSR in [0, 500,000] cycles | `assumed`, signed by the engineer of record |
| Members | W18x50 beam to W14x90 column flange | `sanctioned` (Shapes DB, with hash) |
| Materials | A992 (Fy ≥ 50, Fu ≥ 65 ksi) and A36 plate (36 and 58 ksi) | `sanctioned` (ASTM guaranteed minimums) |
| Bolts | Group 120, 3/4 in., STD holes, threads included, snug-tight | `sanctioned` (Table J3.2), and the joint type per RCSC |
| Welds | E70 fillet, 1/4 in., both sides, 8.5 in. long | Design values. Quality enters as an AWS `assumed` premise |
| Geometry | Bolt pitch, gauges, edge distances, cope size, setback | Design values, with tolerance intervals |
| Tolerances | Hole position, mill under-run, cope cut | From AISC 303 and ASTM A6, as interval premises [check sources] |
| Environment | Indoor dry, or galvanized faying surfaces | `assumed` |

## 3. The connection catalogue (closed list)

Each type is a graph of elements. The graph runs from the supported member, through fasteners, the connecting element and fasteners again, to the supporting member. Coverage generates every limit state for every node and edge (§6).

| Release | Connection type | Limit states (beyond the bolt, weld and element checks every type gets) |
|---|---|---|
| v1.0 | Single-plate (shear tab), conventional and extended | Plate shear yield and rupture, block shear in the plate and the beam web, plate flexure from eccentricity, plate buckling for the extended form, rotational ductility limits, and a weld sized to develop the plate |
| v1.0 | Double angle, bolted-bolted or bolted-welded | Angle shear yield and rupture, block shear, and eccentric weld groups on the outstanding legs |
| v1.0 | Single angle and tee shear connections | Eccentricity on the support side, and tee stem and flange checks |
| v1.0 | Shear end plate | Plate shear, welds to the web, and the bolt group |
| v1.0 | Unstiffened and stiffened seated connections | Seat-angle flexure, web local yielding and crippling (J10), and stiffener and weld checks |
| v1.0 | Coped beams (applies to all of the above) | Block shear and flexural local web buckling at the cope |
| v1.0 | Concentrated forces on the support (J10) | Flange local bending, web local yielding, web crippling, sidesway buckling, compression buckling, panel-zone shear, unframed ends, stiffener and doubler requirements |
| v1.0 | Eccentric bolt and weld groups (brackets) | A bolt group by the instantaneous-centre method or the elastic method, whichever holds more. A bracket plate on edge welded on both faces, and a lapped bracket plate's C-shaped weld, by the instantaneous-centre method or the elastic method, whichever holds more. Every other weld group by the elastic method (§7a) |
| v1.0 | Hangers (tee or angle in tension) | Prying action, flange flexure, and bolt tension plus prying |
| v1.1 | Bracing connections with gusset plates | Whitmore-section yield and buckling (J4.4), block shear, interface forces by the uniform force method, and gusset-to-beam and gusset-to-column welds |
| v1.1 | Flange-plated FR moment connection | Flange plate tension and compression, bolts or welds to the beam flange, and J10 checks on the column |
| v1.1 | Directly welded flange (CJP) FR moment connection | Groove-weld strength (J2.1), J10 checks on the column, and the panel zone |
| v1.1 | Beam and column splices (bolted flange and web plates) | Splice plates per J6 and fillers per J5 |
| v1.1 | Column base plates under axial load | Bearing on concrete (J8), base-plate flexure, anchor rods (J9), and concrete anchorage as a premise |
| v1.2 | End-plate moment connections, flush and extended | Yield-line plate strength, with the governing pattern from the published method. Bolt tension with and without prying [check method source] |
| v1.2 | HSS connections (Chapter K): concentrated forces, truss T, Y, X and K, moment, welds to HSS | All K2 to K5 limit states, with K1 validity limits as validity rows |

## 4. Clause coverage of every section

Coverage is complete when every "shall" in these sections maps to an encoded check, a premise, or an out-of-scope entry with its reason. The section list follows the 360-22 numbering [verified against the AISC comparison document].

| Section | Content | Treatment |
|---|---|---|
| J1 | General provisions: design basis, simple and moment connections, compression members with bearing joints, splices in heavy sections, weld access holes, placement of welds and bolts, bolts with welds, bolts with existing rivets | Encoded as rules and coverage triggers. Heavy-section splice and weld-access-hole geometry are makeability checks. Rivets are out of scope, because v1 has no existing structures. |
| J2 | Welds and welded joints. Groove, fillet, plug and slot welds. Effective areas, size and length limits, and strength, including the new directional-strength factor. Combinations, filler metal, and mixed weld metal | Encoded. Filler metal matching and mixed weld metal become premises. |
| J3.1 to J3.2 | Common and high-strength bolts (Groups 120, 144, 150, 200) | Registry rows and joint-type rules (with RCSC) |
| J3.3 to J3.6 | Holes, minimum spacing, minimum edge distance, maximum spacing and edge distance | Makeability inequalities. Table J3.5's increment C2 is added for oversized and slotted holes. |
| J3.7 to J3.8 | Tension and shear, and combined tension and shear in bearing-type connections | Encoded |
| J3.9 to J3.10 | Slip-critical connections, and combined tension and shear in slip-critical connections | Encoded. The faying-surface class is a premise |
| J3.11 | Bearing and tearout at holes. J3.11a covers snug-tight or pretensioned bolts, and J3.11b covers bolts through an unstiffened box or HSS | Encoded, per hole. A bracket's bolt tears out along its own force. |
| J3.12 to J3.13 | Special fasteners, and wall strength at tension fasteners | Special fasteners are out of scope in v1. Wall strength is encoded for HSS (v1.2) |
| J4.1 to J4.5 | Affected elements in tension, shear, block shear, compression and flexure | Encoded. Block shear is checked on every enumerated path (§6). |
| J5 | Fillers in welded and bolted connections | Encoded (v1.1) |
| J6 | Splices | Encoded (v1.1) |
| J7 | Bearing strength | Encoded |
| J8 | Column bases and bearing on concrete | Encoded (v1.1) |
| J9 | Anchor rods and embedments | Rod strength is encoded. Concrete breakout is a premise (ACI 318 Chapter 17, out of scope). |
| J10.1 to J10.9 | Flanges and webs with concentrated forces | Encoded, with stiffener and doubler requirements as coverage triggers |
| K1 | HSS parameters, effective width, chord-stress interaction, end distance, limits of applicability | Limits of applicability become validity rows (v1.2) |
| K2 to K5 | Concentrated forces on HSS, truss connections, moment connections, and welds to HSS | Encoded (v1.2) |
| B to H as needed | Supporting-member checks, such as the beam web at the connection and the column for J10 | Encoded where a connection check needs them |
| Appendix 3 | Fatigue: cycles, threshold and peak stress, stress ranges, Table A-3.1's categories, bolts in shear and in tension | Encoded for a declared cyclic load (§4a) |

These are excluded outright, and the deck reports each one as a typed UNKNOWN:

- seismic connections (AISC 341, 358)
- fatigue (Appendix 3) where no load case declares a cyclic load. This one is not an UNKNOWN. The readout prints a "not checked" line for each fatigue mode the connection's details would owe, and says that a cyclic load would demand it.
- fire (Appendix 4)
- composite connections (Chapter I)
- existing structures and rivets
- concrete anchorage design

### 4a. Fatigue (Appendix 3)

A load case that names `cycles` on a connection is cyclic. Its other loads on that connection are service loads. Each varies inside its interval, so the interval's width is the load's stress-producing range and its larger end is the peak.

```
load crane {
  on st1 shear in [2 kip, 10 kip]
  on st1 cycles in [0, 500000]
  signed "s.engineer@example.org" source "runway reaction, service loads"
}
```

Under a cyclic case, coverage demands the fatigue mode of every detail on the load path (`petra/models/steel/cyclic.py`).

| Detail | Table A-3.1 | Mode |
|---|---|---|
| Plies of a slip-critical bolted joint, gross section | Case 2.1, category B | `fatigue_bolted` |
| Plies of a pretensioned bolted joint, net section | Case 2.2, category B | `fatigue_bolted` |
| Bolts in tension, on the tensile stress area | Case 8.5, category G | `fatigue_bolt_tension` |
| Shear on a fillet's throat | Case 8.2, category F | `fatigue_weld` |
| A plate's end welded with a fillet on each face, at the toe and the root | Case 5.7, C and C'' | `fatigue_weld_end` |
| The bottom cope's corner of a beam coped at both flanges | Case 1.3, category E' | `fatigue_cope` |

Each check holds the stress range to FSR, and the stress from the peak load to 0.66 Fy. FSR follows the finite-life formula down to the category's threshold FTH. Each check is excused at 20,000 cycles or fewer. A joint under a cyclic load must be pretensioned (J3.2, RCSC 4.2), so `joint_type` fails a snug-tight one.

A detail the deck draws but whose category it does not encode requires the unmodelled `fatigue_detail` mode, so the verdict is UNKNOWN. These details are a single fillet at an angle's or a tee's toe, a plate welded on one face, a lapped plate's C-shaped fillet, a seat angle, a hanger's tee, and a member's flange under a tensile force. `examples/steel/shear_tab_cyclic.petra` is a cyclic design that passes. [steel_traceability.md](steel_traceability.md) maps every Appendix 3 provision.

## 5. Makeability checks

| Check | Source | How |
|---|---|---|
| Hole sizes, minimum spacing, edge distances, maximum spacing | J3.3 to J3.6 | Linear inequalities (R4) |
| Room to enter and tighten each bolt | Wrench and socket clearance geometry | Exact rational geometry, with the clashing point as the witness (expressed as R4 inequalities) |
| Weld access and torch angle | Joint geometry | Geometry inequalities |
| Fillet size limits, with the minimum by thickness and the maximum along edges | J2.2b | Inequalities |
| Cope and weld-access-hole geometry | J1.6 | Inequalities |
| Stock plate thicknesses and bolt lengths | Shop deck | Catalogue membership |
| Installation type matches the joint type | RCSC | Rule check |
| Fit of the drawn parts. Each part lies on the member it bears on, and the beam clears its support | Manual Part 1 (T) and geometry | Exact rational containment, one R4 term per fit (`beam_fit`, `flange_fit`, `web_fit`) |

J3.5 holds each bolt Table J3.4's distance, plus Table J3.5's C2, from every edge of the part it passes through. On a beam web the deck reads the beam end and a top cope's cut above the top row. Since 2026-11-08 it also reads a bottom cope's cut below the bottom row, for a beam coped at both flanges. Before that, the gate's single angle gate-1-05546 passed with its bottom bolt 0.7 in above the cut (measured), where Table J3.4 asks 1-1/8 in. J3.6's maximum is to a bolt's nearest edge. The beam end's own limit already bounds it, so the bottom cope takes no maximum.

### 5a. Fit of the drawn parts

`petra/models/steel/geometry.py` places each kind's parts in one frame per connection, in exact rationals over the design's hypotheses. The module is trusted and is in the premise hash. The frame has three axes. Depth runs down from the beam's top, out runs from the support face along the beam, and across runs over the support face. A part is a span on an axis, and a room is where spans must lie. Each containment is one check, `need <= have` in inches, excused where its guard is at most zero. Each check prints its numbers like any other check, so a FAIL names the part, the room and both lengths.

| Mode | Demanded by | What it checks |
|---|---|---|
| `beam_fit` | every beam web on the load path | A plate, angle or tee bolted to the beam web lies on the flat web, T deep and centred, from (d - T)/2 to (d + T)/2. A cope at least (d - T)/2 deep frees the edge at its flange when the cope runs past the part's far edge. The beam's holes lie on the flat web below and above the copes. An end plate's welds fit the flat web the copes leave. The beam end clears the support face for a tab or angles, and the tee's flange for a tee. A seated beam's end lands on the seat angle or the stiffener. |
| `flange_fit` | a support met on its flange | A pair of bolt lines centred at the gauge lies on the flange and clears the web between its holes. A single angle's bolt line, beside the beam web, lies on the flange. Welds at a plate's faces, a C weld's returns, angle toes, tee tips and seat ends lie on the flange, the fillet's leg included. A bracket's bolt columns have some placement on the flange clear of the web. A seat's bolt holes lie on its vertical leg, below the outstanding leg. |
| `web_fit` | a support met on its web | Bolt lines, parts and welds lie on the web's flat, T. A seat's holes lie on its leg. The beam's flange passes between the column's flanges, unless the beam end lies at or past their tips. |

The modes' model statements state these premises and readings:

- A support met on its web is a column, and the beam frames between its flanges. `web_fit`'s model states this premise, so it is in the footprint of every design with a web support. The deck does not model a girder support, whose flanges the beam's own flanges may meet.
- T from the shapes table bounds the flat web. T is the workable flat depth between the toes of the fillets that Manual Part 1 tabulates. The deck centres it on the web, so each fillet reaches (d - T)/2 from its flange's outer face. A part's corner on a fillet, or on the fillet a shallow cope leaves, does not fit, because the deck does not model clipped corners.
- Where the lines leave a position open, the deck takes the reading most favourable to fit. A single angle, a plate set on edge and a bracket's bolt columns go wherever they fit. An end plate's welds sit anywhere down the web. A cope starts at the beam end or at the setback, whichever lies farther out. A pair of bolt lines is centred on the member, as the gauge across the web reads.
- Holes take their size along or across the force from Table J3.3 for the ply's declared type. A slot across the face needs its length.

The fit checks do not cover:

- the beam flange's corners against the column's web-to-flange fillets
- the angle's own heel fillet under a seat's top bolt, for which the angle's thickness stands in
- whether the stated setback agrees with the beam end that the bolt line draws
- the positions of a top angle and a stiffened seat plate, which the grammar does not draw
- a girder support

The outside judge (`judges/steel.py`) names the same conditions from its own reading. Until 2026-11-07 it read three things more loosely than the deck. The sources side with the deck in each, so the judge now reads them the same way:

1. **A fillet weld at a toe, tip or seat end lays its leg on the face past the part.** The part and the leg at each such weld must lie on the face. The judge already added the leg for a plate's welds. The Manual asks for more: Companion Examples K.2 and K.3 take a shelf of twice the weld size from AISC Manual Figure 8-13. The deck and the judge take only the leg, the least that a weld of the stated size needs.
2. **A cope frees a part's edge only where it cuts as deep as the fillet reaches.** AISC 360-22 defines k as the distance from the flange's outer face to the web toe of the fillet. A shallower cut leaves fillet below it, under the part's corner or a hole. Since 2026-11-08 the deck and the judge both take that reach as (d - T)/2.
3. **Each hole takes the size Table J3.3 gives its ply's declared type.** The type is stated, so it is not a reading the judge may choose. A plain slot runs across the force, so its length lies across the support's face.

The deck is still stricter than the judge in one place. A cope or a beam end frees a fit only where it does so at every point of the design's tolerance box. The judge takes the box's most favourable point.

**The flat web is T, since 2026-11-08.** Petra 0.1.0 read a web's flat as d - 2 kdes, in the deck, the twin, the generator and the judge alike. kdes is k for design calculations. The flat depth a part can bear on is T, the workable depth between the toes of the fillets. The Shapes Database gives T = 15-1/2 in for a W18x35, where d - 2 kdes is 16.05 in. In all 289 W rows of the Shapes Database, T is less than d - 2 kdes, by 0.11 in to 1.60 in (measured on `SHAPE160.xlsx`). The deck, the twin, the generator and the judge now read T for the beam's web and for a column's web, and a cope frees an edge only where it cuts (d - T)/2 deep. The shipped shape rows carry T, copied from the workbook by `python -m petra.registry.steel_shapes import SHAPE160.xlsx --shipped`.

On the gate's stream at seed 1, 10,000 designs, the deck with kdes passed 7,019, and 768 of those fail a fit check with T (measured). 735 fail `beam_fit`, 25 fail `web_fit` and 8 fail both. The judge, reading T, raises a fillet condition on all 768 and on none of the 6,251 that still pass. 648 of the 768 have no cyclic load, so Petra 0.1.0 can read them, and 0.1.0 passes all 648 with its judge silent, so each is a false PASS in 0.1.0. The flips gather on the deep beams, where kdes falls furthest short of (d - T)/2. Half the passing designs on a W30x90, a W27x84 or a W24x76 flip, against 3 of 396 on a W21x44. `FlatWebIsT` in `tests/test_steel_geometry.py` holds a plate edge on that band and an end plate wider than a column web's T to FAIL, and the judge to reject both.

Measured on the absurd-gap stream at seed 1 (13,200 steel designs), at commit `af95e6a` with the old judge: 29 designs failed a fit check that the judge called buildable. 19 had a weld's leg off the face, 8 a cope shallower than kdes and 2 a declared slot. 10 of the 29 also fail another mode. The judge now raises a condition on all 29, and on the same stream no design fails a fit check that the judge calls buildable. P1's close recorded 37 such designs; the count at `af95e6a` is 29.

The twin (§8) restates every fit from the method statements. The gate's manufactured faults (§9) put six misfits into passing designs: rows past the beam's depth, rows off a seat's leg, support bolt lines wider than the face, a beam too wide for a column's web, a plate on the fillet, and bracket columns off the flange. `tests/test_steel_geometry.py` checks six things. Each class of misfit fails the check that names it. The readings that free a fit do free it. The judge reads a weld's leg, a shallow cope and a declared slot as the deck does. A part between T and d - 2 kdes fails, and the judge rejects it. A web support's footprint holds the column premise. The generator's samplers produce designs that fit and that the judge finds buildable.

## 6. How the deck enforces exhaustiveness

| Mechanism | What it guarantees |
|---|---|
| Clause traceability table | Every provision in §4 maps to a check, a premise or an exclusion, in [steel_traceability.md](steel_traceability.md). CI fails if one is unmapped. |
| Load-path graph | Every force component (shear, axial, moment) has a checked path through every fastener and element to the support |
| Limit-state completeness per element | Every element type has a required list of limit states. The coverage check is a trusted, simple set inclusion. |
| A reason for every other mode | Each mode of the domain that a connection does not owe has a recorded physical reason it cannot arise there (`petra/models/steel/absent.py`). The reason is one of three: the part is not drawn, the force that would load it that way is absent, or the source's method takes it as a premise. The readout prints the reason. `tests/test_steel_coverage.py` fails if a generated connection leaves a mode neither owed nor explained. |
| Block-shear path enumeration | The elaborator enumerates every admissible tear-out path from the hole pattern. The twin elaborator must find the same set. |
| Tolerance and material ranges | Every claim covers the tolerance box and the material range, not the nominal value |
| Validity rows | Every formula's applicability limits (such as K1 limits and edge-distance conditions) are proved over the box, or the result is UNKNOWN |
| Margins | Every claim carries a margin δ, so limited compute never leaves an UNKNOWN |

No obligation names a seat's top angle or a stiffened seat plate's welds, because neither carries a computed force.

- A seat's top angle holds the beam's top flange. The deck reads the angle as the restraint that frames the beam's end (J10.7) and keeps both flanges from moving sideways (J10.4). The Manual proportions the angle by practice, not for a force (Part 10). Companion Examples II.A-13 and II.A-14 choose it without a calculation.
- A stiffened seat plate's welds follow the Manual's detailing (Part 10, Fig. 10-11(b)). The plate's weld to the support is the return of the stiffener's weld group under it. The deck's weld check leaves that return out, which is conservative. The plate's weld to the stiffener is sized to match the weld to the support. The grammar draws neither weld. The seat plate's bearing on the stiffener's fitted edge is checked at the plate's own yield stress (J7).

## 7. What the kernel and elaborators need

| Need | Approach | New kernel rule? |
|---|---|---|
| Closed-form limit states over boxes | R4 interval branch-and-bound | No |
| Load share in bolt and weld groups | Elastic method in closed form (R4). A lower bound from any admissible distribution (R1). | No |
| Instantaneous-centre method for eccentric groups | A float search places the centre, and R4 proves what the group holds about it. The proof rests on a measured premise (§7a). | No |
| Clearances and access | Polynomial inequalities over exact coordinates (R4) | No |
| Yield-line end plates (v1.2) | The published governing pattern as a compliance check. A physics PASS needs a lower bound, which R1 can give on a plate strip model [inference]. | No |
| Units | Dimension vectors inside the certificate, planned for P7 ([plan.md](plan.md)) | No |

### 7a. The instantaneous-centre certificate

The Manual's instantaneous-centre method turns the connected part about a centre. Each bolt, or each element of a weld, deforms in proportion to its distance from the centre and carries a force from a load-deformation curve. The group holds a load where those forces balance it. The balancing centre has no closed form, so the deck finds it in two steps.

1. A float search finds the centre on the axis through the centroid across the load, and steps a little short of it toward the group (`petra/models/steel/ic.py`).
2. At that fixed centre r, R4 proves a lower bound on V(r), the force the group holds along the load. It also proves the moment margin M(r) - V(r) (e + r), the moment about r that the group holds beyond what the load puts there. The mechanics layer writes V and M as a sum over the bolts (`instantaneous_centre`), or as exact integrals over a weld group's straight welds cut into segments, with the weld's curve bounded on each segment (`group_ic`).

The certificate gives min(V(r), margin / ell), with ell = 10^-15 in. Where the margin is positive, that is V(r). Where it is not, it is at most zero and cannot pass a design. The check takes the largest of the certificates and the elastic method's C, so C is never less than the elastic method gives.

The kernel proves that the group holds V(r) about r with a positive moment margin. Two facts about the method are premises, which tests measure. First, the eccentricity e(r) = M(r)/V(r) - r that a centre balances falls as r grows, so with a positive margin the balancing centre lies beyond r. Second, V rises up to the balancing centre, so the method's C is at least V(r).

- For bolts, `tests/test_steel_groups.py` measures both over 1 to 12 rows and 1 to 4 columns, gauges from a fifth to five times the pitch, and centres from 10^-4 to 10^4 pitches.
- For a weld line, V peaks at the centre that balances a = 0.102 (measured). The deck takes the method only from a = 1/8 (`petra.weld_ic.a_min`), and the elastic method below it.
- For a C-shaped weld with returns up to five times its line, V peaks at a centre that balances at most a = 0.111 (measured), so the same a = 1/8 holds. The certificate is stated at the box's least kl / L, so it also needs C to rise with the returns. It does at every a from 1/8 to 10, for kl / L up to 2 (measured). The deck takes the method on a C only up to kl = 2 L (`petra.weld_ic.k_max`), and the elastic method past it.

A toleranced design gets one certificate for each pitch and gauge corner of its box, and four along a toleranced length. Each certificate holds over the whole box, and the check takes the largest.

The deck reads the method in these ways.

- A conventional single plate in Manual Table 10-9's configuration takes its eccentricity as a/2. The deck takes it only where every condition holds over the whole box, and otherwise keeps a. The statement still carries the row count, so the kernel proves it: C at a/2 enters times min(1, 6 - rows).
- C is the group's geometry against the load's line, so added material can lower it. A heavier beam's thicker web moves a single angle's support-side load line out, and a thicker plate can leave Table 10-9's configuration (a fillet at least 5/8 tp). No bolt's own strength falls, and that is what `tests/test_steel_properties.py` holds the group to.
- A bracket's group holds C times its weakest bolt (Manual Part 7). Each bolt tears out along its own force, about the centre of the method that gives C (J3.11a). The support's edges are not declared, so only its holes bound its tearout.
- A bracket plate on edge, welded on both faces with e past L/8, is Manual Table 8-4's group at k = 0. Its base metal carries the force along the weld, at most 1.04 times the load's share per unit length (`petra.weld_ic.along_peak`). The bound is 1.0337 for the directional increase times 1.0008 for the curve's peak (measured).
- A lapped bracket plate's C-shaped weld, with e past L/8 from its centroid and returns up to 2 L, is Manual Table 8-8's group. The deck builds it as a list of straight welds, the line and its two returns, and runs the line's search and certificate on that list. Its base metal carries the force along the weld, as above. The check takes the larger of the certificate's C and the elastic method's C, and so does the edge-on group's.
- Edge distances add Table J3.5's C2 for an oversized hole, and for a slot at an edge it runs toward. A plain slot in an eccentric bracket needs a slip-critical joint (J3.3), since the bracket's bolts push along it. For the same reason its slip resistance takes J3.9's factors for a slot parallel to the load, 0.85 for LRFD and 1.76 for ASD. A shear tab's plain short slot keeps the factors for a slot normal to the load, 1.00 and 1.50, as Manual Part 10 details it.
- A hanger pulls normal to its plies, and its card names no direction in their plane. So a slot in either flange may run along the tee or across it, and so may the hanger's shear. Each check takes the worse way. Prying's δ = 1 − d'/p and the flange's net shear take a slot's length, every edge takes the slot's C2, and a long slot takes J3.11a's coefficients for a slot perpendicular to the force. Under a shear a slot needs a slip-critical joint (J3.3) and takes J3.9's factor for a slot parallel to the load. The bolts hold the lesser of the group along the tee and the group across it, where each flange's outer line tears out toward its side edge. Until 2026-11-09 the deck read a plain slot across the tee and the shear along it. On the gate's 909 hangers at commit 140f742 the change turns 22 passes into failures and no failure into a pass (measured).
- A weld bracket's eccentricity is the load's distance from its weld group's centroid, as `docs/reference.md` defines it. A C-shaped weld's centroid lies kl² / (2kl + L) from its vertical line, toward the load (Manual Part 8). Since 2026-11-08 the deck adds that offset before it reads the load from the vertical line. The weld group, its base metal, its throat's fatigue and the plate's sections A-A and B-B all take the same arm. Before, the deck read e from the vertical line, so the gate's bracket gate-1-00009 passed section B-B at 0.927 where the centroid's arm gives 1.038 (measured). On the gate's stream at seed 1, 155 of the 426 weld brackets with returns move from PASS to FAIL, 27 at section B-B and 128 at the elastic weld group (measured). By the instantaneous centre all 128 pass again. So do 93 more that failed the elastic weld group before that change, which the clean-room twin reads at 0.60 to 0.67 (measured).

What the certificate costs, measured.

- The search cuts each weld finer until the bounds give up at most 0.5% of the method's C (`ic.WELD_LOSS`), and stops at 384 segments. At 1% the certificate held Companion II.A-26's C 0.94% under the method, below the Companion's own reading less 1%, so the bound was halved (measured).
- On the 426 gate brackets with returns, the deck's weld reading lies 0.36% to 0.53% above the clean-room twin's (measured). The worst lie at a = 1 and kl = L/5. There the deck gives up 0.47%, and the deck's own twin (`petra/models/steel/twin.py`) reads the method to 1e-6 (measured). So the clean-room twin's reading in that run lies about 0.06% above the method (inferred).
- It reproduces Kulak's Table 13.1 to within 1/2% or one unit of the last printed digit.
- At k = 0 and a = 0.170, Companion II.A-2A interpolates Table 8-4 to C = 3.61. The deck certifies 3.596 (measured). This page gave 3.6125 before 2026-11-08, but the deck then certified 3.580 (measured).
- Companion II.A-23 and II.A-26 interpolate Table 8-8 to C = 1.46 and 1.88. The method gives 1.4569 and 1.8719, and the deck certifies 1.4514 and 1.8630 (measured). The clean-room twin's two-dimensional search agrees with the method to 2e-5 on a C, two parallel lines and a box (measured).
- On an edge-on line, finding a weld group's centre and segments takes about 6 s. A toleranced bracket's report takes about 15 s, against 5 s with the elastic method alone.
- On those 426 brackets the weld and base-metal modes take 2.6 s at the median and 4.4 s at most, against 0.13 s by the elastic method. The whole report takes 10 s at the median and 17 s at most, against 0.27 s (measured, 4 workers on a PC running a second 6-worker job).

Open items.

- A C-shaped weld group below a = 1/8 or with returns past 2 L stays elastic. So does an edge-on weld group below a = 1/8, and every fatigue check.
- The segment list takes any group whose welds lie along or across the load and that mirrors itself across the line through its centroid, such as two parallel lines or a box. The deck feeds it only the line and the C, whose premises are measured. Two parallel lines and a box at a = 3/2 give up 0.72% and 0.74%, past `ic.WELD_LOSS` (measured). An L-shaped group is refused, since its centre leaves that line and the certificate's argument runs along it. An inclined weld is refused too. Its integrals have the same closed forms, but `ic.py` does not encode it.
- A bracket's support has no declared edges, so its tearout is bounded only by its holes.
- The clean-room twin (`twin/`) takes an edge-on weld group by the elastic method, so it fails some designs the deck passes. The deck's tests hold its weld groups to Companion II.A-2A instead.
- The clean-room twin takes a bracket bolt's tearout at its least clear distance in any direction, where J3.11a reads it in the direction of the force. So it fails three gate brackets the deck passes. A separate hand calculation of the method matches the deck on each, to 0.7% on the toleranced one (measured).
- The gate's internal twin runs the weld method in floats. Where a weld check lies above 1 by less than the certificate gives up, the deck fails a design the twin passes. Two of the gate's 10,000 designs do this, by 0.87% and 0.70% (measured).

## 8. Ground truth and outside judges

| Judge | Covers |
|---|---|
| Every Companion v16 example in Chapters J and K and the Part II connection examples, reproduced to rounding | Code implementation |
| Kulak et al. test data (bolt shear, slip, bearing, joint length effects) | Physics behind the bolt rules |
| Twin elaborator, written independently from the same sources, agreeing on all generated cases | Translation |
| Manufactured faults, which are designs with exactly one known defect (missing weld, short edge distance, wrong joint type), all caught | Coverage |
| Breaker, an optimiser that searches for PASSes an independent check refutes | False PASS |
| CalculiX spot checks inside validity rows (plate yielding, Whitmore stresses) | Model sanity |

## 9. The done gate

Every item must hold before the claim in §0 is published.

1. **Clause traceability.** 100% of J1 to J10 and K1 to K5 is mapped (§4), and the table is published.
2. **Catalogue coverage.** Every type in §3 has every applicable limit state, each with validity rows.
3. **Ground truth.** Every in-scope Companion example is reproduced to rounding, and every discrepancy is explained.
4. **Decidedness.** On 10,000 generated connections across the catalogue, each with a margin δ, no UNKNOWN is caused by compute or a missing model.
5. **Twins.** The independent elaborator agrees on all 10,000.
6. **Manufactured faults.** 100% are caught.
7. **Breaker.** No false PASS after a fixed adversarial budget, and every run is logged.
8. **Makeability.** Every generated design passes the deck, or fails with a witness.
9. **Report.** Every connection gets a calculation package that `petra verify` re-checks.

## 10. Build milestones

| # | Milestone | Contents | Gate |
|---|---|---|---|
| M1 | Data layer | Shapes DB v16 loader with hash, ASTM minimums, Table J3.2 bolt strengths, J3.3 hole sizes, J3.4 to J3.6 spacing and edge tables, and provenance on every row | The registry consistency checker passes, and every row cites its clause |
| M2 | Element limit states | J2 welds, J3 bolts, J4 affected elements, J7 bearing, J10 concentrated forces, as statement builders with validity rows | Every Companion Chapter J element example reproduced |
| M3 | Simple shear connections | Shear tab, double angle, single angle, tee, end plate and seated connections, copes, load-path coverage, and makeability | Every Part II shear-connection example reproduced |
| M4 | Groups and hangers | Eccentric bolt and weld groups (elastic, then the instantaneous centre), and hangers with prying | Companion and Kulak cases |
| M5 | Exhaustiveness machinery | Traceability table in CI, connection generator, twin elaborator, manufactured faults, and breaker | Gate items 4 to 7 for v1.0 |
| M6 | Calculation package | Report and `petra verify` | Gate item 9 |
| | v1.0 complete | Simple shear, J10, groups, hangers | §9 for the v1.0 catalogue |
| M7 | v1.1 | Gussets and the uniform force method, flange-plated and CJP moment connections, splices, base plates | §9 extended |
| M8 | v1.2 | End plates, Chapter K HSS | §9 for the whole catalogue, which is the §0 claim |

## 11. Domains that build on this deck

Members (Chapters D to H) and these connections form the shared core of these domains:

- below-the-hook lifting devices, with ASME BTH-1 encoded as methods
- GSE and tooling
- entertainment rigging
- temporary works
- platforms

Each domain becomes a thin rule set on top of the core.
