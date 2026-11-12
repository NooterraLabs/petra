"""The eighth hostile review of petra-verify (kernel/) and petra/grid.py: designs that a rule
fails whatever is missing, which a waiver rested because something was missing. One test per
finding.

  F4  A design whose one line is waived, and whose only proved cell is the `/where` cell of
      that line's rule: the range the rule holds in. That cell counted as the one proved cell a
      PASS needs, so the design passed with nothing it was asked answered.
"""
import unittest

from tests.test_deck_features import ANCHOR, HEAD, asks, cells, design, kind, load, made_up, part, rule, size


def waive(mechanism: str, on: str) -> str:
    return f'\nwaive {mechanism} on {on} by "t@example.org" reason "test"\n'


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
