# How a deck is written

A deck holds what Petra checks a design against, as data. It has four parts.

| Part | Holds |
|---|---|
| Rows | Each equation and each table of a standard |
| Types | The kinds of part a design may have, and the fields of each |
| The grid | For each type, every mechanism a part of that type must answer for |
| Rules | The answers: each binds rows to the fields of a part and states an inequality |

This page describes a row first, with the acceptance check that a row passes before it enters a deck. Then it describes types, the grid and rules, what `petra check` does with a design whose parts are of a deck's types, and the acceptance check that a rule passes. `petra/deck.py` reads rows and runs their acceptance check. `petra/grid.py` reads the rest and checks a design. `petra/rule.py` runs the acceptance check for rules. The kernel reads the whole deck a second time, in `kernel/Petra/Deck.lean`, and makes the cells of a design itself.

Rows and rules are written by transcription, and the transcriber is not trusted. An acceptance check is what stands between a wrong transcription and a deck.

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

An anchor has `standard` and `clause`, each a text that is not empty, and may have `equation`, `table` and `page`, each a text. `page` is the page number as printed, and `equation` lists every equation number the row holds. A row with no anchor, or with an anchor that lacks its standard or its clause, is refused. So is a line of the grid and a rule.

A `range` is two values, the lower first, between which a real design's value would fall. The check draws its sample points from the ranges, so a row with cases needs ranges wide enough for each case to hold somewhere. Every quantity a row takes has a `range`, and a row whose input has none is refused. Each end states its unit, as every value of a dimension does ([A value with its unit](#a-value-with-its-unit)).

