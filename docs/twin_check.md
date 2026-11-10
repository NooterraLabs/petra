# The clean-room twin against Petra on the gate stream

`twin/` is a second implementation of the steel connection limit states, written from AISC 360-22 and the Companion design examples by an agent that never saw Petra's code. Its done test is its disagreement with Petra on the 10,000-design steel gate stream. This page runs that test, gives every disagreement a cause, and checks each cause by hand against the Specification.

Every number carries a label. **Measured** means run or read on 2026-11-08 for this page. **Inferred** means reasoned from measured facts. **Guess** means neither. The twin is frozen at commit 457f36a, and this page changes nothing in it or in Petra.

The run predates the split of a design into a card and a design. Where this page says card, outside the two examples, it means a design together with its load, as one file held them then.

## Outcome

1. **Petra passes bolt brackets that tear out toward the plate's back edge.** Petra runs a bracket bolt's tearout clear distance vertically only. Under an eccentric load the top and bottom bolts push almost horizontally toward the plate's back edge, and J3.11a takes lc in the direction of the force. 8 designs in the stream pass in Petra and fail this way, at utilisations from 1.0003 to 1.299 (measured). The first card below is gate-1-06718 cut to its essentials.
2. **Petra reads a weld bracket's eccentricity from the weld line, and its reference says from the centroid.** The language reference defines `eccentricity` as the load's distance from the weld's centroid. Petra's code measures it from the vertical weld line, so a bracket with returns gets a moment arm short by the weld group's x̄. Read as the reference says, 27 designs that Petra passes fail at section B-B, by up to 10.2% (measured). Which side changes is the maintainer's call. The second card below shows it.
3. **The twin does not pass its done test.** No threshold was set, so this page proposes one (§ The done test). The twin fails it on seven twin errors, five of them unsafe (measured). It also reads no card with a toleranced length, 921 of the stream (measured).
4. **Most verdict disagreements are Petra checking more or checking more conservatively.** Of 1,545 designs that Petra fails and the twin passes, 969 fail a limit state the twin does not check, mostly geometry, fit and fatigue (measured). 613 fail an eccentric bolt or weld group that Petra checks by the elastic method and the twin by the instantaneous centre (IC) (measured).
5. **A hand check found a shared false PASS that the comparison cannot see.** Petra's minimum edge distance omits J3.5's increment C2 for oversized and slotted holes, and the twin checks no geometry. Two bracket plates in the stream with long slots and a 1-1/2 in back edge pass both (measured).

## Petra false PASS designs

### Tearout toward a bracket's back edge

The design:

```
petra 0

bolt_bracket c1 {
  basis lrfd
  plate steel.A36 thickness 0.5 inch
  support W14x61 flange grade steel.A992
  bolts bolt_group.150 diameter 1 inch threads excluded
  rows 2
  columns 1
  pitch 3 inch
  gauge 3 inch
  eccentricity 6 inch
  edge_vertical 2 inch
  plate_edge 1.5 inch
}
```

Its card:

```
petra 0

card "tearout-back-edge" {
  owner "twin@petra.dev"
}

load gate {
  on c1 shear in [0 kip, 16 kip]
  signed "twin@petra.dev" source "twin check"
}
```

Petra passes it, with the bolt group at 0.879 and edge distances at 0.833 (measured). The hand check, by Manual Part 7's IC with each bolt's own force direction:

- The IC sits 0.375 in behind the bolt line. C = 0.476 per unit of bolt strength, and the top bolt carries 2.062 times the load, 32.98 kips at 16 kips (measured).
- That force points 14.04 degrees above the horizontal, back toward the plate's back edge 1-1/2 in away. Along it the clear distance to the edge is 1.5 / cos 14.04 deg less half the 1-1/8 in hole (Table J3.3), so lc = 0.984 in (measured).
- J3.11a, Eq. J3-6c, gives φrn = 0.75 x 1.2 x 0.984 x 0.5 x 58 = 25.67 kips. Bolt shear (J3.7, Fnv 84 ksi from Table J3.2) is 49.5 kips and bearing (Eq. J3-6a) 52.2 kips.
- u = 32.98 / 25.67 = 1.285 (measured). The elastic method gives the same top-bolt force here, so the instantaneous-centre fix of the false-FAIL branch does not close this gap (measured).

