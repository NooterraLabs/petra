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

A weld group takes the same argument in units of its line's length, a = e / L, with V(r)
and M(r) - V(r) (a + r) bounded below over segments of its welds (mechanics.group_ic,
limits.ic_weld_bounds). The group is data: a list of straight welds (Segment), each with
its ends and its throat. `pieces` takes any group whose welds lie along or across the load
and that is its own mirror image in the line through its centroid across the load: a line
loaded out of its plane (Manual Table 8-4 with k = 0), a lapped plate's C (Table 8-8), two
parallel lines, a box. Its centre then stays on that line. It refuses the rest: an L, whose
centre leaves the line, and an inclined weld. `weld_centre` picks r and the segments: it
solves the method in floating point, cuts each weld so the segments' bounds give up little,
and walks r back until the bounds' gap is positive. The premises are measured only for the
groups the deck feeds it, the line and the C.
"""
from __future__ import annotations

import functools
import itertools
import math
from fractions import Fraction
from typing import Mapping, NamedTuple

import numpy as np
from scipy.optimize import brentq

from ...kernel import Expr, Interval, enclose, free_syms
from ...mechanics import Run, add, c, mul
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


# --- Weld groups -----------------------------------------------------------------------------------------

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
"""Part of the segments spread evenly along a weld, the rest where the bounds lose most."""
WELD_SHORT = 1e-7
"""How far below the bounds' balancing centre, relative to its distance, r is placed: room
for the kernel's rounding of the bounds, which is far smaller."""
WELD_DENOMINATOR = 1 << 40
"""Segment ends are rounded to this many parts of the group's unit of length."""
WELD_SAMPLES = 20001
"""Points along each weld at which weld_grid weighs where to cut it."""
WELD_LEAST = 4
"""The fewest segments a weld of the group is cut into."""

Point = tuple[Fraction, Fraction]
Segment = tuple[Point, Point, Fraction]
"""A straight weld (start, end, throat): its ends at (x, y), x along the load's arm toward
the load and y along the load, in a unit of length, and its throat over the group's unit
throat."""


class Piece(NamedTuple):
    """A weld of the group's upper half, its coordinates from the group's centroid: a line
    along the load (across False) at x = at, from y = start to end, start >= 0; or a line
    across it at y = at > 0, from x = start to end."""
    across: bool
    at: Fraction
    start: Fraction
    end: Fraction
    throat: Fraction


RATIO_ROOM = Fraction(1, 10 ** 9)
"""How far past the box's ratios, relative to them, a certificate's ratios are stated, so
its switches on e <= a L and kl >= k L pass by far more than ell."""


HELD = Fraction(1, 10 ** 9)
"""How far inside an enclosure, relative to it, a weld certificate's constants are held."""
HELD_FLOOR = Fraction(1, 10 ** 11)
"""And at least this far, in units of Fnw Aw per unit length: each constant's margin over
petra.switch.length, times the weld's length, then passes C by far."""
HELD_GRID = 1 << 64
"""The constants are rounded outward to this many parts of a unit."""


def below(x: Fraction) -> Fraction:
    """A rational on HELD_GRID, held below x by HELD of it and at least HELD_FLOOR."""
    return Fraction(math.floor((x - abs(x) * HELD - HELD_FLOOR) * HELD_GRID), HELD_GRID)


def above(x: Fraction) -> Fraction:
    """A rational on HELD_GRID, held above x by HELD of it and at least HELD_FLOOR."""
    return Fraction(math.ceil((x + abs(x) * HELD + HELD_FLOOR) * HELD_GRID), HELD_GRID)


def weld_ratio(ratio: Interval, least: Fraction) -> Fraction | None:
    """The ratio a = e / L a weld group's certificate is stated at: just above the box's
    largest, on the GRID; None where the box reaches down to least."""
    if not ratio.lo > least * (1 + RATIO_ROOM):
        return None
    return Fraction(math.ceil(ratio.hi * (1 + RATIO_ROOM) * GRID), GRID)


