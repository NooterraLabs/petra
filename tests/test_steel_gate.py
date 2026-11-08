"""The steel deck's exhaustiveness machinery (docs/steel_connections.md §9 items 4 to 9) on
a small sample: the generator, decidedness, manufactured faults, the breaker, and the
published gate (docs/steel_gate.md, from `python scripts/steel_gate.py`). Also the deck
fixes the generator, the twin and the breaker found: a hanger's support flange checked for
prying, slip-critical joints checked for combined tension and shear (J3.9), a slender seat
stiffener a FAIL, each bolt's prying tributary by Manual Figure 9-4, a slot's length in
prying's delta, a seat's leg tearing toward its top edge, and a seat stiffener's welds
taking their end-loaded length (J2.2b(d)); and those the red-team pass found: prying under
shear working from F'nt, declared fillers (J5.2), a conventional plate's 2d edges, a plate
welded on one face, a seat stiffener at least as thick as the beam web, the 1/4 in beam
underrun in the strength checks, and a rectangular bracket plate's lateral-torsional
buckling (F11 with F1(c)'s Cb = 1)."""
import re
import unittest
from fractions import Fraction
from pathlib import Path

from petra.lang import parse_design
from petra.models.steel import breaker as B
from petra.models.steel import faults as F
from petra.models.steel import gate as G
from petra.models.steel import generate as gen
from petra.pipeline import check_design
from petra.registry import build_registry
from petra.solvers import SolverSource
from petra.verdict import STATUS

REGISTRY = build_registry()
DOC = Path(__file__).resolve().parents[1] / "docs" / "steel_gate.md"
SAMPLE = list(gen.generate(44, 5, REGISTRY))


def status(text: str) -> tuple[str, dict[str, str]]:
    report = check_design(parse_design(text, "t.petra", REGISTRY), REGISTRY, (SolverSource(),))
    return STATUS[type(report.verdict)], G.deck_outcomes(report)[0]


class Generator(unittest.TestCase):
    def test_a_slice_is_the_same_whoever_draws_it(self):
        again = list(gen.generate(4, 5, REGISTRY, start=20))
        self.assertEqual([g.text for g in again], [g.text for g in SAMPLE[20:24]])

    def test_every_kind_is_drawn(self):
        self.assertEqual({g.kind for g in SAMPLE}, set(gen.SAMPLERS))

    def test_loads_carry_the_margin(self):
        for g in SAMPLE:
            with self.subTest(g.name):
                if g.target == "pass":
                    self.assertLessEqual(g.utilisation, 1 - gen.DELTA)
                else:
                    self.assertGreaterEqual(g.utilisation, 1 + gen.DELTA)
                if not g.free:
                    self.assertLessEqual(g.geometry, 1)

    def test_a_toleranced_bracket_is_decided_on_the_side_its_load_was_aimed(self):
        # Gate design 01614. Its free-edge check, enclosed once over the 1/8 in tolerance
        # on its edge distance, read 1.04 at a load where no point of the box passes 0.98,
        # so a load aimed to fail by that reading passed.
        lines = ["  plate steel.A36 thickness 0.625 inch", "  support W12x40 flange grade steel.A992",
                 "  bolts bolt_group.120 diameter 0.875 inch threads excluded", "  rows 2", "  columns 2",
                 "  pitch 3 inch", "  gauge 4 inch", "  eccentricity 6 inch",
                 '  edge_vertical in [1.9375 inch, 2.0625 inch] signed "gate@petra.dev" source "steel gate generator"',
                 "  plate_edge 2 inch", "  free_edge 6 inch"]
        build = lambda load: gen.source("aim", "bolt_bracket", "lrfd", lines, load)
        for goal, expected in ((Fraction(104, 100), "FAIL"), (Fraction(96, 100), "PASS")):
            with self.subTest(goal=goal):
                load, u, mode, _ = gen.scale(build, goal, REGISTRY)
                self.assertEqual(mode, "bracket_edge")
                self.assertEqual(status(build(load))[0], expected)

    def test_min_fillet_follows_table_j2_4(self):
        self.assertEqual([gen.min_fillet(Fraction(t)) for t in ("0.25", "0.5", "0.75", "1")],
                         [Fraction(1, 8), Fraction(3, 16), Fraction(1, 4), Fraction(5, 16)])


class Decidedness(unittest.TestCase):
    def test_every_sample_is_decided_as_expected_and_fails_with_a_witness(self):
        for g in SAMPLE:
            with self.subTest(g.name):
                a = G.assess(g, REGISTRY, with_twin=False)
                self.assertEqual(a.status, g.expected)
                if a.status == "FAIL":
                    self.assertTrue(a.witnessed)


