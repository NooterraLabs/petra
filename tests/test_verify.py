"""`petra check` takes its verdict from the kernel, petra-verify (petra/verify.py).
tests/test_kernel_decides.py holds every way into a check to that, with no kernel and with
one that refuses.

The shell is tested with a stand-in for the kernel's answer, so these tests run with no
kernel built. The `Found` tests hold the order of the places a kernel is looked for, with
empty files in two places of their own. The `Built` tests run the real one when
PETRA_VERIFY names it or the source tree holds a build, as CI's does.
"""
import hashlib
import json
import os
import tempfile
import time
import unittest
import warnings
from pathlib import Path
from unittest import mock

import petra
from petra import verify
from petra.files import read_pair

ROOT = Path(__file__).resolve().parents[1]
CIRCUIT = ROOT / "corpus" / "cases" / "old" / "circuit_pass.petra"
TRUSS = ROOT / "corpus" / "cases" / "old" / "truss_pass.petra"
LAP = ROOT / "examples" / "deck" / "lap_pass.petra"
KERNEL = verify.BUILT
"""Where this source tree's kernel is, before any test names another place."""


def checked(kernel, path=CIRCUIT) -> dict:
    """petra.check of the pair at `path`, with `kernel` answering in place of petra-verify,
    or with no kernel when it is None."""
    found = None if kernel is None else "petra-verify"
    with mock.patch.object(verify, "binary", lambda: found), mock.patch.object(verify, "ask", lambda _, files: kernel(files)):
        return petra.check(*read_pair(path), path=str(path))


def never(files):
    raise AssertionError(f"the kernel was asked about {sorted(files)}")


class Shell(unittest.TestCase):
    """A design none of whose parts is of a deck's type: there is no deck of rules to hand
    the kernel, so it is not asked, and the design reads UNKNOWN with the reason."""

    def test_a_design_no_deck_has_reads_unknown_and_the_kernel_is_not_asked(self):
        result = checked(never)
        self.assertEqual((result["status"], result["reason"], result["kinds"]), ("UNKNOWN", verify.no_deck(["circuit"]), ["circuit"]))
        self.assertEqual((result["kernel"], result["cells"], result["deck"], result["path"], result["more_kinds"]), (None, [], None, "none", 0))

    def test_no_answer_of_a_kernel_can_move_it(self):
        """Whatever a kernel would say of it, PASS among them: nothing is asked, so nothing is taken."""
        passing = lambda files: {"verdict": "PASS", "hashes": {}, "cells_from": "rules", "findings": [], "waived": [], "cells": []}      # noqa: E731
        for path in (CIRCUIT, TRUSS):
            self.assertEqual(checked(passing, path)["status"], "UNKNOWN")

    def test_with_no_kernel_a_lap_has_no_verdict_and_a_design_no_deck_has_is_still_unknown(self):
        with self.assertRaises(verify.NoKernel):
            checked(None, LAP)
        self.assertEqual(checked(None, CIRCUIT)["status"], "UNKNOWN", "the kernel is not asked about it, so it reads the same without one")

    def test_a_design_of_a_deck_is_handed_to_the_kernel_with_its_rules(self):
        seen = {}

        def refuse(files):
            seen.update(files)
            raise verify.BadAnswer("stopped by the test")

        with self.assertRaises(verify.NoVerdict):
            checked(refuse, LAP)
        self.assertEqual(set(seen), {"card", "design", "deck", "rules", "proofs"})
        card, design = json.loads(seen["card"]), json.loads(seen["design"])
        self.assertEqual((card["format"], design["format"]), ("petra-card/0", "petra-design/0"))
        self.assertEqual(design["card"], "sha256:" + hashlib.sha256(seen["card"].encode("utf-8")).hexdigest())

    def test_the_reason_names_four_kinds_at_most_and_cuts_a_long_one(self):
        self.assertEqual(verify.no_deck([]), "the design has no part, so there is no check to work out and nothing can pass it")
        self.assertIn("kind a, b, c, d and 2 more,", verify.no_deck("abcdef"))
        self.assertEqual(verify.clipped("k" * 64), "k" * 64)
        self.assertEqual(verify.clipped("k" * 70), "k" * 64 + "... (6 more characters)")


