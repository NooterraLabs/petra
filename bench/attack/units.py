"""The units of docs/reference.md, written out again from their definitions.

The attacker keeps its own table so that a wrong factor in `petra/units.py` shows: a value it
writes in a unit is checked against the SI value this table gives, and a design it writes in
one unit is rewritten in another that must mean the same. Each factor is from the SI
Brochure and NIST SP 811, as the page lists them, and not copied from the reader.

A dimension is a tuple of exponents of metre, kilogram, second, ampere and degree Celsius.
"""
from __future__ import annotations

import re
from fractions import Fraction

Dim = tuple[int, int, int, int, int]

NONE: Dim = (0, 0, 0, 0, 0)
LENGTH: Dim = (1, 0, 0, 0, 0)
AREA: Dim = (2, 0, 0, 0, 0)
MASS: Dim = (0, 1, 0, 0, 0)
TIME: Dim = (0, 0, 1, 0, 0)
CURRENT: Dim = (0, 0, 0, 1, 0)
TEMPERATURE: Dim = (0, 0, 0, 0, 1)
FORCE: Dim = (1, 1, -2, 0, 0)
STRESS: Dim = (-1, 1, -2, 0, 0)
ENERGY: Dim = (2, 1, -2, 0, 0)
POWER: Dim = (2, 1, -3, 0, 0)
VOLTAGE: Dim = (2, 1, -3, -1, 0)
RESISTANCE: Dim = (2, 1, -3, -2, 0)
RESISTANCE_PER_LENGTH: Dim = (1, 1, -3, -2, 0)
I2T: Dim = (0, 0, 1, 2, 0)
FREQUENCY: Dim = (0, 0, -1, 0, 0)
CHARGE: Dim = (0, 0, 1, 1, 0)
SPEED: Dim = (1, 0, -1, 0, 0)
DENSITY: Dim = (-3, 1, 0, 0, 0)
STIFFNESS: Dim = (0, 1, -2, 0, 0)

_F = Fraction
INCH = _F(254, 10) / 1000                   # exactly 25.4 mm
FOOT = 12 * INCH
LB = _F(45359237, 10 ** 8)                  # the international pound, kg
LBF = LB * _F(980665, 10 ** 5)              # a pound of mass at standard gravity, 9.80665 m/s2
KIP = 1000 * LBF

FACTORS: dict[str, tuple[Fraction, Dim]] = {
    "%": (_F(1, 100), NONE),
    "m": (_F(1), LENGTH), "mm": (_F(1, 1000), LENGTH), "um": (_F(1, 10 ** 6), LENGTH), "cm": (_F(1, 100), LENGTH),
    "km": (_F(1000), LENGTH), "inch": (INCH, LENGTH), "ft": (FOOT, LENGTH), "mile": (5280 * FOOT, LENGTH),
    "mm2": (_F(1, 10 ** 6), AREA), "m2": (_F(1), AREA), "inch2": (INCH * INCH, AREA),
    "N": (_F(1), FORCE), "kN": (_F(1000), FORCE), "MN": (_F(10 ** 6), FORCE), "lbf": (LBF, FORCE), "kip": (KIP, FORCE), "kips": (KIP, FORCE),
    "Pa": (_F(1), STRESS), "kPa": (_F(1000), STRESS), "MPa": (_F(10 ** 6), STRESS), "GPa": (_F(10 ** 9), STRESS),
    "psi": (LBF / (INCH * INCH), STRESS), "ksi": (KIP / (INCH * INCH), STRESS),
    "uA": (_F(1, 10 ** 6), CURRENT), "mA": (_F(1, 1000), CURRENT), "A": (_F(1), CURRENT), "kA": (_F(1000), CURRENT),
    "V": (_F(1), VOLTAGE), "kV": (_F(1000), VOLTAGE),
    "ohm": (_F(1), RESISTANCE), "mohm": (_F(1, 1000), RESISTANCE), "kohm": (_F(1000), RESISTANCE), "Mohm": (_F(10 ** 6), RESISTANCE),
    "ohm/km": (_F(1, 1000), RESISTANCE_PER_LENGTH),
    "mW": (_F(1, 1000), POWER), "W": (_F(1), POWER), "kW": (_F(1000), POWER),
    "J": (_F(1), ENERGY), "Nm": (_F(1), ENERGY), "kip_in": (KIP * INCH, ENERGY), "kip_ft": (KIP * FOOT, ENERGY),
    "lbf_in": (LBF * INCH, ENERGY), "lbf_ft": (LBF * FOOT, ENERGY),
    "s": (_F(1), TIME), "ms": (_F(1, 1000), TIME), "min": (_F(60), TIME), "h": (_F(3600), TIME),
    "degC": (_F(1), TEMPERATURE),
    "g": (_F(1, 1000), MASS), "kg": (_F(1), MASS), "lb": (LB, MASS), "oz": (LB / 16, MASS),
    "A2s": (_F(1), I2T),
    "Hz": (_F(1), FREQUENCY), "rpm": (_F(1, 60), FREQUENCY),
    "mAh": (_F(18, 5), CHARGE), "Ah": (_F(3600), CHARGE),
    "m/s": (_F(1), SPEED), "km/h": (_F(1000, 3600), SPEED), "knot": (_F(1852, 3600), SPEED), "mph": (5280 * FOOT / 3600, SPEED),
    "kg/m3": (_F(1), DENSITY), "g/cm3": (_F(1000), DENSITY),
    "N/mm": (_F(1000), STIFFNESS),
}
"""Spelling -> (factor to SI, dimension). Temperature is in degC, and a value is the number on that scale."""

