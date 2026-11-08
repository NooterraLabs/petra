"""Companion design examples (AISC Design Examples, v16.0) reproduced through the twin.

Each card in cards/ restates one example's given data. The test runs it under LRFD and under ASD
and compares each available strength with the value the example prints.

Tolerance: 1 percent. The Companion prints three significant figures and carries rounded
intermediate values (table lookups, Zc and Sc, per-bolt strengths), so a closed-form value can
differ from the printed one in the third figure. Measured on the frozen twin, the largest deviation
among the 88 card comparisons is 0.92 percent, the ASD interaction sum of Example II.A-22, where the
example carries Fcr, b' and Nr rounded to three figures.
"""

import unittest
from fractions import Fraction as F
from pathlib import Path

from twin import checks as ck
from twin.coped import double_cope_moment, tee_moduli, top_cope_moment
from twin.data import w_shape
from twin.kinds import prying, prying_geometry, tributary
from twin.run import check_text

CARDS = Path(__file__).parent / "cards"
REL = 0.01
LRFD_PHI_B, ASD_OMEGA_B = F(9, 10), F(167, 100)

# card, LRFD demand, ASD demand
DEMANDS = {
    "ii_a_17a_shear_tab.petra": ("49.6", "33.0"),
    "ii_a_1a_double_angle.petra": ("226", "151"),
    "ii_a_4_coped_double_angle.petra": ("60", "40"),
    "ii_a_11a_end_plate.petra": ("60", "40"),
    "ii_a_28a_single_angle.petra": ("39.8", "26.5"),
    "ii_a_30_shear_tee.petra": ("36", "24"),
    "ii_a_22_bolt_bracket.petra": ("36", "24"),
    "ii_a_23_weld_bracket.petra": ("27", "18"),
    "ii_d_1_hanger.petra": ("60", "40"),
    "ii_a_12a_seated.petra": ("54.8", "36.5"),
}

# card, check name, printed LRFD available, printed ASD available (None where not printed)
AVAILABLE = [
    ("ii_a_17a_shear_tab.petra", "bolt group effective strength, beam side", 58.5, 38.9),
    ("ii_a_17a_shear_tab.petra", "shear yielding, plate", 86.4, 57.6),
    ("ii_a_17a_shear_tab.petra", "shear rupture, plate", 58.5, 39.0),
    ("ii_a_17a_shear_tab.petra", "block shear, plate", 65.3, 43.6),
    ("ii_a_1a_double_angle.petra", "bolt group effective strength, beam side", 282, 187),
    ("ii_a_1a_double_angle.petra", "bolt group effective strength, support side", 282, 187),
    ("ii_a_1a_double_angle.petra", "shear yielding, angles", 441, 294),
    ("ii_a_1a_double_angle.petra", "shear rupture, angles", 302, 201),
    ("ii_a_1a_double_angle.petra", "block shear, angles, beam leg", 315, 210),
    ("ii_a_4_coped_double_angle.petra", "bolt group effective strength, beam side", 73.5, 49.0),
    ("ii_a_4_coped_double_angle.petra", "bolt group effective strength, support side", 96.4, 64.1),
    ("ii_a_4_coped_double_angle.petra", "coped section flexure", 374, 249),
    ("ii_a_4_coped_double_angle.petra", "shear yielding, coped section", 170, 113),
    ("ii_a_4_coped_double_angle.petra", "block shear, beam web", 68.6, 45.8),
    ("ii_a_11a_end_plate.petra", "bolt group effective strength, support side", 96.4, 64.1),
    ("ii_a_11a_end_plate.petra", "shear yielding, plate", 128, 85.3),
    ("ii_a_11a_end_plate.petra", "shear rupture, plate", 86.3, 57.5),
    ("ii_a_11a_end_plate.petra", "block shear, plate", 93.8, 62.5),
    ("ii_a_11a_end_plate.petra", "fillet weld, plate to beam web", 67.9, 45.3),
    ("ii_a_28a_single_angle.petra", "shear yielding, angle", 129, 86.0),
    ("ii_a_28a_single_angle.petra", "shear rupture, angle", 87.8, 58.5),
    ("ii_a_28a_single_angle.petra", "block shear, angle, support leg", 93.6, 62.4),
    ("ii_a_28a_single_angle.petra", "flexural yielding, angle, support leg", 558, 371),
    ("ii_a_28a_single_angle.petra", "flexural rupture, angle, support leg", 413, 275),
    ("ii_a_28a_single_angle.petra", "shear yielding, coped section", 141, 94.0),
    ("ii_a_28a_single_angle.petra", "block shear, beam web", 80.9, 53.9),
    ("ii_a_30_shear_tee.petra", "bolt group effective strength, stem", 43.5, 28.9),
    ("ii_a_30_shear_tee.petra", "flexural yielding, tee stem", 521, 346),
    ("ii_a_30_shear_tee.petra", "flexural rupture, tee stem", 386, 257),
    ("ii_a_30_shear_tee.petra", "shear yielding, tee stem", 121, 80.7),
    ("ii_a_30_shear_tee.petra", "shear rupture, tee stem", 81.8, 54.5),
    ("ii_a_30_shear_tee.petra", "block shear, tee stem", 87.4, 58.2),
    ("ii_a_30_shear_tee.petra", "bolt group effective strength, flange", 143, 95.2),
    ("ii_a_22_bolt_bracket.petra", "bolt shear", 81.1, None),
    ("ii_a_22_bolt_bracket.petra", "flexural yielding, section A-A", 1690, 1130),
    ("ii_a_22_bolt_bracket.petra", "shear yielding, plate, section A-A", 225, 150),
    ("ii_a_22_bolt_bracket.petra", "shear rupture, plate, section A-A", 162, 108),
    ("ii_a_22_bolt_bracket.petra", "shear yielding, section B-B", 136, 90.7),
    ("ii_a_23_weld_bracket.petra", "flexural yielding, section A-A", 1370, 910),
    ("ii_a_23_weld_bracket.petra", "shear yielding, section A-A", 202.5, 135),
    ("ii_a_23_weld_bracket.petra", "shear yielding, section B-B", 109, None),
    ("ii_d_1_hanger.petra", "shear yielding, tee flange", 281, 187),
    ("ii_d_1_hanger.petra", "shear rupture, tee flange", 221, 147),
]

