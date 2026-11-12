"""The fourth hostile review of petra-verify (kernel/), one test per reproduced finding.

Each test asserts the behaviour the kernel should have, and each fails against the kernel at
5714d9c (rework), where the review was made. The tests of the kernel are skipped when no
kernel is built. The ones marked "hostile deck" pass their own deck of rules with --rules.

  1  Hostile deck. A load case that puts some of the loads a rule reads on a part, and not
     all, is checked by no cell of the rule, and the line is not left open (Grid.lean,
     `cells`, `unders`; docs/format.md, "Cells from a deck of rules", item 4). A case of
     100 N on a joint that carries 10 N gets PASS, and petra/grid.py says PASS too. The
     same card without the case that carries both loads gets UNKNOWN.
  2  Hostile deck. A load of a type that no rule reads is no cell (Grid.lean, `cells`, the
     fields nothing reads; docs/format.md, item 8, names quantities and keys alone). A card
     that puts 1 MN of it on a joint that carries 10 N gets PASS, and so does petra/grid.py.
  3  Hostile deck. Lean hashes a whole number by its last 64 bits, and a fraction by the
     hashes of its numerator and its denominator, so the numbers 1 + k 2^63 all fall in
     one bucket of a table. Writing a tape finds each constant in such a table (Deck.lean,
     `node`, `Writing.seen`), so the constants of one table of a row cost the square of
     their number to write, and none of it is counted: 30,000 of them, 0.92 MB, 23 to 33
     processor seconds for each part of the rule's type, before any proof and with work 0.
  4  No deck. The caches of ln and exp (Num.lean, `Cache`) are keyed by the numerator and
     the denominator of an end, with the same hash. 1,024 ends that share it fill the cache
     of exp, and each later exp of one of them is charged as one look while the look walks
     the 1,024 and compares numbers of 32,000 bits: 0.97 MB, PASS, 85 to 89 processor
     seconds with work 18.2 billion.
  5  Hostile deck, petra/grid.py. Python hashes a whole number n as n mod (2^61 - 1), and
     `axis` (petra/deck.py) puts the values of a table's side in a set: 30,000 values that
     share a hash, 0.90 MB, take grid.read_deck 312 processor seconds. The kernel answers the
     same files in 1.2.

The classes after the review's own hold what was decided for 1 and 2 (docs/format.md, "Cells
from a deck of rules", items 4 and 8), case by case, and hold the kernel and petra/grid.py to
the same cells in each.
"""
import copy
import json
import math
import time
import unittest
from fractions import Fraction
from unittest import mock

import petra
from petra import grid, verify
from petra.registry import build_registry
from tests.test_kernel_attacks2 import MB, halves, measured, total
from tests.test_kernel_attacks3 import ANCHOR, PROCESSOR_SECONDS, empty_card, with_card, with_rules
from tests.test_kernel_grid import ask, changed, findings, strips

RULES = {
    "format": "petra-rules/0", "name": "pc", "about": "made up",
    "rows": [],
    "types": [{"type": "joint", "what": "a joint", "fields": [{"name": "cap", "dim": "force", "what": "what it carries"}],
               "loads": [{"name": "V", "dim": "force", "least": "0 N", "what": "shear"},
                         {"name": "T", "dim": "force", "least": "0 N", "what": "tension"}]}],
    "grid": [{"type": "joint", "mechanism": "joint.combined", "what": "shear and tension together", "anchor": ANCHOR}],
    "rules": [{"id": "pc/sum", "type": "joint", "mechanism": "joint.combined", "anchor": ANCHOR,
               "says": "the shear and the tension together are at most what the joint carries",
               "le": [["add", ["load", "V"], ["load", "T"]], "cap"]}],
}
DESIGN = "petra 0\n\njoint p {\n  cap 10 N\n}\n"
HEAD = 'petra 0\n\ncard "pc" {\n  owner "t@example.org"\n}\n'
GRAVITY = '\nload gravity {\n  on p V in [0 N, 1 N]\n  on p T in [0 N, 1 N]\n  signed "t@example.org" source "test"\n}\n'
WIND = '\nload wind {\n  on p V in [0 N, 100 N]\n  signed "t@example.org" source "test"\n}\n'
SHEAR = dict(RULES, rules=[{"id": "pc/shear", "type": "joint", "mechanism": "joint.combined", "anchor": ANCHOR,
                            "says": "the shear is at most what the joint carries", "le": [["load", "V"], "cap"]}])
"""The deck of RULES with one rule for the line, which reads V and not T."""
TENSION = '\nload gravity {\n  on p V in [0 N, 1 N]\n  on p T in [0 N, 1000000 N]\n  signed "t@example.org" source "test"\n}\n'


