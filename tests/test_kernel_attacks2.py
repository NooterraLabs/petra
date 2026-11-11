"""The second hostile review of petra-verify (kernel/), one test per confirmed finding.

Each test asserts the behaviour the kernel should have. All five failed against the kernel at
438057d, where the review was made, and the first four pass now that the kernel charges
a proof for the work it does (docs/format.md, "Limits"). The fifth still fails. The review
found no false PASS, no false proof and no false refutation. Its findings were inputs under
1 MB that kept the kernel busy for far more than a minute, held more than a gigabyte, or
printed more than 5 MB, though the evaluation budget and the limits of docs/format.md were
meant to stop them. The tests are skipped when no kernel is built.

  1  An exp of a number near 45,000 took about 0.3 seconds and cost 3 evaluations. Closed: an
     exp pays for its terms times the bits it works in, about 900 million units for this one.
  2  A pick cost 1 + 2 per case, but the kernel tests every condition in each of up to 4,096
     orders, and a condition could be as wide as the file allowed. Closed: the conditions of
     a pick hold at most 1,024 orders, and a pick pays for its ways times its orders.
  3  Tape.eval kept the enclosure of every node of a leaf, and an enclosure may have ends of
     65,536 bits: a chain of negations of one long value held over a gigabyte. Closed: an
     enclosure is given up after the last node that reads it, and a leaf holds 128 MB of them.
  4  Partition.leaves built the box of every leaf before it evaluated one, each a copy of
     every input: inputs times leaves, while the budget counted the leaves alone. Closed:
     the leaves are walked one at a time, and each pays for its copy of the box.
  5  Cells made from a deck of rules are the parts times the lines of the grid, so 89 KB
     print 5.1 MB.

tests/test_kernel_limits.py holds each limit one by one (Work, Orders).
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from fractions import Fraction
from pathlib import Path

from petra import export, verify
from tests.test_kernel_attacks import export_lap, run_raw
from tests.test_kernel_limits import old_path

MB = 1_000_000


def num(x: Fraction) -> str:
    return export.number(Fraction(x))


def total(files: dict[str, str]) -> int:
    return sum(len(body.encode("utf-8")) for body in files.values())


def answered_within(test: unittest.TestCase, files: dict[str, str], seconds: float) -> dict:
    """The kernel's verdict, or a failure of the test when it takes longer than `seconds`."""
    try:
        _, out = run_raw(files, timeout=seconds)
    except subprocess.TimeoutExpired:
        test.fail(f"no verdict after {seconds:.0f} s for an input of {total(files) / MB:.3f} MB")
    return json.loads(out)


