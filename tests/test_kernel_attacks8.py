"""The eighth hostile review of petra-verify (kernel/) and petra/grid.py: designs that a rule
fails whatever is missing, which a waiver rested because something was missing. One test per
finding.

  F1  The shipped deck's Table J3.3 listed holes for bolts to 1 inch, and not its last line,
      d + 1/8 for 1 1/8 inch and more. A lap of two 1 1/8 inch bolts whose shear alone fails
      by 2.5 times had a strength cell with no value, which a waiver rested: PASS_WAIVED. Tables
      J3.3 and J3.4 now list what their last lines give to 1 1/2 inch, and the lap FAILs.
  D1  A waiver rested a cell because something was missing: a key the part left unstated, a
      load a case left out, a table with no line for the part. It rested it though the rule
      failed whatever the missing piece was: a pin that both coatings fail, a bolt whose
      shear alone fails under a case that leaves the tension out, a table gap inside a `min`
      whose other term already fails, a `requires` that no coating meets. Now a waiver rests
      an unstated key or a left-out load only under a completion that a hint names and under
      which the rule holds, the completions of the rested cells agree, a cell that every name
      of its keys fails is refuted, and a table with no line for the part is not rested.
  F2  A `case` on a row that names the class of a weld, whose branch for one class reads a
      table with no line for the weld's grade. The weld was of the other class, and that
      class's branch fails the rule, but the readers wrote every branch, so the empty one sank
      the whole tape, the cell was open and a waiver rested it. A branch that cannot be written
      is now a case with no value inside the pick.
  F3  A table of 600 listed sizes is a pick of 1,200 orders. The kernel would not write a pick
      of more than 1,024 and left the cell open, which a waiver rested, and the grid wrote it and
      refuted the rule: a FAIL that the kernel passed, and a design that keeps the rule ended in
      a Disagreement. Both readers now refuse such a deck when they read it.
  F4  A design whose one line is waived, and whose only proved cell is the `/where` cell of
      that line's rule: the range the rule holds in. That cell counted as the one proved cell a
      PASS needs, so the design passed with nothing it was asked answered.
"""
import json
import math
import unittest
from fractions import Fraction

import petra
from petra import grid, verify
from tests.test_deck_features import (ANCHOR, HEAD, KERNEL, asks, cells, design, given, key, kind, load, made_up, no_deck, parsed, part, reads, reason,
                                      rule, size)
from tests.test_kernel_grid import ask


def waive(mechanism: str, on: str) -> str:
    return f'\nwaive {mechanism} on {on} by "t@example.org" reason "test"\n'


# --- D1. what a part or a case leaves out ---------------------------------------------------------------

COATING = {**key("coating", "zinc", "none"), "optional": True}
PIN = kind("pin", size("d"), size("fy", "stress"), COATING, loads=[{"name": "shear", "dim": "force", "what": "shear on the pin", "least": "0 kN"}])
CAPACITY = ["mul", "0.6", "fy", ["div", ["mul", "pi", "d", "d"], "4"]]
"""0.6 x 240 MPa x pi x (10 mm)^2 / 4 = 11.31 kN for the pin below: 10.18 kN coated, 9.05 kN bare."""
FACTOR = {"id": "made-up/factor", "anchor": ANCHOR, "gives": {"name": "k", "dim": "dimensionless", "what": "a factor of a coating"},
          "takes": [{"name": "coating", "one_of": ["zinc", "none"], "what": "coating"}],
          "table": {"down": {"by": "coating"}, "unit": "1", "cells": ["0.9", "0.8"]}}


def pins(*rules: dict, rows: tuple = ()) -> dict:
    return made_up([PIN], [asks("pin.shear", "pin"), asks("pin.size", "pin")], [*rules, rule("size", "pin", "pin.size", le=[["q", "6", "mm"], "d"])], rows)


BY_WHEN = pins(rule("shear-coated", "pin", "pin.shear", when=["is", "coating", "zinc"], le=[["load", "shear"], ["mul", "0.9", CAPACITY]]),
               rule("shear-bare", "pin", "pin.shear", when=["is", "coating", "none"], le=[["load", "shear"], ["mul", "0.8", CAPACITY]]))
