"""Every layer is bound by hash (plan step 1.7; docs/format.md, type rules 9 to 11).

The design names its card by hash, the card names its deck of rules by hash, deck.json
names the same deck, and the deck is read with the acceptance run that names its hash.
Until 2026-11-16 only the first held: the kernel read whatever deck `--rules` named, and a
deck with one strength made ten times too generous passed a design with no complaint
(audit item F1). The first class is that deck.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from petra import export, grid, rule, verify
from petra.files import ComponentError
from petra.lang import load_card, load_design
from bench.formalizer import bound as acceptance
from tests import bound

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "corpus" / "cases" / "deck" / "d25_net_section_ruptures"
"""A lap whose strap ruptures at its net section under the pull: 34.66 kip against 35.5."""


def sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def generous(deck: str) -> str:
    """The text of the deck that ships with the rupture strength of a net section (J4-2) taken ten times."""
    honest = '"is": [\n    "mul",\n    "Fu",\n    "Ae"\n   ]'
    assert deck.count(honest) == 1
    return deck.replace(honest, '"is": [\n    "mul",\n    "10",\n    "Fu",\n    "Ae"\n   ]')


def kernel(files: dict[str, str], *more: str) -> dict:
    """What petra-verify prints for the files, each handed over under its flag."""
    with tempfile.TemporaryDirectory() as tmp:
        command = [verify.need()]
        for name, body in files.items():
            Path(tmp, f"{name}.json").write_text(body, encoding="utf-8", newline="\n")
            command += [f"--{name}", str(Path(tmp, f"{name}.json"))]
        done = subprocess.run([*command, *more], capture_output=True)
    assert not done.stderr, done.stderr
    return json.loads(done.stdout)


def findings(said: dict) -> list[tuple[str, str, str]]:
    return [(f["rule"], f["file"], f["item"]) for f in said["findings"]]


def pair(card: str, design: str, deck: grid.Deck) -> dict[str, str]:
    """The six files of a pair's texts, as `petra check` hands them to the kernel."""
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "p.card").write_text(card, encoding="utf-8")
        Path(tmp, "p.petra").write_text(design, encoding="utf-8")
        return grid.check(load_design(str(Path(tmp, "p.petra"))), deck)[1]


def changed(files: dict[str, str], name: str, change) -> dict[str, str]:
    """The files with one of them changed as JSON, and the design naming the card as it now is."""
    body = json.loads(files[name])
    change(body)
    out = {**files, name: export.text(body)}
    design = json.loads(out["design"])
    design["card"] = sha(out["card"])
    return {**out, "design": export.text(design)}


