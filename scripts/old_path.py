"""Show that the readers that stay import with the old path removed (plan step 1.2a).

    python scripts/old_path.py [--list FILE] [--scratch DIR] [--pins | --write | --stale]

docs/old_path_removal.md gives every file of petra/ one line: delete, keep or rewrite. This
script holds the list to the tree and then tries it out on a copy, changing nothing here:

1. Every file of petra/ is on the list once, and the list names no file that is not there.
2. petra/ is copied to a scratch folder and every file the list deletes is removed from the
   copy.
3. In each file that stays, every import at module level of a removed module is cut: the
   whole line, or the names on it that a removed module defined. A name that a package
   passes on from a removed module is one of those, so a package's `__init__` loses what it
   only handed through.
4. `petra.grid`, `petra.deck`, `petra.rule`, `petra.verify`, `petra.export`, `petra.cli`
   and `petra.mcp` are imported from the copy, each in an interpreter of its own.

A module that still imports after step 3 uses nothing of the old path while it loads. What it
uses later, inside a function, is the work of step 1.2b: a name that step 3 cut and a
function still reads, and each import inside a function of a file that stays that names a
removed module, which step 5 prints. Step 6 imports every other module that stays and
prints the ones that do not load, with the reason. Those need more than a cut line.

Exits 0 when the list matches the tree and all seven import. `--scratch DIR` keeps the copy
in DIR, which must not exist yet.

`--pins` prints, in place of all that, what pins each file the list deletes or rewrites: the
test modules, and the scripts outside petra/, that import it by name. An import is read from
the source, so a file reached only through another module, or through a command run as a
process, is not counted. The list's last column is this, and so is the paragraph of counts
between its two `pins` marks: `--write` writes both into the list again, after a test or a
script has changed what it imports, and `--stale` exits 1 when that would change the list.
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIST = ROOT / "docs" / "old_path_removal.md"
LINE = re.compile(r"\| `(petra/[^`]+)` \| (delete|keep|rewrite) \|")
MODULES = ("petra.grid", "petra.deck", "petra.rule", "petra.verify", "petra.export", "petra.cli", "petra.mcp")
SKIP = {"__pycache__", "bin"}
"""Folders of petra/ that are not source: the caches, and the kernel a build puts in."""


def listed(path: Path) -> dict[str, str]:
    """Each file the list names, with its class. A file named twice is an error."""
    found: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = LINE.match(line)
        if match:
            if match[1] in found:
                raise SystemExit(f"{path.name}:{number}: {match[1]} is on the list twice")
            found[match[1]] = match[2]
    return found


def files(package: Path) -> list[str]:
    """Every source file of the package, by its path from the repository root."""
    return sorted(p.relative_to(package.parent).as_posix() for p in package.rglob("*")
                  if p.is_file() and not SKIP & set(p.relative_to(package).parts) and p.suffix != ".pyc")


def module_of(path: str) -> str:
    """petra/kernel/__init__.py -> petra.kernel, and petra/grid.py -> petra.grid."""
    parts = Path(path).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


class Tree:
    """The modules of the package as the list leaves them: which stay, and which go."""

    def __init__(self, classes: dict[str, str]) -> None:
        python = {path: kind for path, kind in classes.items() if path.endswith(".py")}
        self.path = {module_of(path): path for path in python}
        self.gone = {module_of(path) for path, kind in python.items() if kind == "delete"}
        self.source = {module: ast.parse((ROOT / path).read_text(encoding="utf-8")) for module, path in self.path.items()}

    def package(self, module: str) -> str:
        return module if self.path[module].endswith("__init__.py") else module.rpartition(".")[0]

    def named(self, module: str, node: ast.ImportFrom) -> str:
        """The module a `from ... import` names, with its dots resolved."""
        if not node.level:
            return node.module or ""
        base = self.package(module).split(".")
        base = base[:len(base) - (node.level - 1)]
        return ".".join(base + ([node.module] if node.module else []))

    def origin(self, module: str, name: str, depth: int = 0) -> str | None:
        """The module of this package that defines `name` of `module`: a submodule of that
        name, or the module `module` itself imports the name from, followed through, or
        `module` when it is of this package and imports the name from nowhere. None for a
        module that is not of this package."""
        if f"{module}.{name}" in self.path:
            return f"{module}.{name}"
        if module not in self.path:
            return None
        if depth < 8:
            for node in self.source[module].body:
                if isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if (alias.asname or alias.name) == name:
                            return self.origin(self.named(module, node), alias.name, depth + 1)
        return module

    def removed(self, module: str, node: ast.stmt) -> list[ast.alias]:
        """The names of an import statement of `module` that a removed module defined."""
        if isinstance(node, ast.Import):
            return [a for a in node.names if any(a.name == gone or a.name.startswith(gone + ".") for gone in self.gone)]
        if isinstance(node, ast.ImportFrom):
            source = self.named(module, node)
            if source in self.gone or any(source.startswith(gone + ".") for gone in self.gone):
                return list(node.names)
            return [a for a in node.names if self.origin(source, a.name) in self.gone]
        return []


OUTSIDE = ("tests", "scripts", "bench", "corpus", "twin", "_build")
"""Where the code that uses petra/ from outside it lives."""
HELD_OUT = ("bench/exam", "bench/tasks.py", "bench/attack", "bench/formalizer")
"""Never read: the exam and its tasks are held out, and the other two are other sessions' work."""


