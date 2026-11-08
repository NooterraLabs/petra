# Block shear pilot

This pilot is phase P8 of [the plan](plan.md). It asks whether the block shear strength of AISC 360-22 Section J4.3, Eq. J4-5, stays at or below the load a plastic plate can carry. At the yield stress Fy it does not, except at one of the box's 48 geometries, or three if the bolts bear as Section J3.11 assumes. At the first point of the box, J4.3's nominal strength is about twice the plate's lower-bound limit load at Fy, and the kernel refutes the claim there. How far J4.3 overshoots depends on the bolt columns:

- With one column, J4.3 needs a flow stress of 1.14 to 2.01 Fu before the bound reaches it. So it rests on more than strain hardening to Fu.
- With two columns, Eq. J4-5 halves its tension term (Ubs = 0.5), and J4.3 needs a flow stress of 0.77 to 1.08 Fu. At one geometry, in A992 and A572 Grade 50 steel, the bound reaches J4.3 at Fy itself.

The kernel checked four points. At the first point it refutes J4.3 at Fy, and proves it at 7/5 Fu, or at 6/5 Fu if the bolts bear as Section J3.11 assumes. At the first two-column point it proves J4.3 at Fu, in A36 and in A992 steel. At that one geometry in A992 steel it proves J4.3 at Fy. The rest of the box comes from the untrusted solver.

Where J4.3 exceeds the bound, it rests on test evidence for rupture: bolts bearing harder than plane stress allows, and steel that hardens past Fy.

## Run it

```
python scripts/blockshear_pilot.py
```

The run stops at the first counterexample, after a few minutes. `--contact confined` changes how a bolt bears on the plate (see "Why J4.3 exceeds the bound"). `--all` sweeps the whole box, and `--log FILE` writes one JSON line per point. The pilot needs Python 3.11 with numpy and scipy, and no network.

## The result

### The first counterexample

The first point of the box is A36 steel, two rows and one column, s 2.25 in, Lev 1.25 in, and Leh 1.25 in. With bearing contact the run prints this:

```
box: grade ['A36', 'A992', 'A572_50'], cols ['1', '2'], rows ['2', '4'], pitch ['9/4', '3'], gauge ['9/4', '3'], lev ['5/4', '2'], leh ['5/4', '2']; bolts bolt_us.3_4, standard holes, margin 2 in, contact bearing
model premise: model:steel.blockshear_lower_bound@bd9bc47495bba527
A36     2x1 s 2.25 Lev 1.25 Leh 1.25: LB/J4.3 at Fy 0.490, J4.3 122.7 kip/in block 2x1 yield, J4.3 governs J3.11, needs 1.27 Fu (9 s)
  FIRST COUNTEREXAMPLE in the box: J4.3 exceeds the lower bound at Fy (statement program 0.4904)
  kernel at Fy: Refutation R1, footprint ['reg:steel.A36.fu', 'reg:steel.A36.fy']
  J4.3 block of 2 row(s) and 1 column(s) governs, branch yield (0.6 Fy Agv + Ubs Fu Ant), Ubs 1: 122.7 kip per inch of thickness
  plane-stress bearing cap n (2/sqrt 3) Fy w = 68.9 kip/in (below J4.3's force)
  flow stress J4.3 needs from this mesh: 73.4 ksi = 2.04 Fy = 1.27 Fu
  premise: each bolt bears on the plate above 2/sqrt 3 Fy over the hole's width, past plane stress at Fy; J4.3 rests on J3.11's confined bearing (2.4 d t Fu) and strain hardening
  kernel at flow stress 7/5 Fu: Theorem R1, footprint ['reg:steel.A36.fu', 'reg:steel.A36.fy']
```

`LB/J4.3 at Fy 0.490` says the best field on this mesh carries 49 percent of J4.3's force when the flow stress is Fy. `needs 1.27 Fu` is the flow stress at which this mesh's bound would reach J4.3's force. The footprint names the registry values that the statement uses.

With confined contact the first counterexample is the same point:

```
box: grade ['A36', 'A992', 'A572_50'], cols ['1', '2'], rows ['2', '4'], pitch ['9/4', '3'], gauge ['9/4', '3'], lev ['5/4', '2'], leh ['5/4', '2']; bolts bolt_us.3_4, standard holes, margin 2 in, contact confined
model premise: model:steel.blockshear_lower_bound@bd9bc47495bba527
A36     2x1 s 2.25 Lev 1.25 Leh 1.25: LB/J4.3 at Fy 0.520, J4.3 122.7 kip/in block 2x1 yield, J4.3 governs J3.11, needs 1.19 Fu (12 s)
  FIRST COUNTEREXAMPLE in the box: J4.3 exceeds the lower bound at Fy (statement program 0.5199)
  kernel at Fy: Refutation R1, footprint ['reg:steel.A36.fu', 'reg:steel.A36.fy']
  J4.3 block of 2 row(s) and 1 column(s) governs, branch yield (0.6 Fy Agv + Ubs Fu Ant), Ubs 1: 122.7 kip per inch of thickness
  flow stress J4.3 needs from this mesh: 69.2 ksi = 1.92 Fy = 1.19 Fu
  premise: a flow stress above Fu; J4.3 rests on more than strain hardening to Fu
  kernel at flow stress 6/5 Fu: Theorem R1, footprint ['reg:steel.A36.fu', 'reg:steel.A36.fy']
```

### Points the kernel proves

`--point` gives the kernel's verdict on one plate. The first two-column point has two rows and two columns, s and g 2.25 in, and Lev and Leh 1.25 in. There J4.3 needs 0.81 Fu in A36 steel, and the kernel proves it at flow stress Fu in both materials:

```
python scripts/blockshear_pilot.py --point 2 2 9/4 9/4 5/4 5/4 --grade A36 --flow fu 1
python scripts/blockshear_pilot.py --point 2 2 9/4 9/4 5/4 5/4 --grade A992 --flow fu 1
```

```
A36     2x2 s 2.25 g 2.25 Lev 1.25 Leh 1.25, flow stress 1 fu, contact bearing: program 1.2307, kernel: Theorem R1, footprint ['reg:steel.A36.fu', 'reg:steel.A36.fy']
A992    2x2 s 2.25 g 2.25 Lev 1.25 Leh 1.25, flow stress 1 fu, contact bearing: program 1.2261, kernel: Theorem R1, footprint ['reg:steel.A992.fu']
```

With four rows and two columns, s 2.25 in, g 3 in, Lev 1.25 in, and Leh 2 in, the bound in A992 steel clears J4.3 at Fy by 0.07 percent. The kernel proves the claim at Fy. There J4.3's force is at most the plate's plastic collapse load with no strain hardening at all. The run takes about 15 minutes:

```
python scripts/blockshear_pilot.py --point 4 2 9/4 3 5/4 2 --grade A992
```

```
A992    4x2 s 2.25 g 3 Lev 1.25 Leh 2, flow stress 1 fy, contact bearing: program 1.0007, kernel: Theorem R1, footprint ['reg:steel.A992.fu', 'reg:steel.A992.fy']
```

### Across the box

The numbers below come from the solver's linear program at each geometry, the program that `--all` runs. Past the first point the kernel did not check them. "Bound over J4.3" is the lower bound at Fy divided by J4.3's force. "Flow stress needed" is the flow stress, over Fu, at which this mesh's bound reaches J4.3's force.

| Over the box | Bearing contact | Confined contact |
|---|---|---|
| Points where J4.3 exceeds the bound at Fy | 142 of 144 | 138 of 144 |
| Points where 0.75 Rn exceeds the bound at Fy | 73 of 144 | 62 of 144 |
| Bound over J4.3 at Fy, one column | 0.340 to 0.674 | 0.443 to 0.706 |
| Bound over J4.3 at Fy, two columns | 0.627 to 1.001 | 0.706 to 1.034 |
| Flow stress needed, one column | 1.14 to 2.01 Fu | 1.09 to 1.48 Fu |
| Flow stress needed, two columns | 0.77 to 1.08 Fu | 0.74 to 0.98 Fu |
| Points that need more than Fu | 58 of 144 | 48 of 144 |

This table gives the flow stress needed at each geometry, over Fu. A star marks a point where J3.11's bearing and tearout strength is below J4.3's, so J4.3 does not govern the plate's bolt checks there.

