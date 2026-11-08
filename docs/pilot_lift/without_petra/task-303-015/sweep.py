import itertools
from check import run

ANGLES = {  # name: (long leg, short leg, t, lb/ft)
    "L4x4x1_4": (4, 4, 0.25, 6.6), "L4x4x5_16": (4, 4, 0.3125, 8.2),
    "L4x4x3_8": (4, 4, 0.375, 9.8), "L4x3_1_2x5_16": (4, 3.5, 0.3125, 7.7),
    "L4x3_1_2x3_8": (4, 3.5, 0.375, 9.1), "L4x3x3_8": (4, 3, 0.375, 8.5),
    "L5x3_1_2x1_4": (5, 3.5, 0.25, 7.0), "L5x3_1_2x5_16": (5, 3.5, 0.3125, 8.7),
    "L5x3_1_2x3_8": (5, 3.5, 0.375, 10.4),
}
BOLT_LB = {0.75: 0.45, 0.875: 0.68, 1.0: 1.0}
LIMIT = 0.95

out = []
for (an, (ll, sl, t, w)), db, (gr, th), n, Lev, outst, gb, gs in itertools.product(
        ANGLES.items(), (0.75, 0.875, 1.0), (("A325", "N"), ("A325", "X"), ("A490", "N"), ("A490", "X")),
        (3, 4, 5, 6), (1.25, 1.5, 1.75, 2.0, 2.25), ("long", "short"),
        (2.0, 2.25, 2.5, 2.75, 3.0), (2.0, 2.25, 2.5, 2.75, 3.0)):
    if ll == sl and outst == "short":
        continue
    leg_sup = ll if outst == "long" else sl
    leg_beam = sl if outst == "long" else ll
    for setback in (0.5,):
        c = dict(db=db, grade=gr, thr=th, n=n, s=3.0, Lev=Lev, t=t, leg_beam=leg_beam,
                 leg_sup=leg_sup, beam_gauge=gb, support_gauge=gs, beam_edge=gb - setback,
                 top=3.5)
        try:
            L, res, det = run(c, verbose=False)
        except Exception:
            continue
        if max(det.values()) > 1.0 + 1e-9:
            continue
        u = max(res.values())
        if u > LIMIT:
            continue
        wt = w * L / 12
        out.append((wt + n * BOLT_LB[db], wt, u, an, outst, db, gr + "-" + th, n, Lev, gb, gs, L))

out.sort()
print("by angle+bolt weight:")
for r in out[:25]:
    print("  tot %.2f ang %.2f u %.3f %s out %s d %.3f %s n %d Lev %.2f gb %.2f gs %.2f L %.2f" % r)
print("by angle weight, A325-N only:")
o2 = sorted([r for r in out if r[6] == "A325-N"], key=lambda r: (r[1], r[0]))
for r in o2[:25]:
    print("  tot %.2f ang %.2f u %.3f %s out %s d %.3f %s n %d Lev %.2f gb %.2f gs %.2f L %.2f" % r)
