"""Calculation packages (docs/steel_connections.md §9 item 9): every connection's package
re-checks with `petra verify` and with `petra check --certs --no-solve`, without trusting the
report."""
import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from petra import cli
from petra.lang import parse_design
from petra.models.steel import calc
from petra.models.steel import generate as gen
from petra.models.steel.domain import required
from petra.models.steel.package import recheck, write_package
from petra.registry import build_registry

REGISTRY = build_registry()
STREAM = list(gen.generate(33, 9, REGISTRY))


def pick(predicate):
    return next(g for g in STREAM if predicate(g))


class Packages(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="steel-package-test-"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def package(self, g):
        return write_package(g.card, g.text, self.root / g.name, REGISTRY)

    def test_passing_failing_and_toleranced_designs_recheck(self):
        for g in (pick(lambda g: g.expected == "PASS" and not g.toleranced), pick(lambda g: g.expected == "FAIL"),
                  pick(lambda g: g.toleranced)):
            with self.subTest(g.name):
                pkg = self.package(g)
                self.assertEqual(pkg.status, g.expected)
                again = recheck(pkg, REGISTRY)
                self.assertTrue(again.holds(pkg.status), again)
                self.assertGreaterEqual(again.certificates, len(pkg.hashes))

    def test_the_report_covers_every_required_mode_and_cites_its_statement(self):
        g = pick(lambda g: g.kind == "shear_tab" and g.expected == "PASS")
        pkg = self.package(g)
        text = (pkg.root / "report.md").read_text(encoding="utf-8")
        d = parse_design(g.card, g.text, "t.petra", REGISTRY)
        for mode in required(calc.connection(d, "c1", REGISTRY), d):
            self.assertIn(f"### {mode}: holds", text)
        for h in pkg.hashes:
            self.assertIn(h, text)
        self.assertIn("**PASS**", text)
        self.assertEqual(pkg.report.design, g.name)

    def test_a_fail_reports_its_witness(self):
        pkg = self.package(pick(lambda g: g.expected == "FAIL"))
        text = (pkg.root / "report.md").read_text(encoding="utf-8")
        self.assertIn("FAILS", text)
        self.assertIn("Witness (SI units):", text)

    def test_petra_verify_accepts_every_certificate(self):
        pkg = self.package(pick(lambda g: g.kind == "hanger"))
        files = [str(p) for p in sorted((pkg.root / "certs").glob("*.json"))]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["verify", *files])
        self.assertEqual(code, 0, out.getvalue())
        self.assertEqual(len(out.getvalue().splitlines()), len(files))

    def test_petra_check_from_the_certificates_alone_reproduces_the_verdict(self):
        g = pick(lambda g: g.kind == "bolt_bracket")
        pkg = self.package(g)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["check", "--certs", str(pkg.root / "certs"), "--no-solve", str(pkg.root / "design.petra")])
        self.assertIn(f"{g.name}: {pkg.status}", out.getvalue())

    def test_a_tampered_certificate_is_caught(self):
        pkg = self.package(pick(lambda g: g.kind == "shear_end_plate" and g.expected == "PASS"))
        victim = sorted((pkg.root / "certs").glob("*.json"))[0]
        victim.unlink()
        again = recheck(pkg, REGISTRY)
        self.assertTrue(again.missing)
        self.assertNotEqual(again.status, "PASS")


if __name__ == "__main__":
    unittest.main()
