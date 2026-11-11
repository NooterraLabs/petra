"""Print the totals of runs, and nothing else.

    python -m bench.exam.summary [--runs DIR] [--json] [FILE ...]

With no FILE it reads every run file in the runs folder. It prints, for each benchmark,
model, seed and arm: tasks answered, model calls, final answers that passed, the mean of
the benchmark's own score, outcomes by broad class, what retries did, how often Petra said
anything and with which status, and characters and seconds. It prints no task id, no text
of a task or an answer, and no result of a single task, so its output is the only part of a
run that may be pasted anywhere.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bench.exam import data, records  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("files", nargs="*", type=Path, metavar="FILE", help="run files; default every one in the runs folder")
    parser.add_argument("--runs", type=Path, default=data.RUNS, help=f"the runs folder; default {data.RUNS}")
    parser.add_argument("--json", action="store_true", help="print the totals as JSON")
    args = parser.parse_args(argv)
    files = args.files or sorted(args.runs.glob("*.jsonl"))
    rows = records.totals([record for path in files for record in records.read(path)])
    print(json.dumps(rows, indent=1) if args.json else records.show(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
