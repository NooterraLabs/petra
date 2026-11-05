"""Rules R1 to R6 through kernel.check, with outcomes worked out by hand. Owner: K."""
import unittest
from fractions import Fraction as F

from lola.kernel import (
    Add,
    Const,
    DefinedHyp,
    DefinedRange,
    Evidence,
    Interval,
    Invalid,
    Leaf,
    Matrix,
    Mul,
    Neg,
    PowInt,
    RangeHyp,
    Refutation,
    Rejection,
    Split,
    Statement,
    Sym,
    Theorem,
    TooWeak,
    check,
)
from lola.kernel.rules.r1_linear import FarkasRay, FeasiblePoints, LinearFeasible
from lola.kernel.rules.r2_definite import GramPositiveDefinite, GramTerm, LDLFactor, NegativeDirection
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
from lola.kernel.rules.r6_scenario import Arithmetic, BinomialTail, tail
from tests.test_codec import BOLT_EVIDENCE, bolt_statement


def c(v) -> Const:
    return Const(F(v))


def hyp(sym, lo, hi=None) -> RangeHyp:
    return RangeHyp(sym, F(lo), F(lo if hi is None else hi), f"in:{sym}")


def pt(**values) -> tuple:
    return tuple((s, F(v)) for s, v in sorted(values.items()))


class RuleCase(unittest.TestCase):
    def assertTheorem(self, statement, body, defined=(), why=""):
        result = check(statement, Evidence(body=body, defined=defined))
        self.assertIsInstance(result, Theorem, f"{why} {getattr(result, 'reason', '')}")
        return result

    def assertRefutation(self, statement, body):
        result = check(statement, Evidence(body=body))
        self.assertIsInstance(result, Refutation, getattr(result, "reason", None))
        return result

    def assertFault(self, fault, statement, body, defined=()):
        result = check(statement, Evidence(body=body, defined=defined))
        self.assertIsInstance(result, Rejection, f"expected a {fault.__name__} rejection")
        self.assertIsInstance(result.fault, fault, result.reason)
        return result


PAIR = Matrix(1, 2, ((0, 0, F(1)), (0, 1, F(1))))


def split_load(lo, hi, b=(Sym("F"),), lower=(c(0), c(0)), upper=(c(3), c(3)), extra=()) -> Statement:
    """x_0 + x_1 = b(F) with lower <= x <= upper, for F in [lo, hi]."""
    return Statement(hyps=extra + (hyp("F", lo, hi),), goal=LinearFeasible(A=PAIR, b=b, lower=lower, upper=upper))


def points(*xs) -> FeasiblePoints:
    return FeasiblePoints(x=tuple(tuple(F(v) for v in x) for x in xs))


class LinearFeasibility(RuleCase):
    def test_one_feasible_point_per_vertex_proves_the_box(self):
        self.assertTheorem(split_load(2, 4), points((1, 1), (2, 2)))

    def test_each_point_must_solve_its_own_vertex_within_bounds(self):
        for body in [points((2, 2), (1, 1)), points((-1, 3), (2, 2)), points((1, 1))]:
            self.assertFault(Invalid, split_load(2, 4), body)

    def test_b_must_be_affine(self):
        dip = split_load(2, 4, b=(PowInt(Add((Sym("F"), c(-3))), 2),), lower=(c(F(1, 2)), c(F(1, 2))))
        self.assertFault(Invalid, dip, points((F(1, 2), F(1, 2)), (F(1, 2), F(1, 2))))

    def test_bounds_are_taken_at_their_worst_over_the_box(self):
        capped = split_load(2, 4, upper=(Sym("C"), Sym("C")), extra=(hyp("C", 2, 3),))
        self.assertTheorem(capped, points((1, 1), (2, 2)))
        self.assertFault(Invalid, capped, points((1, 1), (3, 1)))

    def test_vertices_follow_the_documented_order(self):
        goal = LinearFeasible(A=Matrix(1, 1, ((0, 0, F(1)),)), b=(Add((Sym("F"), Mul((c(10), Sym("G"))))),), lower=(None,), upper=(None,))
        st = Statement(hyps=(hyp("F", 0, 1), hyp("G", 0, 1)), goal=goal)
        self.assertTheorem(st, points((0,), (1,), (10,), (11,)))
        self.assertFault(Invalid, st, points((0,), (10,), (1,), (11,)))

    def test_a_farkas_ray_refutes_at_a_point(self):
        st = split_load(2, 7)
        self.assertRefutation(st, FarkasRay(point=pt(F=7), y=(F(1),)))
        self.assertFault(TooWeak, st, FarkasRay(point=pt(F=7), y=(F(-1),)))
        self.assertFault(TooWeak, st, FarkasRay(point=pt(F=6), y=(F(1),)))
        self.assertFault(Invalid, st, FarkasRay(point=pt(F=8), y=(F(1),)))

    def test_a_ray_may_not_push_along_an_unbounded_variable(self):
        self.assertFault(Invalid, split_load(2, 7, upper=(None, c(3))), FarkasRay(point=pt(F=7), y=(F(1),)))


