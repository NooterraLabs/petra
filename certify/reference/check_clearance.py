#!/usr/bin/env python3
"""Exact check of a clearance certificate between two parts with flat and round faces.

The claim: no point of part A is nearer than `clearance` to any point of part B.

A part is a union of solids, in one frame, every number an exact rational:

  {"kind": "box", "lo": [x, y, z], "hi": [x, y, z], "holes": [{"axis": "z", "centre": [u, v], "radius": R}]}
      a block with its faces square to the axes, less round holes that run right through it
      along a coordinate axis
  {"kind": "cylinder", "axis": "z", "centre": [u, v], "radius": R, "lo": t0, "hi": t1}
      a solid round bar along a coordinate axis, from t0 to t1 along it
  {"kind": "polytope", "halfspaces": [[gx, gy, gz, h], ...]}
      a convex solid with flat faces: every point with g . x <= h for each row

Across an axis the two coordinates (u, v) are (x, y) for "z", (y, z) for "x" and (z, x) for "y".

The certificate gives hints and witnesses. A hint turns a round face into flat ones, always on
the safe side, and the check tests that it is on the safe side:

  for a cylinder   "sides": [[gu, gv, h], ...]: flat faces gu*(u-cu) + gv*(v-cv) <= h. Each must
                   have h >= R * |g|, so the bar lies inside every one of them.
  for a box        "holes": one entry per hole, null or a polygon [[u, v], ...]. A polygon must
                   turn left at every corner, with every corner inside the hole's circle. The
                   pieces are the block cut by the plane of each edge, keeping the side to the
                   edge's right. Their union is the block less K, the points strictly left of
                   every edge. K lies inside the hull of the corners: at the corner furthest along
                   any direction both edges turn left, so the points left of both lie on the near
                   side of it. The hull lies in the closed disc and meets the circle at corners
                   only, and no corner is in K. So K holds no material, even where the polygon
                   winds more than once. null leaves the hole filled, which only adds material.

So each part lies inside a union of convex pieces, each a list of flat faces g . x <= h. `pieces`
below makes that list, and the order of pieces and faces is part of this format.

A witness for a piece P of A and a piece Q of B is two lists of weights, mu over the faces of P
and nu over the faces of Q, none negative. The check adds up n = sum mu_i g_i and a = sum mu_i h_i,
so n . x <= a on all of P. It asks that sum nu_j k_j = -n exactly, and adds up b = -sum nu_j m_j,
so n . y >= b on all of Q. Then every x of P and y of Q are at least (b - a) / |n| apart, and it
asks b - a >= 0 and (b - a)^2 >= clearance^2 * |n|^2. Every pair of pieces needs a witness.

What is not checked: that the solids describe the real part, tolerances, deflection under load,
thermal growth. Those are premises.

    python3 check_clearance.py CERT.json
"""
from __future__ import annotations

import itertools
import json
import sys
import time
from fractions import Fraction as Q

AXES = {"z": (0, 1, 2), "x": (1, 2, 0), "y": (2, 0, 1)}   # axis -> the indices of u, v and of the axis itself

Face = tuple[tuple[Q, Q, Q], Q]


class Refused(Exception):
    pass


def need(ok: bool, why: str) -> None:
    if not ok:
        raise Refused(why)


def _face(axis: str, gu: Q, gv: Q, gt: Q, h: Q) -> Face:
    iu, iv, it = AXES[axis]
    g = [Q(0), Q(0), Q(0)]
    g[iu], g[iv], g[it] = gu, gv, gt
    return (g[0], g[1], g[2]), h


