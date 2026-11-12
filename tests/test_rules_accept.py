"""The acceptance check for rules (petra/rule.py, docs/deck.md): a task, two transcriptions
of its rules, worked examples, and what the check says of each mechanism.

Most tests use the deck STRIPS of tests/test_grid.py, made up for tests: it is no standard,
and its numbers mean nothing. The task gives its types a range for each quantity, calls the
current adverse and the two pads of a strip alike. The first transcription is the deck's
own rules. The worked examples are made up too. The last class runs the check on the files
of the first run: bench/formalizer/rules_a.json, the deck as it shipped then, with
rules_b.json as its second transcription. tests/test_deck_rules.py runs the check on the
deck that ships now.
"""
import collections
import copy
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from fractions import Fraction
from pathlib import Path

from petra import grid, rule
from petra.kernel import Interval
from tests.test_grid import STRIPS, TEST

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "bench" / "formalizer"
RANGES = {"area": ["10 mm2", "100 mm2"], "width": ["0.5 mm", "5 mm"], "T": ["10 degC", "100 degC"], "gap": ["0.1 mm", "3.9 mm"], "screw": ["3 mm", "4 mm"],
          "hole": ["3 mm", "5 mm"], "turns": ["1", "4"], "current": ["0.1 A", "12 A"]}
# Two ways to write one made-up rule for the line of STRIPS that has none: a rule for each pad, and one rule with their minimum.
CREEP = {"id": "test/creep", "type": "strip", "mechanism": "strip.creep", "anchor": TEST, "says": "each pad has 20 mm2 for each strip"}
BY_PAD = [{**CREEP, "id": f"test/creep-{pad}", "le": [["mul", "turns", ["q", "20", "mm2"]], f"{pad}.area"]} for pad in ("near", "far")]
BY_MIN = [{**CREEP, "le": [["mul", "turns", ["q", "20", "mm2"]], ["min", "near.area", "far.area"]]}]
EXAMPLES = {
    "strip.heat": [{"anchor": "made up, 1", "given": {"width": "1 mm", "T": "25 degC", "turns": "2", "near.area": "50 mm2", "far.area": "50 mm2"},
                    "loads": {"current": "1.5 A"}, "side": "right", "gives": "2 A"},
                   {"anchor": "made up, 2", "given": {"width": "1.5 mm", "T": "60 degC", "turns": "3", "near.area": "20 mm2", "far.area": "30 mm2"},
                    "loads": {"current": "2.4 A"}, "side": "ratio", "gives": "0.80"}],
    "strip.hole": [{"anchor": "made up, 3", "given": {"screw": "3 mm", "fit": "close", "hole": "3.5 mm"}, "side": "left", "gives": "3.2 mm"}],
    "strip.bow": [{"anchor": "made up, 4", "given": {"gap": "1 mm"}, "side": "left", "gives": "3.0 mm2"}],
    "strip.spark": [{"anchor": "made up, 5", "given": {"screw": "3 mm", "fit": "free", "hole": "3.6 mm"}, "loads": {"current": "1 A"}, "side": "ratio", "gives": "0.861"}],
}


def task_body() -> dict:
    """The task as JSON: the types of STRIPS with a range for each quantity, its rows, and its grid with no `unless`."""
    types = copy.deepcopy(STRIPS["types"])
    for t in types:
        for f in (*t["fields"], *t.get("loads", [])):
            if "dim" in f:
                f["range"] = RANGES[f["name"]]
    types[1]["alike"] = [["near", "far"]]
    types[1]["loads"][0]["adverse"] = True
    return {"format": rule.TASK, "name": "test-strips", "about": "Made up for the tests.", "rows": copy.deepcopy(STRIPS["rows"]), "types": types,
            "asks": [{k: v for k, v in a.items() if k != "unless"} for a in STRIPS["grid"]]}


def task(edit=lambda body: None) -> rule.Task:
    body = task_body()
    edit(body)
    return rule.read_task(body)


TASK = task()


def reading(edit=lambda body: None, of: rule.Task = TASK) -> rule.Reading:
    """The deck's own rules and `unless` as a transcription, after an edit of the deck."""
    body = copy.deepcopy(STRIPS)
    edit(body)
    return rule.Reading(of, rule.read_transcription(body))


FIRST = reading()


def worked(of: dict = EXAMPLES) -> dict:
    return {m: [rule.worked(e, TASK, m) for e in found] for m, found in of.items()}


def check(mine: rule.Reading, mechanism: str, name: str, other: rule.Reading | None = None, examples: dict | None = None) -> rule.Check:
    """One part of the check on one mechanism, as rule.accept runs it."""
    tried = rule.parts(mine.task, mechanism, [mine, *([other] if other is not None else [])])
    if name == "second":
        return rule.second(mine, other, mechanism, tried)
    return next(c for c in rule.checks(mine, mechanism, worked(examples or {}).get(mechanism, []), tried) if c.name == name)


def with_rule(n: int, **changed):
    """An edit of a deck that changes keys of its n-th rule. A key set to None is removed."""
    def edit(body: dict) -> None:
        body["rules"][n] = {k: v for k, v in {**body["rules"][n], **changed}.items() if v is not None}
    return edit


