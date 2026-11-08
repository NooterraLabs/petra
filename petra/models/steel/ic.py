"""Where an eccentric group's instantaneous centre lies, found in floating point. Untrusted
search: nothing here can make a check pass that should fail.

checks.py holds an eccentric bolt group to Manual Part 7's instantaneous centre method by
a certificate. For a centre r from the centroid, the bolts hold V(r) along the load and
M(r) about the centre (mechanics.instantaneous_centre). Along the axis across the load, a
centre nearer the centroid balances a larger eccentricity and holds less: e(r) = M/V - r
falls and V(r) rises as r grows (the premise, which tests/test_steel_groups.py measures).
So where M(r) >= V(r) (e + r), the centre that balances e lies at r or beyond, and the
group holds at least V(r). The certificate is min(V(r), (M(r) - V(r) (e + r)) / ell) for a
positive length ell: V(r) where r is short of the balancing centre, and at most zero where
it is not. It holds for every r > 0, so the search below can only cost strength.

`bolt_centres` picks r just short of the balancing centre at the corners of the box over
the symbols the pattern and the eccentricity read, one for each pattern of pitch and
gauge: checks.py states a certificate at each and takes the largest, so each pattern
keeps its own C (one r for the whole box, the nearest, gave up 2.4 % at the wide-gauge
corners of a bracket whose gauge and eccentricity were toleranced). It gives none where
no certificate can be stated: an eccentricity that is not positive over the box, or a
corner with no balancing centre, and it drops a centre that could fall on a bolt of a
middle row, where the bolt's direction is undefined.

A weld line loaded out of its plane (Manual Part 8, Table 8-4 with k = 0) takes the same
argument on a line of unit length, a = e / L, with V(r) and M(r) - V(r) (a + r) bounded
below over segments of the line (mechanics.line_ic, limits.ic_weld_bounds). `weld_centre`
picks r and the segments: it solves the method in floating point, cuts the half line so
the segments' bounds give up little, and walks r back until the bounds' gap is positive.
"""
from __future__ import annotations

import functools
import itertools
import math
from fractions import Fraction
from typing import Mapping

import numpy as np
from scipy.optimize import brentq

from ...kernel import Expr, Interval, enclose, free_syms
from ...mechanics import add, c, mul
from ...registry import Registry
from ...units import CUSTOMARY

INCH = float(CUSTOMARY["inch"][0])

SHORT = 1e-3
"""How far short of the balancing centre, relative to its distance, the certificate's
centre is placed where the pattern's lengths are ranged: the strength it gives up, against
room for the kernel's intervals over the box."""
SHORT_POINT = 1e-9
"""The same where they are fixed. The kernel encloses a point to 2^-96, so the certificate
loses about a billionth of the method's C, and the twin's float solution agrees with it."""
PATTERN_LEVELS = (Fraction(-1), Fraction(-1, 3), Fraction(1, 3), Fraction(1))
"""Where in a ranged pitch's or gauge's range bolt_centres states a centre, when it is the
pattern's only ranged length. Between two of them the certificate at the lower one's
centre gives up strength as the pattern widens: with the ends alone, 2.4 % below the
method's C just short of the far end, on a bracket of two columns of four 7/8 in bolts at
e = 8 in whose gauge was 3 +- 1/16 in."""
GRID = 10 ** 12
"""The centre's distance is rounded down to this many parts of a metre."""
MAX_CORNERS = 64
"""The most box corners sampled; past them, the corners of the six widest symbols."""


def _ranged(exprs: tuple[Expr, ...], box: Mapping[str, Interval]) -> tuple[list[str], list[str]]:
    """(every symbol the expressions read, the widest ranged ones, at most six)."""
    names = sorted(set().union(*(free_syms(x) for x in exprs)))
    ranged = sorted((n for n in names if box[n].lo != box[n].hi), key=lambda n: box[n].lo - box[n].hi)
    return names, ranged[: int(math.log2(MAX_CORNERS))]


def _points(exprs: tuple[Expr, ...], box: Mapping[str, Interval],
            levels: Mapping[str, tuple[Fraction, ...]]) -> list[tuple[tuple[float, ...], tuple[float, ...]]]:
    """At each corner of the box over the ranged symbols, a symbol named in `levels` also
    at the places it lists, and at the box's centre: (where the point lies in each ranged
    symbol's range, from -1 to 1; each expression's value)."""
    names, ranged = _ranged(exprs, box)
    out = []
    grid = [levels.get(n, (Fraction(-1), Fraction(1))) for n in ranged]
    for ends in [*itertools.product(*grid), (0,) * len(ranged)]:
        point = {n: (box[n].lo + box[n].hi) / 2 for n in names}
        for n, k in zip(ranged, ends):
            point[n] += k * (box[n].hi - box[n].lo) / 2
        at = {n: Interval(v, v) for n, v in point.items()}
        out.append((tuple(float(k) for k in ends), tuple(float(enclose(x, at).lo) for x in exprs)))
    return out


