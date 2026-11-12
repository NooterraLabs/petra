# Ambiguities found while implementing the kernel from format.md and deck.md

Each entry: where in the text, the question, the readings considered, and the reading taken.
"(example)" marks an entry where an example file taught something the text should have said.

A line that starts "Settled:" was added after the pages changed (changed_since_you_wrote_it.diff). It quotes the sentence that settles the entry and says whether the code changed. Sections H and I are new with that change.

A line that starts "Settled (second change):" was added after the pages changed again (changed_since_your_last_update.diff), in the same way. Section J is new with that change. Its entries also name the bundles of bundles/designs and bundles/decks that bear on them; no bundle's verdict, counts or cells disagree with this kernel, so every bundle named there differs only in its findings.

## A. Units and numbers

A1. reference.md, Units. The task says reference.md has "the table of units and their factors". It has only spellings, no factors. format.md gives two factors (inch = 127/5000 m, lbf = 0.45359237 kg x 9.80665 m/s2). Taken: the usual exact definitions: ft = 12 inch, kip = kips = 1000 lbf, psi = lbf/inch2, ksi = 1000 psi, inch2 = inch^2, kip_in = kip x inch, kip_ft = kip x ft, % = 1/100, g = 1/1000 kg, the SI prefixes as named (um, mm, cm, km, mm2, m2, kN, MN, kPa, MPa, GPa, uA, mA, kA, kV, mohm = milliohm, kohm, Mohm, mW, ms), J = Nm = 1, A2s = A^2 s, degC = 1 on a base of degree Celsius (no offset, since the fifth base unit is the degree Celsius itself). Checked: 36 ksi and 45 kip reproduce the example cards' exact values.

A2. format.md, rules.json, "a quantity with its unit, such as ... `29,000 ksi`" against deck.md, A table: "with no space or comma inside a number: `1100`, not `1 100`". Readings: commas never allowed; commas allowed in any quantity. Taken: a quantity (number and unit in one string) may group its integer part in threes with commas (`29,000`, `1,100`); a badly grouped comma (`2,90`) is refused, and a number alone never takes a comma.

Settled: deck.md, A value with its unit: "A comma is read between thousands and nowhere else: `29,000 ksi` is 29000 ksi, and `2,90` is refused. The digits before the first comma are one to three, and each group after a comma is three." and "So `1 1/2` alone is the number 3/2, and `1,000` alone is the number 1000." and "A number alone in an expression, such as `"2.4"`, is the first form only. It takes no comma and no whole number with a fraction." Code changed: a value with no unit (a range end, a `least`, a band end, a value of `at`, a cell) may now take commas. A number alone in an expression still takes none. Where in the number a comma may stand is H11.

A3. format.md, rules.json, quantity syntax. Not said: whether the space between number and unit is required (the language writes `10mm`), whether a number alone may stand where a quantity of a dimension is expected. Taken: number, then optional single space, then a unit spelling; a mixed number is `INT SPACE INT/INT` and needs a unit; a string without a unit is a number alone and is dimensionless.

Settled: deck.md, A value with its unit: "A value is a text: a number, one space, and a unit." and "A value with no unit is a plain number, of no dimension. So `1 1/2` alone is the number 3/2". Code changed: the space is required, so `10mm` is refused; a mixed number with no unit is the plain number it sums to. What may stand around the space is H5.

A4. deck.md, A table: "A first band ... starts at `0`." Written as a bare `0`, which by A3 is dimensionless, while the band must have its input's dimension. Taken: a bare zero (`0`, `0.0`, `-0`, `0/5`) is accepted as the zero of any dimension wherever the deck writes a quantity (band ends, `at`, ranges, `least`, cells).

Settled, the other way: deck.md, A value with its unit: "`0` and `-0` alone are the plain number zero. They are not the zero of every dimension: a length that is zero is written `0 mm`, and a range, a band or a `least` of a length that starts at a bare `0` is refused for its dimension." and A table: "A first band that the standard prints as "up to 6 mm" starts at zero, written with its unit: `0 mm`." Code changed: the exception for a bare zero is gone. A cell that holds no space is still read in the table's `unit`, so the shipped deck's cell `"0"` under `"unit": "inch"` is 0 inch.

A5. format.md, Numbers: "A string longer than 4,000 characters is refused." Unclear whether this means any string in any file or only a number string. Taken: number strings only (the sentence is in the Numbers section); `what`, `why` and `about` texts have no limit.

A6. format.md, Numbers: lowest terms, no leading zero, no `-0` for numbers in card, design, deck.json and proofs. Not said for deck numbers. Taken: deck numbers follow the rules.json grammar only (`6/4`, `007` and `0.90` are allowed in a deck; a denominator of 0 is refused).

A7. format.md, rules.json, "A number alone ... digits with an optional sign, and then a decimal part or a denominator." Not said whether `.5` or `5.` or `1.5/2` are numbers. Taken: digits are required on both sides of the point, and a denominator is digits only.

A8. format.md, rules.json, dimensions. "A power is written `length^3`, and a product or a quotient `force/length`." The product sign is never shown. Taken: `*` for a product, `/` for a quotient, `^` followed by an optional `-` and digits for an integer power, evaluated left to right (`a/b*c` is `(a/b)*c`), no spaces, and every base one of the fourteen names.

Note: this grammar is still the one of a deck of rules (deck.md, Dimensions, did not change). card.json, design.json and deck.json now have a grammar of their own; see H1.

A9. format.md, What the kernel does not check, "It checks that a part's number has the dimension its field asks, by the name of the dimension that the file states." Not said whether names are compared as text or as exponents (`moment` and `energy` have the same exponents; `area` and `length^2` too). Taken: as text, for a part's number, a given's card input and a load's card input against the deck's field or load. Inside the deck (bindings, sums, both sides of `le`) dimensions are compared as exponents.

