"""The solver registry, SolverSource and the exact repair helpers. Owner: I.

Every registered rule has a solver module of the same name, and nothing else does.
"""
import pkgutil
import unittest
from fractions import Fraction
from unittest import mock

import numpy as np

import lola.solvers as solvers
from lola.kernel import (
    GOAL_RULE,
    LEMMAS,
    MODULE_OF,
    Add,
    Const,
    DefinedHyp,
    DefinedRange,
    Evidence,
    Interval,
    Leaf,
    Matrix,
    Mul,
    Neg,
    RangeHyp,
    Refutation,
    Statement,
    Sym,
    check,
)
from lola.kernel.rules.r3_hypercircle import HypercircleFields, MinimizerComponent, QuadraticProblem
from lola.kernel.rules.r4_enclosure import AllNonpositive, Enclosure, PointWitness
from lola.solvers import SolverSource, r4_enclosure
from lola.solvers.exact import project_onto_equalities, range_box, rationalize, solve_exact, to_numpy


def matrix(*rows) -> Matrix:
    entries = tuple((i, j, Fraction(v)) for i, row in enumerate(rows) for j, v in enumerate(row) if v)
    return Matrix(len(rows), len(rows[0]), entries)


def q(*values) -> tuple[Fraction, ...]:
    return tuple(Fraction(v) for v in values)


class SolverRegistry(unittest.TestCase):
    def test_one_solver_module_per_rule(self):
        on_disk = {info.name for info in pkgutil.iter_modules(solvers.__path__)}
        self.assertEqual(on_disk - solvers._HELPERS, set(MODULE_OF.values()))

    def test_every_goal_has_a_solver(self):
        self.assertEqual(set(solvers.SOLVERS), set(GOAL_RULE))
        for solve in solvers.SOLVERS.values():
            self.assertTrue(callable(solve))

    def test_every_lemma_has_a_range_solver(self):
        self.assertEqual(set(solvers.LEMMA_SOLVERS), set(LEMMAS))
        for propose in solvers.LEMMA_SOLVERS.values():
            self.assertTrue(callable(propose))


X_LE_2 = Statement((RangeHyp("x", Fraction(0), Fraction(1), "in:t.x"),), AllNonpositive((Add((Sym("x"), Neg(Const(Fraction(2))))),)))
PROOF = Evidence(Enclosure(Leaf()))
COUNTER = Evidence(PointWitness((("x", Fraction(1)),), 0))


class Source(unittest.TestCase):
    def offer(self, statement, solve, source=None):
        with mock.patch.dict(solvers.SOLVERS, {type(statement.goal): solve}):
            return list((source or SolverSource()).offer(statement, "sha256:" + "0" * 64))

    def test_the_goal_solver_candidates_pass_through_in_order(self):
        self.assertEqual(self.offer(X_LE_2, lambda s: iter((PROOF, COUNTER))), [PROOF, COUNTER])

    def test_limits_reach_a_solver_that_names_them_and_only_then(self):
        seen = {}

        def bounded(statement, max_cells):
            seen["max_cells"] = max_cells
            return (PROOF,)

        self.assertEqual(self.offer(X_LE_2, bounded, SolverSource(max_cells=7)), [PROOF])
        self.assertEqual(seen, {"max_cells": 7})
        self.assertEqual(self.offer(X_LE_2, lambda statement: (PROOF,), SolverSource(max_cells=7)), [PROOF])

    def test_a_spent_time_limit_stops_after_the_current_candidate(self):
        self.assertEqual(self.offer(X_LE_2, lambda s: iter((PROOF, COUNTER)), SolverSource(time_limit_s=0)), [PROOF])


