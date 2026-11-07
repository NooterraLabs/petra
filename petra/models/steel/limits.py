"""AISC 360-22 Chapter J limit states as kernel expressions. Trusted physics: AISC's
layer over petra/mechanics.

Every function takes kernel Exprs (hypothesis symbols from a StatementBuilder) and returns
the nominal strength Rn, or the quantity a rule compares, as an Expr in SI units. No
function reads a design: the callers in checks.py decide which premise each argument is.
Every number a provision prints (the 0.60 of Fnw = 0.60 FEXX, the 1.61 floor of k1) is a
registry row with its clause and tag (petra/registry/steel.py, docs/principles.md D5), read
through `k`, the caller's constant lookup, so it appears in footprints; each docstring
shows the equation with its printed numbers, to read against the row.

The mechanics under the provisions belongs to no code, and lives in petra/mechanics: the
properties of a section, how a force is shared among bolts or along a weld (the elastic
method of Manual Parts 7 and 8), a plate's elastic buckling stress. This module takes
them from there. Where the Specification names a geometric quantity (Ab, the bolt's body
area; a bracket's a' and b'), a function here says which one it is. So the only literals
here are 0, 1 and 2 (tests/test_steel_principles.py).

A formula that depends on an inch- or ksi-valued quantity in a non-homogeneous way (the
Fy in ksi under a square root) uses the unit as an exact Const, so the expression stays
in SI.

Equation numbers are AISC 360-22's unless marked Manual (AISC Steel Construction Manual,
16th ed., whose methods are encoded here, not its text) or Kulak (Kulak, Fisher and
Struik, Guide to Design Criteria for Bolted and Riveted Joints, 2nd ed., 1987).
"""
from __future__ import annotations

from typing import Callable

from ...kernel import Div, Expr, Ln, Max, Min, PowInt, Sqrt
from ...mechanics import (add, c, circle_area, div, fillet_throat, mul, plate_buckling_stress, power,
                          rectangle_elastic_modulus, rectangle_plastic_modulus, right_triangle, sq, sub)
from ...units import CUSTOMARY

INCH = CUSTOMARY["inch"][0]
KSI = CUSTOMARY["ksi"][0]

K = Callable[[str], Expr]
"""A registry constant by name, as the caller's StatementBuilder states it (Ctx.const)."""


STRICT = "petra.strict.length"
"""A guard that must excuse only on one side of a boundary the code makes strict (J10.2's
"x > d") is shifted by this registry row's length, a millionth of an inch, toward the
excused side: at the boundary itself the stricter formula applies, as the code says, and
within a millionth of an inch past it too, which only errs safe. Callers add it to a
length guard."""

STRICT_RATIO = "petra.strict.ratio"
"""The same shift for a dimensionless guard."""


# --- J3: bolts ---------------------------------------------------------------------------

def bolt_area(d: Expr) -> Expr:
    """Ab, the nominal unthreaded body area (Table J3.2 note): the area of a circle of the
    nominal diameter, pi d^2 / 4."""
    return circle_area(d)


def bolt_shear(fnv: Expr, d: Expr, planes: Expr) -> Expr:
    """Eq J3-1: Rn = Fnv Ab per shear plane."""
    return mul(fnv, bolt_area(d), planes)


def bolt_tension(fnt: Expr, d: Expr) -> Expr:
    """Eq J3-1: Rn = Fnt Ab."""
    return mul(fnt, bolt_area(d))


def combined_fnt(k: K, fnt: Expr, fnv: Expr, frv: Expr, factor: Expr, lrfd: bool) -> Expr:
    """Eq J3-3a/b: F'nt = 1.3 Fnt - Fnt/(phi Fnv) frv <= Fnt (LRFD), with Omega Fnt/Fnv
    in ASD. `factor` is phi (LRFD) or Omega (ASD)."""
    slope = Div(fnt, mul(factor, fnv)) if lrfd else Div(mul(factor, fnt), fnv)
    return Min((sub(mul(k("aisc360.j3_8.intercept"), fnt), mul(slope, frv)), fnt))


def slip(mu: Expr, du: Expr, hf: Expr, tb: Expr, planes: Expr, ksc: Expr) -> Expr:
    """Eq J3-4: Rn = mu Du hf Tb ns ksc, per bolt."""
    return mul(mu, du, hf, tb, planes, ksc)


