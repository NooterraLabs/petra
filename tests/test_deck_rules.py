"""The rules of the deck that ships are rules from the page (docs/deck.md, "The second run").

Nobody writes a rule of a deck by hand. Two transcribers each wrote the rules of a lap from
the pages of AISC 360-22, and bench/formalizer holds what they handed in: rules2_a.json and
rules2_b.json, with eight worked examples in rules2_examples.json. petra/decks/aisc360.json
took the first transcription's rules, and the 14 rows of a3.json that those rules read.

The first class holds the deck to those files, so that an edit of a rule or a row in one
place alone fails. The second runs the acceptance check of petra/rule.py on the deck
itself: its rules must reproduce the worked examples, and the second transcription must
give every sampled part the same answer on every line both answer.
"""
import copy
import json
import unittest
from pathlib import Path

from petra import grid, rule
from petra.kernel import Interval

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "bench" / "formalizer"
NO_RULE = ["lap.tightening", "lap.hole_use", "lap.max_edge_distance", "lap.ply_flexure"]
"""The lines of a lap's grid that the deck has no rule and no `unless` for. Each is open until a card waives it."""
CANNOT_ARISE = ["lap.tension_with_shear", "lap.slip", "lap.ply_shear", "lap.ply_compression"]
RULES = {"lap.spacing": 2, "lap.end_distance": 2, "lap.side_distance": 2, "lap.spread": 2, "lap.strength": 1, "lap.ply_yield": 2, "lap.ply_rupture": 2,
         "lap.block_shear": 2}
"""How many rules answer each line that has one."""
EXAMPLES = {"lap.spacing": 1, "lap.end_distance": 2, "lap.strength": 2, "lap.ply_yield": 1, "lap.ply_rupture": 1, "lap.block_shear": 1}
"""How many worked examples the collector found for each line. None was found for the side distance or the greatest spacing."""


def read(name: str) -> dict:
    return json.loads((BENCH / name).read_text(encoding="utf-8"))


def shipped() -> dict:
    return json.loads((grid.DECKS / "aisc360.json").read_text(encoding="utf-8"))


def task_of(deck: dict) -> dict:
    """The task of the second run, made from the deck: the deck's rows, its types with the
    ranges, `alike` and `adverse` that rules_task2.json gives them, and its grid with no
    `unless`. rules_task2.json no longer loads as it stands: it names the deck and a3.json
    for its rows, and the deck now holds the rows of a3.json, so each would be there twice.
    The name is that task's, because the check samples its parts by it."""
    asked = read("rules_task2.json")
    types = copy.deepcopy(deck["types"])
    for kind, given in zip(types, asked["types"], strict=True):
        sampled = {f["name"]: f for f in (*given["fields"], *given.get("loads", []))}
        for f in (*kind["fields"], *kind.get("loads", [])):
            f.update({key: sampled[f["name"]][key] for key in ("range", "adverse") if key in sampled[f["name"]]})
        if "alike" in given:
            kind["alike"] = given["alike"]
    return {"format": rule.TASK, "name": asked["name"], "about": "The lap of the deck that ships, with the ranges of bench/formalizer/rules_task2.json.",
            "rows": deck["rows"], "types": types, "asks": [{k: v for k, v in a.items() if k != "unless"} for a in deck["grid"]]}