"""Two rules whose `when` covers the two coatings."""
BY_TABLE = pins(rule("shear", "pin", "pin.shear", le=[["load", "shear"], ["mul", ["row", "made-up/factor", {"coating": "coating"}], CAPACITY]]), rows=(FACTOR,))
"""One rule that reads the coating's factor in a table."""


def pin(shear: str, waived: bool = True, coating: str = "unstated") -> tuple[str, str]:
    card = HEAD + given("p.fy", "240 MPa") + load("service", f"p shear in [{shear}, {shear}]") + (waive("pin.shear", "p") if waived else "")
    return design(part("pin", "p", d="10 mm", fy="given p.fy", coating=coating)), card


BOLT = kind("bolt", size("area", "area"), size("fu", "stress"),
            loads=[{"name": "shear", "dim": "force", "what": "shear", "least": "0 kN"}, {"name": "tension", "dim": "force", "what": "tension", "least": "0 kN"}])
INTERACTION = made_up([BOLT], [asks("bolt.combined", "bolt"), asks("bolt.size", "bolt")],
                      [rule("interaction", "bolt", "bolt.combined",
                            le=[["add", ["div", ["load", "shear"], ["mul", "0.45", "fu", "area"]], ["div", ["load", "tension"], ["mul", "0.75", "fu", "area"]]], "1"]),
                       rule("area", "bolt", "bolt.size", le=[["q", "50", "mm2"], "area"])])
"""0.45 x 800 MPa x 157 mm2 = 56.5 kN of shear alone, and 94.2 kN of tension alone."""


def bolt(wind: str) -> tuple[str, str]:
    card = (HEAD + given("b.fu", "800 MPa") + load("gravity", "b shear in [10 kN, 10 kN]", "b tension in [5 kN, 5 kN]")
            + load("wind", f"b shear in [{wind}, {wind}]") + waive("bolt.combined", "b"))
    return design(part("bolt", "b", area="157 mm2", fu="given b.fu")), card


