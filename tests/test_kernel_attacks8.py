"""The eighth hostile review of petra-verify (kernel/) and petra/grid.py: designs that a rule
fails whatever is missing, which a waiver rested because something was missing. One test per
finding.

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
import unittest
from fractions import Fraction

from petra import grid
from tests.test_deck_features import ANCHOR, HEAD, asks, cells, design, given, key, kind, load, made_up, no_deck, part, reads, rule, size


def waive(mechanism: str, on: str) -> str:
    return f'\nwaive {mechanism} on {on} by "t@example.org" reason "test"\n'


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

    def test_a_range_beside_a_proved_rule_is_still_passed(self):
        card = HEAD + load("service", "j pull in [50 kN, 50 kN]")
        found, status, _ = cells(self, where_deck(), design(part("joint", "j", d="20 mm")), card)
        self.assertEqual((found[("j", "joint.bearing", "bearing/service/where")], found[("j", "joint.bearing", "bearing/service")]), ("proved", "proved"))
        self.assertEqual(status, "PASS")


if __name__ == "__main__":
    unittest.main()
