"""The shipped examples, end to end through `python -m petra`.

Each example's header says what it shows, and its name says its verdict: lap_pass passes on the
waivers of its card, lap_fail is refuted, and lap_unknown has lines the deck has no rule for.
The status and the exit code are the kernel's.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "examples/deck/lap_pass.petra": ("PASS_WAIVED", 6),
    "examples/deck/lap_fail.petra": ("FAIL", 1),
    "examples/deck/lap_unknown.petra": ("UNKNOWN", 2),
}


def petra(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "petra", *argv], cwd=ROOT, capture_output=True, text=True, timeout=600)


class Examples(unittest.TestCase):
    def test_every_example_is_listed_here(self):
        self.assertEqual(sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "examples").rglob("*.petra")), sorted(EXPECTED))

    def test_each_example_gets_its_expected_verdict(self):
        for path, (status, code) in EXPECTED.items():
            with self.subTest(path=path):
                done = petra("check", path, "--json")
                self.assertEqual(done.returncode, code, f"{path} exits {code}: {done.stderr}")
                report = json.loads(done.stdout)
                self.assertEqual((report["status"], report["file"], report["path"]), (status, path, "rules"))
                self.assertEqual(report["kernel"]["cells_from"], "rules", "the kernel worked out the cells from the deck")
                states = {c["state"] for c in report["cells"]}
                self.assertEqual("refuted" in states, status == "FAIL")
                self.assertEqual("open" in states or "refuted" in states, status != "PASS_WAIVED")
                for cell in report["cells"]:
                    self.assertTrue(cell["anchor"], f"{path} {cell['mechanism']} names its clause")
                    if cell["state"] in ("proved", "refuted") and not cell["entry"].endswith("/where"):
                        self.assertTrue(cell["rule"], f"{path} {cell['mechanism']} names the rule that settled it")

    def test_the_text_of_each_example_starts_with_its_verdict(self):
        for path, (status, code) in EXPECTED.items():
            with self.subTest(path=path):
                done = petra("check", path)
                self.assertEqual(done.returncode, code)
                self.assertTrue(done.stdout.splitlines()[0].endswith(f": {status}"), done.stdout.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