class Lines(unittest.TestCase):
    def test_the_report_names_the_card_and_the_design_by_hash(self):
        card, design = read_pair(CIRCUIT)
        with mock.patch.object(verify, "binary", lambda: "petra-verify"), mock.patch.object(verify, "ask", lambda _, files: never(files)):
            from petra.pipeline import check_text

            unix = check_text(card, design, "x.petra")
            windows = check_text(card.replace("\n", "\r\n"), design.replace("\n", "\r\n"), "x.petra")
        lines = unix.text().splitlines()
        self.assertEqual(lines[0], "workshop-lighting-radial: UNKNOWN")
        self.assertEqual(lines[1], f"reason     {verify.no_deck(['circuit'])}")
        self.assertEqual(lines[2], f"card       sha256:{hashlib.sha256(card.encode('utf-8')).hexdigest()}  x.card")
        self.assertEqual(lines[3], f"design     sha256:{hashlib.sha256(design.encode('utf-8')).hexdigest()}  x.petra")
        self.assertTrue(lines[4].startswith("path       none: "), lines[4])
        self.assertEqual(len(lines), 5, "and nothing else: Python has no working of its own to print")
        self.assertEqual([line for line in lines if "PASS" in line], [])
        self.assertEqual(unix.to_json()["card"], "x.card")
        self.assertEqual(unix.to_json()["hashes"], windows.to_json()["hashes"], "a checkout's line ends do not change the hash")


