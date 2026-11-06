"""The command line: exit codes, the JSON report, and each subcommand. Owner: Y.

Expected verdicts: examples/circuit_pass.petra passes and examples/bolt_unknown.petra is
UNKNOWN (their own headers say why). With a 16 A draw the circuit_pass design breaks
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

from petra.cli import EXIT_CODES, main
from petra.gym.tasks import generate
from petra.kernel import Evidence, Leaf, Split, encode_evidence
from petra.kernel.rules.r4_enclosure import Enclosure
from petra.registry import build_registry

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
CIRCUIT = EXAMPLES / "circuit_pass.petra"
FAMILY = EXAMPLES / "families" / "cu_pvc_clipped.petra"
VERDICT_KEYS = {"claim", "status", "footprint", "rules", "obligations", "margins"}


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
        self.assertEqual(set(report), {"file", "design", "status", "verdicts"}, "the report has the documented keys")
        self.assertEqual(report["file"], str(CIRCUIT), "the file is named as given")
        for verdict in report["verdicts"]:
            self.assertEqual(set(verdict), VERDICT_KEYS, f"{verdict['claim']} has the documented keys")
            self.assertEqual(verdict["status"], "PASS", f"{verdict['claim']} passes")
            self.assertTrue(verdict["footprint"], f"{verdict['claim']} names its premises")
            self.assertEqual(verdict["obligations"], [], f"{verdict['claim']} has nothing open")

    def test_an_unknown_design_exits_2_and_names_what_is_open(self):
        code, out, _ = run("check", str(EXAMPLES / "bolt_unknown.petra"), "--json")
        self.assertEqual(code, EXIT_CODES["UNKNOWN"], "bolt_unknown exits 2")
        unknown = [v for v in json.loads(out)["verdicts"] if v["status"] == "UNKNOWN"]
        self.assertTrue(unknown, "some entry is UNKNOWN")
        self.assertTrue(all(v["obligations"] for v in unknown), "each UNKNOWN entry says what it needs")

    def test_a_refuted_design_exits_1(self):
        path = self.write("overloaded.petra", CIRCUIT.read_text(encoding="utf-8").replace("[0 A, 10 A]", "[0 A, 16 A]"))
        code, out, _ = run("check", path)
        self.assertEqual(code, EXIT_CODES["FAIL"], "16 A on a B10 exits 1")
        self.assertIn("FAIL", out.splitlines()[0], "the first line gives the overall status")

    def test_input_errors_exit_3_and_print_nothing(self):
        syntax = self.write("broken.petra", "petra 0\ndesign {\n")
        deck = self.write("deck.json", "not a deck")
        for argv in (("check", syntax), ("check", str(self.tmp / "missing.petra")), ("check", str(CIRCUIT), "--deck", deck)):
            code, out, err = run(*argv)
            self.assertEqual(code, EXIT_CODES["INPUT_ERROR"], f"{argv} exits 3")
            self.assertEqual(out, "", f"{argv} prints nothing to stdout")
            self.assertTrue(err, f"{argv} explains itself on stderr")

    def test_usage_errors_exit_3(self):
        for argv in (("frobnicate",), ("check",), ("gym", "--episodes", "1", "--seed", "0", "--domain", "hydraulics")):
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


class Explain(Workspace):
    def test_explain_prints_the_statements(self):
        code, out, _ = run("explain", str(EXAMPLES / "bolt_unknown.petra"))
        self.assertEqual(code, 0, "explain exits 0")
        self.assertIn("obligation", out, "it lists the obligations")

    def test_explain_refuses_a_broken_file(self):
        self.assertEqual(run("explain", self.write("broken.petra", "petra 0\ndesign {\n"))[0], EXIT_CODES["INPUT_ERROR"], "a syntax error exits 3")


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
        path = self.write("too_hot.petra", FAMILY.read_text(encoding="utf-8").replace("[0 A, 13 A]", "[0 A, 16 A]"))
        code, out, _ = run("certify-family", path, "--library", str(self.tmp / "library"))
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


class Gym(Workspace):
    def test_gym_prints_the_summary_line(self):
        registry = build_registry()
        given = (dict(generate("circuit", s, registry).given) for s in range(500))
        seed = next(s for s, g in enumerate(given) if int(g["current"]) <= 10 and int(g["length"]) <= 18)
        code, out, _ = run("gym", "--episodes", "1", "--seed", str(seed), "--domain", "circuit", "--library", str(self.tmp / "library"))
        self.assertEqual(code, 0, "gym exits 0")
        self.assertRegex(out.strip(), r"^solved 1/1 episodes \(library hits \d+, families added [1-9]\d*\)$",
                         "a task within circuit_pass's limits is solved and stored")


if __name__ == "__main__":
    unittest.main()
