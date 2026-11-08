# Hand checks for the lift pilot

This page holds the hand checks behind the [lift pilot](../pilot_lift.md). They decide two things. Each check Petra does not certify gets a verdict: a real violation of AISC 360-22, or Petra being stricter than the code. And the governing limit state of a sample of designs is checked again, away from Petra, to look for a false PASS.

`python docs/pilot_lift/hand_checks.py` prints every number below. The script imports nothing from `petra/`. It uses AISC 360-22, the Manual's methods as the Companion (v16.0) applies them, and shape dimensions from the AISC Shapes Database v16.0.

## The sample

The protocol fixes the sample. It holds every design an agent called safe that Petra does not pass, and two passing designs per arm drawn with `random.Random(303)`. `python scripts/pilot_lift.py grade` prints it.

| Design | Why it is in the sample | Petra |
|---|---|---|
| without_petra/303-003 | called safe, Petra does not pass | UNKNOWN |
| without_petra/303-006 | called safe, Petra does not pass | FAIL |
| without_petra/303-022 | called safe, Petra does not pass | FAIL |
| with_petra/303-003 | drawn | PASS |
| with_petra/303-006 | drawn | PASS |
| without_petra/303-005 | drawn | PASS |
| without_petra/303-019 | drawn | PASS |

## The solvers

Two of the adjudications need the instantaneous-centre method, which Petra does not have. The script solves it from the Manual's load-deformation relations for bolts (Part 7) and for fillet welds (Part 8). Each solver is checked against a Manual value the Companion quotes.

| Case | This script | Manual |
|---|---|---|
| Table 7-6, one column of 4 bolts at 3 in, e = 1.5 in (Example II.A-17) | C = 3.556 | 3.54 |
| Table 8-4, angle 0, k = 0, a = 0.170 (Example II.A-2A) | C = 3.613 | 3.61 |

## The designs

Each table gives the check as the hand calculation reads it and Petra's utilisation for the same check.

### without_petra/303-003: seated, ASD, 15.843 kip

An L4x4x1/2 A36 seat, 6 in long, with one row of two 3/4 in A325-N bolts at a 3-1/2 in gauge.

| Check | Hand | Petra |
|---|---|---|
| Bolt shear, 2 bolts (J3.7) | 0.664 | 0.664 |
| Seat leg flexure, Manual Part 10 | 0.487 | 0.487 |
| J3.5 maximum spacing: 3.5 in against 24(0.34 in) = 8.16 in | holds | open |

Petra has no maximum-spacing rule for a seat with one row of bolts, so it reports UNKNOWN. The check holds. Verdict: `holds`. A seat with two rows, as in with_petra/303-003, gets the rule and passes it.

### without_petra/303-006: shear tab, ASD, 45.988 kip

A 5/16 in A572 Gr 50 plate with four 3/4 in Group 150-N bolts at 3 in, a = 2-1/2 in.

| Check | Hand | Petra |
|---|---|---|
| Bolt group, instantaneous centre, e = a/2 (Table 10-9), C = 3.661 | 0.836 | |
| Bolt group, instantaneous centre, e = a, C = 3.065 | 0.999 | |
| Bolt group, elastic method, e = a | | 1.082 |
| Plate shear rupture (J4.2b) | 0.839 | 0.839 |

The design meets Table 10-9's conventional configuration: four rows of standard holes, plate and beam web no thicker than db/2 + 1/16 in, and Leh of at least 2db on the plate and the beam. So the Manual takes the bolt group at e = a/2 by the instantaneous-centre method. Bolt shear, 15.02 kip, is the weakest per-bolt strength. Plate tearout at the bottom bolt is 16.38 kip and beam web tearout at the end is 15.72 kip. Even at e = a the group holds. Verdict: `conservative`, the elastic-method reading of [steel_connections.md](../steel_connections.md) §7.

### without_petra/303-022: weld bracket, ASD, 48.42 kip at e = 5 in

A 5/16 in A572 Gr 50 plate, 13 in deep, with 3/16 in E70 fillets on both sides to the W12x40 flange.

| Check | Hand | Petra |
|---|---|---|
| Weld group, instantaneous centre, Table 8-4 special case k = 0, a = 0.385, C = 2.726 | 0.911 | |
| Weld group, elastic method, kds = 1.0 | 1.683 | 1.682 |
| Plate behind the weld, worst element at the instantaneous-centre forces | 0.755 | |
| Plate behind the weld, elastic peak flow against shear rupture | | 1.537 |
| Plate flexural yield at the weld line (F11) | 0.612 | 0.612 |
| Plate shear yield (J4.2a) | 0.596 | 0.596 |

The load is not in the plane of the weld group. The agent cited Manual Table 8-4's special case for that, which takes k = 0 and a = e/l. The Manual's Part 8 tables are not among this project's sources, so this page could not read that note. Two things support it without the note. Each weld element still carries a force along its axis and a force across it, as a line of welds with k = 0 does in plane, so the same relations apply. And tests of fillet-welded cruciform joints under out-of-plane eccentric load found the Manual's eccentric weld tables conservative, with test over predicted strength averaging 1.75, because the tables ignore the plate's bearing on the flange ([Kanvinde, Grondin, Gomez and Kwan, Engineering Journal 46(3), 2009](https://ej.aisc.org/index.php/engj/article/view/955)).

The plate's element check takes, at each weld element, the force along the weld against the plate's shear rupture (6.09 kip/in) and the force across it against the plate's tensile yield (9.36 kip/in), as (f_along/6.09)² + (f_across/9.36)². The plate is also 0.3125 in against the Manual's tmin = 6.19D/Fu = 0.286 in, and J2.4's user note says the base metal check need not be performed for fillet welds. Verdicts: `conservative` for both, the elastic-method reading of §7.

