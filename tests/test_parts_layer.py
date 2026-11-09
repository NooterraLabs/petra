"""The parts layer end to end: designs whose meshes are written here, checked through
petra.check, against answers worked by hand. Each failing design differs from a passing
one in one thing, so each FAIL is the rule's own (a mutation of the design, not the code)."""
from __future__ import annotations

import tempfile
import unittest

import petra
from tests.parts_meshes import box, bracket, flipped, pin, plate, tray, upright, write

HEAD = 'petra 0\ndesign "t" {\n  owner "a@b.c"\n  environment indoor_dry\n}\n'
SIGNED = 'signed "a@b.c" source "test"'


def part(name, mesh, material="polymer.petg", process="process.print.fdm_petg_0_4", extra=""):
    lines = [f'  mesh "{mesh[0]}" sha256 "{mesh[1]}" units mm', f"  material {material}"]
    if process:
        lines.append(f"  process {process}")
    return f"part {name} {{\n" + "\n".join(lines) + ("\n" + extra if extra else "") + "\n}\n"


def run(text: str, tmp: str) -> dict:
    out = petra.check(HEAD + text, path=f"{tmp}/t.petra", repair=False)
    if out["status"] == "INPUT_ERROR":
        return {"error": out["error"]}
    got = {}
    for verdict in out["verdicts"]:
        for ob in verdict["obligations"]:
            subject, mode, origin = ob["requirement"].split("/")[:3]
            key = f"{subject}/{mode}" + (f"/{origin[6:]}" if origin.startswith("claim.") else "")
            got[key] = (ob["outcome"], ob.get("describe"))
    return got


