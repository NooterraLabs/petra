"""The acceptance run that petra/decks/aisc360.json is bound to.

    python -m bench.formalizer.bound            write petra/decks/aisc360.run.json
    python -m bench.formalizer.bound --check    exit 1 unless the file there is what the run gives now

A deck is read only with the record of its acceptance run beside it (docs/deck.md, "The
run a deck is bound to"), and the record names the hash of the deck's file. So an edit of
the deck, however small, leaves a deck that no reader takes until the run is made again.

The run is the second run of docs/deck.md: the deck's own rules as the first transcription,
rules2_b.json as the second, and the worked examples of rules2_examples.json. Three things
are changed before the check, and the record says so in `changed`:

- The task is made from the deck: its rows, its types with the ranges, `alike` and
  `adverse` that rules_task2.json gives them, and its grid with no `unless`.
  rules_task2.json no longer loads as it stands: it names the deck and a3.json for its
  rows, and the deck now holds the rows of a3.json, so each would be there twice.
- The second transcription answered `lap.spread` with four rules, two of them for the
  greatest edge distance. The deck asks the edge distance on a line of its own with no
  rule, so those two are set aside.
- Both transcribers said of four lines that they cannot arise, each with a reason and no
  ground, as an `unless` was then. The deck's four were given their grounds by hand, and
  the second transcription's four are given the same ones before the two are compared.

tests/test_deck_rules.py runs this and holds the file beside the deck to it.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

from petra import export, grid, rule

HERE = Path(__file__).resolve().parent
DECK = grid.DECKS / "aisc360.json"
RUN = grid.DECKS / "aisc360.run.json"
READ = ("rules_task2.json", "rules2_b.json", "rules2_examples.json")
SET_ASIDE = ("lap-spread-edge-a", "lap-spread-edge-b")
CHANGED = ("the task is made from the deck's rows, types and grid with the ranges, alike and adverse of rules_task2.json; "
           "the rules lap-spread-edge-a and lap-spread-edge-b of the second transcription are set aside; "
           "the four lines the second transcription excuses are given the deck's grounds")


def read(name: str) -> dict[str, Any]:
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def task_of(deck: dict[str, Any]) -> dict[str, Any]:
    """The task of the second run, made from the deck. The name is that task's, because the
    check samples its parts by it."""
    asked = read("rules_task2.json")
    types = copy.deepcopy(deck["types"])
    for kind, given in zip(types, asked["types"], strict=True):
        sampled = {f["name"]: f for f in (*given["fields"], *given.get("loads", []))}
        for f in (*kind["fields"], *kind.get("loads", [])):
            f.update({key: sampled[f["name"]][key] for key in ("range", "adverse") if key in sampled[f["name"]]})
        if "alike" in given:
            kind["alike"] = given["alike"]
    return {"format": rule.TASK, "name": asked["name"], "about": "The lap of the deck that ships, with the ranges of bench/formalizer/rules_task2.json.",
            "rows": deck["rows"], "types": types, "asks": [{k: v for k, v in a.items() if k != "unless"} for a in deck["grid"]]}


class Run:
    """The run on the deck whose text is `text`: the task, the two readings, the examples,
    and what the check finds."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.deck = json.loads(text)
        self.task = rule.read_task(task_of(self.deck))
        self.first = rule.Reading(self.task, rule.read_transcription(self.deck))
        self.handed_in = read("rules2_b.json")
        self.grounds = {a["mechanism"]: {k: v for k, v in a["unless"].items() if k != "why"} for a in self.deck["grid"] if "unless" in a}
        excused = [{**u, **self.grounds.get(u["mechanism"], {})} for u in self.handed_in["unless"]]
        self.other = rule.Reading(self.task, rule.read_transcription({**self.handed_in, "rules": [r for r in self.handed_in["rules"] if r["id"] not in SET_ASIDE], "unless": excused}))
        self.examples = {m: [rule.worked(e, self.task, m) for e in found] for m, found in read("rules2_examples.json")["examples"].items()}
        self.lines, self.whole = rule.accept(self.first, self.examples, self.other)

    def record(self) -> str:
        """The file of this run (rule.record), with the hash of each file of this folder that it read."""
        inputs = {name: export.sha256((HERE / name).read_text(encoding="utf-8")) for name in READ}
        return rule.record(self.task, self.text, self.lines, self.whole, self.first.stray, inputs, CHANGED)

    def refused(self) -> list[str]:
        """The lines the check refuses, and `reads` when the whole fails: none for a deck that is to ship."""
        return [line.mechanism for line in self.lines if line.state == "refused"] + (["reads"] if self.whole.outcome == "fail" or self.first.stray else [])


def main(argv: list[str]) -> int:
    run = Run(DECK.read_text(encoding="utf-8"))
    found = run.record()
    if run.refused():
        print(f"{DECK.name}: the run refuses {', '.join(run.refused())}, and the deck that ships is bound to no such run: nothing written", file=sys.stderr)
        return 1
    if argv == ["--check"]:
        if not RUN.is_file() or RUN.read_text(encoding="utf-8") != found:
            print(f"{RUN.name} is not the record of the run on {DECK.name} as it is: run python -m bench.formalizer.bound", file=sys.stderr)
            return 1
        return 0
    if argv:
        print("usage: python -m bench.formalizer.bound [--check]", file=sys.stderr)
        return 64
    RUN.write_text(found, encoding="utf-8", newline="\n")
    print(f"{RUN.name}: bound to {export.sha256(DECK.read_text(encoding='utf-8'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
