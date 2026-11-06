"""Verdicts and their assembly from kernel results. Trusted.

Construction rules, enforced in __post_init__ so an illegal verdict cannot exist:
- Pass needs a Scope, a non-empty Footprint and at least one theorem the kernel issued.
  Every label on every theorem must resolve: "par:" labels to a scope parameter, "dsg:"
  labels to the design itself, every other label to a footprint premise. Theorems are
  sealed by the kernel (lola/kernel/check.py), so a Pass cannot be built from claims, a
  copied theorem or an altered one.
- Fail needs an issued Refutation of the obligation's own statement, a theorem for each
  validity row of its model (over the box, or at the refutation's point: at_point), and
  a footprint that names every premise the refuted statement and those theorems rest on.
- Unknown needs at least one Open item, and every Open item names at least one typed
  Need (lola/models/base.py), so "UNKNOWN" always says what would close it.
- Marginal needs at least one WithinMargin outcome, each carrying the claim's own
  theorem, and a footprint that names every premise each of their refutations rests on,
  as a Fail's does, and every premise each of its theorems rests on, as a Pass's does.
- Discharged and Refuted bind the kernel result to the obligation: the issued result's
  statement must equal the obligation's statement. Each also carries one issued theorem
  per validity obligation (models.base.ValidityRow), in order: Discharged and a
  WithinMargin with a theorem over the whole box, Refuted over the box or at the
  refutation's point (_validity_bound). A model used outside its validity range proves
  and refutes nothing. A Discharged claim with a margin
  carries its margin obligation, and the margin statement's theorem when it was proved.
- WithinMargin binds an issued Refutation to the margin obligation, and the margin
  obligation to the claim's (margin_pair_fault): same model, same goal type, the same
  hypotheses in the same order (so the same load case), and a requirement equal to the
  claim's with its criterion tightened by its own margin
  (models.base.Criterion.tightened). So a margin point can only be a certified point
  where the claimed quantity is within the claim's own margin of its bound. A theorem it
  carries is bound to the claim's obligation.
- Open may carry one such margin point without a theorem: the claim is undecided, and
  the report shows where it comes within its margin.

Verdicts at a margin. A claim with `margin m` asks two things: does the claim hold, and
does the design come within m of its bound anywhere. FAIL when the claim is refuted.
MARGINAL when the claim is proved and a certified point lies within m of its bound.
PASS when the claim is proved and no point within m was found; the report says whether
the margin statement itself was proved (the claim holds with at least m to spare) or
is undecided. UNKNOWN when the claim is neither proved nor refuted, with the certified
point within m when one was found. A point within m without the claim's proof is never
MARGINAL: it says nothing about the rest of the box, where the claim may fail, and
MARGINAL ranks below UNKNOWN. The pipeline also tries every margin witness against the
claim, at every expression, so a point past the bound is a FAIL.

Why this decides a claim at tolerance m (delta-decidability, Gao, Avigad and Clarke
2012). If the quantity peaks at least m inside its bound, the claim has slack m, which a
fine enough box partition proves, and no point within m exists: PASS. If it peaks past
the bound, the search finds a refuting point: FAIL. If it peaks strictly between the
bound and m inside it, the claim has some slack, which a fine enough partition proves,
and the search finds a point within m: MARGINAL. Only a peak exactly on the bound, or a
search that runs out of cells, leaves UNKNOWN, and then the report shows the point
within m that the margin search found.

A report holds one ClaimVerdict per claim plus one named "coverage" for the coverage and
port-contract requirements. The design's verdict is their conjunction (`assemble` over
every outcome).

Assembly also checks each kernel result against the premise book: every premise range
must lie inside the range its hypothesis assumed, and a counterexample must sit inside
every premise range. A mismatch is a bug in trusted code, so it raises RangeMismatch
rather than produce a verdict.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Union, get_args

from .coverage import table_premise
from .kernel import FORMAT, Interval, RangeHyp, Refutation, Rejection, Statement, Theorem, is_issued
from .models.base import (
    CertificateRejected,
    CertificateTooWeak,
    ClaimOrigin,
    Criterion,
    Gap,
    Need,
    NeedsCertificate,
    NeedsInputBound,
    NoModel,
    NoRuleForQuantity,
    Obligation,
    OutsideValidity,
    RegistryInconsistent,
    Requirement,
)
from .premises import Footprint, Label, LabelKind, Premise, PremiseBook, RangeMismatch, ScopeParam, Tag, label_kind
from .units import readable_text

COVERAGE_ENTRY = "coverage"
"""The report entry for requirements no claim made. lang/lower.py reserves the name."""


@dataclass(frozen=True)
class Scope:
    """What a verdict holds over. `environment` is None when the design declares none;
    builders that need it then report NeedsInputBound."""

    params: tuple[ScopeParam, ...]
    load_cases: tuple[str, ...]
    environment: str | None

    @property
    def labels(self) -> frozenset[str]:
        return frozenset(p.label for p in self.params)


def _bound_to(result: object, kind: type, obligation: Obligation) -> None:
    if type(result) is not kind or not is_issued(result):
        raise TypeError(f"a {kind.__name__} must be one kernel.check issued")
    if not isinstance(obligation, Obligation):
        raise TypeError("expected an Obligation")
    if result.statement != obligation.statement:
        raise ValueError(f"the {kind.__name__} is for a different statement than the obligation")


def _hyp_names(statement: Statement) -> tuple[str, ...]:
    return tuple(h.label if isinstance(h, RangeHyp) else h.sym for h in statement.hyps)


def at_point(statement: Statement, refutation: Refutation) -> Statement:
    """`statement` with each RangeHyp narrowed to the value the refutation's point gives
    the hypothesis of the same label, where that value lies in its range. A hypothesis
    the refutation does not assume keeps its range, so a theorem of the result holds at
    the point for every value of it: the validity of a model at its counterexample."""
    labels = {h.sym: h.label for h in refutation.statement.hyps if isinstance(h, RangeHyp)}
    value = {labels[sym]: v for sym, v in refutation.point}
    hyps = tuple(
        RangeHyp(h.sym, value[h.label], value[h.label], h.label)
        if isinstance(h, RangeHyp) and h.label in value and h.lo <= value[h.label] <= h.hi else h
        for h in statement.hyps
    )
    return Statement(hyps, statement.goal)


def _validity_bound(obligation: Obligation, theorems: object, refutation: Refutation | None = None) -> None:
    """Every validity obligation of `obligation` proved, in its order: a theorem
    kernel.check issued for its statement, or, beside a refutation, for its statement at
    the refutation's point (`at_point`). A model used outside its validity range proves
    and refutes nothing, so no outcome that rests on it can be built without these."""
    if not isinstance(theorems, tuple):
        raise TypeError("validity proofs are a tuple of theorems")
    if len(theorems) != len(obligation.validity):
        raise ValueError(
            f"{obligation.requirement.id} rests on model {obligation.model.id}, whose {len(obligation.validity)} "
            f"validity rows each need a proof; {len(theorems)} given"
        )
    for theorem, row in zip(theorems, obligation.validity):
        if type(theorem) is not Theorem or not is_issued(theorem):
            raise TypeError("a validity proof is a Theorem kernel.check issued")
        allowed = (row.statement,) if refutation is None else (row.statement, at_point(row.statement, refutation))
        if theorem.statement not in allowed:
            raise ValueError(f"the proof offered for {row.requirement.mode.id} is for another statement")


def margin_pair_fault(obligation: object, margin: object) -> str | None:
    """None when `margin` is `obligation`'s margin obligation, else why it is not: it
    must be the claim's own requirement with its criterion tightened by its own margin,
    over the same model, with the same goal type and the same hypotheses in the same
    order. The hypotheses carry the load case and every input, so a margin obligation of
    another load case does not pair."""
    if not isinstance(obligation, Obligation) or not isinstance(margin, Obligation):
        return "a claim and its margin are both obligations"
    criterion = obligation.requirement.criterion
    if not isinstance(criterion, Criterion) or criterion.margin is None:
        return "only a claim with a margin has a margin obligation"
    if margin.requirement != dataclasses.replace(obligation.requirement, criterion=criterion.tightened()):
        return "the margin obligation is not the claim's requirement at its tightened bound"
    if margin.model != obligation.model:
        return "the margin obligation rests on a different model than the claim"
    if type(margin.statement.goal) is not type(obligation.statement.goal):
        return "the margin obligation states another kind of goal than the claim"
    if _hyp_names(margin.statement) != _hyp_names(obligation.statement):
        return "the margin obligation ranges over other hypotheses than the claim, such as another load case"
    return None


def _paired(obligation: object, margin: object) -> None:
    fault = margin_pair_fault(obligation, margin)
    if fault is not None:
        raise ValueError(fault)


def has_margin(requirement: Requirement) -> bool:
    return isinstance(requirement.criterion, Criterion) and requirement.criterion.margin is not None


@dataclass(frozen=True)
class Discharged:
    """`margin` is the claim's margin obligation when the claim has a margin, and
    `margin_theorem` the proof of that statement when there is one: the claim then holds
    with at least its margin to spare. A proved claim whose margin statement was neither
    proved nor refuted has `margin` and no `margin_theorem`: its margin is undecided."""

    obligation: Obligation
    theorem: Theorem
    source: str            # "certs", "library", "solver:<name>": where the evidence came from
    margin: Obligation | None = None
    margin_theorem: Theorem | None = None
    validity: tuple[Theorem, ...] = ()   # one proof per validity obligation, in order

    def __post_init__(self) -> None:
        _bound_to(self.theorem, Theorem, self.obligation)
        _validity_bound(self.obligation, self.validity)
        if self.margin is None:
            if has_margin(self.obligation.requirement):
                raise ValueError("a claim with a margin is discharged with its margin obligation, so the report can say whether the margin was checked")
            if self.margin_theorem is not None:
                raise ValueError("a margin theorem needs the margin obligation it proves")
            return
        _paired(self.obligation, self.margin)
        if self.margin_theorem is not None:
            _bound_to(self.margin_theorem, Theorem, self.margin)

    @property
    def margin_status(self) -> str | None:
        """"proved", "undecided", or None for a claim without a margin."""
        if self.margin is None:
            return None
        return "proved" if self.margin_theorem is not None else "undecided"


@dataclass(frozen=True)
class Refuted:
    """`validity` proves each validity obligation over the whole box or at the
    refutation's point, so the counterexample lies where the model holds."""

    obligation: Obligation
    refutation: Refutation
    source: str
    validity: tuple[Theorem, ...] = ()

    def __post_init__(self) -> None:
        _bound_to(self.refutation, Refutation, self.obligation)
        _validity_bound(self.obligation, self.validity, self.refutation)


