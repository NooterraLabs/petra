"""The repair-and-minimise loop (petra/loop.py): tasks keep their job, the loop repairs a
failing draft to PASS by petra.check's own repair moves, and the minimiser keeps only
designs the checker passes.

Tasks come from the development seed, DEV, never the held-out one.
"""
import json
import unittest
from pathlib import Path

import petra
from petra import loop
from petra.registry import build_registry

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = build_registry()
DEV = 101


class Tasks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = list(loop.tasks(DEV, 10, REGISTRY))

    def test_tasks_are_drawn_the_same_way_every_time(self):
        again = list(loop.tasks(DEV, 10, REGISTRY))
        self.assertEqual([(t.id, t.kind, t.given, t.loads) for t in again], [(t.id, t.kind, t.given, t.loads) for t in self.tasks])

    def test_the_draft_and_the_reference_keep_the_job(self):
        for task in self.tasks:
            with self.subTest(task.id):
                self.assertIn(task.kind, loop.TASK_KINDS)
                self.assertEqual(task.faithful(task.draft(), REGISTRY), [])
                self.assertEqual(task.faithful(task.reference, REGISTRY), [])

    def test_the_reference_passes_so_the_job_can_be_done(self):
        for task in self.tasks[:3]:
            with self.subTest(task.id):
                self.assertEqual(petra.check(task.reference, repair=False)["status"], "PASS")

    def test_a_design_that_changes_the_job_is_named(self):
        task = self.tasks[0]
        top = task.draft()
        load = loop._kip(task.loads[0][1])
        self.assertTrue(task.faithful(top.replace(f"{load} kip]", "1 kip]"), REGISTRY), "a lowered load")
        beam = next(g for g in task.given if g.startswith("beam"))
        self.assertTrue(task.faithful(top.replace(beam, beam.replace("W21x44", "W21x62")), REGISTRY), "another beam")
        waived = top + '\nwaive steel.weld on st1 by "x" reason "y"\n'
        self.assertIn("the design waives a requirement", task.faithful(waived, REGISTRY))

    def test_the_brief_names_the_kind_the_members_and_the_loads(self):
        brief = self.tasks[0].brief()
        for text in ("shear_tab", "W21x44", "W12x65 flange", "16.294 kip"):
            self.assertIn(text, brief)


class Solve(unittest.TestCase):
    """Task 101-005 is a stiffened seat whose draft FAILs: its 1/2 in stiffener is too thin."""

    @classmethod
    def setUpClass(cls):
        cls.task = next(t for t in loop.tasks(DEV, 5, REGISTRY) if t.id == "101-005")
        cls.judged = []
        cls.solved = loop.solve(cls.task, REGISTRY, judge=lambda text: cls.judged.append(text) or [])

    def test_the_draft_fails_and_the_loop_reaches_pass_within_the_budget(self):
        self.assertEqual(self.solved.attempts[0].status, "FAIL")
        self.assertIsNotNone(self.solved.attempts[0].move, "the loop took a move from the repair")
        self.assertIsNotNone(self.solved.checks_to_pass)
        self.assertLessEqual(self.solved.checks_to_pass, 10)
        self.assertEqual(petra.check(self.solved.passed, repair=False)["status"], "PASS")

    def test_the_optimum_passes_keeps_the_job_and_weighs_less(self):
        self.assertEqual(petra.check(self.solved.optimum, repair=False)["status"], "PASS")
        self.assertEqual(self.task.faithful(self.solved.optimum, REGISTRY), [])
        self.assertLess(self.solved.mass_optimum, self.solved.mass_passed)
        self.assertAlmostEqual(self.solved.mass_optimum, loop.mass(self.solved.optimum, REGISTRY))

    def test_the_judge_reads_every_design_the_loop_keeps(self):
        self.assertEqual(len(self.judged), 1 + self.solved.kept)
        self.assertEqual((self.judged[0], self.judged[-1]), (self.solved.passed, self.solved.optimum))

    def test_the_run_is_plain_json(self):
        body = self.solved.to_json()
        self.assertEqual(json.loads(json.dumps(body)), body)


class Fixed(unittest.TestCase):
    def test_the_loop_never_edits_a_line_the_job_fixes(self):
        """Task 101-011 is a bolted bracket loaded 12 in out. A shorter eccentricity would be
        lighter, but it is the job's, so the optimum keeps it."""
        task = next(t for t in loop.tasks(DEV, 11, REGISTRY) if t.id == "101-011")
        self.assertIn("eccentricity 12 inch", task.given)
        solved = loop.solve(task, REGISTRY)
        self.assertLess(solved.mass_optimum, solved.mass_passed)
        self.assertIn("  eccentricity 12 inch\n", solved.optimum)
        self.assertEqual(task.faithful(solved.optimum, REGISTRY), [])


class Mass(unittest.TestCase):
    def test_a_thicker_plate_and_more_rows_weigh_more(self):
        text = (ROOT / "examples" / "steel" / "shear_tab.petra").read_text(encoding="utf-8")
        base = loop.mass(text, REGISTRY)
        self.assertGreater(loop.mass(text.replace("thickness 0.375 inch", "thickness 0.5 inch"), REGISTRY), base)
        self.assertGreater(loop.mass(text.replace("rows 4", "rows 5"), REGISTRY), base)

    def test_every_kind_has_an_estimate(self):
        for kind in loop.TASK_KINDS:
            with self.subTest(kind):
                self.assertGreater(loop.mass((ROOT / "examples" / "steel" / f"{kind}.petra").read_text(encoding="utf-8"), REGISTRY), 0)


if __name__ == "__main__":
    unittest.main()
