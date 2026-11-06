"""R6. Exact binomial tail inequality, the arithmetic core of a scenario bound.

The kernel checks  sum_{i<=k} C(n,i) eps^i (1-eps)^(n-i) <= beta  in exact rationals.
Reading it as "P(fail) <= eps with confidence 1 - beta" needs two premises the kernel
never sees: the trials were independent draws from the operating condition
(validated_model or assumed), and k failures were observed in n trials (measured).
The uncertainty elaborator attaches both.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..evaluate import Box, enclose
from ..interval import Q
from ..terms import Expr
from .base import Fault, Invalid, RuleSpec, TooWeak


@dataclass(frozen=True, slots=True)
class BinomialTail:
    """Goal. sum_{i=0}^{k} C(n, i) eps^i (1 - eps)^(n - i) <= beta.  Pure arithmetic: what
    the n trials mean is a premise outside the kernel.

    n and k are Exprs that must enclose to exact integer points, so a measured test
    record enters through labelled hypotheses like every other premise."""

    n: Expr
    k: Expr
    eps: Expr
    beta: Expr


@dataclass(frozen=True, slots=True)
class Arithmetic:
    """Proof. The kernel computes the binomial tail itself. No numbers needed."""


def tail(n: int, k: int, eps: Q) -> Q:
    """Exact rational tail sum_{i<=k} C(n,i) eps^i (1-eps)^(n-i), over the one common
    denominator b^n for eps = a/b, so only the final fraction is reduced."""
    a, b = eps.numerator, eps.denominator
    return Q(sum(math.comb(n, i) * a ** i * (b - a) ** (n - i) for i in range(k + 1)), b ** n)


def prove(goal: BinomialTail, body: Arithmetic, box: Box) -> Fault | None:
    """n, k, eps, beta must each enclose to a point over the box, n and k to integers.
    require 0 <= k <= n, 0 < eps < 1, 0 < beta < 1 (Invalid otherwise), and
    tail(n, k, eps) <= beta (TooWeak otherwise: more trials would be needed).

    Soundness is exact arithmetic. An enclosure that is a single point [v, v] contains
    the value at every h, so each of the four is the constant v on the whole box, and the
    goal is one inequality between rationals that `tail` evaluates without rounding.
    Conservative only in refusing a parameter that varies over the box.
    """
    values = []
    for name, e in (("n", goal.n), ("k", goal.k), ("eps", goal.eps), ("beta", goal.beta)):
        v = enclose(e, box)
        if v.lo != v.hi:
            return Invalid(f"{name} is not a single number over the box")
        values.append(v.lo)
    n, k, eps, beta = values
    if n.denominator != 1 or k.denominator != 1 or not (0 <= k <= n and 0 < eps < 1 and 0 < beta < 1):
        return Invalid(f"need integers 0 <= k <= n and 0 < eps, beta < 1, got n = {n}, k = {k}, eps = {eps}, beta = {beta}")
    if tail(int(n), int(k), eps) > beta:
        return TooWeak(f"the tail for {k} failures in {n} trials exceeds beta = {beta}: more trials are needed")
    return None


RULE = RuleSpec(
    id="R6",
    goal=BinomialTail,
    proofs=(Arithmetic,),
    refutations=(),
    tags=(
        ("binomial_tail", BinomialTail),
        ("arithmetic", Arithmetic),
    ),
    lemmas=(),
    prove=prove,
    refute=None,
)
