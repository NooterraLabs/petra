"""The lift pilot's grading rules (scripts/pilot_lift.py, docs/pilot_lift.md): how an
adjudication turns into safe and buildable, and which designs the hand check samples."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pilot_lift  # noqa: E402
from pilot_lift import Graded, hand_sample, settle, table  # noqa: E402


def graded(arm: str = "without_petra", task: str = "303-006", status: str = "FAIL", claim: bool = True,
           uncertified: dict | None = None, judged: list | None = None) -> Graded:
    return Graded(arm, task, "shear_tab", status, uncertified=uncertified or {}, judged=judged or [], claim=claim)


class SettleTests(unittest.TestCase):
    def test_a_stricter_reading_leaves_the_design_safe(self):
        g = graded(uncertified={"steel.bolts": 1.08})
        settle(g, {"steel.bolts": {"verdict": "conservative"}})
        self.assertTrue(g.safe and g.buildable and g.ok)
        self.assertEqual(g.why_not, [])

    def test_an_open_check_that_holds_leaves_the_design_safe(self):
        g = graded(status="UNKNOWN", uncertified={"steel.spacing_max": None})
        settle(g, {"steel.spacing_max": {"verdict": "holds"}})
        self.assertTrue(g.ok)

    def test_a_real_strength_violation_is_unsafe(self):
        g = graded(uncertified={"steel.bolts": 1.3})
        settle(g, {"steel.bolts": {"verdict": "real"}})
        self.assertFalse(g.safe)
        self.assertTrue(g.buildable)
        self.assertEqual(g.why_not, ["unsafe"])

    def test_a_real_fit_violation_is_unbuildable_not_unsafe(self):
        g = graded(uncertified={"steel.beam_fit": 1.1})
        settle(g, {"steel.beam_fit": {"verdict": "real"}})
        self.assertTrue(g.safe)
        self.assertFalse(g.buildable)
        self.assertEqual(g.why_not, ["unbuildable"])

    def test_the_judge_alone_makes_a_design_unbuildable(self):
        g = graded(status="PASS", judged=["J-1 on st1: no room for the wrench"])
        settle(g, {})
        self.assertTrue(g.safe)
        self.assertFalse(g.buildable)

    def test_a_check_without_a_verdict_leaves_the_design_undecided(self):
        g = graded(uncertified={"steel.bolts": 1.08, "steel.weld": 1.2})
        settle(g, {"steel.bolts": {"verdict": "conservative"}})
        self.assertIsNone(g.safe)
        self.assertIsNone(g.ok)

    def test_a_false_pass_found_by_hand_is_unsafe(self):
        g = graded(status="PASS")
        settle(g, {"steel.weld": {"verdict": "real"}})
        self.assertFalse(g.safe)

    def test_an_unknown_verdict_word_is_not_accepted(self):
        g = graded(uncertified={"steel.bolts": 1.08})
        settle(g, {"steel.bolts": {"verdict": "fine"}})
        self.assertIsNone(g.ok)


class TableTests(unittest.TestCase):
    def test_called_safe_but_not_counts_only_designs_the_agent_called_safe(self):
        unsafe_called = graded(task="303-003", uncertified={"steel.bolts": 1.3})
        settle(unsafe_called, {"steel.bolts": {"verdict": "real"}})
        unsafe_flagged = graded(task="303-004", claim=False, uncertified={"steel.bolts": 1.3})
        settle(unsafe_flagged, {"steel.bolts": {"verdict": "real"}})
        text = table([unsafe_called, unsafe_flagged])
        self.assertIn("| Called safe but not safe and buildable | 0 of 0 | 1 of 1 |", text)
        self.assertIn("| ... a real AISC 360-22 violation | 0 of 0 | 1 of 1 |", text)


class AuditTests(unittest.TestCase):
    FOLDER = Path("C:/jobs/a/task-303-006")

    def audit(self, *commands: tuple[str, str]) -> dict:
        return pilot_lift.audit_one([(tool, {"command": c}) for tool, c in commands], self.FOLDER)

    def test_checks_count_by_path_by_variable_and_by_bare_name(self):
        found = self.audit(
            ("Bash", "cd C:/jobs/a/task-303-006 && C:/jobs/venv/Scripts/petra.exe check try1.petra"),
            ("PowerShell", '$p = "C:/jobs/venv/Scripts/petra.exe"; & $p check --json try2.petra'),
            ("Bash", "cd C:/jobs/a/task-303-006 && petra check try2.petra"))
        self.assertEqual(found["checks"], 3)
        self.assertEqual(found["checked"], {"try1.petra", "try2.petra"})

    def test_help_docs_and_file_text_are_not_checks(self):
        found = self.audit(
            ("Bash", "C:/jobs/venv/Scripts/petra.exe check --help"),
            ("Bash", "C:/jobs/venv/Scripts/petra.exe docs skill"),
            ("Bash", "cat > C:/jobs/a/task-303-006/try1.petra <<'EOF'\npetra 0\nEOF"),
            ("Bash", "cp C:/jobs/a/task-303-006/try4.petra C:/jobs/a/task-303-006/final.petra"))
        self.assertEqual(found["checks"], 0)
        self.assertEqual(sorted(set(found["petra_commands"])), ["check", "docs"])

    def test_imports_installs_and_outside_paths_are_reported(self):
        found = self.audit(
            ("Bash", "python -c 'import petra'"),
            ("Bash", "pip install petra"),
            ("Bash", "cat C:/Users/aiden/OneDrive/Desktop/LoLa/petra/loop.py"))
        self.assertEqual(len(found["imports"]), 1)
        self.assertEqual(len(found["installs"]), 1)
        self.assertEqual(found["outside"], ["Bash: C:/Users/aiden/OneDrive/Desktop/LoLa/petra/loop.py"])


class SampleTests(unittest.TestCase):
    def test_the_pilot_sample_is_reproducible(self):
        tasks = ["303-003", "303-004", "303-005", "303-006", "303-014",
                 "303-015", "303-018", "303-019", "303-021", "303-022"]
        failing = {"303-003", "303-006", "303-022"}
        rows = [graded("with_petra", t, "PASS") for t in tasks]
        rows += [graded("without_petra", t, "FAIL" if t in failing else "PASS") for t in tasks]
        self.assertEqual(hand_sample(rows), [
            "without_petra/303-003", "without_petra/303-006", "without_petra/303-022",
            "with_petra/303-003", "with_petra/303-006",
            "without_petra/303-005", "without_petra/303-019"])
        self.assertEqual(pilot_lift.SEED, 303)


if __name__ == "__main__":
    unittest.main()
