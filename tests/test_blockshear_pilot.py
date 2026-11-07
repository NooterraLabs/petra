"""The block shear pilot (docs/blockshear_pilot.md): the trusted builder's exact geometry,
J4.3 by hand, the solver's HCT element, and the kernel's verdicts on a one-bolt plate.

Hand values for the 3 x 1 group, s = 3 in, Lev = Leh = 1.5 in, 3/4 in bolts, A992:
  dn = 13/16 + 1/16 = 7/8 in
  block (3, 1): Agv = 1.5 + 2 x 3 = 7.5, Anv = 7.5 - 2.5 x 7/8 = 5.3125, Ant = 1.5 - 7/16 = 1.0625
  rupture 0.6 x 65 x 5.3125 + 65 x 1.0625 = 276.25 kip/in, yield 0.6 x 50 x 7.5 + 69.0625 = 294.0625
  blocks (1, 1) and (2, 1) allow 3 x 110.5 = 331.5 and 1.5 x 193.375 = 290.0625, so (3, 1) governs
  J3.11: row 1 tearout 1.2 x (1.5 - 13/32) x 65 = 85.3125, rows 2-3 bearing 2.4 x 0.75 x 65 = 117,
  so the group's 319.3125 kip/in exceeds J4.3's 276.25 and J4.3 governs.
"""
import random
import unittest
from fractions import Fraction as Q

from petra.kernel import Evidence, Refutation, Rejection, Theorem, check
from petra.kernel.rules.r1_linear import FeasiblePoints
from petra.models.steel import blockshear as B
from petra.models.steel import blockshear_solve as S
from petra.registry import build_registry
from petra.units import CUSTOMARY

REGISTRY = build_registry()
IN = B.INCH
KSI = CUSTOMARY["ksi"][0]
TINY = B.Discretization(rings=0, cell=Q(2), box=Q(3, 4))


def plate(rows=1, cols=1, grade="A992", lev=Q(3, 2), leh=Q(3, 2)):
    return B.Plate(rows, cols, 3 * IN, 3 * IN, lev * IN, leh * IN, 2 * IN, grade, "bolt_us.3_4")


def area2(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])


class YieldSurface(unittest.TestCase):
    def test_shear_points_lie_on_the_unit_circle_in_order(self):
        pts = B.SHEAR_CIRCLE
        self.assertEqual(len(pts), 16)
        for k, (x, y) in enumerate(pts):
            self.assertEqual(x * x + y * y, 1)
            u, v = pts[(k + 1) % 16]
            self.assertGreater(x * v - y * u, 0, "consecutive points turn counter-clockwise")

    def test_meridian_points_lie_on_the_half_ellipse_in_order(self):
        for p, rho in B.MERIDIAN:
            self.assertEqual(p * p + 3 * rho * rho, 1)
            self.assertGreaterEqual(rho, 0)
        for (p0, r0), (p1, r1), (p2, r2) in zip(B.MERIDIAN, B.MERIDIAN[1:], B.MERIDIAN[2:]):
            self.assertGreater((p1 - p0) * (r2 - r0) - (r1 - r0) * (p2 - p0), 0, "the chords bound a convex polygon")

    def test_each_row_is_a_chord_through_its_two_points(self):
        rows = B.YIELD
        self.assertEqual(len(rows), 25)
        for k, row in enumerate(rows[:16]):
            for q, t in (B.SHEAR_CIRCLE[k], B.SHEAR_CIRCLE[(k + 1) % 16]):
                # rho = 1, sigma_xx - sigma_yy = 2 q, the row's left side at the point is zero
                self.assertEqual(row.sxx * q - row.syy * q + row.txy * t + row.rho, 0)
        for row, (p0, r0), (p1, r1) in zip(rows[16:], B.MERIDIAN, B.MERIDIAN[1:]):
            for p, r in ((p0, r0), (p1, r1)):
                self.assertEqual(row.sxx * p + row.syy * p + row.rho * r, row.rhs)
            self.assertGreater(row.rhs, 0, "the unstressed state is inside")

    def test_bounds_hold_on_the_von_mises_ellipsoid(self):
        self.assertGreater(B.NORMAL_BOUND ** 2, Q(4, 3))
        self.assertGreater(B.SHEAR_BOUND ** 2, Q(1, 3))
        self.assertLess(3 * B.SHEAR_CAP ** 2, 1)
        self.assertGreater(B.CONFINED_BOUND, Q(12, 5) * Q(58, 36), "J3.11's bearing at A36 fits in the zone")

    def test_points_inside_the_polygons_satisfy_von_mises(self):
        rng = random.Random(8)
        for _ in range(400):
            sxx, syy, txy = (Q(rng.randint(-1200, 1200), 1000) for _ in range(3))
            rho = max([Q(0)] + [(r.sxx * sxx + r.syy * syy + r.txy * txy) / -r.rho for r in B.YIELD[:16]])
            if all(r.sxx * sxx + r.syy * syy + r.txy * txy + r.rho * rho <= r.rhs for r in B.YIELD):
                self.assertLessEqual(sxx * sxx - sxx * syy + syy * syy + 3 * txy * txy, 1)


