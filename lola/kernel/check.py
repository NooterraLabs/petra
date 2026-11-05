"""The kernel's single entry point: check(statement, evidence) -> CheckResult.

Results are issued, not constructed. A Theorem or a Refutation is a bare handle with no
fields of its own: its data lives in `_ISSUED`, a kernel-private table keyed by the
handle's identity, and its properties read from there. So:

- calling Theorem(...) raises, and object.__new__(Theorem) gives a handle with no record;
- a handle has no attribute that assignment, even object.__setattr__, can change;
- copy, deepcopy and pickle raise, and dataclasses.replace does not apply;
- `is_issued(x)` is True only for a handle `check` returned.

Verdict types (lola/verdict.py) accept a theorem or refutation only when `is_issued`
says so, so a PASS without kernel-checked theorems cannot be built or laundered.

Rule dispatch goes through the registry tables in kernel/rules. This module names no
rule, so a new rule, or a new QuantityDef with its lemma, never edits it.
"""
from __future__ import annotations

import weakref
from dataclasses import dataclass
from typing import Union

from .codec import DecodeError, decode_evidence, decode_statement, encode_evidence, encode_statement, evidence_hash, statement_hash
from .evaluate import free_syms
from .evidence import Evidence, Point
from .interval import Interval
from .rules import GOAL_RULE, LEMMAS, Fault, Invalid
from .terms import DefinedHyp, RangeHyp, Statement


@dataclass(frozen=True, slots=True)
class _TheoremRecord:
    statement: Statement
    statement_hash: str
    evidence_hash: str
    rule: str
    labels: frozenset[str]
    defined_ranges: tuple[tuple[str, Interval], ...]


@dataclass(frozen=True, slots=True)
class _RefutationRecord:
    statement: Statement
    statement_hash: str
    evidence_hash: str
    rule: str
    labels: frozenset[str]
    point: Point


_ISSUED: "weakref.WeakKeyDictionary[_Issued, object]" = weakref.WeakKeyDictionary()


class _Issued:
    """Base of the two kernel results. Instances hold nothing but a weak-reference slot."""

    __slots__ = ("__weakref__",)

    def __new__(cls, *args: object, **kwargs: object) -> "_Issued":
        raise TypeError(f"{cls.__name__} can only be created by lola.kernel.check")

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __reduce_ex__(self, protocol: object) -> object:
        raise TypeError(f"{type(self).__name__} cannot be copied or pickled")

    def _record(self):
        record = _ISSUED.get(self)
        if record is None:
            raise TypeError(f"this {type(self).__name__} was not issued by lola.kernel.check")
        return record

    @property
    def statement(self) -> Statement:
        return self._record().statement

    @property
    def statement_hash(self) -> str:
        return self._record().statement_hash

    @property
    def evidence_hash(self) -> str:
        return self._record().evidence_hash

    @property
    def rule(self) -> str:
        return self._record().rule

    @property
    def labels(self) -> frozenset[str]:
        """The RangeHyp labels of the statement: exactly the facts the result depends on,
        because check rejects unused hypotheses."""
        return self._record().labels

    def __repr__(self) -> str:
        record = _ISSUED.get(self)
        if record is None:
            return f"<unissued {type(self).__name__}>"
        return f"<{type(self).__name__} {record.rule} {record.statement_hash}>"


class Theorem(_Issued):
    """The statement holds. `defined_ranges` records the ranges proven for DefinedHyps."""

    __slots__ = ()

    @property
    def defined_ranges(self) -> tuple[tuple[str, Interval], ...]:
        return self._record().defined_ranges


class Refutation(_Issued):
    """The statement is false: at `point`, which lies in every RangeHyp range, the goal
    fails. The statement has no DefinedHyp."""

    __slots__ = ()

    @property
    def point(self) -> Point:
        return self._record().point


def _issue(cls: type, record: object) -> _Issued:
    handle = object.__new__(cls)
    _ISSUED[handle] = record
    return handle


def _issue_theorem(statement: Statement, statement_hash: str, evidence_hash: str, rule: str,
                   labels: frozenset[str], defined_ranges: tuple[tuple[str, Interval], ...]) -> Theorem:
    """Kernel-private. Only `check` calls it; tests call it to obtain a genuine handle."""
    return _issue(Theorem, _TheoremRecord(statement, statement_hash, evidence_hash, rule, labels, defined_ranges))


def _issue_refutation(statement: Statement, statement_hash: str, evidence_hash: str, rule: str,
                      labels: frozenset[str], point: Point) -> Refutation:
    """Kernel-private. Only `check` calls it; tests call it to obtain a genuine handle."""
    return _issue(Refutation, _RefutationRecord(statement, statement_hash, evidence_hash, rule, labels, point))


def is_issued(result: object) -> bool:
    """True only for a Theorem or Refutation that `check` returned in this process."""
    return type(result) in (Theorem, Refutation) and result in _ISSUED


@dataclass(frozen=True, slots=True)
class Rejection:
    """The evidence does not check. Not issued: anyone may report a failure, and a
    rejection never proves anything. `rule` is None when the statement failed before a
    rule was chosen."""

    statement_hash: str
    rule: str | None
    fault: Fault

    @property
    def reason(self) -> str:
        return self.fault.reason


CheckResult = Union[Theorem, Refutation, Rejection]


