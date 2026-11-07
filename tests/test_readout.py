"""What a check tells a stranger (petra/readout.py): every refuted obligation's governing
check, demand, capacity and utilisation in the design's units, and its own counterexample
as decimals in those units beside the exact rationals the kernel checked; for every
report, PASS included, the governing strength check and the governing detailing check,
and each obligation's utilisation; and for a bolt group, the limit state and ply that set
each bolt's strength.

The fixtures are designs cold-start agents wrote: a 60 kip shear tab whose bolts and
block shear fail (steel, kips and inches), a 30 m cable that runs hot and drops too
much voltage (wiring, SI), a 75 kip shear tee before and after its repair, a double angle
and an end plate that pass. shear_tab_ovs_snug.petra puts oversized holes in a snug-tight
joint. truss_fail.petra is the shipped failing example.
"""
import dataclasses
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
TEE_TRY1 = FIXTURES / "shear_tee_75k_try1.petra"
TEE_TRY4 = FIXTURES / "shear_tee_75k_try4.petra"
DOUBLE_ANGLE = FIXTURES / "double_angle_70k.petra"
END_PLATE = FIXTURES / "end_plate_40k.petra"
OVS = FIXTURES / "shear_tab_ovs_snug.petra"
TRUSS = ROOT / "examples" / "truss_fail.petra"
HOOK = ROOT / "examples" / "hook_uncertain.petra"
STEEL = sorted((ROOT / "examples" / "steel").glob("*.petra"))
KIP = CUSTOMARY["kip"][0]
RATIONAL = re.compile(r"\b\d+/\d+\b")
OBLIGATION_KEYS = {"requirement", "entry", "category", "outcome", "rule", "statement_hash", "describe", "at", "governing",
                   "demand", "capacity", "unit", "utilisation", "checks", "claim", "counterexample", "margin_point", "needs", "note"}
CHECK_KEYS = {"check", "demand", "capacity", "unit", "utilisation", "excused", "excuse", "met", "parts"}
PART_KEYS = {"part", "count", "capacity", "governing", "limits"}
WEAKEST = "most loaded bolt by the elastic method against the weakest bolt"
SUMMED = "bolt shear, bearing and tearout summed over the group"

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
    """The 30 m cable: 106.8 degC against 70 degC, 10.6 V against 6.9 V."""

    def setUp(self):
        self.report = check(CABLE)

    def test_each_claim_reads_its_quantity_against_its_bound_in_its_units(self):
        found = {f.requirement: f for f in refuted(self.report)}
        hot = found["feed.w1/wire.steady_temperature/claim.hot"]
        self.assertEqual((hot.governing.unit, hot.claim.unit, hot.claim.bound), ("degC", "degC", 70))
        self.assertAlmostEqual(hot.claim.value, 106.8, places=1)
        drop = found["feed.w1/wire.voltage_drop/claim.drop"]
        self.assertEqual((drop.governing.unit, drop.claim.quantity, drop.claim.bound), ("V", "voltage_drop", 0.03))
        self.assertAlmostEqual(drop.claim.value, drop.governing.demand / 230, places=6)
        self.assertGreater(drop.claim.value, drop.claim.bound)

    def test_the_point_gives_each_input_in_its_unit(self):
        text = self.report.render()
        self.assertIn("claim      hot: temperature is 106.8 degC here, against its bound 70 degC", text)
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
                    self.assertTrue(all(set(c) == CHECK_KEYS for c in o["checks"]), o["requirement"])
                    self.assertIn(o["outcome"], {"certified", "refuted", "marginal", "waived", "open"})
                    self.assertIn(o["category"], {"strength", "detailing"})
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
        (shown,) = sample["checks"]
        self.assertEqual(set(shown), CHECK_KEYS)
        (part,) = shown["parts"]
        self.assertEqual(set(part), PART_KEYS)
        self.assertEqual(part, bolts.governing.to_json()["parts"][0], "the sample's part is the report's")

    def test_a_finding_carries_every_number_its_json_record_does(self):
        for path in (JOB5, CABLE, TRUSS, OVS, DOUBLE_ANGLE):
            for f in check(path).findings:
                with self.subTest(path=path.name, requirement=f.requirement):
                    o, g = f.to_json(), f.governing
                    self.assertEqual(o["governing"], None if g is None else g.what)
                    self.assertEqual((o["demand"], o["capacity"], o["unit"]), (None, None, None) if g is None else (g.demand, g.capacity, g.unit))
                    self.assertEqual(o["utilisation"], f.utilisation if f.utilisation is None or f.utilisation < float("inf") else None)
                    self.assertEqual((o["category"], o["checks"]), (f.category, [v.to_json() for v in f.values]))

    def test_utilisation_and_governing_show_in_a_findings_repr(self):
        f = next(f for f in check(JOB5).findings if f.governing is not None)
        shown = repr(f)
        self.assertIn(f"governing=Value(what={f.governing.what!r}", shown)
        self.assertIn(f"utilisation={f.utilisation!r}", shown)
        self.assertIn("utilisation", {field.name for field in dataclasses.fields(readout.Value)})


