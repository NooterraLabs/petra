# LoLa

LoLa checks a physical design against its claims and answers PASS, FAIL, MARGINAL or UNKNOWN. A design can be a pin-jointed truss, a wire circuit, a bolted joint, or a part under a load known only by its range and mean. Every PASS and every FAIL is a theorem that a small exact kernel checked. Every verdict lists the premises it rests on: standard values, signed inputs, models with their validity limits, and the coverage table. Solvers do the search, but the kernel trusts none of them. A solver hands in a certificate, and the kernel checks it with exact rational arithmetic.

[docs/frame.md](docs/frame.md) explains what a verdict means and what v0 covers. [docs/design.md](docs/design.md) explains how the parts fit and why.

## Check your first design

You need Python 3.11. The kernel uses only the standard library. The solvers use `numpy` and `scipy` (HiGHS for linear programs).

1. Check a truss whose claims hold:

	```bash
	python -m lola check examples/truss_pass.lola
	```

	The first lines name the verdict and each obligation the kernel certified:

	```text
	warren-footbridge-panel: PASS
	entries    strength PASS, stability PASS, stress PASS, coverage PASS
	scope      load cases crowd; environment indoor_dry; no parameters
	checked    11 obligations, 11 certified, 0 refuted, 0 waived, 0 open
	  frame/truss.plastic_collapse                 claim strength               R1  certified  solver  sha256:16afbc9f5e6f..
	```

	The footprint at the end lists all 24 premises. For example, `reg:steel.S355.fy` cites EN 10025-2, and `in:warren-footbridge-panel.crowd.frame.D.fy` names the person who signed that load range.

2. Check the same truss under a heavier load:

	```bash
	python -m lola check examples/truss_fail.lola
	```

	The verdict is FAIL, with three refutations. The panel cannot carry the load (R1, a Farkas ray), and two diagonals buckle (R4). Each refutation prints the counterexample point, such as `crowd.frame.D.fy = -60000 N` and `const.steel.E = 200000000000 Pa`. Every value lies inside its signed or sanctioned range.

3. Check a bolted joint whose coverage is incomplete:

	```bash
	python -m lola check examples/bolt_unknown.lola
	```

	The tension claim passes. The verdict is still UNKNOWN, because coverage asks for plate bearing and galvanic corrosion, and v0 has no model for either. LoLa names each open requirement and what would close it:

	```text
	open       2 requirements
	  bracket/bolt.plate_bearing/coverage.bolt.bearing
	    needs no model for bolt.plate_bearing on bracket: waive bolt.plate_bearing on bracket by "<owner>" reason "<why>"
	```

4. To read verdicts from another program, add `--json`. The exit code carries the status: 0 for PASS, 1 for FAIL, 2 for UNKNOWN, 5 for MARGINAL, 3 for an input error, and 4 for an internal error.

5. Check a certificate file on its own, with no solver and no design:

	```bash
	python -m lola verify examples/bolt_tension.cert.json
	```

	The kernel reads the statement and the evidence from the file and prints `theorem` and the statement hash. [The certificate JSON format](docs/design.md#certificate-json-format) is language-neutral, so a second kernel can check the same files.

## Ask how close, and how far

A claim can name a margin after its bound:

```text
claim hot:  lighting.w1.temperature <= 70 degC margin 20 degC under lamp_draw
```

The verdict is FAIL if the wire can pass 70 degC. It is MARGINAL if the kernel certifies a point where the wire comes within 20 degC of the bound, and the claim's proof, when there is one, travels with it. It is PASS if the claim is proved and no point comes that close. `examples/circuit_pass.lola` with this claim is MARGINAL: the wire reaches about 55 degC at the hot corner.

To find how far an input can go, name the range to explore:

```bash
python -m lola envelope examples/circuit_pass.lola --input ambient --from "-20 degC" --to "100 degC"
```

LoLa checks the design with the ambient's range replaced by probe intervals and bisects. It reports `ambient in [-20, 53.125] degC` as proved, with a certified failure of the `hot` claim at 54.3 degC. The probed range is an assumption of the command, not of whoever signed the design's ambient, and the footprint says so. `--input` also takes a load entry (`lamp_draw.lighting.lamps.current`), a component field (`lighting.mains.fault_current`) or a family param.

## Know what a verdict rests on

Each premise in a footprint carries one tag:

- `proved` and `certified` come from the kernel.
- `sanctioned` is a value from a named standard, such as a minimum yield strength.
- `measured` and `assumed` are inputs that a named person signed, with a source.
- `validated_model` is a physical model with its stated validity limits.
- `judged` is the coverage table, which decides which failure modes a design must address.

A verdict is true relative to its footprint. If a premise is wrong, the verdict can be wrong, and the footprint tells you which premise to check.

## Certify a family once

`python -m lola certify-family FILE --library DIR` proves a design's claims over a whole box of inputs and stores the certificates. A later design whose claims fall inside that box gets them from the library. With `python -m lola check FILE --library DIR --no-solve`, the kernel proves those claims and no solver runs. Coverage obligations that the family did not certify stay open. `python scripts/bench_family.py` times that reuse against recomputing, and explains the ratio from its own counters.

`python -m lola gym --episodes 20 --seed 0` runs a baseline agent on generated circuit and bolt tasks. The reward comes only from the kernel verdict.

## Check the build

Run the tests:

```bash
python -m unittest discover -s tests -t .
```

Check the definition of done in [docs/frame.md](docs/frame.md), item by item:

```bash
python scripts/predicate.py
```

## Limits of v0

- The kernel is Python with exact rationals, not Lean. The certificate format is ready for a Lean kernel, but the Lean toolchain is not installed.
- The coverage table is a judgement, and every footprint says so.
- The Euler buckling model applies no imperfection reduction. Its validity text says so.
- Each load case named in a claim is checked on its own. Cases are not summed.
- Continuum finite elements, reduced bases and learned surrogates are out of scope.
