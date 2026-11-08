import math
from calc import evaluate, prying, sup, WT, Ta, Fu

tee, db, grp, g, rows, s, Lev = 'WT8x15_5', 0.75, 120, 3.5, 3, 2.5, 1.25
for mode in ('min', 's', 'trib'):
    res, geo, okg, wt, L, p, dt, ds = evaluate(tee, db, grp, g, rows, s, Lev, mode)
    print(mode, 'p=', round(p, 3), {k: round(v, 3) for k, v in res.items()})
print('geometry', geo, 'ok', okg)
print('tee length', L, 'weight lb', round(wt, 2))
print('tee prying detail', {k: round(v, 4) for k, v in dt.items()})
print('support prying detail', {k: round(v, 4) for k, v in ds.items()})

# bolt force including prying, Manual Part 9 (alpha from actual T)
B = 90*math.pi*db**2/4/2.0
T = Ta/(2*rows)
for name, t, tw in (('tee', WT[tee][1], WT[tee][2]), ('support', sup['tf'], sup['tw'])):
    b = (g-tw)/2; a = (5.53-g)/2
    bp = b-db/2; ap = min(a, 1.25*b)+db/2; rho = bp/ap; delta = 1-(db+1/16)/p
    treq0 = math.sqrt(1.67*4*T*bp/(p*Fu))   # thickness for no prying
    alpha = ((treq0/t)**2 - 1)/delta        # Thornton alpha from required strength
    alpha = max(0.0, min(1.0, alpha))
    q = T*(delta*alpha*rho/(1+delta*alpha))*(t/treq0)**2 if alpha > 0 else 0.0
    print(name, 'T', round(T, 3), 'B', round(B, 3), 'treq_no_prying', round(treq0, 3), 'alpha', round(alpha, 3),
          'q', round(q, 3), 'T+q', round(T+q, 3), 'util', round((T+q)/B, 3))

# p capped at 2b (conservative cap some references give)
b = (g-0.275)/2
p2b = min(p, 2*b)
u_cap = prying(T, B, 0.44, b, (5.53-g)/2, p2b, db)[0]
print('p cap 2b', round(2*b, 3), 'util', round(u_cap, 3))
