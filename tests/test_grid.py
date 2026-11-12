"""A design checked against a deck (petra/grid.py): each test is a card, a design and the
cells or the verdict they must get.

Most tests use STRIPS, a deck made up for them: it is no standard, and its numbers mean
nothing. It has a table read in bands, a table read at listed values, an equation with
two cases that jump, a rule with a range, and a grid with a line no rule answers. The last
classes use the deck that ships, petra/decks/aisc360.json, and the kernel when one is built.
"""
import copy
import importlib.util
import json
import math
import unittest
from pathlib import Path
from unittest import mock

import petra
from petra import deck as rows
from petra import export, grid, verify
from petra.files import read_pair

ROOT = Path(__file__).resolve().parents[1]
TEST = {"standard": "a deck made up for the tests", "clause": "1"}

STRIPS = {
    "format": "petra-rules/0", "name": "test-strips", "about": "Made up for the tests. It is no standard.",
    "rows": [
        {"id": "test/limit", "anchor": TEST, "gives": {"name": "I", "dim": "current", "what": "the current a strip carries"},
         "takes": [{"name": "w", "dim": "length", "what": "its width", "range": ["0.5 mm", "5 mm"]}],
         "table": {"down": {"by": "w", "bands": [["0 mm", "1 mm"], ["1 mm", "2 mm"], ["2 mm", None]], "closed": "upper"},
                   "unit": "A", "cells": ["1", "2", "3"], "rises": ["w"]}},
        {"id": "test/derate", "anchor": TEST, "gives": {"name": "k", "dim": "dimensionless", "what": "the share of it a warm strip carries"},
         "takes": [{"name": "T", "dim": "temperature", "what": "its temperature", "range": ["0 degC", "100 degC"]}],
         "cases": [{"when": ["le", "T", ["q", "40", "degC"]], "is": "1"}, {"when": ["gt", "T", ["q", "40", "degC"]], "is": "0.5"}],
         "jumps": [{"cases": [1, 2], "why": "made up"}]},
        {"id": "test/drill", "anchor": TEST, "gives": {"name": "dh", "dim": "length", "what": "the hole a screw needs"},
         "takes": [{"name": "d", "dim": "length", "what": "the screw's diameter", "range": ["3 mm", "4 mm"]},
                   {"name": "fit", "one_of": ["close", "free"], "what": "the fit"}],
         "table": {"down": {"by": "d", "at": ["3 mm", "4 mm"]}, "across": {"by": "fit"}, "unit": "mm", "cells": [["3.2", "3.6"], ["4.3", None]]}},
    ],
    "types": [
        {"type": "pad", "what": "a pad a strip ends on", "fields": [{"name": "area", "dim": "area", "what": "its area"}]},
        {"type": "strip", "what": "a strip between two pads",
         "fields": [
             {"name": "width", "dim": "length", "what": "its width"},
             {"name": "T", "dim": "temperature", "signed": True, "what": "its temperature"},
             {"name": "gap", "dim": "length", "signed": True, "what": "the gap under it"},
             {"name": "screw", "dim": "length", "what": "the diameter of its screw"},
             {"name": "hole", "dim": "length", "what": "the diameter of its hole"},
             {"name": "fit", "one_of": ["close", "free"], "what": "the fit of the screw"},
             {"name": "turns", "dim": "dimensionless", "whole": True, "least": "1", "what": "how many strips lie side by side"},
             {"name": "lands", "type": "pad", "as": ["near", "far"], "what": "its two pads"}],
         "loads": [{"name": "current", "dim": "current", "least": "0 A", "what": "the current through it"}]},
    ],
    "grid": [
        {"type": "strip", "mechanism": "strip.heat", "what": "overheating", "anchor": TEST},
        {"type": "strip", "mechanism": "strip.hole", "what": "a hole too small for the screw", "anchor": TEST},
        {"type": "strip", "mechanism": "strip.bow", "what": "bowing over the gap", "anchor": TEST},
        {"type": "strip", "mechanism": "strip.creep", "what": "creep", "anchor": TEST},
        {"type": "strip", "mechanism": "strip.spark", "what": "a spark across a loose screw", "anchor": TEST,
         "unless": {"when": ["is", "fit", "close"], "why": "a close fit leaves no room for one"}},
        {"type": "strip", "mechanism": "strip.tide", "what": "the tide", "anchor": TEST, "unless": {"why": "a strip is dry"}},
    ],
    "rules": [
        {"id": "test/heat", "type": "strip", "mechanism": "strip.heat", "anchor": TEST, "says": "the current is at most what the strips carry warm",
         "where": [{"le": [["add", "near.area", "far.area"], ["q", "120", "mm2"]], "why": "the pads are at most 120 mm2 together"}],
         "le": [["load", "current"], ["mul", "turns", ["row", "test/limit", {"w": "width"}], ["row", "test/derate", {"T": "T"}]]]},
        {"id": "test/hole", "type": "strip", "mechanism": "strip.hole", "anchor": TEST, "says": "the hole is at least the screw's",
         "le": [["row", "test/drill", {"d": "screw", "fit": "fit"}], "hole"]},
        {"id": "test/bow", "type": "strip", "mechanism": "strip.bow", "anchor": TEST, "says": "the gap times what is left of 4 mm is at most 4.2 mm2",
         "le": [["mul", "gap", ["sub", ["q", "4", "mm"], "gap"]], ["q", "4.2", "mm2"]]},
        {"id": "test/spark", "type": "strip", "mechanism": "strip.spark", "anchor": TEST, "says": "the hole is at least 0.1 mm over the screw",
         "when": ["is", "fit", "free"], "le": [["add", "screw", ["q", "0.1", "mm"]], "hole"]},
    ],
}

DESIGN = """petra 0

pad p1 {
  area 50 mm2
}

pad p2 {
  area 50 mm2
}

strip s {
  width 1 mm
  T given s.T
  gap given s.gap
  screw 3 mm
  hole 3.2 mm
  fit close
  turns 2
  lands p1 p2
}
"""

CARD = """petra 0

card "strips" {
  owner "t@example.org"
}

given s.T in [20 degC, 30 degC] signed "t@example.org" source "test"
given s.gap in [0.5 mm, 0.6 mm] signed "t@example.org" source "test"

load run {
  on s current in [0 A, 2 A]
  signed "t@example.org" source "test"
}

waive strip.creep on s by "t@example.org" reason "it is a test"
"""


def deck(edit=lambda body: None) -> grid.Deck:
    body = copy.deepcopy(STRIPS)
    edit(body)
    return grid.read_deck(json.dumps(body))


def checked(design=DESIGN, card=CARD, rules=None, swap=(), card_swap=()) -> dict:
    """petra.check of the texts against STRIPS, each after its replacements, with no kernel."""
    for old, new in swap:
        assert old in design, old
        design = design.replace(old, new)
    for old, new in card_swap:
        assert old in card, old
        card = card.replace(old, new)
    with mock.patch.object(grid, "decks", lambda: (rules or deck(),)), mock.patch.object(verify, "binary", lambda: None):
        return petra.check(card, design, path="strips.petra", repair=False)


