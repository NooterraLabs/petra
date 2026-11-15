"""The kernel on a design checked against a deck of rules (kernel/Petra/Deck.lean, Grid.lean).

petra-verify reads the deck's own file, the card and the design, and works out every cell
and every tape itself. proofs.json gives it hints: a partition or a point to try on a cell,
named by subject, mechanism and entry. docs/format.md states the rules.

Each test takes the files `petra check` writes for an honest pair, changes one of them as
someone who wants a better verdict might, and reads what the kernel settles. Most use
STRIPS, the deck made up for tests/test_grid.py, and some the deck that ships. The tests
are skipped when no kernel is built.
"""
import copy
import hashlib
import contextlib
import io
import json
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

import petra
from petra import export, grid, verify
from petra.files import read_pair
from petra.units import CUSTOMARY, UNITS
from tests.test_grid import CARD, DESIGN, STRIPS, UNKNOWN_KEYS

ROOT = Path(__file__).resolve().parents[1]
NO_WAIVER = CARD.replace('waive strip.creep on s by "t@example.org" reason "it is a test"\n', "")
OVER = CARD.replace("[0 A, 2 A]", "[0 A, 2.01 A]")
"""A card whose current is over what the strips carry, so strip.heat is refuted."""


def strips(card: str = CARD, design: str = DESIGN, rules: dict = STRIPS) -> dict[str, str]:
    """The files of the pair against the test deck: with the grid's hints when the grid
    checks the design, and as written when it refuses it."""
    deck = grid.read_deck(json.dumps(rules))
    with mock.patch.object(grid, "decks", lambda: (deck,)):
        parsed = petra.lang.parse_design(card, design, "strips.petra")
        try:
            return grid.check(parsed, deck)[1]
        except grid.ComponentError:
            return grid.bundle(parsed, deck)


def lap(name: str, *swap: tuple[str, str]) -> dict[str, str]:
    """The files of a design of examples/deck, after the replacements in its text."""
    path = ROOT / "examples" / "deck" / f"{name}.petra"
    card, design = read_pair(path)
    for old, new in swap:
        assert old in design, old
        design = design.replace(old, new, 1)
    parsed = petra.lang.parse_design(card, design, str(path))
    return grid.check(parsed, grid.owner(parsed))[1]


def changed(files: dict[str, str], name: str, change) -> dict[str, str]:
    """The files with one of them changed by `change`, which takes its JSON. A changed card
    keeps the design that answers it: the design names the new card's hash, as an honest
    exporter would write it."""
    body = json.loads(files[name])
    change(body)
    out = {**files, name: export.text(body)}
    if name == "card":
        design = json.loads(files["design"])
        design["card"] = "sha256:" + hashlib.sha256(out["card"].encode("utf-8")).hexdigest()
        out["design"] = export.text(design)
    return out


def hint(body: dict, mechanism: str, entry: str | None = None) -> dict:
    """The one hint of proofs.json for the mechanism, to change in place."""
    (found,) = [c for c in body["cells"] if c["mechanism"] == mechanism and entry in (None, c["entry"])]
    return found


def ask(files: dict[str, str], without: tuple[str, ...] = ()) -> dict:
    return verify.ask(verify.binary(), {name: text for name, text in files.items() if name not in without})


def cell(said: dict, mechanism: str, entry: str | None = None) -> dict:
    assert not said["findings"], said["findings"]
    found = [c for c in said["cells"] if c["mechanism"] == mechanism and entry in (None, c["entry"])]
    assert len(found) == 1, (mechanism, entry, said["cells"])
    return found[0]


def states(said: dict) -> list[tuple[str, str, str, str]]:
    return [(c["subject"], c["mechanism"], c["entry"], c["state"]) for c in said["cells"]]


def findings(said: dict) -> str:
    """Why the kernel finds the files ill formed, as one text, or the empty text."""
    assert (said["verdict"] == "ILL-FORMED") == bool(said["findings"]), said
    assert not (said["findings"] and said["cells"]), "with a finding the kernel settles no cell"
    return "; ".join(f"{f['rule']} {f['file']} {f['item']}: {f['why']}" for f in said["findings"])


def part(body: dict, name: str) -> dict:
    return next(p for p in body["parts"] if p["name"] == name)


def line(body: dict, name: str, field: str) -> dict:
    return next(ln for ln in part(body, name)["lines"] if ln["field"] == field)


