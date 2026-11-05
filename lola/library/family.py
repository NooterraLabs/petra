"""Family certification. Untrusted orchestration around the trusted pipeline.

A family is a .lola design with `param` ranges. Certifying it elaborates the family's
claims only: coverage belongs to a concrete design, not to a reusable lemma, so the
cu_pvc family need not name a breaker. Each claim statement is self-contained, so each
discharged claim becomes its own FamilyEntry; a claim that does not discharge stores
nothing and is listed in `skipped`. The kernel checked every stored entry in this run,
and checks its transported evidence again at every reuse.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..ir import Design
from ..pipeline import Report
from ..registry import Registry
from .store import FamilyEntry, Library


@dataclass(frozen=True)
class FamilyReport:
    report: Report
    stored: tuple[FamilyEntry, ...]
    skipped: tuple[str, ...]        # requirement ids not stored, with the reason


def certify_family(design: Design, registry: Registry, library: Library) -> FamilyReport:
    """Requires design.is_family. Pure apart from library.add, which is idempotent."""
    raise NotImplementedError