class Hole(unittest.TestCase):
    def test_the_polygon_circumscribes_the_hole(self):
        n = len(B.HOLE_TANGENTS)
        for k, (x, y) in enumerate(B.HOLE_TANGENTS):
            self.assertEqual(x * x + y * y, 1)
        for k, v in enumerate(B.HOLE_VERTICES):
            for j, u in enumerate(B.HOLE_TANGENTS):
                side = u[0] * v[0] + u[1] * v[1]
                if j in (k, (k - 1) % n):
                    self.assertEqual(side, 1)
                else:
                    self.assertLess(side, 1)

    def test_the_bearing_half_is_symmetric_about_the_row_line(self):
        n = len(B.HOLE_VERTICES)
        for k in range(n):
            x, y = B.HOLE_VERTICES[k]
            self.assertEqual(B.HOLE_VERTICES[(n - k) % n], (x, -y))
        self.assertEqual(B.HOLE_VERTICES[B.BEARING.start][0], 0)
        self.assertEqual(B.HOLE_VERTICES[B.BEARING.stop][0], 0)
        self.assertEqual({(n - 1 - k) % n for k in B.BEARING}, set(B.BEARING))


class Claim(unittest.TestCase):
    def test_j4_3_by_hand(self):
        p = B.Plate(3, 1, 3 * IN, 3 * IN, Q(3, 2) * IN, Q(3, 2) * IN, 2 * IN, "A992", "bolt_us.3_4")
        claim = B.j4_3(p, REGISTRY)
        self.assertEqual((claim.governing.k, claim.governing.j, claim.branch), (3, 1, "rupture"))
        self.assertEqual(claim.force / KSI, Q(27625, 100))
        self.assertEqual(claim.cfu, Q(17, 4))
        self.assertEqual([b.group / KSI for b in claim.blocks], [Q(3315, 10), Q(2900625, 10000), Q(27625, 100)])
        self.assertEqual(B.bearing(p, REGISTRY) / KSI, Q(3193125, 10000))

    def test_the_yield_branch_with_two_columns(self):
        p = B.Plate(2, 2, 3 * IN, 3 * IN, Q(5, 4) * IN, Q(5, 4) * IN, 2 * IN, "A36", "bolt_us.3_4")
        claim = B.j4_3(p, REGISTRY)
        b = claim.governing
        self.assertEqual(claim.force, min(min(x.rupture, x.yield_) * 4 / (x.k * x.j) for x in claim.blocks))
        self.assertEqual(claim.cfy * claim.fy + claim.cfu * claim.fu, claim.force)
        self.assertEqual(b.ubs, Q(1) if b.j == 1 else Q(1, 2))


class Mesh(unittest.TestCase):
    def test_the_mesh_covers_the_plate_less_its_holes_and_conforms(self):
        for rows, cols in ((1, 1), (2, 2)):
            p = plate(rows, cols)
            mesh = B.build_mesh(p, REGISTRY, TINY)
            area = sum(area2(*(mesh.points[v] for v in tri)) for tri in mesh.micro) / 2
            hole = sum(u[0] * v[1] - u[1] * v[0] for u, v in zip(B.HOLE_VERTICES, B.HOLE_VERTICES[1:] + B.HOLE_VERTICES[:1])) / 2
            self.assertEqual(area, mesh.length * mesh.breadth - rows * cols * hole * mesh.radius ** 2)
            sides = {}
            for tri in mesh.micro:
                self.assertGreater(area2(*(mesh.points[v] for v in tri)), 0)
                for a in range(3):
                    key = (min(tri[a], tri[(a + 1) % 3]), max(tri[a], tri[(a + 1) % 3]))
                    sides[key] = sides.get(key, 0) + 1
            for key, count in sides.items():
                self.assertIn(count, (1, 2))
                if count == 1:
                    self.assertIn(mesh.kind(*key)[0], ("free", "held", "hole"))

    def test_the_statement_names_the_grade_and_nothing_else(self):
        pilot = B.statement(plate(), REGISTRY, TINY, B.Flow("fy", Q(1)), "bearing")
        self.assertEqual({h.label for h in pilot.statement.hyps}, {"reg:steel.A992.fy", "reg:steel.A992.fu"})
        flow_fu = B.statement(plate(), REGISTRY, TINY, B.Flow("fu", Q(2)), "bearing")
        self.assertEqual({h.label for h in flow_fu.statement.hyps}, {"reg:steel.A992.fu"})