class WhatIsLeftOut(unittest.TestCase):
    def test_a_rule_that_every_name_of_an_unstated_key_fails_is_refuted(self):
        for waived in (True, False):
            found, status, _ = cells(self, BY_TABLE, *pin("20 kN", waived))
            self.assertEqual((found[("p", "pin.shear", "shear/service")], status), ("refuted", "FAIL"))

    def test_a_rule_that_one_name_meets_is_waived_under_that_name_or_open(self):
        # 9.5 kN: the coated pin carries 10.18 kN and the bare one 9.05 kN.
        found, status, said = cells(self, BY_TABLE, *pin("9.5 kN"))
        self.assertEqual((found[("p", "pin.shear", "shear/service")], status), ("waived", grid.PASS_WAIVED))
        self.assertTrue(reason(said, "pin.shear").startswith(grid.WAIVED), reason(said, "pin.shear"))
        found, status, said = cells(self, BY_TABLE, *pin("9.5 kN", waived=False))
        self.assertEqual((found[("p", "pin.shear", "shear/service")], status), ("open", "UNKNOWN"))

    def test_two_rules_whose_whens_cover_an_unstated_key_and_both_fail_are_not_passed(self):
        # The coated rule rests when the pin is bare, and the bare rule when it is coated: the
        # two completions disagree, so the second cell is not rested.
        found, status, said = cells(self, BY_WHEN, *pin("20 kN"))
        self.assertEqual(([found[("p", "pin.shear", e)] for e in ("shear-coated/service", "shear-bare/service")], status), (["waived", "open"], "UNKNOWN"))
        self.assertTrue(reason(said, "pin.shear", "shear-bare/service").startswith(grid.UNRESTED))

    def test_two_rules_whose_whens_cover_an_unstated_key_rest_under_one_name_that_holds(self):
        # 9.5 kN: under zinc the coated rule holds and the bare one does not answer.
        found, status, _ = cells(self, BY_WHEN, *pin("9.5 kN"))
        self.assertEqual(([found[("p", "pin.shear", e)] for e in ("shear-coated/service", "shear-bare/service")], status), (["waived", "waived"], grid.PASS_WAIVED))

    def test_a_stated_key_is_decided_as_before(self):
        for coating, verdict in (("zinc", "PASS"), ("none", "FAIL")):
            found, status, _ = cells(self, BY_TABLE, *pin("9.5 kN", coating=coating))
            self.assertEqual(status, verdict, coating)

    def test_a_requires_that_no_name_of_an_unstated_key_meets_is_refuted(self):
        rod = kind("rod", size("d"), key("grade", "A", "B", "C"), {**key("coating", "zinc", "paint", "none"), "optional": True})
        size_rule = rule("size", "rod", "rod.size", le=["d", ["q", "100", "mm"]])
        both = rule("finish", "rod", "rod.finish", requires=["or", ["and", ["is", "coating", "zinc"], ["is", "grade", "A"]], ["and", ["is", "coating", "paint"], ["is", "grade", "B"]]])
        deck = made_up([rod], [asks("rod.finish", "rod"), asks("rod.size", "rod")], [both, size_rule])
        for grade, waived, state, verdict in (("C", True, "refuted", "FAIL"), ("C", False, "refuted", "FAIL"), ("A", True, "waived", grid.PASS_WAIVED),
                                              ("A", False, "open", "UNKNOWN")):
            card = HEAD + (waive("rod.finish", "r") if waived else "")
            found, status, said = cells(self, deck, design(part("rod", "r", d="10 mm", grade=grade, coating="unstated")), card)
            self.assertEqual((found[("r", "rod.finish", "finish")], status), (state, verdict), (grade, waived))
        self.assertEqual(reason(said, "rod.finish"), "r.coating is unstated: its maker states none, and the rule reads it")
        found, status, said = cells(self, deck, design(part("rod", "r", d="10 mm", grade="C", coating="unstated")))
        self.assertEqual(reason(said, "rod.finish"), "the part is not what the rule requires: coating is unstated, grade is C")

    def test_a_load_a_case_leaves_out_that_fails_whatever_it_is_is_not_passed(self):
        # Under wind the shear alone is 120 / 56.5 = 2.12 of the bolt, and a tension of at
        # least zero only adds to it.
        found, status, said = cells(self, INTERACTION, *bolt("120 kN"))
        self.assertEqual((found[("b", "bolt.combined", "interaction/wind")], status), ("open", "UNKNOWN"))
        self.assertTrue(reason(said, "bolt.combined", "interaction/wind").startswith(grid.UNRESTED))

    def test_a_load_a_case_leaves_out_rests_under_a_value_at_which_the_rule_holds(self):
        found, status, _ = cells(self, INTERACTION, *bolt("10 kN"))
        self.assertEqual((found[("b", "bolt.combined", "interaction/wind")], status), ("waived", grid.PASS_WAIVED))

    def test_a_table_with_no_line_for_the_part_inside_a_min_is_not_passed(self):
        bearing = {"id": "made-up/bearing", "anchor": ANCHOR, "gives": {"name": "Rb", "dim": "force", "what": "bearing"},
                   "takes": [{"name": "d", "dim": "length", "what": "bolt", "range": ["12 mm", "24 mm"]}],
                   "table": {"down": {"by": "d", "at": ["12 mm", "16 mm", "20 mm", "24 mm"]}, "unit": "kN", "cells": ["40", "55", "70", "85"]}}
        joint = kind("joint", size("d"), size("fu", "stress"), loads=[{"name": "pull", "dim": "force", "what": "pull", "least": "0 kN"}])
        deck = made_up([joint], [asks("joint.strength", "joint")],
                       [rule("strength", "joint", "joint.strength", le=[["load", "pull"], ["min", ["mul", "0.6", "fu", ["div", ["mul", "pi", "d", "d"], "4"]], ["row", "made-up/bearing", {"d": "d"}]]])],
                       [bearing])
        card = HEAD + given("j.fu", "800 MPa") + load("service", "j pull in [400 kN, 400 kN]") + waive("joint.strength", "j")
        found, status, said = cells(self, deck, design(part("joint", "j", d="22 mm", fu="given j.fu")), card)
        self.assertEqual((found[("j", "joint.strength", "strength/service")], status), ("open", "UNKNOWN"))
        self.assertTrue(reason(said, "joint.strength").startswith(grid.UNRESTED))

    def test_an_unless_on_an_unstated_key_rests_under_a_name_at_which_it_holds(self):
        deck = made_up([kind("pin", size("d"), COATING)], [asks("pin.rust", "pin", unless={"when": ["is", "coating", "zinc"], "why": "zinc does not rust"}),
                                                           asks("pin.size", "pin")],
                       [rule("size", "pin", "pin.size", le=[["q", "6", "mm"], "d"])])
        text = design(part("pin", "p", d="10 mm", coating="unstated"))
        for card, state, verdict in ((HEAD + waive("pin.rust", "p"), "waived", grid.PASS_WAIVED), (HEAD, "open", "UNKNOWN")):
            found, status, _ = cells(self, deck, text, card)
            self.assertEqual((found[("p", "pin.rust", "")], status), (state, verdict))

    @KERNEL
    def test_the_kernel_rests_nothing_on_a_completion_that_does_not_fit(self):
        """A hand-made hint: a name the key does not have, a load under its least, a key the
        rule does not read, and the right completion with a partition that proves nothing."""
        rules, read = parsed(BY_TABLE, *pin("9.5 kN"))
        report, files = grid.check(read, rules)
        (good,) = [h for h in json.loads(files["proofs"])["cells"] if h["mechanism"] == "pin.shear"]
        self.assertEqual(good["completion"], {"keys": [["p", "coating", "zinc"]], "loads": []})
        for completion, partition in (({"keys": [["p", "coating", "paint"]]}, "leaf"), ({"keys": [["p", "coating", "zinc"]], "loads": [["p", "shear", "service", "-1"]]}, "leaf"),
                                      ({"keys": [["p", "coating", "zinc"], ["p", "grade", "x"]]}, "leaf"), ({"keys": [["p", "coating", "none"]]}, "leaf")):
            with self.subTest(completion=completion):
                hint = {**good, "completion": completion, "partition": partition}
                said = ask({**files, "proofs": json.dumps({"format": "petra-proofs/0", "cells": [hint]})})
                (cell,) = [c for c in said["cells"] if c["mechanism"] == "pin.shear"]
                self.assertEqual((said["findings"], cell["state"], said["verdict"]), ([], "open", "UNKNOWN"))
        self.assertEqual(report.status, grid.PASS_WAIVED)

    @KERNEL
    def test_the_kernel_refutes_only_with_a_point_for_every_name(self):
        rules, read = parsed(BY_TABLE, *pin("20 kN"))
        report, files = grid.check(read, rules)
        hints = [h for h in json.loads(files["proofs"])["cells"] if h["mechanism"] == "pin.shear"]
        self.assertEqual(sorted(h["completion"]["keys"][0][2] for h in hints), ["none", "zinc"])
        for kept in hints:
            said = ask({**files, "proofs": json.dumps({"format": "petra-proofs/0", "cells": [kept]})})
            (cell,) = [c for c in said["cells"] if c["mechanism"] == "pin.shear"]
            self.assertEqual((cell["state"], said["verdict"]), ("open", "UNKNOWN"))

    def test_a_disagreement_of_the_waivers_is_one_the_kernel_and_the_grid_are_held_to(self):
        rules, read = parsed(BY_WHEN, *pin("9.5 kN"))
        report, files = grid.check(read, rules)
        said = {"cells": [{"subject": c.subject, "mechanism": c.mechanism, "entry": c.entry, "state": c.state} for c in report.cells],
                "verdict": report.verdict, "hashes": {"rules": rules.hash}, "cells_from": "rules", "waived": []}
        self.assertIn("waivers", verify.differs([(c.subject, c.mechanism, c.entry, c.state) for c in report.cells], report.verdict, rules.hash, said, report.waived()))
        self.assertEqual(verify.differs([(c.subject, c.mechanism, c.entry, c.state) for c in report.cells], report.verdict, rules.hash,
                                        {**said, "waived": report.waived()}, report.waived()), "")


