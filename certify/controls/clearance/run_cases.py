#!/usr/bin/env python3
"""Run every case: make the certificate, run the checker on the file, and write results.json.

    python run_cases.py [--true] [name-prefix ...]

--true also runs the dense search of true_clearance.py for each case (slow).
The checker is run as a separate process on the written file, exactly as a user would.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cases import CASES  # noqa: E402
from make_cert import make  # noqa: E402

CHECKER = os.path.join(HERE, "check_clearance.py")

# (case, holes mode, aimed sides or not, the facet counts)
ALL5 = [8, 16, 32, 64, 128]
PLAN = [
    ("c1_pin_in_bore", "auto", False, ALL5),
    ("c2_pin_off_centre", "auto", False, ALL5),
    ("c3a_clevis_vs_pin_and_bar", "auto", False, ALL5),
    ("c3b_clevis_and_pin_vs_bar", "auto", False, ALL5),
    ("c3b_clevis_and_pin_vs_bar", "auto", True, ALL5),
    ("c4a_wedge_rim", "auto", False, ALL5),
    ("c4a_wedge_rim", "auto", True, ALL5),
    ("c4b_wedge_skew", "auto", False, ALL5),
    ("c4b_wedge_skew", "auto", True, ALL5),
    ("c5_blocks_3x2", "auto", False, ALL5),
    ("c5_blocks_1x0", "all", False, [8, 16]),
    ("c5_blocks_1x1", "all", False, [8, 16]),
    ("c5_blocks_2x1", "all", False, [8, 16]),
    ("c5_blocks_2x2", "all", False, [8]),
    ("c5_blocks_3x2", "all", False, [6, 8]),
]


def run_checker(path):
    began = time.perf_counter()
    p = subprocess.run(["python3", CHECKER, path], capture_output=True, text=True)
    wall = time.perf_counter() - began
    out = (p.stdout + p.stderr).strip()
    inner = re.search(r"checked in ([0-9.]+) s", out)
    return {"exit": p.returncode, "proved": p.returncode == 0 and out.startswith("PROVED"), "first_line": out.splitlines()[0] if out else "",
            "check_seconds": float(inner.group(1)) if inner else None, "check_wall_seconds": wall}


def main(argv):
    want_true = "--true" in argv
    prefixes = [a for a in argv[1:] if not a.startswith("--")]
    os.makedirs(os.path.join(HERE, "certs"), exist_ok=True)
    results = []
    truths = {}
    if want_true:
        from true_clearance import true_clearance
    for name, mode, aimed, facets in PLAN:
        if prefixes and not any(name.startswith(p) for p in prefixes):
            continue
        parts, true_text, true_value = CASES[name]
        if want_true and name not in truths:
            truths[name] = true_clearance(parts)
            print(f"{name}: closed form {true_value:.9f}, dense search {truths[name]['true_by_search']:.9f}", flush=True)
        for N in facets:
            path = os.path.join(HERE, "certs", f"{name}_{mode}{'_aim' if aimed else ''}_{N}.json")
            if os.path.exists(path):
                os.remove(path)
            cert, rep = make(parts, N, holes=mode, log=lambda s: None, aimed=aimed)
            row = {"case": name, "holes": mode, "aimed": aimed, "aimed_sides": rep["aimed_sides"], "facets": N, "true_text": true_text, "true": true_value,
                   "true_by_search": truths.get(name, {}).get("true_by_search"),
                   "pieces_a": rep["pieces_a"], "pieces_b": rep["pieces_b"], "pairs": rep["pairs"],
                   "routes": rep["routes"], "unshown": rep["unshown"], "opened": rep["opened"],
                   "make_seconds": rep["seconds"], "shown": rep["shown_float"], "shown_exact": rep["shown"]}
            if cert is not None:
                began = time.perf_counter()
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(cert, f, separators=(",", ":"))
                row["write_seconds"] = time.perf_counter() - began
                row["bytes"] = os.path.getsize(path)
                row.update(run_checker(path))
                row["ratio"] = rep["shown_float"] / true_value
            else:
                row.update({"bytes": None, "proved": None, "ratio": None, "check_seconds": None})
            results.append(row)
            shown = "none" if row["shown"] is None else f"{row['shown']:.9f}"
            ratio = "-" if row["ratio"] is None else f"{row['ratio']:.6f}"
            print(f"{name:28s} {mode:4s}{' aim' if aimed else '    '} N={N:<4d} shown {shown:>12s} true {true_value:.9f} ratio {ratio:>9s} "
                  f"pieces {rep['pieces_a']}x{rep['pieces_b']}={rep['pairs']} make {rep['seconds']:.3f}s "
                  f"check {row.get('check_seconds')} bytes {row['bytes']} proved {row['proved']} routes {rep['routes']}", flush=True)
    out = os.path.join(HERE, "results.json" if not prefixes else "results_partial.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
