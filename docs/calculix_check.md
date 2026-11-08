# CalculiX spot check of the loop's optima

P2 of the [plan](plan.md) asks that every design the optimiser finds also be checked against CalculiX. The minimiser in [the loop](in_the_loop.md) keeps only designs Petra passes and pushes their mass down, so its optima sit near utilisation 1. An overstated capacity would hide there.

`scripts/calculix_check.py` takes a passing steel design, models the connection element whose limit states govern as a plate with finite elements, runs CalculiX, and compares the element's finite-element capacity with the design strength Petra certified for it. This page fixes the criterion, shows that the model is credible, and reports the check of the loop's optima.

## Run it

CalculiX runs where `ccx` is on `PATH`. Otherwise the script sends each batch of inputs over ssh to `--host`, which defaults to `$PETRA_CCX_HOST` and then to the project's VM.

```bash
python scripts/calculix_check.py check design.petra       # the governing element of one design
python scripts/calculix_check.py validate                  # plain plates against hand solutions
python scripts/calculix_check.py converge 202-001 202-006  # each optimum at three mesh sizes
python scripts/calculix_check.py sample                    # every loop optimum the model covers
python scripts/calculix_check.py report                    # the tables on this page, from the log
```

`sample` reads `docs/in_the_loop_log.jsonl` and appends one JSON line per design to `docs/calculix_check_log.jsonl`. It skips designs already in the log, so a stopped run resumes.

## The model

The model is a plate in its own plane. Each connection kind maps to the plate below.

| Kind | Element modelled | Held along | Pushed by |
|---|---|---|---|
| `shear_tab` | the plate | the weld line | its bolts, down |
| `double_angle`, `single_angle` | one angle leg on the beam side, or one outstanding leg | the heel | its bolts, down |
| `shear_tee` | the stem, or half the flange | the flange face, or the face of the stem | its bolts, down |
| `shear_end_plate` | half the end plate | the face of the beam web | its bolts, down |
| `bolt_bracket` | the bracket plate | its bolts | its far edge, down, at the eccentricity |
| `weld_bracket` | the bracket plate | the weld line | its far edge, down, at the eccentricity |

A design gets one model: the element with the most utilised in-scope limit state. Where a connection has two angles or two halves, the model holds one, and its capacity counts twice.

The mesh is structured and written from Python, with no mesher. Lines either side of each hole cut the plate into blocks. Each plain block is an n by m grid, and each hole's block is an O-grid from the hole to the block's square. The plane mesh is extruded to one layer of 20-node bricks (`C3D20R`), t thick, with `uz = 0` on one face, which gives in-plane plane stress. Holes are the standard hole diameter `dh` from Table J3.3.

Steel is elastic at E = 29,000 ksi and ν = 0.3, with von Mises plasticity at the specified minimum Fy and Fu that Petra reads. The analysis is static, with small displacements, under displacement control. The script runs each element twice:

- **The yield run.** The steel is elastic-perfectly-plastic at Fy. Each bolt is rigid and bonded to its whole hole in the direction it pushes, so no net section can form a mechanism. The capacity is the largest load of the run, which ends on the load plateau.
- **The rupture run.** The steel stays at Fy to a plastic strain of 0.01, hardens linearly to Fu at 0.15, and stays at Fu after that. Each bolt is rigid and bears only on the 120 degrees of its hole that face the way it pushes. The capacity is the largest load before any hole stretches 0.25 in, the deformation that the bearing strength of J3.11a is based on.

A bracket's bolts bear in the directions of the elastic method, which turns the plate about the bolt group's centre. A bonded bolt of a bracket is held in both directions.

Each run judges the limit states below. A state counts only when it is on the modelled element.

| Run | AISC 360-22 limit states it judges |
|---|---|
| Yield | J4.2(a) gross shear yielding, J4.5 flexural yielding |
| Rupture | J4.2(b) shear rupture, J4.3 block shear, J3.11a bearing and tearout at the element's holes, J4.5 flexural rupture, J2.4(a) rupture of the element's base metal along its weld |

## The criterion, fixed before the sample ran

This section was committed before the sample ran. Three designs, 202-001, 202-006 and 202-010, were run while the model was built. They are in the sample too.

Petra states each limit state as a check whose demand is linear in the connection's load. So every strength reads as a load: the connection load at which the check reaches utilisation 1, which is the design's load divided by the check's utilisation. For a bolt group the script keeps only the element's bearing and tearout, summed over the bolts, or, for an eccentric group, the weakest bolt over the elastic method's most loaded one.

For each run:

- The **governing state** is the in-scope state with the least design strength, φRn for LRFD or Rn/Ω for ASD.
- The **FE capacity** is the run's capacity times the number of elements that share the load.
- A design is **flagged** when the FE capacity is below the governing state's design strength.
- The **ratio** is the FE capacity over the governing state's nominal strength Rn. It is reported for every case.

Two differences between the model and AISC's formulas are known before the run. The direction of a flag is read against them.

