"""Red-team reproductions for margins (MARGINAL) and `petra envelope`.

Each finding has a test asserting the behaviour the design documents promise; they were
expected failures until the fixes landed. The precondition tests pin what each one relies
on, so it cannot pass for an unrelated reason.

They run on the shipped examples, edited as text.
"""
import contextlib
import io
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from petra import cli
from petra.certs import CertStore
from petra.files import read_pair
from petra.kernel import Evidence, Refutation, Theorem, check, statement_hash
from petra.kernel.rules.r4_enclosure import PointWitness
from petra.lang import load_design, parse_design
from petra.library import Library, certify_family
from petra.models.base import ClaimOrigin
from petra.pipeline import _prepare, check_design
from petra.registry import build_registry
from petra.solvers import SolverSource
from petra.verdict import Marginal, Pass, Refuted, WithinMargin

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = build_registry()


def edited(example: str, *subs: tuple[str, str]) -> tuple[str, str]:
    """The example's card and design, each substitution made in the file that holds its
    text. A substitution of "" adds to the card."""
    card, text = read_pair(ROOT / example)
    for old, new in subs:
        if old:
            assert old in card or old in text, old
            card, text = card.replace(old, new), text.replace(old, new)
        else:
            card += new
    return card, text


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as exc:   # argparse usage errors exit through _Parser.error
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class _Files(unittest.TestCase):
    def setUp(self):
        self.dir = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def write(self, name: str, pair: tuple[str, str]) -> str:
        """Write the design as `name` and its card beside it. Returns the design's path."""
        card, text = pair
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        path.with_suffix(".card").write_text(card, encoding="utf-8")
        return str(path)


# --- 1. A margin witness can hide a refutation of the claim at its own point ---------

# Overload protection at utilisation 1 with margin 1/2, ambient up to 70 degC. The claim
# is false at the hot corner (the wire passes 70 degC at the rated current there). The
# margin statement's first expression, I_B - In/2 <= 0, is refuted at that corner too.
# The pipeline checks the margin witness against the claim with the witness's own
# `which` (0) only, where the claim's first expression I_B - In <= 0 holds, so it
# reports MARGINAL ("not proved and not refuted") at a point where the claim's second
# and fourth expressions are refuted.
HOT_OVERLOAD = (
    ("ambient in [10 degC, 40 degC]", "ambient in [10 degC, 70 degC]"),
    ("claim hot:  lighting.w1.temperature <= 70 degC under lamp_draw\n", ""),
    ("claim drop: lighting.w1.voltage_drop <= 3 % under lamp_draw\n",
     "claim ol: lighting.w1.overload_protection <= 1 margin 1/2 under lamp_draw\n"
     'waive wire.steady_temperature on lighting.w1 by "x@example.org" reason "r"\n'
     'waive port.contract on lighting.t1.wire by "x@example.org" reason "r"\n'),
)


class MarginWitnessHidesFail(_Files):
    def setUp(self):
        super().setUp()
        self.path = self.write("ol.petra", edited("examples/circuit_pass.petra", *HOT_OVERLOAD))
        design = load_design(self.path, REGISTRY)
        prepared = _prepare(design, REGISTRY)
        (i,) = [k for k, e in enumerate(prepared.elaborated) if e.requirement.origin == ClaimOrigin("ol")]
        self.claim, self.margin = prepared.elaborated[i], prepared.margins[i]
        hot = tuple(sorted((h.sym, h.lo if h.label.endswith("clipped_direct.h") else h.hi) for h in self.margin.statement.hyps))
        self.witness = Evidence(PointWitness(hot, 0))
        self.point = hot
        # Certificates a solver run leaves behind, minus the claim's own refutation.
        self.certs = self.dir / "certs"
        run_cli("check", self.path, "--certs", str(self.certs))
        (self.certs / (statement_hash(self.claim.statement)[len("sha256:"):] + ".json")).unlink()

    def test_precondition_the_claim_is_refuted_at_the_witness_point(self):
        self.assertIsInstance(check(self.margin.statement, self.witness), Refutation)
        self.assertNotIsInstance(check(self.claim.statement, self.witness), Refutation)
        self.assertIsInstance(check(self.claim.statement, Evidence(PointWitness(self.point, 1))), Refutation)
        code, out, _ = run_cli("check", self.path)
        self.assertEqual(code, 1, out)
        code, out, _ = run_cli("check", self.path, "--no-solve", "--certs", str(self.certs))
        self.assertEqual(code, 2, out)

    def test_a_margin_witness_never_reports_marginal_where_the_claim_fails(self):
        CertStore(self.certs).record(self.margin.statement, statement_hash(self.margin.statement), self.witness, "hand")
        code, out, _ = run_cli("check", self.path, "--no-solve", "--certs", str(self.certs))
        # Before the fix: exit 5, "ol MARGINAL ... not proved and not refuted", ambient = 70 degC.
        self.assertNotIn("MARGINAL", out.splitlines()[0], out)
        self.assertNotEqual(code, 5, out)
        self.assertEqual(code, 1, "the witness point refutes the claim through another expression")

    def test_a_margin_point_where_the_claim_holds_leaves_an_unproved_claim_unknown(self):
        cool = tuple((sym, Fraction(10) if sym == "ambient" else value) for sym, value in self.point)
        witness = Evidence(PointWitness(cool, 0))
        if not isinstance(check(self.margin.statement, witness), Refutation):
            self.skipTest("the margin statement holds at the cool corner")
        self.assertNotIsInstance(check(self.claim.statement, Evidence(PointWitness(cool, 1))), Refutation)
        CertStore(self.certs).record(self.margin.statement, statement_hash(self.margin.statement), witness, "hand")
        code, out, _ = run_cli("check", self.path, "--no-solve", "--certs", str(self.certs))
        self.assertEqual(code, 2, out)
        self.assertIn("neither proved nor refuted; at this point it is within", out)


