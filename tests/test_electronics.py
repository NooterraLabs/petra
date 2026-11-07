"""The electronics deck (docs/electronics_dc.md): its examples and their certificates, the
board grammar's refusals, the E-series and the registry's parts, coverage of every rating,
validity and missing inputs, the builder rules, and the gate on a small sample."""
import ast
import json
import re
import subprocess
import sys
import unittest
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

from petra.lang import parse_design
from petra.models.base import ComponentError
from petra.models.electronics import board, domain
from petra.models.electronics import faults as F
from petra.models.electronics import gate as G
from petra.models.electronics import generate as gen
from petra.pipeline import check_design
from petra.registry import build_registry
from petra.registry.electronics import E24, E96, neighbours, preferred, series_key, split_decade
from petra.solvers import SolverSource
from petra.verdict import STATUS

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "electronics"
PACKAGE = ROOT / "petra" / "models" / "electronics"
REGISTRY = build_registry()
SIGNED = 'signed "t@example.org" source "test"'
HEADER = 'petra 0\n\ndesign "t" {\n  owner "t@example.org"\n  environment indoor_dry\n}\n\n'
SUPPLY = f"  supply vin voltage in [11.4 V, 12.6 V] {SIGNED} capacity in [1 A, 1 A] {SIGNED}\n"


def written(lines: str, after: str = "", header: str = HEADER, supply: str = SUPPLY) -> str:
    return f"{header}board b {{\n{supply}{lines}}}\n{after}"


def check(text: str):
    return check_design(parse_design(text, "t.petra", REGISTRY), REGISTRY, (SolverSource(),))


def modes(report, kind: str) -> set[str]:
    out = set()
    for o in report.outcomes:
        if type(o).__name__ == kind:
            req = o.requirement if kind == "Open" else o.obligation.requirement
            out.add(req.mode.id.split(".", 1)[1])
    return out


def needs(report) -> str:
    return " ".join(str(n) for o in report.outcomes if type(o).__name__ == "Open" for n in o.needs)


class Examples(unittest.TestCase):
    EXPECTED = {
        "board": ("PASS", set()),
        "adjustable": ("PASS", set()),
        "led_fail": ("FAIL", {"led_rating"}),
        "regulator_fail": ("FAIL", {"regulator_headroom", "regulator_thermal"}),
        "cold_unknown": ("UNKNOWN", set()),
    }

    @classmethod
    def setUpClass(cls):
        cls.reports = {name: check((EXAMPLES / f"{name}.petra").read_text(encoding="utf-8")) for name in cls.EXPECTED}

    def test_each_example_gets_its_verdict_and_names_the_failing_mode(self):
        self.assertEqual(sorted(p.stem for p in EXAMPLES.glob("*.petra")), sorted(self.EXPECTED))
        for name, (status, refuted) in self.EXPECTED.items():
            with self.subTest(name):
                report = self.reports[name]
                self.assertEqual(STATUS[type(report.verdict)], status)
                self.assertEqual(modes(report, "Refuted"), refuted)

    def test_the_cold_example_is_open_on_the_cold_row_everywhere(self):
        report = self.reports["cold_unknown"]
        self.assertTrue(all(type(o).__name__ == "Open" for o in report.outcomes))
        self.assertIn("dc.cold", needs(report))
        self.assertIn("('outdoor_c3.ambient', '-25')", needs(report))

    def test_the_led_example_leaves_the_checks_that_read_the_overdriven_led_open(self):
        report = self.reports["led_fail"]
        self.assertIn("dc.led_range", needs(report))
        self.assertEqual(modes(report, "Discharged"), set(), "nothing that reads the LED past its fit passes")

    def test_the_cli_exits_by_verdict(self):
        for name, code in (("board", 0), ("led_fail", 1), ("cold_unknown", 2)):
            with self.subTest(name):
                done = subprocess.run([sys.executable, "-m", "petra", "check", f"examples/electronics/{name}.petra", "--json"],
                                      cwd=ROOT, capture_output=True, text=True, timeout=600)
                self.assertEqual(done.returncode, code, done.stderr)
                self.assertEqual(json.loads(done.stdout)["status"], self.EXPECTED[name][0])

    def test_each_example_rechecks_from_its_certificates(self):
        for name, (status, _) in self.EXPECTED.items():
            with self.subTest(name):
                self.assertEqual(G.certificates((EXAMPLES / f"{name}.petra").read_text(encoding="utf-8"), REGISTRY, status), "ok")

    def test_coverage_reads_every_rating_of_every_part_in_the_board_example(self):
        report = self.reports["board"]
        owed = {("/".join(o.obligation.requirement.subject), o.obligation.requirement.mode.id) for o in report.outcomes
                if type(o).__name__ == "Discharged"}
        design = parse_design((EXAMPLES / "board.petra").read_text(encoding="utf-8"), "t.petra", REGISTRY)
        lowered = board.lower_board(design.components["psu"], design, REGISTRY)
        for element in lowered.elements.values():
            part = getattr(element, "part", None)
            for mode, (line, props) in domain.RATINGS.items():
                if part is not None and board.FAMILIES[REGISTRY.material(part).family] == line \
                        and set(props) & set(REGISTRY.material(part).props):
                    self.assertIn(("psu/" + element.name, mode.id), owed)
        self.assertIn(("psu/vin", "dc.supply_current"), owed)


