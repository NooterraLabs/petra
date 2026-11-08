import numpy as np
from scipy.optimize import brentq


def icr_C(n, m, s, g, e, ang=0.0):
    """Crawford-Kulak ICR coefficient C for an n-row x m-column group under a vertical
    load at horizontal eccentricity e from the centroid. C = P / Rult."""
    ys = (np.arange(n) - (n - 1) / 2) * s
    xs = (np.arange(m) - (m - 1) / 2) * g
    X, Y = np.meshgrid(xs, ys)
    X = X.ravel()
    Y = Y.ravel()

    def parts(r0):
        xp = X + r0  # ICR at (-r0, 0); load at (+e, 0) acting downward
        d = np.hypot(xp, Y)
        dmax = d.max()
        delta = 0.34 * d / dmax
        R = (1 - np.exp(-10 * delta)) ** 0.55
        Pm = np.sum(R * d) / (e + r0)
        Pv = np.sum(R * xp / d)
        return Pm, Pv, R, xp, d

    f = lambda r0: parts(r0)[0] - parts(r0)[1]
    r0 = brentq(f, 1e-6, 1000)
    Pm, Pv, R, xp, d = parts(r0)
    return Pm, r0


def elastic_C(n, m, s, g, e):
    """Elastic method coefficient (Manual Part 7), conservative cross-check."""
    ys = (np.arange(n) - (n - 1) / 2) * s
    xs = (np.arange(m) - (m - 1) / 2) * g
    X, Y = np.meshgrid(xs, ys)
    X = X.ravel()
    Y = Y.ravel()
    N = len(X)
    Ip = np.sum(X**2 + Y**2)
    # unit load P=1 down at +e: direct shear 1/N down; moment e (clockwise)
    # torsional component on bolt at (x,y): magnitude e*r/Ip perpendicular
    fx = e * Y / Ip
    fy = 1.0 / N + e * X / Ip
    r = np.hypot(fx, fy).max()
    return 1.0 / r


if __name__ == "__main__":
    for g in (3, 5.5, 6, 7.5, 8):
        for n in (2, 3, 4, 5, 6):
            C, r0 = icr_C(n, 2, 3, g, 6)
            print(f"g={g} n={n} C_icr={C:.3f} C_el={elastic_C(n, 2, 3, g, 6):.3f} r0={r0:.3f}")
    # Manual Table 7-7 spot check: s=3, two columns at 3 in, ex=8 in, n=4 -> tabulated C about 3.07
    print("check s=3 g=3 e=8 n=4:", round(icr_C(4, 2, 3, 3, 8)[0], 3))
    print("check s=3 g=5.5 e=6 n=4:", round(icr_C(4, 2, 3, 5.5, 6)[0], 3))
