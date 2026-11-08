# Coped-beam tests against J4.3 and P8's bound

The [block shear pilot](blockshear_pilot.md), phase P8, found that Eq. J4-5 of AISC 360-22 Section J4.3 asks more of a bolted plate than plane-stress plasticity gives. With one line of bolts, J4.3's nominal strength needs a flow stress of 1.14 to 2.01 Fu on P8's mesh. So a J4.3 PASS rests on rupture tests. This page puts the published tests beside both numbers. It takes 25 coped-beam tests, 23 of which failed by block shear. For each it computes Eq. J4-5 and P8's lower bound at the measured Fy, Fu and dimensions, with no resistance factor. A line here is a vertical line of bolts, which the pilot calls a column.

**The tests do not support the claim that J4.3 is unconservative for coped beams.** Three of the 23 block shear failures carried less than J4.3's nominal strength. C1 carried 0.996 of it, 18-10 carried 0.955 and 18-11 carried 0.888 (computed from the measured loads). The one-sided 95 percent upper bound on the share below 1.0 is 0.30. The mean of test over J4.3 is 1.12, with a one-sided 95 percent lower bound of 1.07 (computed). Every test carried at least 1.18 times the design strength 0.75 Rn (computed).

Kulak and Grondin (2001) found the AISC LRFD block shear rule non-conservative for coped beams. The rule they reviewed was the 1999 LRFD rule, which had no Ubs. For Ricles and Yura's two-line coped beams they report a mean of test over that rule of 0.71 (read from their 2002 errata). On the 23 tests here the 1999 rule falls below 1.0 on 11, and on 9 of the 10 with two lines (computed). Eq. J4-5 halves the tension term for two lines (Ubs = 0.5), and with it 2 of those 10 fall below 1.0.

