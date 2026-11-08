# The mechanics layer

`petra/mechanics` holds the mechanics that every design code builds on. A design code is a standard, such as AISC 360, Eurocode 3 or VDI 2230, that says how to check a design. The layer is written once, as exact kernel expressions, and belongs to no design code. It covers the properties of a section, how a group of bolts or a weld shares an eccentric force, and when a plate buckles.

A design code is a thin layer on top. The code layer decides which mechanical quantity governs a limit state. It then factors or caps that quantity with the numbers the code prints, and each of those numbers is a registry row. `petra/models/steel/limits.py` is the AISC 360 layer. A Eurocode 3 or VDI 2230 layer would call the same functions.

## The boundary

`tests/test_mechanics.py` enforces these rules:

- **No design code can reach in.** No module here imports a domain (`petra.models`), the registry or `petra.units`, and no function takes a registry lookup. The layer cannot read a design code's number or depend on a unit system.
- **No decimals.** Every numeric literal is an integer from geometry or statics, such as the 4 of Ï€ dÂ²/4, the twelfths of a moment of inertia, or the 12 of a plate's flexural rigidity. A decimal is a fitted or printed number, such as the 0.60 of 0.60 FEXX or the 2.2 of the Manual's cope k. A decimal therefore belongs to a code layer, as a registry row with its clause.
- **No defaults.** No parameter has a default value, so every call states every input.
- **Checked against physics, not against a design code.** A test holds each formula to a brute-force computation of the quantity it claims:
  - section moduli by integration, strip by strip
  - a bolt group's forces by summing over every bolt
  - a weld group's forces by cutting the weld into short segments
  - the plate buckling stress by solving the plate's buckling equation with finite differences
- **The steel twin stays independent.** The steel twin, `petra/models/steel/twin.py`, is a second, independent implementation of the steel deck's limit states. It imports neither this layer nor the deck's builders. If a formula here has an error, the twin disagrees with it instead of repeating it.
- **Premises name the layer.** The steel deck's model premise hash reads this layer's sources (`petra.mechanics.SOURCES`), so an edit here changes every steel premise label.

## Modules

| Module | Functions | Checked against |
|---|---|---|
| `algebra` | `c`, `add`, `sub`, `mul`, `div`, `sq`, `power` | (expression builders) |
| `sections` | `circle_area`, `rectangle_plastic_modulus`, `rectangle_elastic_modulus`, `rectangle_elastic_thickness`, `rectangle_net_plastic_modulus`, `rectangle_net_elastic_modulus`, `rectangle_peak_shear_stress`, `tee_moduli`, `hex_corner`, `right_triangle` | strip integration, exact integrals of \|y\| over the net section, and polygon geometry |
| `bolt_groups` | `polar_moment`, `corner_radius`, `elastic_bolt_force`, `elastic_block_force`, `elastic_centre`, `instantaneous_centre` | a sum over every bolt of the pattern |
| `weld_groups` | `fillet_throat`, `elastic_weld_line`, `elastic_weld_c`, `element_angles`, `line_ic` | the weld cut into short segments |
| `stability` | `plate_buckling_stress` | a finite-difference solution of D âˆ‡â´w + N âˆ‚Â²w/âˆ‚xÂ² = 0 |

## What stays in a design code

A code layer keeps every number its design code prints, and every empirical method the design code takes from tests or the literature. The AISC 360 layer, for example, keeps these:

- the strength coefficients (0.60 FEXX, 1.8 Fy Apb, 6.25 Fyf tfÂ²)
- the web crippling and web sidesway buckling equations
- the cope's k1 and Î»p
- F11's 1.52 âˆ’ 0.274 x Fy/E
- the prying model's a â‰¤ 1.25 b
- the bracket's Q

Where AISC names a geometric quantity, the AISC layer says which mechanics quantity it is. `limits.bolt_area` is the circle area of the nominal diameter (Table J3.2 note). `limits.bracket_section` is the right triangle of Manual Fig. 15-2. `limits.cope_elastic` is the plate buckling stress, with the Manual's k1 as its coefficient and hc/tw as its slenderness, times the tee's Sc.

## Materials

The design codes already share materials. `petra/registry/catalog.py` and `petra/registry/steel.py` both register grades into the one registry, each grade under its own standard (ASTM A992, EN 10025-2 S355, ISO 898-1 property classes). The modulus E that a design uses is a design-code value, 29,000 ksi in AISC 360 and 210 GPa in EN 1993. Each grade therefore takes its E from the row of the design code it is designed under.

## Glossary

This table gives the meaning of each parameter name in the layer. A name with two meanings has one meaning per module, as the module's docstring says.

| Parameter | Symbol | Meaning |
|---|---|---|
| `a`, `b` | | operands (algebra), the legs of a right triangle (sections), or a load's eccentricity over the length of the weld line it acts on (weld_groups) |
| `x` | | the rational a constant holds (algebra) |
| `exponent` | | the power of `power(a, exponent)` |
| `d` | d | a circle's diameter |
| `t` | t | the rectangle's side parallel to the bending axis, which for a plate is its thickness |
| `depth` | d, L | the rectangle's side in the plane of bending |
| `moment`, `stress` | M, Ïƒ | a bending moment and the extreme-fibre stress it reaches |
| `rows`, `cols` | | rows and columns of a bolt pattern, or of holes in a line |
| `n` | n | bolts in a group, rows Ã— cols |
| `pitch`, `s` | s | centre-to-centre spacing of rows |
| `g` | g | gauge, the spacing of columns |
| `hole` | | width of a hole in a net section |
| `hc` | | overall depth of a tee |
| `bf`, `tf` | bf, tf | a tee's flange width and thickness |
| `tw` | tw | a tee's stem (web) thickness |
| `across_flats` | F | width of a hexagon across its flats |
| `v` | V, R | the force a group carries |
| `e` | e, E | eccentricity of the force from the group's centroid or the weld's line (groups), or Young's modulus (stability) |
| `block_rows`, `block_cols` | | rows at one end and columns at one side that a block of bolts holds |
| `r` | r | distance from a group's centroid to the instantaneous centre it turns about |
| `curve` | R/Rult | a code's load-deformation curve: the fraction of its strength a bolt or a weld element holds at a fraction of the largest deformation |
| `w` | w | fillet weld leg size |
| `length` | L | length of a weld line |
| `z` | | where an element lies along a weld line, from its midpoint, in units of the line's length |
| `zs` | | the ends of the segments a weld line's half is cut into, from its midpoint (0) to its end (1/2) |
| `bounds` | | a lower and an upper bound on a weld element's force per unit length over each segment |
| `lines` | | parallel weld lines |
| `ret` | kl | length of a weld return |
| `nu` | Î½ | Poisson's ratio |
| `coefficient` | k | a plate's buckling coefficient |
| `slenderness` | b/t | a plate's width-to-thickness ratio |
