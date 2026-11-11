"""The third hostile review of petra-verify (kernel/), one test per reproduced finding.

Each test asserts the behaviour the kernel should have, and each failed against the kernel at
b4698ad (rework), where the review was made. The review found no false PASS, no false proof
and no false refutation. The tests are skipped when no kernel is built. The ones marked
"hostile deck" pass their own deck of rules with --rules.

  1  The units of work undercharge steps on long fractions. 60 KB of proofs.json (no deck of
     rules) spend the 20 billion units on products of 8,000-bit fractions in 46 to 65 s;
     docs/format.md says such files take 4 to 15 s, and the author's own chain of small
     products takes 2.7 to 6.5 s on the same machine at the same time.
  2  Hostile deck. The cases that carry every load a rule reads are found by filtering the
     part's loads again for each case (Grid.lean, `unders`), uncounted: 1,000 rules over
     two loads of 3,000 cases each, 0.69 MB, 449 s.
  3  Hostile deck. 1 and 4 together, the worst on paper: 0.81 MB, 89 s.
  4  Hostile deck. Writing the tapes is charged by steps (MAX_STEPS), but each `.field` step
     finds its slot by a linear search of the part's slots (Grid.lean, Part.slot). 2,800
     fields and 1,150 load cases, 0.95 MB: 75 s, before any proof and with work 0.
  5  Hostile deck. Reading a rule builds a name for each joined part times each field of the
     joined type (Deck.lean, scopeOf), before any limit. 152 KB held 1.5 GB.
  6  Hostile deck. A row is read again at each application (Deck.lean, expr, "row"), and every
     name of `let` is read, used or not. 200 KB held 0.84 GB for 33 to 37 s.
  7  Type rule 4 finds the floor of an input by the name it spells its dimension with
     (Check.lean, types). `m^1`, `moment` and `degC^1` escape the floors of length, energy
     and temperature, so a card the docs call ILL-FORMED gets PASS.
  8  The JSON reader reads every lone surrogate escape as U+FFFD, so a waiver for one name
     rests a cell of another.
  9  Load cases are free text, so a case named `gravity/where` makes its main cell print
     under the same key as the range cell of the case `gravity`.
 10  Type rule 5 refuses a waiver with an empty `by` and takes an input with one.

Two more came with the review, and each is decided here as a refusal:

 11  A rule with `where: []` was proved by the kernel and by petra/grid.py, and left open by
     the third reading. A `where` that is there has at least one item.
 12  Two rules of one line of the grid whose ids end alike, `a/x` and `b/x`, gave two cells
     with the entry `x`, and one hint was offered to both.
"""
import copy
import hashlib
import json
import random
import unittest
from collections import Counter
from fractions import Fraction

from petra import export, grid, verify
from tests.test_grid import STRIPS
from tests.test_kernel_attacks import export_lap, run_raw
from tests.test_kernel_attacks2 import MB, answered_within, halves, num, peak_bytes, total
from tests.test_kernel_grid import ask, findings, strips
from tests.test_kernel_limits import old_path
from tests.test_kernel_limits import with_rules as with_deck

HALF_GB = 512_000_000


def text(body) -> str:
    """JSON with every non-ASCII character escaped, so a lone surrogate survives the write."""
    return json.dumps(body, separators=(",", ":"))


def sha(body: str) -> str:
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def core_domains() -> dict:
    return json.loads(export.CORE.read_text(encoding="utf-8"))["domains"]


def with_card(cells: list[dict], inputs: list[dict] = (), waivers: list[dict] = ()) -> dict[str, str]:
    """old_path with inputs on the card, written with text() so any escape survives."""
    card = text({"format": "petra-card/0", "name": "c", "environment": None, "cases": [], "inputs": list(inputs),
                 "claims": [], "waivers": list(waivers)})
    design = text({"format": "petra-design/0", "name": "d", "card": sha(card), "quantities": [], "params": []})
    deck = text({"format": "petra-deck/0", "domains": core_domains(), "constants": []})
    return {"card": card, "design": design, "deck": deck, "proofs": text({"format": "petra-proofs/0", "cells": list(cells)})}


