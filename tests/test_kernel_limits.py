"""The limits on what petra-verify prints and holds (docs/format.md, "Limits").

A file under 1 MB must not make the kernel print many megabytes, hold a gigabyte, or stop
with no verdict. Each test builds files that would do one of those without a limit, and
reads the bounded answer. Most start from STRIPS, the deck made up for tests/test_grid.py.
The tests are skipped when no kernel is built.
"""
import copy
import hashlib
import json
import time
import unittest
from unittest import mock

import petra
from petra import export, grid, verify
from petra.models.base import ComponentError
from petra.registry import build_registry
from tests.test_grid import CARD, DESIGN, STRIPS, TEST
from tests.test_kernel_attacks import run_raw
from tests.test_kernel_grid import Kernel, ask, changed, findings, part, states, strips

MAX_FINDINGS, MAX_TEXT, MAX_NAME, MAX_CELLS = 100, 200, 64, 10_000
"""The limits as kernel/Petra/Files.lean sets them."""


def with_rules(files: dict[str, str], change) -> dict[str, str]:
    """The files with the deck of rules changed by `change`, which takes its JSON."""
    rules = json.loads(files["rules"])
    change(rules)
    return {**files, "rules": json.dumps(rules)}


def printed(files: dict[str, str]) -> tuple[dict, int]:
    """What the kernel says of the files, and how many bytes it printed."""
    _, out = run_raw(files)
    return json.loads(out), len(out)