class Grammar(unittest.TestCase):
    def rejects(self, lines: str, fragment: str, after: str = "") -> None:
        with self.assertRaises(ComponentError) as ctx:
            check(written(lines, after))
        self.assertIn(fragment, str(ctx.exception))

    def test_a_value_outside_the_parts_series_is_refused_with_its_neighbours(self):
        self.rejects("  resistor r1 part res.0603_1pct value 4.7 kohm from vin\n", "is not an E96 value")
        self.rejects("  resistor r1 part res.0603_1pct value 4.7 kohm from vin\n", "4.64 kohm")

    def test_a_value_outside_the_parts_range_is_refused(self):
        self.rejects("  resistor r1 part res.0603_1pct value 4.99 Mohm from vin\n", "is made from")

    def test_a_part_of_the_wrong_kind_is_refused(self):
        self.rejects("  regulator v1 part res.0603_1pct from vin\n", "res.0603_1pct")
        self.rejects("  resistor r1 part led.red_0603 value 1 kohm from vin\n", "led.red_0603")

    def test_every_resistor_is_placed_exactly_once(self):
        self.rejects("  resistor r1 part res.0603_1pct value 1 kohm\n", "is not placed")
        self.rejects("  resistor r1 part res.0603_1pct value 1 kohm\n  resistor r2 part res.0603_1pct value 1 kohm\n"
                     "  divider a from vin top r1 bottom r2\n  divider c from vin top r2 bottom r1\n", "is placed by both")
        self.rejects("  resistor r1 part res.0603_1pct value 1 kohm\n  divider a from vin top r1 bottom r1\n",
                     "two different resistors")

    def test_an_unknown_rail_or_resistor_is_refused(self):
        self.rejects("  resistor r1 part res.0603_1pct value 1 kohm\n  led d1 part led.red_0603 from v9 resistor r1\n",
                     "which is not a supply or regulator")
        self.rejects("  led d1 part led.red_0603 from vin resistor r7\n", "which is not a resistor")

    def test_regulators_feeding_each_other_are_refused(self):
        self.rejects("  regulator v1 part reg.ldo1117_3v3_sot223 from v2\n  regulator v2 part reg.ldo1117_5v0_sot223 from v1\n",
                     "feed each other in a loop")

    def test_feedback_resistors_follow_the_regulators_style(self):
        self.rejects("  resistor r1 part res.0603_1pct value 1 kohm\n  resistor r2 part res.0603_1pct value 1 kohm\n"
                     "  regulator v1 part reg.ldo1117_3v3_sot223 from vin top r1 bottom r2\n", "has a fixed output")
        self.rejects("  regulator v1 part reg.lm317_to220 from vin\n", "is adjustable")

    def test_an_led_count_is_a_whole_number_from_one(self):
        for count in ("0", "1.5"):
            with self.subTest(count):
                self.rejects(f"  resistor r1 part res.0603_1pct value 1 kohm\n"
                             f"  led d1 part led.red_0603 from vin resistor r1 count {count}\n", "count needs a whole number")

    def test_an_unknown_line_names_every_line_a_board_takes(self):
        self.rejects("  fuse f1 from vin\n", "unknown line; a board takes divider, led, regulator, resistor, sink, supply")

    def test_a_claim_on_a_quantity_the_element_lacks_is_refused(self):
        self.rejects("  resistor r1 part res.0603_1pct value 1 kohm from vin\n", "is a quantity of a",
                     after="\nclaim x: b.r1.voltage <= 3 V\n")

    def test_a_load_names_a_sinks_current(self):
        self.rejects("  regulator v1 part reg.ldo1117_3v3_sot223 from vin\n  sink s1 from v1\n", "load field",
                     after=f"\nload run {{\n  on b.s1 force in [1 N, 2 N]\n  {SIGNED}\n}}\n")


