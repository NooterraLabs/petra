"""Benchmark: family reuse versus recomputation. Untrusted measurement code.

FAMILIES lists the families it runs. Each is certified once into a fresh library. Then
N seeded queries inside its box run along two paths, each ending in a kernel Theorem for
the same statement:
  reuse      Library.offer (lookup and transport) + kernel.check
  recompute  SolverSource.offer (the solver) + kernel.check
Both paths consume offers as the pipeline does: check each candidate in turn and stop
at the first one the kernel accepts. The paths run interleaved, alternating which goes
first, after WARMUP queries through both, so warm-up and drift favour neither. The
statement hash, which the pipeline computes once whichever source answers, lies outside
both timed regions.

Reported per path: the median, p90 and range of the wall time per query; the total time
split into kernel.check and the rest, by rule, which sums to the total; and counters of
the work done. The solver counters are observed, not inferred: the solvers' expensive
calls are counted while the benchmark runs (_COUNTED). Each family has a model that
predicts the recompute/reuse ratio from its own counters. A measured ratio further than
FLAG_FACTOR from the prediction is flagged rather than reported as explained.
"""
from __future__ import annotations

import math
import random
import re
import statistics
import tempfile
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Mapping

from ..ir import Design
from ..kernel import GOAL_RULE, Evidence, Rejection, Statement, Theorem, check, statement_hash
from ..kernel.rules.r4_enclosure import AllNonpositive
from ..lang import load_design, parse_design
from ..library import FamilyEntry, Library, certify_family, claim_obligations, leaf_count
from ..registry import PartKind, Registry, build_registry
from ..solvers import SolverSource, r1_linear, r2_definite, r3_hypercircle, r4_enclosure
from ..units import FORCE

ROOT = Path(__file__).resolve().parents[2]

WARMUP = 3
"""Queries run through both paths before timing starts."""

FLAG_FACTOR = 1.5
"""A measured ratio further than this factor from the prediction is flagged."""

CALIBRATION_REPS = 5
"""Runs of each family statement that time a model's unit costs; the median is used."""


@dataclass(frozen=True)
class RuleSplit:
    """One rule's share of a path's total time, over the timed statements."""

    statements: int
    check_s: float     # inside kernel.check
    other_s: float     # outside it: lookup and transport, or the solver


@dataclass(frozen=True)
class PathStats:
    median_s: float
    p90_s: float
    min_s: float
    max_s: float
    check_median_s: float      # median time per query inside kernel.check
    other_median_s: float      # median time per query outside it
    by_rule: Mapping[str, RuleSplit]
    counts: Mapping[str, int]  # summed over the timed statements

    @property
    def total_s(self) -> float:
        return sum(s.check_s + s.other_s for s in self.by_rule.values())


@dataclass(frozen=True)
class UnitCost:
    """One rule's costs on the family's own statement, medians of CALIBRATION_REPS runs."""

    rule: str
    solve_s: float          # SolverSource until it offers the accepted evidence
    check_s: float          # kernel.check of that evidence
    offer_s: float          # Library.offer: lookup and transport
    reuse_check_s: float    # kernel.check of the library's evidence


@dataclass(frozen=True)
class BenchResult:
    family: "Family"
    queries: int
    statements: int
    reuse: PathStats
    recompute: PathStats
    units: tuple[UnitCost, ...]
    predicted_ratio: float
    basis: str              # what the prediction counts, for the report
    measured_ratio: float
    flagged: bool

    @property
    def explanation(self) -> str:
        return "; ".join(self.family.model.explain(self))


# --- Counting the solvers' work ------------------------------------------------------

def _search_cells(tally: Counter) -> None:
    found = r4_enclosure.search_stats()
    tally["cells"] += found["cells"]
    tally["search enclosures"] += found["enclosures"]


