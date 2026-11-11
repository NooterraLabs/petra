"""Run by a grader environment's Python, never by the harness's own: `python -I -X utf8 _in_venv.py MODE ...`.

It is the only code of the harness that reads a benchmark's files with the benchmark's own
packages. It imports nothing from the repository, so it runs in isolated mode.

    samples DATASET OUT              cadtestbench: write the prompts of both partitions to OUT as JSON
    cadtestbench SRC ARGS...         cadtestbench: put the grader's source on the path and call its command line
    cadsilentfailure ROOT TASK CODE OUT SECONDS
                                     cadsilentfailure: run the benchmark's executor on the code file and its
                                     grader on what the executor measured, and write both to OUT as JSON
"""
import json
import sys
from pathlib import Path


def samples(dataset: str, out: str) -> int:
    import pyarrow.parquet as pq

    found = {}
    for path in sorted((Path(dataset) / "samples").glob("*.parquet")):
        rows = pq.read_table(path, columns=["sample_id", "prompt"]).to_pylist()
        found[path.stem] = {row["sample_id"]: row["prompt"] for row in rows}
    Path(out).write_text(json.dumps(found, indent=0, sort_keys=True), encoding="utf-8")
    return 0


def cadtestbench(source: str, *arguments: str) -> int:
    sys.path.insert(0, source)
    from cadtestbench.cli import main

    return main(list(arguments)) or 0


def cadsilentfailure(root: str, task: str, code: str, out: str, seconds: str) -> int:
    sys.path.insert(0, root)
    from benchmark.executor import Build123dExecutor
    from benchmark.grader import grade
    from benchmark.schema import load_task

    ran = Build123dExecutor(timeout_s=int(float(seconds))).run(Path(code).read_text(encoding="utf-8"))
    graded = grade(load_task(task), ran.props)
    Path(out).write_text(json.dumps({
        "props": ran.props, "error": ran.error, "passed": graded.passed, "score": graded.score, "valid_solid": graded.valid_solid,
        "checks": [{"id": c.id, "passed": c.passed, "value": c.value, "reason": c.reason, "weight": c.weight} for c in graded.checks],
    }), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit({"samples": samples, "cadtestbench": cadtestbench, "cadsilentfailure": cadsilentfailure}[sys.argv[1]](*sys.argv[2:]))
