import numpy as np
from calc_icr import icr_line

V = 48.42          # kip, service (ASD)
e = 5.0            # in
M = V*e            # kip-in at the weld line
E = 29000.0
tf, Fu_f = 0.515, 65.0   # W12x40 flange, A992
grades = {"A36": (36.0, 58.0), "A572_50": (50.0, 65.0)}
thk = [3/16, 1/4, 5/16, 3/8, 7/16, 1/2, 9/16, 5/8, 3/4]


_cache = {}


def pn16(L):
    """ICR nominal strength for 1/16 in legs, both sides, length L (kip); scales linearly with D."""
    if L not in _cache:
        _cache[L] = icr_line(L, e, w=1/16, n=200)[0]
    return _cache[L]


def min_fillet(t):
    if t <= 0.25:
        return 1/8
    if t <= 0.5:
        return 3/16
    if t <= 0.75:
        return 1/4
    return 5/16


def checks(g, t, D, L):
    Fy, Fu = grades[g]
    w = D/16
    out = {}
    Pn = pn16(L)*D
    out["weld_icr"] = V/(Pn/2.0)
    # elastic, per weld per inch
    fv = V/(2*L)
    fb = 3*M/L**2
    f = np.hypot(fv, fb)
    cap = 0.6*70*0.7071*w/2.0
    out["weld_elastic"] = f/cap
    th = np.arctan2(fb, fv)
    out["weld_elastic_kds"] = f/(cap*(1+0.5*np.sin(th)**1.5))
    out["base_plate"] = (6.19*D/Fu)/t
    out["base_flange"] = (6.19*D/Fu_f)/tf
    out["fillet_min"] = min_fillet(min(t, tf))/w
    Vc = 0.6*Fy*t*L/1.5
    out["shear_yield"] = V/Vc
    out["shear_rupture"] = V/(0.6*Fu*t*L/2.0)
    Z = t*L**2/4
    S = t*L**2/6
    Mc = Fy*Z/1.67
    out["flex_yield"] = M/Mc
    out["flex_rupture"] = M/(Fu*Z/2.0)
    out["interaction"] = (V/Vc)**2 + (M/Mc)**2
    # Manual Part 9 plate buckling (doubly-coped analogue), ho = L, c = e
    lam = L*np.sqrt(Fy)/(10*t*np.sqrt(475+280*(L/e)**2))
    Q = 1.0 if lam <= 0.7 else (1.34-0.486*lam if lam <= 1.41 else 1.30/lam**2)
    out["lambda"] = lam
    out["buckle_S"] = M/(Fy*Q*S/1.67)
    # F11 LTB, Cb = 1, Lb = e and Lb = 2e
    for tag, Lb in (("ltb_e", e), ("ltb_2e", 2*e)):
        r = Lb*L/t**2
        My = Fy*S
        if r <= 0.08*E/Fy:
            Mn = min(Fy*Z, 1.6*My)
        elif r <= 1.9*E/Fy:
            Mn = min((1.52-0.274*r*Fy/E)*My, Fy*Z)
        else:
            Mn = min(1.9*E/r*S, Fy*Z)
        out[tag] = M/(Mn/1.67)
    out["tL"] = t*L
    return out


if __name__ == "__main__":
    rows = []
    for g in grades:
        for t in thk:
            for D in range(2, 9):
                for L in np.arange(6, 24.01, 0.5):
                    c = checks(g, t, D, L)
                    core = max(c["weld_icr"], c["base_plate"], c["base_flange"], c["fillet_min"],
                               c["shear_yield"], c["shear_rupture"], c["flex_yield"],
                               c["flex_rupture"], c["interaction"])
                    if core <= 1.0:
                        rows.append((c["tL"], g, t, D, L, c))
                        break
    rows.sort(key=lambda r: r[0])
    keys = ["weld_icr", "weld_elastic", "weld_elastic_kds", "base_plate", "fillet_min", "shear_yield",
            "flex_yield", "interaction", "buckle_S", "ltb_e", "ltb_2e", "lambda"]
    print("tL   grade  t     D  L    " + " ".join(f"{k[:9]:>9}" for k in keys))
    for tL, g, t, D, L, c in rows[:40]:
        print(f"{tL:5.2f} {g:7s} {t:.4f} {D} {L:5.2f} " + " ".join(f"{c[k]:9.3f}" for k in keys))