class Hct(unittest.TestCase):
    def test_hct_reproduces_a_cubic_exactly(self):
        rng = random.Random(1)
        a = [Q(rng.randint(-9, 9), rng.randint(1, 5)) for _ in range(10)]

        def grad(x, y):
            return (a[1] + 2 * a[3] * x + a[4] * y + 3 * a[6] * x * x + 2 * a[7] * x * y + a[8] * y * y,
                    a[2] + a[4] * x + 2 * a[5] * y + a[7] * x * x + 2 * a[8] * x * y + 3 * a[9] * y * y)

        def phi(x, y):
            return (a[0] + a[1] * x + a[2] * y + a[3] * x * x + a[4] * x * y + a[5] * y * y + a[6] * x ** 3
                    + a[7] * x * x * y + a[8] * x * y * y + a[9] * y ** 3)

        def hess(x, y):
            return (2 * a[3] + 6 * a[6] * x + 2 * a[7] * y, a[4] + 2 * a[7] * x + 2 * a[8] * y, 2 * a[5] + 2 * a[8] * x + 6 * a[9] * y)

        V = [(Q(0), Q(0)), (Q(3, 2), Q(1, 4)), (Q(1, 3), Q(5, 4))]
        N, edge = [], []
        for i in range(3):
            P0, P1 = V[(i + 1) % 3], V[(i + 2) % 3]
            n = (P1[1] - P0[1], P0[0] - P1[0])
            g = grad((P0[0] + P1[0]) / 2, (P0[1] + P1[1]) / 2)
            N.append(n)
            edge.append(g[0] * n[0] + g[1] * n[1])
        out = S.hct(V, [phi(*v) for v in V], [grad(*v) for v in V], edge, N)
        C = ((V[0][0] + V[1][0] + V[2][0]) / 3, (V[0][1] + V[1][1] + V[2][1]) / 3)
        for m in range(3):
            nodes = (V[m], V[(m + 1) % 3], C)
            for node, h in zip(nodes, out[m]):
                self.assertEqual(h, hess(*node))


class Verdicts(unittest.TestCase):
    """One bolt, Lev = Leh = 1.5 in, A992. J4.3's block (1, 1) allows 110.5 kip/in. Plane
    stress caps the bolt at (2/sqrt 3) Fy w = 47.9 kip/in, so the kernel refutes the bound at
    Fy; at a flow stress of 3 Fu the field carries J4.3's force and the kernel proves it."""

    def test_refuted_at_fy_and_both_programs_agree(self):
        pilot = B.statement(plate(), REGISTRY, TINY, B.Flow("fy", Q(1)), "bearing")
        airy = S.airy_program(pilot, S.airy(pilot))
        own = S.statement_program(pilot)
        self.assertLess(own.factor, 1)
        self.assertAlmostEqual(airy.factor, own.factor, places=6, msg="the Airy space is the statement's space")
        result = check(pilot.statement, Evidence(S.farkas_ray(pilot, own.y)))
        self.assertIsInstance(result, Refutation, getattr(result, "reason", ""))

    def test_proved_at_a_high_flow_stress_and_tampering_is_rejected(self):
        for contact in B.CONTACTS:
            pilot = B.statement(plate(), REGISTRY, TINY, B.Flow("fu", Q(3)), contact)
            field = S.airy(pilot)
            bound = S.airy_program(pilot, field)
            self.assertGreater(bound.factor, 1)
            points = S.feasible_points(pilot, field, bound.z)
            result = check(pilot.statement, Evidence(points))
            self.assertIsInstance(result, Theorem, f"{contact}: {getattr(result, 'reason', '')}")
            self.assertEqual(result.labels, frozenset({"reg:steel.A992.fu"}))
        x = list(points.x[0])
        x[pilot.pressure] *= Q(101, 100)
        self.assertIsInstance(check(pilot.statement, Evidence(FeasiblePoints((tuple(x),)))), Rejection)


if __name__ == "__main__":
    unittest.main()
