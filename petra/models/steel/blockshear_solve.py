"""Untrusted solver for the block shear pilot (blockshear.py). It uses floats, numpy and
scipy's HiGHS, and every number it hands on is evidence the kernel checks (T4).

Two routes to evidence:

- Proof. An Airy stress function phi gives sigma_xx = phi_yy, sigma_yy = phi_xx and
  tau = -phi_xy, which satisfy equilibrium identically. On the statement's mesh, phi is a
  Hsieh-Clough-Tocher (HCT) C1 cubic on each macro triangle's Clough-Tocher split, so its
  stresses are linear on each micro triangle and their tractions are continuous across
  every edge. Free edges get phi = grad phi = 0. A hole's boundary values follow from its
  traction: grad phi is constant on a free edge, and grad phi = C - p x on a bearing edge,
  where p is the bolt's pressure. A loaded hole makes phi many-valued, so each column's
  line y = y_j, from its first hole to the held edge, is a branch cut: phi on the upper
  side is phi on the lower side plus an affine function, which keeps the stresses
  continuous. Any rational values of the remaining degrees of freedom then give a field
  that meets every equality row exactly. A linear program over those degrees of freedom
  finds the largest load factor; its rounded solution, scaled to J4.3's force, gives the
  exact feasible point.
- Refutation. The statement's own linear program, max lambda with the load row scaled by
  lambda, has optimum lambda* < 1. Its equality duals, normalised and rounded, form a
  Farkas ray whose margin is about 1 - lambda*.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as Q

import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog

from ...kernel import Interval, enclose
from ...kernel.rules.r1_linear import FarkasRay, FeasiblePoints
from . import blockshear as B

Form = dict
"""A linear form over the solver's variables: {variable: exact coefficient}."""


def _add(*forms: Form) -> Form:
    out: Form = {}
    for f in forms:
        for k, v in f.items():
            out[k] = out.get(k, 0) + v
    return {k: v for k, v in out.items() if v != 0}


def _scale(c, f: Form) -> Form:
    return {k: c * v for k, v in f.items()} if c != 0 else {}


def _dot(u, v):
    return u[0] * v[0] + u[1] * v[1]


# --- The HCT element -----------------------------------------------------------------------


