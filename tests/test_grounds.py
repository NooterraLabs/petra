"""Plan step 1.6, its last part: every fact behind a verdict has an origin that is checked.

A key is the card's to state unless the deck says that the designer chooses it, and why. A line of the grid is excused
on a ground the readers check, and not on the word of the deck's author. A cell that reads no quantity of the part or of
the card is one of stated keys, whatever the form of its rule, and makes no PASS. And what the fifteenth review found
beside these: a long reason that cost the kernel its time, reasons that crowded out the reason of a refuted cell, a mean
that two ways in still dropped, and a guard on the kernel's answer that did not know a stated cell.

Each test holds the kernel and petra/grid.py to the same answer, through the helpers of tests/test_deck_features.py.
"""
from __future__ import annotations

import copy
import json
import re
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from petra import export, grid, verify
from tests.test_deck_features import HEAD, KERNEL, asks, cells, design, ill_formed, key, kind, load, made_up, no_deck, parsed, part, reads, reason, rule, size
from tests.test_kernel_attacks3 import empty_card, measured, with_rules, PROCESSOR_SECONDS
from tests.test_kernel_grid import ask

ROOT = Path(__file__).resolve().parents[1]
WHY = "made up for the tests"
PULL = {"name": "pull", "dim": "force", "least": "0 N", "what": "the pull"}


def hoist(*keys: dict, lines: list = (), rules: list = (), loads: list = (PULL,)) -> dict:
    """A deck of one type, as written: nothing is signed or chosen for it, and no excuse is given a ground."""
    return made_up([kind("hoist", size("span"), *keys, loads=list(loads))], [asks("hoist.span", "hoist"), *lines],
                   [rule("span", "hoist", "hoist.span", le=[["q", "1", "mm"], "span"]), *rules], signs=False)


class AKeyIsTheCardsOrChosen(unittest.TestCase):
    def test_a_key_says_nothing_or_signed_or_chosen_with_why(self):
        for marks in ({}, {"signed": True}, {"chosen": "the designer picks it, and the drawing says so"}, {"chosen": "x", "signed": False},
                      {"chosen": "the drawing says so", "optional": True}):
            with self.subTest(marks=marks):
                reads(self, hoist({**key("grade", "a", "b"), **marks}))

    def test_a_key_that_is_neither_or_both_is_refused_by_both_readers(self):
        for marks in ({"signed": False}, {"chosen": ""}, {"chosen": " \t"}, {"chosen": "1 2 3."}, {"chosen": " 　"}, {"chosen": 5}, {"chosen": None},
                      {"chosen": ["why"]}, {"chosen": "why", "signed": True}):
            with self.subTest(marks=marks):
                mine, kernels = no_deck(self, hoist({**key("grade", "a", "b"), **marks}))
                self.assertIn(grid.CHOSEN, mine)
                self.assertIn(grid.CHOSEN, kernels)

    def test_a_key_that_may_be_left_unstated_is_a_chosen_one(self):
        mine, kernels = no_deck(self, hoist({**key("grade", "a", "b"), "optional": True}))
        self.assertIn("a field is `signed` or `optional`, and not both", mine)
        self.assertIn("a field is `signed` or `optional`, and not both", kernels)

    def test_a_design_writes_a_chosen_key_and_not_one_the_deck_says_nothing_of(self):
        """Until this step a key with no mark was the design's. It is the card's now, so a deck's author says which keys a
        designer chooses, and a design that writes any other is refused."""
        text = design(part("hoist", "h", span="5 mm", grade="a"))
        mine, kernels = ill_formed(self, hoist(key("grade", "a", "b")), text, states=False)
        self.assertIn("h.grade is for the card to state", mine)
        self.assertIn("is for the card to state", kernels)
        found, verdict, _ = cells(self, hoist({**key("grade", "a", "b"), "chosen": WHY}), text, states=False)
        self.assertEqual((verdict, found["h", "hoist.span", "span"]), ("UNKNOWN", "proved"), "the key that nothing reads is an open cell, and the design is read")
        stated = HEAD + 'given h.grade is a signed "t@example.org" source "test"\n'
        found, verdict, _ = cells(self, hoist(key("grade", "a", "b")), design(part("hoist", "h", span="5 mm", grade="given h.grade")), stated, states=False)
        self.assertEqual(found["h", "hoist.span", "span"], "proved", "and the card states the key that has no mark")

    def test_the_shipped_deck_says_of_each_key_whose_it_is(self):
        deck = json.loads((ROOT / "petra" / "decks" / "aisc360.json").read_text(encoding="utf-8"))
        keys = {(t["type"], f["name"]): ("chosen" if "chosen" in f else "signed") for t in deck["types"] for f in t["fields"] if "one_of" in f}
        self.assertEqual(keys, {("lap", "fastener"): "chosen", ("lap", "threads"): "chosen", ("lap", "holes"): "signed", ("lap", "surface"): "signed"})


