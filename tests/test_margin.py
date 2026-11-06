"""Claims with a margin: the syntax, the tightened statement, and the MARGINAL verdict.

The pipeline cases run on the gadget domain of test_pipeline.py, whose claim reads
F - u * C <= 0 for a load F, a capacity C in [20 kN, 25 kN] and the claimed bound u. With
u = 1/2 and margin 1/10 the margin statement is F - 2/5 * C <= 0, so at the worst corner
(C = 20 kN) a load up to 8 kN keeps slack beyond the margin, a load in (8 kN, 10 kN] is
within the margin, and a load above 10 kN refutes the claim.
"""
import contextlib
import dataclasses
import io
import json
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType
from unittest import mock

from petra import cli, coverage, models
from petra.certs import CertStore
from petra.ir import Rel
from petra.kernel import Add, Const, Mul, Neg, RangeHyp, Refutation, Rejection, Statement, Sym, check, statement_hash
from petra.kernel.check import _issue_refutation, _issue_theorem
from petra.kernel.rules.r4_enclosure import AllNonpositive, PointWitness
from petra.lang import LoweringError, parse_design
from petra.models.base import ClaimOrigin, Criterion, NeedsCertificate, NoRuleForQuantity
from petra.pipeline import explain
from petra.premises import PremiseBook
from petra.solvers import SolverSource
from petra.units import DIMENSIONLESS, TEMPERATURE, Quantity
from petra.verdict import Discharged, Fail, Marginal, Open, Pass, Scope, Unknown, WithinMargin, assemble, verdict_json
from tests.test_pipeline import CAPACITY, GADGET, REGISTRY, STRENGTH, WAIVE_WEAR, GadgetDomain, Solver, build_strength, gadget, point, push
from tests.test_seal import FOOTPRINT

ROOT = Path(__file__).resolve().parent.parent
FITS = "claim fits: g.utilisation <= 1/2 margin 1/10 under push\n"


class Witnesses(Solver):
    """The test solver without its proofs: corner counterexamples only."""

    name = "witnesses"

    def offer(self, statement, digest):
        return (e for e in super().offer(statement, digest) if isinstance(e.body, PointWitness))


class Skipping:
    """Another source with the statements whose hashes are in `skip` withheld."""

    def __init__(self, skip, inner):
        self.name, self.skip, self.inner = inner.name, frozenset(skip), inner

    def offer(self, statement, digest):
        return () if digest in self.skip else self.inner.offer(statement, digest)


def quantity(x, dim=DIMENSIONLESS) -> Quantity:
    return Quantity(point(Fraction(x)), dim)


class Criteria(unittest.TestCase):
    def test_the_bound_moves_inward_by_the_margin(self):
        le = Criterion(Rel.LE, quantity(70, TEMPERATURE), quantity(5, TEMPERATURE))
        ge = Criterion(Rel.GE, quantity(2), quantity(Fraction(1, 2)))
        self.assertEqual(le.tightened(), Criterion(Rel.LE, quantity(65, TEMPERATURE)))
        self.assertEqual(ge.tightened(), Criterion(Rel.GE, quantity(Fraction(5, 2))))

    def test_only_a_criterion_with_a_margin_tightens(self):
        with self.assertRaises(ValueError):
            Criterion(Rel.LE, quantity(1)).tightened()


class Syntax(GadgetDomain):
    def test_a_margin_follows_the_bound_and_keeps_its_unit(self):
        (claim,) = self.design(gadget(CAPACITY), push("10"), FITS, WAIVE_WEAR).claims
        self.assertEqual((claim.bound, claim.margin, claim.under), (quantity(Fraction(1, 2)), quantity(Fraction(1, 10)), ("push",)))
        (percent,) = self.design(gadget(CAPACITY), push("10"), "claim fits: g.utilisation <= 50 % margin 10 %\n", WAIVE_WEAR).claims
        self.assertEqual(percent.margin, quantity(Fraction(1, 10)))
        (plain,) = self.design(gadget(CAPACITY), push("10"), "claim fits: g.utilisation <= 1/2\n", WAIVE_WEAR).claims
        self.assertIsNone(plain.margin)

    def test_a_margin_has_the_bounds_dimension_and_is_positive(self):
        for margin, fragment in (("1 kN", "dimension"), ("0", "positive"), ("-1/10", "positive")):
            with self.subTest(margin=margin), self.assertRaises(LoweringError) as ctx:
                self.design(gadget(CAPACITY), push("10"), f"claim fits: g.utilisation <= 1/2 margin {margin}\n", WAIVE_WEAR)
            self.assertIn(fragment, str(ctx.exception))

    def test_a_bound_without_a_unit_is_named_as_the_problem(self):
        text = (ROOT / "examples" / "circuit_pass.petra").read_text(encoding="utf-8")
        text = text.replace("lighting.w1.temperature <= 70 degC", "lighting.w1.temperature <= 70 margin 20 degC")
        with self.assertRaises(LoweringError) as ctx:
            parse_design(text, "radial.petra", REGISTRY)
        self.assertIn("the bound needs a unit", str(ctx.exception))

    def test_explain_prints_the_margin_statement_beside_the_claim(self):
        text = explain(self.design(gadget(CAPACITY), push("10"), FITS, WAIVE_WEAR), REGISTRY)
        self.assertIn("margin obligation, the bound moved to 0.4", text)
        self.assertEqual(text.count("rule   R4"), 2, text)


