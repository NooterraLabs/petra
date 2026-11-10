"""The command line: exit codes, the JSON report, and each subcommand. Owner: Y.

Expected verdicts: examples/circuit_pass.petra passes and examples/bolt_unknown.petra is
UNKNOWN (their own headers say why). Under a card that asks for a 16 A draw the circuit_pass design breaks
the overload condition I_B <= I_n of its B10 breaker (IEC 60364-4-43 433.1), so it
fails. A stress area of 1.5 x 84.267 mm2 for M12 contradicts ISO 724, so a deck holding
it fails the consistency check.
"""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

import petra
from petra.cli import EXIT_CODES, main
from petra.files import read_pair
from petra.kernel import Evidence, Leaf, Split, encode_evidence
from petra.kernel.rules.r4_enclosure import Enclosure

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
CIRCUIT = EXAMPLES / "circuit_pass.petra"
FAMILY = EXAMPLES / "families" / "cu_pvc_clipped.petra"
VERDICT_KEYS = {"claim", "status", "footprint", "rules", "needs", "margins", "obligations"}


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
    def test_a_passing_design_exits_0_with_the_json_report(self):
        code, out, _ = run("check", str(CIRCUIT), "--json")
        self.assertEqual(code, EXIT_CODES["PASS"], "circuit_pass exits 0")
        report = json.loads(out)
        self.assertEqual(set(report), {"file", "design", "status", "governing", "verdicts", "unchecked", "repair"}, "the report has the documented keys")
        self.assertEqual(report["file"], str(CIRCUIT), "the file is named as given")
        for verdict in report["verdicts"]:
            self.assertEqual(set(verdict), VERDICT_KEYS, f"{verdict['claim']} has the documented keys")
            self.assertEqual(verdict["status"], "PASS", f"{verdict['claim']} passes")
            self.assertTrue(verdict["footprint"], f"{verdict['claim']} names its premises")
            self.assertEqual(verdict["needs"], [], f"{verdict['claim']} has nothing open")
            self.assertTrue(verdict["obligations"], f"{verdict['claim']} lists its obligations")
            self.assertEqual({o["outcome"] for o in verdict["obligations"]}, {"certified"}, f"{verdict['claim']} certifies each")

    def test_an_unknown_design_exits_2_and_names_what_is_open(self):
        code, out, _ = run("check", str(EXAMPLES / "bolt_unknown.petra"), "--json")
        self.assertEqual(code, EXIT_CODES["UNKNOWN"], "bolt_unknown exits 2")
        unknown = [v for v in json.loads(out)["verdicts"] if v["status"] == "UNKNOWN"]
        self.assertTrue(unknown, "some entry is UNKNOWN")
        self.assertTrue(all(v["needs"] for v in unknown), "each UNKNOWN entry says what it needs")

    def test_a_design_refuted_under_another_card_exits_1(self):
        card = self.write("overloaded.card", read_pair(CIRCUIT)[0].replace("[0 A, 10 A]", "[0 A, 16 A]"))
        code, out, _ = run("check", str(CIRCUIT), "--card", card)
        self.assertEqual(code, EXIT_CODES["FAIL"], "16 A on a B10 exits 1")
        self.assertIn("FAIL", out.splitlines()[0], "the first line gives the overall status")

    def test_input_errors_exit_3_and_print_nothing(self):
        card, design = read_pair(CIRCUIT)
        self.write("broken.card", card)
        syntax = self.write("broken.petra", "petra 0\ncircuit {\n")
        lone = self.write("lone.petra", design)
        deck = self.write("deck.json", "not a deck")
        for argv in (("check", syntax), ("check", str(self.tmp / "missing.petra")), ("check", lone), ("check", str(CIRCUIT), "--card", syntax),
                     ("check", str(CIRCUIT), "--deck", deck)):
            code, out, err = run(*argv)
            self.assertEqual(code, EXIT_CODES["INPUT_ERROR"], f"{argv} exits 3")
            self.assertEqual(out, "", f"{argv} prints nothing to stdout")
            self.assertTrue(err, f"{argv} explains itself on stderr")
        self.assertIn("broken.petra:2:1", run("check", syntax)[2], "a syntax error names the design and the place")
        self.assertIn("lone.card", run("check", lone)[2], "a design with no card beside it names the card it looked for")

    def test_a_design_cannot_state_what_is_asked_of_it(self):
        card, design = read_pair(CIRCUIT)
        self.write("own.card", card)
        for line in ("load easy {\n  on lighting.lamps current in [0 A, 1 A]\n  signed \"me\" source \"me\"\n}\n",
                     "claim hot: lighting.w1.temperature <= 500 degC\n",
                     "waive wire.short_circuit on lighting.w1 by \"me\" reason \"fine\"\n"):
            code, out, err = run("check", self.write("own.petra", design + line))
            self.assertEqual((code, out), (EXIT_CODES["INPUT_ERROR"], ""), line)
            self.assertIn("belongs in the card", err, line)

    def test_a_family_is_not_a_design_to_check(self):
        code, _, err = run("check", str(FAMILY))
        self.assertEqual(code, EXIT_CODES["INPUT_ERROR"], "a load that reads a param is one nobody signed")
        self.assertIn("certify-family", err)

    def test_usage_errors_exit_3(self):
        for argv in (("frobnicate",), ("check",), ("mcp", "--budget", "0")):
            self.assertEqual(run(*argv)[0], EXIT_CODES["INPUT_ERROR"], f"{argv} exits 3")

    def test_check_without_solvers_reuses_the_library(self):
        library = str(self.tmp / "library")
        self.assertEqual(run("certify-family", str(FAMILY), "--library", library)[0], 0, "the family certifies")
        code, out, _ = run("check", str(CIRCUIT), "--json", "--library", library, "--no-solve")
        statuses = {v["claim"]: v["status"] for v in json.loads(out)["verdicts"]}
        self.assertEqual((statuses["hot"], statuses["drop"]), ("PASS", "PASS"), "both claims come from the library")
        self.assertEqual(statuses["coverage"], "UNKNOWN", "coverage needs the solver the run switched off")
        self.assertEqual(code, EXIT_CODES["UNKNOWN"], "so the design exits 2")

    def test_python_dash_m_petra_uses_the_same_exit_codes(self):
        done = subprocess.run([sys.executable, "-m", "petra", "check", str(EXAMPLES / "bolt_unknown.petra"), "--json"],
                              cwd=ROOT, capture_output=True, text=True, timeout=300)
        self.assertEqual(done.returncode, EXIT_CODES["UNKNOWN"], "python -m petra exits with the verdict's code")
        self.assertEqual(json.loads(done.stdout)["status"], "UNKNOWN", "and prints the report")

    def test_a_reader_that_closes_stdout_early_stops_the_output_without_a_traceback(self):
        # As `petra check FILE | head` does once it has its lines. Every subcommand, not only check.
        for argv in (("check", str(CIRCUIT)), ("docs", "reference")):
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

    CARD, TEXT = read_pair(ROOT / "examples" / "circuit_pass.petra")

    def check(self, card: bytes, design: bytes) -> int:
        (self.tmp / "design.card").write_bytes(card)
        path = self.tmp / "design.petra"
        path.write_bytes(design)
        return run("check", str(path))[0]

    def test_a_pair_with_a_byte_order_mark_checks(self):
        self.assertEqual(self.check(self.CARD.encode("utf-8-sig"), self.TEXT.encode("utf-8-sig")), EXIT_CODES["PASS"])

    def test_a_utf16_pair_checks(self):
        self.assertEqual(self.check(*(text.replace("\n", "\r\n").encode("utf-16") for text in (self.CARD, self.TEXT))), EXIT_CODES["PASS"])

    def test_bytes_that_are_not_text_are_an_input_error(self):
        self.assertEqual(self.check(self.CARD.encode("utf-8"), b"petra 0\n\xff\xfe\xfd"), EXIT_CODES["INPUT_ERROR"])
        self.assertEqual(self.check(b"petra 0\n\xff\xfe\xfd", self.TEXT.encode("utf-8")), EXIT_CODES["INPUT_ERROR"])