class Shipped(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.deck = grid.kinds()["lap"]
        # The case's card leaves one line with no rule open. With it waived, the rupture is all that stands between the lap and a pass.
        cls.card = CASE.with_suffix(".card").read_text(encoding="utf-8") + 'waive lap.partial_block_shear on splice by "s.engineer@example.org" reason "one line of bolts: no partial block"\n'
        cls.design = CASE.with_suffix(".petra").read_text(encoding="utf-8")
        cls.files = pair(cls.card, cls.design, cls.deck)


class TheDeckThatIsTenTimesTooGenerous(Shipped):
    """The deck that ships with the rupture strength of a net section (J4-2) taken ten times."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.generous = generous(cls.deck.text)

    def test_the_deck_that_ships_fails_the_lap(self):
        said = kernel(self.files)
        self.assertEqual((said["verdict"], said["findings"]), ("FAIL", []))
        self.assertEqual([c["mechanism"] for c in said["cells"] if c["state"] == "refuted"], ["lap.ply_rupture"])

    def test_in_place_of_the_deck_that_ships_the_kernel_refuses_it_three_times_over(self):
        """Nothing else is changed: the card, deck.json and the run all name the deck that ships."""
        said = kernel({**self.files, "rules": self.generous})
        self.assertEqual((said["verdict"], findings(said), said["cells"]),
                         ("ILL-FORMED", [("types.9", "card", "rules"), ("types.10", "deck", "rules"), ("types.11", "run", "deck")], []))
        self.assertIn(self.deck.hash, said["findings"][0]["why"])
        self.assertIn(sha(self.generous), said["findings"][0]["why"])

    def test_with_a_deck_json_and_a_run_written_for_it_the_card_still_refuses_it(self):
        """Whoever swaps the deck can write the two files that are theirs to write. The card is the asker's."""
        deck = json.loads(self.files["deck"])
        deck["rules"] = bound.pin(self.generous)
        said = kernel({**self.files, "rules": self.generous, "deck": export.text(deck), "run": bound.run_of(self.generous)})
        self.assertEqual((said["verdict"], findings(said)), ("ILL-FORMED", [("types.9", "card", "rules")]))

    def test_a_card_that_names_it_passes_and_is_another_card(self):
        """The generous deck passes the lap only under a card that names it, and that card has
        another hash than the one the asker issued: the one check a reader makes shows it."""
        deck = bound.read(self.generous)
        files = pair(bound.card(self.card, deck), self.design, deck)
        said = kernel(files)
        self.assertEqual((said["verdict"], said["findings"]), ("PASS", []))
        self.assertTrue(said["waived"], "the lap passes on its waivers, as the audit's did")
        self.assertNotEqual(said["hashes"]["card"], kernel(self.files)["hashes"]["card"])
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "asked.card").write_text(self.card, encoding="utf-8")
            self.assertNotEqual(export.card_only(str(Path(tmp, "asked.card")), Path(tmp, "out")), said["hashes"]["card"])

    def test_petra_check_refuses_the_pair_and_names_both_decks(self):
        deck = bound.read(self.generous)
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "p.card").write_text(self.card, encoding="utf-8")
            Path(tmp, "p.petra").write_text(self.design, encoding="utf-8")
            with self.assertRaises(ComponentError) as caught:
                grid.check(load_design(str(Path(tmp, "p.petra"))), deck)
        self.assertIn(f"the card names the deck of rules aisc360-22 {self.deck.hash}", str(caught.exception))
        self.assertIn(deck.hash, str(caught.exception))

    def folder(self, tmp: str, deck: str, run: str | None) -> None:
        Path(tmp, "aisc360.json").write_text(deck, encoding="utf-8")
        Path(tmp, "core.json").write_text((grid.DECKS / "core.json").read_text(encoding="utf-8"), encoding="utf-8")
        if run is not None:
            Path(tmp, "aisc360.run.json").write_text(run, encoding="utf-8")

    def read_folder(self, deck: str, run: str | None) -> tuple[grid.Deck, ...]:
        with tempfile.TemporaryDirectory() as tmp:
            self.folder(tmp, deck, run)
            grid.decks.cache_clear()
            try:
                with mock.patch.object(grid, "DECKS", Path(tmp)):
                    return grid.decks()
            finally:
                grid.decks.cache_clear()

    def test_in_the_folder_of_decks_it_is_not_read_with_the_run_of_the_deck_that_ships(self):
        """The audit's case as it was made: the file of the deck edited where it lies."""
        with self.assertRaises(grid.DeckError) as caught:
            self.read_folder(self.generous, self.deck.run)
        self.assertEqual(str(caught.exception), f"aisc360.json: run: deck is not the hash of the deck of rules, {sha(self.generous)}")

    def test_a_deck_with_no_run_beside_it_is_not_read(self):
        with self.assertRaises(grid.DeckError) as caught:
            self.read_folder(self.deck.text, None)
        self.assertEqual(str(caught.exception), f"aisc360.json: {grid.NO_RUN}, and aisc360.run.json is not beside it")

    def test_the_folder_as_it_ships_is_read(self):
        self.assertEqual([d.hash for d in self.read_folder(self.deck.text, self.deck.run)], [self.deck.hash])

    def test_a_deck_with_other_line_ends_is_handed_to_the_kernel_as_it_was_hashed(self):
        """The attacker's finding of 2026-11-16: a deck read from a text with CR LF was hashed with
        line feeds and handed to the kernel as it came, so the grid took the pair and the kernel refused it."""
        crlf = grid.read_deck(self.deck.text.replace("\n", "\r\n"), self.deck.run.replace("\n", "\r\n"))
        self.assertEqual((crlf.hash, crlf.text, crlf.run), (self.deck.hash, self.deck.text, self.deck.run))
        files = pair(self.card, self.design, crlf)
        self.assertNotIn("\r", files["rules"] + files["run"])
        self.assertEqual((kernel(files)["verdict"], kernel(files)["hashes"]["rules"]), ("FAIL", self.deck.hash))

    def test_a_deck_read_with_no_run_checks_no_design(self):
        """`read_deck` with no run reads a deck to look at, or to run the acceptance check on."""
        unbound = grid.read_deck(self.deck.text)
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "p.card").write_text(self.card, encoding="utf-8")
            Path(tmp, "p.petra").write_text(self.design, encoding="utf-8")
            design = load_design(str(Path(tmp, "p.petra")))
            for refused in (grid.check, grid.bundle):
                with self.assertRaises(ComponentError) as caught:
                    refused(design, unbound)
                self.assertIn(f"{grid.NO_RUN}, and the deck aisc360-22 was read with none", str(caught.exception))


