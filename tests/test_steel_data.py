"""Steel deck data layer (M1): every row cites its clause, the published tables are
transcribed exactly, the consistency relations catch corrupted rows, and the Shapes
Database importer reads the workbook and records its hash."""
import json
import os
import re
import tempfile
import unittest
import zipfile
from fractions import Fraction
from pathlib import Path
from unittest import mock

from petra.premises import Tag
from petra.registry import build_deck, build_registry, check_deck
from petra.registry.consistency import corrupt
from petra.registry.steel import BOLT_SIZES, holes_for, size_id, steel_constants, steel_materials
from petra.registry.steel_shapes import (TABLE, ShapeTable, angle_legs, constants as shape_constants, import_workbook,
                                        key, load)
from petra.units import CUSTOMARY, parse_quantity

INCH = CUSTOMARY["inch"][0]
KSI = CUSTOMARY["ksi"][0]
KIP = CUSTOMARY["kip"][0]
PUBLISHED_SHA256 = "e08bea15bbe475e78251292e5f543ff5a11d16b59c9d6af47aec700f8f57f050"
"""SHAPE160.xlsx, the AISC Shapes Database v16.0 workbook the shipped rows were copied from."""
_SOURCES = Path(__file__).resolve().parents[1] / "docs" / "research" / "sources" / "SHAPE160.xlsx"
WORKBOOK = os.environ.get("PETRA_SHAPES_XLSX") or (str(_SOURCES) if _SOURCES.exists() else None)
REGISTRY = build_registry()
DECK = build_deck(REGISTRY)

CITATION = re.compile(r"(AISC 360-22|RCSC 2025|ASTM [A-Z]?\d|AWS A5|ASME B\d|AISC Shapes Database|AISC Steel Construction Manual)")
CLAUSE = re.compile(r"(Section [A-Z]?\d|Part \d|Table [A-Z]?\d|designation|row [WL]\d|thread series \(UNC\)|dimensions of heavy hex nuts|Symbols list)")


def steel_rows():
    """(name, tag, owner, source) of every steel constant and stated material property."""
    for c in steel_constants().values():
        yield c.name, c.tag, c.owner, c.source
    for m in steel_materials().values():
        for prop, value in m.props.items():
            if hasattr(value, "standard"):
                yield f"{m.id}.{prop}", value.tag, value.owner, value.standard


class Provenance(unittest.TestCase):
    def test_every_steel_row_cites_a_document_and_its_clause(self):
        rows = list(steel_rows())
        self.assertGreater(len(rows), 300)
        for name, tag, owner, source in rows:
            self.assertRegex(source, CITATION, name)
            self.assertRegex(source, CLAUSE, name)

    def test_a_judged_row_says_it_was_not_checked_and_a_sanctioned_row_names_its_issuer(self):
        for name, tag, owner, source in steel_rows():
            if tag is Tag.JUDGED:
                self.assertEqual(owner, "petra-maintainers", name)
                self.assertRegex(source, "not checked", name)
            else:
                self.assertIs(tag, Tag.SANCTIONED, name)
                self.assertIn(owner, {"RCSC", "AISC", "ASTM", "AWS"}, name)

    def test_the_rows_checked_against_rcsc_2025_are_sanctioned(self):
        constants = steel_constants()
        for name in ("bolt_us.3_4.std", "bolt_us.3_4.Tm_g120", "rcsc2025.s5_4.mu_a", "rcsc2025.s5_1.phi"):
            self.assertIs(constants[name].tag, Tag.SANCTIONED, name)
            self.assertEqual(constants[name].owner, "RCSC", name)
        self.assertIs(REGISTRY.fact("bolt_group.120.Fnv_N").tag, Tag.SANCTIONED)
        self.assertIs(REGISTRY.fact("bolt_group.A307.fu").tag, Tag.JUDGED, "A307's tensile strength is recalled")

    def test_the_rows_checked_against_aisc_360_22_are_sanctioned(self):
        # Each of these was found in the published text of AISC 360-22; A36's Fy and Fu, the
        # Manual-only clearances and the ASME thread and nut rows are not printed there.
        constants = steel_constants()
        for name in ("aisc360.j4_3.phi", "aisc360.j10_4.cr_below_my", "aisc360.j2_2b.w4", "bolt_us.7_8.edge_min"):
            self.assertIs(constants[name].tag, Tag.SANCTIONED, name)
            self.assertEqual(constants[name].owner, "AISC", name)
            self.assertIn("A360-22W-ewr.pdf", constants[name].source, name)
        for name in ("bolt_group.200.Fnv_N", "steel.A992.fy", "steel.A572_50.fu"):
            self.assertIs(REGISTRY.fact(name).tag, Tag.SANCTIONED, name)
        for name in ("steel.A36.fy", "steel.A36.fu"):
            self.assertIs(REGISTRY.fact(name).tag, Tag.JUDGED, name)
        for name in ("aisc_manual.clearance.socket", "aisc_manual.seat.critical_offset", "bolt_us.3_4.tpi"):
            self.assertIs(constants[name].tag, Tag.JUDGED, name)

    def test_steel_constants_and_the_v0_constants_do_not_collide(self):
        from petra.registry.constants import CONSTANTS
        from petra.registry.electronics import electronics_constants
        self.assertFalse(set(CONSTANTS) & set(steel_constants()))
        self.assertFalse((set(CONSTANTS) | set(steel_constants())) & set(electronics_constants()))
        self.assertEqual(len(REGISTRY.constants), len(CONSTANTS) + len(steel_constants()) + len(electronics_constants()))


