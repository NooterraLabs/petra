"""Interval evaluation and structural queries over Expr. Shared by every rule.

Untrusted solvers may import `enclose` to search (the R4 box solver does), because using
the kernel's own evaluator cannot make a check pass that should fail: the kernel
re-evaluates every leaf itself.
"""
from __future__ import annotations

from typing import Mapping

from .interval import Interval, Q
from .terms import Expr, Statement

Box = Mapping[str, Interval]
"""Symbol -> range. A point is a box of point intervals."""


class NotAffine(ValueError):
    """Raised by `affine_coefficients` when an expression is not affine in the requested
    symbols with rational coefficients."""


def enclose(expr: Expr, box: Box) -> Interval:
    """Natural interval extension of expr over box. Inclusion-isotone.

    Raises KernelArithmeticError (from interval.py) on an undefined operation, and
    KeyError for a symbol missing from the box. check.py guarantees the box is complete
    before any rule runs.
    TODO: one match statement over the 14 Expr variants; memoise shared subterms by id().
    """
    raise NotImplementedError


def free_syms(term: object) -> frozenset[str]:
    """Every Sym name inside any kernel term: an Expr, a goal, a QuantityDef, or a tuple of
    them. A generic walk over dataclass fields, so a new rule's goal needs no case here."""
    raise NotImplementedError


def statement_syms(statement: Statement, bound: frozenset[str] = frozenset()) -> frozenset[str]:
    """Every symbol the goal and the DefinedHyp definitions mention, minus `bound`, the
    symbols the goal binds itself. check.py passes GOAL_RULE[type(goal)].binds(goal), so
    this module never names a rule."""
    raise NotImplementedError


def affine_coefficients(expr: Expr, syms: tuple[str, ...]) -> tuple[Q, tuple[Q, ...]]:
    """Return (c0, (c_1..c_k)) with expr == c0 + sum c_i * syms[i] identically.

    TODO: structural recursion. Const -> (c, 0). Sym in syms -> unit vector.
      Add -> sum. Neg -> negate. Mul -> at most one non-constant factor, the others
      must fold to Const. Div -> denominator must fold to a nonzero Const. Anything else
      that mentions a sym in `syms` -> NotAffine. A subexpression that mentions none of
      `syms` must fold to an exact Const, otherwise NotAffine.
    """
    raise NotImplementedError


def vertices(box: Box, syms: tuple[str, ...]) -> tuple[dict[str, Q], ...]:
    """The 2**k vertices of the sub-box over sorted `syms`, in the canonical order the
    evidence module documents."""
    raise NotImplementedError


def point_box(point: tuple[tuple[str, Q], ...]) -> dict[str, Interval]:
    raise NotImplementedError
