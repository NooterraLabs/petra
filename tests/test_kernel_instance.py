"""Instance evidence: a query checked as a renamed instance of a family theorem. Owner: K.

The family is F in [4, 8] with q = s*_0 = 3F/4 of min s0^2 + 3 s1^2 subject to
s0 + s1 = F, so q spans exactly [3, 6] and the goal 3 <= q <= 6 holds. Queries rename F
to P and q to z. tests/test_kernel_redteam.py holds the forgeries. This file pins what an
accepted Instance yields, how a renaming is read, the symbol convention renaming relies
on, and the family memo.
"""
import sys
import unittest
from fractions import Fraction as Q
from typing import get_args, get_type_hints
from unittest import mock

from petra.kernel import (
    TAGS,
    Add,
    Const,
    DefinedHyp,
    DefinedRange,
    Evidence,
    Instance,
    Interval,
    Leaf,
    Matrix,
    Neg,
    RangeHyp,
    Rejection,
    Statement,
    Sym,
    Theorem,
    check,
    decode_statement,
    encode_statement,
    evidence_hash,
    forget_families,
    rules,
    statement_hash,
)
from petra.kernel.check import FAMILY_MEMO_LIMIT
from petra.kernel.rules.r3_hypercircle import HypercircleFields, MinimizerComponent, QuadraticProblem
from petra.kernel.rules.r4_enclosure import AllNonpositive, Enclosure
from tests import mutations

KERNEL_CHECK = sys.modules["petra.kernel.check"]
"""The module, which the package's `check` function shadows as an attribute."""


def c(v) -> Const:
    return Const(Q(v))


PAIR = Matrix(1, 2, ((0, 0, Q(1)), (0, 1, Q(1))))
EXACT = HypercircleFields(s=((Q(3), Q(1)), (Q(6), Q(2))), u=((Q(3),), (Q(6),)))


def minimizer(load: str, scale=1) -> MinimizerComponent:
    return MinimizerComponent(QuadraticProblem(B=PAIR, f=(Sym(load),), w=(c(1), c(3))), 0, c(scale))


def between(q: str, top=6, bottom=None) -> AllNonpositive:
    """q - top <= 0 and 3 - q <= 0. `bottom` replaces the constant -top when given."""
    first = Const(bottom) if bottom is not None else c(-top)
    return AllNonpositive(exprs=(Add((Sym(q), first)), Add((c(3), Neg(Sym(q))))))


FAMILY = Statement(hyps=(RangeHyp("F", Q(4), Q(8), "in:F"), DefinedHyp("q", minimizer("F"))), goal=between("q"))
FAMILY_EVIDENCE = Evidence(Enclosure(Leaf()), (DefinedRange("q", Q(3), Q(6), EXACT),))
RHO = (("F", "P"), ("q", "z"))


def query(lo, hi, top=6, label="in:P") -> Statement:
    return Statement(hyps=(RangeHyp("P", Q(lo), Q(hi), label), DefinedHyp("z", minimizer("P"))), goal=between("z", top))


def instance(statement=FAMILY, evidence=FAMILY_EVIDENCE, renaming=RHO, defined=()) -> Evidence:
    return Evidence(Instance(statement, evidence, renaming), defined)


class Base(unittest.TestCase):
    def assertRejected(self, result, needle):
        self.assertIsInstance(result, Rejection, f"expected a Rejection, got {type(result).__name__}")
        self.assertIn(needle, result.reason)

    def assertTheorem(self, result):
        self.assertIsInstance(result, Theorem, getattr(result, "reason", ""))
        return result


class IssuedTheorem(Base):
    def test_the_theorem_is_about_the_query_under_the_family_rule(self):
        q, evidence = query(5, 7), instance()
        result = self.assertTheorem(check(q, evidence))
        self.assertEqual(result.statement, q)
        self.assertEqual(result.statement_hash, statement_hash(q))
        self.assertEqual(result.evidence_hash, evidence_hash(evidence))
        self.assertEqual(result.rule, "R4", "the family goal is an R4 goal")
        self.assertEqual(result.labels, frozenset({"in:P"}), "the query's own labels, not the family's in:F")
        self.assertEqual(result.defined_ranges, (("z", Interval(Q(3), Q(6))),), "the family proved q in [3, 6], renamed to z")

    def test_an_instance_that_lists_defined_ranges_is_rejected(self):
        listed = instance(defined=(DefinedRange("z", Q(3), Q(6), EXACT),))
        self.assertRejected(check(query(5, 7), listed), "lists none")
        self.assertTheorem(check(query(5, 7), instance()))

    def test_the_family_evidence_must_be_evidence(self):
        self.assertRejected(check(query(5, 7), instance(evidence=Enclosure(Leaf()))), "must be Evidence")
        self.assertTheorem(check(query(5, 7), instance(evidence=FAMILY_EVIDENCE)))