Petra's tearout for this bolt runs vertically to the top edge, lc = 2 − 0.5625 = 1.4375 in, which gives 37.5 kips (measured). The twin fails the design at 1.373, because it takes II.A-22's least edge distance for every bolt (measured).

### A weld bracket's moment arm

The design:

```
petra 0

weld_bracket c1 {
  basis asd
  plate steel.A36 thickness 0.75 inch
  support W12x50 flange grade steel.A992
  weld electrode.E70 size 0.3125 inch sides 1
  weld_length 14 inch
  weld_return 3 inch
  eccentricity 8 inch
  free_edge 6 inch
}
```

Its card:

```
petra 0

card "bracket-arm" {
  owner "twin@petra.dev"
}

load gate {
  on c1 shear in [0 kip, 30 kip]
  signed "twin@petra.dev" source "twin check"
}
```

Petra passes it, with section B-B at 0.911 (measured). The weld group's centroid lies x̄ = kl² / (2kl + l) = 9 / 20 = 0.45 in from the vertical weld (Manual Part 8). With e measured from the centroid as `docs/reference.md` defines it, the arm to section A-A is 8 + 0.45 − 3 = 5.45 in. Petra uses 8 − 3 = 5.00 in. At the gate's design gate-1-00009, the hand check of Manual Part 15's free-edge section gives θ = 23.2 degrees, λ = 0.354 so Q = 1, and u = 1.038 at the 5.45 in arm against 0.927 at 5.00 in (measured). This design, at 30 kips, gives 1.021 in the twin (measured).

All 31 of the twin's B-B failures on weld brackets come back exactly when Petra is rerun with the eccentricity moved out by x̄ (measured). So the arm is the whole cause. II.A-23 states its load 11-1/4 in from the vertical weld, which matches Petra's code. Its table quantity al = 10.9 in is measured from the centroid, which matches the reference.

### Edge distance for slotted holes, missed by both

Bracket gate-1-01460 has a 3/4 in A36 plate with long slots, 1 in bolts and a back edge 1-1/2 in from the bolt line. J3.5 asks for Table J3.4's 1-1/4 in plus C2 = 3/4 d = 3/4 in for a long slot perpendicular to the edge, 2 in in all. Petra's `edge_min` applies Table J3.4 alone and passes it at 0.833, and the twin checks no geometry (measured). gate-1-05332 is the same detail in a snug-tight joint. Both joints are bearing-type, where J3.3 also allows long slots only with the load across the slot. A bracket bolt's force runs nearly along a horizontal slot (inferred), and Petra's `hole_use` passes both (measured).

## Run it

```bash
python scripts/twin_check.py --workers 7 --full twin_full.jsonl   # the stream, about 12 minutes
python scripts/twin_check.py --rows docs/twin_check_log.jsonl     # the tables on this page, from the log
```

The script generates the gate's stream as `scripts/steel_gate.py` does, seed 1, and checks each design with Petra and with the twin. For each limit state it takes Petra's largest utilisation over the design's box and the twin's largest over its checks, folding the twin's per-ply bearing into the bolt group as Petra does. Two utilisations agree when they are on the same side of 1 and within 1% of the larger. `docs/twin_check_log.jsonl` keeps one compact line per design, with both verdicts, each shared limit state and the cause of each disagreement.

The twin rejects a toleranced length as an input error. For those 921 designs the script runs the twin at both ends of the interval and keeps each check's worse reading (measured).

The stream took 721 s on the 8-thread PC with 7 worker processes (measured). Per design, inside a worker, generation took 0.251 s, Petra 0.211 s and the twin 0.035 s on average (measured). So the twin runs about 6 times faster than Petra (measured). A second run of the committed script reproduced every line of the log but its timings, in 1,200 s while other jobs shared the PC (measured).

## Counts

The twin checked 7,992 designs and declined 2,008 (measured).

| kind | twin status | reason | designs |
|---|---|---|---|
| flange_force | unsupported | the twin has no model for flange_force | 909 |
| stiffened_seat | unsupported | the twin has no model for stiffened_seat | 909 |
| shear_tab | unsupported | extended or multi-column single plates are not modeled | 190 |

Verdicts, on the designs the twin checked (measured).

