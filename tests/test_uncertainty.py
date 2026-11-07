"""Uncertain loads: the demand lowerer, the R5 moment bound and the R6 scenario bound,
through the elaborator, the solvers and kernel.check. Owner: U.

Hand values. The hook's force X lies in [0, 40] kN with mean m, and its capacity C in
[C_lo, 40] kN. For any capacity c, Markov gives P(X > u c) <= m / (u c), and a two-point
law with mass m / (u c) just above u c and the rest at 0 attains it. The weakest capacity
C_lo decides, so the sharp bound is m / (u C_lo):
    m = 10 kN, C_lo = 36 kN, u = 1:     10/36 = 5/18 = 0.27778
        holds for p = 3/10 and 7/25 = 0.28; fails for p = 11/40 = 0.275 and 1/5
    u = 9/10:                           10/32.4 = 0.30864, fails 3/10, holds 8/25 = 0.32
    m = 12 kN:                          12/36 = 0.33333, fails 3/10
    C_lo = 30 kN:                       10/30 = 0.33333, fails 3/10
    the Markov dual g(x) = x / 36 kN, split at x = 36 kN, gives E[g] = 10/36
Binomial tails at eps = 1/100, with ln 0.99 = -0.0100503:
    0 failures:  0.99^300 = 0.04904 and 0.99^299 = 0.04954 are <= 0.05;  0.99^298 = 0.05004 is not
    1 failure in 300:  0.99^300 + 300 (0.01) 0.99^299 = 0.04904 + 0.14862 = 0.19766 > 0.05
    confidence 90 %:  0.99^230 = 0.09911 <= 0.1;  0.99^229 = 0.10011 > 0.1
"""
import unittest
from fractions import Fraction as F
from pathlib import Path

from petra import coverage
from petra.ir import Input, InputKind, Signature
from petra.kernel import Const, Evidence, Leaf, RangeHyp, Rejection, Split, Theorem, TooWeak, check
from petra.kernel.rules.r5_moment import MomentDual
from petra.kernel.rules.r6_scenario import Arithmetic
from petra.lang import load_design, parse_design
from petra.models import uncertainty
from petra.models.base import ComponentError, Gap, InputContradicted, NeedsInputBound, NoRuleForQuantity, Obligation
from petra.pipeline import check_design, elaborate, lower_components
from petra.premises import Tag
from petra.registry import build_registry
from petra.solvers import SolverSource, r5_moment, r6_scenario
from petra.units import FORCE
from petra.verdict import Pass, Unknown, describe_need

REGISTRY = build_registry()
EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "hook_uncertain.petra"
CANARY = Path(__file__).resolve().parents[1] / "judges" / "canaries" / "demand_failed_below_capacity.petra"
DESIGN = "hoist-hook"
OVERLOAD = "<= 3/10 under lift"
TRIALS = "trials 300 failures 0"
MARKOV = MomentDual(F(0), (F(1, 36000),), Split("hook.force", F(36000), Leaf(), Leaf()))


def hook(*edits: tuple[str, str], extra: str = ""):
    text = EXAMPLE.read_text(encoding="utf-8")
    for old, new in edits:
        if old not in text:
            raise AssertionError(f"{old!r} is not in hook_uncertain.petra")
        text = text.replace(old, new)
    return parse_design(text + extra, "hook.petra", REGISTRY)


def elaborated(design, claim: str):
    lowered = lower_components(design, REGISTRY)
    (item,) = [e for e in elaborate(design, lowered, coverage.generate(design, lowered, REGISTRY), REGISTRY)
               if e.requirement.origin.claim == claim]
    return item


def verdicts(test: unittest.TestCase, design) -> dict:
    report = check_design(design, REGISTRY, (SolverSource(),))
    test.assertEqual(report.warnings, (), "no source failed")
    return {e.claim: e.verdict for e in report.entries}


def proved(statement, solver) -> bool:
    return any(isinstance(check(statement, e), Theorem) for e in solver.solve(statement))


def label(name: str) -> str:
    return f"in:{DESIGN}.{name}"


