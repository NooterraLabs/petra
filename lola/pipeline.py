"""Design -> verdict. Trusted, and deliberately short: it binds evidence to obligations
and nothing else.

    models       = lower_components(design, registry)          (each kind's lowerer)
    requirements = coverage.generate(design, models) - waivers
    elaborated   = elaborate(design, models, requirements)     (each mode's builder)
    for each obligation: offer evidence from each source in order; kernel.check decides
    entries      = verdict.entries(outcomes, premises, scope)

Every dispatch reads the domain registry (lola/models/__init__.py): a component's kind
picks its lowerer, a requirement's mode picks its builder. Nothing here names a domain.

Binding invariant: the statement checked is always the one the elaborator just built
from the design. Sources receive that statement and return evidence only. A stored
certificate whose statement hash differs from the obligation's is never consulted,
which is how a tampered or stale certificate fails to discharge anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol

from .ir import Design
from .kernel import Evidence, Statement
from .models.base import ComponentError, Elaborated, Requirement
from .premises import PremiseBook
from .registry import Deck, Registry
from .verdict import ClaimVerdict, Outcome, Verdict


class EvidenceSource(Protocol):
    """Untrusted. Implemented by certs.CertStore, library.Library and solvers.SolverSource.
    May return proof or refutation evidence, several candidates, or none."""

    name: str

    def offer(self, statement: Statement, statement_hash: str) -> Iterable[Evidence]:
        ...


class EvidenceSink(Protocol):
    """Receives evidence the kernel accepted, for example to write a certificate file."""

    def record(self, statement: Statement, statement_hash: str, evidence: Evidence, source: str) -> None:
        ...


@dataclass(frozen=True)
class Report:
    """`verdict` is the conjunction over every entry; `entries` has one ClaimVerdict per
    claim, in source order, then the "coverage" entry."""

    design: str
    path: str
    verdict: Verdict
    entries: tuple[ClaimVerdict, ...]
    outcomes: tuple[Outcome, ...]
    warnings: tuple[str, ...]

    def render(self) -> str:
        raise NotImplementedError

    def to_json(self) -> Mapping[str, Any]:
        """{"file": path, "design": name, "status": the overall status, "verdicts":
        [verdict.verdict_json(e) for e in entries]}. `lola check --json` prints this."""
        raise NotImplementedError


def lower_components(design: Design, registry: Registry) -> dict[str, Any]:
    """Component name -> typed model, by models.KINDS[component.kind]'s lowerer. Collects
    every lowerer's problems and raises one ComponentError, which the CLI reports as an
    input error (exit 3)."""
    raise NotImplementedError


def elaborate(design: Design, models: Mapping[str, Any], requirements: tuple[Requirement, ...], registry: Registry) -> tuple[Elaborated, ...]:
    """For each requirement, the domain that owns the subject's component kind: a mode in
    models.UNMODELLED becomes Gap(needs=(NoModel(mode, subject),)); otherwise the
    domain's builder for the mode runs. Then contracts.contract_obligations over every
    component's `ports`. A requirement whose mode no domain builds and that is not
    unmodelled is a bug in a DomainSpec, which models/__init__._index already refuses."""
    raise NotImplementedError


def check_design(design: Design, registry: Registry, sources: tuple[EvidenceSource, ...], sink: EvidenceSink | None = None, deck: Deck | None = None, path: str = "") -> Report:
    """Check one design. Deterministic given the same sources. Raises ComponentError for
    an input error.

    TODO:
      models = lower_components(design, registry)
      reqs = coverage.generate(design, models, registry)
      reqs, waived = coverage.apply_waivers(reqs, design)
      elaborated = elaborate(design, models, reqs, registry)
      flagged = registry.check_deck(deck) entries, if a deck is given
      for each Gap g: Open(g.requirement, g.needs)
      for each Obligation ob:
          h = kernel.statement_hash(ob.statement)
          if ob's statement uses a label of a flagged entry -> Open(needs=RegistryInconsistent)
          for src in sources: for ev in src.offer(ob.statement, h):
              r = kernel.check(ob.statement, ev)
              Theorem -> Discharged; Refutation -> Refuted; stop. Rejection -> collect.
          none -> Open(needs=NeedsCertificate) if nothing was offered, else one
                  CertificateRejected or CertificateTooWeak per rejection (by fault type)
          on success: sink.record(...)
      book = build_premise_book(design, registry, outcomes)
      entries = verdict.entries(outcomes, book, scope_of(design))
      overall = verdict.assemble(outcomes, book, scope_of(design))
    """
    raise NotImplementedError


def explain(design: Design, registry: Registry) -> str:
    """Elaborate without checking and pretty-print each statement in mathematical notation
    with every hypothesis label, so a reviewer can audit the trusted front end and the
    elaborators against the source file. `lola explain FILE` prints this."""
    raise NotImplementedError


def build_premise_book(design: Design, registry: Registry, outcomes: tuple[Outcome, ...]) -> PremiseBook:
    """PremiseBook from the registry constants and ratings, the design's signed inputs,
    its params and design values, the model specs of every obligation in `outcomes`, the
    coverage table, and the waiver premise of every Waived outcome. Called once, after
    every outcome is known."""
    raise NotImplementedError


__all__ = ["ComponentError", "EvidenceSink", "EvidenceSource", "Report", "build_premise_book", "check_design", "elaborate", "explain", "lower_components"]