_COUNTED = (
    (r1_linear, "linprog", "LP solves", None),
    (r1_linear, "solve_exact", "exact solves", None),
    (r2_definite, "exact_ldl", "LDL factorizations", None),
    (r3_hypercircle, "enclose_minimizer", "solver hypercircles", None),
    (r4_enclosure, "search", "searches", _search_cells),
)
"""(module, attribute, counter, what else to count after each call). Each solver looks
these names up in its own module's globals, so swapping the attribute counts every call.
"exact solves" are the Gauss-Jordan repairs onto A x = b behind R1 points and R3 fields;
"solver hypercircles" are the R3 enclosures the lemma solver computes to propose a force
range."""

_SOLVER_WORK = tuple(counter for _, _, counter, _ in _COUNTED)


@contextmanager
def _counting(tally: Counter) -> Iterator[None]:
    saved = [(module, name, getattr(module, name)) for module, name, _, _ in _COUNTED]
    for module, name, counter, after in _COUNTED:
        setattr(module, name, _counted(getattr(module, name), counter, after, tally))
    try:
        yield
    finally:
        for module, name, fn in saved:
            setattr(module, name, fn)


def _counted(fn: Callable, counter: str, after: Callable[[Counter], None] | None, tally: Counter) -> Callable:
    def call(*args, **kwargs):
        tally[counter] += 1
        try:
            return fn(*args, **kwargs)
        finally:
            if after is not None:
                after(tally)

    return call


# --- One statement through one path ---------------------------------------------------


@dataclass(frozen=True)
class _Step:
    seconds: float
    check_seconds: float
    counts: Counter


def _settle(source, statement: Statement, digest: str, tally: Counter) -> _Step:
    """Time `source` on one statement the way the pipeline consumes it, then count. A
    theorem counts only when it is about the statement hashed to `digest`, so both paths
    are seen to prove the same statement."""
    before = tally.copy()
    checking, checks, evidence, result = 0.0, 0, None, None
    start = time.perf_counter()
    for evidence in source.offer(statement, digest):
        middle = time.perf_counter()
        result = check(statement, evidence)
        checking += time.perf_counter() - middle
        checks += 1
        if not isinstance(result, Rejection):
            break
    seconds = time.perf_counter() - start
    counts = tally - before
    leaves = leaf_count(evidence) if evidence is not None else 0
    exprs = len(statement.goal.exprs) if isinstance(statement.goal, AllNonpositive) else 0
    counts.update({
        "statements": 1,
        "theorems": int(isinstance(result, Theorem) and result.statement_hash == digest),
        "kernel checks": checks,
        "leaves": leaves,
        "enclosures": counts["search enclosures"] + leaves * exprs,
        "lemmas": len(evidence.defined) if evidence is not None else 0,
    })
    return _Step(seconds, checking, counts)


def _rule(statement: Statement) -> str:
    return GOAL_RULE[type(statement.goal)].id


# --- Models ------------------------------------------------------------------------------


def _ms(seconds: float) -> str:
    return f"{seconds * 1e3:.2f} ms"


def _share(part: float, whole: float) -> str:
    return f"{100 * part / whole:.0f} %" if whole else "n/a"


