# CalculiX spot check of the loop's optima

P2 of the [plan](plan.md) asks that every design the optimiser finds also be checked against CalculiX. The minimiser in `petra/loop.py` keeps only designs Petra passes and pushes their mass down, so its optima sit near utilisation 1. An overstated capacity would hide there.

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

Petra states each limit state as a check whose demand is linear in the connection's load. So every strength reads as a load: the connection load at which the check reaches utilisation 1, which is the design's load divided by the check's utilisation. For a bolt group the script keeps only the element's bearing and tearout, summed over the bolts, or, for an eccentric group, the group's C times the element's weakest bolt. The results on this page were measured when the deck took every eccentric group by the elastic method, as its weakest bolt over the most loaded one. The deck now takes the larger of that and the instantaneous centre, and this page has not been rerun.

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

FE capacity over the hand solution, at three element sizes:

| Case | Hand solution | 0.5 in | 0.25 in | 0.125 in |
|---|---|---|---|---|
| shear | 124.7 kip | 0.977 | 0.972 | 0.970 |
| bending | 162.0 kip-in | 0.991 | 0.993 | 0.994 |
| cantilever | 6.75 kip | 1.071 | 1.069 | 1.068 |

Each run ends on a plateau: its load grows by less than 0.3% over the last fifth of the push.

- **Bending** reaches Mp to within 0.7%. The plane of symmetry carries no shear, so this is the model's plastic moment alone.
- **Shear** settles 3% under Fy/√3. The plate's held ends carry a moment of V L / 2, and its free edges carry no shear. A 0.35 in run reads 0.973. This 3% is the band of the criterion.
- **The cantilever** reads 7% over Mp / L. Its welded edge cannot shrink sideways, so the steel along it yields in plane strain. There a bending stress of up to 2/√3 Fy = 1.155 Fy can develop. The gain is real for a plate held along a weld, and the model has it wherever an element is held along an edge: tabs, angles, tees, end plates and welded brackets. It raises the FE capacity, so it cannot cause a flag.

## Convergence

`python scripts/calculix_check.py converge 202-001 202-002 202-006 202-010` runs four optima, one of each topology, at three element sizes. The FE capacities are in kip.

| Design | Run | 0.5 in | 0.35 in | 0.25 in | 0.5 to 0.25 in |
|---|---|---|---|---|---|
| 202-001 `shear_tab` | yield | 127.5 | 127.4 | 127.1 | −0.3% |
| | rupture | 156.6 | 153.3 | 150.8 | −3.7% |
| 202-002 `double_angle` | yield | 111.3 | 110.9 | 110.2 | −0.9% |
| | rupture | 140.2 | 137.2 | 137.3 | −2.1% |
| 202-006 `weld_bracket` | yield | 77.5 | 77.3 | 77.2 | −0.4% |
| | rupture | 89.3 | 89.2 | 89.2 | −0.1% |
| 202-010 `bolt_bracket` | yield | 59.2 | 59.1 | 59.0 | −0.3% |
| | rupture | 62.0 | 61.4 | 61.1 | −1.5% |

The capacities fall as the mesh refines, by at most 3.7% from 0.5 to 0.25 in. So the 5% of the close-call rule covers the step from the screen to the judged size. The yield run is settled to 1%. The shear tab's rupture run still falls 1.6% from 0.35 to 0.25 in, because its capacity hangs on how the edge of a hole deforms. Its judged capacity may be a few percent high.

## Results

`python scripts/calculix_check.py sample` checked all 68 loop optima the model covers: 15 `shear_tab`, 7 `double_angle`, 8 `single_angle`, 10 `shear_tee`, 6 `shear_end_plate`, 9 `bolt_bracket` and 13 `weld_bracket`. The other 32 tasks are seats, stiffened seats and hangers, or have no optimum. Six designs were close calls at 0.5 in and were run again at 0.25 in. Every run finished its push. The log is `docs/calculix_check_log.jsonl`, and `report` prints the tables below from it.

- **32 flags.** All come from the yield run of an LRFD design, and all 32 point to the model.
- **No rupture flag.** The least rupture FE capacity is 1.15 times its design strength.
- **No ASD flag.** The least ASD yield FE capacity is 1.17 times Rn/Ω.
- **No design falls below its own load.** Every FE capacity exceeds the factored or service load the design was sized for.