def renamed(files: dict[str, str], old: str, new: str) -> dict[str, str]:
    """The design with the pad `old` named `new`, in its own block and where a strip lands on it."""
    def change(body: dict) -> None:
        for p in body["parts"]:
            p["name"] = new if p["name"] == old else p["name"]
            for ln in p["lines"]:
                ln["args"] = [{"word": new} if a == {"word": old} else a for a in ln["args"]]
    return changed(files, "design", change)


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Findings(Kernel):
    def test_the_kernel_keeps_the_first_hundred_findings_and_counts_the_rest(self):
        files = changed(strips(), "design", lambda b: part(b, "s")["lines"].extend({"field": f"x{i}", "args": []} for i in range(250)))
        said = ask(files)
        self.assertEqual((said["verdict"], len(said["findings"]), said["more_findings"], said["cells"]), ("ILL-FORMED", MAX_FINDINGS, 150, []))
        self.assertEqual(said["findings"][0], {"rule": "parts.2", "file": "design", "item": "s.x0", "why": "is not a field of a strip"})
        self.assertEqual(said["findings"][-1]["item"], "s.x99", "the first hundred, in the order of the file")

    def test_a_design_with_no_finding_says_there_were_no_more(self):
        self.assertEqual((ask(strips())["findings"], ask(strips())["more_findings"]), ([], 0))

    def test_a_long_text_in_a_finding_is_cut_and_says_how_much_was_left_out(self):
        files = changed(strips(), "design", lambda b: part(b, "s")["lines"].append({"field": "x" * 5000, "args": []}))
        said, size = printed(files)
        (found,) = said["findings"]
        self.assertEqual(found["item"], "s." + "x" * (MAX_TEXT - 2) + "... (4802 more characters)")
        self.assertLess(size, 2000, "the verdict does not hold the long text")

    def test_a_text_is_cut_by_the_bytes_it_prints_in(self):
        """A control character prints in six bytes, so a text of them is cut after 33."""
        files = changed(strips(), "design", lambda b: part(b, "s")["lines"].append({"field": "\u0001" * 500, "args": []}))
        (found,) = ask(files)["findings"]
        self.assertEqual(found["item"], "s." + "\u0001" * 33 + "... (467 more characters)")

    def test_the_reviewers_shape_prints_a_few_kilobytes(self):
        """One part with a name of 45,000 characters and 4,500 lines of a field its type lacks
        made the kernel hold over 1 GB and stop with no verdict."""
        def change(body: dict) -> None:
            body["parts"] = [{"name": "N" * 45000, "type": "pad", "lines": [{"field": "x", "args": []}] * 4500}]
            body["quantities"] = []
        said, size = printed(changed(strips(), "design", change))
        self.assertEqual(said["verdict"], "ILL-FORMED")
        self.assertIn("the name of a part prints in at most 64 bytes, and this one in 45000", said["findings"][0]["why"])
        self.assertLess(size, 20_000)

    def test_a_long_name_of_a_field_on_many_lines_prints_a_few_kilobytes(self):
        """The same shape with the long text in a place the kernel cuts and does not refuse."""
        def change(body: dict) -> None:
            part(body, "p1")["lines"] = [{"field": "y" * 20000, "args": []}] + [{"field": "x", "args": []}] * 20000
        said, size = printed(changed(strips(), "design", change))
        self.assertEqual((said["verdict"], len(said["findings"]), said["more_findings"]), ("ILL-FORMED", MAX_FINDINGS, 19902))
        self.assertLess(size, 40_000)


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Names(Kernel):
    def test_a_part_may_have_a_name_of_64_characters_and_no_more(self):
        honest = ask(strips())
        at = ask(renamed(strips(), "p1", "p" * MAX_NAME))
        self.assertEqual((at["verdict"], at["counts"]), (honest["verdict"], honest["counts"]))
        over = renamed(strips(), "p1", "p" * (MAX_NAME + 1))
        self.assertIllFormed(over, "shape design parts[0]: the name of a part prints in at most 64 bytes, and this one in 65: " + "p" * 65)

    def test_a_name_is_measured_as_it_prints(self):
        """Eleven control characters print in 66 bytes."""
        self.assertIllFormed(renamed(strips(), "p1", "\u0001" * 11), "the name of a part prints in at most 64 bytes, and this one in 66")
        self.assertEqual(ask(renamed(strips(), "p1", "\u0001" * 10))["verdict"], ask(strips())["verdict"])

    def test_a_deck_with_a_name_over_the_limit_does_not_hold_together(self):
        long = "m" * (MAX_NAME + 1)
        line = {"type": "pad", "mechanism": long, "what": "made up", "anchor": TEST}
        self.assertIllFormed(with_rules(strips(), lambda r: r["grid"].append(line)), "the name of a mechanism prints in at most 64 bytes")
        self.assertIllFormed(with_rules(strips(), lambda r: r["rules"][0].update(id="test/" + long)), "the id of a rule prints in at most 64 bytes")
        field = {"name": long, "dim": "length", "what": "made up"}
        self.assertIllFormed(with_rules(strips(), lambda r: r["types"][0]["fields"].append(field)), "a name prints in at most 64 bytes")
        self.assertIllFormed(with_rules(strips(), lambda r: r["rules"][0].update({"let": {long: "1"}})), "a name prints in at most 64 bytes")
        at = with_rules(strips(), lambda r: r["grid"].append({**line, "mechanism": "m" * MAX_NAME}))
        self.assertIn(("p1", "m" * MAX_NAME, "", "open"), states(ask(at)))

    def test_a_load_case_with_a_name_over_the_limit_is_a_shape_finding(self):
        def under(name: str):
            def change(body: dict) -> None:
                for i in body["inputs"]:
                    if "case" in i:
                        i["case"] = name
            return change
        self.assertIllFormed(changed(strips(), "card", under("c" * (MAX_NAME + 1))), "shape card run.s.current: the name of a load case prints in at most 64 bytes")
        self.assertIn(("s", "strip.heat", "heat/" + "c" * MAX_NAME, "open"), states(ask(changed(strips(), "card", under("c" * MAX_NAME)))),
                      "a case of 64 characters is read, and no hint is for its cell")


