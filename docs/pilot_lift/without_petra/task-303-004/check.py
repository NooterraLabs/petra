"""Independent AISC 360-22 / Manual Part 7, 9, 10, 15 checks for an ASD bolted bracket plate
lapped on a column flange, eccentric shear in the plane of the faying surface."""
import math
import sys
sys.path.insert(0, r"C:/Users/aiden/AppData/Local/Temp/claude/b8a6192efa7a5d70/0f9aa34e-5303-40d9-bb2b-9b8f8156fb71/scratchpad/p3/jobs/b/task-303-004")
from icr import icr_C, elastic_C

E = 29000.0
Ra = 88.107  # kip, ASD service shear
e = 6.0      # in, from the bolt group centroid

# support W12x65 flange, A992
bf, tf, tw = 12.0, 0.605, 0.39
Fy_c, Fu_c = 50.0, 65.0

FNV = {("120", "N"): 54, ("120", "X"): 68, ("150", "N"): 68, ("150", "X"): 84}
LEMIN = {0.75: 1.0, 0.875: 1.125, 1.0: 1.25}
GRADES = {"A36": (36, 58), "A572_50": (50, 65)}


def check(grade, t, group, thr, d, n, m, s, g, Lev, Leh, verbose=True):
    Fy, Fu = GRADES[grade]
    dh = d + 1 / 16
    dn = dh + 1 / 16  # B4.3b net-area hole width
    H = 2 * Lev + (n - 1) * s
    out = {}

    # bolt shear, ICR (Manual Part 7) and the elastic method as a cross-check
    rn_v = FNV[(group, thr)] * math.pi / 4 * d * d
    C = icr_C(n, m, s, g, e)[0]
    Cel = elastic_C(n, m, s, g, e)
    # per-bolt bearing / tearout, deformation considered (J3-6a, J3-6c)
    brg_p = 2.4 * d * t * Fu
    tear_edge_v = 1.2 * (Lev - dh / 2) * t * Fu
    tear_edge_h = 1.2 * (Leh - dh / 2) * t * Fu
    tear_int = 1.2 * (s - dh) * t * Fu
    brg_c = 2.4 * d * tf * Fu_c
    edge_c = (bf - g) / 2
    tear_c = 1.2 * (edge_c - dh / 2) * tf * Fu_c
    rn_min = min(rn_v, brg_p, tear_edge_v, tear_edge_h, tear_int, brg_c, tear_c)
    out["bolts (ICR, shear)"] = Ra / (C * rn_v / 2.0)
    out["bolts (elastic, shear)"] = Ra / (Cel * rn_v / 2.0)
    out["bearing/tearout (ICR x min per bolt)"] = Ra / (C * rn_min / 2.0)

    # plate shear at the bolt line nearest the load
    Ag = H * t
    Anv = (H - n * dn) * t
    out["shear_yield"] = Ra / (0.6 * Fy * Ag / 1.50)
    out["shear_rupture"] = Ra / (0.6 * Fu * Anv / 2.00)

    # block shear: shear along the near column top edge -> bottom bolt, tension across to back edge
    Agv = (Lev + (n - 1) * s) * t
    Anv_b = (Lev + (n - 1) * s - (n - 0.5) * dn) * t
    Ant = ((m - 1) * g + Leh - (m - 0.5) * dn) * t
    Rbs = min(0.6 * Fu * Anv_b, 0.6 * Fy * Agv) + 1.0 * Fu * Ant
    out["block_shear (L path)"] = Ra / (Rbs / 2.0)
    # block shear: one bolt column, shear top edge -> bottom bolt, tension to back edge
    Ant1 = (Leh - 0.5 * dn) * t
    Rbs1 = min(0.6 * Fu * Anv_b, 0.6 * Fy * Agv) + Fu * Ant1
    # that block only carries the back column's share; conservatively compare to the full load / m
    out["block_shear (back column, R/m)"] = (Ra / m) / (Rbs1 / 2.0)

    # flexure on the vertical section through the near bolt line
    ys = [(i - (n - 1) / 2) * s for i in range(n)]
    Zg = t * H * H / 4
    Sg = t * H * H / 6
    Znet = Zg - t * dn * sum(abs(y) for y in ys)
    Inet = t * H ** 3 / 12 - t * dn * sum(y * y for y in ys)
    Snet = Inet / (H / 2)
    for label, arm in (("arm e-g/2", e - (m - 1) * g / 2), ("arm e", e)):
        M = Ra * arm
        out[f"flexural_yield ({label})"] = M / (min(Fy * Zg, 1.6 * Fy * Sg) / 1.67)
        out[f"flexural_rupture ({label})"] = M / (Fu * Znet / 2.00)
        # F11 lateral-torsional buckling of a rectangular bar, Lb = arm, Cb = 1
        My = Fy * Sg
        lam = arm * H / t ** 2
        if lam <= 0.08 * E / Fy:
            Mn = min(Fy * Zg, 1.6 * My)
        elif lam <= 1.9 * E / Fy:
            Mn = min(1.0 * (1.52 - 0.274 * lam * Fy / E) * My, Fy * Zg)
        else:
            Mn = 1.9 * E / lam * Sg
        out[f"F11 LTB ({label})"] = M / (Mn / 1.67)
        # Manual Part 9/10 plate buckling (coped-beam / extended-plate form), c = arm
        lamq = H * math.sqrt(Fy) / (10 * t * math.sqrt(475 + 280 * (H / arm) ** 2))
        if lamq <= 0.7:
            Q = 1.0
        elif lamq <= 1.41:
            Q = 1.34 - 0.486 * lamq
        else:
            Q = 1.30 / lamq ** 2
        out[f"plate_buckling Q-method gross S ({label})"] = M / (Q * Fy * Sg / 1.67)
        out[f"plate_buckling Q-method net S ({label})"] = M / (Q * Fy * Snet / 1.67)
        # Part 10 interaction of shear and flexural yielding
        Vc = 0.6 * Fy * Ag / 1.50
        Mc = Fy * Zg / 1.67
        out[f"V-M interaction ({label})"] = (Ra / Vc) ** 2 + (M / Mc) ** 2

    # detailing (J3.3, J3.4, J3.5) and fit on the column flange
    det = {}
    det["pitch >= 3d"] = s >= 3 * d
    det["gauge >= 3d"] = g >= 3 * d
    det["Lev >= Table J3.4"] = Lev >= LEMIN[d]
    det["Leh >= Table J3.4"] = Leh >= LEMIN[d]
    det["flange edge >= Table J3.4"] = edge_c >= LEMIN[d]
    det["edge <= min(12t, 6)"] = max(Lev, Leh) <= min(12 * t, 6.0)
    det["flange edge <= min(12 tf, 6)"] = edge_c <= min(12 * tf, 6.0)
    det["spacing <= min(24t, 12)"] = max(s, g) <= min(24 * t, 12.0)
    det["bolt to web face (in)"] = round(g / 2 - tw / 2, 3)

    if verbose:
        print(f"\n{grade} t={t} | Group {group}-{thr} d={d} | {n}x{m} s={s} g={g} Lev={Lev} Leh={Leh} H={H}")
        print(f"  C_icr={C:.4f} C_el={Cel:.4f} rn/Om shear={rn_v/2:.3f} min per-bolt rn/Om={rn_min/2:.3f}")
        print(f"  per bolt rn/Om: shear {rn_v/2:.2f} brg_plate {brg_p/2:.2f} tear_v {tear_edge_v/2:.2f} tear_h {tear_edge_h/2:.2f} tear_int {tear_int/2:.2f} brg_flange {brg_c/2:.2f} tear_flange {tear_c/2:.2f}")
        for k, v in out.items():
            print(f"  {k:48s} {v:.3f}")
        print("  detailing:", det)
        print(f"  plate t*H = {t*H:.3f} in2 ; bolts = {n*m}")
    return out, det


if __name__ == "__main__":
    check("A572_50", 0.375, "150", "N", 0.75, 6, 2, 3, 5.5, 1.75, 1.75)
    check("A572_50", 0.375, "150", "N", 0.75, 6, 2, 3, 5.5, 1.5, 1.5)
    check("A572_50", 0.4375, "150", "N", 0.75, 6, 2, 3, 5.5, 1.5, 1.5)
    check("A36", 0.5, "120", "N", 0.75, 6, 2, 3, 5.5, 1.5, 1.5)  # likely load-matched layout
    check("A572_50", 0.5, "150", "N", 0.875, 5, 2, 3, 5.5, 1.75, 1.75)