class DefinedHyps(unittest.TestCase):
    """n is the minimiser of s^2 subject to s = f, scaled by 1, so n = f; w is its weight.
    The goal n - 5 <= 0 reads only n, so f and w are hypotheses only of the definition."""

    PROBLEM = QuadraticProblem(matrix((1,)), (Sym("f"),), (Sym("w"),))
    N = DefinedHyp("n", MinimizerComponent(PROBLEM, 0, Const(Fraction(1))))
    STATEMENT = Statement(
        (RangeHyp("f", Fraction(1), Fraction(3), "in:t.f"), N, RangeHyp("w", Fraction(1), Fraction(2), "in:t.w")),
        AllNonpositive((Add((Sym("n"), Neg(Const(Fraction(5))))),)),
    )
    RANGE = DefinedRange("n", Fraction(1), Fraction(3), HypercircleFields((), ()))
    AT_POINT = DefinedRange("n", Fraction(3), Fraction(3), HypercircleFields((), ()))

    def setUp(self):
        self.seen = []
        self.boxes = []

        def solve(statement):
            self.seen.append(statement)
            return (PROOF, Evidence(PointWitness((("n", Fraction(3)),), 0)))

        self.enterContext(mock.patch.dict(solvers.SOLVERS, {AllNonpositive: solve}))

    def offer(self, *ranges):
        def propose(statement, box=None):
            self.boxes.append(box)
            return ranges if box is None else (self.AT_POINT,)

        with mock.patch.dict(solvers.LEMMA_SOLVERS, {MinimizerComponent: propose}):
            return list(SolverSource().offer(self.STATEMENT, "sha256:" + "0" * 64))

    def test_the_goal_is_solved_over_the_proposed_range_and_the_range_goes_with_it(self):
        self.assertEqual(self.offer(self.RANGE), [Evidence(PROOF.body, (self.RANGE,))], "the refutation over n is dropped")
        (solved,) = self.seen
        self.assertEqual(solved, Statement((RangeHyp("n", Fraction(1), Fraction(3), "lemma:n"),), self.STATEMENT.goal))
        self.assertEqual(self.boxes, [None])

    def test_a_refutation_at_a_point_of_the_statement_gets_the_ranges_proved_there(self):
        full = PointWitness((("f", Fraction(3)), ("w", Fraction(1))), 0)

        def refute(statement, original):
            self.seen.append(original)
            return (Evidence(PointWitness((("n", Fraction(3)),), 0)), Evidence(PointWitness((("f", Fraction(3)),), 0)), Evidence(full))

        with mock.patch.dict(solvers.SOLVERS, {AllNonpositive: refute}):
            self.assertEqual(self.offer(self.RANGE), [Evidence(full, (self.AT_POINT,))], "a point over n, or missing w, is dropped")
        self.assertEqual(self.seen, [self.STATEMENT], "a solver that names original sees the statement as written")
        self.assertEqual(self.boxes, [None, {"f": Interval(Fraction(3), Fraction(3)), "w": Interval(Fraction(1), Fraction(1))}])

    def test_a_definition_without_a_proposed_range_is_an_error_not_a_guess(self):
        with self.assertRaises(ValueError):
            self.offer()
        self.assertEqual(self.seen, [])


class Witnesses(unittest.TestCase):
    """The real solvers on q = s*_0 of min s_0^2 + 3 s_1^2 subject to s_0 + s_1 = F, for F
    in [4, 8], where s*_0 = 3F/4. Over q's proposed range [3, 6] alone, q and F vary
    independently, so a goal can fail there and still hold at every true value of q."""

    PROBLEM = QuadraticProblem(matrix((1, 1)), (Sym("F"),), (Const(Fraction(1)), Const(Fraction(3))))

    def results(self, *terms):
        q = DefinedHyp("q", MinimizerComponent(self.PROBLEM, 0, Const(Fraction(1))))
        statement = Statement((RangeHyp("F", Fraction(4), Fraction(8), "in:t.F"), q), AllNonpositive((Add((Sym("q"), *terms)),)))
        return [check(statement, evidence) for evidence in SolverSource().offer(statement, "sha256:" + "0" * 64)]

    def test_a_bound_q_passes_is_refuted_where_q_peaks(self):
        refuted = [r for r in self.results(Neg(Const(Fraction(5)))) if isinstance(r, Refutation)]
        self.assertEqual([r.point for r in refuted], [(("F", Fraction(8)),)], "q - 5 > 0 for F > 20/3, most at F = 8")

    def test_a_bound_that_fails_only_over_the_range_is_not_refuted(self):
        results = self.results(Mul((Const(Fraction(-3, 4)), Sym("F"))), Neg(Const(Fraction(1, 10))))
        self.assertFalse([r for r in results if isinstance(r, Refutation)], "q - 3F/4 - 1/10 is -1/10 at every F, but 29/10 at q = 6, F = 4")