NAMES: dict[str, Dim] = {
    "dimensionless": NONE, "length": LENGTH, "area": AREA, "force": FORCE, "stress": STRESS, "moment": ENERGY, "energy": ENERGY,
    "mass": MASS, "time": TIME, "temperature": TEMPERATURE, "current": CURRENT, "voltage": VOLTAGE, "power": POWER,
    "resistance": RESISTANCE, "I2t": I2T, "charge": CHARGE,
}

POWERS = ("2", "3", "4")


def factor(unit: str) -> tuple[Fraction, Dim]:
    """The factor and dimension of a spelling, or of a unit of length to the power 2, 3 or 4. KeyError for none."""
    if not unit:
        return _F(1), NONE
    name, hat, power = unit.partition("^")
    if not hat:
        return FACTORS[unit]
    f, d = FACTORS[name]
    if d != LENGTH or power not in POWERS:
        raise KeyError(unit)
    return f ** int(power), tuple(int(power) * x for x in d)      # type: ignore[return-value]


def dim_of(text: str) -> Dim | None:
    """The dimension a deck's `dim` names: a name, `length^3`, `force/length`, `current*time`. None when it is none of these."""
    out = [0, 0, 0, 0, 0]
    sign = 1
    for op, token in re.findall(r"([*/]?)([A-Za-z0-9_]+(?:\^-?[0-9]+)?)", text.replace(" ", "")):
        name, _, power = token.partition("^")
        if name not in NAMES:
            return None
        sign = -1 if op == "/" else 1
        for i, x in enumerate(NAMES[name]):
            out[i] += sign * x * (int(power) if power else 1)
    return tuple(out)       # type: ignore[return-value]


def spellings(dim: Dim) -> list[str]:
    """Every spelling of this dimension, with the powers of a length."""
    found = [u for u, (_, d) in FACTORS.items() if d == dim]
    if dim == AREA:
        found.append("m^2")
    if dim == LENGTH:
        pass
    for p in POWERS:
        if dim == tuple(int(p) * x for x in LENGTH):
            found += [f"{u}^{p}" for u in ("mm", "cm", "m", "inch", "ft", "um", "km") if u in FACTORS]
    return found


_NUMBER = re.compile(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[+-]?\d+(?:\.\d+|/\d+)?")


def parse_value(text: str) -> tuple[Fraction, str] | None:
    """(number, unit) of a deck's value text such as `3/4 inch`, `1 1/8 inch`, `29,000 ksi` or `0.9`, or None when it is none of these."""
    t = text.strip()
    m = re.fullmatch(r"(\d+) (\d+)/(\d+)(?: +(.+))?", t)
    if m and int(m.group(3)):
        return _F(int(m.group(1))) + _F(int(m.group(2)), int(m.group(3))), (m.group(4) or "").strip()
    head, _, unit = t.partition(" ")
    if not _NUMBER.fullmatch(head):
        return None
    try:
        n = _F(head.replace(",", ""))
    except ZeroDivisionError:
        return None
    return n, unit.strip()


def si(text: str) -> Fraction | None:
    """The SI value of a deck's value text, by this table, or None."""
    p = parse_value(text)
    if p is None:
        return None
    try:
        return p[0] * factor(p[1])[0]
    except KeyError:
        return None


def number_text(x: Fraction, style: str = "auto") -> str:
    """A number as a design or a card writes it: an integer, a decimal that ends, or a fraction."""
    if x.denominator == 1:
        return str(x.numerator)
    d = x.denominator
    for p in (2, 5):
        while d % p == 0:
            d //= p
    if style in ("auto", "dec") and d == 1:
        digits = 0
        y = x
        while y.denominator != 1:
            y *= 10
            digits += 1
        if digits <= 14:
            sign = "-" if x < 0 else ""
            whole, frac = divmod(abs(x.numerator) * 10 ** digits // x.denominator, 10 ** digits)
            return f"{sign}{whole}.{str(frac).zfill(digits)}"
    return f"{x.numerator}/{x.denominator}"