def excused(unless: dict | None, *more_lines: dict, rules: list = (), keys: tuple = ()) -> dict:
    """The hoist with a second line, `hoist.other`, excused as given, and whatever lines and rules a test adds."""
    line = asks("hoist.other", "hoist", **({} if unless is None else {"unless": unless}))
    return hoist(*keys, lines=[line, *more_lines], rules=list(rules))


class AnExcuseHasAGround(unittest.TestCase):
    def test_an_excuse_with_a_reason_and_no_ground_is_refused(self):
        """The fault this closes: a line that said why it could not arise, in words nothing checked."""
        for unless in ({"why": "it cannot arise"}, {"why": "it cannot arise", "loads": ["pull"], "least": ["pull", "0 N"]},
                       {"why": "it cannot arise", "when": ["is", "grade", "a"], "with": ["hoist.span"]}):
            with self.subTest(unless=unless):
                mine, kernels = no_deck(self, excused(unless, keys=({**key("grade", "a", "b"), "signed": True},)))
                self.assertIn(grid.GROUND, mine)
                self.assertIn(grid.GROUND, kernels)

    def test_a_reason_has_a_letter_in_it(self):
        for why in ("", " ", "\t\r\n", "...", "0", " ", "​", "　", 0, None, ["a reason"], ...):
            with self.subTest(why=why):
                unless = {"loads": ["pull"], **({} if why is ... else {"why": why})}
                mine, kernels = no_deck(self, excused(unless))
                for said in (mine, kernels):
                    self.assertIn("grid hoist.other: unless: it says why, in a text with a letter in it", said)
        reads(self, excused({"loads": ["pull"], "why": "x"}))

    def test_a_least_is_one_the_type_declares(self):
        reads(self, excused({"why": "a pull is never a push", "least": ["pull", "0 N"]}))
        reads(self, excused({"why": "a pull is never a push", "least": ["pull", "-1 kN"]}))
        for least, says in ((["pull", "1 N"], "hoist does not say that pull is at least 1 N"), (["span", "0 mm"], "span has no `least` in hoist"),
                            (["push", "0 N"], "push is no load and no field of hoist"), (["pull", "0 mm"], "the value of `least` is of another dimension than pull"),
                            (["pull"], "`least` is a load or a quantity of the type and a value: [NAME, VALUE]"),
                            ("pull", "`least` is a load or a quantity of the type and a value: [NAME, VALUE]"),
                            ([["pull"], "0 N"], "`least` is a load or a quantity of the type and a value: [NAME, VALUE]")):
            with self.subTest(least=least):
                mine, kernels = no_deck(self, excused({"why": "a pull is never a push", "least": least}))
                self.assertIn(f"grid hoist.other: unless: {says}", mine)
                self.assertIn(f"grid hoist.other: unless: {says}", kernels)

    def test_loads_names_each_load_of_the_type_and_no_other(self):
        reads(self, excused({"why": "it takes a pull alone", "loads": ["pull"]}))
        for loads in ([], ["pull", "pull"], ["push"], ["pull", "push"], "pull", [1]):
            with self.subTest(loads=loads):
                mine, kernels = no_deck(self, excused({"why": "it takes a pull alone", "loads": loads}))
                self.assertIn("grid hoist.other: unless: `loads` names each load of hoist once and no other", mine)
                self.assertIn("grid hoist.other: unless: `loads` names each load of hoist once and no other", kernels)

    def test_with_names_other_lines_that_stand_on_their_own(self):
        reads(self, excused({"why": "the span answers it", "with": ["hoist.span"]}))
        third = asks("hoist.third", "hoist", unless={"why": "the other answers it", "with": ["hoist.other"]})
        for unless, more, says in (({"why": "x", "with": []}, (), "`with` names other lines of the grid, each once"),
                                   ({"why": "x", "with": ["hoist.other"]}, (), "`with` names other lines of the grid, each once"),
                                   ({"why": "x", "with": ["hoist.span", "hoist.span"]}, (), "`with` names other lines of the grid, each once"),
                                   ({"why": "x", "with": ["hoist.none"]}, (), "it is answered with hoist.none, which the grid does not ask of hoist")):
            with self.subTest(unless=unless):
                mine, kernels = no_deck(self, excused(unless, *more))
                self.assertIn(says, mine)
                self.assertIn(says, kernels)
        mine, kernels = no_deck(self, excused({"why": "the span answers it", "with": ["hoist.span"]}, third))
        self.assertIn("grid hoist.third: unless: it is answered with hoist.other, which is itself answered with other lines", mine)
        self.assertIn("grid hoist.third: unless: it is answered with hoist.other, which is itself answered with other lines", kernels)

    def test_no_rule_answers_a_line_that_is_excused_for_the_type(self):
        for unless in ({"why": "x", "loads": ["pull"]}, {"why": "x", "least": ["pull", "0 N"]}, {"why": "x", "with": ["hoist.span"]}):
            with self.subTest(unless=unless):
                mine, kernels = no_deck(self, excused(unless, rules=[rule("other", "hoist", "hoist.other", le=[["q", "2", "mm"], "span"])]))
                says = ("the grid says hoist.other is answered with other lines for hoist" if "with" in unless
                        else "the grid excuses hoist.other by what hoist declares, and no rule answers such a line")
                self.assertIn(f"rule made-up/other: {says}", mine)
                self.assertIn(f"rule made-up/other: {says}", kernels)

    def test_a_line_excused_by_the_loads_of_the_type_asks_of_no_part(self):
        unless = {"why": "it takes a pull alone", "loads": ["pull"]}
        found, verdict, said = cells(self, excused(unless), design(part("hoist", "h", span="5 mm")))
        self.assertEqual((verdict, found["h", "hoist.other", ""], reason(said, "hoist.other")), ("PASS", "not_applicable", unless["why"]))

    def test_the_least_of_a_load_excuses_a_part_the_card_puts_the_load_on_in_every_case(self):
        """The sixteenth review: the least of a load was checked when the deck was read and then held for every part, so a
        line said to arise only under a push was not applicable for a part whose card stated no pull at all. Nothing says
        that a load the card leaves out is there. The line is excused where the card states the load in every case, and is
        open, for the card to waive, for any other part."""
        deck = excused({"why": "a pull is never a push", "least": ["pull", "0 N"]}, rules=[rule("pull", "hoist", "hoist.span", le=[["q", "1", "N"], ["load", "pull"]])])
        text = design(part("hoist", "h", span="5 mm"))
        day, night = load("day", "h pull in [2 N, 5 N]"), load("night", "h pull in [2 N, 3 N]")
        found, verdict, said = cells(self, deck, text, HEAD + day + night)
        self.assertEqual((verdict, found["h", "hoist.other", ""], reason(said, "hoist.other")), ("PASS", "not_applicable", "a pull is never a push"))
        for label, card in (("no case", HEAD), ("a case without it", HEAD + day + "\nload night {\n  signed \"t@example.org\" source \"test\"\n}\n")):
            with self.subTest(card=label):
                found, verdict, said = cells(self, deck, text, card)
                self.assertEqual((found["h", "hoist.other", ""], reason(said, "hoist.other")), ("open", grid.NO_LOAD.format("pull", "h")))
                self.assertNotIn(verdict, ("PASS", "PASS_WAIVED"))
        # Two parts, of which the card loads one: the line is excused for that one alone.
        both = design(part("hoist", "h", span="5 mm"), part("hoist", "g", span="5 mm"))
        found, verdict, said = cells(self, deck, both, HEAD + day)
        self.assertEqual((verdict, found["h", "hoist.other", ""], found["g", "hoist.other", ""]), ("UNKNOWN", "not_applicable", "open"))
        bare = excused({"why": "a pull is never a push", "least": ["pull", "0 N"]})
        waive = '\nwaive hoist.other on h by "t@example.org" reason "this hoist is hung, and is never pushed"\n'
        found, verdict, said = cells(self, bare, text)
        self.assertEqual((verdict, found["h", "hoist.other", ""], reason(said, "hoist.other")), ("UNKNOWN", "open", grid.NO_LOAD.format("pull", "h")))
        found, verdict, said = cells(self, bare, text, HEAD + waive)
        self.assertEqual((verdict, found["h", "hoist.other", ""]), ("PASS_WAIVED", "waived"), "the card may answer for it, as for a line with no rule")

    def test_the_reason_of_a_line_a_least_leaves_open_is_cut_as_the_kernel_cuts_it(self):
        """The sixteenth review, its second round: with names of 64 bytes the reason is past the 200 bytes a reason prints in.
        The kernel cut it and the grid printed it whole."""
        name, pull = "p" * 64, "q" * 64
        deck = made_up([kind("hoist", size("span"), loads=[{"name": pull, "dim": "force", "least": "0 N", "what": "the pull"}])],
                       [asks("hoist.span", "hoist"), asks("hoist.other", "hoist", unless={"why": "a pull is never a push", "least": [pull, "0 N"]})],
                       [rule("span", "hoist", "hoist.span", le=[["q", "1", "mm"], "span"])], signs=False)
        found, verdict, said = cells(self, deck, design(part("hoist", name, span="5 mm")))
        self.assertEqual(found[name, "hoist.other", ""], "open")
        self.assertEqual(reason(said, "hoist.other"), grid._clip(grid.NO_LOAD.format(pull, name)))
        self.assertTrue(reason(said, "hoist.other").endswith("more characters)"))
        deck_, read = parsed(deck, design(part("hoist", name, span="5 mm")))
        self.assertEqual([c.why for c in grid.check(read, deck_)[0].cells if c.mechanism == "hoist.other"], [reason(said, "hoist.other")])

    def test_the_least_of_a_quantity_excuses_a_part_that_states_it(self):
        """A quantity that a part may leave unstated has no value for a part that does, and its least then says nothing."""
        reach = {"name": "reach", "dim": "length", "least": "1 mm", "optional": True, "what": "the reach"}
        deck = made_up([kind("hoist", size("span"), reach)],
                       [asks("hoist.span", "hoist"), asks("hoist.reach", "hoist"), asks("hoist.other", "hoist", unless={"why": "a reach is a millimetre at least", "least": ["reach", "1 mm"]})],
                       [rule("span", "hoist", "hoist.span", le=[["q", "1", "mm"], "span"]), rule("reach", "hoist", "hoist.reach", le=["reach", ["q", "9", "mm"]])], signs=False)
        found, verdict, said = cells(self, deck, design(part("hoist", "h", span="5 mm", reach="2 mm")))
        self.assertEqual((verdict, found["h", "hoist.other", ""], reason(said, "hoist.other")), ("PASS", "not_applicable", "a reach is a millimetre at least"))
        found, verdict, said = cells(self, deck, design(part("hoist", "h", span="5 mm", reach="unstated")))
        self.assertEqual((found["h", "hoist.other", ""], reason(said, "hoist.other")), ("open", grid.NO_VALUE.format("reach", "h")))
        self.assertNotIn(verdict, ("PASS", "PASS_WAIVED"), "leaving the quantity out is no way past the line")
        waive = '\nwaive hoist.other on h by "t@example.org" reason "the reach of this hoist is on its drawing"\n'
        found, verdict, said = cells(self, deck, design(part("hoist", "h", span="5 mm", reach="unstated")), HEAD + waive)
        self.assertEqual((found["h", "hoist.other", ""], found["h", "hoist.reach", "reach"]), ("waived", "open"), "a waiver rests the line, and not the rule that reads the reach")
        self.assertNotIn(verdict, ("PASS", "PASS_WAIVED"))

    def test_a_line_answered_with_others_is_settled_as_they_are(self):
        """`hoist.other` is answered with `hoist.span`, which has a rule, and with `hoist.care`, which has none and so is
        open until a signer waives it. The line cannot arise while both are settled, and is open with the first of them
        that is not. A waiver of the line itself rests nothing: the signer answers for the line it is answered with."""
        deck = excused({"why": "the span and the care answer it", "with": ["hoist.span", "hoist.care"]}, asks("hoist.care", "hoist"))
        fits, short = design(part("hoist", "h", span="5 mm")), design(part("hoist", "h", span="0.5 mm"))
        waive = lambda line: f'\nwaive {line} on h by "t@example.org" reason "test"\n'      # noqa: E731
        found, verdict, said = cells(self, deck, fits)
        self.assertEqual((verdict, found["h", "hoist.other", ""], reason(said, "hoist.other")), ("UNKNOWN", "open", grid.ALONG.format("hoist.care", "h")))
        found, verdict, said = cells(self, deck, fits, HEAD + waive("hoist.care"))
        self.assertEqual((verdict, found["h", "hoist.care", ""], found["h", "hoist.other", ""], reason(said, "hoist.other")),
                         ("PASS_WAIVED", "waived", "not_applicable", "the span and the care answer it"))
        found, verdict, said = cells(self, deck, fits, HEAD + waive("hoist.other"))
        self.assertEqual((verdict, found["h", "hoist.other", ""], found["h", "hoist.care", ""]), ("UNKNOWN", "open", "open"), "a waiver of the line itself rests nothing")
        found, verdict, said = cells(self, deck, short, HEAD + waive("hoist.care"))
        self.assertEqual((verdict, found["h", "hoist.other", ""], reason(said, "hoist.other")), ("FAIL", "open", grid.ALONG.format("hoist.span", "h")))
        # The line may stand before the lines it is answered with: it is settled once every cell is made.
        before = copy.deepcopy(deck)
        before["grid"] = [before["grid"][1], before["grid"][0], before["grid"][2]]
        found, verdict, _ = cells(self, before, fits, HEAD + waive("hoist.care"))
        self.assertEqual((verdict, list(found)[0], found["h", "hoist.other", ""]), ("PASS_WAIVED", ("h", "hoist.other", ""), "not_applicable"))

    def test_slip_of_a_lap_follows_the_line_of_tightening(self):
        """The shipped deck. Whether a joint must be slip-critical is the line of tightening's to answer, which has no rule
        and is a signer's to waive. Slip was not applicable on the deck's word alone, whatever stood open."""
        text, card = [(ROOT / "examples" / "deck" / name).read_text(encoding="utf-8") for name in ("lap_pass.petra", "lap_pass.card")]
        found, verdict, said = cells(self, json.loads((ROOT / "petra" / "decks" / "aisc360.json").read_text(encoding="utf-8")), text, card, states=False)
        self.assertEqual((verdict, found["splice", "lap.tightening", ""], found["splice", "lap.slip", ""]), ("PASS_WAIVED", "waived", "not_applicable"))
        unwaived = "\n".join(line for line in card.splitlines() if not line.startswith("waive lap.tightening ")) + "\n"
        found, verdict, said = cells(self, json.loads((ROOT / "petra" / "decks" / "aisc360.json").read_text(encoding="utf-8")), text, unwaived, states=False)
        self.assertEqual((verdict, found["splice", "lap.tightening", ""], found["splice", "lap.slip", ""], reason(said, "lap.slip")),
                         ("UNKNOWN", "open", "open", grid.ALONG.format("lap.tightening", "splice")))


