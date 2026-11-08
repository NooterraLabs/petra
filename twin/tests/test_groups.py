"""Instantaneous-center coefficients against the values the Companion examples read from the
Manual's Tables 7-6, 7-8, 8-8 and 10-11.

Tolerance: 1 percent. The Companion prints C to three figures, interpolated from tables built by
the same method on a coarser grid, so agreement to the third figure is the most the method can show.
"""

import unittest

from twin.groups import bolt_coefficient, bolt_grid, weld_strength

REL = 0.01


def weld_c(length, kl, ex):
    """Manual Table 8-8 C for a C-shaped weld, from the nominal strength of a 1/16 in. weld."""
    segments = [((0.0, 0.0), (0.0, -length)), ((0.0, 0.0), (kl, 0.0)), ((0.0, -length), (kl, -length))]
    return weld_strength(segments, ex, 1 / 16, 70.0) / length


class BoltGroupTest(unittest.TestCase):
    def check(self, value, expected):
        self.assertLess(abs(value / expected - 1), REL, f"{value:.4f} vs {expected}")

    def test_concentric_group_is_n(self):
        self.assertAlmostEqual(bolt_coefficient(bolt_grid(4, 1, 3.0, 0.0), 0.0), 4.0, places=9)

    def test_ii_a_17a_single_column_e_1_5(self):
        self.check(bolt_coefficient(bolt_grid(4, 1, 3.0, 0.0), 1.5), 3.54)

    def test_ii_a_17b_five_rows_inclined(self):
        self.check(bolt_coefficient(bolt_grid(5, 1, 3.0, 0.0), 2.5, angle_deg=30.0), 4.07)

    def test_ii_a_22_two_columns_e_12(self):
        self.check(bolt_coefficient(bolt_grid(6, 2, 3.0, 5.5), 12.0), 4.53)

    def test_ii_a_24_two_columns_e_16(self):
        self.check(bolt_coefficient(bolt_grid(6, 2, 3.0, 5.5), 16.0), 3.55)

    def test_ii_a_24_two_columns_inclined(self):
        self.check(bolt_coefficient(bolt_grid(6, 2, 3.0, 5.5), 14.0, angle_deg=15.0), 4.05)

    def test_ii_a_28a_table_10_11_case_i_is_e_2_5(self):
        # Example II.A-28A uses Table 10-11 Case I (C = 3.07) as a conservative bound for e < 2.5 in.
        self.check(bolt_coefficient(bolt_grid(4, 1, 3.0, 0.0), 2.5), 3.07)

    def test_ii_a_30_single_column_e_3_8(self):
        self.check(bolt_coefficient(bolt_grid(4, 1, 3.0, 0.0), 3.8), 2.45)


class WeldGroupTest(unittest.TestCase):
    def check(self, value, expected):
        self.assertLess(abs(value / expected - 1), REL, f"{value:.4f} vs {expected}")

    def test_ii_a_23_c_shape(self):
        self.check(weld_c(18.0, 3.0, 10.875), 1.46)

    def test_ii_a_26_c_shape(self):
        self.check(weld_c(10.0, 5.0, 8.75), 1.88)


if __name__ == "__main__":
    unittest.main()