class Tables(unittest.TestCase):
    def inches(self, name):
        return REGISTRY.constants[name].value.lo / INCH

    def test_rcsc_table_3_1_holes(self):
        self.assertEqual(self.inches("bolt_us.3_4.std"), Fraction(13, 16))
        self.assertEqual(self.inches("bolt_us.3_4.ovs"), Fraction(15, 16))
        self.assertEqual(self.inches("bolt_us.3_4.ssl_l"), Fraction(1))
        self.assertEqual(self.inches("bolt_us.7_8.lsl_l"), Fraction(35, 16))
        self.assertEqual(self.inches("bolt_us.1.std"), Fraction(9, 8))

    def test_holes_above_one_inch_follow_the_table_formula(self):
        d = Fraction(5, 4)
        self.assertEqual(holes_for("1-1/4"), (d + Fraction(1, 8), d + Fraction(5, 16), d + Fraction(1, 8),
                                              d + Fraction(3, 8), d + Fraction(1, 8), Fraction(5, 2) * d))

    def test_every_size_has_every_row(self):
        for size in BOLT_SIZES:
            for prop in ("d", "std", "ovs", "ssl_w", "ssl_l", "lsl_w", "lsl_l", "edge_min", "Tm_g120", "Tm_g150",
                         "tpi", "nut_F"):
                self.assertIn(f"bolt_us.{size_id(size)}.{prop}", REGISTRY.constants, f"{size} {prop}")

    def test_rcsc_table_5_2_pretension(self):
        self.assertEqual(REGISTRY.constants["bolt_us.3_4.Tm_g120"].value.lo, 28 * KIP)
        self.assertEqual(REGISTRY.constants["bolt_us.1_1_8.Tm_g150"].value.lo, 80 * KIP)

    def test_table_j3_2_nominal_stresses(self):
        expected = {("120", "Fnt"): 90, ("120", "Fnv_N"): 54, ("120", "Fnv_X"): 68, ("150", "Fnt"): 113,
                    ("150", "Fnv_X"): 84, ("200", "Fnt"): 150, ("A307", "Fnv_N"): 27}
        for (group, prop), ksi in expected.items():
            self.assertEqual(REGISTRY.fact(f"bolt_group.{group}.{prop}").value.lo, ksi * KSI, f"{group} {prop}")
        self.assertNotIn("Fnv_X", REGISTRY.materials["bolt_group.A307"].props, "A307 has one Fnv")

    def test_astm_minimums(self):
        self.assertEqual(REGISTRY.fact("steel.A992.fy").value.lo, 50 * KSI)
        self.assertEqual(REGISTRY.fact("steel.A36.fu").value.lo, 58 * KSI)
        self.assertEqual(REGISTRY.expand("steel.A992", "E").name, "const.aisc360.E")