class Agreement(unittest.TestCase):
    def second(self, mechanism: str, edit, mine: rule.Reading = FIRST) -> rule.Check:
        return check(mine, mechanism, "second", reading(edit))

    def test_a_transcription_agrees_with_itself_and_every_mechanism_it_answers_is_admitted(self):
        lines, whole = rule.accept(FIRST, worked(), reading())
        self.assertEqual({line.mechanism: line.state for line in lines},
                         {"strip.heat": "admitted", "strip.hole": "admitted", "strip.bow": "admitted", "strip.creep": "left out", "strip.spark": "admitted", "strip.tide": "admitted"})
        self.assertEqual({c.outcome for line in lines for c in line.checks if c.name in ("units", "examples", "second")}, {"pass"})
        self.assertEqual(whole.outcome, "pass", whole.detail)
        self.assertEqual(next(line for line in lines if line.mechanism == "strip.creep").note, "the other transcription leaves it out too")

    def test_other_names_and_another_order_are_the_same_rule(self):
        renamed = with_rule(0, let={"cold": ["row", "test/limit", {"w": "width"}], "share": ["row", "test/derate", {"T": "T"}]},
                            le=[["load", "current"], ["mul", "share", "cold", "turns"]], id="other/heat", says="in other words")
        self.assertEqual(self.second("strip.heat", renamed).outcome, "pass")

    def test_two_rules_and_one_rule_with_their_minimum_are_the_same(self):
        split, joined = reading(lambda b: b["rules"].extend(BY_PAD)), reading(lambda b: b["rules"].extend(BY_MIN))
        found = check(split, "strip.creep", "second", joined)
        self.assertEqual((found.outcome, "2 rules against 1" in found.detail), ("pass", True), found.detail)
        self.assertEqual(check(joined, "strip.creep", "second", split).outcome, "pass")
        one_pad = reading(lambda b: b["rules"].append(BY_PAD[0]))
        found = check(split, "strip.creep", "second", one_pad)
        self.assertEqual(found.outcome, "fail")
        self.assertIn("whether the inequality holds", found.detail)

    def test_both_sides_times_one_factor_are_the_same_and_no_note_is_made(self):
        scaled = with_rule(2, le=[["mul", "2", "gap", ["sub", ["q", "4", "mm"], "gap"]], ["q", "8.4", "mm2"]])
        found = self.second("strip.bow", scaled)
        self.assertEqual((found.outcome, "different forms" in found.detail), ("pass", False), found.detail)

    def test_a_difference_at_most_zero_is_the_same_inequality_in_another_form_and_the_check_says_so(self):
        heat = with_rule(0, le=[["sub", ["load", "current"], ["mul", "turns", ["row", "test/limit", {"w": "width"}], ["row", "test/derate", {"T": "T"}]]], ["q", "0", "A"]])
        found = self.second("strip.heat", heat)
        self.assertEqual(found.outcome, "pass", found.detail)
        self.assertIn("208 parts, which hold or fail at 180; the two write the inequality in different forms: they give another ratio at 180 of the 180 parts that hold or fail, "
                      "and from 32 of the first 32 each turns at the same place", found.detail)
        self.assertIn("this one holds at 0.20443 (test/heat: 0.61329 against 3) and the other holds (test/heat: -2.38671 against 0)", found.detail)
        spark = with_rule(3, le=[["sub", ["add", "screw", ["q", "0.1", "mm"]], "hole"], ["q", "0", "mm"]])
        found = self.second("strip.spark", spark)
        self.assertEqual((found.outcome, "different forms" in found.detail), ("pass", True), "it reads no load, so a size is moved: " + found.detail)

    def test_another_form_of_another_inequality_is_refused(self):
        heat = with_rule(0, le=[["sub", ["load", "current"], ["mul", "turns", ["row", "test/limit", {"w": "width"}]]], ["q", "0", "A"]])
        self.assertEqual(self.second("strip.heat", heat).outcome, "fail", "it left out the share a warm strip carries")
        spark = with_rule(3, le=[["sub", ["add", "screw", ["q", "0.11", "mm"]], "hole"], ["q", "0", "mm"]])
        self.assertEqual(self.second("strip.spark", spark).outcome, "fail")

    def test_open_is_open_whatever_leaves_it_open(self):
        """One transcription says its rule for a spark holds for a hole of at most 4 mm, in a range. The other reads a made-up
        table that has a line up to 4 mm and none above, so over 4 mm its row gives no value. The cell is open either way."""
        cover = {"id": "test/cover", "anchor": TEST, "gives": {"name": "c", "dim": "dimensionless", "what": "one, for a hole the table covers"},
                 "takes": [{"name": "h", "dim": "length", "what": "the hole", "range": ["3 mm", "5 mm"]}],
                 "table": {"down": {"by": "h", "bands": [["0 mm", "4 mm"]]}, "cells": ["1"]}}
        covered = task(lambda b: b["rows"].append(cover))
        ranged = reading(with_rule(3, where=[{"le": ["hole", ["q", "4", "mm"]], "why": "the hole is at most 4 mm"}]), covered)
        tabled = reading(with_rule(3, le=[["add", "screw", ["q", "0.1", "mm"]], ["mul", "hole", ["row", "test/cover", {"h": "hole"}]]]), covered)
        self.assertEqual(check(ranged, "strip.spark", "second", tabled).outcome, "pass")
        wide = next(p for p in rule.parts(covered, "strip.spark", [ranged, tabled]).base if p["fit"] == "free" and p["hole"] > Fraction(4, 1000))
        mine, theirs = ranged.answer("strip.spark", wide), tabled.answer("strip.spark", wide)
        self.assertEqual([(a.state, a.kind) for a in (mine, theirs)], [("open", "range"), ("open", "value")])

    def test_two_inequalities_that_no_part_fails_cannot_be_told_the_same(self):
        """The made-up rule for bowing never fails: gap (4 mm - gap) is at most 4 mm2. With 4.3 for 4.2 no part gets another
        answer, and only the ratio differs. The check finds no place where either turns, and refuses."""
        found = self.second("strip.bow", with_rule(2, le=[["mul", "gap", ["sub", ["q", "4", "mm"], "gap"]], ["q", "4.3", "mm2"]]))
        self.assertEqual(found.outcome, "fail")
        self.assertIn("the two give another ratio at 128 of the 128 parts that hold or fail, and from 0 of the first 32 a load or a size was found that turns either answer, "
                      "too few to tell whether the two are one inequality", found.detail)
        self.assertIn("this one holds at 0.67", found.detail)
        self.assertIn("the other holds at 0.65", found.detail)