The forecast held. It named 33 LRFD yield flags and got 32. The one it named and missed is 202-047, a welded bracket whose R_int sits at 0.997 of φRn. Its FE capacity came out 14% over R_int, the most of any welded bracket, and so above φRn.

### The flags

| Task | Kind | Governing yield state | FE / Rn | FE / φRn | FE / R_int | Points to |
|---|---|---|---|---|---|---|
| 202-001 | `shear_tab` | plate, J4.2(a) shear yielding | 0.939 | 0.939 | 0.995 | model |
| 202-004 | `shear_tee` | tee stem, J4.5 flexural yielding | 0.762 | 0.847 | 1.138 | model |
| 202-006 | `weld_bracket` | bracket plate, J4.5 flexural yielding | 0.829 | 0.921 | 1.094 | model |
| 202-012 | `shear_tab` | plate, J4.2(a) shear yielding | 0.871 | 0.871 | 1.084 | model |
| 202-014 | `single_angle` | outstanding leg, J4.2(a) shear yielding | 0.825 | 0.825 | 1.116 | model |
| 202-019 | `shear_tab` | plate, J4.2(a) shear yielding | 0.913 | 0.913 | 1.033 | model |
| 202-026 | `shear_end_plate` | end plate, J4.2(a) shear yielding | 0.871 | 0.871 | 1.023 | model |
| 202-030 | `shear_tab` | plate, J4.2(a) shear yielding | 0.906 | 0.906 | 1.011 | model |
| 202-031 | `double_angle` | angles, J4.2(a) shear yielding | 0.896 | 0.896 | 1.063 | model |
| 202-032 | `shear_tee` | tee stem, J4.2(a) shear yielding | 0.876 | 0.876 | 1.057 | model |
| 202-040 | `bolt_bracket` | bracket plate, J4.5 flexural yielding | 0.787 | 0.874 | 1.073 | model |
| 202-041 | `weld_bracket` | bracket plate, J4.5 flexural yielding | 0.740 | 0.823 | 1.062 | model |
| 202-045 | `shear_tee` | tee stem, J4.5 flexural yielding | 0.786 | 0.874 | 1.149 | model |
| 202-049 | `shear_tab` | plate, J4.2(a) shear yielding | 0.928 | 0.928 | 1.004 | model |
| 202-050 | `shear_end_plate` | end plate, J4.2(a) shear yielding | 0.886 | 0.886 | 1.002 | model |
| 202-052 | `shear_tab` | plate, J4.2(a) shear yielding | 0.871 | 0.871 | 1.084 | model |
| 202-053 | `double_angle` | angles, J4.2(a) shear yielding | 0.853 | 0.853 | 1.136 | model |
| 202-054 | `shear_tee` | tee stem, J4.2(a) shear yielding | 0.833 | 0.833 | 1.076 | model |
| 202-060 | `double_angle` | angles, J4.2(a) shear yielding | 0.900 | 0.900 | 1.054 | model |
| 202-061 | `shear_tee` | tee stem, J4.2(a) shear yielding | 0.904 | 0.904 | 1.019 | model |
| 202-063 | `bolt_bracket` | bracket plate, J4.5 flexural yielding | 0.674 | 0.749 | 1.028 | model |
| 202-067 | `shear_end_plate` | end plate, J4.2(a) shear yielding | 0.838 | 0.838 | 1.043 | model |
| 202-068 | `shear_tab` | plate, J4.2(a) shear yielding | 0.912 | 0.912 | 1.035 | model |
| 202-070 | `shear_tee` | tee stem, J4.2(a) shear yielding | 0.857 | 0.857 | 1.077 | model |
| 202-072 | `shear_tab` | plate, J4.2(a) shear yielding | 0.876 | 0.876 | 1.069 | model |
| 202-077 | `bolt_bracket` | bracket plate, J4.2(a) shear yielding | 0.777 | 0.777 | 1.015 | model |
| 202-079 | `shear_tab` | plate, J4.2(a) shear yielding | 0.901 | 0.901 | 1.037 | model |
| 202-080 | `single_angle` | outstanding leg, J4.2(a) shear yielding | 0.872 | 0.872 | 1.100 | model |
| 202-084 | `shear_tab` | plate, J4.2(a) shear yielding | 0.940 | 0.940 | 0.994 | model |
| 202-085 | `shear_tee` | tee stem, J4.5 flexural yielding | 0.779 | 0.866 | 1.133 | model |
| 202-095 | `double_angle` | angles, J4.2(a) shear yielding | 0.851 | 0.851 | 1.129 | model |
| 202-097 | `weld_bracket` | bracket plate, J4.5 flexural yielding | 0.776 | 0.862 | 1.075 | model |