def slip_ksc(tension_per_bolt: Expr, du: Expr, tb: Expr, factor: Expr | None) -> Expr:
    """Eq J3-5a/b: ksc = 1 - Tu/(Du Tb nb) (LRFD) or 1 - 1.5 Ta/(Du Tb nb) (ASD), here per
    bolt (T/nb is the tension on one bolt); `factor` is 1.5 for ASD, None for LRFD. Not
    less than zero."""
    t = tension_per_bolt if factor is None else mul(factor, tension_per_bolt)
    return Max((sub(c(1), Div(t, mul(du, tb))), c(0)))


def bearing(d: Expr, t: Expr, fu: Expr, coefficient: Expr) -> Expr:
    """Bearing, Eqs J3-6a, J3-6b and J3-6e: Rn = 2.4 d t Fu (deformation a design
    consideration), 3.0 d t Fu (not), 2.0 d t Fu (long slot perpendicular to the force)."""
    return mul(coefficient, d, t, fu)


def tearout(lc: Expr, t: Expr, fu: Expr, coefficient: Expr) -> Expr:
    """Tearout, Eqs J3-6c, J3-6d and J3-6f: Rn = 1.2 lc t Fu, 1.5 lc t Fu, or 1.0 lc t Fu,
    lc the clear distance in the direction of the force."""
    return mul(coefficient, lc, t, fu)


BEARING = {case: (f"aisc360.j3_11a.bearing_{case}", f"aisc360.j3_11a.tearout_{case}")
           for case in ("considered", "not_considered", "lsl_perpendicular")}
"""Section J3.11a: the registry rows of the (bearing, tearout) coefficients by case."""


def hole_net(k: K, dh: Expr) -> Expr:
    """dh + 1/16 in (B4.3b)."""
    return add(dh, k("aisc360.b4_3b.hole_allowance"))


# --- J4: affected elements ------------------------------------------------------------------

def tension_yield(fy: Expr, ag: Expr) -> Expr:
    """Eq J4-1: Rn = Fy Ag."""
    return mul(fy, ag)


def tension_rupture(fu: Expr, ae: Expr) -> Expr:
    """Eq J4-2: Rn = Fu Ae."""
    return mul(fu, ae)


def shear_yield(k: K, fy: Expr, agv: Expr) -> Expr:
    """Eq J4-3: Rn = 0.60 Fy Agv."""
    return mul(k("aisc360.j4_2.shear"), fy, agv)


def shear_rupture(k: K, fu: Expr, anv: Expr) -> Expr:
    """Eq J4-4: Rn = 0.60 Fu Anv."""
    return mul(k("aisc360.j4_2.shear"), fu, anv)


def block_shear(k: K, fy: Expr, fu: Expr, agv: Expr, anv: Expr, ant: Expr, ubs: Expr) -> Expr:
    """Eq J4-5: Rn = 0.60 Fu Anv + Ubs Fu Ant <= 0.60 Fy Agv + Ubs Fu Ant."""
    tension = mul(ubs, fu, ant)
    shear = k("aisc360.j4_3.shear")
    return Min((add(mul(shear, fu, anv), tension), add(mul(shear, fy, agv), tension)))


def compression(fy: Expr, ag: Expr) -> Expr:
    """Eq J4-6: Rn = Fy Ag, J4.4(a) for Lc/r <= 25, which a seat stiffener welded to the
    support along its length meets (vocab.UNBOUNDED)."""
    return mul(fy, ag)


def flexural_yield(fy: Expr, z: Expr) -> Expr:
    """Section J4.5: Mn = Fy Z for a plate."""
    return mul(fy, z)


def flexural_rupture(fu: Expr, znet: Expr) -> Expr:
    """Section J4.5: Mn = Fu Znet."""
    return mul(fu, znet)


# --- J2: welds ----------------------------------------------------------------------------

def fillet_line(k: K, fexx: Expr, w: Expr, length: Expr) -> Expr:
    """Eq J2-4 with Table J2.5 for a longitudinal line: Rn = 0.60 FEXX (w / sqrt 2) L, with
    kds = 1. The directional increase of Eq J2-5 and the group rule of Eq J2-6 are
    permitted, not required, and the deck takes neither (vocab, the weld model)."""
    return mul(k("aisc360.j2_4.fnw"), fexx, fillet_throat(w), length)