class Faults(unittest.TestCase):
    def test_every_fault_is_caught_and_named(self):
        seen = set()
        for c in F.seed_faults(REGISTRY, per_kind=1, seed=101):
            seen.add(c.fault)
            with self.subTest(c.fault, base=c.base):
                self.assertTrue(c.caught and c.is_named, c)
        self.assertGreaterEqual(len(seen), len(F.FAULTS) - 2, "most faults apply to the first base of their kinds")


class Breaker(unittest.TestCase):
    def setUp(self):
        self.base = next(g for g in SAMPLE if g.kind == "shear_tab" and g.expected == "PASS" and not g.toleranced)

    def test_an_oracle_that_agrees_finds_nothing(self):
        def deck(text):
            out = {}
            for (mode, _), v in gen.checks(text, REGISTRY).items():
                out[mode] = max(out.get(mode, 0.0), v.utilisation)
            return out
        run = B.run(self.base, REGISTRY, deck, 6, 0)
        self.assertEqual(run.evaluations, 6)
        self.assertEqual(run.found, [])
        self.assertLessEqual(run.best, 1 + B.SLACK)

    def test_an_oracle_that_disagrees_is_found_and_logged(self):
        run = B.run(self.base, REGISTRY, lambda text: {"bolts": 1.5}, 3, 0)
        self.assertTrue(run.found)
        self.assertEqual(run.log()["false_pass"][0]["modes"], ["bolts"])


class Comparison(unittest.TestCase):
    def test_disagreement_reading(self):
        self.assertEqual(G.compare({"bolts": "pass", "slip": "fail"}, {"bolts": 0.9, "slip": 1.2}), [])
        self.assertEqual(G.compare({"bolts": "pass"}, {"bolts": 1.01}), [("bolts", "pass", 1.01)])
        self.assertEqual(G.compare({"bolts": "fail"}, {"bolts": 0.5}), [("bolts", "fail", 0.5)])
        self.assertEqual(G.compare({"bolts": "pass"}, {}), [("bolts", "pass", None)])
        self.assertEqual(G.compare({}, {"slip": 0.2}), [("slip", "absent", 0.2)])

    def test_a_certified_weld_fail_may_lie_within_the_certificates_loss(self):
        self.assertEqual(G.compare({"weld": "fail"}, {"weld": 0.995}), [])
        self.assertEqual(G.compare({"weld_base_metal": "fail"}, {"weld_base_metal": 0.993}), [])
        self.assertEqual(G.compare({"weld": "fail"}, {"weld": 0.98}), [("weld", "fail", 0.98)])
        self.assertEqual(G.compare({"weld": "pass"}, {"weld": 1.005}), [("weld", "pass", 1.005)])
        self.assertEqual(G.compare({"block_shear": "fail"}, {"block_shear": 0.995}), [("block_shear", "fail", 0.995)])


HANGER = ["  tee {tee} grade steel.A992", "  support {support} flange grade steel.A992",
          "  bolts bolt_group.120 diameter 0.75 inch threads included{joint}", "  rows 2", "  pitch 3 inch",
          "  tee_gauge 3.5 inch", "  edge_vertical 1.5 inch"]


