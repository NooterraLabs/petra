"""How a force is shared along a weld, by the elastic method. The weld is a line (its
throat is taken as a unit width) and the parts it joins are rigid.

The force per unit length is a direct share, v over the weld's total length, plus a
moment's share. In bending about an axis in the weld's plane, that share is M y / I. In
twist about the weld's centroid, it is M r / Ip, normal to the radius r. The force at a
point is linear in its position along a straight segment, so its magnitude peaks at a
segment's end. tests/test_mechanics.py cuts each weld into short pieces, sums them, and
holds these formulas to the result.
"""
from __future__ import annotations

from ..kernel import Div, Expr, PowInt, Sqrt
from .algebra import add, c, mul, sq, sub


def fillet_throat(w: Expr) -> Expr:
    """The throat of an equal-leg fillet weld of leg w: the distance from its root to its
    face, w / sqrt 2."""
    return Div(w, Sqrt(c(2)))


def elastic_weld_line(v: Expr, e: Expr, length: Expr, lines: Expr) -> tuple[Expr, Expr]:
    """(horizontal, vertical) force per unit length at the end of `lines` parallel
    vertical weld lines of `length`. They are loaded by a vertical force v at eccentricity
    e, normal to the lines' plane. The moment v e bends the lines about the horizontal
    axis in their plane, and lines L^3 / 12 is their moment of inertia, so
      f_h = v e (L / 2) / (lines L^3 / 12) = 6 v e / (lines L^2),   f_v = v / (lines L)."""
    total = mul(lines, length)
    return Div(mul(c(6), v, e), mul(total, length)), Div(v, total)


def elastic_weld_c(v: Expr, e: Expr, length: Expr, ret: Expr) -> tuple[Expr, Expr, Expr]:
    """(horizontal, vertical at the return tips, vertical at the heel corners) force per
    unit length on a C-shaped weld. The weld is a vertical line of `length` L, with two
    horizontal returns of `ret` (kl) at its ends running toward the load. It is loaded by
    a vertical force v at e from the vertical line.

    The weld's total length is ltot = L + 2 kl, and its centroid lies xbar = kl^2 / ltot
    from the vertical line, so the load is ex = e - xbar from the centroid. Then
      Ix = L^3/12 + kl L^2 / 2,   Iy = 2 [kl^3/12 + kl (kl/2 - xbar)^2] + L xbar^2,
      Ip = Ix + Iy.
    At the return tips, (kl - xbar, +-L/2), and the heel corners, (-xbar, +-L/2):
      f_h = v ex (L/2) / Ip,   f_v = v / ltot + v ex x / Ip.
    These are the ends of the weld's segments, so the force's magnitude peaks at one of
    them, whichever side of the centroid the load lies."""
    total = add(length, mul(c(2), ret))
    xbar = Div(sq(ret), total)
    ix = add(Div(PowInt(length, 3), c(12)), Div(mul(ret, sq(length)), c(2)))
    iy = add(mul(c(2), add(Div(PowInt(ret, 3), c(12)), mul(ret, sq(sub(Div(ret, c(2)), xbar))))), mul(length, sq(xbar)))
    ip = add(ix, iy)
    moment = mul(v, sub(e, xbar))
    direct = Div(v, total)
    return (Div(mul(moment, Div(length, c(2))), ip), add(direct, Div(mul(moment, sub(ret, xbar)), ip)),
            sub(direct, Div(mul(moment, xbar), ip)))