def summary_lines(text: str) -> list[str]:
    """The `governing` lines right after the `checked` line."""
    lines = text.split("\n")
    at = next(i for i, line in enumerate(lines) if line.startswith("checked    ")) + 1
    end = next(i for i in range(at, len(lines)) if not lines[i].startswith("governing  "))
    return lines[at:end]


class GoverningChecks(unittest.TestCase):
    """Every report, PASS included, names its governing strength check and its governing
    detailing check, each with its numbers, right after the `checked` line."""

    def test_a_pass_names_its_governing_strength_and_detailing_checks(self):
        # The cold-start agents found these by sorting --json: bolts 0.57 and edge_min 0.80
        # for the double angle, the weld 0.59 and spacing_max 0.92 for the end plate.
        for path, strength, detailing in ((DOUBLE_ANGLE, ("da1/steel.bolts/", 0.57), ("da1/steel.edge_min/", 0.8)),
                                          (END_PLATE, ("ep1/steel.weld/", 0.589), ("ep1/steel.spacing_max/", 0.917))):
            with self.subTest(path=path.name):
                report = check(path)
                self.assertIsInstance(report.verdict, petra.Pass)
                s, d = summary_lines(report.render())
                self.assertTrue(s.startswith(f"governing  strength   {strength[0]}"), s)
                self.assertTrue(d.startswith(f"governing  detailing  {detailing[0]}"), d)
                self.assertRegex(s, rf"demand [0-9.]+ kip, capacity [0-9.]+ kip, utilisation {strength[1]}\b")
                self.assertRegex(d, rf"demand [0-9.]+ in, capacity [0-9.]+ in, utilisation {detailing[1]}\b")

    def test_each_is_the_highest_utilisation_of_its_category(self):
        for path in (DOUBLE_ANGLE, END_PLATE, TEE_TRY1, JOB5, CABLE, TRUSS):
            with self.subTest(path=path.name):
                body = check(path).to_json()
                listed = [o for v in body["verdicts"] for o in v["obligations"]]
                for category in ("strength", "detailing"):
                    mine = [c["utilisation"] for o in listed if o["category"] == category for c in o["checks"]
                            if c["utilisation"] is not None and not c["excused"]]
                    found = body["governing"][category]
                    if not mine:
                        self.assertIsNone(found)
                        continue
                    self.assertEqual(set(found), {"requirement"} | CHECK_KEYS)
                    self.assertEqual(found["utilisation"], max(mine))
                    owner = next(o for o in listed if o["requirement"] == found["requirement"])
                    self.assertEqual(owner["category"], category)

    def test_detailing_never_governs_strength(self):
        # flange_force.petra checks only the column's flange and web, so it has no detailing.
        for path in (DOUBLE_ANGLE, END_PLATE, *STEEL):
            with self.subTest(path=path.name):
                found = check(path).governing
                self.assertNotIn(found["strength"].requirement.split("/")[1], readout.DETAILING_MODES)
                if path.name != "flange_force.petra":
                    self.assertIn(found["detailing"].requirement.split("/")[1], readout.DETAILING_MODES)

    def test_a_design_without_numbers_says_none(self):
        report = check(HOOK)
        self.assertIsInstance(report.verdict, petra.Pass)
        self.assertEqual(summary_lines(report.render()), ["governing  strength   none: no strength check here has a utilisation"])
        self.assertEqual(report.to_json()["governing"], {"strength": None, "detailing": None})

    def test_a_member_in_tension_uses_none_of_its_buckling_resistance(self):
        report = check(ROOT / "examples" / "truss_pass.petra")
        chord = next(f for f in report.findings if f.requirement.startswith("frame.bottom_ab/truss.member_buckling"))
        self.assertLess(chord.governing.ratio, 0)
        self.assertEqual(chord.utilisation, 0.0)
        self.assertNotIn("utilisation -", report.render())
        self.assertEqual(len(summary_lines(report.render())), 1)

    def test_every_table_row_ends_with_its_utilisation_or_nothing(self):
        for path in (DOUBLE_ANGLE, TEE_TRY1, OVS, TRUSS, HOOK):
            with self.subTest(path=path.name):
                report = check(path)
                lines = report.render().split("\n")
                at = next(i for i, line in enumerate(lines) if line.startswith("checked    ")) + 1 + len(summary_lines(report.render()))
                for f, line in zip(report.findings, lines[at:at + len(report.findings)]):
                    if f.utilisation is None:
                        self.assertNotIn("utilisation", line)
                    else:
                        self.assertTrue(line.endswith(f"  utilisation {readout._ratio(f.utilisation)}"), line)

    def test_a_claims_utilisation_is_its_quantity_against_its_bound(self):
        cable = {f.requirement: f for f in check(CABLE).findings}
        for name in ("feed.w1/wire.steady_temperature/claim.hot", "feed.w1/wire.voltage_drop/claim.drop"):
            f = cable[name]
            self.assertAlmostEqual(f.utilisation, f.claim.value / f.claim.bound, places=9)
        collapse = next(f for f in check(TRUSS).findings if f.requirement == "frame/truss.plastic_collapse/claim.strength")
        self.assertAlmostEqual(collapse.utilisation, collapse.claim.bound / collapse.claim.value, places=9)