class TheRunOfADeck(Shipped):
    """run.json (type rule 11), in the kernel and in `grid.read_deck`."""

    def run_with(self, **keys) -> str:
        return export.text({"format": grid.RUN, "deck": self.deck.hash, "gate": "petra.rule 1", **keys})

    def both(self, run: str) -> tuple[list[tuple[str, str, str]], str]:
        """The kernel's findings with this run, and why `grid.read_deck` refuses the deck with it."""
        said = kernel({**self.files, "run": run})
        self.assertEqual(said["verdict"], "ILL-FORMED")
        with self.assertRaises(grid.DeckError) as caught:
            grid.read_deck(self.deck.text, run)
        self.assertTrue(str(caught.exception).startswith("run: "), caught.exception)
        return findings(said), str(caught.exception)

    def test_a_run_of_three_keys_binds_the_deck(self):
        said = kernel({**self.files, "run": self.run_with()})
        self.assertEqual((said["verdict"], said["findings"]), ("FAIL", []))
        self.assertEqual(grid.read_deck(self.deck.text, self.run_with()).hash, self.deck.hash)

    def test_no_reader_reads_another_key_of_it(self):
        """Not even what the check found: a run that says a line was refused binds like any other."""
        run = self.run_with(lines=[{"mechanism": "lap.ply_rupture", "state": "refused"}], seed="none", inputs=7, anything={"deck": "x"})
        self.assertEqual(kernel({**self.files, "run": run})["verdict"], "FAIL")
        grid.read_deck(self.deck.text, run)

    def test_with_no_run_the_deck_is_not_read(self):
        said = kernel({name: body for name, body in self.files.items() if name != "run"})
        self.assertEqual((said["verdict"], findings(said), said["hashes"]["run"]), ("ILL-FORMED", [("types.11", "run", "")], None))

    def test_the_run_of_another_deck(self):
        found, why = self.both(self.run_with(deck=sha("another deck")))
        self.assertEqual(found, [("types.11", "run", "deck")])
        self.assertEqual(why, f"run: deck is not the hash of the deck of rules, {self.deck.hash}")

    def test_a_gate_with_no_letter_names_no_gate(self):
        for gate in ("", "1", " 2026-11-16 ", "é"):
            with self.subTest(gate=gate):
                found, why = self.both(self.run_with(gate=gate))
                self.assertEqual(found, [("types.11", "run", "gate")])
                self.assertEqual(why, "run: gate does not name the gate that ran, in a text with a letter in it")

    def test_a_run_that_does_not_read_is_a_shape_finding_and_no_more(self):
        for run in ("not json", "[]", json.dumps({"format": "petra-run/1", "deck": self.deck.hash, "gate": "g"}), self.run_with(deck=7),
                    self.run_with(gate=None), self.run_with(note="a�"), "{" * 200 + "}" * 200,
                    self.run_with(seed=1.5), self.run_with(seed=10 ** 32), self.run_with(seed=1000).replace("1000", "1e3")):
            with self.subTest(run=run[:40]):
                found, _ = self.both(run)
                self.assertEqual(found, [("shape", "run", "")])

    def test_a_number_the_kernel_takes_and_a_text_that_looks_like_one(self):
        for run in (self.run_with(seed=10 ** 31), self.run_with(note='1.5e3 " 2.5'), self.run_with(seed=-7)):
            with self.subTest(run=run[-60:]):
                self.assertEqual(kernel({**self.files, "run": run})["verdict"], "FAIL")
                grid.read_deck(self.deck.text, run)

    def test_a_run_with_no_deck_of_rules_is_refused(self):
        """What only a design checked against a deck of rules has, handed over with no deck (type rule 7)."""
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "p.card").write_text(self.card, encoding="utf-8")
            Path(tmp, "p.petra").write_text(self.design, encoding="utf-8")
        said = kernel({name: body for name, body in self.files.items() if name not in ("rules", "proofs")})
        self.assertEqual(said["verdict"], "ILL-FORMED")
        self.assertIn(("types.7", "run", ""), findings(said))
        self.assertIn(("types.7", "card", "rules"), findings(said))


