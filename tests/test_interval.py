"""Exact rational intervals and rigorous sqrt, ln, exp and pi. Owner: K.

References come from the decimal module at 60 digits, and pi from its first 50 decimals,
never from the kernel. The kernel promises the two grid points around each irrational
value, so each check asserts the enclosure is exactly one grid cell that contains the
reference with room for the reference's own error.
"""
import unittest
from decimal import Decimal, localcontext
from fractions import Fraction as F

from lola.kernel.interval import (
    PRECISION_BITS,
    Interval,
    KernelArithmeticError,
    format_q,
    i_exp,
    i_ln,
    i_max,
    i_min,
    i_pi,
    i_sqrt,
    parse_q,
    round_out,
)

CELL = F(1, 2 ** PRECISION_BITS)
PI_50 = F(Decimal("3.14159265358979323846264338327950288419716939937510"))
SLACK = F(1, 10 ** 49)


def decimal_reference(fn) -> F:
    with localcontext() as ctx:
        ctx.prec = 60
        return F(fn())


def point(x) -> Interval:
    return Interval.point(F(x))


class Rationals(unittest.TestCase):
    def test_canonical_spellings_parse(self):
        for text, value in [("0", F(0)), ("-7", F(-7)), ("3/4", F(3, 4)), ("-3/4", F(-3, 4)), ("12345678901234567890/7", F(12345678901234567890, 7))]:
            self.assertEqual(parse_q(text), value, text)
            self.assertEqual(format_q(value), text, text)

    def test_every_other_spelling_is_refused(self):
        for text in ["1.5", "1e3", "+1", "-0", "01", "2/4", "3/1", "0/5", " 1", "1 ", "1/0", "1/-2", "１", "1_0", "", "/2", 1, 1.5, None]:
            with self.assertRaises(ValueError, msg=repr(text)):
                parse_q(text)

    def test_interval_needs_fraction_endpoints_in_order(self):
        for lo, hi in [(0.5, F(1)), (F(0), 1), (True, F(1))]:
            with self.assertRaises(TypeError, msg=repr((lo, hi))):
                Interval(lo, hi)
        with self.assertRaises(ValueError):
            Interval(F(2), F(1))

    def test_round_out_widens_to_the_dyadic_grid(self):
        self.assertEqual(round_out(F(1, 3), F(2, 3), 2), Interval(F(1, 4), F(3, 4)))
        self.assertEqual(round_out(F(1, 4), F(3, 4), 2), Interval(F(1, 4), F(3, 4)))
        self.assertEqual(round_out(F(-1, 3), F(-1, 3), 1), Interval(F(-1, 2), F(0)))


class Arithmetic(unittest.TestCase):
    def test_exact_operations(self):
        a, b = Interval(F(-2), F(3)), Interval(F(-5), F(4))
        self.assertEqual(a + b, Interval(F(-7), F(7)))
        self.assertEqual(a - b, Interval(F(-6), F(8)))
        self.assertEqual(-a, Interval(F(-3), F(2)))
        self.assertEqual(a * b, Interval(F(-15), F(12)))
        self.assertEqual(Interval(F(1), F(2)) / Interval(F(4), F(8)), Interval(F(1, 8), F(1, 2)))
        self.assertEqual(Interval(F(1), F(2)) / Interval(F(-8), F(-4)), Interval(F(-1, 2), F(-1, 8)))

    def test_division_by_an_interval_holding_zero_is_undefined(self):
        for den in [Interval(F(-1), F(1)), Interval(F(0), F(1)), Interval(F(-1), F(0)), point(0)]:
            with self.assertRaises(KernelArithmeticError):
                point(1) / den

    def test_powers(self):
        self.assertEqual(Interval(F(-2), F(3)).pow_int(2), Interval(F(0), F(9)))
        self.assertEqual(Interval(F(-3), F(-2)).pow_int(2), Interval(F(4), F(9)))
        self.assertEqual(Interval(F(-2), F(3)).pow_int(3), Interval(F(-8), F(27)))
        self.assertEqual(Interval(F(-2), F(3)).pow_int(0), point(1))
        self.assertEqual(Interval(F(1, 2), F(2)).pow_int(1), Interval(F(1, 2), F(2)))
        with self.assertRaises(KernelArithmeticError):
            point(2).pow_int(-1)

    def test_abs_min_max_and_set_operations(self):
        self.assertEqual(Interval(F(-5), F(3)).abs(), Interval(F(0), F(5)))
        self.assertEqual(Interval(F(-5), F(-3)).abs(), Interval(F(3), F(5)))
        self.assertEqual(Interval(F(2), F(3)).abs(), Interval(F(2), F(3)))
        a, b = Interval(F(1), F(4)), Interval(F(2), F(3))
        self.assertEqual(i_min(a, b), Interval(F(1), F(3)))
        self.assertEqual(i_max(a, b), Interval(F(2), F(4)))
        self.assertTrue(b.subset_of(a) and not a.subset_of(b))
        self.assertEqual(Interval(F(1), F(2)).hull(Interval(F(5), F(6))), Interval(F(1), F(6)))
        self.assertTrue(a.contains(F(4)) and not a.contains(F(9, 2)))
        self.assertEqual((a.width(), a.midpoint()), (F(3), F(5, 2)))


