import numpy as np
from scipy.optimize import brentq


def icr_line(L, e, w=1/16, Fexx=70.0, n=400):
    """ICR (AISC 360-22 J2.5, Manual Part 8) for two coincident vertical weld lines of length L
    (each of leg w), vertical load P at horizontal distance e from the line. Returns Pn (kip)."""
    dy = L/n
    y = -L/2 + dy*(np.arange(n)+0.5)
    A = 0.7071*w*dy*2  # two lines

    def resid(r0):
        x = r0*np.ones_like(y)
        r = np.sqrt(x**2 + y**2)
        theta = np.degrees(np.arccos(np.clip(np.abs(x)/r, 0, 1)))
        dm = 0.209*(theta+2)**-0.32*w
        du = np.minimum(1.087*(theta+6)**-0.65*w, 0.17*w)
        k = np.min(du/r)
        d = k*r
        p = d/dm
        fp = (p*(1.9-0.9*p))**0.3
        R = 0.6*Fexx*(1+0.5*np.sin(np.radians(theta))**1.5)*fp*A
        Ry = np.sum(R*x/r)
        M = np.sum(R*r)
        return Ry - M/(e + r0), Ry

    rs = np.logspace(-4, 3, 400)*L
    vals = [resid(r)[0] for r in rs]
    for i in range(len(rs)-1):
        if np.sign(vals[i]) != np.sign(vals[i+1]):
            r0 = brentq(lambda r: resid(r)[0], rs[i], rs[i+1], xtol=1e-12)
            return resid(r0)[1], r0
    raise RuntimeError("no root")


def C_coef(a, n=400):
    L = 10.0
    Pn, r0 = icr_line(L, a*L, n=n)
    return Pn/L


if __name__ == "__main__":
    for a in [0.0001, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.4, 1.6, 2.0]:
        print(f"a={a:.2f}  C={C_coef(a):.3f}  C(n=1000)={C_coef(a, 1000):.3f}")