# card, check name, printed LRFD and ASD utilisation (the bracket interaction sums)
UTILISATION = [
    ("ii_a_22_bolt_bracket.petra", "normal and flexural interaction, section B-B", 0.864, 0.862),
    ("ii_a_23_weld_bracket.petra", "normal and flexural interaction, section B-B", 0.630, 0.631),
]


def run(card, basis, replace=()):
    text = (CARDS / card).read_text(encoding="utf-8")
    lrfd, asd = DEMANDS[card]
    if basis == "asd":
        text = text.replace("basis lrfd", "basis asd").replace(f"{lrfd} kip]", f"{asd} kip]")
    for old, new in replace:
        text = text.replace(old, new)
    [component] = check_text(text)["components"]
    if component["status"] != "checked":
        raise AssertionError(f"{card}: {component}")
    return {c["name"]: c for c in component["checks"]}


class CompanionTest(unittest.TestCase):
    def close(self, value, expected, label):
        self.assertLess(abs(value / expected - 1), REL, f"{label}: twin {value:.4g}, Companion {expected}")

    def test_available_strengths(self):
        for card, name, lrfd, asd in AVAILABLE:
            for basis, expected in (("lrfd", lrfd), ("asd", asd)):
                if expected is None:
                    continue
                with self.subTest(card=card, check=name, basis=basis):
                    self.close(run(card, basis)[name]["available"], expected, f"{card} {name} {basis}")

    def test_bracket_interactions(self):
        for card, name, lrfd, asd in UTILISATION:
            for basis, expected in (("lrfd", lrfd), ("asd", asd)):
                with self.subTest(card=card, basis=basis):
                    self.close(run(card, basis)[name]["utilisation"], expected, f"{card} {basis}")

    def test_ii_a_23_weld_group_nominal(self):
        # C = 1.46 for a 3/16 in. E70 weld 18 in. long: Rn = C C1 D l = 1.46 (1.0)(3)(18) = 78.8 kips.
        self.close(run("ii_a_23_weld_bracket.petra", "lrfd")["fillet weld group"]["nominal"], 78.8, "II.A-23 weld")

    def test_ii_a_28a_coped_flexure_in_moment(self):
        # The example prints phi Mn = 1,140 kip-in. and Mn / Omega = 760 kip-in. with e = c + setback = 4.75 in.
        for basis, expected in (("lrfd", 1140), ("asd", 760)):
            check = run("ii_a_28a_single_angle.petra", basis)["coped section flexure"]
            self.close(check["available"] * 4.75, expected, f"II.A-28A coped flexure {basis}")

    def test_ii_a_28a_beam_web_bolts_at_the_examples_edge(self):
        # The example's bolt check takes the top bolt 1-1/4 in. below the cope (top 3.25 in.); its
        # block shear takes 1-1/2 in. as given. The card carries the given 1-1/2 in.
        for basis, expected in (("lrfd", 68.5), ("asd", 45.6)):
            checks = run("ii_a_28a_single_angle.petra", basis, (("top 3.5 inch", "top 3.25 inch"),))
            self.close(checks["bolt group effective strength, beam leg"]["available"], expected, f"II.A-28A bolts {basis}")

    def test_ii_d_1_bolt_tension_per_bolt(self):
        for basis, expected in (("lrfd", 29.8), ("asd", 19.9)):
            self.close(run("ii_d_1_hanger.petra", basis)["bolt tension"]["available"] / 4, expected, f"II.D-1 {basis}")

    def test_ii_a_12a_seat_angle_table_10_5(self):
        # Table 10-5 gives 113 kips (LRFD) and 74.9 kips (ASD) for an 8 in. L6x4x5/8 with lb,req = 1-1/8 in.
        # A demand whose J10.2 bearing length is exactly 1-1/8 in. puts the twin's reaction there.
        for basis, demand, expected in (("lrfd", "70.3", 113), ("asd", "46.8666667", 74.9)):
            text_demand = DEMANDS["ii_a_12a_seated.petra"][0 if basis == "lrfd" else 1]
            checks = run("ii_a_12a_seated.petra", basis, ((f"{text_demand} kip]", f"{demand} kip]"),))
            seat = checks["seat outstanding leg flexural yielding"]
            self.close(float(demand) / seat["utilisation"], expected, f"II.A-12A seat {basis}")

    def test_ii_a_12a_crippling_branch(self):
        # lb / d = 3.25 / 16.3 = 0.199, so Eq. J10-5a applies, as the example finds.
        checks = run("ii_a_12a_seated.petra", "lrfd")
        self.assertIn("J10-5a", checks["beam web local crippling"]["clause"])


