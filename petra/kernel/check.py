"""The kernel's single entry point: check(statement, evidence) -> CheckResult.

Results are issued, not constructed. A Theorem or a Refutation is a bare handle with no
fields of its own: its data lives in `_ISSUED`, a kernel-private table keyed by the
handle's identity, and its properties read from there. So:

- calling Theorem(...) raises, and object.__new__(Theorem) gives a handle with no record;
- a handle has no attribute that assignment, even object.__setattr__, can change;
- copy, deepcopy and pickle raise, and dataclasses.replace does not apply;
- `is_issued(x)` is True only for a handle `check` returned.

Verdict types (petra/verdict.py) accept a theorem or refutation only when `is_issued`
says so, so a PASS without kernel-checked theorems cannot be built or laundered.

Rule dispatch goes through the registry tables in kernel/rules. This module names no
rule, so a new rule, or a new QuantityDef with its lemma, never edits it.
"""
from __future__ import annotations

import weakref
from collections import OrderedDict
from dataclasses import dataclass
from fractions import Fraction
from typing import Union

from .codec import DecodeError, decode_as, decode_evidence, decode_statement, encode_evidence, encode_statement, hash_of
from .evaluate import free_syms, point_box, rename
from .evidence import Evidence, Instance, Point
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
        raise TypeError(f"{cls.__name__} can only be created by petra.kernel.check")

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __reduce_ex__(self, protocol: object) -> object:
        raise TypeError(f"{type(self).__name__} cannot be copied or pickled")

    def _record(self):
        record = _ISSUED.get(self)
        if record is None or type(record) is not _RECORD_OF.get(type(self)):
            raise TypeError(f"this {type(self).__name__} was not issued by petra.kernel.check")
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
    fails for the true value of every DefinedHyp there (see check)."""

    __slots__ = ()

    @property
    def point(self) -> Point:
        return self._record().point


_RECORD_OF = {Theorem: _TheoremRecord, Refutation: _RefutationRecord}
"""A handle is genuine only while its class matches the kind it was issued as, so
reassigning __class__ cannot turn a refutation into a theorem."""


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
    kind = _RECORD_OF.get(type(result))
    return kind is not None and type(_ISSUED.get(result)) is kind


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

    The statement is encoded once. The hash is taken from that encoding, and the
    statement must decode from it to a term equal to itself, which is what canonical
    means. From then on the kernel reads only the decoded copy, built from plain
    Fractions and ints, so the hash, the checked term and the issued result all come
    from the one encoding, and no caller object answers a comparison inside a rule. The
    equality guard itself compares with the caller's object, so a caller's subclass can
    answer that one comparison. The issued result is still about the decoded copy, so
    code outside the kernel should compare against `result.statement` with terms it
    built itself. Instance evidence is decided by `_instance`, for every goal.

    Why a Theorem means the statement holds. Let B be the box of RangeHyp ranges. Each
    DefinedHyp d names a quantity q_d(h), and its lemma proves q_d(h) in [lo_d, hi_d] for
    every h in B. The rule then proves the goal at every point of B x prod_d [lo_d, hi_d],
    because a rule treats each symbol of the box it is given as ranging over its whole
    interval, independently of the others. The point (h, q(h)) lies in that product, so
    the goal holds at it, which is what the statement asserts for h. Forgetting how q_d
    depends on h is a deliberate relaxation: it can cost a proof, never soundness.

    Why a Refutation means it fails. The statement says goal(h, q(h)) holds for every h
    in B. Refutation evidence names a point h0 that must assign every RangeHyp, in order,
    a value inside its range, so h0 is in B. Each DefinedHyp d comes with a range whose
    lemma, run over the degenerate box {h0}, proves q_d(h0) in [lo_d, hi_d]. The rule's
    refute then shows the goal fails at every point of {h0} x prod_d [lo_d, hi_d],
    treating each defined symbol as ranging over its whole interval as above, so it never
    rests on one representative value. The point (h0, q(h0)) lies in that product, so
    goal(h0, q(h0)) is false and the statement fails at h0. With no DefinedHyp the
    product is the point h0 itself.
    """
    try:
        encoded = encode_statement(statement)
        digest = hash_of(encoded)
    except Exception as exc:
        return Rejection("", None, Invalid(f"the statement does not encode: {exc}"))
    spec = None
    try:
        try:
            canonical = decode_statement(encoded)
        except DecodeError as exc:
            return Rejection(digest, None, Invalid(f"the statement is not a well-typed term: {exc}"))
        if canonical != statement:
            return Rejection(digest, None, Invalid("the statement is not in canonical form"))
        statement = canonical
        spec = GOAL_RULE[type(statement.goal)]
        if type(evidence) is Evidence and type(evidence.body) is Instance:
            return _instance(statement, digest, evidence, spec)
        reason = well_formed(statement)
        if reason is not None:
            return Rejection(digest, None, Invalid(reason))
        return _decide(statement, digest, evidence, spec)
    except Exception as exc:
        return Rejection(digest, spec.id if spec else None, Invalid(f"{type(exc).__name__}: {exc}"))


