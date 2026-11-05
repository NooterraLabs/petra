"""Untrusted solvers. numpy and scipy allowed. A solver's only job is to produce evidence
the kernel accepts; a buggy solver costs an UNKNOWN, never a false PASS.

Each registered rule has one solver module with the same name as its kernel rule module
(lola/kernel/rules/r4_enclosure.py -> lola/solvers/r4_enclosure.py), exposing
`solve(statement) -> Iterable[Evidence]`. SOLVERS is derived from the rule registry by
that convention, so adding a rule never edits this file, and
tests/test_solver_registry.py fails when a rule has no solver module or a solver module
has no rule. Modules in _HELPERS are shared helpers, not rule solvers.

SolverSource dispatches on the goal type. Each goal solver first tries to prove, then to
refute, and yields every candidate it found; the pipeline stops at the first one the
kernel accepts.
"""
from __future__ import annotations

import importlib
from typing import Callable, Iterable, Mapping

from ..kernel import MODULE_OF, RULES, Evidence, Statement

GoalSolver = Callable[[Statement], Iterable[Evidence]]

_HELPERS: frozenset[str] = frozenset({"exact"})
"""Solver-package modules that serve several rules (exact rational repair)."""


def _solvers() -> Mapping[type, GoalSolver]:
    table: dict[type, GoalSolver] = {}
    for rule_id, spec in RULES.items():
        module = importlib.import_module(f"{__name__}.{MODULE_OF[rule_id]}")
        table[spec.goal] = module.solve
    return table


SOLVERS: Mapping[type, GoalSolver] = _solvers()
"""Goal class -> solve function, one per registered rule."""


class SolverSource:
    """EvidenceSource that runs the solver for the statement's goal. DefinedHyps are
    solved first by r3_hypercircle.defined_ranges and attached to the evidence."""

    name = "solver"

    def __init__(self, max_cells: int = 20000, time_limit_s: float = 30.0) -> None:
        raise NotImplementedError

    def offer(self, statement: Statement, statement_hash: str) -> Iterable[Evidence]:
        raise NotImplementedError


__all__ = ["SOLVERS", "GoalSolver", "SolverSource"]
