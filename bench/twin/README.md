# A third reading of the grid

`verify.mjs` is a checker for a design of a deck's types, written from `docs/format.md` and `docs/deck.md` alone. It exists because the kernel was ported from `petra/grid.py` by reading it, so those two agreeing shows a faithful port and not two readings of the specification. This one shares no code and no author with either.

## How it was made

An agent on another model than the kernel's author was given three pages (`format.md`, `deck.md` and the units list of `reference.md`), the shipped deck, the core domains and six exported bundles with the verdict each must get. It was told to open nothing else: no file of the repository, no program of Petra. It wrote one JavaScript file for Node with no dependency, with exact fractions in `BigInt`.

It also kept `AMBIGUITIES.md`: 61 places where the pages were silent, unclear or at odds with the examples, each with the reading it took. That file is a list of faults in the specification, as found by a reader who had only the specification.

## What was changed afterwards

Five changes, each after the specification gained the sentence that settles the question:

- Dimensions are compared by their exponents where a file meets the deck, so `moment` and `energy` are one dimension. The reading had compared them by name.
- The cells for values that nothing reads come after every other cell. The reading had listed them after each part.
- A row, a line of the grid or a rule with no anchor is refused, and so is an anchor that lacks its standard or its clause. The reading had taken both.
- Bands are refused when one has its lower end at or above its upper end, or starts before the one before it ends. The reading had taken them in any order.
- Listed values of `at` are refused unless each is above the one before it. The reading had taken them in any order.

The last three were written by the agent that changed the kernel, which had seen the kernel. Nothing else was edited, until the update below.

## The update of 2026-11-11

The pages changed a great deal after the reading was written: a deck of 15 rules, limits on names and on the steps to read a deck, and the refusals a third hostile review asked for. A second agent, again on another model than the kernel's author, brought the reading up to them. It worked in a folder that held the two pages as they stood, what had changed in them, the units list, the shipped deck, the core domains, this reading and three exported designs with the result each must get. It was told to open nothing else and to run nothing but Node on this file. It reports that it opened nothing else. Its session did show it the titles of the owner's notes and the state of a repository, which it did not ask for, and it ran a few shell commands to count lines before it kept to Node.

What it changed, each from a sentence of the pages:

- How a value is written: the space before a unit, a comma between thousands only, no sign on a mixed number, and a bare `0` as the plain number zero.
- The keys a deck must have: a `range` for every input of a row, `why` on a jump and on an `unless`, `says` on a rule, `what` where the pages ask it.
- The refusals: a mechanism named `unread`, a `where` with no item, two rules of one line whose ids end alike, a map of a `by` that leaves a name out, `rises` or `falls` that names no side of its table, a text with U+FFFD or half a surrogate pair.
- Dimensions written as exponents, and compared by them.
- The limits that decide a verdict: 64 bytes for a name, 200 for the name of a card or a design, a million steps to read a deck, 10,000 cells and ten million steps to make them, 1,024 orders in a pick.

It left out the budget of work, the memory of enclosures and the caches, which are counted in the kernel's own costs. So where the kernel runs out of work and leaves a cell open, this reading may still prove it. It also left out the limits that change only what is printed.

`AMBIGUITIES.md` gained 19 entries, H1 to H19, and 14 of its old entries are now settled by a sentence of the pages. Three of the new ones were sentences at odds between the two pages, and the pages are corrected: a name is held to 64 bytes as printed, a cell's entry is the id from after its last `/`, and a part's number is checked by the exponents of its dimension. The other 16 are places where the pages are silent and the reading it took is the kernel's on every case below.

## How it is used

```bash
PETRA_TWIN=bench/twin/verify.mjs python bench/kernel_grid.py --count 6000 --decks 3000
```

`bench/kernel_grid.py` then runs every generated design through the grid, the kernel and this reading, and counts the designs on which the kernel and the reading give different verdicts or different cells.

```bash
node bench/twin/verify.mjs --card card.json --design design.json --deck deck.json --rules rules.json --proofs proofs.json
```

It prints the verdict, the findings and the cells as JSON.

## What the comparison found

Measured on 2026-11-11 with `--count 6000 --decks 3000 --seed 5`, against the kernel at 438057d:

| Compared | Result |
|---|---|
| Generated designs of the three decks the bench has | The kernel and this reading give the same verdict and the same cells, in the same order, on every one |
| Decks with one or two things damaged | They differ on 225 of 3,000, and every difference is whether a damaged deck is refused |

The differences on damaged decks are of two kinds. This reading accepts some decks the kernel refuses: an anchor with no standard or clause, and bands out of order, which the pages do not say to refuse. And it refuses a key it does not know anywhere in a deck, as the pages say, where the kernel and `petra/grid.py` refuse one only at the top of a row, a type, a grid line or a rule. The second kind is a fault in the kernel and the grid: a misspelled key inside an input or a table side is ignored there, and the default takes its place.

### After the kernel and the grid refuse an unknown key wherever it stands

Measured on 2026-11-11 with `--count 6000 --decks 3000 --seed 7`, twice: against the kernel and the grid at a634e64, and against them once both refuse a key a deck does not know in every object of the deck. This reading is the same file both times.

| Compared | At a634e64 | After |
|---|---|---|
| Generated designs, 5,877 compared | The same verdict and the same cells on every one | The same |
| Damaged decks, 3,000 compared | They differ on 218 | They differ on 116 |

The damaged decks they differ on, by what differs:

| On the deck | At a634e64 | After |
|---|---|---|
| This reading refuses a key the deck does not have there, and the kernel and the grid took it | 102 | 0 |
| The kernel and the grid refuse an anchor that lacks its standard or its clause, and this reading takes it | 55 | 55 |
| They refuse a row, a line of the grid or a rule with no anchor, and this reading takes it | 9 | 9 |
| They refuse a field, a type or a line with no `what`, a rule with no `says`, and an `unless`, an item of `where` or a jump with no `why`. This reading takes each as left out. | 26 | 26 |
| They refuse an input of a row with no `range`, and this reading takes it | 13 | 13 |
| They refuse `rises` or `falls` that names no side of its table, and this reading does not look | 3 | 3 |
| They refuse values of `at` that are out of order, and this reading takes them | 1 | 1 |
| They refuse a `by` that leaves out a name of its field, and this reading leaves the cell open | 1 | 1 |
| They refuse a range that starts at `-0` with no unit, and this reading takes a bare zero for any dimension | 1 | 1 |
| This reading refuses `1 1/2` with no unit, and they read it as a number | 1 | 1 |
| This reading refuses a cell `1,000` whose unit the table gives, and they read it | 1 | 1 |
| Both read the deck, and a rule's `where` is an empty list: they prove the rule's cell, and this reading leaves it open | 5 | 5 |

No deck with bands out of order came up under this seed.

The pages now say that an anchor names its standard and its clause, and that bands and listed values are in order ([deck.md](../../docs/deck.md)). This reading then gained those three refusals, and with them it differs from the kernel on 51 of the 3,000 decks: the rows of the table from `what` down.

### After the shipped deck took its rules from the page

On 2026-11-11 the shipped deck changed: 32 rows for 18, 15 rules for 4, a grid of 16 lines for 15, and two more fields on a lap. This reading is the same file. It reads the new deck, and gives the three designs of `examples/deck` the kernel's verdict and cells.

Measured with `--count 6000 --decks 3000 --seed 7`, after the bench's generator of laps was changed to fill the new fields and to reach the new rules. The designs and the damaged decks are therefore not the ones of the runs above.

| Compared | Result |
|---|---|
| Generated designs, 5,881 compared | The same verdict and the same cells on every one |
| Damaged decks, 3,000 compared | They differ on 46 |

| On the deck | Decks |
|---|---|
| The kernel and the grid refuse a field, a type or a line with no `what`, a rule with no `says`, and an `unless` with no `why`. This reading takes each as left out. | 19 |
| They refuse an input of a row with no `range`, and this reading takes it | 13 |
| They refuse `rises` or `falls` that names no side of its table, and this reading does not look | 5 |
| They refuse a `by` that leaves out a name of its field, and this reading leaves the cell open | 1 |
| They refuse a range that starts at `-0` with no unit, and this reading takes a bare zero for any dimension | 1 |
| This reading refuses `1 1/2` with no unit, and they read it as a number | 1 |
| Both read the deck, and a rule's `where` is an empty list: they prove the rule's cell, and this reading leaves it open | 5 |
| They refuse a rule whose id prints in more than 64 bytes, and this reading has no such limit | 1 |