class Enclosure(unittest.TestCase):
    """A board dropped into a printed tray. The tray's pocket is 36 x 26 mm (measured from
    the mesh); PETG's tolerance is 0.5 mm (reported), the board's 0.1 mm (signed)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.case = write(self.tmp.name, "case", tray((0, 0, 0), (40, 30, 20), 2, 2))

    def tearDown(self):
        self.tmp.cleanup()

    def design(self, board_hi, at="(5 mm, 5 mm, 2 mm)", case=None, insert="insert board along bottom from 25 mm"):
        board = write(self.tmp.name, "board", box((0, 0, 0), board_hi))
        return (part("case", case or self.case) +
                part("board", board, "polymer.pc", None, f"  tolerance in [0.1 mm, 0.1 mm] {SIGNED}\n"
                                                          f"  mass in [8 g, 9 g] {SIGNED}") +
                "assembly box {\n  place case at (0 mm, 0 mm, 0 mm) facing top front\n"
                f"  place board at {at} facing top front\n  {insert}\n}}\n")

    def test_a_board_with_room_goes_in(self):
        got = run(self.design((30, 20, "1.6")), self.tmp.name)
        self.assertEqual(got["box.board/fit.insert"][0], "certified", got["box.board/fit.insert"])
        self.assertEqual(got["box.board/fit.connected"][0], "certified")
        self.assertRegex(got["box.board/fit.insert"][1], "rests on case")

    def test_a_positive_gap_tolerance_can_close_fails(self):
        # 0.25 mm each side (measured), less than 0.5 + 0.1 mm of allowance plus the float.
        got = run(self.design(("35.5", 20, "1.6"), at="(2.25 mm, 5 mm, 2 mm)"), self.tmp.name)
        self.assertEqual(got["box.board/fit.insert"][0], "refuted", got["box.board/fit.insert"])
        self.assertRegex(got["box.board/fit.insert"][1], r"case at 0\.25 mm")

    def test_a_board_sealed_in_a_closed_case_fails(self):
        closed = write(self.tmp.name, "closed", box((0, 0, 0), (40, 30, 20)) + flipped(box((2, 2, 2), (38, 28, 18))))
        got = run(self.design((30, 20, "1.6"), case=closed), self.tmp.name)
        self.assertEqual(got["box.board/fit.insert"][0], "refuted", "its path down crosses the lid")

    def test_every_body_but_the_base_says_how_it_arrives(self):
        got = run(self.design((30, 20, "1.6"), insert=""), self.tmp.name)
        self.assertRegex(got["error"], "board needs exactly one insert line")

    def test_a_board_floating_in_the_pocket_rests_on_nothing(self):
        got = run(self.design((30, 20, "1.6"), at="(5 mm, 5 mm, 6 mm)"), self.tmp.name)
        self.assertEqual(got["box.board/fit.insert"][0], "refuted")
        self.assertRegex(got["box.board/fit.insert"][1], "rests on nothing")
        self.assertEqual(got["box.board/fit.connected"][0], "refuted")

    def two_boards(self, second_x, least):
        a = write(self.tmp.name, "a", box((0, 0, 0), (10, 20, "1.6")))
        b = write(self.tmp.name, "b", box((0, 0, 0), (10, 20, "1.6")))
        signed = f"  tolerance in [0.1 mm, 0.1 mm] {SIGNED}"
        return (part("case", self.case) + part("a", a, "polymer.pc", None, signed) + part("b", b, "polymer.pc", None, signed) +
                "assembly box {\n  place case at (0 mm, 0 mm, 0 mm) facing top front\n"
                "  place a at (5 mm, 5 mm, 2 mm) facing top front\n"
                f"  place b at ({second_x} mm, 5 mm, 2 mm) facing top front\n"
                "  insert a along bottom from 25 mm\n  insert b along bottom from 25 mm\n"
                f"  gap a b {least} mm\n}}\n")

    def test_a_declared_gap_holds_beyond_allowances(self):
        # 1 mm plus 0.1 mm of each board's tolerance is 1.2 mm. Both boards float along z
        # on the case floor, across the gap, so their floats add nothing to it.
        got = run(self.two_boards(18, 1), self.tmp.name)
        self.assertEqual(got["box.a~b/fit.gap"][0], "certified", got["box.a~b/fit.gap"])
        self.assertRegex(got["box.a~b/fit.gap"][1], "a beyond")
        got = run(self.two_boards("16.1", 1), self.tmp.name)
        self.assertEqual(got["box.a~b/fit.gap"][0], "refuted", got["box.a~b/fit.gap"])
        self.assertRegex(got["box.a~b/fit.gap"][1], r"a at 1\.1 mm")

    def test_a_part_larger_than_the_build_volume_fails(self):
        long = write(self.tmp.name, "long", box((0, 0, 0), ("249.5", 10, 10)))
        got = run(part("bar", long), self.tmp.name)
        self.assertEqual(got["bar/print.volume"][0], "refuted", "249.5 mm grown by 0.5 mm each side passes 250 mm")
        short = write(self.tmp.name, "short", box((0, 0, 0), (248, 10, 10)))
        self.assertEqual(run(part("bar", short), self.tmp.name)["bar/print.volume"][0], "certified")

    def test_a_solid_assembly_states_its_centre_of_mass(self):
        machined = part("case", self.case, "aluminium.6061_T6", "process.mill.al6061_3axis")
        text = self.design((30, 20, "1.6")).replace(part("case", self.case), machined)
        text = text.replace("  mass in [8 g, 9 g]", "  cg (15 mm, 10 mm, 0.8 mm)\n  mass in [8 g, 9 g]")
        # The tray's centroid is at z = (24000 * 10 - 16848 * 11) / 7152 = 7.65 mm (measured); the
        # board's at 2.8 mm. 19.3 g of aluminium (2700 kg/m3) and 8 to 9 g of board: 6.0 to 6.2 mm.
        got = run(text + "claim low: box.cg_z <= 6.3 mm\nclaim lower: box.cg_z <= 5.9 mm\n", self.tmp.name)
        self.assertEqual(got["box/parts.cg/low"][0], "certified", got["box/parts.cg/low"])
        self.assertEqual(got["box/parts.cg/lower"][0], "refuted", got["box/parts.cg/lower"])

    def test_a_solid_assembly_over_its_mass_budget_fails(self):
        machined = part("case", self.case, "aluminium.6061_T6", "process.mill.al6061_3axis")
        text = self.design((30, 20, "1.6")).replace(part("case", self.case), machined)
        # 7152 mm3 (measured) of aluminium is 19.3 g (inferred), and the board 8 to 9 g (signed).
        got = run(text + "claim under: box.mass <= 30 g\nclaim over: box.mass <= 25 g\n", self.tmp.name)
        self.assertEqual(got["box/parts.mass/under"][0], "certified", got["box/parts.mass/under"])
        self.assertEqual(got["box/parts.mass/over"][0], "refuted", got["box/parts.mass/over"])

    def test_mass_and_centre_of_mass_claims(self):
        text = self.design((30, 20, "1.6")) + "claim light: box.mass <= 20 g\nclaim heavy: box.mass >= 9 g\n" \
                                              "claim low: box.cg_z <= 10 mm\n"
        got = run(text, self.tmp.name)
        # The tray is 7152 mm3 (measured) of PETG at 1.26 to 1.28 g/cm3 (guess): 9.01 to 9.15 g solid,
        # plus the board's 8 to 9 g (signed).
        self.assertEqual(got["box/parts.mass/light"][0], "certified", got["box/parts.mass/light"])
        self.assertEqual(got["box/parts.mass/heavy"][0], "open", "a printed part's infill can only lower its mass")
        self.assertEqual(got["box/parts.cg/low"][0], "open", "a printed tray's centre of mass needs its fill or a cg line")
        self.assertIn("error", run(self.design((30, 20, "1.6")) + "claim bad: box.cg_x <= 10 g\n", self.tmp.name))


class Fasteners(unittest.TestCase):
    """A milled plate screwed into a milled base, with a battery under the base. Mill
    tolerance is 0.13 mm (reported); the screw is ISO 4762 M3, its shank 3 mm across."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.base = write(t, "base", plate((0, 0, 0), (20, 20, 8), (10, 10), "1.3"))
        self.plate = write(t, "plate", plate((0, 0, 0), (20, 20, 3), (10, 10), "1.8"))
        self.sunk = write(t, "sunk", plate((0, 0, 0), (20, 20, 3), (10, 10), "1.8", sink="3.6"))
        self.battery = write(t, "battery", box((0, 0, 0), (20, 20, 10)))

    def tearDown(self):
        self.tmp.cleanup()

    def design(self, screw, top=None, top_hole="hole h at (10 mm, 10 mm, 3 mm) along bottom diameter 3.6 mm clear"):
        mill = "process.mill.al6061_3axis"
        return (part("base", self.base, "aluminium.6061_T6", mill,
                     "  hole h at (10 mm, 10 mm, 8 mm) along bottom diameter 2.6 mm form") +
                part("battery", self.battery, "aluminium.6061_T6", mill) +
                part("lid", top or self.plate, "aluminium.6061_T6", mill, f"  {top_hole}") +
                "assembly stack {\n  place base at (0 mm, 0 mm, 0 mm) facing top front\n"
                "  place battery at (0 mm, 0 mm, -10 mm) facing top front\n  insert battery along top from 20 mm\n"
                "  place lid at (0 mm, 0 mm, 8 mm) facing top front\n  insert lid along bottom from 20 mm\n"
                f"  fasten f {screw} through lid.h into base.h\n}}\n")

    def test_a_screw_that_fits(self):
        got = run(self.design("screw.M3x10_shcs"), self.tmp.name)
        for rule in ("fit.fastener", "fit.seat", "fit.grip"):
            self.assertEqual(got[f"stack.f/{rule}"][0], "certified", (rule, got[f"stack.f/{rule}"]))
        self.assertEqual(got["base.h/fit.hole"][0], "certified", got["base.h/fit.hole"])
        self.assertEqual(got["lid.h/fit.hole"][0], "certified", got["lid.h/fit.hole"])
        self.assertRegex(got["stack.f/fit.grip"][1], "engages 7 mm")

    def test_a_screw_too_long_reaches_the_battery(self):
        got = run(self.design("screw.M3x16_shcs"), self.tmp.name)
        self.assertEqual(got["stack.f/fit.fastener"][0], "refuted", got["stack.f/fit.fastener"])
        self.assertRegex(got["stack.f/fit.fastener"][1], "battery at 0 mm")

    def test_a_screw_too_short_does_not_grip(self):
        got = run(self.design("screw.M3x6_shcs"), self.tmp.name)
        self.assertEqual(got["stack.f/fit.grip"][0], "refuted", "3 mm engaged against 2 diameters")

    def test_a_hole_smaller_than_declared_fails(self):
        got = run(self.design("screw.M3x10_shcs", top_hole="hole h at (10 mm, 10 mm, 3 mm) along bottom diameter 4.2 mm clear"),
                  self.tmp.name)
        self.assertEqual(got["lid.h/fit.hole"][0], "refuted", "the mesh's hole is 3.6 mm at its corners")

    def test_a_countersunk_screw_needs_its_countersink(self):
        got = run(self.design("screw.M3x10_csk"), self.tmp.name)
        self.assertEqual(got["stack.f/fit.seat"][0], "refuted")
        self.assertRegex(got["stack.f/fit.seat"][1], "declares no countersink")

    def test_a_countersunk_seat_is_accepted(self):
        hole = "hole h at (10 mm, 10 mm, 3 mm) along bottom diameter 3.6 mm clear countersink 7.2 mm"
        got = run(self.design("screw.M3x10_csk", top=self.sunk, top_hole=hole), self.tmp.name)
        self.assertEqual(got["stack.f/fit.seat"][0], "certified", got["stack.f/fit.seat"])
        self.assertEqual(got["lid.h/fit.hole"][0], "certified", got["lid.h/fit.hole"])
        self.assertEqual(got["stack.f/fit.fastener"][0], "certified", got["stack.f/fit.fastener"])

    def test_a_countersink_the_mesh_lacks_fails(self):
        hole = "hole h at (10 mm, 10 mm, 3 mm) along bottom diameter 3.6 mm clear countersink 7.2 mm"
        got = run(self.design("screw.M3x10_csk", top_hole=hole), self.tmp.name)
        self.assertEqual(got["lid.h/fit.hole"][0], "refuted", got["lid.h/fit.hole"])


