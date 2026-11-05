"""Verdict construction rules. Owner: P. Forgery and laundering live in test_seal.py."""
import unittest
from fractions import Fraction

from lola.kernel import Interval
from lola.kernel.check import _issue_theorem
from lola.models.base import (
    ClaimOrigin,
    FailureMode,
    NeedsCertificate,
    NeedsInputBound,
    NoModel,
    Requirement,
)
from lola.premises import Footprint, Premise, ScopeParam, Tag
from lola.verdict import STATUS, Fail, Open, Pass, Scope, Unknown, Waived
from tests.test_seal import FOOTPRINT, LABEL, OBLIGATION, SCOPE, STATEMENT, genuine_refutation, genuine_theorem

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
        self.assertEqual(set(STATUS.values()), {"PASS", "FAIL", "UNKNOWN"})


if __name__ == "__main__":
    unittest.main()
