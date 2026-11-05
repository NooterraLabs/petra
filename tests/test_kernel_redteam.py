"""Red team: try to make the kernel issue a Theorem for a false statement, or a
Refutation for a true one. Owner: M.

Part 2 of seam M. Each attack writes a statement whose truth was worked out by hand, with
evidence crafted to slip past a rule, and asserts the kernel refuses it. Every attack is
paired with a near-neighbour the kernel must still accept, so the attack demonstrably
tells truth from falsehood rather than rejecting everything.

One attack succeeds and exposes a soundness bug. It is kept, marked
@unittest.expectedFailure with the bug named, and reported. Attacks are never weakened to
pass.
"""
import copy
import dataclasses
import json
import pickle
import unittest
from fractions import Fraction as Q

from lola.kernel import (
    Add,
    Const,
    DefinedRange,
    Div,
    Evidence,
    Invalid,
    Ln,
    Matrix,
    Neg,
    PowInt,
    DefinedHyp,
    Instance,
    Interval,
    Leaf,
    RangeHyp,
    Refutation,
    Rejection,
    Split,
    Sqrt,
    Statement,
    Sym,
    Theorem,
    TooWeak,
    check,
    decode_statement,
    encode_statement,
    forget_families,
    is_issued,
)
from lola.kernel.codec import DecodeError
from lola.kernel.rules.r2_definite import GramPositiveDefinite, GramTerm, LDLFactor
from lola.kernel.rules.r3_hypercircle import (
    ComponentBound,
    Hypercircle,
    HypercircleFields,
    HypercircleViolation,
    MinimizerBound,
    MinimizerComponent,
    QuadraticProblem,
)
from lola.kernel.rules.r4_enclosure import AllNonpositive, Enclosure, PointWitness
from lola.kernel.rules.r5_moment import MomentBound, MomentConstraint, MomentDual, RandomVar
from lola.kernel.rules.r6_scenario import Arithmetic, BinomialTail
from tests import mutations


def c(v) -> Const:
    return Const(Q(v))


def r4(sym, lo, hi, expr) -> Statement:
    return Statement(hyps=(RangeHyp(sym, Q(lo), Q(hi), f"in:{sym}"),), goal=AllNonpositive(exprs=(expr,)))


def leaf_check(statement: Statement):
    return check(statement, Evidence(Enclosure(partition=Leaf())))


class Base(unittest.TestCase):
    def assertRejected(self, result, fault=None, needle=None):
        self.assertIsInstance(result, Rejection, f"expected a Rejection, got {type(result).__name__}")
        if fault is not None:
            self.assertIsInstance(result.fault, fault, result.reason)
        if needle is not None:
            self.assertIn(needle, result.reason)
        return result

    def assertTheorem(self, result):
        self.assertIsInstance(result, Theorem, getattr(result, "reason", ""))
        return result


class IntervalDomainErrors(Base):
    """An interval that reaches a point where the expression is undefined must never
    certify a bound. The enclosure raises and the kernel turns it into a Rejection, it
    never silently skips the bad point."""

    def test_zero_in_a_denominator_is_rejected_not_proven(self):
        self.assertRejected(leaf_check(r4("x", -1, 1, Div(c(1), Sym("x")))), Invalid, "contains 0")
        self.assertTheorem(leaf_check(r4("x", 1, 2, Add((Div(c(1), Sym("x")), c(-2))))))

    def test_sqrt_and_ln_of_non_positive_intervals_are_rejected(self):
        self.assertRejected(leaf_check(r4("x", -1, 1, Sqrt(Sym("x")))), Invalid, "sqrt")
        self.assertRejected(leaf_check(r4("x", 0, 1, Ln(Sym("x")))), Invalid, "ln")
        self.assertTheorem(leaf_check(r4("x", 1, 4, Add((Ln(Sym("x")), c(-2))))))


