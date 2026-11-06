"""Elastic buckling of flat plates.

tests/test_mechanics.py solves the plate's buckling equation by finite differences and
holds the formula below to the result.
"""
from __future__ import annotations

from ..kernel import Div, Expr, Pi
from .algebra import c, mul, sq, sub


def plate_buckling_stress(e: Expr, nu: Expr, coefficient: Expr, slenderness: Expr) -> Expr:
    """The stress at which a flat plate of slenderness b/t buckles (Bryan, 1891):
      Fcr = k pi^2 E / (12 (1 - nu^2) (b/t)^2).
    k is the buckling coefficient set by the plate's edge supports and its loading. It is
    4 for a square plate, simply supported on all four edges, in uniform compression. The
    12 (1 - nu^2) comes from the plate's flexural rigidity, D = E t^3 / (12 (1 - nu^2))."""
    return Div(mul(sq(Pi()), e, coefficient), mul(c(12), sub(c(1), sq(nu)), sq(slenderness)))
