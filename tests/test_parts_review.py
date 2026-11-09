"""The parts-core review's findings (2026-11-08), one test each. Every design here was
certified by parts-core at 4d62374 though a real part its premises allow breaks the rule,
or, for FF1, refuted for the way its mesh was triangulated. Each test checks the verdict
the premises give."""
from __future__ import annotations

import random
import tempfile
import unittest
from fractions import Fraction
from math import lcm
from pathlib import Path

from petra.models.base import ComponentError
from petra.models.parts import engine, exact
from petra.models.parts.mesh import MeshError, Unit, read_mesh
from petra.models.parts.space import IDENTITY, Placement, Solid
from tests.parts_meshes import ascii_stl, blind_block, box, flipped, pin, plate, tray, tube, write
from tests.test_parts_layer import SIGNED, part, run

MILL = "process.mill.al6061_3axis"
FDM = "process.print.fdm_petg_0_4"
AL = "aluminium.6061_T6"


def stack(base, base_hole, lid, lid_hole, screw, base_material=(AL, MILL), lid_extra="", extra=""):
    return (part("base", base, base_material[0], base_material[1], f"  {base_hole}") +
            part("lid", lid, AL, MILL, f"  {lid_hole}{lid_extra}") +
            "assembly stack {\n  place base at (0 mm, 0 mm, 0 mm) facing top front\n"
            "  place lid at (0 mm, 0 mm, 8 mm) facing top front\n  insert lid along bottom from 20 mm\n"
            f"  fasten f {screw} through lid.h into base.h\n{extra}}}\n")


LID_HOLE = "hole h at (10 mm, 10 mm, 3 mm) along bottom diameter 3.6 mm clear"


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def mesh(self, name, tris):
        return write(self.tmp, name, tris)

    def check(self, text):
        return run(text, self.tmp)


class F1PressFits(Case):
    def design(self, at):
        block = self.mesh("block", plate((0, 0, 0), (20, 20, 8), (10, 10), "1.51"))
        peg = self.mesh("peg", pin((10, 10), "1.51", 0, 8))
        signed = f"  tolerance in [0.0025 mm, 0.0025 mm] {SIGNED}"
        return self.check(
            part("block", block, AL, None, signed + "\n  hole h at (10 mm, 10 mm, 8 mm) along bottom diameter 3 mm press") +
            part("peg", peg, AL, None, signed) +
            "assembly fit {\n  place block at (0 mm, 0 mm, 0 mm) facing top front\n"
            f"  place peg at {at} facing top front\n  insert peg along bottom from 10 mm\n"
            "  press p peg into block.h diameter 3.02 mm interference 0.01 mm to 0.05 mm\n}\n")

    @unittest.expectedFailure
    def test_f1_a_pin_in_the_air_is_not_pressed(self):
        got = self.design("(40 mm, 0 mm, 30 mm)")
        self.assertEqual(got["fit.p/fit.press"][0], "refuted", got["fit.p/fit.press"])
        self.assertEqual(got["fit.peg/fit.insert"][0], "refuted", got["fit.peg/fit.insert"])

    @unittest.expectedFailure
    def test_f1_a_pin_buried_in_solid_material_fails(self):
        got = self.design("(-5 mm, -5 mm, 0 mm)")
        self.assertEqual(got["fit.peg/fit.insert"][0], "refuted", got["fit.peg/fit.insert"])
        self.assertNotEqual(got["fit.p/fit.press"][0], "certified", got["fit.p/fit.press"])