def _pattern(rows: int, cols: int, s: float, g: float) -> tuple[np.ndarray, np.ndarray]:
    xs = (np.arange(cols) - (cols - 1) / 2) * g
    ys = (np.arange(rows) - (rows - 1) / 2) * s
    x, y = np.meshgrid(xs, ys)
    return x.ravel(), y.ravel()


def _sums(r: float, x: np.ndarray, y: np.ndarray, exponent: float, power: float) -> tuple[float, float]:
    rho = np.hypot(x + r, y)
    force = (1 - np.exp(-exponent * rho / rho.max())) ** power
    along = np.divide(x + r, rho, out=np.zeros_like(rho), where=rho > 0)
    return float(np.sum(force * along)), float(np.sum(force * rho))


def _balancing(e: float, x: np.ndarray, y: np.ndarray, exponent: float, power: float) -> float | None:
    """The centre's distance r at which the bolts balance a load at eccentricity e."""
    scale = float(max(np.abs(x).max(), np.abs(y).max(), e))

    def gap(r: float) -> float:
        v, m = _sums(r, x, y, exponent, power)
        return m - v * (e + r)

    lo, hi = scale * 1e-9, scale * 1e9
    if not gap(lo) > 0 > gap(hi):
        return None
    return brentq(gap, lo, hi, xtol=scale * 1e-13, rtol=1e-13, maxiter=500)


def curve(registry: Registry) -> tuple[float, float]:
    """The bolt curve's exponent mu Delta_max (per unit of q = rho / rho_max) and its power,
    from the rows limits.ic_bolt_curve reads."""
    def value(name: str) -> float:
        return float(registry.constants[name].value.lo)
    return (value("aisc_manual.p7.ic_mu") * value("aisc_manual.p7.ic_delta_max") / INCH,
            value("aisc_manual.p7.ic_lambda"))


def bolt_centres(registry: Registry, rows: int, cols: int, s: Expr, g: Expr, e: Expr,
                 box: Mapping[str, Interval]) -> tuple[Expr, ...]:
    """The certificates' centre distances r in metres, constants, nearest first: SHORT
    short of the balancing centre at the box's corners, the nearest for each pattern of
    pitch and gauge they give (the point itself where nothing is ranged). A centre that
    moved with the box's lengths would also be sound at every point, but it ties V and M
    to those symbols twice over, and the kernel's intervals grow loose enough to lose more
    than the constants give up (measured on a toleranced bracket: 28 s and the elastic
    strength)."""
    exponent, power = curve(registry)
    ranged = _ranged((s, g, e), box)[1]
    short = SHORT if ranged else SHORT_POINT
    pattern = [n for n in ranged if n in free_syms(s) | free_syms(g)]
    # V(r) reads the pattern alone, and a larger e balances nearer the centroid, so one
    # centre per pattern, the nearest of its corners', serves every e the box gives it
    nearest: dict[tuple[float, float], float] = {}
    for ends, (sv, gv, ev) in _points((s, g, e), box, {pattern[0]: PATTERN_LEVELS} if len(pattern) == 1 else {}):
        if not ev > 0:
            return ()
        if ranged and 0 in ends:
            continue
        x, y = _pattern(rows, cols, sv, gv)
        found = _balancing(ev, x, y, exponent, power)
        if found is None:
            return ()
        nearest[(sv, gv)] = min(found, nearest.get((sv, gv), found))
    targets = {Fraction(math.floor(r * (1 - short) * GRID), GRID) for r in nearest.values()}
    out = []
    for r in sorted(t for t in targets if t > 0):
        # a middle-row bolt at x = (j - (cols - 1)/2) g must stay clear of the centre at -r
        arms = [enclose(add(mul(c(Fraction(2 * j - cols + 1, 2)), g), c(r)), box) for j in range(cols)] \
            if rows % 2 and cols > 1 else []
        if not any(arm.lo <= 0 <= arm.hi or min(abs(arm.lo), abs(arm.hi)) < r / 1000 for arm in arms):
            out.append(c(r))
    return tuple(out)


