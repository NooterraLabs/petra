# How the checker works

Petra checks a design against a card and a deck of rules. The verdict comes from a small kernel, `petra-verify`, written in Lean. Everything else finds things for the kernel to check, or words what it said.

## The three inputs

| Input | Written by | Holds |
|---|---|---|
| The card, `NAME.card` | Whoever asks for the design | The loads, each signed bound, and any waivers |
| The design, `NAME.petra` | A designer or an agent | The parts |
| The deck of rules | Whoever transcribes a standard | The types of part, the grid, and the rules |

A design cannot state a load, a waiver or a signature, so it cannot change what is asked of it. [reference.md](reference.md) describes the language of the first two, and [deck.md](deck.md) the third.

## The grid and its cells

A deck lists the types of part it knows. For each type it lists every mechanism a part of that type must answer for. That list is the grid. A rule answers one mechanism: it binds equations and tables of the standard to the fields of a part and states an inequality.

The kernel makes one cell for each part, each mechanism and each load case, and settles it in one of five states.

| State | When |
|---|---|
| Proved | The rule's inequality holds for every value the card and the design allow |
| Refuted | It fails at a point they allow |
| Not applicable | The grid says the mechanism cannot arise for this part |
| Waived | The card waives the mechanism on the part with a signature, and the cell would be open without it: the deck has no rule for the part, or the design or the card leaves out something a rule reads and the rule holds under some value of it |
| Open | Anything else |

No cell has a default. A mechanism with no rule is an open cell and not a silent pass.

## The verdict

| Verdict | When |
|---|---|
| FAIL | A cell is refuted |
| UNKNOWN | No cell is refuted, and a cell is open or no cell is proved |
| PASS | Every cell is proved, waived or not applicable, and at least one is proved |

`petra check` prints PASS_WAIVED for a PASS that rests a cell on a waiver, so that nobody takes it for a pass in which the deck answered every cell.

A design none of whose parts is of a deck's type cannot be checked, since there is no rule to check it by. It reads UNKNOWN, and the report says which kinds no deck has. The kernel is not asked about it, so it reads the same on a machine with no kernel. A design that has parts of a deck's types beside parts of another kind is refused as input.

## What does the work

1. **The language** (`petra/lang`) parses the card and the design.
2. **The exporter** (`petra/export.py`) writes the files the kernel reads. [format.md](format.md) is their specification.
3. **The Python reader** (`petra/grid.py`, `petra/deck.py`) works out the same cells as the kernel will. It searches for hints: a way to split the ranges so that a proof goes through, or a point that refutes a rule. Its cells also word the report.
4. **The kernel** (`kernel/`) reads the files and the deck, works out every cell itself in exact arithmetic, and prints the verdict. It takes the hints only as places to look.
5. **The shell** (`petra/verify.py`, `petra/pipeline.py`) runs the kernel and takes its answer. It compares the kernel's cells with the Python reader's, one by one. A difference is a bug in one of the two and gives no verdict.

No way into a check gives a pass or a fail that is not the kernel's. With no kernel to run, or with one whose answer does not hold together, `petra check` prints no verdict for a design of a deck and exits 4. The Python reader does work out a verdict of its own, which `petra.grid.check` returns to code that calls it: that is its working, held to the kernel's, and no check reports it.

## What a pass rests on

A PASS says that every cell of the grid was settled. It rests on five things of different strength, and it is only as strong as the weakest.

| Level | What stands behind it | Where |
|---|---|---|
| The arithmetic of a proved or refuted cell | Theorems about the kernel's own definitions, checked by Lean | [proved.md](proved.md) |
| The rest of the kernel: reading the files, writing a rule as arithmetic, listing the cells | Tests, a second reading of the specification written without sight of the kernel, a generator of hostile files, and review. Not proved | [format.md](format.md), `bench/` |
| The front end: turning the text of a card and a design into the files the kernel reads | Tests. No second reading of the language. A bug here, a wrong unit factor for one, gives the kernel other numbers than the pair's, and the verdict is then about those | `petra/lang`, `petra/units.py`, `petra/export.py` |
| The rules of a deck | Two transcriptions of the standard that agree on sampled parts, and worked examples from a published source. Agreement is not proof that a rule is the standard's | [deck.md](deck.md) |
| A waived cell | The signature of the person named. Petra checks nothing about it | The report's `waived` lines |

A PASS does not say that the grid lists every way the part can fail. A deck asks about the mechanisms its authors wrote down. [deck.md](deck.md) lists what the first deck covers and what it does not.

A verdict is about the files the kernel was given. The report prints the hash of the card, the design and the deck, and [format.md](format.md) says how a reader ties a PASS to their own card and their own deck.

## The old path

Until 2026-11-15 Petra also held a checker written in Python, with models of trusses, circuits, bolts and steel connections. It could pass a design with no deck of rules, and an audit found designs it passed wrongly ([advisory_0.1.1.md](advisory_0.1.1.md)). It was deleted. [old_path_removal.md](old_path_removal.md) says what went and where it is kept.
