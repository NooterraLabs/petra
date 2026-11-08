"""ASD check of a conventional single-plate (shear tab) connection, AISC 360-22
and Manual Part 10 (Table 10-9 eccentricity), for task 303-006."""
import math
from ic import bolt_C, weld_C

V = 45.988  # kip, service (ASD) shear

# shapes
beam = dict(name="W18x35", d=17.7, tw=0.300, tf=0.425, bf=6.00, kdet=1.125, T=15.5, Fy=50.0, Fu=65.0)
col = dict(name="W10x49", d=10.0, tw=0.340, tf=0.560, bf=10.0, T=7.5, Fy=50.0, Fu=65.0)

GRADES = {"A36": (36.0, 58.0), "A572_50": (50.0, 65.0)}
FNV = {("120", "N"): 54.0, ("120", "X"): 68.0, ("150", "N"): 68.0, ("150", "X"): 84.0}


def check(db, group, thr, n, s, Lev, Leh_p, a, setback, top, tp, grade, w, ecc_rule="table10-9", verbose=True):
    Fyp, Fup = GRADES[grade]
    Ab = math.pi * db ** 2 / 4
    dh = db + 1 / 16                     # standard hole
    dn = dh + 1 / 16                     # hole width for net area (B4.3b)
    L = 2 * Lev + (n - 1) * s
    beam_edge = a - setback
    Leh_b = beam_edge - 0.25            # 1/4 in underrun
    out = {}

    # eccentricity per Manual Table 10-9 (n = 2..5, STD holes -> a/2)
    e = a / 2 if (ecc_rule == "table10-9" and n <= 5) else a
    C = bolt_C(n, s, e)

    # per-bolt strengths (ASD)
    rv = FNV[(group, thr)] * Ab / 2.0
    # bearing / tearout, deformation considered: 2.4 d t Fu, 1.2 lc t Fu ; Omega 2.00
    def br(t, Fu, lc):
        return min(1.2 * lc * t * Fu, 2.4 * db * t * Fu) / 2.0
    p_int = br(tp, Fup, s - dh)
    p_edge_v = br(tp, Fup, Lev - dh / 2)
    p_edge_h = br(tp, Fup, Leh_p - dh / 2)
    b_int = br(beam["tw"], beam["Fu"], s - dh)
    b_edge_h = br(beam["tw"], beam["Fu"], Leh_b - dh / 2)
    b_full = 2.4 * db * beam["tw"] * beam["Fu"] / 2.0  # uncoped: no vertical edge
    rmin_all = min(rv, p_int, p_edge_v, p_edge_h, b_int, b_edge_h, b_full)
    out["bolts (shear, C=%.3f, e=%.3f)" % (C, e)] = V / (C * rv)
    out["bearing (C x min per-bolt bearing/tearout, any direction)"] = V / (C * min(p_int, p_edge_v, p_edge_h, b_int, b_edge_h, b_full))
    out["bolt group (C x governing per-bolt)"] = V / (C * rmin_all)

    # plate shear yield / rupture
    Ag = L * tp
    Anv = (L - n * dn) * tp
    out["plate shear_yield"] = V / (0.6 * Fyp * Ag / 1.5)
    out["plate shear_rupture"] = V / (0.6 * Fup * Anv / 2.0)
    # block shear (single vertical row, Ubs = 1)
    Agv = (L - Lev) * tp
    Anv_b = (L - Lev - (n - 0.5) * dn) * tp
    Ant = (Leh_p - 0.5 * dn) * tp
    Rbs = min(0.6 * Fup * Anv_b + Fup * Ant, 0.6 * Fyp * Agv + Fup * Ant)
    out["plate block_shear"] = V / (Rbs / 2.0)
    # flexure of plate, M = V a at the weld line (conservative for conventional)
    M = V * a
    Z = tp * L ** 2 / 4
    ys = [abs((i - (n - 1) / 2) * s) for i in range(n)]
    Znet = Z - tp * dn * sum(ys)
    Mc_y = Fyp * Z / 1.67
    Mc_r = Fup * Znet / 2.0
    out["plate flexural_yield"] = M / Mc_y
    out["plate flexural_yield + shear interaction (sum of squares)"] = (V / (0.6 * Fyp * Ag / 1.5)) ** 2 + (M / Mc_y) ** 2
    out["plate flexural_rupture"] = M / Mc_r
    # weld: two fillets, E70, concentric and with eccentricity a
    D = w * 16
    Rw0 = 2 * 0.6 * 70 * 0.707 * w * L / 2.0
    Rwe = weld_C(L, a, D) / 2.0
    out["weld (direct shear)"] = V / Rw0
    out["weld (eccentric, e=a, IC)"] = V / Rwe
    # weld base metal: column web, two shear planes (plate on one side): Manual 9-2
    out["support web base metal (tmin=3.09D/Fu)/tw"] = (3.09 * D / col["Fu"]) / col["tw"]
    out["support web base metal (tmin=6.19D/Fu)/tw (conservative)"] = (6.19 * D / col["Fu"]) / col["tw"]
    out["support web shear rupture along welds (1 plane)"] = V / (0.6 * col["Fu"] * col["tw"] * L / 2.0)
    out["plate base metal at weld (shear rupture)"] = V / (0.6 * Fup * tp * L / 2.0)
    # beam web shear (gross), uncoped
    out["beam web shear yield (gross)"] = V / (0.6 * beam["Fy"] * beam["d"] * beam["tw"] / 1.5)
    out["beam web shear rupture along bolt line"] = V / (0.6 * beam["Fu"] * (beam["d"] - n * dn) * beam["tw"] / 2.0)

    geo = {}
    geo["L (plate length)"] = L
    geo["plate width a+Leh"] = a + Leh_p
    geo["plate volume in3"] = L * (a + Leh_p) * tp
    geo["plate mass lb"] = L * (a + Leh_p) * tp * 0.2836
    geo["L <= beam T"] = L <= beam["T"]
    geo["L >= T/2"] = L >= beam["T"] / 2
    geo["plate top below beam top"] = top - Lev
    geo["plate top >= kdet"] = top - Lev >= beam["kdet"]
    geo["plate bottom <= d - kdet"] = top - Lev + L <= beam["d"] - beam["kdet"]
    geo["a <= 3.5"] = a <= 3.5
    geo["Leh plate >= 2db"] = Leh_p >= 2 * db
    geo["Leh beam (less underrun) >= 2db"] = Leh_b >= 2 * db
    geo["t <= db/2+1/16 (plate or web)"] = min(tp, beam["tw"]) <= db / 2 + 1 / 16
    geo["plate t <= db/2+1/16"] = tp <= db / 2 + 1 / 16
    geo["w >= 5/8 tp"] = w >= 5 / 8 * tp
    tthin = min(tp, col["tw"])
    wmin = 1 / 8 if tthin <= 0.25 else (3 / 16 if tthin <= 0.5 else (1 / 4 if tthin <= 0.75 else 5 / 16))
    geo["w >= Table J2.4 min"] = w >= wmin
    geo["s >= 3db (preferred)"] = s >= 3 * db
    Jmin = {0.75: 1.0, 0.875: 1.125, 1.0: 1.25}[db]
    geo["Lev, Leh_p, Leh_b >= J3.4 min"] = min(Lev, Leh_p, Leh_b) >= Jmin
    tmin_ply = min(tp, beam["tw"])
    geo["edges <= min(12t,6)"] = max(Lev, Leh_p, beam_edge) <= min(12 * tmin_ply, 6)
    geo["s <= min(24t,12)"] = s <= min(24 * tmin_ply, 12)
    geo["beam bf fits column T"] = beam["bf"] <= col["T"]
    geo["plate width inside column flange projection"] = a + Leh_p <= (col["bf"] - col["tw"]) / 2
    geo["clear from beam web face to col flange"] = (col["d"] - 2 * col["tf"]) / 2 - beam["tw"] / 2
    geo["clear from plate face to col flange"] = (col["d"] - 2 * col["tf"]) / 2 - beam["tw"] / 2 - tp
    geo["per-bolt: shear, plate int, plate edge v, plate edge h, web int, web edge h, web full"] = [round(x, 2) for x in (rv, p_int, p_edge_v, p_edge_h, b_int, b_edge_h, b_full)]
    if verbose:
        for k, v in out.items():
            print(f"  {k:60s} {v:6.3f}")
        for k, v in geo.items():
            print(f"  {k:60s} {v}")
    return out, geo


