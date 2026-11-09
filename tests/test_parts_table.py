"""The parts layer's one rule table holds together, and every preset row it reads names
its source (docs/parts.md). Owner: P."""
import importlib
import pkgutil
import unittest
from fractions import Fraction

MODULES = ("mesh", "space", "exact", "rules", "lower", "engine", "build", "domain")
LABELS = ("reported:", "inferred:", "guess:")

# Which features each rule family may apply to: a rule's id names what it checks.
FAMILIES = {
    "fit": {"MOVER", "BODY", "GAP", "FASTEN", "PRESS", "HOLE"},
    "insert": {"INSERT_HOLE"},
    "part": {"POLYMER"},
    "print": {"PRINT"},
    "powder": {"POWDER"},
    "sheet": {"SHEET"},
    "mill": {"MILL"},
    "parts": {"CLAIM"},
}


class Table(unittest.TestCase):
    def test_every_module_loads(self):
        import petra.models.parts as parts

        on_disk = {info.name for info in pkgutil.iter_modules(parts.__path__)}
        self.assertEqual(on_disk, set(MODULES))
        for name in MODULES:
            with self.subTest(module=name):
                importlib.import_module(f"petra.models.parts.{name}")

    def test_the_domain_is_registered_and_derives_from_the_table(self):
        import petra.models as models
        from petra.models.parts import DOMAIN, build
        from petra.models.parts.rules import RULES, Evaluator

        self.assertIn(DOMAIN, models._REGISTERED)
        modelled = {r.id for r in RULES if r.evaluator is not Evaluator.UNMODELLED}
        self.assertEqual(set(build.BUILDERS), modelled)
        self.assertEqual({m.id for m in DOMAIN.unmodelled}, {r.id for r in RULES} - modelled)
        self.assertEqual(set(build.MODELS), set(Evaluator) - {Evaluator.UNMODELLED})

    def test_each_rule_applies_where_its_family_says(self):
        from petra.models.parts.rules import RULES

        for rule in RULES:
            with self.subTest(rule=rule.id):
                self.assertIn(rule.applies.name, FAMILIES[rule.id.split(".")[0]])
                self.assertTrue(rule.text)

    def test_every_process_kind_has_a_modelled_rule(self):
        from petra.models.parts.rules import RULES, Applies, Evaluator

        for applies in (Applies.PRINT, Applies.POWDER, Applies.SHEET, Applies.MILL):
            with self.subTest(kind=applies.name):
                self.assertTrue([r for r in RULES if r.applies is applies])
        for applies in (Applies.PRINT, Applies.POWDER, Applies.SHEET):
            with self.subTest(kind=applies.name):
                self.assertTrue([r for r in RULES if r.applies is applies and r.evaluator is not Evaluator.UNMODELLED])


class Sources(unittest.TestCase):
    def test_every_preset_row_is_labelled_with_its_source(self):
        from petra.registry import parts

        rows = {**parts.presets(), **parts.finishes(), **parts.polymers(), **parts.fasteners(), **parts.inserts()}
        for id, row in rows.items():
            for prop, stated in row.props.items():
                with self.subTest(row=id, prop=prop):
                    self.assertTrue(stated.standard.startswith(LABELS), stated.standard)
        for name, constant in parts.constants().items():
            with self.subTest(constant=name):
                self.assertTrue(constant.source.startswith(LABELS), constant.source)

    def test_the_milling_preset_holds_a_shop_tolerance(self):
        # Shops publish +/-0.1 to +/-0.13 mm for standard milling (gap audit row E-138);
        # the scaffold's 0.05 mm was a precision shop's number and passed fits that bind.
        from petra.registry import parts

        tol = parts.presets()["process.mill.al6061_3axis"].props["tolerance"]
        self.assertGreaterEqual(tol.value.lo, Fraction(1, 10000))
        self.assertTrue(tol.standard.startswith("reported:"))


if __name__ == "__main__":
    unittest.main()
