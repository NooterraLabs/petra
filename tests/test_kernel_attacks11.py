"""The eleventh hostile review of petra-verify (kernel/), petra/grid.py and the shipped deck. One test per finding.

  A   Type rule 8 held the floors of `domains.input` and left `domains.size` to deck.json. A size of
      zero in `quantities` is refused by type rule 3, and the same files with the size floor of
      deck.json at -1 were PASS, where a reader is told that nothing in deck.json moves a verdict
      toward PASS. With `--rules` the kernel now holds the size floor of core.json too.
  B   petra/grid.py searched for a partition with no limit on its depth, where the kernel takes one
      at most 64 deep and a file nested at most 128 deep. A rule that fails on every box that holds
      the end of a band and holds on each side of it was PASS in Python at a partition 83 deep and
      UNKNOWN in the kernel, and at 149 deep the kernel refused the proofs. Python's search now
      stops at the kernel's depth, and the cell is open in both.
  C   A text of the card was printed as it stood. A waiver's reason with U+001B sequences moved
      the cursor of a terminal up to the first line of the text report and wrote another status
      there. The kernel escaped the characters under U+0020 and printed U+007F to U+009F, the line
      and paragraph separators and the marks that turn the direction of text raw. Both now print
      each of these as an escape.
  D   The shipped deck asked block shear of the block of all the bolts alone. A lap whose line of
      holes is 1 inch from a side edge, with strong bolts at a long pitch, passed under its waivers
      at 1.29 times what the corner of each plate holds at its end bolt. Nobody writes a rule of a
      deck by hand, so the grid of a lap now asks the blocks of fewer bolts on a line of their own,
      `lap.partial_block_shear`, which has no rule: it is open on every lap until a rule is
      transcribed for it.
  E   petra/grid.py completed a load a case leaves out at the load's `least`, and wrote that value
      into its hint as a fraction in SI. A `least` of 2,100 decimals, which a deck may write, is a
      fraction of 4,201 characters, and the kernel reads no number of more than 4,000: Python said
      PASS_WAIVED and the kernel refused the proofs. Python now writes no completion the kernel
      cannot read, and the cell is open in both.
  F   Two refusals of petra/grid.py stopped with an error of Python's in place of the refusal: a
      `least` past the largest float, which it printed through a float, and a quotient, a root or
      a logarithm with no value over numbers of more than 4,300 digits, which its message wrote
      out whole. `petra check` exited 4 where the kernel refuses the part or leaves the cell open.
  G   The kernel writes every equation of a deck once when it reads its row, and holds the pick it
      writes to 1,024 orders. petra/grid.py counted the orders of the rows a rule applies alone, so
      a deck with an equation of 1,025 orders that no rule applies was PASS in Python and refused
      by the kernel. Python now refuses it. And a row whose `cases` is the empty list, which the
      kernel reads, stopped Python with an IndexError once a rule applied it.
"""
import contextlib
import io
import json
import subprocess
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

import petra.lang
from petra import cli, grid, verify
from petra.registry import build_registry
from tests.test_deck_features import ANCHOR, HEAD, KERNEL, asks, cells, design, given, ill_formed, kind, made_up, no_deck, parsed, part, rule, size
from tests.test_kernel_attacks10 import judged
from tests.test_kernel_grid import ask, findings

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "deck"


# --- A. the size floor of deck.json ---------------------------------------------------------------------------

BARS = made_up([kind("bar", size("x"))], [asks("bar.fits", "bar")], [rule("fits", "bar", "bar.fits", le=["x", ["q", "10", "mm"]])])
BAR_TEXT = design(part("bar", "b", x="given b.x"))
BAR_CARD = HEAD + given("b.x", "5 mm", "6 mm")
STRAY = {"type": "none", "entity": "no part", "line": "none", "field": "none", "role": "size", "dim": "length", "lo": "0", "hi": "0"}
"""A size of zero that no part writes. Type rule 3 holds every quantity of role `size` above the size floor."""


def changed(files: dict[str, str], name: str, change) -> dict[str, str]:
    body = json.loads(files[name])
    change(body)
    return {**files, name: json.dumps(body, indent=1)}