def si(value: str) -> str:
    """A length in millimetres as design.json writes it, in metres."""
    return export.number(Fraction(value) / 1000)


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Kernel(unittest.TestCase):
    def assertIllFormed(self, files: dict[str, str], says: str, without: tuple[str, ...] = ()) -> None:
        self.assertIn(says, findings(ask(files, without)))


class TheKernelsOwnCells(Kernel):
    def test_the_kernel_lists_the_grids_cells_and_settles_each_itself(self):
        files = strips()
        said = ask(files)
        self.assertEqual((said["verdict"], said["counts"]), ("PASS", {"proved": 4, "refuted": 0, "not_applicable": 2, "waived": 1, "open": 0}))
        self.assertEqual(states(said), [(c["subject"], c["mechanism"], c["entry"], c["state"]) for c in json.loads(files["proofs"])["cells"]])
        self.assertEqual(said["hashes"]["rules"], "sha256:" + hashlib.sha256(files["rules"].encode("utf-8")).hexdigest())
        self.assertEqual(said["ignored_hints"], 0)
        self.assertEqual([w["mechanism"] for w in said["waived"]], ["strip.creep"])

    def test_proofs_hold_no_tape_and_a_tape_in_one_is_never_read(self):
        files = strips()
        self.assertNotIn('"tape"', files["proofs"])
        self.assertNotIn('"nodes"', files["proofs"])
        planted = changed(files, "proofs", lambda b: hint(b, "strip.hole").update(tape={"inputs": "nonsense", "nodes": [["c", "-1"]], "roots": [0]}))
        self.assertEqual(states(ask(planted)), states(ask(files)), "not even its shape is read")

    def test_with_no_proofs_every_cell_is_there_and_no_rule_is_proved(self):
        said = ask(strips(), without=("proofs",))
        self.assertEqual((said["verdict"], said["counts"]), ("UNKNOWN", {"proved": 0, "refuted": 0, "not_applicable": 2, "waived": 1, "open": 3}))
        self.assertEqual([c["mechanism"] for c in said["cells"]], ["strip.heat", "strip.hole", "strip.bow", "strip.creep", "strip.spark", "strip.tide"])
        self.assertEqual({c["claimed"] for c in said["cells"]}, {None})

    def test_a_proof_that_needs_its_ranges_split_takes_the_partition_by_label(self):
        files = strips(card=CARD.replace("[0.5 mm, 0.6 mm]", "[1 mm, 3 mm]"))
        split = hint(json.loads(files["proofs"]), "strip.bow")["partition"]
        self.assertEqual(split["input"], "in:strips.s.gap")
        self.assertEqual(cell(ask(files), "strip.bow")["state"], "proved")
        whole = ask(changed(files, "proofs", lambda b: hint(b, "strip.bow").update(partition="leaf")))
        self.assertEqual((cell(whole, "strip.bow")["state"], cell(whole, "strip.bow")["reason"]), ("open", "leaf 0: root 0 is above zero"))
        other = ask(changed(files, "proofs", lambda b: hint(b, "strip.bow")["partition"].update(input="in:strips.s.T")))
        self.assertEqual(cell(other, "strip.bow")["reason"], "the partition splits in:strips.s.T, which the tape does not read")

    def test_a_design_of_a_kind_no_deck_has_has_no_files(self):
        """There is no deck of rules to write and no type that says what its lines are, so the exporter writes nothing and says why."""
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(export.NoDeck) as refused:
            export.export(str(ROOT / "corpus" / "cases" / "old" / "circuit_pass.petra"), Path(tmp, "out"))
        self.assertIn("no deck of rules has a part of kind circuit", str(refused.exception))
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()) as said:
            self.assertEqual(export.main([str(ROOT / "corpus" / "cases" / "old" / "circuit_pass.petra"), "--out", str(Path(tmp, "out"))]), 2)
            self.assertFalse(Path(tmp, "out").exists())
        self.assertIn("nothing written", said.getvalue())

    """A card that was issued for a deck of rules is not checked as a design of the models'
    kinds (type rule 7). The files of a deck design carry marks, and each mark is refused
    with a design that has no parts or with no --rules. What is left is a card.json written
    without the marks, which has another hash, and a verdict that says where its cells came from."""

    FORGED = {"inputs": [{"label": "dsg:x", "lo": "0", "hi": "1"}], "nodes": [["c", "-1"]], "roots": [0]}

    def forged(self, files: dict[str, str]) -> dict[str, str]:
        """The files with `parts` removed and with proofs.json saying what the designer likes:
        one cell proved by a tape that reads nothing of the card, and the rest not applicable."""
        cells = [{"subject": "s", "mechanism": "strip.heat", "entry": "", "state": "proved", "tape": self.FORGED, "partition": "leaf"},
                 {"subject": "s", "mechanism": "strip.hole", "entry": "", "state": "not_applicable", "why": "forged"}]
        return {**changed(files, "design", lambda b: b.pop("parts")), "proofs": export.text({"format": "petra-proofs/0", "cells": cells})}

    def test_the_cells_come_from_the_rules_and_the_verdict_says_so(self):
        files = strips()
        said = ask(files)
        self.assertEqual((said["cells_from"], said["hashes"]["rules"]), ("rules", "sha256:" + hashlib.sha256(files["rules"].encode("utf-8")).hexdigest()))
        self.assertEqual(list(said)[:3], ["verdict", "hashes", "cells_from"], "printed with the verdict, before anything else")

    def test_an_honest_card_with_no_parts_and_no_rules_is_ill_formed(self):
        files = self.forged(strips(card=OVER))
        self.assertEqual(ask(strips(card=OVER))["verdict"], "FAIL", "the honest files, with the deck, fail")
        said = ask(files, without=("rules",))
        self.assertEqual((said["verdict"], said["cells"], said["cells_from"], said["hashes"]["rules"]), ("ILL-FORMED", [], "proofs", None))
        lacks = "which only a design checked against a deck of rules has, and the design has no parts and --rules names none"
        self.assertEqual([(f["rule"], f["file"], f["item"], f["why"]) for f in said["findings"]], [
            ("types.7", "card", "run.s.current", f"is a load on a part, {lacks}"),
            ("types.7", "card", "tests", f"is a key of the card, {lacks}"),
            ("types.7", "card", "probability_claims", f"is a key of the card, {lacks}"),
            ("types.7", "deck", "rules", f"names a deck of rules, {lacks}")])

    def test_each_mark_alone_is_refused(self):
        files = self.forged(strips())

        def only(mark: str) -> dict[str, str]:
            """The forged files with every mark but `mark` taken out, by a designer who rewrites the card."""
            def card(body: dict) -> None:
                if mark != "load":
                    body["inputs"] = [{k: v for k, v in i.items() if k not in ("on", "field")} for i in body["inputs"]]
                for key in ("tests", "probability_claims"):
                    if mark != key:
                        body.pop(key)
            out = changed(files, "card", card)
            return out if mark == "rules" else changed(out, "deck", lambda b: b.pop("rules"))

        for mark, says in (("load", "types.7 card run.s.current: is a load on a part"), ("tests", "types.7 card tests: is a key of the card"),
                           ("probability_claims", "types.7 card probability_claims: is a key of the card"), ("rules", "types.7 deck rules: names a deck of rules")):
            with self.subTest(mark=mark):
                self.assertIllFormed(only(mark), says, without=("rules",))
        self.assertIllFormed(strips(), "types.7 card tests: is a key of the card, which only a design checked against a deck of rules has, and --rules names none",
                             without=("rules",))

    def test_a_card_that_only_waives_is_marked_too(self):
        """The exporter writes `tests` and `probability_claims` into every card of a deck
        design, so a card with no load is refused as well."""
        files = changed(self.forged(strips()), "card", lambda b: b.update(inputs=[i for i in b["inputs"] if "on" not in i]))
        self.assertIllFormed(files, "types.7 card tests", without=("rules",))

    def test_with_every_mark_removed_the_forged_cells_do_not_pass(self):
        """A card.json with no mark and a design with no parts are a design of the models'
        kinds to the kernel, which takes the forged cells as they come. Until 2026-11-14 they
        passed, and only a reader who compared the card's hash, `cells_from` or the hash of
        the rules saw it. With no deck of rules the kernel now passes nothing."""
        honest = strips(card=OVER)
        files = self.forged(honest)

        def unmark(body: dict) -> None:
            body["inputs"] = [{k: v for k, v in i.items() if k not in ("on", "field")} for i in body["inputs"]]
            body.pop("tests"), body.pop("probability_claims")
        files = changed(changed(files, "card", unmark), "deck", lambda b: b.pop("rules"))
        said = ask(files, without=("rules",))
        self.assertEqual((said["verdict"], said["cells_from"], said["hashes"]["rules"], said["counts"]["open"]), ("UNKNOWN", "proofs", None, 0),
                         "the kernel takes the forged cells, and with no deck of rules it passes nothing")
        self.assertNotEqual(said["hashes"]["card"], ask(honest)["hashes"]["card"])


