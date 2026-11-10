"""`petra check` asks the kernel, petra-verify, to check its report (petra/verify.py).

The shell is tested with a stand-in for the kernel's answer, so these tests run with no
kernel built. The `Built` tests run the real one when PETRA_VERIFY names it or the source
tree holds a build, as CI's does.
"""
import hashlib
import json
import unittest
from pathlib import Path
from unittest import mock

import petra
from petra import verify
from petra.files import read_pair

ROOT = Path(__file__).resolve().parents[1]
CIRCUIT = ROOT / "examples" / "circuit_pass.petra"
TRUSS = ROOT / "examples" / "truss_pass.petra"


def answer(files, verdict="PASS", edit=lambda cells: None, findings=()):
    """What a kernel that agrees with every cell would print, after `edit` changes its cells."""
    cells = [{"subject": c["subject"], "mechanism": c["mechanism"], "entry": c["entry"], "claimed": c["state"], "state": c["state"]}
             for c in json.loads(files["proofs"])["cells"]]
    edit(cells)
    return {"verdict": verdict, "hashes": {"card": "sha256:c", "design": "sha256:d", "deck": "sha256:k"}, "findings": list(findings), "cells": cells}


def checked(kernel, path=CIRCUIT) -> dict:
    """petra.check of the pair at `path`, with `kernel` answering in place of petra-verify,
    or with no kernel when it is None."""
    found = None if kernel is None else "petra-verify"
    with mock.patch.object(verify, "binary", lambda: found), mock.patch.object(verify, "ask", lambda _, files: kernel(files)):
        return petra.check(*read_pair(path), path=str(path), repair=False)


class Shell(unittest.TestCase):
    def test_a_kernel_that_agrees_is_counted_and_its_hashes_kept(self):
        result = checked(answer)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["kernel"], {"verdict": "PASS", "checked": 8, "proofs": 8,
                                            "hashes": {"card": "sha256:c", "design": "sha256:d", "deck": "sha256:k"}})

    def test_the_kernel_reads_the_files_of_the_format(self):
        seen = {}
        checked(lambda files: seen.update(files) or answer(files))
        self.assertEqual(set(seen), {"card", "design", "deck", "proofs"})
        card, design = json.loads(seen["card"]), json.loads(seen["design"])
        self.assertEqual((card["format"], design["format"]), ("petra-card/0", "petra-design/0"))
        self.assertEqual(design["card"], "sha256:" + hashlib.sha256(seen["card"].encode("utf-8")).hexdigest())

    def test_a_proof_the_kernel_rejects_is_a_disagreement_nothing_catches(self):
        def reject(cells):
            cells[0].update(state="open", reason="the upper end of root 0 is above zero")

        with self.assertRaises(verify.Disagreement) as ctx:
            checked(lambda files: answer(files, "UNKNOWN", reject))
        self.assertIn("the upper end of root 0 is above zero", str(ctx.exception))
        self.assertIn("lighting", str(ctx.exception), "it names the cell")

    def test_a_proof_the_kernel_has_no_rule_for_is_counted_and_is_no_disagreement(self):
        result = checked(lambda files: answer(files, "UNKNOWN"), TRUSS)
        self.assertEqual(result["status"], "PASS", "the Python checker's verdict stands")
        kernel = result["kernel"]
        self.assertEqual(kernel["verdict"], "UNKNOWN")
        self.assertLess(kernel["checked"], kernel["proofs"])
        self.assertEqual(kernel["proofs"], 37, "10 obligations and the 27 validity proofs of their models")

    def test_a_pair_the_kernel_finds_ill_formed_is_an_input_error(self):
        finding = {"rule": "types.3", "file": "design", "item": "lighting.wire.length", "why": "a size is above 0, and this one goes down to 0"}
        result = checked(lambda files: answer(files, "ILL-FORMED", findings=[finding]))
        self.assertEqual(result["status"], "INPUT_ERROR")
        self.assertIn("petra-verify refuses the design: lighting.wire.length: a size is above 0", result["error"])

    def test_a_kernel_that_reads_other_cells_is_a_disagreement(self):
        with self.assertRaises(verify.Disagreement):
            checked(lambda files: answer(files, edit=lambda cells: cells.pop()))

    def test_with_no_kernel_the_report_says_so(self):
        result = checked(None)
        self.assertEqual((result["status"], result["kernel"]), ("PASS", None))


class Lines(unittest.TestCase):
    def test_the_line_says_how_much_the_kernel_checked(self):
        hashes = {}
        self.assertEqual(verify.Kernel("PASS", 8, 8, hashes).line("PASS"), "petra-verify checked 8 of 8 proofs and agrees")
        self.assertEqual(verify.Kernel("PASS", 19, 22, hashes).line("PASS"),
                         "petra-verify checked 19 of 22 proofs and agrees; it has no rule yet for the other 3")
        self.assertEqual(verify.Kernel("UNKNOWN", 0, 37, hashes).line("PASS"),
                         "petra-verify has no rule yet for any of the 37 proofs; its own verdict is UNKNOWN")

    def test_the_report_names_the_card_and_the_design_by_hash(self):
        card, design = read_pair(CIRCUIT)
        with mock.patch.object(verify, "binary", lambda: None):
            from petra.registry import build_registry
            from petra.repair import check_text
            from petra.solvers import SolverSource

            unix = check_text(card, design, "x.petra", build_registry(), (SolverSource(),), moves=False)
            windows = check_text(card.replace("\n", "\r\n"), design.replace("\n", "\r\n"), "x.petra", build_registry(), (SolverSource(),), moves=False)
        lines = unix.text().splitlines()
        self.assertTrue(lines[2].startswith("scope  "))
        self.assertEqual(lines[3], f"card       sha256:{hashlib.sha256(card.encode('utf-8')).hexdigest()}  x.card")
        self.assertEqual(lines[4], f"design     sha256:{hashlib.sha256(design.encode('utf-8')).hexdigest()}  x.petra")
        self.assertEqual(lines[5], f"kernel     {verify.NO_KERNEL}")
        self.assertEqual(unix.to_json()["card"], "x.card")
        self.assertEqual(unix.to_json()["hashes"], windows.to_json()["hashes"], "a checkout's line ends do not change the hash")


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Built(unittest.TestCase):
    def test_the_kernel_checks_every_proof_of_the_circuit(self):
        result = petra.check(*read_pair(CIRCUIT), repair=False)
        self.assertEqual(result["kernel"]["verdict"], "PASS")
        self.assertEqual((result["kernel"]["checked"], result["kernel"]["proofs"]), (8, 8))
        self.assertEqual(set(result["kernel"]["hashes"]), {"card", "design", "deck"})

    def test_the_kernel_agrees_on_a_refutation(self):
        card, design = read_pair(CIRCUIT)
        result = petra.check(card.replace("[0 A, 10 A]", "[0 A, 16 A]"), design, repair=False)
        self.assertEqual((result["status"], result["kernel"]["verdict"]), ("FAIL", "FAIL"))

    def test_the_kernel_has_no_rule_for_the_truss_yet(self):
        result = petra.check(*read_pair(TRUSS), repair=False)
        self.assertEqual((result["status"], result["kernel"]["verdict"]), ("PASS", "UNKNOWN"))


if __name__ == "__main__":
    unittest.main()