def end_loaded_length(k: K, length: Expr, w: Expr) -> Expr:
    """Section J2.2b(d): the effective length of an end-loaded fillet. Up to 100 w it is the
    length; up to 300 w it is beta l with beta = 1.2 - 0.002 l / w (Eq J2-1); beyond, 180 w,
    which is what beta l reaches at 300 w. beta l >= l exactly when l <= 100 w, so the
    effective length is min(l, beta(lc) lc) with lc = min(l, 300 w)."""
    capped = Min((length, mul(k("aisc360.j2_2b.end_loaded_cap"), w)))
    beta = sub(k("aisc360.j2_2b.beta_intercept"), mul(k("aisc360.j2_2b.beta_slope"), div(capped, w)))
    return Min((length, mul(beta, capped)))


def fillet_per_length(k: K, fexx: Expr, w: Expr) -> Expr:
    """Strength of a longitudinal fillet per unit length: 0.60 FEXX w / sqrt 2."""
    return mul(k("aisc360.j2_4.fnw"), fexx, fillet_throat(w))


def base_metal_per_length(k: K, fu: Expr, t: Expr) -> Expr:
    """Section J2.4(a) with J4.2(b): shear rupture of the base metal along the fusion face,
    0.60 Fu t per unit length."""
    return mul(k("aisc360.j4_2.shear"), fu, t)


def min_fillet(t: Expr, t1: Expr, t2: Expr, t3: Expr, w1: Expr, w2: Expr, w3: Expr, w4: Expr) -> tuple[tuple[Expr, Expr | None], ...]:
    """Table J2.4 as guarded rows ((wmin, guard), ...): a row binds unless its guard is
    <= 0. A thinner part t <= t1 needs w1, t1 < t <= t2 needs w2, t2 < t <= t3 needs w3,
    t > t3 needs w4. The sizes increase, so "w >= wmin(t)" is exactly "w >= w1, and
    w >= w_i unless t <= t_(i-1)" for i = 2, 3, 4: each guard is t - t_(i-1), and a
    thickness on a boundary falls in the lower row, as the table says."""
    return ((w1, None), (w2, sub(t, t1)), (w3, sub(t, t2)), (w4, sub(t, t3)))


# --- J7 and J10 -------------------------------------------------------------------------

def bearing_milled(k: K, fy: Expr, apb: Expr) -> Expr:
    """Eq J7-1: Rn = 1.8 Fy Apb."""
    return mul(k("aisc360.j7.milled"), fy, apb)


def flange_local_bending(k: K, fyf: Expr, tf: Expr) -> Expr:
    """Eq J10-1: Rn = 6.25 Fyf tf^2 (halved within 10 tf of the member end)."""
    return mul(k("aisc360.j10_1.coefficient"), fyf, sq(tf))


def web_local_yielding(k: K, fyw: Expr, tw: Expr, kdes: Expr, lb: Expr, near_end: bool) -> Expr:
    """Eq J10-2: Rn = Fyw tw (5k + lb) away from the end; Eq J10-3: Fyw tw (2.5k + lb)
    within d of the end."""
    return mul(fyw, tw, add(mul(k("aisc360.j10_2.end" if near_end else "aisc360.j10_2.interior"), kdes), lb))


def web_crippling(k: K, e: Expr, fyw: Expr, tw: Expr, tf: Expr, d: Expr, lb: Expr, case: str) -> Expr:
    """Eqs J10-4, J10-5a, J10-5b with Qf = 1 (a W shape):
    interior:          0.80 tw^2 [1 + 3 (lb/d)(tw/tf)^1.5] sqrt(E Fyw tf / tw)
    end, lb/d <= 0.2:  0.40 tw^2 [1 + 3 (lb/d)(tw/tf)^1.5] sqrt(E Fyw tf / tw)
    end, lb/d >  0.2:  0.40 tw^2 [1 + (4 lb/d - 0.2)(tw/tf)^1.5] sqrt(E Fyw tf / tw)"""
    ratio = Div(tw, tf)
    shape = mul(ratio, Sqrt(ratio))
    x = Div(lb, d)
    short = mul(k("aisc360.j10_3.bearing"), x)
    long = sub(mul(k("aisc360.j10_3.long_bearing"), x), k("aisc360.j10_3.long_offset"))
    lead, inner = {"interior": ("aisc360.j10_3.interior", short), "end_short": ("aisc360.j10_3.end", short),
                   "end_long": ("aisc360.j10_3.end", long)}[case]
    return mul(k(lead), sq(tw), add(c(1), mul(inner, shape)), Sqrt(Div(mul(e, fyw, tf), tw)))


