"""The parts scaffold loads, and its one table holds together (docs/parts.md)."""
import importlib
import pkgutil
import unittest

MODULES = ("mesh", "space", "kicad", "exact", "grid", "reach", "rules", "deck", "lower", "engine", "build", "domain")


class PartsScaffold(unittest.TestCase):
    def test_every_module_loads(self):
        import petra.models.parts as parts

        on_disk = {info.name for info in pkgutil.iter_modules(parts.__path__)}
        self.assertEqual(on_disk, set(MODULES))
        for name in MODULES:
            with self.subTest(module=name):
                importlib.import_module(f"petra.models.parts.{name}")
        importlib.import_module("petra.registry.parts")

    def test_the_package_declares_no_domain_until_it_is_registered(self):
        import petra.models.parts as parts

        self.assertFalse(hasattr(parts, "DOMAIN"))

    def test_the_rule_table_holds_together(self):
        from petra.models.parts.domain import rules_for
        from petra.models.parts.rules import RULES, Evaluator, Measure
        from petra.registry import ProcessKind

        swept = {Measure.CLEARANCE} | {m for m in Measure if m.evaluator is Evaluator.GRID}
        for rule in RULES:
            with self.subTest(rule=rule.id):
                self.assertEqual(rule.query is not None, rule.measure in swept, "a rule builds a query exactly when its measure sweeps")
                self.assertEqual(rule.id.split(".")[0], rule.applies.process.value if rule.applies.process else "fit")
        for kind in (ProcessKind.PRINT, ProcessKind.POWDER, ProcessKind.SHEET, ProcessKind.MILL, ProcessKind.MOLD):
            with self.subTest(kind=kind):
                self.assertTrue(rules_for(kind))


if __name__ == "__main__":
    unittest.main()