def cell(result: dict, mechanism: str, entry: str | None = None) -> dict:
    found = [c for c in result["cells"] if c["mechanism"] == mechanism and entry in (None, c["entry"])]
    assert len(found) == 1, (mechanism, entry, [c["entry"] for c in found], result.get("error"))
    return found[0]


class Cells(unittest.TestCase):
    def test_every_mechanism_of_the_grid_gets_a_cell_and_the_verdict_follows(self):
        result = checked()
        self.assertEqual(result["status"], "PASS_WAIVED")
        self.assertEqual(result["counts"], {"proved": 4, "refuted": 0, "not_applicable": 2, "waived": 1, "open": 0})
        self.assertEqual({c["mechanism"] for c in result["cells"]}, {a["mechanism"] for a in STRIPS["grid"]})
        self.assertEqual(cell(result, "strip.tide")["why"], "a strip is dry")
        self.assertEqual(cell(result, "strip.creep")["state"], "waived")
        self.assertIn("it is a test", cell(result, "strip.creep")["why"])

    def test_a_mechanism_with_no_rule_is_open_and_the_design_cannot_pass(self):
        result = checked(card_swap=[('waive strip.creep on s by "t@example.org" reason "it is a test"\n', "")])
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(cell(result, "strip.creep")["state"], "open")
        self.assertIn("no rule", cell(result, "strip.creep")["why"])

    def test_a_point_on_the_end_of_a_band_reads_the_band_that_holds_it(self):
        self.assertAlmostEqual(cell(checked(), "strip.heat", "heat/run")["ratio"], 1.0, msg="1 mm is in the band up to 1 mm: 2 strips carry 2 A")
        over = checked(card_swap=[("[0 A, 2 A]", "[0 A, 2.01 A]")])
        self.assertEqual((over["status"], cell(over, "strip.heat", "heat/run")["state"]), ("FAIL", "refuted"))
        wider = checked(swap=[("width 1 mm", "width 1.001 mm")], card_swap=[("[0 A, 2 A]", "[0 A, 4 A]")])
        self.assertAlmostEqual(cell(wider, "strip.heat", "heat/run")["ratio"], 1.0, msg="just over 1 mm is in the next band")

    def test_a_range_that_straddles_two_cases_must_satisfy_both(self):
        warm = [("[20 degC, 30 degC]", "[30 degC, 50 degC]")]
        half = checked(card_swap=warm + [("[0 A, 2 A]", "[0 A, 1 A]")])
        self.assertEqual(cell(half, "strip.heat", "heat/run")["state"], "proved")
        full = checked(card_swap=warm + [("[0 A, 2 A]", "[0 A, 1.5 A]")])
        self.assertEqual(cell(full, "strip.heat", "heat/run")["state"], "refuted", "at 50 degC the strips carry 1 A")
        edge = checked(card_swap=[("[20 degC, 30 degC]", "[30 degC, 40 degC]")])
        self.assertEqual(cell(edge, "strip.heat", "heat/run")["state"], "proved", "40 degC is in the first case")

    def test_a_table_read_at_listed_values_gives_nothing_between_them(self):
        self.assertAlmostEqual(cell(checked(), "strip.hole")["ratio"], 1.0)
        between = cell(checked(swap=[("screw 3 mm", "screw 3.5 mm")]), "strip.hole")
        self.assertEqual(between["state"], "open")
        self.assertIn("test/drill gives no value at what s has", between["why"])
        empty = cell(checked(swap=[("screw 3 mm", "screw 4 mm"), ("fit close", "fit free"), ("hole 3.2 mm", "hole 5 mm")]), "strip.hole")
        self.assertEqual((empty["state"], empty["why"]), ("open", "test/drill gives no value at what s has: no case of the pick holds somewhere in the box"))
        small = checked(swap=[("hole 3.2 mm", "hole 3.1 mm")])
        self.assertEqual((small["status"], cell(small, "strip.hole")["state"]), ("FAIL", "refuted"))

    def test_outside_a_rules_range_the_cell_is_open_and_never_refuted(self):
        result = checked(swap=[("area 50 mm2\n}\n\npad p2", "area 150 mm2\n}\n\npad p2")], card_swap=[("[0 A, 2 A]", "[0 A, 9 A]")])
        heat = cell(result, "strip.heat")
        self.assertEqual(heat["state"], "open")
        self.assertIn("the pads are at most 120 mm2 together", heat["why"])
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(cell(checked(), "strip.heat", "heat/run/where")["state"], "proved", "inside the range, a cell says so")

    def test_a_rule_that_reads_a_load_has_a_cell_for_each_case_and_is_open_with_none(self):
        two = checked(card_swap=[("waive strip.creep", 'load surge {\n  on s current in [0 A, 3 A]\n  signed "t@example.org" source "test"\n}\n\nwaive strip.creep')])
        self.assertEqual((cell(two, "strip.heat", "heat/run")["state"], cell(two, "strip.heat", "heat/surge")["state"]), ("proved", "refuted"))
        none = checked(card_swap=[('load run {\n  on s current in [0 A, 2 A]\n  signed "t@example.org" source "test"\n}\n', "")])
        self.assertEqual(cell(none, "strip.heat")["state"], "open")
        self.assertIn("the card puts no current on s", cell(none, "strip.heat")["why"])

    def test_what_a_part_is_decides_which_rule_answers_and_whether_one_must(self):
        self.assertEqual(cell(checked(), "strip.spark")["state"], "not_applicable")
        free = checked(swap=[("fit close", "fit free"), ("hole 3.2 mm", "hole 3.6 mm")])
        self.assertEqual(cell(free, "strip.spark")["state"], "proved")
        idle = checked(swap=[("fit close", "fit free"), ("hole 3.2 mm", "hole 3.6 mm")],
                       card_swap=[('load run {\n  on s current in [0 A, 2 A]\n  signed "t@example.org" source "test"\n}\n', "")])
        self.assertEqual(cell(idle, "strip.spark")["state"], "proved", "the rule reads no load, so it answers the same with no load case")
        other = deck(lambda body: body["rules"][3].update(when=["is", "fit", "close"]))
        unanswered = checked(swap=[("fit close", "fit free"), ("hole 3.2 mm", "hole 3.6 mm")], rules=other)
        self.assertEqual(cell(unanswered, "strip.spark")["state"], "open")
        self.assertIn("no rule for it on a part like this one", cell(unanswered, "strip.spark")["why"])

    def test_a_deck_that_asks_whether_a_load_is_there_is_refused(self):
        """`loaded` held when some load case put the load on the part, so one case could switch
        a rule or a line off under every other (the fifth review). A condition is over keys."""
        for edit in (lambda body: body["rules"][3].update(when=["loaded", "current"]),
                     lambda body: body["grid"][4]["unless"].update(when=["or", ["is", "fit", "close"], ["not", ["loaded", "current"]]])):
            with self.assertRaises(grid.DeckError) as refused:
                deck(edit)
            self.assertIn(grid.LOADED, str(refused.exception))

    def test_a_value_that_no_rule_reads_is_an_open_cell(self):
        stray = checked(swap=[("strip s {", "pad p3 {\n  area 1 mm2\n}\n\nstrip s {")])
        self.assertEqual(stray["status"], "UNKNOWN", "a pad that no strip ends on would pass at any area")
        self.assertEqual((cell(stray, "unread")["subject"], cell(stray, "unread")["entry"], cell(stray, "unread")["state"]), ("p3", "area", "open"))
        self.assertEqual([c for c in checked()["cells"] if c["mechanism"] == "unread"], [])

    def test_a_proof_may_need_the_ranges_split(self):
        wide = checked(card_swap=[("[0.5 mm, 0.6 mm]", "[1 mm, 3 mm]")])
        bow = cell(wide, "strip.bow")
        self.assertEqual(bow["state"], "proved", "gap (4 mm - gap) peaks at 4 mm2, under 4.2, and one enclosure over [1, 3] mm reaches 9")
        with mock.patch.object(grid, "decks", lambda: (deck(),)):
            design = petra.lang.parse_design(CARD.replace("[0.5 mm, 0.6 mm]", "[1 mm, 3 mm]"), DESIGN, "strips.petra", petra.registry.build_registry())
            report, files = grid.check(design, grid.owner(design))
        partition = next(c for c in json.loads(files["proofs"])["cells"] if c["mechanism"] == "strip.bow")["partition"]
        self.assertIsInstance(partition, dict, "it is split")
        peak = checked(card_swap=[("[0.5 mm, 0.6 mm]", "[1 mm, 3 mm]")], rules=deck(lambda b: b["rules"][2]["le"].__setitem__(1, ["q", "3.9", "mm2"])))
        self.assertEqual(cell(peak, "strip.bow")["state"], "refuted", "the middle of the range is tried, and there it is 4 mm2")


