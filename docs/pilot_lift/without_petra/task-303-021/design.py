"""Size a bolted bracket plate (ASD) to AISC 360-22 with a conservative envelope of checks."""
import math
import itertools
import numpy as np
from ic import C_ic, bolts

V = 39.889          # kip, ASD service shear
E_ECC = 8.0         # in, from bolt-group centroid
E = 29000.0
# support W12x40 A992
BF, TF, TW = 8.01, 0.515, 0.295
FY_S, FU_S = 50.0, 65.0

GRADES = {"A36": (36.0, 58.0), "A572_50": (50.0, 65.0)}
STOCK = [3/16, 1/4, 5/16, 3/8, 7/16, 1/2, 9/16, 5/8, 3/4, 7/8, 1.0]
BOLT = {  # d: (Ab, std hole, min edge J3.4)
    0.75: (math.pi * 0.75**2 / 4, 13/16, 1.0),
    0.875: (math.pi * 0.875**2 / 4, 15/16, 1.125),
    1.0: (math.pi * 1.0**2 / 4, 1.125, 1.25),
}
FNV = 54.0   # Group 120, threads included (Table J3.2)
OM_BOLT = 2.00


def Q_coped(ho, c, t, Fy):
    lam = ho * math.sqrt(Fy) / (10 * t * math.sqrt(475 + 280 * (ho / c) ** 2))
    if lam <= 0.7:
        return 1.0, lam
    if lam <= 1.41:
        return 1.34 - 0.486 * lam, lam
    return 1.30 / lam**2, lam


def f11(Fy, t, d, Lb, Cb=1.0):
    """AISC F11 rectangular bar bent about its major axis."""
    My = Fy * t * d**2 / 6
    Mp = min(Fy * t * d**2 / 4, 1.5 * My)  # 360-22 F11: Mp <= 1.5 My
    r = Lb * d / t**2
    if r <= 0.08 * E / Fy:
        return Mp
    if r <= 1.9 * E / Fy:
        return min(Cb * (1.52 - 0.274 * r * Fy / E) * My, Mp)
    Fcr = 1.9 * E * Cb / r
    return min(Fcr * t * d**2 / 6, Mp)


def check(db, rows, s, g, Lev, Leh, t, grade, cols=2, verbose=False):
    Fy, Fu = GRADES[grade]
    Ab, dh, emin = BOLT[db]
    dn = dh + 1/16                      # B4.3b net-area hole width
    d = (rows - 1) * s + 2 * Lev        # plate depth
    u = {}
    # geometry
    u["spacing_min"] = (8/3 * db) / min(s, g)
    u["edge_min"] = emin / min(Lev, Leh, (BF - g) / 2)
    u["spacing_max"] = max(s, g) / min(24 * t, 12.0)        # J3.5 (painted)
    u["edge_max"] = max(Lev, Leh) / min(12 * t, 6.0)
    u["flange_fit"] = (g + 2 * emin) / BF
    # bolt strength per bolt (min of shear and bearing/tearout, conservative min lc everywhere)
    rn_v = FNV * Ab
    lc_pl = min(Lev - dh / 2, Leh - dh / 2, s - dh, g - dh)
    rn_pl = min(1.2 * lc_pl * t * Fu, 2.4 * db * t * Fu)
    lc_fl = min((BF - g) / 2 - dh / 2, s - dh, g - dh)
    rn_fl = min(1.2 * lc_fl * TF * FU_S, 2.4 * db * TF * FU_S)
    C, r0 = C_ic(rows, cols, s, g, E_ECC)
    u["bolts"] = V / (C * rn_v / OM_BOLT)
    u["bearing"] = V / (C * min(rn_pl, rn_fl) / 2.00)
    # plate, conservative: full V*e at the critical section
    M = V * E_ECC
    M_phys = V * (E_ECC - (cols - 1) * g / 2)
    Z = t * d**2 / 4
    S = t * d**2 / 6
    ys = (np.arange(rows) - (rows - 1) / 2) * s
    Znet = t * (d**2 / 4 - dn * np.sum(np.abs(ys)))
    if rows % 2 == 1:
        Znet = t * (d**2 / 4 - dn * np.sum(np.abs(ys))) - t * dn**2 / 4
    Mn_y = f11(Fy, t, d, Lb=E_ECC)
    u["flexural_yield"] = M / (Mn_y / 1.67)
    u["flexural_rupture"] = M / (Fu * Znet / 2.00)
    Q, lam = Q_coped(d, E_ECC, t, Fy)
    u["plate_buckling"] = M / (Q * Fy * S / 1.67)
    Vc = 0.6 * Fy * d * t / 1.50
    u["shear_yield"] = V / Vc
    u["shear_rupture"] = V / (0.6 * Fu * (d - rows * dn) * t / 2.00)
    u["interaction"] = (V / Vc) ** 2 + (M / (Fy * Z / 1.67)) ** 2
    # block shear (plate): shear plane along a bolt column from the end bolt to the edge
    Lgv = (rows - 1) * s + Lev
    Agv = Lgv * t
    Anv = (Lgv - (rows - 0.5) * dn) * t
    Ant2 = ((cols - 1) * g + Leh - (cols - 0.5) * dn) * t
    Ant1 = (Leh - 0.5 * dn) * t
    def bs(Ant, Ubs):
        return min(0.6 * Fu * Anv + Ubs * Fu * Ant, 0.6 * Fy * Agv + Ubs * Fu * Ant) / 2.00
    u["block_shear"] = max(V / bs(Ant2, 0.5), V / bs(Ant1, 1.0))
    # physically correct section, for information
    info = dict(C=C, r0=r0, d=d, M_phys_ratio_rupture=M_phys / (Fu * Znet / 2.00),
                M_phys_ratio_buckle=M_phys / (Q * Fy * S / 1.67), lam=lam, Q=Q,
                rn_v=rn_v, rn_pl=rn_pl, rn_fl=rn_fl)
    return u, info


def weight(db, rows, s, g, Lev, Leh, t, cols=2):
    d = (rows - 1) * s + 2 * Lev
    width = (cols - 1) * g + 2 * Leh
    plate = d * width * t * 0.2836
    bolt = rows * cols * {0.75: 0.45, 0.875: 0.68, 1.0: 0.98}[db]
    return plate, bolt


if __name__ == "__main__":
    g = 5.5
    res = []
    for db, rows, s, Lev, Leh, t, grade in itertools.product(
            BOLT, range(2, 7), (3.0, 3.5, 4.0, 4.5, 5.0, 6.0), (1.25, 1.5, 1.75, 2.0),
            (1.25, 1.5, 1.75, 2.0), STOCK, GRADES):
        u, info = check(db, rows, s, g, Lev, Leh, t, grade)
        um = max(u.values())
        if um <= 0.95:
            pw, bw = weight(db, rows, s, g, Lev, Leh, t)
            res.append((pw + bw, pw, um, max(u, key=u.get), db, rows, s, Lev, Leh, t, grade))
    res.sort()
    for r in res[:30]:
        print(" ".join(f"{x:.3f}" if isinstance(x, float) else str(x) for x in r))