class F2Overflow(Case):
    @unittest.expectedFailure
    def test_f2_a_placed_coordinate_never_wraps(self):
        path, sha = ascii_stl(Path(self.tmp) / "bar.stl", box(("0", "0", "0"), ("1000.0000000001", "10", "10")))
        m = read_mesh(path, sha, Unit.MM)
        den = lcm(m.scale, engine.polygon_denominator() * 4)
        try:
            body = exact.place(Solid("bar", m, Placement(IDENTITY, (Fraction(6000), Fraction(0), Fraction(0)))), den)
        except (ValueError, ComponentError):
            return
        lo, hi = exact.extent(body)
        self.assertEqual((lo[0], hi[0]), (6000, Fraction("7000.0000000001")))

    @unittest.expectedFailure
    def test_f2_a_refuted_screw_stays_refuted_when_a_coordinate_gains_decimals(self):
        base = self.mesh("base", plate((0, 0, 0), (20, 20, 8), (10, 10), "1.3"))
        lid = self.mesh("lid", plate((0, 0, 0), (20, 20, 3), (10, 10), "1.8"))
        battery = ascii_stl(Path(self.tmp) / "battery.stl", box(("-80.000000000001", "0", "0"), ("20", "20", "10")))
        battery = (str(battery[0].resolve()).replace("\\", "/"), battery[1])
        got = self.check(
            part("base", base, AL, MILL, "  hole h at (10 mm, 10 mm, 8 mm) along bottom diameter 2.6 mm form") +
            part("battery", battery, AL, MILL) + part("lid", lid, AL, MILL, f"  {LID_HOLE}") +
            "assembly stack {\n  place base at (0 mm, 0 mm, 0 mm) facing top front\n"
            "  place battery at (0 mm, 0 mm, -10 mm) facing top front\n  insert battery along top from 20 mm\n"
            "  place lid at (0 mm, 0 mm, 8 mm) facing top front\n  insert lid along bottom from 20 mm\n"
            "  fasten f screw.M3x16_shcs through lid.h into base.h\n}\n")
        self.assertTrue("error" in got or got["stack.f/fit.fastener"][0] == "refuted", got)


class F3Threads(Case):
    def design(self, base_r, base_hole, screw, base_material=(AL, MILL), lid_r="1.8", lid_d="3.6"):
        base = self.mesh("base", plate((0, 0, 0), (20, 20, 8), (10, 10), base_r))
        lid = self.mesh("lid", plate((0, 0, 0), (20, 20, 3), (10, 10), lid_r))
        return self.check(stack(base, f"hole h at (10 mm, 10 mm, 8 mm) along bottom {base_hole}", lid,
                                f"hole h at (10 mm, 10 mm, 3 mm) along bottom diameter {lid_d} mm clear", screw,
                                base_material))

    @unittest.expectedFailure
    def test_f3_an_m3_thread_meets_no_wall_in_a_5_mm_form_hole(self):
        got = self.design("2.5", "diameter 5 mm form", "screw.M3x10_shcs")
        self.assertEqual(got["stack.f/fit.grip"][0], "refuted", got["stack.f/fit.grip"])

    @unittest.expectedFailure
    def test_f3_an_m3_thread_meets_no_wall_in_a_5_mm_tap_hole(self):
        got = self.design("2.5", "diameter 5 mm tap", "screw.M3x10_shcs")
        self.assertEqual(got["stack.f/fit.grip"][0], "refuted", got["stack.f/fit.grip"])

    @unittest.expectedFailure
    def test_f3_a_4_mm_insert_cannot_give_4_5_mm_of_thread(self):
        got = self.design("2.1", "diameter 4.2 mm insert insert.M3x4", "screw.M3x10_shcs", ("polymer.petg", FDM))
        self.assertEqual(got["stack.f/fit.grip"][0], "refuted", got["stack.f/fit.grip"])

    @unittest.expectedFailure
    def test_f3_an_m4_screw_does_not_thread_an_m3_insert(self):
        got = self.design("2.1", "diameter 4.2 mm insert insert.M3x5_7", "screw.M4x10_shcs", ("polymer.petg", FDM),
                          lid_r="2.6", lid_d="5.2")
        self.assertEqual(got["stack.f/fit.grip"][0], "refuted", got["stack.f/fit.grip"])


INSERT_HOLE = "  hole h at (10 mm, 10 mm, {top} mm) along bottom diameter 4.2 mm insert insert.M3x5_7"


class F4F5InsertHoles(Case):
    @unittest.expectedFailure
    def test_f4_an_insert_hole_is_read_from_the_mesh(self):
        block = self.mesh("block", plate((0, 0, 0), (20, 20, 8), (10, 10), "2.3"))
        got = self.check(part("block", block, "polymer.petg", FDM, INSERT_HOLE.format(top=8)))
        self.assertEqual(got["block.h/insert.hole_size"][0], "refuted", got["block.h/insert.hole_size"])

    @unittest.expectedFailure
    def test_f5_a_thin_standoff_wall_is_measured(self):
        standoff = self.mesh("standoff", tube((10, 10), "2.1", "2.5", 0, 20))
        got = self.check(part("standoff", standoff, "polymer.petg", FDM, INSERT_HOLE.format(top=20)))
        self.assertEqual(got["standoff.h/insert.boss_wall"][0], "refuted", got["standoff.h/insert.boss_wall"])


