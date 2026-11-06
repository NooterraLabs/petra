"""The domain registry derives every table from one tuple and refuses bad specs, and each
elaborator's model premise is keyed by its source. Owner: P."""
import dataclasses
import hashlib
import importlib
import pkgutil
import unittest
from pathlib import Path

import petra.models as models
from petra.lang.parser import DECLS
from petra.models import _index, base, bolt, truss, uncertainty
from petra.premises import Tag


class Registered(unittest.TestCase):
    def test_the_four_v0_domains_in_order(self):
        self.assertEqual(tuple(models.DOMAINS), ("truss", "circuit", "bolt", "uncertainty"))

    def test_every_domain_module_is_registered(self):
        for info in pkgutil.iter_modules(models.__path__):
            module = importlib.import_module(f"petra.models.{info.name}")
            spec = getattr(module, "DOMAIN", None)
            if spec is not None:
                self.assertIn(spec, models._REGISTERED, f"petra.models.{info.name} declares an unregistered DOMAIN")

    def test_tables_derive_from_the_specs(self):
        for spec in models._REGISTERED:
            self.assertIs(models.DOMAINS[spec.name], spec)
            for kind in spec.kinds:
                self.assertIs(models.KINDS[kind], spec)
            for mode in spec.modes:
                self.assertIs(models.MODES[mode.id], mode)
            self.assertLessEqual(spec.unmodelled, models.UNMODELLED)
        for mode in base.CROSS_DOMAIN_MODES:
            self.assertIs(models.MODES[mode.id], mode)
        self.assertEqual(models.COVERAGE, tuple(r for s in models._REGISTERED for r in s.coverage))

    def test_component_kinds_are_not_language_keywords(self):
        self.assertEqual(set(DECLS) & set(models.KINDS), set())

    def test_uncertainty_needs_no_other_domain(self):
        self.assertNotIn("bolt", uncertainty.__dict__)
        self.assertEqual(set(uncertainty.DOMAIN.kinds), {"demand"})


class Refused(unittest.TestCase):
    def test_a_domain_registered_twice(self):
        with self.assertRaisesRegex(RuntimeError, "registered twice"):
            _index((truss.DOMAIN, truss.DOMAIN))

    def test_a_kind_claimed_twice(self):
        clash = dataclasses.replace(bolt.DOMAIN, name="bolt2", kinds={"truss": bolt.lower_joint}, builders={}, unmodelled=frozenset(), qois={}, coverage=(), models={})
        with self.assertRaisesRegex(RuntimeError, "claimed by"):
            _index((truss.DOMAIN, clash))

    def test_a_mode_both_built_and_unmodelled(self):
        with self.assertRaisesRegex(RuntimeError, "both built and unmodelled"):
            _index((dataclasses.replace(bolt.DOMAIN, unmodelled=frozenset({bolt.TENSION, bolt.PLATE_BEARING})),))

    def test_reaching_another_domains_mode(self):
        with self.assertRaisesRegex(RuntimeError, "does not declare"):
            _index((dataclasses.replace(uncertainty.DOMAIN, qois={"collapse_factor": truss.PLASTIC_COLLAPSE}),))

    def test_a_mode_declared_twice(self):
        twin = dataclasses.replace(bolt.DOMAIN, name="bolt2", kinds={"joint2": bolt.lower_joint})
        with self.assertRaisesRegex(RuntimeError, "declared twice"):
            _index((bolt.DOMAIN, twin))


class ModelPremises(unittest.TestCase):
    def spec(self, module):
        return base.model_spec(module, "bolt.tension", "torque-tension", "no prying", "petra-maintainers", "VDI 2230")

    def test_the_source_hash_covers_the_elaborator_module(self):
        expected = hashlib.sha256(Path(bolt.__file__).read_text(encoding="utf-8").encode("utf-8")).hexdigest()[:16]
        self.assertEqual(self.spec(bolt).source_hash, expected)
        self.assertNotEqual(self.spec(truss).source_hash, expected, "another module's source gives another hash")

    def test_the_premise_is_a_validated_model_named_by_id_and_hash(self):
        spec = self.spec(bolt)
        p = spec.premise()
        self.assertEqual(p.label, f"model:bolt.tension@{spec.source_hash}")
        self.assertIs(p.tag, Tag.VALIDATED_MODEL)
        self.assertEqual((p.owner, p.source), ("petra-maintainers", "VDI 2230"))
        self.assertIn("no prying", p.statement)


if __name__ == "__main__":
    unittest.main()
