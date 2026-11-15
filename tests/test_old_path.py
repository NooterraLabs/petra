"""docs/old_path_removal.md stays true to the tree (plan step 1.2a).

scripts/old_path.py copies petra/, removes every file the list deletes, cuts the imports of
removed modules out of the files that stay, and imports the readers that stay from the copy.
It exits 1 when a file of petra/ is not on the list, or is on it twice, or when one of the
seven modules does not import. So a file added to petra/ fails here until the list says
what becomes of it. A test or a script that comes to import other files of petra/ fails
here too, until `python scripts/old_path.py --write` has written the list's last column again.
"""
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TheList(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.done = subprocess.run([sys.executable, str(ROOT / "scripts" / "old_path.py")], cwd=ROOT, capture_output=True, text=True, timeout=600)
        cls.lines = cls.done.stdout.splitlines()

    def test_the_list_names_every_file_and_the_readers_that_stay_import_without_the_old_path(self):
        self.assertEqual(self.done.returncode, 0, self.done.stdout[-2000:] + self.done.stderr[-2000:])
        self.assertIn("4. 7 of 7 modules import from the copy", self.lines)

    def test_the_page_states_the_counts_the_script_prints(self):
        page = (ROOT / "docs" / "old_path_removal.md").read_text(encoding="utf-8")
        first = next(line for line in self.lines if line.startswith("1. "))
        total, delete, keep, rewrite = (int(n) for n in re.findall(r"\d+", first.split(";")[0])[1:])
        self.assertIn(f"Of the {total} files of `petra/`: {delete} delete, {keep} keep, {rewrite} rewrite.", page)
        cut = next(line for line in self.lines if line.startswith("3. cut ")).split()[2]
        later = next(line for line in self.lines if line.startswith("5. ")).split()[1]
        self.assertIn(f"- {cut} imports are cut at module level", page)
        self.assertIn(f"- {later} imports inside functions of the files that stay name a removed module", page)

    def test_the_last_column_and_the_counts_of_tests_are_what_the_tree_imports_today(self):
        stale = subprocess.run([sys.executable, str(ROOT / "scripts" / "old_path.py"), "--stale"], cwd=ROOT, capture_output=True, text=True, timeout=600)
        self.assertEqual(stale.returncode, 0, stale.stdout + stale.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