def web_sidesway(k: K, cr: Expr, tw: Expr, tf: Expr, h: Expr, lb_unbraced: Expr, bf: Expr, restrained: bool) -> tuple[Expr, Expr]:
    """Eqs J10-6 and J10-7: (Rn, r) with r = (h/tw)/(Lb/bf).
    restrained compression flange: Rn = Cr tw^3 tf / h^2 [1 + 0.4 r^3], applies when r <= 2.3
    unrestrained:                   Rn = Cr tw^3 tf / h^2 [0.4 r^3],     applies when r <= 1.7"""
    r = Div(Div(h, tw), Div(lb_unbraced, bf))
    cubic = mul(k("aisc360.j10_4.coefficient"), PowInt(r, 3))
    lead = Div(mul(cr, PowInt(tw, 3), tf), sq(h))
    return mul(lead, add(c(1), cubic) if restrained else cubic), r


def web_compression_buckling(k: K, e: Expr, fyw: Expr, tw: Expr, h: Expr) -> Expr:
    """Eq J10-8: Rn = 24 tw^3 sqrt(E Fyw) / h (halved within d/2 of the end)."""
    return Div(mul(k("aisc360.j10_5.coefficient"), PowInt(tw, 3), Sqrt(mul(e, fyw))), h)


def panel_zone(k: K, fy: Expr, dc: Expr, tw: Expr, pr: Expr, py: Expr, factor: Expr) -> Expr:
    """Eqs J10-9 and J10-10 (frame stability not considered in the analysis):
    Rn = 0.60 Fy dc tw for alpha Pr <= 0.4 Py, and 0.60 Fy dc tw (1.4 - alpha Pr / Py)
    above, which is min(1, 1.4 - alpha Pr / Py) times the first. `factor` is alpha:
    1.0 (LRFD) or 1.6 (ASD)."""
    reduced = sub(k("aisc360.j10_6.intercept"), Div(mul(factor, pr), py))
    return mul(k("aisc360.j10_6.coefficient"), fy, dc, tw, Min((c(1), reduced)))


# --- Manual methods ---------------------------------------------------------------------------

def cope_k1(k: K, hc: Expr, cope_length: Expr, d: Expr) -> Expr:
    """Manual Eqs 9-14, 9-19 and 9-20: k1 = f k >= 1.61, f = 2c/d for c/d <= 1, 1 + c/d
    above; k = 2.2 (hc/c)^1.65 for c/hc <= 1, 2.2 hc/c above. Each branch pair is joined
    with min or max, which is exact: f = min(2x, 1 + x) with x = c/d, because 2x <= 1 + x
    exactly when x <= 1; k = max(2.2 y^1.65, 2.2 y) with y = hc/c, because y^1.65 >= y
    exactly when y >= 1."""
    x = Div(cope_length, d)
    f = Min((mul(c(2), x), add(c(1), x)))
    y = Div(hc, cope_length)
    coefficient = k("aisc_manual.p9.k_coefficient")
    kk = Max((mul(coefficient, power(y, k("aisc_manual.p9.k_exponent"))), mul(coefficient, y)))
    return Max((mul(f, kk), k("aisc_manual.p9.k1_min")))


def cope_lambda_p(k: K, k1: Expr, e: Expr, fy: Expr) -> Expr:
    """Manual Eq 9-18: lambda_p = 0.475 sqrt(k1 E / Fy), against lambda = hc / tw."""
    return mul(k("aisc_manual.p9.lambda_p"), Sqrt(Div(mul(k1, e), fy)))


def cope_inelastic(mp: Expr, my: Expr, lam: Expr, lam_p: Expr) -> Expr:
    """Manual Eqs 9-10 and 9-11, for lambda <= 2 lambda_p: Mn = Mp for lambda <= lambda_p,
    Mp - (Mp - My)(lambda / lambda_p - 1) above. The second is >= Mp exactly when
    lambda <= lambda_p, so Mn = min of the two."""
    return Min((mp, sub(mp, mul(sub(mp, my), sub(Div(lam, lam_p), c(1))))))


def cope_elastic(e: Expr, nu: Expr, k1: Expr, lam: Expr, sc: Expr) -> Expr:
    """For lambda > 2 lambda_p, elastic local buckling of the coped web: Mn = Fcr Sc, Fcr
    the plate buckling stress with the Manual's k1 as its coefficient and lambda = hc / tw
    as its slenderness, pi^2 E k1 / (12 (1 - nu^2) lambda^2). At lambda = 2 lambda_p it is
    (pi^2 / (12 (1 - nu^2) 4 (0.475)^2)) Fy Sc = 1.0006 My, where Eq 9-11 gives My: the
    branches meet."""
    return mul(plate_buckling_stress(e, nu, k1, lam), sc)


