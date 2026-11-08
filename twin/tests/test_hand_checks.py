"""Hand calculations for the limit states a comparison against the documents found wrong or missing.

Each test restates a Companion card with one change and compares the twin with the arithmetic in its
docstring. Hole sizes are Table J3.3's, and net areas add B4.3b's 1/16 in.
"""

import itertools
import math
import unittest
from fractions import Fraction as F
from pathlib import Path

from twin.coped import double_cope_moment
from twin.data import w_shape
from twin.groups import bolt_coefficient, bolt_grid
from twin.run import check_text

CARDS = Path(__file__).parent / "cards"
REL = 1e-9


def component(card, replace=()):
    text = (CARDS / card).read_text(encoding="utf-8")
    for old, new in replace:
        if old not in text:
            raise AssertionError(f"{card}: no {old!r} to replace")
        text = text.replace(old, new)
    [out] = check_text(text)["components"]
    return out


def checks(card, replace=()):
    out = component(card, replace)
    if out["status"] != "checked":
        raise AssertionError(f"{card}: {out}")
    return {c["name"]: c for c in out["checks"]}


class HandTest(unittest.TestCase):
    def close(self, value, expected, label=""):
        self.assertLess(abs(value / expected - 1), REL, f"{label}: twin {value!r}, hand {expected!r}")


class PartialBlockShearTest(HandTest):
    def test_one_row_block_governs_a_narrow_plate(self):
        """II.A-17A with Leh = 1-1/8 in. J4.3 holds on every path, so a block through the k bolt
        rows nearest the plate's bottom edge carries their share k/4 of Ru = 49.6 kips.

        t = 1/4, Lev = 1-1/4, s = 3, dh + 1/16 = 7/8, Ant = (1-1/8 - 7/16)(1/4) = 0.171875 in.^2.
        k = 1: Agv = 0.3125, Anv = 0.3125 - (1/2)(7/8)(1/4) = 0.203125 in.^2,
               Rn = min(0.6(65)(0.203125), 0.6(50)(0.3125)) + 65(0.171875) = 7.921875 + 11.171875
                  = 19.09375 kips, demand 49.6/4 = 12.4 kips, utilisation 12.4 / (0.75 Rn) = 0.866.
        k = 4: Agv = 2.5625, Anv = 1.796875, Rn = 70.078125 + 11.171875 = 81.25 kips,
               utilisation 49.6 / (0.75 Rn) = 0.814.
        k = 2 and k = 3 give 0.831 and 0.819, so the one-row block governs.
        """
        c = checks("ii_a_17a_shear_tab.petra", (("plate_edge 1.5 inch", "plate_edge 1.125 inch"),))
        whole, partial = c["block shear, plate"], c["block shear, plate, partial path"]
        self.close(whole["nominal"], 81.25, "whole block")
        self.close(partial["nominal"], 19.09375, "one-row block")
        self.close(partial["demand"], 12.4, "one-row share")
        self.assertGreater(partial["utilisation"], whole["utilisation"])


class HangerPryingWithShearTest(HandTest):
    def test_prying_uses_the_reduced_tension_of_j3_8(self):
        """II.D-1 with a 30 kip LRFD shear added. As II.A-1B does, the available tension in the
        prying equations is phi F'nt Ab from J3.8, not phi Fnt Ab.

        Ab = pi (3/4)^2 / 4 = 0.4418 in.^2, frv = 30 / (4 Ab) = 16.98 ksi.
        F'nt = 1.3(90) - 90 / (0.75(54)) (16.98) = 79.27 ksi <= 90, Tc = 0.75 F'nt Ab = 26.27 kips.
        Tee flange: b = (3.5 - 0.3)/2 = 1.6, b' = 1.225, a' = min(1.53 + 0.375, 1.25(1.6) + 0.375)
        = 1.905 in., rho = 0.643, p = 4.5 in., delta = 1 - (13/16)/4.5 = 0.819.
        tc = sqrt(4 Tc b' / (0.9 p Fu)) = 0.6992 in., alpha' = ((tc/t)^2 - 1) / (delta (1 + rho))
        = 0.6002 with t = 0.52 in., Q = (t/tc)^2 (1 + delta alpha') = 0.8251.
        Available tension with prying = 4 Q Tc = 86.69 kips. With Fnt it would be 95.3 kips.
        """
        c = checks("ii_d_1_hanger.petra", (("on ii_d_1 tension in [0 kip, 60 kip]",
                                            "on ii_d_1 tension in [0 kip, 60 kip]\n  on ii_d_1 shear in [0 kip, 30 kip]"),))
        self.assertLess(abs(c["bolt tension with prying, tee flange"]["available"] / 86.6887 - 1), 1e-4)


