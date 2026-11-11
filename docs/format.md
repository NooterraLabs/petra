# What the kernel reads

`petra-verify` reads four JSON files, and a fifth for a design checked against a deck of rules, and prints one verdict. This page describes the files, the rules the kernel applies to them, and the verdict. The format is version 0 and will change.

```
petra-verify --card card.json --design design.json --deck deck.json [--rules rules.json] [--proofs proofs.json]
```

`petra check` writes the files for its report and runs the kernel on them when it finds one: the file the environment variable `PETRA_VERIFY` names, else `kernel/.lake/build/bin/petra-verify` in a source tree. It prints how many of the proofs behind its status the kernel checked, and exits 4 if the kernel rejects one that the Python checker accepted.

The kernel trusts none of the files. It checks that they agree with each other and that each proof holds. Who wrote each file is outside the kernel: the verdict prints the SHA-256 of the card, the design, the deck and the rules, and a reader compares the card's hash with the card they issued and the rules' hash with the deck of rules they mean. [Reading a verdict](#reading-a-verdict) says what a PASS means without that comparison: very little.

`python -m petra.export FILE.petra [--card FILE.card] --out DIR` writes the files from a design and its card, the `.card` file beside the design unless `--card` names another. It exits 3 and writes nothing when the language refuses the pair, as it does for a design that states a load, a claim, a waiver or a signature. With `--no-physics` it writes no proofs.json, and a design with parts is then written as it stands, for the kernel to say whether the deck's types take it. With `--card-only FILE.card` and no design it writes card.json alone and prints its hash ([The asker's card](#the-askers-card)).

There are two kinds of design, and the kernel does more for the second.

- A design of the built-in models' kinds has no `parts`. The kernel checks each cell that proofs.json lists, with the tape the cell carries.
- A design whose parts are of a deck of rules ([deck.md](deck.md)) has `parts`, and goes with `--rules`. The kernel reads the deck of rules, works out every cell and every tape itself, and takes from proofs.json only hints: a partition or a point to try.

## Numbers

Every number is a string that holds an exact rational: an integer such as `"18"` or a fraction such as `"-5463/20"`. A fraction is in lowest terms with a denominator above 1, and no number has a leading zero or is `-0`. A string longer than 4,000 characters is refused. A range is a pair `lo`, `hi` with `lo <= hi`. A `dim` names a dimension, and two names are one dimension when their exponents are equal, as `moment` and `energy` are.

A deck of rules writes its own numbers another way, with units. [The rules file](#rulesjson) says how the kernel reads them.

## card.json

What the asker owns.

| Key | Holds |
|---|---|
| `format` | `"petra-card/0"` |
| `name` | The design's name. A premise label `in:NAME.INPUT` names an input of this card. |
| `environment` | A registry id, or null |
| `cases` | The names of the load cases |
| `inputs` | Every bound: `name`, `dim`, `lo`, `hi`, `by`, and `case` for a load. An input with no `by` is one nobody signed, and the kernel refuses the card. The exporter writes one for a load or an ambient that reads a param. |
| `claims` | Each claim: `name`, `subject`, `quantity`, `rel`, `cases`, `bound` |
| `waivers` | Each waiver the asker allows: `subject`, `mechanism`, `by`, `reason` |

For a design with parts, a load's input also has `on`, the part the load is on, and `field`, which of the loads of the part's type it is. An input with none of `case`, `on` and `field` is a given, and its name is `PART.FIELD`, the part and the field that read it. The card also has `tests` and `probability_claims`, the names of its tests records and its probability claims. A deck of rules reads neither yet, so the kernel refuses a card that has one.

Only the card of a design with parts has `on`, `field`, `tests` and `probability_claims`, and the exporter writes the last two into every such card, as empty lists when the card states none. So the kernel takes each as a mark of a card for a deck of rules, and refuses the card with a design that has no parts or with no `--rules` (type rule 7).

## design.json

What the designer owns.

| Key | Holds |
|---|---|
| `format` | `"petra-design/0"` |
| `name` | The design's name |
| `card` | `"sha256:HEX"`, the hash of the bytes of the card this design answers |
| `quantities` | Every number written in a component block: `type`, `entity`, `line`, `field`, `role`, `dim`, `lo`, `hi`. The role is `size` for a number alone and `position` for a number in a tuple. |
| `params` | Each parameter of a family: `name`, `dim`, `lo`, `hi` |
| `parts` | For a design checked against a deck of rules: each component block as written |

A design has no other key, and the kernel refuses one that has. The language refuses the same design earlier: a `.petra` file that states a waiver, a load or an ambient does not parse.

### Parts

```json
{"name": "tab", "type": "plate", "lines": [
  {"field": "thickness", "args": [{"number": {"dim": "length", "lo": "381/40000", "hi": "381/40000"}}]},
  {"field": "Fy", "args": [{"given": "tab.Fy"}]}]}
```

A part has its `name`, its `type` and its `lines` in the order the design writes them. A line has the `field` it gives and its `args`. An argument is one of four things.

| Argument | Is |
|---|---|
| `{"number": {"dim", "lo", "hi"}}` | A number the design writes, in SI |
| `{"given": NAME}` | The bound the card gives under that name |
| `{"word": WORD}` | A bare word |
| `{"text": TEXT}` | A text in quotes |

The exporter that writes `parts` knows no deck. It writes each line as it stands, and anything else a line holds, such as a tuple, as `{"other": KIND}`, which the kernel refuses. The kernel reads what a line means from the field of that name in the deck of rules: a quantity takes one number or one given, a key takes one word or one text, and a field that joins parts takes words that name them.

A tape names what it reads of a part by label. A number that part `P` writes for field `F` is `dsg:DESIGN.P.F`, with the design's name. A given is `in:CARD.P.F` and a load is `in:CARD.INPUT`, with the card's name and the name of the input.

## deck.json

| Key | Holds |
|---|---|
| `format` | `"petra-deck/0"` |
| `domains.size` | `min` and `strict`: the least value a size may take |
| `domains.input` | For each dimension that has a floor, `min` and `strict`. A dimension that is not listed has none. |
| `constants` | Each registry value a proof reads: `label` (`reg:KEY`), `lo`, `hi` |
| `rules` | For a design checked against a deck of rules: the `name` of that deck and the `hash` of its file. The kernel reads only that the key is there (type rule 7). It reads the deck of rules itself, from `--rules`. |

`petra/decks/core.json` holds the domains.

## rules.json

The deck of rules a design with parts is checked against: the file of `petra/decks` as it ships, with `"format": "petra-rules/0"`. [deck.md](deck.md) describes it. `petra check` and `petra.export` hand the kernel the file's own text, so the hash the kernel prints for it is the hash of the deck.

The kernel reads the whole deck and refuses one that does not hold together, as `petra/grid.py` does when it loads one. It reads these itself, and takes none of them from Python:

- A dimension, such as `force/length` or `length^3`, as five exponents of metre, kilogram, second, ampere and degree Celsius. They are rational, because a square root halves them.
- A quantity with its unit, such as `0.75 inch`, `3/4 inch`, `1 1/8 inch` or `29,000 ksi`, as an exact rational in SI. It has the unit table of `petra/units.py` with the same exact factors: an inch is 127/5000 m, and a pound-force is 0.45359237 kg times 9.80665 m/s2.
- A number alone, such as `0.90` or `3/2`: digits with an optional sign, and then a decimal part or a denominator. It takes no exponent, no space and no underscore.
- An expression, as a list of tape nodes. A whole power is a `pow`, a half power is a `pow` of a `sqrt`, a negative one is 1 over it, and any other power is `exp` of the exponent times `ln`. Cases and tables are a `pick`.

The kernel is stricter than `petra/grid.py` in three ways. A name, a unit and a text are JSON strings, and a flag is `true` or `false`: Python also takes a number where a text goes, except for what a field is, where both ask a text. The names of `let` may be read in any order, because the kernel's JSON reader keeps no order of keys, where Python reads them in the order of the file. And the limits below apply.

## proofs.json

| Key | Holds |
|---|---|
| `format` | `"petra-proofs/0"` |
| `cells` | One cell per obligation |

A cell has `subject`, `mechanism`, `entry` and `state`. The state is one of `proved`, `refuted`, `not_applicable`, `waived` and `open`.

For a design with no parts a cell is what the kernel checks. A `not_applicable` or `open` cell has `why`, and a cell may carry a tape.

For a design with parts a cell is a hint for the kernel's own cell of the same subject, mechanism and entry. It carries no tape, and the kernel reads none: it writes the tape from the deck of rules. A `proved` hint has a `partition`, and a `refuted` one a `point`. A hint may also carry `why` and `rule`, the rule's id, which the kernel does not read.

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
| `["pick", [[COND, i], ...]]` | Node `i` of the first case whose condition holds |

A `pick` is how a tape writes a table or an equation with cases. Each case is a condition and a node, and the pick's value is the node of the first case whose condition holds. A condition is `["le", i, j]` (node `i` is at most node `j`), `["lt", i, j]` (node `i` is less than node `j`), `["and", [COND, ...]]`, `["or", [COND, ...]]` or `["not", COND]`. The last case may have `null` for its condition, and then it holds when no case before it does. A pick has at least one case, and an `and` or an `or` has at least one member.

On a box the kernel may not know the order of two nodes that a condition compares, so it tries every order their enclosures allow. For nodes `a` and `b` with enclosures `[a.lo, a.hi]` and `[b.lo, b.hi]`, `a` can be below `b` when `a.lo < b.hi`, equal to it when `a.lo <= b.hi` and `b.lo <= a.hi`, and above it when `a.hi > b.lo`. A node compared with itself is equal. The kernel takes each pair of compared nodes once, and goes through every way of choosing one allowed order for each pair. In one way every condition is true or false, so at most one case is the first to hold. The pick's enclosure is the least range that contains the enclosure of every case that is first in some way. So a thickness exactly on the end of a band takes one band, the one whose condition holds at the end, and a range that straddles the end takes both. Each pair is chosen on its own, which can add a case that no point of the box takes and never drops one that a point takes.

A pick has no value on a box when some way leaves no case that holds, and when there are more than 4,096 ways. The conditions of one pick hold at most 1,024 orders between them ([Limits](#limits)). A node with no value on a box, such as that pick or a division by a range that contains zero, fails the proof only where a root reads it. A root reads through arithmetic, through the nodes a pick compares and through the cases that are first in some way. So a case that is never first may have no value there. A refutation reads a pick by the same rule, with its point as the box.

The kernel writes a tape from a rule with one node for each distinct quantity. Two cases that compare the same quantity with the same value then compare the same pair of nodes, and the cases of a table meet.

### Partitions and points

A `proved` cell with a tape has a `partition`: the string `"leaf"`, or `{"input": k, "at": x, "below": P, "above": P}`, which splits input `k` at `x`. The value `x` lies strictly inside the range the input has at that point of the tree.

A `refuted` cell with a tape has a `point`, one value per input and inside its range, and `which`, the index into `roots` of the root that is more than zero there.

A hint names an input by its label, because the tape is the kernel's. Its partition is `"leaf"` or `{"input": "in:NAME.x", "at": x, "below": P, "above": P}`. Its point is an object with a value for each label, `{"in:NAME.x": "3/2", ...}`, and it has no `which`: a rule's cell has one root.

## The rules

The kernel applies the rules in this order. A design that breaks a rule of the first four groups is ILL-FORMED, and the kernel settles no cell.

**Shape.** Each file is JSON with its `format`. Every number parses, and every range has `lo <= hi`. A cell has its keys and a state from the list, and a node is one from the table. A part's name is within the limit below. A tape that reads a node ahead of itself, or lacks its `partition`, `point` or `which`, leaves its cell open.

**Types.**

1. The design's `card` is the SHA-256 of the card file's bytes.
2. The design has no key but `format`, `name`, `card`, `quantities`, `params` and `parts`.
3. Every quantity of role `size` has `lo` above `domains.size.min`, or at it when `strict` is false.
4. Every input whose dimension is in `domains.input` has `lo` at or above that floor, or above it when `strict` is true.
5. Every waiver of the card names a `by`.
6. A design with `parts` comes with `--rules`.
7. A file that only a design checked against a deck of rules has comes with `parts` in the design and with `--rules`. There are three such marks: an input of the card with `on` or `field`, the key `tests` or `probability_claims` in the card, and the key `rules` in deck.json. Each mark is a finding when the design has no `parts` or `--rules` names no deck.

Rule 7 is what stops a downgrade. Without it, a card issued for a deck of rules could be handed to the kernel with a design stripped of its `parts` and with no `--rules`. The kernel would then check the cells that proofs.json lists, and a `not_applicable` cell there is taken as stated.

**The deck of rules.** With `--rules`, the file is a deck that holds together, as [deck.md](deck.md) describes: it has no unknown key, every rule names rows, fields and loads that exist, every input of a row is bound once and to its dimension, both sides of every inequality have one dimension, every sum and comparison inside a row or a rule is of one dimension, every rule answers a line of the grid that can arise, and no two rows, types, lines or rules have one name. A name of a field, a load, a joined part or a `let` is letters, digits and `_`. These names, the name of a mechanism and the id of a rule are within the limit below.

**Parts.** With `--rules`, the design and the card are parts of the deck's types:

1. Every part has a type of the deck and a name no other part has.
2. A part has every field of its type once, and no other line.
3. A quantity is one number or one given, of the field's dimension, more than zero and at least the field's `least`. A `whole` field is one whole number that the design writes. A `signed` field is a given. A given is named `PART.FIELD` for the part and the field that read it, and the card has one input of that name, which is no load.
4. A key is one word or one text, and one of the field's names.
5. A field that joins parts has one word for each name in its `as`, and they name different parts of the field's type. No part is joined more than once.
6. Every input of the card has a name of its own, and is a load or a given that a part reads. A load has `case`, `on` and `field`: it is on a part, it is one of the loads of that part's type, of its dimension and at least its `least`, and no case puts one load on one part twice. The name of its case is within the limit below.
7. Every waiver names a part and a mechanism that the grid asks of that part's type.
8. The card has no claim, no tests record and no probability claim, and the design has no param.

**Cells.** For each cell of a design with no parts:

1. `proved` with a tape: every input is labelled `in:`, `reg:` or `dsg:`. An input labelled `in:NAME.INPUT` is input `INPUT` of the card named `NAME`, and every input labelled `reg:` is a constant of the deck. The tape's range for it contains the card's or the deck's. The kernel evaluates every root on every leaf of the partition by the interval rule, and the upper end of each is at most zero. A cell that meets all of this is proved. Otherwise it is open, and the verdict says which test failed.
2. `refuted` with a tape: the same test on labels. Each value of the point lies in its input's range and in the card's or the deck's range for that label, and two inputs with one label have one value. The lower end of root `which` at the point is above zero. A cell that meets this is refuted. Otherwise it is open.
3. `proved` or `refuted` with no tape is open: the kernel has no rule for its proof yet.
4. `waived` holds only when the card lists a waiver with the same `subject` and `mechanism`. Otherwise it is open.
5. `not_applicable` is taken as stated, and counted.

**Cells from a deck of rules.** With `--rules` the kernel makes the cells itself, in this order: for each part in the design's order, each line the grid has for its type in the deck's order, and then each field that nothing reads.

1. A line whose mechanism the card waives on the part is one `waived` cell.
2. Otherwise, a line whose `unless` holds for the part, or that has an `unless` with no condition, is one `not_applicable` cell.
3. Otherwise, each rule for the line whose `when` holds for the part gives cells, and a line with no such rule is one `open` cell. These three have an empty `entry`.
4. A rule that reads no load gives one cell. Its `entry` is the rule's id from its last `/` on, so `lap-yield-a` for `aisc360-22/lap-yield-a`. A rule that reads loads gives one cell for each load case that puts every load it reads on the part, in the order of the cases' names, and the `entry` then ends in `/CASE`. It gives one `open` cell when the card puts one of its loads on the part in no case, or no case has them all.
5. A rule with `where` needs its range first. The kernel writes a tape with one root for each inequality of `where` and looks for a hint with the cell's entry and `/where`. When a partition of such a hint proves every root, that is a `proved` cell with that entry, and the rule's cell follows. When none does, the rule's cell is `open` and there is no `/where` cell: outside its range a rule proves and refutes nothing, whatever the hints say.
6. The rule's cell has a tape with one root, the left side of `le` less the right. The kernel tries each hint for the cell in the file's order. A partition that proves the root makes the cell `proved`. A point that has a value for every input, each inside the range the card or the design gives it, with the root above zero there, makes it `refuted`. The first hint that does either settles the cell. With none it is `open`. The state a hint claims decides nothing.
7. A tape that cannot be written leaves the cell `open`: a table has no line for the part's key, every cell it could read is empty, or an equation or a table would be a pick of more than 1,024 orders.
8. A quantity or a key of a part is read by a rule that applies to the part, by a rule that applies to the part that joins it, or by an `unless` of the grid's lines for its type. Each one that nothing reads is one `open` cell, with mechanism `unread` and the field as its `entry`.

A hint for a cell that the kernel does not have is ignored and counted. So proofs.json can leave a cell open that a better search would settle, and it can do nothing else: it cannot add a cell, drop one, or change what a cell says.

The interval rule is the one in `petra/kernel/interval.py` and `petra/kernel/evaluate.py`: exact rational intervals, with `sqrt`, `ln`, `exp` and pi rounded outward on a grid of 2^-96. An `ln` or an `exp` is rounded from an enclosure of 128 bits, and from one of 224, 608 and then 2,144 bits when the one before has a point of the grid inside it. The two kernels give the same ends for every root. The Python kernel has no `pick`: `petra/grid.py`, which searches for the partitions and the points, reads a pick by the same rule a second time.

## The verdict

| Verdict | When | Exit code |
|---|---|---|
| ILL-FORMED | A rule of the first four groups is broken, or the design is past a limit on its cells | 3 |
| FAIL | A cell is refuted | 1 |
| UNKNOWN | No cell is refuted, and a cell is open or no cell is proved | 2 |
| PASS | Every cell is proved, waived or not applicable, and at least one is proved | 0 |

The kernel prints one JSON object: `verdict`, the `hashes` of the files, where `rules` is null when `--rules` names no deck, `cells_from` (`rules` when the kernel made the cells from a deck of rules, and `proofs` when it took the list of proofs.json), `findings` (the first 100 broken rules, each with the file and the item), `more_findings` (how many more there were), `counts` (the cells in each state), `dsg_inputs` (the distinct `dsg:` labels the settled proofs read), `work` (the units of work the proofs took, as [Work](#work) counts them), `waived` (each waiver a PASS rests on, once) and `cells`. With `--rules` it also prints `ignored_hints`. A cell has its subject, mechanism and entry, `claimed`, `state`, the state the kernel settled on, and `reason` when the kernel left it open. `claimed` is the state the file claims for the cell. With `--rules` it is the state of the first hint for the cell, and null when there is none. A command line it cannot read prints the usage and exits 64.

For a design with parts, `petra check` compares the kernel's cells with the ones `petra/grid.py` made: the same count, and at each place the same subject, mechanism, entry and state. It also holds the kernel to `cells_from` at `rules` and to the hash of the deck it used itself. Any difference raises `petra.verify.Disagreement`, and `petra check` exits 4. `python bench/kernel_grid.py` makes that comparison on generated designs. The report of `petra check` prints the hash of the deck of rules on its `rules` line.

## Reading a verdict

A verdict is about the files the kernel was given. Three things in it say which files those were. A reader checks all three before taking a PASS.

| In the verdict | Says | The reader checks |
|---|---|---|
| `cells_from` | `rules`: `--rules` named a deck of rules, and the kernel made every cell from it. `proofs`: there was no deck of rules, and the kernel checked the cells that proofs.json lists. | That it is `rules`, for a design that was to be checked against a deck of rules. |
| `hashes.rules` | The hash of the deck of rules the kernel read, or null when it read none. | That it is the hash of the deck the reader trusts. |
| `hashes.card` | The hash of card.json. | That it is the hash of the card.json that the asker's own card gives. |

A PASS means "checked against a deck of rules" only when `hashes.rules` is the hash of the reader's trusted deck. The kernel cannot know which deck that is. A deck with a rule left out, or with a limit raised, holds together like any other, and the kernel reads it and prints its hash. A PASS with `cells_from` at `proofs`, with null for the rules, or with the hash of some other deck, says nothing about the reader's deck.

A PASS is about the asker's card only when `hashes.card` is the asker's. A designer who lowers a signed load in card.json gets a PASS from a kernel that did its work, under the same card name, and only the hash shows it.

## The asker's card

For a design with parts, card.json is a function of the card's text alone. It holds each given under the name the card gives it, each load with the part and the field the card puts it on, and each waiver. Nothing in it comes from the design. So the asker can work out its hash with no design, with their own copy of Petra:

```
python -m petra.export --card-only CARD.card --out DIR
```

The command writes `DIR/card.json` and prints its hash. It reads no design, so what the card says of a part is not checked against any. It exits 3 and writes nothing for a card the language refuses.

The asker runs it on the card they issued, and compares the hash it prints with `hashes.card` in the kernel's verdict.

- The two are the same: the verdict is about the asker's card.
- They differ: the card.json the kernel read states something else. It may give a load another range, waive a mechanism the asker did not, or hold a bound the asker never gave.

The comparison holds for a design with parts only. For a design of the models' kinds card.json takes names from the design, so its hash is not the one this command prints. `tests/test_export_card.py` compares the two files, byte for byte, for every pair of `examples/deck` and `corpus/cases/deck`.

## Limits

The kernel stops work that would not end. A tape has at least one root. A partition is at most 64 deep, and a `pow` exponent at most 64 in magnitude. A condition of a pick in a tape that a file carries nests at most 16 deep, where `le` or `lt` alone is 1 deep. The conditions of one pick hold at most 1,024 orders between them, in a tape that a file carries and in one the kernel writes. A value with more than 65,536 bits, or an `exp` of a number beyond 65,536, leaves its cell open. A pick has no value on a box where it has more than 4,096 ways to order the nodes it compares. A file's JSON nests at most 128 deep, and a number outside a string has at most 32 digits and no fraction or exponent.

A deck of rules has three more. A quantity or a number is at most 4,000 characters. A whole or a half power has an exponent of at most 64 in magnitude. An expression nests at most 1,024 deep, counted through the names of `let` it reads and the rows it applies, so a name of `let` that reads itself, or a chain of names longer than that, is refused. `petra/grid.py` has the second of these and not the other two.

The time a verdict takes, what the kernel holds while it works and what it prints are each bounded, whatever the files hold. Ten limits see to that.

| Limit | Value | Past it |
|---|---|---|
| Findings in `findings` | 100 | The kernel keeps the first 100, and `more_findings` counts the rest. |
| The item or the reason of a finding, and the reason of a cell | 200 bytes as printed | The text is cut, and ends with how many characters were left out. |
| The name of a part, and of a load case that puts a load on a part | 64 bytes as printed | A shape finding |
| In a deck of rules: the name of a field, a load, a joined part and a `let`, the name of a mechanism, and the id of a rule | 64 bytes as printed | The deck does not hold together |
| Cells made from a deck of rules | 10,000 | A finding of the rule `limits`, and the design is ILL-FORMED |
| Steps to write the tapes of a design from a deck of rules | 10,000,000 | A finding of the rule `limits`, and the design is ILL-FORMED |
| Work for the proofs of one verdict | 20,000,000,000 units | A proof that cannot pay for its tape is not tried, and a step that cannot pay is not taken. The cell is open, and the reason says so. |
| Enclosures held at once while one leaf is walked | 16,777,216 words of 64 bits, which is 128 MB | The node whose enclosure would go past it has no value. |
| Entries in the cache of `ln` and in the cache of `exp` | 1,024 each | The cache starts again from the new entry. |
| Times a waiver is printed in `waived` | 1 | Cells that rest on one waiver print it once. |

A name of 64 characters in ASCII prints in 64 bytes. A character outside ASCII prints in up to four, a quote, a backslash and a line end in two, and any other control character in six. A cell prints these names whole, so they are refused and not cut. A step is one name or one operator of a rule and each thing the operator reads, each time the rule is written for a part and a load case, or one node of the tape. A pick counts each order of its conditions, and a table each of its cells.

### Work

A proof pays for what it does, in units of work, from what its verdict has left. A unit is about what one operation on one 64-bit word of a number costs: a nanosecond or so on a desktop. The kernel counts the words of the numbers a step reads and charges the step before it takes it. So the count is a bound on the time, set before the time is spent, and not a measure of it.

- **The fee.** Before its first step a proof pays for its tape: the size of the tape three times, and once more for each leaf of its partition, with 20,000 units and 8 for each input for the split that made the leaf. The size of a tape is 60 units for each node and 15 for each node it reads, and for a pick 2 for each of its orders times each distinct pair of nodes it compares. A refutation pays as a proof with one leaf, and 20,000 for each input. A proof whose fee is more than the work left is not tried and pays nothing.
- **The steps.** Each step then pays by the 64-bit words of the numbers it reads. A term of a sum pays for the words of the sum so far times the words of the term. A factor of a product and a quotient pay for the square of the words of both, because the kernel compares the four products of the ends with each other. A least, a greatest and each pair a pick compares pay for the product of the words of the two. A square root pays for the square of the words of its whole part. A power pays for its exponent squared times its words squared. An `ln` pays for the square of its words, and for the square of the bits of its enclosure times its words. An `exp` of `x` works with about twice `x` bits, sums about that many terms over their logarithm, and pays for the terms times the bits times its words. An `ln` or an `exp` of a number the cache holds pays for the look. A pick pays for each way it tries times its orders times its pairs. A step that costs more than the work left is not taken, and its node has no value, as a node that divides by zero has none.
- **The count.** The kernel takes the work of each proof from what is left, in the order of the cells. A proof that fails has spent what its steps took. The verdict prints the work its proofs took as `work`.

A step that rounds to the grid pays for each enclosure it asks for, before it asks. So an `ln` or an `exp` whose value lies close to a point of the grid pays for the finer enclosures too, and one that does not pays for the first alone.

The heaviest design of the corpus, `weld_bracket`, takes 3.2 billion units in under three seconds: a sixth of the budget. The next takes 0.1 billion, and a lap of the first deck of rules 2.5 million. Files under 1 MB made to spend all 20 billion on one kind of step took between 4 and 15 seconds on the desktop the costs were fitted on, a four-core machine of 2017, and held at most 220 MB. The slowest was one pick of 1,024 orders over twelve inputs on 2,000 leaves, in 116 KB of files. A busy machine takes longer in proportion. `tests/test_kernel_limits.py` and `tests/test_kernel_attacks2.py` hold the limits one by one.

### What the kernel holds and prints

The kernel walks the leaves of a partition one at a time. On a leaf it gives up the enclosure of a node after the last node that reads it, and it holds at most 128 MB of enclosures at once. So what it holds is the files as it read them, the enclosures of one leaf, and two caches of at most 1,024 entries each.

A cell made from a deck of rules prints in at most about 600 bytes, and all of them in about 6 MB. A cell that proofs.json lists prints once, in under three times its own bytes.

`petra/grid.py` holds a name to the same 64 bytes, counted the same way, so it refuses the same decks and designs. It has none of the other limits. `petra check` reports a design past the limit on cells or on steps as an input error, in the kernel's words. A proof the kernel does not finish for the budget of work, or does not write for the limit on a pick's orders, leaves a cell open that the grid proved, and `petra check` stops with exit code 4 and the kernel's reason.

## What the kernel does not check yet

For every design:

- The numbers in card.json and design.json are in SI, and the Python front end converted them from the units the card and the design write. The kernel reads the units of a deck of rules itself, and not those of a card or a design. It checks that a part's number has the dimension its field asks, by the name of the dimension that the file states.
- card.json is not a function of the card's text alone for a design of the models' kinds: an input that a component reads with `given` takes its name from the component. So the hash of card.json identifies a card together with a design, and the hash `petra check` prints on its `card` line, of the card's text, is the one to compare with the card that was issued. For a design with parts card.json is a function of the card alone ([The asker's card](#the-askers-card)).
- The interval rule is proved in Lean: a tape that the kernel proves has every root at most zero on its box, and a point it accepts as a refutation has its root above zero ([proved.md](proved.md)). Nothing else on this page is proved. For the shape and type rules, the deck of rules, the cells and the verdict, the kernel is a second implementation, and `bench/kernel_grid.py` and the corpus compare it with the first.

For a design with no parts:

- The list of cells comes from Python, from the models' coverage rules. The kernel checks each cell and not that the list is complete.
- A tape's formula comes from Python's models. The kernel checks its arithmetic and its `in:` and `reg:` inputs, not that the formula is the standard's.
- Inputs labelled `dsg:` are the design's values as the models resolved them. The kernel does not tie them to `quantities`, and the verdict counts them.
- A `not_applicable` cell is the model's word.
- Proofs by the other five rules have no tape, and neither has an interval proof that leans on a defined quantity.
- A cell holds the proof of its own statement. The proofs that its model applies there (its validity rows) and the proof of a claim's margin are not in the file. `petra check` counts them among the proofs the kernel has no rule for.

For a design with parts:

- The deck of rules is the one `--rules` names. The kernel prints its hash and does not know whether it is the deck a reader means, or whether its rows are the standard's. [deck.md](deck.md) says what stands behind a row, and that nothing yet stands behind a type, a grid line or a rule but the hand that wrote it.
- The search for a partition or a point is Python's. A search that finds nothing leaves a cell open that may be provable. It cannot make a cell proved or refuted.
- The card that `petra.export` writes for a design with parts is refused without `parts` or without `--rules` (type rule 7). A card.json written by hand without the marks of rule 7 is not. With a design that has no `parts` it is checked as a design of the models' kinds, by the cells that proofs.json lists. That card.json has another hash than the asker's, and the verdict prints `cells_from` as `proofs` and null for the rules. What remains open is a reader who compares none of the three ([Reading a verdict](#reading-a-verdict)).
- `quantities` repeats the numbers of `parts` for the size rule. The kernel reads a part's numbers from `parts` and does not compare the two.
- The card's `cases` and `environment` are not read for a design with parts. A load case is the `case` of a load.
