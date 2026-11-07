# Petra's Python API and `--json` output

This page covers what a program needs to read a check: the call, the report it returns, the verdict and outcome classes, the findings (each obligation's numbers in the design's units), and the JSON that `petra check --json` prints. `petra/__init__.py`, `petra/pipeline.py`, `petra/verdict.py` and `petra/readout.py` hold the definitions. If this page and the code disagree, the code is right.

## Example

```python
import petra

report = petra.check_file("examples/truss_fail.petra")
print(type(report.verdict).__name__)               # Fail
strength = report.governing["strength"]            # the highest utilisation of any strength check
print(strength.requirement, strength.value.what, strength.value.utilisation)
for f in report.findings:
    print(f.requirement, f.category, f.outcome, f.utilisation)
    if f.outcome == "refuted":
        g = f.governing
        print("  ", g.what, g.demand, g.capacity, g.unit, round(g.utilisation, 2))
        for c in f.point:
            if c.varies:
                print("  at", c.symbol, "=", c.shown, "exact", c.exact, c.si_unit)
```

The same report as data comes from `petra check --json examples/truss_fail.petra`, or from `json.dumps(report.to_json())`.

## Checking a design

`petra.check_file(path, *, certs=None, library=None, solve=True) -> Report` loads a `.petra` file with the shipped registry and checks it. It gathers evidence in the order certificate store (`certs`, a directory), then `library` (a `petra.Library`), then the solvers (unless `solve=False`). The kernel checks every piece of evidence. Accepted evidence is written to `certs` when you give it. A syntax error raises `petra.lang.LolaSyntaxError`, and a design that cannot be lowered raises `petra.lang.LoweringError` or `petra.models.base.ComponentError`. The CLI reports each of these as exit code 3.

`petra.check_design(design, registry, sources, sink=None, deck=None, path="") -> Report` is the same thing for a design and registry you already hold. `petra.parse_design`, `petra.load_design` and `petra.build_registry` make those.

## Report

`petra.pipeline.Report` is a frozen dataclass with these fields.

| field | type | meaning |
|---|---|---|
| `design` | `str` | the design's name |
| `path` | `str` | the file it was read from |
| `verdict` | `Pass \| Fail \| Unknown \| Marginal` | the conjunction over every entry |
| `entries` | `tuple[ClaimVerdict, ...]` | one per claim, in source order, then the `coverage` entry |
| `outcomes` | `tuple[Outcome, ...]` | every requirement's outcome, in elaboration order |
| `warnings` | `tuple[str, ...]` | what the run could not do or match: a waiver that matches no requirement, an evidence source that failed, a certificate it could not record, a margin it did not check |
| `ir` | `petra.ir.Design \| None` | the design that was checked |
| `registry` | `Registry \| None` | the registry it was checked against |
| `findings` | `tuple[Finding, ...]` | one per outcome, in the same order, computed on first use |
| `governing` | `dict[str, Governing \| None]` | the governing `"strength"` check and the governing `"detailing"` check of the whole report, computed on first use (see Findings) |

`report.render()` returns the text `petra check` prints. Right after its `checked` line come the lines `governing  strength` and `governing  detailing`, each naming the requirement, the check, its demand, capacity and utilisation in the design's units. The strength line reads `none` when no strength check has a utilisation, and the detailing line is left out when no detailing check has one. Each row of the obligation table ends with its finding's utilisation, or with nothing when it has none. `report.to_json()` returns the JSON described below.

## Verdicts

`petra.verdict.STATUS` maps each class to its status string. `SEVERITY` orders the statuses. The conjunction of several verdicts takes the most severe one: PASS 0, MARGINAL 1, UNKNOWN 2, FAIL 3. `petra check` exits with 0 for PASS, 1 for FAIL, 2 for UNKNOWN and 5 for MARGINAL. All four classes are importable from `petra`.