class HookExample(unittest.TestCase):
    def test_the_example_passes_on_both_rules(self):
        report = check_design(load_design(EXAMPLE, REGISTRY), REGISTRY, (SolverSource(),))
        self.assertIsInstance(report.verdict, Pass)
        self.assertEqual({e.claim: type(e.verdict) for e in report.entries}, {"overload": Pass, "tested": Pass})
        self.assertEqual({e.claim: {t.rule for t in e.verdict.theorems} for e in report.entries},
                         {"overload": {"R5"}, "tested": {"R6"}})

    def test_the_footprint_names_each_premise_with_its_tag_and_owner(self):
        report = check_design(load_design(EXAMPLE, REGISTRY), REGISTRY, (SolverSource(),))
        found = {p.label: (p.tag, p.owner) for p in report.verdict.footprint.premises if p.tag is not Tag.CERTIFIED}
        self.assertEqual(found, {
            label("hook.capacity"): (Tag.MEASURED, "qa.lab@example.org"),
            label("lift.hook.force"): (Tag.ASSUMED, "ops.lead@example.org"),
            label("lift.hook.force.mean"): (Tag.ASSUMED, "ops.lead@example.org"),
            label("tests.proof.trials"): (Tag.MEASURED, "qa.lab@example.org"),
            label("tests.proof.failures"): (Tag.MEASURED, "qa.lab@example.org"),
            uncertainty.MOMENT_MODEL.premise().label: (Tag.VALIDATED_MODEL, "petra-maintainers"),
            uncertainty.SCENARIO_MODEL.premise().label: (Tag.VALIDATED_MODEL, "petra-maintainers"),
            coverage.table_premise().label: (Tag.JUDGED, "petra-maintainers"),
        })


class RangeAndMean(unittest.TestCase):
    def test_every_premise_enters_as_a_labelled_hypothesis(self):
        ob = elaborated(load_design(EXAMPLE, REGISTRY), "overload")
        self.assertIsInstance(ob, Obligation)
        self.assertEqual(ob.model, uncertainty.MOMENT_MODEL)
        self.assertEqual(ob.statement.hyps, (
            RangeHyp("hook.capacity", F(36000), F(40000), label("hook.capacity")),
            RangeHyp("lift.hook.force", F(0), F(40000), label("lift.hook.force")),
            RangeHyp("lift.hook.force.mean", F(10000), F(10000), label("lift.hook.force.mean")),
        ))
        self.assertEqual(ob.statement.goal.p, F(3, 10), "p is the claim's own number")

    def test_the_markov_dual_proves_the_claim_and_not_a_tighter_one(self):
        self.assertIsInstance(check(elaborated(load_design(EXAMPLE, REGISTRY), "overload").statement, Evidence(MARKOV)), Theorem)
        tight = check(elaborated(hook((OVERLOAD, "<= 1/5 under lift")), "overload").statement, Evidence(MARKOV))
        self.assertIsInstance(tight, Rejection)
        self.assertIsInstance(tight.fault, TooWeak, "E[g] = 5/18 exceeds 1/5")

    def test_the_solver_proves_claims_above_the_sharp_bound_only(self):
        for p, holds in [("3/10", True), ("7/25", True), ("11/40", False), ("1/5", False)]:
            with self.subTest(p=p):
                statement = elaborated(hook((OVERLOAD, f"<= {p} under lift")), "overload").statement
                self.assertEqual(proved(statement, r5_moment), holds)

    def test_a_claim_tighter_than_the_bound_is_unknown_not_pass(self):
        tight = hook((OVERLOAD, "<= 1/5 under lift"))
        self.assertEqual(tuple(r5_moment.solve(elaborated(tight, "overload").statement)), (), "no evidence that cannot check")
        self.assertIsInstance(verdicts(self, tight)["overload"], Unknown)
        self.assertIsInstance(verdicts(self, hook((OVERLOAD, "<= 7/25 under lift")))["overload"], Pass)

    def test_the_threshold_scales_the_capacity(self):
        lower = ("utilisation > 1)", "utilisation > 9/10)")
        self.assertIsInstance(verdicts(self, hook(lower))["overload"], Unknown)
        self.assertIsInstance(verdicts(self, hook(lower, (OVERLOAD, "<= 8/25 under lift")))["overload"], Pass)

    def test_the_bound_rests_on_the_signed_mean_and_the_lowest_capacity(self):
        for edit in [("mean 10 kN", "mean 12 kN"), ("capacity in [36 kN", "capacity in [30 kN")]:
            with self.subTest(edit=edit[1]):
                self.assertIsInstance(verdicts(self, hook(edit))["overload"], Unknown)
        self.assertIsInstance(verdicts(self, hook(("mean 10 kN", "mean 21/2 kN")))["overload"], Pass, "10.5/36 = 0.2917")

    def test_a_load_without_a_signed_mean_is_a_gap_naming_it(self):
        gap = elaborated(hook((" mean 10 kN", "")), "overload")
        self.assertIsInstance(gap, Gap)
        self.assertEqual(gap.needs, (NeedsInputBound(("lift", "hook"), "force.mean", "N"),))
        self.assertIsInstance(verdicts(self, hook((" mean 10 kN", "")))["overload"], Unknown)

    def test_a_load_case_without_a_force_on_the_demand_is_a_gap(self):
        latch = 'demand latch {\n  capacity in [5 kN, 6 kN] measured "qa.lab@example.org" source "PL-0918"\n}\n'
        gap = elaborated(hook(extra=latch + "claim latched: P(latch.utilisation > 1) <= 1/10 under lift\n"), "latched")
        self.assertEqual(gap.needs, (NeedsInputBound(("lift", "latch"), "force", "N"),))