class Consistency(unittest.TestCase):
    def broken(self, deck):
        return {(f.entry, f.relation) for f in check_deck(deck)}

    def test_the_steel_records_break_no_relation(self):
        self.assertEqual([f for f in check_deck(DECK) if "bolt" in f.entry or "aisc" in f.entry or "steel" in f.entry], [])

    def test_a_wrong_hole_is_caught(self):
        self.assertIn(("const.bolt_us.3_4", "bolt.oversize_order"), self.broken(corrupt(DECK, "const.bolt_us.3_4", "std", Fraction(5, 4))))

    def test_a_pretension_off_by_a_row_is_caught(self):
        self.assertEqual(self.broken(corrupt(DECK, "const.bolt_us.7_8", "Tm_g120", Fraction(51, 39))),
                         {("const.bolt_us.7_8", "bolt.pretension_g120")})

    def test_a_shape_area_slip_is_caught_by_the_plates_and_the_weight(self):
        found = self.broken(corrupt(DECK, "const.aisc_shapes_v16.W18x50", "A", Fraction(11, 10)))
        self.assertEqual(found, {("const.aisc_shapes_v16.W18x50", "shape.plate_area"),
                                 ("const.aisc_shapes_v16.W18x50", "shape.weight")})

    def test_a_web_thickness_slip_is_caught(self):
        self.assertIn(("const.aisc_shapes_v16.W14x90", "shape.plate_area"),
                      self.broken(corrupt(DECK, "const.aisc_shapes_v16.W14x90", "tw", Fraction(2))))

    def test_a_bolt_stress_slip_is_caught(self):
        self.assertEqual(self.broken(corrupt(DECK, "bolt_group.150", "Fnv_X", Fraction(68, 84))),
                         {("bolt_group.150", "bolt_group.shear_ratio_x")})


