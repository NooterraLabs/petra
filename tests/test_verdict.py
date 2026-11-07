"""Verdict construction, assembly, JSON and rendering. Owner: P. Forgery and laundering
live in test_seal.py.

kernel.check is not implemented in this seam's tree, so kernel results come from the
kernel-private issuers, as in test_seal.py."""
import json
import unittest
from fractions import Fraction

from petra.coverage import table_premise
from petra.kernel import Add, Const, Interval, Invalid, Neg, RangeHyp, Rejection, Statement, Sym
from petra.kernel.check import _issue_refutation, _issue_theorem
from petra.kernel.rules.r4_enclosure import AllNonpositive
from petra.models.base import (
    GALVANIC_CORROSION,
    CertificateRejected,
    CertificateTooWeak,
    ClaimOrigin,
    CoverageOrigin,
    FailureMode,
    Gap,
    InputContradicted,
    NeedsCertificate,
    NeedsInputBound,
    NoModel,
    NoRuleForQuantity,
    Obligation,
    RegistryInconsistent,
    Requirement,
)
from petra.premises import Footprint, Premise, PremiseBook, RangeMismatch, ScopeParam, Tag, UnresolvedLabel
from petra.verdict import (
    COVERAGE_ENTRY,
    STATUS,
    ClaimVerdict,
    Discharged,
    Fail,
    Open,
    Pass,
    Refuted,
    Scope,
    Unknown,
    Waived,
    assemble,
    describe_need,
    entries,
    open_from_gap,
    render,
    verdict_json,
)
from tests.test_seal import FOOTPRINT, LABEL, MODEL, OBLIGATION, SCOPE, STATEMENT, genuine_refutation, genuine_theorem

MODE = FailureMode("test.mode")
REQ = Requirement(subject=("d",), mode=MODE, criterion=None, origin=ClaimOrigin("c"))
OPEN = Open(REQ, (NoModel(MODE, ("d",)),))


class Passes(unittest.TestCase):
    def test_needs_a_scope_a_footprint_and_theorems(self):
        t = genuine_theorem()
        with self.assertRaises(TypeError):
            Pass(None, FOOTPRINT, (t,))
        with self.assertRaises(TypeError):
            Pass(SCOPE, (), (t,))
        with self.assertRaises(ValueError):
            Pass(SCOPE, FOOTPRINT, ())
        with self.assertRaises(TypeError):
            Pass(SCOPE, FOOTPRINT, [t])

    def test_every_theorem_label_resolves(self):
        stray = _issue_theorem(STATEMENT, "sha256:s", "sha256:e", "R4", frozenset({"reg:steel.S355.fy"}), ())
        with self.assertRaises(ValueError):
            Pass(SCOPE, FOOTPRINT, (stray,))
        param = _issue_theorem(STATEMENT, "sha256:s", "sha256:e", "R4", frozenset({LABEL, "par:d.length"}), ())
        with self.assertRaises(ValueError):
            Pass(SCOPE, FOOTPRINT, (param,))
        scoped = Scope((ScopeParam("par:d.length", "length", Interval(Fraction(1), Fraction(2)), "m"),), ("lift",), None)
        Pass(scoped, FOOTPRINT, (param,))
        drawn = _issue_theorem(STATEMENT, "sha256:s", "sha256:e", "R4", frozenset({LABEL, "dsg:d.frame.A.x"}), ())
        Pass(SCOPE, FOOTPRINT, (drawn,))


class Unknowns(unittest.TestCase):
    def test_needs_an_open_item(self):
        Unknown((OPEN,), FOOTPRINT)
        with self.assertRaises(ValueError):
            Unknown((), FOOTPRINT)
        with self.assertRaises(TypeError):
            Unknown(("needs a certificate",), FOOTPRINT)

    def test_open_items_name_typed_needs(self):
        Open(REQ, (NeedsInputBound(("site",), "fault_current", "A"), NeedsCertificate("sha256:s", "R4", "f <= 20")))
        with self.assertRaises(ValueError):
            Open(REQ, ())
        with self.assertRaises(TypeError):
            Open(REQ, ("a signed bound on the fault current",))

    def test_progress_theorems_must_be_issued(self):
        Unknown((OPEN,), FOOTPRINT, (genuine_theorem(),))
        with self.assertRaises(TypeError):
            Unknown((OPEN,), FOOTPRINT, (object(),))


