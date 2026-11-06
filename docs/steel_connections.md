# Niche 1, finished exhaustively: steel connections to AISC 360-22

Written 2026-11-05. This is the build specification for the first niche Petra finishes completely before any public release. It follows [NICHE.md](NICHE.md) §14, which picks steel connections as the open deck with the most designs, and [COMPILER.md](COMPILER.md), which places this deck in the standard-library layer. Tags are as in NICHE.md.

## 0. The claim this work must earn

> **Petra checks every provision of AISC 360-22 Chapters J and K, for every connection type in its catalogue. Every verdict covers the whole tolerance and material range, and every result is re-checkable by the kernel.**

That claim covers a real slice of structural engineering. Fabricators and connection engineers design these connections every day, and AI connection tools are starting to produce them (NICHE §14.5).

**Why this niche can be closed:**
- **Forces arrive as signed inputs.** The engineer of record gives the required strengths at each connection, so no building-wide analysis is needed.
- **The rules are free and finite.** Chapters J and K list every limit state in a free document.
- **The kernel already suffices.** Almost every check is a closed-form inequality over a box, which R4 handles. Load distribution in bolt and weld groups is a linear program, which R1 handles. No new kernel rule is needed for the first release (one possible exception is noted in §7).

## 1. Sources

| Source | Role | Access |
|---|---|---|
| AISC 360-22, Chapters J and K (and B–H for supporting members) | The provisions | Free PDF [verified] |
| AISC 360-22 vs 360-16 comparison | Change list. It confirms the 360-22 section numbering used in §4 | Free [verified] |
| AISC Design Examples (Companion), v16 | Ground truth: Chapter J and K examples, plus the Part II connection examples | Free [verified] |
| AISC Shapes Database v16 | Section dimensions | Free [verified] |
| RCSC Specification for Structural Joints Using High-Strength Bolts (2025) | Bolt installation types, joint types, faying surfaces | Free from boltcouncil.org [verified] |
| Kulak, Fisher and Struik, *Guide to Design Criteria for Bolted and Riveted Joints*, 2nd ed. | The research and test data behind the bolt rules: the rawest material, and an outside judge | Free from boltcouncil.org [verified] |
| AISC 303-22 Code of Standard Practice | Fabrication and erection tolerances | [check: free download] |
| AISC Steel Construction Manual, 16th ed., Parts 7–15 | Design procedures: prying, eccentric groups, copes, uniform force method, conventional shear-tab configurations | Paid. Encode the methods, not the text (NICHE §4), or derive them from the free research they cite |
| AISC Design Guides 1, 4, 16, 29 | Base plates, end plates, bracing connections | [check: free to members only] |
| AWS D1.1 | Prequalified weld details | Paid; enters as `assumed` premises |
| ACI 318 Chapter 17 | Concrete anchorage | Paid. Out of scope; enters as premises from ICC-ES reports |

## 2. The requirements card (inputs)

| Input | Example | Premise tag |
|---|---|---|
| Required strengths per load combination (LRFD or ASD) | Vu in [0, 62] kips; Tu in [0, 15] kips | `assumed`, signed by the engineer of record |
| Members | W18x50 beam to W14x90 column flange | `sanctioned` (Shapes DB, with hash) |
| Materials | A992 (Fy ≥ 50, Fu ≥ 65 ksi); A36 plate (36 and 58 ksi) | `sanctioned` (ASTM guaranteed minimums) |
| Bolts | Group 120, 3/4 in., STD holes, threads included, snug-tight | `sanctioned` (Table J3.2) plus the joint type per RCSC |
| Welds | E70 fillet, 1/4 in., both sides, 8.5 in. long | Design values; quality enters as an AWS `assumed` premise |
| Geometry | Bolt pitch, gauges, edge distances, cope size, setback | Design values, with tolerance intervals |
| Tolerances | Hole position, mill under-run, cope cut | From AISC 303 and ASTM A6, as interval premises [check sources] |
| Environment | Indoor dry, or galvanized faying surfaces | `assumed` |

## 3. The connection catalogue (closed list)

Each type is a graph of elements: supported member → fasteners → connecting element → fasteners → supporting member. Coverage generates every limit state for every node and edge (§6).