class Series(unittest.TestCase):
    def test_e96_is_ten_to_the_i_over_96_rounded_to_three_figures(self):
        self.assertEqual(len(E96), 96)
        for i, text in enumerate(E96):
            self.assertEqual(Fraction(text), Fraction(round(10 ** (i / 96), 2)).limit_denominator(100), text)

    def test_e24_runs_in_order_within_five_percent_of_ten_to_the_i_over_24(self):
        self.assertEqual(len(E24), 24)
        self.assertEqual(sorted(E24, key=Fraction), list(E24))
        for i, text in enumerate(E24):
            self.assertLess(abs(float(text) / 10 ** (i / 24) - 1), 0.05, text)

    def test_every_value_is_a_registry_constant(self):
        for steps, values in ((24, E24), (96, E96)):
            for text in values:
                self.assertEqual(REGISTRY.constants[series_key(steps, text)].value.lo, Fraction(text))

    def test_a_value_splits_into_a_mantissa_and_a_decade(self):
        self.assertEqual(split_decade(Fraction(4990)), (Fraction(499, 100), Fraction(1000)))
        self.assertEqual(split_decade(Fraction(1, 2)), (Fraction(5), Fraction(1, 10)))
        self.assertEqual(preferred(Fraction(4990), 96, REGISTRY.constants), ("iec60063.E96.4_99", Fraction(1000)))
        self.assertIsNone(preferred(Fraction(4700), 96, REGISTRY.constants))
        self.assertEqual(neighbours(Fraction(4700), 96, REGISTRY.constants), (Fraction(4640), Fraction(4750)))
        self.assertEqual(neighbours(Fraction(9900), 24, REGISTRY.constants), (Fraction(9100), Fraction(10000)))


class Parts(unittest.TestCase):
    def test_every_property_of_every_part_has_a_role(self):
        parts = [m for m in REGISTRY.materials.values() if m.family in board.FAMILIES]
        self.assertEqual(len(parts), 10)
        for m in parts:
            with self.subTest(m.id):
                roles = domain.PROPERTIES[board.FAMILIES[m.family]]
                named = set().union(*roles.values())
                self.assertEqual(set(m.props), named & set(m.props), "a property with no role")
                self.assertTrue(roles["rating"] & set(m.props), "a part holds a rating")

    def test_every_part_cites_its_source_and_says_it_is_recalled(self):
        for m in (m for m in REGISTRY.materials.values() if m.family in board.FAMILIES):
            with self.subTest(m.id):
                self.assertIn("recalled", m.standard)
                for prop in m.props.values():
                    if hasattr(prop, "standard"):
                        self.assertTrue(prop.standard)