class Others(unittest.TestCase):
    def test_waiver_premise_is_a_waiver(self):
        Waived(REQ, Premise("waive:d.test.mode.d", Tag.JUDGED, "o@example.org", "calc C-14", "checked by hand"))
        with self.assertRaises(ValueError):
            Waived(REQ, Premise("cov:0123", Tag.JUDGED, "o@example.org", "s", "table"))

    def test_fail_footprint_covers_the_refuted_statement(self):
        other = Footprint((Premise("cov:0123", Tag.JUDGED, "o@example.org", "s", "table"),))
        with self.assertRaises(ValueError):
            Fail(OBLIGATION, genuine_refutation(), other)

    def test_status_names(self):
        self.assertEqual(set(STATUS.values()), {"PASS", "FAIL", "UNKNOWN", "MARGINAL"})


def interval(lo: int, hi: int) -> Interval:
    return Interval(Fraction(lo), Fraction(hi))


def load_premise(lo: int = 0, hi: int = 10) -> Premise:
    return Premise(LABEL, Tag.ASSUMED, "owner@example.org", "brief", "f in the signed range", interval(lo, hi), "N")


MOMENT = "in:d.lift.moment"
MOMENT_PREMISE = Premise(MOMENT, Tag.ASSUMED, "owner@example.org", "brief", "m in the signed range", interval(0, 5), "N m")
ARM_STATEMENT = Statement(
    hyps=(RangeHyp(sym="m", lo=Fraction(0), hi=Fraction(5), label=MOMENT),),
    goal=AllNonpositive(exprs=(Add((Sym("m"), Neg(Const(Fraction(20))))),)),
)
ARM = Obligation(Requirement(("d", "arm"), MODE, None, CoverageOrigin("test.rule")), ARM_STATEMENT, MODEL, "m stays below 20")
COVERAGE_OPEN = Open(Requirement(("d", "arm"), GALVANIC_CORROSION, None, CoverageOrigin("galvanic.contact")), (NoModel(GALVANIC_CORROSION, ("d", "arm")),))
WAIVER = Premise("waive:d.test.mode.d.arm", Tag.JUDGED, "m.engineer@example.org", "t.petra:40", "checked by hand")
WAIVED = Waived(ARM.requirement, WAIVER)
MODEL_LABEL = "model:test.model@0000000000000000"


def book(*premises: Premise) -> PremiseBook:
    return PremiseBook(premises or (load_premise(), MOMENT_PREMISE), [], [])


def proved() -> Discharged:
    return Discharged(OBLIGATION, genuine_theorem(), "solver:r4_enclosure")


def arm_proved() -> Discharged:
    return Discharged(ARM, _issue_theorem(ARM_STATEMENT, "sha256:m", "sha256:e", "R1", frozenset({MOMENT}), ()), "certs")


def refuted() -> Refuted:
    return Refuted(OBLIGATION, genuine_refutation(), "solver:r4_enclosure")


def arm_refuted() -> Refuted:
    return Refuted(ARM, _issue_refutation(ARM_STATEMENT, "sha256:m", "sha256:e", "R4", frozenset({MOMENT}), (("m", Fraction(5)),)), "certs")


