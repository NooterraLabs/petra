import numpy as np
from scipy.optimize import brentq


def bolt_C(n, s, e, cols=1, g=3.0):
    """AISC instantaneous-centre coefficient C for a vertical load at horizontal
    eccentricity e from the centroid of an n-row bolt group with pitch s."""
    ys = np.array([(i - (n - 1) / 2) * s for i in range(n)])
    xs = np.array([(j - (cols - 1) / 2) * g for j in range(cols)])
    X, Y = np.meshgrid(xs, ys)
    X = X.ravel()
    Y = Y.ravel()
    if e == 0:
        return float(len(X))

    def resid(r0):
        dx = X + r0
        dy = Y
        c = np.hypot(dx, dy)
        cmax = c.max()
        d = 0.34 * c / cmax
        R = (1 - np.exp(-10 * d)) ** 0.55
        Fy = np.sum(R * dx / c)
        M = np.sum(R * c)
        P = M / (e + r0)
        return P - Fy, P

    r0 = brentq(lambda r: resid(r)[0], 1e-6, 1000)
    return resid(r0)[1]


def weld_C(L, e, D=1.0, Fexx=70.0, nseg=600):
    """Nominal strength (kip) of two parallel vertical fillet lines of length L
    at the same x (both sides of a plate), vertical load at eccentricity e,
    by the AISC instantaneous-centre method; D in sixteenths."""
    ys = (np.arange(nseg) + 0.5) / nseg * L - L / 2
    xs = np.zeros(nseg)
    ell = L / nseg

    def strength(r0):
        dx = xs + r0
        dy = ys
        c = np.hypot(dx, dy)
        th = np.arccos(np.clip(np.abs(dx) / c, 0, 1))
        thd = th * 180 / np.pi
        sinth = np.sin(th)
        w = D / 16
        du = np.minimum(1.087 * (thd + 6) ** -0.65 * w, 0.17 * w)
        dm = 0.209 * (thd + 2) ** -0.32 * w
        crit = np.argmin(du / c)
        delta = c * du[crit] / c[crit]
        p = delta / dm
        Fw = 0.6 * Fexx * (1 + 0.5 * sinth ** 1.5) * (p * (1.9 - 0.9 * p)) ** 0.3
        R = Fw * 0.707 * w * ell
        Fy = np.sum(R * dx / c)
        M = np.sum(R * c)
        P = M / (e + r0)
        return P - Fy, P

    if e == 0:
        return 2 * 0.6 * Fexx * 0.707 * D / 16 * L
    r0 = brentq(lambda r: strength(r)[0], 1e-4, 1e4)
    return 2 * strength(r0)[1]


if __name__ == "__main__":
    for n in range(2, 7):
        print(n, [round(bolt_C(n, 3.0, e), 3) for e in (0.75, 1.5, 1.75, 2.0, 3.0)])
    # check vs Manual Table 8-4 style: L=12, a=0.25 (e=3), D=1 sixteenth
    print("weld 2 lines L=12 e=0:", weld_C(12, 0, 1), " e=3:", weld_C(12, 3, 1))
