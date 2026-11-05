"""Exact sparse products, Gram sums and LDL^T products. Owner: K."""
import unittest
from fractions import Fraction as F

from lola.kernel import Interval, Matrix
from lola.kernel.linalg import dot, gram_quadratic, gram_sum, is_unit_lower, ldl_product, matvec, rmatvec

A = Matrix(2, 3, ((0, 0, F(1)), (0, 2, F(2)), (1, 1, F(-1))))
IDENTITY = Matrix(2, 2, ((0, 0, F(1)), (1, 1, F(1))))
COLUMN = Matrix(2, 1, ((0, 0, F(1)), (1, 0, F(2))))
L = Matrix(2, 2, ((0, 0, F(1)), (1, 0, F(-1, 3)), (1, 1, F(1))))


class Products(unittest.TestCase):
    def test_matvec_and_transpose(self):
        self.assertEqual(matvec(A, (F(1), F(2), F(3))), (F(7), F(-2)))
        self.assertEqual(rmatvec(A, (F(1), F(2))), (F(1), F(-2), F(2)))
        self.assertEqual(dot((F(1), F(2)), (F(3), F(-1, 2))), F(2))

    def test_gram_sum_by_hand(self):
        self.assertEqual(gram_sum((F(2), F(-1)), (COLUMN, IDENTITY)), {(0, 0): F(1), (0, 1): F(4), (1, 1): F(7)})

    def test_gram_sum_drops_cancelled_entries(self):
        self.assertEqual(gram_sum((F(1), F(-1)), (COLUMN, COLUMN)), {})

    def test_ldl_product_by_hand(self):
        self.assertEqual(ldl_product(L, (F(3, 4), F(2, 3))), {(0, 0): F(3, 4), (0, 1): F(-1, 4), (1, 1): F(3, 4)})

    def test_gram_quadratic_over_interval_weights(self):
        weights = (Interval(F(1), F(2)), Interval(F(-1), F(0)))
        self.assertEqual(gram_quadratic(weights, (IDENTITY, COLUMN), (F(1), F(1))), Interval(F(-7), F(4)))


class UnitLower(unittest.TestCase):
    def test_accepts_unit_lower_triangular(self):
        self.assertTrue(is_unit_lower(L, 2))
        self.assertTrue(is_unit_lower(IDENTITY, 2))
        self.assertTrue(is_unit_lower(Matrix(0, 0, ()), 0))

    def test_refuses_everything_else(self):
        cases = {
            "entry above the diagonal": Matrix(2, 2, ((0, 0, F(1)), (0, 1, F(5)), (1, 1, F(1)))),
            "diagonal entry 2": Matrix(2, 2, ((0, 0, F(2)), (1, 1, F(1)))),
            "missing diagonal entry": Matrix(2, 2, ((0, 0, F(1)), (1, 0, F(1)))),
            "wrong size": IDENTITY,
        }
        for name, M in cases.items():
            self.assertFalse(is_unit_lower(M, 3 if name == "wrong size" else 2), name)


if __name__ == "__main__":
    unittest.main()
