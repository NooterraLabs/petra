"""The exact evaluator on shapes whose answers are known: boxes at measured gaps, a box
inside a box, a wall of zero thickness, a surface that crosses itself."""
from __future__ import annotations

import random
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from petra.models.parts import exact
from petra.models.parts.mesh import Unit, read_mesh
from petra.models.parts.space import IDENTITY, Placement, Solid
from tests.parts_meshes import ascii_stl, box, flipped


def _mesh(tmp, name, tris):
    path, sha = ascii_stl(Path(tmp) / f"{name}.stl", tris)
    return read_mesh(path, sha, Unit.MM)


def _body(tmp, name, tris, offset=(0, 0, 0), den=None):
    m = _mesh(tmp, name, tris)
    solid = Solid(name, m, Placement(IDENTITY, tuple(Fraction(c) for c in offset)))
    return exact.place(solid, den or exact.denominator([Fraction(1, m.scale)], offset))


class Distances(unittest.TestCase):
    def test_triangles_at_known_distances(self):
        t = ((0, 0, 0), (4, 0, 0), (0, 4, 0))
        self.assertEqual(exact.tri_tri2(t, ((0, 0, 3), (4, 0, 3), (0, 4, 3))), 9)
        self.assertEqual(exact.tri_tri2(t, ((1, 1, -1), (1, 1, 1), (2, 1, 1))), 0, "an edge pierces t")
        self.assertEqual(exact.tri_tri2(t, ((5, 5, 0), (6, 5, 0), (5, 6, 0))), 18,
                         "coplanar, corner (5,5) to the hypotenuse x + y = 4 at (2,2)")

    def test_coplanar_corner_to_edge(self):
        t = ((0, 0, 0), (4, 0, 0), (0, 4, 0))
        self.assertEqual(exact.tri_tri2(t, ((3, 3, 0), (6, 3, 0), (3, 6, 0))), 2,
                         "(3,3) lies 2/sqrt(2) from x + y = 4, squared 2")

    def test_skew_edges(self):
        self.assertEqual(exact.seg_seg2((0, 0, 0), (2, 0, 0), (1, -1, 5), (1, 1, 5)), 25)
        self.assertEqual(exact.seg_seg2((0, 0, 0), (2, 2, 0), (0, 2, 1), (2, 0, 1)), 1)

    def test_against_dense_sampling(self):
        rng = random.Random(7)
        for _ in range(30):
            t = tuple(tuple(rng.randint(-5, 5) for _ in range(3)) for _ in range(3))
            u = tuple(tuple(rng.randint(-5, 5) for _ in range(3)) for _ in range(3))
            if exact.normal(t) == (0, 0, 0) or exact.normal(u) == (0, 0, 0):
                continue
            d = exact.tri_tri2(t, u)
            n = 6
            sampled = min(sum((p - q) ** 2 for p, q in zip(_bary(t, i, j, n), _bary(u, k, m, n)))
                          for i in range(n + 1) for j in range(n + 1 - i) for k in range(n + 1) for m in range(n + 1 - k))
            self.assertLessEqual(d, sampled, "the exact distance never exceeds a sampled one")
            self.assertLessEqual(float(sampled) ** 0.5 - float(d) ** 0.5, 15 / n, "and lies near it")


def _bary(t, i, j, n):
    return tuple(Fraction(i * a + j * b + (n - i - j) * c, n) for a, b, c in zip(*t))


class Prisms(unittest.TestCase):
    def test_sweep_reaches_what_the_rest_position_misses(self):
        u = ((0, 0, 0), (2, 0, 0), (0, 2, 0))
        t = ((0, 0, 10), (2, 0, 10), (0, 2, 10))
        self.assertEqual(exact.tri_tri2(t, u), 100)
        self.assertEqual(exact.tri_prism2(t, u, (0, 0, 20)), 0, "sweeping up 20 passes through t")
        self.assertEqual(exact.tri_prism2(t, u, (0, 0, 4)), 36)
        self.assertEqual(exact.tri_prism2(t, u, (5, 0, 0)), 100, "a sideways sweep stays in z = 0")

    def test_point_inside_the_hull(self):
        u = ((0, 0, 0), (4, 0, 0), (0, 4, 0))
        tiny = ((1, 1, 2), (2, 1, 2), (1, 2, 2))
        self.assertEqual(exact.tri_prism2(tiny, u, (0, 0, 5)), 0, "tiny lies inside the swept prism")