class F6F11F12F14Screws(Case):
    @unittest.expectedFailure
    def test_f6_a_screw_that_must_cut_solid_to_reach_its_hole_fails(self):
        base = self.mesh("base", blind_block((0, 0, 0), (20, 20, 10), (10, 10), "1.3", 5))
        lid = self.mesh("lid", plate((0, 0, 0), (20, 20, 3), (10, 10), "1.8"))
        got = self.check(
            part("base", base, AL, MILL, "  hole h at (10 mm, 10 mm, 5 mm) along top diameter 2.6 mm tap") +
            part("lid", lid, AL, MILL, "  hole h at (10 mm, 10 mm, 0 mm) along top diameter 3.6 mm clear") +
            "assembly stack {\n  place base at (0 mm, 0 mm, 0 mm) facing top front\n"
            "  place lid at (0 mm, 0 mm, -3 mm) facing top front\n  insert lid along top from 20 mm\n"
            "  fasten f screw.M3x16_shcs through lid.h into base.h\n}\n")
        self.assertEqual(got["stack.f/fit.fastener"][0], "refuted", got["stack.f/fit.fastener"])

    @unittest.expectedFailure
    def test_f11_a_countersunk_head_sits_below_the_mouth_and_bottoms_out(self):
        base = self.mesh("base", blind_block((0, 0, 0), (20, 20, 8), (10, 10), "1.3", "7.1"))
        lid = self.mesh("lid", plate((0, 0, 0), (20, 20, 3), (10, 10), "1.8", sink="3.6"))
        got = self.check(stack(base, "hole h at (10 mm, 10 mm, 8 mm) along bottom diameter 2.6 mm depth 7.1 mm tap", lid,
                               LID_HOLE + " countersink 7.2 mm", "screw.M3x10_csk"))
        self.assertEqual(got["stack.f/fit.grip"][0], "refuted", got["stack.f/fit.grip"])

    @unittest.expectedFailure
    def test_f12_two_screws_in_one_hole_fail(self):
        base = self.mesh("base", plate((0, 0, 0), (20, 20, 8), (10, 10), "1.3"))
        lid = self.mesh("lid", plate((0, 0, 0), (20, 20, 3), (10, 10), "1.8"))
        got = self.check(stack(base, "hole h at (10 mm, 10 mm, 8 mm) along bottom diameter 2.6 mm tap", lid, LID_HOLE,
                               "screw.M3x10_shcs", extra="  fasten g screw.M3x10_shcs through lid.h into base.h\n"))
        self.assertEqual(got["stack.f/fit.fastener"][0], "refuted", got["stack.f/fit.fastener"])
        self.assertEqual(got["stack.g/fit.fastener"][0], "refuted", got["stack.g/fit.fastener"])

    @unittest.expectedFailure
    def test_f14_the_tapped_hole_moves_the_screw_with_its_tolerance(self):
        base = self.mesh("base", plate((0, 0, 0), (20, 20, 8), (10, 10), "1.3"))
        lid = self.mesh("lid", plate((0, 0, 0), (20, 20, 3), (10, 10), "1.72"))
        got = self.check(stack(base, "hole h at (10 mm, 10 mm, 8 mm) along bottom diameter 2.6 mm tap", lid,
                               "hole h at (10 mm, 10 mm, 3 mm) along bottom diameter 3.4 mm clear", "screw.M3x10_shcs"))
        self.assertEqual(got["stack.f/fit.fastener"][0], "refuted", got["stack.f/fit.fastener"])


