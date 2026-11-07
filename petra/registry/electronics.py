"""The electronics deck's data: resistor values, tolerance classes, temperature
coefficients, power and voltage ratings, LED and linear-regulator ratings. Trusted; each
row is a premise with a tag, an owner and a source.

What is here:
- IEC 60063 preferred values: the E24 and E96 mantissas, as constants
  "iec60063.E24.4_7" and "iec60063.E96.4_99". A resistor's nominal value is one mantissa
  times a power of ten, and lowering refuses a value outside its part's series.
- IEC 60062 tolerance letter codes F and J, and the IEC 60115 climatic category and
  rated ambient of surface-mount chip resistors, as constants.
- Parts, as registry materials (the steel deck's bolt groups are the precedent): chip
  resistors "res.*", chip LEDs "led.*", linear regulators "reg.*". The family says what a
  part is: resistor, led, regulator_fixed, regulator_floating (the LM317 style, whose
  reference sits between output and adjust) or regulator_grounded (an adjustable LDO
  whose reference sits between feedback and ground).

A spread is stated by its ends or its magnitude, never as one shared interval, because
two parts of one type vary independently: the model gives each part instance its own
variable over [-1, 1] or [0, 1] and reads the ends from here.

Every value below was written from memory of the standards and of typical manufacturer
datasheets. None has been checked against the published text, so each is tagged judged,
owned by petra-maintainers, and its source says "recalled". The E-series tables are also
checked by tests/test_electronics.py against the geometric series they round: E96 is
round(10^(i/96)) to three digits exactly, and each E24 value lies within 5 % of
10^(i/24). Upgrading a row to sanctioned is a one-line change once its text is checked.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Mapping

from ..kernel import Interval, Sym
from ..premises import Tag
from .model import Constant, Derived, Material, Stated

JUDGED = Tag.JUDGED
MAINTAINERS = "petra-maintainers"
RECALLED = "recalled and not checked against the published text"

MICRO = Fraction(1, 10**6)
MILLI = Fraction(1, 1000)


def _iv(x: str | Fraction, scale: Fraction = Fraction(1)) -> Interval:
    v = Fraction(x) * scale
    return Interval(v, v)


# --- IEC 60063 preferred values ---------------------------------------------------------

E24 = ("1.0 1.1 1.2 1.3 1.5 1.6 1.8 2.0 2.2 2.4 2.7 3.0 3.3 3.6 3.9 4.3 4.7 5.1 5.6 6.2 6.8 7.5 8.2 9.1").split()
E96 = ("1.00 1.02 1.05 1.07 1.10 1.13 1.15 1.18 1.21 1.24 1.27 1.30 1.33 1.37 1.40 1.43 1.47 1.50 1.54 1.58 "
       "1.62 1.65 1.69 1.74 1.78 1.82 1.87 1.91 1.96 2.00 2.05 2.10 2.15 2.21 2.26 2.32 2.37 2.43 2.49 2.55 "
       "2.61 2.67 2.74 2.80 2.87 2.94 3.01 3.09 3.16 3.24 3.32 3.40 3.48 3.57 3.65 3.74 3.83 3.92 4.02 4.12 "
       "4.22 4.32 4.42 4.53 4.64 4.75 4.87 4.99 5.11 5.23 5.36 5.49 5.62 5.76 5.90 6.04 6.19 6.34 6.49 6.65 "
       "6.81 6.98 7.15 7.32 7.50 7.68 7.87 8.06 8.25 8.45 8.66 8.87 9.09 9.31 9.53 9.76").split()
SERIES: Mapping[int, tuple[str, ...]] = {24: tuple(E24), 96: tuple(E96)}
"""Values per decade -> the series' mantissas, as decimal text with the series' digits."""


def series_key(steps: int, mantissa: str) -> str:
    """The constant of one mantissa: (96, "4.99") -> "iec60063.E96.4_99"."""
    return f"iec60063.E{steps}.{mantissa.replace('.', '_')}"


def _series_constants() -> list[Constant]:
    table = {24: "E24, the series of 24 values per decade", 96: "E96, the series of 96 values per decade"}
    return [Constant(series_key(steps, m), _iv(m), "1", JUDGED, MAINTAINERS,
                     f"IEC 60063:2015 preferred number series {table[steps]}; {RECALLED}",
                     f"the {table[steps].split(',')[0]} value {m}")
            for steps, values in SERIES.items() for m in values]


# --- IEC 60062 and IEC 60115 ------------------------------------------------------------

_CONSTANTS: tuple[tuple[str, Interval, str, str, str], ...] = (
    ("iec60062.F", _iv("1/100"), "1", "IEC 60062:2016 tolerance letter code F: plus or minus 1 %",
     "a resistor marked F is within 1 % of its nominal value"),
    ("iec60062.J", _iv("5/100"), "1", "IEC 60062:2016 tolerance letter code J: plus or minus 5 %",
     "a resistor marked J is within 5 % of its nominal value"),
    ("iec60115_1.reference_temperature", _iv(20), "degC",
     "IEC 60115-1 reference temperature of the resistance and its temperature coefficient",
     "a resistor's tolerance and temperature coefficient are stated about 20 degC"),
    ("iec60115_8.rated_ambient", _iv(70), "degC",
     "IEC 60115-8 rated ambient temperature of surface-mount fixed resistors",
     "a chip resistor carries its rated dissipation up to 70 degC ambient"),
    ("iec60115_8.upper_category", _iv(155), "degC",
     "IEC 60115-8 climatic category 55/155/56: upper category temperature",
     "a chip resistor of category 55/155/56 may run at up to 155 degC"),
    ("iec60115_8.lower_category", _iv(-55), "degC",
     "IEC 60115-8 climatic category 55/155/56: lower category temperature",
     "a chip resistor of category 55/155/56 may run at down to -55 degC"),
)
"""(name, value, unit, source, what it says)."""


def electronics_constants() -> dict[str, Constant]:
    rows = [Constant(name, value, unit, JUDGED, MAINTAINERS, f"{source}; {RECALLED}", statement)
            for name, value, unit, source, statement in _CONSTANTS]
    rows += _series_constants()
    table = {c.name: c for c in rows}
    if len(table) != len(rows):
        raise RuntimeError("an electronics constant is defined twice")
    return table


def _copy(name: str, unit: str) -> Derived:
    """A part property that is one constant, so its premise is that constant."""
    return Derived(Sym(f"const.{name}"), unit, note=f"the constant {name}")


def _stated(value: Interval, unit: str, source: str, conditions: str) -> Stated:
    return Stated(value, unit, JUDGED, MAINTAINERS, f"{source}; {RECALLED}", conditions)


# --- Chip resistors ---------------------------------------------------------------------

RESISTORS: Mapping[str, tuple[str, int, str, str, str, str, str, str, str]] = {
    "res.0603_1pct": ("0603", 96, "F", "100", "1/10", "75", "10", "1000000", "RC0603 F"),
    "res.0603_5pct": ("0603", 24, "J", "200", "1/10", "75", "10", "10000000", "RC0603 J"),
    "res.0805_1pct": ("0805", 96, "F", "100", "1/8", "150", "10", "1000000", "RC0805 F"),
    "res.1206_1pct": ("1206", 96, "F", "100", "1/4", "200", "10", "1000000", "RC1206 F"),
}
"""id -> (case size, values per decade, tolerance letter, temperature coefficient in
ppm/K, rated dissipation at the rated ambient in W, limiting element voltage in V, lowest
and highest value in ohm, the datasheet line). Thick-film chip resistors as the Yageo RC
series datasheet gives them."""

DATASHEET = "Yageo RC series thick-film chip resistor datasheet"


def _resistors() -> dict[str, Material]:
    out: dict[str, Material] = {}
    for mid, (case, steps, letter, tcr, p70, lev, r_min, r_max, line) in RESISTORS.items():
        where = f"{DATASHEET}, {line}"
        props = {
            "tolerance": _copy(f"iec60062.{letter}", "1"),
            "tcr": _stated(_iv(tcr, MICRO), "1/K", f"{where}: temperature coefficient {tcr} ppm/K",
                           f"{case} resistance changes by at most {tcr} ppm per kelvin from the reference temperature"),
            "p70": _stated(_iv(p70), "W", f"{where}: rated dissipation {p70} W at 70 degC",
                           f"{case} rated dissipation {p70} W up to the rated ambient"),
            "lev": _stated(_iv(lev), "V", f"{where}: maximum working voltage {lev} V",
                           f"{case} limiting element voltage {lev} V"),
            "r_min": _stated(_iv(r_min), "ohm", f"{where}: lowest value {r_min} ohm",
                             f"the series is made from {r_min} ohm"),
            "r_max": _stated(_iv(r_max), "ohm", f"{where}: highest value {r_max} ohm",
                             f"the series is made up to {r_max} ohm"),
            "steps": _stated(_iv(steps), "1", f"{where}: values from the IEC 60063 E{steps} series",
                             f"the series is made in the E{steps} values"),
            "t_ref": _copy("iec60115_1.reference_temperature", "degC"),
            "t_rated": _copy("iec60115_8.rated_ambient", "degC"),
            "t_upper": _copy("iec60115_8.upper_category", "degC"),
            "t_lower": _copy("iec60115_8.lower_category", "degC"),
        }
        tol = "1" if letter == "F" else "5"
        out[mid] = Material(mid, "resistor", f"{DATASHEET}: {case} thick-film chip resistor, {tol} % (E{steps}); "
                            f"{RECALLED}", props)
    return out


# --- Chip LEDs ----------------------------------------------------------------------------

LEDS: Mapping[str, tuple[str, str, str, str, str, str, str, str, str]] = {
    "led.red_0603": ("red AlInGaP", "1.65", "2.1", "5", "15", "25", "-2.5", "-1.5", "500"),
    "led.white_0603": ("white InGaN", "2.55", "3.0", "10", "20", "20", "-3.5", "-2", "500"),
}
"""id -> (die, threshold voltage V0 low and high in V, slope resistance Rd low and high in
ohm, maximum continuous forward current at 25 degC in mA, forward-voltage temperature
coefficient low and high in mV/K, junction-to-ambient thermal resistance in K/W). The
forward voltage is V0 + Rd I at 25 degC; the fit covers 1 mA up to the maximum current."""

LED_DATASHEET = "typical 0603 chip LED datasheet"


def _leds() -> dict[str, Material]:
    out: dict[str, Material] = {}
    for mid, (die, v0_lo, v0_hi, rd_lo, rd_hi, if_max, tc_lo, tc_hi, theta) in LEDS.items():
        where = f"{LED_DATASHEET} ({die}), forward voltage against current and temperature, fitted as V0 + Rd I"

        def s(value: Interval, unit: str, what: str, conditions: str) -> Stated:
            return _stated(value, unit, f"{where}: {what}", conditions)

        props = {
            "v0_min": s(_iv(v0_lo), "V", f"threshold voltage at least {v0_lo} V", f"V0 >= {v0_lo} V at 25 degC"),
            "v0_max": s(_iv(v0_hi), "V", f"threshold voltage at most {v0_hi} V", f"V0 <= {v0_hi} V at 25 degC"),
            "rd_min": s(_iv(rd_lo), "ohm", f"slope resistance at least {rd_lo} ohm", f"Rd >= {rd_lo} ohm"),
            "rd_max": s(_iv(rd_hi), "ohm", f"slope resistance at most {rd_hi} ohm", f"Rd <= {rd_hi} ohm"),
            "tc_min": s(_iv(tc_lo, MILLI), "V/K", f"forward voltage falls by at most {tc_lo[1:]} mV/K",
                        f"dVf/dT >= {tc_lo} mV/K"),
            "tc_max": s(_iv(tc_hi, MILLI), "V/K", f"forward voltage falls by at least {tc_hi[1:]} mV/K",
                        f"dVf/dT <= {tc_hi} mV/K"),
            "t_ref": s(_iv(25), "degC", "forward voltage stated at 25 degC", "Vf is stated at 25 degC"),
            "i_min": s(_iv(1, MILLI), "A", "the fit holds from 1 mA", "the forward-voltage fit holds from 1 mA"),
            "if_max": s(_iv(if_max, MILLI), "A", f"maximum continuous forward current {if_max} mA at 25 degC",
                        f"IF <= {if_max} mA at 25 degC ambient"),
            "t_knee": s(_iv(25), "degC", "the forward current derates from 25 degC ambient",
                        "IF max holds up to 25 degC ambient"),
            "t_upper": s(_iv(85), "degC", "the forward current derates linearly to zero at 85 degC ambient",
                         "IF max falls linearly to zero at 85 degC ambient"),
            "t_lower": s(_iv(-40), "degC", "operating temperature from -40 degC", "operates from -40 degC ambient"),
            "theta": s(_iv(theta), "K/W", f"junction-to-ambient thermal resistance {theta} K/W on a typical pad",
                       f"RthJA {theta} K/W"),
        }
        out[mid] = Material(mid, "led", f"{LED_DATASHEET}: 0603 {die} LED; {RECALLED}", props)
    return out


# --- Linear regulators ----------------------------------------------------------------------

def _regulator(mid: str, family: str, what: str, sheet: str, rows: Mapping[str, tuple[str, str, str]]) -> Material:
    """rows: prop -> (value text with unit scale applied by the unit, unit, what the sheet says)."""
    scale = {"V": Fraction(1), "A": Fraction(1), "mA": MILLI, "uA": MICRO, "K/W": Fraction(1), "degC": Fraction(1)}
    unit_of = {"mA": "A", "uA": "A"}
    props = {}
    for prop, (value, unit, said) in rows.items():
        props[prop] = _stated(_iv(value, scale[unit]), unit_of.get(unit, unit), f"{sheet}: {said}", f"{what}: {said}")
    return Material(mid, family, f"{sheet}: {what}; {RECALLED}", props)


LM317 = "TI LM317 datasheet (SLVS044), electrical characteristics"
LM1117 = "TI LM1117 datasheet (SNOS412), electrical characteristics"
ADJ_LDO = "typical 150 mA adjustable low-dropout regulator in SOT-23-5 (MIC5205-ADJ datasheet)"


def _regulators() -> dict[str, Material]:
    common_1117 = {
        "vdo_max": ("1.2", "V", "dropout at most 1.2 V at 800 mA"),
        "vin_max": ("15", "V", "input voltage at most 15 V"),
        "iout_max": ("800", "mA", "output current at most 800 mA"),
        "iq_max": ("10", "mA", "quiescent current at most 10 mA"),
        "theta_ja": ("60", "K/W", "junction-to-ambient thermal resistance 60 K/W in SOT-223"),
        "tj_max": ("125", "degC", "operating junction temperature at most 125 degC"),
        "tj_min": ("0", "degC", "operating junction temperature from 0 degC"),
    }
    return {
        "reg.lm317_to220": _regulator("reg.lm317_to220", "regulator_floating", "LM317 adjustable regulator, TO-220",
                                      LM317, {
            "vref_min": ("1.20", "V", "reference voltage at least 1.20 V"),
            "vref_max": ("1.30", "V", "reference voltage at most 1.30 V"),
            "iadj_max": ("100", "uA", "adjust-pin current at most 100 uA"),
            "vdo_max": ("3", "V", "reference specified from 3 V input-output differential"),
            "vdiff_max": ("40", "V", "input-output differential at most 40 V"),
            "iout_max": ("1.5", "A", "output current at most 1.5 A"),
            "iout_min": ("10", "mA", "minimum load current 10 mA to stay in regulation"),
            "theta_ja": ("50", "K/W", "junction-to-ambient thermal resistance 50 K/W in TO-220, free air"),
            "tj_max": ("125", "degC", "operating junction temperature at most 125 degC"),
            "tj_min": ("0", "degC", "operating junction temperature from 0 degC"),
        }),
        "reg.ldo1117_3v3_sot223": _regulator("reg.ldo1117_3v3_sot223", "regulator_fixed",
                                             "1117 fixed 3.3 V regulator, SOT-223", LM1117, {
            "vout_min": ("3.235", "V", "output voltage at least 3.235 V over line, load and temperature"),
            "vout_max": ("3.365", "V", "output voltage at most 3.365 V over line, load and temperature"),
            **common_1117,
        }),
        "reg.ldo1117_5v0_sot223": _regulator("reg.ldo1117_5v0_sot223", "regulator_fixed",
                                             "1117 fixed 5.0 V regulator, SOT-223", LM1117, {
            "vout_min": ("4.900", "V", "output voltage at least 4.900 V over line, load and temperature"),
            "vout_max": ("5.100", "V", "output voltage at most 5.100 V over line, load and temperature"),
            **common_1117,
        }),
        "reg.ldo_adj_sot23_5": _regulator("reg.ldo_adj_sot23_5", "regulator_grounded",
                                          "adjustable 150 mA low-dropout regulator, SOT-23-5", ADJ_LDO, {
            "vref_min": ("1.215", "V", "feedback reference at least 1.215 V"),
            "vref_max": ("1.265", "V", "feedback reference at most 1.265 V"),
            "ifb_max": ("1", "uA", "feedback-pin current at most 1 uA either way"),
            "vdo_max": ("0.35", "V", "dropout at most 0.35 V at 150 mA"),
            "vin_max": ("16", "V", "input voltage at most 16 V"),
            "iout_max": ("150", "mA", "output current at most 150 mA"),
            "iq_max": ("3", "mA", "ground current at most 3 mA"),
            "theta_ja": ("220", "K/W", "junction-to-ambient thermal resistance 220 K/W in SOT-23-5"),
            "tj_max": ("125", "degC", "operating junction temperature at most 125 degC"),
            "tj_min": ("-40", "degC", "operating junction temperature from -40 degC"),
        }),
    }


def electronics_materials() -> dict[str, Material]:
    return {**_resistors(), **_leds(), **_regulators()}
