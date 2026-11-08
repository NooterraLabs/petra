"""The CalculiX spot check (scripts/calculix_check.py, docs/calculix_check.md).

The offline tests read loop optima from docs/in_the_loop_log.jsonl. The test that runs
CalculiX needs `ccx` on PATH, or a host in $PETRA_CCX_HOST that runs it over ssh, and is
skipped when it has neither.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
import unittest
from pathlib import Path

import numpy as np

import petra

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("calculix_check", ROOT / "scripts" / "calculix_check.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["calculix_check"] = module
    spec.loader.exec_module(module)
    return module


cc = _load()
OPTIMA = {json.loads(line)["task"]: json.loads(line) for line in (ROOT / "docs" / "in_the_loop_log.jsonl").read_text().splitlines()}


def element(task: str):
    return cc.elements(OPTIMA[task]["optimum"], task)[0]


def node_set(inp: str, name: str) -> list[int]:
    body = inp.split(f"*NSET, NSET={name}\n")[1].split("\n*")[0]
    return [int(x) for line in body.splitlines() for x in line.split(",")]


class TheMesh(unittest.TestCase):
    def test_it_covers_the_plate_less_its_holes(self):
        for task in ("202-001", "202-010", "202-006"):
            el = element(task)
            exact = (el.x1 - el.x0) * (el.y1 - el.y0) - len(el.holes) * math.pi * el.dh ** 2 / 4
            for size in (0.5, 0.25):
                with self.subTest(task=task, size=size):
                    self.assertAlmostEqual(cc.mesh(el, size).area(), exact, delta=1e-3 * exact)

    def test_every_quad_turns_counter_clockwise(self):
        m = cc.mesh(element("202-010"), 0.5)
        x, y = m.xy[m.quads[:, :4], 0], m.xy[m.quads[:, :4], 1]
        self.assertTrue(np.all(np.sum(x * np.roll(y, -1, axis=1) - np.roll(x, -1, axis=1) * y, axis=1) > 0))

    def test_no_node_lies_inside_a_hole(self):
        el = element("202-001")
        m = cc.mesh(el, 0.25)
        for hx, hy in el.holes:
            self.assertGreaterEqual(np.hypot(m.xy[:, 0] - hx, m.xy[:, 1] - hy).min(), el.dh / 2 - 1e-9)


class PetrasStrengths(unittest.TestCase):
    def test_the_governing_state_is_the_capacity_petra_check_reports(self):
        text = OPTIMA["202-001"]["optimum"]
        governing = petra.check(text)["governing"]["strength"]
        el = element("202-001")
        state = min((s for s in el.states if s.run == "rupture"), key=lambda s: s.design)
        self.assertEqual(state.what, governing["check"])
        self.assertAlmostEqual(state.design, governing["capacity"], places=3)
        self.assertAlmostEqual(state.nominal, state.design / 0.75, places=6)

    def test_asd_strengths_are_rn_over_omega(self):
        el = element("202-002")
        self.assertEqual(el.basis, "asd")
        state = next(s for s in el.states if s.mode == "shear_yield")
        self.assertAlmostEqual(state.nominal, 1.5 * state.design, places=6)

    def test_a_bolt_group_counts_only_the_elements_bearing_and_tearout(self):
        el = element("202-002")
        bolts = next(s for s in el.states if s.mode == "bolts")
        # four 5/8 in bolts through two 3/8 in A36 angles, ASD (Omega 2.00): each tears out,
        # 1.2 lc t Fu per angle, lc 1.25 - 11/32 in at the bottom bolt and 1.75 - 11/16 in above
        tearout = [1.2 * lc * 0.375 * 58 * 2 / 2.0 for lc in (1.25 - 0.6875 / 2, 1.75 - 0.6875, 1.75 - 0.6875, 1.75 - 0.6875)]
        self.assertLess(max(tearout), 2.4 * 0.625 * 0.375 * 58 * 2 / 2.0)
        self.assertAlmostEqual(bolts.design, sum(tearout), places=6)

    def test_an_eccentric_group_keeps_its_weakest_bolt_and_its_sum(self):
        el = element("202-004")
        bolts = next(s for s in el.states if s.mode == "bolts")
        # the tee stem's four bolts at 1-15/16 in, 3 in from the load, by the instantaneous
        # centre (C = 2.1235, more than the elastic method's 23.379 / 12.333 = 1.896): C times
        # the stem's weakest bolt, tearout to the edge (12.852 kip)
        self.assertAlmostEqual(bolts.design, 2.1235 * 12.852, delta=0.01)
        # summed as a concentric group: three bolts bear (27.056 kip), the bottom one tears out
        self.assertAlmostEqual(bolts.summed, (3 * 27.056 + 12.852) / 0.75, delta=0.01)
        concentric = next(s for s in element("202-002").states if s.mode == "bolts")
        self.assertAlmostEqual(concentric.summed, concentric.nominal, places=9)

    def test_kinds_that_bend_out_of_plane_have_no_element(self):
        for task, row in OPTIMA.items():
            if row["kind"] in ("seated", "stiffened_seat", "hanger") and row["optimum"]:
                self.assertEqual(cc.elements(row["optimum"], task), [])
                break


class TheInput(unittest.TestCase):
    def test_each_run_states_its_material(self):
        el = element("202-001")
        yielding, rupture = cc.deck(el, "yield", 0.5).inp, cc.deck(el, "rupture", 0.5).inp
        self.assertIn("*PLASTIC\n36, 0\n36, 10\n", yielding)
        self.assertIn("*PLASTIC\n36, 0\n36, 0.01\n58, 0.15\n58, 10\n", rupture)

    def test_a_bolt_bears_on_a_third_of_its_hole(self):
        el = element("202-001")
        bearing = node_set(cc.deck(el, "rupture", 0.25).inp, "NLOAD")
        whole = node_set(cc.deck(el, "yield", 0.25).inp, "NLOAD")
        self.assertTrue(set(bearing) < set(whole))
        self.assertAlmostEqual(len(bearing) / len(whole), 1 / 3, delta=0.02)

    def test_a_bracket_rupture_run_holds_each_bolt_the_way_it_bears(self):
        el = element("202-010")
        inp = cc.deck(el, "rupture", 0.5).inp
        self.assertIn("*EQUATION", inp)
        self.assertNotIn("NBOLT", inp)


class ReadingTheResults(unittest.TestCase):
    DAT = """
 total force (fx,fy,fz) for set NLOAD and time  0.5000000E+00

        0.000000E+00 -1.000000E+01  0.000000E+00

 displacements (vx,vy,vz) for set NFAR and time  0.5000000E+00

       {far}  0.000000E+00 -1.000000E-01  0.000000E+00

 total force (fx,fy,fz) for set NLOAD and time  0.1000000E+01

        0.000000E+00 -1.200000E+01  0.000000E+00

 displacements (vx,vy,vz) for set NFAR and time  0.1000000E+01

       {far}  0.000000E+00 -1.000000E-01  0.000000E+00
