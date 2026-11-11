"""The third hostile review of petra-verify (kernel/), one test per reproduced finding.

Each test asserts the behaviour the kernel should have, and each failed against the kernel at
b4698ad (rework), where the review was made. The review found no false PASS, no false proof
and no false refutation. The tests are skipped when no kernel is built. The ones marked
"hostile deck" pass their own deck of rules with --rules.

All ten are closed, and each docstring keeps what the review measured. A test of time does
not read the clock, which a busy machine stretches. It holds the kernel to what it counts
(`work`, the leaf where the work ran out, the cells it made), to a refusal, and to the
processor seconds of its process, with a margin of three times or more.

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
import re
import unittest
from collections import Counter
from fractions import Fraction

from petra import export, grid, verify
from tests.test_grid import STRIPS
from tests.test_kernel_attacks import export_lap, run_raw
from tests.test_kernel_attacks2 import MB, halves, measured, total
from tests.test_kernel_grid import ask, findings, strips
from tests.test_kernel_limits import COSTLY, MAX_WORK, old_path
from tests.test_kernel_limits import with_rules as with_deck

HALF_GB = 512_000_000
PROCESSOR_SECONDS = 30
"""The most processor seconds the kernel may take on an input under 1 MB. A test holds the
kernel to it by the processor time of its process, which a busy machine does not stretch as
it stretches the clock, and each input here takes a fraction of it."""


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


def with_rules(rules: dict, card: dict, parts: list[dict], hints: list[dict] = (), name: str = "c") -> dict[str, str]:
    """A design of `parts` against a hostile deck of rules."""
    card_text = text(card)
    design = text({"format": "petra-design/0", "name": name, "card": sha(card_text), "quantities": [], "params": [],
                   "parts": parts})
    deck = text({"format": "petra-deck/0", "domains": core_domains(), "constants": [], "rules": {"name": rules["name"], "hash": "x"}})
    return {"card": card_text, "design": design, "deck": deck, "rules": text(rules),
            "proofs": text({"format": "petra-proofs/0", "cells": list(hints)})}


def empty_card(inputs: list[dict] = (), name: str = "c") -> dict:
    return {"format": "petra-card/0", "name": name, "environment": None, "cases": [], "inputs": list(inputs), "claims": [],
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
        said, seconds, _ = measured(files)
        (found,) = said["cells"]
        self.assertEqual(found["state"], "open")
        leaf = re.fullmatch(r"leaf (\d+): node \d+: " + re.escape(COSTLY), found["reason"])
        self.assertTrue(leaf, found["reason"])
        self.assertGreater(said["work"], MAX_WORK * 9 // 10, "the proof stopped because the work ran out")
        self.assertLess(int(leaf[1]), 250, "a leaf of fifty such products is charged at least 80 million units, where it was charged 29 million")
        self.assertLess(seconds, PROCESSOR_SECONDS, "the work is spent in 6 to 8 processor seconds")

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
        said, seconds, _ = measured(files)
        self.assertEqual((said["verdict"], said["counts"]["open"], said["work"]), ("UNKNOWN", N, 0))
        self.assertLess(seconds, PROCESSOR_SECONDS, "the tapes are written in about 2 processor seconds")

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
        said, seconds, _ = measured(files)
        self.assertEqual((said["verdict"], said["counts"]["open"]), ("UNKNOWN", N + 1))
        self.assertGreater(said["work"], MAX_WORK * 9 // 10, "the hinted proof stopped because the work ran out")
        self.assertLess(seconds, PROCESSOR_SECONDS, "the tapes are written and the work is spent in about 7 processor seconds")

    def test_the_cases_that_carry_every_load_of_a_rule_are_found_in_time(self):
        """Finding 2, hostile deck. 1,000 rules each read loads A and B of one part; the card
        puts A on it in 3,000 cases and B in 3,000 others. For each case of A the kernel
        filtered the part's 6,000 loads again to see whether B is there too, so each rule
        cost about 27 million steps of that before it made its one open cell, and none was
        counted: 0.69 MB, 449 s and 434 CPU seconds, work 0.

        The fourth review changed what these files ask (docs/format.md, "Cells from a deck of
        rules", item 4): a rule that reads loads has a cell for each load case of the card,
        open under a case that does not put every load it reads on the part. So the 1,000
        rules ask 6,000 cells each, which is past the 10,000 the kernel makes, and it refuses
        the design at once. One such rule asks 6,000, and each is open."""
        N = 3000
        kind = {"type": "t", "what": "w", "fields": [{"name": "f", "dim": "length", "what": "w"}],
                "loads": [{"name": n, "dim": "length", "what": "w"} for n in ("A", "B")]}
        inputs = [{"name": f"{x}{c}", "dim": "length", "lo": "0", "hi": "1", "by": "b", "case": f"{x}{c}", "on": "p",
                   "field": x.upper()} for x in ("a", "b") for c in range(N)]
        part = {"name": "p", "type": "t", "lines": [{"field": "f", "args": [{"number": {"dim": "length", "lo": "1", "hi": "1"}}]}]}

        def files_of(count: int) -> dict[str, str]:
            rules = {"format": "petra-rules/0", "name": "big", "about": "a", "rows": [], "types": [kind],
                     "grid": [{"type": "t", "mechanism": "m", "what": "w", "anchor": ANCHOR}],
                     "rules": [{"id": f"r/{i}", "type": "t", "mechanism": "m", "anchor": ANCHOR, "says": "s",
                                "le": [["load", "A"], ["load", "B"]]} for i in range(count)]}
            return with_rules(rules, empty_card(inputs), [part])

        files = files_of(1000)
        self.assertLess(total(files), 0.7 * MB)
        said, seconds, _ = measured(files)
        self.assertEqual((said["verdict"], len(said["cells"])), ("ILL-FORMED", 0), "6,000 cells for each of 1,000 rules are past the limit")
        self.assertEqual([(f["rule"], f["item"]) for f in said["findings"]], [("limits", "parts")])
        self.assertIn("asks more than 10000 cells", said["findings"][0]["why"])
        self.assertLess(seconds, PROCESSOR_SECONDS, "the design is refused in under a processor second")
        said, seconds, _ = measured(files_of(1))
        self.assertEqual((said["verdict"], len(said["cells"])), ("UNKNOWN", 2 * N + 1), "an open cell for each case, and one for the field nothing reads")
        self.assertEqual({c["state"] for c in said["cells"]}, {"open"})
        self.assertEqual([c["reason"] for c in said["cells"][:2]] + [said["cells"][N]["reason"]],
                         ["case a0 puts no B on p, which the rule reads", "case a1 puts no B on p, which the rule reads",
                          "case b0 puts no A on p, which the rule reads"])
        self.assertLess(seconds, PROCESSOR_SECONDS, "the cases are found in under a processor second")


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
        said, seconds, peak = measured(files)
        self.assertEqual((said["verdict"], said["findings"]), ("UNKNOWN", []), "the deck is read, and the design has no part")
        self.assertLess(peak, HALF_GB // 4, "the kernel holds about 35 MB")
        self.assertLess(seconds, PROCESSOR_SECONDS)

    def test_a_wide_row_applied_by_many_lets_reads_in_bounded_memory(self):
        """Finding 6, hostile deck. A row whose body adds its one input 20,000 times, and a
        rule with 4,000 names of `let` that each apply it and that nothing uses: 80 million
        steps written while the deck is read. 200 KB held 0.84 GB for 33 to 37 s. A name is
        two steps to read, so the row is 40,000 and the deck 160 million."""
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
        said, seconds, peak = measured(files)
        self.assertEqual([(f["rule"], f["file"]) for f in said["findings"]], [("shape", "rules")])
        self.assertEqual(grid._steps(rules), 160_196_088, "the grid makes the same count")
        self.assertIn("reading this deck takes 160196088 steps, over the budget of 1000000", said["findings"][0]["why"])
        self.assertLess(peak, HALF_GB // 4, "the deck is refused before a row is read")
        self.assertLess(seconds, PROCESSOR_SECONDS)


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
        said = json.loads(out)
        self.assertEqual(said["verdict"], "ILL-FORMED")
        self.assertEqual([(f["rule"], f["item"], f["why"]) for f in said["findings"]], [("types.5", "x", "the input names no by")])

    def test_an_input_whose_dim_names_no_dimension_is_refused(self):
        """A floor is found by exponents, so a `dim` the kernel cannot read as exponents has
        no floor to be held to. It is a finding, where it was taken as a dimension with none."""
        for dim in ("lenght", "m", "m^1  s^1", ""):
            with self.subTest(dim=dim):
                files = with_card([cell(TRUE)], inputs=[{"name": "x", "dim": dim, "lo": "-5", "hi": "1", "by": "b"}])
                said = json.loads(run_raw(files)[1])
                self.assertEqual((said["verdict"], [f["rule"] for f in said["findings"]]), ("ILL-FORMED", ["types.4"]))
                self.assertIn("is not a dimension", said["findings"][0]["why"])

    def test_two_keys_of_one_dimension_give_it_the_tighter_floor(self):
        """deck.json may list `length` and `m^1`. They are one dimension, and an input is held
        to the higher of the two floors, however it spells its own."""
        def said(lo: str, dim: str, floors: dict) -> dict:
            files = with_card([cell(TRUE)], inputs=[{"name": "x", "dim": dim, "lo": lo, "hi": "9", "by": "b"}])
            deck = json.loads(files["deck"])
            deck["domains"]["input"] = {"about": "made up", **floors}
            return json.loads(run_raw({**files, "deck": text(deck)})[1])
        floors = {"length": {"min": "0", "strict": False}, "m^1": {"min": "5", "strict": False}, "m^1 kg^0": {"min": "5", "strict": True}}
        for dim in ("length", "m^1", "kg^0 m^1"):
            with self.subTest(dim=dim):
                self.assertEqual(said("6", dim, floors)["verdict"], "PASS")
                under = said("5", dim, floors)
                self.assertEqual((under["verdict"], [f["rule"] for f in under["findings"]]), ("ILL-FORMED", ["types.4"]),
                                 "5 is at the floor of 5, and one of the two floors at 5 is strict")
        named = said("6", "length", {"lenght": {"min": "0", "strict": False}})
        self.assertEqual([(f["rule"], f["file"], f["item"], f["why"]) for f in named["findings"]],
                         [("shape", "deck", "domains.input.lenght", "is not a dimension")])


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
        said = json.loads(out)
        self.assertEqual((said["verdict"], sorted(f["file"] for f in said["findings"])), ("ILL-FORMED", ["card", "proofs"]))
        self.assertIn("holds U+FFFD", said["findings"][0]["why"])

    def test_a_text_with_the_replacement_character_is_refused_wherever_it_stands(self):
        """A file is refused for U+FFFD in a name, in prose and in a key, written as itself or
        as an escape. A pair of escapes that is one character is read as that character."""
        honest = strips()
        for name, change in (("card", lambda b: b["waivers"][0].update(reason="a reason�")),
                             ("design", lambda b: b["parts"][0].update(name="p�")),
                             ("rules", lambda b: b["types"][0].update(what="a pad�")),
                             ("rules", lambda b: b["rules"][0].update({"let": {"k�": "1"}})),
                             ("proofs", lambda b: b["cells"][0].update({"note�": "x"}))):
            for write in (text, lambda b: json.dumps(b, ensure_ascii=False)):
                with self.subTest(file=name, escaped=write is text):
                    body = json.loads(honest[name])
                    change(body)
                    said = ask({**honest, name: write(body)})
                    self.assertIn(f"shape {name} : a text or a key holds U+FFFD", findings(said))
        pair = json.loads(honest["card"])
        pair["waivers"][0]["reason"] = "a face \U0001F600"
        self.assertIn("\\ud83d\\ude00", text(pair))
        card = text(pair)
        design = json.loads(honest["design"])
        design["card"] = sha(card)
        self.assertEqual(ask({**honest, "card": card, "design": text(design)})["verdict"], ask(honest)["verdict"])

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
        self.assertEqual([(f["rule"], f["file"], f["item"]) for f in said["findings"]], [("shape", "card", "gravity/where.splice.pull")])
        self.assertIn("the name of a load case holds no /", said["findings"][0]["why"])

    def test_no_line_of_the_grid_is_named_as_the_cells_of_unread_fields_are(self):
        """A rule `x/area` for a mechanism `unread` of a pad would give the cell p1/unread/area,
        which is also the cell of the pad's area when nothing reads it."""
        def unread(rules: dict) -> None:
            rules["grid"].append({"type": "pad", "mechanism": "unread", "what": "made up", "anchor": ANCHOR})
        said = ask(with_deck(strips(), unread))
        self.assertIn("grid unread: no mechanism is named unread", findings(said))
        body = copy.deepcopy(STRIPS)
        unread(body)
        with self.assertRaises(grid.DeckError):
            grid.read_deck(json.dumps(body))


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

    def test_the_grid_refuses_a_text_with_the_replacement_character_or_half_a_pair(self):
        self.refused(lambda b: b["types"][0].update(what="a pad�"))
        self.refused(lambda b: b["types"][0].update(what="a pad\ud800"))
        self.refused(lambda b: b["rules"][0].update({"let": {"k\udfff": "1"}}))
        body = copy.deepcopy(STRIPS)
        body["types"][0]["what"] = "a face \U0001F600"
        self.assertEqual(grid.read_deck(json.dumps(body)).name, "test-strips", "a pair that is one character is read")

    def test_the_grid_refuses_an_anchor_that_names_something_that_is_no_text(self):
        self.refused(lambda b: b["rules"][0]["anchor"].update(equation=5))
        self.refused(lambda b: b["grid"][0]["anchor"].update(page=["12"]))
        self.refused(lambda b: b["rows"][0]["anchor"].update(table=None))

    def test_the_grid_reads_a_values_digits_and_blanks_as_the_kernel_does(self):
        """Digits are 0 to 9, and what is dropped around a value is space, tab and line end."""
        def ranged(value: str):
            return lambda b: b["rows"][0]["takes"][0].update(range=[value, "5 mm"])
        for value in ("١ ١/٢ mm", "0.5 mm ", " 0.5 mm"):
            with self.subTest(value=value):
                self.refused(ranged(value))
        self.refused(lambda b: b["rows"][0]["takes"][0].update(dim="length^١"))
        body = copy.deepcopy(STRIPS)
        ranged(" \t0.5 mm \r\n")(body)
        self.assertEqual(grid.read_deck(json.dumps(body)).name, "test-strips")


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Decks(unittest.TestCase):
    def test_a_where_that_is_there_has_an_item(self):
        """Item 11. With `where: []` the kernel wrote no range cell and proved the rule's cell."""
        said = ask(with_deck(strips(), empty_where))
        self.assertIn("rule test/heat: `where` has at least one item", findings(said))
        self.assertEqual(said["findings"][0]["file"], "rules")

    def test_two_rules_of_one_line_have_two_entries(self):
        """Item 12. `test/hole` and `other/hole` both answer strip.hole of a strip, and both
        cells were s/strip.hole/hole."""
        said = ask(with_deck(strips(), one_entry_twice))
        self.assertIn("two rules answer strip.hole of strip with ids that end in hole after the last /", findings(said))
        self.assertEqual(said["findings"][0]["file"], "rules")

    def test_what_an_anchor_names_is_text_and_a_rule_with_none_is_refused_in_plain_words(self):
        said = ask(with_deck(strips(), lambda r: r["rules"][0]["anchor"].update(equation=5)))
        self.assertIn("rule test/heat: the anchor's equation is not a text", findings(said))
        said = ask(with_deck(strips(), lambda r: r["rules"][0].pop("anchor")))
        self.assertIn("rule test/heat: it has no `anchor`", findings(said))
        self.assertNotIn("property not found", findings(said))

    def test_the_kernel_reads_a_values_digits_and_blanks_as_the_grid_does(self):
        def ranged(value: str):
            return lambda r: r["rows"][0]["takes"][0].update(range=[value, "5 mm"])
        for value in ("١ ١/٢ mm", "0.5 mm ", " 0.5 mm"):
            with self.subTest(value=value):
                self.assertIn("row test/limit", findings(ask(with_deck(strips(), ranged(value)))))
        self.assertEqual(ask(with_deck(strips(), ranged(" \t0.5 mm \r\n")))["verdict"], ask(strips())["verdict"])


def deck_of(rows=(), types=(), grid_lines=(), rules=()) -> dict:
    return {"format": "petra-rules/0", "name": "big", "about": "a", "rows": list(rows), "types": list(types), "grid": list(grid_lines), "rules": list(rules)}


def asks(kind: str = "t", mechanism: str = "m", **more) -> dict:
    return {"type": kind, "mechanism": mechanism, "what": "w", "anchor": ANCHOR, **more}


def rule_of(id_: str = "r/x", kind: str = "t", mechanism: str = "m", le=("f", "f"), **more) -> dict:
    return {"id": id_, "type": kind, "mechanism": mechanism, "anchor": ANCHOR, "says": "s", "le": list(le), **more}


LENGTH = {"name": "f", "dim": "length", "what": "w"}
ONE = [{"number": {"dim": "length", "lo": "1", "hi": "1"}}]
PLAIN = {"type": "t", "what": "w", "fields": [LENGTH]}


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Shapes(unittest.TestCase):
    """Inputs under 1 MB, each made for one loop of the kernel, found while the ten findings
    were closed. Each docstring says what the kernel at b4698ad took. A loop whose length an
    input sets is now either gone through once for each value of the file, or counted
    against a limit before it runs: the steps to read a deck, the steps to make the cells,
    or the work of the proofs. Each test holds the kernel to a refusal or to processor
    seconds and memory with a wide margin: every one of these takes under 2 seconds and
    under 110 MB."""

    def bounded(self, files: dict[str, str], megabytes: int = 128) -> dict:
        self.assertLess(total(files), 1.05 * MB)
        said, seconds, peak = measured(files)
        self.assertLess(seconds, PROCESSOR_SECONDS / 3, "processor seconds")
        self.assertLess(peak, megabytes * MB, "bytes held")
        return said

    def test_names_of_let_in_chains_of_powers(self):
        """30,000 names of `let`, each a power of the next. The reader kept hold of the table
        of names while it read the base of a power, so each name it added copied the table:
        21 s and 9.6 GB."""
        lets = {f"a{i}": "2" if i % 400 == 399 or i == 29_999 else ["pow", f"a{i + 1}", "2"] for i in range(30_000)}
        said = self.bounded(with_rules(deck_of(types=[PLAIN], grid_lines=[asks()], rules=[rule_of(let=lets)]), empty_card(), []))
        self.assertEqual((said["verdict"], said["findings"]), ("UNKNOWN", []))

    def test_a_list_of_many_names_is_gone_through_once(self):
        """A key of 38,000 names. The test that no name is there twice asked the table for a
        name while it put the name in, which copies the table: 10 s for one such list,
        whatever read it afterwards. With 8,500 parts that give the key a name it lacks, the
        list was also written out for each: 45 s."""
        names = [f"n{k}" for k in range(38_000)]
        kind = {"type": "t", "what": "w", "fields": [{"name": "k", "one_of": names, "what": "w"}]}
        parts = [{"name": f"p{i}", "type": "t", "lines": [{"field": "k", "args": [{"word": "zz"}]}]} for i in range(8_500)]
        said = self.bounded(with_rules(deck_of(types=[kind], grid_lines=[asks()]), empty_card(), parts))
        self.assertEqual((said["verdict"], len(said["findings"]), said["more_findings"]), ("ILL-FORMED", 100, 8_400))
        self.assertTrue(said["findings"][0]["why"].startswith("is one of: n0, n1, n2"))

    def test_rises_and_falls_that_name_a_side_many_times(self):
        """80,000 names in each list: every name of one was compared with every name of the other, 29 s."""
        row = {"id": "w", "anchor": ANCHOR, "gives": {"name": "y", "dim": "length"},
               "takes": [{"name": "D", "dim": "length", "range": ["1 m", "2 m"]}, {"name": "g", "one_of": ["a", "b"]}],
               "table": {"down": {"by": "D", "at": ["1 m"]}, "across": {"by": "g"}, "cells": [["1 m", "2 m"]],
                         "rises": ["D"] * 80_000, "falls": ["g"] * 80_000}}
        said = self.bounded(with_rules(deck_of(rows=[row], types=[PLAIN], grid_lines=[asks()], rules=[rule_of()]), empty_card(), []))
        self.assertEqual((said["verdict"], said["findings"]), ("UNKNOWN", []))

    def test_a_jump_between_many_cases(self):
        """A jump whose `cases` lists 150,000 numbers: each was compared with all before it, 72 s."""
        row = {"id": "w", "anchor": ANCHOR, "gives": {"name": "y", "dim": "length"}, "takes": [{"name": "x", "dim": "length", "range": ["1 m", "2 m"]}],
               "cases": [{"when": ["le", "x", ["q", "1", "m"]], "is": "x"}, {"is": "x"}], "jumps": [{"cases": list(range(150_000)), "why": "w"}]}
        said = self.bounded(with_rules(deck_of(rows=[row], types=[PLAIN], grid_lines=[asks()], rules=[rule_of()]), empty_card(), []))
        self.assertIn("row w: a jump names two of the row's cases by number, from 1, and says why", findings(said))

    def test_a_key_of_many_names_bound_many_times_is_over_the_steps_to_read(self):
        """A row with a key of 30,000 names, applied 9,000 times: each time, every name of the
        field was looked for among the row's, over a minute. The row is 60,000 names and
        cells, each two steps or three, and 9,000 times that is over the steps a deck may
        take to read."""
        names = [f"n{k}" for k in range(30_000)]
        row = {"id": "w", "anchor": ANCHOR, "gives": {"name": "y", "dim": "length"}, "takes": [{"name": "g", "one_of": names}],
               "table": {"down": {"by": "g"}, "cells": ["1 m"] * 30_000}}
        kind = {"type": "t", "what": "w", "fields": [LENGTH, {"name": "k", "one_of": names, "what": "w"}]}
        rule = rule_of(le=(["add"] + [["row", "w", {"g": "k"}] for _ in range(9_000)], "f"))
        rules = deck_of(rows=[row], types=[kind], grid_lines=[asks()], rules=[rule])
        said = self.bounded(with_rules(rules, empty_card(), []))
        self.assertGreater(grid._steps(rules), 1_000_000_000)
        self.assertIn(f"reading this deck takes {grid._steps(rules)} steps, over the budget of 1000000", findings(said), "the grid makes the same count")

    def test_many_rules_that_join_many_parts(self):
        """3,000 rules and 3,000 lines with a condition, for a type that joins 300 parts of a
        type of 300 fields: 90,000 names were made for each rule and each line, over a minute."""
        plate = {"type": "p", "what": "w", "fields": [{"name": f"f{k}", "dim": "length", "what": "w"} for k in range(300)]}
        lap = {"type": "lap", "what": "w", "fields": [{"name": "joins", "type": "p", "as": [f"a{k}" for k in range(300)], "what": "w"},
                                                      {"name": "k", "one_of": ["x", "y"], "what": "w"}]}
        lines = [asks("lap", f"m{i}", unless={"why": "", "when": ["is", "k", "x"]}) for i in range(3_000)]
        rules = [rule_of(f"r/{i}", "lap", f"m{i}", le=("a0.f0", "a1.f1")) for i in range(3_000)]
        said = self.bounded(with_rules(deck_of(types=[plate, lap], grid_lines=lines, rules=rules), empty_card(), []))
        self.assertEqual((said["verdict"], said["findings"]), ("UNKNOWN", []))

    def test_a_long_condition_for_many_parts_is_over_the_steps(self):
        """A line of the grid whose `unless` has 25,000 parts, for 5,000 parts of the design:
        125 million looks that nothing counted, over a minute. Each is a step now."""
        kind = {"type": "t", "what": "w", "fields": [LENGTH, {"name": "k", "one_of": ["x", "y"], "what": "w"}]}
        lines = [asks(unless={"why": "", "when": ["and"] + [["is", "k", "x"]] * 25_000})]
        parts = [{"name": f"p{i}", "type": "t", "lines": [{"field": "f", "args": ONE}, {"field": "k", "args": [{"word": "x"}]}]} for i in range(4_500)]
        said = self.bounded(with_rules(deck_of(types=[kind], grid_lines=lines), empty_card(), parts))
        self.assertEqual([(f["rule"], f["why"][:60]) for f in said["findings"]],
                         [("limits", "writing the tapes of this design from the deck of rules take")])

    def test_many_rules_that_are_for_no_part_are_over_the_steps(self):
        """1,200 rules of one line whose `when` has 25 parts and holds for no part, and 3,000
        parts: no cell came of them, so nothing counted the 90 million looks."""
        kind = {"type": "t", "what": "w", "fields": [LENGTH, {"name": "k", "one_of": ["x", "y"], "what": "w"}]}
        rules = [rule_of(f"r/{i}", when=["and"] + [["is", "k", "y"]] * 25) for i in range(1_200)]
        parts = [{"name": f"p{i}", "type": "t", "lines": [{"field": "f", "args": ONE}, {"field": "k", "args": [{"word": "x"}]}]} for i in range(3_000)]
        said = self.bounded(with_rules(deck_of(types=[kind], grid_lines=[asks()], rules=rules), empty_card(), parts))
        self.assertEqual([f["rule"] for f in said["findings"]], ["limits"])

    def test_empty_parts_of_a_type_of_many_fields_are_counted(self):
        """14,000 parts with no line, of a type of 9,000 fields: a finding for each field each
        part lacks, 126 million of them. Past the hundred it keeps, the kernel counts them
        from the sizes and does not go through them."""
        kind = {"type": "t", "what": "w", "fields": [{"name": f"f{k}", "dim": "length", "what": "w"} for k in range(9_000)]}
        parts = [{"name": f"p{i}", "type": "t", "lines": []} for i in range(14_000)]
        said = self.bounded(with_rules(deck_of(types=[kind]), empty_card(), parts))
        self.assertEqual((said["verdict"], len(said["findings"]), said["more_findings"]), ("ILL-FORMED", 100, 14_000 * 9_000 - 100))
        self.assertEqual((said["findings"][0]["item"], said["findings"][0]["why"], said["findings"][99]["why"]), ("p0", "lacks f0", "lacks f99"))

    def test_an_input_the_card_gives_many_times(self):
        """A design with no parts. The card gives one input 9,000 times and a tape reads it
        12,000 times: every reading was held to every giving, 2.8 s. The givings of a name
        are now held as the one range that contains them and the one they share."""
        inputs = [{"name": "x", "dim": "force", "lo": str(k % 7), "hi": str(10 + k % 5), "by": "b"} for k in range(9_000)]
        tape = {"inputs": [{"label": "in:c.x", "lo": "0", "hi": "14"}] * 12_000, "nodes": [["c", "-1"]], "roots": [0]}
        said = self.bounded(with_card([cell(tape)], inputs=inputs))
        self.assertEqual(said["verdict"], "PASS")
        narrow = dict(tape, inputs=[{"label": "in:c.x", "lo": "0", "hi": "13"}])
        (found,) = self.bounded(with_card([cell(narrow)], inputs=inputs))["cells"]
        self.assertEqual((found["state"], found["reason"]), ("open", "the tape's range for in:c.x does not contain the signed one"))
        point = {"subject": "s", "mechanism": "m", "entry": "e", "state": "refuted", "which": 0,
                 "tape": {"inputs": tape["inputs"][:1], "nodes": [["c", "1"]], "roots": [0]}}
        self.assertEqual(self.bounded(with_card([dict(point, point=["8"])], inputs=inputs))["verdict"], "FAIL", "8 is in every range")
        (found,) = self.bounded(with_card([dict(point, point=["5"])], inputs=inputs))["cells"]
        self.assertEqual((found["state"], found["reason"]), ("open", "the point is outside the signed range of input 0"), "5 is under a range that starts at 6")


SAME_HASH = 2 ** 63
"""Whole numbers that differ by a multiple of this had one hash in the kernel's tables, while it kept tables by a hash."""


def alike(k: int, lead: str = "n") -> str:
    """A name of 64 characters that shares its first 58 with every other such name."""
    return lead * 58 + f"{k:06d}"


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Alike(unittest.TestCase):
    """Inputs under about 1 MB whose keys are made to cost a table the most, added with the
    fourth review. That review found two tables kept by a hash that a file could work out:
    30,000 constants that shared it took 45 to 50 processor seconds to write, and 1,024 ends
    in a cache took 85 to 90 (tests/test_kernel_attacks4.py). Every table of the kernel is now
    kept in the order of its keys (docs/format.md, "Tables"), so a look costs the logarithm
    of the table whatever the keys are.

    The first tests are numbers that shared the old hash, in each table that holds numbers a
    file writes. The others are what costs a table kept in order the most: names that are
    alike to their last characters, and tapes of many different nodes. Each docstring says
    what the kernel took before the tables were kept in order, at 5714d9c, and each test
    holds the kernel to a third of its 30 processor seconds."""

    def bounded(self, files: dict[str, str], megabytes: int = 128) -> dict:
        self.assertLess(total(files), 1.12 * MB)
        said, seconds, peak = measured(files)
        self.assertLess(seconds, PROCESSOR_SECONDS / 3, "processor seconds")
        self.assertLess(peak, megabytes * MB, "bytes held")
        return said

    def table(self, body: dict, parts: int = 2) -> dict[str, str]:
        row = {"id": "h", "anchor": ANCHOR, "gives": {"name": "y", "dim": "dimensionless", "what": "w"},
               "takes": [{"name": "x", "dim": "dimensionless", "what": "w", "range": ["1", "2"]}], "table": body}
        kind = {"type": "t", "what": "w", "fields": [{"name": "f", "dim": "dimensionless", "what": "w"}]}
        rules = deck_of(rows=[row], types=[kind], grid_lines=[asks()], rules=[rule_of(le=(["row", "h", {"x": "f"}], "1"))])
        one = [{"number": {"dim": "dimensionless", "lo": "1", "hi": "1"}}]
        return with_rules(rules, empty_card(), [{"name": f"p{i}", "type": "t", "lines": [{"field": "f", "args": one}]} for i in range(parts)])

    def test_the_numbers_of_a_table_that_shared_a_hash(self):
        """30,000 numbers 1 + k 2^63 as the values a table is read at, as its cells, and as
        the ends of its bands, for two parts. Each is a constant of the tape. As listed
        values they took 46 processor seconds, and they take under one."""
        same = [str(1 + k * SAME_HASH) for k in range(30_000)]
        shapes = {"listed values": {"down": {"by": "x", "at": same}, "cells": ["1"] * 30_000},
                  "cells": {"down": {"by": "x", "at": [str(k + 1) for k in range(30_000)]}, "cells": same},
                  "bands": {"down": {"by": "x", "bands": [[same[k], same[k + 1]] for k in range(15_000)]}, "cells": ["1"] * 15_000}}
        for what, body in shapes.items():
            with self.subTest(what):
                said = self.bounded(self.table(body))
                self.assertEqual((said["verdict"], said["findings"], said["counts"]["open"], said["work"]), ("UNKNOWN", [], 2, 0))
                self.assertIn("over the budget of 1024 for one pick", said["cells"][0]["reason"])

    def test_the_floors_of_dimensions_whose_exponents_shared_a_hash(self):
        """deck.json with a floor for each of 16,000 dimensions m^(1 + k 2^64). The floors are
        kept by the exponents of their dimensions, and these shared a hash: 11.4 processor
        seconds, with no deck of rules and no cell, and 0.3 now."""
        card = text({"format": "petra-card/0", "name": "c", "environment": None, "cases": [], "claims": [], "waivers": [],
                     "inputs": [{"name": "x", "dim": f"m^{1 + 5 * 2 ** 64}", "lo": "-1", "hi": "1", "by": "b"}]})
        design = text({"format": "petra-design/0", "name": "d", "card": sha(card), "quantities": [], "params": []})
        domains = core_domains()
        domains["input"] = {**domains["input"], **{f"m^{1 + k * 2 ** 64}": {"min": "0", "strict": False} for k in range(16_000)}}
        files = {"card": card, "design": design, "deck": text({"format": "petra-deck/0", "domains": domains, "constants": []}),
                 "proofs": text({"format": "petra-proofs/0", "cells": []})}
        said = self.bounded(files)
        self.assertEqual([(f["rule"], f["item"]) for f in said["findings"]], [("types.4", "x")], "the input is found under the floor of its own dimension")

    def test_a_rule_that_reads_many_fields_of_a_joined_part_with_names_alike(self):
        """A rule sums 1,400 fields of the part its part joins, written for 1,150 load cases.
        The names of the fields, of the parts, of the card and of the design are as long as
        they may be and alike to their last characters, so every comparison of two of them
        reads to the end. 1.2 processor seconds before, and under one now: a rule reads a
        field in one step however often it names it, so a tape looks for no input."""
        fields = [alike(k, "f") for k in range(1_400)]
        leaf = {"type": "leaf", "what": "w", "fields": [{"name": name, "dim": "length", "what": "w"} for name in fields]}
        kind = {"type": "t", "what": "w", "fields": [{"name": "holds", "type": "leaf", "as": ["a"], "what": "w"}], "loads": [{"name": "L", "dim": "length", "what": "w"}]}
        sums = rule_of("r/sum", mechanism="sum", le=(["load", "L"], ["add"] + [f"a.{name}" for name in fields] + [f"a.{name}" for name in fields[:200]]))
        part, held, title = "p" * 64, "q" * 64, "c" * 200
        inputs = [{"name": f"i{c}", "dim": "length", "lo": "0", "hi": "1", "by": "b", "case": f"c{c}", "on": part, "field": "L"} for c in range(1_150)]
        parts = [{"name": held, "type": "leaf", "lines": [{"field": name, "args": ONE} for name in fields]},
                 {"name": part, "type": "t", "lines": [{"field": "holds", "args": [{"word": held}]}]}]
        hint = {"subject": part, "mechanism": "sum", "entry": "sum/c7", "state": "proved", "partition": "leaf"}
        said = self.bounded(with_rules(deck_of(types=[leaf, kind], grid_lines=[asks(mechanism="sum")], rules=[sums]), empty_card(inputs, title), parts, [hint], title))
        self.assertEqual((said["verdict"], said["findings"], said["counts"]["open"], said["counts"]["proved"]), ("UNKNOWN", [], 1_149, 1))
        self.assertEqual(said["dsg_inputs"], 1_400, "a field the rule names twice is one input of the tape")

    def test_tapes_of_many_different_nodes(self):
        """A rule of 100 chains of 400 names of `let`, each the one before negated, for 70
        parts: 2.8 million nodes written, each looked for among up to 40,000 others. This is
        the shape that a table kept in order costs most beside one kept by a hash: 1.3
        processor seconds before, and 2.3 now."""
        lets, ends = {}, []
        for c in range(100):
            lets[f"n{c}_0"] = ["mul", "f", str(c + 2)]
            lets.update({f"n{c}_{i}": ["neg", f"n{c}_{i - 1}"] for i in range(1, 400)})
            ends.append(f"n{c}_399")
        rules = deck_of(types=[PLAIN], grid_lines=[asks()], rules=[rule_of(le=(["add", *ends], "f"), let=lets)])
        said = self.bounded(with_rules(rules, empty_card(), [{"name": f"p{i}", "type": "t", "lines": [{"field": "f", "args": ONE}]} for i in range(70)]))
        self.assertEqual((said["verdict"], said["findings"], said["counts"]["open"]), ("UNKNOWN", [], 70))

    def test_parts_inputs_and_hints_with_names_alike(self):
        """1,600 parts that each join one of 1,600 others, a given of the card for each, and a
        hint for each, all with names of 64 characters that share their first 58. Every table
        of parts, of inputs and of hints is asked for each of them."""
        leaf = {"type": "leaf", "what": "w", "fields": [{"name": "f", "dim": "length", "signed": True, "what": "w"}]}
        kind = {"type": "t", "what": "w", "fields": [{"name": "holds", "type": "leaf", "as": ["a"], "what": "w"}]}
        rules = deck_of(types=[leaf, kind], grid_lines=[asks()], rules=[rule_of(le=("a.f", ["q", "2", "m"]))])
        count = 1_600
        parts = [{"name": alike(k, "q"), "type": "leaf", "lines": [{"field": "f", "args": [{"given": f"{alike(k, 'q')}.f"}]}]} for k in range(count)]
        parts += [{"name": alike(k, "p"), "type": "t", "lines": [{"field": "holds", "args": [{"word": alike(k, "q")}]}]} for k in range(count)]
        inputs = [{"name": f"{alike(k, 'q')}.f", "dim": "length", "lo": "1", "hi": "1", "by": "b"} for k in range(count)]
        hints = [{"subject": alike(k, "p"), "mechanism": "m", "entry": "x", "state": "proved", "partition": "leaf"} for k in range(count)]
        said = self.bounded(with_rules(rules, empty_card(inputs), parts, hints))
        self.assertEqual((said["verdict"], said["findings"], said["counts"]["proved"], said["ignored_hints"]), ("PASS", [], count, 0))


def applied(make) -> int:
    """How many times the deck `make(times)` may apply its row within the steps to read a
    deck. Each time adds as many steps as the one before."""
    none, once = grid._steps(make(0)), grid._steps(make(1))
    times = (1_000_000 - none) // (once - none)
    assert grid._steps(make(times)) <= 1_000_000 < grid._steps(make(times + 1))
    return times


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Numbers(unittest.TestCase):
    """A number of a deck is read eighteen digits at a time, and a text counts for its length
    in the steps to read a deck. Found after the ten findings were closed: a row of long
    numbers that a rule applied many times was within the steps, at one step a value, and
    took the kernel minutes, a microsecond for each digit each time."""

    def test_a_number_read_in_pieces_is_the_number_its_digits_write(self):
        """Each number is written whole and as its digits, one at a time, in names of `let`:
        the first digit, then ten times that and the second, and so on. A rule holds each to
        the other both ways, and a leaf proves both only when the two are equal. The lengths
        are on both sides of a piece of eighteen digits, and some pieces are all zeros or
        all nines."""
        rnd = random.Random(11)
        written = ["0", "7", "10", "9" * 17, "9" * 18, "9" * 19, "1" + "0" * 17, "1" + "0" * 18, "1" + "0" * 19, "1" + "0" * 35, "1" + "0" * 36, "1" + "0" * 37,
                   "5" + "0" * 17 + "9" * 18 + "0" * 18 + "3", "0" * 20 + "42", "123456789" * 13]
        written += ["".join(rnd.choice("0123456789") for _ in range(n)) for n in (17, 18, 19, 20, 35, 36, 37, 38, 53, 54, 55, 72, 73, 100)]
        lines, rules, hints = [], [], []
        for k, number in enumerate(written):
            lets = {"a0": ["add", number[0], "0"]}
            lets.update({f"a{i}": ["add", ["mul", f"a{i - 1}", "10"], digit] for i, digit in enumerate(number[1:], 1)})
            last = f"a{len(number) - 1}"
            for way, le in (("up", (number, last)), ("down", (last, number))):
                lines.append(asks(mechanism=f"n{k}.{way}"))
                rules.append(rule_of(f"r/{way}{k}", mechanism=f"n{k}.{way}", let=lets, le=(["mul", "f", le[0]], ["mul", "f", le[1]])))
                hints.append({"subject": "p", "mechanism": f"n{k}.{way}", "entry": f"{way}{k}", "state": "proved", "partition": "leaf"})
        parts = [{"name": "p", "type": "t", "lines": [{"field": "f", "args": ONE}]}]
        said = ask(with_rules(deck_of(types=[PLAIN], grid_lines=lines, rules=rules), empty_card(), parts, hints))
        self.assertEqual((said["verdict"], said["findings"], said["counts"]["proved"]), ("PASS", [], 2 * len(written)))
        off = rule_of("r/up0", mechanism="n0.up", le=(["mul", "f", "1" + "0" * 18], ["mul", "f", "9" * 18]))
        said = ask(with_rules(deck_of(types=[PLAIN], grid_lines=lines[:1], rules=[off]), empty_card(), parts, hints[:1]))
        self.assertEqual((said["verdict"], said["cells"][0]["reason"]), ("UNKNOWN", "leaf 0: root 0 is above zero"), "the next number up is more")

    def long_row(self, count: int, digits: int):
        rnd = random.Random(5)
        row = {"id": "w", "anchor": ANCHOR, "gives": {"name": "y", "dim": "dimensionless"}, "takes": [{"name": "x", "dim": "length", "range": ["1 m", "2 m"]}],
               "is": ["add"] + [str(rnd.randrange(10 ** (digits - 1), 10 ** digits)) for _ in range(count)]}
        return lambda times: deck_of(rows=[row], types=[PLAIN], grid_lines=[asks()],
                                     rules=[rule_of(let={f"v{i}": ["row", "w", {"x": "f"}] for i in range(times)})])

    def test_a_row_of_long_numbers_applied_many_times_is_over_the_steps_to_read(self):
        """A row that adds 200 numbers of 3,900 digits, and 4,500 names of `let` that each
        apply it and that nothing reads: 0.92 MB. At one step a value that was 900,000
        steps, within the million, and the kernel read each number again each time, a digit
        at a time: at b4698ad the row applied 400 times took 346 s, so these would take
        over an hour. A text is two steps and one for each 8 characters, so a number of
        3,900 digits is 489 steps and the deck 440 million."""
        rules = self.long_row(200, 3900)(4500)
        files = with_rules(rules, empty_card(), [])
        self.assertLess(total(files), MB)
        said, seconds, peak = measured(files)
        self.assertGreater(grid._steps(rules), 400_000_000)
        self.assertIn(f"reading this deck takes {grid._steps(rules)} steps, over the budget of 1000000", findings(said))
        self.assertLess(seconds, PROCESSOR_SECONDS / 10)

    def test_rows_of_numbers_applied_to_the_steps_to_read_are_read_in_time(self):
        """Rows of numbers of 3,900 digits, of 31 and of 7, each applied as often as the
        steps to read a deck allow. Each reads in 1 to 2.5 processor seconds and under
        100 MB, as a deck at the limit made of anything else does."""
        for count, digits in ((200, 3900), (20_000, 31), (5_000, 7)):
            with self.subTest(digits=digits):
                make = self.long_row(count, digits)
                rules = make(applied(make))
                self.assertGreater(grid._steps(rules), 900_000)
                files = with_rules(rules, empty_card(), [{"name": "p", "type": "t", "lines": [{"field": "f", "args": ONE}]}])
                self.assertLess(total(files), MB)
                said, seconds, peak = measured(files)
                self.assertEqual((said["verdict"], said["findings"], len(said["cells"])), ("UNKNOWN", [], 1))
                self.assertLess(seconds, PROCESSOR_SECONDS / 3)
                self.assertLess(peak, HALF_GB // 2)


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Worst(unittest.TestCase):
    """The input under 1 MB that takes the kernel longest and the one that makes it hold most,
    of those that could be built once every count was a limit. Each brings several limits to
    their edge at once. They took 10.2 processor seconds and 265 MB on the desktop the costs
    were fitted on (docs/format.md, "Work" and "What the kernel holds and prints"), of the 30
    seconds and the 512 MB that an input under 1 MB may take. The first took 11.7 before the
    kernel's tables were kept in order."""

    def test_a_deck_its_cells_and_a_proof_each_at_its_limit_answer_in_time(self):
        """Three rules for one part, each at a limit. `r/read` applies a row of 5,000 numbers
        94 times, which brings the deck to the million steps to read: a number is the text
        that costs most to read for its steps. `r/sum` sums 1,400 fields with names of 64
        characters, and is written for the 2,151 load cases that the ten million steps of
        the cells allow. The hinted proof of `r/big` spends the twenty billion units of work
        on `exp` of fractions of 250 bits, the step whose unit took longest in
        bench/work_sweep.py. The card, the design and the part have the longest names they
        may, which the label of every input of every tape holds. Alone, the three took 1.5,
        1.0 and 7.8 processor seconds."""
        fields = [f"f{k:063d}" for k in range(1_400)]
        part, title = "p" * 64, "c" * 200
        row = {"id": "w", "anchor": ANCHOR, "gives": {"name": "y", "dim": "dimensionless"}, "takes": [{"name": "x", "dim": "length", "range": ["1 m", "2 m"]}],
               "is": ["add"] + [str(1_000_000 + k) for k in range(5_000)]}
        kind = {"type": "t", "what": "w", "fields": [{"name": name, "dim": "length", "what": "w"} for name in fields] + [{"name": "g", "dim": "dimensionless", "what": "w"}],
                "loads": [{"name": "L", "dim": "length", "what": "w"}]}
        rnd = random.Random(3)
        lets = {f"q{i}": ["mul", "g", ["div", str(rnd.getrandbits(250) | 1 << 249 | 1), str(rnd.getrandbits(250) | 1 << 249 | 1)]] for i in range(64)}
        spends = rule_of("r/big", mechanism="big", let=lets, le=(["max"] + [["exp", f"q{i}"] for i in range(64)], "1000000"))
        sums = rule_of("r/sum", mechanism="sum", le=(["load", "L"], ["add"] + fields))

        def make(times: int) -> dict:
            reads = rule_of("r/read", mechanism="read", le=("1", ["add", "1"] + [f"v{i}" for i in range(times)]), let={f"v{i}": ["row", "w", {"x": fields[0]}] for i in range(times)})
            return deck_of(rows=[row], types=[kind], grid_lines=[asks(mechanism="sum"), asks(mechanism="read"), asks(mechanism="big")], rules=[sums, reads, spends])

        self.assertEqual(applied(make), 94)
        rules = make(94)
        lines = [{"field": name, "args": ONE} for name in fields] + [{"field": "g", "args": [{"number": {"dim": "dimensionless", "lo": "1", "hi": "2"}}]}]
        hint = {"subject": part, "mechanism": "big", "entry": "big", "state": "proved", "partition": halves(f"dsg:{title}.{part}.g", Fraction(1), Fraction(2), 400)}

        def files(cases: int) -> dict[str, str]:
            inputs = [{"name": f"i{c}", "dim": "length", "lo": "0", "hi": "1", "by": "b", "case": f"c{c}", "on": part, "field": "L"} for c in range(cases)]
            return with_rules(rules, empty_card(inputs, title), [{"name": part, "type": "t", "lines": lines}], [hint], title)

        over = measured(files(2_152))[0]
        self.assertEqual([f["rule"] for f in over["findings"]], ["limits"], "one more load case is over the steps of the cells")
        self.assertTrue(0.9 * MB < total(files(2_151)) < MB, total(files(2_151)))
        said, seconds, peak = measured(files(2_151))
        self.assertEqual((said["verdict"], said["findings"], len(said["cells"])), ("UNKNOWN", [], 2_151 + 2))
        self.assertRegex(said["cells"][-1]["reason"], r"^leaf \d+: node \d+: " + re.escape(COSTLY) + "$")
        self.assertGreater(said["work"], MAX_WORK * 99 // 100, "the proof stopped because the work ran out")
        self.assertLess(seconds, PROCESSOR_SECONDS, "it took 10.2 processor seconds")
        self.assertLess(peak, HALF_GB)

    def test_a_deck_a_proof_and_a_megabyte_of_lists_each_at_its_limit_are_held_in_bounded_memory(self):
        """A deck that takes the million steps to read, each two of them a number that the
        kernel keeps as a step of its rule. A hinted proof that keeps 4,080 enclosures of
        numbers of 65,400 bits, each the one before and 1 so that no two share a number, all
        read by one `min` so that none is given up before it: the kernel holds 16,777,216
        words of enclosures, and these are 4,089 words each. And the rest of the megabyte in
        lists nested 120 deep that the kernel parses and does not read."""
        long = Fraction((1 << 6540) - 1, (1 << 6539) + 1)
        row = {"id": "w", "anchor": ANCHOR, "gives": {"name": "y", "dim": "dimensionless"},
               "takes": [{"name": "x", "dim": "dimensionless", "range": ["1", "2"]}], "is": ["add"] + ["11"] * 5_000}
        kind = {"type": "t", "what": "w", "fields": [{"name": "f", "dim": "dimensionless", "what": "w"}]}
        kept = ["neg", ["abs", ["min"] + [f"c{k}" for k in range(4080)]]]

        def make(times: int) -> dict:
            lets = {f"v{i}": ["row", "w", {"x": "f"}] for i in range(times)}
            lets["c0"] = ["pow", ["div", str(long.numerator), str(long.denominator)], "10"]
            lets.update({f"c{k}": ["add", f"c{k - 1}", "1"] for k in range(1, 4080)})
            return deck_of(rows=[row], types=[kind], grid_lines=[asks()], rules=[rule_of(le=(kept, ["mul", "f", ["add"] + [f"v{i}" for i in range(times)]]), let=lets)])

        self.assertEqual(applied(make), 94)
        rules = make(94)
        deep: object = 0
        for _ in range(120):
            deep = [deep]
        parts = [{"name": "p", "type": "t", "lines": [{"field": "f", "args": [{"number": {"dim": "dimensionless", "lo": "1", "hi": "1"}}]}]}]
        hint = {"subject": "p", "mechanism": "m", "entry": "x", "state": "proved", "partition": "leaf", "junk": []}
        hint["junk"] = [deep] * ((999_000 - total(with_rules(rules, empty_card(), parts, [hint]))) // 242)
        files = with_rules(rules, empty_card(), parts, [hint])
        self.assertTrue(0.99 * MB < total(files) < MB, total(files))
        said, seconds, peak = measured(files)
        self.assertEqual((said["verdict"], said["findings"], said["counts"]["proved"]), ("PASS", [], 1), "every enclosure was held: the `min` read them all")
        self.assertLess(peak, HALF_GB, "it held 264 MB")
        self.assertLess(seconds, PROCESSOR_SECONDS)


if __name__ == "__main__":
    unittest.main()
