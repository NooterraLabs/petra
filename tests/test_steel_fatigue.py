"""Fatigue on code-defined details (AISC 360-22 Appendix 3), as a user of the steel deck sees it.

A load case that names cycles on a connection is cyclic. Coverage then demands the fatigue
check of every detail on the load path, each a stress range against Table A-3.1's allowable
range and a peak stress against 0.66 Fy, excused at 20,000 cycles or fewer. A detail whose
category the deck does not encode leaves the verdict UNKNOWN. A design with no cyclic case
owes no fatigue check, and the readout says a cyclic load would demand them.

Hand values for examples/steel/shear_tab_cyclic.petra (plate 3/8 x 12 in, four 3/4 in bolts
at 3 in, a = 3 in, W18x50 coped 1.5 in top and 2 in bottom over 5 in, setback 1/2 in; the
shear range 8 kip, peak 10 kip):
    plate end   S = 0.375 x 12^2 / 6 = 9 in^3; 8 x 3 / 9 + 3 x 8 / (2 x 0.375 x 12) = 5.333 ksi
    category C  1000 (4.4 / 500,000)^0.333 = 20.73 ksi
    category E' 1000 (0.39 / 500,000)^0.333 = 9.248 ksi
    category B  1000 (12 / 500,000)^0.333 = 28.95 ksi; at 2e8 cycles its threshold, 16 ksi
    category F  100 (1.5 / 500,000)^0.167 = 11.96 ksi
    RFIL        (0.06 + 0.72 x 0.25 / 0.375) / 0.375^0.167 = 0.6361, root 13.18 ksi
"""
import unittest
from pathlib import Path

from petra.lang import load_design, parse_design
from petra.models.steel import calc, domain
from petra.models.steel.cyclic import NOT_CYCLIC
from petra.models.steel.vocab import MODES
from petra.pipeline import check_design
from petra.registry import build_registry
from petra.solvers import SolverSource
from petra.verdict import STATUS

REGISTRY = build_registry()
STEEL = Path(__file__).resolve().parents[1] / "examples" / "steel"
EXAMPLE = (STEEL / "shear_tab_cyclic.petra").read_text(encoding="utf-8")
ENCODED = {"fatigue_bolted", "fatigue_weld", "fatigue_weld_end", "fatigue_cope"}


def variant(*edits: tuple[str, str], text: str = EXAMPLE):
    for old, new in edits:
        assert old in text, old
        text = text.replace(old, new)
    return parse_design(text, "variant.petra", REGISTRY)


def status(d) -> tuple[str, dict[str, str]]:
    report = check_design(d, REGISTRY, (SolverSource(),))
    modes = {}
    for o in report.outcomes:
        req = o.obligation.requirement if hasattr(o, "obligation") else o.requirement
        modes.setdefault(req.mode.id.removeprefix("steel."), set()).add(type(o).__name__)
    return STATUS[type(report.verdict)], modes


def values(d, mode: str, case: str = "crane", conn: str = "st1") -> dict[str, calc.Value]:
    return {v.what: v for v in calc.values(calc.connection(d, conn, REGISTRY), d, REGISTRY, mode, case)}


def one(found: dict[str, calc.Value], phrase: str) -> calc.Value:
    hits = [v for what, v in found.items() if phrase in what]
    assert len(hits) == 1, (phrase, list(found))
    return hits[0]


class CyclicCoverage(unittest.TestCase):
    def test_the_cyclic_example_owes_and_passes_every_fatigue_check_of_its_details(self):
        d = load_design(STEEL / "shear_tab_cyclic.petra", REGISTRY)
        owed = {m for m in domain.required(calc.connection(d, "st1", REGISTRY), d) if m.startswith("fatigue")}
        self.assertEqual(owed, ENCODED)
        verdict, modes = status(d)
        self.assertEqual(verdict, "PASS")
        self.assertTrue(all(modes[m] == {"Discharged"} for m in ENCODED))

    def test_without_a_cyclic_case_no_fatigue_check_is_owed_and_the_reason_says_why(self):
        d = load_design(STEEL / "shear_tab.petra", REGISTRY)
        conn = calc.connection(d, "st1", REGISTRY)
        self.assertFalse([m for m in domain.required(conn, d) if m.startswith("fatigue")])
        self.assertEqual(domain.absent(conn, d)[MODES["fatigue_weld_end"]], NOT_CYCLIC)

    def test_a_plate_welded_on_one_face_is_unknown_never_pass(self):
        verdict, modes = status(variant(("sides 2", "sides 1")))
        self.assertEqual(modes["fatigue_detail"], {"Open"})
        self.assertNotEqual(verdict, "PASS")
        self.assertNotIn("fatigue_weld_end", modes)

    def test_a_snug_tight_joint_under_a_cyclic_load_fails_its_joint_type(self):
        verdict, modes = status(variant((" joint pretensioned", "")))
        self.assertEqual(verdict, "FAIL")
        self.assertIn("Refuted", modes["joint_type"])
        self.assertNotIn("fatigue_bolted", modes)
        what = one(values(variant((" joint pretensioned", "")), "joint_type"), "its load cyclic")
        self.assertGreater(what.utilisation, 1)

    def test_a_snug_tight_joint_under_a_static_load_alone_passes(self):
        static = EXAMPLE[:EXAMPLE.index("load crane")]
        verdict, _ = status(variant((" joint pretensioned", ""), text=static))
        self.assertEqual(verdict, "PASS")