def bolt_centre(registry: Registry, rows: int, cols: int, s: Expr, g: Expr, e: Expr,
                box: Mapping[str, Interval]) -> Expr | None:
    """The nearest of bolt_centres, or None where there is none."""
    found = bolt_centres(registry, rows, cols, s, g, e, box)
    return found[0] if found else None


# --- Weld lines ------------------------------------------------------------------------------------------

WELD_ROWS = ("aisc360.j2_4.kds", "aisc360.j2_4.kds_power", "aisc_manual.p8.ic_delta_m", "aisc_manual.p8.ic_delta_m_offset",
             "aisc_manual.p8.ic_delta_m_power", "aisc_manual.p8.ic_delta_u", "aisc_manual.p8.ic_delta_u_offset",
             "aisc_manual.p8.ic_delta_u_power", "aisc_manual.p8.ic_delta_u_cap", "aisc_manual.p8.ic_curve_a",
             "aisc_manual.p8.ic_curve_b", "aisc_manual.p8.ic_curve_power")
"""The rows limits.ic_weld_bounds reads, in the order weld_curve gives them."""
WELD_LOSS = 0.01
"""The share of the method's C the segments may give up before the search cuts finer."""
WELD_SEGMENTS = (32, 48, 64, 96, 128)
"""The segment counts tried, fewest first: the kernel's work grows with them."""
WELD_FLOOR = 0.02
"""Part of the segments spread evenly along the line, the rest where the bounds lose most."""
WELD_SHORT = 1e-7
"""How far below the bounds' balancing centre, relative to its distance, r is placed: room
for the kernel's rounding of the bounds, which is far smaller."""
WELD_DENOMINATOR = 1 << 40
"""Segment ends are rounded to this many parts of the line's length."""


RATIO_ROOM = Fraction(1, 10 ** 9)
"""How far above the box's largest e / L the certificate's ratio is stated, relative to it,
so its switch on e <= a L passes by far more than ell."""


def weld_ratio(ratio: Interval, least: Fraction) -> Fraction | None:
    """The ratio a = e / L a weld line's certificate is stated at: just above the box's
    largest, on the GRID; None where the box reaches down to least."""
    if not ratio.lo > least * (1 + RATIO_ROOM):
        return None
    return Fraction(math.ceil(ratio.hi * (1 + RATIO_ROOM) * GRID), GRID)


def weld_curve(registry: Registry) -> tuple[float, ...]:
    return tuple(float(registry.constants[name].value.lo) for name in WELD_ROWS)


def _weld_element(z: np.ndarray, r: float, curve: tuple[float, ...]) -> tuple[np.ndarray, np.ndarray]:
    """(kds, p) of the elements at z on the half line, the end at z = 1/2."""
    kds, kpow, m0, moff, mpow, u0, uoff, upow, ucap, _, _, _ = curve
    rho = np.hypot(z, r)
    theta = np.degrees(np.arctan2(z, r))
    end = math.degrees(math.atan2(0.5, r))
    du = min(u0 * (end + uoff) ** -upow, ucap)
    p = rho / math.hypot(0.5, r) * du / (m0 * (theta + moff) ** -mpow)
    return 1 + kds * (z / rho) ** kpow, p


def _weld_f(p: np.ndarray, curve: tuple[float, ...]) -> np.ndarray:
    a, b, power = curve[9:]
    return (p * (a - b * p)) ** power


def _weld_force(z: np.ndarray, r: float, curve: tuple[float, ...]) -> np.ndarray:
    kds, p = _weld_element(z, r, curve)
    return kds * _weld_f(p, curve)


NODES, WEIGHTS = np.polynomial.legendre.leggauss(20)


def weld_sums(r: float, curve: tuple[float, ...]) -> tuple[float, float]:
    """(V, M) of the method on a line of unit length, by Gauss-Legendre quadrature over
    pieces that grade toward the midpoint, where the elements turn fastest."""
    cuts = sorted({0.0, 0.5, *(x for x in r * 2.0 ** np.arange(-8, 12) if x < 0.5)})
    v = m = 0.0
    for lo, hi in zip(cuts, cuts[1:]):
        z = (hi - lo) / 2 * NODES + (hi + lo) / 2
        w = WEIGHTS * (hi - lo) / 2
        f = _weld_force(z, r, curve)
        rho = np.hypot(z, r)
        v += float(np.sum(w * f * r / rho))
        m += float(np.sum(w * f * rho))
    return 2 * v, 2 * m