| Plate | s | g | Lev | Leh | A36, bearing | A36, confined | A992 and A572 Grade 50, bearing | A992 and A572 Grade 50, confined |
|---|---|---|---|---|---|---|---|---|
| 2 x 1 | 2.25 |  | 1.25 | 1.25 | 1.27 | 1.19 | 1.27 | 1.20 |
| 2 x 1 | 2.25 |  | 1.25 | 2 | 1.63 * | 1.40 * | 1.64 * | 1.40 * |
| 2 x 1 | 2.25 |  | 2 | 1.25 | 1.33 | 1.21 | 1.43 | 1.30 |
| 2 x 1 | 2.25 |  | 2 | 2 | 1.68 | 1.28 | 1.77 | 1.36 |
| 2 x 1 | 3 |  | 1.25 | 1.25 | 1.38 | 1.24 | 1.48 | 1.34 |
| 2 x 1 | 3 |  | 1.25 | 2 | 1.76 * | 1.40 * | 1.86 * | 1.48 * |
| 2 x 1 | 3 |  | 2 | 1.25 | 1.45 | 1.25 | 1.64 | 1.42 |
| 2 x 1 | 3 |  | 2 | 2 | 1.82 | 1.31 | 2.01 * | 1.45 * |
| 4 x 1 | 2.25 |  | 1.25 | 1.25 | 1.14 | 1.09 | 1.14 | 1.09 |
| 4 x 1 | 2.25 |  | 1.25 | 2 | 1.25 | 1.12 | 1.25 | 1.12 |
| 4 x 1 | 2.25 |  | 2 | 1.25 | 1.17 | 1.10 | 1.22 | 1.14 |
| 4 x 1 | 2.25 |  | 2 | 2 | 1.29 | 1.11 | 1.33 | 1.15 |
| 4 x 1 | 3 |  | 1.25 | 1.25 | 1.29 | 1.12 | 1.42 | 1.24 |
| 4 x 1 | 3 |  | 1.25 | 2 | 1.47 | 1.14 | 1.60 | 1.25 |
| 4 x 1 | 3 |  | 2 | 1.25 | 1.32 | 1.12 | 1.50 | 1.28 |
| 4 x 1 | 3 |  | 2 | 2 | 1.51 | 1.12 | 1.69 | 1.25 |
| 2 x 2 | 2.25 | 2.25 | 1.25 | 1.25 | 0.81 | 0.79 | 0.82 | 0.80 |
| 2 x 2 | 2.25 | 2.25 | 1.25 | 2 | 0.87 | 0.84 | 0.88 | 0.85 |
| 2 x 2 | 2.25 | 2.25 | 2 | 1.25 | 0.86 | 0.83 | 0.92 | 0.89 |
| 2 x 2 | 2.25 | 2.25 | 2 | 2 | 0.86 | 0.79 | 0.91 | 0.84 |
| 2 x 2 | 2.25 | 3 | 1.25 | 1.25 | 0.85 | 0.81 | 0.85 | 0.82 |
| 2 x 2 | 2.25 | 3 | 1.25 | 2 | 0.92 | 0.86 | 0.92 | 0.86 |
| 2 x 2 | 2.25 | 3 | 2 | 1.25 | 0.89 | 0.83 | 0.94 | 0.88 |
| 2 x 2 | 2.25 | 3 | 2 | 2 | 0.92 | 0.80 | 0.97 | 0.84 |
| 2 x 2 | 3 | 2.25 | 1.25 | 1.25 | 0.87 | 0.84 | 0.93 | 0.90 |
| 2 x 2 | 3 | 2.25 | 1.25 | 2 | 0.89 | 0.84 | 0.94 | 0.89 |
| 2 x 2 | 3 | 2.25 | 2 | 1.25 | 0.91 | 0.88 | 1.02 | 0.98 |
| 2 x 2 | 3 | 2.25 | 2 | 2 | 0.91 | 0.82 | 1.00 | 0.91 |
| 2 x 2 | 3 | 3 | 1.25 | 1.25 | 0.91 | 0.86 | 0.96 | 0.92 |
| 2 x 2 | 3 | 3 | 1.25 | 2 | 0.96 | 0.86 | 1.01 | 0.91 |
| 2 x 2 | 3 | 3 | 2 | 1.25 | 0.94 | 0.88 | 1.04 | 0.97 |
| 2 x 2 | 3 | 3 | 2 | 2 | 0.99 | 0.83 | 1.08 | 0.91 |
| 4 x 2 | 2.25 | 2.25 | 1.25 | 1.25 | 0.82 | 0.81 | 0.82 | 0.81 |
| 4 x 2 | 2.25 | 2.25 | 1.25 | 2 | 0.78 | 0.76 | 0.78 | 0.76 |
| 4 x 2 | 2.25 | 2.25 | 2 | 1.25 | 0.83 | 0.82 | 0.86 | 0.85 |
| 4 x 2 | 2.25 | 2.25 | 2 | 2 | 0.79 | 0.76 | 0.81 | 0.79 |
| 4 x 2 | 2.25 | 3 | 1.25 | 1.25 | 0.80 | 0.78 | 0.80 | 0.78 |
| 4 x 2 | 2.25 | 3 | 1.25 | 2 | 0.77 | 0.74 | 0.77 | 0.74 |
| 4 x 2 | 2.25 | 3 | 2 | 1.25 | 0.81 | 0.79 | 0.84 | 0.82 |
| 4 x 2 | 2.25 | 3 | 2 | 2 | 0.78 | 0.75 | 0.80 | 0.77 |
| 4 x 2 | 3 | 2.25 | 1.25 | 1.25 | 0.86 | 0.84 | 0.94 | 0.93 |
| 4 x 2 | 3 | 2.25 | 1.25 | 2 | 0.82 | 0.79 | 0.90 | 0.87 |
| 4 x 2 | 3 | 2.25 | 2 | 1.25 | 0.87 | 0.85 | 0.98 | 0.95 |
| 4 x 2 | 3 | 2.25 | 2 | 2 | 0.83 | 0.79 | 0.93 | 0.89 |
| 4 x 2 | 3 | 3 | 1.25 | 1.25 | 0.85 | 0.82 | 0.93 | 0.90 |
| 4 x 2 | 3 | 3 | 1.25 | 2 | 0.82 | 0.78 | 0.90 | 0.85 |
| 4 x 2 | 3 | 3 | 2 | 1.25 | 0.86 | 0.83 | 0.96 | 0.93 |
| 4 x 2 | 3 | 3 | 2 | 2 | 0.83 | 0.78 | 0.93 | 0.87 |

