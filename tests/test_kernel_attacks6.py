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


class DeadBranch(unittest.TestCase):
    def test_what_only_the_branch_of_a_name_no_cell_holds_reads_is_read_by_nothing_in_all_three(self):
        """A quantity: `t` is named by the branch Z alone. A part has a = 30 mm, so its name is
        B, and t = 1000 m. At e4c3cde the grid gives PASS with one cell; the kernel gives the
        same proved cell and an `unread` cell for p.t, UNKNOWN, and verify.differs says so.

        A load: P is named by the branch Z alone, and case g puts it on p. At e4c3cde the grid
        has `m/g` proved and gives PASS; the kernel has `m`, with no case, and `unread` `P/g`.

        The acceptance check, on the first rule as a transcription of a task: at e4c3cde `reads`
        passes, `every field and every load is read`, and the line is admitted with exit 0.

        The kernel's reading is the one kept here: what no part can reach is read by nothing,
        so it is an `unread` cell and the verdict does not rest on it."""
        quantity = made_up([kind("w", size("a"), size("t"))], [asks("w.m", "w")],
                           [rule("m", "w", "w.m", le=[["case", BY_CATEGORY, {"B": "a", "C": ["mul", "a", "2"], "Z": "t"}], ["q", "60", "mm"]])], [CATEGORY])
        loaded = made_up([kind("w", size("a"), size("cap", "force"), loads=[{"name": "P", "dim": "force", "least": "0 N", "what": "P"}])], [asks("w.m", "w")],
                         [rule("m", "w", "w.m", le=[["case", BY_CATEGORY, {"B": ["q", "1", "N"], "C": ["q", "1", "N"], "Z": ["load", "P"]}], "cap"])], [CATEGORY])
        for name, deck, text, card in (("a quantity", quantity, design(part("w", "p", a="30 mm", t="1000 m")), HEAD),
                                       ("a load", loaded, design(part("w", "p", a="30 mm", cap="10 N")), HEAD + load("g", "p P in [0 N, 5 N]"))):
            with self.subTest(name):
                if not verify.binary():
                    self.skipTest("no petra-verify is built here and PETRA_VERIFY names none")
                mine, status, said, differ = both(deck, text, card)
                self.assertEqual(differ, "", "the grid and the kernel list the same cells and give the same verdict")
                self.assertNotEqual(status, "PASS", "no cell checks what the branch Z alone reads")
        with self.subTest("the acceptance check"):
            task = {"format": acceptance.TASK, "name": "made-up", "about": "made up", "rows": [CATEGORY],
                    "types": [{"type": "w", "what": "a w", "fields": [{"name": "a", "dim": "length", "what": "a", "range": ["1 mm", "100 mm"]},
                                                                    {"name": "t", "dim": "length", "what": "t", "range": ["1 mm", "100 mm"]}]}],
                    "asks": [{"type": "w", "mechanism": "w.m", "what": "m", "anchor": ANCHOR}]}
            reading = acceptance.Reading(acceptance.read_task(task), acceptance.read_transcription({"rules": quantity["rules"]}))
            found = acceptance.reads(reading)
            self.assertEqual(found.outcome, "fail", found.detail)
            self.assertIn("w.t", found.detail)


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