class Disagreement(unittest.TestCase):
    def differs(self, mechanism: str, edit, *says: str) -> None:
        found = check(FIRST, mechanism, "second", reading(edit))
        self.assertEqual(found.outcome, "fail", found.detail)
        for text in says:
            self.assertIn(text, found.detail)

    def test_a_factor(self):
        self.differs("strip.spark", with_rule(3, le=[["add", "screw", ["q", "0.11", "mm"]], "hole"]), "whether the inequality holds", "test/spark")
        self.differs("strip.heat", with_rule(0, le=[["load", "current"], ["mul", "0.9", "turns", ["row", "test/limit", {"w": "width"}], ["row", "test/derate", {"T": "T"}]]]),
                     "this one holds at", "and the other fails at")

    def test_a_range(self):
        loose = with_rule(0, where=[{"le": [["add", "near.area", "far.area"], ["q", "125", "mm2"]], "why": "the pads are at most 125 mm2 together"}])
        self.differs("strip.heat", loose, "the range a rule holds in", "outside its range: the pads are at most 120 mm2 together")
        self.differs("strip.heat", with_rule(0, where=None), "the range a rule holds in")

    def test_which_parts_a_rule_answers_for(self):
        self.differs("strip.spark", with_rule(3, when=["is", "fit", "close"]), "which parts a rule answers for", "has no rule for a part like it")
        self.differs("strip.spark", with_rule(3, when=["not", ["is", "fit", "free"]]), "which parts a rule answers for")
        same = check(FIRST, "strip.spark", "second", reading(with_rule(3, when=None)))
        self.assertEqual(same.outcome, "pass", "the line cannot arise for a close fit, so a rule for every strip answers the same parts")

    def test_a_transcription_that_asks_whether_a_load_is_there_does_not_load(self):
        """`loaded` is no condition (the fifth review): a rule that asks it is refused when its deck is read, and here in `units`."""
        asked = reading(with_rule(3, when=["loaded", "current"]))
        found = check(asked, "strip.spark", "units")
        self.assertEqual(found.outcome, "fail")
        self.assertIn(grid.LOADED, found.detail)

    def test_whether_the_mechanism_can_arise(self):
        self.differs("strip.spark", lambda b: b["grid"][4].pop("unless"), "whether it can arise", "says it cannot arise (a close fit leaves no room for one)")
        self.differs("strip.spark", lambda b: b["grid"][4]["unless"].__setitem__("when", ["is", "fit", "free"]), "whether it can arise")
        self.differs("strip.tide", lambda b: [b["grid"][5].pop("unless"), b["rules"].append({**CREEP, "mechanism": "strip.tide", "le": ["gap", ["q", "9", "mm"]]})], "whether it can arise")

    def test_the_column_of_a_table(self):
        self.differs("strip.hole", with_rule(1, le=[["row", "test/drill", {"d": "screw", "fit": ["by", "fit", {"close": "free", "free": "close"}]}], "hole"]))
        self.differs("strip.hole", with_rule(1, le=[["row", "test/drill", {"d": "screw", "fit": ["key", "close"]}], "hole"]), "where a row gives a value", "test/drill gives no value here")

    def test_the_end_of_a_band_and_a_case_on_each_side(self):
        """The rows of a second transcription are the task's, so only the rule can move an end: here it reads the table at a width a hundredth larger."""
        wider = with_rule(0, le=[["load", "current"], ["mul", "turns", ["row", "test/limit", {"w": ["mul", "1.01", "width"]}], ["row", "test/derate", {"T": "T"}]]])
        self.differs("strip.heat", wider, "whether the inequality holds")
        warmer = with_rule(0, le=[["load", "current"], ["mul", "turns", ["row", "test/limit", {"w": "width"}], ["row", "test/derate", {"T": ["sub", "T", ["q", "0.01", "degC"]]}]]])
        self.differs("strip.heat", warmer, "whether the inequality holds")

    def test_a_mechanism_the_other_leaves_out_has_no_second(self):
        found = check(FIRST, "strip.bow", "second", reading(lambda b: b["rules"].pop(2)))
        self.assertEqual((found.outcome, found.detail), ("none", "the other transcription leaves it out"))
        lines, _ = rule.accept(reading(lambda b: b["rules"].pop(2)), {}, FIRST)
        self.assertEqual(next(line.note for line in lines if line.mechanism == "strip.bow"), "the other transcription answers it")

    def test_the_other_does_not_load(self):
        found = check(FIRST, "strip.bow", "second", reading(with_rule(2, le=["gap", ["q", "4", "A"]])))
        self.assertEqual(found.outcome, "fail")
        self.assertIn("the other transcription does not load", found.detail)