class TheGridsNames(unittest.TestCase):
    """petra/grid.py holds a name to the same 64 bytes, counted the same way, so the grid and
    the kernel refuse the same decks and the same designs (bench/kernel_grid.py)."""

    def test_the_grid_refuses_a_deck_with_a_name_over_the_limit(self):
        long = "m" * (MAX_NAME + 1)
        line = {"type": "pad", "mechanism": long, "what": "made up", "anchor": TEST}
        cases = {
            "a mechanism": lambda r: r["grid"].append(line),
            "a mechanism of eleven control characters, which print in 66 bytes": lambda r: r["grid"].append({**line, "mechanism": "\u0001" * 11}),
            "a mechanism of 22 letters of two bytes and 21 of one": lambda r: r["grid"].append({**line, "mechanism": "\u00e9" * 22 + "a" * 21}),
            "the id of a rule": lambda r: r["rules"][0].update(id="test/" + "m" * 60),
            "a field": lambda r: r["types"][0]["fields"].append({"name": long, "dim": "length", "what": "made up"}),
            "a name of let": lambda r: r["rules"][0].update({"let": {long: "1"}}),
        }
        for what, change in cases.items():
            with self.subTest(what=what):
                body = copy.deepcopy(STRIPS)
                change(body)
                with self.assertRaises(grid.DeckError):
                    grid.read_deck(json.dumps(body))
        at = copy.deepcopy(STRIPS)
        at["grid"].append({**line, "mechanism": "\u00e9" * 22 + "a" * 20})
        at["rules"][0]["id"] = "test/" + "m" * 59
        self.assertEqual(grid.read_deck(json.dumps(at)).rules[0].id, "test/" + "m" * 59, "64 bytes are within the limit")

    def test_the_grid_refuses_a_part_and_a_load_case_with_a_name_over_the_limit(self):
        deck = grid.read_deck(json.dumps(STRIPS))

        def check(card: str, design: str):
            with mock.patch.object(grid, "decks", lambda: (deck,)):
                return grid.check(petra.lang.parse_design(card, design, "strips.petra", build_registry()), deck)

        self.assertEqual(check(CARD, DESIGN.replace("p1", "p" * MAX_NAME))[0].status, check(CARD, DESIGN)[0].status)
        says = "the name of a part and of a load case is at most 64 characters"
        with self.assertRaisesRegex(ComponentError, says):
            check(CARD, DESIGN.replace("p1", "p" * (MAX_NAME + 1)))
        with self.assertRaisesRegex(ComponentError, says):
            check(CARD.replace("load run", "load " + "r" * (MAX_NAME + 1)), DESIGN)

    @unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
    def test_the_kernel_refuses_the_same_two_designs(self):
        said = ask(strips(design=DESIGN.replace("p1", "p" * (MAX_NAME + 1))))
        self.assertIn("the name of a part prints in at most 64 bytes", findings(said))
        said = ask(strips(card=CARD.replace("load run", "load " + "r" * (MAX_NAME + 1))))
        self.assertIn("the name of a load case prints in at most 64 bytes", findings(said))


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Cells(Kernel):
    @staticmethod
    def lines(count: int):
        """A deck with `count` more lines of the grid for a pad, which the design has two of."""
        return lambda r: r["grid"].extend({"type": "pad", "mechanism": f"pad.m{i}", "what": "made up", "anchor": TEST} for i in range(count))

    def test_the_kernel_makes_ten_thousand_cells_and_no_more(self):
        strip = len(ask(strips())["cells"])
        most = (MAX_CELLS - strip) // 2
        said, size = printed(with_rules(strips(), self.lines(most)))
        self.assertEqual((said["verdict"], len(said["cells"])), ("UNKNOWN", strip + 2 * most))
        self.assertLess(size, 2_000_000)
        over, size = printed(with_rules(strips(), self.lines(most + 1)))
        self.assertEqual((over["verdict"], over["cells"]), ("ILL-FORMED", []))
        self.assertEqual(over["findings"], [{"rule": "limits", "file": "design", "item": "parts",
                                             "why": "the deck of rules asks more than 10000 cells of this design, and the kernel makes no more"}])
        self.assertLess(size, 2000)

    def test_many_parts_and_many_lines_of_the_grid_are_refused_before_their_cells_are_made(self):
        """3,000 parts and 5,000 lines would be 15 million cells from about 1 MB."""
        def many(body: dict) -> None:
            body["parts"] += [{"name": f"q{i}", "type": "pad", "lines": [{"field": "area", "args": [{"number": {"dim": "area", "lo": "1", "hi": "1"}}]}]} for i in range(3000)]
        files = with_rules(changed(strips(), "design", many), self.lines(5000))
        self.assertLess(sum(len(text.encode()) for text in files.values()), 1_500_000)
        start = time.perf_counter()
        said, size = printed(files)
        self.assertEqual((said["verdict"], said["findings"][0]["rule"], said["cells"]), ("ILL-FORMED", "limits", []))
        self.assertLess(size, 2000)
        self.assertLess(time.perf_counter() - start, 30)

    def test_writing_the_tapes_takes_ten_million_steps_and_no_more(self):
        """A rule with a sum of 60,000 terms, written for 200 pads, is 12 million steps."""
        def long_rule(r: dict) -> None:
            r["grid"].append({"type": "pad", "mechanism": "pad.sum", "what": "made up", "anchor": TEST})
            r["rules"].append({"id": "test/sum", "type": "pad", "mechanism": "pad.sum", "anchor": TEST, "says": "made up",
                               "le": [["add"] + ["area"] * 60000, ["q", "1", "m2"]]})

        def pads(count: int):
            def change(body: dict) -> None:
                body["parts"] += [{"name": f"q{i}", "type": "pad", "lines": [{"field": "area", "args": [{"number": {"dim": "area", "lo": "1", "hi": "1"}}]}]} for i in range(count)]
            return change
        files = with_rules(strips(), long_rule)
        few = ask(changed(files, "design", pads(20)))
        self.assertEqual((few["verdict"], few["counts"]["open"] >= 22), ("UNKNOWN", True), "22 pads are within the budget, and their cells are open")
        over = ask(changed(files, "design", pads(200)))
        self.assertEqual((over["verdict"], over["cells"]), ("ILL-FORMED", []))
        self.assertEqual(over["findings"], [{"rule": "limits", "file": "design", "item": "parts",
                                             "why": "writing the tapes of this design from the deck of rules takes more than 10000000 steps, and the kernel takes no more"}])

    def test_sixty_thousand_parts_are_read_in_seconds(self):
        """The duplicate-name check, the count of joins and the duplicate-input check each
        compared every pair: 45,000 empty parts ran past 30 seconds."""
        def many(body: dict) -> None:
            body["parts"] = [{"name": f"q{i}", "type": "pad", "lines": []} for i in range(60000)]
            body["quantities"] = []
        start = time.perf_counter()
        said, size = printed(changed(strips(), "design", many))
        took = time.perf_counter() - start
        self.assertEqual((said["verdict"], len(said["findings"])), ("ILL-FORMED", MAX_FINDINGS))
        self.assertLess(took, 20, f"reading 60,000 parts took {took:.0f} s")
        self.assertLess(size, 20_000)