class NetPlasticModulusTest(HandTest):
    def test_hole_on_the_neutral_axis(self):
        """II.A-22 with three rows: depth 2(2.5) + 2(3) = 11 in., holes at -3, 0 and 3 in., 7/8 in.
        wide. The middle hole spans the neutral axis and removes t (7/8)^2 / 4.

        Znet = (3/8)(11^2/4 - (7/8)(3 + 3) - (7/8)^2/4) = 9.303223 in.^3, Fu Znet = 604.7095 kip-in.
        """
        c = checks("ii_a_22_bolt_bracket.petra", (("rows 6", "rows 3"),))
        self.close(c["flexural rupture, section A-A"]["nominal"], 65 * 9.30322265625, "Fu Znet")


class DoubleCopeCbTest(HandTest):
    def test_eq_9_21_groups_the_log_term_with_three(self):
        """Manual Eq. 9-21 is Cb = [3 + ln(Lb/d)](1 - dct/d) >= 1.84. II.A-7 prints 1.94 for
        Lb = 9.5, d = 16 and dct = 3.5 in.: (3 + ln 0.594)(0.781) = 1.94.

        W16x40 coped 3.5 in. at the top and 2 in. at the bottom over c = 20 in., so hc = 10.5 in.
        Cb = (3 + ln(20/16))(1 - 3.5/16) = 2.518. Lb hc / tw^2 = 20(10.5)/0.305^2 = 2257 > 1.9E/Fy,
        so F11-4 and F11-5 apply: Fcr = 1.9(29,000)(2.518)/2257 = 61.46 ksi,
        Sc = 0.305(10.5)^2/6 = 5.604 in.^3, Mn = Fcr Sc = 344.5 kip-in. < Mp = 420.3 kip-in.
        """
        mn, _ = double_cope_moment(w_shape("W16x40"), F(50), F(7, 2), F(2), F(20))
        self.assertLess(abs(float(mn) / 344.4521 - 1), 1e-5)


class ContinuousWebEndBoltTest(HandTest):
    def test_top_bolt_tears_out_toward_the_beam_top(self):
        """II.A-1A with s = 2-1/4 in. and the top bolt 3 in. below the beam's top. J3.11's lc runs
        in the direction of the force to the next hole or the edge of the material, so the top bolt
        of an uncoped web has lc = 3 - (13/16)/2 = 2.594 in., not s - dh.

        tw = 0.76 in.: bearing 2.4(3/4)(0.76)(65) = 88.92 kips, interior tearout
        1.2(2.25 - 0.8125)(0.76)(65) = 85.215 kips, top tearout 1.2(2.594)(0.76)(65) = 153.76 kips.
        Beam web total = 7(85.215) + 88.92 = 685.425 kips (681.72 with the top bolt as interior).
        """
        c = checks("ii_a_1a_double_angle.petra", (("pitch 3 inch", "pitch 2.25 inch\n  top 3 inch"),))
        self.close(c["bearing and tearout, beam web, beam side"]["nominal"], 685.425, "beam web")


