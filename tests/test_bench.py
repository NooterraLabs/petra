"""The family reuse benchmark. Owner: F.

Timings vary run to run, so these tests check the counters and the report's structure:
every query lies inside its family's box, so both paths must end each claim statement in
a kernel Theorem for that statement. The reuse path checks an Instance of the family
theorem, which the kernel has memoised, so it never calls a solver and runs no rule; the
recompute path does both. The first query of a process pays the family checks.

Hand check of the truss family box (examples/families/warren_truss.petra). The truss is
statically determinate (7 members, 7 free DOFs: B x y, C x, D x y, E x y), so its member
forces are statics and do not depend on E. With P_D, P_E the downward node loads, the
reaction at A is R_A = 0.75 P_D + 0.25 P_E, and the 2.5 m end diagonal (direction
(1.5, 2) / 2.5) carries N_ad = -R_A / 0.8 = -(0.9375 P_D + 0.3125 P_E). At the worst
vertex, P_D = P_E = P, that is 1.25 P of compression.
    CHS 60.3x3.2  A = pi/4 (60.3^2 - 53.9^2) = 574.03 mm2,  I = pi/64 (60.3^4 - 53.9^4) = 23.468 cm4
    over 2.5 m at E = 200 GPa (the low end of steel's 200 to 210 GPa, where capacity is least):
        N_cr = pi^2 E I / L^2 = 74.119 kN,  A fy = 203.78 kN
    EN 1993-1-1 6.3.1.2, curve c (alpha = 0.49):
        lambda = sqrt(203.78 / 74.119) = 1.6581,  Phi = (1 + 0.49 (1.6581 - 0.2) + 1.6581^2) / 2 = 2.2319
        chi = 1 / (Phi + sqrt(Phi^2 - lambda^2)) = 0.2684,  N_b = chi A fy = 54.692 kN,
        the compression capacity
    the members' own weight at g = 9.84 m/s2 (the top of the registry's range) and 7850 kg/m3:
        44.3 N/m for CHS 60.3x3.2 and 56.6 N/m for CHS 76.1x3.2, so 0.196 kN at D and E
        and 0.244 kN at B; N_ad gains 1.25 x 0.196 + 0.625 x 0.244 = 0.397 kN, and 0.044 kN
        more at its lower end, the axial share of its own weight (44.3 N/m x 2 m rise / 2)
    the strength claim factors the load and not the weight, so the collapse factor at the
    worst vertex is (54.692 - 0.441) / (1.25 P):
        P = 28.5 kN 1.5228  (the shipped box)
        P = 28.8 kN 1.5070
        P = 29 kN   1.4966
        P = 40 kN   1.0850
so the strength claim's box edge is P = 54.251 / (1.5 x 1.25) = 28.93 kN per node. Without
the weight it was 29.17 kN, and the bare Euler load, which v0 used before the buckling
curve, put it at 39.53 kN. The other claims hold with room at P = 28.5 kN: the stress
claim reads (|N_ad| + 0.441 kN + 1.533 kN) / A = 65.5 MPa against 235 MPa, the 1.533 kN
being the bending the diagonal's weight causes at midspan (EN 1993-1-1 6.2.1(7)), and a
float eigen-check of K + lambda K_G (tension stiffening dropped, as the statement does)
puts global instability far above the claimed 3. The other members at factor 1.5: the
top chord carries 1.5 x 0.375 (P_D + P_E) = 32.1 kN against its 77.0 kN buckling
resistance (CHS 76.1x3.2 over 3 m), the bottom chord 32.1 kN of tension against
203.8 kN, and the inner diagonals 1.5 x 0.3125 |P_D - P_E| <= 13.4 kN, each with well
under 1 kN from the weight. Every member stays below yield and far inside the 0.002
strain limit, and both sections are class 1 (D / t = 18.8 and 23.8 against
90 x 235 / 355 = 59.6), so each validity row holds.

Solver calls per truss query, from the solvers' own algorithms over a box with two load
symbols, so 2^2 = 4 vertices. Strength (R1) runs one HiGHS LP and one exact repair per
vertex. Stability (R2) and stress (R4) each read member force lemmas from four elastic
problems: the load case, with one exact field repair per vertex, and a unit downward load
at each of the three free y DOFs (B, D, E), which the weight loads, with one exact repair
each. Each problem has one hypercircle, which every lemma on it reads: stability proves
7 x 4 lemmas and stress 1 x 4, for diag_ad alone. Stability runs one exact LDL and stress
one R4 search.
"""
import dataclasses
import random
import tempfile
import unittest
from pathlib import Path

