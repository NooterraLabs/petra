"""Verdicts and their assembly from kernel results. Trusted.

Construction rules, enforced in __post_init__ so an illegal verdict cannot exist:
- Pass needs a Scope, a non-empty Footprint and at least one theorem the kernel issued.
  Every label on every theorem must resolve: "par:" labels to a scope parameter, "dsg:"
  labels to the design itself, every other label to a footprint premise. Theorems are
  sealed by the kernel (lola/kernel/check.py), so a Pass cannot be built from claims, a
  copied theorem or an altered one.
- Fail needs an issued Refutation of the obligation's own statement, and a footprint
  that names every premise the refuted statement rests on.
- Unknown needs at least one Open item, and every Open item names at least one typed
  Need (lola/models/base.py), so "UNKNOWN" always says what would close it.
- Discharged and Refuted bind the kernel result to the obligation: the issued result's
  statement must equal the obligation's statement.

A report holds one ClaimVerdict per claim plus one named "coverage" for the coverage and
port-contract requirements. The design's verdict is their conjunction (`assemble` over
every outcome).

Assembly also checks each kernel result against the premise book: every premise range
must lie inside the range its hypothesis assumed, and a counterexample must sit inside
every premise range. A mismatch is a bug in trusted code, so it raises RangeMismatch
rather than produce a verdict.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Union, get_args

from .coverage import table_premise
from .kernel import FORMAT, Interval, RangeHyp, Refutation, Rejection, Statement, Theorem, is_issued
from .models.base import (
    CertificateRejected,
    CertificateTooWeak,
    ClaimOrigin,
    Gap,
    Need,
    NeedsCertificate,
    NeedsInputBound,
    NoModel,
    NoRuleForQuantity,
    Obligation,
    RegistryInconsistent,
    Requirement,
)
from .premises import Footprint, Label, LabelKind, Premise, PremiseBook, RangeMismatch, ScopeParam, Tag, label_kind

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


@dataclass(frozen=True)
class Discharged:
    obligation: Obligation
    theorem: Theorem
    source: str            # "certs", "library", "solver:<name>": where the evidence came from

    def __post_init__(self) -> None:
        _bound_to(self.theorem, Theorem, self.obligation)


@dataclass(frozen=True)
class Refuted:
    obligation: Obligation
    refutation: Refutation
    source: str

    def __post_init__(self) -> None:
        _bound_to(self.refutation, Refutation, self.obligation)


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
    evidence at all becomes NeedsCertificate; a Gap keeps its own needs."""

    requirement: Requirement
    needs: tuple[Need, ...]
    rejections: tuple[Rejection, ...] = ()

    def __post_init__(self) -> None:
        _typed_needs(self.needs)


Outcome = Union[Discharged, Refuted, Waived, Open]
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

    def __post_init__(self) -> None:
        _bound_to(self.refutation, Refutation, self.obligation)
        if not isinstance(self.footprint, Footprint):
            raise TypeError("a Fail needs a Footprint")
        _resolved(frozenset(l for l in self.refutation.labels if label_kind(l) is not LabelKind.PARAM), self.footprint, None)


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


Verdict = Union[Pass, Fail, Unknown]

STATUS: Mapping[type, str] = {Pass: "PASS", Fail: "FAIL", Unknown: "UNKNOWN"}


@dataclass(frozen=True)
class ClaimVerdict:
    """One report entry: a claim by name, or COVERAGE_ENTRY."""

    claim: str
    verdict: Verdict
    outcomes: tuple[Outcome, ...]


def _requirement(outcome: Outcome) -> Requirement:
    if isinstance(outcome, (Discharged, Refuted)):
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


def assemble(outcomes: tuple[Outcome, ...], book: PremiseBook, scope: Scope) -> Verdict:
    """Pure. FAIL if any outcome is Refuted (the first by requirement id; a counterexample
    stands whatever else is open). Else UNKNOWN if any is Open. Else PASS.

    Footprint = the book's premises for the labels of all theorems used (each checked
    by book.resolve) + model premises of their obligations + the coverage premise +
    waiver premises + one certified premise per theorem ("cert:<statement-hash>"). A
    FAIL's footprint is what its refutation rests
    on: its premises, its model, the coverage premise and its certified premise.

    A PASS needs a theorem, so outcomes that are all waivers have no verdict and the
    Pass constructor raises ValueError.
    """
    if not all(isinstance(o, _OUTCOME_TYPES) for o in outcomes):
        raise TypeError("a verdict is assembled only from Discharged, Refuted, Waived and Open outcomes")
    refuted = sorted((o for o in outcomes if isinstance(o, Refuted)), key=lambda o: o.obligation.requirement.id)
    if refuted:
        first = refuted[0]
        backing = _backing(book, first.refutation.statement)
        point = dict(first.refutation.point)
        for hyp, entry in backing:
            if not entry.range.lo <= point[hyp.sym] <= entry.range.hi:
                raise RangeMismatch(f"the counterexample puts {hyp.sym} at {point[hyp.sym]}, outside what {hyp.label} grants")
        premises = [entry for _, entry in backing if isinstance(entry, Premise)]
        premises += [first.obligation.model.premise(), table_premise(), _certified(first.refutation)]
        return Fail(first.obligation, first.refutation, _footprint(premises))
    discharged = [o for o in outcomes if isinstance(o, Discharged)]
    premises = [table_premise(), *(o.waiver for o in outcomes if isinstance(o, Waived))]
    for d in discharged:
        premises += [entry for _, entry in _backing(book, d.theorem.statement) if isinstance(entry, Premise)]
        premises += [d.obligation.model.premise(), _certified(d.theorem)]
    theorems = tuple(d.theorem for d in discharged)
    still_open = tuple(o for o in outcomes if isinstance(o, Open))
    if still_open:
        return Unknown(still_open, _footprint(premises), theorems)
    return Pass(scope, _footprint(premises), theorems)


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
    raise TypeError(f"{need!r} is not a typed Need")


