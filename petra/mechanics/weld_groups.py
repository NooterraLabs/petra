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
caller passes bounds on it in. `group_ic` gives lower bounds on the force and the moment
a group of straight runs holds for one centre; the code layer finds the centre that
balances the load. tests/test_mechanics.py cuts each weld into short pieces, sums them, and holds these
formulas to the result.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Callable, NamedTuple, Sequence

from ..kernel import Div, Expr, Ln, Neg, Pi, PowInt, Sqrt
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


class Run(NamedTuple):
    """A straight run of weld in a group that turns about a centre (group_ic). It lies d
    from the centre, and its segments end at us along it, measured from the foot of its
    normal through the centre, rising from 0 or more. A run along the load lies at x =
    sign d; a run across it, a return, lies at y = d with its elements at x = sign u.
    Sign 1 puts it on the load's side of the centre, -1 behind the centre. Its throat, over
    the group's unit throat, scales its elements' force and deformation, which the bounds
    the caller passes carry."""
    d: Fraction
    us: tuple[Fraction, ...]
    across: bool
    sign: int
    throat: Fraction


def group_ic(arm: Fraction, runs: Sequence[Run], bounds: Sequence[Sequence[tuple[Expr, Expr]]]) -> tuple[Expr, Expr]:
    """Lower bounds on (V, M - V arm) for a weld group that turns about a centre. The load
    acts along y, at arm from the centre along x. The group is `runs` and their mirror
    images in the x axis.

    An element at (x, y), rho from the centre, carries a force F per unit length normal to
    its radius: x / rho of it along the load, and a moment F rho about the centre. On a run
    rho = sqrt(u^2 + d^2), and x is sign d along the load or sign u across it, so
      V = 2 sum int F x / rho du,   M = 2 sum int F rho du,
    and the group holds a load at arm when M = V arm. The gap M - V arm is 2 sum int F w du
    with w = (u^2 + d^2 - arm x) / rho. Its numerator is a quadratic in u with a leading
    coefficient of 1, so it is positive past its last root and changes sign at each root.
    Along the load it has one positive root, sqrt(arm sign d - d^2), where that is real
    and positive. Across it, with sign 1 and arm > 2 d, it has two:
    (arm -+ sqrt(arm^2 - 4 d^2)) / 2.

    bounds[i][k] = (lo, hi) bound F on run i's segment [us[k], us[k + 1]]. x keeps the
    run's sign along it, so int F x / rho >= lo X in front of the centre and hi X behind
    it, with X = int x / rho over the segment. Over a piece of a segment where w >= 0,
    int F w >= lo W, and where w <= 0, hi W, with W = int w over the piece. A segment is
    split at each root inside it. The integrals are exact, with asinh(u / d) =
    ln(u / d + sqrt(1 + (u / d)^2)) = ln((u + rho) / d):
      int d / rho du = d asinh(u / d),   int u / rho du = rho,
      int rho du = (u rho + d^2 asinh(u / d)) / 2.

    A straight line of unit length turning about a centre r from its midpoint, on its
    normal there, with the load a from the line, is one run along the load: d = r, us
    from 0 to 1/2, arm = a + r, and the root sqrt(a r)."""
    assert arm > 0 and len(bounds) == len(runs)
    v_terms, g_terms = [], []
    for run, segments in zip(runs, bounds):
        d, us, s = run.d, run.us, run.sign
        assert d > 0 and s in (1, -1) and us[0] >= 0 and all(p < q for p, q in zip(us, us[1:]))
        assert len(segments) == len(us) - 1
        roots = _roots(arm, run)
        at = [_ends(run, u) for u in us]
        for k, (lo, hi) in enumerate(segments):
            p, q = us[k], us[k + 1]
            v_terms.append(mul(lo if s > 0 else hi, sub(at[k + 1][0], at[k][0])))
            # w's sign on a piece: + with an even count of roots past it
            past = sum(1 for place, _ in roots if place(p) < 0)
            points = [at[k], *(ends for place, ends in roots if place(p) < 0 < place(q)), at[k + 1]]
            for j, ((v0, m0), (v1, m1)) in enumerate(zip(points, points[1:])):
                bound = hi if (past - j) % 2 else lo
                g_terms.append(mul(bound, sub(sub(m1, m0), mul(c(arm), sub(v1, v0)))))
    return mul(c(2), add(*v_terms)), mul(c(2), add(*g_terms))


def _ends(run: Run, u: Fraction) -> tuple[Expr, Expr]:
    """(int_0^u x / rho, int_0^u rho) up to a constant, at a rational u along the run."""
    d, s = run.d, run.sign
    ratio, rho = c(u / d), Sqrt(c(u * u + d * d))
    ash = Ln(add(ratio, Sqrt(add(c(1), sq(ratio)))))
    moment = Div(add(mul(c(u), rho), mul(c(d * d), ash)), c(2))
    if run.across:
        return (rho if s > 0 else Neg(rho)), moment
    return mul(c(s * d), ash), moment


def _roots(arm: Fraction, run: Run) -> list[tuple[Callable[[Fraction], int], tuple[Expr, Expr]]]:
    """The positive roots of w's numerator on the run, rising: for each, the sign of
    t - root at a rational t, and _ends at the root."""
    d = run.d
    if not run.across:
        q = arm * run.sign * d - d * d
        if q <= 0:
            return []
        ratio, rho = Sqrt(c(q / (d * d))), Sqrt(c(q + d * d))
        ash = Ln(add(ratio, Sqrt(add(c(1), sq(ratio)))))
        return [(lambda t: _sign(t * t - q), (mul(c(d), ash), Div(add(mul(Sqrt(c(q)), rho), mul(c(d * d), ash)), c(2))))]
    disc = arm * arm - 4 * d * d
    if run.sign < 0 or disc <= 0:
        return []
    out = []
    for side in (-1, 1):
        u = Div(add(c(arm), mul(c(side), Sqrt(c(disc)))), c(2))
        # on the root u^2 + d^2 = arm u
        rho = Sqrt(mul(c(arm), u))
        ash = Ln(Div(add(u, rho), c(d)))
        out.append((_place(arm, disc, side), (rho, Div(add(mul(u, rho), mul(c(d * d), ash)), c(2)))))
    return out


def _place(arm: Fraction, disc: Fraction, side: int) -> Callable[[Fraction], int]:
    """The sign of t - (arm + side sqrt(disc)) / 2 at a rational t, decided in rationals."""
    def place(t: Fraction) -> int:
        w = 2 * t - arm
        if side < 0:
            return 1 if w >= 0 else _sign(disc - w * w)
        return -1 if w <= 0 else _sign(w * w - disc)
    return place


def _sign(x: Fraction) -> int:
    return (x > 0) - (x < 0)
