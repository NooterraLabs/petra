"""Where a check stopped (petra/readout.py, plan P1 item 6): every check a guard of its
clause excuses says so, with the condition and its numbers, and every mode a
component's domain declares that no requirement names on it is listed with the reason
the coverage table gives.

Cold-start agents found both silent: flange_force.petra passes with its sidesway
buckling check excused and a blank utilisation, and with no panel-zone check because it
declares no panel_shear load; a shear tee lists steel.ductility and steel.prying in its
vocabulary and no obligation demands them.
"""
import dataclasses
import re
import tempfile
import unittest
from pathlib import Path

import petra
from petra import models, readout
from petra.pipeline import Report

ROOT = Path(__file__).resolve().parents[1]
STEEL = ROOT / "examples" / "steel"
FLANGE_FORCE = STEEL / "flange_force.petra"
SHEAR_TEE = STEEL / "shear_tee.petra"
HANGER = STEEL / "hanger.petra"
TRUSS_PASS = ROOT / "examples" / "truss_pass.petra"
DESIGNS = sorted([*(ROOT / "examples").rglob("*.petra"), *(ROOT / "judges" / "canaries").glob("*.petra"),
                  *(ROOT / "tests" / "fixtures").rglob("*.petra")])
SIDESWAY = "member web: web sidesway buckling where its slenderness ratio makes it apply (J10.4)"

# A W14x90 (AISC Shapes Database v16.0) as flange_force.petra loads it, Lb = 144 in.
D, KDES, TW, BF, LB = 14.0, 1.31, 0.44, 14.5, 144.0

_REPORTS: dict[Path, Report] = {}


def check(path: Path) -> Report:
    if path not in _REPORTS:
        _REPORTS[path] = petra.check_file(path)
    return _REPORTS[path]


def edge(text: str, head: str) -> list[str]:
    return [line for line in text.split("\n") if line.startswith(head)]


def with_load(path: Path, line: str) -> Report:
    """The design at `path` with one more entry in its load block."""
    text = path.read_text(encoding="utf-8")
    added = re.sub(r"^(\s*)signed ", rf"\g<1>{line}\n\g<1>signed ", text, count=1, flags=re.M)
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / path.name
        target.write_text(added, encoding="utf-8", newline="\n")
        return petra.check_file(target)


def written(text: str) -> Report:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "design.petra"
        target.write_text(text, encoding="utf-8", newline="\n")
        return petra.check_file(target)


END_FORCE = """petra 0

design "flange-force-near-the-end" {
  owner "s.engineer@example.org"
}

flange_force ff1 {
  basis lrfd
  member W14x90 grade steel.A992
  bearing_length 0.5 inch
  location end
  distance in [16 inch, 30 inch] signed "s.engineer@example.org" source "framing plan"
  force_kind compressive
  flange_restrained yes
  unbraced_length 144 inch
  moment_at_force below_yield
}

load gravity {
  on ff1 force in [0 kip, 400 kip]
  on ff1 panel_shear in [0 kip, 50 kip]
  on ff1 axial in [0 kip, 100 kip]
  signed "s.engineer@example.org" source "beam reaction"
}
"""


class Excused(unittest.TestCase):
    def test_the_sidesway_check_says_which_ratio_excuses_it(self):
        report = check(FLANGE_FORCE)
        (line,) = edge(report.render(), "excused    ")
        self.assertTrue(line.startswith(f"excused    ff1/steel.web_sidesway_buckling: {SIDESWAY}: "), line)
        found = re.search(r"/ W14x90.bf\) = ([0-9.]+) >= j10_4.restrained_limit \+ strict.ratio = ([0-9.]+)$", line)
        self.assertIsNotNone(found, line)
        ratio, limit = map(float, found.groups())
        self.assertAlmostEqual(ratio, ((D - 2 * KDES) / TW) / (LB / BF), places=3)
        self.assertEqual(limit, 2.3)
        self.assertGreater(ratio, limit)

    def test_a_row_every_guard_excuses_says_excused(self):
        row = next(line for line in check(FLANGE_FORCE).render().split("\n") if line.startswith("  ff1/steel.web_sidesway_buckling "))
        self.assertTrue(row.endswith("  excused"), row)

    def test_every_excused_check_says_why_and_no_other_does(self):
        seen = 0
        for path in DESIGNS:
            listed = [c for v in check(path).to_json()["verdicts"] for o in v["obligations"] for c in o["checks"]]
            for c in listed:
                with self.subTest(path=path.name, check=c["check"]):
                    self.assertEqual(c["excuse"] is not None, c["excused"])
                    seen += c["excused"]
        self.assertGreater(seen, 10, "the examples excuse checks")

    def test_an_excuse_is_read_at_the_counterexample(self):
        report = written(END_FORCE)
        self.assertIsInstance(report.verdict, petra.Fail)
        (f,) = [f for f in report.findings if f.requirement.startswith("ff1/steel.web_local_yielding/")]
        self.assertEqual((f.outcome, f.at), ("refuted", "point"))
        (at,) = [c for c in f.point if c.label.endswith(".ff1.distance")]
        (excused,) = [v for v in f.values if v.excused]
        self.assertEqual(excused.what, "member web: web local yielding within d of the member end (J10.2)")
        self.assertEqual(excused.excuse, f"ff1.distance = {readout._number(float(at.exact / readout._factor('inch')))} inch "
                                         f">= W14x90.d + strict.length = 14 inch")

    def test_over_the_box_an_excuse_gives_the_range(self):
        report = written(END_FORCE.replace("[0 kip, 400 kip]", "[0 kip, 100 kip]"))
        self.assertIsInstance(report.verdict, petra.Pass)
        (f,) = [f for f in report.findings if f.requirement.startswith("ff1/steel.web_crippling/")]
        (excused,) = [v for v in f.values if v.excused]
        self.assertEqual(f.at, "box")
        self.assertEqual(excused.excuse, "ff1.distance = 16 to 30 inch >= W14x90.d / 2 = 7 inch")

    def test_the_same_check_excused_twice_prints_once(self):
        lines = edge(check(STEEL / "shear_end_plate.petra").render(), "excused    ")
        (line,) = [line for line in lines if line.startswith("excused    ep1/steel.fillet_size: ")]
        self.assertEqual(line.count("<= j2_2b.t"), 3, line)


