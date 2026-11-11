# How a deck is written

A deck holds what Petra checks a design against, as data. It has four parts.

| Part | Holds |
|---|---|
| Rows | Each equation and each table of a standard |
| Types | The kinds of part a design may have, and the fields of each |
| The grid | For each type, every mechanism a part of that type must answer for |
| Rules | The answers: each binds rows to the fields of a part and states an inequality |

This page describes a row first, with the acceptance check that a row passes before it enters a deck. Then it describes types, the grid and rules, and what `petra check` does with a design whose parts are of a deck's types. `petra/deck.py` reads rows and runs the acceptance check. `petra/grid.py` reads the rest and checks a design. The kernel reads the whole deck a second time, in `kernel/Petra/Deck.lean`, and makes the cells of a design itself.

Rows are written by transcription, and the transcriber is not trusted. The acceptance check is what stands between a wrong transcription and a deck.

## A row

A row is a JSON object. This one is the hoop stress in a thin-walled pressure vessel.

```json
{
  "id": "example/hoop-stress",
  "anchor": {"standard": "a textbook", "clause": "8.2", "equation": "8-1", "page": "412"},
  "gives": {"name": "sigma_h", "dim": "stress", "what": "hoop stress in the wall"},
  "takes": [
    {"name": "p", "dim": "stress", "what": "internal gauge pressure", "range": ["0.1 MPa", "20 MPa"]},
    {"name": "r", "dim": "length", "what": "inner radius", "range": ["50 mm", "2 m"]},
    {"name": "t", "dim": "length", "what": "wall thickness", "range": ["1 mm", "50 mm"]}
  ],
  "is": ["div", ["mul", "p", "r"], "t"]
}
```

| Key | Holds |
|---|---|
| `id` | The deck's name for the row: the standard, a slash, and the equation number |
| `anchor` | Where the equation is: `standard`, `clause`, and `equation` and `page` when the standard gives them |
| `gives` | The quantity the equation gives: its `name` as the standard writes it, its `dim`, and `what` it is |
| `takes` | Each quantity the equation reads: `name`, `dim`, `what`, and a `range` |
| `is` | The expression, for an equation with one case |
| `cases` | The cases, for an equation the standard splits |
| `table` | The cells, for a table. A row has one of `is`, `cases` and `table`. |
| `jumps` | Each pair of cases that the standard does not make meet, and why: `[{"cases": [1, 2], "why": "..."}]`, counting cases from 1 |

A name is the standard's own symbol, written in plain letters: `Fu`, `Agv`, `lc`. A prime is written `_prime`, as in `Fnt_prime`. A row takes every quantity its expression reads. It reads no quantity from another row: where the standard defines one symbol by another equation, the row takes that symbol as an input.

A factor that the standard fixes as a number in the equation, such as a resistance factor, is written as that number and is not an input. So is a property the standard fixes with a unit, such as the modulus of elasticity of steel: it is a constant with its unit.

In the anchor, `page` is the page number as printed, and `equation` lists every equation number the row holds.

A `range` is two values, the lower first, between which a real design's value would fall. The check draws its sample points from the ranges, so a row with cases needs ranges wide enough for each case to hold somewhere.

### Dimensions

A `dim` is one of `dimensionless`, `length`, `area`, `force`, `stress`, `moment`, `mass`, `time`, `temperature`, `energy`, `current`, `voltage`, `power` and `resistance`. A power is written `length^3`, and a product or a quotient `force/length`.

A row carries no units. A value with a unit appears in two places: a range, and a constant that the standard gives with a unit. Every unit the language reference lists is allowed, such as `inch`, `inch2`, `kip`, `ksi`, `mm`, `mm2`, `kN` and `MPa`.

### Expressions

An expression is a number, a name, or a list that starts with an operator.

| Written | Means |
|---|---|
| `"2.4"`, `"3/4"` | An exact number: digits, and then a decimal part or a denominator. A decimal is the decimal the standard prints. |
| `"pi"` | Pi |
| `"Fu"` | An input of the row |
| `["q", "29000", "ksi"]` | A constant with a unit |
| `["add", a, b, ...]`, `["mul", a, b, ...]` | A sum, a product |
| `["sub", a, b]`, `["div", a, b]` | A difference, a quotient |
| `["neg", a]`, `["abs", a]`, `["sqrt", a]` | The negative, the absolute value, the square root |
| `["min", a, b, ...]`, `["max", a, b, ...]` | The least, the greatest |
| `["pow", a, "2"]`, `["pow", a, "3/2"]` | A power with a fixed exponent. A whole or a half power is at most 64. |
| `["pow", a, b]` | A power with an exponent that varies. Both must be plain numbers. |
| `["exp", a]`, `["ln", a]` | The exponential and the natural logarithm of a plain number |

