"""Instantaneous-center strength of eccentrically loaded bolt and weld groups.

Bolt groups follow the AISC Manual Part 7 method (cited by Companion Examples II.A-17A, II.A-24
and II.A-30): each bolt's force grows with its slip Δ as R = Rult (1 - e^(-10Δ))^0.55, with
Δ proportional to the distance from the instantaneous center and 0.34 in. at the farthest bolt.

Weld groups follow the Manual Part 8 method (cited by Examples II.A-23 and II.A-26): each
element's strength is 0.60 FEXX (1 + 0.5 sin^1.5 θ) [p (1.9 - 0.9 p)]^0.3 times its throat
area, with p = Δ / Δm, Δm = 0.209 (θ + 2)^-0.32 w and Δu = 1.087 (θ + 6)^-0.65 w ≤ 0.17 w. The
element that first reaches Δu sets the rotation.

Both solvers work in floats, place the load's line of action at a perpendicular distance from
the group's centroid, and search the instantaneous center in two dimensions by Newton's method.
"""

import math


def _rotate(points, theta):
    c, s = math.cos(theta), math.sin(theta)
    return [(x * c - y * s, x * s + y * c) for x, y in points]


def _centered(points):
    n = len(points)
    cx = sum(p[0] for p in points) / n
    cy = sum(p[1] for p in points) / n
    return [(x - cx, y - cy) for x, y in points]


def _solve(forces, e, guess_scale):
    """Find the center (cx, cy) where the resisting forces balance a downward load on x = e,
    and return (P, cx, cy).

    forces(cx, cy) returns a list of (rx, ry, R) with r the vector from the center to the
    element and R the element's force on the loaded part, R (-ry, rx) / |r|. The load P equals
    the resisting moment about the center divided by the lever arm e - cx.
    """

    def residual(cx, cy):
        fx = fy = m = 0.0
        for rx, ry, r in forces(cx, cy):
            d = math.hypot(rx, ry)
            fx += -r * ry / d
            fy += r * rx / d
            m += r * d
        p = m / (e - cx)
        return fx, fy - p, p

    lo, hi = -1e6 * guess_scale, -1e-9 * guess_scale
    for _ in range(200):
        mid = (lo + hi) / 2
        if residual(mid, 0.0)[1] > 0:
            lo = mid
        else:
            hi = mid
    cx, cy = (lo + hi) / 2, 0.0
    h = 1e-7 * guess_scale
    for _ in range(50):
        g1, g2, p = residual(cx, cy)
        if abs(g1) + abs(g2) < 1e-12 * max(1.0, abs(p)):
            break
        a = residual(cx + h, cy)
        b = residual(cx, cy + h)
        j11, j12 = (a[0] - g1) / h, (b[0] - g1) / h
        j21, j22 = (a[1] - g2) / h, (b[1] - g2) / h
        det = j11 * j22 - j12 * j21
        if det == 0:
            break
        dx = (g1 * j22 - g2 * j12) / det
        dy = (j11 * g2 - j21 * g1) / det
        cx, cy = cx - dx, cy - dy
    return residual(cx, cy)[2], cx, cy


def bolt_coefficient(points, ex, angle_deg=0.0):
    """C for a bolt group: the eccentric load it carries, in units of one bolt's strength.

    points are bolt centers in inches. ex is the horizontal distance from the group's centroid to
    the load's line of action, and angle_deg the load's angle from vertical, as Manual Tables 7-6
    to 7-13 define them.
    """
    pts = _centered(points)
    theta = math.radians(angle_deg)
    e = abs(ex) * math.cos(theta)
    if e < 1e-9:
        return float(len(pts))
    return _bolt_center(_rotate(pts, theta), e)[0]


def bolt_forces(points, ex):
    """C and the unit direction of each bolt's force on the connected plate, for a downward load
    ex from the centroid. Each force lies perpendicular to the bolt's radius from the
    instantaneous center, and J3.11a measures that bolt's lc along it."""
    pts = _centered(points)
    e = abs(ex)
    if e < 1e-9:
        return float(len(pts)), [(0.0, 1.0)] * len(pts)
    c, cx, cy = _bolt_center(pts, e)
    pushes = []
    for x, y in pts:
        rx, ry = x - cx, y - cy
        d = math.hypot(rx, ry)
        pushes.append((-ry / d, rx / d))
    return c, pushes