class Transcendentals(unittest.TestCase):
    def assertGridCell(self, enclosure: Interval, reference: F, name: str):
        self.assertEqual(enclosure.hi - enclosure.lo, CELL, f"{name}: one grid cell wide")
        self.assertEqual((enclosure.lo / CELL).denominator, 1, f"{name}: endpoints on the grid")
        self.assertLess(enclosure.lo, reference - SLACK * abs(reference), f"{name}: lower end below the value")
        self.assertGreater(enclosure.hi, reference + SLACK * abs(reference), f"{name}: upper end above the value")

    def test_sqrt_against_decimal(self):
        for x in [F(2), F(3), F(1, 3), F(10) ** 30 + 1, F(7, 10) ** 9]:
            ref = decimal_reference(lambda: Decimal(x.numerator).sqrt() / Decimal(x.denominator).sqrt())
            self.assertGridCell(i_sqrt(point(x)), ref, f"sqrt {x}")

    def test_sqrt_of_a_square_is_exact(self):
        self.assertEqual(i_sqrt(point(F(9, 4))), point(F(3, 2)))
        self.assertEqual(i_sqrt(point(0)), point(0))
        self.assertEqual(i_sqrt(Interval(F(1, 4), F(4))), Interval(F(1, 2), F(2)))

    def test_ln_against_decimal(self):
        for x in [F(2), F(10), F(1, 7), F(99, 100), F(10) ** 30, F(1, 3) ** 40]:
            ref = decimal_reference(lambda: (Decimal(x.numerator) / Decimal(x.denominator)).ln())
            self.assertGridCell(i_ln(point(x)), ref, f"ln {x}")

    def test_exp_against_decimal(self):
        for x in [F(1), F(-1), F(5, 2), F(-7, 3), F(40), F(1, 1000)]:
            ref = decimal_reference(lambda: (Decimal(x.numerator) / Decimal(x.denominator)).exp())
            self.assertGridCell(i_exp(point(x)), ref, f"exp {x}")

    def test_pi_against_fifty_digits(self):
        self.assertGridCell(i_pi(), PI_50, "pi")

    def test_rational_values_are_exact(self):
        self.assertEqual(i_ln(point(1)), point(0))
        self.assertEqual(i_exp(point(0)), point(1))

    def test_intervals_map_endpoint_to_endpoint(self):
        e = i_exp(Interval(F(-1), F(1)))
        self.assertEqual((e.lo, e.hi), (i_exp(point(-1)).lo, i_exp(point(1)).hi))
        ln = i_ln(Interval(F(1, 7), F(10)))
        self.assertEqual((ln.lo, ln.hi), (i_ln(point(F(1, 7))).lo, i_ln(point(10)).hi))
        r = i_sqrt(Interval(F(2), F(3)))
        self.assertEqual((r.lo, r.hi), (i_sqrt(point(2)).lo, i_sqrt(point(3)).hi))

    def test_inclusion_isotone(self):
        outer, inner = Interval(F(1, 3), F(5)), Interval(F(1, 2), F(4))
        for fn in (i_sqrt, i_ln, i_exp):
            self.assertTrue(fn(inner).subset_of(fn(outer)), fn.__name__)

    def test_undefined_arguments_raise(self):
        with self.assertRaises(KernelArithmeticError):
            i_sqrt(Interval(F(-1, 10 ** 30), F(4)))
        for bad in [Interval(F(0), F(1)), Interval(F(-2), F(-1))]:
            with self.assertRaises(KernelArithmeticError):
                i_ln(bad)


if __name__ == "__main__":
    unittest.main()