### On a finer mesh

The pilot's mesh has one ring of cells around each hole and plain cells up to 1 in. Refining it raises the bound by a few percent, and the second step adds less than the first. The table gives the bound over J4.3 at Fy. The second plate is the 3 x 1 plate whose J4.3 values the tests check by hand. It lies outside the box.

| Plate | Contact | 0 rings, 2 in cells | 1 ring, 1 in cells (the pilot) | 2 rings, 1/2 in cells |
|---|---|---|---|---|
| A36, 2 x 1, s 2.25 in, Lev 1.25 in, Leh 1.25 in | bearing | 0.449 | 0.490 | 0.500 |
| A36, 2 x 1, s 2.25 in, Lev 1.25 in, Leh 1.25 in | confined | 0.476 | 0.520 | 0.530 |
| A992, 3 x 1, s 3 in, Lev 1.5 in, Leh 1.5 in | bearing | 0.484 | 0.505 | 0.506 |
| A992, 3 x 1, s 3 in, Lev 1.5 in, Leh 1.5 in | confined | 0.559 | 0.606 | 0.608 |

`scripts/blockshear_pilot.py` does not print this table. Each row is `airy_program` from `petra/models/steel/blockshear_solve.py` on `Discretization(rings, cell, box=3/4)`.

## The box

The box is a grid of 144 points. Every combination of the values below is one point with its own statement. Nothing is claimed between the points.

| Parameter | Values |
|---|---|
| Grade, Fy and Fu from the registry | `steel.A36` (36 and 58 ksi), `steel.A992` (50 and 65 ksi), `steel.A572_50` (50 and 65 ksi) |
| Bolt | 3/4 in (`bolt_us.3_4`) in a standard 13/16 in hole |
| Rows | 2, 4 |
| Columns | 1, 2 |
| Pitch s | 2.25 in, 3 in |
| Gauge g | 2.25 in, 3 in, with two columns only |
| End distance Lev, from the first row to the end edge | 1.25 in, 2 in |
| Side distance Leh, from the first column to the side edge | 1.25 in, 2 in |
| Thickness | any |