class EnclosureModel:
    """The cable family (R4). The unit of work in both paths is one evaluation of
    kernel.enclose on one expression over one cell: the solver evaluates with the
    kernel's own enclosure, and an R4 check encloses every expression on every leaf. So
    the model predicts the ratio from enclosure counts rather than cells, since a solver
    cell costs several enclosures (its own, its centre point and the trial halves of
    each split)."""

    shown = ("leaves", "cells", "enclosures")

    def calibrate(self, entries: tuple[FamilyEntry, ...], library: Library) -> tuple[UnitCost, ...]:
        return ()

    def predict(self, reuse: PathStats, recompute: PathStats, queries: int, units: tuple[UnitCost, ...]) -> tuple[float, str]:
        a, b = recompute.counts["enclosures"], reuse.counts["enclosures"]
        return (a / b if b else math.inf), f"from enclosure counts ({a} / {b})"

    def explain(self, r: BenchResult) -> list[str]:
        reuse, recompute = r.reuse, r.recompute
        lines = [
            f"reuse still pays the kernel re-check of the {reuse.counts['leaves']} leaves the {r.statements} query statements touch "
            f"({reuse.counts['enclosures']} enclosures, median {_ms(reuse.check_median_s)} per query, "
            f"{_share(reuse.check_median_s, reuse.median_s)} of the path) plus library lookup and transport "
            f"(median {_ms(reuse.other_median_s)} per query)",
            f"recompute pays the box search ({recompute.counts['cells']} cells, median {_ms(recompute.other_median_s)} per query) "
            f"and the kernel check of its own {recompute.counts['leaves']} leaves (median {_ms(recompute.check_median_s)} per query)",
            f"so the ratio is about (search + check) / (lookup + check) = ({_ms(recompute.other_median_s)} + "
            f"{_ms(recompute.check_median_s)}) / ({_ms(reuse.other_median_s)} + {_ms(reuse.check_median_s)}), "
            "and the kernel check, which both paths pay, bounds it",
        ]
        if recompute.counts["cells"] <= r.statements:
            lines.append("the solver needs about one cell per statement, because on one concrete cable the enclosure "
                         "over the whole query box already proves the bound, so reuse can save at most that one search; "
                         "reuse pays off when a query's own search needs many cells")
        if r.flagged:
            lines.append(f"FLAGGED: the measured {r.measured_ratio:.2f}x is not within {FLAG_FACTOR}x of the "
                         f"{r.predicted_ratio:.2f}x the enclosure counters predict, so enclosures alone do not explain the "
                         "time; each kernel check also pays a fixed cost the counters do not see (the canonical round trip "
                         "of statement and evidence), and reuse pays for lookup and transport")
        return lines