def weld_returns(returns: Interval, most: Fraction) -> Fraction | None:
    """The ratio k = kl / L a C-shaped group's certificate is stated at: just below the
    box's least, on the GRID; None where the box reaches up to most, or k rounds to 0."""
    if not returns.hi < most * (1 - RATIO_ROOM):
        return None
    found = Fraction(math.floor(returns.lo * (1 - RATIO_ROOM) * GRID), GRID)
    return found if found > 0 else None


def weld_curve(registry: Registry) -> tuple[float, ...]:
    return tuple(float(registry.constants[name].value.lo) for name in WELD_ROWS)


def pieces(segments: tuple[Segment, ...]) -> tuple[Piece, ...] | None:
    """The group's upper half about the line through its centroid across the load, or None
    where the method's search and certificate do not hold it: a weld neither along nor
    across the load, a group that is not its own mirror image in that line (its centre
    would leave the line, and V alone no longer balances the load), or a weld across the
    load on the line itself. The centroid weighs each weld by its throat times its length."""
    if not all((p[0] == q[0]) != (p[1] == q[1]) for p, q, _ in segments):
        return None
    weight = [t * (abs(q[0] - p[0]) + abs(q[1] - p[1])) for p, q, t in segments]
    xc, yc = (sum(w * (p[i] + q[i]) / 2 for w, (p, q, _) in zip(weight, segments)) / sum(weight) for i in (0, 1))
    moved = [((p[0] - xc, p[1] - yc), (q[0] - xc, q[1] - yc), t) for p, q, t in segments]

    def key(seg: Segment) -> tuple:
        p, q, t = seg
        return (min(p, q), max(p, q), t)

    if sorted(map(key, moved)) != sorted(key(((p[0], -p[1]), (q[0], -q[1]), t)) for p, q, t in moved):
        return None
    out = []
    for p, q, t in moved:
        if p[0] == q[0]:
            lo, hi = sorted((p[1], q[1]))
            if hi > 0:
                out.append(Piece(False, p[0], max(lo, Fraction(0)), hi, t))
        elif p[1] == 0:
            return None
        elif p[1] > 0:
            out.append(Piece(True, p[1], *sorted((p[0], q[0])), t))
    return tuple(out)


def weld_runs(r: Fraction, group: tuple[Piece, ...], cuts: tuple[tuple[Fraction, ...], ...]) -> tuple[Run, ...]:
    """The group's upper half turning about a centre r behind its centroid, each piece cut
    at its cuts, as mechanics.group_ic's runs: a piece across the load is split where the
    centre's normal crosses it."""
    runs = []
    for piece, at in zip(group, cuts):
        if not piece.across:
            h = piece.at + r
            assert h != 0
            runs.append(Run(abs(h), at, False, 1 if h > 0 else -1, piece.throat))
            continue
        xs = [x + r for x in at]
        zero = (Fraction(0),) if xs[0] < 0 < xs[-1] else ()
        if xs[0] < 0:
            runs.append(Run(piece.at, (*zero, *(-x for x in reversed(xs) if x < 0 or not zero)), True, -1, piece.throat))
        if xs[-1] > 0:
            runs.append(Run(piece.at, (*zero, *(x for x in xs if x > 0 or not zero)), True, 1, piece.throat))
    return tuple(runs)


Span = tuple[float, float, float, bool, int, float]
"""weld_runs' run in floats and uncut: (d, start, end, across, sign, throat)."""


def _spans(r: float, group: tuple[Piece, ...]) -> list[Span]:
    out: list[Span] = []
    for piece in group:
        at, lo, hi, t = float(piece.at), float(piece.start), float(piece.end), float(piece.throat)
        if not piece.across:
            out.append((abs(at + r), lo, hi, False, 1 if at + r > 0 else -1, t))
            continue
        if lo + r < 0:
            out.append((at, max(-(hi + r), 0.0), -(lo + r), True, -1, t))
        if hi + r > 0:
            out.append((at, max(lo + r, 0.0), hi + r, True, 1, t))
    return out


