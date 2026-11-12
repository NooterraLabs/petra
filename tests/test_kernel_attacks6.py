"""The sixth hostile review of petra-verify (kernel/), petra/grid.py and petra/rule.py, one test
per reproduced finding, on the five deck features of tests/test_deck_features.py.

Each test asserts the behaviour the checker should have, and each fails at e4c3cde (rework),
where the review was made. The tests of the kernel are skipped when no kernel is built.

  1  A `case` on a row whose `one_of` has a name that no cell holds, which docs/deck.md
     allows. The `case` must still give that name an expression. The kernel writes a pick
     over the cells that hold a name (Deck.lean, `expr`, "case"), so it never reaches that
     expression: it counts nothing the expression names as read (Deck.lean `readRule`,
     `fields` and `loads` from `reach`) and never writes it (`Rule.tape`). petra/grid.py
     writes every branch (`_env`) and counts every branch read (`_reads`), and so does
     docs/format.md (cells, items 7 and 8). So a quantity that only that branch names is
     checked by nothing, and the grid gives PASS at any value of it, where the kernel leaves
     an `unread` cell; a load that only that branch names gives the grid a cell for each
     load case and the kernel one cell with no case. `petra check` raises Disagreement and
     exits 4; with no kernel it prints the grid's PASS. petra/rule.py's `reads` uses
     grid._reads, so the acceptance check says every field is read and admits the deck.
  2  petra/rule.py admits, with exit 0, a rule whose `requires` holds for every combination of
     the keys it names: `service is 0 or it is not`. The acceptance check sampled every
     combination, so it knows, and says `reach none ... widen the task's ranges`, which no
     range can change. The kernel then proves the line for every part, and counts the keys
     read, so no `unread` cell is left for them either.
  3  A known class, in a form the change to "keys the card states" does not reach: the order
     in which a design lists the parts of a join decides which is `top`, so it switches an
     `unless` on a key of a joined part. Same plates, same keys, same sizes: FAIL in one
     order, PASS in the other.
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from petra import grid, rule as acceptance, verify
from tests.test_deck_features import ANCHOR, HEAD, asks, design, kind, key, load, made_up, part, parsed, rule, size
from tests.test_kernel_grid import ask

KERNEL = unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")


def both(rules: dict, text: str, card: str = HEAD) -> tuple[list, str, dict, str]:
    """The grid's cells and verdict, what the kernel said, and where the two differ (verify.differs)."""
    deck, read = parsed(rules, text, card)
    report, files = grid.check(read, deck)
    mine = [(c.subject, c.mechanism, c.entry, c.state) for c in report.cells]
    said = ask(files)
    return mine, report.status, said, verify.differs(mine, report.status, deck.hash, said)


# --- 1. the branch of a name that no cell holds ------------------------------------------------------------

CATEGORY = {"id": "made-up/cat", "anchor": ANCHOR, "gives": {"name": "cat", "one_of": ["B", "C", "Z"], "what": "a category"},
            "takes": [{"name": "a", "dim": "length", "range": ["1 mm", "100 mm"], "what": "a"}],
            "table": {"down": {"by": "a", "bands": [["0 mm", "50 mm"], ["50 mm", "100 mm"]], "closed": "upper"}, "cells": ["B", "C"]}}
"""Names B for a length up to 50 mm and C above it. Z is a name of the row that no cell holds."""
BY_CATEGORY = ["row", "made-up/cat", {"a": "a"}]


REACHED = {**CATEGORY, "takes": [{**CATEGORY["takes"][0], "range": ["1 mm", "150 mm"]}],
           "table": {"down": {"by": "a", "bands": [["0 mm", "50 mm"], ["50 mm", "100 mm"], ["100 mm", "150 mm"]], "closed": "upper"}, "cells": ["B", "C", "Z"]}}
"""The same row with a third band, whose cell holds Z: every name it gives is one some length reaches."""
EMPTY_LINE = {"id": "made-up/k", "anchor": ANCHOR, "gives": {"name": "f", "dim": "dimensionless"}, "takes": [{"name": "grade", "one_of": ["x", "y"]}],
              "table": {"down": {"by": "grade"}, "unit": "1", "cells": [None, "2"]}}
"""A table read by a key, whose line for `x` is empty: a part whose key is x has no value in it."""


