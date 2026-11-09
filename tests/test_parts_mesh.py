"""A part's mesh reads exactly, and a surface that is not a solid's boundary is refused
(docs/parts.md, "A mesh is the boundary of a solid"). Owner: parts."""
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from petra.models.parts.mesh import MeshError, Unit, read_mesh
from petra.models.parts.space import Axis, Placement, turn
from tests.parts_meshes import ascii_stl, binary_stl, box, flipped, three_mf


class MeshCase(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.dir = Path(self._dir.name)

    def tearDown(self):
        self._dir.cleanup()

    def read(self, tris, name="part.stl", writer=ascii_stl, unit=Unit.MM):
        path, sha = writer(self.dir / name, tris)
        return read_mesh(path, sha, unit)

    def refused(self, tris, pattern, writer=ascii_stl):
        with self.assertRaisesRegex(MeshError, pattern):
            self.read(tris, writer=writer)


class ReadsExactly(MeshCase):
    def test_a_binary_float_reads_as_the_decimal_the_cad_tool_wrote(self):
        mesh = self.read(box(("0", "0", "0"), ("25.1", "10", "3.3")), writer=binary_stl)
        lo, hi = mesh.bounds()
        self.assertEqual(hi, (Fraction(251, 10), Fraction(10), Fraction(33, 10)))
        self.assertEqual(lo, (0, 0, 0))

    def test_ascii_decimals_read_as_written_and_inches_convert_exactly(self):
        mesh = self.read(box(("0", "0", "0"), ("1", "0.5", "2")), unit=Unit.INCH)
        self.assertEqual(mesh.bounds()[1], (Fraction(254, 10), Fraction(127, 10), Fraction(508, 10)))

    def test_volume_and_centroid_are_exact(self):
        mesh = self.read(box(("1", "2", "3"), ("3.5", "4", "4")))
        self.assertEqual(mesh.volume(), Fraction(5, 2) * 2 * 1)
        self.assertEqual(mesh.centroid(), (Fraction(9, 4), Fraction(3), Fraction(7, 2)))

    def test_a_3mf_reads_one_object_with_its_build_transform(self):
        mesh = self.read(box(("0", "0", "0"), ("1", "1", "1")), name="part.3mf",
                         writer=lambda p, t: three_mf(p, t, transform="1 0 0 0 1 0 0 0 1 10 0 0.5"))
        self.assertEqual(mesh.bounds(), ((10, 0, Fraction(1, 2)), (11, 1, Fraction(3, 2))))

    def test_a_hash_that_differs_from_the_design_is_refused(self):
        path, _ = ascii_stl(self.dir / "p.stl", box(("0", "0", "0"), ("1", "1", "1")))
        with self.assertRaisesRegex(MeshError, "sha256"):
            read_mesh(path, "0" * 64, Unit.MM)


class RefusesWhatIsNotASolid(MeshCase):
    """Each case is a surface the parity reading of the scaffold accepted, or read as less
    material than the file draws."""

    def test_an_edge_shared_by_four_faces_is_refused(self):
        two = box(("0", "0", "0"), ("1", "1", "1")) + box(("1", "1", "0"), ("2", "2", "1"))
        self.refused(two, "more than two faces|same direction")

    def test_a_duplicated_face_is_refused(self):
        cube = box(("0", "0", "0"), ("1", "1", "1"))
        self.refused(cube + cube[:1], "more than two faces|same direction")

    def test_a_doubled_wall_does_not_cancel_it_is_refused(self):
        cube = box(("0", "0", "0"), ("1", "1", "1"))
        wall = [(("3", "0", "0"), ("4", "0", "0"), ("4", "1", "0"))]
        self.refused(cube + wall + flipped(wall), "same three vertices")

    def test_a_closed_piece_with_no_volume_is_refused(self):
        cube = box(("0", "0", "0"), ("1", "1", "1"))
        sheet = [(("3", "0", "0"), ("4", "0", "0"), ("4", "1", "0")), (("3", "0", "0"), ("4", "1", "0"), ("3", "1", "0"))]
        pancake = sheet + [(("3", "0", "0"), ("3", "1", "0"), ("4", "0", "0")), (("4", "0", "0"), ("3", "1", "0"), ("4", "1", "0"))]
        self.refused(cube + pancake, "no volume")

    def test_an_open_surface_is_refused(self):
        self.refused(box(("0", "0", "0"), ("1", "1", "1"))[:-1], "one face")

    def test_an_inside_out_surface_is_refused(self):
        self.refused(flipped(box(("0", "0", "0"), ("1", "1", "1"))), "inside out")

    def test_a_collapsed_triangle_is_refused(self):
        cube = box(("0", "0", "0"), ("1", "1", "1"))
        self.refused(cube + [(("0", "0", "0"), ("1", "0", "0"), ("2", "0", "0"))], "no area|one face")


class Placements(unittest.TestCase):
    def test_a_turn_takes_the_body_top_and_front_where_the_design_says(self):
        t = turn(Axis.FRONT, Axis.BOTTOM)
        self.assertIs(t.axis(Axis.TOP), Axis.FRONT)
        self.assertIs(t.axis(Axis.FRONT), Axis.BOTTOM)
        self.assertEqual(Placement(t, (Fraction(1), 0, 0)).apply((0, 0, Fraction(2))), (1, -2, 0))

    def test_parallel_axes_name_no_turn(self):
        with self.assertRaises(ValueError):
            turn(Axis.TOP, Axis.BOTTOM)

    def test_every_turn_is_a_rotation(self):
        for top in Axis:
            for front in Axis:
                if top.value[0] * front.value[0] + top.value[1] * front.value[1] + top.value[2] * front.value[2]:
                    continue
                r = turn(top, front).rows
                det = (r[0][0] * (r[1][1] * r[2][2] - r[1][2] * r[2][1]) - r[0][1] * (r[1][0] * r[2][2] - r[1][2] * r[2][0])
                       + r[0][2] * (r[1][0] * r[2][1] - r[1][1] * r[2][0]))
                self.assertEqual(det, 1)


if __name__ == "__main__":
    unittest.main()
