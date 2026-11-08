"""The rolled shapes as the judge reads them, in inches.

W rows come from the AISC Shapes Database table Petra ships (or the user's own workbook
when PETRA_SHAPES_XLSX names it), read as the published decimal text through the table
loader, which interprets nothing. Angles and tees are read from their designations: an
angle's legs and thickness are its name, and a WT is half of the W it is cut from.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass
from fractions import Fraction

from petra.registry import steel_shapes


@dataclass(frozen=True)
class W:
    label: str
    d: Fraction
    bf: Fraction
    tf: Fraction
    tw: Fraction
    T: Fraction       # the workable flat depth between the fillets' toes (Manual Part 1)

    @property
    def toe(self) -> Fraction:
        """How far down from a flange's outer face the fillet reaches: the flat depth T sits
        centred on the web."""
        return (self.d - self.T) / 2


@dataclass(frozen=True)
class Angle:
    label: str
    long: Fraction
    short: Fraction
    t: Fraction


@dataclass(frozen=True)
class Tee:
    label: str
    parent: W
    depth: Fraction   # d / 2 of the parent W


@functools.lru_cache(maxsize=1)
def w_table() -> dict[str, W]:
    """"W18x50" -> its row. The key spells the designation as the .petra grammar does."""
    out = {}
    for row in steel_shapes.load().w:
        key = row["label"].replace("X", "x").replace(".", "_")
        out[key] = W(key, *(Fraction(row[p]) for p in ("d", "bf", "tf", "tw", "T")))
    return out


def w(designation: str) -> W | None:
    return w_table().get(designation)


def _number(text: str) -> Fraction:
    """"4" -> 4, "3_8" -> 3/8, "3_1_2" -> 7/2: a designation's inch dimension."""
    parts = text.split("_")
    if len(parts) == 1:
        return Fraction(parts[0])
    if len(parts) == 2:
        return Fraction(int(parts[0]), int(parts[1]))
    if len(parts) == 3:
        return int(parts[0]) + Fraction(int(parts[1]), int(parts[2]))
    raise ValueError(text)


def angle(designation: str) -> Angle | None:
    """"L4x3_1_2x3_8" -> legs 4 and 3-1/2, thickness 3/8."""
    if not designation.startswith("L"):
        return None
    try:
        a, b, t = (_number(p) for p in designation[1:].split("x"))
    except ValueError:
        return None
    return Angle(designation, max(a, b), min(a, b), t)


def _decimal_text(x: Fraction) -> str:
    return str(x.numerator) if x.denominator == 1 else f"{float(x):g}".replace(".", "_")


def tee(designation: str) -> Tee | None:
    """"WT9x25" -> half of W18x50; "WT5x22_5" -> half of W10x45."""
    if not designation.startswith("WT") or "x" not in designation:
        return None
    depth, weight = designation[2:].split("x", 1)
    try:
        parent = w(f"W{_decimal_text(2 * Fraction(depth))}x{_decimal_text(2 * Fraction(weight.replace('_', '.')))}")
    except ValueError:
        return None
    return None if parent is None else Tee(designation, parent, parent.d / 2)