The language has no sine, cosine or tangent and no sum over a list. An equation that needs one cannot be written as a row yet. Say so and do not approximate it.

### Cases

An equation that the standard splits is written as cases. Each case has a condition, `when`, and an expression, `is`. The first case whose condition holds gives the value, and the last case may leave `when` out to hold otherwise. Where the standard states one condition two ways, the row uses the way that reads the row's own inputs.

```json
"cases": [
  {"when": ["le", ["div", "L", "r"], "100"], "is": ["mul", "A", "sy"]},
  {"is": ["div", ["mul", "A", "sy", "10000"], ["pow", ["div", "L", "r"], "2"]]}
]
```

A condition is `["le", a, b]`, `["lt", a, b]`, `["ge", a, b]` or `["gt", a, b]` between two expressions of one dimension, or `["and", c, ...]`, `["or", c, ...]` or `["not", c]` of conditions.

## A table

A table of a standard is a row with `table` in place of an expression. This one gives a tolerance by nominal size and grade.

```json
{
  "id": "example/tolerance",
  "anchor": {"standard": "a textbook", "clause": "3.1", "table": "3", "page": "57"},
  "gives": {"name": "T", "dim": "length", "what": "tolerance on a size"},
  "takes": [
    {"name": "D", "dim": "length", "what": "nominal size", "range": ["1 mm", "30 mm"]},
    {"name": "grade", "one_of": ["fine", "medium", "coarse"], "what": "tolerance grade"}
  ],
  "table": {
    "down": {"by": "D", "bands": [["0 mm", "6 mm"], ["6 mm", "18 mm"], ["18 mm", "30 mm"]], "closed": "upper"},
    "across": {"by": "grade"},
    "unit": "um",
    "cells": [["8", "12", "0.1 mm"], ["11", "18", "0.12 mm"], ["13", "21", null]],
    "rises": ["D", "grade"]
  }
}
```

An input of a table is a quantity, as in an equation, or a key. A key is one of a few names that the standard uses to pick a line or a column, such as a grade, a hole type or a pollution degree. It has `one_of`, the names in the standard's order, and no `dim` or `range`. Only a table reads a key.

| Key of `table` | Holds |
|---|---|
| `down` | The side that picks the line. `by` names the input it reads. |
| `across` | The side that picks the column, for a table with two sides. A table with one side leaves it out, and `cells` is then a plain list. |
| `cells` | One line for each place of `down`, each with one cell for each place of `across`, as printed. `null` is a cell the standard leaves empty. |
| `unit` | The unit of a cell that states none. A cell may state its own, as `"0.1 mm"` does above. |
| `rises`, `falls` | The sides along which the printed values never go down, or never go up |

A side that reads a key has `by` alone, and its places are the key's names in order. A side that reads a quantity has one of two forms.

- `bands`: pairs of values, the lower end first, in order. `closed` says which end a band holds: `upper` for "above 6 mm up to and including 18 mm", which is the default, and `lower` for "6 mm and over, under 18 mm". A first band that the standard prints as "up to 6 mm" starts at `0`. A last band that the standard prints as "over 18 mm" has `null` for its upper end.
- `at`: the listed values, in order, for a table that gives a line for each standard size and nothing between them.

A value is written as the standard prints it, with a decimal point where the standard prints a decimal comma, and with no space or comma inside a number: `1100`, not `1 100`. A whole number and a fraction are written as printed, with one space: `1 1/8 inch`. Where a cell prints one value in two systems of units, the row holds the first, and the anchor says which.

A table's anchor has `table`, its number, and for `clause` a clause that cites it. Where the standard prints no symbol for what a table gives, `gives.name` is a short name of the transcriber's. The `range` of an input that a side reads is the span of that side. An empty cell does not break a run: `rises` and `falls` are checked over the cells that hold a value.

A table cannot hold everything a printed table does. A line whose cells are formulas, a cell with two numbers, and a footnote that changes a value under a condition are left out, and the transcriber says so. A row whose key leaves out a line has one name fewer than the table has lines.