def old_path(cells: list[dict], waivers: list[dict]) -> dict[str, str]:
    """Files of a design with no parts: a card with the waivers and nothing else, and the cells."""
    card = export.text({"format": "petra-card/0", "name": "c", "environment": None, "cases": [], "inputs": [], "claims": [], "waivers": waivers})
    design = {"format": "petra-design/0", "name": "d", "card": "sha256:" + hashlib.sha256(card.encode()).hexdigest(), "quantities": [], "params": []}
    domains = json.loads(export.CORE.read_text(encoding="utf-8"))["domains"]
    return {"card": card, "design": export.text(design), "deck": export.text({"format": "petra-deck/0", "domains": domains, "constants": []}),
            "proofs": json.dumps({"format": "petra-proofs/0", "cells": cells}, separators=(",", ":"))}


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Waivers(Kernel):
    def test_a_waiver_that_many_cells_rest_on_is_printed_once(self):
        """9,000 waived cells under one waiver with a reason of 400,000 characters made the
        kernel hold over 3 GB: it wrote the waiver out for each cell."""
        waiver = {"subject": "a", "mechanism": "m", "by": "b" * 1000, "reason": "r" * 400_000}
        other = {"subject": "a", "mechanism": "n", "by": "c", "reason": "another"}
        cells = [{"subject": "a", "mechanism": "m", "entry": str(i), "state": "waived"} for i in range(9000)]
        cells.insert(5, {"subject": "a", "mechanism": "n", "entry": "", "state": "waived"})
        files = old_path(cells, [waiver, other])
        self.assertLess(sum(len(text.encode()) for text in files.values()), 1_000_000)
        said, size = printed(files)
        self.assertEqual((said["verdict"], said["counts"]["waived"]), ("UNKNOWN", 9001))
        self.assertEqual(said["waived"], [waiver, other], "each waiver once and whole, in the order the cells first rest on it")
        self.assertLess(size, 1_500_000)

    def test_the_cells_of_proofs_json_print_in_under_three_times_their_bytes(self):
        cells = [{"subject": "", "mechanism": "", "entry": "", "state": "proved"}] * 17000
        files = old_path(cells, [])
        said, size = printed(files)
        self.assertEqual((said["verdict"], len(said["cells"])), ("UNKNOWN", 17000))
        self.assertLess(size, 3 * len(json.dumps(cells, separators=(",", ":"))))


