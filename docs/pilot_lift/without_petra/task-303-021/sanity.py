from ic import C_ic

for g in (3.0, 5.5, 6.0, 8.0):
    print("2x6 s3 e16 g", g, C_ic(6, 2, 3.0, g, 16.0), C_ic(6, 2, 3.0, g, 16.0, True))
# Table 7-6 one column, s = 3, e = 8
for n in range(2, 9):
    print("1col", n, round(C_ic(n, 1, 3.0, 0.0, 8.0)[0], 3), round(C_ic(n, 1, 3.0, 0.0, 8.0, True)[0], 3))
