#!/usr/bin/env python3
"""Make a clearance certificate that check_clearance.py accepts.

    python make_cert.py PARTS.json FACETS OUT.json [--holes auto|all] [--aim] [--claim C] [--force]

PARTS.json is {"A": [solid, ...], "B": [solid, ...]} in the checker's part format.
FACETS is the number of flat faces put on every round face.

How it works

1. Hints. Each bar gets FACETS tangent sides, each open hole an inscribed polygon with FACETS
   corners. The directions are exact rational points of the unit circle: w_k near
   exp(i pi k / N), corners w_k^2, normals w_k w_(k+1). So a side of a bar is exactly parallel
   to an edge of a coaxial hole, and h = R holds with equality.
2. Float. For each pair of pieces, scipy's nnls solves
       least |sum lam_i g_i|^2  with  sum lam_i g_i + sum kap_j k_j = 0,  h.lam + m.kap = -gap
   by penalty. Only the support (which faces carry weight) is taken from it.
3. Exact. On that support the weights that cancel are the null space of a small rational
   matrix. In that null space the best ratio gap^2 / |n|^2 has a closed form, t = H^-1 c.
   All in fractions, so the two sides cancel exactly by construction, with nothing rounded.
   When that fails there are three fallbacks, in `pair_witness`. Each still solves the
   cancelling exactly, and gives away a little of the gap instead.
4. A piece with no point at all (two holes' cuts that face away from each other) gets a
   witness with n = 0, found once and used for every pair it is in.
5. The clearance written is the least over the pairs of gap / |n|, rounded down to a rational
   (exact when that least is itself rational).

--holes auto leaves a hole filled (null) unless its plug comes nearer the other part than the
clearance reached without it. --holes all opens every hole, which shows the growth in pieces.
--aim adds to each bar a few sides that squarely face the other part (see `aim`).
--claim C writes the certificate with clearance C, and writes nothing when C cannot be shown,
unless --force is given (for negative controls).

Exit status: 0 a file was written, 1 no certificate, 2 bad arguments.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import sys
import time
from fractions import Fraction as Q
from math import gcd, isqrt

import numpy as np
from scipy.optimize import linprog, nnls

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_clearance import pieces  # noqa: E402  the exact order of pieces and faces

PENALTY = 1.0e4
DENOM = 10 ** 6          # the bound on the denominator of tan(angle / 2) for circle points


# ---------------------------------------------------------------- exact rational helpers

def js(q: Q):
    """A fraction as the checker reads it back: an int, or a string p/q."""
    q = Q(q)
    return int(q) if q.denominator == 1 else f"{q.numerator}/{q.denominator}"


def cmul(a, b):
    return (a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0])


def circle_units(N: int, denom: int = DENOM):
    """w[k] near exp(i pi k / N) for k = 0..N, each exactly on the unit circle, w[N] = -w[0].

    For even N, w[k + N/2] = i w[k] exactly. Then corner k + N/2 is exactly opposite corner k,
    and normal k + N/2 exactly opposite normal k."""
    def near(f: Q):
        """A rational point of the unit circle near the angle f pi, for 0 <= f <= 1."""
        flip = f > Q(1, 2)
        if flip:
            f = 1 - f                     # (c, s) -> (-c, s)
        swap = f > Q(1, 4)
        if swap:
            f = Q(1, 2) - f               # (c, s) -> (s, c)
        t = Q(math.tan(float(f) * math.pi / 2)).limit_denominator(denom)
        c, s = (1 - t * t) / (1 + t * t), 2 * t / (1 + t * t)
        if swap:
            c, s = s, c
        if flip:
            c = -c
        return (c, s)

    if N % 2 == 0:
        first = [near(Q(k, N)) for k in range(N // 2)]
        out = first + [(-s, c) for c, s in first]
    else:
        out = [near(Q(k, N)) for k in range(N)]
    out.append((-out[0][0], -out[0][1]))
    return out


def nullspace(cols, with_free=False):
    """A basis of {w : sum_i w_i cols[i] = 0}, cols a list of 3-vectors of fractions.

    Basis vector k is 1 at the free column free[k] and 0 at the other free columns."""
    s = len(cols)
    M = [[cols[j][r] for j in range(s)] for r in range(3)]
    pivots, row = [], 0
    for col in range(s):
        p = next((r for r in range(row, 3) if M[r][col] != 0), None)
        if p is None:
            continue
        M[row], M[p] = M[p], M[row]
        inv = 1 / M[row][col]
        M[row] = [x * inv for x in M[row]]
        for r in range(3):
            if r != row and M[r][col] != 0:
                f = M[r][col]
                M[r] = [x - f * y for x, y in zip(M[r], M[row])]
        pivots.append(col)
        row += 1
        if row == 3:
            break
    free = [c for c in range(s) if c not in pivots]
    basis = []
    for fc in free:
        w = [Q(0)] * s
        w[fc] = Q(1)
        for r, pc in enumerate(pivots):
            w[pc] = -M[r][fc]
        basis.append(w)
    return (basis, free) if with_free else basis


def solve(H, c):
    """Solve H t = c exactly, or None when H is singular."""
    r = len(c)
    M = [list(H[i]) + [c[i]] for i in range(r)]
    for col in range(r):
        p = next((i for i in range(col, r) if M[i][col] != 0), None)
        if p is None:
            return None
        M[col], M[p] = M[p], M[col]
        inv = 1 / M[col][col]
        M[col] = [x * inv for x in M[col]]
        for i in range(r):
            if i != col and M[i][col] != 0:
                f = M[i][col]
                M[i] = [x - f * y for x, y in zip(M[i], M[col])]
    return [M[i][r] for i in range(r)]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def exact_on_support(Pf, Qf, SP, SQ):
    """The best exact witness whose weights sit on the faces SP of P and SQ of Q.

    Returns (mu, nu, gap, nn) with integer weights, or None when the support gives none."""
    SP, SQ = list(SP), list(SQ)
    while True:
        cols = [Pf[i][0] for i in SP] + [Qf[j][0] for j in SQ]
        c = [-Pf[i][1] for i in SP] + [-Qf[j][1] for j in SQ]
        s, sp = len(cols), len(SP)
        if s == 0:
            return None
        Z = nullspace(cols)
        if not Z:
            return None

        def nvec(w):
            return [sum(w[a] * cols[a][k] for a in range(sp)) for k in range(3)]

        if len(Z) == 1:
            w = Z[0]
            if sum(w) < 0:
                w = [-x for x in w]
        else:
            AZ = [nvec(z) for z in Z]
            H = [[dot(a, b) for b in AZ] for a in AZ]
            t = solve(H, [dot(c, z) for z in Z])
            if t is None:
                return None
            w = [sum(t[a] * Z[a][i] for a in range(len(Z))) for i in range(s)]
        worst = min(range(s), key=lambda i: w[i])
        if w[worst] < 0:
            # the free optimum leaves the cone: drop the worst face and try again
            if worst < sp:
                SP.pop(worst)
            else:
                SQ.pop(worst - sp)
            continue
        gap, n = dot(c, w), nvec(w)
        nn = dot(n, n)
        if gap < 0 or (nn == 0 and gap <= 0):
            return None
        return whole(SP, SQ, w, gap, nn)


# ---------------------------------------------------------------- the float stage

class Piece:
    def __init__(self, faces):
        self.faces = faces
        G = np.array([[float(x) for x in g] for g, _ in faces])
        h = np.array([float(hh) for _, hh in faces])
        norm = np.linalg.norm(G, axis=1)
        norm[norm == 0] = 1.0
        self.G, self.h, self.norm = G / norm[:, None], h / norm, norm
        self.empty = None                 # exact weights showing the piece has no point, when it has none


def float_pair(P: Piece, Qp: Piece, origin):
    """Float weights for the nearest approach of two pieces: (lam, kap, distance or None).

    Least squares over weights >= 0 of three things at once: eps |n|, PENALTY times how far the
    two sides are from cancelling, and PENALTY times (gap - 1). With the gap held at 1, |n| is
    1 / distance, so eps is set to the distance found so far and eps |n| stays near 1. With
    eps = 1 throughout, two pieces 0.004 apart were taken to collide, and two blocks 1e-9 apart
    drew no weights at all."""
    nP, nQ = len(P.h), len(Qp.h)
    hP, hQ = P.h - P.G @ origin, Qp.h - Qp.G @ origin
    A = np.zeros((7, nP + nQ))
    A[3:6, :nP] = PENALTY * P.G.T
    A[3:6, nP:] = PENALTY * Qp.G.T
    A[6, :nP] = PENALTY * hP
    A[6, nP:] = PENALTY * hQ
    b = np.zeros(7)
    b[6] = -PENALTY
    eps, lam, kap, good = 1.0, None, None, None
    for _ in range(7):
        A[0:3, :nP] = eps * P.G.T
        try:
            w, _ = nnls(A, b, maxiter=50 * (nP + nQ))
        except RuntimeError:
            return None, None, None
        lam, kap = w[:nP], w[nP:]
        n = P.G.T @ lam
        cancel = n + Qp.G.T @ kap
        gap = -(hP @ lam + hQ @ kap)
        nn = float(np.linalg.norm(n))
        size = max(float(np.abs(w).max()), 1e-300)
        if gap < 0.5 or np.linalg.norm(cancel) > 1e-5 * size:
            if good is not None:
                break                     # the pass before was sound: keep it
            eps *= 1e-3                   # |n| weighed too much, or the pieces meet: try with less
            continue
        good = (lam, kap, math.inf if nn < 1e-9 * gap else gap / nn)
        if eps * nn <= 4.0:
            break
        eps = gap / nn                    # the distance, as far as it is known
    if good is None:
        return lam, kap, None             # no plane found between them: they meet, or nearly
    return good


def support(lam, kap, rel=1e-13):
    """The faces that carry weight, judged against the largest weight of either side."""
    top = max(float(lam.max()) if len(lam) else 0.0, float(kap.max()) if len(kap) else 0.0)
    if top <= 0:
        return [], []
    return [i for i in range(len(lam)) if lam[i] > rel * top], [j for j in range(len(kap)) if kap[j] > rel * top]


def round_on_support(Pf, Qf, SP, SQ, wP, wQ):
    """Exact weights near the float ones: round the free weights, solve the rest exactly.

    The null space of the support's normals is exact, so whatever is rounded, the sides cancel."""
    SP, SQ = list(SP), list(SQ)
    cols = [Pf[i][0] for i in SP] + [Qf[j][0] for j in SQ]
    c = [-Pf[i][1] for i in SP] + [-Qf[j][1] for j in SQ]
    s, sp = len(cols), len(SP)
    Z, free = nullspace(cols, with_free=True)
    if not Z:
        return None
    wf = [float(x) for x in wP] + [float(x) for x in wQ]
    top = max(wf)
    w = [Q(0)] * s
    for z, fc in zip(Z, free):
        t = Q(wf[fc] / top).limit_denominator(10 ** 9)
        w = [a + t * b for a, b in zip(w, z)]
    if any(x < 0 for x in w):
        return None
    n = [sum(w[a] * cols[a][k] for a in range(sp)) for k in range(3)]
    gap, nn = dot(c, w), dot(n, n)
    if gap < 0 or (nn == 0 and gap <= 0):
        return None
    return whole(SP, SQ, w, gap, nn)