That gives 48 geometries, each with three grades. A992 and A572 Grade 50 have the same Fy and Fu, so their numbers match. Every point meets the minimum spacing of Section J3.4 and the minimum edge distance of Table J3.4.

Thickness is not a grid axis. J4.3's strength and the stress field both scale with the thickness t, so one statement per unit thickness covers every t.

## The method

The plate is the corner of a larger plate, the coped beam of Commentary Figure C-J4.2. The bolts push toward the end edge. The plate is held along its two far edges, 2 in beyond the outer row and the outer column. The steel deck checks blocks made of the first k rows from the end edge and the first j columns from the side edge. J4.3's force is the bolt-group force at which the weakest of those blocks reaches Eq. J4-5, with every bolt taking an equal share. It is the nominal strength Rn, before the resistance factor.

`petra/models/steel/blockshear.py` states each point as one R1 goal, a linear feasibility problem with exact rational rows. The mesh is linear-stress triangles (Sloan 1988). Each hole is a 16-sided polygon drawn around the 13/16 in hole. The rows say:

- Each triangle is in equilibrium, and traction is continuous across every interior edge.
- Free edges, and the half of each hole the bolt moves away from, carry no traction.
- Each bolt presses on the other half of its hole with a uniform pressure of its own.
- The bolts' forces sum to J4.3's force and pass through the group's centroid.
- At every triangle corner the stresses lie inside a polygon inscribed in the von Mises surface for plane stress, with flow stress sigma0.

The polygon's vertices are rational points on the von Mises surface, so the polygon lies inside it. A point that meets every row is then a statically admissible stress field. By the lower-bound theorem of limit analysis, a proof means J4.3's force is at most the plate's plastic collapse load at sigma0. A refutation means J4.3's force exceeds the best field on this mesh.

`petra/models/steel/blockshear_solve.py` finds the evidence and is untrusted. To prove, it writes the field from an Airy stress function, a C1 cubic on each triangle. Any rational values of that function's free parameters meet the equilibrium, continuity, and boundary rows exactly. A linear program in scipy's HiGHS picks the parameters with the largest load factor. The solver rounds them, scales the field to J4.3's force, and computes the yield slacks exactly. To refute, it solves the statement's own linear program and rounds its duals into a Farkas ray. The kernel checks both kinds of evidence with rule R1, and no kernel change was needed.

`scripts/blockshear_pilot.py` sweeps the box. Per geometry, one linear program gives the lower bound per unit flow stress, so every grade's load factor follows from it. At the first point where J4.3 exceeds the bound at Fy, the run has the kernel check a refutation. It then has the kernel prove the bound at the smallest flow stress on a fixed ladder of multiples of Fu. With `--point`, the run checks one plate at one flow stress. It tries a proof when the program carries J4.3's force, and a refutation otherwise.

## Why J4.3 exceeds the bound

In plane stress a bolt cannot push harder than the steel at the edge of its hole allows. With no friction, the hole's surface carries only the bolt's pressure p, as a normal stress, and the stress along the edge is free. Von Mises in plane stress then caps p at 2 sigma0 / sqrt 3, reached when the stress along the edge is a compression of p / 2. So a bolt delivers at most (2 / sqrt 3) sigma0 d t, with d the hole's width across the push. This cap holds for every stress field, so it holds on any mesh. It is a hand argument, and the kernel checks only the meshed statement.

At the first point the cap is 2 x 1.155 x 36 ksi x 13/16 in = 67.5 kip per inch of thickness, and J4.3 asks for 122.7. The run prints 68.9 because the mesh's 16-sided hole is a little wider than the round one. No plane-stress field at Fy carries J4.3's force there, however fine the mesh. Across the box, J4.3 exceeds the cap at Fy at 112 of 144 points, and at Fu at 50. Friction would add shear on the hole's surface and raise the cap by at most 21 percent. J4.3 still exceeds that raised cap at Fu at 36 points.

Tests show that real plates carry far more. Section J3.11 gives the bearing strength at a bolt hole as 2.4 d t Fu, with d the bolt's diameter. Commentary J3.11 bases it on tests (Frank and Yura 1981, Kim and Yura 1996, Lewis and Zwerneman 1996). For a 3/4 in bolt in A36 steel that is 104 kip per inch of thickness, three times the plane-stress cap at Fy. The bolt confines the steel through the thickness, and the steel hardens past Fy.

