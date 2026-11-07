"""The outside judge (judges/) and the absurd-gap generator (scripts/absurd_gap.py), docs/plan.md
P0 item 2. The judge names every canary's stated condition and nothing on the examples, its
source imports nothing from petra.models or petra.mechanics (whose formulas P1's model may
share), and the generator gives the same designs and findings for the same seed. Petra's
verdict on a canary is not asserted: P1 turns those false PASSes into FAILs, and the
canaries stay valid either way."""
import ast
import importlib.util
import sys
import unittest
from pathlib import Path

from judges import CONDITIONS, judge
from petra.lang import load_design
from petra.registry import build_registry

ROOT = Path(__file__).resolve().parents[1]
CANARIES = sorted((ROOT / "judges" / "canaries").glob("*.petra"))
EXAMPLES = sorted((ROOT / "examples").rglob("*.petra"))
REGISTRY = build_registry()


def _script():
    spec = importlib.util.spec_from_file_location("absurd_gap", ROOT / "scripts" / "absurd_gap.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["absurd_gap"] = module    # its dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


def _stated(path: Path) -> str:
    return next(line.split(":", 1)[1].strip() for line in path.read_text(encoding="utf-8").splitlines()
                if line.startswith("# violates:"))


class Canaries(unittest.TestCase):
    def test_there_is_a_canary_per_known_false_pass(self):
        self.assertGreaterEqual(len(CANARIES), 5)

    def test_the_judge_names_each_canarys_stated_condition(self):
        for path in CANARIES:
            with self.subTest(canary=path.stem):
                stated = _stated(path)
                self.assertIn(stated, CONDITIONS)
                found = judge(load_design(path, REGISTRY), REGISTRY)
                self.assertIn(stated, found.ids, [(v.id, v.reason) for v in found.violations])


class Examples(unittest.TestCase):
    def test_the_judge_finds_every_example_buildable(self):
        self.assertTrue(EXAMPLES)
        for path in EXAMPLES:
            with self.subTest(example=str(path.relative_to(ROOT))):
                found = judge(load_design(path, REGISTRY), REGISTRY)
                self.assertEqual([(v.id, v.reason) for v in found.violations], [])


class Independence(unittest.TestCase):
    def test_the_judges_source_imports_nothing_from_petras_models(self):
        for path in sorted((ROOT / "judges").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                         else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                for name in names:
                    with self.subTest(file=path.name, module=name):
                        self.assertFalse(name.startswith("petra.models"), name)
                        self.assertFalse(name.startswith("petra.mechanics"), name)


class Generator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.A = _script()

    def test_a_seed_gives_the_same_designs_and_findings(self):
        n = len(dict.fromkeys(self.A.SCHEDULE))    # one design of every kind
        first, second = (self.A.run(3, n, workers=1) for _ in range(2))
        strip = lambda rows: [{k: v for k, v in r.items() if k != "seconds"} for r in rows]
        self.assertEqual(strip(first), strip(second))
        self.assertEqual(self.A.log_lines(first, []), self.A.log_lines(second, []))
        self.assertEqual({r["kind"] for r in first}, set(self.A.SCHEDULE))

    def test_designs_are_drawn_from_their_own_stream(self):
        texts = lambda seed: [self.A.sample(seed, i, REGISTRY).text for i in (0, 5, 40)]
        self.assertEqual(texts(3), texts(3))
        self.assertNotEqual(texts(3), texts(4))


if __name__ == "__main__":
    unittest.main()
