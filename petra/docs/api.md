# Petra's Python API and `--json` output

This page describes what a program needs to read a check. It covers the calls, the report that `check_file` returns, the verdict and outcome classes, the findings, the repair that names what to change on a FAIL, and the JSON that `petra check --json` prints. A finding gives one obligation's numbers in the design's units. The definitions are in `petra/__init__.py`, `petra/pipeline.py`, `petra/verdict.py`, `petra/readout.py`, and `petra/repair.py`. Where this page and the code disagree, the code is correct.

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

`petra check --json examples/truss_fail.petra` gives the same report as JSON, and so does `petra.check(card, design)`. `report.to_json()` gives it without the `repair` key.

## Check functions

`petra.check(card, design, *, path="<design>", repair=True) -> dict` checks a design against a card, both given as text, with the shipped registry and the solvers. It returns plain data that `json.dumps` takes as it is: the JSON that `petra check --json` prints, described in the JSON section. A FAIL's `repair` key names the inputs that lower the governing check, as Repair describes. With `repair=False`, `repair` is null and the call runs one check. A pair that does not lower returns `{"file": path, "status": "INPUT_ERROR", "error": TEXT}` and does not raise. So does a card whose load or ambient reads a param, which is a family and goes to `petra.certify_family`. `path` is the name that error messages and `file` give the design, and the card's messages say `path` with `.card` in place of `.petra`.

```python
import petra

result = petra.check(open("tab.card", encoding="utf-8").read(), open("tab.petra", encoding="utf-8").read())
if result["status"] == "FAIL":
    move = result["repair"]["moves"][0]
    print(move["direction"], move["input"], "on line", move["line"], "from", move["from"], "to", move["to"])
```

`petra.check_file(path, *, card=None, certs=None, library=None, solve=True) -> Report` loads the design at `path` and its card with the shipped registry and checks the pair. The card is the `.card` file beside the design unless `card` names another. It gathers evidence from these sources, in this order:

1. The certificate store `certs`, a directory.
2. `library`, a `petra.Library`.
3. The solvers, unless `solve=False`.

The kernel checks every piece of evidence. When `certs` is given, `check_file` records accepted evidence there. A syntax error raises `petra.lang.LolaSyntaxError`. A design that cannot be lowered raises `petra.lang.LoweringError` or `petra.models.base.ComponentError`. The CLI reports each of these errors as exit code 3.

`petra.check_design(design, registry, sources, sink=None, deck=None, path="") -> Report` does the same check for a design and registry that you already hold. `petra.parse_design(card, design, path, registry)` and `petra.load_design(path, registry, card=None)` return a design, and `petra.build_registry` returns a registry.

## The card's hash and the kernel

A status is about one card and one design. `hashes` names each by the SHA-256 of its text, so a reader can tell that a PASS was against the card they issued: for a file saved as UTF-8 with LF line ends it is what `sha256sum` prints. `petra check` prints the two on its `card` and `design` lines.

`kernel` is the word of `petra-verify`, the small checker in `kernel/` that is written in Lean. `petra.check` and `petra check` run it on the report when there is one to run: the file the environment variable `PETRA_VERIFY` names, else the one `lake build` put in a source tree's `kernel/`. An installed package carries none yet, and `kernel` is then null. The kernel checks again each proof it has a rule for, and `checked` of `proofs` counts them. For the rest the Python checker's word stands alone, and the kernel's own `verdict` is then UNKNOWN where the status is PASS. A proof the kernel rejects after the Python checker accepted it is a bug in one of the two: `petra.check` raises `petra.verify.Disagreement`, and `petra check` exits 4. `petra.check_file` and `petra.check_design` return the Python checker's report and run no kernel.

## Report

`petra.pipeline.Report` is a frozen dataclass with these fields.

