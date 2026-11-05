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
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Union, get_args

from .kernel import Refutation, Rejection, Theorem, is_issued
from .models.base import Gap, Need, Obligation, Requirement
from .premises import Footprint, LabelKind, Premise, PremiseBook, ScopeParam, label_kind

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


def assemble(outcomes: tuple[Outcome, ...], book: PremiseBook, scope: Scope) -> Verdict:
    """Pure. FAIL if any outcome is Refuted (the first by requirement id; a counterexample
    stands whatever else is open). Else UNKNOWN if any is Open. Else PASS.

    Footprint = book.footprint(labels of all theorems used) + model premises of their
    obligations + the coverage premise + waiver premises + one certified premise per
    theorem ("cert:<statement-hash>").
    """
    raise NotImplementedError


def entries(outcomes: tuple[Outcome, ...], book: PremiseBook, scope: Scope) -> tuple[ClaimVerdict, ...]:
    """Group outcomes by origin (ClaimOrigin.claim, else COVERAGE_ENTRY) and `assemble`
    each group. Claims in source order, then coverage."""
    raise NotImplementedError


def open_from_gap(gap: Gap) -> Open:
    raise NotImplementedError


def describe_need(need: Need) -> str:
    """One line a person can act on, such as "signed bound on site.fault_current [A]" or
    "waive corrosion.galvanic on frame.n3 by ...". The JSON "obligations" list is these."""
    raise NotImplementedError


def verdict_json(entry: ClaimVerdict) -> Mapping[str, Any]:
    """{"claim", "status": STATUS[type(verdict)], "footprint": [{"tag", "label", "owner",
    "source"}], "rules": sorted rule ids of the kernel results used ("R1"...),
    "obligations": [describe_need(n) for every need of every open item]}. "obligations"
    is non-empty exactly when status is UNKNOWN."""
    raise NotImplementedError


def render(verdict: Verdict, outcomes: tuple[Outcome, ...]) -> str:
    """The text `lola check` prints: verdict line, scope, per-obligation table (rule,
    outcome, statement hash prefix, evidence source), then the footprint grouped by tag
    with owner and source. For UNKNOWN, each open item with what it needs. For FAIL, the
    counterexample point in design units."""
    raise NotImplementedError
