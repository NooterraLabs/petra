# Petra frontier plan

This plan takes Petra past checking code formulas. It covers the physics and the materials those formulas rest on, function as well as strength, assemblies, and the questions a design never asked. It also sets the order of that work against evidence and against the compute that is actually available. [The project plan](plan.md) still sets phases P0 to P8. This page adds the frontier track that follows them, and §6 of the plan links here.

The plan was written on 2026-11-07. Five research agents each took one lens: physics and materials, function, composition and life, coverage and intent, and generation and agents. They proposed 63 ideas, each with a mechanism, a done test and a kill condition. Two adversarial reviewers then attacked the merged draft, and most of their findings changed it (Appendix A). The agents' notes are in the project's private research folder, beside the earlier planning documents, and are not in this repository.

Every claim carries a label: **measured** (run or read while writing this plan), **inferred** (reasoned from measured facts), or **guess**.

## Summary

1. **A verdict is only as good as four things.** These are the inference, the premises, the questions asked, and the translation from intent and design into maths. The kernel makes the inference strong. Every false PASS found so far came from the other three (plan §1, measured).
2. **The pilots changed the bet.** Agents without Petra made 10 safe designs out of 10 standard steel connections (P3, measured). On P8's mesh, AISC's block shear formula sits above a plastic lower bound at yield on almost every plate it tried (measured). So "agents make unsafe designs" is unproven, and code formulas rest partly on tests, not on proofs.
3. **The keystone experiment is honesty under optimisation.** An optimiser pushes against three graders: Petra, an LLM judge, and a floating-point finite element model. Judges that share nothing with Petra then grade the winners. Every other program matters more if Petra stays honest there.
4. **"Unsafe" must be defined before anything is measured.** Code compliance and physical failure are different truths, and Petra's current judges are not independent of Petra (§3).
5. **The first build work is oracles that are not Petra.** These are a clean-room twin of the steel deck, metamorphic relations, and table-based differential tests. They address the weakest measured number. If one of Petra's own checks went missing, today's judges and breaker would expose the gap in only 22 of 199 cases, because the judges have no condition of their own for those modes (`docs/canary_recall.md`, measured).
6. **Petra's own false FAILs cost users now.** It rejected 3 of 10 safe designs in P3 (measured). That alone meets the decision table's false-FAIL row (§4, computed). Fixing those comes before new physics.
7. **Compute credits end on 2026-11-15** (plan §6). The token-heavy experiments run before then, and so do the keystone experiment's LLM arms. The CPU-heavy work (CalculiX, kernel rules) runs after (§4).
8. **The kernel stays frozen until evidence asks for a rule.** It is at 1,414 of its 1,500 budgeted code lines (measured). Each new rule must first state its soundness conditions, then ship a mutation corpus and a check against an outside checker (§7).
9. **Each new design class ships its own judge, canaries and breaker first,** one class at a time. That is the plan's coverage rule (plan §4), applied to function, contracts and dynamics.
10. **Some things stay out of reach.** Fracture with no declared flaw, rigid impact with friction, and complete knowledge of failure modes stay out of reach (§8). Petra answers UNKNOWN there, with what is missing.

## 1. What a verdict rests on

A verdict combines four factors, and the weakest one sets its trust.

| Factor | What can go wrong | State on 2026-11-07 |
|---|---|---|
| Inference | The certificate does not prove the statement | Six exact-rational rules. No false PASS traced to them (measured, plan §1). |
| Premises | A code formula, registry value or model is wrong for the case | P8 showed that J4.3 rests on rupture tests (measured). The registry values are versioned, with an errata field (measured). |
| Questions | No obligation exists for the failure that happens | Coverage fires a check only when a rule matches, so leaving out a load removes checks (plan P1 item 5, measured). With one of Petra's modes removed, the judges and breaker expose the hole in 22 of 199 cases (`docs/canary_recall.md`, measured). So the outside oracles rarely notice a missing strength check. |
| Translation | The card or the model says something other than what was meant | Before P1 there were 1,711 absurd PASSes in 15,600 designs, all from elaboration (measured). |