@dataclass(frozen=True)
class WithinMargin:
    """A claim obligation not refuted, whose margin obligation (the same claim stated
    with its bound moved inward by its margin) the kernel refuted. `theorem` is the
    claim's own theorem when it was proved too, else None. As an outcome it always has
    one (`assemble` refuses it otherwise); without one it is an Open item's margin
    point."""

    obligation: Obligation
    margin: Obligation
    refutation: Refutation
    source: str
    theorem: Theorem | None = None
    validity: tuple[Theorem, ...] = ()   # with a theorem: one proof per validity obligation

    def __post_init__(self) -> None:
        _bound_to(self.refutation, Refutation, self.margin)
        if self.theorem is not None:
            _bound_to(self.theorem, Theorem, self.obligation)
            _validity_bound(self.obligation, self.validity)
        elif self.validity:
            raise ValueError("an open item's margin point carries no validity proofs")
        _paired(self.obligation, self.margin)


@dataclass(frozen=True)
class Waived:
    requirement: Requirement
    waiver: Premise

    def __post_init__(self) -> None:
        if label_kind(self.waiver.label) is not LabelKind.WAIVER:
            raise ValueError(f"{self.waiver.label}: a waiver premise label starts with waive:")


_NEED_TYPES: tuple[type, ...] = get_args(Need)


