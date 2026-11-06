"""Steel deck element limit states (M2): the AISC 360-22 Chapter J and RCSC 2025 strengths
reproduce the AISC Manual's published values, the shear tab example's checks match a hand
calculation, the J10 guards excuse exactly the checks they should, every example
connection passes, and a corrupted design fails on the check it breaks.

Published values (AISC Steel Construction Manual, 16th ed., Parts 7 and 8), each recomputed
from the registry's rows through lola.models.steel.limits, LRFD:
    3/4 in Group 120 bolt, single shear: threads included 17.9 kips, excluded 22.5 kips
    3/4 in Group 120 bolt, tension: 29.8 kips
    3/4 in Group 120 bolt, slip, Class A, standard holes, one plane: 9.49 kips
    bearing of a 3/4 in bolt per inch of thickness, Fu = 58 ksi: 78.3 kips/in
    tearout of a 3/4 in bolt in a standard hole, edge 1 1/4 in, Fu = 58 ksi: 44.0 kips/in
    E70 fillet weld, per sixteenth of an inch of leg, per inch of length: 1.392 kips/in

Hand values for examples/steel/shear_tab.lola (W18x50 beam, 3/8 in A36 plate, four 3/4 in
Group 120 bolts at 3 in, a = 3 in, V = 45 kips):
    elastic method, e = a: Ip = 4 (15 x 9) / 12 = 45 in2, M = 135 kip-in,
        corner bolt fx = 135 x 4.5 / 45 = 13.5, fy = 45 / 4 = 11.25 -> 17.573 kips
    weakest bolt: shear 0.75 x 54 x 0.4418 = 17.892 kips (bearing and tearout are larger)
    plate shear yield 1.0 x 0.6 x 36 x 12 x 0.375 = 97.2; rupture 0.75 x 0.6 x 58 x 8.5 x 0.375 = 83.194
    plate flexure 0.9 x 36 x 13.5 = 437.4 kip-in; rupture 0.75 x 58 x 9.5625 = 415.969 kip-in
    welds 2 x 12 x 4 x 1.392 = 133.643 kips
"""
import unittest
from fractions import Fraction
from pathlib import Path

from lola.kernel import enclose
from lola.lang import load_design, parse_design
from lola.models.base import NeedsInputBound
from lola.models.steel import calc
from lola.models.steel import limits as L
from lola.models.steel.checks import block_paths
from lola.pipeline import check_design
from lola.registry import build_registry
from lola.solvers import SolverSource
from lola.units import CUSTOMARY

REGISTRY = build_registry()
STEEL = Path(__file__).resolve().parents[1] / "examples" / "steel"
INCH, KIP, KSI = (CUSTOMARY[u][0] for u in ("inch", "kip", "ksi"))


def const(name: str):
    return L.c(REGISTRY.constants[name].value.lo)


def prop(material: str, name: str):
    return L.c(REGISTRY.materials[material].props[name].value.lo)


def value(expr, per=KIP) -> float:
    return float(enclose(expr, {}).lo / per)


def design(name: str, *edits: tuple[str, str], extra: str = ""):
    text = (STEEL / f"{name}.lola").read_text(encoding="utf-8")
    for old, new in edits:
        if old not in text:
            raise AssertionError(f"{old!r} is not in {name}.lola")
        text = text.replace(old, new)
    return parse_design(text + extra, f"{name}.lola", REGISTRY)


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
        considered, _ = L.BEARING["considered"]
        bearing = L.mul(phi, L.bearing(self.d, t, fu, considered))
        lc = L.sub(L.c(Fraction(5, 4) * INCH), L.div(const("bolt_us.3_4.std"), L.c(2)))
        tearout = L.mul(phi, L.tearout(lc, t, fu, L.BEARING["considered"][1]))
        self.assertAlmostEqual(value(bearing), 78.3, places=1)
        self.assertAlmostEqual(value(tearout), 44.0, places=1)

    def test_fillet_weld_per_sixteenth(self):
        w = L.mul(const("aisc360.j2_4.phi"), L.fillet_per_length(prop("electrode.E70", "FEXX"), L.c(INCH / 16)))
        self.assertAlmostEqual(value(w, KIP / INCH), 1.392, places=3)


class ElasticMethod(unittest.TestCase):
    """The block resultant agrees with the corner bolt and with the whole group."""

    def test_a_whole_group_carries_the_force_and_a_corner_block_the_corner_bolt(self):
        v, e, s, g = L.c(40), L.c(8), L.c(3), L.c(3)
        fx, fy = L.elastic_block_force(v, e, L.c(8), 4, 2, s, g, 4, 2)
        self.assertEqual((value(fx, 1), value(fy, 1)), (0.0, 40.0))
        corner = L.elastic_bolt_force(v, e, L.c(4), 4, 1, s, L.c(0))
        block = L.elastic_block_force(v, e, L.c(4), 4, 1, s, L.c(0), 1, 1)
        self.assertEqual([value(x, 1) for x in corner], [value(x, 1) for x in block])

    def test_three_rows_of_a_two_column_bracket(self):
        # Ip = 8 (15 x 9 + 3 x 9) / 12 = 108; |sum y| = 2 x 3 x 1 x 3 / 2 = 9; |sum x| = 0
        fx, fy = L.elastic_block_force(L.c(40), L.c(8), L.c(8), 4, 2, L.c(3), L.c(3), 3, 2)
        self.assertAlmostEqual(value(fx, 1), 320 * 9 / 108, places=9)
        self.assertAlmostEqual(value(fy, 1), 30.0, places=9)

    def test_block_paths_cover_every_row_and_column_count(self):
        self.assertEqual(block_paths(2, 2), [(1, 1), (1, 2), (2, 1), (2, 2)])
        self.assertEqual(len(block_paths(4, 3)), 12)


