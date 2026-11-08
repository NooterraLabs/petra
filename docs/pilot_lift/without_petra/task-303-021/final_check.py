"""Final check of the chosen bracket: PL 3/8 A572-50, 2 x 5 3/4 in A325-N, s 3, g 5.5, Lev 1.25, Leh 1.25."""
import math
from design import check, weight, V, Q_coped, f11
from ic import C_ic, C_elastic

c = (0.75, 5, 3.0, 5.5, 1.25, 1.25, 3/8, "A572_50")
u, info = check(*c)
print({k: round(float(v), 3) for k, v in sorted(u.items(), key=lambda x: -x[1])})
print({k: (round(float(v), 3) if isinstance(v, float) else v) for k, v in info.items()})
pw, bw = weight(*c[:7])
print("plate lb", round(pw, 2), "bolts lb", round(bw, 2))
print("C elastic", C_elastic(5, 2, 3.0, 5.5, 8.0), "util", V / (C_elastic(5, 2, 3.0, 5.5, 8.0) * info["rn_v"] / 2))

# standard (physical) plate checks at the outer bolt column, M = V (e - g/2)
Fy, Fu, t, d = 50.0, 65.0, 0.375, info["d"]
M = V * (8.0 - 5.5 / 2)
Z, S = t * d**2 / 4, t * d**2 / 6
dn = 13/16 + 1/16
Znet = t * (d**2 / 4 - dn * (3 + 3 + 6 + 6)) - t * dn**2 / 4
Q, lam = Q_coped(d, 8.0 - 2.75, t, Fy)
print("M at outer bolt line", round(M, 1), "kip-in")
print("yield (Fy Z, F11 Lb=5.25)", round(M / (f11(Fy, t, d, 5.25) / 1.67), 3))
print("rupture Fu Znet/2", round(M / (Fu * Znet / 2), 3), "Znet", round(Znet, 3))
print("buckling Q Fy S (c=5.25)", round(M / (Q * Fy * S / 1.67), 3), "lam", round(lam, 3))
Vc = 0.6 * Fy * d * t / 1.5
print("interaction", round((V / Vc) ** 2 + (M / (Fy * Z / 1.67)) ** 2, 3))
# moment-only bolt coefficient and Part 10 style ductility limit
import numpy as np
from ic import bolts
x, y = bolts(5, 2, 3.0, 5.5)
dd = np.hypot(x, y)
R = (1 - np.exp(-10 * 0.34 * dd / dd.max())) ** 0.55
Cp = float(np.sum(R * dd))
Ab = math.pi * 0.75**2 / 4
Mmax = 1.25 * 54 * Ab * Cp
print("C' (in)", round(Cp, 2), "tmax", round(6 * Mmax / (Fy * d**2), 3))
