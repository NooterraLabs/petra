# Ambiguities found while implementing the kernel from format.md and deck.md

Each entry: where in the text, the question, the readings considered, and the reading taken.
"(example)" marks an entry where an example file taught something the text should have said.

## A. Units and numbers

A1. reference.md, Units. The task says reference.md has "the table of units and their factors". It has only spellings, no factors. format.md gives two factors (inch = 127/5000 m, lbf = 0.45359237 kg x 9.80665 m/s2). Taken: the usual exact definitions: ft = 12 inch, kip = kips = 1000 lbf, psi = lbf/inch2, ksi = 1000 psi, inch2 = inch^2, kip_in = kip x inch, kip_ft = kip x ft, % = 1/100, g = 1/1000 kg, the SI prefixes as named (um, mm, cm, km, mm2, m2, kN, MN, kPa, MPa, GPa, uA, mA, kA, kV, mohm = milliohm, kohm, Mohm, mW, ms), J = Nm = 1, A2s = A^2 s, degC = 1 on a base of degree Celsius (no offset, since the fifth base unit is the degree Celsius itself). Checked: 36 ksi and 45 kip reproduce the example cards' exact values.

A2. format.md, rules.json, "a quantity with its unit, such as ... `29,000 ksi`" against deck.md, A table: "with no space or comma inside a number: `1100`, not `1 100`". Readings: commas never allowed; commas allowed in any quantity. Taken: a quantity (number and unit in one string) may group its integer part in threes with commas (`29,000`, `1,100`); a badly grouped comma (`2,90`) is refused, and a number alone never takes a comma.

A3. format.md, rules.json, quantity syntax. Not said: whether the space between number and unit is required (the language writes `10mm`), whether a number alone may stand where a quantity of a dimension is expected. Taken: number, then optional single space, then a unit spelling; a mixed number is `INT SPACE INT/INT` and needs a unit; a string without a unit is a number alone and is dimensionless.

A4. deck.md, A table: "A first band ... starts at `0`." Written as a bare `0`, which by A3 is dimensionless, while the band must have its input's dimension. Taken: a bare zero (`0`, `0.0`, `-0`, `0/5`) is accepted as the zero of any dimension wherever the deck writes a quantity (band ends, `at`, ranges, `least`, cells).

A5. format.md, Numbers: "A string longer than 4,000 characters is refused." Unclear whether this means any string in any file or only a number string. Taken: number strings only (the sentence is in the Numbers section); `what`, `why` and `about` texts have no limit.

A6. format.md, Numbers: lowest terms, no leading zero, no `-0` for numbers in card, design, deck.json and proofs. Not said for deck numbers. Taken: deck numbers follow the rules.json grammar only (`6/4`, `007` and `0.90` are allowed in a deck; a denominator of 0 is refused).

A7. format.md, rules.json, "A number alone ... digits with an optional sign, and then a decimal part or a denominator." Not said whether `.5` or `5.` or `1.5/2` are numbers. Taken: digits are required on both sides of the point, and a denominator is digits only.

A8. format.md, rules.json, dimensions. "A power is written `length^3`, and a product or a quotient `force/length`." The product sign is never shown. Taken: `*` for a product, `/` for a quotient, `^` followed by an optional `-` and digits for an integer power, evaluated left to right (`a/b*c` is `(a/b)*c`), no spaces, and every base one of the fourteen names.

A9. format.md, What the kernel does not check, "It checks that a part's number has the dimension its field asks, by the name of the dimension that the file states." Not said whether names are compared as text or as exponents (`moment` and `energy` have the same exponents; `area` and `length^2` too). Taken: as text, for a part's number, a given's card input and a load's card input against the deck's field or load. Inside the deck (bindings, sums, both sides of `le`) dimensions are compared as exponents.

## B. JSON

B1. format.md, Limits: "A file's JSON nests at most 128 deep, and a number outside a string has at most 32 digits and no fraction or exponent." Not said what breaking a limit leads to. Taken: the file is not JSON the kernel reads, so Shape is broken and the verdict is ILL-FORMED. Depth counts each array or object as one level, the outermost being 1.

B2. format.md, deck rule "every input of a row is bound once". A JSON object can repeat a key, and the text does not say what the reader does then. Taken: a repeated key in any object of any file is refused as ill formed JSON (ILL-FORMED); a reader that kept the last value would silently drop a binding.

B3. Not said: byte order mark, invalid UTF-8. Taken: the file must be valid UTF-8 with no byte order mark.

