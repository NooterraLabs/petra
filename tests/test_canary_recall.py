"""The canary-recall harness (scripts/canary_recall.py), docs/plan.md P1 items 4 and 7: a hole
planted by discharging modes changes only the verdict it should, and the searches find a
planted hole on a tiny budget. The holes here take out every mode, so they stay findable
whatever checks P1 adds."""
import importlib.util
import sys
import unittest
from pathlib import Path

from petra import models
from petra.registry import build_registry

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = build_registry()


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module    # its dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


class Holes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = _load("canary_recall")
        cls.A = cls.R.A
        cls.A._init()
        cls.canaries = {c["name"]: c for c in cls.A.canaries(REGISTRY)}

    def test_no_hole_leaves_petras_verdict(self):
        for name, row in self.canaries.items():
            with self.subTest(canary=name):
                self.assertEqual(self.A.holed_status(row), row["status"])

    def test_discharging_the_modes_that_refuse_a_canary_passes_it_and_nothing_less_does(self):
        refused = {name: row for name, row in self.canaries.items() if row["refused"]}
        self.assertTrue(refused, "some canary is refused by a mode today, such as the hanger's edge distance")
        for name, row in refused.items():
            with self.subTest(canary=name):
                self.assertEqual(self.A.holed_status(row, set(row["refused"])), "PASS")
                for mode in row["refused"]:
                    self.assertNotEqual(self.A.holed_status(row, set(row["refused"]) - {mode}), "PASS")

    def test_the_generator_finds_a_planted_hole_on_a_tiny_budget(self):
        hole = self.R.Hole("no steel checks", "shear_tab", frozenset(models.MODES), None, "given")
        (result,), _ = self.R.recall(2, 10, workers=1, kinds=("shear_tab",), given=(hole,))
        self.assertEqual(result["found_by"], "generator", result)
        row = self.A.assess(self.A.sample(2, result["index"], REGISTRY), REGISTRY)
        self.assertTrue(row["violations"])
        self.assertEqual(self.A.holed_status(row, hole.modes), "PASS")
        self.assertNotEqual(row["status"], "PASS")

    def test_the_breaker_reports_the_first_exposure_its_climb_reaches(self):
        start = self.canaries["hanger_support_side_flange_width"]
        hole = self.R.Hole("no steel checks", "hanger", frozenset(models.MODES), frozenset({start["condition"]}), "given")
        result = self.R.climb(hole, [{**start, "index": 0}], 5, seed=1)
        self.assertEqual(result["found_by"], "breaker", result)
        self.assertLessEqual(result["after"], 5)
        row = self.A.assess(self.A.Sample(0, "hanger", "breaker", (), result["text"]), REGISTRY)
        self.assertTrue(self.R.exposes(row, hole))

    def test_a_hole_reads_as_kind_modes_and_condition(self):
        hole = self.R.parse_hole("hanger:steel.edge_min+steel.clearance@steel.support_side.flange_width")
        self.assertEqual((hole.kind, hole.modes, hole.target),
                         ("hanger", frozenset({"steel.edge_min", "steel.clearance"}), frozenset({"steel.support_side.flange_width"})))
        self.assertIsNone(self.R.parse_hole("joint:bolt.tension").target)


if __name__ == "__main__":
    unittest.main()