def _bolt_center(pts, e):
    scale = max(1.0, max(math.hypot(x, y) for x, y in pts))

    def forces(cx, cy):
        rs = [(x - cx, y - cy) for x, y in pts]
        dmax = max(math.hypot(rx, ry) for rx, ry in rs)
        out = []
        for rx, ry in rs:
            delta = 0.34 * math.hypot(rx, ry) / dmax
            out.append((rx, ry, (1 - math.exp(-10 * delta)) ** 0.55))
        return out

    return _solve(forces, e, scale)


def bolt_grid(rows, columns, pitch, gauge):
    return [(c * gauge, -r * pitch) for r in range(rows) for c in range(columns)]


def weld_strength(segments, ex, w, fexx, angle_deg=0.0, elements=200):
    """Nominal strength Rn, kips, of a fillet weld group by the instantaneous center method.

    segments are ((x1, y1), (x2, y2)) weld lines in inches, w the leg size in inches, fexx the
    electrode strength in ksi, ex and angle_deg as for bolt_coefficient.
    """
    elems = []
    for (x1, y1), (x2, y2) in segments:
        length = math.hypot(x2 - x1, y2 - y1)
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        for i in range(elements):
            t = (i + 0.5) / elements
            elems.append((x1 + t * (x2 - x1), y1 + t * (y2 - y1), ux, uy, length / elements))
    total = sum(el[4] for el in elems)
    cx0 = sum(el[0] * el[4] for el in elems) / total
    cy0 = sum(el[1] * el[4] for el in elems) / total
    theta = math.radians(angle_deg)
    c, s = math.cos(theta), math.sin(theta)
    rotated = []
    for x, y, ux, uy, dl in elems:
        x, y = x - cx0, y - cy0
        rotated.append((x * c - y * s, x * s + y * c, ux * c - uy * s, ux * s + uy * c, dl))
    e = abs(ex) * math.cos(theta)
    throat = w * math.sqrt(2) / 2
    if e < 1e-9:
        return _concentric_weld(rotated, throat, fexx)
    scale = max(1.0, max(math.hypot(el[0], el[1]) for el in rotated))

    def angle(rx, ry, ux, uy):
        d = math.hypot(rx, ry)
        cosang = abs((-ry * ux + rx * uy) / d)
        return math.degrees(math.acos(min(1.0, cosang)))

    def forces(cx, cy):
        data = []
        ratio = math.inf
        for x, y, ux, uy, dl in rotated:
            rx, ry = x - cx, y - cy
            th = angle(rx, ry, ux, uy)
            du = min(1.087 * (th + 6) ** -0.65 * w, 0.17 * w)
            d = math.hypot(rx, ry)
            ratio = min(ratio, du / d)
            data.append((rx, ry, th, d, dl))
        out = []
        for rx, ry, th, d, dl in data:
            p = ratio * d / (0.209 * (th + 2) ** -0.32 * w)
            k = (1 + 0.5 * math.sin(math.radians(th)) ** 1.5) * (p * (1.9 - 0.9 * p)) ** 0.3
            out.append((rx, ry, 0.6 * fexx * throat * dl * k))
        return out

    return _solve(forces, e, scale)[0]


def _concentric_weld(elems, throat, fexx):
    """A load through the centroid. A linear group, its lines all parallel, takes Eq. J2-5's
    directional increase, which the J2.4 User Note allows when it is loaded through its center of
    gravity. Any other group takes kds = 1.0. In the rotated frame the load is vertical, so the
    sine of its angle to a line is that line's horizontal component."""
    _, _, ux0, uy0, _ = elems[0]
    linear = all(abs(ux * uy0 - uy * ux0) < 1e-9 for _, _, ux, uy, _ in elems)
    kds = 1 + 0.5 * abs(ux0) ** 1.5 if linear else 1.0
    return kds * sum(0.6 * fexx * throat * dl for *_, dl in elems)