| field | type | meaning |
|---|---|---|
| `design` | `str` | the design's name |
| `path` | `str` | the file the design was read from |
| `verdict` | `Pass \| Fail \| Unknown \| Marginal` | the conjunction of the verdicts of all entries |
| `entries` | `tuple[ClaimVerdict, ...]` | one per claim, in source order, then the `coverage` entry |
| `outcomes` | `tuple[Outcome, ...]` | every requirement's outcome, in elaboration order |
| `warnings` | `tuple[str, ...]` | what the run could not do or match: a waiver that matches no requirement, an evidence source that failed, a certificate it could not record, a margin it did not check |
| `ir` | `petra.ir.Design \| None` | the design that was checked |
| `registry` | `Registry \| None` | the registry the design was checked against |
| `findings` | `tuple[Finding, ...]` | one per outcome, in the same order, computed on first use |
| `governing` | `dict[str, Governing \| None]` | the governing `"strength"` check and the governing `"detailing"` check of the whole report, computed on first use (see The governing checks) |
| `unchecked` | `tuple[Unchecked, ...]` | each mode of a component's domain that no requirement names on that component, with the reason, computed on first use (see What was not checked) |

`report.render()` returns the text that `petra check` prints. Right after its `checked` line, the text has a `governing  strength` line and a `governing  detailing` line. Each line names the requirement and the check, with the check's demand, capacity, and utilisation in the design's units. The strength line reads `none` when no strength check has a utilisation. The detailing line is left out when no detailing check has a utilisation. Each row of the obligation table ends with its finding's utilisation, with `excused` when a guard excuses every term the finding read, or with nothing. The `excused` and `not checked` lines come after the table and its margin lines, as What was not checked describes. `report.to_json()` returns the JSON that the JSON section describes.

## Verdicts

`petra.verdict.STATUS` maps each verdict class to its status string. `SEVERITY` orders the statuses: PASS 0, MARGINAL 1, UNKNOWN 2, FAIL 3. The conjunction of several verdicts takes the most severe one. `petra check` exits with 0 for PASS, 1 for FAIL, 2 for UNKNOWN, and 5 for MARGINAL. All four classes are importable from `petra`.

| class | status | fields |
|---|---|---|
| `petra.Pass` | PASS | `scope` (the params and load cases the proofs hold over), `footprint`, `theorems` |
| `petra.Fail` | FAIL | `obligation` (the first refuted one), `refutation`, `footprint`, `validity` |
| `petra.Unknown` | UNKNOWN | `open` (the `Open` items), `footprint`, `theorems` (those that discharged) |
| `petra.Marginal` | MARGINAL | `near` (the `WithinMargin` items), `footprint`, `theorems`, `scope` |

`footprint.premises` lists every premise that the verdict depends on and that is not proved. Each premise has a `tag`, a `label`, an `owner`, and a `source`. The `tag` is one of `assumed`, `measured`, `sanctioned`, `judged`, `validated_model`, or `certified`. A registry premise, whose label starts with `reg:`, also has a `version`. The `version` is the version of the registry entry that the premise's value came from, which is one more than the number of errata recorded against that entry. `petra registry recall ID` lists the designs whose verdicts depend on an entry. A FAIL's footprint names the premises behind its counterexample.

## Entries

`petra.verdict.ClaimVerdict(claim, verdict, outcomes)` is one entry of a report. `claim` is the claim's name. The requirements that no claim made, which are the coverage rules and the port contracts, form one entry whose `claim` is `"coverage"`, the value of `verdict.COVERAGE_ENTRY`. `verdict` is the entry's own verdict, and `outcomes` are the entry's outcomes.

## Outcomes

Each requirement ends in one of five outcomes. `petra.verdict` defines a class for each.

