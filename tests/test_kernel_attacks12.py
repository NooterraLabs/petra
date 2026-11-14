"""The twelfth hostile review, of the first three steps of phase 1: the kernel's verdict as the only one by every
way into a check, and no pass for a design whose cells the kernel did not work out from a deck of rules. It began
with an hour of the attacker of bench/attack, which needs no model. One class per finding.

  A   docs/format.md said what each file has, and not that a key may not be left out. The clean-room reading,
      written from that page, read a card with no `cases`, a design with no `quantities` and a deck.json with no
      `constants` as files with empty lists, and gave PASS where the kernel refuses the file: 40 of 305 files with
      one key left out. The kernel was right and the page was silent. The page now lists the keys that may be
      left out, and these tests hold the kernel to that list, key by key.
  B   The page did not say what a key written twice in one object reads as. The kernel and petra/grid.py read
      the last value, and the clean-room reading refused the file. The page now says the last value is read.
  C   The page did not say how far the rules go after a broken one, and two readers of one ill-formed file
      listed other rules: one stopped at a shape finding where the other went on to Parts, and the reverse. The
      page now says it: a broken item is left out and the rest is read, a file that does not read whole stops the
      kernel when it is the card, the design or deck.json, and a given that a refused line names is still read.
  D   `petra check --json`, `petra.check` and the server's structured content gave a design of an old kind the
      kernel's UNKNOWN as its `status`, and under it the Python checker's own: `"status": "PASS"` for each claim
      in `verdicts`, and for the design after each move of `repair`. A caller that read the claims saw 400 kV on
      a 750 V cable pass each of them. No `status` of that JSON is a pass now: the Python checker's PASS and
      MARGINAL read UNKNOWN there, as they do in a recall.
"""
import copy
import hashlib
import json
import unittest
from pathlib import Path

import petra
import petra.lang
from petra import grid, mcp
from petra.files import read_pair
from petra.registry import build_registry
from tests.test_deck_features import KERNEL
from tests.test_kernel_grid import ask

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "deck"

MAY_BE_LEFT_OUT = {
    "card": {(): {"states", "tests", "probability_claims"}, ("inputs",): {"case", "on", "field"}, ("waivers",): {"by"}, ("states",): {"by"}},
    "design": {(): {"parts"}},
    "deck": {(): {"rules"}, ("rules",): {"name", "hash"}, ("domains", "size"): {"about"}, ("domains", "input"): {"about"}},
    "proofs": {("cells",): {"tape", "partition", "point", "which", "rule", "completion", "why"}, ("cells", "completion"): {"keys", "loads"}},
}
"""docs/format.md, "Keys": the keys that a file, an item or a cell may leave out, by the file and the place of
the object in it. `rules` of deck.json is read only for being there, so nothing of it is missed."""


def lap(name: str) -> dict[str, str]:
    """The files `petra check` hands the kernel for an example of the shipped deck."""
    read = petra.lang.parse_design((EXAMPLES / f"{name}.card").read_text(encoding="utf-8"), (EXAMPLES / f"{name}.petra").read_text(encoding="utf-8"),
                                   f"{name}.petra", build_registry())
    return grid.check(read, grid.owner(read))[1]


def rebound(files: dict[str, str]) -> dict[str, str]:
    """The files with the design naming the card by the hash of the card as it now stands."""
    design = json.loads(files["design"])
    if "card" not in design:
        return files
    design["card"] = "sha256:" + hashlib.sha256(files["card"].encode("utf-8")).hexdigest()
    return {**files, "design": json.dumps(design, indent=1)}


def drops(body: dict):
    """(place, key, the file without that key), once for each key at each place of the file."""
    seen = set()

    def walk(node, path, trail):
        if isinstance(node, dict):
            for key in list(node):
                if (path, key) not in seen:
                    seen.add((path, key))
                    changed = copy.deepcopy(body)
                    target = changed
                    for step in trail:
                        target = target[step]
                    del target[key]
                    yield path, key, changed
            for key, value in node.items():
                yield from walk(value, path + (key,), trail + (key,))
        elif isinstance(node, list):
            for n, value in enumerate(node):
                yield from walk(value, path, trail + (n,))

    yield from walk(body, (), ())


def rules_of(said: dict) -> set[tuple[str, str]]:
    return {(f["file"], f["rule"]) for f in said["findings"]}