def hct(V, phi, grad, edge, N):
    """Second derivatives (phi_xx, phi_xy, phi_yy) of the HCT interpolant at the three
    nodes of each micro triangle, in the mesh's micro order: for macro (V0, V1, V2) these
    are (V0, V1, G), (V1, V2, G), (V2, V0, G), G the centroid. `edge[i]` is
    grad phi . N[i] at the midpoint of edge i = (V[i+1], V[i+2]), N[i] normal to that edge.
    Works on any field of numbers: Fractions for evidence, floats for the program.

    Bernstein-Bezier form on each micro triangle: the edge and vertex ordinates follow
    from phi and grad phi at the vertices, the ordinate next to each edge's middle from
    the normal derivative there, and the inner ordinates from C1 across the micro edges
    (Farin's construction, as in Lai and Schumaker, Spline Functions on Triangulations,
    Section 6.1)."""
    third = 1 / Q(3) if isinstance(V[0][0], Q) else 1 / 3
    C = ((V[0][0] + V[1][0] + V[2][0]) * third, (V[0][1] + V[1][1] + V[2][1]) * third)
    near = [phi[m] + _dot(grad[m], (C[0] - V[m][0], C[1] - V[m][1])) * third for m in range(3)]
    sub_c, centres = [], []
    for i in range(3):
        P0, P1 = (i + 1) % 3, (i + 2) % 3
        c = {(3, 0, 0): phi[P0], (0, 3, 0): phi[P1]}
        E = (V[P1][0] - V[P0][0], V[P1][1] - V[P0][1])
        c[(2, 1, 0)] = phi[P0] + _dot(grad[P0], E) * third
        c[(1, 2, 0)] = phi[P1] - _dot(grad[P1], E) * third
        c[(2, 0, 1)], c[(0, 2, 1)] = near[P0], near[P1]
        M = ((V[P0][0] + V[P1][0]) / 2, (V[P0][1] + V[P1][1]) / 2)
        d = (C[0] - M[0], C[1] - M[1])
        n = N[i]
        alpha, beta = _dot(d, n) / _dot(n, n), _dot(d, E) / _dot(E, E)
        dt = 3 * ((c[(2, 1, 0)] - c[(3, 0, 0)]) / 4 + (c[(1, 2, 0)] - c[(2, 1, 0)]) / 2 + (c[(0, 3, 0)] - c[(1, 2, 0)]) / 4)
        D = alpha * edge[i] + beta * dt
        d200 = -c[(3, 0, 0)] / 2 - c[(2, 1, 0)] / 2 + c[(2, 0, 1)]
        d020 = -c[(1, 2, 0)] / 2 - c[(0, 3, 0)] / 2 + c[(0, 2, 1)]
        c[(1, 1, 1)] = 2 * (D * third - d200 / 4 - d020 / 4) + c[(2, 1, 0)] / 2 + c[(1, 2, 0)] / 2
        sub_c.append(c)
        centres.append(c[(1, 1, 1)])
    W = [(centres[(m - 1) % 3] + near[m] + centres[(m + 1) % 3]) * third for m in range(3)]
    cC = (W[0] + W[1] + W[2]) * third
    for i in range(3):
        c = sub_c[i]
        c[(1, 0, 2)], c[(0, 1, 2)], c[(0, 0, 3)] = W[(i + 1) % 3], W[(i + 2) % 3], cC
    out = [None, None, None]
    for i in range(3):
        P = [V[(i + 1) % 3], V[(i + 2) % 3], C]
        a2 = (P[1][0] - P[0][0]) * (P[2][1] - P[0][1]) - (P[2][0] - P[0][0]) * (P[1][1] - P[0][1])
        ux = [(P[1][1] - P[2][1]) / a2, (P[2][1] - P[0][1]) / a2, (P[0][1] - P[1][1]) / a2]
        uy = [(P[2][0] - P[1][0]) / a2, (P[0][0] - P[2][0]) / a2, (P[1][0] - P[0][0]) / a2]
        c = sub_c[i]

        def second(u, v, a):
            s = 0
            for j in range(3):
                for k in range(3):
                    e = [0, 0, 0]
                    e[a] += 1
                    e[j] += 1
                    e[k] += 1
                    s += u[j] * v[k] * c[tuple(e)]
            return 6 * s

        out[(i + 1) % 3] = [(second(ux, ux, a), second(ux, uy, a), second(uy, uy, a)) for a in range(3)]
    return out


# --- The Airy parametrisation --------------------------------------------------------------


@dataclass
class Airy:
    """Every macro triangle's 12 HCT values (phi, grad phi at its vertices, then the edge
    normal derivatives) as linear forms over `count` variables; the bolts' pressure
    variables; and the forms' coefficients exact."""

    local: list
    normals: list
    count: int
    pressure: list


