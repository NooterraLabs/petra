"""The fifth hostile review of petra-verify (kernel/) and the front end, one test per reproduced
finding.

Each test asserts the behaviour the checker should have, and each fails at 495f2b7 (rework),
where the review was made. The tests of the kernel are skipped when no kernel is built. The
ones marked "hostile deck" pass their own deck of rules with --rules.

  1  Hostile deck. `loaded` is asked once of a part, over every case of the card (Grid.lean
     `Static.holds`, grid.py `_static`), while a rule that reads loads has a cell for each case
     (docs/format.md, "Cells from a deck of rules", item 4). So a case can switch a rule or a
     line off for every other case. Deck B: the line joint.shear cannot arise when the joint
     carries T. Case gravity puts up to 100 N of V on a joint that carries 10 N, and the
     verdict is FAIL. Add case calm, which puts T of zero on the joint: the line is
     not_applicable, V counts as read by the line's rules, and the verdict is PASS, in the
     kernel and in petra/grid.py. Deck A, the natural form, `when not loaded T` beside
     `when loaded T`: the same case turns FAIL into UNKNOWN.
  2  Front end, petra/lang/lower.py `arg`. Each `given NAME` the card does not give is a problem
     that lists, sorted again, every given the card has. G givens and R such references make
     G x R names of messages: 0.351 MB of input, `petra check` held 1,420 MB and printed 330 MB.
  3  Front end. An unknown unit (petra/units.py:159) and a waiver of an unknown mode
     (lower.py:492) each print the whole table they come from: 400 and 2,400 bytes of message
     for 4 and 31 bytes of input, with no cap on how many. Just under 1 MB of unknown units
     printed 99.5 MB and held 513 MB.
  4  The card's environment is read by nothing for a design of a deck's types (docs/format.md
     says so), and nothing refuses it: the lap of examples/deck in marine C5 gets the PASS it
     gets indoors, while grid.read_parts refuses an `ambient` as a thing a deck does not read.

All four are closed. What was decided for each:

  1  `loaded` is taken out of the condition language. A rule that reads a load has a cell for
     each load case and a card states the load in every case, as zero where there is none, so
     "is the load there" has no meaning left. A deck that asks it anywhere is refused. The
     review's two tests asked that `loaded` be read under each case. They now hold decks A
     and B to the refusal, and hold the same decks with the condition taken out to FAIL
     whatever case is added.
  2, 3  A message lists at most four names and says how many there are, one message is
     printed once with how many times it arose, at most 100 problems are printed for a pair
     and the rest are counted, and a card or a design over 1 MB is refused before it is read.
  4  A card that names an environment is refused for a design of a deck's types, as an
     ambient is, in petra/grid.py and in the kernel under --rules.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import petra
from petra import grid, verify
from petra.registry import build_registry
from tests.test_kernel_attacks2 import MB
from tests.test_kernel_attacks3 import ANCHOR, PROCESSOR_SECONDS
from tests.test_kernel_grid import ask, strips

REPO = Path(__file__).resolve().parents[1]

MEGABYTES = 512
"""The most memory a check may hold on an input under 1 MB."""

JOINT = {"type": "joint", "what": "a joint", "fields": [{"name": "cap", "dim": "force", "what": "what it carries"}],
         "loads": [{"name": "V", "dim": "force", "least": "0 N", "what": "shear"},
                   {"name": "T", "dim": "force", "least": "0 N", "what": "tension"}]}
NATURAL = {"format": "petra-rules/0", "name": "pc", "about": "made up", "rows": [], "types": [JOINT],
           "grid": [{"type": "joint", "mechanism": "joint.shear", "what": "the shear", "anchor": ANCHOR}],
           "rules": [{"id": "pc/alone", "type": "joint", "mechanism": "joint.shear", "anchor": ANCHOR, "when": ["not", ["loaded", "T"]],
                      "says": "with no tension the shear is at most what the joint carries", "le": [["load", "V"], "cap"]},
                     {"id": "pc/combined", "type": "joint", "mechanism": "joint.shear", "anchor": ANCHOR, "when": ["loaded", "T"],
                      "says": "with tension the shear and the tension together are at most what the joint carries",
                      "le": [["add", ["load", "V"], ["load", "T"]], "cap"]}]}
"""Deck A: one line, a rule for a joint with no tension and a rule for one with tension."""
EXCUSED = {"format": "petra-rules/0", "name": "pc", "about": "made up", "rows": [], "types": [JOINT],
           "grid": [{"type": "joint", "mechanism": "joint.shear", "what": "the shear", "anchor": ANCHOR,
                     "unless": {"when": ["loaded", "T"], "why": "a joint that carries T is a tension joint, checked as one"}},
                    {"type": "joint", "mechanism": "joint.size", "what": "the size", "anchor": ANCHOR}],
           "rules": [{"id": "pc/shear", "type": "joint", "mechanism": "joint.shear", "anchor": ANCHOR,
                      "says": "the shear is at most what the joint carries", "le": [["load", "V"], "cap"]},
                     {"id": "pc/tension", "type": "joint", "mechanism": "joint.shear", "anchor": ANCHOR,
                      "says": "the tension is at most what the joint carries", "le": [["load", "T"], "cap"]},
                     {"id": "pc/size", "type": "joint", "mechanism": "joint.size", "anchor": ANCHOR,
                      "says": "the joint carries at least 1 N", "le": [["q", "1", "N"], "cap"]}]}
"""Deck B: the line joint.shear has an `unless` that turns on `loaded T`, and a second line
reads the cap alone, so the joint has a proved cell."""
DESIGN = "petra 0\n\njoint p {\n  cap 10 N\n}\n"
HEAD = 'petra 0\n\ncard "pc" {\n  owner "t@example.org"\n}\n'


def load(case: str, *lines: str) -> str:
    return f"\nload {case} {{\n" + "".join(f"  on {line}\n" for line in lines) + '  signed "t@example.org" source "test"\n}\n'


GRAVITY = load("gravity", "p V in [0 N, 100 N]")
CALM = load("calm", "p T in [0 N, 0 N]")
CALM_V = load("calm", "p V in [0 N, 1 N]", "p T in [0 N, 0 N]")


def grid_status(card: str, rules: dict) -> str:
    deck = grid.read_deck(json.dumps(rules))
    with mock.patch.object(grid, "decks", lambda: (deck,)):
        parsed = petra.lang.parse_design(card, DESIGN, "pc.petra", build_registry())
        return grid.check(parsed, deck)[0].status


def entries(said: dict) -> list[tuple[str, str]]:
    return [(c["entry"], c["state"]) for c in said["cells"]]


def with_calm(rules: dict, calm: str) -> tuple[dict, dict[str, str]]:
    """What the kernel says of case gravity alone, and the files of the card with `calm` beside
    it that carry the hints of gravity alone: the point that refutes the shear of case gravity
    is still a point of the card, and a kernel that makes the cell settles it with that point
    whatever petra/grid.py finds."""
    alone = strips(HEAD + GRAVITY, DESIGN, rules)
    both = strips(HEAD + GRAVITY + calm, DESIGN, rules)
    return ask(alone), {**both, "proofs": alone["proofs"]}


def unconditioned(rules: dict) -> dict:
    """The deck with every `when` and every `unless` that asks `loaded` taken out: what is
    left of decks A and B once the condition is gone."""
    return {**rules, "grid": [{k: v for k, v in a.items() if k != "unless"} for a in rules["grid"]],
            "rules": [{k: v for k, v in r.items() if k != "when"} for r in rules["rules"]]}


def measured_check(card: str, design: str, timeout: float = 120) -> tuple[int | None, int, float, int]:
    """`python -m petra check` on the pair, written to a folder of its own: the exit code (None
    when stopped at `timeout` on the clock), the bytes it printed, its processor seconds and the
    most memory its process held, from Windows' counters for that process."""
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                           "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                           "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]

    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "x.card").write_text(card, encoding="utf-8", newline="\n")
        Path(tmp, "x.petra").write_text(design, encoding="utf-8", newline="\n")
        with open(Path(tmp, "out"), "wb") as out:
            p = subprocess.Popen([sys.executable, "-B", "-m", "petra", "check", str(Path(tmp, "x.petra"))], cwd=str(REPO),
                                 stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT)
            stopped = []
            timer = threading.Timer(timeout, lambda: (stopped.append(True), p.kill()))  # this process only
            timer.start()
            try:
                p.wait()
            finally:
                timer.cancel()
            handle = wintypes.HANDLE(int(p._handle))
            counters = Counters()
            counters.cb = ctypes.sizeof(Counters)
            times = [wintypes.FILETIME() for _ in range(4)]
            ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
            ctypes.windll.kernel32.GetProcessTimes(handle, *(ctypes.byref(t) for t in times))
        seconds = sum((t.dwHighDateTime << 32) | t.dwLowDateTime for t in times[2:]) / 1e7
        return None if stopped else p.returncode, Path(tmp, "out").stat().st_size, seconds, counters.PeakWorkingSetSize


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class LoadedIsNoCondition(unittest.TestCase):
    """Finding 1, as decided: `loaded` is no condition. The review found that it was asked once
    of a part over every case, so that one case switched a line or a rule off under every
    other: deck B went from FAIL to PASS, and deck A from FAIL to UNKNOWN, when a case that
    puts a tension of zero on the joint was added. The kernel now refuses both decks, and a
    condition is over keys alone, which no load case changes."""

    def test_a_case_that_carries_no_tension_does_not_excuse_the_shear_of_another(self):
        """Finding 1, hostile deck B, whose line joint.shear has `unless loaded T`. At 495f2b7:
        case gravity alone gave shear/gravity refuted and FAIL, and with case calm, T in
        [0 N, 0 N], beside it the kernel made ("", not_applicable) and (size, proved) and said
        PASS. Now the deck is refused. With the `unless` taken out, the two cases together
        are FAIL: shear/gravity is refuted whatever calm states."""
        said = ask({**strips(HEAD + GRAVITY + CALM, DESIGN, unconditioned(EXCUSED)), "rules": json.dumps(EXCUSED)})
        self.assertEqual((said["verdict"], [f["file"] for f in said["findings"]]), ("ILL-FORMED", ["rules"]))
        self.assertIn("grid joint.shear: `loaded` is no condition", said["findings"][0]["why"])
        alone, files = with_calm(unconditioned(EXCUSED), CALM)
        self.assertEqual((alone["verdict"], entries(alone)[:1]), ("FAIL", [("shear/gravity", "refuted")]))
        said = ask(files)
        self.assertEqual(said["verdict"], "FAIL", f"the point that refutes shear/gravity is still a point of the card: {entries(said)}")
        self.assertEqual(entries(said)[:4], [("shear/calm", "open"), ("shear/gravity", "refuted"), ("tension/calm", "open"), ("tension/gravity", "open")],
                         "the hints are those of gravity alone, so nothing proves the tension of case calm")

    def test_a_case_that_carries_no_tension_keeps_the_rule_for_no_tension_in_another(self):
        """Finding 1, hostile deck A, with `when not loaded T` beside `when loaded T`. At
        495f2b7 case calm, V in [0 N, 1 N] and T in [0 N, 0 N], turned FAIL into UNKNOWN. Now
        the deck is refused. With the two `when` taken out both rules answer under each case,
        and the verdict is FAIL with and without case calm."""
        said = ask({**strips(HEAD + GRAVITY + CALM_V, DESIGN, unconditioned(NATURAL)), "rules": json.dumps(NATURAL)})
        self.assertEqual((said["verdict"], [f["file"] for f in said["findings"]]), ("ILL-FORMED", ["rules"]))
        self.assertIn("rule pc/alone: `loaded` is no condition", said["findings"][0]["why"])
        alone, files = with_calm(unconditioned(NATURAL), CALM_V)
        self.assertEqual((alone["verdict"], entries(alone)), ("FAIL", [("alone/gravity", "refuted"), ("combined/gravity", "open")]))
        said = ask(files)
        self.assertEqual(said["verdict"], "FAIL", f"case calm takes nothing away from case gravity: {entries(said)}")
        self.assertIn(("alone/gravity", "refuted"), entries(said))


