"""kernel.check: well-formedness, dispatch, lemma plumbing and issued results. Owner: K.

Statements here use R4, the simplest goal, so each test isolates check's own behaviour.
The lemma success path needs R3 and is tested in test_rules.
"""
import unittest
from fractions import Fraction as F

from lola import kernel
from lola.kernel import (
    Add,
    Const,
    DefinedHyp,
    DefinedRange,
    Evidence,
    Invalid,
    Leaf,
    Matrix,
    Neg,
    RangeHyp,
    Refutation,
    Rejection,
    Split,
    Statement,
    Sym,
    Theorem,
    TooWeak,
    check,
    is_issued,
)
from lola.kernel.rules.r1_linear import FeasiblePoints
from lola.kernel.rules.r3_hypercircle import HypercircleFields, MinimizerComponent, QuadraticProblem
from lola.kernel.rules.r4_enclosure import AllNonpositive, Enclosure, PointWitness
from lola.kernel.rules.r5_moment import MomentBound, MomentConstraint, MomentDual, RandomVar

LABEL = "in:d.lift.force"
LEAF = Evidence(body=Enclosure(partition=Leaf()))


def c(v) -> Const:
    return Const(F(v))


def below(limit, lo=0, hi=10, sym="f") -> Statement:
    """sym - limit <= 0 for sym in [lo, hi]."""
    return Statement(hyps=(RangeHyp(sym, F(lo), F(hi), LABEL),), goal=AllNonpositive(exprs=(Add((Sym(sym), Neg(c(limit)))),)))


def witness(*point, which=0) -> Evidence:
    return Evidence(body=PointWitness(point=tuple((s, F(v)) for s, v in point), which=which))


PROBLEM = QuadraticProblem(B=Matrix(1, 2, ((0, 0, F(1)), (0, 1, F(1)))), f=(Sym("f"),), w=(c(1), c(3)))
FIELDS = HypercircleFields(s=((F(0), F(0)), (F(15, 2), F(5, 2))), u=((F(0),), (F(15, 2),)))
WITH_LEMMA = Statement(
    hyps=(RangeHyp("f", F(0), F(10), LABEL), DefinedHyp("q", MinimizerComponent(PROBLEM, 0, c(1)))),
    goal=AllNonpositive(exprs=(Add((Sym("q"), Neg(c(8)))),)),
)


class IssuedResults(unittest.TestCase):
    def test_a_theorem_records_what_it_rests_on(self):
        result = check(below(20), LEAF)
        self.assertIsInstance(result, Theorem)
        self.assertTrue(is_issued(result))
        self.assertEqual(result.rule, "R4")
        self.assertEqual(result.labels, frozenset({LABEL}))
        self.assertEqual(result.statement, below(20))
        self.assertEqual(result.statement_hash, kernel.statement_hash(below(20)))
        self.assertEqual(result.evidence_hash, kernel.evidence_hash(LEAF))
        self.assertEqual(result.defined_ranges, ())

    def test_a_refutation_records_its_point(self):
        result = check(below(5), witness(("f", 10)))
        self.assertIsInstance(result, Refutation)
        self.assertTrue(is_issued(result))
        self.assertEqual((result.rule, result.point, result.labels), ("R4", (("f", F(10)),), frozenset({LABEL})))

    def test_a_false_claim_gets_no_theorem(self):
        result = check(below(5), LEAF)
        self.assertIsInstance(result, Rejection)
        self.assertIsInstance(result.fault, TooWeak)
        self.assertEqual((result.rule, result.statement_hash), ("R4", kernel.statement_hash(below(5))))

    def test_a_true_claim_gets_no_refutation(self):
        result = check(below(20), witness(("f", 10)))
        self.assertIsInstance(result, Rejection)
        self.assertIsInstance(result.fault, TooWeak)


