"""AISC 360-22 Chapter J limit states as kernel expressions. Trusted physics.

Every function takes kernel Exprs (hypothesis symbols from a StatementBuilder) and returns
the nominal strength Rn, or the quantity a rule compares, as an Expr in SI units. No
function reads a registry or a design: the callers in checks.py decide which premise each
argument is. Numbers here are the formulas' own coefficients, fixed by the equation they
come from (the 0.60 of Fnw = 0.60 FEXX); resistance and safety factors, table values and
material values are registry constants, so they appear in footprints.

A formula that depends on an inch- or ksi-valued quantity in a non-homogeneous way (the
1/16 in hole allowance, the Fy in ksi under a square root) uses the unit as an exact
Const, so the expression stays in SI.

Equation numbers are AISC 360-22's unless marked Manual (AISC Steel Construction Manual,
16th ed., whose methods are encoded here, not its text) or Kulak (Kulak, Fisher and
Struik, Guide to Design Criteria for Bolted and Riveted Joints, 2nd ed., 1987).
"""
from __future__ import annotations

from fractions import Fraction

from ...kernel import Add, Const, Div, Exp, Expr, Ln, Max, Min, Mul, Neg, Pi, PowInt, Sqrt
from ...units import CUSTOMARY

INCH = CUSTOMARY["inch"][0]
KSI = CUSTOMARY["ksi"][0]


def c(x: Fraction | int | str) -> Const:
    return Const(Fraction(x))


def add(*xs: Expr) -> Expr:
    return xs[0] if len(xs) == 1 else Add(tuple(xs))


def mul(*xs: Expr) -> Expr:
    return xs[0] if len(xs) == 1 else Mul(tuple(xs))


def sub(a: Expr, b: Expr) -> Expr:
    return Add((a, Neg(b)))


def div(a: Expr, b: Expr) -> Expr:
    return Div(a, b)


def sq(a: Expr) -> Expr:
    return PowInt(a, 2)


def power(a: Expr, exponent: Fraction) -> Expr:
    """a ** exponent for a > 0: exp(exponent ln a)."""
    return Exp(Mul((c(exponent), Ln(a))))


STRICT = c(INCH / 10**6)
"""A guard that must excuse only on one side of a boundary the code makes strict (J10.2's
"x > d") is shifted by one millionth of an inch toward the excused side: at the boundary
itself the stricter formula applies, as the code says, and within a millionth of an inch
past it too, which only errs safe. Callers add it to a length guard."""

STRICT_RATIO = c(Fraction(1, 10**9))
"""The same shift for a dimensionless guard."""

SIXTEENTH = c(INCH / 16)
"""Section B4.3b: the width of a bolt hole for net area is 1/16 in larger than its nominal
dimension."""


# --- J3: bolts ---------------------------------------------------------------------------

def bolt_area(d: Expr) -> Expr:
    """Ab = pi d^2 / 4, the nominal unthreaded body area (Table J3.2 note)."""
    return Mul((Div(Pi(), c(4)), sq(d)))


def bolt_shear(fnv: Expr, d: Expr, planes: Expr) -> Expr:
    """Eq J3-1: Rn = Fnv Ab per shear plane."""
    return mul(fnv, bolt_area(d), planes)


def bolt_tension(fnt: Expr, d: Expr) -> Expr:
    """Eq J3-1: Rn = Fnt Ab."""
    return mul(fnt, bolt_area(d))


def combined_fnt(fnt: Expr, fnv: Expr, frv: Expr, factor: Expr, lrfd: bool) -> Expr:
    """Eq J3-3a/b: F'nt = 1.3 Fnt - Fnt/(phi Fnv) frv <= Fnt (LRFD), with Omega Fnt/Fnv
    in ASD. `factor` is phi (LRFD) or Omega (ASD)."""
    slope = Div(fnt, mul(factor, fnv)) if lrfd else Div(mul(factor, fnt), fnv)
    return Min((sub(mul(c("1.3"), fnt), mul(slope, frv)), fnt))


def slip(mu: Expr, du: Expr, hf: Expr, tb: Expr, planes: Expr, ksc: Expr) -> Expr:
    """Eq J3-4: Rn = mu Du hf Tb ns ksc, per bolt."""
    return mul(mu, du, hf, tb, planes, ksc)


def slip_ksc(tension_per_bolt: Expr, du: Expr, tb: Expr, factor: Expr | None) -> Expr:
    """Eq J3-5a/b: ksc = 1 - Tu/(Du Tb nb) (LRFD) or 1 - 1.5 Ta/(Du Tb nb) (ASD), here per
    bolt (T/nb is the tension on one bolt); `factor` is 1.5 for ASD, None for LRFD. Not
    less than zero."""
    t = tension_per_bolt if factor is None else mul(factor, tension_per_bolt)
    return Max((sub(c(1), Div(t, mul(du, tb))), c(0)))