def _results(verdict: Verdict) -> tuple[Theorem | Refutation, ...]:
    return (verdict.refutation,) if isinstance(verdict, Fail) else verdict.theorems


def verdict_json(entry: ClaimVerdict) -> Mapping[str, Any]:
    """{"claim", "status": STATUS[type(verdict)], "footprint": [{"tag", "label", "owner",
    "source"}], "rules": sorted rule ids of the kernel results used ("R1"...),
    "obligations": [describe_need(n) for every need of every open item]}. "obligations"
    is non-empty exactly when status is UNKNOWN."""
    verdict = entry.verdict
    still_open = verdict.open if isinstance(verdict, Unknown) else ()
    return {
        "claim": entry.claim,
        "status": STATUS[type(verdict)],
        "rules": sorted({r.rule for r in _results(verdict)}),
        "obligations": [describe_need(n) for o in still_open for n in o.needs],
        "footprint": [
            {"tag": p.tag.value, "label": p.label, "owner": p.owner, "source": p.source}
            for p in verdict.footprint.premises
        ],
    }


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
            what = f"{outcome.theorem.rule}  certified  {outcome.source}  {outcome.theorem.statement_hash[:19]}.."
        case Refuted():
            what = f"{outcome.refutation.rule}  refuted    {outcome.source}  {outcome.refutation.statement_hash[:19]}.."
        case Waived():
            what = f"--  waived by {outcome.waiver.owner}"
        case _:
            what = "--  open"
    name = f"{'.'.join(req.subject)}/{req.mode.id}"
    return f"{name:<44} {origin:<28} {what}"


def render(verdict: Verdict, outcomes: tuple[Outcome, ...]) -> str:
    """The text `lola check` prints: verdict line, scope, per-obligation table (rule,
    outcome, statement hash prefix, evidence source), then the footprint grouped by tag
    with owner and source. For UNKNOWN, each open item with what it needs. For FAIL, the
    counterexample point, in SI base units (degC for temperature) as the IR holds it."""
    count = {kind: sum(isinstance(o, kind) for o in outcomes) for kind in (Discharged, Refuted, Waived, Open)}
    lines = [STATUS[type(verdict)]]
    if isinstance(verdict, Pass):
        lines.append(f"scope      {_scope_text(verdict.scope)}")
    lines.append(
        f"checked    {len(outcomes)} obligations, {count[Discharged]} certified, {count[Refuted]} refuted, "
        f"{count[Waived]} waived, {count[Open]} open"
    )
    lines += [f"  {_outcome_row(o)}" for o in outcomes]
    if isinstance(verdict, Fail):
        labels = {h.sym: h.label for h in verdict.refutation.statement.hyps if isinstance(h, RangeHyp)}
        units = {p.label: p.unit for p in verdict.footprint.premises}
        lines.append(f"counterexample  {verdict.obligation.requirement.id}: {verdict.obligation.describe}")
        for sym, value in verdict.refutation.point:
            unit = units.get(labels[sym])
            shown = f"{value} {unit}" if unit else f"{value}"
            lines.append(f"  {sym} = {shown}   ({labels[sym]})")
    if isinstance(verdict, Unknown):
        lines.append(f"open       {len(verdict.open)} requirements")
        for item in verdict.open:
            lines.append(f"  {item.requirement.id}")
            lines += [f"    needs {describe_need(n)}" for n in item.needs]
    lines.append(f"footprint  {len(verdict.footprint.premises)} premises")
    for tag, premises in verdict.footprint.by_tag().items():
        lines += [f"  {tag.value:<16} {p.label}   {p.statement}   ({p.owner}; {p.source})" for p in premises]
    return "\n".join(lines)