class Refused(unittest.TestCase):
    def refused(self, says: str, **how) -> None:
        result = checked(**how)
        self.assertEqual(result["status"], "INPUT_ERROR", result)
        self.assertIn(says, result["error"])

    def test_a_design_cannot_state_what_only_the_card_may(self):
        self.refused("s.T is for the card to state", swap=[("T given s.T", "T 25 degC")], card_swap=[('given s.T in [20 degC, 30 degC] signed "t@example.org" source "test"\n', "")])

    def test_a_part_reads_only_the_bound_the_card_gives_for_that_field(self):
        other = 'given s.T in [20 degC, 30 degC] signed "t@example.org" source "test"\n'
        self.refused("s.T reads `given cool`, and a part reads only the bound the card gives for it: `given s.T`",
                     swap=[("T given s.T", "T given cool")], card_swap=[(other, other.replace("s.T", "cool"))])
        two = [("gap given s.gap", "gap given s.width"), ("width 1 mm", "width given s.gap")]
        more = '[0.5 mm, 0.6 mm] signed "t@example.org" source "test"\ngiven s.width in [1 mm, 1 mm]'
        self.refused("s.width reads `given s.gap`", swap=two, card_swap=[("[0.5 mm, 0.6 mm]", more)])

    def test_a_part_has_each_line_of_its_type_once_and_no_other(self):
        self.refused("s lacks hole", swap=[("  hole 3.2 mm\n", "")])
        self.refused("s.colour is not a line of a strip", swap=[("  fit close\n", "  fit close\n  colour red\n")])
        self.refused("s.hole is given twice", swap=[("  fit close\n", "  fit close\n  hole 3.3 mm\n")])

    def test_a_value_has_the_dimension_and_the_domain_of_its_field(self):
        self.refused("s.width is a length, not a current", swap=[("width 1 mm", "width 1 A")])
        self.refused("s.fit is one of: close, free", swap=[("fit close", "fit snug")])
        self.refused("s.turns is a count: a whole number", swap=[("turns 2", "turns 2.5")])
        self.refused("s.lands names 2 different pad parts", swap=[("lands p1 p2", "lands p1 s")])
        self.refused("s.lands names 2 different pad parts", swap=[("lands p1 p2", "lands p1 p1")])

    def test_a_part_is_joined_by_one_other(self):
        second = DESIGN.split("strip s {")[1].replace("given s.", "given r.")
        more = 'given r.T in [20 degC, 30 degC] signed "t@example.org" source "test"\ngiven r.gap in [0.5 mm, 0.6 mm] signed "t@example.org" source "test"\n\nload run'
        self.refused("p1 is joined by s and r", design=DESIGN + "\nstrip r {" + second, card_swap=[("load run", more)])

    def test_a_load_is_one_the_type_takes_and_no_less_than_its_least(self):
        self.refused("a strip takes: current", card_swap=[("on s current in [0 A, 2 A]", "on s force in [0 N, 2 N]")])
        self.refused("is at least 0 in SI units", card_swap=[("[0 A, 2 A]", "[-1 A, 2 A]")])
        self.refused("a pad takes: no load", card_swap=[("on s current", "on p1 current")])

    def test_a_waiver_names_a_mechanism_the_grid_asks_of_the_part(self):
        self.refused("the deck asks of a pad: nothing", card_swap=[("waive strip.creep on s", "waive strip.creep on p1")])

    def test_what_a_deck_does_not_read_yet_is_refused_and_not_ignored(self):
        self.refused("states a claim, which a deck does not read yet", card_swap=[("waive strip.creep", "claim heat: s.current <= 2 A\n\nwaive strip.creep")])

    def test_a_design_of_a_deck_and_of_the_models_is_refused(self):
        mixed = DESIGN + "\njoint j {\n  bolt bolt.M12_A4_70 count 1\n  plate aluminium.6061_T6 thickness 10 mm\n  plate aluminium.6061_T6 thickness 10 mm\n}\n"
        self.refused("a design is checked against one deck", design=mixed)


