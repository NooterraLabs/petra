"""P2's predicate (docs/plan.md §6 P2, docs/in_the_loop.md): an agent reaches PASS within
CHECKS checks on at least SHARE of held-out steel tasks, and no optimum the loop finds
fails the outside judge's geometry.

    python scripts/in_the_loop.py loop [--seed 202] [--n 100] [--workers 4] [--log FILE]
        Run petra.loop.solve on the first n tasks of the seed: repair to PASS, then
        minimise the mass. The outside judge (judges/) reads every design the loop keeps.
        Prints a summary and writes one JSON line per task to --log.
    python scripts/in_the_loop.py briefs DIR --petra PATH [--seed 202] [--agents 10]
        Write one folder per agent task under DIR, each holding BRIEF.md: the job, where
        the petra command is, and how checks are counted. The tasks are the seed's first
        tasks whose drafted design (`petra new KIND` with the job written in) FAILs, so
        each needs a repair.
    python scripts/in_the_loop.py score DIR [--seed 202] [--agents 10]
        Re-check every tryN.petra an agent left in its folder, in order. A task counts as
        reached when a try within CHECKS passes, keeps the job (petra.loop.Task.faithful)
        and the judge finds no violation in it. Prints one row per task and the share.

The numbers below were frozen before any held-out measurement (docs/in_the_loop.md).
Development used DEV_SEED only.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from collections import Counter
from fractions import Fraction
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from judges import judge as outside  # noqa: E402
from petra import loop  # noqa: E402
from petra.lang import parse_design  # noqa: E402
from petra.registry import build_registry  # noqa: E402
from petra.repair import check_text  # noqa: E402
from petra.solvers import SolverSource  # noqa: E402

CHECKS = 10
SHARE = Fraction(4, 5)
HELD_OUT_SEED = 202
DEV_SEED = 101
LOOP_TASKS = 100
AGENT_TASKS = 10

_REGISTRY = None


def registry():
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = build_registry()
    return _REGISTRY


def judged(text: str) -> list[str]:
    """The outside judge's violations of a design, each as `id on subject: reason`."""
    found = outside(parse_design(text, "<judge>", registry()), registry())
    return [f"{v.id} on {v.subject}: {v.reason}" for v in found.violations]


def _solve(task: loop.Task) -> dict:
    start = time.monotonic()
    run = loop.solve(task, registry(), budget=CHECKS, judge=judged)
    return {**run.to_json(), "given": list(task.given), "loads": [[f, str(top)] for f, top in task.loads],
            "basis": task.basis, "passed": run.passed, "optimum": run.optimum,
            "unfaithful": task.faithful(run.optimum, registry()) if run.optimum else [],
            "seconds": round(time.monotonic() - start, 1)}


def cmd_loop(args: argparse.Namespace) -> int:
    tasks = list(loop.tasks(args.seed, args.n, registry()))
    with Pool(args.workers) as pool:
        rows = pool.map(_solve, tasks, chunksize=1)
    if args.log:
        Path(args.log).write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8", newline="\n")
    print(summary(rows, args.seed))
    return 0


def summary(rows: list[dict], seed: int) -> str:
    n = len(rows)
    reached = [r for r in rows if r["checks_to_pass"] is not None and r["checks_to_pass"] <= CHECKS]
    first = [r for r in rows if r["checks_to_pass"] == 1]
    repaired = [r["checks_to_pass"] for r in reached if r["checks_to_pass"] > 1]
    violations = [(r["task"], j) for r in rows for j in r["judged"]]
    ratios = [r["mass_optimum"] / r["mass_passed"] for r in rows if r["mass_optimum"] and r["mass_passed"]]
    kinds = Counter(r["kind"] for r in rows)
    lines = [f"Seed {seed}, {n} tasks, budget {CHECKS} checks.", "",
             f"- Reached PASS within {CHECKS} checks: {len(reached)} of {n} ({len(reached) / n:.0%}); the bar is {float(SHARE):.0%}.",
             f"- The drafted design passed at the first check: {len(first)} of {n}.",
             f"- Checks to PASS where a repair was needed: {len(repaired)} tasks, "
             + (f"median {statistics.median(repaired)}, most {max(repaired)}." if repaired else "none."),
             f"- Designs the loop kept and the judge read: {sum(1 + r['kept'] for r in rows if r['passed'])}. "
             f"Judge violations: {len(violations)}.",
             f"- Optima that change the job: {sum(bool(r['unfaithful']) for r in rows)}.",
             f"- Designs the minimiser checked: {sum(r['probes'] for r in rows)}. "
             f"Seconds per task: median {statistics.median(r['seconds'] for r in rows)}, most {max(r['seconds'] for r in rows)}.",
             (f"- Mass of the optimum over the mass of the first PASS: median {statistics.median(ratios):.2f}, "
              f"range {min(ratios):.2f} to {max(ratios):.2f}." if ratios else "- No optimum."),
             "", "| Kind | Tasks | Reached | Passed at check 1 | Judge violations |", "|---|---|---|---|---|"]
    for kind in loop.TASK_KINDS:
        if kinds[kind]:
            mine = [r for r in rows if r["kind"] == kind]
            lines.append(f"| {kind} | {len(mine)} | {sum(r in reached for r in mine)} | {sum(r in first for r in mine)} | "
                         f"{sum(len(r['judged']) for r in mine)} |")
    missed = [r for r in rows if r not in reached]
    if missed:
        lines += ["", "Missed:"] + [f"- {r['task']} {r['kind']}: {r['attempts']}" for r in missed]
    if violations:
        lines += ["", "Violations:"] + [f"- {t}: {j['violations']}" for t, j in violations]
    changed = [r for r in rows if r["unfaithful"]]
    if changed:
        lines += ["", "Optima that change the job:"] + [f"- {r['task']}: {'; '.join(r['unfaithful'])}" for r in changed]
    return "\n".join(lines)


