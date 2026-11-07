"""What a FAIL tells a stranger (petra/readout.py): every refuted obligation's governing
check, demand, capacity and utilisation in the design's units, and its own counterexample
as decimals in those units beside the exact rationals the kernel checked.

The fixtures are designs a cold-start agent wrote: a 60 kip shear tab whose bolts and
block shear fail (steel, kips and inches) and a 30 m cable that runs hot and drops too
much voltage (wiring, SI). truss_fail.petra is the shipped failing example.
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

import petra
from petra import readout, verdict
from petra.kernel.rules.r4_enclosure import AllNonpositive
from petra.pipeline import Report
from petra.units import CUSTOMARY, UNITS

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "readout"
JOB5 = FIXTURES / "job5_fail_60k.petra"
CABLE = FIXTURES / "cable_30m_protected.petra"
TRUSS = ROOT / "examples" / "truss_fail.petra"
KIP = CUSTOMARY["kip"][0]
RATIONAL = re.compile(r"\b\d+/\d+\b")
OBLIGATION_KEYS = {"requirement", "entry", "outcome", "rule", "statement_hash", "describe", "at", "governing",
                   "demand", "capacity", "unit", "utilisation", "checks", "claim", "counterexample", "margin_point", "needs", "note"}

_REPORTS: dict[Path, Report] = {}


def check(path: Path) -> Report:
    if path not in _REPORTS:
        _REPORTS[path] = petra.check_file(path)
    return _REPORTS[path]


def refuted(report: Report) -> list[readout.Finding]:
    return [f for f in report.findings if f.outcome == "refuted"]


def blocks(text: str) -> dict[str, list[str]]:
    """Requirement id -> the lines printed under its "counterexample" heading."""
    found: dict[str, list[str]] = {}
    current = None
    for line in text.split("\n"):
        if line.startswith("counterexample  "):
            current = line[len("counterexample  "):].split(":")[0]
            found[current] = []
        elif current is not None and line.startswith("  "):
            found[current].append(line.strip())
        else:
            current = None
    return found


def factor(unit: str) -> Fraction:
    return (UNITS.get(unit) or CUSTOMARY[unit])[0]


class SteelFailure(unittest.TestCase):
    """job5: 60 kip on three 3/4 in bolts, refuted for the bolts and for block shear."""

    def setUp(self):
        self.report = check(JOB5)

    def test_every_refuted_obligation_has_its_governing_check_in_kips(self):
        found = refuted(self.report)
        self.assertEqual({f.requirement for f in found}, {"tab/steel.bolts/coverage.steel.bolts", "tab/steel.block_shear/coverage.steel.block_shear"})
        for f in found:
            with self.subTest(requirement=f.requirement):
                g = f.governing
                self.assertEqual((f.at, g.unit), ("point", "kip"))
                self.assertGreater(g.demand, g.capacity)
                self.assertGreater(g.utilisation, 1)
        bolts = next(f for f in found if "bolts" in f.requirement)
        self.assertIn("most loaded bolt", bolts.governing.what)
        self.assertAlmostEqual(bolts.governing.demand, 36.06, places=2)
        self.assertAlmostEqual(bolts.governing.utilisation, 2.02, places=2)

    def test_each_counterexample_gives_the_load_in_kips_and_its_exact_value(self):
        for f in refuted(self.report):
            with self.subTest(requirement=f.requirement):
                (shear,) = [c for c in f.point if c.label.endswith(".reaction.tab.shear")]
                self.assertEqual((shear.decimal, shear.unit, shear.si_unit, shear.exact), ("60", "kip", "N", 60 * KIP))
                self.assertTrue(shear.varies)

    def test_the_text_prints_numbers_and_point_under_each_refuted_obligation(self):
        text = self.report.render()
        found = blocks(text)
        self.assertEqual(set(found), {f.requirement for f in refuted(self.report)})
        for requirement, lines in found.items():
            with self.subTest(requirement=requirement):
                self.assertTrue(lines[0].startswith("governing  "), lines)
                self.assertRegex(lines[0], r"demand [0-9.]+ kip, capacity [0-9.]+ kip, utilisation [0-9.]+$")
                self.assertTrue(any(re.search(r"reaction\.tab\.shear = 60 kip", line) for line in lines), lines)
                self.assertFalse([line for line in lines if RATIONAL.search(line)], "no exact rational in the point")
        self.assertIn("also over  plate: block of 2 row(s)", text)

    def test_a_claim_on_a_check_reads_its_utilisation_against_the_claimed_bound(self):
        source = JOB5.read_text(encoding="utf-8") + "\nclaim tight: tab.bolts <= 0.95 under reaction\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "job5_claim.petra"
            path.write_text(source, encoding="utf-8", newline="\n")
            report = petra.check_file(path)
            text = report.render()
        (f,) = [f for f in refuted(report) if f.requirement == "tab/steel.bolts/claim.tight"]
        self.assertTrue(f.governing.what.endswith("against 0.95 of its available strength"), f.governing.what)
        self.assertEqual((f.claim.claim, f.claim.quantity, f.claim.bound, f.claim.unit), ("tight", "bolts", 0.95, "1"))
        self.assertAlmostEqual(f.claim.value, 0.95 * f.governing.utilisation)
        self.assertIn("claim      tight: bolts is 2.015 here, against its bound 0.95", text)

    def test_a_failing_reader_costs_its_numbers_never_the_verdict(self):
        def broken():
            def read(*args):
                raise RuntimeError("boom")
            return readout.Domain(read, {})

        report = petra.check_file(JOB5)
        with mock.patch.dict(readout.READERS, {"steel": broken}):
            text = report.render()
        self.assertIsInstance(report.verdict, petra.Fail)
        self.assertIn("numbers    not read: the steel reader failed: RuntimeError: boom", text)
        self.assertEqual(len(report.findings), len(report.outcomes))


class WiringFailure(unittest.TestCase):
    """The 30 m cable: 100 degC against 70 degC, 9.9 V against 6.9 V."""

    def setUp(self):
        self.report = check(CABLE)

    def test_each_claim_reads_its_quantity_against_its_bound_in_its_units(self):
        found = {f.requirement: f for f in refuted(self.report)}
        hot = found["feed.w1/wire.steady_temperature/claim.hot"]
        self.assertEqual((hot.governing.unit, hot.claim.unit, hot.claim.bound), ("degC", "degC", 70))
        self.assertAlmostEqual(hot.claim.value, 100.1, places=1)
        drop = found["feed.w1/wire.voltage_drop/claim.drop"]
        self.assertEqual((drop.governing.unit, drop.claim.quantity, drop.claim.bound), ("V", "voltage_drop", 0.03))
        self.assertAlmostEqual(drop.claim.value, drop.governing.demand / 230, places=6)
        self.assertGreater(drop.claim.value, drop.claim.bound)

    def test_the_point_gives_each_input_in_its_unit(self):
        text = self.report.render()
        self.assertIn("claim      hot: temperature is 100.1 degC here, against its bound 70 degC", text)
        self.assertIn("draw.feed.load.current = 20 A", text)
        self.assertIn("ambient                        = 30 degC", text)
        for requirement, lines in blocks(text).items():
            with self.subTest(requirement=requirement):
                self.assertTrue(lines[0].startswith("governing  "), lines)
                self.assertFalse([line for line in lines if RATIONAL.search(line)], lines)

    def test_a_coverage_requirement_has_no_claim(self):
        coverage = [f for f in self.report.findings if f.entry == "coverage"]
        self.assertTrue(coverage)
        self.assertTrue(all(f.claim is None for f in coverage))


class TrussFailure(unittest.TestCase):
    def setUp(self):
        self.report = check(TRUSS)

    def test_the_collapse_claim_reads_the_load_factor_the_truss_carries(self):
        (f,) = [f for f in refuted(self.report) if f.requirement == "frame/truss.plastic_collapse/claim.strength"]
        self.assertEqual((f.governing.demand, f.claim.bound, f.claim.quantity), (1.5, 1.5, "collapse_factor"))
        self.assertLess(f.claim.value, 1.5)
        self.assertAlmostEqual(f.claim.value, f.governing.capacity)

    def test_member_buckling_reads_the_member_force_at_the_point(self):
        found = [f for f in refuted(self.report) if f.requirement.endswith("/truss.member_buckling/coverage.truss.axial_member")]
        self.assertEqual(len(found), 2)
        for f in found:
            with self.subTest(requirement=f.requirement):
                self.assertEqual(f.governing.unit, "kN")
                self.assertGreater(f.governing.utilisation, 1)
                self.assertIsNone(f.note)


class Json(unittest.TestCase):
    def test_every_outcome_is_an_obligation_with_its_numbers(self):
        for path in (JOB5, CABLE, TRUSS):
            with self.subTest(path=path.name):
                done = subprocess.run([sys.executable, "-m", "petra", "check", "--json", str(path)], capture_output=True, text=True, cwd=ROOT)
                body = json.loads(done.stdout)
                report = check(path)
                listed = [o for v in body["verdicts"] for o in v["obligations"]]
                self.assertEqual(len(listed), len(report.outcomes))
                for o in listed:
                    self.assertEqual(set(o), OBLIGATION_KEYS)
                    self.assertIn(o["outcome"], {"certified", "refuted", "marginal", "waived", "open"})
                    self.assertTrue(o["statement_hash"].startswith("sha256:"))
                for o in (o for o in listed if o["outcome"] == "refuted"):
                    self.assertIsNotNone(o["governing"], o["requirement"])
                    self.assertGreater(o["utilisation"], 1)
                    self.assertTrue(o["counterexample"])
                    for c in o["counterexample"]:
                        exact = Fraction(c["exact"])
                        if c["unit"] is not None and c["si_unit"] is not None and c["unit"] != c["si_unit"]:
                            self.assertAlmostEqual(float(c["value"].lstrip("~")), float(exact / factor(c["unit"])), places=4)

    def test_needs_list_what_an_open_entry_needs(self):
        body = check(ROOT / "examples" / "bolt_unknown.petra").to_json()
        coverage = next(v for v in body["verdicts"] if v["claim"] == "coverage")
        self.assertEqual(coverage["status"], "UNKNOWN")
        self.assertEqual(coverage["needs"], [n for o in coverage["obligations"] for n in o["needs"]])
        tension = next(v for v in body["verdicts"] if v["claim"] == "tension")
        (o,) = tension["obligations"]
        self.assertEqual((o["outcome"], o["at"], o["unit"], o["counterexample"]), ("certified", "box", "kN", None))
        self.assertLess(o["utilisation"], 1)


class Terms(unittest.TestCase):
    def test_terms_name_each_term_their_builders_state(self):
        seen = set()
        for path in (CABLE, ROOT / "examples" / "circuit_pass.petra", ROOT / "examples" / "bolt_unknown.petra", TRUSS):
            for o in check(path).outcomes:
                statement, *_ = readout._parts(o)
                mode = (o.requirement if isinstance(o, (verdict.Open, verdict.Waived)) else o.obligation.requirement).mode.id
                if statement is not None and isinstance(statement.goal, AllNonpositive) and mode in readout.TERMS:
                    seen.add(mode)
                    self.assertEqual(len(statement.goal.exprs), len(readout.TERMS[mode]), mode)
        self.assertEqual(seen, set(readout.TERMS), "every listed mode was held to a statement")


class Api(unittest.TestCase):
    def test_marginal_is_exported(self):
        self.assertIs(petra.Marginal, verdict.Marginal)

    def test_a_report_without_its_design_still_gives_a_finding_per_outcome(self):
        import dataclasses
        bare = dataclasses.replace(check(CABLE), ir=None, registry=None)
        self.assertEqual(len(bare.findings), len(bare.outcomes))
        self.assertTrue(all(f.values == () and f.note == "the report carries no design to read it against" for f in bare.findings))
        self.assertEqual(bare.verdict, check(CABLE).verdict)

    def test_docs_api_shows_an_obligation_with_every_key(self):
        text = (ROOT / "petra" / "docs" / "api.md").read_text(encoding="utf-8")
        start = text.index("```json\n") + len("```json\n")
        sample = json.loads(text[start:text.index("\n```", start)])
        self.assertEqual(set(sample), OBLIGATION_KEYS)
        (bolts,) = [f for f in refuted(check(JOB5)) if f.requirement == sample["requirement"]]
        self.assertEqual((sample["statement_hash"], sample["unit"]), (bolts.statement_hash, bolts.governing.unit))


if __name__ == "__main__":
    unittest.main()