class ACellThatReadsNothing(unittest.TestCase):
    """The fifteenth review: a deck may write a requirement over keys as an inequality, and a cell of it was the proved cell
    a PASS needs. A tape none of whose roots reads an input reads no quantity of the part or of the card, so its cell is one
    of stated keys."""

    def constant(self, low: str, high: str, *more: dict) -> dict:
        return made_up([kind("hoist", size("span"))], [asks("hoist.fixed", "hoist"), *(asks("hoist.span", "hoist") for _ in more)],
                       [rule("fixed", "hoist", "hoist.fixed", le=[["q", low, "mm"], ["q", high, "mm"]]), *more], signs=False)

    def test_a_rule_of_numbers_alone_makes_no_pass(self):
        found, verdict, said = cells(self, self.constant("1", "2"), design(part("hoist", "h", span="5 mm")))
        self.assertEqual((verdict, found["h", "hoist.fixed", "fixed"], reason(said, "hoist.fixed")), ("UNKNOWN", "proved", grid.NOTHING_READ))
        if verify.binary():
            self.assertEqual([c.get("stated") for c in said["cells"] if c["mechanism"] == "hoist.fixed"], [True])

    def test_it_fails_when_refuted_and_passes_beside_a_cell_that_reads_the_part(self):
        _, verdict, _ = cells(self, self.constant("2", "1"), design(part("hoist", "h", span="5 mm")))
        self.assertEqual(verdict, "FAIL")
        real = rule("span", "hoist", "hoist.span", le=[["q", "1", "mm"], "span"])
        found, verdict, said = cells(self, self.constant("1", "2", real), design(part("hoist", "h", span="5 mm")))
        self.assertEqual((verdict, found["h", "hoist.span", "span"]), ("PASS", "proved"))

    def test_an_open_cell_of_such_a_rule_has_no_mark_in_either_reader(self):
        """Cosine of a third of pi is a half, which no interval decides. The cell is open and says nothing, so neither
        reader marks it: the kernel marked it once and the grid did not, and `petra check` would have called that a
        difference."""
        bare = made_up([kind("hoist", size("span"))], [asks("hoist.fixed", "hoist")],
                       [rule("fixed", "hoist", "hoist.fixed", le=[["cos", ["div", "pi", "3"]], "1/2"])], signs=False)
        deck, read = parsed(bare, design(part("hoist", "h", span="5 mm")))
        report, files = grid.check(read, deck)
        self.assertEqual([(c.state, c.stated) for c in report.cells if c.mechanism == "hoist.fixed"], [("open", False)])
        if verify.binary():
            self.assertEqual([(c["state"], c.get("stated")) for c in ask(files)["cells"] if c["mechanism"] == "hoist.fixed"], [("open", None)])

    def test_an_input_that_no_root_reads_is_nothing_read(self):
        """The sixteenth review: a row took two quantities and was the first of them, and a rule bound the second to the
        span. The tape held the span as an input that nothing read, and its cell was the proved cell of a PASS."""
        row = {"id": "made-up/first", "anchor": {"standard": "s", "clause": "1"}, "gives": {"name": "L", "dim": "length", "what": "L"},
               "takes": [{"name": name, "dim": "length", "what": name, "range": ["1 mm", "9 mm"]} for name in "xy"], "is": "x"}
        bare = made_up([kind("hoist", size("span"))], [asks("hoist.fixed", "hoist")],
                       [rule("fixed", "hoist", "hoist.fixed", le=[["row", "made-up/first", {"x": ["q", "1", "mm"], "y": "span"}], ["q", "2", "mm"]])], rows=[row], signs=False)
        found, verdict, said = cells(self, bare, design(part("hoist", "h", span="5 mm")))
        self.assertEqual((verdict, found["h", "hoist.fixed", "fixed"], reason(said, "hoist.fixed")), ("UNKNOWN", "proved", grid.NOTHING_READ))
        bare["rules"][0]["le"][0][2] = {"x": "span", "y": ["q", "1", "mm"]}
        found, verdict, said = cells(self, bare, design(part("hoist", "h", span="1.5 mm")))
        self.assertEqual((verdict, found["h", "hoist.fixed", "fixed"], reason(said, "hoist.fixed")), ("PASS", "proved", ""), "and the row that is the span reads it")

    def test_a_rule_that_reads_a_quantity_and_does_not_turn_on_it_is_still_worked_out(self):
        """A known limit, which the pages state: nothing but a tape that reads no input is told from a check. A deck's author
        who writes nought times the span has written a rule that holds for every part, as one who writes a limit of a
        kilometre has, and answers for it as for every rule."""
        idle = made_up([kind("hoist", size("span"))], [asks("hoist.fixed", "hoist")],
                       [rule("fixed", "hoist", "hoist.fixed", le=[["mul", "0", "span"], ["q", "1", "mm"]])], signs=False)
        found, verdict, said = cells(self, idle, design(part("hoist", "h", span="5 mm")))
        self.assertEqual((verdict, found["h", "hoist.fixed", "fixed"]), ("PASS", "proved"))

    def test_the_report_says_stated_and_why_the_design_is_unknown(self):
        bare = made_up([kind("hoist")], [asks("hoist.fixed", "hoist")], [rule("fixed", "hoist", "hoist.fixed", le=[["q", "1", "mm"], ["q", "2", "mm"]])], signs=False)
        deck, read = parsed(bare, design(part("hoist", "h")))
        report = grid.check(read, deck)[0]
        lines = report.lines()
        self.assertEqual((report.status, [c.state for c in report.cells]), ("UNKNOWN", ["proved"]), "one cell, proved, and no pass")
        self.assertTrue(any(re.search(r"h/hoist\.fixed\s+stated\s", line) and grid.NOTHING_READ in line for line in lines), lines)
        self.assertTrue(any(line.startswith("unknown    no cell was worked out") for line in lines), lines)

    def test_a_reason_of_a_deck_prints_on_one_line(self):
        forged = "x\n  h/hoist.span  proved  span\nmade-up: PASS"
        deck, read = parsed(made_up([kind("hoist", size("span"))], [asks("hoist.span", "hoist"), asks("hoist.other", "hoist", unless={"why": forged, "loads": []})],
                                    [rule("span", "hoist", "hoist.span", le=["span", ["q", "1", "mm"]])], signs=False), design(part("hoist", "h", span="5 mm")))
        lines = grid.check(read, deck)[0].lines()
        self.assertEqual([line for line in lines if "PASS" in line], [line for line in lines if "hoist.other" in line], "the words stand on the line of their own cell")
        self.assertEqual(sum(line.startswith("  h/hoist.span") for line in lines), 1)

    def test_a_name_and_an_anchor_of_a_deck_print_on_one_line_too(self):
        """The sixteenth review: a line feed in an anchor or in the name of a mechanism still wrote lines of the report."""
        forged = "1)\nmade-up: PASS\n  h/hoist.span  proved   0.1  span (std"
        deck, read = parsed(made_up([kind("hoist", size("span"))], [{**asks("hoist.span", "hoist"), "anchor": {"standard": "std", "clause": forged}},
                                                                    asks("hoist.x\n  h/hoist.y  proved", "hoist", unless={"why": "x", "loads": []})],
                                    [{**rule("span", "hoist", "hoist.span", le=["span", ["q", "1", "mm"]]), "anchor": {"standard": "std", "clause": forged}}], signs=False),
                            design(part("hoist", "h", span="5 mm")))
        report = grid.check(read, deck)[0]
        lines = report.lines()
        self.assertEqual(len(lines), 3 + len(report.cells), lines)
        self.assertEqual([line.split()[0] for line in lines[3:]], ["h/hoist.span", "h/hoist.x"])

    def test_no_item_of_the_report_holds_a_line_feed(self):
        """The second round: the deck's name on the line of the rules, and the name of a key in the completion a waived cell
        rests on, still wrote lines. Every item of the report is one line now, whatever the texts in it hold."""
        deck = made_up([kind("hoist", size("span"), {**key("grade", "a\nmade-up: PASS", "b"), "chosen": WHY, "optional": True})],
                       [asks("hoist.span", "hoist"), asks("hoist.grade", "hoist")],
                       [rule("span", "hoist", "hoist.span", le=[["q", "1", "mm"], "span"]), rule("grade", "hoist", "hoist.grade", requires=["is", "grade", "a\nmade-up: PASS"])],
                       signs=False)
        deck["name"] = "made-up\nmade-up: PASS\n"
        waive = '\nwaive hoist.grade on h by "t@example.org" reason "test"\n'
        deck_, read = parsed(deck, design(part("hoist", "h", span="5 mm", grade="unstated")), HEAD + waive, states=False)
        with unittest.mock.patch.object(grid, "decks", lambda: (deck_,)):
            report = grid.check(read, deck_)[0]
        lines = report.lines()
        self.assertTrue(any("rested where" in line for line in lines), lines)
        self.assertEqual([line for line in lines if "\n" in line], [])


