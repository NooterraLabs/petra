"""Untrusted solvers. numpy and scipy allowed. A solver's only job is to produce evidence
the kernel accepts; a buggy solver costs an UNKNOWN, never a false PASS.

Each registered rule has one solver module with the same name as its kernel rule module
(lola/kernel/rules/r4_enclosure.py -> lola/solvers/r4_enclosure.py), exposing
`solve(statement) -> Iterable[Evidence]`. A rule that declares lemmas also has its
module expose `defined_ranges(statement, box=None) -> tuple[DefinedRange, ...]`, which
proposes and proves a range for each DefinedHyp whose quantity that rule defines, over
the RangeHyp box, or over `box` when one is given (a point box, for a refutation at that
point). SOLVERS and LEMMA_SOLVERS are derived from the rule registry by that convention,
so adding a rule never edits this file, and tests/test_solver_registry.py fails when a
rule has no solver module or a solver module has no rule. Modules in _HELPERS are shared
helpers, not rule solvers.

SolverSource dispatches on the goal type. Each goal solver first tries to prove, then to
refute, and yields every candidate it found; the pipeline stops at the first one the
kernel accepts. A solve function that names a `max_cells` or `time_limit_s` parameter
receives the source's limits, and one that names `original` receives the statement as
written, DefinedHyps included, so that it can look for a point that refutes it.
"""
from __future__ import annotations

import importlib
import inspect
import time
from typing import Callable, Iterable, Mapping, Union

from ..kernel import GOAL_RULE, MODULE_OF, REFUTATION_RULE, RULES, Box, DefinedHyp, DefinedRange, Evidence, Interval, RangeHyp, Statement, free_syms

GoalSolver = Callable[[Statement], Iterable[Evidence]]
LemmaSolver = Callable[[Statement, Union[Box, None]], tuple[DefinedRange, ...]]

_HELPERS: frozenset[str] = frozenset({"exact"})
"""Solver-package modules that serve several rules (exact rational repair)."""


def _module(rule_id: str):
    return importlib.import_module(f"{__name__}.{MODULE_OF[rule_id]}")


def _solvers() -> Mapping[type, GoalSolver]:
    table: dict[type, GoalSolver] = {}
    for rule_id, spec in RULES.items():
        table[spec.goal] = _module(rule_id).solve
    return table


def _lemma_solvers() -> Mapping[type, LemmaSolver]:
    return {lemma.defines: _module(rule_id).defined_ranges for rule_id, spec in RULES.items() for lemma in spec.lemmas}


SOLVERS: Mapping[type, GoalSolver] = _solvers()
"""Goal class -> solve function, one per registered rule."""

LEMMA_SOLVERS: Mapping[type, LemmaSolver] = _lemma_solvers()
"""QuantityDef class -> defined_ranges of the solver module of the rule that proves it."""


class SolverSource:
    """EvidenceSource that runs the solver for the statement's goal. DefinedHyps are
    solved first by the lemma solver of their quantity, and the goal solver then works
    on the statement with each DefinedHyp replaced by a RangeHyp over its proposed range.
    That is the box the kernel checks a proof over, so a proof for it, with the
    DefinedRanges attached, is a proof of the original statement.

    A refutation is checked differently: at its point, with each DefinedHyp over the
    range its lemma proves there. So a refutation whose point assigns exactly the
    original statement's RangeHyps, in order, gets the DefinedRanges the lemma solvers
    prove at that point, and any other refutation of a statement with a DefinedHyp is
    dropped, because at its point a defined symbol need not take its true value."""

    name = "solver"

    def __init__(self, max_cells: int = 20000, time_limit_s: float = 30.0) -> None:
        self.max_cells = max_cells
        self.time_limit_s = time_limit_s

    def offer(self, statement: Statement, statement_hash: str) -> Iterable[Evidence]:
        deadline = time.monotonic() + self.time_limit_s
        defined = tuple(h for h in statement.hyps if isinstance(h, DefinedHyp))
        ranges = _defined_ranges(statement, defined)
        range_syms = tuple(h.sym for h in statement.hyps if isinstance(h, RangeHyp))
        solve = SOLVERS[type(statement.goal)]
        for evidence in solve(_over_ranges(statement, ranges), **self._options(solve, statement)):
            body = evidence.body
            if not defined:
                yield evidence
            elif type(body) not in REFUTATION_RULE:
                yield Evidence(body, ranges)
            elif tuple(sym for sym, _ in body.point) == range_syms:
                yield Evidence(body, _defined_ranges(statement, defined, {sym: Interval(v, v) for sym, v in body.point}))
            if time.monotonic() >= deadline:
                return

    def _options(self, solve: GoalSolver, statement: Statement) -> dict:
        named = inspect.signature(solve).parameters
        options = {"max_cells": self.max_cells, "time_limit_s": self.time_limit_s, "original": statement}
        return {k: v for k, v in options.items() if k in named}


def _defined_ranges(statement: Statement, defined: tuple[DefinedHyp, ...], box: Box | None = None) -> tuple[DefinedRange, ...]:
    proposed: dict[str, DefinedRange] = {}
    for solve_lemma in dict.fromkeys(LEMMA_SOLVERS[type(h.definition)] for h in defined):
        proposed.update((r.sym, r) for r in solve_lemma(statement, box))
    missing = [h.sym for h in defined if h.sym not in proposed]
    if missing:
        raise ValueError(f"no lemma solver proposed a range for {missing}")
    return tuple(proposed[h.sym] for h in defined)


def _over_ranges(statement: Statement, ranges: tuple[DefinedRange, ...]) -> Statement:
    """Each DefinedHyp becomes a RangeHyp over its proposed range, and the RangeHyps only
    the definitions used are dropped, so the result is a well-formed statement."""
    if not ranges:
        return statement
    by_sym = {r.sym: r for r in ranges}
    used = free_syms(statement.goal) - GOAL_RULE[type(statement.goal)].binds(statement.goal)
    hyps = tuple(
        RangeHyp(h.sym, by_sym[h.sym].lo, by_sym[h.sym].hi, f"lemma:{h.sym}") if isinstance(h, DefinedHyp) else h
        for h in statement.hyps
        if h.sym in used
    )
    return Statement(hyps, statement.goal)


__all__ = ["LEMMA_SOLVERS", "SOLVERS", "GoalSolver", "LemmaSolver", "SolverSource"]