| Release | Connection type | Limit states (beyond the bolt, weld and element checks every type gets) |
|---|---|---|
| v1.0 | Single-plate (shear tab), conventional and extended | Plate shear yield and rupture; block shear in the plate and the beam web; plate flexure from eccentricity; plate buckling for the extended form; rotational ductility limits; weld sized to develop the plate |
| v1.0 | Double angle: bolted–bolted, bolted–welded | Angle shear yield and rupture; block shear; eccentric weld groups on the outstanding legs |
| v1.0 | Single angle; tee shear connection | Eccentricity on the support side; tee stem and flange checks |
| v1.0 | Shear end plate | Plate shear; welds to the web; bolt group |
| v1.0 | Unstiffened and stiffened seated connections | Seat-angle flexure; web local yielding and crippling (J10); stiffener and weld checks |
| v1.0 | Coped beams (applies to all of the above) | Block shear and flexural local web buckling at the cope |
| v1.0 | Concentrated forces on the support (J10) | Flange local bending, web local yielding, web crippling, sidesway buckling, compression buckling, panel-zone shear, unframed ends, stiffener and doubler requirements |
| v1.0 | Eccentric bolt and weld groups (brackets) | Elastic method first; instantaneous-centre method once its certificate exists (§7) |
| v1.0 | Hangers (tee or angle in tension) | Prying action; flange flexure; bolt tension plus prying |
| v1.1 | Bracing connections: gusset plates | Whitmore-section yield and buckling (J4.4); block shear; interface forces by the uniform force method; gusset-to-beam and gusset-to-column welds |
| v1.1 | Flange-plated FR moment connection | Flange plate tension and compression; bolts or welds to the beam flange; J10 checks on the column |
| v1.1 | Directly welded flange (CJP) FR moment connection | Groove-weld strength (J2.1); J10 checks on the column; panel zone |
| v1.1 | Beam and column splices (bolted flange and web plates) | Splice plates per J6; fillers per J5 |
| v1.1 | Column base plates under axial load | Bearing on concrete (J8); base-plate flexure; anchor rods (J9); concrete anchorage as a premise |
| v1.2 | End-plate moment connections, flush and extended | Yield-line plate strength, with the governing pattern from the published method; bolt tension with and without prying [check method source] |
| v1.2 | HSS connections (Chapter K): concentrated forces, truss T/Y/X/K, moment, welds to HSS | All K2–K5 limit states, with K1 validity limits as validity rows |

## 4. Clause coverage: every section mapped

Done means every "shall" in these sections maps to an encoded check, a premise, or an out-of-scope entry with its reason. The section list follows the 360-22 numbering [verified against the AISC comparison document].

| Section | Content | Treatment |
|---|---|---|
| J1 | General provisions: design basis, simple and moment connections, compression members with bearing joints, splices in heavy sections, weld access holes, placement of welds and bolts, bolts with welds, bolts with existing rivets | Encoded as rules and coverage triggers. Heavy-section splice and weld-access-hole geometry are makeability checks. Rivets are out of scope (no existing structures in v1). |
| J2 | Welds and welded joints: groove, fillet, plug and slot welds; effective areas; size and length limits; strength including the new directional-strength factor; combinations; filler metal; mixed weld metal | Encoded. Filler metal matching and mixed weld metal become premises. |
| J3.1–J3.2 | Common and high-strength bolts (Groups 120, 144, 150, 200) | Registry rows and joint-type rules (with RCSC) |
| J3.3–J3.6 | Holes, minimum spacing, minimum edge distance, maximum spacing and edge distance | Makeability inequalities |
| J3.7–J3.8 | Tension and shear; combined, bearing-type | Encoded |
| J3.9–J3.10 | Slip-critical; combined, slip-critical | Encoded; the faying-surface class is a premise |
| J3.11 | Bearing and tearout at holes (a: snug-tight or pretensioned; b: bolts through unstiffened box or HSS) | Encoded, per hole |
| J3.12–J3.13 | Special fasteners; wall strength at tension fasteners | Special fasteners are out of scope in v1; wall strength is encoded for HSS (v1.2) |
| J4.1–J4.5 | Affected elements in tension, shear, block shear, compression and flexure | Encoded. Block shear runs over every enumerated path (§6). |
| J5 | Fillers in welded and bolted connections | Encoded (v1.1) |
| J6 | Splices | Encoded (v1.1) |
| J7 | Bearing strength | Encoded |
| J8 | Column bases and bearing on concrete | Encoded (v1.1) |
| J9 | Anchor rods and embedments | Rod strength encoded. Concrete breakout is a premise (ACI 318 Chapter 17, out of scope). |
| J10.1–J10.9 | Flanges and webs with concentrated forces | Encoded, with stiffener and doubler requirements as coverage triggers |
| K1 | HSS parameters, effective width, chord-stress interaction, end distance, limits of applicability | Limits of applicability become validity rows (v1.2) |
| K2–K5 | Concentrated forces on HSS; truss connections; moment connections; welds to HSS | Encoded (v1.2) |
| B–H as needed | Supporting-member checks such as the beam web at the connection, and the column for J10 | Encoded where a connection check needs them |

**Excluded outright, as typed UNKNOWN:**
- seismic connections (AISC 341, 358);
- fatigue (Appendix 3) unless declared;
- fire (Appendix 4);
- composite connections (Chapter I);
- existing structures and rivets;
- concrete anchorage design.

## 5. Makeability checks

| Check | Source | How |
|---|---|---|
| Hole sizes, minimum spacing, edge distances, maximum spacing | J3.3–J3.6 | Linear inequalities (R4) |
| Room to enter and tighten each bolt | Wrench and socket clearance geometry | Exact rational geometry, with the clashing point as the witness (expressed as R4 inequalities) |
| Weld access and torch angle | Joint geometry | Geometry inequalities |
| Fillet size limits: minimum by thickness, maximum along edges | J2.2b | Inequalities |
| Cope and weld-access-hole geometry | J1.6 | Inequalities |
| Stock plate thicknesses and bolt lengths | Shop deck | Catalogue membership |
| Installation type matches the joint type | RCSC | Rule check |

