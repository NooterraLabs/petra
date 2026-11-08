import math
import numpy as np
from scipy.optimize import brentq

Vu = 142.863
# Beam W24x55 A992
d_b, tw_b, bf_b, tf_b, kdet_b, T_b = 23.6, 0.395, 7.01, 0.505, 1.4375, 20.75
# Support W14x61 web A992
d_c, tw_c, bf_c, tf_c, kdet_c, T_c = 13.9, 0.375, 10.0, 0.645, 1.5, 10.875
Fy_b, Fu_b = 50.0, 65.0
# Angles A36
Fy_a, Fu_a = 36.0, 58.0


def ic_C(e, ys):
    """Instantaneous-centre coefficient C for one vertical line of bolts, vertical load at e."""
    ys = np.array(ys, dtype=float) - np.mean(ys)

    def resid(ro):
        xs = np.zeros_like(ys) + ro
        dist = np.hypot(xs, ys)
        Delta = 0.34 * dist / dist.max()
        R = (1 - np.exp(-10 * Delta)) ** 0.55
        Ry = np.sum(R * xs / dist)
        M = np.sum(R * dist)
        P = M / (ro + e)
        return Ry - P, P

    ro = brentq(lambda x: resid(x)[0], 1e-4, 200)
    return resid(ro)[1]


