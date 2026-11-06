"""The trusted kernel stays small enough to port. Owner: K."""
import ast
import io
import tokenize
import unittest
from pathlib import Path

from petra.kernel import KERNEL_LINE_BUDGET

KERNEL = Path(__file__).resolve().parents[1] / "petra" / "kernel"
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


class KernelBudget(unittest.TestCase):
    def test_counter_skips_docstrings_comments_and_blank_lines(self):
        source = (
            '"""Module docstring\nover two lines."""\n\n# a comment\n'
            'X = 1  # trailing comment\n"""Attribute docstring."""\n\n'
            'def f(a,\n      b):\n    """Docstring."""\n    return a + b\n'
            'TEXT = """not a docstring\nbut a value"""\n'
        )
        self.assertEqual(code_lines(source), 6, "X = 1, two lines of def header, the return, two lines of TEXT")

    def test_kernel_is_within_budget(self):
        total = sum(code_lines(path.read_text(encoding="utf-8")) for path in KERNEL.rglob("*.py"))
        self.assertLessEqual(total, KERNEL_LINE_BUDGET, f"petra/kernel has {total} code lines")


if __name__ == "__main__":
    unittest.main()
