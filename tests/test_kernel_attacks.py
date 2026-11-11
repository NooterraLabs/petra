"""A hostile reviewer's findings against petra-verify (kernel/), one test per confirmed one.

Each test asserts the behaviour the kernel should have, so it fails against the kernel as it
stands today and passes once the hole is closed. The tests are skipped when no kernel is built.
They reuse the helpers of tests/test_kernel_grid.py: `strips`, `ask`, `base` bundles are built
by exporting an honest design and then changing the bytes a designer would hand over.

Findings, by the classes of the review brief:
  6  the findings list is unbounded: one part with a long name and many bad lines makes the
     kernel emit hundreds of megabytes and use over a gigabyte, from an input under 1 MB.
  5  the documented downgrade is total: a card that places loads on parts, with `parts`
     stripped from the design and no --rules, is read as a models'-kinds design and can be
     driven to PASS with forged not-applicable and trivial proved cells, under the honest
     card's own hash.
"""
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from petra import verify

ROOT = Path(__file__).resolve().parents[1]


def run_raw(files: dict[str, str], timeout: float = 60) -> tuple[int, bytes]:
    """Run the kernel on the files and return (exit code, raw stdout bytes). Unlike verify.ask
    this keeps the size of the output, which one finding is about."""
    kernel = verify.binary()
    with tempfile.TemporaryDirectory() as tmp:
        command = [kernel]
        for name, body in files.items():
            path = Path(tmp, f"{name}.json")
            path.write_text(body, encoding="utf-8", newline="\n")
            command += [f"--{name}", str(path)]
        done = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    return done.returncode, done.stdout


def export_lap(name: str) -> dict[str, str]:
    """The five files petra.export writes for an example lap design, each as text."""
    from petra import export

    with tempfile.TemporaryDirectory() as tmp:
        export.export(str(ROOT / "examples" / "deck" / f"{name}.petra"), Path(tmp))
        return {p.stem: p.read_text(encoding="utf-8") for p in sorted(Path(tmp).iterdir())}


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Attacks(unittest.TestCase):
    def test_the_findings_list_is_bounded_for_a_long_repeated_name(self):
        """Class 6. A design of one part whose name is 20000 characters and 2000 lines of a
        field its type lacks makes the kernel repeat the name in a finding per line. The input
        is 0.13 MB; today the kernel emits about 40 MB and allocates hundreds of megabytes. The
        output a verdict carries should stay a small multiple of the input it describes."""
        files = export_lap("lap_pass")
        design = json.loads(files["design"])
        design["parts"] = [{"name": "N" * 20000, "type": "plate", "lines": [{"field": "x", "args": []} for _ in range(2000)]}]
        design["quantities"] = []
        files["design"] = json.dumps(design, separators=(",", ":"))
        self.assertLess(len(files["design"].encode()), 1_000_000, "the input is under 1 MB")
        code, out = run_raw(files, timeout=60)
        self.assertLess(len(out), 20_000_000, f"the kernel wrote {len(out) / 1e6:.0f} MB of verdict for a 0.13 MB input")

    def test_a_card_that_places_loads_is_not_checked_without_the_rules_deck(self):
        """Class 5. The known downgrade (strip `parts`, pass no --rules) is total. The card of
        a lap carries inputs with `on` and `field`: loads placed on a part, which only a card
        for a deck of rules has. With `parts` removed from the design and no --rules, the kernel
        reads it as a design of the models' kinds and trusts proofs.json: forged `not_applicable`
        cells and one trivial `proved` tape drive it to PASS, under the honest card's own hash.
        A card that places loads should not pass without the deck it was placed against."""
        files = export_lap("lap_fail")      # genuinely refuted against the deck: pull of 60 kip
        with_rules = verify.ask(verify.binary(), files)
        self.assertEqual(with_rules["verdict"], "FAIL", "the honest files, with --rules, FAIL")
        card = json.loads(files["card"])
        self.assertTrue(any("on" in i and "field" in i for i in card["inputs"]), "the card places loads on parts")

        design = json.loads(files["design"])
        del design["parts"]
        trivial = {"inputs": [{"label": "dsg:x", "lo": "0", "hi": "1"}], "nodes": [["c", "-1"]], "roots": [0]}
        cells = []
        for c in json.loads(export_lap("lap_pass")["proofs"])["cells"]:
            if c["state"] == "proved":
                cells.append({"subject": c["subject"], "mechanism": c["mechanism"], "entry": c["entry"], "state": "proved", "tape": trivial, "partition": "leaf"})
            else:
                cells.append({"subject": c["subject"], "mechanism": c["mechanism"], "entry": c["entry"], "state": "not_applicable", "why": "forged"})
        forged = {
            "card": files["card"],      # unchanged: the printed card hash matches the honest one
            "design": json.dumps({**design, "card": "sha256:" + hashlib.sha256(files["card"].encode()).hexdigest()}),
            "deck": files["deck"],
            "proofs": json.dumps({"format": "petra-proofs/0", "cells": cells}),
        }
        said = verify.ask(verify.binary(), forged)      # no --rules
        self.assertEqual(said["hashes"]["card"], with_rules["hashes"]["card"], "the card hash is the honest one")
        self.assertNotEqual(said["verdict"], "PASS", "a card that places loads must not PASS without its deck of rules")


if __name__ == "__main__":
    unittest.main()