The frontier work raises the premises, the questions and the translation toward the kernel's standard. It then extends the inference from strength to function, assemblies and time.

## 2. What P3 and P8 changed

**P3, the lift pilot.** Ten steel connection tasks each went to two fresh agents, one with Petra and one without. Both arms made 10 of 10 safe and buildable designs (measured, pilot report on its branch).
- With Petra, the designs used 13% less steel in total (154.9 lb against 178.2 lb).
- The agents with Petra took a median of 21.7 minutes and 26 tool calls. Without it, they took 11.7 minutes and 16.5 tool calls.
- Petra refused 3 of the 10 safe designs made without it. Two were eccentric groups, where Petra uses the elastic method and not the instantaneous centre. The third was a one-row seat with no spacing rule.
- Zero unsafe designs in 10 bounds the unaided unsafe rate only below 25.9% at 95% confidence (computed). So the pilot cannot tell "agents never fail" from "agents fail one time in five".

**P8, the block shear pilot.** The pilot built lower-bound stress fields for 144 plates and had the kernel check four of them (measured, pilot report on its branch).
- On its mesh, J4.3's nominal strength exceeds the plastic lower bound at yield at 142 of 144 plates.
- A refutation from the kernel refutes the claim on that mesh only. A finer mesh raises the bound.
- A hand argument shows that J4.3 exceeds the plane-stress bearing limit at yield at 112 of 144 plates on any mesh. The kernel does not check that argument.
- J4.3 is fitted to rupture tests, and real plates beat plane-stress plasticity through confinement and strain hardening (Commentary J4.3, read by the pilot).
- Research on coped beams may point the other way. A search summary seen by a reviewer says Kulak and Grondin (2001) found the block shear rules unconservative for coped beams (not verified against the paper). P8's one-column plates are coped-beam geometry, so its one-column rows may hold a real erratum. Section 4 runs that check first.

**Corrections to earlier claims in this project's conversation:**
- "Physics checks any geometry and replaces the codes" is wrong. A physics floor at yield is sound but loose, and the codes are tight because they rest on tests. Physics underwrites the codes and covers designs no code reaches.
- "Code safety factors become derivable" overreaches. A failure probability far in the tail always rests on a declared tail shape. Swapping the tail family at equal moments moves a reliability index of 4.5 to anywhere from 3.76 to 5.85 (computed by a reviewer and not re-run here). Data alone needs about 300,000 failure-free trials to show a failure probability of 1e-5 at 95% confidence (computed).
- The Comet and Challenger were not simply checks nobody wrote.
  - The Comet's fatigue test ran on a fuselage section that had first been proof-loaded, which lengthened its test life (secondary sources, read by a research agent).
  - Challenger launched at 36 °F with no launch rule for booster temperature. No earlier flight had been colder than 53 °F (read by a research agent).
  - Of nine famous failures studied, fewer than half are a missing failure mode. The rest are missing environments, changes that never reached the analysis, single points of failure, and premises inside the evidence (inferred).

## 3. Rules every frontier program follows

These rules come from the reviews. Each one names a failure the first draft had.