class AllowableRanges(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load_design(STEEL / "shear_tab_cyclic.petra", REGISTRY)

    def test_the_finite_life_ranges_match_the_hand_values(self):
        weld_end = values(self.d, "fatigue_weld_end")
        toe, root = one(weld_end, "weld toe"), one(weld_end, "weld root")
        self.assertAlmostEqual(float(toe.demand), 16 / 3, places=3)
        self.assertAlmostEqual(float(toe.capacity), 20.726, places=2)
        self.assertAlmostEqual(float(root.capacity), 13.184, places=2)
        self.assertAlmostEqual(float(one(values(self.d, "fatigue_cope"), "category E'").capacity), 9.248, places=2)
        self.assertAlmostEqual(float(one(values(self.d, "fatigue_weld"), "category F").capacity), 11.959, places=2)
        self.assertAlmostEqual(float(one(values(self.d, "fatigue_bolted"), "plate (beam side): stress range").capacity),
                               28.95, places=1)

    def test_past_its_knee_each_category_holds_at_its_threshold(self):
        d = variant(("cycles in [0, 500000]", "cycles in [0, 200000000]"))
        self.assertEqual(float(one(values(d, "fatigue_bolted"), "plate (beam side): stress range").capacity), 16)
        self.assertEqual(float(one(values(d, "fatigue_weld_end"), "weld toe").capacity), 10)
        self.assertEqual(float(one(values(d, "fatigue_cope"), "category E'").capacity), 2.6)
        self.assertEqual(float(one(values(d, "fatigue_weld"), "category F").capacity), 8)

    def test_at_20000_cycles_every_fatigue_check_is_excused(self):
        d = variant(("cycles in [0, 500000]", "cycles in [0, 20000]"))
        for mode in ENCODED:
            with self.subTest(mode):
                self.assertTrue(all(v.excused for v in values(d, mode).values()))

    def test_the_root_check_is_excused_where_rfil_reaches_one(self):
        # a 5/16 in fillet on a 3/8 in plate: RFIL = (0.06 + 0.72 x 0.833) / 0.375^0.167 = 0.78;
        # on a 1/4 in plate (0.06 + 0.72 x 1.25) / 0.25^0.167 = 1.21, so the toe governs alone
        thick = values(variant(("size 0.25 inch sides 2", "size 0.3125 inch sides 2")), "fatigue_weld_end")
        self.assertFalse(one(thick, "weld root").excused)
        thin = values(variant(("thickness 0.375 inch", "thickness 0.25 inch"),
                              ("size 0.25 inch sides 2", "size 0.3125 inch sides 2")), "fatigue_weld_end")
        self.assertTrue(one(thin, "weld root").excused)

    def test_the_peak_load_is_held_to_two_thirds_of_fy(self):
        peak = one(values(self.d, "fatigue_weld_end"), "peak cyclic load")
        self.assertAlmostEqual(float(peak.demand), 10 * 3 / 9 + 30 / 9, places=3)
        self.assertAlmostEqual(float(peak.capacity), 0.66 * 36, places=3)

    def test_a_two_column_plate_end_takes_the_moment_to_its_bolt_group_centroid(self):
        d = variant(("support W14x90 flange", "support W14x90 web"), ("  rows 4\n", "  rows 4\n  columns 2\n  gauge 3 inch\n"),
                    ("bolt_line 3 inch", "bolt_line 6 inch"), ("beam_edge 1.75 inch", "beam_edge 2 inch"),
                    ("  weld electrode", "  form extended\n  weld electrode"))
        toe = one(values(d, "fatigue_weld_end"), "weld toe")
        self.assertAlmostEqual(float(toe.demand), 8 * (6 + 1.5) / 9 + 24 / 9, places=3)


class BoltsInTension(unittest.TestCase):
    HANGER = (STEEL / "hanger.petra").read_text(encoding="utf-8") + (
        '\nload hoist {\n  on h1 tension in [2 kip, 10 kip]\n  on h1 cycles in [0, 500000]\n'
        '  signed "s.engineer@example.org" source "hoist, service loads"\n}\n')

    def test_pretensioned_bolts_carry_a_fifth_of_the_peak_on_their_tensile_stress_area(self):
        d = parse_design(self.HANGER, "hanger.petra", REGISTRY)
        check = one(values(d, "fatigue_bolt_tension", "hoist", "h1"), "category G")
        at = 3.14159265 / 4 * (0.75 - 0.9743 / 10) ** 2           # Eq A-3-7, 10 threads per inch
        self.assertAlmostEqual(float(check.demand), 0.2 * 10 / 4 / at, places=3)
        self.assertAlmostEqual(float(check.capacity), 1000 * (0.39 / 5e5) ** 0.333, places=2)     # 9.25 ksi > FTH 7

    def test_a_cyclic_hanger_is_unknown_for_its_tee(self):
        verdict, modes = status(parse_design(self.HANGER, "hanger.petra", REGISTRY))
        self.assertEqual(verdict, "UNKNOWN")
        self.assertEqual(modes["fatigue_detail"], {"Open"})
        self.assertEqual(modes["fatigue_bolt_tension"], {"Discharged"})


if __name__ == "__main__":
    unittest.main()