## C. Shape and the proofs file

C1. format.md, The rules, Shape: "Every number parses". The proofs file is a file too, so an unparseable `at` of a partition or value of a point breaks Shape and makes the whole verdict ILL-FORMED, which sits badly with "proofs.json ... cannot add a cell, drop one, or change what a cell says." Taken: literal. A hint's `subject`, `mechanism`, `entry` and `state` must be strings and the state one of the five; a number string inside a partition or a point must parse; a break is ILL-FORMED. A partition or point that parses but is wrong (bad label, `at` outside its range, missing value) only fails that hint.

C2. format.md, proofs.json: a hint may carry both a `partition` and a `point`, or a state that does not match what it carries ("The state a hint claims decides nothing"). Taken: each hint is tried for what it carries, the partition first and then the point; a hint's state is never read.

C3. format.md, Cells from a deck of rules, 6: "A point that has a value for every input". Not said whether a point may hold values for labels the tape does not read. Taken: extra labels are ignored.

C4. format.md, Limits: "A value with more than 65,536 bits ... leaves its cell open." Not said whether bits means the numerator, the denominator or both, nor whether "its cell" means the whole cell or only the hint being tried. Taken: a rational whose numerator or denominator has more than 65,536 bits gives its node no value on that box; the hint fails, and a later hint may still settle the cell.

C5. (example) format.md, proofs.json says a cell in proofs.json is a hint "for the kernel's own cell". The examples carry hints for waived, not_applicable and no-rule open cells, with `why` and no partition. Taken: those match cells the kernel has, so they are not "ignored", and they change nothing.

C6. format.md: the command line requires `--proofs` only optionally. Taken: with no proofs file there are no hints; every rule cell is open.

C7. format.md, The verdict: a file that cannot be read (missing path). Taken: ILL-FORMED with a finding, not the usage exit 64, which is kept for a command line that does not parse.

C8. The task leaves out the path for a design with no parts. format.md gives no verdict for "this kernel does not read that path". Taken: exit 64 with a message on stderr and no JSON, so such a design is never given a verdict this kernel did not compute.

C9. Not said: what the kernel prints when it fails inside itself. Taken: exit 70 with the error on stderr and no JSON, so a crash can never be mistaken for a verdict (a FAIL is exit 1, an internal error is never 0 to 3).

## D. The deck of rules

