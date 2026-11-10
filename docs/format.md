# What the kernel reads

`petra-verify` reads four JSON files and prints one verdict. This page describes the files, the rules the kernel applies to them, and the verdict. The format is version 0 and will change.

```
petra-verify --card card.json --design design.json --deck deck.json [--proofs proofs.json]
```

The kernel trusts none of the four. It checks that they agree with each other and that each proof holds. Who wrote each file is outside the kernel: the verdict prints the SHA-256 of the card, the design and the deck, and a reader compares the card's hash with the card they issued.

`python -m petra.export FILE.petra --out DIR` writes the four files from a `.petra` design.

## Numbers

Every number is a string that holds an exact rational: an integer such as `"18"` or a fraction such as `"-5463/20"`. A fraction is in lowest terms with a denominator above 1, and no number has a leading zero or is `-0`. A string longer than 4,000 characters is refused. A range is a pair `lo`, `hi` with `lo <= hi`.

## card.json

What the asker owns.

| Key | Holds |
|---|---|
| `format` | `"petra-card/0"` |
| `name` | The design's name. A premise label `in:NAME.INPUT` names an input of this card. |
| `environment` | A registry id, or null |
| `cases` | The names of the load cases |
| `inputs` | Every signed bound: `name`, `dim`, `lo`, `hi`, `by`, and `case` for a load |
| `claims` | Each claim: `name`, `subject`, `quantity`, `rel`, `cases`, `bound` |
| `waivers` | Each waiver the asker allows: `subject`, `mechanism`, `by`, `reason` |

## design.json

What the designer owns.

| Key | Holds |
|---|---|
| `format` | `"petra-design/0"` |
| `name` | The design's name |
| `card` | `"sha256:HEX"`, the hash of the bytes of the card this design answers |
| `quantities` | Every number written in a component block: `type`, `entity`, `line`, `field`, `role`, `dim`, `lo`, `hi`. The role is `size` for a number alone and `position` for a number in a tuple. |
| `params` | Each parameter of a family: `name`, `dim`, `lo`, `hi` |

A design has no other key. The exporter writes `waivers`, `loads` or `ambient` when a `.petra` file states a waiver, or a load or an ambient that nobody signed, and the kernel refuses the design.

## deck.json

| Key | Holds |
|---|---|
| `format` | `"petra-deck/0"` |
| `domains.size` | `min` and `strict`: the least value a size may take |
| `domains.input` | For each dimension that has a floor, `min` and `strict`. A dimension that is not listed has none. |
| `constants` | Each registry value a proof reads: `label` (`reg:KEY`), `lo`, `hi` |

`petra/decks/core.json` holds the domains.

## proofs.json

| Key | Holds |
|---|---|
| `format` | `"petra-proofs/0"` |
| `cells` | One cell per obligation |

A cell has `subject`, `mechanism`, `entry` and `state`. The state is one of `proved`, `refuted`, `not_applicable`, `waived` and `open`. A `not_applicable` or `open` cell has `why`. A cell may carry a tape.

### Tapes

A tape states that every root is at most zero for all values of the inputs in their ranges.

| Key | Holds |
|---|---|
| `inputs` | Each input: `label`, `lo`, `hi` |
| `nodes` | A list. Node `i` may refer only to nodes before it. |
| `roots` | The indices of the root nodes |

A node is a list whose first item names it.

| Node | Value |
|---|---|
| `["c", "3/8"]` | The constant |
| `["s", k]` | Input `k` |
| `["pi"]` | Pi |
| `["add", [i, ...]]`, `["mul", [i, ...]]` | The sum or the product of the nodes |
| `["min", [i, ...]]`, `["max", [i, ...]]` | The least or the greatest of the nodes |
| `["neg", i]`, `["abs", i]` | The negation or the absolute value |
| `["sqrt", i]`, `["ln", i]`, `["exp", i]` | The function of node `i` |
| `["div", i, j]` | Node `i` over node `j` |
| `["pow", i, n]` | Node `i` to the integer power `n` |

