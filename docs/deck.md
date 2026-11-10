# How a rule is written

A deck holds the rules Petra checks a design against. A rule is a row: one equation of a standard, written as data. This page describes a row, the acceptance check that a row passes before it enters a deck, and how to run the check. `petra/deck.py` reads rows and runs the check.

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
| `cases` | The cases, for an equation the standard splits. A row has `is` or `cases`, not both. |
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
| `"2.4"`, `"3/4"` | An exact number. A decimal is the decimal the standard prints. |
| `"pi"` | Pi |
| `"Fu"` | An input of the row |
| `["q", "29000", "ksi"]` | A constant with a unit |
| `["add", a, b, ...]`, `["mul", a, b, ...]` | A sum, a product |
| `["sub", a, b]`, `["div", a, b]` | A difference, a quotient |
| `["neg", a]`, `["abs", a]`, `["sqrt", a]` | The negative, the absolute value, the square root |
| `["min", a, b, ...]`, `["max", a, b, ...]` | The least, the greatest |
| `["pow", a, "2"]`, `["pow", a, "3/2"]` | A power with a fixed exponent |
| `["pow", a, b]` | A power with an exponent that varies. Both must be plain numbers. |
| `["exp", a]`, `["ln", a]` | The exponential and the natural logarithm of a plain number |

The language has no sine, cosine or tangent, no table lookup and no sum over a list. An equation that needs one cannot be written as a row yet. Say so and do not approximate it.

### Cases

An equation that the standard splits is written as cases. Each case has a condition, `when`, and an expression, `is`. The first case whose condition holds gives the value, and the last case may leave `when` out to hold otherwise. Where the standard states one condition two ways, the row uses the way that reads the row's own inputs.

```json
"cases": [
  {"when": ["le", ["div", "L", "r"], "100"], "is": ["mul", "A", "sy"]},
  {"is": ["div", ["mul", "A", "sy", "10000"], ["pow", ["div", "L", "r"], "2"]]}
]
```

A condition is `["le", a, b]`, `["lt", a, b]`, `["ge", a, b]` or `["gt", a, b]` between two expressions of one dimension, or `["and", c, ...]`, `["or", c, ...]` or `["not", c]` of conditions.

## A worked example

A worked example is a use of the equation that a published source prints: the value of every input and the result. Examples are kept apart from the rows, in a file that names each row by its id.

```json
{"examples": {"example/hoop-stress": [
  {"anchor": "the textbook, Example 8.1, p. 414",
   "given": {"p": "1.5 MPa", "r": "600 mm", "t": "8 mm"},
   "gives": "112.5 MPa"}
]}}
```

`given` holds every input of the row, as the source states it. It may hold more: a quantity the source states and the row does not read is ignored, and the row then reproduces the result only if it was right not to read it. `gives` is the result as printed, with its unit. A reproduction must come within 0.5% of the printed result, or within half a unit of its last printed digit when that is more, because a worked example rounds what it carries from line to line. `within` states another bound, such as `"1 %"`, when the print warrants it.

## The acceptance check

| Part | Passes when | Is `none` when |
|---|---|---|
| `units` | Every sum, comparison, minimum and maximum is of one dimension, every exponent and every argument of `exp` and `ln` is a plain number, and each case gives the row's dimension | never |
| `examples` | The row reproduces every worked example given for it | no example is given |
| `continuity` | Wherever one case hands over to another, the two differ by at most 1%, or `jumps` names that pair | no two sample points fell in different cases |
| `second` | A second transcription, made without sight of the first, gives the same value at 96 points drawn from the ranges and at every meeting of the cases | no second transcription is given |

A row is admitted when no part fails. A part that is `none` is not a failure. It says the row has less behind it: a row with no worked example rests on its dimensions and on two transcribers agreeing.

The second transcription may name its inputs differently. The check tries each renaming that keeps the dimensions, and says which one it used.

```bash
python -m petra.deck rows.json --examples examples.json --second other_rows.json
```

The command prints each row as admitted or refused with the four parts, and exits 0 when every row is admitted, 1 when one is refused, and 3 when a file does not hold rows.

## What the check cannot see

- A transcription that is wrong in a way that keeps the dimensions, where no worked example exercises the error and a second transcriber makes the same mistake.
- An equation used outside the conditions its clause sets, when the row leaves those conditions out. A condition that is not a comparison of quantities, such as a hole type or a design method, cannot be written in a row at all.
- Whether the row is the right equation for a design. A deck binds rows to the parts of a design, and that binding is not a row.

The kernel does not read rows yet, so a row proves nothing by itself.
