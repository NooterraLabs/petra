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


def directional_kds(sin_theta: Expr) -> Expr:
    """Eq J2-5: kds = 1.0 + 0.50 sin^1.5 theta, theta the load's angle to the weld axis."""
    return add(c(1), mul(c("0.5"), sin_theta, Sqrt(sin_theta)))


def end_loaded_length(length: Expr, w: Expr) -> Expr:
    """Section J2.2b(d): the effective length of an end-loaded fillet. Up to 100 w it is the
    length; up to 300 w it is beta l with beta = 1.2 - 0.002 l / w (Eq J2-1); beyond, 180 w.
    beta l = 1.2 l - 0.002 l^2 / w = 180 w - 0.002 (l - 300 w)^2 / w, which peaks at 180 w
    at l = 300 w and exceeds l below 100 w, so the effective length is
    min(l, 180 w - 0.002 (min(l, 300 w) - 300 w)^2 / w)."""
    cap = mul(c(300), w)
    curve = sub(mul(c(180), w), div(mul(c("0.002"), sq(sub(Min((length, cap)), cap))), w))
    return Min((length, curve))


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

def tee_moduli(hc: Expr, tw: Expr, bf: Expr, tf: Expr) -> tuple[Expr, Expr]:
    """(Sc, Zc) of the tee a top cope leaves: the web, tw thick, and the bottom flange,
    bf by tf, hc deep in all, fillets neglected (the section Manual Tables 9-2a and 9-2b
    tabulate). Sc is the elastic modulus to the cope edge, the tee's far fibre.

    The plastic neutral axis lies at y = max(A / (2 bf), tf + (A/2 - Af) / tw) above the
    flange's outer face: the first is right when the flange holds half the area, the
    second when it does not, and in each case it is the larger, because bf > tw. With
    m = min(y, tf) and n = max(y, tf), Zc = bf (m^2 + (tf - m)^2) / 2 + bf tf max(0, y - tf)
    + tw ((n - tf)^2 + (hc - n)^2) / 2 + tw (hc - tf) max(0, tf - y), which is the first
    moment of area about y in either case."""
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


def cope_k1(hc: Expr, cope_length: Expr, d: Expr) -> Expr:
    """Manual Eqs 9-14, 9-19 and 9-20: k1 = f k >= 1.61, f = 2c/d for c/d <= 1, 1 + c/d
    above; k = 2.2 (hc/c)^1.65 for c/hc <= 1, 2.2 hc/c above. Each branch pair is joined
    with min or max, which is exact: f = min(2x, 1 + x) with x = c/d, because 2x <= 1 + x
    exactly when x <= 1; k = max(2.2 y^1.65, 2.2 y) with y = hc/c, because y^1.65 >= y
    exactly when y >= 1."""
    x = Div(cope_length, d)
    f = Min((mul(c(2), x), add(c(1), x)))
    y = Div(hc, cope_length)
    k = Max((mul(c("2.2"), power(y, Fraction(33, 20))), mul(c("2.2"), y)))
    return Max((mul(f, k), c("1.61")))


def cope_lambda_p(k1: Expr, e: Expr, fy: Expr) -> Expr:
    """Manual Eq 9-18: lambda_p = 0.475 sqrt(k1 E / Fy), against lambda = hc / tw."""
    return mul(c("0.475"), Sqrt(Div(mul(k1, e), fy)))


def cope_inelastic(mp: Expr, my: Expr, lam: Expr, lam_p: Expr) -> Expr:
    """Manual Eqs 9-10 and 9-11, for lambda <= 2 lambda_p: Mn = Mp for lambda <= lambda_p,
    Mp - (Mp - My)(lambda / lambda_p - 1) above. The second is >= Mp exactly when
    lambda <= lambda_p, so Mn = min of the two."""
    return Min((mp, sub(mp, mul(sub(mp, my), sub(Div(lam, lam_p), c(1))))))


def cope_elastic(e: Expr, nu: Expr, k1: Expr, lam: Expr, sc: Expr) -> Expr:
    """For lambda > 2 lambda_p, elastic local buckling of the coped web:
    Mn = Fcr Sc, Fcr = pi^2 E k1 / (12 (1 - nu^2) lambda^2). At lambda = 2 lambda_p it is
    (pi^2 / (12 (1 - nu^2) 4 (0.475)^2)) Fy Sc = 1.0006 My, where Eq 9-11 gives My: the
    branches meet."""
    return Div(mul(sq(Pi()), e, k1, sc), mul(c(12), sub(c(1), sq(nu)), sq(lam)))


def double_cope_cb(cope_length: Expr, d: Expr, dct: Expr) -> Expr:
    """Manual Eq 9-21, a beam coped at both flanges with equal cope lengths:
    Cb = [3 + ln(Lb / d)] (1 - dct / d) >= 1.84, Lb = c, d the full beam depth."""
    return Max((mul(add(c(3), Ln(Div(cope_length, d))), sub(c(1), Div(dct, d))), c("1.84")))