The confined contact tests whether bearing explains the whole gap. In the bolt's contact zone it lets the stress through the thickness equal the in-plane mean stress. Von Mises then limits only the in-plane shear, so the bearing cap goes away. The bound rises by 1 to 39 percent. With one column J4.3 still needs a flow stress of 1.09 to 1.48 Fu. So on this mesh, a plane-stress plate at Fu falls short of Eq. J4-5 with one column even when the bolts bear as J3.11 allows.

Two columns change the picture. Eq. J4-5 takes only half of the tension plane's strength there (Ubs = 0.5), so J4.3's force grows by less than the number of bolts. The bearing cap grows with the number of bolts. J4.3 exceeds the cap at Fy at 64 of the 96 two-column points, against all 48 one-column points. With two columns J4.3 needs 0.77 to 1.08 Fu in bearing contact and 0.74 to 0.98 Fu in confined contact. So with two columns, strain hardening to Fu covers every point once the bolts bear as J3.11 allows. At three geometries with four rows, in A992 and A572 Grade 50 steel, the confined bound passes J4.3 at Fy itself.

## What this means for the registry premise

The steel deck checks block shear with the registry rows `aisc360.j4_3.shear` (0.60) and `aisc360.j4_3.ubs_nonuniform` (0.5). Both carry the tag `sanctioned` and the source AISC. The pilot does not change their values. It shows what a PASS on them rests on.

A J4.3 PASS is not, in general, a plastic lower bound. At Fy the pilot's bound is 0.34 to 1.00 times J4.3's force across the box. The design strength 0.75 Rn exceeds the bound at 73 of 144 points, every one-column point among them. The shear coefficient alone is above plasticity, since 0.60 exceeds the von Mises ratio 1 / sqrt 3 = 0.577.

Commentary J4.3 says why. It calls block shear a rupture limit state, not a yielding one, and it fits Eq. J4-5 to tests (Birkemoe and Gilmor 1978, Ricles and Yura 1983, Hardash and Bjorhovde 1985, Kulak and Grondin 2001). So J4.3 rests on test evidence for two effects that a plane-stress plastic plate at Fy lacks:

- Bearing above the plane-stress cap, from confinement through the thickness. J3.11's 2.4 d t Fu is the tested value.
- Strain hardening past Fy, to a flow stress near Fu with two columns and above Fu with one.

The proposal is to record this premise on `aisc360.j4_3.shear`, with Commentary J4.3 and this pilot as its sources. The registry would then say that a J4.3 PASS rests on rupture tests. With one column it rests on more than strain hardening to Fu: at the first point the kernel proves Eq. J4-5 against plasticity only once the flow stress reaches 7/5 Fu, or 6/5 Fu with confined bearing.

## What the pilot leaves open

- **The box is a grid.** The pilot judges 144 separate points and claims nothing between them. A proof over a region would need the geometry as hypotheses. But the mesh coordinates are entries of R1's matrix, and R1 takes the matrix as exact numbers, so each geometry needs its own statement.
- **The kernel checked four points.** The other rows of each sweep come from the untrusted solver's linear programs. At the 112 points where J4.3 exceeds the bearing cap at Fy, the cap argument backs the claim that J4.3 exceeds the plane-stress limit at Fy, on any mesh. Everything else rests on the solver alone.
- **The bound depends on the mesh.** A finer mesh gives a higher lower bound, and the table under "On a finer mesh" shows the steps. Where J4.3 exceeds the bearing cap, no mesh closes the gap in bearing contact. Elsewhere, and in confined contact, a much finer mesh could close more of it.
- **The confined zone has a fixed size.** It is the bearing half of the bolt's box, 3/4 in from the bolt at most. A larger zone would raise the confined bound.
- **The model makes choices J4.3 does not state.** The bolts are rigid, fill their holes, and press with uniform pressure and no friction. The holes have no 1/16 in allowance for damage. The plate is held 2 in beyond the outer bolts. The field may share the force unequally between bolts, as long as the resultant passes through the centroid.
- **No registry row changed.** The premise text above is a proposal for the maintainers.
