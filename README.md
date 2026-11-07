# Petra

Petra checks a physical design against its claims and answers PASS, FAIL, MARGINAL or UNKNOWN. A design can be a steel connection, a pin-jointed truss, a wire circuit, a bolted joint, or a part under a load known only by its range and mean. Every PASS and every FAIL is a theorem that a small exact kernel checked. Every verdict lists the premises it rests on: standard values, signed inputs, models with their validity limits, and the coverage table. Solvers do the search, but the kernel trusts none of them. A solver hands in a certificate, and the kernel checks it with exact rational arithmetic.

The steel connections deck checks connections to AISC 360-22 Chapters J and K. It covers single-plate shear tabs, double and single angles, shear end plates, shear tees, unstiffened and stiffened seats, tee hangers, bolted and welded brackets, and concentrated flange forces on a column. [examples/steel](examples/steel) holds one design of each kind, and [docs/steel_connections.md](docs/steel_connections.md) is the deck's specification. Petra ships only the rows of the AISC Shapes Database that the examples and tests use. To use every W shape and angle, set `PETRA_SHAPES_XLSX` to your own copy of `SHAPE160.xlsx`.

[docs/reference.md](docs/reference.md) is the language reference, and [petra/docs/api.md](petra/docs/api.md) documents the Python API. `petra docs reference` and `petra docs api` print them from any install. [docs/frame.md](docs/frame.md) explains what a verdict means and what v0 covers. [docs/design.md](docs/design.md) explains how the parts fit and why.

## Install

You need Python 3.11 or later. Petra depends on `numpy` and `scipy` (HiGHS for linear programs). The kernel uses only the standard library.

From a clone of this repository, install Petra and its `petra` command:

```bash
pip install .
```

To install a working copy whose edits take effect without reinstalling, add `-e`:

```bash
pip install -e .
```

The build backend is part of the repository (`_build/petra_build.py`) and needs no packages, so pip builds Petra without network access. pip needs the network only to fetch `numpy` and `scipy` when they are missing. To build a wheel to install on another machine, run `pip wheel --no-deps -w dist .`.

To install a wheel file, such as one built that way, pass its path to pip:

```bash
pip install petra-0.1.0-py3-none-any.whl
```

Petra is not on PyPI yet. Publication is pending.

To run Petra from the repository root without installing it, write `python -m petra` in place of `petra`.

The documentation is installed with Petra. `petra docs` lists it, and `petra docs NAME` prints one document:

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

## Quickstart

1. Check a steel shear tab. It joins a W18x50 beam to the flange of a W14x90 column through a 3/8 in plate and four 3/4 in bolts.

	```bash
	petra check examples/steel/shear_tab.petra
	```

	The first lines give the verdict and count the obligations:

	<!-- sample: petra check examples/steel/shear_tab.petra | head -n 4 -->
	```text
	steel-shear-tab: PASS
	entries    coverage PASS
	scope      load cases gravity; environment undeclared; no parameters
	checked    17 obligations, 17 certified, 0 refuted, 0 waived, 0 open
	```

	Then comes one line per limit state the kernel certified, such as `st1/steel.block_shear`. The footprint at the end lists every premise the verdict rests on.

2. To read the verdict from another program, add `--json`. Petra prints the same report as one JSON object.

	```bash
	petra check examples/steel/shear_tab.petra --json
	```

	The exit code carries the overall status: 0 for PASS, 1 for FAIL, 2 for UNKNOWN, 5 for MARGINAL, 3 for an input error, and 4 for an internal error.

3. To check a design from Python, call `petra.check_file`. `report.to_json()` returns the object that `--json` prints, and `report.render()` returns the text that `petra check` prints.

	```python
	import petra
	report = petra.check_file("examples/bolt_unknown.petra")
	print(report.to_json()["status"], [(v["claim"], v["status"]) for v in report.to_json()["verdicts"]])
	```

	<!-- sample: python -->
	```text
	UNKNOWN [('tension', 'PASS'), ('coverage', 'UNKNOWN')]
	```

4. To write your own design, start from a template. `petra kinds` lists the component kinds by domain:

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

	`petra kinds double_angle` prints every line a double angle takes, each with its meaning and unit, and `petra new double_angle` prints a complete double-angle design to edit. `petra registry list` prints every material, part and shape Petra knows, and common names such as A325 and A992 resolve to their registry ids.

	```bash
	petra registry list bolt_group
	```

	<!-- sample: petra registry list bolt_group | head -n 2 -->
	```text
	bolt_group.120   bolt: ASTM F3125 Grades A325 and F1852 (Group 120); AISC's -N and -X are `threads included` and `threads excluded`; also A325, F1852
	bolt_group.144   bolt: ASTM F3148 Grade 144 (Group 144); AISC's -N and -X are `threads included` and `threads excluded`; also F3148
	```

	A FAIL names each refuted check with its demand, capacity and utilisation in the design's units, and the point where it fails. Change the input that check reads and check again.