class Version(unittest.TestCase):
    def test_version_prints_the_version_and_exits_0(self):
        code, out, _ = run("--version")
        self.assertEqual((code, out.strip()), (0, f"petra {petra.__version__}"))


class Explain(Workspace):
    def test_explain_prints_the_statements(self):
        code, out, _ = run("explain", str(EXAMPLES / "bolt_unknown.petra"))
        self.assertEqual(code, 0, "explain exits 0")
        self.assertIn("obligation", out, "it lists the obligations")

    def test_explain_refuses_a_broken_file(self):
        self.write("broken.card", read_pair(CIRCUIT)[0])
        self.assertEqual(run("explain", self.write("broken.petra", "petra 0\ncircuit {\n"))[0], EXIT_CODES["INPUT_ERROR"], "a syntax error exits 3")


class Verify(Workspace):
    def certificates(self) -> list[Path]:
        certs = self.tmp / "certs"
        run("check", str(CIRCUIT), "--certs", str(certs))
        return sorted(certs.glob("*.json"))

    def test_certificates_written_by_check_verify(self):
        paths = self.certificates()
        self.assertTrue(paths, "check wrote certificates")
        code, out, _ = run("verify", *map(str, paths))
        self.assertEqual(code, 0, "every certificate checks")
        self.assertEqual(out.count(": theorem "), len(paths), "one theorem line per file")

    def test_library_files_verify(self):
        library = self.tmp / "library"
        run("certify-family", str(FAMILY), "--library", str(library))
        paths = sorted(library.rglob("*.json"))
        self.assertEqual(len(paths), 2, "two library files")
        self.assertEqual(run("verify", *map(str, paths))[0], 0, "library files verify like certificates")

    def test_forged_evidence_exits_1(self):
        path = self.certificates()[0]
        cert = json.loads(path.read_text(encoding="utf-8"))
        sym = next(h["sym"] for h in cert["statement"]["hyps"] if h["t"] == "range_hyp")
        cert["evidence"] = encode_evidence(Evidence(Enclosure(Split(sym, Fraction(10**9), Leaf(), Leaf()))))
        code, out, _ = run("verify", self.write("forged.json", json.dumps(cert)))
        self.assertEqual(code, 1, "the kernel rejects a split outside the cell")
        self.assertIn("REJECTED", out, "and says so")

    def test_an_edited_statement_exits_3(self):
        path = self.certificates()[0]
        cert = json.loads(path.read_text(encoding="utf-8"))
        cert["statement"]["hyps"] = cert["statement"]["hyps"][1:]
        self.assertEqual(run("verify", self.write("edited.json", json.dumps(cert)))[0], EXIT_CODES["INPUT_ERROR"], "a statement that does not match its hash does not decode")


