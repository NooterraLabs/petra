"""Evidence transport: turn a family's evidence into evidence for a query statement whose
box sits inside the family box. Untrusted. Each rule's transport relies on a kernel
theorem, so the kernel accepts the result for the query statement on its own terms:

  R4  restrict the partition to the query box: drop subtrees disjoint from it, keep
      splits that cut it. Leaves shrink, and interval arithmetic is inclusion-isotone,
      so every kept leaf still encloses <= 0. Cost: only the leaves meeting the query.
  R5  same restriction on the domination partition; multipliers unchanged.
  R1  each query vertex is a convex combination of family vertices with exact weights
      (product of per-symbol barycentric weights); x_query = sum theta x_family exactly.
  R3  same convex combination on s; u likewise (any u is admissible). Bounds may loosen
      slightly, never break, because per-vertex enclosures hold over the family box.
  R2  reuse (reference_weights, L, d) unchanged: the query's weight enclosures are
      inside the family's, so r_j <= enclose(w_j, query).lo still holds.
  R6  unchanged.
DefinedRange entries transport the same way as R3 evidence.
"""
from __future__ import annotations

from ..kernel import Evidence, Partition, Statement


def transport(family_statement: Statement, family_evidence: Evidence, query: Statement, renaming: dict[str, str]) -> Evidence:
    raise NotImplementedError


def restrict_partition(partition: Partition, family_box: dict, query_box: dict) -> Partition:
    """TODO: recursive. Split(sym, at) with at <= query.lo(sym) -> restrict(right);
    at >= query.hi(sym) -> restrict(left); else keep the split with both children
    restricted to their halves of the query box."""
    raise NotImplementedError


def barycentric(query_vertex: dict, family_box: dict, syms: tuple[str, ...]) -> tuple:
    """Exact weights over the 2**k family vertices, in kernel vertex order."""
    raise NotImplementedError