D1. format.md, The rules, The deck of rules: the list of checks does not include several things deck.md states as facts about a deck: bands "in order", the lower end first; `cells` having one line per place; the last case being the only one that may leave out `when`; a row's expression giving the row's `gives.dim`; a key being read only by a table. Taken: refuse a deck where cells do not have one line per place and one cell per across place; refuse a case without `when` that is not last; refuse a row whose expression or cells do not give `gives.dim` (deck.md's acceptance check, units part, says so, and without it the dimension check on rules would rest on an unchecked claim); refuse a key input in a row that is not a table; refuse `null` anywhere but the upper end of the last band. Not refused: bands out of order or overlapping, a band with lo > hi (the pick reads them as written).

D2. deck.md, A row, `range`: "two values, the lower first". Taken: each end must parse with the input's dimension and lo <= hi, else the deck is refused.

D3. deck.md, The grid, and format.md "no two rows, types, lines or rules have one name". The name of a line is not defined: its mechanism, or its type and mechanism. Taken: its mechanism; two grid lines with one mechanism are refused even for different types.

D4. deck.md, A type: "The name of a field ... is letters, digits and `_`, as the language writes a name." Taken: ASCII letters, digits and `_`, starting with a letter or `_` (reference.md's rule), for field, load, `as`, `let` and row input names. `pi` always means Pi in an expression; a field or `let` named `pi` cannot be read.

D5. deck.md, A rule: a key binding is "to a key field". Not said whether a joined part's key field (`a.grade`) may be named, though format.md, Cells 8 counts reads by "a rule that applies to the part that joins it", which only matters for keys if it can. Taken: a key binding, a `by` and an `["is", FIELD, NAME]` condition may name a key field of the part or `AS.FIELD` of a joined part.

D6. deck.md, A rule: `["by", FIELD, {NAME OF THE FIELD: NAME OF THE ROW'S KEY}]`. Not said whether the map must cover every name of the field. Taken: each key of the map must be a name of the field and each value a name of the row's key, and the map may be partial; a part whose key the map leaves out gives a tape that cannot be written ("a table has no line for the part's key", Cells 7), so its cell is open.

D7. deck.md, Expressions: "["pow", a, "2"], ["pow", a, "3/2"]: a power with a fixed exponent" and "["pow", a, b]: an exponent that varies". Not said what counts as fixed. Taken: the exponent is fixed when it is a number string; otherwise (a name, `pi`, a list) it varies and both base and exponent must be plain numbers. A fixed exponent that is neither whole nor half is written as exp of the exponent times ln, so its base must also be a plain number.

D8. format.md, rules.json and Limits: a half power k/2 is "a `pow` of a `sqrt`", and the deck allows a half power up to 64 in magnitude, but a tape's `pow` exponent is "at most 64 in magnitude". `a^(127/2)` would need `pow(sqrt a, 127)`. Taken: the tape limit is not applied to tapes the kernel writes itself; the deck limit (exponent at most 64) is.

D9. format.md, rules.json: "a negative one is 1 over it". Taken: `a^-n` is `div(c 1, pow(a, n))` and `a^(-k/2)` is `div(c 1, pow(sqrt a, k))`.

D10. format.md, Limits: "An expression nests at most 1,024 deep, counted through the names of `let` it reads and the rows it applies". The unit of depth is not defined. Taken: a leaf is 1, a list is 1 more than its deepest argument, a `let` name is 1 more than its expression, a row application is 1 more than the row's expression with each input taking the depth of its binding. A `let` that reads itself, directly or through others, is refused.

D11. deck.md, A rule, `where`. Not said whether `where` may be an empty list. Taken: a present `where` always needs its range proved; an empty one gives a tape with no root, which cannot be proved ("A tape has at least one root"), so the rule's cell is open.

D12. deck.md, The grid: `["loaded", LOAD]` is not defined. Taken: it holds when the card puts that load on the part in at least one case.

D13. format.md, The rules: the checks of a deck say "it has no unknown key". Not said which keys are required. Taken: required are a row's `id`, `gives` (with `name` and `dim`), `takes` and one of `is`, `cases`, `table`; a type's `type` and `fields`; a field's `name` and one of `dim`, `one_of`, `type`; a load's `name` and `dim`; a grid line's `type` and `mechanism`; an `unless`'s nothing; a rule's `id`, `type`, `mechanism` and `le`. Descriptive keys (`what`, `why`, `says`, `about`, `anchor`) are optional but must be text (an anchor: an object of texts with keys `standard`, `clause`, `equation`, `table`, `page`).

D14. deck.md, A type: `signed`, `whole`, `least` only make sense on a quantity, `as` only on a joining field. Taken: refused elsewhere. `signed` and `whole` must be JSON booleans (format.md: "a flag is `true` or `false`").

D15. deck.md, A rule, "every rule answers a line of the grid that can arise". Taken: the rule's `type` and `mechanism` name a line, and that line has no `unless` without `when`. A conditional `unless` can arise for some part, so it passes.

D16. Not said: two rules of one line whose ids end in the same text after the last `/` give two cells with one entry. Not refused; hints for the entry are tried for both cells.

## E. Parts and the card

E1. format.md, card.json: the card's required keys are not stated, nor whether it may have other keys (the design may not). Taken: `format` and `name` are required; `inputs`, `waivers`, `claims`, `tests` and `probability_claims` default to empty lists; `cases` and `environment` are not read; other keys are not refused.

E2. format.md, Parts 3: "A `whole` field is one whole number that the design writes." Taken: a number argument with lo = hi and an integer value.

E3. format.md, Parts 3: "more than zero and at least the field's `least`" for a given. Taken: the card input's `lo` must be more than zero and at least `least`.

E4. format.md, Types 5 and card.json "An input with no `by` ... the kernel refuses the card". Taken: `by` must be a non-empty text for every input and every waiver; a break is ILL-FORMED.

E5. format.md, card.json: an input with some but not all of `case`, `on`, `field`. Taken: neither a load nor a given, so ILL-FORMED.

E6. format.md, Types 1, the card's SHA-256. Not implemented, as the task allows; the design's `card` is only checked to be a text.

E7. format.md, Parts 5: not said whether a part may join itself (possible only if a type joins its own type). Not refused beyond "different parts" and "no part is joined more than once".

## F. Cells

F1. format.md, Cells from a deck of rules, opening sentence: "for each part in the design's order, each line the grid has for its type in the deck's order, and then each field that nothing reads." Readings: the unread fields of a part follow that part's lines; or all unread fields come after all parts. Taken: per part, its lines and then its unread fields.

F2. Same sentence: the order of a part's unread fields, the type's field order or the part's line order. Taken: the type's field order.

F3. format.md, Cells 8: "read by a rule that applies to the part". Not said whether a rule applies when its line is waived for the part or its line's `unless` holds, nor whether the reads of a rule whose `when` fails count. Taken: a rule applies to a part when it is of the part's type and its `when` holds, whatever the waivers and `unless`; its reads are the fields named in `le`, `where`, `when`, in the `let` names those reach, and in its row bindings (a direct key field and the field of a `by`). An `unless` with a condition reads its key fields whether or not it holds.

F4. (example) format.md, Cells 4: a rule that reads a load and finds no case for it "gives one `open` cell". Its entry is not stated. d08_no_load's hints show the rule's id tail with no `/CASE` (`lap-strength`). Taken: that.

F5. (example) Same case: not said whether its `where` is still tried and a `/where` cell made. Taken: no `/where` cell is tried or made; the one cell is open.

F6. format.md, Cells 4: "in the order of the cases' names". Taken: sorted by Unicode code point of the case name (not the card's `cases` list, which format.md says is not read).

F7. format.md, Cells 4: "Its `entry` is the rule's id from its last `/` on, so `lap-yield-a`". "From its last `/` on" would include the slash; the example does not. Taken: the text after the last `/`, or the whole id when it has none.

F8. format.md, Cells 4: what "reads a load" means. Taken: a `["load", NAME]` in `le`, `where` or a `let` they reach. `["loaded", LOAD]` in `when` is a condition on presence, not a read.

F9. (example) The order of a `/where` cell and its rule's cell is not stated. The examples put `.../where` first. Taken: the `/where` cell first, then the rule's cell, for each case.

F10. format.md, Cells 7: "a table has no line for the part's key" cannot happen with a direct key binding, which the deck check makes total. Taken: it arises only through a partial `by` (D6). "Every cell it could read is empty" is read as: after the keys are fixed, every cell of the remaining line, column or table is null.

## G. Tapes and picks

G1. format.md, Tapes: "The kernel takes each pair of compared nodes once". Not said whether `le(a, b)` and `lt(b, a)` compare one pair or two. Readings: ordered pairs (a way may then choose `a < b` for one and `b < a` for the other, a combination no point takes, which can leave no case and so no value); unordered pairs. Taken: unordered; one order is chosen for {a, b} and read in both directions. This also makes the translation of `ge` and `gt` (as `le` and `lt` with the sides swapped) immaterial.

G2. format.md, Tapes, "one node for each distinct quantity". Not said whether constants and other subexpressions are shared. Taken: every node is shared by structure (two identical nodes are one), which keeps the pairs a table compares identical, as the text wants.

G3. deck.md, A table, bands. The pick conditions are not given. Taken: `closed: upper` is `lo < x and x <= hi`, `closed: lower` is `lo <= x and x < hi`, a null upper end drops the second comparison; `at` is `x <= v and v <= x`; no fallback case, so outside every band or between listed values the pick has no value. An empty cell gives no case. A table with two quantity sides is a pick over the lines whose cases are picks over the columns.

G4. format.md, Tapes: "The pick's enclosure is the least range that contains the enclosure of every case that is first in some way." Taken: all compared nodes of a pick are evaluated (a failure fails the pick), the ways are counted before enumeration (more than 4,096 fails), and only the nodes of cases first in some way are evaluated.

G5. format.md, The interval rule: sqrt, ln, exp and pi "rounded outward on a grid of 2^-96". Taken: an absolute grid: the lower end is floor(2^96 f) / 2^96 and the upper ceil(2^96 f) / 2^96 of the true value at each end (each function increasing), refined until the two ends are at most one grid step apart; exact when the true value lies on the grid (sqrt of a square, exp 0, ln 1). sqrt of a range reaching below zero, ln of one reaching zero or below, and exp of one reaching beyond 65,536 in magnitude have no value.

G6. format.md, Partitions: "The value x lies strictly inside the range the input has at that point of the tree." Taken: a split outside, on an end, of an unknown label or beyond depth 64 fails the hint.

G7. deck.md, Expressions, and format.md, Tapes: `add`, `mul`, `min` and `max` are shown with two arguments; their arity is not stated. Taken: one or more arguments in a deck and on a tape (one argument is that argument), zero refused; `add`, `min` and `max` need all arguments of one dimension, and `mul` multiplies the dimensions.
