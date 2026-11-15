"""Nothing but petra-verify decides a verdict (plan step 1.1).

Every way into a check is run here: the command line as text and as JSON, the server's
check tool, `petra.check`, which the skill names beside the two, `petra.check_file`, and
the two functions that call petra/verify.py, `repair.check_text` and `grid.checked`. Each is run with no kernel,
with a kernel that refuses in each way one can, and with the real one.

The faults these tests were written against, at 1e34098:

- With no kernel the Python checker's verdict stood, and `petra check` exited 0 on a PASS.
- A kernel that printed a verdict and then exited 3, or wrote a panic to its error stream,
  read as "checked and agrees": its exit code and its error stream were dropped.
- `petra check` printed PASS and exited 0 for a truss the kernel calls UNKNOWN, with the
  kernel's own verdict in one line of the report.
- The kernel alone gave PASS to a failing truss when handed a proofs file with one trivial
  proved cell and every other cell written as not applicable. Without a deck of rules it
  takes the cells of proofs.json as they come, and every design of the models' kinds was
  checked that way.

The tests that run a kernel are skipped when none is built.
"""
import contextlib
import functools
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import petra
from petra import export, mcp, verify
from petra.cli import EXIT_CODES, main
from petra.files import card_of, read_pair

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
TRUSS = EXAMPLES / "truss_pass.petra"            # the Python checker says PASS, and no proof has a tape
TRUSS_FAIL = EXAMPLES / "truss_fail.petra"       # the Python checker says FAIL, and no proof has a tape
CIRCUIT = EXAMPLES / "circuit_pass.petra"        # the Python checker says PASS, and every proof has a tape
TAB = EXAMPLES / "steel" / "shear_tab.petra"     # the same, of a steel kind
LAP = EXAMPLES / "deck" / "lap_pass.petra"       # a design of a deck of rules that passes on waivers
LAP_FAIL = EXAMPLES / "deck" / "lap_fail.petra"  # one the deck refutes
MODELS = (TRUSS, TRUSS_FAIL, CIRCUIT, TAB)
PASSES = ("PASS", "PASS_WAIVED", "MARGINAL")
NO_VERDICT = "NO_VERDICT"
CODES = {code: name for name, code in EXIT_CODES.items()}
KERNEL = unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")

REAL = getattr(verify, "run", None)
"""The one function of petra/verify.py that starts the kernel: the command in, and out its
exit code, what it printed and what it wrote to its error stream."""


def cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def refused(out: str, err: str) -> str:
    """Exit code 4 is no verdict: nothing on stdout, and on stderr the reason in a line, or
    for a disagreement of the two checkers its traceback."""
    assert out == "" and ("no verdict" in err or "petra.verify.Disagreement" in err), (out, err[-400:])
    return NO_VERDICT


def by_text(path: Path) -> str:
    """`petra check PATH`: the status of its exit code. What it prints first must hold that
    status, and no other."""
    code, out, err = cli("check", str(path))
    if code == EXIT_CODES["INTERNAL_ERROR"]:
        return refused(out, err)
    if code == EXIT_CODES["INPUT_ERROR"]:
        assert out == "", out
        return "INPUT_ERROR"
    first = out.split("\n", 1)[0]
    said = [word.strip(":") for word in first.split() if word.strip(":") in EXIT_CODES]
    assert said == [CODES[code]], f"exit code {code} under the line {first!r}"
    return CODES[code]


def by_json(path: Path) -> str:
    """`petra check PATH --json`: the status of its JSON, which its exit code must give too."""
    code, out, err = cli("check", str(path), "--json")
    if code == EXIT_CODES["INTERNAL_ERROR"]:
        return refused(out, err)
    if code == EXIT_CODES["INPUT_ERROR"]:
        assert out == "", out
        return "INPUT_ERROR"
    status = json.loads(out)["status"]
    assert EXIT_CODES[status] == code, f"exit code {code} with the status {status}"
    return status


def by_server(path: Path) -> str:
    """The server's check tool, as its worker runs it."""
    reply = mcp._call({"name": "check", "arguments": {"path": str(path)}})
    text = reply["content"][0]["text"]
    if reply["isError"]:
        assert "structuredContent" not in reply, reply
        return NO_VERDICT if text.startswith("no verdict") else "INPUT_ERROR"
    status = reply["structuredContent"]["status"]
    assert status in text.split("\n", 1)[0], text
    return status