class TheFirstKeyLeftUnstated(unittest.TestCase):
    def test_both_readers_name_the_first_key_a_requirement_reads(self):
        """The attacker, at seed 20: a rule required two keys that a part left unstated, and the kernel named the first as the
        rule writes them where the grid named the first by name. It was so before this step. The pages fix the order for a
        rule with `requires`, so both name the same key now, on an open cell and on a waived one."""
        for first, second in (("seal", "maker"), ("maker", "seal")):
            keys = [{**key(name, "none", "full"), "optional": True, "chosen": WHY} for name in ("seal", "maker")]
            deck = made_up([kind("hoist", size("span"), *keys)], [asks("hoist.span", "hoist"), asks("hoist.sealed", "hoist")],
                           [rule("span", "hoist", "hoist.span", le=[["q", "1", "mm"], "span"]),
                            rule("sealed", "hoist", "hoist.sealed", requires=["and", ["is", first, "none"], ["is", second, "none"]])], signs=False)
            text = design(part("hoist", "h", span="5 mm", seal="unstated", maker="unstated"))
            for waive in ("", '\nwaive hoist.sealed on h by "t@example.org" reason "test"\n'):
                with self.subTest(first=first, waived=bool(waive)):
                    deck_, read = parsed(deck, text, HEAD + waive, states=False)
                    report, files = grid.check(read, deck_)
                    (mine,) = [c for c in report.cells if c.mechanism == "hoist.sealed"]
                    self.assertIn(f"h.{first} is unstated: its maker states none, and the rule reads it", mine.why)
                    if verify.binary():
                        (theirs,) = [c for c in ask(files)["cells"] if c["mechanism"] == "hoist.sealed"]
                        self.assertIn(f"h.{first} is unstated: its maker states none, and the rule reads it", theirs["reason"])


