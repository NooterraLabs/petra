"""Material, fastener and shape data, each value tagged with the table it comes from."""

import json
import re
from dataclasses import dataclass
from fractions import Fraction as F
from functools import lru_cache
from pathlib import Path

E = F(29000)  # AISC 360-22 Symbols list, E = 29,000 ksi

# Fy and Fu, ksi. A992 and A572 Gr. 50 as the Companion quotes Manual Tables 2-4 and 2-5.
# A36 is ASTM A36's 36 and 58 ksi: the Manual table is not among the twin's sources.
GRADES = {
    "steel.A992": (F(50), F(65)),
    "steel.A572_50": (F(50), F(65)),
    "steel.A36": (F(36), F(58)),
}

# AISC 360-22 Table J3.2: Fnt, Fnv threads included (N), Fnv threads excluded (X), ksi.
BOLT_GROUPS = {
    "bolt_group.A307": (F(45), F(27), F(27)),
    "bolt_group.120": (F(90), F(54), F(68)),
    "bolt_group.144": (F(108), F(65), F(81)),
    "bolt_group.150": (F(113), F(68), F(84)),
    "bolt_group.200": (F(150), F(90), F(113)),
}

# AISC 360-22 Table J3.1, minimum pretension Tb in kips, by diameter in inches.
PRETENSION = {
    "bolt_group.120": {F(1, 2): 12, F(5, 8): 19, F(3, 4): 28, F(7, 8): 39, F(1): 51,
                       F(9, 8): 64, F(5, 4): 81, F(11, 8): 97, F(3, 2): 118},
    "bolt_group.150": {F(1, 2): 15, F(5, 8): 24, F(3, 4): 35, F(7, 8): 49, F(1): 64,
                       F(9, 8): 80, F(5, 4): 102, F(11, 8): 121, F(3, 2): 148},
    "bolt_group.200": {F(1): 90, F(9, 8): 113, F(5, 4): 143},
}
PRETENSION["bolt_group.144"] = PRETENSION["bolt_group.150"]

ELECTRODES = {"electrode.E70": F(70), "electrode.E80": F(80)}

# AISC 360-22 Table J3.3, by diameter: standard, oversize, short slot (w, l), long slot (w, l).
_HOLES = {
    F(1, 2): (F(9, 16), F(5, 8), (F(9, 16), F(11, 16)), (F(9, 16), F(5, 4))),
    F(5, 8): (F(11, 16), F(13, 16), (F(11, 16), F(7, 8)), (F(11, 16), F(25, 16))),
    F(3, 4): (F(13, 16), F(15, 16), (F(13, 16), F(1)), (F(13, 16), F(15, 8))),
    F(7, 8): (F(15, 16), F(17, 16), (F(15, 16), F(9, 8)), (F(15, 16), F(35, 16))),
    F(1): (F(9, 8), F(5, 4), (F(9, 8), F(21, 16)), (F(9, 8), F(5, 2))),
}


@dataclass(frozen=True)
class Hole:
    """A hole for a bolt of diameter d, with its dimension along the shear force (vertical) and
    across it."""

    kind: str
    d: F
    along: F
    across: F

    @property
    def long_slot_across_force(self):
        return self.kind == "lsl"

    def edge_increment(self, toward):
        """Table J3.5's C2 at an edge the hole's `toward` dimension, "along" or "across", reaches.
        A slot whose long axis lies parallel to that edge adds nothing."""
        if self.kind == "ovs":
            return F(1, 16) if self.d <= F(7, 8) else F(1, 8)
        if self.kind == "std" or getattr(self, toward) < max(self.along, self.across):
            return F(0)
        if self.kind.startswith("lsl"):
            return F(3, 4) * self.d
        return F(1, 8) if self.d <= 1 else F(3, 16)


def hole(d, kind="std"):
    if d in _HOLES:
        std, ovs, ssl, lsl = _HOLES[d]
    else:
        std, ovs, ssl, lsl = d + F(1, 8), d + F(5, 16), (d + F(1, 8), d + F(3, 8)), (d + F(1, 8), F(5, 2) * d)
    if kind == "std":
        return Hole(kind, d, std, std)
    if kind == "ovs":
        return Hole(kind, d, ovs, ovs)
    if kind in ("ssl", "lsl"):
        w, length = ssl if kind == "ssl" else lsl
        return Hole(kind, d, w, length)
    if kind in ("ssl_parallel", "lsl_parallel"):
        w, length = ssl if kind == "ssl_parallel" else lsl
        return Hole(kind, d, length, w)
    raise ValueError(f"unknown hole type {kind}")


@dataclass(frozen=True)
class WShape:
    name: str
    A: F
    d: F
    bf: F
    tw: F
    tf: F
    kdes: F
    k1: F
    Sx: F
    Zx: F


@dataclass(frozen=True)
class TeeShape:
    name: str
    d: F
    bf: F
    tw: F
    tf: F
    kdes: F
    k1: F


@dataclass(frozen=True)
class AngleShape:
    name: str
    long_leg: F
    short_leg: F
    t: F
    A: F
    x: F
    y: F
    kdes: F


@lru_cache(maxsize=1)
def _table():
    return json.loads((Path(__file__).parent / "shapes.json").read_text(encoding="utf-8"))


def _row(name):
    row = _table().get(name)
    if row is None:
        raise KeyError(f"shape {name} is not in twin/shapes.json")
    return {k: F(v) for k, v in row.items()}


def w_shape(name):
    if not name.startswith("W") or name.startswith("WT"):
        raise KeyError(f"{name} is not a W shape")
    r = _row(name)
    return WShape(name, r["A"], r["d"], r["bf"], r["tw"], r["tf"], r["kdes"], r["k1"], r["Sx"], r["Zx"])


def tee_shape(name):
    if not name.startswith("WT"):
        raise KeyError(f"{name} is not a WT shape")
    r = _row(name)
    m = re.fullmatch(r"WT(\d+(?:_\d+)?)x(\d+(?:_\d+)?)", name)
    depth, weight = (F(part.replace("_", ".")) for part in m.groups())
    parent = f"W{_spell(2 * depth)}x{_spell(2 * weight)}"
    return TeeShape(name, r["d"], r["bf"], r["tw"], r["tf"], r["kdes"], _row(parent)["k1"])


def _spell(value):
    text = str(float(value)).rstrip("0").rstrip(".")
    return text.replace(".", "_")


def angle_shape(name):
    """Legs and thickness are exact, read from the size in the name; the rest from the table."""
    m = re.fullmatch(r"L([0-9_]+)x([0-9_]+)x([0-9_]+)", name)
    if not m:
        raise KeyError(f"{name} is not an angle")
    a, b, t = (_dimension(part) for part in m.groups())
    r = _row(name)
    return AngleShape(name, max(a, b), min(a, b), t, r["A"], r["x"], r["y"], r["kdes"])


def _dimension(part):
    """`3_1_2` is 3-1/2 and `3_8` is 3/8 in the card's spelling of an angle size."""
    pieces = [int(p) for p in part.split("_")]
    if len(pieces) == 1:
        return F(pieces[0])
    if len(pieces) == 2:
        return F(pieces[0], pieces[1])
    return pieces[0] + F(pieces[1], pieces[2])
