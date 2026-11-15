# Petra's Python API and `--json` output

Petra checks a design against a card and a deck of rules. The card, `NAME.card`, holds what is asked: the loads, the signed bounds and the waivers. The design, `NAME.petra`, holds the parts. The answer is the verdict of `petra-verify`, a small kernel written in Lean. Nothing in Python gives a verdict.

## Example

```python
import petra

card = open("lap.card", encoding="utf-8").read()
design = open("lap.petra", encoding="utf-8").read()

result = petra.check(card, design)
print(result["status"])                  # PASS, PASS_WAIVED, FAIL, UNKNOWN or INPUT_ERROR
for cell in result.get("cells", []):
    print(cell["subject"], cell["mechanism"], cell["state"], cell["ratio"])

checked = petra.check_file("lap.petra")  # reads lap.card beside it
print(checked.text())                    # what `petra check` prints
```

## Check functions

`petra.check(card, design, *, path="<design>")` takes the two texts and returns a dict that `json.dumps` takes as it is. It is what `petra check --json` prints. A pair that is refused gives `{"file", "status": "INPUT_ERROR", "error"}` and raises nothing.

`petra.check_file(path, *, card=None)` reads the design at `path` and the card, which is the `.card` file beside the design unless `card` names another. It returns the checked pair, with these members:

| Member | Holds |
|---|---|
| `status` | The kernel's verdict: PASS, PASS_WAIVED, FAIL or UNKNOWN |
| `reason` | For a design with a part of a kind no deck has, why it reads UNKNOWN. Otherwise `None` |
| `kernel` | What the kernel said: its verdict, the hashes of the files it read and the waivers it lists |
| `hashes` | The SHA-256 of the card's text and of the design's |
| `to_json()` | The dict `petra.check` returns |
| `text()` | What `petra check` prints |
| `report` | For a design of a deck, the Python reader's cells, which word the report and decide nothing |

`check_file` raises what the pair raises when it is refused: `petra.lang.LolaSyntaxError`, `petra.lang.LoweringError`, `petra.files.ComponentError` or `OSError`.

Both functions raise `petra.verify.NoVerdict` when there is no verdict to give. See the next section.

## The kernel

`status` is the verdict of `petra-verify`, the checker in `kernel/`. Petra runs the file the environment variable `PETRA_VERIFY` names, else the one inside the installed package, else the one `lake build` put in a source tree's `kernel/`. A wheel from PyPI carries the kernel for its platform, and Petra installed from the sdist carries none.

With no kernel to run, there is no verdict. The same holds for a kernel whose exit code or error stream is at odds with what it printed, or whose answer does not hold together ([format.md](../../docs/format.md), the first section). Then `petra.check` raises `petra.verify.NoVerdict`, `petra check` prints nothing to stdout and exits 4, and the server's `check` tool answers with an error.

The kernel reads the deck's own file and works out every cell itself. The Python reader works the same cells out to word the report and to search for hints of proofs. `petra.check` compares the two, cell by cell, and raises `petra.verify.Disagreement` if they differ. That is a bug in one of the two, and `petra check` exits 4 with a traceback.

## The hashes

A status is about one card and one design. `hashes` names each by the SHA-256 of its text, so a reader can tell that a PASS was against the card they issued. For a file saved as UTF-8 with LF line ends it is what `sha256sum` prints. `petra check` prints the two on its `card` and `design` lines. `kernel.hashes` names the files the kernel read: `card.json`, `design.json`, `deck.json` and `rules.json`, as [format.md](../../docs/format.md) describes them.

## JSON of a design checked against a deck

`petra kinds` lists each shipped deck and its types. A design whose parts are of a deck's types is checked against that deck's grid: every mechanism the deck asks about, for every part, under every load case. `docs/deck.md` in the repository describes a deck and the states of a cell.

