# Steel deck glossary

D8 of [principles.md](principles.md): the deck's code names are AISC's symbols, lowercased
where Python needs it, and this page maps each name to its symbol and meaning. Symbols are
AISC 360-22's unless marked Manual (AISC Steel Construction Manual, 16th ed.). A name
listed with two meanings has one per function, and the function's docstring says which.
`tests/test_steel_principles.py` holds every parameter of `lola/models/steel/limits.py`
and every length field of the grammar (`lower._LENGTHS`) to this page.

## Quantities in limits.py

| Code name | Symbol | Meaning |
|---|---|---|
| `k` | | the registry constant lookup every function takes first: `k("aisc360.j4_2.shear")` is 0.60 |
| `a` | a | prying (Manual Part 9): bolt line to the flange edge. Bracket (Manual Fig. 15-2): plate depth at the support, section A-A |
| `a1` | a′ | bracket: length of the free-edge section B-B (Manual Eq. 15-17) |
| `across_flats` | F | width of a hex nut across its flats |
| `ae` | Ae | effective net area |
| `ag` | Ag | gross area |
| `agv` | Agv | gross area in shear |
| `ant` | Ant | net area in tension |
| `anv` | Anv | net area in shear |
| `apb` | Apb | projected bearing area (J7) |
| `b` | b | prying: bolt line to the face of the stem or web. Bracket: projection of the sloped free edge from section A-A |
| `b1` | b′ | bracket: depth of section B-B normal to the free edge |
| `b_tension` | B | available tension per bolt (Manual Part 9) |
| `bf` | bf | flange width |
| `block_cols`, `block_rows` | | columns and rows of bolts a block-shear path holds |
| `case` | | which web-crippling equation: `interior` (J10-4), `end_short` (J10-5a), `end_long` (J10-5b) |
| `cb` | Cb | lateral-torsional buckling modification factor |
| `coefficient` | | the J3.11a bearing or tearout coefficient, a registry row |
| `cols`, `rows` | | bolt columns and rows of a pattern; n = rows × cols |
| `cope_length` | c | length of a cope |
| `cr` | Cr | J10.4's constant, 960,000 or 480,000 ksi |
| `d` | d | bolt diameter (J3, prying); member depth (J10, Manual Part 9), by function |
| `dc` | dc | column depth (J10.6) |
| `dct` | dct | depth of the top cope (Manual Eq. 9-21) |
| `depth` | d, L | depth of a plate or bar in bending (F11's d) |
| `dh` | dh | nominal hole dimension |
| `du` | Du | slip multiplier |
| `e` | E, e | modulus of elasticity in J10 and Manual Parts 9 and 15; eccentricity in the elastic group functions and `seat_weld_line` |
| `exponent` | | the power of `power(a, exponent)` |
| `factor` | φ, Ω, α | resistance or safety factor; J10.6's α |
| `fexx` | FEXX | filler metal classification strength |
| `fnt`, `fnv` | Fnt, Fnv | nominal tensile and shear stress of a bolt (Table J3.2) |
| `frv` | frv | required shear stress |
| `fu`, `fy` | Fu, Fy | specified minimum tensile and yield stress |
| `fyf`, `fyw` | Fyf, Fyw | yield stress of the flange, of the web |
| `g` | g | gauge between bolt columns |
| `h` | h | clear web depth, d − 2k |
| `hc` | hc | web depth a cope leaves |
| `hf` | hf | filler factor |
| `hole` | dh′ | hole width for net area, dh + 1/16 in (B4.3b) |
| `k1` | k1 | coped web's plate buckling coefficient, f k (Manual Part 9) |
| `kdes` | k | design distance from the flange's outer face to the web toe of the fillet |
| `ksc` | ksc | slip reduction for tension (Eq. J3-5) |
| `lam`, `lam_p` | λ, λp | slenderness and its compact limit |
| `lb` | lb | length of bearing (J10) |
| `lb_unbraced` | Lb | unbraced length (J10.4, F11) |
| `lc` | lc | clear distance to an edge or the next hole, in the direction of the force |
| `length` | l, L | length of a weld or an element |
| `lines` | | parallel weld lines |
| `lrfd` | | LRFD (true) or ASD (false) |
| `mp`, `my` | Mp, My | plastic and yield moment |
| `mu` | μ | mean slip coefficient |
| `n` | n, nb | bolts in a group |
| `near_end` | | J10.2: the force within d of the member end |
| `nu` | ν | Poisson's ratio |
| `p` | p | flange length tributary to a bolt (Manual Fig. 9-4) |
| `phi` | φ | resistance factor, or 1/Ω in ASD (prying) |
| `pitch`, `s` | s | centre-to-centre spacing of bolt rows |
| `planes` | ns | shear or slip planes |
| `pr`, `py` | Pr, Py | required axial strength; axial yield strength (J10.6) |
| `restrained` | | J10.4: the loaded flange restrained against rotation |
| `ret` | kl | length of a weld return |
| `sc` | Sc | elastic section modulus of a coped section |
| `t` | t | thickness |
| `t1`, `t2`, `t3`, `w1`, `w2`, `w3`, `w4` | | Table J2.4's thickness rows and minimum fillet sizes |
| `tb` | Tb | minimum bolt pretension |
| `tension_per_bolt` | Tu/nb, Ta/nb | required tension on one bolt |
| `tf`, `tw` | tf, tw | flange and web thickness |
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
| `bolt_line` | a | weld line or support face to the bolt line (Manual Part 10) |
| `beam_edge` | Leh | horizontal edge distance on the beam web |
| `top` | | beam's top to the top bolt row |
| `setback` | | gap from the support face to the beam end |
| `eccentricity` | e | load's distance from the bolt group's or weld's centroid |
| `beam_gauge`, `support_gauge` | g | gauge of the bolts through the beam web, through the support |
| `plate_width` | | an end plate's width |
| `seat_length` | | a seat angle's length along the beam's width |
| `bearing_length` | lb | length of bearing (J10) |
| `distance` | | from the member end to a concentrated force (J10) |
| `unbraced_length` | Lb | J10.4's laterally unbraced length |
| `stiffener_width` | W | width of a seat stiffener (Manual Table 10-8) |
| `stiffener_length` | l | length of a seat stiffener and its welds |
| `weld_length` | L | length of a bracket's weld line |
| `tee_gauge` | g | gauge across a hanger tee's flange |
| `weld_return` | kl | a bracket weld's returns |
| `free_edge` | b | a shaped bracket's free edge, projected |

## Registry rows

A coefficient's row is named `<document>.<clause>.<role>`: `aisc360.j10_3.long_offset` is
the 0.2 of Eq. J10-5b, `aisc_manual.p9.tc` the 4 of Manual Eq. 9-30a. Resistance and
safety factors are `<group>.phi<suffix>` and `<group>.omega<suffix>`; `lola.strict.*` are
LoLa's own encoding of a strict inequality. `lola/registry/steel.py` gives each row its
clause, tag and owner.
