"""A row of a deck: reading it, what it gives, and the acceptance check (docs/deck.md)."""
import copy
import unittest
from fractions import Fraction

from petra import deck

HOOP = {
    "id": "example/hoop-stress",
    "anchor": {"standard": "a textbook", "clause": "8.2", "equation": "8-1"},
    "gives": {"name": "sigma_h", "dim": "stress", "what": "hoop stress in the wall"},
    "takes": [
        {"name": "p", "dim": "stress", "what": "internal gauge pressure", "range": ["0.1 MPa", "20 MPa"]},
        {"name": "r", "dim": "length", "what": "inner radius", "range": ["50 mm", "2 m"]},
        {"name": "t", "dim": "length", "what": "wall thickness", "range": ["1 mm", "50 mm"]},
    ],
    "is": ["div", ["mul", "p", "r"], "t"],
}
WORKED = {"anchor": "the textbook, Example 8.1", "given": {"p": "1.5 MPa", "r": "600 mm", "t": "8 mm"}, "gives": "112.5 MPa"}

STRUT = {
    "id": "example/strut",
    "anchor": {"standard": "a textbook", "clause": "9.1"},
    "gives": {"name": "P", "dim": "force", "what": "strut capacity"},
    "takes": [
        {"name": "A", "dim": "area", "what": "area", "range": ["100 mm2", "10000 mm2"]},
        {"name": "sy", "dim": "stress", "what": "yield stress", "range": ["200 MPa", "400 MPa"]},
        {"name": "L", "dim": "length", "what": "length", "range": ["0.5 m", "10 m"]},
        {"name": "r", "dim": "length", "what": "radius of gyration", "range": ["10 mm", "100 mm"]},
    ],
    "cases": [
        {"when": ["le", ["div", "L", "r"], "100"], "is": ["mul", "A", "sy"]},
        {"is": ["div", ["mul", "A", "sy", "10000"], ["pow", ["div", "L", "r"], "2"]]},
    ],
}


GRADES = {
    "id": "example/tolerance",
    "anchor": {"standard": "a textbook", "clause": "3.1", "table": "3"},
    "gives": {"name": "T", "dim": "length", "what": "tolerance on a size"},
    "takes": [
        {"name": "D", "dim": "length", "what": "nominal size", "range": ["1 mm", "30 mm"]},
        {"name": "grade", "one_of": ["fine", "medium", "coarse"], "what": "tolerance grade"},
    ],
    "table": {
        "down": {"by": "D", "bands": [["0 mm", "6 mm"], ["6 mm", "18 mm"], ["18 mm", "30 mm"]], "closed": "upper"},
        "across": {"by": "grade"},
        "unit": "um",
        "cells": [["5", "9", "0.1 mm"], ["7", "14", "0.12 mm"], ["10", "16", None]],
        "rises": ["D", "grade"],
    },
}
DRILL = {
    "id": "example/drill",
    "anchor": {"standard": "a textbook", "clause": "3.2", "table": "4"},
    "gives": {"name": "dh", "dim": "length", "what": "hole diameter"},
    "takes": [{"name": "d", "dim": "length", "what": "screw diameter", "range": ["3 mm", "6 mm"]}],
    "table": {"down": {"by": "d", "at": ["3 mm", "4 mm", "5 mm", "6 mm"]}, "cells": ["3.4 mm", "4.5 mm", "5.5 mm", "6.6 mm"], "rises": ["d"]},
}


def table(body: dict, **parts) -> dict:
    out = copy.deepcopy(body)
    out["table"].update(parts)
    return out


def changed(body: dict, **parts) -> dict:
    out = copy.deepcopy(body)
    out.update(parts)
    return out


def outcome(checks, name: str) -> str:
    return next(c.outcome for c in checks if c.name == name)