The last kind is new to these runs. The damage put the 112 characters of a row's `what` where the id of a rule was. The kernel and the grid hold an id to 64 bytes, and this reading applies none of the kernel's limits on size, as the next section says. Every other kind is in the table above.

### After the update of 2026-11-11

Measured with `--count 6000 --decks 3000 --seed 7`, against the kernel and the grid at 5714d9c. The damage now also makes a line named `unread`, a `where` with no item, two rules that end alike, and a wide row applied 9 or 1,000 times.

| Compared | Result |
|---|---|
| Generated designs, 5,881 compared | The same verdict and the same cells on every one |
| Damaged decks, 3,000 compared | The same on every one: 2,563 refused by all three, 188 PASS, 159 FAIL, 89 UNKNOWN, and one design refused |

The reading as it was before the update differs from the kernel on 7 of the first 49 of these decks, so the comparison does see a difference when there is one.

## The second update of 2026-11-11

Three merges changed the pages after the first update: a cell for every load case of the card, a cell for a load nothing reads, units with a power, conditions on a joined part's key, rules that require, rows that give a name, what a type needs, keys and counts the card states, fields a record may leave unstated, quantities at or under zero, strict `lt`, and more units. A third agent, again on another model than the kernel's author, brought the reading up to them under the same rule: a folder with the pages, what had changed in them, the two decks, this reading and its notes, and nothing else.

It had more examples than before: 45 generated designs and 40 damaged decks, each with the kernel's answer. It was told to change the reading only where the pages support the answer, and to write down every place they do not, rather than fit the examples. It reports one slip: it once wrote helper files outside its folder, and deleted them.

`AMBIGUITIES.md` gained section J, ten entries. Most are about the findings a refused deck prints, which the comparison does not count: how many findings a deck that does not load gives, which rule a part of an unknown kind breaks, and how an item is named. 13 earlier entries were settled by the pages in another way than the reading had taken, and the reading changed to match.

Measured with `--count 6000 --decks 3000 --seed 7` against the kernel and the grid at c5167fb, the comparison first found 7 damaged decks that the kernel and the grid refuse and this reading took. Both kinds were rules the pages did not state: a count of any dimension but `dimensionless`, and a jump whose `cases` do not name exactly two different cases. [deck.md](../../docs/deck.md) now states both, and the reading gained them from that sentence.

| Compared | Result |
|---|---|
| Generated designs, 5,773 compared | The same verdict and the same cells on every one |
| Damaged decks, 3,000 compared | The same on every one: 2,396 refused by all three, 167 PASS, 144 FAIL, 281 UNKNOWN, and 12 designs refused |

## The third update, of 2026-11-12

The merge of the cosine changed the pages again: `cos` on a tape, a waiver that rests only a cell no inequality could answer, the refusal of a rule with no value where a field says it may be, a refutation inside a `where`, and the exact root of a point that is the square of a fraction. A fourth agent, on another model than the kernel's author and under the same rule as before, brought the reading up to them. It had 43 generated designs and 40 damaged decks with the kernel's answers, and after the update all 83 agree in verdict, counts and cells.

`AMBIGUITIES.md` gained section K, seven entries. Most are about how the walk of a waived line is read: which questions a cell whose `where` is not proved asks (K5), which nodes start "no value anywhere" (K6), and a pick too large to walk (K7). K7 is a real gap: a pick of more than 4,096 ways may have a value, so a waiver cannot rest its cell, and the kernel is being changed to refuse such picks when the deck loads.

Measured with `--count 6000 --decks 3000 --seed 7` against the kernel and the grid at d7955ff:

| Compared | Result |
|---|---|
| Generated designs, 5,773 compared | The same verdict and the same cells on every one |
| Damaged decks, 3,000 compared | The same on every one: 2,385 refused by all three, 167 PASS, 154 FAIL, 281 UNKNOWN, and 13 designs refused |

## The fourth update, of 2026-11-12

