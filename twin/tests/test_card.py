"""The twin's own card reader and shape table."""

import re
import unittest
from fractions import Fraction as F
from pathlib import Path

from twin.card import CardError, parse
from twin.data import angle_shape, hole, tee_shape, w_shape
from twin.run import check_text, envelope

TWIN = Path(__file__).resolve().parents[1]
EXAMPLES = TWIN.parent / "examples" / "steel"

CARD = """petra 0
# a comment line
design "d" {
  owner "someone"
}
shear_tab st1 {
  basis lrfd
  plate steel.A36 thickness 9.525 mm   # 3/8 in.
  rows 4
  pitch 3 inch
}
load gravity {
  on st1 shear in [-10 kip, 44.482216152605 kN]
  signed "someone" source "calc"
}
load wind {
  on st1 shear in [0 kip, 12 kip]
}
"""


class CardTest(unittest.TestCase):
    def test_components_and_units(self):
        card = parse(CARD)
        [st] = card.components
        self.assertEqual((st.kind, st.name), ("shear_tab", "st1"))
        kind, qty = st.lines["plate"][2]
        self.assertEqual(qty.dim, "length")
        self.assertEqual(qty.value, F(3, 8))
        self.assertEqual(st.lines["rows"][0][1].dim, "count")

    def test_load_envelope_takes_the_largest_magnitude(self):
        card = parse(CARD)
        self.assertEqual(len(card.loads), 2)
        self.assertEqual(envelope(card.loads, "st1"), {"shear": F(12)})
        self.assertEqual(card.loads[0].hi.value, F(10))

    def test_duplicate_line_is_an_error(self):
        with self.assertRaises(CardError):
            parse("shear_tab a {\n  rows 2\n  rows 3\n}\n")

    def test_unclosed_block_is_an_error(self):
        with self.assertRaises(CardError):
            parse("shear_tab a {\n  rows 2\n")

    def test_every_example_card_parses_and_runs(self):
        cards = sorted(EXAMPLES.glob("*.petra"))
        self.assertTrue(cards)
        for path in cards:
            with self.subTest(card=path.name):
                report = check_text(path.read_text(encoding="utf-8"))
                for component in report["components"]:
                    self.assertIn(component["status"], ("checked", "unsupported"))

    def test_unknown_kind_is_reported_not_guessed(self):
        report = check_text("stiffened_seat s {\n  basis lrfd\n}\n")
        self.assertEqual(report["components"][0]["status"], "unsupported")

    def test_missing_line_is_an_input_error(self):
        report = check_text("shear_tab s {\n  basis lrfd\n}\n")
        self.assertEqual(report["components"][0]["status"], "input_error")


class ShapeTest(unittest.TestCase):
    def test_w_shape_values(self):
        w = w_shape("W16x50")
        self.assertEqual((w.d, w.tw, w.bf, w.tf, w.kdes), (F("16.3"), F("0.38"), F("7.07"), F("0.63"), F("1.03")))

    def test_angle_legs_and_thickness_come_exactly_from_the_name(self):
        a = angle_shape("L5x3_1_2x5_16")
        self.assertEqual((a.long_leg, a.short_leg, a.t), (F(5), F(7, 2), F(5, 16)))

    def test_tee_values(self):
        t = tee_shape("WT6x17_5")
        self.assertEqual((t.bf, t.tf, t.tw), (F("6.56"), F("0.52"), F("0.3")))

    def test_hole_table_j3_3(self):
        self.assertEqual(hole(F(3, 4)).along, F(13, 16))
        self.assertEqual(hole(F(1)).along, F(9, 8))
        self.assertTrue(hole(F(3, 4), "lsl").long_slot_across_force)


class IndependenceTest(unittest.TestCase):
    def test_no_module_imports_petra(self):
        pattern = re.compile(r"^\s*(import|from)\s+(petra|judges)\b", re.M)
        for path in TWIN.rglob("*.py"):
            with self.subTest(module=path.name):
                self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