def _decide(statement: Statement, digest: str, evidence: Evidence, spec) -> CheckResult:
    def reject(fault: Fault) -> Rejection:
        return Rejection(digest, spec.id, fault)

    encoded = encode_evidence(evidence)
    canonical = decode_evidence(encoded)
    if canonical != evidence:
        return reject(Invalid("the evidence is not in canonical form"))
    # Rules see only the decoded copy, built from plain Fractions and ints, so a value
    # whose class overrides comparison cannot answer the rule's checks for itself.
    evidence, ehash = canonical, hash_of(encoded)
    box = {h.sym: Interval(h.lo, h.hi) for h in statement.hyps if isinstance(h, RangeHyp)}
    defined = [h for h in statement.hyps if isinstance(h, DefinedHyp)]
    claims = {claim.sym: claim for claim in evidence.defined}
    if len(claims) != len(evidence.defined) or set(claims) != {h.sym for h in defined}:
        return reject(Invalid("the evidence must give exactly one DefinedRange per DefinedHyp"))
    labels = frozenset(h.label for h in statement.hyps if isinstance(h, RangeHyp))
    body = evidence.body
    refuting = type(body) not in spec.proofs
    if refuting:
        if type(body) not in spec.refutations:
            return reject(Invalid(f"{type(body).__name__} is not evidence for {spec.id}"))
        if tuple(sym for sym, _ in body.point) != tuple(box) or not all(box[sym].contains(v) for sym, v in body.point):
            return reject(Invalid("the point must assign every RangeHyp, in order, a value inside its range"))
        box = point_box(body.point)
    ranges: dict[str, Interval] = {}
    memos: dict[type, dict] = {}
    for h in defined:
        lemma, claim = LEMMAS.get(type(h.definition)), claims[h.sym]
        if lemma is None or type(claim.proof) is not lemma.evidence:
            return reject(Invalid(f"no lemma proves a range for {h.sym} from {type(claim.proof).__name__}"))
        fault = lemma.prove(h.definition, claim, box, memos.setdefault(lemma.defines, {}))
        if fault is not None:
            return reject(fault)
        ranges[h.sym] = Interval(claim.lo, claim.hi)
    fault = (spec.refute if refuting else spec.prove)(statement.goal, body, {**box, **ranges})
    if fault is not None:
        return reject(fault)
    if refuting:
        return _issue_refutation(statement, digest, ehash, spec.id, labels, body.point)
    return _issue_theorem(statement, digest, ehash, spec.id, labels, tuple(sorted(ranges.items())))


