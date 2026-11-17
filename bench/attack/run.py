"""The runner: makes inputs and judges them until stopped.

    python3.11 -m bench.attack.run [--seed S] [--budget SECONDS] [--jobs N] [--out DIR] [--log FILE]

It takes a seed and a time budget (none: until stopped), uses the cores it is given, keeps
each difference as a folder under DIR/found (see found.py), and appends one line to the log
when it ends, or when it is stopped with SIGINT or SIGTERM, or when a file named STOP appears
in DIR. It needs no model and no network.

The line holds: seed, inputs made, the share that reached the comparison (every reader was
asked) and the share that settled (the kernel gave PASS, FAIL or UNKNOWN), differences,
distinct differences, crashes, hangs, relations checked and broken, wall time.

Another machine runs it the same way (see README.md): the repository, the kernel built for
that machine, Node, and Python 3.11.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import multiprocessing
import os
import random
import re
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "bench" / "attack" / "runs"
LOG = ROOT / "bench" / "attack" / "log.jsonl"

COUNTS = ("made", "reached", "settled", "differences", "crashes", "hangs", "relations", "violations", "new", "internal")


def judge(maker, d, cli: bool):
    from . import readers
    if d.files is not None and d.spec is None:
        return readers.judge_files({**d.files, "rules": d.deck_text})
    card, design = d.texts()
    return readers.judge(card, design, d.deck_text, d.base_text, cli=cli, run=d.run)


def relation(d, base, j, base_draft) -> list:
    """The differences that a relation's two judged inputs show."""
    from . import meta
    from .readers import Diff
    name = d.relation[0]
    if base.verdict.get("kernel") is None or j.verdict.get("kernel") is None:
        return []
    if name in ("units", "units_si"):
        return [Diff("bundle", "grid", f"{n} differs when the numbers are written in other units", key=f"{name}|{n}") for n in ("card", "design") if base.files.get(n) != j.files.get(n)]
    if name == "rename":
        return meta.same(base, j, "rename", d.extra.get("rename"))
    if name in ("reorder", "json", "respell"):
        return meta.same(base, j, name, ordered=False)
    if name == "bind_same":
        return meta.same(base, j, "bind")
    if name in ("load_up", "load_down"):
        return meta.load_check(base, j, d.extra.get("up", True))
    if name == "stronger":
        return meta.stronger_check(base, j)
    if name == "hints":
        return meta.hints_check(base, j)
    return []


def step(maker, stats: collections.Counter, out: Path, seed: int, rng: random.Random, over=lambda: False) -> None:
    from . import bind, found, readers
    maker.hung = None
    drafts = maker.next()
    if maker.hung is not None:         # the Python reader did not finish a design in a minute
        stats["made"] += 1
        stats["hangs"] += 1
        stats["new"] += found.keep(out, maker.hung, readers.Judged(), readers.Diff("hang", "grid", "grid.check took over 60 seconds on this design", key="check|bundle"), seed=seed)
    cli = rng.random() < 1 / readers.Config.cli_share
    judged: list = []
    for d in drafts:
        if over() and judged:
            break
        j = judge(maker, d, cli and d.files is None)
        judged.append(j)
        stats["made"] += 1
        stats["reached"] += j.reached
        stats["settled"] += j.settled
        stats["recipe:" + d.recipe] += 1
        stats["reached:" + d.recipe] += j.reached
        stats["outcome:" + (j.verdict.get("kernel") or j.outcome[:30])] += 1
        if not j.reached:
            stats["unreached:" + d.recipe + ":" + re.sub(r"\d+|\S+\.(?:card|petra):|\"[^\"]*\"", "#", j.outcome)[:110]] += 1
        for diff in j.diffs:
            stats["crashes" if diff.kind == "crash" else "hangs" if diff.kind == "hang" else "differences"] += 1
            stats["new"] += found.keep(out, d, j, diff, seed=seed)
        if d.extra.get("bind"):          # what a draft of the binding expects (bind.expected), held as a relation
            stats["relations"] += 1
            for diff in bind.expected(d.extra, j):
                stats["violations"] += 1
                stats["new"] += found.keep(out, d, j, diff, seed=seed)
        if d.relation and d.relation[1] < len(judged) - 1:
            base_draft, base = drafts[d.relation[1]], judged[d.relation[1]]
            stats["relations"] += 1
            for diff in relation(d, base, j, base_draft):
                stats["violations"] += 1
                stats["new"] += found.keep(out, d, j, diff, base_draft, base, seed=seed)
    # a pair the language read gets a twin under a relation, as often as one in three
    if rng.random() < 0.34 and judged and judged[0].reached and drafts[0].spec is not None and drafts[0].files is None and len(drafts) == 1:
        for c in maker.derive(drafts[0]):
            base, base_draft = judged[0], drafts[0]
            stats["relations"] += 1
            if c.relation[0] in ("units", "units_si"):                  # the same files are the same verdict: compare the files and go no further
                from . import readers
                files = readers.bundle_of(*c.texts(), c.deck_text)
                cj = readers.Judged(files=files or {}, reached=files is not None)
                cj.verdict = dict(base.verdict)
                diffs = relation(c, base, cj, base_draft) if files else []
                for diff in diffs:
                    stats["violations"] += 1
                    stats["new"] += found.keep(out, c, cj, diff, base_draft, base, seed=seed)
                continue
            j = judge(maker, c, False)
            stats["made"] += 1
            stats["reached"] += j.reached
            stats["settled"] += j.settled
            stats["recipe:" + c.recipe] += 1
            stats["reached:" + c.recipe] += j.reached
            stats["outcome:" + (j.verdict.get("kernel") or j.outcome[:30])] += 1
            for diff in j.diffs:
                stats["crashes" if diff.kind == "crash" else "hangs" if diff.kind == "hang" else "differences"] += 1
                stats["new"] += found.keep(out, c, j, diff, seed=seed)
            for diff in relation(c, base, j, base_draft):
                stats["violations"] += 1
                stats["new"] += found.keep(out, c, j, diff, base_draft, base, seed=seed)