| class | status | fields |
|---|---|---|
| `petra.Pass` | PASS | `scope` (the params and load cases the proofs hold over), `footprint`, `theorems` |
| `petra.Fail` | FAIL | `obligation` (the first refuted one), `refutation`, `footprint`, `validity` |
| `petra.Unknown` | UNKNOWN | `open` (the `Open` items), `footprint`, `theorems` (those that discharged) |
| `petra.Marginal` | MARGINAL | `near` (the `WithinMargin` items), `footprint`, `theorems`, `scope` |

`footprint.premises` lists every premise that is not proved and that the verdict rests on. Each premise has a `tag` (`assumed`, `measured`, `sanctioned`, `judged`, `validated_model` or `certified`), a `label`, an `owner` and a `source`. A FAIL's footprint names the premises behind its counterexample.

## Entries

`petra.verdict.ClaimVerdict(claim, verdict, outcomes)` is one entry of a report. `claim` is the claim's name, or `"coverage"` (`verdict.COVERAGE_ENTRY`) for the requirements no claim made, which are the coverage rules and port contracts. `verdict` is the entry's own verdict, and `outcomes` are the entry's outcomes.

## Outcomes

Each requirement ends as one of five outcome classes, all defined in `petra.verdict`.

| class | finding `outcome` | what happened | fields |
|---|---|---|---|
| `Discharged` | `certified` | the kernel proved the obligation | `obligation`, `theorem`, `source`, `margin`, `margin_theorem`, `validity` |
| `Refuted` | `refuted` | the kernel checked a counterexample | `obligation`, `refutation`, `source`, `validity` |
| `WithinMargin` | `marginal` | the claim was proved, but a certified point lies within its margin | `obligation`, `margin`, `refutation`, `source`, `theorem`, `validity` |
| `Waived` | `waived` | a named owner waived the requirement | `requirement`, `waiver` |
| `Open` | `open` | nothing settled it | `requirement`, `needs`, `rejections`, `statement`, `near` |

`obligation.requirement.id` names a requirement as `subject/mode/origin`, for example `tab/steel.bolts/coverage.steel.bolts`. `obligation.statement` is the kernel statement. `refutation.point` gives each symbol of the statement's hypotheses an exact `Fraction` in SI base units, with temperatures in degC. `verdict.describe_need(n)` turns each of an `Open` item's `needs` into one line of text.

## Findings

`petra.readout.Finding` is tooling. It reads an outcome after the verdict is assembled and cannot change it. If a domain reader fails, the finding loses its numbers and says so in `note`.

| field | JSON key | meaning |
|---|---|---|
| `requirement`, `entry`, `outcome`, `rule`, `statement_hash`, `describe` | the same | which obligation this is, and how it ended |
| `category` | `category` | `"strength"` or `"detailing"`, by the mode (`readout.DETAILING_MODES`) |
| `values` | `checks` | its terms, each a `Value` (below) |
| `governing` | `governing` (its `what`), `demand`, `capacity`, `unit` | the term no guard excuses with the highest utilisation, or a rule that is not met; None when no term has a utilisation |
| `utilisation` | `utilisation` | the governing term's utilisation, or None. JSON gives null when it is unbounded. |
| `at` | `at` | `"point"` when `values` were evaluated at the counterexample or margin point, `"box"` when they were enclosed over the whole box, None when nothing was read |
| `claim` | `claim` | `Claimed(claim, quantity, value, bound, unit)`: a claim's quantity where it was read, against its bound |
| `point` | `counterexample` or `margin_point` | the counterexample or margin point, as `Coordinate(symbol, label, exact, si_unit, decimal, unit, varies)` |
| `needs` | `needs` | for an open item, what would settle it |
| `note` | `note` | why some or all terms were not read |

A `Value` is one term: `what`, `unit`, `demand`, `capacity`, `excused`, `claimed`, `met`, `parts` and `utilisation`, which is demand / capacity, 0 when a guard excuses the term or the demand acts the other way (a truss member in tension against its buckling resistance), and infinite for a positive demand against no capacity. `Value.ratio` keeps the sign. `Value.to_json()` gives the term's JSON record.

