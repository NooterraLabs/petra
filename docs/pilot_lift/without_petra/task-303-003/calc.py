import math
Ra = 15.843  # kip, ASD service
# Beam W16x26 A992
d, bf, tw, tf, kdes = 15.7, 5.5, 0.25, 0.345, 0.747
Fy, Fu, E = 50.0, 65.0, 29000.0
# Support W10x49 web A992
dc, bfc, twc, tfc, kc_det = 10.0, 10.0, 0.34, 0.56, 1.25
T = dc - 2*kc_det
# Seat L4x4x1/2 A36, 4 in outstanding leg, 6 in long
t, leg_out, leg_v, L, ka = 0.5, 4.0, 4.0, 6.0, 0.875
Fya, Fua = 36.0, 58.0
setback = 0.5; a = setback + 0.25
# Bolts: 2 x 3/4 A325-N (Group 120, threads included), one row, gauge 3.5
db, nb, g, Lev = 0.75, 2, 3.5, 2.0
Ab = math.pi*db**2/4; Fnv = 54.0; dh = db + 1/16

def wly(lb):  # J10-3 (within d of end), Omega 1.5
    return Fy*tw*(2.5*kdes + lb)/1.5
def wc(lb):   # J10-5a/b, Omega 2.0, Qf = 1
    base = 0.40*tw**2*math.sqrt(E*Fy*tf/tw)
    r = lb/d
    f = 3*r if r <= 0.2 else (4*r - 0.2)
    return base*(1 + f*(tw/tf)**1.5)/2.0

lb_avail = leg_out - a
lb_wly = max(0.0, Ra*1.5/(Fy*tw) - 2.5*kdes)
base = 0.40*tw**2*math.sqrt(E*Fy*tf/tw)/2.0
lb_wc = max(0.0, (Ra/base - 1)/(3*(tw/tf)**1.5)*d)
lb_req = max(kdes, lb_wly, lb_wc)
print(f"lb_avail {lb_avail:.3f}  lb_wly {lb_wly:.3f}  lb_wc {lb_wc:.3f}  lb_req {lb_req:.3f}")

res = {}
res['web_local_yielding (lb avail)'] = Ra/wly(lb_avail)
res['web_local_yielding (lb=k)'] = Ra/wly(kdes)
res['web_crippling (lb avail)'] = Ra/wc(lb_avail)
res['web_crippling (lb=k)'] = Ra/wc(kdes)
res['web_crippling (lb=0)'] = Ra/wc(0)
Mn_a = Fya*L*t**2/4/1.67
for name, lb in [('lb_req', lb_req), ('lb avail', lb_avail)]:
    e = a + lb/2 - (t + 0.375)
    res[f'seat_flexure Manual e=a+lb/2-(t+3/8) [{name}] e={e:.3f}'] = Ra*e/Mn_a if e > 0 else 0
    e2 = a + lb/2 - t
    res[f'seat_flexure variant e=a+lb/2-t [{name}] e={e2:.3f}'] = Ra*e2/Mn_a
res['seat shear_yield 0.6FyLt/1.5'] = Ra/(0.6*Fya*L*t/1.5)
res['bolts shear'] = Ra/(nb*Fnv*Ab/2.0)
lc_angle = Lev - dh/2
rn_angle = min(1.2*lc_angle*t*Fua, 2.4*db*t*Fua)
res['bearing angle'] = (Ra/nb)/(rn_angle/2.0)
res['bearing support web'] = (Ra/nb)/(2.4*db*twc*Fu/2.0)
for k, v in res.items():
    print(f"{v:6.3f}  {k}")
print("support T", T, "seat L", L, "clear between flanges", dc-2*tfc)
print("edge along length", (L-g)/2, "bolt from heel", leg_v-Lev, "socket clearance to out. leg face", leg_v-Lev-t)
print("bolt line to column flange inner face", (dc-2*tfc)/2 - g/2)