def agent_tasks(seed: int, count: int) -> list[loop.Task]:
    """The seed's first `count` tasks whose drafted design FAILs."""
    out = []
    for task in loop.tasks(seed, 10 * count, registry()):
        if check_text(task.draft(), "<draft>", registry(), (SolverSource(),), moves=False).status == "FAIL":
            out.append(task)
            if len(out) == count:
                return out
    raise RuntimeError(f"fewer than {count} tasks of seed {seed} need a repair")


BRIEF = """# Task {id}

A user asks you to design a steel connection with Petra, a design checker. Petra is
installed. Run it as:

    {petra}

{job}
## How to work

- Work in this folder: `{folder}`. Change to it before you run anything, and write
  files only there. Use only what the `petra` command prints, its `--help` and its
  documents. Do not read Petra's source files or anything outside this folder.
- Save each design you want checked as `try1.petra`, `try2.petra`, and so on, in this
  folder, and check it with `petra check tryN.petra` (with or without `--json`). Each
  such run is one check, and you have at most {checks}.
- Other `petra` commands, such as `--help`, `docs`, `kinds`, `new` and `registry list`,
  are not checks. Use them as often as you like.
- Do not call Petra from a script or from Python, and do not check any other file.
- Stop at the first PASS, or after {checks} checks.

When you stop, report the number of checks you ran, the status of each, and the file
that passed, if one did.
"""


def cmd_briefs(args: argparse.Namespace) -> int:
    root = Path(args.dir)
    for task in agent_tasks(args.seed, args.agents):
        folder = root / f"task-{task.id}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "BRIEF.md").write_text(BRIEF.format(id=task.id, petra=args.petra, job=task.brief(), folder=folder.resolve().as_posix(),
                                                      checks=CHECKS), encoding="utf-8", newline="\n")
        print(folder)
    return 0


_TRY = re.compile(r"try(\d+)\.petra$")


def cmd_score(args: argparse.Namespace) -> int:
    root = Path(args.dir)
    rows = []
    for task in agent_tasks(args.seed, args.agents):
        folder = root / f"task-{task.id}"
        tries = sorted((p for p in folder.glob("try*.petra") if _TRY.search(p.name)), key=lambda p: int(_TRY.search(p.name)[1]))
        statuses, reached, problems = [], None, []
        for i, path in enumerate(tries, 1):
            text = path.read_text(encoding="utf-8")
            status = check_text(text, path.name, registry(), (SolverSource(),), moves=False).status
            statuses.append(status)
            if status == "PASS" and reached is None:
                problems = task.faithful(text, registry()) + judged(text)
                reached = i
        ok = reached is not None and reached <= CHECKS and not problems
        rows.append(ok)
        print(f"| {task.id} | {task.kind} | {len(tries)} | {' '.join(statuses) or 'none'} | "
              f"{reached if reached is not None else '-'} | {'yes' if ok else 'no'} | {'; '.join(problems) or '-'} |")
    print(f"\nReached a faithful PASS within {CHECKS} checks: {sum(rows)} of {len(rows)} ({sum(rows) / len(rows):.0%}); "
          f"the bar is {float(SHARE):.0%}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("loop")
    run.add_argument("--seed", type=int, default=HELD_OUT_SEED)
    run.add_argument("--n", type=int, default=LOOP_TASKS)
    run.add_argument("--workers", type=int, default=4)
    run.add_argument("--log", metavar="FILE")
    run.set_defaults(run=cmd_loop)
    briefs = commands.add_parser("briefs")
    briefs.add_argument("dir")
    briefs.add_argument("--petra", required=True, metavar="PATH")
    briefs.add_argument("--seed", type=int, default=HELD_OUT_SEED)
    briefs.add_argument("--agents", type=int, default=AGENT_TASKS)
    briefs.set_defaults(run=cmd_briefs)
    score = commands.add_parser("score")
    score.add_argument("dir")
    score.add_argument("--seed", type=int, default=HELD_OUT_SEED)
    score.add_argument("--agents", type=int, default=AGENT_TASKS)
    score.set_defaults(run=cmd_score)
    args = parser.parse_args()
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