class Inserts(unittest.TestCase):
    """Heat-set inserts in a printed block. FDM holes shrink 0.1 to 0.2 mm (guess); the
    M3 x 5.7 insert asks for 3.9 to 4.1 mm and 1.6 mm of wall (guess)."""

    def run_hole(self, diameter, centre=(10, 10), thick=8):
        with tempfile.TemporaryDirectory() as tmp:
            block = write(tmp, "block", plate((0, 0, 0), (20, 20, thick), centre, f"{diameter / 2}"))
            hole = f"  hole h at ({centre[0]} mm, {centre[1]} mm, {thick} mm) along bottom diameter {diameter} mm insert insert.M3x5_7"
            return run(part("block", block, "polymer.petg", "process.print.fdm_petg_0_4", hole), tmp)

    def test_a_hole_sized_for_shrink_suits_the_insert(self):
        got = self.run_hole(4.2)
        for rule in ("insert.hole_size", "insert.depth", "insert.boss_wall"):
            self.assertEqual(got[f"block.h/{rule}"][0], "certified", (rule, got[f"block.h/{rule}"]))

    def test_the_catalogue_size_uncompensated_fails(self):
        self.assertEqual(self.run_hole(4.0)["block.h/insert.hole_size"][0], "refuted", "4.0 less 0.2 is 3.8 mm")

    def test_a_boss_too_thin_fails(self):
        got = self.run_hole(4.2, centre=(3, 10))
        self.assertEqual(got["block.h/insert.boss_wall"][0], "refuted", "3 - 2.1 = 0.9 mm of wall")

    def test_a_block_too_thin_for_the_insert_fails(self):
        self.assertEqual(self.run_hole(4.2, thick=4)["block.h/insert.depth"][0], "refuted")