# --- F2. a branch that cannot be written ---------------------------------------------------------------

CLASSES = [
    {"id": "made-up/class", "anchor": ANCHOR, "gives": {"name": "class", "one_of": ["B", "C"], "what": "the class of a weld by its throat"},
     "takes": [{"name": "a", "dim": "length", "what": "throat", "range": ["1 mm", "100 mm"]}],
     "table": {"down": {"by": "a", "bands": [["0 mm", "10 mm"], ["10 mm", "100 mm"]], "closed": "upper"}, "cells": ["B", "C"]}},
    {"id": "made-up/grade-factor", "anchor": ANCHOR, "gives": {"name": "k", "dim": "dimensionless", "what": "a factor of a grade in class C"},
     "takes": [{"name": "grade", "one_of": ["S235", "S355", "S460"], "what": "steel grade"}],
     "table": {"down": {"by": "grade"}, "unit": "1", "cells": ["0.8", "0.9", None]}},
]
WELD = kind("weld", size("a"), size("length"), size("fu", "stress"), key("grade", "S235", "S355", "S460"),
            loads=[{"name": "pull", "dim": "force", "what": "the pull on the weld"}])
BRANCHES = made_up([WELD], [asks("weld.strength", "weld")],
                   [rule("strength", "weld", "weld.strength",
                         le=[["load", "pull"],
                             ["mul", "0.6", "fu", "a", "length",
                              ["case", ["row", "made-up/class", {"a": "a"}], {"B": "1", "C": ["row", "made-up/grade-factor", {"grade": "grade"}]}]]])],
                   CLASSES)


