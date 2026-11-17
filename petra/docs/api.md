# Petra's Python API and `--json` output

Petra checks a design against a card and a deck of rules. The card, `NAME.card`, holds what is asked: the deck of rules, by the hash of its file, the loads, the signed bounds and the waivers. The design, `NAME.petra`, holds the parts. The answer is the verdict of `petra-verify`, a small kernel written in Lean. No function here gives a pass or a fail of its own.

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
| `status` | The kernel's verdict: PASS, PASS_WAIVED, FAIL or UNKNOWN. For a design no deck has it is UNKNOWN, and the kernel is not asked |
| `reason` | For a design no deck has, why it reads UNKNOWN. Otherwise `None` |
| `kernel` | What the kernel said: its verdict, the hashes of the files it read, one hash of them all and the waivers it lists. `None` for a design no deck has, which the kernel is not asked about |
| `hashes` | The SHA-256 of the card's text and of the design's |
| `to_json()` | The dict `petra.check` returns |
| `text()` | What `petra check` prints |
| `report` | For a design of a deck, the Python reader's cells, which word the report and decide nothing |

`check_file` raises what the pair raises when it is refused: `petra.lang.LolaSyntaxError`, `petra.lang.LoweringError`, `petra.files.ComponentError` or `OSError`.

For a design of a deck, both functions raise `petra.verify.NoVerdict` when there is no verdict to give. See the next section.

## The kernel

For a design of a deck, `status` is the verdict of `petra-verify`, the checker in `kernel/`. Petra runs the file the environment variable `PETRA_VERIFY` names, else the one inside the installed package, else the one `lake build` put in a source tree's `kernel/`. A wheel from PyPI carries the kernel for its platform, and Petra installed from the sdist carries none.

With no kernel to run, there is no verdict of a design of a deck. The same holds for a kernel whose exit code or error stream is at odds with what it printed, or whose answer does not hold together ([format.md](../../docs/format.md), the first section). Then `petra.check` raises `petra.verify.NoVerdict`, `petra check` prints nothing to stdout and exits 4, and the server's `check` tool answers with an error.

The kernel reads the deck's own file and works out every cell itself. The Python reader works the same cells out to word the report and to search for hints of proofs. `petra.check` compares the two, cell by cell, and raises `petra.verify.Disagreement` if they differ. That is a bug in one of the two, and `petra check` exits 4 with a traceback.

## The hashes

A status is about one card and one design. `hashes` names each by the SHA-256 of its text, so a reader can tell that a PASS was against the card they issued. For a file saved as UTF-8 with LF line ends it is what `sha256sum` prints. `petra check` prints the two on its `card` and `design` lines. The card names the deck of rules by the hash of its file, and a pair whose card names another deck, or none, is refused, so the card's hash also says which rules. `kernel.hashes` names the files the kernel read: `card.json`, `design.json`, `deck.json`, `rules.json`, `run.json` and `proofs.json`, as [format.md](../../docs/format.md) describes them, and `kernel.bundle` is one hash of the six. `petra check` prints the hash of the run on its `run` line and the bundle on its `bundle` line.

## JSON of a design checked against a deck

`petra kinds` lists each shipped deck and its types, with the line a card writes to name the deck. A design whose parts are of a deck's types is checked against that deck's grid: every mechanism the deck asks about, for every part, under every load case. `docs/deck.md` in the repository describes a deck and the states of a cell.

```
{"file": FILE, "design": NAME, "status": "PASS" | "PASS_WAIVED" | "FAIL" | "UNKNOWN",
 "deck": {"name": NAME, "hash": "sha256:HEX"},
 "counts": {"proved": N, "refuted": N, "not_applicable": N, "waived": N, "open": N},
 "cells": [CELL, ...],                         one per answer, in the order of the grid
 "waived": [WAIVER, ...],                      each waiver a cell rests on, once, in the order of the cells
 "card": FILE, "hashes": {"card": HASH, "design": HASH},
 "path": "rules",                              the kernel worked out the cells from the rules deck
 "kernel": {"verdict": "PASS" | "FAIL" | "UNKNOWN", "checked": N, "cells_from": "rules",
            "waived": [WAIVER, ...], "hashes": {...}, "bundle": HASH}}

WAIVER = {"subject": PART, "mechanism": NAME, "by": SIGNER, "reason": TEXT}

CELL = {"subject": PART, "mechanism": NAME, "entry": TEXT,
        "state": "proved" | "refuted" | "not_applicable" | "waived" | "open",
        "what": TEXT,                          what the rule states, or what the grid asks
        "anchor": TEXT,                        the clause
        "why": TEXT,                           the reason, or "" for a cell with none
        "rule": ID | null,
        "ratio": NUMBER | null,                the left side of the rule over the right, at its worst
        "stated": true,                        only for a cell that reads no quantity
        "completion": COMPLETION}              only for a waived cell that rests on one

COMPLETION = {"keys": [[PART, FIELD, NAME], ...], "loads": [[PART, LOAD, CASE, RATIONAL, UNIT], ...]}
```

