#!/usr/bin/env python3
"""The parts of every case, in the checker's part format. Running it writes parts/NAME.json.

Each case also carries its true clearance in closed form, as text and as a number. Those
closed forms are reasoned here by hand. true_clearance.py tests them by a dense search.
"""
from __future__ import annotations

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))

PLATE = {"kind": "box", "lo": [-30, -30, 0], "hi": [30, 30, 12],
         "holes": [{"axis": "z", "centre": [0, 0], "radius": "21/2"}]}
PLATE2 = {"kind": "box", "lo": [-30, -30, 32], "hi": [30, 30, 44],
          "holes": [{"axis": "z", "centre": [0, 0], "radius": "21/2"}]}


def pin(cx="0", lo=-5, hi=17):
    return {"kind": "cylinder", "axis": "z", "centre": [cx, 0], "radius": 10, "lo": lo, "hi": hi}


# the bar of the clevis: along x, its axis at y = 77/4, z = 45/2, radius 6
BAR = {"kind": "cylinder", "axis": "x", "centre": ["77/4", "45/2"], "radius": 6, "lo": -40, "hi": 40}

# wedge a: the sloping face 3x + 4z >= 105, unit normal (3, 0, 4)/5
WEDGE_A = {"kind": "polytope", "halfspaces": [[-3, 0, -4, -105], [1, 0, 0, 30], [0, 0, 1, 40], [0, 1, 0, 10], [0, -1, 0, 10]]}
# wedge b: the sloping face 2x + y + 2z >= 60, unit normal (2, 1, 2)/3
WEDGE_B = {"kind": "polytope", "halfspaces": [[-2, -1, -2, -60], [1, 0, 0, 30], [0, 0, 1, 40], [0, 1, 0, 20], [0, -1, 0, 20]]}
ROUND = {"kind": "cylinder", "axis": "z", "centre": [0, 0], "radius": 5, "lo": 0, "hi": 20}

# two blocks with holes: a plate with three holes, and a square bar with two cross holes
# that passes through the plate's middle hole
BLOCK_A = {"kind": "box", "lo": [-30, -30, 0], "hi": [30, 30, 12],
           "holes": [{"axis": "z", "centre": [0, 0], "radius": 10},
                     {"axis": "z", "centre": [-20, -20], "radius": 4},
                     {"axis": "z", "centre": [20, 20], "radius": 4}]}
BLOCK_B = {"kind": "box", "lo": [-6, -6, -10], "hi": [6, 6, 30],
           "holes": [{"axis": "x", "centre": [0, 20], "radius": 2},
                     {"axis": "y", "centre": [-5, 0], "radius": 2}]}
# the same with fewer holes, for the count of pieces
BLOCK_A2 = dict(BLOCK_A, holes=BLOCK_A["holes"][:2])
BLOCK_A1 = dict(BLOCK_A, holes=BLOCK_A["holes"][:1])
BLOCK_B1 = dict(BLOCK_B, holes=BLOCK_B["holes"][:1])
BLOCK_B0 = dict(BLOCK_B, holes=[])

CASES = {
    # name: (parts, the true clearance as text, as a number)
    "c1_pin_in_bore": ({"A": [PLATE], "B": [pin()]}, "21/2 - 10 = 1/2", 0.5),
    "c2_pin_off_centre": ({"A": [PLATE], "B": [pin("3/10")]}, "21/2 - 10 - 3/10 = 1/5", 0.2),
    # 3a: the clevis against the pin and the bar. The pin in its bores binds: 1/2.
    #     The bar is 45/2 - 6 - 12 = 9/2 above the lower plate and 32 - 45/2 - 6 = 7/2 under the upper.
    "c3a_clevis_vs_pin_and_bar": ({"A": [PLATE, PLATE2], "B": [pin(lo=-5, hi=49), BAR]}, "min(1/2, 7/2, 9/2) = 1/2", 0.5),
    # 3b: the clevis with its pin against the bar. Crossed bars: 77/4 - 10 - 6 = 13/4, under the 7/2 to the plate.
    "c3b_clevis_and_pin_vs_bar": ({"A": [PLATE, PLATE2, pin(lo=-5, hi=49)], "B": [BAR]}, "min(77/4 - 16, 7/2) = 13/4", 3.25),
    # 4a: the rim point (5, 0, 20) of the bar is 21 - (3*5 + 4*20)/5 = 2 from the sloping face
    "c4a_wedge_rim": ({"A": [WEDGE_A], "B": [ROUND]}, "21 - 19 = 2", 2.0),
    # 4b: the bar's greatest (2x + y + 2z)/3 is (5 sqrt 5 + 40)/3, the face is at 20
    "c4b_wedge_skew": ({"A": [WEDGE_B], "B": [ROUND]}, "20 - (40 + 5 sqrt 5)/3", 20 - (40 + 5 * math.sqrt(5)) / 3),
    # 5: the square bar's corner (6, 6) is 10 - 6 sqrt 2 from the wall of the middle hole
    "c5_blocks_3x2": ({"A": [BLOCK_A], "B": [BLOCK_B]}, "10 - 6 sqrt 2", 10 - 6 * math.sqrt(2)),
    "c5_blocks_2x1": ({"A": [BLOCK_A2], "B": [BLOCK_B1]}, "10 - 6 sqrt 2", 10 - 6 * math.sqrt(2)),
    "c5_blocks_1x0": ({"A": [BLOCK_A1], "B": [BLOCK_B0]}, "10 - 6 sqrt 2", 10 - 6 * math.sqrt(2)),
    "c5_blocks_1x1": ({"A": [BLOCK_A1], "B": [BLOCK_B1]}, "10 - 6 sqrt 2", 10 - 6 * math.sqrt(2)),
    "c5_blocks_2x2": ({"A": [BLOCK_A2], "B": [BLOCK_B]}, "10 - 6 sqrt 2", 10 - 6 * math.sqrt(2)),
}


def main() -> None:
    os.makedirs(os.path.join(HERE, "parts"), exist_ok=True)
    for name, (parts, _, _) in CASES.items():
        with open(os.path.join(HERE, "parts", name + ".json"), "w", encoding="utf-8") as f:
            json.dump(parts, f, indent=1)
    print(f"wrote {len(CASES)} files under parts/")


if __name__ == "__main__":
    main()