1. **Define truth for each limit state before measuring.** Code compliance and physical failure differ by design. In P3, CalculiX flagged a code-compliant end plate in both arms. Its model holes stretch 0.25 in at about 1.4 d t Fu, where J3.11a allows 2.4 d t Fu (measured). The pilot reads this as a flag that may say more about the model's bearing than about the design (inferred). Each experiment names one outcome per hypothesis and the judge for it. Where code and physics disagree, that is reported as its own result, never as a false PASS.
2. **Name what each judge shares with Petra.** The fit and strength judges import `petra.ir` and `petra.registry` (measured). So a wrong registry value is wrong in both, and they are not outside judges for registry errors. Each judge is labelled by what it shares: the registry, Petra's design representation (`petra.ir`), or the model family that wrote it. The clean-room twin (§4) imports neither module, so it is outside for registry errors, but it shares the model family.
3. **Do not count the same model family as independent.** This project's agents all run on one model family (plan Appendix C). A done test that needs "two model families" is labelled single-family and weaker, unless a second family is configured. Non-model oracles come first wherever they exist.
4. **Each new design class ships its judge, canaries and breaker before it ships a PASS.** That is the plan's coverage rule (plan §4). It applies to function, contracts, dynamics and assemblies, one class at a time.
5. **Write a kernel rule's soundness conditions before writing the rule.** The reviews found three proposed proof shapes that accept a trivial or one-sided certificate (§6).
6. **Run any lift test with at least 25 tasks per arm, and size it from a replicated rate.** Ten tasks bound nothing useful.
7. **Keep an elaboration trust budget.** The kernel has a line budget, but elaboration, where every false PASS lived, has none. Each new elaborator states its size and passes a twin-elaborator check before release.

## 4. Order of work

### Before credits end on 2026-11-15

These runs need tokens more than CPU, so they go first. The plan gave the last credits to the canary campaign and the P1 breaker runs (plan §8 item 6). P1 has closed, so these runs use what remains (inferred).

| Run | What it measures | Truth and judge | Size |
|---|---|---|---|
| Unaided failure-regime search | Where frontier agents without Petra call unsafe designs safe. Regimes: optimisation pressure (mass scored, silent zero for FAIL), multi-part bays, off-table geometry, long task lists. | Code compliance, judged by hand checks the pilot protocol samples. Single-family, so labelled weaker. | Successive halving over generator cells, then fresh seeds to replicate. The model stays fixed at the frontier user's model. |
| Missing-obligation tasks, unaided arm only | Whether agents name and check a decisive obligation the brief does not mention | The planted obligation, built from synthetic mechanisms of strength and of function, not from famous cases, which the models already know | 25 tasks |
| Clean-room twin of the steel deck | A second implementation of the steel limit states, written from the AISC specification by agents with no access to Petra's code | Disagreement with Petra on the 10,000-design gate stream. Labelled single-family (§3 rule 2). The AISC specification is licensed, so the twin reads it in place and encodes methods with clause citations, never its text. | One deck |
| Grader-honesty setup | Task sets and pre-registration for the keystone experiment below | | Protocol only |
| Keystone LLM arms | The LLM-judge reward and the LLM design loop, in the trusses and frames arena | Closed forms now. Converged CalculiX runs on CPU after the credits end. | As the protocol sets. If it is not ready in time, the keystone runs CMA-ES alone and reports the LLM arms as not run. |

### The keystone experiment: honesty under optimisation (LLM arms first, the rest in weeks 1 to 4)

The same optimisers minimise mass under each of three rewards: Petra, an LLM judge, and floating-point finite elements at a fixed mesh. Two optimiser families run, CMA-ES and an LLM design loop. Judges that never serve as a reward then grade the optimised designs as the optimisation budget grows.

It runs in two arenas, so that truth does not depend on AISC's rupture calibration:
- **Trusses and frames.** Truth is a closed form or a converged nonlinear CalculiX run, which the reward FEM never uses.
- **Steel connections.** Truth is code compliance, judged by the clean-room twin (single-family) and by metamorphic relations. Each check takes 0.07 s here (plan §1, measured), so certified rewards are affordable. The 2D plate rung is not used, because one kernel proof there takes about 15 minutes (measured in P8).

| Outcome | What follows |
|---|---|
| A judge confirms a Petra false PASS | Stop the frontier work and fix it, as P1 did |
| Petra has no false PASS, and another grader's false-PASS rate has a 95% lower bound above 10% (threshold a guess) | Publish the curves. The certified-gap benchmark (F7) moves first. |
| Every grader's false-PASS rate stays under 2% at the top budget (threshold a guess) | Honesty does not set Petra apart in that arena. Move to the arena where the float model is known to be weak, deflection and collapse of continua, once F6 makes it affordable. |