class FromTheFiles(unittest.TestCase):
    """The deck against what the transcribers handed in."""

    @classmethod
    def setUpClass(cls):
        cls.deck = shipped()

    def test_every_rule_is_the_first_transcriptions_rule_of_that_id_unedited(self):
        handed_in = {r["id"]: r for r in read("rules2_a.json")["rules"]}
        self.assertEqual(len(self.deck["rules"]), 15)
        for written in self.deck["rules"]:
            with self.subTest(rule=written["id"]):
                self.assertEqual(written, handed_in[written["id"]], "a rule of the deck is the transcription, and neither is edited alone")
        self.assertEqual({m: sum(r["mechanism"] == m for r in self.deck["rules"]) for m in RULES}, RULES)
        self.assertEqual(sorted(handed_in), sorted(r["id"] for r in self.deck["rules"]), "the deck takes every rule the first transcription has")

    def test_the_fourteen_rows_the_rules_brought_are_the_third_runs_rows_unedited(self):
        handed_in = read("a3.json")["rows"]
        self.assertEqual((len(self.deck["rows"]), len(handed_in)), (32, 14))
        self.assertEqual(self.deck["rows"][18:], handed_in, "the rows of a3.json, in its order, after the 18 the deck had")

    def test_every_row_a_rule_reads_is_in_the_deck(self):
        named = {node[1] for r in self.deck["rules"] for _, node in rule.places(r) if isinstance(node, list) and node[:1] == ["row"] and len(node) == 3}
        self.assertLessEqual(named, {r["id"] for r in self.deck["rows"]})
        self.assertLessEqual({"aisc360-22/J3.4-spacing", "aisc360-22/table-J3.5", "aisc360-22/table-J3.2-note-c", "aisc360-22/B4.3b-hole", "aisc360-22/D3-1"}, named)

    def test_the_types_are_the_ones_both_transcribers_were_given(self):
        """A rule reads a part by the names of its type's fields, so the deck's types are the task's, less the keys only a task has."""
        asked = read("rules_task2.json")["types"]
        plain = [{**{k: v for k, v in t.items() if k != "alike"}, "fields": [{k: v for k, v in f.items() if k != "range"} for f in t["fields"]],
                  **({"loads": [{k: v for k, v in f.items() if k not in ("range", "adverse")} for f in t["loads"]]} if "loads" in t else {})} for t in asked]
        self.assertEqual(self.deck["types"], plain)
        lap = [f["name"] for f in self.deck["types"][1]["fields"]]
        self.assertEqual(lap[lap.index("end"):], ["end", "side", "surface", "joins"])

    def test_the_grid_has_sixteen_lines_and_j3_6_is_two_of_them(self):
        """The task asked Section J3.6 as one line. The deck asks its greatest spacing and its greatest edge distance apart:
        the lap has no field for each plate's own edge distance, so only the spacing has rules."""
        asked = [a["mechanism"] for a in read("rules_task2.json")["asks"]]
        lines = [a["mechanism"] for a in self.deck["grid"]]
        at = asked.index("lap.spread") + 1
        self.assertEqual(lines, [*asked[:at], "lap.max_edge_distance", *asked[at:]])
        self.assertEqual(len(lines), 16)
        ruled = {r["mechanism"] for r in self.deck["rules"]}
        self.assertEqual(sorted(a["mechanism"] for a in self.deck["grid"] if "unless" in a), sorted(CANNOT_ARISE))
        self.assertEqual([m for m in lines if m not in ruled and m not in CANNOT_ARISE], NO_RULE)
        self.assertEqual(sorted(ruled), sorted(RULES))
        by = {a["mechanism"]: a for a in self.deck["grid"]}
        self.assertEqual(by["lap.max_edge_distance"]["anchor"], {"standard": "AISC 360-22", "clause": "J3.6"})
        self.assertEqual(by["lap.spread"]["what"], "maximum spacing of the holes")


