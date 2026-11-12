"""What a deck, a card and a design can say since three more families asked for it
(docs/deck.md, docs/format.md): a key and a count that the card states, a waiver that rests
only a cell that would be open, more units, a field that a record may leave unstated, a
quantity at or under zero, and a rule that states `lt`.

Each class takes one of them through what is accepted, what is refused and with which
finding, the cells and their states, and the reasons. Every deck here is made up: it is no
standard and its numbers mean nothing. A test reads a deck with petra/grid.py and with the
kernel and holds the two to the same refusal or the same cells. The tests of the kernel are
skipped when no kernel is built.
"""
import json
import unittest
from fractions import Fraction
from pathlib import Path

from petra import export, grid, verify
from petra.lang import LolaSyntaxError, LoweringError
from petra.units import CUSTOMARY, UNITS, Dim, UnitError, parse_quantity, readable_text
from tests.test_deck_features import (ANCHOR, HEAD, KERNEL, SIGNED, asks, cells, design, given, ill_formed, key, kind, load, made_up, no_deck, parsed, part,
                                      reads, reason, rule, size)
from tests.test_kernel_grid import ask, cell, findings

INCH = Fraction(127, 5000)
LB = Fraction(45359237, 100000000)


# --- 1. a key and a whole number that the card states ---------------------------------------------------

LIMIT = {"id": "made-up/limit", "anchor": ANCHOR, "gives": {"name": "L", "dim": "length"}, "takes": [{"name": "category", "one_of": ["A", "B", "C"]}],
         "table": {"down": {"by": "category"}, "unit": "m", "cells": ["2", "4", "6"]}}


def lifters(signed: bool = True) -> dict:
    """A beam whose category, service class and count of lugs are the card's to state, or with `signed` false the design's."""
    mark = {"signed": True} if signed else {}
    beam = kind("beam", {**key("category", "A", "B", "C"), **mark}, {**key("service", "0", "1", "2"), **mark}, key("end", "straight", "round"),
                size("lugs", "dimensionless", whole=True, least="2", **mark), size("pins", "dimensionless", whole=True), size("length"), size("Fy", "stress", signed=True),
                needs=[{"le": ["pins", "lugs"], "why": "made up: a pin for each lug at most"}])
    return made_up([beam], [asks("beam.class", "beam"), asks("beam.length", "beam"), asks("beam.lugs", "beam"), asks("beam.heavy", "beam"),
                            asks("beam.end", "beam", unless={"when": ["or", ["is", "end", "round"], ["is", "category", "C"]], "why": "made up"})],
                   [rule("class", "beam", "beam.class", when=["is", "category", "A"], requires=["is", "service", "0"]),
                    rule("length", "beam", "beam.length", le=["length", ["row", "made-up/limit", {"category": "category"}]]),
                    rule("lugs", "beam", "beam.lugs", le=[["mul", "lugs", ["q", "1", "m"]], ["mul", "pins", "length"]]),
                    rule("heavy", "beam", "beam.heavy", when=["not", ["is", "service", "0"]], lt=[["mul", "lugs", ["q", "10", "ksi"]], "Fy"]),
                    rule("end", "beam", "beam.end", le=["length", ["q", "1", "m"]])], [LIMIT])


LIFTERS = lifters()
STATES = dict(category="B", service='"1"', lugs="2")


def says(name: str, value: str) -> str:
    return f"given {name} is {value} {SIGNED}\n"


def beam(states: dict | None = None, card_more: str = "", **lines: str) -> tuple[str, str]:
    """A beam and its card: the card states what `states` holds, and the design reads each of those with a given unless `lines` says otherwise."""
    states = STATES if states is None else states
    written = {"end": "straight", "pins": "2", "length": "3 m", "Fy": "given b.Fy", **{name: f"given b.{name}" for name in states}, **lines}
    order = {name: written[name] for name in ("category", "service", "end", "lugs", "pins", "length", "Fy") if name in written}
    return design(part("beam", "b", **order)), HEAD + "".join(says(f"b.{name}", value) for name, value in states.items()) + given("b.Fy", "36 ksi") + card_more


def with_card(test: unittest.TestCase, text: str, card: str, change, rules: dict = LIFTERS) -> dict:
    """What the kernel says of the pair when card.json is changed by `change` after it is written, with the design answering the changed card."""
    deck, read = parsed(rules, text, card)
    files = grid.bundle(read, deck)
    body = json.loads(files["card"])
    change(body)
    new = export.text(body)
    return ask({**files, "card": new, "design": files["design"].replace(json.loads(files["design"])["card"], export.sha256(new))})