Say `rises` or `falls` only where it holds for the whole table. It is what lets the check catch a cell that was misread.

## A worked example

A worked example is a use of the equation that a published source prints: the value of every input and the result. Examples are kept apart from the rows, in a file that names each row by its id.

```json
{"examples": {"example/hoop-stress": [
  {"anchor": "the textbook, Example 8.1, p. 414",
   "given": {"p": "1.5 MPa", "r": "600 mm", "t": "8 mm"},
   "gives": "112.5 MPa"}
]}}
```

`given` holds every input of the row, as the source states it, and a key by its name. It may hold more: a quantity the source states and the row does not read is ignored, and the row then reproduces the result only if it was right not to read it. `gives` is the result as printed, with its unit. A reproduction must come within 0.5% of the printed result, or within half a unit of its last printed digit when that is more, because a worked example rounds what it carries from line to line. `within` states another bound, such as `"1 %"`, when the print warrants it.

## The acceptance check

| Part | Passes when | Is `none` when |
|---|---|---|
| `units` | Every sum, comparison, minimum and maximum is of one dimension, every exponent and every argument of `exp` and `ln` is a plain number, and each case gives the row's dimension. For a table: every cell has the row's dimension and every band its input's. | never |
| `examples` | The row reproduces every worked example given for it | no example is given |
| `continuity` | For an equation: wherever one case hands over to another, the two differ by at most 1%, or `jumps` names that pair | no two sample points fell in different cases |
| `shape` | For a table, in place of continuity: the cells never go down along a side the row says it rises on, and never up along one it falls on | the row says neither |
| `second` | A second transcription, made without sight of the first, gives the same value at 96 points drawn from the ranges and at every meeting of the cases. For a table: in every cell and on each side of every band's ends. | no second transcription is given |

A row is admitted when no part fails. A part that is `none` is not a failure. It says the row has less behind it: a row with no worked example rests on its dimensions and on two transcribers agreeing.

The second transcription may name its inputs differently. The check tries each renaming that keeps the dimensions, and says which one it used. It may also name a key's values differently: they are matched by their order, which is the standard's.

```bash
python -m petra.deck rows.json --examples examples.json --second other_rows.json
```

The command prints each row as admitted or refused with the four parts, and exits 0 when every row is admitted, 1 when one is refused, and 3 when a file does not hold rows.

## What the check cannot see

- A transcription that is wrong in a way that keeps the dimensions, where no worked example exercises the error and a second transcriber makes the same mistake.
- An equation used outside the conditions its clause sets, when the row leaves those conditions out. A condition that is not a comparison of quantities, such as a hole type or a design method, cannot be written in a row at all.
- A single cell of a table read one digit off, or taken from the line below, where the table still rises as it should and no example reads that cell. In the second run the check with no second transcription refused 52% of damaged tables: nearly all of the cells read ten times too large or taken from the next column, and about one in ten of those one digit off. A table rests on its second transcription, which compares every cell.
- Whether the row is the right equation for a design. A rule binds rows to the parts of a design, and the acceptance check does not cover rules.

A row proves nothing by itself. A rule puts it to work.

## A deck

A deck is one JSON file in `petra/decks`.

| Key | Holds |
|---|---|
| `format` | `"petra-rules/0"` |
| `name` | The deck's name |
| `about` | What the deck covers |
| `rows` | The rows, each as described above |
| `types` | The types |
| `grid` | The lines of the grid |
| `rules` | The rules |

A design names a type as the kind of a component block: `lap splice { ... }` is a part named `splice` of type `lap`. The parts of one design are all of one deck's types, or all of the built-in models' kinds.

`petra/decks/aisc360.json` is the first deck. It holds 18 rows of AISC 360-22, the types `plate` and `lap`, a grid of 15 lines for a lap, and 4 rules.

### A type

```json
{"type": "plate", "what": "a flat steel plate that a joint connects",
 "fields": [
  {"name": "thickness", "dim": "length", "what": "its thickness"},
  {"name": "Fy", "dim": "stress", "signed": true, "what": "the specified minimum yield stress of its steel"}]}
```

A field is one line of the part's block. It is one of three things.

| A field with | Is | A design writes |
|---|---|---|
| `dim` | A quantity of that dimension, more than zero | `thickness 0.375 inch`, or `Fy given tab.Fy` |
| `one_of` | A key: one of the listed names | `threads included`, and in quotes when the name has a space: `fastener "Group 120"` |
| `type` | The parts of that type it joins, one for each name in `as` | `joins tab strap` |