class F7F8Arrival(Case):
    @unittest.expectedFailure
    def test_f7_a_board_that_starts_inside_a_closed_case_fails(self):
        case = self.mesh("closed", box((0, 0, 0), (40, 30, 20)) + flipped(box((2, 2, 2), (38, 28, 18))))
        board = self.mesh("board", box((0, 0, 0), (30, 20, "1.6")))
        got = self.check(part("case", case) + part("board", board, "polymer.pc", None, f"  tolerance in [0.1 mm, 0.1 mm] {SIGNED}") +
                         "assembly box {\n  place case at (0 mm, 0 mm, 0 mm) facing top front\n"
                         "  place board at (5 mm, 5 mm, 2 mm) facing top front\n  insert board along bottom from 1 mm\n}\n")
        self.assertEqual(got["box.board/fit.insert"][0], "refuted", got["box.board/fit.insert"])

    @unittest.expectedFailure
    def test_f8_every_piece_of_a_mover_is_tested_for_containment(self):
        block = self.mesh("block", box((0, 0, 0), (40, 40, 40)))
        mover = self.mesh("mover", box((10, 10, 40), (20, 20, 50)) + box((10, 10, 10), (20, 20, 20)))
        got = self.check(part("block", block, AL, MILL) + part("mover", mover, AL, MILL) +
                         "assembly a {\n  place block at (0 mm, 0 mm, 0 mm) facing top front\n"
                         "  place mover at (0 mm, 0 mm, 0 mm) facing top front\n  insert mover along bottom from 1 mm\n}\n")
        self.assertEqual(got["a.mover/fit.insert"][0], "refuted", got["a.mover/fit.insert"])


class F9Shells(Case):
    @unittest.expectedFailure
    def test_f9_shells_joined_at_one_vertex_are_refused(self):
        v, x, y, z = (0, 0, 0), (10, 0, 0), (0, 10, 0), (0, 0, 10)
        a, b, c = (6, 2, 1), (2, 6, 1), (1, 1, 6)
        shells = self.mesh("shells", [(v, y, x), (v, x, z), (v, z, y), (x, y, z), (v, b, a), (v, a, c), (v, c, b), (a, b, c)])
        got = self.check(part("p", shells, AL, MILL) + "claim heavy: p.mass >= 0.5 g\n")
        self.assertIn("error", got)
        self.assertRegex(got["error"], "nested")

    @unittest.expectedFailure
    def test_f9_an_inward_piece_hung_on_one_vertex_is_refused(self):
        corner = (10, 10, 10)
        tet = [(corner, (12, 11, 11), (11, 12, 11)), (corner, (11, 12, 11), (11, 11, 12)),
               (corner, (11, 11, 12), (12, 11, 11)), ((12, 11, 11), (11, 11, 12), (11, 12, 11))]
        hung = self.mesh("hung", box((0, 0, 0), (10, 10, 10)) + tet)
        got = self.check(part("p", hung, AL, MILL) + "claim light: p.mass <= 10 g\n")
        self.assertIn("error", got)


class F10Mass(Case):
    @unittest.expectedFailure
    def test_f10_mass_is_bounded_over_the_tolerance(self):
        plate_ = self.mesh("plate", box((0, 0, 0), (10, 10, 1)))
        got = self.check(part("p", plate_, AL, MILL) + "claim light: p.mass <= 0.28 g\n")
        self.assertEqual(got["p/parts.mass/light"][0], "refuted", got["p/parts.mass/light"])

    @unittest.expectedFailure
    def test_f10_mass_is_bounded_over_the_finish_buildup(self):
        plate_ = self.mesh("plate", box((0, 0, 0), (10, 10, 1)))
        got = self.check(part("p", plate_, AL, MILL, "  finish process.powder_coat") + "claim light: p.mass <= 0.4 g\n")
        self.assertEqual(got["p/parts.mass/light"][0], "refuted", got["p/parts.mass/light"])


class F13F15Registry(Case):
    @unittest.expectedFailure
    def test_f13_a_head_at_its_least_diameter_can_pass_the_hole(self):
        base = self.mesh("base", plate((0, 0, 0), (20, 20, 8), (10, 10), "1.3"))
        lid = self.mesh("lid", plate((0, 0, 0), (20, 20, 3), (10, 10), "2.69"))
        got = self.check(
            part("base", base, AL, MILL, "  hole h at (10 mm, 10 mm, 8 mm) along bottom diameter 2.6 mm tap") +
            part("lid", lid, AL, None, f"  tolerance in [0.01 mm, 0.01 mm] {SIGNED}\n"
                                        "  hole h at (10 mm, 10 mm, 3 mm) along bottom diameter 5.37 mm clear") +
            "assembly stack {\n  place base at (0 mm, 0 mm, 0 mm) facing top front\n"
            "  place lid at (0 mm, 0 mm, 8 mm) facing top front\n  insert lid along bottom from 20 mm\n"
            "  fasten f screw.M3x10_shcs through lid.h into base.h\n}\n")
        self.assertEqual(got["stack.f/fit.seat"][0], "refuted", got["stack.f/fit.seat"])

    @unittest.expectedFailure
    def test_f15_a_print_tolerance_grows_with_the_part(self):
        bar = self.mesh("bar", box((0, 0, 0), (248, 10, 10)))
        got = self.check(part("bar", bar, "polymer.pla", "process.print.fdm_pla_0_4"))
        self.assertEqual(got["bar/print.volume"][0], "refuted", got["bar/print.volume"])