class Renamings(Base):
    def test_the_renaming_lists_every_family_symbol_once_in_order(self):
        for bad in [(("q", "z"), ("F", "P")), (("F", "P"),), (("F", "P"), ("G", "G"), ("q", "z")), (("F", "P"), ("F", "P"), ("q", "z"))]:
            with self.subTest(renaming=bad):
                self.assertRejected(check(query(5, 7), instance(renaming=bad)), "every family symbol once")
        self.assertTheorem(check(query(5, 7), instance(renaming=RHO)))

    def test_a_renaming_may_change_the_order_of_symbols(self):
        # F to b and q to a puts the defined hypothesis first.
        reordered = Statement(hyps=(DefinedHyp("a", minimizer("b")), RangeHyp("b", Q(5), Q(7), "in:b")), goal=between("a"))
        self.assertTheorem(check(reordered, instance(renaming=(("F", "b"), ("q", "a")))))
        self.assertRejected(check(reordered, instance(renaming=(("F", "a"), ("q", "b")))), "pair one to one")

    def test_labels_are_opaque_but_symbols_are_not(self):
        result = self.assertTheorem(check(query(5, 7, label="reg:anything"), instance()))
        self.assertEqual(result.labels, frozenset({"reg:anything"}))
        other_symbol = Statement(hyps=(RangeHyp("Q", Q(5), Q(7), "in:P"), DefinedHyp("z", minimizer("Q"))), goal=between("z"))
        self.assertRejected(check(other_symbol, instance()), "pair one to one")


def mentions_str(annotation) -> bool:
    return annotation is str or any(mentions_str(a) for a in get_args(annotation))


SYMBOL_FIELDS = {("sym", "name"), ("range_hyp", "sym"), ("defined_hyp", "sym"), ("random_var", "sym")}
"""Where a statement names a symbol, by reading terms.py and the rule modules: a Sym's
name, and the binders, each a str field named sym."""

OPAQUE_FIELDS = {("range_hyp", "label")}

EVIDENCE_FIELDS = {
    ("split", "sym"), ("defined_range", "sym"), ("instance", "renaming"),
    ("farkas_ray", "point"), ("negative_direction", "point"), ("hypercircle_violation", "point"), ("point_witness", "point"),
}
"""Evidence names symbols too, but an Instance never renames evidence."""


def symbols(obj) -> set:
    """Every symbol a statement's JSON names: Sym names and values under a key sym."""
    if isinstance(obj, list):
        return set().union(set(), *map(symbols, obj))
    if not isinstance(obj, dict):
        return set()
    found = set().union(set(), *map(symbols, obj.values()))
    if obj.get("t") == "sym":
        found.add(obj["name"])
    if isinstance(obj.get("sym"), str):
        found.add(obj["sym"])
    return found


def renamed(obj, rho: dict):
    """The same renaming spelled on JSON, independently of the kernel's."""
    if isinstance(obj, list):
        return [renamed(x, rho) for x in obj]
    if not isinstance(obj, dict):
        return obj
    out = {key: renamed(value, rho) for key, value in obj.items()}
    if obj.get("t") == "sym":
        out["name"] = rho[obj["name"]]
    if isinstance(obj.get("sym"), str):
        out["sym"] = rho[obj["sym"]]
    return out


def first_sym(obj) -> dict | None:
    if isinstance(obj, dict):
        if obj.get("t") == "sym":
            return obj
        obj = list(obj.values())
    if isinstance(obj, list):
        for item in obj:
            found = first_sym(item)
            if found is not None:
                return found
    return None