class Reading(unittest.TestCase):
    def test_a_row_gives_its_value_exactly_in_si(self):
        row = deck.read(HOOP)
        at = {"p": Fraction(1500000), "r": Fraction(6, 10), "t": Fraction(8, 1000)}
        self.assertEqual(deck.value(row, at), Fraction(112500000))
        self.assertEqual((row.gives, deck.show(row.dim), row.problems), ("sigma_h", "stress", ()))

    def test_data_that_is_not_a_row_is_refused(self):
        for broken, why in ((changed(HOOP, extra=1), "extra"), (changed(HOOP, **{"is": ["mul", "p", "q"]}), "'q'"),
                            (changed(HOOP, **{"is": ["sin", "p"]}), "'sin'"), (changed(HOOP, cases=[{"is": "p"}]), "one of"),
                            (changed(HOOP, anchor={"standard": "x"}), "clause"),
                            (changed(HOOP, gives={"name": "s", "dim": "pressure"}), "'pressure'")):
            with self.subTest(why=why), self.assertRaisesRegex(deck.RowError, why):
                deck.read(broken)
        with self.assertRaisesRegex(deck.RowError, "range of r"):
            deck.read(changed(HOOP, takes=[HOOP["takes"][0], {**HOOP["takes"][1], "range": ["2 m", "50 mm"]}, HOOP["takes"][2]]))

    def test_a_whole_number_and_a_fraction_read_as_printed(self):
        self.assertEqual(deck.quantity("1 1/8 inch", "x")[0], Fraction(9, 8) * Fraction(127, 5000))
        self.assertEqual(deck.quantity("1 1/8", "x"), (Fraction(9, 8), deck.NONE))
        self.assertEqual(deck.quantity("29,000 ksi", "x")[0], deck.quantity("29000 ksi", "x")[0])
        for wrong in ("0,3 mm", "1 1/0 inch", "1 1 inch"):
            with self.subTest(wrong=wrong), self.assertRaises(deck.RowError):
                deck.quantity(wrong, "x")

    def test_powers_roots_and_constants_with_units(self):
        body = changed(HOOP, **{"is": ["mul", ["sqrt", ["mul", "p", ["q", "200", "GPa"]]], ["pow", ["div", "t", "r"], "3/2"]]})
        row = deck.read(body)
        self.assertEqual(row.problems, ())
        got = deck.value(row, {"p": Fraction(2 * 10 ** 6), "r": Fraction(4), "t": Fraction(1)})
        self.assertAlmostEqual(float(got), (2e6 * 200e9) ** 0.5 * 0.25 ** 1.5, delta=1e-3)

    def test_a_whole_or_a_half_power_is_at_most_64_as_in_the_kernel(self):
        for exponent, taken in (("64", True), ("-64", True), ("64/2", True), ("65", False), ("-65", False), ("129/2", False), ("1000000000", False)):
            body = changed(HOOP, **{"is": ["mul", "p", ["pow", ["div", "t", "r"], exponent]]})
            with self.subTest(exponent=exponent):
                if taken:
                    self.assertEqual(deck.read(body).problems, ())
                else:
                    with self.assertRaises(deck.RowError):
                        deck.read(body)

    def test_a_number_is_digits_with_a_decimal_part_or_a_denominator(self):
        for number, taken in (("2.4", True), ("3/4", True), ("-0.5", True), ("+7", True), ("1e3", False), (" 5", False), ("1_000", False), ("5.", False), (".5", False), ("1/0", False)):
            body = changed(HOOP, **{"is": ["mul", "p", ["div", "r", "t"], number]})
            with self.subTest(number=number):
                if taken:
                    self.assertEqual(deck.read(body).problems, ())
                else:
                    with self.assertRaises(deck.RowError):
                        deck.read(body)


class Units(unittest.TestCase):
    def test_each_dimension_error_is_named(self):
        for expr, why in ((["add", "p", "r"], "add of stress and length"), (["mul", "p", "r"], "case 1 gives"),
                          (["mul", "p", ["exp", "r"]], "exp of a length"), (["mul", "p", ["pow", "2", "t"]], "an exponent of a length")):
            with self.subTest(why=why):
                check = deck.units(deck.read(changed(HOOP, **{"is": expr})))
                self.assertEqual(check.outcome, "fail")
                self.assertIn(why, check.detail)
        self.assertEqual(deck.units(deck.read(HOOP)).outcome, "pass")