def worker(index: int, seed: int, deadline: float | None, out: str, petra: str | None, kernel: str | None, twin: str | None, max_steps: int | None) -> None:
    sys.path.insert(0, str(ROOT))
    if petra:
        sys.path.insert(0, petra)       # first, so that `import petra` reads the copy and not this checkout's
    import petra as _petra              # at once: bench/kernel_grid.py puts this checkout first on the path when it is imported
    del _petra
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    if kernel:
        os.environ["PETRA_VERIFY"] = kernel
    from . import readers
    from .maker import Maker
    readers.Config.kernel = kernel or os.environ.get("PETRA_VERIFY")
    if twin:
        readers.Config.twin = twin
    outdir = Path(out)
    rng = random.Random(f"{seed}/{index}")
    maker = Maker(rng)
    stats: collections.Counter = collections.Counter()
    t0 = time.time()
    n = 0
    stop = outdir / "STOP"
    flag = {"stop": False}
    signal.signal(signal.SIGTERM, lambda *_: flag.update(stop=True))
    signal.signal(signal.SIGINT, lambda *_: flag.update(stop=True))
    while not flag["stop"] and not stop.exists() and (deadline is None or time.time() < deadline) and (max_steps is None or n < max_steps):
        try:
            from .readers import alarm
            with alarm(420):
                step(maker, stats, outdir, seed, rng, lambda: flag["stop"] or stop.exists() or (deadline is not None and time.time() > deadline))
        except Exception:       # noqa: BLE001 a fault of the attacker is kept and the run goes on
            stats["internal"] += 1
            (outdir / "internal").mkdir(exist_ok=True)
            if stats["internal"] <= 5:
                (outdir / "internal" / f"w{index}-{stats['internal']}.txt").write_text(traceback.format_exc(), encoding="utf-8")
        n += 1
        if n % 10 == 0:
            _save(outdir, index, stats, t0, n)
    _save(outdir, index, stats, t0, n)


def _save(outdir: Path, index: int, stats: collections.Counter, t0: float, steps: int) -> None:
    tmp = outdir / f".stats-{index}.tmp"
    import petra
    tmp.write_text(json.dumps({"stats": dict(stats), "wall": time.time() - t0, "steps": steps, "petra": petra.__file__}), encoding="utf-8")
    os.replace(tmp, outdir / f"stats-{index}.json")


