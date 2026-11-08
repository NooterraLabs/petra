from icr import icr_C

for n in (2, 3):
    for s in (3.0, 3.25, 3.5, 4.0):
        row = []
        for e in (3.0, 3.25, 3.5):
            C, _ = icr_C([i * s for i in range(n)], [0] * n, e)
            row.append(f"e={e}: C={C:.3f}")
        print(n, s, "  ".join(row))
