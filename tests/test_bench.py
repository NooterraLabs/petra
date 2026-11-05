"""The family reuse benchmark. Owner: F.

Timings vary run to run, so these tests check the counters and the report's structure:
every query lies inside its family's box, so both paths must end each claim statement in
a kernel Theorem for that statement, the reuse path must never call a solver, and the
recompute path must.

Hand check of the truss family box (examples/families/warren_truss.lola). The truss is
statically determinate (7 members, 7 free DOFs: B x y, C x, D x y, E x y), so its member
forces are statics and do not depend on E. With P_D, P_E the downward node loads, the
reaction at A is R_A = 0.75 P_D + 0.25 P_E, and the 2.5 m end diagonal (direction
(1.5, 2) / 2.5) carries N_ad = -R_A / 0.8 = -(0.9375 P_D + 0.3125 P_E). At the worst
vertex, P_D = P_E = P, that is 1.25 P of compression.
    CHS 60.3x3.2  A = pi/4 (60.3^2 - 53.9^2) = 574.03 mm2,  I = pi/64 (60.3^4 - 53.9^4) = 23.468 cm4
    Euler load over 2.5 m at E = 200 GPa (the low end of steel's 200 to 210 GPa):
        pi^2 E I / L^2 = 74.119 kN,  below A fy = 203.78 kN, so it is the compression capacity
    collapse factor at the worst vertex = 74.119 / (1.25 P):
        P = 39 kN   1.5204  (the shipped box)
        P = 39.5 kN 1.5011
        P = 39.6 kN 1.4974
        P = 40 kN   1.4824
so the strength claim's box edge is P = 74.119 / (1.5 x 1.25) = 39.53 kN per node. The
other claims hold with room at P = 39 kN: |N_ad| / A = 84.9 MPa against 235 MPa, and a
float eigen-check of K + lambda K_G (tension stiffening dropped, as the statement does)
puts global instability at a factor of about 670 against the claimed 3. The other
members at factor 1.5: the top chord carries 1.5 x 0.375 (P_D + P_E) = 43.9 kN against
its 107.0 kN Euler load (CHS 76.1x3.2 over 3 m), the bottom chord 43.9 kN of tension
against 203.8 kN, and the inner diagonals 1.5 x 0.3125 |P_D - P_E| <= 18.3 kN.

Solver calls per truss query, from the solvers' own algorithms over a box with two load
symbols, so 2^2 = 4 vertices: strength (R1) runs one HiGHS LP and one exact repair per
vertex; stress (R3) one exact field repair per vertex; stability (R2) one field repair
per vertex for the shared elastic problem, one hypercircle per member force lemma (7
members) and one exact LDL.
"""
import dataclasses
import random
import tempfile
import unittest
from pathlib import Path

from lola.bench import family as bench
from lola.lang import load_design, parse_design
from lola.library import Library, certify_family
from lola.registry import build_registry

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = build_registry()
CABLE_CLAIMS = len(("hot", "drop"))
TRUSS_CLAIMS = len(("strength", "stability", "stress"))
MEMBERS = 7
VERTICES = 2 ** len(("load_d", "load_e"))
TRUSS_BOX = "[-39 kN, 0 kN]"


def edited(family: bench.Family, old: str, new: str, root: str) -> bench.Family:
    text = family.path.read_text(encoding="utf-8")
    assert old in text, f"{family.path.name} declares {old!r} as the tests expect"
    path = Path(root) / family.path.name
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    return dataclasses.replace(family, path=path)