IDENTITY = Matrix(2, 2, ((0, 0, F(1)), (1, 1, F(1))))
ONES = Matrix(2, 1, ((0, 0, F(1)), (1, 0, F(1))))
UNIT_LOWER = Matrix(2, 2, ((0, 0, F(1)), (1, 0, F(-1, 3)), (1, 1, F(1))))


def stiffness(lam_hi, dim=2) -> Statement:
    """E I - lam 1 1^T, with eigenvalues E and E - 2 lam, for E in [1, 2] and lam in [0, lam_hi]."""
    goal = GramPositiveDefinite(dim=dim, terms=(GramTerm(Sym("E"), IDENTITY), GramTerm(Neg(Sym("lam")), ONES)))
    return Statement(hyps=(hyp("E", 1, 2), hyp("lam", 0, lam_hi)), goal=goal)


def ldl(r0=1, d1=F(2, 3), L=UNIT_LOWER) -> LDLFactor:
    """The reference I - (1/4) 1 1^T = [[3/4, -1/4], [-1/4, 3/4]] has L = [[1, 0], [-1/3, 1]], d = (3/4, 2/3)."""
    return LDLFactor(reference_weights=(F(r0), F(-1, 4)), L=L, d=(F(3, 4), F(d1)))


class Definiteness(RuleCase):
    def test_an_exact_ldl_of_a_reference_below_the_box_proves_it(self):
        self.assertTheorem(stiffness(F(1, 4)), ldl())

    def test_each_part_of_the_factor_is_checked(self):
        above = Matrix(2, 2, ((0, 0, F(1)), (0, 1, F(1, 2)), (1, 0, F(-1, 3)), (1, 1, F(1))))
        for body in [ldl(d1=-1), ldl(r0=F(3, 2)), ldl(L=above), ldl(d1=F(3, 4))]:
            self.assertFault(Invalid, stiffness(F(1, 4)), body)
        self.assertFault(Invalid, stiffness(F(1, 4), dim=3), ldl())

    def test_a_reference_must_lie_below_the_whole_box(self):
        self.assertFault(Invalid, stiffness(1), ldl())

    def test_a_direction_of_nonpositive_curvature_refutes(self):
        st = stiffness(1)
        self.assertRefutation(st, NegativeDirection(point=pt(E=1, lam=1), v=(F(1), F(1))))
        self.assertRefutation(st, NegativeDirection(point=pt(E=1, lam=F(1, 2)), v=(F(1), F(1))))
        self.assertFault(TooWeak, st, NegativeDirection(point=pt(E=1, lam=1), v=(F(1), F(-1))))
        self.assertFault(Invalid, st, NegativeDirection(point=pt(E=1, lam=1), v=(F(0), F(0))))


PROBLEM = QuadraticProblem(B=PAIR, f=(Sym("F"),), w=(c(1), c(3)))
EXACT = HypercircleFields(s=((F(3), F(1)), (F(6), F(2))), u=((F(3),), (F(6),)))
PER_WEIGHT = QuadraticProblem(B=PAIR, f=(c(3),), w=(c(1), Sym("k")))


def minimizer(*bounds, energy_hi=None) -> Statement:
    """min s_0^2 + 3 s_1^2 subject to s_0 + s_1 = F, for F in [4, 8]: s* = (3F/4, F/4),
    u* = 3F/4, energy 3F^2/4, so s*_0 in [3, 6], s*_1 in [1, 2] and the energy reaches 48."""
    return Statement(hyps=(hyp("F", 4, 8),), goal=MinimizerBound(problem=PROBLEM, bounds=bounds, energy_hi=energy_hi))


def per_weight(hi, k_lo=2) -> Statement:
    """min s_0^2 + k s_1^2 subject to s_0 + s_1 = 3, for k in [k_lo, 4]: s*_0 = 3k/(k + 1)."""
    return Statement(hyps=(hyp("k", k_lo, 4),), goal=MinimizerBound(problem=PER_WEIGHT, bounds=(bound(hi),), energy_hi=None))


def bound(hi, lo=None, index=0, scale=1) -> ComponentBound:
    return ComponentBound(index, c(scale), None if lo is None else c(lo), c(hi))