### The decision table

Every rate below is a one-sided 95% lower bound, so a row fires on evidence and not on noise. The thresholds themselves are guesses. The false-FAIL rate is measured over every design the pilots and the regime search grade safe by hand checks.

| Result | Programs that move first | Programs that wait or die |
|---|---|---|
| A regime's replicated unaided failure rate is at least 15%. At 25 tasks that takes 8 failures (computed). | A powered lift test there (25 to 40 tasks per arm), then the matching program: F1 for missing obligations, F4 for multi-part bays | Programs aimed at other regimes |
| Unaided agents miss the decisive obligation in at least 30% of tasks, 12 of 25 (computed) | F1 closed-world coverage | |
| Most obligations the unaided arm misses are function claims, such as jamming, slip or settling | F3, with its first class and judge | |
| Every unaided arm stays null | Agent-safety lift is not Petra's lead. Value comes from certification, mass and training reward: F7, the keystone curves and F2 lead. | Lift-based claims leave the public docs. F1 continues as soundness work, not as lift. |
| No row above selects a design class | The first new class is frames, through K-C. Frames serve buckling, vibration and F4's frequency contracts, and the keystone's truss arena already builds their judge (guess). | F3 waits for a row or a user |
| Petra's false-FAIL rate on safe designs is above 5% | False-FAIL fixes come before everything. P3 already fires this row, at 3 of 10, a lower bound of 8.7% (computed). | |

### The 12-week core (after 2026-11-15)

| Week | Item | Done when | Killed when |
|---|---|---|---|
| 1 | **False-FAIL fixes.** The instantaneous-centre method for eccentric bolt and weld groups, and the one-row seat spacing rule. J10.8 and J10.9 credit, open since P1 (plan §6) and not seen in P3, joins only if a measured false FAIL needs it. | The 3 P3 rejections pass, the steel gate still has 0 false PASS, and the false-FAIL rate on the safe-design set above falls | A fix creates a false PASS the clean-room twin finds |
| 1 | **P8's one-column rows against coped-beam tests.** Compare J4.3 and the lower bound with published coped-beam block shear tests. | A table of test over J4.3 and test over the lower bound for every extracted specimen, with extraction labelled single-family | Fewer than 20 specimens can be extracted |
| 1 to 2 | **Metamorphic oracles.** Capacity must not fall as thickness, bolt count or Fy rises, and verdicts must not change under a change of units or a mirror image. | The relations run over the gate stream in CI, and each seeded inversion is caught | |
| 2 | **Lockfile and `petra audit`.** Every verdict pins the registry entries it used. An erratum re-checks the affected verdicts and labels each one unchanged, weakened or flipped. | Re-issued as an advisory, the cable-resistance erratum reproduces the table in `docs/registry.md` row by row | |
| 2 to 3 | **Repair intervals over all obligations.** A FAIL reports the input range that passes every check at once, as a union of intervals where needed. | One-try repair on held-out briefs, and no reported interval contains a failing point | Agents ignore the interval in transcripts |
| 3 to 5 | **Closed-world coverage on steel.** Each cell of subject, mode, phase and environment holds an obligation, a proved exclusion, a judged exclusion or a waiver, with no catch-all. Exclusions that are inequalities become theorems. | Deleting any one exclusion makes some gate design UNKNOWN that names the cell, and at least 90% of generated designs still get a decided verdict | Text-only exclusions fill more than half the cells |
| 5 to 8 | **The certified-gap benchmark (F7).** Score is a certified lower bound on minimum mass divided by the design's mass. Tasks carry dated seeds. | A 100-task steel tier ships kernel-checked bounds | Bounds sit under half the best known mass on most tasks |
| 8 to 12 | **The first new design class chosen by the decision table.** It ships with its judge, canaries and breaker. | It meets the coverage rule | Its breaker cannot reach 90% canary recall in two rounds |

