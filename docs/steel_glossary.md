# Steel deck glossary

This page maps each code name in the steel deck to its AISC symbol and its meaning. Principle
D8 in [principles.md](principles.md) makes the deck's code names AISC's symbols, lowercased
where Python needs it. Symbols are AISC 360-22's unless the meaning cites the Manual, the AISC
Steel Construction Manual, 16th ed. A name with two meanings has one meaning per function,
and the function's docstring says which one applies.

`tests/test_steel_principles.py` fails if this page is missing a parameter of a function in
`petra/models/steel/limits.py` or a length field of the grammar (`lower._LENGTHS`). The
deck builds on the mechanics in `petra/mechanics`: section properties, bolt and weld groups,
and plate buckling. Their names are in [mechanics.md](mechanics.md).

## Quantities in limits.py

| Code name | Symbol | Meaning |
|---|---|---|
| `k` | | the registry constant lookup, which every function takes as its first argument. `k("aisc360.j4_2.shear")` is 0.60 |
| `a` | a | in prying (Manual Part 9), the distance from the bolt line to the flange edge. In a bracket (Manual Fig. 15-2), the plate depth at the support, section A-A |
| `a1` | a′ | in a bracket, the length of the free-edge section B-B (Manual Eq. 15-17) |
| `ae` | Ae | effective net area |
| `ag` | Ag | gross area |
| `agv` | Agv | gross area in shear |
| `ant` | Ant | net area in tension |
| `anv` | Anv | net area in shear |
| `apb` | Apb | projected bearing area (J7) |
| `b` | b | in prying, the distance from the bolt line to the face of the stem or web. In a bracket, the projection of the sloped free edge from section A-A. In a shear tee, the flange's flexible width (Manual Fig. 9-6) |
| `b1` | b′ | in a bracket, the depth of section B-B normal to the free edge |
| `b_tension` | B | available tension per bolt (Manual Part 9) |
| `bf` | bf | flange width |
| `case` | | the web-crippling equation that applies: `interior` (J10-4), `end_short` (J10-5a) or `end_long` (J10-5b) |
| `cb` | Cb | lateral-torsional buckling modification factor |
| `coefficient` | | the J3.11a bearing or tearout coefficient, a registry row |
| `cope_length` | c | length of a cope |
| `cr` | Cr | J10.4's constant, 960,000 or 480,000 ksi |
| `critical` | | rationals bounding the least Delta_u / rho over a weld group's elements, the ratio at which every element deforms (Manual Part 8) |
| `d` | d | bolt diameter (J3, prying) or member depth (J10, Manual Part 9), by function |
| `dc` | dc | column depth (J10.6) |
| `dct` | dct | depth of the top cope (Manual Eq. 9-21) |
| `depth` | d, L | depth of a plate or bar in bending (F11's d) |
| `dh` | dh | nominal hole dimension |
| `du` | Du | slip multiplier |
| `e` | E, e | modulus of elasticity in J10, F11 and Manual Parts 9 and 15, or eccentricity in `seat_weld_line` |
| `factor` | φ, Ω, α | resistance or safety factor, or J10.6's α |
| `fexx` | FEXX | filler metal classification strength |
| `fnt`, `fnv` | Fnt, Fnv | nominal tensile and shear stress of a bolt (Table J3.2) |
| `frv` | frv | required shear stress |
| `fu`, `fy` | Fu, Fy | specified minimum tensile and yield stress |
| `fyf`, `fyw` | Fyf, Fyw | yield stress of the flange and of the web |
| `h` | h | clear web depth, d − 2k |
| `hc` | hc | web depth a cope leaves |
| `hf` | hf | filler factor |
| `k1` | k1 | coped web's plate buckling coefficient, f k (Manual Part 9) |
| `kdes` | k | design distance from the flange's outer face to the web toe of the fillet |
| `ksc` | ksc | slip reduction for tension (Eq. J3-5) |
| `lam`, `lam_p` | λ, λp | slenderness and its compact limit |
| `lb` | lb | length of bearing (J10) |
| `lb_unbraced` | Lb | unbraced length (J10.4, F11) |
| `lc` | lc | clear distance to an edge or the next hole, in the direction of the force |
| `length` | l, L | length of a weld or an element |
| `lrfd` | | LRFD (true) or ASD (false) |
| `mp`, `my` | Mp, My | plastic and yield moment |
| `mu` | μ | mean slip coefficient |
| `near_end` | | true when the force is within d of the member end (J10.2) |
| `nu` | ν | Poisson's ratio |
| `p` | p | flange length tributary to a bolt (Manual Fig. 9-4) |
| `phi` | φ | resistance factor, or 1/Ω in ASD (prying) |
| `planes` | ns | number of shear or slip planes |
| `pr`, `py` | Pr, Py | required axial strength and axial yield strength (J10.6) |
| `run`, `runs` | | a weld group's straight welds turning about an instantaneous center, each cut into segments at its distance from the centre (mechanics.Run, Manual Part 8) |
| `restrained` | | true when the loaded flange is restrained against rotation (J10.4) |
| `sc` | Sc | elastic section modulus of a coped section |
| `t` | t | thickness |
| `t1`, `t2`, `t3`, `w1`, `w2`, `w3`, `w4` | | Table J2.4's thickness rows and minimum fillet sizes |
| `tb` | Tb | minimum bolt pretension |
| `tension_per_bolt` | Tu/nb, Ta/nb | required tension on one bolt |
| `tf`, `tw` | tf, tw | flange and web thickness |
| `theta` | θ | a weld element's angle, in degrees, between its force and its weld's axis (Eq. J2-5) |
| `ts` | ts | a tee's stem thickness |
| `ubs` | Ubs | block shear tension-stress factor |
| `v` | R, V | the force a group carries |
| `w` | w | fillet weld leg size |
| `x` | | F11's Lb d / t², or lb / d in J10.3 |
| `z`, `znet` | Z, Znet | plastic section modulus, gross and net |

## The grammar's length fields

| Field | Symbol | Meaning |
|---|---|---|
| `pitch` | s | spacing of bolt rows |
| `gauge` | g | spacing of bolt columns |
| `edge_vertical` | Lev | vertical edge distance of the end rows |
| `plate_edge` | Leh | horizontal edge distance on the connecting element |
| `bolt_line` | a | distance from the weld line or the support face to the bolt line (Manual Part 10) |
| `beam_edge` | Leh | horizontal edge distance on the beam web, as detailed. Strength checks take it less the 1/4 in underrun (Manual Part 10) |
| `top` | | distance from the beam's top to the top bolt row |
| `setback` | | gap from the support face to the beam end, as detailed. A seat's strength checks add the 1/4 in underrun |
| `eccentricity` | e | the load's distance from the centroid of the bolt group or the weld |
| `beam_gauge`, `support_gauge` | g | gauge of the bolts through the beam web, and of the bolts through the support |
| `plate_width` | | an end plate's width |
| `seat_length` | | a seat angle's length along the beam's width |
| `bearing_length` | lb | length of bearing (J10) |
| `distance` | | distance from the member end to a concentrated force (J10) |
| `unbraced_length` | Lb | J10.4's laterally unbraced length |
| `stiffener_width` | W | width of a seat stiffener (Manual Table 10-8) |
| `stiffener_length` | l | length of a seat stiffener and its welds |
| `weld_length` | L | length of a bracket's weld line |
| `tee_gauge` | g | gauge across a hanger tee's flange |
| `weld_return` | kl | length of a bracket weld's returns |
| `free_edge` | b | projected length of a shaped bracket's free edge |

## Fatigue (Appendix 3)

These are the names in `petra/models/steel/fatigue.py` and the load field that states a cyclic load.

| Code name | Symbol | Meaning |
|---|---|---|
| `cycles` | nSR | the number of stress-range cycles over the design life. A load case that names it on a connection is cyclic, as in `on c1 cycles in [0, 2000000]` |
| `nsr` | nSR | the cycles as the formulas read them, no fewer than 20,000 (Section 3.1) |
| `floor` | | nSR less 20,000, the guard that excuses a fatigue check at 20,000 cycles or fewer |
| `fsr` | FSR | allowable stress range (Eqs. A-3-1, A-3-2 and A-3-5) |
| `cf` | Cf | the constant of a stress category (Table A-3.1) |
| `fth` | FTH | threshold allowable stress range, the least FSR of a category (Table A-3.1) |
| `rfil` | RFIL | reduction factor for the root crack of a pair of fillets at a plate's end (Eq. A-3-6) |
| `tensile_stress_area` | At | a bolt's tensile stress area (Eq. A-3-7) |
| `peak_limit` | | 0.66 Fy, the most stress the peak cyclic load may cause (Section 3.1) |
| `section_stress` | | M / S plus 3 V / (2 t d), the bound on a section's largest principal stress |

## Registry row names

A coefficient's registry row is named `<document>.<clause>.<role>`. For example,
`aisc360.j10_3.long_offset` is the 0.2 of Eq. J10-5b, and `aisc_manual.p9.tc` is the 4 of
Manual Eq. 9-30a. Resistance factors are named `<group>.phi<suffix>`, and safety factors are
named `<group>.omega<suffix>`. The `petra.strict.*` rows are Petra's own encoding of a strict
inequality. `petra/registry/steel.py` gives each row its clause, tag and owner. Appendix 3's
rows are `aisc360.app3.*` in `petra/registry/steel_fatigue.py`, and a stress category's are
`aisc360.app3.cat_<category>.cf` and `.fth`.
