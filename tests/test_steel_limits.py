"""Steel deck element limit states (M2): the AISC 360-22 Chapter J and RCSC 2025 strengths
reproduce the AISC Manual's published values, the shear tab example's checks match a hand
calculation, the J10 guards excuse exactly the checks they should, every example
connection passes, and a corrupted design fails on the check it breaks.

Published values (AISC Steel Construction Manual, 16th ed., Parts 7 and 8), each recomputed
from the registry's rows through petra.models.steel.limits, LRFD:
    3/4 in Group 120 bolt, single shear: threads included 17.9 kips, excluded 22.5 kips
    3/4 in Group 120 bolt, tension: 29.8 kips
    3/4 in Group 120 bolt, slip, Class A, standard holes, one plane: 9.49 kips
    bearing of a 3/4 in bolt per inch of thickness, Fu = 58 ksi: 78.3 kips/in
    tearout of a 3/4 in bolt in a standard hole, edge 1 1/4 in, Fu = 58 ksi: 44.0 kips/in
    E70 fillet weld, per sixteenth of an inch of leg, per inch of length: 1.392 kips/in

Hand values for examples/steel/shear_tab.petra and its card (W18x50 beam, 3/8 in A36 plate,
four 3/4 in Group 120 bolts at 3 in, a = 3 in, V = 45 kips):
    elastic method, e = a: Ip = 4 (15 x 9) / 12 = 45 in2, M = 135 kip-in,
        corner bolt fx = 135 x 4.5 / 45 = 13.5, fy = 45 / 4 = 11.25 -> 17.573 kips,
        which the plate's one-row block carries
    weakest bolt: shear 0.75 x 54 x 0.4418 = 17.892 kips (bearing and tearout are larger)
    bolt group: a conventional single plate of 4 rows takes Table 10-9's e = a/2 = 1.5 in;
        the instantaneous center (R = Rult (1 - e^(-10 Delta))^0.55, Delta_max 0.34 in,
        Manual Part 7) balances at C = 3.5564, so the group holds 3.5564 x 17.892 = 63.632 kips
    plate shear yield 1.0 x 0.6 x 36 x 12 x 0.375 = 97.2; rupture 0.75 x 0.6 x 58 x 8.5 x 0.375 = 83.194
    plate flexure 0.9 x 36 x 13.5 = 437.4 kip-in; rupture 0.75 x 58 x 9.5625 = 415.969 kip-in
    welds 2 x 12 x 4 x 1.392 = 133.643 kips
"""
import unittest
from fractions import Fraction
from pathlib import Path

from petra import mechanics as M
from petra.files import read_pair
from petra.kernel import enclose
from petra.lang import load_design, parse_design
from petra.models.base import NeedsInputBound
from petra.models.steel import calc
from petra.models.steel import limits as L
from petra.models.steel.checks import block_paths
from petra.pipeline import check_design
from petra.registry import build_registry
from petra.solvers import SolverSource
from petra.units import CUSTOMARY

REGISTRY = build_registry()
STEEL = Path(__file__).resolve().parents[1] / "examples" / "steel"
INCH, KIP, KSI = (CUSTOMARY[u][0] for u in ("inch", "kip", "ksi"))


def const(name: str):
    return L.c(REGISTRY.constants[name].value.lo)


def prop(material: str, name: str):
    return L.c(REGISTRY.materials[material].props[name].value.lo)


def value(expr, per=KIP) -> float:
    return float(enclose(expr, {}).lo / per)


def edited(text: str, edits: tuple[tuple[str, str], ...], file: str) -> str:
    for old, new in edits:
        if old not in text:
            raise AssertionError(f"{old!r} is not in {file}")
        text = text.replace(old, new)
    return text


def design(name: str, *edits: tuple[str, str], card: tuple[tuple[str, str], ...] = (), extra: str = ""):
    """The example with `edits` made to its design and `card` to its card, and `extra` added to the card."""
    card_text, text = read_pair(STEEL / f"{name}.petra")
    return parse_design(edited(card_text, card, f"{name}.card") + extra, edited(text, edits, f"{name}.petra"),
                        f"{name}.petra", REGISTRY)


def outcomes(d) -> dict[str, str]:
    """Requirement id -> outcome class name."""
    report = check_design(d, REGISTRY, (SolverSource(),))
    return {(o.obligation.requirement if hasattr(o, "obligation") else o.requirement).id: type(o).__name__
            for o in report.outcomes}


