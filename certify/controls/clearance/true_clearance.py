#!/usr/bin/env python3
"""The true clearance of two parts by a dense search over their real surfaces.

    python true_clearance.py PARTS.json [...]

Independent of make_cert.py and of the checker: no facets, no weights, no duality. Each part's
surface is cut into patches with two parameters (block faces, hole walls, bar sides, bar ends,
triangles of a polytope's faces). For every pair of patches a grid of points on each is compared
point against point, then the grid is shrunk around the nearest two points, over and over.

Every sampled point is on the real part, so the number found can only be too large, never too
small. It is the true clearance when the first coarse grid lands in the right valley.
"""
from __future__ import annotations

import itertools
import json
import sys
import time
from fractions import Fraction as Q

import numpy as np

AX = {"z": (0, 1, 2), "x": (1, 2, 0), "y": (2, 0, 1)}


def fl(x) -> float:
    return float(Q(x))


class Patch:
    def __init__(self, name, f, valid=None):
        self.name, self.f, self.valid = name, f, valid

    def points(self, lo, hi, m):
        s = np.linspace(lo[0], hi[0], m)
        t = np.linspace(lo[1], hi[1], m)
        S, T = np.meshgrid(s, t, indexing="ij")
        st = np.stack([S.ravel(), T.ravel()], axis=1)
        pts = self.f(st)
        ok = np.ones(len(pts), bool) if self.valid is None else self.valid(pts)
        return st, pts, ok


def in_solid_box(solid):
    lo = np.array([fl(c) for c in solid["lo"]])
    hi = np.array([fl(c) for c in solid["hi"]])
    holes = [(AX[h["axis"]], fl(h["centre"][0]), fl(h["centre"][1]), fl(h["radius"])) for h in solid.get("holes", [])]

    def valid(p):
        ok = np.all(p >= lo - 1e-12, axis=1) & np.all(p <= hi + 1e-12, axis=1)
        for (iu, iv, _), cu, cv, R in holes:
            ok &= (p[:, iu] - cu) ** 2 + (p[:, iv] - cv) ** 2 >= R * R * (1 - 1e-13)
        return ok
    return lo, hi, holes, valid


def patches(solid, tag):
    out = []
    kind = solid["kind"]
    if kind == "box":
        lo, hi, holes, valid = in_solid_box(solid)
        for k in range(3):
            i, j = [d for d in range(3) if d != k]
            for side, val in (("lo", lo[k]), ("hi", hi[k])):
                def f(st, k=k, i=i, j=j, val=val):
                    p = np.empty((len(st), 3))
                    p[:, k] = val
                    p[:, i] = lo[i] + st[:, 0] * (hi[i] - lo[i])
                    p[:, j] = lo[j] + st[:, 1] * (hi[j] - lo[j])
                    return p
                out.append(Patch(f"{tag} face {'xyz'[k]} {side}", f, valid))
        for n, ((iu, iv, it), cu, cv, R) in enumerate(holes):
            def f(st, iu=iu, iv=iv, it=it, cu=cu, cv=cv, R=R):
                p = np.empty((len(st), 3))
                a = 2 * np.pi * st[:, 0]
                p[:, iu] = cu + R * np.cos(a)
                p[:, iv] = cv + R * np.sin(a)
                p[:, it] = lo[it] + st[:, 1] * (hi[it] - lo[it])
                return p
            out.append(Patch(f"{tag} wall of hole {n}", f, valid))
    elif kind == "cylinder":
        iu, iv, it = AX[solid["axis"]]
        cu, cv, R = fl(solid["centre"][0]), fl(solid["centre"][1]), fl(solid["radius"])
        t0, t1 = fl(solid["lo"]), fl(solid["hi"])

        def side(st):
            p = np.empty((len(st), 3))
            a = 2 * np.pi * st[:, 0]
            p[:, iu] = cu + R * np.cos(a)
            p[:, iv] = cv + R * np.sin(a)
            p[:, it] = t0 + st[:, 1] * (t1 - t0)
            return p
        out.append(Patch(f"{tag} side", side))
        for name, val in (("lo", t0), ("hi", t1)):
            def end(st, val=val):
                p = np.empty((len(st), 3))
                a = 2 * np.pi * st[:, 0]
                p[:, iu] = cu + R * st[:, 1] * np.cos(a)
                p[:, iv] = cv + R * st[:, 1] * np.sin(a)
                p[:, it] = val
                return p
            out.append(Patch(f"{tag} end {name}", end))
    elif kind == "polytope":
        H = np.array([[fl(x) for x in row] for row in solid["halfspaces"]])
        G, h = H[:, :3], H[:, 3]
        verts = []
        for i, j, k in itertools.combinations(range(len(h)), 3):
            M = G[[i, j, k]]
            if abs(np.linalg.det(M)) < 1e-12:
                continue
            v = np.linalg.solve(M, h[[i, j, k]])
            if np.all(G @ v <= h + 1e-9):
                verts.append(v)
        verts = np.array(verts)
        for i in range(len(h)):
            on = verts[np.abs(verts @ G[i] - h[i]) < 1e-8]
            if len(on) < 3:
                continue
            on = np.unique(np.round(on, 9), axis=0)
            c = on.mean(axis=0)
            e1 = on[0] - c
            e1 /= np.linalg.norm(e1)
            e2 = np.cross(G[i] / np.linalg.norm(G[i]), e1)
            order = np.argsort(np.arctan2((on - c) @ e2, (on - c) @ e1))
            on = on[order]
            for t in range(1, len(on) - 1):
                v0, v1, v2 = on[0], on[t], on[t + 1]

                def tri(st, v0=v0, v1=v1, v2=v2):
                    return v0 + st[:, :1] * (v1 - v0) + (st[:, :1] * st[:, 1:2]) * (v2 - v1)
                out.append(Patch(f"{tag} face {i} triangle {t}", tri))
    else:
        raise ValueError(kind)
    return out