class SolverCallModel:
    """The truss family (R1, R2 with its R3 force lemmas, R3). Recompute runs HiGHS and an
    exact repair per load vertex (R1), float fields and an exact repair per vertex plus
    one solver hypercircle per force lemma and an exact LDL (R2), and fields per vertex
    (R3). That work is fixed by the number of load vertices and the size of the truss,
    not by the width of the box, so a solver call on the family's own statement costs
    what a call on a query does. The model times one solver call, one kernel check and
    one library offer per rule on the family statements before the timed run, and
    predicts the ratio as solver calls avoided against kernel checks paid, at those unit
    costs. The LP, exact-solve and LDL counters show the avoided calls happened on one
    path and not the other."""

    shown = ("LP solves", "exact solves", "LDL factorizations", "solver hypercircles", "lemmas", "kernel checks")

    def calibrate(self, entries: tuple[FamilyEntry, ...], library: Library) -> tuple[UnitCost, ...]:
        units = []
        for entry in sorted(entries, key=lambda e: _rule(e.statement)):
            digest = statement_hash(entry.statement)
            runs = [(_settle(SolverSource(), entry.statement, digest, Counter()), _settle(library, entry.statement, digest, Counter()))
                    for _ in range(CALIBRATION_REPS)]
            if not all(a.counts["theorems"] and b.counts["theorems"] for a, b in runs):
                raise ValueError(f"the family's own {_rule(entry.statement)} statement did not end in a theorem on both paths")
            units.append(UnitCost(
                _rule(entry.statement),
                statistics.median(a.seconds - a.check_seconds for a, _ in runs),
                statistics.median(a.check_seconds for a, _ in runs),
                statistics.median(b.seconds - b.check_seconds for _, b in runs),
                statistics.median(b.check_seconds for _, b in runs),
            ))
        return tuple(units)

    def predict(self, reuse: PathStats, recompute: PathStats, queries: int, units: tuple[UnitCost, ...]) -> tuple[float, str]:
        """A query carries the family's claims, so it costs what the family statements do."""
        solved = sum(u.solve_s + u.check_s for u in units)
        reused = sum(u.offer_s + u.reuse_check_s for u in units)
        costs = ", ".join(f"{u.rule} solve {_ms(u.solve_s)} + check {_ms(u.check_s)} against offer {_ms(u.offer_s)} + check "
                          f"{_ms(u.reuse_check_s)}" for u in units)
        return (solved / reused if reused else math.inf), f"from solver calls avoided against kernel checks paid, at unit costs timed on the family statements ({costs})"

    def explain(self, r: BenchResult) -> list[str]:
        reuse, recompute = r.reuse, r.recompute
        avoided = ", ".join(f"{recompute.counts.get(c, 0) / r.queries:g} {c}" for c in _SOLVER_WORK[:-1])
        made = sum(reuse.counts.get(c, 0) for c in _SOLVER_WORK)
        heaviest = max(reuse.by_rule, key=lambda rule: reuse.by_rule[rule].check_s)
        lines = [
            f"recompute makes {avoided} per query (median {_ms(recompute.other_median_s)} in the solvers) and then the kernel "
            f"check (median {_ms(recompute.check_median_s)})",
            f"reuse made {made} solver calls; it pays library lookup and transport (median {_ms(reuse.other_median_s)}) and the "
            f"same kernel check (median {_ms(reuse.check_median_s)}, {_share(reuse.check_median_s, reuse.median_s)} of the path; "
            f"the {heaviest} check alone is {_share(reuse.by_rule[heaviest].check_s, reuse.total_s)} of the reuse total)",
            f"so the ratio is about (solve + check) / (transport + check), and the kernel check, which both paths pay, bounds "
            f"it: with free transport it could reach only ({_ms(recompute.other_median_s)} + {_ms(recompute.check_median_s)}) / "
            f"{_ms(reuse.check_median_s)} = {(recompute.other_median_s + recompute.check_median_s) / reuse.check_median_s:.2f}x",
        ]
        if r.flagged:
            lines.append(f"FLAGGED: the measured {r.measured_ratio:.2f}x is not within {FLAG_FACTOR}x of the "
                         f"{r.predicted_ratio:.2f}x the unit costs on the family statements predict, so a query's work differs "
                         "from the family statement's, and the per-call model does not explain the time")
        return lines


# --- Families -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Family:
    """One family the benchmark runs: its file, how many queries a default run takes, how
    to write a query inside its box, and the model that explains its ratio."""

    name: str
    path: Path
    queries: int
    query: Callable[[int, random.Random, Design, str, Registry], str]
    model: EnclosureModel | SolverCallModel


def _cable_query(i: int, rng: random.Random, family: Design, text: str, registry: Registry) -> str:
    """A concrete design inside the family box: a cable size whose area and insulation
    lie in the family's ranges, a whole-metre run, a current range [0, I] and an
    ambient sub-range, with the family's claims."""
    params = family.params
    size, insulation = params["size"].range.value, params["insulation"].range.value
    sizes = sorted(
        (pid for pid, part in registry.parts.items()
         if part.kind is PartKind.CABLE and part.series is not None
         and size.contains(part.fixes["area"].lo) and insulation.contains(part.fixes["insulation"].lo)),
        key=lambda pid: registry.parts[pid].fixes["area"].lo,
    )
    run_, draw, amb = (params[p].range.value for p in ("run", "draw", "amb"))
    length = rng.randint(max(1, int(run_.lo)), int(run_.hi))
    current = rng.randint(1, int(draw.hi * 2)) / 2
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
        f"  on c.load current in [0 A, {current:g} A]",
        f"  {signed}",
        "}",
        "claim hot:  c.w1.temperature <= 70 degC under demand",
        "claim drop: c.w1.voltage_drop <= 3 % under demand",
        "",
    ])


LOAD_STEP = 500
"""Newtons. Truss query loads lie on this grid."""