def weld_balancing(a: float, curve: tuple[float, ...]) -> float | None:
    """The centre's distance r, over the line's length, that balances a load at a = e / L."""
    def gap(r: float) -> float:
        v, m = weld_sums(r, curve)
        return m - v * (a + r)

    lo, hi = 1e-9, 1e3
    if not gap(lo) > 0 > gap(hi):
        return None
    return brentq(gap, lo, hi, xtol=1e-15, rtol=1e-13, maxiter=500)


def _segment(za: float, zb: float, r: float) -> tuple[float, float]:
    """(int r / rho, int rho) over [za, zb]."""
    def ends(z: float) -> tuple[float, float]:
        ash = math.asinh(z / r)
        return r * ash, (z * math.hypot(z, r) + r * r * ash) / 2
    (v0, m0), (v1, m1) = ends(za), ends(zb)
    return v1 - v0, m1 - m0


def weld_bounds(r: float, a: float, zs: np.ndarray, curve: tuple[float, ...]) -> tuple[float, float]:
    """The floating-point value of the kernel's (V_lo, gap_lo) for these segments, which
    mechanics.line_ic and limits.ic_weld_bounds state exactly."""
    kds, p = _weld_element(zs, r, curve)
    f = _weld_f(p, curve)
    peak = curve[9] / (2 * curve[10])
    z0 = math.sqrt(a * r)
    v = g = 0.0
    for k in range(len(zs) - 1):
        lo = kds[k] * min(f[k], f[k + 1])
        hi = kds[k + 1] * float(_weld_f(np.array([max(p[k], min(p[k + 1], peak))]), curve)[0])
        iv, _ = _segment(zs[k], zs[k + 1], r)
        v += lo * iv
        pieces = [(zs[k], z0), (z0, zs[k + 1])] if zs[k] < z0 < zs[k + 1] else [(zs[k], zs[k + 1])]
        for za, zb in pieces:
            pv, pm = _segment(za, zb, r)
            weight = pm - (a + r) * pv
            g += min(lo * weight, hi * weight)
    return 2 * v, 2 * g


def weld_grid(r: float, a: float, n: int, curve: tuple[float, ...]) -> np.ndarray:
    """n segments over the half line, denser where the element's force changes fastest
    and the bounds' weights are largest: density sqrt(|F'| w), which minimises the first
    order loss of bounds taken at the segments' ends."""
    z = np.linspace(0.0, 0.5, 20001)
    slope = np.abs(np.gradient(_weld_force(z, r, curve), z))
    rho = np.hypot(z, r)
    weight = r / rho + np.abs(z * z - a * r) / (rho * (a + r))
    density = np.sqrt(slope * weight)
    density += WELD_FLOOR * density.mean()
    total = np.concatenate([[0.0], np.cumsum((density[1:] + density[:-1]) / 2 * np.diff(z))])
    return np.interp(np.linspace(0.0, total[-1], n + 1), total, z)


def _rational_grid(zs: np.ndarray) -> tuple[Fraction, ...]:
    out = [Fraction(0)]
    for z in zs[1:-1]:
        q = Fraction(round(float(z) * WELD_DENOMINATOR), WELD_DENOMINATOR)
        if out[-1] < q < Fraction(1, 2):
            out.append(q)
    return (*out, Fraction(1, 2))


@functools.lru_cache(maxsize=256)
def weld_centre(curve: tuple[float, ...], a: Fraction) -> tuple[Fraction, tuple[Fraction, ...]] | None:
    """(r, zs): the certificate's centre distance over the line's length, a constant, and
    the segment ends, or None. Tries WELD_SEGMENTS in turn and keeps the first whose
    bounds give up at most WELD_LOSS of the method's C, else the best."""
    af = float(a)
    found = weld_balancing(af, curve)
    if found is None:
        return None
    target = weld_sums(found, curve)[0]
    best: tuple[float, Fraction, tuple[Fraction, ...]] | None = None
    for n in WELD_SEGMENTS:
        zs = _rational_grid(weld_grid(found, af, n, curve))
        grid = np.array([float(z) for z in zs])
        lo, hi = found * 0.8, found
        if weld_bounds(lo, af, grid, curve)[1] <= 0:
            continue
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if weld_bounds(mid, af, grid, curve)[1] > 0 else (lo, mid)
        r = Fraction(math.floor(lo * (1 - WELD_SHORT) * GRID), GRID)
        v, gap = weld_bounds(float(r), af, grid, curve)
        if not (r > 0 and gap > 0):
            continue
        if best is None or v > best[0]:
            best = (v, r, zs)
        if v >= (1 - WELD_LOSS) * target:
            break
    return None if best is None else (best[1], best[2])