class Magnitudes(Base):
    """Exact rationals carry arbitrary magnitude with no float error, and sqrt rounds
    outward, so a false bound by a hair is not accepted."""

    HUGE = Q(10) ** 600
    TINY = Q(1, 10 ** 600)

    def test_huge_and_tiny_rationals_decide_correctly(self):
        self.assertRejected(leaf_check(r4("x", 0, self.HUGE, Add((Sym("x"), c(-1))))), TooWeak)
        self.assertTheorem(leaf_check(r4("x", 0, self.HUGE, Add((Sym("x"), Neg(c(self.HUGE)))))))
        self.assertTheorem(leaf_check(r4("x", 0, self.TINY, Add((Sym("x"), Neg(c(self.TINY)))))))

    def test_sqrt_rounds_outward_so_a_bound_below_the_root_fails(self):
        # sqrt(2) = 1.41421356...; a claim of <= 1.41421 is false, <= 1.41422 is true.
        self.assertRejected(leaf_check(r4("x", 2, 2, Add((Sqrt(Sym("x")), Neg(c(Q(141421, 100000))))))), TooWeak)
        self.assertTheorem(leaf_check(r4("x", 2, 2, Add((Sqrt(Sym("x")), Neg(c(Q(141422, 100000))))))))


class Boxes(Base):
    def test_an_empty_box_is_malformed_not_vacuously_proven(self):
        self.assertRejected(leaf_check(r4("x", 1, 0, Sym("x"))), Invalid, "lo > hi")

    def test_a_degenerate_point_box_still_discriminates(self):
        self.assertTheorem(leaf_check(r4("x", 5, 5, Add((Sym("x"), c(-5))))))
        false_at_the_point = r4("x", 5, 5, Add((Sym("x"), c(-4))))
        self.assertRejected(leaf_check(false_at_the_point), TooWeak)
        self.assertIsInstance(check(false_at_the_point, Evidence(PointWitness((("x", Q(5)),), 0))), Refutation)


QUAD = r4("x", 0, 1, Add((PowInt(Sym("x"), 2), Neg(Sym("x")), c(Q(-1, 10)))))


class Partitions(Base):
    """A split point must lie strictly inside its cell. On the boundary or outside it the
    two halves would not cover the cell, so the walk rejects it."""

    def test_split_on_the_boundary_or_outside_the_cell_is_rejected(self):
        for at in (0, 1, 2, -1):
            with self.subTest(at=at):
                self.assertRejected(check(QUAD, Evidence(Enclosure(Split("x", Q(at), Leaf(), Leaf())))), Invalid, "strictly inside")

    def test_an_interior_partition_still_proves_the_true_bound(self):
        fix = mutations.BY_NAME["r4_enclosure"]
        self.assertTheorem(check(fix.statement, fix.evidence))


def one_term_pd(w_lo, w_hi) -> Statement:
    goal = GramPositiveDefinite(dim=1, terms=(GramTerm(Sym("w"), Matrix(1, 1, ((0, 0, Q(1)),))),))
    return Statement(hyps=(RangeHyp("w", Q(w_lo), Q(w_hi), "in:w"),), goal=goal)


class R2NegativeWeights(Base):
    """M(h) = w * [[1]] is positive definite only when w > 0. A negative weight cannot be
    certified: no positive pivot can factor a negative reference matrix."""

    IDENT = Matrix(1, 1, ((0, 0, Q(1)),))

    def test_a_negative_weight_cannot_be_certified_positive_definite(self):
        negative = one_term_pd(-1, -1)
        self.assertRejected(check(negative, Evidence(LDLFactor((Q(-1),), self.IDENT, (Q(-1),)))), Invalid, "pivot")
        self.assertRejected(check(negative, Evidence(LDLFactor((Q(1),), self.IDENT, (Q(1),)))), Invalid, "lower bound")

    def test_a_positive_weight_is_certified(self):
        self.assertTheorem(check(one_term_pd(1, 2), Evidence(LDLFactor((Q(1),), self.IDENT, (Q(1),)))))

    def test_a_lying_fraction_subclass_cannot_forge_a_positive_pivot(self):
        class Liar(Q):
            def __le__(self, other):
                return False

            def __gt__(self, other):
                return True

        forged = Evidence(LDLFactor((Q(-1),), self.IDENT, (Liar(-1),)))
        self.assertRejected(check(one_term_pd(-1, -1), forged), Invalid, "pivot")


PAIR = Matrix(1, 2, ((0, 0, Q(1)), (0, 1, Q(1))))
PROBLEM = QuadraticProblem(B=PAIR, f=(Sym("F"),), w=(c(1), c(3)))