def grid_status(card: str, rules: dict = RULES) -> str:
    deck = grid.read_deck(json.dumps(rules))
    with mock.patch.object(grid, "decks", lambda: (deck,)):
        parsed = petra.lang.parse_design(card, DESIGN, "pc.petra", build_registry())
        return grid.check(parsed, deck)[0].status


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Cases(unittest.TestCase):
    def test_a_case_that_puts_some_of_the_loads_a_rule_reads_on_a_part_is_checked(self):
        """Finding 1, hostile deck. The rule reads V and T of the joint, V + T <= cap, and the
        cap is 10 N. Case wind puts V of up to 100 N on it and no T. With case wind alone the
        kernel leaves the rule open, as the card puts no T on the joint. With case gravity
        beside it, which puts up to 1 N of each on the joint, the kernel makes one cell,
        sum/gravity, proves it and says PASS: work 44,824, 0.1 processor seconds, 4 KB."""
        alone = ask(strips(HEAD + WIND, DESIGN, RULES))
        self.assertEqual(alone["verdict"], "UNKNOWN", "with no T in any case the rule is left open")
        said = ask(strips(HEAD + GRAVITY + WIND, DESIGN, RULES))
        self.assertEqual([(c["entry"], c["state"]) for c in said["cells"]][:1], [("sum/gravity", "proved")])
        self.assertNotEqual(said["verdict"], "PASS", "case wind puts 100 N on a joint that carries 10 N, and no cell checks it")

    def test_a_load_that_no_rule_reads_is_left_open(self):
        """Finding 2, hostile deck. The one rule of the line reads V alone, V <= cap; the type
        has a load T too, and the card puts 1 MN of it on the joint. The kernel makes one cell,
        shear/gravity, proves it and says PASS: work 34,196, 0.1 processor seconds, 3 KB. A
        field nothing reads is an open cell (docs/format.md, item 8), and a load is not."""
        said = ask(strips(HEAD + TENSION, DESIGN, SHEAR))
        self.assertEqual([(c["entry"], c["state"]) for c in said["cells"]][:1], [("shear/gravity", "proved")])
        self.assertNotEqual(said["verdict"], "PASS", "the card puts 1 MN of T on the joint, and no cell reads T")


class TheGridChecksTheSameCases(unittest.TestCase):
    """petra/grid.py, the second reading, makes the cells the kernel makes, and so the same."""

    def test_the_grid_checks_a_case_that_puts_some_of_the_loads_a_rule_reads_on_a_part(self):
        """Finding 1 in petra/grid.py, `_answers`: the cases are the intersection of the
        cases of each load the rule reads."""
        self.assertEqual(grid_status(HEAD + WIND), "UNKNOWN")
        self.assertNotEqual(grid_status(HEAD + GRAVITY + WIND), "PASS", "case wind is checked by no cell")

    def test_the_grid_leaves_open_a_load_that_no_rule_reads(self):
        """Finding 2 in petra/grid.py, `_unread`: it goes through the fields of a type alone."""
        self.assertNotEqual(grid_status(HEAD + TENSION, SHEAR), "PASS", "no cell reads T")


def both(test: unittest.TestCase, card: str, rules: dict = RULES, design: str = DESIGN) -> tuple[list[tuple[str, str, str, str]], str, dict]:
    """The cells of the pair as the kernel lists them and its verdict, after the test holds
    petra/grid.py to the same cells in the same order and to the same verdict. Also what the
    kernel said, for its reasons."""
    deck = grid.read_deck(json.dumps(rules))
    with mock.patch.object(grid, "decks", lambda: (deck,)):
        parsed = petra.lang.parse_design(card, design, "pc.petra", build_registry())
        report, files = grid.check(parsed, deck)
    said = ask(files)
    cells = [(c["subject"], c["mechanism"], c["entry"], c["state"]) for c in said["cells"]]
    test.assertEqual(said["findings"], [])
    test.assertEqual(cells, [(c.subject, c.mechanism, c.entry, c.state) for c in report.cells], "the kernel and the grid list the same cells")
    test.assertEqual(said["verdict"], report.verdict)
    return cells, said["verdict"], said


def reason(said: dict, entry: str, subject: str = "p") -> str:
    """Why the kernel left the part's cell of this entry open."""
    (found,) = [c for c in said["cells"] if (c["subject"], c["entry"]) == (subject, entry)]
    return found.get("reason", "")


def load(case: str, *lines: str) -> str:
    return f"\nload {case} {{\n" + "".join(f"  on {line}\n" for line in lines) + '  signed "t@example.org" source "test"\n}\n'


COMBINED = "joint.combined"
TWO = dict(RULES, rules=[
    {"id": "pc/shear", "type": "joint", "mechanism": COMBINED, "anchor": ANCHOR, "says": "the shear is at most what the joint carries",
     "le": [["load", "V"], "cap"]},
    {"id": "pc/tension", "type": "joint", "mechanism": COMBINED, "anchor": ANCHOR, "says": "the tension is at most what the joint carries",
     "le": [["load", "T"], "cap"]}])
