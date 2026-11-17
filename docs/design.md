# How the checker works

Petra checks a design against a card and a deck of rules. The verdict comes from a small kernel, `petra-verify`, written in Lean. Everything else finds things for the kernel to check, or words what it said.

## The three inputs

| Input | Written by | Holds |
|---|---|---|
| The card, `NAME.card` | Whoever asks for the design | The deck of rules it asks for, by the hash of its file, the loads, each signed bound, and any waivers |
| The design, `NAME.petra` | A designer or an agent | The parts |
| The deck of rules | Whoever transcribes a standard | The types of part, the grid, and the rules, with the record of the deck's acceptance run beside it |

A design cannot state a load, a waiver or a signature, so it cannot change what is asked of it. [reference.md](reference.md) describes the language of the first two, and [deck.md](deck.md) the third.

## The grid and its cells

A deck lists the types of part it knows. For each type it lists every mechanism a part of that type must answer for. That list is the grid. A rule answers one mechanism: it binds equations and tables of the standard to the fields of a part and states an inequality.

The kernel makes one cell for each part, each mechanism and each load case, and settles it in one of five states.

| State | When |
|---|---|
| Proved | The rule's inequality holds for every value the card and the design allow, or the keys are as a rule requires |
| Refuted | The inequality fails at a point they allow, or the keys are not as a rule requires |
| Not applicable | The deck excuses the part from the mechanism, with a reason and on one ground that the kernel checks: a condition over keys the card states, the loads the type takes, the least value the type declares for a load or a quantity that the part has a value for, or other lines of the grid whose cells for the part are all proved, waived or not applicable |
| Waived | The card waives the mechanism on the part with a signature, and the cell would be open without it: the deck has no rule for the part, or the design or the card leaves out something a rule reads and the rule holds under some value of it |
| Open | Anything else |

No cell has a default. A mechanism with no rule and no excuse is an open cell and not a silent pass.

A cell that reads no quantity of the part or of the card is marked `stated`: a cell of a rule that requires something of the keys, and a proved or refuted cell of an inequality neither of whose sides reads one, as an inequality between numbers of the deck alone. Nothing is worked out for it. A cell is worked out when it is proved, it is not marked `stated`, and it is not the cell that proves only the range a rule holds in, whose entry ends in `/where`.

That is all "worked out" means: the cell is proved, and its inequality reads a quantity of the part or of the card. The kernel does not tell whether the inequality turns on what it reads. A rule that reads a quantity and does not turn on it, as nought times a span, has a cell that counts as worked out. The deck's author answers for such a rule, as for a limit set too high.

## The verdict

| Verdict | When |
|---|---|
| FAIL | A cell is refuted |
| UNKNOWN | No cell is refuted, and a cell is open or no cell is worked out |
| PASS | Every cell is proved, waived or not applicable, and at least one is worked out |

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

A PASS says that every cell is proved, waived or not applicable, and that at least one was worked out: it is proved by an inequality that reads a quantity of the part or of the card. It does not say that the inequality turns on that quantity. A proved cell says that the design meets that rule of the deck, under the card. It does not say that the design meets the standard. A PASS rests on eleven things of different strength, and it is only as strong as the weakest.

| Level | What stands behind it | Where |
|---|---|---|
| The arithmetic of a proved or refuted cell | Theorems about the kernel's own definitions, checked by Lean | [proved.md](proved.md) |
| The rest of the kernel: reading the files, writing a rule as arithmetic, listing the cells | Tests, a second reading of the specification written without sight of the kernel, a generator of hostile files, and review. Not proved | [format.md](format.md), `bench/` |
| The front end: turning the text of a card and a design into the files the kernel reads | Tests. No second reading of the language. A bug here, a wrong unit factor for one, gives the kernel other numbers than the pair's, and the verdict is then about those | `petra/lang`, `petra/units.py`, `petra/export.py` |
| The rules of a deck | Two transcriptions of the standard that agree on sampled parts, and worked examples from a published source. Agreement is not proof that a rule is the standard's | [deck.md](deck.md) |
| The deck the card names | The card names the deck by the hash of its file, and the kernel refuses the pair with any other deck. That stops a deck swapped or edited after the card was issued, a limit raised by a slip among them, and makes the card's hash say which rules were asked for. It does not say the deck is a good one, only that it is the one the card's owner named, and it ties a PASS to that deck only for a reader who compares the card's hash with the card they issued | The card's `rules` line, and [format.md](format.md), "Reading a verdict" |
| The deck's acceptance run | A record beside the deck names the deck's hash and the gate that ran, and the kernel reads the deck only with it. That stops a deck edited after its run, by any hand, from being read until the run is made again. It does not show that the run happened or what it found: the kernel reads neither, and a record can be written by hand. Running the check again and comparing the two records, byte for byte, shows that the record is of a run on the deck's own rows. What the run found is in the record's lines, which no reader of a deck reads yet: a deck whose record says that a line was refused is read like any other | `petra/decks/aisc360.run.json`, and [deck.md](deck.md), "The run a deck is bound to" |
| A waived cell | The signature of the person named. Petra checks nothing about it | The report's `waived` lines |
| A key the card states | The signature of the person who states it. The kernel checks that the key is stated and signed, and not that it is true of the part. Every key is the card's unless the deck says the designer chooses it. Which lines a condition excuses and which rules answer turn on the card's keys, and on one thing that is the design's: the order in which it lists the parts of a join, which picks the part that stands under each name. Nothing checks that order | The card, and [deck.md](deck.md), "The grid" |
| A key the designer chooses | The design's own word, for a key that the deck marks `chosen` with a reason. The kernel checks that the deck gives the reason, and not that it is true. Nothing checks that the name the design writes reaches the drawing and the parts list, or that what is built keeps it. A rule may take a limit from a table by such a key | The design, and [deck.md](deck.md), "A key the designer chooses" |
| A cell that is not applicable | One ground that the kernel checks, and the deck's reason in words, which it prints on the cell and does not check. The ground is a condition over keys the card states that holds for the part, the loads that the type takes, the least value that the type declares for a load the card puts on the part in every load case or for a quantity the part states, or other lines of the grid whose cells are all proved, waived or not applicable for the part. A ground excuses a line and may say less than the reason does. That the mechanism cannot arise is the deck's reason, which no reader checks, and the deck's author's to answer for | The report's `not_applicable` cells |
| A cell marked `stated` | The word of whoever stated the keys, the card or the design. Every cell of a rule with `requires` is marked, and so is a proved or refuted cell of an inequality that reads no quantity of the part or of the card. Nothing is worked out for it, and such cells alone make no PASS. A proved cell of an inequality that is not marked reads a quantity, and nothing shows that its rule turns on it | Cells marked `stated`, which the report prints as `stated` where they are proved |

A PASS does not say that the grid lists every way the part can fail. A deck asks about the mechanisms its authors wrote down. [deck.md](deck.md) lists what the first deck covers and what it does not.

A verdict is about the files the kernel was given. The report prints the hash of the card, the design, the deck and its run, and one hash of all six files the kernel read. The card names the deck, so a reader who ties a PASS to their own card ties it to the deck they asked for too. [format.md](format.md) says how.

## The old path

Until 2026-11-15 Petra also held a checker written in Python, with models of trusses, circuits, bolts and steel connections. It could pass a design with no deck of rules, and an audit found designs it passed wrongly ([advisory_0.1.1.md](advisory_0.1.1.md)). It was deleted. [old_path_removal.md](old_path_removal.md) says what went and where it is kept.
