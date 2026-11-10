# Petra v0: the math-only kernel

This is the authoritative design for Petra v0. It began as candidate 1 in an arena, a contest between two competing designs that a rubric and a cross-judge scored. It carries the grafts and fixes listed under [Synthesis decision](#synthesis-decision).

## Problem

Petra turns a `.petra` design into a verdict that is a theorem relative to named premises. Untrusted solvers produce certificates, and a small kernel checks them in exact rational arithmetic. [The frame](frame.md) asks for six certificate rules, four physics domains, a makeable set, coverage, port contracts, family certificates, and a small kernel that a Lean kernel can later replace.

This document uses the frame's terms. A premise is a fact a verdict assumes. Each premise has a tag, such as `sanctioned` for a value that a named standard fixes. A verdict's footprint is the set of premises it used, apart from `proved` ones. The makeable set is the registry of real materials, parts, processes and environments that a design may name. An obligation is one check the design owes. Coverage is the table that decides which obligations a design owes beyond its claims. A waiver is a `waive` line in the design that accepts one of those obligations and names who answers for it. R1 to R6 are the kernel's six certificate rules.

One sentence in the frame makes the design hard. It says each rule checks a certificate "against equations the kernel builds itself from the design". If the kernel builds the equations, the kernel knows physics, and the Lean port has to port trusses, wires and bolts too. Every v1 item (continuum finite elements, reduced basis, neural surrogates) would add physics to the kernel.

This design keeps the frame's intent but moves the physics out of the kernel. The kernel knows only mathematics: rationals, intervals, expressions, exact matrices, and six theorems about them. Small trusted elaborators, one per domain, build the equations from the design. A solver still never supplies a matrix or a model equation. It receives a statement an elaborator built and returns numbers. Every footprint names each elaborator it rests on as a `validated_model` premise, keyed by the hash of the elaborator's source.

The design meets the frame's constraints. `petra/kernel` imports only the standard library, and a test enforces it. Certificates are language-neutral JSON. A PASS cannot be built without theorems the kernel issued, a scope and a footprint. An UNKNOWN always names, as typed data, what would close it. The checker never invents an input bound.

## What a caller sees

### The command line

```text
python -m petra check examples/truss_pass.petra
```

`check` parses the file and elaborates every claim and every coverage obligation into kernel statements. It gathers evidence from three sources, in this order: stored certificates, the library, and the solvers. The kernel then decides each statement. The output below was captured from the build. Hashes are cut to four hex digits, certified premises are collapsed to one line, and long lines are cut.

```text
warren-footbridge-panel: PASS
entries    strength PASS, stability PASS, stress PASS, coverage PASS
scope      load cases crowd; environment indoor_dry; no parameters
checked    10 obligations, 10 certified, 0 refuted, 0 waived, 0 open
  frame/truss.plastic_collapse                 claim strength               R1  certified  solver  sha256:aa44..  validity 1 proved
  frame/truss.global_stability                 claim stability              R2  certified  solver  sha256:2a8a..  validity 2 proved
  frame.diag_ad/truss.elastic_stress           claim stress                 R3  certified  solver  sha256:238a..  validity 2 proved
  frame.bottom_ab/truss.member_buckling        coverage truss.axial_member  R4  certified  solver  sha256:8fbc..  validity 3 proved
  frame.bottom_bc/truss.member_buckling        coverage truss.axial_member  R4  certified  solver  sha256:cfe6..  validity 3 proved
  frame.top_de/truss.member_buckling           coverage truss.axial_member  R4  certified  solver  sha256:775d..  validity 3 proved
  frame.diag_ad/truss.member_buckling          coverage truss.axial_member  R4  certified  solver  sha256:a1e9..  validity 3 proved
  frame.diag_db/truss.member_buckling          coverage truss.axial_member  R4  certified  solver  sha256:05e1..  validity 3 proved
  frame.diag_be/truss.member_buckling          coverage truss.axial_member  R4  certified  solver  sha256:00ec..  validity 3 proved
  frame.diag_ec/truss.member_buckling          coverage truss.axial_member  R4  certified  solver  sha256:f0fd..  validity 3 proved
footprint  29 premises
  certified        cert:sha256:00ec.. and 12 more   kernel-checked in this run
  sanctioned       reg:const.en10219_2.60_3x3_2.D   CHS 60.3 x 3.2 has outside diameter 60.3 mm   (CEN; EN 10219-2:20...
  sanctioned       reg:const.en10219_2.60_3x3_2.t   CHS 60.3 x 3.2 has wall thickness 3.2 mm   (CEN; EN 10219-2:2006,...
  sanctioned       reg:const.en10219_2.76_1x3_2.D   CHS 76.1 x 3.2 has outside diameter 76.1 mm   (CEN; EN 10219-2:20...
  sanctioned       reg:const.en10219_2.76_1x3_2.t   CHS 76.1 x 3.2 has wall thickness 3.2 mm   (CEN; EN 10219-2:2006,...
  sanctioned       reg:const.en1993_1_1.class3_tube_limit   a tube is class 3 or better in compression when d / t <= ...
  sanctioned       reg:const.en1993_1_1.curve_c.alpha   buckling curve c has imperfection factor 0.49   (CEN; EN 1993...
  sanctioned       reg:const.en1993_1_1.epsilon_reference_fy   the slenderness limits of EN 1993-1-1 Table 5.2 scale ...
  sanctioned       reg:const.steel.E   the elastic modulus of structural steel lies in [200, 210] GPa   (CEN; EN 1993...
  sanctioned       reg:steel.S355.fy   steel.S355.fy 355000000 Pa, minimum upper yield strength ReH, nominal thicknes...
  validated_model  model:truss.elastic@b49e..   linear elastic pin-jointed 2D truss: member forces minimise the compl...
  validated_model  model:truss.flexural_buckling@b49e..   flexural buckling of a pin-ended uniform member, EN 1993-1-...
  validated_model  model:truss.plastic@b49e..   rigid-perfectly-plastic pin-jointed 2D truss, static (lower-bound) th...
  validated_model  model:truss.stability@b49e..   linear prebuckling of a pin-jointed 2D truss, Green-strain geometri...
  assumed          in:warren-footbridge-panel.crowd.frame.D.fy   crowd.frame.D.fy in [-24000, -16000] N   (client.str...
  assumed          in:warren-footbridge-panel.crowd.frame.E.fy   crowd.frame.E.fy in [-24000, -16000] N   (client.str...
  judged           cov:d668..   every failure mode a v0 design must address is demanded by one of galvanic.contact, t...
```

The report has one entry per claim and one entry named `coverage` for the requirements no claim made (coverage rules and port contracts). The design's verdict is the conjunction of the entries. `--json` prints the same report as data:

```json
{"file": "examples/bolt_unknown.petra", "design": "mast-bracket-coastal", "status": "UNKNOWN", "verdicts": [
  {"claim": "tension", "status": "PASS", "rules": ["R4"], "needs": [], "margins": [],
   "footprint": [{"tag": "assumed", "label": "in:mast-bracket-coastal.wind.bracket.force", "owner": "client.structures@example.org", "source": "wind study WS-4, 50-year return"}, "..."],
   "obligations": [{"requirement": "bracket/bolt.tension/claim.tension", "outcome": "certified", "rule": "R4", "statement_hash": "sha256:4b70...",
                    "governing": "bolt tension against its limit", "demand": 29.04, "capacity": 34.13, "unit": "kN", "utilisation": 0.851, "at": "box", "...": "..."}]},
  {"claim": "coverage", "status": "UNKNOWN", "rules": [], "margins": [],
   "needs": ["no model for bolt.plate_bearing on bracket: waive bolt.plate_bearing on bracket by ...", "no model for corrosion.galvanic on bracket: waive corrosion.galvanic on bracket by ..."],
   "footprint": ["..."], "obligations": ["..."]}]}
```

`needs` is non-empty exactly when the entry is UNKNOWN. Each line is `verdict.describe_need` applied to one typed `Need`. `obligations` has one record per outcome of the entry, with its numbers in the design's units and, when refuted, its counterexample. [petra/docs/api.md](../petra/docs/api.md) gives every field.

The other commands are these:

| Command | What it does |
|---|---|
| `petra explain FILE` | prints the statements with every hypothesis label |
| `petra envelope FILE --input NAME --from LO --to HI` | finds the widest proved interval of one input (call site 5) |
| `petra verify CERT.json` | checks a certificate file on its own, the job a Lean kernel will take over |
| `petra certify-family FILE --library DIR` | certifies a family into the library at DIR (call site 4) |
| `petra registry build --out DECK` | exports the registry as a deck |
| `petra registry check [DECK]` | checks a deck. With no deck, it checks the shipped registry and exits 0 when every relation holds. |
| `petra registry recall ID [FILE ...]` | lists the designs whose verdicts rest on a registry entry ([registry.md](registry.md)) |

`check` takes its exit code from the overall status: 0 for PASS, 1 for FAIL, 2 for UNKNOWN, 5 for MARGINAL, and 3 for an input error. `envelope` exits with the worse of its anchor's status and the status of the obligations that do not depend on the input.

### Call site 1. A CI gate in a hardware repo

```python
import sys
import petra
from petra.premises import Tag

report = petra.check_file("designs/bracket.petra", certs="certs/", library=petra.Library("lib/"), solve=False)
print(report.render())
verdict = report.verdict
if not isinstance(verdict, petra.Pass):
    sys.exit(1)
judged = [p for p in verdict.footprint.premises if p.tag is Tag.JUDGED and not p.label.startswith("cov:")]
APPROVED_SIGNERS = {"m.engineer@example.org", "a.reviewer@example.org"}
if any(p.owner not in APPROVED_SIGNERS for p in judged):
    sys.exit("a waiver or judgement is signed by someone outside the approved list")
```

`solve=False` makes CI check only committed certificates and the library. The gate reads the footprint as data, so a team can write policy about premises ("no judged premise from an unapproved signer") instead of reading reports.

### Call site 3. An independent checker, the future Lean kernel's test harness

```python
import json
from petra import kernel

env = json.load(open("certs/f7e4f426.json"))
statement = kernel.decode_statement(env["statement"])
assert kernel.statement_hash(statement) == env["statement_hash"]
result = kernel.check(statement, kernel.decode_evidence(env["evidence"]))
if isinstance(result, kernel.Rejection):
    print("rejected:", result.reason)
else:
    print(type(result).__name__, sorted(result.labels))   # Theorem or Refutation, and what it rests on
```

The kernel needs nothing but the file. A Lean port reimplements this interface, and the mutation suite runs against it.

### Call site 4. Certify a family once, reuse it

```python
import petra
from petra.registry import build_registry

registry = build_registry()
library = petra.Library("library/")
family = petra.load_design("examples/families/cu_pvc_clipped.petra", registry)   # and cu_pvc_clipped.card beside it
petra.certify_family(family, registry, library)          # R4 partitions over the whole box, stored
report = petra.check_file("examples/circuit_pass.petra", library=library)
# the `hot` and `drop` obligations show source "library": an Instance of the family theorem, checked by the kernel
```

### Call site 5. Margins and safe envelopes

A claim may name a margin after its bound. Suppose the `hot` claim in `examples/circuit_pass.petra` is edited to this:

```text
claim hot:  lighting.w1.temperature <= 70 degC margin 20 degC under lamp_draw
```

The edited claim asks two things. Does the wire stay at or below 70 degC, and does it come within 20 degC of that anywhere? For each claim obligation, the pipeline builds a second statement with the bound moved inward by the margin. `petra explain` prints it as "margin obligation, the bound moved to 50 degC". Unless the claim is refuted, the pipeline offers that statement to the sources. It also tries every margin witness against the claim, so a point past the bound is a FAIL. MARGINAL needs both a proof of the claim and a certified point within the margin. Here the claim is proved, but the wire reaches about 56 degC at the hot corner, so `check` exits 5:

```text
workshop-lighting-radial: MARGINAL
entries    hot MARGINAL, drop PASS, coverage PASS
scope      load cases lamp_draw; environment indoor_dry; no parameters
checked    7 obligations, 6 certified, 0 refuted, 1 within margin, 0 waived, 0 open
  lighting.w1/wire.steady_temperature          claim hot                    R4  marginal   solver  proved, margin point at sha256:a27a..
  ...
within margin  lighting.w1/wire.steady_temperature/claim.hot: lighting.w1 runs at or below 70 degC under lamp_draw
  proved; at this point it is within 20 degC of its bound
  ambient = 40 degC   (in:workshop-lighting-radial.ambient)
  lamp_draw.lighting.lamps.current = 10 A   (in:workshop-lighting-radial.lamp_draw.lighting.lamps.current)
  ...
```

With `margin 2 degC`, the same design passes, and the report says what the search settled about the margin:

```text
margin     lighting.w1/wire.steady_temperature/claim.hot: proved: the claim holds with at least 2 degC to spare
```

Here the solver proved the claim at 68 degC as well. When the solver finds neither a point within the margin nor a proof at the tightened bound, the line reads `undecided: no point within 2 degC of the bound was found, and slack 2 degC is not proved`. The verdict is still PASS, because the claim is proved. With the bound at 50 degC, the design fails. A point within the margin, found while the claim itself is neither proved nor refuted, gives UNKNOWN, and the report prints the point under the open item. Such a point says nothing about the rest of the box, where the claim may still fail. `--json` lists each margin claim under `margins` with `proved` and `margin` (`proved`, `undecided`, or `within` with its point). The margin statement has the same hash as the plain `<= 50 degC` claim, so the same certificates serve both. A certificate that proves the margin statement proves the claim too.

`petra envelope` answers the inverse question. Over what range of one input does the design hold? The command never invents a bound. The caller names the range to explore:

```text
python -m petra envelope examples/circuit_pass.petra --input ambient --from "-20 degC" --to "100 degC"
```

```text
envelope   ambient in [-20, 51.953125] degC: every obligation that depends on it is proved (one check over the whole interval passes)
input      in:workshop-lighting-radial.ambient, stated [10, 40] degC; probed [-20, 100] degC from 25 degC, resolution 1.875 degC
below      proved to -20 degC, the end of the probe range
above      proved to 51.953125 degC; 53.125 degC is not: FAIL (lighting.w1/wire.steady_temperature/claim.hot is refuted at this point with ambient = 53.125 degC); 1.171875 degC undecided
elsewhere  the obligations that do not depend on ambient are PASS
probes     10 checks (limit 64)
```

Each probe replaces the ambient's range in the design and checks the result like any design, so the reported interval is a PASS assembled from kernel theorems. `petra envelope` assumes the probed range. The site manager did not sign it, because the manager signed only [10, 40] degC.

The same command takes a load entry, a component field or a family param. `--input lamp_draw.lighting.lamps.current` stops at 10.06 A, where the B10 breaker no longer protects the wire. `lighting.mains.fault_current` stops at 6.19 kA, the wire's short-circuit withstand. With a margin claim, the envelope shrinks to where the margin holds. `margin 10 degC` stops it at 42.58 degC, with MARGINAL at 43.75 degC.

The search is bounded. It runs at most 64 checks (`--max-probes N`). The two sides share them, after one check is reserved for the anchor and one for confirmation. The search never bisects finer than 1/2^20 of the probe range, and it raises a finer `--resolution` to that floor. A side that stops at the limit reports how much it left undecided. The exit code is the worse of the anchor's status and the status on the `elsewhere` line, so an envelope over a design that fails elsewhere does not exit 0. A negative bound may be written `--from -20degC`. `--json` prints the same as exact rationals in SI units.

### One example per domain

These examples ship in `examples/` with the sketch. The sketch is the first commit, in which every shared type is complete and only function bodies are missing. Hand calculations chose the numbers to give the stated verdict, and the numbers will be re-tuned when the solvers run.

#### Trusses

`truss_pass.petra` expects PASS. `truss_fail.petra` raises the load to 60 kN per node and expects FAIL by a collapse mechanism on the end diagonal.

The card, `truss_pass.card`:

```petra
petra 0

card "warren-footbridge-panel" {
  owner "a.reviewer@example.org"
  environment indoor_dry
}

load crowd {
  on frame.D fy in [-24 kN, -16 kN]
  on frame.E fy in [-24 kN, -16 kN]
  signed "client.structures@example.org" source "brief rev B, section 3.2"
}

claim strength:   frame.collapse_factor >= 1.5 under crowd
claim stability:  frame.stability_factor >= 3 under crowd
claim stress:     frame.member(diag_ad).stress <= 235 MPa under crowd
```

The design, `truss_pass.petra`:

```petra
petra 0

truss frame {
  material steel.S355
  section chs.60_3x3_2

  node A at (0 m, 0 m) support pinned
  node B at (3 m, 0 m)
  node C at (6 m, 0 m) support roller_x
  node D at (1.5 m, 2 m)
  node E at (4.5 m, 2 m)

  member bottom_ab: A -- B
  member bottom_bc: B -- C
  member top_de:    D -- E section chs.76_1x3_2
  member diag_ad:   A -- D
  member diag_db:   D -- B
  member diag_be:   B -- E
  member diag_ec:   E -- C
}
```

A hand calculation gives the margins. At factor 1.5, the end diagonal carries 45 kN of compression against an EN 1993-1-1 compression resistance of 54.0 kN. That is the flexural buckling resistance of 54.7 kN (CHS 60.3x3.2, L = 2.5 m, curve c, relative slenderness 1.66, reduction factor 0.27, at E = 200 GPa), lowered 1.3% by the member check of 6.3.3 for the bending of the diagonal's own weight. The members' own weight adds 0.44 kN, which the factor does not scale. Every load case carries the weight of each member, computed from its section area and steel's density, with gravity at the top of the registry's 9.76 to 9.84 m/s2. The bare Euler load would be 74.1 kN. With the rev C load of 60 kN, the end diagonal needs 112.5 kN, which fails.

#### Wire circuits

`circuit_pass.petra` expects PASS, with two obligations reused from the family.

The card, `circuit_pass.card`:

```petra
petra 0

card "workshop-lighting-radial" {
  owner "e.designer@example.org"
  environment indoor_dry
}

ambient in [10 degC, 40 degC] signed "site.manager@example.org" source "site survey 2026-09"

given fault_current in [0 kA, 6 kA] signed "dno.liaison@example.org" source "DNO letter 2026-08-14"

load lamp_draw {
  on lighting.lamps current in [0 A, 10 A]
  signed "e.designer@example.org" source "luminaire schedule rev 3"
}

claim hot:  lighting.w1.temperature <= 70 degC under lamp_draw
claim drop: lighting.w1.voltage_drop <= 3 % under lamp_draw
```

The design, `circuit_pass.petra`:

```petra
petra 0

circuit lighting {
  supply mains voltage 230 V fault_current given fault_current
  breaker cb1 part mcb.B10
  wire w1 cable cable.cu_pvc_2_5 length 18 m install install.clipped_direct
  terminal t1 part terminal.lever_4mm2_75C
  consumer lamps

  connect mains.out -> cb1.in
  connect cb1.out -> w1.a
  connect w1.b -> t1.wire
  connect t1.out -> lamps.in
}
```

Coverage adds three obligations:

- short circuit, which compares the breaker's let-through I2t against k^2 S^2, with k derived from copper's constants
- overload protection to IEC 60364-4-43, which needs I_B <= I_n and the wire at I_n to stay below 70 degC
- the default voltage-drop limit

The `w1.b -> t1.wire` connection adds three port contracts. The wire's steady-temperature guarantee must lie inside the terminal's 75 degC assumption, its current inside the terminal's rated current, and its conductor area inside the 0.2 to 4 mm2 that the terminal clamps. A terminal clamps a wire connected at either of its ports, so a wire at `t1.out` gets the same three contracts.

#### Bolts

`bolt_unknown.petra` expects UNKNOWN.

The card, `bolt_unknown.card`:

```petra
petra 0

card "mast-bracket-coastal" {
  owner "m.engineer@example.org"
  environment marine_c5
}

given torque in [40 Nm, 50 Nm] signed "fitter.lead@example.org" source "assembly spec AS-12 rev C"
given nut_factor in [0.16, 0.22] measured "test.lab@example.org" source "torque-tension report TT-2026-031"
given load_share in [0.10, 0.25] signed "m.engineer@example.org" source "joint diagram calc JD-7"

load wind {
  on bracket force in [0 kN, 12 kN]
  signed "client.structures@example.org" source "wind study WS-4, 50-year return"
}

claim tension: bracket.tension_utilisation <= 0.9 under wind
```

The design, `bolt_unknown.petra`:

```petra
petra 0

joint bracket {
  bolt bolt.M12_A4_70 count 1
  plate aluminium.6061_T6 thickness 10 mm
  plate aluminium.6061_T6 thickness 10 mm
  torque given torque
  nut_factor given nut_factor
  load_share given load_share
}
```

The tension claim is certified, with a worst case of 29.0 kN against 0.9 x 450 MPa x 84.3 mm2 = 34.1 kN. The bolt force is the larger of two shares. While the plates stay clamped, the bolt carries F_V + Phi F / n. Once the joint opens, the bolt carries the whole share, F / n = 12 kN. The claim therefore holds whether or not the plates stay clamped. Coverage demands `bolt.separation`, which is certified too. The least preload, 40 Nm / (0.22 x 12 mm) = 15.2 kN, exceeds the plates' share of the force, 0.9 x 12 kN = 10.8 kN, so the joint stays clamped. Coverage also demands `corrosion.galvanic` (A4 stainless against 6061 aluminium in a wet C5 environment) and `bolt.plate_bearing`. v0 has no model for either, and no waiver names them, so the verdict is UNKNOWN. The report lists both, with what each needs.

#### Uncertain loads

`hook_uncertain.petra` expects PASS. The demand domain compares a demand with a capacity and knows nothing about bolts, so this example depends on no other domain's model.

The card, `hook_uncertain.card`:

```petra
petra 0

card "hoist-hook" {
  owner "m.engineer@example.org"
  environment indoor_dry
}

given capacity in [36 kN, 40 kN] measured "qa.lab@example.org" source "proof-load report PL-0917, minimum of 12 samples"

load lift {
  on hook force in [0 kN, 40 kN] mean 10 kN
  signed "ops.lead@example.org" source "hoist duty log 2025, 14200 lifts"
}

tests proof {
  on hook trials 300 failures 0 at 36 kN
  signed "qa.lab@example.org" source "batch 2026-09 proof tests, independent lots"
}

claim overload: P(hook.utilisation > 1) <= 3/10 under lift
claim tested:   P(fail hook at 36 kN) <= 1/100 confidence 95 % from proof
```

The design, `hook_uncertain.petra`:

```petra
petra 0

demand hook {
  capacity given capacity
}
```

R5 checks `overload`. Over every distribution on [0, 40] kN with mean 10 kN, the load exceeds a capacity of at least 36 kN with probability at most 10/36 = 0.278 <= 0.3, with no distribution assumed. The dual function is h(x) = x/36. R6 checks `tested`. The claimed level equals the tested level, and 0.99^300 = 0.049 <= 0.05.

## Shape

### The data structures

The design has five central types and two registries. The registries say which rules and which domains exist. Everything else is a function between the types.

1. `kernel.Statement` (`petra/kernel/terms.py`) is `hyps` plus one `goal`. It reads "for every value of the range hypotheses inside their ranges, and every defined hypothesis equal to the quantity it names, the goal holds." There are six goal variants, one per rule, each defined in its rule module under `petra/kernel/rules/`: `LinearFeasible` (R1), `GramPositiveDefinite` (R2), `MinimizerBound` (R3), `AllNonpositive` (R4), `MomentBound` (R5), `BinomialTail` (R6). Their fields are `Expr` trees, sparse exact `Matrix` values, and rationals. No field names a physical thing.
2. `kernel.Hyp` is either `RangeHyp(sym, lo, hi, label)` or `DefinedHyp(sym, definition)`. The label is an opaque string to the kernel. Outside the kernel it names a premise (`reg:`, `in:`), a scope parameter (`par:`) or a drawn design value (`dsg:`).
3. `kernel.Evidence` (`petra/kernel/evidence.py`) holds only what a solver chose: feasible points, an LDL factor, hypercircle fields, a split tree, dual multipliers, or a counterexample point. The rule modules declare the body types. Evidence never holds a matrix or an expression from the model.
4. `kernel.Theorem` and `kernel.Refutation` are issued, not constructed. Each is a bare handle with no fields. Its data lives in a kernel-private table keyed by the handle's identity, and `kernel.is_issued(x)` is true only for a handle `check` returned. Calling the class raises an exception. `object.__new__` gives a handle with no record. Assignment, even through `object.__setattr__`, has nothing to change. Copy, deepcopy, pickle and `dataclasses.replace` raise an exception. `tests/test_seal.py` tries each of these. A theorem exposes the statement, its hash, the rule, and `labels`, the exact set of hypothesis labels it rests on.
5. `verdict.Pass | Fail | Unknown | Marginal` (`petra/verdict.py`) are the verdict types. A report prints the variant.
   - `Pass` takes a `Scope`, a non-empty `Footprint` and a non-empty tuple of issued theorems. Every label of every theorem resolves to a footprint premise, a scope parameter or the design itself.
   - `Fail` takes an issued `Refutation` of the obligation's own statement, and a theorem for each validity row of its model, over the box or at the refutation's point. A validity row is a numeric limit of the model (decision 12).
   - `Marginal` takes at least one `WithinMargin` item and the `Scope` its theorems hold over. A `WithinMargin` item is an issued `Refutation` of a claim's margin statement together with the claim's own theorem.
   - `Unknown` takes at least one `Open` item, and each `Open` names at least one typed `Need` (`petra/models/base.py`): `NeedsCertificate`, `CertificateRejected`, `CertificateTooWeak`, `NeedsInputBound`, `InputContradicted`, `NoRuleForQuantity`, `NoModel`, `RegistryInconsistent` or `OutsideValidity`. An `Open` for a claim with a margin may also carry `near`, a `WithinMargin` without a theorem. That item is the point within the margin found while the claim was neither proved nor refuted.

The rule registry is `petra/kernel/rules/__init__.py`. Each rule module ends with `RULE = RuleSpec(...)`, which names its goal, evidence and lemma types, their JSON tags, and its check functions. `_REGISTERED` lists the six specs. `RULES`, `GOAL_RULE`, `PROOF_RULE`, `REFUTATION_RULE`, `LEMMAS`, the rule part of `codec.TAGS`, and `MODULE_OF` are all derived from it. The solver for a rule is the module of the same name under `petra/solvers/`.

The domain registry is `petra/models/__init__.py`. Each domain module ends with `DOMAIN = DomainSpec(...)`, which names its component kinds and their lowerers, its failure modes and their builders, its claimable quantities, its probability methods, its coverage rules, its model premises, and its feature and port hooks. `_REGISTERED` names the four v0 domains (truss, circuit, bolt, uncertainty), and `DOMAINS`, `KINDS`, `MODES`, `UNMODELLED` and `COVERAGE` are derived from it. The tuple is already filled in, so no implementer edits the file.

### How data flows

```text
card, design --lang.parse_design-->      ir.Design             trusted front end: names, units, signatures; generic components
ir.Design   --pipeline.lower_components--> typed models       each kind's lowerer (models.KINDS): attributes, registry ids
models      --coverage.generate-->      Requirement[]         claims plus the coverage table, minus waivers
Requirement --pipeline.elaborate-->     Obligation | Gap      the owning domain's builder: Statement plus ModelSpec
Statement   --EvidenceSource.offer-->   Evidence[]            untrusted: certs dir, library, solvers
(Statement, Evidence) --kernel.check--> Theorem | Refutation | Rejection
outcomes + PremiseBook --verdict.entries--> ClaimVerdict[]   one per claim, plus "coverage"; footprint = labels used
```

A reader traces any verdict in three files: the elaborator that built the statement, `kernel/check.py`, and `verdict.py`.

### Design decisions

1. **The statement is a pure function of the design, and evidence holds only solver choices.** The pipeline elaborates the design itself, asks sources for evidence for that exact statement, and binds stored certificates by `statement_hash`. A tampered statement in a certificate file hashes differently and is never consulted. Data flow, not a check, enforces the frame's rule that "a solver never supplies the matrices" (per boundary-discipline).
2. **Every number that comes from a premise enters as a labelled `RangeHyp`.** The footprint is then a structural function of the theorem. The kernel returns `labels`, and `PremiseBook` maps each label to a tagged premise with owner and source. `check` rejects a statement with an unused hypothesis, so the footprint lists only premises the proof used. `StatementBuilder` (`models/base.py`) has no method that turns a bare number into a hypothesis, so an elaborator cannot invent an input bound (per encode-lessons-in-structure and type-system-discipline).
3. **Lemmas live in evidence, not in statements.** A truss's stability and member-buckling checks need elastic member forces, which only a solver can bound. The statement names them as `DefinedHyp(sym, MinimizerComponent(problem, i, scale))`. The evidence proposes a range and proves it with hypercircle fields. The kernel checks the lemma, then uses the range. The rule that can prove a quantity declares it as a `Lemma` on its `RuleSpec`, and `check` finds the lemma through `rules.LEMMAS`, so a new quantity never edits `check.py`. Solver-chosen numbers never enter a statement, so decision 1 holds for statically indeterminate structures too.
4. **Force densities make truss equilibrium exact.** With rational node coordinates, the equilibrium matrix in force densities q = N/L has entries x_j - x_i. Lengths appear only as `Sqrt(L^2)` inside capacity and weight expressions, which the kernel encloses rigorously. No float and no rounding ever touch an equality the kernel checks.
5. **One theorem covers each kind of uncertainty.** By convexity, checking every vertex of the load box covers loads that enter affinely (R1 right-hand sides, R3 load vectors). Interval evaluation over the whole box covers material and geometry ranges. A load-factor range [0, lambda] in R2 is a hypothesis inside the geometric-stiffness weights, and one Loewner lower bound plus one LDL^T covers every factor at once, so no pencil lemma is needed.
6. **Family reuse is an instance of a checked theorem.** The library is untrusted storage. A query inside a family box gets `Instance` evidence: the family statement, the family's evidence, and a renaming from family symbols to query symbols. The kernel checks the family evidence once per process and remembers the theorem by the hashes of the family statement and evidence. For each query it then checks that the query is the family statement with every symbol renamed one to one and every `RangeHyp` range narrowed. A theorem for every point of the family box holds at every point of a narrower box, so one family check serves every query, and a query costs one pass over its own statement. One kernel rule serves all six goal kinds, so a new rule needs no reuse code. The renaming must move every reference to a symbol, and `tests/test_kernel_instance.py` checks that statements name symbols only through `Sym` and the `sym` binder fields.
7. **Every model input is a hypothesis, even a point value.** A concrete 2.5 mm2 wire and the 2.5 to 16 mm2 family produce statements with the same shape and different boxes, so the library matches them by a shape hash that erases ranges and labels.
8. **Elaborators are hashed into their premises.** `ModelSpec.source_hash` is the sha256 of the elaborator module's source. Editing the physics changes the `model:` label in every footprint and every family key that depends on it.
9. **One registration per concept, and every table is derived.** A rule is one `RuleSpec` in `kernel/rules/_REGISTERED`, and a domain is one `DomainSpec` in `models/_REGISTERED`. Each `_index` refuses a registry that would make a table ambiguous: a type, tag, kind or mode claimed twice, a spec naming an untagged type, or a domain reaching a mode it does not declare. A failure mode is declared once, by the domain that owns it, and waivers name it by id. The typing aliases (`Goal`, `ProofEvidence`, `QuantityDef` and the rest) stay for readers. `tests/test_structure.py` fails when an alias and the registry disagree, `tests/test_domain_registry.py` does the same for domains, and `tests/test_solver_registry.py` for solver modules (per model-the-domain and encode-lessons-in-structure).
10. **A margin is a second statement, not a tolerance inside a rule.** `claim NAME: QOI <= B margin m` keeps the claim's statement as it was and adds one built by the same builder from the requirement with its bound at B - m (`Criterion.tightened`). Builders read only the relation and the bound, so they need no change, and the kernel sees two ordinary statements. FAIL is a refutation of the claim. The pipeline tries every margin witness against the claim too, at every expression of its goal, so it never reports a point past the bound as merely within the margin. MARGINAL is a proof of the claim plus a refutation of the margin statement. PASS is a proof of the claim with no point found within the margin, and the report says whether the margin statement was proved as well ("margin proved") or not ("margin undecided"). A certificate that proves the margin statement proves the claim, whose goal is weaker, so the pipeline accepts it for both. A point within the margin without the claim's proof is UNKNOWN, with the point shown. Such a point says nothing about the rest of the box, and MARGINAL must not rate a claim that may fail elsewhere above UNKNOWN.

    The two statements make a claim decidable at tolerance m, in the sense of Gao, Avigad and Clarke's delta-decidability. The claim's peak is the worst value its quantity reaches over the box, and the peak decides the verdict:

    - A peak at least m inside the bound leaves slack m, which a fine enough partition proves. The verdict is PASS.
    - A peak past the bound is refuted. The verdict is FAIL.
    - A peak strictly between B - m and B leaves the claim some slack and the margin search a point. The verdict is MARGINAL.
    - Only a peak exactly on B, or an exhausted budget, leaves UNKNOWN, and the report then shows the margin point.

    Apart from those two cases, UNKNOWN is left for missing premises and missing models. `verdict.WithinMargin` and `verdict.Discharged` check that the margin obligation is the claim's own requirement at its own tightened bound, over the same model, with the same goal type and the same hypotheses. A builder that states its margin any other way gives the claim an open item, "margin not checked", and a warning, never a silent PASS.
11. **An envelope is a search over checks, not a new kind of proof.** `petra envelope` (`petra/envelope.py`, untrusted) replaces one input's range with a probe interval and calls `check_design`. A claim holds for all values in its ranges, so a PASS over an interval is a PASS over every interval inside it. Whether [anchor, x] passes is therefore monotone in x, even when the physics is not, and bisection on x finds the end of the proved interval within the resolution. A counterexample or margin point at input value v blocks every interval holding v, so growth stops there at once. The answer is a PASS that the pipeline assembled, so the envelope adds nothing to the trusted base. The search is bounded. It runs at most `--max-probes` checks (default 64), shared between the two sides after the anchor check and the confirming check are reserved, and it never bisects finer than 1/2^20 of the probe range. The report notes a raised resolution and a side that stopped at the limit. The exit code is the worse of the anchor's status and the status of the obligations that do not depend on the input, so a design that fails elsewhere never exits 0 from `petra envelope`.
12. **A model's numeric validity limits are statements the kernel checks, not text.** A `ModelSpec` lists its limits as `ValidityRow`s, each an inequality over the same quantities as the claim. Examples are |N|/(A fy) <= 1 for a linear-elastic member, |N|/(E A) <= 0.002 for small strain, and D fy <= 90 t 235 MPa for a class 3 tube. Every obligation carries one validity obligation per row of its model, built over the same hypotheses and load case, with mode `validity.<row>` and no criterion. A row is a separate statement, not a conjunct of the claim's goal, so each proof stays one rule and one certificate. A row shared by several obligations of one load case is solved once per run, keyed by its statement hash.

    `Discharged` and `WithinMargin` need a theorem of every row over the whole box, so a PASS or MARGINAL never rests on a model used outside the range its rows state. A proof of the claim alone is not enough for a PASS. The claim could hold only because the model is wrong where it is used. `Refuted` needs each row proved over the box or at the refutation's point. `verdict.at_point` narrows every range hypothesis the refutation assumes to its value there, and leaves the rest at full range. A FAIL is therefore a counterexample at which the model holds, even when a row fails elsewhere in the box. A row refuted at the point gives UNKNOWN with `OutsideValidity`, which names the model, the row and the point. An undecided row gives its own needs. The pipeline takes the first counterexample the sources offer and does not search for another where the rows hold. A claim whose first counterexample lies outside the model's range therefore reads UNKNOWN with that point, even when a valid counterexample exists elsewhere in the box.

    The kernel never learns what a row means. Validity lives in the elaborators and the pipeline, and the kernel checks ordinary statements. A limit not yet stated as a row is listed in `ModelSpec.unchecked`, and the premise text prints it as "not checked: ...". `tests/test_validity.py` fails when a model's validity text states a numeric limit in words.

    A limit past which the design itself has failed is a failure mode with its own check, not a row. A bolted joint that opens is one example. VDI 2230 never designs an opened joint, so coverage demands `bolt.separation`, (1 - Phi) F / n <= T / (K d), of every joint. The tension model needs no row for it either, because its bolt force, max(T / (K d) + Phi F / n, F / n), is exact whether the plates stay clamped or part. A counterexample past opening is therefore a FAIL.

### Where validation lives

Validation happens at three boundaries and nowhere else (per boundary-discipline):

1. The front end. `lang.lower` checks design-level names, units, signatures, component kinds against `models.KINDS` and waiver modes against `models.MODES`, and returns a `Design` with generic components. Each domain's lowerer then checks its own attributes, local names, registry ids and qois (quantities of interest). A lowerer raises `ComponentError`, which the CLI reports as an input error, like a lowering error.
2. The codec. `kernel.codec` decodes certificate JSON strictly, rejecting unknown keys and non-canonical rationals, so one file has one meaning.
3. The kernel. `kernel.check` checks statement well-formedness before any rule runs.

Elaborators trust the IR, and rules trust the box that `check` hands them.

### Invariants carried by types

- A PASS needs issued theorems, a `Scope` and a non-empty `Footprint`, enforced by constructor checks and the kernel seal. Every theorem label must resolve.
- An UNKNOWN needs at least one open item, and an open item needs at least one typed `Need`, so an UNKNOWN never says only "unknown".
- `Discharged` and `Refuted` require the kernel result's statement to equal the obligation's statement.
- An obligation's validity obligations are exactly its model's rows, in order, each over the same model with the obligation's requirement in the row's mode (`Obligation.__post_init__`). A validity obligation has no rows of its own.
- `Discharged`, and `WithinMargin` with a theorem, need an issued theorem of each row's statement, in order. `Refuted` and `Fail` need one of each row's statement or of the row at the refutation's point (`verdict._validity_bound`). A footprint lists the premises the row proofs used.
- A margin obligation must be the claim's requirement with its criterion tightened by its own margin, over the same model, with the same goal type and the same hypothesis names in order (`verdict.margin_pair_fault`). `WithinMargin` and `Discharged` both check this. `WithinMargin` also requires its refutation's statement to equal the margin obligation's, and any theorem it carries to be the claim's own. `Discharged` refuses a claim with a margin but no margin obligation, and a margin theorem must prove the margin statement.
- `Marginal` and `assemble` refuse a `WithinMargin` without the claim's theorem, so a MARGINAL always rests on a proof of the claim. A point without one travels as `Open.near`, which must be a theorem-less `WithinMargin` for the open item's own requirement and statement.
- A `Footprint` holds premises sorted by label, each label once.
- An input bound cannot exist without a `Signature`, because `ir.Input` has no optional owner.
- A premise cannot carry tag `proved`, and its tag must fit its label namespace (`premises.ALLOWED_TAGS`). An owner's load range can never be tagged `sanctioned`.
- Refutation evidence names a point inside every `RangeHyp` range. Each `DefinedHyp` range is proved by its lemma at that point, and the rule shows the goal fails across those ranges, so a counterexample is always a point the premises admit with the true defined values there.
- `RangeHyp` and `DefinedHyp` are separate types, so a defined quantity cannot carry a range the statement asserted.

### What the design never does

- The kernel never interprets a label, a unit, or a physical name.
- No part of Petra substitutes a default input bound. A missing bound is a `Gap` needing `NeedsInputBound`. Petra still checks a design with no environment class. Builders that need the class report `NeedsInputBound`, and the galvanic rule treats an undeclared environment as wet.
- The library and the certificate directory are never trusted. The kernel checks what they offer on every use. It checks a library family once per process, and every query against that family.
- The consistency checker can only add open items needing `RegistryInconsistent`, never remove one.

### Shared state

The only shared mutable state is the certificate directory and the library, which CI and `certify-family` may write at once. Both name each file by the hash of the statement it proves, and both write by temporary file plus atomic rename. Two writers of one entry each write a complete, kernel-accepted file, and whichever rename happens last wins, with nothing lost. A crash leaves no partial file, and a second run finds the entry present and writes nothing (per separate-before-serializing-shared-state and make-operations-idempotent). Readers re-check everything, so a stale or foreign file costs a rejection, never a wrong verdict. Inside one process the kernel also keeps a bounded memo of the family theorems that `Instance` evidence used, keyed by the hashes of the family statement and evidence. Only a theorem `check` has just issued for exactly those hashes enters it, so the memo saves time and changes no verdict. Everything else is a pure function of the design and the registry.

### Interface depth

`kernel.check(statement, evidence)` is one function over plain data. It hides six theorems, rigorous sqrt, ln, exp and pi, vertex enumeration in a canonical order, the Loewner bound, Sylvester's law of inertia, the hypercircle identity, lemma discharge, and sealing. A caller learns the term language and nothing about how a rule checks.

`pipeline.check_design(design, registry, sources)` is the only way to get a verdict. A source is a one-method protocol (`offer`), so certificate files, the library and the solvers plug in the same way. A new source, such as a remote solver farm, is one class.

An elaborator is one function per failure mode, `(requirement, typed model, design, registry) -> tuple[Obligation | Gap, ...]`, registered on its domain's `DomainSpec`. It hides all of a domain's physics, and the rest of Petra sees only statements.

The exposed complexity is the term language itself. An elaborator author must express physics as one of six goal shapes. Those six shapes are the price of a physics-free kernel, and [Alternatives considered](#alternatives-considered) weighs that price.

## Certificate JSON format

A certificate file is an envelope around two kernel terms, a statement and its evidence. The file stores the statement so that the file can be checked on its own (call site 3). Petra's pipeline never trusts that stored statement. The pipeline re-elaborates the design and looks files up by the hash of the fresh statement.

- Every term is an object with a `"t"` tag. Field keys are the dataclass field names in `kernel/terms.py`, `kernel/evidence.py` and the rule modules under `kernel/rules/`. `kernel/codec.py` lists the core tags and merges in the tags each `RuleSpec` declares.
- Rationals are strings, `"n"` or `"p/q"` reduced with q > 1. The decoder rejects decimals, exponents and floats. Counts and indices are JSON integers.
- Strings may not hold surrogate code points. Canonical text escapes a surrogate pair and the character it encodes alike, so allowing them would let two terms share a hash.
- Matrices are `{"t": "matrix", "rows": m, "cols": n, "entries": [[i, j, "p/q"], ...]}` in (i, j) order with no zeros.
- Canonical text is `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`. `statement_hash` is `"sha256:"` plus the hex digest of the canonical statement.
- Hypotheses are sorted by `sym` with no duplicates.
- An `instance` evidence body holds a family `statement`, the family's `evidence`, and a `renaming`: pairs of family symbol and query symbol, sorted by family symbol, covering every family symbol, bound ones included. Its envelope's `defined` list is empty, because the defined ranges come from the family theorem. The family evidence may not itself be an `instance`.

The example is the bolt-tension obligation from `bolt_unknown.petra`, copied verbatim from `examples/bolt_tension.cert.json`. `tests/test_docs.py` fails if the two differ. The builder names symbols by design path. Over the box, the goal says max(T/(K d) + phi F / n, F / n) - 0.9 Rp02 As <= 0. The first branch of the max is the bolt force while the plates stay clamped, and the second is the whole share F / n once they part. Here n is the bracket's bolt count, and As = (pi/4)((d2 + d3)/2)^2 is written out from the ISO 724 coefficients. The evidence is a single leaf. Within each branch of the max, every symbol with a nonzero range appears once, so the interval enclosure over the whole box equals the worst corner, up to the pi enclosure. A hand check of that corner gives 26,042 N of preload plus 3,000 N of external share, which is more than the 12,000 N of the opened branch. Against 0.9 x 450 MPa x 84.27 mm^2 = 34,128 N, that gives a margin of -5,086 N.

```json
{
  "format": "petra-cert/0",
  "kernel": "petra-kernel/0",
  "statement_hash": "sha256:4b704bfeffe30102181ec044dad0e38272fbed879c59c4cd3f1a05fb68851960",
  "statement": {
    "t": "statement",
    "hyps": [
      {"t": "range_hyp", "sym": "bolt.M12_A4_70.Rp02_min", "lo": "450000000", "hi": "450000000", "label": "reg:bolt.M12_A4_70.Rp02_min"},
      {"t": "range_hyp", "sym": "bracket.count", "lo": "1", "hi": "1", "label": "dsg:mast-bracket-coastal.bracket.count"},
      {"t": "range_hyp", "sym": "bracket.load_share", "lo": "1/10", "hi": "1/4", "label": "in:mast-bracket-coastal.bracket.load_share"},
      {"t": "range_hyp", "sym": "bracket.nut_factor", "lo": "4/25", "hi": "11/50", "label": "in:mast-bracket-coastal.bracket.nut_factor"},
      {"t": "range_hyp", "sym": "bracket.torque", "lo": "40", "hi": "50", "label": "in:mast-bracket-coastal.bracket.torque"},
      {"t": "range_hyp", "sym": "const.iso261.M12.d", "lo": "3/250", "hi": "3/250", "label": "reg:const.iso261.M12.d"},
      {"t": "range_hyp", "sym": "const.iso261.M12.pitch", "lo": "7/4000", "hi": "7/4000", "label": "reg:const.iso261.M12.pitch"},
      {"t": "range_hyp", "sym": "const.iso724.d2_coefficient", "lo": "649519/1000000", "hi": "649519/1000000", "label": "reg:const.iso724.d2_coefficient"},
      {"t": "range_hyp", "sym": "const.iso724.d3_coefficient", "lo": "1226869/1000000", "hi": "1226869/1000000", "label": "reg:const.iso724.d3_coefficient"},
      {"t": "range_hyp", "sym": "wind.bracket.force", "lo": "0", "hi": "12000", "label": "in:mast-bracket-coastal.wind.bracket.force"}
    ],
    "goal": {"t": "all_nonpositive", "exprs": [{"t": "add", "args": [{"t": "max", "args": [{"t": "add", "args": [{"t": "div", "num": {"t": "sym", "name": "bracket.torque"}, "den": {"t": "mul", "args": [{"t": "sym", "name": "bracket.nut_factor"}, {"t": "sym", "name": "const.iso261.M12.d"}]}}, {"t": "mul", "args": [{"t": "sym", "name": "bracket.load_share"}, {"t": "div", "num": {"t": "sym", "name": "wind.bracket.force"}, "den": {"t": "sym", "name": "bracket.count"}}]}]}, {"t": "div", "num": {"t": "sym", "name": "wind.bracket.force"}, "den": {"t": "sym", "name": "bracket.count"}}]}, {"t": "neg", "arg": {"t": "mul", "args": [{"t": "const", "value": "9/10"}, {"t": "mul", "args": [{"t": "sym", "name": "bolt.M12_A4_70.Rp02_min"}, {"t": "mul", "args": [{"t": "div", "num": {"t": "pi"}, "den": {"t": "const", "value": "4"}}, {"t": "pow_int", "base": {"t": "div", "num": {"t": "add", "args": [{"t": "add", "args": [{"t": "sym", "name": "const.iso261.M12.d"}, {"t": "neg", "arg": {"t": "mul", "args": [{"t": "sym", "name": "const.iso724.d2_coefficient"}, {"t": "sym", "name": "const.iso261.M12.pitch"}]}}]}, {"t": "add", "args": [{"t": "sym", "name": "const.iso261.M12.d"}, {"t": "neg", "arg": {"t": "mul", "args": [{"t": "sym", "name": "const.iso724.d3_coefficient"}, {"t": "sym", "name": "const.iso261.M12.pitch"}]}}]}]}, "den": {"t": "const", "value": "2"}}, "exponent": 2}]}]}]}}]}]}
  },
  "evidence": {"t": "evidence", "body": {"t": "enclosure", "partition": {"t": "leaf"}}, "defined": []},
  "producer": {"petra": "0.1.0", "source": "solver"}
}
```

The kernel's answer for this file, which `python -m petra verify examples/bolt_tension.cert.json` shows, is a `Theorem` whose `labels` are the ten labels above. The footprint built from those labels shows the four signed or measured inputs, the sanctioned ISO 261, ISO 724 and ISO 3506 values, `model:bolt.tension@...` and `cov:...`.

## Module map and line budget

Line counts do not include docstrings, comments or blank lines. `tests/test_kernel_budget.py` counts them and enforces [principles.md](principles.md) T2 from the manifest `tests/trusted_base.py`. The kernel's shared core holds at most 1,000 code lines, each rule has a manifest entry, and all trusted code holds at most `TRUSTED_CEILING` in that manifest, set to the 17,727 measured when the parts and boards decks merged on 2026-11-09. The kernel table and the trusted totals below were measured on 2026-11-08. The other tables are estimates from the v0 design.

### Trusted kernel, mathematics only and standard library only (the Lean port target)

| File | Owns | Code lines |
|---|---|---|
| `petra/kernel/interval.py` | `Q`, canonical rational parsing, `Interval`, outward rounding, rigorous sqrt, ln, exp, pi | 141 |
| `petra/kernel/terms.py` | `Expr` variants, `Matrix`, `RangeHyp`, `DefinedHyp`, `Statement` | 70 |
| `petra/kernel/evidence.py` | partitions, points, `Evidence`, `DefinedRange`, `Instance` | 34 |
| `petra/kernel/codec.py` | strict JSON codec, canonical text, hashes, core tags merged with rule tags | 130 |
| `petra/kernel/evaluate.py` | `enclose`, free symbols, affine decomposition, vertex order | 123 |
| `petra/kernel/linalg.py` | exact sparse products, Gram sums, LDL^T product | 43 |
| `petra/kernel/check.py` | `check`, well-formedness, registry dispatch, lemma handling, `Instance` checks and the family memo, issued results | 236 |
| `petra/kernel/rules/base.py` | `RuleSpec`, `Lemma`, `Invalid`, `TooWeak` | 30 |
| `petra/kernel/rules/__init__.py` | `_REGISTERED`, `_index`, derived tables, typing aliases | 92 |
| `petra/kernel/__init__.py` | public re-exports | 58 |
| **Shared core, capped at 1,000** | | **957** |
| `petra/kernel/rules/r1_linear.py` | goal and evidence types, vertex feasibility, Farkas | 71 |
| `petra/kernel/rules/r2_definite.py` | goal and evidence types, Loewner bound plus LDL^T, negative direction | 68 |
| `petra/kernel/rules/r3_hypercircle.py` | `QuadraticProblem`, `MinimizerComponent`, hypercircle enclosure, `prove_defined` lemma | 150 |
| `petra/kernel/rules/r4_enclosure.py` | goal and evidence types, partition walk, point witness | 64 |
| `petra/kernel/rules/r5_moment.py` | goal and evidence types, moment dual with cell-wise domination | 60 |
| `petra/kernel/rules/r6_scenario.py` | goal type, exact binomial tail | 44 |
| **Rules, one manifest entry each** | | **457** |
| **Kernel total** | | **1,414** |

### Trusted outside the kernel

These files decide what a statement means. A bug here can produce a wrong verdict, so they are trusted. The elaborators also appear in every footprint they touch as `validated_model` premises. The front end, IR, premises, coverage, verdict and pipeline are trusted without being premises, and [Open questions and risks](#open-questions-and-risks) asks whether they should be.

`tests/trusted_base.py` lists every trusted module outside the kernel, each with the judge or twin that checks it or a dated debt. On 2026-11-08 the list held 48 modules and 12,116 code lines (measured), so the whole trusted base held 13,530. The table below is the v0 design's estimate for the files v0 began with, kept as history. The steel and electronics decks and the mechanics layer came later.

| File | Owns | Estimate |
|---|---|---|
| `petra/models/base.py` | `FailureMode`, `ModelSpec`, `Requirement`, the `Need` variants, `Obligation`, `Gap`, coverage and port vocabulary, `DomainSpec`, `StatementBuilder` | 260 |
| `petra/models/truss.py` | truss model and lowerer, geometry, R1, R2, R3, R4 statements, coverage rules, `DOMAIN` | 380 |
| `petra/models/circuit.py` | circuit model and lowerer, series topology, heat balance, adiabatic, drop, overload statements, ports, `DOMAIN` | 380 |
| `petra/models/bolt.py` | joint model and lowerer, torque-tension and load sharing, features, coverage rules, `DOMAIN` | 170 |
| `petra/models/uncertainty.py` | demand model and lowerer, R5 and R6 builders, `DOMAIN` | 150 |
| `petra/models/contracts.py` | assume-guarantee statements over every domain's ports | 120 |
| `petra/models/__init__.py` | `_REGISTERED`, `_index`, derived tables (already complete) | 50 |
| `petra/registry/model.py` | makeable-set types, `Registry` lookups | 120 |
| `petra/registry/constants.py` | the short constants list | 250 |
| `petra/registry/catalog.py` | generators that derive every registry entry | 400 |
| `petra/registry/__init__.py` | re-exports | 0 |
| `petra/lang/lexer.py`, `syntax.py`, `parser.py`, `lower.py`, `__init__.py` | text to IR, generic component blocks | 850 |
| `petra/ir.py` | design IR with generic components | 220 |
| `petra/units.py` | exact units | 120 |
| `petra/premises.py` | tags, labels, premises, footprint, `PremiseBook` | 180 |
| `petra/coverage.py` | cross-domain rules, requirement generation, waivers | 160 |
| `petra/verdict.py` | verdict types, per-claim entries, assembly, JSON, rendering | 260 |
| `petra/pipeline.py` | `lower_components`, `elaborate`, `check_design`, `explain`, `Report`, source protocol | 220 |
| **Total, v0 estimate** | | **about 4,500** |

### Untrusted

A bug in any of these files costs an UNKNOWN or a slow run, never a false PASS, because the kernel re-checks everything they produce.

| File | Owns | Estimate |
|---|---|---|
| `petra/solvers/__init__.py` | `SOLVERS` derived by module name, `SolverSource` | 50 |
| `petra/solvers/exact.py` | float to exact repair | 160 |
| `petra/solvers/r1_linear.py` | R1 via HiGHS, Farkas rays | 160 |
| `petra/solvers/r2_definite.py` | R2 exact LDL^T, eigenvector refutation | 120 |
| `petra/solvers/r3_hypercircle.py` | R3 fields, `DefinedRange` lemmas | 160 |
| `petra/solvers/r4_enclosure.py` | R4 branch and bound, `search` | 200 |
| `petra/solvers/r5_moment.py` | R5 dual LP and domination tree | 140 |
| `petra/solvers/r6_scenario.py` | R6 | 20 |
| `petra/certs.py` | certificate envelope, `CertStore` | 120 |
| `petra/library/store.py`, `family.py`, `__init__.py` | library, `Instance` offers, family certification | 270 |
| `petra/registry/deck.py`, `consistency.py` | decks and the physics-consistency checker | 350 |
| `petra/envelope.py` | probe narrowing, bounded bisection, envelope reports | 410 |
| `petra/cli.py`, `petra/__main__.py`, `petra/__init__.py` | shell | 250 |
| **Total** | | **about 3,000** |

## Implementation seams

The sketch is the shared-types commit. Every type in it is complete, and only bodies are missing. Once it lands, the work runs in three waves of seams. A seam is one implementer's share of the work. Each seam owns its files outright, including its tests and examples, so no two implementers touch one file (per separate-before-serializing-shared-state). A seam that needs a helper from another seam's file asks that owner and does not edit the file. `petra/models/__init__.py` belongs to no seam. Its `_REGISTERED` tuple already names the four domains, and nobody edits it.

**Wave 1.** These seams need only the sketch.

| Seam | Owns |
|---|---|
| K kernel | every file under `petra/kernel/` (`interval.py`, `terms.py`, `evidence.py`, `codec.py`, `evaluate.py`, `linalg.py`, `check.py`, `__init__.py`, `rules/*`), `tests/__init__.py`, `tests/test_structure.py`, `tests/test_seal.py`, `tests/test_kernel_budget.py`, `tests/test_interval.py`, `tests/test_evaluate.py`, `tests/test_linalg.py`, `tests/test_codec.py`, `tests/test_check.py`, `tests/test_rules.py` |
| L language and units | `petra/lang/*`, `petra/ir.py`, `petra/units.py`, `tests/test_lang.py`, `tests/test_units.py` |
| G registry | `petra/registry/*` (`model.py`, `constants.py`, `catalog.py`, `deck.py`, `consistency.py`, `__init__.py`), `tests/test_registry.py`, `tests/test_registry_consistency.py` |
| P builder, premises, coverage, verdict | `petra/models/base.py`, `petra/premises.py`, `petra/coverage.py`, `petra/verdict.py`, `tests/test_domain_registry.py`, `tests/test_premises.py`, `tests/test_coverage.py`, `tests/test_verdict.py` |

**Wave 2.** These seams code against the sketch's signatures from the start and switch to running tests as K, L, G and P land.

| Seam | Owns | Needs |
|---|---|---|
| T trusses | `petra/models/truss.py`, `petra/solvers/r1_linear.py`, `petra/solvers/r2_definite.py`, `petra/solvers/r3_hypercircle.py`, `examples/truss_pass.petra`, `examples/truss_fail.petra`, `tests/test_truss.py` | K, L, G, P |
| C circuits, bolts, port contracts | `petra/models/circuit.py`, `petra/models/bolt.py`, `petra/models/contracts.py`, `petra/solvers/r4_enclosure.py`, `examples/circuit_pass.petra`, `examples/bolt_unknown.petra`, `examples/bolt_tension.cert.json`, `tests/test_circuit.py`, `tests/test_bolt.py`, `tests/test_contracts.py` | K, L, G, P |
| U uncertainty | `petra/models/uncertainty.py`, `petra/solvers/r5_moment.py`, `petra/solvers/r6_scenario.py`, `examples/hook_uncertain.petra`, `tests/test_uncertainty.py` | K, L, G, P, and `r4_enclosure.search` from C for R5 domination trees (its signature is in the sketch). The example uses the demand domain only, so U never waits on the bolt model. |
| I pipeline | `petra/pipeline.py`, `petra/certs.py`, `petra/solvers/__init__.py`, `petra/solvers/exact.py`, `petra/__init__.py`, `tests/test_pipeline.py`, `tests/test_certs.py`, `tests/test_solver_registry.py` | K, L, P |
| M mutation suite | `tests/test_kernel_mutations.py`, `tests/mutations.py`, `tests/fixtures/*` | K |

**Wave 3.** These seams need the pipeline (I). F also needs C, and Y also needs F.

| Seam | Owns | Needs |
|---|---|---|
| F library, families | `petra/library/*`, `examples/families/*`, `tests/test_library.py` | I, C |
| Y CLI | `petra/cli.py`, `petra/__main__.py`, `tests/test_cli.py`, `tests/test_examples.py` | I, F |

The sketch ships `tests/test_structure.py`, `tests/test_seal.py`, `tests/test_domain_registry.py`, `tests/test_solver_registry.py`, `tests/test_premises.py` and `tests/test_verdict.py`, and they pass. `scripts/predicate.py`, which checks the definition of done, names `tests/test_kernel_mutations.py` (M) and `tests/test_registry_consistency.py` (G), and the sketch leaves both out on purpose. A placeholder would exit 0 without running a mutation or a corruption, and the predicate would count it as verified.

The mutation suite (M) defines mutation operators per evidence type and per statement field. Each operator states why it must invalidate the certificate. The v0 operators are:

- R1. Perturb one entry of a feasible point whose column of A is nonzero, which breaks A x = b. Negate a Farkas ray, which cannot satisfy the strict inequality in both directions.
- R2. Make one LDL pivot non-positive.
- R3. Perturb one entry of a statically admissible field whose column of B is nonzero, which breaks B s = f.
- R4 and R5. Move a split point outside its cell. Zero the R5 multipliers when the failure region is non-empty.
- Refutations. Move the counterexample point outside the hypothesis box.
- Statements, R6 included. Edit one byte of a stored statement, which the hash check catches before the kernel runs.

An operator that can leave a certificate valid, such as scaling a Farkas ray by a positive constant, is not in the suite.

## Synthesis decision

The base is candidate 1, this design. The arena rubric chose it, and an independent cross-judge agreed. Candidate 1 scored 4, 4, 2, 4, 4, 5 against candidate 2's 2, 3, 4, 4, 3, 4.

The design took four grafts from candidate 2. A graft is a piece of the losing design carried into the winner.

1. **Registration.** Each registry has one `_REGISTERED` tuple, and every other table is derived from it. For kernel rules, each rule module declares its goal, evidence and lemma types, their tags and its check functions in one `RuleSpec` (`petra/kernel/rules/base.py`, `petra/kernel/rules/*.py`). `GOAL_RULE`, `RULES`, `PROOF_RULE`, `REFUTATION_RULE`, `LEMMAS` and `MODULE_OF` are derived in `petra/kernel/rules/__init__.py`, the codec tags in `petra/kernel/codec.py`, and the solver table by module name in `petra/solvers/__init__.py`. For domains, `petra/models/__init__.py` names the four `DomainSpec`s, and each domain module owns its component kinds, failure modes, coverage rules and elaborators (`petra/models/base.py`, `petra/models/<domain>.py`). The typing aliases stay, checked against the registries by tests.
2. **Generic components.** An IR component is a kind, a name and typed attribute lines (`petra/ir.py`, `petra/lang/syntax.py`). The grammar and the IR know no domain.
3. **Typed needs.** A `Need` union replaces free-text needs (`petra/models/base.py`, `petra/verdict.py`): `NeedsCertificate`, `CertificateRejected`, `CertificateTooWeak`, `NeedsInputBound`, `NoRuleForQuantity` and `NoModel`, plus this design's `RegistryInconsistent`. Candidate 2's `NeedsWaiver` is folded into `NoModel`. Here both name the same state, a mode no model builds, which only a waiver or a design change closes.
4. **A demand-versus-capacity uncertainty example.** It follows candidate 2's hoist hook (`examples/hook_uncertain.petra`, `petra/models/uncertainty.py`). The uncertainty seam no longer depends on the bolt model.

Review of this design led to these fixes:

- Seal laundering. `dataclasses.replace` on a theorem returned a sealed theorem. Theorems and refutations are now bare handles over a kernel-private table (`petra/kernel/check.py`), and `tests/test_seal.py` attacks them.
- Lemma proving dispatches through `rules.LEMMAS` instead of naming `r3_hypercircle` in `check.py`.
- The constructor checks in `petra/verdict.py` and `petra/premises.py` are implemented, not left as TODOs.
- `build_premise_book` has the signature its one call site uses, `(design, registry, outcomes)`.

The synthesis rejected candidate 2's untrusted lowering. That lowering writes raw numbers into models, and those numbers never reach the footprint. A wrong lowering could change a verdict with no premise naming it. The cross-judge found this soundness hole. Here the lowerers are trusted, every model number enters a statement through `StatementBuilder` as a labelled hypothesis, and the footprint is derived from the labels of the theorems used.

Both candidates chose canonical rational strings in certificate JSON, certificates bound to statements by hash, untrusted libraries re-checked on every use, and verdicts that cannot be built without kernel results. The candidates reached these choices independently, and that agreement is some evidence that the choices are right.

## Tradeoffs accepted

- We accept a trusted base outside the kernel (front end, elaborators, registry derivations, coverage, verdict, pipeline) in exchange for a kernel with no physics in it. On 2026-11-08 it held 12,116 code lines against the kernel's 1,414 (measured), and T2 counts both under one ceiling. The Lean port moves only the kernel. The rest stays Python and stays trusted.
- We accept that elaborators carry real physics risk in exchange for naming each one, by source hash, in every footprint it touches. A wrong heat-balance formula is visible as a premise, not hidden in a checker.
- We accept bigger statements, because every model input is a hypothesis even when it is a point value, in exchange for a structural footprint and family matching by shape.
- We accept conservative relaxations inside the rules in exchange for one simple theorem each. R1 evaluates bounds over the whole box. R2 checks a Loewner lower bound. Lemma ranges are quantified independently of each other. Each can turn a true PASS into UNKNOWN. None can produce a false PASS.
- We accept rational node coordinates in exchange for exact equilibrium. A 60-degree truss must be drawn with a rational approximation, and the verdict is about the truss as drawn. Geometric tolerances are not modelled in v0.
- We accept plastic collapse only for a statically determinate truss. The static theorem lets a buckled member keep its buckling resistance while load redistributes. That assumption is unconservative wherever there is load to redistribute. The plastic model's row "the truss has no state of self-stress" is an R2 statement that B^T B is positive definite, a condition that holds exactly when B's columns are independent. An indeterminate truss therefore reads UNKNOWN on its strength claim, with OutsideValidity naming the row. A mechanism (fewer members than free degrees of freedom) passes the row. R1 still refutes its collapse claim when no static field carries the load, and global stability, demanded beside collapse, refuses a mechanism that carries it. With no state of self-stress nothing redistributes, so the class 3 row is enough where EN 1993-1-1 5.6 asks for class 1 before plastic redistribution.
- We accept bounds on how a member's own weight acts along it, in exchange for keeping the truss pin-jointed. Each member's weight, g rho A L with g at the top of its registry range, loads its two end joints, half at each, in every load case. The plastic model shifts the member bounds by an exact right inverse of B, and a second copy of the field must carry the weight alone, since a factor claim covers every factor from 0 up. The elastic models superpose the load case with one unit load per free vertical degree of freedom, each an R3 lemma. Along an inclined member the force is taken at its worse end, and a tension or yield check adds the midspan bending by the linear interaction of EN 1993-1-1 6.2.1(7). In compression the same bending lowers the buckling resistance, by the member check of 6.3.3 with Annex B. A tube does not twist, so (6.62) never governs, and (6.61) reads N / N_b + k_yy M / M_Rk <= 1. The model takes three bounds that hold for every section the class 3 row admits. k_yy is taken at its cap of Table B.1, C_my (1 + 0.8 N / N_b). C_my is 0.95, from Table B.3 for a uniform load with no end moments. M_Rk is W_el fy, which Table 6.7 lets class 1 and 2 raise to W_pl fy. The compression capacity is then N_b (1 - x) / (1 + 0.8 x), with x = 0.95 M / (W_el fy). Table B.1 names I and RHS sections, and the model reads a tube the same way. These factors are recalled, not read from the EN text, which is not in the repository. Annex A, the other method 6.3.3 allows, is not computed, so the capacity never exceeds the Annex B one. Every joint is taken as braced out of plane, so a member buckles over its length L about every axis, and the footprint states that too.
- We accept that a family certifies its claims only, without coverage, in exchange for families that work as reusable lemmas across designs that differ in breakers and terminals.
- We accept a coverage table that is one judged premise in exchange for saying plainly that what can go wrong is an engineering judgement.
- We accept an extra kernel check per validity row, about a third more checking time on the test suite, in exchange for PASS and FAIL that never rest on a model used outside its range. A claim whose model leaves its range somewhere in the box now reads UNKNOWN where it used to read PASS. A FAIL needs the rows only at its own point, so a design is not excused by a row that fails elsewhere.

## Alternatives considered

- **A physics-aware kernel.** This alternative is the closest to the frame's wording. The kernel builds equilibrium and heat-balance equations from the IR. Its interface is as small as this one (`check(design, certificate)`), but it hides physics inside the trusted core. Every v1 rule (continuum finite elements, reduced basis, neural surrogates) adds physics to the kernel, the kernel's 1,500-line budget of the time breaks within one release, and a Lean port must formalise trusses and wires. It lost because the part that must be small and portable would grow with every domain.
- **An LCF-style kernel.** The kernel has a handful of inference rules, and theorems are built by composing them, as in HOL Light. It is the closest match to Lean and would make lemma use first-class. It lost on size and solver burden. Solvers would have to emit proof terms, and six certificate checks plus their supporting lemmas would not fit in the 1,500 lines the kernel was then allowed.
- **Statements that carry solver-chosen lemma bounds.** They need a separate `discharge(theorem, sym, lemma)` kernel call. This alternative exposes one more kernel entry point and makes statements depend on solver output, and that dependence breaks binding by hash. `DefinedHyp` keeps one entry point and keeps statements a pure function of the design.
- **Footprints listed by elaborators.** Each obligation would carry its footprint as a side list. That list is simpler to write, but it creates a second source of truth that an elaborator can forget to update. Deriving the footprint from hypothesis labels makes omissions impossible for numeric premises, and the unused-hypothesis rule makes padding impossible.
- **A trusted result cache.** For family reuse, the library would store "the kernel checked this", and a query would do a containment check only. The cache is faster, but it makes the library part of the trusted base and needs signing or a ledger premise. The kernel's own per-process memo of family theorems it checked keeps the library untrusted and gives the same speed after the first query.
- **MARGINAL only for an undecided claim.** The first margin design reported MARGINAL only when the claim was neither proved nor refuted. A claim proved one degree under its bound then read PASS, which hides exactly what a margin asks about. The second design reported a margin point as MARGINAL whether or not the claim was proved. MARGINAL reads better than UNKNOWN, so a claim that failed at a corner the search never reached read better than a claim with no evidence at all. MARGINAL now needs the claim's proof, and a margin point without one is UNKNOWN with the point shown.
- **PASS only when the margin statement is proved.** It would make PASS mean "holds with slack m", but it moves the problem case, a peak exactly on the bound, from B to B - m. A design that peaks exactly at B - m can neither prove the margin statement nor refute it, so UNKNOWN returns. Proving the claim and finding no margin point keeps a gap of m between the two searches. PASS instead says which case holds, "margin proved" or "margin undecided".
- **Evidence transport.** This was v0's first reuse design. It cut the family's evidence down to the query box, with one transport function per rule, and the kernel re-checked the result against the query. It was sound, but every query paid a full kernel check, which bounded reuse at about 1.57x even with free transport (1.31x measured on the Warren truss family). `Instance` evidence replaced it and measured 1.64x and 1.92x in two runs on the same family, with no solver call and no kernel enclosure per query.

## Open questions and risks

- Should the front end and pipeline appear in the footprint, for example as a `validated_model` premise "petra-language v0 semantics", so the footprint lists all trusted code and not only the elaborators?
- A counterexample search that respects the rows would turn some UNKNOWNs into FAILs, namely those whose first counterexample lies outside the model's range (decision 12). On loads of 100 to 170 kN the solver refutes a 250 MPa stress claim at the 170 kN corner, past yield, so the claim reads UNKNOWN, although 130 kN refutes it where the member is elastic. The R4 refuter could search the box with the rows as constraints, or the pipeline could retry with the box cut at the row's boundary. Which is worth it?
- A statically determinate truss's member forces follow from statics alone, so they stay exact past yield, and the below-yield and small-strain rows are needed only for elastic forces in an indeterminate truss. As built, a determinate truss loaded past yield gives UNKNOWN on its member-buckling obligations rather than FAIL. Plastic collapse still fails it unless that mode is waived. Should the elastic rows depend on determinacy?
- The stability model's rows are checked at load factor 1. A claim of a stability factor below 1 can then read UNKNOWN on a row the claimed load never reaches.
- The truss compression capacity takes W_el fy for M_Rk, which holds in class 3. A class 2 row (D / t <= 70 eps^2, recalled) would let it take W_pl fy, 1.31 to 1.36 times W_el for the six registry tubes (computed). On a two-panel 12 m Warren girder whose top chord is one 6 m CHS 48.3x3.2, that raises the largest node load a collapse factor of 1.5 allows from 0.733 kN (measured) to 0.806 kN (computed). The code gives 0.918 kN at E = 210 GPa with the more favourable annex (computed). Is the tighter capacity worth a second class row?
- The truss rows do not yet state EN 1090 erection tolerances, the partial factor (gamma_M1 is taken as 1), or whether the class 3 row should apply to tension members, which cannot buckle locally. The 0.002 small-strain limit is the maintainers' choice, not a code value. Who owns those choices?
- The adiabatic fault model still needs "the fault is cleared within 5 s" as a row, but no breaker operating time is in the registry, so it is listed as not checked. Should breaker curves become sanctioned premises?
- Should wire resistance come from resistivity over nominal area, as the frame says, or from the IEC 60228 maximum resistance, which is the value the standard guarantees? The consistency checker relates the two either way. Decided on 2026-11-06: a registry value may be the specified limit when the standard guarantees the limit rather than the property (plan §8 item 7).
- Should a FAIL that rests on a point admitted only by a spec range (yield at its guaranteed minimum) be reported differently from a FAIL at an owner-signed load corner? Both are refutations relative to premises, but they read differently to an owner.
- When a claim and a coverage default address the same mode on the same subject, is "keep the stricter, keep both if incomparable" the rule the owner expects?
- Independent lemma ranges lose correlation between member forces. On highly indeterminate trusses this may give UNKNOWN for global stability. Is v0 allowed to stay determinate-first?
- Who owns the galvanic thresholds (0.15 V for wet or C3 and above, from MIL-STD-889C), and the convection coefficient range for clipped-direct cables? Both are judged constants with a named owner in the sketch.
- A claim whose peak sits exactly on its bound costs the claim search its whole cell budget before the margin search answers. On x(1 - x) <= 1/4 the R4 search spent all 20,000 cells (6 s in one dimension, 18 s in three) and gave up, then the margin statement was refuted in one cell, so the report is UNKNOWN with that point. A combined search that proves at B and witnesses at B - m in one pass would stop at once, but it would give up on the claim's proof, and a claim with less than m of slack would read UNKNOWN where it could have been MARGINAL. Is the cell budget the right place to pay for that?
- `petra envelope` probes one input. A safe region over two inputs, such as ambient and load current together, needs a 2D partition of probe boxes, and an input with a mean is refused, since a probe interval need not contain it. Its probe limit counts checks, not time, and 64 checks of a design with a claim whose peak sits exactly on its bound can still take minutes. Should the limit be a time budget?
- The kernel cannot defend against code that runs in its own process. The K3 red team reproduced three such attacks, none of them through data:
  - `object.__setattr__` on an issued theorem's `statement` left it issued with a false goal, and `verdict.Discharged` then accepted it for a false obligation. The bare handles of data structure 4 have since closed this attack, and `tests/test_seal.py` checks that the assignment raises and changes nothing.
  - Writing into the cached `i_pi()` interval makes `check` issue a theorem for a false statement. While the family memo holds a theorem checked in that window, it keeps lending that theorem after pi is restored.
  - A caller's `Fraction` subclass answers the canonical-form guard's equality, so a raw statement can compare equal to a theorem about its canonical copy.

  Certificates and agent designs must therefore reach the kernel as data, through the codec, never as Python objects built by untrusted code. Untrusted code must still never run in the checker's process. The Lean kernel, or a kernel in its own process, removes the class of attack.

## Next implementation step

Start wave 1. K begins with `kernel/interval.py` and a test that encloses sqrt(2), ln(2), exp(1) and pi against 50-digit `decimal` references. L, G and P start in parallel.
