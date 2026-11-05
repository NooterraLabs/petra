"""Benchmark: family reuse versus recomputation. Untrusted measurement code.

FAMILIES lists the families it runs. Each is certified once into a fresh library. Then
N seeded queries inside its box run along two paths, each ending in a kernel Theorem for
the same statement:
  reuse      Library.offer (the lookup, which returns an Instance of the family) + kernel.check
  recompute  SolverSource.offer (the solver) + kernel.check
Both paths consume offers as the pipeline does: check each candidate in turn and stop
at the first one the kernel accepts. The paths run interleaved, alternating which goes
first, after WARMUP queries through both, so warm-up and drift favour neither. The
statement hash, which the pipeline computes once whichever source answers, lies outside
both timed regions.

The kernel checks the family theorem behind an Instance once per process and memoises
it, so reuse has two costs. The first query of a process pays each family's check as
well: it is timed FIRST_REPS times, each run after kernel.forget_families(). Every later
query finds the memo warm, and the timed run, which follows those runs and the
calibration, measures that amortised cost. The kernel's own enclosures are counted on
both paths (_COUNTED), which shows that the timed Instance checks did no rule work.

Reported per path: the median, p90 and range of the wall time per query; the total time
split into kernel.check and the rest, by rule, which sums to the total; and counters of
the work done. The solver counters are observed, not inferred: the solvers' expensive
calls are counted while the benchmark runs. CostModel predicts the recompute/reuse ratio
from unit costs timed on the first warm-up query, and charges the Instance check by
statement size, since a renaming, a comparison and a box inclusion are linear in it. A
measured ratio further than FLAG_FACTOR from the prediction is flagged rather than
reported as explained.
"""
from __future__ import annotations

import importlib
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
from typing import Any, Callable, Iterator, Mapping

from ..ir import Design
from ..kernel import GOAL_RULE, MODULE_OF, Evidence, Instance, Rejection, Statement, Theorem, check, encode_statement, forget_families, statement_hash
from ..lang import load_design, parse_design
from ..library import Library, certify_family, claim_obligations, leaf_count
from ..registry import PartKind, Registry, build_registry
from ..solvers import SolverSource, r1_linear, r2_definite, r3_hypercircle, r4_enclosure
from ..units import FORCE

ROOT = Path(__file__).resolve().parents[2]

WARMUP = 3
"""Queries run through both paths before timing starts."""

FLAG_FACTOR = 1.5
"""A measured ratio further than this factor from the prediction is flagged."""

CALIBRATION_REPS = 5
"""Runs of each statement of the first warm-up query that time the unit costs; the median is used."""

FIRST_REPS = 5
"""Runs of the first query on a cold family memo."""


@dataclass(frozen=True)
class RuleSplit:
    """One rule's share of a path's total time, over the timed statements."""

    statements: int
    nodes: int         # JSON nodes of those statements, the size an Instance check walks
    check_s: float     # inside kernel.check
    other_s: float     # outside it: the lookup, or the solver


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
    """One rule's costs on the first warm-up query, summed over that query's statements of
    the rule (the cable's two claims are both R4), medians of CALIBRATION_REPS runs."""

    rule: str
    nodes: int              # JSON nodes of those statements
    solve_s: float          # SolverSource until it offers the accepted evidence
    check_s: float          # kernel.check of that evidence
    offer_s: float          # Library.offer: the lookup, which builds the Instance
    instance_s: float       # kernel.check of the Instance, with the family theorem memoised

    @property
    def per_node_s(self) -> float:
        return self.instance_s / self.nodes


@dataclass(frozen=True)
class FirstQuery:
    """Reuse on the first query of a process, FIRST_REPS runs each after
    kernel.forget_families(), so its Instance checks include every family check."""

    runs: tuple[float, ...]    # seconds per run, the query's statements summed
    check_runs: tuple[float, ...]
    theorems: int              # over every run
    statements: int            # over every run
    kernel_enclosures: int     # over every run

    @property
    def median_s(self) -> float:
        return statistics.median(self.runs)

    @property
    def check_median_s(self) -> float:
        return statistics.median(self.check_runs)


