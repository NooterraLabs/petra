"""Benchmark: family reuse versus recomputation. Untrusted measurement code.

Setup: certify examples/families/cu_pvc_clipped.lola once. Generate N query designs
inside its box (seeded): random size, length, current range, ambient sub-range.

Paths timed per query, each ending in a kernel Theorem for the same statement:
  reuse      library.lookup + transport + kernel.check
  recompute  SolverSource (box search) + kernel.check

Reported for each path: median and p90 wall time over N queries after a warm-up, and
the counters that explain the time: kernel enclosures evaluated, solver cells visited
(recompute only), leaves re-checked (reuse only). The report states the expected ratio
as (cells visited + leaves checked) / leaves re-checked and compares it with the
measured ratio, so a speedup that the counters do not explain is flagged rather than
reported.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PathStats:
    median_s: float
    p90_s: float
    kernel_enclosures: int
    solver_cells: int
    leaves_checked: int


@dataclass(frozen=True)
class BenchResult:
    queries: int
    reuse: PathStats
    recompute: PathStats
    predicted_ratio: float
    measured_ratio: float
    explanation: str


def run(family_path: str, queries: int = 200, seed: int = 0) -> BenchResult:
    raise NotImplementedError


def render(result: BenchResult) -> str:
    """One line per path, each starting with its name ("reuse", "recompute"), then the
    predicted and measured ratio lines. scripts/bench_family.py prints this."""
    raise NotImplementedError