"""The line answered by two rules, one for each load."""


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class ACellForEachCase(unittest.TestCase):
    """docs/format.md, "Cells from a deck of rules", item 4: a rule that reads loads has one
    cell for each load case of the card, and under a case that does not put every load it
    reads on the part the cell is open. petra/grid.py lists the same cells."""

    def test_a_case_that_puts_every_load_on_the_part_is_a_cell_as_before(self):
        cells, verdict, _ = both(self, HEAD + GRAVITY)
        self.assertEqual((cells, verdict), ([("p", COMBINED, "sum/gravity", "proved")], "PASS"))

    def test_two_cases_that_put_every_load_on_the_part_are_two_cells_in_the_order_of_their_names(self):
        cells, verdict, _ = both(self, HEAD + load("wind", "p V in [0 N, 2 N]", "p T in [0 N, 3 N]") + GRAVITY)
        self.assertEqual((cells, verdict), ([("p", COMBINED, "sum/gravity", "proved"), ("p", COMBINED, "sum/wind", "proved")], "PASS"))

    def test_a_case_that_puts_some_of_the_loads_on_the_part_is_an_open_cell_that_names_the_case_and_the_load(self):
        cells, verdict, said = both(self, HEAD + GRAVITY + WIND)
        self.assertEqual((cells, verdict), ([("p", COMBINED, "sum/gravity", "proved"), ("p", COMBINED, "sum/wind", "open")], "UNKNOWN"))
        self.assertEqual(reason(said, "sum/wind"), "case wind puts no T on p, which the rule reads")

    def test_a_case_that_puts_none_of_the_loads_on_the_part_is_an_open_cell_that_names_them(self):
        """Case wind is a case of the card, and puts nothing on the joint: an empty block in
        the card, or loads on another part alone."""
        for wind in (load("wind"), load("wind", "q V in [0 N, 1 N]", "q T in [0 N, 1 N]")):
            design = DESIGN + ("\njoint q {\n  cap 10 N\n}\n" if "on q" in wind else "")
            cells, verdict, said = both(self, HEAD + GRAVITY + wind, design=design)
            self.assertEqual(cells[:2], [("p", COMBINED, "sum/gravity", "proved"), ("p", COMBINED, "sum/wind", "open")])
            self.assertEqual(verdict, "UNKNOWN")
            self.assertEqual(reason(said, "sum/wind"), "case wind puts no V and no T on p, which the rule reads")
            if "on q" in wind:
                self.assertEqual(cells[2:], [("q", COMBINED, "sum/gravity", "open"), ("q", COMBINED, "sum/wind", "proved")])

    def test_a_load_of_zero_that_the_card_states_is_read_and_proved(self):
        """A card that means no tension in wind says so, and the cell is proved."""
        cells, verdict, _ = both(self, HEAD + GRAVITY + load("wind", "p V in [0 N, 9 N]", "p T in [0 N, 0 N]"))
        self.assertEqual((cells, verdict), ([("p", COMBINED, "sum/gravity", "proved"), ("p", COMBINED, "sum/wind", "proved")], "PASS"))
        cells, verdict, _ = both(self, HEAD + GRAVITY + load("wind", "p V in [0 N, 100 N]", "p T in [0 N, 0 N]"))
        self.assertEqual((cells, verdict), ([("p", COMBINED, "sum/gravity", "proved"), ("p", COMBINED, "sum/wind", "refuted")], "FAIL"))

    def test_two_rules_that_read_different_loads_each_have_a_cell_for_each_case(self):
        cells, verdict, said = both(self, HEAD + GRAVITY + WIND, TWO)
        self.assertEqual(cells, [("p", COMBINED, "shear/gravity", "proved"), ("p", COMBINED, "shear/wind", "refuted"),
                                 ("p", COMBINED, "tension/gravity", "proved"), ("p", COMBINED, "tension/wind", "open")])
        self.assertEqual(verdict, "FAIL")
        self.assertEqual(reason(said, "tension/wind"), "case wind puts no T on p, which the rule reads")

    def test_a_card_with_no_load_case_leaves_one_open_cell_with_no_case_in_its_entry(self):
        cells, verdict, said = both(self, HEAD)
        self.assertEqual((cells, verdict), ([("p", COMBINED, "sum", "open")], "UNKNOWN"))
        self.assertEqual(reason(said, "sum"), "the card puts no V and no T on p, which the rule reads")

    def test_a_rule_with_a_range_has_no_range_cell_under_a_case_that_lacks_a_load(self):
        ranged = dict(RULES, rules=[dict(RULES["rules"][0], where=[{"le": [["load", "V"], ["q", "50", "N"]], "why": "the shear is at most 50 N"}])])
        cells, verdict, _ = both(self, HEAD + GRAVITY + WIND, ranged)
        self.assertEqual(cells, [("p", COMBINED, "sum/gravity/where", "proved"), ("p", COMBINED, "sum/gravity", "proved"), ("p", COMBINED, "sum/wind", "open")])
        self.assertEqual(verdict, "UNKNOWN")

    def test_a_name_in_cases_that_no_load_has_is_a_load_case_of_the_card(self):
        """card.json lists `storm` in `cases` and has no load in it. The kernel reads the
        name as a case, as petra/grid.py reads an empty block of the card."""
        files = strips(HEAD + GRAVITY, DESIGN, RULES)
        said = ask(changed(files, "card", lambda card: card["cases"].append("storm")))
        self.assertEqual([(c["entry"], c["state"]) for c in said["cells"]], [("sum/gravity", "proved"), ("sum/storm", "open")])
        self.assertEqual(said["verdict"], "UNKNOWN")

    def test_the_case_of_a_load_is_a_load_case_whether_cases_lists_it_or_not(self):
        files = strips(HEAD + GRAVITY + WIND, DESIGN, RULES)
        said = ask(changed(files, "card", lambda card: card.update(cases=[])))
        self.assertEqual([(c["entry"], c["state"]) for c in said["cells"]], [("sum/gravity", "proved"), ("sum/wind", "open")])
        said = ask(changed(files, "card", lambda card: card.update(cases=["wind", "gravity", "wind"])))
        self.assertEqual([(c["entry"], c["state"]) for c in said["cells"]], [("sum/gravity", "proved"), ("sum/wind", "open")])

    def test_a_name_in_cases_is_held_to_what_the_case_of_a_load_is(self):
        files = strips(HEAD + GRAVITY, DESIGN, RULES)
        said = ask(changed(files, "card", lambda card: card["cases"].append("a/b")))
        self.assertIn("shape card cases: the name of a load case holds no /", findings(said))
        said = ask(changed(files, "card", lambda card: card["cases"].append("x" * 65)))
        self.assertIn("shape card cases: the name of a load case prints in at most 64 bytes", findings(said))
        with self.assertRaises(grid.ComponentError):
            grid_status(HEAD + GRAVITY + load("x" * 65))