A row has `id`, `anchor`, `gives`, `takes` and one of `is`, `cases` and `table`. `gives` has `name` and `dim`, each a text, and an input has `name`. A table that gives a name has `one_of` in place of `dim` ([A table that gives a name](#a-table-that-gives-a-name)). The `what` of `gives` and of an input may be left out. A jump has `cases` and `why`. `cases` is a list of whole numbers, each one of the row's cases counted from 1, in which exactly two different numbers stand: `[1]` and `[1, 2, 3]` are refused. `why` is a text that is not empty.

### Dimensions

A `dim` is one of `dimensionless`, `length`, `area`, `force`, `stress`, `moment`, `mass`, `time`, `temperature`, `energy`, `current`, `voltage`, `power` and `resistance`. A power is written `length^3`, and a product or a quotient `force/length`.

A row carries no units. A value with a unit appears in two places: a range, and a constant that the standard gives with a unit. Every unit the language reference lists is allowed, such as `inch`, `inch2`, `kip`, `ksi`, `mm`, `mm2`, `kN` and `MPa`. A deck also reads `N m`, which a design cannot write.

A unit is one spelling of that list, read whole. `m/s`, `km/h`, `kg/m3`, `g/cm3`, `N/mm` and `ohm/km` are each one unit, with the `/` in the spelling: no unit is worked out from two others, so `mm/s` and `kg/m^3` are refused. A dimension that has no name of its own is written from the names: a speed is `length/time`, a speed of rotation `dimensionless/time`, a charge `current*time`, a density `mass/length^3` and a stiffness `force/length`. [reference.md](reference.md), "Units", gives the factor of each unit and where it comes from, says that a turn and an angle are plain numbers, and says why the one unit of temperature is `degC`.

A unit of length may be raised to a power: the unit, `^` and the power, with no space, as in `mm^3` and `inch^4`. The units of length are `m`, `mm`, `um`, `cm`, `km`, `inch`, `ft` and `mile`. The power is `2`, `3` or `4`, written as that one digit. The factor is the unit's own factor to that power, exactly, and the dimension is `length^2`, `length^3` or `length^4`: `1 inch^4` is (127/5000)^4 m^4. So a section modulus is written `20 inch^3` and a moment of inertia `100 inch^4`.

- An area has two spellings and one meaning: `mm^2` is `mm2`, `m^2` is `m2` and `inch^2` is `inch2`. Both are accepted wherever a value stands.
- No other unit takes a power. `kN^2`, `ksi^2`, `mm2^2` and `1^2` are refused. A power of a unit that is itself a product or a quotient, as `ohm/km` and `kip_in` are, could be read two ways, and no quantity of a deck needs one.
- Any other power is refused, and so is any other spelling of these three: `inch^0`, `inch^1`, `inch^5`, `inch^3/2`, `inch^04`, `inch^+4` and `inch^2^2`.
- A power is part of a unit. It stands in no number: `"2^2"` and `"2 mm^2"` are no numbers alone, and a `dim` is `length^4`, never `mm^4`.

A power works wherever a value is read: a `range`, a `least`, the end of a band, a listed value of `at`, a cell, the `unit` of a table, a `["q", NUMBER, UNIT]`, a number of a design and a bound of a card.

### A value with its unit

A value is a text: a number, one space, and a unit. It stands in a `range`, a `least`, the end of a band, a listed value of `at` and a cell of a table. `["q", NUMBER, UNIT]` holds its two halves, which are joined with one space and read as one value. Both halves are texts. So a `q` takes whatever a value takes: `["q", "29,000", "ksi"]` and `["q", "1 1/8", "inch"]` are read, and `["q", "3", ""]` is `3 `, the plain number 3.

- The number is digits with an optional sign, and then a decimal part or a denominator that is not zero: `0.75`, `-3`, `3/4`. The digits are `0` to `9`.
- A whole number and a fraction with one space between them are their sum: `1 1/8 inch` is 9/8 inch. This form takes no sign.
- A comma is read between thousands and nowhere else: `29,000 ksi` is 29000 ksi, and `2,90` is refused. The digits before the first comma are one to three, and each group after a comma is three. A comma stands only in the digits before a decimal point, in a whole number or a decimal: `29,000` and `1,234.5`. A number with a `/` takes none, so `1,000/3` and `1,000 1/8 inch` are refused.
- A value with no unit is a plain number, of no dimension. So `1 1/2` alone is the number 3/2, and `1,000` alone is the number 1000.
- `0` and `-0` alone are the plain number zero. They are not the zero of every dimension: a length that is zero is written `0 mm`, and a range, a band or a `least` of a length that starts at a bare `0` is refused for its dimension.
- Spaces, tabs and line ends around the value are dropped, and so are those around the unit. No other character is. A line end is a line feed or a carriage return.
- The space that parts the number from its unit is the first space of the value, the character U+0020. More spaces, tabs and line ends may follow it before the unit, and they are dropped: `3  inch` is 3 inch. A tab alone does not part the two, so `3` and a tab and `inch` is refused. A whole number and its fraction have exactly one space between them.

A number alone in an expression, such as `"2.4"`, is the first form only. It takes no comma and no whole number with a fraction.

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
| `["cos", a]` | The cosine of a plain number, an angle in radians |

`cos` is the one operator for angles. Its argument is a plain number and so is its value: a deck that takes the cosine of a length is refused when it is read. An angle is in radians, and any angle of up to 65,536 in size has a cosine. A larger one has none, and a cell whose rule reads it is open, as for a division by a range that holds zero.

The language has no sine, no tangent, no inverse of them and no degrees. A row writes the first two and the last with `cos` and `pi`:

| Wanted | Written |
|---|---|
| The sine of `x` | `["cos", ["sub", ["div", "pi", "2"], "x"]]`, the cosine of a quarter turn less `x` |
| The cosine of `x` degrees | `["cos", ["mul", "x", ["div", "pi", "180"]]]` |
| The tangent of `x` | The sine over the cosine |

An angle in degrees stays a plain number: the row multiplies it by pi over 180 itself, so the factor is on the tape and the kernel checks it with the rest.

`pi` is held between two fractions 2^-96 apart, and a cosine is rounded outward to the same grid ([format.md](format.md), "Tapes"). So a design that sits exactly on a limit which is a cosine, as 1/2 is the cosine of 60 degrees, is neither proved nor refuted, and its cell is open.

An equation that needs an arc cosine or another inverse, or a sum over a list, cannot be written as a row yet. Say so and do not approximate it.

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
| `unit` | The unit of a cell that states none. A cell may state its own, as `"0.1 mm"` does above. Spaces, tabs and line ends around a cell are dropped first. A cell that then holds a space is read as stating its own, and any other cell is read in the table's `unit`: `"1 "` under `"unit": "inch"` is 1 inch. So `"1,000"` under `"unit": "um"` is 1000 um, and a whole number with a fraction in a cell is written with its unit, `"1 1/8 inch"`: `"1 1/8"` alone is the plain number 9/8, whatever `unit` says. |
| `rises`, `falls` | The sides along which the printed values never go down, or never go up. Each is a list of texts, and each text is the `by` of a side of this table. A name may stand twice in a list. No name is in both lists. A list that names anything else is refused. |

A side that reads a key has `by` alone, and its places are the key's names in order. A side that reads a quantity has one of two forms.

- `bands`: pairs of values, the lower end first, in order. `closed` says which end a band holds: `upper` for "above 6 mm up to and including 18 mm", which is the default, and `lower` for "6 mm and over, under 18 mm". A first band that the standard prints as "up to 6 mm" starts at zero, written with its unit: `0 mm`. A last band that the standard prints as "over 18 mm" has `null` for its upper end.
- `at`: the listed values, in order and each once, for a table that gives a line for each standard size and nothing between them.

A band's lower end is under its upper end, and no band starts before the one before it ends. A side whose bands are out of order or lie over one another is refused, and so is a side whose listed values are out of order. A side with `at` has no `closed`: it has no band to close.

A value is written as the standard prints it, with a decimal point where the standard prints a decimal comma, and with no space or comma inside a number: `1100`, not `1 100`. A whole number and a fraction are written as printed, with one space: `1 1/8 inch`. Where a cell prints one value in two systems of units, the row holds the first, and the anchor says which.

A table's anchor has `table`, its number, and for `clause` a clause that cites it. Where the standard prints no symbol for what a table gives, `gives.name` is a short name of the transcriber's. The `range` of an input that a side reads is the span of that side. An empty cell does not break a run: `rises` and `falls` are checked over the cells that hold a value.

A table cannot hold everything a printed table does. A line whose cells are formulas, a cell with two numbers, and a footnote that changes a value under a condition are left out, and the transcriber says so. A row whose key leaves out a line has one name fewer than the table has lines.

Say `rises` or `falls` only where it holds for the whole table. It is what lets the check catch a cell that was misread.

### A table that gives a name

Some tables of a standard give no quantity. They sort a part into a category by its sizes, and other tables are then read at that category. Such a table is a row whose `gives` has `one_of` in place of `dim`, and whose cells are names.

```json
{
  "id": "example/category",
  "anchor": {"standard": "a textbook", "clause": "4.2", "table": "7", "page": "90"},
  "gives": {"name": "category", "one_of": ["B", "C", "D", "E"], "what": "the category of an attachment"},
  "takes": [
    {"name": "a", "dim": "length", "what": "its length", "range": ["1 mm", "300 mm"]},
    {"name": "t", "dim": "length", "what": "its thickness", "range": ["1 mm", "100 mm"]}
  ],
  "table": {
    "down": {"by": "a", "bands": [["0 mm", "50 mm"], ["50 mm", "100 mm"], ["100 mm", "200 mm"]], "closed": "upper"},
    "across": {"by": "t", "bands": [["0 mm", "25 mm"], ["25 mm", null]], "closed": "upper"},
    "cells": [["B", "B"], ["C", "D"], ["E", null]]
  }
}
```

- `gives` has `name`, `one_of` and perhaps `what`. `one_of` is the names the table can give, in the standard's order: a list of texts that is not empty, each once. `gives` has `dim` or `one_of`, and never both.
- The row is a table. A row that gives a name with `is` or `cases` is refused.
- It takes quantities and no key, so each side reads a quantity, in `bands` or `at`, exactly as a side of any table does. A table with one side derives the name from one quantity, and a table with two sides from two.
- A cell is one of the names of `one_of`, as a text, or `null` where the standard gives none. Any text of `one_of` is a name, whatever it looks like: the text `"null"` is a name and `null` is an empty cell. A cell that holds anything else is refused.
- Every name of `one_of` is the name of at least one cell. A row that lists a name that no cell holds is refused, and the refusal names the row and the name. Such a name is one that no part can have. A `case` over the row would still give it an expression, and nothing would ever read that expression: what only it named would count as read and be checked by no cell. So there is no such branch. Every name a row gives is one some sizes reach, and every expression of a `case` is one some part's cell is written from.
- The table has `down`, `cells` and perhaps `across`, and no other key: no `unit`, no `rises` and no `falls`.

The bands say what the table covers. A value in no band, between two listed values, or at an empty cell has no name. Nothing is assumed there: a rule that reads the name has no value, and its cell is open. A value on the end of a band is in the band that holds that end.

A name is read in two ways, both in a rule: as a key of a row, and by a `case` ([A rule](#a-rule)). It is no quantity, so `["row", "example/category", {...}]` in a sum, a product or a side of `le` is refused. A row applies no row, so no row reads a name.

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
| `units` | Every sum, comparison, minimum and maximum is of one dimension, every exponent and every argument of `exp`, `ln` and `cos` is a plain number, and each case gives the row's dimension. For a table: every cell has the row's dimension and every band its input's. | never |
| `examples` | The row reproduces every worked example given for it | no example is given |
| `continuity` | For an equation: wherever one case hands over to another, the two differ by at most 1%, or `jumps` names that pair | no two sample points fell in different cases |
| `shape` | For a table, in place of continuity: the cells never go down along a side the row says it rises on, and never up along one it falls on | the row says neither |
| `second` | A second transcription, made without sight of the first, gives the same value at 96 points drawn from the ranges and at every meeting of the cases. For a table: in every cell and on each side of every band's ends. | no second transcription is given |

A row is admitted when no part fails. A part that is `none` is not a failure. It says the row has less behind it: a row with no worked example rests on its dimensions and on two transcribers agreeing.

The second transcription may name its inputs differently. The check tries each renaming that keeps the dimensions, and says which one it used. It may also name a key's values differently: they are matched by their order, which is the standard's.

A table that gives a name passes the same check. `units` holds every band to its input's dimension. `shape` is `none`, since a name neither rises nor falls. A worked example gives the name the source prints, as `"gives": "D"`. `second` compares the name in every cell and on each side of every band's ends, and matches the names of the two transcriptions by their order in `one_of`.

```bash
python -m petra.deck rows.json --examples examples.json --second other_rows.json
```

The command prints each row as admitted or refused with the four parts, and exits 0 when every row is admitted, 1 when one is refused, and 3 when a file does not hold rows.

## What the check cannot see

- A transcription that is wrong in a way that keeps the dimensions, where no worked example exercises the error and a second transcriber makes the same mistake.
- An equation used outside the conditions its clause sets, when the row leaves those conditions out. A condition that is not a comparison of quantities, such as a hole type or a design method, cannot be written in a row at all.
- A single cell of a table read one digit off, or taken from the line below, where the table still rises as it should and no example reads that cell. In the second run the check with no second transcription refused 52% of damaged tables: nearly all of the cells read ten times too large or taken from the next column, and about one in ten of those one digit off. A table rests on its second transcription, which compares every cell.
- Whether the row is the right equation for a design. A rule binds rows to the parts of a design, and a rule has an acceptance check of its own, described below.

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

Each object of a deck has the keys this page gives it, and no other. A key the page does not give is refused wherever it stands: in the deck, a row, an `anchor`, `gives`, an input of `takes`, a case, a jump, a table, a side of a table, a type, a field, a load, a need, a line of the grid, `unless`, a rule and an item of `where`. So is a key where it does not belong: `whole`, `least` or `may_be` on a field that is no quantity, `signed` on a field that joins parts, `optional` on a field that joins parts or on a load, `as` on a field that joins no part, and `closed` on a side with no `bands`. The refusal names the key. A misspelled key is then an error, and never a key left out with its default in its place: `close` for `closed` would leave every band closed at its upper end.

A design names a type as the kind of a component block: `lap splice { ... }` is a part named `splice` of type `lap`. The parts of one design are all of one deck's types, or all of the built-in models' kinds.

`petra/decks/aisc360.json` is the first deck. It holds 32 rows of AISC 360-22, the types `plate` and `lap`, a grid of 16 lines for a lap, and 15 rules. The rules answer 8 of the lines. [What the first deck covers](#what-the-first-deck-covers) lists every line, what answers it, and what the deck leaves open.

### The size of a deck

Reading a deck takes steps, and a deck that takes more than 1,000,000 is refused before a row of it is read. The count is made from the deck's JSON alone, by three rules.

1. The size of a JSON value is 1 for a number, `true`, `false` and `null`. The size of a text is 2, and 1 more for each 8 characters it holds: 2 for a text of up to 7 characters, 3 from 8, 4 from 16. A character is one code point of Unicode, however many bytes it takes. The size of a list is 1 more than the sizes of its items. The size of an object is 1 more than the sizes of its values. A key is not counted.
2. A rule applies a row at each list `["row", ID, BINDS]`: a list of exactly three items whose first is the text `row` and whose second is a text. Every such list inside an item of `rules` counts, wherever in the item it stands. It counts the size of the first item of `rows` that is an object with that text as its `id`, and nothing when no row has that `id`.
3. The steps of a deck are the size of its whole file and what rule 2 counts.

The count follows the work. A rule reads a row again each time it applies it, with the row's inputs bound to the rule's expressions, and it reads everything else in the file once. A text of an expression is a name or a number. The kernel goes through it character by character each time it reads it, and a number becomes a step of the rule that the kernel keeps: so a text counts for its length, and for two where a list counts for one. A name is found through a table whatever the deck holds, and a type that joins many parts costs a rule only the names the rule writes.

The first deck, 58 KB, takes 10,019 steps: 6,238 for its file and 3,781 for the 37 times its rules apply a row. That is about a hundredth of the limit, so ten decks of that size are a tenth of it. With the 18 rows and 4 rules it shipped until 2026-11-11 it took 5,500. A file under 1 MB whose rules apply no row is always within it: a text of `n` characters takes `n` and three bytes with its quotes and its comma, and any other value two or more, so a megabyte holds under 700,000 steps. So the limit refuses one kind of deck: a long row applied many times. `petra/grid.py` makes the same count and refuses the same decks.

### A type

```json
{"type": "plate", "what": "a flat steel plate that a joint connects",
 "fields": [
  {"name": "thickness", "dim": "length", "what": "its thickness"},
  {"name": "Fy", "dim": "stress", "signed": true, "what": "the specified minimum yield stress of its steel"}]}
```

A type has `type`, its name, `what`, a text, and `fields`. Its `what` may be the empty text. It may have `loads` and `needs`, which are described below.

A field is one line of the part's block. It has `name`, `what`, a text that is not empty, and one of `dim`, `one_of` and `type`. It is one of three things.

| A field with | Is | A design writes |
|---|---|---|
| `dim` | A quantity of that dimension, more than zero unless it says `may_be` | `thickness 0.375 inch`, or `Fy given tab.Fy` |
| `one_of` | A key: one of the listed names | `threads included`, and in quotes when the name has a space: `fastener "Group 120"`, or `category given beam.category` |
| `type` | The parts of that type it joins, one for each name in `as` | `joins tab strap` |

A quantity may also have these. A key may have `optional` and `signed`, and no other of them.

| Key | Means |
|---|---|
| `optional` | A part may leave it unstated: the design writes `unstated` in its place ([A field that a record may leave unstated](#a-field-that-a-record-may-leave-unstated)) |
| `signed` | Only the card states it, and the design reads it with `given`. A design that writes a number or a name for it is refused. A material strength is signed, and so is a design category ([What the card states of a part](#what-the-card-states-of-a-part)). |
| `whole` | It is a count: a whole number, which the design writes or the card states exactly. A count is a plain number, so its `dim` is `dimensionless`, and a `whole` field of any other dimension is refused. |
| `least` | The least value it may take |
| `may_be` | `"zero"`: it may be zero, and not under it. `"negative"`: it may be zero or under it. Without `may_be` a quantity of a part is more than zero. |

The name of a field, of a load and of a joined part in `as` is letters, digits and `_`, as the language writes a name. So a rule's `a.Fy` is always a field of a joined part, and no name reads as a number. The kernel holds these names, a name of `let`, a mechanism and a rule's id to 64 bytes as printed, and a design to 10,000 cells ([format.md](format.md), "Limits").

A part has every field of its type once, and no other line. A field that is `optional` is there too, with its value or with `unstated`. A part is joined by at most one other: a plate that two laps join would be checked under each lap's load alone, so the pair is refused.

`petra kinds lap` prints the lines of a type and what the grid asks of it, and `petra new lap` prints a design to start from, with its card under `--card`.

A part reads only the bound the card gives under the part's name and the field's. On the part `tab`, the line `Fy given tab.Fy` reads `given tab.Fy in [36 ksi, 36 ksi] signed ...` from the card, and `Fy given tab.Fu` is refused. So a design cannot read the bound for one field into another.

`as` gives each joined part the name a rule calls it by. With `"as": ["a", "b"]`, a rule reads `a.thickness` and `b.Fu`. A design lists one part for each name, in the order of `as`: in `joins tab strap` the part `tab` is `a` and `strap` is `b`. Which part fills which name is a statement of the design, read like any field, and nothing in a card or a deck checks it: `joins strap tab` is another design, which a line or a rule that asks about `a` may answer another way, and the order must be true of what is built.

`loads` lists what a card may put on a part of the type. Each has a `name`, a `dim`, `what` it is, a text that is not empty, and a `least` when it has a floor. A card states one in a load case: `on splice pull in [0 kip, 45 kip]`.

### What the card states of a part

Some fields are not the designer's to choose. A lifter's design category sets its safety factor, a drone's class sets the rules it flies under, and the shop a cut part is checked for sets every limit. A design that wrote its own would pick its own verdict. So a type marks such a field `signed`, as it marks a strength, and the card states it.

```json
{"name": "category", "one_of": ["A", "B", "C"], "signed": true, "what": "the design category"}
{"name": "lugs", "dim": "dimensionless", "whole": true, "signed": true, "what": "the number of lugs the lift needs"}
```

```
given b.category is B signed "rigging@example.org" source "lift plan LP-7"
given b.lugs is 2 signed "rigging@example.org" source "lift plan LP-7"
```

```
beam b {
  category given b.category
  lugs given b.lugs
}
```

The design asks with `given NAME`, as it asks for a bound, and the card answers under the same name, `PART.FIELD`. What differs is the answer. A quantity that is no count is a range, `in [lo, hi]`. A key and a count are exact, so the card states them with `is` and no range: the name of the key, as a bare word or in quotes, or one whole number with no unit. [reference.md](reference.md) gives the grammar, and [format.md](format.md) says how card.json holds a statement, in `states`.

| A field | The design writes | The card states |
|---|---|---|
| A quantity that is no count | a number, or `given NAME` | `given NAME in [lo, hi] signed ...` |
| A count (`whole`) | a whole number, or `given NAME` | `given NAME is 4 signed ...` |
| A key | a name, or `given NAME` | `given NAME is B signed ...` |

`signed` takes the first way from the design: the field is then a given, and a design that writes it is refused, with a finding that says the field is for the card to state. Without `signed` either may state the field. So a card may fix a key that its type leaves open, and the design reads it the same way.

- The form follows the field. A bound for a key or for a count is refused, and so is `is` for a quantity that is no count, a whole number for a key, and a name for a count. A key named `"2"` is stated in quotes, `is "2"`: without them `2` is a number.
- The name is one of the key's names, and the count is within its field's floor and its `least`, as if the design had written it.
- A part reads only what the card states for it: on the part `b`, the line `category given c.category` is refused.
- A design that reads a given the card does not state is refused, and the finding names the part and the field: `b.category: the card states no b.category`.
- The card states a thing once, and states nothing that no part reads: a statement for a part that is not there, or for a field that its design wrote itself, is refused. A statement and a bound do not share a name.
- A statement carries a signature, as a bound does, and one with none is refused.

Whatever reads the field reads it the same, whoever stated it: a `when`, an `unless`, a `requires`, a key of a table, a `by`, a need, and a rule that reads the count as a number. A count that the card states is an input of a tape under the label `in:CARD.PART.FIELD`, with one value. The cells are the cells of the same part with the field written by its design.

The value is in card.json, so the hash of the card covers it: a card that states category B and one that states C have two hashes ([format.md](format.md), "Reading a verdict").

### A field that a record may leave unstated

A standard's table is complete. A maker's data sheet is not: one maker of propellers states a greatest speed and no greatest thrust, another the thrust and no speed, and many battery packs state no resistance. A design must not make the number up. So a type may mark a quantity or a key `optional`, and a design then writes the one word `unstated` in place of its value.

```json
{"name": "speed_limit", "dim": "dimensionless/time", "optional": true, "what": "the greatest speed its maker allows"}
```

```
rotor_set r {
  speed_limit unstated
  thrust_limit 12 N
}
```

- `optional` is `true` or `false`, and a field without it is not optional. It stands on a quantity, a count among them, and on a key. A field that joins parts and a load have none. A field is not both `optional` and `signed`, and a card cannot state `unstated`: what a record leaves out is for the design to say, since the design names the part, and only the card states a signed field.
- The word is `unstated`, bare and alone on its line. In quotes it is a text, which no quantity takes and which is no name of an optional key. A key that is `optional` has no name `unstated`, and a deck that gives it one is refused. On a key that is not optional, `unstated` is a name like any other when the key lists it.
- A field that is not optional must be stated, as before: `unstated` on a quantity that is not optional is refused, with a finding that says so.
- A field left unstated has no value. It takes no default and is never read as zero.

What reads an unstated field has no answer, and says so.

- **A rule.** A rule that reads the field gives the cells it would give, each `open`. It reads the field in a side of its inequality, in its `where`, in a row or a `case` it applies, in its `when` or in its `requires`. It has one cell, entered as the rule's, when it has `requires`, reads no load, or the card has no load case. Otherwise it has one cell for each load case, entered `RULE/CASE`. It has no `/where` cell. The reason names the field by the part that has it and says that its maker states none: `r.speed_limit is unstated: its maker states none, and the rule reads it`. The kernel names the first such field in the order the rule reads its fields. `petra check` prints its own reason, which names the first by name where a rule reads several.
- **A `when`.** A rule whose `when` names an unstated key answers: nothing says that it does not apply. Its cells are open, as above. So a line is not left "with no rule for a part like this one" because a key was left out.
- **An `unless`.** A line whose `unless` names an unstated key is one `open` cell with an empty entry, and no rule of the line is run: nothing says whether the mechanism can arise. Its reason is ``r.guard is unstated: its maker states none, and the `unless` of the line reads it``.
- A condition is not decided in part. `["or", ["is", "guard", "full"], ["is", "finish", "none"]]` with `finish` unstated is not decided, though `guard` alone would settle it.
- **A need.** A need that names an unstated field is not asked of the part. It is neither kept nor broken, and it does not refuse the part.
- **Nothing.** An unstated field that nothing reads has no `unread` cell: there is no value that something failed to check.

So leaving a field out never helps a design past a rule. Every cell that would have read it is open. A waiver rests a cell whose rule, or whose line's `unless`, reads a key left unstated, since what is unsaid is which rule answers or which line of a table. It does not rest one whose rule reads a quantity left unstated: the rule's inequality could be answered for every value the quantity may take, so the cell stays open and the design is UNKNOWN ([What a waiver rests](#what-a-waiver-rests)).

### A quantity at or under zero

A size is more than zero, and most quantities of a part are sizes. Some are not: the lowest temperature a battery may be discharged at, a position measured from a datum, a count of spares that may be none. A field says so with `may_be`.

```json
{"name": "low", "dim": "temperature", "may_be": "negative", "least": "-40 degC", "what": "the lowest temperature it may be discharged at"}
{"name": "offset", "dim": "length", "may_be": "zero", "what": "from the datum to its near end"}
```

A design then writes `low -10 degC` and `offset 0 mm`, and a card may give either with `given`.

| A field says | Its value is | A `least` beside it |
|---|---|---|
| nothing | more than zero | may be there, and holds too |
| `"may_be": "zero"` | at least zero | is refused: the floor is zero |
| `"may_be": "negative"` | of any sign | is under zero, or left out. One at zero or above is refused. |

`may_be` is one of those two texts. Anything else is refused: `true`, `"positive"`, `"Zero"`. It stands on a quantity, a count among them, and on no key and no field that joins parts.

A load has no floor by its sign: it may be zero or negative as it is, unless its `least` says otherwise. But the kernel holds every bound of a card to the floor that its dimension has in deck.json ([format.md](format.md), type rule 4), and there a length, a mass, a time and seven more are at least zero. So a load that is a position needs `"may_be": "negative"` to go under zero. On a load, `may_be` is `"negative"` or left out: `"zero"` says nothing a load does not say already, and is refused.

`may_be: negative` lifts a floor at zero and no other. The floor of a temperature in deck.json is absolute zero, -273.15 degC. It holds for every temperature of a part and of a card, whatever `may_be` says: a number the design writes under it, and a bound of the card that reaches under it, are refused.

A temperature is a number on the Celsius scale, and the kernel does arithmetic on that number as on any other. It does not know a temperature from a difference of two temperatures: both have the dimension `temperature`. A sum, a difference, a comparison, a least and a greatest of temperatures mean what they say. A product or a quotient of a temperature means something only where the temperature is a difference, as in an expansion over a rise of 30 degC. Twice 20 degC is not a temperature, and the kernel computes 40 all the same: the `units` part of an acceptance check passes it. A rule that needs an absolute temperature adds `["q", "273.15", "degC"]` itself. [reference.md](reference.md), "Units", says why there is no `K` and no `degF`.

A quotient by a quantity that is zero has no value, and neither has a root of one under zero or a logarithm of one at zero or under it. In a rule, the cell is then open: the kernel's proof fails where a root reads a division by a range that contains zero, and so does a refutation at a point where the divisor is zero.

A deck whose rule divides by a field that says `may_be`, or by a load that says it, is refused when it is read, and so is one whose rule takes the root of a quantity that `may_be` lets be under zero, or the logarithm of one that it lets be zero or under. The deck says such a value is a value the part may have, and at it the rule says nothing, so a part there could never be checked by the rule. Both readers find the field through what stands for it: a name of `let`, an input of a row that the rule binds to it, a power of it other than zero, and its root. An even power of a field that may be under zero is at least zero, and may be under a root. A power that is not whole or half is the exponential of a logarithm, and a field that `may_be` lets be zero is refused as its base. A sum or a product that holds such a field is not looked into: `offset + station` may be a divisor, and its cell is open where it is zero. In a need, a field that says `may_be` is refused as a divisor in the same way ([What a type needs](#what-a-type-needs)).

### What a type needs

A pin larger than its hole, a hole wider than its plate and a span longer than its beam are not weak designs. They are not designs. A rule would work a strength out from such a part and might prove it. So a type may state `needs`: what must hold among its fields for a part of it to be a part at all.

```json
{"type": "eye", "what": "a plate with a hole for a pin",
 "fields": [
  {"name": "hole", "dim": "length", "what": "the diameter of its hole"},
  {"name": "width", "dim": "length", "what": "its width"},
  {"name": "edge", "dim": "length", "what": "from the centre of the hole to the edge beyond it"},
  {"name": "pin", "type": "pin", "what": "its pin"}],
 "needs": [
  {"lt": ["pin.d", "hole"], "why": "a pin passes through its hole"},
  {"lt": ["hole", "width"], "why": "a hole is narrower than its plate"},
  {"le": [["div", "hole", "2"], "edge"], "why": "the edge lies beyond the hole"}]}
```

`needs` is a list with at least one item: a type that needs nothing leaves it out, and `"needs": []` is refused. A need has `le` or `lt`, never both, and `why`, a text that is not empty. `le` and `lt` hold two sides of one dimension: with `le` the first is at most the second, and with `lt` it is under it.

A side is one of these, and nothing else.

| Written | Means |
|---|---|
| `"hole"` | A quantity field of the type |
| `"pin.d"` | A quantity field of a part the type joins, by the name `as` gives that part, as a rule reads it |
| `"2"`, `"3/4"`, `["q", "1/16", "inch"]` | A number, and a constant with its unit, as in a row |
| `["add", a, b, ...]`, `["mul", a, b, ...]` | A sum, a product |
| `["sub", a, b]`, `["neg", a]` | A difference, the negative |
| `["div", a, b]` | A quotient, where `b` is a field that is more than zero or a number that is not zero |

Exact fractions decide these, and that is why the list ends there. A need has no root, no logarithm, no power, no least, no greatest, no absolute value and no pi. It reads no load, no row, no `case` and no key. A quotient divides by a field or by a constant, and by no other expression: a quantity of a part is more than zero ([format.md](format.md), Parts 3), so a quotient by a field never divides by zero and needs no other need to say so. A field that says `may_be` may be zero, so a need that divides by one is refused when the deck is read. Such a field may stand anywhere else in a need: in a sum, in a product, and above the line of a quotient. A need names at least one field, and it names each field once, over both sides: `2 a <= b` is written `["mul", "2", "a"]`, and not `["add", "a", "a"]`. A deck with a need that breaks any of this does not load.

A need is asked of every part of the type, and it must hold for every value the card and the design allow. A field that the design writes is one number. A field that the card bounds is a range. The kernel works out the range of each side from the ranges of its fields with the four operations on their ends, in exact fractions: the ends of a sum are the sums of the ends, the ends of a product are the least and the greatest of the four products of the ends, the negative turns the two ends round, and a quotient is a product by the two ends of the divisor turned over. Because a side reads each field once, that is the range of the side and no wider. The need holds when the most the first side reaches is at most the least the second reaches, or under it for `lt`. So the answer is exact: there is no rounding, no search and no hint, and no cell.

A part that breaks a need makes the design ILL-FORMED, as a missing field does. The finding names the part, the need by its number from 1 and its type, the two values in SI units, and the `why`:

```
e: breaks need 1 of a eye: its left side, 23/1000, is not under its right side, 11/500, in SI units: a pin passes through its hole
```

For `le` it says `is not at most`. Where a side has a range, the finding gives the most of the left side as `up to 21/1000` and the least of the right as `down to 7/200`. The kernel cuts a finding at 200 bytes, so a long `why` loses its end. The needs are asked last, of a design that breaks no other rule of its files, so each field is there and each quantity is within its floor when a need reads it.

A need reads nothing in the sense of the `unread` cells. A field that only a need names is still a field that no rule checks, and has its open cell.

### The grid

```json
{"type": "lap", "mechanism": "lap.spacing", "what": "minimum spacing of the holes",
 "anchor": {"standard": "AISC 360-22", "clause": "J3.4"}}
```

A line of the grid names one mechanism that every part of a type answers for, and the clause that raises it. The type is one of the deck's. A line has `type`, `mechanism`, `anchor` and `what`, a text, which may be empty. No mechanism is named `unread`: that is the name of the cells for the fields that nothing reads, and a line of that name is refused. The grid is written from the standard's own list of sections, and a line is there whether or not the deck has a rule for it. A line with no rule leaves its cell open, so a design cannot pass until the deck gets the rule or the card waives the mechanism.

A line may say that the mechanism cannot arise, and why:

```json
"unless": {"why": "a lap is a bearing-type joint, which claims no slip resistance"}
"unless": {"when": ["is", "fit", "close"], "why": "a close fit leaves no room for one"}
```

With no `when`, it never arises for the type. A condition is `["is", FIELD, NAME]`, or `and`, `or` and `not` of these. An `unless` has `why`, a text, which may be empty. An `unless` with no `why` is refused. A line whose `unless` is `null` is read as a line with none.

An `is` holds when a key has the name `NAME`, which is one of the key's names. `FIELD` says which key, in one of two ways.

- A key field of the type itself: `["is", "fit", "close"]`.
- `PART.FIELD`, a key field of a part the type joins. `PART` is the name that the `as` of the joining field gives the part, as an expression of a rule reads `a.Fy`. With `"as": ["top", "bottom"]`, `["is", "top.stiffened", "yes"]` holds for a beam whose part `top` is stiffened.

Each name of `as` is one part, so a condition is about one part. A field with no `as` joins one part, under the field's own name. A field whose `as` gives several names is no part's name: with `lugs` joining `top` and `bottom`, `["is", "lugs.stiffened", "yes"]` could hold for one lug and not for the other, so it has no meaning and the deck is refused. A condition that is to hold for both says so: `["and", ["is", "top.stiffened", "yes"], ["is", "bottom.stiffened", "yes"]]`. A name reaches one part and no further: `top.pin.finish` is refused. A field named as a joined part is, as `top` beside the part `top`, is still that field: `top` alone is the type's own key, and `top.stiffened` the key of the part.

A line and a rule are for one part of their type, and each is asked once of that part. Nothing is asked once for each part it joins: a rule that is to answer for each of two lugs is two rules, as the first deck has one for each plate.

A condition is over keys and asks about no load. The keys of a part are the same under every load case of the card, so a condition holds for a part or it does not, and no case can switch a line or a rule off for another case. The condition `["loaded", LOAD]`, which held when some case put the load on the part, is gone, and a deck that writes `loaded` in a `when`, an `unless` or a `requires` is refused, alone or inside `and`, `or` and `not`, whatever follows the word. It did exactly that switching: a rule that reads a load has a cell for each load case, and a case that put a load of zero on a joint made a line not applicable under the case that broke it. A deck that means "where the part carries tension" reads the tension in its rule, and the card states the tension in every case, as zero where there is none.

### A rule

A rule answers one line of the grid with an inequality.

```json
{"id": "aisc360-22/lap-ply-yield-a", "type": "lap", "mechanism": "lap.ply_yield",
 "anchor": {"standard": "AISC 360-22", "clause": "J4.1(a)", "equation": "J4-1"},
 "says": "the pull is at most 0.90 of the yield strength of the gross section of plate a, its width times its thickness",
 "le": [["load", "pull"],
        ["mul", "0.90", ["row", "aisc360-22/J4-1", {"Fy": "a.Fy", "Ag": ["mul", "a.width", "a.thickness"]}]]]}
```

| Key | Holds |
|---|---|
| `id`, `type`, `mechanism` | The rule's name, and the line of the grid it answers. A cell is entered under the id from after its last `/`, so two rules for one type and one mechanism have ids that differ there: `a/x` and `b/x` together are refused. |
| `anchor` | The clause the inequality comes from |
| `says` | The inequality in words: a text that is not empty. A rule with no `says` is refused. |
| `le` | Two expressions. The rule holds when the first is at most the second. A rule that states no inequality has `requires` in its place ([A rule that requires](#a-rule-that-requires)). |
| `lt` | In place of `le`: two expressions, and the rule holds when the first is under the second ([A rule that states lt](#a-rule-that-states-lt)). A rule has one of `le`, `lt` and `requires`. |
| `let` | Names for expressions the rule uses more than once. A name is letters, digits and `_`, and is no field's name. An expression reads the names before it. |
| `where` | The range the rule holds in: a list of `{"le": [a, b], "why": "..."}` with at least one item. Each item has `why`, a text, which may be empty. A rule that holds everywhere leaves `where` out: `"where": []` is refused. |
| `when` | A condition on the part, as in the grid: on its own keys and on the keys of the parts it joins. The rule answers only for the parts it holds for. |

An expression is written as a row's is. A name in it is a quantity field of the part, `NAME.FIELD` for a part it joins, or a name from `let`. It has two more forms.

| Written | Means |
|---|---|
| `["load", NAME]` | A load the card puts on the part. It is a load of the rule's own type: a rule reads no load of a part its part joins. |
| `["row", ID, {INPUT: ...}]` | A row of the deck that gives a quantity, with each of its inputs bound |
| `["case", ["row", ID, {INPUT: ...}], {NAME: ...}]` | The expression of the name that a row gives |

A quantity that a row takes is bound to an expression of its dimension. A key that a row takes is bound in one of four ways.

- To a key field whose names are all names of the row's key.
- To `["key", NAME]`, one name of the row's key.
- To `["by", FIELD, {NAME OF THE FIELD: NAME OF THE ROW'S KEY}]`. The map of a `by` has one entry for each name of the field and no other entry, and each of its values is a name of the row's key. A map that leaves a name of the field out is refused.
- To `["row", ID, {INPUT: ...}]`, where the row `ID` gives a name ([A table that gives a name](#a-table-that-gives-a-name)) and each quantity it takes is bound to an expression of its dimension. The key then has the name that row gives for the part's sizes. Every name of that row's `one_of` is a name of the key, or the deck is refused. A `by` takes a field and no row, so the names are not mapped: the row that gives the name writes the names of the key it feeds.

```json
["row", "example/allowed", {"category": ["row", "example/category", {"a": "length", "t": "thickness"}], "service": "service"}]
```

A key bound this way is still a key of the table it is bound in. The name comes from the row and from nothing else: a key field of the part with the same names, or a name of the part's own, has no say in it.

A `case` picks an expression by a name that a row gives. Its first item is `["row", ID, {INPUT: ...}]` with a row that gives a name, and its second has an expression for each name of that row's `one_of` and for no other name, all of one dimension. Its value is the expression of the name the row gives. It is how a formula that changes with a category is written. A `case` is read in a rule and in no row. Each name of the row is held by a cell of it ([A table that gives a name](#a-table-that-gives-a-name)), so each expression of a `case` is the value for some sizes, and a rule reads what every one of them names.

```json
["case", ["row", "example/category", {"a": "length", "t": "thickness"}],
 {"B": "1", "C": ["div", "length", ["q", "50", "mm"]], "D": "3", "E": ["row", "example/reduction", {"x": "length"}]}]
```

Where the row gives no name, the table read at it and the `case` have no value, and the rule's cell is open. A `case` writes every one of its expressions for the part: if one of them has no value that can be written for the part, as a table with no line for the part's key, the cell is open whatever name the row gives.

A formula whose case goes by the size of one of its own inputs needs none of this: it is an equation with `cases`, and its conditions are the bands.

A factor that the clause fixes for the inequality, such as a resistance factor, is a number in the rule.

Reading a deck checks every rule. Each input of each row is bound once and to its dimension. Both sides of `le` or of `lt` have one dimension. The rule answers a line of the grid that can arise. A deck that fails any of these does not load, and the kernel finds a design checked against it ill formed.

### A rule that states lt

"Less than 55 lb" and "under 250 g" are not "at most". A rule that has `lt` in place of `le` states that its first side is under its second.

```json
{"id": "made-up/under-250", "type": "craft", "mechanism": "craft.under",
 "anchor": {"standard": "a regulation", "clause": "3"},
 "says": "the mass is under 250 g",
 "lt": ["mass", ["q", "250", "g"]]}
```

- A rule has one of `le`, `lt` and `requires`. A rule with two of them, or with none, is refused. A rule with `lt` may have `let`, `where` and `when`, as one with `le`. An item of `where` has `le` and no `lt`.
- The cell is `proved` when the first side is under the second for every value the card and the design allow. A mass of exactly 250 g is not proved under 250 g. A range that reaches 250 g is not either.
- The cell is `refuted` at a point they allow where the first side is not under the second: where it is equal to it or over it. So a mass of exactly 250 g is refuted, and `le` would prove it.
- The cell is `open` where neither is shown. A side with a logarithm, an exponential, a cosine or pi is enclosed and not exact, and so is the square root of a value that is not the square of a fraction. So a value that lies exactly on the limit may be open: its enclosure reaches to both sides.
- The root of a value that is the square of a fraction is that fraction. The diagonal of a box of 3 mm by 4 mm, `["sqrt", ["add", ["mul", "a", "a"], ["mul", "b", "b"]]]`, is 5 mm exactly, so it is refuted under 5 mm. The diagonal of 1 mm by 1 mm is no fraction, and a limit within 2^-96 m of it may be open.
- A side that is under itself is refuted: `"lt": ["span", "span"]` holds for no part.

The kernel decides it with the proof it has for `le` ([format.md](format.md), Cells 6, and [proved.md](proved.md)). The cells, their entries, the load cases, `where` and the hints are those of a rule with `le`. `petra check` prints the same ratio, the most of the first side over the least of the second, and a refuted `lt` may print a ratio of 1.

### A rule that requires

Some clauses ask no inequality. They say what a part must be: a lifter of one category is of one service class, a pinhole is machined. Such a rule has `requires` in place of `le`.

```json
{"id": "made-up/category-a", "type": "hoist", "mechanism": "hoist.category",
 "anchor": {"standard": "a standard", "clause": "2.1(b)"},
 "says": "a hoist of category A is of service class 0",
 "when": ["is", "category", "A"],
 "requires": ["is", "service", "0"]}
```

| Key | Holds |
|---|---|
| `id`, `type`, `mechanism`, `anchor`, `says` | As for any rule |
| `requires` | A condition over keys that must hold: `["is", FIELD, NAME]` on a key of the part or of a part it joins, and `and`, `or` and `not` of these, as a `when` writes them |
| `when` | As for any rule: the parts the rule answers for |

A rule has one of `le`, `lt` and `requires`, and never two of them. A rule with `requires` has no `let` and no `where`, which are for an inequality. Its condition is over keys, as every condition is: a rule requires something of what a part is. A deck that breaks any of these does not load.

For a part that its `when` holds for, the rule gives one cell, entered as any rule's cell is. The cell is `proved` when the condition holds for the part and `refuted` when it does not. It has no tape, it needs no hint and no search, and it takes no work. A refuted cell makes the verdict FAIL as any refuted cell does. Its reason names each key the condition names, in the order it names them and each once, with the name the part has for it: `the part is not what the rule requires: top.bore is machined, bottom.bore is cut`. A reason prints in 200 bytes, so a rule that requires many keys names the ones that fit and counts the rest: `k00 is no, k01 is no and 38 more`.

The rule reads the keys that its `requires` and its `when` name, so those keys have no `unread` cell on a part the rule applies to. It reads no load, so it has one cell whatever load cases the card has.

A requirement must be one that a part can break and a part can meet. `service is 0, or it is not` holds for every part. Its cell would be proved whatever a design is, and its keys would count as read. So reading a deck tries each `requires`. The keys that the rule's `requires` and its `when` name take finitely many combinations of names: the product of how many names each key has, each key once. The reader goes through every combination. The rule answers at a combination when its `when` holds there, and a rule with no `when` answers at all of them. The deck is refused when:

- the rule answers at no combination: its `when` holds for no part;
- what it requires holds at every combination at which the rule answers: no part can break it;
- what it requires holds at none of them: no part can meet it.

The refusal names the rule and says which of the three it is. A requirement that its own `when` already implies is of the second kind, and so is one that lists every name of a key.

The reader tries a rule only while the work is small. The rules with `requires` are taken in the order of the deck. The cost of one is its combinations times the sizes of its `requires` and of its `when`, where the size of a condition is 1 for an `is`, 1 more than the sizes of its members for an `and` and an `or`, and 1 more than its member for a `not`. A rule is tried when its combinations are at most 4,096 and its cost, added to the cost of the rules tried before it, is at most 1,000,000. A rule past either is not tried, and it does not count towards the million. The deck loads with it, and nothing in the reader says whether its requirement is empty: that is left to the acceptance check for a rule, which says so when it cannot try a requirement in full ([The parts of the check](#the-parts-of-the-check)). The reader does not take the `unless` of the rule's line into account. The acceptance check does.

## A design checked against a deck

`petra check` makes one cell for each answer and writes the files of [format.md](format.md): the card, the design with its parts as written, and the deck's own file. A cell has one of five states.

| State | When |
|---|---|
| `proved` | A rule's inequality holds for every value the card and the design allow, or what a rule requires of the keys holds |
| `refuted` | The inequality fails at a point they allow, or what a rule requires does not hold. For `lt` that is a point where the two sides are equal, too. |
| `not applicable` | The grid says the mechanism cannot arise for this part |
| `waived` | The card waives the mechanism on the part, the cell would be open without the waiver, and no inequality could answer it |
| `open` | Anything else |

No cell has a default. The verdict is FAIL with a refuted cell, UNKNOWN with an open cell or with nothing proved, and PASS otherwise. `petra check` says PASS_WAIVED for a PASS with a waived cell, and exits 6 for it, where a PASS exits 0 ([What a waiver rests](#what-a-waiver-rests)).

### What a waiver rests

A waiver rests a cell that would be open and that no inequality of the deck could answer, and no other: the one who signs it answers for what the deck has nothing to say about on that line of that part, and not for what the deck could say, whether it settled it or not.

The card waives a mechanism on a part, and the cells of that line are made as if it had not. Every rule of the line is run.

| Without the waiver the cell is | With it the cell is |
|---|---|
| `proved` | `proved`. The waiver was not needed for it. |
| `refuted` | `refuted`, and the verdict is FAIL. No waiver hides a refutation. |
| `not applicable` | `not applicable` |
| `open`, and no inequality could answer it | `waived` |
| `open`, and the rule's inequality is left undecided | `open`, and the verdict is UNKNOWN |

No inequality could answer a cell when:

- the line has no rule, or none for a part like this one;
- a rule reads a load that a case of the card does not put on the part, or the card has no load case;
- a table or an equation of a row that the rule reads gives nothing for the part: the tape cannot be written, because a table has no line for the part's key or every cell it could read is empty, or the rule has no value at any point of the ranges, because a row gives nothing at any of them;
- the rule's `where` holds nowhere in the ranges;
- the part leaves unstated a key that the rule or the line's `unless` reads, and no quantity that the rule reads.

Every other open cell stays open under a waiver, and its reason starts `the waiver rests no cell that an inequality could answer: `. Such a cell has a rule whose inequality could be answered. It is neither proved nor refuted at the points tried, its `where` may hold somewhere in the ranges and is not proved, it has no value at some points and not at all of them, as a quotient by a range that holds zero has none, or the part leaves a quantity unstated that it reads. A better search, a narrower range or a stated value may settle it, and a waiver does not stand in for them: a refutation that the search missed would otherwise pass under the waiver.

"No value at any point of the ranges" is decided over the whole box at once. A node has no value anywhere when it reads one that has none anywhere. A row's table or equation is a pick, and it has no value anywhere when, for every order of what it compares that the enclosures leave possible, no case holds or the case that holds has no value anywhere. A bolt of a size that a table does not list, written as one size, is such a cell: every point of the ranges reads the table at that size. A width that the card gives as a range from a listed size to one that is not listed is not: the table has a value at the listed size, and the rule could be refuted there.

A waived cell keeps the entry it had. So a line with three rules of which two prove and one reads a table that gives nothing for the part is two `proved` cells and one `waived` cell, and a line with no rule is one `waived` cell with an empty entry. The reason of a waived cell says what was open: it is `open but for the waiver: ` and then the reason the open cell had, as in `open but for the waiver: the deck has no rule for it`.

So a card cannot switch a rule off. A card written when a deck had no rule for a line, which waived the line, does not hide the rule the deck has since gained: the rule is run, and a design that fails it fails. A design that failed a rule under a waiver was never safe by that rule, and now the verdict says so.

A waiver that rests no cell is no fault. Every cell of its line was proved, refuted or not applicable, and the card allowed more than the design needed. The verdict lists, under `waived`, each waiver that some cell rests on, with who signed it and why, and it does not list one that rests none.

When every open cell is waived, no cell is open. `waived` stays a state of its own: a waived cell is counted as waived and never as proved. The verdict is then PASS when no cell is refuted and at least one cell is proved, and UNKNOWN when none is proved: a design all of whose lines are waived has nothing proved, and is not passed. A cell entered `RULE/where` proves that the rule's range holds for the part, and not the rule, so it does not count: a design whose only proved cell is the range of a waived rule has nothing proved either.

A PASS with a waived cell is not the PASS of a design the deck checked in full: the design passes what the deck could check, and each signer answers for the cells their waiver rests. `petra check` gives it a word of its own, PASS_WAIVED, in its first line, in the `status` of its JSON and in the reply of the MCP tool, and exits 6 where a PASS exits 0. A caller that tests for exit 0 does not take it for a full pass. Its text has a `waived` line that counts the cells and the waivers, and one line for each waiver with who signed it and why, and `petra check --json` lists the same waivers under `waived`. The kernel has no such word: it says PASS, and its own `waived` list names the same waivers in the same order.

A rule reads what it reads whether or not its line is waived or can arise: the fields and the loads of a rule of a line that cannot arise have no `unread` cell, though that rule is not run.

The kernel does not search: a cell is open when no hint of proofs.json settles it. `petra check` looks for a point that refutes each cell, and a point it finds is checked by the kernel and stands. It tries the corners of the ranges while no more than six inputs have a range. Past six it tries one corner, the one the rule climbs to: from the middle of the ranges it sets each input in turn to the end of its range where the rule is further from holding, and goes round again until a round moves none. Then it tries the middle of the ranges. Where none of these refutes the rule and it looks for a proof by halving the ranges, it tries the middle of each part it cannot prove, and stops at the first that refutes the rule. A refutation that the search does not find leaves the cell open and the design UNKNOWN, waiver or not.

While a waiver rested such a cell, six designs that a rule refutes passed under one, each where the search missed the point: past six ranged inputs, inside the ranges away from their corners, inside a `where`, at an equality that `lt` refutes, at a quotient by zero, and at an unstated quantity (`tests/test_kernel_attacks7.py`). What a waiver rests now is what the deck has nothing to say about, which no search could change. The search now finds the first three, the corner past six ranged inputs, the point inside the ranges and the point inside the `where`, and the three designs FAIL. The fourth FAILs too: its side is the root of 3² + 4², which is now 5 exactly, as the root of the square of any fraction is ([format.md](format.md), "Tapes"). The deck of the quotient by zero, whose rule divided by a count that may be zero, is now refused when it is read ([A quantity at or under zero](#a-quantity-at-or-under-zero)).

`petra-verify` reads the same three files and makes the cells again, each with the tape of its rule. It takes nothing of a cell from `petra check` but a hint: the partition that proved it, or the point that refuted it. The kernel tries the hint on its own tape, and the state it settles on is its own. `petra check` then compares the two lists cell by cell, and stops with exit code 4 if they differ.

These cases are open. The first four a waiver rests where they hold for every point of the ranges, and the rest it does not ([What a waiver rests](#what-a-waiver-rests)).

- The grid has a line and the deck has no rule for it, or none that holds for this part.
- A rule reads a load, and a load case of the card does not put it on the part. No load is taken as zero: a card that means none in a case states a load of zero there.
- A table has no value where the rule reads it: between the listed values of a table read at listed values, outside every band, or in an empty cell.
- A rule, or the `unless` of a line, reads a key that the part leaves unstated ([A field that a record may leave unstated](#a-field-that-a-record-may-leave-unstated)).
- A rule's `where` is not proved, and no point inside its range that the search tried fails the rule. Outside its range a rule says nothing, so its cell is never refuted there. A point inside it where the rule fails refutes the cell, as any refuting point does, and the kernel checks that the point is inside. A waiver rests the cell when the `where` holds nowhere in the ranges.
- A rule reads a quantity that the part leaves unstated.
- The inequality is neither proved over the ranges the card gives nor refuted at a point of them that the search tried.
- No rule and no line of the grid reads a quantity or a key of a part. A value nothing reads is a value nothing checks, so a plate that no lap joins has an open cell for each of its fields, named `unread`.
- No rule reads a load that the card puts on a part. A rule reads a load in an expression: a side of its `le` or of its `where`, or a name of `let` that one of them reads. The load has an open cell named `unread` for each load case that puts it on the part, entered as `LOAD/CASE`.

The cells named `unread` come after every other cell, part by part: a part's fields in the order of its type's fields, and then its loads in the order of their names and of their cases' names.

A rule that reads a load has a cell for each load case of the card, entered as `RULE/CASE`. The load cases of the card are every `load` block it has, whether the block puts a load on this part, on another, or on none. Under a case that puts every load the rule reads on the part, the cell is proved, refuted or open as the inequality is. Under a case that leaves one of them out, the cell is open and names the case and the load. So a card with a case `wind` that puts a shear on a joint and no tension leaves every rule that reads the tension open under `wind`, until the card states the tension there, as zero if that is what it means. A card with no `load` block leaves one open cell for the rule. A rule with `where` has one more cell for each case, named with `/where`, that proves its range.

A quantity on the end of a band reads the band that holds that end, exactly. Over a range that reaches into two bands or two cases, the inequality must hold in both.

```bash
petra check examples/deck/lap_unknown.petra
```

```
lap-splice: UNKNOWN
rules      sha256:d959367e...  aisc360-22
card       sha256:b0372d69...  examples/deck/lap_unknown.card
design     sha256:3fd22401...  examples/deck/lap_unknown.petra
kernel     petra-verify checked 12 of 12 proofs and gives the same verdict
path       rules: the kernel worked out every cell from the rules deck
cells      12 proved, 0 refuted, 4 not applicable, 0 waived, 4 open
  splice/lap.tightening          open                    the deck has no rule for it (AISC 360-22 J3.2)
  splice/lap.spacing             proved           0.667  lap-spacing-centres (AISC 360-22 J3.4)
  splice/lap.spacing             proved           0.343  lap-spacing-clear (AISC 360-22 J3.4, Table J3.3)
  splice/lap.end_distance        proved           0.667  lap-end-distance-standard (AISC 360-22 J3.5, Table J3.4)
  splice/lap.slip                not applicable          a lap is a bearing-type joint, which claims no slip resistance (AISC 360-22 J3.9)
  splice/lap.ply_yield           proved           0.617  lap-ply-yield-a/gravity (AISC 360-22 J4.1(a), equation J4-1)
  ...
```

The `rules` line is the hash of the deck's file, which the kernel prints as `hashes.rules`. A verdict is "checked against this deck" only when that hash is the one the reader trusts ([format.md](format.md), "Reading a verdict"). The number on a proved or refuted line is the most the left side of the rule reaches over the least the right side does. `examples/deck` has the same lap passing, with a card that waives the four open mechanisms, and failing under a larger pull.

## The acceptance check for a rule

A rule passes an acceptance check before it enters a deck, as a row does. The check reads three things.

| | Holds |
|---|---|
| A task | The types, the rows a rule may use, and the mechanisms to answer. Every transcriber gets the same task. |
| A transcription | The rules one transcriber wrote for the task, and the mechanisms it says cannot arise |
| Worked examples | For a mechanism: a part, and a number that a published source prints for it |

### A task

A task is a JSON file. `bench/formalizer/rules_task.json` is the task of the first run: the rules of a lap.

| Key | Holds |
|---|---|
| `format` | `"petra-rule-task/0"` |
| `name`, `about` | The task's name, and what it covers |
| `rows`, or `rows_from` | The rows, or where they are: the path of a deck or of a file of rows, from the task's folder, or a list of such paths |
| `types` | The types, as a deck holds them, with the three keys below |
| `asks` | The lines of the grid to answer, each with no `unless` |

The types are given, and not left to the transcriber, because two transcribers must mean the same part by `a.thickness`. A task adds three keys to a type.

```json
{"name": "pitch", "dim": "length", "what": "...", "range": ["1 inch", "6 inch"]}
{"name": "pull", "dim": "force", "least": "0 kip", "what": "...", "range": ["1 kip", "1000 kip"], "adverse": true}
"alike": [["a", "b"]]
```

| Key | On | Means |
|---|---|---|
| `range` | Each quantity and each load | Two values between which a real part's value falls. The check samples parts from the ranges. A range is not a limit of the standard. |
| `adverse` | A load | More of it never helps: no part fails under less of it and holds under more |
| `alike` | A type | Joined parts, by their names in `as`, that may change places and leave the part what it was |

The ranges must be wide enough for each rule to hold for one part and fail for another.

A range holds values that a part may have, so it follows its field. It starts above zero for a size. It may start at zero for a field that says `"may_be": "zero"`, and under zero for a field or a load that says `"may_be": "negative"`, down to its `least` and never under absolute zero. A load that says nothing starts at zero or above. The check then tries parts at and under zero, and on the ends of a band that lies there. It moves a load or a size far past its range to see an answer turn: to 64 times the top and a 64th of the bottom. An end under zero is divided where the other is multiplied, so "more" of a load whose top is -5 degC is -0.078 degC.

### A transcription

```json
{"rules": [],
 "unless": [{"mechanism": "lap.slip", "why": "a lap is a bearing-type joint, which claims no slip resistance"}],
 "left_out": [{"mechanism": "lap.spacing", "why": "the task's rows hold no row of Section J3.4"}]}
```

| Key | Holds |
|---|---|
| `rules` | The rules, each as a deck holds a rule |
| `unless` | Each mechanism that cannot arise: `mechanism`, `why`, and `when` if it cannot arise for some parts only |
| `left_out` | Each mechanism the transcriber did not answer, or answered in part, and why |

Any other key is the transcriber's note. A deck's own file is read as a transcription too: its rules, and the `unless` of its grid.

### A worked example of a mechanism

The numbers here are made up.

```json
{"examples": {"lap.ply_yield": [
  {"anchor": "a design guide, Example 3, p. 41",
   "given": {"a.thickness": "3/8 inch", "a.width": "6 inch", "a.Fy": "36 ksi",
             "b.thickness": "1/2 inch", "b.width": "6 inch", "b.Fy": "36 ksi"},
   "loads": {"pull": "45 kip"},
   "side": "right", "gives": "72.9 kip"}
]}}
```

`given` holds each field the source states, by the name a rule reads it under, and `loads` each load. `side` says which number the source prints: `left` or `right` for one side of the inequality, or `ratio` for the left side over the right. The check compares it with the rule that has the largest ratio for the part, which is the rule that governs. So an example does not depend on how a transcriber split a mechanism into rules: the one above is reproduced by a rule for each plate and by one rule with the lesser of the two. The bound is a row example's: 0.5%, or half a unit of the last printed digit, or `within`.

An example gives what its source states and no more. A rule that reads a field the example does not give does not reproduce it. A load is the exception. Where the source prints a strength and no load, the side is worked out under two loads, and it is reproduced if it is the same under both.

### What a transcription says of a part

The check tries parts as points: each key a name, each quantity and each load one value. For one part, a transcription gives a mechanism one of four answers. They are what a deck makes of a cell for a part with no ranges: not applicable, refuted, open and proved.

| Answer | When |
|---|---|
| `cannot arise` | The mechanism's `unless` holds for the part |
| `fails` | A rule whose `when` holds for the part fails |
| `open` | No rule's `when` holds for the part. Or none fails and one says nothing: the part is outside its `where`, a row gives no value there, or the part carries no load the rule reads. |
| `holds` | Every rule whose `when` holds for the part holds |

An answer that holds or fails has a ratio: the largest, over its rules, of the left side over the right. It is the number `petra check` prints on a line.

For each mechanism the check tries 96 parts. They take every combination of the type's keys in turn, and each carries every load of its type. A quantity is spread over its range on a log scale, and a count over its whole numbers. A quantity that a rule binds straight to the side of a table sits on the values the table lists, and on and beside the ends of its bands. The first 32 parts each have a partner: the same part with other sizes and loads. Where a transcription treats a part and its partner differently, by another case of a row, another band of a table or the other side of a range, the check halves the way between them 24 times and tries the part on each side of the change.

### The parts of the check

| Part | Passes when | Is `none` when |
|---|---|---|
| `units` | The rules load as a deck's rules do: each input of each row bound once and to its dimension, both sides of one dimension, a line of the grid that can arise | never |
| `examples` | The rules reproduce every worked example given for the mechanism | no example is given |
| `reach` | Every rule answers a sampled part and fails at one, the mechanism holds at one, every `where` fails at one, and every argument of a `min` or a `max` decides an answer at one | a rule fails at no part, a `where` fails at no part, or an argument decides at none. The detail says which. |
| `direction` | More of an adverse load turns no failing part into a holding one. Two sides that changed places do that. | the rules read no adverse load |
| `alike` | The answer and the ratio stay when two alike parts change places. A rule that reads one plate's thickness with the other plate's strength does not pass. | the rules read no alike parts |
| `second` | A second transcription, made without sight of the first, gives every part tried the same answer | no second transcription is given, or it leaves the mechanism out |

`reach` fails when a rule answers no sampled part, or the mechanism fails at every part it answers. A rule that no part in the task's ranges can meet is wrong, or the ranges are.

A rule with `requires` is not sampled for `reach`. It is tried at every combination of the names of the keys that its `requires`, its `when` and the `unless` of its line name. It answers at a combination when its `when` holds there and the `unless` does not. `reach` fails when the rule answers at no combination, when what it requires holds at every combination at which it answers, and when it holds at none: such a rule says nothing of a part. The detail says which, with the counts. Wider ranges cannot change a key, so the detail gives no advice to widen them. Where the keys take more than 4,096 combinations the rule is not tried, `reach` is `none`, and the detail says that what the rule requires was not tried in full. The mechanism is then admitted on what else stands behind it, and the line of its check says what does not.

A mechanism is admitted when no part of its check fails. A part that is `none` says the mechanism has less behind it. One more line is about the transcription as a whole: `reads` passes when a rule or an `unless` reads every key, every quantity and every load of the types. `petra check` leaves a design open at a field nothing reads.

```bash
python -m petra.rule task.json rules.json --second other_rules.json --examples examples.json
```

The command prints each mechanism as admitted, refused or left out, with the parts of its check. It exits 0 when no mechanism is refused and `reads` passes, 1 otherwise, and 3 when a file does not hold what it should.

### What two transcriptions must agree on

Two transcriptions mean the same when they give every part the same answer. The verdict of a design rests on the states of its cells and on nothing else of a rule. So two transcriptions that give every part the same answer give every design the same verdict, however each is written. The check compares answers, and never the text of two rules.

| The two differ in | Counts as |
|---|---|
| The names in `let`, the order of a sum or a product, the words of `says`, the ids | the same |
| One rule for each of two plates, against one rule with a `min` over the plates | the same. The mechanism fails when either rule fails, and the larger ratio of the two rules is the ratio of the one. |
| Both sides times one factor above zero, as a force against a stress | the same. The ratio does not change. |
| `a <= b` against `a - b <= 0` | the same answer. The detail says the two are in different forms. |
| What leaves a part open: no `when` that holds in one, a `where` or a table with no value in the other | the same. The cell is open in both. |
| A `where` in one and none in the other | different. Outside the range one is open and the other answers. |
| A safe shortcut, as the count times the weakest bolt for the sum over the bolts | different. Some part fails by one and holds by the other. |
| A rule for a kind of part the other has no rule for | different |
| An `unless` in one and a rule in the other | different |

The check cannot try every part, so at each part where both hold or both fail it compares the ratios too. Equal ratios say more than equal answers: the two inequalities are then as near to turning at that part, and not only on the same side of it. A factor that one transcriber got wrong changes the ratio at every part, and the answer at few.

Where the ratios differ, the two may still be one inequality in two forms. From each of the first 32 such parts the check moves one load, or failing that one size, until either answer turns, and tries the part on each side of the turn. One inequality in two forms turns at the same place. The two are refused when fewer than half of these parts have such a place: nothing then tells them apart, and nothing tells them the same.

When `second` fails, its detail says how many parts get another answer, what the two differ on, and one part with what each says of it. This is the rule the first deck once had for the bolts, against a transcription with no `where`:

```
the two give another answer at 18 of 132 parts, 18 on the range a rule holds in. At fastener=Group 144, threads=excluded,
holes=standard, diameter=0.0127, count=12, pitch=0.10932, end=0.014041, a.thickness=0.03101, a.Fu=4.8251e+08,
b.thickness=0.0065213, b.Fu=4.5298e+08, pull=887640 (SI) this one says nothing (aisc360-22/lap-strength: outside its range:
the line of bolts is at most 38 inch long ...) and the other fails at 1.47451 (aisc360-22/lap-bolts: 887640 against 601991)
```

### The first run

`python bench/formalizer/rules.py` runs the check on the first deck as it shipped until 2026-11-11. `bench/formalizer/rules_a.json` keeps that file: 18 rows, a grid of 15 lines for a lap, and four rules that were written by hand. The task is the lap of that deck. The first transcription is those four rules. The second is `bench/formalizer/rules_b.json`. It answers the three mechanisms that deck had rules for, says the same four cannot arise, and leaves out the same eight.

The two agree at every part tried: 128 parts for each mechanism, and 136 for the strength of the bolts. One writes a rule for the yielding of each plate, and the other one rule with the lesser of the two.

That says less than two transcriptions from the page would. The second was written by a language model from its memory of AISC 360-22 and from the rows' own descriptions, with no copy of the standard. Its writer had read this page, which then showed one of the four rules and named the rows that two others read, and had read the deck's grid, with its four `unless`. Nothing in the run tells whether the two share one wrong reading of a clause. The run has no worked example. The deck no longer has any of the four rules.

The run then damages each rule, one change at a time, and counts the damaged rules that the check refuses with no second transcription. A damaged rule that gives every part tried the answer the rule gives is not a wrong rule, and is left out.

| Damage | Wrong rules | Refused | By `alike` alone | By another part |
|---|---|---|---|---|
| A field of the other joined part | 22 | 22 | 18 | 4 |
| The wrong one of two fields of one dimension, as `Fy` for `Fu` | 44 | 34 | 26 | 8 |
| A number a tenth off, or a power one off | 15 | 5 | 4 | 1 |
| A `min` for a `max` | 7 | 6 | 6 | 0 |
| An argument of a sum, a product, a `min` or a `max` left out | 36 | 30 | 20 | 10 |
| A `where` left out | 1 | 0 | 0 | 0 |
| A key bound to another column of a table | 5 | 0 | 0 | 0 |
| The row of another equation with the same kinds of input | 15 | 12 | 12 | 0 |
| A `when` turned into its opposite | 1 | 0 | 0 | 0 |
| The two sides of an inequality or of a range changed places | 5 | 3 | 0 | 3 |
| A difference or a quotient turned round | 6 | 3 | 0 | 3 |
| All | 157 | 115 | 86 | 29 |

The check refused 115 of 157 wrong rules, 73%. `alike` alone refused 86 of them. A lap joins two like plates, so its rules write each term twice, and one change damages one of the two. A transcriber who errs the same way for both plates is not seen by `alike`. The last column is then the fairer measure: 29 of 157, or 18%. A lap takes one load, so no rule was damaged by the load of another kind.

A number a tenth off, a key bound to another column, a range left out and a `when` turned round pass almost every time. A worked example or a second transcription is what catches those. On the deck made up for the tests, with one or two made-up examples for each rule, the check with no second transcription refused 43 of 49 wrong rules. With no example it refused 21.

### The second run

The rules the first deck ships come from the second run. Two transcribers each wrote the rules for every line of a lap's grid from the pages of AISC 360-22. They were two different models, and neither saw the other's rules or the rules the deck then shipped. A third agent collected eight worked examples from the AISC Design Examples v16.0 without seeing any rule. `bench/formalizer/rules2.md` describes the run. `rules2_a.json` and `rules2_b.json` are the two transcriptions as handed in, and `rules2_examples.json` the examples.

The two give every part tried the same answer on seven lines: the least spacing, the end and side distances, the strength of the bolts and their holes, and the yielding, rupture and block shear of each plate. Both say the same four lines cannot arise, and both leave out tightening and bending of the plates. On the use of a hole type, one says it cannot arise for standard holes and the other says nothing, and neither wrote a rule: Section J3.3 bars oversize holes from a bearing-type joint, which is no inequality between quantities. The deck keeps that line with no rule.

They differed on Section J3.6, which the task asked as one line. The section limits two things. For the greatest spacing the two wrote the same inequality. For the greatest edge distance the section reads each plate's own distance and thickness, and the lap states only the least distance over both plates. One transcriber wrote a rule from that least distance, and the other refused to and said why. So the deck asks Section J3.6 on two lines. `lap.spread` is the greatest spacing and has the rules both wrote. `lap.max_edge_distance` has no rule until a lap has a field for it.

The deck's 15 rules are the first transcription's, unedited. The 14 rows they read that the deck lacked are from the third run of rows, where two transcribers agreed on every value. `tests/test_deck_rules.py` holds the deck to those files, so a rule or a row edited in one place alone fails a test. It also runs the check on the deck itself, with the second transcription less its two rules for the edge distance.

| Line | Parts tried | Both hold or fail at | Worked examples reproduced |
|---|---|---|---|
| `lap.spacing` | 132 | 125 | 1 |
| `lap.end_distance` | 128 | 103 | 2 |
| `lap.side_distance` | 128 | 106 | none found |
| `lap.spread` | 128 | 128 | none found |
| `lap.strength` | 140 | 125 | 2 |
| `lap.ply_yield` | 128 | 128 | 1 |
| `lap.ply_rupture` | 128 | 116 | 1 |
| `lap.block_shear` | 128 | 116 | 1 |

The two agree at every part on each of the eight lines, with the same ratio wherever both hold or fail.

The run says less than that table may seem to.

- All eight examples use a 3/4 inch Group 120 bolt with threads included, in 50 ksi steel. None tells another size, group or grade apart.
- The source works no lap of two plates whole. Each example is a part of another connection: one line of bolts, or one plate. The three for a plate give that plate's fields alone, so each is held against the rule for one plate.
- No example was found for the side distance or the greatest spacing. Those rules rest on two transcribers agreeing.
- Each transcriber had seen one rule of the first run on this page, and a sample report that named two more by their equations.
- The types and the grid were given to both, so nothing here checks them.

### What the check for a rule cannot see

- An error that both transcribers make, and a shortcut that both choose. Two who read a clause the same wrong way agree.
- Whether the second transcription was made without sight of the first, and from the standard.
- A difference that no tried part shows. The check tries 96 parts and their partners. It sits a quantity on the ends of a table's bands only where a rule binds a field straight to the table. Where the input of a band or of a case is an expression, it tries a part on each side of the end, and not the part on the end.
- Whether the task is right. The types, their ranges, `adverse`, `alike` and the lines of the grid are given, and nothing checks them. A field that a clause needs and the type lacks is not found by the check: the lap of the first run had no distance from its holes to a side edge. A transcriber may find it. In the second run one refused to write the greatest edge distance from a field that was the wrong one for the clause.
- Whether a mechanism that both say cannot arise can arise. The check compares the two `unless`, and not their reasons.
- The words of a rule. `says` and `anchor` are not compared, so a rule may say one thing and state another.
- The ratio of a rule in another form. `a - b <= 0` gives the answers of `a <= b`, and `petra check` prints no ratio for it.
- Whether a rule can be proved. The check tries points. `petra check` proves a rule over ranges, and may leave a cell open that holds at every point of them.
- A part that leaves a field unstated. Every part the check tries states each of its fields. Say one transcription reads an optional field and the other does not. The first is open for a part that leaves the field unstated, and the second is not. The check tells the two apart only where the field's value changes an answer.

## What the first deck covers

`petra/decks/aisc360.json` checks one kind of joint: a `lap`, which is one line of two or more bolts in single shear through two plates, in a bearing-type joint that is pulled along the line. The holes are standard or oversize. The rules use LRFD. The grid has 16 lines for a lap.

| Line | Section | What answers it |
|---|---|---|
| `lap.tightening` | J3.2 | No rule |
| `lap.hole_use` | J3.3 | No rule |
| `lap.spacing` | J3.4 | 2 rules: 2 2/3 diameters between centres, and one diameter clear between holes |
| `lap.end_distance` | J3.5 | 2 rules: Table J3.4 for standard holes, and with the increment of Table J3.5 for oversize ones |
| `lap.side_distance` | J3.5 | 2 rules, as for the end distance |
| `lap.spread` | J3.6 | 2 rules for the greatest spacing: 24 thicknesses of the thinner plate and 12 inch where the plates are painted or protected, 14 and 7 inch for unpainted weathering steel |
| `lap.max_edge_distance` | J3.6 | No rule |
| `lap.strength` | J3.7, J3.11 | 1 rule: the sum over the bolts of the least of a bolt's shear strength and the bearing and tearout strengths at its two holes. Note c of Table J3.2 takes the shear stress at 83.3% for a line over 38 inch. |
| `lap.tension_with_shear` | J3.8 | Cannot arise: the pull shears the bolts |
| `lap.slip` | J3.9 | Cannot arise: the joint is bearing-type |
| `lap.ply_yield` | J4.1 | 2 rules, one for each plate |
| `lap.ply_rupture` | J4.1 | 2 rules, one for each plate: the net section less one hole, taken 1/16 inch wider (B4.3b), with a shear lag factor of 1 |
| `lap.ply_shear` | J4.2 | Cannot arise: the plates are pulled |
| `lap.block_shear` | J4.3 | 2 rules, one for each plate: shear along the line of holes from the end of the plate, and tension across to the side edge |
| `lap.ply_compression` | J4.4 | Cannot arise: the load is a pull |
| `lap.ply_flexure` | J4.5 | No rule |

So 8 lines have rules, 4 cannot arise, and 4 have no rule. A line with no rule is open on every lap, and a lap passes only when its card waives each of the four.

| Line with no rule | Why |
|---|---|
| `lap.tightening` | Section J3.2 asks for pretensioned bolts by what the joint is for, which is no comparison of quantities |
| `lap.hole_use` | Section J3.3 bars oversize holes from a bearing-type joint, which a lap is. That is a ban on a kind of hole and no inequality, and no transcriber wrote it. So the deck does not refuse a lap with oversize holes. It leaves the line open. |
| `lap.max_edge_distance` | Section J3.6 limits the distance from each hole to the nearest edge of each plate by that plate's thickness. A lap states `side`, the least distance over both plates, and has no field for each plate's own. |
| `lap.ply_flexure` | Section J4.5 gives no equation, and a lap takes no load that is a moment |

On the lines that have rules, the deck leaves three things out on purpose. Both transcribers left out the same three.

- **A bolt of 1 1/8 inch or more.** Table J3.3 lists a hole for each bolt to 1 inch and gives a formula for larger ones. A rule cannot choose between a table and a formula by the size of the bolt, so the rules read the table. For a larger bolt the four lines whose rules read the hole are open: the clear spacing, the strength of the bolts and their holes, and the rupture and block shear of each plate. The end and side distances are open over 1 1/4 inch, where Table J3.4 ends the same way. The deck holds the formulas as rows, and no rule reads them.
- **A joint where deformation of the hole at service load is not a design consideration.** Equations J3-6b and J3-6d give such a joint more bearing and tearout strength. A lap has no key that says so, and the strength rule reads J3-6a and J3-6c for every lap, which give less.
- **Note a of Table J3.4**, which permits a lesser edge distance under conditions that are not quantities. The rules hold the table's values, so a lap that leans on the note has a refuted cell and fails. A waiver does not rest it: a waiver rests only a cell that would be open ([What a waiver rests](#what-a-waiver-rests)). Until 2026-11-11 a card could waive the line and pass such a lap. The deck now cannot pass it, though the standard may permit it, and will not until a rule holds the note's conditions or leaves the cell open where they may apply.

A bolt of a size the tables do not list, such as 0.7 inch, has no value in them. Every rule that reads a table at that size is open.

The deck has no rule by ASD, none for slotted holes, and none for more than one line of bolts or more than two plates. Fifteen of its 32 rows are read by no rule.

The first deck states no `needs` ([What a type needs](#what-a-type-needs)), so nothing compares the fields of a lap with one another. A lap may state a `side` of more than half the width of a plate, which no plate can have. It is not refused, and the block shear of each plate is then worked out from that `side`.

## What a deck does not check yet

- Types and grid lines are written once, by hand, and nothing second-transcribes them. A rule has the acceptance check above. The 15 rules of the first deck are one of two transcriptions from the pages that agree at every part tried, and eight worked examples stand behind six of its eight lines with rules ([The second run](#the-second-run)).
- The kernel makes the cells and the tapes from the deck's file, and does not know whether that file is the standard's. It prints the file's hash.
- The kernel does not search. The partition or the point for a cell comes from `petra/grid.py`, so a cell that search does not settle is open, though a better search might prove it.
- A `not applicable` cell is the deck's word. The kernel checks that the line's `unless` holds for the part, and not that the mechanism cannot arise.
- The `range` of a row's input is where the acceptance check samples the row. It is not enforced as the range the row holds in. A rule's `where` is.
- A type with no line in the grid gets no cell of its own. A `plate` has none: the lap that joins it asks about it, and a plate that nothing joins has only its `unread` cells.
- A card's claims, tests, ambient and environment, a family's params, and the repair that `petra check` suggests on a FAIL are not read for a design of a deck's types. A card or a design that states one is refused: `environment marine_c5` in the card of a lap is an input error, `the card or the design states an environment, which a deck does not read yet`, and the kernel finds the pair ill formed.
- The first deck has rules for 8 of the 16 lines of a lap's grid, all by LRFD. Four lines cannot arise for a lap, and four are open: tightening, hole use, the greatest edge distance and flexure of the plates. [What the first deck covers](#what-the-first-deck-covers) says what else it leaves open.
- A cell whose rule could be answered and that nothing settles is open, and the design is UNKNOWN where it would be FAIL. A rule that fails for every value an unstated quantity may take is one: `current ≤ min(limit, rating)` with the rating under the current and the limit unstated. No point is tried for a quantity that has none, and a waiver does not rest the cell ([What a waiver rests](#what-a-waiver-rests)).
