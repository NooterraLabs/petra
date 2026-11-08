"""Hand check of an all-bolted single-angle connection, AISC 360-22, ASD.
Conservative choices throughout:
  * both bolt groups are taken as eccentric (beam-web leg: e = beam_gauge from the support
    face; support leg: e = support_gauge + tw/2 from the beam web centreline);
  * the eccentric bolt-group strength is C x min(per-bolt strength over shear, bearing and
    tearout at every edge the bolt forces can point to, end and toe), the Manual Part 7
    lower bound;
  * angle flexure checked in both legs with the larger eccentricity.
"""
import math
import sys
from icr import icr

E = 29000.0
RA = 39.449  # kip, ASD service shear

beam = dict(name="W24x55", d=23.6, tw=0.395, tf=0.505, bf=7.01, kdet=1.3125, Fy=50.0, Fu=65.0)
col = dict(name="W14x61", d=13.9, tw=0.375, tf=0.645, bf=10.0, k1=1.0, Fy=50.0, Fu=65.0)
A36 = dict(Fy=36.0, Fu=58.0)

BOLTS = {  # Fnv ksi, Table J3.2 (threads included N / excluded X)
    ("A325", "N"): 54.0, ("A325", "X"): 68.0,
    ("A490", "N"): 68.0, ("A490", "X"): 84.0,
}
EDGE_MIN = {0.75: 1.0, 0.875: 1.125, 1.0: 1.25}  # Table J3.4


