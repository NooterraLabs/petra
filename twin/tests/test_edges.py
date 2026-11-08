"""Bolt holes that run past an edge, from two steel gate designs a metamorphic test flagged.

J3.11a's lc and J4.3's net areas measure the steel between a hole and the next hole or edge, so a
hole that overruns an edge leaves zero there, never less. Below Table J3.4's edge distance, Table
J3.4 note [a] lets the J3.11 and J4 checks govern down to one bolt diameter, and J3.5 adds Table
J3.5's C2 for oversized and slotted holes. A bolt line on or past its element's edge puts no hole
in the element, so the card is refused.
"""

import unittest
from dataclasses import replace
from fractions import Fraction as F
from unittest import mock

from twin import fields
from twin.data import w_shape
from twin.groups import bolt_coefficient, bolt_grid
from twin.tests.test_hand_checks import component

TAB = "gate_1_04213_shear_tab.petra"
ANGLE = "gate_1_03786_single_angle.petra"
INSIDE_TOE = (("support_gauge 5.5 inch", "support_gauge 3.25 inch"),)
REL = 1e-9


def by_name(out):
    if out["status"] != "checked":
        raise AssertionError(out)
    return {c["name"]: c for c in out["checks"]}


def thicker_web(beam, extra=F(1, 16)):
    def shape(name):
        s = w_shape(name)
        return replace(s, tw=s.tw + extra) if name == beam else s

    return mock.patch.object(fields, "w_shape", shape)


class EdgeTest(unittest.TestCase):
    def close(self, value, expected, label=""):
        self.assertLess(abs(value / expected - 1), REL, f"{label}: twin {value!r}, hand {expected!r}")


class SlotPastTheCopeTest(EdgeTest):
    """gate-1-04213: the top bolt's vertical short slot, 1-1/8 in. long, centres 0.5 in. below the
    cope's cut."""

    C = bolt_coefficient(bolt_grid(2, 1, 3.0, 0.0), 1.75)

    def test_the_edge_distance_at_the_cope_governs(self):
        """J3.5 asks d + C2 = 7/8 + 1/8 = 1 in. of a short slot whose long axis points at the edge.
        The slot centres 0.5 in. from the cut, so the utilisation is 1 / 0.5 = 2."""
        out = component(TAB)
        self.assertEqual(out["status"], "checked")
        self.assertEqual(out["governing"],
                         {"name": "edge distance along the force, beam web, beam side", "utilisation": 2.0})

    def test_the_top_bolt_tears_out_nothing_from_the_web(self):
        """lc = 0.5 - (9/8)/2 < 0, so no web lies ahead of the top bolt and its tearout is 0. The
        bottom bolt is interior, lc = 3 - 9/8 = 1.875 in., tearout 1.2(1.875)(1/4)(65) = 36.5625
        kips against bearing 2.4(7/8)(1/4)(65) = 34.125 kips. Each bolt's least strength is 0 at
        the top and the plate's edge tearout 1.2(1.25 - 15/32)(5/16)(65) = 19.04296875 kips at the
        bottom. C is the IC coefficient of two bolts at e = a/2 = 1.75 in."""
        c = by_name(component(TAB))
        k = self.C / 2
        self.close(c["bearing and tearout, beam web, beam side"]["nominal"] / k, 34.125, "web")
        self.close(c["bolt group effective strength, beam side"]["nominal"] / k, 19.04296875, "group")

    def test_the_web_block_through_the_top_row_has_no_net_shear_area(self):
        """The shear plane from the cut to the top hole holds no steel, so Anv = 0. Agv = 0.5(1/4)
        = 0.125 in.^2, Ant = (2 - 1/4 - (15/16 + 1/16)/2)(1/4) = 0.3125 in.^2,
        Rn = min(0, 0.6(50)(0.125)) + 65(0.3125) = 20.3125 kips."""
        c = by_name(component(TAB))
        self.close(c["block shear, beam web, partial path"]["nominal"], 20.3125, "one-row block")


class DoubleCopeTest(EdgeTest):
    """gate-1-04213 coped 2 in. at the bottom too: hc = 15.7 - 2 - 2 = 11.7 in., and the bottom
    bolt sits 11.7 - 0.5 - 3 = 8.2 in. above the bottom cope."""

    BOTH = (("cope top depth 2 inch length 4 inch", "cope both depth 2 inch length 4 inch bottom_depth 2 inch"),)

    def test_the_net_section_counts_no_steel_above_the_top_hole(self):
        """With dh + 1/16 = 1-3/16 in., Anv = (0 + (3 - 1.1875) + (8.2 - 0.59375))(1/4)
        = 2.3546875 in.^2, Rn = 0.6(65)(2.3546875) = 91.8328125 kips."""
        c = by_name(component(TAB, self.BOTH))
        self.close(c["shear rupture, coped section"]["nominal"], 91.8328125, "net section")
        self.close(c["edge distance along the force, beam web, bottom cope"]["available"], 8.2, "bottom edge")

    def test_a_bolt_line_past_the_bottom_cope_is_an_input_error(self):
        """A 10.5 in. bottom cope leaves hc = 3.2 in., so the bottom bolt sits 0.3 in. inside it."""
        deeper = (("cope top depth 2 inch length 4 inch", "cope both depth 2 inch length 4 inch bottom_depth 10.5 inch"),)
        out = component(TAB, deeper)
        self.assertEqual(out["status"], "input_error")
        self.assertIn("beam web, bottom cope", out["reason"])
        self.assertIn("0.3 in. past", out["reason"])