class Coverage(unittest.TestCase):
    def test_coverage_demands_every_rating_with_no_claim(self):
        report = check(written("  resistor r1 part res.0603_1pct value 2.21 kohm\n"
                               "  led d1 part led.red_0603 from vin resistor r1\n"))
        demanded = {o.obligation.requirement.mode.id.split(".", 1)[1] for o in report.outcomes
                    if type(o).__name__ in ("Discharged", "Refuted")}
        self.assertEqual(demanded, {"led_rating", "resistor_power", "resistor_voltage", "supply_current"})
        self.assertEqual(STATUS[type(report.verdict)], "PASS")

    def test_a_regulator_owes_each_of_its_ratings(self):
        report = check(written("  resistor r1 part res.0603_1pct value 237 ohm\n  resistor r2 part res.0603_1pct value 715 ohm\n"
                               "  regulator v1 part reg.lm317_to220 from vin top r1 bottom r2\n  sink s1 from v1\n",
                               after=f"\nload run {{\n  on b.s1 current in [10 mA, 100 mA]\n  {SIGNED}\n}}\n"))
        owed = {o.obligation.requirement.mode.id.split(".", 1)[1] for o in report.outcomes
                if type(o).__name__ in ("Discharged", "Refuted") and o.obligation.requirement.subject[-1] == "v1"}
        self.assertEqual(owed, {"regulator_headroom", "regulator_input", "regulator_current", "regulator_min_load",
                                "regulator_thermal"})


class Validity(unittest.TestCase):
    def test_an_led_below_its_fitted_current_is_unknown_not_pass(self):
        report = check(written("  resistor r1 part res.0603_1pct value 100 kohm\n"
                               "  led d1 part led.red_0603 from vin resistor r1\n",
                               after="\nclaim lit: b.d1.current >= 1 uA\n"))
        self.assertEqual(STATUS[type(report.verdict)], "UNKNOWN")
        self.assertIn("dc.led_range", needs(report))
        self.assertIn("led_current", modes(report, "Open"))

    def test_no_ambient_is_a_gap_naming_it(self):
        header = HEADER.replace("  environment indoor_dry\n", "")
        report = check(written("  resistor r1 part res.0603_1pct value 10 kohm from vin\n", header=header))
        self.assertEqual(STATUS[type(report.verdict)], "UNKNOWN")
        self.assertIn("ambient", needs(report))

    def test_no_capacity_leaves_the_supply_check_open(self):
        supply = f"  supply vin voltage in [11.4 V, 12.6 V] {SIGNED}\n"
        report = check(written("  resistor r1 part res.0603_1pct value 10 kohm from vin\n", supply=supply))
        self.assertEqual(modes(report, "Open"), {"supply_current"})
        self.assertIn("capacity", needs(report))

    def test_a_sink_with_no_current_leaves_what_reads_it_open(self):
        report = check(written("  regulator v1 part reg.ldo1117_3v3_sot223 from vin\n  sink s1 from v1\n"))
        self.assertEqual(STATUS[type(report.verdict)], "UNKNOWN")
        self.assertIn("current", needs(report))
        self.assertIn("regulator_current", modes(report, "Open"))


ALLOWED = {0, 1, 2}
NUMBER = re.compile(r"-?\d+(\.\d+)?(/\d+)?")
LABEL_LENGTH = ("domain", 16)
"""The premise hash keeps base.py's 16 hex digits."""


class BuilderRules(unittest.TestCase):
    """D3 to D5 of docs/principles.md, for the trusted modules here."""

    def trees(self):
        for module in domain.TRUSTED:
            yield module, ast.parse((PACKAGE / f"{module}.py").read_text(encoding="utf-8"))

    def test_no_builder_function_has_a_default_argument(self):
        for module, tree in self.trees():
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.Lambda)):
                    with self.subTest(module=module, line=node.lineno):
                        self.assertEqual(node.args.defaults, [])
                        self.assertTrue(all(d is None for d in node.args.kw_defaults))

    def test_no_builder_dataclass_field_has_a_default(self):
        for module, tree in self.trees():
            for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
                for field in cls.body:
                    if isinstance(field, ast.AnnAssign):
                        with self.subTest(module=module, field=f"{cls.name}.{ast.unparse(field.target)}"):
                            self.assertIsNone(field.value)

    def test_builder_modules_have_no_numeric_literal_but_0_1_and_2(self):
        for module, tree in self.trees():
            found = []
            for n in ast.walk(tree):
                if not isinstance(n, ast.Constant) or isinstance(n.value, bool):
                    continue
                if isinstance(n.value, (int, float)):
                    number = n.value
                elif isinstance(n.value, str) and NUMBER.fullmatch(n.value):
                    number = Fraction(n.value)
                else:
                    continue
                if number not in ALLOWED and (module, number) != LABEL_LENGTH:
                    found.append((n.lineno, n.value))
            self.assertEqual(found, [], module)

    def test_every_model_has_rows_or_says_unbounded(self):
        for spec in domain.MODEL_SPECS:
            with self.subTest(spec.id):
                self.assertNotEqual(bool(spec.rows), "Unbounded" in spec.validity)

    def test_the_premise_hash_reads_the_trusted_modules(self):
        self.assertEqual(domain.TRUSTED, ("board", "network", "domain"))
        self.assertTrue(all(spec.source_hash == domain.SOURCE_HASH for spec in domain.MODEL_SPECS))