def bar_ltb(e: Expr, fy: Expr, cb: Expr, lb: Expr, depth: Expr, t: Expr) -> tuple[Expr, Expr, Expr]:
    """Section F11 for a rectangular bar `depth` by `t` bent about its major axis, unbraced
    over `lb`: (x = Lb d / t^2, Mn by Eq F11-3 for x <= 1.9 E / Fy, Mn by Eq F11-4 above),
    each <= Mp = Fy Z (Eq F11-1, Z = 1.5 Sx). F11-3 is Cb [1.52 - 0.274 x Fy / E] My;
    F11-4 is Fcr Sx with Fcr = 1.9 E Cb / x. Below x = 0.08 E / Fy F11-3 with Cb >= 1 is
    already >= 1.49 My, and yielding (Mp = 1.5 My) governs, as F11.2(a) has it."""
    sx = Div(mul(t, sq(depth)), c(6))
    my, mp = mul(fy, sx), mul(c("1.5"), fy, sx)
    x = Div(mul(lb, depth), sq(t))
    f11_3 = mul(cb, sub(c("1.52"), mul(c("0.274"), x, Div(fy, e))), my)
    f11_4 = mul(Div(mul(c("1.9"), e, cb), x), sx)
    return x, Min((mp, f11_3)), Min((mp, f11_4))


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


def elastic_weld_c(v: Expr, e: Expr, length: Expr, ret: Expr) -> tuple[Expr, Expr, Expr]:
    """(horizontal, vertical at the return tips, vertical at the heel corners) force per
    unit length on a C-shaped weld, by the elastic method (Manual Part 8, the line
    properties of Manual Fig. 8-7): a
    vertical line of `length` and two returns of `ret` at its ends running toward the load,
    loaded by v at e from the vertical line. With ltot = L + 2 kl the centroid lies
    xbar = kl^2 / ltot from the vertical line, ex = e - xbar,
      Ix = L^3/12 + kl L^2 / 2,   Iy = 2 [kl^3/12 + kl (kl/2 - xbar)^2] + L xbar^2,
    at the return tips (kl - xbar, +-L/2) and the heel corners (-xbar, +-L/2):
      f_h = v ex (L/2) / Ip,   f_v = v / ltot + v ex x / Ip.
    The force varies linearly along each segment, so its magnitude peaks at a segment's
    end: one of these points, whichever side of the centroid the load lies."""
    total = add(length, mul(c(2), ret))
    xbar = Div(sq(ret), total)
    ix = add(Div(PowInt(length, 3), c(12)), Div(mul(ret, sq(length)), c(2)))
    iy = add(mul(c(2), add(Div(PowInt(ret, 3), c(12)), mul(ret, sq(sub(Div(ret, c(2)), xbar))))), mul(length, sq(xbar)))
    ip = add(ix, iy)
    moment = mul(v, sub(e, xbar))
    direct = Div(v, total)
    return (Div(mul(moment, Div(length, c(2))), ip), add(direct, Div(mul(moment, sub(ret, xbar)), ip)),
            sub(direct, Div(mul(moment, xbar), ip)))


def seat_weld_line(v: Expr, e: Expr, length: Expr) -> tuple[Expr, Expr]:
    """(horizontal, vertical) force per unit length at the top of the two vertical weld
    lines of a seat angle, loaded by v at e from the support face, with the angle's
    vertical leg bearing on the support below the welds' neutral axis (Manual Part 10,
    the elastic method behind Table 10-6): R = v / (2 L^2) sqrt(L^2 + 20.25 e^2), so
    f_h = 2.25 v e / L^2 and f_v = v / (2 L)."""
    return Div(mul(c("2.25"), v, e), sq(length)), Div(v, mul(c(2), length))


# --- Bracket plates (Manual Part 15) ------------------------------------------------------------------

def bracket_section(a: Expr, b: Expr) -> tuple[Expr, Expr, Expr, Expr]:
    """(sin theta, cos theta, a', b') of a shaped bracket plate (Manual Fig. 15-2): a is
    its depth at the support (section A-A), b the projection of its sloped free edge. The
    free-edge section B-B runs normal to that edge: theta = atan(b/a), a' = a / cos theta
    (Manual Eq 15-17), b' = a sin theta."""
    hyp = Sqrt(add(sq(a), sq(b)))
    sin, cos = Div(b, hyp), Div(a, hyp)
    return sin, cos, hyp, Div(mul(a, b), hyp)


def bracket_lambda(a1: Expr, b1: Expr, t: Expr, fy: Expr) -> Expr:
    """Slenderness of the free edge (Manual Eq 15-18), Fy in ksi:
    lambda = (b'/t) sqrt(Fy) / (5 sqrt(475 + 1120 (b'/a')^2))."""
    return Div(mul(Div(b1, t), Sqrt(Div(fy, c(KSI)))), mul(c(5), Sqrt(add(c(475), mul(c(1120), sq(Div(b1, a1)))))))


def bracket_q_stocky(lam: Expr) -> Expr:
    """Reduction Q for lambda <= 1.41 (Manual Eqs 15-13 to 15-15): 1 up to 0.70, then
    1.34 - 0.486 lambda. The least of the two is exact on [0, 1.41] but at lambda = 0.70,
    where it is 0.9998 rather than 1."""
    return Min((c(1), sub(c("1.34"), mul(c("0.486"), lam))))


def bracket_q_slender(lam: Expr) -> Expr:
    """Reduction Q for lambda > 1.41 (Manual Eq 15-16): 1.30 / lambda^2."""
    return Div(c("1.30"), sq(lam))


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