UNKNOWN_KEYS = {
    "the anchor of a row": (lambda b: b["rows"][0].__setitem__("anchor", {**TEST, "claus": "2"}), "claus"),
    "what a row gives": (lambda b: b["rows"][0]["gives"].update(unit="A"), "unit"),
    "an input of a row": (lambda b: b["rows"][0]["takes"][0].update(rnge=["1 mm", "2 mm"]), "rnge"),
    "a key a row takes": (lambda b: b["rows"][2]["takes"][1].update(least="1"), "least"),
    "a case": (lambda b: b["rows"][1]["cases"][0].update(then="1"), "then"),
    "a jump": (lambda b: b["rows"][1]["jumps"][0].update(because="made up"), "because"),
    "a table": (lambda b: b["rows"][0]["table"].update(units="A"), "units"),
    "a side with bands": (lambda b: b["rows"][0]["table"]["down"].update(close="lower"), "close"),
    "a side read at listed values, which has no bands to close": (lambda b: b["rows"][2]["table"]["down"].update(closed="upper"), "closed"),
    "a side that reads a key": (lambda b: b["rows"][2]["table"]["across"].update(closed="upper"), "closed"),
    "a type": (lambda b: b["types"][0].update(note="made up"), "note"),
    "a field": (lambda b: b["types"][0]["fields"][0].update(lest="1 mm2"), "lest"),
    "a key field, which has no least value": (lambda b: b["types"][1]["fields"][5].update(least="1"), "least"),
    "a field that joins parts, which is no count": (lambda b: b["types"][1]["fields"][7].update(whole=True), "whole"),
    "a quantity, which joins no part": (lambda b: b["types"][1]["fields"][0].update({"as": ["a"]}), "as"),
    "a load": (lambda b: b["types"][1]["loads"][0].update(signed=True), "signed"),
    "a line of the grid": (lambda b: b["grid"][0].update(note="made up"), "note"),
    "the anchor of a line of the grid": (lambda b: b["grid"][0].__setitem__("anchor", {**TEST, "note": "made up"}), "note"),
    "unless": (lambda b: b["grid"][4]["unless"].update(wen=["is", "fit", "free"]), "wen"),
    "a rule": (lambda b: b["rules"][0].update(unless="made up"), "unless"),
    "the anchor of a rule": (lambda b: b["rules"][0].__setitem__("anchor", {**TEST, "pages": "12"}), "pages"),
    "an item of where": (lambda b: b["rules"][0]["where"][0].update(because="made up"), "because"),
    "the deck": (lambda b: b.update(notes="made up"), "notes"),
}
"""Each place of a deck where a key may stand, with a key the deck does not have there. The
grid and the kernel refuse every one, and name the key (tests/test_kernel_grid.py)."""


class Decks(unittest.TestCase):
    def wrong(self, says: str, edit) -> None:
        with self.assertRaises(grid.DeckError) as ctx:
            deck(edit)
        self.assertIn(says, str(ctx.exception))

    def test_a_key_the_deck_does_not_know_is_refused_wherever_it_stands(self):
        """A key that was skipped would be a misspelled one read as left out: `close` for
        `closed` would leave a band closed at its upper end."""
        for what, (edit, key) in UNKNOWN_KEYS.items():
            with self.subTest(what=what):
                self.wrong(f"{key} is not a key here", edit)

    def test_an_anchor_names_its_standard_and_its_clause(self):
        for place in ("rows", "grid", "rules"):
            for anchor in ({"standard": "made up"}, {"clause": "1"}, {"standard": "", "clause": "1"}):
                with self.subTest(place=place, anchor=anchor), self.assertRaises(grid.DeckError):
                    deck(lambda b: b[place][0].__setitem__("anchor", anchor))

    def test_bands_are_in_order_and_none_lies_over_another(self):
        for bands in ([["1 mm", "2 mm"], ["0 mm", "1 mm"], ["2 mm", None]], [["0 mm", "1.5 mm"], ["1 mm", "2 mm"], ["2 mm", None]],
                      [["1 mm", "0 mm"], ["1 mm", "2 mm"], ["2 mm", None]]):
            with self.subTest(bands=bands):
                self.wrong("the bands of w are pairs, the lower end first, in order and none over another",
                           lambda b: b["rows"][0]["table"]["down"].__setitem__("bands", bands))

    def test_a_rule_binds_each_input_of_a_row_to_its_dimension(self):
        self.wrong("w is a length, and the rule binds a temperature", lambda b: b["rules"][0]["le"][1][2][2].__setitem__("w", "T"))
        self.wrong("test/limit takes w", lambda b: b["rules"][0]["le"][1][2].__setitem__(2, {}))
        self.wrong("`le` compares a current with a length", lambda b: b["rules"][0]["le"].__setitem__(1, "width"))
        self.wrong("is not a row of the deck", lambda b: b["rules"][1]["le"][0].__setitem__(1, "test/none"))

    def test_a_key_is_bound_to_names_the_row_has(self):
        self.wrong("fit has names the row lacks: snug", lambda b: b["types"][1]["fields"][5].__setitem__("one_of", ["close", "snug"]))
        deck(lambda b: b["rules"][1]["le"][0][2].__setitem__("fit", ["key", "free"]))
        deck(lambda b: b["rules"][1]["le"][0][2].__setitem__("fit", ["by", "fit", {"close": "free", "free": "close"}]))
        self.wrong("`by` gives one of the row's names for each name of fit", lambda b: b["rules"][1]["le"][0][2].__setitem__("fit", ["by", "fit", {"close": "free"}]))

    def test_a_rule_answers_a_line_of_the_grid_that_can_arise(self):
        self.wrong("the grid does not ask strip.melt of strip", lambda b: b["rules"][0].__setitem__("mechanism", "strip.melt"))
        self.wrong("the grid does not ask strip.tide of strip, or says it never arises", lambda b: b["rules"][0].__setitem__("mechanism", "strip.tide"))
        self.wrong("the grid does not ask strip.tide of strip, or says it never arises",
                   lambda b: [b["grid"][5]["unless"].__setitem__("why", ""), b["rules"][0].__setitem__("mechanism", "strip.tide")])
        self.wrong("two rules have one name", lambda b: b["rules"].append(b["rules"][0]))

    def test_a_row_of_a_deck_has_no_dimension_error(self):
        self.wrong("test/derate", lambda b: b["rows"][1]["cases"][0].__setitem__("is", ["q", "1", "mm"]))

    def test_a_name_is_one_the_language_writes_and_a_number_has_no_exponent(self):
        # A field named `load current` would read as the load, and `near.area` as a field of a joined part.
        self.wrong("it has a name of letters, digits and _", lambda b: b["types"][0]["fields"][0].__setitem__("name", "load current"))
        self.wrong("it has a name of letters, digits and _", lambda b: b["types"][1]["fields"][0].__setitem__("name", "near.area"))
        self.wrong("`as` names each part once, in letters, digits and _", lambda b: b["types"][1]["fields"][7].__setitem__("as", ["near", "@0"]))
        self.wrong("no name of letters, digits and _", lambda b: b["rules"][2].__setitem__("let", {"load current": "gap"}))
        self.wrong("'4e0' is not a number", lambda b: b["rules"][2]["le"][0].__setitem__(1, ["sub", "4e0", "gap"]))
        self.wrong("'1_0' is not a number", lambda b: b["rules"][2]["le"][0].__setitem__(1, ["pow", "gap", "1_0"]))

    def test_what_a_field_is_is_a_text(self):
        """The kernel refuses a field whose `what` is true, a number or empty, and so does the
        grid: bench/kernel_grid.py found a damaged deck that only the kernel refused."""
        for value in (True, 1, ["its width"], ""):
            with self.subTest(value=value):
                self.wrong("`what`, a text, and one of `dim`, `one_of` and `type`", lambda b: b["types"][0]["fields"][0].__setitem__("what", value))

    def test_a_line_of_the_grid_names_a_type_of_the_deck(self):
        self.wrong("grid strip.creep: a line has a type of the deck", lambda b: b["grid"][3].__setitem__("type", "strap"))
        self.wrong("not a deck (KeyError: 'why')", lambda b: b["grid"][5].__setitem__("unless", {}))


