"""Holds the mechanics layer (petra/mechanics, docs/mechanics.md) to its boundary and to
the physics it states.

The boundary: nothing in the layer can read a code's number.
- It imports no domain, no registry and no units.
- No function takes a registry lookup or has a default.
- Every numeric literal is an integer of geometry or statics.
- The steel twin imports neither the layer nor the deck's builders.
- The steel premise hash reads the layer's sources.

The physics: each formula is held to a brute-force computation of what it claims. The
brute force is written here from first principles and shares no formula with the layer:
- section properties by integrating over the section's rectangles, exactly, with the
  antiderivatives of |y| and y^2;
- bolt-group forces by summing every bolt;
- weld-group forces by cutting the weld into short pieces;
- the plate buckling stress by solving the plate's buckling equation by finite
  differences.
Where the brute force is exact (rationals throughout), so is the comparison.
"""
import ast
import math
import re
import unittest
from fractions import Fraction
from pathlib import Path

import numpy as np
from scipy.sparse import diags, identity, kron
from scipy.sparse.linalg import eigsh

from petra import mechanics as M
from petra.kernel import enclose
from petra.models.steel import vocab

ROOT = Path(__file__).resolve().parents[1]
LAYER = ROOT / "petra" / "mechanics"
FORBIDDEN = {"checks", "limits", "build", "calc", "domain"}
"""The deck builders the steel twin must not import (its docstring)."""


def exact(expr) -> Fraction:
    """The value of an expression with no irrational in it."""
    box = enclose(expr, {})
    assert box.lo == box.hi, "not an exact value"
    return box.lo


def num(expr) -> float:
    box = enclose(expr, {})
    return float((box.lo + box.hi) / 2)


def q(x) -> object:
    return M.c(Fraction(x))


# --- The boundary --------------------------------------------------------------------------------

DECIMAL = re.compile(r"\s*-?(\d*\.\d+|\d+/\d+)\s*")
ROW_NAME = re.compile(r"[a-z0-9_]+(\.[a-z0-9_]+)+")


class TheBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trees = {m: ast.parse((LAYER / f"{m}.py").read_text(encoding="utf-8")) for m in M.MODULES}
        cls.init = ast.parse((LAYER / "__init__.py").read_text(encoding="utf-8"))

    def test_every_module_of_the_package_is_listed(self):
        self.assertEqual({p.stem for p in LAYER.glob("*.py")} - {"__init__"}, set(M.MODULES))

    def test_the_layer_imports_only_the_kernel_and_itself(self):
        for name, tree in (*self.trees.items(), ("__init__", self.init)):
            for node in ast.walk(tree):
                with self.subTest(module=name, line=getattr(node, "lineno", 0)):
                    if isinstance(node, ast.Import):
                        self.assertEqual([a.name for a in node.names], ["os"])
                    elif isinstance(node, ast.ImportFrom):
                        self.assertTrue((node.level, node.module) in {(0, "__future__"), (0, "fractions"), (0, "typing"),
                                                                      (2, "kernel")}
                                        or (node.level == 1 and node.module in M.MODULES),
                                        f"imports {'.' * node.level}{node.module}")

    def test_no_function_takes_a_registry_lookup_or_has_a_default(self):
        for name, tree in self.trees.items():
            for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
                with self.subTest(module=name, function=fn.name):
                    self.assertNotIn("k", [a.arg for a in fn.args.args])
                    self.assertEqual(fn.args.defaults, [])
                    self.assertTrue(all(d is None for d in fn.args.kw_defaults))

    def test_every_numeric_literal_is_an_integer_and_no_string_names_a_registry_row(self):
        for name, tree in self.trees.items():
            for n in ast.walk(tree):
                if not isinstance(n, ast.Constant) or isinstance(n.value, bool):
                    continue
                with self.subTest(module=name, line=n.lineno, value=repr(n.value)[:40]):
                    self.assertNotIsInstance(n.value, (float, complex))
                    if isinstance(n.value, str):
                        self.assertIsNone(DECIMAL.fullmatch(n.value))
                        self.assertIsNone(ROW_NAME.fullmatch(n.value))

    def test_the_steel_twin_imports_neither_the_layer_nor_the_builders(self):
        tree = ast.parse((ROOT / "petra" / "models" / "steel" / "twin.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names = {node.module or ""} | {a.name for a in node.names}
                with self.subTest(line=node.lineno):
                    self.assertFalse(any("mechanics" in x for x in names))
                    if node.level == 1:
                        self.assertFalse(({node.module} if node.module else {a.name for a in node.names}) & FORBIDDEN)
            elif isinstance(node, ast.Import):
                self.assertFalse(any("mechanics" in a.name or "petra.models.steel." in a.name for a in node.names))

    def test_the_steel_premise_hash_reads_the_layer(self):
        self.assertLessEqual(set(M.SOURCES), set(vocab.HASHED))

    def test_every_parameter_is_glossed(self):
        text = (ROOT / "docs" / "mechanics.md").read_text(encoding="utf-8")
        glossed = {name for line in text.splitlines() if line.startswith("| `")
                   for name in re.findall(r"`([a-z_0-9]+)`", line.split("|")[1])}
        for module, tree in self.trees.items():
            for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
                for a in fn.args.args:
                    with self.subTest(function=f"{module}.{fn.name}", parameter=a.arg):
                        self.assertIn(a.arg, glossed)


# --- Sections: exact integrals over rectangles ------------------------------------------------------

def _area(pieces) -> Fraction:
    return sum(b * (y1 - y0) for y0, y1, b in pieces)


def _centroid(pieces) -> Fraction:
    return sum(b * (y1 * y1 - y0 * y0) / 2 for y0, y1, b in pieces) / _area(pieces)


def _first_moment(pieces, axis) -> Fraction:
    """The integral of |y - axis| dA, by the antiderivative u |u| / 2 of |u|."""
    def f(y):
        u = y - axis
        return u * abs(u) / 2
    return sum(b * (f(y1) - f(y0)) for y0, y1, b in pieces)


def _second_moment(pieces, axis) -> Fraction:
    """The integral of (y - axis)^2 dA."""
    return sum(b * ((y1 - axis) ** 3 - (y0 - axis) ** 3) / 3 for y0, y1, b in pieces)


def _area_below(pieces, axis) -> Fraction:
    return sum(b * (min(y1, axis) - y0) for y0, y1, b in pieces if y0 < axis)


def _plastic_axis(pieces) -> Fraction:
    """The y below which half the area lies, walking the rectangles (none of them a hole)
    from the bottom."""
    assert all(b > 0 for _, _, b in pieces)
    half, below = _area(pieces) / 2, Fraction(0)
    for y0, y1, b in sorted(pieces):
        if below + b * (y1 - y0) >= half:
            return y0 + (half - below) / b
        below += b * (y1 - y0)
    raise AssertionError("no axis")


def _cross(u, v) -> float:
    """The 2-D cross product u x v."""
    return float(u[0] * v[1] - u[1] * v[0])


class Sections(unittest.TestCase):
    def test_a_rectangles_moduli(self):
        for t, d in ((Fraction(3, 8), Fraction(18)), (Fraction(1, 2), Fraction(4)), (Fraction(8), Fraction(1, 2))):
            rect = [(-d / 2, d / 2, t)]
            self.assertEqual(exact(M.rectangle_plastic_modulus(q(t), q(d))), _first_moment(rect, Fraction(0)))
            self.assertEqual(exact(M.rectangle_elastic_modulus(q(t), q(d))), _second_moment(rect, Fraction(0)) / (d / 2))

    def test_the_thickness_at_which_a_rectangle_reaches_a_stress(self):
        moment, stress, d = Fraction(1350), Fraction(36), Fraction(12)
        t = exact(M.rectangle_elastic_thickness(q(moment), q(stress), q(d)))
        self.assertEqual(stress * _second_moment([(-d / 2, d / 2, t)], Fraction(0)) / (d / 2), moment)

    def test_a_rectangles_net_plastic_modulus(self):
        # holes as rectangles of negative width, at their places in the line
        for rows, pitch, hole, t, d in ((6, 3, Fraction(15, 16), Fraction(3, 8), 18), (5, 3, Fraction(13, 16), Fraction(1, 2), 15),
                                        (1, 3, Fraction(7, 8), Fraction(1, 4), 6), (2, Fraction(5, 2), 1, Fraction(5, 8), 8),
                                        (7, 3, Fraction(15, 16), Fraction(3, 4), 21)):
            with self.subTest(rows=rows):
                d, pitch = Fraction(d), Fraction(pitch)
                net = [(-d / 2, d / 2, t)] + [(y - hole / 2, y + hole / 2, -t)
                                             for y in ((i - Fraction(rows - 1, 2)) * pitch for i in range(rows))]
                self.assertEqual(_area_below(net, Fraction(0)), _area(net) / 2)    # the axis stays at mid-depth
                self.assertEqual(exact(M.rectangle_net_plastic_modulus(q(t), q(d), rows, q(pitch), q(hole))),
                                 _first_moment(net, Fraction(0)))

    def test_a_tees_moduli_with_its_plastic_axis_in_the_stem_and_in_the_flange(self):
        for hc, tw, bf, tf in ((Fraction(142, 10), Fraction(1, 4), Fraction(11, 2), Fraction(69, 200)),   # in the stem
                               (Fraction(3), Fraction(3, 10), Fraction(8), Fraction(3, 5)),                # in the flange
                               (Fraction(6), Fraction(1, 2), Fraction(5), Fraction(1, 2))):
            with self.subTest(hc=hc, bf=bf):
                tee = [(Fraction(0), tf, bf), (tf, hc, tw)]       # y from the flange's outer face
                ybar = _centroid(tee)
                self.assertGreater(hc - ybar, ybar)               # the stem's tip is the far fibre
                sc, zc = M.tee_moduli(q(hc), q(tw), q(bf), q(tf))
                self.assertEqual(exact(sc), _second_moment(tee, ybar) / (hc - ybar))
                self.assertEqual(exact(zc), _first_moment(tee, _plastic_axis(tee)))

    def test_a_circles_area(self):
        n, r = 200_000, 0.375                                     # a regular n-gon's area tends to the circle's
        self.assertAlmostEqual(num(M.circle_area(q(Fraction(3, 4)))), n / 2 * r * r * math.sin(2 * math.pi / n), places=9)

    def test_a_hexagons_corner(self):
        corners = [np.array([math.cos(math.pi * i / 3), math.sin(math.pi * i / 3)]) for i in range(6)]
        across = float(np.linalg.norm(corners[0] + corners[1]))   # twice the distance to a flat's midpoint
        self.assertAlmostEqual(num(M.hex_corner(M.c(Fraction(across)))), 1.0, places=12)

    def test_a_right_triangle_and_a_fillets_throat(self):
        for a, b in ((15, 9), (12, 12), (4, 20)):
            o, ta, tb = np.zeros(2), np.array([0.0, a]), np.array([b, 0.0])   # the right angle at o
            hyp = tb - ta
            cos = float(np.dot(o - ta, hyp) / (np.linalg.norm(o - ta) * np.linalg.norm(hyp)))
            normal = abs(_cross(hyp, o - ta)) / float(np.linalg.norm(hyp))
            got = [num(x) for x in M.right_triangle(q(a), q(b))]
            for g, w in zip(got, (math.sqrt(1 - cos * cos), cos, float(np.linalg.norm(hyp)), normal)):
                self.assertAlmostEqual(g, w, places=12)
        # an equal-leg fillet, its root at o and its legs w along the axes: the throat is
        # the distance from the root to the face
        w = 0.3125
        o, leg_a, leg_b = np.zeros(2), np.array([w, 0.0]), np.array([0.0, w])
        face = leg_b - leg_a
        self.assertAlmostEqual(num(M.fillet_throat(q(Fraction(5, 16)))), abs(_cross(face, o - leg_a)) / float(np.linalg.norm(face)),
                               places=12)


# --- Bolt groups: a sum over every bolt ---------------------------------------------------------------

def _bolts(rows: int, cols: int, s: Fraction, g: Fraction):
    """(x, y) of each bolt about the centroid; x across the columns, y along them."""
    return [((j - Fraction(cols - 1, 2)) * g, (i - Fraction(rows - 1, 2)) * s) for i in range(rows) for j in range(cols)]


def _forces(bolts, v: Fraction, e: Fraction):
    """Each bolt's force under v along the columns at e across them: an equal share of v,
    and the moment v e shared in proportion to each bolt's radius, normal to it."""
    ip = sum(x * x + y * y for x, y in bolts)
    m, n = v * e, len(bolts)
    return [(-m * y / ip, v / n + m * x / ip) for x, y in bolts]


PATTERNS = ((4, 1, 3, 0), (3, 2, 3, 3), (6, 2, 3, Fraction(11, 2)), (5, 3, Fraction(5, 2), 3), (2, 4, 3, 2))


class BoltGroups(unittest.TestCase):
    def test_the_polar_moment_and_the_corner_radius(self):
        for rows, cols, s, g in PATTERNS:
            with self.subTest(rows=rows, cols=cols):
                bolts = _bolts(rows, cols, Fraction(s), Fraction(g))
                self.assertEqual(exact(M.polar_moment(q(len(bolts)), rows, cols, q(s), q(g))), sum(x * x + y * y for x, y in bolts))
                self.assertAlmostEqual(num(M.corner_radius(rows, cols, q(s), q(g))),
                                       max(math.hypot(x, y) for x, y in bolts), places=12)

    def test_the_critical_bolt_carries_the_most(self):
        for rows, cols, s, g in PATTERNS:
            for v, e in ((Fraction(45), Fraction(3)), (Fraction(10), Fraction(33, 2)), (Fraction(7), Fraction(0))):
                with self.subTest(rows=rows, cols=cols, e=e):
                    forces = _forces(_bolts(rows, cols, Fraction(s), Fraction(g)), v, e)
                    fx, fy = (exact(x) for x in M.elastic_bolt_force(q(v), q(e), q(rows * cols), rows, cols, q(s), q(g)))
                    self.assertEqual(fx * fx + fy * fy, max(a * a + b * b for a, b in forces))
                    self.assertIn((fx, fy), {(abs(a), b) for a, b in forces})

    def test_a_blocks_resultant_on_the_side_the_twist_adds(self):
        for rows, cols, s, g in PATTERNS:
            bolts = _bolts(rows, cols, Fraction(s), Fraction(g))
            forces = dict(zip(bolts, _forces(bolts, Fraction(40), Fraction(8))))
            ys, xs = sorted({y for _, y in bolts}), sorted({x for x, _ in bolts})
            for k in range(1, rows + 1):
                for j in range(1, cols + 1):
                    with self.subTest(rows=rows, cols=cols, block=(k, j)):
                        def resultant(rows_of, cols_of):
                            held = [forces[b] for b in bolts if b[1] in rows_of and b[0] in cols_of]
                            return sum(a for a, _ in held), sum(b for _, b in held)
                        corners = [resultant(r, xs[-j:]) for r in (ys[:k], ys[-k:])]       # the +x side
                        fx, fy = (exact(x) for x in M.elastic_block_force(q(40), q(8), q(len(bolts)), rows, cols, q(s), q(g), k, j))
                        self.assertIn((fx, fy), {(abs(a), b) for a, b in corners})
                        others = [resultant(r, xs[:j]) for r in (ys[:k], ys[-k:])]          # the -x side
                        self.assertGreaterEqual(fx * fx + fy * fy, max(a * a + b * b for a, b in others))


# --- Weld groups: the weld cut into short pieces ----------------------------------------------------------

def _pieces(segments, n: int):
    """Midpoints and lengths of each segment ((x0, y0), (x1, y1)) cut into n pieces."""
    pts, dl = [], []
    for (x0, y0), (x1, y1) in segments:
        t = (np.arange(n) + 0.5) / n
        pts.append(np.column_stack((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)))
        dl.append(np.full(n, math.hypot(x1 - x0, y1 - y0) / n))
    return np.vstack(pts), np.concatenate(dl)


class WeldGroups(unittest.TestCase):
    def test_parallel_lines_bent_out_of_their_plane(self):
        v, e, length, lines = 30.0, 4.5, 12.0, 2
        pts, dl = _pieces([((0.0, -length / 2), (0.0, length / 2))] * lines, 20_000)
        y = pts[:, 1]
        # the parts rotate rigidly about the lines' horizontal axis: f = kappa y, with
        # kappa set so that the forces' moment is v e
        kappa = v * e / float(np.sum(y * y * dl))
        fh, fv = (num(x) for x in M.elastic_weld_line(q(v), q(Fraction(9, 2)), q(length), q(lines)))
        self.assertAlmostEqual(fh / (kappa * length / 2), 1.0, places=7)
        self.assertAlmostEqual(fv / (v / float(np.sum(dl))), 1.0, places=12)

    def test_a_c_shaped_weld_peaks_where_the_formula_says(self):
        length, ret, v = 10.0, 3.0, 10.0
        segments = [((0.0, -length / 2), (0.0, length / 2)), ((0.0, length / 2), (ret, length / 2)),
                    ((0.0, -length / 2), (ret, -length / 2))]
        pts, dl = _pieces(segments, 20_000)
        total = float(np.sum(dl))
        xc = float(np.sum(pts[:, 0] * dl)) / total
        ip = float(np.sum(((pts[:, 0] - xc) ** 2 + pts[:, 1] ** 2) * dl))
        # every point of the weld, its segments' ends included
        ends = np.array([p for seg in segments for p in seg])
        everywhere = np.vstack((pts, ends))
        for e in (12.0, 9.5, 0.4, 0.0):           # beyond the centroid, and between it and the vertical line
            with self.subTest(e=e):
                m = v * (e - xc)
                fx = -m * everywhere[:, 1] / ip
                fy = v / total + m * (everywhere[:, 0] - xc) / ip
                peak = float(np.max(np.hypot(fx, fy)))
                fh, tip, heel = (num(x) for x in M.elastic_weld_c(q(v), M.c(Fraction(e)), q(length), q(ret)))
                self.assertAlmostEqual(max(math.hypot(fh, tip), math.hypot(fh, heel)) / peak, 1.0, places=7)
                # and the components at the upper return's tip and heel
                for (x, y), f in (((ret, length / 2), tip), ((0.0, length / 2), heel)):
                    self.assertAlmostEqual(f, v / total + m * (x - xc) / ip, places=7)
                self.assertAlmostEqual(fh, m * (length / 2) / ip, places=7)


# --- Stability: the plate equation by finite differences ------------------------------------------

def _buckling_force(a: float, b: float, rigidity: float, nx: int, ny: int) -> float:
    """The least N (force per unit width, compressing along x) at which a plate a by b,
    simply supported on all four edges, buckles: D grad^4 w + N d^2w/dx^2 = 0. On a simply
    supported edge w = 0 and the bending moment is zero, so grad^2 w = 0 too, and grad^4
    is the square of the Laplacian with w = 0 on the edges."""
    def minus_d2(n, h):
        return diags([-np.ones(n - 1), 2 * np.ones(n), -np.ones(n - 1)], [-1, 0, 1]) / (h * h)
    ax, ay = minus_d2(nx, a / (nx + 1)), minus_d2(ny, b / (ny + 1))
    lap = kron(identity(ny), ax) + kron(ay, identity(nx))
    stiffness = (rigidity * (lap @ lap)).tocsc()
    geometric = kron(identity(ny), ax).tocsc()
    return float(eigsh(stiffness, k=1, M=geometric, sigma=0, which="LM", return_eigenvectors=False)[0])


class Stability(unittest.TestCase):
    def test_bryans_formula_against_the_plate_equation(self):
        e, nu, t, b = 200e9, 0.3, 0.01, 1.0
        rigidity = e * t ** 3 / (12 * (1 - nu ** 2))
        # a square plate buckles in one half-wave, k = 4; a plate 1.5 b long in two, k = (2/1.5 + 1.5/2)^2
        for aspect, nx, coefficient in ((1, 47, Fraction(4)), (Fraction(3, 2), 71, (Fraction(4, 3) + Fraction(3, 4)) ** 2)):
            with self.subTest(aspect=aspect):
                stress = _buckling_force(float(aspect) * b, b, rigidity, nx, 47) / t
                formula = num(M.plate_buckling_stress(q(int(e)), q(Fraction(3, 10)), M.c(coefficient), q(int(b / t))))
                self.assertLess(abs(formula / stress - 1), 2e-3)


if __name__ == "__main__":
    unittest.main()