@KERNEL
class AKeyLeftOut(unittest.TestCase):
    def test_the_kernel_refuses_a_file_without_a_key_that_the_page_does_not_let_it_leave_out(self):
        for name in ("lap_pass", "lap_fail", "lap_unknown"):
            files = lap(name)
            for file in ("card", "design", "deck", "proofs"):
                may = MAY_BE_LEFT_OUT[file]
                for place, key, changed in drops(json.loads(files[file])):
                    if file == "proofs" and place[:2] == ("cells", "point"):
                        continue      # the labels of a point are no keys of the format
                    if file == "deck" and place == ("domains", "input") and key != "about":
                        continue      # a dimension with no floor is a deck.json with other floors: type rule 8, below
                    said = ask(rebound({**files, file: json.dumps(changed, indent=1)}))
                    with self.subTest(example=name, file=file, place=".".join(place), key=key):
                        if key in may.get(place, ()):
                            # A key that may be left out is no shape finding of its file. What it leaves out may break another rule.
                            self.assertNotIn((file, "shape"), rules_of(said))
                        else:
                            self.assertEqual(said["verdict"], "ILL-FORMED", "the page lets no reader take this file")

    def test_a_card_a_design_and_a_deck_with_a_list_left_out_are_not_files_with_an_empty_list(self):
        files = lap("lap_pass")
        self.assertEqual(ask(files)["verdict"], "PASS")
        for file, key in (("card", "cases"), ("card", "claims"), ("card", "environment"), ("design", "params"), ("design", "quantities"),
                          ("deck", "constants")):
            with self.subTest(file=file, key=key):
                body = json.loads(files[file])
                del body[key]
                said = ask(rebound({**files, file: json.dumps(body, indent=1)}))
                self.assertEqual((said["verdict"], rules_of(said)), ("ILL-FORMED", {(file, "shape")}), "the clean-room reading gave PASS")
                self.assertEqual([f["item"] for f in said["findings"]], [""], "it is a finding of the whole file")

    def test_a_deck_of_rules_with_no_name_is_refused(self):
        files = lap("lap_pass")
        deck = json.loads(files["rules"])
        del deck["name"]
        said = ask({**files, "rules": json.dumps(deck)})
        self.assertEqual((said["verdict"], rules_of(said)), ("ILL-FORMED", {("rules", "shape")}))
        del deck["about"]
        deck["name"] = "aisc360"
        self.assertEqual(ask({**files, "rules": json.dumps(deck)})["verdict"], "PASS", "a deck may leave out `about`, and no other key of its own")


def twice(text: str, key: str, first: str) -> str:
    """The file with `key` of its outermost object written twice: `first`, and then the value it has."""
    assert text.lstrip().startswith("{")
    return "{" + f"{json.dumps(key)}: {first}," + text.lstrip()[1:]


@KERNEL
class AKeyWrittenTwice(unittest.TestCase):
    def test_the_last_value_is_read_and_the_file_is_not_refused(self):
        files = lap("lap_pass")
        for file, key, first in (("design", "quantities", "[]"), ("design", "name", '"another"'), ("deck", "constants", '"none"'),
                                 ("proofs", "cells", "7"), ("rules", "rules", "[]"), ("rules", "grid", "[]")):
            with self.subTest(file=file, key=key):
                said = ask({**files, file: twice(files[file], key, first)})
                self.assertEqual((said["verdict"], said["findings"]), ("PASS", []))

    def test_a_card_with_a_key_twice_is_another_file_than_the_one_the_design_names(self):
        files = lap("lap_pass")
        doubled = {**files, "card": twice(files["card"], "waivers", "[]")}
        self.assertEqual(rules_of(ask(doubled)), {("design", "types.1")}, "the hash is of the bytes")
        self.assertEqual(ask(rebound(doubled))["verdict"], "PASS", "and with its own hash the last value is read")

    def test_the_first_value_decides_nothing(self):
        files = lap("lap_pass")
        card = json.loads(files["card"])
        bare = rebound({**files, "card": json.dumps({**card, "waivers": []}, indent=1)})
        self.assertEqual(ask(bare)["verdict"], "UNKNOWN", "with no waiver the lap's open lines are open")
        # The waivers first and the empty list last: a reader that kept the first value would pass it.
        first = rebound({**files, "card": twice(json.dumps({**card, "waivers": []}, indent=1), "waivers", json.dumps(card["waivers"]))})
        self.assertEqual(ask(first)["verdict"], "UNKNOWN")


