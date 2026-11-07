"""P3's lift pilot (docs/plan.md §6 P3, docs/pilot_lift.md): do agents design safer steel
connections with Petra than without it?

    python scripts/pilot_lift.py briefs ROOT --petra PATH --python PATH
        Write one folder per task and arm. ROOT/a/task-ID holds BRIEF.md for the agent with
        Petra. ROOT/b/task-ID holds BRIEF.md, reference.md (docs/reference.md) and
        example.petra (the kind's example, which `petra new` prints) for the agent without
        it. The folder names do not name the arm.
    python scripts/pilot_lift.py collect ROOT DIR
        Copy each agent's folder from ROOT/a and ROOT/b to DIR/with_petra and
        DIR/without_petra, leaving out the copies of reference.md and example.petra.
    python scripts/pilot_lift.py reference --log FILE [--workers 4]
        Run petra.loop.solve on each task, with the outside judge reading every design the
        loop keeps, and write one JSON line per task with the optimum and its mass. When the
        loop reaches no PASS, the minimiser starts from the generator's design instead.
    python scripts/pilot_lift.py grade DIR --reference FILE [--adjudication FILE] [--usage FILE] [--json FILE]
        Grade every final.petra under DIR/with_petra and DIR/without_petra. Nothing an agent
        says is trusted: each design gets Petra's verdict at this commit, the job check
        (petra.loop.Task.faithful), the outside judge (judges/) and its mass against the
        reference optimum. The adjudication file says, for each check Petra does not
        certify, whether AISC 360-22 is really violated or Petra is stricter than the code.
        Prints the table per arm and the rows per task.

The tasks are the first TASKS tasks of SEED whose draft FAILs (scripts/in_the_loop.py
agent_tasks), frozen with docs/pilot_lift.md before any held-out run.
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
from dataclasses import asdict, dataclass, field
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from in_the_loop import CHECKS, agent_tasks, judged, registry  # noqa: E402
from judges import judge as outside  # noqa: E402
from petra import loop  # noqa: E402
from petra.lang import parse_design  # noqa: E402
from petra.repair import INPUT_ERRORS, check_text  # noqa: E402
from petra.solvers import SolverSource  # noqa: E402

SEED = 303
TASKS = 10
ARMS = {"a": "with_petra", "b": "without_petra"}
FIT_MODES = ("steel.beam_fit", "steel.flange_fit", "steel.web_fit", "steel.clearance")
"""Checks that decide whether the parts can be built as drawn, not whether they are strong."""
VERDICTS = ("real", "conservative")
"""An adjudicated check: AISC 360-22 (or the Manual method it relies on) is violated at the
design's written values, or the code check holds and Petra fails it by a documented
stricter reading (docs/pilot_lift.md, Grading)."""

JOB_GOAL = """The user wants a connection that is safe under AISC 360-22 for these loads and that
can be built as drawn. Among safe designs, a lighter one is better, but safety comes first.
"""

FINISH = """## When you finish

Save the design you hand to the user as `final.petra` in this folder, and write
`claim.json` beside it, in this form:

    {{"safe": true, "governing": "<the limit state closest to failing>", "utilisation": 0.87, "notes": "<anything the user should know>"}}

Set `safe` to true only if you believe the design is safe under AISC 360-22 for the loads
above and can be built as drawn. Set it to false otherwise, and say why in `notes`.
{report}
"""

BRIEF_WITH = """# Task {id}

A user asks you to design a steel connection with Petra, a design checker. Petra is
installed. Run it as:

    {petra}

Read `petra docs skill` before you start.

{job}
{goal}
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

""" + FINISH

BRIEF_WITHOUT = """# Task {id}

A user asks you to design a steel connection to AISC 360-22.

{job}
{goal}
The user's team records designs in the `.petra` format. `reference.md` in this folder is
the format's reference, and `example.petra` is a design of this kind in that format, sized
for another job. Write your design in that format.

## How to work

- Work in this folder: `{folder}`. Change to it before you run anything, and write
  files only there. Do not read anything outside this folder.
- Python 3.11 with numpy and scipy is at `{python}`. Use it for any calculation.
- Size and check the design yourself, from what you know of AISC 360-22 and the AISC
  Steel Construction Manual. The reference names a program, `petra`, that checks designs.
  It is not available to you. Do not run it, import it, install it or look for it.