class ChangedCard(Kernel):
    """card.json is changed, and the design names the new card as an honest exporter would."""

    def test_a_card_the_decks_types_do_not_take_is_ill_formed(self):
        files = strips()

        def load(body) -> dict:
            return next(i for i in body["inputs"] if i.get("case"))

        cases = {
            "a load under the least its type takes": (lambda b: load(b).update(lo="-1"), "parts.6 card run.s.current: is under the least current may take"),
            "a current under the floor of its dimension": (lambda b: load(b).update(lo="-1"), "types.4 card run.s.current"),
            "a load on a part that takes none": (lambda b: load(b).update(on="p1"), "parts.6 card run.s.current: a pad takes no load current"),
            "a load on no part": (lambda b: load(b).update(on="nobody"), "parts.6 card run.s.current: a load is put on a part, and nobody is not one"),
            "a load the type lacks": (lambda b: load(b).update(field="force"), "parts.6 card run.s.current: a strip takes no load force"),
            "a load of another dimension": (lambda b: load(b).update(dim="force"), "parts.6 card run.s.current: is a force"),
            "a load that does not say where it is": (lambda b: load(b).pop("on"), "parts.6 card run.s.current: a load has its case, the part it is on and its field"),
            "a waiver of a mechanism the grid does not ask": (lambda b: b["waivers"][0].update(mechanism="strip.melt"), "parts.7 card s/strip.melt"),
            "a waiver on a part of another type": (lambda b: b["waivers"][0].update(subject="p1"), "parts.7 card p1/strip.creep"),
            "a waiver nobody signed": (lambda b: b["waivers"][0].pop("by"), "types.5 card s/strip.creep"),
            "a bound of another dimension": (lambda b: next(i for i in b["inputs"] if i["name"] == "s.gap").update(dim="force"), "parts.3 design s.gap: is a force"),
            "a bound that reaches zero": (lambda b: next(i for i in b["inputs"] if i["name"] == "s.gap").update(lo="0"), "parts.3 design s.gap: is not more than zero"),
            "a bound nobody signed": (lambda b: next(i for i in b["inputs"] if i["name"] == "s.gap").pop("by"), "shape card inputs"),
            "a bound no part reads": (lambda b: b["inputs"].append({"name": "s.spare", "dim": "length", "lo": "1", "hi": "2", "by": "x"}), "parts.6 card s.spare: is no load, and no part reads it"),
            "two bounds of one name": (lambda b: b["inputs"].append(dict(load(b))), "parts.6 card run.s.current: two inputs have this name"),
            "a claim": (lambda b: b["claims"].append({"name": "c", "subject": "s", "quantity": "current", "rel": "<=", "cases": [], "bound": {"dim": "current", "lo": "2", "hi": "2"}}),
                        "parts.8 card claims"),
            "a tests record": (lambda b: b.update(tests=["proof"]), "parts.8 card tests"),
        }
        for what, (change, says) in cases.items():
            with self.subTest(what=what):
                self.assertIllFormed(changed(files, "card", change), says)

    def test_a_card_changed_without_the_design_naming_it_is_ill_formed(self):
        files = strips()
        body = json.loads(files["card"])
        body["waivers"] = []
        self.assertIllFormed({**files, "card": export.text(body)}, "types.1 design card")

    def test_a_pull_below_zero_is_ill_formed_though_a_force_has_no_floor(self):
        files = lap("lap_pass")
        pushed = changed(files, "card", lambda b: next(i for i in b["inputs"] if i.get("case")).update(lo="-1"))
        self.assertEqual(findings(ask(pushed)), "parts.6 card gravity.splice.pull: is under the least pull may take")

    def test_a_waiver_holds_only_when_the_card_lists_it(self):
        files = strips()
        said = ask(changed(files, "card", lambda b: b.update(waivers=[])))
        self.assertEqual((said["verdict"], cell(said, "strip.creep")["claimed"], cell(said, "strip.creep")["state"]), ("UNKNOWN", "waived", "open"))

    def test_a_wider_load_turns_a_proof_open_and_a_second_case_adds_a_cell(self):
        files = strips()

        def wider(body):
            next(i for i in body["inputs"] if i.get("case")).update(hi="3")

        said = ask(changed(files, "card", wider))
        self.assertEqual((said["verdict"], cell(said, "strip.heat", "heat/run")["state"]), ("UNKNOWN", "open"))

        def surge(body):
            body["cases"].append("surge")
            body["inputs"].append({**next(i for i in body["inputs"] if i.get("case")), "name": "surge.s.current", "case": "surge"})

        more = ask(changed(files, "card", surge))
        self.assertEqual([(c["entry"], c["state"]) for c in more["cells"] if c["mechanism"] == "strip.heat"],
                         [("heat/run/where", "proved"), ("heat/run", "proved"), ("heat/surge", "open")], "its range has no hint, so it is open")


