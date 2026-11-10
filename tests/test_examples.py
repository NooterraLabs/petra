"""The shipped examples, end to end through `python -m petra`. Owner: Y.

Expected statuses come from each example's own header: circuit_pass proves both claims
and every coverage demand; bolt_unknown proves its tension claim but has no model and
no waiver for galvanic corrosion or plate bearing; the cu_pvc family proves both claims
over its box, but a family names no breaker or terminal, so its coverage demands stay
open. `petra check` refuses a family, whose card leaves its load to a param, so the
family's report comes from check_design. Truss and hook examples join once their
elaborators land.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from petra.lang import load_design
from petra.pipeline import check_design
from petra.registry import build_registry
from petra.solvers import SolverSource

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "examples/circuit_pass.petra": ("PASS", 0),
    "examples/bolt_unknown.petra": ("UNKNOWN", 2),
}
FAMILY = "examples/families/cu_pvc_clipped.petra"


def petra(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "petra", *argv], cwd=ROOT, capture_output=True, text=True, timeout=600)


class Examples(unittest.TestCase):
    def assertReport(self, report: dict, path: str, status: str):
        self.assertEqual(report["status"], status, f"{path} is {status}")
        self.assertEqual(report["file"], path, "the report names the file")
        for verdict in report["verdicts"]:
            self.assertTrue(verdict["footprint"], f"{path} {verdict['claim']} names its premises")
            if verdict["status"] == "PASS":
                self.assertTrue(verdict["rules"], f"{path} {verdict['claim']} names the rules its proof used")
            self.assertEqual(bool(verdict["needs"]), verdict["status"] == "UNKNOWN", f"{path} {verdict['claim']} lists needs only when open")
            self.assertTrue(verdict["obligations"], f"{path} {verdict['claim']} lists its obligations")

    def test_each_example_gets_its_expected_verdict(self):
        for path, (status, code) in EXPECTED.items():
            with self.subTest(path=path):
                done = petra("check", path, "--json")
                self.assertEqual(done.returncode, code, f"{path} exits {code}: {done.stderr}")
                self.assertReport(json.loads(done.stdout), path, status)

    def test_check_refuses_the_family_and_check_design_leaves_its_coverage_open(self):
        done = petra("check", FAMILY, "--json")
        self.assertEqual(done.returncode, 3, f"{FAMILY} is an input error to `petra check`: {done.stdout}")
        self.assertIn("certify-family", done.stderr)
        registry = build_registry()
        report = check_design(load_design(ROOT / FAMILY, registry), registry, (SolverSource(),), path=FAMILY)
        self.assertReport(report.to_json(), FAMILY, "UNKNOWN")

    def test_a_design_inside_the_family_reuses_it_without_solving(self):
        with tempfile.TemporaryDirectory() as library:
            stored = petra("certify-family", "examples/families/cu_pvc_clipped.petra", "--library", library)
            self.assertEqual(stored.returncode, 0, f"the family certifies: {stored.stdout}{stored.stderr}")
            done = petra("check", "examples/circuit_pass.petra", "--json", "--library", library, "--no-solve")
        verdicts = {v["claim"]: v for v in json.loads(done.stdout)["verdicts"]}
        for claim in ("hot", "drop"):
            self.assertEqual(verdicts[claim]["status"], "PASS", f"{claim} passes from the library alone")
            self.assertTrue(verdicts[claim]["footprint"], f"{claim} keeps its footprint")
        self.assertEqual(verdicts["coverage"]["status"], "UNKNOWN", "coverage is not in the family, and the run solved nothing")


if __name__ == "__main__":
    unittest.main()