class FromThePage(unittest.TestCase):
    """The acceptance check on the deck's own rules, with the second transcription and the worked examples.

    The second transcription answered `lap.spread` with four rules: two for the greatest spacing, which are the deck's, and
    two for the greatest edge distance, `lap-spread-edge-a` and `-b`, written from the lap's least side distance. The first
    transcriber refused to write those, and the deck asks the edge distance on a line of its own with no rule. So this
    test sets the two edge rules aside before it compares. They are set aside here and not in rules2_b.json, which is
    kept as it was handed in."""

    SET_ASIDE = ("lap-spread-edge-a", "lap-spread-edge-b")

    @classmethod
    def setUpClass(cls):
        cls.deck = shipped()
        cls.task = rule.read_task(task_of(cls.deck))
        cls.first = rule.Reading(cls.task, rule.read_transcription(cls.deck))
        handed_in = read("rules2_b.json")
        assert sorted(r["id"] for r in handed_in["rules"] if r["id"] in cls.SET_ASIDE) == sorted(cls.SET_ASIDE)
        cls.other = rule.Reading(cls.task, rule.read_transcription({**handed_in, "rules": [r for r in handed_in["rules"] if r["id"] not in cls.SET_ASIDE]}))
        cls.examples = {m: [rule.worked(e, cls.task, m) for e in found] for m, found in read("rules2_examples.json")["examples"].items()}
        cls.lines, cls.whole = rule.accept(cls.first, cls.examples, cls.other)
        cls.by = {line.mechanism: line for line in cls.lines}

    def check(self, mechanism: str, name: str) -> rule.Check:
        return next(c for c in self.by[mechanism].checks if c.name == name)

    def test_the_task_is_the_decks_own_lap(self):
        self.assertEqual(self.task.name, read("rules_task2.json")["name"], "the parts are sampled by the task's name, so they are the second run's")
        self.assertEqual(self.task.mechanisms, [a["mechanism"] for a in self.deck["grid"]])
        self.assertEqual((self.first.stray, self.other.stray), ([], []))

    def test_every_line_with_a_rule_or_an_unless_is_admitted_and_the_rest_are_left_out(self):
        self.assertEqual({m: line.state for m, line in self.by.items()}, {**{m: "admitted" for m in (*RULES, *CANNOT_ARISE)}, **{m: "left out" for m in NO_RULE}})
        self.assertEqual({m: len(self.by[m].rules) for m in RULES}, RULES)
        self.assertEqual([c.name for line in self.lines for c in line.checks if c.outcome == "fail"], [])
        self.assertEqual(self.whole.outcome, "pass", "a rule or an `unless` reads every field of a lap and of its plates, and the pull: " + self.whole.detail)

    def test_the_rules_reproduce_the_eight_worked_examples(self):
        self.assertEqual({m: len(found) for m, found in self.examples.items() if found}, EXAMPLES)
        self.assertEqual(sum(EXAMPLES.values()), 8)
        for mechanism, count in EXAMPLES.items():
            with self.subTest(mechanism=mechanism):
                found = self.check(mechanism, "examples")
                self.assertEqual((found.outcome, found.detail), ("pass", f"{count} reproduced"))
        for mechanism in set(RULES) - set(EXAMPLES):
            self.assertEqual(self.check(mechanism, "examples").outcome, "none", f"{mechanism} rests on its two transcriptions alone")

    def test_the_second_transcription_agrees_on_every_line_both_answer(self):
        for mechanism in (*RULES, *CANNOT_ARISE):
            with self.subTest(mechanism=mechanism):
                self.assertTrue(self.other.answers(mechanism), "the second transcription answers it")
                found = self.check(mechanism, "second")
                self.assertEqual(found.outcome, "pass", found.detail)
                self.assertNotIn("different forms", found.detail, "and with the same ratio at every part that holds or fails")
        for mechanism in NO_RULE:
            self.assertFalse(self.other.answers(mechanism), f"neither answers {mechanism}")

    def test_the_parts_tried_reach_every_rule(self):
        """Each rule answers a sampled part and fails at one, so an agreement is not two rules that say nothing."""
        for mechanism in RULES:
            with self.subTest(mechanism=mechanism):
                found = self.check(mechanism, "reach")
                self.assertIn(found.outcome, ("pass", "none"), found.detail)
                self.assertNotIn("holds at every sampled part", found.detail)
                settled = int(self.check(mechanism, "second").detail.split("which hold or fail at ")[1].split(",")[0].split(";")[0])
                self.assertGreater(settled, 100, "the two were compared where both hold or fail")

    def test_with_the_edge_rules_the_second_transcription_differs_on_the_one_line(self):
        """What the run found: the two differ on Section J3.6 alone, where the task's own field was the wrong one for the clause."""
        handed_in = rule.Reading(self.task, rule.read_transcription(read("rules2_b.json")))
        found = rule.second(self.first, handed_in, "lap.spread", rule.parts(self.task, "lap.spread", [self.first, handed_in]))
        self.assertEqual(found.outcome, "fail")
        self.assertIn("on whether the inequality holds", found.detail)

    def test_a_rule_at_a_point_is_what_the_grid_encloses_there(self):
        """The check reads a rule at a point by rule._values, a second way to evaluate the tape that grid.py writes. On the
        deck's rules, with their tables and the two cases of note c, it gives what grid.enclosures gives."""
        compared = 0
        for mechanism in RULES:
            for found in self.first.rules[mechanism]:
                for point in rule.parts(self.task, mechanism, [self.first]).base[:24]:
                    tape = self.first._tape(found, point)
                    if isinstance(tape, str) or any(label not in point for label in tape.labels):
                        continue
                    box = [point[label] for label in tape.labels]
                    ours, _ = rule._values(tape, box)
                    theirs = grid.enclosures([list(node) for node in tape.raw], [Interval.point(x) for x in box])
                    for a, b in zip(ours, theirs, strict=True):
                        self.assertEqual(isinstance(a, str), isinstance(b, str), (found.id, a, b))
                        self.assertTrue(isinstance(a, str) or rule._lifted(a) == b, (found.id, a, b))
                    compared += 1
        self.assertGreater(compared, 250)


if __name__ == "__main__":
    unittest.main()