class StatedByTheCard(unittest.TestCase):
    def test_a_card_states_a_key_and_a_count_and_the_design_reads_them_with_a_given(self):
        text, card = beam()
        found, verdict, said = cells(self, LIFTERS, text, card)
        self.assertEqual(found, {("b", "beam.length", "length"): "proved", ("b", "beam.lugs", "lugs"): "proved", ("b", "beam.heavy", "heavy"): "proved",
                                 ("b", "beam.end", "end"): "refuted", ("b", "beam.class", ""): "open"})
        deck, read = parsed(LIFTERS, text, card)
        body = export.card(read, export.read_inputs(read), placed=True)
        self.assertEqual(body["states"], [{"name": "b.category", "by": "t@example.org", "key": "B"}, {"name": "b.lugs", "by": "t@example.org", "whole": "2"},
                                          {"name": "b.service", "by": "t@example.org", "key": "1"}])
        self.assertEqual([i["name"] for i in body["inputs"]], ["b.Fy"], "a statement is no bound, and is no input")
        lines = {line["field"]: line["args"] for line in json.loads(grid.bundle(read, deck)["design"])["parts"][0]["lines"]}
        self.assertEqual((lines["category"], lines["lugs"]), ([{"given": "b.category"}], [{"given": "b.lugs"}]))

    def test_the_hash_of_the_card_covers_what_it_states(self):
        hashes = set()
        for states in (STATES, {**STATES, "category": "C"}, {**STATES, "lugs": "3"}, {**STATES, "service": '"2"'}):
            deck, read = parsed(LIFTERS, *beam(states, pins="2"))
            hashes.add(export.sha256(grid.bundle(read, deck)["card"]))
        self.assertEqual(len(hashes), 4)
        text, card = beam()
        deck, read = parsed(LIFTERS, text, card)
        self.assertNotIn("states", json.loads(grid.bundle(parsed(PACKS, *pack())[1], grid.read_deck(json.dumps(PACKS)))["card"]), "a card that states none has no such key")

    def test_whatever_reads_the_field_reads_it_the_same_whoever_stated_it(self):
        """A `when`, a `requires`, an `unless`, a key of a table, a rule on the count and a need: the cells of a beam whose card states the
        three fields are the cells of the same beam under a deck that leaves them to the design."""
        for states in (STATES, dict(category="A", service='"0"', lugs="2"), dict(category="A", service='"2"', lugs="3"), dict(category="C", service='"0"', lugs="4")):
            with self.subTest(states):
                pins = dict(pins=states["lugs"])
                by_card, verdict, _ = cells(self, LIFTERS, *beam(states, **pins))
                by_design, same, _ = cells(self, lifters(False), *beam({}, **states, **pins))
                self.assertEqual((by_card, verdict), (by_design, same))
        found, verdict, _ = cells(self, LIFTERS, *beam(dict(category="A", service='"2"', lugs="3"), pins="3"))
        self.assertEqual((found["b", "beam.class", "class"], found["b", "beam.heavy", "heavy"], verdict), ("refuted", "proved", "FAIL"))
        found, _, _ = cells(self, LIFTERS, *beam(dict(category="C", service='"0"', lugs="4"), pins="4"))
        self.assertEqual((found["b", "beam.end", ""], found["b", "beam.length", "length"]), ("not_applicable", "proved"))

    def test_a_key_that_is_not_signed_may_be_stated_by_either(self):
        text, card = beam({**STATES, "end": "round"})
        found, _, _ = cells(self, LIFTERS, text, card)
        self.assertEqual(found["b", "beam.end", ""], "not_applicable", "the card states the end, which the type leaves to either")
        text, card = beam({**STATES, "pins": "2"})
        found, _, _ = cells(self, LIFTERS, text, card)
        self.assertEqual(found["b", "beam.lugs", "lugs"], "proved")

    def test_a_design_that_writes_a_field_of_the_cards_is_refused(self):
        for lines, finding in ((dict(category="B"), "parts.4 design b.category: is for the card to state: the design reads it with a given"),
                               (dict(category='"B"'), "parts.4 design b.category: is for the card to state"),
                               (dict(service='"1"'), "parts.4 design b.service: is for the card to state"),
                               (dict(lugs="2"), "parts.3 design b.lugs: is for the card to state: the design reads it with a given")):
            with self.subTest(lines):
                states = {name: value for name, value in STATES.items() if name not in lines}
                mine, its = ill_formed(self, LIFTERS, *beam(states, **lines))
                self.assertIn(finding, its)
                self.assertIn("is for the card to state", mine)
                with self.assertRaises(LoweringError) as unread:      # the card states it too: then no part reads what the card states
                    parsed(LIFTERS, *beam(STATES, **lines))
                self.assertIn("and no component reads it", str(unread.exception))

    def test_a_design_cannot_read_a_statement_under_another_name(self):
        for lines, card_more, finding in (
                (dict(category="given b.service"), "", "parts.4 design b.category: reads the given b.service, and a part reads only what the card states for it, b.category"),
                (dict(category="given c.category"), says("c.category", "A"), "parts.4 design b.category: reads the given c.category"),
                (dict(lugs="given b.pins", pins="2"), says("b.pins", "5"), "parts.3 design b.lugs: reads the given b.pins"),
                (dict(category="given b.category B"), "", "parts.4 design b.category: takes one name, or one given"),
                (dict(category="given b.category given b.category"), "", "parts.4 design b.category: takes one name, or one given")):
            with self.subTest(lines):
                text, card = beam(**lines)
                for name, value in STATES.items():      # the card states only what the design reads: the language refuses a statement nothing reads
                    if f"given b.{name}" not in text:
                        card = card.replace(says(f"b.{name}", value), "")
                mine, its = ill_formed(self, LIFTERS, text, card + card_more)
                self.assertIn(finding, its)
        text, card = beam()
        for change in (("category given", "Category given"), ("category given b.category", "category given b.Category")):
            with self.subTest(change):
                with self.assertRaises((LoweringError, grid.ComponentError)):
                    deck, read = parsed(LIFTERS, text.replace(*change), card)
                    grid.check(read, deck)

    def test_a_card_that_does_not_state_it_leaves_the_design_refused_by_name(self):
        text, card = beam()
        with self.assertRaises(LoweringError) as refused:
            parsed(LIFTERS, text, card.replace(says("b.category", "B"), ""))
        self.assertIn("b.category: the card gives no 'b.category'", str(refused.exception))
        if verify.binary():
            said = with_card(self, text, card, lambda body: body["states"].pop(0))
            self.assertEqual((said["verdict"], findings(said)), ("ILL-FORMED", "parts.4 design b.category: the card states no b.category"))
            said = with_card(self, text, card, lambda body: body.pop("states"))
            self.assertEqual(findings(said).count("the card states no b."), 3)
            said = with_card(self, text, card, lambda body: body["states"].__setitem__(1, {"name": "b.lugs", "by": "t@example.org", "key": "2"}))
            self.assertIn("parts.3 design b.lugs: the card states a name for b.lugs, and it is a count", findings(said))

    def test_a_card_states_one_of_the_names_and_a_count_within_its_floor(self):
        for states, finding in (({**STATES, "category": "D"}, "parts.4 design b.category: is one of: A, B, C"), ({**STATES, "category": '"b"'}, "parts.4 design b.category: is one of: A, B, C"),
                                ({**STATES, "service": "1"}, "parts.4 design b.service: the card states a whole number for b.service, and it is a key"),
                                ({**STATES, "category": "2"}, "parts.4 design b.category: the card states a whole number"),
                                ({**STATES, "lugs": "two"}, "parts.3 design b.lugs: the card states a name for b.lugs, and it is a count"),
                                ({**STATES, "lugs": '"2"'}, "parts.3 design b.lugs: the card states a name for b.lugs"),
                                ({**STATES, "lugs": "1"}, "parts.3 design b.lugs: is under the least its field may take"),
                                ({**STATES, "lugs": "0"}, "parts.3 design b.lugs: is not more than zero"), ({**STATES, "lugs": "-2"}, "parts.3 design b.lugs: is not more than zero")):
            with self.subTest(states):
                mine, its = ill_formed(self, LIFTERS, *beam(states))
                self.assertIn(finding, its)
        mine, its = ill_formed(self, LIFTERS, *beam(pins="3"))
        self.assertIn("parts.9 design b: breaks need 1 of a beam: its left side, 3, is not at most its right side, 2", its, "a need reads the count the card states")
        found, _, _ = cells(self, LIFTERS, *beam({**STATES, "lugs": "+3"}, pins="3"))
        self.assertEqual(found["b", "beam.lugs", "lugs"], "proved")

    def test_a_bound_is_no_statement_and_a_statement_no_bound(self):
        text, card = beam()
        for old, new, finding in ((says("b.category", "B"), given("b.category", "1", "2"), "parts.4 design b.category: b.category is a bound of the card, and a key or a count is stated exactly"),
                                  (says("b.lugs", "2"), given("b.lugs", "2", "2"), "parts.3 design b.lugs: b.lugs is a bound of the card, and a key or a count is stated exactly"),
                                  (given("b.Fy", "36 ksi"), says("b.Fy", "36"), "parts.3 design b.Fy: b.Fy is stated exactly by the card, and a quantity that is no count reads a bound")):
            with self.subTest(new):
                mine, its = ill_formed(self, LIFTERS, text, card.replace(old, new))
                self.assertIn(finding, its)

    def test_the_card_language_reads_is_with_a_name_a_text_or_a_whole_number_and_a_signature(self):
        text, card = beam()
        for value in ("B", '"B"', '"a name with spaces"', "2", "+2", "-2", "0", "kN", "h", "K", "unstated"):
            with self.subTest(value):
                try:
                    parsed(LIFTERS, text, card.replace(says("b.category", "B"), says("b.category", value)))
                except grid.ComponentError:
                    pass
        for value in ("2.5", "1/2", "2 mm", "2 %", "B C", "", "signed", "in", "given", "[A, B]", "(A)", "b.category", "A.B", "is B", '"B" "C"', "2 3"):
            with self.subTest(value):
                with self.assertRaises(LolaSyntaxError):
                    parsed(LIFTERS, text, card.replace(says("b.category", "B"), says("b.category", value)))
        for line in ("given b.category is B\n", 'given b.category is B signed "" source "x"\n', 'given b.category is B signed "x" source ""\n',
                     "given b.category is B mean 2 " + SIGNED + "\n", says("b.category", "B") + says("b.category", "C"), says("b.category", "B") + given("b.category", "1")):
            with self.subTest(line):
                with self.assertRaises((LoweringError, LolaSyntaxError)):
                    parsed(LIFTERS, text, card.replace(says("b.category", "B"), line))
        measured = card.replace(says("b.category", "B"), 'given b.category is B measured "lab@example.org" source "a report"\n')
        (first, *_) = export.card(parsed(LIFTERS, text, measured)[1], [], placed=True)["states"]
        self.assertEqual(first, {"name": "b.category", "by": "lab@example.org", "key": "B"})

    def test_a_component_of_the_models_reads_no_exact_statement(self):
        from petra.lang import parse_design
        from petra.registry import build_registry

        card = 'petra 0\n\ncard "hook" {\n  owner "t@example.org"\n}\n' + says("capacity", "5")
        with self.assertRaises(LoweringError) as refused:
            parse_design(card, "petra 0\n\ndemand hook {\n  capacity given capacity\n}\n", "hook.petra", build_registry())
        self.assertIn("only a part of a deck's type reads such a given", str(refused.exception))

    @KERNEL
    def test_a_card_json_that_states_what_no_part_reads_twice_or_under_an_inputs_name_is_refused(self):
        text, card = beam()
        stray = {"name": "nobody.category", "by": "t@example.org", "key": "B"}
        for change, finding in ((lambda b: b["states"].append(stray), "parts.6 card nobody.category: is stated, and no part reads it"),
                                (lambda b: b["states"].append({**stray, "name": "b.end"}), "parts.6 card b.end: is stated, and no part reads it"),
                                (lambda b: b["states"].append(dict(b["states"][0])), "parts.6 card b.category: two statements have this name"),
                                (lambda b: b["states"].append({**b["states"][0], "key": "C"}), "parts.4 design b.category: the card states b.category twice"),
                                (lambda b: b["states"].append({"name": "b.Fy", "by": "t@example.org", "key": "B"}), "parts.6 card b.Fy: is the name of a statement and of an input"),
                                (lambda b: b["inputs"].append({"name": "b.category", "dim": "dimensionless", "lo": "1", "hi": "1", "by": "x"}), "parts.6 card b.category: is the name of a statement and of an input"),
                                (lambda b: b["states"][0].update(by=""), "types.5 card b.category: the statement names no by"),
                                (lambda b: b["states"][0].pop("by"), "types.5 card b.category: the statement names no by"),
                                (lambda b: b["states"][0].update(whole="2"), "shape card states[0]: a statement has one of key, a text, and whole"),
                                (lambda b: b["states"][0].pop("key"), "shape card states[0]: a statement has one of key"),
                                (lambda b: b["states"][0].update(key=2), "shape card states[0]: a statement has one of key"),
                                (lambda b: b["states"][1].update(whole="2.5"), "shape card states[1]: whole: not a canonical rational"),
                                (lambda b: b["states"][1].update(whole="5/2"), "shape card states[1]: whole is not a whole number"),
                                (lambda b: b["states"][1].update(whole="02"), "shape card states[1]: whole: "),
                                (lambda b: b["states"][1].update(whole=2), "shape card states[1]: a statement has one of key"),
                                (lambda b: b["states"][0].update(case="x"), "shape card states[0]: a statement has name, by and one of key and whole, and no case"),
                                (lambda b: b.update(states={}), "shape card : states is not a list")):
            with self.subTest(finding):
                said = with_card(self, text, card, change)
                self.assertEqual(said["verdict"], "ILL-FORMED")
                self.assertIn(finding, findings(said))

    @KERNEL
    def test_a_card_that_states_a_key_is_a_card_for_a_deck_of_rules(self):
        """Type rule 7: with a design stripped of its parts, or with no deck of rules, the kernel refuses the card for its `states`."""
        deck, read = parsed(LIFTERS, *beam())
        files = grid.check(read, deck)[1]
        stripped = json.loads(files["design"])
        del stripped["parts"]
        said = ask({**files, "design": json.dumps(stripped)}, without=("rules",))
        self.assertIn("types.7 card states: is a key of the card, which only a design checked against a deck of rules has", findings(said))


