#!/usr/bin/env python3
"""Probes of how a number is read: a good certificate with one number written loosely.

    python form_probes.py GOOD_CERT.json OUT_DIR

check_clearance.py takes whatever Python's Fraction and int take. The Lean checker reads a
number only as a JSON whole number or a string "p" or "p/q", and an index only as a JSON
whole number. So the two may differ on these files, and where they do the Lean checker
should be the one that refuses. Each file's name says what was changed.
"""
from __future__ import annotations

import copy
import json
import os
import sys


def main(argv: list[str]) -> int:
    good = json.loads(open(argv[1], encoding="utf-8").read())
    out = argv[2]
    os.makedirs(out, exist_ok=True)
    box = next(n for n, s in enumerate(good["parts"]["A"]) if s["kind"] == "box")
    bar = next(n for n, s in enumerate(good["parts"]["B"]) if s["kind"] == "cylinder")
    probes = {}

    c = copy.deepcopy(good)
    c["parts"]["A"][box]["lo"] = [float(x) for x in c["parts"]["A"][box]["lo"]]
    probes["c1_lo_as_float"] = c

    c = copy.deepcopy(good)
    c["parts"]["A"][box]["lo"] = c["parts"]["A"][box]["lo"] + [0]
    probes["c2_box_with_four_coordinates"] = c

    c = copy.deepcopy(good)
    c["witnesses"][0]["a"] = str(c["witnesses"][0]["a"])
    probes["c3_piece_index_as_string"] = c

    c = copy.deepcopy(good)
    c["witnesses"][0]["mu"][0][0] = float(c["witnesses"][0]["mu"][0][0])
    probes["c4_face_index_as_float"] = c

    c = copy.deepcopy(good)
    c["clearance"] = 0.25
    probes["c5_clearance_as_float_0.25"] = c

    # a hole left filled is not read, so its fields may hold anything; the witnesses then
    # name faces that the filled block does not have
    c = copy.deepcopy(good)
    c["hints"]["A"][box]["holes"] = [None] * len(c["parts"]["A"][box]["holes"])
    c["parts"]["A"][box]["holes"] = [{"axis": "w", "centre": "nowhere", "radius": []} for _ in c["parts"]["A"][box]["holes"]]
    probes["c6_filled_hole_with_junk_fields"] = c

    c = copy.deepcopy(good)
    c["hints"]["B"][bar]["holes"] = [None]
    probes["c7_bar_hint_with_a_holes_key"] = c

    c = copy.deepcopy(good)
    c["parts"]["B"][bar]["centre"] = c["parts"]["B"][bar]["centre"] + [0]
    probes["c8_centre_with_three_numbers"] = c

    for name, cert in probes.items():
        with open(os.path.join(out, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(cert, f, separators=(",", ":"))
    print(f"wrote {len(probes)} files to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
