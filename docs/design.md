# LoLa v0: the math-only kernel

This is the design of record. It began as arena candidate 1 and carries the grafts and fixes listed under Synthesis decision.

## Problem

LoLa turns a `.lola` design into a verdict that is a theorem relative to named premises. Untrusted solvers produce certificates, and a small kernel checks them in exact rational arithmetic. The frame asks for six certificate rules, four physics domains, a makeable set, coverage, port contracts, family certificates, a gym, and a kernel under about 1,500 lines that a Lean kernel can later replace.

The shape is not obvious because of one sentence in the frame. Each rule checks a certificate "against equations the kernel builds itself from the design". If the kernel builds the equations, the kernel knows physics, and the Lean port has to port trusses, wires and bolts too. Every v1 item (continuum FE, reduced basis, neural surrogates) would add physics to the kernel.

This candidate keeps the intent and moves the physics. The kernel knows only mathematics: rationals, intervals, expressions, exact matrices, and six theorems about them. Small trusted elaborators, one per domain, build the equations from the design. A solver still never supplies a matrix or a model equation. It receives a statement an elaborator built and returns numbers. Each elaborator is named in every footprint as a `validated_model` premise, keyed by the hash of its source.

The design honours the frame's constraints. `lola/kernel` imports only the standard library, and a test enforces it. Certificates are language-neutral JSON. A PASS cannot be built without theorems the kernel issued, a scope and a footprint. An UNKNOWN always names, as typed data, what would close it. The checker never invents an input bound.

## Usage (caller's view)

### README quickstart

```text
python -m lola check examples/truss_pass.lola
```

`check` parses the file, elaborates every claim and every coverage obligation into kernel statements, gathers evidence (stored certificates, then the library, then the solvers), and lets the kernel decide each one. The output below is captured from the build, with hashes cut to four hex digits, certified premises collapsed to one line, and long lines cut.

```text
warren-footbridge-panel: PASS
entries    strength PASS, stability PASS, stress PASS, coverage PASS
scope      load cases crowd; environment indoor_dry; no parameters
checked    11 obligations, 11 certified, 0 refuted, 0 waived, 0 open
  frame/truss.plastic_collapse                 claim strength               R1  certified  solver  sha256:16af..
  frame/truss.global_stability                 claim stability              R2  certified  solver  sha256:2a8a..
  frame.diag_ad/truss.elastic_stress           claim stress                 R3  certified  solver  sha256:78ad..
  frame/truss.small_strain                     coverage truss.frame         R3  certified  solver  sha256:5872..
  frame.bottom_ab/truss.member_buckling        coverage truss.axial_member  R4  certified  solver  sha256:0486..
  frame.bottom_bc/truss.member_buckling        coverage truss.axial_member  R4  certified  solver  sha256:90a5..
  frame.top_de/truss.member_buckling           coverage truss.axial_member  R4  certified  solver  sha256:0482..
  frame.diag_ad/truss.member_buckling          coverage truss.axial_member  R4  certified  solver  sha256:eab2..
  frame.diag_db/truss.member_buckling          coverage truss.axial_member  R4  certified  solver  sha256:2972..
  frame.diag_be/truss.member_buckling          coverage truss.axial_member  R4  certified  solver  sha256:c9d0..
  frame.diag_ec/truss.member_buckling          coverage truss.axial_member  R4  certified  solver  sha256:bc2f..
footprint  24 premises
  certified        cert:sha256:0482.. and 10 more   kernel-checked in this run
  sanctioned       reg:const.en10219_2.60_3x3_2.D   CHS 60.3 x 3.2 has outside diameter 60.3 mm   (CEN; EN 10219-2:...
  sanctioned       reg:const.en10219_2.60_3x3_2.t   CHS 60.3 x 3.2 has wall thickness 3.2 mm   (CEN; EN 10219-2:200...
  sanctioned       reg:const.en10219_2.76_1x3_2.D   CHS 76.1 x 3.2 has outside diameter 76.1 mm   (CEN; EN 10219-2:...
  sanctioned       reg:const.en10219_2.76_1x3_2.t   CHS 76.1 x 3.2 has wall thickness 3.2 mm   (CEN; EN 10219-2:200...
  sanctioned       reg:const.steel.E   the elastic modulus of structural steel lies in [200, 210] GPa   (CEN; EN 19...
  sanctioned       reg:steel.S355.fy   steel.S355.fy 355000000 Pa, minimum upper yield strength ReH, nominal thickn...
  validated_model  model:truss.elastic@798e..   linear elastic pin-jointed 2D truss: member forces minimise the com...
  validated_model  model:truss.euler@798e..   pin-ended prismatic Euler column: compression N <= u pi^2 E I / L^2;...
  validated_model  model:truss.plastic@798e..   rigid-perfectly-plastic pin-jointed 2D truss, static (lower-bound)...
  validated_model  model:truss.stability@798e..   linear prebuckling of a pin-jointed 2D truss, Green-strain geomet...
  assumed          in:warren-footbridge-panel.crowd.frame.D.fy   crowd.frame.D.fy in [-24000, -16000] N   (client.s...
  assumed          in:warren-footbridge-panel.crowd.frame.E.fy   crowd.frame.E.fy in [-24000, -16000] N   (client.s...
  judged           cov:2ed9..   every failure mode a v0 design must address is demanded by one of galvanic.contact,...
```

The report has one entry per claim and one entry named `coverage` for the requirements no claim made (coverage rules and port contracts). The design's verdict is the conjunction of the entries. `--json` prints the same report as data:

```json
{"file": "examples/bolt_unknown.lola", "design": "mast-bracket-coastal", "status": "UNKNOWN", "verdicts": [
  {"claim": "tension", "status": "PASS", "rules": ["R4"], "obligations": [],
   "footprint": [{"tag": "assumed", "label": "in:mast-bracket-coastal.wind.bracket.force", "owner": "client.structures@example.org", "source": "wind study WS-4, 50-year return"}, "..."]},
  {"claim": "coverage", "status": "UNKNOWN", "rules": [],
   "obligations": ["no model for corrosion.galvanic on bracket: waive corrosion.galvanic on bracket by ...", "no model for bolt.plate_bearing on bracket: waive bolt.plate_bearing on bracket by ..."],
   "footprint": ["..."]}]}
```

`obligations` is non-empty exactly when the entry is UNKNOWN. Each line is `verdict.describe_need` applied to one typed `Need`.