@KERNEL
class TheKernelsOwnSizeFloor(unittest.TestCase):
    def files(self) -> dict[str, str]:
        rules, read = parsed(BARS, BAR_TEXT, BAR_CARD)
        report, files = grid.check(read, rules)
        self.assertEqual((report.verdict, ask(files)["verdict"]), ("PASS", "PASS"))
        return changed(files, "design", lambda d: d["quantities"].append(STRAY))

    def test_a_size_of_zero_is_refused_whatever_size_floor_deck_json_gives(self):
        files = self.files()
        said = ask(files)
        self.assertEqual((said["verdict"], [f["rule"] for f in said["findings"]]), ("ILL-FORMED", ["types.3"]))
        for label, change in (("a floor under zero", lambda s: s.update(min="-1")),
                              ("a floor that a size may sit on", lambda s: s.update(strict=False)),
                              ("both", lambda s: s.update(min="-1", strict=False))):
            with self.subTest(label):
                said = ask(changed(files, "deck", lambda d: change(d["domains"]["size"])))
                self.assertEqual(said["verdict"], "ILL-FORMED", "it was PASS")
                self.assertIn("types.8 deck domains.size: is not the size floor of petra/decks/core.json", findings(said))
                self.assertIn("types.3", findings(said), "the kernel goes on with core.json's size floor")

    def test_a_higher_size_floor_is_a_finding_too_and_another_text_about_it_is_not(self):
        rules, read = parsed(BARS, BAR_TEXT, BAR_CARD)
        files = grid.check(read, rules)[1]
        said = ask(changed(files, "deck", lambda d: d["domains"]["size"].update(min="1")))
        self.assertEqual([f["rule"] for f in said["findings"]], ["types.8"])
        said = ask(changed(files, "deck", lambda d: d["domains"]["size"].update(about="another text")))
        self.assertEqual((said["findings"], said["verdict"]), ([], "PASS"))


# --- B. a partition deeper than the kernel takes --------------------------------------------------------------

def banded(first: str) -> dict:
    """A bar of length x and one rule, x <= T(x), where T is `first` mm on (0, 5 mm] and 10 mm on (5 mm, 10 mm]."""
    table = {"id": "made-up/T", "anchor": ANCHOR, "gives": {"name": "T", "dim": "length"},
             "takes": [{"name": "x", "dim": "length", "range": ["1 mm", "10 mm"]}],
             "table": {"down": {"by": "x", "bands": [["0 mm", "5 mm"], ["5 mm", "10 mm"]], "closed": "upper"}, "unit": "mm", "cells": [first, "10"]}}
    return made_up([kind("bar", size("x"))], [asks("bar.fits", "bar")], [rule("fits", "bar", "bar.fits", le=["x", ["row", "made-up/T", {"x": "x"}]])], [table])


def depth(partition) -> int:
    return 0 if not isinstance(partition, dict) else 1 + max(depth(partition["below"]), depth(partition["above"]))


class APartitionAsDeepAsTheKernelTakes(unittest.TestCase):
    def test_a_rule_that_holds_only_under_a_comb_deeper_than_64_is_open_in_both_readers(self):
        """x in [5 mm, 5.5 mm] starts on the end of the first band. A box that holds 5 mm and more reads both bands and fails
        until it is narrower than the margin of the first band, so the search halves toward 5 mm: 83 times for a margin of
        1e-25 mm and 149 times for 1e-45 mm. The rule holds at every x, and neither reader can show it."""
        for margin in (25, 45):
            with self.subTest(margin=margin):
                rules = banded("5." + "0" * (margin - 1) + "1")
                found, status, said = cells(self, rules, BAR_TEXT, BAR_CARD)
                self.assertEqual((found, status), ({("b", "bar.fits", "fits"): "open"}, "UNKNOWN"), "it was PASS in Python")
                deck, read = parsed(rules, BAR_TEXT, BAR_CARD)
                hints = json.loads(grid.check(read, deck)[1]["proofs"])["cells"]
                self.assertLessEqual(max((depth(h.get("partition")) for h in hints), default=0), 64)

    def test_a_partition_64_deep_is_still_found(self):
        """A margin of 1e-18 mm takes a comb about 60 deep, which the kernel takes."""
        found, status, _ = cells(self, banded("5." + "0" * 17 + "1"), BAR_TEXT, BAR_CARD)
        self.assertEqual((found, status), ({("b", "bar.fits", "fits"): "proved"}, "PASS"))