class ChangedRules(Kernel):
    """The rules file is changed: one cell of a table, its bytes alone, or so that it no longer holds together."""

    def rules(self, edit) -> dict:
        body = copy.deepcopy(STRIPS)
        edit(body)
        return body

    def test_one_cell_of_a_table_changed_is_another_hash_and_another_verdict(self):
        files = lap("lap_pass")
        honest = ask(files)
        self.assertEqual(honest["verdict"], "PASS")

        def end_distance(body):      # Table J3.4 asks 1 inch of a 3/4 inch bolt, and the design has 1.5 inch
            table = next(r for r in body["rows"] if r["id"] == "aisc360-22/table-J3.4")["table"]
            self.assertEqual(table["cells"][2], "1")
            table["cells"][2] = "2"

        body = json.loads(files["rules"])
        end_distance(body)
        said = ask({**files, "rules": json.dumps(body, indent=1) + "\n"})
        self.assertNotEqual(said["hashes"]["rules"], honest["hashes"]["rules"])
        self.assertEqual(said["hashes"]["deck"], honest["hashes"]["deck"])
        self.assertEqual((said["verdict"], cell(said, "lap.end_distance")["state"]), ("UNKNOWN", "open"))
        label = "dsg:lap-splice-waived.splice."
        point = {label + "diameter": export.number(Fraction(381, 20000)), label + "end": export.number(Fraction(381, 10000))}
        refuted = ask(changed({**files, "rules": json.dumps(body, indent=1) + "\n"}, "proofs", lambda b: hint(b, "lap.end_distance").update(point=point)))
        self.assertEqual((refuted["verdict"], cell(refuted, "lap.end_distance")["state"]), ("FAIL", "refuted"))

    def test_the_same_rules_in_other_bytes_are_another_hash_and_the_same_cells(self):
        files = lap("lap_unknown")
        again = {**files, "rules": json.dumps(json.loads(files["rules"]))}
        self.assertNotEqual(ask(again)["hashes"]["rules"], ask(files)["hashes"]["rules"])
        self.assertEqual(states(ask(again)), states(ask(files)))

    def test_a_rules_file_that_does_not_hold_together_is_ill_formed(self):
        files = strips()
        cases = {
            "a sum of two dimensions in a rule": (lambda b: b["rules"][3]["le"].__setitem__(0, ["add", "screw", ["q", "0.1", "A"]]), "rule test/spark: add of different dimensions"),
            "a comparison of two dimensions": (lambda b: b["rules"][0]["le"].__setitem__(1, "width"), "rule test/heat: `le` compares two dimensions"),
            "a range of two dimensions": (lambda b: b["rules"][0]["where"][0]["le"].__setitem__(1, ["q", "120", "mm"]), "rule test/heat: `where` compares two dimensions"),
            "a row with a case of another dimension": (lambda b: b["rows"][1]["cases"][0].__setitem__("is", ["q", "1", "mm"]), "row test/derate: case 1 gives another dimension"),
            "a condition that compares two dimensions": (lambda b: b["rows"][1]["cases"][0].__setitem__("when", ["le", "T", ["q", "40", "mm"]]), "row test/derate: a condition compares two dimensions"),
            "a cell of another dimension": (lambda b: b["rows"][0]["table"]["cells"].__setitem__(1, "2 mm"), "row test/limit: a cell is of another dimension"),
            "a band of another dimension": (lambda b: b["rows"][0]["table"]["down"]["bands"].__setitem__(0, ["0 A", "1 mm"]), "row test/limit: the side that reads w has a value of another dimension"),
            "bands out of order": (lambda b: b["rows"][0]["table"]["down"]["bands"].__setitem__(1, ["0.5 mm", "2 mm"]), "row test/limit: the bands of w"),
            "an input bound to another dimension": (lambda b: b["rules"][0]["le"][1][2][2].__setitem__("w", "T"), "rule test/heat: test/limit: the rule binds w to another dimension"),
            "an input not bound": (lambda b: b["rules"][0]["le"][1][2].__setitem__(2, {}), "rule test/heat: test/limit takes w"),
            "a row the deck lacks": (lambda b: b["rules"][1]["le"][0].__setitem__(1, "test/none"), "rule test/hole: test/none is not a row of the deck"),
            "a field the type lacks": (lambda b: b["rules"][1]["le"].__setitem__(1, "depth"), "rule test/hole: depth is not a number, and nothing here has that name"),
            "a load the type lacks": (lambda b: b["rules"][0]["le"].__setitem__(0, ["load", "force"]), "rule test/heat: the type takes no load force"),
            "a key with names the row lacks": (lambda b: b["types"][1]["fields"][5].__setitem__("one_of", ["close", "snug"]), "rule test/hole: fit has names the row lacks"),
            "a rule for a line the grid lacks": (lambda b: b["rules"][0].__setitem__("mechanism", "strip.melt"), "rule test/heat: the grid does not ask strip.melt of strip"),
            "a rule for a line that never arises": (lambda b: b["rules"][0].__setitem__("mechanism", "strip.tide"), "rule test/heat: the grid says strip.tide never arises"),
            "two rules of one id": (lambda b: b["rules"].append(b["rules"][0]), "two rules have one id"),
            "two rows of one id": (lambda b: b["rows"].append(b["rows"][0]), "two rows have one id"),
            "an unknown key in the deck": (lambda b: b.update(notes="x"), "notes is not a key here"),
            "an unknown key in a rule": (lambda b: b["rules"][0].update(unless="x"), "rule test/heat: unless is not a key here"),
            "an unknown key in a row": (lambda b: b["rows"][0].update(note="x"), "row test/limit: note is not a key here"),
            "an operator the language lacks": (lambda b: b["rules"][2]["le"].__setitem__(0, ["sin", "gap"]), "rule test/bow: sin with 1 arguments is not in the language"),
            "a unit nobody defined": (lambda b: b["rules"][2]["le"].__setitem__(1, ["q", "4.2", "furlong2"]), "furlong2 is not a unit"),
            "a number with an exponent": (lambda b: b["rules"][2]["le"][0].__setitem__(1, ["sub", ["q", "4e0", "mm"], "gap"]), "4e0 mm is not a quantity"),
            "a name of let defined by itself": (lambda b: b["rules"][2].update(let={"a": ["add", "a", "gap"]}), "rule test/bow: `let` defines a by itself"),
            "a field named like a number": (lambda b: b["types"][0]["fields"][0].update(name="2"), "field 2: 2 is not a name"),
            "another format": (lambda b: b.update(format="petra-rules/1"), "shape rules : format is not petra-rules/0"),
        }
        for what, edit in cases.items():
            with self.subTest(what=what):
                self.assertIllFormed({**files, "rules": json.dumps(self.rules(edit[0]))}, edit[1])
        self.assertIllFormed({**files, "rules": "{"}, "shape rules : not JSON")

    def test_a_key_the_deck_does_not_know_is_refused_wherever_it_stands(self):
        """The same places and keys as the grid's test, and the finding names the key."""
        files = strips()
        for what, (edit, key) in UNKNOWN_KEYS.items():
            with self.subTest(what=what):
                self.assertIllFormed({**files, "rules": json.dumps(self.rules(edit))}, f"{key} is not a key here")

    def test_an_anchor_names_its_standard_and_its_clause(self):
        files = strips()
        for place in ("rows", "grid", "rules"):
            for anchor in ({"standard": "made up"}, {"clause": "1"}, {"standard": "", "clause": "1"}):
                with self.subTest(place=place, anchor=anchor):
                    rules = self.rules(lambda b: b[place][0].__setitem__("anchor", anchor))
                    self.assertIllFormed({**files, "rules": json.dumps(rules)}, "the anchor lacks its standard or its clause")

    def test_bands_are_in_order_and_none_lies_over_another(self):
        files = strips()
        for bands in ([["1 mm", "2 mm"], ["0 mm", "1 mm"], ["2 mm", None]], [["0 mm", "1.5 mm"], ["1 mm", "2 mm"], ["2 mm", None]],
                      [["1 mm", "0 mm"], ["1 mm", "2 mm"], ["2 mm", None]]):
            with self.subTest(bands=bands):
                rules = self.rules(lambda b: b["rows"][0]["table"]["down"].__setitem__("bands", bands))
                self.assertIllFormed({**files, "rules": json.dumps(rules)}, "row test/limit: the bands of w are pairs, the lower end first, in order and none over another")

    def test_the_kernels_unit_table_is_the_one_of_petra_units(self):
        # For each unit, two rules with no input: 1 of the unit is at most, and at least, its SI factor as Python has it.
        table = {**UNITS, **CUSTOMARY}
        rules = []
        for n, (unit, (factor, dim)) in enumerate(table.items()):
            base, scale = next((u, f) for u, (f, d) in table.items() if d == dim)      # the first unit of its dimension, whatever its factor
            one, same = ["q", "1", unit], ["mul", export.number(factor / scale), ["q", "1", base]]
            rules += [{**STRIPS["rules"][2], "id": f"test/unit-{n}-{way}", "le": sides} for way, sides in (("le", [one, same]), ("ge", [same, one]))]
        files = strips(rules=self.rules(lambda b: b.update(rules=rules + [r for k, r in enumerate(STRIPS["rules"]) if k != 2])))
        said = ask(files)
        units = [c for c in said["cells"] if c["mechanism"] == "strip.bow"]
        self.assertEqual((len(units), {c["state"] for c in units}), (2 * len(table), {"proved"}), [c for c in units if c["state"] != "proved"])
        self.assertGreaterEqual(len(table), 67)
        off = self.rules(lambda b: b["rules"][2].update(le=[["q", "1", "inch"], ["q", "25.39999", "mm"]]))
        self.assertEqual(cell(ask({**files, "rules": json.dumps(off)}), "strip.bow", "bow")["state"], "open", "an inch is not under 25.4 mm")

    def test_the_kernel_reads_a_quantity_as_the_deck_writes_it(self):
        # Each way a deck may write 4.2 mm2 on the right of test/bow leaves its proof as it is, and 4.2 mm does not.
        files = strips(card=CARD.replace("[0.5 mm, 0.6 mm]", "[1 mm, 3 mm]"))
        for written in (["q", "4.2", "mm2"], ["q", "21/5", "mm2"], ["q", "4 1/5", "mm2"], ["q", "0.0000042", "m2"], ["mul", ["q", "2.1", "mm"], ["q", "0.2", "cm"]],
                        ["q", "4,200,000", "um"], ["pow", ["q", "17.64", "mm2"], "2"], ["mul", "4.2", ["pow", ["q", "1", "mm"], "2"]],
                        ["div", ["q", "4.2", "mm"], ["pow", ["q", "1", "mm"], "-1"]], ["mul", ["sqrt", ["q", "17.64", "mm2"]], ["q", "1", "mm"]],
                        ["mul", ["pow", ["q", "17.64", "mm2"], "1/2"], ["q", "1", "mm"]], ["mul", ["exp", ["ln", "4.2"]], ["q", "1.0001", "mm2"]]):
            with self.subTest(written=written):
                said = ask({**files, "rules": json.dumps(self.rules(lambda b: b["rules"][2]["le"].__setitem__(1, written)))})
                if written[:2] in (["q", "4,200,000"], ["pow", ["q", "17.64", "mm2"]]):
                    self.assertIn("rule test/bow: `le` compares two dimensions", findings(said), "micrometres and mm4 are not an area")
                else:
                    self.assertEqual((cell(said, "strip.bow")["state"], said["findings"]), ("proved", []))
        lower = ask({**files, "rules": json.dumps(self.rules(lambda b: b["rules"][2]["le"].__setitem__(1, ["q", "3.9", "mm2"])))})
        self.assertEqual(cell(lower, "strip.bow")["state"], "open", "gap (4 mm - gap) reaches 4 mm2, and the old partition proves nothing under it")


if __name__ == "__main__":
    unittest.main()