# --- 2. a waiver rests only a cell that would be open ---------------------------------------------------

STEP = {"id": "made-up/step", "anchor": ANCHOR, "gives": {"name": "c", "dim": "force"}, "takes": [{"name": "w", "dim": "length", "range": ["1 mm", "20 mm"]}],
        "table": {"down": {"by": "w", "at": ["5 mm", "10 mm"]}, "unit": "N", "cells": ["50", "100"]}}
JOINT = kind("joint", size("w"), size("cap", "force"), key("grade", "a", "b"), size("rating", "force", optional=True),
             loads=[{"name": "pull", "dim": "force", "least": "0 N", "what": "a pull"}])
JOINTS = made_up([JOINT], [asks("j.none", "joint"), asks("j.size", "joint"), asks("j.pull", "joint"), asks("j.range", "joint"), asks("j.table", "joint"),
                           asks("j.cannot", "joint", unless={"when": ["is", "grade", "b"], "why": "made up: grade b has none"}), asks("j.grade", "joint"),
                           asks("j.two", "joint"), asks("j.rated", "joint")],
                 [rule("size", "joint", "j.size", le=["w", ["q", "10", "mm"]]),
                  rule("pull", "joint", "j.pull", le=[["load", "pull"], "cap"]),
                  rule("range", "joint", "j.range", le=["w", ["q", "12", "mm"]], where=[{"le": [["q", "6", "mm"], "w"], "why": "made up: at least 6 mm wide"}]),
                  rule("table", "joint", "j.table", le=[["row", "made-up/step", {"w": "w"}], "cap"]),
                  rule("cannot", "joint", "j.cannot", le=["w", ["q", "1", "mm"]]),
                  rule("grade", "joint", "j.grade", when=["is", "grade", "b"], le=["w", ["q", "8", "mm"]]),
                  rule("first", "joint", "j.two", le=["w", ["q", "20", "mm"]]), rule("second", "joint", "j.two", lt=[["load", "pull"], ["q", "40", "N"]]),
                  rule("rated", "joint", "j.rated", le=["cap", "rating"])], [STEP])
LINES = [a["mechanism"] for a in JOINTS["grid"]]
BY = 'by "w@example.org" reason "tested apart"'


def joint(waive: list[str] | None = None, cases: str | None = None, **lines: str) -> tuple[str, str]:
    """A joint and its card. The card waives every line of the grid unless `waive` names the lines, and has two load cases unless `cases` gives them."""
    written = {"w": "10 mm", "cap": "100 N", "grade": "a", "rating": "150 N", **lines}
    cases = load("calm", "p pull in [0 N, 30 N]") + load("gale", "p pull in [0 N, 90 N]") if cases is None else cases
    return design(part("joint", "p", **written)), HEAD + cases + "".join(f"\nwaive {m} on p {BY}\n" for m in (LINES if waive is None else waive))


class AWaiverRestsWhatIsOpen(unittest.TestCase):
    def test_a_waived_line_keeps_what_its_rules_prove_and_refute_and_rests_what_is_open(self):
        """Every line of the grid is waived. The cells are the cells of the same joint with no waiver, but that each open one is waived."""
        bare, bare_verdict, _ = cells(self, JOINTS, *joint([]))
        found, verdict, said = cells(self, JOINTS, *joint())
        self.assertEqual(bare, {("p", "j.none", ""): "open", ("p", "j.size", "size"): "proved", ("p", "j.pull", "pull/calm"): "proved", ("p", "j.pull", "pull/gale"): "proved",
                                ("p", "j.range", "range/where"): "proved", ("p", "j.range", "range"): "proved", ("p", "j.table", "table"): "proved",
                                ("p", "j.cannot", "cannot"): "refuted", ("p", "j.grade", ""): "open", ("p", "j.two", "first"): "proved",
                                ("p", "j.two", "second/calm"): "proved", ("p", "j.two", "second/gale"): "refuted", ("p", "j.rated", "rated"): "proved"})
        self.assertEqual(found, {k: "waived" if v == "open" else v for k, v in bare.items()})
        self.assertEqual((bare_verdict, verdict), ("FAIL", "FAIL"), "no waiver hides a refutation")
        self.assertEqual(list(found), list(bare), "each cell keeps its place and its entry")

    def test_each_way_a_cell_is_open_is_a_way_it_is_waived_and_its_reason_says_which(self):
        for lines, cases, mechanism, entry, was in (
                ({}, None, "j.none", "", "the deck has no rule for it"),
                ({}, None, "j.grade", "", "the deck has no rule for it on a part like this one"),
                ({}, load("calm", "p pull in [0 N, 30 N]") + load("idle"), "j.pull", "pull/idle", "case idle puts no pull on p, which the rule reads"),
                ({}, "", "j.pull", "pull", "the card puts no pull on p, which the rule reads"),
                (dict(w="5 mm"), None, "j.range", "range", "the range the rule holds in is not proved: "),
                (dict(w="7 mm"), None, "j.table", "table", ""),      # between the two widths the table lists, where it has no value
                (dict(rating="unstated"), None, "j.rated", "rated", "p.rating is unstated: its maker states none, and the rule reads it")):
            with self.subTest(mechanism=mechanism, entry=entry):
                found, _, said = cells(self, JOINTS, *joint(cases=cases, **lines))
                self.assertEqual(found["p", mechanism, entry], "waived")
                if verify.binary():
                    self.assertTrue(reason(said, mechanism, entry).startswith("open but for the waiver: " + was), reason(said, mechanism, entry))
                bare, _, _ = cells(self, JOINTS, *joint([], cases=cases, **lines))
                self.assertEqual(bare["p", mechanism, entry], "open")
        found, _, _ = cells(self, JOINTS, *joint(w="5 mm"))
        self.assertNotIn(("p", "j.range", "range/where"), found, "a range that is not proved has no cell of its own, waived or not")

    def test_a_line_that_cannot_arise_stays_so_under_a_waiver(self):
        found, _, _ = cells(self, JOINTS, *joint(grade="b", w="8 mm"))
        self.assertEqual((found["p", "j.cannot", ""], found["p", "j.grade", "grade"]), ("not_applicable", "proved"))

    def test_a_waiver_for_a_line_whose_every_cell_is_proved_rests_nothing_and_is_not_listed(self):
        text, card = joint(["j.size", "j.table", "j.none", "j.grade"], w="10 mm")
        found, verdict, said = cells(self, JOINTS, text, card)
        self.assertEqual((found["p", "j.size", "size"], found["p", "j.table", "table"], found["p", "j.none", ""]), ("proved", "proved", "waived"))
        if verify.binary():
            self.assertEqual([w["mechanism"] for w in said["waived"]], ["j.none", "j.grade"], "the waivers of j.size and j.table rest no cell")
            self.assertEqual(said["counts"]["waived"], 2)

    def test_the_verdict_when_every_open_cell_is_waived(self):
        """PASS when something is proved and nothing refuted. UNKNOWN when nothing is proved: waived is a state of its own, and is never counted as proved."""
        calm = load("calm", "p pull in [0 N, 30 N]")
        passing = dict(w="10 mm", grade="b", cap="100 N")
        found, verdict, said = cells(self, JOINTS, *joint(cases=calm, **{**passing, "w": "8 mm"}))
        self.assertEqual((verdict, sorted(set(found.values()))), ("PASS", ["not_applicable", "proved", "waived"]))
        found, verdict, _ = cells(self, JOINTS, *joint(["j.size", "j.pull", "j.range", "j.table", "j.grade", "j.two", "j.rated"], cases=calm, **{**passing, "w": "8 mm"}))
        self.assertEqual((verdict, found["p", "j.none", ""]), ("UNKNOWN", "open"), "one open cell that no waiver rests")
        nothing = made_up([JOINT], [asks("j.none", "joint"), asks("j.rated", "joint")], [rule("rated", "joint", "j.rated", le=["cap", "rating"])])
        found, verdict, _ = cells(self, nothing, *joint(["j.none", "j.rated"], cases="", rating="unstated"))
        self.assertEqual((verdict, set(found.values()) - {"open"}), ("UNKNOWN", {"waived"}), "every line is waived and nothing is proved")

    def test_the_report_says_who_signed_and_what_was_open(self):
        deck, read = parsed(JOINTS, *joint())
        report, _ = grid.check(read, deck)
        (none,) = [c for c in report.cells if c.mechanism == "j.none"]
        self.assertEqual((none.state, none.why), ("waived", "by w@example.org: tested apart; open but for the waiver: the deck has no rule for it"))
        self.assertIn("  p/j.none    waived", report.render())

    def test_the_first_waiver_of_a_line_is_the_one_a_cell_rests_on(self):
        text, card = joint(["j.none"])
        found, _, said = cells(self, JOINTS, text, card + '\nwaive j.none on p by "second@example.org" reason "again"\n')
        self.assertEqual(found["p", "j.none", ""], "waived")
        if verify.binary():
            self.assertEqual([(w["mechanism"], w["by"]) for w in said["waived"]], [("j.none", "w@example.org")])

    def test_a_cell_named_unread_takes_no_waiver(self):
        spare = made_up([kind("joint", size("w"), size("spare"))], [asks("j.size", "joint")], [rule("size", "joint", "j.size", le=["w", ["q", "10", "mm"]])])
        text = design(part("joint", "p", w="1 mm", spare="1 mm"))
        with self.assertRaises((LoweringError, grid.ComponentError)):
            deck, read = parsed(spare, text, HEAD + f"\nwaive unread on p {BY}\n")
            grid.check(read, deck)
        found, verdict, _ = cells(self, spare, text, HEAD + f"\nwaive j.size on p {BY}\n")
        self.assertEqual((found["p", "unread", "spare"], verdict), ("open", "UNKNOWN"))

    @KERNEL
    def test_a_hint_and_a_waiver_aimed_at_one_cell(self):
        """The cell of j.size on a waived line, with a width the card bounds. The hint that proves it makes it proved, the point that refutes
        it makes it refuted, and with no hint that settles it the cell is open, which the waiver rests. The state a hint claims decides nothing."""
        text, card = joint(["j.size"], w="given p.w")
        label = "in:made-up.p.w"
        for lo, hi, hint, state in (("5 mm", "10 mm", dict(state="proved", partition="leaf"), "proved"),
                                    ("5 mm", "10 mm", dict(state="refuted", point={label: "1/100"}), "waived"),
                                    ("5 mm", "10 mm", dict(state="waived"), "waived"), ("5 mm", "10 mm", dict(state="open", why="x"), "waived"),
                                    ("5 mm", "11 mm", dict(state="proved", partition="leaf"), "waived"),
                                    ("5 mm", "11 mm", dict(state="refuted", point={label: "11/1000"}), "refuted"),
                                    ("5 mm", "11 mm", dict(state="proved", point={label: "11/1000"}), "refuted"),
                                    ("5 mm", "11 mm", dict(state="refuted", point={label: "1/100"}), "waived"),
                                    ("5 mm", "11 mm", dict(state="refuted", point={label: "3/250"}), "waived")):
            with self.subTest(lo=lo, hi=hi, hint=hint):
                its = hinted(self, JOINTS, text, card + given("p.w", lo, hi), "j.size", "p", **hint)
                self.assertEqual(its["state"], state)
                self.assertEqual(its.get("reason", "").startswith("open but for the waiver: "), state == "waived")
        deck, read = parsed(JOINTS, text, card + given("p.w", "5 mm", "11 mm"))
        report, files = grid.check(read, deck)
        self.assertEqual(next(c.state for c in report.cells if c.mechanism == "j.size"), "refuted", "petra check finds the corner at 11 mm, and no waiver rests it")
        said = ask(files, without=("proofs",))
        self.assertEqual(cell(said, "j.size")["state"], "waived", "with no proofs.json nothing settles the cell, and the waiver rests it: the kernel does not search")


