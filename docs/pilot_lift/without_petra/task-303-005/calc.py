import math

Ta = 34.745  # kip, ASD service tension
Fy, Fu = 50.0, 65.0
# W16x31 support (AISC Shapes v16)
sup = dict(d=15.9, bf=5.53, tw=0.275, tf=0.44, kdes=0.842, k1=0.75)
# WT shapes (from parent W): bf, tf, tw, plf
WT = {
    'WT8x13':   (5.5, 0.345, 0.25, 13.0),
    'WT8x15_5': (5.53, 0.44, 0.275, 15.5),
    'WT6x13':   (6.49, 0.38, 0.23, 13.0),
    'WT6x17_5': (6.56, 0.52, 0.30, 17.5),
    'WT9x17_5': (6.0, 0.425, 0.30, 17.5),
    'WT8x18':   (6.99, 0.43, 0.295, 18.0),
    'WT7x19':   (6.77, 0.515, 0.31, 19.0),
    'WT6x20':   (8.01, 0.515, 0.295, 20.0),
    'WT8x20':   (7.0, 0.505, 0.305, 20.0),
}
Om_t = 2.0   # bolt tension, J3.6
Om_b = 1.67  # flange bending (prying), Manual Part 9
emin = {0.75: 1.0, 0.875: 1.125, 1.0: 1.25}       # Table J3.4 (2022)
C1 = {0.75: 1.25, 0.875: 1.375, 1.0: 1.4375}      # Manual Table 7-15 tightening clearance


def prying(T, B, t, b, a, p, db, Fu=Fu, Om=Om_b):
    dh = db + 1/16
    bp = b - db/2
    ap = min(a, 1.25*b) + db/2
    rho = bp/ap
    delta = 1 - dh/p
    tc = math.sqrt(Om*4*B*bp/(p*Fu))
    alpha_p = (1/(delta*(1+rho)))*((tc/t)**2 - 1)
    if alpha_p < 0:
        Q = 1.0
    elif alpha_p <= 1:
        Q = (t/tc)**2*(1+delta*alpha_p)
    else:
        Q = (t/tc)**2*(1+delta)
    Tav = B*Q
    # alternative: required thickness with prying for full B (tmin) - Manual eq 9-20
    tmin = math.sqrt(Om*4*T*bp/(p*Fu*(1+delta*min(max(alpha_p,0),1)))) if alpha_p>=0 else None
    return T/Tav, dict(bp=bp, ap=ap, rho=rho, delta=delta, tc=tc, alpha_p=alpha_p, Q=Q, Tav=Tav)


def evaluate(tee, db, grp, g, rows, s, Lev, pmode='min'):
    bf_t, tf_t, tw_t, w = WT[tee]
    Fnt = {120: 90.0, 150: 113.0}[grp]
    Ab = math.pi*db**2/4
    B = Fnt*Ab/Om_t
    n = 2*rows
    T = Ta/n
    L = (rows-1)*s + 2*Lev
    if pmode == 'min':
        p = min(s, L/rows) if rows > 1 else L
    elif pmode == 's':
        p = s
    else:
        p = L/rows
    res = {}
    res['prying_tee'], dt = prying(T, B, tf_t, (g-tw_t)/2, (bf_t-g)/2, p, db)
    res['prying_sup'], ds = prying(T, B, sup['tf'], (g-sup['tw'])/2, (sup['bf']-g)/2, p, db)
    res['bolt_tension'] = T/B
    Ag = L*tw_t
    res['stem_yield'] = Ta/(Fy*Ag/1.67)
    res['stem_rupture'] = Ta/(Fu*Ag/2.0)
    res['J10_1_FLB'] = Ta/(6.25*Fy*sup['tf']**2/1.67)
    res['J10_2_WLY_lb0'] = Ta/(Fy*sup['tw']*(5*sup['kdes'])/1.5)
    res['J10_2_WLY_lbL'] = Ta/(Fy*sup['tw']*(5*sup['kdes']+L)/1.5)
    geo = dict(edge_sup=(sup['bf']-g)/2, edge_tee=(bf_t-g)/2, emin=emin[db],
               s=s, Lev=Lev, clear_sup=g/2-sup['tw']/2, clear_tee=g/2-tw_t/2, C1=C1[db],
               fillet_sup=g/2-sup['k1'])
    ok_geo = (geo['edge_sup'] >= emin[db]-1e-9 and geo['edge_tee'] >= emin[db]-1e-9
              and Lev >= emin[db]-1e-9 and s >= 3*db-1e-9
              and geo['clear_sup'] >= C1[db] and geo['clear_tee'] >= C1[db])
    wt = w*L/12
    return res, geo, ok_geo, wt, L, p, dt, ds


if __name__ == '__main__':
    out = []
    for tee in WT:
        for db in (0.75, 0.875):
            for g in (3.0, 3.25, 3.5, 4.0):
                for rows in (2, 3):
                    for s in (2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 4.0):
                        for Lev in (1.0, 1.125, 1.25, 1.375, 1.5, 1.625, 1.75, 2.0):
                            res, geo, okg, wt, L, p, dt, ds = evaluate(tee, db, 120, g, rows, s, Lev)
                            if not okg:
                                continue
                            # conservative: also with p = min(s, L/rows) and p_s
                            res_s = evaluate(tee, db, 120, g, rows, s, Lev, 's')[0]
                            upry = max(res['prying_tee'], res['prying_sup'], res_s['prying_tee'], res_s['prying_sup'])
                            if upry <= 0.92:
                                out.append((round(wt, 2), tee, db, g, rows, s, Lev, L, p,
                                            round(res['prying_tee'], 3), round(res['prying_sup'], 3), round(upry, 3)))
    out.sort()
    for r in out[:40]:
        print(r)