def formalizer(name: str) -> dict:
    return {r["id"]: r for r in json.loads((ROOT / "bench" / "formalizer" / name).read_text(encoding="utf-8"))["rows"]}


LAST_LINES = {
    "aisc360-22/table-J3.3": (("aisc360-22/table-J3.3-large-standard", "aisc360-22/table-J3.3-large-oversize"), ("9/8", "5/4", "11/8", "3/2"),
                              "J3.3, with its last line, d + 1/8 and d + 5/16 for 1 1/8 inch and more, taken at 1 1/8, 1 1/4, 1 3/8 and 1 1/2 inch"),
    "aisc360-22/table-J3.4": (("aisc360-22/table-J3.4-large",), ("11/8", "3/2"), "J3.4, with its last line, 1 1/4 d over 1 1/4 inch, taken at 1 3/8 and 1 1/2 inch")}
"""The two tables whose last line the standard prints as a formula of the bolt's diameter: the
formula's row for each column, the sizes past the printed ones it is taken at, and the anchor.
A rule reads a table at the bolt's size and cannot choose a formula by it, so the deck lists
what the formula gives at each size of bolt to 1 1/2 inch, the largest the deck's other rows
take. Each formula is a row of the deck of its own, which two transcribers agreed on."""


def with_last_line(transcribed: dict, deck_rows: dict) -> dict:
    """The table as the deck holds it: the transcription with a line for each size of
    LAST_LINES, whose cells are what the formula rows give there, in inch."""
    formulas, sizes, anchor = LAST_LINES[transcribed["id"]]
    row = copy.deepcopy(transcribed)
    inch = rows.quantity("1 inch", "inch")[0]
    for size in sizes:
        line = [export.number(rows.value(rows.read(deck_rows[f]), {"d": rows.quantity(f"{size} inch", "d")[0]}) / inch) for f in formulas]
        row["table"]["down"]["at"].append(f"{size} inch")
        row["table"]["cells"].append(line if "across" in row["table"] else line[0])
    row["takes"][0]["range"][1] = f"{sizes[-1]} inch"
    row["anchor"] = {**row["anchor"], "table": anchor}
    return row


