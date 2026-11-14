#!/usr/bin/env python3
"""Negative controls for check_clearance.py.

    python neg_controls.py

Part 1, claims too large. For each case the generator is asked for more than the true clearance,
and for a hair more than it can show. Honest, it must write nothing. Forced (--force), it writes
its best witnesses under the false claim, and the checker must refuse the file.

Part 2, spoiled certificates. Good certificates are changed one thing at a time. Every changed
file must be refused. A few changes that leave the proof intact are run too, and must be accepted,
so that a checker that refused everything would not pass this test.

The checker runs as a separate process on each file. "crashed" means it ended with a Python
traceback instead of a REFUSED line: not accepted, but not a clean refusal either.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from fractions import Fraction as Q

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cases import CASES  # noqa: E402
from check_clearance import pieces  # noqa: E402
from make_cert import js, make  # noqa: E402

CHECKER = os.path.join(HERE, "check_clearance.py")
OUT = os.path.join(HERE, "neg")


def verdict(cert, name):
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


# ------------------------------------------------------------------ the ways to spoil

def first_box_with_polygon(cert):
    for side in "AB":
        for si, hint in enumerate(cert["hints"][side]):
            if hint and hint.get("holes"):
                for hi, poly in enumerate(hint["holes"]):
                    if poly is not None:
                        return side, si, hi
    return None


def first_cylinder(cert):
    for side in "AB":
        for si, solid in enumerate(cert["parts"][side]):
            if solid["kind"] == "cylinder" and cert["hints"][side][si] and cert["hints"][side][si].get("sides"):
                return side, si
    return None


def real_witness(cert, k=0):
    """The index of the k-th witness that has weights on both sides."""
    both = [i for i, w in enumerate(cert["witnesses"]) if w["mu"] and w["nu"]]
    return both[k % len(both)]


def weight_raised(c):
    w = c["witnesses"][real_witness(c, 3)]
    w["mu"][0][1] = js(Q(w["mu"][0][1]) * Q(1001, 1000))


def weight_nudged_on_b(c):
    w = c["witnesses"][real_witness(c, 5)]
    w["nu"][-1][1] = js(Q(w["nu"][-1][1]) + Q(1, 10 ** 12) * Q(w["nu"][-1][1]))


def one_side_doubled(c):
    w = c["witnesses"][real_witness(c, 1)]
    w["mu"] = [[i, js(Q(x) * 2)] for i, x in w["mu"]]


def weight_negated(c):
    w = c["witnesses"][real_witness(c, 2)]
    w["mu"][0][1] = js(-Q(w["mu"][0][1]))
    w["nu"][0][1] = js(-Q(w["nu"][0][1]))


def both_sides_negated(c):
    # the same plane, turned round: every weight of the witness negated, so the sides still cancel
    w = c["witnesses"][real_witness(c, 2)]
    w["mu"] = [[i, js(-Q(x))] for i, x in w["mu"]]
    w["nu"] = [[i, js(-Q(x))] for i, x in w["nu"]]


def witness_dropped(c):
    del c["witnesses"][real_witness(c, 4)]


def witness_emptied(c):
    w = c["witnesses"][real_witness(c, 0)]
    w["mu"], w["nu"] = [], []


def means_something_else(c, w, a, b):
    """Would the weights of witness w, read against pieces a and b, name any different plane?

    Pieces of one block share faces. A witness that names only shared faces proves the same thing
    for either piece, so moving it is no spoiling. (The first run moved such witnesses, and the
    checker rightly accepted two files: see explain_accepts.py.)"""
    A = pieces(c["parts"]["A"], c["hints"]["A"])
    B = pieces(c["parts"]["B"], c["hints"]["B"])
    return any(A[w["a"]][i] != A[a][i] for i, _ in w["mu"]) or any(B[w["b"]][j] != B[b][j] for j, _ in w["nu"])


def witness_copied_over_another(c):
    ws = c["witnesses"]
    i = real_witness(c, 0)
    j = next((k for k in range(len(ws)) if k != i and means_something_else(c, ws[i], ws[k]["a"], ws[k]["b"])), None)
    if j is None:
        return "skip"
    a, b = ws[j]["a"], ws[j]["b"]
    ws[j] = copy.deepcopy(ws[i])
    ws[j]["a"], ws[j]["b"] = a, b


def pieces_renumbered(c):
    na = max(w["a"] for w in c["witnesses"]) + 1
    nb = max(w["b"] for w in c["witnesses"]) + 1
    if na > 1:
        for w in c["witnesses"]:
            w["a"] = (w["a"] + 1) % na
    elif nb > 1:
        for w in c["witnesses"]:
            w["b"] = (w["b"] + 1) % nb
    else:
        return "skip"


def two_pieces_swapped(c):
    ws = c["witnesses"]
    i = real_witness(c, 0)
    j = next((k for k in range(len(ws)) if ws[k]["a"] != ws[i]["a"] and ws[k]["b"] == ws[i]["b"]
              and means_something_else(c, ws[i], ws[k]["a"], ws[k]["b"])), None)
    if j is None:
        return "skip"
    ws[i]["a"], ws[j]["a"] = ws[j]["a"], ws[i]["a"]


def faces_renumbered(c):
    w = c["witnesses"][real_witness(c, 0)]
    w["mu"] = [[i + 1, x] for i, x in w["mu"]]


def face_index_changed_on_b(c):
    w = c["witnesses"][real_witness(c, 1)]
    w["nu"][0][0] = w["nu"][0][0] - 1 if w["nu"][0][0] > 0 else 1


def clearance_raised_a_hair(c):
    c["clearance"] = js(Q(c["clearance"]) * (1 + Q(1, 10 ** 9)))


def clearance_raised_by_one_bit(c):
    c["clearance"] = js(Q(c["clearance"]) + Q(1, 2 ** 60))


def clearance_doubled(c):
    c["clearance"] = js(Q(c["clearance"]) * 2)


def clearance_negative(c):
    c["clearance"] = js(-Q(c["clearance"]))


def corner_pushed_outside(c):
    at = first_box_with_polygon(c)
    if at is None:
        return "skip"
    side, si, hi = at
    hole = c["parts"][side][si]["holes"][hi]
    cu, cv = (Q(x) for x in hole["centre"])
    poly = c["hints"][side][si]["holes"][hi]
    u, v = (Q(x) for x in poly[1])
    poly[1] = [js(cu + (u - cu) * Q(101, 100)), js(cv + (v - cv) * Q(101, 100))]


def corner_pushed_outside_by_a_hair(c):
    at = first_box_with_polygon(c)
    if at is None:
        return "skip"
    side, si, hi = at
    hole = c["parts"][side][si]["holes"][hi]
    cu, cv = (Q(x) for x in hole["centre"])
    poly = c["hints"][side][si]["holes"][hi]
    f = 1 + Q(1, 10 ** 15)
    u, v = (Q(x) for x in poly[2])
    poly[2] = [js(cu + (u - cu) * f), js(cv + (v - cv) * f)]


def corner_moved_inward(c):
    at = first_box_with_polygon(c)
    if at is None:
        return "skip"
    side, si, hi = at
    hole = c["parts"][side][si]["holes"][hi]
    cu, cv = (Q(x) for x in hole["centre"])
    poly = c["hints"][side][si]["holes"][hi]
    u, v = (Q(x) for x in poly[1])
    poly[1] = [js(cu + (u - cu) * Q(999, 1000)), js(cv + (v - cv) * Q(999, 1000))]


def corner_dropped(c):
    at = first_box_with_polygon(c)
    if at is None:
        return "skip"
    side, si, hi = at
    del c["hints"][side][si]["holes"][hi][1]


def polygon_reversed(c):
    at = first_box_with_polygon(c)
    if at is None:
        return "skip"
    side, si, hi = at
    c["hints"][side][si]["holes"][hi].reverse()


def polygon_made_dented(c):
    at = first_box_with_polygon(c)
    if at is None:
        return "skip"
    side, si, hi = at
    poly = c["hints"][side][si]["holes"][hi]
    poly[1], poly[2] = poly[2], poly[1]


def polygon_all_scaled_up(c):
    # every corner pushed out by the same factor: a bigger regular polygon, outside the hole
    at = first_box_with_polygon(c)
    if at is None:
        return "skip"
    side, si, hi = at
    hole = c["parts"][side][si]["holes"][hi]
    cu, cv = (Q(x) for x in hole["centre"])
    poly = c["hints"][side][si]["holes"][hi]
    for k, (u, v) in enumerate(poly):
        poly[k] = [js(cu + (Q(u) - cu) * Q(21, 20)), js(cv + (Q(v) - cv) * Q(21, 20))]


def hole_left_filled(c):
    at = first_box_with_polygon(c)
    if at is None:
        return "skip"
    side, si, hi = at
    c["hints"][side][si]["holes"][hi] = None


def hole_made_smaller(c):
    at = first_box_with_polygon(c)
    if at is None:
        return "skip"
    side, si, hi = at
    hole = c["parts"][side][si]["holes"][hi]
    hole["radius"] = js(Q(hole["radius"]) * Q(99, 100))


def side_pulled_inside(c):
    at = first_cylinder(c)
    if at is None:
        return "skip"
    side, si = at
    s = c["hints"][side][si]["sides"][0]
    s[2] = js(Q(s[2]) * Q(99, 100))


def side_pulled_inside_by_a_hair(c):
    at = first_cylinder(c)
    if at is None:
        return "skip"
    side, si = at
    s = c["hints"][side][si]["sides"][1]
    s[2] = js(Q(s[2]) * (1 - Q(1, 10 ** 15)))


def all_sides_pulled_inside(c):
    # the prism shrunk as a whole: every side a twentieth nearer the axis
    at = first_cylinder(c)
    if at is None:
        return "skip"
    side, si = at
    for s in c["hints"][side][si]["sides"]:
        s[2] = js(Q(s[2]) * Q(19, 20))


def side_turned(c):
    at = first_cylinder(c)
    if at is None:
        return "skip"
    side, si = at
    s = c["hints"][side][si]["sides"][0]
    s[0] = js(Q(s[0]) + Q(1, 1000))


def side_removed(c):
    at = first_cylinder(c)
    if at is None:
        return "skip"
    side, si = at
    del c["hints"][side][si]["sides"][0]


def bar_made_fatter(c):
    at = first_cylinder(c)
    if at is None:
        return "skip"
    side, si = at
    solid = c["parts"][side][si]
    solid["radius"] = js(Q(solid["radius"]) * Q(101, 100))


# which way to move the first bar of each case so that it comes nearer the other part.
# (Moved away, the old witnesses still prove the old claim, and the file is rightly accepted.)
TOWARD = {"c1_pin_in_bore": (1, 0), "c2_pin_off_centre": (1, 0), "c3a_clevis_vs_pin_and_bar": (1, 0),
          "c3b_clevis_and_pin_vs_bar": (0, 2), "c4a_wedge_rim": (2, 0), "c4b_wedge_skew": (2, 1)}
CURRENT = {"case": None}


def bar_moved(c):
    at = first_cylinder(c)
    if at is None or CURRENT["case"] not in TOWARD:
        return "skip"
    side, si = at
    solid = c["parts"][side][si]
    du, dv = TOWARD[CURRENT["case"]]
    solid["centre"] = [js(Q(solid["centre"][0]) + du), js(Q(solid["centre"][1]) + dv)]


def bar_axis_changed(c):
    at = first_cylinder(c)
    if at is None:
        return "skip"
    side, si = at
    solid = c["parts"][side][si]
    solid["axis"] = {"z": "x", "x": "y", "y": "z"}[solid["axis"]]


def parts_swapped(c):
    c["parts"]["A"], c["parts"]["B"] = c["parts"]["B"], c["parts"]["A"]
    c["hints"]["A"], c["hints"]["B"] = c["hints"]["B"], c["hints"]["A"]


def format_changed(c):
    c["format"] = "clearance-cert/1"


SPOILS = [weight_raised, weight_nudged_on_b, one_side_doubled, weight_negated, both_sides_negated, witness_dropped,
          witness_emptied, witness_copied_over_another, pieces_renumbered, two_pieces_swapped, faces_renumbered,
          face_index_changed_on_b, clearance_raised_a_hair, clearance_raised_by_one_bit, clearance_doubled,
          clearance_negative, corner_pushed_outside, corner_pushed_outside_by_a_hair, corner_moved_inward,
          corner_dropped, polygon_reversed, polygon_made_dented, polygon_all_scaled_up, hole_left_filled,
          hole_made_smaller, side_pulled_inside, side_pulled_inside_by_a_hair, all_sides_pulled_inside, side_turned,
          side_removed, bar_made_fatter, bar_moved, bar_axis_changed, parts_swapped, format_changed]


# changes that leave the proof whole: these must be ACCEPTED

def witness_scaled_whole(c):
    w = c["witnesses"][real_witness(c, 0)]
    w["mu"] = [[i, js(Q(x) * 7)] for i, x in w["mu"]]
    w["nu"] = [[i, js(Q(x) * 7)] for i, x in w["nu"]]


def clearance_lowered(c):
    c["clearance"] = js(Q(c["clearance"]) * Q(9, 10))


def witnesses_reordered(c):
    c["witnesses"].reverse()


def witness_given_twice(c):
    c["witnesses"].append(copy.deepcopy(c["witnesses"][0]))


HARMLESS = [witness_scaled_whole, clearance_lowered, witnesses_reordered, witness_given_twice]

# the good certificates to spoil: (case, facets, holes, aimed)
BASES = [("c1_pin_in_bore", 32, "auto", False), ("c2_pin_off_centre", 64, "auto", False),
         ("c3a_clevis_vs_pin_and_bar", 16, "auto", False), ("c3b_clevis_and_pin_vs_bar", 16, "auto", True),
         ("c4a_wedge_rim", 16, "auto", False), ("c4b_wedge_skew", 32, "auto", True),
         ("c5_blocks_3x2", 16, "auto", False), ("c5_blocks_2x1", 8, "all", False)]

# claims too large: (case, facets, aimed)
CLAIMS = [("c1_pin_in_bore", 64, False), ("c2_pin_off_centre", 64, False), ("c3a_clevis_vs_pin_and_bar", 32, False),
          ("c3b_clevis_and_pin_vs_bar", 32, False), ("c3b_clevis_and_pin_vs_bar", 32, True), ("c4a_wedge_rim", 32, False),
          ("c4a_wedge_rim", 32, True), ("c4b_wedge_skew", 32, False), ("c4b_wedge_skew", 32, True), ("c5_blocks_3x2", 32, False)]


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    quiet = lambda s: None  # noqa: E731
    record = {"claims": [], "spoils": [], "harmless": []}
    bad = 0

    print("== part 1: claims too large")
    for name, N, aimed in CLAIMS:
        parts, _, true_value = CASES[name]
        _, rep = make(parts, N, log=quiet, aimed=aimed)
        shown = Q(rep["shown"])
        over_true = Q(true_value).limit_denominator(10 ** 12) * (1 + Q(1, 10 ** 6))       # above the true clearance
        asks = [("true + 1e-6 of it", over_true), ("true x 2", over_true * 2), ("shown + 2^-40", shown + Q(1, 2 ** 40))]
        for label, claim in asks:
            honest, _ = make(parts, N, log=quiet, aimed=aimed, claim=js(claim))
            forced, _ = make(parts, N, log=quiet, aimed=aimed, claim=js(claim), force=True)
            v, line = verdict(forced, f"claim_{name}_{N}{'_aim' if aimed else ''}_{label.split()[0]}{'2' if 'x 2' in label else ''}")
            ok = honest is None and v != "ACCEPTED"
            bad += not ok
            row = {"case": name, "facets": N, "aimed": aimed, "ask": label, "claim": float(claim), "shown": float(shown),
                   "true": true_value, "honest_wrote_a_file": honest is not None, "forced_file": v, "checker_said": line}
            record["claims"].append(row)
            print(f"  {name:28s} N={N:<3d}{' aim' if aimed else '    '} ask {label:18s} = {float(claim):.9f}: honest wrote {'A FILE' if honest is not None else 'nothing'}, forced file {v}: {line[:70]}")
        # and the exact amount shown must be accepted
        good, _ = make(parts, N, log=quiet, aimed=aimed, claim=js(shown))
        v, line = verdict(good, f"claim_{name}_{N}{'_aim' if aimed else ''}_exact")
        bad += v != "ACCEPTED"
        record["claims"].append({"case": name, "facets": N, "aimed": aimed, "ask": "exactly what is shown", "claim": float(shown), "forced_file": v})
        print(f"  {name:28s} N={N:<3d}{' aim' if aimed else '    '} ask exactly what is shown = {float(shown):.9f}: {v}")

    print("== part 2: spoiled certificates")
    for name, N, holes, aimed in BASES:
        parts, _, _ = CASES[name]
        CURRENT["case"] = name
        base, _ = make(parts, N, holes=holes, log=quiet, aimed=aimed)
        tag = f"{name}_{N}"
        v, _ = verdict(base, f"base_{tag}")
        print(f"  base {tag}: {v}, {len(base['witnesses'])} witnesses")
        bad += v != "ACCEPTED"
        for spoil in SPOILS:
            c = copy.deepcopy(base)
            if spoil(c) == "skip":
                continue
            v, line = verdict(c, f"spoil_{tag}_{spoil.__name__}")
            bad += v == "ACCEPTED"
            record["spoils"].append({"base": tag, "spoil": spoil.__name__, "verdict": v, "checker_said": line})
            print(f"    {spoil.__name__:32s} {v:9s} {line[:95]}")
        for change in HARMLESS:
            c = copy.deepcopy(base)
            change(c)
            v, line = verdict(c, f"harmless_{tag}_{change.__name__}")
            bad += v != "ACCEPTED"
            record["harmless"].append({"base": tag, "change": change.__name__, "verdict": v})
            print(f"    {change.__name__:32s} {v:9s} (must be accepted)")

    n_sp = len(record["spoils"])
    acc = [r for r in record["spoils"] if r["verdict"] == "ACCEPTED"]
    crashed = [r for r in record["spoils"] if r["verdict"] == "crashed"]
    print(f"== {n_sp} spoiled files over {len(BASES)} good certificates, {len(SPOILS)} ways: "
          f"{n_sp - len(acc) - len(crashed)} refused, {len(crashed)} crashed, {len(acc)} ACCEPTED")
    for r in acc:
        print("   ACCEPTED:", r)
    over = [r for r in record["claims"] if r["ask"] != "exactly what is shown"]
    print(f"== {len(over)} claims too large: honest wrote a file {sum(r['honest_wrote_a_file'] for r in over)} times, "
          f"forced files accepted {sum(r['forced_file'] == 'ACCEPTED' for r in over)} times")
    print(f"== harmless changes accepted {sum(r['verdict'] == 'ACCEPTED' for r in record['harmless'])} of {len(record['harmless'])}")
    with open(os.path.join(HERE, "neg_results.json"), "w", encoding="utf-8") as f:
        json.dump(record, f, indent=1)
    print("problems:", bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