class WhatTheCardSays(Shipped):
    """card.json names its deck (type rule 9), its owner, and where each value is from (type rule 5)."""

    def found(self, change) -> list[tuple[str, str, str]]:
        said = kernel(changed(self.files, "card", change))
        self.assertEqual(said["verdict"], "ILL-FORMED")
        return findings(said)

    def test_the_exporter_writes_them(self):
        card = json.loads(self.files["card"])
        self.assertEqual((card["owner"], card["rules"]), ("s.engineer@example.org", {"name": "aisc360-22", "hash": self.deck.hash}))
        for item in (*card["inputs"], *card["states"]):
            self.assertEqual((bool(item["source"]), item["kind"]), (True, "signed"), item["name"])

    def test_a_measured_value_says_so(self):
        card = self.card.replace('given tab.Fu in [58 ksi, 58 ksi] signed "s.engineer@example.org" source "ASTM A36, specified minimum"',
                                 'given tab.Fu in [58 ksi, 58 ksi] measured "lab@example.org" source "mill certificate 4471"')
        self.assertNotEqual(card, self.card)
        held = {i["name"]: i for i in json.loads(pair(card, self.design, self.deck)["card"])["inputs"]}
        self.assertEqual((held["tab.Fu"]["by"], held["tab.Fu"]["source"], held["tab.Fu"]["kind"]), ("lab@example.org", "mill certificate 4471", "measured"))
        self.assertEqual(held["tab.Fy"]["kind"], "signed")

    def test_a_card_that_names_no_deck(self):
        self.assertEqual(self.found(lambda c: c.pop("rules")), [("types.9", "card", "rules")])
        for held in ("aisc360-22", [], {"name": "aisc360-22"}, {"hash": self.deck.hash}, {"name": 1, "hash": self.deck.hash}, None):
            with self.subTest(held=held):
                self.assertEqual(self.found(lambda c: c.update(rules=held)), [("types.9", "card", "rules")])

    def test_a_card_that_names_the_hash_under_another_name(self):
        self.assertEqual(self.found(lambda c: c["rules"].update(name="aisc360-16")), [("types.9", "card", "rules")])

    def test_a_card_with_no_owner(self):
        for change in (lambda c: c.pop("owner"), lambda c: c.update(owner=""), lambda c: c.update(owner=["s.engineer@example.org"])):
            self.assertEqual(self.found(change), [("types.5", "card", "owner")])

    def test_a_value_with_no_source_or_no_kind(self):
        name = json.loads(self.files["card"])["inputs"][0]["name"]
        for change in (lambda i: i.pop("source"), lambda i: i.update(source=""), lambda i: i.pop("kind"), lambda i: i.update(kind="assumed"),
                       lambda i: i.update(kind="Signed"), lambda i: (i.pop("source"), i.pop("kind"))):
            self.assertEqual(self.found(lambda c: change(c["inputs"][0])), [("types.5", "card", name)])

    def test_a_statement_with_no_source_or_no_kind(self):
        name = json.loads(self.files["card"])["states"][0]["name"]
        for change in (lambda s: s.pop("source"), lambda s: s.update(kind="chosen")):
            self.assertEqual(self.found(lambda c: change(c["states"][0])), [("types.5", "card", name)])

    def test_the_findings_come_in_the_order_the_page_gives(self):
        def change(card: dict) -> None:
            card.pop("rules"), card.pop("owner"), card["states"][0].pop("kind"), card["inputs"][1].pop("source")

        files = changed(self.files, "card", change)
        deck = json.loads(files["deck"])
        deck["rules"]["hash"] = sha("another")
        said = kernel({**files, "deck": export.text(deck), "run": bound.run_of("another")})
        card = json.loads(self.files["card"])
        self.assertEqual(findings(said), [("types.9", "card", "rules"), ("types.10", "deck", "rules"), ("types.11", "run", "deck"), ("types.5", "card", "owner"),
                                          ("types.5", "card", card["inputs"][1]["name"]), ("types.5", "card", card["states"][0]["name"])])

    def test_deck_json_names_the_deck_too(self):
        for change in (lambda d: d.pop("rules"), lambda d: d["rules"].update(hash=sha("another")), lambda d: d["rules"].update(name="other"),
                       lambda d: d.update(rules=True)):
            said = kernel(changed(self.files, "deck", change))
            self.assertEqual((said["verdict"], findings(said)), ("ILL-FORMED", [("types.10", "deck", "rules")]))