| kind | both PASS | both FAIL | Petra FAIL, twin PASS | Petra PASS, twin FAIL |
|---|---|---|---|---|
| shear_tab | 465 | 0 | 255 | 0 |
| double_angle | 609 | 121 | 175 | 4 |
| shear_end_plate | 605 | 212 | 92 | 0 |
| single_angle | 619 | 6 | 284 | 0 |
| shear_tee | 596 | 38 | 275 | 0 |
| seated | 691 | 146 | 72 | 0 |
| bolt_bracket | 641 | 89 | 167 | 12 |
| weld_bracket | 628 | 104 | 150 | 27 |
| hanger | 597 | 230 | 75 | 7 |
| all | 5451 | 946 | 1545 | 50 |

The governing limit state, the most utilised one both sides check, is the same in 6,775 of 7,992 designs (measured).

| kind | same governing limit state | another |
|---|---|---|
| shear_tab | 432 | 288 |
| double_angle | 828 | 81 |
| shear_end_plate | 896 | 13 |
| single_angle | 448 | 461 |
| shear_tee | 683 | 226 |
| seated | 909 | 0 |
| bolt_bracket | 834 | 75 |
| weld_bracket | 844 | 65 |
| hanger | 901 | 8 |

Each limit state that both sides check, by outcome (measured).

| kind | limit state | agree | apart | twin fails, Petra holds | Petra fails, twin holds |
|---|---|---|---|---|---|
| shear_tab | block_shear | 22 | 697 | 0 | 1 |
| shear_tab | bolts | 0 | 583 | 0 | 137 |
| shear_tab | cope_buckling | 164 | 0 | 0 | 0 |
| shear_tab | shear_rupture | 690 | 30 | 0 | 0 |
| shear_tab | shear_yield | 687 | 33 | 0 | 0 |
| shear_tab | slip | 0 | 93 | 0 | 21 |
| shear_tab | weld | 720 | 0 | 0 | 0 |
| shear_tab | weld_base_metal | 0 | 720 | 0 | 0 |
| double_angle | block_shear | 834 | 67 | 0 | 8 |
| double_angle | bolts | 709 | 192 | 7 | 1 |
| double_angle | cope_buckling | 245 | 0 | 0 | 0 |
| double_angle | shear_rupture | 593 | 299 | 0 | 17 |
| double_angle | shear_yield | 674 | 235 | 0 | 0 |
| double_angle | slip | 170 | 0 | 0 | 0 |
| shear_end_plate | block_shear | 845 | 59 | 0 | 5 |
| shear_end_plate | bolts | 864 | 43 | 2 | 0 |
| shear_end_plate | shear_rupture | 909 | 0 | 0 | 0 |
| shear_end_plate | shear_yield | 704 | 205 | 0 | 0 |
| shear_end_plate | slip | 198 | 0 | 0 | 0 |
| shear_end_plate | weld | 909 | 0 | 0 | 0 |
| shear_end_plate | weld_base_metal | 856 | 53 | 0 | 0 |
| single_angle | block_shear | 20 | 861 | 0 | 28 |
| single_angle | bolts | 6 | 794 | 0 | 109 |
| single_angle | cope_buckling | 247 | 0 | 0 | 0 |
| single_angle | flexural_rupture | 414 | 197 | 0 | 0 |
| single_angle | flexural_yield | 611 | 0 | 0 | 0 |
| single_angle | shear_rupture | 887 | 22 | 0 | 0 |
| single_angle | shear_yield | 894 | 15 | 0 | 0 |
| single_angle | slip | 0 | 185 | 0 | 14 |
| shear_tee | block_shear | 200 | 703 | 0 | 6 |
| shear_tee | bolts | 17 | 725 | 0 | 167 |
| shear_tee | cope_buckling | 232 | 0 | 0 | 0 |
| shear_tee | flexural_rupture | 626 | 283 | 0 | 0 |
| shear_tee | flexural_yield | 909 | 0 | 0 | 0 |
| shear_tee | shear_rupture | 891 | 18 | 0 | 0 |
| shear_tee | shear_yield | 844 | 65 | 0 | 0 |
| shear_tee | slip | 0 | 168 | 0 | 7 |
| seated | bolts | 298 | 245 | 0 | 0 |
| seated | seat_flexure | 896 | 13 | 0 | 0 |
| seated | shear_yield | 709 | 200 | 0 | 0 |
| seated | web_crippling | 909 | 0 | 0 | 0 |
| seated | web_local_yielding | 909 | 0 | 0 | 0 |
| bolt_bracket | bolts | 52 | 765 | 17 | 75 |
| bolt_bracket | bracket_edge | 367 | 7 | 0 | 0 |
| bolt_bracket | flexural_rupture | 729 | 180 | 0 | 0 |
| bolt_bracket | flexural_yield | 909 | 0 | 0 | 0 |
| bolt_bracket | shear_rupture | 909 | 0 | 0 | 0 |
| bolt_bracket | shear_yield | 909 | 0 | 0 | 0 |
| weld_bracket | bracket_edge | 200 | 130 | 31 | 0 |
| weld_bracket | flexural_yield | 483 | 426 | 0 | 0 |
| weld_bracket | shear_yield | 909 | 0 | 0 | 0 |
| weld_bracket | weld | 483 | 325 | 0 | 101 |
| hanger | bolt_combined | 54 | 4 | 0 | 0 |
| hanger | bolt_tension | 909 | 0 | 0 | 0 |
| hanger | bolts | 196 | 57 | 0 | 0 |
| hanger | prying | 793 | 99 | 13 | 4 |
| hanger | shear_rupture | 909 | 0 | 0 | 0 |
| hanger | shear_yield | 909 | 0 | 0 | 0 |
| hanger | tension_yield | 909 | 0 | 0 | 0 |

