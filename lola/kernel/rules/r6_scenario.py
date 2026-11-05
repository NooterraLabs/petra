"""R6. Exact binomial tail inequality, the arithmetic core of a scenario bound.

The kernel checks  sum_{i<=k} C(n,i) eps^i (1-eps)^(n-i) <= beta  in exact rationals.
Reading it as "P(fail) <= eps with confidence 1 - beta" needs two premises the kernel
never sees: the trials were independent draws from the operating condition
(validated_model or assumed), and k failures were observed in n trials (measured).
The uncertainty elaborator attaches both.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..evaluate import Box
from ..interval import Q
from ..terms import Expr
from .base import Fault, RuleSpec


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
    """Exact rational tail. TODO: iterate i = 0..k with math.comb; n up to 10**5 is fine."""
    raise NotImplementedError


def prove(goal: BinomialTail, body: Arithmetic, box: Box) -> Fault | None:
    """n, k, eps, beta must each enclose to a point over the box, n and k to integers.
    require 0 <= k <= n, 0 < eps < 1, 0 < beta < 1 (Invalid otherwise), and
    tail(n, k, eps) <= beta (TooWeak otherwise: more trials would be needed)."""
    raise NotImplementedError


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
