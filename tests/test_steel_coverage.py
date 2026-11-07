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


if __name__ == "__main__":
    unittest.main()