class DeckFixes(unittest.TestCase):
    def hanger(self, tee, support, joint="", shear=None):
        lines = [x.format(tee=tee, support=support, joint=joint) for x in HANGER]
        secondary = (("shear", Fraction(shear)),) if shear else ()
        return gen.source("h", "hanger", "lrfd", lines, Fraction(20), secondary)

    def test_a_thinner_support_flange_is_checked_for_prying_not_left_open(self):
        # WT7x26.5 (tf 0.660 in) under a W21x57 (tf 0.650 in): the support flange is the thinner.
        text = self.hanger("WT7x26_5", "W21x57")
        verdict, modes = status(text)
        self.assertIn(verdict, ("PASS", "FAIL"))
        whats = [v.what for (m, _), v in gen.checks(text, REGISTRY).items() if m == "prying"]
        self.assertTrue(any("support flange" in w for w in whats) and any("tee flange" in w for w in whats), whats)

    def test_a_slip_critical_hanger_with_shear_checks_combined_tension_and_shear(self):
        text = self.hanger("WT9x25", "W21x62", " joint slip_critical surface class_a", shear="0.3")
        verdict, modes = status(text)
        self.assertIn(verdict, ("PASS", "FAIL"))
        self.assertIn(modes.get("bolt_combined"), ("pass", "fail"))
        self.assertIn(modes.get("slip"), ("pass", "fail"))

    def test_a_slender_seat_stiffener_fails_rather_than_leaving_the_model(self):
        lines = ["  beam W21x44 grade steel.A992", "  support W14x90 flange grade steel.A992",
                 "  plate steel.A36 thickness 0.375 inch", "  stiffener steel.A36 thickness 0.375 inch",
                 "  stiffener_width 6 inch", "  stiffener_length 12 inch", "  setback 0.75 inch",
                 "  weld electrode.E70 size 0.3125 inch sides 2", "  top_angle L4x4x1_4 grade steel.A36 outstanding long"]
        verdict, modes = status(gen.source("s", "stiffened_seat", "lrfd", lines, Fraction(20)))
        self.assertEqual((verdict, modes["compression"]), ("FAIL", "fail"))

    def prying(self, holes, rows):
        lines = [x.format(tee="WT9x25", support="W21x62", joint="") for x in HANGER]
        lines = [x.replace("rows 2", f"rows {rows}") for x in lines] + [f"  holes flange {holes}"]
        text = gen.source("h", "hanger", "lrfd", lines, Fraction(20))
        return {v.what: v.utilisation for (m, _), v in gen.checks(text, REGISTRY).items() if m == "prying"}

    def test_prying_takes_each_bolts_tributary_length_by_figure_9_4(self):
        # Companion II.D-1: an end bolt min(le, 1.75 b) + min(s/2, 1.75 b), an inner bolt
        # 2 min(s/2, 1.75 b); each flange with its own b
        whats = list(self.prying("std", 3))
        for flange in ("tee flange", "support flange"):
            for bolts in ("end bolts", "inner bolts"):
                self.assertTrue(any(f"{flange} at the {bolts}" in w for w in whats), (flange, bolts, whats))

    def test_a_parallel_slot_takes_its_length_in_pryings_delta(self):
        # delta = 1 - d'/p, d' along the flange: a slot along the tee weakens it more than across
        across, along = self.prying("ssl", 2), self.prying("ssl_parallel", 2)
        tee = next(w for w in across if "tee flange" in w)
        self.assertGreater(along[tee], across[tee])

    def test_a_seat_leg_tears_toward_its_top_edge(self):
        # the bolts hold the seat up, so its vertical leg tears up from the top row
        def bolts(lev):
            lines = ["  beam W18x35 grade steel.A992", "  support W12x50 flange grade steel.A992",
                     "  angle L6x4x3_8 grade steel.A36 outstanding short", "  seat_length 6 inch",
                     "  setback 0.75 inch", "  support_side bolted",
                     "  bolts bolt_group.150 diameter 0.75 inch threads excluded", "  rows 2", "  pitch 3 inch",
                     f"  edge_vertical {lev} inch", "  support_gauge 3.5 inch",
                     "  top_angle L4x4x1_4 grade steel.A36 outstanding long"]
            text = gen.source("s", "seated", "lrfd", lines, Fraction(20))
            return max(v.utilisation for (m, _), v in gen.checks(text, REGISTRY).items() if m == "bolts")
        self.assertGreater(bolts(1), bolts(2))

    def test_a_long_stiffener_weld_counts_its_end_loaded_length(self):
        # J2.2b(d): a seat stiffener's welds are end-loaded (Commentary J2.2b); past 100 w only
        # beta l counts (Eq J2-1). At 75 w the check is excused; at 128 w it governs.
        def weld(length):
            lines = ["  beam W21x44 grade steel.A992", "  support W14x90 flange grade steel.A992",
                     "  plate steel.A36 thickness 0.375 inch", "  stiffener steel.A36 thickness 0.5 inch",
                     "  stiffener_width 6 inch", f"  stiffener_length {length} inch", "  setback 0.75 inch",
                     "  weld electrode.E70 size 0.1875 inch sides 2",
                     "  top_angle L4x4x1_4 grade steel.A36 outstanding long"]
            text = gen.source("s", "stiffened_seat", "lrfd", lines, Fraction(40))
            return {v.what: v.utilisation for (m, _), v in gen.checks(text, REGISTRY).items() if m == "weld"}
        short, long = weld(14), weld(24)
        end_loaded = next(w for w in long if "end-loaded" in w)
        self.assertEqual(short[end_loaded], 0.0)
        self.assertGreater(long[end_loaded], max(u for w, u in long.items() if w != end_loaded))

    def tab(self, *edits: tuple[str, str]) -> str:
        lines = ["  beam W16x26 grade steel.A992", "  support W14x90 web grade steel.A992",
                 "  plate steel.A36 thickness 0.375 inch", "  bolts bolt_group.120 diameter 0.75 inch threads included",
                 "  rows 3", "  pitch 3 inch", "  edge_vertical 1.5 inch", "  plate_edge 1.5 inch", "  bolt_line 3 inch",
                 "  beam_edge 1.75 inch", "  top 3 inch", "  weld electrode.E70 size 0.25 inch sides 2"]
        for old, new in edits:
            self.assertIn(old, lines)
            lines = [new if x == old else x for x in lines]
        return gen.source("t", "shear_tab", "lrfd", lines, Fraction(30))

    @staticmethod
    def values(text: str, mode: str) -> dict[str, float]:
        return {v.what: v.utilisation for (m, _), v in gen.checks(text, REGISTRY).items() if m == mode}

    def test_prying_under_shear_works_from_the_tension_j3_8_leaves(self):
        # Companion II.A-1B: B = phi F'nt Ab. A WT7x45 under 78 kip of tension and 44 kip of
        # shear: 1.04 by the Manual, 0.78 with B = phi Fnt Ab as before.
        lines = ["  tee WT7x45 grade steel.A992", "  support W14x90 flange grade steel.A992",
                 "  bolts bolt_group.120 diameter 0.75 inch threads included joint pretensioned", "  rows 2",
                 "  pitch 3 inch", "  tee_gauge 4 inch", "  edge_vertical 1.5 inch"]
        sheared = gen.source("h", "hanger", "lrfd", lines, Fraction(78), (("shear", Fraction(44, 78)),))
        plain = gen.source("h", "hanger", "lrfd", lines, Fraction(78))
        self.assertAlmostEqual(max(self.values(sheared, "prying").values()), 1.038, places=3)
        self.assertLess(max(self.values(plain, "prying").values()), 0.8)

    def test_declared_fillers_take_j5_2s_least_factor(self):
        plain = self.values(self.tab(), "bolts")
        filled = self.values(self.tab(("  bolts bolt_group.120 diameter 0.75 inch threads included",
                                       "  bolts bolt_group.120 diameter 0.75 inch threads included fillers one")), "bolts")
        self.assertGreater(max(filled.values()), max(plain.values()))

    def test_a_conventional_plate_keeps_2d_horizontal_edges(self):
        # Companion II.A-17A: Leh >= 2d on the plate and on the beam web
        u = self.values(self.tab(("  plate_edge 1.5 inch", "  plate_edge 1.125 inch")), "ductility")
        self.assertAlmostEqual(u["plate: horizontal edge distance at least 2d (Manual Part 10)"], 4 / 3, places=6)

    def test_a_plate_welded_on_one_face_is_outside_the_single_plate_method(self):
        verdict, modes = status(self.tab(("  weld electrode.E70 size 0.25 inch sides 2", "  weld electrode.E70 size 0.25 inch sides 1")))
        self.assertNotEqual(verdict, "PASS")
        self.assertNotIn(modes.get("ductility"), ("pass", "fail"))

    def test_a_seat_stiffener_is_as_thick_as_the_beam_web_scaled_by_yield(self):
        # Companion II.A-14: ts >= tw Fy,beam / Fy,stiffener; a W18x50 web (0.355 in) over an
        # A36 stiffener wants 0.493 in
        lines = ["  beam W18x50 grade steel.A992", "  support W14x90 flange grade steel.A992",
                 "  plate steel.A36 thickness 0.375 inch", "  stiffener steel.A36 thickness 0.375 inch",
                 "  stiffener_width 4 inch", "  stiffener_length 10 inch", "  setback 0.5 inch",
                 "  weld electrode.E70 size 0.25 inch sides 2", "  top_angle L4x4x1_4 grade steel.A36 outstanding long"]
        u = self.values(gen.source("s", "stiffened_seat", "lrfd", lines, Fraction(20)), "compression")
        rule = next(w for w in u if "beam web's thickness" in w)
        self.assertAlmostEqual(u[rule], 0.355 * 50 / 36 / 0.375, places=6)

    def test_a_seat_takes_the_quarter_inch_underrun_on_its_setback(self):
        # Companion II.A-12A and II.A-14: lb = seat - setback - 1/4 in. A seat detailed at a
        # 1/2 in setback is checked as the Companion checks one at 3/4 in.
        def seat(setback: str) -> float:
            lines = ["  beam W16x50 grade steel.A992", "  support W14x90 web grade steel.A992",
                     "  angle L6x4x1_2 grade steel.A572_50 outstanding short", "  seat_length 8 inch",
                     f"  setback {setback} inch", "  support_side bolted",
                     "  bolts bolt_group.120 diameter 0.75 inch threads included", "  rows 2", "  pitch 3 inch",
                     "  edge_vertical 1.25 inch", "  support_gauge 5.5 inch",
                     "  top_angle L4x4x1_4 grade steel.A36 outstanding long"]
            return max(self.values(gen.source("s", "seated", "lrfd", lines, Fraction(40)), "seat_flexure").values())
        # the bearing the reaction needs is kdes = 1.03 in, so M = 40 kip x (3/4 + 1.03 / 2 - (1/2 + 3/8))
        # in = 15.6 kip-in against 0.9 x 50 x 8 x 1/2^2 / 4 = 22.5 kip-in
        self.assertAlmostEqual(seat("0.5"), 40 * (0.75 + 1.03 / 2 - 0.875) / 22.5, places=3)
        self.assertGreater(seat("0.5"), 2 * seat("0.25"))

    def test_a_coped_beam_webs_block_runs_to_the_beam_end_less_the_underrun(self):
        # Companion II.A-4: Ant = (leh - 1/4 in - (dh + 1/16 in) / 2) tw
        coped = [("  top 3 inch", "  top 3 inch\n  setback 0.5 inch\n  cope top depth 1.5 inch length 4 inch")]
        at_2 = self.values(self.tab(*coped, ("  beam_edge 1.75 inch", "  beam_edge 2 inch")), "block_shear")
        at_175 = self.values(self.tab(*coped), "block_shear")
        web = [w for w in at_2 if w.startswith("beam web")]
        self.assertTrue(web)
        self.assertTrue(all(at_175[w] > at_2[w] for w in web))

    def test_a_rectangular_bracket_buckles_as_a_cantilever(self):
        # F11 with Lb = 15 in from section A-A to the load, d = 18 in, t = 1/4 in, Cb = 1
        # (F1(c)): Lb d/t^2 = 4320 > 1.9 E/Fy, Fcr = 1.9 E / 4320 = 12.75 ksi, phi Mn =
        # 0.9 Fcr Sx = 154.95 kip-in against M = 10 x 15 kip-in; yielding alone gives 0.23.
        lines = ["  plate steel.A36 thickness 0.25 inch", "  support W14x90 flange grade steel.A992",
                 "  bolts bolt_group.120 diameter 0.75 inch threads included", "  rows 6", "  columns 2",
                 "  pitch 3 inch", "  gauge 3 inch", "  eccentricity 16.5 inch", "  edge_vertical 1.5 inch",
                 "  plate_edge 1.5 inch"]
        text = gen.source("b", "bolt_bracket", "lrfd", lines, Fraction(10))
        fcr = 1.9 * 29000 / (15 * 18 / 0.25 ** 2)
        self.assertAlmostEqual(max(self.values(text, "plate_buckling").values()), 150 / (0.9 * fcr * 0.25 * 18 ** 2 / 6),
                               places=4)
        self.assertLess(max(self.values(text, "flexural_yield").values()), 0.25)

    def test_a_hanger_hangs_from_a_flange(self):
        text = self.hanger("WT9x25", "W21x62").replace("W21x62 flange", "W21x62 web")
        with self.assertRaises(Exception):
            status(text)