_FAMILIES: "OrderedDict[tuple[str, str], Theorem]" = OrderedDict()
"""Family theorems that Instance checks used, keyed by (statement hash, evidence hash),
least recently used first. Only `_family` writes it, and only a Theorem `check` just
issued whose own hashes are the key. Canonical text is one to one (codec refuses the
surrogate code points that would make two strings share it), so an entry is the
kernel's verdict on exactly the statement and evidence its key names, up to a sha256
collision. `_instance` still reads the statement from the theorem, never from the
Instance's spelling of it, so even a colliding key could only lend a theorem the kernel
checked."""

FAMILY_MEMO_LIMIT = 64


def forget_families() -> None:
    """Empty the family memo. It costs time only: the next Instance checks its family again."""
    _FAMILIES.clear()


def _family(key: tuple[str, str], body: dict) -> Theorem | str:
    """The family Theorem for `key`, the hashes of `body`, the Instance's encoding, at
    its family statement and evidence, or why there is none. A family not yet in the memo
    is decoded from that encoding and checked, so no caller object is read again."""
    found = _FAMILIES.get(key)
    if found is not None:
        _FAMILIES.move_to_end(key)
        return found
    try:
        statement, evidence = decode_statement(body["statement"]), decode_evidence(body["evidence"])
    except DecodeError as exc:
        return f"the family does not decode: {exc}"
    result = check(statement, evidence)
    if isinstance(result, Refutation):
        return "the family evidence refutes the family statement, and a refutation has no instances"
    if isinstance(result, Rejection):
        return f"the family evidence does not check: {result.reason}"
    if (result.statement_hash, result.evidence_hash) != key:
        return "the family statement or evidence encoded differently when it was checked"
    _FAMILIES[key] = result
    if len(_FAMILIES) > FAMILY_MEMO_LIMIT:
        _FAMILIES.popitem(last=False)
    return result