class FF1Sweeps(Case):
    def test_ff1_a_triangle_in_the_plane_of_a_swept_one_is_not_inside_the_sweep(self):
        u = ((0, 0, 0), (10, 0, 0), (0, 10, 0))
        t = ((100, 0, 0), (100, 10, 5), (110, 0, 5))
        self.assertEqual(exact.tri_prism2(t, u, (0, 0, 5)), 8100)

    def test_ff1_the_sweep_distance_agrees_with_dense_sampling(self):
        rng = random.Random(11)
        n = 6
        for _ in range(60):
            u = tuple(tuple(rng.randint(-4, 4) for _ in range(3)) for _ in range(3))
            if exact.normal(u) == (0, 0, 0):
                continue
            v = tuple(rng.randint(-3, 3) for _ in range(3))
            p = (Fraction(rng.randint(-2, 2)), Fraction(rng.randint(-2, 2)))
            corner = tuple(u[0][k] + p[0] * (u[1][k] - u[0][k]) + p[1] * (u[2][k] - u[0][k]) for k in range(3))
            t = (tuple(int(c) for c in corner),) + tuple(tuple(rng.randint(-6, 6) for _ in range(3)) for _ in range(2))
            if exact.normal(t) == (0, 0, 0):
                continue
            d = exact.tri_prism2(t, u, v)
            swept = [tuple(c + s * w for c, w in zip(q, v)) for s in (Fraction(i, n) for i in range(n + 1))
                     for q in _points(u, n)]
            sampled = min(sum((a - b) ** 2 for a, b in zip(x, y)) for x in _points(t, n) for y in swept)
            self.assertLessEqual(d, sampled, (t, u, v))
            self.assertLessEqual(float(sampled) ** 0.5 - float(d) ** 0.5, 30 / n, (t, u, v, d, sampled))

    def test_ff1_the_verdict_does_not_depend_on_how_a_wall_is_split(self):
        plain = tray((0, 0, 0), (40, 30, 20), 2, 2)
        p = (Fraction(2), Fraction(15), Fraction(3))
        a, b, c, d = [tuple(Fraction(x) for x in v) for v in ((2, 28, 20), (2, 2, 20), (2, 2, 2), (2, 28, 2))]
        wall = {frozenset((a, b, c)), frozenset((a, c, d))}
        split = [(p, a, b), (p, b, c), (p, c, d), (p, d, a)] + [t for t in plain if frozenset(t) not in wall]
        board_tris = box((0, 0, 0), (34, 24, "1.6"))
        board = self.mesh("board", board_tris[2:4] + board_tris[:2] + board_tris[4:])
        verdicts = []
        for name, tris in (("plain", plain), ("split", split)):
            case = self.mesh(name, tris)
            got = self.check(part("case", case) + part("board", board, "polymer.pc", None, f"  tolerance in [0.1 mm, 0.1 mm] {SIGNED}") +
                             "assembly box {\n  place case at (0 mm, 0 mm, 0 mm) facing top front\n"
                             "  place board at (3 mm, 3 mm, 2 mm) facing top front\n  insert board along bottom from 25 mm\n}\n")
            verdicts.append(got["box.board/fit.insert"][0])
        self.assertEqual(verdicts[0], verdicts[1])


def _points(t, n):
    return [tuple(Fraction(i * a + j * b + (n - i - j) * c, n) for a, b, c in zip(*t)) for i in range(n + 1) for j in range(n + 1 - i)]


class L1Cache(Case):
    @unittest.expectedFailure
    def test_l1_a_mesh_changed_on_disk_is_refused_under_its_old_hash(self):
        path, sha = ascii_stl(Path(self.tmp) / "cube.stl", box(("0", "0", "0"), ("10", "10", "10")))
        read_mesh(path, sha, Unit.MM)
        ascii_stl(Path(self.tmp) / "cube.stl", box(("0", "0", "0"), ("50", "10", "10")))
        with self.assertRaisesRegex(MeshError, "sha256"):
            read_mesh(path, sha, Unit.MM)


if __name__ == "__main__":
    unittest.main()