def welded(a: str, grade: str, pull: str = "400 kN", waived: bool = True) -> tuple[str, str]:
    card = HEAD + given("w.fu", "510 MPa") + load("service", f"w pull in [0 kN, {pull}]") + (waive("weld.strength", "w") if waived else "")
    return design(part("weld", "w", a=a, length="100 mm", fu="given w.fu", grade=grade)), card


class BranchesThatCannotBeWritten(unittest.TestCase):
    def test_a_weld_of_the_class_whose_branch_is_written_is_refuted_under_a_waiver(self):
        # A throat of 5 mm is class B, whose factor is 1: the weld carries 0.6 x 510 MPa x 5 mm
        # x 100 mm = 153 kN and the pull reaches 400 kN. Class C has no factor for S460.
        for waived in (True, False):
            found, status, _ = cells(self, BRANCHES, *welded("5 mm", "S460", waived=waived))
            self.assertEqual((found[("w", "weld.strength", "strength/service")], status), ("refuted", "FAIL"))

    def test_a_weld_of_the_class_whose_branch_is_written_is_proved(self):
        found, status, _ = cells(self, BRANCHES, *welded("5 mm", "S460", pull="100 kN", waived=False))
        self.assertEqual((found[("w", "weld.strength", "strength/service")], status), ("proved", "PASS"))

    def test_a_weld_of_the_class_with_no_factor_for_its_grade_is_not_decided(self):
        found, status, _ = cells(self, BRANCHES, *welded("20 mm", "S460", pull="100 kN", waived=False))
        self.assertEqual((found[("w", "weld.strength", "strength/service")], status), ("open", "UNKNOWN"))

    def test_a_throat_on_both_sides_of_the_class_line_is_refuted_where_class_b_fails(self):
        # From 5 mm to 20 mm the class is B to 10 mm and C past it. B fails at 5 mm.
        text, card = welded("given w.a", "S460")
        found, status, _ = cells(self, BRANCHES, text, card + given("w.a", "5 mm", "20 mm"))
        self.assertEqual((found[("w", "weld.strength", "strength/service")], status), ("refuted", "FAIL"))


# --- F3. a pick of more than 1,024 orders --------------------------------------------------------------

def catalogue(sizes: int) -> dict:
    """A rod and a catalogue of `sizes` listed sizes from 10 mm, 2 kN for each millimetre."""
    row = {"id": "made-up/catalogue", "anchor": ANCHOR, "gives": {"name": "cap", "dim": "force", "what": "catalogue capacity"},
           "takes": [{"name": "d", "dim": "length", "what": "size", "range": ["10 mm", f"{10 + sizes - 1} mm"]}],
           "table": {"down": {"by": "d", "at": [f"{10 + k} mm" for k in range(sizes)]}, "unit": "kN", "cells": [f"{(10 + k) * 2}" for k in range(sizes)]}}
    rod = kind("rod", size("d"), loads=[{"name": "pull", "dim": "force", "what": "pull", "least": "0 kN"}])
    return made_up([rod], [asks("rod.strength", "rod")], [rule("strength", "rod", "rod.strength", le=[["load", "pull"], ["row", "made-up/catalogue", {"d": "d"}]])], [row])