class Assembly(unittest.TestCase):
    def test_a_pass_rests_on_its_theorems_models_the_table_and_certificates(self):
        v = assemble((proved(),), book(), SCOPE)
        self.assertIsInstance(v, Pass)
        self.assertIs(v.scope, SCOPE)
        self.assertEqual(v.footprint.labels, {LABEL, MODEL_LABEL, table_premise().label, "cert:sha256:s"})
        self.assertEqual({p.tag for p in v.footprint.premises}, {Tag.ASSUMED, Tag.VALIDATED_MODEL, Tag.JUDGED, Tag.CERTIFIED})

    def test_waivers_join_the_footprint(self):
        v = assemble((proved(), WAIVED), book(), SCOPE)
        self.assertIsInstance(v, Pass)
        self.assertIn(WAIVER.label, v.footprint.labels)

    def test_an_open_item_makes_unknown_and_keeps_progress(self):
        t = proved()
        v = assemble((t, OPEN), book(), SCOPE)
        self.assertIsInstance(v, Unknown)
        self.assertEqual(v.open, (OPEN,))
        self.assertEqual(v.theorems, (t.theorem,))
        self.assertIn(LABEL, v.footprint.labels)

    def test_a_refutation_fails_whatever_else_is_open(self):
        v = assemble((arm_proved(), refuted(), OPEN), book(), SCOPE)
        self.assertIsInstance(v, Fail)
        self.assertEqual(v.footprint.labels, {LABEL, MODEL_LABEL, table_premise().label, "cert:sha256:s"})
        self.assertNotIn(MOMENT, v.footprint.labels, "a counterexample rests only on its own statement")

    def test_the_first_refutation_by_requirement_id_is_reported(self):
        self.assertLess(ARM.requirement.id, OBLIGATION.requirement.id)
        for outcomes in ((refuted(), arm_refuted()), (arm_refuted(), refuted())):
            self.assertIs(assemble(outcomes, book(), SCOPE).obligation, ARM)

    def test_a_premise_range_must_lie_inside_its_hypothesis(self):
        self.assertIsInstance(assemble((proved(),), book(load_premise(2, 8)), SCOPE), Pass)
        with self.assertRaises(RangeMismatch):
            assemble((proved(),), book(load_premise(0, 20)), SCOPE)

    def test_a_counterexample_must_be_a_point_the_premises_admit(self):
        self.assertIsInstance(assemble((refuted(),), book(load_premise(0, 10)), SCOPE), Fail)
        with self.assertRaises(RangeMismatch):
            assemble((refuted(),), book(load_premise(0, 5)), SCOPE)

    def test_every_label_must_resolve(self):
        with self.assertRaises(UnresolvedLabel):
            assemble((proved(),), book(MOMENT_PREMISE), SCOPE)

    def test_only_outcomes_are_assembled(self):
        for stray in (genuine_theorem(), Rejection("sha256:s", "R4", Invalid("tampered"))):
            with self.assertRaises(TypeError):
                assemble((proved(), stray), book(), SCOPE)

    def test_waivers_alone_prove_nothing(self):
        with self.assertRaises(ValueError):
            assemble((WAIVED,), book(), SCOPE)


class Entries(unittest.TestCase):
    def test_claims_in_order_then_coverage(self):
        b = Open(Requirement(("d",), MODE, None, ClaimOrigin("b")), (NoModel(MODE, ("d",)),))
        c = proved()
        result = entries((b, c, COVERAGE_OPEN, b), book(), SCOPE)
        self.assertEqual([e.claim for e in result], ["b", "c", COVERAGE_ENTRY])
        self.assertEqual([e.outcomes for e in result], [(b, b), (c,), (COVERAGE_OPEN,)])
        self.assertEqual([STATUS[type(e.verdict)] for e in result], ["UNKNOWN", "PASS", "UNKNOWN"])

    def test_a_coverage_entry_needs_something_besides_waivers(self):
        self.assertEqual([e.claim for e in entries((proved(), WAIVED), book(), SCOPE)], ["c"])
        self.assertEqual([e.claim for e in entries((proved(),), book(), SCOPE)], ["c"])
        self.assertEqual([e.claim for e in entries((proved(), WAIVED, arm_proved()), book(), SCOPE)], ["c", COVERAGE_ENTRY])

    def test_open_from_gap_keeps_the_gaps_needs(self):
        needs = (NeedsInputBound(("site",), "fault_current", "A"),)
        self.assertEqual(open_from_gap(Gap(REQ, needs)), Open(REQ, needs))
        with self.assertRaises(ValueError):
            open_from_gap(Gap(REQ, ()))