class BracketTearoutTest(HandTest):
    """II.A-22 cut to two bolts in one column, s = 3 in., loaded e = 3 in. from their centroid.
    J3.11a measures lc in the direction of the force, and about the instantaneous center each bolt
    pushes the plate perpendicular to its own radius.

    Both bolts sit rho from the center and reach the same force R, so vertical equilibrium gives
    2 R r0 / rho = P and moments about the center give 2 R rho = P (e + r0), with r0 the center's
    offset from the bolt line. Hence r0 = (s/2)^2 / e = 0.75 in., rho = 1.6771 in. and
    C = 2 (1 - e^-3.4)^0.55 r0 / rho. The top bolt pushes the plate along (-2, 1)/sqrt 5, toward the
    back edge Leh behind it, which the line meets sqrt(5) Leh / 2 from the bolt. The bottom bolt
    pushes along (2, 1)/sqrt 5, toward the load, and meets the top edge 5.5 sqrt 5 in. away, so
    bearing governs it. Plate t = 3/8, Fu = 65, d = 3/4. The plate's strength is (C/n) times the sum
    of the bolts' strengths, as Example II.A-17A sums an eccentric group.
    """

    R0 = 1.5**2 / 3
    C = 2 * (1 - math.exp(-3.4)) ** 0.55 * R0 / math.hypot(R0, 1.5)
    TWO_BOLTS = (("rows 6", "rows 2"), ("columns 2", "columns 1"), ("eccentricity 12 inch", "eccentricity 3 inch"))

    def plate(self, *replace):
        return checks("ii_a_22_bolt_bracket.petra", self.TWO_BOLTS + replace)["bearing and tearout, plate"]["nominal"]

    def test_each_bolt_tears_out_along_its_own_force(self):
        """Leh = 1-1/4 in., standard holes. Top bolt lc = 1.25 sqrt(5)/2 - 13/32 = 0.99129 in.,
        tearout 1.2(0.99129)(3/8)(65) = 28.995 kips. Bottom bolt bearing 2.4(3/4)(3/8)(65) = 43.875
        kips. The least clear distance in any direction, Leh - 13/32 = 0.84375 in., would give both
        bolts 24.680 kips."""
        lc = 1.25 * math.sqrt(5) / 2 - 13 / 32
        hand = self.C / 2 * (1.2 * lc * 0.375 * 65 + 2.4 * 0.75 * 0.375 * 65)
        got = self.plate(("  free_edge 15.25 inch\n", ""), ("plate_edge 2 inch", "plate_edge 1.25 inch"))
        self.close(got, hand, "standard holes")

    def test_long_slot_across_the_shear(self):
        """Leh = 1-1/2 in. and a horizontal slot 13/16 by 1-7/8 in., a 13/32 in. radius drawn out
        17/32 in. each way. The top bolt's line leaves its slot through the end arc, at
        (17/32)(2/sqrt 5) + sqrt((13/32)^2 - (17/32)^2 / 5) = 0.80470 in., so lc = 1.5 sqrt(5)/2
        - 0.80470 = 0.87235 in. A long slot lies across some bolt's force, so Eqs. J3-6e and J3-6f
        apply: tearout 1.0(0.87235)(3/8)(65) = 21.264 kips, bearing 2.0(3/4)(3/8)(65) = 36.5625."""
        h, r = 17 / 32, 13 / 32
        lc = 1.5 * math.sqrt(5) / 2 - (h * 2 / math.sqrt(5) + math.sqrt(r * r - h * h / 5))
        hand = self.C / 2 * (lc * 0.375 * 65 + 2.0 * 0.75 * 0.375 * 65)
        got = self.plate(("  free_edge 15.25 inch\n", ""), ("plate_edge 2 inch", "plate_edge 1.5 inch\n  holes plate lsl"))
        self.close(got, hand, "long slot")

    def test_a_shaped_brackets_free_edge_stops_the_bottom_bolt(self):
        """free_edge 2 in.: the free edge rises from the bottom of section A-A, 2.5 in. below the
        bottom bolt, to the top edge 8 in. higher and 2 in. on, so it climbs 4 in. per inch. The
        bottom bolt's line (2, 1)/sqrt 5 meets it after 2.5 / (7/sqrt 5) = 0.79861 in., lc = 0.39236
        in., tearout 1.2(0.39236)(3/8)(65) = 11.477 kips. The top bolt is as with Leh = 1-1/4 in."""
        top = 1.2 * (1.25 * math.sqrt(5) / 2 - 13 / 32) * 0.375 * 65
        bottom = 1.2 * (2.5 * math.sqrt(5) / 7 - 13 / 32) * 0.375 * 65
        got = self.plate(("free_edge 15.25 inch", "free_edge 2 inch"), ("plate_edge 2 inch", "plate_edge 1.25 inch"))
        self.close(got, self.C / 2 * (top + bottom), "free edge")


SIGNED = 'signed "detailer@example.org" source "fabrication tolerance"'


class IntervalLengthTest(HandTest):
    """A length may be a signed bound or a param. Each check reports its worst case over every
    end of every interval."""

    def assert_worst(self, interval_card, point_cards):
        got = checks("ii_a_30_shear_tee.petra", interval_card)
        points = [checks("ii_a_30_shear_tee.petra", r) for r in point_cards]
        self.assertEqual(set(got), set(points[0]))
        for name, check in got.items():
            worst = max(p[name]["utilisation"] for p in points)
            self.assertAlmostEqual(check["utilisation"], worst, places=12, msg=name)

    def test_signed_bounds(self):
        ends = {"edge_vertical": ("1.125", "1.375"), "bolt_line": ("3.6", "4.0")}
        given = {"edge_vertical": "1.25", "bolt_line": "3.8"}
        interval = [(f"{k} {given[k]} inch", f"{k} in [{lo} inch, {hi} inch] {SIGNED}") for k, (lo, hi) in ends.items()]
        corners = [[(f"{k} {given[k]} inch", f"{k} {v} inch") for k, v in zip(ends, pick)]
                   for pick in itertools.product(*ends.values())]
        self.assert_worst(interval, corners)

    def test_param(self):
        interval = [("petra 0", "petra 0\nparam a in [3.6 inch, 4.0 inch]"), ("bolt_line 3.8 inch", "bolt_line param a")]
        self.assert_worst(interval, [[("bolt_line 3.8 inch", f"bolt_line {v} inch")] for v in ("3.6", "4.0")])


class BracketSlipAndBlockShearTest(HandTest):
    def test_slip_critical_bracket(self):
        """II.A-22 made slip-critical, Class A, standard holes, one slip plane. J3.9 gives each
        bolt mu Du hf Tb ns = 0.30(1.13)(1.0)(28)(1) = 9.492 kips, scaled by C as the bolt shear
        check is. The eccentric bracket's block shear has no J4.3 demand in the documents read and
        must be listed, not dropped."""
        out = component("ii_a_22_bolt_bracket.petra", (("threads included", "threads included joint slip_critical"),))
        c = {x["name"]: x for x in out["checks"]}
        self.close(c["slip"]["nominal"] / bolt_coefficient(bolt_grid(6, 2, 3.0, 5.5), 12.0), 9.492, "slip")
        self.assertTrue(any("block shear" in u for u in out["unsupported"]), out["unsupported"])


if __name__ == "__main__":
    unittest.main()
