import itertools
from design import check, weight, BOLT, STOCK, GRADES, V, FNV
from ic import C_elastic

g = 5.5
res = []
for db, rows, s, Lev, Leh, t, grade in itertools.product(
        BOLT, range(2, 7), (3.0, 3.5, 4.0, 4.5, 5.0, 6.0), (1.25, 1.5, 1.75, 2.0),
        (1.25, 1.5), STOCK, GRADES):
    u, info = check(db, rows, s, g, Lev, Leh, t, grade)
    rn_min = min(info["rn_v"], info["rn_pl"], info["rn_fl"])
    u["elastic_bolts"] = V / (C_elastic(rows, 2, s, g, 8.0) * rn_min / 2.0)
    um = max(u.values())
    if um <= 0.95:
        pw, bw = weight(db, rows, s, g, Lev, Leh, t)
        res.append((round(pw + bw, 2), round(pw, 2), round(um, 3), max(u, key=u.get), round(u["bolts"], 3),
                    round(u["elastic_bolts"], 3), db, rows, s, Lev, Leh, t, grade))
res.sort()
for r in res[:25]:
    print(r)