@dataclass(frozen=True)
class BenchResult:
    family: "Family"
    queries: int
    statements: int
    reuse: PathStats
    recompute: PathStats
    first: FirstQuery
    units: tuple[UnitCost, ...]
    predicted_ratio: float
    basis: str              # what the prediction counts, for the report
    measured_ratio: float
    flagged: bool

    @property
    def explanation(self) -> str:
        return "; ".join(self.family.model.explain(self))


# --- Counting the solvers' and the kernel's work ----------------------------------------

def _search_cells(tally: Counter) -> None:
    found = r4_enclosure.search_stats()
    tally["cells"] += found["cells"]
    tally["search enclosures"] += found["enclosures"]


_KERNEL_RULES = tuple(importlib.import_module(f"..kernel.rules.{name}", __package__) for name in sorted(set(MODULE_OF.values())))

_COUNTED = (
    (r1_linear, "linprog", "LP solves", None),
    (r1_linear, "solve_exact", "exact solves", None),
    (r2_definite, "exact_ldl", "LDL factorizations", None),
    (r3_hypercircle, "enclose_minimizer", "solver hypercircles", None),
    (r4_enclosure, "search", "searches", _search_cells),
    *((rule, "enclose", "kernel enclosures", None) for rule in _KERNEL_RULES if hasattr(rule, "enclose")),
)
"""(module, attribute, counter, what else to count after each call). Each solver and each
kernel rule looks these names up in its own module's globals, so swapping the attribute
counts every call and leaves the result alone. "exact solves" are the Gauss-Jordan
repairs onto A x = b behind R1 points and R3 fields; "solver hypercircles" are the R3
enclosures the lemma solver computes to propose force ranges, one per elastic problem;
"kernel enclosures" are the enclosures the kernel's rules evaluate while checking, in
every rule module the registry names."""

_SOLVER_WORK = tuple(counter for _, _, counter, _ in _COUNTED[:5])


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
class _Query:
    """One claim statement of a query, with what the pipeline computes once whichever
    source answers: its hash, and its size in JSON nodes."""

    statement: Statement
    digest: str
    nodes: int
    rule: str


@dataclass(frozen=True)
class _Step:
    seconds: float
    check_seconds: float
    counts: Counter


def _settle(source, query: _Query, tally: Counter) -> _Step:
    """Time `source` on one statement the way the pipeline consumes it, then count. A
    theorem counts only when it is about the statement hashed to `digest`, so both paths
    are seen to prove the same statement."""
    before = tally.copy()
    checking, checks, evidence, result = 0.0, 0, None, None
    start = time.perf_counter()
    for evidence in source.offer(query.statement, query.digest):
        middle = time.perf_counter()
        result = check(query.statement, evidence)
        checking += time.perf_counter() - middle
        checks += 1
        if not isinstance(result, Rejection):
            break
    seconds = time.perf_counter() - start
    counts = tally - before
    walked = evidence is not None and not isinstance(evidence.body, Instance)
    counts.update({
        "statements": 1,
        "nodes": query.nodes,
        "theorems": int(isinstance(result, Theorem) and result.statement_hash == query.digest),
        "kernel checks": checks,
        "instances": int(evidence is not None and isinstance(evidence.body, Instance)),
        "leaves": leaf_count(evidence) if walked else 0,
        "enclosures": counts["search enclosures"] + counts["kernel enclosures"],
        "lemmas": len(evidence.defined) if evidence is not None else 0,
    })
    return _Step(seconds, checking, counts)