def double_cope_cb(k: K, cope_length: Expr, d: Expr, dct: Expr) -> Expr:
    """Manual Eq 9-21, a beam coped at both flanges with equal cope lengths:
    Cb = [3 + ln(Lb / d)] (1 - dct / d) >= 1.84, Lb = c, d the full beam depth."""
    cb = mul(add(k("aisc_manual.p9.cb_intercept"), Ln(Div(cope_length, d))), sub(c(1), Div(dct, d)))
    return Max((cb, k("aisc_manual.p9.cb_min")))


def bar_ltb(k: K, e: Expr, fy: Expr, cb: Expr, lb_unbraced: Expr, depth: Expr, t: Expr) -> tuple[Expr, Expr, Expr]:
    """Section F11 for a rectangular bar `depth` by `t` bent about its major axis, unbraced
    over `lb_unbraced`: (x = Lb d / t^2, Mn by Eq F11-3 for x <= 1.9 E / Fy, Mn by Eq F11-4 above),
    each <= Mp = Fy Z (Eq F11-1, Z = 1.5 Sx). F11-3 is Cb [1.52 - 0.274 x Fy / E] My;
    F11-4 is Fcr Sx with Fcr = 1.9 E Cb / x. Below x = 0.08 E / Fy F11-3 with Cb >= 1 is
    already >= 1.49 My, and yielding (Mp = 1.5 My) governs, as F11.2(a) has it."""
    sx = rectangle_elastic_modulus(t, depth)
    my, mp = mul(fy, sx), mul(fy, rectangle_plastic_modulus(t, depth))
    x = Div(mul(lb_unbraced, depth), sq(t))
    f11_3 = mul(cb, sub(k("aisc360.f11.inelastic_intercept"), mul(k("aisc360.f11.inelastic_slope"), x, Div(fy, e))), my)
    f11_4 = mul(Div(mul(k("aisc360.f11.elastic"), e, cb), x), sx)
    return x, Min((mp, f11_3)), Min((mp, f11_4))


# --- Seat welds (Manual Part 10) ------------------------------------------------------------------

def seat_weld_line(k: K, v: Expr, e: Expr, length: Expr) -> tuple[Expr, Expr]:
    """(horizontal, vertical) force per unit length at the top of the two vertical weld
    lines of a seat angle, loaded by v at e from the support face, with the angle's
    vertical leg bearing on the support below the welds' neutral axis (Manual Part 10,
    the elastic method behind Table 10-6): R = v / (2 L^2) sqrt(L^2 + 20.25 e^2), so
    f_h = 2.25 v e / L^2 and f_v = v / (2 L)."""
    return Div(mul(k("aisc_manual.t10_6.lever"), v, e), sq(length)), Div(v, mul(c(2), length))


# --- Bracket plates (Manual Part 15) ------------------------------------------------------------------

def bracket_section(a: Expr, b: Expr) -> tuple[Expr, Expr, Expr, Expr]:
    """(sin theta, cos theta, a', b') of a shaped bracket plate (Manual Fig. 15-2): a is
    its depth at the support (section A-A), b the projection of its sloped free edge, so
    the plate is the right triangle with legs a and b. The free-edge section B-B runs
    normal to that edge: theta = atan(b/a), a' = a / cos theta (Manual Eq 15-17) is the
    hypotenuse, and b' = a sin theta its distance from the right angle."""
    return right_triangle(a, b)


def bracket_lambda(k: K, a1: Expr, b1: Expr, t: Expr, fy: Expr) -> Expr:
    """Slenderness of the free edge (Manual Eq 15-18), Fy in ksi:
    lambda = (b'/t) sqrt(Fy) / (5 sqrt(475 + 1120 (b'/a')^2))."""
    root = Sqrt(add(k("aisc_manual.p15.lambda_intercept"), mul(k("aisc_manual.p15.lambda_slope"), sq(Div(b1, a1)))))
    return Div(mul(Div(b1, t), Sqrt(Div(fy, c(KSI)))), mul(k("aisc_manual.p15.lambda_coefficient"), root))


def bracket_q_stocky(k: K, lam: Expr) -> Expr:
    """Reduction Q for lambda <= 1.41 (Manual Eqs 15-13 to 15-15): 1 up to 0.70, then
    1.34 - 0.486 lambda. The least of the two is exact on [0, 1.41] but at lambda = 0.70,
    where it is 0.9998 rather than 1."""
    return Min((c(1), sub(k("aisc_manual.p15.q_intercept"), mul(k("aisc_manual.p15.q_slope"), lam))))