def airy(pilot: B.Pilot) -> Airy:
    mesh = pilot.mesh
    pts = mesh.points
    where = {p: i for i, p in enumerate(pts)}
    count = 0

    def fresh(n: int) -> list[Form]:
        nonlocal count
        out = [{count + k: Q(1)} for k in range(n)]
        count += n
        return out

    ys = sorted({y for _, y in mesh.bolts})
    nv = len(B.HOLE_VERTICES)
    hole_ids = {}
    for b, (cx, cy) in enumerate(mesh.bolts):
        hole_ids[b] = [where[(cx + mesh.radius * vx, cy + mesh.radius * vy)] for vx, vy in B.HOLE_VERTICES]

    # Branch cuts: per column, from V0 of each hole to V8 of the next, and from the last to the held edge.
    segments = []          # (y, x_from, x_to, bolt_from)
    for j, y in enumerate(ys):
        column = [b for b, (_, yb) in enumerate(mesh.bolts) if yb == y]
        column.sort(key=lambda b: mesh.bolts[b][0])
        for i, b in enumerate(column):
            start = pts[hole_ids[b][0]][0]
            end = pts[hole_ids[column[i + 1]][nv // 2]][0] if i + 1 < len(column) else mesh.length
            segments.append((y, start, end, b))

    def segment_of(p) -> int | None:
        for s, (y, x0, x1, _) in enumerate(segments):
            if p[1] == y and x0 <= p[0] <= x1:
                return s
        return None

    macro_vertices = sorted({v for tri in mesh.macro for v in tri})
    hole_vertex = {}
    for b, ids in hole_ids.items():
        for k, v in enumerate(ids):
            hole_vertex[v] = (b, k)

    zero: Form = {}
    vertex = {}      # v -> {side: (phi, gx, gy)}, side in ("", "+", "-")
    jump = {}        # segment -> (alpha, beta, gamma) forms
    params = {b: fresh(4) for b in range(len(mesh.bolts))}   # a, Gx, Gy, p

    for v in macro_vertices:
        p = pts[v]
        if v in hole_vertex:
            continue
        if p[0] == 0 or p[1] == 0:
            vertex[v] = {"": (zero, zero, zero)}
        elif segment_of(p) is not None:
            vertex[v] = {"-": tuple(fresh(3))}
        else:
            vertex[v] = {"": tuple(fresh(3))}

    edges = {}
    for tri in mesh.macro:
        for a in range(3):
            u, w = tri[a], tri[(a + 1) % 3]
            edges.setdefault((min(u, w), max(u, w)), None)

    def normal(key):
        (x0, y0), (x1, y1) = pts[key[0]], pts[key[1]]
        return (y1 - y0, x0 - x1)

    edge = {}        # key -> {side: form}
    for key in edges:
        (x0, y0), (x1, y1) = pts[key[0]], pts[key[1]]
        if key in mesh.holes:
            continue
        if (x0 == 0 and x1 == 0) or (y0 == 0 and y1 == 0):
            edge[key] = {"": zero}
        elif y0 == y1 and segment_of(pts[key[0]]) is not None and segment_of(pts[key[0]]) == segment_of(pts[key[1]]):
            edge[key] = {"-": fresh(1)[0]}
        else:
            edge[key] = {"": fresh(1)[0]}

    def affine_at(J, p) -> Form:
        return _add(J[0], _scale(p[0], J[1]), _scale(p[1], J[2]))

    # Walk each hole counter-clockwise from V0 on the upper side, column by column.
    for j, y in enumerate(ys):
        incoming = None
        for s, (sy, _, _, b) in enumerate(segments):
            if sy != y:
                continue
            a, gx, gy, pr = params[b]
            ids = hole_ids[b]
            P = [pts[v] for v in ids] + [pts[ids[0]]]
            phi, g = [a], [(gx, gy)]
            mids = []
            for k in range(nv):
                key = (min(ids[k], ids[(k + 1) % nv]), max(ids[k], ids[(k + 1) % nv]))
                Nk = normal(key)
                M = ((P[k][0] + P[k + 1][0]) / 2, (P[k][1] + P[k + 1][1]) / 2)
                if k in B.BEARING:
                    Cx, Cy = _add(g[k][0], _scale(P[k][0], pr)), _add(g[k][1], _scale(P[k][1], pr))
                    g.append((_add(Cx, _scale(-P[k + 1][0], pr)), _add(Cy, _scale(-P[k + 1][1], pr))))
                    sq = (P[k + 1][0] ** 2 + P[k + 1][1] ** 2 - P[k][0] ** 2 - P[k][1] ** 2) / 2
                    phi.append(_add(phi[k], _scale(P[k + 1][0] - P[k][0], Cx), _scale(P[k + 1][1] - P[k][1], Cy), _scale(-sq, pr)))
                    gm = (_add(Cx, _scale(-M[0], pr)), _add(Cy, _scale(-M[1], pr)))
                else:
                    g.append(g[k])
                    phi.append(_add(phi[k], _scale(P[k + 1][0] - P[k][0], g[k][0]), _scale(P[k + 1][1] - P[k][1], g[k][1])))
                    gm = g[k]
                mids.append((key, _add(_scale(Nk[0], gm[0]), _scale(Nk[1], gm[1]))))
            half = nv // 2

            def lower(form_phi, form_g, p):
                if incoming is None:
                    return form_phi, form_g
                return (_add(form_phi, _scale(-1, affine_at(incoming, p))),
                        (_add(form_g[0], _scale(-1, incoming[1])), _add(form_g[1], _scale(-1, incoming[2]))))

            for k in range(nv + 1):
                v = ids[k % nv]
                upper_side = k <= half
                lower_side = k >= half
                slot = vertex.setdefault(v, {})
                if upper_side:
                    side = "+" if (k == 0 or (k == half and incoming is not None)) else ""
                    slot[side] = (phi[k], g[k][0], g[k][1])
                if lower_side:
                    lp, lg = lower(phi[k], g[k], P[k])
                    side = "-" if (k == nv or (k == half and incoming is not None)) else ""
                    if side == "" and k == half:
                        continue
                    slot[side] = (lp, lg[0], lg[1])
            for k, (key, form) in enumerate(mids):
                if k < half or incoming is None:
                    edge[key] = {"": form}
                else:
                    edge[key] = {"": _add(form, _scale(-1, _add(_scale(normal(key)[0], incoming[1]), _scale(normal(key)[1], incoming[2]))))}
            # The outgoing jump: upper minus lower at V0, an affine function.
            lp, lg = lower(phi[nv], g[nv], P[0])
            beta, gamma = _add(gx, _scale(-1, lg[0])), _add(gy, _scale(-1, lg[1]))
            value = _add(a, _scale(-1, lp))
            alpha = _add(value, _scale(-P[0][0], beta), _scale(-P[0][1], gamma))
            jump[s] = (alpha, beta, gamma)
            incoming = jump[s]

    # Upper copies of cut vertices and cut edges.
    for v, slot in vertex.items():
        if "-" in slot and "+" not in slot:
            s = segment_of(pts[v])
            J = jump[s]
            ph, gx, gy = slot["-"]
            slot["+"] = (_add(ph, affine_at(J, pts[v])), _add(gx, J[1]), _add(gy, J[2]))
    for key, slot in edge.items():
        if "-" in slot and "+" not in slot:
            J = jump[segment_of(pts[key[0]])]
            Nk = normal(key)
            slot["+"] = _add(slot["-"], _scale(Nk[0], J[1]), _scale(Nk[1], J[2]))

    local, normals = [], []
    for tri in mesh.macro:
        cy = sum(pts[v][1] for v in tri) / 3

        def pick(slot, p):
            if "" in slot:
                return slot[""]
            return slot["+"] if cy > p[1] else slot["-"]

        vals = [pick(vertex[v], pts[v]) for v in tri]
        keys = [(min(tri[(i + 1) % 3], tri[(i + 2) % 3]), max(tri[(i + 1) % 3], tri[(i + 2) % 3])) for i in range(3)]
        eds = [pick(edge[k], pts[k[0]]) for k in keys]
        local.append([vals[0][0], vals[1][0], vals[2][0], vals[0][1], vals[0][2], vals[1][1], vals[1][2],
                      vals[2][1], vals[2][2], eds[0], eds[1], eds[2]])
        normals.append([normal(k) for k in keys])
    return Airy(local, normals, count, [params[b][3] for b in range(len(mesh.bolts))])


def _local_stresses(V, N, values):
    """Stresses (sxx, syy, tau) at the 9 micro corners of one macro triangle, from its 12
    HCT values in Airy's order."""
    phi = values[0:3]
    grad = [(values[3], values[4]), (values[5], values[6]), (values[7], values[8])]
    out = []
    for micro in hct(V, phi, grad, values[9:12], N):
        for xx, xy, yy in micro:
            out.append((yy, xx, -xy))
    return out


def stress_matrix(pilot: B.Pilot, field: Airy) -> sp.csr_matrix:
    """The float map from Airy's variables to the stresses at every corner, in the
    statement's corner order (macro m gives micro triangles 3m..3m+2)."""
    rows, cols, vals = [], [], []
    pts = pilot.mesh.points
    for m, tri in enumerate(pilot.mesh.macro):
        V = [(float(pts[v][0]), float(pts[v][1])) for v in tri]
        N = [(float(n[0]), float(n[1])) for n in field.normals[m]]
        basis = []
        for l in range(12):
            unit = [0.0] * 12
            unit[l] = 1.0
            basis.append(_local_stresses(V, N, unit))
        for corner in range(9):
            for comp in range(3):
                r = 3 * (9 * m + corner) + comp
                acc: dict = {}
                for l in range(12):
                    w = basis[l][corner][comp]
                    if w != 0.0:
                        for var, coeff in field.local[m][l].items():
                            acc[var] = acc.get(var, 0.0) + w * float(coeff)
                for var, w in acc.items():
                    if w != 0.0:
                        rows.append(r)
                        cols.append(var)
                        vals.append(w)
    return sp.csr_matrix((vals, (rows, cols)), shape=(3 * pilot.corners, field.count))


def exact_stresses(pilot: B.Pilot, field: Airy, z: list[Q]) -> list[tuple[Q, Q, Q]]:
    pts = pilot.mesh.points
    out = []
    for m, tri in enumerate(pilot.mesh.macro):
        values = [sum((c * z[k] for k, c in form.items()), Q(0)) for form in field.local[m]]
        out += _local_stresses([pts[v] for v in tri], field.normals[m], values)
    return out


# --- The programs ----------------------------------------------------------------------------


@dataclass
class Bound:
    """The largest load factor a program found, as a multiple of J4.3's force, and what the
    evidence needs."""

    factor: float
    z: np.ndarray | None = None
    y: np.ndarray | None = None


def _box(pilot: B.Pilot) -> dict:
    return {h.sym: Interval(h.lo, h.hi) for h in pilot.statement.hyps}


def _sigma0(pilot: B.Pilot) -> Q:
    return pilot.flow.factor * (pilot.claim.fy if pilot.flow.prop == "fy" else pilot.claim.fu)


def airy_program(pilot: B.Pilot, field: Airy, S: sp.csr_matrix | None = None) -> Bound:
    """max lambda over the Airy variables: the yield rows at every corner, the moment row,
    and the bolts' forces summing to lambda times J4.3's force. Stresses in units of
    sigma0, so every number is near one."""
    S = stress_matrix(pilot, field) if S is None else S
    nz, nc = field.count, pilot.corners
    nsig, nrho = 3 * nc, nc
    total = nz + nsig + nrho + 1
    sig0, rho0, lam = nz, nz + nsig, nz + nsig + nrho
    # Equalities: S z - sigma = 0; load; moment.
    eq = [sp.hstack([S, -sp.identity(nsig, format="csr"), sp.csr_matrix((nsig, nrho + 1))])]
    width = float(pilot.mesh.width)
    force = float(pilot.claim.force / _sigma0(pilot))
    load = sp.lil_matrix((1, total))
    for f in field.pressure:
        (var, _), = f.items()
        load[0, var] = width
    load[0, lam] = -force
    eq.append(load.tocsr())
    ys = [y for _, y in pilot.mesh.bolts]
    centroid = sum(ys) / len(ys)
    if any(y != centroid for y in ys):
        moment = sp.lil_matrix((1, total))
        for f, y in zip(field.pressure, ys):
            (var, _), = f.items()
            moment[0, var] = float(y - centroid)
        eq.append(moment.tocsr())
    A_eq = sp.vstack(eq).tocsr()
    b_eq = np.zeros(A_eq.shape[0])
    rows, cols, vals, rhs = [], [], [], []
    r = 0
    for c in range(nc):
        for y in pilot.table(c):
            for col, v in ((sig0 + 3 * c, y.sxx), (sig0 + 3 * c + 1, y.syy), (sig0 + 3 * c + 2, y.txy), (rho0 + c, y.rho)):
                if v != 0:
                    rows.append(r)
                    cols.append(col)
                    vals.append(float(v))
            rhs.append(float(y.rhs))
            r += 1
    A_ub = sp.csr_matrix((vals, (rows, cols)), shape=(r, total))
    bounds = [(None, None)] * nz + [(None, None)] * nsig + [(0, None)] * nrho + [(0, None)]
    for f in field.pressure:
        (var, _), = f.items()
        bounds[var] = (0, None)
    c = np.zeros(total)
    c[lam] = -1
    res = linprog(c, A_ub=A_ub, b_ub=np.array(rhs), A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs-ipm")
    if res.status != 0:
        raise RuntimeError(f"the Airy program failed: {res.message}")
    return Bound(float(res.x[lam]), z=res.x[:nz])


def statement_program(pilot: B.Pilot) -> Bound:
    """max lambda over the statement itself, its load row scaled by lambda, in units of
    sigma0. The equality duals give the Farkas ray when lambda < 1."""
    goal = pilot.statement.goal
    box = _box(pilot)
    s0 = float(_sigma0(pilot))
    entries = goal.A.entries
    A = sp.csr_matrix(([float(v) for _, _, v in entries], ([i for i, _, _ in entries], [j for _, j, _ in entries])),
                      shape=(goal.A.rows, goal.A.cols))
    b = np.array([float(enclose(e, box).lo) for e in goal.b]) / s0
    lo = [float(enclose(e, box).lo) / s0 for e in goal.lower]
    hi = [float(enclose(e, box).lo) / s0 for e in goal.upper]
    d = np.zeros(goal.A.rows)
    d[pilot.load_row] = b[pilot.load_row]
    rest = b.copy()
    rest[pilot.load_row] = 0
    A_l = sp.hstack([A, sp.csr_matrix(-d.reshape(-1, 1))]).tocsr()
    c = np.zeros(goal.A.cols + 1)
    c[-1] = -1
    res = linprog(c, A_eq=A_l, b_eq=rest, bounds=list(zip(lo, hi)) + [(0, None)], method="highs-ipm")
    if res.status != 0:
        raise RuntimeError(f"the statement's program failed: {res.message}")
    return Bound(float(res.x[-1]), y=np.asarray(res.eqlin.marginals))


# --- Evidence -------------------------------------------------------------------------------


def _dyadic(v: float, bits: int) -> Q:
    return Q(round(v * (1 << bits)), 1 << bits)


def feasible_points(pilot: B.Pilot, field: Airy, z: np.ndarray, bits: int = 48) -> FeasiblePoints | None:
    """Round the Airy program's solution, scale it to J4.3's force exactly, and fill in rho
    and the slacks. None when the rounded field leaves the yield surface."""
    zq = [_dyadic(float(v), bits) for v in z]
    ys = [y for _, y in pilot.mesh.bolts]
    pvars = [next(iter(f)) for f in field.pressure]
    for var in pvars:
        zq[var] = max(zq[var], Q(0))
    centroid = sum(ys) / len(ys)
    arms = [y - centroid for y in ys]
    if any(arms):
        pivot = max((k for k in range(len(arms)) if arms[k] != 0), key=lambda k: zq[pvars[k]])
        rest = sum(arms[k] * zq[pvars[k]] for k in range(len(arms)) if k != pivot)
        zq[pvars[pivot]] = -rest / arms[pivot]
        if zq[pvars[pivot]] < 0:
            return None
    carried = pilot.mesh.width * sum(zq[v] for v in pvars)
    if carried <= 0:
        return None
    scale = pilot.claim.force / carried
    zq = [scale * v for v in zq]
    stresses = exact_stresses(pilot, field, zq)
    sigma0 = _sigma0(pilot)
    x = [Q(0)] * pilot.statement.goal.A.cols
    shear_rows = B.YIELD[:len(B.SHEAR_CIRCLE)]
    for c, (sxx, syy, txy) in enumerate(stresses):
        table = pilot.table(c)
        x[3 * c], x[3 * c + 1], x[3 * c + 2] = sxx, syy, txy
        rho = max([Q(0)] + [(y.sxx * sxx + y.syy * syy + y.txy * txy) / -y.rho for y in shear_rows])
        x[pilot.rho + c] = rho
        for r, y in enumerate(table):
            slack = y.rhs * sigma0 - (y.sxx * sxx + y.syy * syy + y.txy * txy + y.rho * rho)
            if slack < 0:
                return None
            x[pilot.slack + c * len(B.YIELD) + r] = slack
    for k, var in enumerate(pvars):
        x[pilot.pressure + k] = zq[var]
    vertices = 1 << len({h.sym for h in pilot.statement.hyps if h.sym in _b_syms(pilot)})
    point = tuple(x)
    return FeasiblePoints(tuple(point for _ in range(vertices)))


def _b_syms(pilot: B.Pilot) -> set[str]:
    from ...kernel import free_syms
    return set(free_syms(pilot.statement.goal.b))


def farkas_ray(pilot: B.Pilot, y: np.ndarray, bits: int = 48) -> FarkasRay:
    """The statement program's equality duals, oriented so y . b_load > 0, rounded."""
    goal = pilot.statement.goal
    box = _box(pilot)
    b_load = float(enclose(goal.b[pilot.load_row], box).lo)
    if y[pilot.load_row] * b_load < 0:
        y = -y
    peak = float(np.max(np.abs(y))) or 1.0
    y = y / peak
    y[np.abs(y) < 1e-13] = 0.0
    point = tuple((h.sym, h.lo) for h in pilot.statement.hyps)
    return FarkasRay(point, tuple(_dyadic(float(v), bits) for v in y))