def check(statement: Statement, evidence: Evidence) -> CheckResult:
    """Decide whether `evidence` proves or refutes `statement`.

    Never raises for bad evidence or a bad statement: every failure, including
    arithmetic errors inside a rule, becomes a Rejection, and an exception can only
    replace a result by a Rejection, never produce one. Every table below comes from
    kernel/rules. The statement hash is empty when the statement does not encode.

    Why a Theorem means the statement holds. Let B be the box of RangeHyp ranges. Each
    DefinedHyp d names a quantity q_d(h), and its lemma proves q_d(h) in [lo_d, hi_d] for
    every h in B. The rule then proves the goal at every point of B x prod_d [lo_d, hi_d],
    because a rule treats each symbol of the box it is given as ranging over its whole
    interval, independently of the others. The point (h, q(h)) lies in that product, so
    the goal holds at it, which is what the statement asserts for h. Forgetting how q_d
    depends on h is a deliberate relaxation: it can cost a proof, never soundness.

    Why a Refutation means it fails. Refutation evidence is accepted only for a
    statement with no DefinedHyp, and its point must assign every RangeHyp a value inside
    its range, so the point is in B. The rule shows the goal false there.
    """
    try:
        digest = statement_hash(statement)
    except Exception as exc:
        return Rejection("", None, Invalid(f"the statement does not encode: {exc}"))
    spec = None
    try:
        reason = well_formed(statement)
        if reason is not None:
            return Rejection(digest, None, Invalid(reason))
        spec = GOAL_RULE[type(statement.goal)]
        return _decide(statement, digest, evidence, spec)
    except Exception as exc:
        return Rejection(digest, spec.id if spec else None, Invalid(f"{type(exc).__name__}: {exc}"))


def _decide(statement: Statement, digest: str, evidence: Evidence, spec) -> CheckResult:
    def reject(fault: Fault) -> Rejection:
        return Rejection(digest, spec.id, fault)

    if decode_evidence(encode_evidence(evidence)) != evidence:
        return reject(Invalid("the evidence is not in canonical form"))
    box = {h.sym: Interval(h.lo, h.hi) for h in statement.hyps if isinstance(h, RangeHyp)}
    defined = [h for h in statement.hyps if isinstance(h, DefinedHyp)]
    claims = {claim.sym: claim for claim in evidence.defined}
    if len(claims) != len(evidence.defined) or set(claims) != {h.sym for h in defined}:
        return reject(Invalid("the evidence must give exactly one DefinedRange per DefinedHyp"))
    labels = frozenset(h.label for h in statement.hyps if isinstance(h, RangeHyp))
    body, ehash = evidence.body, evidence_hash(evidence)
    if type(body) in spec.proofs:
        ranges: dict[str, Interval] = {}
        for h in defined:
            lemma, claim = LEMMAS.get(type(h.definition)), claims[h.sym]
            if lemma is None or type(claim.proof) is not lemma.evidence:
                return reject(Invalid(f"no lemma proves a range for {h.sym} from {type(claim.proof).__name__}"))
            fault = lemma.prove(h.definition, claim, box)
            if fault is not None:
                return reject(fault)
            ranges[h.sym] = Interval(claim.lo, claim.hi)
        fault = spec.prove(statement.goal, body, {**box, **ranges})
        if fault is not None:
            return reject(fault)
        return _issue_theorem(statement, digest, ehash, spec.id, labels, tuple(sorted(ranges.items())))
    if type(body) not in spec.refutations:
        return reject(Invalid(f"{type(body).__name__} is not evidence for {spec.id}"))
    if defined:
        return reject(Invalid("a refutation needs a statement with no DefinedHyp"))
    if tuple(sym for sym, _ in body.point) != tuple(box) or not all(box[sym].contains(v) for sym, v in body.point):
        return reject(Invalid("the point must assign every RangeHyp, in order, a value inside its range"))
    fault = spec.refute(statement.goal, body, box)
    if fault is not None:
        return reject(fault)
    return _issue_refutation(statement, digest, ehash, spec.id, labels, body.point)


def well_formed(statement: Statement) -> str | None:
    """None if the statement satisfies the invariants listed in terms.py, else the reason.
    Also checks that hyps are sorted by sym with no duplicates. The free symbols of the
    goal exclude GOAL_RULE[type(goal)].binds(goal).

    Typing comes first: the statement must survive the strict codec unchanged, so every
    number is an exact Fraction or int, every matrix is canonical, and the goal is a
    registered Goal. Every RangeHyp label then names a fact some part of the statement
    uses, which is what makes Theorem.labels the exact footprint.
    """
    try:
        if decode_statement(encode_statement(statement)) != statement:
            return "the statement is not in canonical form"
    except (DecodeError, TypeError) as exc:
        return f"the statement is not a well-typed term: {exc}"
    names = [h.sym for h in statement.hyps]
    hyp_syms = set(names)
    if names != sorted(hyp_syms):
        return "hypotheses must be sorted by sym with no duplicates"
    if any(isinstance(h, RangeHyp) and h.lo > h.hi for h in statement.hyps):
        return "a RangeHyp has lo > hi"
    bound = GOAL_RULE[type(statement.goal)].binds(statement.goal)
    goal_syms = free_syms(statement.goal) - bound
    definition_syms = free_syms(tuple(h.definition for h in statement.hyps if isinstance(h, DefinedHyp)))
    if bound & hyp_syms:
        return f"the goal binds hypothesis symbols {sorted(bound & hyp_syms)}"
    if not definition_syms <= {h.sym for h in statement.hyps if isinstance(h, RangeHyp)}:
        return "a DefinedHyp definition may mention RangeHyp symbols only"
    if not goal_syms <= hyp_syms:
        return f"the goal mentions undeclared symbols {sorted(goal_syms - hyp_syms)}"
    unused = hyp_syms - goal_syms - definition_syms
    if unused:
        return f"unused hypotheses {sorted(unused)}"
    return None