def collect(outdir: Path) -> tuple[collections.Counter, float, int]:
    total: collections.Counter = collections.Counter()
    wall, steps = 0.0, 0
    for p in sorted(outdir.glob("stats-*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        total.update(d["stats"])
        total["petra:" + d.get("petra", "")] = 1
        wall = max(wall, d["wall"])
        steps += d["steps"]
    return total, wall, steps


def line(seed: int, jobs: int, budget: float | None, total: collections.Counter, wall: float, steps: int, outdir: Path, note: str) -> dict:
    made = total["made"] or 1
    try:
        head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:       # noqa: BLE001
        head = ""
    distinct = len([p for p in (outdir / "found").glob("*") if p.is_dir()]) if (outdir / "found").exists() else 0
    return {"time": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "head": head, "seed": seed, "jobs": jobs, "budget_s": budget,
            "inputs": total["made"], "reached": total["reached"], "share_reached": round(total["reached"] / made, 4), "settled": total["settled"],
            "share_settled": round(total["settled"] / made, 4), "differences": total["differences"], "distinct": distinct, "crashes": total["crashes"], "hangs": total["hangs"],
            "relations": total["relations"], "relations_broken": total["violations"], "internal_errors": total["internal"], "wall_s": round(wall, 1), "note": note,
            "recipes": {k[7:]: v for k, v in sorted(total.items()) if k.startswith("recipe:")}, "verdicts": {k[8:]: v for k, v in sorted(total.items()) if k.startswith("outcome:")},
            "reads_petra_from": sorted({_where(k[6:]) for k in total if k.startswith("petra:")}),
            "unreached": {k[10:]: v for k, v in sorted(total.items(), key=lambda kv: -kv[1]) if k.startswith("unreached:")}}


def _where(path: str) -> str:
    """Where the workers read petra from, with no path of this machine in it: the summary goes into a tracked file."""
    try:
        Path(path).resolve().relative_to(ROOT)
        return "petra of this checkout"
    except ValueError:
        return "a copy of petra outside this checkout"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seed", type=int, default=int(time.time()) % 100000)
    ap.add_argument("--budget", type=float, default=None, help="seconds to run; none means until stopped")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", type=Path, default=None, help="where found/ and the counts go; default runs/SEED-TIME under bench/attack")
    ap.add_argument("--log", type=Path, default=LOG)
    ap.add_argument("--kernel", default=os.environ.get("PETRA_VERIFY"))
    ap.add_argument("--twin", default=None, help="the third reading, such as bench/twin/verify.mjs; default readers.Config.twin")
    ap.add_argument("--petra", default=None, help="a folder that holds a petra package to read the designs with, in place of this checkout's own")
    ap.add_argument("--max-steps", type=int, default=None, help="steps for each worker, for the tests")
    ap.add_argument("--until", default="", help="stop at the first difference of one of these kinds (verdict, cells, bundle, relation...), for showing that a planted fault is found")
    ap.add_argument("--note", default="")
    args = ap.parse_args(argv)
    if not args.kernel:
        print("no kernel: set PETRA_VERIFY to petra-verify or give --kernel", file=sys.stderr)
        return 2
    out = args.out or OUT / f"{args.seed}-{int(time.time())}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "STOP").unlink(missing_ok=True)
    deadline = time.time() + args.budget if args.budget else None
    ctx = multiprocessing.get_context("spawn")
    procs = [ctx.Process(target=worker, args=(i, args.seed, deadline, str(out), args.petra, args.kernel, args.twin, args.max_steps), daemon=False) for i in range(args.jobs)]
    t0 = time.time()
    for p in procs:
        p.start()

    def stop(*_):
        (out / "STOP").write_text("stop", encoding="utf-8")

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    last = 0.0
    kinds = tuple(k for k in args.until.split(",") if k)
    first = None
    while any(p.is_alive() for p in procs):
        time.sleep(1)
        if kinds and first is None:
            hit = [p.name for p in (out / "found").glob("*") if p.name.startswith(tuple(k + "-" for k in kinds))] if (out / "found").exists() else []
            if hit:
                first = (time.time() - t0, sorted(hit)[0])
                print(f"found {first[1]} after {first[0]:.0f} s", flush=True)
                stop()
        if time.time() - last > 120:
            last = time.time()
            total, wall, steps = collect(out)
            print(f"[{int(time.time() - t0)} s] made {total['made']}, reached {total['reached']}, settled {total['settled']}, differences {total['differences']}, crashes {total['crashes']}, relations broken {total['violations']}", flush=True)
    for p in procs:
        p.join()
    total, wall, steps = collect(out)
    row = line(args.seed, args.jobs, args.budget, total, time.time() - t0, steps, out, args.note)
    if first:
        row["first_hit_s"], row["first_hit"] = round(first[0], 1), first[1]
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=False) + "\n")
    print(json.dumps(row, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
