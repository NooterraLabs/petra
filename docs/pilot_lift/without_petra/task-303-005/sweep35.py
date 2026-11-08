from calc import evaluate, WT

for g in (3.5, 3.25):
    print('=== gauge', g)
    out = []
    for tee in WT:
        for db in (0.75, 0.875):
            for rows in (2, 3):
                for s in (2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 3.75, 4.0):
                    for Lev in (1.0, 1.125, 1.25, 1.375, 1.5, 1.625, 1.75, 1.875, 2.0):
                        res, geo, okg, wt, L, p, dt, ds = evaluate(tee, db, 120, g, rows, s, Lev)
                        if not okg:
                            continue
                        res_s = evaluate(tee, db, 120, g, rows, s, Lev, 's')[0]
                        res_t = evaluate(tee, db, 120, g, rows, s, Lev, 'trib')[0]
                        u_min = max(res['prying_tee'], res['prying_sup'])
                        u_s = max(res_s['prying_tee'], res_s['prying_sup'])
                        u_t = max(res_t['prying_tee'], res_t['prying_sup'])
                        if max(u_min, u_s, u_t) <= 0.95:
                            out.append((round(wt, 2), tee, db, rows, s, Lev, L, round(p, 3),
                                        round(u_min, 3), round(u_s, 3), round(u_t, 3)))
    out.sort()
    for r in out[:25]:
        print(r)
