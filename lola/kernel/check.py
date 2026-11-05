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

from .evidence import Evidence, Point
from .interval import Interval
from .rules import Fault
from .terms import Statement


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
    arithmetic errors inside a rule, becomes a Rejection. Every table below comes from
    kernel/rules.

    TODO:
      reason = well_formed(statement)                       -> Rejection(Invalid) on failure
      spec = GOAL_RULE.get(type(goal))                       -> Rejection(Invalid) if None
      box = {h.sym: Interval(h.lo, h.hi) for RangeHyp}
      for each DefinedHyp d:
          dr = the unique evidence.defined entry for d.sym  -> Rejection(Invalid) otherwise
          lemma = LEMMAS.get(type(d.definition))             -> Rejection(Invalid) if None
          require type(dr.proof) is lemma.evidence
          fault = lemma.prove(d.definition, dr, box)         -> Rejection(fault) on a fault
          box[d.sym] = Interval(dr.lo, dr.hi)
      if type(body) in spec.proofs:
          fault = spec.prove(goal, body, box)
          return Rejection(fault) or _issue_theorem(...)
      elif type(body) in spec.refutations:
          statement must have no DefinedHyp; point must assign every RangeHyp inside
          its range
          fault = spec.refute(goal, body, box)
          return Rejection(fault) or _issue_refutation(...)
      else:
          Rejection(Invalid(f"{type(body).__name__} is not evidence for {spec.id}"))
    KernelArithmeticError and NotAffine raised inside a rule become Rejection(Invalid).
    """
    raise NotImplementedError


def well_formed(statement: Statement) -> str | None:
    """None if the statement satisfies the invariants listed in terms.py, else the reason.
    Also checks that hyps are sorted by sym with no duplicates. The free symbols of the
    goal exclude GOAL_RULE[type(goal)].binds(goal)."""
    raise NotImplementedError
