"""card.json from the card alone: `python -m petra.export --card-only CARD.card --out DIR`.

For a design of a deck's types, card.json holds nothing that the design chooses. So the
asker can write it from their own card with their own copy of Petra, and compare its hash
with the `card` hash the kernel prints (docs/format.md, "The asker's card"). These tests
hold the exporter to that: the file from the card alone is, byte for byte, the file the
full export writes, for every pair of examples/deck and corpus/cases/deck.
"""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import petra
from petra import export, grid, verify
from petra.files import read_pair
from petra.lang import LoweringError, load_card, load_design
from petra.registry import build_registry
from petra.repair import INPUT_ERRORS

ROOT = Path(__file__).resolve().parents[1]
PAIRS = sorted([*(ROOT / "examples" / "deck").glob("*.petra"), *(ROOT / "corpus" / "cases" / "deck").glob("*.petra")])


def full(design: Path, physics: bool = False) -> dict[str, bytes]:
    """The files the full export writes for the pair, each as its bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        export.export(str(design), Path(tmp), physics=physics)
        return {p.stem: p.read_bytes() for p in Path(tmp).iterdir()}


def alone(card: Path) -> tuple[str, bytes]:
    """The hash `--card-only` prints for the card, and the card.json it writes."""
    with tempfile.TemporaryDirectory() as tmp:
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            code = export.main(["--card-only", str(card), "--out", tmp])
        assert code == 0, code
        return said.getvalue().strip(), Path(tmp, "card.json").read_bytes()


class CardOnly(unittest.TestCase):
    def test_the_card_alone_gives_the_bytes_the_full_export_writes_for_every_deck_pair(self):
        self.assertGreaterEqual(len(PAIRS), 15)
        compared = 0
        for design in PAIRS:
            with self.subTest(design=design.name):
                try:
                    load_design(design)
                except INPUT_ERRORS:
                    continue        # the pair does not lower, so no export writes a card for it
                files = full(design)
                self.assertIn("rules", files, "a pair of these folders is of a deck's types")
                said, body = alone(design.with_suffix(".card"))
                self.assertEqual(body, files["card"], "card.json depends on the design")
                self.assertEqual(said, "sha256:" + hashlib.sha256(files["card"]).hexdigest())
                compared += 1
        self.assertGreaterEqual(compared, 15, "every pair of the two folders lowers today")

    def test_the_hash_is_the_one_the_design_names(self):
        files = full(ROOT / "examples" / "deck" / "lap_pass.petra")
        said, _ = alone(ROOT / "examples" / "deck" / "lap_pass.card")
        self.assertEqual(json.loads(files["design"])["card"], said)

    def test_another_design_for_the_same_card_gets_the_same_card_json(self):
        """The design changes every number it may, and lists its parts and lines another way round."""
        card, design = read_pair(ROOT / "examples" / "deck" / "lap_pass.petra")
        blocks = design.split("\n\n")
        other = "\n\n".join([blocks[0], *reversed(blocks[1:])]).replace("0.375 inch", "0.5 inch").replace("count 3", "count 4")
        self.assertNotEqual(other, design)
        registry = build_registry()
        first = petra.lang.parse_design(card, design, "lap.petra", registry, "lap.card")
        second = petra.lang.parse_design(card, other, "lap.petra", registry, "lap.card")
        deck = grid.owner(first)
        self.assertEqual(grid.bundle(first, deck)["card"], grid.bundle(second, deck)["card"])
        self.assertNotEqual(grid.bundle(first, deck)["design"], grid.bundle(second, deck)["design"])

    def test_a_given_read_on_two_lines_is_in_the_card_once(self):
        """A design may read one given on two lines. The kernel refuses it, and the card it is refused with is the asker's."""
        card, design = read_pair(ROOT / "examples" / "deck" / "lap_pass.petra")
        twice = design.replace("Fu given tab.Fu", "Fu given tab.Fy")
        with self.assertRaises(LoweringError):      # tab.Fu is then read by nothing
            petra.lang.parse_design(card, twice, "lap.petra", build_registry(), "lap.card")
        twice = design.replace("Fy given strap.Fy", "Fy given tab.Fy")
        with self.assertRaises(LoweringError):
            petra.lang.parse_design(card, twice, "lap.petra", build_registry(), "lap.card")
        both = design.replace("Fy given strap.Fy", "Fy given strap.Fy\n  Fu given tab.Fy", 1)
        parsed = petra.lang.parse_design(card, both, "lap.petra", build_registry(), "lap.card")
        _, body = alone(ROOT / "examples" / "deck" / "lap_pass.card")
        self.assertEqual(grid.bundle(parsed, grid.owner(parsed))["card"].encode("utf-8"), body)

    def test_the_card_alone_is_not_checked_against_any_design(self):
        """A load on a part that no design has declared lowers: there is no design to say so."""
        design = load_card(ROOT / "examples" / "deck" / "lap_pass.card")
        self.assertEqual((dict(design.components), sorted(design.givens)), ({}, ["strap.Fu", "strap.Fy", "tab.Fu", "tab.Fy"]))

    def test_a_card_that_does_not_lower_is_an_input_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp, "bad.card")
            bad.write_text('petra 0\n\ncard "c" {\n  owner "o@example.org"\n}\n\ngiven a.b in [2 mm, 1 mm] signed "o@example.org" source "s"\n', encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()) as said:
                self.assertEqual(export.main(["--card-only", str(bad), "--out", str(Path(tmp, "out"))]), 3)
            self.assertIn("malformed range", said.getvalue())
            self.assertFalse(Path(tmp, "out", "card.json").exists())

    def test_card_only_takes_no_design_and_a_design_takes_no_card_only(self):
        for argv in (["x.petra", "--card-only", "x.card", "--out", "o"], ["--out", "o"], ["--card-only", "x.card", "--no-physics", "--out", "o"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                export.main(argv)

    def test_a_card_of_the_models_kinds_gets_another_hash_than_its_design_names(self):
        """For a design of the models' kinds card.json takes names from the design, so the
        card alone does not give it. The hashes differ, and the reader is told why."""
        said, body = alone(ROOT / "examples" / "truss_pass.card")
        design = load_design(ROOT / "examples" / "truss_pass.petra")
        files = export.bundle(design, build_registry())
        self.assertNotEqual(said, json.loads(files["design"])["card"])
        self.assertIn("tests", json.loads(body), "it is written as the card of a design of a deck's types")


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class TheAskersCheck(unittest.TestCase):
    """The hostile review's finding 3: a designer hands in a card.json under the asker's card
    name with a signed load halved, and the kernel prints PASS. The asker's own hash shows it."""

    def test_a_dishonest_card_json_has_another_hash_than_the_askers(self):
        mine, _ = alone(ROOT / "examples" / "deck" / "lap_fail.card")
        files = {name: body.decode("utf-8") for name, body in full(ROOT / "examples" / "deck" / "lap_fail.petra", physics=True).items()}
        honest = verify.ask(verify.binary(), files)
        self.assertEqual((honest["verdict"], honest["hashes"]["card"]), ("FAIL", mine), "the honest files fail, under the asker's hash")

        card = json.loads(files["card"])
        pull = next(i for i in card["inputs"] if i.get("field") == "pull")
        pull["hi"] = export.number(petra.kernel.parse_q(pull["hi"]) / 2)
        asked = {a.mechanism for a in grid.kinds()["lap"].asks if a.type == "lap"}
        card["waivers"] = [{"subject": "splice", "mechanism": m, "by": "designer", "reason": "forged"} for m in sorted(asked)
                           if m not in ("lap.strength", "lap.end_distance", "lap.ply_yield")]
        forged = {**files, "card": export.text(card)}
        design = json.loads(files["design"])
        design["card"] = export.sha256(forged["card"])
        forged["design"] = export.text(design)
        said = verify.ask(verify.binary(), forged)
        self.assertEqual(said["findings"], [])
        self.assertNotIn(said["verdict"], ("FAIL", "ILL-FORMED"), "the kernel finds the dishonest card well formed, and no cell is refuted under the lower pull")
        self.assertNotEqual(said["hashes"]["card"], mine, "the card it was checked against is not the asker's, and the hash shows it")


if __name__ == "__main__":
    unittest.main()