class CableBenchmark(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = bench.run(bench.CABLE, queries=4, seed=0)

    def test_every_query_statement_is_proved_on_both_paths(self):
        r = self.result
        self.assertEqual(r.statements, 4 * CABLE_CLAIMS, "each query has the family's two claims")
        self.assertEqual(r.reuse.counts["theorems"], r.statements, "reuse proves every statement")
        self.assertEqual(r.recompute.counts["theorems"], r.statements, "recompute proves every statement")

    def test_reuse_re_checks_leaves_without_searching(self):
        reuse, recompute, n = self.result.reuse.counts, self.result.recompute.counts, self.result.statements
        self.assertEqual(reuse.get("searches", 0), 0, "reuse runs no search")
        self.assertEqual(reuse.get("cells", 0), 0, "so it visits no cell")
        self.assertGreaterEqual(reuse["leaves"], n, "reuse re-checks at least one leaf per statement")
        self.assertGreaterEqual(recompute["cells"], n, "recompute searches at least one cell per statement")
        self.assertGreater(recompute["enclosures"], reuse["enclosures"], "the search adds enclosures reuse does not pay")

    def test_the_report_explains_the_ratio(self):
        lines = bench.render(self.result).splitlines()
        self.assertTrue(any(line.startswith("reuse ") for line in lines), "a reuse line")
        self.assertTrue(any(line.startswith("recompute ") for line in lines), "a recompute line")
        self.assertIn("enclosure counts", self.result.basis, "the cable model counts enclosures")
        self.assertIn("re-check", self.result.explanation, "the explanation names what reuse still pays for")
        self.assertIn(f"{self.result.reuse.counts['leaves']} leaves", self.result.explanation, "with the leaf count")

    def test_counters_do_not_depend_on_timing(self):
        again = bench.run(bench.CABLE, queries=4, seed=0)
        for path in ("reuse", "recompute"):
            first, second = getattr(self.result, path).counts, getattr(again, path).counts
            self.assertEqual(first, second, f"{path} counters repeat for the same seed")


class TrussBenchmark(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = bench.run(bench.TRUSS, queries=2, seed=0)

    def test_every_query_statement_is_proved_on_both_paths(self):
        r = self.result
        self.assertEqual(r.statements, 2 * TRUSS_CLAIMS, "each query has the family's three claims")
        self.assertEqual({rule: s.statements for rule, s in r.reuse.by_rule.items()}, {"R1": 2, "R2": 2, "R3": 2}, "one statement per rule per query")
        for path in (r.reuse, r.recompute):
            self.assertEqual(path.counts["theorems"], r.statements, "every statement ends in a theorem for itself")
            self.assertEqual(path.counts["kernel checks"], r.statements, "the first candidate is accepted, so one check each")
            self.assertEqual(path.counts["lemmas"], 2 * MEMBERS, "each stability check proves one force lemma per member")

    def test_reuse_avoids_exactly_the_solver_calls_recompute_makes(self):
        reuse, recompute, n = self.result.reuse.counts, self.result.recompute.counts, self.result.queries
        for counter in ("LP solves", "exact solves", "LDL factorizations", "solver hypercircles", "searches"):
            self.assertEqual(reuse.get(counter, 0), 0, f"reuse makes no {counter}")
        self.assertEqual(recompute["LP solves"], n * VERTICES, "one HiGHS LP per load vertex of the strength statement")
        self.assertEqual(recompute["exact solves"], n * 3 * VERTICES, "one exact repair per vertex for R1, R3 and R2's elastic problem")
        self.assertEqual(recompute["LDL factorizations"], n, "one exact LDL per stability statement")
        self.assertEqual(recompute["solver hypercircles"], n * MEMBERS, "one lemma hypercircle per member force")

    def test_the_truss_model_counts_solver_calls_not_enclosures(self):
        r = self.result
        self.assertEqual([u.rule for u in r.units], ["R1", "R2", "R3"], "one unit cost per rule, timed on the family statements")
        self.assertTrue(all(min(u.solve_s, u.check_s, u.offer_s, u.reuse_check_s) > 0 for u in r.units), "every unit cost was timed")
        self.assertIn("solver calls avoided", r.basis, "the prediction is solver calls against kernel checks")
        self.assertNotIn("enclosure", r.basis, "the enclosure model is the cable's")
        lines = bench.render(r).splitlines()
        self.assertTrue(lines[0].startswith("truss family"), "the block names its family")
        self.assertTrue(any(line.startswith("reuse ") for line in lines), "a reuse line")
        self.assertIn("LP solves", next(line for line in lines if line.startswith("recompute ")), "the recompute line counts LP solves")

    def test_the_split_covers_every_timed_query(self):
        n = self.result.queries
        for path in (self.result.reuse, self.result.recompute):
            slack = 1e-9 * n
            self.assertGreaterEqual(path.total_s, n * path.min_s - slack, "the split sums the timed queries, none dropped")
            self.assertLessEqual(path.total_s, n * path.max_s + slack, "and counts none twice")
            self.assertTrue(all(s.check_s > 0 and s.other_s > 0 for s in path.by_rule.values()), "each rule has time in and outside the kernel")


class TrussQueries(unittest.TestCase):
    def setUp(self):
        self.family = load_design(bench.TRUSS.path, REGISTRY)
        self.text = bench.TRUSS.path.read_text(encoding="utf-8")

    def test_queries_are_sub_boxes_with_the_family_geometry(self):
        rng = random.Random(0)
        frame = [(a.key, a.args) for a in self.family.components["frame"].attrs]
        for i in range(8):
            query = parse_design(bench.TRUSS.query(i, rng, self.family, self.text, REGISTRY), "q.lola", REGISTRY)
            self.assertFalse(query.is_family, "a query is a concrete design")
            self.assertEqual([(a.key, a.args) for a in query.components["frame"].attrs], frame, "same nodes, members, sections, steel")
            self.assertEqual([(c.name, c.qoi, c.rel, c.bound) for c in query.claims],
                             [(c.name, c.qoi, c.rel, c.bound) for c in self.family.claims], "same claims")
            for mine, theirs in zip(query.loads["crowd"].entries, self.family.loads["crowd"].entries):
                box, load = self.family.params[theirs.value.name].range.value, mine.value.range.value
                self.assertEqual(mine.target, theirs.target, "the same node carries the load")
                self.assertTrue(box.lo <= load.lo < load.hi <= box.hi, f"query {i}: {load} is a proper sub-box of {box}")

    def test_a_family_whose_params_are_not_loads_has_no_load_query(self):
        cable = load_design(bench.CABLE.path, REGISTRY)
        with self.assertRaises(ValueError):
            bench.TRUSS.query(0, random.Random(0), cable, bench.CABLE.path.read_text(encoding="utf-8"), REGISTRY)


class TrussBoxEdge(unittest.TestCase):
    def certify(self, edge_kn: str) -> tuple:
        with tempfile.TemporaryDirectory() as root:
            family = edited(bench.TRUSS, TRUSS_BOX, f"[-{edge_kn} kN, 0 kN]", root)
            return certify_family(load_design(family.path, REGISTRY), REGISTRY, Library(root)).skipped

    def test_the_shipped_box_certifies_every_claim(self):
        self.assertEqual(self.certify("39"), (), "collapse factor 1.5204 at the worst vertex, stress 84.9 MPa, instability near 670")

    def test_the_box_edge_sits_where_the_hand_check_puts_it(self):
        self.assertEqual(self.certify("39.5"), (), "1.5011 at 39.5 kN is within the claimed 1.5")
        (skipped,) = self.certify("39.6")
        self.assertIn("claim.strength", skipped, "only strength fails at 39.6 kN (1.4974 by hand)")
        self.assertIn("refuted by R1", skipped, "the solver finds a collapse mechanism")
        for at in ("load_d = -39600", "load_e = -39600", "const.steel.E = 200000000000"):
            self.assertIn(at, skipped, f"at the hand check's worst vertex: {at}")


class Refusals(unittest.TestCase):
    def test_a_family_that_does_not_certify_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            too_hot = edited(bench.CABLE, "[0 A, 13 A]", "[0 A, 16 A]", root)
            with self.assertRaises(ValueError) as caught:
                bench.run(too_hot, queries=1, seed=0)
        self.assertIn("claim.hot", str(caught.exception), "the refusal names the claim that did not certify")
        with tempfile.TemporaryDirectory() as root:
            too_heavy = edited(bench.TRUSS, TRUSS_BOX, "[-40 kN, 0 kN]", root)
            with self.assertRaises(ValueError) as caught:
                bench.run(too_heavy, queries=1, seed=0)
        self.assertIn("claim.strength", str(caught.exception), "40 kN per node gives 1.4824 by hand, below 1.5")

    def test_no_queries_is_refused(self):
        with self.assertRaises(ValueError):
            bench.run(bench.CABLE, queries=0, seed=0)


if __name__ == "__main__":
    unittest.main()
