"""Structural rules that hold for the sketch already and must keep holding. Owner: K."""
import ast
import dataclasses
import importlib
import inspect
import sys
import typing
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "petra"
KERNEL = ROOT / "kernel"
STDLIB = set(sys.stdlib_module_names)


def imports(path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(a.name, 0) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            found.append((node.module or "", node.level))
    return found


def members(alias: object) -> set:
    """The classes a typing alias names. A one-member Union is the class itself."""
    return set(typing.get_args(alias)) or {alias}


def rule_modules() -> list:
    from petra.kernel.rules import MODULE_OF

    return [importlib.import_module(f"petra.kernel.rules.{m}") for m in MODULE_OF.values()]


class KernelBoundary(unittest.TestCase):
    def test_kernel_imports_only_stdlib_and_itself(self):
        for path in KERNEL.rglob("*.py"):
            for name, level in imports(path):
                if level == 0:
                    self.assertIn(name.split(".")[0], STDLIB, f"{path.name} imports {name}")
                else:
                    depth = len(path.relative_to(KERNEL).parts) - 1
                    self.assertLessEqual(level - 1, depth, f"{path.name} reaches outside petra.kernel")

    def test_outside_code_uses_only_the_kernel_package_and_rule_modules(self):
        from petra.kernel.rules import MODULE_OF

        allowed = [[]] + [["rules", m] for m in MODULE_OF.values()]
        for path in ROOT.rglob("*.py"):
            if KERNEL in path.parents:
                continue
            for name, _ in imports(path):
                parts = name.split(".")
                if "kernel" in parts:
                    tail = parts[parts.index("kernel") + 1:]
                    self.assertIn(tail, allowed, f"{path.relative_to(ROOT)} imports kernel internals: {name}")

    def test_check_and_codec_name_no_rule_module(self):
        from petra.kernel.rules import MODULE_OF

        for module in ("check.py", "codec.py"):
            source = (KERNEL / module).read_text(encoding="utf-8")
            for rule_module in MODULE_OF.values():
                self.assertNotIn(rule_module, source, f"{module} names {rule_module}; dispatch through the registry")


class RuleRegistry(unittest.TestCase):
    def test_aliases_agree_with_the_registry(self):
        from petra.kernel import rules

        self.assertEqual(members(rules.Goal), set(rules.GOAL_RULE))
        self.assertEqual(members(rules.ProofEvidence), set(rules.PROOF_RULE))
        self.assertEqual(members(rules.RefutationEvidence), set(rules.REFUTATION_RULE))
        self.assertEqual(members(rules.QuantityDef), set(rules.LEMMAS))
        self.assertEqual(members(rules.LemmaEvidence), {lemma.evidence for lemma in rules.LEMMAS.values()})

    def test_every_rule_module_is_registered_once(self):
        from petra.kernel import rules
        from petra.kernel.rules import base

        on_disk = {p.stem for p in (KERNEL / "rules").glob("r*.py")}
        self.assertEqual(on_disk, set(rules.MODULE_OF.values()))
        for module in rule_modules():
            self.assertIsInstance(module.RULE, base.RuleSpec)
            self.assertIs(rules.RULES[module.RULE.id], module.RULE)

    def test_corrupt_registries_are_refused(self):
        from petra.kernel.rules import _index, r1_linear, r5_moment

        with self.assertRaisesRegex(RuntimeError, "registered twice"):
            _index((r1_linear.RULE, r1_linear.RULE))
        with self.assertRaisesRegex(RuntimeError, "untagged"):
            _index((dataclasses.replace(r1_linear.RULE, tags=()),))
        with self.assertRaisesRegex(RuntimeError, "refute must"):
            _index((dataclasses.replace(r5_moment.RULE, refute=r1_linear.RULE.refute),))
        with self.assertRaisesRegex(RuntimeError, "refute must"):
            _index((dataclasses.replace(r1_linear.RULE, refute=None),))
        with self.assertRaisesRegex(RuntimeError, "registered twice"):
            _index((r1_linear.RULE, dataclasses.replace(r5_moment.RULE, id="R1")))


class Codec(unittest.TestCase):
    def test_every_term_class_has_exactly_one_tag(self):
        from petra.kernel import codec, evidence, terms

        tagged = list(codec.TAGS.values())
        self.assertEqual(len(tagged), len(set(tagged)), "a class has two tags")
        for module in [terms, evidence, *rule_modules()]:
            for name, obj in vars(module).items():
                if inspect.isclass(obj) and obj.__module__ == module.__name__ and dataclasses.is_dataclass(obj):
                    self.assertIn(obj, tagged, f"{module.__name__}.{name} has no codec tag")

    def test_field_annotations_resolve_with_the_rule_aliases(self):
        from petra.kernel import codec, rules

        for cls in codec.TAGS.values():
            typing.get_type_hints(cls, localns=dict(vars(rules)))


class Sealing(unittest.TestCase):
    def test_theorem_cannot_be_built_outside_the_kernel(self):
        from petra.kernel import Statement, Theorem
        from petra.kernel.rules.r4_enclosure import AllNonpositive

        st = Statement(hyps=(), goal=AllNonpositive(exprs=()))
        with self.assertRaises(TypeError):
            Theorem(st, "sha256:x", "sha256:y", "R4", frozenset(), ())


if __name__ == "__main__":
    unittest.main()