def _workbook(path, rows):
    strings = sorted({cell for row in rows for cell in row if not _numeric(cell)})
    index = {s: i for i, s in enumerate(strings)}
    shared = "".join(f"<si><t>{s}</t></si>" for s in strings)
    body = []
    for r, row in enumerate(rows, start=1):
        cells = []
        for c, cell in enumerate(row):
            ref = f"{chr(65 + c)}{r}"
            if _numeric(cell):
                cells.append(f'<c r="{ref}"><v>{cell}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="s"><v>{index[cell]}</v></c>')
        body.append(f'<row r="{r}">{"".join(cells)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/sharedStrings.xml", f"<sst {ns}>{shared}</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData>{''.join(body)}</sheetData></worksheet>")


def _numeric(cell):
    try:
        float(cell)
        return True
    except ValueError:
        return False


class ShapesDatabase(unittest.TestCase):
    def test_the_importer_reads_w_and_l_rows_and_records_the_hash(self):
        rows = [
            # The published sheet repeats each header for its SI columns after the US ones.
            ["Type", "EDI_Std_Nomenclature", "AISC_Manual_Label", "W", "A", "d", "bf", "tw", "tf", "kdes", "k1", "T",
             "AISC_Manual_Label", "A", "d", "bf", "tw", "tf", "kdes", "k1", "T"],
            ["W", "W18X50", "W18X50", "50", "14.7", "18", "7.5", "0.35499999999999998", "0.57", "0.972", "0.8125", "15.5",
             "W460X74", "9480", "457", "191", "9.02", "14.5", "24.7", "21", "394"],
            ["W", "W99X1", "W99X1", "1", "–", "1", "1", "1", "1", "1", "1", "1"],
            ["L", "L4X3-1/2X3/8", "L4X3-1/2X3/8", "9.1", "2.67", "4", "–", "–", "–", "0.75", "–", "–", "L102X89X9.5"],
            ["C", "C15X50", "C15X50", "50", "14.7", "15", "3.72", "0.716", "0.65", "1.44", "–", "12.125"],
        ]
        with tempfile.TemporaryDirectory() as tmp:
            book = os.path.join(tmp, "aisc-shapes-database-v16.0.xlsx")
            _workbook(book, rows)
            body = import_workbook(book)
            kept = import_workbook(book, keep={"L4X3-1/2X3/8"})
            out = os.path.join(tmp, "shapes.json")
            with open(out, "w", encoding="utf-8") as f:
                json.dump(body, f)
            table = load(out)
        self.assertEqual(len(body["sha256"]), 64)
        self.assertEqual([r["label"] for r in body["W"]], ["W18X50"], "a row with a dash is skipped")
        self.assertEqual(body["W"][0]["tw"], "0.355", "a float cell is read as its shortest decimal; the US column, not the SI one")
        self.assertEqual(body["W"][0]["T"], "15.5", "T, the flat web the fit checks read, in inches")
        self.assertEqual((kept["W"], kept["L"]), ([], ["L4X3-1/2X3/8"]), "keep holds only the labels named")
        self.assertIn("PETRA_SHAPES_XLSX", kept["scope"], "and a kept table says how to load every row")
        self.assertEqual(body["L"], ["L4X3-1/2X3/8"])
        self.assertIs(table.tag, Tag.SANCTIONED)
        found = shape_constants(table)
        tw = found["aisc_shapes_v16.W18x50.tw"]
        self.assertEqual(tw.value.lo, Fraction(355, 1000) * INCH)
        self.assertIn(body["sha256"], tw.source)
        self.assertEqual(tw.owner, "AISC")

    def test_the_shipped_rows_cite_the_published_database(self):
        # Copied from SHAPE160.xlsx, the AISC Shapes Database v16.0 workbook. The earlier
        # transcription from memory had 5 of its 168 values wrong, among them W30X90 kdes.
        table = load(TABLE)
        self.assertIsInstance(table, ShapeTable)
        self.assertIs(table.tag, Tag.SANCTIONED)
        self.assertEqual((table.file, table.sha256), ("SHAPE160.xlsx", PUBLISHED_SHA256))
        rows = {r["label"]: r for r in table.w}
        self.assertEqual((rows["W18X50"]["tw"], rows["W30X90"]["kdes"], rows["W14X90"]["d"]), ("0.355", "1.26", "14.0"))

    def test_the_repository_ships_only_the_rows_it_uses(self):
        # docs/principles.md P9: the database is AISC's compilation; the full table loads at
        # run time from the user's own copy (PETRA_SHAPES_XLSX), never from the repository.
        with open(TABLE, encoding="utf-8") as f:
            body = json.load(f)
        self.assertLessEqual(len(body["W"]), 40)
        self.assertLessEqual(len(body["L"]), 20)

    @unittest.skipUnless(WORKBOOK, "the published workbook is not at hand (set PETRA_SHAPES_XLSX, or keep it in "
                                   "docs/research/sources/)")
    def test_every_shipped_row_is_the_workbooks(self):
        published = import_workbook(WORKBOOK)
        self.assertEqual(published["sha256"], PUBLISHED_SHA256)
        rows = {r["label"]: r for r in published["W"]}
        shipped = load(TABLE)
        for row in shipped.w:
            self.assertEqual(row, rows[row["label"]])
        self.assertLessEqual(set(shipped.angles), set(published["L"]))

    def test_a_workbook_that_is_not_the_cited_one_is_refused(self):
        rows = [["Type", "EDI_Std_Nomenclature", "AISC_Manual_Label", "W", "A", "d", "bf", "tw", "tf", "kdes"],
                ["W", "W18X50", "W18X50", "50", "14.7", "18", "7.5", "0.355", "0.57", "0.972"]]
        with tempfile.TemporaryDirectory() as tmp:
            book = os.path.join(tmp, "SHAPE160.xlsx")
            _workbook(book, rows)
            with mock.patch.dict(os.environ, {"PETRA_SHAPES_XLSX": book}):
                with self.assertRaisesRegex(ValueError, "is not the workbook the shipped rows cite"):
                    load(TABLE)

    def test_designations(self):
        self.assertEqual(key("L4X3-1/2X3/8"), "L4x3_1_2x3_8")
        self.assertEqual(angle_legs("L4X3-1/2X3/8"), (Fraction(4), Fraction(7, 2), Fraction(3, 8)))
        weight = REGISTRY.constants["aisc_shapes_v16.W18x50.w"]
        self.assertIs(weight.tag, Tag.SANCTIONED)
        self.assertEqual(REGISTRY.constants["aisc_shapes_v16.L4x3_1_2x3_8.t"].value.lo, Fraction(3, 8) * INCH)


class Units(unittest.TestCase):
    def test_customary_units_are_exact(self):
        self.assertEqual(parse_quantity("1", "inch").value.lo, Fraction(254, 10000))
        self.assertEqual(parse_quantity("1", "kip").value.lo, Fraction("4448.2216152605"))
        self.assertEqual(parse_quantity("50", "ksi").value.lo, 50 * Fraction("4448.2216152605") / Fraction(254, 10000) ** 2)
        self.assertEqual(parse_quantity("1", "kip_ft").value.lo, 12 * parse_quantity("1", "kip_in").value.lo)


if __name__ == "__main__":
    unittest.main()