class Examples(unittest.TestCase):
    def test_the_rules_reproduce_a_side_or_the_ratio(self):
        for mechanism, count in (("strip.heat", 2), ("strip.hole", 1), ("strip.bow", 1), ("strip.spark", 1)):
            found = check(FIRST, mechanism, "examples", examples=EXAMPLES)
            self.assertEqual((found.outcome, found.detail), ("pass", f"{count} reproduced"))
        self.assertEqual(check(FIRST, "strip.heat", "examples").outcome, "none")

    def test_a_wrong_rule_does_not(self):
        wrong = reading(with_rule(0, le=[["load", "current"], ["mul", "turns", ["row", "test/limit", {"w": "width"}]]]))
        found = check(wrong, "strip.heat", "examples", examples=EXAMPLES)
        self.assertEqual(found.outcome, "fail")
        self.assertIn("made up, 2: prints 0.80 for the ratio, and test/heat gives 0.5000 of it", found.detail)
        self.assertNotIn("made up, 1", found.detail, "at 25 degC the share is 1, so the first example cannot tell")
        swapped = reading(with_rule(2, le=[["q", "4.2", "mm2"], ["mul", "gap", ["sub", ["q", "4", "mm"], "gap"]]]))
        self.assertIn("prints 3.0 mm2 for the left side, and test/bow gives 1.4000 of it", check(swapped, "strip.bow", "examples", examples=EXAMPLES).detail)

    def test_a_rule_that_reads_what_the_example_does_not_give_does_not_reproduce_it(self):
        reads_more = reading(with_rule(2, le=[["mul", "gap", ["sub", "hole", "gap"]], ["q", "4.2", "mm2"]]))
        found = check(reads_more, "strip.bow", "examples", examples=EXAMPLES)
        self.assertEqual((found.outcome, found.detail), ("fail", "made up, 4: the rules read hole, which the example does not give"))

    def test_an_example_of_one_of_two_like_parts_is_held_against_the_rules_it_gives_every_field_of(self):
        """A source that works one pad of two gives that pad's fields alone. The rule for that pad must reproduce it, and the
        rule for the other pad is not tested by it. Two strips take 40 mm2 of each pad: 0.80 of a pad of 50 mm2, and all of one of 40."""
        near = {"strip.creep": [{"anchor": "made up, 6", "given": {"turns": "2", "near.area": "50 mm2"}, "side": "ratio", "gives": "0.80"}]}
        more = ["mul", "turns", ["q", "25", "mm2"]]

        def by_pad(near_rule: dict = BY_PAD[0], far_rule: dict = BY_PAD[1]) -> rule.Reading:
            return reading(lambda b: b["rules"].extend([near_rule, far_rule]))

        found = check(by_pad(), "strip.creep", "examples", examples=near)
        self.assertEqual((found.outcome, found.detail), ("pass", "1 reproduced"), "the rule for the far pad reads far.area, which the example does not give, and is set aside")
        wrong_near = check(by_pad(near_rule={**BY_PAD[0], "le": [more, "near.area"]}), "strip.creep", "examples", examples=near)
        self.assertEqual((wrong_near.outcome, wrong_near.detail), ("fail", "made up, 6: prints 0.80 for the ratio, and test/creep-near gives 1.2500 of it"))
        wrong_far = by_pad(far_rule={**BY_PAD[1], "le": [more, "far.area"]})
        self.assertEqual(check(wrong_far, "strip.creep", "examples", examples=near).outcome, "pass", "a wrong rule for the far pad is not tested by an example of the near one")
        # One rule with the lesser of the two pads reads both, so the example gives no rule every field, and none reproduces it.
        joined = check(reading(lambda b: b["rules"].extend(BY_MIN)), "strip.creep", "examples", examples=near)
        self.assertEqual((joined.outcome, joined.detail), ("fail", "made up, 6: the rules read far.area, which the example does not give"))
        # An example that gives both pads is held against both rules, and the smaller pad governs.
        both = {"strip.creep": [{"anchor": "made up, 7", "given": {"turns": "2", "near.area": "50 mm2", "far.area": "40 mm2"}, "side": "ratio", "gives": "1.00"}]}
        self.assertEqual(check(by_pad(), "strip.creep", "examples", examples=both).outcome, "pass")
        found = check(wrong_far, "strip.creep", "examples", examples=both)
        self.assertEqual((found.outcome, found.detail), ("fail", "made up, 7: prints 1.00 for the ratio, and test/creep-far gives 1.2500 of it"))

    def test_a_side_that_reads_no_load_needs_none(self):
        no_load = {"strip.heat": [{**EXAMPLES["strip.heat"][0], "loads": {}}]}
        self.assertEqual(check(FIRST, "strip.heat", "examples", examples=no_load).outcome, "pass")
        ratio = {"strip.heat": [{**EXAMPLES["strip.heat"][1], "loads": {}}]}
        self.assertIn("the rules read current, which the example does not give", check(FIRST, "strip.heat", "examples", examples=ratio).detail)

    def test_the_printed_value_has_the_dimension_of_the_side(self):
        length = {"strip.bow": [{**EXAMPLES["strip.bow"][0], "gives": "3.0 mm"}]}
        self.assertIn("prints a length, and the sides of test/bow are a area", check(FIRST, "strip.bow", "examples", examples=length).detail)

    def test_an_example_of_a_part_the_rules_do_not_answer_fails(self):
        close = {"strip.spark": [{**EXAMPLES["strip.spark"][0], "given": {"screw": "3 mm", "fit": "close", "hole": "3.6 mm"}}]}
        self.assertIn("for this part the transcription says it cannot arise", check(FIRST, "strip.spark", "examples", examples=close).detail)

    def test_an_example_names_fields_of_the_type_with_their_dimensions(self):
        for given, says in (({"gap": "1 A"}, "gap = 1 A is not a length"), ({"depth": "1 mm"}, "a strip has no depth"), ({"fit": "snug"}, "fit = snug is not one of close, free")):
            with self.assertRaises(grid.DeckError) as ctx:
                rule.worked({**EXAMPLES["strip.bow"][0], "given": given}, TASK, "strip.bow")
            self.assertIn(says, str(ctx.exception))
        with self.assertRaises(grid.DeckError):
            rule.worked({**EXAMPLES["strip.bow"][0], "side": "top"}, TASK, "strip.bow")


