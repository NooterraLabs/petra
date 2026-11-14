#!/usr/bin/env python3
"""Negative control: certificates that are whole and consistent, but rest on a hint that lies.

    python cheat_controls.py

neg_controls.py spoils one thing in a good file, which leaves stale witnesses behind. Here the
generator itself is made to cheat. Its hints are pushed to the unsafe side (a hole's polygon
grown past the hole, a bar's sides pulled inside the bar) and it then makes exact witnesses for
those false pieces. Every witness cancels and shows the claim, and the claim is above the true
clearance. Only the checker's test of the hints stands in the way.

In this process only, the checker's `need` is replaced so that the two hint tests pass. That lets
the generator build the false pieces, and lets us confirm the file is otherwise consistent. The
checker's file is not touched, and the verdict that counts comes from running it as a separate
process on the written file.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from fractions import Fraction as Q

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_clearance  # noqa: E402
import make_cert as mc  # noqa: E402
from cases import CASES  # noqa: E402

CHECKER = os.path.join(HERE, "check_clearance.py")
OUT = os.path.join(HERE, "neg")
honest_need = check_clearance.need
honest_hints = mc.make_hints


def lenient_need(ok, why):
    if "cuts into it" in why or "is outside the hole" in why:
        return
    honest_need(ok, why)


def lying_hints(hole_scale: Q, side_scale: Q):
    def make_hints(solids, N, opened, units, extra=None):
        hints = honest_hints(solids, N, opened, units, extra)
        for solid, hint in zip(solids, hints):
            if solid["kind"] == "cylinder":
                for side in hint["sides"]:
                    side[2] = mc.js(Q(side[2]) * side_scale)
            elif solid["kind"] == "box":
                for hole, poly in zip(solid.get("holes", []), hint["holes"]):
                    if poly is None:
                        continue
                    cu, cv = (Q(x) for x in hole["centre"])
                    for k, (u, v) in enumerate(poly):
                        poly[k] = [mc.js(cu + (Q(u) - cu) * hole_scale), mc.js(cv + (Q(v) - cv) * hole_scale)]
        return hints
    return make_hints


CHEATS = [
    # (case, facets, the hole's polygon times, the bar's sides times)
    ("c1_pin_in_bore", 64, Q(105, 100), Q(1)),
    ("c1_pin_in_bore", 64, Q(1), Q(95, 100)),
    ("c1_pin_in_bore", 64, 1 + Q(1, 10 ** 12), Q(1)),
    ("c1_pin_in_bore", 64, Q(1), 1 - Q(1, 10 ** 12)),
    ("c1_pin_in_bore", 8, Q(11, 10), Q(1)),
    ("c2_pin_off_centre", 32, Q(102, 100), Q(99, 100)),
    ("c3a_clevis_vs_pin_and_bar", 16, Q(11, 10), Q(1)),
    ("c3b_clevis_and_pin_vs_bar", 16, Q(1), Q(9, 10)),
    ("c4a_wedge_rim", 16, Q(1), Q(9, 10)),
    ("c4b_wedge_skew", 16, Q(1), Q(1, 2)),
    ("c5_blocks_3x2", 16, Q(11, 10), Q(1)),
]


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    quiet = lambda s: None  # noqa: E731
    bad = 0
    rows = []
    for n, (name, N, hole_scale, side_scale) in enumerate(CHEATS):
        parts, _, true_value = CASES[name]
        _, honest = mc.make(parts, N, log=quiet)
        check_clearance.need = lenient_need
        mc.make_hints = lying_hints(hole_scale, side_scale)
        try:
            cert, rep = mc.make(parts, N, log=quiet)
            inside = None
            if cert is not None:
                inside = float(check_clearance.check(cert)["clearance"])       # consistent, the hint tests set aside
        finally:
            check_clearance.need = honest_need
            mc.make_hints = honest_hints
        if cert is None:
            print(f"{name} N={N}: the cheat made no file")
            continue
        path = os.path.join(OUT, f"cheat_{n}_{name}_{N}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cert, f, separators=(",", ":"))
        p = subprocess.run(["python3", CHECKER, path], capture_output=True, text=True)
        text = (p.stdout + p.stderr).strip()
        verdict = "ACCEPTED" if p.returncode == 0 and text.startswith("PROVED") else ("refused" if text.startswith("REFUSED") else "crashed")
        bad += verdict == "ACCEPTED"
        honest_shown = honest["shown_float"]
        rows.append({"case": name, "facets": N, "hole_scale": float(hole_scale), "side_scale": float(side_scale), "true": true_value,
                     "honest_shown": honest_shown, "claimed": float(Q(cert["clearance"])), "consistent_but_for_hints": inside, "checker": verdict,
                     "checker_said": text.splitlines()[0] if text else ""})
        print(f"{name:28s} N={N:<3d} polygon x {float(hole_scale):.15g}, sides x {float(side_scale):.15g}: true {true_value:.9f}, "
              f"honest {'none' if honest_shown is None else f'{honest_shown:.9f}'}, the lie claims {float(Q(cert['clearance'])):.12f} "
              f"(above the true one: {float(Q(cert['clearance'])) > true_value}), consistent but for the hints: {inside is not None}, "
              f"checker: {verdict} | {text.splitlines()[0][:80] if text else ''}")
    with open(os.path.join(HERE, "cheat_results.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    print(f"{len(rows)} lying certificates, accepted: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