def bearing(d: Expr, t: Expr, fu: Expr, coefficient: Fraction) -> Expr:
    """Eq J3-6a/b/c bearing: Rn = 2.4 d t Fu (deformation a design consideration),
    3.0 d t Fu (not), 2.0 d t Fu (long slot perpendicular to the force)."""
    return mul(c(coefficient), d, t, fu)


def tearout(lc: Expr, t: Expr, fu: Expr, coefficient: Fraction) -> Expr:
    """Eq J3-6d/e/f tearout: Rn = 1.2 lc t Fu, 1.5 lc t Fu, or 1.0 lc t Fu, lc the clear
    distance in the direction of the force."""
    return mul(c(coefficient), lc, t, fu)


BEARING = {"considered": (Fraction(12, 5), Fraction(6, 5)), "not_considered": (Fraction(3), Fraction(3, 2)),
           "lsl_perpendicular": (Fraction(2), Fraction(1))}
"""Section J3.11a: (bearing, tearout) coefficients by case."""


def hole_net(dh: Expr) -> Expr:
    """dh + 1/16 in (B4.3b)."""
    return add(dh, SIXTEENTH)


# --- J4: affected elements ------------------------------------------------------------------

def tension_yield(fy: Expr, ag: Expr) -> Expr:
    """Eq J4-1: Rn = Fy Ag."""
    return mul(fy, ag)


def tension_rupture(fu: Expr, ae: Expr) -> Expr:
    """Eq J4-2: Rn = Fu Ae."""
    return mul(fu, ae)


def shear_yield(fy: Expr, agv: Expr) -> Expr:
    """Eq J4-3: Rn = 0.60 Fy Agv."""
    return mul(c("0.6"), fy, agv)


def shear_rupture(fu: Expr, anv: Expr) -> Expr:
    """Eq J4-4: Rn = 0.60 Fu Anv."""
    return mul(c("0.6"), fu, anv)


def block_shear(fy: Expr, fu: Expr, agv: Expr, anv: Expr, ant: Expr, ubs: Fraction) -> Expr:
    """Eq J4-5: Rn = 0.60 Fu Anv + Ubs Fu Ant <= 0.60 Fy Agv + Ubs Fu Ant."""
    tension = mul(c(ubs), fu, ant)
    return Min((add(mul(c("0.6"), fu, anv), tension), add(mul(c("0.6"), fy, agv), tension)))


def compression(fy: Expr, ag: Expr) -> Expr:
    """Eq J4-6: Rn = Fy Ag, valid when Lc/r <= 25 (a validity row)."""
    return mul(fy, ag)


def flexural_yield(fy: Expr, z: Expr) -> Expr:
    """Section J4.5: Mn = Fy Z for a plate."""
    return mul(fy, z)


def flexural_rupture(fu: Expr, znet: Expr) -> Expr:
    """Section J4.5: Mn = Fu Znet."""
    return mul(fu, znet)


def plate_plastic_modulus(t: Expr, depth: Expr) -> Expr:
    """Z = t L^2 / 4 for a rectangular plate bent about its strong axis."""
    return Div(mul(t, sq(depth)), c(4))


def plate_net_modulus(t: Expr, depth: Expr, rows: int, pitch: Expr, hole: Expr) -> Expr:
    """Znet of a plate of depth L with one vertical line of `rows` holes of net width dh'
    at pitch s, centred on mid-depth: t/4 (L^2 - 4 dh' sum |y_i|), where each hole removes
    dh' t at its distance |y_i| from the plastic neutral axis. For a regular pattern
    sum |y_i| = s (rows^2 - (rows mod 2)) / 4."""
    lever = Fraction(rows * rows - rows % 2, 4)   # sum of |y_i| / s over the rows
    return Div(mul(t, sub(sq(depth), mul(c(4), hole, c(lever), pitch))), c(4))


# --- J2: welds ----------------------------------------------------------------------------

def fillet_line(fexx: Expr, w: Expr, length: Expr, transverse: bool) -> Expr:
    """Eq J2-4 with Table J2.5: Rn = 0.60 FEXX (w / sqrt 2) L kds, kds = 1 + 0.5 sin^1.5
    theta: 1.0 for a longitudinal line (theta 0), 1.5 for a transverse one (theta 90)."""
    kds = c("1.5") if transverse else c(1)
    return mul(c("0.6"), fexx, Div(w, Sqrt(c(2))), length, kds)


