"""The formalizer run: two transcriptions of each equation, the worked examples, and how
much of a wrong row the acceptance check catches.

    python bench/formalizer/run.py [--rows a.json] [--second b.json] [--examples examples.json]

The three files default to the ones beside this script. For each equation it prints the
acceptance check on the first transcription with the other as its second. Then it damages
each admitted row in every way MUTATIONS lists, one change at a time, and counts the
damaged rows that the check refuses without a second transcription: by units, by a worked
example, or by continuity. A damaged row that gives the same values as the original at
every sample point is not a wrong row and is left out.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Iterator

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from petra import deck  # noqa: E402

FLIP = {"le": "ge", "ge": "le", "lt": "gt", "gt": "lt"}


def _number(node: Any) -> Fraction | None:
    if not isinstance(node, str):
        return None
    try:
        return Fraction(node)
    except (ValueError, ZeroDivisionError):
        return None


def _places(node: Any, path: tuple = ()) -> Iterator[tuple[tuple, Any]]:
    """Every node of an expression or condition tree with the path that reaches it."""
    yield path, node
    if isinstance(node, list):
        for n, child in enumerate(node[1:], 1):
            yield from _places(child, (*path, n))


def _put(tree: Any, path: tuple, new: Any) -> Any:
    if not path:
        return new
    out = list(tree)
    out[path[0]] = _put(tree[path[0]], path[1:], new)
    return out


def _trees(body: dict) -> list[tuple[Callable[[dict, Any], None], Any]]:
    """Each expression and condition of a row with a function that writes one back."""
    if "is" in body:
        return [(lambda b, new: b.__setitem__("is", new), body["is"])]
    out = []
    for n, case in enumerate(body["cases"]):
        for key in ("when", "is"):
            if key in case:
                out.append((lambda b, new, n=n, key=key: b["cases"][n].__setitem__(key, new), case[key]))
    return out


def mutations(body: dict) -> Iterator[tuple[str, dict]]:
    """(what was changed, the damaged row), one change each."""
    for put, tree in _trees(body):
        for path, node in _places(tree):
            def damaged(new: Any, what: str) -> tuple[str, dict]:
                out = copy.deepcopy(body)
                put(out, _put(tree, path, new))
                return what, out

            x = _number(node)
            exponent = bool(path) and isinstance(tree_at(tree, path[:-1]), list) and tree_at(tree, path[:-1])[0] == "pow" and path[-1] == 2
            if x is not None and exponent:
                yield damaged(str(x + 1), f"exponent {node} plus one")
            elif x is not None and x not in (0, 1):
                for factor, name in ((Fraction(11, 10), "up"), (Fraction(9, 10), "down")):
                    yield damaged(str(x * factor), f"constant {node} {name} 10%")
            if not isinstance(node, list):
                continue
            op, args = node[0], node[1:]
            if op in ("mul", "add", "min", "max") and len(args) >= 2:
                for n in range(len(args)):
                    kept = args[:n] + args[n + 1:]
                    yield damaged(kept[0] if len(kept) == 1 else [op, *kept], f"{op} loses argument {n + 1}")
            if op in ("min", "max"):
                yield damaged(["max" if op == "min" else "min", *args], f"{op} becomes the other")
            if op == "sqrt":
                yield damaged(args[0], "square root dropped")
            if op in ("sub", "div") and len(args) == 2:
                yield damaged([op, args[1], args[0]], f"{op} turned round")
            if op in FLIP:
                yield damaged([FLIP[op], *args], f"{op} becomes {FLIP[op]}")
    names = [t["name"] for t in body["takes"]]
    dims = {t["name"]: t["dim"] for t in body["takes"]}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if dims[a] == dims[b]:
                out = copy.deepcopy(body)
                swap = {a: b, b: a}
                for put, tree in _trees(body):
                    put(out, _renamed(tree, swap))
                yield f"{a} and {b} change places", out
    if "cases" in body:
        for i in range(len(body["cases"]) - 1):
            out = copy.deepcopy(body)
            out["cases"][i]["is"], out["cases"][i + 1]["is"] = body["cases"][i + 1]["is"], body["cases"][i]["is"]
            yield f"cases {i + 1} and {i + 2} change places", out


def tree_at(tree: Any, path: tuple) -> Any:
    for step in path:
        tree = tree[step]
    return tree


def _renamed(node: Any, swap: dict[str, str]) -> Any:
    if isinstance(node, str):
        return swap.get(node, node)
    return [node[0], *(_renamed(child, swap) for child in node[1:])]


def worked(row: deck.Row, bodies: list[dict]) -> tuple[list[deck.Example], list[str]]:
    """The row's examples, with an example's names read as the row's when they differ only
    in case or underscores. The second list says which examples could not be read."""
    key = {name.lower().replace("_", ""): name for name in row.takes}
    found, unread = [], []
    for body in bodies:
        given = {key.get(name.lower().replace("_", ""), name): text for name, text in body.get("given", {}).items()}
        try:
            found.append(deck.example({**body, "given": given}, row))
        except deck.RowError as exc:
            unread.append(str(exc))
    return found, unread


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--rows", default=str(HERE / "a.json"))
    parser.add_argument("--second", default=str(HERE / "b.json"))
    parser.add_argument("--examples", default=str(HERE / "examples.json"))
    args = parser.parse_args()
    first = {b["id"]: b for b in json.loads(Path(args.rows).read_text(encoding="utf-8"))["rows"]}
    other = deck.load(args.second)
    examples = json.loads(Path(args.examples).read_text(encoding="utf-8"))["examples"]

    admitted: list[tuple[dict, deck.Row, list[deck.Example]]] = []
    tally: dict[str, dict[str, int]] = {}
    for rid, body in first.items():
        row = deck.read(body)
        mine, unread = worked(row, examples.get(rid, []))
        checks = deck.accept(row, mine, other.get(rid))
        refused = any(c.outcome == "fail" for c in checks)
        print(f"{rid}: {'REFUSED' if refused else 'admitted'}")
        for c in checks:
            print(f"  {c.name:<11} {c.outcome:<5} {c.detail}")
            tally.setdefault(c.name, {}).setdefault(c.outcome, 0)
            tally[c.name][c.outcome] += 1
        for line in unread:
            print(f"  example not read: {line}")
        if not refused:
            admitted.append((body, row, mine))
    print(f"\n{len(first)} rows, {len(admitted)} admitted")
    for name, counts in tally.items():
        print(f"  {name:<11} " + ", ".join(f"{n} {outcome}" for outcome, n in sorted(counts.items())))

    print("\nDamaged rows that the check refuses with no second transcription")
    total = {"wrong": 0, "units": 0, "examples": 0, "continuity": 0, "any": 0}
    for body, row, mine in admitted:
        counts = dict.fromkeys(total, 0)
        missed = []
        for what, damaged in mutations(body):
            try:
                wrong = deck.read(damaged)
            except deck.RowError:
                continue
            if deck.second(row, wrong).outcome == "pass":
                continue
            failed = {c.name for c in (deck.units(wrong), deck.reproduces(wrong, mine), deck.continuous(wrong)) if c.outcome == "fail"}
            counts["wrong"] += 1
            for name in failed:
                counts[name] += 1
            counts["any"] += bool(failed)
            if not failed:
                missed.append(what)
        for name in total:
            total[name] += counts[name]
        print(f"  {row.id}: {counts['wrong']} wrong rows, {counts['any']} refused (units {counts['units']}, examples {counts['examples']}, "
              f"continuity {counts['continuity']}), {len(mine)} examples" + (f"; passed: {'; '.join(missed)}" if missed else ""))
    if total["wrong"]:
        print(f"\n{total['wrong']} wrong rows: {total['any']} refused ({total['any'] / total['wrong']:.0%}); by units {total['units']}, "
              f"by a worked example {total['examples']}, by continuity {total['continuity']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
