# Mechanics: the general layer

`petra/mechanics` holds the mechanics that every design code builds on. It is written
once, as exact kernel expressions, and belongs to no code. It covers the properties of a
section, how an eccentric force is shared among a group of bolts or along a weld, and
when a plate buckles. A design code is a thin layer on top. The code decides which
mechanical quantity governs a limit state, then factors or caps it with the numbers it
prints, each a registry row. `petra/models/steel/limits.py` is AISC 360's layer. A
Eurocode 3 or VDI 2230 layer would sit on the same functions.

## The boundary

`tests/test_mechanics.py` holds these rules:

- **No code can reach in.** No module here imports a domain (`petra.models`), the
  registry or `petra.units`, and no function takes a registry lookup. The layer cannot read
  a code's number or depend on a unit system.
- **No decimals.** Every numeric literal is an integer from geometry or statics: the 4
  of π d²/4, the twelfths of a moment of inertia, the 12 of a plate's flexural rigidity. A
  decimal is a fitted or printed number (the 0.60 of 0.60 FEXX, the 2.2 of the Manual's
  cope k), so it belongs to a code layer, as a registry row with its clause.
- **No defaults.** Every input is stated where it is used.
- **Checked against physics, not against a code.** Each formula is held to a brute-force
  computation of the quantity it claims:
  - section moduli by integration, strip by strip;
  - a bolt group's forces by summing over every bolt;
  - a weld group's forces by cutting the weld into short segments;
  - the plate buckling stress by solving the plate's buckling equation with finite
    differences.
- **The steel twin stays independent.** `petra/models/steel/twin.py` imports neither this
  layer nor the deck's builders. If a formula here has a slip, the twin disagrees with
  it rather than repeating it.
- **Premises name it.** The steel deck's model premise hash reads this layer's sources
  (`petra.mechanics.SOURCES`). An edit here changes every steel premise label.

## What is here

| Module | Functions | Checked against |
|---|---|---|
| `algebra` | `c`, `add`, `sub`, `mul`, `div`, `sq`, `power` | (expression builders) |
| `sections` | `circle_area`, `rectangle_plastic_modulus`, `rectangle_elastic_modulus`, `rectangle_elastic_thickness`, `rectangle_net_plastic_modulus`, `tee_moduli`, `hex_corner`, `right_triangle` | strip integration; exact integrals of \|y\| over the net section; polygon geometry |
| `bolt_groups` | `polar_moment`, `corner_radius`, `elastic_bolt_force`, `elastic_block_force` | a sum over every bolt of the pattern |
| `weld_groups` | `fillet_throat`, `elastic_weld_line`, `elastic_weld_c` | the weld cut into short segments |
| `stability` | `plate_buckling_stress` | a finite-difference solution of D ∇⁴w + N ∂²w/∂x² = 0 |

## What stays in a code

A code layer keeps every number its text prints, and every empirical method it takes from
tests or the literature:

- the strength coefficients (0.60 FEXX, 1.8 Fy Apb, 6.25 Fyf tf²);
- the web crippling and web sidesway buckling equations;
- the cope's k1 and λp;
- F11's 1.52 − 0.274 x Fy/E;
- the prying model's a ≤ 1.25 b;
- the bracket's Q.

Where AISC names a geometric quantity, its layer says which one it is.
`limits.bolt_area` is the circle area of the nominal diameter (Table J3.2 note).
`limits.bracket_section` is the right triangle of Manual Fig. 15-2. `limits.cope_elastic`
is the plate buckling stress, with the Manual's k1 as its coefficient and hc/tw as its
slenderness, times the tee's Sc.

Materials are already shared. `petra/registry/catalog.py` and `petra/registry/steel.py`
each register grades into the one registry, every grade under its own standard (ASTM
A992, EN 10025-2 S355, ISO 898-1 property classes). The modulus E a design uses is a code
value: 29,000 ksi in AISC 360, 210 GPa in EN 1993. So each grade takes its E from the
code row it is designed under.

## Glossary

The names of the layer's parameters. A name listed with two meanings has one per module,
as its docstring says.

| Code name | Symbol | Meaning |
|---|---|---|
| `a`, `b` | | operands (algebra); the legs of a right triangle (sections) |
| `x` | | the rational a constant holds (algebra) |
| `exponent` | | the power of `power(a, exponent)` |
| `d` | d | a circle's diameter |
| `t` | t | the rectangle's side parallel to the bending axis: a plate's thickness |
| `depth` | d, L | the rectangle's side in the plane of bending |
| `moment`, `stress` | M, σ | a bending moment and the extreme-fibre stress it reaches |
| `rows`, `cols` | | rows and columns of a bolt pattern, or of holes in a line |
| `n` | n | bolts in a group, rows × cols |
| `pitch`, `s` | s | centre-to-centre spacing of rows |
| `g` | g | gauge, the spacing of columns |
| `hole` | | width of a hole in a net section |
| `hc` | | overall depth of a tee |
| `bf`, `tf` | bf, tf | a tee's flange width and thickness |
| `tw` | tw | a tee's stem (web) thickness |
| `across_flats` | F | width of a hexagon across its flats |
| `v` | V, R | the force a group carries |
| `e` | e, E | eccentricity of the force from the group's centroid or the weld's line (groups); Young's modulus (stability) |
| `block_rows`, `block_cols` | | rows at one end and columns at one side that a block of bolts holds |
| `w` | w | fillet weld leg size |
| `length` | L | length of a weld line |
| `lines` | | parallel weld lines |
| `ret` | kl | length of a weld return |
| `nu` | ν | Poisson's ratio |
| `coefficient` | k | a plate's buckling coefficient |
| `slenderness` | b/t | a plate's width-to-thickness ratio |