## Walk through the examples

1. Check a truss whose claims hold:

	```bash
	petra check examples/truss_pass.petra
	```

	The first lines name the verdict, the governing strength check with its utilisation, and the first obligation the kernel certified:

	<!-- sample: petra check examples/truss_pass.petra | head -n 6 -->
	```text
	warren-footbridge-panel: PASS
	entries    strength PASS, stability PASS, stress PASS, coverage PASS
	scope      load cases crowd; environment indoor_dry; no parameters
	checked    10 obligations, 10 certified, 0 refuted, 0 waived, 0 open
	governing  strength   frame.diag_ad/truss.member_buckling/coverage.truss.axial_member: compression against the flexural buckling resistance: demand 30 kN, capacity 54.69 kN, utilisation 0.549
	  frame/truss.plastic_collapse                 claim strength               R1  certified  solver  sha256:aa44bf3a95d0..  validity 1 proved
	```

	The footprint at the end lists every premise. For example, `reg:steel.S355.fy` cites EN 10025-2, and `in:warren-footbridge-panel.crowd.frame.D.fy` names the person who signed that load range.

2. Check the same truss under a heavier load:

	```bash
	petra check examples/truss_fail.petra
	```

	The verdict is FAIL, with three refutations. The panel cannot carry the load (R1, a Farkas ray), and two diagonals buckle (R4). Each refutation prints the counterexample point. Every value lies inside its signed or sanctioned range. Each refutation names its governing check with demand, capacity and utilisation. These lines show the counts and the first two refutations:

	<!-- sample: petra check examples/truss_fail.petra | sed -n '1,3p;14,26p' -->
	```text
	warren-footbridge-panel-rev-c: FAIL
	entries    strength FAIL, coverage FAIL
	checked    9 obligations, 6 certified, 3 refuted, 0 waived, 0 open
	counterexample  frame/truss.plastic_collapse/claim.strength: a static field within every member's capacity carries 1.5 times load case crowd on frame
	  governing  load factor: the claimed factor against the largest one a static field within every member's capacity carries: demand 1.5, capacity 0.7292, utilisation 2.06
	  claim      strength: collapse_factor is 0.7292 here, against its bound 1.5
	  at         const.steel.E    = 200 GPa   (reg:const.steel.E)
	             crowd.frame.D.fy = -60 kN   (in:warren-footbridge-panel-rev-c.crowd.frame.D.fy)
	             crowd.frame.E.fy = -60 kN   (in:warren-footbridge-panel-rev-c.crowd.frame.E.fy)
	  fixed      16 more values, as the design and the registry state them (--json lists each)
	counterexample  frame.diag_ad/truss.member_buckling/coverage.truss.axial_member: the compression in frame.diag_ad is at most 1 times its flexural buckling resistance under load case crowd
	  governing  compression against the flexural buckling resistance: demand 75 kN, capacity 54.69 kN, utilisation 1.37
	  at         const.steel.E    = 200 GPa   (reg:const.steel.E)
	             crowd.frame.D.fy = -60 kN   (in:warren-footbridge-panel-rev-c.crowd.frame.D.fy)
	             crowd.frame.E.fy = -60 kN   (in:warren-footbridge-panel-rev-c.crowd.frame.E.fy)
	  fixed      16 more values, as the design and the registry state them (--json lists each)
	```

3. Check a bolted joint whose coverage is incomplete:

	```bash
	petra check examples/bolt_unknown.petra
	```

	The tension claim passes. The verdict is still UNKNOWN, because coverage asks for plate bearing and galvanic corrosion, and v0 has no model for either. Petra names each open requirement and what would close it:

	<!-- sample: petra check examples/bolt_unknown.petra | head -n 12 -->
	```text
	mast-bracket-coastal: UNKNOWN
	entries    tension PASS, coverage UNKNOWN
	checked    3 obligations, 1 certified, 0 refuted, 0 waived, 2 open
	governing  strength   bracket/bolt.tension/claim.tension: bolt tension against its limit: demand 29.04 kN, capacity 34.13 kN, utilisation 0.851
	  bracket/bolt.tension                         claim tension                R4  certified  solver  sha256:9caaf8237101..  utilisation 0.851
	  bracket/bolt.plate_bearing                   coverage bolt.bearing        --  open
	  bracket/corrosion.galvanic                   coverage galvanic.contact    --  open
	open       2 requirements
	  bracket/bolt.plate_bearing/coverage.bolt.bearing
	    needs no model for bolt.plate_bearing on bracket: waive bolt.plate_bearing on bracket by "<owner>" reason "<why>"
	  bracket/corrosion.galvanic/coverage.galvanic.contact
	    needs no model for corrosion.galvanic on bracket: waive corrosion.galvanic on bracket by "<owner>" reason "<why>"
	```

