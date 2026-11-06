"""The kernel's core term language: expressions, matrices, hypotheses, statements.

Goals, evidence bodies and the quantities a DefinedHyp may name are not here. Each rule
module under kernel/rules defines its own, so a new rule adds terms without editing this
file. kernel/rules/__init__.py holds the Goal and QuantityDef aliases.

This file contains no physics. A symbol is an opaque name. A label is an opaque string
that the kernel copies into results and never interprets. The meaning of a statement is
always:

    for every assignment of the RangeHyp symbols inside their ranges,
    and with every DefinedHyp symbol equal to the quantity its definition names,
    the goal holds.

Physics enters only through the numbers and shapes an elaborator (petra/models/*) puts
into these terms. The kernel decides whether evidence proves or refutes the statement.

Elaborator contract (not checkable by the kernel, enforced by models.base.StatementBuilder):
every number that comes from a premise enters a statement as a labelled RangeHyp, never
as a Const. That is what makes the footprint a structural function of the theorem.

Invariants (checked by `well_formed` in check.py, not here, so constructing a term stays
cheap for elaborators and the decoder):
- every Sym in the goal names exactly one hypothesis, and every hypothesis is used;
- RangeHyp.lo <= RangeHyp.hi;
- a DefinedHyp's definition refers only to RangeHyp symbols, never to another DefinedHyp;
- matrix dimensions agree with the goal's vectors.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Union

from .interval import Q

if TYPE_CHECKING:
    from .rules import Goal, QuantityDef

# ---------------------------------------------------------------------------
# Expressions. Evaluated by interval arithmetic in evaluate.py.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Const:
    value: Q


@dataclass(frozen=True, slots=True)
class Sym:
    name: str


@dataclass(frozen=True, slots=True)
class Pi:
    """The real number pi, enclosed by interval.i_pi()."""


@dataclass(frozen=True, slots=True)
class Add:
    args: tuple["Expr", ...]


@dataclass(frozen=True, slots=True)
class Mul:
    args: tuple["Expr", ...]


@dataclass(frozen=True, slots=True)
class Neg:
    arg: "Expr"


@dataclass(frozen=True, slots=True)
class Div:
    num: "Expr"
    den: "Expr"


@dataclass(frozen=True, slots=True)
class PowInt:
    base: "Expr"
    exponent: int


@dataclass(frozen=True, slots=True)
class Sqrt:
    arg: "Expr"


@dataclass(frozen=True, slots=True)
class Ln:
    arg: "Expr"


@dataclass(frozen=True, slots=True)
class Exp:
    arg: "Expr"


@dataclass(frozen=True, slots=True)
class Abs:
    arg: "Expr"


@dataclass(frozen=True, slots=True)
class Min:
    args: tuple["Expr", ...]


@dataclass(frozen=True, slots=True)
class Max:
    args: tuple["Expr", ...]


Expr = Union[Const, Sym, Pi, Add, Mul, Neg, Div, PowInt, Sqrt, Ln, Exp, Abs, Min, Max]

# ---------------------------------------------------------------------------
# Exact matrices. Sparse triples so JSON stays small; dense access in linalg.py.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Matrix:
    """rows x cols rational matrix. `entries` holds (i, j, value) sorted by (i, j), with
    no zero values and no duplicate positions. Canonical form makes hashing stable."""

    rows: int
    cols: int
    entries: tuple[tuple[int, int, Q], ...]


# ---------------------------------------------------------------------------
# Hypotheses.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RangeHyp:
    """sym ranges over [lo, hi]. `label` is opaque to the kernel. Outside the kernel it
    resolves to a premise id or a scope parameter id."""

    sym: str
    lo: Q
    hi: Q
    label: str


@dataclass(frozen=True, slots=True)
class DefinedHyp:
    """sym equals the quantity `definition` names. The statement fixes no range for it.
    The evidence proposes a range and proves it with the lemma of the rule that
    registered the definition's type (rules.LEMMAS), so solver-chosen numbers never enter
    the statement."""

    sym: str
    definition: "QuantityDef"


Hyp = Union[RangeHyp, DefinedHyp]


@dataclass(frozen=True, slots=True)
class Statement:
    """hyps are sorted by sym so two elaborations of the same design produce the same
    canonical JSON and the same hash. `goal` is a Goal variant defined by a rule module
    under kernel/rules; the rule registry maps its type to the rule that checks it."""

    hyps: tuple[Hyp, ...]
    goal: "Goal"
