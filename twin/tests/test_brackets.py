"""Brackets: a plate welded on both faces with the load in its plane, and bolt tearout about the
instantaneous center.

A comparison over generated designs found the twin failing nine bracket cards, now in
cards/gate_1_*_bracket.petra. On the six weld brackets the twin read the weld lines by the
elastic method; Manual Table 8-4 at k = 0 reads them by the instantaneous center method. On the
three bolt brackets it took every bolt's tearout at the least clear distance in any direction;
J3.11a measures lc in the direction of each bolt's own force.
"""

import math
import unittest

from twin.data import w_shape
from twin.run import check_text
from twin.tests.test_hand_checks import CARDS, checks, component

REL = 0.01
WELD = "fillet weld lines, load normal to the faying surface"

GOVERNING = {
    "gate_1_00042_weld_bracket.petra": WELD,
    "gate_1_00185_weld_bracket.petra": WELD,
    "gate_1_00229_weld_bracket.petra": WELD,
    "gate_1_00273_weld_bracket.petra": WELD,
    "gate_1_00284_weld_bracket.petra": WELD,
    "gate_1_00427_weld_bracket.petra": WELD,
    # Bolt shear governs every bolt of these two, so the group's effective strength ties with it.
    "gate_1_07378_bolt_bracket.petra": "bolt shear",
    "gate_1_08126_bolt_bracket.petra": "bolt group effective strength",
    "gate_1_08786_bolt_bracket.petra": "bolt shear",
}

WELDS_B = """petra 0

weld_bracket welds_b {{
  basis {basis}
  plate steel.A572_50 thickness 0.75 inch
  support W14x90 flange grade steel.A992
  weld electrode.E70 size {w} inch sides 2
  weld_length {length} inch
  eccentricity 4 inch
}}

load reaction {{
  on welds_b shear in [0 kip, 100 kip]
}}
"""


class GateBracketTest(unittest.TestCase):
    def test_verdicts_and_governing_checks(self):
        for card, name in GOVERNING.items():
            with self.subTest(card=card):
                out = component(card)
                self.assertEqual(out["status"], "checked", out)
                self.assertEqual(out["governing"]["name"], name)
                self.assertLess(out["governing"]["utilisation"], 1.0)

    def test_least_distance_tearout_no_longer_governs(self):
        for card in [c for c in GOVERNING if "bolt_bracket" in c]:
            with self.subTest(card=card):
                c = checks(card)
                self.assertLess(c["bearing and tearout, plate"]["utilisation"],
                                c["bolt group effective strength"]["utilisation"])


class WeldsBTest(unittest.TestCase):
    """Manual Table 8-4 at k = 0 with al = 4 in., as Example II.A-2A applies it to welds B, a weld
    line on each angle's outstanding leg. Part A of that example reads the same 318 and 212 kips
    from Table 10-2, so Tables 10-2 and 10-3 read welds B this way (inferred). The card restates
    the line as a weld bracket with the load 4 in. off it."""

    def available(self, basis, w, length):
        text = WELDS_B.format(basis=basis, w=w, length=length)
        [out] = check_text(text)["components"]
        return {c["name"]: c for c in out["checks"]}[WELD]["available"]

    def test_companion_values(self):
        cases = [
            ("II.A-2A, Table 8-4", "0.3125", "23.5", 318, 212),
            ("II.A-3, Table 10-3", "0.25", "24", 260, 173),
            ("II.A-31, Table 10-2", "0.25", "11.5", 99.7, 66.5),
        ]
        for label, w, length, lrfd, asd in cases:
            for basis, expected in (("lrfd", lrfd), ("asd", asd)):
                with self.subTest(example=label, basis=basis):
                    got = self.available(basis, w, length)
                    self.assertLess(abs(got / expected - 1), REL, f"{label} {basis}: twin {got:.4g}")


class WeldBaseMetalTest(unittest.TestCase):
    """Table J2.5 leaves a fillet weld's base metal to J4. Manual Eq. 9-7, tmin = 6.19 D / Fu,
    matches the shear rupture of a plate with a fillet on each face to its welds, and Example
    II.A-11B applies it with the size the eccentric weld needs. Eq. 9-6, tmin = 3.09 D / Fu, does
    the same for a support with the connection on one face, as Example II.A-15 applies it. So each
    base metal check is the weld group's strength times t / tmin.

    gate-1-00042: 3/8 in. E70 fillets on both faces of a 3/4 in. A36 plate (Fu = 58) to a W12x40
    flange (Fu = 65). With 6.19 = 2 (70)(sqrt 2 / 2) / 16, the plate's tmin is
    2 (70)(0.375)(sqrt 2 / 2) / 58 = 0.64002 in. and the flange's is half that at Fu = 65.
    """

    CARD = "gate_1_00042_weld_bracket.petra"

    def test_base_metal_is_the_weld_times_t_over_tmin(self):
        c = checks(self.CARD)
        weld = c[WELD]["nominal"]
        throat = 0.375 * math.sqrt(2) / 2
        plate_tmin = 2 * 70 * throat / 58
        flange_tmin = 70 * throat / 65
        tf = float(w_shape("W12x40").tf)
        self.assertAlmostEqual(c["plate shear rupture at the weld"]["nominal"] / weld, 0.75 / plate_tmin, places=9)
        self.assertAlmostEqual(c["support flange shear rupture at the weld"]["nominal"] / weld, tf / flange_tmin,
                               places=9)

    def test_a_plate_thinner_than_tmin_governs(self):
        """At 3/8 in. the plate is 0.375 / 0.64002 = 0.586 of Eq. 9-7's tmin, so its rupture at the
        weld governs, ahead of the weld and of section A-A."""
        out = component(self.CARD, (("thickness 0.75 inch", "thickness 0.375 inch"),))
        self.assertEqual(out["governing"]["name"], "plate shear rupture at the weld")
        self.assertGreater(out["governing"]["utilisation"], 1.0)


if __name__ == "__main__":
    unittest.main()
