"""Family certification. Untrusted orchestration around the trusted pipeline.

A family is a .lola design with `param` ranges. Certifying it elaborates the family's
claims only: coverage belongs to a concrete design, not to a reusable lemma, so the
cu_pvc family need not name a breaker. Each claim statement is self-contained, so each
discharged claim becomes its own FamilyEntry; a claim that does not discharge stores
nothing and is listed in `skipped`. The kernel checked every stored entry in this run.
A reuse is an Instance of the entry, so the kernel checks the entry again once per
process and checks each query against it.

The report is the pipeline's report on the family design with the solver run on the
claim statements only, so its coverage entry stays open by construction: a family is
not a design anyone builds.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .. import coverage
from ..ir import Design
from ..kernel import Evidence, Statement, statement_hash
from ..models.base import ClaimOrigin, Obligation
from ..pipeline import Report, check_design, elaborate, lower_components
from ..registry import Registry
from ..solvers import SolverSource
from ..verdict import Discharged, Open, Refuted, Waived, describe_need
from .store import FamilyEntry, Library, family_entry


@dataclass(frozen=True)
class FamilyReport:
    report: Report
    stored: tuple[FamilyEntry, ...]
    skipped: tuple[str, ...]        # requirement ids not stored, with the reason


def claim_obligations(design: Design, registry: Registry) -> tuple[Obligation, ...]:
    """The statements the design's claims elaborate to, without coverage or port
    contracts. Claims that cannot be stated (gaps) are left out."""
    lowered = lower_components(design, registry)
    claims, _ = coverage.apply_waivers(coverage.claim_requirements(design, lowered), design)
    return tuple(
        e for e in elaborate(design, lowered, claims, registry)
        if isinstance(e, Obligation) and isinstance(e.requirement.origin, ClaimOrigin)
    )


def certify_family(design: Design, registry: Registry, library: Library) -> FamilyReport:
    """Requires design.is_family. Pure apart from library.add, which is idempotent."""
    if not design.is_family:
        raise ValueError(f"{design.path}: {design.name} declares no param, so it is a design, not a family")
    wanted = frozenset(statement_hash(o.statement) for o in claim_obligations(design, registry))
    accepted = _Accepted()
    report = check_design(design, registry, (_ClaimsOnly(wanted, SolverSource()),), sink=accepted, path=design.path)
    stored: list[FamilyEntry] = []
    skipped: list[str] = []
    for outcome in report.outcomes:
        requirement = outcome.obligation.requirement if isinstance(outcome, (Discharged, Refuted)) else outcome.requirement
        if not isinstance(requirement.origin, ClaimOrigin):
            continue
        if isinstance(outcome, Discharged):
            obligation = outcome.obligation
            entry = family_entry(obligation.statement, accepted.evidence[outcome.theorem.statement_hash], (obligation.model.premise().label,))
            library.add(entry)
            stored.append(entry)
        else:
            skipped.append(f"{requirement.id}: {_why(outcome)}")
    return FamilyReport(report, tuple(stored), tuple(skipped))


def _why(outcome: Refuted | Open | Waived) -> str:
    if isinstance(outcome, Refuted):
        point = ", ".join(f"{sym} = {value}" for sym, value in outcome.refutation.point)
        return f"refuted by {outcome.refutation.rule} at {point}"
    if isinstance(outcome, Waived):
        return f"waived by {outcome.waiver.owner}, so there is nothing to store"
    return "; ".join(describe_need(n) for n in outcome.needs)


class _ClaimsOnly:
    """The solver, for the claim statements only."""

    name = "solver"

    def __init__(self, wanted: frozenset[str], solver: SolverSource) -> None:
        self.wanted = wanted
        self.solver = solver

    def offer(self, statement: Statement, statement_hash: str) -> Iterable[Evidence]:
        return self.solver.offer(statement, statement_hash) if statement_hash in self.wanted else ()


class _Accepted:
    """Sink: the evidence the kernel accepted, by statement hash."""

    def __init__(self) -> None:
        self.evidence: dict[str, Evidence] = {}

    def record(self, statement: Statement, statement_hash: str, evidence: Evidence, source: str) -> None:
        self.evidence[statement_hash] = evidence
