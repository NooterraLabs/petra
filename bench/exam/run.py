"""Sit a benchmark: an agent alone, and the same agent with Petra's reports fed back.

    python -m bench.exam.run --benchmark NAME [--arm alone|petra|both] [--tasks N] [--seed S] [--model CMD]
                             [--attempts K] [--max-calls N] [--fetch] [--shakedown]

Both arms get the same tasks, drawn by the seed, the same model command and the same number
of attempts, K.

    alone   The agent answers the task. A benchmark that shows an agent something between
            attempts (its public feedback) gives a retry, up to K attempts: the retry sees
            the task, the agent's own previous reply and that feedback. Most benchmarks
            show nothing, and then there is one attempt.
    petra   The same, and the agent is also given Petra's guide (petra/docs/skill.md) and
            may hand in a Petra design and card. `petra check` runs on them, and its report
            goes back with the previous reply, up to the same K. A reply that hands in
            nothing gets no report, and without feedback from the benchmark no retry.

The grader's result is never shown to the model. Every attempt is graded and recorded, and
the last attempt's answer is the one that counts.

One record is written for each model call, to a file in the runs folder (records.py says
what it holds). A rerun reads the file and skips what is recorded, so a run that was
stopped goes on where it stopped. A run makes at most `--max-calls` model calls, and stops
when three calls in a row fail. What it prints holds no task id, no text of a task or an
answer, and no result of a single task: only totals, the same that `python -m
bench.exam.summary` prints.

Exits 0 when every chosen task has its final answer, 2 when the run stopped at the cap on
calls, and 1 when it stopped because the model command failed.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import random
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bench.exam import checker, data, model as models, records  # noqa: E402
from bench.exam.adapters import Adapter, load  # noqa: E402

FAILURES = 3
"""A run stops when this many model calls in a row fail."""
RULE = "\n\n---\n\n"


@dataclass
class Settings:
    arms: tuple[str, ...] = records.ARMS
    tasks: int = 10
    seed: int = 1
    model: str = models.DEFAULT
    attempts: int = 2
    max_calls: int = 60
    call_timeout: float = 600.0
    grade_timeout: float = 300.0
    petra_timeout: float = 180.0
    shakedown: bool = False
    guides: list[Path] = field(default_factory=lambda: [checker.GUIDE])


def chosen(adapter: Adapter, folder: Path, count: int, seed: int) -> list[str]:
    """The tasks of a run: `count` of the benchmark's tasks, drawn by the seed. Both arms
    of a seed get the same ones."""
    ids = sorted(adapter.tasks(folder))
    return random.Random(seed).sample(ids, min(count, len(ids)))


def build(adapter: Adapter, folder: Path, task: str, arm: str, attempt: int, previous: dict | None, settings: Settings) -> str:
    """The prompt of one attempt. A retry sees the task again, the agent's own previous
    reply, the benchmark's feedback when it gives any, and in the petra arm Petra's report."""
    parts = [adapter.prompt(folder, task)]
    if arm == "petra":
        parts.append(checker.offer(settings.guides))
    if previous is not None:
        parts.append("Your previous reply was:\n\n" + previous["reply"].strip())
        if previous.get("feedback"):
            parts.append("The benchmark's feedback on that reply:\n\n" + previous["feedback"])
        if arm == "petra":
            parts.append("Petra's report on what you handed in:\n\n" + previous["petra"]["text"])
        last = attempt >= settings.attempts
        ask = f"Give your {'final' if last else 'next'} answer to the task now, whole and in the form asked for above."
        if arm == "petra" and not last:
            ask += " You may hand in a design and a card again."
        parts.append(ask)
    return checker.scrub(RULE.join(parts), data.HOME)


def same(a: str | None, b: str | None) -> bool:
    """Whether two answers are one answer, apart from white space."""
    return re.sub(r"\s+", " ", a or "").strip() == re.sub(r"\s+", " ", b or "").strip()


def run(adapter: Adapter, folder: Path, out: Path, settings: Settings,
        call: Callable[[str, str, float], models.Reply] = models.call, say: Callable[[str], None] = print) -> int:
    """Sit the chosen tasks and append the records to `out`. Returns the exit code."""
    tasks = chosen(adapter, folder, settings.tasks, settings.seed)
    version = adapter.version(folder)
    mine = [r for r in records.read(out) if (r["benchmark"], r["seed"], r["model"], bool(r.get("shakedown")))
            == (adapter.name, settings.seed, settings.model, settings.shakedown)]
    calls = failures = 0
    for number, task in enumerate(tasks, 1):
        for arm in settings.arms:
            history = sorted((r for r in mine if r["task"] == task and r["arm"] == arm and r["model_ok"]), key=lambda r: r["attempt"])
            previous = history[-1] if history else None
            while not (previous and previous["final"]) and (attempt := len(history) + 1) <= settings.attempts:
                if calls >= settings.max_calls:
                    say(f"stopped at the cap of {settings.max_calls} model calls; run again to go on")
                    return 2
                began = time.monotonic()
                prompt = build(adapter, folder, task, arm, attempt, previous, settings)
                reply = call(settings.model, prompt, settings.call_timeout)
                calls += 1
                record = {
                    "format": records.FORMAT, "benchmark": adapter.name, "version": version, "task": task, "arm": arm,
                    "seed": settings.seed, "attempt": attempt, "final": False, "shakedown": settings.shakedown,
                    "model": settings.model, "command": models.describe(settings.model),
                    "prompt": prompt, "prompt_sha256": data.text_hash(prompt), "reply": reply.text, "reply_sha256": data.text_hash(reply.text),
                    "answer": None, "answer_sha256": None, "model_ok": reply.ok, "model_error": reply.error,
                    "feedback": None, "petra": None, "changed": None, "grade": None,
                    "chars": {"prompt": len(prompt), "reply": len(reply.text)},
                    "seconds": {"model": round(reply.seconds, 2), "petra": 0.0, "feedback": 0.0, "grade": 0.0, "attempt": 0.0},
                }
                if not reply.ok:
                    failures += 1
                    finish(out, record, began)
                    say(f"[{number:>3}/{len(tasks)}] {arm:<5} attempt {attempt}: the model call failed ({reply.error.splitlines()[0][:200]})")
                    if failures >= FAILURES:
                        say(f"stopped: {FAILURES} model calls in a row failed")
                        return 1
                    break      # this task and arm wait for a rerun
                failures = 0
                text, design, card = checker.split(reply.text) if arm == "petra" else (reply.text, None, None)
                answer = adapter.answer(text)
                record["answer"], record["answer_sha256"] = answer, data.text_hash(answer) if answer is not None else None
                if arm == "petra":
                    report = checker.check(design, card, settings.petra_timeout)
                    record["petra"], record["seconds"]["petra"] = report.to_dict(), round(report.seconds, 2)
                more = attempt < settings.attempts
                if more:
                    mark = time.monotonic()
                    feedback = adapter.feedback(folder, task, answer, settings.grade_timeout)
                    record["feedback"] = checker.scrub(feedback, data.HOME) if feedback is not None else None
                    record["seconds"]["feedback"] = round(time.monotonic() - mark, 2)
                again = more and (record["feedback"] is not None or bool(record["petra"] and record["petra"]["handed_in"]))
                grade = adapter.grade(folder, task, answer, settings.grade_timeout)
                record["grade"], record["seconds"]["grade"] = grade.to_dict(), round(grade.seconds, 2)
                record["changed"] = None if previous is None else not same(answer, previous["answer"])
                record["final"] = not again
                finish(out, record, began)
                say(f"[{number:>3}/{len(tasks)}] {arm:<5} attempt {attempt}: model {reply.seconds:.0f} s, "
                    f"{len(reply.text):,} characters back, graded in {grade.seconds:.0f} s")
                history.append(record)
                mine.append(record)
                previous = record
    say("every chosen task has its final answer")
    return 0


def finish(out: Path, record: dict, began: float) -> None:
    record["seconds"]["attempt"] = round(time.monotonic() - began, 2)
    record["at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    records.append(out, record)


def run_file(runs: Path, benchmark: str, seed: int, model: str, shakedown: bool = False) -> Path:
    """The file a run's records go to: one for each benchmark, seed and model, and another
    for a shakedown, so that a run that counts never goes on from one that does not."""
    tag = model if re.fullmatch(r"[A-Za-z0-9_.-]+", model) else "command-" + hashlib.sha256(model.encode("utf-8")).hexdigest()[:10]
    return runs / f"{benchmark}-seed{seed}-{tag}{'-shakedown' if shakedown else ''}.jsonl"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--benchmark", required=True, help="a benchmark's name, or MODULE:NAME for an adapter that lives elsewhere")
    parser.add_argument("--arm", choices=(*records.ARMS, "both"), default="both", help="alone, petra, or both on the same tasks")
    parser.add_argument("--tasks", type=int, default=10, metavar="N", help="how many tasks to draw")
    parser.add_argument("--seed", type=int, default=1, help="draws the tasks")
    parser.add_argument("--model", default=models.DEFAULT,
                        help=f"a command that reads a prompt on stdin and prints the answer, or one of: echo, {', '.join(models.PRESETS)}")
    parser.add_argument("--attempts", type=int, default=2, metavar="K", help="the most attempts at a task, in either arm")
    parser.add_argument("--max-calls", type=int, default=60, help="the most model calls this run makes")
    parser.add_argument("--call-timeout", type=float, default=600.0, metavar="S", help="seconds one model call may take")
    parser.add_argument("--grade-timeout", type=float, default=300.0, metavar="S", help="seconds the grader may take on one answer")
    parser.add_argument("--petra-timeout", type=float, default=180.0, metavar="S", help="seconds one `petra check` may take")
    parser.add_argument("--guide", type=Path, action="append", metavar="FILE",
                        help=f"what the petra arm is given to read; default {checker.GUIDE.relative_to(ROOT).as_posix()}")
    parser.add_argument("--data", type=Path, default=data.DATA, help=f"where benchmark files are; default {data.DATA}")
    parser.add_argument("--runs", type=Path, default=data.RUNS, help=f"where records are written; default {data.RUNS}")
    parser.add_argument("--fetch", action="store_true", help="fetch the benchmark and make its grader's environment first")
    parser.add_argument("--shakedown", action="store_true", help="mark the records as a test of the plumbing, whose numbers mean nothing")
    args = parser.parse_args(argv)
    for folder in (args.data, args.runs):
        if why := data.refused(folder):
            parser.error(f"{folder} is {why}, and benchmark files and records stay out of it")
    adapter = load(args.benchmark)
    folder = args.data / adapter.name
    if args.fetch:
        adapter.fetch(folder)
        print(f"fetched {adapter.name}: {len(adapter.tasks(folder))} tasks")
    settings = Settings(arms=records.ARMS if args.arm == "both" else (args.arm,), tasks=args.tasks, seed=args.seed, model=args.model,
                        attempts=args.attempts, max_calls=args.max_calls, call_timeout=args.call_timeout,
                        grade_timeout=args.grade_timeout, petra_timeout=args.petra_timeout, shakedown=args.shakedown,
                        guides=args.guide or [checker.GUIDE])
    out = run_file(args.runs, adapter.name, args.seed, args.model, args.shakedown)
    code = run(adapter, folder, out, settings, say=lambda line: print(line, flush=True))
    print()
    print(records.show(records.totals(records.read(out))))
    return code


if __name__ == "__main__":
    sys.exit(main())