| class | finding `outcome` | what happened | fields |
|---|---|---|---|
| `Discharged` | `certified` | the kernel proved the obligation | `obligation`, `theorem`, `source`, `margin`, `margin_theorem`, `validity` |
| `Refuted` | `refuted` | the kernel checked a counterexample | `obligation`, `refutation`, `source`, `validity` |
| `WithinMargin` | `marginal` | the claim was proved, but a certified point lies within its margin | `obligation`, `margin`, `refutation`, `source`, `theorem`, `validity` |
| `Waived` | `waived` | a named owner waived the requirement | `requirement`, `waiver` |
| `Open` | `open` | nothing settled it | `requirement`, `needs`, `rejections`, `statement`, `near` |

`obligation.requirement.id` names a requirement as `subject/mode/origin`, for example `tab/steel.bolts/coverage.steel.bolts`. `obligation.statement` is the kernel statement. `refutation.point` gives each symbol of the statement's hypotheses an exact `Fraction` in SI base units. Temperatures are in degC. `verdict.describe_need(n)` turns one of an `Open` item's `needs` into one line of text.

## Findings

`petra.readout.Finding` is tooling. It reads an outcome after the verdict is assembled, and it cannot change the verdict. If a domain reader fails, the finding has no numbers, and its `note` says so.

| field | JSON key | meaning |
|---|---|---|
| `requirement`, `entry`, `outcome`, `rule`, `statement_hash`, `describe` | the same | which obligation this is, and how it ended |
| `category` | `category` | `"strength"` or `"detailing"`, set by the mode (`readout.DETAILING_MODES`) |
| `values` | `checks` | the finding's terms, each a `Value` (described below) |
| `governing` | `governing` (its `what`), `demand`, `capacity`, `unit` | among the terms that no guard excuses, a rule that is not met, else the term with the highest utilisation. None when no term has a utilisation. |
| `utilisation` | `utilisation` | the governing term's utilisation, or None. The JSON gives null when the utilisation is unbounded. |
| `at` | `at` | `"point"` when `values` were evaluated at the counterexample or margin point, `"box"` when they were enclosed over the whole box, or None when nothing was read |
| `claim` | `claim` | `Claimed(claim, quantity, value, bound, unit)`, a claim's quantity where it was read, against its bound |
| `point` | `counterexample` or `margin_point` | the counterexample or margin point, as `Coordinate(symbol, label, exact, si_unit, decimal, unit, varies)` |
| `needs` | `needs` | for an open item, what would settle it |
| `note` | `note` | why some or all terms were not read |

A `Value` is one term. Its fields are `what`, `unit`, `demand`, `capacity`, `excused`, `excuse`, `claimed`, `met`, `parts`, and `utilisation`. `utilisation` is demand / capacity. It is 0 when a guard excuses the term, or when the demand acts the other way, as for a truss member in tension against its buckling resistance. It is infinite for a positive demand against no capacity. `Value.ratio` keeps the sign. `Value.to_json()` gives the term's JSON record. `excuse` is None unless `excused` is true. For an excused term, `excuse` is the condition that excuses the term, with its numbers where the term was read (see What was not checked).

Two fields, `met` and `parts`, apply only to some terms.

- **Rules.** Hole use and joint type are rules, which are either met or not. `DETAILING_MODES` marks them `"rule"`. A rule's demand and capacity are joint levels and counts, not quantities. For a rule, `demand`, `capacity`, `unit`, and `utilisation` are None, and `met` says whether the rule holds. `met` is None for every other term.
- **Parts.** A capacity made of parts lists them in `parts`, weakest first. Only the two bolt group checks of the steel deck have parts: an eccentric group's "C times the weakest bolt", whose capacity is C times its first part's, and "bolt shear, bearing and tearout summed over the group". Each `Part(what, count, limits)` is one row position of the group, such as `"bottom row (1 bolt)"`. Its `limits` are each bolt's strengths at that position, in the check's unit. There is one `Limit(what, capacity)` for the bolt's shear, and one for bearing and one for tearout in each ply. A tearout names its clear distance, as in `"tearout of the tee stem to its edge (lc 0.6875 in)"`. `Part.capacity` is the least of the part's limits, and `Part.governing` is the limit that sets that capacity.