### Parked, with the reason

- **A public transparency log of verdicts.** No user cites a foreign contract yet, so its own kill condition already applies.
- **As-built data and certified inspection dates.** These need measured data from real parts.
- **Controller code and monitors, and Taylor-model flowpipes.** They wait for a validated dynamics class.
- **Neural proposers.** They wait until the physics rung has users.
- **A function reward for text-to-CAD.** The expected result is predictable without the work.
- **Mining an ontology of failures from investigation records.** The language models already know those records, so the recall it reports would measure memory. It returns only with records dated after the model's training cutoff, or with synthetic planted mechanisms.
- **A Boolean proof checker for cut sets.** Order-1 cut sets are a linear enumeration, and structural collapse is a linear program.
- **Exact failure probabilities.** The reviewer's calculation shows the declared tail decides the answer. They return as tail-sensitivity reports.
- **Gap tests for function and assemblies.** Planted thin-region faults, and parts that pass alone but fail together, need a function or assembly class that Petra does not have yet. So they cannot measure lift now. They return with the first class the decision table selects.
- **A premise concentration index.** It would measure whether optimisation drifts onto the weakest premises. It needs the premise ladder (F2) to rank premises first.

## 5. The verdict this builds toward

A user or agent runs one command and gets six things:
- **The verdict.**
- **What it proved.** The rung of the premise ladder it reached, from plasticity at yield up to "tests only".
- **What it assumed.** A lockfile of premises.
- **What it asked.** A cell map against a named version of the failure ontology, with recall reported separately for fit faults and strength faults.
- **What would change it.** A certified repair interval.
- **What it could not decide.** Typed UNKNOWNs that name the missing input, printed like Lean's open goals.

## 6. The programs

Each program lists its strongest ideas, the soundness conditions the reviews added, and where it waits on the decision table.

### F1. Closed-world coverage

- The cell map, with four constructors and no catch-all (week 3 above).
- Obligations derived from a typed graph of energy stores, flows and environment agents. The aim is that a wind agent on a slender span demands an aeroelastic check that nobody wrote by hand.
- Typed environments and life phases, from fabrication through transport, erection, service and maintenance.
- Removal of each load-bearing element, with a linear program per case, to find members with no alternate path.
- Vacuity and teeth checks. A claim that no member of its family can fail is flagged, and so is a card no design can meet.
- Read-back by semantic diff. Two formalisations of the same intent are compared, and the kernel finds a design they judge differently. The owner answers that one concrete question.

**Conditions added by the reviews.**
- Applicability must not become a new catch-all. A floor on the share of decided verdicts and a cap on how many values a designer must declare keep it honest.
- Exclusions proved over a declared load box still depend on the declared loads, and the verdict says so.

### F2. The premise ladder

Each code clause records which premises the kernel needs to prove it. The premises include plane stress at yield, shear at 0.6 Fy, confinement at contacts, and flow stress raised toward Fu. The weakest set that works is the clause's place on the ladder.

