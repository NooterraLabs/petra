"""petra.check(text) returns plain data, and a FAIL names the input that lowers its governing
check the most and the way to move it (petra/repair.py).

The 60 kip shear tab of tests/fixtures/readout/job5_fail_60k.petra fails on its bolts:
three 3/4 in bolts in one column carry 60 kip at the elastic method's eccentricity, at
about twice their strength. Bolt shear sets every bolt's strength, so the plate's thickness
does not move that check, and a fourth bolt row moves it the most.
"""
import contextlib
import io
import json
import re
import unittest
from pathlib import Path

import petra
from petra.cli import EXIT_CODES, main
from petra.repair import sites, written

ROOT = Path(__file__).resolve().parents[1]
FAILING = ROOT / "tests" / "fixtures" / "readout" / "job5_fail_60k.petra"
PASSING = ROOT / "examples" / "steel" / "shear_tab.petra"


def set_number(text: str, line: int, old: str, new: str) -> str:
    """The design with the number `old` on 1-based `line` written as `new`."""
    lines = text.split("\n")
    lines[line - 1] = re.sub(rf"(?<![\w.]){re.escape(old)}(?![\w.])", new, lines[line - 1], count=1)
    return "\n".join(lines)


def obligation(result: dict, requirement: str) -> dict:
    (found,) = [o for v in result["verdicts"] for o in v["obligations"] if o["requirement"] == requirement]
    return found


class Failing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = FAILING.read_text(encoding="utf-8")
        cls.result = petra.check(cls.text)

    def test_the_result_is_plain_json(self):
        self.assertEqual(json.loads(json.dumps(self.result)), self.result, "json round-trips the result unchanged")
        self.assertEqual(self.result["status"], "FAIL")

    def test_the_repair_targets_the_refuted_check_with_the_highest_utilisation(self):
        refuted = [o for v in self.result["verdicts"] for o in v["obligations"] if o["outcome"] == "refuted"]
        worst = max(refuted, key=lambda o: o["utilisation"])
        self.assertEqual(self.result["repair"]["check"], worst["requirement"])
        self.assertEqual(self.result["repair"]["check"], "tab/steel.bolts/coverage.steel.bolts")
        self.assertAlmostEqual(self.result["repair"]["utilisation"], worst["utilisation"])

    def test_a_fourth_row_lowers_the_bolts_most(self):
        first = self.result["repair"]["moves"][0]
        self.assertEqual((first["input"], first["direction"], first["from"], first["to"]), ("tab.rows", "increase", "3", "4"))

    def test_every_move_lowers_the_check_and_the_first_lowers_it_most(self):
        moves = self.result["repair"]["moves"]
        self.assertGreater(len(moves), 1, "more than one input moves the bolts")
        for m in moves:
            self.assertLess(m["utilisation"], self.result["repair"]["utilisation"], m["input"])
        self.assertEqual([m["utilisation"] for m in moves], sorted(m["utilisation"] for m in moves))
        self.assertNotIn("tab.plate thickness", {m["input"] for m in moves}, "bolt shear does not read the plate")

    def test_a_move_reads_what_checking_the_edited_design_reads(self):
        for m in self.result["repair"]["moves"][:2]:
            after = petra.check(set_number(self.text, m["line"], m["from"], m["to"]), repair=False)
            self.assertAlmostEqual(obligation(after, self.result["repair"]["check"])["utilisation"], m["utilisation"], msg=m["input"])
            self.assertEqual(after["status"], m["status"], m["input"])

    def test_clears_names_a_value_at_which_the_check_holds(self):
        cleared = [m for m in self.result["repair"]["moves"] if m["clears"] is not None]
        self.assertTrue(cleared, "some move clears the bolts")
        m = cleared[0]
        after = petra.check(set_number(self.text, m["line"], m["from"], m["clears"]["to"]), repair=False)
        self.assertEqual(obligation(after, self.result["repair"]["check"])["outcome"], "certified")
        self.assertEqual(after["status"], m["clears"]["status"])


class Others(unittest.TestCase):
    def test_a_pass_has_no_repair(self):
        result = petra.check(PASSING.read_text(encoding="utf-8"))
        self.assertEqual((result["status"], result["repair"]), ("PASS", None))

    def test_an_input_error_is_data_not_an_exception(self):
        result = petra.check("petra 0\ndesign {\n")
        self.assertEqual(result["status"], "INPUT_ERROR")
        self.assertIn("<text>:2", result["error"], "the error names the line")

    def test_a_step_is_the_next_value_the_design_accepts(self):
        """A 1/4 in plate bears on 3/4 in bolts at 40 kip: the plate's next stocked thickness
        is 5/16 in, and the next RCSC Table 5.2 bolt below 3/4 in is 5/8 in."""
        text = FAILING.read_text(encoding="utf-8").replace("thickness 0.375 inch", "thickness 0.25 inch") \
            .replace("60 kip]", "40 kip]").replace("threads included", "threads excluded")
        moves = {(m["input"], m["direction"]): m for m in petra.check(text)["repair"]["moves"]}
        self.assertEqual(moves[("tab.plate thickness", "increase")]["to"], "0.3125")
        self.assertEqual(moves[("tab.bolts diameter", "decrease")]["to"], "0.625")
        for m in moves.values():
            self.assertNotEqual(petra.check(set_number(text, m["line"], m["from"], m["to"]), repair=False)["status"], "INPUT_ERROR", m["input"])


class Sites(unittest.TestCase):
    def test_numbers_in_a_bound_or_outside_a_component_are_not_sites(self):
        text = FAILING.read_text(encoding="utf-8").replace("  rows 3\n", "  rows 3\n  top in [3 inch, 3.125 inch] signed \"x\" source \"y\"\n")
        names = [s.input for s in sites(text)]
        self.assertIn("tab.rows", names)
        self.assertEqual(len(names), len(set(names)), "each site once")
        self.assertFalse(any("reaction" in n for n in names), "the load is signed by its owner, not an input to move")
        self.assertEqual(names.count("tab.top"), 1, "the toleranced top is a bound, not a site")

    def test_a_number_is_written_as_the_design_wrote_its_neighbour(self):
        from fractions import Fraction
        self.assertEqual(written(Fraction(7, 16), "0.375"), "0.4375")
        self.assertEqual(written(Fraction(4), "3"), "4")
        self.assertEqual(written(Fraction(7, 16), "3/8"), "7/16")
        self.assertEqual(written(Fraction(49, 16), "3"), "3.0625")


class Cli(unittest.TestCase):
    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(list(argv))
        return code, out.getvalue()

    def test_the_text_names_the_move_after_the_governing_lines(self):
        code, out = self.run_cli("check", str(FAILING))
        self.assertEqual(code, EXIT_CODES["FAIL"])
        lines = out.splitlines()
        at = next(i for i, line in enumerate(lines) if line.startswith("repair "))
        self.assertTrue(lines[at - 1].startswith("governing  "), "the repair follows the governing lines")
        self.assertIn("increase  tab.rows (line 19) from 3 to 4", lines[at + 1])

    def test_the_json_carries_the_repair(self):
        code, out = self.run_cli("check", str(FAILING), "--json")
        self.assertEqual(json.loads(out)["repair"]["moves"][0]["input"], "tab.rows")
        code, out = self.run_cli("check", str(PASSING), "--json")
        self.assertIsNone(json.loads(out)["repair"])


if __name__ == "__main__":
    unittest.main()