def checks(d, conn: str, mode: str, case: str = "gravity") -> dict[str, calc.Value]:
    return {v.what: v for v in calc.values(calc.connection(d, conn, REGISTRY), d, REGISTRY, mode, case)}


class PublishedValues(unittest.TestCase):
    """Manual Part 7 and Part 8 values, from the registry's rows."""

    d = const("bolt_us.3_4.d")

    def test_bolt_shear_and_tension(self):
        phi = const("rcsc2025.s5_1.phi")
        n = L.mul(phi, L.bolt_shear(prop("bolt_group.120", "Fnv_N"), self.d, L.c(1)))
        x = L.mul(phi, L.bolt_shear(prop("bolt_group.120", "Fnv_X"), self.d, L.c(1)))
        t = L.mul(phi, L.bolt_tension(prop("bolt_group.120", "Fnt"), self.d))
        self.assertAlmostEqual(value(n), 17.9, places=1)
        self.assertAlmostEqual(value(x), 22.5, places=1)
        self.assertAlmostEqual(value(t), 29.8, places=1)

    def test_slip_resistance(self):
        rn = L.slip(const("rcsc2025.s5_4.mu_a"), const("rcsc2025.s5_4.Du"), const("rcsc2025.s5_4.hf_one"),
                    const("bolt_us.3_4.Tm_g120"), L.c(1), L.c(1))
        self.assertAlmostEqual(value(L.mul(const("rcsc2025.s5_4.phi_std"), rn)), 9.49, places=2)

    def test_bearing_and_tearout_per_inch_of_thickness(self):
        phi, fu, t = const("rcsc2025.s5_3.phi"), L.c(58 * KSI), L.c(INCH)
        considered = const(L.BEARING["considered"][0])
        bearing = L.mul(phi, L.bearing(self.d, t, fu, considered))
        lc = L.sub(L.c(Fraction(5, 4) * INCH), L.div(const("bolt_us.3_4.std"), L.c(2)))
        tearout = L.mul(phi, L.tearout(lc, t, fu, const(L.BEARING["considered"][1])))
        self.assertAlmostEqual(value(bearing), 78.3, places=1)
        self.assertAlmostEqual(value(tearout), 44.0, places=1)

    def test_fillet_weld_per_sixteenth(self):
        w = L.mul(const("aisc360.j2_4.phi"), L.fillet_per_length(const, prop("electrode.E70", "FEXX"), L.c(INCH / 16)))
        self.assertAlmostEqual(value(w, KIP / INCH), 1.392, places=3)


class ElasticMethod(unittest.TestCase):
    """The block resultant agrees with the corner bolt and with the whole group."""

    def test_a_whole_group_carries_the_force_and_a_corner_block_the_corner_bolt(self):
        v, e, s, g = L.c(40), L.c(8), L.c(3), L.c(3)
        fx, fy = M.elastic_block_force(v, e, L.c(8), 4, 2, s, g, 4, 2)
        self.assertEqual((value(fx, 1), value(fy, 1)), (0.0, 40.0))
        corner = M.elastic_bolt_force(v, e, L.c(4), 4, 1, s, L.c(0))
        block = M.elastic_block_force(v, e, L.c(4), 4, 1, s, L.c(0), 1, 1)
        self.assertEqual([value(x, 1) for x in corner], [value(x, 1) for x in block])

    def test_three_rows_of_a_two_column_bracket(self):
        # Ip = 8 (15 x 9 + 3 x 9) / 12 = 108; |sum y| = 2 x 3 x 1 x 3 / 2 = 9; |sum x| = 0
        fx, fy = M.elastic_block_force(L.c(40), L.c(8), L.c(8), 4, 2, L.c(3), L.c(3), 3, 2)
        self.assertAlmostEqual(value(fx, 1), 320 * 9 / 108, places=9)
        self.assertAlmostEqual(value(fy, 1), 30.0, places=9)

    def test_block_paths_cover_every_row_and_column_count(self):
        self.assertEqual(block_paths(2, 2), [(1, 1), (1, 2), (2, 1), (2, 2)])
        self.assertEqual(len(block_paths(4, 3)), 12)