class FormulaTest(unittest.TestCase):
    """Examples whose numbers sit below a card: coped sections, prying and the J10 constants."""

    def close(self, value, expected, label):
        self.assertLess(abs(float(value) / expected - 1), REL, f"{label}: twin {float(value):.4g}, Companion {expected}")

    def test_ii_a_4_coped_section_moduli(self):
        sc, zc = tee_moduli(w_shape("W18x50"), F(2))
        self.close(sc, 23.4, "Sc")
        self.close(zc, 42.5, "Zc")

    def test_ii_a_6_top_cope(self):
        mn, _ = top_cope_moment(w_shape("W21x62"), F(50), F(8), F(9))
        rn = mn / F(19, 2)
        self.close(mn, 1230, "Mn")
        self.close(rn * LRFD_PHI_B, 116, "phi Rn")
        self.close(rn / ASD_OMEGA_B, 77.2, "Rn / Omega")

    def test_ii_a_7_double_cope(self):
        mn, _ = double_cope_moment(w_shape("W16x40"), F(50), F(7, 2), F(2), F(19, 2))
        self.close(mn, 421, "Mn")
        self.close(mn / 10 * LRFD_PHI_B, 37.9, "phi Rn")
        self.close(mn / 10 / ASD_OMEGA_B, 25.2, "Rn / Omega")

    def test_ii_a_1b_prying(self):
        # ASD, B = 26.8 kips, b' = 2.82 in., a' = 1.87 in., p = 2.90 in., t = 5/8 in., d' = 15/16 in.
        tc, alpha, q = prying(F("26.8"), F("2.82"), F("1.87"), F("2.90"), F(15, 16), F(5, 8), F(65), lrfd=False)
        self.close(alpha, 3.46, "alpha'")
        self.close(q, 0.244, "Q")

    def test_ii_d_1_prying_geometry(self):
        b, b1, a1 = prying_geometry(F(3, 4), F(7, 2), F("0.3"), F("6.56"))
        self.close(b, 1.60, "b")
        self.close(b1, 1.23, "b'")
        self.close(a1, 1.91, "a'")
        self.assertEqual(tributary(2, F(5), F(2), b), [F(9, 2), F(9, 2)])

    def test_ii_d_1_tc_from_the_required_tension(self):
        # The example evaluates Eqs. 9-30a and 9-30b with the required tension per bolt.
        b, b1, a1 = prying_geometry(F(3, 4), F(7, 2), F("0.3"), F("6.56"))
        for lrfd, tr, expected in ((True, F(15), 0.529), (False, F(10), 0.530)):
            tc, _, _ = prying(tr, b1, a1, F(9, 2), F(13, 16), F("0.52"), F(65), lrfd)
            self.close(tc, expected, "tc")

    def test_ii_d_1_tmin_matches_prying_capacity(self):
        # The example finds tmin = 0.393 in. for Tr = 15.0 kips (Eq. 9-37a). The twin's prying model
        # with the full bolt strength 29.8 kips must give 15.0 kips per bolt at that thickness.
        b, b1, a1 = prying_geometry(F(3, 4), F(7, 2), F("0.3"), F("6.56"))
        bolt = ck.bolt_tension(F(90), F(3, 4)) * F(3, 4)
        _, _, q = prying(bolt, b1, a1, F(9, 2), F(13, 16), F("0.393"), F(65), True)
        self.close(bolt * q, 15.0, "B Q")

    def test_ii_a_14_web_yielding_and_crippling_constants(self):
        w = w_shape("W21x68")
        fy = F(50)
        r1 = ck.web_local_yielding(fy, w.tw, w.kdes, F(0), w.d)
        r2 = ck.web_local_yielding(fy, w.tw, w.kdes, F(1), w.d) - r1
        self.close(r1, 64.0, "R1")
        self.close(r2, 21.5, "R2")
        phi = F(3, 4)
        lb = F(6)  # lb / d = 0.28, the J10-5b branch
        rn = phi * ck.web_crippling(fy, w.tw, w.tf, lb, w.d)
        rn_plus = phi * ck.web_crippling(fy, w.tw, w.tf, lb + 1, w.d)
        r6 = rn_plus - rn
        self.close(r6, 7.95, "R6")
        self.close(rn - r6 * lb, 75.9, "R5")


if __name__ == "__main__":
    unittest.main()