def _weld_ends(spans: list[Span], curve: tuple[float, ...]) -> list[tuple[float, float]]:
    """(rho, Delta_u over the unit w) at each run's far end, where the critical element lies."""
    u0, uoff, upow, ucap = curve[5:9]
    return [(math.hypot(end, d), t * min(u0 * (math.degrees(math.atan2(end, d)) + uoff) ** -upow, ucap))
            for d, _, end, _, _, t in spans]


def _weld_element(u: np.ndarray, d: float, throat: float, ends: list[tuple[float, float]],
                  curve: tuple[float, ...]) -> tuple[np.ndarray, np.ndarray]:
    """(kds, p) of the elements at u along a run d from the centre."""
    kds, kpow, m0, moff, mpow = curve[:5]
    rho = np.hypot(u, d)
    theta = np.degrees(np.arctan2(u, d))
    deformed = np.minimum.reduce([rho / far * du for far, du in ends])
    return 1 + kds * (u / rho) ** kpow, deformed / (throat * (m0 * (theta + moff) ** -mpow))


def _weld_f(p: np.ndarray, curve: tuple[float, ...]) -> np.ndarray:
    a, b, power = curve[9:]
    return (p * (a - b * p)) ** power


def _weld_force(u: np.ndarray, d: float, throat: float, ends: list[tuple[float, float]],
                curve: tuple[float, ...]) -> np.ndarray:
    kds, p = _weld_element(u, d, throat, ends, curve)
    return throat * kds * _weld_f(p, curve)


NODES, WEIGHTS = np.polynomial.legendre.leggauss(20)


def weld_sums(r: float, curve: tuple[float, ...], group: tuple[Piece, ...]) -> tuple[float, float]:
    """(V, M) of the method on the group about a centre r behind its centroid, by
    Gauss-Legendre quadrature over pieces of each run that grade toward the foot of its
    normal, where the elements turn fastest."""
    spans = _spans(r, group)
    ends = _weld_ends(spans, curve)
    v = m = 0.0
    for d, start, end, across, sign, throat in spans:
        cuts = sorted({start, end, *(x for x in d * 2.0 ** np.arange(-8, 12) if start < x < end)})
        for lo, hi in zip(cuts, cuts[1:]):
            u = (hi - lo) / 2 * NODES + (hi + lo) / 2
            w = WEIGHTS * (hi - lo) / 2
            f = _weld_force(u, d, throat, ends, curve)
            rho = np.hypot(u, d)
            v += float(np.sum(w * f * sign * (u if across else d) / rho))
            m += float(np.sum(w * f * rho))
    return 2 * v, 2 * m


def weld_balancing(a: float, curve: tuple[float, ...], group: tuple[Piece, ...]) -> float | None:
    """The centre's distance r behind the centroid that balances a load a from it."""
    def gap(r: float) -> float:
        v, m = weld_sums(r, curve, group)
        return m - v * (a + r)

    lo, hi = 1e-9, 1e3
    if not gap(lo) > 0 > gap(hi):
        return None
    return brentq(gap, lo, hi, xtol=1e-15, rtol=1e-13, maxiter=500)


def _segment(za: float, zb: float, d: float, across: bool) -> tuple[float, float]:
    """(int x / rho, int rho) over [za, zb] of a run in front of the centre."""
    def ends(z: float) -> tuple[float, float]:
        ash = math.asinh(z / d)
        rho = math.hypot(z, d)
        return (rho if across else d * ash), (z * rho + d * d * ash) / 2
    (v0, m0), (v1, m1) = ends(za), ends(zb)
    return v1 - v0, m1 - m0