class OrdersOfAPick(unittest.TestCase):
    def test_a_table_of_600_listed_sizes_is_refused_by_both_readers(self):
        mine, kernel = no_deck(self, catalogue(600))
        self.assertIn("would compare 1200 orders, over the budget of 1024 for one pick", mine)
        self.assertIn("would compare 1200 orders, over the budget of 1024 for one pick", kernel)

    def test_a_table_of_512_listed_sizes_is_read_and_its_cell_decided_alike(self):
        reads(self, catalogue(512))
        text = design(part("rod", "r", d="20 mm"))
        for pull, verdict in (("100 kN", "FAIL"), ("10 kN", "PASS")):
            found, status, _ = cells(self, catalogue(512), text, HEAD + load("service", f"r pull in [{pull}, {pull}]"))
            self.assertEqual(status, verdict, found)

    def test_a_case_on_a_row_that_names_by_more_than_1024_orders_is_refused(self):
        bands = [[f"{k} m", f"{k + 1} m"] for k in range(513)]
        naming = {"id": "made-up/class", "anchor": ANCHOR, "gives": {"name": "c", "one_of": ["a", "b"], "what": "class"},
                  "takes": [{"name": "x", "dim": "length", "what": "x", "range": ["0 m", "513 m"]}],
                  "table": {"down": {"by": "x", "bands": bands}, "cells": ["a", "b"] * 256 + ["a"]}}
        deck = made_up([kind("t", size("w"))], [asks("t.m", "t")],
                       [rule("m", "t", "t.m", le=["w", ["case", ["row", "made-up/class", {"x": "w"}], {"a": ["q", "1", "m"], "b": ["q", "2", "m"]}]])], [naming])
        mine, kernel = no_deck(self, deck)
        self.assertIn("would compare 1026 orders", mine)
        self.assertIn("would compare 1026 orders", kernel)

    def test_the_grid_writes_no_pick_of_more_than_1024_orders(self):
        tape = grid._Tape()
        x, c = tape.input(grid.Value("dsg:x", grid.Interval(Fraction(0), Fraction(1)))), tape.const(Fraction(1))
        tape.pick([(["and", [["le", x, c]] * 1024], c), (None, c)], "a row")
        with self.assertRaises(grid.NoValue) as refused:
            tape.pick([(["and", [["le", x, c]] * 1025], c), (None, c)], "a row")
        self.assertIn("would compare 1025 orders, over the budget of 1024", str(refused.exception))


# --- F4. a proved range is not a proved rule -------------------------------------------------------------

BEARING = [{"id": "made-up/bearing", "anchor": ANCHOR, "gives": {"name": "Rb", "dim": "force", "what": "bearing"},
            "takes": [{"name": "d", "dim": "length", "what": "bolt", "range": ["12 mm", "24 mm"]}],
            "table": {"down": {"by": "d", "at": ["12 mm", "16 mm", "20 mm", "24 mm"]}, "unit": "kN", "cells": ["40", "55", "70", "85"]}}]
JOINT = kind("joint", size("d"), loads=[{"name": "pull", "dim": "force", "what": "pull", "least": "0 kN"}])


def where_deck(*more: dict) -> dict:
    return made_up([JOINT], [asks("joint.bearing", "joint")],
                   [rule("bearing", "joint", "joint.bearing", where=[{"le": ["d", ["q", "30", "mm"]], "why": "the table stops at 30 mm"}],
                         le=[["load", "pull"], ["row", "made-up/bearing", {"d": "d"}]]), *more], BEARING)


class WhereIsNotTheRule(unittest.TestCase):
    def test_a_design_whose_only_proved_cell_is_a_range_is_not_passed(self):
        # At 22 mm the table has no line, so the rule has no value for the joint and its cell is
        # open. Its range, d <= 30 mm, is proved. That is the design's only proved cell.
        card = HEAD + load("service", "j pull in [500 kN, 500 kN]") + waive("joint.bearing", "j")
        found, status, _ = cells(self, where_deck(), design(part("joint", "j", d="22 mm")), card)
        self.assertEqual(found[("j", "joint.bearing", "bearing/service/where")], "proved")
        self.assertNotIn(status, ("PASS", "PASS_WAIVED"))

    def test_a_range_that_holds_nowhere_is_rested_with_one_reason_in_both_readers(self):
        card = HEAD + load("service", "j pull in [500 kN, 500 kN]") + waive("joint.bearing", "j")
        deck, read = parsed(where_deck(), design(part("joint", "j", d="40 mm")), card)
        report, _ = grid.check(read, deck)
        found, status, said = cells(self, where_deck(), design(part("joint", "j", d="40 mm")), card)
        self.assertEqual((found[("j", "joint.bearing", "bearing/service")], status), ("waived", "UNKNOWN"))
        its = reason(said, "joint.bearing")
        self.assertEqual(its, grid.WAIVED + "the rule holds only where the table stops at 30 mm, and that holds nowhere in the ranges for j")
        self.assertTrue(report.cells[0].why.endswith("; " + its), report.cells[0].why)

    def test_a_range_beside_a_proved_rule_is_still_passed(self):
        card = HEAD + load("service", "j pull in [50 kN, 50 kN]")
        found, status, _ = cells(self, where_deck(), design(part("joint", "j", d="20 mm")), card)
        self.assertEqual((found[("j", "joint.bearing", "bearing/service/where")], found[("j", "joint.bearing", "bearing/service")]), ("proved", "proved"))
        self.assertEqual(status, "PASS")