def pieces(solids: list[dict], hints: list[dict | None]) -> list[list[Face]]:
    """The convex pieces whose union holds a part, each a list of faces (g, h) for g . x <= h."""
    need(len(hints) == len(solids), "one hint, or null, for each solid is needed")
    out: list[list[Face]] = []
    for n, (solid, hint) in enumerate(zip(solids, hints)):
        hint = hint or {}
        kind = solid["kind"]
        allowed = {"polytope": {"kind", "halfspaces"}, "cylinder": {"kind", "axis", "centre", "radius", "lo", "hi"}, "box": {"kind", "lo", "hi", "holes"}}
        need(kind in allowed, f"solid {n} is of no known kind")
        need(set(solid) <= allowed[kind], f"solid {n} has a key this format does not know: {sorted(set(solid) - allowed[kind])}")
        need(set(hint) <= {"sides", "holes"}, f"the hint for solid {n} has a key this format does not know")
        if kind == "polytope":
            faces = [((Q(a), Q(b), Q(c)), Q(h)) for a, b, c, h in solid["halfspaces"]]
            need(len(faces) >= 1, f"solid {n} has no face")
            out.append(faces)
        elif kind == "cylinder":
            axis, R = solid["axis"], Q(solid["radius"])
            cu, cv = (Q(c) for c in solid["centre"])
            lo, hi = Q(solid["lo"]), Q(solid["hi"])
            need(R > 0 and lo < hi, f"solid {n} is no cylinder")
            faces = [_face(axis, Q(0), Q(0), Q(-1), -lo), _face(axis, Q(0), Q(0), Q(1), hi)]
            for gu, gv, h in hint.get("sides", []):
                gu, gv, h = Q(gu), Q(gv), Q(h)
                need(h >= 0 and h * h >= R * R * (gu * gu + gv * gv), f"a side given for the cylinder {n} cuts into it")
                faces.append(_face(axis, gu, gv, Q(0), h + gu * cu + gv * cv))
            out.append(faces)
        elif kind == "box":
            lo, hi = [Q(c) for c in solid["lo"]], [Q(c) for c in solid["hi"]]
            need(all(a < b for a, b in zip(lo, hi)), f"solid {n} is no box")
            base: list[Face] = []
            for k in range(3):
                g = [Q(0), Q(0), Q(0)]
                g[k] = Q(-1)
                base.append(((g[0], g[1], g[2]), -lo[k]))
                g = [Q(0), Q(0), Q(0)]
                g[k] = Q(1)
                base.append(((g[0], g[1], g[2]), hi[k]))
            holes = solid.get("holes", [])
            given = hint.get("holes", [None] * len(holes))
            need(len(given) == len(holes), f"one polygon, or null, for each hole of the box {n} is needed")
            cuts: list[list[Face]] = []
            for hole, polygon in zip(holes, given):
                if polygon is None:
                    continue
                need(set(hole) <= {"axis", "centre", "radius"}, f"a hole of the box {n} has a key this format does not know: {sorted(set(hole) - {'axis', 'centre', 'radius'})}")
                axis, R = hole["axis"], Q(hole["radius"])
                need(R > 0, f"a hole of the box {n} has no radius")
                cu, cv = (Q(c) for c in hole["centre"])
                P = [(Q(u), Q(v)) for u, v in polygon]
                need(len(P) >= 3, f"a polygon given for a hole of the box {n} has under three corners")
                edges: list[Face] = []
                for i, (pu, pv) in enumerate(P):
                    qu, qv = P[(i + 1) % len(P)]
                    wu, wv = P[(i + 2) % len(P)]
                    need((pu - cu) ** 2 + (pv - cv) ** 2 <= R * R, f"a corner of a polygon given for a hole of the box {n} is outside the hole")
                    need((qu - pu) * (wv - qv) - (qv - pv) * (wu - qu) > 0, f"a polygon given for a hole of the box {n} is not convex and counter-clockwise")
                    eu, ev = qu - pu, qv - pv
                    # outside the edge p->q of a counter-clockwise polygon: e x (x - p) <= 0
                    edges.append(_face(axis, -ev, eu, Q(0), -ev * pu + eu * pv))
                cuts.append(edges)
            for choice in itertools.product(*cuts):
                out.append(base + list(choice))
        else:
            raise Refused(f"solid {n} is of no known kind")
    return out


def check(cert: dict) -> dict:
    need(cert.get("format") == "clearance-cert/0", "not a clearance-cert/0 file")
    c = Q(cert["clearance"])
    need(c >= 0, "the clearance is negative")
    A = pieces(cert["parts"]["A"], cert["hints"]["A"])
    B = pieces(cert["parts"]["B"], cert["hints"]["B"])
    seen: set[tuple[int, int]] = set()
    least: tuple[Q, Q] | None = None   # (gap^2, |n|^2) of the witness that shows least
    for w in cert["witnesses"]:
        ia, ib = int(w["a"]), int(w["b"])
        need(0 <= ia < len(A) and 0 <= ib < len(B), "a witness names no piece")
        n, a, m, b = [Q(0)] * 3, Q(0), [Q(0)] * 3, Q(0)
        for i, mu in w["mu"]:
            mu = Q(mu)
            need(mu >= 0, "a weight is negative")
            need(0 <= int(i) < len(A[ia]), "a weight names no face")
            g, h = A[ia][int(i)]
            n = [n[k] + mu * g[k] for k in range(3)]
            a += mu * h
        for j, nu in w["nu"]:
            nu = Q(nu)
            need(nu >= 0, "a weight is negative")
            need(0 <= int(j) < len(B[ib]), "a weight names no face")
            g, h = B[ib][int(j)]
            m = [m[k] + nu * g[k] for k in range(3)]
            b -= nu * h
        need(all(n[k] + m[k] == 0 for k in range(3)), f"the two sides of the witness for pieces {ia} and {ib} do not face each other")
        gap, nn = b - a, sum(x * x for x in n)
        # With no direction (n = 0) a witness shows something only when b > a, and then it shows a piece is empty.
        need(nn > 0 or gap > 0, f"the witness for pieces {ia} and {ib} has no direction")
        need(gap >= 0 and gap * gap >= c * c * nn, f"the witness for pieces {ia} and {ib} does not show the clearance")
        if nn > 0 and (least is None or gap * gap * least[1] < least[0] * nn):
            least = (gap * gap, nn)
        seen.add((ia, ib))
    missing = [(i, j) for i in range(len(A)) for j in range(len(B)) if (i, j) not in seen]
    need(not missing, f"{len(missing)} pairs of pieces have no witness, the first {missing[:1]}")
    return {"clearance": c, "pieces_a": len(A), "pieces_b": len(B), "pairs": len(A) * len(B), "least_shown_squared": None if least is None else least[0] / least[1]}


def main(argv: list[str]) -> int:
    began = time.perf_counter()
    cert = json.loads(open(argv[1], encoding="utf-8").read())
    try:
        out = check(cert)
    except Refused as why:
        print(f"REFUSED: {why}")
        return 1
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError, AttributeError) as bad:
        print(f"REFUSED: the file is not in the format ({type(bad).__name__}: {bad})")
        return 1
    sq = out["least_shown_squared"]
    try:
        shown = "none, every piece pair has an empty piece" if sq is None else f"{(sq.numerator / sq.denominator) ** 0.5:.6f}"
    except OverflowError:
        shown = "too large or small to print"
    print(f"PROVED: the parts are at least {out['clearance']} = {out['clearance'].numerator / out['clearance'].denominator:.6f} apart")
    print(f"  {out['pieces_a']} pieces of A against {out['pieces_b']} of B, {out['pairs']} pairs, the least distance shown {shown}")
    print(f"  checked in {time.perf_counter() - began:.3f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
