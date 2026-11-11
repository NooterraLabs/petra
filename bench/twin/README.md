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

## What it is not

It does not read a design of the models' kinds or hash a file. It applies the limits that decide a verdict and not the budget of work, the memory of enclosures or the limits on what is printed. It is a reading of the rules path only.