class Alone(unittest.TestCase):
    """The parts of the check that need no second transcription."""

    def test_units_is_what_reading_a_deck_says(self):
        self.assertIn("`le` compares a length with a current", check(reading(with_rule(2, le=["gap", ["q", "4", "A"]])), "strip.bow", "units").detail)
        self.assertIn("w is a length, and the rule binds a temperature", check(reading(with_rule(0, le=[["load", "current"], ["row", "test/limit", {"w": "T"}]])), "strip.heat", "units").detail)
        tide = reading(lambda b: b["rules"].append({**CREEP, "mechanism": "strip.tide", "le": ["gap", ["q", "9", "mm"]]}))
        self.assertIn("says it never arises", check(tide, "strip.tide", "units").detail)
        lines, _ = rule.accept(tide)
        self.assertEqual(next(line.state for line in lines if line.mechanism == "strip.tide"), "refused")

    def test_a_rule_for_a_mechanism_the_task_does_not_ask_is_stray(self):
        stray = reading(lambda b: b["rules"].append({**CREEP, "mechanism": "strip.melt", "le": ["gap", ["q", "9", "mm"]]}))
        self.assertEqual(stray.stray, ["rule test/creep answers strip.melt, which the task does not ask"])
        self.assertEqual(reading(lambda b: b["rules"].append(b["rules"][0])).stray, ["two rules have the id test/heat"])

    def test_reach_fails_a_rule_that_answers_no_part_or_fails_every_part(self):
        never = with_rule(0, where=[{"le": [["add", "near.area", "far.area"], ["q", "1", "mm2"]], "why": "the pads are tiny"}])
        found = check(reading(never), "strip.heat", "reach")
        self.assertEqual(found.outcome, "fail")
        self.assertIn("test/heat answers none of 96 parts", found.detail)
        self.assertIn("outside its range: the pads are tiny", found.detail)
        found = check(reading(with_rule(2, le=[["mul", "gap", ["sub", ["q", "4", "mm"], "gap"]], ["q", "0.001", "mm2"]])), "strip.bow", "reach")
        self.assertEqual((found.outcome, "it fails every part it answers" in found.detail), ("fail", True))
        self.assertEqual(check(FIRST, "strip.heat", "reach").outcome, "pass", check(FIRST, "strip.heat", "reach").detail)

    def test_reach_says_what_the_sampled_parts_never_put_to_work(self):
        slack = check(reading(with_rule(2, le=[["mul", "gap", ["sub", ["q", "4", "mm"], "gap"]], ["q", "42", "mm2"]])), "strip.bow", "reach")
        self.assertEqual(slack.outcome, "none")
        self.assertIn("test/bow holds at every sampled part it answers", slack.detail)
        wide = check(reading(with_rule(0, where=[{"le": [["add", "near.area", "far.area"], ["q", "900", "mm2"]], "why": "the pads are small"}])), "strip.heat", "reach")
        self.assertEqual(wide.outcome, "none")
        self.assertIn("test/heat: its range holds at every sampled part (the pads are small)", wide.detail)
        dead = check(reading(lambda b: b["rules"].append({**CREEP, "le": [["mul", "turns", ["q", "20", "mm2"]], ["min", "near.area", "far.area", ["q", "1", "m2"]]]})), "strip.creep", "reach")
        self.assertEqual(dead.outcome, "none")
        self.assertIn('test/creep: ["q", "1", "m2"] never decides its min in le 1', dead.detail)
        self.assertNotIn("near.area", dead.detail)

    def test_direction_fails_sides_that_changed_places(self):
        swapped = with_rule(0, le=[["mul", "turns", ["row", "test/limit", {"w": "width"}], ["row", "test/derate", {"T": "T"}]], ["load", "current"]])
        found = check(reading(swapped), "strip.heat", "direction")
        self.assertEqual(found.outcome, "fail")
        self.assertIn("more current helps", found.detail)
        self.assertEqual(check(FIRST, "strip.heat", "direction").outcome, "pass")
        self.assertEqual(check(FIRST, "strip.bow", "direction").outcome, "none", "it reads no load")
        self.assertEqual(check(FIRST, "strip.spark", "direction").outcome, "none", "its rule reads no load")
        self.assertEqual(check(reading(swapped, task(lambda b: b["types"][1]["loads"][0].pop("adverse"))), "strip.heat", "direction").outcome, "none", "the task calls no load adverse")

    def test_alike_fails_a_rule_that_treats_two_like_parts_differently(self):
        twice = with_rule(0, where=[{"le": [["add", "near.area", "near.area"], ["q", "120", "mm2"]], "why": "the pads are at most 120 mm2 together"}])
        found = check(reading(twice), "strip.heat", "alike")
        self.assertEqual(found.outcome, "fail")
        self.assertIn("with near and far changed places the answer changes", found.detail)
        self.assertEqual(check(FIRST, "strip.heat", "alike").outcome, "pass")
        self.assertEqual(check(FIRST, "strip.bow", "alike").outcome, "none", "it reads no pad")
        both = reading(lambda b: b["rules"].extend(BY_PAD))
        self.assertEqual(check(both, "strip.creep", "alike").outcome, "pass", "a rule for each pad is alike as a pair")
        self.assertEqual(check(reading(lambda b: b["rules"].append(BY_PAD[0])), "strip.creep", "alike").outcome, "fail")

    def test_reads_names_each_field_and_load_that_nothing_reads(self):
        self.assertEqual(rule.reads(FIRST).outcome, "pass")
        found = rule.reads(reading(lambda b: b["rules"].pop(2)))
        self.assertEqual((found.outcome, found.detail), ("fail", "nothing reads strip.gap; 2 mechanisms have no rule that loads, and one of them may"))
        idle = rule.reads(reading(lambda b: [b["rules"].pop(3), b["rules"].pop(0)]))
        self.assertIn("nothing reads strip.width, strip.T, strip.turns, strip.near.area, strip.far.area, strip.current", idle.detail)

    def test_reads_names_a_load_that_no_expression_reads(self):
        """Only test/heat reads the current. With it gone no expression reads the current, and
        `petra check` would leave a design open at it (docs/format.md, "Cells from a deck of
        rules", item 8)."""
        asked = rule.reads(reading(lambda b: b["rules"].pop(0)))
        self.assertIn("nothing reads strip.width, strip.T, strip.turns, strip.near.area, strip.far.area, strip.current", asked.detail)