class Verdicts(GadgetDomain):
    def test_slack_beyond_the_margin_passes_and_says_the_margin_is_proved(self):
        report = self.check(gadget(CAPACITY), push("7"), FITS, WAIVE_WEAR)
        self.assertIsInstance(report.verdict, Pass, report.render())
        (proved,) = [o for o in report.outcomes if isinstance(o, Discharged)]
        self.assertEqual(proved.margin_status, "proved")
        self.assertIn(f"margin     {proved.obligation.requirement.id}: proved: the claim holds with at least 0.1 to spare", report.render())
        self.assertEqual(verdict_json(report.entries[0])["margins"], [{"requirement": proved.obligation.requirement.id, "proved": True, "margin": "proved"}])

    def test_a_margin_no_source_decides_is_reported_undecided(self):
        body = (gadget(CAPACITY), push("7"), FITS, WAIVE_WEAR)
        margin = next(o for o in self.check(*body).outcomes if isinstance(o, Discharged)).margin
        report = self.check(*body, sources=(Skipping({statement_hash(margin.statement)}, Solver()),))
        self.assertIsInstance(report.verdict, Pass, report.render())
        self.assertIn("undecided: no point within 0.1 of the bound was found, and slack 0.1 is not proved", report.render())
        self.assertEqual(verdict_json(report.entries[0])["margins"][0]["margin"], "undecided")

    def test_a_point_within_the_margin_is_marginal_and_keeps_the_proof(self):
        report = self.check(gadget(CAPACITY), push("9"), FITS, WAIVE_WEAR)
        self.assertIsInstance(report.verdict, Marginal, report.render())
        (near,) = report.verdict.near
        self.assertIsNotNone(near.theorem, "the claim itself was proved")
        self.assertIn(near.theorem, report.verdict.theorems)
        self.assertEqual(dict(near.refutation.point)["push.g.force"], 9000)
        self.assertIn("in:rig.push.g.force", report.verdict.footprint.labels)
        text = report.render()
        self.assertIn("within margin", text)
        self.assertIn("proved; at this point it is within 0.1 of its bound", text)
        entry = verdict_json(report.entries[0])
        self.assertEqual((entry["status"], entry["obligations"]), ("MARGINAL", []))

    def test_without_a_proof_a_point_within_the_margin_is_unknown_and_shown(self):
        # A point within the margin says nothing about the rest of the box, so without
        # the claim's proof it cannot rank below UNKNOWN.
        report = self.check(gadget(CAPACITY), push("9"), FITS, WAIVE_WEAR, sources=(Witnesses(),))
        self.assertIsInstance(report.verdict, Unknown, report.render())
        (item,) = report.verdict.open
        self.assertIsNone(item.near.theorem)
        self.assertEqual(dict(item.near.refutation.point)["push.g.force"], 9000)
        self.assertIn("neither proved nor refuted; at this point it is within 0.1 of its bound", report.render())
        self.assertIn("push.g.force = 9000 N", report.render())
        (margin,) = verdict_json(report.entries[0])["margins"]
        self.assertEqual((margin["proved"], margin["margin"], margin["point"]["push.g.force"]), (False, "within", "9000"))

    def test_a_refuted_claim_fails_whatever_its_margin(self):
        report = self.check(gadget(CAPACITY), push("12"), FITS, WAIVE_WEAR)
        self.assertIsInstance(report.verdict, Fail, report.render())

    def test_a_margin_point_past_the_bound_is_a_fail(self):
        body = (gadget(CAPACITY), push("12"), FITS, WAIVE_WEAR)
        claim = self.check(*body, sources=()).verdict.open[0].needs[0].statement_hash
        report = self.check(*body, sources=(Skipping({claim}, Witnesses()),))
        self.assertIsInstance(report.verdict, Fail, report.render())
        self.assertEqual(report.verdict.refutation.statement_hash, claim, "the margin witness refutes the claim itself")

    def test_no_proof_and_no_point_within_the_margin_stays_unknown(self):
        report = self.check(gadget(CAPACITY), push("7"), FITS, WAIVE_WEAR, sources=(Witnesses(),))
        self.assertIsInstance(report.verdict, Unknown, report.render())

    def test_statuses_combine_by_severity(self):
        tight = "claim tight: g.utilisation <= 1/3 under push\n"
        loose = "claim loose: g.utilisation <= 1 under push\n"
        cases = (
            ((FITS, tight), (Witnesses(),), Fail, Unknown),
            ((FITS, loose), (Witnesses(),), Unknown, Unknown),
            ((FITS, loose), (Solver(),), Marginal, Marginal),
        )
        for claims, sources, expected, fits in cases:
            with self.subTest(claims=claims, expected=expected.__name__):
                report = self.check(gadget(CAPACITY), push("9"), *claims, WAIVE_WEAR, sources=sources)
                self.assertIsInstance(report.verdict, expected, report.render())
                self.assertIsInstance(self.entry(report, "fits"), fits)

    def test_marginal_and_an_open_item_combine_to_unknown(self):
        loose = "claim loose: g.utilisation <= 1 under push\n"
        body = (gadget(CAPACITY), push("9"), FITS, loose, WAIVE_WEAR)
        other = next(o for o in self.check(*body).outcomes if isinstance(o, Discharged) and o.obligation.requirement.origin == ClaimOrigin("loose"))
        report = self.check(*body, sources=(Skipping({statement_hash(other.obligation.statement)}, Solver()),))
        self.assertIsInstance(report.verdict, Unknown, report.render())
        self.assertIsInstance(self.entry(report, "fits"), Marginal)

    def unpaired(self) -> None:
        def build(req, model, design, registry):
            built = build_strength(req, model, design, registry)
            return built if req.criterion.margin is not None else built + built

        domain = dataclasses.replace(GADGET, builders={**GADGET.builders, STRENGTH: build})
        self.enterContext(mock.patch.object(models, "KINDS", MappingProxyType({"gadget": domain})))
        self.enterContext(mock.patch.object(coverage, "KINDS", {"gadget": domain}))

    def test_a_builder_whose_tightened_statements_do_not_pair_leaves_the_margin_open(self):
        self.unpaired()
        report = self.check(gadget(CAPACITY), push("9"), FITS, WAIVE_WEAR)
        self.assertIsInstance(report.verdict, Unknown, report.render())
        (need,) = report.verdict.open[0].needs
        self.assertIsInstance(need, NoRuleForQuantity)
        self.assertIn("margin statement was not checked", need.reason)
        self.assertTrue(any("margin was not checked" in w for w in report.warnings), report.warnings)

    def test_a_refuted_claim_with_an_unpaired_margin_still_fails(self):
        self.unpaired()
        self.assertIsInstance(self.check(gadget(CAPACITY), push("12"), FITS, WAIVE_WEAR).verdict, Fail)