# --- 3. more units --------------------------------------------------------------------------------------

NEW_UNITS = {
    "kW": (Fraction(1000), Dim(m=2, kg=1, s=-3)), "min": (Fraction(60), Dim(s=1)), "h": (Fraction(3600), Dim(s=1)),
    "Hz": (Fraction(1), Dim(s=-1)), "rpm": (Fraction(1, 60), Dim(s=-1)),
    "mAh": (Fraction(18, 5), Dim(s=1, A=1)), "Ah": (Fraction(3600), Dim(s=1, A=1)),
    "m/s": (Fraction(1), Dim(m=1, s=-1)), "km/h": (Fraction(5, 18), Dim(m=1, s=-1)), "knot": (Fraction(1852, 3600), Dim(m=1, s=-1)),
    "mph": (Fraction(1609344, 3600000), Dim(m=1, s=-1)), "mile": (Fraction(1609344, 1000), Dim(m=1)),
    "kg/m3": (Fraction(1), Dim(m=-3, kg=1)), "g/cm3": (Fraction(1000), Dim(m=-3, kg=1)), "N/mm": (Fraction(1000), Dim(kg=1, s=-2)),
    "lb": (LB, Dim(kg=1)), "oz": (LB / 16, Dim(kg=1)),
    "lbf_in": (LB * Fraction(980665, 100000) * INCH, Dim(m=2, kg=1, s=-2)), "lbf_ft": (LB * Fraction(980665, 100000) * 12 * INCH, Dim(m=2, kg=1, s=-2)),
}
"""Each unit read since 2026-11-11, with its factor to SI as a fraction worked out here from its definition, and its dimension."""

SAME = [(("60", "rpm"), ("1", "Hz")), (("1000", "mAh"), ("1", "Ah")), (("1", "Ah"), ("3600", "A2s")), (("3.6", "km/h"), ("1", "m/s")), (("3600", "knot"), ("1852", "m/s")),
        (("1", "mph"), ("0.44704", "m/s")), (("1", "mile"), ("5280", "ft")), (("1", "h"), ("60", "min")), (("1", "min"), ("60000", "ms")), (("16", "oz"), ("1", "lb")),
        (("1", "lb"), ("453.59237", "g")), (("1", "g/cm3"), ("1000", "kg/m3")), (("12", "lbf_in"), ("1", "lbf_ft")), (("1", "lbf_ft"), ("0.001", "kip_ft")),
        (("1", "kW"), ("1000", "W"))]
"""Pairs of values that are one quantity. `A2s` is a current squared for a time, so the third pair is of two dimensions and is refused."""

MOTOR = kind("motor", size("speed", "dimensionless/time"), size("charge", "current*time"), size("pace", "length/time"), size("run", "time"), size("h", "time"),
             size("mass", "mass"), size("density", "mass/length^3"), size("rate", "force/length"), size("torque", "moment"), size("power", "power"),
             size("reach", "length"), key("grade", "K", "L"))
MOTORS = made_up([MOTOR], [asks("motor.units", "motor")],
                 [rule(f"same-{n}-{way}", "motor", "motor.units", le=[["q", *(a if way == "up" else b)], ["q", *(b if way == "up" else a)]])
                  for n, (a, b) in enumerate(SAME) if n != 2 for way in ("up", "down")])
SPIN = dict(speed="9000 rpm", charge="2200 mAh", pace="54 km/h", run="12 min", h="2 h", mass="1.5 lb", density="1.6 g/cm3", rate="3 N/mm", torque="20 lbf_in",
            power="1.2 kW", reach="0.5 mile", grade="K")


