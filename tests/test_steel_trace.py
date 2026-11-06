"""Clause traceability of the steel deck (docs/steel_connections.md §6, §9 item 1): every
AISC 360-22 Chapter J and K provision maps to exactly one check, rule, premise or exclusion;
every mode the deck has is named by a provision; the published table is current."""
import unittest
from pathlib import Path

from petra.models.steel import trace
from petra.models.steel.vocab import MODELS, MODES

DOC = Path(__file__).resolve().parents[1] / "docs" / "steel_traceability.md"


class Traceability(unittest.TestCase):
    def test_every_provision_is_mapped_once_in_order(self):
        self.assertEqual([(p.section, p.title) for p in trace.TABLE], list(trace.SPEC_SECTIONS))

    def test_every_treatment_is_known_and_explained(self):
        for p in (*trace.TABLE, *trace.OTHER):
            with self.subTest(p.section):
                self.assertIn(p.treatment, trace.TREATMENTS)
                if p.treatment == "check":
                    self.assertTrue(p.modes, "a check names its modes")
                else:
                    self.assertTrue(p.note, "a rule, premise or exclusion says what it is")

    def test_named_modes_exist(self):
        known = {*MODES, "load_path"}
        for p in (*trace.TABLE, *trace.OTHER):
            for mode in p.modes:
                self.assertIn(mode, known, p.section)

    def test_every_mode_of_the_deck_is_traced(self):
        named = {m for p in (*trace.TABLE, *trace.OTHER) if p.treatment == "check" for m in p.modes}
        self.assertEqual(set(MODES) - named, set())

    def test_premises_naming_a_mode_are_stated_in_its_model(self):
        """A premise row that names a mode points at a model whose statement carries it."""
        for p in trace.TABLE:
            if p.treatment == "premise" and p.modes:
                for mode in p.modes:
                    spec = MODELS[MODES[mode]]
                    self.assertTrue(spec.validity or spec.unchecked, f"{p.section}: {mode}")

    def test_the_published_table_is_current(self):
        self.assertEqual(DOC.read_text(encoding="utf-8"), trace.render(),
                         "docs/steel_traceability.md is stale: run python -m petra.models.steel.trace")


if __name__ == "__main__":
    unittest.main()
