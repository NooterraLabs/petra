"""The kernel mutation suite. Owner: M.

Part 1 of seam M. For every rule R1 to R6 and every evidence kind (proofs, refutations,
the R3 lemma under each, and an Instance of a family theorem) a valid certificate is built
as a fixture under tests/fixtures/ and shown valid through kernel.check. Then a battery of mutation operators tampers with each
certificate in a way that is guaranteed to destroy validity, and the suite asserts the
kernel (or the strict codec, or the statement-hash binding) rejects every mutant.

The fixtures, operators and envelope verifier live in tests/mutations.py, which is also a
runnable self-check (python -m tests.mutations). The coverage test derives what must be
covered from the kernel rule registry, so a new rule or evidence kind that ships without a
fixture fails the suite rather than passing silently.
"""
import copy
import json
import unittest
from pathlib import Path

from petra.kernel import (
    LEMMAS,
    PROOF_RULE,
    REFUTATION_RULE,
    RULES,
    DecodeError,
    Instance,
    Refutation,
    Rejection,
    Theorem,
)
from tests import mutations
from tests.mutations import (
    DECODE_ERROR,
    FIXTURES,
    HASH_MISMATCH,
    OPERATORS,
    REJECTION,
    HashMismatch,
    verify_envelope,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{name}.cert.json").read_text(encoding="utf-8"))


class ValidFixtures(unittest.TestCase):
    """Each stored certificate checks as the Theorem or Refutation its rule calls for.
    This is the positive half the mutation tests discriminate against."""

    def test_every_fixture_checks_as_its_declared_kind(self):
        for fix in FIXTURES:
            with self.subTest(fixture=fix.name):
                result = verify_envelope(_load(fix.name))
                want = Theorem if fix.kind == "theorem" else Refutation
                self.assertIsInstance(result, want, getattr(result, "reason", repr(result)))
                self.assertEqual(result.rule, fix.rule)

    def test_stored_files_match_the_fixtures_they_were_generated_from(self):
        for fix in FIXTURES:
            with self.subTest(fixture=fix.name):
                stored = _load(fix.name)
                self.assertEqual(stored["statement_hash"], fix.envelope()["statement_hash"])
                self.assertEqual(stored, fix.envelope(), "regenerate with tests.mutations.write_fixtures")


class Mutants(unittest.TestCase):
    """Every operator, on every fixture it applies to, is rejected in the way its kind
    says. An operator never leaves a certificate valid, so a Theorem or Refutation here
    would be a soundness failure."""

    def _rejection(self, env: dict):
        try:
            return verify_envelope(env)
        except DecodeError:
            return DECODE_ERROR

    def test_each_mutant_is_rejected(self):
        for fix in FIXTURES:
            base = _load(fix.name)
            for op in OPERATORS:
                if not op.applies(fix):
                    continue
                with self.subTest(fixture=fix.name, operator=op.name):
                    result = self._rejection(op.apply(fix, copy.deepcopy(base)))
                    self.assertNotIsInstance(result, (Theorem, Refutation), f"{op.name} left {fix.name} valid: {op.why}")
                    if op.expect == DECODE_ERROR:
                        self.assertEqual(result, DECODE_ERROR, op.why)
                    elif op.expect == HASH_MISMATCH:
                        self.assertIsInstance(result, HashMismatch, op.why)
                    else:
                        self.assertIsInstance(result, Rejection, op.why)

    def test_perturbing_a_load_bearing_rational_breaks_an_exact_check(self):
        fix = mutations.BY_NAME["r2_ldl"]
        op = next(o for o in OPERATORS if o.name == "perturb_load_bearing_rational")
        result = verify_envelope(op.apply(fix, copy.deepcopy(_load(fix.name))))
        self.assertIsInstance(result, Rejection)
        self.assertIn("Gram", result.reason)

    def test_editing_the_stored_statement_fails_the_hash_before_the_kernel(self):
        fix = mutations.BY_NAME["r6_binomial"]
        op = next(o for o in OPERATORS if o.name == "edit_stored_statement_byte")
        result = verify_envelope(op.apply(fix, copy.deepcopy(_load(fix.name))))
        self.assertIsInstance(result, HashMismatch)
        self.assertNotEqual(result.expected, result.actual)


class OperatorsBite(unittest.TestCase):
    def test_every_operator_fires_on_at_least_one_fixture(self):
        for op in OPERATORS:
            with self.subTest(operator=op.name):
                self.assertTrue(any(op.applies(f) for f in FIXTURES), f"{op.name} applies to no fixture")

    def test_every_operator_applies_to_an_instance(self):
        """An Instance nests a family certificate, so each way of breaking one must reach
        through it."""
        instances = [f for f in FIXTURES if isinstance(f.evidence.body, Instance)]
        self.assertTrue(instances, "there is an Instance fixture")
        for op in OPERATORS:
            with self.subTest(operator=op.name):
                self.assertTrue(all(op.applies(f) for f in instances), f"{op.name} skips an Instance fixture")


class Coverage(unittest.TestCase):
    """Derived from the rule registry, not a hand list: a rule or evidence kind with no
    fixture fails here."""

    def test_every_rule_has_a_valid_fixture(self):
        covered = {fix.rule for fix in FIXTURES}
        self.assertEqual(set(RULES), covered, "a registered rule has no fixture")

    def test_every_evidence_kind_has_a_fixture(self):
        bodies = {type(fix.evidence.body) for fix in FIXTURES}
        self.assertLessEqual(set(PROOF_RULE), bodies, "a proof evidence type has no fixture")
        self.assertLessEqual(set(REFUTATION_RULE), bodies, "a refutation evidence type has no fixture")
        self.assertIn(Instance, bodies, "Instance evidence, accepted for every goal, has no fixture")

    def test_every_lemma_has_a_fixture_of_each_kind(self):
        """check proves a lemma over the RangeHyp box for a theorem and at the point for a
        refutation, so each needs its own fixture."""
        wanted = {lemma.evidence for lemma in LEMMAS.values()}
        for kind in ("theorem", "refutation"):
            proven = {type(dr.proof) for fix in FIXTURES if fix.kind == kind for dr in fix.evidence.defined}
            self.assertLessEqual(wanted, proven, f"a registered lemma has no {kind} fixture exercising it")


if __name__ == "__main__":
    unittest.main()
