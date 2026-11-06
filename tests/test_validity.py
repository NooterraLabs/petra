"""Validity rows: a model's numeric limits as checked obligations. Owner: I.

models/base.py declares the rows (ValidityRow) and refuses an obligation that leaves one
unstated; pipeline._settle decides each row beside its obligation; verdict.py refuses an
outcome that rests on a model without the row proofs. These tests hold the semantics:
a proof needs every row proved over the box, a counterexample needs every row proved
over the box or at its point, and anything else is UNKNOWN naming the row.

Hand values (tests/test_truss.py): at equal node loads P the end diagonal of the Warren
footbridge carries 1.25 P of compression. CHS 60.3x3.2: A = 574.03 mm2, A fy = 203.78 kN,
N_cr = 74.12 kN and EN 1993-1-1 curve c N_b = 54.69 kN over 2.5 m at E = 200 GPa.
    P = 58 kN   1.25 P = 72.5 kN: inside the bare Euler load, past N_b
    P = 100 kN  diag stress 1.25 P / A = 217.8 MPa
    P = 130 kN  283.1 MPa
    P = 165 kN  359.3 MPa, past fy = 355 MPa
    P = 170 kN  370.2 MPa; strain 370.2 MPa / 200 GPa = 0.00185, inside 0.002
"""
import dataclasses
import importlib
import pkgutil
import re
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from petra import models
from petra.kernel import RangeHyp, Refutation, Statement, Theorem, check, statement_hash
from petra.lang import load_design, parse_design
from petra.library import Library, certify_family
from petra.models import truss
from petra.models.base import (
    VALIDITY_PREFIX,
    ClaimOrigin,
    ComponentError,
    FailureMode,
    ModelSpec,
    Obligation,
    OutsideValidity,
    validity_obligation,
)
from petra.pipeline import check_design, elaborate, explain, lower_components
from petra.registry import build_registry
from petra.solvers import SolverSource
from petra.verdict import Discharged, Fail, Open, Pass, Refuted, Unknown, at_point, describe_need

REGISTRY = build_registry()
ROOT = Path(__file__).resolve().parents[1]
PASS = (ROOT / "examples" / "truss_pass.petra").read_text(encoding="utf-8")
CROWD = "  on frame.D fy in [-24 kN, -16 kN]\n  on frame.E fy in [-24 kN, -16 kN]"
CLAIMS = """claim strength:   frame.collapse_factor >= 1.5 under crowd
claim stability:  frame.stability_factor >= 3 under crowd
claim stress:     frame.member(diag_ad).stress <= 235 MPa under crowd"""

LIMIT = re.compile(r"(<=?|>=?|≤|≥|\bwithin\b|\bat most\b|\bat least\b|\bup to\b|\bbelow\b|\babove\b|\bbeyond\b|\bunder\b|\bless than\b|\bmore than\b|\bexceeds?\b|\bexceeding\b)\s*[-+]?\d")
"""A number used as a limit in words: what a ValidityRow, or ModelSpec.unchecked, is for."""


def footbridge(lo_kn: int, hi_kn: int, claims: str):
    assert CROWD in PASS and CLAIMS in PASS, "truss_pass.petra changed shape"
    text = PASS.replace(CROWD, f"  on frame.D fy in [{lo_kn} kN, {hi_kn} kN]\n  on frame.E fy in [{lo_kn} kN, {hi_kn} kN]")
    return parse_design(text.replace(CLAIMS, claims), "t.petra", REGISTRY)


def obligations(design) -> tuple[Obligation, ...]:
    lowered = lower_components(design, REGISTRY)
    from petra import coverage
    return tuple(o for o in elaborate(design, lowered, coverage.generate(design, lowered, REGISTRY), REGISTRY) if isinstance(o, Obligation))


def claimed(design, claim: str) -> Obligation:
    (found,) = [o for o in obligations(design) if o.requirement.origin == ClaimOrigin(claim)]
    return found


def solved(statement: Statement):
    for evidence in SolverSource().offer(statement, statement_hash(statement)):
        result = check(statement, evidence)
        if isinstance(result, (Theorem, Refutation)):
            return result
    return None