class TestsAgainstCapacity(unittest.TestCase):
    """A part that broke at L held at most L, so a failure below C_lo refutes the signed capacity."""

    def test_a_failure_below_the_capacity_refutes_it_and_the_bound_stays_open(self):
        design = hook(("trials 300 failures 0 at 36 kN", "trials 500 failures 1 at 30 kN"))
        gap = elaborated(design, "overload")
        self.assertIsInstance(gap, Gap)
        (need,) = gap.needs
        self.assertIsInstance(need, InputContradicted)
        self.assertEqual((need.target, need.field, need.record), (("hook",), "capacity", "tests proof"))
        line = describe_need(need)
        for part in ("hook.capacity", "tests proof", "30 kN", "36 kN"):
            self.assertIn(part, line)
        self.assertIsInstance(verdicts(self, design)["overload"], Unknown)

    def test_a_failure_at_the_capacity_or_a_clean_test_below_it_refutes_nothing(self):
        for edit in ("trials 300 failures 1 at 36 kN", "trials 300 failures 0 at 30 kN"):
            with self.subTest(tests=edit):
                design = hook(("trials 300 failures 0 at 36 kN", edit))
                self.assertIsInstance(elaborated(design, "overload"), Obligation)
                self.assertIsInstance(verdicts(self, design)["overload"], Pass)

    def test_a_refuted_capacity_and_a_missing_mean_are_both_named(self):
        gap = elaborated(hook(("trials 300 failures 0 at 36 kN", "trials 500 failures 1 at 30 kN"), (" mean 10 kN", "")), "overload")
        self.assertEqual([type(n) for n in gap.needs], [InputContradicted, NeedsInputBound])

    def test_the_canary_with_a_failure_below_its_capacity_is_refused_on_its_overload_claim(self):
        report = check_design(load_design(CANARY, REGISTRY), REGISTRY, (SolverSource(),))
        self.assertIsInstance(report.verdict, Unknown)
        (item,) = report.verdict.open
        self.assertEqual(item.requirement.id, "hook/uncertain.range_mean/claim.overload")
        self.assertEqual([type(n) for n in item.needs], [InputContradicted])