- **Rules.** Hole use and joint type are rules, met or not (`DETAILING_MODES` marks them `"rule"`). Their demand and capacity are joint levels and counts, not quantities, so `demand`, `capacity`, `unit` and `utilisation` are None, and `met` says whether the rule holds. `met` is None for every other term.
- **Parts.** A capacity made of parts lists them in `parts`, weakest first. Today these are the two bolt group checks of the steel deck, "most loaded bolt ... against the weakest bolt" and "bolt shear, bearing and tearout summed over the group". Each `Part(what, count, limits)` is one row position of the group, such as `"bottom row (1 bolt)"`. Its `limits` are each bolt's strengths there: `Limit(what, capacity)` for its shear and for its bearing and tearout in each ply, in the check's unit. A tearout names its clear distance, as in `"tearout of the tee stem to its edge (lc 0.6875 in)"`. `Part.capacity` is the least of its limits, and `Part.governing` is the limit that sets it.

A claim's utilisation is its quantity against its bound: for `q <= bound` the governing term's utilisation is q / bound, and for `q >= bound` it is bound / q.

The numbers are in the design's units: kips, inches and ksi for the steel deck, and readable SI elsewhere (degC, V, A, kN). Each number is a float rounded for people. The exact value the kernel checked is `Coordinate.exact`, a `Fraction` in SI base units. Over a box, the demand is the largest value and the capacity the least, so the utilisation is an upper bound for every point in the box.

Some obligations have no single demand and capacity to read. These are R2 (definiteness), R3 (hypercircle), R5 and R6 statements, and R1 statements other than a truss's collapse factor. For those, `values` is empty and `note` says why. The point is still given.

### The governing checks

`report.governing` (or `petra.readout.governing(report.findings)`) has two keys. `"strength"` is the governing strength check and `"detailing"` the governing detailing check. Each is ranked as a finding's `governing` is, over every finding of that category: a rule that is not met first, then the highest utilisation, the first in report order among equals. Each is a `Governing(category, requirement, value)`, or None when no term of the category has a utilisation. Detailing means edge distance, spacing, room to tighten, fillet size, the proportions that keep a connection ductile, hole use and joint type (`readout.DETAILING_MODES`). Every other mode is a strength check, so the governing strength check is never an edge distance.

## JSON

`petra check --json FILE` prints a single object, with keys sorted.

```
{"file": FILE, "design": NAME, "status": "PASS" | "FAIL" | "UNKNOWN" | "MARGINAL",
 "governing": {"strength": GOVERNING | null, "detailing": GOVERNING | null},
 "verdicts": [ENTRY, ...]}                     one per claim, then "coverage"

GOVERNING = {"requirement", **CHECK}           the report's governing check of that category

ENTRY = {"claim": NAME, "status": STATUS,
         "rules": ["R1", ...],                 the rules of the kernel results the verdict used
         "footprint": [{"tag", "label", "owner", "source"}, ...],
         "needs": [TEXT, ...],                 what each open item needs; non-empty iff UNKNOWN
         "margins": [{"requirement", "proved", "margin": "proved" | "undecided" | "within",
                      "point"?: {SYMBOL: EXACT}}, ...],     claims with a margin
         "obligations": [OBLIGATION, ...]}     one per outcome of the entry

OBLIGATION = {"requirement", "entry", "describe",
              "category": "strength" | "detailing",
              "outcome": "certified" | "refuted" | "marginal" | "waived" | "open",
              "rule": "R4" | ... | null, "statement_hash": "sha256:..." | null,
              "at": "point" | "box" | null,
              "governing": NAME | null, "demand", "capacity": NUMBER | null,   null for a rule
              "unit": UNIT | null,                   null: SI base units, dimension unknown, or a rule
              "utilisation": NUMBER | null,          null when unbounded, for a rule, or with no term read
              "checks": [CHECK, ...],
              "claim": {"claim", "quantity", "value", "bound", "unit"} | null,
              "counterexample": [COORDINATE, ...] | null,   for "refuted"
              "margin_point": [COORDINATE, ...] | null,     for "marginal", or "open" with a margin point
              "needs": [TEXT, ...], "note": TEXT | null}

CHECK = {"check": NAME, "demand", "capacity": NUMBER | null,   null for a rule
         "unit": UNIT | null, "utilisation": NUMBER | null, "excused": true | false,
         "met": true | false | null,           a rule's outcome; null for any other check
         "parts": [PART, ...]}                 what a bolt group's capacity is made of, weakest first; else []

PART = {"part": NAME, "count": N,              a row position of a bolt group and how many bolts sit there
        "capacity": NUMBER, "governing": NAME, each bolt's strength there, and the limit that sets it
        "limits": [{"limit": NAME, "capacity": NUMBER}, ...]}   its shear, and its bearing and tearout in each ply

COORDINATE = {"symbol", "label",
              "value": DECIMAL TEXT, "unit": UNIT | null,   in the design's unit; "~" marks a rounded decimal
              "exact": "p/q", "si_unit": UNIT | null,       the kernel's exact rational, SI base units
              "varies": true | false}                       true: the statement lets it range
```