class R3Inconsistency(Base):
    def test_a_field_that_breaks_equilibrium_is_rejected(self):
        st = Statement(hyps=(RangeHyp("F", Q(4), Q(8), "in:F"),), goal=MinimizerBound(PROBLEM, (ComponentBound(0, c(1), None, c(6)),), None))
        broken = HypercircleFields(s=((Q(0), Q(0)), (Q(0), Q(0))), u=((Q(0),), (Q(0),)))
        self.assertRejected(check(st, Evidence(Hypercircle(broken))), Invalid, "B s != f")
        self.assertTheorem(check(st, Evidence(Hypercircle(HypercircleFields(s=((Q(3), Q(1)), (Q(6), Q(2))), u=((Q(3),), (Q(6),)))))))


def hook(p) -> Statement:
    goal = MomentBound(
        random=(RandomVar("x", Sym("Lo"), Sym("Hi")),),
        moments=(MomentConstraint(Sym("x"), Sym("M"), Sym("M")),),
        fail=Add((Sym("x"), Neg(Sym("C")))),
        p=Q(p) if isinstance(p, int) else p,
    )
    hyps = tuple(sorted(
        (RangeHyp("C", Q(36), Q(40), "in:C"), RangeHyp("Hi", Q(40), Q(40), "in:Hi"), RangeHyp("Lo", Q(0), Q(0), "in:Lo"), RangeHyp("M", Q(10), Q(10), "in:M")),
        key=lambda h: h.sym,
    ))
    return Statement(hyps=hyps, goal=goal)


def dual(y) -> MomentDual:
    return MomentDual(y0=Q(0), y=(Q(y),), partition=Split("x", Q(36), Leaf(), Leaf()))


class R5Domination(Base):
    """A dual g must dominate the failure indicator over the whole support. A multiplier
    that makes g dip below zero (so g fails to dominate on part of the support), or that
    only meets a bound stronger than the truth, cannot certify the claim."""

    def test_a_dual_that_does_not_dominate_everywhere_is_rejected(self):
        # y = -1/36 makes g(x) = -x/36 < 0 on (0, 40], so it fails to dominate there.
        self.assertRejected(check(hook(Q(3, 10)), Evidence(dual(Q(-1, 36)))), TooWeak)

    def test_a_claim_stronger_than_the_true_bound_cannot_be_dualised(self):
        # The true bound is E[X]/36 = 10/36 = 5/18; any valid g exceeds p = 1/10.
        self.assertRejected(check(hook(Q(1, 10)), Evidence(dual(Q(1, 36)))), TooWeak, "5/18")

    def test_the_true_markov_bound_is_certified(self):
        self.assertTheorem(check(hook(Q(3, 10)), Evidence(dual(Q(1, 36)))))


def binomial(n, k, eps, beta) -> Statement:
    return Statement(hyps=(), goal=BinomialTail(n=c(n), k=c(k), eps=c(eps), beta=c(beta)))


class R6Degenerate(Base):
    """The binomial tail is defined for integers 0 <= k <= n and probabilities strictly
    inside (0, 1). Every degenerate parameter is rejected, not computed into a false bound."""

    def test_degenerate_parameters_are_rejected(self):
        cases = {
            "eps=0": binomial(300, 0, Q(0), Q(1, 20)),
            "eps=1": binomial(300, 0, Q(1), Q(1, 20)),
            "beta=1": binomial(300, 0, Q(1, 100), Q(1)),
            "k>n": binomial(3, 5, Q(1, 100), Q(1, 20)),
            "n=5/2": binomial(Q(5, 2), 0, Q(1, 100), Q(1, 20)),
        }
        for name, st in cases.items():
            with self.subTest(case=name):
                self.assertRejected(check(st, Evidence(Arithmetic())), Invalid)

    def test_a_well_posed_tail_is_certified(self):
        self.assertTheorem(check(binomial(300, 0, Q(1, 100), Q(1, 20)), Evidence(Arithmetic())))


FALSE_ST = r4("x", 0, 2, Add((Sym("x"), c(-1))))      # false at x = 2
TRUE_ST = r4("x", 0, 1, Add((Sym("x"), c(-2))))       # true over [0, 1]


def genuine_refutation() -> Refutation:
    r = check(FALSE_ST, Evidence(PointWitness((("x", Q(2)),), 0)))
    assert isinstance(r, Refutation)
    return r


def genuine_theorem() -> Theorem:
    t = check(TRUE_ST, Evidence(Enclosure(Leaf())))
    assert isinstance(t, Theorem)
    return t