class Gate(unittest.TestCase):
    """The gate on a small sample; scripts/electronics_gate.py runs it at size and writes
    docs/electronics_gate.md."""

    @classmethod
    def setUpClass(cls):
        cls.sample = list(gen.generate(12, 7, REGISTRY))
        cls.rows = [G.assess(g, REGISTRY, False) for g in cls.sample]

    def test_a_slice_is_the_same_whoever_draws_it(self):
        self.assertEqual([g.text for g in gen.generate(2, 7, REGISTRY, start=4)], [g.text for g in self.sample[4:6]])

    def test_every_kind_is_drawn(self):
        self.assertEqual({g.kind for g in self.sample}, set(gen.KINDS))

    def test_every_design_is_decided(self):
        self.assertEqual([(r.name, r.status, r.needs) for r in self.rows if r.status not in ("PASS", "FAIL")], [])

    def test_every_claim_lands_on_its_target(self):
        off = [(r.name, c, t, o) for r in self.rows for c, (t, o) in r.claims.items() if t != o]
        self.assertEqual(off, [])

    def test_claims_carry_the_margin(self):
        for g in self.sample:
            for c in g.claims:
                x = g.extremes[(c.subject, c.side)]
                slack = abs(c.bound - x) / x
                with self.subTest(g.name, claim=c.name):
                    self.assertGreaterEqual(slack, gen.DELTA * Fraction(99, 100))

    def test_each_fault_is_caught_and_named_in_one_base(self):
        pool = F.bases(REGISTRY, 1, 101)
        seen = set()
        for fault in F.FAULTS:
            for kind in fault.kinds:
                for g in pool[kind]:
                    base = replace(g, claims=fault.claims(g))
                    faulty = fault.edit(base, REGISTRY)
                    if fault.name in seen or faulty is None:
                        continue
                    if base.claims and F.status_and_modes(base.text, REGISTRY)[0] != "PASS":
                        continue
                    status, refuted, _ = F.status_and_modes(faulty.text, REGISTRY)
                    with self.subTest(fault.name, base=g.name):
                        self.assertEqual(status, "FAIL")
                        self.assertTrue(set(refuted) & fault.modes, refuted)
                    seen.add(fault.name)
        self.assertEqual(seen, {f.name for f in F.FAULTS})

    def test_the_published_gate_decides_everything_and_catches_every_fault(self):
        text = (ROOT / "docs" / "electronics_gate.md").read_text(encoding="utf-8")
        decided = re.search(r"\| 1\. Decidedness \| (\d+) of (\d+) PASS or FAIL; 0 UNKNOWN \|", text)
        self.assertIsNotNone(decided, "docs/electronics_gate.md reports every design decided")
        self.assertEqual(decided.group(1), decided.group(2))
        faults = re.search(r"\| 5\. Planted faults \| (\d+) of (\d+) caught \(FAIL\), (\d+) named", text)
        self.assertIsNotNone(faults)
        self.assertEqual(len(set(faults.groups())), 1, "every fault caught and named")


if __name__ == "__main__":
    unittest.main()
