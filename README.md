# Petra

Petra checks a physical design against the claims written in it and answers PASS, FAIL, MARGINAL or UNKNOWN. A design is a short `.petra` file that describes a steel connection, a truss, a wire circuit, a bolted joint or a load known only by its range and mean. Every PASS and every FAIL comes with a certificate that a small kernel re-checks in exact rational arithmetic. Every verdict lists the premises it rests on.

Petra is at version 0.1.0 and has one maintainer. It checks the claims and loads that a design states. It does not choose the loads, and it does not replace the engineer who signs the design.

## Install

Petra needs Python 3.11 or later. pip installs `numpy` and `scipy` with it:

```bash
pip install petra
```

To work on Petra, install a clone in editable mode, so your edits take effect without reinstalling:

```bash
git clone https://github.com/NooterraLabs/petra
cd petra
pip install -e .
```

To run Petra from the clone without installing it, write `python -m petra` in place of `petra`.

The build backend is part of the repository (`_build/petra_build.py`), so pip builds Petra from a clone without network access. To install on a machine with no network, build a wheel with `pip wheel --no-deps -w dist .` and copy it there. If that machine already has `numpy` and `scipy`, install the wheel with `pip install --no-index petra-0.1.0-py3-none-any.whl`.

## Check a steel connection

[examples/steel](examples/steel) holds one design of each steel connection kind. `petra new KIND` prints the example of a kind, ready to edit. This shear tab joins a W18x50 beam to the flange of a W14x90 column through a 3/8 in plate and four 3/4 in bolts:

```bash
petra new shear_tab
```

<!-- sample: petra new shear_tab | sed -n '13,31p' -->
```text
shear_tab st1 {
  basis lrfd
  beam W18x50 grade steel.A992
  support W14x90 flange grade steel.A992
  plate steel.A36 thickness 0.375 inch
  bolts bolt_group.120 diameter 0.75 inch threads included
  rows 4
  pitch 3 inch
  edge_vertical 1.5 inch
  plate_edge 1.5 inch
  bolt_line 3 inch
  beam_edge 1.75 inch
  top 3 inch
  weld electrode.E70 size 0.25 inch sides 2
}

load gravity {
  on st1 shear in [0 kip, 45 kip]
  signed "s.engineer@example.org" source "beam reaction, LRFD 1.2D + 1.6L, calc SC-3"
```

Check it:

```bash
petra check examples/steel/shear_tab.petra
```

These lines come from the report:

<!-- sample: petra check examples/steel/shear_tab.petra | sed -n '1,5p;13p;39p;45p;108p;112p;129p;130p' -->
```text
steel-shear-tab: PASS
entries    coverage PASS
scope      load cases gravity; environment undeclared; no parameters
checked    19 obligations, 19 certified, 0 refuted, 0 waived, 0 open
governing  strength   st1/steel.bolts/coverage.steel.bolts: beam side: most loaded bolt by the elastic method against the weakest bolt (J3.7, J3.11a): demand 17.57 kip, capacity 17.89 kip, utilisation 0.982; weakest top row (1 bolt): 17.89 kip, set by bolt shear
  st1/steel.bolts                              coverage steel.bolts         R4  certified  solver  sha256:fafccb69d51e..  utilisation 0.982
not checked  steel.prying on st1: no bolt is in tension, so none is pried (Manual Part 9)
footprint  92 premises
  sanctioned       reg:steel.A992.fu   steel.A992.fu 115653761996773/258064 Pa, ASTM A992 (W shapes): Fu >= 65 ksi   (AISC; ASTM A992 (W shapes) specified minimum tensile strength Fu = 65 ksi (AISC Steel Construction Manual, 16th ed. Table 2-4, as quoted in the Companion to the Manual v16.0 Vol. 1 Example D.1); version 1)
  validated_model  model:steel.bolts@04e8b4dfa2652ed8   bolt shear rupture (Eq J3-1) and bearing and tearout at every hole (Eq J3-6a-f), taken per bolt as the least of its shear strength and its bearing or tearout strength in each ply, summed over a concentric group; an eccentric group by the elastic method against the weakest bolt; through declared fillers the shear strength times 0.85, J5.2(a)'s least factor, since the grammar gives no filler thickness; valid when bolts of one group, size and installation; holes of the declared type; threads included or excluded as declared; the elastic method assumes a rigid connected part rotating about the group centroid. Unbounded: Eqs J3-1 and J3-6 state no range of their own; Table J3.2's reduction of Fnv for long end-loaded joints does not arise, since every catalogue bolt group is a shear connection's, a bracket's or a hanger's, which Commentary J3.7 exempts   (petra-maintainers; AISC 360-22 Sections J3.7 and J3.11a, Table J3.2; AISC Steel Construction Manual, 16th ed. (method encoded, not its text) Part 7 (elastic method))
  assumed          in:steel-shear-tab.gravity.st1.shear   gravity.st1.shear in [0, 200169.9726867225] N   (s.engineer@example.org; beam reaction, LRFD 1.2D + 1.6L, calc SC-3)
  judged           cov:cf885ae3de145584   every failure mode a v0 design must address is demanded by one of galvanic.contact, truss.frame, truss.axial_member, wire.conductor, bolt.tension, bolt.separation, bolt.bearing, steel.bolts, steel.bolt_tension, steel.bolt_combined, steel.slip, steel.shear_yield, steel.shear_rupture, steel.block_shear, steel.tension_yield, steel.tension_rupture, steel.flexural_yield, steel.flexural_rupture, steel.weld, steel.weld_base_metal, steel.bearing, steel.web_local_yielding, steel.web_crippling, steel.flange_local_bending, steel.web_sidesway_buckling, steel.web_compression_buckling, steel.panel_zone, steel.seat_flexure, steel.prying, steel.spacing_min, steel.edge_min, steel.spacing_max, steel.edge_max, steel.fillet_size, steel.hole_use, steel.joint_type, steel.clearance, steel.beam_fit, steel.flange_fit, steel.web_fit, steel.compression, steel.cope_buckling, steel.plate_buckling, steel.ductility, steel.tee_ductility, steel.bracket_edge, steel.extended_ductility, steel.load_path, steel.j10_stiffeners   (petra-maintainers; Petra coverage table v0: petra/coverage.py and each domain's coverage rules)
```

The first line is the verdict. An obligation is one statement that the design must satisfy. Petra makes one for each claim and one for each failure mode that the coverage table demands for the kind. All 19 obligations here have certificates that the kernel accepted. The `governing` line names the check closest to its limit, with the AISC clauses it encodes and its demand, capacity and utilisation. Each obligation line names the kernel rule that checked its certificate (R4 here) and the hash of its statement. A `not checked` line names a failure mode that cannot arise in this design, and says why. The footprint lists the 92 premises that the verdict rests on.

## Read a FAIL and an UNKNOWN

This truss carries a heavier load than [examples/truss_pass.petra](examples/truss_pass.petra):

```bash
petra check examples/truss_fail.petra
```

A FAIL prints a counterexample for each refuted obligation. The counterexample is a point where every input lies inside its signed or sanctioned range and the claim does not hold. These lines show the counts and the first two refutations:

<!-- sample: petra check examples/truss_fail.petra | sed -n '1,3p;15,27p' -->
```text
warren-footbridge-panel-rev-c: FAIL
entries    strength FAIL, coverage FAIL
checked    9 obligations, 6 certified, 3 refuted, 0 waived, 0 open
counterexample  frame/truss.plastic_collapse/claim.strength: a static field within every member's capacity carries the self-weight of frame, alone and with 1.5 times load case crowd
  governing  load factor: the claimed factor against the largest one a static field within every member's capacity carries: demand 1.5, capacity 0.7232, utilisation 2.07
  claim      strength: collapse_factor is 0.7232 here, against its bound 1.5
  at         const.earth.gravity = 9.84 m/s2   (reg:const.earth.gravity)
             const.steel.E       = 200 GPa   (reg:const.steel.E)
             const.steel.density = ~8004.77 kg/m3   (reg:const.steel.density)
             crowd.frame.D.fy    = -60 kN   (in:warren-footbridge-panel-rev-c.crowd.frame.D.fy)
             crowd.frame.E.fy    = -60 kN   (in:warren-footbridge-panel-rev-c.crowd.frame.E.fy)
  fixed      16 more values, as the design and the registry state them (--json lists each)
counterexample  frame.diag_ad/truss.member_buckling/coverage.truss.axial_member: the compression in frame.diag_ad is at most 1 times its flexural buckling resistance under load case crowd and the self-weight
  governing  compression against the flexural buckling resistance: demand 75.45 kN, capacity 54.69 kN, utilisation 1.38
  at         const.earth.gravity = 9.84 m/s2   (reg:const.earth.gravity)
             const.steel.E       = 200 GPa   (reg:const.steel.E)
```

This bolted joint is missing models for two of the failure modes that coverage demands:

```bash
petra check examples/bolt_unknown.petra
```

The tension claim passes, and so does the separation check that coverage adds. The verdict is still UNKNOWN, because v0 has no model for plate bearing or galvanic corrosion. Petra names each open requirement and what would close it:

<!-- sample: petra check examples/bolt_unknown.petra | head -n 13 -->
```text
mast-bracket-coastal: UNKNOWN
entries    tension PASS, coverage UNKNOWN
checked    4 obligations, 2 certified, 0 refuted, 0 waived, 2 open
governing  strength   bracket/bolt.tension/claim.tension: bolt tension against its limit: demand 29.04 kN, capacity 34.13 kN, utilisation 0.851
  bracket/bolt.tension                         claim tension                R4  certified  solver  sha256:4b704bfeffe3..  utilisation 0.851
  bracket/bolt.separation                      coverage bolt.separation     R4  certified  solver  sha256:ac3c5a1677e6..  utilisation 0.713
  bracket/bolt.plate_bearing                   coverage bolt.bearing        --  open
  bracket/corrosion.galvanic                   coverage galvanic.contact    --  open
open       2 requirements
  bracket/bolt.plate_bearing/coverage.bolt.bearing
    needs no model for bolt.plate_bearing on bracket: waive bolt.plate_bearing on bracket by "<owner>" reason "<why>"
  bracket/corrosion.galvanic/coverage.galvanic.contact
    needs no model for corrosion.galvanic on bracket: waive corrosion.galvanic on bracket by "<owner>" reason "<why>"
```

A claim may also name a margin, such as `<= 70 degC margin 20 degC`. Its verdict is MARGINAL when the claim is proved and the kernel certifies a point within the margin of the bound. [docs/reference.md](docs/reference.md) gives the rules.

## What a verdict rests on

Solvers search for a proof or a counterexample for each obligation and hand it in as a certificate. The kernel in [petra/kernel](petra/kernel) checks the certificate with exact rational arithmetic under one of six rules, R1 to R6. The kernel imports only the Python standard library and trusts no solver. `petra verify` checks a certificate file on its own, with no solver and no design:

```bash
petra verify examples/bolt_tension.cert.json
```

<!-- sample: petra verify examples/bolt_tension.cert.json -->
```text
examples/bolt_tension.cert.json: theorem sha256:4b704bfeffe30102181ec044dad0e38272fbed879c59c4cd3f1a05fb68851960
```

