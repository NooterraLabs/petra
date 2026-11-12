# What the kernel reads

`petra-verify` reads four JSON files, and a fifth for a design checked against a deck of rules, and prints one verdict. This page describes the files, the rules the kernel applies to them, and the verdict. The format is version 0 and will change.

```
petra-verify --card card.json --design design.json --deck deck.json [--rules rules.json] [--proofs proofs.json]
```

`petra check` writes the files for its report and runs the kernel on them when it finds one. It looks in three places, in this order: the file the environment variable `PETRA_VERIFY` names, the kernel inside the installed package, and `kernel/.lake/build/bin/petra-verify` in a source tree. A wheel from PyPI carries the kernel as `petra/bin/petra-verify`, or `petra-verify.exe` on Windows. Petra installed from the sdist carries none, and its report then says on the `kernel` line that no kernel ran. `petra check` prints how many of the proofs behind its status the kernel checked, and exits 4 if the kernel rejects one that the Python checker accepted.

The kernel trusts none of the files. It checks that they agree with each other and that each proof holds. Who wrote each file is outside the kernel: the verdict prints the SHA-256 of the card, the design, the deck and the rules, and a reader compares the card's hash with the card they issued and the rules' hash with the deck of rules they mean. [Reading a verdict](#reading-a-verdict) says what a PASS means without that comparison: very little.

`python -m petra.export FILE.petra [--card FILE.card] --out DIR` writes the files from a design and its card, the `.card` file beside the design unless `--card` names another. It exits 3 and writes nothing when the language refuses the pair, as it does for a design that states a load, a claim, a waiver or a signature. With `--no-physics` it writes no proofs.json, and a design with parts is then written as it stands, for the kernel to say whether the deck's types take it. With `--card-only FILE.card` and no design it writes card.json alone and prints its hash ([The asker's card](#the-askers-card)).

There are two kinds of design, and the kernel does more for the second.

- A design of the built-in models' kinds has no `parts`. The kernel checks each cell that proofs.json lists, with the tape the cell carries.
- A design whose parts are of a deck of rules ([deck.md](deck.md)) has `parts`, and goes with `--rules`. The kernel reads the deck of rules, works out every cell and every tape itself, and takes from proofs.json only hints: a partition or a point to try.

## Numbers

Every number is a string that holds an exact rational: an integer such as `"18"` or a fraction such as `"-5463/20"`. A fraction is in lowest terms with a denominator above 1, and no number has a leading zero or is `-0`. A string longer than 4,000 characters is refused. A range is a pair `lo`, `hi` with `lo <= hi`.

A `dim` names a dimension. In card.json, design.json and deck.json it is one of `dimensionless`, `length`, `area`, `force`, `stress`, `mass`, `time`, `temperature`, `energy`, `moment`, `current`, `voltage`, `power`, `resistance`, `I2t` and `resistance per length`, or the exponents of metre, kilogram, second, ampere and degree Celsius that are not zero, as in `m^3 s^-1`: each a base, `^` and a whole number, with one space between two. Two names are one dimension when their exponents are equal, as `moment` and `energy` are, and `length` and `m^1`. Wherever the kernel compares two dimensions or looks one up, it does so by the exponents and never by the spelling.

In the form with exponents, the bases are `m`, `kg`, `s`, `A` and `degC`. They may stand in any order, and a base may stand more than once: its exponents are then added, so `m^1 m^1` is `m^2` and `kg^1 m^1 s^-2` is a force. Each base has its `^` and its whole number. The number may be zero or negative, may have leading zeros and has no `+`: `m` alone names no dimension, and `m^0` is the dimensionless. The empty text names no dimension, and neither does a text with two spaces together or with a space at either end.

The kernel holds an input of the card to this (type rule 4), and the number of a part, whose `dim` must be the dimension of its field (Parts 3). The `dim` of an item of `quantities`, of `params` and of the `bound` of a claim is a text that the kernel reads no further: it is not held to name a dimension.

### Texts

No text of a file and no key of an object holds U+FFFD, the replacement character, and the kernel refuses a file that has one anywhere. The reason is the escape `\uXXXX`. A character outside the first 65,536 is written as two escapes, a surrogate pair, and the kernel reads the pair as that character. Half a pair alone is no character, and the kernel's JSON reader reads it as U+FFFD. So once a file is read, `"a\ud800"`, `"a\udfff"` and `"a�"` are the same text, and the kernel cannot tell which the file wrote. Three names that differ in the file would be one name, and a waiver for one would rest a cell of another. A reader that keeps half a pair as it is refuses a text with half a pair in it, and a text with U+FFFD, to refuse what the kernel does.

A deck of rules writes its own numbers another way, with units. [The rules file](#rulesjson) says how the kernel reads them.

## card.json

What the asker owns.

| Key | Holds |
|---|---|
| `format` | `"petra-card/0"` |
| `name` | The design's name. A premise label `in:NAME.INPUT` names an input of this card. |
| `environment` | A registry id, or null. For a design with parts it is null: a deck of rules reads no environment yet, and a card that states one is refused (Parts 8). |
| `cases` | The names of the load cases. For a design with parts, the load cases of the card are these names and the `case` of each load, each once. |
| `inputs` | Every bound: `name`, `dim`, `lo`, `hi`, `by`, and `case` for a load. An input with no `by` is one nobody signed, and the kernel refuses the card. The exporter writes one for a load or an ambient that reads a param. An input whose `by` is the empty text is refused too (type rule 5). |
| `claims` | Each claim: `name`, `subject`, `quantity`, `rel`, `cases`, `bound` |
| `waivers` | Each waiver the asker allows: `subject`, `mechanism`, `by`, `reason` |
| `states` | For a design with parts: each key and each count the card states exactly. A card that states none has no such key. |

For a design with parts, a load's input also has `on`, the part the load is on, and `field`, which of the loads of the part's type it is. An input with none of `case`, `on` and `field` is a given, and its name is `PART.FIELD`, the part and the field that read it. The card also has `tests` and `probability_claims`, the names of its tests records and its probability claims. A deck of rules reads neither yet, so the kernel refuses a card that has one.

An item of `states` is what the card states of one field of one part with no range: the name of a key, or a whole number ([deck.md](deck.md), "What the card states of a part").

```json
{"name": "b.category", "by": "rigging@example.org", "key": "B"}
{"name": "b.lugs", "by": "rigging@example.org", "whole": "2"}
```

It has `name`, which is `PART.FIELD` as a given's is, `by`, and exactly one of `key`, a text, and `whole`, a whole number written as every number of the file is: `"2"`, `"-3"`, and never `"2.0"`, `"02"` or `2`. It has no other key. An item that breaks this is a shape finding and is left out. A statement is no input: it has no `dim`, no `lo` and no `hi`, type rule 4 does not read it, and no tape's range is tested against it. The exporter writes the items in the order of their names, and writes no `states` at all for a card that states none, so the card.json of such a card is byte for byte what it was before a card could state a key.

Only the card of a design with parts has `on`, `field`, `tests`, `probability_claims` and `states`, and the exporter writes `tests` and `probability_claims` into every such card, as empty lists when the card states none. So the kernel takes each as a mark of a card for a deck of rules, and refuses the card with a design that has no parts or with no `--rules` (type rule 7).

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
| `domains.input` | For each dimension that has a floor, `min` and `strict`. A dimension that is not listed has none. Each key names a dimension, and a key that names none is a shape finding. So is a key whose value lacks `min`, a number, or `strict`, which is `true` or `false`. The key `about` is prose and is not read. Two keys of one dimension, as `length` and `m^1`, give it one floor: the higher of the two, and the strict one when both are at one height. |
| `constants` | Each registry value a proof reads: `label` (`reg:KEY`), `lo`, `hi` |
| `rules` | For a design checked against a deck of rules: the `name` of that deck and the `hash` of its file. The kernel reads only that the key is there (type rule 7). It reads the deck of rules itself, from `--rules`. |

`petra/decks/core.json` holds the domains.

## rules.json

The deck of rules a design with parts is checked against: the file of `petra/decks` as it ships, with `"format": "petra-rules/0"`. [deck.md](deck.md) describes it. `petra check` and `petra.export` hand the kernel the file's own text, so the hash the kernel prints for it is the hash of the deck.

The kernel reads the whole deck and refuses one that does not hold together, as `petra/grid.py` does when it loads one. It reads these itself, and takes none of them from Python:

- A dimension, such as `force/length` or `length^3`, as five exponents of metre, kilogram, second, ampere and degree Celsius. They are rational, because a square root halves them.
- A quantity with its unit, such as `0.75 inch`, `3/4 inch`, `1 1/8 inch` or `29,000 ksi`, as an exact rational in SI. It has the unit table of `petra/units.py` with the same exact factors: an inch is 127/5000 m, and a pound-force is 0.45359237 kg times 9.80665 m/s2. A unit of length may be raised to the power 2, 3 or 4, as in `mm^3` and `inch^4`, and its factor is then the unit's own to that power ([deck.md](deck.md), "Dimensions"). A number of a design in such a unit reaches the kernel in SI, with the `dim` `m^3` or `m^4`.
- A number alone, such as `0.90` or `3/2`: digits with an optional sign, and then a decimal part or a denominator. It takes no exponent, no space and no underscore.
- An expression, as a list of tape nodes. A whole power is a `pow`, a half power is a `pow` of a `sqrt`, a negative one is 1 over it, and any other power is `exp` of the exponent times `ln`. A cosine is a `cos`. Cases and tables are a `pick`.
- A rule with no value where a field says it may be. Once a rule's nodes are written, the kernel refuses a `div` whose divisor a field or a load that says `may_be` stands for, a `sqrt` of one that says `"may_be": "negative"`, and an `ln` of either. A node stands for a field when it is the field's input, the field again where the rule names it twice, a `pow` other than the 0th of a node that stands for it, or a `sqrt` of one. An even `pow` of a field that may be under zero stands for one that may be zero. A `let` and an input of a row are the node they are bound to, so this follows them. No other node stands for a field: a sum or a product that holds one may be zero, and its cell is then open ([deck.md](deck.md), "A quantity at or under zero").

The kernel is stricter than `petra/grid.py` in three ways. A name, a unit and a text are JSON strings: Python also takes a number where a unit or another text goes. A flag of a field, `signed`, `whole` and `optional`, is `true` or `false` for both, and `may_be` is one of its two texts for both. A name is a JSON string for both: the name of a type, of a field, of a load, of a joined part, of a mechanism, of an input of a row, of a side that `rises` or `falls` names, and the id of a row and of a rule. The names of `let` may be read in any order, because the kernel's JSON reader keeps no order of keys, where Python reads them in the order of the file. And the limits below apply.

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
| `["cos", i]` | The cosine of node `i`, an angle in radians |
| `["div", i, j]` | Node `i` over node `j` |
| `["pow", i, n]` | Node `i` to the integer power `n` |
| `["pick", [[COND, i], ...]]` | Node `i` of the first case whose condition holds |

`cos` is the one node for angles. A tape has no sine, no tangent, no inverse of them and no degrees: a sine is the cosine of a quarter turn less the angle, and an angle in degrees is multiplied by pi over 180 on the tape, with the tape's pi ([deck.md](deck.md), "Expressions").

**The cosine of an enclosure.** Between `k` pi and `k + 1` pi the cosine falls when `k` is even and rises when `k` is odd, and at `k` pi it is 1 or −1. So the kernel first places the enclosure `[lo, hi]` of the angle among the multiples of pi, with its own enclosure of pi, two fractions 2^-96 apart. It finds a whole number `i` with `i` pi at or under `lo` and a whole number `j` with `hi` at or under `j` pi. Each is tested with the end of pi that makes the test harder: `i` times the upper end of pi is at most `lo` for an `i` of zero or more, and `i` times the lower end for an `i` under zero, and the other way round for `j`.

| The enclosure lies | The enclosure of its cosine |
|---|---|
| Between `i` pi and `i + 1` pi: `j` is at most `i + 1` | For an even `i`, from the grid point at or under cos `hi` to the grid point at or over cos `lo`. For an odd `i`, from the one at or under cos `lo` to the one at or over cos `hi`. |
| Over `i + 1` pi, or so near it that pi does not say: `j` is `i + 2` | For an even `i`, from −1 to the greater of the grid points at or over cos `lo` and cos `hi`. For an odd `i`, from the lesser of the grid points at or under them to 1. |
| Over more: `j` is over `i + 2` | From −1 to 1 |

The grid is the one `sqrt`, `ln` and `exp` round to, of 2^-96. The cosine of zero is 1, and the cosine of any other fraction is no fraction, so it lies strictly between two neighbouring grid points, and those are its enclosure: the kernel sums the series of the cosine with its remainder until an enclosure has no grid point inside it, as it does for `ln` and `exp`. An enclosure of a cosine never reaches past 1 or −1. So an angle next to a multiple of pi, whose cosine is closer to 1 or to −1 than the grid is fine, has the last step under 1, or the first over −1, for its enclosure. An end that the kernel's pi does not place on one side of a multiple of pi counts as on both sides, the second line of the table: the enclosure then reaches to 1 or to −1, which is within a step of the cosine of that end.

A `cos` has no value in three cases. Its angle has none. Its angle's enclosure reaches below −65,536 or above 65,536. Or the cosine of an end is closer to a grid point other than 1 and −1 than the finest enclosure is wide, which is 2^-2144: the cosine of a fraction that agrees with an odd multiple of a quarter turn to some 640 digits is that close to zero.

A `pick` is how a tape writes a table or an equation with cases. Each case is a condition and a node, and the pick's value is the node of the first case whose condition holds. A condition is `["le", i, j]` (node `i` is at most node `j`), `["lt", i, j]` (node `i` is less than node `j`), `["and", [COND, ...]]`, `["or", [COND, ...]]` or `["not", COND]`. The last case may have `null` for its condition, and then it holds when no case before it does. A pick has at least one case, and an `and` or an `or` has at least one member.

On a box the kernel may not know the order of two nodes that a condition compares, so it tries every order their enclosures allow. For nodes `a` and `b` with enclosures `[a.lo, a.hi]` and `[b.lo, b.hi]`, `a` can be below `b` when `a.lo < b.hi`, equal to it when `a.lo <= b.hi` and `b.lo <= a.hi`, and above it when `a.hi > b.lo`. A node compared with itself is equal. The kernel takes each pair of compared nodes once, and goes through every way of choosing one allowed order for each pair. In one way every condition is true or false, so at most one case is the first to hold. The pick's enclosure is the least range that contains the enclosure of every case that is first in some way. So a thickness exactly on the end of a band takes one band, the one whose condition holds at the end, and a range that straddles the end takes both. Each pair is chosen on its own, which can add a case that no point of the box takes and never drops one that a point takes.

A pick has no value on a box when some way leaves no case that holds, and when there are more than 4,096 ways. The conditions of one pick hold at most 1,024 orders between them ([Limits](#limits)). A node with no value on a box, such as that pick or a division by a range that contains zero, fails the proof only where a root reads it. A root reads through arithmetic, through the nodes a pick compares and through the cases that are first in some way. So a case that is never first may have no value there. A refutation reads a pick by the same rule, with its point as the box.

The kernel writes a tape from a rule with one node for each distinct quantity. Two cases that compare the same quantity with the same value then compare the same pair of nodes, and the cases of a table meet.

### How the kernel writes a table

A table of a deck becomes picks, in one fixed way. Each side of the table gives a list of places, each with a condition or with none.

- **A side read by a key** gives one place with no condition: the place of the name the key has for the part, read from the key field, through the map of a `by`, or fixed by `["key", NAME]`.
- **A side read by a quantity `x` in bands** gives one place for each band, in order. For bands closed at the upper end the condition is `["and", [["lt", LO, x], ["le", x, HI]]]`, and for bands closed at the lower end `["and", [["le", LO, x], ["lt", x, HI]]]`, where `LO` and `HI` are the nodes of the band's ends. A last band with no upper end has the first comparison alone, with no `and`.
- **A side read at listed values** gives one place for each value `v`, in order, with the condition `["and", [["le", x, V], ["le", V, x]]]`.
- **A side whose key a row names** ([deck.md](deck.md), "A table that gives a name") gives one place for each cell of that row that holds a name, in the order of that row's lines and, within a line, of its cells. The place is the place of the cell's name on this side. The condition is the condition of the cell's place on that row's own side, as the two items above give it. For a row with two sides it is `["and", [DOWN, ACROSS]]` of the two. So one name may have several places here, one for each cell that holds it, and an empty cell has none.

The value of the table is then built line by line. For each place down, in order, take each place across, in order, whose cell at that line is not empty, as a case: the condition of the place across, and the constant of the cell. A table with one side has one place across, with no condition. A line with no such case has no value and is left out. A line whose first case has no condition is the node of that case. Any other line is a pick of its cases. The table is the pick whose cases are the lines that have a value, each with the condition of its place down. Where the first of them has no condition, the table is that line's node, and with no line at all the tape cannot be written.

A `case` is one pick: for each cell of its row that holds a name, in the same order, the condition of the cell and the node of the expression of its name. Every name of the row is held by a cell, or the deck does not load, so the pick has the expression of every name of the `case` among its cases, and none is left out of the tape.

Each pick is held to 1,024 orders on its own: the pick over the lines, and the pick of each line. A band with two ends has 2 orders, a band with one end 1, and a listed value 2. A cell of a row with two sides that gives a name has the orders of both its bands. An equation with cases is one pick, whose orders are the `le`, `lt`, `ge` and `gt` of its conditions. One case that holds otherwise, standing first, is its own node and no pick.

### Partitions and points

A `proved` cell with a tape has a `partition`: the string `"leaf"`, or `{"input": k, "at": x, "below": P, "above": P}`, which splits input `k` at `x`. The value `x` lies strictly inside the range the input has at that point of the tree.

A `refuted` cell with a tape has a `point`, one value per input and inside its range, and `which`, the index into `roots` of the root that is more than zero there.

A hint names an input by its label, because the tape is the kernel's. Its partition is `"leaf"` or `{"input": "in:NAME.x", "at": x, "below": P, "above": P}`. Its point is an object with a value for each label, `{"in:NAME.x": "3/2", ...}`, and it has no `which`: a rule's cell has one root.

## The rules

The kernel applies the rules in this order. A design that breaks a rule of the first four groups is ILL-FORMED, and the kernel settles no cell.

**Shape.** Each file is JSON with its `format`, and none of its texts and keys holds U+FFFD ([Texts](#texts)). Every number parses, and every range has `lo <= hi`. A cell has its keys and a state from the list, and a node is one from the table. A part's name is within the limit below, whether or not `--rules` names a deck, and with `--rules` so are the name of the card and the name of the design. Those two are tested when the deck that `--rules` names holds together. With a deck that does not, the kernel reads no part and tests neither name: the finding is the deck's. A tape that reads a node ahead of itself, or lacks its `partition`, `point` or `which`, leaves its cell open.

**Types.**

1. The design's `card` is the SHA-256 of the card file's bytes.
2. The design has no key but `format`, `name`, `card`, `quantities`, `params` and `parts`.
3. Every quantity of role `size` has `lo` above `domains.size.min`, or at it when `strict` is false. One kind of quantity is not held to this: with `--rules` and `parts`, a quantity whose `entity` is the name of a part and whose `line` is a field of that part's type that says `may_be` ([deck.md](deck.md), "A quantity at or under zero"). Parts 3 holds the number of that field to the field's own floor. The part is the first of that name in `parts`.
4. Every input's `dim` names a dimension. Every input whose dimension has a floor in `domains.input` has `lo` at or above that floor, or above it when `strict` is true. The floor is found by the exponents of the dimension, so an input written as `m^1` or as `moment` meets the floor of `length` or of `energy`. One kind of input is not held to a floor that is at zero or above: with `--rules` and `parts`, an input for a field or a load that says `may_be: negative`. For a load that is the load `field` of the type of the part `on`. For any other input it is the field named after the last `.` of the input's `name`, of the type of the part named before it. A floor under zero holds for these too: an input of a temperature is never under -5463/20, which is absolute zero in degC.
5. Every input, every waiver and every item of `states` of the card names a `by` that is not the empty text.
6. A design with `parts` comes with `--rules`.
7. A file that only a design checked against a deck of rules has comes with `parts` in the design and with `--rules`. There are three such marks: an input of the card with `on` or `field`, the key `tests`, `probability_claims` or `states` in the card, and the key `rules` in deck.json. Each mark is a finding when the design has no `parts` or `--rules` names no deck.

The shape and type rules are applied to every design, with parts or without, and with `--rules` or without.

Rule 7 is what stops a downgrade. Without it, a card issued for a deck of rules could be handed to the kernel with a design stripped of its `parts` and with no `--rules`. The kernel would then check the cells that proofs.json lists, and a `not_applicable` cell there is taken as stated.

**The deck of rules.** With `--rules`, the file is a deck that holds together, as [deck.md](deck.md) describes: it has no unknown key, wherever a key may stand, every anchor names its standard and its clause, the bands of a table are in order and none lies over another, every rule names rows, fields and loads that exist, every rule has one of `le`, `lt` and `requires`, no `when`, `unless` or `requires` asks `loaded`, every row gives a quantity or a name and not both, every name that a row gives is held by a cell of that row, every input of a row is bound once and to its dimension, a name that a row gives is read only by a key whose names hold all of that row's and by a `case` with an expression for each of them, both sides of every inequality have one dimension, every sum and comparison inside a row or a rule is of one dimension, every rule answers a line of the grid that can arise, and no two rows, types, lines or rules have one name. A name of a field, a load, a joined part or a `let` is letters, digits and `_`. These names, the name of a mechanism and the id of a rule are within the limit below. Three more keep the cells apart: no mechanism is named `unread`, a `where` that is there has at least one item, and no two rules for one type and one mechanism have ids that are the same after their last `/`. And no rule requires what no part can break or no part can meet: the kernel tries each `requires` at every combination of the names of the keys that it and its `when` name, while a rule has at most 4,096 combinations and the deck is within 1,000,000 ([deck.md](deck.md), "A rule that requires", states the count). A rule past either is read untried.

**Parts.** With `--rules`, the design and the card are parts of the deck's types:

1. Every part has a type of the deck and a name no other part has.
2. A part has every field of its type once, and no other line. A field that its type marks `optional` may be left unstated: its line then has the one argument `{"word": "unstated"}`, and the part has no value for it ([deck.md](deck.md), "A field that a record may leave unstated"). That argument on a quantity that is not optional is a finding of Parts 3, and on a key that is not optional it is the name `unstated`, which the key has or lacks (Parts 4).
3. A quantity is one number or one given, of the field's dimension and at least the field's `least`. Its lower end is more than zero. With `may_be: zero` on the field it is at least zero, and with `may_be: negative` it has no floor by its sign. A number that the design writes for a field that may be negative is also held to the floor that its dimension has in `domains.input`, when that floor is under zero: of two floors of one dimension the tighter is taken, as in type rule 4, and it holds only if it is under zero. A `whole` field is one whole number: a number that the design writes with `lo` equal to `hi`, or a given. A `signed` field is a given. A given is named `PART.FIELD` for the part and the field that read it. For a quantity that is no count the card has one input of that name, which is no load. For a count the card has one item of `states` of that name, with `whole`: the count is that number, held to the field's floor and its `least`, and a tape reads it as the input `in:CARD.PART.FIELD` with that one value. An input of that name is no count, and an item with `key` is none either: each is a finding.
4. A key is one word, one text or one given, and one of the field's names. A `signed` key is a given, and a word or a text for it is a finding. A given is named `PART.FIELD`, and the card has one item of `states` of that name, with `key`: the key has that name, which is one of the field's names. An item with `whole`, an input of that name and no item at all are each a finding, and the last names the given: `the card states no b.category`.
5. A field that joins parts has one word for each name in its `as`, and they name different parts of the field's type. No part is joined more than once. The word at each place is the part that the name at that place of `as` stands for. Which part fills which name is a statement of the design, read like any field, and nothing in a card or a deck checks it: the same parts listed in another order are another design, and may get another verdict.
6. Every input of the card has a name of its own, and is a load or a given that a part reads. Every item of `states` has a name of its own too, among the items and among the inputs, and is read by a line of a part: a statement for a part that is not there, or for a field whose line does not read it, is a finding, `is stated, and no part reads it`. A line reads the name its given writes, so a statement is read when some line of some part has a given of its name. A load has `case`, `on` and `field`: it is on a part, it is one of the loads of that part's type, of its dimension and at least its `least`, and no case puts one load on one part twice. The name of its case is within the limit below and holds no `/`. A case that breaks either is a shape finding. So is a name in `cases` that no load has and that breaks either: it is a load case too, and a cell prints it. The kernel tests a load in this order and stops at the first that fails: its part, its field, its dimension, its `least`, that no case puts it on the part twice, and then the name of its case. So the name of a case is held to its limit for a load that breaks nothing else, and a load that breaks something else is a finding of this rule alone. Such a load is no load of the card, and no cell prints its case.
7. Every waiver names a part and a mechanism that the grid asks of that part's type.
8. The card has no claim, no tests record, no probability claim and no environment, and the design has no param. A deck of rules reads none of these yet. A card that states one would get a verdict that looks as if it held there: a lap whose card named a marine atmosphere once passed exactly as it does indoors. So each is a finding, and none is ignored. The finding for an environment names the file `card` and the item `environment`, and says `a deck of rules does not read an environment yet`. An ambient is refused by rule 6: it is an input that is no load and that no part reads.
9. Every part keeps every need of its type ([deck.md](deck.md), "What a type needs"). This rule is applied last, and only to files that break no rule before it: shape, types, the deck of rules, and Parts 1 to 8. So when a need is read, each field it names is there, and each quantity is more than zero unless its field says `may_be`. A need divides by no field that says `may_be`: such a deck does not load. The kernel takes each part in the design's order and each need of its type in the deck's order. It works out the range of each side over the ranges of the part's fields with exact fractions: a field that the design writes has the range of its number, and a field that reads a given the range of the card's input. The need holds when the upper end of the first side is at most the lower end of the second, or under it for `lt`. A need that names a field the part leaves unstated, its own or one of a part it joins, is not asked: it is no finding, and the kernel goes on to the next need. A need that does not hold is a finding of the rule `parts.9`, in the file `design`, whose item is the part's name. A need whose numbers would have more than 65,536 bits is not decided, and that is a finding of `parts.9` too: `need K of a TYPE is not decided: a value has more than 65536 bits`. The finding of a broken need prints the two ends as fractions in SI units. An end whose numerator or denominator has more than 256 bits is not written out: the finding says `a number of N bits`, where `N` is the bits of the longer of the two. The kernel keeps the first 100 findings and counts the rest, and it does not write the text of a finding it only counts.

**Cells.** For each cell of a design with no parts:

1. `proved` with a tape: every input is labelled `in:`, `reg:` or `dsg:`. An input labelled `in:NAME.INPUT` is input `INPUT` of the card named `NAME`, and every input labelled `reg:` is a constant of the deck. The tape's range for it contains the card's or the deck's. The kernel evaluates every root on every leaf of the partition by the interval rule, and the upper end of each is at most zero. A cell that meets all of this is proved. Otherwise it is open, and the verdict says which test failed.
2. `refuted` with a tape: the same test on labels. Each value of the point lies in its input's range and in the card's or the deck's range for that label, and two inputs with one label have one value. The lower end of root `which` at the point is above zero. A cell that meets this is refuted. Otherwise it is open.
3. `proved` or `refuted` with no tape is open: the kernel has no rule for its proof yet.
4. `waived` holds only when the card lists a waiver with the same `subject` and `mechanism`. Otherwise it is open.
5. `not_applicable` is taken as stated, and counted.

**Cells from a deck of rules.** With `--rules` the kernel makes the cells itself, in this order: for each part in the design's order, each line the grid has for its type in the deck's order. Then, for each part in the design's order again, each field and each load that nothing reads.

The load cases of the card are the names its `cases` lists and the `case` of each of its loads, each name once, whatever part a load is on. The two need not agree. A name in `cases` that no load has is a case that puts no load on any part, and the `case` of a load is a case whether `cases` lists it or not. Names are in order by their characters, each compared by its code point, and a name comes before every longer name that starts with it.

1. The cells of a line are made by items 2 to 7, whether or not the card waives the line's mechanism on the part: every rule of a waived line is run. Where the card does waive it, each cell of the line that those items leave `open` and that no inequality could answer is then `waived`, with the entry it has, and no other cell changes. No inequality could answer a cell that is open because the line's `unless` reads an unstated key (item 2), because the line has no rule for the part (item 3), because the unstated fields the rule reads are all keys (item 3), because a case leaves out a load the rule reads or the card has no load case (item 4), because the tape cannot be written (item 7), or because the rule says nothing at any point of the box: its `where` holds nowhere in it (item 5), or its root has no value anywhere in it (item 6). Every other open cell of the line stays `open`, and its reason starts `the waiver rests no cell that an inequality could answer: `. A cell that is `proved`, `refuted` or `not_applicable` stays so. So a waiver rests a cell that would be open, and no other, and it hides no refutation. The reason of a waived cell is `open but for the waiver: ` and then the reason the cell had while it was open, cut to 200 bytes as any reason is. The waiver is the first in the card's list with the part as its `subject` and the line's `mechanism`.
2. A line whose `unless` names a key that is unstated, for the part or for the part it names, is one `open` cell with an empty `entry`, and no rule of the line is run. A condition that names an unstated key is not decided, whatever its other keys are. The reason is ``PART.FIELD is unstated: its maker states none, and the `unless` of the line reads it``, where `PART` is the name of the part that has the field. Otherwise, a line whose `unless` holds for the part, or that has an `unless` with no condition, is one `not_applicable` cell.
3. Otherwise, each rule for the line that answers for the part gives cells, and a line with no such rule is one `open` cell. The cells of items 2 and 3 that no rule gives have an empty `entry`. A rule answers for a part when its `when` holds for the part, and when its `when` names a key that is unstated.

   A rule that answers and reads a field that is unstated gives only `open` cells. The fields a rule reads are those of item 8: of its sides, its `where`, its `when` and its `requires`, of the part and of the parts it joins. It gives one cell, with the rule's `entry`, when it has `requires`, reads no load, or the card has no load case. Otherwise it gives one for each load case, with the entry `RULE/CASE`, in the order of the cases' names. It gives no `/where` cell, and writes no tape. The reason is `PART.FIELD is unstated: its maker states none, and the rule reads it`, for the first unstated field in this order: the fields that the steps of the rule read, in the order of the steps, and then the keys of its `when`; or for a rule with `requires`, the keys of its `when` and then of its `requires`. A step order is the kernel's own, so another reader may name another of the unstated fields a rule reads. The cells and their states do not depend on it.

   A waiver rests these cells when every unstated field the rule reads is a key (item 1): what is unsaid is which rule answers, or which line of a table. When one is a quantity, they stay open under a waiver, since the rule's inequality could be answered for every value the quantity may take. That leaves a known miss. A rule that fails whatever value an unstated quantity takes is open and not refuted, so the design is UNKNOWN where it fails: `current ≤ min(limit, rating)` with the rating under the current and the limit unstated. The kernel tries no point for a quantity that has no value, and `petra check` gives it none (`tests/test_kernel_attacks7.py`, `UnstatedEveryValueFails`).
4. A rule with `requires` gives one cell, whose `entry` is the rule's id from after its last `/`. The cell is `proved` when the condition over keys holds for the part and `refuted` when it does not. The kernel writes no tape for it, looks for no hint and spends no work, and a hint for it changes nothing. A refuted cell has a `reason`: `the part is not what the rule requires: ` and then, for each key the condition names, in the order it names them and each once, `KEY is NAME`, with `, ` between two. `KEY` is the key as the condition writes it, `service` or `top.bore`, and `NAME` the name the part has for it, or its first 200 characters. A reason prints in 200 bytes, and the keys are named while they fit: the first key always, and a later one while the keys so far, `, ` and that key are at most 144 bytes, which leaves room for the first words and for ` and N more`. That ends the reason when a key is left out, and `N` counts the keys it does not name. Items 5 to 7 are for the other rules, which state an inequality.

   A rule that reads no load gives one cell. Its `entry` is the rule's id from after its last `/`, so `lap-spacing-centres` for `aisc360-22/lap-spacing-centres`. A rule that reads loads gives one cell for each load case of the card, in the order of the cases' names, and the `entry` then ends in `/CASE`. Under a case that puts every load the rule reads on the part, the cell is settled as items 5 to 7 say. Under a case that does not, the cell is `open`, there is no `/where` cell, and the reason names the case and the loads it does not put on the part: the first four, and how many more. No load is taken as zero. A card that means no tension in wind states a tension of zero in wind. When the card has no load case at all, the rule gives one `open` cell whose `entry` has no case.
5. A rule with `where` needs its range first. The kernel writes a tape with one root for each inequality of `where` and looks for a hint with the cell's entry and `/where`. When a partition of such a hint proves every root, that is a `proved` cell with that entry, and the rule's cell follows. When none does, there is no `/where` cell, and outside its range a rule proves and refutes nothing, whatever the hints say. Inside it a point may still refute the rule. The kernel writes the rule's tape again with a root that is a `pick`: the rule's root where every item of `where` holds, and -1 where one does not. It tries the points of the hints with the cell's entry on that tape, and none of their partitions. A point where that root is above zero is inside the range and fails the rule there ([proved.md](proved.md), `Tape.refuted_within`), and the cell is `refuted`. Otherwise it is `open`. On a line the card waives, the kernel then asks whether the `where` holds nowhere in the box: whether a root of its tape has a lower end above zero over the whole box, or has no value anywhere in it, as item 6 decides that.
6. The rule's cell has a tape with one root, the left side of `le` less the right. The kernel tries each hint for the cell in the file's order. A partition that proves the root makes the cell `proved`. A point that has a value for every input, each inside the range the card or the design gives it, with the root above zero there, makes it `refuted`. The first hint that does either settles the cell. With none it is `open`. The state a hint claims decides nothing.

   For a rule that states `lt`, the root is another node and everything else is the same. Let `L` and `R` be the nodes of the two sides. The kernel adds the constants `["c", "-1"]` and `["c", "1"]`, at nodes `M` and `P`, and the root is `["pick", [[["lt", L, R], M], [null, P]]]`: -1 where the left side is under the right, and 1 elsewhere. A partition proves that root when the pick is -1 alone on every leaf, which is when the upper end of the left side's enclosure is under the lower end of the right side's. So the left side is under the right at every point of the box. A point refutes it when the pick is 1 alone there, which is when the lower end of the left side's enclosure at the point is at or above the upper end of the right side's. So the left side is not under the right at that point: equal counts. Where both sides are one node, the pick is 1 and the cell is refuted at any point.

   On a line the card waives, an `open` cell asks one more question: whether its root has no value at any point of the box. The kernel walks the tape over the whole box, as a proof walks one leaf, and keeps every enclosure. A node other than a pick has no value anywhere when it reads a node that has none anywhere. A pick has none anywhere when a node it compares has none anywhere, or when every node it compares has an enclosure and, in every way of taking one order for each pair that the enclosures leave possible, no case holds or the first case that holds has no value anywhere. At each point of the box the true order of each pair is one of those ways, so the pick has no value at that point. A pick of more than 4,096 ways, or that the walk cannot pay for, may have a value. So a table read at a size it does not list has no value anywhere when the box holds that size alone, and has one somewhere when the box reaches a size it lists.
7. A tape that cannot be written leaves the cell `open`: a table has no line for the part's key, every cell it could read is empty, or an equation, a table or a `case` would be a pick of more than 1,024 orders. A tape holds every expression that its roots read, the expressions of every name of a `case` among them, so one that cannot be written leaves the cell open whatever name the row gives. No name of a `case` is without a cell: a row that gives a name that none of its cells holds does not load.
8. A quantity or a key of a part is read by a rule that applies to the part, by a rule that applies to the part that joins it, or by an `unless` of the grid's lines for its type. A load that the card puts on a part is read by a rule that applies to the part. A rule applies to a part when it is for the part's type and it answers for the part: its `when` holds, or names a key that is unstated (item 3). It applies whether or not the card waives its line or the line's `unless` holds. A field that the part leaves unstated has no `unread` cell, read or not. A rule reads what the sides of its `le` and of its `where` name: themselves, through a name of `let`, and in what they bind to an input of a row. A name of `let` that none of those sides reads is not read. A rule also reads the key of each `is` in its `when` and in its `requires`, and an `unless` the key of each `is` in it. An `is` on `PART.FIELD` reads that key of the part the name `PART` stands for, and the key is then read for that part and not for the part that joins it. An `unless` reads its keys whether or not it holds, and a rule only when it applies. A condition is over keys alone, so whether a rule applies to a part does not turn on the load cases of the card. A load is read by an expression and by nothing else. A rule names the loads of its own type alone, so a rule of the part that joins a part reads none of that part's loads. Each quantity and each key that nothing reads is one `open` cell, with mechanism `unread` and the field as its `entry`. Each load that nothing reads is one `open` cell for each case that puts it on the part, with mechanism `unread` and the entry `LOAD/CASE`. For one part the cells of its fields come first, in the order of its type's fields, and then the cells of its loads, in the order of the loads' names and, for one load, of the cases' names.

A hint for a cell that the kernel does not have is ignored and counted. So proofs.json can leave a cell open that a better search would settle, and it can do nothing else: it cannot add a cell, drop one, or change what a cell says.

A waiver does not change that. It rests an open cell only where no inequality could answer it (item 1), and a cell that a hint could settle is not one. So a proofs.json that leaves out the point that refutes a cell of a waived line leaves that cell `open`, and the design UNKNOWN, where the point would make it `refuted`. The kernel does not search, but it does not need to tell a cell that nobody could settle from one that nobody tried to: what it rests is decided from the deck, the design and the card, and no hint enters it. A reader takes a `waived` cell for what it says: the deck has nothing to say about the line for that part, and the one who signed the waiver answers for it.

No two of these cells have the same subject, mechanism and entry, so a hint names one cell and a reader finds one cell under a key. Here is why. Two parts have two names. A line of the grid gives a part cells of its own mechanism, and a type has a mechanism once. Within one line, a cell that no rule gives has the empty entry, and a part has one such cell at most, only where no rule of the line gives it a cell. Two rules of the line have different entries, because their ids differ after the last `/`, and an entry has no `/` in it before the case. An id that ends in `/` gives the empty entry, and no other rule of the line has it. A rule with `requires` gives the one entry `RULE`, with no case and no `/where`, and is held to the same rule about ids as any other. A case has no `/` either, so `RULE/CASE` and `RULE/CASE/where` are never the entry of another case or of another rule. A rule gives the entry with no case only when the card has no case, and then it gives no other. The cells named `unread` share their mechanism with no line of the grid. Among them, the cell of a field has the field's name as its entry, which holds no `/`, and a type has a field once. The cell of a load has `LOAD/CASE`, which holds one `/`: the name of a load holds none, and neither does a case. So it is the entry of no field, two loads or two cases give two entries, and no case puts one load on one part twice. The kernel also checks the finished list, once, after the last cell is made, and a design that would have one key twice is ILL-FORMED with a finding of the rule `limits`.

A finding of the rule `limits` names the file `design`. Its item is `parts` when the design is past the cells, past the steps to make them, or would have one key twice, and the reason says which. Its item is the name of a part when deciding the needs ran out of work at that part (Parts 9).

This holds for the cells the kernel makes. Without `--rules` the cells are the list of proofs.json, which the kernel takes as it comes, and that list may hold one key twice.

The interval rule is the one in `petra/kernel/interval.py` and `petra/kernel/evaluate.py`: exact rational intervals, with `sqrt`, `ln`, `exp`, `cos` and pi rounded outward on a grid of 2^-96. An `ln`, an `exp` or a `cos` is rounded from an enclosure of 128 bits, and from one of 224, 608 and then 2,144 bits when the one before has a point of the grid inside it. The two kernels give the same ends for every root. The Python kernel has no `pick`: `petra/grid.py`, which searches for the partitions and the points, reads a pick by the same rule a second time.

## The verdict

| Verdict | When | Exit code |
|---|---|---|
| ILL-FORMED | A rule of the first four groups is broken, or the design is past a limit on its cells or on the work of its needs | 3 |
| FAIL | A cell is refuted | 1 |
| UNKNOWN | No cell is refuted, and a cell is open or no cell is proved | 2 |
| PASS | Every cell is proved, waived or not applicable, and at least one is proved | 0 |

The kernel's verdict has no word for a PASS that rests a cell on a waiver: it is PASS, and `waived` lists the waivers it rests on. `petra check` calls such a PASS of a design checked against a deck of rules PASS_WAIVED and exits 6 for it, so that no caller takes it for a PASS in which the deck answered every cell. It compares PASS_WAIVED from its own cells with PASS from the kernel's, and its `waived` with the kernel's.

The kernel prints one JSON object: `verdict`, the `hashes` of the files, where `rules` is null when `--rules` names no deck, `cells_from` (`rules` when the kernel made the cells from a deck of rules, and `proofs` when it took the list of proofs.json), `findings` (the first 100 broken rules, each with the file and the item), `more_findings` (how many more there were), `counts` (the cells in each state), `dsg_inputs` (the distinct `dsg:` labels the settled proofs read), `work` (the units of work the needs and the proofs took, as [Work](#work) counts them), `waived` (each waiver that a cell rests on, once, in the order of the cells, and no waiver that rests none) and `cells`. With `--rules` it also prints `ignored_hints`. A cell has its subject, mechanism and entry, `claimed`, `state`, the state the kernel settled on, and `reason` when the kernel left it open, waived it or refuted a rule that requires. `claimed` is the state the file claims for the cell. With `--rules` it is the state of the first hint for the cell, and null when there is none. A command line it cannot read prints the usage and exits 64.

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

For a design with parts, card.json is a function of the card's text alone. It holds each given under the name the card gives it, each key and each count the card states, each load with the part and the field the card puts it on, and each waiver. Nothing in it comes from the design. So the asker can work out its hash with no design, with their own copy of Petra:

```
python -m petra.export --card-only CARD.card --out DIR
```

The command writes `DIR/card.json` and prints its hash. It reads no design, so what the card says of a part is not checked against any. It exits 3 and writes nothing for a card the language refuses.

The asker runs it on the card they issued, and compares the hash it prints with `hashes.card` in the kernel's verdict.

- The two are the same: the verdict is about the asker's card.
- They differ: the card.json the kernel read states something else. It may give a load another range, waive a mechanism the asker did not, or hold a bound the asker never gave.

The comparison holds for a design with parts only. For a design of the models' kinds card.json takes names from the design, so its hash is not the one this command prints. `tests/test_export_card.py` compares the two files, byte for byte, for every pair of `examples/deck` and `corpus/cases/deck`.

## Limits

The kernel stops work that would not end. A tape has at least one root. A partition is at most 64 deep, and a `pow` exponent at most 64 in magnitude. A condition of a pick in a tape that a file carries nests at most 16 deep, where `le` or `lt` alone is 1 deep. The conditions of one pick hold at most 1,024 orders between them, in a tape that a file carries and in one the kernel writes. A value with more than 65,536 bits, or an `exp` or a `cos` of a number beyond 65,536, leaves its cell open. A pick has no value on a box where it has more than 4,096 ways to order the nodes it compares. A file's JSON nests at most 128 deep, and a number outside a string has at most 32 digits and no fraction or exponent.

A deck of rules has four more. A quantity or a number is at most 4,000 characters. A whole or a half power has an exponent of at most 64 in magnitude. An expression nests at most 1,024 deep, counted through the names of `let` it reads and the rows it applies, so a name of `let` that reads itself, or a chain of names longer than that, is refused. Reading the deck takes at most 1,000,000 steps, counted from its file before a row is read ([deck.md](deck.md), "The size of a deck"). `petra/grid.py` has the second and the fourth of these and not the other two. Both try what the rules of a deck require within the same two bounds: 4,096 combinations of names for a rule, and 1,000,000 for a deck, counted as the combinations of each rule tried times the sizes of its `requires` and of its `when`. So trying takes a bounded time whatever a deck requires, and a rule past a bound is read without being tried.

The time a verdict takes, what the kernel holds while it works and what it prints are each bounded, whatever the files hold. Thirteen limits see to that, and one rule about tables.

| Limit | Value | Past it |
|---|---|---|
| Findings in `findings` | 100 | The kernel keeps the first 100, and `more_findings` counts the rest. |
| The item or the reason of a finding, and the reason of a cell | 200 bytes as printed | The text is cut, and ends with how many characters were left out. |
| The name of a part and of a load case | 64 bytes as printed | A shape finding |
| The name of the card and the name of the design, for a design checked against a deck of rules | 200 bytes as printed | A shape finding |
| In a deck of rules: the name of a field, a load, a joined part and a `let`, the name of a mechanism, and the id of a rule | 64 bytes as printed | The deck does not hold together |
| Steps to read a deck of rules | 1,000,000 | The deck does not hold together, and no row of it is read |
| Cells made from a deck of rules | 10,000 | A finding of the rule `limits`, and the design is ILL-FORMED |
| Reasons of the cells made from a deck of rules, together | 500,000 bytes as printed | The kernel keeps the first reasons, in the order of the cells. Each cell after them says `past what the verdict prints of reasons` in place of its own. |
| Steps to make the cells of a design from a deck of rules and to write their tapes | 10,000,000 | A finding of the rule `limits`, and the design is ILL-FORMED |
| Work for the needs and the proofs of one verdict | 20,000,000,000 units | A proof that cannot pay for its tape is not tried, and a step that cannot pay is not taken. The cell is open, and the reason says so. A need that cannot pay for a step is a finding of the rule `limits`, and the design is ILL-FORMED. |
| Enclosures held at once while one leaf is walked | 16,777,216 words of 64 bits, which is 128 MB | The node whose enclosure would go past it has no value. |
| Entries in the cache of `ln`, in the cache of `exp` and in the cache of `cos` | 1,024 each | The cache starts again from the new entry. |
| Times a waiver is printed in `waived` | 1 | Cells that rest on one waiver print it once. |

A name of 64 characters in ASCII prints in 64 bytes. A character outside ASCII prints in up to four, a quote, a backslash and a line end in two, and any other control character in six. A line end is a line feed, U+000A, or a carriage return, U+000D. A control character is any other character below U+0020: the tab is one, and prints in six. U+007F is none, and prints in one. A character outside ASCII prints in the bytes of its UTF-8, which are two, three or four. A cell prints these names whole, so they are refused and not cut. The label of every input of a tape holds the name of the card or of the design, which is why those two are held to 200 bytes.

Every limit is tested before the work it bounds, and never after. The kernel counts a deck's steps from its file before it reads a row. It counts a step of the cells before it takes the step. It takes the cost of a step of a proof from the work left before it takes the step.

### Tables

Wherever the kernel looks for a name or a number, it looks in a table kept in the order of its keys. That holds for the parts, the fields, the loads, the load cases, the rows, the rules, the inputs of the card, the hints, the nodes and the constants of a tape it writes, the exponents of a dimension, and the ends in the caches of `ln`, `exp` and `cos`. Such a table is a balanced tree: neither side of a key holds more than three times as many keys as the other. So a look compares the key with at most five keys for each two bits of the table's count, and with about one for each bit as a rule. A comparison of two texts or of two whole numbers reads them from their start to where they differ, so it reads no more than the shorter is long. A pair is in order by its first member and then by its second, and a fraction by its numerator and then by its denominator.

No table of the kernel is kept by a hash of its keys. A file chooses the keys: its names, its labels and its numbers. A hash that the file can work out can be made to send many keys to one place of a table, and a look there walks them all. The hash of a whole number that the kernel's language provides is the number's last 64 bits, so the numbers `1 + k × 2^63` all share one. The fourth review found two tables kept by it: the constants of a tape the kernel writes, and the two caches. 30,000 such values in one table of a deck took 45 to 50 processor seconds to write for two parts, and 1,024 such ends in a cache took 85 to 90 seconds for a proof charged as 18 billion units. In a table kept in order the same files take 0.7 and 6 seconds, and no choice of keys does more than make every comparison read to the end of the shorter key.

A rule reads a field or a load in one step, however often it names it: a second mention is a step that hands on the first and weighs the same. So writing a tape adds one input for each field and each load without looking for it among the inputs before.

### Steps

Making the cells of a design is counted in steps, 10,000,000 at most. The work is the deck times the design, so it is not held by the size of the files alone.

- **A line of the grid, for a part.** One step, and the size of the condition of its `unless`. The size of a condition is 1 for an `is`, 1 more than the sizes of its members for an `and` and an `or`, and 1 more than its member for a `not`.
- **A rule of the line, for the part.** One step, the size of its `when`, and one for each load it reads. For a rule with `requires`: one step, the size of its `when` and the size of its `requires`, and that is all the rule costs, since it has no tape. Every rule of the line is counted, whether its `when` holds for the part or not.
- **An unstated field.** Only for a part that leaves a field unstated, or that joins a part that does: for each rule that answers, one step for each field the rule reads, and for a rule that then gives a cell for each load case, one step for each load case. A design that states every field takes the steps it took before a field could be left out.
- **The load cases.** For a rule that answers and reads loads: one step for each load case of the card, for each load the rule reads.
- **A tape.** The weight of the rule each time it is written for a part and a load case, twice for a rule with `where`, and one step for each node of each tape written. Where the `where` is not proved, the tape of the rule inside its range ([The rules](#the-rules), item 5) is written in place of the rule's own tape, and its nodes are counted the same way. The weight of a rule is the sum over its steps, read or not. A step is one name or one operator of the rule, and weighs 1 and 1 for each thing the operator reads. A difference is two steps, a negation and a sum, and a power is up to four: a root, a power, a one and a quotient, or a constant, a logarithm, a product and an exponential. A pick weighs 1, 1 for each case and 2 for each order of its conditions. A table weighs 1, 1 for each place down, 1 for each cell, and 1 for each entry of a `by` that reads it. A table with a key that a row names weighs more, since it goes through its cells once for each cell of that row: 1 for each cell of that row that holds a name, and the product of the places it goes through down and across. A side whose key a row names goes through one place for each such cell, any other side through each of its places, and a table with one side through one place across. The row that gives the name adds a step for each end of its bands and each of its listed values, each time a rule applies it, and a `case` is a pick.
- **What a rule reads.** After the cells, for each part: one step, and for each rule of the part's type the steps of the rule above and one for each field the rule reads.

The count is made in this order. The limit is tested after each charge of items 1, 2, 3 and 5, so a design is refused at the first of those that takes the count past 10,000,000. The nodes of item 4 are added with no test of their own, and are in the count at the next charge.

1. For each part in the design's order and each line of the grid for its type: the line and every rule of the line, in one charge. That is 1, the size of the line's `unless`, and for each rule of the line 1, the size of its `when` and one for each load it reads, or for a rule with `requires` the size of that condition. A line with no `unless`, and an `unless` with no `when`, has a condition of size 0. The charge is made whether the card waives the line, the line's `unless` holds, or neither. A waived line also takes the charges of items 2 to 4, since its rules are run: a waiver saves no step.
2. For each rule that answers, when the part leaves a field unstated or joins a part that does: one for each field the rule reads, in one charge, before the kernel looks for an unstated one among them. Where it finds one and the rule gives a cell for each load case: one for each load case of the card, in a second charge. Such a rule takes no charge of the items below.

   For each rule that answers and reads loads, when the card has a load case: every load case of the card times every load the rule reads, in one charge. A case counts whether or not it puts the load on the part.
3. For each cell of such a rule under a case that puts every one of its loads on the part, and for the one cell of a rule that reads no load: the weight of the rule, or twice the weight for a rule with `where`, before a tape is written. It is twice whether or not the range is then proved. A case that leaves a load out pays no weight, and neither does a rule under a card with no load case.
4. For each tape that is written: one step for each node the tape holds, once the tape is written. A node that two expressions share is one node. A tape that cannot be written adds none.
5. After every cell, for each part: 1, and for each rule of the part's type what item 1 charges for the rule and one for each field it reads. The fields a rule reads are counted each once: the quantities and the keys that the sides of its `le` and of its `where` read, and the keys that its `when` and its `requires` name, of the part and of the parts it joins.

The weight of a rule is the sum of the weights of its steps. Every name of `let` is read and weighed once, whether a side reads it or not, and each side of `le` and of each item of `where` once. The comparison of two sides is no step: its two nodes, the negative of the second side and their sum, are counted with the nodes of the tape. For `lt` they are three: the two constants and the pick.

| Written | Steps and their weights |
|---|---|
| A number, `pi`, a `q` | One step of weight 1 |
| A field, a load | One step of weight 1. Each later mention is one more step of weight 1, which hands on the first. |
| `add`, `mul`, `min`, `max` of `n` | One step of weight 1 + `n` |
| `neg`, `abs`, `sqrt`, `exp`, `ln`, `cos` | One step of weight 2 |
| `div` | One step of weight 3 |
| `sub` | Two steps, of weights 2 and 3: a negative and a sum |
| A whole power above 0 | One step of weight 2 |
| A whole power of 0 or below | A power, a one and a quotient: weights 2, 1 and 3. A power of 0 is written as 1 over the power, as a negative one is. |
| A half power | A root of weight 2 first, and then as the whole power of twice the exponent |
| Any other fixed power | A constant, a logarithm, a product and an exponential: weights 1, 2, 3 and 2 |
| A power with an exponent that varies | A logarithm, a product and an exponential, weights 2, 3 and 2, after the steps of the exponent |
| A row applied | The steps of each quantity it binds, the steps of its body, and one step more of weight 1 and 1 for each quantity it binds. A key that is bound is no step. Inside the body, the name of an input is no step either, however often the body names it: it is the step of the quantity bound to it. |
| The body of an equation | Its expressions, and a pick of weight 1, 1 for each case and 2 for each order. One case that holds otherwise is no pick. |
| The body of a table | One step, weighed as above |
| A row that gives a name, applied | The steps of each quantity it binds, and one step of weight 1 for each end of a band and each listed value of its sides |
| A `case` | The steps of the row that gives the name, the steps of the expression of each name, and a pick with one case for each cell of that row that holds a name |

### Work

A proof pays for what it does, in units of work, from what its verdict has left. The kernel finds the cost of a step from the lengths of the numbers the step reads, and takes it from the work left before it takes the step. So the count is a bound on the time, set before the time is spent, and not a measure of it. The costs are fitted so that a unit takes about the same time whatever the step and however long its numbers: 0.3 to 0.4 nanoseconds on the desktop they were fitted on, a four-core machine of 2017.

A cost is a whole number. In the formulas below:

- The **bits** of a number are the bits of its numerator or of its denominator in lowest terms, whichever has more. Zero has a numerator of no bits and a denominator of one bit. The bits of an enclosure are the bits of its longer end.
- `root(n)` is the square root of `n` rounded down, and `h(n)` is `n × root(n)`.
- `ramp(n, a, b)` is 0 for `n` up to `a`, then `n − a`, and `b − a` from `b` on.
- A division rounds down, and a formula is worked from left to right. A difference that would be below zero is zero.

**The fee.** Before its first step a proof pays for its tape: `size × (3 + leaves) + leaves × (20,000 + 8 × inputs)`, with the leaves of its partition and the inputs of its tape. The size of a tape is the sum of the sizes of its nodes.

| Node | Size |
|---|---|
| A constant, an input, `pi` | 200 |
| `add`, `mul`, `min`, `max` | 200, and 40 for each node it reads |
| `neg`, `abs`, `sqrt`, `ln`, `exp`, `cos`, `pow` | 240 |
| `div` | 280 |
| A pick | 200, 40 for each case, and 20 × its orders × (its pairs + 1) |

The orders of a pick are every `le` and `lt` of its conditions. Its pairs are the distinct pairs of nodes that they compare, where `a` against `b` and `b` against `a` are one pair. A refutation pays as a proof with one leaf, and 20,000 more for each input. A proof whose fee is more than the work left is not tried and pays nothing.

**The steps.** On each leaf the kernel takes the steps of the nodes that a root reads, in the order of the tape. A node that no root reads has no step. A node other than a pick that reads a node with no value has none either, and pays nothing. A step that costs more than the work left is not taken and pays nothing, and its node has no value, as a node that divides by zero has none. A step that is taken and then has no value, because its value has too many bits or is not defined, has paid.

Three costs come back in many steps. They are for two numbers of `p` and of `w` bits, of which the longer has `m`:

- `sum(p, w)` is `4,000 + 875 × ramp(m, 16, 32)`, and `(p + w) × 11 / 10 + h(root(p × w))` more when `p + w` is 64 or more.
- `product(p, w)` is `12,000 + 1,500 × ramp(m, 8, 32)`, and `h(p + w) × 26 / 100 + h(root(p × w)) × 27 / 10` more when `p + w` is 64 or more.
- `order(p, w)` is `550 + 1,625 × ramp(m, 12, 20)`, and `h(p + w) / 30` more when `p + w` is 64 or more.

In the table, `n` is the bits of the enclosure the step reads.

| Step | Units |
|---|---|
| A constant | 800 when its bits `n` are under 32, and `8,000 + n / 8` otherwise |
| An input | 700 when the bits `n` of its range on the leaf, or of its value at the point of a refutation, are under 32, and `4,000 + n / 12` otherwise |
| `pi` | 2,800 |
| `neg`, `abs` | 1,100 when `n` is under 32, and `7,000 + n / 3` otherwise |
| `add` | For each term in turn, `sum(p, w)`. `p` is the bits of the sum of the terms before it, which is 1 before the first, and `w` the bits of the term. |
| `mul` | For each factor in turn, `product(p, w)`, in the same way |
| `div` | `product(p, w)` for a numerator of `p` bits and a divisor of `w`, and 6,000 more when `w` is under 32, `14,000 + w / 2` more otherwise |
| `min`, `max` | 500. For the first node it reads, 800 when its bits `n` are under 32, and `3,000 + n / 16` otherwise. For each node after it, `order(p, w)`, where `p` is the most bits of the nodes before it and `w` its own. |
| `sqrt` | `62,000 + 4 × n + (a × a + b × b) / 900`. `a` is the bits of the numerator of the lower end and 256, less the bits of its denominator, and `b` is the same for the upper end. |
| `pow` by `k` or by `−k` | `2,800 + n / 8 + k × (e + n / 2) + (k − 1) × (h(n) × 31 / 20) + ((k − 1) × (k − 2) / 2) × (n × n / 300 + 4 × n)`. `e` is 4,700 when `n × k` is under 32, 14,500 when `n` alone is, and 31,000 otherwise. |
| `ln` | 25,000, and for each end what is below. An upper end equal to the lower pays a look. |
| `exp` | 3,000 when the enclosure reaches below −65,536 or above 65,536, and the node has no value. Otherwise 25,000, and for each end what is below. An upper end equal to the lower pays a look. |
| `cos` | 3,000 when the enclosure reaches below −65,536 or above 65,536, and the node has no value. Otherwise 25,000, `15,000 + 3 × n` for placing the enclosure among the multiples of pi, and for each end what is below. An upper end equal to the lower, or to its negative, pays a look. |
| A pick | What is below |

**An end of `ln`, of `exp` and of `cos`.** The kernel keeps the ends it has rounded in three caches, one for each of the three steps. A cache is kept in the order of its ends, by numerator and then by denominator ([Tables](#tables)), so a look compares the end with at most 25 of the 1,024 ends a cache holds, and with 10 or 11 as a rule, and each comparison reads no more than the end has bits. A look is `1,500 + n / 8` for an end of `n` bits. An end of `ln` pays a look when it is 1 or the cache of `ln` holds it, and an end of `exp` when it is 0 or the cache of `exp` holds it. An end of `cos` pays a look when it is 0 or the cache of `cos` holds its size: the cosine of an end is the cosine of its negative, so the two are one entry. Any other end pays for an enclosure of `p` bits. The first enclosure the kernel asks for has 128 bits, and the next ones 224, 608 and 2,144.

- For `ln`, of an end of `n` bits: `f × p + p × n × 4 / 5 + h(n) × 3 / 5`. `f` is 17,000, but for the first enclosure it is 5,000 when `n` is under 32 and 7,000 otherwise.
- For `exp`, of an end `x`: let `c` be the size of `x` rounded up to a whole number, `s` the bits of `c` and 1, `q` be `p + 2 × s + 2 × c`, `wide` be `q / 64 + 1`, `terms` the larger of 32 and `2 × q / b` for the bits `b` of `q`, and `v` be 1 and the bits of the numerator and of the denominator of `x` together over 64. The cost is `(terms × (10,000 + 54 × wide + 20 × v + wide × v / 3) + (s + 16) × wide × wide / 4) × 17 / 10`.
- For `cos`, of an end `x` of `n` bits: let `c` and `s` be as for `exp`, `q` be `p + 2 × s + 8`, `wide` be `q / 64 + 1`, `terms` be `q / (b + 1)` for the bits `b` of `q`, and `w` be `n / 64 + 1`. The cost is `110,000 + 1,000 × w + h(n) + terms × (25,000 + 400 × w + 20 × wide × w) + s × (11,000 + 30 × wide × wide)`. The kernel halves the angle `s` times, sums the series of the cosine of what is left, and doubles the angle `s` times again, so `q` grows by two bits for each doubling and not with the size of `x`, as it does for `exp`.

A step that rounds to the grid pays for each enclosure it asks for, before it asks. So an `ln`, an `exp` or a `cos` whose value lies close to a point of the grid pays for the finer enclosures too, and one that does not pays for the first alone. The cost is found from the caches as they are before the step. A cache gains an end when the step that rounded it has a value, and a proof that fails leaves the caches as they were before it. A cache holds 1,024 ends, and one more starts it again from that end.

**A pick.** A pick first looks at its pairs: twice `order(p, w)` for each pair, for the bits of its two nodes. A node with no value counts as zero here, which has 1 bit. A pick that cannot pay for the look is not taken. Its ways are the product, over its pairs, of how many of below, equal and above the two enclosures leave possible. With more than 4,096 ways the pick pays for the look alone and has no value. Otherwise it pays `ways × (200 + 20 × pairs + 30 × cases + orders × (150 + 6 × pairs))` more, and `order(L, L)` for each way or for each case, whichever are fewer, where `L` is the most bits of the nodes its cases give, and at least 1.

**The needs.** What a type needs of its fields is decided before any cell is made (Parts 9), and it pays from the same 20,000,000,000 units, before each step. A number of a need pays as a constant, and a field as an input, by the bits of its range. Each term of a sum pays `sum(p, w)` and each factor of a product `product(p, w)`, as in a tape, a negative pays as `neg`, a quotient as `div`, and the comparison of the two sides pays `order(p, w)` once. A sum starts from zero and a product from one, each of 1 bit. A need has no tape, so it pays no fee. For a part that leaves a field unstated, or joins a part that does, each need first pays 700 for each field it names, each as often as it names it, to look for an unstated one. It pays that whether it finds one or not, and a need that names one pays nothing more. A step it cannot pay for is not taken: the kernel stops there, with a finding of the rule `limits` whose item is the part, and asks no further need. A value with more than 65,536 bits ends that need alone, with a finding of `parts.9`, and what its steps took stays spent.

**Whether a rule says nothing.** On a waived line, the walk that asks whether a `where` holds nowhere or a root has no value anywhere (The rules, items 5 and 6) pays as a proof of one leaf: its fee, and then its steps. Each pick that has no value while every node it compares has one then pays its pick step again. A walk whose fee is more than the work left is not taken. A step it cannot pay for has no value, as in a proof, and a pick it cannot pay for again may have a value. Either way the cell stays open. What the walk adds to the caches is not kept.

**The count.** The kernel takes the work of the needs first, and then the work of each proof from what is left, in the order of the cells. A proof that fails has spent what its steps took. The verdict prints the work its needs and its proofs took as `work`.

`bench/work_sweep.py` measures what a unit costs, for each step and for numbers of 64 to 64,000 bits with no pattern in them, and compares it with a chain of small products. It fails when a unit of any step costs over three times a unit of the chain. It also measures a look, as `lnheld`, `expheld` and `cosheld`: an `ln`, an `exp` and a `cos` of an end that its cache holds, when the cache is full of 1,022 ends that have one denominator and numerators that differ in one word in the middle. A unit of such a look took 0.19 to 0.28 nanoseconds in a run where the chain took 0.34, on the same desktop while it did other work, and a look of `cos` 0.42 to 0.47 in a run where the chain took 0.45 and then 0.55. In the kernel before the fourth review, whose caches were kept by a hash, it took 1.8 to 3.5 against a chain at 0.33, which is ten times, and the sweep fails on that. On the desktop the costs were fitted on it prints, in nanoseconds a unit:

| Step | 64 bits | 250 | 1,000 | 4,000 | 16,000 | 64,000 |
|---|---|---|---|---|---|---|
| A constant | 0.24 | 0.26 | 0.22 | 0.21 | 0.27 | 0.23 |
| `pi` | 0.24 | | | | | |
| `neg` | 0.36 | 0.33 | 0.40 | 0.32 | 0.39 | 0.43 |
| `abs` | 0.25 | 0.23 | 0.27 | 0.26 | 0.30 | 0.26 |
| `add` | 0.27 | 0.30 | 0.30 | 0.21 | 0.23 | 0.22 |
| `mul` | 0.30 | 0.29 | 0.35 | 0.36 | 0.29 | 0.32 |
| `div` | 0.28 | 0.31 | 0.38 | 0.36 | 0.31 | 0.30 |
| `min` | 0.22 | 0.21 | 0.21 | 0.24 | 0.29 | 0.28 |
| `max` | 0.22 | 0.24 | 0.21 | 0.25 | 0.29 | 0.28 |
| A pick of one order | 0.19 | 0.20 | 0.20 | 0.31 | 0.34 | 0.30 |
| `sqrt` | 0.30 | 0.29 | 0.31 | 0.29 | 0.26 | 0.21 |
| `pow` by 2 | 0.17 | 0.20 | 0.25 | 0.27 | 0.27 | 0.28 |
| `pow` by 3 | 0.16 | 0.19 | 0.25 | 0.32 | 0.23 | 0.25 |
| `pow` by 8 | 0.15 | 0.22 | 0.37 | 0.32 | 0.23 | 0.17 |
| `ln` | 0.28 | 0.29 | 0.46 | 0.40 | 0.33 | 0.43 |
| `exp` | 0.32 | 0.36 | 0.33 | 0.33 | 0.32 | 0.41 |
| `cos` | 0.40 | 0.44 | 0.34 | 0.29 | 0.26 | 0.29 |

The chain took 0.34 in that run, so the most, 0.46, is 1.4 times it. The line of `cos` is from a later run on a busier desktop, where the chain took 0.45 and the most of any step, 0.56, was 1.2 times it. A figure moves by about a quarter from one run to the next: in a run on a busier machine the most was 0.55 against a chain at 0.38. A constant of a file has at most 4,000 characters, so its last two columns are for one of 6,000 bits. A product of two numbers of 64,000 bits and a power of a long number have too many bits for a value, and their figures are for steps that paid and had none. Before the costs were fitted again the same sweep gave between 0.15 and 2.34 against a chain at 0.15, which is 16 times.

A step on whole numbers, or on fractions with a short numerator or denominator, is charged as the same step on fractions with no pattern and takes less, down to a tenth of the time for long numbers. So the count does not run far under the time, and for such numbers it runs well over it.

The heaviest design of the corpus, `weld_bracket`, takes 5.4 billion units in two processor seconds: a little over a quarter of the budget. The next takes 0.13 billion, and a lap of the first deck of rules 6.0 million.

Files of 1 MB made to take as long as they can took 10.0 to 10.2 processor seconds in three runs on the same desktop, and 14.0 in a run while it did more other work. They hold three rules for one part. One applies a row of 5,000 numbers as often as the million steps to read a deck allow, which took 1.5 seconds alone. One sums 1,400 fields and is written for as many load cases as the ten million steps of the cells allow, 1.0 seconds. And one has a hinted proof that spends the twenty billion units on `exp` of fractions of 250 bits, 7.8 seconds. With products or quotients in place of `exp` the proof took 5 to 6 seconds. Before the tables were kept in order ([Tables](#tables)) the same files took 10.7 to 11.7 seconds.

Three more kinds of file are made to cost the tables the most. Numbers that share the hash the tables were once kept by, 30,000 in one table of a deck or 1,024 in a cache: 0.7 seconds and 5.8 to 6.1, where they took 45 to 50 and 85 to 90. Names of 64 characters that are alike to their last characters, for 1,400 fields of a joined part under 1,150 load cases: 0.7 to 0.8. And tapes of 40,000 different nodes for 70 parts, the shape that a table kept in order costs most beside one kept by a hash: 2.2, where they took 1.3. A busy machine takes longer in proportion. `tests/test_kernel_limits.py`, `tests/test_kernel_attacks2.py`, `tests/test_kernel_attacks3.py` and `tests/test_kernel_attacks4.py` hold the limits one by one.

Five kinds of file are made to cost the most by what a card, a design and a deck can state since 2026-11-11, each alone, in about 1 MB (`tests/test_deck_features2.py`, `Heaviest`). A card that states a key and a count for each of 4,800 parts: 0.5 seconds. A table read at 42,000 listed values, each written in the units that the kernel's list holds last: 1.1. A deck of 212 rules that each look through 190 fields for the one a part leaves unstated, for 47 parts: 1.1. A card of 9,000 loads under the floor of their dimension, which their type lets them be, and a given whose name is 400,000 dots: 0.8. And 1,209 requirements, of which the first nine are tried to the million and the rest are read untried: 0.3. None held more than 64 MB.

The heaviest file is still the first of this section, and two of the six things reach it. The rules of a waived line are run, so a waiver saves the kernel no work, and each open cell of a waived line costs a walk more over its box, to ask whether its rule says nothing there. And a rule may state `lt`, whose root is a pick. With its three lines waived and its three rules strict, that file took 14.1 and 15.2 processor seconds in two runs while the desktop did other work, and the file as it was took 13.8 beside the first of them. Both held 115 MB. With a walk for each of its 2,153 open cells it took 16.6, on a desktop busy with two other checks, and held 109 MB (`tests/test_kernel_attacks3.py`, `Worst`).

Three files are made to spend the twenty billion units on `cos`, and none takes as long as that first file (`tests/test_kernel_attacks3.py`, `Worst`). The first file itself, with two cosines of each fraction of 250 bits where it has one `exp`: 11.2 processor seconds and 115 MB while the desktop did other work, where the file as it was took 13.3 beside it. Cosines within 2^-2300 of zero, which ask for all four enclosures and have no value, 1,200 of them before the work runs out: 4.1 seconds and 33 MB. And looks in a cache that holds 1,000 ends of 16,000 bits that are alike, after the quarter of the work that rounding them takes: 5.0 seconds and 56 MB.

### What the kernel holds and prints

The kernel walks the leaves of a partition one at a time. On a leaf it gives up the enclosure of a node after the last node that reads it, and it holds at most 128 MB of enclosures at once. For a design with parts it also holds the deck of rules as it read it, which the million steps bound, and one tape: it writes the tape of a cell, settles the cell and gives the tape up. So what it holds is the files as it read them, the deck, one tape, the enclosures of one leaf, and three caches of at most 1,024 entries each.

Files of 1 MB made to hold as much of all of these at once as they can took 264 MB on the desktop the costs were fitted on. They hold a deck that takes just under the million steps to read, each two of them a number that the kernel keeps, a proof that keeps 4,080 enclosures whose numbers have 65,400 bits, and the rest of the megabyte in lists nested 120 deep, which the kernel parses and does not read. Alone, the kernel with an empty design takes 28 MB, with such a deck 97 MB, with the enclosures at their limit 186 MB, and with a megabyte of nested lists 68 MB.

A cell made from a deck of rules prints in at most about 370 bytes beside its reason: three names of at most 64, 64 and 135 bytes, and its states. All the cells print in at most 3.7 MB, their reasons in 0.5 MB more, and the cells past those reasons say so in at most 0.4 MB: 4.6 MB, whatever the files hold. The cells are the parts times the lines of the grid, so a small deck can reach most of that: 100 parts and 100 lines with names of 64 bytes are 89 KB of files and print 3.7 MB. A cell that proofs.json lists prints once, in under three times its own bytes.

`petra/grid.py` holds a name to the same 64 bytes and the name of a card to the same 200, counted the same way, and counts the steps to read a deck as the kernel does, so it refuses the same decks and designs. It has none of the other limits. Its tables are Python's, which are kept by a hash. Python hashes a text with a key that no file knows, and a whole number by its remainder on division by 2^61 − 1, which a file can work out. So `petra/grid.py`, `petra/deck.py` and `petra/kernel/interval.py` key a table by a text and by no number that a file writes: a name is a text before it is a key, the values a table is read at are compared each with the one before, and the caches of `ln`, `exp` and `cos` are kept by the digits of an end. The fourth review found the values of a table in a set: 30,000 of them that shared a hash took 312 processor seconds to read. `petra check` reports a design past the limit on cells or on steps as an input error, in the kernel's words. A proof the kernel does not finish for the budget of work, or does not write for the limit on a pick's orders, leaves a cell open that the grid proved, and `petra check` stops with exit code 4 and the kernel's reason.

## What the kernel does not check yet

For every design:

- The numbers in card.json and design.json are in SI, and the Python front end converted them from the units the card and the design write. The kernel reads the units of a deck of rules itself, and not those of a card or a design. It checks that a part's number has the dimension its field asks, by the exponents of the dimension that the file states.
- card.json is not a function of the card's text alone for a design of the models' kinds: an input that a component reads with `given` takes its name from the component. So the hash of card.json identifies a card together with a design, and the hash `petra check` prints on its `card` line, of the card's text, is the one to compare with the card that was issued. For a design with parts card.json is a function of the card alone ([The asker's card](#the-askers-card)).
- The interval rule is proved in Lean: a tape that the kernel proves has every root at most zero on its box, and a point it accepts as a refutation has its root above zero ([proved.md](proved.md)). So is what that means for a root that is the pick of an `lt` rule: the left side is under the right on the box, or not under it at the point. Nothing else on this page is proved. For the shape and type rules, the deck of rules, the cells and the verdict, the kernel is a second implementation, and `bench/kernel_grid.py` and the corpus compare it with the first.

For a design with no parts:

- The list of cells comes from Python, from the models' coverage rules. The kernel checks each cell and not that the list is complete.
- A tape's formula comes from Python's models. The kernel checks its arithmetic and its `in:` and `reg:` inputs, not that the formula is the standard's.
- Inputs labelled `dsg:` are the design's values as the models resolved them. The kernel does not tie them to `quantities`, and the verdict counts them.
- A `not_applicable` cell is the model's word.
- Proofs by the other five rules have no tape, and neither has an interval proof that leans on a defined quantity.
- A cell holds the proof of its own statement. The proofs that its model applies there (its validity rows) and the proof of a claim's margin are not in the file. `petra check` counts them among the proofs the kernel has no rule for.

For a design with parts:

- The deck of rules is the one `--rules` names. The kernel prints its hash and does not know whether it is the deck a reader means, or whether its rows are the standard's. [deck.md](deck.md) says what stands behind a row, and that nothing yet stands behind a type, a grid line or a rule but the hand that wrote it.
- The search for a partition or a point is Python's. A search that finds nothing leaves a cell open that may be provable or refutable. It cannot make a cell proved or refuted, and a waiver does not rest a cell that it could settle (Cells from a deck of rules, item 1). So a point that the search missed leaves the design UNKNOWN and not PASS, and it does not make it FAIL.
- The card that `petra.export` writes for a design with parts is refused without `parts` or without `--rules` (type rule 7). A card.json written by hand without the marks of rule 7 is not. With a design that has no `parts` it is checked as a design of the models' kinds, by the cells that proofs.json lists. That card.json has another hash than the asker's, and the verdict prints `cells_from` as `proofs` and null for the rules. What remains open is a reader who compares none of the three ([Reading a verdict](#reading-a-verdict)).
- `quantities` repeats the numbers of `parts` for the size rule. The kernel reads a part's numbers from `parts` and does not compare the two.
- No deck of rules reads an environment, so the card of a design with parts states none: one that does is refused, and not passed over. Its `cases` are read as the names of load cases and for nothing else, and the kernel does not hold them to the cases its loads name: the load cases are both together.
