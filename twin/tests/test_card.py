"""The twin's own reader of a card and its design, and its shape table."""

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
card "d" {
  owner "someone"
}
given plate_edge in [1.4375 inch, 1.5625 inch] signed "someone" source "calc"
load gravity {
  on st1 shear in [-10 kip, 44.482216152605 kN]
  signed "someone" source "calc"
}
load wind {
  on st1 shear in [0 kip, 12 kip]
}
"""

DESIGN = """petra 0
# a comment line
shear_tab st1 {
  basis lrfd
  plate steel.A36 thickness 9.525 mm   # 3/8 in.
  rows 4
  pitch 3 inch
  plate_edge given plate_edge
}
"""

NOTHING = "petra 0\n"
"""A card that asks nothing, and a design with no component."""


class CardTest(unittest.TestCase):
    def test_components_and_units(self):
        pair = parse(CARD, DESIGN)
        [st] = pair.components
        self.assertEqual((st.kind, st.name), ("shear_tab", "st1"))
        kind, qty = st.lines["plate"][2]
        self.assertEqual(qty.dim, "length")
        self.assertEqual(qty.value, F(3, 8))
        self.assertEqual(st.lines["rows"][0][1].dim, "count")

    def test_load_envelope_takes_the_largest_magnitude(self):
        pair = parse(CARD, DESIGN)
        self.assertEqual(len(pair.loads), 2)
        self.assertEqual(envelope(pair.loads, "st1"), {"shear": F(12)})
        self.assertEqual(pair.loads[0].hi.value, F(10))

    def test_a_line_reads_the_bound_the_card_gives(self):
        [st] = parse(CARD, DESIGN).components
        [(kind, (lo, hi))] = st.lines["plate_edge"]
        self.assertEqual((kind, lo.dim, lo.value, hi.value), ("bound", "length", F(23, 16), F(25, 16)))

    def test_a_given_the_card_does_not_state_is_an_error(self):
        with self.assertRaisesRegex(CardError, "design line 8: the card gives no bound named edge"):
            parse(CARD, DESIGN.replace("given plate_edge", "given edge"))

    def test_a_given_no_component_reads_is_an_error(self):
        with self.assertRaisesRegex(CardError, "no component reads the given plate_edge"):
            parse(CARD, DESIGN.replace("plate_edge given plate_edge", "plate_edge 1.5 inch"))

    def test_a_design_states_no_bound(self):
        bound = 'plate_edge in [1.4375 inch, 1.5625 inch] signed "someone" source "calc"'
        with self.assertRaisesRegex(CardError, "design line 8: a design states no bound"):
            parse(NOTHING, DESIGN.replace("plate_edge given plate_edge", bound))

    def test_a_design_states_no_load(self):
        for line in ("load wind {\n  on st1 shear in [0 kip, 1 kip]\n}\n", "given plate_edge in [1 inch, 2 inch]\n",
                     'waive steel.bolts on st1 by "someone" reason "none"\n'):
            with self.subTest(line=line.split()[0]):
                with self.assertRaisesRegex(CardError, "belongs in the card"):
                    parse(CARD, DESIGN + line)

    def test_a_card_holds_no_component(self):
        with self.assertRaisesRegex(CardError, "card line 3: a card holds no component block"):
            parse(DESIGN.replace("plate_edge given plate_edge", "plate_edge 1.5 inch"), NOTHING)

    def test_a_param_is_declared_in_one_file(self):
        param = "param a in [3 inch, 4 inch]\n"
        self.assertEqual(set(parse(CARD + param, DESIGN).params), {"a"})
        self.assertEqual(set(parse(CARD, DESIGN + param).params), {"a"})
        with self.assertRaisesRegex(CardError, "param a is declared in the card too"):
            parse(CARD + param, DESIGN + param)

    def test_duplicate_line_is_an_error(self):
        with self.assertRaises(CardError):
            parse(NOTHING, "shear_tab a {\n  rows 2\n  rows 3\n}\n")

    def test_unclosed_block_is_an_error(self):
        with self.assertRaises(CardError):
            parse(NOTHING, "shear_tab a {\n  rows 2\n")

    def test_every_example_pair_parses_and_runs(self):
        designs = sorted(EXAMPLES.glob("*.petra"))
        self.assertTrue(designs)
        for path in designs:
            with self.subTest(design=path.name):
                report = check_text(path.with_suffix(".card").read_text(encoding="utf-8"), path.read_text(encoding="utf-8"))
                for component in report["components"]:
                    self.assertIn(component["status"], ("checked", "unsupported"))

    def test_unknown_kind_is_reported_not_guessed(self):
        report = check_text(NOTHING, "stiffened_seat s {\n  basis lrfd\n}\n")
        self.assertEqual(report["components"][0]["status"], "unsupported")

    def test_missing_line_is_an_input_error(self):
        report = check_text(NOTHING, "shear_tab s {\n  basis lrfd\n}\n")
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