class FromTests(unittest.TestCase):
    def test_the_statement_is_the_binomial_tail_of_the_signed_record(self):
        ob = elaborated(load_design(EXAMPLE, REGISTRY), "tested")
        self.assertEqual(ob.model, uncertainty.SCENARIO_MODEL)
        self.assertEqual(ob.statement.hyps, (
            RangeHyp("tests.proof.failures", F(0), F(0), label("tests.proof.failures")),
            RangeHyp("tests.proof.trials", F(300), F(300), label("tests.proof.trials")),
        ))
        self.assertEqual((ob.statement.goal.eps, ob.statement.goal.beta), (Const(F(1, 100)), Const(F(1, 20))))

    def test_enough_failure_free_trials_prove_the_claim_and_fewer_do_not(self):
        for n, holds in [(300, True), (299, True), (298, False)]:
            with self.subTest(trials=n):
                statement = elaborated(hook((TRIALS, f"trials {n} failures 0")), "tested").statement
                self.assertEqual(proved(statement, r6_scenario), holds)

    def test_trials_that_do_not_support_the_claim_get_no_theorem(self):
        design = hook((TRIALS, "trials 300 failures 1"))
        statement = elaborated(design, "tested").statement
        exact = check(statement, Evidence(Arithmetic()))
        self.assertIsInstance(exact, Rejection)
        self.assertIsInstance(exact.fault, TooWeak, "the tail 0.198 exceeds 0.05")
        self.assertEqual(tuple(r6_scenario.solve(statement)), (), "the float tail already shows the claim unsupported")
        self.assertIsInstance(verdicts(self, design)["tested"], Unknown)
        example = load_design(EXAMPLE, REGISTRY)
        self.assertEqual(tuple(r6_scenario.solve(elaborated(example, "tested").statement)), (Evidence(Arithmetic()),))
        self.assertIsInstance(verdicts(self, example)["tested"], Pass)

    def test_the_confidence_sets_beta(self):
        for n, holds in [(230, True), (229, False)]:
            with self.subTest(trials=n):
                design = hook((TRIALS, f"trials {n} failures 0"), ("confidence 95 %", "confidence 90 %"))
                self.assertEqual(proved(elaborated(design, "tested").statement, r6_scenario), holds)

    def test_a_level_above_the_tested_level_is_a_gap(self):
        above = elaborated(hook(("fail hook at 36 kN", "fail hook at 40 kN")), "tested")
        self.assertIsInstance(above, Gap)
        self.assertEqual([type(n) for n in above.needs], [NoRuleForQuantity])
        below = elaborated(hook(("fail hook at 36 kN", "fail hook at 30 kN")), "tested")
        self.assertTrue(proved(below.statement, r6_scenario), "a test at 36 kN covers a claim at 30 kN")


class Lowering(unittest.TestCase):
    def test_the_demand_keeps_its_signed_capacity(self):
        demand = lower_components(load_design(EXAMPLE, REGISTRY), REGISTRY)["hook"]
        capacity = demand.capacity
        self.assertIsInstance(capacity, Input)
        self.assertEqual((capacity.name, capacity.range.value.lo, capacity.range.value.hi, capacity.range.dim, capacity.kind),
                         ("hook.capacity", F(36000), F(40000), FORCE, InputKind.MEASURED))
        self.assertEqual(capacity.signature, Signature("qa.lab@example.org", "proof-load report PL-0917, minimum of 12 samples"))

    def test_malformed_demands_and_references_are_component_errors(self):
        capacity = 'capacity in [36 kN, 40 kN] measured "qa.lab@example.org" source "proof-load report PL-0917, minimum of 12 samples"'
        cases = {
            "missing capacity": [(capacity, "")],
            "repeated capacity": [(capacity, capacity + "\n  " + capacity)],
            "unknown attribute": [(capacity, capacity + "\n  " + capacity.replace("capacity", "strength"))],
            "capacity not a force": [("capacity in [36 kN, 40 kN]", "capacity in [36 m, 40 m]")],
            "capacity not positive": [("capacity in [36 kN", "capacity in [0 kN")],
            "load field not force": [("on hook force", "on hook pull")],
            "qoi not utilisation": [("P(hook.utilisation > 1)", "P(hook.stress > 1)")],
            "threshold not a fraction": [("P(hook.utilisation > 1)", "P(hook.utilisation > 1 kN)")],
            "tests not on the demand itself": [("on hook trials", "on hook.eye trials")],
        }
        designs = {what: hook(*edits) for what, edits in cases.items()}
        designs["ordinary claim"] = hook(extra="claim plain: hook.utilisation <= 1 under lift\n")
        for what, design in designs.items():
            with self.subTest(what), self.assertRaises(ComponentError):
                lower_components(design, REGISTRY)


if __name__ == "__main__":
    unittest.main()