# --- 2. PASS while every point is within the margin --------------------------------

class UndecidedMarginPasses(_Files):
    """R2 cannot refute a stability factor, so the margin statement at 10^30 + 3 is never
    refuted: PASS, with no word that the margin was not decided. README: "It is PASS if
    the claim is proved and no point comes that close." Every point comes that close."""

    HUGE = "1000000000000000000000000000000"

    def report(self, claim: str):
        pair = edited("examples/truss_pass.petra", ("claim stability:  frame.stability_factor >= 3 under crowd", claim))
        return check_design(parse_design(*pair, "t.petra", REGISTRY), REGISTRY, (SolverSource(),))

    def test_a_stress_margin_prints_in_a_readable_unit(self):
        pair = edited("examples/truss_pass.petra", ("claim stress:     frame.member(diag_ad).stress <= 235 MPa under crowd",
                                                     "claim stress: frame.member(diag_ad).stress <= 235 MPa margin 300 MPa under crowd"))
        report = check_design(parse_design(*pair, "t.petra", REGISTRY), REGISTRY, (SolverSource(),))
        self.assertIn("300 MPa", report.render())
        self.assertNotIn("300000000 Pa", report.render())

    def test_precondition_the_plain_claim_at_the_tightened_bound_is_not_proved(self):
        report = self.report(f"claim stability: frame.stability_factor >= {self.HUGE}3 under crowd")
        self.assertNotIsInstance(report.verdict, Pass, report.render())

    def test_a_margin_the_solvers_cannot_decide_is_not_a_plain_pass(self):
        report = self.report(f"claim stability: frame.stability_factor >= 3 margin {self.HUGE} under crowd")
        text = report.render()
        self.assertTrue(not isinstance(report.verdict, Pass) or "margin" in text, text)


# --- 3. A certified proof of the margin statement is thrown away -------------------

class MarginProofDiscarded(_Files):
    """The `<= 58 degC` certificate proves `<= 60 degC margin 2 degC` outright (it is the
    margin statement, and checked against the claim it is a theorem of the claim's own
    statement). _within_margin checks it against the claim, gets that Theorem, and drops
    it, so the claim stays UNKNOWN with "no R4 certificate"."""

    def test_precondition_the_margin_certificate_proves_the_claim(self):
        certs = str(self.dir / "certs")
        plain = self.write("p.petra", edited("examples/circuit_pass.petra", ("<= 70 degC under lamp_draw", "<= 58 degC under lamp_draw")))
        self.assertEqual(run_cli("check", plain, "--certs", certs)[0], 0)
        path = self.write("m.petra", edited("examples/circuit_pass.petra", ("<= 70 degC under lamp_draw", "<= 60 degC margin 2 degC under lamp_draw")))
        design = load_design(path, REGISTRY)
        prepared = _prepare(design, REGISTRY)
        (i,) = [k for k, e in enumerate(prepared.elaborated) if e.requirement.origin == ClaimOrigin("hot")]
        claim, margin = prepared.elaborated[i], prepared.margins[i]
        (evidence,) = CertStore(certs).offer(margin.statement, statement_hash(margin.statement))
        self.assertIsInstance(check(claim.statement, evidence), Theorem)
        self.assertEqual(tuple(CertStore(certs).offer(claim.statement, statement_hash(claim.statement))), ())

    def test_the_claim_passes_on_the_margin_certificate(self):
        certs = str(self.dir / "certs")
        plain = self.write("p.petra", edited("examples/circuit_pass.petra", ("<= 70 degC under lamp_draw", "<= 58 degC under lamp_draw")))
        run_cli("check", plain, "--certs", certs)
        path = self.write("m.petra", edited("examples/circuit_pass.petra", ("<= 70 degC under lamp_draw", "<= 60 degC margin 2 degC under lamp_draw")))
        code, out, _ = run_cli("check", path, "--no-solve", "--certs", certs)
        self.assertEqual(code, 0, out)
        self.assertIn("proved: the claim holds with at least 2 degC to spare", out)