class Sheet(unittest.TestCase):
    """Laser-cut 3 mm aluminium. A flat plate is a profile of the stock; a bracket bent
    from the same sheet is not, and v0 reads no bend lines."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, tris):
        mesh = write(self.tmp.name, "sheet", tris)
        return run(part("blank", mesh, "aluminium.6061_T6", "process.sheet.laser_al_3"), self.tmp.name)["blank/sheet.prism"]

    def test_a_flat_plate_is_a_profile(self):
        got = self.check(plate((0, 0, 0), (40, 30, 3), (20, 15), 2))
        self.assertEqual(got[0], "certified", got)

    def test_a_bent_bracket_is_not(self):
        got = self.check(bracket(40, 30, 3, 20))
        self.assertEqual(got[0], "refuted", got)
        self.assertRegex(got[1], "bend lines")

    def test_a_plate_of_other_stock_fails(self):
        self.assertEqual(self.check(box((0, 0, 0), (40, 30, 4)))[0], "refuted")


class Bridges(unittest.TestCase):
    """Printed PLA with +z up. The bridge row is 5 to 10 mm (reported), held at 5 mm."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, tris):
        mesh = write(self.tmp.name, "printed", tris)
        return run(part("p", mesh, "polymer.pla", "process.print.fdm_pla_0_4"), self.tmp.name)["p/print.bridge"]

    def test_a_closed_box_bridges_its_whole_ceiling(self):
        # The void's ceiling is 36 x 26 mm (measured); its centre is 13 mm from every edge.
        got = self.check(box((0, 0, 0), (40, 30, 20)) + flipped(box((2, 2, 2), (38, 28, 18))))
        self.assertEqual(got[0], "refuted", got)
        self.assertRegex(got[1], "z 18 mm spans at least 26 mm")

    def test_a_narrow_channel_bridges(self):
        got = self.check(box((0, 0, 0), (40, 30, 10)) + flipped(box((18, 2, 2), (22, 28, 6))))
        self.assertEqual(got[0], "certified", got)

    def test_a_ledge_with_a_free_edge_is_unknown(self):
        # An arm 37 mm out and 4 mm wide: no span through it reaches 5 mm, but its tip
        # hangs free, so it needs support, which v0 does not model.
        got = self.check(upright([(0, 30), (0, 0), (3, 0), (3, 27), (40, 27), (40, 30)], 4))
        self.assertEqual(got[0], "open", got)

    def test_a_block_has_no_face_over_air(self):
        self.assertEqual(self.check(box((0, 0, 0), (40, 30, 10)))[0], "certified")