class CertifyFamily(Workspace):
    def test_the_family_stores_both_claims(self):
        code, out, _ = run("certify-family", str(FAMILY), "--library", str(self.tmp / "library"))
        self.assertEqual(code, 0, "every claim is stored")
        self.assertEqual(out.count("stored "), 2, "one line per stored claim")

    def test_a_false_family_exits_1(self):
        card = self.write("too_hot.card", read_pair(FAMILY)[0].replace("[0 A, 13 A]", "[0 A, 16 A]"))
        code, out, _ = run("certify-family", str(FAMILY), "--card", card, "--library", str(self.tmp / "library"))
        self.assertEqual(code, EXIT_CODES["FAIL"], "the hot claim is refuted at 16 A")
        self.assertIn("skipped", out, "the refuted claim is listed")

    def test_a_concrete_design_exits_3(self):
        self.assertEqual(run("certify-family", str(CIRCUIT), "--library", str(self.tmp / "library"))[0], EXIT_CODES["INPUT_ERROR"], "a design with no param is not a family")


class Registry(Workspace):
    def test_the_shipped_registry_is_consistent(self):
        code, out, _ = run("registry", "check")
        self.assertEqual(code, 0, "the shipped deck breaks no relation")
        self.assertIn("0 findings", out, "and says so")

    def test_a_built_deck_round_trips(self):
        deck = str(self.tmp / "deck.json")
        self.assertEqual(run("registry", "build", "--out", deck)[0], 0, "build exits 0")
        self.assertEqual(run("registry", "check", deck)[0], 0, "the written deck is consistent")

    def test_a_wrong_stress_area_exits_1(self):
        deck = self.tmp / "deck.json"
        run("registry", "build", "--out", str(deck))
        body = json.loads(deck.read_text(encoding="utf-8"))
        record = next(r for r in body["records"] if (r["entry"], r["prop"]) == ("bolt.M12_A4_70", "As"))
        record["lo"], record["hi"] = (str(Fraction(record[k]) * Fraction(3, 2)) for k in ("lo", "hi"))
        deck.write_text(json.dumps(body), encoding="utf-8", newline="\n")
        code, out, _ = run("registry", "check", str(deck))
        self.assertEqual(code, 1, "a deck that contradicts ISO 724 exits 1")
        self.assertIn("bolt.M12_A4_70", out, "the finding names the entry")

    def test_an_unreadable_deck_exits_3(self):
        self.assertEqual(run("registry", "check", self.write("deck.json", "{"))[0], EXIT_CODES["INPUT_ERROR"], "a deck that does not parse exits 3")


if __name__ == "__main__":
    unittest.main()
