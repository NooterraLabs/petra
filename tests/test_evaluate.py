"""Interval evaluation of expressions, free symbols, affine forms and vertex order. Owner: K."""
import unittest
from decimal import Decimal
from fractions import Fraction as F

from petra.kernel import (
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
    NotAffine,
    Pi,
    PowInt,
    Sqrt,
    Sym,
    affine_coefficients,
    enclose,
    free_syms,
)
from petra.kernel.evaluate import at_vertices, vertices
from petra.kernel.rules.r4_enclosure import AllNonpositive

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


class Structure(unittest.TestCase):
    def test_free_syms_walks_every_field(self):
        self.assertEqual(free_syms(Add((x, Mul((y, c(2))), Pi()))), {"x", "y"})
        self.assertEqual(free_syms(AllNonpositive(exprs=(x, Neg(Sym("z"))))), {"x", "z"})
        self.assertEqual(free_syms((c(1), Pi())), frozenset())

    def test_affine_forms(self):
        cases = [
            (Add((Mul((c(2), x)), c(3))), (3, (2, 0))),
            (Div(Add((x, Neg(y))), c(2)), (0, (F(1, 2), F(-1, 2)))),
            (Mul((c(3), x, c(F(1, 2)))), (0, (F(3, 2), 0))),
            (Mul((Sqrt(c(4)), y)), (0, (0, 2))),
            (Mul((PowInt(c(3), 2), x)), (0, (9, 0))),
            (PowInt(x, 1), (0, (1, 0))),
            (PowInt(y, 0), (1, (0, 0))),
            (Mul((Add((x, Neg(x))), y)), (0, (0, 0))),
            (Add(()), (0, (0, 0))),
        ]
        for expr, (c0, cs) in cases:
            self.assertEqual(affine_coefficients(expr, ("x", "y")), (F(c0), tuple(F(v) for v in cs)), repr(expr))

    def test_non_affine_forms_raise(self):
        for expr in [Mul((x, y)), Div(c(1), x), PowInt(x, 2), Sqrt(x), Mul((Pi(), x)), Sym("z"), Div(x, c(0)), Abs(x)]:
            with self.assertRaises(NotAffine, msg=repr(expr)):
                affine_coefficients(expr, ("x", "y"))

    def test_vertex_order_puts_the_first_symbol_in_the_low_bit(self):
        box = {"a": Interval(F(0), F(1)), "b": Interval(F(2), F(3))}
        expected = ({"a": 0, "b": 2}, {"a": 1, "b": 2}, {"a": 0, "b": 3}, {"a": 1, "b": 3})
        self.assertEqual(vertices(box, ("a", "b")), expected)
        self.assertEqual(vertices(box, ()), ({},))
        self.assertEqual(at_vertices((Add((Sym("a"), Mul((c(10), Sym("b"))))),), ("a", "b"), box), ((20,), (21,), (30,), (31,)))


if __name__ == "__main__":
    unittest.main()