A claim's utilisation compares its quantity with its bound. For `q <= bound`, the governing term's utilisation is q / bound. For `q >= bound`, it is bound / q.

The numbers are in the design's units. The steel deck uses kips, inches, and ksi. Other domains use readable SI units, such as degC, V, A, and kN. Each number is a float, rounded for people to read. The exact value that the kernel checked is `Coordinate.exact`, a `Fraction` in SI base units. Over a box, the demand is the largest value and the capacity is the least value, so the utilisation is an upper bound for every point in the box. The steel deck takes them on the part of the box where the utilisation peaks (`petra/models/steel/calc.py`). It splits the box until the bound lies within 1 part in 2,000 of a utilisation that some point reaches, and on the same side of 1. So a check the kernel proved reads at most 1, unless the split runs out of its 400 cells first.

Some obligations have no single demand and capacity to read. These are the R2 (definiteness), R3 (hypercircle), R5, and R6 statements, and every R1 statement other than a truss's collapse factor. For these obligations, `values` is empty and `note` says why, but `point` is still given. An open item whose model is used outside its validity range is not read either, because that model's numbers say nothing about the design. Its `needs` name the validity row.

### The governing checks

`report.governing` has two keys, and `petra.readout.governing(report.findings)` returns the same dictionary. `"strength"` is the governing strength check, and `"detailing"` is the governing detailing check. Each is chosen from every finding of its category by the same ranking as a finding's `governing`: a rule that is not met first, then the highest utilisation, then the first in report order among equals. Each is a `Governing(category, requirement, value)`, or None when no term of the category has a utilisation.

`readout.DETAILING_MODES` lists the detailing modes: edge distance, spacing, room to tighten, fillet size, the proportions that keep a connection ductile, hole use, and joint type. Every other mode is a strength check, so the governing strength check is never an edge distance.

### What was not checked

A PASS covers the obligations in its table and nothing else. Two kinds of line after the table say where checking stopped. Both come from tooling that reads the report after the verdict, and neither changes the verdict.

**Excused checks.** Some clauses apply only under a condition. The term of such a check carries a guard, and the term holds wherever the formula holds or the guard is <= 0. Where a guard is <= 0 over the whole box, or at the counterexample or margin point, the term is excused. An excused term has `Value.excused` set to true and a utilisation of 0. Its `Value.excuse` gives each guard that excuses it as a condition with its numbers. Both sides of the condition are in the design's units, and the side that names a design input comes first. For example:

```
excused    ff1/steel.web_sidesway_buckling: member web: web sidesway buckling where its slenderness ratio makes it apply (J10.4): ((W14x90.d - (2 * W14x90.kdes)) / W14x90.tw) / (ff1.unbraced_length / W14x90.bf) = 2.604 >= j10_4.restrained_limit + strict.ratio = 2.3
```

A domain reader may word the excuse itself by setting `Value.excuse`. Otherwise, `readout.findings` reads the excuse from the guard in the kernel statement, a term of the form `Min((check, *guards))` as the steel deck builds it. A symbol prints as its last two dotted parts, or in full where two symbols would print alike. A check excused in several load cases prints one line, with its distinct conditions joined by `; `.

**Modes not demanded.** `readout.unchecked(report)`, also available as `report.unchecked`, lists each mode of a component's domain (`KINDS[kind].modes`) that no requirement names on that component. It takes the components in design order and gives each mode as `Unchecked(subject, mode, reason)`. The reason comes from the coverage table and is one of these:

- `"no <field> load is declared; one would demand it"`. The component's kind takes a load `field` that no load case declares on the component. A probe copy of the design, with that load added as zero, makes `coverage.generate` demand the mode. The probe changes nothing that the report demands or decides.
- `readout.CLAIM_ONLY`, `"only a claim demands it; the coverage table never does"`. No coverage rule of the domain lists the mode.
- `readout.NOT_DEMANDED`, `"not demanded by the coverage table"`. A coverage rule can demand the mode but does not demand it for this component, and the table records no reason. The usual cause is the component's attributes or kind.

