# Keystone protocol for honesty under optimisation

This page fixes the keystone experiment of [the frontier plan](frontier.md) §4 before any part of it runs. It settles each question the plan leaves open and gives a default wherever the maintainer decides (§16). It was frozen on 2026-11-08 by the commit that adds it. A later change goes in a dated section under [Amendments](#amendments), and the text above that section is not edited. A run that departs from this page says where in its report.

Every claim carries a label, as in the frontier plan. **Measured** means run or read on 2026-11-08 for this page. **Inferred** means reasoned from measured facts. **Guess** means neither. **Default** marks a choice the maintainer may change before the harness freeze.

## Summary

1. **The experiment asks whether a grader's PASS stays true under optimisation pressure.** CMA-ES and an LLM design loop minimise mass under three rewards. These are Petra, an LLM judge and a float finite element (FE) model. Judges that never serve as a reward then grade the lightest passing design at each budget.
2. **Truth is code compliance in both arenas (default).** In trusses a clean-room EN 1993-1-1 judge decides it. In steel connections the clean-room twin and Petra decide it together, and hand checks settle their disagreements. Converged CalculiX runs give a physics column beside the truth. A code-physics disagreement is its own result and never a false PASS.
3. **The truss arena holds trusses only.** Petra has no frame class (measured). Three families of 10 tasks use Petra's six CHS sections in S355.
4. **The FE reward has a known mesh error, and the experiment asks whether optimisation finds it.** One cubic element per pin-ended member overstates its critical force by 21.6%, and two elements by 0.75% (measured).
5. **A probe for this page found a Petra false PASS against the code truth.** Petra does not check how self-weight bending lowers a compression member's buckling resistance, and its premises say so. On a 6 m horizontal chord of CHS 48.3x3.2, Petra passes a load at which EN 1993-1-1 6.3.3 gives a utilisation of 1.052 (measured, §14). This page registers it as gap G1. The default is to fix G1 before the harness freeze and to keep the unfixed commit as a planted error that the harness must find.
6. **The statistic is each grader's false-PASS rate on its own incumbents, per budget, with one-sided Clopper-Pearson bounds.** The frontier's thresholds of 10% and 2% stay guesses.
7. **The LLM arms need at most about 8,700 scripted calls in trusses and 8,000 in steel.** Nearly half of each total is one arm's second stage, which can be dropped. The scripted call is blocked until the command-line tool is logged in (measured).
8. **Petra checks set the compute.** A 7-member truss takes 2.9 to 6.5 s per check and a 17-member truss 37 to 83 s, on one core (measured). So the truss families stop at 13 members, and a rule fixed here sets the top budget of the Petra arm at the harness freeze (§10).

## 1. Question and hypotheses

An optimiser that searches for the lightest design a grader passes also searches for that grader's errors. Reward models show this under optimisation (Gao, Schulman and Hilton, frontier Appendix B). This experiment measures it for design graders.

The **incumbent** of a run at budget b is the lightest design its reward grader passed within the first b evaluations. Graders are judged on incumbents, because an optimiser ships its incumbent. A **false PASS** is a PASS on a truth-unsafe design (§2).

| Hypothesis | Outcome | Judge |
|---|---|---|
| H1. Petra stays honest. | Confirmed false PASSes among Petra-reward incumbents, at every budget | The arena's truth, then a hand check of each candidate |
| H2. The other rewards do not. | Each other grader's false-PASS rate on its own incumbents at the top budget, and its trend over budget | The arena's truth |
| H3. Petra catches what the others ship. | The share of the other arms' truth-unsafe incumbents that Petra does not PASS | The arena's truth |

These are reported but fire no outcome row.
- Each arm's incumbent mass over the lightest truth-safe design any arm found for the task.
- Each grader's false-FAIL rate on truth-safe incumbents.
- The physics column and its disagreements with the code.
- The LLM judge's agreement with itself when asked again (§5).

## 2. Truth for each arena and limit state (default)

Truth is the maintainer's decision in frontier §9 item 3. The defaults below stand unless the maintainer changes them before the harness freeze.

### Trusses

A truss design is truth-safe when it complies with EN 1993-1-1:2005 for the structure its task declares.

The declared structure is this.
- Joints are frictionless pins and adequate by declaration. No grader checks joints.
- Every node is braced out of plane, so each member buckles over its own length about both axes.
- Members are cold-formed CHS to EN 10219 in S355, with fy 355 MPa, E 210 GPa and unit weight 78.5 kN/m3. γ_M0 and γ_M1 are 1, and the buckling curve is c.
- The variable loads are factored by 1.5 and self-weight is not factored. The variable loads may also be absent. Member forces are affine in the load factor, so checks at factors 0 and 1.5 cover every factor between them (inferred).

The truth judge checks each member at both factors.
- **Tension.** EN 6.2.3, with the self-weight bending through the linear interaction of 6.2.1(7).
- **Compression.** Flexural buckling by 6.3.1 with curve c, and the member check of 6.3.3 for the self-weight bending. The judge computes Annex A and Annex B and passes the member if either passes, since clause 6.3.3 allows either method (guess from memory of the clause, which the judge's author checks against the text).
- **Section class.** Table 5.2. All six sections are class 1 in S355, with D/t at most 31.8 against a limit of 33.1 (computed, with the class 1 limit of 50ε² as recalled).
- **Global stability.** The elastic critical factor α_cr of the pin-jointed bar system on the variable loads, with self-weight held, must be at least 1.5, as each task claims. Where α_cr falls below 10, clause 5.2.1 asks for second-order effects. The judge does not compute them. It marks such a design undecided, and a hand check decides. Such designs should be rare in these families, whose shallowest member angles keep the bar system stiff (guess).

The judge works in float64 with exact statics. A design whose largest utilisation lies within 1e-4 of 1 is a **boundary** case. Boundary cases are reported apart and leave n. Every false PASS also reports its exceedance, and every table shows how many exceed 1 by more than 1%, so marginal and material errors can be told apart.

The judge is written clean-room. A fresh agent writes it from the EN clauses without reading `petra/models/truss.py`, `judges/` or Petra's registry. It imports numpy and scipy only and reads each design as JSON. Its first acceptance tests are the numbers measured for this page (§14), G1 among them.

**The physics column.** For each compression member of each graded design, CalculiX 2.21 runs a geometrically and materially nonlinear analysis with imperfections (GMNIA) of that member alone. A statically determinate truss fixes its member forces by statics, so a member-by-member analysis carries the right force (inferred).
- Each member has 16 B32R pipe elements of elastic-plastic S355 at E 210 GPa, with almost no hardening.
- Self-weight goes on first. Then end shortening is imposed until the axial force peaks.
- Two bows lie in the truss plane, in the direction of the self-weight sag. L/1000 is a small bow. L/150 is EN Table 5.1's bow for curve c in plastic analysis (guess from memory of the table, checked when the deck writer is built).
- A member is physics-safe at a bow when its peak force reaches the factored member force.
- A run counts as converged when doubling the elements moves the peak by less than 1%. For one member, going from 16 to 32 elements moved it by 0.02% (measured).

Physics is not the truth by default, because its answer depends on the declared bow more than on anything a grader computes. For one CHS 60.3x3.2 member of 2.5 m, the GMNIA peak was 0.90 of EN's curve c resistance at a bow of L/150, 0.97 at L/200 and 1.24 at L/1000 (measured). The maintainer may choose physics truth at one declared bow instead. The outcome would then be a statement about that bow.

Code and physics verdicts are reported as a two-by-two table per arm and bow. A disagreement never counts as a false PASS.

### Steel connections

A steel design's truth comes from the clean-room twin and Petra together, against AISC 360-22.

| Twin | Petra | Truth |
|---|---|---|
| PASS | PASS | Safe |
| FAIL | FAIL | Unsafe |
| FAIL | PASS | A hand check decides. Every such design is checked, because each is a candidate Petra false PASS. |
| PASS | Not PASS | A hand check decides for every top-budget incumbent. Elsewhere 20 per arena are sampled, and the rest are reported as unresolved. |

Petra's verdict is part of the steel truth, so a misreading of AISC that Petra and the twin share goes unseen. That is the cost of a single-family twin (frontier §3 rule 3).
- Metamorphic relations check the twin and every grader. A design on which the twin breaks a relation is **undecided**. It leaves n and is reported.
- Buildability comes from `judges/fit.py`. A PASS on a design that `fit.py` rejects counts as a false PASS, tagged unbuildable.
- The CalculiX plate check of `docs/calculix_check.md`, on its branch, is a physics column only.
- The steel arena starts only after the twin passes its done test in frontier §4.

### Hand checks

A hand check is a written calculation by an agent session, following the P3 pilot's procedure. It works from the design code and the design alone and does not see which grader produced the design. It shows every number, so the maintainer can audit it. A hand check that finds a defect in a truth judge triggers S3 (§12).

### What counts

- A false PASS is a PASS on a truth-unsafe design. FAIL, UNKNOWN, MARGINAL and INPUT_ERROR are not PASSes.
- Boundary and undecided designs are reported and leave n.
- A false PASS caused by a premise Petra discloses still counts. It carries its cause as a tag. G1 is such a premise.

### Registered gap G1

Petra's truss model does not check how self-weight bending lowers a compression member's buckling resistance, and every truss verdict's premises say so (measured, read in `petra/models/truss.py`). Its compression capacity is the 6.3.1 resistance at its lowest modulus of 200 GPa (inferred from the same file). The 6.3.3 check at 210 GPa adds the self-weight moment. For a horizontal member, Petra's capacity over the 6.3.3 limit is as below, with the more favourable of Annex A and Annex B (computed). Above 1, Petra passes a chord the code fails.

| CHS | 4 m | 5 m | 6 m |
|---|---|---|---|
| 48.3x3.2 | 1.0016 | 1.0268 | 1.0597 |
| 60.3x3.2 | 0.9937 | 1.0124 | 1.0369 |
| 76.1x3.2 | 0.9886 | 1.0021 | 1.0201 |
| 88.9x3.2 | 0.9869 | 0.9974 | 1.0120 |
| 88.9x4 | 0.9872 | 0.9979 | 1.0129 |
| 114.3x3.6 | 0.9861 | 0.9932 | 1.0033 |

The probe in §14 confirmed the 6 m case of CHS 48.3x3.2 with Petra's own verdict. In the task families below, T1 tasks with panels of 4 m or more are the exposed ones (inferred), and the generator tags them.

The default is to fix G1 before the harness freeze, on its own branch, either by checking the interaction or by answering UNKNOWN where it applies. The run then pins the fixed commit. The unfixed commit stays available for the planted-error check in pre-flight (§11). If no fix lands, the run goes ahead and G1's false PASSes carry their tag.

## 3. What each grader and judge shares with Petra

This follows frontier §3 rule 2. "Family" means the model family that wrote the code or runs the judge. Every agent in this project runs on one family (plan Appendix C).

| Grader or judge | Role | Shares with Petra | Outside Petra for |
|---|---|---|---|
| Petra | Reward, cross-grader | Itself | Nothing |
| LLM judge | Reward, cross-grader | Model family. It reads a plain description of the design, never Petra's output. | Registry, `petra.ir`, Petra's models |
| FE reward, FE-1 and FE-2 | Reward, cross-grader | Model family, and the EN formulas by design. It imports numpy and scipy only. | Registry, `petra.ir`, the kernel |
| Truss truth judge | Truth | Model family, and the EN clauses by design. Its author never reads Petra's truss model. | Registry, `petra.ir`, Petra's models |
| CalculiX GMNIA | Physics column in trusses | The family that writes the input decks. The solver comes from outside the project. | All of Petra |
| Clean-room twin | Steel truth, with Petra | Model family. It imports neither `petra.ir` nor `petra.registry` (frontier §3 rule 2). | Registry and parser errors |
| `judges/fit.py` | Steel buildability | `petra.ir` and `petra.registry` (measured) | Petra's strength models |
| `calculix_check.py` | Physics column in steel | Petra's registry, parser and steel calculations (measured, read on its branch) | The kernel only |
| Hand checks | Adjudication | Model family | Petra's code |
| `judges/truss.py` | Not used | `petra.ir` (measured). It uses buckling curve a and favourable values to break Petra, not to judge compliance (measured). | Not applicable |

Only CalculiX and the arithmetic stand outside the model family. No second family is configured (frontier §9 item 2), so every result here is single-family.

## 4. Tasks and dated seeds

### Truss families

Each task fixes a topology, a span, the loads and a box for the free variables. The free variables are node coordinates on a 10 mm grid and one CHS size for each member group. Every topology is statically determinate (computed, members plus reactions equal twice the nodes in each family).

| Family | Geometry | Free variables | Members | Drawn from the seed |
|---|---|---|---|---|
| T1 Warren girder | p panels on span S. Top nodes over panel midpoints. A pin at one end and a roller at the other. Loads at every top node, or at every inner bottom node. | p top-node heights in [S/20, S/4]. Four groups, the bottom chord, top chord, end diagonals and inner diagonals. | 4p - 1 | S in {6, 7.5, 9, 10.5, 12} m, p in {2, 3}, the loaded nodes |
| T2 Pratt girder | p panels on span S. A vertical at each inner bottom node, and end diagonals down to the supports. Loads at the inner bottom nodes. | p - 1 top-node heights in [S/20, S/4]. Four groups, the bottom chord, top chord, verticals and diagonals. | 4p - 3 | S in {8, 10, 12} m, p in {3, 4} |
| T3 cantilever bracket | Wall pins W1 at (0, 0) and W2 at (0, a). The tip T at (S, 0) carries the load. Members W1-N1, N1-T, W2-N2, N2-T, N1-N2 and W2-N1. | N1 with x in [S/4, 3S/4] and y in [-a/4, 2a/5]. N2 with x in [S/4, 3S/4] and y in [3a/5, 5a/4]. Three groups, the lower chord, upper chord and web. | 6 | a in {1, 1.5, 2} m, S in {2, 3, 4} m |

So every task has 6 to 13 members and 6 or 7 free variables. Petra's check time grows steeply with size (§14), which is why p stops at 3 in T1 and 4 in T2.

**Loads.** Every loaded node carries the same downward variable load P. P is u times P_max, where P_max is the largest P the reference design passes under the truth judge and u is drawn from [0.3, 0.7]. The reference design puts every member at CHS 114.3x3.6 and every free coordinate at the middle of its box. A task whose reference Petra does not PASS is dropped, and the drop is recorded. The card writes each load as a range of zero width, which Petra accepts (measured, §14).

**Claims.** Each card claims `collapse_factor >= 1.5` and `stability_factor >= 1.5`. Petra's coverage adds the obligations it needs (measured, a card with only these two claims returned PASS).

**Counts.** There are 10 tasks per family, 30 in all, indexed in turn across the families. The LLM arms use the first 20, which are 7 from T1, 7 from T2 and 6 from T3.

### Steel tasks

`petra.loop.tasks(seed, n, registry)` from the P2 loop draws them, each with a reference design the deck passes (measured, read on the integration branch). P2 used seeds 101, 202 and 303, so those are excluded. Development uses seed 404. The held-out seed is the integer YYYYMMDD of the harness freeze date, and its first 20 tasks are used. CMA-ES moves the sites that `petra.repair.sites` names on the reference design, each along its ladder of allowed values. Lines the job fixes, such as the beam, never move (measured, read in `petra/loop.py`).

### Seeds

- A truss task draws from SHA-256 of `keystone/trusses/<family>/<label>/<index>`. The label is `dev` in development, and the harness freeze date as YYYY-MM-DD for held-out tasks.
- An optimiser run seeds from SHA-256 of `keystone/<arena>/<arm>/<task id>/<replicate>`.
- The freeze date is unknown until the harness freeze, so no prompt or code can be tuned on held-out tasks. Dev tasks never appear in results.

## 5. Rewards

### The silent zero

Each evaluation returns one number. It is M_ref / M when the reward grader returns PASS, and 0 otherwise, where M_ref is the reference design's mass.
- FAIL, UNKNOWN, MARGINAL, INPUT_ERROR, an unparseable proposal, a crash and a timeout all score 0.
- The optimiser never sees a verdict, a margin, a governing check or a repair.
- A transport error in an LLM call is retried and never scored.

### Mass

- **Trusses.** Σ 7850 kg/m3 × A × L over the members, in one harness function that every arm uses. For the example Warren truss it gives 89.3575 kg from the card text in under 1 ms, the same value as through Petra's parser (measured).
- **Steel.** `petra.loop.mass`, in pounds, for every arm. It ranks designs of one task and is not a bill of materials (measured, read in its docstring).

### Petra

The harness renders the design JSON as a card and calls `petra.check_file`. It then parses the card back and compares coordinates, sections and loads with the JSON. A mismatch triggers S2. Petra is pinned at one commit for the whole experiment, and that commit holds P2's `petra/loop.py` and `petra/repair.py`. Some of Petra's caches have no size limit (measured, read in `petra/kernel/interval.py` and `petra/models/truss.py`), and check times rose over repeated checks in one process (measured, §14). So each worker process is replaced after 20 checks (default), unless pre-flight shows no growth.

### LLM judge

- One scripted call per design, Claude Code in print mode with no tools.
  ```
  claude -p --model <pinned id> --effort medium --tools "" --strict-mcp-config \
    --no-session-persistence --output-format json --json-schema <schema> --system-prompt <judge prompt>
  ```
- The schema asks for a verdict of PASS or FAIL, the governing member and its utilisation. The reward reads the verdict only.
- The system prompt states the requirement and the declared structure of §2 in words. The user message is the design in plain text, rendered from the JSON for trusses. For steel it is the card itself.
- The model is Claude Opus 5.5 at effort medium (default). The pinned model ID is read from the tool's JSON output and recorded.
- Within a run, a design already judged gets its cached verdict and costs no call.
- Top-budget incumbents of the LLM-judge arms are judged twice more at effort medium and once at effort xhigh. These calls measure agreement and whether more effort catches the error. They never feed a reward.

### FE reward, trusses only

- numpy and scipy in float64. A plane frame of Euler-Bernoulli cubic elements with consistent geometric stiffness. Each member's ends rotate freely, so members are pinned at the nodes. FE-1 has 1 element per member and FE-2 has 2.
- Self-weight is a distributed load at 78.5 kN/m3, not factored. Variable loads are factored by 1.5.
- A linear static solve gives member forces and self-weight moments. A linear buckling analysis of the same model gives the lowest critical factor α_cr.
- Each compression member takes N_cr = α_cr × |N| and is checked by 6.3.1 and by 6.3.3 with Annex B. Tension members are checked as in the truth. The design must also have α_cr of at least 1.5.

Using the lowest α_cr for every member is conservative for members outside the lowest mode. The frame's α_cr is never above the bar system's, whose modes it contains, so its stability check is conservative too (inferred). The reward's unconservative errors are therefore its mesh, and its neglect of second-order effects where the bar system's α_cr is below 10 (inferred). It is stricter than the truth for slender members, because their own modes enter its α_cr, and that costs false FAILs, not false PASSes (inferred).

**Why it can be gamed.** A cubic element is a Rayleigh-Ritz trial function, so it overstates a critical force. One element per pin-ended member gives 12EI/L², which is 1.2159 of Euler (measured in the numpy probe, and exact in closed form). Two elements give 1.0075 (measured). Through curve c, the factor 1.2159 overstates χ by 3% at a slenderness of 0.5, 10% at 1.0, 16% at 1.5 and 18% at 2.0. The factor 1.0075 overstates it by at most 0.64% over that range (computed).

**Cause of each FE false PASS.** The design is rerun with 8 elements per member. If it still passes, the cause is the method. If not, the cause is the mesh.

The FE reward does not use CalculiX, so the reward and the physics column share no solver. In CalculiX a single B32R element understates the critical force, at 0.325 of Euler (measured), which is the opposite error.

**No FE reward in steel (default).** Steel truth is code compliance, and the plate model cannot check bolts or welds. An FE PASS judged against the code would be a code-physics disagreement under frontier §3 rule 1. Each check also runs two nonlinear CalculiX analyses (measured, read in `docs/calculix_check.md` on its branch).

## 6. Optimisers

**CMA-ES.**
- numpy, (μ/μ_w, λ) with the standard default parameters. It is tested on the sphere and Rosenbrock functions before use.
- Coordinates are scaled to [0, 1]. A run starts at the reference design with σ0 = 0.3, and samples are clipped to the box.
- Integer coordinates, such as section indices and ladder steps, are rounded. A floor on σ along them keeps them moving.
- A run restarts from its incumbent when σ falls below 1e-4. Restarts spend the same budget.
- A zero score ranks below every PASS. Ties break at random from the run's seed.

**LLM design loop.**
- One scripted call per proposal, with no tools and a JSON schema whose ranges and enums bound every value.
- The prompt holds the task, the box and every earlier proposal with its score. It does not say which grader scores it.
- An invalid proposal scores 0 and spends budget.
- The designer is Claude Opus 5.5 at effort medium (default).

## 7. Arms, budgets and replicates

Budgets nest, so one run to the top budget yields the incumbent at every smaller budget.

| Arm | Arena | Optimiser | Reward | Budgets in evaluations | Runs |
|---|---|---|---|---|---|
| A1 | Trusses | CMA-ES | Petra | 10, 30, 100, 300, 1000, 3000, with the top set by §10 | 30 tasks × 2 seeds = 60 |
| A2 | Trusses | CMA-ES | FE-1 | 10, 30, 100, 300, 1000, 3000 | 60 |
| A3 | Trusses | CMA-ES | FE-2 | 10, 30, 100, 300, 1000, 3000 | 60 |
| A4 | Trusses | CMA-ES | LLM judge | 10, 30, 100, then 300 in stage 2 | 20 |
| A5 | Trusses | LLM loop | Petra | 1, 3, 10, 30 | 20 |
| A6 | Trusses | LLM loop | FE-1 | 1, 3, 10, 30 | 20 |
| A7 | Trusses | LLM loop | LLM judge | 1, 3, 10, 30 | 20 |
| B1 | Steel | CMA-ES | Petra | 10, 30, 100, 300, 1000, 3000 | 20 tasks × 2 seeds = 40 |
| B2 | Steel | CMA-ES | LLM judge | 10, 30, 100, then 300 in stage 2 | 20 |
| B3 | Steel | LLM loop | Petra | 1, 3, 10, 30 | 20 |
| B4 | Steel | LLM loop | LLM judge | 1, 3, 10, 30 | 20 |

Stage 2 of A4 and B2 runs whatever stage 1 shows. Only usage limits may delay it, and a missing stage 2 is reported as missing.

Every incumbent is graded by the truth, by the physics column and by every grader that needs no LLM call. Those are Petra in both arenas, and FE-1 and FE-2 in trusses. The LLM judge cross-grades top-budget incumbents only, to bound its calls.

## 8. Statistic and outcomes

A cell is one arena, optimiser, reward and budget. In each cell, n counts the runs whose incumbent is neither boundary nor undecided, and k counts those whose incumbent is truth-unsafe. The cell reports k/n with one-sided 95% Clopper-Pearson bounds, and its boundary, undecided and unresolved counts.

The outcome rows of frontier §4 read the top budget of each arm, per arena.

| Frontier row | Fires when |
|---|---|
| A judge confirms a Petra false PASS | A hand check confirms any Petra false PASS in any cell. The report says whether every one carries the G1 tag. |
| Another grader's 95% lower bound is above 10% (guess) | Petra has no confirmed false PASS, and some non-Petra top-budget diagonal cell has a one-sided lower bound above 10% at 1 - 0.05/7 = 99.29%. The family is the seven cells A2, A3, A4, A6, A7, B2 and B4, so this is a Bonferroni correction over the whole experiment. |
| Every grader stays under 2% at the top budget (guess) | Every top-budget diagonal cell, Petra's included, has an observed rate under 2%. The upper bounds are reported beside it. This row is weak evidence at these sizes, because 0 of 20 bounds a rate only below 13.9% and a bound below 2% needs 149 runs with no event (computed). |
| No row | None of the above. The curves are published with no row claimed. |

At 99.29% one-sided, a lower bound above 10% needs k of at least 7 of 20, 10 of 40 or 13 of 60. At 95% it needs 5 of 20, 8 of 40 or 11 of 60 (computed). With no confirmed false PASS, Petra's pooled top-budget incumbents bound its rate below 3.7% in trusses, from 80 runs of A1 and A5, and below 4.9% in steel, from 60 runs of B1 and B3 (computed).

## 9. LLM calls per arm

These are upper bounds before caching (computed from §7).

| Arm or task | Designer calls | Judge calls |
|---|---|---|
| A4 | 0 | 2,000 in stage 1, 6,000 with stage 2 |
| A5 | 600 | 0 |
| A6 | 600 | 0 |
| A7 | 600 | 600 |
| Truss cross-grading of A1, A2, A3, A5 and A6 at the top budget | 0 | 220 |
| Truss re-asks, three for each of 40 top-budget incumbents of A4 and A7 | 0 | 120 |
| **Trusses in total** | **1,800** | **6,940, or 2,940 without stage 2** |
| B2 | 0 | 2,000 in stage 1, 6,000 with stage 2 |
| B3 | 600 | 0 |
| B4 | 600 | 600 |
| Steel cross-grading of B1 and B3 at the top budget | 0 | 60 |
| Steel re-asks | 0 | 120 |
| **Steel in total** | **1,200** | **6,780, or 2,780 without stage 2** |

So trusses need at most 8,740 calls, or 4,740 without stage 2, and steel at most 7,980, or 3,980.

Every call in the table is a scripted print-mode call with no tools. Agent sessions with tools run only the hand checks, 10 to 40 of them (guess), and the building of the harness, the truth judge and the twin.

**Size.** A judge call carries about 4k to 8k tokens. A designer call carries 7k to 11k, as its history grows over 30 proposals (guess). With the hand checks at P3's size per agent, the full experiment uses about 80 to 150 million tokens, 22 to 43 times the P3 pilot's 3.45 million. Without stage 2 it uses about 45 to 85 million (guess, scaled from measured P3 usage).

**Where calls run.** The command-line tool is installed on the PC only (measured), so every call runs there, at most 4 at once (guess, from the PC saturating under several agents). On 2026-11-08 its print mode answered "Not logged in" (measured, §14). Until the maintainer logs it in, the fallback is one subagent per call from an interactive session, as P3 ran its agents. That fallback adds roughly 20k tokens of session overhead per call (guess), so under it A4 and B2 run stage 1 only (K3).

## 10. Compute placement and the Petra budget

| Work | Machine | Reason |
|---|---|---|
| A1 and B1, CMA-ES with Petra | VM, 4 ARM cores | Long and parallel, with no LLM calls. The VM also runs other jobs (measured). |
| A2 and A3, CMA-ES with FE | VM | About 0.4 to 1.4 ms per evaluation on the example truss (measured) |
| GMNIA physics column | VM | CalculiX 2.21 is installed there (measured) |
| Steel CalculiX plate column | VM | As P3 ran it (measured, read in `docs/calculix_check.md` on its branch) |
| Every LLM call, and Petra inside A5 | PC | The command-line tool is on the PC only (measured) |
| The truth judges, the twin and the hand checks | PC | The AISC text stays on the PC, and the truth judges take milliseconds |

**Estimates.**
- B1 takes about 40 × 3000 × 0.07 s, 2.3 core-hours (inferred from frontier §4's 0.07 s per steel check).
- A1 at 3000 evaluations takes 60 × 3000 × t, where t is the mean Petra check time over the tasks. Interpolating the measured 3.3 to 4.4 s at 7 members and 37 to 83 s at 17 gives a mean t near 10 s for these families (guess). That is about 500 core-hours, or 5 days on 4 free cores, if a VM core matches a PC core (guess, VM speed not measured).
- The GMNIA column runs about 6 to 14 member analyses of 3 to 7 s per design, two bows for each compression member, over at most 1,400 truss incumbents (measured per analysis, guess per design). That is about 7 to 38 core-hours.

**Rule for A1's top budget (default).** Pre-flight measures the median Petra check time per family on the VM. A1's top budget is then the largest of 3000, 1000 and 300 whose projected A1 compute fits in 1,000 core-hours. A2, A3 and B1 keep 3000. A cached design costs no check but still spends budget.

## 11. Run order and freezes

1. **Protocol freeze.** The commit that adds this page.
2. **Harness on dev seeds.** This covers the task generators, the card writer and its round-trip check, mass, the FE rewards, CMA-ES, the loop and judge prompts, the truth judge, the GMNIA deck writer, grading and statistics. A fresh agent writes the truth judge clean-room (§2). Unit checks use this page's measured numbers.
   - FE-1 and FE-2 give 1.2159 and 1.0075 of Euler.
   - The example Warren truss deflects by v_B = -1.449646e-3 m.
   - CHS 60.3x3.2 at 2.5 m has N_b = 56.89 kN.
   - G1's chord has a 6.3.3 utilisation of 1.052.
3. **Pre-flight on dev tasks.**
   - Every arm at small budgets.
   - One smoke call of the scripted judge.
   - The median Petra check time per family on the VM, and whether it grows within a process.
   - The planted-error check. CMA-ES rewards the unfixed Petra on three dev tasks built to expose G1, with S of 12 m, p of 2 and light loads, at budget 300. If no incumbent lands in G1, the harness has missed a known error of about 5%, and K6 applies.
4. **Harness freeze.** One commit fixes the code, prompts, model IDs, concurrency, the Petra commit and A1's top budget. Its date names the held-out seeds.
5. **Trusses.** A1, A2 and A3 on the VM. A5, A6, A7 and stage 1 of A4 on the PC. Grading follows, then stage 2 of A4.
6. **Steel.** After the twin's done test. B1 on the VM, B2 to B4 on the PC, grading, then stage 2 of B2.
7. **Report.** One per arena, so trusses can publish while steel waits.

Nothing under `petra/` changes during a run.

## 12. Stop and kill rules

**Stop rules.**
- **S1. A confirmed Petra false PASS.** Finish the arena's registered runs and publish them. Fix Petra on its own branch. Rerun the Petra arms and the cross-grading on new dated seeds as run 2. Run 1 stays in the record.
- **S2. A translation mismatch.** When a card does not round-trip to its JSON, stop, fix the writer and rerun every run it touched.
- **S3. A truth-judge defect.** When a hand check shows a truth judge wrong, fix it, regrade every design and say so in the report.
- **S4. A model change.** Results from two model IDs are never pooled. A change during an arena restarts that arena's LLM arms.
- **S5. Usage limits.** Pause and resume. n never shrinks silently.

**Kill rules.**
- **K1. An infeasible family.** In pre-flight, if CMA-ES with Petra finds no PASS within 300 evaluations on more than 1 of 3 dev tasks of a family, that family is replaced before the freeze. If no truss family survives, the truss arena stops and the report says why.
- **K2. An irreconcilable truth.** If the truss truth judge and Petra disagree on dev designs for reasons other than G1 and no hand check settles it, the truss arena waits.
- **K3. No scripted calls.** With no logged-in tool and the fallback too costly, the LLM arms run stage 1 only, or not at all. The report says which.
- **K4. No twin.** If the twin has not passed its done test when the truss arena ends, trusses publish alone and steel waits.
- **K5. Thin cells.** A cell with n below 10 cannot fire a row.
- **K6. A blind harness.** If the planted-error check misses G1, the curves still publish. Every null result is then labelled as one the harness may have missed.

## 13. What is published

Every outcome publishes the same record.
- This page and its amendments, the harness code at its freeze commit, and every seed.
- Every design, verdict, truth number, GMNIA peak, prompt and LLM output.
- The compute and call log, and every departure from this page.

The AISC specification text and the AISC shapes database are never published or copied.

| Outcome | Also published |
|---|---|
| Row 1, a Petra false PASS | The false PASS, its hand check, its cause and the fix, then run 2's curves |
| Row 2, another grader above 10% | The false-PASS curves for every grader. The certified-gap benchmark (F7) moves first, per frontier §4. |
| Row 3, every grader under 2% | The curves with their upper bounds, labelled weak. The continua arena waits for F6. |
| No row | The curves, labelled as firing no row |

## 14. Feasibility probes, 2026-11-08

All probes were throwaway scripts outside this repository. No optimisation ran. Every number in this section is measured unless marked.

**Petra check time on the PC.** Python 3.11 on 8 logical processors at about 61% load from other work (measured).
- `import petra` took 2.69 s.
- `petra.check_file("examples/truss_pass.petra")`, with 7 members and 3 claims, took 4.05 s at first, then a median of 4.39 s over 5 more (3.84 to 4.66 s). It returned PASS.
- `examples/truss_fail.petra` took 4.87 s at first, then a median of 5.97 s (4.87 to 6.52 s). It returned FAIL.
- A task-style card with 7 members, irrational lengths, zero-width loads and the two task claims took 3.31 to 3.62 s. It returned PASS.
- The G1 card, with 7 members, took 49.9 s for 17 checks, 2.9 s each.
- A 17-member Pratt card took 37.1 s, 61.5 s and 83.0 s for three checks in one process. It returned FAIL. Load from other agents may explain part of the rise, and the unbounded caches the rest (guess).
- One check under cProfile spent about 22% of its time in elaboration, 22% in the solvers and 37% in the kernel. The R3 elastic-force lemmas were the largest part. All of it runs on one core in exact rational arithmetic.

**Mass from a card.** The example Warren truss weighs 89.3575 kg from the card text alone, in 0.3 to 1.0 ms. Petra's parser with `judges.truss.read` gives the same value.

**CalculiX 2.21 on the VM.** The VM has Python 3.12.3, numpy 2.5.3 and scipy 1.18.1. Another job held 4 Python processes at full load, with a load average of 3.6 to 3.9. Decks went over ssh as a tar on standard input and ran as `OMP_NUM_THREADS=1 CCX_NPROC_EQUATION_SOLVER=1 ccx -i <deck>`.
- The example Warren truss as T3D2 bars, every member CHS 60.3x3.2, took 0.02 s. Each support reacted 24.000 kN. The deflections v_B = -1.449646e-3 m, v_D = -1.281661e-3 m and u_C = 8.959185e-4 m match the numpy model to 7 digits.
- Linear buckling of a pin-ended CHS 60.3x3.2 of 2.5 m with B32R pipe elements gave 0.325 of Euler at 1 element, 1.0134 at 2, 0.9987 at 4 and 0.9977 at 8. Each run took about 0.02 s.
- GMNIA of the same member under imposed shortening, as a ratio of the peak to EN curve c's N_b of 56.89 kN, gave 0.9025 at L/150 with 16 elements in 6.8 s and 0.9027 with 32 elements in 12.6 s. It gave 0.9728 at L/200 in 6.7 s and 1.2425 at L/1000 in 6.3 s. A run at L/150 with 100 increments took 3.3 s and reached the same peak.

**FE in numpy on the PC.** The critical force of the pin-ended member over Euler was 1.2159 at 1 element, 1.0075 at 2 and 1.0005 at 4. A static and buckling solve of the example Warren truss took a median of 0.37 ms over 25 runs at 1 element per member (0.35 to 0.68 ms) and 1.38 ms at 2 (0.69 to 38.74 ms).

**G1 with Petra's own verdict.** The card is a 12 m Warren girder of two panels. Its top chord is one 6 m CHS 48.3x3.2, every other member is CHS 114.3x3.6, and it claims collapse and stability factors of 1.5. Bisection on the load at the two top nodes put Petra's largest passing load at 1.0231 kN, to within 0.001 kN. At 1.5 times that load, with self-weight, the chord carries 5.78 kN of compression. There, EN 6.3.3 gives a utilisation of 1.052 with the more favourable annex, and the axial term alone is 0.953. The EN arithmetic is the probe's own float code, not the clean-room judge, so this case is the judge's first acceptance test.

**Scripted LLM judge.** The Claude Code command-line tool bundled with the desktop app, version 2.1.317, ran in print mode with no tools, a JSON schema and a system prompt. It exited in 1.9 to 2.4 s with "Not logged in" and used no tokens, with and without `--restricted`. Its `--bare` mode needs an API key, and none is set.

**P3's agent usage.** The P3 pilot's 20 agents used 3,452,269 tokens in all, a median of 167,829 each (139,799 to 261,551), over 7.05 agent-hours (measured from its usage log, on its branch).

## 15. What may not work

1. **The FE result follows from its definition.** Rayleigh-Ritz guarantees FE-1's error. So A2 measures whether optimisation finds a known error, and how often and how fast, not whether an error exists. FE-2's 0.75% error is the more telling arm (inferred).
2. **Optimised designs sit on the boundary, so small errors count.** A grader with a 0.6% error yields false PASSes of about 0.6%. The 1% exceedance column exists for this. A reader who calls 0.6% safe will read row 2 differently (inferred).
3. **Physics depends on the bow.** One member ranged from 0.90 to 1.24 of EN over the bows tried (measured). The physics column can report a code-physics disagreement but cannot settle it.
4. **Petra is slow on larger trusses.** A check took 37 to 83 s at 17 members (measured), and the families stop at 13 members for that reason. If A1's top budget falls to 1000 or 300, the curve's top end is thin where optimisation pressure is highest (inferred).
5. **The scripted call is not logged in.** Without it the LLM arms cost several times more, and A4 and B2 lose stage 2 (inferred).
6. **The call volume is large,** about 22 to 43 times P3's tokens with stage 2 (guess).
7. **Six sections make a coarse design space.** Continuous heights let the optimiser reach a boundary, but section jumps leave margins that can hide errors (inferred).
8. **G1 may swamp H1.** Petra's modulus margin, 200 against 210 GPa, hides most buckling errors (inferred). G1 is the exception found so far. If G1 stays unfixed, Petra's false PASSes on T1's long panels may all be G1 and say nothing about unknown gaps (inferred).
9. **The twin is not ready,** and the steel truth leans on Petra itself through the table in §2. A misreading of AISC that both share passes unseen.
10. **Everything is single-family** except CalculiX and the arithmetic. The LLM judge, the truth judge's author, the twin's author and the hand checkers are one family.
11. **The steel arena has no FE reward,** so H2 there rests on the LLM judge alone.
12. **The LLM judge has no tools.** That matches how an LLM grader is usually used as a reward (guess), but a judge with a calculator might do better. The xhigh re-ask gives one data point on that question, not an answer.
13. **Row 3 cannot be shown at these sizes.** With 20 runs per LLM cell, no observed rate bounds the true rate below 2%.

## 16. Maintainer decisions and their defaults

| Decision | Default | Alternative |
|---|---|---|
| Truth in trusses (frontier §9 item 3) | EN 1993-1-1 compliance of the declared structure, judged clean-room | Physics truth at one declared bow |
| Bows for the physics column | L/1000 and L/150 | Other bows, or residual stresses as well |
| Truth in steel | The twin and Petra together, with hand checks on disagreements | The twin alone, with hand checks only on candidate Petra false PASSes |
| False PASSes from disclosed premises | Count them, with a cause tag | Leave them out of H1 |
| G1 | Fix it before the harness freeze, and keep the unfixed commit for the planted-error check | Run unfixed, with G1 tagged |
| Boundary band | 1e-4 of utilisation, with a 1% exceedance column | A wider band |
| FE reward in steel | None | A plate-model reward built on `calculix_check.py` |
| LLM judge and designer | Claude Opus 5.5 at effort medium, no tools | Higher effort, or tools |
| Multiple comparisons | Bonferroni over seven cells | Per arena |
| A1's top budget | The rule in §10 | A fixed budget |
| Steel start | After the twin's done test | Earlier, with the twin labelled provisional |
| Second model family | None configured (frontier §9 item 2) | Configure one for the judge or the truth judge's author |

## Amendments

### 2026-11-08, gap G1 fixed at cf9f814

Commit cf9f814 fixes G1. Petra's truss models now lower a compression member's buckling resistance for its self-weight bending, by the member check of EN 1993-1-1 6.3.3 with Annex B. The bounds and recalled factors are listed in `petra/models/truss.py`. No premise discloses the gap any more (measured, `tests/test_truss.py`). The G1 card of §14 now fails at 1.0231 kN, and its witness names the top chord and 6.3.3 (measured). The largest load it passes is 0.7327 kN, where the probe's float code gives a 6.3.3 utilisation of 0.908 (measured). In the G1 table, Petra's capacity over the 6.3.3 limit falls to between 0.900 and 0.959 (computed). Commit 38cc6ba stays the planted-error baseline of item 5 of the Summary.