def _typed_needs(needs: object) -> None:
    if not isinstance(needs, tuple) or not needs:
        raise ValueError("an open item names at least one need")
    for need in needs:
        if not isinstance(need, _NEED_TYPES):
            raise TypeError(f"{need!r} is not a typed Need")


@dataclass(frozen=True)
class Open:
    """A requirement no theorem or refutation settled, with what would settle it. A kernel
    Rejection becomes CertificateRejected or CertificateTooWeak (by its fault type); no
    evidence at all becomes NeedsCertificate; a Gap keeps its own needs. `statement` is
    the obligation's statement, or None for a Gap, which has none. `near` is a certified
    point where the claim comes within its margin of its bound, when the margin search
    found one: a WithinMargin without a theorem, for this requirement."""

    requirement: Requirement
    needs: tuple[Need, ...]
    rejections: tuple[Rejection, ...] = ()
    statement: Statement | None = None
    near: WithinMargin | None = None

    def __post_init__(self) -> None:
        _typed_needs(self.needs)
        if self.near is None:
            return
        if type(self.near) is not WithinMargin or self.near.theorem is not None:
            raise TypeError("an open item's margin point is a WithinMargin without a theorem")
        if self.near.obligation.requirement != self.requirement or self.near.obligation.statement != self.statement:
            raise ValueError("the margin point belongs to another obligation than the open item")