def with_rules(rules: dict, card: dict, parts: list[dict], hints: list[dict] = ()) -> dict[str, str]:
    """A design of `parts` against a hostile deck of rules."""
    card_text = text(card)
    design = text({"format": "petra-design/0", "name": "c", "card": sha(card_text), "quantities": [], "params": [],
                   "parts": parts})
    deck = text({"format": "petra-deck/0", "domains": core_domains(), "constants": [], "rules": {"name": rules["name"], "hash": "x"}})
    return {"card": card_text, "design": design, "deck": deck, "rules": text(rules),
            "proofs": text({"format": "petra-proofs/0", "cells": list(hints)})}


def empty_card(inputs: list[dict] = ()) -> dict:
    return {"format": "petra-card/0", "name": "c", "environment": None, "cases": [], "inputs": list(inputs), "claims": [],
            "waivers": [], "tests": [], "probability_claims": []}


ANCHOR = {"standard": "s", "clause": "c"}
TRUE = {"inputs": [], "nodes": [["c", "-1"]], "roots": [0]}


def cell(tape: dict | None = None, state: str = "proved", subject: str = "s", **more) -> dict:
    found = {"subject": subject, "mechanism": "m", "entry": "e", "state": state, **more}
    if tape is not None:
        found.update(tape=tape, partition="leaf")
    return found


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Time(unittest.TestCase):
    def test_products_of_long_fractions_spend_the_budget_in_the_documented_time(self):
        """Finding 1. Fifty products of two 8,000-bit fractions on each of 1,024 leaves: 60 KB.
        The work runs out at leaf 693 after 46 s on an idle desktop and 52 to 65 s on a busy
        one; the author's chain of 4,000 small products spends the same 20 billion units in
        2.7 to 6.5 s there. No deck of rules: the tape is proofs.json's."""
        rnd = random.Random(1)
        odd = lambda: rnd.getrandbits(8000) | (1 << 7999) | 1
        nodes = [["s", 0]]

        def fraction() -> int:
            x = Fraction(odd(), odd())
            nodes.extend([["c", str(x.numerator)], ["c", str(x.denominator)], ["div", len(nodes), len(nodes) + 1]])
            return len(nodes) - 1

        a, b = fraction(), fraction()
        roots = []
        for _ in range(50):
            nodes.extend([["mul", [a, b]], ["abs", len(nodes)], ["neg", len(nodes) + 1]])
            roots.append(len(nodes) - 1)
        tape = {"inputs": [{"label": "dsg:x", "lo": "0", "hi": "1024"}], "nodes": nodes, "roots": roots}
        files = old_path([cell(tape) | {"partition": halves(0, Fraction(0), Fraction(1024), 1024)}], [])
        self.assertLess(total(files), 70_000)
        answered_within(self, files, 30)

    def test_the_tapes_of_a_type_with_many_fields_are_written_in_time(self):
        """Finding 4, hostile deck. One rule sums 2,800 fields of 64-byte names that share a
        prefix and reads one load; the card puts the load on the part in 1,150 cases. That is
        under MAX_STEPS, but each `.field` step of each tape searches the part's slots: 0.95
        MB, 75 s and 58 CPU seconds on a busy desktop, with work 0 and 1,150 open cells."""
        F, N = 2800, 1150
        name = lambda k: "q" * (64 - len(f"f{k}")) + f"f{k}"
        kind = {"type": "t", "what": "w", "fields": [{"name": name(k), "dim": "length", "what": "w"} for k in range(F)],
                "loads": [{"name": "L", "dim": "length", "what": "w"}]}
        rule = {"id": "r/x", "type": "t", "mechanism": "m", "anchor": ANCHOR, "says": "s",
                "le": [["load", "L"], ["add"] + [name(k) for k in range(F)]]}
        rules = {"format": "petra-rules/0", "name": "big", "about": "a", "rows": [], "types": [kind],
                 "grid": [{"type": "t", "mechanism": "m", "what": "w", "anchor": ANCHOR}], "rules": [rule]}
        inputs = [{"name": f"i{c}", "dim": "length", "lo": "0", "hi": "1", "by": "b", "case": f"c{c}", "on": "p", "field": "L"}
                  for c in range(N)]
        lines = [{"field": name(k), "args": [{"number": {"dim": "length", "lo": "1", "hi": "1"}}]} for k in range(F)]
        files = with_rules(rules, empty_card(inputs), [{"name": "p", "type": "t", "lines": lines}])
        self.assertLess(total(files), MB)
        answered_within(self, files, 30)

    def test_the_worst_on_paper_answers_in_time(self):
        """Finding 3, findings 1 and 4 together, hostile deck. Rule r/x of the test above with 1,500
        cases, and a rule r/big whose one hinted proof multiplies quotients of 3,990-digit
        literals on 200 leaves until the 20 billion units run out: 0.81 MB, 89 s and 49 MB on
        a busy desktop."""
        F, N, K, L = 2000, 1500, 12, 200
        rnd = random.Random(3)
        name = lambda k: "q" * (64 - len(f"f{k}")) + f"f{k}"
        fields = [{"name": name(k), "dim": "length", "what": "w"} for k in range(F)] + [{"name": "g", "dim": "length", "what": "w"}]
        kind = {"type": "t", "what": "w", "fields": fields, "loads": [{"name": "L", "dim": "length", "what": "w"}]}
        lets = {f"b{i}": str(rnd.randrange(10 ** 3989, 10 ** 3990) | 1) for i in range(K)}
        lets.update({f"d{i}": ["div", f"b{i}", f"b{i + 1}"] for i in range(K - 1)})
        products = [["mul", f"d{i}", f"d{j}"] for i in range(K - 1) for j in range(i, K - 1)]
        big = {"id": "r/big", "type": "t", "mechanism": "big", "anchor": ANCHOR, "says": "s", "let": lets,
               "le": [["mul", "g", ["min", "1"] + products], ["mul", "2", "g"]]}
        steps = {"id": "r/x", "type": "t", "mechanism": "m", "anchor": ANCHOR, "says": "s",
                 "le": [["load", "L"], ["add"] + [name(k) for k in range(F)]]}
        rules = {"format": "petra-rules/0", "name": "big", "about": "a", "rows": [], "types": [kind],
                 "grid": [{"type": "t", "mechanism": m, "what": "w", "anchor": ANCHOR} for m in ("m", "big")],
                 "rules": [steps, big]}
        inputs = [{"name": f"i{c}", "dim": "length", "lo": "0", "hi": "1", "by": "b", "case": f"c{c}", "on": "p", "field": "L"}
                  for c in range(N)]
        lines = [{"field": name(k), "args": [{"number": {"dim": "length", "lo": "1", "hi": "1"}}]} for k in range(F)]
        lines.append({"field": "g", "args": [{"number": {"dim": "length", "lo": "1", "hi": "2"}}]})
        hint = {"subject": "p", "mechanism": "big", "entry": "big", "state": "proved",
                "partition": halves("dsg:c.p.g", Fraction(1), Fraction(2), L)}
        files = with_rules(rules, empty_card(inputs), [{"name": "p", "type": "t", "lines": lines}], [hint])
        self.assertLess(total(files), MB)
        answered_within(self, files, 30)

    def test_the_cases_that_carry_every_load_of_a_rule_are_found_in_time(self):
        """Finding 2, hostile deck. 1,000 rules each read loads A and B of one part; the card
        puts A on it in 3,000 cases and B in 3,000 others. For each case of A the kernel
        filters the part's 6,000 loads again to see whether B is there too, so each rule
        costs about 27 million steps of that before it makes its one open cell, and none is
        counted: 0.69 MB, 449 s and 434 CPU seconds, work 0."""
        N, R = 3000, 1000
        kind = {"type": "t", "what": "w", "fields": [{"name": "f", "dim": "length", "what": "w"}],
                "loads": [{"name": n, "dim": "length", "what": "w"} for n in ("A", "B")]}
        rules = {"format": "petra-rules/0", "name": "big", "about": "a", "rows": [], "types": [kind],
                 "grid": [{"type": "t", "mechanism": "m", "what": "w", "anchor": ANCHOR}],
                 "rules": [{"id": f"r/{i}", "type": "t", "mechanism": "m", "anchor": ANCHOR, "says": "s",
                            "le": [["load", "A"], ["load", "B"]]} for i in range(R)]}
        inputs = [{"name": f"{x}{c}", "dim": "length", "lo": "0", "hi": "1", "by": "b", "case": f"{x}{c}", "on": "p",
                   "field": x.upper()} for x in ("a", "b") for c in range(N)]
        part = {"name": "p", "type": "t", "lines": [{"field": "f", "args": [{"number": {"dim": "length", "lo": "1", "hi": "1"}}]}]}
        files = with_rules(rules, empty_card(inputs), [part])
        self.assertLess(total(files), 0.7 * MB)
        answered_within(self, files, 30)


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Memory(unittest.TestCase):
    def test_a_type_that_joins_many_parts_of_a_wide_type_reads_in_bounded_memory(self):
        """Finding 5, hostile deck. A type of 3,000 fields, a type that joins 3,000 parts of it,
        and one rule: reading the rule makes 9 million names. 152 KB held 1.49 GB for 21 s,
        and there are no parts."""
        J = G = 3000
        plate = {"type": "p", "what": "w", "fields": [{"name": f"f{k}", "dim": "length", "what": "w"} for k in range(G)]}
        lap = {"type": "lap", "what": "w", "fields": [{"name": "joins", "type": "p", "as": [f"a{k}" for k in range(J)], "what": "w"}]}
        rule = {"id": "r0", "type": "lap", "mechanism": "m", "anchor": ANCHOR, "says": "s", "le": ["a0.f0", "a0.f0"]}
        rules = {"format": "petra-rules/0", "name": "big", "about": "a", "rows": [], "types": [plate, lap],
                 "grid": [{"type": "lap", "mechanism": "m", "what": "w", "anchor": ANCHOR}], "rules": [rule]}
        files = with_rules(rules, empty_card(), [])
        self.assertLess(total(files), 160_000)
        self.assertLess(peak_bytes(files, timeout=300), HALF_GB)

    def test_a_wide_row_applied_by_many_lets_reads_in_bounded_memory(self):
        """Finding 6, hostile deck. A row whose body adds its one input 20,000 times, and a
        rule with 4,000 names of `let` that each apply it and that nothing uses: 80 million
        steps written while the deck is read. 200 KB held 0.84 GB for 33 to 37 s."""
        row = {"id": "w", "anchor": ANCHOR, "gives": {"name": "y", "dim": "length", "what": "w"},
               "takes": [{"name": "x", "dim": "length", "what": "w", "range": ["1 m", "2 m"]}],
               "is": ["add"] + ["x"] * 20_000}
        kind = {"type": "t", "what": "w", "fields": [{"name": "f", "dim": "length", "what": "w"}]}
        rule = {"id": "r/x", "type": "t", "mechanism": "m", "anchor": ANCHOR, "says": "s",
                "let": {f"v{i}": ["row", "w", {"x": "f"}] for i in range(4000)}, "le": ["f", "f"]}
        rules = {"format": "petra-rules/0", "name": "big", "about": "a", "rows": [row], "types": [kind],
                 "grid": [{"type": "t", "mechanism": "m", "what": "w", "anchor": ANCHOR}], "rules": [rule]}
        files = with_rules(rules, empty_card(), [])
        self.assertLess(total(files), 210_000)
        self.assertLess(peak_bytes(files, timeout=300), HALF_GB)


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Types(unittest.TestCase):
    def test_a_floor_holds_for_every_spelling_of_its_dimension(self):
        """Finding 7. docs/format.md: "two names are one dimension when their exponents are equal",
        and type rule 4 holds an input to the floor of its dimension in domains.input. The
        kernel looks the floor up by the name the card spells, so each of these is PASS."""
        for dim, lo in (("m^1", "-5"), ("moment", "-5"), ("degC^1", "-1000")):
            with self.subTest(dim=dim):
                files = with_card([cell(TRUE)], inputs=[{"name": "x", "dim": dim, "lo": lo, "hi": "1", "by": "b"}])
                _, out = run_raw(files)
                said = json.loads(out)
                self.assertEqual(said["verdict"], "ILL-FORMED")
                self.assertIn("types.4", [f["rule"] for f in said["findings"]])

    def test_an_input_with_an_empty_by_is_refused(self):
        """Finding 10. A waiver with `by: ""` is refused (types.5, "the waiver names no by"),
        and docs/format.md refuses an input with no `by`; an input with `by: ""` is PASS."""
        files = with_card([cell(TRUE)], inputs=[{"name": "x", "dim": "length", "lo": "0", "hi": "1", "by": ""}])
        _, out = run_raw(files)
        self.assertEqual(json.loads(out)["verdict"], "ILL-FORMED")


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Names(unittest.TestCase):
    def test_a_waiver_rests_only_the_cell_it_names(self):
        """Finding 8. The card waives "a\\udfff" and proofs.json has a waived cell "a\\ud800".
        Python, which wrote petra/grid.py, reads two names; the kernel reads both as "a\\ufffd"
        and prints PASS."""
        files = with_card([cell(TRUE), cell(state="waived", subject="a\ud800")],
                          waivers=[{"subject": "a\udfff", "mechanism": "m", "by": "b", "reason": "r"}])
        self.assertIn("\\ud800", files["proofs"])
        _, out = run_raw(files)
        self.assertNotEqual(json.loads(out)["verdict"], "PASS")

    def test_no_two_cells_print_one_key(self):
        """Finding 9. The lap design with a second load case named `gravity/where`: its main
        cell of lap-strength and the range cell of the case `gravity` both print as
        splice/lap.strength/lap-strength/gravity/where, and the one hint of that key is
        offered to both tapes. The JS reading does the same."""
        files = export_lap("lap_pass")
        card = json.loads(files["card"])
        proofs = json.loads(files["proofs"])
        pull = next(i for i in card["inputs"] if i.get("field") == "pull")
        card["cases"].append("gravity/where")
        card["inputs"].append(dict(pull, case="gravity/where", name="gravity/where.splice.pull"))
        added = []
        for c in proofs["cells"]:
            if c["entry"].startswith(("lap-strength/gravity", "lap-yield-a/gravity", "lap-yield-b/gravity")):
                added.append(dict(copy.deepcopy(c), entry=c["entry"].replace("/gravity", "/gravity/where", 1)))
        proofs["cells"] += added
        files["card"] = text(card)
        design = json.loads(files["design"])
        design["card"] = sha(files["card"])
        files["design"] = text(design)
        files["proofs"] = text(proofs)
        _, out = run_raw(files)
        said = json.loads(out)
        keys = Counter((c["subject"], c["mechanism"], c["entry"]) for c in said["cells"])
        twice = [k for k, n in keys.items() if n > 1]
        self.assertTrue(said["verdict"] == "ILL-FORMED" or not twice, f"{said['verdict']} with {twice} printed twice")


