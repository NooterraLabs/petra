"""Family certification. Untrusted orchestration around the trusted pipeline.

A family is a .petra design with `param` ranges. Certifying it elaborates the family's
claims only: coverage belongs to a concrete design, not to a reusable lemma, so the
cu_pvc family need not name a breaker. Each claim statement is self-contained, so each
proved claim becomes its own FamilyEntry, including one with a certified point within
its margin, which is also listed in `near`. Each validity row the claim was proved with
becomes an entry too, so an instance shows that its model holds as well as its claim. A
claim that is not proved stores nothing and is listed in `skipped`, with the reason: a
refuted claim names its counterexample, at which the solver also proves the rows. The solver sees each claim's margin statement too, so a family's
margins are checked as a design's are. The kernel checked every stored entry in this
run.
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
from ..pipeline import Report, check_design, elaborate, lower_components, margin_obligations
from ..registry import Registry
from ..solvers import SolverSource
from ..verdict import Discharged, Open, Refuted, Waived, WithinMargin, describe_need
from .store import FamilyEntry, Library, family_entry, shape_hash


@dataclass(frozen=True)
class FamilyReport:
    report: Report
    stored: tuple[FamilyEntry, ...]
    skipped: tuple[str, ...]        # requirement ids not stored, with the reason
    near: tuple[str, ...] = ()      # requirement ids stored whose claim comes within its margin, with the point


def claim_obligations(design: Design, registry: Registry) -> tuple[Obligation, ...]:
    """The statements the design's claims elaborate to, without coverage or port
    contracts. Claims that cannot be stated (gaps) are left out."""
    return tuple(o for o, _ in _with_margins(design, registry))


def _with_margins(design: Design, registry: Registry) -> tuple[tuple[Obligation, Obligation | str | None], ...]:
    lowered = lower_components(design, registry)
    claims, _ = coverage.apply_waivers(coverage.claim_requirements(design, lowered), design)
    elaborated = elaborate(design, lowered, claims, registry)
    return tuple(
        (e, m) for e, m in zip(elaborated, margin_obligations(design, lowered, elaborated, registry))
        if isinstance(e, Obligation) and isinstance(e.requirement.origin, ClaimOrigin)
    )


def certify_family(design: Design, registry: Registry, library: Library) -> FamilyReport:
    """Requires design.is_family. Pure apart from library.add, which is idempotent."""
    if not design.is_family:
        raise ValueError(f"{design.path}: {design.name} declares no param, so it is a design, not a family")
    wanted = frozenset(
        statement_hash(s.statement)
        for pair in _with_margins(design, registry)
        for o in pair
        if isinstance(o, Obligation)
        for s in (o, *o.validity)
    )
    rows = frozenset(
        shape_hash(v.statement)
        for pair in _with_margins(design, registry)
        for o in pair
        if isinstance(o, Obligation)
        for v in o.validity
    )
    accepted = _Accepted()
    report = check_design(design, registry, (_ClaimsOnly(wanted, rows, SolverSource()),), sink=accepted, path=design.path)
    stored: list[FamilyEntry] = []
    skipped: list[str] = []
    near: list[str] = []
    for outcome in report.outcomes:
        requirement = outcome.obligation.requirement if isinstance(outcome, (Discharged, Refuted, WithinMargin)) else outcome.requirement
        if not isinstance(requirement.origin, ClaimOrigin):
            continue
        if isinstance(outcome, (Discharged, WithinMargin)):
            obligation = outcome.obligation
            model = (obligation.model.premise().label,)
            proved = ((obligation.statement, outcome.theorem), *((v.statement, t) for v, t in zip(obligation.validity, outcome.validity)))
            for statement, theorem in proved:
                entry = family_entry(statement, accepted.evidence[theorem.statement_hash], model)
                library.add(entry)
                if entry not in stored:
                    stored.append(entry)
            if isinstance(outcome, WithinMargin):
                near.append(f"{requirement.id}: proved, and within its margin of the bound by {outcome.refutation.rule} at {_point(outcome.refutation)}")
        else:
            skipped.append(f"{requirement.id}: {_why(outcome)}")
    return FamilyReport(report, tuple(stored), tuple(skipped), tuple(near))


def _point(refutation) -> str:
    return ", ".join(f"{sym} = {value}" for sym, value in refutation.point)


def _why(outcome: Refuted | Open | Waived) -> str:
    if isinstance(outcome, Refuted):
        return f"refuted by {outcome.refutation.rule} at {_point(outcome.refutation)}"
    if isinstance(outcome, Waived):
        return f"waived by {outcome.waiver.owner}, so there is nothing to store"
    needs = "; ".join(describe_need(n) for n in outcome.needs)
    if outcome.near is not None:
        needs += f"; neither proved nor refuted, and within its margin of the bound by {outcome.near.refutation.rule} at {_point(outcome.near.refutation)}"
    return needs


class _ClaimsOnly:
    """The solver, for the claim statements, their margin statements and their validity
    rows only. A row narrowed to a claim's counterexample (verdict.at_point) has a row's
    shape with a narrower box, so a refuted claim is a FAIL here as in its design."""

    name = "solver"

    def __init__(self, wanted: frozenset[str], rows: frozenset[str], solver: SolverSource) -> None:
        self.wanted = wanted
        self.rows = rows
        self.solver = solver

    def offer(self, statement: Statement, statement_hash: str) -> Iterable[Evidence]:
        if statement_hash in self.wanted or shape_hash(statement) in self.rows:
            return self.solver.offer(statement, statement_hash)
        return ()


class _Accepted:
    """Sink: the evidence the kernel accepted, by statement hash."""

    def __init__(self) -> None:
        self.evidence: dict[str, Evidence] = {}

    def record(self, statement: Statement, statement_hash: str, evidence: Evidence, source: str) -> None:
        self.evidence[statement_hash] = evidence