Each of the 19 tests P8's plate holds carried more than P8's lower bound at Fy. The 18 block shear failures among them carried 1.63 to 2.49 times it in bearing contact (computed on the solver's linear programs, which the kernel did not check). So no test refutes the bound. With the flow stress raised to each specimen's Fu, they still carried 1.20 to 1.84 times it. On P8's mesh a real coped web outruns a plane-stress plate at Fu by that much, which fits the premise the pilot named (inferred).

Two limits bound what this says. One model family read every paper, and the tests are among those J4.3 was fitted to. Both are under "What the tests can and cannot say".

## Run it

```
python scripts/coped_beam_check.py solve
python scripts/coped_beam_check.py report
```

`solve` reads `docs/coped_beam_tests.json`. It computes J4.3 and the 1999 rule for every specimen and P8's bound for the 19 that P8's plate holds, and writes `docs/coped_beam_check_log.jsonl`. It took 42 minutes on one core, for 38 linear programs (measured). `--only ID ...` recomputes the named specimens and keeps the rest of the log. `report` prints the tables on this page from the data file and the log. The script needs Python 3.11 with numpy and scipy, and no network.

`tests/test_coped_beam_check.py` runs no linear program. It checks that this page quotes the report, that every J4.3 block the script computes equals the steel deck's on every meshed specimen, and that six Ricles and Yura values match a published computation.

## The tests

`docs/coped_beam_tests.json` holds the numbers. Each specimen names its source and the table or figure each number came from. The file holds numbers only, and no paper text or figure is in the repository.

**The extraction is single-family.** One model family read every source and typed every number, and no second family checked the reading. The checks under "Extraction checks" are its only cross-check.

| Source | Specimens | Read from |
|---|---|---|
| Franchuk, Driver and Grondin (2002), Structural Engineering Report 244, University of Alberta | 17, A1 to J2 | the report, open full text |
| Birkemoe and Gilmor (1978), Engineering Journal 15(4) | 1, I-2 | the paper, an open scan |
| Ricles and Yura (1983), Journal of the Structural Division 109(1) | 7, 18-10 to 18-19 | not the paper. IDEA StatiCa's verification page for block shear to AISC, its Tables 3 and 4 and Figure 28 |
| Kulak and Grondin (2001), Engineering Journal 38(4), and its 2002 errata | none | published means, for the extraction checks |

Fy and Fu come from coupons of each web. The Alberta report gives static and dynamic values, and the data file takes the static means. Its holes are measured. Elsewhere the hole is the standard hole for the bolt, marked (std) below. The load is the largest reaction on the tested connection. Lev runs from the top bolt down to the cope edge, and Leh from the line nearest the beam end to the beam end. s lists the pitches from the top, and g is the gauge between two lines. Five Ricles and Yura specimens have five bolts in two lines of three, with one hole left out. The data file lists the holes each line has.

### Specimens

| Specimen | Source | Lines x rows | t (mm) | Fy (MPa) | Fu (MPa) | Lev (mm) | Leh (mm) | s (mm) | g (mm) | Hole (mm) |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | SER244 | 1 x 4 | 7.03 | 361 | 519 | 26.3 | 24.8 | 75.1/75.3/75.1 |  | 20.6 |
| A2 | SER244 | 1 x 4 | 7.03 | 361 | 519 | 25.2 | 25.3 | 75.1/75.1/74.9 |  | 20.6 |
| B1 | SER244 | 1 x 4 | 7.00 | 367 | 513 | 26.5 | 24.1 | 75.3/75.3/75.6 |  | 20.9 |
| B2 | SER244 | 1 x 4 | 7.00 | 367 | 513 | 25.1 | 26.0 | 74.9/75.1/75.0 |  | 20.7 |
| C1 | SER244 | 1 x 3 | 6.95 | 366 | 516 | 25.6 | 26.2 | 101.6/101.9 |  | 20.7 |
| C2 | SER244 | 2 x 3 | 6.95 | 366 | 516 | 25.1 | 24.9 | 101.9/102.4 | 76.1 | 20.7 |
| D1 | SER244 | 1 x 3 | 6.87 | 377 | 523 | 32.0 | 31.6 | 103.3/103.1 |  | 27.0 |
| D2 | SER244 | 1 x 4 | 6.87 | 377 | 523 | 25.3 | 50.2 | 75.4/75.3/74.8 |  | 20.7 |
| E1 | SER244 | 1 x 4 | 7.01 | 370 | 522 | 24.3 | 50.4 | 74.7/75.1/75.1 |  | 20.6 |
| E2 | SER244 | 1 x 4 | 7.01 | 370 | 522 | 49.4 | 24.2 | 75.3/75.4/75.0 |  | 20.6 |
| F1 | SER244 | 1 x 3 | 6.94 | 368 | 517 | 25.2 | 25.8 | 75.0/75.4 |  | 20.7 |
| G1 | SER244 | 1 x 3 | 7.95 | 368 | 479 | 25.8 | 25.1 | 75.3/75.0 |  | 20.7 |
| G2 | SER244 | 1 x 3 | 7.95 | 368 | 479 | 26.1 | 23.6 | 75.3/75.0 |  | 20.7 |
| H1 | SER244 | 1 x 3 | 6.93 | 355 | 429 | 26.5 | 25.1 | 74.8/75.0 |  | 20.7 |
| H2 | SER244 | 1 x 3 | 6.93 | 355 | 429 | 26.5 | 25.4 | 74.8/75.0 |  | 20.7 |
| J1 | SER244 | 2 x 3 | 7.16 | 378 | 515 | 26.7 | 24.1 | 101.9/101.8 | 76.4 | 20.7 |
| J2 | SER244 | 2 x 2 | 7.16 | 378 | 515 | 27.5 | 24.7 | 75.3 | 75.0 | 20.7 |
| I-2 | BG1978 | 1 x 3 | 7.75 | 362 | 545 | 57.1 | 44.5 | 76.2/76.2 |  | 20.6 (std) |
| 18-10 | RY1983_via_IDEA | 2 x 3, 5 bolts | 11.18 | 264 | 412 | 50.8 | 25.4 | 76.2/76.2 | 76.2 | 20.6 (std) |
| 18-11 | RY1983_via_IDEA | 2 x 3, 5 bolts | 11.18 | 264 | 412 | 50.8 | 38.1 | 76.2/76.2 | 101.6 | 20.6 x 49.2 slot (std) |
| 18-12 | RY1983_via_IDEA | 2 x 3, 5 bolts | 11.18 | 264 | 412 | 50.8 | 50.8 | 76.2/76.2 | 76.2 | 20.6 (std) |
| 18-16 | RY1983_via_IDEA | 2 x 2 | 10.92 | 252 | 400 | 50.8 | 25.4 | 152.4 | 76.2 | 20.6 (std) |
| 18-17 | RY1983_via_IDEA | 2 x 2 | 10.92 | 252 | 400 | 50.8 | 50.8 | 152.4 | 76.2 | 20.6 (std) |
| 18-18 | RY1983_via_IDEA | 2 x 3, 5 bolts | 10.92 | 252 | 400 | 25.4 | 25.4 | 76.2/76.2 | 76.2 | 20.6 (std) |
| 18-19 | RY1983_via_IDEA | 2 x 3, 5 bolts | 10.92 | 252 | 400 | 50.8 | 50.8 | 76.2/76.2 | 76.2 | 20.6 (std) |

### Copes and failures

| Specimen | Bolt (mm) | Cope, length x depth (mm) | End rotation (deg) | Block shear | Failure reported |
|---|---|---|---|---|---|
| A1 | 19.1 | 73.7 x 36.3 | 0 | no | stopped before block shear when the web buckled near the cope on reloading, with necking and cracks on the tension face |
| A2 | 19.1 | 74.9 x 36.4 | 3.5 | yes | block tear-out |
| B1 | 19.1 | 73.3 x 34.9 | 2 | yes | block tear-out |
| B2 | 19.1 | 73.8 x 36.6 | 0 | yes | block tear-out |
| C1 | 19.1 | 74.4 x 36.2 | 0 | yes | block tear-out |
| C2 | 19.1 | 149.5 x 35.5 | 0 | yes | partial tear-out |
| D1 | 25.4 | 79.7 x 36.3 | 0 | yes | block tear-out |
| D2 | 19.1 | 98.4 x 35.1, top and bottom | 0 | no | shear of the web, with both flanges coped and the bottom cope 26.8 mm below the bottom bolt |
| E1 | 19.1 | 99.4 x 37.8 | 0 | yes | block tear-out |
| E2 | 19.1 | 74.8 x 35.9 | 0 | yes | block tear-out |
| F1 | 19.1 | 74.4 x 36.3 | 0 | yes | block tear-out |
| G1 | 19.1 | 74.4 x 37.3 | 0 | yes | block tear-out |
| G2 | 19.1 | 74.5 x 37.3 | 0 | yes | block tear-out |
| H1 | 19.1 | 76.3 x 35.4 | 2 | yes | partial tear-out |
| H2 | 19.1 | 77.5 x 35.6 | 3.5 | yes | partial tear-out |
| J1 | 19.1 | 150.3 x 34.7 | 2 | yes | block tear-out, after the web buckled near the cope and was stiffened |
| J2 | 19.1 | 152.1 x 32.9 | 0 | yes | block tear-out |
| I-2 | 19.1 | 152.4 x not given | not given | yes | incipient block shear, the web split at the lower hole and necked, with local web buckling at the cope, stopped at a level load |
| 18-10 | 19.1 | 203.2 x 38.1 | not given | yes | block shear, as SER244 section 2.2 reports for all seven, four of which also buckled at the cope, not saying which four |
| 18-11 | 19.1 | 203.2 x not given | not given | yes | block shear, horizontal slotted holes |
| 18-12 | 19.1 | 203.2 x 38.1 | not given | yes | block shear |
| 18-16 | 19.1 | 203.2 x 38.1 | not given | yes | block shear |
| 18-17 | 19.1 | 203.2 x 38.1 | not given | yes | block shear |
| 18-18 | 19.1 | 203.2 x 38.1 | not given | yes | block shear |
| 18-19 | 19.1 | 203.2 x 38.1 | not given | yes | block shear |

A1 and D2 did not fail by block shear, so they stay out of the counts below. The Alberta report calls three of its failures partial tear-outs, and Birkemoe and Gilmor stopped I-2 at incipient block shear. These count as block shear failures, as their sources count them.

These tests were found and not extracted:

- Yura, Birkemoe and Ricles (1982), three coped beams. The paper is behind a paywall, and the AISC library copy of the related reports refused automated fetches.
- Aalberg and Larsen (2000), eight coped beams. No open copy was found.
- Fang, Lam, Yam and Seak (2013), ten coped beams with single-sided connections, and Lam, Fang, Yam, Wang and Iu (2015), seventeen with two lines of bolts. Only the publishers hold the full text.
- Yam, Lam and Seak (2011), four coped beams with tee connections. It is a paid download.
- Birkemoe and Gilmor (1978), tests II-1 and II-2. The paper does not say whether their loads are per connection.
- Yam, Zhong, Lam and Iu (2007), ten coped beams with welded clip angles. They are welded, so they fall outside the deck's bolted block and P8's mesh.

## Which Ubs, and why

Section J4.3 sets Ubs = 1 where the tension stress is uniform and Ubs = 0.5 where it is nonuniform. Commentary J4.3 draws the cases in Figure C-J4.2. Part (a), the cases for Ubs = 1, includes a beam end with a single line of bolts. Part (b), the case for Ubs = 0.5, is a coped beam end with more than one line. The Commentary gives the reason for part (b). The bolts nearest the beam end take most of the shear, so the tension plane is not evenly stressed.

So each one-line specimen takes Ubs = 1, and each two-line specimen takes Ubs = 0.5. The Commentary's third value, 1 - e/l, is for conditions the figure does not show, and every specimen here is one it shows. The steel deck and P8 read the clause the same way. They take Ubs = 1 for a block of one line, and the registry's `aisc360.j4_3.ubs_nonuniform`, 0.5, for a block of two.

## J4.3 against the tests

J4.3 here is Eq. J4-5 on the block the tests tore out. Its shear plane runs down the line farther from the beam end, from the cope edge to the bottom bolt. Its tension plane runs from there to the beam end. Each hole takes the 1/16 in allowance of Section B4.3b on the net areas, and a slotted hole takes its slot length on the tension plane. The value is the nominal strength Rn at the measured Fy and Fu.

The steel deck computes J4.3 another way. It checks every block of the first k rows and first j lines, gives every bolt an equal share of the load, and keeps the least. On 10 of the 13 one-line failures its least block is the top bolt alone, at 0.63 to 0.81 of the whole block's strength (computed). The tests tore out the whole block, so this page compares them with it. The deck's value is never above the whole block's, and the readings table gives it too.

### Block shear failures

| Specimen | Ubs | Test (kN) | J4.3 (kN) | Test / J4.3 | Bound at Fy (kN) | Test / bound | J4.3 / bound | Test / confined bound |
|---|---|---|---|---|---|---|---|---|
| A2 | 1 | 496.0 | 429.8 | 1.154 | 213.9 | 2.32 | 2.01 | 2.11 |
| B1 | 1 | 514.0 | 421.1 | 1.221 | 216.5 | 2.37 | 1.94 | 2.20 |
| B2 | 1 | 475.0 | 424.1 | 1.120 | 218.3 | 2.18 | 1.94 | 1.97 |
| C1 | 1 | 402.0 | 403.6 | 0.996 | 161.8 | 2.48 | 2.49 | 2.19 |
| C2 | 1/2 | 537.0 | 471.3 | 1.139 | 307.0 | 1.75 | 1.54 | 1.66 |
| D1 | 1 | 448.0 | 422.1 | 1.061 | 207.4 | 2.16 | 2.03 | 1.99 |
| E1 | 1 | 568.0 | 520.5 | 1.091 | 228.6 | 2.49 | 2.28 | 1.91 |
| E2 | 1 | 517.0 | 476.1 | 1.086 | 227.5 | 2.27 | 2.09 | 2.06 |
| F1 | 1 | 324.0 | 310.7 | 1.043 | 158.0 | 2.05 | 1.97 | 1.89 |
| G1 | 1 | 379.0 | 328.2 | 1.155 | 180.8 | 2.10 | 1.81 | 1.94 |
| G2 | 1 | 387.0 | 323.2 | 1.198 | 178.1 | 2.17 | 1.81 | 2.04 |
| H1 | 1 | 324.0 | 256.6 | 1.263 | 152.9 | 2.12 | 1.68 | 1.97 |
| H2 | 1 | 341.0 | 257.5 | 1.324 | 153.3 | 2.22 | 1.68 | 2.06 |
| J1 | 1/2 | 667.0 | 497.8 | 1.340 | 329.9 | 2.02 | 1.51 | 1.92 |
| J2 | 1/2 | 338.0 | 275.6 | 1.226 | 206.8 | 1.63 | 1.33 | 1.58 |
| I-2 | 1 | 498.2 | 493.2 | 1.010 | 200.6 | 2.48 | 2.46 | 1.86 |
| 18-10 | 1/2 | 493.8 | 516.8 | 0.955 | not meshed | | |  |
| 18-11 | 1/2 | 449.3 | 505.9 | 0.888 | not meshed | | |  |
| 18-12 | 1/2 | 676.1 | 575.2 | 1.175 | not meshed | | |  |
| 18-16 | 1/2 | 493.8 | 485.1 | 1.018 | 244.4 | 2.02 | 1.98 | 1.81 |
| 18-17 | 1/2 | 582.7 | 540.6 | 1.078 | 262.8 | 2.22 | 2.06 | 1.69 |
| 18-18 | 1/2 | 449.3 | 443.1 | 1.014 | not meshed | | |  |
| 18-19 | 1/2 | 596.1 | 540.6 | 1.103 | not meshed | | |  |

### Other failures

| Specimen | Test (kN) | J4.3 (kN) | Test / J4.3 | Bound at Fy (kN) | Failure |
|---|---|---|---|---|---|
| A1 | 439.0 | 431.2 | 1.018 | 214.4 | stopped before block shear when the web buckled near the cope on reloading, with necking and cracks on the tension face |
| D2 | 529.0 | 512.8 | 1.032 | not meshed | shear of the web, with both flanges coped and the bottom cope 26.8 mm below the bottom bolt |

### Test over J4.3

| Group | Specimens | Below 1.0 | 95% upper bound on the share below 1.0 | Mean | CoV | 95% lower bound on the mean | Least |
|---|---|---|---|---|---|---|---|
| one line, Ubs = 1 | 13 | 1 | 0.32 | 1.13 | 0.09 | 1.08 | 0.996 |
| two lines, Ubs = 0.5 | 10 | 2 | 0.51 | 1.09 | 0.12 | 1.02 | 0.888 |
| all | 23 | 3 | 0.30 | 1.12 | 0.10 | 1.07 | 0.888 |

With one line, 1 of 13 tests falls below 1.0, and C1 carried 0.996 of J4.3. With two lines, 2 of 10 fall below 1.0. Both are Ricles and Yura tests. 18-10 has a 1 in edge distance Leh and five bolts. 18-11 has horizontal slots across its tension plane. The upper bounds are wide because the samples are small. One test below 1.0 in 13 is consistent with a true share up to 0.32, and two in 10 with a share up to 0.51 (computed).

### Test over J4.3 under other readings, and over the 1999 rule

| Rule | One line, below 1.0 | One line, mean | Two lines, below 1.0 | Two lines, mean | All, below 1.0 | All, mean |
|---|---|---|---|---|---|---|
| J4.3, whole block, B4.3b allowance (the tables above) | 1 of 13 | 1.13 | 2 of 10 | 1.09 | 3 of 23 | 1.12 |
| J4.3, whole block, no allowance | 1 of 13 | 1.10 | 2 of 10 | 1.08 | 3 of 23 | 1.09 |
| J4.3, the deck's least block, B4.3b allowance | 0 of 13 | 1.41 | 2 of 10 | 1.11 | 2 of 23 | 1.28 |
| the 1999 LRFD rule, no Ubs, whole block | 2 of 13 | 1.13 | 9 of 10 | 0.78 | 11 of 23 | 0.97 |

The hole allowance moves the one-line mean from 1.10 to 1.13 and changes no count. The deck's least block puts no one-line test below 1.0. The 1999 rule puts 9 of the 10 two-line tests below 1.0. There it is mostly Eq. J4-5 with Ubs = 1, so Ubs is the main difference (inferred).

The Alberta report's dynamic yield values run 2 to 5 percent above its static ones (measured, its Table 3-4). Had the data file taken Fy and Fu 5 percent higher for every Alberta beam, each Alberta ratio would fall by 5 percent. F1 would then join C1 below 1.0, at 0.993 (computed).

## P8's bound against the tests

For each specimen P8's plate holds, the script builds P8's statement and runs P8's solver, unchanged. It uses P8's mesh and 2 in margin and holds the plate's two far edges, as the pilot does. It takes the measured hole with no allowance, and a small registry view hands the model the specimen's Fy, Fu and hole. The as-built pitches differ by under a millimetre, so the plate takes their mean, which keeps the whole block's length. P8's plate is a full rectangle of round holes with one free end edge. So the five Ricles and Yura specimens with a missing bolt or a slot get no bound, and neither does D2 with its bottom cope.

"Bound" is P8's lower bound at Fy in bearing contact. "Confined bound" uses the pilot's confined contact. "Test / bound at Fu" sets the flow stress to the specimen's Fu.

### Test over P8's bound

| Group | Specimens | Test / bound | J4.3 / bound | Test / confined bound | Test / bound at Fu |
|---|---|---|---|---|---|
| one line, Ubs = 1 | 13 | 2.05 to 2.49 | 1.68 to 2.49 | 1.86 to 2.20 | 1.46 to 1.84 |
| two lines, Ubs = 0.5 | 5 | 1.63 to 2.22 | 1.33 to 2.06 | 1.58 to 1.92 | 1.20 to 1.48 |
| all | 18 | 1.63 to 2.49 | 1.33 to 2.49 | 1.58 to 2.20 | 1.20 to 1.84 |

Every test sits above the bound in both contacts. The 18 block shear failures carried 1.63 to 2.49 times the bound at Fy, and A1 carried 2.05 times it before its test stopped (computed). So no test refutes the bound. A test below it would mean the web gave way before a plane-stress plastic plate at Fy could. The lower-bound theorem rules that out while the model's premises hold.

The tests stay above the bound with the flow stress at Fu. They carried 1.46 to 1.84 times it with one line and 1.20 to 1.48 times it with two (computed). So these webs carried what J4.3 asks beyond a plane-stress plate at Fu. The pilot names two effects such a plate lacks, bearing confined through the thickness and strain hardening past Fy. The tests cannot separate those from the slack in the bound itself, which a finer mesh would shrink (inferred).

"J4.3 / bound" uses the whole block. The pilot's ratios use the deck's least block, which is lower on most one-line specimens, so the two are not the same number.

## Extraction checks

Two published computations check the reading. Kulak and Grondin's errata and the Alberta report's Table 5-1 each give the mean of test over the 1999 LRFD rule for each family. The script recomputes that rule on the extracted numbers. IDEA StatiCa's page gives Eq. J4-5 for each Ricles and Yura specimen at measured properties.

### Extraction check against published means of the 1999 LRFD rule

| Family | Specimens here | Mean here | Published | Where |
|---|---|---|---|---|
| SER244 | 17 | 1.09 | 17 tests, mean 1.11, CoV 0.13 | SER244 Table 5-1, AISC LRFD 1999 column, all 17 Alberta tests |
| SER244 | 17 | 1.09 | 17 tests, mean 1.06, sd 0.12 | KG2001 errata, Table 1 Revised, Franchuk et al. row |
| RY1983_via_IDEA | 7 | 0.71 | 7 tests, mean 0.71, CoV 0.11 | SER244 Table 5-1, AISC LRFD 1999 column |
| RY1983_via_IDEA | 7 | 0.71 | 7 tests, mean 0.71, sd 0.08 | KG2001 errata, Table 1 Revised, Ricles and Yura row |
| BG1978 | 1 | 0.97 | 1 test, mean 0.98 | SER244 Table 5-1, AISC LRFD 1999 column |
| BG1978 | 1 | 0.97 | 1 test, mean 0.95 | KG2001 errata, Table 1 Revised, Birkemoe and Gilmor row |

The Alberta mean here falls between the two published means, and the other two families match within 0.02. The two published Alberta means differ by 0.05 on the same 17 tests, so this check cannot settle the reading more finely than that (computed).

### Ricles and Yura, J4.3 here and on the IDEA page

| Specimen | J4.3 here (kip) | IDEA P_AISC (kip) |
|---|---|---|
| 18-10 | 116.2 | 116.2 |
| 18-11 | 113.7 | 133.4 |
| 18-12 | 129.3 | 129.3 |
| 18-16 | 109.1 | 109.1 |
| 18-17 | 121.5 | 121.5 |
| 18-18 | 99.6 | 99.6 |
| 18-19 | 121.5 | 121.5 |

Six of the seven values match to 0.1 kip. 18-11 does not. Its tension plane crosses horizontal slots, which the Alberta report's review of the tests gives as 49 mm by 21 mm, so the data file takes a slot 1-15/16 in long. IDEA's value matches a slot of 15/16 in. The gap of 19.7 kip is exactly 0.5 Fu t times the extra 1.5 in of slot on the tension plane (computed). Under IDEA's reading 18-11 would carry 0.757 of J4.3 instead of 0.888 (computed). It falls below 1.0 either way.

## What the tests can and cannot say

- **The tests are not independent of J4.3.** Commentary J4.3 cites Birkemoe and Gilmor (1978) and Ricles and Yura (1983). It also cites Kulak and Grondin (2001), whose 2002 errata added the Alberta tests to their review. So these 23 tests check that this reading reproduces the fit on the evidence behind it. They do not test J4.3 out of sample (inferred).
- **The two-line evidence is mostly one lab's.** Seven of the ten two-line tests are Ricles and Yura's, read through a secondary page with standard holes. Lam et al. (2015) ran seventeen two-line tests a decade after Ubs entered the Specification in 2005, so they could test Ubs = 0.5 on new evidence. Their full text was not open.
- **The extraction is single-family.** A second model family reading the same sources would catch typing errors that the published means cannot.
- **No reliability index.** This page counts tests below Rn and bounds that share. Whether 0.75 Rn reaches the target reliability needs the statistics of material, fabrication and load, which this page does not take up.
- **P8's bound is the solver's, on P8's plate.** The kernel checked none of these 19 statements. P8's plate ends 2 in beyond the outer bolts with its far edges held, while a real web runs on below the bolts and along the span. So the bound is the plate's, not the beam's (inferred). A finer mesh would raise it, as the pilot's mesh study shows.

## What this means for the registry premise

No registry row changed. The pilot proposed recording on `aisc360.j4_3.shear` that a J4.3 PASS rests on rupture tests, not on plane-stress plasticity at Fy. This page supplies those tests for coped beams. The proposal, for the maintainers, is to add this page to that premise's sources, with one sentence. On 23 published coped-beam block shear tests at measured properties, test over Eq. J4-5's Rn runs from 0.888 to 1.340 with a mean of 1.12, and 3 fall below 1.0. Those tests are among the ones J4.3 was fitted to.