def empty_where(rules: dict) -> None:
    rules["rules"][0]["where"] = []


def one_entry_twice(rules: dict) -> None:
    """A second rule for the line strip.hole whose id ends as the first one's does."""
    rules["rules"].append(dict(copy.deepcopy(rules["rules"][1]), id="other/hole"))


class TheGridRefusesTheSameDecks(unittest.TestCase):
    """petra/grid.py refuses what the kernel refuses of a deck (bench/kernel_grid.py)."""

    def refused(self, change) -> None:
        body = copy.deepcopy(STRIPS)
        change(body)
        with self.assertRaises(grid.DeckError):
            grid.read_deck(json.dumps(body))

    def test_the_grid_refuses_an_empty_where(self):
        self.refused(empty_where)

    def test_the_grid_refuses_two_rules_of_one_line_with_one_entry(self):
        self.refused(one_entry_twice)


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Decks(unittest.TestCase):
    def test_a_where_that_is_there_has_an_item(self):
        """Item 11. With `where: []` the kernel wrote no range cell and proved the rule's cell."""
        said = ask(with_deck(strips(), empty_where))
        self.assertIn("rule test/heat", findings(said))
        self.assertEqual(said["findings"][0]["file"], "rules")

    def test_two_rules_of_one_line_have_two_entries(self):
        """Item 12. `test/hole` and `other/hole` both answer strip.hole of a strip, and both
        cells were s/strip.hole/hole."""
        said = ask(with_deck(strips(), one_entry_twice))
        self.assertIn("hole", findings(said))
        self.assertEqual(said["findings"][0]["file"], "rules")


if __name__ == "__main__":
    unittest.main()