[The certificate JSON format](docs/design.md#certificate-json-format) does not depend on Python, so a second kernel can check the same files.

A verdict is true relative to its footprint. Each premise in the footprint carries one of these tags:

| Tag | Source | Example from the shear tab |
|---|---|---|
| `certified`, `proved` | The kernel | A certificate for the bolts' shear and bearing |
| `sanctioned` | A value from a named standard | ASTM A992's minimum tensile strength, 65 ksi |
| `measured`, `assumed` | An input that a named person signed, with its source | The beam reaction, 0 to 45 kip |
| `validated_model` | A physical model with numeric validity limits, which the kernel checks | Bolt shear rupture and bearing, AISC 360-22 Eqs. J3-1 and J3-6 |
| `judged` | The coverage table, and values the maintainers chose | Which failure modes a design must address |

If a premise is wrong, the verdict can be wrong, and the footprint tells you which premise to check. A model used outside its validity limits gives UNKNOWN, with the point where it leaves them.

## What Petra covers

| Domain | Kinds | What it checks |
|---|---|---|
| `steel` | `shear_tab`, `double_angle`, `single_angle`, `shear_tee`, `shear_end_plate`, `seated`, `stiffened_seat`, `flange_force`, `bolt_bracket`, `weld_bracket`, `hanger` | AISC 360-22 Chapters J and K, with the AISC Manual (16th edition) and the RCSC 2025 bolt specification. [docs/steel_connections.md](docs/steel_connections.md) is the specification. |
| `truss` | `truss` | Plastic collapse, member buckling (EN 1993-1-1), stress and stability of a pin-jointed truss |
| `circuit` | `circuit` | Wire temperature, short circuit, overload protection (IEC 60364-4-43) and voltage drop |
| `bolt` | `joint` | Bolt tension and joint separation |
| `uncertainty` | `demand` | A demand known by its range and mean, or by tests to failure, against a capacity |

Petra ships only the rows of the AISC Shapes Database that its examples and tests use. To use every W shape and angle, set `PETRA_SHAPES_XLSX` to your own copy of `SHAPE160.xlsx`.

## Write a design

`petra kinds` lists the component kinds by domain:

```bash
petra kinds
```

<!-- sample: petra kinds -->
```text
domain truss: truss
domain circuit: circuit
domain bolt: joint
domain uncertainty: demand
domain steel: shear_tab, double_angle, single_angle, shear_tee, shear_end_plate, seated,
  stiffened_seat, flange_force, bolt_bracket, weld_bracket, hanger

`petra kinds KIND` prints the lines a kind takes, each with its meaning; `petra kinds DOMAIN`
prints them for every kind of a domain, and `petra kinds --all` for every kind.
`petra new KIND` prints a complete design of KIND to start from.
```

`petra kinds double_angle` prints every line a double angle takes, with its meaning and unit. `petra registry list` prints every material, part and shape that Petra knows. Common names such as A325 and A992 resolve to their registry ids:

```bash
petra registry list bolt_group
```

<!-- sample: petra registry list bolt_group | head -n 2 -->
```text
bolt_group.120   bolt: ASTM F3125 Grades A325 and F1852 (Group 120); AISC's -N and -X are `threads included` and `threads excluded`; also A325, F1852
bolt_group.144   bolt: ASTM F3148 Grade 144 (Group 144); AISC's -N and -X are `threads included` and `threads excluded`; also F3148
```

When a design fails, the report names each refuted check with its demand, capacity and utilisation in the design's units. Change the input that the check reads, and check again.

## Use Petra from a program

`petra check FILE --json` prints the same report as one JSON object. The exit code carries the overall verdict:

| Exit code | Meaning |
|---|---|
| 0 | PASS |
| 1 | FAIL |
| 2 | UNKNOWN |
| 5 | MARGINAL |
| 3 | Input error |
| 4 | Internal error |

From Python, `petra.check_file` returns a report. `report.to_json()` returns the object that `--json` prints, and `report.render()` returns the text that `petra check` prints:

```python
import petra
report = petra.check_file("examples/bolt_unknown.petra")
print(report.to_json()["status"], [(v["claim"], v["status"]) for v in report.to_json()["verdicts"]])
```

<!-- sample: python -->
```text
UNKNOWN [('tension', 'PASS'), ('coverage', 'UNKNOWN')]
```

Other commands:

- `petra envelope FILE --input NAME --from LO --to HI` finds the widest interval of one input over which the design still passes.
- `petra certify-family FILE --library DIR` proves a design's claims over a box of inputs once. A later design inside the box gets its certificates from the library, with no solver run.
- `petra registry recall ID` lists the designs whose verdicts rest on a registry entry.
- `petra gym --episodes 20 --seed 0` runs a baseline agent on generated circuit and bolt tasks, rewarded only by kernel verdicts.

[petra/docs/api.md](petra/docs/api.md) documents each command's output and the Python API.

## How Petra is tested

The samples in this README are real command output, and `tests/test_docs.py` fails when one goes stale. The measures below ran on commit `9ae6009` on 2026-11-07:

| Measure | Result | Report |
|---|---|---|
| The test suite | 1,230 tests pass | `python -m unittest discover -s tests -t .` |
| Absurd-design gap: generated designs that Petra passes and the separate judge in [judges](judges) rejects | 0 of 54,000, over seeds 1, 2 and 3 | [docs/absurd_gap.md](docs/absurd_gap.md) |
| Canary recall: copies of Petra with checks taken out, for each of which the search must find a design the copy wrongly passes | 52 of 53 found | [docs/canary_recall.md](docs/canary_recall.md) |
| Steel gate: 10,000 generated connections, checked against a second implementation, planted faults and an adversarial search | 0 false PASS, and 218 of 218 planted faults caught | [docs/steel_gate.md](docs/steel_gate.md) |

## Limits of v0

- The kernel is Python with exact rationals, not Lean. The certificate format is ready for a Lean kernel, but that kernel does not exist yet.
- The coverage table is a judgement, and every footprint says so.
- Member buckling uses the EN 1993-1-1 curve c reduction with gamma_M1 = 1 and no EN 1090 erection tolerance. The plastic collapse model lets a buckled member keep its buckling resistance, which is unconservative for an indeterminate truss. The 0.002 small-strain limit is the maintainers' choice, not a code value.
- Petra checks each load case named in a claim on its own. It does not sum load cases.
- The steel deck does not yet model the rotational flexibility of angles and end plates, and does not check the welds of a stiffened seat's top angle and plate. [docs/plan.md](docs/plan.md) lists the rest under P1.
- Continuum finite elements, reduced bases and learned surrogates are out of scope.

## Documentation

`petra docs` prints the documents that install with Petra:

```bash
petra docs
```

<!-- sample: petra docs -->
```text
readme     installing Petra, a quickstart and worked examples
reference  the .petra language: syntax, units, every kind's lines and every registry id
api        the Python API, and the JSON that `petra check --json` prints
`petra docs NAME` prints one.
```

The rest are in [docs](docs):

- [docs/frame.md](docs/frame.md) says what a verdict means and what v0 covers.
- [docs/design.md](docs/design.md) says how the parts fit together, and why.
- [docs/steel_connections.md](docs/steel_connections.md) specifies the steel deck.
- [docs/plan.md](docs/plan.md) is the plan, with each phase's measured results.

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) says how to run the tests and regenerate the generated files. Every commit needs a sign-off under the Developer Certificate of Origin. A bug report is most useful with the `.petra` file, the command and Petra's output.

## Licence

Petra's code is Apache-2.0 ([LICENSE](LICENSE)), and its documentation is CC BY 4.0 ([docs/LICENSE.md](docs/LICENSE.md)). [CONTRIBUTING.md](CONTRIBUTING.md) pledges to keep those licences. [TRADEMARK.md](TRADEMARK.md) says how the Petra name may be used, and what "Petra-checked" means.