**Which way they point.** Every flag reaches R_int: the least FE / R_int is 0.994, inside the 3% band, and the median is 1.077. So von Mises shear and the interaction of shear with moment account for each flag in full. None points to a strength Petra computed wrongly for its own geometry. They point to AISC's convention: φ = 1.00 on 0.6 Fy for shear yielding, and shear and flexural yielding checked apart. Petra follows that convention, as the deck should.

The largest gaps are where one element runs high in both shear and flexure: bolted and welded brackets and tee stems. 202-063, a bolted bracket, reaches 0.749 of φRn. If the deck ever wants to be stricter than AISC there, the lever already exists. Petra checks the Eq 10-8 circle on extended shear tabs, and the same circle on brackets and tee stems would close these gaps. That is a choice for the deck, not a bug.

R_int sits at or under the FE capacity for every kind, to within the 3% band. The model beats it by up to 17%. A held edge gives part of that, 7% in the cantilever validation. The rest is the circle itself, which is cautious for a short, deep plate.

| Kind | n | FE / R_int, min | median | max |
|---|---|---|---|---|
| `shear_tab` | 15 | 0.994 | 1.033 | 1.084 |
| `shear_end_plate` | 6 | 1.002 | 1.042 | 1.123 |
| `shear_tee` | 10 | 1.019 | 1.077 | 1.149 |
| `bolt_bracket` | 9 | 1.015 | 1.094 | 1.139 |
| `double_angle` | 7 | 1.054 | 1.102 | 1.136 |
| `single_angle` | 8 | 1.031 | 1.101 | 1.173 |
| `weld_bracket` | 13 | 1.062 | 1.123 | 1.142 |

### The ratios

FE capacity over the governing state's Rn, for every design:

| Run | Basis | Governing state | n | min | p10 | median | p90 | max |
|---|---|---|---|---|---|---|---|---|
| yield | all | all | 68 | 0.674 | 0.782 | 0.874 | 1.013 | 1.060 |
| yield | ASD | flexural yielding | 13 | 0.752 | 0.791 | 0.893 | 1.020 | 1.033 |
| yield | ASD | shear yielding | 18 | 0.783 | 0.842 | 0.871 | 0.913 | 0.939 |
| yield | LRFD | flexural yielding | 13 | 0.674 | 0.745 | 0.787 | 1.040 | 1.060 |
| yield | LRFD | shear yielding | 24 | 0.777 | 0.834 | 0.876 | 0.924 | 0.940 |
| rupture | all | all | 68 | 0.864 | 0.965 | 1.265 | 2.093 | 2.774 |
| rupture | ASD | block shear | 6 | 0.888 | 0.920 | 0.975 | 0.987 | 0.990 |
| rupture | ASD | bolt group | 10 | 1.301 | 1.436 | 1.772 | 2.202 | 2.385 |
| rupture | ASD | shear rupture | 6 | 1.087 | 1.092 | 1.123 | 1.135 | 1.139 |
| rupture | ASD | weld base metal | 9 | 1.421 | 1.547 | 1.815 | 2.009 | 2.020 |
| rupture | LRFD | block shear | 12 | 0.864 | 0.883 | 1.016 | 1.144 | 1.149 |
| rupture | LRFD | bolt group | 12 | 1.229 | 1.389 | 1.716 | 2.558 | 2.774 |
| rupture | LRFD | shear rupture | 9 | 1.062 | 1.101 | 1.134 | 1.217 | 1.218 |
| rupture | LRFD | weld base metal | 4 | 1.402 | 1.421 | 1.512 | 1.872 | 2.006 |