# --- F1. a bolt past the sizes Table J3.3 prints -------------------------------------------------------

LAP = "petra 0\n" + "".join(f"\nplate {p} {{\n  thickness 1 inch\n  width 12 inch\n  Fy given {p}.Fy\n  Fu given {p}.Fu\n}}\n" for p in ("tab", "strap")) + """
lap splice {
  fastener "Group 120"
  threads included
  diameter 1.125 inch
  holes standard
  count 2
  pitch 4 inch
  end 2 inch
  side 3 inch
  surface protected
  joins tab strap
}
"""
"""Two 1 inch A36 plates joined by two 1 1/8 inch Group 120 bolts, the design of the review."""
LAP_CARD = ('petra 0\n\ncard "lap" {\n  owner "t@example.org"\n}\n\n'
            + "".join(f'given {p}.{f} in [{v} ksi, {v} ksi] signed "t@example.org" source "ASTM A36"\n' for p in ("tab", "strap") for f, v in (("Fy", 36), ("Fu", 58)))
            + '\nload gravity {\n  on splice pull in [0 kip, 200 kip]\n  signed "t@example.org" source "test"\n}\n'
            + "".join(waive(m, "splice") for m in ("lap.tightening", "lap.hole_use", "lap.max_edge_distance", "lap.ply_flexure",
                                                    "lap.spacing", "lap.strength", "lap.ply_rupture", "lap.block_shear")))
"""Its card, which waives the four lines the deck has no rule for and the four whose rules read a hole."""


class ABoltPastThePrintedSizes(unittest.TestCase):
    def test_a_lap_whose_bolts_fail_in_shear_fails_under_its_waivers(self):
        """Each bolt carries 0.75 x 54 ksi x pi / 4 x (1 1/8 inch)^2 = 40.3 kip in shear, under the bearing and the tearout of its
        holes, so the two carry 80.5 kip under a pull of 200: the joint fails whatever its holes are. The shipped deck's Table J3.3
        stopped at 1 inch, so the rule had no value, the cell was open and the waiver rested it: PASS_WAIVED. The table now lists the
        hole its last line gives, 1 1/4 inch, and with D1 a waiver rests no cell of a table with no line for the part."""
        found = petra.check(LAP_CARD, LAP, path="lap.petra", repair=False)
        self.assertEqual(found["status"], "FAIL")
        (strength,) = [c for c in found["cells"] if c["mechanism"] == "lap.strength"]
        self.assertEqual(strength["state"], "refuted")
        self.assertAlmostEqual(strength["ratio"], 200 / (2 * 0.75 * 54 * math.pi / 4 * 1.125 ** 2), places=6)
        self.assertEqual([c["mechanism"] for c in found["cells"] if c["state"] == "waived"],
                         ["lap.tightening", "lap.hole_use", "lap.max_edge_distance", "lap.ply_flexure"], "the waivers of the lines with rules rest nothing")
        larger = petra.check(LAP_CARD, LAP.replace("diameter 1.125 inch", "diameter 1.75 inch").replace("pitch 4 inch", "pitch 5 inch").replace("end 2 inch", "end 3 inch"),
                             path="lap.petra", repair=False)
        self.assertEqual(larger["status"], "UNKNOWN", "a bolt past the sizes the tables list is not decided, and no waiver passes it")


if __name__ == "__main__":
    unittest.main()
