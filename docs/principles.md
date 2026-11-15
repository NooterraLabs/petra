# Engineering principles

These are the rules for anyone writing Petra code, human or agent. One rule ranks above the others: a rule that matters is enforced by a test, not by this page. The last column says which test.

## 1. The trusted base

| # | Rule | Why | Enforced by |
|---|---|---|---|
| T1 | The verdict is the kernel's. Nothing in Python gives one, and with no kernel there is none. | Every line that can pass a design is a possible false pass, so there is one place for them | `tests/test_kernel_decides.py`, `tests/test_no_wrong_pass.py` |
| T2 | What Python does on the way to the kernel is counted and held to a ceiling: its arithmetic, the front end, and the reader of a deck. Each part names what checks it, or a dated debt. | A bug in the front end gives the kernel the wrong files. A cap makes growth a decision. | `tests/test_kernel_budget.py`, which reads `tests/trusted_base.py` |
| T3 | No floats decide anything. The kernel and the Python reader work in exact rationals and intervals rounded outward. A float appears only in a ratio that a report prints. | A rounding error is a false pass that nobody can see | `tests/test_interval.py`, `tests/test_cosine.py`, the comparison of the two readers |
| T4 | A search is never trusted. A partition or a point that Python finds is a hint, and the kernel checks it. | Check each output and not the program that made it | [format.md](format.md), `bench/kernel_grid.py` |
| T5 | The package needs the standard library alone, and holds no piece of the deleted Python checker. | An install with no other package has less to trust, and the old path could pass on its own word | `tests/test_structure.py` |

`python -m tests.test_kernel_budget` prints the counts of T2 and every recorded debt.

## 2. Decks

A deck is data: rows, types, a grid and rules ([deck.md](deck.md)). Every false pass found so far came from how a standard was turned into checks, and never from arithmetic.

| # | Rule | Why | Enforced by |
|---|---|---|---|
| D1 | The grid lists every mechanism a part of a type must answer for. A mechanism with no rule is an open cell. | A check that nobody wrote must show, and not pass in silence | The kernel, and `tests/test_grid.py` |
| D2 | Every row and every rule names its clause. | A reader can find the sentence of the standard behind any cell | `petra/deck.py`, `petra/grid.py` when a deck is read |
| D3 | A row states the range of each quantity it reads, and a rule its `where`. A verdict outside them is open. | An equation used outside its range is a wrong answer that looks right | The kernel |
| D4 | A row and a rule enter a deck through the acceptance check: two transcriptions that agree on sampled parts, and worked examples from a published source. | The transcriber is not trusted | `tests/test_deck.py`, `tests/test_rules_accept.py`, `tests/test_deck_rules.py` |
| D5 | Units are fixed at the boundary. A quantity is parsed with its unit and stored exactly in SI. | Unit errors are among the classic engineering failures | `tests/test_units.py` |
| D6 | Only the card states a load, a signed bound or a waiver. | A design must not change what is asked of it | `tests/test_lang.py`, `tests/test_cli.py` |
| D7 | A waiver rests only a cell that the deck has no rule for, or one that holds under a completion of what is left out. It never rests a refuted cell. | A signature is not a proof | The kernel, and `tests/test_kernel_attacks7.py` |

## 3. Evidence that the code is right

| # | Rule | Enforced by |
|---|---|---|
| V1 | The corpus holds every design with a known answer, and each must get it by every way into a check. A wrong verdict found anywhere becomes a corpus case. | `corpus/run.py`, `tests/test_no_wrong_pass.py` |
| V2 | The kernel and the Python reader give every cell the same state, on generated designs and on damaged decks. | `bench/kernel_grid.py`, `tests/test_kernel_grid.py` |
| V3 | A second reading of [format.md](format.md), written without sight of the kernel, gives the same verdicts on the same files. | `bench/twin/` |
| V4 | A generator of hostile files runs against all three readers. | `bench/attack/` |
| V5 | The arithmetic of a proof and of a refutation is proved in Lean, with no axiom beyond Lean's standard three. | `proofs/`, [proved.md](proved.md) |
| V6 | Every finding of a hostile review has a test that fails before its fix. | `tests/test_kernel_attacks*.py` |

## 4. Process

| # | Rule |
|---|---|
| P1 | A false pass is never a known limit. It is fixed, or its cell is made open, before the change merges. |
| P2 | A fix starts as a test that reproduces the fault. |
| P3 | Standard text, PDFs and large tables never enter the repository. A deck cites a clause and encodes a method. |
| P4 | A page says what is so. It does not name a file that is gone, and it says "two transcriptions agree", never "correct". |
