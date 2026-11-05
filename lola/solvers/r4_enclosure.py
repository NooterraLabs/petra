"""R4 solver: branch and bound over the hypothesis box. Untrusted, but it evaluates with
kernel.enclose so that every leaf it reports is a leaf the kernel will accept.

Loop (best-first on the largest upper enclosure):
  cell passes if every expr encloses <= 0 -> leaf
  cell fails at its centre point (point enclosure > 0) -> PointWitness, stop
  otherwise split the symbol with the largest width times |partial sensitivity|
  (sensitivity estimated by enclosing on halves), at the midpoint rounded to a short
  dyadic so leaf boundaries stay cheap to encode.
Gives up after max_cells and returns nothing (the obligation becomes UNKNOWN).

Also used by r5_moment.py for R5 domination trees and by library/transport.py to re-split
the part of a query box that a family partition does not cover.
"""
from __future__ import annotations

from typing import Iterable

from ..kernel import Evidence, Expr, Partition, Statement


def solve(statement: Statement, max_cells: int = 20000) -> Iterable[Evidence]:
    raise NotImplementedError


def search(exprs: tuple[Expr, ...], box: dict, max_cells: int) -> Partition | dict | None:
    """Partition on success, a violating point (dict) on refutation, None on give-up."""
    raise NotImplementedError


def search_stats() -> dict:
    """Counters from the last search: cells visited, enclosures evaluated, max depth.
    The family benchmark reports these to explain its timing."""
    raise NotImplementedError
