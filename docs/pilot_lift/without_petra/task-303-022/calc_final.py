import numpy as np
from calc_icr import icr_line
import calc_enum as ce

for L in (12.5, 13.0, 13.5):
    Pn16, r0 = icr_line(L, ce.e, w=1/16, n=2000)
    print(f"L={L}: a={ce.e/L:.4f}  C={Pn16/L:.4f}  r0={r0:.3f}")
    c = ce.checks("A572_50", 5/16, 3, L)
    for k, v in c.items():
        print(f"   {k:18s} {v:.3f}")
    Pn = Pn16*3
    print(f"   weld Rn/Omega = {Pn/2:.2f} kip vs Va = {ce.V} kip")