def violation(at, s, u, which=0) -> HypercircleViolation:
    return HypercircleViolation(point=pt(F=at), s=tuple(map(F, s)), u=tuple(map(F, u)), which=which)


class Hypercircles(RuleCase):
    def test_exact_fields_prove_the_tight_bounds(self):
        self.assertTheorem(minimizer(bound(6, lo=3), bound(8, index=1, scale=4), energy_hi=c(48)), Hypercircle(EXACT))

    def test_claims_past_the_minimiser_are_too_weak(self):
        for st in [minimizer(bound(F(59, 10))), minimizer(bound(F(15, 2), index=1, scale=4)), minimizer(energy_hi=c(47))]:
            self.assertFault(TooWeak, st, Hypercircle(EXACT))

    def test_any_u_gives_a_sound_but_wider_sphere(self):
        sloppy = Hypercircle(HypercircleFields(s=EXACT.s, u=((F(0),), (F(0),))))
        self.assertTheorem(minimizer(bound(7)), sloppy, why="at F = 8 the sphere is 3 +- 2 sqrt 3, up to 6.47")
        self.assertFault(TooWeak, minimizer(bound(6)), sloppy)

    def test_fields_must_be_admissible_at_every_vertex(self):
        for fields in [HypercircleFields(s=((F(3), F(1)), (F(6), F(3))), u=EXACT.u), HypercircleFields(s=EXACT.s[:1], u=EXACT.u[:1])]:
            self.assertFault(Invalid, minimizer(bound(6)), Hypercircle(fields))

    def test_one_sphere_covers_every_weight_in_the_box(self):
        exact_at_k_2 = Hypercircle(HypercircleFields(s=((F(2), F(1)),), u=((F(2),),)))
        self.assertTheorem(per_weight(3), exact_at_k_2)
        self.assertFault(TooWeak, per_weight(F(21, 10)), exact_at_k_2)
        self.assertFault(Invalid, per_weight(3, k_lo=0), exact_at_k_2)

    def test_a_sphere_outside_the_bound_refutes(self):
        st = minimizer(bound(5))
        self.assertRefutation(st, violation(8, (6, 2), (6,)))
        self.assertFault(TooWeak, st, violation(4, (3, 1), (3,)))
        self.assertFault(Invalid, st, violation(8, (6, 3), (6,)))
        self.assertFault(Invalid, st, violation(8, (6, 2), (6,), which=1))

    def test_the_dual_energy_refutes_an_energy_bound(self):
        st = minimizer(energy_hi=c(40))
        self.assertRefutation(st, violation(8, (6, 2), (6,), which=-1))
        self.assertFault(TooWeak, st, violation(8, (6, 2), (0,), which=-1))

    def test_a_lemma_proves_the_range_of_a_defined_quantity(self):
        st = Statement(hyps=(hyp("F", 4, 8), DefinedHyp("q", MinimizerComponent(PROBLEM, 0, c(1)))), goal=AllNonpositive(exprs=(Add((Sym("q"), c(-7))),)))
        result = self.assertTheorem(st, Enclosure(partition=Leaf()), defined=(DefinedRange("q", F(3), F(6), EXACT),))
        self.assertEqual(result.defined_ranges, (("q", Interval(F(3), F(6))),))
        self.assertEqual(result.labels, frozenset({"in:F"}))
        self.assertFault(TooWeak, st, Enclosure(partition=Leaf()), defined=(DefinedRange("q", F(3), F(5), EXACT),))


def bolt(force_hi) -> Statement:
    st = bolt_statement()
    return Statement(hyps=(RangeHyp("F", F(0), F(force_hi), st.hyps[0].label),) + st.hyps[1:], goal=st.goal)


WORST = dict(K=F(4, 25), P=F(7, 4000), Rp02=450000000, T=50, c2=F(649519, 1000000), c3=F(1226869, 1000000), d=F(3, 250), phi=F(1, 4))
QUADRATIC = Statement(hyps=(hyp("x", 0, 1),), goal=AllNonpositive(exprs=(Add((PowInt(Sym("x"), 2), Neg(Sym("x")), c(F(-1, 10)))),)))


def split(at, left=Leaf(), right=Leaf()) -> Split:
    return Split("x", F(at), left, right)


