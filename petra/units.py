"""Exact units. Trusted front-end code: a wrong conversion changes every statement.

Every quantity is normalised to SI with exact rational factors when it is parsed, so
elaborators and the kernel see bare rationals in base units. Temperature is the one
exception: Petra's canonical temperature unit is degC, because every v0 formula (IEC
60287, IEC 60949, IEC 60228) is written in degC differences and no v0 model needs an
absolute temperature. A model that needs kelvin must convert explicitly with
`to_kelvin`, which makes the affine offset visible.
"""
from __future__ import annotations

import decimal
import re
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
TIME = Dim(s=1)
POWER = Dim(m=2, kg=1, s=-3)
RESISTANCE = Dim(m=2, kg=1, s=-3, A=-2)
RESISTANCE_PER_LENGTH = Dim(m=1, kg=1, s=-3, A=-2)


@dataclass(frozen=True, slots=True)
class Quantity:
    """An exact interval in SI base units (degC for temperature) with its dimension."""

    value: Interval
    dim: Dim


_ONE = Fraction(1)
_KILO = Fraction(1000)
_MILLI = Fraction(1, 1000)

UNITS: dict[str, tuple[Fraction, Dim]] = {
    "1": (_ONE, DIMENSIONLESS),
    "%": (Fraction(1, 100), DIMENSIONLESS),
    "m": (_ONE, LENGTH),
    "mm": (_MILLI, LENGTH),
    "cm": (Fraction(1, 100), LENGTH),
    "km": (_KILO, LENGTH),
    "mm2": (Fraction(1, 10**6), AREA),
    "m2": (_ONE, AREA),
    "N": (_ONE, FORCE),
    "kN": (_KILO, FORCE),
    "MN": (Fraction(10**6), FORCE),
    "Pa": (_ONE, STRESS),
    "kPa": (_KILO, STRESS),
    "MPa": (Fraction(10**6), STRESS),
    "GPa": (Fraction(10**9), STRESS),
    "A": (_ONE, CURRENT),
    "kA": (_KILO, CURRENT),
    "V": (_ONE, VOLTAGE),
    "kV": (_KILO, VOLTAGE),
    "ohm": (_ONE, RESISTANCE),
    "mohm": (_MILLI, RESISTANCE),
    "ohm/km": (_MILLI, RESISTANCE_PER_LENGTH),
    "W": (_ONE, POWER),
    "J": (_ONE, ENERGY),
    "Nm": (_ONE, TORQUE),
    "N m": (_ONE, TORQUE),
    "s": (_ONE, TIME),
    "ms": (_MILLI, TIME),
    "degC": (_ONE, TEMPERATURE),
    "A2s": (_ONE, I2T),
}
"""Unit spelling -> (factor to SI, dimension). The one table of unit spellings. The .petra
lexer cannot write "N m" or "ohm/km"; they serve format_quantity and callers outside
.petra text."""

_INCH = Fraction(127, 5000)
_LBF = Fraction(45359237, 10**8) * Fraction(980665, 10**5)
_KIP = 1000 * _LBF

CUSTOMARY: dict[str, tuple[Fraction, Dim]] = {
    "inch": (_INCH, LENGTH),
    "ft": (12 * _INCH, LENGTH),
    "inch2": (_INCH**2, AREA),
    "lbf": (_LBF, FORCE),
    "kip": (_KIP, FORCE),
    "kips": (_KIP, FORCE),
    "psi": (_LBF / _INCH**2, STRESS),
    "ksi": (_KIP / _INCH**2, STRESS),
    "kip_in": (_KIP * _INCH, TORQUE),
    "kip_ft": (_KIP * 12 * _INCH, TORQUE),
}
"""US customary spellings for the steel deck (AISC 360 is written in inches and kips),
exact by definition: 1 inch = 25.4 mm, 1 lbf = 0.45359237 kg x 9.80665 m/s2. Parsed and
formatted like UNITS, but readable_text and si_unit never choose one, so SI reports stay
SI. "in" is a .petra keyword, so the inch is spelled "inch"."""

_NAMED_DIMS: dict[Dim, str] = {
    DIMENSIONLESS: "dimensionless",
    LENGTH: "length",
    AREA: "area",
    FORCE: "force",
    STRESS: "stress",
    CURRENT: "current",
    VOLTAGE: "voltage",
    TEMPERATURE: "temperature",
    ENERGY: "energy",
    I2T: "I2t",
    TIME: "time",
    POWER: "power",
    RESISTANCE: "resistance",
    RESISTANCE_PER_LENGTH: "resistance per length",
}

_NUMBER = re.compile(r"[+-]?[0-9]+(?:\.[0-9]+|/[0-9]+)?")