class DeadBranch(unittest.TestCase):
    """The review asserted the kernel's reading: what only the branch of a name no cell holds
    reads is read by nothing, so it has an `unread` cell. The decision went further, and the
    tests here hold the checker to the decision: there is no such branch. A row that lists
    in `one_of` a name that none of its cells holds is refused when the deck is read, by the
    kernel and by petra/grid.py, so every expression of a `case` is one some part reaches."""

    def decks(self, row: dict) -> tuple[dict, dict]:
        quantity = made_up([kind("w", size("a"), size("t"))], [asks("w.m", "w")],
                           [rule("m", "w", "w.m", le=[["case", BY_CATEGORY, {"B": "a", "C": ["mul", "a", "2"], "Z": "t"}], ["q", "60", "mm"]])], [row])
        loaded = made_up([kind("w", size("a"), size("cap", "force"), loads=[{"name": "P", "dim": "force", "least": "0 N", "what": "P"}])], [asks("w.m", "w")],
                         [rule("m", "w", "w.m", le=[["case", BY_CATEGORY, {"B": ["q", "1", "N"], "C": ["q", "1", "N"], "Z": ["load", "P"]}], "cap"])], [row])
        return quantity, loaded

    def test_a_row_that_gives_a_name_no_cell_holds_is_refused_by_all_three(self):
        """At e4c3cde the two decks loaded. For the first the grid gave PASS with one cell and
        the kernel the same proved cell and an `unread` cell for p.t, UNKNOWN. For the second
        the grid had `m/g` proved and the kernel `m`, with no case, and `unread` `P/g`. The
        acceptance check said `every field and every load is read` and exited 0."""
        from tests.test_deck_features import no_deck

        for name, deck in zip(("a quantity", "a load"), self.decks(CATEGORY)):
            with self.subTest(name):
                mine, its = no_deck(self, deck)
                for said in (mine, its):
                    self.assertIn("made-up/cat", said)
                    self.assertRegex(said, "no cell holds '?Z'?, which `one_of` lists")
        with self.subTest("the acceptance check"):
            task = {"format": acceptance.TASK, "name": "made-up", "about": "made up", "rows": [CATEGORY],
                    "types": [{"type": "w", "what": "a w", "fields": [{"name": "a", "dim": "length", "what": "a", "range": ["1 mm", "100 mm"]},
                                                                    {"name": "t", "dim": "length", "what": "t", "range": ["1 mm", "100 mm"]}]}],
                    "asks": [{"type": "w", "mechanism": "w.m", "what": "m", "anchor": ANCHOR}]}
            with self.assertRaisesRegex(grid.DeckError, "made-up/cat: no cell holds 'Z'"):
                acceptance.read_task(task)

    @KERNEL
    def test_with_every_name_in_a_cell_the_grid_and_the_kernel_read_every_branch_alike(self):
        """The same two decks with a third band whose cell holds Z. The branch Z is then the
        value for a part of 120 mm, so `t` and `P` are read, by the kernel as by the grid:
        neither has an `unread` cell for them, and the two list the same cells."""
        quantity, loaded = self.decks(REACHED)
        for name, deck, text, card, entry in (("a quantity", quantity, design(part("w", "p", a="30 mm", t="1000 m")), HEAD, "m"),
                                              ("a load", loaded, design(part("w", "p", a="30 mm", cap="10 N")), HEAD + load("g", "p P in [0 N, 5 N]"), "m/g")):
            with self.subTest(name):
                mine, status, said, differ = both(deck, text, card)
                self.assertEqual(differ, "", "the grid and the kernel list the same cells and give the same verdict")
                self.assertEqual((mine, status), ([("p", "w.m", entry, "proved")], "PASS"))
        mine, status, said, differ = both(quantity, design(part("w", "p", a="120 mm", t="1000 m")))
        self.assertEqual((differ, mine, status), ("", [("p", "w.m", "m", "refuted")], "FAIL"), "at 120 mm the name is Z, and t is over 60 mm")

    @KERNEL
    def test_a_branch_that_cannot_be_written_leaves_the_cell_open_whatever_a_hint_says(self):
        """A `case` whose expression for Z reads a table at an empty line. At e4c3cde, with Z in
        no cell, the kernel never wrote that expression, and a hand-made hint of one leaf made
        it prove the cell, which item 7 of docs/format.md leaves open. The deck with Z in no
        cell is now refused. With Z in a cell the kernel writes the expression of every name,
        the tape cannot be written, and the cell is open with or without the hint."""
        from tests.test_deck_features import no_deck

        def deck(row: dict) -> dict:
            return made_up([kind("w", size("a"), key("grade", "x", "y"))], [asks("w.m", "w")],
                           [rule("m", "w", "w.m", le=[["case", BY_CATEGORY, {"B": "1", "C": "1", "Z": ["row", "made-up/k", {"grade": "grade"}]}], "2"])], [row, EMPTY_LINE])

        no_deck(self, deck(CATEGORY))
        rules, read = parsed(deck(REACHED), design(part("w", "p", a="30 mm", grade="x")))
        files = grid.bundle(read, rules)
        hint = {"subject": "p", "mechanism": "w.m", "entry": "m", "state": "proved", "partition": "leaf"}
        for hints in ([], [hint]):
            said = ask({**files, "proofs": json.dumps({"format": "petra-proofs/0", "cells": hints})})
            (found,) = [c for c in said["cells"] if c["mechanism"] == "w.m"]
            self.assertEqual((said["findings"], found["state"], found["reason"]), ([], "open", "a table gives nothing here"))
        mine, status, said, differ = both(deck(REACHED), design(part("w", "p", a="30 mm", grade="x")))
        self.assertEqual((differ, [c[3] for c in mine], status), ("", ["open"], "UNKNOWN"))
        mine, status, said, differ = both(deck(REACHED), design(part("w", "p", a="30 mm", grade="y")))
        self.assertEqual((differ, [c[3] for c in mine], status), ("", ["proved"], "PASS"))


