"""Grade the recorded answers of run files again, and print how the new grades compare with the recorded ones.

    python -m bench.exam.regrade [--data DIR] [--grade-timeout S] [--no-sandbox] FILE ...

It calls no model and writes nothing. Every record that holds a grade has its answer graded again by its benchmark's
adapter, in the sandbox, in the order the records were written. It is how a change to the way grades are made, such
as the sandbox, is shown to leave the grades as they were.

It prints totals only, for each file and benchmark: how the grades were made then and now, how many have the outcome
class that was recorded and how many have another, the count for each pair of classes, how many of the same class
have another score, which built-in errors the grader named where the class changed, and the seconds a grade took
then and now. It prints no task id, no text of a task or an answer, and no result of a single task.

Exits 0 when every grade has its recorded class, and 1 otherwise.
"""
from __future__ import annotations

import argparse
import builtins
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bench.exam import data, records, run as exam  # noqa: E402
from bench.exam.adapters import Adapter, load  # noqa: E402
from bench.exam.sandbox import NONE  # noqa: E402

ERRORS = {name for name in dir(builtins) if isinstance(getattr(builtins, name), type) and issubclass(getattr(builtins, name), BaseException)}
"""The names of Python's built-in errors. Only these are counted from what a grader said, so that no word of a task
or an answer can reach the totals."""


def named(detail: dict) -> list[str]:
    """The built-in errors that a grade's detail names, each once, or one word when it names none."""
    return sorted(set(re.findall(r"[A-Za-z]+", json.dumps(detail))) & ERRORS) or ["no built-in error named"]


def again(adapter: Adapter, folder: Path, found: list[dict], timeout: float, sandboxed: bool = True) -> dict:
    """Grade again every record that holds a grade, and count how the new grades compare. No value in what comes
    back names a task or quotes one."""
    how, _ = exam.ready(adapter, folder, sandboxed)
    graded = [record for record in found if record.get("grade")]
    pairs: Counter = Counter()
    errors: Counter = Counter()
    scores = then = now = 0.0
    for record in graded:
        grade = adapter.grade(folder, record["task"], record["answer"], timeout)
        was = record["grade"]
        pairs[(was["outcome"], grade.outcome)] += 1
        if was["outcome"] != grade.outcome:
            errors.update(named(grade.detail))
        elif abs(was["score"] - grade.score) > 1e-9:
            scores += 1
        then += record["seconds"]["grade"] + record["seconds"]["feedback"]
        now += grade.seconds
    same = sum(n for (was, new), n in pairs.items() if was == new)
    return {"benchmark": adapter.name, "grades": len(graded), "made_then": dict(Counter(record.get("sandbox", NONE) for record in graded)),
            "made_now": how, "same_class": same, "another_class": len(graded) - same, "same_class_another_score": int(scores),
            "pairs": [{"recorded": was, "now": new, "grades": n} for (was, new), n in sorted(pairs.items())], "errors_where_the_class_changed": dict(errors),
            "version_stated_otherwise": sum(record["version"] != adapter.version(folder) for record in graded),
            "seconds_recorded": round(then, 1), "seconds_now": round(now, 1)}


def show(row: dict) -> str:
    """The totals of one regrade as text."""
    n = max(row["grades"], 1)
    then = ", ".join(f"{how} {count}" for how, count in sorted(row["made_then"].items())) or "nothing"
    lines = [f"{row['benchmark']}: {row['grades']} grades made again, in {row['made_now']} (recorded as made in: {then})",
             f"  same outcome class {row['same_class']}, another {row['another_class']}; of the same class, another score {row['same_class_another_score']}"]
    lines += [f"  recorded {pair['recorded']}, now {pair['now']}: {pair['grades']}" for pair in row["pairs"]]
    if row["errors_where_the_class_changed"]:
        lines.append("  where the class changed, the grader named: " + ", ".join(f"{name} {count}" for name, count in sorted(row["errors_where_the_class_changed"].items())))
    if row["version_stated_otherwise"]:
        lines.append(f"  {row['version_stated_otherwise']} of these records state the benchmark's version in other words than the files here do")
    lines.append(f"  seconds a grade: {row['seconds_recorded'] / n:.1f} recorded, {row['seconds_now'] / n:.1f} now")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("files", nargs="+", type=Path, metavar="FILE", help="run files")
    parser.add_argument("--data", type=Path, default=data.DATA, help=f"where benchmark files are; default {data.DATA}")
    parser.add_argument("--grade-timeout", type=float, default=300.0, metavar="S", help="seconds the grader may take on one answer")
    parser.add_argument("--no-sandbox", action="store_true", help="grade outside the sandbox, as `run --no-sandbox` does")
    parser.add_argument("--json", action="store_true", help="print the totals as JSON")
    args = parser.parse_args(argv)
    rows = []
    for path in args.files:
        found = records.read(path)
        for benchmark in sorted({record["benchmark"] for record in found}):
            adapter = load(benchmark)
            rows.append(again(adapter, args.data / adapter.name, [r for r in found if r["benchmark"] == benchmark], args.grade_timeout, not args.no_sandbox))
            if not args.json:
                print(show(rows[-1]), flush=True)
    if args.json:
        print(json.dumps(rows, indent=1))
    return 1 if any(row["another_class"] for row in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
