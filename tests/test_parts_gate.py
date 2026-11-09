"""The parts gate (scripts/parts_gate.py) on a seeded slice: one design of each family keeps
its outcomes under four relations, and no plant on it comes back PASS. Two faults patched
in here, and never shipped, show the gate catches the classes it was built for: stops read
by triangle, which a split face breaks, and a thread hole with no wall measured, which a
thinned base slips past."""
import dataclasses
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

from petra.models.parts import engine

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module    # its dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


G = _load("parts_gate")
SEED = 1
FAMILIES = 5
"""The stream deals the families in turn, so its first 5 designs are one of each."""
ENCLOSURE, STACK = 0, 4
RELATIONS = ("turn_90", "split_edges", "far_frame", "scale_2")


class Slice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = [G.assess(SEED, i, relations=RELATIONS) for i in range(FAMILIES)]

    def test_one_design_of_each_family_passes(self):
        self.assertEqual(sorted(r["family"] for r in self.rows), sorted(G.FAMILIES))
        for row in self.rows:
            self.assertEqual(row["base"], "pass", row)

    def test_no_relation_breaks(self):
        for row in self.rows:
            self.assertEqual(row["broken"], {}, row)
            self.assertTrue(row["relations"], row)

    def test_no_plant_passes(self):
        for row in self.rows:
            self.assertEqual(row["passed"], [], row)
            self.assertTrue(row["plants"], row)


class Faults(unittest.TestCase):
    def test_stops_read_by_triangle_break_the_split_relation(self):
        def by_triangle(body, k, s, pick):
            return [pick(s * p[k] for p in t) for t in body.pts]

        with mock.patch.object(engine, "_face_extremes", by_triangle):
            row = G.assess(SEED, ENCLOSURE, relations=["split_edges"], plants=[])
        self.assertIn("split_edges", row["broken"], row)

    def test_a_thread_hole_with_no_wall_measured_lets_a_thin_base_pass(self):
        real = engine.bore

        def no_wall(*args, **kwargs):
            return dataclasses.replace(real(*args, **kwargs), out2=None)

        with mock.patch.object(engine, "bore", no_wall):
            row = G.assess(SEED, STACK, relations=[], plants=["thin_wall"])
        self.assertEqual(row["passed"], ["thin_wall"], row)


if __name__ == "__main__":
    unittest.main()