JOINED = {
    "format": "petra-rules/0", "name": "pc", "about": "made up", "rows": [],
    "types": [RULES["types"][0],
              {"type": "holder", "what": "what holds a joint", "fields": [{"name": "grip", "dim": "force", "what": "what it grips with"},
                                                                         {"name": "holds", "type": "joint", "as": ["j"], "what": "its joint"}]}],
    "grid": [{"type": "holder", "mechanism": "holder.grip", "what": "the grip", "anchor": ANCHOR}],
    "rules": [{"id": "pc/grip", "type": "holder", "mechanism": "holder.grip", "anchor": ANCHOR, "says": "the joint carries at most the grip",
               "le": ["j.cap", "grip"]}],
}
"""A holder joins a joint and its one rule reads the joint's `cap`. The grid asks nothing of a joint."""


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class ALoadThatNothingReads(unittest.TestCase):
    """docs/format.md, item 8: a load the card puts on a part is read by an expression of a
    rule that applies to the part. Each one that nothing reads is an open cell named
    `unread`, with the entry LOAD/CASE. petra/grid.py lists the same cells."""

    def test_a_load_that_no_rule_reads_is_an_open_cell_for_each_case_that_puts_it_on_the_part(self):
        cells, verdict, said = both(self, HEAD + TENSION + load("wind", "p V in [0 N, 2 N]", "p T in [0 N, 3 N]"), SHEAR)
        self.assertEqual(cells, [("p", COMBINED, "shear/gravity", "proved"), ("p", COMBINED, "shear/wind", "proved"),
                                 ("p", "unread", "T/gravity", "open"), ("p", "unread", "T/wind", "open")])
        self.assertEqual(verdict, "UNKNOWN")
        self.assertEqual(reason(said, "T/wind"), "no rule of the deck reads the load T that case wind puts on p, so nothing checks it")

    def test_a_deck_whose_when_or_unless_asks_whether_a_load_is_there_is_refused(self):
        """Until the fifth review a `when` and an `unless` could ask `loaded`, which read
        nothing of the load. It held when any case of the card put the load on the part, so
        one case could switch a rule or a line off under every other. The condition is gone:
        a deck that asks it does not load, in petra/grid.py and in the kernel."""
        asked = dict(RULES, rules=[dict(SHEAR["rules"][0], when=["loaded", "T"])])
        excused = dict(SHEAR, grid=[dict(RULES["grid"][0], unless={"when": ["loaded", "T"], "why": "made up"})])
        for rules in (asked, excused):
            with self.assertRaises(grid.DeckError) as refused:
                grid.read_deck(json.dumps(rules))
            self.assertIn(grid.LOADED, str(refused.exception))
            said = ask(strips(HEAD + TENSION, DESIGN, SHEAR) | {"rules": json.dumps(rules)})
            self.assertIn("`loaded` is no condition: a condition is over keys", findings(said))
            self.assertEqual([f["file"] for f in said["findings"]], ["rules"])

    def test_the_loads_of_a_part_whose_line_is_waived_are_read_by_the_rule_of_the_line(self):
        """The rule of a waived line is run, and reads the loads as it reads the fields: no cell
        is named unread. A waiver rests a cell that would be open, and no other. Under gravity
        the card puts both loads on the joint and the rule proves, so the cell is proved and
        the waiver was not needed. Under wind the card states no tension, the cell would be
        open, and that cell is the one the waiver rests. Until then the line was one waived
        cell, and with nothing proved the verdict was UNKNOWN."""
        waived = HEAD.replace("}\n", '}\n\nwaive joint.combined on p by "t@example.org" reason "it is a test"\n', 1)
        cells, verdict, said = both(self, waived + GRAVITY + WIND)
        self.assertEqual((cells, verdict), ([("p", COMBINED, "sum/gravity", "proved"), ("p", COMBINED, "sum/wind", "waived")], "PASS"))
        self.assertEqual(next(c["reason"] for c in said["cells"] if c["state"] == "waived"), "open but for the waiver: case wind puts no T on p, which the rule reads")

    KEYED = dict(RULES, types=[dict(RULES["types"][0], fields=[*RULES["types"][0]["fields"], {"name": "kind", "one_of": ["plain", "tension"], "what": "what it is for"}])])
    """The deck of RULES with a key on the joint, for a `when` and an `unless` to ask about."""
    TENSION_JOINT = DESIGN.replace("  cap 10 N\n", "  cap 10 N\n  kind tension\n")

    def test_the_loads_of_a_part_whose_line_is_not_applicable_are_read_by_the_rule_of_the_line(self):
        excused = dict(self.KEYED, grid=[dict(RULES["grid"][0], unless={"when": ["is", "kind", "tension"], "why": "made up"})])
        cells, verdict, _ = both(self, HEAD + GRAVITY + WIND, excused, self.TENSION_JOINT)
        self.assertEqual((cells, verdict), ([("p", COMBINED, "", "not_applicable")], "UNKNOWN"))

    def test_the_loads_of_a_part_that_a_rule_does_not_apply_to_are_not_read_by_it(self):
        """The one rule holds for a plain joint, and this one is a tension joint: the line
        has no rule for it, and nothing reads its fields or its two loads."""
        slack = dict(self.KEYED, rules=[dict(RULES["rules"][0], when=["is", "kind", "plain"])])
        cells, verdict, _ = both(self, HEAD + GRAVITY, slack, self.TENSION_JOINT)
        self.assertEqual(cells, [("p", COMBINED, "", "open"), ("p", "unread", "cap", "open"), ("p", "unread", "kind", "open"),
                                 ("p", "unread", "T/gravity", "open"), ("p", "unread", "V/gravity", "open")])
        self.assertEqual(verdict, "UNKNOWN")

    def test_a_rule_of_the_part_that_joins_a_part_reads_its_fields_and_not_its_loads(self):
        """A rule names a load of its own type alone, so a load on a joined part is read by a
        rule of that part's type or by none."""
        design = DESIGN + "\nholder h {\n  grip 20 N\n  holds p\n}\n"
        cells, verdict, _ = both(self, HEAD + GRAVITY, JOINED, design)
        self.assertEqual(cells, [("h", "holder.grip", "grip", "proved"), ("p", "unread", "T/gravity", "open"), ("p", "unread", "V/gravity", "open")])
        self.assertEqual(verdict, "UNKNOWN")
        reaching = copy.deepcopy(JOINED)
        reaching["rules"][0]["le"] = [["load", "V"], "grip"]
        with self.assertRaises(grid.DeckError):
            grid.read_deck(json.dumps(reaching))
        self.assertIn("the type takes no load V", findings(ask(strips(HEAD + GRAVITY, design, JOINED) | {"rules": json.dumps(reaching)})))

    def test_the_cells_of_unread_fields_and_unread_loads_have_different_keys(self):
        """A type with a field and a load of one name, V, and no rule: the field's cell has
        the entry V and the load's V/gravity, and the kernel prints no key twice."""
        twin = {"format": "petra-rules/0", "name": "pc", "about": "made up", "rows": [],
                "types": [{"type": "joint", "what": "a joint", "fields": [{"name": "V", "dim": "force", "what": "a field"}],
                           "loads": [{"name": "V", "dim": "force", "least": "0 N", "what": "a load"}]}],
                "grid": [], "rules": []}
        cells, verdict, _ = both(self, HEAD + load("gravity", "p V in [0 N, 1 N]"), twin, "petra 0\n\njoint p {\n  V 10 N\n}\n")
        self.assertEqual((cells, verdict), ([("p", "unread", "V", "open"), ("p", "unread", "V/gravity", "open")], "UNKNOWN"))