class SearchStats(unittest.TestCase):
    """r4_enclosure.search_stats describes the last search call alone, so a caller can
    attribute the counters to the call it timed."""

    BOX = {"x": Interval(Fraction(0), Fraction(1))}
    NEEDS_SPLITS = (Add((Mul((Sym("x"), Sym("x"))), Neg(Sym("x")), Const(Fraction(-1, 10)))),)
    HOLDS_AT_THE_ROOT = (Add((Sym("x"), Const(Fraction(-2)))),)

    def test_each_search_reports_its_own_counters(self):
        r4_enclosure.search(self.NEEDS_SPLITS, dict(self.BOX), 20000)
        first = r4_enclosure.search_stats()
        self.assertGreater(first["cells"], 1, "x^2 - x - 1/10 encloses to [-11/10, 9/10] on [0, 1], so the root splits")
        r4_enclosure.search(self.HOLDS_AT_THE_ROOT, dict(self.BOX), 20000)
        self.assertEqual(r4_enclosure.search_stats(), {"cells": 1, "enclosures": 1, "max_depth": 0}, "x - 2 encloses to [-2, -1] at the root")
        r4_enclosure.search(self.NEEDS_SPLITS, dict(self.BOX), 20000)
        self.assertEqual(r4_enclosure.search_stats(), first, "the same search counts the same again")

    def test_the_witness_ascent_after_a_search_is_not_counted(self):
        q = DefinedHyp("q", MinimizerComponent(Witnesses.PROBLEM, 0, Const(Fraction(1))))
        goal = AllNonpositive((Add((Sym("q"), Neg(Const(Fraction(5))))),))
        load = RangeHyp("F", Fraction(4), Fraction(8), "in:t.F")
        over_range = Statement((load, RangeHyp("q", Fraction(3), Fraction(6), "lemma:q")), goal)
        (witness,) = r4_enclosure.solve(over_range, original=Statement((load, q), goal))
        self.assertIsInstance(witness.body, PointWitness, "q - 5 > 0 at F = 8, where q = 6")
        after_solve = r4_enclosure.search_stats()
        r4_enclosure.search(goal.exprs, {"F": Interval(Fraction(4), Fraction(8)), "q": Interval(Fraction(3), Fraction(6))}, 20000)
        self.assertEqual(after_solve, r4_enclosure.search_stats(), "the counters are the search's, not the ascent's after it")


class SolveExact(unittest.TestCase):
    def test_a_square_nonsingular_system_gets_its_one_solution(self):
        self.assertEqual(solve_exact(matrix((2, 1), (1, 3)), q(3, 5)), q("4/5", "7/5"))

    def test_an_underdetermined_system_gets_the_basic_solution(self):
        self.assertEqual(solve_exact(matrix((1, 2, 3)), q(6)), q(6, 0, 0))

    def test_a_consistent_dependent_system_is_solved(self):
        self.assertEqual(solve_exact(matrix((1, 1), (2, 2)), q(1, 2)), q(1, 0))

    def test_an_inconsistent_system_has_no_solution(self):
        self.assertIsNone(solve_exact(matrix((1, 1), (2, 2)), q(1, 3)))

    def test_a_right_hand_side_of_the_wrong_length_is_refused(self):
        with self.assertRaises(ValueError):
            solve_exact(matrix((1, 0), (0, 1)), q(1))


class Repair(unittest.TestCase):
    def test_the_residual_moves_onto_the_basic_entries_only(self):
        repaired = project_onto_equalities(matrix((1, 1, 1)), q(1), q("1/3", "1/3", "1/4"), (2,))
        self.assertEqual(repaired, q("1/3", "1/3", "1/3"))

    def test_an_exact_point_is_returned_unchanged(self):
        self.assertEqual(project_onto_equalities(matrix((1, 0), (0, 1)), q(1, 1), q(1, 1), (0,)), q(1, 1))

    def test_a_basis_that_cannot_absorb_the_residual_is_an_error(self):
        with self.assertRaises(ValueError):
            project_onto_equalities(matrix((1, 0), (0, 1)), q(1, 1), q(0, 0), (0,))

    def test_rationalize_rounds_each_float_to_a_nearby_rational(self):
        self.assertEqual(rationalize(np.array([[0.25], [1 / 3]])), q("1/4", "1/3"))
        self.assertEqual(rationalize([0.1], max_den=10), q("1/10"))

    def test_to_numpy_places_every_entry_and_zeros_elsewhere(self):
        self.assertEqual(to_numpy(matrix((0, "1/2"), (3, 0))).tolist(), [[0.0, 0.5], [3.0, 0.0]])

    def test_range_box_reads_only_range_hypotheses(self):
        self.assertEqual(range_box(DefinedHyps.STATEMENT), {"f": q(1, 3), "w": q(1, 2)})


if __name__ == "__main__":
    unittest.main()