The other commands are `lola explain FILE` (print the statements with every hypothesis label), `lola verify CERT.json` (check a certificate file on its own, the job a Lean kernel will take over), `lola certify-family FILE --library DIR`, `lola registry build --out DECK` and `lola registry check [DECK]` (with no deck it checks the shipped registry and exits 0 when every relation holds), and `lola gym --episodes N --seed S`, which prints a `solved k/N` line. The family benchmark is `scripts/bench_family.py`, which prints a `reuse` line and a `recompute` line. Exit codes for `check` are 0 PASS, 1 FAIL, 2 UNKNOWN, 3 input error, taken from the overall status.

### Call site 1. A CI gate in a hardware repo

```python
import sys
import lola
from lola.premises import Tag

report = lola.check_file("designs/bracket.lola", certs="certs/", library=lola.Library("lib/"), solve=False)
print(report.render())
verdict = report.verdict
if not isinstance(verdict, lola.Pass):
    sys.exit(1)
judged = [p for p in verdict.footprint.premises if p.tag is Tag.JUDGED and not p.label.startswith("cov:")]
APPROVED_SIGNERS = {"m.engineer@example.org", "a.reviewer@example.org"}
if any(p.owner not in APPROVED_SIGNERS for p in judged):
    sys.exit("a waiver or judgement is signed by someone outside the approved list")
```

`solve=False` makes CI check only committed certificates and the library. The gate reads the footprint as data, so a team can write policy about premises ("no judged premise from an unapproved signer") instead of reading reports.

### Call site 2. An AI lab using the gym as a grader

```python
from lola import Library
from lola.gym import BaselineAgent, LolaEnv

library = Library("library/")
env = LolaEnv("circuit", seed=7, library=library)   # a key of lola.models.DOMAINS with a gym generator
agent = BaselineAgent(library)
for _ in range(200):
    task = env.reset()
    submission = agent.act(task)
    reward, report = env.step(submission)   # 1.0 PASS, 0.0 UNKNOWN, -1.0 FAIL
    agent.learn(task, submission, reward)   # on PASS, certify a widened family into the library
print(agent.stats())
```

`env.step` never runs a solver for the agent. It checks the agent's certificates and the shared library with the kernel. The reward is a function of the kernel verdict alone.

### Call site 3. An independent checker, the future Lean kernel's test harness

```python
import json
from lola import kernel

env = json.load(open("certs/f7e4f426.json"))
statement = kernel.decode_statement(env["statement"])
assert kernel.statement_hash(statement) == env["statement_hash"]
result = kernel.check(statement, kernel.decode_evidence(env["evidence"]))
if isinstance(result, kernel.Rejection):
    print("rejected:", result.reason)
else:
    print(type(result).__name__, sorted(result.labels))   # Theorem or Refutation, and what it rests on
```

The kernel needs nothing but the file. That is the contract a Lean port reimplements, and the mutation suite runs against it.

### Call site 4. Certify a family once, reuse it

```python
import lola
from lola.registry import build_registry

registry = build_registry()
library = lola.Library("library/")
family = lola.load_design("examples/families/cu_pvc_clipped.lola", registry)
lola.certify_family(family, registry, library)          # R4 partitions over the whole box, stored
report = lola.check_file("examples/circuit_pass.lola", library=library)
# the `hot` and `drop` obligations show source "library": an Instance of the family theorem, checked by the kernel
```

### One example per domain

The sketch ships these in `examples/`. Numbers were chosen by hand calculation to land on the stated verdict and will be re-tuned when the solvers run.

**Trusses** (`truss_pass.lola`, expected PASS. `truss_fail.lola` raises the load to 60 kN per node and expects FAIL by a collapse mechanism on the end diagonal).

```lola
lola 0

design "warren-footbridge-panel" {
  owner "a.reviewer@example.org"
  environment indoor_dry
}

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

load crowd {
  on frame.D fy in [-24 kN, -16 kN]
  on frame.E fy in [-24 kN, -16 kN]
  signed "client.structures@example.org" source "brief rev B, section 3.2"
}

claim strength:   frame.collapse_factor >= 1.5 under crowd
claim stability:  frame.stability_factor >= 3 under crowd
claim stress:     frame.member(diag_ad).stress <= 235 MPa under crowd
```

A hand calculation gives the margins. At factor 1.5 the end diagonal carries 45 kN of compression against an Euler load of about 78 kN (CHS 60.3x3.2, I = 23.5 cm4, L = 2.5 m). With the rev C load of 60 kN it needs 112.5 kN, which fails.

**Wire circuits** (`circuit_pass.lola`, expected PASS, two obligations reused from the family).

```lola
lola 0

design "workshop-lighting-radial" {
  owner "e.designer@example.org"
  environment indoor_dry
}

ambient in [10 degC, 40 degC] signed "site.manager@example.org" source "site survey 2026-09"

circuit lighting {
  supply mains voltage 230 V fault_current in [0 kA, 6 kA] signed "dno.liaison@example.org" source "DNO letter 2026-08-14"
  breaker cb1 part mcb.B10
  wire w1 cable cable.cu_pvc_2_5 length 18 m install install.clipped_direct
  terminal t1 part terminal.lever_4mm2_75C
  consumer lamps

  connect mains.out -> cb1.in
  connect cb1.out -> w1.a
  connect w1.b -> t1.wire
  connect t1.out -> lamps.in
}

load lamp_draw {
  on lighting.lamps current in [0 A, 10 A]
  signed "e.designer@example.org" source "luminaire schedule rev 3"
}

claim hot:  lighting.w1.temperature <= 70 degC under lamp_draw
claim drop: lighting.w1.voltage_drop <= 3 % under lamp_draw
```