def _timed(source, statements: tuple[_Query, ...]) -> tuple[float, float, bool]:
    """(seconds outside kernel.check, seconds inside it, whether every statement ended in
    a theorem about itself) for `source` on `statements`."""
    steps = [_settle(source, q, Counter()) for q in statements]
    return (sum(s.seconds - s.check_seconds for s in steps), sum(s.check_seconds for s in steps),
            all(s.counts["theorems"] for s in steps))


def _rule(statement: Statement) -> str:
    return GOAL_RULE[type(statement.goal)].id


def _nodes(obj: Any) -> int:
    if isinstance(obj, dict):
        return 1 + sum(map(_nodes, obj.values()))
    if isinstance(obj, list):
        return 1 + sum(map(_nodes, obj))
    return 1


# --- The model ----------------------------------------------------------------------------


def _ms(seconds: float) -> str:
    return f"{seconds * 1e3:.2f} ms"


def _share(part: float, whole: float) -> str:
    return f"{100 * part / whole:.0f} %" if whole else "n/a"


@dataclass(frozen=True)
class CostModel:
    """Predicts the recompute/reuse ratio per query from unit costs timed per rule on the
    first warm-up query, which the timed run does not count. Recompute is charged the
    solver call, whose work the counters show, and the kernel check. Reuse is charged the
    lookup and the Instance check, at its cost per statement node. That check renames
    the family statement, compares it with the query, checks the box inclusion and
    encodes, hashes and decodes both, a constant amount of work per node, so its cost is
    linear in statement size, and the model charges it the timed statements' size.
    `shown` names the counters each path line prints."""

    shown: tuple[str, ...]

    def calibrate(self, statements: tuple[_Query, ...], library: Library) -> tuple[UnitCost, ...]:
        units = []
        for rule in sorted({q.rule for q in statements}):
            mine = tuple(q for q in statements if q.rule == rule)
            solved, reused = [], []
            for i in range(CALIBRATION_REPS):
                if i % 2 == 0:
                    solved.append(_timed(SolverSource(), mine))
                    reused.append(_timed(library, mine))
                else:
                    reused.append(_timed(library, mine))
                    solved.append(_timed(SolverSource(), mine))
            if not all(proved for _, _, proved in solved + reused):
                raise ValueError(f"the first warm-up query's {rule} statements did not end in theorems on both paths")
            units.append(UnitCost(
                rule,
                sum(q.nodes for q in mine),
                statistics.median(other for other, _, _ in solved),
                statistics.median(checking for _, checking, _ in solved),
                statistics.median(other for other, _, _ in reused),
                statistics.median(checking for _, checking, _ in reused),
            ))
        return tuple(units)

    def predict(self, reuse: PathStats, recompute: PathStats, queries: int, units: tuple[UnitCost, ...]) -> tuple[float, str]:
        solved = sum(u.solve_s + u.check_s for u in units)
        reused = sum(u.offer_s + u.per_node_s * reuse.by_rule[u.rule].nodes / queries for u in units)
        costs = ", ".join(f"{u.rule} solve {_ms(u.solve_s)} + check {_ms(u.check_s)} against lookup {_ms(u.offer_s)} + Instance "
                          f"check {u.per_node_s * 1e6:.2f} us per node x {u.nodes} nodes" for u in units)
        return (solved / reused if reused else math.inf), ("from unit costs timed on the first warm-up query, the Instance check "
                                                           f"linear in statement size ({costs})")

    def explain(self, r: BenchResult) -> list[str]:
        reuse, recompute, first = r.reuse, r.recompute, r.first
        n = r.statements
        made = ", ".join(f"{recompute.counts.get(c, 0) / r.queries:g} {c}" for c in _SOLVER_WORK if recompute.counts.get(c, 0))
        per_node = sum(s.check_s for s in reuse.by_rule.values()) / reuse.counts["nodes"] if reuse.counts.get("nodes") else 0.0
        lines = [
            f"reuse looks each statement up (median {_ms(reuse.other_median_s)} per query, the canonical shape of the query) "
            f"and checks an Instance of its family (median {_ms(reuse.check_median_s)}, {_share(reuse.check_median_s, reuse.median_s)} "
            f"of the path): one encoding, hash and decoding of the query, an encoding and hash of the Instance, which carries the "
            f"family statement, then a renaming, a comparison and a box inclusion, {per_node * 1e6:.2f} us per node over "
            f"{reuse.counts['nodes'] // max(n, 1)} nodes per statement; it made "
            f"{sum(reuse.counts.get(c, 0) for c in _SOLVER_WORK)} solver calls and {reuse.counts.get('kernel enclosures', 0)} kernel "
            "enclosures, because the family theorems were already memoised",
            f"the first query of a process also checks each family once: median {_ms(first.median_s)} over {len(first.runs)} runs "
            f"(range {min(first.runs) * 1e3:.2f}-{max(first.runs) * 1e3:.2f} ms, kernel check {_ms(first.check_median_s)}, "
            f"{first.kernel_enclosures // max(len(first.runs), 1)} kernel enclosures per run), against the {_ms(reuse.median_s)} "
            "median of every later query",
            f"recompute runs the solvers ({made} per query, median {_ms(recompute.other_median_s)}) and a full kernel check "
            f"(median {_ms(recompute.check_median_s)}, {recompute.counts.get('kernel enclosures', 0) // max(n, 1)} kernel enclosures "
            f"and {recompute.counts.get('lemmas', 0) // max(n, 1)} lemmas per statement), which pays the same round trip of the "
            "statement plus the rule's own work",
            f"so the ratio is about (solve + check) / (lookup + Instance check) = ({_ms(recompute.other_median_s)} + "
            f"{_ms(recompute.check_median_s)}) / ({_ms(reuse.other_median_s)} + {_ms(reuse.check_median_s)}), and reuse is "
            "bounded by statement size, not by the family's evidence",
            f"both paths end in a kernel Theorem for the statement hash each query was hashed to: reuse "
            f"{reuse.counts.get('theorems', 0)}/{n}, recompute {recompute.counts.get('theorems', 0)}/{n}, first query "
            f"{first.theorems}/{first.statements}",
        ]
        if r.flagged:
            lines.append(f"FLAGGED: the measured {r.measured_ratio:.2f}x is not within {FLAG_FACTOR}x of the "
                         f"{r.predicted_ratio:.2f}x the unit costs predict, so the timed queries cost something the first "
                         "warm-up query did not")
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
    model: CostModel


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


