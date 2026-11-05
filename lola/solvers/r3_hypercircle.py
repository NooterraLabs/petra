"""R3 solver and DefinedHyp lemmas. Untrusted.

Per vertex: solve the weighted least-norm problem in floats with weights at their
midpoints (numpy.linalg.lstsq on W^-1/2), giving s~ and u~. Repair s~ exactly onto
B s = f(v) (exact.project_onto_equalities); u needs no repair (any u is admissible).
The bound tightness depends only on how close s and t = W^-1 B^T u are to s*, so float
accuracy matters for sharpness, never for soundness.
"""
from __future__ import annotations

from typing import Iterable

from ..kernel import DefinedRange, Evidence, Statement
from ..kernel.rules.r3_hypercircle import MinimizerComponent


def solve(statement: Statement) -> Iterable[Evidence]:
    raise NotImplementedError


def fields_for(problem, box: dict):
    """HypercircleFields for a QuadraticProblem over the RangeHyp box."""
    raise NotImplementedError


def defined_ranges(statement: Statement) -> tuple[DefinedRange, ...]:
    """For each DefinedHyp: compute fields, enclose the component with the kernel's own
    formula (calling kernel.enclose on the same expressions), widen by a relative 1e-9,
    and propose that range. The main solver then works over the proposed ranges."""
    raise NotImplementedError


def defined_range(sym: str, definition: MinimizerComponent, box: dict) -> DefinedRange:
    raise NotImplementedError