def by_api(path: Path) -> str:
    """`petra.check(card, design)`, the call the skill gives for Python."""
    try:
        return petra.check(*read_pair(path), path=str(path), repair=False)["status"]
    except verify.NoVerdict:
        return NO_VERDICT


def by_check_text(path: Path) -> str:
    """repair.check_text, which every way above goes through."""
    from petra import build_registry
    from petra.repair import check_text
    from petra.solvers import SolverSource

    try:
        return check_text(*read_pair(path), str(path), build_registry(), (SolverSource(),), moves=False).status
    except verify.NoVerdict:
        return NO_VERDICT


def by_grid(path: Path) -> str:
    """grid.checked, the other caller of petra/verify.py: a design of a deck of rules."""
    from petra import build_registry, grid
    from petra.lang import parse_design
    from petra.models.base import ComponentError

    card, text = read_pair(path)
    design = parse_design(card, text, str(path), build_registry())
    try:
        return grid.checked(design, grid.owner(design), card, text, card_of(str(path))).status
    except verify.NoVerdict:
        return NO_VERDICT
    except ComponentError:
        return "INPUT_ERROR"


def by_check_file(path: Path) -> str:
    """`petra.check_file(path)`, a check of a file."""
    from petra.repair import INPUT_ERRORS

    try:
        return petra.check_file(path).status
    except verify.NoVerdict:
        return NO_VERDICT
    except INPUT_ERRORS:
        return "INPUT_ERROR"


WAYS = {"petra check": by_text, "petra check --json": by_json, "the server": by_server, "petra.check": by_api, "petra.check_file": by_check_file,
        "check_text": by_check_text}


SLOW = (TRUSS, TRUSS_FAIL)
"""A truss takes the solvers 6 to 9 s, so it goes through two ways in, and the rest through all."""


def ways(path: Path) -> dict:
    if path in SLOW:
        return {"petra check": by_text, "petra.check": by_api}
    return {**WAYS, **({"grid.checked": by_grid} if path in (LAP, LAP_FAIL) else {})}


@functools.cache
def exported(path: Path) -> dict[str, str]:
    """The files petra.export writes for the pair at `path`, each as its text by its name."""
    with tempfile.TemporaryDirectory() as tmp:
        export.export(str(path), Path(tmp))
        return {p.stem: p.read_text(encoding="utf-8") for p in sorted(Path(tmp).iterdir())}


def kernel_alone(path: Path, proofs: str | None = None) -> tuple[str, dict]:
    """What petra-verify itself says of the pair at `path`, run on the files petra.export
    writes, or with `proofs` in place of the proofs it wrote: the verdict of its exit code,
    and what it printed."""
    files = {**exported(path), **({} if proofs is None else {"proofs": proofs})}
    with tempfile.TemporaryDirectory() as tmp:
        for name, body in files.items():
            Path(tmp, f"{name}.json").write_text(body, encoding="utf-8", newline="\n")
        command = [verify.binary(), *(part for name in files for part in (f"--{name}", str(Path(tmp, f"{name}.json"))))]
        done = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True)
    said = json.loads(done.stdout)
    assert done.stderr == b"" and {"PASS": 0, "FAIL": 1, "UNKNOWN": 2, "ILL-FORMED": 3}[said["verdict"]] == done.returncode
    return said["verdict"], said


@contextlib.contextmanager
def no_kernel():
    """No PETRA_VERIFY, no kernel in the package and none built in the tree."""
    nowhere = Path(tempfile.gettempdir(), "petra-no-kernel", "petra-verify")
    env = {k: v for k, v in os.environ.items() if k != "PETRA_VERIFY"}
    with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(verify, "PACKAGED", nowhere), mock.patch.object(verify, "BUILT", nowhere):
        yield


def refusing(how):
    """The real kernel with `how` between it and the caller: `how` takes its exit code, what
    it printed and its error stream, and gives the three as the caller is to see them."""
    return mock.patch.object(verify, "run", lambda command: how(*REAL(command)))


def rewritten(code: int, **keys):
    """A kernel that prints what the real one does with `keys` put over it, and exits `code`."""
    return lambda _, out, err: (code, json.dumps({**json.loads(out), **keys}).encode("utf-8"), err)