from petra.bench import family as bench
from petra.lang import load_design, parse_design
from petra.library import Library, certify_family
from petra.registry import build_registry

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = build_registry()
CABLE_CLAIMS = len(("hot", "drop"))
TRUSS_CLAIMS = len(("strength", "stability", "stress"))
MEMBERS = 7
VERTICES = 2 ** len(("load_d", "load_e"))
UNIT_LOADS = len(("B", "D", "E"))
PROBLEMS = 1 + UNIT_LOADS
TRUSS_BOX = "[-28.5 kN, 0 kN]"


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

    def test_reuse_checks_an_instance_without_searching_or_running_a_rule(self):
        reuse, recompute, n = self.result.reuse.counts, self.result.recompute.counts, self.result.statements
        self.assertEqual(reuse["instances"], n, "reuse answers every statement with an Instance")
        for counter in ("searches", "cells", "leaves", "kernel enclosures"):
            self.assertEqual(reuse.get(counter, 0), 0, f"reuse has no {counter}: the family theorem is memoised")
        self.assertEqual(recompute.get("instances", 0), 0, "recompute never offers an Instance")
        self.assertGreaterEqual(recompute["cells"], n, "recompute searches at least one cell per statement")
        self.assertGreater(recompute["kernel enclosures"], 0, "and the kernel re-evaluates its partition")

    def test_the_first_query_pays_the_family_checks(self):
        first = self.result.first
        self.assertEqual(len(first.runs), bench.FIRST_REPS, "the first query is timed FIRST_REPS times")
        self.assertEqual(first.statements, bench.FIRST_REPS * CABLE_CLAIMS, "each run has the query's two claims")
        self.assertEqual(first.theorems, first.statements, "every run proves every statement")
        self.assertGreater(first.kernel_enclosures, 0, "each run checks the family theorems, which runs their rule")

    def test_the_report_explains_the_ratio(self):
        lines = bench.render(self.result).splitlines()
        for name in ("reuse ", "recompute ", "first ", "predicted ", "measured "):
            self.assertTrue(any(line.startswith(name) for line in lines), f"a {name.strip()} line")
        self.assertIn("linear in statement size", self.result.basis, "the model charges the Instance check by size")
        self.assertIn("Instance", self.result.explanation, "the explanation names what reuse pays for")
        self.assertIn("first query", self.result.explanation, "and what the first query pays besides")

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
        self.assertEqual({rule: s.statements for rule, s in r.reuse.by_rule.items()}, {"R1": 2, "R2": 2, "R4": 2}, "one statement per rule per query")
        for path in (r.reuse, r.recompute):
            self.assertEqual(path.counts["theorems"], r.statements, "every statement ends in a theorem for itself")
            self.assertEqual(path.counts["kernel checks"], r.statements, "the first candidate is accepted, so one check each")
        self.assertEqual(r.recompute.counts["lemmas"], 2 * (MEMBERS + 1) * PROBLEMS, "stability reads every member, stress one, on each elastic problem")
        self.assertEqual(r.reuse.counts.get("lemmas", 0), 0, "an Instance proves no lemma: the family theorem holds the ranges")
        self.assertEqual(r.reuse.counts["instances"], r.statements, "reuse answers every statement with an Instance")

    def test_reuse_avoids_exactly_the_solver_calls_recompute_makes(self):
        reuse, recompute, n = self.result.reuse.counts, self.result.recompute.counts, self.result.queries
        for counter in ("LP solves", "exact solves", "LDL factorizations", "solver hypercircles", "searches", "kernel enclosures"):
            self.assertEqual(reuse.get(counter, 0), 0, f"reuse makes no {counter}")
        self.assertEqual(recompute["LP solves"], n * VERTICES, "one HiGHS LP per load vertex of the strength statement")
        self.assertEqual(recompute["exact solves"], n * (3 * VERTICES + 2 * UNIT_LOADS), "one exact repair per vertex for R1 and each load problem, one per unit problem")
        self.assertEqual(recompute["LDL factorizations"], n, "one exact LDL per stability statement")
        self.assertEqual(recompute["solver hypercircles"], n * 2 * PROBLEMS, "one hypercircle per elastic problem of the stability and stress statements")
        self.assertGreater(recompute["kernel enclosures"], 0, "the kernel replays each proof")

    def test_the_model_charges_the_instance_check_by_statement_size(self):
        r = self.result
        self.assertEqual([u.rule for u in r.units], ["R1", "R2", "R4"], "one unit cost per rule, timed on the first warm-up query")
        self.assertTrue(all(min(u.solve_s, u.check_s, u.offer_s, u.instance_s) > 0 for u in r.units), "every unit cost was timed")
        self.assertTrue(all(u.nodes > 0 and u.per_node_s > 0 for u in r.units), "the Instance check has a cost per node")
        self.assertIn("linear in statement size", r.basis, "the prediction charges the Instance check by size")
        lines = bench.render(r).splitlines()
        self.assertTrue(lines[0].startswith("truss family"), "the block names its family")
        self.assertIn("instances", next(line for line in lines if line.startswith("reuse ")), "the reuse line counts Instances")
        self.assertIn("LP solves", next(line for line in lines if line.startswith("recompute ")), "the recompute line counts LP solves")
        self.assertEqual(r.first.theorems, r.first.statements, "the first query proves every statement in every run")

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
            query = parse_design(bench.TRUSS.query(i, rng, self.family, self.text, REGISTRY), "q.petra", REGISTRY)
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
        self.assertEqual(self.certify("28.5"), (), "collapse factor 1.5228 at the worst vertex, stress 65.5 MPa")

    def test_the_box_edge_sits_where_the_hand_check_puts_it(self):
        self.assertEqual(self.certify("28.8"), (), "1.5070 at 28.8 kN is within the claimed 1.5")
        (skipped,) = self.certify("29")
        self.assertIn("claim.strength", skipped, "only strength fails at 29 kN (1.4966 by hand)")
        self.assertIn("refuted by R1", skipped, "the solver finds a collapse mechanism")
        for at in ("load_d = -29000", "load_e = -29000", "const.steel.E = 200000000000", "const.earth.gravity = 246/25"):
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
        self.assertIn("claim.strength", str(caught.exception), "40 kN per node gives 1.0850 by hand, below 1.5")

    def test_no_queries_is_refused(self):
        with self.assertRaises(ValueError):
            bench.run(bench.CABLE, queries=0, seed=0)


if __name__ == "__main__":
    unittest.main()