if __name__ == "__main__":
    import sys
    cands = {
        "H: 4x3/4 A490-N, 5/16 A572-50, a=2.5": dict(db=0.75, group="150", thr="N", n=4, s=3.0, Lev=1.75, Leh_p=1.75, a=2.5, setback=0.5, top=3.5, tp=5 / 16, grade="A572_50", w=0.25),
        "D: 4x7/8 A325-N, 5/16 A572-50, a=2.75": dict(db=0.875, group="120", thr="N", n=4, s=3.0, Lev=1.75, Leh_p=1.75, a=2.75, setback=0.5, top=3.5, tp=5 / 16, grade="A572_50", w=0.25),
        "A: 4x7/8 A325-N, 3/8 A36, a=3": dict(db=0.875, group="120", thr="N", n=4, s=3.0, Lev=1.75, Leh_p=1.75, a=3.0, setback=0.5, top=3.5, tp=3 / 8, grade="A36", w=0.25),
        "B: 5x3/4 A325-N, 3/8 A36, a=3": dict(db=0.75, group="120", thr="N", n=5, s=3.0, Lev=1.5, Leh_p=1.5, a=3.0, setback=0.5, top=3.0, tp=3 / 8, grade="A36", w=0.25),
    }
    for name, c in cands.items():
        print("==", name)
        out, geo = check(**c)
        print("  MAX util:", round(max(v for k, v in out.items() if "6.19" not in k and "3.09" not in k and "sum of squares" not in k), 3))
        print("  -- with e = a (conservative, not Table 10-9):")
        out2, _ = check(**c, ecc_rule="a", verbose=False)
        print("    bolt group:", round(out2[[k for k in out2 if k.startswith("bolt group")][0]], 3))