Where shear yielding governs, no yield ratio passes 0.940, under the 0.962 that von Mises allows. Where flexural yielding governs, the ratio reaches 1.06, with help from the held edge.

Block shear has the lowest rupture ratios, down to 0.864 (202-030). Its shear planes are 0.962 of 0.6 Fu under von Mises, and the run stops at a hole stretch of 0.25 in or at the end of its push, before the whole block has flowed. With φ = 0.75 that still leaves a margin of 1.15.

The bolt-group and weld base metal ratios are high for a reason in the check, not the steel. A bolt group with an eccentric load is checked as its weakest bolt against the most loaded one by the elastic method. The weld's base metal is checked at the most stressed point of the weld line, elastically. The plate redistributes past both. The model also pushes every bolt alike, so it does not test the eccentricity itself.

**A diagnostic, after the run.** This is outside the criterion. For the 22 designs whose rupture run is governed by an eccentric bolt group, the script also sums the element's bearing and tearout over its bolts, as a concentric group's are. Then bearing and tearout never govern: block shear or net shear rupture takes over, and the FE capacity is 0.82 to 1.21 times that Rn, median 1.09. The least is 202-054, a tee stem in net shear rupture, at 0.823. So the sample tests the holes' bearing and tearout only through those mechanisms.

**The rupture ratios are lower bounds.** The rupture run's push ends at 0.4 in of bolt travel, or at 5% of the length for a welded bracket's edge. In 13 runs a hole stretched 0.25 in first, as the criterion means. In the other 55 the push ended first, with the load still rising, by a median 3.2% over the last fifth of the push. Their capacity is the load at the end of the push, so their ratios are low by a few percent or more. A lower bound can make a flag but cannot hide one, so the verdicts stand.

### Every design

FE capacity over the governing state's Rn, with the element size the result was judged at.

