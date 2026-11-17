"""The nonstop attacker (bench/attack): its generator, its relations and its runner.

The tests that need the kernel and Node are skipped when either is missing. The rest run
on the Python reader alone.
"""
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

from petra import grid, units as petra_units, verify
from petra.files import ComponentError
from petra.lang import LoweringError, parse_design

from bench.attack import bind, deckinfo, decks, files as F, gen, found, meta, readers, spec as S, units
from bench.attack import maker as MAKER
from bench.attack.maker import Maker

ROOT = Path(__file__).resolve().parents[1]
DECK_TEXT = (ROOT / "petra" / "decks" / "aisc360.json").read_text(encoding="utf-8")
RUN_TEXT = (ROOT / "petra" / "decks" / "aisc360.run.json").read_text(encoding="utf-8")
"""The run the shipped deck is bound to: a design is checked only against a deck read with it."""
KERNEL = verify.binary()
NODE = shutil.which("node")


def pair(name: str) -> tuple[str, str]:
    p = ROOT / "examples" / "deck" / f"{name}.petra"
    return p.with_suffix(".card").read_text(encoding="utf-8"), p.read_text(encoding="utf-8")


class Units(unittest.TestCase):
    def test_the_attackers_table_is_the_readers(self):
        """The attacker's factors are written from the definitions, and they are the reader's, each exactly."""
        for name, (factor, dim) in {**petra_units.UNITS, **petra_units.CUSTOMARY}.items():
            if name in ("1", "N m"):
                continue
            mine, mdim = units.FACTORS[name]
            self.assertEqual(mine, factor, name)
            self.assertEqual(mdim, (dim.m, dim.kg, dim.s, dim.A, dim.degC), name)

    def test_values_of_a_deck(self):
        self.assertEqual(units.si("1 1/8 inch"), Fraction(9, 8) * units.INCH)
        self.assertEqual(units.si("29,000 ksi"), 29000 * units.factor("ksi")[0])
        self.assertEqual(units.dim_of("force/length"), units.STIFFNESS)
        self.assertEqual(units.dim_of("length^3"), (3, 0, 0, 0, 0))
        self.assertIsNone(units.dim_of("nonsense"))

    def test_number_text_is_exact(self):
        for x in (Fraction(3, 8), Fraction(1, 3), Fraction(-5, 4), Fraction(10 ** 20 + 1, 7), Fraction(0), Fraction(7)):
            self.assertEqual(Fraction(units.number_text(x)), x)
            self.assertEqual(Fraction(units.number_text(x, "frac")), x)


class Specs(unittest.TestCase):
    def test_the_pairs_of_the_corpus_read_and_write_back_to_the_same_files(self):
        deck = grid.read_deck(DECK_TEXT, RUN_TEXT)
        n = 0
        for folder in ("corpus/cases/deck", "examples/deck"):
            for path in sorted((ROOT / folder).glob("*.petra")):
                card, design = path.with_suffix(".card").read_text(encoding="utf-8"), path.read_text(encoding="utf-8")
                s = S.read(card, design)
                self.assertIsNotNone(s, path.name)
                with mock.patch.object(grid, "decks", lambda: (deck,)):
                    try:
                        a = grid.bundle(parse_design(card, design, "a.petra"), deck)
                    except (LoweringError, ComponentError) as refused:      # a pair refused is refused for the same reason when written back:
                        with self.assertRaises(type(refused), msg=path.name) as again:     # the language's refusal, or a card that names another deck or none
                            grid.bundle(parse_design(*s.texts(), "a.petra"), deck)
                        self.assertEqual([m.split(": ", 1)[1] for m in again.exception.problems], [m.split(": ", 1)[1] for m in refused.problems], path.name)
                        continue
                    b = grid.bundle(parse_design(*s.texts(), "b.petra"), deck)
                self.assertEqual(a, b, path.name)
                n += 1
        self.assertGreater(n, 40)

    def test_simplest_fraction_between(self):
        self.assertEqual(gen.simplest_between(Fraction(127, 2500) - Fraction(1, 10 ** 15), Fraction(127, 2500)), Fraction(127, 2500))
        self.assertEqual(gen.simplest_between(Fraction(3, 10), Fraction(4, 10)), Fraction(1, 3))
        self.assertEqual(gen.simplest_between(Fraction(-3, 10), Fraction(-4, 10)), Fraction(-1, 3))


