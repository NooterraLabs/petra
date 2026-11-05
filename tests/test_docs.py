"""The design doc's worked examples stay true to the shipped files."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN = (ROOT / "docs" / "design.md").read_text(encoding="utf-8")


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
        named = set(re.findall(r"examples/[\w/]+\.(?:lola|json)", DESIGN))
        self.assertTrue(named, "the doc names example files")
        missing = sorted(p for p in named if not (ROOT / p).exists())
        self.assertEqual(missing, [], "docs/design.md names example files that do not exist")


if __name__ == "__main__":
    unittest.main()