def _instance(query: Statement, digest: str, evidence: Evidence, spec) -> CheckResult:
    """Accept `query`, the decoded statement, as an instance of a family theorem.

    The evidence is encoded once, and everything below reads that encoding or the
    kernel's own results, never the caller's evidence object again. Checks: (a) the
    family evidence checks to a Theorem for the family statement F, by a full check of
    the decoded encoding, memoised in _FAMILIES; (b) the renaming rho maps the symbols
    of F, its hypotheses and the variables its goal binds, one to one onto distinct
    symbols; (c) sorted by their renamed symbols, the hypotheses of F pair one to one
    with those of the query Q, of the same kind, with every DefinedHyp definition equal
    to rho of the family's and every Q range inside its family range, and Q's goal binds
    rho of what F's binds; (d) Q's goal is rho of F's; (e) the encoded family evidence is
    Evidence whose body is not an Instance, so an Instance is one level deep. Depth is a
    limit on cost, not on soundness: a valid chain of instances would still be true.
    Labels are opaque and not compared. F is always the statement of the family
    theorem, never the Instance's own spelling of it.

    Why a Theorem for Q means Q holds. A statement refers to a symbol only by name, as a
    Sym or as a str field named sym (tests/test_kernel_instance.py pins that
    convention), so rename moves every reference. The family theorem says goal_F(h, q(h))
    for every h in B_F, the box of F's RangeHyp ranges, where q_d(h) is the quantity
    DefinedHyp d names. Take h' in B_Q and put h = rho^-1(h'): h gives each family
    RangeHyp s the value h' gives rho(s), which lies in Q's range for rho(s) and so in
    F's range for s, hence h is in B_F. Each DefinedHyp rho(d) of Q is defined by
    rho(definition of d), so it names the same function of the renamed arguments and
    q'_rho(d)(h') = q_d(h). Q's goal is rho(goal_F). Renaming every symbol by one
    bijection changes no meaning, provided no bound variable meets a hypothesis, and the
    variables Q binds are rho of F's, which are disjoint from F's hypotheses, so they are
    disjoint from Q's. So goal_Q(h', q'(h')) is goal_F(h, q(h)), which holds. The
    defined ranges F's theorem proved hold at h, so their renamed copies hold at h'.
    Symbol order shapes only the layout of evidence (vertex order), never meaning: no
    term refers to a hypothesis by its position. Every goal's meaning at a point depends
    on that point alone, never on the box around it, so narrowing ranges keeps each
    point's meaning. R5 reads its support from ranges, and a narrower support only
    shrinks the set of distributions the bound must cover.

    Q is also well formed, so its labels are its exact footprint. Sorted hypotheses with
    no duplicates and lo <= hi are checked here, and the binders are disjoint as above.
    The other conditions of well_formed (definitions mention RangeHyps only, the goal
    mentions declared symbols only, no hypothesis is unused) are statements about free
    symbols and the hypotheses that declare them, which a bijective renaming preserves
    because free_syms commutes with rename, and F satisfies them.

    The issued Theorem carries the family rule id, Q's own labels, the family's defined
    ranges renamed and copied down to new Fractions, so no two issued results share a
    mutable object, and the hash of the Instance evidence.
    """
    def reject(reason: str) -> Rejection:
        return Rejection(digest, spec.id, Invalid(reason))

    encoded = encode_evidence(evidence)
    ehash, body = hash_of(encoded), encoded["body"]
    if body["t"] != "instance":
        return reject("the evidence changed while it was read")
    if encoded["defined"]:
        return reject("an Instance takes its defined ranges from the family theorem, so it lists none")
    inner = body["evidence"]
    if type(inner) is not dict or inner.get("t") != "evidence" or inner["body"]["t"] == "instance":
        return reject("the family evidence must be Evidence that is not itself an Instance")
    family = _family((hash_of(body["statement"]), hash_of(inner)), body)
    if isinstance(family, str):
        return reject(family)
    renaming = decode_as(body["renaming"], tuple[tuple[str, str], ...])
    rho, fam = dict(renaming), family.statement
    binds = GOAL_RULE[type(fam.goal)].binds(fam.goal)
    if [s for s, _ in renaming] != sorted({h.sym for h in fam.hyps} | binds) or len(set(rho.values())) != len(rho):
        return reject("the renaming must map every family symbol once, sorted, to distinct query symbols")
    renamed = sorted((rename(h, rho) for h in fam.hyps), key=lambda h: h.sym)
    if [(type(h), h.sym) for h in renamed] != [(type(h), h.sym) for h in query.hyps]:
        return reject("the hypotheses do not pair one to one with the family's, renamed")
    for f, q in zip(renamed, query.hyps):
        if isinstance(q, RangeHyp) and not f.lo <= q.lo <= q.hi <= f.hi:
            return reject(f"{q.sym} ranges over [{q.lo}, {q.hi}], which is not inside the family range [{f.lo}, {f.hi}]")
        if isinstance(q, DefinedHyp) and q.definition != f.definition:
            return reject(f"{q.sym} is not defined as its family counterpart is, renamed")
    if spec.binds(query.goal) != {rho[x] for x in binds} or query.goal != rename(fam.goal, rho):
        return reject("the goal is not the family goal renamed")
    labels = frozenset(h.label for h in query.hyps if isinstance(h, RangeHyp))
    ranges = tuple(sorted((rho[sym], Interval(Fraction(iv.lo), Fraction(iv.hi))) for sym, iv in family.defined_ranges))
    return _issue_theorem(query, digest, ehash, family.rule, labels, ranges)


def well_formed(statement: Statement) -> str | None:
    """None if the statement satisfies the invariants listed in terms.py, else the reason.
    Also checks that hyps are sorted by sym with no duplicates. The free symbols of the
    goal exclude GOAL_RULE[type(goal)].binds(goal).

    `check` calls it on the decoded copy, so typing is settled first: every number is an
    exact Fraction or int, every matrix is canonical, and the goal is a registered Goal.
    Every RangeHyp label then names a fact some part of the statement uses, which is
    what makes Theorem.labels the exact footprint.
    """
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