class Examples(unittest.TestCase):
    def test_a_printed_result_is_reproduced_or_not(self):
        row = deck.read(HOOP)
        self.assertEqual(deck.reproduces(row, [deck.example(WORKED, row)]).outcome, "pass")
        wrong = deck.read(changed(HOOP, **{"is": ["div", ["mul", "p", "r"], ["mul", "2", "t"]]}))
        check = deck.reproduces(wrong, [deck.example(WORKED, wrong)])
        self.assertEqual(check.outcome, "fail")
        self.assertIn("0.5000 of it", check.detail)
        self.assertEqual(deck.reproduces(row, []).outcome, "none")

    def test_the_bound_follows_the_printed_digits(self):
        row = deck.read(HOOP)
        coarse = deck.example({**WORKED, "gives": "110 MPa"}, row)
        self.assertEqual(coarse.within, deck.ROUNDED, "half a unit of 110 is under 0.5%")
        self.assertEqual(deck.reproduces(row, [coarse]).outcome, "fail", "112.5 is 2.3% from 110")
        self.assertEqual(deck.reproduces(row, [deck.example({**WORKED, "gives": "110 MPa", "within": "3 %"}, row)]).outcome, "pass")

    def test_an_example_gives_every_input_in_its_dimension(self):
        row = deck.read(HOOP)
        for broken in ({**WORKED, "given": {"p": "1.5 MPa", "r": "600 mm"}}, {**WORKED, "given": {**WORKED["given"], "t": "8 kN"}},
                       {**WORKED, "gives": "112.5 mm"}):
            with self.assertRaises(deck.RowError):
                deck.example(broken, row)
        more = deck.example({**WORKED, "given": {**WORKED["given"], "E": "200 GPa"}}, row)
        self.assertEqual(set(more.given), {"p", "r", "t"}, "a quantity the row does not read is left out")


class Continuity(unittest.TestCase):
    def test_cases_that_meet_pass_and_cases_that_do_not_fail(self):
        self.assertEqual(deck.continuous(deck.read(STRUT)).outcome, "pass")
        gap = copy.deepcopy(STRUT)
        gap["cases"][1]["is"][1][3] = "9000"
        check = deck.continuous(deck.read(gap))
        self.assertEqual(check.outcome, "fail")
        self.assertIn("10.00%", check.detail)
        said = deck.continuous(deck.read(changed(gap, jumps=[{"cases": [1, 2], "why": "the standard steps down here"}])))
        self.assertEqual(said.outcome, "pass")
        self.assertIn("as the row says", said.detail)

    def test_a_jump_excuses_only_the_two_cases_it_names(self):
        three = copy.deepcopy(STRUT)
        three["cases"] = [{"when": ["le", ["div", "L", "r"], "50"], "is": ["mul", "A", "sy", "2"]}, *STRUT["cases"]]
        self.assertEqual(deck.continuous(deck.read(three)).outcome, "fail", "cases 1 and 2 differ by half where they meet")
        excused = changed(three, jumps=[{"cases": [1, 2], "why": "a step in the standard"}])
        self.assertEqual(deck.continuous(deck.read(excused)).outcome, "pass")
        excused["cases"][2]["is"][1][3] = "9000"
        check = deck.continuous(deck.read(excused))
        self.assertEqual(check.outcome, "fail", "cases 2 and 3 no longer meet, and no jump names them")
        self.assertIn("cases 2 and 3 differ by 10.00%", check.detail)
        with self.assertRaisesRegex(deck.RowError, "two of the row's cases"):
            deck.read(changed(three, jumps=[{"cases": [1, 4], "why": "x"}]))

    def test_ranges_that_reach_one_case_only_are_none(self):
        narrow = copy.deepcopy(STRUT)
        narrow["takes"][2]["range"] = ["0.5 m", "0.6 m"]
        self.assertEqual(deck.continuous(deck.read(narrow)).outcome, "none")
        self.assertEqual(deck.continuous(deck.read(HOOP)).outcome, "pass")


