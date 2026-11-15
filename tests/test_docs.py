"""The public pages stay true to the tree and to what Petra prints.

No page names a file that is not there: the old path was deleted on 2026-11-15, and a page that
still pointed at one of its files would describe a checker that does not exist (plan step R1).
The README's quickstart runs as written, from an empty directory, and its design reads UNKNOWN
with five lines open.
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
BASH = re.compile(r"^```bash\n(?P<code>.*?)^```$", re.M | re.S)
PAGES = sorted([README, ROOT / "CONTRIBUTING.md", *(ROOT / "docs").glob("*.md"), *(ROOT / "petra" / "docs").glob("*.md"), ROOT / "kernel" / "README.md"])
TOPS = ("petra", "kernel", "proofs", "tests", "bench", "corpus", "docs", "examples", "scripts", "plugins", "_build")
"""The folders of the tree a page may name a file of."""
BUILT = ("petra/bin/", "kernel/.lake/")
"""Where a build puts the kernel. A page names these, and a clean tree has neither."""
NAMED = re.compile(r"`((?:%s)/[A-Za-z0-9_./-]+)`" % "|".join(TOPS))
DESIGNS = re.compile(r"\b((?:examples|corpus/cases)/[A-Za-z0-9_/.-]+\.(?:petra|card))\b")
LINK = re.compile(r"\]\(([^)\s]+)\)")

# A reader has no kernel named in the environment but the one under test, and the only Petra on the path is the one under test.
ENV = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
ENV["PYTHONPATH"] = str(ROOT)


def missing(page: Path) -> list[str]:
    """Each file a page names in backticks by its path from the root, or links to by a relative path, that is not in the tree."""
    text = page.read_text(encoding="utf-8")
    out = []
    for name in NAMED.findall(text):
        path = name.rstrip(".,")
        if path.startswith(BUILT):      # what a build puts in the tree
            continue
        if not (ROOT / path).exists() and not list(ROOT.glob(path + "*")):      # a name may be the start of several: `tests/test_kernel_attacks`
            out.append(name)
    for name in DESIGNS.findall(text):      # a design or a card named anywhere, in a command of a code block too
        if not (ROOT / name).exists():
            out.append(name)
    for target in LINK.findall(text):
        if target.startswith(("https://", "http://", "#", "mailto:")):
            continue
        if not (page.parent / target.split("#", 1)[0]).exists():
            out.append(target)
    return sorted(set(out))


class Pages(unittest.TestCase):
    def test_no_page_names_a_file_that_is_not_there(self):
        self.assertGreater(len(PAGES), 8)
        for page in PAGES:
            with self.subTest(page=str(page.relative_to(ROOT))):
                self.assertEqual(missing(page), [])

    def test_a_missing_file_is_caught(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "docs") as tmp:
            page = Path(tmp, "page.md")
            page.write_text("See `petra/models/steel/calc.py`, `petra/grid.py` and [the plan](../plan.md), and [this](../design.md#the-verdict).\n"
                            "```bash\npetra check examples/circuit_pass.petra\npetra check examples/deck/lap_pass.petra\n```\n", encoding="utf-8")
            self.assertEqual(missing(page), ["../plan.md", "examples/circuit_pass.petra", "petra/models/steel/calc.py"])


class Readme(unittest.TestCase):
    text = README.read_text(encoding="utf-8")

    def test_the_quickstart_runs_as_written_and_its_design_is_unknown_with_five_lines_open(self):
        """The card `petra new lap --card` prints signs no waiver (tests/test_kernel_attacks12.py, Q): the
        quickstart's lap reads UNKNOWN, and the README says so."""
        commands = [line for m in BASH.finditer(self.text) for line in m["code"].splitlines()
                    if line.strip() and not line.startswith("pip install")]
        self.assertEqual([c.split()[0] for c in commands], ["petra"] * len(commands), "the quickstart runs only petra")
        with tempfile.TemporaryDirectory() as empty:
            for command in commands:
                shell = f'"{sys.executable}" -m petra' + command.removeprefix("petra")
                done = subprocess.run(shell, shell=True, cwd=empty, env=ENV, capture_output=True, text=True, timeout=300)
                self.assertEqual(done.returncode, 2 if command == commands[-1] else 0, f"{command}\n{done.stderr}")
        self.assertEqual(commands[-1].split()[:2], ["petra", "check"])
        self.assertTrue(done.stdout.splitlines()[0].endswith(": UNKNOWN"), done.stdout)
        lines = [line for line in done.stdout.splitlines() if line.startswith("  splice/")]
        self.assertEqual((sum(" open " in line for line in lines), sum(" waived " in line for line in lines)), (5, 0), "the README says five open, and no waiver")

    def test_no_word_is_in_capitals(self):
        prose = re.sub(r"\]\([^)]*\)", "]", self.text)
        self.assertEqual(re.findall(r"\b[A-Z]{2,}\b", prose), [], "link targets are file names and may keep their case")


if __name__ == "__main__":
    unittest.main()