class NotChecked(unittest.TestCase):
    def test_the_panel_zone_is_demanded_and_names_the_loads_it_reads(self):
        report = check(FLANGE_FORCE)
        self.assertFalse([u for u in report.unchecked if u.mode == "steel.panel_zone"])
        (open_,) = [o for v in report.to_json()["verdicts"] for o in v["obligations"] if "/steel.panel_zone/" in o["requirement"]]
        self.assertEqual(open_["outcome"], "open")
        text = report.render()
        for field in ("panel_shear", "axial"):
            self.assertIn(f"needs signed bound on ff1.{field} [kip]", text)

    def test_declaring_the_named_load_demands_the_mode(self):
        for path, line in ((SHEAR_TEE, "on tee1 axial in [0 kip, 5 kip]"), (HANGER, "on h1 shear in [0 kip, 5 kip]")):
            report = check(path)
            field = line.split()[2]
            named = {u.mode for u in report.unchecked if u.reason == f"no {field} load is declared; one would demand it"}
            with self.subTest(path=path.name):
                self.assertTrue(named)
                loaded = with_load(path, line)
                demanded = {r.mode.id for r in map(readout._requirement, loaded.outcomes)}
                self.assertLessEqual(named, demanded)
                self.assertFalse(named & {u.mode for u in loaded.unchecked})

    def test_a_shear_tee_says_ductility_and_prying_are_not_demanded(self):
        report = check(SHEAR_TEE)
        for mode in ("steel.ductility", "steel.prying"):
            self.assertIn(readout.Unchecked("tee1", mode, readout.NOT_DEMANDED), report.unchecked)
        (line,) = [line for line in edge(report.render(), "not checked  ") if line.endswith(readout.NOT_DEMANDED)]
        self.assertRegex(line, r"\bsteel\.ductility\b.*\bsteel\.prying\b.* on tee1: ")

    def test_a_mode_only_a_claim_demands_says_so(self):
        report = check(TRUSS_PASS)
        self.assertEqual(report.unchecked, (readout.Unchecked("frame", "truss.compliance", readout.CLAIM_ONLY),))

    def test_every_domain_mode_no_requirement_names_is_listed_once(self):
        for path in DESIGNS:
            report = check(path)
            with self.subTest(path=path.name):
                named = {(r.subject[0], r.mode.id) for r in map(readout._requirement, report.outcomes)}
                declared = {(name, m.id) for name, c in report.ir.components.items() for m in models.KINDS[c.kind].modes}
                listed = [(u.subject, u.mode) for u in report.unchecked]
                self.assertEqual(len(listed), len(set(listed)))
                self.assertEqual(set(listed), declared - named)
                self.assertEqual(report.to_json()["unchecked"], [u.to_json() for u in report.unchecked])

    def test_components_alike_share_a_line(self):
        text = FLANGE_FORCE.read_text(encoding="utf-8")
        block = text[text.index("flange_force ff1 {"):text.index("}", text.index("flange_force ff1 {")) + 1]
        twice = text.replace(block, f"{block}\n\n{block.replace('ff1', 'ff2')}").replace(
            "  signed ", "  on ff2 force in [0 kip, 150 kip]\n  signed ")
        lines = edge(written(twice).render(), "not checked  ")
        self.assertTrue(lines)
        for line in lines:
            self.assertRegex(line, r" on ff1, ff2: ")

    def test_a_report_without_its_design_lists_nothing(self):
        bare = dataclasses.replace(check(FLANGE_FORCE), ir=None, registry=None)
        self.assertEqual(bare.unchecked, ())


if __name__ == "__main__":
    unittest.main()
