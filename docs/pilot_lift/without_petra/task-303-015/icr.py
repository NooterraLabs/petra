import numpy as np
from scipy.optimize import brentq


def icr(n, s, e, cols=1, g=0.0):
    """Instantaneous-centre analysis (AISC Manual Part 7, Crawford-Kulak) of a bolt
    group under a vertical load at horizontal eccentricity e from the group centroid.
    Returns C (load / single-bolt strength), r0, and the per-bolt force vectors
    (as fractions of the ultimate bolt strength)."""
    ys = (np.arange(n) - (n - 1) / 2) * s
    xs = (np.arange(cols) - (cols - 1) / 2) * g
    pts = np.array([(x, y) for x in xs for y in ys])

    def state(r0):
        dx = pts[:, 0] + r0
        dy = pts[:, 1]
        r = np.hypot(dx, dy)
        delta = 0.34 * r / r.max()
        R = (1 - np.exp(-10 * delta)) ** 0.55
        Ry = np.sum(R * dx / r)
        M = np.sum(R * r)
        P = M / (e + r0)
        # force direction on each bolt: perpendicular to radius
        fx = -R * dy / r
        fy = R * dx / r
        return P - Ry, P, np.c_[fx, fy], pts

    if e <= 1e-9:
        return float(n * cols), np.inf, None, pts
    r0 = brentq(lambda r: state(r)[0], 1e-6, 1e5)
    _, P, F, pts = state(r0)
    return P, r0, F, pts


if __name__ == "__main__":
    for n in (3, 4, 5, 6):
        row = []
        for e in (1.5, 2.0, 2.25, 2.5, 2.7, 3.0):
            row.append(f"e={e}:{icr(n, 3.0, e)[0]:.3f}")
        print(n, " ".join(row))
