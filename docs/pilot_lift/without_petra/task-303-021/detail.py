from design import check, weight
from ic import C_elastic

cands = {
    "A": (0.75, 4, 3.5, 5.5, 1.5, 1.25, 3/8, "A572_50"),
    "A36": (0.75, 4, 3.5, 5.5, 1.5, 1.25, 3/8, "A36"),
    "B": (0.75, 4, 4.0, 5.5, 1.25, 1.25, 3/8, "A572_50"),
    "C": (0.75, 4, 4.5, 5.5, 1.5, 1.25, 5/16, "A572_50"),
    "D": (0.75, 5, 3.0, 5.5, 1.5, 1.25, 3/8, "A572_50"),
    "E": (0.875, 4, 3.0, 5.5, 1.5, 1.5, 1/2, "A572_50"),
    "F": (0.75, 4, 3.5, 5.5, 1.5, 1.5, 3/8, "A572_50"),
}
for k, c in cands.items():
    u, info = check(*c)
    pw, bw = weight(*c[:7])
    ce = C_elastic(c[1], 2, c[2], c[3], 8.0)
    print(k, c, f"plate {pw:.1f} lb bolts {bw:.1f} lb  C={info['C']:.3f} Cel={ce:.3f} d={info['d']}")
    print("   ", {kk: round(v, 3) for kk, v in sorted(u.items(), key=lambda x: -x[1])})
    print("    phys rupture", round(info["M_phys_ratio_rupture"], 3), "phys buckle", round(info["M_phys_ratio_buckle"], 3),
          "lam", round(info["lam"], 3), "Q", round(info["Q"], 3), "rn", round(info["rn_v"], 2), round(info["rn_pl"], 2), round(info["rn_fl"], 2))