def nearest(pa: Patch, pb: Patch, loa, hia, lob, hib, m):
    sa, xa, oka = pa.points(loa, hia, m)
    sb, xb, okb = pb.points(lob, hib, m)
    if not oka.any() or not okb.any():
        return np.inf, None, None
    sa, xa, sb, xb = sa[oka], xa[oka], sb[okb], xb[okb]
    d2 = (xa * xa).sum(1)[:, None] + (xb * xb).sum(1)[None, :] - 2 * xa @ xb.T
    k = int(np.argmin(d2))
    ia, ib = divmod(k, d2.shape[1])
    return float(np.linalg.norm(xa[ia] - xb[ib])), sa[ia], sb[ib]


def zoom(pa, pb, m=25, levels=40):
    loa, hia, lob, hib = (np.zeros(2), np.ones(2), np.zeros(2), np.ones(2))
    best = np.inf
    for _ in range(levels):
        d, sa, sb = nearest(pa, pb, loa, hia, lob, hib, m)
        if sa is None:
            break
        best = min(best, d)
        wa, wb = (hia - loa) * 0.3, (hib - lob) * 0.3        # the new box is 0.6 of the old, round the best
        loa, hia = np.clip(sa - wa, 0, 1), np.clip(sa + wa, 0, 1)
        lob, hib = np.clip(sb - wb, 0, 1), np.clip(sb + wb, 0, 1)
        if max(wa.max(), wb.max()) < 1e-11:
            break
    return best


def true_clearance(parts, coarse=41, keep=24):
    began = time.perf_counter()
    A = [p for n, s in enumerate(parts["A"]) for p in patches(s, f"A{n}")]
    B = [p for n, s in enumerate(parts["B"]) for p in patches(s, f"B{n}")]
    first = []
    for pa in A:
        for pb in B:
            d, _, _ = nearest(pa, pb, np.zeros(2), np.ones(2), np.zeros(2), np.ones(2), coarse)
            first.append((d, pa, pb))
    first.sort(key=lambda t: t[0])
    best, where = np.inf, None
    for d, pa, pb in first[:keep]:
        if not np.isfinite(d):
            continue
        z = zoom(pa, pb)
        if z < best:
            best, where = z, (pa.name, pb.name)
    return {"true_by_search": best, "between": where, "patch_pairs": len(first), "coarse_least": first[0][0],
            "seconds": time.perf_counter() - began}


def main(argv):
    for path in argv[1:]:
        parts = json.loads(open(path, encoding="utf-8").read())
        out = true_clearance(parts)
        print(path, json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