class Forgery(Base):
    """Sealed results must not be forgeable. A laundered Refutation that reads as a
    Theorem would let a FAIL be presented as a PASS for a false statement."""

    def test_copy_pickle_and_replace_on_a_result_all_raise(self):
        for result in (genuine_theorem(), genuine_refutation()):
            for attack in (copy.copy, copy.deepcopy, pickle.dumps):
                with self.subTest(kind=type(result).__name__, attack=attack.__name__):
                    with self.assertRaises(TypeError):
                        attack(result)
            with self.subTest(kind=type(result).__name__, attack="replace"):
                with self.assertRaises(TypeError):
                    dataclasses.replace(result, statement=TRUE_ST)

    def test_object_new_handles_are_not_issued(self):
        self.assertFalse(is_issued(object.__new__(Theorem)))
        self.assertFalse(is_issued(object.__new__(Refutation)))

    def test_class_swap_cannot_launder_a_refutation_into_a_theorem(self):
        laundered = genuine_refutation()
        object.__setattr__(laundered, "__class__", Theorem)
        self.assertFalse(is_issued(laundered), "a class-swapped refutation must not read as an issued theorem")
        with self.assertRaises(TypeError):
            laundered.statement

    def test_class_swap_cannot_turn_a_theorem_into_a_refutation(self):
        swapped = genuine_theorem()
        object.__setattr__(swapped, "__class__", Refutation)
        self.assertFalse(is_issued(swapped), "a class-swapped theorem must not read as an issued refutation")

    def test_unswapped_results_stay_issued(self):
        self.assertTrue(is_issued(genuine_refutation()))
        self.assertTrue(is_issued(genuine_theorem()))


class Hypotheses(Base):
    """The footprint is the labels of the used hypotheses, so an unused or duplicated
    hypothesis must be rejected rather than padding the footprint with facts the proof
    never used."""

    def test_an_unused_hypothesis_is_rejected(self):
        with_spare = Statement(
            hyps=tuple(sorted((RangeHyp("x", Q(0), Q(1), "in:x"), RangeHyp("z", Q(0), Q(1), "in:z")), key=lambda h: h.sym)),
            goal=AllNonpositive(exprs=(Add((Sym("x"), c(-2))),)),
        )
        self.assertRejected(leaf_check(with_spare), Invalid, "unused")

    def test_a_duplicate_hypothesis_is_rejected(self):
        duped = Statement(
            hyps=(RangeHyp("x", Q(0), Q(1), "in:x"), RangeHyp("x", Q(0), Q(1), "in:x2")),
            goal=AllNonpositive(exprs=(Add((Sym("x"), c(-2))),)),
        )
        self.assertRejected(leaf_check(duped), Invalid, "duplicates")

    def test_the_clean_statement_is_accepted(self):
        self.assertTheorem(leaf_check(r4("x", 0, 1, Add((Sym("x"), c(-2))))))


class DefinedHypCycles(Base):
    """A DefinedHyp may name only RangeHyp symbols. A definition that reaches another
    defined symbol is a cycle and is rejected before any rule runs."""

    def test_a_definition_referring_to_another_defined_symbol_is_rejected(self):
        cyclic = Statement(
            hyps=tuple(sorted(
                (RangeHyp("F", Q(4), Q(8), "in:F"),
                 DefinedHyp("q", MinimizerComponent(PROBLEM, 0, Sym("q2"))),
                 DefinedHyp("q2", MinimizerComponent(PROBLEM, 1, c(1)))),
                key=lambda h: h.sym,
            )),
            goal=AllNonpositive(exprs=(Add((Sym("q"), Neg(Sym("q2")))),)),
        )
        self.assertRejected(check(cyclic, Evidence(Enclosure(Leaf()))), Invalid, "RangeHyp symbols only")

    def test_a_definition_over_a_range_symbol_is_accepted(self):
        fix = mutations.BY_NAME["r3_lemma"]
        self.assertTheorem(check(fix.statement, fix.evidence))


class StatementHashBinding(Base):
    """A certificate is bound to its statement by hash (design.md call site 3). A file
    whose stored hash does not match its statement is refused before the kernel runs."""

    def test_a_tampered_statement_hash_is_detected(self):
        env = mutations.BY_NAME["r1_feasible"].envelope()
        self.assertIsInstance(mutations.verify_envelope(env), Theorem)
        env["statement_hash"] = "sha256:" + "0" * 64
        self.assertIsInstance(mutations.verify_envelope(env), mutations.HashMismatch)

    def test_a_statement_whose_hash_matches_still_checks(self):
        self.assertIsInstance(mutations.verify_envelope(mutations.BY_NAME["r6_binomial"].envelope()), Theorem)


