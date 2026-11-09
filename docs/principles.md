# Engineering principles

Written 2026-11-05. These are the rules for anyone writing Petra code, human or agent, and especially for deck authors such as the steel connections work ([steel_connections.md](steel_connections.md)). A deck is the set of builders, models and registry rows that checks one kind of design against one design code. The steel connections deck, for example, checks connections to AISC 360-22 Chapters J and K.

The rules come from three sources:

- the numbered decisions in [design.md](design.md#design-decisions), which the code already enforces
- the pstack principles the codebase already cites, such as boundary-discipline, type-system-discipline, model-the-domain and encode-lessons-in-structure
- the practice of high-assurance tools, such as proof kernels, verified compilers and electronic design automation (EDA) sign-off

One rule ranks above all the others. A rule that matters is enforced by a test, not by this page (encode lessons in structure). The Enforced by column says which rules a test already enforces, and §4 lists the structural tests.

## 1. The trusted base

| # | Rule | Why | Enforced by |
|---|---|---|---|
| T1 | The kernel knows maths only. It never interprets a label, unit or physical name. It imports only the standard library. | A Lean port and outside auditors must be able to read the whole trusted base (the de Bruijn criterion) | Import test and design.md |
| T2 | The trusted base is counted. The kernel's shared core stays under a cap, each certificate rule earns its lines, and all trusted code, in the kernel or outside it, stays under one ceiling (§1.1) | Every trusted line is a possible false PASS. A cap on the kernel alone pushes logic into trusted modules outside it. | `tests/test_kernel_budget.py`, which reads the manifest `tests/trusted_base.py` |
| T3 | No floats in the trusted path. Exact rationals and outward-rounded intervals only. Floats live in untrusted solvers. | A rounding error is a false PASS that no one can see | Kernel import test and review |
| T4 | Solvers are never trusted. Every number a solver chooses is evidence the kernel checks. | Translation validation: check each output, don't prove the producer | Data flow (design.md decision 1) and the mutation suite |
| T5 | Changing a rule needs a second implementation's agreement (later, Lean) and a full mutation-suite run | A kernel bug would break every verdict at once | Process, until the Lean kernel exists |

### 1.1 How T2 counts the trusted base

T2 replaced a fixed kernel total of 1,500 code lines on 2026-11-08. Each certificate rule costs 44 to 150 code lines (measured), and coming domains such as dynamics and stability need more rules. Every confirmed false PASS so far came from models, elaboration or premises, never from kernel arithmetic ([plan](plan.md) §1).

`tests/test_kernel_budget.py` counts code lines, which leave out blank lines, comments and docstrings. It reads the manifest `tests/trusted_base.py`. T2 has four parts, and the test enforces the first three.

1. **The shared core has a cap.** The core is the kernel without its rule modules. It holds terms, evaluation, interval arithmetic, the checker loop, the codec, evidence, linear algebra, the rule base and registry, and the package's re-exports. It measured 957 code lines on 2026-11-08, and `CORE_CAP` is 1,000.
2. **Each rule earns its lines.** The manifest lists each rule module with its code lines and three items. These are the doc section that states the rule's soundness, the mutation corpus the rule must reject, and its check against an outside checker. An item a rule lacks is a dated `Debt` that says what exists instead. The test fails when a rule module has no entry, when an entry's count differs from the file, and when an entry points at a doc heading or a test that does not exist. R1 to R6 held 457 code lines on 2026-11-08 (measured).
3. **The whole trusted base is counted.** The manifest puts every module under `petra/` outside the kernel in a trusted group or in the untrusted list, and the test fails on a module in neither. Each trusted group names the judge or twin that checks it and what that judge shares with Petra, or a dated debt. The 48 trusted modules outside the kernel held 12,116 code lines on 2026-11-08 (measured). With the core and the rules, the trusted base held 13,530 code lines against `TRUSTED_CEILING`, 14,000. The ceiling changes only by editing that constant, with the reason beside it.
4. **A rule proved in Lean stops counting.** Once Lean proves a rule's soundness, the rule's lines leave the trusted total. The mechanism comes later.

`python -m tests.test_kernel_budget` prints the three counts and every recorded debt.

## 2. Elaborators and decks, where every false PASS so far came from

An elaborator turns a design into the statements the kernel checks. Its builders, one per failure mode, are the functions that build those statements.

| # | Rule | Why | Enforced by |
|---|---|---|---|
| D1 | Each failure mode has one builder, `(requirement, model, design, registry) -> Obligation or Gap`. A builder is pure, with no I/O or global state. | A reader traces any verdict in three files | design.md interface |
| D2 | Every builder cites its clause. Every clause in a deck's scope maps back to a builder, a premise or an exclusion. | Exhaustiveness is a checked table, not a claim | Add a traceability test (§4) |
| D3 | Every model has validity rows. A limit stated in words but not as a row fails CI. | Formulas used outside their range were the false PASSes in the audit of dira, the larger engine that came before Petra | `tests/test_validity.py`, and a "builder has rows" test still to add (§4) |
| D4 | No silent defaults. A missing input is a `Gap` needing `NeedsInputBound`, never a default value. | The checker must never invent an input | `StatementBuilder` has no number-to-hypothesis method. A lint for default arguments in builders is still to add (§4). |
| D5 | No magic numbers in builders. Every constant (factors, Fy, hole sizes) is a registry row with a source, a clause and a premise tag. | Provenance, and footprints that show every number | Add a lint for numeric literals in deck modules (§4) |
| D6 | Units are fixed at the boundary. Parse with units, store exact canonical values, and let no unitless number cross a module boundary. | Unit errors were among the historical engineering disasters | `units.py`. Dimension vectors inside certificates are planned for P7 (plan.md). |
| D7 | Domain outcomes are typed values, not exceptions. UNKNOWN needs, refutations and gaps are data. Exceptions are only for programmer errors and bad input. | An agent acts on the variant. A crash tells it nothing. | `verdict` types |
| D8 | Names follow the standard's symbols (Rn, φ, Ω, Fnv, Agv), and each deck has a glossary. Docstrings cite clauses, and the code never copies standard text. | Reviewers check code against the clause line by line, and standard text is under copyright | Review, and a similarity check against the source |
| D9 | Model the domain once. Repeated rules live in one structure, such as a table of limit states per element type, not in scattered conditionals. | Coverage and the twin elaborators (V4) read the same table | Registries (design.md decision 9) |
| D10 | Every elaborator is hashed into its premises. Editing physics changes every affected footprint. | An old verdict cannot survive a model change unnoticed | design.md decision 8 |

## 3. Proof that the code is right

| # | Rule | What it catches | Status |
|---|---|---|---|
| V1 | Golden tests reproduce published examples "to rounding". The tolerance policy is written down, and every discrepancy is explained, never tuned away. | Wrong formulas | Per deck |
| V2 | Manufactured single faults are designs with exactly one known defect, such as a missing weld, a short edge distance or a wrong joint type. The checker must catch each one. | Missing coverage | Per deck ([steel_connections.md](steel_connections.md) §9) |
| V3 | Property tests check four properties: adding material never lowers capacity; scaling units changes nothing; mirroring a design changes nothing; a larger load box never turns FAIL into PASS | Sign and direction errors | `tests/test_steel_properties.py` |
| V4 | A twin elaborator is written from the sources by a separate agent with no access to the first implementation's code. The two must agree on generated cases. | Translation bugs | Per deck. The steel twin is `petra/models/steel/twin.py`. |
| V5 | Mutation tests mutate a formula in a builder, and some test must fail | Tests that test nothing | The kernel mutation suite, and `tests/test_steel_mutation.py` for the steel deck |
| V6 | A breaker is an optimiser that searches for PASSes an independent check refutes. Every run is logged. | False PASS | Per deck |
| V7 | Test behaviour, not implementation. Assert verdicts, margins and footprints, not internal calls. | Brittle tests | Review |
| V8 | Prove it on the real artifact. Run `python -m petra check` on real example files, not only unit tests. | Proxy success | Every milestone |
| V9 | Explain the number. Every reported count, such as examples reproduced, decided share or speed, says what limits it. | Misleading progress | Every milestone report |

## 4. Structural tests

Each test below makes CI fail when a rule from §1 to §3 is broken (encode lessons in structure):

| Rule | Test |
|---|---|
| The kernel core's cap, a manifest entry for every rule with each missing item as a dated debt, a trust class for every module under `petra/`, and the trusted total's ceiling (T2) | `tests/test_kernel_budget.py` |
| Traceability: every clause row maps to a builder, a premise or an exclusion, and every builder maps to a clause row (D2) | `tests/test_steel_trace.py` |
| Every `ModelSpec` a deck uses has at least one validity row, or an explicit "unbounded" note (D3) | `tests/test_steel_trace.py` |
| No default argument values, and no numeric literals other than 0, 1 and 2, in deck builder modules (D4, D5) | `tests/test_steel_principles.py` |
| Every registry row has a source, a clause and a tag (D5) | `tests/test_steel_principles.py`, `tests/test_registry.py` |
| A deck mutation suite (V5) | `tests/test_steel_mutation.py` |
| Property tests for monotonicity, unit scaling and mirroring (V3) | `tests/test_steel_properties.py` |

## 5. Process

| # | Rule | Principle |
|---|---|---|
| P1 | Work in verifiable units. Each milestone ends with its gate run and its numbers reported before the next milestone starts. | Sequence work into verifiable units |
| P2 | Settle the data structures before writing logic. The registry rows, the element graph and the limit-state table come first. | Foundational thinking |
| P3 | Delete before adding. No compatibility shims, no dead code, no "v2" next to "v1". | Subtract before you add, and the laziness protocol |
| P4 | Find the root cause before fixing. When two fixes fail, write down the premise they shared and test it. | Fix root causes, and attack the premise |
| P5 | Validate at the boundary (parser, lowerer, codec) and trust internal types after that | Boundary discipline |
| P6 | Make illegal states unrepresentable, for example a PASS with no footprint (already impossible) | Type system discipline |
| P7 | Parallel sessions get separate worktrees and branches, never shared files | Separate before serializing shared state |
| P8 | Each milestone gets an independent review (`/code-review` at high effort) and a red-team pass before it is merged | Outside judge |
| P9 | Standard text, PDFs and large tables never enter the repository. Sources live in the gitignored `docs/research/sources/`, and registry rows cite them by name and hash. | Standards are copyrighted. Petra encodes methods and cites clauses. |
| P10 | Correctness first. Optimise only with a measured profile, and explain the number. | Explain the number |