def peak_bytes(files: dict[str, str], timeout: float = 120) -> int:
    """The most memory the kernel's process held while it read the files and answered."""
    with tempfile.TemporaryDirectory() as tmp:
        command = [verify.binary()]
        for name, body in files.items():
            Path(tmp, f"{name}.json").write_text(body, encoding="utf-8", newline="\n")
            command += [f"--{name}", str(Path(tmp, f"{name}.json"))]
        p = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        timer = threading.Timer(timeout, p.kill)
        timer.start()
        try:
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes

                class Counters(ctypes.Structure):
                    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                        (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                                       "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                                       "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
                p.wait()
                counters = Counters()
                counters.cb = ctypes.sizeof(Counters)
                if not ctypes.windll.psapi.GetProcessMemoryInfo(wintypes.HANDLE(int(p._handle)), ctypes.byref(counters), counters.cb):
                    raise OSError("GetProcessMemoryInfo failed")
                return counters.PeakWorkingSetSize
            _, _, usage = os.wait4(p.pid, 0)
            p.returncode = 0
            return usage.ru_maxrss * (1 if sys.platform == "darwin" else 1024)
        finally:
            timer.cancel()


def bare(cells: list[dict]) -> dict[str, str]:
    """A design with no parts whose proofs.json lists `cells`."""
    return old_path(cells, [])


def proved(tape: dict, partition="leaf") -> dict:
    return {"subject": "s", "mechanism": "m", "entry": "e", "state": "proved", "tape": tape, "partition": partition}


def halves(input_, lo: Fraction, hi: Fraction, leaves: int):
    """A partition of [lo, hi] on `input_` into `leaves` leaves, balanced."""
    if leaves == 1:
        return "leaf"
    m = leaves // 2
    at = lo + (hi - lo) * Fraction(m, leaves)
    return {"input": input_, "at": num(at), "below": halves(input_, lo, at, m), "above": halves(input_, at, hi, leaves - m)}


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Time(unittest.TestCase):
    def test_an_exp_of_a_number_near_the_limit_is_paid_for(self):
        """Finding 1. 250 exps of different numbers near 45,000, 10 KB: 76 seconds. With a
        partition each leaf pays again, so the budget allows about 2 million of them."""
        nodes, exps = [], []
        for i in range(250):
            nodes += [["c", num(Fraction(45000) + Fraction(i + 1, 7919))], ["exp", len(nodes)]]
            exps.append(len(nodes) - 1)
        nodes += [["min", exps], ["neg", len(nodes)]]
        files = bare([proved({"inputs": [], "nodes": nodes, "roots": [len(nodes) - 1]})])
        self.assertLess(total(files), 12_000)
        answered_within(self, files, 30)

    def test_a_wide_condition_of_a_pick_is_paid_for(self):
        """Finding 2. Twelve inputs in [0, 1] each compared with 1 give 4,096 orders. The one
        case's condition is an `and` of 40,000 terms that hold, and a thirteenth input is split
        into 16 leaves: 0.49 MB, 132 seconds, for 800 evaluations of the budget."""
        nodes = [["s", k] for k in range(12)] + [["c", "1"], ["c", "-1"]]
        condition = ["and", [["le", k % 12, 12] for k in range(40_000)]]
        nodes.append(["pick", [[condition, 13], [None, 13]]])
        tape = {"inputs": [{"label": "dsg:", "lo": "0", "hi": "1"}] * 13, "nodes": nodes, "roots": [len(nodes) - 1]}
        files = bare([proved(tape, halves(12, Fraction(0), Fraction(1), 16))])
        self.assertLess(total(files), MB)
        answered_within(self, files, 30)


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Memory(unittest.TestCase):
    def test_a_chain_of_copies_of_a_long_value_holds_under_a_gigabyte(self):
        """Finding 3. A value of about 65,000 bits and 70,001 nodes that each negate the one
        before: 0.98 MB held 1.25 GB in a second. 45,000 nodes ["mul", [1]] held 1.9 GB from
        0.80 MB."""
        x = Fraction((1 << 6550) - 1, (1 << 6549) + 1)
        nodes = [["c", num(x)], ["mul", [0] * 10]] + [["neg", k + 1] for k in range(70_001)]
        files = bare([proved({"inputs": [], "nodes": nodes, "roots": [len(nodes) - 1]})])
        self.assertLess(total(files), MB)
        self.assertLess(peak_bytes(files), 1_000_000_000)

    def test_a_partition_over_many_inputs_holds_under_a_gigabyte(self):
        """Finding 4. 14,000 inputs that no node reads, one constant node, and 9,800 leaves on
        input 0: 0.99 MB held 1.3 GB, while the budget charged 29,400 evaluations."""
        tape = {"inputs": [{"label": "dsg:", "lo": "0", "hi": "9800"}] * 14_000, "nodes": [["c", "-1"]], "roots": [0]}
        files = bare([proved(tape, halves(0, Fraction(0), Fraction(9800), 9800))])
        self.assertLess(total(files), MB)
        self.assertLess(peak_bytes(files), 1_000_000_000)


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Output(unittest.TestCase):
    def test_many_parts_and_many_lines_of_the_grid_print_under_five_megabytes(self):
        """Finding 5. A deck of rules of one type with 100 lines of 64-byte names, each with a
        rule that reads four loads of 64-byte names, and 100 parts of 64-byte names that the
        card puts no load on: 10,000 open cells, each with the longest reason. 89 KB printed
        5.1 MB."""
        def name(prefix: str, k: int, width: int = 64) -> str:
            s = f"{prefix}{k}"
            return s + "q" * (width - len(s))
        anchor = {"standard": "AISC 360-22", "clause": "J3.2"}
        loads = [name(f"L{j}_", 0) for j in range(4)]
        kind = {"type": "t", "what": "w", "fields": [{"name": "x", "dim": "force", "what": "w"}],
                "loads": [{"name": n, "dim": "force", "what": "w"} for n in loads]}
        rules = {"format": "petra-rules/0", "name": "big", "about": "a", "rows": [], "types": [kind],
                 "grid": [{"type": "t", "mechanism": name("m", k), "what": "w", "anchor": anchor} for k in range(100)],
                 "rules": [{"id": "r/" + name("i", k, 62), "type": "t", "mechanism": name("m", k), "anchor": anchor, "says": "s",
                            "le": [["add"] + [["load", n] for n in loads], "x"]} for k in range(100)]}
        card = export.text({"format": "petra-card/0", "name": "c", "environment": None, "cases": [], "inputs": [], "claims": [],
                            "waivers": [], "tests": [], "probability_claims": []})
        parts = [{"name": name("p", i), "type": "t", "lines": [{"field": "x", "args": [{"number": {"dim": "force", "lo": "1", "hi": "1"}}]}]}
                 for i in range(100)]
        design = {"format": "petra-design/0", "name": "c", "card": export.sha256(card), "quantities": [], "params": [], "parts": parts}
        files = {"card": card, "design": json.dumps(design, separators=(",", ":")), "deck": export_lap("lap_pass")["deck"],
                 "rules": json.dumps(rules, separators=(",", ":")), "proofs": '{"format":"petra-proofs/0","cells":[]}'}
        self.assertLess(total(files), 100_000)
        _, out = run_raw(files, timeout=120)
        self.assertEqual(len(json.loads(out)["cells"]), 10_000)
        self.assertLess(len(out), 5 * MB)


if __name__ == "__main__":
    unittest.main()