Outcome = Union[Discharged, Refuted, WithinMargin, Waived, Open]
_OUTCOME_TYPES: tuple[type, ...] = get_args(Outcome)


def _issued(results: object, kind: type) -> None:
    if not isinstance(results, tuple):
        raise TypeError(f"expected a tuple of {kind.__name__}")
    for r in results:
        if type(r) is not kind or not is_issued(r):
            raise TypeError(f"a verdict holds only {kind.__name__}s kernel.check issued")


def _resolved(labels: frozenset[str], footprint: Footprint, scope: Scope | None) -> None:
    for label in labels:
        kind = label_kind(label)
        if kind is LabelKind.DESIGN:
            continue
        if kind is LabelKind.PARAM:
            if scope is None or label not in scope.labels:
                raise ValueError(f"{label} is not a parameter of the verdict's scope")
        elif label not in footprint.labels:
            raise ValueError(f"{label} is used but missing from the footprint")


@dataclass(frozen=True)
class Pass:
    scope: Scope
    footprint: Footprint
    theorems: tuple[Theorem, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.scope, Scope):
            raise TypeError("a Pass needs a Scope")
        if not isinstance(self.footprint, Footprint):
            raise TypeError("a Pass needs a Footprint")
        _issued(self.theorems, Theorem)
        if not self.theorems:
            raise ValueError("a Pass rests on at least one theorem")
        for t in self.theorems:
            _resolved(t.labels, self.footprint, self.scope)


@dataclass(frozen=True)
class Fail:
    obligation: Obligation
    refutation: Refutation
    footprint: Footprint
    validity: tuple[Theorem, ...] = ()

    def __post_init__(self) -> None:
        _bound_to(self.refutation, Refutation, self.obligation)
        _validity_bound(self.obligation, self.validity, self.refutation)
        if not isinstance(self.footprint, Footprint):
            raise TypeError("a Fail needs a Footprint")
        for result in (self.refutation, *self.validity):
            _resolved(frozenset(l for l in result.labels if label_kind(l) is not LabelKind.PARAM), self.footprint, None)


@dataclass(frozen=True)
class Unknown:
    """`theorems` are the obligations that did discharge, so a report can show progress."""

    open: tuple[Open, ...]
    footprint: Footprint
    theorems: tuple[Theorem, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.open, tuple) or not self.open:
            raise ValueError("an Unknown names at least one open item")
        if not all(isinstance(o, Open) for o in self.open):
            raise TypeError("an Unknown holds only Open items")
        if not isinstance(self.footprint, Footprint):
            raise TypeError("an Unknown needs a Footprint")
        _issued(self.theorems, Theorem)


@dataclass(frozen=True)
class Marginal:
    """Every obligation proved, at least one with a certified point within its margin.
    `theorems` are the claim theorems: those that discharged and those that came with a
    margin point. `scope` is what the proofs hold over, as a Pass's."""

    near: tuple[WithinMargin, ...]
    footprint: Footprint
    theorems: tuple[Theorem, ...] = ()
    scope: Scope | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.near, tuple) or not self.near:
            raise ValueError("a Marginal names at least one obligation within its margin")
        if not all(isinstance(n, WithinMargin) for n in self.near):
            raise TypeError("a Marginal holds only WithinMargin items")
        if any(n.theorem is None for n in self.near):
            raise ValueError("MARGINAL needs the claim's own proof beside each point within its margin; an unproved claim with such a point is UNKNOWN")
        if not isinstance(self.footprint, Footprint):
            raise TypeError("a Marginal needs a Footprint")
        if self.scope is not None and not isinstance(self.scope, Scope):
            raise TypeError("a Marginal's scope is a Scope")
        _issued(self.theorems, Theorem)
        for n in self.near:
            _resolved(frozenset(l for l in n.refutation.labels if label_kind(l) is not LabelKind.PARAM), self.footprint, None)
        for t in self.theorems:
            _resolved(frozenset(l for l in t.labels if label_kind(l) is not LabelKind.PARAM), self.footprint, None)


Verdict = Union[Pass, Fail, Unknown, Marginal]

STATUS: Mapping[type, str] = {Pass: "PASS", Fail: "FAIL", Unknown: "UNKNOWN", Marginal: "MARGINAL"}

SEVERITY: Mapping[str, int] = {"PASS": 0, "MARGINAL": 1, "UNKNOWN": 2, "FAIL": 3}
"""How the statuses combine: a conjunction takes the most severe. A refutation stands
whatever else is open; an open item leaves the conjunction undecided even where the rest
is decided at its margin."""