class Rules(unittest.TestCase):
    """Hole use and joint type are met or not: no demand, capacity or utilisation."""

    def test_rule_checks_carry_no_numbers(self):
        for path in (DOUBLE_ANGLE, OVS):
            for f in check(path).findings:
                if readout.DETAILING_MODES.get(f.requirement.split("/")[1]) != readout.RULE:
                    continue
                with self.subTest(path=path.name, requirement=f.requirement):
                    self.assertTrue(f.values)
                    for c in f.to_json()["checks"]:
                        self.assertEqual((c["demand"], c["capacity"], c["unit"], c["utilisation"]), (None, None, None, None))
                        self.assertIn(c["met"], (True, False))

    def test_a_rule_not_met_governs_its_obligation_and_the_detailing_summary(self):
        report = check(OVS)
        (f,) = refuted(report)
        self.assertEqual(f.requirement, "st1/steel.hole_use/coverage.steel.hole_use")
        self.assertEqual((f.governing.what, f.governing.met, f.utilisation), ("plate: ovs holes in a joint of the type they need (J3.3)", False, None))
        text = report.render()
        self.assertEqual(blocks(text)[f.requirement][0], "governing  plate: ovs holes in a joint of the type they need (J3.3): not met")
        self.assertEqual(summary_lines(text)[1], f"governing  detailing  {f.requirement}: plate: ovs holes in a joint of the type they need (J3.3): not met")
        self.assertEqual(report.to_json()["governing"]["detailing"]["met"], False)

    def test_numeric_checks_have_no_met(self):
        f = next(f for f in check(DOUBLE_ANGLE).findings if f.requirement.startswith("da1/steel.edge_min/"))
        self.assertTrue(all(v.met is None and v.utilisation is not None for v in f.values))