1. **Von Mises shear.** Under von Mises, a plate yields in pure shear at Fy/√3 = 0.577 Fy, and AISC's J4.2 uses 0.6 Fy. So the yield run can reach at most 0.962 of J4.2(a)'s Rn. With φ = 1.00 for shear yielding, every LRFD design whose governing yield state is J4.2(a) is expected to be flagged. The rupture run's shear is 0.962 of 0.6 Fu for the same reason. With φ = 0.75, the rupture run can fall 22% below its von Mises value before a flag.
2. **Shear and moment together.** The model carries shear and moment together. Petra checks shear yielding and flexural yielding apart, as AISC does for every element here. Petra checks the two together only for an extended shear tab, with the circle of Manual Eq 10-8, and none of the sampled tabs is extended. The script reports a reference capacity for each yield run, the same circle drawn through the von Mises shear strength and the flexural yield strength, in nominal terms:

   R_int = 1 / √((1 / (0.962 Rn,shear))² + (1 / Rn,flexure)²)

   Where Petra has no shear or flexural yield check on the element, the term is the plate's own: 0.6 Fy t d, or Fy t d² / 4 over the arm from the held edge to the bolt group's centre. The end plates and the angles' beam-side legs take their flexure term this way.

A flag points **to the model** when it comes from the yield run and the FE capacity is at least (1 − 0.03) R_int. The 3% band is the model's own shortfall in pure shear, which the validation below measures. A run that stopped before it could measure its capacity is **unresolved**. Every other flag points **to the deck**, every flag of the rupture run included.

A flag that points to the deck is a lead to examine, not a bug. AISC's formulas are calibrated on tests, and a finite-element limit load is a model too.

### Mesh size

The sample runs each design at an element size of 0.5 in. It runs a design again at 0.25 in when a finer mesh could change its verdict: some run stopped early, or its FE capacity is within 5% of its design strength, or a yield flag's FE capacity is within 5% of (1 − 0.03) R_int. The finer run's result is the one judged. The convergence study below sets the 5%.

### What the criterion predicts

These predictions come from Petra's strengths and R_int alone, before any finite-element run.

- **LRFD yield.** R_int is below φRn for 33 of the 37 LRFD designs in scope: all 24 whose governing yield state is shear yielding, and 9 of the 13 governed by flexural yielding. If the FE capacity sits near R_int, these 33 are flagged and the flags point to the model.
- **ASD yield.** Ω = 1.50 or 1.67 leaves R_int above Rn/Ω for all 31 ASD designs. None should be flagged.
- **Rupture.** No rupture flag is expected. A rupture flag needs an FE capacity under 0.75 Rn for LRFD, or 0.50 Rn for ASD.

## Validation

`python scripts/calculix_check.py validate` runs three plain A36 plates, 1/2 in thick, in the yield run.

| Case | What the hand solution is |
|---|---|
| shear | A plate 12 in deep and 1.5 in long, both ends held in x, one end pushed down: pure shear, Fy/√3 d t = 124.7 kip |
| bending | Half of a 6 in by 60 in plate in four-point bending. The moment at its plane of symmetry is constant and shear-free, and is read from the reactions there: Mp = Fy t d² / 4 = 162 kip-in |
| cantilever | A plate 6 in deep and 24 in long, welded along one end, pushed down along the other: Mp / L = 6.75 kip |

The pure-shear plate reads 0.977, 0.973 and 0.972 of its hand solution at element sizes of 0.5, 0.35 and 0.25 in. That 2.8% shortfall sets the band of the criterion. The rest of the validation is added with the sample's results.

## Convergence

To follow, with the sample's results.

## Results

To follow.

## Not checked, and why

| Not checked | Why |
|---|---|
| Bolt shear (J3.7) | A bolt is rigid here. Its fracture needs a model of the bolt, its threads and its shear planes. |
| Bolt tension, prying, combined tension and shear, slip | These are bolt fracture and friction, which a plate model has no part for. |
| Weld metal (J2.4) | Weld fracture needs a model of the weld's throat. The plate's own base metal along the weld is checked. |
| Tension yielding and rupture (J4.1) | Only hangers have them, and a hanger is not modelled. |
| Buckling: plate, cope, web, compression | A one-layer plane model cannot buckle. Buckling needs a shell or a member model. |
| The beam web and the support's plies | They belong to the members. The model holds the connection element only. |
| `seated`, `stiffened_seat`, `hanger` | Their elements bend out of their own planes: the seat's leg and the hanger's tee flange. A stiffener's load on its top edge is a convention, 0.8 of its width, that a model would only restate. |
| The other elements of a connection | Each design gets one model, of the element whose in-scope state is most utilised. `check --all` runs every element. |
| Hole deformation as a design concern | J3.11a's bearing strength assumes deformation at service load is a concern. The rupture run uses that limit, 0.25 in, for every design. |

## Limits of the model

- The steel is at its specified minimum Fy and Fu, as Rn is. The hardening between them is assumed, not taken from coupon tests.
- The model has no fracture. Rupture shows as flow at Fu across a net section, capped by the 0.25 in elongation limit.
- Bolts are rigid. A real bolt bends and its hole ovalises against it, which softens the bearing curve.
- Displacements are small. A tab that twists or a bracket edge that buckles is outside it.
- CalculiX 2.21 is Ubuntu's package, and it was already on the VM. Nothing was installed on the VM or on the PC for this check.