def _roots(arm: float, d: float, across: bool, sign: int) -> list[float]:
    """The positive roots of u^2 + d^2 - arm x along a run (mechanics.group_ic), rising."""
    if not across:
        q = arm * sign * d - d * d
        return [math.sqrt(q)] if q > 0 else []
    disc = arm * arm - 4 * d * d
    return [(arm - math.sqrt(disc)) / 2, (arm + math.sqrt(disc)) / 2] if sign > 0 and disc > 0 else []


def _spans_of(runs: tuple[Run, ...]) -> list[Span]:
    return [(float(run.d), float(run.us[0]), float(run.us[-1]), run.across, run.sign, float(run.throat)) for run in runs]


def _segment_bounds(runs: tuple[Run, ...], curve: tuple[float, ...]) -> list[list[tuple[float, float]]]:
    """The floating-point value of limits.ic_weld_bounds' (lo, hi) on each segment."""
    spans = _spans_of(runs)
    ends = _weld_ends(spans, curve)
    peak = curve[9] / (2 * curve[10])
    out = []
    for run, (d, _, _, _, _, throat) in zip(runs, spans):
        us = np.array([float(u) for u in run.us])
        kds, p = _weld_element(us, d, throat, ends, curve)
        f = _weld_f(p, curve)
        out.append([(throat * kds[i] * min(f[i], f[i + 1]),
                     throat * kds[i + 1] * float(_weld_f(np.array([max(p[i], min(p[i + 1], peak))]), curve)[0]))
                    for i in range(len(us) - 1)])
    return out


def weld_bounds(arm: Fraction, runs: tuple[Run, ...], curve: tuple[float, ...]) -> tuple[float, float]:
    """The floating-point value of the kernel's (V_lo, gap_lo) for these runs, which
    mechanics.group_ic and limits.ic_weld_bounds state exactly."""
    arm_f = float(arm)
    v = g = 0.0
    for run, segments in zip(runs, _segment_bounds(runs, curve)):
        d, across, sign = float(run.d), run.across, run.sign
        us = [float(u) for u in run.us]
        roots = _roots(arm_f, d, across, sign)
        for i, (lo, hi) in enumerate(segments):
            iv, _ = _segment(us[i], us[i + 1], d, across)
            v += (lo if sign > 0 else hi) * sign * iv
            cuts = [us[i], *(z for z in roots if us[i] < z < us[i + 1]), us[i + 1]]
            past = sum(1 for z in roots if z > us[i])
            for j, (za, zb) in enumerate(zip(cuts, cuts[1:])):
                pv, pm = _segment(za, zb, d, across)
                g += (hi if (past - j) % 2 else lo) * (pm - arm_f * sign * pv)
    return 2 * v, 2 * g


HELD_BOUND = Fraction(1, 10 ** 8)
"""How far inside the float method's value a segment's held bound lies, relative to it:
room for the critical ratio's own HELD and the floats' rounding, which are far smaller."""


def weld_held(runs: tuple[Run, ...], curve: tuple[float, ...]) -> tuple[tuple[Fraction, Fraction],
                                                                        list[list[tuple[Fraction, Fraction]]]]:
    """Rational constants just inside the weld certificate's bounds, from the float method
    (checks.weld_certificate proves each): the critical element's least Delta_u / rho
    (limits.ic_weld_critical) held below and above, and each segment's force bounds
    (limits.ic_weld_bounds) held below and above by HELD_BOUND of them."""
    critical = min(du / rho for rho, du in _weld_ends(_spans_of(runs), curve))
    exact = Fraction(critical)
    held = [[(below(Fraction(lo) * (1 - HELD_BOUND)), above(Fraction(hi) * (1 + HELD_BOUND))) for lo, hi in run]
            for run in _segment_bounds(runs, curve)]
    return (below(exact), above(exact)), held