def entry(report, name: str):
    (found,) = [e for e in report.entries if e.claim == name]
    return found


def all_model_specs() -> set[ModelSpec]:
    found = set()
    for info in pkgutil.iter_modules(models.__path__):
        module = importlib.import_module(f"petra.models.{info.name}")
        found |= {v for v in vars(module).values() if isinstance(v, ModelSpec)}
    for domain in (models.DOMAINS.values() if hasattr(models.DOMAINS, "values") else models.DOMAINS):
        found |= set(domain.models.values())
    return found


class Lint(unittest.TestCase):
    def test_no_model_states_a_numeric_limit_in_words(self):
        specs = all_model_specs()
        self.assertGreaterEqual(len(specs), 12, "every domain's models are found")
        for spec in specs:
            with self.subTest(model=spec.id):
                self.assertIsNone(LIMIT.search(spec.validity), "a numeric limit is a ValidityRow, or listed in ModelSpec.unchecked")

    def test_the_lint_catches_the_limits_v0_used_to_state_in_words(self):
        for text in ("fault cleared within 5 s", "|strain| <= 0.002 in every member", "a alpha < 1 (checked)", "strain under 0.002", "d/t less than 90", "N ≤ 1 A fy"):
            with self.subTest(text=text):
                self.assertIsNotNone(LIMIT.search(text))

    def test_an_unchecked_limit_is_printed_as_not_checked(self):
        from petra.models import circuit
        self.assertIn("not checked: the fault is cleared within 5 s", circuit.ADIABATIC.premise().statement)

    def test_every_truss_obligation_states_each_row_of_its_model_over_its_own_load_case(self):
        for o in obligations(footbridge(-24, -16, CLAIMS)):
            with self.subTest(requirement=o.requirement.id):
                self.assertEqual(tuple(v.row for v in o.validity), o.model.rows)
                inputs = {h.label for h in o.statement.hyps if isinstance(h, RangeHyp) and h.label.startswith("in:")}
                for v in o.validity:
                    self.assertTrue(v.requirement.mode.id.startswith(VALIDITY_PREFIX))
                    self.assertEqual(v.requirement.origin, o.requirement.origin)
                    self.assertEqual(v.validity, ())
                    used = {h.label for h in v.statement.hyps if isinstance(h, RangeHyp) and h.label.startswith("in:")}
                    self.assertLessEqual(used, inputs, "a row ranges over the obligation's own load case")

    def test_an_obligation_that_leaves_a_row_unstated_cannot_be_built(self):
        design = footbridge(-24, -16, CLAIMS)
        o, other = claimed(design, "stress"), claimed(design, "stability")
        with self.assertRaisesRegex(ValueError, "one validity obligation for each"):
            Obligation(o.requirement, o.statement, o.model, o.describe)
        with self.assertRaisesRegex(ValueError, "one validity obligation for each"):
            Obligation(o.requirement, o.statement, o.model, o.describe, o.validity[:1])
        with self.assertRaisesRegex(ValueError, "not over the same model"):
            Obligation(o.requirement, o.statement, o.model, o.describe, other.validity)
        with self.assertRaisesRegex(ValueError, "no validity rows of its own"):
            dataclasses.replace(o.validity[0], validity=o.validity)

    def test_a_validity_mode_that_names_no_row_of_its_model_is_refused(self):
        row = claimed(footbridge(-24, -16, CLAIMS), "stress").validity[0]
        made_up = dataclasses.replace(row.requirement, mode=FailureMode(f"{VALIDITY_PREFIX}anything"))
        with self.assertRaisesRegex(ValueError, "is not a validity row of model truss.elastic"):
            dataclasses.replace(row, requirement=made_up)

    def test_a_row_of_another_model_is_refused(self):
        o = claimed(footbridge(-24, -16, CLAIMS), "strength")
        with self.assertRaisesRegex(ValueError, "is not a validity row"):
            validity_obligation(o.requirement, o.model, truss.BELOW_YIELD, o.statement, "x")