## Why they disagree

A disagreement is a verdict that differs or a limit state on opposite sides of 1. There are 771 of the second kind and 1,595 of the first (measured). Each has a cause from the table, set by a rule in `scripts/twin_check.py` that reads the card and both readings. No disagreement is left unclassified (measured). The classes split the brief's four, twin error, Petra error, coverage and ambiguity, by which side is safe.

| class | cause | what differs | twin fails, Petra holds | Petra fails, twin holds | verdicts it splits | examples |
|---|---|---|---|---|---|---|
| Petra error, unsafe | `tearout-direction` | bracket bolt pushed toward the plate's back edge, whose tearout Petra never checks | 11 | 0 | 8 | gate-1-00096, gate-1-00855, gate-1-01108 |
| Petra error, unsafe | `weld-arm` | weld bracket eccentricity read from the weld line, where the reference says the centroid | 31 | 0 | 27 | gate-1-00009, gate-1-00295, gate-1-00713 |
| twin error, unsafe | `partial-block` | block shear through fewer rows than the group, which the twin does not check | 0 | 33 | 28 | gate-1-00311, gate-1-00354, gate-1-00430 |
| twin error, unsafe | `prying-shear` | hanger prying under shear, which the twin computes from Fnt instead of F'nt | 0 | 4 | 4 | gate-1-07479, gate-1-08084, gate-1-08447 |
| Petra error, conservative | `uncoped-web-rupture` | uncoped beam web checked for shear rupture of its net section | 0 | 17 | 12 | gate-1-01123, gate-1-01376, gate-1-03598 |
| Petra error, conservative | `eccentric-method` | eccentric bolt or weld group by Petra's elastic method against the twin's IC | 0 | 631 | 613 | gate-1-00000, gate-1-00053, gate-1-00057 |
| twin error, conservative | `bracket-least-edge` | every bracket bolt given II.A-22's least edge distance | 5 | 0 | 3 | gate-1-01141, gate-1-02087, gate-1-03374 |
| twin error, conservative | `slot-in-tearout` | a bracket's parallel slot length taken into the back edge's clear distance | 1 | 0 | 1 | gate-1-04144 |
| twin error, conservative | `web-end-bolt` | a continuous web's end bolt taken as an interior bolt | 9 | 0 | 4 | gate-1-00631, gate-1-01332, gate-1-04654 |
| ambiguity | `hanger-slot` | a slot in a hanger flange, whose orientation the card does not fix | 13 | 0 | 7 | gate-1-00747, gate-1-01363, gate-1-02606 |
| ambiguity | `filler-thickness` | fillers declared without a thickness | 0 | 1 | 0 | gate-1-01926 |
| coverage | `impossible-layout` | a bolt line off its angle leg, which only Petra's geometry modes see | 0 | 15 | 15 | gate-1-00068, gate-1-00112, gate-1-00343 |
| coverage | `petra-only` | a limit state Petra checks and the twin does not | 0 | 0 | 969 | gate-1-00011, gate-1-00058, gate-1-00067 |