def pins(tree: Tree) -> dict[str, list[str]]:
    """For each module of the package, the files outside it that import it by name: `import
    petra.x`, `from petra.x import y`, `from petra import x`, and `petra.NAME` where NAME is a
    name the package hands on from that module (`petra._API`)."""
    handed = {}
    for node in ast.walk(tree.source["petra"]):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_API" for t in node.targets):
            handed = {name: f"petra.{module}" for name, module in ast.literal_eval(node.value).items()}
    found: dict[str, set[str]] = {module: set() for module in tree.path}
    for folder in OUTSIDE:
        for path in sorted((ROOT / folder).rglob("*.py")):
            name = path.relative_to(ROOT).as_posix()
            if any(name == held or name.startswith(held + "/") for held in HELD_OUT):
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                used: list[str] = []
                if isinstance(node, ast.Import):
                    used = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                    used = [tree.origin(node.module, a.name) or "" for a in node.names] + [node.module]
                elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "petra":
                    used = [handed.get(node.attr, f"petra.{node.attr}")]
                for module in used:
                    if module in found and module != "petra":
                        found[module].add(name)
    return {module: sorted(names) for module, names in found.items()}


MARKED = re.compile(r"(<!-- pins -->\n).*?(\n<!-- /pins -->)", re.S)
"""The paragraph of the list that `written` writes: what the test modules import."""


def short(names: list[str]) -> str:
    """The files that import one of the list's, as its last column names them: the test
    modules first, without `tests/` and `.py`, and then the scripts by their paths."""
    tests = [name.removeprefix("tests/").removesuffix(".py") for name in names if name.startswith("tests/")]
    return ", ".join([*tests, *(name for name in names if not name.startswith("tests/"))])


def written(text: str, classes: dict[str, str], tree: Tree) -> str:
    """The text of the list with its last column and its marked paragraph written from what
    imports each file today."""
    held = {tree.path[module]: names for module, names in pins(tree).items()}
    lines = []
    for line in text.split("\n"):
        match = LINE.match(line)
        if match and match[1] in held and match[2] != "keep":
            head, _, _ = line.rstrip().removesuffix("|").rstrip().rpartition(" | ")
            line = f"{head} | {short(held[match[1]]) or 'nothing'} |"
        lines.append(line)
    modules = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / "tests").glob("test_*.py"))

    def importing(kind: str) -> set[str]:
        return {name for path, names in held.items() if classes[path] == kind for name in names if name in modules}

    deleted, rewritten = importing("delete"), importing("rewrite") - importing("delete")
    free = [name for name in modules if name not in deleted and name not in rewritten]
    names = lambda found: ", ".join(f"`{short([name])}`" for name in sorted(found))      # noqa: E731
    scripts = sorted({name for path, found in held.items() if classes[path] == "delete" for name in found if not name.startswith("tests/")})
    said = (f"Of the {len(modules)} test modules, {len(deleted)} import a file marked delete. They are replaced by corpus and boundary tests in "
            f"step 1.2b. {len(rewritten)} more import only files marked rewrite: {names(rewritten)}. {len(free)} import neither: {names(free)}.\n\n"
            f"The scripts outside `petra/` that import a file marked delete: {', '.join(f'`{name}`' for name in scripts)}.")
    return MARKED.sub(lambda found: found[1] + said + found[2], "\n".join(lines))


def typing_only(node: ast.stmt) -> bool:
    return isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test)