def weld_grid(r: float, a: float, n: int, curve: tuple[float, ...], group: tuple[Piece, ...]) -> list[np.ndarray]:
    """About n cuts over the group's upper half, each piece's from its start to its end,
    denser where the element's force changes fastest and the bounds' weights are largest:
    density sqrt(|F'| w), which minimises the first order loss of bounds taken at the
    segments' ends, w the weights of V and of the gap. Each piece takes its share of n by
    its integrated density, and at least WELD_LEAST."""
    ends = _weld_ends(_spans(r, group), curve)
    arm = a + r
    densities = []
    for piece in group:
        s = np.linspace(float(piece.start), float(piece.end), WELD_SAMPLES)
        x = np.full_like(s, float(piece.at) + r) if not piece.across else s + r
        u, d = (s, abs(float(piece.at) + r)) if not piece.across else (np.abs(s + r), float(piece.at))
        slope = np.abs(np.gradient(_weld_force(u, d, float(piece.throat), ends, curve), s))
        rho = np.hypot(u, d)
        density = np.sqrt(slope * (np.abs(x) / rho + np.abs(rho * rho - arm * x) / (rho * arm)))
        densities.append((s, density + WELD_FLOOR * density.mean()))
    totals = [np.concatenate([[0.0], np.cumsum((f[1:] + f[:-1]) / 2 * np.diff(s))]) for s, f in densities]
    whole = sum(t[-1] for t in totals)
    counts = [n] if len(totals) == 1 else [max(WELD_LEAST, round(n * t[-1] / whole)) for t in totals]
    return [np.interp(np.linspace(0.0, t[-1], m + 1), t, s) for (s, _), t, m in zip(densities, totals, counts)]


def _rational_grid(zs: np.ndarray, start: Fraction, end: Fraction) -> tuple[Fraction, ...]:
    out = [start]
    for z in zs[1:-1]:
        q = Fraction(round(float(z) * WELD_DENOMINATOR), WELD_DENOMINATOR)
        if out[-1] < q < end:
            out.append(q)
    return (*out, end)


@functools.lru_cache(maxsize=256)
def weld_centre(curve: tuple[float, ...], segments: tuple[Segment, ...], a: Fraction) -> tuple[Fraction, tuple[Run, ...]] | None:
    """(r, runs) for a load a from the group's centroid: the certificate's centre distance
    behind the centroid, a constant, and the group's runs cut into segments; None where
    `pieces` refuses the group or no centre balances the load. Tries WELD_SEGMENTS in turn
    and keeps the first whose bounds give up at most WELD_LOSS of the method's C, else the
    best."""
    group = pieces(segments)
    if group is None:
        return None
    af = float(a)
    found = weld_balancing(af, curve, group)
    if found is None:
        return None
    target = weld_sums(found, curve, group)[0]
    lines = {-p.at for p in group if not p.across}

    def placed(r: float) -> Fraction:
        # on the GRID and off every line along the load, whose distance from the centre a run keeps
        at = Fraction(math.floor(r * GRID), GRID)
        while at in lines:
            at -= Fraction(1, GRID)
        return at

    best: tuple[float, Fraction, tuple[Run, ...]] | None = None
    for n in WELD_SEGMENTS:
        cuts = tuple(_rational_grid(s, p.start, p.end) for s, p in zip(weld_grid(found, af, n, curve, group), group))

        def gap(r: float) -> float:
            at = placed(r)
            return weld_bounds(a + at, weld_runs(at, group, cuts), curve)[1]

        lo, hi = found * 0.8, found
        if gap(lo) <= 0:
            continue
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if gap(mid) > 0 else (lo, mid)
        r = placed(lo * (1 - WELD_SHORT))
        if not r > 0:
            continue
        runs = weld_runs(r, group, cuts)
        v, g = weld_bounds(a + r, runs, curve)
        if not g > 0:
            continue
        if best is None or v > best[0]:
            best = (v, r, runs)
        if v >= (1 - WELD_LOSS) * target:
            break
    return None if best is None else (best[1], best[2])