A design can split on more than one cause, so the verdict column sums to more than 1,595.

### The hand checks, two per cause where the stream has two

- **`tearout-direction`.** gate-1-06718 by hand gives u = 1.299 (measured), worked as the first card above. gate-1-00096 gives 1.209, with the top bolt's force at 172.9 degrees, lc = 0.949 in and φrn = 30.97 kips (measured). The script's `bracket_tearout` repeats the hand method for every bracket the twin fails. 11 fail it and 5 pass it (measured). All 63 standard-hole brackets that Petra fails and the twin passes pass it (measured).
- **`weld-arm`.** gate-1-00009 by hand, worked above. gate-1-02924 has arms 3.45 and 3.00 in, with u = 1.067 and 0.847 (measured). Moving e by x̄ reproduces the twin's B-B reading on all 31 (measured).
- **`partial-block`.** J4.3 holds every shear path with its tension path. gate-1-00430's double angles carry a third of 28.3 kips on the bottom bolt. The block below that bolt has Agv = 1.25 x 5/16 in², and its tension path to the toe is 1/32 in net, after half the long slot and the extra 1/16 in of B4.3b. Rn/Ω = 9.00 kips against 9.43 (measured). gate-1-04316's end plate gives 5.08 kips against 5.37 on its top bolt's block, whose side edge of 3/4 in also fails Table J3.4 (measured). The twin checks the block through every row only.
- **`prying-shear`.** II.A-1B reduces each bolt's tension to F'nt by J3.8 before it enters Manual Eq. 9-30 and Q Tc. The twin uses the full Fnt and checks the combination apart. At gate-1-07479 the twin's tension with prying is 22.6 kips per bolt and Petra's 19.1 (measured). gate-1-08084 is the same at 27.4 and 26.1 (measured).
- **`uncoped-web-rupture`.** II.A-1A states that shear rupture and block shear of the beam do not apply when the beam is not coped. Petra checks the uncoped web's net section anyway, failing gate-1-01123 at 1.046 and gate-1-07965 at 1.056, where the twin's governing angle rupture is 0.75 and 0.56 (measured).
- **`eccentric-method`.** gate-1-00000's shear tab, by Petra's elastic method at e = a = 3.5 in, puts 13.61 kips on its most loaded bolt against a weakest bolt of 13.33 kips, u = 1.021 (measured). II.A-17A's IC at e = a/2 gives C = 3.442, so u = 0.690 with the weakest bolt and 0.631 in the twin (measured). gate-1-00057's single angle support leg gives Petra 1.024, IC at e = 2.9 in times the weakest bolt 0.970, and the twin 0.451 (measured). The twin's 0.451 scales the sum of the bolts' strengths by C / n. II.A-28A instead multiplies C by the least bolt strength, which is the reading the twin should use (inferred).
- **`bracket-least-edge`.** gate-1-03374 and gate-1-04155 give 0.878 and 0.898 with lc taken along each bolt's force (measured). The twin's least edge distance is II.A-22's simplification, which that example calls conservative.
- **`slot-in-tearout`.** gate-1-04144 is the stream's one case. The twin's lc of 0.25 in mixes the back edge with the parallel slot's length. A hand check with the least clear distance between slots, 0.5 in, gives 0.674, so Petra's PASS at 0.803 stands (measured).
- **`web-end-bolt`.** At gate-1-04654 the top bolt in the uncoped beam web pushes up toward the beam's top, 3 in away, so lc = 2.44 in and bearing governs at 29.25 kips. The twin takes s − dh = 1.875 in, 27.42 kips (measured). At gate-1-00631 the bottom bolt in the support's web has no edge below it, and the twin again takes the interior value (measured). II.A-1A gives only the non-edge value for its beam web, where bearing governs every bolt (inferred).
- **`hanger-slot`.** Manual Part 9's δ = 1 − d'/p needs the hole's size along the tee's length. A hanger's force is normal to its flanges, and its card fixes no direction for a slot in them. Petra took a plain slot's width, 13/16 in, and the twin its length, 1 in. At gate-1-02947 that gave δ = 0.768 against 0.714, and 65.4 kips against 63.4 (measured). gate-1-06302 was the same on the support flange (measured). Since 2026-11-09 Petra reads such a slot the worse way in every check. The run at commit 140f742 had 11 hanger-slot designs, 5 of them Petra PASS and twin FAIL (measured). On the same card texts Petra's prying now equals the twin's on all 11, all 11 fail, and no hanger disagrees with the twin (measured). The row above counts an earlier run.
- **`filler-thickness`.** gate-1-01926 is slip critical with one filler. J5.2's reduction applies to bearing-type joints with fillers over 1/4 in, and the card states no thickness. Petra takes the 0.85 floor and the twin no reduction (measured).
- **`impossible-layout`.** gate-1-00068's single angle puts its support bolts 5-1/2 in from the heel of a 5 in leg. Petra's partial block has a negative tension area and its `edge_min` fails (measured). The twin computes only the full block. gate-1-00112 is the same.
- **`petra-only`.** These are limit states the twin leaves out by design (twin/README.md, Not modeled), counted below.

