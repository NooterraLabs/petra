import math
import sys
sys.path.insert(0, r"C:/Users/aiden/AppData/Local/Temp/claude/b8a6192efa7a5d70/0f9aa34e-5303-40d9-bb2b-9b8f8156fb71/scratchpad/p3/jobs/b/task-303-004")
from icr import icr_C, elastic_C

P = 88.107
bolts = {
    "3/4 A325-N": (0.75, 54), "3/4 A325-X": (0.75, 68), "3/4 A490-X": (0.75, 84),
    "7/8 A325-N": (0.875, 54), "7/8 A325-X": (0.875, 68), "7/8 A490-X": (0.875, 84),
    "1 A325-N": (1.0, 54), "1 A325-X": (1.0, 68), "1 A490-X": (1.0, 84),
}
for name, (d, F) in bolts.items():
    rn = F * math.pi / 4 * d * d
    for basis, k in (("asd", 1 / 2.0), ("lrfd", 0.75)):
        ra = rn * k
        for g in (3, 3.5, 4, 5, 5.5, 6, 7.5, 8):
            for n in range(2, 9):
                for s in (3,):
                    C = icr_C(n, 2, s, g, 6)[0]
                    cap = C * ra
                    if abs(cap / P - 1) < 0.004:
                        print(f"{name} {basis} g={g} n={n} C={C:.4f} cap={cap:.3f} ratio={P/cap:.4f}")
        for n in range(2, 12):
            C = icr_C(n, 1, 3, 0, 6)[0]
            cap = C * ra
            if abs(cap / P - 1) < 0.004:
                print(f"{name} {basis} one column n={n} C={C:.4f} cap={cap:.3f} ratio={P/cap:.4f}")