def fillet_group(longitudinal: Expr, transverse: Expr) -> Expr:
    """Eq J2-6: Rn = max(Rnwl + Rnwt, 0.85 Rnwl + 1.5 Rnwt) for a group of longitudinal and
    transverse lines, with Rnwt taken without its directional increase (kds = 1). Callers
    pass Rnwt at kds 1."""
    return Max((add(longitudinal, transverse), add(mul(c("0.85"), longitudinal), mul(c("1.5"), transverse))))


def fillet_per_length(fexx: Expr, w: Expr) -> Expr:
    """Strength of a longitudinal fillet per unit length: 0.60 FEXX w / sqrt 2."""
    return mul(c("0.6"), fexx, Div(w, Sqrt(c(2))))


def base_metal_per_length(fu: Expr, t: Expr) -> Expr:
    """Section J2.4(a) with J4.2(b): shear rupture of the base metal along the fusion face,
    0.60 Fu t per unit length."""
    return mul(c("0.6"), fu, t)


def min_fillet(t: Expr, t1: Expr, t2: Expr, t3: Expr, w1: Expr, w2: Expr, w3: Expr, w4: Expr) -> tuple[tuple[Expr, Expr | None], ...]:
    """Table J2.4 as guarded rows ((wmin, guard), ...): a row binds unless its guard is
    <= 0. A thinner part t <= t1 needs w1, t1 < t <= t2 needs w2, t2 < t <= t3 needs w3,
    t > t3 needs w4. The sizes increase, so "w >= wmin(t)" is exactly "w >= w1, and
    w >= w_i unless t <= t_(i-1)" for i = 2, 3, 4: each guard is t - t_(i-1), and a
    thickness on a boundary falls in the lower row, as the table says."""
    return ((w1, None), (w2, sub(t, t1)), (w3, sub(t, t2)), (w4, sub(t, t3)))


# --- J7 and J10 -------------------------------------------------------------------------

def bearing_milled(fy: Expr, apb: Expr) -> Expr:
    """Eq J7-1: Rn = 1.8 Fy Apb."""
    return mul(c("1.8"), fy, apb)


def flange_local_bending(fyf: Expr, tf: Expr) -> Expr:
    """Eq J10-1: Rn = 6.25 Fyf tf^2 (halved within 10 tf of the member end)."""
    return mul(c("6.25"), fyf, sq(tf))


def web_local_yielding(fyw: Expr, tw: Expr, k: Expr, lb: Expr, near_end: bool) -> Expr:
    """Eq J10-2: Rn = Fyw tw (5k + lb) away from the end; Eq J10-3: Fyw tw (2.5k + lb)
    within d of the end."""
    return mul(fyw, tw, add(mul(c("2.5" if near_end else 5), k), lb))


def web_crippling(e: Expr, fyw: Expr, tw: Expr, tf: Expr, d: Expr, lb: Expr, case: str) -> Expr:
    """Eqs J10-4, J10-5a, J10-5b with Qf = 1 (a W shape):
    interior:          0.80 tw^2 [1 + 3 (lb/d)(tw/tf)^1.5] sqrt(E Fyw tf / tw)
    end, lb/d <= 0.2:  0.40 tw^2 [1 + 3 (lb/d)(tw/tf)^1.5] sqrt(E Fyw tf / tw)
    end, lb/d >  0.2:  0.40 tw^2 [1 + (4 lb/d - 0.2)(tw/tf)^1.5] sqrt(E Fyw tf / tw)"""
    ratio = Div(tw, tf)
    shape = mul(ratio, Sqrt(ratio))
    x = Div(lb, d)
    lead, inner = {"interior": ("0.8", mul(c(3), x)), "end_short": ("0.4", mul(c(3), x)),
                   "end_long": ("0.4", sub(mul(c(4), x), c("0.2")))}[case]
    return mul(c(lead), sq(tw), add(c(1), mul(inner, shape)), Sqrt(Div(mul(e, fyw, tf), tw)))


def web_sidesway(cr: Expr, tw: Expr, tf: Expr, h: Expr, lb_unbraced: Expr, bf: Expr, restrained: bool) -> tuple[Expr, Expr]:
    """Eqs J10-6 and J10-7: (Rn, r) with r = (h/tw)/(Lb/bf).
    restrained compression flange: Rn = Cr tw^3 tf / h^2 [1 + 0.4 r^3], applies when r <= 2.3
    unrestrained:                   Rn = Cr tw^3 tf / h^2 [0.4 r^3],     applies when r <= 1.7"""
    r = Div(Div(h, tw), Div(lb_unbraced, bf))
    cubic = mul(c("0.4"), PowInt(r, 3))
    lead = Div(mul(cr, PowInt(tw, 3), tf), sq(h))
    return mul(lead, add(c(1), cubic) if restrained else cubic), r