REFUSALS = {
    "prints its verdict and exits 3": lambda code, out, err: (3, out, err),
    "prints its verdict and exits 1": lambda code, out, err: (1, out, err),
    "prints its verdict and is killed": lambda code, out, err: (-9, out, err),
    "prints its verdict and exits 70": lambda code, out, err: (70, out, err),
    "prints its verdict and panics on its error stream": lambda code, out, err: (code, out, err + b"PANIC at Petra.Grid.cells Petra.Grid:1:1: index out of bounds\n"),
    "prints nothing": lambda code, out, err: (0, b"", b""),
    "prints half of its verdict": lambda code, out, err: (code, out[:len(out) // 2], err),
    "prints text that is no JSON": lambda code, out, err: (0, b"PASS\n", err),
    "prints a list": lambda code, out, err: (0, b"[]", err),
    "prints a verdict that is none of the four": rewritten(0, verdict="PASS_WAIVED"),
    "prints PASS and exits as it would have": lambda code, out, err: rewritten(code, verdict="PASS")(code, out, err),
    "prints PASS and exits 0": rewritten(0, verdict="PASS"),
    "prints PASS, exits 0 and says the cells are a deck's": rewritten(0, verdict="PASS", cells_from="rules"),
}
"""Each is a kernel whose answer cannot be taken, or one that says PASS where the real one
does not. None may read as a pass at any way in."""


class NoKernel(unittest.TestCase):
    """With no kernel there is no verdict: nothing printed to stdout, exit code 4, and the
    reason on the error stream. The Python checker, the grid of a deck and the solvers
    all ran, and none of them decides."""

    def test_no_way_in_gives_a_verdict_without_a_kernel(self):
        for path in (CIRCUIT, TRUSS, TRUSS_FAIL, LAP, LAP_FAIL):
            for name, way in ways(path).items():
                with self.subTest(path=path.name, way=name), no_kernel():
                    self.assertEqual(way(path), NO_VERDICT)

    def test_the_refusal_says_where_a_kernel_is_looked_for(self):
        with no_kernel():
            code, out, err = cli("check", str(CIRCUIT))
        self.assertEqual((code, out), (EXIT_CODES["INTERNAL_ERROR"], ""))
        self.assertIn("PETRA_VERIFY", err)
        self.assertNotIn("Traceback", err)

    def test_a_kernel_that_is_named_and_is_not_there_gives_no_verdict(self):
        """PETRA_VERIFY names a file that does not exist, a folder, and a file that is not a
        program. Each was a traceback, or with a folder a PermissionError."""
        with tempfile.TemporaryDirectory() as tmp:
            text = Path(tmp, "petra-verify")
            text.write_text("not a program\n", encoding="utf-8")
            for named in (str(Path(tmp, "missing")), tmp, str(text)):
                for path in (CIRCUIT, LAP):
                    for name, way in ways(path).items():
                        with self.subTest(named=Path(named).name, path=path.name, way=name), mock.patch.dict(os.environ, {"PETRA_VERIFY": named}):
                            self.assertEqual(way(path), NO_VERDICT)

    def test_the_server_in_its_own_process_answers_with_an_error_and_no_verdict(self):
        """`petra mcp` as a client starts it, with PETRA_VERIFY naming a file that is not there."""
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "check", "arguments": {"path": str(LAP)}}}
        nowhere = str(Path(tempfile.gettempdir(), "petra-no-kernel", "petra-verify"))
        done = subprocess.run([sys.executable, "-m", "petra", "mcp"], cwd=ROOT, input=json.dumps(request).encode("utf-8") + b"\n", capture_output=True,
                              env={**os.environ, "PETRA_VERIFY": nowhere}, timeout=300)
        (line,) = done.stdout.splitlines()
        reply = json.loads(line)["result"]
        self.assertTrue(reply["isError"], reply)
        self.assertTrue(reply["content"][0]["text"].startswith("no verdict: "), reply)
        self.assertNotIn("structuredContent", reply)

    def test_an_ill_formed_pair_is_an_input_error_with_or_without_a_kernel(self):
        """What the language refuses never reaches a kernel, so it reads the same without one."""
        with tempfile.TemporaryDirectory() as tmp, no_kernel():
            broken = Path(tmp, "broken.petra")
            broken.write_text("petra 0\nshear_tab {\n", encoding="utf-8")
            Path(tmp, "broken.card").write_text(read_pair(TAB)[0], encoding="utf-8")
            for name, way in WAYS.items():
                with self.subTest(way=name):
                    self.assertEqual(way(broken), "INPUT_ERROR")