class MoreUnits(unittest.TestCase):
    def test_each_new_unit_has_its_exact_factor_and_its_dimension(self):
        table = {**UNITS, **CUSTOMARY}
        for unit, (factor, dim) in NEW_UNITS.items():
            with self.subTest(unit):
                q = parse_quantity("1", unit)
                self.assertEqual((q.value.lo, q.dim), (factor, dim))
                self.assertEqual(table[unit], (factor, dim))
                self.assertIsInstance(table[unit][0], Fraction, "a factor is a fraction and never a float")
        self.assertEqual(parse_quantity("1", "knot").value.lo, Fraction(463, 900))
        self.assertEqual(parse_quantity("1", "mph").value.lo, Fraction(1397, 3125))
        self.assertEqual(parse_quantity("9000", "rpm").value.lo, 150, "150 turns a second")
        self.assertEqual(parse_quantity("2200", "mAh").value.lo, 7920, "7,920 ampere seconds")

    def test_no_unit_that_had_a_spelling_got_a_second_one(self):
        for unit in ("N.m", "N_m", "lbf.ft", "lbf.in", "lbf_inch", "lbs", "lbm", "hr", "hour", "minute", "sec", "RPM", "hz", "kph", "kmh", "kn", "kt", "mi", "kg/m^3",
                     "g/cc", "K", "degK", "degF", "F", "C", "kelvin", "rpm^2", "Hz^2", "m/s^2", "h^2", "mm/s", "m/min", "m/h", "ft/s", "N/m", "kN/m", "kWh", "Wh", "mAs"):
            with self.subTest(unit):
                self.assertRaises(UnitError, parse_quantity, "1", unit)
        self.assertEqual(parse_quantity("1", "mile^2"), parse_quantity("2589988.110336", "m2"), "a mile is a unit of length, so it takes a power")

    def test_a_report_still_prints_a_time_in_seconds_and_a_power_in_watts(self):
        self.assertEqual(readable_text(parse_quantity("7200", "s")), "7200 s")
        self.assertEqual(readable_text(parse_quantity("5", "kW")), "5000 W")
        self.assertEqual(readable_text(parse_quantity("9000", "rpm")), "150 Hz")
        self.assertEqual(readable_text(parse_quantity("54", "km/h")), "15 m/s")
        self.assertEqual(readable_text(parse_quantity("1.6", "g/cm3")), "1.6 g/cm3")

    def test_the_language_reads_each_new_unit_in_a_design_and_in_a_card(self):
        deck, read = parsed(MOTORS, design(part("motor", "m", **{**SPIN, "run": "given m.run"})), HEAD + given("m.run", "12 min", "0.5 h"))
        written = {q["field"]: q for q in export.design_file(read, "", deck=True)["quantities"]}
        expected = {"speed": ("s^-1", 150), "charge": ("s^1 A^1", 7920), "pace": ("m^1 s^-1", 15), "h": ("time", 7200), "mass": ("mass", Fraction(3, 2) * LB),
                    "density": ("m^-3 kg^1", 1600), "rate": ("kg^1 s^-2", 3000), "torque": ("energy", 20 * NEW_UNITS["lbf_in"][0]), "power": ("power", 1200),
                    "reach": ("length", Fraction(804672, 1000))}
        self.assertEqual({name: (q["dim"], Fraction(q["lo"])) for name, q in written.items()}, expected)
        (run,) = export.card(read, export.read_inputs(read), placed=True)["inputs"]
        self.assertEqual((run["dim"], run["lo"], run["hi"]), ("time", "720", "1800"))

    def test_pairs_of_values_that_are_one_quantity_are_one_to_the_kernel_and_to_the_grid(self):
        found, verdict, said = cells(self, MOTORS, design(part("motor", "m", **SPIN)))
        units = {k: v for k, v in found.items() if k[1] == "motor.units"}
        self.assertEqual((len(units), set(units.values())), (2 * (len(SAME) - 1), {"proved"}))
        mine, its = no_deck(self, made_up([MOTOR], [asks("motor.units", "motor")], [rule("charge", "motor", "motor.units", le=[["q", *SAME[2][0]], ["q", *SAME[2][1]]])]))
        self.assertIn("`le` compares two dimensions", its)

    def test_a_unit_is_read_whole_and_never_from_its_halves(self):
        """`m/s` beside `m` and `s`, `mAh` beside `m`, `A` and `h`, `min` beside `m` and `in`, and `h` beside a field named `h`."""
        for field, value, dim, si in (("pace", "3 m/s", "m^1 s^-1", 3), ("charge", "3 mAh", "s^1 A^1", Fraction(54, 5)), ("run", "3 min", "time", 180), ("h", "3 h", "time", 10800),
                                      ("run", "3 h", "time", 10800), ("h", "3 min", "time", 180), ("run", "3 s", "time", 3), ("reach", "3 m", "length", 3)):
            with self.subTest(field=field, value=value):
                _, read = parsed(MOTORS, design(part("motor", "m", **{**SPIN, field: value})))
                (q,) = [q for q in export.design_file(read, "", deck=True)["quantities"] if q["field"] == field]
                self.assertEqual((q["dim"], Fraction(q["lo"])), (dim, si))
        for field, value in (("pace", "3 m"), ("pace", "3 s"), ("charge", "3 A"), ("charge", "3 h"), ("charge", "3 mA"), ("run", "3 m"), ("run", "3 inch"), ("speed", "3 s")):
            with self.subTest(field=field, value=value):
                _, its = ill_formed(self, MOTORS, design(part("motor", "m", **{**SPIN, field: value})))
                self.assertIn(f"parts.3 design m.{field}: is a ", its)

    def test_a_unit_with_a_space_or_another_mark_in_it_is_no_unit(self):
        for value in ("3 m /s", "3 m/ s", "3 m / s", "3 m/2", "3 /s", "3 m//s", "3 m/s/s", "3 m.s", "3 kg/m^3"):
            with self.subTest(value):
                with self.assertRaises((LolaSyntaxError, LoweringError)):
                    parsed(MOTORS, design(part("motor", "m", **{**SPIN, "pace": value})))
        for value in ("3 m in", "3 mA h", "3 m A h"):
            with self.subTest(value):
                with self.assertRaises((LolaSyntaxError, LoweringError, grid.ComponentError)):
                    grid.check(parsed(MOTORS, design(part("motor", "m", **{**SPIN, "charge": value})))[1], grid.read_deck(json.dumps(MOTORS)))

    def test_k_is_a_name_of_a_key_and_no_unit(self):
        found, _, _ = cells(self, MOTORS, design(part("motor", "m", **SPIN)))
        self.assertIn(("m", "unread", "grade"), found)
        with self.assertRaises(LoweringError) as refused:
            parsed(MOTORS, design(part("motor", "m", **{**SPIN, "run": "5 K"})))
        self.assertIn("unknown unit 'K'", str(refused.exception))
        _, its = ill_formed(self, MOTORS, design(part("motor", "m", **{**SPIN, "grade": "5 h"})))
        self.assertIn("parts.4 design m.grade: takes one name", its)

    def test_a_deck_reads_the_units_wherever_it_reads_a_value(self):
        row = {"id": "made-up/limit", "anchor": ANCHOR, "gives": {"name": "v", "dim": "length/time"},
               "takes": [{"name": "n", "dim": "dimensionless/time", "range": ["60 rpm", "200 Hz"]}],
               "table": {"down": {"by": "n", "bands": [["0 rpm", "6000 rpm"], ["100 Hz", None]], "closed": "upper"}, "unit": "km/h", "cells": ["36", "20 m/s"]}}
        rotor = kind("rotor", size("speed", "dimensionless/time", least="60 rpm"), size("pace", "length/time"))
        deck = made_up([rotor], [asks("rotor.pace", "rotor")], [rule("pace", "rotor", "rotor.pace", le=["pace", ["row", "made-up/limit", {"n": "speed"}]])], [row])
        for speed, pace, state in (("6000 rpm", "10 m/s", "proved"), ("6000 rpm", "36.1 km/h", "refuted"), ("100.001 Hz", "72 km/h", "proved"), ("6001 rpm", "20.1 m/s", "refuted")):
            with self.subTest(speed=speed, pace=pace):
                found, _, _ = cells(self, deck, design(part("rotor", "r", speed=speed, pace=pace)))
                self.assertEqual(found["r", "rotor.pace", "pace"], state)
        _, its = ill_formed(self, deck, design(part("rotor", "r", speed="59 rpm", pace="1 m/s")))
        self.assertIn("parts.3 design r.speed: is under the least its field may take", its)
        for change in (lambda b: b["rows"][0]["table"].update(unit="km/hr"), lambda b: b["rows"][0]["takes"][0].update(range=["60 rpm", "200 hz"]),
                       lambda b: b["types"][0]["fields"][0].update(least="1 m/s"), lambda b: b["rows"][0]["table"]["down"]["bands"][0].__setitem__(1, "6000 mph")):
            body = json.loads(json.dumps(deck))
            change(body)
            no_deck(self, body)


# --- 4. a field that a record may leave unstated --------------------------------------------------------

ROTOR = kind("rotor_set", size("thrust", "force"), size("speed_limit", "dimensionless/time", optional=True), size("thrust_limit", "force", optional=True),
             {**key("balance", "static", "dynamic"), "optional": True}, {**key("guard", "none", "full"), "optional": True}, size("mass", "mass", optional=True),
             size("blades", "dimensionless", whole=True, optional=True), key("grain", "along", "unstated"),
             needs=[{"le": ["thrust", "thrust_limit"], "why": "made up: the thrust is within what the maker allows"}])
QUAD = kind("quad", size("speed", "dimensionless/time"), {"name": "sets", "type": "rotor_set", "as": ["rotor"], "what": "its rotor sets"},
            loads=[{"name": "pull", "dim": "force", "least": "0 N", "what": "the thrust asked of a rotor"}],
            needs=[{"lt": ["speed", ["mul", "2", "rotor.speed_limit"]], "why": "made up: the speed is under twice the limit"}])
QUADS = made_up([ROTOR, QUAD],
                [asks("quad.speed", "quad"), asks("quad.thrust", "quad"), asks("quad.balance", "quad"), asks("quad.static", "quad"),
                 asks("quad.guarded", "quad", unless={"when": ["is", "rotor.guard", "full"], "why": "made up: a guarded rotor"}), asks("quad.grain", "quad"),
                 asks("rotor_set.own", "rotor_set")],
                [rule("speed", "quad", "quad.speed", le=["speed", "rotor.speed_limit"]),
                 rule("thrust", "quad", "quad.thrust", le=[["load", "pull"], "rotor.thrust_limit"]),
                 rule("balance", "quad", "quad.balance", requires=["is", "rotor.balance", "dynamic"]),
                 rule("static", "quad", "quad.static", when=["is", "rotor.balance", "static"], le=["speed", ["q", "100", "Hz"]]),
                 rule("guarded", "quad", "quad.guarded", le=[["load", "pull"], ["q", "100", "N"]]),
                 rule("grain", "quad", "quad.grain", when=["is", "rotor.grain", "unstated"], le=["speed", ["q", "200", "Hz"]]),
                 rule("own", "rotor_set", "rotor_set.own", le=["thrust", "thrust_limit"]),
                 rule("own-speed", "rotor_set", "rotor_set.own", when=["is", "guard", "none"], le=[["q", "10", "Hz"], "speed_limit"])])
SET = dict(thrust="10 N", speed_limit="9000 rpm", thrust_limit="12 N", balance="dynamic", guard="none", mass="30 g", blades="2", grain="along")
HOVER = load("hover", "q pull in [0 N, 8 N]") + load("climb", "q pull in [0 N, 11 N]")
NO_MAKER = "{} is unstated: its maker states none, and {} reads it"


def quad(card: str = HOVER, speed: str = "140 Hz", **lines: str) -> tuple[str, str]:
    return design(part("rotor_set", "r", **{**SET, **lines}), part("quad", "q", speed=speed, sets="r")), HEAD + card


