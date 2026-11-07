# Petra project plan

This plan sets one order of work for Petra. Earlier planning documents disagreed on where to start. ENGINE_MAP picks drones first, and BRAINSTORM picks electronics. NICHE §14.4 picks steel connections, with lifting as the designer's first product. This plan keeps NICHE's first pick, moves lifting later, and makes connections the designer's first product too.

ENGINE_MAP, BRAINSTORM, NICHE, COMPILER and PRIOR_ART are the project's earlier planning documents. They are not in this repository. Bare labels such as E2 to E5 refer to items from the same planning work.

The plan was written on 2026-11-06 and revised the same day after two adversarial reviews (Appendix C). The summary and §1 to §5 describe Petra as it stood on 2026-11-06. Each phase in §6 records its own results, with their dates.

Every claim carries a label: **measured** (run or read while writing this plan), **inferred** (reasoned from measured facts), or **guess**.

## Summary

1. **The project builds a compiler for physical designs.** A signed requirements card and a design go in. Out comes a verdict anyone can re-check, then the build files. The verdict is PASS, FAIL with a counterexample, or UNKNOWN naming what is missing.
2. **It has three parts.** They are the open checker (Petra), a benchmark and training environment (Petra Bench), and a designer that writes Petra and emits CAD.
3. **When this plan was written, no stranger could use Petra, and it was not yet safe.** It had no package file, licence, public repository or language reference (measured). In one afternoon, a fresh agent and a reviewer found false PASSes of three kinds: parts that do not fit, a conductor that does not fit its terminal, and a truss with no self-weight. A cable resistance was also unconservative (§1).
4. **Every false PASS is in elaboration, the layer that turns a design into maths.** None is in the kernel. Petra's own gate reported zero false PASS because it checks Petra against itself (inferred from §1).
5. **So the first work is a geometry judge and a measured breaker, not more physics.** Packaging runs alongside that work. Publishing waits for both.
6. **The first users are AI agents, then labs, then engineers.** A dated check after publishing measures whether agents really come first (§3).
7. **Petra covers one design class completely before the next.** Coverage grows by rule family, not by niche (§4).
8. **Petra wins its category with engines that grow with compute.** These are breakers, an optimiser that hunts for false PASSes, a task generator, and self-play. The install path and the certificate format grow with adoption, and the project measures that growth rather than assuming it (§5).
9. **CAD is an output first.** Reading other tools' files comes later, with one reader per kind of data (§6, P6).
10. **The build order.** P0 makes Petra usable and P1 makes it safe. Then Petra is published. After that come P2 (Petra in the agent's loop), P3 (the benchmark), P4 (the designer), P5 (coverage), P6 (readers for other tools' files) and P7 (trust upgrades), all in §6. P8 is a pilot that proves one code formula against physics. It runs alongside P2 and is the first test of the long-term aim in §5.

## 1. Where Petra stood on 2026-11-06, measured

### The path of a new user

The first rows come from the plan author's own checks. The rest come from a cold-start test, in which a fresh agent with no context and no network had to install Petra and do five jobs (Appendix A).

