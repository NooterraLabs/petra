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
from fractions import Fraction
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


SPENT = "this proof would take the kernel past the 20000000000 units of work it spends on one verdict, so it is not tried"
COSTLY = "this step would take the kernel past the 20000000000 units of work it spends on one verdict, so it is not taken"
UNSAID = "past what the verdict prints of reasons"
MAX_WORK, MAX_ORDERS, MAX_REASONS = 20_000_000_000, 1024, 500_000
"""The limits as kernel/Petra/Tape.lean and Files.lean set them."""


def halves(label, lo: int, hi: int):
    """A partition that splits the range of the input into ranges of length 1."""
    if hi - lo == 1:
        return "leaf"
    mid = (lo + hi) // 2
    return {"input": label, "at": str(mid), "below": halves(label, lo, mid), "above": halves(label, mid, hi)}


def proved(tape: dict, entry: str, partition="leaf") -> dict:
    return {"subject": "a", "mechanism": "m", "entry": entry, "state": "proved", "tape": tape, "partition": partition}


SHORT = {"inputs": [{"label": "dsg:x", "lo": "0", "hi": "1"}], "nodes": [["c", "-1"]], "roots": [0]}


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Work(Kernel):
    """The proofs of one verdict get 20,000,000,000 units of work (docs/format.md, "Work"). A
    proof pays for its tape on its leaves before it starts, and each step then pays for the
    numbers it handles. So a tape of long numbers, of many `exp`, of wide picks or of many
    leaves stops when the work is spent, and its cell is open."""

    def test_a_proof_that_cannot_pay_for_its_tape_on_its_leaves_is_not_tried_and_a_small_one_after_it_is(self):
        """A tape of 60,000 nodes is 14 million units a leaf, and 8,192 leaves are 118 billion."""
        long = {"inputs": [{"label": "dsg:x", "lo": "0", "hi": "8192"}], "nodes": [["c", "-1"]] + [["neg", 0]] * 60000, "roots": [0]}
        start = time.perf_counter()
        said = ask(old_path([proved(long, "long", halves(0, 0, 8192)), proved(SHORT, "short")], []))
        self.assertEqual([(c["state"], c.get("reason")) for c in said["cells"]], [("open", SPENT), ("proved", None)])
        self.assertEqual(said["verdict"], "UNKNOWN")
        self.assertLess(said["work"], 100_000, "a proof that is not tried costs nothing")
        self.assertLess(time.perf_counter() - start, 30)

    def test_the_same_tape_on_fewer_leaves_is_tried(self):
        long = {"inputs": [{"label": "dsg:x", "lo": "0", "hi": "64"}], "nodes": [["c", "-1"]] + [["neg", 0]] * 60000, "roots": [0]}
        said = ask(old_path([proved(long, "long", halves(0, 0, 64))], []))
        self.assertEqual((said["verdict"], said["cells"][0]["state"]), ("PASS", "proved"))
        self.assertGreater(said["work"], 60000 * 240 * 64, "it paid for every node on every leaf")

    def test_a_step_that_costs_more_than_the_work_left_is_not_taken_and_a_small_proof_after_it_is_tried(self):
        """One `exp` of a number near 65,000 with 65,000 bits a side would sum 15,000 terms of
        130,000 bits, each times that number: more than a verdict has. The steps before it are
        paid for, and it is not."""
        x = Fraction((1 << 6550) - 1, (1 << 6549) + 1)
        nodes = [["c", export.number(x)], ["mul", [0] * 10], ["c", "64000"], ["add", [1, 2]], ["exp", 3], ["neg", 4]]
        start = time.perf_counter()
        said = ask(old_path([proved({"inputs": [], "nodes": nodes, "roots": [5]}, "costly"), proved(SHORT, "short")], []))
        self.assertEqual([(c["state"], c.get("reason")) for c in said["cells"]], [("open", f"leaf 0: node 4: {COSTLY}"), ("proved", None)])
        self.assertLess(said["work"], MAX_WORK // 100, "the step that was not taken was not paid for")
        self.assertLess(time.perf_counter() - start, 30)

    def test_work_that_runs_out_leaves_the_cell_open_and_the_verdict_says_what_was_spent(self):
        """A chain of 4,000 small products costs about 97 million units a leaf, so the work
        runs out near leaf 205 of 256. This is the yardstick of bench/work_sweep.py: its
        numbers fit a machine word, and a unit of every other step is held to three times
        the time a unit of this one takes."""
        nodes = [["c", "3/8"], ["c", "8/3"], ["s", 0]]
        for k in range(4000):
            nodes.append(["mul", [len(nodes) - 1, k % 2]])
        nodes += [["c", "-1000"], ["add", [len(nodes) - 1, len(nodes)]]]
        tape = {"inputs": [{"label": "dsg:x", "lo": "0", "hi": "256"}], "nodes": nodes, "roots": [len(nodes) - 1]}
        start = time.perf_counter()
        said = ask(old_path([proved(tape, "costly", halves(0, 0, 256))], []))
        (cell,) = said["cells"]
        self.assertEqual(cell["state"], "open")
        self.assertRegex(cell["reason"], r"^leaf \d+: node \d+: " + COSTLY + "$")
        self.assertLessEqual(said["work"], MAX_WORK)
        self.assertGreater(said["work"], MAX_WORK * 9 // 10)
        self.assertLess(time.perf_counter() - start, 60)

    def test_a_hint_past_the_budget_is_not_tried_and_the_other_cells_are_settled(self):
        """A rule with a sum of 20,000 terms and a hint with 8,192 leaves for its cell."""
        def long_rule(r: dict) -> None:
            r["grid"].append({"type": "pad", "mechanism": "pad.sum", "what": "made up", "anchor": TEST})
            r["rules"].append({"id": "test/sum", "type": "pad", "mechanism": "pad.sum", "anchor": TEST, "says": "made up",
                               "le": [["add"] + [["mul", "area", f"{i}.5"] for i in range(20000)], ["q", "1", "m2"]]})
        files = with_rules(strips(), long_rule)
        honest = ask(strips())
        hint = {"subject": "p1", "mechanism": "pad.sum", "entry": "sum", "state": "proved", "partition": halves("dsg:strips.p1.area", 0, 8192)}
        start = time.perf_counter()
        said = ask(changed(files, "proofs", lambda b: b["cells"].insert(0, hint)))
        self.assertLess(time.perf_counter() - start, 30)
        cells = {(c["subject"], c["mechanism"], c["entry"]): c for c in said["cells"]}
        self.assertEqual((cells["p1", "pad.sum", "sum"]["state"], cells["p1", "pad.sum", "sum"]["reason"]), ("open", SPENT))
        self.assertEqual(cells["p2", "pad.sum", "sum"]["reason"], "proofs.json has no partition and no point for it")
        self.assertEqual([c for c in states(said) if c[0] == "s"], states(honest), "the cells of the strip are settled as before")

    def test_the_verdict_says_how_much_work_its_proofs_took(self):
        self.assertGreater(ask(strips())["work"], 0)
        self.assertEqual(ask(strips(), without=("proofs",))["work"], 0, "with no hint there is no proof to pay for")
        self.assertEqual(ask(old_path([], []))["work"], 0)

    def test_a_long_sum_of_short_numbers_costs_what_its_numbers_come_to(self):
        """Nine thousand terms with one denominator: the sum stays short, and each term pays for a short sum."""
        nodes = [["c", f"{2 * i + 1}/2"] for i in range(9000)] + [["add", list(range(9000))], ["neg", 9000]]
        said = ask(old_path([proved({"inputs": [], "nodes": nodes, "roots": [9001]}, "sum")], []))
        self.assertEqual(said["cells"][0]["state"], "proved")
        self.assertLess(said["work"], 9000 * 20_000)


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Orders(Kernel):
    """The conditions of one pick hold at most 1,024 orders between them. The kernel tests
    every order in each way it tries, so a wide condition is work that the count of cases
    does not show."""

    @staticmethod
    def wide(orders: int) -> dict:
        nodes = [["s", 0], ["c", "1"], ["c", "-1"], ["pick", [[["and", [["le", 0, 1]] * orders], 2], [None, 2]]]]
        return {"inputs": [{"label": "dsg:x", "lo": "0", "hi": "1"}], "nodes": nodes, "roots": [3]}

    def test_a_pick_that_a_file_carries_holds_1024_orders_and_no_more(self):
        at = ask(old_path([proved(self.wide(MAX_ORDERS), "at")], []))
        self.assertEqual((at["verdict"], at["cells"][0]["state"]), ("PASS", "proved"))
        over = ask(old_path([proved(self.wide(MAX_ORDERS + 1), "over")], []))
        self.assertEqual((over["verdict"], over["cells"]), ("ILL-FORMED", []))
        self.assertIn("the conditions of a pick hold 1025 orders, over the budget of 1024", over["findings"][0]["why"])

    def test_a_deck_whose_rule_would_write_a_pick_of_more_is_refused_when_it_is_read(self):
        """The row's first case compares its input 1,100 times, and its second once."""
        def wide(r: dict) -> None:
            row = next(x for x in r["rows"] if x["id"] == "test/derate")
            row["cases"][0]["when"] = ["and"] + [["le", "T", ["q", "40", "degC"]]] * 1100
        said = ask(with_rules(strips(), wide))
        self.assertEqual((said["verdict"], [f["file"] for f in said["findings"]]), ("ILL-FORMED", ["rules"]))
        self.assertIn("would compare 1101 orders, over the budget of 1024 for one pick", said["findings"][0]["why"])


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Reasons(Kernel):
    """The cells made from a deck of rules are the parts times the lines of the grid, so their
    reasons are not held by the size of the files. The verdict prints 500,000 bytes of them."""

    @staticmethod
    def loud(parts: int, lines: int) -> dict[str, str]:
        """A deck of one type with `lines` lines of the grid, each with a rule that reads four
        loads of 64-byte names, and `parts` parts that the card puts no load on: every cell
        is open, with the longest reason the kernel writes."""
        def name(prefix: str, k: int, width: int = 64) -> str:
            return f"{prefix}{k}".ljust(width, "q")
        loads = [name(f"L{j}_", 0) for j in range(4)]
        kind = {"type": "t", "what": "w", "fields": [{"name": "x", "dim": "force", "what": "w"}],
                "loads": [{"name": n, "dim": "force", "what": "w"} for n in loads]}
        rules = {"format": "petra-rules/0", "name": "loud", "about": "a", "rows": [], "types": [kind],
                 "grid": [{"type": "t", "mechanism": name("m", k), "what": "w", "anchor": TEST} for k in range(lines)],
                 "rules": [{"id": "r/" + name("i", k, 62), "type": "t", "mechanism": name("m", k), "anchor": TEST, "says": "s",
                            "le": [["add"] + [["load", n] for n in loads], "x"]} for k in range(lines)]}
        card = export.text({"format": "petra-card/0", "name": "c", "environment": None, "cases": [], "inputs": [], "claims": [],
                            "waivers": [], "tests": [], "probability_claims": []})
        made = [{"name": name("p", i), "type": "t", "lines": [{"field": "x", "args": [{"number": {"dim": "force", "lo": "1", "hi": "1"}}]}]}
                for i in range(parts)]
        design = {"format": "petra-design/0", "name": "c", "card": export.sha256(card), "quantities": [], "params": [], "parts": made}
        return {"card": card, "design": json.dumps(design, separators=(",", ":")), "deck": strips()["deck"],
                "rules": json.dumps(rules, separators=(",", ":")), "proofs": '{"format":"petra-proofs/0","cells":[]}'}

    def test_a_few_cells_keep_their_reasons_whole(self):
        said, _ = printed(self.loud(3, 3))
        self.assertEqual(len(said["cells"]), 9)
        self.assertTrue(all(c["reason"].startswith("the card puts no L0_0q") for c in said["cells"]))

    def test_ten_thousand_cells_print_half_a_megabyte_of_reasons_and_then_say_so(self):
        said, size = printed(self.loud(100, 100))
        reasons = [c["reason"] for c in said["cells"]]
        self.assertEqual(len(reasons), 10_000)
        kept = [r for r in reasons if r != UNSAID]
        self.assertEqual(reasons, kept + [UNSAID] * (len(reasons) - len(kept)), "the first reasons are kept, in the order of the cells")
        self.assertGreater(len(kept), 2000)
        self.assertLessEqual(sum(len(json.dumps(r)) - 2 for r in kept), MAX_REASONS)
        self.assertGreater(sum(len(json.dumps(r)) - 2 for r in kept), MAX_REASONS - 300)
        self.assertLess(size, 4_000_000)

    def test_the_cells_of_proofs_json_keep_every_reason(self):
        """Each is in the file once, so its reason prints in a few times the cell's own bytes."""
        cells = [{"subject": "", "mechanism": "", "entry": "", "state": "proved"}] * 17000
        said, _ = printed(old_path(cells, []))
        self.assertEqual({c["reason"] for c in said["cells"]}, {"the kernel has no rule yet for a proof with no tape"})


MAX_READ, MAX_TITLE = 1_000_000, 200
"""The limits as kernel/Petra/Files.lean sets them."""


def padded(steps: int) -> dict:
    """STRIPS with a row of 1,000 names that one more rule applies 400 times, and a type with
    a key of as many names as bring the deck to exactly `steps` steps to read: a name of
    under 8 characters is 2 steps, and one of 8 characters is 3."""
    body = copy.deepcopy(STRIPS)
    body["rows"].append({"id": "test/wide", "anchor": TEST, "gives": {"name": "y", "dim": "area"},
                         "takes": [{"name": "x", "dim": "area", "range": ["1 mm2", "2 mm2"]}], "is": ["add"] + ["x"] * 1000})
    body["grid"].append({"type": "pad", "mechanism": "pad.wide", "what": "made up", "anchor": TEST})
    body["rules"].append({"id": "test/wide", "type": "pad", "mechanism": "pad.wide", "anchor": TEST, "says": "made up",
                          "let": {f"v{i}": ["row", "test/wide", {"x": "area"}] for i in range(400)}, "le": ["area", "v0"]})
    body["types"].append({"type": "filler", "what": "made up", "fields": [{"name": "k", "what": "made up", "one_of": []}]})
    names = body["types"][-1]["fields"][0]["one_of"]
    gap = steps - grid._steps(body)
    names.extend(["n" * 8] * (gap % 2) + [f"n{i}" for i in range((gap - 3 * (gap % 2)) // 2)])
    assert names and grid._steps(body) == steps, grid._steps(body)
    return body


class Reading(Kernel):
    """Reading a deck takes at most 1,000,000 steps (docs/deck.md, "The size of a deck"): the
    size of its JSON, and the size of a row again each time a rule applies it. The kernel
    and petra/grid.py make the count from the file and refuse the same decks."""

    def test_the_grid_counts_the_first_deck_far_under_the_limit(self):
        """The deck with four rules takes 5,500 steps: 3,874 for its file, and 1,626 for the
        14 times its rules apply a row. The deck with fifteen rules that the branch `rework`
        has in its place takes 10,503: 6,360, and 4,143 for 37 times, since its tables of
        holes and edge distances list the sizes their last lines give. The two needs of a lap,
        added 2026-11-12, took 55 of its file's steps. Ten decks of that size would be about a
        tenth of the limit."""
        deck = next(d for d in grid.decks() if "lap" in d.types)
        body = json.loads(deck.text)
        self.assertIn((len(body["rules"]), grid._size(body), grid._steps(body)), [(4, 3874, 5500), (15, 6360, 10503)])
        self.assertLess(grid._steps(body) * 10 * 8, MAX_READ, "ten decks of its size are under an eighth of the limit")

    def test_the_count_is_the_size_of_the_file_and_of_a_row_for_each_time_a_rule_applies_it(self):
        self.assertEqual([grid._size(t) for t in ("", "n" * 7, "n" * 8, "n" * 15, "n" * 16, "é" * 8, "𝄞" * 8)], [2, 2, 3, 3, 4, 3, 3],
                         "a text is two, and one more for each eight characters, whatever bytes they take")
        self.assertEqual([grid._size(v) for v in (0, 1.5, True, None, [], {}, [[]], {"key": []})], [1, 1, 1, 1, 1, 1, 2, 2], "a key is not counted")
        row = {"id": "r", "is": ["add", "x", "x"]}
        self.assertEqual(grid._size(row), 10, "the object, a text, and a list of three texts")
        rule = {"id": "q", "le": [["row", "r", {"x": "f"}], ["row", "none", {}]], "let": {"a": ["mul", ["row", "r", {"x": "f"}], "2"]}}
        body = {"format": "petra-rules/0", "rows": [row, {**row, "is": "x"}], "rules": [rule], "about": ["row", "r", {}]}
        self.assertEqual(grid._steps(body), grid._size(body) + 2 * 10, "the first row of the id, for each list in a rule, and nowhere else")

    def test_the_grid_reads_a_deck_of_a_million_steps_and_no_more(self):
        self.assertEqual(grid.read_deck(json.dumps(padded(MAX_READ))).name, "test-strips")
        with self.assertRaisesRegex(grid.DeckError, "reading this deck takes 1000001 steps, over the budget of 1000000"):
            grid.read_deck(json.dumps(padded(MAX_READ + 1)))

    @unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
    def test_the_kernel_reads_a_deck_of_a_million_steps_and_no_more(self):
        honest = ask(strips())
        at = ask({**strips(), "rules": json.dumps(padded(MAX_READ))})
        self.assertEqual(at["findings"], [])
        self.assertEqual([c for c in states(at) if c[1] != "pad.wide"], states(honest), "the deck is read, and the other cells are as before")
        over = ask({**strips(), "rules": json.dumps(padded(MAX_READ + 1))})
        self.assertEqual((over["verdict"], over["cells"]), ("ILL-FORMED", []))
        self.assertEqual([(f["rule"], f["file"]) for f in over["findings"]], [("shape", "rules")])
        self.assertIn("reading this deck takes 1000001 steps, over the budget of 1000000", over["findings"][0]["why"])

    @unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
    def test_the_kernel_and_the_grid_count_a_text_by_its_characters_whatever_bytes_they_take(self):
        """A deck over the limit, so that each says what it counted. Its `about` holds 36
        characters of one, two, three and four bytes. The file writes them as themselves or
        as escapes, and a character outside the first 65,536 as a pair of escapes."""
        body = padded(MAX_READ + 50)
        body["about"] = "a" * 9 + "\u00e9" * 9 + "\u20ac" * 9 + "\U0001d11e" * 9
        self.assertEqual(grid._size(body["about"]), 2 + 36 // 8)
        count = grid._steps(body)
        self.assertGreater(count, MAX_READ)
        for text in (json.dumps(body), json.dumps(body, ensure_ascii=False)):
            with self.assertRaisesRegex(grid.DeckError, f"reading this deck takes {count} steps"):
                grid.read_deck(text)
            over = ask({**strips(), "rules": text})
            self.assertIn(f"reading this deck takes {count} steps, over the budget of 1000000", over["findings"][0]["why"])

    def test_the_name_of_a_card_is_at_most_200_bytes_for_a_design_with_parts(self):
        deck = grid.read_deck(json.dumps(STRIPS))

        def check(name: str):
            with mock.patch.object(grid, "decks", lambda: (deck,)):
                return grid.check(petra.lang.parse_design(CARD.replace('card "strips"', f'card "{name}"'), DESIGN, "strips.petra", build_registry()), deck)

        self.assertEqual(check("n" * MAX_TITLE)[0].verdict, "PASS")
        with self.assertRaisesRegex(ComponentError, "the name of the card is at most 200 characters"):
            check("n" * (MAX_TITLE + 1))

    @unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
    def test_the_kernel_holds_the_two_names_to_the_same_200_bytes(self):
        """The label of each input of a tape holds the name of the card or of the design. A
        name of 250,000 characters and 3,000 numbers made the kernel hold 0.8 GB."""
        at = ask(strips(card=CARD.replace('card "strips"', 'card "' + "n" * MAX_TITLE + '"')))
        self.assertEqual((at["verdict"], at["findings"]), ("PASS", []))
        over = ask(strips(card=CARD.replace('card "strips"', 'card "' + "n" * (MAX_TITLE + 1) + '"')))
        self.assertEqual([(f["rule"], f["file"], f["item"]) for f in over["findings"]], [("shape", "card", "name"), ("shape", "design", "name")])
        self.assertIn("the name of the card prints in at most 200 bytes for a design with parts, and this one in 201", over["findings"][0]["why"])


if __name__ == "__main__":
    unittest.main()
