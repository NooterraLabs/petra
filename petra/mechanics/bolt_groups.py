"""How a force is shared among a group of bolts, by the elastic method. The bolts are
equal springs and the plate between them is rigid.

A force through the group's centroid is shared equally among the bolts. A moment M about
the centroid gives each bolt a force M r / Ip normal to its radius r from the centroid,
where Ip is the sum of r^2 over the bolts per unit bolt area. A force at an eccentricity
is the sum of the two.

The patterns are regular: `rows` rows at pitch s by `cols` columns at gauge g, with
n = rows x cols bolts, symmetric about the centroid. The force v acts along the columns,
at eccentricity e from the centroid across them. tests/test_mechanics.py sums every bolt
in a pattern and holds these formulas to the result.
"""
from __future__ import annotations

from fractions import Fraction

from ..kernel import Div, Expr, Sqrt
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