| Step | What a newcomer needs | State on 2026-11-06 | Label |
|---|---|---|---|
| Find it | A public repository or package page | No git remote | measured |
| Trust the licence | A licence file | None | measured |
| Install | `pip install petra` | No `pyproject.toml` (`ls` fails, measured). The PyPI JSON API returned 404 for `petra`, which was read as the name being free. That reading was wrong: the API returns 404 for a project with no releases, and `petra` is held by such a project. The cold-start agent reports that pip printed "Neither 'setup.py' nor 'pyproject.toml' found", and that it needed a hand-made `.pth` file and wrapper scripts, about 8 tool calls. | measured, partly by the agent |
| Get the real product | One trunk | `master` is 16 commits behind `daedalus/mechanics-layer` (15 before this plan's own commit). It is a fast-forward, because `validity-obligations` is already inside it. | measured |
| Read what the code cites | Every cited doc in git | The steel code and tests cite `docs/principles.md`, but git does not track it | measured |
| Find the steel deck | A README pointer | The README never mentions it. The agent found `examples/steel` with `ls`. | measured |
| Learn the language | A reference and templates | None. The agent copied an example's 13 lines and learned field names from the error messages, which were clear. | measured |
| Name parts | A way to list the registry | None. Petra answers "A325 is not a registry material", with no suggestion. The agent grepped a 305 KB deck JSON. | reported by the agent |
| Use any beam | The full shapes table | 30 W shapes and 16 angles ship. W8x31 is "not a W shape in the shape table". The full table needs the AISC spreadsheet locally. | measured by reviewer A |
| Run a check | A `petra` command | It works, in 1.8 s from the command line. The check takes 0.07 s, and import takes the rest. | measured |
| Read results in code | A documented API and full JSON | `petra.check_file` works (measured). Per-claim access is undocumented, and `--json` printed `"obligations": []` and no counterexample (reported by the agent, reproduced by reviewer A). | measured, partly |
| Fix a FAIL | Demand, capacity, the input to change | None of these. Counterexamples print as SI rationals, some without units. The agent repaired the design in three hand-computed tries. | reported by the agent |
| Train against it | An environment in a hub format | `petra gym` has its own `step(Submission)` API, in no hub format, with generators for circuits and bolts only. | measured |

### What the checker could prove on 2026-11-06

| Area | State on 2026-11-06 | Label |
|---|---|---|
| Kernel | 6 rule families, exact rationals, 2,615 lines | measured |
| Trusted elaboration | Models, language, coverage, registry and pipeline, about 15,000 lines. Every false PASS below is here. | measured by reviewer A |
| Domains | 2D trusses, one cable's heating and voltage drop, bolted joints, probability bounds, 11 AISC steel connection kinds | measured |
| Steel gate | 10,000 of 10,000 random designs decided, a twin elaborator agrees, 151 of 151 planted faults caught, 22 breaker runs with no false PASS | measured in a gate run earlier in the session that wrote this plan |
| Geometry | Exact 2D points or scalar parameters. No 3D, mesh or B-rep. | measured |
| Across parts | Port contracts on current, temperature, voltage and force only | measured |
| Vibration, fatigue, transients | None | measured |

### False PASSes found on 2026-11-06

The plan's author re-ran five of these. Each of the others is labelled with who found it.

| Design | Verdict | Why it is wrong | Label |
|---|---|---|---|
| Shear tab, 8 rows at 3 in pitch on a W16x31 (depth 15.9 in) | PASS, 17 of 17 | The bottom bolt sits 24 in down, below the beam | measured, re-run by the author |
| Shear tab, W36x231 beam into the web of a W10x45 column | PASS | The beam's 16.5 in flange cannot fit between the column flanges | measured, re-run by the author |
| Double angle, same beam and column | PASS | Same | measured, re-run by the author |
| Bolt bracket, gauge 10 in on a W10x45 flange (8.02 in wide) | PASS | The bolts are off the flange | measured, re-run by the author |
| Circuit, 16 mm2 cable into a 4 mm2 lever terminal | PASS | The conductor does not fit the terminal | measured, re-run by the author |
| Seat, single angle, end plate with too many rows | PASS | Same fit failures in other kinds | reported by reviewer A |
| Warren truss scaled to a 600 m span under 1 to 2 N | PASS | The model has no self-weight, and it never states the out-of-plane bracing it assumes | reported by reviewer A |
| Any cable near the voltage-drop limit | Drop about 7% low | Resistance is `rho20 / nominal area` (`petra/registry/catalog.py:91`), 6.90 ohm/km for 2.5 mm2, not the IEC 60228 maximum of 7.41 | measured in code |

Two more premises are unconservative, and the code already discloses both. `truss.plastic` assumes that a buckled member keeps holding its load. The cable's current rating comes from a judged surface coefficient.

**Why the checks missed them.** The gate, the twin elaborator, the planted faults and the breaker all search inside the model. None of them can find a failure mode the model never names (inferred). The published worked examples cannot find one either. `tests/test_steel_companion.py`, `test_steel_part2.py` and `test_steel_groups.py` already reproduce those examples, and the gaps survived them, because worked examples are sensible designs (measured). That finding changed the plan, under the rule that work must be proved on the real artifact, not on a proxy for it. A deck counts as covered only when a judge outside the model agrees, and that judge has to look at absurd designs.

## 2. What the project makes

**The purpose.** Petra aims to let people accept any physical design an AI proposes the way they accept a compiled program. A small checker that anyone can run says the design meets its requirements, and says exactly what that verdict rests on.

**The product in one sentence.** Petra turns a signed requirements card and a design into a verdict anyone can re-check, and the designer turns a prompt into a design that passes.

The whole system is a compiler, layer by layer (COMPILER §1). The language is `.petra`. The kernel is the type checker. The decks are the standard library. The designer is the optimiser. CAD, drawings and the calculation package are the binary. CompCert proves the C it compiles and never takes apart a binary to check it. So CAD comes out of a checked design, stamped with the design's hash.

| Part | What it is | Who uses it | Open |
|---|---|---|---|
| Petra | The language, the kernel, the decks, the `petra` command and the Python API | Agents, then engineers | Yes |
| Petra Bench | Design tasks from requirements cards, scored by Petra, with baselines and a training environment | Labs and agent builders | Yes |
| The designer | It goes from a prompt to a requirements card, then to checked `.petra`, then to CAD and a calculation package. Its name is not chosen yet. Daedalus is already the wave-physics engine. | People who want a part designed | Yes. This reverses NICHE §8, following the maintainer's later decision that the designer need not stay private. |

**What Petra is not.** It is not a CAD program, a finite element solver, or a platform that converts between formats. Solvers are untrusted helpers that hand the kernel evidence (measured, `petra/solvers/`).

## 3. Who it is for, in order

1. **Coding agents.** A user asks Claude Code, Codex or Cursor to "check this steel connection" or "size this connection for 45 kips". The agent installs Petra, reads one page, writes a design, and acts on the verdict. Reaching agents should need no outreach, because agents install from PyPI and start a new tool with `--help`. That is a guess until P1's publish predicate measures it, because its only sources are search snippets (Appendix B, item 9). A 3D machined or printed bracket is a different job, and it waits for coverage row 8 (inferred).
2. **Labs and agent builders.** They load environments in Harbor, verifiers or OpenEnv format, tagged `rl-environment` on Hugging Face (Appendix B, items 5 to 7). Xplore, Talos and Vektor grade with solvers and keep their tasks closed. EngDesign is open and graded by simulation (items 10 to 12). The research found none that certifies code compliance or answers UNKNOWN.
3. **Engineers.** They check a design that they or an AI made. For steel connections, Petra already works as a check calculation once the parameters are typed in (measured, cold-start job 2). As of 2026-11-06, engineers must work in AISC and US customary units.

**The bet, and how to test it.** Groups 1 and 3 often overlap, because the person asking an agent to check a connection is usually an engineer. The bet is that agents pick Petra up once it is findable and works the first time. After publishing, the project tracks outside installs, issues, dependents and benchmark submissions. If those are near zero 60 days after publishing, the project revisits the order in §3 (the 60 days is a guess).

## 4. What Petra covers

### The coverage rule

A design class counts as covered only when all of these hold, and each is a gate someone can re-run:

- Petra generates an obligation for every failure mode the governing code names, whether or not a claim asks for it.
- **Every part sits in an exact geometric model.** Petra generates containment, non-intersection and clearance obligations from that model, and never writes them per kind.
- Petra includes every load the design causes, starting with self-weight. It states every assumption the design needs, such as bracing, as a premise.
- Every model has validity rows, and a design outside them gets UNKNOWN, never PASS.
- Every registry value is an interval. Each check takes the value its method was calibrated with, such as AISC's nominal values with their phi factors. Otherwise it takes the worst end of the interval the standard specifies.
- A random-design gate decides 100% of designs, and a twin elaborator agrees.
- **An absurd-design breaker, scored on seeded canaries, finds no PASS.** The breaker must catch at least 90% of the seeded absurd canaries (ENGINE_MAP §6.3), so a weak breaker cannot pass the gate.

On 2026-11-06 no design class met the coverage rule. Steel connections met all but the geometry, loads and breaker items.

### The order of coverage

Coverage grows by rule family. Rows that open a family come early, because each family serves many niches (NICHE §14.7). Durations are guesses for one founder working with agents. Writing code is fast. Reviewer B found from git that the 22,369-line package (measured) was written between 2026-11-05 and 2026-11-06. Making it correct is the slow part.

| Order | Coverage step | New maths | Niches it opens | Guess |
|---|---|---|---|---|
| 1 | Close steel connections on the coverage rule above, then add the remaining Chapter J and K and Manual Part 9 to 15 types | Geometry model, R4 | Building connections | in P1 |
| 2 | 2D lower-bound limit analysis (K3 phase A, an LP on R1) | None in the kernel (PRIOR_ART K3) | Gusset and bracket plates, cut-outs | 1 to 2 weeks |
| 3 | 3D frames and the linker: one LP over each part's capacity polytope | R1 again | Platforms, stands, racking, skids, assemblies | 2 to 4 weeks |
| 4 | Fatigue on code-defined details (AISC 360 Appendix 3) | R4 plus a cycle count on the card | Cyclic supports, crane runways | 1 week |
| 5 | Lowest natural frequency of a discrete model: K minus omega squared M positive definite | R2 with a negative mass weight, which R2's proof allows (`r2_definite.py:68`) | Frame modes against machine speed, for the model as built. A continuum part needs a discretisation bound, which is research. | 1 to 2 weeks |
| 6 | Steady heat networks between parts | R1 or R4 | Electrical panels, battery packs | 1 to 2 weeks |
| 7 | Lifting devices: lugs, padeyes, lifting beams | Members (Chapters D to H) plus BTH-1, a paid standard implemented by clause | Lifting and handling | 3 to 6 weeks |
| 8 | 3D continuum limit analysis and Prager-Synge bounds | Phase B conic rule. 3D eigenvalue constants are research. | Machined, cast and printed parts | months |
| 9 | Validated ODE steps (K4) | New rule, about 120 lines (PRIOR_ART) | Transients, braking, heating over time | 2 to 4 weeks |

**Drones and electronics no longer go first.** Drones need rows 5 and 9, plus attitude stability, before a PASS means anything. Electronics DC worst case needs only R4, and atopile offers an agent hook. So electronics DC worst case is the strongest candidate for a second deck, alongside row 2. Loop stability in electronics still needs a new family (inferred, BRAINSTORM §4.2).

**Whole systems.** Fatigue, vibration and heat across parts are rows 3 to 6 and 9. They combine through the linker. Each part certifies the loads it can carry, and an assembly holds when one LP finds connection loads inside every part's range (BRAINSTORM §4.3).

## 5. The category and the long-term aim

### The category is verified engineering

Autonomous engineering is the goal. Verified engineering is what makes autonomy safe to accept. An AI's design is trusted because its proof re-checks, not because the AI is good.

Lean is the precedent. It became the checker for AI mathematics through a one-line install and JSON access for agents, one growing library, public benchmarks, and labs training against it as the reward (Appendix B, items 1 to 4). Lean's trust rests on a kernel that rarely fails. Petra's failures so far are all in elaboration, so Petra's trust work starts there (§6, P1 and P7).

### Engines that grow with compute

These need no outreach, and they get stronger the more they run:

- the absurd-design breaker and its canaries, run across every kind and domain
- the optimiser in P2, which pushes mass down and so reaches false-PASS regions first
- the task generator, with hard tiers and hidden variants, so the benchmark does not saturate the way miniF2F did (Appendix B, item 4)
- self-play between the designer and the breakers (BRAINSTORM §4.4)
- validity atlases, which map where each model has been checked against an outside oracle (BRAINSTORM §4.7)
- spot checks against an independent solver, CalculiX, as `docs/steel_connections.md` §8 already plans

### What grows with adoption

These also need no outreach, but they need users to find Petra, and the project measures them (§3):

- the install path agents find first: PyPI, a SKILL.md, the MCP registry, the Hugging Face tag
- the open specifications for the requirements card, the design and the certificate

### The long-term aim is a Lean for physical objects

The aim is for Petra to do for physical objects what Lean does for mathematics. Petra becomes the place where every claim about a built thing is written down and re-checked. Lean won with four things: a small trusted kernel, one library that keeps growing, automation whose output the kernel checks, and a benchmark that labs train against. Petra copies all four. It adds a fifth that Lean never needed, a versioned record of what Petra assumes about the physical world. That record holds materials, models and ratings, each with its source and errata.

As of 2026-11-06, the kernel checks code formulas such as AISC's, so trust rests on the project's transcription of the code. Every false PASS so far has been in that layer. The decisive step gives the kernel rules that bound the physics directly, for any geometry:

| Physics | Kernel rule | What it bounds |
|---|---|---|
| Collapse | Lower-bound limit analysis | The load capacity of any part |
| Stiffness | Equilibrated stress (Prager and Synge) | Deflection of any shape |
| Buckling, vibration | Eigenvalue enclosures | Critical loads and frequencies |
| Dynamics | Barrier certificates | Staying inside a safe region |
| Scatter, fatigue | Scenario statistics | Failure probability |

Three things follow (inferred, not yet tested):

1. Any 3D part becomes checkable, so the decks become shortcuts rather than the limits of what Petra can check.
2. Every code formula becomes a theorem to prove. The theorem says that inside its validity range, the formula never claims more than the physics bound allows.
3. Petra flags any clause that cannot be proved, so Petra starts auditing the codes.

The premises that remain cannot be reduced further, and they play the part that axioms play for Lean. They are material behaviour, measured strengths, imperfection and fracture data, and loads, each stated, versioned and recallable. Capturing all of physical design never means every design is decided. It means no design is silently wrong. Each design gets PASS relative to listed premises, FAIL with a counterexample, or UNKNOWN naming what is missing.

| Stage | What it captures | Evidence that it worked |
|---|---|---|
| 1. Steel connections (P0 to P4) | One code-governed niche, with agents in the loop | The lift test in P3, and no false PASS under the breaker |
| 2. All code-governed design | Members, joints, welds, pressure vessels, wiring, timber, concrete, autoformalised | Decks grow with compute, and each passes its gate |
| 3. The physics kernel (P8 first) | Any 3D part, and codes proved against physics | Code formulas proved conservative, or flagged |
| 4. Systems | Assemblies across force, heat and current, dynamics and probability | Linked contracts between parts |
| 5. Lifecycle | Manufacture, inspection, field use and recall | An erratum reaches every affected design within a day |
| 6. Lean underneath | The kernel and the physics rules in Lean | A PASS is a Lean proof |

Stage 3 is the bet that lets Petra capture all design rather than one deck at a time. P8 tests that bet cheaply.

## 6. Build phases, P0 to P8

Each phase ends in a predicate someone can re-run, and a phase is done only when its predicate passes. Lanes of work that touch different files run in parallel, each on its own branch.

**Compute credits end on 2026-11-15** (ENGINE_MAP D5). The canary campaign in P0 and the breaker runs in P1 need the most compute, so they run first.

### P0. Usable, and the gap measured (2 to 4 days)

1. **One trunk.** Fast-forward `master` to `daedalus/mechanics-layer`. Commit `docs/principles.md`.
2. **Measure the gap.** Write the absurd-design generator and its seeded canaries for every steel kind and every domain. Run the generator, and publish the count of absurd designs that get PASS. That count is the baseline P1 must drive to zero.
3. **Package.** Add a `pyproject.toml` with a `petra` command, an Apache-2.0 licence, and a wheel that installs offline. Put Install, Quickstart and the steel deck at the top of the README. The README's sample output comes from a test, so it cannot go stale.
4. **Teach.** `petra kinds` and `petra new <kind>` print each kind's fields, units and a template, generated from the domain specs. Add `petra registry list [prefix]` with "did you mean" suggestions. Map common names such as A325 to their entries. Generate the language reference from the domain specs too.
5. **Make results actionable.** For every refuted check, report demand, capacity and utilisation in the user's units, the governing sub-check, and that check's own counterexample. `--json` carries all of it. Document the Python API, including MARGINAL.

**Done when** the scripted cold-start test passes on fresh agents with rotated, held-out briefs. Install takes one call from the wheel, offline. The steel job takes under 10 tool calls, with no digging through `dir()` or repr. The repair job reaches PASS from the output alone. The baseline is about 8 calls to install, 22 for the steel job, and three hand-computed repair tries (Appendix A).

**Result, 2026-11-07.** P0 was met in round 2. Each round ran two fresh agents on held-out briefs, outside the repository, with only the wheel. The outside judge found that every design the agents brought to PASS was buildable.

| Round | Install | Steel job | Repair | Library |
|---|---|---|---|---|
| 1 (sets A, B) | 1 pip call each | 7 and 8 calls. Both needed `--json` and a script to name the governing check. | 1 try after a hand calculation, and 4 tries that found tearout from AISC knowledge | `dir()` and repr, because no document shipped |
| 2 (sets C, D), after one fix round | 1 pip call each | 5 and 8 calls, read from the text report | 1 try each, chosen from the limit the report names | `petra docs api` alone, plus one inspection to learn why a utilisation was blank |

On seed 1, 1,711 of 15,600 generated designs PASS but cannot be built as drawn. That is 16% of all PASSes, and it is the gap baseline (`docs/absurd_gap.md`). Sixty-three of the 2,532 designs drawn by the deck's own samplers are in the gap, so the steel gate's "no false PASS" held for strength only.

On 2026-11-07 the work was published as `main` of the public repository [NooterraLabs/petra](https://github.com/NooterraLabs/petra). The local `master` branch was not fast-forwarded.

### P1. Safe (1 to 3 weeks)

1. **An exact geometric model for every steel kind.** Plates, bolts, beam and support become exact rational shapes. Petra generates the containment, non-intersection, edge and clearance obligations from that one model. The model covers all three fit classes: the beam side, the support side, and the beam against the support (flange clearance, cope needed). The same model later emits the CAD in P4.
2. **Loads and premises.** Add self-weight to the truss, and state its bracing assumption as a premise. Add a check that a conductor fits its terminal. Close the unconservative premises the code already admits, or turn them into UNKNOWN.
3. **The registry as a versioned, physical instruction set.** Values become intervals. Each entry gets a version, its source and an errata field, and the cable resistance fix is the first erratum. A recall query answers "which verdicts rest on this entry" (COMPILER §6, rows 3 and 4).
4. **Re-run the whole gate.** The whole gate is the twin elaborator, the planted faults, the 10,000 designs, and the breaker with canary recall of at least 90%, across every kind and domain.
5. **Coverage from the physics, not from the declared loads.** A flange force demands the panel-zone check only when the design declares a `panel_shear` load (`petra/models/steel/path.py`), so leaving the load out removes the check. The same question applies to a shear tee's flexibility and prying, and to the stiffened seat's plate and top angle, which no obligation names. Petra demands each mode a part's physics implies. If the design leaves out a load, the verdict is UNKNOWN and names what it needs, instead of a shorter list of checks.
6. **Say what was not checked.** An excused check and a mode the coverage table did not demand each print a line that names it and says why.
7. **What P0 found that the plan must decide.**
   - Five steel kinds and the bolt and uncertainty domains have no canary yet. Seed them from the gap examples, or recall cannot be measured.
   - The grammar does not say whether a support is a column or a girder, so "cope needed" cannot be judged.
   - Whether a part on a web-to-flange fillet counts as unbuildable decides 238 of the 1,711.
   - The gap count is compared only at a pinned seed and generator commit.
8. **The joint and demand classes the canary lane found.** A bolted joint's force model holds only while the plates stay clamped. A demand's stated capacity can sit above the level at which the design's own tests broke a part. The outside judge finds about 360 and 340 such designs respectively in 54,000 (seeds 1 to 3). Each becomes an obligation or an UNKNOWN.

**Interim result, 2026-11-07.** By then items 1, 3 and 6 and the canaries of item 7 were merged. The steel gap fell from 1,516 to 0 on seed 1, and it was 0 on the unseen seed 7. Canary recall on Petra before the fit checks was 51 of 53. The canary lane showed that the recall measure needed restating, as the next paragraph does.

**How recall is measured.** A canary hole is the set of modes that refuse a canary. The recall tooling treats those modes as discharged, and the search, with the outside judge as its oracle, must then find a PASS of that canary's kind and condition. The bar is at least 90% of canary holes, pooled. Each hole's budget is three over its cell's measured rate, and at least 600 designs. Recall per kind is reported but not gated, because one rare cell can fail a whole kind that has only one to three canaries. Recall by single mode is only reported, because it falls toward zero as the fit gaps close. Runs are compared by stream hash, not by seed and commit, because the generator samples the registry. flange_force has no canary because its grammar draws no parts, and the report says so (P5 draws more).

**Done when** the absurd-design count is zero on seed 1 and the held-out seeds 2 and 3, canary recall meets the bar above, and the full gate passes.

**Done on 2026-11-07, at commit `9ae6009`.** All eight items are merged. These results were measured on that tree:

| Check | Result | Report |
|---|---|---|
| Absurd-design gap, seeds 1, 2, 3 (18,000 each) | 0, 0 and 0. Stream hashes `47073143610e`, `291b3478e158`, `14fe2e487b13`. | `docs/absurd_gap.md` |
| Canary recall, pooled | 52 of 53 holes (98%). The miss is a double angle's support-side web width. | `docs/canary_recall.md` |
| Steel gate, 10,000 designs and 22 breaker runs | All decided, twins agree, 218 of 218 faults caught and named, 0 false PASS | `docs/steel_gate.md` |
| Test suite | 1,230 tests pass | |

P1 leaves these items open:

- Rotational flexibility of angles and end plates is not encoded.
- The stiffened seat's top-angle and plate welds are not checked, and the reason is printed.
- J10.8 and J10.9 are not credited.
- The hanger's J10.2 check rests on Eq. J10-3 as a premise.
- Fault clearing time is not checked.
- The joint's F_Z is taken as 0.
- The readout prints the enclosure utilisation, which can read above 1 on a PASS (gate design 01614). The gate's 3 FAIL-as-PASS against the generator's aim come from the same enclosure overstating a utilisation.
- 37 of 13,200 steel designs FAIL though the outside judge calls them buildable.

**Then publish.** The public repository came first, on 2026-11-07 (§8 item 2). PyPI comes next. **Done when** a networked fresh agent installs from public PyPI and passes the rotated briefs.

### P2. In the loop (1 to 2 weeks)

P2 delivers three things:

- A plain-data result from `petra.check(text)`, and a FAIL that names the input that moves it most and in which direction.
- An MCP server over the same API, using only the standard library, and a SKILL.md for coding agents. The check is already fast enough, at 0.07 s in process (measured).
- **The repair-and-minimise loop.** An agent or a search writes, checks and repairs a design until PASS, then pushes mass down under certified margins. The loop sets the benchmark's reference optimum. It is also the strongest breaker the project has, so every design it finds is also checked against CalculiX.

**Done when**, on held-out steel tasks, an agent reaches PASS within 10 checks on at least 80% of tasks (both targets are guesses to be tuned once, then frozen), and no design the optimiser finds fails the geometry model or the CalculiX spot check.

### P3. Petra Bench v0 (2 to 3 weeks)

- **Tasks** are requirements cards with the design left blank. The agent may call Petra, as an engineer calls a checker. The score is certified mass against the reference optimum, and FAIL or UNKNOWN scores zero. Hard tiers and hidden variants come from the generator.
- **Format.** Tasks are Harbor task directories with Petra in `tests/test.sh`, tagged on Hugging Face.
- **Baselines.** The project runs baselines for three or four frontier models.
- **Lift.** Each baseline also runs without Petra, with the same model and the same held-out tasks, and with Python and whatever the model knows of the specification. Checks that do not trust the agent grade both arms. They are Petra, the outside judge for buildability, CalculiX for strength, and a hand-checked sample. The numbers are the share of final designs that are safe and buildable, the share that the agent called safe but are not, mass against the reference optimum, and the checks and tokens needed to finish. If the arm without Petra scores as well, the bet in §3 is wrong. So a pilot of ten tasks per arm runs as soon as P1 is done.
- **Grader honesty.** Publish the breaker sample size and Petra's false-PASS count, split into arithmetic, coverage and validity (PRIOR_ART A2). Compare against an independent solver at equal compute (ENGINE_MAP §6.1). Run Petra over other graders' passing designs to count their false PASSes (BRAINSTORM X3).
- **Open specifications.** Publish specifications for the requirements card, the design and the certificate, with a written `.petra` semantics (E3).

**Done when** the tasks, baselines and grader numbers are public and reproduce with one command.

### P4. The designer, for connections (2 to 4 weeks)

The designer for connections has four parts:

- A prompt becomes a requirements card, with read-back (E4). The designer shows the card back in plain words, and nothing is signed until the user confirms it. An agent cannot sign for the user.
- Templates for the steel connection kinds, sized from the shapes table.
- The P2 loop, run to PASS and minimum mass.
- A build123d STEP file from the P1 geometry model, plus drawings, a bill of materials and the calculation package. All of them are bound to the design hash (E5) and checked by `petra verify --design`.

**Done when** prompts written by someone else each produce a package whose hash re-checks, whose solid model matches the design parameters, and which has no interference.

### P5. Coverage

P5 works through the rows of §4 in order. Each row ships only when it meets the coverage rule, including the absurd-design breaker.

### P6. Readers for other tools' files

Petra gets one reader per kind of data, never one per format. A reader fills fields of the requirements card or the design, and never produces a verdict.

| Kind | Example files | Fills | When |
|---|---|---|---|
| Parametric model | Connection schedules, IDEA Open Model, IFC objects | Geometry, material | After P1 |
| Design source | An exact CadQuery or build123d subset | The design | After P4 |
| Analysis deck | CalculiX `.inp` | Mesh, material, loads, supports | After coverage row 2 |
| Bare geometry | STEP | Geometry | Last, through a rational polyhedron inside the part |
| Requirements | SysML v2 | Claims, loads, environment | When a user asks |

**Done when**, for each reader, a design filled by the reader gets the same verdict as the same design written by hand, and every field the file cannot supply is printed as missing rather than guessed.

### P7. Trust upgrades

P7 puts units inside the certificate (E2) and adds twin elaborators for every deck. Last, it ports the kernel rules to Lean, and the Lean port re-checks the same JSON certificates. The Lean port comes last because the kernel is not where Petra has failed (§1).

**Done when** the Lean checker accepts every certificate in the gate corpus and rejects every planted fault, and every deck has a twin that agrees on the full gate.

### P8. The physics-kernel pilot (3 to 5 days, after P1, alongside P2)

P8 is the cheap test of stage 3 in §5. It takes one AISC formula, block shear on a plate (AISC 360-22 J4.3), and proves that inside its validity range the formula never claims more than a 2D lower-bound limit analysis allows.

- **Method.** The pilot builds a statically admissible stress field on a triangulated plate. It replaces the yield surface with an inscribed polygon, so the bound stays a lower bound. That makes the problem a linear programme, so its certificate is the kind R1 already checks (inferred). If the pilot needs a new kernel rule, it stops and reports, because the kernel changes only with the maintainer's approval.
- **The question it settles.** J4.3 takes the rupture terms at the tensile strength F_u, while a perfectly plastic limit analysis can use only a flow stress. So the expected outcome is mixed (guess). The yield terms are provable from physics, and the rupture terms rest on strain hardening and test data. Either outcome is a result. A proof makes the extreme version real. A flag names the premise the code rests on, and that premise goes into the registry with its source.

**Done when** the kernel proves the bound over a stated box of plate geometries, or the first configuration where J4.3 exceeds it is printed with the premise it rests on.

## 7. What the project stops doing

- **dira and its Studio stay frozen.** dira is the project's earlier, larger engine. Pieces move into Petra only when a phase needs them (ENGINE_MAP D1).
- **The five planning documents become background.** This plan sets the order of work, and the other documents keep their evidence.
- **No importer per file format, and no conversion between design representations** (PRIOR_ART never-do list).
- **No new physics before P1 passes.** The near term is cut to the smallest set of changes between the state on 2026-11-06 and a safe first verdict for a stranger, on the principle of the smallest change that solves the problem.
- **No claim of "zero false PASS" anywhere public** until P1's predicate holds.
- **No money, pricing or go-to-market sections.**

## 8. Decisions only the maintainer can make

1. **Publish after P1, or earlier as an alpha with the false-PASS list printed on the README.** **Decided on 2026-11-06 to publish after P1,** because a checker's first public fact should not be a false PASS.
2. **Where to publish.** **Decided on 2026-11-07:** the public repository `NooterraLabs/petra`, after P1 closed.
3. **The licence.** The licence is Apache-2.0, which ENGINE_MAP D3 made conditional on a data-licence audit. The full AISC shapes table cannot ship until that audit says how.
4. **The PyPI name.** `petra` is held by another account's project, which has no releases. **Decided on 2026-11-07:** Petra publishes as `petra-lang`. The command stays `petra` and the import stays `import petra`.
5. **The designer's name.** Daedalus is taken by the wave-physics engine.
6. **The last credits, which run to 2026-11-15.** **Decided on 2026-11-06** that they go to the canary campaign and the P1 breaker runs.
7. **Registry values from physics, or from specified limits.** `docs/frame.md` item 5 says registries are computed from physics, with wire resistance from resistivity and nominal area as the example. That derivation is what produced the low resistance. IEC 60228 specifies a maximum resistance, not an area, so physics alone cannot give the guaranteed value. **Decided on 2026-11-06** that a short list of specified limits may stand as constants. `docs/frame.md` item 5 and `docs/registry.md` now say so.
8. **How Petra is run in the open.** `docs/open_source.md` describes how Lean, Rocq, seL4, Ferrocene, code_aster and the open benchmarks are run, and sets out a playbook for Petra. **Decided on 2026-11-06:**
   - The docs are under CC BY 4.0 (`docs/LICENSE.md`).
   - Contributions are signed off under the DCO, with a pledge that Petra stays Apache-2.0 (`CONTRIBUTING.md`).
   - `TRADEMARK.md` sets how the name may be used. It reserves "Petra-checked" for checkers that pass the conformance corpus.

   The repository went public on 2026-11-07, so the name policy is open for comment. A CI check that refuses unsigned commits is still to be added.

## Appendix A. Cold-start test

On 2026-11-06, a fresh general-purpose agent with no context and no network got five jobs.

| Job | Result | Tool calls | Notes |
|---|---|---|---|
| Install | Only with a workaround | About 8 | pip cannot install a folder without `pyproject.toml` |
| Steel shear tab, W16x31, 3 bolts, 45 kip | FAIL, 2 of 17 refuted | About 22 | Copied an example almost whole. Needed beam grade, support, edge distances and a signer the brief did not give. |
| Cable, 2.5 mm2, 30 m, 16 to 20 A | FAIL, 4 of 5 refuted | About 6 | Needed a protective device and a fault current. Printed no drop or temperature figures. |
| Library | Worked | About 6 | Found per-claim access by inspecting objects |
| Repair to PASS at 60 kip | Third try | About 6 | Output gave no demand, capacity or direction to change |

While repairing, the agent tried 5, 6 and 8 rows and got PASS on all three. That is how the first false PASS was found.

The agent ranked three fixes:

1. an install path
2. a generated language reference, with a registry listing and common names
3. failure output with demand, capacity, the governing sub-check and full JSON

The agent also noted that the shear tab takes the full bolt-line distance as eccentricity with the elastic method. That choice is conservative and documented in `docs/steel_connections.md` §7, but not documented for users.

## Appendix B. Research sources

A research agent read these sources on 2026-11-06. "Snippet" means the agent saw only a search excerpt.

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

Two independent reviewers attacked the first draft. Nobody has reviewed the rewrite that followed, which brought a new P1, a new coverage order and new predicates. Both reviewers ran on the same model as the author, because this setup runs every role of pstack, the agent tooling used here, on the parent model. So the panel had no model diversity. Findings that both reviewers raised carry the most weight.

**Raised by both reviewers, and acted on:**

- The fit fix was too narrow. Five more false PASSes reproduced (§1). P1 now builds one geometric model per kind instead of writing a fit rule per kind.
- The worked-example judge already existed and could not see the gap.
- The P0 predicate could pass with the gaps still open. Safety is now P1's own predicate, with canary recall.
- The claim that Petra "grows with compute" had nothing behind it. §5 now separates compute engines from adoption.
- The discrete frequency check was oversold. It certifies the lowest mode of the model only.

**Raised by one reviewer, and acted on.** Reviewer A raised three findings:

- The registry rule "guaranteed, never nominal" would condemn AISC's calibrated nominal values. Per-check interval ends replaced it.
- An offline install needs a wheel, and the shapes table holds 30 W shapes.
- The truss has no self-weight.

Reviewer B raised five:

- The benchmark needed a score beyond PASS, a decision on checker access, an independent oracle, and an attack on outside graders.
- The designer needed read-back before signing, and P4 should cover connections only.
- Coverage rows that open families should come earlier, with estimates.
- Credits end on 2026-11-15, and gating the phases in series wasted parallel lanes.
- The agents-first bet needed a measure and a date.

**Considered and kept as is:**

- Electronics as the second deck. It is now named as the strongest candidate to run alongside row 2, not moved ahead of it.
- Copyright of standards tables. Single specified limits per size, such as IEC 60228 maximum resistances, are values. Rating tables stay out, and current ratings stay derived, with their judged coefficient disclosed.

**Left to the maintainer.** Reviewer B's point that taking IEC 60228 maxima conflicts with `docs/frame.md` item 5 (§8, decision 7).

**Dismissed.** None. Every finding had a concrete basis.
