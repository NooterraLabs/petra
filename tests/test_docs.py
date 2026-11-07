"""The docs' examples stay true to the shipped files and to what Petra prints.

The README's quickstart runs as written, from an empty directory, and its design passes.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN = (ROOT / "docs" / "design.md").read_text(encoding="utf-8")
README = ROOT / "README.md"
BASH = re.compile(r"^```bash\n(?P<code>.*?)^```$", re.M | re.S)

# A reader has no shapes workbook, and the only Petra on the path is the one under test.
ENV = {k: v for k, v in os.environ.items() if k not in ("PETRA_SHAPES_XLSX", "PYTHONPATH")}
ENV["PYTHONPATH"] = str(ROOT)


def json_block_after(heading: str) -> object:
    start = DESIGN.index(heading)
    a = DESIGN.index("```json\n", start) + len("```json\n")
    return json.loads(DESIGN[a:DESIGN.index("\n```", a)])


class DesignDoc(unittest.TestCase):
    def test_the_certificate_example_is_the_shipped_certificate(self):
        shipped = json.loads((ROOT / "examples" / "bolt_tension.cert.json").read_text(encoding="utf-8"))
        self.assertEqual(json_block_after("## Certificate JSON format"), shipped,
                         "docs/design.md must show examples/bolt_tension.cert.json verbatim")

    def test_a_drifted_certificate_example_is_caught(self):
        shipped = json.loads((ROOT / "examples" / "bolt_tension.cert.json").read_text(encoding="utf-8"))
        drifted = {**shipped, "statement_hash": "sha256:" + "0" * 64}
        self.assertNotEqual(json_block_after("## Certificate JSON format"), drifted)

    def test_every_example_file_the_doc_names_exists(self):
        named = set(re.findall(r"examples/[\w/]+\.(?:petra|json)", DESIGN))
        self.assertTrue(named, "the doc names example files")
        missing = sorted(p for p in named if not (ROOT / p).exists())
        self.assertEqual(missing, [], "docs/design.md names example files that do not exist")


class Readme(unittest.TestCase):
    text = README.read_text(encoding="utf-8")

    def test_the_quickstart_runs_as_written_and_its_design_passes(self):
        commands = [line for m in BASH.finditer(self.text) for line in m["code"].splitlines()
                    if line.strip() and not line.startswith("pip install")]
        self.assertEqual([c.split()[0] for c in commands], ["petra"] * len(commands), "the quickstart runs only petra")
        with tempfile.TemporaryDirectory() as empty:
            for command in commands:
                shell = f'"{sys.executable}" -m petra' + command.removeprefix("petra")
                done = subprocess.run(shell, shell=True, cwd=empty, env=ENV, capture_output=True, text=True, timeout=300)
                self.assertEqual(done.returncode, 0, f"{command}\n{done.stderr}")
        self.assertTrue(done.stdout.splitlines()[0].endswith(": PASS"), done.stdout)

    def test_no_word_is_in_capitals(self):
        prose = re.sub(r"\]\([^)]*\)", "]", self.text)
        self.assertEqual(re.findall(r"\b[A-Z]{2,}\b", prose), [], "link targets are file names and may keep their case")


if __name__ == "__main__":
    unittest.main()