class AFieldLeftUnstated(unittest.TestCase):
    def test_a_rotor_set_that_states_every_field_is_checked_as_before(self):
        found, verdict, _ = cells(self, QUADS, *quad())
        self.assertEqual(found, {("r", "rotor_set.own", "own"): "proved", ("r", "rotor_set.own", "own-speed"): "proved", ("q", "quad.speed", "speed"): "proved",
                                 ("q", "quad.thrust", "thrust/climb"): "proved", ("q", "quad.thrust", "thrust/hover"): "proved", ("q", "quad.balance", "balance"): "proved",
                                 ("q", "quad.static", ""): "open", ("q", "quad.guarded", "guarded/climb"): "proved", ("q", "quad.guarded", "guarded/hover"): "proved",
                                 ("q", "quad.grain", ""): "open", ("r", "unread", "mass"): "open", ("r", "unread", "blades"): "open", ("r", "unread", "grain"): "open"})
        self.assertEqual(verdict, "UNKNOWN", "the rule that reads the grain does not apply to this rotor set, so nothing reads its grain")

    def test_a_rule_that_reads_an_unstated_quantity_is_open_and_names_it(self):
        found, verdict, said = cells(self, QUADS, *quad(speed_limit="unstated"))
        self.assertEqual((found["q", "quad.speed", "speed"], found["r", "rotor_set.own", "own-speed"], verdict), ("open", "open", "UNKNOWN"))
        self.assertEqual(reason(said, "quad.speed"), NO_MAKER.format("r.speed_limit", "the rule"))
        self.assertEqual(reason(said, "rotor_set.own", "own-speed"), NO_MAKER.format("r.speed_limit", "the rule"))
        self.assertEqual((found["q", "quad.thrust", "thrust/hover"], found["r", "rotor_set.own", "own"]), ("proved", "proved"), "the other limit is stated, and is checked")
        self.assertNotIn(("r", "unread", "speed_limit"), found)

    def test_an_unstated_field_is_never_read_as_zero_or_as_any_number(self):
        """A speed of 10,000 Hz would fail any limit, and breaks the quad's need at any limit a maker states. With the limit unstated nothing is proved or refuted of it."""
        found, _, said = cells(self, QUADS, *quad(speed="10000 Hz", speed_limit="unstated"))
        self.assertEqual(found["q", "quad.speed", "speed"], "open")
        mine, its = ill_formed(self, QUADS, *quad(speed="10000 Hz"))
        self.assertIn("parts.9 design q: breaks need 1 of a quad", its)
        found, _, _ = cells(self, QUADS, *quad(thrust="1000 N", thrust_limit="unstated"))
        self.assertEqual(found["r", "rotor_set.own", "own"], "open", "the rotor's own need names the limit too, and does not refuse the part")

    def test_a_rule_that_reads_loads_has_an_open_cell_for_each_case(self):
        found, _, said = cells(self, QUADS, *quad(thrust_limit="unstated"))
        self.assertEqual((found["q", "quad.thrust", "thrust/hover"], found["q", "quad.thrust", "thrust/climb"]), ("open", "open"))
        self.assertNotIn(("q", "quad.thrust", "thrust"), found)
        self.assertEqual(reason(said, "quad.thrust", "thrust/climb"), NO_MAKER.format("r.thrust_limit", "the rule"))
        found, _, said = cells(self, QUADS, *quad("", thrust_limit="unstated"))
        self.assertEqual((found["q", "quad.thrust", "thrust"], reason(said, "quad.thrust")), ("open", NO_MAKER.format("r.thrust_limit", "the rule")))
        self.assertEqual(reason(said, "quad.guarded"), "the card puts no pull on q, which the rule reads", "a rule that reads no unstated field says what it said")

    def test_a_requirement_and_a_when_on_an_unstated_key_are_open(self):
        found, verdict, said = cells(self, QUADS, *quad(balance="unstated"))
        self.assertEqual((found["q", "quad.balance", "balance"], found["q", "quad.static", "static"], verdict), ("open", "open", "UNKNOWN"))
        self.assertEqual(reason(said, "quad.balance"), NO_MAKER.format("r.balance", "the rule"))
        self.assertEqual(reason(said, "quad.static"), NO_MAKER.format("r.balance", "the rule"))
        self.assertNotIn(("q", "quad.static", ""), found, "nothing says the rule does not apply, so the line is not without a rule")
        found, _, _ = cells(self, QUADS, *quad(balance="static"))
        self.assertEqual((found["q", "quad.balance", "balance"], found["q", "quad.static", "static"]), ("refuted", "refuted"))

    def test_an_unless_on_an_unstated_key_leaves_the_line_open_and_runs_no_rule(self):
        found, _, said = cells(self, QUADS, *quad(guard="unstated"))
        self.assertEqual({k[2]: v for k, v in found.items() if k[1] == "quad.guarded"}, {"": "open"})
        self.assertEqual(reason(said, "quad.guarded"), NO_MAKER.format("r.guard", "the `unless` of the line"))
        self.assertEqual(found["r", "rotor_set.own", "own-speed"], "open", "a rule of the rotor set whose `when` names its guard")
        found, _, _ = cells(self, QUADS, *quad(guard="full"))
        self.assertEqual({k[2]: v for k, v in found.items() if k[1] == "quad.guarded"}, {"": "not_applicable"})
        found, _, _ = cells(self, QUADS, *quad(HOVER.replace("11 N", "101 N"), guard="none", thrust_limit="200 N"))
        self.assertEqual(found["q", "quad.guarded", "guarded/climb"], "refuted")

    def test_a_field_left_unstated_that_nothing_reads_has_no_cell(self):
        found, _, _ = cells(self, QUADS, *quad(mass="unstated", blades="unstated"))
        self.assertEqual([k for k in found if k[1] == "unread"], [("r", "unread", "grain")])
        found, _, _ = cells(self, QUADS, *quad())
        self.assertEqual([k for k in found if k[1] == "unread"], [("r", "unread", "mass"), ("r", "unread", "blades"), ("r", "unread", "grain")])
        found, verdict, _ = cells(self, QUADS, *quad(mass="unstated", blades="unstated", grain="unstated", balance="dynamic"))
        self.assertEqual(([k for k in found if k[1] == "unread"], found["q", "quad.static", ""], verdict), ([], "open", "UNKNOWN"))

    def test_unstated_is_a_name_of_a_key_that_is_not_optional(self):
        found, _, _ = cells(self, QUADS, *quad(grain="unstated"))
        self.assertEqual(found["q", "quad.grain", "grain"], "proved", "the key has the name `unstated`, and the rule's `when` holds for it")
        self.assertEqual(found["q", "quad.speed", "speed"], "proved")

    def test_a_field_that_is_not_optional_must_be_stated_and_the_word_is_bare(self):
        for lines, finding in ((dict(thrust="unstated"), "parts.3 design r.thrust: is left unstated, and its field is not `optional`: it must be stated"),
                               (dict(speed_limit='"unstated"'), "parts.3 design r.speed_limit: is one number or one given"),
                               (dict(speed_limit="unstated unstated"), "parts.3 design r.speed_limit: is one number or one given"),
                               (dict(speed_limit="none"), "parts.3 design r.speed_limit: is one number or one given"),
                               (dict(balance='"unstated"'), "parts.4 design r.balance: is one of: static, dynamic"),
                               (dict(balance="unknown"), "parts.4 design r.balance: is one of: static, dynamic"),
                               (dict(blades="unstated 2"), "parts.3 design r.blades: is one number or one given")):
            with self.subTest(lines):
                mine, its = ill_formed(self, QUADS, *quad(**lines))
                self.assertIn(finding, its)
        text, card = quad()
        mine, its = ill_formed(self, QUADS, text.replace("speed 140 Hz", "speed unstated"), card)
        self.assertIn("parts.3 design q.speed: is left unstated", its)
        text, card = quad(speed_limit="given r.speed_limit")
        found, _, _ = cells(self, QUADS, text, card + given("r.speed_limit", "150 Hz", "160 Hz"))
        self.assertEqual(found["q", "quad.speed", "speed"], "proved", "a card may bound a field that a part may leave unstated")

    def test_a_deck_marks_a_quantity_or_a_key_optional_with_true_or_false(self):
        for field in (size("x", optional="yes"), size("x", optional=1), size("x", optional=None), size("x", optional=True, signed=True), {**key("x", "a", "unstated"), "optional": True},
                      {"name": "x", "type": "rotor_set", "what": "x", "optional": True}, {**key("x", "a", "b"), "optional": "true"}):
            with self.subTest(field):
                no_deck(self, made_up([ROTOR, kind("holder", field)]))
        no_deck(self, made_up([kind("holder", size("x"), loads=[{"name": "f", "dim": "force", "what": "f", "optional": True}])]))
        reads(self, made_up([kind("holder", size("x", optional=False), size("y", optional=True, whole=True, dim="dimensionless", may_be="zero"), {**key("k", "a", "unstated"), "optional": False})]))


# --- 5. a quantity at or under zero ---------------------------------------------------------------------

PACK = kind("pack", size("low", "temperature", may_be="negative"), size("high", "temperature", may_be="negative", least="-40 degC"),
            size("station", "length", may_be="negative"), size("offset", "length", may_be="zero"), size("spare", "dimensionless", whole=True, may_be="zero"),
            size("mass", "mass"), size("drift", "length", may_be="negative", signed=True), size("width", "length"),
            loads=[{"name": "air", "dim": "temperature", "what": "the air"}, {"name": "shift", "dim": "length", "may_be": "negative", "what": "a shift of either sign"},
                   {"name": "reach", "dim": "length", "what": "a reach"}],
            needs=[{"le": [["add", "station", "drift"], ["mul", "2", "width"]], "why": "made up: the station and its drift stay within two widths"},
                   {"lt": [["mul", "offset", "station"], ["mul", "width", ["q", "1", "m"]]], "why": "made up: a product of two fields that may not be positive"}])