class NoFalseRefutation(Base):
    def test_a_true_statement_cannot_be_refuted(self):
        true_at_the_edge = r4("x", 0, 1, Add((Sym("x"), c(-1))))
        self.assertRejected(check(true_at_the_edge, Evidence(PointWitness((("x", Q(1)),), 0))), TooWeak)
        self.assertIsInstance(check(FALSE_ST, Evidence(PointWitness((("x", Q(2)),), 0))), Refutation)


def over_q(goal) -> Statement:
    return Statement(hyps=(RangeHyp("F", Q(4), Q(8), "in:F"), DefinedHyp("q", MinimizerComponent(PROBLEM, 0, c(1)))), goal=goal)


def fields_at(F) -> HypercircleFields:
    """The exact field at F, s* = (3F/4, F/4) and u* = 3F/4, once per vertex of the point box."""
    s, u = (Q(3 * F, 4), Q(F, 4)), (Q(3 * F, 4),)
    return HypercircleFields(s=(s, s), u=(u, u))


def q_witness(F, lo, hi) -> Evidence:
    return Evidence(PointWitness((("F", Q(F)),), 0), (DefinedRange("q", Q(lo), Q(hi), fields_at(F)),))


def above(lo) -> Statement:
    """s*_0 >= lo for the problem whose right-hand side is q itself: s*_0 = 3q/4, which lies
    in [9/4, 9/2] over the box and is 9/2 at F = 8."""
    loaded = QuadraticProblem(B=PAIR, f=(Sym("q"),), w=(c(1), c(3)))
    return over_q(MinimizerBound(loaded, (ComponentBound(0, c(1), c(lo), None),), None))


class DefinedRefutations(Base):
    """q = s*_0 = 3F/4 of PROBLEM for F in [4, 8], so q <= 6 everywhere, with q = 6 at
    F = 8. A refutation fixes F at its point and lets q span the range its lemma proves
    there. q - 7 <= 0 and q - 6 <= 0 are true, q - 5 <= 0 is false at F = 8. Each attack
    aims a Refutation at a statement true at the attack's point, and each neighbour
    refutes a false statement with the same kind of evidence."""

    TRUE_7 = over_q(AllNonpositive(exprs=(Add((Sym("q"), c(-7))),)))
    TRUE_6 = over_q(AllNonpositive(exprs=(Add((Sym("q"), c(-6))),)))
    FALSE_5 = over_q(AllNonpositive(exprs=(Add((Sym("q"), c(-5))),)))

    def test_a_range_that_lies_about_q_is_not_proved(self):
        self.assertRejected(check(self.TRUE_7, q_witness(8, 8, 9)), TooWeak, "the hypercircle gives [6, 6]")
        self.assertIsInstance(check(self.FALSE_5, q_witness(8, 6, 6)), Refutation)

    def test_an_honest_wide_range_cannot_stand_in_for_one_of_its_values(self):
        self.assertRejected(check(self.TRUE_6, q_witness(8, 6, 7)), TooWeak, "encloses down to 0")
        self.assertIsInstance(check(self.FALSE_5, q_witness(8, 6, 7)), Refutation)

    def test_a_point_outside_the_box_is_not_a_counterexample(self):
        self.assertRejected(check(self.TRUE_7, q_witness(12, 9, 9)), Invalid, "inside its range")
        self.assertIsInstance(check(self.FALSE_5, q_witness(8, 6, 6)), Refutation)

    def test_q_cannot_be_given_a_value_in_the_point(self):
        smuggled = Evidence(PointWitness((("F", Q(8)), ("q", Q(9))), 0), (DefinedRange("q", Q(6), Q(6), fields_at(8)),))
        self.assertRejected(check(self.TRUE_7, smuggled), Invalid, "in order")
        self.assertIsInstance(check(self.FALSE_5, q_witness(8, 6, 6)), Refutation)

    def test_a_right_hand_side_spanning_q_cannot_be_read_at_one_end(self):
        at_2 = HypercircleViolation(point=(("F", Q(8)),), s=(Q(3, 2), Q(1, 2)), u=(Q(3, 2),), which=0)
        wide = (DefinedRange("q", Q(2), Q(13, 2), fields_at(8)),)
        self.assertRejected(check(above(2), Evidence(at_2, wide)), Invalid, "one exact vector")
        at_6 = HypercircleViolation(point=(("F", Q(8)),), s=(Q(9, 2), Q(3, 2)), u=(Q(9, 2),), which=0)
        self.assertIsInstance(check(above(5), Evidence(at_6, (DefinedRange("q", Q(6), Q(6), fields_at(8)),))), Refutation)