class Second(unittest.TestCase):
    def test_the_same_equation_written_another_way_agrees(self):
        other = changed(HOOP, **{"is": ["mul", "r", ["div", "p", "t"]]})
        self.assertEqual(deck.second(deck.read(HOOP), deck.read(other)).outcome, "pass")

    def test_other_names_for_the_inputs_are_matched_by_dimension(self):
        other = changed(HOOP, takes=[{**HOOP["takes"][0], "name": "pressure"}, {**HOOP["takes"][2], "name": "wall"},
                                     {**HOOP["takes"][1], "name": "radius"}], **{"is": ["div", ["mul", "pressure", "radius"], "wall"]})
        check = deck.second(deck.read(HOOP), deck.read(other))
        self.assertEqual(check.outcome, "pass")
        self.assertIn("r as radius", check.detail)

    def test_a_constant_ten_percent_off_disagrees(self):
        for expr in (["div", ["mul", "1.1", "p", "r"], "t"], ["div", ["mul", "p", "r"], ["mul", "t", "t"]], ["div", ["mul", "p", "t"], "r"]):
            with self.subTest(expr=expr):
                self.assertEqual(deck.second(deck.read(HOOP), deck.read(changed(HOOP, **{"is": expr}))).outcome, "fail")

    def test_a_case_boundary_that_moved_disagrees(self):
        moved = copy.deepcopy(STRUT)
        moved["cases"][0]["when"][2] = "101"
        self.assertEqual(deck.second(deck.read(STRUT), deck.read(moved)).outcome, "fail", "the meeting points fall between 100 and 101")