This design is lighter than the reference optimum because of these two checks. The design with Petra for the same task needed 19 in of weld, where this one has 13 in.

### with_petra/303-003: seated, ASD, 15.843 kip

An L5x3-1/2x3/8 A572 Gr 50 seat with its 3-1/2 in leg outstanding, and two rows of two A325-N bolts.

| Check | Hand | Petra |
|---|---|---|
| Seat leg flexure, Manual Part 10, with the 1/4 in underrun | 0.937 | 0.937 |
| The same, at the nominal setback | 0.310 | |
| Bolt shear, 4 bolts (J3.7) | 0.332 | 0.332 |

The required bearing length is kdes = 0.747 in. Web local yielding needs 0.034 in, and web crippling holds at any bearing length. The governing check depends on the 1/4 in underrun that Petra adds to the setback. The Manual recommends it. At the nominal setback the leg is at 0.310.

### with_petra/303-006: shear tab, ASD, 45.988 kip

A 1/4 in A572 Gr 50 plate with five 3/4 in A325-N bolts at 3 in, a = 2-1/4 in.

| Check | Hand | Petra |
|---|---|---|
| Bolt group, instantaneous centre, e = a/2, C = 4.731 | 0.818 | |
| Bolt group, instantaneous centre, e = a, C = 4.276 | 0.905 | |
| Bolt group, elastic method, e = a | | 0.968 |
| Plate shear rupture (J4.2b) | 0.867 | 0.867 |

The weakest bolt is the plate's tearout at the bottom bolt, 11.88 kip. The governing check by hand is plate shear rupture, 0.867.

### without_petra/303-005: hanger, ASD, 34.745 kip

A WT8x15.5 hanging from a W16x31 flange on six 3/4 in A325 bolts, three rows at 2-1/2 in, 3-1/2 in gauge.

| Check | Hand | Petra |
|---|---|---|
| Bolt tension with prying, Manual Part 9, Q = 0.321 | 0.908 | 0.908 |
| Tee stem tensile yield (J4.1a) | 0.563 | 0.563 |

The tee is cut from a W16x31, so the tee flange and the support flange give the same prying result. The agent named J10.1 flange local bending of the support as its governing check, at 0.96. Petra checks the bolted support flange through prying instead. The design holds under both.

### without_petra/303-019: shear end plate, LRFD, 139.063 kip

A 1/4 in A572 Gr 50 end plate, 7-1/2 in by 14-1/2 in, with eight 3/4 in A325-N bolts and 1/4 in E70 fillets to the W21x44 web.

| Check | Hand | Petra |
|---|---|---|
| Bolt shear, 8 bolts (J3.7) | 0.972 | 0.972 |
| Weld, two lines of 1/4 in (J2.4) | 0.892 | 0.892 |
| Beam web at the weld, tmin = 0.381 in against 0.35 in | 0.970 | 0.970 |
| End plate block shear, one bolt at the end (J4.3) | 0.960 | 0.960 |
| End plate block shear, full block both sides (J4.3) | 0.916 | 0.916 |
| End plate shear rupture (J4.2b) | 0.864 | 0.864 |

## What the hand checks found

- No real violation of AISC 360-22 in any of the seven designs.
- Every Petra number the hand checks repeat matches to within 0.001.
- Petra's three non-passes are the elastic method where the Manual uses the instantaneous centre (two designs), and one missing rule (one design).
- One passing design, with_petra/303-003, passes only by a margin that depends on the underrun Petra adds. It holds either way.

## CalculiX

The CalculiX spot check (`scripts/calculix_check.py` at commit `308be67`, on the branch of the CalculiX cross-check) ran on each sampled design its plane model covers, with every element (`--all`) at 0.25 in. It does not model seats or hangers, so it skips with_petra/303-003, without_petra/303-003 and without_petra/303-005. [calculix_sample.txt](calculix_sample.txt) has the output.

| Design | Run | FE capacity, kip | Design strength, kip | FE over nominal Rn | Result |
|---|---|---|---|---|---|
| with_petra/303-006 | yield | 104.5 | 76.2 | 0.913 | ok |
| with_petra/303-006 | rupture | 83.6 | 47.5 | 0.879 | ok |
| without_petra/303-006 | yield | 104.6 | 78.1 | 0.893 | ok |
| without_petra/303-006 | rupture | 86.3 | 46.3 | 0.932 | ok |
| without_petra/303-022 | yield | 91.3 | 79.1 | 0.692 | ok |
| without_petra/303-022 | rupture | 98.5 | 31.5 | 1.564 | ok |
| without_petra/303-019 | yield | 191.6 | 217.5 | 0.881 | flag, points to the model |
| without_petra/303-019 | rupture | 133.8 | 144.8 | 0.693 | flag, points to the deck |

The yield flag on without_petra/303-019 is the one the check's own page predicts for LRFD: von Mises shear yields at 0.577 Fy, where J4.2(a) uses 0.6 Fy with φ = 1.00.

The rupture flag on without_petra/303-019 is a lead. In the model a bolt hole of the end plate stretches 0.25 in at 133.8 kip, under the design strength of 144.8 kip and under the factored load of 139.1 kip. AISC 360-22's formulas give 0.960 for the same plate. The check's page calls a flag that points to the deck "a lead to examine, not a bug", since its rigid bolts and assumed hardening are a model too. The grading counts AISC 360-22, so the design stays safe in the pilot's numbers, and the flag is reported with the results. The end plate of with_petra/303-019, run outside the sample, gets the same flag at the same 133.8 kip ([calculix_rest.txt](calculix_rest.txt)).
