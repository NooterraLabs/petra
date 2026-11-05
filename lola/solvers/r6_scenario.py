"""R6 solver. The kernel computes the tail itself, so the only evidence is Arithmetic().
The solver still computes the tail in floats first and offers nothing when it clearly
exceeds beta, so a false claim reports UNKNOWN with a reason instead of a rejection."""
from __future__ import annotations

from typing import Iterable

from ..kernel import Evidence, Statement


def solve(statement: Statement) -> Iterable[Evidence]:
    raise NotImplementedError