class Shipped(unittest.TestCase):
    """The deck of AISC 360-22 rows and the three designs under examples/deck."""

    def test_every_row_is_one_two_transcribers_agreed_on_and_passes_the_acceptance_check(self):
        spec = importlib.util.spec_from_file_location("formalizer_run", ROOT / "bench" / "formalizer" / "run.py")
        run = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(run)
        first = formalizer("a.json") | formalizer("a2.json") | formalizer("a3.json")
        second = formalizer("b.json") | formalizer("b2.json") | formalizer("b3.json")
        examples = {}
        for name in ("examples.json", "examples2.json", "examples3.json"):
            examples |= json.loads((ROOT / "bench" / "formalizer" / name).read_text(encoding="utf-8"))["examples"]
        body = json.loads((grid.DECKS / "aisc360.json").read_text(encoding="utf-8"))
        self.assertEqual(len(body["rows"]), 32, "the 18 of the first two runs and the 14 of the third")
        deck_rows = {r["id"]: r for r in body["rows"]}
        for written in body["rows"]:
            with self.subTest(row=written["id"]):
                transcribed = first[written["id"]]
                if written["id"] in LAST_LINES:
                    self.assertEqual(written, with_last_line(transcribed, deck_rows), "the transcription with the lines its last line gives")
                    self.assertEqual(rows.shape(rows.read(written)).outcome, "pass", "the lines run on from the printed ones")
                else:
                    self.assertEqual(written, transcribed, "the row is the transcription, unedited")
                row = rows.read(transcribed)
                found, unread = run.worked(row, examples.get(row.id, []))
                self.assertEqual(unread, [])
                checks = rows.accept(row, found, rows.read(second[row.id]))
                self.assertEqual([c.name for c in checks if c.outcome == "fail"], [])
                self.assertEqual(checks[-1].outcome, "pass", "a second transcription agrees")

    def check(self, name: str) -> dict:
        path = ROOT / "examples" / "deck" / f"{name}.petra"
        with mock.patch.object(verify, "binary", lambda: None):
            return petra.check(*read_pair(path), path=str(path), repair=False)

    NO_RULE = ["lap.tightening", "lap.hole_use", "lap.max_edge_distance", "lap.ply_flexure"]

    def test_the_lap_that_waives_nothing_is_unknown_with_its_rules_proved(self):
        result = self.check("lap_unknown")
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["counts"], {"proved": 12, "refuted": 0, "not_applicable": 4, "waived": 0, "open": 4})
        self.assertEqual([c["mechanism"] for c in result["cells"] if c["state"] == "open"], self.NO_RULE)
        self.assertEqual({c["why"] for c in result["cells"] if c["state"] == "open"}, {"the deck has no rule for it"})
        # Each ratio is worked out here from the clause, with the numbers of the design.
        # Three 3/4 inch Group 120 bolts with threads in the shear plane: 0.75 x 54 ksi x 0.4418 inch2 is 17.9 kip a bolt, the
        # shear strength Design Examples v16.0 prints for this bolt, and bearing and tearout on 3/8 inch A36 are above it.
        self.assertAlmostEqual(cell(result, "lap.strength", "lap-strength/gravity")["ratio"], 45 / (3 * 17.892), places=3)
        self.assertAlmostEqual(cell(result, "lap.ply_yield", "lap-ply-yield-a/gravity")["ratio"], 45 / (0.9 * 36 * 6 * 0.375), places=6)
        self.assertAlmostEqual(cell(result, "lap.end_distance")["ratio"], 1 / 1.5, places=6)
        self.assertAlmostEqual(cell(result, "lap.side_distance")["ratio"], 1 / 3, places=6)
        # J3.4: 2 2/3 diameters between centres, and one diameter clear between holes of 13/16 inch.
        self.assertAlmostEqual(cell(result, "lap.spacing", "lap-spacing-centres")["ratio"], (8 / 3 * 0.75) / 3, places=6)
        self.assertAlmostEqual(cell(result, "lap.spacing", "lap-spacing-clear")["ratio"], 0.75 / (3 - 13 / 16), places=6)
        # J3.6(a): 24 thicknesses of a painted plate, 9 inch, which is under 12 inch.
        self.assertAlmostEqual(cell(result, "lap.spread")["ratio"], 3 / (24 * 0.375), places=6)
        # J4.1(b) and B4.3b: the net section has one hole, taken 13/16 + 1/16 inch wide.
        self.assertAlmostEqual(cell(result, "lap.ply_rupture", "lap-ply-rupture-b/gravity")["ratio"], 45 / (0.75 * 58 * (6 - 7 / 8) * 0.375), places=6)
        # J4.3: 7.5 inch in shear, less 2.5 holes for the net, and 3 inch less half a hole in tension. Yielding of the gross shear area governs.
        block = 0.75 * (min(0.6 * 58 * (7.5 - 2.5 * 7 / 8) * 0.375, 0.6 * 36 * 7.5 * 0.375) + 58 * (3 - 7 / 16) * 0.375)
        self.assertAlmostEqual(block, 87.363, places=3)
        self.assertAlmostEqual(cell(result, "lap.block_shear", "lap-block-shear-a/gravity")["ratio"], 45 / block, places=6)

    def test_the_overloaded_lap_fails_and_the_waived_one_passes(self):
        failed = self.check("lap_fail")
        self.assertEqual((failed["status"], [c["mechanism"] for c in failed["cells"] if c["state"] == "refuted"]), ("FAIL", ["lap.strength"]))
        waived = self.check("lap_pass")
        self.assertEqual((waived["status"], waived["counts"]["waived"], waived["counts"]["open"]), ("PASS_WAIVED", 4, 0))
        self.assertEqual([c["mechanism"] for c in waived["cells"] if c["state"] == "waived"], self.NO_RULE, "the card waives the lines with no rule, and no line that has one")

    def variant(self, *swap: tuple[str, str], pull: str = "45 kip") -> dict:
        path = ROOT / "examples" / "deck" / "lap_unknown.petra"
        card, design = read_pair(path)
        for old, new in swap:
            assert old in design, old
            design = design.replace(old, new)
        assert "[0 kip, 45 kip]" in card
        with mock.patch.object(verify, "binary", lambda: None):
            return petra.check(card.replace("[0 kip, 45 kip]", f"[0 kip, {pull}]"), design, path=str(path), repair=False)

    def test_tearout_governs_a_short_end_and_the_table_refuses_it(self):
        short = self.variant(("end 1.5 inch", "end 0.75 inch"))
        self.assertEqual(cell(short, "lap.end_distance")["state"], "refuted", "Table J3.4 asks 1 inch of a 3/4 inch bolt")
        # lc = 0.75 - 13/32 inch, so an end bolt tears out at 1.2 x 0.34375 x 0.375 x 58 = 8.97 kip, under its shear strength of 23.86.
        capacity = 0.75 * (2 * min(23.856, 8.972) + 23.856)
        self.assertAlmostEqual(cell(short, "lap.strength", "lap-strength/gravity")["ratio"], 45 / capacity, places=3)

    def test_what_the_tables_do_not_list_is_open(self):
        odd = self.variant(("diameter 0.75 inch", "diameter 0.7 inch"))
        self.assertEqual({cell(odd, "lap.strength", "lap-strength/gravity")["state"], cell(odd, "lap.end_distance")["state"]}, {"open"})
        self.assertEqual(cell(odd, "lap.spacing", "lap-spacing-centres")["state"], "proved", "2 2/3 diameters is no table")
        self.assertEqual(self.variant(("count 3", "count 1"))["status"], "INPUT_ERROR", "the rule sums over two end bolts")

    def test_a_bolt_of_an_inch_and_an_eighth_is_read_on_the_last_line_of_each_table(self):
        """Table J3.3 lists holes for bolts to 1 inch and gives a formula, d + 1/8 for a standard hole, for 1 1/8 inch and
        more. A rule cannot choose between the two by the size of the bolt, so the deck's table lists what the formula gives
        at 1 1/8 inch, and the four lines that need a hole are answered. Until the eighth review they were open, and a waiver
        rested them: a lap whose bolts failed in shear passed (tests/test_kernel_attacks8.py)."""
        large = self.variant(("diameter 0.75 inch", "diameter 1.125 inch"), ("pitch 3 inch", "pitch 3.5 inch"), ("end 1.5 inch", "end 2 inch"))
        self.assertEqual([c["mechanism"] for c in large["cells"] if c["state"] == "open"], self.NO_RULE)
        self.assertEqual((large["status"], large["counts"]["refuted"]), ("UNKNOWN", 0))
        # J3.4: one diameter clear between holes of 1 1/8 + 1/8 inch.
        self.assertAlmostEqual(cell(large, "lap.spacing", "lap-spacing-clear")["ratio"], 1.125 / (3.5 - 1.25), places=6)
        # The end bolts tear out of 3/8 inch A36 at 0.75 x 1.2 x (2 - 1.25 / 2) inch, and the middle one shears at 0.75 x 54 ksi x pi / 4 x 1.125^2.
        capacity = 2 * 0.75 * 1.2 * (2 - 1.25 / 2) * 0.375 * 58 + 0.75 * 54 * math.pi / 4 * 1.125 ** 2
        self.assertAlmostEqual(cell(large, "lap.strength", "lap-strength/gravity")["ratio"], 45 / capacity, places=6)
        # Table J3.4 asks 1 1/2 inch of this bolt.
        self.assertAlmostEqual(cell(large, "lap.end_distance")["ratio"], 1.5 / 2, places=6)
        self.assertAlmostEqual(cell(large, "lap.side_distance")["ratio"], 1.5 / 3, places=6)
        # Past 1 1/4 inch Table J3.4 gives 1 1/4 d: 15/8 inch for a bolt of 1 1/2 inch.
        largest = self.variant(("diameter 0.75 inch", "diameter 1.5 inch"), ("pitch 3 inch", "pitch 4.5 inch"), ("end 1.5 inch", "end 2.5 inch"))
        self.assertAlmostEqual(cell(largest, "lap.end_distance")["ratio"], 1.875 / 2.5, places=6)
        self.assertAlmostEqual(cell(largest, "lap.spacing", "lap-spacing-clear")["ratio"], 1.5 / (4.5 - 1.625), places=6)

    def test_a_bolt_the_tables_do_not_list_leaves_six_lines_open_and_no_waiver_rests_them(self):
        """1 3/4 inch is past the sizes the tables list, so every rule that reads a hole or a least edge distance has no value to
        read. A card that waives those lines too leaves them open: the deck must cover the part."""
        six = ("lap.spacing", "lap.end_distance", "lap.side_distance", "lap.strength", "lap.ply_rupture", "lap.block_shear")
        card, design = read_pair(ROOT / "examples" / "deck" / "lap_pass.petra")
        for old, new in (("diameter 0.75 inch", "diameter 1.75 inch"), ("pitch 3 inch", "pitch 5 inch"), ("end 1.5 inch", "end 3 inch")):
            assert old in design, old
            design = design.replace(old, new)
        card += "".join(f'\nwaive {m} on splice by "t@example.org" reason "test"\n' for m in six)
        with mock.patch.object(verify, "binary", lambda: None):
            found = petra.check(card, design, path=str(ROOT / "examples" / "deck" / "lap_pass.petra"), repair=False)
        opened = [c for c in found["cells"] if c["state"] == "open"]
        self.assertEqual({c["mechanism"] for c in opened}, set(six))
        for c in opened:
            self.assertTrue(c["why"].startswith(grid.UNRESTED) and "gives no value at what splice has" in c["why"], c["why"])
        self.assertEqual(found["status"], "UNKNOWN")

    def test_each_limit_of_the_clauses_turns_where_the_clause_puts_it(self):
        """A lap on each side of a limit: the first holds, at the limit or just inside it, and the second fails."""
        def states(mechanism: str, entry: str | None, *laps: dict) -> list[str]:
            return [cell(found, mechanism, entry)["state"] for found in laps]

        turned = ["proved", "refuted"]
        # J3.4: 2 2/3 diameters of a 3/4 inch bolt are 2 inch.
        self.assertEqual(states("lap.spacing", "lap-spacing-centres", self.variant(("pitch 3 inch", "pitch 2 inch")), self.variant(("pitch 3 inch", "pitch 1.999 inch"))), turned)
        # Table J3.4: 1 inch from a 3/4 inch bolt to a side edge.
        self.assertEqual(states("lap.side_distance", None, self.variant(("side 3 inch", "side 1 inch")), self.variant(("side 3 inch", "side 0.999 inch"))), turned)
        # J3.6(a): 24 thicknesses of 3/8 inch, 9 inch. J3.6(b): 14 thicknesses, 5.25 inch.
        self.assertEqual(states("lap.spread", None, self.variant(("pitch 3 inch", "pitch 9 inch")), self.variant(("pitch 3 inch", "pitch 9.001 inch"))), turned)
        weathering = ("surface protected", "surface weathering")
        self.assertEqual(states("lap.spread", None, self.variant(weathering, ("pitch 3 inch", "pitch 5.25 inch")), self.variant(weathering, ("pitch 3 inch", "pitch 5.251 inch"))), turned)
        # J3.6: the caps of 12 inch and 7 inch, on plates of 3/4 inch, where 24 and 14 thicknesses are more.
        thick = ("thickness 0.375 inch", "thickness 0.75 inch")
        self.assertEqual(states("lap.spread", None, self.variant(thick, ("pitch 3 inch", "pitch 12 inch")), self.variant(thick, ("pitch 3 inch", "pitch 12.001 inch"))), turned)
        self.assertEqual(states("lap.spread", None, self.variant(thick, weathering, ("pitch 3 inch", "pitch 7 inch")),
                                self.variant(thick, weathering, ("pitch 3 inch", "pitch 7.001 inch"))), turned)
        # J4.1(b): the net section of a 6 inch plate ruptures at 0.75 x 58 x 5.125 x 0.375 = 83.602 kip.
        self.assertEqual(states("lap.ply_rupture", "lap-ply-rupture-a/gravity", self.variant(pull="83.6 kip"), self.variant(pull="83.61 kip")), turned)
        # J4.3: with the holes 1.25 inch from a side edge, a block tears out at 0.75 x (60.75 + 58 x 0.8125 x 0.375) = 58.816 kip.
        near = ("side 3 inch", "side 1.25 inch")
        self.assertEqual(states("lap.block_shear", "lap-block-shear-b/gravity", self.variant(near, pull="58.81 kip"), self.variant(near, pull="58.82 kip")), turned)

    def test_an_oversize_hole_adds_the_increment_of_table_j3_5_to_the_end_and_the_side(self):
        oversize = ("holes standard", "holes oversize")
        at = self.variant(oversize, ("end 1.5 inch", "end 1.0625 inch"), ("side 3 inch", "side 1.0625 inch"))
        self.assertEqual([(cell(at, m)["entry"], cell(at, m)["state"], cell(at, m)["ratio"]) for m in ("lap.end_distance", "lap.side_distance")],
                         [("lap-end-distance-oversize", "proved", 1.0), ("lap-side-distance-oversize", "proved", 1.0)], "1 inch and 1/16 inch more, for a 3/4 inch bolt")
        under = self.variant(oversize, ("end 1.5 inch", "end 1 inch"), ("side 3 inch", "side 1 inch"))
        self.assertEqual([cell(under, m)["state"] for m in ("lap.end_distance", "lap.side_distance")], ["refuted", "refuted"], "what is enough for a standard hole")
        self.assertAlmostEqual(cell(under, "lap.end_distance")["ratio"], 1.0625, places=6)
        # A 1 inch bolt: 1 1/4 inch of Table J3.4 and 1/8 inch of Table J3.5.
        inch = self.variant(oversize, ("diameter 0.75 inch", "diameter 1 inch"), ("end 1.5 inch", "end 1.375 inch"))
        self.assertEqual((cell(inch, "lap.end_distance")["state"], cell(inch, "lap.end_distance")["ratio"]), ("proved", 1.0))
        self.assertEqual(cell(at, "lap.hole_use")["state"], "open", "whether a bearing-type joint may have such holes is a line with no rule")

    def test_a_line_of_bolts_over_38_inch_takes_the_shear_stress_at_83_3_percent(self):
        """Note c of Table J3.2. The rule the deck had before, written by hand, said nothing of such a line, and its cell was open."""
        bolt = 0.75 * 54 * 3.141592653589793 / 4 * 0.75 ** 2
        long = self.variant(("count 3", "count 14"))      # 13 x 3 inch = 39 inch
        self.assertEqual(cell(long, "lap.strength")["state"], "proved")
        self.assertAlmostEqual(cell(long, "lap.strength")["ratio"], 45 / (14 * 0.833 * bolt), places=6)
        at = self.variant(("count 3", "count 20"), ("pitch 3 inch", "pitch 2 inch"))      # 19 x 2 inch = 38 inch, which is not over 38
        self.assertAlmostEqual(cell(at, "lap.strength")["ratio"], 45 / (20 * bolt), places=6)
        over = self.variant(("count 3", "count 20"), ("pitch 3 inch", "pitch 2.0001 inch"))
        self.assertAlmostEqual(cell(over, "lap.strength")["ratio"], 45 / (20 * 0.833 * bolt), places=6)

    def test_a_waiver_rests_only_a_cell_that_would_be_open_and_hides_no_refutation(self):
        """A card may waive a line that has rules, and the rules are still run. Under a pull of 200 kip a block tears out of each plate, so
        both cells of the waived line are refuted. Until a waiver rested only what was open, the line was one waived cell, and a card
        written when the deck had four rules, which waived the lines that had none then, hid the rules they have now.
        Under 45 kip the same rules prove, the cells are proved, and the waiver rests nothing."""
        path = ROOT / "examples" / "deck" / "lap_unknown.petra"
        card, design = read_pair(path)
        card += 'waive lap.block_shear on splice by "s.engineer@example.org" reason "calculation C-12 sheet 4"\n'
        with mock.patch.object(verify, "binary", lambda: None):
            found = petra.check(card.replace("45 kip", "200 kip"), design, path=str(path), repair=False)
            held = petra.check(card, design, path=str(path), repair=False)
        shear = {c["entry"]: (c["state"], c["rule"]) for c in found["cells"] if c["mechanism"] == "lap.block_shear"}
        self.assertEqual(shear, {"lap-block-shear-a/gravity": ("refuted", "aisc360-22/lap-block-shear-a"), "lap-block-shear-b/gravity": ("refuted", "aisc360-22/lap-block-shear-b")})
        self.assertEqual(cell(found, "lap.ply_rupture", "lap-ply-rupture-a/gravity")["state"], "refuted", "a line the card does not waive is still answered")
        self.assertEqual({c["state"] for c in held["cells"] if c["mechanism"] == "lap.block_shear"}, {"proved"})
        self.assertEqual((held["counts"]["waived"], held["status"]), (0, "UNKNOWN"), "the four lines with no rule are open, and the waiver of a line that proves rests none")

    def test_a_waived_line_with_no_rule_is_one_waived_cell_that_says_what_was_open(self):
        path = ROOT / "examples" / "deck" / "lap_pass.petra"
        with mock.patch.object(verify, "binary", lambda: None):
            found = petra.check(*read_pair(path), path=str(path), repair=False)
        waived = [c for c in found["cells"] if c["state"] == "waived"]
        self.assertEqual(([c["mechanism"] for c in waived], [c["entry"] for c in waived], found["status"]), (self.NO_RULE, [""] * 4, "PASS_WAIVED"))
        for c in waived:
            self.assertRegex(c["why"], r"^by .+: .+; open but for the waiver: the deck has no rule for it$")

    def test_a_pass_that_rests_on_a_waiver_says_so_in_its_text_its_json_its_exit_code_and_the_mcp_reply(self):
        """The lap of lap_pass passes every rule the deck has, and four cells rest on the card's waivers. `petra check` gives it a status
        word of its own, PASS_WAIVED, which exits 6, and its JSON lists the four waivers. The kernel says PASS and lists the same four."""
        import contextlib
        import io

        from petra import mcp
        from petra.cli import EXIT_CODES, main

        path = ROOT / "examples" / "deck" / "lap_pass.petra"
        card = read_pair(path)[0]
        waivers = [{"subject": "splice", "mechanism": m, "by": "s.engineer@example.org", "reason": card.split(f"waive {m} on splice by \"s.engineer@example.org\" reason \"")[1].split("\"")[0]}
                   for m in self.NO_RULE]
        for json_flag in ((), ("--json",)):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(["check", str(path), *json_flag])
            self.assertEqual(code, EXIT_CODES["PASS_WAIVED"])
            self.assertEqual(code, 6)
            if json_flag:
                said = json.loads(out.getvalue())
                self.assertEqual((said["status"], said["waived"]), ("PASS_WAIVED", waivers))
                if said["kernel"] is not None:
                    self.assertEqual((said["kernel"]["verdict"], said["kernel"]["waived"]), ("PASS", waivers))
            else:
                lines = out.getvalue().splitlines()
                self.assertEqual(lines[0], "lap-splice-waived: PASS_WAIVED")
                self.assertIn("waived     4 cells rest on 4 waivers, so the design passes what the deck could check and each signer answers for the rest", lines)
                self.assertIn(f"  splice/lap.tightening  by s.engineer@example.org: {waivers[0]['reason']}", lines)
        text, body = mcp._check({"path": str(path)})
        self.assertEqual((text.splitlines()[0], body["status"], body["waived"]), ("lap-splice-waived: PASS_WAIVED", "PASS_WAIVED", waivers))


