"""Exact units: every quantity becomes an exact rational in SI (degC for temperature) once,
at the parse boundary. Owner: L."""
import unittest
from fractions import Fraction

from petra.kernel import Interval
from petra.units import (
    AREA,
    CURRENT,
    DIMENSIONLESS,
    ENERGY,
    FORCE,
    I2T,
    LENGTH,
    STRESS,
    TEMPERATURE,
    TORQUE,
    VOLTAGE,
    Dim,
    Quantity,
    UnitError,
    format_quantity,
    parse_quantity,
    require_dim,
    to_kelvin,
)

TIME = Dim(s=1)
POWER = Dim(m=2, kg=1, s=-3)
OHM = Dim(m=2, kg=1, s=-3, A=-2)
OHM_PER_M = Dim(m=1, kg=1, s=-3, A=-2)


def point(x, dim) -> Quantity:
    return Quantity(Interval(Fraction(x), Fraction(x)), dim)


class Parse(unittest.TestCase):
    def test_every_unit_spelling_converts_to_its_si_factor(self):
        factors = {
            "1": (1, DIMENSIONLESS), "%": (Fraction(1, 100), DIMENSIONLESS),
            "m": (1, LENGTH), "mm": (Fraction(1, 1000), LENGTH), "cm": (Fraction(1, 100), LENGTH), "km": (1000, LENGTH),
            "mm2": (Fraction(1, 10**6), AREA), "m2": (1, AREA),
            "N": (1, FORCE), "kN": (1000, FORCE), "MN": (10**6, FORCE),
            "Pa": (1, STRESS), "kPa": (1000, STRESS), "MPa": (10**6, STRESS), "GPa": (10**9, STRESS),
            "A": (1, CURRENT), "kA": (1000, CURRENT), "V": (1, VOLTAGE), "kV": (1000, VOLTAGE),
            "ohm": (1, OHM), "mohm": (Fraction(1, 1000), OHM), "ohm/km": (Fraction(1, 1000), OHM_PER_M),
            "W": (1, POWER), "J": (1, ENERGY), "Nm": (1, TORQUE), "N m": (1, TORQUE),
            "s": (1, TIME), "ms": (Fraction(1, 1000), TIME), "degC": (1, TEMPERATURE), "A2s": (1, I2T),
        }
        for unit, (factor, dim) in factors.items():
            with self.subTest(unit=unit):
                self.assertEqual(parse_quantity("1", unit), point(factor, dim))

    def test_numbers_are_parsed_exactly_from_their_text(self):
        cases = [
            ("2.5", "mm2", Fraction(1, 400000), AREA),
            ("-24", "kN", Fraction(-24000), FORCE),
            ("0.1", None, Fraction(1, 10), DIMENSIONLESS),
            ("0.16", None, Fraction(4, 25), DIMENSIONLESS),
            ("3/10", None, Fraction(3, 10), DIMENSIONLESS),
            ("+1.5", "m", Fraction(3, 2), LENGTH),
            ("95", "%", Fraction(19, 20), DIMENSIONLESS),
        ]
        for number, unit, value, dim in cases:
            with self.subTest(number=number, unit=unit):
                q = parse_quantity(number, unit)
                self.assertEqual(q, point(value, dim))
                self.assertIs(type(q.value.lo), Fraction, "a float never appears")
                self.assertIs(type(q.value.hi), Fraction, "a float never appears")

    def test_an_unknown_unit_is_rejected(self):
        for unit in ("kNN", "K", "mm^2", "in", ""):
            with self.subTest(unit=unit), self.assertRaisesRegex(UnitError, "unknown unit"):
                parse_quantity("1", unit)

    def test_a_number_that_is_not_exact_text_is_rejected(self):
        for number in ("1e3", ".5", "1.", "1.5/2", "1/0", "0x10", " 1", "١"):
            with self.subTest(number=number), self.assertRaises(UnitError):
                parse_quantity(number, None)

    def test_degc_is_canonical_and_kelvin_is_an_explicit_offset(self):
        self.assertEqual(parse_quantity("10", "degC"), point(10, TEMPERATURE), "no offset at parse time")
        self.assertEqual(to_kelvin(Interval(Fraction(10), Fraction(40))), Interval(Fraction(28315, 100), Fraction(31315, 100)))


class RequireDim(unittest.TestCase):
    def test_a_matching_dimension_passes_through(self):
        q = point(24000, FORCE)
        self.assertIs(require_dim(q, FORCE, "load"), q)

    def test_a_mismatch_names_what_was_checked(self):
        with self.assertRaisesRegex(UnitError, "ambient"):
            require_dim(point(24000, FORCE), TEMPERATURE, "ambient")


class Format(unittest.TestCase):
    def test_exact_values_print_as_exact_decimals_in_the_unit(self):
        self.assertEqual(format_quantity(point(24000, FORCE), "kN"), "24 kN")
        self.assertEqual(format_quantity(Quantity(Interval(Fraction(-24000), Fraction(-16000)), FORCE), "kN"), "[-24, -16] kN")
        self.assertEqual(format_quantity(point(Fraction(1, 400000), AREA), "mm2"), "2.5 mm2")
        self.assertEqual(format_quantity(point(Fraction(3, 100), DIMENSIONLESS), "%"), "3 %")
        self.assertEqual(format_quantity(point(Fraction(-1, 8), DIMENSIONLESS), "1"), "-0.125")

    def test_a_non_terminating_value_is_marked_approximate(self):
        self.assertEqual(format_quantity(point(Fraction(1, 3), DIMENSIONLESS), "1"), "~0.333333")
        self.assertEqual(format_quantity(point(Fraction(2, 3), LENGTH), "m"), "~0.666667 m")

    def test_formatting_in_a_unit_of_another_dimension_is_rejected(self):
        with self.assertRaises(UnitError):
            format_quantity(point(24000, FORCE), "MPa")
        with self.assertRaises(UnitError):
            format_quantity(point(24000, FORCE), "furlong")


if __name__ == "__main__":
    unittest.main()