def run(c, verbose=True):
    d = c["db"]
    dh = d + 1 / 16          # standard hole, Table J3.3
    dhn = dh + 1 / 16        # net-area width, B4.3b
    n, s, Lev = c["n"], c["s"], c["Lev"]
    t = c["t"]
    L = (n - 1) * s + 2 * Lev
    leg_b, leg_s = c["leg_beam"], c["leg_sup"]
    gb, gs = c["beam_gauge"], c["support_gauge"]
    toe_b, toe_s = leg_b - gb, leg_s - gs
    Leh_beam = c["beam_edge"] - 0.25   # underrun
    Ab = math.pi * d * d / 4
    rv = BOLTS[(c["grade"], c["thr"])] * Ab / 2.0   # single shear, Omega 2.00

    res = {}

    def bt(lc, tp, Fu):  # per-bolt bearing/tearout, deformation considered, ASD
        return min(1.2 * lc * tp * Fu, 2.4 * d * tp * Fu) / 2.0

    # per-bolt minima on each ply, over every edge a bolt force can point to
    ang_end = bt(Lev - dh / 2, t, A36["Fu"])
    ang_int = bt(s - dh, t, A36["Fu"])
    ang_toe_b = bt(toe_b - dh / 2, t, A36["Fu"])
    ang_toe_s = bt(toe_s - dh / 2, t, A36["Fu"])
    web = bt(min(Leh_beam - dh / 2, c["top"] - dh / 2, s - dh), beam["tw"], beam["Fu"])
    flg = bt(1e9, col["tf"], col["Fu"])
    # column flange edge distance across the flange
    xcol = gs + beam["tw"] / 2
    col_edge = col["bf"] / 2 - xcol

    eb = gb
    es = gs + beam["tw"] / 2
    Cb = icr(n, s, eb)[0]
    Cs = icr(n, s, es)[0]
    Cb0 = float(n)

    res["bolt shear, beam leg (e=%.3f, C=%.3f)" % (eb, Cb)] = RA / (Cb * rv)
    res["bolt shear, support leg (e=%.3f, C=%.3f)" % (es, Cs)] = RA / (Cs * rv)
    res["bolt shear, beam leg concentric (C=n)"] = RA / (Cb0 * rv)
    rb_beamleg = min(rv, ang_end, ang_int, ang_toe_b, web)
    rb_supleg = min(rv, ang_end, ang_int, ang_toe_s, flg)
    res["bolts+bearing, beam leg C*min (min=%.2f)" % rb_beamleg] = RA / (Cb * rb_beamleg)
    res["bolts+bearing, support leg C*min (min=%.2f)" % rb_supleg] = RA / (Cs * rb_supleg)

    # angle shear
    Vy = 0.6 * A36["Fy"] * L * t / 1.50
    Vr = 0.6 * A36["Fu"] * (L - n * dhn) * t / 2.00
    res["angle shear yield (J4-3)"] = RA / Vy
    res["angle shear rupture (J4-4)"] = RA / Vr
    # block shear, each leg, tension plane to the toe, shear plane to the far end
    for nm, toe in (("beam leg", toe_b), ("support leg", toe_s)):
        Agv = (L - Lev) * t
        Anv = (L - Lev - (n - 0.5) * dhn) * t
        Ant = (toe - 0.5 * dhn) * t
        Rn = min(0.6 * A36["Fu"] * Anv, 0.6 * A36["Fy"] * Agv) + 1.0 * A36["Fu"] * Ant
        res["angle block shear, %s" % nm] = RA / (Rn / 2.0)
    # angle flexure, in-plane bending of the leg, larger eccentricity
    e = max(eb, es)
    M = RA * e
    S = t * L * L / 6
    Z = t * L * L / 4
    My = A36["Fy"] * S
    Lb = e
    lam = Lb * L / t ** 2
    if lam <= 0.08 * E / A36["Fy"]:
        Mn = A36["Fy"] * Z
    elif lam <= 1.9 * E / A36["Fy"]:
        Mn = min(A36["Fy"] * Z, (1.52 - 0.274 * lam * A36["Fy"] / E) * My)
    else:
        Mn = min(A36["Fy"] * Z, 1.9 * E / lam * S)
    res["angle flexural yield (F11, Cb=1)"] = M / (Mn / 1.67)
    ys = [(i - (n - 1) / 2) * s for i in range(n)]
    Znet = Z - t * dhn * sum(abs(y) for y in ys)
    res["angle flexural rupture (Fu Znet)"] = M / (A36["Fu"] * Znet / 2.0)
    res["angle shear+flexure interaction (gross)"] = math.sqrt(
        (RA / Vy) ** 2 + (M / (Mn / 1.67)) ** 2)
    # beam web shear (gross), column flange bearing already in min
    res["beam web shear yield (G2)"] = RA / (0.6 * beam["Fy"] * beam["d"] * beam["tw"] / 1.5)

    # detailing (pass/fail as ratio required/provided)
    emin = EDGE_MIN[d]
    det = {}
    det["spacing >= 2-2/3 d"] = (8 / 3 * d) / s
    det["spacing >= 3d (preferred)"] = (3 * d) / s
    det["Lev >= Table J3.4"] = emin / Lev
    det["toe edge beam leg >= J3.4"] = emin / toe_b
    det["toe edge support leg >= J3.4"] = emin / toe_s
    det["beam edge (less 1/4 underrun) >= J3.4"] = emin / Leh_beam
    det["column flange edge >= J3.4"] = emin / col_edge
    det["edge max 12t<=6in (Lev)"] = Lev / min(12 * t, 6.0)
    det["edge max (toe beam)"] = toe_b / min(12 * t, 6.0)
    det["edge max (toe sup)"] = toe_s / min(12 * t, 6.0)
    det["spacing max 24t<=12"] = s / min(24 * t, 12.0)
    T = beam["d"] - 2 * beam["kdet"]
    det["angle length >= T/2 (stability)"] = (T / 2) / L
    det["angle within T (top clear of fillet)"] = beam["kdet"] / (c["top"] - Lev)
    bot = c["top"] + (n - 1) * s + Lev
    det["angle within T (bottom)"] = bot / (beam["d"] - beam["kdet"])
    det["outstanding toe on column flange"] = (leg_s + beam["tw"] / 2) / (col["bf"] / 2)
    det["support bolt clear of col web fillet (washer)"] = (col["k1"] + (2 * d) / 2) / xcol
    det["angle t <= 5/8 (flexibility)"] = t / 0.625
    det["setback >= 1/2 beam end clear"] = 0.5 / (gb - c["beam_edge"]) if gb - c["beam_edge"] > 0 else 9.9

    if verbose:
        print(f"L = {L:.3f} in, angle t = {t}, bolts {n} x {d} {c['grade']}-{c['thr']}, rv = {rv:.2f} k")
        print(f"per-bolt: angle end {ang_end:.2f}, int {ang_int:.2f}, toe_b {ang_toe_b:.2f}, toe_s {ang_toe_s:.2f}, web {web:.2f}, col flg {flg:.2f}")
        for k, v in sorted(res.items(), key=lambda kv: -kv[1]):
            print(f"  {v:6.3f}  {k}")
        print(" detailing (<=1 ok):")
        for k, v in det.items():
            flag = "" if v <= 1.0 + 1e-9 else "   <-- FAIL"
            print(f"  {v:6.3f}  {k}{flag}")
    return L, res, det


if __name__ == "__main__":
    base = dict(db=0.875, grade="A325", thr="N", n=4, s=3.0, Lev=1.75, t=0.375,
                leg_beam=4.0, leg_sup=4.0, beam_gauge=2.5, support_gauge=2.5,
                beam_edge=2.0, top=3.5)
    run(base)