def run(db, Fnv, leg_out, leg_beam, t, n, s, Lev, beam_gauge, support_gauge, setback, top, label):
    Ab = math.pi * db ** 2 / 4
    dh = db + 1 / 16          # standard hole
    dn = dh + 1 / 16          # B4.3b net-area hole width
    L = (n - 1) * s + 2 * Lev
    r = {}
    rv = 0.75 * Fnv * Ab
    bear_web = 0.75 * 2.4 * db * tw_b * Fu_b
    lc_web_top = top - dh / 2
    lc_int = s - dh
    web_top = min(bear_web, 0.75 * 1.2 * lc_web_top * tw_b * Fu_b)
    web_int = min(bear_web, 0.75 * 1.2 * lc_int * tw_b * Fu_b)
    lc_edge = Lev - dh / 2
    ang2_edge = min(0.75 * 2.4 * db * 2 * t * Fu_a, 0.75 * 1.2 * lc_edge * 2 * t * Fu_a)
    ang2_int = min(0.75 * 2.4 * db * 2 * t * Fu_a, 0.75 * 1.2 * lc_int * 2 * t * Fu_a)
    per_cons = [min(2 * rv, web_int, ang2_int) for _ in range(n)]
    per_cons[0] = min(2 * rv, web_top, ang2_edge)
    per_cons[-1] = min(2 * rv, web_int, ang2_edge)
    r['beam-side bolts: shear only'] = 2 * rv * n
    r['beam-side bolts+bearing (per bolt min)'] = sum(per_cons)
    r['beam web bearing (group)'] = web_top + (n - 1) * web_int
    g_leg = (support_gauge - tw_b) / 2
    bear_out = 0.75 * 2.4 * db * t * Fu_a
    out_edge = min(bear_out, 0.75 * 1.2 * lc_edge * t * Fu_a)
    out_int = min(bear_out, 0.75 * 1.2 * lc_int * t * Fu_a)
    bear_col = 0.75 * 2.4 * db * tw_c * Fu_b
    per_s = [min(rv, out_int, bear_col)] * n
    per_s[0] = min(rv, out_edge, bear_col)
    r['support-side bolts: shear only'] = 2 * n * rv
    r['support-side bolts+bearing'] = 2 * sum(per_s)
    r['support (column web) bearing'] = 2 * n * bear_col
    Agv = 2 * L * t
    Anv = 2 * (L - n * dn) * t
    r['angle shear yield'] = 1.0 * 0.6 * Fy_a * Agv
    r['angle shear rupture'] = 0.75 * 0.6 * Fu_a * Anv

    def block(toe):
        agv = (L - Lev) * t
        anv = (L - Lev - (n - 0.5) * dn) * t
        ant = (toe - 0.5 * dn) * t
        return 2 * 0.75 * min(0.6 * Fu_a * anv + Fu_a * ant, 0.6 * Fy_a * agv + Fu_a * ant)

    toe_beam = leg_beam - beam_gauge
    toe_out = leg_out - g_leg
    r['angle block shear (beam legs)'] = block(toe_beam)
    r['angle block shear (outstanding legs)'] = block(toe_out)
    r['beam web shear yield (0.9, Cv1=1)'] = 0.9 * 0.6 * Fy_b * d_b * tw_b
    r['beam web shear rupture at bolt line'] = 0.75 * 0.6 * Fu_b * (d_b - n * dn) * tw_b
    ys = [i * s for i in range(n)]
    C_s = ic_C(g_leg, ys)
    r['[sens] support bolts with e = leg gauge (IC)'] = 2 * C_s * min(per_s)
    C_b = ic_C(beam_gauge, ys)
    r['[sens] beam-side bolts with e = beam gauge (IC)'] = C_b * min(per_cons)
    geo = {}
    Lmin = {0.75: 1.0, 0.875: 1.125, 1.0: 1.25}[db]
    geo['spacing, 2.667d, 3d'] = (s, round(2.667 * db, 3), 3 * db)
    geo['Lev, Lmin'] = (Lev, Lmin)
    geo['toe edge beam leg'] = round(toe_beam, 4)
    geo['toe edge outstanding leg'] = round(toe_out, 4)
    geo['beam_edge detailed / strength'] = (beam_gauge - setback, beam_gauge - setback - 0.25)
    geo['edge max 12t<=6'] = min(12 * t, 6)
    geo['spacing max 24t<=12'] = min(24 * t, 12)
    geo['clearance beam leg (g - t)'] = beam_gauge - t
    geo['clearance outstanding leg (g - t)'] = round(g_leg - t, 4)
    geo['outstanding width, col T'] = (2 * leg_out + tw_b, T_c)
    geo['beam bf, col T'] = (bf_b, T_c)
    geo['angle top from beam top, kdet'] = (top - Lev, kdet_b)
    geo['angle bottom from beam top, d-kdet'] = (top - Lev + L, d_b - kdet_b)
    geo['L, T_beam/2, T_beam'] = (L, T_b / 2, T_b)
    geo['bolt line to col flange inner face'] = round(d_c / 2 - tf_c - support_gauge / 2, 4)
    geo['bolt line to col fillet (T/2)'] = round(T_c / 2 - support_gauge / 2, 4)
    print('=====', label, '| L =', L)
    worst = None
    for k, v in r.items():
        u = Vu / v
        print(f'  {k:50s} phiRn = {v:8.2f}  util = {u:.3f}')
        if not k.startswith('[') and (worst is None or u > worst[1]):
            worst = (k, round(u, 4))
    for k, v in geo.items():
        print(f'  {k:50s} {v}')
    print('  GOVERNING:', worst, ' IC C support', round(C_s, 3), ' beam', round(C_b, 3))
    return worst


if __name__ == '__main__':
    run(0.875, 54, 4.0, 3.5, 0.375, 4, 3.0, 1.5, 2.0, 5.5, 0.5, 3.5, 'L4x3-1/2x3/8 OSL long, 7/8 A325-N, s3 Lev1.5')
    run(0.875, 54, 4.0, 3.5, 0.375, 4, 3.0, 1.25, 2.0, 5.5, 0.5, 3.5, 'L4x3-1/2x3/8 OSL long, 7/8 A325-N, s3 Lev1.25')
    run(0.875, 54, 4.0, 3.5, 0.3125, 4, 3.5, 1.5, 2.0, 5.5, 0.5, 3.5, 'L4x3-1/2x5/16 OSL long, 7/8 A325-N, s3.5 Lev1.5')
    run(0.75, 54, 4.0, 3.5, 0.375, 4, 3.0, 1.25, 2.0, 5.5, 0.5, 3.0, '3/4 A325-N 4 rows (reference check)')