| Task | Kind | Element | Basis | Size (in) | Yield state | Yield FE / Rn | Rupture state | Rupture FE / Rn | Flag |
|---|---|---|---|---|---|---|---|---|---|
| 202-001 | shear_tab | plate | LRFD | 0.25 | shear_yield | 0.939 | shear_rupture | 1.062 | yield, model |
| 202-002 | double_angle | angles | ASD | 0.5 | shear_yield | 0.886 | shear_rupture | 1.131 |  |
| 202-003 | single_angle | angle outstanding | ASD | 0.5 | flexural_yield | 0.789 | bolts | 2.182 |  |
| 202-004 | shear_tee | tee stem | LRFD | 0.5 | flexural_yield | 0.762 | bolts | 2.330 | yield, model |
| 202-006 | weld_bracket | bracket plate | LRFD | 0.5 | flexural_yield | 0.829 | weld_base_metal | 1.560 | yield, model |
| 202-007 | single_angle | angle outstanding | ASD | 0.5 | shear_yield | 0.847 | bolts | 2.056 |  |
| 202-010 | bolt_bracket | bracket plate | LRFD | 0.5 | flexural_yield | 1.028 | block_shear | 1.149 |  |
| 202-011 | weld_bracket | bracket plate | ASD | 0.5 | flexural_yield | 1.033 | weld_base_metal | 2.020 |  |
| 202-012 | shear_tab | plate | LRFD | 0.5 | shear_yield | 0.871 | bolts | 1.389 | yield, model |
| 202-014 | single_angle | angle outstanding | LRFD | 0.5 | shear_yield | 0.825 | bolts | 2.526 | yield, model |
| 202-017 | weld_bracket | bracket plate | ASD | 0.5 | flexural_yield | 0.949 | weld_base_metal | 1.815 |  |
| 202-019 | shear_tab | plate | LRFD | 0.5 | shear_yield | 0.913 | shear_rupture | 1.125 | yield, model |
| 202-023 | weld_bracket | bracket plate | ASD | 0.5 | flexural_yield | 1.023 | weld_base_metal | 2.006 |  |
| 202-025 | shear_tee | tee stem | ASD | 0.5 | shear_yield | 0.868 | bolts | 1.776 |  |
| 202-026 | shear_end_plate | end plate | LRFD | 0.5 | shear_yield | 0.871 | block_shear | 1.022 | yield, model |
| 202-028 | weld_bracket | bracket plate | ASD | 0.5 | flexural_yield | 0.975 | weld_base_metal | 1.885 |  |
| 202-030 | shear_tab | plate | LRFD | 0.25 | shear_yield | 0.906 | block_shear | 0.864 | yield, model |
| 202-031 | double_angle | angles | LRFD | 0.5 | shear_yield | 0.896 | shear_rupture | 1.171 | yield, model |
| 202-032 | shear_tee | tee stem | LRFD | 0.5 | shear_yield | 0.876 | bolts | 1.625 | yield, model |
| 202-034 | weld_bracket | bracket plate | ASD | 0.5 | flexural_yield | 0.869 | weld_base_metal | 1.640 |  |
| 202-035 | single_angle | angle outstanding | ASD | 0.5 | flexural_yield | 0.799 | bolts | 2.178 |  |
| 202-036 | shear_tee | tee stem | ASD | 0.5 | shear_yield | 0.844 | bolts | 2.385 |  |
| 202-037 | shear_end_plate | end plate | ASD | 0.5 | shear_yield | 0.783 | block_shear | 0.969 |  |
| 202-040 | bolt_bracket | bracket plate | LRFD | 0.5 | flexural_yield | 0.787 | block_shear | 1.148 | yield, model |
| 202-041 | weld_bracket | bracket plate | LRFD | 0.5 | flexural_yield | 0.740 | weld_base_metal | 1.402 | yield, model |
| 202-043 | shear_tab | plate | ASD | 0.5 | shear_yield | 0.916 | shear_rupture | 1.097 |  |
| 202-044 | single_angle | angle outstanding | ASD | 0.5 | shear_yield | 0.904 | bolts | 1.768 |  |
| 202-045 | shear_tee | tee stem | LRFD | 0.5 | flexural_yield | 0.786 | bolts | 2.027 | yield, model |
| 202-047 | weld_bracket | bracket plate | LRFD | 0.5 | flexural_yield | 1.025 | weld_base_metal | 2.006 |  |
| 202-049 | shear_tab | plate | LRFD | 0.25 | shear_yield | 0.928 | shear_rupture | 1.134 | yield, model |
| 202-050 | shear_end_plate | end plate | LRFD | 0.25 | shear_yield | 0.886 | block_shear | 0.880 | yield, model |
| 202-051 | bolt_bracket | bracket plate | ASD | 0.5 | flexural_yield | 0.893 | block_shear | 0.981 |  |
| 202-052 | shear_tab | plate | LRFD | 0.5 | shear_yield | 0.871 | bolts | 1.389 | yield, model |
| 202-053 | double_angle | angles | LRFD | 0.5 | shear_yield | 0.853 | shear_rupture | 1.218 | yield, model |
| 202-054 | shear_tee | tee stem | LRFD | 0.5 | shear_yield | 0.833 | bolts | 2.562 | yield, model |
| 202-055 | shear_end_plate | end plate | ASD | 0.5 | shear_yield | 0.837 | block_shear | 0.888 |  |
| 202-057 | bolt_bracket | bracket plate | LRFD | 0.5 | flexural_yield | 1.038 | block_shear | 0.928 |  |
| 202-059 | shear_tab | plate | ASD | 0.5 | shear_yield | 0.939 | shear_rupture | 1.087 |  |
| 202-060 | double_angle | angles | LRFD | 0.5 | shear_yield | 0.900 | shear_rupture | 1.119 | yield, model |
| 202-061 | shear_tee | tee stem | LRFD | 0.5 | shear_yield | 0.904 | bolts | 1.529 | yield, model |
| 202-063 | bolt_bracket | bracket plate | LRFD | 0.5 | flexural_yield | 0.674 | block_shear | 1.103 | yield, model |
| 202-064 | weld_bracket | bracket plate | ASD | 0.5 | flexural_yield | 0.915 | weld_base_metal | 1.736 |  |
| 202-065 | shear_tab | plate | ASD | 0.5 | shear_yield | 0.911 | block_shear | 0.984 |  |
| 202-066 | double_angle | angles | ASD | 0.5 | shear_yield | 0.869 | shear_rupture | 1.129 |  |
| 202-067 | shear_end_plate | end plate | LRFD | 0.5 | shear_yield | 0.838 | block_shear | 0.954 | yield, model |
| 202-068 | shear_tab | plate | LRFD | 0.5 | shear_yield | 0.912 | shear_rupture | 1.138 | yield, model |
| 202-069 | single_angle | angle outstanding | ASD | 0.5 | shear_yield | 0.889 | bolts | 1.471 |  |
| 202-070 | shear_tee | tee stem | LRFD | 0.5 | shear_yield | 0.857 | bolts | 1.807 | yield, model |
| 202-072 | shear_tab | plate | LRFD | 0.5 | shear_yield | 0.876 | bolts | 1.229 | yield, model |
| 202-073 | double_angle | angles | ASD | 0.5 | shear_yield | 0.870 | shear_rupture | 1.117 |  |
| 202-074 | single_angle | angle outstanding | ASD | 0.5 | shear_yield | 0.909 | bolts | 1.451 |  |
| 202-075 | shear_tee | tee stem | ASD | 0.5 | shear_yield | 0.866 | bolts | 1.577 |  |
| 202-077 | bolt_bracket | bracket plate | LRFD | 0.25 | shear_yield | 0.777 | block_shear | 1.030 | yield, model |
| 202-078 | weld_bracket | bracket plate | ASD | 0.5 | flexural_yield | 1.009 | weld_base_metal | 1.981 |  |
| 202-079 | shear_tab | plate | LRFD | 0.5 | shear_yield | 0.901 | shear_rupture | 1.110 | yield, model |
| 202-080 | single_angle | angle outstanding | LRFD | 0.5 | shear_yield | 0.872 | bolts | 1.553 | yield, model |
| 202-082 | bolt_bracket | bracket plate | LRFD | 0.5 | flexural_yield | 1.060 | block_shear | 0.912 |  |
| 202-084 | shear_tab | plate | LRFD | 0.25 | shear_yield | 0.940 | block_shear | 1.011 | yield, model |
| 202-085 | shear_tee | tee stem | LRFD | 0.5 | flexural_yield | 0.779 | bolts | 2.774 | yield, model |
| 202-086 | bolt_bracket | bracket plate | ASD | 0.5 | flexural_yield | 0.890 | block_shear | 0.952 |  |
| 202-087 | weld_bracket | bracket plate | ASD | 0.5 | flexural_yield | 0.836 | weld_base_metal | 1.578 |  |
| 202-088 | shear_end_plate | end plate | ASD | 0.5 | shear_yield | 0.865 | block_shear | 0.990 |  |
| 202-091 | bolt_bracket | bracket plate | LRFD | 0.5 | flexural_yield | 1.040 | block_shear | 1.104 |  |
| 202-092 | weld_bracket | bracket plate | ASD | 0.5 | flexural_yield | 0.752 | weld_base_metal | 1.421 |  |
| 202-094 | shear_tab | plate | ASD | 0.5 | shear_yield | 0.873 | bolts | 1.301 |  |
| 202-095 | double_angle | angles | LRFD | 0.5 | shear_yield | 0.851 | shear_rupture | 1.217 | yield, model |
| 202-097 | weld_bracket | bracket plate | LRFD | 0.5 | flexural_yield | 0.776 | weld_base_metal | 1.464 | yield, model |
| 202-099 | shear_tab | plate | ASD | 0.5 | shear_yield | 0.899 | shear_rupture | 1.139 |  |

## What would sharpen the check

- **Push the rupture run until a hole stretches 0.25 in.** Then every rupture ratio is the criterion's capacity, not a lower bound.
- **Turn an eccentric bolt group's bolts about the group's centre,** as the brackets already do. Then the model tests the elastic method's weakest-against-most-loaded rule, not only the holes.
- **Model the out-of-plane kinds with shells.** Seats, stiffened seats and hangers are a third of the loop's tasks and are not checked here.

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