def web_compression_buckling(e: Expr, fyw: Expr, tw: Expr, h: Expr) -> Expr:
    """Eq J10-8: Rn = 24 tw^3 sqrt(E Fyw) / h (halved within d/2 of the end)."""
    return Div(mul(c(24), PowInt(tw, 3), Sqrt(mul(e, fyw))), h)


def panel_zone(fy: Expr, dc: Expr, tw: Expr, pr: Expr, py: Expr, factor: Expr) -> Expr:
    """Eqs J10-9 and J10-10 (frame stability not considered in the analysis):
    Rn = 0.60 Fy dc tw for alpha Pr <= 0.4 Py, and 0.60 Fy dc tw (1.4 - alpha Pr / Py)
    above, which is min(1, 1.4 - alpha Pr / Py) times the first. `factor` is alpha:
    1.0 (LRFD) or 1.6 (ASD)."""
    return mul(c("0.6"), fy, dc, tw, Min((c(1), sub(c("1.4"), Div(mul(factor, pr), py)))))


# --- Manual methods ---------------------------------------------------------------------------

def cope_fcr(e: Expr, nu: Expr, fy: Expr, tw: Expr, ho: Expr, cope_length: Expr, d: Expr) -> Expr:
    """Manual Part 9, flexural local buckling of a beam web coped at the top flange
    (Cheng, Yura and Johnson 1988): Fcr = [pi^2 E / (12 (1 - nu^2))] (tw/ho)^2 f k <= Fy,
    f = 2c/d for c/d <= 1, 1 + c/d above; k = 2.2 (ho/c)^1.65 for c/ho <= 1, 2.2 ho/c
    above. (The Manual's 26,210 ksi is the bracket with E = 29,000 ksi and nu = 0.3.)
    Each branch pair is joined with min or max, which is exact: f = min(2x, 1 + x) with
    x = c/d, because 2x <= 1 + x exactly when x <= 1; k = max(2.2 y^1.65, 2.2 y) with
    y = ho/c, because y^1.65 >= y exactly when y >= 1. Valid for c <= 2d and dc <= d/2
    (validity rows)."""
    plate = Div(mul(sq(Pi()), e), mul(c(12), sub(c(1), sq(nu))))
    x = Div(cope_length, d)
    f = Min((mul(c(2), x), add(c(1), x)))
    y = Div(ho, cope_length)
    k = Max((mul(c("2.2"), power(y, Fraction(33, 20))), mul(c("2.2"), y)))
    return Min((mul(plate, sq(Div(tw, ho)), f, k), fy))


def cope_fcr_both(e: Expr, fy: Expr, tw: Expr, ho: Expr, cope_length: Expr, d: Expr, dct: Expr) -> Expr:
    """Manual Part 9, both flanges coped by dc: Fcr = 0.62 pi E tw^2 fd / (c ho) <= Fy with
    fd = 3.5 - 7.5 dct/d. Valid for dct <= 0.2 d (a validity row)."""
    fd = sub(c("3.5"), mul(c("7.5"), Div(dct, d)))
    return Min((Div(mul(c("0.62"), Pi(), e, sq(tw), fd), mul(cope_length, ho)), fy))


def coped_section_modulus(tw: Expr, ho: Expr) -> Expr:
    """Snet of the remaining web (a rectangle tw by ho, the flange cope removing the
    flange): tw ho^2 / 6. Conservative: the Manual tabulates the tee section's elastic
    modulus, which is larger when the bottom flange remains."""
    return Div(mul(tw, sq(ho)), c(6))


def plate_buckling_q(fy: Expr, t: Expr, ho: Expr, c_len: Expr) -> Expr:
    """Manual Part 9 (Muir and Thornton 2004), plate buckling of an extended single plate
    or a doubly coped web: lambda = ho sqrt(Fy/ksi) / (10 t sqrt(475 + 280 (ho/c)^2));
    Q = 1 for lambda <= 0.7, 1.34 - 0.486 lambda for 0.7 < lambda <= 1.41, 1.30/lambda^2
    above. The three branches meet continuously at 0.7 and 1.41 (within 0.1 %), and Q is
    min(1, 1.34 - 0.486 lambda) on the first two and 1.30/lambda^2 on the last; the
    elaborator guards each branch with its range of lambda. Returns lambda."""
    ratio = Div(ho, c_len)
    return Div(mul(ho, Sqrt(Div(fy, c(KSI)))), mul(c(10), t, Sqrt(add(c(475), mul(c(280), sq(ratio))))))