class Parts(unittest.TestCase):
    def test_every_combination_of_keys_and_every_load_on_every_part(self):
        """A part carries every load of its type: a card states each load in every case, as zero where there is none."""
        tried = rule.parts(TASK, "strip.spark", [FIRST])
        self.assertEqual(len(tried.base), rule.PARTS)
        self.assertEqual({p["fit"] for p in tried.base}, {"close", "free"})
        self.assertTrue(all("load current" in p for mechanism in ("strip.spark", "strip.heat") for p in rule.parts(TASK, mechanism, [FIRST]).base))

    def test_a_size_bound_to_a_table_sits_on_and_beside_its_ends(self):
        mm = Fraction(1, 1000)
        widths = {p["width"] for p in rule.parts(TASK, "strip.heat", [FIRST]).base}
        self.assertLessEqual({1 * mm, 2 * mm, 1 * mm + mm / 1000, 2 * mm - mm / 1000}, widths)
        screws = [p["screw"] for p in rule.parts(TASK, "strip.hole", [FIRST]).base]
        self.assertGreater(sum(s in (3 * mm, 4 * mm) for s in screws), 80, "a table read at listed values gives nothing between them")
        self.assertIn(Fraction(7, 2) * mm, screws)

    def test_a_count_is_a_whole_number_and_a_partner_keeps_what_is_not_a_size(self):
        tried = rule.parts(TASK, "strip.hole", [FIRST])
        self.assertEqual({p["turns"] for p in tried.base}, {1, 2, 3, 4})
        for p, q in tried.pairs:
            self.assertEqual((p["fit"], p["turns"], p["screw"]), (q["fit"], q["turns"], q["screw"]))
        self.assertTrue(any(p["hole"] != q["hole"] for p, q in tried.pairs))

    def test_the_parts_do_not_depend_on_the_order_the_readings_come_in(self):
        other = reading(with_rule(0, id="other/heat"))
        self.assertEqual(rule.parts(TASK, "strip.heat", [FIRST, other]), rule.parts(TASK, "strip.heat", [other, FIRST]))

    def test_a_point_gives_what_the_grid_encloses_over_a_box_of_points(self):
        """rule._values is a second way to evaluate a tape at a point. It must give what grid.enclosures gives."""
        aisc = rule.read_task(json.loads((BENCH / "rules_task.json").read_text(encoding="utf-8")), BENCH)
        compared = 0
        for of, mine in ((TASK, FIRST), (aisc, rule.load(aisc, str(BENCH / "rules_a.json")))):
            for mechanism in of.mechanisms:
                for found in mine.rules[mechanism]:
                    for point in rule.parts(of, mechanism, [mine]).base[:24]:
                        tape = mine._tape(found, point)
                        if isinstance(tape, str) or any(label not in point for label in tape.labels):
                            continue
                        box = [point[label] for label in tape.labels]
                        ours, _ = rule._values(tape, box)
                        theirs = grid.enclosures([list(node) for node in tape.raw], [Interval.point(x) for x in box])
                        for a, b in zip(ours, theirs, strict=True):
                            self.assertEqual(isinstance(a, str), isinstance(b, str), (found.id, a, b))
                            self.assertTrue(isinstance(a, str) or rule._lifted(a) == b, (found.id, a, b))
                        compared += 1
        self.assertGreater(compared, 150)


class Tasks(unittest.TestCase):
    def refused(self, says: str, edit) -> None:
        with self.assertRaises(grid.DeckError) as ctx:
            task(edit)
        self.assertIn(says, str(ctx.exception))

    def test_a_task_gives_each_quantity_a_range_a_part_may_have(self):
        self.refused("strip.gap: a task gives each quantity and each load a `range`", lambda b: b["types"][1]["fields"][2].pop("range"))
        self.refused("strip.gap: its range is two length values a part may have, the lower first", lambda b: b["types"][1]["fields"][2].__setitem__("range", ["2 mm", "1 mm"]))
        self.refused("strip.gap: its range is two length values", lambda b: b["types"][1]["fields"][2].__setitem__("range", ["0 mm", "1 mm"]))
        self.refused("strip.turns: its range is two dimensionless values", lambda b: b["types"][1]["fields"][6].__setitem__("range", ["1.5", "4"]))
        self.refused("strip.fit: only a quantity has a range", lambda b: b["types"][1]["fields"][5].__setitem__("range", ["1 mm", "2 mm"]))

    def test_a_task_asks_and_does_not_answer(self):
        self.refused("a task asks each mechanism once and gives no `unless`", lambda b: b["asks"][0].__setitem__("unless", {"why": "never"}))
        self.refused("`alike` lists groups of two or more joined parts of one type", lambda b: b["types"][1].__setitem__("alike", [["near", "width"]]))
        self.refused("a task has format", lambda b: b.__setitem__("rules", []))

    def test_a_deck_is_read_as_a_transcription(self):
        said = rule.read_transcription(STRIPS)
        self.assertEqual((len(said.rules), sorted(said.unless)), (4, ["strip.spark", "strip.tide"]))
        own = rule.read_transcription({"rules": [], "unless": [{"mechanism": "strip.tide", "why": "dry"}], "left_out": [{"mechanism": "strip.creep", "why": "no row"}], "transcriber": "x"})
        self.assertEqual((dict(own.unless), dict(own.left_out)), ({"strip.tide": {"why": "dry"}}, {"strip.creep": "no row"}))