@KERNEL
class Refusing(unittest.TestCase):
    """A kernel whose answer cannot be taken gives no verdict, and one that says PASS where
    the real one does not never reads as a pass."""

    def test_no_refusing_kernel_reads_as_a_pass(self):
        for said, how in REFUSALS.items():
            for path in (CIRCUIT, LAP_FAIL):
                for name, way in ways(path).items():
                    with self.subTest(kernel=said, path=path.name, way=name), refusing(how):
                        self.assertNotIn(way(path), PASSES)

    def test_an_exit_code_or_an_error_stream_at_odds_with_the_verdict_is_no_verdict(self):
        """The lap passes on its waivers with the real kernel. With one that prints the same
        verdict and then exits otherwise, or panics, it has no verdict."""
        self.assertEqual(by_json(LAP), "PASS_WAIVED")
        for said in list(REFUSALS)[:9]:
            for name, way in ways(LAP).items():
                with self.subTest(kernel=said, way=name), refusing(REFUSALS[said]):
                    self.assertEqual(way(LAP), NO_VERDICT)

    def test_a_kernel_that_calls_the_files_ill_formed_is_an_input_error(self):
        finding = {"rule": "types.5", "file": "card", "item": "x", "why": "the input names no by"}
        ill = rewritten(3, verdict="ILL-FORMED", findings=[finding], cells=[])
        for path in (CIRCUIT, LAP):
            for name, way in ways(path).items():
                with self.subTest(path=path.name, way=name), refusing(ill):
                    self.assertEqual(way(path), "INPUT_ERROR")

    def test_a_kernel_that_leaves_every_cell_open_is_never_a_pass(self):
        """The kernel says UNKNOWN of a pair the Python checker passes: every cell open. The
        truss, whose proofs have no tape, reads UNKNOWN. The circuit and the lap have no
        verdict: the Python checker holds cells proved that this kernel leaves open."""
        def unknown(code, out, err):
            said = json.loads(out)
            for cell in said["cells"]:
                cell.update(state="open", reason="the kernel has no rule yet for a proof with no tape")
            said.update(verdict="UNKNOWN", waived=[])
            return 2, json.dumps(said).encode("utf-8"), err

        for path, status in ((TRUSS, "UNKNOWN"), (CIRCUIT, NO_VERDICT), (LAP, NO_VERDICT)):
            for name, way in ways(path).items():
                with self.subTest(path=path.name, way=name), refusing(unknown):
                    self.assertEqual(way(path), status)

    @unittest.skipIf(os.name == "nt", "the stand-in kernel is a shell script")
    def test_the_command_in_its_own_process_takes_the_exit_code_and_the_error_stream(self):
        """`python -m petra check` in a process of its own, with PETRA_VERIFY naming a script
        that runs the real kernel and then exits 3, or writes to its error stream."""
        with tempfile.TemporaryDirectory() as tmp:
            for stem, last in (("exits3", "exit 3"), ("panics", 'echo "PANIC at Petra.Grid" >&2\nexit $code')):
                script = Path(tmp, stem)
                script.write_text(f'#!/bin/sh\n"{verify.binary()}" "$@"\ncode=$?\n{last}\n', encoding="utf-8")
                script.chmod(script.stat().st_mode | stat.S_IXUSR)
                for path in (LAP, CIRCUIT):
                    with self.subTest(kernel=stem, path=path.name):
                        done = subprocess.run([sys.executable, "-m", "petra", "check", str(path)], cwd=ROOT, capture_output=True, text=True,
                                              env={**os.environ, "PETRA_VERIFY": str(script)}, stdin=subprocess.DEVNULL)
                        self.assertEqual((done.returncode, done.stdout), (EXIT_CODES["INTERNAL_ERROR"], ""), done.stderr)
                        self.assertIn("no verdict", done.stderr)