**Conditions added by the reviews.**
- The premises form a partial order, not a chain. Confinement and hardening are independent, so the result is a set of minimal premise pairs (P8's first plate needs 1.27 Fu with bearing contact and 1.19 Fu with confined contact, measured).
- A refutation on a mesh does not set a boundary. A boundary needs a kernel-checked collapse mechanism, an upper bound, at the weaker premise set. Otherwise the result reads "proved at this set, open below".
- An erratum needs test evidence below the target reliability. Landing on "tests only" is not an erratum.
- Calibrating test load over the physics floor must be validated leaving out one test series and one mechanism at a time. A pooled scatter figure says nothing about untested geometry.

**Done when** every steel clause in the registry records a minimal premise set the kernel proved, or reads "proved at this set, open below" with its mesh. **Killed when** fewer than a quarter of the steel clauses reach any rung below "tests only" (threshold a guess), since then the ladder adds a label and no information.

### F3. Function

The ideas that hold up:
- grip, no-jam and self-locking as linear-programming certificates;
- pump and heat-sink claims on measured monotone curves;
- kinematic mobility and singularity-free workspaces;
- swept collision by separating planes;
- loop margins in electronics.

The polynomial certificate rule (K-A) opens most of them.

**Conditions added by the reviews.**
- **Settling and decay shapes need positive definiteness.** "V̇ ≤ −2αV" and "AᵀP + PA + 2αP ≤ 0" accept V = 0 and P = 0. Each shape must carry V ≻ 0 or P ≻ 0 as a kernel-built obligation.
- **No-jam and self-locking over a range need a new goal.** R1 proves "for every h, a feasible x exists", and its refutation is a single point. "For every h, no x exists" needs its own goal: one ray whose bound holds over the whole box.
- **A FAIL needs the outer friction pyramid.** A Farkas ray against the inscribed pyramid refutes only the approximation.
- **A Krawczyk path needs gluing.** The solution at each junction must lie in both boxes, or the path can jump between branches.
- **Rounding sum-of-squares certificates must be tested on hard cases.** Equilibria and contacts give singular Gram matrices, where rounding needs facial reduction. The kill test runs on those cases, not on strictly feasible ones.

F3 waits until the decision table selects function, and its first class ships with a judge.

**Done when** the first function class meets the coverage rule, and its certificates reject every wrong certificate in a mutation corpus that includes refutations against the inscribed friction pyramid. **Killed when** the decision table never selects function, or K-A's rounding fails on the singular-Gram kill set.

### F4. Assemblies and contracts

The ideas that hold up:
- ports typed by conjugate pairs: force and motion, voltage and current, temperature and heat flow;
- a closure certificate for each cycle where parts heat or load each other;
- refinement checks for drop-in parts;
- a contract quotient that hands each subagent the weakest contract its part must meet;
- interaction obligations from the contact graph;
- incremental re-checking after an edit.

**Conditions added by the reviews.**
- **Stiffness contracts must not bound frequency from the unsafe side.** Condensing a part to its port stiffness is a Rayleigh-Ritz projection, so it can miss an internal mode. Each contract also certifies that the part has no fixed-interface mode below the band (a Wittrick-Williams count, K-C), plus a dynamic stiffness bound across the band.
- **Cycle closure needs its side conditions checked.** Monotone comparison needs the coupling signs checked as obligations, and small gain needs a box shown to be invariant.
- **Most steel connections are governed by rupture,** so the plastic linker rarely applies. The composition-gap measurement counts how many real assemblies are indeterminate with ductile ports before any linker is built.

**Done when** the composition-gap measurement is published and, if it finds assemblies whose parts pass alone but fail together, the first contract class checks one such assembly with its fixed-interface mode count. **Killed when** that measurement finds no such assembly in the gate stream or the regime search.

### F5. Life

The lockfile and `petra audit` are in the core (week 2). The rest is parked (§4).

### F6. Speed

The measured limit on agent time is the agent, not the check. A check takes a median of 53 ms and a p95 of 92 ms in process (measured by a research agent). The P3 agents spent twice as long with Petra. So speed work targets the 15-minute proof of a 2D plate, which blocks the physics rung. The plan for that proof:
- Stress fields that are equilibrated by construction.
- A cached null-space lemma per mesh.
- A pointwise yield check.
- Region certificates over geometry boxes, which close the gaps between grid points. These are a soundness gain as well as a speed gain.

The null-space lemma and the pointwise yield check are kernel rules, so they wait like any rule (K-D in §7). Floating-point filters stay in the untrusted producer and never enter the kernel. For training throughput, checks run in parallel processes.

**Done when** the four P8 plates the kernel checked get the same verdicts at least 10 times faster (target a guess). **Killed when** the speed-up stays under 3 times (threshold a guess), since then the physics rung stays out of reach of any optimisation loop.

### F7. Generation

- **The certified-gap benchmark** (core, weeks 5 to 8). For trusses, the gap is certified only if the lower bound holds over the whole domain, not only the chosen node set. Otherwise the reported gap can go negative.
- **Synthesis that is certification.** A feasible point of the plastic layout program is both a design and its R1 certificate. Counterexample-guided synthesis handles tolerance boxes, with each R4 refutation adding a point.
- **Self-play.** A conjecturer proposes tasks the designer barely solves, a breaker hunts PASSes a judge fails, and an auditor proposes "this clause never exceeds this bound". Each break becomes a canary, an obligation or an erratum.
- **A deck factory.** Agents formalise a code chapter, and only versions that pass the full P1 gate ship. Its done test is a chapter, such as AISC Chapter D, with no model code written by hand.

## 7. The kernel

**The budget.** The kernel holds 1,414 code lines against a budget of 1,500 (measured with the counter in `tests/test_kernel_budget.py`). The earlier compiler notes set a ceiling of "under 2,000 lines, in two languages". So every line also costs one in the planned Lean port.

**The policy.**
- No rule is added before a validated program needs it.
- No checking step moves out of the kernel to save lines.
- Floating-point arithmetic never enters the kernel.
- Each rule first writes its soundness conditions. It then ships with a corpus of wrong certificates that it must reject, and with a check against an outside checker: Lean's `sos` certificate format for K-A, a KeYmaera X export for K-B.

| Group | What it checks | Serves | Lines (guess) |
|---|---|---|---|
| K-A | Polynomial identities, and positivity from rational Gram matrices with LDLᵀ factors | F3 contact over tolerances, collision, stability, margins. F4 nonlinear passivity. F6 region certificates. | about 150 to 200 |
| K-B | Dynamics obligations that the kernel itself builds: barrier, ranking and Lyapunov conditions with every side condition, plus box invariance | F3 dynamics, F4 cycle closure | about 160 |
| K-C | Interval linear algebra: eigenvalue counts (Wittrick-Williams) and Krawczyk existence | Frame buckling and vibration, F4 frequency contracts, kinematic paths | about 140 |
| K-D | A cached null-space lemma per mesh, and a pointwise yield rule | F6 plate proofs | about 120 |
| K-E | Exact integration of quadratic forms on simplices, for continuum stiffness bounds | Deflection claims, fracture mechanics | about 200 |
| ∀-infeasible | One Farkas ray valid over a whole parameter box | F3 no-jam and self-locking | about 40 |

The table sums to about 810 to 860 lines. All of it would take the kernel to about 2,250 lines, past the 2,000 ceiling (computed from the guesses). So the ceiling admits only some of these rules, and evidence picks which.

Removed from the first draft:
- **K-D's float path.** It moves to the producer.
- **K-G, a finite cover for coverage maps.** It stays in `verdict.py`, outside the kernel.
- **K-F, enclosed special functions.** Exact failure probabilities are parked.
- **K-H, the Boolean proof checker.** It is not needed.
- **K-I, Taylor-model flowpipes.** They are parked.

**The maintainer's decision.** Raising the ceiling is the maintainer's call, and so is each rule. The likely first candidates are K-C (frames and frequency contracts) and the ∀-infeasible goal, at about 180 lines together. That keeps the kernel under 1,600 lines (inferred).

## 8. What stays out of reach

Petra answers UNKNOWN on each of these and names what is missing.

| Limit | Status | What Petra can still do |
|---|---|---|
| Fracture with no declared flaw | Impossible from physics alone. Onset is a measured, statistical premise. | Bound the fracture mechanics for a declared flaw |
| Rigid impact with friction | No unique solution in the rigid model (Painlevé) | Compliant models over bounded stiffness, which is research |
| Chaotic long horizons | Impossible in practice | Statistical claims |
| Complete failure-mode coverage | Not a well-posed decision problem | Completeness relative to a named ontology version, with recall measured on held-out cases |
| Ground truth for materials | Needs tests. Agents can curate published data, but no compute replaces the original test. | Versioned datasets with provenance |
| Far-tail failure probability | Rests on a declared tail shape | Report how much the answer moves when the tail changes |

## 9. Decisions only the maintainer can make

1. **The kernel ceiling,** and each new rule. The recommendation is 2,000 code lines, with K-C and the ∀-infeasible goal first.
2. **Whether to configure a second model family** for twin formalisation and outside checks. If not, those checks stay labelled single-family.
3. **The definition of truth for each limit state** in the keystone experiment, before it runs.
4. **Whether the P8 one-column result, if the coped-beam check confirms it, goes public as an erratum.**

## Appendix A. How this plan was made

**Five lenses.** Five agents worked from one shared brief. Each wrote 10 to 14 ideas with a mechanism, kernel impact, prior art (marked read or recalled), a done test, a kill condition and a cost guess. All five ran on the same model family as the author.

**Two reviewers.** Both ran on the same model family too, so the panel had no model diversity. Findings that both raised carry the most weight.

**Raised by both reviewers, and acted on:**
- "Unsafe" had no definition, and the judges share Petra's registry and parser.
- Same-family checks were treated as independent.
- The draft ignored the credit cliff and was several times over scope.
- The frequency contract bounds from the unsafe side.
- The first kernel wave came before any evidence and went over the ceiling.
- The atlas could not measure lift before the capabilities existed, and had no decision table or null branch.
- New design classes skipped the coverage rule.
- Recall mined from famous failures measures what the model already knows.
- The life program came before generation, against the rule to rank by use.
- The draft wrongly claimed that every lens put measurement first.

**Raised by one reviewer, and acted on:**
- Settling shapes accept a zero certificate.
- No-jam needs a new goal, and the friction polarity was wrong.
- Petra's false FAILs were missing from the plan.
- P8's coped-beam geometry may hide a real erratum.
- The calibration done test measured pooled scatter, not transfer.
- The reliability-index program fails its own kill condition.
- Metamorphic and table oracles, a clean-room twin, and an elaboration budget were missing.
- Mesh refutations were read as boundaries.
- The premise ladder is a partial order.
- Repair intervals from the governing check alone can be false.
- The latency target was below the floor Amdahl's law allows.

**A third reviewer** ran on a different model of the same family and checked the plan against its sources. Acted on:
- The decision table's rates became 95% lower bounds, and its thresholds are labelled guesses.
- F2, F3, F4 and F6 gained done tests and kill conditions.
- Dropped items are now listed: the function and assembly gap tests, the premise concentration index, and K-G.
- The keystone's LLM arms moved before the credits end.
- The clean-room twin is labelled by what it shares.
- J10.8 and J10.9 are marked as open since P1, not found in P3.
- The kernel table's total is stated.
- Claims labelled measured were narrowed to what their sources say, such as the end-plate flag and the 22 of 199 recall.

**Considered and kept:**
- The keystone experiment as the lead result.
- Coverage as soundness work even if agents turn out not to need it.

## Appendix B. Sources

The research agents and reviewers marked each source as read (fetched that day), read as a summary only, or recalled. This list keeps sources read in full that bear on a decision above.

- Cai and Driver, "Prediction of Bolted Connection Capacity for Block Shear Failures along Atypical Paths", AISC Engineering Journal, 2010, Table 6: https://ej.aisc.org/index.php/engj/article/view/994
- Gao, Schulman and Hilton, "Scaling Laws for Reward Model Overoptimization", 2022. Read by a research agent.
- Leveson and Thomas, STPA Handbook, 2018, pp. 36 to 38: https://psas.scripts.mit.edu/home/get_file.php?name=STPA_handbook.pdf
- Benveniste et al., Inria research report RR-8759, 2015, on contract-based design. Read by a research agent.
- Peyrl and Parrilo, on rounding sum-of-squares certificates to rationals, 2008. Read by a research agent.
- The P3 and P8 pilot reports, and `docs/calculix_check.md`, on their branches as of 2026-11-07.