class Tables(unittest.TestCase):
    MM = Fraction(1, 1000)

    def test_a_cell_is_read_by_band_and_key_with_its_own_unit_or_the_tables(self):
        row = deck.read(GRADES)
        at = lambda size, grade: deck.value(row, {"D": size * self.MM, "grade": grade})  # noqa: E731
        self.assertEqual(at(10, "medium"), Fraction(14, 10 ** 6))
        self.assertEqual(at(10, "coarse"), Fraction(12, 10 ** 5), "a cell with its own unit keeps it")
        self.assertEqual((at(6, "fine"), at(Fraction(601, 100), "fine")), (Fraction(5, 10 ** 6), Fraction(7, 10 ** 6)), "a band holds its upper end")
        self.assertEqual((at(0, "fine"), at(31, "fine"), at(20, "coarse")), (None, None, None), "outside the bands, and an empty cell")
        lower = deck.read(table(GRADES, down={**GRADES["table"]["down"], "closed": "lower"}))
        self.assertEqual(deck.value(lower, {"D": 6 * self.MM, "grade": "fine"}), Fraction(7, 10 ** 6))

    def test_the_last_band_may_have_no_upper_end(self):
        open_top = deck.read(table(GRADES, down={"by": "D", "bands": [["0 mm", "6 mm"], ["6 mm", "18 mm"], ["18 mm", None]]}))
        self.assertEqual(deck.value(open_top, {"D": 5000 * self.MM, "grade": "fine"}), Fraction(10, 10 ** 6))
        self.assertEqual(deck.second(open_top, deck.read(GRADES)).outcome, "fail", "one stops at 30 mm and the other does not")
        with self.assertRaisesRegex(deck.RowError, "only the last"):
            deck.read(table(GRADES, down={"by": "D", "bands": [["0 mm", None], ["6 mm", "18 mm"], ["18 mm", "30 mm"]]}))

    def test_a_table_read_at_listed_values_gives_nothing_between_them(self):
        row = deck.read(DRILL)
        self.assertEqual(deck.value(row, {"d": 4 * self.MM}), Fraction(45, 10 ** 4))
        self.assertIsNone(deck.value(row, {"d": Fraction(9, 2) * self.MM}))

    def test_data_that_is_not_a_table_is_refused(self):
        for broken, why in ((table(GRADES, cells=GRADES["table"]["cells"][:2]), "3 lines of 3"),
                            (table(GRADES, down={"by": "D", "bands": [["0 mm", "6 mm"], ["5 mm", "18 mm"], ["18 mm", "30 mm"]]}), "none over another"),
                            (table(GRADES, across={"by": "grade", "at": ["1 mm"]}), "`by` alone"), (table(GRADES, rises=["D"], falls=["D"]), "no side is in both"),
                            (table(DRILL, down={"by": "d", "at": ["4 mm", "3 mm", "5 mm", "6 mm"]}), "in order"),
                            (changed(GRADES, jumps=[]), "no jumps"), (table(GRADES, cells=[["5", "9", "0,1 mm"], ["7", "14", "1"], ["10", "16", None]]), "comma"),
                            (changed(HOOP, takes=[*HOOP["takes"], {"name": "k", "one_of": ["a", "b"]}]), "takes no key")):
            with self.subTest(why=why), self.assertRaisesRegex(deck.RowError, why):
                deck.read(broken)

    def test_units_reads_every_cell_and_every_band(self):
        self.assertEqual(deck.units(deck.read(GRADES)).outcome, "pass")
        force = deck.units(deck.read(table(GRADES, cells=[["5", "9", "0.1 kN"], ["7", "14", "0.12 mm"], ["10", "16", None]])))
        self.assertEqual(force.outcome, "fail")
        self.assertIn("a cell is a force", force.detail)
        bands = deck.units(deck.read(table(GRADES, down={"by": "D", "bands": [["0 kN", "6 kN"], ["6 kN", "18 kN"], ["18 kN", "30 kN"]]})))
        self.assertIn("the side that reads D is not all length", bands.detail)

    def test_shape_catches_a_cell_that_breaks_the_run(self):
        self.assertEqual(deck.shape(deck.read(GRADES)).outcome, "pass")
        slipped = deck.shape(deck.read(table(GRADES, cells=[["5", "9", "0.1 mm"], ["7", "41", "0.12 mm"], ["10", "16", None]])))
        self.assertEqual(slipped.outcome, "fail")
        self.assertIn("along D the table rises, and in line 2 place 3 is under place 2", slipped.detail)
        self.assertEqual(deck.shape(deck.read(table(GRADES, rises=[]))).outcome, "none")

    def test_a_second_transcription_is_compared_cell_by_cell_and_at_every_band_end(self):
        row = deck.read(GRADES)
        self.assertEqual(deck.second(row, deck.read(GRADES)).outcome, "pass")
        one_cell = deck.second(row, deck.read(table(GRADES, cells=[["5", "9", "0.1 mm"], ["7", "15", "0.12 mm"], ["10", "16", None]])))
        self.assertEqual(one_cell.outcome, "fail")
        self.assertIn("grade=medium", one_cell.detail)
        for other in (table(GRADES, down={**GRADES["table"]["down"], "closed": "lower"}),
                      table(GRADES, down={"by": "D", "bands": [["0 mm", "6 mm"], ["6 mm", "20 mm"], ["20 mm", "30 mm"]]}),
                      table(GRADES, cells=[["5", "9", "0.1 mm"], ["7", "14", "0.12 mm"], ["10", "16", "0.2 mm"]])):
            self.assertEqual(deck.second(row, deck.read(other)).outcome, "fail")
        self.assertEqual(deck.second(row, deck.read(DRILL)).outcome, "fail", "another table altogether")

    def test_a_keys_names_are_matched_by_their_order(self):
        row = deck.read(GRADES)
        takes = [GRADES["takes"][0], {"name": "class", "one_of": ["f", "m", "c"], "what": "tolerance class"}]
        renamed = changed(table(GRADES, rises=["D", "class"], across={"by": "class"}), takes=takes)
        self.assertEqual(deck.second(row, deck.read(renamed)).outcome, "pass")
        reordered = changed(table(GRADES, rises=["D", "class"], across={"by": "class"}), takes=[takes[0], {**takes[1], "one_of": ["m", "f", "c"]}])
        self.assertEqual(deck.second(row, deck.read(reordered)).outcome, "pass", "the cells are in the printed order whatever a column is called")
        fewer = changed(table(GRADES, rises=["D", "class"], across={"by": "class"}, cells=[["5", "9"], ["7", "14"], ["10", "16"]]), takes=[takes[0], {**takes[1], "one_of": ["f", "m"]}])
        self.assertEqual(deck.second(row, deck.read(fewer)).outcome, "fail")

    def test_an_example_names_its_key(self):
        row = deck.read(GRADES)
        worked = {"anchor": "the textbook, Example 3.2", "given": {"D": "10 mm", "grade": "medium"}, "gives": "14 um"}
        self.assertEqual([c.outcome for c in deck.accept(row, [deck.example(worked, row)], row)], ["pass"] * 4)
        with self.assertRaisesRegex(deck.RowError, "not one of"):
            deck.example({**worked, "given": {"D": "10 mm", "grade": "rough"}}, row)


class Accepting(unittest.TestCase):
    def test_a_row_is_admitted_when_no_part_fails(self):
        row = deck.read(HOOP)
        checks = deck.accept(row, [deck.example(WORKED, row)], row)
        self.assertEqual([c.outcome for c in checks], ["pass"] * 4)
        alone = deck.accept(row, [])
        self.assertEqual((outcome(alone, "examples"), outcome(alone, "second")), ("none", "none"))


if __name__ == "__main__":
    unittest.main()