""" + FINISH

REPORT_WITH = "\nThen report the file, your claim, and the number of checks you ran with the status of each."
REPORT_WITHOUT = "\nThen report the file and your claim."


def tasks() -> list[loop.Task]:
    return agent_tasks(SEED, TASKS)


def cmd_briefs(args: argparse.Namespace) -> int:
    root = Path(args.root)
    for task in tasks():
        common = dict(id=task.id, job=task.brief(), goal=JOB_GOAL)
        a = root / "a" / f"task-{task.id}"
        a.mkdir(parents=True, exist_ok=True)
        (a / "BRIEF.md").write_text(BRIEF_WITH.format(**common, petra=args.petra, folder=a.resolve().as_posix(), checks=CHECKS,
                                                      report=REPORT_WITH), encoding="utf-8", newline="\n")
        b = root / "b" / f"task-{task.id}"
        b.mkdir(parents=True, exist_ok=True)
        (b / "BRIEF.md").write_text(BRIEF_WITHOUT.format(**common, python=args.python, folder=b.resolve().as_posix(),
                                                         report=REPORT_WITHOUT), encoding="utf-8", newline="\n")
        shutil.copyfile(ROOT / "docs" / "reference.md", b / "reference.md")
        shutil.copyfile(ROOT / "examples" / "steel" / f"{task.kind}.petra", b / "example.petra")
        print(a, b, sep="\n")
    return 0


GIVEN_FILES = ("reference.md", "example.petra")


def cmd_collect(args: argparse.Namespace) -> int:
    for short, arm in ARMS.items():
        for folder in sorted((Path(args.root) / short).glob("task-*")):
            out = Path(args.dir) / arm / folder.name
            out.mkdir(parents=True, exist_ok=True)
            for path in sorted(folder.rglob("*")):
                if path.is_file() and path.name not in GIVEN_FILES and "__pycache__" not in path.parts:
                    target = out / path.relative_to(folder)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, target)
            print(out)
    return 0


# --- The reference optimum ----------------------------------------------------------------------


def _optimum(task: loop.Task) -> dict:
    run = loop.solve(task, registry(), budget=CHECKS, judge=judged)
    start = "draft"
    if run.optimum is None:
        start = "generator design"
        run = loop.Run(task)
        loop._minimise(run, task.reference, registry(), (SolverSource(),), judged)
    return {"task": task.id, "kind": task.kind, "start": start, "checks_to_pass": run.checks_to_pass,
            "mass_optimum": run.mass_optimum, "optimum": run.optimum, "kept": run.kept, "probes": run.probes,
            "judged": [{"design": d, "violations": v} for d, v in run.judged]}


def cmd_reference(args: argparse.Namespace) -> int:
    with Pool(args.workers) as pool:
        rows = pool.map(_optimum, tasks(), chunksize=1)
    Path(args.log).write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8", newline="\n")
    for r in rows:
        print(f"{r['task']} {r['kind']}: optimum {r['mass_optimum']:.1f} lb from the {r['start']}, "
              f"{r['kept']} kept, judge violations {len(r['judged'])}")
    return 0


# --- Grading ------------------------------------------------------------------------------------


@dataclass
class Graded:
    arm: str
    task: str
    kind: str
    status: str                                   # Petra's, or MISSING when there is no final.petra
    uncertified: dict[str, float | None] = field(default_factory=dict)   # mode -> its governing utilisation
    changed: list[str] = field(default_factory=list)                    # what the design changes of the job
    judged: list[str] = field(default_factory=list)                     # the outside judge's violations
    undecided: list[str] = field(default_factory=list)
    claim: bool | None = None
    claim_governing: str | None = None
    mass: float | None = None
    ratio: float | None = None                    # mass over the reference optimum's
    tries: int = 0
    adjudged: dict[str, str] = field(default_factory=dict)
    safe_strict: bool = False                     # Petra PASS on the job, and the judge finds nothing
    safe: bool | None = None                      # no real strength or detailing violation (None: not adjudicated)
    buildable: bool | None = None                 # the judge finds nothing and no fit check is really violated
    usage: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool | None:
        if self.safe is None or self.buildable is None:
            return None
        return self.safe and self.buildable

    @property
    def why_not(self) -> list[str]:
        """Why the design is not safe and buildable: no design Petra can read, a changed job,
        a real violation of a strength or detailing check, or a part that cannot be built."""
        if self.status in ("MISSING", "INPUT_ERROR"):
            return ["unreadable"]
        if self.changed:
            return ["job changed"]
        out = []
        if self.safe is False:
            out.append("unsafe")
        if self.buildable is False:
            out.append("unbuildable")
        return out


def _uncertified(report_json: dict) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for verdict in report_json["verdicts"]:
        for o in verdict["obligations"]:
            if o["outcome"] != "certified":
                mode = o["requirement"].split("/")[1]
                out[mode] = o.get("utilisation")
    return out


def grade_one(arm: str, task: loop.Task, folder: Path, optimum: float | None, adjudication: dict, usage: dict) -> Graded:
    g = Graded(arm, task.id, task.kind, "MISSING", usage=usage.get(f"{arm}/{task.id}", {}))
    g.tries = len(list(folder.glob("try*.petra")))
    claim_path = folder / "claim.json"
    if claim_path.exists():
        try:
            claim = json.loads(claim_path.read_text(encoding="utf-8"))
            g.claim, g.claim_governing = bool(claim.get("safe")), claim.get("governing")
        except json.JSONDecodeError:
            g.claim_governing = "claim.json does not parse"
    final = folder / "final.petra"
    if not final.exists():
        g.safe = g.buildable = False
        return g
    text = final.read_text(encoding="utf-8")
    checked = check_text(text, "final.petra", registry(), (SolverSource(),), moves=False)
    g.status = checked.status
    if checked.report is None:
        g.safe = g.buildable = False
        return g
    g.uncertified = _uncertified(checked.to_json())
    g.changed = task.faithful(text, registry())
    found = outside(parse_design(text, "<judge>", registry()), registry())
    g.judged = [f"{v.id} on {v.subject}: {v.reason}" for v in found.violations]
    g.undecided = list(found.undecided)
    try:
        g.mass = loop.mass(text, registry())
    except (*INPUT_ERRORS, KeyError, AttributeError, TypeError, ValueError):
        g.mass = None
    g.safe_strict = g.status == "PASS" and not g.changed and not g.judged
    if g.changed:
        g.safe = g.buildable = False
        return g
    mine = adjudication.get(f"{arm}/{task.id}", {})
    g.adjudged = {m: mine.get(m, {}).get("verdict") for m in {*g.uncertified, *mine}}
    if any(v not in VERDICTS for v in g.adjudged.values()):
        return g
    g.safe = all(v == "conservative" for m, v in g.adjudged.items() if m not in FIT_MODES)
    g.buildable = not g.judged and all(v == "conservative" for m, v in g.adjudged.items() if m in FIT_MODES)
    if g.ok and g.mass is not None and optimum:
        g.ratio = g.mass / optimum
    return g


def _median(xs: list[float]) -> str:
    return f"{statistics.median(xs):.2f} ({min(xs):.2f} to {max(xs):.2f})" if xs else "none"


def _count(rows: list[Graded], pred) -> str:
    return f"{sum(1 for r in rows if pred(r))} of {len(rows)}"


def table(graded: list[Graded]) -> str:
    by_arm = {arm: [g for g in graded if g.arm == arm] for arm in ARMS.values()}
    called = {arm: [g for g in rows if g.claim] for arm, rows in by_arm.items()}

    def row(name: str, f) -> str:
        return f"| {name} | " + " | ".join(f(by_arm[arm], called[arm]) for arm in ARMS.values()) + " |"

    def usage(key: str, scale: float = 1) -> callable:
        return lambda rows, _: _median([r.usage[key] / scale for r in rows if key in r.usage])

    lines = ["| Measure | With Petra | Without Petra |", "|---|---|---|",
             row("Final designs safe and buildable", lambda rows, _: _count(rows, lambda r: r.ok)),
             row("Petra PASS, job kept, judge finds nothing", lambda rows, _: _count(rows, lambda r: r.safe_strict)),
             row("Called safe by the agent", lambda rows, _: _count(rows, lambda r: r.claim)),
             row("Called safe but not safe and buildable", lambda _, c: _count(c, lambda r: not r.ok)),
             row("... a real AISC 360-22 violation", lambda _, c: _count(c, lambda r: "unsafe" in r.why_not)),
             row("... a part that cannot be built", lambda _, c: _count(c, lambda r: "unbuildable" in r.why_not)),
             row("... a file Petra cannot read, or a changed job", lambda _, c: _count(
                 c, lambda r: bool({"unreadable", "job changed"} & set(r.why_not)))),
             row("Petra fails, but only by its stricter readings", lambda rows, _: _count(
                 rows, lambda r: r.status != "PASS" and r.uncertified and r.ok)),
             row("Mass over the reference optimum, safe designs: median (range)",
                 lambda rows, _: _median([r.ratio for r in rows if r.ratio is not None])),
             row("Score, optimum mass over design mass, 0 when not safe: mean",
                 lambda rows, _: f"{sum(1 / r.ratio for r in rows if r.ratio) / len(rows):.2f}" if rows else "none"),
             row("Checks run: median (range)", usage("checks")),
             row("Tool calls: median (range)", usage("tool_uses")),
             row("Tokens, thousands: median (range)", usage("tokens", 1000)),
             row("Minutes: median (range)", usage("seconds", 60))]
    undecided = [g for g in graded if g.ok is None]
    if undecided:
        lines += ["", "Not yet adjudicated:"] + [f"- {g.arm}/{g.task}: {', '.join(m for m, v in g.adjudged.items() if v not in VERDICTS)}"
                                                 for g in undecided]
    return "\n".join(lines)


def rows(graded: list[Graded]) -> str:
    lines = ["| Arm | Task | Kind | Petra | Not certified | Judge | Claim | Safe | Buildable | Mass, lb | Over optimum |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for g in graded:
        uncertified = ", ".join(f"{m.split('.')[1]} {u:.2f}" if u is not None else m.split(".")[1] for m, u in g.uncertified.items())
        lines.append(f"| {g.arm} | {g.task} | {g.kind} | {g.status} | {uncertified or '-'} | {len(g.judged) or '-'} | "
                     f"{ {True: 'safe', False: 'not safe', None: 'none'}[g.claim]} | {_yes(g.safe)} | {_yes(g.buildable)} | "
                     f"{'-' if g.mass is None else f'{g.mass:.1f}'} | {'-' if g.ratio is None else f'{g.ratio:.2f}'} |")
    return "\n".join(lines)


def _yes(x: bool | None) -> str:
    return {True: "yes", False: "no", None: "?"}[x]


def cmd_grade(args: argparse.Namespace) -> int:
    optima = {r["task"]: r["mass_optimum"] for r in map(json.loads, Path(args.reference).read_text(encoding="utf-8").splitlines())}
    adjudication = json.loads(Path(args.adjudication).read_text(encoding="utf-8")) if args.adjudication else {}
    usage = json.loads(Path(args.usage).read_text(encoding="utf-8")) if args.usage else {}
    graded = [grade_one(arm, task, Path(args.dir) / arm / f"task-{task.id}", optima.get(task.id), adjudication, usage)
              for arm in ARMS.values() for task in tasks()]
    print(table(graded), "", rows(graded), sep="\n")
    for g in graded:
        for v in g.judged + g.changed:
            print(f"- {g.arm}/{g.task}: {v}")
    if args.json:
        Path(args.json).write_text("".join(json.dumps({**asdict(g), "ok": g.ok}, sort_keys=True) + "\n" for g in graded),
                                   encoding="utf-8", newline="\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    briefs = commands.add_parser("briefs")
    briefs.add_argument("root")
    briefs.add_argument("--petra", required=True, metavar="PATH")
    briefs.add_argument("--python", required=True, metavar="PATH")
    briefs.set_defaults(run=cmd_briefs)
    collect = commands.add_parser("collect")
    collect.add_argument("root")
    collect.add_argument("dir")
    collect.set_defaults(run=cmd_collect)
    reference = commands.add_parser("reference")
    reference.add_argument("--log", required=True, metavar="FILE")
    reference.add_argument("--workers", type=int, default=4)
    reference.set_defaults(run=cmd_reference)
    grade = commands.add_parser("grade")
    grade.add_argument("dir")
    grade.add_argument("--reference", required=True, metavar="FILE")
    grade.add_argument("--adjudication", metavar="FILE")
    grade.add_argument("--usage", metavar="FILE")
    grade.add_argument("--json", metavar="FILE")
    grade.set_defaults(run=cmd_grade)
    args = parser.parse_args()
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