# --- 4. WithinMargin accepts the margin obligation of another load case -------------

class MispairedWithinMargin(unittest.TestCase):
    def test_within_margin_refuses_a_margin_obligation_of_another_load_case(self):
        pair = edited(
            "examples/truss_pass.petra",
            ("claim strength:   frame.collapse_factor >= 1.5 under crowd\n", ""),
            ("claim stability:  frame.stability_factor >= 3 under crowd\n", ""),
            ("claim stress:     frame.member(diag_ad).stress <= 235 MPa under crowd",
             "claim stress: frame.member(diag_ad).stress <= 235 MPa margin 300 MPa"),
            ("", 'load gust {\n  on frame.E fx in [1 kN, 2 kN]\n  signed "c@example.org" source "s"\n}\n'),
        )
        prepared = _prepare(parse_design(*pair, "t.petra", REGISTRY), REGISTRY)
        (crowd, _), (gust, gust_margin) = [(e, m) for e, m in zip(prepared.elaborated, prepared.margins) if m is not None]
        self.assertIn("crowd", crowd.describe)
        self.assertIn("gust", gust_margin.describe)
        digest = statement_hash(gust_margin.statement)
        refutation = next(r for ev in SolverSource().offer(gust_margin.statement, digest)
                          if isinstance(r := check(gust_margin.statement, ev), Refutation))
        with self.assertRaises(ValueError):
            WithinMargin(crowd, gust_margin, refutation, "solver")


# --- 5. certify-family calls a proved margin claim "not proved" and drops it --------

class FamilyMarginMessage(_Files):
    def test_a_proved_claim_with_a_margin_point_is_not_called_unproved(self):
        pair = edited(
            "examples/families/cu_pvc_clipped.petra",
            ("claim hot:  c.w1.temperature <= 70 degC under demand",
             "claim hot:  c.w1.temperature <= 70 degC margin 20 degC under demand\n"
             "claim hot50: c.w1.temperature <= 50 degC under demand"),
        )
        design = parse_design(*pair, "f.petra", REGISTRY)
        result = certify_family(design, REGISTRY, Library(self.dir / "lib"))
        near = [o for o in result.report.outcomes if isinstance(o, WithinMargin)]
        self.assertTrue(near and near[0].theorem is not None, "precondition: hot is proved and within its margin")
        self.assertFalse(any("claim.hot:" in s and "not proved" in s for s in result.skipped), result.skipped)


# --- 6. Envelope: exit status and argument parsing ----------------------------------

class EnvelopeCli(_Files):
    def test_exit_status_is_not_zero_when_the_design_fails_elsewhere(self):
        path = self.write("c.petra", edited("examples/circuit_pass.petra", ("fault_current in [0 kA, 6 kA]", "fault_current in [0 kA, 9 kA]")))
        self.assertEqual(run_cli("check", path)[0], 1)
        code, out, _ = run_cli("envelope", path, "--input", "ambient", "--from", "10 degC", "--to", "60 degC")
        self.assertIn("elsewhere  the obligations that do not depend on ambient are FAIL", out)
        self.assertNotEqual(code, 0, out)  # today 0, the same as a design that holds

    def test_a_negative_quantity_with_its_unit_attached_is_accepted(self):
        # _quantity documents "-20degC"; argparse takes it for an option and exits 3.
        code, out, err = run_cli("envelope", str(ROOT / "examples/truss_pass.petra"), "--input", "crowd.frame.D.fy",
                                 "--from", "-30kN", "--to", "-10kN", "--resolution", "10kN")
        self.assertEqual(code, 0, err)


if __name__ == "__main__":
    unittest.main()