PACKS = made_up([PACK], [asks("pack.cold", "pack"), asks("pack.span", "pack"), asks("pack.share", "pack"), asks("pack.centre", "pack")],
                [rule("cold", "pack", "pack.cold", le=["low", ["load", "air"]]),
                 rule("span", "pack", "pack.span", lt=["low", "high"]),
                 rule("share", "pack", "pack.share", le=[["div", "mass", "offset"], ["div", ["q", "10", "kg"], ["q", "1", "m"]]]),
                 rule("centre", "pack", "pack.centre", le=[["abs", ["add", "station", "drift", ["load", "shift"], ["neg", ["load", "reach"]], ["mul", "spare", "width"]]], ["q", "20", "mm"]])])
COLD = dict(low="-10 degC", high="40 degC", station="-5 mm", offset="200 mm", spare="0", mass="1 kg", drift="given p.drift", width="30 mm")
FLIGHT = load("flight", "p air in [-10 degC, 40 degC]", "p shift in [-2 mm, 2 mm]", "p reach in [0 mm, 1 mm]")


def pack(card: str = FLIGHT, drift: tuple[str, str] = ("-3 mm", "3 mm"), **lines: str) -> tuple[str, str]:
    return design(part("pack", "p", **{**COLD, **lines})), HEAD + given("p.drift", *drift) + card


class AtOrUnderZero(unittest.TestCase):
    def test_a_battery_to_ten_below_and_a_station_behind_the_datum_are_read_and_checked(self):
        found, verdict, said = cells(self, PACKS, *pack())
        self.assertEqual((found["p", "pack.cold", "cold/flight"], found["p", "pack.span", "span"], found["p", "pack.share", "share"], found["p", "pack.centre", "centre/flight"], verdict),
                         ("proved", "proved", "proved", "proved", "PASS"))
        deck, read = parsed(PACKS, *pack())
        written = {q["field"]: q for q in export.design_file(read, "", deck=True)["quantities"]}
        self.assertEqual([(written[f]["dim"], written[f]["lo"]) for f in ("low", "station", "spare")], [("temperature", "-10"), ("length", "-1/200"), ("dimensionless", "0")])
        found, _, _ = cells(self, PACKS, *pack(FLIGHT.replace("[-10 degC, 40 degC]", "[-10.001 degC, 40 degC]")))
        self.assertEqual(found["p", "pack.cold", "cold/flight"], "refuted", "the air may be colder than the pack allows")

    def test_a_range_in_fahrenheit_is_stated_in_celsius_as_exact_fractions(self):
        """25 to 150 degF is -35/9 to 590/9 degC. No unit has an offset, so the card writes the fractions."""
        fahrenheit = FLIGHT.replace("[-10 degC, 40 degC]", "[-35/9 degC, 590/9 degC]")
        deck, read = parsed(PACKS, *pack(fahrenheit, low="-4 degC"))
        air = next(i for i in export.card(read, export.read_inputs(read), placed=True)["inputs"] if i.get("field") == "air")
        self.assertEqual((Fraction(air["lo"]), Fraction(air["hi"])), ((Fraction(25) - 32) * 5 / 9, (Fraction(150) - 32) * 5 / 9))
        found, _, _ = cells(self, PACKS, *pack(fahrenheit, low="-4 degC"))
        self.assertEqual(found["p", "pack.cold", "cold/flight"], "proved")
        for unit in ("degF", "K"):
            with self.assertRaises(LoweringError):
                parsed(PACKS, *pack(low=f"14 {unit}"))

    def test_zero_and_under_it_are_refused_where_the_field_does_not_permit_them(self):
        for lines, finding in ((dict(mass="0 kg"), "parts.3 design p.mass: is not more than zero"), (dict(mass="-1 kg"), "parts.3 design p.mass: is not more than zero"),
                               (dict(width="0 mm"), "parts.3 design p.width: is not more than zero"),
                               (dict(offset="-1 mm"), "parts.3 design p.offset: is under zero, and its field may be zero and not under it"),
                               (dict(spare="-1"), "parts.3 design p.spare: is under zero"), (dict(spare="0.5"), "parts.3 design p.spare: is a count: one whole number"),
                               (dict(high="-41 degC"), "parts.3 design p.high: is under the least its field may take"),
                               (dict(low="-300 degC"), "parts.3 design p.low: a temperature is at least -5463/20, and this one goes down to -300")):
            with self.subTest(lines):
                mine, its = ill_formed(self, PACKS, *pack(**lines))
                self.assertIn(finding, its)
        mine, its = ill_formed(self, PACKS, *pack(mass="0 kg"))
        self.assertIn("types.3 design p.mass.mass", its, "a number of a field that says nothing is still held to the floor of a size")
        mine, its = ill_formed(self, PACKS, *pack(low="-300 degC"))
        self.assertNotIn("types.3", its, "a field that may be negative is held to its own floor, and to absolute zero")
        for lines in (dict(offset="0 mm", mass="0.001 g"), dict(spare="0"), dict(low="-273.15 degC", high="-40 degC"), dict(station="0 mm"), dict(station="-1 km", width="1 km")):
            with self.subTest(lines):
                cells(self, PACKS, *pack(**lines))

    def test_a_bound_of_the_card_follows_the_field_or_the_load_it_is_for(self):
        for card, drift, finding in ((FLIGHT, ("-3 mm", "3 mm"), None), (FLIGHT.replace("[-2 mm, 2 mm]", "[-9 mm, -8 mm]"), ("5 mm", "6 mm"), None),
                                     (FLIGHT.replace("[0 mm, 1 mm]", "[-1 mm, 1 mm]"), ("-3 mm", "3 mm"), "types.4 card flight.p.reach: a length is at least 0, and this one goes down to -1/1000"),
                                     (FLIGHT.replace("[-10 degC, 40 degC]", "[-274 degC, 40 degC]"), ("-3 mm", "3 mm"), "types.4 card flight.p.air: a temperature is at least -5463/20")):
            with self.subTest(card=card, drift=drift):
                if finding is None:
                    cells(self, PACKS, *pack(card, drift))
                else:
                    self.assertIn(finding, ill_formed(self, PACKS, *pack(card, drift))[1])
        text, card = pack(width="given p.width")
        mine, its = ill_formed(self, PACKS, text, card + given("p.width", "-1 mm", "30 mm"))
        self.assertIn("types.4 card p.width: a length is at least 0", its)
        self.assertIn("parts.3 design p.width: is not more than zero", its)
        cold = json.loads(json.dumps(PACKS))
        cold["types"][0]["loads"][0]["may_be"] = "negative"
        mine, its = ill_formed(self, cold, *pack(FLIGHT.replace("[-10 degC, 40 degC]", "[-274 degC, 40 degC]")))
        self.assertIn("types.4 card flight.p.air: a temperature is at least -5463/20", its, "may_be lifts a floor at zero, and absolute zero is no such floor")

    def test_a_quotient_by_a_field_at_zero_has_no_value_and_its_cell_is_open(self):
        found, verdict, said = cells(self, PACKS, *pack(offset="0 mm"))
        self.assertEqual((found["p", "pack.share", "share"], verdict), ("open", "UNKNOWN"))
        if verify.binary():
            text, card = pack(offset="0 mm")
            for hint in (dict(state="proved", partition="leaf"), dict(state="refuted", point={"dsg:made-up.p.mass": "1", "dsg:made-up.p.offset": "0"})):
                its = hinted(self, PACKS, text, card, "pack.share", "p", **hint)
                self.assertEqual(its["state"], "open")
                self.assertIn("division by an interval that contains 0", its["reason"])
        text, card = pack(offset="given p.offset")
        found, _, _ = cells(self, PACKS, text, card + given("p.offset", "0 mm", "200 mm"))
        self.assertEqual(found["p", "pack.share", "share"], "open", "the offset may be zero, so the quotient has no value all over its range")
        found, _, _ = cells(self, PACKS, *pack(offset="50 mm"))
        self.assertEqual(found["p", "pack.share", "share"], "refuted", "1 kg over 50 mm is 20 kg/m")

    def test_a_need_reads_a_field_at_or_under_zero_and_divides_by_none(self):
        mine, its = ill_formed(self, PACKS, *pack(station="58 mm"))
        self.assertIn("parts.9 design p: breaks need 1 of a pack: its left side, up to 61/1000, is not at most its right side, 3/50", its)
        mine, its = ill_formed(self, PACKS, *pack(offset="700 mm", station="100 mm", width="60 mm"))
        self.assertIn("parts.9 design p: breaks need 2 of a pack: its left side, 7/100, is not under its right side, 3/50", its)
        found, _, _ = cells(self, PACKS, *pack(offset="700 mm", station="-100 mm", width="60 mm", low="-10 degC"))
        self.assertIn(("p", "pack.span", "span"), found, "a product under zero is under the right side, and the part is a part")
        for divisor in ("offset", "station", "spare", "drift"):
            with self.subTest(divisor):
                body = json.loads(json.dumps(PACKS))
                body["types"][0]["needs"].append({"le": [["div", "mass" if divisor == "spare" else "width", divisor], ["q", "1", "kg" if divisor == "spare" else "1"]], "why": "made up"})
                mine, its = no_deck(self, body)
                self.assertIn("may be zero", its)
        body = json.loads(json.dumps(PACKS))
        body["types"][0]["needs"].append({"le": [["div", "station", "width"], "3"], "why": "made up: a quotient by a field that is more than zero"})
        cells(self, body, *pack())

    def test_a_deck_says_may_be_in_one_of_two_ways_and_agrees_with_its_least(self):
        for field in (size("x", may_be="positive"), size("x", may_be=True), size("x", may_be="Zero"), size("x", may_be=None), size("x", may_be=["zero"]), size("x", may_be=""),
                      size("x", may_be="zero", least="0 mm"), size("x", may_be="zero", least="-1 mm"), size("x", may_be="zero", least="1 mm"),
                      size("x", may_be="negative", least="0 mm"), size("x", may_be="negative", least="1 mm"), {**key("x", "a", "b"), "may_be": "zero"},
                      {"name": "x", "type": "pack", "what": "x", "may_be": "negative"}):
            with self.subTest(field):
                no_deck(self, made_up([PACK, kind("holder", field)]))
        for burden in ({"name": "f", "dim": "force", "what": "f", "may_be": "zero"}, {"name": "f", "dim": "force", "what": "f", "may_be": "negative", "least": "0 N"},
                       {"name": "f", "dim": "force", "what": "f", "may_be": "any"}):
            with self.subTest(burden):
                no_deck(self, made_up([kind("holder", size("x"), loads=[burden])]))
        reads(self, made_up([kind("holder", size("x", may_be="negative", least="-1 mm"), size("n", "dimensionless", whole=True, may_be="negative"),
                                  loads=[{"name": "f", "dim": "length", "what": "f", "may_be": "negative", "least": "-1 mm"}])]))