CABLE = Family("cable", ROOT / "examples" / "families" / "cu_pvc_clipped.lola", 200, _cable_query,
               CostModel(("instances", "leaves", "cells", "kernel enclosures")))
TRUSS = Family("truss", ROOT / "examples" / "families" / "warren_truss.lola", 40, _load_query,
               CostModel(("instances", "LP solves", "exact solves", "LDL factorizations", "solver hypercircles", "lemmas", "kernel enclosures")))
FAMILIES: tuple[Family, ...] = (CABLE, TRUSS)
"""Query counts keep a default run of scripts/bench_family.py near a minute: one truss
query costs as much as ten to thirty cable queries."""


# --- The run ---------------------------------------------------------------------------------


@dataclass
class _Tally:
    times: list[float]
    checks: list[float]
    counts: Counter
    by_rule: dict[str, list]   # rule -> [statements, nodes, check s, other s]

    def add(self, query: _Query, step: _Step) -> None:
        self.counts.update(step.counts)
        split = self.by_rule.setdefault(query.rule, [0, 0, 0.0, 0.0])
        split[0] += 1
        split[1] += query.nodes
        split[2] += step.check_seconds
        split[3] += step.seconds - step.check_seconds

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
        reuse = _Tally([], [], Counter(), {})
        recompute = _Tally([], [], Counter(), {})
        tally: Counter = Counter()
        with _counting(tally):
            first = _first_query(work[0], library, tally)
            units = family.model.calibrate(work[0], library)
            for i, statements in enumerate(work):
                paths = ((reuse, library), (recompute, SolverSource()))
                for path, source in (paths if i % 2 == 0 else paths[::-1]):
                    steps = [(q, _settle(source, q, tally)) for q in statements]
                    if i >= WARMUP:
                        for q, step in steps:
                            path.add(q, step)
                        path.times.append(sum(step.seconds for _, step in steps))
                        path.checks.append(sum(step.check_seconds for _, step in steps))
    reuse_stats, recompute_stats = reuse.stats(), recompute.stats()
    predicted, basis = family.model.predict(reuse_stats, recompute_stats, queries, units)
    measured = recompute_stats.median_s / reuse_stats.median_s if reuse_stats.median_s else math.inf
    flagged = not (1 / FLAG_FACTOR <= measured / predicted <= FLAG_FACTOR)
    statements = sum(len(s) for s in work[WARMUP:])
    return BenchResult(family, queries, statements, reuse_stats, recompute_stats, first, units, predicted, basis, measured, flagged)