@dataclass(frozen=True)
class ClaimVerdict:
    """One report entry: a claim by name, or COVERAGE_ENTRY."""

    claim: str
    verdict: Verdict
    outcomes: tuple[Outcome, ...]


def _requirement(outcome: Outcome) -> Requirement:
    if isinstance(outcome, (Discharged, Refuted, WithinMargin)):
        return outcome.obligation.requirement
    if isinstance(outcome, (Waived, Open)):
        return outcome.requirement
    raise TypeError(f"{outcome!r} is not an outcome")


def _backing(book: PremiseBook, statement: Statement) -> list[tuple[RangeHyp, Premise | ScopeParam]]:
    """Each RangeHyp with the book entry its label names, range-checked. A "dsg:" hyp is
    the design itself and needs no entry."""
    return [
        (h, book.resolve(h.label, Interval(h.lo, h.hi)))
        for h in statement.hyps
        if isinstance(h, RangeHyp) and label_kind(h.label) is not LabelKind.DESIGN
    ]


def _certified(result: Theorem | Refutation) -> Premise:
    verb = "proves" if isinstance(result, Theorem) else "refutes"
    return Premise(
        Label(f"cert:{result.statement_hash}"),
        Tag.CERTIFIED,
        FORMAT,
        "kernel-checked in this run",
        f"{result.rule} evidence {verb} statement {result.statement_hash}",
    )


def _footprint(premises: Iterable[Premise]) -> Footprint:
    by_label: dict[str, Premise] = {}
    for p in premises:
        if by_label.setdefault(p.label, p) != p:
            raise ValueError(f"two different premises are named {p.label}")
    return Footprint(tuple(by_label[label] for label in sorted(by_label)))


def _witnessed(book: PremiseBook, refutation: Refutation) -> list[Premise]:
    """The premises a refutation rests on, with its point checked inside each range."""
    backing = _backing(book, refutation.statement)
    point = dict(refutation.point)
    for hyp, entry in backing:
        if not entry.range.lo <= point[hyp.sym] <= entry.range.hi:
            raise RangeMismatch(f"the counterexample puts {hyp.sym} at {point[hyp.sym]}, outside what {hyp.label} grants")
    return [entry for _, entry in backing if isinstance(entry, Premise)]


def assemble(outcomes: tuple[Outcome, ...], book: PremiseBook, scope: Scope) -> Verdict:
    """Pure. By SEVERITY: FAIL if any outcome is Refuted (the first by requirement id; a
    counterexample stands whatever else is open). Else UNKNOWN if any is Open. Else
    MARGINAL if any is WithinMargin. Else PASS. A WithinMargin's theorem counts with the
    Discharged ones; a WithinMargin without one is refused, since it belongs in an Open.

    Footprint = the book's premises for the labels of all theorems used (each checked
    by book.resolve) + model premises of their obligations + the coverage premise +
    waiver premises + one certified premise per theorem ("cert:<statement-hash>"),
    margin theorems included. A FAIL's footprint is what its refutation rests on: its
    premises, its model, the coverage premise and its certified premise. A MARGINAL's
    adds the same for each margin refutation to the PASS footprint of what did
    discharge, and an UNKNOWN's adds it for each margin point its open items show.

    A PASS needs a theorem, so outcomes that are all waivers have no verdict and the
    Pass constructor raises ValueError.
    """
    if not all(isinstance(o, _OUTCOME_TYPES) for o in outcomes):
        raise TypeError("a verdict is assembled only from Discharged, Refuted, WithinMargin, Waived and Open outcomes")
    if any(isinstance(o, WithinMargin) and o.theorem is None for o in outcomes):
        raise ValueError("a margin point without the claim's proof is an Open item's, not an outcome")
    refuted = sorted((o for o in outcomes if isinstance(o, Refuted)), key=lambda o: o.obligation.requirement.id)
    if refuted:
        first = refuted[0]
        premises = _witnessed(book, first.refutation)
        premises += [first.obligation.model.premise(), table_premise(), _certified(first.refutation)]
        premises += _validity_premises(book, first.obligation, first.validity)
        return Fail(first.obligation, first.refutation, _footprint(premises), first.validity)
    discharged = [o for o in outcomes if isinstance(o, Discharged)]
    premises = [table_premise(), *(o.waiver for o in outcomes if isinstance(o, Waived))]
    for d in discharged:
        premises += [entry for _, entry in _backing(book, d.theorem.statement) if isinstance(entry, Premise)]
        premises += [d.obligation.model.premise(), _certified(d.theorem)]
        premises += _validity_premises(book, d.obligation, d.validity)
        if d.margin_theorem is not None:
            premises.append(_certified(d.margin_theorem))
    theorems = _distinct(t for d in discharged for t in (d.theorem, *d.validity))
    still_open = tuple(o for o in outcomes if isinstance(o, Open))
    if still_open:
        for o in still_open:
            if o.near is not None:
                premises += _witnessed(book, o.near.refutation) + [o.near.margin.model.premise(), _certified(o.near.refutation)]
        return Unknown(still_open, _footprint(premises), theorems)
    near = tuple(o for o in outcomes if isinstance(o, WithinMargin))
    if near:
        for n in near:
            premises += _witnessed(book, n.refutation) + [n.margin.model.premise(), _certified(n.refutation)]
            premises += [entry for _, entry in _backing(book, n.theorem.statement) if isinstance(entry, Premise)]
            premises.append(_certified(n.theorem))
            premises += _validity_premises(book, n.obligation, n.validity)
        return Marginal(near, _footprint(premises), _distinct((*theorems, *(t for n in near for t in (n.theorem, *n.validity)))), scope)
    return Pass(scope, _footprint(premises), theorems)