class StoredMarginPoints(GadgetDomain):
    def test_a_stored_margin_refutation_replays_from_the_certificate_store(self):
        store = CertStore(self.enterContext(tempfile.TemporaryDirectory()))
        body = (gadget(CAPACITY), push("9"), FITS, WAIVE_WEAR)
        first = self.check(*body, sink=store)
        self.assertIsInstance(first.verdict, Marginal)
        again = self.check(*body, sources=(store,))
        self.assertIsInstance(again.verdict, Marginal, again.render())
        self.assertEqual(again.verdict.near[0].source, "certs")
        self.assertEqual(again.to_json(), first.to_json())


class Construction(GadgetDomain):
    def setUp(self):
        super().setUp()
        report = self.check(gadget(CAPACITY), push("9"), FITS, WAIVE_WEAR)
        (self.near,) = report.verdict.near

    def test_the_genuine_item_constructs(self):
        n = self.near
        WithinMargin(n.obligation, n.margin, n.refutation, n.source, n.theorem)
        WithinMargin(n.obligation, n.margin, n.refutation, n.source)

    def test_a_refutation_of_another_statement_is_refused(self):
        n = self.near
        other = _issue_refutation(n.obligation.statement, "sha256:s", "sha256:e", "R4", frozenset(), n.refutation.point)
        with self.assertRaises(ValueError):
            WithinMargin(n.obligation, n.margin, other, n.source)

    def test_a_margin_obligation_at_another_bound_is_refused(self):
        n = self.near
        req = n.margin.requirement
        moved = dataclasses.replace(req, criterion=Criterion(Rel.LE, quantity(Fraction(3, 10))))
        forged = dataclasses.replace(n.margin, requirement=moved)
        refutation = _issue_refutation(forged.statement, "sha256:s", "sha256:e", "R4", frozenset(), n.refutation.point)
        with self.assertRaises(ValueError):
            WithinMargin(n.obligation, forged, refutation, n.source)

    def test_a_margin_obligation_on_another_model_is_refused(self):
        n = self.near
        model = dataclasses.replace(n.margin.model, id="other.model")
        forged = dataclasses.replace(n.margin, model=model)
        with self.assertRaises(ValueError):
            WithinMargin(n.obligation, forged, n.refutation, n.source)

    def test_a_claim_without_a_margin_is_never_within_one(self):
        n = self.near
        plain = dataclasses.replace(n.obligation.requirement, criterion=dataclasses.replace(n.obligation.requirement.criterion, margin=None))
        with self.assertRaises(ValueError):
            WithinMargin(dataclasses.replace(n.obligation, requirement=plain), n.margin, n.refutation, n.source)

    def test_a_theorem_must_be_the_claims_own(self):
        n = self.near
        stray = _issue_theorem(n.margin.statement, "sha256:s", "sha256:e", "R4", frozenset(), ())
        with self.assertRaises(ValueError):
            WithinMargin(n.obligation, n.margin, n.refutation, n.source, stray)

    def test_a_marginal_verdict_names_an_item_within_its_margin(self):
        with self.assertRaises(ValueError):
            Marginal((), FOOTPRINT)
        with self.assertRaises(TypeError):
            Marginal(("near the bound",), FOOTPRINT)

    def test_a_marginal_verdict_needs_the_claims_proof(self):
        n = self.near
        bare = WithinMargin(n.obligation, n.margin, n.refutation, n.source)
        with self.assertRaises(ValueError):
            Marginal((bare,), FOOTPRINT)
        with self.assertRaises(ValueError):
            assemble((bare,), PremiseBook([], [], ()), Scope((), (), None))

    def test_a_proved_margin_claim_carries_its_margin_obligation(self):
        n = self.near
        with self.assertRaises(ValueError):
            Discharged(n.obligation, n.theorem, n.source)
        Discharged(n.obligation, n.theorem, n.source, n.margin)
        with self.assertRaises(ValueError):
            Discharged(n.obligation, n.theorem, n.source, n.margin, n.theorem)

    def test_an_open_items_margin_point_is_its_own_and_unproved(self):
        n = self.near
        bare = WithinMargin(n.obligation, n.margin, n.refutation, n.source)
        need = (NeedsCertificate("sha256:s", "R4", "x"),)
        Open(n.obligation.requirement, need, statement=n.obligation.statement, near=bare)
        with self.assertRaises(TypeError):
            Open(n.obligation.requirement, need, statement=n.obligation.statement, near=n)
        other = dataclasses.replace(n.obligation.requirement, origin=ClaimOrigin("other"))
        with self.assertRaises(ValueError):
            Open(other, need, statement=n.obligation.statement, near=bare)