class SymbolConvention(Base):
    """The soundness argument in kernel/check.py (_instance) needs a renaming to move
    every reference to a symbol. Statements refer to symbols only through the fields
    listed here, so a new str field fails this test until it is placed."""

    def test_statements_name_symbols_only_through_the_fields_renaming_moves(self):
        aliases = {name: getattr(rules, name) for name in ("Goal", "ProofEvidence", "RefutationEvidence", "QuantityDef", "LemmaEvidence")}
        found = {(tag, name) for tag, cls in TAGS.items() for name, annotation in get_type_hints(cls, localns=aliases).items() if mentions_str(annotation)}
        self.assertEqual(found, SYMBOL_FIELDS | OPAQUE_FIELDS | EVIDENCE_FIELDS, "place every str field in the term language")

    def test_every_goal_survives_a_renaming_that_reverses_symbol_order(self):
        theorems = [f for f in mutations.FIXTURES if f.kind == "theorem" and not isinstance(f.evidence.body, Instance)]
        self.assertEqual({f.rule for f in theorems}, set(rules.RULES), "a theorem fixture for every rule")
        for fix in theorems:
            with self.subTest(fixture=fix.name):
                encoded = encode_statement(fix.statement)
                names = sorted(symbols(encoded))
                rho = {s: f"v{len(names) - i:02d}" for i, s in enumerate(names)}
                spelled = renamed(encoded, rho)
                spelled["hyps"].sort(key=lambda h: h["sym"])
                evidence = instance(fix.statement, fix.evidence, tuple(sorted(rho.items())))
                result = self.assertTheorem(check(decode_statement(spelled), evidence))
                self.assertEqual(result.rule, fix.rule)
                missed = first_sym(spelled["goal"])
                if missed is None:
                    continue
                missed["name"] = next(old for old, new in rho.items() if new == missed["name"])
                self.assertRejected(check(decode_statement(spelled), evidence), "not the family goal renamed")


class FamilyMemo(Base):
    """The kernel remembers family theorems by the hashes of the family statement and
    evidence an Instance spells, so a remembered family is not checked again. A family
    is checked as it was encoded, so the caller's objects are never read again."""

    def setUp(self):
        forget_families()

    def family_checks(self, statement=FAMILY) -> int:
        """Evidence decodings while the kernel checks query(5, 7) as an Instance of
        `statement`: two when it checks the family (decoding it from the Instance, then
        checking it), none when it remembers the family theorem."""
        with mock.patch.object(KERNEL_CHECK, "decode_evidence", wraps=KERNEL_CHECK.decode_evidence) as spy:
            self.assertTheorem(check(query(5, 7), instance(statement=statement)))
        return spy.call_count

    def test_a_failed_family_check_stores_nothing(self):
        too_narrow = Evidence(Enclosure(Leaf()), (DefinedRange("q", Q(3), Q(5), EXACT),))
        for _ in range(2):
            self.assertRejected(check(query(5, 7), instance(evidence=too_narrow)), "does not check")
            self.assertTheorem(check(query(5, 7), instance()))

    def test_a_family_is_checked_as_it_was_encoded(self):
        class Shifty(Q):
            """Spells -6 the first time its numerator is read, and its value -7 after."""
            read = False

            @property
            def numerator(self):
                if self.read:
                    return self._numerator
                self.read = True
                return -6

        # The encoding says q <= 6, which the family evidence proves. The query claims
        # z <= 7, which the object later reports, and is not that theorem renamed.
        liar = Statement(hyps=FAMILY.hyps, goal=between("q", bottom=Shifty(-7)))
        self.assertRejected(check(query(5, 7, top=7), instance(statement=liar)), "not the family goal renamed")
        self.assertTheorem(check(query(5, 7), instance()))

    def test_the_memo_is_bounded_least_recently_used_and_forgettable(self):
        def others(count: int, start: int) -> None:
            for k in range(start, start + count):
                goal = AllNonpositive(exprs=(Add((Sym("x"), c(-2 - k))),))
                family = Statement(hyps=(RangeHyp("x", Q(0), Q(1), "in:x"),), goal=goal)
                renamed_query = Statement(hyps=(RangeHyp("y", Q(0), Q(1), "in:y"),), goal=AllNonpositive(exprs=(Add((Sym("y"), c(-2 - k))),)))
                self.assertTheorem(check(renamed_query, instance(family, Evidence(Enclosure(Leaf())), (("x", "y"),))))

        miss = self.family_checks()
        self.assertEqual(miss, 2, "the first Instance decodes the family and checks it")
        self.assertEqual(self.family_checks(), 0, "a remembered family is not checked again")
        others(FAMILY_MEMO_LIMIT - 1, 0)
        self.assertEqual(self.family_checks(), 0, "a full memo still holds the family")
        others(1, FAMILY_MEMO_LIMIT - 1)
        self.assertEqual(self.family_checks(), 0, "the most recently used family outlives an eviction")
        others(FAMILY_MEMO_LIMIT, FAMILY_MEMO_LIMIT)
        self.assertEqual(self.family_checks(), miss, "a family pushed out of the bounded memo is checked again")
        forget_families()
        self.assertEqual(self.family_checks(), miss, "forget_families empties the memo")

if __name__ == "__main__":
    unittest.main()