"""

    def test_the_rupture_capacity_stops_where_a_hole_stretches_a_quarter_inch(self):
        el = element("202-001")
        el = cc.replace(el, holes=el.holes[:1], bears=el.bears[:1])
        job = cc.deck(el, "rupture", 0.5)
        far = cc._far_ids(job)[0]
        curve = cc.parse(self.DAT.format(far=far), job)
        # the bolt has moved 0.2 in and 0.4 in; the hole's far side 0.1 in both times
        self.assertEqual(curve.elongation, (0.1, 0.30000000000000004))
        self.assertEqual(curve.capacity("rupture"), (10.0, 0.5))
        self.assertEqual(curve.capacity("yield"), (12.0, 1.0))
        self.assertTrue(curve.complete)


class TheDirectionOfAFlag(unittest.TestCase):
    @staticmethod
    def curve(load: float, complete: bool = True):
        return cc.Curve((0.5, 1.0), (0.9 * load, load), (0.0, 0.0), complete, ())

    def setUp(self):
        self.el = element("202-001")
        self.r_int = cc.reference(self.el)["r_int"]
        self.design = min(s.design for s in self.el.states if s.run == "yield")

    def judge(self, load: float, complete: bool = True) -> dict:
        return cc.compare(self.el, {"yield": self.curve(load / self.el.copies, complete), "rupture": self.curve(1e4)})

    def test_r_int_is_the_circle_through_von_mises_shear_and_flexure(self):
        ref = cc.reference(self.el)
        self.assertEqual(ref["shear_from"], "petra")
        self.assertAlmostEqual(ref["r_int"] ** -2, (ref["shear"] / math.sqrt(3) / 0.6) ** -2 + ref["flexure"] ** -2, places=12)
        # an LRFD shear tab whose shear yielding governs: von Mises alone puts R_int under phi Rn
        self.assertLess(self.r_int, self.design)

    def test_a_flag_the_model_explains_points_to_the_model(self):
        runs = self.judge(self.r_int)
        self.assertTrue(runs["yield"]["flagged"])
        self.assertEqual(runs["yield"]["direction"], "model")
        self.assertFalse(runs["rupture"]["flagged"])
        self.assertIsNone(runs["rupture"]["direction"])

    def test_a_flag_below_r_int_points_to_the_deck(self):
        self.assertEqual(self.judge((1 - cc.BAND) * self.r_int * 0.99)["yield"]["direction"], "deck")

    def test_a_run_that_stopped_early_is_unresolved(self):
        self.assertEqual(self.judge(0.5 * self.r_int, complete=False)["yield"]["direction"], "unresolved")

    def test_a_verdict_a_finer_mesh_could_change_is_a_close_call(self):
        line = (1 - cc.BAND) * self.r_int
        for load, close in ((self.design * 1.02, True), (self.design * 1.2, False), (line * 1.01, True),
                            (line * 0.98, True), (line * 0.8, False)):
            with self.subTest(load=load / self.design):
                self.assertEqual(cc.close_call({"runs": self.judge(load)}), close)


class CalculiX(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ccx = cc.Ccx(host=os.environ.get("PETRA_CCX_HOST"))
        if not cls.ccx.reachable():
            raise unittest.SkipTest("no ccx on PATH and no reachable $PETRA_CCX_HOST")

    def test_a_plain_plate_yields_in_shear_at_fy_over_root_three(self):
        el, hand, _ = cc.VALIDATION["shear"]
        job = cc.deck(el, "yield", 0.75, "test_shear")
        curve = cc.parse(self.ccx.run([job])["test_shear"], job)
        self.assertTrue(curve.complete)
        self.assertLess(abs(curve.capacity("yield")[0] / hand - 0.98), 0.03)


if __name__ == "__main__":
    unittest.main()
