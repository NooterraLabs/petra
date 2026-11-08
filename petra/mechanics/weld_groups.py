"""How a force is shared along a weld. The weld is a line (its throat is taken as a unit
width) and the parts it joins are rigid.

By the elastic method the force per unit length is a direct share, v over the weld's
total length, plus a moment's share. In bending about an axis in the weld's plane, that
share is M y / I. In twist about the weld's centroid, it is M r / Ip, normal to the radius
r. The force at a point is linear in its position along a straight segment, so its
magnitude peaks at a segment's end.

By the instantaneous centre method the joined part turns about a centre, and each element
of the weld deforms in proportion to its distance from it, normal to its radius. An
element's force follows from its deformation and its angle by a code's curve, so the
caller passes bounds on it in. `line_ic` gives lower bounds on the force and the moment a
straight line holds for one centre; the code layer finds the centre that balances the
load. tests/test_mechanics.py cuts each weld into short pieces, sums them, and holds these
formulas to the result.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Sequence

from ..kernel import Div, Expr, Ln, Pi, PowInt, Sqrt
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


ANGLE_GRID = 1 << 80
"""The angles below are rounded outward to this many parts of a radian."""


def element_angles(r: Fraction, zs: Sequence[Fraction]) -> list[tuple[Expr, Expr]]:
    """(lo, hi) bounds in degrees on atan(z / r) at each z of zs, increasing from 0: the
    angle between a weld line and the force on its element at z when the line turns about
    a centre r > 0 from its midpoint, on its normal there (the force is normal to the
    element's radius (r, z)).

    The bounds are rationals in radians times 180 / pi, found by exact rational arithmetic
    along the line. With y = z / r, atan y - atan y' = atan d for d = (y - y') / (1 + y y')
    when y y' > -1. The steps are cut so that d <= 1/4 (past y' = 4 every step has d < 1/y'
    <= 1/4; before it, the cut lands at (y' + 1/4) / (1 - y'/4), the tangent of atan y' +
    atan 1/4). For 0 <= d <= 1 the series d - d^3/3 + d^5/5 - ... alternates with falling
    terms, so a partial sum ending on a subtracted term lies below atan d and adding the
    next term lies above it; the sums run until that term is below the rounding grid. Each
    step adds its bounds to the last and rounds them outward, so lo <= atan y <= hi."""
    quarter = Fraction(1, 4)

    def series(d: Fraction) -> tuple[Fraction, Fraction]:
        total, k = Fraction(0), 0
        while True:
            total += d ** (4 * k + 1) / (4 * k + 1) - d ** (4 * k + 3) / (4 * k + 3)
            k += 1
            last = d ** (4 * k + 1) / (4 * k + 1)
            if last * ANGLE_GRID < 1:
                return total, total + last

    def degrees(x: Fraction) -> Expr:
        return Div(mul(c(180), c(x)), Pi())

    assert r > 0 and zs[0] == 0 and all(p < q for p, q in zip(zs, zs[1:]))
    lo = hi = y_last = Fraction(0)
    out = [(c(0), c(0))]
    for z in zs[1:]:
        y = z / r
        while y_last < y:
            step = y if y_last >= 4 else min(y, (y_last + quarter) / (1 - y_last * quarter))
            s_lo, s_hi = series((step - y_last) / (1 + step * y_last))
            lo = Fraction(_floor((lo + s_lo) * ANGLE_GRID), ANGLE_GRID)
            hi = Fraction(-_floor(-(hi + s_hi) * ANGLE_GRID), ANGLE_GRID)
            y_last = step
        out.append((degrees(lo), degrees(hi)))
    return out


def _floor(x: Fraction) -> int:
    """The greatest integer at most x."""
    return x.numerator // x.denominator


def line_ic(r: Fraction, a: Fraction, zs: Sequence[Fraction], bounds: Sequence[tuple[Expr, Expr]]) -> tuple[Expr, Expr]:
    """Lower bounds on (V, M - V (a + r)) for a straight weld line of unit length that
    turns about a centre r > 0 from its midpoint, on its normal there. The load acts along
    the line, at a from it on the far side of the centre.

    The element at z along the line, rho = sqrt(z^2 + r^2) from the centre, carries a force
    F(z) per unit length normal to its radius, so r / rho of it along the line, and a moment
    F rho about the centre. By symmetry
      V = 2 int_0^(1/2) F r / rho dz,   M = 2 int_0^(1/2) F rho dz,
    and the line holds a load at a when M = V (a + r). The gap M - V (a + r) is
    2 int F w dz with w = (z^2 - a r) / rho, which is negative below z0 = sqrt(a r) and
    positive above it.

    zs runs from 0 to 1/2, and bounds[k] = (lo, hi) bound F on [zs[k], zs[k + 1]]. Then
    V >= 2 sum lo_k int r / rho, and over a piece of a segment above z0, int F w >= lo_k W,
    below it hi_k W, with W = int w over the piece. The segment holding z0 is split there.
    The integrals are exact:
      int r / rho dz = r asinh(z / r),   int rho dz = (z rho + r^2 asinh(z / r)) / 2."""
    assert zs[0] == 0 and zs[-1] == Fraction(1, 2) and all(p < q for p, q in zip(zs, zs[1:])) and r > 0
    assert len(bounds) == len(zs) - 1

    def ends(z: Fraction | None) -> tuple[Expr, Expr]:
        # (int_0^z r / rho, int_0^z rho), z None for z0
        if z is None:
            ratio, z_e, rho = Sqrt(c(a / r)), Sqrt(c(a * r)), Sqrt(c(a * r + r * r))
        else:
            ratio, z_e, rho = c(z / r), c(z), Sqrt(c(z * z + r * r))
        ash = Ln(add(ratio, Sqrt(add(c(1), sq(ratio)))))
        return mul(c(r), ash), Div(add(mul(z_e, rho), mul(c(r * r), ash)), c(2))

    at = [ends(z) for z in zs]
    split = ends(None)
    v_terms, g_terms = [], []
    for k, (lo, hi) in enumerate(bounds):
        p, q = zs[k], zs[k + 1]
        v_terms.append(mul(lo, sub(at[k + 1][0], at[k][0])))
        if p * p < a * r < q * q:
            pieces = [(at[k], split, hi), (split, at[k + 1], lo)]
        else:
            pieces = [(at[k], at[k + 1], lo if p * p >= a * r else hi)]
        for (v0, m0), (v1, m1), bound in pieces:
            g_terms.append(mul(bound, sub(sub(m1, m0), mul(c(a + r), sub(v1, v0)))))
    return mul(c(2), add(*v_terms)), mul(c(2), add(*g_terms))
