"""Exact units. Trusted front-end code: a wrong conversion changes every statement.

Every quantity is normalised to SI with exact rational factors when it is parsed, so
elaborators and the kernel see bare rationals in base units. Temperature is the one
exception: LoLa's canonical temperature unit is degC, because every v0 formula (IEC
60287, IEC 60949, IEC 60228) is written in degC differences and no v0 model needs an
absolute temperature. A model that needs kelvin must convert explicitly with
`to_kelvin`, which makes the affine offset visible.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .kernel import Interval


@dataclass(frozen=True, slots=True)
class Dim:
    """Exponents of (m, kg, s, A, degC)."""

    m: int = 0
    kg: int = 0
    s: int = 0
    A: int = 0
    degC: int = 0


DIMENSIONLESS = Dim()
LENGTH = Dim(m=1)
AREA = Dim(m=2)
FORCE = Dim(m=1, kg=1, s=-2)
STRESS = Dim(m=-1, kg=1, s=-2)
CURRENT = Dim(A=1)
VOLTAGE = Dim(m=2, kg=1, s=-3, A=-1)
TEMPERATURE = Dim(degC=1)
ENERGY = Dim(m=2, kg=1, s=-2)
TORQUE = ENERGY
I2T = Dim(A=2, s=1)


@dataclass(frozen=True, slots=True)
class Quantity:
    """An exact interval in SI base units (degC for temperature) with its dimension."""

    value: Interval
    dim: Dim


UNITS: dict[str, tuple[Fraction, Dim]] = {}
"""Unit spelling -> (factor to SI, dimension). The one table of unit spellings.

TODO: m, mm, cm, km, mm2, m2, N, kN, MN, Pa, kPa, MPa, GPa, A, kA, V, kV, ohm, mohm,
  W, J, s, ms, degC, "%", "N m", "A2s", "ohm/km", "1" (dimensionless).
"""


def parse_quantity(number: str, unit: str | None) -> Quantity:
    """Exact parse: "2.5" "mm2" -> 2.5e-6 m^2 as Fraction(1, 400000). Floats never appear:
    the number is parsed from its decimal text. Unknown unit -> UnitError."""
    raise NotImplementedError


def require_dim(q: Quantity, dim: Dim, what: str) -> Quantity:
    """Boundary check used by lang/lower.py: raise UnitError naming `what` on mismatch."""
    raise NotImplementedError


def to_kelvin(t_degC: Interval) -> Interval:
    raise NotImplementedError


def format_quantity(q: Quantity, unit: str) -> str:
    """For reports. Exact rational shown as a decimal with an exact/approx marker."""
    raise NotImplementedError


class UnitError(ValueError):
    pass
