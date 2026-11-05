"""Evidence: what an untrusted solver hands the kernel for one statement.

Evidence holds only numbers and partitions chosen by a solver. It never holds a matrix
or an expression from the model: those live in the Statement, which an elaborator built
from the design. The kernel reads the statement and the evidence separately, so a solver
cannot change what is being proved.

This module holds the shared pieces. Each rule module under kernel/rules defines its own
proof and refutation body types and registers them in its RuleSpec. The body's type
decides which the kernel attempts.

Vertex order. R1 and R3 enumerate the vertices of the box spanned by the vertex symbols
(the hypothesis symbols that occur in b or f; a DefinedHyp symbol spans its proven
range). The order is fixed by the kernel: symbols sorted by name, bit k of the vertex
index selects hi (1) or lo (0) of the k-th symbol. Evidence lists one entry per vertex
in that order, so a solver cannot skip a vertex.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Union

from .interval import Q

if TYPE_CHECKING:
    from .rules import LemmaEvidence, ProofEvidence, RefutationEvidence

Vector = tuple[Q, ...]
Point = tuple[tuple[str, Q], ...]
"""An assignment of every RangeHyp symbol, sorted by symbol."""

# --- Partitions, used by R4 and R5 and by library transport -----------------


@dataclass(frozen=True, slots=True)
class Leaf:
    pass


@dataclass(frozen=True, slots=True)
class Split:
    """Split the current cell at sym = at into [lo, at] and [at, hi]. `at` must lie
    strictly inside the cell's current range for sym."""

    sym: str
    at: Q
    left: "Partition"
    right: "Partition"


Partition = Union[Leaf, Split]

# --- DefinedHyp lemmas ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DefinedRange:
    """Proposes lo <= sym <= hi for a DefinedHyp and proves it with `proof`, whose type
    must be the lemma evidence the defining rule registered for the DefinedHyp's
    QuantityDef (rules.LEMMAS). For MinimizerComponent that is R3's HypercircleFields."""

    sym: str
    lo: Q
    hi: Q
    proof: "LemmaEvidence"


# --- The envelope -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Evidence:
    """Everything one check consumes. `defined` must give exactly one DefinedRange per
    DefinedHyp of the statement. For refutation evidence each range is proved at the
    evidence point rather than over the box, so the counterexample is a point the
    premises admit together with the true defined values there."""

    body: "Union[ProofEvidence, RefutationEvidence]"
    defined: tuple[DefinedRange, ...] = ()