A quantity may also have these.

| Key | Means |
|---|---|
| `signed` | Only the card states it, and the design reads it with `given`. A design that writes a number for it is refused. A material strength is signed. |
| `whole` | It is a count, and the design writes a whole number |
| `least` | The least value it may take |

The name of a field, of a load and of a joined part in `as` is letters, digits and `_`, as the language writes a name. So a rule's `a.Fy` is always a field of a joined part, and no name reads as a number. The kernel holds these names, a name of `let`, a mechanism and a rule's id to 64 characters, and a design to 10,000 cells ([format.md](format.md), "Limits").

A part has every field of its type once, and no other line. A part is joined by at most one other: a plate that two laps join would be checked under each lap's load alone, so the pair is refused.

`petra kinds lap` prints the lines of a type and what the grid asks of it, and `petra new lap` prints a design to start from, with its card under `--card`.

A part reads only the bound the card gives under the part's name and the field's. On the part `tab`, the line `Fy given tab.Fy` reads `given tab.Fy in [36 ksi, 36 ksi] signed ...` from the card, and `Fy given tab.Fu` is refused. So a design cannot read the bound for one field into another.

`as` gives each joined part the name a rule calls it by. With `"as": ["a", "b"]`, a rule reads `a.thickness` and `b.Fu`.

`loads` lists what a card may put on a part of the type. Each has a `name`, a `dim`, `what` it is, and a `least` when it has a floor. A card states one in a load case: `on splice pull in [0 kip, 45 kip]`.

### The grid

```json
{"type": "lap", "mechanism": "lap.spacing", "what": "minimum spacing of the holes",
 "anchor": {"standard": "AISC 360-22", "clause": "J3.4"}}
```

A line of the grid names one mechanism that every part of a type answers for, and the clause that raises it. The type is one of the deck's. The grid is written from the standard's own list of sections, and a line is there whether or not the deck has a rule for it. A line with no rule leaves its cell open, so a design cannot pass until the deck gets the rule or the card waives the mechanism.

A line may say that the mechanism cannot arise, and why:

```json
"unless": {"why": "a lap is a bearing-type joint, which claims no slip resistance"}
"unless": {"when": ["is", "fit", "close"], "why": "a close fit leaves no room for one"}
```

With no `when`, it never arises for the type. A condition is `["is", FIELD, NAME]` on a key field, `["loaded", LOAD]`, or `and`, `or` and `not` of these.

### A rule

A rule answers one line of the grid with an inequality.

```json
{"id": "aisc360-22/lap-yield-a", "type": "lap", "mechanism": "lap.ply_yield",
 "anchor": {"standard": "AISC 360-22", "clause": "J4.1", "equation": "J4-1"},
 "says": "the pull is at most 0.90 of the yield strength of the gross section of the first plate",
 "le": [["load", "pull"],
        ["mul", "0.90", ["row", "aisc360-22/J4-1", {"Fy": "a.Fy", "Ag": ["mul", "a.width", "a.thickness"]}]]]}
```

| Key | Holds |
|---|---|
| `id`, `type`, `mechanism` | The rule's name, and the line of the grid it answers |
| `anchor` | The clause the inequality comes from |
| `says` | The inequality in words |
| `le` | Two expressions. The rule holds when the first is at most the second. |
| `let` | Names for expressions the rule uses more than once. A name is letters, digits and `_`, and is no field's name. An expression reads the names before it. |
| `where` | The range the rule holds in: a list of `{"le": [a, b], "why": "..."}` |
| `when` | A condition on the part, as in the grid. The rule answers only for the parts it holds for. |

An expression is written as a row's is. A name in it is a quantity field of the part, `NAME.FIELD` for a part it joins, or a name from `let`. It has two more forms.

| Written | Means |
|---|---|
| `["load", NAME]` | A load the card puts on the part |
| `["row", ID, {INPUT: ...}]` | A row of the deck, with each of its inputs bound |