The text prints one line per reason and set of components. Each line names the modes in id order, and the lines with a load reason come first:

```
not checked  steel.panel_zone on ff1: no panel_shear load is declared; one would demand it
not checked  steel.bearing, steel.block_shear, ... on ff1: not demanded by the coverage table
```

Modes of other domains that a component could meet are not listed, because they belong to the connection, not to the component's domain. A port contract and galvanic corrosion are such modes.

## Repair

`petra.repair` is tooling. It reads a FAIL and never changes a verdict. The governing check of a FAIL is its refuted obligation that ranks first, by the order The governing checks describes. A site is a number written on a component's line, outside any bound or tuple. A load is never a site, because its owner signed it.

For each site, `repair` tries one step up and one step down and checks each edited design. A step is the smallest edit that the design accepts:

- A count, such as `rows 3`, steps by 1.
- A length in inches steps by 1/16 in.
- Any other number steps by a tenth of its leading digit's place, so 30 m steps by 1 m.
- An edit that the language or the domain refuses is not a step. Examples are a plate thickness that the shop deck does not stock and a bolt diameter that RCSC Table 5.2 does not list. The search walks on to the next value.

A move is a step that lowers the governing check's utilisation. Moves come sorted by that utilisation, so the first move lowers the check the most. For the first three moves, `repair` also searches outward in the move's direction for a value at which the check is certified. It doubles the step until the check holds, then halves the gap. The move's `clears` gives that value and the design's status there, or null when the search found none within 64 steps.

A move changes one number. The design's status after a move can still be FAIL on another check, and `fails` names those checks. On a FAIL, a check runs one design for each site and direction, plus up to about 40 more for the `clears` searches, so it takes a few seconds.

When no single number lowers the check, `repair` tries swaps instead. A swap puts another shape of the same family on an `angles`, `angle`, `top_angle` or `tee` line: any angle in the shapes table for an angle, and any tee cut from one of its W shapes for a tee. The moves are then the swaps that lower the check, with the ones that leave the fewest failed checks first. A swap's `clears` is the swap itself when the check holds there. A rule that neither a number nor a swap fixes, such as a slip-critical joint's hole type, gives an empty `moves`.

`petra check` prints the first three moves after the governing lines:

```
repair     tab/steel.bolts at utilisation 2.02; each move lowers it, the first the most:
  increase  tab.rows (line 19) from 3 to 4: utilisation 1.31; it holds at 5, where the design is FAIL on tab/steel.beam_fit
  increase  tab.bolts diameter (line 18) from 0.75 to 0.875 inch: utilisation 1.79
  decrease  tab.bolt_line (line 23) from 3 to 2.9375 inch: utilisation 1.99
```

With `--no-solve`, `petra check` computes no repair.

## JSON

`petra check --json FILE` prints one object with sorted keys. In the shape below, an upper-case name is a placeholder, a key followed by `?` may be absent, and text to the right of a line describes it.

