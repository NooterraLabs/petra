"""The record of a run: one JSON object a line, one line for each model call.

A run file lives in the runs folder, outside the repository, because a record holds the
task's prompt and the model's reply in full. Only `totals` leaves it: counts by arm, by
benchmark and by outcome, with no task id and no text of a task or an answer.

A record has:

    format, benchmark, version, task, arm, seed, attempt, final, shakedown
    model, command                    the --model value and the command it stands for
    prompt, prompt_sha256             what the model was sent
    reply, reply_sha256               what it printed, whole
    answer, answer_sha256             the part of the reply the grader takes, or null
    model_ok, model_error             false and the reason when the call failed
    feedback                          what the benchmark itself shows before the next attempt, or null
    petra                             the petra arm's report (checker.Report), or null
    changed                           whether the answer differs from the attempt before, or null
    grade                             the grader's result (adapters.Grade), never shown to the model
    sandbox                           how the grade was made: "bwrap VERSION", "none" when the model's code ran with
                                      no sandbox, or "not needed" when the grader executes nothing the model wrote.
                                      A record from before the sandbox has no such field, and counts as "none"
    chars                             prompt and reply lengths in characters
    seconds                           model, petra, feedback, grade, and the whole attempt
    at                                when the record was written, UTC

`final` is true on the attempt whose answer counts. A failed call is recorded with
`model_ok` false and is not an attempt: a rerun makes that call again.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

from bench.exam.adapters import OUTCOMES
from bench.exam.checker import SAID, STATUSES
from bench.exam.sandbox import NONE

FORMAT = "petra-exam/0"
ARMS = ("alone", "petra")
NOTE = "This was a shakedown. It shows that the plumbing runs. Its numbers mean nothing and compare nothing."
BARE = "{n} of {of} grades were made with no sandbox: the model's code ran as the user."


def read(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with open(path, encoding="utf-8") as lines:
        return [json.loads(line) for line in lines if line.strip()]


def append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as out:
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
        out.flush()
        os.fsync(out.fileno())


def totals(records: list[dict]) -> list[dict]:
    """One dict of counts for each benchmark, model, seed and arm in the records. No value
    in it names a task or quotes one."""
    groups: dict[tuple, list[dict]] = {}
    for record in records:
        key = (record["benchmark"], record["model"], record["seed"], bool(record.get("shakedown")), record["arm"])
        groups.setdefault(key, []).append(record)
    out = []
    for (benchmark, model, seed, shakedown, arm), group in sorted(groups.items()):
        ok = [r for r in group if r["model_ok"]]
        by_task: dict[str, list[dict]] = {}
        for record in sorted(ok, key=lambda r: r["attempt"]):
            by_task.setdefault(record["task"], []).append(record)
        done = {task: attempts for task, attempts in by_task.items() if attempts[-1]["final"]}
        finals = [attempts[-1] for attempts in done.values()]
        firsts = [attempts[0] for attempts in done.values()]
        retries = [(a, b) for attempts in by_task.values() for a, b in zip(attempts, attempts[1:])]
        reports = [r["petra"] for r in ok if r.get("petra")]
        after_report = [(a, b) for a, b in retries if a.get("petra") and a["petra"]["handed_in"]]
        row = {
            "benchmark": benchmark, "model": model, "seed": seed, "shakedown": shakedown, "arm": arm,
            "tasks_answered": len(done), "tasks_unfinished": len(by_task) - len(done),
            "calls": len(group), "calls_failed": len(group) - len(ok),
            "grades": sum(bool(r.get("grade")) for r in ok),
            "grades_with_no_sandbox": sum(bool(r.get("grade")) and r.get("sandbox", NONE) == NONE for r in ok),
            "passed": sum(r["grade"]["passed"] for r in finals),
            "mean_score": round(sum(r["grade"]["score"] for r in finals) / len(finals), 4) if finals else None,
            "outcomes": {name: n for name in OUTCOMES if (n := Counter(r["grade"]["outcome"] for r in finals)[name])},
            "passed_on_first_attempt": sum(r["grade"]["passed"] for r in firsts),
            "tasks_with_a_retry": sum(len(attempts) > 1 for attempts in done.values()),
            "retries": len(retries), "retries_that_changed_the_answer": sum(bool(b["changed"]) for _, b in retries),
            "retries_fail_to_pass": sum(not a["grade"]["passed"] and b["grade"]["passed"] for a, b in retries),
            "retries_pass_to_fail": sum(a["grade"]["passed"] and not b["grade"]["passed"] for a, b in retries),
            "prompt_chars": sum(r["chars"]["prompt"] for r in group), "reply_chars": sum(r["chars"]["reply"] for r in group),
            "model_seconds": round(sum(r["seconds"]["model"] for r in group)),
            "grade_seconds": round(sum(r["seconds"]["grade"] + r["seconds"]["feedback"] for r in group)),
            "wall_seconds": round(sum(r["seconds"]["attempt"] for r in group)),
        }
        if arm == "petra":
            count = Counter(report["status"] for report in reports)
            row["petra"] = {
                "replies": len(reports), "said_something": sum(count[s] for s in SAID),
                "by_status": {status: count[status] for status in STATUSES if count[status]},
                "reports_fed_back": len(after_report),
                "next_answer_changed_after_a_report": sum(bool(b["changed"]) for _, b in after_report),
                "seconds": round(sum(r["seconds"]["petra"] for r in ok)),
            }
        out.append(row)
    return out


def show(rows: list[dict]) -> str:
    """The totals as text. This is all of a run that may be pasted anywhere."""
    lines = []
    for key in sorted({(r["benchmark"], r["model"], r["seed"], r["shakedown"]) for r in rows}):
        benchmark, model, seed, shakedown = key
        lines.append(f"{benchmark}, model {model}, seed {seed}")
        if shakedown:
            lines.append(f"  {NOTE}")
        mine = [r for r in rows if (r["benchmark"], r["model"], r["seed"], r["shakedown"]) == key]
        if bare := sum(r["grades_with_no_sandbox"] for r in mine):
            lines.append("  " + BARE.format(n=bare, of=sum(r["grades"] for r in mine)))
        for row in mine:
            outcomes = ", ".join(f"{name} {n}" for name, n in row["outcomes"].items()) or "none"
            score = "-" if row["mean_score"] is None else f"{row['mean_score']:.3f}"
            lines.append(f"  {row['arm']:<6} tasks answered {row['tasks_answered']}, unfinished {row['tasks_unfinished']}; "
                         f"calls {row['calls']}, of which failed {row['calls_failed']}")
            lines.append(f"         final answers: passed {row['passed']} of {row['tasks_answered']}, mean score {score}; outcomes: {outcomes}")
            lines.append(f"         first answers that passed {row['passed_on_first_attempt']}; tasks with a retry {row['tasks_with_a_retry']}; "
                         f"retries {row['retries']}, changed the answer {row['retries_that_changed_the_answer']}, "
                         f"fail to pass {row['retries_fail_to_pass']}, pass to fail {row['retries_pass_to_fail']}")
            if "petra" in row:
                p = row["petra"]
                statuses = ", ".join(f"{name} {n}" for name, n in p["by_status"].items()) or "none"
                lines.append(f"         Petra: said something on {p['said_something']} of {p['replies']} replies ({statuses}); "
                             f"reports fed back {p['reports_fed_back']}, next answer changed after {p['next_answer_changed_after_a_report']}")
            lines.append(f"         characters sent {row['prompt_chars']:,}, received {row['reply_chars']:,}; "
                         f"model {row['model_seconds']} s, grader {row['grade_seconds']} s, wall {row['wall_seconds']} s")
    return "\n".join(lines) if lines else "no records"