class Outcomes(unittest.TestCase):
    def test_a_proof_needs_the_proof_of_every_row(self):
        o = claimed(footbridge(-24, -16, CLAIMS), "stress")
        theorem = solved(o.statement)
        rows = tuple(solved(v.statement) for v in o.validity)
        self.assertIsInstance(theorem, Theorem)
        self.assertTrue(all(isinstance(r, Theorem) for r in rows))
        with self.assertRaisesRegex(ValueError, "validity rows each need a proof"):
            Discharged(o, theorem, "solver")
        with self.assertRaisesRegex(ValueError, "for another statement"):
            Discharged(o, theorem, "solver", validity=rows[::-1])
        with self.assertRaisesRegex(TypeError, "Theorem kernel.check issued"):
            Discharged(o, theorem, "solver", validity=(rows[0], theorem.statement))
        self.assertEqual(Discharged(o, theorem, "solver", validity=rows).validity, rows)


class Verdicts(unittest.TestCase):
    def test_the_bare_euler_false_pass_is_now_a_fail(self):
        """The audit's H7: under the bare Euler load 72.5 kN fits inside 74.12 kN, so v0
        proved collapse factor >= 1 at 58 kN; EN 1993's 54.69 kN refutes it."""
        report = check_design(footbridge(-58, -50, "claim strength: frame.collapse_factor >= 1 under crowd"), REGISTRY, (SolverSource(),))
        verdict = entry(report, "strength").verdict
        self.assertIsInstance(verdict, Fail, "1.25 x 58 = 72.5 kN of compression against N_b = 54.69 kN")
        self.assertEqual(len(verdict.validity), 1, "the section-class row is proved beside the mechanism")
        self.assertIn("model:truss.plastic", {p.label.split("@")[0] for p in verdict.footprint.premises})

    def test_a_stress_claim_past_yield_is_unknown_not_proved(self):
        """The audit's H3: an elastic stress claim proved where the elastic model no longer
        holds. 359 to 370 MPa is within the claimed 400 MPa, and past fy = 355 MPa."""
        design = footbridge(-170, -165, "claim stress: frame.member(diag_ad).stress <= 400 MPa under crowd")
        self.assertIsInstance(solved(claimed(design, "stress").statement), Theorem, "the claim statement alone is proved")
        verdict = entry(check_design(design, REGISTRY, (SolverSource(),)), "stress").verdict
        self.assertIsInstance(verdict, Unknown)
        (item,) = verdict.open
        outside = [n for n in item.needs if isinstance(n, OutsideValidity)]
        self.assertEqual([(n.model, n.row) for n in outside], [("truss.elastic", "truss.elastic.below_yield")])
        self.assertIn("outside its validity range", describe_need(outside[0]))
        self.assertTrue(dict(outside[0].point), "the need names the inputs where the row fails")

    def test_a_counterexample_outside_the_model_is_not_a_fail(self):
        design = footbridge(-170, -165, "claim stress: frame.member(diag_ad).stress <= 300 MPa under crowd")
        self.assertIsInstance(solved(claimed(design, "stress").statement), Refutation, "359 MPa and up exceeds 300 MPa")
        verdict = entry(check_design(design, REGISTRY, (SolverSource(),)), "stress").verdict
        self.assertIsInstance(verdict, Unknown, "every point of the box is past yield, so the model says nothing there")
        (item,) = verdict.open
        self.assertTrue(any(isinstance(n, OutsideValidity) and n.row == truss.BELOW_YIELD.id for n in item.needs))

    def test_a_counterexample_where_the_model_holds_is_a_fail_though_the_row_fails_elsewhere(self):
        """Loads 100 to 170 kN: the row fails at 170 kN (370 MPa), and holds at 130 kN
        (283 MPa), where a 250 MPa claim fails. The FAIL rests on the row at that point."""
        design = footbridge(-170, -100, "claim stress: frame.member(diag_ad).stress <= 250 MPa under crowd")
        o = claimed(design, "stress")
        below, strain = o.validity
        self.assertIsInstance(solved(below.statement), Refutation, "370 MPa > 355 MPa at 170 kN")
        loads = {h.label for h in o.statement.hyps if isinstance(h, RangeHyp) and h.label.startswith("in:")}
        narrow = Statement(tuple(dataclasses.replace(h, lo=Fraction(-130000), hi=Fraction(-130000)) if isinstance(h, RangeHyp) and h.label in loads else h for h in o.statement.hyps), o.statement.goal)
        (evidence,) = [e for e in SolverSource().offer(narrow, statement_hash(narrow)) if isinstance(check(narrow, e), Refutation)][:1]
        self.assertIsInstance(check(o.statement, evidence), Refutation, "the 130 kN point refutes the claim over the whole box")

        class AtThePoint:
            name = "point"

            def offer(self, statement, digest):
                return (evidence,) if digest == statement_hash(o.statement) else SolverSource().offer(statement, digest)

        report = check_design(design, REGISTRY, (AtThePoint(),))
        verdict = entry(report, "stress").verdict
        self.assertIsInstance(verdict, Fail)
        point_proof, strain_proof = verdict.validity
        self.assertEqual(point_proof.statement, at_point(below.statement, verdict.refutation), "below yield at 130 kN")
        self.assertNotEqual(point_proof.statement, below.statement)
        self.assertEqual(strain_proof.statement, strain.statement, "0.00185 at most: proved over the whole box")
        (refuted,) = [x for x in report.outcomes if isinstance(x, Refuted) and x.obligation.requirement.origin == ClaimOrigin("stress")]
        self.assertEqual(refuted.validity, verdict.validity)

    def test_a_counterexample_past_a_row_names_its_point_once(self):
        """Loads 100 to 170 kN, claim 250 MPa: the solver's counterexample is the 170 kN
        corner, past yield. The need names that corner, and the row's need over the whole
        box is not listed beside it."""
        design = footbridge(-170, -100, "claim stress: frame.member(diag_ad).stress <= 250 MPa under crowd")
        verdict = entry(check_design(design, REGISTRY, (SolverSource(),)), "stress").verdict
        self.assertIsInstance(verdict, Unknown)
        (item,) = verdict.open
        (outside,) = [n for n in item.needs if isinstance(n, OutsideValidity) and n.row == truss.BELOW_YIELD.id]
        self.assertEqual(set(dict(outside.point).values()), {"-170000"}, "both node loads at the corner")
        self.assertIn("-170000", describe_need(outside))

    def test_at_point_narrows_only_what_the_counterexample_assumes(self):
        design = footbridge(-170, -100, "claim stress: frame.member(diag_ad).stress <= 250 MPa under crowd")
        o = claimed(design, "stress")
        refutation = solved(o.statement)
        self.assertIsInstance(refutation, Refutation)
        section = o.model.rows.index(truss.SECTION_CLASS) if truss.SECTION_CLASS in o.model.rows else None
        self.assertIsNone(section, "the elastic model has no section row")
        narrowed = at_point(o.validity[0].statement, refutation)
        value = {h.label: v for h, (_, v) in zip((h for h in refutation.statement.hyps if isinstance(h, RangeHyp)), refutation.point)}
        for h in narrowed.hyps:
            if isinstance(h, RangeHyp):
                with self.subTest(label=h.label):
                    if h.label in value:
                        self.assertEqual((h.lo, h.hi), (value[h.label], value[h.label]))
        self.assertEqual(narrowed.goal, o.validity[0].statement.goal)

    def test_the_shipped_examples_keep_their_verdicts(self):
        for name, kind in (("truss_pass", Pass), ("truss_fail", Fail)):
            with self.subTest(example=name):
                report = check_design(load_design(ROOT / "examples" / f"{name}.petra", REGISTRY), REGISTRY, (SolverSource(),))
                self.assertIsInstance(report.verdict, kind)
                for outcome in report.outcomes:
                    if isinstance(outcome, (Discharged, Refuted)):
                        self.assertEqual(len(outcome.validity), len(outcome.obligation.model.rows))

    def test_explain_prints_each_row_beside_its_obligation(self):
        text = explain(footbridge(-24, -16, CLAIMS), REGISTRY)
        for row in (truss.BELOW_YIELD, truss.SMALL_STRAIN, truss.SECTION_CLASS):
            self.assertIn(f"validity {row.id}: {row.text}", text)