class Generator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seeds = deckinfo.seeds()
        cls.info = deckinfo.read(cls.seeds["aisc360"])
        gen.learn_anchors(gen.corpus_specs())

    def test_it_is_reproducible(self):
        a = [gen.fresh(random.Random(7), self.info).texts() for _ in range(1)]
        b = [gen.fresh(random.Random(7), self.info).texts() for _ in range(1)]
        self.assertEqual(a, b)
        self.assertNotEqual(a, [gen.fresh(random.Random(8), self.info).texts()])

    def test_a_fresh_design_is_read_by_the_language_and_keeps_its_needs(self):
        deck = grid.read_deck(DECK_TEXT, RUN_TEXT)
        rng = random.Random(3)
        read = 0
        for _ in range(60):
            s = gen.fresh(rng, self.info)
            self.assertEqual(gen.breaks(s, self.info), [])
            with mock.patch.object(grid, "decks", lambda: (deck,)):
                try:
                    parse_design(*s.texts(), "x.petra")
                    read += 1
                except Exception:       # noqa: BLE001
                    pass
        self.assertGreaterEqual(read, 57)

    def test_the_other_decks_give_designs_too(self):
        rng = random.Random(4)
        for name, deck in self.seeds.items():
            info = deckinfo.read(deck)
            self.assertTrue(info.types, name)
            s = gen.fresh(rng, info)
            self.assertTrue(s.parts, name)

    def test_a_changed_deck_mostly_still_loads(self):
        rng = random.Random(5)
        loaded = 0
        for _ in range(30):
            mutated, notes, kind = decks.mutate(rng, self.seeds["aisc360"])
            try:
                grid.read_deck(json.dumps(mutated))
                loaded += 1
            except grid.DeckError:
                pass
        self.assertGreaterEqual(loaded, 12)

    def test_a_respelled_value_is_the_same_value(self):
        rng = random.Random(6)
        for _ in range(40):
            mutated = json.loads(DECK_TEXT)
            note = decks.op_respell(rng, mutated)
            self.assertTrue(note)
        # the respelling keeps each number: the first deck, respelled five times, still loads
        d = json.loads(DECK_TEXT)
        for _ in range(5):
            decks.op_respell(rng, d)
        grid.read_deck(json.dumps(d))


class Relations(unittest.TestCase):
    def test_the_shipped_deck_reads_each_load_on_the_side_of_its_limit_only(self):
        self.assertTrue(meta.load_monotone(json.loads(DECK_TEXT)))

    def test_a_deck_with_a_load_on_the_wrong_side_is_not_held(self):
        d = json.loads(DECK_TEXT)
        rule = next(r for r in d["rules"] if "le" in r and meta._mentions_load(r["le"][0]))
        rule["le"] = [rule["le"][1], rule["le"][0]]
        self.assertFalse(meta.load_monotone(d))
        for name in deckinfo.seeds():
            if name != "aisc360":
                meta.load_monotone(deckinfo.seeds()[name])      # reads without a fault

    def test_the_same_numbers_in_another_unit_write_the_same_files(self):
        deck = grid.read_deck(DECK_TEXT, RUN_TEXT)
        for name in ("lap_pass", "lap_fail", "lap_unknown"):
            s = S.read(*pair(name))
            for child in (meta.to_si(s), meta.other_units(random.Random(1), s)):
                self.assertEqual(readers.bundle_of(*s.texts(), DECK_TEXT), readers.bundle_of(*child.texts(), DECK_TEXT), name)

    def test_a_wrong_factor_in_the_reader_is_seen_by_the_unit_relation(self):
        """Plant a wrong factor for the inch and the unit relation shows it: the number written in inches differs from the same number in metres."""
        s = S.read(*pair("lap_pass"))
        good = readers.bundle_of(*meta.to_si(s).texts(), DECK_TEXT)
        wrong = (petra_units.CUSTOMARY["inch"][0] * Fraction(1001, 1000), petra_units.CUSTOMARY["inch"][1])
        with mock.patch.dict(petra_units.CUSTOMARY, {"inch": wrong}):
            bad = readers.bundle_of(*s.texts(), DECK_TEXT)
            si = readers.bundle_of(*meta.to_si(s).texts(), DECK_TEXT)
        self.assertNotEqual(bad["design"], si["design"])
        self.assertEqual(good["design"], si["design"])      # a number written in metres does not read the inch at all

    def test_a_rename_moves_every_name(self):
        s = S.read(*pair("lap_pass"))
        child, new = meta.renamed(random.Random(2), s)
        card, design = child.texts()
        for old in new:
            self.assertNotIn(f" {old} ", design.replace("\n", " "))
        self.assertTrue(readers.bundle_of(card, design, DECK_TEXT))

    def test_a_hint_that_changes_a_proved_cell_is_caught(self):
        honest = [("s", "m", "e", "proved", ""), ("s", "n", "", "open", "")]
        self.assertIsNone(F.sound(honest, [("s", "m", "e", "open", ""), ("s", "n", "", "proved", "")]))
        self.assertIn("proved and is refuted", F.sound(honest, [("s", "m", "e", "refuted", ""), ("s", "n", "", "open", "")]))
        self.assertIn("not the same", F.sound(honest, honest[:1]))