The JSON deliberately omits where each piece of evidence came from (solver, certificate store or library). A report replayed from stored certificates therefore prints the same JSON as the run that found them.

Here is the bolts obligation of the 60 kip shear tab in `tests/fixtures/readout/job5_fail_60k.petra`, cut down to one part of the bolt group and one fixed coordinate. Every bolt's strength is set by bolt shear here, so the bolt group needs more or larger bolts, not more edge distance:

```json
{"requirement": "tab/steel.bolts/coverage.steel.bolts", "entry": "coverage", "category": "strength", "outcome": "refuted", "rule": "R4",
 "statement_hash": "sha256:967688885e06a51cbc60952fbc87219edb7b531f98916adcfc509a0266cdfc92",
 "describe": "tab (shear_tab) holds every bolts check under reaction: beam side: most loaded bolt by the elastic method against the weakest bolt (J3.7, J3.11a)",
 "at": "point",
 "governing": "beam side: most loaded bolt by the elastic method against the weakest bolt (J3.7, J3.11a)",
 "demand": 36.05551275463989, "capacity": 17.89235190989812, "unit": "kip", "utilisation": 2.015135457664112,
 "checks": [{"check": "beam side: most loaded bolt by the elastic method against the weakest bolt (J3.7, J3.11a)",
             "demand": 36.05551275463989, "capacity": 17.89235190989812, "unit": "kip", "utilisation": 2.015135457664112,
             "excused": false, "met": null,
             "parts": [{"part": "top row (1 bolt)", "count": 1, "capacity": 17.89235190989812, "governing": "bolt shear",
                        "limits": [{"limit": "bolt shear", "capacity": 17.89235190989812},
                                   {"limit": "bearing on the plate", "capacity": 29.3625},
                                   {"limit": "tearout of the plate to the next hole (lc 2.188 in)", "capacity": 42.8203125},
                                   {"limit": "bearing on the beam web", "capacity": 24.13125},
                                   {"limit": "tearout of the beam web to its edge (lc 2.594 in)", "capacity": 41.726953125}]}]}],
 "claim": null,
 "counterexample": [
   {"symbol": "reaction.tab.shear", "label": "in:job5-shear-tab-60k.reaction.tab.shear", "value": "60", "unit": "kip",
    "exact": "26689329691563/100000000", "si_unit": "N", "varies": true},
   {"symbol": "bolt_group.120.Fnv_N", "label": "reg:bolt_group.120.Fnv_N", "value": "54", "unit": "ksi",
    "exact": "240203967224067/645160", "si_unit": "Pa", "varies": false}],
 "margin_point": null, "needs": [], "note": null}
```

## Envelopes

`petra envelope FILE --input NAME --from LO --to HI` finds the widest interval of one input over which every obligation that depends on it is proved. The search and its report live in `petra/envelope.py` (`envelope`, `render`, `to_json`). Without `--at`, the search starts from the middle of the input's stated range. If the design does not pass there, the search starts again from the low end of the probe range. The text prints values in the unit of `--from`, and `--json` prints exact rationals in SI base units.