Coverage adds short circuit (breaker let-through I2t against k^2 S^2 with k derived from copper's constants), overload protection (IEC 60364-4-43, I_B <= I_n and the wire at I_n stays below 70 degC), and the default voltage-drop limit. The `w1.b -> t1.wire` connection adds a port contract, which requires the wire's steady-temperature guarantee to sit inside the terminal's 75 degC assumption.

**Bolts** (`bolt_unknown.lola`, expected UNKNOWN).

```lola
lola 0

design "mast-bracket-coastal" {
  owner "m.engineer@example.org"
  environment marine_c5
}

joint bracket {
  bolt bolt.M12_A4_70 count 1
  plate aluminium.6061_T6 thickness 10 mm
  plate aluminium.6061_T6 thickness 10 mm
  torque in [40 Nm, 50 Nm] signed "fitter.lead@example.org" source "assembly spec AS-12 rev C"
  nut_factor in [0.16, 0.22] measured "test.lab@example.org" source "torque-tension report TT-2026-031"
  load_share in [0.10, 0.25] signed "m.engineer@example.org" source "joint diagram calc JD-7"
}

load wind {
  on bracket force in [0 kN, 12 kN]
  signed "client.structures@example.org" source "wind study WS-4, 50-year return"
}

claim tension: bracket.tension_utilisation <= 0.9 under wind
```

The tension claim is certified (worst case 29.0 kN against 0.9 x 450 MPa x 84.3 mm2 = 34.1 kN). Coverage demands `corrosion.galvanic` (A4 stainless against 6061 aluminium in a wet C5 environment) and `bolt.plate_bearing`. v0 has no model for either and no waiver names them, so the verdict is UNKNOWN and lists both with what each needs.

**Uncertain loads** (`hook_uncertain.lola`, expected PASS). The demand domain compares a demand with a capacity and knows nothing about bolts, so this example depends on no other domain's model.

```lola
lola 0

design "hoist-hook" {
  owner "m.engineer@example.org"
  environment indoor_dry
}

demand hook {
  capacity in [36 kN, 40 kN] measured "qa.lab@example.org" source "proof-load report PL-0917, minimum of 12 samples"
}

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

`overload` goes to R5. Over every distribution on [0, 40] kN with mean 10 kN, the load exceeds a capacity of at least 36 kN with probability at most 10/36 = 0.278 <= 0.3, with no distribution assumed. The dual function is h(x) = x/36. `tested` goes to R6. The claimed level equals the tested level, and 0.99^300 = 0.049 <= 0.05.

## Shape

### The data structures

Five types carry the whole design, and two registries say which rules and which domains exist. Everything else is a function between them.

1. **`kernel.Statement`** (`lola/kernel/terms.py`) is `hyps` plus one `goal`. It reads "for every value of the range hypotheses inside their ranges, and every defined hypothesis equal to the quantity it names, the goal holds." There are six goal variants, one per rule, each defined in its rule module under `lola/kernel/rules/`: `LinearFeasible` (R1), `GramPositiveDefinite` (R2), `MinimizerBound` (R3), `AllNonpositive` (R4), `MomentBound` (R5), `BinomialTail` (R6). Their fields are `Expr` trees, sparse exact `Matrix` values, and rationals. No field names a physical thing.
2. **`kernel.Hyp`** is either `RangeHyp(sym, lo, hi, label)` or `DefinedHyp(sym, definition)`. The label is an opaque string to the kernel. Outside the kernel it names a premise (`reg:`, `in:`), a scope parameter (`par:`) or a drawn design value (`dsg:`).
3. **`kernel.Evidence`** (`lola/kernel/evidence.py`) holds only what a solver chose: feasible points, an LDL factor, hypercircle fields, a split tree, dual multipliers, or a counterexample point. The body types are declared by the rule modules. Evidence never holds a matrix or an expression from the model.
4. **`kernel.Theorem` and `kernel.Refutation`** are issued, not constructed. Each is a bare handle with no fields. Its data lives in a kernel-private table keyed by the handle's identity, and `kernel.is_issued(x)` is true only for a handle `check` returned. Calling the class raises, `object.__new__` gives a handle with no record, assignment (even `object.__setattr__`) has nothing to change, and copy, deepcopy, pickle and `dataclasses.replace` raise. `tests/test_seal.py` tries each one. A theorem exposes the statement, its hash, the rule, and `labels`, the exact set of hypothesis labels it rests on.
5. **`verdict.Pass | Fail | Unknown`** (`lola/verdict.py`). `Pass` takes a `Scope`, a non-empty `Footprint` and a non-empty tuple of issued theorems whose every label resolves to a footprint premise, a scope parameter or the design itself. `Fail` takes an issued `Refutation` of the obligation's own statement. `Unknown` takes at least one `Open` item, and each `Open` names at least one typed `Need` (`lola/models/base.py`): `NeedsCertificate`, `CertificateRejected`, `CertificateTooWeak`, `NeedsInputBound`, `NoRuleForQuantity`, `NoModel` or `RegistryInconsistent`. A gym agent acts on the variant, and a report prints it.

The rule registry is `lola/kernel/rules/__init__.py`. Each rule module ends with `RULE = RuleSpec(...)`, which names its goal, evidence and lemma types, their JSON tags, and its check functions. `_REGISTERED` lists the six specs, and `RULES`, `GOAL_RULE`, `PROOF_RULE`, `REFUTATION_RULE`, `LEMMAS`, the rule part of `codec.TAGS`, and `MODULE_OF` are derived from it. The solver for a rule is the module of the same name under `lola/solvers/`.

The domain registry is `lola/models/__init__.py`. Each domain module ends with `DOMAIN = DomainSpec(...)`, which names its component kinds and their lowerers, its failure modes and their builders, its claimable quantities, its probability methods, its coverage rules, its model premises, and its feature and port hooks. `_REGISTERED` names the four v0 domains (truss, circuit, bolt, uncertainty), and `DOMAINS`, `KINDS`, `MODES`, `UNMODELLED` and `COVERAGE` are derived from it. The tuple is already filled in, so no implementer edits the file.

### How data flows

```text
.lola text  --lang.parse_design-->      ir.Design             trusted front end: names, units, signatures; generic components
ir.Design   --pipeline.lower_components--> typed models       each kind's lowerer (models.KINDS): attributes, registry ids
models      --coverage.generate-->      Requirement[]         claims plus the coverage table, minus waivers
Requirement --pipeline.elaborate-->     Obligation | Gap      the owning domain's builder: Statement plus ModelSpec
Statement   --EvidenceSource.offer-->   Evidence[]            untrusted: certs dir, library, solvers
(Statement, Evidence) --kernel.check--> Theorem | Refutation | Rejection
outcomes + PremiseBook --verdict.entries--> ClaimVerdict[]   one per claim, plus "coverage"; footprint = labels used
```

A reader traces any verdict in three files: the elaborator that built the statement, `kernel/check.py`, and `verdict.py`.

### Load-bearing decisions

1. **The statement is a pure function of the design, and evidence holds only solver choices.** The pipeline elaborates the design itself, asks sources for evidence for that exact statement, and binds stored certificates by `statement_hash`. A tampered statement in a certificate file hashes differently and is never consulted. This is the frame's "a solver never supplies the matrices", enforced by data flow rather than by a check (per boundary-discipline).
2. **Every number that comes from a premise enters as a labelled `RangeHyp`.** The footprint is then a structural function of the theorem. The kernel returns `labels`, and `PremiseBook` maps each label to a tagged premise with owner and source. `check` rejects a statement with an unused hypothesis, so the footprint lists only premises the proof used. `StatementBuilder` (`models/base.py`) has no method that turns a bare number into a hypothesis, so an elaborator cannot invent an input bound (per encode-lessons-in-structure and type-system-discipline).
3. **Lemmas live in evidence, not in statements.** A truss's stability and member-buckling checks need elastic member forces, which only a solver can bound. The statement names them as `DefinedHyp(sym, MinimizerComponent(problem, i, scale))`. The evidence proposes a range and proves it with hypercircle fields. The kernel checks the lemma, then uses the range. The rule that can prove a quantity declares it as a `Lemma` on its `RuleSpec`, and `check` finds the lemma through `rules.LEMMAS`, so a new quantity never edits `check.py`. Solver-chosen numbers never enter a statement, so decision 1 holds for statically indeterminate structures too.
4. **Force densities make truss equilibrium exact.** With rational node coordinates, the equilibrium matrix in force densities q = N/L has entries x_j - x_i. Lengths appear only as `Sqrt(L^2)` inside capacity and weight expressions, which the kernel encloses rigorously. No float and no rounding ever touch an equality the kernel checks.
5. **Each kind of uncertainty is covered by one theorem.** Loads that enter affinely (R1 right-hand sides, R3 load vectors) are covered by checking every vertex of the load box, by convexity. Material and geometry ranges are covered by interval evaluation over the whole box. A load-factor range [0, lambda] in R2 is a hypothesis inside the geometric-stiffness weights, and one Loewner lower bound plus one LDL^T covers every factor at once, so no pencil lemma is needed.
6. **Family reuse is an instance of a checked theorem.** The library is untrusted storage. A query inside a family box gets `Instance` evidence: the family statement, the family's evidence, and a renaming from family symbols to query symbols. The kernel checks the family evidence once per process and remembers the theorem by the hashes of the family statement and evidence. For each query it then checks that the query is the family statement with every symbol renamed one to one and every `RangeHyp` range narrowed. A theorem for every point of the family box holds at every point of a narrower box, so one family check serves every query, and a query costs one pass over its own statement. One kernel rule serves all six goal kinds, so a new rule needs no reuse code. The renaming must move every reference to a symbol, and `tests/test_kernel_instance.py` pins that statements name symbols only through `Sym` and the `sym` binder fields.
7. **Every model input is a hypothesis, even a point value.** A concrete 2.5 mm2 wire and the 2.5 to 16 mm2 family produce statements with the same shape and different boxes, so the library matches them by a shape hash that erases ranges and labels.
8. **Elaborators are hashed into their premises.** `ModelSpec.source_hash` is the sha256 of the elaborator module's source. Editing the physics changes the `model:` label in every footprint and every family key that depends on it.
9. **One registration per concept, and every table is derived.** A rule is one `RuleSpec` in `kernel/rules/_REGISTERED`, and a domain is one `DomainSpec` in `models/_REGISTERED`. Each `_index` refuses a registry that would make a table ambiguous: a type, tag, kind or mode claimed twice, a spec naming an untagged type, or a domain reaching a mode it does not declare. A failure mode is declared once, by the domain that owns it, and waivers name it by id. The typing aliases (`Goal`, `ProofEvidence`, `QuantityDef` and the rest) stay for readers. `tests/test_structure.py` fails when an alias and the registry disagree, `tests/test_domain_registry.py` does the same for domains, and `tests/test_solver_registry.py` for solver modules (per model-the-domain and encode-lessons-in-structure).

### Where validation lives

Validation happens at three boundaries and nowhere else (per boundary-discipline). The front end is the first. `lang.lower` checks design-level names, units, signatures, component kinds against `models.KINDS` and waiver modes against `models.MODES`, and returns a `Design` with generic components. Each domain's lowerer then checks its own attributes, local names, registry ids and qois, and raises `ComponentError`, which the CLI reports as an input error like a lowering error. `kernel.codec` decodes certificate JSON strictly, rejecting unknown keys and non-canonical rationals, so one file has one meaning. `kernel.check` checks statement well-formedness before any rule runs. Elaborators trust the IR, and rules trust the box that `check` hands them.

### Invariants carried by types

- A PASS needs issued theorems, a `Scope` and a non-empty `Footprint`, enforced by constructor checks and the kernel seal. Every theorem label must resolve.
- An UNKNOWN needs at least one open item, and an open item needs at least one typed `Need`, so an UNKNOWN never says only "unknown".
- `Discharged` and `Refuted` require the kernel result's statement to equal the obligation's statement.
- A `Footprint` holds premises sorted by label, each label once.
- An input bound cannot exist without a `Signature`, because `ir.Input` has no optional owner.
- A premise cannot carry tag `proved`, and its tag must fit its label namespace (`premises.ALLOWED_TAGS`). An owner's load range can never be tagged `sanctioned`.
- Refutation evidence names a point inside every `RangeHyp` range. Each `DefinedHyp` range is proved by its lemma at that point, and the rule shows the goal fails across those ranges, so a counterexample is always a point the premises admit with the true defined values there.
- `RangeHyp` and `DefinedHyp` are separate types, so a defined quantity cannot carry a range the statement asserted.

### What the design deliberately does not do

- The kernel never interprets a label, a unit, or a physical name.
- No part of LoLa substitutes a default input bound. A missing bound is a `Gap` needing `NeedsInputBound`. A design with no environment class is still checked: builders that need it report `NeedsInputBound`, and the galvanic rule treats an undeclared environment as wet.
- The library and the certificate directory are never trusted. The kernel checks what they offer on every use. A library family is checked once per process, and every query against it.
- `gym.LolaEnv.step` never runs a solver for the agent.
- The consistency checker can only add open items needing `RegistryInconsistent`, never remove one.

### Shared state

The only shared mutable state is the certificate directory and the library, which gym workers, CI and `certify-family` may write at once. Both name each file by the hash of the statement it proves, and both write by temporary file plus atomic rename. Two writers of one entry each write a complete, kernel-accepted file, and whichever rename lands last wins with no loss. A crash leaves no partial file, and a second run finds the entry present and writes nothing (per separate-before-serializing-shared-state and make-operations-idempotent). Readers re-check everything, so a stale or foreign file costs a rejection, never a wrong verdict. Inside one process the kernel also keeps a bounded memo of the family theorems that `Instance` evidence used, keyed by the hashes of the family statement and evidence. Only a theorem `check` has just issued for exactly those hashes enters it, so the memo saves time and changes no verdict. Everything else is a pure function of the design and the registry.

### Interface depth

`kernel.check(statement, evidence)` is one function over plain data. Behind it sit six theorems, rigorous sqrt, ln, exp and pi, vertex enumeration in a canonical order, the Loewner bound, Sylvester's law of inertia, the hypercircle identity, lemma discharge, and sealing. A caller learns the term language and nothing about how a rule checks.

`pipeline.check_design(design, registry, sources)` is the only way to get a verdict. A source is a one-method protocol (`offer`), so certificate files, the library and the solvers plug in the same way. A new source, such as a remote solver farm, is one class.

An elaborator is one function per failure mode, `(requirement, typed model, design, registry) -> tuple[Obligation | Gap, ...]`, registered on its domain's `DomainSpec`. It hides all of a domain's physics, and the rest of LoLa sees only statements.

The exposed complexity is the term language itself. An elaborator author must express physics as one of six goal shapes. That is the price of a physics-free kernel, and the alternatives section weighs it.

## Certificate JSON format

A certificate file is an envelope around two kernel terms. The statement is stored so the file can be checked on its own (call site 3). LoLa's pipeline never trusts it. It re-elaborates and looks files up by the hash of the fresh statement.

- Every term is an object with a `"t"` tag. Field keys are the dataclass field names in `kernel/terms.py`, `kernel/evidence.py` and the rule modules under `kernel/rules/`. `kernel/codec.py` lists the core tags and merges in the tags each `RuleSpec` declares.
- Rationals are strings, `"n"` or `"p/q"` reduced with q > 1. The decoder rejects decimals, exponents and floats. Counts and indices are JSON integers.
- Strings may not hold surrogate code points. Canonical text escapes a surrogate pair and the character it encodes alike, so allowing them would let two terms share a hash.
- Matrices are `{"t": "matrix", "rows": m, "cols": n, "entries": [[i, j, "p/q"], ...]}` in (i, j) order with no zeros.
- Canonical text is `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`. `statement_hash` is `"sha256:"` plus the hex digest of the canonical statement.
- Hypotheses are sorted by `sym` with no duplicates.
- An `instance` evidence body holds a family `statement`, the family's `evidence`, and a `renaming`: pairs of family symbol and query symbol, sorted by family symbol, covering every family symbol, bound ones included. Its envelope's `defined` list is empty, because the defined ranges come from the family theorem. The family evidence may not itself be an `instance`.

The example is the bolt-tension obligation from `bolt_unknown.lola`, copied verbatim from `examples/bolt_tension.cert.json` (`tests/test_docs.py` fails if the two differ). The builder names symbols by design path. The goal says T/(K d) + phi F / n - 0.9 Rp02 As <= 0 over the box, where n is the bracket's bolt count and As = (pi/4)((d2 + d3)/2)^2 is written out from the ISO 724 coefficients. The evidence is a single leaf. Every symbol with a nonzero range appears once, so the interval enclosure over the whole box equals the worst corner up to the pi enclosure. A hand check of that corner gives 26,042 N of preload plus 3,000 N of external share against 0.9 x 450 MPa x 84.27 mm^2 = 34,128 N, a margin of -5,086 N.

```json
{
  "format": "lola-cert/0",
  "kernel": "lola-kernel/0",
  "statement_hash": "sha256:9caaf82371013b4170cfbb25cde94eaa54b40ee325600116748e4ca91b55f372",
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
    "goal": {"t": "all_nonpositive", "exprs": [{"t": "add", "args": [{"t": "add", "args": [{"t": "div", "num": {"t": "sym", "name": "bracket.torque"}, "den": {"t": "mul", "args": [{"t": "sym", "name": "bracket.nut_factor"}, {"t": "sym", "name": "const.iso261.M12.d"}]}}, {"t": "div", "num": {"t": "mul", "args": [{"t": "sym", "name": "bracket.load_share"}, {"t": "sym", "name": "wind.bracket.force"}]}, "den": {"t": "sym", "name": "bracket.count"}}]}, {"t": "neg", "arg": {"t": "mul", "args": [{"t": "const", "value": "9/10"}, {"t": "mul", "args": [{"t": "sym", "name": "bolt.M12_A4_70.Rp02_min"}, {"t": "mul", "args": [{"t": "div", "num": {"t": "pi"}, "den": {"t": "const", "value": "4"}}, {"t": "pow_int", "base": {"t": "div", "num": {"t": "add", "args": [{"t": "add", "args": [{"t": "sym", "name": "const.iso261.M12.d"}, {"t": "neg", "arg": {"t": "mul", "args": [{"t": "sym", "name": "const.iso724.d2_coefficient"}, {"t": "sym", "name": "const.iso261.M12.pitch"}]}}]}, {"t": "add", "args": [{"t": "sym", "name": "const.iso261.M12.d"}, {"t": "neg", "arg": {"t": "mul", "args": [{"t": "sym", "name": "const.iso724.d3_coefficient"}, {"t": "sym", "name": "const.iso261.M12.pitch"}]}}]}]}, "den": {"t": "const", "value": "2"}}, "exponent": 2}]}]}]}}]}]}
  },
  "evidence": {"t": "evidence", "body": {"t": "enclosure", "partition": {"t": "leaf"}}, "defined": []},
  "producer": {"source": "solver:r4_enclosure", "lola": "0.1.0"}
}
```

The kernel's answer for this file is a `Theorem` whose `labels` are the ten labels above (`python -m lola verify examples/bolt_tension.cert.json`). Its footprint shows the four signed or measured inputs, the sanctioned ISO 261, ISO 724 and ISO 3506 values, `model:bolt.tension@...` and `cov:...`.

## Module map and line budget

Line counts do not include docstrings, comments or blank lines. The kernel column is measured with the counter in `tests/test_kernel_budget.py`, which enforces the kernel total against `kernel.KERNEL_LINE_BUDGET = 1500`. The other tables are estimates.

### Trusted kernel, mathematics only and standard library only (the Lean port target)

| File | Owns | Code lines |
|---|---|---|
| `lola/kernel/interval.py` | `Q`, canonical rational parsing, `Interval`, outward rounding, rigorous sqrt, ln, exp, pi | 141 |
| `lola/kernel/terms.py` | `Expr` variants, `Matrix`, `RangeHyp`, `DefinedHyp`, `Statement` | 70 |
| `lola/kernel/evidence.py` | partitions, points, `Evidence`, `DefinedRange`, `Instance` | 34 |
| `lola/kernel/codec.py` | strict JSON codec, canonical text, hashes, core tags merged with rule tags | 130 |
| `lola/kernel/evaluate.py` | `enclose`, free symbols, affine decomposition, vertex order | 123 |
| `lola/kernel/linalg.py` | exact sparse products, Gram sums, LDL^T product | 43 |
| `lola/kernel/check.py` | `check`, well-formedness, registry dispatch, lemma handling, `Instance` checks and the family memo, issued results | 236 |
| `lola/kernel/rules/base.py` | `RuleSpec`, `Lemma`, `Invalid`, `TooWeak` | 30 |
| `lola/kernel/rules/__init__.py` | `_REGISTERED`, `_index`, derived tables, typing aliases | 92 |
| `lola/kernel/rules/r1_linear.py` | goal and evidence types, vertex feasibility, Farkas | 71 |
| `lola/kernel/rules/r2_definite.py` | goal and evidence types, Loewner bound plus LDL^T, negative direction | 68 |
| `lola/kernel/rules/r3_hypercircle.py` | `QuadraticProblem`, `MinimizerComponent`, hypercircle enclosure, `prove_defined` lemma | 150 |
| `lola/kernel/rules/r4_enclosure.py` | goal and evidence types, partition walk, point witness | 64 |
| `lola/kernel/rules/r5_moment.py` | goal and evidence types, moment dual with cell-wise domination | 60 |
| `lola/kernel/rules/r6_scenario.py` | goal type, exact binomial tail | 44 |
| `lola/kernel/__init__.py` | public re-exports | 58 |
| **Total** | | **1,414** |

### Trusted outside the kernel

These files decide what a statement means. A bug here can produce a wrong verdict, so they are trusted. The elaborators also appear in every footprint they touch as `validated_model` premises. The front end, IR, premises, coverage, verdict and pipeline are trusted without being premises (an open question below).

| File | Owns | Estimate |
|---|---|---|
| `lola/models/base.py` | `FailureMode`, `ModelSpec`, `Requirement`, the `Need` variants, `Obligation`, `Gap`, coverage and port vocabulary, `DomainSpec`, `StatementBuilder` | 260 |
| `lola/models/truss.py` | truss model and lowerer, geometry, R1, R2, R3, R4 statements, coverage rules, `DOMAIN` | 380 |
| `lola/models/circuit.py` | circuit model and lowerer, series topology, heat balance, adiabatic, drop, overload statements, ports, `DOMAIN` | 380 |
| `lola/models/bolt.py` | joint model and lowerer, torque-tension and load sharing, features, coverage rules, `DOMAIN` | 170 |
| `lola/models/uncertainty.py` | demand model and lowerer, R5 and R6 builders, `DOMAIN` | 150 |
| `lola/models/contracts.py` | assume-guarantee statements over every domain's ports | 120 |
| `lola/models/__init__.py` | `_REGISTERED`, `_index`, derived tables (already complete) | 50 |
| `lola/registry/model.py` | makeable-set types, `Registry` lookups | 120 |
| `lola/registry/constants.py` | the short constants list | 250 |
| `lola/registry/catalog.py` | generators that derive every registry entry | 400 |
| `lola/registry/__init__.py` | re-exports | 0 |
| `lola/lang/lexer.py`, `syntax.py`, `parser.py`, `lower.py`, `__init__.py` | text to IR, generic component blocks | 850 |
| `lola/ir.py` | design IR with generic components | 220 |
| `lola/units.py` | exact units | 120 |
| `lola/premises.py` | tags, labels, premises, footprint, `PremiseBook` | 180 |
| `lola/coverage.py` | cross-domain rules, requirement generation, waivers | 160 |
| `lola/verdict.py` | verdict types, per-claim entries, assembly, JSON, rendering | 260 |
| `lola/pipeline.py` | `lower_components`, `elaborate`, `check_design`, `explain`, `Report`, source protocol | 220 |
| **Total** | | **about 4,500** |

### Untrusted

A bug in any of these files costs an UNKNOWN or a slow run, never a false PASS, because the kernel re-checks everything they produce.

| File | Owns | Estimate |
|---|---|---|
| `lola/solvers/__init__.py` | `SOLVERS` derived by module name, `SolverSource` | 50 |
| `lola/solvers/exact.py` | float to exact repair | 160 |
| `lola/solvers/r1_linear.py` | R1 via HiGHS, Farkas rays | 160 |
| `lola/solvers/r2_definite.py` | R2 exact LDL^T, eigenvector refutation | 120 |
| `lola/solvers/r3_hypercircle.py` | R3 fields, `DefinedRange` lemmas | 160 |
| `lola/solvers/r4_enclosure.py` | R4 branch and bound, `search` | 200 |
| `lola/solvers/r5_moment.py` | R5 dual LP and domination tree | 140 |
| `lola/solvers/r6_scenario.py` | R6 | 20 |
| `lola/certs.py` | certificate envelope, `CertStore` | 120 |
| `lola/library/store.py`, `family.py`, `__init__.py` | library, `Instance` offers, family certification | 270 |
| `lola/registry/deck.py`, `consistency.py` | decks and the physics-consistency checker | 350 |
| `lola/gym/tasks.py`, `env.py`, `agent.py`, `__init__.py` | gym and baseline agent | 450 |
| `lola/bench/family.py`, `__init__.py`, `scripts/bench_family.py` | reuse benchmark | 220 |
| `lola/cli.py`, `lola/__main__.py`, `lola/__init__.py` | shell | 220 |
| **Total** | | **about 2,800** |

## Implementation seams

The sketch is the shared-types commit. Every type in it is complete, and only bodies are missing. Once it lands, the seams below run in three waves. Each seam owns its files outright, including its tests and examples, so no two implementers touch one file (per separate-before-serializing-shared-state). A seam that needs a helper from another seam's file asks that owner and does not edit the file. `lola/models/__init__.py` belongs to no seam: its `_REGISTERED` tuple already names the four domains, and nobody edits it.

**Wave 1.** These seams need only the sketch.

| Seam | Owns |
|---|---|
| K kernel | every file under `lola/kernel/` (`interval.py`, `terms.py`, `evidence.py`, `codec.py`, `evaluate.py`, `linalg.py`, `check.py`, `__init__.py`, `rules/*`), `tests/__init__.py`, `tests/test_structure.py`, `tests/test_seal.py`, `tests/test_kernel_budget.py`, `tests/test_interval.py`, `tests/test_evaluate.py`, `tests/test_linalg.py`, `tests/test_codec.py`, `tests/test_check.py`, `tests/test_rules.py` |
| L language and units | `lola/lang/*`, `lola/ir.py`, `lola/units.py`, `tests/test_lang.py`, `tests/test_units.py` |
| G registry | `lola/registry/*` (`model.py`, `constants.py`, `catalog.py`, `deck.py`, `consistency.py`, `__init__.py`), `tests/test_registry.py`, `tests/test_registry_consistency.py` |
| P builder, premises, coverage, verdict | `lola/models/base.py`, `lola/premises.py`, `lola/coverage.py`, `lola/verdict.py`, `tests/test_domain_registry.py`, `tests/test_premises.py`, `tests/test_coverage.py`, `tests/test_verdict.py` |

**Wave 2.** These seams code against the sketch's signatures from the start and switch to running tests as K, L, G and P land.

| Seam | Owns | Needs |
|---|---|---|
| T trusses | `lola/models/truss.py`, `lola/solvers/r1_linear.py`, `lola/solvers/r2_definite.py`, `lola/solvers/r3_hypercircle.py`, `examples/truss_pass.lola`, `examples/truss_fail.lola`, `tests/test_truss.py` | K, L, G, P |
| C circuits, bolts, port contracts | `lola/models/circuit.py`, `lola/models/bolt.py`, `lola/models/contracts.py`, `lola/solvers/r4_enclosure.py`, `examples/circuit_pass.lola`, `examples/bolt_unknown.lola`, `examples/bolt_tension.cert.json`, `tests/test_circuit.py`, `tests/test_bolt.py`, `tests/test_contracts.py` | K, L, G, P |
| U uncertainty | `lola/models/uncertainty.py`, `lola/solvers/r5_moment.py`, `lola/solvers/r6_scenario.py`, `examples/hook_uncertain.lola`, `tests/test_uncertainty.py` | K, L, G, P; `r4_enclosure.search` from C for R5 domination trees (its signature is in the sketch). The example uses the demand domain only, so U never waits on the bolt model. |
| I pipeline | `lola/pipeline.py`, `lola/certs.py`, `lola/solvers/__init__.py`, `lola/solvers/exact.py`, `lola/__init__.py`, `tests/test_pipeline.py`, `tests/test_certs.py`, `tests/test_solver_registry.py` | K, L, P |
| M mutation suite | `tests/test_kernel_mutations.py`, `tests/mutations.py`, `tests/fixtures/*` | K |

**Wave 3.**

| Seam | Owns | Needs |
|---|---|---|
| F library, families, benchmark | `lola/library/*`, `lola/bench/*`, `examples/families/*`, `scripts/bench_family.py`, `tests/test_library.py`, `tests/test_bench.py` | I, C |
| Y gym and CLI | `lola/gym/*`, `lola/cli.py`, `lola/__main__.py`, `tests/test_gym.py`, `tests/test_cli.py`, `tests/test_examples.py` | I, F |

The sketch ships `tests/test_structure.py`, `tests/test_seal.py`, `tests/test_domain_registry.py`, `tests/test_solver_registry.py`, `tests/test_premises.py` and `tests/test_verdict.py`, and they pass. `tests/test_kernel_mutations.py` (M) and `tests/test_registry_consistency.py` (G) are named by `scripts/predicate.py` and are deliberately absent. A placeholder would exit 0 without running a mutation or a corruption, and the predicate would count it as verified.

The mutation suite (M) defines mutation operators per evidence type and per statement field. Each operator states why it must invalidate the certificate. The v0 operators are:

- R1. Perturb one entry of a feasible point whose column of A is nonzero, which breaks A x = b. Negate a Farkas ray, which cannot satisfy the strict inequality in both directions.
- R2. Make one LDL pivot non-positive.
- R3. Perturb one entry of a statically admissible field whose column of B is nonzero, which breaks B s = f.
- R4 and R5. Move a split point outside its cell. Zero the R5 multipliers when the failure region is non-empty.
- Refutations. Move the counterexample point outside the hypothesis box.
- Statements, R6 included. Edit one byte of a stored statement, which the hash check catches before the kernel runs.

An operator that can leave a certificate valid, such as scaling a Farkas ray by a positive constant, is not in the suite.

## Synthesis decision

**Base: candidate 1**, this design. The arena rubric chose it, and an independent cross-judge agreed: candidate 1 scored 4, 4, 2, 4, 4, 5 against candidate 2's 2, 3, 4, 4, 3, 4.

**Grafts, all from candidate 2.**

1. **Registration.** Each registry has one `_REGISTERED` tuple, and every other table is derived from it. For kernel rules, each rule module declares its goal, evidence and lemma types, their tags and its check functions in one `RuleSpec` (`lola/kernel/rules/base.py`, `lola/kernel/rules/*.py`). `GOAL_RULE`, `RULES`, `PROOF_RULE`, `REFUTATION_RULE`, `LEMMAS` and `MODULE_OF` are derived in `lola/kernel/rules/__init__.py`, the codec tags in `lola/kernel/codec.py`, and the solver table by module name in `lola/solvers/__init__.py`. For domains, `lola/models/__init__.py` names the four `DomainSpec`s, and each domain module owns its component kinds, failure modes, coverage rules and elaborators (`lola/models/base.py`, `lola/models/<domain>.py`). The typing aliases stay, checked against the registries by tests.
2. **Generic components.** An IR component is a kind, a name and typed attribute lines (`lola/ir.py`, `lola/lang/syntax.py`). The grammar and the IR know no domain.
3. **Typed needs.** A `Need` union replaces free-text needs (`lola/models/base.py`, `lola/verdict.py`): `NeedsCertificate`, `CertificateRejected`, `CertificateTooWeak`, `NeedsInputBound`, `NoRuleForQuantity` and `NoModel`, plus this design's `RegistryInconsistent`. Candidate 2's `NeedsWaiver` is folded into `NoModel`. Here both name the same state, a mode no model builds, which only a waiver or a design change closes.
4. **A demand-versus-capacity uncertainty example**, after candidate 2's hoist hook (`examples/hook_uncertain.lola`, `lola/models/uncertainty.py`). The uncertainty seam no longer depends on the bolt model.

**Fixes to this design found in review.**

- Seal laundering. `dataclasses.replace` on a theorem returned a sealed theorem. Theorems and refutations are now bare handles over a kernel-private table (`lola/kernel/check.py`), and `tests/test_seal.py` attacks them.
- Lemma proving dispatches through `rules.LEMMAS` instead of naming `r3_hypercircle` in `check.py`.
- The constructor checks in `lola/verdict.py` and `lola/premises.py` are implemented, not left as TODOs.
- `build_premise_book` has the signature its one call site uses, `(design, registry, outcomes)`.

**Rejected: candidate 2's untrusted lowering.** Its lowering writes raw numbers into models, and those numbers never reach the footprint. A wrong lowering could change a verdict with no premise naming it. The cross-judge found this soundness hole. Here the lowerers are trusted, every model number enters a statement through `StatementBuilder` as a labelled hypothesis, and the footprint is derived from the labels of the theorems used.

**Convergence.** Both candidates chose canonical rational strings in certificate JSON, certificates bound to statements by hash, untrusted libraries re-checked on every use, and verdicts that cannot be built without kernel results. They reached these independently, which is some evidence that they are right.

## Tradeoffs accepted

- We accept a trusted base of about 4,500 lines outside the kernel (front end, elaborators, registry derivations, coverage, verdict, pipeline) in exchange for a kernel of about 1,500 lines with no physics in it. The Lean port moves only the kernel. The rest stays Python and stays trusted.
- We accept that elaborators carry real physics risk in exchange for naming each one, by source hash, in every footprint it touches. A wrong heat-balance formula is visible as a premise, not hidden in a checker.
- We accept bigger statements, because every model input is a hypothesis even when it is a point value, in exchange for a structural footprint and family matching by shape.
- We accept conservative relaxations inside the rules in exchange for one simple theorem each. R1 evaluates bounds over the whole box. R2 checks a Loewner lower bound. Lemma ranges are quantified independently of each other. Each can turn a true PASS into UNKNOWN. None can produce a false PASS.
- We accept rational node coordinates in exchange for exact equilibrium. A 60-degree truss must be drawn with a rational approximation, and the verdict is about the truss as drawn. Geometric tolerances are not modelled in v0.
- We accept that a family certifies its claims only, without coverage, in exchange for families that work as reusable lemmas across designs that differ in breakers and terminals.
- We accept a coverage table that is one judged premise in exchange for saying plainly that what can go wrong is an engineering judgement.

## Alternatives considered

- **A physics-aware kernel**, closest to the frame's wording, where the kernel builds equilibrium and heat-balance equations from the IR. Its interface is as small as this one (`check(design, certificate)`), but it hides physics inside the trusted core. Every v1 rule (continuum FE, reduced basis, neural surrogates) adds physics to the kernel, the 1,500-line budget breaks within one release, and a Lean port must formalise trusses and wires. It lost because the part that must be small and portable would grow with every domain.
- **An LCF-style kernel**, with a handful of inference rules and theorems built by composing them, as in HOL Light. It is the closest match to Lean and would make lemma use first-class. It lost on size and solver burden. Solvers would have to emit proof terms, and six certificate checks plus their supporting lemmas would not fit in 1,500 lines.
- **Statements that carry solver-chosen lemma bounds**, with a separate `discharge(theorem, sym, lemma)` kernel call. It exposes one more kernel entry point and makes statements depend on solver output, which breaks binding by hash. `DefinedHyp` keeps one entry point and keeps statements a pure function of the design.
- **Footprints listed by elaborators** as a side list on each obligation. It is simpler to write, but it creates a second source of truth that an elaborator can forget to update. Deriving the footprint from hypothesis labels makes omissions impossible for numeric premises, and the unused-hypothesis rule makes padding impossible.
- **A trusted result cache** for family reuse, where the library stores "the kernel checked this" and a query does a containment check only. It is faster, but it makes the library part of the trusted base and needs signing or a ledger premise. The kernel's own per-process memo of family theorems it checked keeps the library untrusted and gives the same speed after the first query.
- **Evidence transport**, v0's first reuse design. It cut the family's evidence down to the query box, with one transport function per rule, and the kernel re-checked the result against the query. It was sound, but every query paid a full kernel check, which bounded reuse at about 1.57x even with free transport (1.31x measured on the Warren truss family). `Instance` evidence replaced it and measured 1.64x and 1.92x in two runs on the same family, with no solver call and no kernel enclosure per query.

## Open questions and risks

- Should the front end and pipeline appear in the footprint, for example as a `validated_model` premise "lola-language v0 semantics", so the footprint lists all trusted code and not only the elaborators?
- Should truss compression capacity use the EN 1993-1-1 buckling-curve reduction (a sanctioned premise) rather than the bare Euler load? Euler without an imperfection knock-down is unconservative against codes. The change is one Expr in `truss.py`.
- Should wire resistance come from resistivity over nominal area, as the frame says, or from the IEC 60228 maximum resistance, which is the value the standard guarantees? The consistency checker relates the two either way.
- Should a FAIL that rests on a point admitted only by a spec range (yield at its guaranteed minimum) be reported differently from a FAIL at an owner-signed load corner? Both are refutations relative to premises, but they read differently to an owner.
- When a claim and a coverage default address the same mode on the same subject, is "keep the stricter, keep both if incomparable" the rule the owner expects?
- Independent lemma ranges lose correlation between member forces. On highly indeterminate trusses this may give UNKNOWN for global stability. Is v0 allowed to stay determinate-first?
- The gym reward has no efficiency term because v0 has no design-limit claims. Is a pure PASS reward enough for the first baseline?
- `scripts/predicate.py` accepts only exit codes 0 and 1 from `lola check --json` and raises on anything else, but this design exits 2 for UNKNOWN, and `examples/bolt_unknown.lola` is meant to be UNKNOWN. Either the predicate accepts 2, or `check --json` exits 0 whenever it printed a report and leaves the status to the JSON. The predicate's owner decides. This commit changes neither.
- Who owns the galvanic thresholds (0.15 V for wet or C3 and above, from MIL-STD-889C), and the convection coefficient range for clipped-direct cables? Both are judged constants with a named owner in the sketch.

## Next implementation step

Start wave 1. K begins with `kernel/interval.py` and a test that encloses sqrt(2), ln(2), exp(1) and pi against 50-digit `decimal` references. L, G and P start in parallel.