STEP = 2 ** 63
"""Whole numbers that differ by a multiple of this have one hash in Lean."""


def colliding(n: int, parts: int) -> dict[str, str]:
    """A row whose table lists `n` values of x that share a hash, read by one rule, and
    `parts` parts of the rule's type."""
    row = {"id": "h", "anchor": ANCHOR, "gives": {"name": "y", "dim": "dimensionless", "what": "w"},
           "takes": [{"name": "x", "dim": "dimensionless", "what": "w", "range": ["1", "2"]}],
           "table": {"down": {"by": "x", "at": [str(1 + k * STEP) for k in range(n)]}, "cells": ["1"] * n}}
    kind = {"type": "t", "what": "w", "fields": [{"name": "f", "dim": "dimensionless", "what": "w"}]}
    rule = {"id": "r/x", "type": "t", "mechanism": "m", "anchor": ANCHOR, "says": "s",
            "le": [["row", "h", {"x": "f"}], "1"]}
    rules = {"format": "petra-rules/0", "name": "collide", "about": "a", "rows": [row], "types": [kind],
             "grid": [{"type": "t", "mechanism": "m", "what": "w", "anchor": ANCHOR}], "rules": [rule]}
    one = lambda i: {"name": f"p{i}", "type": "t",
                     "lines": [{"field": "f", "args": [{"number": {"dim": "dimensionless", "lo": "1", "hi": "1"}}]}]}
    return with_rules(rules, empty_card(), [one(i) for i in range(parts)])


