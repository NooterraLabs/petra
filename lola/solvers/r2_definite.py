"""R2 solver. Untrusted.

Proof: reference weights r_j = enclose(w_j, box).lo rounded down to a short dyadic;
build M_ref exactly; compute LDL^T exactly with Fractions (no pivoting; PD needs none).
If some pivot is <= 0, M_ref is not PD: try a refutation.
Refutation: at the box point that minimises the smallest eigenvalue (found with
numpy.linalg.eigh on corner samples), take the eigenvector, rationalise it, and check
v^T M v <= 0 exactly before offering it.
"""
from __future__ import annotations

from typing import Iterable

from ..kernel import Evidence, Statement


def solve(statement: Statement) -> Iterable[Evidence]:
    raise NotImplementedError


def exact_ldl(entries: dict, n: int) -> tuple | None:
    """(L, d) or None when a pivot is not positive."""
    raise NotImplementedError
