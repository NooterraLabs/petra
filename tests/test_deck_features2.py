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

    def test_each_way_a_cell_is_open_that_a_waiver_rests_is_a_way_it_is_waived_and_its_reason_says_which(self):
        """No rule for the part, a load left out that a completion gives (a pull of zero, the least it may be, is under the cap), and a `where`
        that holds nowhere. A key left unstated is the last such way, which AFieldLeftUnstated and tests/test_kernel_attacks8.py test."""
        for lines, cases, mechanism, entry, was in (
                ({}, None, "j.none", "", "the deck has no rule for it"),
                ({}, None, "j.grade", "", "the deck has no rule for it on a part like this one"),
                ({}, load("calm", "p pull in [0 N, 30 N]") + load("idle"), "j.pull", "pull/idle", "case idle puts no pull on p, which the rule reads"),
                ({}, "", "j.pull", "pull", "the card puts no pull on p, which the rule reads"),
                (dict(w="5 mm"), None, "j.range", "range", "the rule holds only where made up: at least 6 mm wide, and that holds nowhere in the ranges for p")):
            with self.subTest(mechanism=mechanism, entry=entry):
                found, _, said = cells(self, JOINTS, *joint(cases=cases, **lines))
                self.assertEqual(found["p", mechanism, entry], "waived")
                if verify.binary():
                    self.assertTrue(reason(said, mechanism, entry).startswith("open but for the waiver: " + was), reason(said, mechanism, entry))
                bare, _, _ = cells(self, JOINTS, *joint([], cases=cases, **lines))
                self.assertEqual(bare["p", mechanism, entry], "open")
        found, _, _ = cells(self, JOINTS, *joint(w="5 mm"))
        self.assertNotIn(("p", "j.range", "range/where"), found, "a range that is not proved has no cell of its own, waived or not")

    def test_a_cell_that_an_inequality_could_answer_stays_open_under_a_waiver_and_says_so(self):
        """A `where` that holds in part of the ranges, a table that has a value in part of them or in none, and a quantity left unstated. The
        rule could be refuted where it has a value, at the value the table would give if the deck listed the width, or at the value the
        quantity has, so the waiver does not rest the cell, and its reason says so. Until the eighth review it rested the cell of a table with no
        value anywhere in the ranges."""
        for lines, bounds, mechanism, entry, was in (
                (dict(w="given p.w"), ("5 mm", "7 mm"), "j.range", "range", "the range the rule holds in is not proved: "),
                (dict(w="given p.w"), ("5 mm", "7 mm"), "j.table", "table", ""),      # the table lists 5 mm
                (dict(w="7 mm"), None, "j.table", "table", ""),      # between the two widths the table lists, where it has no value
                (dict(rating="unstated"), None, "j.rated", "rated", "p.rating is unstated: its maker states none, and the rule reads it")):
            with self.subTest(mechanism=mechanism):
                text, card = joint(**lines)
                found, _, said = cells(self, JOINTS, text, card + (given("p.w", *bounds) if bounds else ""))
                self.assertEqual(found["p", mechanism, entry], "open")
                if verify.binary():
                    self.assertTrue(reason(said, mechanism, entry).startswith(grid.UNRESTED + was), reason(said, mechanism, entry))

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
        """PASS when something is proved and nothing refuted, which `petra check` calls PASS_WAIVED, and the kernel PASS with the waivers
        listed. UNKNOWN when nothing is proved: waived is a state of its own, and is never counted as proved."""
        calm = load("calm", "p pull in [0 N, 30 N]")
        passing = dict(w="10 mm", grade="b", cap="100 N")
        found, verdict, said = cells(self, JOINTS, *joint(cases=calm, **{**passing, "w": "5 mm"}))
        self.assertEqual((verdict, sorted(set(found.values()))), ("PASS_WAIVED", ["not_applicable", "proved", "waived"]))
        if verify.binary():
            self.assertEqual((said["verdict"], [w["mechanism"] for w in said["waived"]]), ("PASS", ["j.none", "j.range"]))
        found, verdict, _ = cells(self, JOINTS, *joint(["j.size", "j.pull", "j.range", "j.table", "j.grade", "j.two", "j.rated"], cases=calm, **{**passing, "w": "5 mm"}))
        self.assertEqual((verdict, found["p", "j.none", ""]), ("UNKNOWN", "open"), "one open cell that no waiver rests")
        nothing = made_up([JOINT], [asks("j.none", "joint"), asks("j.pull", "joint")], [rule("pull", "joint", "j.pull", le=[["load", "pull"], "cap"])])
        found, verdict, _ = cells(self, nothing, *joint(["j.none", "j.pull"], cases=""))
        self.assertEqual((verdict, {k: v for k, v in found.items() if k[1] != "unread"}), ("UNKNOWN", {("p", "j.none", ""): "waived", ("p", "j.pull", "pull"): "waived"}),
                         "every line is waived and nothing is proved")

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
        it makes it refuted, and with no hint that settles it the cell is open: its rule's inequality could be answered, so the waiver does not
        rest it. The state a hint claims decides nothing."""
        text, card = joint(["j.size"], w="given p.w")
        label = "in:made-up.p.w"
        for lo, hi, hint, state in (("5 mm", "10 mm", dict(state="proved", partition="leaf"), "proved"),
                                    ("5 mm", "10 mm", dict(state="refuted", point={label: "1/100"}), "open"),
                                    ("5 mm", "10 mm", dict(state="waived"), "open"), ("5 mm", "10 mm", dict(state="open", why="x"), "open"),
                                    ("5 mm", "11 mm", dict(state="proved", partition="leaf"), "open"),
                                    ("5 mm", "11 mm", dict(state="refuted", point={label: "11/1000"}), "refuted"),
                                    ("5 mm", "11 mm", dict(state="proved", point={label: "11/1000"}), "refuted"),
                                    ("5 mm", "11 mm", dict(state="refuted", point={label: "1/100"}), "open"),
                                    ("5 mm", "11 mm", dict(state="refuted", point={label: "3/250"}), "open")):
            with self.subTest(lo=lo, hi=hi, hint=hint):
                its = hinted(self, JOINTS, text, card + given("p.w", lo, hi), "j.size", "p", **hint)
                self.assertEqual(its["state"], state)
                self.assertEqual(its.get("reason", "").startswith(grid.UNRESTED), state == "open")
        deck, read = parsed(JOINTS, text, card + given("p.w", "5 mm", "11 mm"))
        report, files = grid.check(read, deck)
        self.assertEqual(next(c.state for c in report.cells if c.mechanism == "j.size"), "refuted", "petra check finds the corner at 11 mm, and no waiver rests it")
        said = ask(files, without=("proofs",))
        self.assertEqual(cell(said, "j.size")["state"], "open", "with no proofs.json nothing settles the cell, and the waiver does not rest it: the kernel does not search")


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

    def test_a_table_a_case_and_a_range_that_read_an_unstated_field_leave_the_cell_open(self):
        """Each other way a rule reads a field: as the key of a table, through a `by`, as the quantity a row sorts by for a `case`, and in its `where`."""
        allowed = {"id": "made-up/allowed", "anchor": ANCHOR, "gives": {"name": "v", "dim": "dimensionless/time"}, "takes": [{"name": "balance", "one_of": ["static", "dynamic"]}],
                   "table": {"down": {"by": "balance"}, "unit": "Hz", "cells": ["100", "200"]}}
        sort = {"id": "made-up/sort", "anchor": ANCHOR, "gives": {"name": "size", "one_of": ["small", "large"]}, "takes": [{"name": "m", "dim": "mass", "range": ["1 g", "1 kg"]}],
                "table": {"down": {"by": "m", "bands": [["0 g", "50 g"], ["50 g", None]]}, "cells": ["small", "large"]}}
        deck = made_up([ROTOR, kind("quad", size("speed", "dimensionless/time"), {"name": "sets", "type": "rotor_set", "as": ["rotor"], "what": "its rotor sets"})],
                       [asks("quad.key", "quad"), asks("quad.by", "quad"), asks("quad.case", "quad"), asks("quad.where", "quad")],
                       [rule("key", "quad", "quad.key", le=["speed", ["row", "made-up/allowed", {"balance": "rotor.balance"}]]),
                        rule("by", "quad", "quad.by", le=["speed", ["row", "made-up/allowed", {"balance": ["by", "rotor.guard", {"none": "static", "full": "dynamic"}]}]]),
                        rule("case", "quad", "quad.case", le=["speed", ["case", ["row", "made-up/sort", {"m": "rotor.mass"}], {"small": ["q", "150", "Hz"], "large": ["q", "250", "Hz"]}]]),
                        rule("where", "quad", "quad.where", le=["speed", ["q", "300", "Hz"]], where=[{"le": ["rotor.thrust", "rotor.thrust_limit"], "why": "made up"}])],
                       [allowed, sort])
        found, _, _ = cells(self, deck, *quad(""))
        self.assertEqual({k[1]: v for k, v in found.items() if k[0] == "q" and not k[2].endswith("/where")},
                         {"quad.key": "proved", "quad.by": "refuted", "quad.case": "proved", "quad.where": "proved"}, "140 Hz against 200, 100, 150 and 300")
        for field, mechanism in (("balance", "quad.key"), ("guard", "quad.by"), ("mass", "quad.case"), ("thrust_limit", "quad.where")):
            with self.subTest(field):
                found, _, said = cells(self, deck, *quad("", **{field: "unstated"}))
                mine = {k[2]: v for k, v in found.items() if k[1] == mechanism}
                self.assertEqual(mine, {mechanism.split(".")[1]: "open"}, "one open cell, and no cell for a range")
                self.assertEqual(reason(said, mechanism), NO_MAKER.format(f"r.{field}", "the rule"))
                self.assertEqual(sum(v == "open" for k, v in found.items() if k[0] == "q"), 1, "the rules that do not read it are settled")

    def test_a_waiver_rests_a_cell_left_open_by_an_unstated_key_and_not_by_an_unstated_quantity(self):
        """A key left unstated leaves unsaid which rule answers, and a waiver rests the cells that read it. A quantity left unstated leaves the
        rule's inequality to be answered for whatever value it has, and the cell stays open under the waiver."""
        def waive(*mechanisms: str) -> str:
            return HOVER + "".join(f"\nwaive {m} on q {BY}\n" for m in mechanisms)

        found, _, said = cells(self, QUADS, *quad(waive("quad.balance", "quad.static"), balance="unstated"))
        self.assertEqual((found["q", "quad.balance", "balance"], found["q", "quad.static", "static"]), ("waived", "waived"))
        self.assertTrue(reason(said, "quad.static").endswith("open but for the waiver: " + NO_MAKER.format("r.balance", "the rule")), reason(said, "quad.static"))
        found, _, said = cells(self, QUADS, *quad(waive("quad.guarded"), guard="unstated"))
        self.assertEqual(found["q", "quad.guarded", ""], "waived")
        self.assertTrue(reason(said, "quad.guarded").endswith("open but for the waiver: " + NO_MAKER.format("r.guard", "the `unless` of the line")))
        found, verdict, said = cells(self, QUADS, *quad(waive("quad.speed"), speed_limit="unstated"))
        self.assertEqual((found["q", "quad.speed", "speed"], verdict), ("open", "UNKNOWN"))
        self.assertEqual(reason(said, "quad.speed"), grid.UNRESTED + NO_MAKER.format("r.speed_limit", "the rule"))
        found, _, _ = cells(self, QUADS, *quad(waive("quad.thrust"), thrust_limit="unstated"))
        self.assertEqual((found["q", "quad.thrust", "thrust/hover"], found["q", "quad.thrust", "thrust/climb"]), ("open", "open"))

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
                 rule("share", "pack", "pack.share", le=[["div", "mass", ["add", "offset", "station"]], ["div", ["q", "10", "kg"], ["q", "1", "m"]]]),
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

    def test_a_quotient_by_a_sum_at_zero_has_no_value_and_its_cell_is_open(self):
        """The rule divides by the offset and the station together, which are zero where the
        offset of 5 mm makes up for the station 5 mm behind the datum."""
        found, verdict, said = cells(self, PACKS, *pack(offset="5 mm"))
        self.assertEqual((found["p", "pack.share", "share"], verdict), ("open", "UNKNOWN"))
        if verify.binary():
            text, card = pack(offset="5 mm")
            point = {"dsg:made-up.p.mass": "1", "dsg:made-up.p.offset": "1/200", "dsg:made-up.p.station": "-1/200"}
            for hint in (dict(state="proved", partition="leaf"), dict(state="refuted", point=point)):
                its = hinted(self, PACKS, text, card, "pack.share", "p", **hint)
                self.assertEqual(its["state"], "open")
                self.assertIn("division by an interval that contains 0", its["reason"])
        text, card = pack(offset="given p.offset")
        found, _, _ = cells(self, PACKS, text, card + given("p.offset", "0 mm", "5 mm"))
        self.assertEqual(found["p", "pack.share", "share"], "open", "the sum may be zero, so the quotient has no value all over its range")
        found, _, _ = cells(self, PACKS, *pack(offset="50 mm"))
        self.assertEqual(found["p", "pack.share", "share"], "refuted", "1 kg over 45 mm is 22.2 kg/m")

    def test_a_rule_that_divides_by_a_field_that_may_be_zero_is_refused_when_the_deck_is_read(self):
        """Or takes the root of one that may be under zero, or the logarithm of either: for a
        part at that value the rule has no value. The field may be named through a `let`, an
        input of a row, a power or a root, in a side or a `where`, or be a load that says
        `may_be`. A sum or a product that holds one is not looked into, and its cell is open
        where it is zero."""
        per_metre = ["div", ["q", "1", "kg"], ["q", "1", "m"]]
        inverse = {"id": "made-up/inverse", "anchor": ANCHOR, "gives": {"name": "y", "dim": "mass/length"},
                   "takes": [{"name": "x", "dim": "length", "range": ["1 mm", "1 m"]}], "is": ["div", ["q", "1", "kg"], "x"]}
        refused = {"it divides by offset": [dict(le=[["div", "mass", "offset"], per_metre]), dict(let={"o": "offset"}, le=[["div", "mass", "o"], per_metre]),
                                            dict(le=[["mul", "mass", ["pow", "offset", "-1"]], per_metre]),
                                            dict(le=[["mul", "mass", ["pow", "offset", "-0.5"]], ["div", ["q", "1", "kg"], ["sqrt", ["q", "1", "m"]]]]),
                                            dict(le=["mass", ["q", "1", "kg"]], where=[{"le": [["div", ["q", "1", "m"], "offset"], "1"], "why": "made up"}]),
                                            dict(le=[["row", "made-up/inverse", {"x": "offset"}], per_metre])],
                   "it divides by shift": [dict(le=[["div", "mass", ["load", "shift"]], per_metre])],
                   "it takes the root of station": [dict(le=[["sqrt", "station"], ["sqrt", ["q", "1", "m"]]])],
                   "it takes the logarithm of spare": [dict(le=[["ln", "spare"], "1"]), dict(le=[["pow", "spare", "0.3"], "1"])]}
        for says, bodies in refused.items():
            for body in bodies:
                with self.subTest(body):
                    mine, its = no_deck(self, made_up([PACK], [asks("pack.cold", "pack")], [rule("cold", "pack", "pack.cold", **body)], [inverse]))
                    self.assertIn(f"rule made-up/cold: {says}, which its `may_be` lets be", mine)
                    self.assertIn(says, its)
        for body in (dict(le=[["sqrt", "offset"], ["sqrt", ["q", "1", "m"]]]), dict(le=[["sqrt", ["pow", "station", "2"]], ["q", "1", "m"]]),
                     dict(le=[["div", "mass", ["add", "offset", "station"]], per_metre]), dict(le=[["div", "mass", ["mul", "offset", "2"]], per_metre]),
                     dict(le=[["row", "made-up/inverse", {"x": ["add", "offset", "width"]}], per_metre])):
            with self.subTest(body):
                reads(self, made_up([PACK], [asks("pack.cold", "pack")], [rule("cold", "pack", "pack.cold", **body)], [inverse]))

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

    @staticmethod
    def task(low: list[str], offset: list[str], air: list[str], adverse: bool = False) -> tuple[dict, list[dict]]:
        """A task for four rules of a cell, with these ranges for its lowest temperature, its offset and the air, and the four rules."""
        from petra import rule as acceptance

        derate ={"id": "made-up/derate", "anchor": ANCHOR, "gives": {"name": "k", "dim": "dimensionless"}, "takes": [{"name": "t", "dim": "temperature", "range": ["-40 degC", "60 degC"]}],
                  "table": {"down": {"by": "t", "bands": [["-40 degC", "0 degC"], ["0 degC", "60 degC"]]}, "cells": ["1/2", "1"]}}
        cell_ = {"type": "cell", "what": "a cell", "fields": [
            {"name": "low", "dim": "temperature", "may_be": "negative", "least": "-40 degC", "what": "its lowest temperature", "range": low},
            {"name": "offset", "dim": "length", "may_be": "zero", "what": "an offset", "range": offset}, {"name": "reach", "dim": "length", "what": "a reach", "range": ["10 mm", "100 mm"]},
            {"name": "draw", "dim": "current", "what": "the current drawn", "range": ["1 A", "40 A"]}, {"name": "rated", "dim": "current", "what": "the rated current", "range": ["10 A", "60 A"]}],
            "loads": [{"name": "air", "dim": "temperature", "may_be": "negative", "what": "the air", "range": air, **({"adverse": True} if adverse else {})}]}
        task = {"format": acceptance.TASK, "name": "made-up", "about": "made up", "rows": [derate], "types": [cell_],
                "asks": [{"type": "cell", "mechanism": f"cell.{name}", "what": name, "anchor": ANCHOR} for name in ("cold", "fits", "slope", "derated")]}
        rules = [rule("cold", "cell", "cell.cold", le=["low", ["load", "air"]]), rule("fits", "cell", "cell.fits", lt=["offset", "reach"]),
                 rule("slope", "cell", "cell.slope", le=[["div", "reach", ["mul", "2", "offset"]], "1"]),
                 rule("derated", "cell", "cell.derated", le=["draw", ["mul", "rated", ["row", "made-up/derate", {"t": "low"}]]])]
        return task, rules

    def accepted(self, *ranges, **more) -> tuple[int, str]:
        """What the acceptance check for a rule says of the four rules, sampled in these ranges."""
        import contextlib
        import io
        import tempfile

        from petra import rule as acceptance

        task, rules = self.task(*ranges, **more)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "task.json").write_text(json.dumps(task), encoding="utf-8")
            (Path(tmp) / "rules.json").write_text(json.dumps({"rules": rules}), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = acceptance.main([str(Path(tmp) / "task.json"), str(Path(tmp) / "rules.json")])
        return code, out.getvalue() + err.getvalue()

    def test_the_acceptance_check_for_a_rule_samples_a_field_where_its_type_says_it_may_be(self):
        """A task gives each quantity a range to sample it in, and the range follows the field: at zero for one that may be zero, and
        under it for one that may be negative, down to its `least` and to absolute zero. A band that ends at 0 degC is tried on its end."""
        code, printed = self.accepted(["-20 degC", "10 degC"], ["0 mm", "150 mm"], ["-10 degC", "40 degC"])
        self.assertEqual(code, 0, printed)
        for name in ("cold", "fits", "slope", "derated"):
            self.assertRegex(printed, rf"cell\.{name}: admitted[^:]*\n +units +pass[^\n]*\n +examples[^\n]*\n +reach +pass +96 parts: \d+ fails, \d+ holds")
        from petra import rule as acceptance

        body, rules = self.task(["-20 degC", "10 degC"], ["0 mm", "150 mm"], ["-10 degC", "40 degC"])
        read = acceptance.read_task(body)
        tried = acceptance.parts(read, "cell.derated", [acceptance.Reading(read, acceptance.Transcription(tuple(rules), {}, {}))])
        lows = {p["low"] for p in tried.base}
        self.assertLessEqual({Fraction(-40), Fraction(-999, 25), Fraction(-1, 25), Fraction(0), Fraction(3, 50), Fraction(60)}, lows, "on each end of each band, and a thousandth of the band inside it")
        self.assertTrue(any(p["offset"] == 0 for p in acceptance.parts(read, "cell.fits", [], count=4_000).base), "an offset of zero is one of the values a part is given")
        for ranges, named in(((["-50 degC", "10 degC"], ["0 mm", "150 mm"], ["-10 degC", "40 degC"]), "cell.low"),
                              ((["-20 degC", "10 degC"], ["-1 mm", "150 mm"], ["-10 degC", "40 degC"]), "cell.offset"),
                              ((["-20 degC", "10 degC"], ["0 mm", "150 mm"], ["-300 degC", "40 degC"]), "cell.air")):
            with self.subTest(named):
                code, printed = self.accepted(*ranges)
                self.assertEqual(code, 3, printed)
                self.assertIn(f"{named}: its range is two", printed, "under its `least`, under zero for a field that may be zero, and under absolute zero")
        code, printed = self.accepted(["-20 degC", "-20 degC"], ["0 mm", "0 mm"], ["-10 degC", "0 degC"])
        self.assertEqual(code, 1, printed)
        self.assertRegex(printed, r"reach +fail +made-up/slope answers none of 96 parts: 96 no value; mostly: [^\n]*division by \[0, 0\], which contains 0")
        code, printed = self.accepted(["-20 degC", "10 degC"], ["0 mm", "150 mm"], ["-30 degC", "-5 degC"], adverse=True)
        self.assertRegex(printed, r"direction +fail +more air helps: [^\n]* with air=-30 and holds [^\n]* with air=-0\.078125",
                         "above a top under zero is a 64th of it: the air is warmer there, and a warmer day helps this rule")


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

    def test_lt_with_a_range_and_a_root_of_a_square(self):
        """The square root of 0.09 m2 is 0.3 m exactly, since 0.09 is the square of a fraction, so a span of exactly 0.3 m is not under
        0.3 m and is refuted. Until the root of such a point was exact, its enclosure reached to both sides of 0.3 m and the cell was open.
        A root that is no fraction is rounded, and tests/test_kernel_attacks7.py holds a limit inside its enclosure open."""
        for span, mass, state in (("0.299 m", "249 g", "proved"), ("0.301 m", "249 g", "refuted"), ("0.3 m", "249 g", "refuted"), ("0.2 m", "1.5 kg", "open")):
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


# --- the three families that asked for them -------------------------------------------------------------

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DRAFTS = {"lifter": ("sha256:c39453ed2545a61b6c3c04129c4fecc3fedb1b684b0dde7eb010ffc71eb1e7bc", 4, 52),
          "process": ("sha256:e52e1af691a4d50d5266ce65e43c971ebba7f28fab5851bca2ee0b05f8860637", 3, 49),
          "drone": ("sha256:d7b1995de5d63c113b154768e7d7f2c9ed996730eec0aa822508d77bf66ada91", 12, 74)}
"""The scouts' drafts of the types and the grid of three families, as they stand on the branches `lifter`, `process` and `drone`
(bench/formalizer/NAME/draft.json): the hash of each file, how many types it has and how many lines of the grid. None has a row
or a rule, and none is a deck that ships."""
SAMPLE = {"length": "100 mm", "mass": "30 g", "force": "10 N", "stress": "100 MPa", "voltage": "14.8 V", "current": "20 A", "power": "500 W", "resistance": "20 mohm",
          "time": "12 min", "temperature": "40 degC", "dimensionless": "2", "moment": "5 Nm", "length^3": "50 inch^3", "length^4": "300 inch^4",
          "dimensionless/time": "9000 rpm", "current*time": "2200 mAh", "length/time": "19 m/s"}
"""A value of each dimension the drafts use, in a unit a data sheet would print it in. They are made up."""


def draft(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}_draft.json").read_text(encoding="utf-8"))


def field_of(body: dict, of: str, name: str) -> dict:
    return next(f for t in body["types"] if t["type"] == of for f in t["fields"] if f["name"] == name)


def lifter2() -> dict:
    """The lifting beam, restated once more. The design category and the service class are the asker's: the category sets the design
    factor, so a design that chose its own would choose its own strength. The card states both."""
    from tests.test_deck_features import lifter

    body = lifter()
    for name in ("category", "service"):
        field_of(body, "lifting_beam", name)["signed"] = True
    return body


def process2() -> dict:
    """The cut and bent part, restated. The shop whose limits a part is checked against is the asker's to name: a design that named
    its own would pick the loosest. The card states it."""
    body = draft("process")
    field_of(body, "cut_part", "shop")["signed"] = True
    return body


def drone2() -> dict:
    """The quadcopter, restated.

    - The regulation it is flown under, the class it is to bear and the number of its rotor sets are the asker's, and the card states them.
    - A propeller's maker states a greatest speed or a greatest thrust, and seldom both. The draft had a key to say which, and a number the
      design made up for the other. Both limits are optional now, and the key is gone. A pack's resistance is optional too.
    - A battery may be discharged below freezing, so its lowest and its highest temperature may be negative.
    - A position along the line of flight is measured from the middle of the rotor axes and may be negative, in the design and in a load.
      The draft measured every position from the rear end of the bottom plate, because a quantity was more than zero."""
    body = draft("drone")
    for name in ("rule_set", "class_mark", "rotors"):
        field_of(body, "quadcopter", name)["signed"] = True
    rotor = next(t for t in body["types"] if t["type"] == "rotor_set")
    rotor["fields"] = [f for f in rotor["fields"] if f["name"] != "propeller_limit"]
    for of, name in (("rotor_set", "speed_limit"), ("rotor_set", "thrust_limit"), ("battery", "resistance")):
        field_of(body, of, name)["optional"] = True
    for of, name in (("battery", "temperature_low"), ("battery", "temperature_high"), ("quadcopter", "centre"), ("quadcopter", "battery_station")):
        field_of(body, of, name)["may_be"] = "negative"
    quad = next(t for t in body["types"] if t["type"] == "quadcopter")
    station = next(f for f in quad["loads"] if f["name"] == "payload_station")
    station.pop("least")
    station["may_be"] = "negative"
    return body


def stated(body: dict, parts: dict[str, str], says_of: dict[str, str] | None = None, cases: str = "", **lines: str) -> tuple[str, str]:
    """A made-up design of the deck's types and its card. `parts` names each part and its type. Every field takes a value of SAMPLE for its
    dimension, the first name of its key, or its least count, and the parts a field joins are the parts of that type in order. A quantity
    that is `signed` reads a given that the card bounds at the sample. `lines` changes a line, as `PART__FIELD=value`, and `says_of` is what
    the card states exactly, by `PART.FIELD`."""
    kinds = {t["type"]: t for t in body["types"]}
    blocks, card = [], HEAD
    for name, of in parts.items():
        written = {}
        for f in kinds[of]["fields"]:
            key_ = f"{name}__{f['name']}"
            if key_ in lines:
                written[f["name"]] = lines[key_]
            elif "type" in f:
                written[f["name"]] = " ".join([p for p, t in parts.items() if t == f["type"]][:len(f.get("as", [f["name"]]))])
            elif f"{name}.{f['name']}" in (says_of or {}):
                written[f["name"]] = f"given {name}.{f['name']}"
            elif "one_of" in f:
                first = f["one_of"][0]
                written[f["name"]] = first if first.isidentifier() else f'"{first}"'
            elif f.get("signed"):
                written[f["name"]] = f"given {name}.{f['name']}"
                card += given(f"{name}.{f['name']}", SAMPLE[f["dim"]])
            else:
                written[f["name"]] = f.get("least", "2") if f.get("whole") else SAMPLE[f["dim"]]
        blocks.append(part(of, name, **written))
    card += "".join(says(name, value) for name, value in (says_of or {}).items())
    return design(*blocks), card + cases


class TheThreeFamilies(unittest.TestCase):
    """The drafts of three families, each restated with what a deck can say now: types and lines of the grid alone, with no row and no
    rule. So every line that can arise is open, and what the tests hold is that the kernel and petra/grid.py read each deck and a
    made-up design of it alike, and refuse what the card alone may state when the design writes it."""

    def test_each_fixture_is_its_scouts_draft(self):
        for name, (digest, types, lines) in DRAFTS.items():
            with self.subTest(name):
                self.assertEqual(export.sha256((FIXTURES / f"{name}_draft.json").read_text(encoding="utf-8")), digest)
                body = draft(name)
                self.assertEqual((body["rows"], body["rules"], len(body["types"]), len(body["grid"])), ([], [], types, lines))

    def test_each_draft_and_each_restatement_loads_in_the_grid_and_in_the_kernel(self):
        for name, restated in (("lifter", lifter2), ("process", process2), ("drone", drone2)):
            with self.subTest(name):
                reads(self, draft(name))
                reads(self, restated())
                self.assertEqual(len(grid.read_deck(json.dumps(restated())).asks), DRAFTS[name][2], "the restatement asks every line the draft asks")

    LIFT = {"w": "i_shape", "up": "lug", "down": "lug", "s1": "shackle", "s2": "shackle", "b": "lifting_beam"}
    FITS = dict(s1__pin="1 inch", s2__pin="1 inch", up__hole="2 inch", up__width="6 inch", up__edge="3 inch", down__hole="2 inch", down__width="6 inch", down__edge="3 inch",
                b__length="120 inch")
    """Sizes that keep what a lug and a beam need of their fields: a pin under its hole, a hole narrower than its plate, the span within the length."""

    def test_a_lifting_beam_takes_its_category_and_its_service_class_from_the_card(self):
        body = lifter2()
        hot = load("lift", "b lift in [0 kip, 10 kip]", "b temperature in [-35/9 degC, 590/9 degC]")
        text, card = stated(body, self.LIFT, {"b.category": "B", "b.service": '"1"'}, hot, **self.FITS)
        card = card.replace(given("b.span", "100 mm"), given("b.span", "96 inch", "100 inch"))
        found, verdict, _ = cells(self, body, text, card)
        lines = {k[1]: v for k, v in found.items() if k[0] == "b" and k[1] != "unread"}
        self.assertEqual((len(lines), sorted(set(lines.values())), verdict), (52, ["not_applicable", "open"], "UNKNOWN"))
        deck, read = parsed(body, text, card)
        made = export.card(read, export.read_inputs(read), placed=True)
        self.assertEqual(made["states"], [{"name": "b.category", "by": "t@example.org", "key": "B"}, {"name": "b.service", "by": "t@example.org", "key": "1"}])
        heat = next(i for i in made["inputs"] if i.get("field") == "temperature")
        self.assertEqual((heat["dim"], Fraction(heat["lo"]), Fraction(heat["hi"])), ("temperature", Fraction(-35, 9), Fraction(590, 9)), "25 to 150 degF, as exact fractions of a degC")
        for field, written in (("category", "B"), ("service", '"1"')):
            with self.subTest(field):
                others = {k: v for k, v in {"b.category": "B", "b.service": '"1"'}.items() if k != f"b.{field}"}
                mine, its = ill_formed(self, body, *stated(body, self.LIFT, others, hot, **self.FITS, **{f"b__{field}": written}))
                self.assertIn(f"parts.4 design b.{field}: is for the card to state", its)
        service_0 = stated(body, self.LIFT, {"b.category": "B", "b.service": '"0"'}, hot, **self.FITS)
        found_0, _, _ = cells(self, body, service_0[0], service_0[1].replace(given("b.span", "100 mm"), given("b.span", "96 inch", "100 inch")))
        self.assertEqual((found["b", "lifting_beam.beam_fatigue", ""], found_0["b", "lifting_beam.beam_fatigue", ""]), ("open", "not_applicable"),
                         "the service class the card states is what the grid's `unless` reads")

    CUT = {"c": "cut_part"}

    def test_a_cut_part_takes_its_shop_from_the_card(self):
        body = process2()
        text, card = stated(body, self.CUT, {"c.shop": "oshcut"})
        found, verdict, _ = cells(self, body, text, card)
        lines = {k[1]: v for k, v in found.items() if k[0] == "c" and k[1] != "unread"}
        asked = [a for a in body["grid"] if a["type"] == "cut_part"]
        self.assertEqual((len(lines), verdict), (len(asked), "UNKNOWN"))
        self.assertIn(("c", "unread", "shop"), found, "no line of the draft reads the shop yet: its rules will, and until then the card's statement is checked by nothing")
        mine, its = ill_formed(self, body, *stated(body, self.CUT, c__shop="oshcut"))
        self.assertIn("parts.4 design c.shop: is for the card to state", its)
        mine, its = ill_formed(self, body, *stated(body, self.CUT, {"c.shop": "nobody"}))
        self.assertIn("parts.4 design c.shop: is one of: sendcutsend, oshcut", its)
        bent = {"c": "cut_part", "f": "bend", "p": "bent_part"}
        found, _, _ = cells(self, body, *stated(body, bent, {"c.shop": "strictest"}, f__grain="unstated"))
        self.assertIn(("f", "unread", "grain"), found, "`unstated` is a name of this key, which is not optional: the bend states that the grain is not stated to the shop")

    FLEET = {"r": "rotor_set", "e": "controller", "bat": "battery", "plug1": "connector", "plug2": "connector", "lead1": "lead", "lead2": "lead", "fc": "autopilot",
             "pm": "power_module", "top": "plate", "bottom": "plate", "a": "arm", "posts": "post", "rest": "sundries", "q": "quadcopter"}
    ASKED = {"q.rule_set": "eu_open", "q.class_mark": "C1", "q.rotors": "4"}

    def test_a_quadcopter_takes_its_class_from_the_card_and_states_what_its_makers_state(self):
        body = drone2()
        flight = load("cruise", "q payload in [0 g, 200 g]", "q payload_station in [-30 mm, 10 mm]", "q altitude in [0 m, 120 m]", "q air_temperature in [-10 degC, 40 degC]",
                      "q load_factor in [1, 2]", "q drop in [0 mm, 500 mm]")
        made = dict(r__speed_limit="unstated", r__thrust_limit="12 N", bat__resistance="unstated", bat__temperature_low="-10 degC", bat__temperature_high="40 degC",
                    q__centre="0 mm", q__battery_station="-20 mm", bat__cells="4", posts__count="4")
        text, card = stated(body, self.FLEET, self.ASKED, flight, **made)
        found, verdict, _ = cells(self, body, text, card)
        self.assertEqual(verdict, "UNKNOWN", "the draft has no rule, so every line that can arise is open")
        lines = {k[:2]: v for k, v in found.items() if k[1] != "unread"}
        self.assertEqual(len(lines), 74, "each line of the draft's grid is asked of the one part of its type")
        unread = {k[0] + "." + k[2] for k in found if k[1] == "unread"}
        self.assertNotIn("r.speed_limit", unread, "a limit the maker does not state has no cell")
        self.assertNotIn("bat.resistance", unread)
        self.assertIn("r.thrust_limit", unread, "the limit the maker states is a value that no rule of the draft checks yet")
        deck, read = parsed(body, text, card)
        written = {(q["entity"], q["field"]): q for q in export.design_file(read, "", deck=True)["quantities"]}
        self.assertEqual([(written[k]["dim"], written[k]["lo"]) for k in (("bat", "temperature_low"), ("q", "centre"), ("q", "battery_station"), ("r", "speed_full"), ("bat", "capacity"))],
                         [("temperature", "-10"), ("length", "0"), ("length", "-1/50"), ("s^-1", "150"), ("s^1 A^1", "7920")])
        card_json = export.card(read, export.read_inputs(read), placed=True)
        self.assertEqual([s["name"] for s in card_json["states"]], ["q.class_mark", "q.rotors", "q.rule_set"])
        self.assertEqual(next(i["lo"] for i in card_json["inputs"] if i.get("field") == "payload_station"), "-3/100")
        for field, written_by_design in (("class_mark", "C1"), ("rule_set", "eu_open"), ("rotors", "4")):
            with self.subTest(field):
                asked = {k: v for k, v in self.ASKED.items() if k != f"q.{field}"}
                mine, its = ill_formed(self, body, *stated(body, self.FLEET, asked, flight, **made, **{f"q__{field}": written_by_design}))
                self.assertIn(f"design q.{field}: is for the card to state", its)
        us = stated(body, self.FLEET, {**self.ASKED, "q.rule_set": "us_part_107", "q.class_mark": "none"}, flight, **made)
        found_us, _, _ = cells(self, body, *us)
        self.assertEqual((found["q", "quad.us_mass", ""], found_us["q", "quad.us_mass", ""], found["q", "quad.eu_class_mass", ""], found_us["q", "quad.eu_class_mass", ""]),
                         ("not_applicable", "open", "open", "not_applicable"), "the regulation and the class that the card states switch the lines of the grid")

    def test_what_the_drafts_had_to_bend_is_refused_or_needless_now(self):
        body = drone2()
        self.assertNotIn("propeller_limit", [f["name"] for t in body["types"] if t["type"] == "rotor_set" for f in t["fields"]])
        mine, its = ill_formed(self, body, *stated(body, self.FLEET, self.ASKED, r__speed_limit="unstated", r__thrust_limit="unstated", bat__temperature_low="-300 degC"))
        self.assertIn("parts.3 design bat.temperature_low: a temperature is at least -5463/20", its)
        mine, its = ill_formed(self, body, *stated(body, self.FLEET, self.ASKED, r__thrust_full="unstated"))
        self.assertIn("parts.3 design r.thrust_full: is left unstated, and its field is not `optional`", its)
        old = draft("drone")
        with self.assertRaises((LoweringError, grid.ComponentError)):      # the draft as the scout left it takes no battery below freezing
            deck, read = parsed(old, *stated(old, self.FLEET, bat__temperature_low="-10 degC", bat__cells="4", posts__count="4", q__rotors="4"))
            grid.check(read, deck)


# --- the heaviest input that each of them allows --------------------------------------------------------


@KERNEL
class Heaviest(unittest.TestCase):
    """For each thing a card, a design or a deck can state since 2026-11-11, the input of about 1 MB that was made to cost the kernel most by
    it, alone. Each is held to a third of the 30 processor seconds and to the 512 MB that an input under 1 MB may take, and each docstring
    says what it took on the desktop the costs were fitted on. The two that reach furthest, a deck at every limit whose lines are all
    waived and whose rules state `lt`, are in `Worst` of tests/test_kernel_attacks3.py, since they are that test's files."""

    def bounded(self, files: dict[str, str]) -> dict:
        from tests import test_kernel_attacks3 as heavy

        self.assertLess(heavy.total(files), 1.12 * heavy.MB)
        said, seconds, peak = heavy.measured(files)
        self.assertLess(seconds, heavy.PROCESSOR_SECONDS / 3, "processor seconds")
        self.assertLess(peak, heavy.HALF_GB, "bytes held")
        return said

    def test_a_card_that_states_a_key_and_a_count_for_each_of_4800_parts(self):
        """4,800 parts that each read a key and a count from the card, and a card that states both for each: 9,600 statements, 1.0 MB.
        A rule requires the key of each part, and nothing reads the count. Every look for a statement is by its name, in a table kept
        in order. 0.5 processor seconds and 49 MB. With 2,000 statements that no part reads the design is refused in 0.2."""
        from tests.test_kernel_attacks3 import empty_card, with_rules

        gate = kind("gate", {**key("k", "yes", "no"), "signed": True}, size("n", "dimensionless", whole=True, signed=True))
        deck = made_up([gate], [asks("gate.set", "gate")], [rule("set", "gate", "gate.set", requires=["is", "k", "yes"])])
        names = [f"g{i:04d}" for i in range(4_800)]
        card = {**empty_card(), "states": [s for name in names for s in ({"name": f"{name}.k", "by": "b", "key": "yes" if int(name[1:]) % 2 else "no"},
                                                                         {"name": f"{name}.n", "by": "b", "whole": "3"})]}
        parts = [{"name": name, "type": "gate", "lines": [{"field": "k", "args": [{"given": f"{name}.k"}]}, {"field": "n", "args": [{"given": f"{name}.n"}]}]} for name in names]
        said = self.bounded(with_rules(deck, card, parts))
        self.assertEqual((said["verdict"], said["findings"], said["counts"]["proved"], said["counts"]["refuted"], said["counts"]["open"]), ("FAIL", [], 2_400, 2_400, 4_800))
        stray = {**card, "states": card["states"][:6_000] + [{"name": f"x{i}.k", "by": "b", "key": "yes"} for i in range(2_000)]}
        parts = parts[:3_000]
        over = self.bounded(with_rules(deck, stray, parts))
        self.assertEqual((over["verdict"], len(over["findings"]), over["more_findings"]), ("ILL-FORMED", 100, 1_900), "a statement that no part reads is a finding, and they are counted past a hundred")

    def test_a_table_of_values_in_the_unit_that_is_listed_last(self):
        """A table read at 42,000 listed values, each cell in `oz`, the last unit of the kernel's list, and each value in `mile`: 84,000
        quantities whose unit is found past every other, 1.0 MB. A rule reads the table, which is a pick of far more orders than a pick
        may hold, so the deck is refused when it is read, after every value of it is read. 1.1 processor seconds and 60 MB."""
        from tests.test_kernel_attacks3 import empty_card, with_rules

        count = 42_000
        row = {"id": "made-up/w", "anchor": ANCHOR, "gives": {"name": "m", "dim": "mass"}, "takes": [{"name": "x", "dim": "length", "range": ["1 mile", f"{count} mile"]}],
               "table": {"down": {"by": "x", "at": [f"{k} mile" for k in range(1, count + 1)]}, "cells": [f"{k} oz" for k in range(1, count + 1)]}}
        deck = made_up([kind("t", size("f"), size("m", "mass"))], [asks("t.m", "t")], [rule("m", "t", "t.m", le=["m", ["row", "made-up/w", {"x": "f"}]])], [row])
        number = lambda dim, x: [{"number": {"dim": dim, "lo": x, "hi": x}}]      # noqa: E731
        parts = [{"name": f"p{i}", "type": "t", "lines": [{"field": "f", "args": number("length", "201168/125")}, {"field": "m", "args": number("mass", "1/100")}]} for i in range(2)]
        said = self.bounded(with_rules(deck, empty_card(), parts))
        self.assertEqual((said["verdict"], [f["file"] for f in said["findings"]]), ("ILL-FORMED", ["rules"]))
        self.assertIn("over the budget of 1024 for one pick", said["findings"][0]["why"])

    def test_parts_that_leave_a_field_unstated_under_rules_that_read_many(self):
        """A type of 190 optional fields, 212 rules that each sum them all, and 47 parts that leave the last field unstated. Each rule looks
        through its 190 fields for each part before it finds the one that is unstated: 9,964 open cells and 1.9 million steps of the ten
        million, 1.0 MB. One part more is past the cells a design may have. 1.1 processor seconds and 53 MB, and 0.7 seconds for the design that is refused."""
        from tests.test_kernel_attacks3 import empty_card, with_rules

        fields = [f"f{k:03d}" for k in range(190)]
        deck = made_up([kind("t", *(size(name, optional=True) for name in fields))], [asks(f"t.m{r:03d}", "t") for r in range(212)],
                       [rule(f"m{r:03d}", "t", f"t.m{r:03d}", le=[["add", *fields], ["q", "1", "km"]]) for r in range(212)])
        one = [{"number": {"dim": "length", "lo": "1", "hi": "1"}}]
        lines = [{"field": name, "args": one} for name in fields[:-1]] + [{"field": fields[-1], "args": [{"word": "unstated"}]}]

        def files(parts: int) -> dict[str, str]:
            return with_rules(deck, empty_card(), [{"name": f"p{i}", "type": "t", "lines": lines} for i in range(parts)])

        said = self.bounded(files(47))
        self.assertEqual((said["verdict"], said["findings"], said["counts"]["open"]), ("UNKNOWN", [], 47 * 212))
        self.assertEqual(said["cells"][0]["reason"], "p0.f189 is unstated: its maker states none, and the rule reads it")
        self.assertEqual(said["cells"][-1]["reason"], "past what the verdict prints of reasons")
        over = self.bounded(files(48))
        self.assertEqual([(f["rule"], f["item"]) for f in over["findings"]], [("limits", "parts")])
        self.assertIn("more than 10000 cells", over["findings"][0]["why"])

    def test_bounds_under_their_floor_for_loads_that_may_be_negative_and_one_long_name(self):
        """9,000 loads of a length under zero on parts whose type lets the load be negative, so that type rule 4 looks each one up and lets
        it by, and one given whose name is 400,000 dots, which the rule splits at its last dot to find no part: 0.9 MB and 0.4 MB. 0.8 and 0.2 processor seconds, and at most 64 MB."""
        from tests.test_kernel_attacks3 import empty_card, with_rules

        deck = made_up([kind("t", size("f"), loads=[{"name": "shift", "dim": "length", "may_be": "negative", "what": "a shift"}])], [asks("t.m", "t")],
                       [rule("m", "t", "t.m", le=[["add", "f", ["load", "shift"]], ["q", "1", "m"]])])
        one = [{"number": {"dim": "length", "lo": "1/2", "hi": "1/2"}}]
        parts = [{"name": f"p{i:03d}", "type": "t", "lines": [{"field": "f", "args": one}]} for i in range(90)]
        loads = [{"name": f"i{i}", "dim": "length", "lo": "-1", "hi": "1/4", "by": "b", "case": f"c{i // 90:02d}", "on": f"p{i % 90:03d}", "field": "shift"} for i in range(9_000)]
        said = self.bounded(with_rules(deck, empty_card(loads), parts))
        self.assertEqual((said["verdict"], said["findings"], len(said["cells"])), ("UNKNOWN", [], 9_000), "no hint proves a cell, and none is refused for its floor")
        dots = {"name": "." * 400_000, "dim": "length", "lo": "-1", "hi": "1", "by": "b"}
        said = self.bounded(with_rules(deck, empty_card([*loads[:90], dots]), parts))
        self.assertEqual(sorted({f["rule"] for f in said["findings"]}), ["parts.6", "types.4"], "under the floor of a length, and read by no part")

    def test_requirements_tried_to_the_million_and_a_thousand_more_left_untried(self):
        """Nine rules that each require a condition of 26 conditions over twelve keys of two names, 4,096 combinations each, which is the
        million that a deck's requirements are tried within, and 1,200 more such rules that are then read untried: 0.93 MB. Each rule has a
        line of its own, since two rules of one line may not end alike. 0.3 processor seconds and 43 MB."""
        from tests.test_kernel_attacks3 import empty_card, with_rules
        from tests.test_kernel_attacks6 import SWITCHES, PANEL

        honest = ["or", *(["is", name, "yes"] for name in SWITCHES[:12]), ["and", *(["is", name, "yes"] for name in SWITCHES[:12])]]
        count = 1_209
        deck = made_up([PANEL], [asks(f"panel.s{n:04d}", "panel") for n in range(count)], [rule(f"s{n:04d}", "panel", f"panel.s{n:04d}", requires=honest) for n in range(count)])
        lines = [{"field": name, "args": [{"word": "no"}]} for name in SWITCHES]
        said = self.bounded(with_rules(deck, empty_card(), [{"name": "p", "type": "panel", "lines": lines}]))
        self.assertEqual((said["verdict"], said["findings"], said["counts"]["refuted"], said["counts"]["open"]), ("FAIL", [], count, 1), "every switch is off, and one is read by no rule")


if __name__ == "__main__":
    unittest.main()