def bench():
    spec = importlib.util.spec_from_file_location("formalizer_rules", BENCH / "rules.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Measurement(unittest.TestCase):
    """bench/formalizer/rules.py damages each rule one change at a time and counts what the check refuses with no second transcription."""

    @classmethod
    def setUpClass(cls):
        cls.bench = bench()
        cls.lines, cls.kinds = cls.bench.measure(FIRST, worked(), ["strip.heat", "strip.hole", "strip.bow", "strip.spark"])

    def test_each_kind_of_damage_is_made(self):
        heat = [(kind, what) for kind, what, _ in self.bench.mutations(STRIPS["rules"][0], TASK)]
        self.assertEqual(sorted({kind for kind, _ in heat}), ["factor", "other part", "sides swapped", "similar field", "term dropped", "where dropped"])
        self.assertLessEqual({("other part", "near.area becomes far.area in where 0"), ("similar field", "width becomes gap in le 1"), ("factor", "120 up a tenth in where 0"),
                              ("term dropped", "mul loses argument 3 in le 1"), ("where dropped", "range 1 left out in "), ("sides swapped", "the two sides of range 1 change places in ")},
                             {(kind, what if " in " in what else what + " in ") for kind, what in heat})
        made = {kind for r in STRIPS["rules"] for kind, _, _ in self.bench.mutations(r, TASK)}
        self.assertLessEqual({"key column", "when inverted", "turned round"}, made)
        more = task(lambda b: [b["types"][1]["loads"].append({"name": "surge", "dim": "current", "what": "a surge", "range": ["1 A", "20 A"]}),
                               b["rows"].append({**b["rows"][0], "id": "test/limit-cold"})])
        found = [(kind, what) for kind, what, _ in self.bench.mutations(STRIPS["rules"][0], more)]
        self.assertIn(("other load", "load current becomes surge in le 0"), found)
        self.assertIn(("other row", "test/limit becomes test/limit-cold in le 1"), found)
        capped = {**CREEP, "le": [["max", "gap", "screw"], "hole"]}
        self.assertIn("min for max", [kind for kind, _, _ in self.bench.mutations(capped, TASK)])
        self.assertEqual({kind for r in STRIPS["rules"] for kind, _, _ in self.bench.mutations(r, more)} | {"min for max"}, set(self.bench.KINDS))

    def test_one_change_is_made_at_a_time_and_the_rule_is_left_as_it_was(self):
        before = copy.deepcopy(STRIPS["rules"])
        for body in STRIPS["rules"]:
            for _, what, damaged in self.bench.mutations(body, TASK):
                self.assertNotEqual(damaged, body, what)
        self.assertEqual(STRIPS["rules"], before)

    def test_the_tally_by_kind_of_damage(self):
        total = sum((tally for tally in self.kinds.values()), start=collections.Counter())
        self.assertEqual((total["wrong"], total["any"]), (49, 43), "the samples come from a fixed seed, so the tally is the same each time")
        self.assertEqual([total[name] for name in self.bench.PARTS], [3, 34, 7, 1, 2, 10], "every rule of STRIPS has a made-up example, and an example catches most damage")
        self.assertEqual((self.kinds["factor"]["wrong"], self.kinds["factor"]["any"]), (8, 2), "an example whose part is inside a range cannot tell where the range ends")
        self.assertEqual(self.kinds["sides swapped"]["wrong"], self.kinds["sides swapped"]["any"], "an example or the direction of the load refuses each swap")
        self.assertEqual(self.kinds["other part"]["alike"], self.kinds["other part"]["wrong"], "a field of the other pad breaks what the task calls alike")
        text = self.bench.table(self.kinds)
        self.assertEqual(text[0].split(), ["damage", "wrong", "refused", *self.bench.PARTS])
        self.assertEqual(text[-3].split()[:3], ["all", str(total["wrong"]), str(total["any"])])
        self.assertEqual(text[-2:], ["  refused by one part of the check and no other: units 3, examples 22, reach 1, reads 3", "  refused by a part other than `alike`: 43 (88%)"])

    def test_damage_that_changes_no_answer_is_not_counted_as_wrong(self):
        """Two rows with one formula: reading the other changes no answer, so it is no wrong rule."""
        twin = task(lambda b: b["rows"].append({**b["rows"][2], "id": "test/drill-again"}))
        lines, kinds = self.bench.measure(reading(of=twin), {}, ["strip.hole"])
        self.assertIn(" 1 the same as the rule", lines[0])
        self.assertEqual(kinds["other row"]["wrong"], 0)

    def test_without_examples_the_check_alone_refuses_less(self):
        lines, bare = self.bench.measure(FIRST, {}, ["strip.spark"])
        self.assertEqual(len(lines), 1)
        self.assertIn("  test/spark: 12 wrong rules, 4 refused (reach 4), 0 the same as the rule; passed: add loses argument 1 in le 0 (term dropped); ", lines[0])
        self.assertTrue(lines[0].endswith("; the two sides of `le` change places (sides swapped)"), lines[0])
        self.assertEqual(sum(tally["examples"] for tally in bare.values()), 0)
        self.assertIn("  test/spark: 12 wrong rules, 10 refused (examples 10, reach 4), 0 the same as the rule", self.lines[3])


class CommandLine(unittest.TestCase):
    def run_main(self, first: dict, second: dict | None = None, examples: dict | None = None) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as folder:
            paths = {}
            for name, data in (("task", task_body()), ("first", first), ("second", second), ("examples", {"examples": examples} if examples else None)):
                if data is not None:
                    paths[name] = str(Path(folder) / f"{name}.json")
                    Path(paths[name]).write_text(json.dumps(data), encoding="utf-8")
            args = [paths["task"], paths["first"], *(["--second", paths["second"]] if second else []), *(["--examples", paths["examples"]] if examples else [])]
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(out):
                code = rule.main(args)
        return code, out.getvalue()

    def test_it_prints_each_mechanism_and_exits_by_what_it_found(self):
        code, out = self.run_main(STRIPS, STRIPS, EXAMPLES)
        self.assertEqual(code, 0, out)
        self.assertIn("strip.heat: admitted  test/heat", out)
        self.assertIn("strip.tide: admitted  (cannot arise: a strip is dry)", out)
        self.assertIn("strip.creep: left out", out)
        self.assertIn("reads        pass", out)
        damaged = copy.deepcopy(STRIPS)
        damaged["rules"][2]["le"][1] = ["q", "4.3", "mm2"]
        code, out = self.run_main(damaged, STRIPS)
        self.assertEqual(code, 1)
        self.assertIn("strip.bow: REFUSED", out)
        code, out = self.run_main({"rules": "none"})
        self.assertEqual(code, 3, out)


class FirstRun(unittest.TestCase):
    """The first run for rules: the four rules the deck shipped then, written by hand, and a second transcription of them.
    bench/formalizer/rules_a.json is that deck's file. The deck that ships now has none of the four."""

    FIRST = str(BENCH / "rules_a.json")

    @classmethod
    def setUpClass(cls):
        cls.body = json.loads((BENCH / "rules_task.json").read_text(encoding="utf-8"))
        cls.task = rule.read_task(cls.body, BENCH)
        cls.deck = json.loads(Path(cls.FIRST).read_text(encoding="utf-8"))

    def test_the_task_has_the_types_of_the_deck_of_the_time_and_asks_what_its_grid_asked(self):
        self.assertEqual(self.task.body["types"], [{**t, "loads": t.get("loads", [])} for t in self.deck["types"]])
        self.assertEqual(self.task.body["grid"], [{k: v for k, v in a.items() if k != "unless"} for a in self.deck["grid"]])
        self.assertEqual(self.task.body["rows"], self.deck["rows"])
        self.assertEqual((len(self.deck["rows"]), len(self.deck["grid"]), len(self.deck["rules"])), (18, 15, 4))

    def test_the_deck_that_ships_has_none_of_the_first_runs_rules(self):
        shipped = json.loads((grid.DECKS / "aisc360.json").read_text(encoding="utf-8"))
        self.assertEqual([r for r in self.deck["rules"] if r in shipped["rules"]], [], "the four were written by hand, and a deck's rules come from the page")

    def test_a_task_may_take_its_rows_from_several_files(self):
        """The task of the second run named two files: the deck of the time, and the 14 rows of the third formalizer run."""
        wider = rule.read_task({**self.body, "rows_from": [self.body["rows_from"], "a3.json"]}, BENCH)
        self.assertEqual(len(wider.deck.rows), len(self.deck["rows"]) + 14)
        self.assertIn("aisc360-22/J3.4-spacing", wider.deck.rows)

    def test_the_two_transcriptions_agree_on_every_mechanism_either_answers(self):
        first, other = rule.load(self.task, self.FIRST), rule.load(self.task, str(BENCH / "rules_b.json"))
        lines, whole = rule.accept(first, {}, other)
        self.assertEqual((first.stray, other.stray, whole.outcome), ([], [], "pass"))
        states = {line.mechanism: line.state for line in lines}
        self.assertEqual(sorted(m for m, state in states.items() if state == "admitted"),
                         ["lap.end_distance", "lap.ply_compression", "lap.ply_shear", "lap.ply_yield", "lap.slip", "lap.strength", "lap.tension_with_shear"])
        self.assertEqual(set(states.values()), {"admitted", "left out"})
        for line in lines:
            self.assertEqual([c.outcome for c in line.checks if c.name == "second"], ["pass"] if line.state == "admitted" else [], line.mechanism)
            self.assertEqual(line.state == "left out", not other.answers(line.mechanism), line.mechanism)
        self.assertEqual({c.outcome for line in lines for c in line.checks if c.name == "examples"}, {"none"}, "this run has no worked example")

    def second(self, mechanism: str, edit) -> rule.Check:
        """The four rules of the first run against the second transcription after an edit of it."""
        body = json.loads((BENCH / "rules_b.json").read_text(encoding="utf-8"))
        edit(body["rules"])
        first, other = rule.load(self.task, self.FIRST), rule.Reading(self.task, rule.read_transcription(body))
        return rule.second(first, other, mechanism, rule.parts(self.task, mechanism, [first, other]))

    def test_a_second_transcription_that_reads_the_clauses_another_way_is_told_apart(self):
        def weakest_bolt(rules: list) -> None:
            rules[0]["let"]["least"] = ["min", "shear", "bear_a", "bear_b", "tear_a_end", "tear_b_end", "tear_a_in", "tear_b_in"]
            rules[0]["le"][1] = ["mul", "0.75", "count", "least"]

        found = self.second("lap.strength", weakest_bolt)
        self.assertEqual(found.outcome, "fail", "the count times the weakest bolt is safe, and it is another rule")
        self.assertIn("on whether the inequality holds, and another ratio at", found.detail)
        found = self.second("lap.strength", lambda rules: rules[0].pop("where"))
        self.assertIn("the two give another answer at 18 of 132 parts, 18 on the range a rule holds in", found.detail)
        found = self.second("lap.strength", lambda rules: rules[0]["let"].__setitem__("lc_end", ["sub", "end", ["div", ["add", "dh", ["q", "1/16", "inch"]], "2"]]))
        self.assertEqual(found.outcome, "fail", "a hole a sixteenth of an inch wider, as for a net area")
        found = self.second("lap.end_distance", lambda rules: rules[1].pop("when"))
        self.assertIn("on which parts a rule answers for", found.detail)

    def test_the_same_inequality_in_another_form_is_not(self):
        found = self.second("lap.strength", lambda rules: rules[0].__setitem__("le", [["sub", ["load", "pull"], rules[0]["le"][1]], ["q", "0", "kip"]]))
        self.assertEqual(found.outcome, "pass", found.detail)
        self.assertIn("the two write the inequality in different forms: they give another ratio at 107 of the 107 parts that hold or fail, and from 32 of the first 32 each turns at the same place", found.detail)


if __name__ == "__main__":
    unittest.main()