class TheGridRefusesLoaded(unittest.TestCase):
    """Finding 1 in petra/grid.py, the second reading: it refuses the same two decks, and gives
    the decks without the condition the same FAIL with and without case calm."""

    def test_the_grid_does_not_excuse_the_shear_of_case_gravity(self):
        with self.assertRaises(grid.DeckError) as refused:
            grid.read_deck(json.dumps(EXCUSED))
        self.assertIn(grid.LOADED, str(refused.exception))
        self.assertEqual(grid_status(HEAD + GRAVITY, unconditioned(EXCUSED)), "FAIL")
        self.assertEqual(grid_status(HEAD + GRAVITY + CALM, unconditioned(EXCUSED)), "FAIL", "case calm excuses nothing of case gravity")

    def test_the_grid_keeps_the_rule_for_no_tension_in_case_gravity(self):
        with self.assertRaises(grid.DeckError) as refused:
            grid.read_deck(json.dumps(NATURAL))
        self.assertIn(grid.LOADED, str(refused.exception))
        self.assertEqual(grid_status(HEAD + GRAVITY, unconditioned(NATURAL)), "FAIL")
        self.assertEqual(grid_status(HEAD + GRAVITY + CALM_V, unconditioned(NATURAL)), "FAIL", "case calm takes nothing away from case gravity")