# --- C. control characters of a card in what is printed -------------------------------------------------------

RAW = ("\x1b", "\x08", "\r", "\x00", "\x7f", "\x85", "\x9b", " ", " ", "‮", "⁦", "‏")
"""Escape, backspace, carriage return, NUL, DEL, two of C1 (NEL and CSI), the line and paragraph separators, and three
marks that turn the direction of text."""


def moves(text: str) -> list[str]:
    """The characters of a text that a terminal may act on and not show: every control character but the line feed, the
    line and paragraph separators, and the marks that turn the direction of text."""
    return sorted({c for c in text if c != "\n" and (unicodedata.category(c) in ("Cc", "Zl", "Zp") or unicodedata.bidirectional(c) in
                                                     ("LRE", "RLE", "LRO", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI") or c in "‎‏؜")})


class NothingPrintedMovesTheCursor(unittest.TestCase):
    def lap(self, reason: str, pull: str = "60 kip") -> tuple[str, str]:
        card = (EXAMPLES / "lap_pass.card").read_text(encoding="utf-8").replace("[0 kip, 45 kip]", f"[0 kip, {pull}]")
        old = next(line for line in card.splitlines() if line.startswith("waive lap.tightening"))
        return card.replace(old, old[: old.index('reason "')] + f'reason "{reason}"'), (EXAMPLES / "lap_pass.petra").read_text(encoding="utf-8")

    def printed(self, card: str, text: str, *flags: str, named: str = "lap") -> tuple[int, str, str]:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, f"{named}.card").write_text(card, encoding="utf-8", newline="")
            Path(tmp, f"{named}.petra").write_text(text, encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["check", *flags, str(Path(tmp, f"{named}.petra"))])
        return code, out.getvalue(), err.getvalue()

    def test_the_text_report_escapes_a_reason_that_would_write_over_the_status_line(self):
        """The lap of examples/deck at 60 kip fails. Its first waiver's reason goes up seven lines, erases the line and
        writes PASS_WAIVED there."""
        reason = "snug-tight\x1b[7A\x1b[2K\x1b[Glap-splice-waived: PASS_WAIVED\x1b[7B\x1b[G"
        code, out, err = self.printed(*self.lap(reason))
        self.assertEqual((code, out.splitlines()[0]), (1, "lap-splice-waived: FAIL"))
        self.assertEqual(moves(out + err), [], "the report holds a character a terminal acts on")
        self.assertIn("snug-tight\\u001b[7A\\u001b[2K\\u001b[Glap-splice-waived: PASS_WAIVED", out)

    def test_the_text_report_escapes_every_character_a_terminal_acts_on(self):
        for raw in RAW:
            if raw in "\r\x00":      # a line end to the language, and a character it refuses
                continue
            with self.subTest(raw=f"U+{ord(raw):04X}"):
                code, out, err = self.printed(*self.lap(f"snug{raw}tight", "45 kip"))
                self.assertEqual(code, 6, err)
                self.assertEqual(moves(out + err), [])
                self.assertIn(f"snug\\u{ord(raw):04x}tight", out)

    def test_the_name_of_a_file_is_escaped_in_a_report_and_in_a_refusal(self):
        """A report and a refusal both print the path of the design, which is whatever its file is named."""
        card, text = self.lap("snug-tight", "45 kip")
        code, out, err = self.printed(card, text, named="la\x1b[2Kp")
        self.assertEqual((code, moves(out + err)), (6, []), err)
        self.assertIn("la\\u001b[2Kp.petra", out)
        code, out, err = self.printed(card, text.replace('"Group 120"', '"Group 121"'), named="la\x1b[2Kp")
        self.assertEqual((code, out, moves(err)), (3, "", []), err)
        self.assertIn("la\\u001b[2Kp.petra", err)

    @KERNEL
    def test_the_kernel_escapes_them_in_its_verdict(self):
        rules, read = parsed(BARS, BAR_TEXT, BAR_CARD.replace('card "made-up"', 'card "m' + "".join(RAW) + '"'))
        files = grid.check(read, rules)[1]
        name = json.loads(files["card"])["name"]
        self.assertEqual(name, "m" + "".join(RAW))
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            command = [verify.binary()]
            for key, body in files.items():
                Path(tmp, f"{key}.json").write_text(body, encoding="utf-8", newline="\n")
                command += [f"--{key}", str(Path(tmp, f"{key}.json"))]
            done = subprocess.run(command, capture_output=True, stdin=subprocess.DEVNULL)
        out = done.stdout.decode("utf-8")
        self.assertEqual(moves(out), [], "the verdict holds a character a terminal acts on")
        said = json.loads(out)
        self.assertEqual(said["verdict"], "PASS", said["findings"])
        self.assertTrue(all(c["entry"] == "fits" for c in said["cells"]))

    def test_both_readers_count_an_escaped_character_as_the_six_bytes_it_prints_in(self):
        """A name of the card prints in at most 200 bytes. Each of these characters prints as an escape of six."""
        for raw in ("\x7f", "\x85", "\x9b", " ", "‮"):
            for room, taken in ((194, True), (195, False)):
                with self.subTest(raw=f"U+{ord(raw):04X}", ascii=room):
                    card = BAR_CARD.replace('card "made-up"', f'card "{"n" * room}{raw}"')
                    if taken:
                        self.assertEqual(cells(self, BARS, BAR_TEXT, card)[1], "PASS")
                    else:
                        mine, kernel = ill_formed(self, BARS, BAR_TEXT, card)
                        self.assertIn("the name of the card", mine)
                        self.assertIn("prints in at most 200 bytes", kernel)


# --- D. block shear of the corner at the end bolt -------------------------------------------------------------

def lap(card_changes: dict[str, str], **fields: str) -> tuple[str, str]:
    """The passing lap of examples/deck with the lines of its lap changed, `count="2"`, and the card's text changed by
    `card_changes`."""
    text = (EXAMPLES / "lap_pass.petra").read_text(encoding="utf-8")
    for field, value in fields.items():
        (line,) = [line for line in text.splitlines() if line.strip().split(" ")[0] == field]
        text = text.replace(line, f"  {field} {value}")
    card = (EXAMPLES / "lap_pass.card").read_text(encoding="utf-8")
    for old, new in card_changes.items():
        assert old in card, old
        card = card.replace(old, new)
    return card, text


PART = "lap.partial_block_shear"
CORNER = dict(fastener='"Group 150"', threads="excluded", count="2", pitch="6 inch", end="2 inch", side="1 inch")
"""Two 3/8 inch A36 plates 6 inch wide, two 3/4 inch Group 150 bolts with threads excluded at 6 inch, end 2 inch, side
1 inch. The block of both bolts holds 57.8 kip and the bolts 55.7. The corner of a plate at its end bolt holds
0.75 (min(0.6 x 58 x 0.586, 0.6 x 36 x 0.750) + 58 x 0.211) = 21.3 kip by Equation J4-5, and each bolt carries half the pull."""


def unwaived(card: str, mechanism: str) -> str:
    return "\n".join(line for line in card.splitlines() if not line.startswith(f"waive {mechanism} ")) + "\n"


class TheCornerAtTheEndBolt(unittest.TestCase):
    def test_a_lap_whose_end_bolts_tear_the_corners_out_does_not_pass_under_the_four_waivers_it_passed_under(self):
        card, text = lap({"[0 kip, 45 kip]": "[0 kip, 55 kip]"}, **CORNER)
        mine, said = judged(unwaived(card, PART), text)
        self.assertEqual(mine, "UNKNOWN", "it was PASS_WAIVED")
        if said:
            self.assertEqual(said["verdict"], "UNKNOWN")
            self.assertEqual({c["entry"]: c["state"] for c in said["cells"] if c["mechanism"] == "lap.block_shear"},
                             {"lap-block-shear-a/gravity": "proved", "lap-block-shear-b/gravity": "proved"}, "the rules of the block of all the bolts hold")
            (cell,) = [c for c in said["cells"] if c["mechanism"] == PART]
            self.assertEqual((cell["subject"], cell["entry"], cell["state"], cell["reason"]), ("splice", "", "open", "the deck has no rule for it"))

    def test_the_line_is_open_on_every_lap_and_the_example_waives_it(self):
        card, text = lap({})
        self.assertIn(f"waive {PART} on splice", card)
        self.assertEqual(judged(card, text)[0], "PASS_WAIVED")
        mine, said = judged(unwaived(card, PART), text)
        self.assertEqual(mine, "UNKNOWN")
        if said:
            self.assertEqual([c["state"] for c in said["cells"] if c["mechanism"] == PART], ["open"])

    def test_the_grid_asks_it_after_block_shear_and_no_rule_answers_it(self):
        deck = json.loads((grid.DECKS / "aisc360.json").read_text(encoding="utf-8"))
        lines = [a["mechanism"] for a in deck["grid"]]
        self.assertEqual(lines[lines.index("lap.block_shear") + 1], PART)
        (line,) = [a for a in deck["grid"] if a["mechanism"] == PART]
        self.assertEqual((line["anchor"], "unless" in line), ({"standard": "AISC 360-22", "clause": "J4.3"}, False))
        self.assertEqual([r["id"] for r in deck["rules"] if r["mechanism"] == PART], [])

    def test_the_examples_keep_their_verdicts(self):
        for name, status in (("lap_pass", "PASS_WAIVED"), ("lap_fail", "FAIL"), ("lap_unknown", "UNKNOWN")):
            with self.subTest(name):
                mine, _ = judged((EXAMPLES / f"{name}.card").read_text(encoding="utf-8"), (EXAMPLES / f"{name}.petra").read_text(encoding="utf-8"))
                self.assertEqual(mine, status)


# --- E. a completion the kernel cannot read -------------------------------------------------------------------

def rods(digits: int) -> dict:
    """A rod whose pull is at least a number of `digits` decimals, about 0.57 N, and at most 1 kN."""
    least = "0.57" + "123456789" * (digits // 9) + "1" * (digits % 9) + " N"
    rod = kind("rod", size("d"), loads=[{"name": "pull", "dim": "force", "what": "the pull", "least": least}])
    return made_up([rod], [asks("rod.pull", "rod"), asks("rod.size", "rod")],
                   [rule("pull", "rod", "rod.pull", le=[["load", "pull"], ["q", "1", "kN"]]), rule("size", "rod", "rod.size", le=[["q", "1", "mm"], "d"])])


ROD_TEXT = design(part("rod", "r", d="10 mm"))
ROD_CARD = HEAD + '\nload service {\n  signed "t@example.org" source "test"\n}\nwaive rod.pull on r by "t@example.org" reason "the pull is at its least"\n'


class ACompletionTheKernelReads(unittest.TestCase):
    def test_a_least_whose_fraction_is_over_4000_characters_rests_no_cell(self):
        found, status, said = cells(self, rods(2100), ROD_TEXT, ROD_CARD)
        self.assertEqual((found[("r", "rod.pull", "pull/service")], status), ("open", "UNKNOWN"), "it was PASS_WAIVED in Python, and the kernel refused the proofs")

    def test_a_least_whose_fraction_the_kernel_reads_still_rests_its_cell(self):
        found, status, said = cells(self, rods(1000), ROD_TEXT, ROD_CARD)
        self.assertEqual((found[("r", "rod.pull", "pull/service")], status), ("waived", "PASS_WAIVED"))
        if verify.binary():
            ((_, _, _, value, unit),) = next(c["completion"]["loads"] for c in said["cells"] if c.get("completion"))
            self.assertEqual((len(value) > 2000, unit), (True, "N"))


# --- F. refusals that stopped with an error of Python's -------------------------------------------------------

BIG = "1" + "0" * 400


def boxes(**least: str) -> dict:
    """A box whose `d`, or whose load `pull`, has a `least` of 10^400."""
    return made_up([kind("box", size("d", **({"least": least["d"]} if "d" in least else {})),
                         loads=[{"name": "pull", "dim": "force", "what": "the pull", **({"least": least["pull"]} if "pull" in least else {})}])],
                   [asks("box.size", "box")], [rule("size", "box", "box.size", le=[["q", "1", "mm"], "d"])])


def train(le: list) -> dict:
    """A gear train of two ratios x and y of 98 decimals, and a rule on the difference of their 64th powers: numbers of some 6,300 digits."""
    return made_up([kind("train", size("x", "dimensionless"), size("y", "dimensionless"), size("d"))], [asks("train.ratio", "train"), asks("train.size", "train")],
                   [rule("ratio", "train", "train.ratio", le=le), rule("size", "train", "train.size", le=[["q", "1", "mm"], "d"])])


RATIO = "1." + "0" * 96
TRAIN_TEXT = design(part("train", "t", x="given t.x", y=f"{RATIO}2", d="10 mm"))
TRAIN_CARD = HEAD + given("t.x", f"{RATIO}1", f"{RATIO}3")
DIFFERENCE = ["sub", ["pow", "x", "64"], ["pow", "y", "64"]]


class RefusalsOverLongNumbers(unittest.TestCase):
    def test_a_number_under_a_least_past_the_largest_float_is_refused_by_both(self):
        mine, kernel = ill_formed(self, boxes(d=f"{BIG} mm"), design(part("box", "b", d="10 mm")))
        self.assertIn("is under 1e397", mine)
        self.assertIn("parts.3", kernel)

    def test_a_load_under_a_least_past_the_largest_float_is_refused_by_both(self):
        card = HEAD + '\nload service {\n  on b pull in [1 kN, 2 kN]\n  signed "t@example.org" source "test"\n}\n'
        mine, kernel = ill_formed(self, boxes(pull=f"{BIG} N"), design(part("box", "b", d="10 mm")), card)
        self.assertIn("is at least 1e400", mine)
        self.assertIn("parts.6", kernel)

    def test_a_node_with_no_value_over_long_numbers_stops_neither_reader(self):
        """Over the whole box the side has no value. The quotient is over 10 at the top of x, and both readers refute it there."""
        for label, side in (("a quotient by a range that holds zero", ["div", "1", DIFFERENCE]), ("a root of a range that reaches under zero", ["sqrt", DIFFERENCE]),
                            ("a logarithm of a range that reaches under zero", ["ln", DIFFERENCE])):
            with self.subTest(label):
                found, status, _ = cells(self, train([side, "10"]), TRAIN_TEXT, TRAIN_CARD)      # the two readers give the same cells
                self.assertIn((found[("t", "train.ratio", "ratio")], status), (("open", "UNKNOWN"), ("refuted", "FAIL")))


# --- G. an equation that no rule applies ----------------------------------------------------------------------

def stepped(orders: int) -> dict:
    return {"id": "made-up/steps", "anchor": ANCHOR, "gives": {"name": "y", "dim": "length"}, "takes": [{"name": "x", "dim": "length", "range": ["1 mm", "2000 mm"]}],
            "cases": [{"when": ["le", "x", ["q", str(n + 1), "mm"]], "is": "x"} for n in range(orders)]}


THIN = [kind("bar", size("t"), size("w"))], [asks("bar.thin", "bar")]
THIN_TEXT = design(part("bar", "b", t="5 mm", w="10 mm"))


class AnEquationNoRuleApplies(unittest.TestCase):
    def test_one_of_1025_orders_is_refused_by_both_readers(self):
        mine, kernel = no_deck(self, made_up(*THIN, [rule("thin", "bar", "bar.thin", le=["t", "w"])], [stepped(1025)]))
        self.assertIn("row made-up/steps: a pick of the rule's tape would compare 1025 orders", mine)
        self.assertIn("would compare 1025 orders", kernel)

    def test_one_of_1024_orders_is_read_by_both(self):
        self.assertEqual(cells(self, made_up(*THIN, [rule("thin", "bar", "bar.thin", le=["t", "w"])], [stepped(1024)]), THIN_TEXT)[1], "PASS")

    def test_a_row_of_no_cases_that_a_rule_applies_is_read_by_both(self):
        none = {**stepped(0), "id": "made-up/none"}
        applied = made_up(*THIN, [rule("thin", "bar", "bar.thin", le=["t", "w"], let={"spare": ["row", "made-up/none", {"x": "t"}]})], [none])
        self.assertEqual(cells(self, applied, THIN_TEXT)[1], "PASS")


if __name__ == "__main__":
    unittest.main()