class TheCardsText(Shipped):
    """The line `rules "NAME" "HASH"` of a card block."""

    def load(self, card: str):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "p.card").write_text(card, encoding="utf-8")
            Path(tmp, "p.petra").write_text(self.design, encoding="utf-8")
            return load_design(str(Path(tmp, "p.petra")))

    def test_the_card_names_the_deck(self):
        self.assertEqual(self.load(self.card).rules, ("aisc360-22", self.deck.hash))

    def test_a_card_that_names_none_is_told_the_line_to_write(self):
        line = f'  rules "aisc360-22" "{self.deck.hash}"\n'
        self.assertEqual(self.card.count(line), 1)
        design = self.load(self.card.replace(line, ""))
        self.assertIsNone(design.rules)
        with self.assertRaises(ComponentError) as caught:
            grid.check(design, self.deck)
        self.assertIn(f'the card names no deck of rules, so nothing says which rules its owner asked for: its owner adds `rules "aisc360-22" "{self.deck.hash}"`', str(caught.exception))

    def test_a_card_names_one_deck(self):
        twice = self.card.replace("  owner ", f'  rules "aisc360-22" "{self.deck.hash}"\n  owner ', 1)
        with self.assertRaises(Exception) as caught:
            self.load(twice)
        self.assertIn("the card's rules is given twice", str(caught.exception))

    def test_naming_the_deck_again_changes_that_line_and_no_other(self):
        other = bound.read(generous(self.deck.text))
        again = grid.pinned(self.card, other)
        self.assertEqual([a for a, b in zip(again.splitlines(), self.card.splitlines()) if a != b], [f'  rules "aisc360-22" "{other.hash}"'])
        self.assertEqual(grid.pinned(again, self.deck), self.card)
        with self.assertRaises(ValueError):
            grid.pinned("petra 0\n", self.deck)

    def test_the_card_alone_gives_the_hash_the_kernel_prints(self):
        """The deck a card names is in card.json, so the asker's own hash of their card covers it."""
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "asked.card").write_text(self.card, encoding="utf-8")
            self.assertEqual(export.card_only(str(Path(tmp, "asked.card")), Path(tmp, "out")), kernel(self.files)["hashes"]["card"])
            self.assertEqual(load_card(str(Path(tmp, "asked.card"))).rules, ("aisc360-22", self.deck.hash))

    def test_a_stale_card_the_script_cannot_write_is_stale_all_the_same(self):
        """Round 2 of the seventeenth review: once `grid.pinned` refused a card it could not name
        right, the script passed such a card over, in its check too."""
        stale = self.card.replace(self.deck.hash, "sha256:" + "1" * 64)
        for label, text, said in (("as written", stale, "does not name"), ("the closing brace indented", stale.replace("\n}\n\ngiven", "\n  }\n\ngiven", 1), "cannot write the line"),
                                  ("no space after the word", stale.replace('rules "', 'rules"'), "cannot write the line")):
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp:
                Path(tmp, "p.card").write_text(text, encoding="utf-8")
                Path(tmp, "p.petra").write_text(self.design, encoding="utf-8")
                for mode in (["--check"], []):
                    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pin.py"), *mode, tmp], cwd=ROOT, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(ROOT)})
                    if mode or "cannot" in said:
                        self.assertEqual(done.returncode, 1, (label, mode, done.stdout))
                        self.assertIn(said, done.stdout)

    def test_every_card_kept_here_names_the_deck_as_it_is(self):
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pin.py"), "--check", "examples", "corpus/cases"], cwd=ROOT, capture_output=True, text=True,
                              env={**os.environ, "PYTHONPATH": str(ROOT)})
        self.assertEqual((done.returncode, done.stdout), (0, ""), "run python scripts/pin.py examples corpus/cases")


class TheHashOfTheBundle(Shipped):
    def test_the_verdict_prints_six_hashes_and_one_of_them_all(self):
        said = kernel(self.files)
        self.assertEqual(said["hashes"], {name: sha(self.files[name]) for name in ("card", "design", "deck", "rules", "run", "proofs")})
        lines = "".join(f"{name} {sha(self.files[name])}\n" for name in ("card", "design", "deck", "rules", "run", "proofs"))
        self.assertEqual(said["bundle"], sha(lines))
        self.assertEqual(said["bundle"], verify.bundle_hash(said["hashes"]))

    def test_a_file_that_was_not_given_is_none(self):
        files = {name: body for name, body in self.files.items() if name != "proofs"}
        said = kernel(files)
        self.assertIsNone(said["hashes"]["proofs"])
        self.assertEqual(said["bundle"], sha("".join(f"{name} {sha(files[name]) if name in files else 'none'}\n" for name in verify.HASHED)))

    def test_another_hint_is_another_bundle(self):
        proofs = json.loads(self.files["proofs"])
        proofs["cells"] = proofs["cells"][:-1]
        other = kernel({**self.files, "proofs": export.text(proofs)})
        said = kernel(self.files)
        self.assertNotEqual(other["bundle"], said["bundle"])
        self.assertEqual({name for name in verify.HASHED if other["hashes"][name] != said["hashes"][name]}, {"proofs"})

    def test_an_answer_with_another_bundle_is_no_answer(self):
        real = verify.run

        def lying(command):
            code, out, err = real(command)
            said = json.loads(out)
            return code, json.dumps({**said, "bundle": sha("other files")}).encode(), err

        with mock.patch.object(verify, "run", lying), self.assertRaises(verify.BadAnswer) as caught:
            verify.ask(verify.need(), self.files)
        self.assertIn("a hash of the bundle that is not the hash of the six lines of its files", str(caught.exception))

    def test_the_report_prints_the_run_and_the_bundle(self):
        done = subprocess.run([sys.executable, "-m", "petra", "check", str(CASE.with_suffix(".petra"))], cwd=ROOT, capture_output=True, text=True,
                              env={**os.environ, "PYTHONPATH": str(ROOT)})
        said = kernel(pair(CASE.with_suffix(".card").read_text(encoding="utf-8"), self.design, self.deck))
        lines = done.stdout.splitlines()
        self.assertEqual(lines[1], f"rules      {self.deck.hash}  aisc360-22")
        self.assertEqual(lines[2], f"run        {said['hashes']['run']}  the acceptance run the deck is bound to")
        self.assertEqual(lines[5], f"bundle     {said['bundle']}  the six files the kernel read")


