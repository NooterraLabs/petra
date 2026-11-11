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
import unittest
from pathlib import Path
from unittest import mock

import petra
from petra import deck as rows
from petra import grid, verify
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
         "when": ["loaded", "current"], "le": [["add", "screw", ["q", "0.1", "mm"]], "hole"]},
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
        self.assertEqual(result["status"], "PASS")
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
        self.assertEqual(cell(idle, "strip.spark")["state"], "open")
        self.assertIn("no rule for it on a part like this one", cell(idle, "strip.spark")["why"])

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


class Shipped(unittest.TestCase):
    """The deck of AISC 360-22 rows and the three designs under examples/deck."""

    def test_every_row_is_one_two_transcribers_agreed_on_and_passes_the_acceptance_check(self):
        spec = importlib.util.spec_from_file_location("formalizer_run", ROOT / "bench" / "formalizer" / "run.py")
        run = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(run)
        first, second = formalizer("a.json") | formalizer("a2.json"), formalizer("b.json") | formalizer("b2.json")
        examples = {}
        for name in ("examples.json", "examples2.json"):
            examples |= json.loads((ROOT / "bench" / "formalizer" / name).read_text(encoding="utf-8"))["examples"]
        body = json.loads((grid.DECKS / "aisc360.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(body["rows"]), 18)
        for written in body["rows"]:
            with self.subTest(row=written["id"]):
                self.assertEqual(written, first[written["id"]], "the row is the transcription, unedited")
                row = rows.read(written)
                found, unread = run.worked(row, examples.get(row.id, []))
                self.assertEqual(unread, [])
                checks = rows.accept(row, found, rows.read(second[row.id]))
                self.assertEqual([c.name for c in checks if c.outcome == "fail"], [])
                self.assertEqual(checks[-1].outcome, "pass", "a second transcription agrees")

    def check(self, name: str) -> dict:
        path = ROOT / "examples" / "deck" / f"{name}.petra"
        with mock.patch.object(verify, "binary", lambda: None):
            return petra.check(*read_pair(path), path=str(path), repair=False)

    def test_the_lap_that_waives_nothing_is_unknown_with_its_rules_proved(self):
        result = self.check("lap_unknown")
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["counts"], {"proved": 5, "refuted": 0, "not_applicable": 4, "waived": 0, "open": 8})
        # Three 3/4 inch Group 120 bolts with threads in the shear plane: 0.75 x 54 ksi x 0.4418 inch2 is 17.9 kip a bolt, the
        # shear strength Design Examples v16.0 prints for this bolt, and bearing and tearout on 3/8 inch A36 are above it.
        self.assertAlmostEqual(cell(result, "lap.strength", "lap-strength/gravity")["ratio"], 45 / (3 * 17.892), places=3)
        self.assertAlmostEqual(cell(result, "lap.ply_yield", "lap-yield-a/gravity")["ratio"], 45 / (0.9 * 36 * 6 * 0.375), places=6)
        self.assertAlmostEqual(cell(result, "lap.end_distance")["ratio"], 1 / 1.5, places=6)

    def test_the_overloaded_lap_fails_and_the_waived_one_passes(self):
        self.assertEqual(self.check("lap_fail")["status"], "FAIL")
        waived = self.check("lap_pass")
        self.assertEqual((waived["status"], waived["counts"]["waived"], waived["counts"]["open"]), ("PASS", 8, 0))

    def variant(self, *swap: tuple[str, str]) -> dict:
        path = ROOT / "examples" / "deck" / "lap_unknown.petra"
        card, design = read_pair(path)
        for old, new in swap:
            assert old in design, old
            design = design.replace(old, new)
        with mock.patch.object(verify, "binary", lambda: None):
            return petra.check(card, design, path=str(path), repair=False)

    def test_tearout_governs_a_short_end_and_the_table_refuses_it(self):
        short = self.variant(("end 1.5 inch", "end 0.75 inch"))
        self.assertEqual(cell(short, "lap.end_distance")["state"], "refuted", "Table J3.4 asks 1 inch of a 3/4 inch bolt")
        # lc = 0.75 - 13/32 inch, so an end bolt tears out at 1.2 x 0.34375 x 0.375 x 58 = 8.97 kip, under its shear strength of 23.86.
        capacity = 0.75 * (2 * min(23.856, 8.972) + 23.856)
        self.assertAlmostEqual(cell(short, "lap.strength", "lap-strength/gravity")["ratio"], 45 / capacity, places=3)

    def test_what_the_tables_do_not_list_is_open(self):
        odd = self.variant(("diameter 0.75 inch", "diameter 0.7 inch"))
        self.assertEqual({cell(odd, "lap.strength", "lap-strength/gravity")["state"], cell(odd, "lap.end_distance")["state"]}, {"open"})
        long = self.variant(("count 3", "count 14"))
        self.assertIn("at most 38 inch long", cell(long, "lap.strength")["why"])
        oversize = self.variant(("holes standard", "holes oversize"))
        self.assertIn("no rule for it on a part like this one", cell(oversize, "lap.end_distance")["why"])
        self.assertEqual(self.variant(("count 3", "count 1"))["status"], "INPUT_ERROR", "the rule sums over two end bolts")


@unittest.skipIf(verify.binary() is None, "no petra-verify is built here")
class Kernel(unittest.TestCase):
    """The kernel works out every cell the grid makes, and gives the same verdict. petra.check
    compares the two lists cell by cell and raises on a difference."""

    def test_the_kernel_agrees_on_the_shipped_examples(self):
        for name, status in (("lap_unknown", "UNKNOWN"), ("lap_fail", "FAIL"), ("lap_pass", "PASS")):
            with self.subTest(design=name):
                path = ROOT / "examples" / "deck" / f"{name}.petra"
                result = petra.check(*read_pair(path), path=str(path), repair=False)
                self.assertEqual((result["status"], result["kernel"]["verdict"], result["kernel"]["checked"]), (status, status, 5))

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
                self.assertEqual(result["kernel"]["verdict"], result["status"], "a difference raises before this line")
                self.assertGreaterEqual(result["kernel"]["checked"], 4)


if __name__ == "__main__":
    unittest.main()