def _validity_premises(book: PremiseBook, obligation: Obligation, theorems: tuple[Theorem, ...]) -> list[Premise]:
    """What the validity proofs rest on. A proof at a counterexample's point narrows only
    labels the counterexample assumes, whose point `_witnessed` has checked against the
    book, so the ranges are checked against each validity obligation's own statement."""
    premises: list[Premise] = []
    for row, theorem in zip(obligation.validity, theorems):
        premises += [entry for _, entry in _backing(book, row.statement) if isinstance(entry, Premise)]
        premises.append(_certified(theorem))
    return premises


def _distinct(theorems: Iterable[Theorem]) -> tuple[Theorem, ...]:
    """Theorems in order, each statement once: obligations of one load case share
    their validity proofs."""
    seen: dict[str, Theorem] = {}
    for t in theorems:
        seen.setdefault(t.statement_hash, t)
    return tuple(seen.values())


def _entry_name(outcome: Outcome) -> str:
    origin = _requirement(outcome).origin
    return origin.claim if isinstance(origin, ClaimOrigin) else COVERAGE_ENTRY


def entries(outcomes: tuple[Outcome, ...], book: PremiseBook, scope: Scope) -> tuple[ClaimVerdict, ...]:
    """Group outcomes by origin (ClaimOrigin.claim, else COVERAGE_ENTRY) and `assemble`
    each group. Claims in source order (the order their outcomes arrive), then coverage.

    The coverage entry is left out when nothing in it is certified, refuted or open:
    with no coverage requirements, or with every one waived, it has nothing a verdict
    could rest on. Its waivers still reach the design's verdict through `assemble` over
    every outcome.
    """
    groups: dict[str, list[Outcome]] = {}
    for outcome in outcomes:
        groups.setdefault(_entry_name(outcome), []).append(outcome)
    coverage = groups.pop(COVERAGE_ENTRY, [])
    named = list(groups.items())
    if any(not isinstance(o, Waived) for o in coverage):
        named.append((COVERAGE_ENTRY, coverage))
    return tuple(ClaimVerdict(name, assemble(tuple(group), book, scope), tuple(group)) for name, group in named)


def open_from_gap(gap: Gap) -> Open:
    if not isinstance(gap, Gap):
        raise TypeError("expected a Gap")
    return Open(gap.requirement, gap.needs)