```
{"file": FILE, "design": NAME, "status": "PASS" | "FAIL" | "UNKNOWN" | "MARGINAL",
 "card": FILE,                                 the card the design was checked against
 "hashes": {"card": HASH, "design": HASH},     "sha256:HEX" of each text as UTF-8 with LF line ends
 "kernel": KERNEL | null,                      the kernel's word; null when no kernel ran
 "governing": {"strength": GOVERNING | null, "detailing": GOVERNING | null},
 "verdicts": [ENTRY, ...],                     one per claim, then "coverage"
 "unchecked": [UNCHECKED, ...],                each mode of a component's domain no requirement names, design order
 "repair": REPAIR | null}                      a FAIL's moves; null for any other status

KERNEL = {"verdict": "PASS" | "FAIL" | "UNKNOWN",   the kernel's own verdict on the files it read
          "checked": N,                        the proofs and refutations the kernel checked and accepted
          "proofs": N,                         the proofs and refutations the status rests on
          "hashes": {"card", "design", "deck"}}   of the JSON files the kernel read (docs/format.md)

REPAIR = {"check": REQUIREMENT,                the governing check: the refuted obligation that ranks first
          "utilisation": NUMBER | null,        its utilisation
          "moves": [MOVE, ...]}                the steps that lower it, the one that lowers it most first, or the swaps

MOVE = {"input": NAME,                         "<component>.<key>", with the word before the number, as "tab.plate thickness"
        "line": N, "from": NUMBER TEXT,        where the number (or a swap's shape) is written, and it as written
        "unit": UNIT | null,                   the unit written after it; null for a swap
        "direction": "increase" | "decrease" | "swap",
        "to": NUMBER TEXT,                     the step, written as the design writes numbers, or the swap's shape
        "utilisation": NUMBER | null,          the governing check's after the step
        "status": STATUS, "fails": [REQUIREMENT, ...],   the design's after the step, and its refuted checks
        "clears": {"to", "utilisation", "status", "fails"} | null}   a value at which the check holds; first three moves only

UNCHECKED = {"subject": NAME, "mode": MODE, "reason": TEXT}   see What was not checked

GOVERNING = {"requirement", **CHECK}           the report's governing check of that category

ENTRY = {"claim": NAME, "status": STATUS,
         "rules": ["R1", ...],                 the rules of the kernel results the verdict used
         "footprint": [{"tag", "label", "owner", "source", "version"?}, ...],
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
         "excuse": TEXT | null,                the condition that excuses it, with its numbers; null unless excused
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

The JSON leaves out the source of each piece of evidence, so that a report replayed from stored certificates prints the same JSON as the run that found them. That source is the solver, the certificate store, or the library.

The example below is the bolts obligation of the 60 kip shear tab in `tests/fixtures/readout/job5_fail_60k.petra`, cut down to one part of the bolt group and one fixed coordinate. Here bolt shear sets every bolt's strength, so the bolt group needs more or larger bolts, not more edge distance. The group holds C = 2.48 times its weakest bolt, by the instantaneous center at Table 10-9's e = a/2.

```json
{"requirement": "tab/steel.bolts/coverage.steel.bolts", "entry": "coverage", "category": "strength", "outcome": "refuted", "rule": "R4",
 "statement_hash": "sha256:b9be510498ee6ee6b5c84332337eaf755889fb55bf85620479ff4da28b07e446",
 "describe": "tab (shear_tab) holds every bolts check under reaction: beam side: the eccentric group by the instantaneous center or the elastic method, C times the weakest bolt (J3.7, J3.11a, Manual Part 7)",
 "at": "point",
 "governing": "beam side: the eccentric group by the instantaneous center or the elastic method, C times the weakest bolt (J3.7, J3.11a, Manual Part 7)",
 "demand": 60.0, "capacity": 44.39425071742194, "unit": "kip", "utilisation": 1.3515263582645352,
 "checks": [{"check": "beam side: the eccentric group by the instantaneous center or the elastic method, C times the weakest bolt (J3.7, J3.11a, Manual Part 7)",
             "demand": 60.0, "capacity": 44.39425071742194, "unit": "kip", "utilisation": 1.3515263582645352,
             "excused": false, "excuse": null, "met": null,
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

`petra envelope FILE --input NAME --from LO --to HI` finds the widest interval of one input over which every obligation that depends on that input is proved. `petra/envelope.py` holds the search and its report, in `envelope`, `render`, and `to_json`. Without `--at`, the search starts from the middle of the input's stated range. If the design does not pass there, the search starts again from the low end of the probe range. The text output prints values in the unit of `--from`, and `--json` prints exact rationals in SI base units.
