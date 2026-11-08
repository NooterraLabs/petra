import numpy as np
from scipy.optimize import brentq


def bolts(rows, cols, s, g):
    xs = (np.arange(cols) - (cols - 1) / 2) * g
    ys = (np.arange(rows) - (rows - 1) / 2) * s
    X, Y = np.meshgrid(xs, ys)
    return X.ravel(), Y.ravel()


def C_ic(rows, cols, s, g, e, normalize=False):
    """IC method (AISC Manual Part 7) for a vertical load at x = +e from the centroid.
    Returns C (in units of Rult, or of R(0.34) when normalize) and r0."""
    x, y = bolts(rows, cols, s, g)

    def resid(r0):
        dx = x + r0
        d = np.hypot(dx, y)
        dmax = d.max()
        D = 0.34 * d / dmax
        R = (1 - np.exp(-10 * D)) ** 0.55
        if normalize:
            R = R / (1 - np.exp(-3.4)) ** 0.55
        Pm = np.sum(R * d) / (e + r0)
        Pv = np.sum(R * dx / d)
        return Pm - Pv, Pm

    r0 = brentq(lambda r: resid(r)[0], 1e-6, 1e4)
    return resid(r0)[1], r0


def C_elastic(rows, cols, s, g, e):
    x, y = bolts(rows, cols, s, g)
    n = len(x)
    Ip = np.sum(x ** 2 + y ** 2)
    # unit P downward at x=e: direct v = 1/n; torsion M = e
    fx = e * y / Ip
    fy = 1 / n + e * x / Ip
    fmax = np.max(np.hypot(fx, fy))
    return 1 / fmax


if __name__ == "__main__":
    # sanity check against AISC Manual Table 7-6 (one column, s = 3 in, angle 0):
    # tabulated e = 8 in, n = 6 -> C about 2.63 ; n = 4 -> about 1.36 (from memory, rough)
    for n in (4, 6):
        print("1 col", n, C_ic(n, 1, 3.0, 0.0, 8.0), C_ic(n, 1, 3.0, 0.0, 8.0, True))
    for n in range(2, 9):
        for g in (3.0, 5.5):
            c1, _ = C_ic(n, 2, 3.0, g, 8.0)
            c2, _ = C_ic(n, 2, 3.0, g, 8.0, normalize=True)
            ce = C_elastic(n, 2, 3.0, g, 8.0)
            print(f"rows {n} g {g}: C={c1:.3f} (norm {c2:.3f}) elastic {ce:.3f}")
