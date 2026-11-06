"""Kernel results cannot be forged, copied or altered outside kernel.check. Owner: K.

Each attack either raises or yields a handle that verdict assembly refuses. The genuine
handles come from the kernel-private issuers, which only kernel.check calls in the
product; tests may reach them because tests/ is outside the import-boundary rule.
"""
import copy
import dataclasses
import pickle
import unittest
from fractions import Fraction

from petra.kernel import Const, RangeHyp, Refutation, Statement, Sym, Theorem, is_issued
from petra.kernel.check import _issue_refutation, _issue_theorem
from petra.kernel.rules.r4_enclosure import AllNonpositive
from petra.kernel.terms import Add, Neg
from petra.models.base import ClaimOrigin, FailureMode, ModelSpec, Obligation, Requirement
from petra.premises import Footprint, Premise, Tag
from petra.verdict import Discharged, Fail, Pass, Refuted, Scope

LABEL = "in:d.lift.force"
STATEMENT = Statement(
    hyps=(RangeHyp(sym="f", lo=Fraction(0), hi=Fraction(10), label=LABEL),),
    goal=AllNonpositive(exprs=(Add((Sym("f"), Neg(Const(Fraction(20))))),)),
)
OTHER = Statement(
    hyps=(RangeHyp(sym="f", lo=Fraction(0), hi=Fraction(30), label=LABEL),),
    goal=AllNonpositive(exprs=(Add((Sym("f"), Neg(Const(Fraction(20))))),)),
)
FOOTPRINT = Footprint((Premise(LABEL, Tag.ASSUMED, "owner@example.org", "brief", "f in [0, 10] N"),))
SCOPE = Scope(params=(), load_cases=("lift",), environment=None)
MODEL = ModelSpec("test.model", "form", "validity", "owner@example.org", "textbook", "0" * 16)
OBLIGATION = Obligation(
    requirement=Requirement(subject=("d",), mode=FailureMode("test.mode"), criterion=None, origin=ClaimOrigin("c")),
    statement=STATEMENT,
    model=MODEL,
    describe="f stays below 20",
)


def genuine_theorem(statement: Statement = STATEMENT) -> Theorem:
    return _issue_theorem(statement, "sha256:s", "sha256:e", "R4", frozenset({LABEL}), ())


def genuine_refutation(statement: Statement = STATEMENT) -> Refutation:
    return _issue_refutation(statement, "sha256:s", "sha256:e", "R4", frozenset({LABEL}), (("f", Fraction(10)),))


class Controls(unittest.TestCase):
    def test_genuine_results_are_accepted(self):
        t, r = genuine_theorem(), genuine_refutation()
        self.assertTrue(is_issued(t) and is_issued(r))
        Pass(SCOPE, FOOTPRINT, (t,))
        Discharged(OBLIGATION, t, "test")
        Refuted(OBLIGATION, r, "test")
        Fail(OBLIGATION, r, FOOTPRINT)


class Forgery(unittest.TestCase):
    def test_constructors_raise(self):
        with self.assertRaises(TypeError):
            Theorem()
        with self.assertRaises(TypeError):
            Refutation(STATEMENT)

    def test_object_new_gives_a_handle_verdicts_refuse(self):
        forged = object.__new__(Theorem)
        self.assertFalse(is_issued(forged))
        with self.assertRaises(TypeError):
            forged.statement
        with self.assertRaises(TypeError):
            Pass(SCOPE, FOOTPRINT, (forged,))
        with self.assertRaises(TypeError):
            Discharged(OBLIGATION, forged, "test")
        forged_r = object.__new__(Refutation)
        with self.assertRaises(TypeError):
            Fail(OBLIGATION, forged_r, FOOTPRINT)

    def test_subclass_handles_are_refused(self):
        class Fake(Theorem):
            __slots__ = ()

        forged = object.__new__(Fake)
        self.assertFalse(is_issued(forged))
        with self.assertRaises(TypeError):
            Pass(SCOPE, FOOTPRINT, (forged,))

    def test_a_theorem_is_not_a_refutation(self):
        with self.assertRaises(TypeError):
            Fail(OBLIGATION, genuine_theorem(), FOOTPRINT)


class Laundering(unittest.TestCase):
    def test_dataclasses_replace_raises(self):
        for result in (genuine_theorem(), genuine_refutation()):
            with self.assertRaises(TypeError):
                dataclasses.replace(result, statement=OTHER)

    def test_copy_deepcopy_and_pickle_raise(self):
        for result in (genuine_theorem(), genuine_refutation()):
            for attack in (copy.copy, copy.deepcopy, pickle.dumps):
                with self.assertRaises(TypeError, msg=attack.__name__):
                    attack(result)

    def test_assignment_raises_and_changes_nothing(self):
        t = genuine_theorem()
        with self.assertRaises(AttributeError):
            t.statement = OTHER
        with self.assertRaises(AttributeError):
            t.rule = "R1"
        with self.assertRaises(AttributeError):
            object.__setattr__(t, "statement", OTHER)
        with self.assertRaises(AttributeError):
            object.__setattr__(t, "smuggled", OTHER)
        with self.assertRaises(AttributeError):
            del t.rule
        self.assertEqual(t.statement, STATEMENT)
        self.assertEqual(t.rule, "R4")
        r = genuine_refutation()
        with self.assertRaises(AttributeError):
            r.point = (("f", Fraction(10)),)

    def test_a_result_for_another_statement_is_refused(self):
        with self.assertRaises(ValueError):
            Discharged(OBLIGATION, genuine_theorem(OTHER), "test")
        with self.assertRaises(ValueError):
            Fail(OBLIGATION, genuine_refutation(OTHER), FOOTPRINT)


if __name__ == "__main__":
    unittest.main()
