#!/usr/bin/env python3
"""Probes of check_clearance.py: places where it might be wrong, each with a concrete file.

    python probe_checker.py

Writes its files under probes/ and prints what the checker did with each. Nothing here edits
the checker. Each probe says what a sound and tidy checker should do, and what this one did.
"""
from __future__ import annotations

import copy
import json
import math
import os
import random
import subprocess
import sys
from fractions import Fraction as Q

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cases import CASES  # noqa: E402
from check_clearance import Refused, check, pieces  # noqa: E402
from make_cert import js, make  # noqa: E402

CHECKER = os.path.join(HERE, "check_clearance.py")
OUT = os.path.join(HERE, "probes")


def run(cert, name):
    path = os.path.join(OUT, name + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cert, f, separators=(",", ":"))
    p = subprocess.run(["python3", CHECKER, path], capture_output=True, text=True)
    text = (p.stdout + p.stderr).strip()
    if p.returncode == 0 and text.startswith("PROVED"):
        return "ACCEPTED", text.splitlines()[0]
    if text.startswith("REFUSED"):
        return "refused", text.splitlines()[0]
    return "crashed", text.splitlines()[-1] if text else ""


def show(title, expect, got):
    print(f"- {title}\n    should: {expect}\n    did:    {got[0]} | {got[1][:110]}")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    quiet = lambda s: None  # noqa: E731
    parts = CASES["c1_pin_in_bore"][0]
    good, _ = make(parts, 32, log=quiet)
    assert run(good, "good")[0] == "ACCEPTED"

    # 1. a sound certificate in which every witness shows an empty piece
    empty = {"format": "clearance-cert/0", "clearance": "1000",
             "parts": {"A": [{"kind": "polytope", "halfspaces": [[1, 0, 0, -1], [-1, 0, 0, -1]]}],
                       "B": [{"kind": "box", "lo": [0, 0, 0], "hi": [1, 1, 1]}]},
             "hints": {"A": [None], "B": [None]},
             "witnesses": [{"a": 0, "b": 0, "mu": [[0, 1], [1, 1]], "nu": []}]}
    show("part A is the empty set (x <= -1 and x >= 1), one witness shows it",
         "accept: an empty part is any distance from anything", run(empty, "empty_part"))
    try:
        print("    check() alone returns:", {k: str(v) for k, v in check(empty).items()})
    except Refused as why:
        print("    check() alone refuses:", why)

    # 2. weights on a very large or very small scale
    for label, factor in (("times 10^200", Q(10) ** 200), ("times 10^-200", Q(1, 10 ** 200))):
        c = copy.deepcopy(good)
        w = c["witnesses"][0]
        w["mu"] = [[i, js(Q(x) * factor)] for i, x in w["mu"]]
        w["nu"] = [[i, js(Q(x) * factor)] for i, x in w["nu"]]
        show(f"one witness of a good certificate, every weight {label}", "accept: the same plane, the same proof",
             run(c, "scaled_" + label.replace(" ", "_").replace("^", "")))

    # 3. a hole with a negative radius
    c = copy.deepcopy(good)
    c["parts"]["A"][0]["holes"][0]["radius"] = "-21/2"
    show("the plate's hole given radius -21/2", "refuse, as a bar with radius <= 0 is refused", run(c, "negative_hole_radius"))

    # 4. keys the format does not know
    c = copy.deepcopy(good)
    c["parts"]["A"][0]["holes"][0]["depth"] = 3
    show("the hole given a key \"depth\": 3, as a blind hole would be written",
         "refuse: the format has no blind holes, and reading it as a through hole removes material that is there",
         run(c, "unknown_key_depth"))
    c = copy.deepcopy(good)
    c["parts"]["B"][0]["holes"] = [{"axis": "z", "centre": [0, 0], "radius": 9}]
    show("the pin given \"holes\" (a tube)", "accept or refuse, both safe: the bore is ignored, which only adds material",
         run(c, "unknown_key_tube"))

    # 5. face indices
    c = copy.deepcopy(good)
    nfaces = len(pieces(c["parts"]["A"], c["hints"]["A"])[0])
    w = c["witnesses"][0]
    w["mu"] = [[i - nfaces, x] for i, x in w["mu"]]
    show("a face index given as i - (number of faces), a negative number", "refuse, or accept: Python reads it as the same face, so no harm",
         run(c, "negative_face_index"))
    c = copy.deepcopy(good)
    c["witnesses"][0]["mu"][0][0] = 999
    show("a face index out of range", "refuse with a reason", run(c, "face_index_out_of_range"))
    c = copy.deepcopy(good)
    c["clearance"] = float("nan")
    show("clearance NaN", "refuse with a reason", run(c, "clearance_nan"))
    c = copy.deepcopy(good)
    del c["witnesses"][0]["nu"]
    show("a witness with no \"nu\" key", "refuse with a reason", run(c, "missing_key"))

    # 6. a polygon that is not convex but passes the convexity tests: it winds twice
    # the limacon r = 1 + 2 cos t turns left all the way round, twice. Shifted so that the hole's
    # centre line misses its inner loop, the line is crossed twice only, as for a convex polygon.
    n = 240
    pts = []
    for k in range(n):
        t = 2 * math.pi * k / n
        r = 1 + 2 * math.cos(t)
        pts.append((r * math.cos(t) - 1.0, r * math.sin(t) - 1.0))
    scale = 10.4 / max(math.hypot(x, y) for x, y in pts)
    poly = [[js(Q(x * scale).limit_denominator(10 ** 6)), js(Q(y * scale).limit_denominator(10 ** 6))] for x, y in pts]
    solid = copy.deepcopy(parts["A"][0])
    try:
        ps = pieces([solid], [{"holes": [poly]}])
        print(f"- a polygon of {n} corners that winds twice round (a limacon), all inside the hole\n"
              f"    should: refuse, the format asks for a convex polygon\n    did:    taken as a hint, {len(ps)} pieces")
        # is the plate less the hole still inside the union of the pieces? sample it.
        rng = random.Random(1)
        missed = tested = 0
        while tested < 200000:
            x, y, z = rng.uniform(-30, 30), rng.uniform(-30, 30), rng.uniform(0, 12)
            if x * x + y * y < 10.5 ** 2:
                continue
            tested += 1
            if not any(all(float(g[0]) * x + float(g[1]) * y + float(g[2]) * z <= float(h) + 1e-9 for g, h in face[6:]) for face in ps):
                missed += 1
        print(f"    of {tested} random points of the plate less the hole, {missed} lie in no piece")
        # and near the hole's wall, where a miss would be
        missed = tested = 0
        while tested < 200000:
            a, r = rng.uniform(0, 2 * math.pi), rng.uniform(10.5, 10.6)
            x, y = r * math.cos(a), r * math.sin(a)
            tested += 1
            if not any(all(float(g[0]) * x + float(g[1]) * y <= float(h) + 1e-9 for g, h in face[6:]) for face in ps):
                missed += 1
        print(f"    of {tested} random points just outside the hole's wall, {missed} lie in no piece")
    except Refused as why:
        print("- the limacon polygon is refused:", why)

    # 7. a small convex polygon that does not straddle the centre line: sound, but refused
    small = [[1, 1], [2, 1], [2, 2], [1, 2]]
    try:
        pieces([solid], [{"holes": [small]}])
        print("- a small square inside the hole, wholly above the centre line: taken")
    except Refused as why:
        print(f"- a small convex square inside the hole, wholly above the centre line\n    should: take it, it is convex and inside\n    did:    refused | {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
