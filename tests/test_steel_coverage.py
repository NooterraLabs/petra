"""Steel coverage from the physics (docs/plan.md P1 item 5): what a connection's parts can
fail by is demanded, or its reason for not arising is recorded, whatever loads the design
declares.
"""
import tempfile
import unittest
from pathlib import Path

import petra

ROOT = Path(__file__).resolve().parents[1]
STEEL = ROOT / "examples" / "steel"


def written(text: str):
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "design.petra"
        target.write_text(text, encoding="utf-8", newline="\n")
        return petra.check_file(target)


def checks(report, mode: str) -> list[str]:
    return [c["check"] for v in report.to_json()["verdicts"] for o in v["obligations"] if f"/steel.{mode}/" in o["requirement"]
            for c in o["checks"]]


def outcome(report, mode: str) -> str:
    (found,) = {o["outcome"] for v in report.to_json()["verdicts"] for o in v["obligations"] if f"/steel.{mode}/" in o["requirement"]}
    return found


class MaximumSpacing(unittest.TestCase):
    """J3.6 limits the longitudinal spacing of bolts, the pitch along a bolt line, at 24 t
    and 12 in; it says nothing of the gauge across the force (Commentary J3.6). A 1/4 in end
    plate allows 6 in."""

    END_PLATE = (STEEL / "shear_end_plate.petra").read_text(encoding="utf-8")

    def test_a_gauge_past_24_t_is_not_held_to_it(self):
        wide = written(self.END_PLATE.replace("support_gauge 5.5 inch", "support_gauge 6.5 inch").replace(
            "plate_width 8 inch", "plate_width 9 inch"))
        self.assertEqual(outcome(wide, "spacing_max"), "certified")
        self.assertFalse([c for c in checks(wide, "spacing_max") if "gauge" in c])

    def test_a_pitch_past_24_t_fails(self):
        tall = written(self.END_PLATE.replace("pitch 3 inch", "pitch 6.5 inch").replace("rows 4", "rows 2"))
        self.assertEqual(outcome(tall, "spacing_max"), "refuted")


class PanelZone(unittest.TestCase):
    """A flange force may be one flange of a moment connection's couple, which shears the
    column's panel zone (J10.6) whatever loads the design declares. The check reads the
    panel's required shear and the column's axial force, neither of which the force gives:
    left out, each leaves the panel zone open by name, never unchecked or taken as zero."""

    FORCE = (STEEL / "flange_force.petra").read_text(encoding="utf-8")

    def loaded(self, *lines: str):
        return written(self.FORCE.replace("  signed ", "".join(f"  {line}\n" for line in lines) + "  signed ", 1))

    def test_a_force_with_neither_load_leaves_the_panel_zone_open_naming_both(self):
        report = written(self.FORCE)
        self.assertIsInstance(report.verdict, petra.Unknown)
        self.assertEqual(outcome(report, "panel_zone"), "open")
        text = report.render()
        for field in ("panel_shear", "axial"):
            self.assertIn(f"needs signed bound on ff1.{field} [kip]", text)

    def test_each_load_left_out_is_named_alone(self):
        for given, missing in (("on ff1 panel_shear in [0 kip, 100 kip]", "axial"), ("on ff1 axial in [0 kip, 300 kip]", "panel_shear")):
            with self.subTest(missing=missing):
                text = self.loaded(given).render()
                self.assertIn(f"needs signed bound on ff1.{missing} [kip]", text)
                self.assertEqual(text.count("needs signed bound"), 1, text)

    def test_with_both_the_panel_zone_is_checked(self):
        report = self.loaded("on ff1 panel_shear in [0 kip, 100 kip]", "on ff1 axial in [0 kip, 300 kip]")
        self.assertIsInstance(report.verdict, petra.Pass)
        self.assertEqual(outcome(report, "panel_zone"), "certified")

    def test_a_tensile_axial_force_reduces_the_web_as_a_compressive_one_does(self):
        # W14x90: Py = 50 ksi x 26.5 in2 = 1325 kip; 1000 kip is past 0.4 Py, so Eq J10-10 applies.
        def utilisation(axial: str) -> float:
            report = self.loaded("on ff1 panel_shear in [0 kip, 300 kip]", f"on ff1 axial in {axial}")
            (u,) = [c["utilisation"] for v in report.to_json()["verdicts"] for o in v["obligations"]
                    if "/steel.panel_zone/" in o["requirement"] for c in o["checks"]]
            return u
        dc, tw, fy, py = 14.0, 0.44, 50.0, 50.0 * 26.5
        expected = 300 / (0.9 * 0.6 * fy * dc * tw * (1.4 - 1000 / py))
        self.assertAlmostEqual(utilisation("[0 kip, 1000 kip]"), expected, places=3)
        self.assertAlmostEqual(utilisation("[-1000 kip, 0 kip]"), expected, places=3)


if __name__ == "__main__":
    unittest.main()