class TheGuardKnowsAStatedCell(unittest.TestCase):
    @KERNEL
    def test_a_pass_on_stated_cells_alone_is_no_answer(self):
        only = made_up([kind("hoist", {**key("grade", "a", "b"), "chosen": WHY})], [asks("hoist.grade", "hoist")],
                       [rule("grade-a", "hoist", "hoist.grade", requires=["is", "grade", "a"])], signs=False)
        deck, read = parsed(only, design(part("hoist", "h", grade="a")), states=False)
        report, files = grid.check(read, deck)
        said = ask(files)
        self.assertEqual((said["verdict"], [c.get("stated") for c in said["cells"]]), ("UNKNOWN", [True]))
        forged = json.dumps({**said, "verdict": "PASS"}).encode("utf-8")
        with self.assertRaises(verify.BadAnswer):
            verify.taken("petra-verify", 0, forged, b"")
        mine = [(c.subject, c.mechanism, c.entry, c.state) for c in report.cells]
        self.assertEqual(verify.differs(mine, report.verdict, deck.hash, said, report.waived(), report.completions(), [c.stated for c in report.cells]), "")
        self.assertIn("stated keys", verify.differs(mine, report.verdict, deck.hash, said, report.waived(), report.completions(), [False]))


class AMeanReachesNoFile(unittest.TestCase):
    def test_every_way_to_the_kernels_files_refuses_a_mean(self):
        text, card = [(ROOT / "examples" / "deck" / name).read_text(encoding="utf-8") for name in ("lap_pass.petra", "lap_pass.card")]
        with_mean = card.replace("on splice pull in [0 kip, 45 kip]", "on splice pull in [0 kip, 45 kip] mean 44 kip")
        self.assertNotEqual(with_mean, card)
        with tempfile.TemporaryDirectory() as held:
            folder = Path(held)
            (folder / "mean.petra").write_text(text, encoding="utf-8")
            (folder / "mean.card").write_text(with_mean, encoding="utf-8")
            for argv in ([str(folder / "mean.petra"), "--no-physics", "--out", str(folder / "a")], [str(folder / "mean.petra"), "--out", str(folder / "b")],
                         ["--card-only", str(folder / "mean.card"), "--out", str(folder / "c")]):
                with self.subTest(argv=argv[:2]):
                    with self.assertRaises(SystemExit) as stopped:
                        raise SystemExit(export.main(argv))
                    self.assertEqual(stopped.exception.code, 3)
                    self.assertFalse((Path(argv[-1]) / "card.json").exists(), "and no card.json is written")


