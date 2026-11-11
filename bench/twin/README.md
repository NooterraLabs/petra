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

## What it is not

It does not read a design of the models' kinds, hash a file, or apply the kernel's limits on size. It is a reading of the rules path only.