class Published(unittest.TestCase):
    @unittest.skipUnless(DOC.exists(), "docs/steel_gate.md is written by scripts/steel_gate.py")
    def test_the_published_gate_holds(self):
        text = DOC.read_text(encoding="utf-8")
        n = int(re.search(r"Stream seed \d+: (\d+) generated", text).group(1))
        self.assertGreaterEqual(n, 10000)
        self.assertIn(f"| 4. Decidedness | {n} of {n} PASS or FAIL; 0 UNKNOWN or MARGINAL |", text)
        self.assertRegex(text, rf"\| 5\. Twins \| {n} of {n} agree on every mode; 0 disagree; 0 twin errors \|")
        caught = re.search(r"\| 6\. Manufactured faults \| (\d+) of (\d+) caught, (\d+) named", text).groups()
        self.assertEqual(len(set(caught)), 1)
        self.assertRegex(text, r"\| 7\. Breaker \| \d+ runs, \d+ deck evaluations each; 0 found a false PASS \|")
        fails = re.search(r"\| 8\. Makeability \| (\d+) of (\d+) FAILs carry a witness \|", text).groups()
        self.assertEqual(fails[0], fails[1])
        self.assertIn(f"| 9. Report | {n} of {n} calculation packages re-check", text)


if __name__ == "__main__":
    unittest.main()