class ReasonsKeepTheirRoom(unittest.TestCase):
    @KERNEL
    def test_a_long_reason_of_a_deck_costs_the_kernel_nothing(self):
        """A reason of 700,000 characters, each printed in six bytes, on a line that 3,000 parts are excused from. The kernel
        cut the reason again for the cell of each part: 41 processor seconds. It is cut once, where the deck is read."""
        blank = {"type": "t", "what": "w", "fields": []}
        line = {"type": "t", "mechanism": "m", "what": "w", "anchor": {"standard": "s", "clause": "1"}, "unless": {"why": "x" + "\u007f" * 700_000, "loads": []}}
        deck = {"format": "petra-rules/0", "name": "made-up", "rows": [], "types": [blank], "grid": [line], "rules": []}
        files = with_rules(deck, empty_card(), [{"name": f"p{i}", "type": "t", "lines": []} for i in range(3_000)])
        said, seconds, _ = measured(files)
        self.assertLess(seconds, PROCESSOR_SECONDS / 3)
        self.assertEqual((said["findings"], said["counts"]["not_applicable"]), ([], 3_000))
        self.assertTrue(said["cells"][0]["reason"].endswith("more characters)"))

    def test_a_reason_is_cut_once_and_both_readers_print_the_same(self):
        """The kernel cut a deck's reason where it read the deck and again in the cell, so it printed less of a long one
        than the grid did. Each ground gives the cell the reason as it was cut once."""
        why = "x" * 300
        for unless in ({"why": why, "loads": ["pull"]}, {"why": why, "least": ["pull", "0 N"]}, {"why": why, "with": ["hoist.span"]},
                       {"why": why, "when": ["is", "grade", "a"]}):
            with self.subTest(unless=unless):
                keys = ({**key("grade", "a", "b"), "signed": True},) if "when" in unless else ()
                text = design(part("hoist", "h", span="5 mm", **({"grade": "a"} if keys else {})))
                rules = [rule("pull", "hoist", "hoist.span", le=[["q", "1", "N"], ["load", "pull"]])] if "least" in unless else []
                found, _, said = cells(self, excused(unless, keys=keys, rules=rules), text, HEAD + (load("day", "h pull in [2 N, 5 N]") if rules else ""))
                self.assertEqual(found["h", "hoist.other", ""], "not_applicable")
                self.assertEqual(reason(said, "hoist.other"), grid._clip(why))
                self.assertTrue(grid._clip(why).endswith("... (100 more characters)"))

    @KERNEL
    def test_the_reasons_of_excused_lines_take_no_room_from_a_refutation(self):
        """2,700 parts, each excused from a line with a reason of 199 bytes, and the last of them refuted by a rule that
        requires. The reasons of the excused cells are past half a million bytes between them, and the reason of the
        refuted cell, which says why the design fails, is still printed."""
        why = "a" * 199
        deck = made_up([kind("hoist", {**key("grade", "a", "b"), "chosen": WHY})],
                       [asks("hoist.grade", "hoist"), asks("hoist.other", "hoist", unless={"why": why, "loads": []})],
                       [rule("grade-a", "hoist", "hoist.grade", requires=["is", "grade", "a"])], signs=False)
        parts = [part("hoist", f"h{i}", grade="a") for i in range(2_699)] + [part("hoist", "last", grade="b")]
        found, verdict, said = cells(self, deck, design(*parts), states=False)
        self.assertEqual(verdict, "FAIL")
        refuted = [c for c in said["cells"] if c["state"] == "refuted"]
        self.assertEqual([c["reason"] for c in refuted], ["the part is not what the rule requires: grade is b"])
        excused = [c.get("reason") for c in said["cells"] if c["state"] == "not_applicable"]
        self.assertEqual((excused[0], excused[-1]), (why, "past what the verdict prints of reasons"))

    @KERNEL
    def test_no_other_reason_takes_the_room_of_a_refutation(self):
        """The sixteenth review: 2,700 parts with names of 64 bytes, each with a line answered with a line that is open. The
        reasons of the open cells are past half a million bytes between them, and they took the room of the one reason that
        says why the design fails. So did the reason of a proved cell that reads nothing, on a design of more parts. A
        refuted cell's reason has room of its own."""
        line, other = "m" * 64, "n" * 64
        deck = made_up([kind("hoist", {**key("grade", "a", "b"), "chosen": WHY})],
                       [asks(line, "hoist"), asks(other, "hoist", unless={"why": "y" * 199, "with": [line]}), asks("hoist.grade", "hoist")],
                       [rule("grade-a", "hoist", "hoist.grade", requires=["is", "grade", "a"])], signs=False)
        names = [f"h{i:04d}" + "x" * 59 for i in range(2_700)]
        parts = [{"name": name, "type": "hoist", "lines": [{"field": "grade", "args": [{"word": "b" if name == names[-1] else "a"}]}]} for name in names]
        said, _, _ = measured(with_rules(deck, empty_card(), parts))
        self.assertEqual((said["verdict"], said["findings"]), ("FAIL", []))
        self.assertEqual([c["reason"] for c in said["cells"] if c["state"] == "refuted"], ["the part is not what the rule requires: grade is b"])
        self.assertEqual([c["reason"] for c in said["cells"] if c["state"] == "open"][-1], "past what the verdict prints of reasons", "the room of the other reasons did run out")

    @KERNEL
    def test_nor_do_the_reasons_of_proved_cells_that_read_nothing(self):
        """The other form the review found: 3,500 parts, each with a proved cell of numbers alone, which says in 93 bytes that
        it reads nothing, and a rule that requires, which the last part breaks."""
        deck = made_up([kind("hoist", {**key("grade", "a", "b"), "chosen": WHY})], [asks("hoist.grade", "hoist"), asks("hoist.fixed", "hoist")],
                       [rule("grade-a", "hoist", "hoist.grade", requires=["is", "grade", "a"]),
                        rule("fixed", "hoist", "hoist.fixed", le=[["q", "1", "mm"], ["q", "2", "mm"]])], signs=False)
        parts = [{"name": f"h{i}", "type": "hoist", "lines": [{"field": "grade", "args": [{"word": "b" if i == 3_499 else "a"}]}]} for i in range(3_500)]
        hints = [{"subject": f"h{i}", "mechanism": "hoist.fixed", "entry": "fixed", "state": "proved", "partition": "leaf"} for i in range(3_500)]
        said, _, _ = measured(with_rules(deck, empty_card(), parts, hints))
        self.assertEqual((said["verdict"], said["findings"]), ("FAIL", []))
        self.assertEqual([c["reason"] for c in said["cells"] if c["state"] == "refuted"], ["the part is not what the rule requires: grade is b"])
        self.assertEqual([c["reason"] for c in said["cells"] if c["state"] == "proved"][-1], "past what the verdict prints of reasons", "the room of the other reasons did run out")


if __name__ == "__main__":
    unittest.main()
