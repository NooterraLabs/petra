"""Properties of the plane shapes that connection parts are cut from. These are exact
geometry.

Lengths may be in any consistent unit; the kernel works in SI. A rectangle t by depth is
bent about the axis through its centroid parallel to t, so depth lies in the plane of
bending: a plate bent in its plane (t its thickness), or a seat's leg bent across its
thickness (t its length along the beam). Its elastic modulus is taken about the centroid
and its plastic modulus about the plastic neutral axis. tests/test_mechanics.py
integrates each section strip by strip and holds these formulas to that result.
"""
from __future__ import annotations

from fractions import Fraction

from ..kernel import Div, Expr, Max, Min, Mul, Pi, PowInt, Sqrt
from .algebra import add, c, mul, sq, sub


def circle_area(d: Expr) -> Expr:
    """pi d^2 / 4, the area of a circle of diameter d."""
    return Mul((Div(Pi(), c(4)), sq(d)))


def rectangle_plastic_modulus(t: Expr, depth: Expr) -> Expr:
    """Z = t depth^2 / 4: the first moment of each half about the middle, summed."""
    return Div(mul(t, sq(depth)), c(4))


def rectangle_elastic_modulus(t: Expr, depth: Expr) -> Expr:
    """S = I / (depth / 2) = (t depth^3 / 12) / (depth / 2) = t depth^2 / 6."""
    return Div(mul(t, sq(depth)), c(6))


def rectangle_elastic_thickness(moment: Expr, stress: Expr, depth: Expr) -> Expr:
    """The thickness t at which a rectangle t by depth, bent by `moment`, first reaches
    `stress` at its extreme fibre: stress t depth^2 / 6 = moment, so t = 6 moment /
    (stress depth^2)."""
    return Div(moment, Div(mul(stress, sq(depth)), c(6)))


def rectangle_net_plastic_modulus(t: Expr, depth: Expr, rows: int, pitch: Expr, hole: Expr) -> Expr:
    """Znet of a rectangle t by depth with one line of `rows` holes across the thickness,
    each `hole` wide, at `pitch`, centred on mid-depth, the holes no wider than the pitch.

    The plastic neutral axis stays at mid-depth by symmetry, so Znet = t/4 (depth^2 - 4
    sum of hole * |y_i|), where each hole removes its area hole * t at its distance |y_i|
    from the axis. For a regular line of holes, sum |y_i| = pitch (rows^2 - (rows mod 2)) / 4.
    With an odd number of rows the middle hole sits on the axis, and it also removes its
    own first moment t hole^2 / 4."""
    lever = Fraction(rows * rows - rows % 2, 4)   # sum of |y_i| / pitch over the rows
    removed = mul(c(4), hole, c(lever), pitch)
    if rows % 2:
        removed = add(removed, sq(hole))
    return Div(mul(t, sub(sq(depth), removed)), c(4))


def rectangle_net_elastic_modulus(t: Expr, depth: Expr, rows: int, pitch: Expr, hole: Expr) -> Expr:
    """Snet = Inet / (depth / 2) of the rectangle and line of holes rectangle_net_plastic_modulus
    takes. The elastic axis stays at mid-depth by symmetry. Each hole removes its own second
    moment, t hole^3 / 12, and its area t hole times y_i^2 at its distance y_i from the axis.
    For a regular line, sum y_i^2 = pitch^2 rows (rows^2 - 1) / 12. So
    Inet = t (depth^3 - rows hole^3 - hole pitch^2 rows (rows^2 - 1)) / 12."""
    spread = c(rows * (rows * rows - 1))       # 12 sum y_i^2 / pitch^2
    removed = add(mul(c(rows), PowInt(hole, 3)), mul(hole, sq(pitch), spread))
    return Div(mul(t, sub(PowInt(depth, 3), removed)), mul(c(6), depth))


def rectangle_peak_shear_stress(v: Expr, t: Expr, depth: Expr) -> Expr:
    """The largest shear stress v Q / (I t) in a rectangle t by depth carrying shear v in
    the plane of depth. It is reached at mid-depth, where Q = t depth^2 / 8 and
    I = t depth^3 / 12, so it is 3 v / (2 t depth)."""
    return Div(mul(c(3), v), mul(c(2), t, depth))


def tee_moduli(hc: Expr, tw: Expr, bf: Expr, tf: Expr) -> tuple[Expr, Expr]:
    """(S, Z) of a tee hc deep overall: a flange bf by tf and a stem (web) tw thick. S is
    the elastic modulus to the stem's tip, which is the tee's far fibre. Z is the plastic
    modulus. Fillets are neglected.

    The plastic neutral axis lies at y = max(A / (2 bf), tf + (A/2 - Af) / tw) above the
    flange's outer face. The first value applies when the flange holds at least half the
    area and the second when it does not; in each case it is the larger of the two,
    because bf > tw. With m = min(y, tf) and n = max(y, tf):
      Z = bf (m^2 + (tf - m)^2) / 2 + bf tf max(0, y - tf)
          + tw ((n - tf)^2 + (hc - n)^2) / 2 + tw (hc - tf) max(0, tf - y).
    In either case this is the first moment of area about y."""
    h = sub(hc, tf)
    af, aw = mul(bf, tf), mul(tw, h)
    area = add(af, aw)
    ybar = Div(add(mul(af, Div(tf, c(2))), mul(aw, add(tf, Div(h, c(2))))), area)
    inertia = add(Div(mul(bf, PowInt(tf, 3)), c(12)), mul(af, sq(sub(ybar, Div(tf, c(2))))),
                  Div(mul(tw, PowInt(h, 3)), c(12)), mul(aw, sq(sub(add(tf, Div(h, c(2))), ybar))))
    sc = Div(inertia, sub(hc, ybar))
    half = Div(area, c(2))
    y = Max((Div(half, bf), add(tf, Div(sub(half, af), tw))))
    m, n = Min((y, tf)), Max((y, tf))
    zc = add(Div(mul(bf, add(sq(m), sq(sub(tf, m)))), c(2)), mul(bf, tf, Max((c(0), sub(y, tf)))),
             Div(mul(tw, add(sq(sub(n, tf)), sq(sub(hc, n)))), c(2)), mul(tw, h, Max((c(0), sub(tf, y)))))
    return sc, zc


def hex_corner(across_flats: Expr) -> Expr:
    """The distance from the centre of a regular hexagon to a corner. For a width F across
    the flats it is F / sqrt 3, because the flats lie F / 2 = R cos 30 deg from the centre."""
    return Div(across_flats, Sqrt(c(3)))


def right_triangle(a: Expr, b: Expr) -> tuple[Expr, Expr, Expr, Expr]:
    """(sin theta, cos theta, hypotenuse, normal) of a right triangle with legs a and b.
    theta = atan(b / a) is the angle between the hypotenuse and leg a. The hypotenuse is
    sqrt(a^2 + b^2) = a / cos theta. The normal is the distance from the right angle to
    the hypotenuse, a b / hypotenuse = a sin theta."""
    hyp = Sqrt(add(sq(a), sq(b)))
    sin, cos = Div(b, hyp), Div(a, hyp)
    return sin, cos, hyp, Div(mul(a, b), hyp)