@unittest.skipUnless(KERNEL and (NODE or not readers.Config.twin), "needs a built kernel, and Node for the third reading")
class Readers(unittest.TestCase):
    """The third reading is asked when readers.Config.twin names it, and is not asked while it is None."""

    @classmethod
    def setUpClass(cls):
        readers.Config.kernel = KERNEL

    def test_the_readers_agree_on_the_examples(self):
        for name, verdict in (("lap_pass", "PASS"), ("lap_fail", "FAIL"), ("lap_unknown", "UNKNOWN")):
            j = readers.judge(*pair(name), DECK_TEXT)
            self.assertTrue(j.reached and j.settled, name)
            self.assertEqual(j.verdict, {"grid": verdict, "kernel": verdict, **({"twin": verdict} if readers.Config.twin else {})}, name)
            self.assertEqual([d for d in j.diffs if d.kind != "reason"], [], name)

    def test_a_refused_pair_does_not_reach(self):
        j = readers.judge("petra 0\n", "petra 0\n\nlap x {\n}\n", DECK_TEXT)
        self.assertFalse(j.reached)

    def test_files_no_language_wrote_are_asked_of_the_kernel_and_the_third_reading(self):
        files = readers.bundle_of(*pair("lap_pass"), DECK_TEXT)
        self.assertEqual(readers.judge_files(files).diffs, [])
        broken = {**files, "card": files["card"].replace('"cases"', '"kases"')}
        j = readers.judge_files(broken)
        self.assertEqual(j.verdict["kernel"], "ILL-FORMED")

    def test_a_third_reading_that_says_something_else_is_a_difference(self):
        kernel = {"verdict": "PASS", "cells": [{"subject": "a", "mechanism": "m", "entry": "", "state": "proved"}], "findings": []}
        twin = {"verdict": "UNKNOWN", "cells": [{"subject": "a", "mechanism": "m", "entry": "", "state": "open", "reason": "x"}], "findings": []}
        self.assertEqual([d.kind for d in readers.compare_two(kernel, twin, "kernel/twin")], ["verdict"])
        twin = {**kernel, "cells": [{"subject": "a", "mechanism": "m", "entry": "", "state": "open"}]}
        self.assertEqual([d.kind for d in readers.compare_two(kernel, twin, "kernel/twin")], ["cells"])

    def test_the_share_that_reaches_the_comparison(self):
        maker = Maker(random.Random(11))
        reached = made = 0
        for _ in range(14):
            for d in maker.next():
                card, design = d.texts()
                j = readers.judge_files({**d.files, "rules": d.deck_text}) if d.files else readers.judge(card, design, d.deck_text, d.base_text)
                made += 1
                reached += j.reached
        self.assertGreaterEqual(reached / made, 0.5, f"{reached} of {made}")

    def test_a_difference_is_kept_as_a_folder_that_runs_again(self):
        maker = Maker(random.Random(1))
        d = maker.language("aisc360")
        j = readers.judge(*d.texts(), d.deck_text)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(found.keep(Path(tmp), d, j, readers.Diff("cells", "kernel/twin", "a made-up difference", key="x")))
            self.assertFalse(found.keep(Path(tmp), d, j, readers.Diff("cells", "kernel/twin", "a made-up difference", key="x")))
            folder = next(Path(tmp, "found").iterdir())
            self.assertTrue((folder / "run.sh").exists() and (folder / "case.json").exists())
            self.assertEqual(json.loads((folder / "case.json").read_text())["count"], 2)
            done = subprocess.run([sys.executable, "-m", "bench.attack.repro", str(folder)], cwd=ROOT, capture_output=True, text=True, env={**os.environ, "PETRA_VERIFY": KERNEL})
            self.assertIn("verdicts:", done.stdout, done.stderr)

    def test_the_runner_stops_and_writes_one_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp, "log.jsonl")
            done = subprocess.run([sys.executable, "-m", "bench.attack.run", "--seed", "3", "--jobs", "2", "--max-steps", "3", "--out", tmp, "--log", str(log), "--kernel", KERNEL],
                                  cwd=ROOT, capture_output=True, text=True, timeout=600)
            self.assertEqual(done.returncode, 0, done.stderr)
            rows = log.read_text().splitlines()
            self.assertEqual(len(rows), 1)
            row = json.loads(rows[0])
            for key in ("seed", "inputs", "share_reached", "differences", "crashes", "wall_s"):
                self.assertIn(key, row)
            self.assertGreater(row["inputs"], 0)