HAIR = Q(1, 2 ** 256)
"""Exact rationals have no smallest step, so a hair stands for one: a positive excess far
below every range in these statements. Any positive excess must be refused."""

EXACT_FIELDS = HypercircleFields(s=((Q(3), Q(1)), (Q(6), Q(2))), u=((Q(3),), (Q(6),)))


def between(q: str, top) -> AllNonpositive:
    """q - top <= 0 and 3 - q <= 0."""
    return AllNonpositive(exprs=(Add((Sym(q), c(-top))), Add((c(3), Neg(Sym(q))))))


def family(top=6, extra=()) -> Statement:
    """F in [4, 8] and q = s*_0 = 3F/4 of PROBLEM, so q spans exactly [3, 6]: q <= top
    holds for top >= 6 and is false at F = 8 for top < 6."""
    hyps = tuple(sorted((RangeHyp("F", Q(4), Q(8), "in:F"), DefinedHyp("q", MinimizerComponent(PROBLEM, 0, c(1)))) + extra, key=lambda h: h.sym))
    return Statement(hyps=hyps, goal=between("q", top))


FAMILY = family()
FAMILY_EVIDENCE = Evidence(Enclosure(Leaf()), (DefinedRange("q", Q(3), Q(6), EXACT_FIELDS),))
RHO = (("F", "P"), ("q", "z"))


def query(lo, hi, top=6, scale=1) -> Statement:
    """The family renamed F to P and q to z, over P in [lo, hi]. z = scale * 3P/4."""
    problem = QuadraticProblem(B=PAIR, f=(Sym("P"),), w=(c(1), c(3)))
    return Statement(hyps=(RangeHyp("P", Q(lo), Q(hi), "in:P"), DefinedHyp("z", MinimizerComponent(problem, 0, c(scale)))), goal=between("z", top))


def instance(statement=FAMILY, evidence=FAMILY_EVIDENCE, renaming=RHO) -> Evidence:
    return Evidence(Instance(statement, evidence, renaming))


def hook_bound_as(x: str) -> Statement:
    """hook(3/10) with its random variable named x."""
    goal = MomentBound(
        random=(RandomVar(x, Sym("Lo"), Sym("Hi")),),
        moments=(MomentConstraint(Sym(x), Sym("M"), Sym("M")),),
        fail=Add((Sym(x), Neg(Sym("C")))),
        p=Q(3, 10),
    )
    return Statement(hyps=hook(Q(3, 10)).hyps, goal=goal)


