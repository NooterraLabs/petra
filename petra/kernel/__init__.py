"""The arithmetic of the Python reader. Mathematics only; standard library only.

Rationals, exact intervals, the nodes of an expression, and the enclosure of an expression
over a box. deck.py, rule.py and grid.py search with these for the hints of proofs.json and
for the reader's own cells, which `petra check` compares with the kernel's.

This is not a checker and it gives no verdict. The kernel is petra-verify, under kernel/,
and it does this arithmetic again for itself (kernel/Petra/Interval.lean).

    enclose(expr, box)        an interval that holds every value of the expression over the box
    Interval, Q, parse_q      exact intervals over the rationals
    the term constructors     Const, Sym, Add and the rest (terms.py)
"""
from __future__ import annotations

from .evaluate import Box, enclose, free_syms
from .interval import MAX_ARGUMENT, PRECISION_BITS, Interval, KernelArithmeticError, Q, i_cos, i_ln, i_pi, i_sqrt, parse_q
from .terms import (
    Abs,
    Add,
    Const,
    Cos,
    Div,
    Exp,
    Expr,
    Ln,
    Max,
    Min,
    Mul,
    Neg,
    Pi,
    PowInt,
    Sqrt,
    Sym,
)

KERNEL_LINE_BUDGET = 1500
"""tests/test_kernel_budget.py counts non-blank, non-comment, non-docstring lines under
petra/kernel and fails above this number."""
