"""ASD check of the shear tee in final.petra, AISC 360-22 and Manual Part 10 (15th/16th ed.)."""
import math
from icr import icr_C

Va = 9.817                      # kip, service shear
Fy, Fu = 50.0, 65.0             # A992 (tee, beam, column)
# geometry
db, n, s, Lev, a = 0.75, 2, 4.0, 1.75, 3.5
beam_edge_det = 2.25
Leh_beam = beam_edge_det - 0.25  # Manual Part 10 underrun
g = 3.75
dh = db + 1 / 16                # standard hole
dh_net = dh + 1 / 16            # J4 net-section width
# shapes
tw_b, d_b_, tf_b = 0.23, 12.2, 0.38          # W12x26
tf_c, bf_c, tw_c = 0.56, 10.0, 0.34          # W10x49
ts, tf_t, bf_t, d_t = 0.23, 0.38, 6.49, 6.1  # WT6x13 (from W12x26)
L = (n - 1) * s + 2 * Lev
Ab = math.pi * db ** 2 / 4
res = {}

# bolts: Group 120, threads included, Fnv = 54 ksi, single shear
rv = 54 * Ab / 2.0
def bearing(lc, t):
    return min(1.2 * lc * t * Fu, 2.4 * db * t * Fu) / 2.0
# stem bolts: per-bolt minimum of shear, bearing/tearout on stem (bottom edge) and beam web
r_stem = min(bearing(Lev - dh / 2, ts), bearing(s - dh, ts))
r_beam_h = bearing(Leh_beam - dh / 2, tw_b)   # horizontal tearout toward beam end (eccentric load)
r_beam = min(bearing(99, tw_b), r_beam_h)
r_min = min(rv, r_stem, r_beam)
C, _ = icr_C([i * s for i in range(n)], [0] * n, a)
res["stem bolt group, ICR e=a (bolt shear)"] = Va / (C * r_min)
# elastic method cross-check
M = Va * a
J = sum(((i - (n - 1) / 2) * s) ** 2 for i in range(n))
ymax = (n - 1) / 2 * s
fh = M * ymax / J
res["stem bolt group, elastic e=a"] = math.hypot(Va / n, fh) / r_min
# support bolts: 2n bolts, concentric shear, bearing on tee flange and column flange
r_fl = min(rv, bearing(Lev - dh / 2, tf_t), bearing(99, tf_c))
res["support bolts"] = Va / (2 * n * r_fl)

# tee stem
Vy = 0.6 * Fy * L * ts / 1.50
Vr = 0.6 * Fu * (L - n * dh_net) * ts / 2.00
res["stem shear yield"] = Va / Vy
res["stem shear rupture"] = Va / Vr
Agv = (L - Lev) * ts
Anv = (L - Lev - (n - 0.5) * dh_net) * ts
Leh_stem = d_t - a
Ant = (Leh_stem - 0.5 * dh_net) * ts
Rbs = min(0.6 * Fu * Anv, 0.6 * Fy * Agv) + Fu * Ant
res["stem block shear"] = Va / (Rbs / 2.0)
Z = ts * L ** 2 / 4
Znet = Z - sum(ts * dh_net * abs((i - (n - 1) / 2) * s) for i in range(n))
Mf_y = Fy * Z / 1.67
Mf_r = Fu * Znet / 2.00
res["stem flexural yield (M=V a)"] = M / Mf_y
res["stem flexural rupture (M=V a)"] = M / Mf_r
res["stem shear+flexure interaction"] = (Va / Vy) ** 2 + (M / Mf_y) ** 2
# stem buckling, Manual Part 9 plate method
lam = (L * math.sqrt(Fy)) / (10 * ts * math.sqrt(475 + 280 * (L / a) ** 2))
res["stem buckling lambda / 0.7 (Q=1 if <=1)"] = lam / 0.7

# tee flange
res["flange shear yield"] = Va / (0.6 * Fy * 2 * L * tf_t / 1.50)
res["flange shear rupture"] = Va / (0.6 * Fu * 2 * (L - n * dh_net) * tf_t / 2.00)

# beam web (uncoped) shear
res["beam web shear"] = Va / (0.6 * Fy * d_b_ * tw_b / 1.50)

# ductility (Manual Part 10 shear tee)
res["stem thickness <= db/2+1/16"] = ts / (db / 2 + 1 / 16)
b = (g - ts) / 2
Fyb = 92.0
tmax = min(0.163 * db * math.sqrt(Fyb / Fy * (L ** 2 / b ** 2 + 2)), 0.69 * db * math.sqrt(Fyb / Fy))
res["tee flange thickness <= tf,max"] = tf_t / tmax

# detailing (J3.3, J3.4, J3.5)
res["pitch >= 3 db"] = 3 * db / s
res["gauge >= 3 db"] = 3 * db / g
res["Lev >= 1.0 (J3.4)"] = 1.0 / Lev
res["tee flange edge >= 1.0"] = 1.0 / ((bf_t - g) / 2)
res["beam Leh >= 2 db"] = 2 * db / Leh_beam
res["stem Leh >= 2 db"] = 2 * db / Leh_stem
res["stem tip edge <= 12 t"] = Leh_stem / (12 * ts)
res["beam edge <= 12 t"] = beam_edge_det / (12 * tw_b)
res["Lev <= 12 t (stem)"] = Lev / (12 * ts)
res["pitch <= 24 t"] = s / (24 * ts)
res["a <= 3.5"] = a / 3.5
T = d_b_ - 2 * 0.875
res["L >= T/2"] = (T / 2) / L
res["L <= T (fits)"] = (L + (3.0 - Lev) - 0.875) / T if False else L / T

print(f"L = {L} in, C = {C:.3f}, r_min = {r_min:.2f} kip (rv {rv:.2f}, stem {r_stem:.2f}, beam {r_beam:.2f})")
print(f"t_f,max = {tmax:.3f} in, b = {b:.3f} in, tee weight = {13 * L / 12:.2f} lb")
for k, v in sorted(res.items(), key=lambda kv: -kv[1]):
    print(f"{v:6.3f}  {k}")