### Limit states apart

These sit on the same side of 1 but differ by more than 1%. Their main causes (inferred from samples, not classified row by row):

- Bolt groups and slip of the shear tab, single angle, tee and brackets, and weld brackets' welds, the `eccentric-method` cause short of a verdict.
- Block shear of the shear tab, single angle and tee. Petra's partial blocks take each bolt's elastic share, and the twin checks the full block only.
- Flexural rupture of single angles, tees and brackets. A hole on the neutral axis removes t h²/4 of Znet, which the twin leaves out. It costs the twin 1% to 4%, and 27.7% at gate-1-00948, whose hole is a long slot parallel to the force (measured). This is a twin error, unsafe.
- Shear yielding and rupture of double angles, end plates and seats. Petra also checks the beam web's gross section, which the twin does not.
- Weld brackets' flexural yielding and section B-B, the `weld-arm` cause short of a verdict.
- The shear tab's `weld_base_metal`. Petra's governing check is the plate's base metal along the weld, which the twin does not check (measured on gate-1-00000).

### Coverage

Designs that Petra fails on a limit state the twin does not check (measured).

| Petra-only failed mode | designs | of which the verdict's only cause |
|---|---|---|
| edge_min | 204 | 148 |
| weld | 178 | 160 |
| beam_fit | 158 | 124 |
| hole_use | 145 | 116 |
| joint_type | 130 | 102 |
| fatigue_bolted | 109 | 103 |
| ductility | 71 | 49 |
| fatigue_weld_end | 49 | 48 |
| web_fit | 47 | 39 |
| edge_max | 44 | 36 |
| flange_fit | 43 | 38 |
| clearance | 42 | 30 |
| slip | 37 | 35 |
| fatigue_weld | 35 | 34 |
| weld_base_metal | 33 | 27 |
| fillet_size | 33 | 25 |
| spacing_min | 20 | 15 |
| block_shear | 10 | 3 |
| web_local_yielding | 8 | 0 |
| fatigue_cope | 6 | 6 |
| plate_buckling | 2 | 0 |

The `weld` rows are welded support sides of angles, tees and seats, which the twin lists as not modeled. The `block_shear` rows and 33 of the 37 `slip` rows are bolt brackets. The twin checks neither there and does not list them as unsupported (measured). The other 4 `slip` rows are slip-critical hangers, which the twin lists. The twin checks two limit states Petra does not, a weld bracket's shear rupture at section A-A on all 909 and a hanger's combined bolt tension and shear on 195 (measured).

## The readings the brief left open