class BoltGroups(unittest.TestCase):
    """A bolt group's check names the limit state and ply that set each bolt's strength."""

    def bolts(self, path: Path) -> readout.Finding:
        return next(f for f in check(path).findings if "/steel.bolts/" in f.requirement)

    def test_tearout_at_the_tee_stems_bottom_edge_sets_the_weakest_bolt(self):
        # 1 in bolts, 1-1/8 in standard holes, 1-1/4 in edge distance: lc = 1.25 - 1.125/2
        # = 0.6875 in on the 0.37 in stem of a WT6x25 in A992, so phi 1.2 lc t Fu =
        # 0.75 x 1.2 x 0.6875 x 0.37 x 65 kip (J3.11a, Eq J3-6c).
        g = self.bolts(TEE_TRY1).governing
        self.assertIn(WEAKEST, g.what)
        weakest = g.parts[0]
        self.assertEqual((weakest.what, weakest.count), ("bottom row (1 bolt)", 1))
        self.assertEqual(weakest.governing.what, "tearout of the tee stem to its edge (lc 0.6875 in)")
        self.assertAlmostEqual(weakest.capacity, 0.75 * 1.2 * 0.6875 * 0.37 * 65, places=9)
        self.assertAlmostEqual(g.capacity, weakest.capacity, places=9)
        self.assertIn("bolt shear", {limit.what for limit in weakest.limits})
        text = check(TEE_TRY1).render()
        self.assertIn("weakest    bottom row (1 bolt): 14.88 kip, set by tearout of the tee stem to its edge (lc 0.6875 in); ", text)
        self.assertTrue(summary_lines(text)[0].endswith("; weakest bottom row (1 bolt): 14.88 kip, set by tearout of the tee stem "
                                                         "to its edge (lc 0.6875 in)"), summary_lines(text)[0])

    def test_the_repair_moved_the_weakest_bolt_from_tearout_to_bolt_shear(self):
        # Try 4: 3/4 in bolts with threads excluded and 1-1/2 in edge distance. Its bolt
        # shear, phi Fnv Ab = 0.75 x 68 x pi 0.75^2 / 4, is now below the stem's tearout.
        g = self.bolts(TEE_TRY4).governing
        self.assertEqual(g.parts[0].governing.what, "bolt shear")
        self.assertAlmostEqual(g.capacity, 0.75 * 68 * 3.141592653589793 * 0.75 ** 2 / 4, places=3)

    def test_every_bolt_group_check_names_its_parts(self):
        for path in STEEL:
            for f in check(path).findings:
                for v in f.values:
                    if WEAKEST not in v.what and SUMMED not in v.what:
                        continue
                    with self.subTest(path=path.name, check=v.what):
                        self.assertTrue(v.parts)
                        self.assertEqual([p.capacity for p in v.parts], sorted(p.capacity for p in v.parts))
                        for p in v.parts:
                            self.assertEqual(p.capacity, min(limit.capacity for limit in p.limits))
                        if WEAKEST in v.what:
                            self.assertAlmostEqual(v.capacity, v.parts[0].capacity, places=9)
                        else:
                            self.assertAlmostEqual(v.capacity, sum(p.count * p.capacity for p in v.parts), places=6)

    def test_no_other_check_has_parts(self):
        for path in (DOUBLE_ANGLE, TEE_TRY1):
            for f in check(path).findings:
                for v in f.values:
                    if WEAKEST not in v.what and SUMMED not in v.what:
                        self.assertEqual(v.parts, (), v.what)


class Labels(unittest.TestCase):
    def test_no_check_name_repeats_a_word(self):
        doubled = re.compile(r"\b(\w+) \1\b")
        for path in STEEL:
            for f in check(path).findings:
                for v in f.values:
                    self.assertIsNone(doubled.search(v.what), v.what)

    def test_the_tee_flange_names_its_side_edge(self):
        f = next(f for f in check(ROOT / "examples" / "steel" / "shear_tee.petra").findings if "/steel.edge_min/" in f.requirement)
        self.assertIn("tee flange: flange side edge distance at least Table J3.4's (J3.5)", {v.what for v in f.values})


if __name__ == "__main__":
    unittest.main()