## 6. How exhaustiveness is enforced, not just claimed

| Mechanism | What it guarantees |
|---|---|
| **Clause traceability table** | Every provision in §4 maps to a check, a premise or an exclusion. CI fails if one is unmapped. |
| **Load-path graph** | Every force component (shear, axial, moment) has a checked path through every fastener and element to the support |
| **Limit-state completeness per element** | Every element type has a required list of limit states. The coverage check is set inclusion, trusted and simple. |
| **Block-shear path enumeration** | The elaborator enumerates every admissible tear-out path from the hole pattern. The twin elaborator must find the same set. |
| **Tolerance and material ranges** | Every claim covers the tolerance box and the material range, not the nominal value |
| **Validity rows** | Every formula's applicability limits (such as K1 limits and edge-distance conditions) are proved over the box, or the result is UNKNOWN |
| **Margins** | Every claim carries a margin δ, so limited compute never leaves an UNKNOWN |

## 7. What the kernel and elaborators need

| Need | Approach | New kernel rule? |
|---|---|---|
| Closed-form limit states over boxes | R4 interval branch-and-bound | No |
| Load share in bolt and weld groups | Elastic method in closed form (R4). A lower bound from any admissible distribution (R1). | No |
| Instantaneous-centre method for eccentric groups | Needs a proof that an equilibrium point exists in a box (interval Newton or Krawczyk). Until then, use the elastic method, which is conservative. | **Possibly**: one small existence rule |
| Clearances and access | Polynomial inequalities over exact coordinates (R4) | No |
| Yield-line end plates (v1.2) | The published governing pattern as a compliance check. A physics PASS needs a lower bound, which R1 can give on a plate strip model [inference]. | No |
| Units | E2 dimension vectors (in progress in the original session) | No |

## 8. Ground truth and outside judges

| Judge | Covers |
|---|---|
| Every Companion v16 example in Chapters J and K and the Part II connection examples, reproduced to rounding | Code implementation |
| Kulak et al. test data (bolt shear, slip, bearing, joint length effects) | Physics behind the bolt rules |
| Twin elaborator, written independently from the same sources, agreeing on all generated cases | Translation |
| Manufactured faults: designs with exactly one known defect (missing weld, short edge distance, wrong joint type), all caught | Coverage |
| Breaker: an optimiser searches for PASSes that an independent check refutes | False PASS |
| CalculiX spot checks inside validity rows (plate yielding, Whitmore stresses) | Model sanity |

## 9. The done gate

All must hold before the claim in §0 is published.

1. **Clause traceability:** 100% of J1–J10 and K1–K5 mapped (§4), with the table published.
2. **Catalogue coverage:** every type in §3 has every applicable limit state, each with validity rows.
3. **Ground truth:** every in-scope Companion example reproduced to rounding, and every discrepancy explained.
4. **Decidedness:** on 10,000 generated connections across the catalogue, each with a margin δ, no UNKNOWN caused by compute or a missing model.
5. **Twins:** the independent elaborator agrees on all 10,000.
6. **Manufactured faults:** 100% caught.
7. **Breaker:** no false PASS after a fixed adversarial budget, with every run logged.
8. **Makeability:** every generated design passes the deck, or fails with a witness.
9. **Report:** every connection gets a calculation package that `petra verify` re-checks.

## 10. Build milestones

| # | Milestone | Contents | Gate |
|---|---|---|---|
| M1 | Data layer | Shapes DB v16 loader with hash; ASTM minimums; Table J3.2 bolt strengths; J3.3 hole sizes; J3.4–J3.6 spacing and edge tables; provenance on every row | Registry consistency checker passes; every row cites its clause |
| M2 | Element limit states | J2 welds, J3 bolts, J4 affected elements, J7 bearing, J10 concentrated forces, as statement builders with validity rows | Every Companion Chapter J element example reproduced |
| M3 | Simple shear connections | Shear tab, double angle, single angle, tee, end plate, seated; copes; load-path coverage; makeability | Every Part II shear-connection example reproduced |
| M4 | Groups and hangers | Eccentric bolt and weld groups (elastic); hangers with prying | Companion and Kulak cases |
| M5 | Exhaustiveness machinery | Traceability table in CI; connection generator; twin elaborator; manufactured faults; breaker | Gate items 4–7 for v1.0 |
| M6 | Calculation package | Report and `petra verify` | Gate item 9 |
| — | **v1.0 complete** | Simple shear, J10, groups, hangers | §9 for the v1.0 catalogue |
| M7 | v1.1 | Gussets and the uniform force method, flange-plated and CJP moment connections, splices, base plates | §9 extended |
| M8 | v1.2 | End plates, Chapter K HSS | §9 for the whole catalogue: the §0 claim |

## 11. What the same deck unlocks next

Members (Chapters D–H) plus these connections give the shared core for:
- below-the-hook lifting devices (ASME BTH-1 encoded as methods);
- GSE and tooling;
- entertainment rigging;
- temporary works;
- platforms.

Each becomes a thin rule set on top (NICHE §14.4).