1. **Single-angle support leg, IC or Manual Table 10-11.** Table 10-11 Case I is the IC at e = 2-1/2 in (C = 3.065 against the table's 3.07, measured in twin/README.md). II.A-28A uses it as a bound for e below 2-1/2 in. So the IC at the actual e is a valid and less conservative reading, and Petra's elastic method is conservative. The open point is the twin's C / n scaling of summed bolt strengths, above.
2. **Bracket Znet.** Eq. 15-3 on the actual plate is first principles. II.A-22 reads Table 15-2, which assumes a 1-1/2 in vertical edge, and is conservative there. Both sides use the actual plate and agree on 729 of 909 (measured). The other 180 are the twin's missing t h²/4 term.
3. **Hanger stem Whitmore width.** Shared. Neither side can check it, because the card has no attached member. Both yield the stem over the tee's full length and agree on all 909 (measured). For II.D-1 that gives 121.5 kips against the example's 104 (twin/README.md). The card needs the attached member's width before either side can check it.
4. **Double-cope Cb.** II.A-7 prints Cb = 1.94 for Lb = 9.5 in, d = 16 in and dct = 3.5 in. Only Petra's grouping of Manual Eq. 9-21, [3 + ln(Lb/d)](1 − dct/d), gives it, at 1.937 (measured). The twin's 3 + ln(Lb/d)(1 − dct/d) gives 2.59, so this is a twin error, unsafe. The stream does not show it. All 888 coped-flexure states agree, likely because the plastic moment caps both (inferred).
5. **The 1/4 in underrun.** Both sides take it off the beam web's end distance and add it to a seat's setback. That only lowers strengths, so it cannot hide a false PASS (inferred).

## Under the false-FAIL fixes

Another branch moves eccentric bolt and weld groups to the IC method and changes the one-row seat spacing rule. Neither fix is made here.

- 546 designs fail in Petra only through `eccentric-method`, 146 tees, 129 shear tabs, 112 single angles, 93 weld brackets and 66 bolt brackets (measured). They move to PASS if Petra's IC matches the twin's (inferred). 67 more lose one of several causes (measured).
- Petra's shear tab and tee stem use e = a, and II.A-17A uses e = a/2. If the fix keeps e = a, part of the 129 and 146 stay FAIL (inferred).
- The IC fix does not close `tearout-direction`, whose 8 false PASS designs fail by the IC as well (measured). Of the 63 standard-hole brackets Petra now fails on its bolts, none fails by the IC with tearout along each bolt's force, so the fix adds no false PASS there (measured). The 12 slotted ones were not checked.
- The weld-group fix interacts with `weld-arm`. If the arm moves to the reference's meaning, weld demands rise with it (inferred).
- No seated design in the stream fails `spacing_min`, so the seat rule moves no verdict here (measured). The seated `edge_min` failure sampled is real. gate-1-01424's 6 in seat carries bolts at a 5-1/2 in gauge, which leaves a 1/4 in side edge (measured).

## The done test

The frontier plan names the measure, disagreement with Petra on this stream, but sets no threshold. This is a proposal for the maintainer.

**Proposal.** The twin passes when, on the seed-1 stream,

1. it reads every card the stream holds, with no input error (now 921, measured),
2. every disagreement has a cause that a hand check settled (now true, measured),
3. no cause is a twin error, except a conservative reading a Companion example itself uses (now four in the disagreements and three more found by hand, measured),
4. every Petra-unsafe cause is fixed or registered as a known gap before the steel arena starts (now two open, measured).

Under that proposal the twin does not pass yet. Its errors for the clean-room fix, each read from the clause cited:

- `partial-block`. J4.3 holds every path, so blocks through fewer rows count, with each bolt's share as the demand. Unsafe.
- `prying-shear`. With shear present, the bolt tension in Manual Eqs. 9-30 and Q Tc is F'nt of J3.8, as II.A-1B does. Unsafe.
- The Znet of a hole on the neutral axis, t h²/4. Unsafe, 1% to 28% (measured).
- Double-cope Cb of Manual Eq. 9-21, grouped as II.A-7 computes it. Unsafe.
- An eccentric group's strength as C times the least bolt strength, as II.A-28A does, not C / n times their sum. Unsafe in method; no verdict in the stream turned on it (measured where sampled).
- `web-end-bolt` and `slot-in-tearout`. Conservative.
- Toleranced lengths. The twin should read an interval, or say unsupported.
- Bracket slip and bracket block shear, which the twin neither checks nor lists as unsupported.

II.A-22's least edge distance for every bracket bolt is a conservative reading the Companion uses, so it may stay.

## Files

- `scripts/twin_check.py` runs the stream and prints the tables on this page.
- `docs/twin_check_log.jsonl` holds one line per design, with its verdicts, its shared limit states and each disagreement's cause.