# --- Groups (elastic method, Manual Part 7) ------------------------------------------------------

def elastic_bolt_force(v: Expr, e: Expr, n: Expr, rows: int, cols: int, s: Expr, g: Expr) -> tuple[Expr, Expr]:
    """(horizontal, vertical) force on the critical corner bolt of a rows x cols pattern
    under a vertical force v at eccentricity e from the pattern's centroid (Manual Part 7,
    elastic method): Ip = n [(rows^2 - 1) s^2 + (cols^2 - 1) g^2] / 12, corner at
    x = (cols - 1) g / 2, y = (rows - 1) s / 2; fx = v e y / Ip, fy = v/n + v e x / Ip."""
    ip = mul(n, Div(add(mul(c(rows * rows - 1), sq(s)), mul(c(cols * cols - 1), sq(g))), c(12)))
    x = mul(c(Fraction(cols - 1, 2)), g)
    y = mul(c(Fraction(rows - 1, 2)), s)
    moment = mul(v, e)
    return Div(mul(moment, y), ip), add(Div(v, n), Div(mul(moment, x), ip))


def elastic_block_force(v: Expr, e: Expr, n: Expr, rows: int, cols: int, s: Expr, g: Expr, k: int, j: int) -> tuple[Expr, Expr]:
    """(horizontal, vertical) resultant, by the same elastic method, of the forces on the
    bolts of a block holding k rows from one end and j columns from one side of the
    pattern. Over those bolts |sum y| = j k (rows - k) s / 2 and |sum x| = k j (cols - j) g / 2,
    so fx = v e |sum y| / Ip and fy = v k j / n + v e |sum x| / Ip, which takes the side on
    which the twist adds to the direct share. A block holding every bolt carries v."""
    ip = mul(n, Div(add(mul(c(rows * rows - 1), sq(s)), mul(c(cols * cols - 1), sq(g))), c(12)))
    moment = mul(v, e)
    sum_y = mul(c(Fraction(j * k * (rows - k), 2)), s)
    sum_x = mul(c(Fraction(k * j * (cols - j), 2)), g)
    return Div(mul(moment, sum_y), ip), add(Div(mul(v, c(k * j)), n), Div(mul(moment, sum_x), ip))


def elastic_weld_line(v: Expr, e: Expr, length: Expr, lines: Expr) -> tuple[Expr, Expr]:
    """(horizontal, vertical) force per unit length at the end of `lines` parallel vertical
    weld lines of `length`, loaded by v at eccentricity e normal to the lines' plane
    (Manual Part 8, elastic method on a line weld): f_v = v / (lines L), f_h = 6 v e /
    (lines L^2)."""
    total = mul(lines, length)
    return Div(mul(c(6), v, e), mul(total, length)), Div(v, total)


# --- Prying (Kulak Chapter 17, Manual Part 9) --------------------------------------------------------

def prying_available(b_tension: Expr, d: Expr, dh: Expr, p: Expr, b: Expr, a: Expr, t: Expr, fu: Expr, phi: Expr) -> Expr:
    """Available tension per bolt including prying, B Q, with the Manual Part 9 form of
    the Struik-de Back model (Kulak Eq 17.11-17.12):
      b' = b - d/2, a' = min(a, 1.25 b) + d/2, rho = b'/a', delta = 1 - dh/p,
      tc = sqrt(4 B b' / (phi p Fu)), alpha' = [(tc/t)^2 - 1] / (delta (1 + rho)),
      Q = (t/tc)^2 (1 + delta alpha') with alpha' clipped to [0, 1], and Q <= 1.
    `phi` is the resistance factor (LRFD) or 1/Omega (ASD); `b_tension` is the bolt's
    available tension B."""
    b1 = sub(b, Div(d, c(2)))
    a1 = add(Min((a, mul(c("1.25"), b))), Div(d, c(2)))
    rho = Div(b1, a1)
    delta = sub(c(1), Div(dh, p))
    tc2 = Div(mul(c(4), b_tension, b1), mul(phi, p, fu))
    ratio = Div(sq(t), tc2)
    alpha = Div(sub(Div(tc2, sq(t)), c(1)), mul(delta, add(c(1), rho)))
    clipped = Min((c(1), Max((c(0), alpha))))
    q = Min((c(1), mul(ratio, add(c(1), mul(delta, clipped)))))
    return mul(b_tension, q)