def _parse_number(text: str) -> Fraction:
    if not _NUMBER.fullmatch(text):
        raise UnitError(f"malformed number {text!r}: write an integer, a decimal or p/q, with no exponent")
    try:
        return Fraction(text)
    except ZeroDivisionError:
        raise UnitError(f"malformed number {text!r}: zero denominator") from None


def _unit(unit: str) -> tuple[Fraction, Dim]:
    found = UNITS.get(unit) or CUSTOMARY.get(unit)
    if found is None:
        raise UnitError(f"unknown unit {unit!r}; known units: {', '.join(sorted({*UNITS, *CUSTOMARY}))}")
    return found


def _dim_text(dim: Dim) -> str:
    if dim in _NAMED_DIMS:
        return _NAMED_DIMS[dim]
    return " ".join(f"{base}^{exp}" for base, exp in zip(("m", "kg", "s", "A", "degC"), (dim.m, dim.kg, dim.s, dim.A, dim.degC)) if exp)


def parse_quantity(number: str, unit: str | None) -> Quantity:
    """Exact parse: "2.5" "mm2" -> 2.5e-6 m^2 as Fraction(1, 400000). Floats never appear:
    the number is parsed from its decimal text. Unknown unit -> UnitError."""
    x = _parse_number(number)
    factor, dim = _unit("1" if unit is None else unit)
    v = x * factor
    return Quantity(Interval(v, v), dim)


def require_dim(q: Quantity, dim: Dim, what: str) -> Quantity:
    """Boundary check used by lang/lower.py: raise UnitError naming `what` on mismatch."""
    if q.dim != dim:
        raise UnitError(f"{what}: expected {_dim_text(dim)}, got {_dim_text(q.dim)}")
    return q


_ZERO_CELSIUS_IN_KELVIN = Fraction(27315, 100)


def to_kelvin(t_degC: Interval) -> Interval:
    return Interval(t_degC.lo + _ZERO_CELSIUS_IN_KELVIN, t_degC.hi + _ZERO_CELSIUS_IN_KELVIN)


def _decimal_text(x: Fraction) -> str:
    """Exact when the decimal expansion terminates, otherwise six significant digits
    marked with a leading "~"."""
    d = x.denominator
    twos = fives = 0
    while d % 2 == 0:
        d //= 2
        twos += 1
    while d % 5 == 0:
        d //= 5
        fives += 1
    if d == 1:
        places = max(twos, fives)
        digits = abs(x.numerator) * 10**places // x.denominator
        whole, frac = divmod(digits, 10**places)
        text = str(whole) if places == 0 else f"{whole}.{frac:0{places}d}"
        return f"-{text}" if x < 0 else text
    approx = decimal.Context(prec=6).divide(decimal.Decimal(x.numerator), decimal.Decimal(x.denominator))
    return "~" + format(approx, "f")


def format_quantity(q: Quantity, unit: str) -> str:
    """For reports. Exact rational shown as a decimal with an exact/approx marker."""
    factor, dim = _unit(unit)
    require_dim(q, dim, f"formatting in {unit}")
    lo, hi = _decimal_text(q.value.lo / factor), _decimal_text(q.value.hi / factor)
    text = lo if q.value.lo == q.value.hi else f"[{lo}, {hi}]"
    return text if unit == "1" else f"{text} {unit}"


class UnitError(ValueError):
    pass


def si_unit(dim: Dim) -> str:
    """The SI spelling of a dimension, or its base-unit exponents when UNITS has no unit
    of factor 1 for it."""
    named = next((u for u, (factor, d) in UNITS.items() if factor == 1 and d == dim), None)
    if named is not None:
        return named
    return " ".join(f"{base}^{e}" for base, e in zip(("m", "kg", "s", "A", "degC"), (dim.m, dim.kg, dim.s, dim.A, dim.degC)) if e)


def interval_text(value: Interval) -> str:
    return str(value.lo) if value.lo == value.hi else f"[{value.lo}, {value.hi}]"


def quantity_text(q: Quantity) -> str:
    """A quantity in its SI unit, for reports."""
    unit = si_unit(q.dim)
    return format_quantity(q, unit) if unit in UNITS else f"{interval_text(q.value)} {unit}"


def readable_text(q: Quantity) -> str:
    """A quantity in the unit of its dimension with the largest factor that still leaves
    its magnitude at least 1 (300 MPa, not 300000000 Pa), preferring the SI unit among
    equal factors and never "%". quantity_text when no unit fits."""
    si = si_unit(q.dim)
    size = max(abs(q.value.lo), abs(q.value.hi))
    units = [(factor, name == si, name) for name, (factor, dim) in UNITS.items() if dim == q.dim and name != "%"]
    fitting = [u for u in units if u[0] <= size]
    if not units or size == 0:
        return quantity_text(q)
    return format_quantity(q, max(fitting or [min(units)])[2])
