"""The command line: exit codes, the JSON report, and each subcommand.

The status and the exit code of `petra check` are the kernel's (tests/test_kernel_decides.py).
The three laps of examples/deck are checked against the AISC deck: lap_pass passes on the
waivers of its card, lap_unknown has five lines the deck has no rule for, and lap_fail carries
a pull its bolts do not. A truss is a kind no deck has, so it reads UNKNOWN with that reason.
"""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import petra
from petra import verify
from petra.cli import EXIT_CODES, build_parser, main
from petra.files import read_pair

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
OLD = Path(__file__).resolve().parents[1] / "corpus" / "cases" / "old"
"""Designs of kinds no deck has, which read UNKNOWN: the examples of the old path, kept as cases."""
LAP = EXAMPLES / "deck" / "lap_pass.petra"
TRUSS = OLD / "truss_pass.petra"
DECK_KEYS = {"file", "design", "status", "deck", "counts", "cells", "waived", "card", "hashes", "path", "kernel"}
CELL_KEYS = {"subject", "mechanism", "entry", "state", "what", "anchor", "why", "rule", "ratio"}


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class Workspace(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def write(self, name: str, text: str) -> str:
        path = self.tmp / name
        path.write_text(text, encoding="utf-8", newline="\n")
        return str(path)


class Check(Workspace):
    def test_a_lap_that_passes_on_waivers_exits_6_with_the_json_report(self):
        code, out, _ = run("check", str(LAP), "--json")
        self.assertEqual(code, EXIT_CODES["PASS_WAIVED"], "lap_pass exits 6: the kernel says PASS and lists the waivers its cells rest on")
        report = json.loads(out)
        self.assertEqual(set(report), DECK_KEYS, "the report has the documented keys")
        self.assertEqual((report["status"], report["kernel"]["verdict"], report["path"]), ("PASS_WAIVED", "PASS", "rules"))
        self.assertEqual(report["file"], str(LAP), "the file is named as given")
        self.assertEqual(len(report["waived"]), 5, "each of the five waivers is listed")
        for cell in report["cells"]:
            self.assertLessEqual(CELL_KEYS, set(cell), f"{cell['mechanism']} has the documented keys")
        self.assertEqual(sum(report["counts"].values()), len(report["cells"]), "the counts are of the cells")

    def test_a_lap_with_open_lines_exits_2_and_names_them(self):
        code, out, _ = run("check", str(EXAMPLES / "deck" / "lap_unknown.petra"), "--json")
        self.assertEqual(code, EXIT_CODES["UNKNOWN"], "lap_unknown exits 2")
        pending = [c for c in json.loads(out)["cells"] if c["state"] == "open"]
        self.assertEqual(len(pending), 5, "the five lines the deck has no rule for")
        self.assertTrue(all(c["why"] for c in pending), "and each says why it is open")

    def test_a_lap_that_is_refuted_exits_1(self):
        code, out, _ = run("check", str(EXAMPLES / "deck" / "lap_fail.petra"))
        self.assertEqual(code, EXIT_CODES["FAIL"], "lap_fail exits 1")
        self.assertIn("FAIL", out.splitlines()[0], "the first line gives the status")
        self.assertIn("refuted", out)

    def test_a_design_of_a_kind_no_deck_has_exits_2_with_the_reason(self):
        code, out, _ = run("check", str(TRUSS), "--json")
        self.assertEqual(code, EXIT_CODES["UNKNOWN"], "a truss exits 2: no deck of rules has one")
        report = json.loads(out)
        self.assertEqual((report["status"], report["reason"], report["kinds"]), ("UNKNOWN", verify.no_deck(["truss"]), ["truss"]))
        self.assertEqual((report["cells"], report["deck"], report["kernel"], report["path"]), ([], None, None, "none"), "and no cell was worked out")
        code, out, _ = run("check", str(TRUSS))
        self.assertEqual(code, EXIT_CODES["UNKNOWN"])
        self.assertEqual(out.splitlines()[1], f"reason     {verify.no_deck(['truss'])}", "the text gives the reason on its second line")

    def test_input_errors_exit_3_and_print_nothing(self):
        card, design = read_pair(LAP)
        self.write("broken.card", card)
        syntax = self.write("broken.petra", "petra 0\nlap {\n")
        lone = self.write("lone.petra", design)
        for argv in (("check", syntax), ("check", str(self.tmp / "missing.petra")), ("check", lone), ("check", str(LAP), "--card", syntax)):
            code, out, err = run(*argv)
            self.assertEqual(code, EXIT_CODES["INPUT_ERROR"], f"{argv} exits 3")
            self.assertEqual(out, "", f"{argv} prints nothing to stdout")
            self.assertTrue(err, f"{argv} explains itself on stderr")
        self.assertIn("broken.petra:2:1", run("check", syntax)[2], "a syntax error names the design and the place")
        self.assertIn("lone.card", run("check", lone)[2], "a design with no card beside it names the card it looked for")

    def test_a_design_cannot_state_what_is_asked_of_it(self):
        card, design = read_pair(LAP)
        self.write("own.card", card)
        for line in ("load easy {\n  on splice pull in [0 kip, 1 kip]\n  signed \"me\" source \"me\"\n}\n",
                     "claim hot: splice.temperature <= 500 degC\n",
                     "waive lap.tightening on splice by \"me\" reason \"fine\"\n"):
            code, out, err = run("check", self.write("own.petra", design + line))
            self.assertEqual((code, out), (EXIT_CODES["INPUT_ERROR"], ""), line)
            self.assertIn("belongs in the card", err, line)

    def test_a_part_of_a_deck_beside_one_of_no_deck_is_refused(self):
        card, design = read_pair(LAP)
        self.write("mixed.card", card)
        code, out, err = run("check", self.write("mixed.petra", design + "\ntruss frame {\n  node a at (0 m, 0 m)\n}\n"))
        self.assertEqual((code, out), (EXIT_CODES["INPUT_ERROR"], ""))
        self.assertIn("frame", err, "the part of no deck is named")
        many = design + "".join(f"\ntruss f{i} {{\n}}\n" for i in range(40))
        code, out, err = run("check", self.write("mixed.petra", many))
        self.assertEqual((code, out), (EXIT_CODES["INPUT_ERROR"], ""))
        self.assertIn("and 36 more", err, "four of the parts of no deck are named, and the rest counted")

    def test_a_design_with_no_part_reads_unknown_and_says_so(self):
        card, _ = read_pair(TRUSS)
        self.write("empty.card", 'petra 0\n\ncard "nothing" {\n  owner "me"\n}\n')
        code, out, _ = run("check", self.write("empty.petra", "petra 0\n"))
        self.assertEqual(code, EXIT_CODES["UNKNOWN"])
        self.assertEqual(out.splitlines()[1], "reason     the design has no part, so there is no check to work out and nothing can pass it")

    def test_usage_errors_exit_3(self):
        for argv in (("frobnicate",), ("check",), ("mcp", "--budget", "0"), ("check", str(LAP), "--no-solve"), ("envelope", str(LAP)),
                     ("verify", "x.json"), ("certify-family", str(LAP)), ("registry", "list"), ("explain", str(LAP))):
            self.assertEqual(run(*argv)[0], EXIT_CODES["INPUT_ERROR"], f"{argv} exits 3")

    def test_the_commands_are_the_ones_the_kernel_or_the_decks_serve(self):
        """Nothing that the old Python checker served is a command: each was a way to a status that was not the kernel's."""
        actions = [a for a in build_parser()._actions if a.dest == "command"]
        self.assertEqual(sorted(actions[0].choices), ["check", "docs", "kinds", "mcp", "new"])

    def test_python_dash_m_petra_uses_the_same_exit_codes(self):
        done = subprocess.run([sys.executable, "-m", "petra", "check", str(EXAMPLES / "deck" / "lap_unknown.petra"), "--json"],
                              cwd=ROOT, capture_output=True, text=True, timeout=300)
        self.assertEqual(done.returncode, EXIT_CODES["UNKNOWN"], "python -m petra exits with the verdict's code")
        self.assertEqual(json.loads(done.stdout)["status"], "UNKNOWN", "and prints the report")

    def test_a_reader_that_closes_stdout_early_stops_the_output_without_a_traceback(self):
        # As `petra check FILE | head` does once it has its lines. Every subcommand, not only check.
        for argv in (("check", str(LAP)), ("docs", "reference")):
            proc = subprocess.Popen([sys.executable, "-m", "petra", *argv], cwd=ROOT, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            proc.stdout.close()
            err = proc.stderr.read().decode("utf-8", "replace")
            proc.stderr.close()
            self.assertEqual(proc.wait(timeout=300), EXIT_CODES["BROKEN_PIPE"], f"{argv} exits 141, not 4")
            self.assertEqual(err, "", f"{argv} prints no traceback")


class Encodings(Workspace):
    """Windows PowerShell 5.1 writes UTF-8 with a byte order mark from `Out-File -Encoding
    utf8` and UTF-16 from `>`. The README's quickstart redirects `petra new` into a file."""

    CARD, TEXT = read_pair(LAP)

    def check(self, card: bytes, design: bytes) -> int:
        (self.tmp / "design.card").write_bytes(card)
        path = self.tmp / "design.petra"
        path.write_bytes(design)
        return run("check", str(path))[0]

    def test_a_pair_with_a_byte_order_mark_checks(self):
        self.assertEqual(self.check(self.CARD.encode("utf-8-sig"), self.TEXT.encode("utf-8-sig")), EXIT_CODES["PASS_WAIVED"])

    def test_a_utf16_pair_checks(self):
        self.assertEqual(self.check(*(text.replace("\n", "\r\n").encode("utf-16") for text in (self.CARD, self.TEXT))), EXIT_CODES["PASS_WAIVED"])

    def test_bytes_that_are_not_text_are_an_input_error(self):
        self.assertEqual(self.check(self.CARD.encode("utf-8"), b"petra 0\n\xff\xfe\xfd"), EXIT_CODES["INPUT_ERROR"])
        self.assertEqual(self.check(b"petra 0\n\xff\xfe\xfd", self.TEXT.encode("utf-8")), EXIT_CODES["INPUT_ERROR"])


class Version(unittest.TestCase):
    def test_version_prints_the_version_and_exits_0(self):
        code, out, _ = run("--version")
        self.assertEqual((code, out.strip()), (0, f"petra {petra.__version__}"))


class Teach(Workspace):
    def test_kinds_lists_the_decks_and_prints_a_type(self):
        code, out, _ = run("kinds")
        self.assertEqual(code, 0)
        self.assertIn("deck aisc360-22: plate, lap", out)
        code, out, _ = run("kinds", "lap")
        self.assertEqual(code, 0)
        self.assertIn("lap.block_shear", out, "a type prints what the grid asks of it")
        self.assertEqual(json.loads(run("kinds", "lap", "--json")[1])["decks"][0]["types"][0]["type"], "lap")
        self.assertEqual(run("kinds", "truss")[0], EXIT_CODES["INPUT_ERROR"], "a kind no deck has is no type")
        self.assertEqual(run("kinds", "lap", "--all")[0], EXIT_CODES["INPUT_ERROR"])

    def test_new_prints_a_pair_that_checks(self):
        code, card, _ = run("new", "lap", "--card")
        self.assertEqual(code, 0)
        code, design, _ = run("new", "lap", "--name", "joint")
        self.assertEqual(code, 0)
        self.write("lap.card", card.replace(" on splice ", " on joint "))
        self.assertEqual(run("check", self.write("lap.petra", design))[0], EXIT_CODES["UNKNOWN"], "the card signs no waiver, so five lines are open")
        self.assertEqual(run("new", "truss")[0], EXIT_CODES["INPUT_ERROR"])

    def test_docs_lists_and_prints(self):
        code, out, _ = run("docs")
        self.assertEqual(code, 0)
        self.assertEqual([line.split()[0] for line in out.splitlines()[:-1]], ["readme", "reference", "api", "skill"])
        self.assertEqual(run("docs", "api")[0], 0)
        self.assertEqual(run("docs", "nothing")[0], EXIT_CODES["INPUT_ERROR"])


if __name__ == "__main__":
    unittest.main()
