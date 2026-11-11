"""Run by a grader environment's Python, never by the harness's own, and in the sandbox (bench/exam/sandbox.py).

The harness sends this file to `python -I -X utf8 -` on stdin, with one line added at the end that calls `main` with
a mode and a request. So the file is not on disk where the grader runs, and what a grader is asked goes in with it.
It imports nothing from the repository. The benchmark's fetched files are in the folder that EXAM_DATA names.

    samples                                    cadtestbench: the prompts of both partitions
    cadtestbench PARTITION SAMPLE ANSWER       cadtestbench: write the answer where the grader's command line looks
                                               for it, call that command line, and give back the summary it wrote
    cadsilentfailure TASK ANSWER SECONDS       cadsilentfailure: run the benchmark's executor on the answer and its
                                               grader on what the executor measured, and give back both

A mode runs in a new empty folder, which is also its home, and its result is printed as one JSON value. Standard
output is kept for that value alone: what the grader or the answer prints goes to standard error.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

DATA = os.environ.get("EXAM_DATA", "")


def samples() -> dict:
    import pyarrow.parquet as pq

    found = {}
    for path in sorted((Path(DATA) / "dataset" / "samples").glob("*.parquet")):
        rows = pq.read_table(path, columns=["sample_id", "prompt"]).to_pylist()
        found[path.stem] = {row["sample_id"]: row["prompt"] for row in rows}
    return found


def cadtestbench(partition: str, sample: str, answer: str) -> dict:
    sys.path.insert(0, str(Path(DATA) / "grader" / "src"))
    from cadtestbench.cli import main as command_line

    work = Path.cwd()
    model = work / "run" / "generated_models" / sample
    model.mkdir(parents=True)
    (model / "gpt_generated.py").write_text(answer, encoding="utf-8", newline="\n")
    try:
        code = command_line(["evaluate", str(work / "run"), "--partition", partition, "--dataset", str(Path(DATA) / "dataset"),
                             "--eval-root", str(work / "eval"), "--sample-ids", sample]) or 0
    except SystemExit as stop:
        code = stop.code or 0
    found = sorted((work / "eval").glob(f"*/samples/{sample}/summary.json"))
    return {"exit": code, "summary": json.loads(found[-1].read_text(encoding="utf-8")) if found else None}


def cadsilentfailure(task: str, answer: str, seconds: float) -> dict:
    sys.path.insert(0, DATA)
    from benchmark.executor import Build123dExecutor
    from benchmark.grader import grade
    from benchmark.schema import load_task

    ran = Build123dExecutor(timeout_s=int(seconds)).run(answer)
    graded = grade(load_task(str(Path(DATA) / "tasks" / f"{task}.json")), ran.props)
    return {"props": ran.props, "error": ran.error, "passed": graded.passed, "score": graded.score, "valid_solid": graded.valid_solid,
            "checks": [{"id": c.id, "passed": c.passed, "value": c.value, "reason": c.reason, "weight": c.weight} for c in graded.checks]}


MODES = {"samples": samples, "cadtestbench": cadtestbench, "cadsilentfailure": cadsilentfailure}


def main(mode: str, request: dict) -> int:
    """Run one mode in a new empty folder and print its result. Whatever else is printed meanwhile goes to stderr."""
    result = os.dup(1)
    os.dup2(2, 1)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as work:
        os.environ.update(HOME=work, HF_HOME=str(Path(work) / "hf"))
        os.chdir(work)
        try:
            found = MODES[mode](**request)
        finally:
            os.chdir(tempfile.gettempdir())
    with os.fdopen(result, "w", encoding="utf-8") as out:
        json.dump(found, out)
    return 0