```
{"file": FILE, "design": NAME, "status": "PASS" | "PASS_WAIVED" | "FAIL" | "UNKNOWN",
 "deck": {"name": NAME, "hash": "sha256:HEX"},
 "counts": {"proved": N, "refuted": N, "not_applicable": N, "waived": N, "open": N},
 "cells": [CELL, ...],                         one per answer, in the order of the grid
 "waived": [WAIVER, ...],                      each waiver a cell rests on, once, in the order of the cells
 "card": FILE, "hashes": {"card": HASH, "design": HASH},
 "path": "rules",                              the kernel worked out the cells from the rules deck
 "kernel": {"verdict": "PASS" | "FAIL" | "UNKNOWN", "checked": N, "cells_from": "rules",
            "waived": [WAIVER, ...], "hashes": {...}}}

WAIVER = {"subject": PART, "mechanism": NAME, "by": SIGNER, "reason": TEXT}

CELL = {"subject": PART, "mechanism": NAME, "entry": TEXT,
        "state": "proved" | "refuted" | "not_applicable" | "waived" | "open",
        "what": TEXT,                          what the rule states, or what the grid asks
        "anchor": TEXT,                        the clause
        "why": TEXT,                           for an open, a not applicable and a waived cell
        "rule": ID | null,
        "ratio": NUMBER | null,                the left side of the rule over the right, at its worst
        "completion": COMPLETION}              only for a waived cell that rests on one

COMPLETION = {"keys": [[PART, FIELD, NAME], ...], "loads": [[PART, LOAD, CASE, RATIONAL, UNIT], ...]}
```

The verdict is FAIL with a refuted cell, UNKNOWN with an open cell or with nothing proved, and else PASS.

The status is PASS_WAIVED when the design passes and a waiver of the card rests one of its cells. The design passes what the deck could check, and each signer answers for the cells its waiver rests. `petra check` exits 6 for it. The kernel has no word of its own for this: it says PASS and lists the waivers, and the status is read from that list.

A waived cell that a part or a case left something out of rests on a completion: a name for each key left unstated and a value for each load left out, under which the rule holds. The value is in SI and UNIT names its unit, as the kernel's verdict prints it: `degC` for a temperature, `1` for a plain number, and the exponents of the dimension, as `kg^1 s^-2`, where no unit of factor 1 has it. The signer answers for the completion too, so the cell prints it.

`ratio` is worked out by the Python reader. It is not the kernel's.

## JSON of a design no deck has

A design with a part of a kind no shipped deck has cannot be checked: there is no rule to check it by. The kernel is handed its card and its quantities with no deck of rules. It holds them to the type rules, works out no cell, and gives UNKNOWN.

```
{"file": FILE, "design": NAME, "status": "UNKNOWN",
 "reason": TEXT,                               which kinds of part no deck has
 "kinds": [KIND, ...],
 "deck": null, "cells": [], "waived": [],
 "card": FILE, "hashes": {"card": HASH, "design": HASH},
 "path": "none",
 "kernel": {"verdict": "UNKNOWN", "checked": 0, "cells_from": "proofs", "waived": [], "hashes": {...}}}
```

A design with parts of a deck's types and parts of another kind is refused.

## Exit codes of `petra check`

| Status | Code |
|---|---|
| PASS | 0 |
| FAIL | 1 |
| UNKNOWN | 2 |
| INPUT_ERROR | 3 |
| No verdict, or a crash | 4 |
| PASS_WAIVED | 6 |

## Other modules

Everything below is untrusted: a bug in it costs an input error, an UNKNOWN or a difference from the kernel, never a pass.

| Module | Holds |
|---|---|
| `petra.lang` | `parse_design(card, design, path)` and `load_design(path)`: the two texts as one parsed design |
| `petra.grid` | The Python reader of a deck's grid: `decks()`, `kinds()`, `check(design, deck)` |
| `petra.rule` | Reads a deck's types, grid and rules, and runs an acceptance of a rule |
| `petra.deck` | Reads a deck's rows: tables and constants |
| `petra.export` | Writes the files the kernel reads: `python -m petra.export FILE.petra --out DIR` |
| `petra.verify` | Finds and runs the kernel, and takes its answer |
| `petra.teach` | What `petra kinds`, `petra new` and `petra docs` print |
