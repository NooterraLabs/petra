"""The family reuse benchmark. Owner: F.

Timings vary run to run, so these tests check the counters and the report's structure:
every query lies inside the family box, so both paths must end each claim statement in
a kernel Theorem, the reuse path must never search, and the recompute path must.
"""
import tempfile
import unittest
from pathlib import Path

from lola.bench import family as bench

ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / "examples" / "families" / "cu_pvc_clipped.lola"
CLAIMS = len(("hot", "drop"))


class Benchmark(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = bench.run(str(FAMILY), queries=4, seed=0)

    def test_every_query_statement_is_proved_on_both_paths(self):
        r = self.result
        self.assertEqual(r.statements, 4 * CLAIMS, "each query has the family's two claims")
        self.assertEqual(r.reuse.theorems, r.statements, "reuse proves every statement")
        self.assertEqual(r.recompute.theorems, r.statements, "recompute proves every statement")

    def test_reuse_re_checks_leaves_without_searching(self):
        r = self.result
        self.assertEqual(r.reuse.solver_cells, 0, "reuse runs no search")
        self.assertGreaterEqual(r.reuse.leaves_checked, r.statements, "reuse re-checks at least one leaf per statement")
        self.assertGreaterEqual(r.recompute.solver_cells, r.statements, "recompute searches at least one cell per statement")
        self.assertGreater(r.recompute.kernel_enclosures, r.reuse.kernel_enclosures, "the search adds enclosures reuse does not pay")

    def test_the_report_explains_the_ratio(self):
        lines = bench.render(self.result).splitlines()
        self.assertTrue(any(line.startswith("reuse ") for line in lines), "a reuse line")
        self.assertTrue(any(line.startswith("recompute ") for line in lines), "a recompute line")
        self.assertIn("re-check", self.result.explanation, "the explanation names what reuse still pays for")
        self.assertIn(f"{self.result.reuse.leaves_checked} leaves", self.result.explanation, "with the leaf count")

    def test_counters_do_not_depend_on_timing(self):
        again = bench.run(str(FAMILY), queries=4, seed=0)
        for path in ("reuse", "recompute"):
            first, second = getattr(self.result, path), getattr(again, path)
            self.assertEqual((first.kernel_enclosures, first.solver_cells, first.leaves_checked),
                             (second.kernel_enclosures, second.solver_cells, second.leaves_checked), f"{path} counters repeat for the same seed")


class Refusals(unittest.TestCase):
    def test_a_family_that_does_not_certify_is_refused(self):
        text = FAMILY.read_text(encoding="utf-8").replace("[0 A, 13 A]", "[0 A, 16 A]")
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "too_hot.lola"
            path.write_text(text, encoding="utf-8", newline="\n")
            with self.assertRaises(ValueError) as caught:
                bench.run(str(path), queries=1, seed=0)
        self.assertIn("claim.hot", str(caught.exception), "the refusal names the claim that did not certify")

    def test_no_queries_is_refused(self):
        with self.assertRaises(ValueError):
            bench.run(str(FAMILY), queries=0, seed=0)


if __name__ == "__main__":
    unittest.main()