The verdict is FAIL with a refuted cell. With none refuted it is UNKNOWN with an open cell or with no cell that was worked out, and else PASS. A cell was worked out when its `state` is `proved`, it has no `stated`, and its `entry` does not end in `/where`.

`why` holds a reason for an open, a waived and a not applicable cell, for a refuted cell of a rule that requires, and for a proved cell marked `stated`. On a not applicable cell it is the reason the deck gives for excusing the line. Any other cell has the empty text.

`stated` marks a cell for which nothing is worked out: every cell of a rule that requires something of the keys, and a proved or refuted cell of an inequality that reads no quantity of the part or of the card. The mark goes by what the inequality reads, and not by whether it turns on it: a rule that reads a quantity and does not turn on it, as nought times a span, has a cell with no mark. It is `true` or left out. `petra check` prints `stated` in place of `proved` for such a cell, and a design whose proved cells are all marked so, or prove only a rule's range, reads UNKNOWN.

The status is PASS_WAIVED when the design passes and a waiver of the card rests one of its cells. The design passes what the deck could check, and each signer answers for the cells its waiver rests. `petra check` exits 6 for it. The kernel has no word of its own for this: it says PASS and lists the waivers, and the status is read from that list.

A waived cell that a part or a case left something out of rests on a completion: a name for each key left unstated and a value for each load left out, under which the rule holds. The value is in SI and UNIT names its unit, as the kernel's verdict prints it: `degC` for a temperature, `1` for a plain number, and the exponents of the dimension, as `kg^1 s^-2`, where no unit of factor 1 has it. The signer answers for the completion too, so the cell prints it.

`ratio` is worked out by the Python reader. It is not the kernel's. Nor is `report.verdict`, the reader's own word for the cells it worked out: `petra.check` holds it to the kernel's and reports only the kernel's.

## JSON of a design no deck has

A design none of whose parts is of a deck's type cannot be checked: there is no rule to check it by. The kernel is not asked about it, and it reads UNKNOWN with a kernel on the machine or without one.

```
{"file": FILE, "design": NAME, "status": "UNKNOWN",
 "reason": TEXT,                               which kinds of part no deck has
 "kinds": [KIND, ...],                         at most 100 of them, each cut to 64 characters
 "more_kinds": N,                              how many more there are
 "deck": null, "kernel": null, "cells": [], "waived": [],
 "card": FILE, "hashes": {"card": HASH, "design": HASH},
 "path": "none"}
```

The pair is still held to the language: a load with no signature, a given no part reads and a load on a part the design does not have are refused as input. Past that nothing checks its numbers. The kernel holds every size and every signed bound to the floors of `deck.json`, and it is not asked, so a length under zero or an ambient of -1000 degC reads UNKNOWN like the rest.

A design with parts of a deck's types and parts of another kind is refused as input.

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

None of these gives the verdict of a check. A bug in the reader of a deck costs an UNKNOWN or a difference from the kernel. A bug in the language, the units or the exporter gives the kernel other files than the pair's, and the verdict is then about those files.

| Module | Holds |
|---|---|
| `petra.lang` | `parse_design(card, design, path)` and `load_design(path)`: the two texts as one parsed design |
| `petra.grid` | The Python reader of a deck: `read_deck(text)`, `decks()`, `kinds()`, and `check(design, deck)`, which returns the reader's own cells and runs no kernel |
| `petra.rule` | The acceptance check that a rule passes before it enters a deck, and with `--run FILE` the record of the run that a deck is read with |
| `petra.deck` | Reads a deck's rows: tables and constants |
| `petra.export` | Writes the files the kernel reads, for a design of a deck: `python -m petra.export FILE.petra --out DIR` |
| `petra.verify` | Finds and runs the kernel, and takes its answer |
| `petra.teach` | What `petra kinds`, `petra new` and `petra docs` print |
