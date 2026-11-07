# Engineering principles

Written 2026-11-05. These are the rules for anyone writing Petra code, human or agent, and especially for deck authors such as the steel connections work (`docs/research/STEEL_CONNECTIONS.md`).

They come from three sources:
- the load-bearing decisions in [design.md](design.md), which the code already enforces;
- the pstack principles the codebase already cites (boundary-discipline, type-system-discipline, model-the-domain, encode-lessons-in-structure and the rest);
- the practice of high-assurance tools: proof kernels, verified compilers and EDA sign-off.

**One rule over all the others:** a rule that matters is enforced by a test, not by this page (encode lessons in structure). The **Enforced by** column says which ones are, and §4 lists the tests still to write.

## 1. The trusted base

| # | Rule | Why | Enforced by |
|---|---|---|---|
| T1 | The kernel knows maths only. It never interprets a label, unit or physical name. It imports only the standard library. | A Lean port and outside auditors must be able to read the whole trusted base (the de Bruijn criterion) | Import test; design.md |
| T2 | The kernel stays small: under about 2,000 lines, with every line justified | Every line is a possible false PASS | Line budget in design.md; add a CI check (§4) |
| T3 | No floats in the trusted path. Exact rationals and outward-rounded intervals only. Floats live in untrusted solvers. | A rounding error is a false PASS that no one can see | Kernel import test; review |
| T4 | Solvers are never trusted. Every number a solver chooses is evidence the kernel checks. | Translation validation: check each output, don't prove the producer | Data flow (design.md decision 1); mutation suite |
| T5 | Changing a rule needs a second implementation's agreement (later, Lean) and a full mutation-suite run | A kernel bug would break every verdict at once | Process, until the Lean kernel exists |

## 2. Elaborators and decks: where every false PASS so far came from

| # | Rule | Why | Enforced by |
|---|---|---|---|
| D1 | **One builder per failure mode**, `(requirement, model, design, registry) -> Obligation or Gap`, pure, with no I/O or global state | A reader traces any verdict in three files | design.md interface |
| D2 | **Every builder cites its clause.** Every clause in a deck's scope maps back to a builder, a premise or an exclusion. | Exhaustiveness is a checked table, not a claim | Add a traceability test (§4) |
| D3 | **Every model has validity rows.** A limit stated in words but not as a row fails CI. | Formulas used outside their range were the dira audit's false PASSes | `tests/test_validity.py`; add "builder has rows" (§4) |
| D4 | **No silent defaults.** A missing input is a `Gap` needing `NeedsInputBound`, never a default value. | The checker must never invent an input | `StatementBuilder` has no number-to-hypothesis method; add a lint for default arguments in builders (§4) |
| D5 | **No magic numbers in builders.** Every constant (factors, Fy, hole sizes) is a registry row with a source, a clause and a premise tag. | Provenance, and footprints that show every number | Add a lint for numeric literals in deck modules (§4) |
| D6 | **Units are fixed at the boundary.** Parse with units, store exact canonical values, and let no unitless number cross a module boundary. | Unit errors were among the historical disasters (PRIOR_ART) | `units.py`; E2 dimension vectors |
| D7 | **Domain outcomes are typed values, not exceptions.** UNKNOWN needs, refutations and gaps are data. Exceptions are only for programmer errors and bad input. | An agent acts on the variant; a crash tells it nothing | `verdict` types |
| D8 | **Names follow the standard's symbols** (Rn, φ, Ω, Fnv, Agv), with a glossary per deck. Docstrings cite clauses; the code never copies standard text. | Reviewers check code against the clause line by line; copyright | Review; similarity check against the source |
| D9 | **Model the domain once.** Repeated rules live in one structure, such as a table of limit states per element type, not in scattered conditionals. | Coverage and twins read the same table | Registries (design.md decision 9) |
| D10 | **Every elaborator is hashed into its premises.** Editing physics changes every affected footprint. | Old verdicts can't silently survive a model change | design.md decision 8 |

## 3. Proof that the code is right

| # | Rule | What it catches | Status |
|---|---|---|---|
| V1 | **Golden tests from published examples**, reproduced "to rounding", with the tolerance policy written down and every discrepancy explained, never tuned away | Wrong formulas | Per deck |
| V2 | **Manufactured single faults**: designs with exactly one known defect (missing weld, short edge distance, wrong joint type), each of which must be caught | Missing coverage | Per deck (STEEL_CONNECTIONS §9) |
| V3 | **Property tests**: adding material never lowers capacity; scaling units changes nothing; mirroring a design changes nothing; a larger load box never turns FAIL into PASS | Sign and direction errors | To add |
| V4 | **Twin elaborator**, written from the sources by a separate agent with no access to the first implementation's code, and required to agree on generated cases | Translation bugs | E3; per deck |
| V5 | **Mutation tests**: mutate a formula in a builder, and some test must fail | Tests that don't actually test | Kernel mutation suite exists; add one for decks |
| V6 | **Breaker**: an optimiser searches for PASSes that an independent check refutes, with every run logged | False PASS | Per deck |
| V7 | **Test behaviour, not implementation**: assert verdicts, margins and footprints, not internal calls | Brittle tests | Review |
| V8 | **Prove it on the real artifact**: run `python -m petra check` on real example files, not just unit tests | Proxy success | Every milestone |
| V9 | **Explain the number**: every reported count (examples reproduced, decided share, speed) says what limits it | Misleading progress | Every milestone report |

## 4. Structural tests still to write

These turn rules in §1–§3 into CI failures (encode lessons in structure):

1. Kernel line budget (T2).
2. Traceability: every clause row maps to a builder, premise or exclusion; every builder maps to a clause row (D2).
3. Every `ModelSpec` used by a deck has at least one validity row, or an explicit "unbounded" note (D3).
4. No default argument values and no numeric literals in deck builder modules, apart from 0 and 1 (D4, D5).
5. Every registry row has a source, a clause and a tag (D5).
6. A deck mutation suite (V5).
7. Property tests for monotonicity, unit scaling and mirroring (V3).

## 5. Process

| # | Rule | Principle |
|---|---|---|
| P1 | Work in verifiable units: each milestone ends with its gate run and the numbers reported before the next starts | Sequence work into verifiable units |
| P2 | Settle the data structures before writing logic: the registry rows, the element graph and the limit-state table come first | Foundational thinking |
| P3 | Delete before adding. No compatibility shims, no dead code, no "v2" next to "v1". | Subtract before you add; laziness protocol |
| P4 | Find the root cause before fixing. When two fixes fail, write down the premise they shared and test it. | Fix root causes; attack the premise |
| P5 | Validate at the boundary (parser, lowerer, codec) and trust internal types after that | Boundary discipline |
| P6 | Make illegal states unrepresentable, for example a PASS with no footprint (already impossible) | Type system discipline |
| P7 | Parallel sessions get separate worktrees and branches, never shared files | Separate before serializing shared state |
| P8 | Each milestone gets an independent review (`/code-review` at high effort) and a red-team pass before it is merged | Outside judge |
| P9 | Standard text, PDFs and large tables never enter the repository. Sources live in the gitignored `docs/research/sources/`, and registry rows cite them by name and hash. | NICHE §4 |
| P10 | Correctness first. Optimise only with a measured profile, and explain the number. | Explain the number |