BITS = 32_000
Q = 2 ** BITS - 1


def ends(n: int) -> list[int]:
    """The first `n` whole numbers k with no factor in common with Q: x_k = 1 + k 2^(BITS/2) / Q
    then has the denominator Q, and the numerator Q + k 2^(BITS/2), whose last 64 bits are Q's."""
    return [k for k in range(1, 8 * n) if math.gcd(k, Q) == 1][:n]


def exp_cell(entry: str, filled: int, chosen: int, exps: int, leaves: int) -> dict:
    """A proved cell whose tape makes x_k for the first `chosen` of the `filled` ends, and has
    `exps` roots -exp(x_k), going round them, over `leaves` leaves."""
    nodes = [["c", str(2 ** (BITS // 4))], ["pow", 0, 4], ["c", "-1"], ["add", [1, 2]], ["pow", 0, 2], ["div", 4, 3], ["c", "1"]]
    xs = []
    for k in ends(filled)[:chosen]:
        nodes += [["c", str(k)], ["mul", [len(nodes), 5]], ["add", [6, len(nodes) + 1]]]
        xs.append(len(nodes) - 1)
    roots = []
    for i in range(exps):
        nodes += [["exp", xs[i % len(xs)]], ["neg", len(nodes)]]
        roots.append(len(nodes) - 1)
    tape = {"inputs": [{"label": "dsg:x", "lo": "0", "hi": str(leaves)}], "nodes": nodes, "roots": roots}
    return {"subject": "s", "mechanism": "m", "entry": entry, "state": "proved", "tape": tape,
            "partition": halves(0, Fraction(0), Fraction(leaves), leaves)}


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Time(unittest.TestCase):
    def test_constants_that_share_a_hash_are_written_in_time(self):
        """Finding 3, hostile deck. 30,000 values of a table's `at` that are 1 + k 2^63, and two
        parts: 0.92 MB, UNKNOWN with work 0 and one open cell for each part (the table compares
        60,000 orders, over the 1,024 of one pick), 46 MB. Two parts took 49.8 and 46.8
        processor seconds on a quiet desktop and 156.5, 81.3 and 48.8 on a busy one; one part
        32.5, 23.1 and 27.9, and four parts 92.3, busy. The same table with values of the same
        length that do not share a hash took 1.2 processor seconds for three parts.

        Since the eighth review such a deck is refused when it is read, and no tape is written.
        A table of 512 such values is a pick of 1,024 orders, as many as a pick may compare: it
        is read, and the tapes of a thousand parts are written in time. The card gives no work,
        so each cell is open, as each was before."""
        files = colliding(30_000, 2)
        self.assertLess(total(files), MB)
        said, seconds, _ = measured(files, timeout=600)
        self.assertEqual((said["verdict"], [f["file"] for f in said["findings"]]), ("ILL-FORMED", ["rules"]))
        self.assertIn("would compare 60000 orders, over the budget of 1024", said["findings"][0]["why"])
        self.assertLess(seconds, PROCESSOR_SECONDS, "the deck is refused in about a processor second")
        said, seconds, _ = measured(colliding(512, 1_000), timeout=600)
        self.assertEqual((said["verdict"], said["counts"]["open"], said["work"]), ("UNKNOWN", 1_000, 0))
        self.assertLess(seconds, PROCESSOR_SECONDS, "the tapes are written in time")

    def test_ends_that_share_a_hash_are_looked_up_in_the_caches_in_time(self):
        """Finding 4, no deck. Cell `fill` takes exp of 1,024 ends x_k = (Q + k 2^16000) / Q,
        Q = 2^32000 - 1, which share a hash, and proves, so the cache of exp is full and kept.
        Cell `hit` takes exp of x_1 30,000 times on each of 11 leaves. Each is charged as a
        look in the cache, and each look walks the 1,024 ends and compares numbers of 32,000
        bits that differ in a few bits in the middle. 0.97 MB: PASS, work 18.2 billion, 89.0,
        85.7 and 84.9 processor seconds on a quiet desktop, 76 MB. With 4 leaves, work 8.9
        billion: 34.2 quiet, 56.0 to 106.4 busy. With 4 leaves and without cell `fill`: work
        5.3 billion, 2.1 processor seconds."""
        files = with_card([exp_cell("fill", 1024, 1024, 1024, 1), exp_cell("hit", 1024, 1, 30_000, 11)])
        self.assertLess(total(files), MB)
        said, seconds, _ = measured(files, timeout=1200)
        self.assertEqual((said["verdict"], said["counts"]["proved"], said["work"] < 20 * 10 ** 9), ("PASS", 2, True))
        self.assertLess(seconds, PROCESSOR_SECONDS, "the work is 18 billion units, which take about 7 processor seconds")


class TheGridReadsInTime(unittest.TestCase):
    def test_values_that_share_a_hash_in_python_are_read_in_time(self):
        """Finding 5, hostile deck, petra/grid.py. Python hashes a whole number n as n mod
        (2^61 - 1), so the numbers 1 + k (2^61 - 1) share one, and `axis` (petra/deck.py)
        puts the values of a table's side in a set to see that each is there once. 30,000 of
        them, 0.90 MB: grid.read_deck took 312 processor seconds, where the kernel answers the
        same files in 1.2 and the values 1 + k 2^63 of finding 3 are read in 1.8. 12,000 took
        53 busy and 39.3 and 34.5 quiet; 16,000 are read here. No rule reads the row, since a
        rule that read it would write a pick over the 1,024 orders, and the deck is refused
        then."""
        body = json.loads(colliding(16_000, 1)["rules"])
        body["rows"][0]["table"]["down"]["at"] = [str(1 + k * (2 ** 61 - 1)) for k in range(16_000)]
        body["rules"] = []
        started = time.process_time()
        grid.read_deck(json.dumps(body))
        self.assertLess(time.process_time() - started, PROCESSOR_SECONDS, "the values are read in about a processor second")

    def test_dimensions_that_share_a_hash_in_python_are_compared_in_time(self):
        """Finding 5 again, in `same` (petra/deck.py), which put the dimensions of a sum in a
        set. A dimension is its exponents, and a deck writes one as `length^N` with any whole
        N. 12,000 fields of dimensions length^(1 + k (2^61 - 1)) under one `add`, 0.98 MB:
        grid.read_deck took 54 processor seconds to refuse the sum, and takes 1.4."""
        names = [f"x{k}" for k in range(12_000)]
        kind = {"type": "t", "what": "w", "fields": [{"name": name, "dim": f"length^{1 + k * PYTHON_STEP}", "what": "w"} for k, name in enumerate(names)]}
        rule = {"id": "r/x", "type": "t", "mechanism": "m", "anchor": ANCHOR, "says": "s", "le": [["add", *names], "1"]}
        body = json.dumps(dict(BARE, types=[kind], grid=[{"type": "t", "mechanism": "m", "what": "w", "anchor": ANCHOR}], rules=[rule]))
        self.assertLess(len(body), MB)
        started = time.process_time()
        with self.assertRaisesRegex(grid.DeckError, "rule r/x: add of length and m\\^2305843009213693952"):
            grid.read_deck(body)
        self.assertLess(time.process_time() - started, PROCESSOR_SECONDS, "the sum is refused in about a processor second")


PYTHON_STEP = 2 ** 61 - 1
"""Whole numbers that differ by a multiple of this have one hash in Python."""
BARE = {"format": "petra-rules/0", "name": "collide", "about": "a", "rows": [], "types": [], "grid": [], "rules": []}
PLAIN = {"type": "t", "what": "w", "fields": [{"name": "f", "dim": "dimensionless", "what": "w"}]}


def row_of(**more) -> dict:
    return {"id": "h", "anchor": ANCHOR, "gives": {"name": "y", "dim": "dimensionless", "what": "w"},
            "takes": [{"name": "x", "dim": "dimensionless", "what": "w", "range": ["1", "2"]}], **more}


class NoTableOfTheGridIsKeyedByANumberOfTheFile(unittest.TestCase):
    """petra/grid.py and petra/deck.py key their tables by texts, which Python hashes with a
    key no file knows, and by no number a deck writes. A deck that writes a whole number
    where a name goes is refused before the number keys anything, as the kernel refuses it:
    there a name is a JSON string."""

    SAME = [1 + k * PYTHON_STEP for k in range(12_000)]
    DECKS = {
        "the name of a type": (dict(BARE, types=[{"type": v, "what": "w", "fields": []} for v in SAME]), "the name of a type is a text"),
        "the name of a mechanism": (dict(BARE, types=[PLAIN], grid=[{"type": "t", "mechanism": v, "what": "w", "anchor": ANCHOR} for v in SAME]),
                                    "a line has a type of the deck, mechanism"),
        "the name of an input of a row": (dict(BARE, types=[PLAIN], rows=[dict(row_of(**{"is": "1"}), takes=[
            {"name": v, "dim": "dimensionless", "what": "w", "range": ["1", "2"]} for v in SAME])]), "an input has a name, a text"),
        "the cases of a jump": (dict(BARE, types=[PLAIN], rows=[row_of(cases=[{"when": ["le", "x", "1"], "is": "1"}, {"is": "2"}],
                                                                       jumps=[{"cases": [v, 2], "why": "w"} for v in SAME])]),
                                "a jump names two of the row's cases by number"),
        "the sides a table rises along": (dict(BARE, types=[PLAIN], rows=[row_of(table={"down": {"by": "x", "at": ["1"]}, "cells": ["1"], "rises": SAME})]),
                                          "`rises` and `falls` name sides of the table"),
        "the names of joined parts": (dict(BARE, types=[{"type": "t", "what": "w", "fields": [{"name": "f", "type": "u", "as": SAME, "what": "w"}]},
                                                        {"type": "u", "what": "w", "fields": []}]), "`as` names each part once"),
    }

    def test_a_deck_with_whole_numbers_that_share_a_hash_where_names_go_is_refused_in_time(self):
        for what, (body, why) in self.DECKS.items():
            with self.subTest(what):
                text = json.dumps(body)
                started = time.process_time()
                with self.assertRaisesRegex(grid.DeckError, why):
                    grid.read_deck(text)
                self.assertLess(time.process_time() - started, PROCESSOR_SECONDS / 10, "the deck is refused in a fraction of a processor second")

    @unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
    def test_the_kernel_refuses_the_same_decks(self):
        for what, (body, _) in self.DECKS.items():
            with self.subTest(what):
                said, seconds, _ = measured(with_rules(body, empty_card(), []))
                self.assertEqual((said["verdict"], [f["file"] for f in said["findings"]]), ("ILL-FORMED", ["rules"]))
                self.assertLess(seconds, PROCESSOR_SECONDS)

    def test_a_map_of_a_by_with_whole_numbers_for_the_rows_names_is_refused(self):
        names = [f"k{k}" for k in range(12_000)]
        row = dict(row_of(table={"down": {"by": "g"}, "cells": ["1", "2"]}), takes=[{"name": "g", "one_of": ["a", "b"], "what": "w"}])
        rule = {"id": "r/x", "type": "t", "mechanism": "m", "anchor": ANCHOR, "says": "s",
                "le": [["row", "h", {"g": ["by", "key", dict(zip(names, self.SAME))]}], "1"]}
        body = dict(BARE, rows=[row], types=[{"type": "t", "what": "w", "fields": [{"name": "key", "one_of": names, "what": "w"}]}],
                    grid=[{"type": "t", "mechanism": "m", "what": "w", "anchor": ANCHOR}], rules=[rule])
        started = time.process_time()
        with self.assertRaisesRegex(grid.DeckError, "`by` gives one of the row's names for each name of key"):
            grid.read_deck(json.dumps(body))
        self.assertLess(time.process_time() - started, PROCESSOR_SECONDS / 10)

    def test_a_whole_number_too_long_for_python_to_read_is_a_deck_that_does_not_hold_together(self):
        """Python reads no whole number of more than 4,300 digits, and its JSON reader raises
        a ValueError for one. grid.read_deck let that through as it was."""
        with self.assertRaisesRegex(grid.DeckError, "not a deck"):
            grid.read_deck('{"format": "petra-rules/0", "name": ' + "1" * 5000 + "}")

    def test_the_caches_of_ln_and_exp_are_keyed_by_the_text_of_an_end(self):
        """petra/kernel/interval.py kept the ends it had rounded under the ends themselves,
        which are fractions a tape computes from a file's numbers. Two ends that share a hash
        are two entries, and each has its own value."""
        from petra.kernel import interval

        ends = [Fraction(1 + k * PYTHON_STEP, 3) for k in (1, 2, 4)]
        self.assertEqual(len({hash(x) for x in ends}), 1, "the three ends share a hash")
        for cached, point, at in ((interval._ln_cached, interval._ln_point, interval._ln_at), (interval._exp_cached, interval._exp_point, interval._exp_at)):
            ends_here = ends if point is interval._ln_point else [x / 10 ** 18 for x in ends]
            before = cached.cache_info().currsize
            self.assertEqual([point(x) for x in ends_here], [interval._grid(at, x) for x in ends_here])
            self.assertEqual(cached.cache_info().currsize - before, 3)
            self.assertEqual({type(key) for key in map(interval._text, ends_here)}, {str})


if __name__ == "__main__":
    unittest.main()