@KERNEL
class Decides(unittest.TestCase):
    """With the real kernel, every way in gives the kernel's own verdict and exit code."""

    def test_a_design_of_the_models_kinds_gets_the_kernels_verdict_and_never_a_pass(self):
        """The Python checker passes the truss, the circuit and the shear tab and fails the
        other truss. The kernel has no deck of rules for any of them."""
        for path in MODELS:
            its, _ = kernel_alone(path)
            self.assertIn(its, ("UNKNOWN", "FAIL"), f"petra-verify alone, on {path.name}")
            for name, way in ways(path).items():
                with self.subTest(path=path.name, way=name):
                    self.assertEqual(way(path), its)

    def test_the_exit_code_of_the_command_is_the_kernels(self):
        for path in (CIRCUIT, TAB, LAP_FAIL):
            its, _ = kernel_alone(path)
            with self.subTest(path=path.name):
                done = subprocess.run([sys.executable, "-m", "petra", "check", str(path)], cwd=ROOT, capture_output=True, stdin=subprocess.DEVNULL)
                self.assertEqual(done.returncode, {"PASS": 0, "FAIL": 1, "UNKNOWN": 2}[its])

    def test_the_report_gives_the_reason_and_no_status_of_the_python_checkers(self):
        """The truss reads UNKNOWN because no deck of rules has a truss. The report says so
        on its second line, calls what follows the working of Python's models, and gives
        neither their verdict nor their status of each claim (plan step 1.1a)."""
        code, out, _ = cli("check", str(TRUSS))
        lines = out.splitlines()
        self.assertEqual((code, lines[0]), (EXIT_CODES["UNKNOWN"], "warren-footbridge-panel: UNKNOWN"))
        self.assertEqual(lines[1], f"reason     {verify.no_deck(['truss'])}")
        self.assertTrue(any(line.startswith("path       legacy: every line below is the working of Python's models, which chose the checks and wrote the "
                                            "formulas, and it decides nothing: where it says certified") for line in lines), lines[:8])
        self.assertEqual([line for line in lines if "PASS" in line or line.startswith("entries")], [])
        report = json.loads(cli("check", str(TRUSS), "--json")[1])
        self.assertEqual((report["status"], report["kernel"]["verdict"], report["reason"]), ("UNKNOWN", "UNKNOWN", verify.no_deck(["truss"])))
        self.assertNotIn("python", report)

    def test_a_design_of_a_deck_gets_the_kernels_verdict(self):
        """PASS reads PASS_WAIVED when the kernel lists a waiver that a cell rests on, until
        the waived pass is retired (plan step 1.9)."""
        for path, status in ((LAP, "PASS_WAIVED"), (LAP_FAIL, "FAIL")):
            its, said = kernel_alone(path)
            self.assertEqual("PASS_WAIVED" if its == "PASS" and said["waived"] else its, status)
            self.assertEqual(said["cells_from"], "rules")
            for name, way in ways(path).items():
                with self.subTest(path=path.name, way=name):
                    self.assertEqual(way(path), status)

    def test_the_json_of_a_check_holds_the_kernels_answer(self):
        for path in (CIRCUIT, LAP):
            report = json.loads(cli("check", str(path), "--json")[1])
            its, said = kernel_alone(path)
            with self.subTest(path=path.name):
                self.assertEqual((report["kernel"]["verdict"], report["kernel"]["cells_from"]), (its, said["cells_from"]))