class SatisfiedEdgeDistanceTest(EdgeTest):
    def test_a_satisfied_edge_distance_does_not_govern(self):
        """II.A-17A at a tenth of its reaction: Lev = 1.25 in. against d = 3/4 in. is 0.6, above
        every strength utilisation, but a detailing limit does not grow with the load."""
        out = component("ii_a_17a_shear_tab.petra", (("49.6 kip", "4.96 kip"),))
        edge = by_name(out)["edge distance along the force, plate, beam side"]
        self.close(edge["utilisation"], 0.6, "J3.5")
        self.assertEqual(edge["mode"], "edge_min")
        self.assertLess(out["governing"]["utilisation"], 0.6)
        self.assertNotIn("edge distance", out["governing"]["name"])


class BoltLinePastTheToeTest(EdgeTest):
    """gate-1-03786: support_gauge runs from the heel to the bolt line in the outstanding leg."""

    def test_a_bolt_line_past_the_toe_is_an_input_error(self):
        """5.5 in. on the 3.5 in. outstanding leg puts the bolt line 2 in. past the toe."""
        out = component(ANGLE)
        self.assertEqual(out["status"], "input_error")
        self.assertIn("angle, support leg", out["reason"])
        self.assertIn("2 in. past", out["reason"])

    def test_a_hole_over_the_toe_fails_j3_5(self):
        """support_gauge 3.25 in. leaves 0.25 in. to the toe, under the hole's half width 13/32 in.
        J3.5 asks d = 3/4 in. of a standard hole, so the utilisation is 0.75 / 0.25 = 3."""
        out = component(ANGLE, INSIDE_TOE)
        self.assertEqual(out["status"], "checked")
        self.assertEqual(out["governing"]["name"], "edge distance across the force, angle, support leg")
        self.close(out["governing"]["utilisation"], 3.0, "J3.5")

    def test_the_block_over_the_toe_has_no_net_tension_area(self):
        """Ant = 0 where the hole runs past the toe. Agv = (1.25 + 3)(3/8) = 1.59375 in.^2,
        Anv = (1.25 - 7/16 + 3 - 7/8)(3/8) = 1.1015625 in.^2,
        Rn = min(0.6(58)(1.1015625), 0.6(36)(1.59375)) + 0 = 34.425 kips."""
        c = by_name(component(ANGLE, INSIDE_TOE))
        self.close(c["block shear, angle, support leg"]["nominal"], 34.425, "block")


class NoNegativeStrengthTest(EdgeTest):
    def assert_none_negative(self, card, replace):
        out = component(card, replace)
        if out["status"] == "input_error":
            return out
        for check in by_name(out).values():
            self.assertGreaterEqual(check["available"], 0, f"{card} {replace}: {check['name']}")
        return out

    def test_the_cope_cut_swept_across_the_top_hole(self):
        for sixteenths in range(33, 57):
            top = sixteenths / 16
            with self.subTest(top=top):
                self.assert_none_negative(TAB, (("top 2.5 inch", f"top {top} inch"),))

    def test_the_support_bolt_line_swept_across_the_toe(self):
        for eighths in range(2, 41):
            gauge = eighths / 8
            with self.subTest(support_gauge=gauge):
                out = self.assert_none_negative(ANGLE, (("support_gauge 5.5 inch", f"support_gauge {gauge} inch"),))
                self.assertEqual(out["status"] == "input_error", gauge >= 3.5)


class MonotoneTest(EdgeTest):
    """A thicker element or one more row of bolts makes a stronger design, so no capacity may fall.
    The single angle's element is the angle: a thicker beam web moves its support bolt line off the
    web's centre, e = gauge + tw/2, and rightly lowers the IC coefficient there."""

    def assert_not_lower(self, before, after, label):
        b, a = by_name(before), by_name(after)
        for name in b.keys() & a.keys():
            self.assertGreaterEqual(a[name]["available"], b[name]["available"] * (1 - REL), f"{label}: {name}")

    def test_a_thicker_beam_web(self):
        before = component(TAB)
        with thicker_web("W16x26"):
            after = component(TAB)
        self.assert_not_lower(before, after, "web + 1/16 in.")

    def test_a_thicker_angle(self):
        thicker = INSIDE_TOE + (("L4x3_1_2x3_8", "L4x3_1_2x1_2"),)
        self.assert_not_lower(component(ANGLE, INSIDE_TOE), component(ANGLE, thicker), "angle 1/2 in.")

    def test_one_more_row(self):
        for card, change in ((TAB, ()), (ANGLE, INSIDE_TOE)):
            with self.subTest(card=card):
                after = component(card, change + (("rows 2", "rows 3"),))
                self.assert_not_lower(component(card, change), after, f"{card} rows 3")

    def test_the_refused_design_stays_refused(self):
        with thicker_web("W12x26"):
            self.assertEqual(component(ANGLE)["status"], "input_error")
        self.assertEqual(component(ANGLE, (("rows 2", "rows 3"),))["status"], "input_error")


if __name__ == "__main__":
    unittest.main()
