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

The unit of work in both paths is one evaluation of kernel.enclose on one expression
over one cell: the solver evaluates with the kernel's own enclosure, and an R4 check
encloses every expression on every leaf. So the prediction counts enclosures rather
than cells, since a solver cell costs several enclosures (its own, its centre point and
the trial halves of each split). The two paths run interleaved, alternating which goes
first, so warm-up and drift favour neither.
"""
from __future__ import annotations

import random
import statistics
import tempfile
import time
from dataclasses import dataclass
from fractions import Fraction

from ..kernel import Evidence, Statement, Theorem, check, statement_hash
from ..kernel.rules.r4_enclosure import AllNonpositive
from ..lang import load_design, parse_design
from ..library import Library, certify_family, claim_obligations, leaf_count
from ..registry import PartKind, Registry, build_registry
from ..solvers import SolverSource
from ..solvers.r4_enclosure import search_stats

WARMUP = 3
"""Queries run through both paths before timing starts."""

FLAG_FACTOR = 1.5
"""A measured ratio further than this factor from the prediction is flagged."""


@dataclass(frozen=True)
class PathStats:
    median_s: float
    p90_s: float
    kernel_enclosures: int
    solver_cells: int
    leaves_checked: int
    min_s: float = 0.0
    max_s: float = 0.0
    check_median_s: float = 0.0     # median time per query inside kernel.check
    other_median_s: float = 0.0     # median time per query outside it: lookup and transport, or the search
    theorems: int = 0               # statements that ended in a kernel Theorem


@dataclass(frozen=True)
class BenchResult:
    queries: int
    reuse: PathStats
    recompute: PathStats
    predicted_ratio: float
    measured_ratio: float
    explanation: str
    statements: int = 0
    flagged: bool = False


@dataclass
class _Tally:
    times: list[float]
    checks: list[float]
    enclosures: int = 0
    cells: int = 0
    leaves: int = 0
    theorems: int = 0

    def stats(self) -> PathStats:
        ordered = sorted(self.times)
        p90 = ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))]
        others = [t - c for t, c in zip(self.times, self.checks)]
        return PathStats(statistics.median(ordered), p90, self.enclosures, self.cells, self.leaves,
                         ordered[0], ordered[-1], statistics.median(self.checks), statistics.median(others), self.theorems)


def run(family_path: str, queries: int = 200, seed: int = 0) -> BenchResult:
    """Raises ValueError when certification stores nothing for one of the family's
    claims, since no query could then reuse it."""
    if queries < 1:
        raise ValueError("the benchmark needs at least one query")
    registry = build_registry()
    family = load_design(family_path, registry)
    with tempfile.TemporaryDirectory() as root:
        library = Library(root)
        certified = certify_family(family, registry, library)
        if certified.skipped:
            raise ValueError(f"{family_path}: certification stored nothing for {'; '.join(certified.skipped)}")
        rng = random.Random(f"lola-bench/{seed}")
        work = [_statements(_query(i, rng, family.params, registry), registry) for i in range(WARMUP + queries)]
        reuse, recompute = _Tally([], []), _Tally([], [])
        for i, statements in enumerate(work):
            timed = i >= WARMUP
            paths = ((reuse, _reuse, library), (recompute, _recompute, None))
            for tally, path, arg in (paths if i % 2 == 0 else paths[::-1]):
                elapsed, checking = 0.0, 0.0
                for statement, digest in statements:
                    took, took_check, counted = path(statement, digest, arg)
                    elapsed += took
                    checking += took_check
                    if timed:
                        tally.enclosures += counted["enclosures"]
                        tally.cells += counted["cells"]
                        tally.leaves += counted["leaves"]
                        tally.theorems += counted["theorem"]
                if timed:
                    tally.times.append(elapsed)
                    tally.checks.append(checking)
    statements = sum(len(s) for s in work[WARMUP:])
    return _result(queries, statements, reuse.stats(), recompute.stats())


def _result(queries: int, statements: int, reuse: PathStats, recompute: PathStats) -> BenchResult:
    predicted = recompute.kernel_enclosures / reuse.kernel_enclosures if reuse.kernel_enclosures else float("inf")
    measured = recompute.median_s / reuse.median_s if reuse.median_s else float("inf")
    flagged = not (1 / FLAG_FACTOR <= measured / predicted <= FLAG_FACTOR)

    def ms(seconds: float) -> str:
        return f"{seconds * 1e3:.2f} ms"

    lines = [
        f"reuse still pays the kernel re-check of the {reuse.leaves_checked} leaves the {statements} query statements touch "
        f"({reuse.kernel_enclosures} enclosures, median {ms(reuse.check_median_s)} per query, "
        f"{_share(reuse.check_median_s, reuse.median_s)} of the path) plus library lookup and transport "
        f"(median {ms(reuse.other_median_s)} per query)",
        f"recompute pays the box search ({recompute.solver_cells} cells, median {ms(recompute.other_median_s)} per query) "
        f"and the kernel check of its own {recompute.leaves_checked} leaves (median {ms(recompute.check_median_s)} per query)",
        f"so the ratio is about (search + check) / (lookup + check) = ({ms(recompute.other_median_s)} + "
        f"{ms(recompute.check_median_s)}) / ({ms(reuse.other_median_s)} + {ms(reuse.check_median_s)}), "
        "and the kernel check, which both paths pay, bounds it",
    ]
    if recompute.solver_cells <= statements:
        lines.append("the solver needs about one cell per statement, because on one concrete cable the enclosure "
                     "over the whole query box already proves the bound, so reuse can save at most that one search; "
                     "reuse pays off when a query's own search needs many cells")
    if flagged:
        lines.append(f"FLAGGED: the measured {measured:.2f}x is not within {FLAG_FACTOR}x of the {predicted:.2f}x the "
                     "enclosure counters predict, so enclosures alone do not explain the time; each kernel check also "
                     "pays a fixed cost the counters do not see (the canonical round trip of statement and evidence), "
                     "and reuse pays for lookup and transport")
    return BenchResult(queries, reuse, recompute, predicted, measured, "; ".join(lines), statements, flagged)


def _share(part: float, whole: float) -> str:
    return f"{100 * part / whole:.0f} %" if whole else "n/a"


def render(result: BenchResult) -> str:
    """One line per path, each starting with its name ("reuse", "recompute"), then the
    predicted and measured ratio lines. scripts/bench_family.py prints this."""
    def path(name: str, p: PathStats, extra: str) -> str:
        return (f"{name:<10} median {p.median_s * 1e3:.2f} ms  p90 {p.p90_s * 1e3:.2f} ms  "
                f"range {p.min_s * 1e3:.2f}-{p.max_s * 1e3:.2f} ms per query  {extra}  "
                f"enclosures {p.kernel_enclosures}  theorems {p.theorems}/{result.statements}")

    return "\n".join([
        f"family reuse benchmark: {result.queries} queries, {result.statements} claim statements, paths interleaved after {WARMUP} warm-up queries",
        path("reuse", result.reuse, f"leaves re-checked {result.reuse.leaves_checked}"),
        path("recompute", result.recompute, f"solver cells {result.recompute.solver_cells}"),
        f"predicted  {result.predicted_ratio:.2f}x recompute/reuse, from enclosure counts "
        f"({result.recompute.kernel_enclosures} / {result.reuse.kernel_enclosures})",
        f"measured   {result.measured_ratio:.2f}x recompute/reuse, from median wall time per query"
        + ("  FLAGGED: the counters do not explain it" if result.flagged else ""),
        f"why        {result.explanation}",
    ])


def _reuse(statement: Statement, digest: str, library: Library) -> tuple[float, float, dict]:
    start = time.perf_counter()
    offered = list(library.offer(statement, digest))
    middle = time.perf_counter()
    result = check(statement, offered[0]) if offered else None
    end = time.perf_counter()
    leaves = leaf_count(offered[0]) if offered else 0
    return end - start, end - middle, {"enclosures": leaves * _exprs(statement), "cells": 0, "leaves": leaves,
                                       "theorem": isinstance(result, Theorem)}


def _recompute(statement: Statement, digest: str, _: object) -> tuple[float, float, dict]:
    start = time.perf_counter()
    offered = list(SolverSource().offer(statement, digest))
    searched = search_stats()
    middle = time.perf_counter()
    result = check(statement, offered[0]) if offered else None
    end = time.perf_counter()
    leaves = leaf_count(offered[0]) if offered else 0
    return end - start, end - middle, {"enclosures": searched["enclosures"] + leaves * _exprs(statement),
                                       "cells": searched["cells"], "leaves": leaves, "theorem": isinstance(result, Theorem)}


def _exprs(statement: Statement) -> int:
    return len(statement.goal.exprs) if isinstance(statement.goal, AllNonpositive) else 1


def _statements(text: str, registry: Registry) -> tuple[tuple[Statement, str], ...]:
    """Each claim statement with its hash, which the pipeline computes once whichever
    source answers, so neither timed path pays it."""
    design = parse_design(text, "bench-query.lola", registry)
    return tuple((o.statement, statement_hash(o.statement)) for o in claim_obligations(design, registry))


def _query(i: int, rng: random.Random, params, registry: Registry) -> str:
    """A concrete design inside the family box: a cable size whose area and insulation
    lie in the family's ranges, a whole-metre run, a current range [0, I] and an
    ambient sub-range, with the family's claims."""
    size, insulation = params["size"].range.value, params["insulation"].range.value
    sizes = sorted(
        (pid for pid, part in registry.parts.items()
         if part.kind is PartKind.CABLE and part.series is not None
         and size.contains(part.fixes["area"].lo) and insulation.contains(part.fixes["insulation"].lo)),
        key=lambda pid: registry.parts[pid].fixes["area"].lo,
    )
    run, draw, amb = (params[p].range.value for p in ("run", "draw", "amb"))
    length = rng.randint(max(1, int(run.lo)), int(run.hi))
    current = Fraction(rng.randint(1, int(draw.hi * 2)), 2)
    lo = rng.randint(int(amb.lo), int(amb.hi))
    hi = rng.randint(lo, int(amb.hi))
    signed = f'signed "bench@example.org" source "bench query {i}"'
    return "\n".join([
        "lola 0",
        f'design "bench-query-{i:04d}" {{',
        '  owner "bench@example.org"',
        "  environment indoor_dry",
        "}",
        f"ambient in [{lo} degC, {hi} degC] {signed}",
        "circuit c {",
        "  supply mains voltage 230 V",
        f"  wire w1 cable {rng.choice(sizes)} length {length} m install install.clipped_direct",
        "  consumer load",
        "  connect mains.out -> w1.a",
        "  connect w1.b -> load.in",
        "}",
        "load demand {",
        f"  on c.load current in [0 A, {float(current):g} A]",
        f"  {signed}",
        "}",
        "claim hot:  c.w1.temperature <= 70 degC under demand",
        "claim drop: c.w1.voltage_drop <= 3 % under demand",
        "",
    ])


__all__ = ["BenchResult", "PathStats", "render", "run"]