4. Check a certificate file on its own, with no solver and no design:

	```bash
	petra verify examples/bolt_tension.cert.json
	```

	The kernel reads the statement and the evidence from the file and prints `theorem` and the statement hash:

	<!-- sample: petra verify examples/bolt_tension.cert.json -->
	```text
	examples/bolt_tension.cert.json: theorem sha256:9caaf82371013b4170cfbb25cde94eaa54b40ee325600116748e4ca91b55f372
	```

	[The certificate JSON format](docs/design.md#certificate-json-format) is language-neutral, so a second kernel can check the same files.

## Ask how close, and how far

A claim can name a margin after its bound:

```text
claim hot:  lighting.w1.temperature <= 70 degC margin 20 degC under lamp_draw
```

The verdict is FAIL if the wire can pass 70 degC. It is MARGINAL if the claim is proved and the kernel also certifies a point where the wire comes within 20 degC of the bound. It is PASS if the claim is proved and no point comes that close, and the report says whether the margin itself was proved (the claim holds with at least 20 degC to spare) or is undecided. A point within the margin while the claim is neither proved nor refuted gives UNKNOWN, with the point shown. `examples/circuit_pass.petra` with this claim is MARGINAL, because the wire reaches about 55 degC at the hot corner.

To find how far an input can go, name the range to explore:

```bash
petra envelope examples/circuit_pass.petra --input ambient --from "-20 degC" --to "100 degC"
```

Petra checks the design with the ambient's range replaced by probe intervals and bisects. It reports the widest interval it proved and the first point where a claim fails:

<!-- sample: petra envelope examples/circuit_pass.petra --input ambient --from "-20 degC" --to "100 degC" | head -n 4 -->
```text
envelope   ambient in [-20, 53.125] degC: every obligation that depends on it is proved (one check over the whole interval passes)
input      in:workshop-lighting-radial.ambient, stated [10, 40] degC; probed [-20, 100] degC from 25 degC, resolution 1.875 degC
below      proved to -20 degC, the end of the probe range
above      proved to 53.125 degC; 54.296875 degC is not: FAIL (lighting.w1/wire.steady_temperature/claim.hot is refuted at this point with ambient = 54.296875 degC); 1.171875 degC undecided
```

The probed range is an assumption of the command, not of whoever signed the design's ambient, and the footprint says so. `--input` also takes a load entry (`lamp_draw.lighting.lamps.current`), a component field (`lighting.mains.fault_current`) or a family param. The search runs at most 64 checks (`--max-probes`), and the command exits 0 only when the anchor and the obligations that do not depend on the input both pass.

## Know what a verdict rests on

Each premise in a footprint carries one tag:

- `proved` and `certified` come from the kernel.
- `sanctioned` is a value from a named standard, such as a minimum yield strength.
- `measured` and `assumed` are inputs that a named person signed, with a source.
- `validated_model` is a physical model. Its numeric validity limits, such as a member staying below yield, are checked inequalities. Every PASS and FAIL carries a kernel proof of each one, and a model used outside its range gives UNKNOWN with the point. Limits not yet checked are printed as "not checked".
- `judged` is the coverage table, which decides which failure modes a design must address.

A verdict is true relative to its footprint. If a premise is wrong, the verdict can be wrong, and the footprint tells you which premise to check.

## Certify a family once

`petra certify-family FILE --library DIR` proves a design's claims over a whole box of inputs and stores the certificates. A later design whose claims fall inside that box gets them from the library. With `petra check FILE --library DIR --no-solve`, the kernel proves those claims and no solver runs. Coverage obligations that the family did not certify stay open. `python scripts/bench_family.py` times that reuse against recomputing, and explains the ratio from its own counters.

`petra gym --episodes 20 --seed 0` runs a baseline agent on generated circuit and bolt tasks. The reward comes only from the kernel verdict.

## Check the build

Run the tests:

```bash
python -m unittest discover -s tests -t .
```

The samples in this README are command output. A test runs each command and fails when a sample is stale. To rewrite every sample from its command, run:

```bash
python tests/test_docs.py --write
```

Check the definition of done in [docs/frame.md](docs/frame.md), item by item:

```bash
python scripts/predicate.py
```

## Limits of v0

- The kernel is Python with exact rationals, not Lean. The certificate format is ready for a Lean kernel, but the Lean toolchain is not installed.
- The coverage table is a judgement, and every footprint says so.
- Member buckling uses the EN 1993-1-1 curve c reduction with gamma_M1 = 1 and no EN 1090 erection tolerance. The plastic collapse model lets a buckled member keep its buckling resistance, which is unconservative for an indeterminate truss. The 0.002 small-strain limit is the maintainers' choice, not a code value.
- Each load case named in a claim is checked on its own. Cases are not summed.
- Continuum finite elements, reduced bases and learned surrogates are out of scope.