class Found(unittest.TestCase):
    """Where `binary` looks for the kernel: the environment, then the package, then the
    source tree. Each test has its own two places and no kernel named."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # The built kernel is where `lake build` puts it in a source tree, kernel/.lake/build/bin, so that its tree is the fifth
        # folder above it however deep the temporary folder is: /tmp/NAME on Linux is nearer the root than a kernel's own path.
        self.tree = Path(tmp.name, "tree")
        self.packaged, self.built = Path(tmp.name, "packaged", verify.EXE), self.tree / "kernel" / ".lake" / "build" / "bin" / verify.EXE
        for patch in (mock.patch.object(verify, "PACKAGED", self.packaged), mock.patch.object(verify, "BUILT", self.built),
                      mock.patch.dict(os.environ)):
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop("PETRA_VERIFY", None)
        verify.runs.cache_clear()
        self.addCleanup(verify.runs.cache_clear)

    def put(self, path: Path, mode: int = 0o755) -> None:
        path.parent.mkdir(parents=True)
        path.write_bytes(b"")
        path.chmod(mode)
        if path == self.built:      # the built kernel is used only from a source tree of Petra (verify.source_tree): this is one
            (self.tree / "kernel" / "lakefile.toml").write_text('name = "petra-kernel"\n', encoding="utf-8")
            (self.tree / "pyproject.toml").write_text('[project]\nname = "petra-lang"\n', encoding="utf-8")

    def test_with_none_named_packaged_or_built_there_is_no_kernel(self):
        self.assertIsNone(verify.binary())

    def test_the_kernel_built_in_the_source_tree_is_found(self):
        self.put(self.built)
        self.assertEqual(verify.binary(), str(self.built))

    def test_the_kernel_a_wheel_carries_comes_before_the_source_trees(self):
        self.put(self.packaged)
        self.put(self.built)
        with mock.patch.object(verify, "runs", lambda kernel: True):
            self.assertEqual(verify.binary(), str(self.packaged))

    def test_the_kernel_the_environment_names_comes_first(self):
        self.put(self.packaged)
        self.put(self.built)
        os.environ["PETRA_VERIFY"] = "named"
        self.assertEqual(verify.binary(), "named")

    def test_a_packaged_kernel_that_cannot_run_is_warned_of_once_and_passed_over(self):
        """An empty file with no execute bit: Windows cannot start it, and elsewhere its
        mode says it is no program."""
        self.put(self.packaged, 0o644)
        with self.assertWarns(RuntimeWarning) as caught:
            self.assertIsNone(verify.binary())
        self.assertIn(str(self.packaged), str(caught.warning))
        self.put(self.built)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            self.assertEqual(verify.binary(), str(self.built), "the source tree's kernel stands in, with no second warning")

    @unittest.skipUnless(KERNEL.is_file(), "no petra-verify is built here")
    def test_a_packaged_kernel_that_runs_is_used(self):
        with mock.patch.object(verify, "PACKAGED", KERNEL), warnings.catch_warnings():
            warnings.simplefilter("error")
            self.assertEqual(verify.binary(), str(KERNEL))

    @unittest.skipUnless(os.name == "nt" and KERNEL.is_file(), "needs Windows and a petra-verify built here")
    def test_a_packaged_kernel_that_imports_a_dll_this_windows_lacks_is_passed_over(self):
        """As a Windows older than 10 version 1903 sees the kernel, which imports icu.dll:
        the copy here imports icx.dll, which no Windows has. Windows shows no box for it."""
        self.packaged.parent.mkdir()
        self.packaged.write_bytes(KERNEL.read_bytes().replace(b"icu.dll\0", b"icx.dll\0"))
        began = time.monotonic()
        with self.assertWarns(RuntimeWarning):
            self.assertIsNone(verify.binary())
        self.assertLess(time.monotonic() - began, 30, "it did not wait for a click or for the time limit")


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Built(unittest.TestCase):
    def test_a_design_no_deck_has_reads_unknown(self):
        for path, kind in ((CIRCUIT, "circuit"), (TRUSS, "truss")):
            result = petra.check(*read_pair(path))
            self.assertEqual((result["status"], result["kernel"], result["reason"]), ("UNKNOWN", None, verify.no_deck([kind])))

    def test_no_number_of_a_part_no_deck_has_is_held_to_a_floor(self):
        """A size of zero, a number under zero, a moment of either sign: the floors are of types, and a part of no deck
        has none. The thirteenth review found such a pair refused as input, with a message about a size, where the
        reason it cannot be checked is that no deck has its kind."""
        head = 'petra 0\n\ncard "t" {\n  owner "me"\n}\n'
        for line in ("cold -5 degC", "gap 0", "slope -1", "offset -3 mm", "length 0 m"):
            with self.subTest(line=line):
                self.assertEqual(petra.check(head, f"petra 0\nwidget w {{\n  {line}\n}}\n")["status"], "UNKNOWN")
        load = 'load g {\n  on w moment in [-5 Nm, 5 Nm]\n  signed "me" source "s"\n}\n'
        self.assertEqual(petra.check(head + load, "petra 0\nwidget w {\n  size 3 mm\n}\n")["status"], "UNKNOWN")

    def test_a_card_under_which_the_old_checker_refuted_the_circuit_reads_unknown_too(self):
        """16 A on a B10 breaker: the Python checker refuted it. With that checker gone there is no cell to refute, and
        the right answer, FAIL, waits for the deck that brings circuits back."""
        card, design = read_pair(CIRCUIT)
        self.assertEqual(petra.check(card.replace("[0 A, 10 A]", "[0 A, 16 A]"), design)["status"], "UNKNOWN")

    def test_a_long_kind_costs_no_more_than_its_text(self):
        """The thirteenth review, finding 1: a kind of 12,000 characters on a part with 12,000 numbers took 1.7 s and
        122 MB while the files were written for the kernel, and four times that at twice the size. No file is written now."""
        import time

        head = 'petra 0\n\ncard "t" {\n  owner "me"\n}\n'
        began = time.process_time()
        result = petra.check(head, "petra 0\n" + "k" * 48_000 + " w {\n  a" + " 1" * 48_000 + "\n}\n")
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertLess(time.process_time() - began, 5)
        self.assertLess(len(json.dumps(result)), 2000, "and the report cuts the kind")

    def test_the_kernel_works_out_the_cells_of_a_lap(self):
        result = petra.check(*read_pair(LAP))
        self.assertEqual((result["status"], result["kernel"]["verdict"], result["kernel"]["cells_from"]), ("PASS_WAIVED", "PASS", "rules"))
        self.assertEqual(set(result["kernel"]["hashes"]), {"card", "design", "deck", "rules"})


if __name__ == "__main__":
    unittest.main()