def kernel_word(status: str) -> str:
    """The kernel's verdict for a status of `petra check`: PASS for PASS_WAIVED, whose waivers the kernel lists beside it."""
    return "PASS" if status == grid.PASS_WAIVED else status


@unittest.skipIf(verify.binary() is None, "no petra-verify is built here")
class Kernel(unittest.TestCase):
    """The kernel works out every cell the grid makes, and gives the same verdict. petra.check
    compares the two lists cell by cell and raises on a difference."""

    def test_the_kernel_agrees_on_the_shipped_examples(self):
        for name, status, its in (("lap_unknown", "UNKNOWN", "UNKNOWN"), ("lap_fail", "FAIL", "FAIL"), ("lap_pass", "PASS_WAIVED", "PASS")):
            with self.subTest(design=name):
                path = ROOT / "examples" / "deck" / f"{name}.petra"
                result = petra.check(*read_pair(path), path=str(path), repair=False)
                self.assertEqual((result["status"], result["kernel"]["verdict"], result["kernel"]["checked"]), (status, its, 12))

    def test_the_kernel_agrees_on_every_lap_of_the_corpus_and_each_gets_the_verdict_worked_out_by_hand(self):
        """corpus/expected.tsv gives each lap of corpus/cases/deck the verdict a hand calculation from AISC 360-22 gives it,
        and the header of each design shows the arithmetic. The grid and the kernel must both give that verdict."""
        expected = {}
        for line in (ROOT / "corpus" / "expected.tsv").read_text(encoding="utf-8").splitlines():
            path, _, rest = line.partition("\t")
            if path.startswith("corpus/cases/deck/"):
                expected[path] = rest.split("\t")[0]
        self.assertGreaterEqual(len(expected), 37)
        self.assertLessEqual({"PASS_WAIVED", "FAIL", "UNKNOWN", "INPUT_ERROR"}, set(expected.values()))
        for path, verdict in expected.items():
            with self.subTest(design=path):
                result = petra.check(*read_pair(ROOT / path), path=path, repair=False)
                if verdict == "NOT_PASS":         # the standard refuses it and the deck has no rule that can
                    self.assertIn(result["status"], ("FAIL", "UNKNOWN"))
                    self.assertEqual(result["kernel"]["verdict"], result["status"])
                    continue
                self.assertEqual(result["status"], verdict)
                if verdict != "INPUT_ERROR":      # a pair the grid refuses is not sent to the kernel
                    self.assertEqual(result["kernel"]["verdict"], kernel_word(verdict))

    def test_the_kernel_agrees_on_bands_cases_listed_values_and_a_split_proof(self):
        cards = {"at the end of a band": [], "over the band": [("[0 A, 2 A]", "[0 A, 2.01 A]")],
                 "two cases": [("[20 degC, 30 degC]", "[30 degC, 50 degC]"), ("[0 A, 2 A]", "[0 A, 1 A]")],
                 "two cases, refuted": [("[20 degC, 30 degC]", "[30 degC, 50 degC]"), ("[0 A, 2 A]", "[0 A, 1.5 A]")],
                 "a split proof": [("[0.5 mm, 0.6 mm]", "[1 mm, 3 mm]")]}
        for what, card_swap in cards.items():
            with self.subTest(what=what):
                card = CARD
                for old, new in card_swap:
                    card = card.replace(old, new)
                with mock.patch.object(grid, "decks", lambda: (deck(),)):
                    result = petra.check(card, DESIGN, path="strips.petra", repair=False)
                self.assertEqual(result["kernel"]["verdict"], kernel_word(result["status"]), "a difference raises before this line")
                self.assertGreaterEqual(result["kernel"]["checked"], 4)


if __name__ == "__main__":
    unittest.main()