class KnifeEdge(unittest.TestCase):
    """x (1 - x) <= 1/4 on [0, 1] holds with equality at x = 1/2. Interval enclosures
    never close the cells around 1/2 and no point exceeds the bound, so the claim alone
    is undecided; with a margin the search finds a point within it at once."""

    @staticmethod
    def statement(slack: Fraction) -> Statement:
        x = Sym("x")
        q = Mul((x, Add((Const(Fraction(1)), Neg(x)))))
        return Statement((RangeHyp("x", Fraction(0), Fraction(1), "in:k.x"),), AllNonpositive((Add((q, Neg(Const(Fraction(1, 4) - slack)))),)))

    def test_the_claim_is_undecided_and_its_margin_statement_is_refuted(self):
        claim, margin = self.statement(Fraction(0)), self.statement(Fraction(1, 100))
        source = SolverSource(max_cells=500)
        self.assertEqual([type(check(claim, e)) for e in source.offer(claim, "")], [])
        (evidence,) = source.offer(margin, "")
        self.assertIsInstance(check(margin, evidence), Refutation)
        self.assertIsInstance(check(claim, evidence), Rejection, "the point is within the margin, not past the bound")


class CommandLine(unittest.TestCase):
    def run_check(self, bound: str, *flags: str) -> tuple[int, str]:
        text = (ROOT / "examples" / "circuit_pass.petra").read_text(encoding="utf-8")
        text = text.replace("lighting.w1.temperature <= 70 degC", f"lighting.w1.temperature <= {bound}")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "radial.petra"
            path.write_text(text, encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cli.main(["check", str(path), *flags])
        return code, out.getvalue()

    def test_marginal_exits_5_and_names_its_status(self):
        code, out = self.run_check("70 degC margin 25 degC", "--json")
        self.assertEqual(code, 5)
        report = json.loads(out)
        self.assertEqual(report["status"], "MARGINAL")
        self.assertEqual([v["status"] for v in report["verdicts"]], ["MARGINAL", "PASS", "PASS"])

    def test_a_margin_the_design_keeps_passes(self):
        code, out = self.run_check("70 degC margin 2 degC")
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