Settled: format.md, Numbers: "Two names are one dimension when their exponents are equal, as `moment` and `energy` are, and `length` and `m^1`. Wherever the kernel compares two dimensions or looks one up, it does so by the exponents and never by the spelling." Code changed: a part's number, a given and a load are compared with the deck's field or load by exponents, and a floor of `domains.input` is looked up by exponents. The sentence A9 quotes is still on the page; see H16.

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

Note: format.md, Types 7, now gives findings that a design with no parts can have: "Each mark is a finding when the design has no `parts` or `--rules` names no deck." Code changed: the shape and type rules are applied to a design with no parts before the kernel gives up on it, and a finding there makes it ILL-FORMED. Before, such a design went to exit 64 whatever its type findings. Exit 64 is now only for a design with no parts that breaks no rule this kernel reads (H13).

C9. Not said: what the kernel prints when it fails inside itself. Taken: exit 70 with the error on stderr and no JSON, so a crash can never be mistaken for a verdict (a FAIL is exit 1, an internal error is never 0 to 3).

## D. The deck of rules

D1. format.md, The rules, The deck of rules: the list of checks does not include several things deck.md states as facts about a deck: bands "in order", the lower end first; `cells` having one line per place; the last case being the only one that may leave out `when`; a row's expression giving the row's `gives.dim`; a key being read only by a table. Taken: refuse a deck where cells do not have one line per place and one cell per across place; refuse a case without `when` that is not last; refuse a row whose expression or cells do not give `gives.dim` (deck.md's acceptance check, units part, says so, and without it the dimension check on rules would rest on an unchecked claim); refuse a key input in a row that is not a table; refuse `null` anywhere but the upper end of the last band. Not refused: bands out of order or overlapping, a band with lo > hi (the pick reads them as written).

Settled: deck.md, A table: "A band's lower end is under its upper end, and no band starts before the one before it ends. A side whose bands are out of order or lie over one another is refused, and so is a side whose listed values are out of order." and format.md, The deck of rules: "the bands of a table are in order and none lies over another". The code already refused these (the "Not refused" sentence above was out of date); no change.

D2. deck.md, A row, `range`: "two values, the lower first". Taken: each end must parse with the input's dimension and lo <= hi, else the deck is refused.

Note: a range is now required: deck.md, A row: "Every quantity a row takes has a `range`, and a row whose input has none is refused. Each end states its unit". Code changed: a quantity input with no `range` is refused.

D3. deck.md, The grid, and format.md "no two rows, types, lines or rules have one name". The name of a line is not defined: its mechanism, or its type and mechanism. Taken: its mechanism; two grid lines with one mechanism are refused even for different types.

D4. deck.md, A type: "The name of a field ... is letters, digits and `_`, as the language writes a name." Taken: ASCII letters, digits and `_`, starting with a letter or `_` (reference.md's rule), for field, load, `as`, `let` and row input names. `pi` always means Pi in an expression; a field or `let` named `pi` cannot be read.

Settled (second change): format.md, The deck of rules: "A name of a field, a load, a joined part or a `let` is letters, digits and `_`." and format.md, rules.json: "A name is a JSON string for both: the name of a type, of a field, of a load, of a joined part, of a mechanism, of an input of a row, ...". Code changed: the name of an input of a row and the name of a type are held to be a text that is not empty, and no longer to letters, digits and `_`. That a name does not start with a digit is still this kernel's reading, and an input of a row named `pi` is still refused. Bundles decks/lap-ill-formed-0 and decks/lap-ill-formed-13 rename an input of a row to `J3.6(b)` and `force/length`; the deck is now refused where the body reads the old name, as their findings say.

D5. deck.md, A rule: a key binding is "to a key field". Not said whether a joined part's key field (`a.grade`) may be named, though format.md, Cells 8 counts reads by "a rule that applies to the part that joins it", which only matters for keys if it can. Taken: a key binding, a `by` and an `["is", FIELD, NAME]` condition may name a key field of the part or `AS.FIELD` of a joined part.

D6. deck.md, A rule: `["by", FIELD, {NAME OF THE FIELD: NAME OF THE ROW'S KEY}]`. Not said whether the map must cover every name of the field. Taken: each key of the map must be a name of the field and each value a name of the row's key, and the map may be partial; a part whose key the map leaves out gives a tape that cannot be written ("a table has no line for the part's key", Cells 7), so its cell is open.

Settled: deck.md, A rule: "The map of a `by` has one entry for each name of the field and no other entry, and each of its values is a name of the row's key. A map that leaves a name of the field out is refused." Code changed: a partial map is refused and the deck does not load.

D7. deck.md, Expressions: "["pow", a, "2"], ["pow", a, "3/2"]: a power with a fixed exponent" and "["pow", a, b]: an exponent that varies". Not said what counts as fixed. Taken: the exponent is fixed when it is a number string; otherwise (a name, `pi`, a list) it varies and both base and exponent must be plain numbers. A fixed exponent that is neither whole nor half is written as exp of the exponent times ln, so its base must also be a plain number.

D8. format.md, rules.json and Limits: a half power k/2 is "a `pow` of a `sqrt`", and the deck allows a half power up to 64 in magnitude, but a tape's `pow` exponent is "at most 64 in magnitude". `a^(127/2)` would need `pow(sqrt a, 127)`. Taken: the tape limit is not applied to tapes the kernel writes itself; the deck limit (exponent at most 64) is.

D9. format.md, rules.json: "a negative one is 1 over it". Taken: `a^-n` is `div(c 1, pow(a, n))` and `a^(-k/2)` is `div(c 1, pow(sqrt a, k))`.

D10. format.md, Limits: "An expression nests at most 1,024 deep, counted through the names of `let` it reads and the rows it applies". The unit of depth is not defined. Taken: a leaf is 1, a list is 1 more than its deepest argument, a `let` name is 1 more than its expression, a row application is 1 more than the row's expression with each input taking the depth of its binding. A `let` that reads itself, directly or through others, is refused.

D11. deck.md, A rule, `where`. Not said whether `where` may be an empty list. Taken: a present `where` always needs its range proved; an empty one gives a tape with no root, which cannot be proved ("A tape has at least one root"), so the rule's cell is open.

Settled: deck.md, A rule: "A rule that holds everywhere leaves `where` out: `"where": []` is refused." and format.md, The deck of rules: "a `where` that is there has at least one item". Code changed: an empty `where` is refused and the deck does not load.

D12. deck.md, The grid: `["loaded", LOAD]` is not defined. Taken: it holds when the card puts that load on the part in at least one case.

Settled (second change), by removal: deck.md, Conditions: "The condition `["loaded", LOAD]`, which held when some case put the load on the part, is gone, and a deck that writes `loaded` in a `when`, an `unless` or a `requires` is" refused; format.md, The deck of rules: "no `when`, `unless` or `requires` asks `loaded`". Code changed: `loaded` is refused and the deck does not load.

D13. format.md, The rules: the checks of a deck say "it has no unknown key". Not said which keys are required. Taken: required are a row's `id`, `gives` (with `name` and `dim`), `takes` and one of `is`, `cases`, `table`; a type's `type` and `fields`; a field's `name` and one of `dim`, `one_of`, `type`; a load's `name` and `dim`; a grid line's `type` and `mechanism`; an `unless`'s nothing; a rule's `id`, `type`, `mechanism` and `le`. Descriptive keys (`what`, `why`, `says`, `about`, `anchor`) are optional but must be text (an anchor: an object of texts with keys `standard`, `clause`, `equation`, `table`, `page`).

Settled: deck.md now names them. A row: "A row has `id`, `anchor`, `gives`, `takes` and one of `is`, `cases` and `table`. `gives` has `name` and `dim`, each a text, and an input has `name`. The `what` of `gives` and of an input may be left out. A jump has `why`, a text that is not empty." A type: "A type has `type`, its name, `what`, a text, and `fields`. Its `what` may be the empty text." A field: "It has `name`, `what`, a text that is not empty, and one of `dim`, `one_of` and `type`." A load: "Each has a `name`, a `dim`, `what` it is, a text that is not empty". A line: "A line has `type`, `mechanism`, `anchor` and `what`, a text, which may be empty." An unless: "An `unless` has `why`, a text, which may be empty. An `unless` with no `why` is refused. A line whose `unless` is `null` is read as a line with none." A rule: "`says` ... a text that is not empty. A rule with no `says` is refused." An item of where: "Each item has `why`, a text, which may be empty." An anchor: "A row with no anchor, or with an anchor that lacks its standard or its clause, is refused. So is a line of the grid and a rule." Code changed to require each of these as stated; the anchor was already required.

Settled (second change): deck.md, A rule: "A rule has one of `le`, `lt` and `requires`, and never two of them. A rule with `requires` has no `let` and no `where`". A row that gives a name has `one_of` in place of `dim` in `gives`, and a type may have `loads` and `needs`. Code changed: `le` is no longer required of a rule; exactly one of the three is.

D14. deck.md, A type: `signed`, `whole`, `least` only make sense on a quantity, `as` only on a joining field. Taken: refused elsewhere. `signed` and `whole` must be JSON booleans (format.md: "a flag is `true` or `false`").

Settled: deck.md, A deck: "So is a key where it does not belong: `signed`, `whole` or `least` on a field that is no quantity, `as` on a field that joins no part, and `closed` on a side with no `bands`." The reading taken; no change. That `signed` and `whole` are booleans is still this kernel's reading.

Settled (second change): format.md, rules.json: "A flag of a field, `signed`, `whole` and `optional`, is `true` or `false` for both, and `may_be` is one of its two texts for both." and deck.md, A deck: "`whole`, `least` or `may_be` on a field that is no quantity, `signed` on a field that joins parts, `optional` on a field that joins parts or on a load". Code changed: the new keys are placed as the page says, and a key may now be `signed`.

D15. deck.md, A rule, "every rule answers a line of the grid that can arise". Taken: the rule's `type` and `mechanism` name a line, and that line has no `unless` without `when`. A conditional `unless` can arise for some part, so it passes.

D16. Not said: two rules of one line whose ids end in the same text after the last `/` give two cells with one entry. Not refused; hints for the entry are tried for both cells.

Settled: deck.md, A rule: "A cell is entered under the id from after its last `/`, so two rules for one type and one mechanism have ids that differ there: `a/x` and `b/x` together are refused." and format.md, The deck of rules: "no two rules for one type and one mechanism have ids that are the same after their last `/`". Code changed: such a deck does not load.

## E. Parts and the card

E1. format.md, card.json: the card's required keys are not stated, nor whether it may have other keys (the design may not). Taken: `format` and `name` are required; `inputs`, `waivers`, `claims`, `tests` and `probability_claims` default to empty lists; `cases` and `environment` are not read; other keys are not refused.

Settled (second change), in part: format.md, card.json now gives `cases` ("For a design with parts, the load cases of the card are these names and the `case` of each load, each once"), `environment` ("For a design with parts it is null ... a card that states one is refused (Parts 8)") and `states`. Code changed: all three are read. Whether other keys are refused is still not said, and they are not.

E2. format.md, Parts 3: "A `whole` field is one whole number that the design writes." Taken: a number argument with lo = hi and an integer value.

Settled (second change), differently: format.md, Parts 3: "A `whole` field is one whole number: a number that the design writes with `lo` equal to `hi`, or a given. ... For a count the card has one item of `states` of that name, with `whole`". Code changed: a count may be a given, read from `states`, and an input of that name or an item with `key` is a finding.

E3. format.md, Parts 3: "more than zero and at least the field's `least`" for a given. Taken: the card input's `lo` must be more than zero and at least `least`.

Settled (second change): format.md, Parts 3: "Its lower end is more than zero. With `may_be: zero` on the field it is at least zero, and with `may_be: negative` it has no floor by its sign." The reading taken for a field without `may_be`; code changed for the two kinds of `may_be`.

E4. format.md, Types 5 and card.json "An input with no `by` ... the kernel refuses the card". Taken: `by` must be a non-empty text for every input and every waiver; a break is ILL-FORMED.

Settled: format.md, Types 5: "Every input and every waiver of the card names a `by` that is not the empty text." and card.json: "An input whose `by` is the empty text is refused too (type rule 5)." The reading taken; no change.

E5. format.md, card.json: an input with some but not all of `case`, `on`, `field`. Taken: neither a load nor a given, so ILL-FORMED.

E6. format.md, Types 1, the card's SHA-256. Not implemented, as the task allows; the design's `card` is only checked to be a text.

Note: the pages did not change Types 1, and it is still not implemented. The tests of this folder edit the bundle's card without changing the design's `card`, which a kernel that checks Types 1 would refuse.

E7. format.md, Parts 5: not said whether a part may join itself (possible only if a type joins its own type). Not refused beyond "different parts" and "no part is joined more than once".

## F. Cells

F1. format.md, Cells from a deck of rules, opening sentence: "for each part in the design's order, each line the grid has for its type in the deck's order, and then each field that nothing reads." Readings: the unread fields of a part follow that part's lines; or all unread fields come after all parts. Taken: per part, its lines and then its unread fields.

Settled: deck.md, A design checked against a deck: "These cells come after every other cell, part by part, each part's in the order of its type's fields." So all unread cells come after all other cells. The code already put them there (the "Taken" above was out of date); no change.

F2. Same sentence: the order of a part's unread fields, the type's field order or the part's line order. Taken: the type's field order.

Settled: by the same sentence, "each part's in the order of its type's fields". No change.

F3. format.md, Cells 8: "read by a rule that applies to the part". Not said whether a rule applies when its line is waived for the part or its line's `unless` holds, nor whether the reads of a rule whose `when` fails count. Taken: a rule applies to a part when it is of the part's type and its `when` holds, whatever the waivers and `unless`; its reads are the fields named in `le`, `where`, `when`, in the `let` names those reach, and in its row bindings (a direct key field and the field of a `by`). An `unless` with a condition reads its key fields whether or not it holds.

Note: deck.md now says "A waiver takes the whole line ... no rule for that line is run on the part". It does not say whether a rule that is not run still reads the part's fields. Kept as taken; see H17.

Settled (second change): format.md, Cells 8: "A rule applies to a part when it is for the part's type and it answers for the part: its `when` holds, or names a key that is unstated (item 3). It applies whether or not the card waives its line or the line's `unless` holds." and "A name of `let` that none of those sides reads is not read. A rule also reads the key of each `is` in its `when` and in its `requires`". The reading taken, with `requires` and unstated keys added; code changed for those two.

F4. (example) format.md, Cells 4: a rule that reads a load and finds no case for it "gives one `open` cell". Its entry is not stated. d08_no_load's hints show the rule's id tail with no `/CASE` (`lap-strength`). Taken: that.

Settled (second change), differently: format.md, Cells 4: "A rule that reads loads gives one cell for each load case of the card ... Under a case that does not [put every load the rule reads on the part], the cell is `open`, there is no `/where` cell ... When the card has no load case at all, the rule gives one `open` cell whose `entry` has no case." Code changed: the one open cell with no case is now only for a card with no load case; a case that leaves a load out gives its own open cell `RULE/CASE`.

F5. (example) Same case: not said whether its `where` is still tried and a `/where` cell made. Taken: no `/where` cell is tried or made; the one cell is open.

Settled (second change): by the same item, "there is no `/where` cell". The reading taken; no change.

F6. format.md, Cells 4: "in the order of the cases' names". Taken: sorted by Unicode code point of the case name (not the card's `cases` list, which format.md says is not read).

Settled (second change): format.md, Cells from a deck of rules: "The load cases of the card are the names its `cases` lists and the `case` of each of its loads, each name once ... Names are in order by their characters, each compared by its code point, and a name comes before every longer name that starts with it." Code changed: the card's `cases` is read, and its names are load cases too.

F7. format.md, Cells 4: "Its `entry` is the rule's id from its last `/` on, so `lap-yield-a`". "From its last `/` on" would include the slash; the example does not. Taken: the text after the last `/`, or the whole id when it has none.

Settled: deck.md, A rule: "A cell is entered under the id from after its last `/`". format.md keeps "from its last `/` on" with an example that has no slash; see H9. No change.

F8. format.md, Cells 4: what "reads a load" means. Taken: a `["load", NAME]` in `le`, `where` or a `let` they reach. `["loaded", LOAD]` in `when` is a condition on presence, not a read.

Settled (second change): format.md, Cells 8: "A load is read by an expression and by nothing else." `loaded` is gone (D12). The reading taken, for `le` and `lt`; no change.

F9. (example) The order of a `/where` cell and its rule's cell is not stated. The examples put `.../where` first. Taken: the `/where` cell first, then the rule's cell, for each case.

F10. format.md, Cells 7: "a table has no line for the part's key" cannot happen with a direct key binding, which the deck check makes total. Taken: it arises only through a partial `by` (D6). "Every cell it could read is empty" is read as: after the keys are fixed, every cell of the remaining line, column or table is null.

Note: now that a partial `by` is refused (D6), a deck that loads cannot reach "a table has no line for the part's key". The code keeps the check as a guard.

## G. Tapes and picks

G1. format.md, Tapes: "The kernel takes each pair of compared nodes once". Not said whether `le(a, b)` and `lt(b, a)` compare one pair or two. Readings: ordered pairs (a way may then choose `a < b` for one and `b < a` for the other, a combination no point takes, which can leave no case and so no value); unordered pairs. Taken: unordered; one order is chosen for {a, b} and read in both directions. This also makes the translation of `ge` and `gt` (as `le` and `lt` with the sides swapped) immaterial.

G2. format.md, Tapes, "one node for each distinct quantity". Not said whether constants and other subexpressions are shared. Taken: every node is shared by structure (two identical nodes are one), which keeps the pairs a table compares identical, as the text wants.

G3. deck.md, A table, bands. The pick conditions are not given. Taken: `closed: upper` is `lo < x and x <= hi`, `closed: lower` is `lo <= x and x < hi`, a null upper end drops the second comparison; `at` is `x <= v and v <= x`; no fallback case, so outside every band or between listed values the pick has no value. An empty cell gives no case. A table with two quantity sides is a pick over the lines whose cases are picks over the columns.

Settled (second change): format.md, How the kernel writes a table, gives these conditions and this build, line by line, with "A line whose first case has no condition is the node of that case" and "Where the first of them has no condition, the table is that line's node". The reading taken; code changed only for a side whose key a row names, which is new.

G4. format.md, Tapes: "The pick's enclosure is the least range that contains the enclosure of every case that is first in some way." Taken: all compared nodes of a pick are evaluated (a failure fails the pick), the ways are counted before enumeration (more than 4,096 fails), and only the nodes of cases first in some way are evaluated.

G5. format.md, The interval rule: sqrt, ln, exp and pi "rounded outward on a grid of 2^-96". Taken: an absolute grid: the lower end is floor(2^96 f) / 2^96 and the upper ceil(2^96 f) / 2^96 of the true value at each end (each function increasing), refined until the two ends are at most one grid step apart; exact when the true value lies on the grid (sqrt of a square, exp 0, ln 1). sqrt of a range reaching below zero, ln of one reaching zero or below, and exp of one reaching beyond 65,536 in magnitude have no value.

Note: format.md now says "An `ln` or an `exp` is rounded from an enclosure of 128 bits, and from one of 224, 608 and then 2,144 bits when the one before has a point of the grid inside it." That is how the reference finds the same ends; the ends on the grid are what G5 takes, so no change.

G6. format.md, Partitions: "The value x lies strictly inside the range the input has at that point of the tree." Taken: a split outside, on an end, of an unknown label or beyond depth 64 fails the hint.

G7. deck.md, Expressions, and format.md, Tapes: `add`, `mul`, `min` and `max` are shown with two arguments; their arity is not stated. Taken: one or more arguments in a deck and on a tape (one argument is that argument), zero refused; `add`, `min` and `max` need all arguments of one dimension, and `mul` multiplies the dimensions.

## H. New with the changed pages

H1. format.md, Numbers: a `dim` of card.json, design.json and deck.json is one of sixteen names "or the exponents of metre, kilogram, second, ampere and degree Celsius that are not zero, as in `m^3 s^-1`: each a base, `^` and a whole number, with one space between two." Not said whether the bases may come in any order, whether one base may come twice, whether `^1` may be left out, or whether the empty text names the dimensionless. Taken: the bases in the order the sentence lists them (`m`, `kg`, `s`, `A`, `degC`), each at most once, each with `^` and a whole number that is not zero and has no `+`, one space between two and none elsewhere. `m kg s^-2`, `kg^1 m^1 s^-2`, `m^0` and the empty text are refused. A deck of rules keeps its own grammar (A8).

Settled (second change), differently: format.md, Numbers: "They may stand in any order, and a base may stand more than once: its exponents are then added, so `m^1 m^1` is `m^2` and `kg^1 m^1 s^-2` is a force. Each base has its `^` and its whole number. The number may be zero or negative, may have leading zeros and has no `+`: `m` alone names no dimension, and `m^0` is the dimensionless. The empty text names no dimension, and neither does a text with two spaces together or with a space at either end." Code changed: any order, repeats added, `^0` and leading zeros read.

H2. format.md, Types 4: "Every input's `dim` names a dimension." Not said for the `dim` of a design's `quantities` or `params`, which the kernel does not compare with anything. Taken: not checked.

Settled (second change): format.md, Numbers: "The `dim` of an item of `quantities`, of `params` and of the `bound` of a claim is a text that the kernel reads no further: it is not held to name a dimension." The reading taken; no change.

H3. format.md, Limits: "A character outside ASCII prints in up to four, a quote, a backslash and a line end in two, and any other control character in six." Not said which characters are line ends, nor whether DEL is a control character. Taken: LF and CR are line ends (2); every other character below U+0020, the tab among them, is 6; U+007F is ASCII and 1; a character outside ASCII is the length of its UTF-8 (2 to 4).

Settled (second change): format.md, Limits: "A line end is a line feed, U+000A, or a carriage return, U+000D. A control character is any other character below U+0020: the tab is one, and prints in six. U+007F is none, and prints in one. A character outside ASCII prints in the bytes of its UTF-8". The reading taken; no change.

H4. deck.md, A value with its unit: "`["q", NUMBER, UNIT]` holds its two halves, which are joined with one space and read as one value." Taken: literally, so a `q` takes what any value takes (commas, a whole number with a fraction), and `["q", "3", ""]` is `3 `, the plain number 3.

Settled (second change): deck.md: "Both halves are texts. So a `q` takes whatever a value takes: `["q", "29,000", "ksi"]` and `["q", "1 1/8", "inch"]` are read". The reading taken; no change.

H5. deck.md, A value with its unit: "a number, one space, and a unit" against "Spaces, tabs and line ends around the value are dropped, and so are those around the unit. No other character is." Not said whether `3  inch` or `3\tinch` is one space. Taken: between the number and the unit stands a run of spaces, tabs and line ends that holds at least one space. `3  inch` and `3 \tinch` are read, `3\tinch` is refused. Line ends are LF and CR (H3). No other character, such as a no-break space, is dropped.

Settled (second change), differently: deck.md: "The space that parts the number from its unit is the first space of the value, the character U+0020. More spaces, tabs and line ends may follow it before the unit, and they are dropped: `3  inch` is 3 inch. A tab alone does not part the two". Code changed: the number ends at the first U+0020, so `3 \tinch` is still read and `3\t inch`, which H5 read, is now refused.

H6. deck.md, A table, `unit`: "A cell that holds a space is read as stating its own." Not said whether a space at the start or the end counts, or whether a tab is a space. Taken: a cell that holds U+0020 anywhere states its own unit, so `"1 "` is the plain number 1, whatever `unit` says, and is refused in a table of a dimension. A cell with a tab and no space is read in the table's unit, and `"1\tinch"` is then no value and is refused.

Settled (second change), differently: deck.md, A table: "Spaces, tabs and line ends around a cell are dropped first. A cell that then holds a space is read as stating its own, and any other cell is read in the table's `unit`: `"1 "` under `"unit": "inch"` is 1 inch." Code changed: a cell is trimmed before the space is looked for.

H7. deck.md, A type: "The kernel holds these names, a name of `let`, a mechanism and a rule's id to 64 characters" against format.md, Limits: "64 bytes as printed". Taken: bytes as printed (format.md's table and the paragraph under it say how they are counted). The two agree for names of letters, digits and `_`; they differ for a mechanism or an id outside ASCII or with a quote, a backslash or a control character.

Settled (second change): deck.md, A type, now says "to 64 bytes as printed". The reading taken; no change.

H8. format.md, Steps. The page counts the steps to make the cells but leaves choices open. Taken:
- (a) A line that is waived or not applicable costs its own step and the size of its `unless`, and its rules cost nothing: a waived line runs no rule (deck.md: "no rule for that line is run on the part"), and Cells 3 comes to a line's rules only when the line is neither. Every rule of a line that is neither costs its step, whether its `when` holds or not.
- (b) The size of an `unless` with no `when`, and of no `unless` or a null one, is 0.
- (c) "The load cases": for each load the rule reads, the number of cases that put that load on the part. A case that puts two of its loads counts twice.
- (d) "The weight of the rule each time it is written for a part and a load case, twice for a rule with `where`": charged once for each case the rule gives a cell, before the tape is written, as twice the weight for a rule with `where` even when the `where` is not proved and the tape of `le` is then not written. A rule that reads a load the card puts on the part in no case writes no tape and costs no weight.
- (e) "One step for each node of each tape written": a node costs a step when it is added to a tape. Nodes are shared by structure within one tape (G2), so a repeated part costs once. A tape whose writing stops (no line for a key, every cell empty, more than 1,024 orders) has paid for the nodes added before it stopped. The orders and the keys of a row are checked before any node of that row is written.
- (f) The weight of an expression: a name, a number, `pi`, a `q` and a `load` weigh 1. `add`, `mul`, `min` and `max` of n arguments weigh 1 + n and their arguments. `neg`, `abs`, `sqrt`, `exp` and `ln` weigh 2, `div` 3, `sub` 5 (a negation, 2, and a sum of two, 3), each with its arguments. A power with a fixed whole exponent of 0 or more weighs 2 (a power); below 0, 6 (a power, a one and a quotient); a half power above 0, 4 (a root and a power); below 0, 8; a fixed exponent neither whole nor half, 8 (a constant, a logarithm, a product and an exponential); a varying exponent, 7 and its weight (a logarithm, a product and an exponential). Each power adds the weight of its base. The exponent of a fixed power is not a step.
- (g) A rule weighs each `let` once, read or not, and its `le` and each item of `where` as a difference of the two sides (5 and both sides). Its `when` is not in its weight: it is counted as "the size of its `when`".
- (h) A row applied weighs each of its quantity bindings once, however often the row reads the input, 1 for each key binding, and its body. The `row` itself weighs nothing more. An `is` weighs its expression, each input read in it a name of 1. Cases weigh 1, 1 for each case and 2 for each order, with both sides of each comparison and each case's `is`; `and`, `or` and `not` add nothing. A table weighs 1, 1 for each place down, 1 for each cell (empty ones too) and 1 for each entry of each `by` that binds one of its keys.
- (i) "What a rule reads": "the steps of the rule above" are 1, the size of its `when` and one for each load it reads; "one for each field the rule reads" counts the distinct fields of the part and `AS.FIELD` names in its reads (F3), loads apart.
- (j) The steps are charged in this order: per part and line, the line, then its rules; per rule and case, the load cases, the weight, the nodes; after the unread cells, what a rule reads. The limit is tested before each charge, so a design is refused at the first charge that would pass 10,000,000.

Settled (second change), mostly: format.md, Steps, now gives the count in five numbered items and a table of weights. Each letter above, against it:
- (a) differently: "The charge is made whether the card waives the line, the line's `unless` holds, or neither. A waived line also takes the charges of items 2 to 4, since its rules are run: a waiver saves no step." Code changed: the line and every rule of it are one charge, and a waived line runs its rules.
- (b) settled: "A line with no `unless`, and an `unless` with no `when`, has a condition of size 0." No change.
- (c) differently: "every load case of the card times every load the rule reads, in one charge. A case counts whether or not it puts the load on the part." Code changed.
- (d) settled: "It is twice whether or not the range is then proved. A case that leaves a load out pays no weight, and neither does a rule under a card with no load case." No change.
- (e) differently: "For each tape that is written: one step for each node the tape holds, once the tape is written ... A tape that cannot be written adds none." and "The nodes of item 4 are added with no test of their own". Code changed: a tape that stops pays nothing, and its nodes are tested at the next charge.
- (f) settled by the table, with the power of 0 now said: "A power of 0 is written as 1 over the power, as a negative one is." No change to the weights; the tape now writes a power of 0 that way too.
- (g) differently: "The comparison of two sides is no step: its two nodes, the negative of the second side and their sum, are counted with the nodes of the tape." Code changed: the 5 of a difference is gone from the weight.
- (h) differently: "A row applied: The steps of each quantity it binds, the steps of its body, and one step more of weight 1 and 1 for each quantity it binds. A key that is bound is no step. Inside the body, the name of an input is no step either". A pick of cases weighs 1, 1 for each case and 2 for each order, and "One case that holds otherwise is no pick." Code changed. What the table leaves open is J3 and J4.
- (i) settled by item 5: "The fields a rule reads are counted each once: the quantities and the keys that the sides of its `le` and of its `where` read, and the keys that its `when` and its `requires` name". No change, but for `requires`.
- (j) differently: "The limit is tested after each charge of items 1, 2, 3 and 5". Code changed: the count is made first and tested after it.

H9. format.md, Cells 4, "Its `entry` is the rule's id from its last `/` on", against deck.md, A rule, "the id from after its last `/`". Taken: after (F7). The example in Cells 4 has no slash.

Settled (second change): format.md, Cells 4, now says "whose `entry` is the rule's id from after its last `/`". The reading taken; no change.

H10. format.md, Parts 6: "The name of its case is within the limit below and holds no `/`. A case that breaks either is a shape finding." and Limits: "a load case that puts a load on a part". Not said whether the limit holds for an input with `case` and `on` that is not otherwise a valid load. Taken: it holds for every input with a text `case` and an `on`, in the shape rules, before it is known whether the load is valid.

Settled (second change), differently: format.md, Parts 6: "The kernel tests a load in this order and stops at the first that fails: its part, its field, its dimension, its `least`, that no case puts it on the part twice, and then the name of its case. ... So is a name in `cases` that no load has and that breaks either". Code changed: the name of a case is tested last, for a load that breaks nothing else, and the names of `cases` are tested too.

H11. deck.md, A value with its unit: "A comma is read between thousands and nowhere else". Not said in which parts of a number a comma may stand. Taken: in the digits before a decimal point or a `/`, and in the whole number of a mixed number; never in a decimal part, a denominator or the fraction of a mixed number.

Settled (second change), differently: deck.md: "A comma stands only in the digits before a decimal point, in a whole number or a decimal: `29,000` and `1,234.5`. A number with a `/` takes none, so `1,000/3` and `1,000 1/8 inch` are refused." Code changed: no comma before a `/` or in a mixed number.

H12. format.md, deck.json, `domains.input`: "Each key names a dimension, and a key that names none is a shape finding." Not said what a key whose value is not an object, or lacks `min` or `strict`, is. Taken: a shape finding too.

Settled (second change): format.md, deck.json: "So is a key whose value lacks `min`, a number, or `strict`, which is `true` or `false`." The reading taken; no change.

H13. format.md, Types 7, for a design with no parts. This kernel does not read the path of a design with no parts (C8). Taken: the shape and type rules are applied to it as to any design, and a finding makes it ILL-FORMED; with none, exit 64.

H14. format.md, Cells 7: "an equation or a table would be a pick of more than 1,024 orders" and Tapes: "The orders of a pick are every `le` and `lt` of its conditions." Not said how a table counts. Taken: a table read by quantities is written as G3 says, and each pick is counted on its own. A band with an upper end gives 2 orders, a last band with none 1, a listed value of `at` 2. Only the lines or columns that hold a cell the tape could read count. For a table with two quantity sides, the pick over the lines and each pick over the columns of a line are held to 1,024 apart. An equation's orders are its comparisons (`le`, `lt`, `ge`, `gt`), counted on the row.

Settled (second change): format.md, How the kernel writes a table: "Each pick is held to 1,024 orders on its own: the pick over the lines, and the pick of each line. A band with two ends has 2 orders, a band with one end 1, and a listed value 2. A cell of a row with two sides that gives a name has the orders of both its bands. An equation with cases is one pick, whose orders are the `le`, `lt`, `ge` and `gt` of its conditions." The reading taken; code changed to count a place that a row names, and a `case`, the same way.

H15. format.md, Cells: "a design that would have one key twice is ILL-FORMED with a finding of the rule `limits`." With the deck checks above, a deck that loads cannot give one key twice (the page says why). Taken: the check is made on every cell as it is added, as a guard; no test can reach it.

H16. format.md, What the kernel does not check: "It checks that a part's number has the dimension its field asks, by the name of the dimension that the file states." against Numbers: "by the exponents and never by the spelling". Taken: by the exponents (A9).

Settled (second change): format.md, What the kernel does not check, now says "by the exponents of the dimension that the file states". The reading taken; no change.

H17. deck.md: "A waiver takes the whole line ... no rule for that line is run on the part, whether or not it would hold." against format.md, Cells 8: "read by a rule that applies to the part". Not said whether a rule that is not run applies, for the unread cells. Taken: Cells 8 did not change, so F3 stands: a rule of the part's type whose `when` holds reads its fields whether or not its line is waived. No bundle tells the two apart: the shipped deck has no rule for a waived line of lap_pass.

Settled (second change), by a change of rule: format.md, Cells 1: "The cells of a line are made by items 2 to 7, whether or not the card waives the line's mechanism on the part: every rule of a waived line is run. Where the card does waive it, each cell of the line that those items leave `open` is then `waived` ... A cell that is `proved`, `refuted` or `not_applicable` stays so." Code changed: a waived line gives the cells of its rules, and a waiver rests only the open ones, with the reason `open but for the waiver: ` and the open cell's reason. 23 bundles have waived cells, and all agree.

H18. format.md, Limits: the 200-byte names are "for a design checked against a deck of rules", and Shape: "with `--rules` so are the name of the card and the name of the design". Taken: applied whenever `--rules` is given.

Settled (second change), in part: format.md, Shape: "Those two are tested when the deck that `--rules` names holds together. With a deck that does not, the kernel reads no part and tests neither name: the finding is the deck's." Code changed: the two names are tested only when the deck holds together. That they are tested for a design with no parts is still this kernel's reading.

H19. format.md, Limits: a finding of the rule `limits`. Not said which file and item it names. Taken: the file `design` and the item `limits`, with a reason that says which limit was passed.

Settled (second change), differently: format.md, Cells from a deck of rules: "A finding of the rule `limits` names the file `design`. Its item is `parts` when the design is past the cells, past the steps to make them, or would have one key twice, and the reason says which." Code changed: the item is `parts`. The item that names a part, for needs that run out of work, does not arise: work is left out (I).

## I. Limits applied and left out

format.md, Limits, lists thirteen limits. This kernel applies those that decide a verdict, a refusal or a state, and computes each as the pages define it. Each is tested before the work it bounds.

Applied: a part's name, 64 bytes as printed, and a load case's name, 64 bytes and no `/` (shape findings); the names of the card and the design, 200 bytes, with `--rules` (shape findings); the names of a field, a load, a joined part and a `let`, a mechanism and a rule's id, 64 bytes (the deck does not hold together); 1,000,000 steps to read a deck (the deck does not hold together, and it is refused before a row is read); 10,000 cells and 10,000,000 steps to make them (a finding of the rule `limits`, ILL-FORMED); one key twice (the same, H15); 1,024 orders in a pick the kernel writes (its cell is open). The limits of the first two paragraphs of Limits were handled before this change, as B1, C4, D8, D10 and G4 to G6 say. Those on a tape that a file carries do not arise here: this kernel reads no such tape.

Left out:
- Work for the proofs of one verdict, 20,000,000,000 units. The units are the reference kernel's own costs of its arithmetic (format.md, Work), which the task allows to be left out. Where the reference runs out of work its cell is open, and this kernel may still prove it. The bundles' work is 6,025,706 units, far inside the budget.
- Enclosures held while a leaf is walked, 16,777,216 words of 64 bits: the reference's own memory.
- The caches of `ln` and `exp`, 1,024 entries each: they change how the reference finds a value, not the value.
- The first 100 findings and `more_findings`, the item or reason of a finding and the reason of a cell cut at 200 bytes, the reasons of the cells held to 500,000 bytes together, and a waiver printed once in `waived`: they change only what is printed, never a verdict, a cell or its state. This kernel prints every finding whole, and prints no `waived`.

Second change. Applied as well: the name of a case in `cases` that no load has, 64 bytes and no `/` (a shape finding); a need whose numbers would have more than 65,536 bits (a finding of `parts.9`); trying what a rule requires within 4,096 combinations for a rule and 1,000,000 for the deck (a rule past either is read untried); 1,024 orders for each pick of a table whose side a row names, and for a `case`. Steps now follow format.md's five items (H8). This kernel now prints `waived`, each waiver that some cell rests on, once, in the order of the cells.

Left out as well: the work of the needs. format.md, Limits: "A need that cannot pay for a step is a finding of the rule `limits`". The needs are decided with exact fractions and held to 65,536 bits, which bounds them, but in this kernel's own time and not in the reference's units. A design whose needs the reference cannot pay for would be ILL-FORMED there and not here; no bundle comes near (the most `work` any expected.json shows is 45,508,886 units, against 20,000,000,000).

## J. New with the second change

J1. format.md, The deck of rules, and deck.md: "A deck that fails any of these does not load". Not said how many findings a deck that does not load gives. Taken: one finding for each row, type, line of the grid or rule that fails, and none for the rules when a row or a type has failed (the rules are not read then). Bundles decks/kit-ill-formed-22 and decks/kit-ill-formed-34 each damage two rules and expect one finding, for the first. Their verdicts, counts and cells agree; only the findings differ.

J2. format.md, design.json: an argument the exporter cannot write is `{"other": KIND}`, "which the kernel refuses". Not said under which rule, nor whether the part is read on. Taken: a finding of Parts 3 (or 4 or 5, by the field), and the part is kept. Bundle designs/lap-ill-formed-33 expects a shape finding, and then a Parts 5 finding on the lap that joins the part and Parts 6 findings on the givens the part reads, which follow only if the part was left out. Both are ILL-FORMED.

J3. format.md, Steps, the table of weights. It has no row for a name of `let` where a side reads it. Taken: one step of weight 1, as a field's later mention is, while the `let`'s own expression is weighed once ("Every name of `let` is read and weighed once, whether a side reads it or not").

J4. format.md, Steps: "A table with a key that a row names weighs more, since it goes through its cells once for each cell of that row: 1 for each cell of that row that holds a name, and the product of the places it goes through down and across." Not said whether the product is in place of "1 for each cell" or added to it, nor whether "1 for each place down" counts the side's own places or those it goes through. Taken: 1, 1 for each of the side's own places down, the product in place of the cells (it equals the count of cells for a table no row names), 1 for each cell of the naming row that holds a name, and 1 for each entry of a `by`. No bundle comes near the step limit, so no bundle tells the readings apart.

J5. format.md, Types 3 and 4: the exemptions for a field or a load that says `may_be` hold "with `--rules` and `parts`". Not said what holds when the deck of rules does not hold together, so that no type is known. Taken: no exemption, so every size and every input is held to its floor. The damaged decks of bundles/decks expect exactly that: their types.3 and types.4 findings name sizes and inputs that the intact deck exempts.

J6. format.md, The rules: "The kernel applies the rules in this order." Not said in so many words whether a shape or a type finding stops the rules after it. Parts 9 is "applied last, and only to files that break no rule before it", which would need no saying if every rule stopped the next; and Shape says that with a deck that does not hold together "the kernel reads no part". Taken: a file that is not JSON with its format, and a deck that does not hold together, stop the kernel; any other shape or type finding does not, and Parts 1 to 8 are applied after it. Parts 9 is applied only with no finding at all. Code changed. Bundle designs/lap-ill-formed-37 shows a types.3 finding and two parts.3 findings together, as this reading gives.

J7. deck.md, What a type needs: "A quotient divides by a field or by a constant, and by no other expression". Not said whether a constant is a number alone, a `q`, or both. Taken: both, and a constant that is zero is refused.

J8. deck.md, A quantity at or under zero: the table says a `least` beside `"may_be": "negative"` "is under zero, or left out. One at zero or above is refused." The table is for a field ("A field says"). Not said for a load, which may say `may_be: negative` too. Taken: a load's `least` is not held to be under zero.

J9. format.md, The verdict: findings are printed "each with the file and the item". Not said what the item of a finding is, nor which rule a finding of the deck of rules names. Taken: the rule `shape` for a shape finding and for a deck that does not hold together, and an item that names the place in the file, such as `parts[2] rig` with the line in the reason. The bundles name the deck's findings `shape` too, and name a part's findings `PART.FIELD`. Only the text of the findings differs.

J10. format.md, card.json: `cases` holds "The names of the load cases". Not said what an item that is not a text is. Taken: a shape finding, and the item is no load case.
