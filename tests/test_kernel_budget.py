"""What Petra's Python counts is counted, and held to a ceiling (docs/principles.md T2).

Two parts are counted in code lines: the arithmetic of the Python reader, under petra/kernel, and
the modules outside it that the manifest calls trusted. The manifest, tests/trusted_base.py, holds
the arithmetic's cap, the total's ceiling, and the class of every module under petra/.
`python -m tests.test_kernel_budget` prints the counts and every recorded debt, then runs the tests.
"""
import ast
import io
import tokenize
import unittest
from pathlib import Path

from tests import trusted_base as M

ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "petra" / "kernel"
NOT_CODE = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER}


def code_lines(source: str) -> int:
    """Lines that hold code. Blank lines, comments and docstrings (any statement that is
    only a string literal) do not count."""
    docstrings = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            docstrings.update(range(node.lineno, node.end_lineno + 1))
    code = set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type not in NOT_CODE:
            code.update(range(token.start[0], token.end[0] + 1))
    return len(code - docstrings)


def lines(path: str) -> int:
    return code_lines((ROOT / path).read_text(encoding="utf-8"))


def relative(paths) -> list[str]:
    return sorted(p.relative_to(ROOT).as_posix() for p in paths)


def core_files() -> list[str]:
    return relative(KERNEL.rglob("*.py"))


def outside_files() -> list[str]:
    return [path for path in relative((ROOT / "petra").rglob("*.py")) if not path.startswith("petra/kernel/")]


def trusted_modules() -> list[str]:
    return [module for group in M.TRUSTED for module in group.modules]


def counts() -> dict[str, int]:
    return {
        "core": sum(lines(path) for path in core_files()),
        "outside": sum(lines(path) for path in trusted_modules()),
    }


def resolves(ref: M.Ref) -> bool:
    path = ROOT / ref.path
    if not path.exists():
        return False
    if not ref.anchor:
        return True
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".md":
        return any(line.lstrip("#").strip() == ref.anchor for line in text.splitlines() if line.startswith("#"))
    return any(isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name == ref.anchor
               for node in ast.parse(text).body)


def debts() -> list[tuple[str, M.Debt]]:
    return [(group.name, group.checked_by) for group in M.TRUSTED if isinstance(group.checked_by, M.Debt)]


def report() -> str:
    c = counts()
    rows = [
        "What Petra's Python counts, in code lines (docs/principles.md T2)",
        f"  arithmetic        {c['core']:6,}   cap {M.CORE_CAP.lines:,}",
        f"  outside it        {c['outside']:6,}   {len(trusted_modules())} modules",
        f"  total             {sum(c.values()):6,}   ceiling {M.TRUSTED_CEILING.lines:,}",
        f"Debts ({len(debts())})",
    ]
    rows += [f"  {name}, since {debt.since}: {debt.what}" for name, debt in debts()]
    return "\n".join(rows)


class Counter(unittest.TestCase):
    def test_counter_skips_docstrings_comments_and_blank_lines(self):
        source = (
            '"""Module docstring\nover two lines."""\n\n# a comment\n'
            'X = 1  # trailing comment\n"""Attribute docstring."""\n\n'
            'def f(a,\n      b):\n    """Docstring."""\n    return a + b\n'
            'TEXT = """not a docstring\nbut a value"""\n'
        )
        self.assertEqual(code_lines(source), 6, "X = 1, two lines of def header, the return, two lines of TEXT")

    def test_a_reference_resolves_only_to_a_heading_or_definition_that_exists(self):
        self.assertTrue(resolves(M.Ref("docs/principles.md", "1. The trusted base")))
        self.assertFalse(resolves(M.Ref("docs/principles.md", "1. The trusted")))
        self.assertTrue(resolves(M.Ref("tests/test_kernel_budget.py", "Counter")))
        self.assertFalse(resolves(M.Ref("tests/test_kernel_budget.py", "counter")))
        self.assertFalse(resolves(M.Ref("tests/no_such_test.py")))


class KernelCore(unittest.TestCase):
    def test_the_shared_core_is_within_its_cap(self):
        core = counts()["core"]
        self.assertLessEqual(core, M.CORE_CAP.lines, f"the arithmetic has {core} code lines; raise CORE_CAP only with its reason")


class TrustedBase(unittest.TestCase):
    def test_every_module_outside_the_kernel_is_classified_once(self):
        self.assertEqual(sorted(trusted_modules() + list(M.UNTRUSTED)), outside_files(),
                         "add the module to a trusted group or to UNTRUSTED in tests/trusted_base.py")

    def test_each_trusted_group_names_its_judge_or_a_dated_debt(self):
        for group in M.TRUSTED:
            with self.subTest(group=group.name):
                if isinstance(group.checked_by, M.Debt):
                    self.assertTrue(group.checked_by.what)
                    continue
                judge = group.checked_by
                self.assertTrue(judge.shares, "say what the judge shares with Petra")
                for ref in (judge.code, *judge.compared_by):
                    self.assertTrue(resolves(ref), f"{ref} does not exist")

    def test_the_whole_trusted_base_is_within_its_ceiling(self):
        c = counts()
        total = sum(c.values())
        self.assertLessEqual(total, M.TRUSTED_CEILING.lines,
                             f"what is counted has {total} code lines (the arithmetic {c['core']}, outside it "
                             f"{c['outside']}); raise TRUSTED_CEILING only with its reason")

    def test_each_limit_carries_its_reason(self):
        for limit in (M.CORE_CAP, M.TRUSTED_CEILING):
            self.assertTrue(limit.reason)


if __name__ == "__main__":
    print(report())
    unittest.main()