SPENT = "this proof would take the kernel past the 20000000 evaluations it spends on one verdict, so it is not tried"


def halves(label, lo: int, hi: int):
    """A partition that splits the range of the input into ranges of length 1."""
    if hi - lo == 1:
        return "leaf"
    mid = (lo + hi) // 2
    return {"input": label, "at": str(mid), "below": halves(label, lo, mid), "above": halves(label, mid, hi)}


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Evaluations(Kernel):
    """The proofs of one verdict get 20,000,000 evaluations: the length of each tape times the
    leaves of its partition, added up in the order of the cells. A long tape with many hints,
    or with a partition of many leaves, ran for over ten minutes from under 1 MB."""

    def test_a_proof_past_the_budget_is_not_tried_and_its_cell_is_open(self):
        """Each cell costs 30,003 evaluations a leaf and has 256 leaves: 7.7 million. Two fit."""
        tape = {"inputs": [{"label": "dsg:x", "lo": "0", "hi": "256"}], "nodes": [["c", "-1"]] + [["neg", 0]] * 10000, "roots": [0]}
        cells = [{"subject": "a", "mechanism": "m", "entry": str(i), "state": "proved", "tape": tape, "partition": halves(0, 0, 256)} for i in range(3)]
        start = time.perf_counter()
        said = ask(old_path(cells, []))
        self.assertEqual([(c["state"], c.get("reason")) for c in said["cells"]], [("proved", None), ("proved", None), ("open", SPENT)])
        self.assertEqual(said["verdict"], "UNKNOWN")
        self.assertLess(time.perf_counter() - start, 30)

    def test_a_small_proof_after_a_proof_that_was_not_tried_is_tried(self):
        long = {"inputs": [{"label": "dsg:x", "lo": "0", "hi": "1024"}], "nodes": [["c", "-1"]] + [["neg", 0]] * 10000, "roots": [0]}
        short = {"inputs": [{"label": "dsg:x", "lo": "0", "hi": "1"}], "nodes": [["c", "-1"]], "roots": [0]}
        cells = [{"subject": "a", "mechanism": "m", "entry": "long", "state": "proved", "tape": long, "partition": halves(0, 0, 1024)},
                 {"subject": "a", "mechanism": "m", "entry": "short", "state": "proved", "tape": short, "partition": "leaf"}]
        said = ask(old_path(cells, []))
        self.assertEqual([(c["state"], c.get("reason")) for c in said["cells"]], [("open", SPENT), ("proved", None)])

    def test_a_hint_past_the_budget_is_not_tried_and_the_other_cells_are_settled(self):
        """A rule with a sum of 9,000 terms and a hint with 512 leaves for its cell."""
        def long_rule(r: dict) -> None:
            r["grid"].append({"type": "pad", "mechanism": "pad.sum", "what": "made up", "anchor": TEST})
            r["rules"].append({"id": "test/sum", "type": "pad", "mechanism": "pad.sum", "anchor": TEST, "says": "made up",
                               "le": [["add"] + [["mul", "area", f"{i}.5"] for i in range(9000)], ["q", "1", "m2"]]})
        files = with_rules(strips(), long_rule)
        honest = ask(strips())
        hint = {"subject": "p1", "mechanism": "pad.sum", "entry": "sum", "state": "proved", "partition": halves("dsg:strips.p1.area", 0, 512)}
        start = time.perf_counter()
        said = ask(changed(files, "proofs", lambda b: b["cells"].insert(0, hint)))
        self.assertLess(time.perf_counter() - start, 30)
        cells = {(c["subject"], c["mechanism"], c["entry"]): c for c in said["cells"]}
        self.assertEqual((cells["p1", "pad.sum", "sum"]["state"], cells["p1", "pad.sum", "sum"]["reason"]), ("open", SPENT))
        self.assertEqual(cells["p2", "pad.sum", "sum"]["reason"], "proofs.json has no partition and no point for it")
        self.assertEqual([c for c in states(said) if c[0] == "s"], states(honest), "the cells of the strip are settled as before")


if __name__ == "__main__":
    unittest.main()