A quantity that a row takes is bound to an expression of its dimension. A key that a row takes is bound in one of three ways: to a key field whose names are all names of the row's key, to `["key", NAME]`, or to `["by", FIELD, {NAME OF THE FIELD: NAME OF THE ROW'S KEY}]`.

A factor that the clause fixes for the inequality, such as a resistance factor, is a number in the rule.

Reading a deck checks every rule. Each input of each row is bound once and to its dimension. Both sides of `le` have one dimension. The rule answers a line of the grid that can arise. A deck that fails any of these does not load, and the kernel finds a design checked against it ill formed.

## A design checked against a deck

`petra check` makes one cell for each answer and writes the files of [format.md](format.md): the card, the design with its parts as written, and the deck's own file. A cell has one of five states.

| State | When |
|---|---|
| `proved` | A rule's inequality holds for every value the card and the design allow |
| `refuted` | It fails at a point they allow |
| `not applicable` | The grid says the mechanism cannot arise for this part |
| `waived` | The card waives the mechanism on the part |
| `open` | Anything else |

No cell has a default. The verdict is FAIL with a refuted cell, UNKNOWN with an open cell or with nothing proved, and PASS otherwise.

`petra-verify` reads the same three files and makes the cells again, each with the tape of its rule. It takes nothing of a cell from `petra check` but a hint: the partition that proved it, or the point that refuted it. The kernel tries the hint on its own tape, and the state it settles on is its own. `petra check` then compares the two lists cell by cell, and stops with exit code 4 if they differ.

These cases are open:

- The grid has a line and the deck has no rule for it, or none that holds for this part.
- A rule reads a load and the card puts none on the part.
- A rule's `where` is not proved. Outside its range a rule says nothing, so its cell is never refuted there.
- A table has no value where the rule reads it: between the listed values of a table read at listed values, outside every band, or in an empty cell.
- The inequality is neither proved over the ranges the card gives nor refuted at a corner or the middle of them.
- No rule and no line of the grid reads a quantity or a key of a part. A value nothing reads is a value nothing checks, so a plate that no lap joins has an open cell for each of its fields, named `unread`.

A rule that reads a load has a cell for each load case that puts the load on the part. A rule with `where` has one more cell, named with `/where`, that proves its range.

A quantity on the end of a band reads the band that holds that end, exactly. Over a range that reaches into two bands or two cases, the inequality must hold in both.

```bash
petra check examples/deck/lap_unknown.petra
```

```
lap-splice: UNKNOWN
deck       sha256:d80024f8...  aisc360-22
card       sha256:b0372d69...  examples/deck/lap_unknown.card
design     sha256:ba2b35d4...  examples/deck/lap_unknown.petra
kernel     petra-verify checked 5 of 5 proofs and gives the same verdict
cells      5 proved, 0 refuted, 4 not applicable, 0 waived, 8 open
  splice/lap.spacing             open                    the deck has no rule for it (AISC 360-22 J3.4)
  splice/lap.end_distance        proved           0.667  lap-end-distance (AISC 360-22 J3.5, Table J3.4)
  splice/lap.strength            proved           0.838  lap-strength/gravity (AISC 360-22 J3.7 and J3.11, equation J3-1, J3-6a, J3-6c, Table J3.2, J3.3)
  splice/lap.slip                not applicable          a lap is a bearing-type joint, which claims no slip resistance (AISC 360-22 J3.9)
  ...
```

The number on a proved or refuted line is the most the left side of the rule reaches over the least the right side does. `examples/deck` has the same lap passing, with a card that waives the eight open mechanisms, and failing under a larger pull.

## What a deck does not check yet

- Types, grid lines and rules are written once, by hand. No second transcription and no worked example stands behind them, as they do behind a row.
- The kernel makes the cells and the tapes from the deck's file, and does not know whether that file is the standard's. It prints the file's hash.
- The kernel does not search. The partition or the point for a cell comes from `petra/grid.py`, so a cell that search does not settle is open, though a better search might prove it.
- A `not applicable` cell is the deck's word. The kernel checks that the line's `unless` holds for the part, and not that the mechanism cannot arise.
- The `range` of a row's input is where the acceptance check samples the row. It is not enforced as the range the row holds in. A rule's `where` is.
- A type with no line in the grid gets no cell of its own. A `plate` has none: the lap that joins it asks about it, and a plate that nothing joins has only its `unread` cells.
- A card's claims, tests and ambient, a family's params, and the repair that `petra check` suggests on a FAIL are not read for a design of a deck's types. A card or a design that states one is refused.
- The first deck has rules for 3 of the 15 lines of a lap's grid, all by LRFD. Four lines cannot arise for a lap, and eight are open: tightening, hole use, spacing, side distance, maximum spacing, tensile rupture, block shear and flexure of the plates.
