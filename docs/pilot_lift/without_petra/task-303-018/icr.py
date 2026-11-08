import numpy as np
from scipy.optimize import brentq


def icr_C(ys, xs, e):
    """Crawford-Kulak ICR. Vertical load at distance e (along x) from the centroid.
    Returns C = P / r_ult (the Manual Table 7-6 coefficient)."""
    xs = np.array(xs, float)
    ys = np.array(ys, float)
    xs = xs - xs.mean()
    ys = ys - ys.mean()
    Dmax = 0.34

    def forces(r0):
        dx = xs + r0
        dy = ys
        d = np.hypot(dx, dy)
        dm = d.max()
        D = Dmax * d / dm
        R = (1 - np.exp(-10 * D)) ** 0.55
        return dx, dy, d, R

    def resid(r0):
        dx, dy, d, R = forces(r0)
        M = np.sum(R * d)
        P = M / (e + r0)
        Fy = np.sum(R * dx / d)
        return Fy - P

    r0 = brentq(resid, 1e-6, 1e4)
    dx, dy, d, R = forces(r0)
    return np.sum(R * d) / (e + r0), r0


if __name__ == "__main__":
    for n in (2, 3):
        for s in (3.0,):
            ys = [i * s for i in range(n)]
            for e in (0.001, 2.5, 2.75, 3.0, 3.25, 3.5):
                C, r0 = icr_C(ys, [0] * n, e)
                print(n, s, e, round(C, 3))