class Binding(unittest.TestCase):
    """What the attacker holds of the binding by hash (bench/attack/bind.py), on files made up here."""

    def setUp(self):
        self.files = {"card": F.dump({"format": "petra-card/0", "rules": {"name": "aisc360-22", "hash": bind.deck_hash(DECK_TEXT)}}),
                      "design": "{}", "deck": "{}", "rules": DECK_TEXT, "run": RUN_TEXT}
        hashes, whole = bind.bundle(self.files)
        self.said = {"verdict": "PASS", "hashes": hashes, "bundle": whole}

    def test_the_bundle_is_the_hash_of_six_lines(self):
        hashes, whole = bind.bundle({"card": "a"})
        lines = "".join(f"{n} {hashes[n] or 'none'}\n" for n in bind.FILES)
        self.assertEqual(whole, bind.sha(lines))
        self.assertEqual([n for n in bind.FILES if hashes[n]], ["card"])

    def test_a_pass_of_the_files_whose_card_names_the_deck_read_is_held(self):
        self.assertEqual(bind.held_of(self.files, self.said), [])

    def test_a_pass_for_a_card_that_names_another_deck_is_a_difference(self):
        files = {**self.files, "card": F.dump({"rules": {"name": "aisc360-22", "hash": "sha256:" + "0" * 64}})}
        hashes, whole = bind.bundle(files)
        self.assertEqual([d.kind for d in bind.held_of(files, {**self.said, "hashes": hashes, "bundle": whole})], ["bind"])

    def test_a_bundle_that_is_not_of_the_files_is_a_difference(self):
        self.assertEqual([d.kind for d in bind.held_of(self.files, {**self.said, "bundle": "sha256:00"})], ["bundle"])
        self.assertEqual([d.kind for d in bind.held_of({**self.files, "run": RUN_TEXT + " "}, self.said)], ["bundle"])

    def test_the_shipped_deck_is_read_with_its_record_and_any_other_with_one_made_up(self):
        self.assertEqual(bind.run_for(DECK_TEXT), RUN_TEXT)
        made = json.loads(bind.run_for(DECK_TEXT + "\n"))
        self.assertEqual((made["format"], made["deck"]), (grid.RUN, bind.deck_hash(DECK_TEXT + "\n")))
        grid.read_deck(DECK_TEXT + "\n", bind.run_for(DECK_TEXT + "\n"))

    def test_a_card_names_the_deck_it_is_checked_against(self):
        s = S.read(*pair("lap_pass"))
        self.assertEqual(s.rules, bind.pin(DECK_TEXT))
        s.rules = S.DECK
        self.assertIn('rules "x\\"y" "sha256:1"', s.card_text(('x"y', "sha256:1")))
        self.assertNotIn("rules", s.card_text())


@unittest.skipUnless(KERNEL, "needs a built kernel")
class BindingRecipes(unittest.TestCase):
    """Each recipe of the binding, once: what it expects holds, and the kernel and the grid agree on refusing or not."""

    @classmethod
    def setUpClass(cls):
        readers.Config.kernel = KERNEL

    def test_each_recipe_of_the_binding_meets_what_it_expects(self):
        from bench.attack import run as R
        maker = Maker(random.Random(21))
        for kind in sorted(MAKER.BINDING):      # crlf among them: the attacker found the readers apart on it on 2026-11-16, and they agree since
            drafts = getattr(maker, "bind_" + kind)()
            judged = []
            for d in drafts:
                j = R.judge(maker, d, False)
                judged.append(j)
                self.assertEqual([x.detail for x in j.diffs if x.kind != "reason"], [], f"{kind}: {d.notes[-1:]}")
                self.assertEqual([x.detail for x in bind.expected(d.extra, j)], [], f"{kind}: {d.notes[-1:]}")
                if d.relation:
                    self.assertEqual([x.detail for x in R.relation(d, judged[d.relation[1]], j, drafts[d.relation[1]])], [], kind)
            refused = [d for d in drafts if (d.extra.get("bind") or {}).get("expect") == "refuse"]
            for d, j in zip(drafts, judged):
                if d in refused and j.reached:
                    self.assertEqual(j.verdict.get("kernel"), "ILL-FORMED", kind)

    def test_the_third_reading_is_not_asked_while_it_is_switched_off(self):
        with mock.patch.object(readers.Config, "twin", None):
            j = readers.judge(*pair("lap_unknown"), DECK_TEXT)
        self.assertNotIn("twin", j.verdict)


if __name__ == "__main__":
    unittest.main()