@KERNEL
class AfterABrokenRule(unittest.TestCase):
    def test_a_broken_item_is_left_out_and_the_rest_is_read(self):
        files = lap("lap_pass")
        card = json.loads(files["card"])
        given = next(i for i in card["inputs"] if "on" not in i)
        given["lo"] = "0/5"
        said = ask(rebound({**files, "card": json.dumps(card, indent=1)}))
        self.assertEqual(rules_of(said), {("card", "shape"), ("design", "parts.3")}, "the part that reads the given finds none")

    def test_a_part_with_a_line_that_does_not_read_is_left_out_whole(self):
        files = lap("lap_pass")
        design = json.loads(files["design"])
        plate = design["parts"][0]
        number = next(a["number"] for ln in plate["lines"] for a in ln["args"] if "number" in a)
        number["hi"] = "1.5"
        said = ask({**files, "design": json.dumps(design, indent=1)})
        self.assertEqual(rules_of(said), {("design", "shape"), ("design", "parts.5"), ("card", "parts.6")})
        self.assertEqual([f["item"] for f in said["findings"] if f["rule"] == "shape"], ["parts[0]"])

    def test_the_kernel_stops_at_a_card_a_design_or_a_deck_that_does_not_read_whole(self):
        files = lap("lap_pass")
        for file, change in (("design", lambda d: d.update(parts="none")), ("deck", lambda d: d["domains"]["size"].update(min="1 ")),
                             ("card", lambda d: d.update(name=7))):
            with self.subTest(file=file):
                body = json.loads(files[file])
                change(body)
                said = ask(rebound({**files, file: json.dumps(body, indent=1)}) if file == "card" else {**files, file: json.dumps(body, indent=1)})
                self.assertEqual((rules_of(said), [f["item"] for f in said["findings"]]), ({(file, "shape")}, [""]))

    def test_a_design_with_no_parts_is_one_with_no_part_for_the_rules_of_parts(self):
        files = lap("lap_pass")
        design = json.loads(files["design"])
        del design["parts"]
        said = ask({**files, "design": json.dumps(design, indent=1)})
        self.assertEqual(rules_of(said), {("card", "types.7"), ("deck", "types.7"), ("card", "parts.6"), ("card", "parts.7")})

    def test_a_given_that_a_refused_line_names_is_read(self):
        files = lap("lap_pass")
        design = json.loads(files["design"])
        lines = {ln["field"]: ln for ln in design["parts"][0]["lines"]}
        lines["Fy"]["args"], lines["Fu"]["args"] = lines["Fu"]["args"], lines["Fy"]["args"]
        said = ask({**files, "design": json.dumps(design, indent=1)})
        self.assertEqual(rules_of(said), {("design", "parts.3")}, "no finding of Parts 6 for the two givens")

    def test_a_floor_left_out_of_deck_json_is_a_deck_with_other_floors(self):
        files = lap("lap_pass")
        deck = json.loads(files["deck"])
        del deck["domains"]["input"]["length"]["strict"]
        said = ask({**files, "deck": json.dumps(deck, indent=1)})
        self.assertEqual(rules_of(said), {("deck", "shape"), ("deck", "types.8")}, "the floor is left out, and the rest is not core.json's")


ROOT = Path(__file__).resolve().parents[1]
PASSES = ("PASS", "PASS_WAIVED", "MARGINAL")


def statuses(node, place: str = "") -> list[tuple[str, str]]:
    """Each value under a key named `status`, anywhere in a JSON, with its place."""
    if isinstance(node, dict):
        return [found for key, value in node.items()
                for found in ([(f"{place}.{key}", value)] if key == "status" else statuses(value, f"{place}.{key}"))]
    if isinstance(node, list):
        return [found for value in node for found in statuses(value, f"{place}[]")]
    return []


@KERNEL
class NoStatusInsideTheJsonIsAPass(unittest.TestCase):
    CABLE = "corpus/cases/audit/c4_400kv_on_750v_cable.petra"      # must not pass, and the Python checker passes each of its claims
    BRACKET = "corpus/cases/pilot/bracket_from_the_arm.petra"      # fails, with moves after which the Python checker refutes nothing

    def said(self, path: str) -> dict:
        card, text = read_pair(str(ROOT / path), None)
        return petra.check(card, text, path=path)

    def test_no_claim_of_a_design_with_no_deck_has_the_status_of_a_pass(self):
        said = self.said(self.CABLE)
        self.assertEqual(said["status"], "UNKNOWN")
        self.assertTrue(said["verdicts"])
        self.assertEqual([found for found in statuses(said) if found[1] in PASSES], [], "each claim read PASS")

    def test_no_move_of_a_repair_leaves_a_design_with_the_status_of_a_pass(self):
        said = self.said(self.BRACKET)
        self.assertEqual(said["status"], "FAIL")
        self.assertTrue(said["repair"]["moves"])
        self.assertEqual([found for found in statuses(said) if found[1] in PASSES], [], "the design after a move read PASS")
        self.assertIn("UNKNOWN", {value for place, value in statuses(said["repair"])}, "after a move that refutes nothing the design is not known to pass")

    def test_the_servers_structured_content_holds_none_either(self):
        card, text = read_pair(str(ROOT / self.CABLE), None)
        text_out, structured = mcp._check({"design": text, "card": card})
        self.assertEqual(structured["status"], "UNKNOWN")
        self.assertEqual([found for found in statuses(structured) if found[1] in PASSES], [])


if __name__ == "__main__":
    unittest.main()