class AFlagGivenTwice(Shipped):
    def test_names_two_files_and_is_no_command_line_the_kernel_reads(self):
        """Until 2026-11-16 the kernel read the first of two `--rules` and said nothing of the second."""
        with tempfile.TemporaryDirectory() as tmp:
            command = [verify.need()]
            for name, body in {**self.files, "other": generous(self.deck.text)}.items():
                Path(tmp, f"{name}.json").write_text(body, encoding="utf-8", newline="\n")
                command += [] if name == "other" else [f"--{name}", str(Path(tmp, f"{name}.json"))]
            for flag in ("rules", "card", "run", "proofs"):
                for first in (True, False):
                    twice = [f"--{flag}", str(Path(tmp, "other.json"))]
                    done = subprocess.run([*command[:1], *twice, *command[1:]] if first else [*command, *twice], capture_output=True, text=True)
                    self.assertEqual((done.returncode, done.stdout), (64, ""), (flag, first))
                    self.assertIn("usage: petra-verify", done.stderr)


class TheRecordOfARun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.deck = grid.kinds()["lap"]
        cls.accepted = acceptance.Run(cls.deck.text)
        cls.generous = generous(cls.deck.text)

    def test_a_record_names_the_deck_and_the_gate_and_reads_as_a_run(self):
        whole = rule.Check("reads", "pass", "every field and every load is read")
        text = rule.record(self.accepted.task, self.deck.text, [rule.Line("lap.strength", "admitted", ("r",), (whole,))], whole, [], {"task": sha("t")}, "nothing")
        body = json.loads(text)
        self.assertEqual((body["format"], body["deck"], body["gate"], body["seed"], body["changed"]), (grid.RUN, self.deck.hash, rule.GATE, 0, "nothing"))
        self.assertEqual(body["lines"], [{"mechanism": "lap.strength", "state": "admitted", "rules": ["r"], "note": "",
                                          "checks": [{"name": "reads", "outcome": "pass", "detail": "every field and every load is read"}]}])
        self.assertEqual(grid.read_deck(self.deck.text, text).run, text)

    def test_the_deck_that_ships_is_bound_to_the_gate_it_went_through(self):
        body = json.loads(self.deck.run)
        self.assertEqual((body["deck"], body["gate"]), (self.deck.hash, rule.GATE))
        self.assertEqual(sorted(body["inputs"]), ["rules2_b.json", "rules2_examples.json", "rules_task2.json"])
        self.assertEqual((self.accepted.refused(), {line["state"] for line in body["lines"]}), ([], {"admitted", "left out"}))

    def test_a_run_on_other_rows_than_the_decks_writes_no_record_for_it(self):
        """The seventeenth review: the check reads the rows of its task, and of a deck only the
        rules. So the deck with a strength taken ten times got the record of the deck that ships,
        with every line admitted, from a run whose task held the honest rows."""
        whole = rule.Check("reads", "pass", "")
        with self.assertRaises(grid.DeckError) as caught:
            rule.record(self.accepted.task, self.generous, self.accepted.lines, whole, [], {})
        self.assertEqual(str(caught.exception), "a run binds a deck when its task is the deck's own, and the rows of the task are not the deck's")
        self.assertIsNone(rule.own(self.accepted.task, json.loads(self.deck.text)))
        body = json.loads(self.deck.text)
        body["grid"] = body["grid"][:-1]
        self.assertEqual(rule.own(self.accepted.task, body), "the lines of the grid of the task are not the deck's")
        body = json.loads(self.deck.text)
        body["types"][0]["fields"][0]["what"] += "."
        self.assertEqual(rule.own(self.accepted.task, body), "the types of the task are not the deck's")

    def test_the_decks_own_is_asked_of_what_json_writes(self):
        """Round 2 of the seventeenth review: Python compares true with 1 and 2.0 with 2 as equal,
        and an item of the types or of the grid that is no object was passed over."""
        body = json.loads(self.deck.text)
        row = next(r for r in body["rows"] if isinstance(r.get("is"), list))
        row["is"] = [True if x == "1" else x for x in row["is"]] + [1]
        task = self.accepted.task
        twin = json.loads(json.dumps(body))
        twin["rows"][body["rows"].index(row)]["is"][-1] = True
        self.assertEqual(json.dumps(1) == json.dumps(True), False)
        for key in ("types", "grid"):
            for odd in (None, "x", []):
                changed_ = json.loads(self.deck.text)
                changed_[key].append(odd)
                self.assertEqual(rule.own(task, changed_), "the types and the grid of the deck are not lists of objects", (key, odd))
        honest = json.loads(self.deck.text)
        self.assertIsNone(rule.own(task, honest))
        honest["types"][0]["fields"][0]["optional"] = 1
        self.assertEqual(rule.own(task, honest), "the types of the task are not the deck's")

    def test_a_record_that_cannot_be_written_is_said_not_to_be(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "task.json").write_text(json.dumps(acceptance.task_of(json.loads(self.deck.text))), encoding="utf-8")
            Path(tmp, "deck.json").write_text(self.deck.text, encoding="utf-8")
            done = subprocess.run([sys.executable, "-m", "petra.rule", "task.json", "deck.json", "--run", str(Path(tmp, "no_such_folder", "out.run.json"))],
                                  cwd=tmp, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(ROOT)})
        self.assertEqual(done.returncode, 3)
        self.assertIn("petra.rule: the record is not written", done.stderr)
        self.assertNotIn("Traceback", done.stderr)

    def test_a_run_on_the_generous_decks_own_rows_refuses_the_line(self):
        """Run on its own rows, the worked example of the rupture catches it, and the writer of the
        shipped deck's record writes none."""
        self.assertEqual(acceptance.Run(self.generous).refused(), ["lap.ply_rupture"])

    def command(self, task: dict, deck: str, tmp: str) -> subprocess.CompletedProcess:
        Path(tmp, "task.json").write_text(json.dumps(task), encoding="utf-8")
        Path(tmp, "deck.json").write_text(deck, encoding="utf-8")
        return subprocess.run([sys.executable, "-m", "petra.rule", "task.json", "deck.json", "--examples", str(ROOT / "bench" / "formalizer" / "rules2_examples.json"), "--run", "out.run.json"],
                              cwd=tmp, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(ROOT)})

    def test_the_command_writes_no_record_of_a_run_on_other_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = self.command(acceptance.task_of(json.loads(self.deck.text)), self.generous, tmp)
            self.assertEqual((done.returncode, done.stdout, Path(tmp, "out.run.json").exists()), (3, "", False))
            self.assertIn("a run binds a deck when its task is the deck's own, and the rows of the task are not the deck's", done.stderr)

    def test_the_command_on_the_generous_decks_own_rows_says_that_the_run_refused(self):
        """The record is written, since it is true, and it binds the deck, since no reader reads
        what a record found. The command exits 1 and says so."""
        with tempfile.TemporaryDirectory() as tmp:
            done = self.command(acceptance.task_of(json.loads(self.generous)), self.generous, tmp)
            self.assertEqual(done.returncode, 1)
            self.assertIn("is the record of a run that refused", done.stderr)
            body = json.loads(Path(tmp, "out.run.json").read_text(encoding="utf-8"))
            self.assertEqual((body["deck"], [line["mechanism"] for line in body["lines"] if line["state"] == "refused"]), (sha(self.generous), ["lap.ply_rupture"]))
            self.assertEqual(sorted(body["inputs"]), ["examples", "rules", "task"])
            self.assertEqual(body["inputs"]["rules"], body["deck"])

    def test_the_command_on_the_deck_that_ships_writes_the_same_record_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.command(acceptance.task_of(json.loads(self.deck.text)), self.deck.text, tmp)
            once = Path(tmp, "out.run.json").read_text(encoding="utf-8")
            self.command(acceptance.task_of(json.loads(self.deck.text)), self.deck.text, tmp)
            self.assertEqual((first.returncode, once), (0, Path(tmp, "out.run.json").read_text(encoding="utf-8")))
            self.assertNotIn(tmp, once)
            self.assertEqual(grid.read_deck(self.deck.text, once).hash, self.deck.hash)

    def test_a_transcription_is_no_deck_to_bind(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = self.command(acceptance.task_of(json.loads(self.deck.text)), (ROOT / "bench" / "formalizer" / "rules2_b.json").read_text(encoding="utf-8"), tmp)
            self.assertEqual((done.returncode, Path(tmp, "out.run.json").exists()), (3, False))


class WhatTheSeventeenthReviewFound(Shipped):
    def test_a_deck_text_with_two_carriage_returns_is_hashed_as_it_is_handed_over(self):
        """`\r\r\n` became `\r\n` on the way in and was hashed as if it had become `\n`: the grid
        took the pair and the kernel refused it."""
        with self.assertRaises(grid.DeckError) as caught:
            grid.read_deck(self.deck.text.replace("\n", "\r\r\n"), self.deck.run)
        self.assertTrue(str(caught.exception).startswith("run: deck is not the hash of the deck of rules, "))
        odd = bound.read(self.deck.text.replace("\n", "\r\r\n"))
        self.assertNotEqual(odd.hash, self.deck.hash)
        self.assertEqual(odd.hash, sha(odd.text))
        files = pair(bound.card(self.card, odd), self.design, odd)
        self.assertEqual(kernel(files)["hashes"]["rules"], odd.hash)
        self.assertEqual(kernel(files)["verdict"], "FAIL")

    def test_a_run_with_a_constant_that_is_no_json(self):
        for word in ("NaN", "Infinity", "-Infinity"):
            run = self.deck.run.replace('"seed": 0', f'"seed": {word}')
            self.assertNotEqual(run, self.deck.run)
            self.assertEqual(findings(kernel({**self.files, "run": run})), [("shape", "run", "")])
            with self.assertRaises(grid.DeckError) as caught:
                grid.read_deck(self.deck.text, run)
            self.assertTrue(str(caught.exception).startswith("run: not JSON"), caught.exception)

    def test_the_exporter_says_that_the_decks_do_not_read_and_exits_4(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("aisc360.json", "core.json"):
                Path(tmp, name).write_text((grid.DECKS / name).read_text(encoding="utf-8"), encoding="utf-8")
            script = ("import sys; from pathlib import Path; from petra import grid, export; grid.DECKS = Path(sys.argv[1]); "
                      "sys.exit(export.main([sys.argv[2], '--out', sys.argv[3]]))")
            done = subprocess.run([sys.executable, "-c", script, tmp, str(CASE.with_suffix(".petra")), str(Path(tmp, "out"))], cwd=ROOT, capture_output=True, text=True,
                                  env={**os.environ, "PYTHONPATH": str(ROOT)})
        self.assertEqual((done.returncode, done.stdout), (4, ""))
        self.assertIn("aisc360.run.json is not beside it", done.stderr)
        self.assertNotIn("Traceback", done.stderr)

    def test_a_card_laid_out_another_way_is_named_right_or_not_at_all(self):
        """`grid.pinned` reads back what it wrote. Each of these read as a card before, and came
        back naming two decks, or with the line in a load's block."""
        line = f'  rules "aisc360-22" "{self.deck.hash}"\n'
        plain = self.card.replace(line, "")
        other = bound.read(generous(self.deck.text))
        for label, text in (("the closing brace indented", plain.replace("\n}\n\ngiven", "\n  }\n\ngiven", 1)), ("the card indented", plain.replace('card "', '  card "', 1)),
                            ("CR LF and a deck named", self.card.replace("\n", "\r\n")), ("no space between the two texts", self.card.replace('"aisc360-22" "', '"aisc360-22""')),
                            ("no space after the word", self.card.replace('rules "', 'rules"'))):
            with self.subTest(label):
                try:
                    again = grid.pinned(text, other)
                except ValueError as exc:
                    self.assertIn("its owner writes", str(exc) + "its owner writes" * ("no card block" in str(exc)))
                    continue
                with tempfile.TemporaryDirectory() as tmp:
                    Path(tmp, "p.card").write_text(again, encoding="utf-8", newline="")
                    self.assertEqual(load_card(str(Path(tmp, "p.card"))).rules, ("aisc360-22", other.hash))

    def test_the_line_printed_for_a_deck_with_a_quote_in_its_name_names_that_deck(self):
        body = json.loads(self.deck.text)
        body["name"] = 'a" "sha256:OTHER" #'
        odd = bound.read(json.dumps(body))
        self.assertEqual(grid.rules_line(odd), 'rules "a\\" \\"sha256:OTHER\\" #" "' + odd.hash + '"')
        named = grid.pinned(self.card, odd)
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "p.card").write_text(named, encoding="utf-8")
            self.assertEqual(load_card(str(Path(tmp, "p.card"))).rules, (odd.name, odd.hash))
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "p.card").write_text(self.card, encoding="utf-8")
            Path(tmp, "p.petra").write_text(self.design, encoding="utf-8")
            with self.assertRaises(ComponentError) as caught:
                grid.check(load_design(str(Path(tmp, "p.petra"))), odd)
        self.assertIn(grid.rules_line(odd).partition(" ")[2].rpartition(" ")[0].strip('"').replace('\\"', '"'), str(caught.exception))


if __name__ == "__main__":
    unittest.main()
