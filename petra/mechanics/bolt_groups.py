"""How a force is shared among a group of bolts. The plate between the bolts is rigid.

By the elastic method the bolts are equal springs. A force through the group's centroid
is shared equally among the bolts. A moment M about the centroid gives each bolt a force
M r / Ip normal to its radius r from the centroid, where Ip is the sum of r^2 over the
bolts per unit bolt area. A force at an eccentricity is the sum of the two.

By the instantaneous centre method the plate turns about a centre, and each bolt deforms
in proportion to its distance from it, normal to its radius. A bolt's force follows from
its deformation by a load-deformation curve, which is a code's (fitted to tests), so the
caller passes it in. `instantaneous_centre` gives the force and the moment the bolts hold
for one centre; the code layer finds the centre that balances the load.

The patterns are regular: `rows` rows at pitch s by `cols` columns at gauge g, with
n = rows x cols bolts, symmetric about the centroid. The force v acts along the columns,
at eccentricity e from the centroid across them. tests/test_mechanics.py sums every bolt
in a pattern and holds these formulas to the result.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Callable

from ..kernel import Abs, Div, Expr, Sqrt
from .algebra import add, c, mul, sq


def polar_moment(n: Expr, rows: int, cols: int, s: Expr, g: Expr) -> Expr:
    """Ip = n [(rows^2 - 1) s^2 + (cols^2 - 1) g^2] / 12, the sum of x^2 + y^2 over the
    pattern. The sum of y^2 down a column of `rows` bolts at pitch s is
    rows (rows^2 - 1) s^2 / 12, and the same holds across a row."""
    return mul(n, Div(add(mul(c(rows * rows - 1), sq(s)), mul(c(cols * cols - 1), sq(g))), c(12)))


def corner_radius(rows: int, cols: int, s: Expr, g: Expr) -> Expr:
    """The distance from the centroid to a corner bolt, which is the farthest bolt:
    sqrt(((rows - 1) s / 2)^2 + ((cols - 1) g / 2)^2)."""
    return Sqrt(add(sq(mul(c(Fraction(rows - 1, 2)), s)), sq(mul(c(Fraction(cols - 1, 2)), g))))


def elastic_bolt_force(v: Expr, e: Expr, n: Expr, rows: int, cols: int, s: Expr, g: Expr) -> tuple[Expr, Expr]:
    """(across, along) components of the force on the critical bolt: the corner bolt on
    the side where the twist adds to the direct share. The corner is at
    x = (cols - 1) g / 2, y = (rows - 1) s / 2, so
      f_across = v e y / Ip,   f_along = v / n + v e x / Ip."""
    ip = polar_moment(n, rows, cols, s, g)
    x = mul(c(Fraction(cols - 1, 2)), g)
    y = mul(c(Fraction(rows - 1, 2)), s)
    moment = mul(v, e)
    return Div(mul(moment, y), ip), add(Div(v, n), Div(mul(moment, x), ip))


def elastic_block_force(v: Expr, e: Expr, n: Expr, rows: int, cols: int, s: Expr, g: Expr, block_rows: int, block_cols: int) -> tuple[Expr, Expr]:
    """(across, along) components of the resultant force on a block of bolts: the
    k = block_rows rows at one end of the pattern and the j = block_cols columns at one
    side. Over those bolts |sum y| = j k (rows - k) s / 2 and |sum x| = k j (cols - j) g / 2,
    so
      f_across = v e |sum y| / Ip,   f_along = v k j / n + v e |sum x| / Ip,
    taking the side on which the twist adds to the direct share. A block that holds every
    bolt carries v."""
    ip = polar_moment(n, rows, cols, s, g)
    moment = mul(v, e)
    kr, jc = block_rows, block_cols
    sum_y = mul(c(Fraction(jc * kr * (rows - kr), 2)), s)
    sum_x = mul(c(Fraction(kr * jc * (cols - jc), 2)), g)
    return Div(mul(moment, sum_y), ip), add(Div(mul(v, c(kr * jc)), n), Div(mul(moment, sum_x), ip))


def elastic_centre(e: Expr, rows: int, cols: int, s: Expr, g: Expr) -> Expr:
    """How far behind the centroid, on the axis across the force, the elastic method's
    bolt forces turn about under a force at e. A bolt at (x, y) carries v / n along the
    force and M r / Ip normal to its radius, so its force is proportional to
    (-y, x + Ip / (n e)) with Ip the sum of x^2 + y^2: every force is normal to the line from
    (-Ip / (n e), 0) to its bolt. On the pattern Ip / n = (g^2 (cols^2 - 1) + s^2 (rows^2 -
    1)) / 12."""
    spread = add(mul(c(cols * cols - 1), sq(g)), mul(c(rows * rows - 1), sq(s)))
    return Div(spread, mul(c(12), e))


def instantaneous_centre(r: Expr, rows: int, cols: int, s: Expr, g: Expr, curve: Callable[[Expr], Expr]) -> tuple[Expr, Expr]:
    """(V, M): the force along the load and the moment about the centre that the bolts
    hold when the pattern turns about a centre on the axis through the centroid across the
    force, r > 0 from the centroid on the side away from the load. The load acts on the
    side of the corner (X, Y) = ((cols - 1) g / 2, (rows - 1) s / 2), so that corner is the
    farthest bolt, rho_max = sqrt((X + r)^2 + Y^2) from the centre.

    The bolt at (x, y) is rho = sqrt((x + r)^2 + y^2) from the centre. It deforms in
    proportion to rho, so it carries curve(rho / rho_max) of one bolt's strength, normal to
    its radius. Along the load that force has the component curve (x + r) / rho, and about
    the centre the moment curve rho, so
      V = sum curve(rho / rho_max) (x + r) / rho,   M = sum curve(rho / rho_max) rho.
    The bolts hold a load P at eccentricity e from the centroid when P = V and
    P (e + r) = M; the components across the load cancel, the pattern being symmetric
    about the axis. A bolt at the centre itself has rho = 0, where the quotients are
    undefined: the caller keeps r off every bolt of a middle row."""
    far = Sqrt(add(sq(add(mul(c(Fraction(cols - 1, 2)), g), r)), sq(mul(c(Fraction(rows - 1, 2)), s))))
    v_terms, m_terms = [], []
    for j in range(cols):
        arm = add(mul(c(Fraction(2 * j - cols + 1, 2)), g), r)
        for i in range((rows + 1) // 2):
            level = Fraction(rows - 1 - 2 * i, 2)
            rho = Abs(arm) if level == 0 else Sqrt(add(sq(arm), sq(mul(c(level), s))))
            force = curve(Div(rho, far))
            count = 1 if level == 0 else 2
            v_terms.append(mul(c(count), force, Div(arm, rho)))
            m_terms.append(mul(c(count), force, rho))
    return add(*v_terms), add(*m_terms)