class Lowering(unittest.TestCase):
    def test_a_member_of_another_family_than_its_section_is_refused(self):
        text = PASS.replace("member diag_ad:   A -- D", "member diag_ad:   A -- D material aluminium.6061_T6")
        design = parse_design(text, "t.petra", REGISTRY)
        with self.assertRaisesRegex(ComponentError, "buckling curve does not hold"):
            lower_components(design, REGISTRY)

    def test_every_hollow_section_buckles_on_curve_c(self):
        alpha = REGISTRY.constants["en1993_1_1.curve_c.alpha"]
        self.assertEqual((alpha.value.lo, alpha.value.hi), (Fraction(49, 100), Fraction(49, 100)))
        sections = [p for p in REGISTRY.parts.values() if p.id.startswith("chs.")]
        self.assertTrue(sections)
        for part in sections:
            with self.subTest(section=part.id):
                self.assertEqual(part.props["buckling_alpha"].expr.name, "const.en1993_1_1.curve_c.alpha")


class Envelope(unittest.TestCase):
    def test_an_input_a_row_reads_counts_as_one_the_obligation_depends_on(self):
        from petra import envelope
        design = footbridge(-24, -16, CLAIMS)
        reach = envelope._row_reach(design, REGISTRY)
        o = claimed(design, "stress")
        key = envelope._key(o.requirement.id, o.statement)
        for v in o.validity:
            self.assertLessEqual({h.label for h in v.statement.hyps if isinstance(h, RangeHyp)}, reach[key])
        item = Open(o.requirement, (OutsideValidity(o.model.id, truss.BELOW_YIELD.id, truss.BELOW_YIELD.text, "sha256:0", ()),), statement=o.statement)
        self.assertFalse(envelope._depends(item, "in:read.by.a.row.only", {}))
        self.assertTrue(envelope._depends(item, "in:read.by.a.row.only", {key: frozenset({"in:read.by.a.row.only"})}))


