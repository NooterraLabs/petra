"""cad-silent-failure-bench: a text specification in, build123d code out, graded on measured geometry.

The benchmark's repository holds the tasks as JSON files and the grader as a small Python
package. One archive of the repository is fetched at a pinned commit, and only the tasks,
the grader and the licences are kept from it: the reference solutions and the published
answers of other models never reach the disk.

A task's prompt is the benchmark's own: its system text, read from the source of its
agent module without running it, then the specification and the units. The grader runs
the code in a child process, measures the solid with the CAD kernel, and holds the
measurements to the task's checks. The pass condition is that every check passes, and the
score is the weighted share that pass.

The benchmark defines feedback between attempts, in its tool-use condition: the measured
properties of the agent's own solid, or the error its code raised. `feedback` gives the
same six properties. It never gives a check or its result.

The grader executes the model's code. That is how the benchmark grades, and it is not a
sandbox: the code runs as this user, held only by the time limit.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

from bench.exam import data
from bench.exam.adapters import Adapter, Grade
from bench.exam.adapters.cadtestbench import in_venv

COMMIT = "c95d9ebedd5a3ce0c36513cb41768cdc63ef1369"
ARCHIVE = f"https://codeload.github.com/rodriguescarson/cad-silent-failure-bench/zip/{COMMIT}"
VERSION = {"repository": f"github rodriguescarson/cad-silent-failure-bench at {COMMIT}", "suite": "v1.1",
           "licence": "MIT for the code, CC BY 4.0 for the tasks"}
KEEP = ["tasks/*.json", "benchmark/*.py", "LICENSE", "LICENSE-DATA", "README.md", "ERRATA.md", "requirements.txt", "docs/HARNESS.md",
        "scripts/regrade.py"]
DIGEST = "fcadf7b8740ce4ed1c24cd2ab379f92204eade186ed5aba96c3885acf3a4924c"
"""The hash of the kept files' sorted "PATH HASH" lines (data.fetch_archive)."""
PACKAGES = ["build123d==0.11.1", "cadquery-ocp-novtk==7.9.3.1.1", "numpy==2.4.6"]
"""The kernel the benchmark's README names, at the versions the first fetch got."""
SHOWN = ("valid_solid", "bbox", "volume", "com", "solid_count", "cylinders")
"""The measured properties the benchmark's tool-use condition shows the agent."""
_CODE = re.compile(r"```(?:python)?\s*(.*?)```", re.S)
"""The benchmark's own rule for the code in a reply: the first fenced block."""


class CadSilentFailure(Adapter):
    name = "cadsilentfailure"
    about = "a text specification in, build123d code out; every check on the measured solid must pass"

    def __init__(self) -> None:
        self._ran: dict[tuple[str, str], dict] = {}

    def fetch(self, folder: Path) -> dict:
        manifest = data.fetch_archive(folder, ARCHIVE, KEEP, VERSION, DIGEST)
        data.make_venv(self.name, PACKAGES)
        return manifest

    def tasks(self, folder: Path) -> list[str]:
        return sorted(path.stem for path in (folder / "tasks").glob("*.json"))

    def _system(self, folder: Path) -> str:
        """The value of SYSTEM in the benchmark's agent module, read from its source."""
        tree = ast.parse((folder / "benchmark" / "agents.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SYSTEM" for t in node.targets):
                return ast.literal_eval(node.value)
        raise ValueError("the benchmark's agent module states no SYSTEM")

    def prompt(self, folder: Path, task: str) -> str:
        spec = json.loads(data.inside(folder / "tasks", f"{task}.json").read_text(encoding="utf-8"))
        return f"{self._system(folder)}\n\nSpecification (task {spec['id']}):\n{spec['nl_spec']}\n\nUnits: {spec.get('units', 'mm')}."

    def answer(self, reply: str) -> str | None:
        found = _CODE.search(reply)
        return found.group(1).strip() + "\n" if found and found.group(1).strip() else None

    def _run(self, folder: Path, task: str, answer: str, timeout: float) -> dict:
        """The executor and the grader on one answer. An answer is run once: feedback and
        grade read the same run."""
        key = (task, data.text_hash(answer))
        if key not in self._ran:
            with tempfile.TemporaryDirectory() as work:
                code, out = Path(work) / "answer.py", Path(work) / "out.json"
                code.write_text(answer, encoding="utf-8", newline="\n")
                arguments = ["cadsilentfailure", str(folder), str(folder / "tasks" / f"{task}.json"), str(code), str(out), str(timeout)]
                try:
                    done = in_venv(self.name, arguments, timeout + 30)
                except subprocess.TimeoutExpired:
                    return {"harness_error": f"the grader did not finish within {timeout + 30:.0f} s"}
                if done.returncode != 0 or not out.is_file():
                    return {"harness_error": "the grader wrote no result", "exit": done.returncode, "said": (done.stdout + done.stderr)[-2000:]}
                self._ran[key] = json.loads(out.read_text(encoding="utf-8"))
        return self._ran[key]

    def feedback(self, folder: Path, task: str, answer: str | None, timeout: float) -> str | None:
        if answer is None:
            return "No ```python block found. Provide one assigning `result`."
        ran = self._run(folder, task, answer, timeout)
        if "harness_error" in ran:
            return "Your code could not be measured."
        if ran.get("error") or not ran.get("props"):
            return f"Execution error: {ran.get('error')}"
        return "Kernel-measured properties of your solid:\n" + json.dumps({k: ran["props"].get(k) for k in SHOWN}, indent=1)

    def grade(self, folder: Path, task: str, answer: str | None, timeout: float) -> Grade:
        if answer is None:
            return Grade("no_answer", 0.0, {"why": "the reply has no fenced block"})
        began = time.monotonic()
        ran = self._run(folder, task, answer, timeout)
        seconds = time.monotonic() - began
        if "harness_error" in ran:
            return Grade("grader_error", 0.0, ran, seconds)
        detail = {"error": ran.get("error"), "valid_solid": ran.get("valid_solid"),
                  "checks": len(ran.get("checks") or []), "failed": [c for c in ran.get("checks") or [] if not c["passed"]]}
        if not ran.get("props"):
            return Grade("invalid", 0.0, detail, seconds)
        return Grade("pass" if ran["passed"] else "wrong", float(ran["score"]), detail, seconds)


ADAPTER = CadSilentFailure()