class ShearTabHandValues(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load_design(STEEL / "shear_tab.lola", REGISTRY)

    def test_the_most_loaded_bolt_against_the_weakest(self):
        (bolts,) = checks(self.d, "st1", "bolts").values()
        self.assertAlmostEqual(bolts.demand, 17.573, places=3)
        self.assertAlmostEqual(bolts.available, 17.892, places=3)

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
            self.assertAlmostEqual(found[what].available, available, places=2, msg=what)

    def test_the_full_block_carries_the_reaction_and_smaller_blocks_their_resultant(self):
        found = checks(self.d, "st1", "block_shear")
        self.assertAlmostEqual(found["plate: block of 4 row(s) and 1 column(s) (J4.3)"].demand, 45.0, places=6)
        self.assertAlmostEqual(found["plate: block of 1 row(s) and 1 column(s) (J4.3)"].demand, 17.573, places=3)
        self.assertAlmostEqual(found["plate: block of 4 row(s) and 1 column(s) (J4.3)"].available, 81.12, places=2)

    def test_asd_divides_by_omega(self):
        d = design("shear_tab", ("basis lrfd", "basis asd"), ("[0 kip, 45 kip]", "[0 kip, 30 kip]"))
        (bolts,) = checks(d, "st1", "bolts").values()
        self.assertAlmostEqual(bolts.available, 17.892 / 1.5, places=3)
        self.assertAlmostEqual(bolts.demand, 17.573 * 30 / 45, places=3)


class SeatBearingLength(unittest.TestCase):
    def test_the_seat_arm_uses_the_bearing_length_the_reaction_needs(self):
        # W16x26: J10-3 needs 30 / (50 x 0.25) - 2.5 x 0.747 = 0.53 in; J10-5a needs
        # (30 / 0.75 / 35.36 - 1) / (0.25 / 0.345)^1.5 x 15.7 / 3 = 1.11 in, which governs.
        # Arm = 0.75 + 1.113 / 2 - (0.75 + 0.375) = 0.181 in; M = 30 x 0.181 = 5.43 kip-in.
        d = load_design(STEEL / "seated.lola", REGISTRY)
        (flexure,) = checks(d, "seat1", "seat_flexure").values()
        self.assertAlmostEqual(flexure.demand, 5.43, places=1)
        self.assertAlmostEqual(flexure.available, 0.9 * 36 * 8 * 0.75 ** 2 / 4, places=6)


class J10Guards(unittest.TestCase):
    def at_distance(self, inches: str) -> dict[str, bool]:
        d = design("flange_force", ("location interior", f"location end\n  distance {inches} inch"))
        found = {**checks(d, "ff1", "web_local_yielding"), **checks(d, "ff1", "web_crippling")}
        return {what: v.excused for what, v in found.items()}

    def test_end_checks_apply_only_within_their_distance(self):
        # W14x90: d = 14.0 in. J10-3 applies within d of the end, J10-5 within d/2.
        near_yield, near_cripple = "web local yielding within d of the member end (J10.2)", \
            "web local crippling within d/2 of the member end (J10.3)"
        self.assertEqual((self.at_distance("5")[near_yield], self.at_distance("5")[near_cripple]), (False, False))
        self.assertEqual((self.at_distance("10")[near_yield], self.at_distance("10")[near_cripple]), (False, True))
        self.assertEqual((self.at_distance("20")[near_yield], self.at_distance("20")[near_cripple]), (True, True))


class Verdicts(unittest.TestCase):
    def test_every_example_connection_passes(self):
        for path in sorted(STEEL.glob("*.lola")):
            with self.subTest(example=path.name):
                found = outcomes(load_design(path, REGISTRY))
                self.assertTrue(found)
                self.assertEqual(set(found.values()), {"Discharged"}, found)

    def test_a_short_edge_fails_the_minimum_edge_distance(self):
        found = outcomes(design("shear_tab", ("edge_vertical 1.5 inch", "edge_vertical 0.75 inch")))
        self.assertEqual(found["st1/steel.edge_min/coverage.steel.edge_min"], "Refuted")

    def test_a_small_fillet_fails_the_minimum_size_and_ductility(self):
        found = outcomes(design("shear_tab", ("size 0.25 inch", "size 0.125 inch")))
        self.assertEqual(found["st1/steel.fillet_size/coverage.steel.fillet_size"], "Refuted")
        self.assertEqual(found["st1/steel.ductility/coverage.steel.ductility"], "Refuted")
        self.assertEqual(found["st1/steel.weld/coverage.steel.weld"], "Discharged")

    def test_a_claim_tightens_the_utilisation(self):
        extra = "\nclaim tight: st1.bolts <= 0.95 under gravity\nclaim loose: st1.block_shear <= 0.9 under gravity\n"
        found = outcomes(design("shear_tab", extra=extra))
        self.assertEqual(found["st1/steel.bolts/claim.tight"], "Refuted")
        self.assertEqual(found["st1/steel.block_shear/claim.loose"], "Discharged")

    def test_a_load_case_without_the_shear_leaves_every_check_open(self):
        d = design("shear_tab", ("on st1 shear in [0 kip, 45 kip]", "on st1 axial in [0 kip, 5 kip]"))
        report = check_design(d, REGISTRY, (SolverSource(),))
        self.assertTrue(report.outcomes)
        for o in report.outcomes:
            self.assertEqual(type(o).__name__, "Open", o)
            if o.requirement.id != "st1/steel.load_path/coverage.steel.load_path":
                self.assertIn(NeedsInputBound(("st1",), "shear", "kip"), o.needs, o.requirement.id)


if __name__ == "__main__":
    unittest.main()