class Enclosures(RuleCase):
    def test_the_bolt_margin_is_negative_on_its_box(self):
        self.assertTheorem(bolt_statement(), BOLT_EVIDENCE.body)
        self.assertTheorem(bolt_statement(), Enclosure(partition=Leaf()), why="the worst corner gives 26042 + 3000 - 34128 = -5086 N")

    def test_a_larger_force_range_is_refuted_at_its_worst_corner(self):
        st = bolt(40000)
        self.assertFault(TooWeak, st, Enclosure(partition=Leaf()))
        self.assertRefutation(st, PointWitness(point=pt(F=40000, **WORST), which=0))
        self.assertFault(TooWeak, st, PointWitness(point=pt(F=0, **WORST), which=0))

    def test_a_fine_partition_beats_the_dependency_problem(self):
        coarse = split(F(1, 2), split(F(1, 4)), split(F(3, 4), Leaf(), split(F(7, 8))))
        fine = split(F(1, 2), split(F(1, 4)), split(F(3, 4), Leaf(), split(F(7, 8), Leaf(), split(F(15, 16)))))
        self.assertTheorem(QUADRATIC, Enclosure(fine))
        for partition in [Leaf(), coarse]:
            self.assertFault(TooWeak, QUADRATIC, Enclosure(partition))

    def test_partitions_are_bounded_in_depth(self):
        chain = Leaf()
        for k in range(65, 0, -1):
            chain = split(F(1, 2 ** k), chain)
        self.assertFault(Invalid, QUADRATIC, Enclosure(chain))


def hook(p=F(3, 10), random=(RandomVar("x", Sym("Lo"), Sym("Hi")),)) -> Statement:
    """P(X > C) for X on [Lo, Hi] = [0, 40] with mean M = 10 and C in [36, 40]. Markov's
    g = x/36 dominates the indicator and gives 10/36 = 5/18."""
    goal = MomentBound(random=random, moments=(MomentConstraint(Sym("x"), Sym("M"), Sym("M")),), fail=Add((Sym("x"), Neg(Sym("C")))), p=p)
    return Statement(hyps=(hyp("C", 36, 40), hyp("Hi", 40), hyp("Lo", 0), hyp("M", 10)), goal=goal)


def dual(*y, partition=Split("x", F(36), Leaf(), Leaf())) -> MomentDual:
    return MomentDual(y0=F(0), y=tuple(map(F, y)), partition=partition)


class Moments(RuleCase):
    def test_markov_proves_the_hook(self):
        self.assertTheorem(hook(), dual(F(1, 36)))

    def test_domination_and_the_bound_are_both_checked(self):
        self.assertFault(TooWeak, hook(), dual(F(1, 36), partition=Leaf()))
        self.assertFault(TooWeak, hook(), dual(0))
        self.assertFault(TooWeak, hook(p=F(1, 4)), dual(F(1, 36)))

    def test_malformed_duals_are_invalid(self):
        self.assertFault(Invalid, hook(), dual())
        self.assertFault(Invalid, hook(), dual(F(1, 36), partition=Split("x", F(40), Leaf(), Leaf())))
        x = RandomVar("x", Sym("Lo"), Sym("Hi"))
        self.assertFault(Invalid, hook(random=(x, x)), dual(F(1, 36)))


def trials(n, k=0, eps=F(1, 100), beta=F(1, 20)) -> Statement:
    """0.99^298 = 0.05004 > 1/20 > 0.99^299 = 0.04954."""
    return Statement(hyps=(), goal=BinomialTail(n=c(n), k=c(k), eps=c(eps), beta=c(beta)))


def counted(n_hi) -> Statement:
    return Statement(hyps=(hyp("n", 299, n_hi),), goal=BinomialTail(n=Sym("n"), k=c(0), eps=c(F(1, 100)), beta=c(F(1, 20))))


class BinomialTails(RuleCase):
    def test_the_tail_is_exact(self):
        self.assertEqual(tail(10, 1, F(1, 2)), F(11, 1024), "(1 + 10) / 2^10")
        self.assertEqual(tail(3, 3, F(1, 3)), F(1), "the whole binomial sum")

    def test_enough_trials_prove_the_bound(self):
        for n in (299, 300):
            self.assertTheorem(trials(n), Arithmetic())
        self.assertFault(TooWeak, trials(298), Arithmetic())

    def test_observed_failures_enter_the_tail(self):
        self.assertTheorem(trials(10, k=1, eps=F(1, 2), beta=F(11, 1024)), Arithmetic())
        self.assertFault(TooWeak, trials(10, k=1, eps=F(1, 2), beta=F(1, 100)), Arithmetic())

    def test_parameters_must_be_exact_and_in_range(self):
        for st in [trials(300, eps=0), trials(300, eps=1), trials(300, beta=1), trials(10, k=11), trials(F(5, 2)), counted(300)]:
            self.assertFault(Invalid, st, Arithmetic())
        self.assertTheorem(counted(299), Arithmetic())


if __name__ == "__main__":
    unittest.main()