def givens(names: int, references: int) -> tuple[str, str]:
    """A card of `names` givens, and a plate whose thickness reads `given z`, which the card does
    not give, `references` times."""
    card = 'petra 0\n\ncard "c" {\n  owner "a"\n}\n\n' + "".join(
        f'given g{i} in [1 m, 1 m] signed "a" source "b"\n' for i in range(names))
    return card, "petra 0\n\nplate p {\n  thickness" + " given z" * references + "\n}\n"


@unittest.skipUnless(os.name == "nt", "the counters of a process are read from Windows")
class TheFrontEndKeepsTheBudget(unittest.TestCase):
    """Findings 2 and 3. `petra check` on a pair under 1 MB takes at most 30 processor seconds
    and 512 MB, and what it prints of a pair it refuses is not many times the pair."""

    def assertBounded(self, card: str, design: str, timeout: float = 120):
        size = len(card.encode()) + len(design.encode())
        self.assertLess(size, MB)
        code, printed, seconds, peak = measured_check(card, design, timeout)
        figures = f"{size / MB:.3f} MB in, exit {code}, {seconds:.1f} s, {peak / MB:.0f} MB held, {printed:,} bytes printed"
        self.assertIsNotNone(code, f"stopped after {timeout:.0f} s: {figures}")
        self.assertEqual(code, 3, f"the pair is refused as input: {figures}")
        self.assertLess(seconds, PROCESSOR_SECONDS, figures)
        self.assertLess(peak, MEGABYTES * MB, figures)
        self.assertLess(printed, 3 * size, figures)

    def test_givens_the_card_lacks_are_not_each_told_every_given_it_has(self):
        """Finding 2. 6,000 givens and 8,000 references to a given the card lacks, 0.351 MB:
        10.8 processor seconds, 1,420 MB held and 330 MB printed (measured in the review)."""
        self.assertBounded(*givens(6000, 8000))

    def test_unknown_units_are_not_each_told_every_unit(self):
        """Finding 3. 24,000 numbers with the unknown unit `z`, 0.096 MB: each prints every unit
        petra knows, about 7.5 MB in all. 249,980 of them, 999,987 bytes, printed 99.5 MB and
        held 513.2 to 513.9 MB in three runs of the review, over the 512,000,000 bytes."""
        self.assertBounded('petra 0\n\ncard "c" {\n  owner "a"\n}\n', "petra 0\n\nplate p {\n  thickness" + " 1 z" * 24000 + "\n}\n")

    def test_waivers_of_an_unknown_mode_are_not_each_told_every_mode(self):
        """Finding 3. 3,100 waivers of the unknown mode `q`, 0.096 MB: each prints the 106 modes
        of the models, about 7.4 MB in all (0.96 MB printed 75 MB in the review)."""
        card = 'petra 0\n\ncard "c" {\n  owner "a"\n}\n' + 'waive q on p by "a" reason "b"\n' * 3100
        self.assertBounded(card, "petra 0\n")


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class TheEnvironmentIsAnswered(unittest.TestCase):
    """Finding 4. A card that names an environment for a design of a deck's types is refused, as
    an `ambient` is, or its environment is a cell that is open until a rule reads it."""

    def test_a_lap_in_marine_c5_does_not_pass_on_what_was_checked_indoors(self):
        examples = REPO / "examples" / "deck"
        card = (examples / "lap_pass.card").read_text(encoding="utf-8")
        design = (examples / "lap_pass.petra").read_text(encoding="utf-8")
        marine = card.replace('  owner "s.engineer@example.org"\n', '  owner "s.engineer@example.org"\n  environment marine_c5\n')
        self.assertNotEqual(marine, card)
        indoors = petra.check(card, design, path=str(examples / "lap_pass.petra"), repair=False)
        self.assertEqual((indoors["status"], indoors["kernel"]["verdict"]), ("PASS", "PASS"))
        said = petra.check(marine, design, path=str(examples / "lap_pass.petra"), repair=False)
        verdicts = (said.get("status"), (said.get("kernel") or {}).get("verdict"))
        self.assertNotEqual(verdicts, ("PASS", "PASS"), "marine C5 is read by no cell, and the lap passes as it does indoors")


if __name__ == "__main__":
    unittest.main()
