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


def answer(files, verdict="UNKNOWN", cells=(), findings=()):
    """What the kernel prints for the files of a design it was handed no deck of rules for: the
    hash of each file, no cell, and UNKNOWN. `verdict`, `cells` and `findings` make it say
    something else."""
    hashes = {name: (f"sha256:{hashlib.sha256(files[name].encode('utf-8')).hexdigest()}" if name in files else None) for name in verify.HASHED}
    return {"verdict": verdict, "hashes": hashes, "cells_from": "proofs", "findings": list(findings), "waived": [], "cells": list(cells)}


def checked(kernel, path=CIRCUIT) -> dict:
    """petra.check of the pair at `path`, with `kernel` answering in place of petra-verify,
    or with no kernel when it is None."""
    found = None if kernel is None else "petra-verify"
    with mock.patch.object(verify, "binary", lambda: found), mock.patch.object(verify, "ask", lambda _, files: kernel(files)):
        return petra.check(*read_pair(path), path=str(path))


class Shell(unittest.TestCase):
    """A design with a part of a kind no deck has: the kernel is handed its card and its
    quantities with no deck of rules, and its verdict is the status."""

    def test_the_kernels_unknown_is_the_status_and_its_hashes_are_kept(self):
        result = checked(answer)
        self.assertEqual((result["status"], result["reason"], result["kinds"]), ("UNKNOWN", verify.no_deck(["circuit"]), ["circuit"]))
        self.assertEqual({k: v for k, v in result["kernel"].items() if k != "hashes"}, {"verdict": "UNKNOWN", "checked": 0, "cells_from": "proofs", "waived": []})
        self.assertEqual(set(result["kernel"]["hashes"]), {"card", "design", "deck"}, "the kernel read no deck of rules, and its null for one is left out")
        self.assertEqual((result["cells"], result["deck"], result["path"]), ([], None, "none"))

    def test_a_kernel_that_says_pass_of_these_files_is_not_taken(self):
        """The files hold no deck of rules, so a PASS is not the kernel's."""
        proved = [{"subject": "lighting", "mechanism": "wire.ampacity", "entry": "", "state": "proved"}]
        for cells in ((), proved):
            with self.assertRaises(verify.NoVerdict):
                checked(lambda files: answer(files, "PASS", cells))

    def test_a_kernel_that_gives_these_files_a_cell_or_a_fail_is_not_taken(self):
        """It was handed no deck of rules and no proofs, so it has no cell to refute or to leave open."""
        for verdict, state in (("FAIL", "refuted"), ("UNKNOWN", "open")):
            with self.assertRaises(verify.NoVerdict):
                checked(lambda files: answer(files, verdict, [{"subject": "lighting", "mechanism": "wire.ampacity", "entry": "", "state": state}]))

    def test_the_kernel_reads_the_files_of_the_format_and_no_deck_of_rules(self):
        seen = {}
        checked(lambda files: seen.update(files) or answer(files))
        self.assertEqual(set(seen), {"card", "design", "deck"}, "no rules and no proofs: Python writes no cell for the kernel to take")
        card, design, deck = (json.loads(seen[name]) for name in ("card", "design", "deck"))
        self.assertEqual((card["format"], design["format"], deck["format"]), ("petra-card/0", "petra-design/0", "petra-deck/0"))
        self.assertEqual(design["card"], "sha256:" + hashlib.sha256(seen["card"].encode("utf-8")).hexdigest())
        self.assertNotIn("parts", design, "the parts are read only against the deck that has their types")
        self.assertNotIn("rules", deck)

    def test_a_pair_the_kernel_finds_ill_formed_is_an_input_error(self):
        finding = {"rule": "types.3", "file": "design", "item": "lighting.wire.length", "why": "a size is above 0, and this one goes down to 0"}
        result = checked(lambda files: answer(files, "ILL-FORMED", findings=[finding]))
        self.assertEqual(result["status"], "INPUT_ERROR")
        self.assertIn("petra-verify refuses the design: lighting.wire.length: a size is above 0", result["error"])

    def test_with_no_kernel_there_is_no_verdict(self):
        for path in (CIRCUIT, LAP):
            with self.assertRaises(verify.NoKernel):
                checked(None, path)


class Lines(unittest.TestCase):
    def test_the_report_names_the_card_and_the_design_by_hash(self):
        card, design = read_pair(CIRCUIT)
        with mock.patch.object(verify, "binary", lambda: "petra-verify"), mock.patch.object(verify, "ask", lambda _, files: answer(files)):
            from petra.pipeline import check_text

            unix = check_text(card, design, "x.petra")
            windows = check_text(card.replace("\n", "\r\n"), design.replace("\n", "\r\n"), "x.petra")
        lines = unix.text().splitlines()
        self.assertEqual(lines[0], "workshop-lighting-radial: UNKNOWN")
        self.assertEqual(lines[1], f"reason     {verify.no_deck(['circuit'])}")
        self.assertEqual(lines[2], f"card       sha256:{hashlib.sha256(card.encode('utf-8')).hexdigest()}  x.card")
        self.assertEqual(lines[3], f"design     sha256:{hashlib.sha256(design.encode('utf-8')).hexdigest()}  x.petra")
        self.assertEqual(lines[4], "kernel     petra-verify gives UNKNOWN: it was handed no deck of rules and worked out no cell")
        self.assertTrue(lines[5].startswith("path       none: "), lines[5])
        self.assertEqual(len(lines), 6, "and nothing else: Python has no working of its own to print")
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
    def test_the_kernel_gives_a_design_of_no_deck_unknown(self):
        for path, kind in ((CIRCUIT, "circuit"), (TRUSS, "truss")):
            result = petra.check(*read_pair(path))
            self.assertEqual((result["status"], result["kernel"]["verdict"], result["reason"]), ("UNKNOWN", "UNKNOWN", verify.no_deck([kind])))
            self.assertEqual(set(result["kernel"]["hashes"]), {"card", "design", "deck"})

    def test_a_card_under_which_the_old_checker_refuted_the_circuit_reads_unknown_too(self):
        """16 A on a B10 breaker: the Python checker refuted it, and the kernel checked that refutation's arithmetic. With
        that checker gone there is no cell to refute, and the right answer, FAIL, waits for the deck that brings circuits back."""
        card, design = read_pair(CIRCUIT)
        result = petra.check(card.replace("[0 A, 10 A]", "[0 A, 16 A]"), design)
        self.assertEqual((result["status"], result["kernel"]["verdict"]), ("UNKNOWN", "UNKNOWN"))

    def test_the_kernel_refuses_a_size_under_its_floor_with_no_deck_of_rules(self):
        """The type rules hold for every pair the kernel reads: a length of zero is no size, whatever kind its part is of."""
        card, design = read_pair(CIRCUIT)
        self.assertIn("length 18 m", design)
        result = petra.check(card, design.replace("length 18 m", "length 0 m", 1))
        self.assertEqual(result["status"], "INPUT_ERROR")
        self.assertIn("petra-verify refuses the design: lighting.wire.length: a size is above 0", result["error"])

    def test_the_kernel_works_out_the_cells_of_a_lap(self):
        result = petra.check(*read_pair(LAP))
        self.assertEqual((result["status"], result["kernel"]["verdict"], result["kernel"]["cells_from"]), ("PASS_WAIVED", "PASS", "rules"))
        self.assertEqual(set(result["kernel"]["hashes"]), {"card", "design", "deck", "rules"})


if __name__ == "__main__":
    unittest.main()
