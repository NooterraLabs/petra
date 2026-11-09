"""Clause traceability of the steel deck (docs/steel_connections.md §6, §9 item 1): every
AISC 360-22 Chapter J and K provision and every Appendix 3 provision maps to exactly one
check, rule, premise or exclusion; every mode the deck has is named by a provision; the
published table is current."""
import itertools
import unittest
from pathlib import Path

from petra.models.steel import trace
from petra.models.steel.vocab import MODELS, MODES, UNMODELLED

DOC = Path(__file__).resolve().parents[1] / "docs" / "steel_traceability.md"
PLAN = DOC.parent / "steel_connections.md"


class Traceability(unittest.TestCase):
    def test_every_provision_is_mapped_once_in_order(self):
        self.assertEqual([(p.section, p.title) for p in trace.TABLE], list(trace.SPEC_SECTIONS))

    def test_every_appendix3_provision_is_mapped_once_in_order(self):
        self.assertEqual([(p.section, p.title) for p in trace.APPENDIX3], list(trace.APPENDIX3_SECTIONS))

    def test_every_treatment_is_known_and_explained(self):
        for p in trace.ALL:
            with self.subTest(p.section):
                self.assertIn(p.treatment, trace.TREATMENTS)
                if p.treatment == "check":
                    self.assertTrue(p.modes, "a check names its modes")
                else:
                    self.assertTrue(p.note, "a rule, premise or exclusion says what it is")

    def test_named_modes_exist(self):
        known = {*MODES, *(m.id.removeprefix("steel.") for m in UNMODELLED)}
        for p in trace.ALL:
            for mode in p.modes:
                self.assertIn(mode, known, p.section)

    def test_every_mode_of_the_deck_is_traced(self):
        named = {m for p in trace.ALL if p.treatment == "check" for m in p.modes}
        self.assertEqual(set(MODES) - named, set())

    def test_premises_naming_a_mode_are_stated_in_its_model(self):
        """A premise row that names a mode points at a model whose statement carries it."""
        for p in (*trace.TABLE, *trace.APPENDIX3):
            if p.treatment == "premise" and p.modes:
                for mode in p.modes:
                    spec = MODELS[MODES[mode]]
                    self.assertTrue(spec.validity or spec.unchecked, f"{p.section}: {mode}")

    def test_the_clause_plan_calls_no_excluded_section_encoded_today(self):
        """docs/steel_connections.md §4 marks a later version's work "(v1.1)" or "(v1.2)",
        so a section this table excludes is never called encoded there without one."""
        excluded = {p.section for p in trace.TABLE if p.treatment == "excluded"}
        lines = PLAN.read_text(encoding="utf-8").split("\n## 4.", 1)[1].splitlines()[1:]
        for line in itertools.takewhile(lambda line: not line.startswith("#"), lines):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 3 and cells[0] in excluded:
                with self.subTest(cells[0]):
                    self.assertFalse("encoded" in cells[2].lower() and "(v1." not in cells[2], cells[2])

    def test_the_published_table_is_current(self):
        self.assertEqual(DOC.read_text(encoding="utf-8"), trace.render(),
                         "docs/steel_traceability.md is stale: run python -m petra.models.steel.trace")


if __name__ == "__main__":
    unittest.main()