def bracket_q_slender(k: K, lam: Expr) -> Expr:
    """Reduction Q for lambda > 1.41 (Manual Eq 15-16): 1.30 / lambda^2."""
    return Div(k("aisc_manual.p15.q_slender"), sq(lam))


# --- Prying (Kulak Chapter 17, Manual Part 9) --------------------------------------------------------

def prying_available(k: K, b_tension: Expr, d: Expr, dh: Expr, p: Expr, b: Expr, a: Expr, t: Expr, fu: Expr, phi: Expr) -> Expr:
    """Available tension per bolt including prying, B Q, with the Manual Part 9 form of
    the Struik-de Back model (Kulak Eq 17.11-17.12):
      b' = b - d/2, a' = min(a, 1.25 b) + d/2, rho = b'/a', delta = 1 - dh/p,
      tc = sqrt(4 B b' / (phi p Fu)), alpha' = [(tc/t)^2 - 1] / (delta (1 + rho)),
      Q = (t/tc)^2 (1 + delta alpha') with alpha' clipped to [0, 1], and Q <= 1.
    `phi` is the resistance factor (LRFD) or 1/Omega (ASD); `b_tension` is the bolt's
    available tension B.

    With K = phi p Fu t^2 / (4 b'), the B at which tc = t, (tc/t)^2 = B / K, and the three
    branches of B Q are B (alpha' <= 0, Q = 1), K + (B - K) / (1 + rho) (0 < alpha' < 1,
    where delta cancels) and K (1 + delta) (alpha' >= 1). Each branch lies at or below the
    others exactly where it applies, so B Q is their least: the same function, written with
    B once in each branch, so its enclosure stays exact when B ranges over an interval (B
    reduced for shear by Eq J3-3)."""
    b1 = sub(b, Div(d, c(2)))
    a1 = add(Min((a, mul(k("aisc_manual.p9.a_limit"), b))), Div(d, c(2)))
    rho = Div(b1, a1)
    delta = sub(c(1), Div(dh, p))
    no_prying = Div(mul(phi, p, fu, sq(t)), mul(k("aisc_manual.p9.tc"), b1))
    partial = Div(add(mul(no_prying, rho), b_tension), add(c(1), rho))
    return Min((b_tension, partial, mul(no_prying, add(c(1), delta))))


# --- Shear tee rotational ductility (Manual Part 9) ---------------------------------------------------

def tee_flexibility(k: K, b: Expr, length: Expr) -> Expr:
    """The term (b^2 / l^2 + 2) of Manual Eqs 9-51 and 9-52: b the tee flange's flexible
    width (Figure 9-6), l the tee's length."""
    return add(Div(sq(b), sq(length)), k("aisc_manual.p9.tee_flexibility"))


def tee_weld_min(k: K, fy: Expr, tf: Expr, b: Expr, length: Expr, ts: Expr) -> Expr:
    """The least fillet that lets a tee welded to its support rotate (Manual Eq 9-51), Fy
    in ksi and lengths in inches: wmin = 0.0155 (Fy tf^2 / b)(b^2 / l^2 + 2) <= (5/8) ts.
    The first term is homogeneous in length once Fy is in ksi."""
    first = mul(k("aisc_manual.p9.tee_weld_coefficient"), Div(fy, c(KSI)), Div(sq(tf), b), tee_flexibility(k, b, length))
    return Min((first, mul(k("aisc_manual.p9.tee_weld_cap"), ts)))


def tee_bolt_min(k: K, fy: Expr, tf: Expr, p: Expr, b: Expr, length: Expr, ts: Expr) -> Expr:
    """The least bolt diameter that lets a tee bolted to its support rotate (Manual Eq
    9-52), Fy in ksi and lengths in inches: dmin = 0.0941 tf sqrt((Fy p / b)(b^2 / l^2 + 2))
    <= 0.115 sqrt(Fy ts), p the flange length each bolt acts on (Figure 9-4). The cap is
    in inches with ts in inches."""
    ksi = Div(fy, c(KSI))
    first = mul(k("aisc_manual.p9.tee_bolt_coefficient"), tf, Sqrt(mul(ksi, Div(p, b), tee_flexibility(k, b, length))))
    cap = mul(k("aisc_manual.p9.tee_bolt_cap"), Sqrt(mul(ksi, Div(ts, c(INCH)))), c(INCH))
    return Min((first, cap))