class InstanceForgeries(Base):
    """Instance evidence lets a query borrow a family theorem through a renaming. Every
    attack is refused and every neighbour borrows a theorem for a true instance. The
    attacks aim at queries that are false or ill-formed, except the nested Instance,
    which is refused for its depth alone. Over P in [lo, hi] the query's z = 3P/4 spans
    [3lo/4, 3hi/4], so 3 <= z <= 6 holds exactly when [lo, hi] lies inside [4, 8], the
    family box."""

    def test_a_query_range_wider_by_a_hair_is_not_an_instance(self):
        # At P = 8 + HAIR, z = 6 + 3 HAIR/4 > 6; at P = 4 - HAIR, z = 3 - 3 HAIR/4 < 3.
        self.assertRejected(check(query(4, 8 + HAIR), instance()), Invalid, "not inside the family range")
        self.assertRejected(check(query(4 - HAIR, 8), instance()), Invalid, "not inside the family range")
        self.assertTheorem(check(query(4, 8), instance()))
        self.assertTheorem(check(query(5, 7), instance()))

    def test_an_empty_query_box_is_not_vacuously_an_instance(self):
        self.assertRejected(check(query(7, 5), instance()), Invalid, "not inside the family range")
        self.assertTheorem(check(query(5, 5), instance()))

    def test_a_renaming_that_is_not_a_bijection_is_rejected(self):
        # Renaming the random variable x to M captures the mean hypothesis M.
        captured = (("C", "C"), ("Hi", "Hi"), ("Lo", "Lo"), ("M", "M"), ("x", "M"))
        self.assertRejected(check(hook_bound_as("M"), instance(hook(Q(3, 10)), Evidence(dual(Q(1, 36))), captured)), Invalid, "distinct")
        fresh = (("C", "C"), ("Hi", "Hi"), ("Lo", "Lo"), ("M", "M"), ("x", "y"))
        result = self.assertTheorem(check(hook_bound_as("y"), instance(hook(Q(3, 10)), Evidence(dual(Q(1, 36))), fresh)))
        self.assertEqual(result.rule, "R5", "an Instance reports its family's rule")
        # a - b + 1 <= 0 holds over a in [0, 1], b in [2, 3]. Merging a and b into x
        # would give 1 <= 0, which is false at every point.
        pair = Statement(hyps=(RangeHyp("a", Q(0), Q(1), "in:a"), RangeHyp("b", Q(2), Q(3), "in:b")), goal=AllNonpositive(exprs=(Add((Sym("a"), Neg(Sym("b")), c(1))),)))
        merged = Statement(hyps=(RangeHyp("x", Q(0), Q(1), "in:x"), RangeHyp("x", Q(2), Q(3), "in:y")), goal=AllNonpositive(exprs=(Add((Sym("x"), Neg(Sym("x")), c(1))),)))
        kept = Statement(hyps=(RangeHyp("x", Q(0), Q(1), "in:x"), RangeHyp("y", Q(2), Q(3), "in:y")), goal=AllNonpositive(exprs=(Add((Sym("x"), Neg(Sym("y")), c(1))),)))
        leaf = Evidence(Enclosure(Leaf()))
        self.assertRejected(check(merged, instance(pair, leaf, (("a", "x"), ("b", "x")))), Invalid, "distinct")
        self.assertTheorem(check(kept, instance(pair, leaf, (("a", "x"), ("b", "y")))))

    def test_a_goal_that_differs_by_one_constant_is_not_an_instance(self):
        # z <= 5 fails at P = 8, where z = 6.
        self.assertRejected(check(query(4, 8, top=5), instance()), Invalid, "not the family goal renamed")
        self.assertTheorem(check(query(4, 8, top=6), instance()))

    def test_a_definition_that_differs_is_not_an_instance(self):
        # Scale 2 makes z = 3P/2, which is 12 at P = 8.
        self.assertRejected(check(query(4, 8, scale=2), instance()), Invalid, "not defined as its family counterpart")
        self.assertTheorem(check(query(4, 8, scale=1), instance()))

    def test_family_evidence_that_does_not_check_proves_nothing(self):
        # The family with top 5 is false at F = 8, and q cannot be held to [3, 5].
        lie = Evidence(Enclosure(Leaf()), (DefinedRange("q", Q(3), Q(5), EXACT_FIELDS),))
        self.assertRejected(check(query(4, 8, top=5), instance(family(top=5), lie)), Invalid, "does not check")
        self.assertTheorem(check(query(4, 8, top=6), instance(family(top=6), FAMILY_EVIDENCE)))

    def test_a_family_refutation_has_no_instances(self):
        witness = Evidence(PointWitness((("F", Q(8)),), 0), (DefinedRange("q", Q(6), Q(6), fields_at(8)),))
        self.assertIsInstance(check(family(top=5), witness), Refutation, "the family with top 5 is false at F = 8")
        self.assertRejected(check(query(4, 8, top=5), instance(family(top=5), witness)), Invalid, "refutes")
        self.assertTheorem(check(query(4, 8, top=6), instance()))

    def test_an_instance_of_an_instance_is_rejected(self):
        middle = Statement(hyps=(RangeHyp("G", Q(4), Q(8), "in:G"), DefinedHyp("w", MinimizerComponent(QuadraticProblem(B=PAIR, f=(Sym("G"),), w=(c(1), c(3))), 0, c(1)))), goal=between("w", 6))
        middle_evidence = instance(renaming=(("F", "G"), ("q", "w")))
        self.assertTheorem(check(middle, middle_evidence))
        self.assertRejected(check(query(5, 7), instance(middle, middle_evidence, (("G", "P"), ("w", "z")))), Invalid, "not itself an Instance")
        self.assertTheorem(check(query(5, 7), instance()))

    def test_a_family_hypothesis_the_query_lacks_is_not_dropped(self):
        # q + r - 7 <= 0 holds for r in [0, 1]. Without its hypothesis zeta is free, and
        # zeta = 2 breaks the goal at P = 8. zeta sorts last, so pairing the hypotheses
        # in order would run out of query hypotheses before it.
        with_r = Statement(hyps=family(extra=(RangeHyp("r", Q(0), Q(1), "in:r"),)).hyps, goal=AllNonpositive(exprs=(Add((Sym("q"), Sym("r"), c(-7))),)))
        problem = QuadraticProblem(B=PAIR, f=(Sym("P"),), w=(c(1), c(3)))
        z = DefinedHyp("z", MinimizerComponent(problem, 0, c(1)))
        goal = AllNonpositive(exprs=(Add((Sym("z"), Sym("zeta"), c(-7))),))
        lacking = Statement(hyps=(RangeHyp("P", Q(4), Q(8), "in:P"), z), goal=goal)
        holding = Statement(hyps=(RangeHyp("P", Q(4), Q(8), "in:P"), z, RangeHyp("zeta", Q(0), Q(1, 2), "in:zeta")), goal=goal)
        renaming = (("F", "P"), ("q", "z"), ("r", "zeta"))
        self.assertRejected(check(lacking, instance(with_r, FAMILY_EVIDENCE, renaming)), Invalid, "pair one to one")
        self.assertTheorem(check(holding, instance(with_r, FAMILY_EVIDENCE, renaming)))


    def test_family_evidence_that_changes_while_read_is_judged_by_its_encoding(self):
        # Reading the bound below turns the middle evidence's body from an Instance into a
        # plain enclosure, after the encoder has already spelled it as an Instance. A
        # check of the raw object would pass the one-level rule while the encoding, which
        # the hash names, nests two levels.
        middle = Statement(hyps=(RangeHyp("G", Q(4), Q(8), "in:G"), DefinedHyp("w", MinimizerComponent(QuadraticProblem(B=PAIR, f=(Sym("G"),), w=(c(1), c(3))), 0, c(1)))), goal=between("w", 6))

        class Flip(Q):
            @property
            def numerator(self):
                object.__setattr__(holder, "body", Enclosure(Leaf()))
                return self._numerator

        holder = Evidence(Instance(FAMILY, Evidence(Enclosure(Leaf()), (DefinedRange("q", Flip(3), Q(6), EXACT_FIELDS),)), (("F", "G"), ("q", "w"))))
        forget_families()
        result = check(query(5, 7), instance(middle, holder, (("G", "P"), ("w", "z"))))
        self.assertRejected(result, Invalid, "not itself an Instance")
        self.assertIsInstance(holder.body, Enclosure, "the raw object no longer shows the nesting")
        self.assertTheorem(check(query(5, 7), instance()))

    def test_instances_of_one_family_share_no_mutable_range(self):
        # Every Instance of a family borrows the defined ranges of one remembered theorem.
        # Writing into one issued range must not change what any other result certifies.
        forget_families()
        first = self.assertTheorem(check(query(5, 7), instance()))
        second = self.assertTheorem(check(query(4, 8), instance()))
        ((_, a),), ((_, b),) = first.defined_ranges, second.defined_ranges
        self.assertIsNot(a, b)
        self.assertIsNot(a.lo, b.lo)
        object.__setattr__(a, "lo", Q(100))
        object.__setattr__(a, "hi", Q(200))
        third = self.assertTheorem(check(query(5, 6), instance()))
        self.assertEqual(second.defined_ranges, (("z", Interval(Q(3), Q(6))),))
        self.assertEqual(third.defined_ranges, (("z", Interval(Q(3), Q(6))),))

    def test_strings_with_surrogates_have_no_canonical_text(self):
        # ensure_ascii spells a surrogate pair and the character it encodes alike, so two
        # different symbols would share a statement hash and a family memo key.
        pair, astral = chr(0xD83D) + chr(0xDE00), chr(0x1F600)
        self.assertEqual(json.dumps(pair, ensure_ascii=True), json.dumps(astral, ensure_ascii=True))

        def named(sym: str) -> Statement:
            return r4(sym, 0, 1, Add((Sym(sym), c(-1))))

        self.assertRejected(leaf_check(named(pair)), Invalid, "surrogate")
        self.assertTheorem(leaf_check(named(astral)))
        lone = encode_statement(named("x"))
        lone["hyps"][0]["sym"] = chr(0xD83D)
        with self.assertRaises(DecodeError):
            decode_statement(lone)

if __name__ == "__main__":
    unittest.main()
