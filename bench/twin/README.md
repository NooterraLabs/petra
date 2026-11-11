# A third reading of the grid

`verify.mjs` is a checker for a design of a deck's types, written from `docs/format.md` and `docs/deck.md` alone. It exists because the kernel was ported from `petra/grid.py` by reading it, so those two agreeing shows a faithful port and not two readings of the specification. This one shares no code and no author with either.

## How it was made

An agent on another model than the kernel's author was given three pages (`format.md`, `deck.md` and the units list of `reference.md`), the shipped deck, the core domains and six exported bundles with the verdict each must get. It was told to open nothing else: no file of the repository, no program of Petra. It wrote one JavaScript file for Node with no dependency, with exact fractions in `BigInt`.

It also kept `AMBIGUITIES.md`: 61 places where the pages were silent, unclear or at odds with the examples, each with the reading it took. That file is a list of faults in the specification, as found by a reader who had only the specification.

## What was changed afterwards

Two changes, each after the specification gained the sentence that settles the question:

- Dimensions are compared by their exponents where a file meets the deck, so `moment` and `energy` are one dimension. The reading had compared them by name.
- The cells for values that nothing reads come after every other cell. The reading had listed them after each part.

Nothing else was edited.

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

The pages now say that an anchor names its standard and its clause, and that bands and listed values are in order ([deck.md](../../docs/deck.md)). This reading was not edited for it. A copy of it with those three refusals added differs from the kernel on 51 of the 3,000 decks: the rows of the table from `what` down.

## What it is not

It does not read a design of the models' kinds, hash a file, or apply the kernel's limits on size. It is a reading of the rules path only.