class Json(unittest.TestCase):
    def entry(self, *outcomes) -> ClaimVerdict:
        (only,) = entries(outcomes, book(), SCOPE)
        return only

    def test_a_pass_entry(self):
        data = verdict_json(self.entry(proved()))
        self.assertEqual(data["claim"], "c")
        self.assertEqual(data["status"], "PASS")
        self.assertEqual(data["rules"], ["R4"])
        self.assertEqual(data["needs"], [])
        self.assertIn({"tag": "assumed", "label": LABEL, "owner": "owner@example.org", "source": "brief"}, data["footprint"])
        self.assertEqual(len(data["footprint"]), 4)
        json.dumps(data)

    def test_an_unknown_entry_names_what_it_needs(self):
        data = verdict_json(self.entry(proved(), OPEN))
        self.assertEqual(data["status"], "UNKNOWN")
        self.assertEqual(data["needs"], [describe_need(NoModel(MODE, ("d",)))])
        self.assertEqual(data["rules"], ["R4"])

    def test_a_fail_entry(self):
        data = verdict_json(self.entry(refuted()))
        self.assertEqual((data["status"], data["rules"], data["needs"]), ("FAIL", ["R4"], []))
        self.assertIn(LABEL, [p["label"] for p in data["footprint"]])

    def test_rules_list_each_rule_once_sorted(self):
        whole = ClaimVerdict("all", assemble((proved(), arm_proved(), proved()), book(), SCOPE), ())
        self.assertEqual(verdict_json(whole)["rules"], ["R1", "R4"])


class Needs(unittest.TestCase):
    def test_the_documented_lines(self):
        self.assertEqual(describe_need(NeedsInputBound(("site",), "fault_current", "A")), "signed bound on site.fault_current [A]")
        self.assertTrue(
            describe_need(NoModel(GALVANIC_CORROSION, ("bracket",))).startswith(
                "no model for corrosion.galvanic on bracket: waive corrosion.galvanic on bracket by "
            )
        )

    def test_every_need_names_what_would_close_it(self):
        cases = {
            NeedsCertificate("sha256:ab", "R4", "f stays below 20"): ("R4", "sha256:ab", "f stays below 20"),
            CertificateRejected("sha256:ab", "R1", "certs", "A x != b"): ("certs", "sha256:ab", "R1", "A x != b"),
            CertificateTooWeak("sha256:ab", None, "library", "leaf crosses 0"): ("library", "sha256:ab", "leaf crosses 0"),
            NoRuleForQuantity("frame.stability_factor", "indeterminate truss"): ("frame.stability_factor", "indeterminate truss"),
            InputContradicted(("hook",), "capacity", "N", "tests proof", "1 of 500 parts broke at 30 kN"): ("hook.capacity", "tests proof", "30 kN"),
            RegistryInconsistent("cable.cu_pvc_2_5", "R20 = rho20 / A", "off by 3 %"): ("cable.cu_pvc_2_5", "R20 = rho20 / A", "off by 3 %"),
        }
        for need, parts in cases.items():
            line = describe_need(need)
            for part in parts:
                self.assertIn(part, line, type(need).__name__)

    def test_a_bare_string_is_not_a_need(self):
        with self.assertRaises(TypeError):
            describe_need("needs a certificate")


class Rendering(unittest.TestCase):
    def test_a_pass_shows_scope_obligations_and_footprint(self):
        outcomes = (proved(),)
        text = render(assemble(outcomes, book(), SCOPE), outcomes)
        self.assertEqual(text.splitlines()[0], "PASS")
        for part in ("load cases lift", "environment undeclared", "certified", "solver:r4_enclosure", LABEL, MODEL_LABEL, table_premise().label):
            self.assertIn(part, text)

    def test_an_unknown_shows_what_each_open_item_needs(self):
        outcomes = (proved(), OPEN)
        text = render(assemble(outcomes, book(), SCOPE), outcomes)
        self.assertEqual(text.splitlines()[0], "UNKNOWN")
        self.assertIn(OPEN.requirement.id, text)
        self.assertIn(f"needs {describe_need(OPEN.needs[0])}", text)

    def test_a_fail_shows_the_counterexample(self):
        outcomes = (refuted(),)
        text = render(assemble(outcomes, book(), SCOPE), outcomes)
        self.assertEqual(text.splitlines()[0], "FAIL")
        self.assertIn("counterexample", text)
        self.assertIn(f"f = 10 N   ({LABEL})", text)


if __name__ == "__main__":
    unittest.main()