class Family(unittest.TestCase):
    def test_a_family_stores_its_row_proofs_and_an_instance_reuses_them(self):
        family = load_design(ROOT / "examples" / "families" / "warren_truss.petra", REGISTRY)
        with tempfile.TemporaryDirectory() as root:
            library = Library(root)
            certified = certify_family(family, REGISTRY, library)
            self.assertEqual(certified.skipped, ())
            stored = {statement_hash(e.statement) for e in certified.stored}
            for outcome in certified.report.outcomes:
                if isinstance(outcome, Discharged) and isinstance(outcome.obligation.requirement.origin, ClaimOrigin):
                    for v in outcome.obligation.validity:
                        self.assertIn(statement_hash(v.statement), stored, v.requirement.id)
            report = check_design(load_design(ROOT / "examples" / "truss_pass.petra", REGISTRY), REGISTRY, (Library(root),))
            for name in ("strength", "stability", "stress"):
                with self.subTest(claim=name):
                    verdict = entry(report, name).verdict
                    self.assertIsInstance(verdict, Pass, "the claim and every row it rests on come from the family")

    def test_a_family_claim_refuted_where_its_rows_hold_is_reported_refuted(self):
        text = (ROOT / "examples" / "families" / "warren_truss.petra").read_text(encoding="utf-8")
        text = text.replace("[-29 kN, 0 kN]", "[-170 kN, -100 kN]")
        text = "\n".join(line for line in text.splitlines() if not line.startswith("claim "))
        text += "\nclaim stress: frame.member(diag_db).stress <= 30 MPa under crowd\n"
        with tempfile.TemporaryDirectory() as root:
            certified = certify_family(parse_design(text, "f.petra", REGISTRY), REGISTRY, Library(root))
        (skipped,) = certified.skipped
        self.assertIn("refuted by R3", skipped, "the rows are proved at the counterexample, as in a design")


if __name__ == "__main__":
    unittest.main()