@KERNEL
class ForgedProofs(unittest.TestCase):
    """Without a deck of rules the kernel takes the cells of proofs.json as they come, so
    nothing it checks there makes a PASS."""

    def forged(self, path: Path) -> str:
        """A proofs file for the pair: its first cell proved by a tape that proves -1 <= 0,
        and every other cell written as not applicable."""
        honest = json.loads(exported(path)["proofs"])["cells"]
        trivial = {"inputs": [{"label": "dsg:x", "lo": "0", "hi": "1"}], "nodes": [["c", "-1"]], "roots": [0]}
        cells = [{"subject": c["subject"], "mechanism": c["mechanism"], "entry": c["entry"],
                  **({"state": "proved", "tape": trivial, "partition": "leaf"} if n == 0 else {"state": "not_applicable", "why": "forged"})}
                 for n, c in enumerate(honest)]
        return json.dumps({"format": "petra-proofs/0", "cells": cells})

    def test_a_forged_proofs_file_does_not_pass_a_failing_truss(self):
        verdict, said = kernel_alone(TRUSS_FAIL, self.forged(TRUSS_FAIL))
        self.assertEqual((said["cells_from"], said["counts"]["proved"], said["counts"]["open"]), ("proofs", 1, 0), "the kernel took the forged cells")
        self.assertEqual(verdict, "UNKNOWN")

    def test_no_proofs_file_passes_without_a_deck_of_rules(self):
        """The honest proofs of each shipped design of the models' kinds, and the forged ones."""
        for path in MODELS:
            for proofs in (None, self.forged(path)):
                with self.subTest(path=path.name, forged=proofs is not None):
                    verdict, said = kernel_alone(path, proofs)
                    self.assertEqual(said["cells_from"], "proofs")
                    self.assertNotEqual(verdict, "PASS")

    def test_the_kernel_still_checks_each_tape_without_a_deck_of_rules(self):
        """The verdict is closed, and the cells are still settled: the circuit's proofs all
        have tapes, and the kernel proves each."""
        verdict, said = kernel_alone(CIRCUIT)
        self.assertEqual((verdict, said["counts"]["open"], said["counts"]["refuted"]), ("UNKNOWN", 0, 0))
        self.assertGreater(said["counts"]["proved"], 0)


@KERNEL
class OutsideCheck(unittest.TestCase):
    """The ways to a status that do not go through `petra check`. Until plan step 1.1a each
    gave the Python checker's own PASS: `petra.check_file` returned its report, `petra
    envelope` exited 0 where every check it made passed, and `petra registry recall` printed
    PASS beside each design. tests/test_no_wrong_pass.py walks the corpus through the first."""

    def test_check_file_is_a_check_and_gives_the_kernels_verdict(self):
        for path, status in ((TRUSS, "UNKNOWN"), (CIRCUIT, "UNKNOWN"), (LAP, "PASS_WAIVED"), (LAP_FAIL, "FAIL")):
            with self.subTest(path=path.name):
                checked = petra.check_file(path)
                self.assertEqual((checked.status, checked.to_json()["status"]), (status, status))
                self.assertEqual(checked.reason is not None, path in MODELS, "the reason is that the kind has no deck of rules")
        with no_kernel(), self.assertRaises(verify.NoKernel):
            petra.check_file(LAP)

    def test_an_envelope_is_no_pass(self):
        """Every check the Python checker makes over 20 to 30 degC passes. That is its
        working: the circuit has no deck of rules, so the status is UNKNOWN and the exit code 2."""
        argv = ("envelope", str(CIRCUIT), "--input", "ambient", "--from", "20 degC", "--to", "30 degC", "--max-probes", "4")
        code, out, _ = cli(*argv)
        lines = out.splitlines()
        self.assertEqual((code, lines[0], lines[1]), (EXIT_CODES["UNKNOWN"], "workshop-lighting-radial: UNKNOWN", f"reason     {verify.no_deck(['circuit'])}"))
        self.assertIn("decides nothing", lines[2])
        code, out, _ = cli(*argv, "--json")
        found = json.loads(out)
        self.assertEqual((code, found["status"], found["reason"]), (EXIT_CODES["UNKNOWN"], "UNKNOWN", verify.no_deck(["circuit"])))

    def test_a_recall_prints_no_pass(self):
        code, out, _ = cli("registry", "recall", "cable.cu_pvc", str(CIRCUIT))
        self.assertEqual(code, 0)
        rows = [line.split() for line in out.splitlines() if "circuit_pass.petra" in line or line.startswith("  hot") or line.startswith("  drop")]
        self.assertEqual([row[0] if "circuit_pass.petra" in " ".join(row) else row[1] for row in rows], ["UNKNOWN"] * len(rows), out)
        self.assertGreaterEqual(len(rows), 3)
        self.assertNotIn("PASS", out)
        found = json.loads(cli("registry", "recall", "cable.cu_pvc", str(CIRCUIT), "--json")[1])
        self.assertEqual({d["status"] for d in found["designs"]} | {v["status"] for d in found["designs"] for v in d["verdicts"]}, {"UNKNOWN"})


if __name__ == "__main__":
    unittest.main()