def whole(SP, SQ, w, gap, nn):
    """The same witness on a handier scale.

    Whole numbers with no common factor when those are short. Otherwise each weight over the
    largest, so that |n| stays near 1: the checker turns |n|^2 into a float for its report, and
    that overflows on whole numbers of 150 digits (see exhibit_overflow.py)."""
    sp, s = len(SP), len(w)
    den = 1
    for x in w:
        den = den * x.denominator // gcd(den, x.denominator)
    ints = [int(x * den) for x in w]
    g = 0
    for x in ints:
        g = gcd(g, x)
    g = g or 1
    if max(ints) // g < 10 ** 30:
        scale = Q(den, g)
        out = [Q(x // g) for x in ints]
    else:
        scale = 1 / max(w)
        out = [x * scale for x in w]
    mu = [(SP[a], out[a]) for a in range(sp) if out[a]]
    nu = [(SQ[a - sp], out[a]) for a in range(sp, s) if out[a]]
    return mu, nu, gap * scale, nn * scale * scale


def empty_proof(P: Piece, origin):
    """Exact weights mu >= 0 with sum mu g = 0 and sum mu h < 0: the piece has no point. Or None."""
    hP = P.h - P.G @ origin
    A = np.vstack([P.G.T, hP[None, :]])
    try:
        w, rnorm = nnls(A, np.array([0.0, 0.0, 0.0, -1.0]))
    except RuntimeError:
        return None
    if rnorm > 1e-9:
        return None
    S, _ = support(w, np.zeros(0))
    out = exact_on_support(P.faces, [], S, [])
    if out is None:
        out = round_on_support(P.faces, [], S, [], w[S] / P.norm[S], [])
    return out


def exact_support(P: Piece, n, origin):
    """Exact weights mu >= 0 on the faces of P with sum mu g = n, for a rational n, and their sum mu h.

    The least sum mu h sits on at most three faces. A float linear program finds the point of P
    furthest along n. The eight faces nearest that point are the candidates (all the faces, when P
    has nine or fewer), and every one, two or three of them is solved exactly. Whatever set wins,
    the weights are a true bound on n . x over P: only how tight it is rests on the float guess."""
    nf = np.array([float(x) for x in n])
    count = len(P.faces)
    if count <= 9:
        cand = list(range(count))
    else:
        res = linprog(-nf, A_ub=P.G, b_ub=P.h - P.G @ origin, bounds=[(None, None)] * 3, method="highs-ds")
        if res.status != 0:
            return None
        slack = (P.h - P.G @ origin) - P.G @ res.x
        cand = [int(i) for i in np.argsort(np.abs(slack))[:8]]
    minus = tuple(-x for x in n)
    best = None
    for k in (1, 2, 3):
        for trio in itertools.combinations(cand, k):
            Z = nullspace([P.faces[i][0] for i in trio] + [minus])
            if len(Z) != 1 or Z[0][-1] == 0:
                continue
            w = [x / Z[0][-1] for x in Z[0][:-1]]
            if any(x < 0 for x in w):
                continue
            a = sum(x * P.faces[i][1] for i, x in zip(trio, w))
            if best is None or a < best[0]:
                best = (a, [(i, x) for i, x in zip(trio, w) if x])
    return best


def by_direction(P: Piece, Qp: Piece, lam, kap, origin):
    """A witness whose direction is taken exactly from one side's float support.

    For the float stage a face of one piece and an edge of the other can look parallel when they
    are off by 1e-12, and then no weights on that support cancel exactly. Here the direction n is
    built from one side's own faces, with its float weights rounded, so that side holds by
    construction. The other side gets exact weights for that same n from `exact_support`.
    Both ways round are tried and the better kept."""
    SP, SQ = support(lam, kap)
    top = max(float(lam.max()), float(kap.max()))
    best = None
    for first in ("P", "Q"):
        X, S, w = (P, SP, lam) if first == "P" else (Qp, SQ, kap)
        if not S:
            continue
        own = [(i, Q(float(w[i]) / float(X.norm[i]) / top).limit_denominator(10 ** 9)) for i in S]
        own = [(i, x) for i, x in own if x > 0]
        v = [sum(x * X.faces[i][0][k] for i, x in own) for k in range(3)]      # +n from P's faces, -n from Q's
        if all(x == 0 for x in v):
            continue
        other = exact_support(Qp if first == "P" else P, [-x for x in v], origin)
        if other is None:
            continue
        mu, nu = (own, other[1]) if first == "P" else (other[1], own)
        gap = -sum(x * Qp.faces[j][1] for j, x in nu) - sum(x * P.faces[i][1] for i, x in mu)
        nn = dot(v, v)
        if gap < 0:
            continue
        if best is None or gap * gap * best[3] > best[2] * best[2] * nn:
            best = (mu, nu, gap, nn)
    return best


def near_faces(P: Piece, S, origin, tol=1e-7):
    """The faces of P that pass through the point where the faces S meet (least squares)."""
    if not S:
        return []
    G, h = P.G[S], P.h[S] - P.G[S] @ origin
    x = np.linalg.lstsq(G, h, rcond=None)[0]
    slack = (P.h - P.G @ origin) - P.G @ x
    return [i for i in range(len(slack)) if abs(slack[i]) < tol]


def pair_witness(P: Piece, Qp: Piece, origin):
    """(float distance, exact witness or None, how it was found)."""
    if P.empty is not None:
        mu, _, gap, nn = P.empty
        return math.inf, (mu, [], gap, nn), "a is empty"
    if Qp.empty is not None:
        mu, _, gap, nn = Qp.empty
        return math.inf, ([], mu, gap, nn), "b is empty"
    lam, kap, d = float_pair(P, Qp, origin)
    if lam is None:
        return None, None, "meet"
    SP, SQ = support(lam, kap)
    # the exact solve is the judge: a witness it returns is a proof, whatever the float stage thought
    out = exact_on_support(P.faces, Qp.faces, SP, SQ)
    if out is not None:
        return d, out, "support" if d is not None else "support, float unsure"
    out = round_on_support(P.faces, Qp.faces, SP, SQ, lam[SP] / P.norm[SP], kap[SQ] / Qp.norm[SQ])
    if out is not None:
        return d, out, "rounded"
    if d is None:
        return None, None, "meet"
    # last try: every face through the two nearest points, pruned by the exact solve
    out = exact_on_support(P.faces, Qp.faces, near_faces(P, SP, origin), near_faces(Qp, SQ, origin))
    if out is not None:
        return d, out, "near"
    out = by_direction(P, Qp, lam, kap, origin)
    if out is not None:
        return d, out, "direction"
    return d, None, "failed"


# ---------------------------------------------------------------- hints

def holes_of(solids):
    return [(si, hi) for si, s in enumerate(solids) if s["kind"] == "box" for hi in range(len(s.get("holes", [])))]


def make_hints(solids, N, opened, units, extra=None):
    """extra: {index of a cylinder: [unit normals of further sides]}"""
    corners = [cmul(units[k], units[k]) for k in range(N)]
    normals = [cmul(units[k], units[k + 1]) for k in range(N)]
    hints = []
    for si, s in enumerate(solids):
        if s["kind"] == "cylinder":
            R = Q(s["radius"])
            more = (extra or {}).get(si, [])
            hints.append({"sides": [[js(c), js(sn), js(R)] for c, sn in normals + more]})
        elif s["kind"] == "box":
            polys = []
            for hi, hole in enumerate(s.get("holes", [])):
                if (si, hi) in opened:
                    R = Q(hole["radius"])
                    cu, cv = (Q(x) for x in hole["centre"])
                    polys.append([[js(cu + R * c), js(cv + R * sn)] for c, sn in corners])
                else:
                    polys.append(None)
            hints.append({"holes": polys})
        else:
            hints.append(None)
    return hints


def plug(solid, hole, N):
    """The material that filling a hole adds, as one float piece: a prism around it, cut by the block."""
    AX = {"z": (0, 1, 2), "x": (1, 2, 0), "y": (2, 0, 1)}
    iu, iv, _ = AX[hole["axis"]]
    faces = []
    for k in range(3):
        g = [Q(0)] * 3
        g[k] = Q(-1)
        faces.append((tuple(g), -Q(solid["lo"][k])))
        g = [Q(0)] * 3
        g[k] = Q(1)
        faces.append((tuple(g), Q(solid["hi"][k])))
    R = float(Q(hole["radius"]))
    cu, cv = (float(Q(x)) for x in hole["centre"])
    for k in range(N):
        a = math.pi * (2 * k + 1) / N
        g = [0.0, 0.0, 0.0]
        g[iu], g[iv] = math.cos(a), math.sin(a)
        faces.append((tuple(g), R + g[iu] * cu + g[iv] * cv))
    return Piece(faces)


# ---------------------------------------------------------------- the whole certificate

def root_down(x: Q, bits: int = 64) -> Q:
    """The largest fraction with denominator 2^bits whose square is at most x, or the exact root."""
    num, den = x.numerator, x.denominator
    rn, rd = isqrt(num), isqrt(den)
    if rn * rn == num and rd * rd == den:
        return Q(rn, rd)
    return Q(isqrt((num << (2 * bits)) // den), 1 << bits)


def float_least(A, B, origin):
    least = math.inf
    for P in A:
        for Qp in B:
            d = float_pair(P, Qp, origin)[2]
            if d is None:
                return 0.0
            least = min(least, d)
    return least


def choose_holes(parts, N, units, origin, log):
    """Open only the holes whose plugs come nearer the other part than the clearance reached."""
    opened = {"A": set(), "B": set()}
    while True:
        P = {s: [Piece(f) for f in pieces(parts[s], make_hints(parts[s], N, opened[s], units))] for s in "AB"}
        c = float_least(P["A"], P["B"], origin)
        add = []
        for s, o in (("A", "B"), ("B", "A")):
            for si, hi in holes_of(parts[s]):
                if (si, hi) in opened[s]:
                    continue
                pg = plug(parts[s][si], parts[s][si]["holes"][hi], max(N, 16))
                d = float_least([pg], P[o], origin)
                if d <= c * (1 + 1e-9) + 1e-12:
                    add.append((s, si, hi, d))
        if not add:
            return opened
        for s, si, hi, d in add:
            log(f"  open hole {hi} of solid {si} of part {s}: its plug is {d:.6f} from the other part, the clearance so far {c:.6f}")
            opened[s].add((si, hi))


def bounds_centre(parts):
    """A point near the parts, for the float stage only."""
    pts = []
    for s in "AB":
        for solid in parts[s]:
            if solid["kind"] == "box":
                pts.append([(float(Q(a)) + float(Q(b))) / 2 for a, b in zip(solid["lo"], solid["hi"])])
            elif solid["kind"] == "cylinder":
                iu, iv, it = {"z": (0, 1, 2), "x": (1, 2, 0), "y": (2, 0, 1)}[solid["axis"]]
                p = [0.0] * 3
                p[iu], p[iv] = (float(Q(x)) for x in solid["centre"])
                p[it] = (float(Q(solid["lo"])) + float(Q(solid["hi"]))) / 2
                pts.append(p)
    return np.mean(np.array(pts), axis=0) if pts else np.zeros(3)


def side_along(a: Q, b: Q):
    """A vector g exactly along (a, b) with |g| <= 1, and within 2^-48 of 1.

    With h = R it is a lawful side: h >= R |g|. The direction is exact, so a witness that needs
    this side and one other face still cancels exactly. Only the offset gives away 2^-48 R."""
    r2 = a * a + b * b
    rn, rd = isqrt(r2.numerator), isqrt(r2.denominator)
    if rn * rn == r2.numerator and rd * rd == r2.denominator:
        r = Q(rn, rd)
    else:
        r = Q(isqrt((r2.numerator << 96) // r2.denominator) + 1, 1 << 48)      # just over the length
    return (a / r, b / r)


def owners(solids, hints):
    """For each piece, the index of the solid it came from."""
    out = []
    for si, (solid, hint) in enumerate(zip(solids, hints)):
        out += [si] * len(pieces([solid], [hint]))
    return out


def solve_all(parts, hints, origin):
    A = [Piece(f) for f in pieces(parts["A"], hints["A"])]
    B = [Piece(f) for f in pieces(parts["B"], hints["B"])]
    for piece in A + B:
        piece.empty = empty_proof(piece, origin)
    records, least2, routes, unshown = [], None, {}, 0
    for ia, P in enumerate(A):
        for ib, Qp in enumerate(B):
            d, out, route = pair_witness(P, Qp, origin)
            routes[route] = routes.get(route, 0) + 1
            if out is None:
                unshown += 1
                continue
            records.append((ia, ib, out))
            _, _, gap, nn = out
            if nn > 0:
                d2 = gap * gap / nn
                least2 = d2 if least2 is None or d2 < least2 else least2
    return A, B, records, least2, routes, unshown


def aim(parts, hints, A, B, records, least2, extra, units, N, denom):
    """Give each bar a side that squarely faces the other part, where a pair is within a tenth of the least.

    A bar's regular sides seldom face the nearest point, and a corner of the prism then sticks out
    by R (1 / cos(pi / N) - 1). One more side along the witness's own direction removes that."""
    regular = [cmul(units[k], units[k + 1]) for k in range(N)]
    own = {"A": owners(parts["A"], hints["A"]), "B": owners(parts["B"], hints["B"])}
    added = 0
    for ia, ib, (mu, _, gap, nn) in records:
        if nn == 0 or gap * gap * 100 > least2 * nn * 121:
            continue
        n = [sum(x * A[ia].faces[i][0][k] for i, x in mu) for k in range(3)]
        for side, si, sign in (("A", own["A"][ia], 1), ("B", own["B"][ib], -1)):
            solid = parts[side][si]
            if solid["kind"] != "cylinder":
                continue
            iu, iv, _ = {"z": (0, 1, 2), "x": (1, 2, 0), "y": (2, 0, 1)}[solid["axis"]]
            a, b = sign * n[iu], sign * n[iv]
            if a == 0 and b == 0:
                continue
            u = side_along(a, b)
            have = regular + extra[side].setdefault(si, [])
            if any(abs(float(u[0] * h[1] - u[1] * h[0])) < 1e-9 and u[0] * h[0] + u[1] * h[1] > 0 for h in have):
                continue
            extra[side][si].append(u)
            added += 1
    return added


def make(parts, N, holes="auto", claim=None, force=False, log=print, denom=DENOM, aimed=False):
    """Returns (certificate or None, report)."""
    began = time.perf_counter()
    units = circle_units(N, denom)
    origin = bounds_centre(parts)
    if holes == "all":
        opened = {s: set(holes_of(parts[s])) for s in "AB"}
    else:
        opened = choose_holes(parts, N, units, origin, log)
    extra = {"A": {}, "B": {}}
    added_sides = 0
    for _ in range(4 if aimed else 1):
        hints = {s: make_hints(parts[s], N, opened[s], units, extra[s]) for s in "AB"}
        A, B, records, least2, routes, unshown = solve_all(parts, hints, origin)
        if not aimed or unshown or least2 is None:
            break
        more = aim(parts, hints, A, B, records, least2, extra, units, N, denom)
        if not more:
            break
        added_sides += more
    else:
        hints = {s: make_hints(parts[s], N, opened[s], units, extra[s]) for s in "AB"}
        A, B, records, least2, routes, unshown = solve_all(parts, hints, origin)
    witnesses = [{"a": ia, "b": ib, "mu": [[i, js(x)] for i, x in mu], "nu": [[j, js(x)] for j, x in nu]}
                 for ia, ib, (mu, nu, _, _) in records]
    report = {"facets": N, "pieces_a": len(A), "pieces_b": len(B), "pairs": len(A) * len(B), "routes": routes,
              "unshown": unshown, "opened": {s: sorted(opened[s]) for s in "AB"}, "aimed_sides": added_sides,
              "empty_a": sum(p.empty is not None for p in A), "empty_b": sum(p.empty is not None for p in B)}
    shown = None
    if unshown == 0 and least2 is not None:
        shown = root_down(least2)
        report["exact_square"] = js(least2)
    report["shown"] = None if shown is None else js(shown)
    report["shown_float"] = None if shown is None else float(shown)
    clearance = shown
    if claim is not None:
        claim = Q(claim)
        report["claim"] = js(claim)
        if shown is None or claim > shown:
            report["claim_met"] = False
            if not force:
                report["seconds"] = time.perf_counter() - began
                return None, report
        else:
            report["claim_met"] = True
        clearance = claim
    report["seconds"] = time.perf_counter() - began
    if clearance is None:
        return None, report
    cert = {"format": "clearance-cert/0", "clearance": js(clearance), "parts": parts, "hints": hints, "witnesses": witnesses}
    return cert, report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Make a clearance certificate for check_clearance.py")
    ap.add_argument("parts")
    ap.add_argument("facets", type=int)
    ap.add_argument("out")
    ap.add_argument("--holes", choices=["auto", "all"], default="auto")
    ap.add_argument("--claim", default=None, help="write this clearance, if it can be shown")
    ap.add_argument("--force", action="store_true", help="write the claim even when it cannot be shown")
    ap.add_argument("--denom", type=int, default=DENOM)
    ap.add_argument("--aim", action="store_true", help="add to each bar a side that squarely faces the other part")
    args = ap.parse_args(argv)
    parts = json.loads(open(args.parts, encoding="utf-8").read())
    need = args.facets >= 3
    if not need:
        print("at least 3 facets are needed")
        return 2
    cert, report = make(parts, args.facets, args.holes, args.claim, args.force, denom=args.denom, aimed=args.aim)
    print(json.dumps(report))
    if cert is None:
        print("NO CERTIFICATE")
        return 1
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(cert, f, separators=(",", ":"))
    print(f"wrote {args.out}: clearance {cert['clearance']} = {float(Q(cert['clearance'])):.9f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