def describe_need(need: Need) -> str:
    """One line a person can act on, such as "signed bound on site.fault_current [A]" or
    "waive corrosion.galvanic on frame.n3 by ...". The JSON "obligations" list is these."""
    match need:
        case NeedsCertificate():
            return f"no {need.rule} certificate for {need.describe}: supply evidence for statement {need.statement_hash}"
        case CertificateRejected():
            by = f" by {need.rule}" if need.rule else ""
            return f"{need.source} evidence for {need.statement_hash} rejected{by}: {need.reason}"
        case CertificateTooWeak():
            by = f" for {need.rule}" if need.rule else ""
            return f"{need.source} evidence for {need.statement_hash} too weak{by}: {need.reason}; a finer partition or a sharper field may close it"
        case NeedsInputBound():
            return f"signed bound on {'.'.join(need.target)}.{need.field} [{need.unit}]"
        case NoRuleForQuantity():
            return f"no rule for {need.qoi}: {need.reason}"
        case NoModel():
            subject = ".".join(need.subject)
            return f'no model for {need.mode.id} on {subject}: waive {need.mode.id} on {subject} by "<owner>" reason "<why>"'
        case RegistryInconsistent():
            return f"registry entry {need.entry} breaks {need.relation}: {need.message}; correct the record"
        case OutsideValidity():
            point = ", ".join(f"{sym} = {value}" for sym, value in need.point) or "a point of the scope"
            return (f"model {need.model} is used outside its validity range: {need.row} ({need.text}) is refuted at "
                    f"{point}, statement {need.statement_hash}; narrow the signed inputs, change the design, or use a model valid there")
    raise TypeError(f"{need!r} is not a typed Need")


def _results(verdict: Verdict) -> tuple[Theorem | Refutation, ...]:
    if isinstance(verdict, Fail):
        return (verdict.refutation, *verdict.validity)
    if isinstance(verdict, Marginal):
        return verdict.theorems + tuple(n.refutation for n in verdict.near)
    return verdict.theorems


def verdict_json(entry: ClaimVerdict) -> Mapping[str, Any]:
    """{"claim", "status": STATUS[type(verdict)], "footprint": [{"tag", "label", "owner",
    "source"}], "rules": sorted rule ids of the kernel results used ("R1"...),
    "obligations": [describe_need(n) for every need of every open item], "margins":
    margin_json for every obligation of a claim with a margin that is not refuted or
    waived}. "obligations" is non-empty exactly when status is UNKNOWN."""
    verdict = entry.verdict
    still_open = verdict.open if isinstance(verdict, Unknown) else ()
    return {
        "claim": entry.claim,
        "status": STATUS[type(verdict)],
        "rules": sorted({r.rule for r in _results(verdict)}),
        "obligations": [describe_need(n) for o in still_open for n in o.needs],
        "margins": [m for o in entry.outcomes if (m := margin_json(o)) is not None],
        "footprint": [
            {"tag": p.tag.value, "label": p.label, "owner": p.owner, "source": p.source}
            for p in verdict.footprint.premises
        ],
    }


def margin_json(outcome: Outcome) -> Mapping[str, Any] | None:
    """{"requirement", "proved": whether the claim itself is proved, "margin": "proved"
    (the claim holds with at least its margin to spare), "undecided" (no point within the
    margin was found and the slack is not proved) or "within" (a certified point lies
    within the margin, given as "point": {symbol: exact value})}. None for an outcome
    with no margin, or one that is refuted or waived."""
    if isinstance(outcome, Discharged) and outcome.margin is not None:
        return {"requirement": outcome.obligation.requirement.id, "proved": True, "margin": outcome.margin_status}
    near = outcome if isinstance(outcome, WithinMargin) else outcome.near if isinstance(outcome, Open) else None
    if near is not None:
        point = {sym: str(value) for sym, value in near.refutation.point}
        return {"requirement": near.obligation.requirement.id, "proved": near.theorem is not None, "margin": "within", "point": point}
    if isinstance(outcome, Open) and has_margin(outcome.requirement):
        return {"requirement": outcome.requirement.id, "proved": False, "margin": "undecided"}
    return None


def _scope_text(scope: Scope) -> str:
    params = ", ".join(f"{p.name} in [{p.range.lo}, {p.range.hi}] {p.unit}" for p in scope.params)
    return "; ".join((
        f"load cases {', '.join(scope.load_cases) or 'none'}",
        f"environment {scope.environment or 'undeclared'}",
        params or "no parameters",
    ))


def _outcome_row(outcome: Outcome) -> str:
    req = _requirement(outcome)
    origin = f"claim {req.origin.claim}" if isinstance(req.origin, ClaimOrigin) else f"coverage {req.origin.rule}"
    match outcome:
        case Discharged():
            margin = f"  margin {outcome.margin_status}" if outcome.margin is not None else ""
            what = f"{outcome.theorem.rule}  certified  {outcome.source}  {outcome.theorem.statement_hash[:19]}..{margin}"
        case Refuted():
            what = f"{outcome.refutation.rule}  refuted    {outcome.source}  {outcome.refutation.statement_hash[:19]}.."
        case WithinMargin():
            what = f"{outcome.refutation.rule}  marginal   {outcome.source}  proved, margin point at {outcome.refutation.statement_hash[:19]}.."
        case Waived():
            what = f"--  waived by {outcome.waiver.owner}"
        case _:
            what = "--  open, margin point found" if outcome.near is not None else "--  open"
    proofs = getattr(outcome, "validity", ())
    if proofs:
        what += f"  validity {len(proofs)} proved"
    name = f"{'.'.join(req.subject)}/{req.mode.id}"
    return f"{name:<44} {origin:<28} {what}"


