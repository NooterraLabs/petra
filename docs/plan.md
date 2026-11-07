# Petra: what we make, cover, conquer and build

Written 2026-11-06, revised the same day after two adversarial reviews. This plan sets one order of work. ENGINE_MAP picks drones first and BRAINSTORM picks electronics. NICHE §14.4 picks steel connections, with lifting as the designer's first product. This plan keeps NICHE's first pick, moves lifting later, and makes connections the designer's first product too. Every claim carries a label: **measured** (run or read this session), **inferred** (reasoned from measured facts), or **guess**.

## The answer

1. **We make a compiler for physical designs.** A signed requirements card and a design go in. A verdict anyone can re-check comes out, then the build files: PASS, FAIL with a counterexample, or UNKNOWN naming what is missing.
2. **It has three parts.** The open checker (Petra), a benchmark and training environment (Petra Bench), and a designer that writes Petra and emits CAD.
3. **Today no stranger can use Petra, and it is not yet safe.** It has no package file, licence, public repository or language reference (measured). A fresh agent and a reviewer found false PASSes in one afternoon. They fall into three kinds: parts that do not fit, a conductor that does not fit its terminal, and a truss with no self-weight. A cable resistance also leans the unsafe way (§1).
4. **Every false PASS sits in the layer that turns a design into maths.** None sits in the kernel. Our gate reported zero false PASS because it checks Petra against itself (inferred from §1).
5. **So the first real work is a geometry judge and a measured breaker, not more physics.** Packaging runs alongside it. Publishing waits for both.
6. **The first users are AI agents,** then labs, then engineers. Whether agents really come first is measured after publishing, with a dated check (§3).
7. **We cover one design class completely before the next,** and coverage grows by rule family, not by niche (§4).
8. **We win with engines that grow with compute.** Breakers, an optimiser that hunts for false PASSes, a task generator, and self-play. The install path and the certificate format grow with adoption, and we measure that honestly (§5).
9. **CAD is an output first.** Reading other tools' files comes later, one reader per kind of data (§6, P6).
10. **Build order.** P0 usable, P1 safe, then publish. P2 in the loop, P3 benchmark, P4 designer, P5 coverage, P6 readers, P7 trust (§6).

## 1. Where we stand, measured

### The journey of a new user today

The first rows come from my own checks. The rest come from a cold-start test. A fresh agent with no context and no network was told to install Petra and do five jobs (Appendix A).