A `proved` cell with a tape has a `partition`: the string `"leaf"`, or `{"input": k, "at": x, "below": P, "above": P}`, which splits input `k` at `x`. The value `x` lies strictly inside the range the input has at that point of the tree.

A `refuted` cell with a tape has a `point`, one value per input and inside its range, and `which`, the index into `roots` of the root that is more than zero there.

## The rules

The kernel applies the rules in this order. A design that breaks a rule of the first two groups is ILL-FORMED, and the kernel reads no proof.

**Shape.** Each file is JSON with its `format`. Every number parses, and every range has `lo <= hi`. A cell has its keys and a state from the list, and a node is one from the table. A tape that reads a node ahead of itself, or lacks its `partition`, `point` or `which`, leaves its cell open.

**Types.**

1. The design's `card` is the SHA-256 of the card file's bytes.
2. The design has no key but `format`, `name`, `card`, `quantities` and `params`.
3. Every quantity of role `size` has `lo` above `domains.size.min`, or at it when `strict` is false.
4. Every input whose dimension is in `domains.input` has `lo` at or above that floor, or above it when `strict` is true.
5. Every waiver of the card names a `by`.

**Cells.** For each cell:

1. `proved` with a tape: every input is labelled `in:`, `reg:` or `dsg:`. An input labelled `in:NAME.INPUT` is input `INPUT` of the card named `NAME`, and every input labelled `reg:` is a constant of the deck. The tape's range for it contains the card's or the deck's. The kernel evaluates every root on every leaf of the partition by the interval rule, and the upper end of each is at most zero. A cell that meets all of this is proved. Otherwise it is open, and the verdict says which test failed.
2. `refuted` with a tape: the same test on labels. Each value of the point lies in its input's range and in the card's or the deck's range for that label, and two inputs with one label have one value. The lower end of root `which` at the point is above zero. A cell that meets this is refuted. Otherwise it is open.
3. `proved` or `refuted` with no tape is open: the kernel has no rule for its proof yet.
4. `waived` holds only when the card lists a waiver with the same `subject` and `mechanism`. Otherwise it is open.
5. `not_applicable` is taken as stated, and counted.

The interval rule is the one in `petra/kernel/interval.py` and `petra/kernel/evaluate.py`: exact rational intervals, with `sqrt`, `ln`, `exp` and pi rounded outward on a grid of 2^-96. The two kernels give the same ends for every root.

## The verdict

| Verdict | When | Exit code |
|---|---|---|
| ILL-FORMED | A shape or type rule is broken | 3 |
| FAIL | A cell is refuted | 1 |
| UNKNOWN | No cell is refuted, and a cell is open or no cell is proved | 2 |
| PASS | Every cell is proved, waived or not applicable, and at least one is proved | 0 |

The kernel prints one JSON object: `verdict`, the three `hashes`, `findings` (each broken rule, with the file and the item), `counts` (the cells in each state), `dsg_inputs` (the distinct `dsg:` labels the settled proofs read), `waived` (each waiver a PASS rests on) and `cells` (for each cell the state the file claimed, the state the kernel settled on, and the reason when they differ). A command line it cannot read prints the usage and exits 64.

## Limits

The kernel stops work that would not end. A tape has at least one root. A partition is at most 64 deep, and a `pow` exponent at most 64 in magnitude. A value with more than 65,536 bits, or an `exp` of a number beyond 65,536, leaves its cell open. A file's JSON nests at most 128 deep, and a number outside a string has at most 32 digits and no fraction or exponent.

## What the kernel does not check yet

- The list of cells comes from Python's coverage rules. The kernel checks each cell and not that the list is complete.
- A tape's formula comes from Python's models. The kernel checks its arithmetic and its `in:` and `reg:` inputs, not that the formula is the standard's.
- Inputs labelled `dsg:` are the design's values as the models resolved them. The kernel does not tie them to `quantities`, and the verdict counts them.
- A `not_applicable` cell is the model's word.
- Proofs by the other five rules have no tape.