def _point_lines(refutation: Refutation, footprint: Footprint, pad: str = "  ") -> list[str]:
    labels = {h.sym: h.label for h in refutation.statement.hyps if isinstance(h, RangeHyp)}
    units = {p.label: p.unit for p in footprint.premises}
    lines = []
    for sym, value in refutation.point:
        unit = units.get(labels[sym])
        shown = f"{value} {unit}" if unit else f"{value}"
        lines.append(f"{pad}{sym} = {shown}   ({labels[sym]})")
    return lines


def _margin_of(requirement: Requirement) -> str:
    return readable_text(requirement.criterion.margin)


def _margin_lines(outcomes: tuple[Outcome, ...]) -> list[str]:
    """One line per proved claim obligation with a margin: whether the margin itself was
    proved, or no point within it was found and its slack is not proved."""
    lines = []
    for o in outcomes:
        if isinstance(o, Discharged) and o.margin is not None:
            m = _margin_of(o.obligation.requirement)
            said = (f"proved: the claim holds with at least {m} to spare" if o.margin_theorem is not None
                    else f"undecided: no point within {m} of the bound was found, and slack {m} is not proved")
            lines.append(f"margin     {o.obligation.requirement.id}: {said}")
    return lines


def render(verdict: Verdict, outcomes: tuple[Outcome, ...]) -> str:
    """The text `lola check` prints: verdict line, scope, per-obligation table (rule,
    outcome, statement hash prefix, evidence source), then the footprint grouped by tag
    with owner and source. For UNKNOWN, each open item with what it needs. For FAIL, the
    counterexample point, in SI base units (degC for temperature) as the IR holds it. For
    MARGINAL, each point within a claim's margin, the same way, and for an open item the
    point within its margin when the search found one. Each proved claim with a margin
    gets a line saying whether the margin was proved or is undecided. Margins print in a
    readable unit of their dimension (units.readable_text)."""
    count = {kind: sum(isinstance(o, kind) for o in outcomes) for kind in (Discharged, Refuted, WithinMargin, Waived, Open)}
    lines = [STATUS[type(verdict)]]
    if isinstance(verdict, (Pass, Marginal)) and verdict.scope is not None:
        lines.append(f"scope      {_scope_text(verdict.scope)}")
    lines.append(
        f"checked    {len(outcomes)} obligations, {count[Discharged]} certified, {count[Refuted]} refuted, "
        + (f"{count[WithinMargin]} within margin, " if count[WithinMargin] else "")
        + f"{count[Waived]} waived, {count[Open]} open"
    )
    lines += [f"  {_outcome_row(o)}" for o in outcomes]
    if not isinstance(verdict, Fail):
        lines += _margin_lines(outcomes)
    if isinstance(verdict, Fail):
        lines.append(f"counterexample  {verdict.obligation.requirement.id}: {verdict.obligation.describe}")
        lines += _point_lines(verdict.refutation, verdict.footprint)
    if isinstance(verdict, Marginal):
        for n in verdict.near:
            lines.append(f"within margin  {n.obligation.requirement.id}: {n.obligation.describe}")
            lines.append(f"  proved; at this point it is within {_margin_of(n.obligation.requirement)} of its bound")
            lines += _point_lines(n.refutation, verdict.footprint)
    if isinstance(verdict, Unknown):
        lines.append(f"open       {len(verdict.open)} requirements")
        for item in verdict.open:
            lines.append(f"  {item.requirement.id}")
            lines += [f"    needs {describe_need(n)}" for n in item.needs]
            if item.near is not None:
                lines.append(f"    neither proved nor refuted; at this point it is within {_margin_of(item.requirement)} of its bound")
                lines += _point_lines(item.near.refutation, verdict.footprint, "      ")
    lines.append(f"footprint  {len(verdict.footprint.premises)} premises")
    for tag, premises in verdict.footprint.by_tag().items():
        lines += [f"  {tag.value:<16} {p.label}   {p.statement}   ({p.owner}; {p.source})" for p in premises]
    return "\n".join(lines)
