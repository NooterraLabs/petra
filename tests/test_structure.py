"""Structural rules of the package that must keep holding.

The verdict of a check is the kernel's. What stands in petra/ parses, writes files, searches for
hints and words reports, and it does that with the standard library alone. The old path, the
Python checker with its models, registry and solvers, was deleted on 2026-11-15 (the tag
`old-path` holds it), and nothing here may bring a piece of it back by name.
"""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "petra"
ARITHMETIC = ROOT / "kernel"
STDLIB = set(sys.stdlib_module_names)
GONE = ("certs", "coverage", "envelope", "library", "loop", "mechanics", "models", "premises", "readout", "recall", "registry", "repair",
        "solvers", "verdict")
"""The modules and packages of the old path, each once a name under petra/."""


def imports(path: Path) -> list[tuple[str, int, tuple[str, ...]]]:
    """Every import of a file, at any depth: the module, its level, and the names taken from it."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(a.name, 0, ()) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            found.append((node.module or "", node.level, tuple(a.name for a in node.names)))
    return found


class Arithmetic(unittest.TestCase):
    def test_it_imports_only_the_standard_library_and_itself(self):
        for path in ARITHMETIC.rglob("*.py"):
            for name, level, _ in imports(path):
                if level == 0:
                    self.assertIn(name.split(".")[0], STDLIB, f"{path.name} imports {name}")
                else:
                    depth = len(path.relative_to(ARITHMETIC).parts) - 1
                    self.assertLessEqual(level - 1, depth, f"{path.name} reaches outside petra.kernel")

    def test_outside_code_takes_it_by_the_package_and_not_by_its_files(self):
        for path in ROOT.rglob("*.py"):
            if ARITHMETIC in path.parents:
                continue
            for name, level, names in imports(path):
                parts = name.split(".")
                if "kernel" in parts:
                    self.assertEqual(parts[parts.index("kernel") + 1:], [], f"{path.relative_to(ROOT)} imports the arithmetic's internals: {name}")


class Package(unittest.TestCase):
    def test_it_imports_only_the_standard_library_and_itself(self):
        """An install of Petra needs no other package: the solvers that needed numpy and scipy went with the old path."""
        for path in ROOT.rglob("*.py"):
            for name, level, _ in imports(path):
                if level == 0:
                    self.assertIn(name.split(".")[0], STDLIB | {"petra"}, f"{path.relative_to(ROOT)} imports {name}")

    def test_no_file_of_the_old_path_is_there(self):
        for name in GONE:
            self.assertFalse((ROOT / name).exists() or (ROOT / f"{name}.py").exists(), f"petra/{name} is back")
        self.assertEqual(sorted(p.name for p in ARITHMETIC.glob("*.py")), ["__init__.py", "evaluate.py", "interval.py", "terms.py"],
                         "petra/kernel holds the reader's arithmetic and no checker")

    def test_no_file_imports_a_module_of_the_old_path(self):
        for path in ROOT.rglob("*.py"):
            for name, level, names in imports(path):
                parts = [p for p in name.split(".") if p and p != "petra"]
                first = parts[0] if parts else None
                self.assertNotIn(first, GONE, f"{path.relative_to(ROOT)} imports {name}")
                if not parts and (level == 1 and path.parent == ROOT or name == "petra"):      # `from . import x` at the top, or `from petra import x`
                    for taken in names:
                        self.assertNotIn(taken, GONE, f"{path.relative_to(ROOT)} imports {taken}")


if __name__ == "__main__":
    unittest.main()