class Bodies(unittest.TestCase):
    def test_gap_between_boxes(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = _body(tmp, "b", box((0, 0, 0), (10, 10, 10)), offset=("10.25", 0, 0), den=100)
            a = _body(tmp, "a", box((0, 0, 0), (10, 10, 10)), den=100)
            near = exact.nearest(a, b, within=1000)
            self.assertEqual(near.d2 / 100 ** 2, Fraction(1, 16), "a 0.25 mm gap")
            self.assertIsNone(exact.nearest(a, b, within=10).d2, "nothing nearer than 0.1 mm")

    def test_touching_faces(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = _body(tmp, "a", box((0, 0, 0), (10, 10, 10)))
            b = _body(tmp, "b", box((0, 0, 0), (4, 4, 4)), offset=(3, 3, 10))
            self.assertEqual(exact.nearest(a, b, within=5).d2, 0)
            self.assertTrue(exact.touching(a, b))

    def test_parity(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = _body(tmp, "a", box((0, 0, 0), (10, 10, 10)))
            self.assertTrue(exact.inside((5, 5, 5), a))
            self.assertTrue(exact.inside((1, 9, 2), a))
            self.assertFalse(exact.inside((11, 5, 5), a))
            self.assertFalse(exact.inside((-1, -1, -1), a))
            self.assertIsNone(exact.inside((10, 5, 5), a), "on the surface")
            self.assertIsNone(exact.inside((10, 10, 10), a), "on a corner")
            hollow = _body(tmp, "h", box((0, 0, 0), (10, 10, 10)) + flipped(box((2, 2, 2), (8, 8, 8))))
            self.assertFalse(exact.inside((5, 5, 5), hollow), "the void is outside the material")
            self.assertTrue(exact.inside((1, 5, 5), hollow))

    def test_sweep_along_a_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = _body(tmp, "case", box((0, 0, 0), (10, 10, 2)))
            lid = _body(tmp, "lid", box((0, 0, 0), (10, 10, 1)), offset=(0, 0, 5))
            self.assertEqual(exact.nearest(case, lid, within=100).d2, 9)
            self.assertEqual(exact.nearest(case, lid, within=100, sweep=(0, 0, -4)).d2, 0, "moving down 4 lands on it")
            self.assertEqual(exact.nearest(case, lid, within=100, sweep=(0, 0, 4)).d2, 9, "moving up never comes nearer")


class Surfaces(unittest.TestCase):
    """A mesh whose edges are all shared by two faces can still fail to bound a solid."""

    def test_a_solid_has_no_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(exact.surface_problem(_mesh(tmp, "a", box((0, 0, 0), (10, 10, 10)))))
            hollow = box((0, 0, 0), (10, 10, 10)) + flipped(box((2, 2, 2), (8, 8, 8)))
            self.assertIsNone(exact.surface_problem(_mesh(tmp, "h", hollow)), "a void facing inward is a solid")
            apart = box((0, 0, 0), (10, 10, 10)) + box((20, 0, 0), (30, 10, 10))
            self.assertIsNone(exact.surface_problem(_mesh(tmp, "two", apart)), "two separate bodies")

    def test_zero_thickness_wall(self):
        with tempfile.TemporaryDirectory() as tmp:
            tris = box((0, 0, 0), (10, 10, 10)) + box((10, 2, 2), (20, 8, 8))
            problem = exact.surface_problem(_mesh(tmp, "w", tris))
            self.assertRegex(problem, "facing opposite ways", "the two bodies touch on a face of no thickness")

    def test_self_crossing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tris = box((0, 0, 0), (10, 10, 10)) + box((5, 5, 5), (15, 15, 15))
            self.assertRegex(exact.surface_problem(_mesh(tmp, "x", tris)), "crosses or touches itself")

    def test_inner_body_facing_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            tris = box((0, 0, 0), (10, 10, 10)) + box((2, 2, 2), (8, 8, 8))
            self.assertRegex(exact.surface_problem(_mesh(tmp, "n", tris)), "nested 1 deep and faces outward")


if __name__ == "__main__":
    unittest.main()