class ShearTabHandValues(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load_design(STEEL / "shear_tab.petra", REGISTRY)

    def test_the_group_holds_c_times_its_weakest_bolt(self):
        (bolts,) = checks(self.d, "st1", "bolts").values()
        self.assertAlmostEqual(bolts.demand, 45.0, places=6)
        self.assertAlmostEqual(bolts.parts[0].capacity, 17.892, places=3)
        self.assertAlmostEqual(bolts.capacity, 3.5564 * 17.892, places=2)

    def test_plate_strengths(self):
        found = {**checks(self.d, "st1", "shear_yield"), **checks(self.d, "st1", "shear_rupture"),
                 **checks(self.d, "st1", "flexural_yield"), **checks(self.d, "st1", "flexural_rupture"),
                 **checks(self.d, "st1", "weld")}
        expected = {
            "plate: shear yielding of the gross section (J4.2a)": 97.2,
            "beam web: shear yielding of the gross section (J4.2a)": 191.7,
            "plate: shear rupture of the net section (J4.2b)": 83.194,
            "plate: flexural yielding of the gross section (J4.5)": 437.4,
            "plate: flexural rupture of the net section through the bolt holes (J4.5)": 415.969,
            "plate to support: fillet welds in longitudinal shear (J2.4)": 133.643,
        }
        for what, available in expected.items():
            self.assertAlmostEqual(found[what].capacity, available, places=2, msg=what)

    def test_the_full_block_carries_the_reaction_and_smaller_blocks_their_resultant(self):
        found = checks(self.d, "st1", "block_shear")
        self.assertAlmostEqual(found["plate: block of 4 row(s) and 1 column(s) (J4.3)"].demand, 45.0, places=6)
        self.assertAlmostEqual(found["plate: block of 1 row(s) and 1 column(s) (J4.3)"].demand, 17.573, places=3)
        self.assertAlmostEqual(found["plate: block of 4 row(s) and 1 column(s) (J4.3)"].capacity, 81.12, places=2)

    def test_asd_divides_by_omega(self):
        d = design("shear_tab", ("basis lrfd", "basis asd"), card=(("[0 kip, 45 kip]", "[0 kip, 30 kip]"),))
        (bolts,) = checks(d, "st1", "bolts").values()
        self.assertAlmostEqual(bolts.parts[0].capacity, 17.892 / 0.75 / 2.00, places=3)
        self.assertAlmostEqual(bolts.capacity, 3.5564 * 17.892 / 0.75 / 2.00, places=2)
        self.assertAlmostEqual(bolts.demand, 30.0, places=6)


class SeatBearingLength(unittest.TestCase):
    def test_the_seat_arm_uses_the_bearing_length_the_reaction_needs(self):
        # W16x26: J10-3 needs 30 / (50 x 0.25) - 2.5 x 0.747 = 0.53 in; J10-5a needs
        # (30 / 0.75 / 35.36 - 1) / (0.25 / 0.345)^1.5 x 15.7 / 3 = 1.11 in, which governs.
        # Arm = 0.5 + 0.25 (underrun) + 1.113 / 2 - (0.75 + 0.375) = 0.181 in; M = 30 x 0.181 = 5.43 kip-in.
        d = load_design(STEEL / "seated.petra", REGISTRY)
        (flexure,) = checks(d, "seat1", "seat_flexure").values()
        self.assertAlmostEqual(flexure.demand, 5.43, places=1)
        self.assertAlmostEqual(flexure.capacity, 0.9 * 36 * 8 * 0.75 ** 2 / 4, places=6)


class PryingClosedForm(unittest.TestCase):
    """limits.prying_available writes B Q as the least of its three branches, B once in each,
    so an interval B (reduced for shear by Eq J3-3) encloses exactly; here it is held to the
    Manual's form, Q = (t/tc)^2 (1 + delta alpha') with alpha' clipped to [0, 1] and Q <= 1."""

    @staticmethod
    def manual(bt, d, dh, p, b, a, t, fu, phi):
        b1, a1 = b - d / 2, min(a, 1.25 * b) + d / 2
        rho, delta = b1 / a1, 1 - dh / p
        tc2 = 4 * bt * b1 / (phi * p * fu)
        alpha = (tc2 / t ** 2 - 1) / (delta * (1 + rho))
        return bt * min(1.0, t ** 2 / tc2 * (1 + delta * min(1.0, max(0.0, alpha))))

    def test_it_is_the_manuals_form(self):
        import random
        rng = random.Random(7)
        for _ in range(400):
            args = (rng.uniform(5, 60), rng.choice((0.75, 0.875, 1.0)), rng.choice((0.8125, 0.9375, 1.0625)),
                    rng.uniform(2.5, 6), rng.uniform(1.0, 3.5), rng.uniform(1.0, 4.0), rng.uniform(0.3, 1.5), 65.0,
                    rng.choice((0.9, 1 / 1.67)))
            mine = L.prying_available(const, *(L.c(Fraction(x).limit_denominator(10**6)) for x in args))
            with self.subTest(args=args):
                self.assertAlmostEqual(float(enclose(mine, {}).lo), self.manual(*args), delta=1e-6 * self.manual(*args))

    def test_an_interval_b_encloses_exactly(self):
        from petra.kernel import Interval
        from petra.kernel.terms import Sym
        b = Sym("b_tension")
        fixed = [L.c(x) for x in (Fraction(3, 4), Fraction(13, 16), Fraction(3), Fraction(7, 4), Fraction(2),
                                  Fraction(1, 2), Fraction(65), Fraction(9, 10))]
        expr = L.prying_available(const, b, *fixed)
        for lo, hi in ((Fraction(10), Fraction(20)), (Fraction(20), Fraction(60)), (Fraction(5), Fraction(80))):
            at_lo = L.prying_available(const, L.c(lo), *fixed)
            self.assertEqual(enclose(expr, {b.name: Interval(lo, hi)}).lo, enclose(at_lo, {}).lo)


class J10Guards(unittest.TestCase):
    def at_distance(self, inches: str) -> dict[str, bool]:
        d = design("flange_force", ("location interior", f"location end\n  distance {inches} inch\n  end_twist restrained"))
        found = {**checks(d, "ff1", "web_local_yielding"), **checks(d, "ff1", "web_crippling")}
        return {what: v.excused for what, v in found.items()}

    def test_end_checks_apply_only_within_their_distance(self):
        # W14x90: d = 14.0 in. J10-3 applies within d of the end, J10-5 within d/2.
        near_yield, near_cripple = "member web: web local yielding within d of the member end (J10.2)", \
            "member web: web local crippling within d/2 of the member end (J10.3)"
        self.assertEqual((self.at_distance("5")[near_yield], self.at_distance("5")[near_cripple]), (False, False))
        self.assertEqual((self.at_distance("10")[near_yield], self.at_distance("10")[near_cripple]), (False, True))
        self.assertEqual((self.at_distance("20")[near_yield], self.at_distance("20")[near_cripple]), (True, True))


class Verdicts(unittest.TestCase):
    def test_every_example_connection_passes(self):
        # flange_force.card states no panel_shear or axial load, which the panel zone reads (build.NEEDS)
        left_open = {"flange_force.petra": {"ff1/steel.panel_zone/coverage.steel.panel_zone"}}
        for path in sorted(STEEL.glob("*.petra")):
            with self.subTest(example=path.name):
                found = outcomes(load_design(path, REGISTRY))
                self.assertTrue(found)
                self.assertEqual({r: o for r, o in found.items() if o != "Discharged"},
                                 dict.fromkeys(left_open.get(path.name, ()), "Open"), found)

    def test_a_short_edge_fails_the_minimum_edge_distance(self):
        found = outcomes(design("shear_tab", ("edge_vertical 1.5 inch", "edge_vertical 0.75 inch")))
        self.assertEqual(found["st1/steel.edge_min/coverage.steel.edge_min"], "Refuted")

    def test_a_small_fillet_fails_the_minimum_size_and_ductility(self):
        found = outcomes(design("shear_tab", ("size 0.25 inch", "size 0.125 inch")))
        self.assertEqual(found["st1/steel.fillet_size/coverage.steel.fillet_size"], "Refuted")
        self.assertEqual(found["st1/steel.ductility/coverage.steel.ductility"], "Refuted")
        self.assertEqual(found["st1/steel.weld/coverage.steel.weld"], "Discharged")

    def test_a_claim_tightens_the_utilisation(self):
        # the bolts read 45 / 63.632 = 0.707, above the tight claim's 0.6
        extra = "\nclaim tight: st1.bolts <= 0.6 under gravity\nclaim loose: st1.block_shear <= 0.9 under gravity\n"
        found = outcomes(design("shear_tab", extra=extra))
        self.assertEqual(found["st1/steel.bolts/claim.tight"], "Refuted")
        self.assertEqual(found["st1/steel.block_shear/claim.loose"], "Discharged")

    def test_a_load_case_without_the_shear_leaves_every_check_open(self):
        d = design("shear_tab", card=(("on st1 shear in [0 kip, 45 kip]", "on st1 axial in [0 kip, 5 kip]"),))
        report = check_design(d, REGISTRY, (SolverSource(),))
        self.assertTrue(report.outcomes)
        for o in report.outcomes:
            self.assertEqual(type(o).__name__, "Open", o)
            if o.requirement.id != "st1/steel.load_path/coverage.steel.load_path":
                self.assertIn(NeedsInputBound(("st1",), "shear", "kip"), o.needs, o.requirement.id)


BOTTOM_COPE_CARD = """petra 0

card "gate-1-05546" {
  owner "gate@petra.dev"
}

load gate {
  on c1 shear in [0 kip, 10.728 kip]
  signed "gate@petra.dev" source "steel gate generator"
}
"""

BOTTOM_COPE = """petra 0

single_angle c1 {
  basis asd
  beam W12x26 grade steel.A992
  support W12x65 web grade steel.A992
  angle L4x4x1_2 grade steel.A36 outstanding short
  bolts bolt_group.120 diameter 0.875 inch threads included
  holes angle ssl
  top 3.5 inch
  rows 3
  pitch 3 inch
  edge_vertical 1.5 inch
  beam_edge 1.5 inch
  beam_gauge 2.25 inch
  support_side welded
  support_weld electrode.E70 size 0.25 inch
  cope both depth 1.5 inch length 3 inch bottom_depth 2 inch
  setback 0.5 inch
}
"""


class BottomCopeEdge(unittest.TestCase):
    """J3.5 holds a bolt's centre a Table J3.4 distance from every edge of the part, the
    cut edge of a beam's bottom cope among them. The gate's single angle gate-1-05546:
    a W12x26 (d = 12.2 in) coped 1-1/2 in at the top and 2 in at the bottom, three 7/8 in
    bolts from 3-1/2 in below its top at 3 in. The bottom bolt sits 3.5 + 2 x 3 = 9.5 in
    down, 12.2 - 2 - 9.5 = 0.7 in above the bottom cope, where Table J3.4 asks 1-1/8 in.
    The deck passed it at 03a6fbf."""

    def test_a_bolt_near_the_bottom_cope_fails_the_minimum_edge_distance(self):
        d = parse_design(BOTTOM_COPE_CARD, BOTTOM_COPE, "gate.petra", REGISTRY)
        self.assertEqual(outcomes(d)["c1/steel.edge_min/coverage.steel.edge_min"], "Refuted")
        found = checks(d, "c1", "edge_min", "gate")["beam web: bottom cope edge distance at least Table J3.4's (J3.5)"]
        self.assertAlmostEqual(found.demand, 1.125, places=9)
        self.assertAlmostEqual(found.capacity, 0.7, places=9)

    def test_the_bottom_cope_takes_c2_and_no_maximum(self):
        """Table J3.5 adds C2 = 1/16 in for a 7/8 in bolt's oversized hole. J3.6 bounds the
        distance to a bolt's nearest edge, which the beam end already holds within its
        limit, so the bottom cope takes no maximum: on a W18x50 (d = 18.0 in) it sits
        18.0 - 2 - 9.5 = 6.5 in below the bottom bolt, past J3.6's 6 in."""
        text = BOTTOM_COPE.replace("W12x26", "W18x50").replace("holes angle ssl", "holes beam ovs")
        text = text.replace("threads included", "threads included joint slip_critical surface class_a")
        d = parse_design(BOTTOM_COPE_CARD, text, "gate.petra", REGISTRY)
        found = checks(d, "c1", "edge_min", "gate")
        near = found["beam web: bottom cope edge distance at least Table J3.4's plus Table J3.5's C2 for its ovs holes (J3.5)"]
        self.assertAlmostEqual(near.demand, 1.125 + 0.0625, places=9)
        self.assertAlmostEqual(near.capacity, 6.5, places=9)
        self.assertFalse([what for what in checks(d, "c1", "edge_max", "gate") if "bottom cope" in what])
        self.assertEqual(outcomes(d)["c1/steel.edge_max/coverage.steel.edge_max"], "Discharged")


if __name__ == "__main__":
    unittest.main()