class Temperature(unittest.TestCase):
    def test_pla_beside_a_motor_softens(self):
        with tempfile.TemporaryDirectory() as tmp:
            block = write(tmp, "block", box((0, 0, 0), (10, 10, 10)))
            heat = f"  heat in [10 degC, 20 degC] {SIGNED}"
            got = run(part("mount", block, "polymer.pla", "process.print.fdm_pla_0_4", heat), tmp)
            # indoor_dry is 5 to 40 degC (IEC 60364-5-51 AA5); PLA's HDT is 50 to 56 degC (guess).
            self.assertEqual(got["mount/part.temperature"][0], "refuted")
            got = run(part("mount", block, "polymer.petg", "process.print.fdm_petg_0_4", heat), tmp)
            self.assertEqual(got["mount/part.temperature"][0], "certified", "40 + 20 against PETG's 64 degC")


class Press(unittest.TestCase):
    def design(self, tol):
        with tempfile.TemporaryDirectory() as tmp:
            block = write(tmp, "block", plate((0, 0, 0), (20, 20, 8), (10, 10), "1.5"))
            peg = write(tmp, "peg", pin((10, 10), "1.51", 0, 8))
            signed = f"  tolerance in [{tol} mm, {tol} mm] {SIGNED}"
            text = (part("block", block, "aluminium.6061_T6", None,
                         signed + "\n  hole h at (10 mm, 10 mm, 8 mm) along bottom diameter 3 mm press") +
                    part("peg", peg, "aluminium.6061_T6", None, signed) +
                    "assembly fit {\n  place block at (0 mm, 0 mm, 0 mm) facing top front\n"
                    "  place peg at (0 mm, 0 mm, 0 mm) facing top front\n  insert peg along bottom from 10 mm\n"
                    "  press p peg into block.h diameter 3.02 mm interference 0.01 mm to 0.05 mm\n}\n")
            return run(text, tmp)

    def test_an_interference_fit_is_its_range_not_a_clash(self):
        got = self.design("0.0025")
        self.assertEqual(got["fit.p/fit.press"][0], "certified", got["fit.p/fit.press"])
        self.assertEqual(got["fit.peg/fit.insert"][0], "certified", got["fit.peg/fit.insert"])

    def test_a_loose_tolerance_breaks_the_range(self):
        self.assertEqual(self.design("0.01")["fit.p/fit.press"][0], "refuted")


if __name__ == "__main__":
    unittest.main()
