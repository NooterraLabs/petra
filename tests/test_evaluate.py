"""Interval evaluation of expressions over a box."""
import unittest
from decimal import Decimal
from fractions import Fraction as F

from petra.kernel import (
    free_syms,
    Abs,
    Add,
    Const,
    Div,
    Exp,
    Interval,
    KernelArithmeticError,
    Ln,
    Max,
    Min,
    Mul,
    Neg,
    Pi,
    PowInt,
    Sqrt,
    Sym,
    enclose,
)

x, y = Sym("x"), Sym("y")
BOX = {"x": Interval(F(1), F(2)), "y": Interval(F(-3), F(4))}
PI_50 = F(Decimal("3.14159265358979323846264338327950288419716939937510"))


def c(v) -> Const:
    return Const(F(v))


class Enclose(unittest.TestCase):
    def test_each_operation_over_a_box(self):
        cases = [
            (c(5), (5, 5)),
            (x, (1, 2)),
            (Add((x, y, c(1))), (-1, 7)),
            (Add(()), (0, 0)),
            (Mul((x, y)), (-6, 8)),
            (Mul(()), (1, 1)),
            (Neg(y), (-4, 3)),
            (Div(y, x), (-3, 4)),
            (PowInt(y, 2), (0, 16)),
            (PowInt(y, 3), (-27, 64)),
            (Sqrt(PowInt(x, 2)), (1, 2)),
            (Abs(y), (0, 4)),
            (Min((x, y)), (-3, 2)),
            (Max((x, y)), (1, 4)),
            (Ln(c(1)), (0, 0)),
            (Exp(c(0)), (1, 1)),
        ]
        for expr, (lo, hi) in cases:
            self.assertEqual(enclose(expr, BOX), Interval(F(lo), F(hi)), repr(expr))

    def test_transcendental_leaves_contain_their_values(self):
        two_pi = enclose(Mul((c(2), Pi())), BOX)
        self.assertTrue(two_pi.lo < 2 * PI_50 < two_pi.hi)
        self.assertTrue(enclose(Ln(x), BOX).contains(F(1, 2)))
        self.assertTrue(enclose(Exp(x), BOX).contains(F(5)))

    def test_natural_extension_does_not_track_dependency(self):
        self.assertEqual(enclose(Add((x, Neg(x))), BOX), Interval(F(-1), F(1)))

    def test_undefined_operations_raise(self):
        for expr in [Div(c(1), y), Sqrt(y), Ln(y), PowInt(x, -1), Min(()), Max(())]:
            with self.assertRaises(KernelArithmeticError, msg=repr(expr)):
                enclose(expr, BOX)

    def test_missing_symbol_raises_key_error(self):
        with self.assertRaises(KeyError):
            enclose(Sym("z"), BOX)

    def test_shared_subterms_do_not_blow_up(self):
        e = x
        for _ in range(60):
            e = Add((e, e))
        self.assertEqual(enclose(e, {"x": Interval(F(1), F(1))}), Interval(F(2) ** 60, F(2) ** 60))


class Symbols(unittest.TestCase):
    def test_free_syms_walks_every_field(self):
        self.assertEqual(free_syms(Add((x, Mul((y, c(2))), Pi()))), {"x", "y"})
        self.assertEqual(free_syms((c(1), Pi())), frozenset())
        self.assertEqual(free_syms((x, Neg(Sym("z")))), {"x", "z"})


if __name__ == "__main__":
    unittest.main()