class WellFormedness(unittest.TestCase):
    def assertIllFormed(self, statement, evidence=LEAF):
        result = check(statement, evidence)
        self.assertIsInstance(result, Rejection)
        self.assertIsInstance(result.fault, Invalid)
        self.assertIsNone(result.rule)
        return result

    def test_hypotheses_sorted_without_duplicates(self):
        two = lambda hyps: Statement(hyps=hyps, goal=AllNonpositive(exprs=(Add((Sym("a"), Sym("b"), Neg(c(1)))),)))
        a, b = RangeHyp("a", F(0), F(0), "in:a"), RangeHyp("b", F(0), F(0), "in:b")
        self.assertIsInstance(check(two((a, b)), LEAF), Theorem)
        self.assertIllFormed(two((b, a)))
        self.assertIllFormed(two((a, a, b)))

    def test_every_hypothesis_is_used(self):
        st = below(20)
        unused = Statement(hyps=st.hyps + (RangeHyp("g", F(0), F(1), "in:g"),), goal=st.goal)
        self.assertIn("unused", self.assertIllFormed(unused).reason)

    def test_every_symbol_is_declared(self):
        st = below(20)
        self.assertIllFormed(Statement(hyps=st.hyps, goal=AllNonpositive(exprs=(Add((Sym("f"), Sym("g"))),))))

    def test_ranges_are_ordered(self):
        self.assertIllFormed(below(20, lo=10, hi=0))

    def test_numbers_are_exact_fractions(self):
        st = below(20)
        self.assertEqual(check(Statement(hyps=st.hyps, goal=AllNonpositive(exprs=(Add((Sym("f"), Const(-20.0))),))), LEAF).statement_hash, "")
        self.assertIllFormed(Statement(hyps=(RangeHyp("f", 0, 10, LABEL),), goal=st.goal))

    def test_goal_is_a_registered_goal(self):
        self.assertIllFormed(Statement(hyps=(), goal=c(1)))
        self.assertIllFormed(None)

    def test_definitions_mention_range_symbols_only(self):
        chained = QuadraticProblem(B=PROBLEM.B, f=(Sym("q"),), w=PROBLEM.w)
        st = Statement(
            hyps=(RangeHyp("f", F(0), F(10), LABEL), DefinedHyp("q", MinimizerComponent(PROBLEM, 0, c(1))), DefinedHyp("r", MinimizerComponent(chained, 0, c(1)))),
            goal=AllNonpositive(exprs=(Add((Sym("q"), Sym("r"))),)),
        )
        self.assertIllFormed(st)

    def test_a_goal_may_not_bind_a_hypothesis_symbol(self):
        goal = MomentBound(random=(RandomVar("f", c(0), c(1)),), moments=(MomentConstraint(Sym("f"), Sym("m"), Sym("m")),), fail=Sym("f"), p=F(1, 2))
        st = Statement(hyps=(RangeHyp("f", F(0), F(1), "in:f"), RangeHyp("m", F(0), F(0), "in:m")), goal=goal)
        self.assertIllFormed(st, Evidence(body=MomentDual(y0=F(0), y=(F(1),), partition=Leaf())))


class Dispatch(unittest.TestCase):
    def assertInvalid(self, statement, evidence, rule="R4"):
        result = check(statement, evidence)
        self.assertIsInstance(result, Rejection)
        self.assertIsInstance(result.fault, Invalid)
        self.assertEqual(result.rule, rule)
        return result

    def test_evidence_for_another_rule(self):
        self.assertIn("not evidence for R4", self.assertInvalid(below(20), Evidence(body=FeasiblePoints(x=()))).reason)

    def test_malformed_evidence_never_raises(self):
        for evidence in [None, Evidence(body=Leaf()), Evidence(body=Enclosure(partition=Split("f", 5.0, Leaf(), Leaf()))), Evidence(body=Enclosure(partition=Leaf()), defined=[])]:
            self.assertInvalid(below(20), evidence)

    def test_split_points_stay_inside_their_cells(self):
        self.assertIsInstance(check(below(20), Evidence(body=Enclosure(partition=Split("f", F(5), Leaf(), Leaf())))), Theorem)
        for split in [Split("f", F(0), Leaf(), Leaf()), Split("f", F(11), Leaf(), Leaf()), Split("g", F(1), Leaf(), Leaf())]:
            self.assertInvalid(below(20), Evidence(body=Enclosure(partition=split)))

    def test_refutation_point_must_be_a_point_of_the_box(self):
        self.assertIsInstance(check(below(5), witness(("f", 10))), Refutation)
        for evidence in [witness(("f", 11)), witness(), witness(("f", 10), ("g", 1)), witness(("f", 10), which=1)]:
            self.assertInvalid(below(5), evidence)

    def test_refutation_needs_a_statement_without_defined_hyps(self):
        lemma = DefinedRange("q", F(0), F(15, 2), FIELDS)
        self.assertInvalid(WITH_LEMMA, Evidence(body=PointWitness(point=(("f", F(10)),), which=0), defined=(lemma,)))

    def test_one_defined_range_per_defined_hyp(self):
        lemma = DefinedRange("q", F(0), F(15, 2), FIELDS)
        for defined in [(), (lemma, lemma), (lemma, DefinedRange("z", F(0), F(1), FIELDS))]:
            self.assertInvalid(WITH_LEMMA, Evidence(body=Enclosure(partition=Leaf()), defined=defined))


if __name__ == "__main__":
    unittest.main()