| Step | What a newcomer needs | State today | Label |
|---|---|---|---|
| Find it | A public repository or package page | No git remote | measured |
| Trust the licence | A licence file | None | measured |
| Install | `pip install petra` | No `pyproject.toml` (`ls` fails, measured). The name `petra` is free on PyPI (measured). The cold-start agent reports that pip printed "Neither 'setup.py' nor 'pyproject.toml' found", and that it needed a hand-made `.pth` file and wrapper scripts, about 8 tool calls. | measured, partly by the agent |
| Get the real product | One trunk | `master` is 16 commits behind `daedalus/mechanics-layer` (15 before this plan's own commit). It is a fast-forward, since `validity-obligations` is already inside it. | measured |
| Read what the code cites | Every cited doc in git | `docs/principles.md` is cited by the steel code and tests but untracked | measured |
| Find the steel deck | A README pointer | The README never mentions it. The agent found `examples/steel` with `ls`. | measured |
| Learn the language | A reference and templates | None. The agent copied an example's 13 lines and learned field names from error messages, which were clear. | measured |
| Name parts | A way to list the registry | None. "A325 is not a registry material", with no suggestion. The agent grepped a 305 KB deck JSON. | reported by the agent |
| Use any beam | The full shapes table | 30 W shapes and 16 angles ship. W8x31 is "not a W shape in the shape table". The full table needs the AISC spreadsheet locally. | measured by reviewer A |
| Run a check | A `petra` command | Works. 1.8 s from the command line, of which 0.07 s is the check and the rest is import. | measured |
| Read results in code | A documented API and full JSON | `petra.check_file` works (measured). Per-claim access is undocumented, and `--json` printed `"obligations": []` and no counterexample (reported by the agent, reproduced by reviewer A). | measured, partly |
| Fix a FAIL | Demand, capacity, the input to change | None of these. Counterexamples print as SI rationals, some without units. The agent repaired the design in three hand-computed tries. | reported by the agent |
| Train against it | An environment in a hub format | `petra gym` has its own `step(Submission)` API, in no hub format, with generators for circuits and bolts only | measured |

### What the checker can prove today

| Area | Today | Label |
|---|---|---|
| Kernel | 6 rule families, exact rationals, 2,615 lines | measured |
| Trusted elaboration | Models, language, coverage, registry and pipeline, about 15,000 lines. Every false PASS below is here. | measured by reviewer A |
| Domains | 2D trusses, one cable's heating and voltage drop, bolted joints, probability bounds, 11 AISC steel connection kinds | measured |
| Steel gate | 10,000 of 10,000 random designs decided, a twin elaborator agrees, 151 of 151 planted faults caught, 22 breaker runs with no false PASS | measured in the gate run earlier this session |
| Geometry | Exact 2D points or scalar parameters. No 3D, mesh or B-rep. | measured |
| Across parts | Port contracts on current, temperature, voltage and force only | measured |
| Vibration, fatigue, transients | None | measured |

### False PASSes found on 2026-11-06

I re-ran five of these myself. The rest are labelled by who found them.

| Design | Verdict | Why it is wrong | Label |
|---|---|---|---|
| Shear tab, 8 rows at 3 in pitch on a W16x31 (depth 15.9 in) | PASS, 17 of 17 | The bottom bolt sits 24 in down, below the beam | measured, re-run by me |
| Shear tab, W36x231 beam into the web of a W10x45 column | PASS | The beam's 16.5 in flange cannot fit between the column flanges | measured, re-run by me |
| Double angle, same beam and column | PASS | Same | measured, re-run by me |
| Bolt bracket, gauge 10 in on a W10x45 flange (8.02 in wide) | PASS | The bolts are off the flange | measured, re-run by me |
| Circuit, 16 mm2 cable into a 4 mm2 lever terminal | PASS | The conductor does not fit the terminal | measured, re-run by me |
| Seat, single angle, end plate with too many rows | PASS | Same fit failures in other kinds | reported by reviewer A |
| Warren truss scaled to a 600 m span under 1 to 2 N | PASS | The model has no self-weight, and the out-of-plane bracing it assumes is never stated | reported by reviewer A |
| Any cable near the voltage-drop limit | Drop about 7% low | Resistance is `rho20 / nominal area` (`petra/registry/catalog.py:91`), 6.90 ohm/km for 2.5 mm2, not the IEC 60228 maximum of 7.41 | measured in code |

Two more premises lean the unsafe way and are already disclosed in the code. `truss.plastic` takes a buckled member to keep holding its load. The cable's current rating comes from a judged surface coefficient.

**What this means.** The gate, the twin, the planted faults and the breaker all search inside the model. None of them can find a failure mode the model never names (inferred). The published worked examples cannot find one either. `tests/test_steel_companion.py`, `test_steel_part2.py` and `test_steel_groups.py` already reproduce them, and the gaps survived, because worked examples are sensible designs (measured). Prove It Works changed the plan here. A deck counts as covered only when a judge outside the model agrees, and that judge has to look at absurd designs.

## 2. What we make

**The goal beyond the goal.** Any physical design an AI proposes can be accepted the way a compiled program is accepted. A small checker anyone can run says the design meets its requirements, and says exactly what that rests on.

**The product in one sentence.** Petra turns a signed requirements card and a design into a verdict anyone can re-check, and the designer turns a prompt into a design that passes.

It is a compiler, layer by layer (COMPILER §1). The language is `.petra`. The kernel is the type checker. The decks are the standard library. The designer is the optimiser. CAD, drawings and the calculation package are the binary. CompCert proves the C it compiles and never takes apart a binary to check it. So CAD comes out of a checked design, stamped with the design's hash.

| Part | What it is | Who uses it | Open |
|---|---|---|---|
| Petra | The language, the kernel, the decks, the `petra` command and the Python API | Agents, then engineers | Yes |
| Petra Bench | Design tasks from requirements cards, scored by Petra, with baselines and a training environment | Labs and agent builders | Yes |
| The designer | Prompt to requirements card to checked `.petra` to CAD and calculation package. Name to be chosen; Daedalus is already the wave-physics engine. | People who want a part designed | Yes. This reverses NICHE §8, following your later call that the designer need not stay private. |

**What Petra is not.** It is not a CAD program, a finite element solver, or a platform that converts between formats. Solvers are untrusted helpers that hand the kernel evidence (measured, `petra/solvers/`).

## 3. Who it is for, in order

1. **Coding agents.** A user asks Claude Code, Codex or Cursor to "check this steel connection" or "size this connection for 45 kips". The agent installs Petra, reads one page, writes a design, and acts on the verdict. Reaching agents should cost no outreach, because they install from PyPI and start a new tool with `--help` (Appendix B, item 9, search snippets only, so this is a guess until P1's publish predicate measures it). A 3D machined or printed bracket is a different job, and waits for coverage row 8 (inferred).
2. **Labs and agent builders.** They load environments in Harbor, verifiers or OpenEnv format, tagged `rl-environment` on Hugging Face (items 5 to 7). Xplore, Talos and Vektor grade with solvers and keep their tasks closed. EngDesign is open and graded by simulation (items 10 to 12). None was found that certifies code compliance or answers UNKNOWN.
3. **Engineers.** They check a design they or an AI made. For steel connections this already works as a check calculation once the parameters are typed in (measured, cold-start job 2). Today they must work in AISC and US customary units.

**The bet, and how we test it.** Groups 1 and 3 often overlap. The person asking an agent to check a connection is usually an engineer. The bet is that agents pick Petra up once it is findable and works first time. After publishing, we track outside installs, issues, dependents and benchmark submissions. If those are near zero 60 days after publishing, we revisit the order of §3 (the 60 days is a guess).

## 4. What we cover

### When a design class counts as covered

All of these, each a re-runnable gate:
- every failure mode the governing code names is generated as an obligation, whether or not a claim asks for it;
- **every part sits in an exact geometric model**, with containment, non-intersection and clearance obligations generated from it, never written per kind;
- every load the design causes (self-weight, for a start) is included, and every assumption it needs (bracing, for one) is stated as a premise;
- every model has validity rows, and a design outside them gets UNKNOWN, never PASS;
- every registry value is an interval, and each check takes the value its method was calibrated with (AISC's nominal values with their phi factors), or else the worst end of the interval the standard specifies;
- a random-design gate decides 100%, and a twin elaborator agrees;
- **an absurd-design breaker, scored on seeded canaries, finds no PASS.** It must catch at least 90% of the seeded absurd canaries (ENGINE_MAP §6.3), so a weak breaker cannot pass the gate.

No class meets this today. Steel connections meet all but the geometry, loads and breaker items.

### The order

Coverage grows by rule family. Rows that open a family come early, because each family serves many niches (NICHE §14.7). Durations are guesses for one founder with agents. Writing code is fast. The 22,369-line package (measured) was written between 2026-11-05 and 2026-11-06 (reviewer B, from git). Getting it right is the slow part.

| Order | Coverage step | New maths | Niches it opens | Guess |
|---|---|---|---|---|
| 1 | Close steel connections on the coverage rule above, then add the remaining Chapter J and K and Manual Part 9 to 15 types | Geometry model, R4 | Building connections | in P1 |
| 2 | 2D lower-bound limit analysis (K3 phase A, an LP on R1) | None in the kernel (PRIOR_ART K3) | Gusset and bracket plates, cut-outs | 1 to 2 weeks |
| 3 | 3D frames and the linker: one LP over each part's capacity polytope | R1 again | Platforms, stands, racking, skids, assemblies | 2 to 4 weeks |
| 4 | Fatigue on code-defined details (AISC 360 Appendix 3) | R4 plus a cycle count on the card | Cyclic supports, crane runways | 1 week |
| 5 | Lowest natural frequency of a discrete model: K minus omega squared M positive definite | R2 with a negative mass weight, which R2's proof allows (`r2_definite.py:68`) | Frame modes against machine speed, for the model as built. A continuum part needs a discretisation bound, which is research. | 1 to 2 weeks |
| 6 | Steady heat networks between parts | R1 or R4 | Electrical panels, battery packs | 1 to 2 weeks |
| 7 | Lifting devices: lugs, padeyes, lifting beams | Members (Chapters D to H) plus BTH-1, a paid standard implemented by clause | Lifting and handling | 3 to 6 weeks |
| 8 | 3D continuum limit analysis and Prager-Synge bounds | Phase B conic rule; 3D eigenvalue constants are research | Machined, cast and printed parts | months |
| 9 | Validated ODE steps (K4) | New rule, about 120 lines (PRIOR_ART) | Transients, braking, heating over time | 2 to 4 weeks |

**Retired from the front.** Drones need rows 5 and 9 plus attitude stability before a PASS means anything. Electronics DC worst case needs only R4, and atopile offers an agent hook, so it is the strongest candidate for a second deck alongside row 2. Loop stability there still needs a new family (inferred, BRAINSTORM §4.2).

**Whole systems.** Fatigue, vibration and heat across parts are rows 3 to 6 and 9. They combine through the linker. Each part certifies the loads it can carry, and an assembly holds when one LP finds connection loads inside every part's range (BRAINSTORM §4.3).

## 5. What we conquer

**The category is verified engineering.** Autonomous engineering is the goal. Verified engineering is what makes autonomy safe to accept. An AI's design is trusted because its proof re-checks, not because the AI is good.

Lean is the precedent. It became the checker for AI mathematics through a one-line install and JSON access for agents, one growing library, public benchmarks, and labs training against it as the reward (Appendix B, items 1 to 4). Lean's trust lives in a kernel that rarely fails. Petra's failures so far all live in elaboration, so our trust work goes there first (§6, P1 and P7).

**Engines that grow with compute.** These need no outreach and get stronger the more we run them:
- the absurd-design breaker and its canaries, run across every kind and domain;
- the optimiser in P2, which pushes mass down and so walks into false-PASS regions first;
- the task generator, with hard tiers and hidden variants, so the benchmark does not saturate the way miniF2F did (item 4);
- self-play between the designer and the breakers (BRAINSTORM §4.4);
- validity atlases, which map where each model has been checked against an outside oracle (BRAINSTORM §4.7);
- spot checks against an independent solver, CalculiX, as `docs/steel_connections.md` §8 already plans.

**Things that grow with adoption.** These need no outreach either, but they need users to find Petra, and we measure them (§3):
- the install path agents find first: PyPI, a SKILL.md, the MCP registry, the Hugging Face tag;
- the open requirements card, design and certificate specifications.

## 6. What we build

Each phase ends in a predicate someone can re-run. Lanes that touch different files run in parallel. A phase is done only when its predicate passes.

**Compute ends 2026-11-15** (ENGINE_MAP D5). The canary campaign in P0 and the breaker runs in P1 are the most compute-hungry work, so they run first.

### P0. Usable, and the gap measured (2 to 4 days)

1. **One trunk.** Fast-forward `master` to `daedalus/mechanics-layer`. Commit `docs/principles.md`.
2. **Measure the gap.** Write the absurd-design generator and its seeded canaries for every steel kind and every domain, run it, and publish the count of absurd designs that get PASS. This is the baseline P1 must drive to zero.
3. **Package.** A `pyproject.toml` with a `petra` command, an Apache-2.0 licence, and a wheel that installs offline. The README gets Install, Quickstart and the steel deck up front, and its sample output comes from a test, so it cannot go stale.
4. **Teach.** `petra kinds` and `petra new <kind>` print each kind's fields, units and a template, generated from the domain specs. Add `petra registry list [prefix]` with "did you mean" suggestions, map common names such as A325 to their entries, and generate the language reference the same way.
5. **Make results actionable.** For every refuted check, report demand, capacity and utilisation in the user's units, the governing sub-check, and its own counterexample. `--json` carries all of it. Document the Python API, MARGINAL included.

**Done when** the scripted cold-start test passes on fresh agents with rotated, held-out briefs. Install takes one call from the wheel, offline. The steel job takes under 10 tool calls, with no `dir()` or repr digging. The repair job reaches PASS from the output alone. The baseline is about 8 calls to install, 22 for the steel job, and three hand-computed repair tries (Appendix A).

**Result, 2026-11-07: met in round 2.** Each round ran two fresh agents on held-out briefs, with only the wheel, outside the repository. The outside judge found every design they reached PASS on buildable.

| Round | Install | Steel job | Repair | Library |
|---|---|---|---|---|
| 1 (sets A, B) | 1 pip call each | 7 and 8 calls; both needed `--json` and a script to name the governing check | 1 try after a hand calculation; 4 tries, which found tearout from AISC knowledge | `dir()` and repr, because no document shipped |
| 2 (sets C, D), after one fix round | 1 pip call each | 5 and 8 calls, read from the text report | 1 try each, chosen from the limit the report names | `petra docs api` alone; one inspection to learn why a utilisation was blank |

The gap baseline is 1,711 of 15,600 generated designs that PASS but cannot be built as drawn, 16% of all PASSes (`docs/absurd_gap.md`, seed 1). Sixty-three of the 2,532 designs the deck's own samplers drew are in it, so the steel gate's "no false PASS" held for strength only.

`master` has not moved. The fast-forward waits on your go.

### P1. Safe (1 to 3 weeks)

1. **An exact geometric model for every steel kind.** Plates, bolts, beam and support become exact rational shapes, and containment, non-intersection, edge and clearance obligations are generated from that one model. This covers all three fit classes: the beam side, the support side, and the beam against the support (flange clearance, cope needed). The same model later emits the CAD in P4.
2. **Loads and premises.** Add self-weight to the truss, and state its bracing assumption as a premise. Add a conductor-to-terminal fit check. Close the unconservative premises the code already admits, or turn them into UNKNOWN.
3. **The registry as a versioned, physical instruction set.** Values become intervals. Each entry gets a version, its source and an errata field, and the cable resistance fix is the first erratum. A recall query answers "which verdicts rest on this entry" (COMPILER §6, rows 3 and 4).
4. **Re-run the whole gate.** That means the twin, the planted faults, the 10,000 designs, and the breaker with canary recall of at least 90%, across every kind and domain.
5. **Coverage from the physics, not from the declared loads.** A flange force demands the panel-zone check only when the design declares a `panel_shear` load (`petra/models/steel/path.py`), so leaving the load out removes the check. The same question holds for a shear tee's flexibility and prying, and for the stiffened seat's plate and top angle, which no obligation names. Each mode a part's physics implies is demanded. A load the design leaves out gives UNKNOWN with what it needs, not a shorter list.
6. **Say what was not checked.** An excused check and a mode the coverage table did not demand both print a line that names it and why.
7. **What P0 found the plan must decide.**
   - Five steel kinds and the bolt and uncertainty domains have no canary yet. Seed them from the gap examples, or recall cannot be measured.
   - The grammar does not say whether a support is a column or a girder, so "cope needed" cannot be judged.
   - Whether a part on a web-to-flange fillet counts as unbuildable decides 238 of the 1,711.
   - The gap count is compared only at a pinned seed and generator commit.

8. **The joint and demand classes the canary lane found.** A bolted joint's force model holds only while the plates stay clamped, and a demand's stated capacity can sit above the level where the design's own tests broke a part. The outside judge finds about 360 and 340 such designs in 54,000 (seeds 1 to 3). Each becomes an obligation or an UNKNOWN.

**Result so far, 2026-11-07.** Items 1, 3, 6 and the canaries of item 7 are merged. The steel gap fell from 1,516 to 0 on seed 1 and is 0 on the unseen seed 7. Canary recall on Petra before the fit checks was 51 of 53. The canary lane showed the recall measure needed restating, below.

**How recall is measured.** A canary hole is the set of modes that refuse a canary, treated as discharged in tooling. The search, with the judge as its oracle, must find a PASS of that canary's kind and condition. The bar is at least 90% of canary holes pooled, with each hole's budget set to three over its cell's measured rate (at least 600 designs). Per kind, recall is reported, not gated, because one rare cell sinks a kind with one to three canaries. Recall by single mode is reported only: it falls toward zero as the fit gaps close. Runs compare by stream hash, not by seed and commit, because the generator samples the registry. flange_force has no canary because its grammar draws no parts, and the report says so (P5 draws more).

**Done when** the absurd-design count is zero on seed 1 and the held-out seeds 2 and 3, canary recall meets the bar above, and the full gate passes.

**Then publish,** on your go (§8): the public repository, then PyPI. **Done when** a networked fresh agent installs from public PyPI and passes the rotated briefs.

### P2. In the loop (1 to 2 weeks)

- A plain-data result from `petra.check(text)`, and a FAIL that names the input that moves it most and which way.
- An MCP server over the same API, standard library only, and a SKILL.md for coding agents. The check is already fast enough: 0.07 s in process (measured).
- **The repair-and-minimise loop.** An agent or a search writes, checks and repairs until PASS, then pushes mass down under certified margins. It is the benchmark's reference optimum and the strongest breaker we have, so every design it finds is also checked against CalculiX.

**Done when**, on held-out steel tasks, an agent reaches PASS within 10 checks on at least 80% of tasks (both targets are guesses to be tuned once, then frozen), and no design the optimiser finds fails the geometry model or the CalculiX spot check.

### P3. Petra Bench v0 (2 to 3 weeks)

- **Tasks** are requirements cards with the design left blank. The agent may call Petra, as an engineer calls a checker. The score is certified mass against the reference optimum, and FAIL or UNKNOWN scores zero. Hard tiers and hidden variants come from the generator.
- **Format.** Harbor task directories with Petra in `tests/test.sh`, tagged on Hugging Face.
- **Baselines** for three or four frontier models, run by us.
- **Lift.** Each baseline also runs without Petra: the same model and the same held-out tasks, with Python and whatever it knows of the specification. Both arms are graded by checks that do not trust the agent: Petra, the outside judge for buildability, CalculiX for strength, and a hand-checked sample. The numbers are the share of final designs that are safe and buildable, the share the agent called safe that are not, mass against the reference optimum, and checks and tokens to finish. If the arm without Petra scores as well, the bet in §3 is wrong, so a pilot of ten tasks per arm runs as soon as P1 is done.
- **Grader honesty.** Publish the breaker sample size and Petra's false-PASS count, split into arithmetic, coverage and validity (PRIOR_ART A2). Compare against an independent solver at equal compute (ENGINE_MAP §6.1), and run Petra over other graders' passing designs to count their false PASSes (BRAINSTORM X3).
- **Open specifications** for the requirements card, the design and the certificate, with a written `.petra` semantics (E3).

**Done when** the tasks, baselines and grader numbers are public and reproduce with one command.

### P4. The designer, for connections (2 to 4 weeks)

- Prompt to requirements card, with read-back (E4): the card is shown back in plain words, and nothing is signed until it is confirmed. An agent cannot sign for the user.
- Templates for the steel connection kinds, sized from the shapes table.
- The P2 loop to PASS and minimum mass.
- A build123d STEP file from the P1 geometry model, plus drawings, a bill of materials and the calculation package, all bound to the design hash (E5) and checked by `petra verify --design`.

**Done when** prompts written by someone else each produce a package whose hash re-checks, whose solid model matches the design parameters, and which has no interference.

### P5. Coverage

The rows of §4 in order. Each ships only when it meets the coverage rule, absurd-design breaker included.

### P6. Readers for other tools' files

One reader per kind of data, never one per format. A reader fills fields of the requirements card or the design, and never produces a verdict.

| Kind | Example files | Fills | When |
|---|---|---|---|
| Parametric model | Connection schedules, IDEA Open Model, IFC objects | Geometry, material | After P1 |
| Design source | An exact CadQuery or build123d subset | The design | After P4 |
| Analysis deck | CalculiX `.inp` | Mesh, material, loads, supports | After coverage row 2 |
| Bare geometry | STEP | Geometry | Last, through a rational polyhedron inside the part |
| Requirements | SysML v2 | Claims, loads, environment | When a user asks |

**Done when**, for each reader, a design filled by the reader gets the same verdict as the same design written by hand, and every field the file cannot supply is printed as missing rather than guessed.

### P7. Trust upgrades

Units inside the certificate (E2), twin elaborators for every deck, and finally a Lean port of the kernel rules that re-checks the same JSON certificates. The Lean port comes last because the kernel is not where Petra has failed (§1).

**Done when** the Lean checker accepts every certificate in the gate corpus and rejects every planted fault, and every deck has a twin that agrees on the full gate.

## 7. What we stop

- **dira and the Studio stay frozen.** Pieces move into Petra only when a phase needs them (ENGINE_MAP D1).
- **The five planning documents become background.** This plan sets the order. The others keep their evidence.
- **No importer per file format, and no conversion between design representations** (PRIOR_ART never-do list).
- **No new physics before P1 passes.** Laziness Protocol cut the near term to the smallest set of changes between today and a safe first verdict for a stranger.
- **No claim of "zero false PASS" anywhere public** until P1's predicate holds.
- **No money, pricing or go-to-market sections.**

## 8. Decisions only you can make

1. **Publish after P1, or earlier as an alpha with the false-PASS list printed on the README.** I recommend after P1, because a checker's first public fact should not be a false PASS.
2. **Where to publish.** A `NooterraLabs` or `nooterra` GitHub org. Publishing is an outward action, so it waits for you.
3. **The licence.** Apache-2.0, which ENGINE_MAP D3 made conditional on a data-licence audit. The full AISC shapes table cannot ship until that audit says how.
4. **Claim `petra` on PyPI.** It is free today (measured).
5. **The designer's name.** Daedalus is taken by the wave-physics engine.
6. **The last credits, to 2026-11-15.** I recommend spending them on the P0 canary campaign and the P1 breaker runs.
7. **Registry values from physics, or from specified limits.** `docs/frame.md` item 5 says registries are computed from physics, with wire resistance from resistivity and nominal area as the example. That derivation is what produced the low resistance. IEC 60228 specifies a maximum resistance, not an area, so physics alone cannot give the guaranteed value. I recommend allowing a short list of specified limits as constants, and changing frame.md item 5 to say so.
8. **How Petra is run in the open.** `docs/open_source.md` sets out how Lean, Rocq, seL4, Ferrocene, code_aster and the open benchmarks are run, and a playbook for Petra. Three of its steps are yours: CC-BY-4.0 for the docs, the DCO with a pledge that Petra stays Apache-2.0, and who holds the Petra name and on what terms others may use it.

## Appendix A. Cold-start test

A fresh general-purpose agent, with no context and no network, got five jobs on 2026-11-06.

| Job | Result | Tool calls | Notes |
|---|---|---|---|
| Install | Only with a workaround | About 8 | pip cannot install a folder without `pyproject.toml` |
| Steel shear tab, W16x31, 3 bolts, 45 kip | FAIL, 2 of 17 refuted | About 22 | Copied an example almost whole. Needed beam grade, support, edge distances and a signer the brief did not give. |
| Cable, 2.5 mm2, 30 m, 16 to 20 A | FAIL, 4 of 5 refuted | About 6 | Needed a protective device and a fault current. Printed no drop or temperature figures. |
| Library | Worked | About 6 | Per-claim access found by inspecting objects |
| Repair to PASS at 60 kip | Third try | About 6 | Output gave no demand, capacity or direction to change |

While repairing, the agent tried 5, 6 and 8 rows and got PASS on all three. That is how the first false PASS surfaced.

The agent ranked three fixes. First, an install path. Second, a generated language reference with registry listing and common names. Third, failure output with demand, capacity, the governing sub-check and full JSON. It also noted that the shear tab takes the full bolt-line distance as eccentricity with the elastic method. That choice is conservative and documented in `docs/steel_connections.md:131`, but not to users.

## Appendix B. Research sources

A research agent read these on 2026-11-06. "Snippet" means only a search excerpt was seen.

1. Lean install with elan: https://github.com/leanprover/elan (read)
2. The Lean REPL's JSON interface: https://github.com/leanprover-community/repl (read). Pip wrappers: https://github.com/augustepoiroux/LeanInteract (read), https://github.com/project-numina/kimina-lean-server (read)
3. Mathlib size: https://leanprover-community.github.io/mathlib_stats.html (read)
4. Labs on Lean: DeepSeek-Prover-V2 https://arxiv.org/abs/2504.21801 (read), Kimina-Prover https://arxiv.org/abs/2504.11354 (read), Seed-Prover 1.5 https://seed.bytedance.com/en/blog/seed-prover-1-5-advanced-mathematical-reasoning-through-a-novel-agentic-architecture (read), AlphaProof https://www.nature.com/articles/s41586-025-09833-y (snippet), PutnamBench https://trishullab.github.io/PutnamBench/leaderboard.html (read)
5. Harbor task format: https://harborframework.com/docs/tasks (read)
6. Prime Intellect verifiers and the Environments Hub: https://docs.primeintellect.ai/verifiers/overview (read)
7. OpenEnv: https://github.com/openenv/OpenEnv (read). Hugging Face RL environments as tagged datasets: https://huggingface.co/blog/rl-environments (snippet)
8. MCP registry growth: https://www.digitalapplied.com/blog/mcp-adoption-statistics-2026-model-context-protocol (read, a secondary source)
9. CLI against MCP for agents: https://labs.scale.com/blog/mcp-vs-cli (snippet), https://spiritroom.app/blog/mcp-vs-cli-for-agents/ (snippet)
10. Xplore RWE-bench: https://xplore.ai/rwe-bench (read)
11. Talos: https://talos-ai.org/environments/ (read). Vektor: https://vektor-technologies.com/ (read). g factor: https://www.g-ftech.com/gyms (read)
12. EngDesign, 101 tasks graded by simulation, 67 under MIT: https://github.com/AGI4Engineering/EngDesign (read)
13. IDEA StatiCa Connection API: https://developer.ideastatica.com/docs/api/connection-api/connection_api_overview.html (read). SCS Steel Connection Studio APIs: https://www.scs.pe/apis (read)
14. Formal in Silico, Lean-checked certificates for FEM, DFT and molecular dynamics results: https://smu-diga.github.io/formal-in-silico-programme/ (read). It certifies simulation numbers, not design verdicts, so it is a reference for P7, not a rival.

## Appendix C. What the two reviews changed

Two independent reviewers attacked the first draft. The rewrite that followed (a new P1, a new coverage order, new predicates) has not been reviewed again. Both ran on the same model as the author, because every pstack role in this setup is set to the parent model, so the panel had no model diversity. Findings both raised carry the most weight.

**Acted on, raised by both:**
- The fit fix was too narrow. Five more false PASSes reproduced (§1). P1 now builds one geometric model per kind instead of writing a fit rule per kind.
- The worked-example judge already existed and could not see the gap.
- The P0 predicate could pass with the gaps still open. Safety is now P1's own predicate, with canary recall.
- "Grows with compute" was hollow. §5 now separates compute engines from adoption.
- The discrete frequency check was oversold. It certifies the lowest mode of the model only.

**Acted on, raised by one:**
- Reviewer A: the registry rule "guaranteed, never nominal" would condemn AISC's calibrated nominal values. It was replaced with per-check interval ends.
- Reviewer A: an offline install needs a wheel, and the shapes table holds 30 W shapes.
- Reviewer A: the truss has no self-weight.
- Reviewer B: the benchmark needed a score beyond PASS, a decision on checker access, an independent oracle, and an attack on outside graders.
- Reviewer B: the designer needed read-back before signing, and P4 should cover connections only.
- Reviewer B: coverage rows that open families should come earlier, with estimates.
- Reviewer B: credits end 2026-11-15, and serial gating wasted parallel lanes.
- Reviewer B: the agents-first bet needed a measure and a date.

**Considered and kept as is:**
- Electronics as the second deck. It is now named as the strongest candidate to run alongside row 2, not moved ahead of it.
- Copyright of standards tables. Single specified limits per size, such as IEC 60228 maximum resistances, are values. Rating tables stay out, and current ratings stay derived, with their judged coefficient disclosed.

**Left to you:** reviewer B's point that taking IEC 60228 maxima conflicts with `docs/frame.md` item 5 (§8, decision 7).

**Dismissed:** none. Every finding had a concrete basis.