def cut(tree: Tree, module: str, text: str) -> tuple[str, list[str], list[tuple[str, str]]]:
    """The text of a file that stays with its imports of removed modules cut at module level,
    what was cut, and each import inside a function that names a removed module, with the
    function's name."""
    lines = text.split("\n")
    taken: list[str] = []
    later: list[tuple[str, str]] = []

    def walk(body: list[ast.stmt], inside: str | None) -> None:
        for node in body:
            if typing_only(node):
                walk(node.orelse, inside)      # an import under TYPE_CHECKING never runs
                continue
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                gone = tree.removed(module, node)
                if not gone:
                    continue
                names = ", ".join(a.name for a in gone)
                source = tree.named(module, node) if isinstance(node, ast.ImportFrom) else ""
                if inside is not None:
                    later.append((inside, f"{source}: {names}" if source else names))
                    continue
                kept = [a for a in node.names if a not in gone]
                indent = " " * node.col_offset
                node.names = kept
                lines[node.lineno - 1:node.end_lineno] = [indent + (ast.unparse(node) if kept else "pass")] + [""] * (node.end_lineno - node.lineno)
                taken.append(f"{source}: {names}" if source else names)
                continue
            for name in ("body", "orelse", "finalbody", "handlers"):
                inner = getattr(node, name, None)
                if isinstance(inner, list):
                    here = node.name if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else inside
                    walk([n for n in inner if isinstance(n, ast.stmt)] + [s for h in inner if isinstance(h, ast.ExceptHandler) for s in h.body], here)

    walk(ast.parse(text).body, None)
    return "\n".join(lines), taken, later


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--list", type=Path, default=LIST, help="the list; default docs/old_path_removal.md")
    parser.add_argument("--scratch", type=Path, help="keep the copy in this folder, which must not exist yet")
    parser.add_argument("--pins", action="store_true", help="print what outside petra/ imports each file the list deletes or rewrites")
    parser.add_argument("--write", action="store_true", help="write the list's last column and its counts of tests again")
    parser.add_argument("--stale", action="store_true", help="exit 1 when --write would change the list")
    args = parser.parse_args()

    classes = listed(args.list)
    if args.write or args.stale:
        text = args.list.read_text(encoding="utf-8")
        fresh = written(text, classes, Tree(classes))
        if args.write:
            args.list.write_text(fresh, encoding="utf-8")
        elif fresh != text:
            print(f"{args.list.name} is stale: a test or a script imports other files of petra/ than it says. Run python scripts/old_path.py --write")
        return 1 if args.stale and fresh != text else 0
    if args.pins:
        tree = Tree(classes)
        held = pins(tree)
        for module, path in sorted(tree.path.items(), key=lambda item: item[1]):
            if classes[path] != "keep":
                print(f"{path}\t{classes[path]}\t{' '.join(held[module]) or 'none'}")
        return 0
    there = files(ROOT / "petra")
    problems = [f"{path} is not on the list" for path in there if path not in classes]
    problems += [f"{path} is on the list and not in the tree" for path in classes if path not in there]
    counts = {kind: sum(1 for k in classes.values() if k == kind) for kind in ("delete", "keep", "rewrite")}
    print(f"1. the list names {len(classes)} files: {counts['delete']} delete, {counts['keep']} keep, {counts['rewrite']} rewrite; "
          f"petra/ holds {len(there)}")
    for problem in problems:
        print(f"   {problem}")
    if problems:
        return 1

    holder = None if args.scratch else tempfile.TemporaryDirectory()
    scratch = args.scratch or Path(holder.name)
    try:
        shutil.copytree(ROOT / "petra", scratch / "petra", ignore=shutil.ignore_patterns(*SKIP))
        for path, kind in classes.items():
            if kind == "delete":
                (scratch / path).unlink()
        for folder in sorted((p for p in (scratch / "petra").rglob("*") if p.is_dir()), reverse=True):
            if not any(folder.iterdir()):
                folder.rmdir()
        print(f"2. removed {counts['delete']} files from a copy of petra/, which leaves {len(files(scratch / 'petra'))}")

        tree = Tree(classes)
        cuts, later = 0, []
        for module, path in sorted(tree.path.items()):
            if module in tree.gone:
                continue
            text, taken, inside = cut(tree, module, (ROOT / path).read_text(encoding="utf-8"))
            (scratch / path).write_text(text, encoding="utf-8")
            cuts += len(taken)
            for what in taken:
                print(f"   cut from {path}: {what}")
            later += [(path, function, what) for function, what in inside]
        print(f"3. cut {cuts} imports of removed modules at module level, from the files that stay")

        failed = 0
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        for name in MODULES:
            code = (f"import importlib, pathlib, petra\n"
                    f"assert pathlib.Path(petra.__file__).resolve().is_relative_to(pathlib.Path({str(scratch.resolve())!r})), petra.__file__\n"
                    f"importlib.import_module({name!r})\n")
            done = subprocess.run([sys.executable, "-c", code], cwd=scratch, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL)
            failed += done.returncode != 0
            print(f"   {name}: " + ("imports" if done.returncode == 0 else "DOES NOT IMPORT: " + (done.stderr.strip().splitlines() or ["no message"])[-1]))
        print(f"4. {len(MODULES) - failed} of {len(MODULES)} modules import from the copy")

        print(f"5. {len(later)} imports inside functions of the files that stay name a removed module, which step 1.2b rewrites:")
        for path, function, what in later:
            print(f"   {path}: {function}: {what}")

        others = [module for module in sorted(tree.path) if module not in tree.gone and module not in MODULES]
        broken = []
        for name in others:
            done = subprocess.run([sys.executable, "-c", f"import importlib\nimportlib.import_module({name!r})\n"], cwd=scratch, env=env,
                                  capture_output=True, text=True, stdin=subprocess.DEVNULL)
            if done.returncode != 0:
                broken.append(f"   {name}: {(done.stderr.strip().splitlines() or ['no message'])[-1]}")
        print(f"6. of the other {len(others)} modules that stay, {len(others) - len(broken)} import from the copy and {len(broken)} do not:")
        print("\n".join(broken) if broken else "   none")
        return 1 if failed else 0
    finally:
        if holder is not None:
            holder.cleanup()


if __name__ == "__main__":
    sys.exit(main())