The eighth review's fixes changed the pages again: a waiver rests a cell for an unstated key or a missing load only under a completion a hint names and under which the rule holds, and the completions must agree across the design; a cell that every name of its keys fails is refuted; a table with no line for the part, a tape that cannot be written and a rule with no value stay open; a `/where` cell is not the proved cell a PASS needs; a rule that could write a pick of more than 1,024 orders is refused when the deck is read. A fifth agent, on another model than the kernel's author and under the same rule as before, brought the reading up to them. Of the 83 bundles, 82 agreed before the update and all 83 after, reasons and waived lists included. It also wrote 25 checks of its own for paths no bundle reaches, which pass. It reports one slip: it listed the folder above its own once, and used nothing from it.

`AMBIGUITIES.md` gained section L, eleven entries. Two of them name places where the ninth hostile review, run at the same time and apart from it, found a wrong PASS: L1, whether a witness for a rule with a `where` must prove the tape inside the range, and L9, whether a completed load is held to its dimension's floor or only to its `least`.

Measured with `--count 6000 --decks 3000 --seed 7` against the kernel and the grid at d7b617f:

| Compared | Result |
|---|---|
| Generated designs, 5,773 compared | The same verdict and the same cells on every one |
| Damaged decks, 3,000 compared | The same on every one: 2,390 refused by all three, 167 PASS, 152 FAIL, 278 UNKNOWN, and 13 designs refused |

## The fifth update, of 2026-11-12

The ninth review's fixes changed the pages again: what a design reads is worked out under the completions of the rested cells, a witness for a rule with a `where` must prove the `where` too, a completed load is held to its dimension's floor, a load case named `where` is refused, hints are charged, and a waived cell carries its completion. A sixth agent, under the same rule as before, brought the reading up to them: 83 of 83 bundles agree, completions included, and its own 50 checks pass. Its notes L1 and L9 are settled by the pages the other way from the reading it had taken. It logged five new notes, M1 to M5; given to the tenth hostile review as leads, M4 (a completion printed as a bare number "in SI units" where the unit of temperature is degC) was a fault, and the other four held.

Measured with `--count 6000 --decks 3000 --seed 7` against the kernel and the grid at 4a2ee81:

| Compared | Result |
|---|---|
| Generated designs, 5,773 compared | The same verdict and the same cells on every one |
| Damaged decks, 3,000 compared | The same on every one: 2,390 refused by all three, 167 PASS, 152 FAIL, 278 UNKNOWN, and 13 designs refused |

## The sixth update, of 2026-11-13

The tenth review's fixes changed the pages again: with `--rules` the floors are `core.json`'s and a deck.json that gives others is a finding (type rule 8), a completion prints each load's value with its unit, and each sum so far of a node that adds many is held to 65,536 bits. A seventh agent, under the same rule as before, brought the reading up to them. Its folder held the two pages, what had changed in them, the units list, the two decks, this reading, its notes and 89 bundles with the kernel's answers: the 83 generated ones, and the tenth review's three forged deck.json files beside their real ones. Before the update 7 of the 89 differed, the three forged floors in verdict and four in the unit of a completed load. After it all 89 agree, completions included, and its own 97 checks of floors, units, bits and the first deck pass.

It reports two slips, neither outside its folder: a listing piped through `head`, and a shell loop that labelled four runs of Node. Its session also showed it the repository's rules for agents and five commit subjects, which it did not ask for.

`AMBIGUITIES.md` gained section N, nine entries. Given to the eleventh hostile review as leads, N7 was a fault: type rule 8 covered `domains.input` only, and a deck.json with a lower `domains.size` turned a refused design to PASS.

Measured with `--count 6000 --decks 3000 --seed 7` against the kernel and the grid at e77d558:

| Compared | Result |
|---|---|
| Generated designs, 5,773 compared | The same verdict and the same cells on every one |
| Damaged decks, 3,000 compared | The same on every one: 2,394 refused by all three, 167 PASS, 152 FAIL, 274 UNKNOWN, and 13 designs refused |

This run compares verdicts and cells, and its generator forges no deck.json, so it does not see either change of this update: the 89 bundles do.

## What it is not

It does not read a design of the models' kinds or hash a file. It applies the limits that decide a verdict and not the budget of work, the memory of enclosures or the limits on what is printed. It is a reading of the rules path only.