def _first_query(statements: tuple[_Query, ...], library: Library, tally: Counter) -> FirstQuery:
    """Reuse on one query FIRST_REPS times, each run after the kernel forgets every family
    theorem, so each run pays the family checks a process pays once."""
    runs, checks, theorems, enclosures = [], [], 0, 0
    for _ in range(FIRST_REPS):
        forget_families()
        steps = [_settle(library, q, tally) for q in statements]
        runs.append(sum(s.seconds for s in steps))
        checks.append(sum(s.check_seconds for s in steps))
        theorems += sum(s.counts["theorems"] for s in steps)
        enclosures += sum(s.counts["kernel enclosures"] for s in steps)
    return FirstQuery(tuple(runs), tuple(checks), theorems, FIRST_REPS * len(statements), enclosures)


def _statements(text: str, registry: Registry) -> tuple[_Query, ...]:
    """Each claim statement with its hash and size, which the pipeline computes once
    whichever source answers, so neither timed path pays them."""
    design = parse_design(text, "bench-query.lola", registry)
    out = []
    for o in claim_obligations(design, registry):
        out.append(_Query(o.statement, statement_hash(o.statement), _nodes(encode_statement(o.statement)), _rule(o.statement)))
    return tuple(out)


def render(result: BenchResult) -> str:
    """One block per family: the header, one line per path starting with its name
    ("reuse", "recompute"), the first query on a cold family memo, the split of each
    path's total time, then the predicted and measured ratio and the explanation.
    scripts/bench_family.py prints this."""
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

    first = r.first
    rules = ", ".join(f"{rule} {s.statements}" for rule, s in r.reuse.by_rule.items())
    return "\n".join([
        f"{family.name} family {Path(family.path).name}: {r.queries} queries, {r.statements} claim statements ({rules}), "
        f"paths interleaved after {WARMUP} warm-up queries",
        path("reuse", r.reuse),
        path("recompute", r.recompute),
        f"first      median {_ms(first.median_s)}  range {min(first.runs) * 1e3:.2f}-{max(first.runs) * 1e3:.2f} ms over "
        f"{len(first.runs)} runs of the first query, reuse on a cold family memo  kernel enclosures {first.kernel_enclosures}  "
        f"theorems {first.theorems}/{first.statements}",
        split("reuse", r.reuse, "lookup"),
        split("recompute", r.recompute, "solver"),
        f"predicted  {r.predicted_ratio:.2f}x recompute/reuse, {r.basis}",
        f"measured   {r.measured_ratio:.2f}x recompute/reuse, from median wall time per query"
        + ("  FLAGGED: the unit costs do not explain it" if r.flagged else ""),
        f"why        {r.explanation}",
    ])


__all__ = ["CABLE", "FAMILIES", "TRUSS", "BenchResult", "CostModel", "Family", "FirstQuery", "PathStats", "RuleSplit", "UnitCost", "render", "run"]