_COMMENT = re.compile(r"^\s*#.*\n", re.M)
_PARAM_LINE = re.compile(r"^param\s+\w+\s+in\s+\[[^\]]*\]\s*\n", re.M)
_PARAM_REF = re.compile(r"\bparam\s+(\w+)")
_DESIGN = re.compile(r'design\s+"[^"]*"')
_SIGNATURE = re.compile(r'signed\s+"[^"]*"\s+source\s+"[^"]*"')


def _load_query(i: int, rng: random.Random, family: Design, text: str, registry: Registry) -> str:
    """The family's own text, so the geometry, sections, materials and claims are the
    family's, with each param (a node load) replaced by a signed load range: two distinct
    points of the LOAD_STEP grid inside the param's range, so every query box has as
    many vertices as the family box."""
    loads = {}
    for name, p in family.params.items():
        if p.range.dim != FORCE:
            raise ValueError(f"{family.path}: param {name} is not a load, so no load query can replace it")
        r = p.range.value
        lo, hi = sorted(rng.sample(range(math.ceil(r.lo / LOAD_STEP), math.floor(r.hi / LOAD_STEP) + 1), 2))
        loads[name] = f"in [{lo * LOAD_STEP} N, {hi * LOAD_STEP} N]"
    body = _PARAM_LINE.sub("", _COMMENT.sub("", text))
    body = _PARAM_REF.sub(lambda m: loads[m.group(1)], body)
    body = _DESIGN.sub(f'design "bench-truss-{i:04d}"', body, count=1)
    return _SIGNATURE.sub(f'signed "bench@example.org" source "bench query {i}"', body)


CABLE = Family("cable", ROOT / "examples" / "families" / "cu_pvc_clipped.lola", 200, _cable_query, EnclosureModel())
TRUSS = Family("truss", ROOT / "examples" / "families" / "warren_truss.lola", 40, _load_query, SolverCallModel())
FAMILIES: tuple[Family, ...] = (CABLE, TRUSS)
"""Query counts keep a default run of scripts/bench_family.py near a minute: one truss
query costs as much as ten to thirty cable queries."""


# --- The run ---------------------------------------------------------------------------------


@dataclass
class _Tally:
    times: list[float]
    checks: list[float]
    counts: Counter
    by_rule: dict[str, list]   # rule -> [statements, check s, other s]

    def add(self, rule: str, step: _Step) -> None:
        self.counts.update(step.counts)
        split = self.by_rule.setdefault(rule, [0, 0.0, 0.0])
        split[0] += 1
        split[1] += step.check_seconds
        split[2] += step.seconds - step.check_seconds

    def stats(self) -> PathStats:
        ordered = sorted(self.times)
        p90 = ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))]
        others = [t - c for t, c in zip(self.times, self.checks)]
        return PathStats(statistics.median(ordered), p90, ordered[0], ordered[-1], statistics.median(self.checks),
                         statistics.median(others), {rule: RuleSplit(*s) for rule, s in sorted(self.by_rule.items())}, dict(self.counts))