# --- 2. a requirement that every part meets -----------------------------------------------------------------

HOIST = {"format": acceptance.TASK, "name": "made-up", "about": "made up", "rows": [],
         "types": [{"type": "hoist", "what": "a hoist", "fields": [{"name": "category", "one_of": ["A", "B"], "what": "its category"},
                                                                    {"name": "service", "one_of": ["0", "1"], "what": "its service class"}]}],
         "asks": [{"type": "hoist", "mechanism": "hoist.category", "what": "the category and the service class", "anchor": ANCHOR}]}


def hoist_rule(**body) -> dict:
    return {"id": "made-up/category", "type": "hoist", "mechanism": "hoist.category", "anchor": ANCHOR, "says": "made up", **body}


class VacuousRequirement(unittest.TestCase):
    def accepted(self, transcription: dict) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "task.json").write_text(json.dumps(HOIST), encoding="utf-8")
            (Path(tmp) / "rules.json").write_text(json.dumps(transcription), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = acceptance.main([str(Path(tmp) / "task.json"), str(Path(tmp) / "rules.json")])
        return code, out.getvalue()

    def test_a_requirement_that_holds_for_every_combination_of_its_keys_is_not_admitted(self):
        """Each of these proves the line for every hoist it answers for, whatever its keys.
        Every combination of the two keys is sampled (4 of the 96 parts). At e4c3cde each is
        `admitted`, exit 0, with `reach none ... widen the task's ranges to see these`."""
        for name, transcription in {
            "a tautology": {"rules": [hoist_rule(when=["is", "category", "A"], requires=["or", ["is", "service", "0"], ["not", ["is", "service", "0"]]])]},
            "every name of the key": {"rules": [hoist_rule(when=["is", "category", "A"], requires=["or", ["is", "service", "0"], ["is", "service", "1"]])]},
            "what its `when` says": {"rules": [hoist_rule(when=["and", ["is", "category", "A"], ["is", "service", "0"]], requires=["is", "service", "0"])]},
            "what its line's `unless` leaves": {"rules": [hoist_rule(when=["is", "category", "A"], requires=["is", "service", "0"])],
                                                 "unless": [{"mechanism": "hoist.category", "why": "made up", "when": ["is", "service", "1"]}]},
        }.items():
            with self.subTest(name):
                code, printed = self.accepted(transcription)
                self.assertNotEqual(code, 0, printed)
                self.assertNotIn("hoist.category: admitted", printed)
        with self.subTest("the clause as written is still admitted"):
            # A hoist of category A is of service class 0. This holds at e4c3cde and must go on holding.
            code, printed = self.accepted({"rules": [hoist_rule(when=["is", "category", "A"], requires=["is", "service", "0"])]})
            self.assertEqual(code, 0, printed)

    def test_the_check_says_which_way_a_requirement_is_empty_and_gives_no_advice_about_ranges(self):
        """The decision: a requirement is tried at every combination of the keys that it, its
        `when` and its line's `unless` name, and is refused when it holds at every one at which
        it answers, or at none. The first three are refused when the rules are read as a deck,
        so `units` fails. The fourth reads as a deck, and `reach` refuses it."""
        for requires, when, unless, said in (
                (["or", ["is", "service", "0"], ["not", ["is", "service", "0"]]], ["is", "category", "A"], None, "so no part can break it"),
                (["and", ["is", "service", "0"], ["is", "service", "1"]], ["is", "category", "A"], None, "so no part can meet it"),
                (["is", "service", "0"], ["and", ["is", "category", "A"], ["is", "category", "B"]], None, "its `when` holds for no combination"),
                (["is", "service", "0"], ["is", "category", "A"], ["is", "service", "1"], "requires what holds at every one of the 1 combinations of the names of its keys at which it answers, of 4"),
                (["is", "service", "1"], ["is", "category", "A"], ["is", "service", "1"], "requires what holds at none of the 1 combinations of the names of its keys at which it answers, of 4"),
                (["is", "service", "0"], ["is", "category", "A"], ["is", "category", "A"], "answers at none of the 4 combinations")):
            with self.subTest(requires=requires, when=when, unless=unless):
                code, printed = self.accepted({"rules": [hoist_rule(when=when, requires=requires)],
                                               **({"unless": [{"mechanism": "hoist.category", "why": "made up", "when": unless}]} if unless else {})})
                self.assertEqual(code, 1, printed)
                self.assertIn("hoist.category: REFUSED", printed)
                self.assertIn(said, printed)
                self.assertNotIn("widen", printed, "no range of the task changes a key")

    def test_a_requirement_over_more_combinations_than_the_check_tries_is_not_admitted_in_silence(self):
        """Thirteen keys of two names take 8,192 combinations, over the 4,096 that are tried. The
        rule is admitted, since nothing shows it wrong, and `reach` is `none` and says that it was
        not tried in full. It gives no advice about ranges."""
        keys = [f"k{n:02d}" for n in range(13)]
        task = {**HOIST, "types": [{"type": "hoist", "what": "a hoist", "fields": [{"name": name, "one_of": ["no", "yes"], "what": name} for name in keys]}]}
        always = ["or", *(["is", name, "yes"] for name in keys), ["and", *(["is", name, "no"] for name in keys)]]
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "task.json").write_text(json.dumps(task), encoding="utf-8")
            (Path(tmp) / "rules.json").write_text(json.dumps({"rules": [hoist_rule(requires=always)]}), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = acceptance.main([str(Path(tmp) / "task.json"), str(Path(tmp) / "rules.json")])
        printed = out.getvalue()
        self.assertEqual(code, 0, printed)
        self.assertRegex(printed, r"reach +none +made-up/category: what it requires was not tried in full: its 13 keys take over 4,096 combinations")
        self.assertNotIn("widen", printed)


SWITCHES = [f"k{n:02d}" for n in range(13)]
PANEL = kind("panel", *(key(name, "no", "yes") for name in SWITCHES))


def panel(*rules: dict) -> dict:
    return made_up([PANEL], [asks("panel.set", "panel")], list(rules))


def always(keys: list[str]) -> list:
    """A condition that holds for every combination of these keys: one of them is yes, or all of them are no."""
    return ["or", *(["is", name, "yes"] for name in keys), ["and", *(["is", name, "no"] for name in keys)]]


class TheDeckReaderTriesARequirement(unittest.TestCase):
    """The decision, in the reader of a deck: the kernel and petra/grid.py refuse a `requires`
    that holds for every combination of the names of the keys it and its `when` read, or for
    none, when the combinations are at most 4,096 and trying it keeps the deck within
    1,000,000: the combinations times the sizes of the two conditions, over the rules tried
    so far. Past either, the rule is left to the acceptance check."""

    def test_a_requirement_no_part_can_break_or_meet_is_refused_by_the_kernel_and_the_grid(self):
        from tests.test_deck_features import no_deck, reads

        hoist = kind("hoist", key("category", "A", "B"), key("service", "0", "1"), {"name": "lugs", "type": "lug", "as": ["top", "bottom"], "what": "its lugs"})
        lug = kind("lug", key("bore", "machined", "cut"))

        def deck(**body) -> dict:
            return made_up([lug, hoist], [asks("hoist.category", "hoist")], [rule("category", "hoist", "hoist.category", **body)])

        for body, said in ((dict(requires=["or", ["is", "service", "0"], ["not", ["is", "service", "0"]]]), "so no part can break it"),
                           (dict(requires=["or", ["is", "service", "0"], ["is", "service", "1"]]), "so no part can break it"),
                           (dict(when=["and", ["is", "category", "A"], ["is", "service", "0"]], requires=["is", "service", "0"]), "so no part can break it"),
                           (dict(when=["is", "top.bore", "cut"], requires=["not", ["is", "top.bore", "machined"]]), "so no part can break it"),
                           (dict(requires=["and", ["is", "service", "0"], ["is", "service", "1"]]), "so no part can meet it"),
                           (dict(when=["is", "service", "1"], requires=["is", "service", "0"]), "so no part can meet it"),
                           (dict(when=["and", ["is", "category", "A"], ["not", ["is", "category", "A"]]], requires=["is", "service", "0"]), "its `when` holds for no combination")):
            with self.subTest(body):
                mine, its = no_deck(self, deck(**body))
                self.assertIn("rule made-up/category: ", its)
                self.assertIn(said, its)
                self.assertIn(said, mine)
        for body in (dict(when=["is", "category", "A"], requires=["is", "service", "0"]), dict(requires=["is", "top.bore", "machined"]),
                     dict(when=["is", "top.bore", "cut"], requires=["is", "bottom.bore", "machined"]),
                     dict(requires=["or", ["is", "service", "0"], ["is", "category", "B"]])):
            with self.subTest(body):
                reads(self, deck(**body))

    def test_a_requirement_over_4096_combinations_is_left_to_the_acceptance_check(self):
        from tests.test_deck_features import no_deck, reads

        no_deck(self, panel(rule("set", "panel", "panel.set", requires=always(SWITCHES[:12]))))
        reads(self, panel(rule("set", "panel", "panel.set", requires=always(SWITCHES))))

    def test_trying_stops_at_a_million_for_one_deck_in_the_order_of_its_rules(self):
        """A rule over twelve keys of two names is 4,096 combinations of a condition of size 26:
        106,496 for each. Nine are within the million and the tenth is past it, so a requirement
        that no part can break is refused as the ninth rule and read as the tenth."""
        from tests.test_deck_features import no_deck, reads

        honest = ["or", *(["is", name, "yes"] for name in SWITCHES[:12]), ["and", *(["is", name, "yes"] for name in SWITCHES[:12])]]
        self.assertEqual((grid._weight(grid.read_deck(json.dumps(panel(rule("set", "panel", "panel.set", requires=honest)))).rules[0].requires), 4096 * 26), (26, 106_496))
        empty = always(SWITCHES[:12])

        def deck(before: int) -> dict:
            return panel(*(rule(f"set{n}", "panel", "panel.set", requires=honest) for n in range(before)), rule("empty", "panel", "panel.set", requires=empty))

        mine, its = no_deck(self, deck(8))
        self.assertIn("rule made-up/empty: what it requires holds for every combination", its)
        reads(self, deck(9))


# --- 3. the order of a join -------------------------------------------------------------------------------

PLATE = kind("plate", size("t"), key("stiff", "yes", "no"))
LINK = kind("link", {"name": "plates", "type": "plate", "as": ["top", "bottom"], "what": "its two plates"})
BEARING = made_up([PLATE, LINK],
                  [asks("link.bear", "link", unless={"when": ["and", ["is", "top.stiff", "yes"], ["is", "bottom.stiff", "no"]], "why": "made up"}),
                   asks("link.size", "link")],
                  [rule("bear", "link", "link.bear", le=[["q", "10", "mm"], ["min", "top.t", "bottom.t"]]),
                   rule("size", "link", "link.size", le=[["q", "1", "mm"], "top.t"])])
PLATES = part("plate", "p1", t="5 mm", stiff="yes") + "\n" + part("plate", "p2", t="5 mm", stiff="no")


class JoinOrder(unittest.TestCase):
    @KERNEL
    def test_the_order_of_a_join_alone_does_not_turn_a_fail_into_a_pass(self):
        """`plates p2 p1`: the line link.bear applies and its cell is refuted, FAIL. `plates p1
        p2`: the same plates with the same keys and sizes, and the line cannot arise, PASS. The
        card is the same; nothing it states says which plate is on top."""
        verdicts = set()
        for order in ("p2 p1", "p1 p2"):
            mine, status, said, differ = both(BEARING, design(PLATES, part("link", "L", plates=order)))
            self.assertEqual(differ, "")
            verdicts.add(status)
        self.assertNotEqual(verdicts, {"PASS", "FAIL"}, "only the order of the join differs")


if __name__ == "__main__":
    unittest.main()