# --- 6. a rule that states lt ---------------------------------------------------------------------------

CRAFT = kind("craft", size("mass", "mass"), size("cap", "mass", signed=True), size("span", "length"),
             loads=[{"name": "cargo", "dim": "mass", "least": "0 g", "what": "what it carries"}])
CRAFTS = made_up([CRAFT], [asks("craft.under", "craft"), asks("craft.within", "craft"), asks("craft.capped", "craft"), asks("craft.laden", "craft"),
                           asks("craft.self", "craft"), asks("craft.ranged", "craft")],
                 [rule("under", "craft", "craft.under", lt=["mass", ["q", "250", "g"]]),
                  rule("within", "craft", "craft.within", le=["mass", ["q", "250", "g"]]),
                  rule("capped", "craft", "craft.capped", lt=["mass", "cap"]),
                  rule("laden", "craft", "craft.laden", lt=[["add", "mass", ["load", "cargo"]], ["q", "55", "lb"]]),
                  rule("self", "craft", "craft.self", lt=["span", "span"]),
                  rule("ranged", "craft", "craft.ranged", lt=[["sqrt", ["mul", "span", "span"]], ["q", "0.3", "m"]],
                       where=[{"le": ["mass", ["q", "1", "kg"]], "why": "made up: a craft of at most a kilogram"}])])


def craft(mass: str = "249 g", cap: str = "250 g", span: str = "0.5 m", cap_to: str | None = None, cargo: str | None = None) -> tuple[str, str]:
    card = HEAD + given("c.cap", cap, cap_to) + (load("flight", f"c cargo in {cargo}") if cargo else "")
    return design(part("craft", "c", mass=mass, cap="given c.cap", span=span)), card


def hinted(test: unittest.TestCase, rules: dict, text: str, card: str, mechanism: str, subject: str = "c", **hint) -> dict:
    """The kernel's cell of `mechanism` when the hints of proofs.json are this one hint alone, which claims what the caller likes."""
    deck, read = parsed(rules, text, card)
    files = grid.bundle(read, deck)
    proofs = {"format": "petra-proofs/0", "cells": [{"subject": subject, "mechanism": mechanism, "entry": mechanism.split(".")[1], **hint}]}
    said = ask({**files, "proofs": json.dumps(proofs)})
    test.assertEqual(said["findings"], [])
    return cell(said, mechanism)


class AStrictRule(unittest.TestCase):
    def test_lt_is_proved_under_the_limit_and_refuted_on_it(self):
        for mass, under, within in (("249.999 g", "proved", "proved"), ("250 g", "refuted", "proved"), ("250.001 g", "refuted", "refuted"), ("0.55 lb", "proved", "proved"),
                                    ("8.818 oz", "proved", "proved"), ("8.8185 oz", "refuted", "refuted"), ("1/4 kg", "refuted", "proved")):
            with self.subTest(mass):
                found, verdict, _ = cells(self, CRAFTS, *craft(mass))
                self.assertEqual((found["c", "craft.under", "under"], found["c", "craft.within", "within"]), (under, within))
                self.assertEqual(verdict, "FAIL", "no span is under itself")

    def test_lt_over_a_range_is_proved_only_when_the_whole_range_is_under(self):
        for lo, hi, state in (("250 g", "250 g", "proved"), ("249.001 g", "300 g", "proved"), ("249 g", "300 g", "refuted"), ("240 g", "249 g", "refuted"),
                              ("249.0001 g", "249.0001 g", "proved")):
            with self.subTest(lo=lo, hi=hi):
                found, _, _ = cells(self, CRAFTS, *craft("249 g", lo, cap_to=hi))
                self.assertEqual(found["c", "craft.capped", "capped"], state, "the cap may be anywhere in its range, and the mass is 249 g")

    def test_nothing_is_under_itself(self):
        found, _, said = cells(self, CRAFTS, *craft())
        self.assertEqual(found["c", "craft.self", "self"], "refuted")

    def test_lt_reads_a_load_in_each_case_and_follows_its_range(self):
        for cargo, state in (("[0 lb, 54 lb]", "proved"), ("[0 lb, 54.45 lb]", "proved"), ("[0 lb, 54.46 lb]", "refuted"), ("[54.5 lb, 60 lb]", "refuted")):
            with self.subTest(cargo):
                found, _, _ = cells(self, CRAFTS, *craft(cargo=cargo))
                self.assertEqual(found["c", "craft.laden", "laden/flight"], state, "249 g and the cargo, against 55 lb")
        found, _, said = cells(self, CRAFTS, *craft())
        self.assertEqual((found["c", "craft.laden", "laden"], reason(said, "craft.laden")), ("open", "the card puts no cargo on c, which the rule reads"))

    def test_lt_with_a_range_and_a_root_that_is_rounded(self):
        """The square root of 0.09 m2 is enclosed and not exact, so a span of exactly 0.3 m is neither under 0.3 m nor shown not to be."""
        for span, mass, state in (("0.299 m", "249 g", "proved"), ("0.301 m", "249 g", "refuted"), ("0.3 m", "249 g", "open"), ("0.2 m", "1.5 kg", "open")):
            with self.subTest(span=span, mass=mass):
                found, _, said = cells(self, CRAFTS, *craft(mass, cap="2 kg", span=span))
                self.assertEqual(found["c", "craft.ranged", "ranged"], state)
                self.assertEqual(("c", "craft.ranged", "ranged/where") in found, mass == "249 g")

    def test_a_rule_states_one_of_le_lt_and_requires(self):
        both = rule("both", "craft", "craft.under", le=["mass", ["q", "250", "g"]], lt=["mass", ["q", "250", "g"]])
        for body in (both, rule("none", "craft", "craft.under"), rule("req", "craft", "craft.under", lt=["mass", "cap"], requires=["is", "x", "y"]),
                     rule("three", "craft", "craft.under", lt=["mass", "cap", "cap"]), rule("one", "craft", "craft.under", lt=["mass"]),
                     rule("dims", "craft", "craft.under", lt=["mass", "span"]), rule("text", "craft", "craft.under", lt="mass"),
                     rule("where", "craft", "craft.under", lt=["mass", "cap"], where=[{"lt": ["mass", "cap"], "why": "made up"}]),
                     rule("gt", "craft", "craft.under", gt=["cap", "mass"]), rule("ge", "craft", "craft.under", ge=["cap", "mass"])):
            with self.subTest(body["id"]):
                mine, its = no_deck(self, made_up([CRAFT], [asks("craft.under", "craft")], [body]))
        mine, its = no_deck(self, made_up([CRAFT], [asks("craft.under", "craft")], [both]))
        self.assertIn("a rule has one of `le`", its)
        self.assertIn("a rule has one of `le`", mine)

    @KERNEL
    def test_a_hint_cannot_prove_lt_on_its_edge_or_refute_it_under_it(self):
        text, card = craft("250 g")
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.under", state="proved", partition="leaf")["state"], "open", "250 g is not under 250 g")
        mass = {"dsg:made-up.c.mass": "1/4"}
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.under", state="refuted", point=mass)["state"], "refuted")
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.within", state="refuted", point=mass)["state"], "open", "250 g is at most 250 g")
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.within", state="proved", partition="leaf")["state"], "proved")
        text, card = craft("249 g", "249 g", cap_to="300 g")
        label = "in:made-up.c.cap"
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.capped", state="proved", partition="leaf")["state"], "open")
        split = {"input": label, "at": "1/4", "below": "leaf", "above": "leaf"}
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.capped", state="proved", partition=split)["state"], "open", "the cap may be 249 g, which the mass is not under")
        mass = {"dsg:made-up.c.mass": "249/1000"}
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.capped", state="refuted", point={**mass, label: "1/4"})["state"], "open", "249 g is under 250 g")
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.capped", state="refuted", point={**mass, label: "249/1000"})["state"], "refuted", "249 g is not under 249 g")
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.capped", state="refuted", point={**mass, label: "31/125"})["state"], "open", "the card gives no cap of 248 g")
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.capped", state="refuted", point={label: "249/1000"})["state"], "open", "the point gives the mass no value")


if __name__ == "__main__":
    unittest.main()