def run(family: Family, queries: int | None = None, seed: int = 0) -> BenchResult:
    """Raises ValueError when certification stores nothing for one of the family's
    claims, since no query could then reuse it."""
    queries = family.queries if queries is None else queries
    if queries < 1:
        raise ValueError("the benchmark needs at least one query")
    registry = build_registry()
    design = load_design(family.path, registry)
    text = Path(family.path).read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as root:
        library = Library(root)
        certified = certify_family(design, registry, library)
        if certified.skipped:
            raise ValueError(f"{family.path}: certification stored nothing for {'; '.join(certified.skipped)}")
        rng = random.Random(f"lola-bench/{family.name}/{seed}")
        work = [_statements(family.query(i, rng, design, text, registry), registry) for i in range(WARMUP + queries)]
        units = family.model.calibrate(certified.stored, library)
        reuse = _Tally([], [], Counter(), {})
        recompute = _Tally([], [], Counter(), {})
        tally: Counter = Counter()
        with _counting(tally):
            for i, statements in enumerate(work):
                paths = ((reuse, library), (recompute, SolverSource()))
                for path, source in (paths if i % 2 == 0 else paths[::-1]):
                    steps = [(_rule(s), _settle(source, s, digest, tally)) for s, digest in statements]
                    if i >= WARMUP:
                        for rule, step in steps:
                            path.add(rule, step)
                        path.times.append(sum(step.seconds for _, step in steps))
                        path.checks.append(sum(step.check_seconds for _, step in steps))
    reuse_stats, recompute_stats = reuse.stats(), recompute.stats()
    predicted, basis = family.model.predict(reuse_stats, recompute_stats, queries, units)
    measured = recompute_stats.median_s / reuse_stats.median_s if reuse_stats.median_s else math.inf
    flagged = not (1 / FLAG_FACTOR <= measured / predicted <= FLAG_FACTOR)
    statements = sum(len(s) for s in work[WARMUP:])
    return BenchResult(family, queries, statements, reuse_stats, recompute_stats, units, predicted, basis, measured, flagged)


def _statements(text: str, registry: Registry) -> tuple[tuple[Statement, str], ...]:
    """Each claim statement with its hash, which the pipeline computes once whichever
    source answers, so neither timed path pays it."""
    design = parse_design(text, "bench-query.lola", registry)
    return tuple((o.statement, statement_hash(o.statement)) for o in claim_obligations(design, registry))


def render(result: BenchResult) -> str:
    """One block per family: the header, one line per path starting with its name
    ("reuse", "recompute"), the split of each path's total time, then the predicted and
    measured ratio and the explanation. scripts/bench_family.py prints this."""
    r = result
    family = r.family

    def counters(p: PathStats) -> str:
        return "  ".join(f"{c} {p.counts.get(c, 0)}" for c in family.model.shown)

    def path(name: str, p: PathStats) -> str:
        return (f"{name:<10} median {_ms(p.median_s)}  p90 {_ms(p.p90_s)}  range {p.min_s * 1e3:.2f}-{p.max_s * 1e3:.2f} ms "
                f"per query  {counters(p)}  theorems {p.counts.get('theorems', 0)}/{r.statements}")

    def split(name: str, p: PathStats, other: str) -> str:
        def rules(pick: Callable[[RuleSplit], float]) -> str:
            return " ".join(f"{rule} {pick(s):.2f}" for rule, s in p.by_rule.items())

        check_s = sum(s.check_s for s in p.by_rule.values())
        other_s = sum(s.other_s for s in p.by_rule.values())
        return (f"split      {name} {p.total_s:.2f} s over {r.queries} queries = kernel check {check_s:.2f} s "
                f"({rules(lambda s: s.check_s)}) + {other} {other_s:.2f} s ({rules(lambda s: s.other_s)})")

    rules = ", ".join(f"{rule} {s.statements}" for rule, s in r.reuse.by_rule.items())
    return "\n".join([
        f"{family.name} family {Path(family.path).name}: {r.queries} queries, {r.statements} claim statements ({rules}), "
        f"paths interleaved after {WARMUP} warm-up queries",
        path("reuse", r.reuse),
        path("recompute", r.recompute),
        split("reuse", r.reuse, "lookup and transport"),
        split("recompute", r.recompute, "solver"),
        f"predicted  {r.predicted_ratio:.2f}x recompute/reuse, {r.basis}",
        f"measured   {r.measured_ratio:.2f}x recompute/reuse, from median wall time per query"
        + ("  FLAGGED: the counters do not explain it" if r.flagged else ""),
        f"why        {r.explanation}",
    ])


__all__ = ["CABLE", "FAMILIES", "TRUSS", "BenchResult", "Family", "PathStats", "RuleSplit", "UnitCost", "render", "run"]
