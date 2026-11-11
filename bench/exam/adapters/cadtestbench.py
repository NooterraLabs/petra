"""CADTestBench: a text requirement in, a CadQuery script out, graded by executable tests.

The dataset is four parquet files on Hugging Face and the grader is the `cadtestbench`
package of the benchmark's repository. Both are pinned by hash below. The repository also
holds four models' answers, which are not fetched.

A task is one prompt of one partition, named PARTITION/SAMPLE. The grader runs the answer
and then each test of that sample on the solid it made, in its own process and in an
empty folder. The benchmark's pass condition is that every test passes, and its score is
the share of tests that pass. The benchmark defines no feedback between attempts.

The grader executes the model's script. That is how the benchmark grades, so it runs in
the sandbox (bench/exam/sandbox.py), on the grader host (bench/exam/host.py).
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from bench.exam import data, host, sandbox
from bench.exam.adapters import Adapter, Grade, code_block

DATASET = "https://huggingface.co/datasets/dimitrismallis/CADTestBench/resolve/2b9a4a972d142d2bc634d072e9d4485f171ced06"
GRADER = "https://raw.githubusercontent.com/dimitrismallis/CADTestBench/e29283cc61db7329039d95b429766a50bfd37f89"
VERSION = {"dataset": "huggingface dimitrismallis/CADTestBench at 2b9a4a972d142d2bc634d072e9d4485f171ced06",
           "grader": "github dimitrismallis/CADTestBench at e29283cc61db7329039d95b429766a50bfd37f89",
           "licence": "MIT"}
FILES = (
    (DATASET, "dataset", "samples/abstract.parquet", "67a5779bc5114ce4db6bc9be89bf22c25e707bc83e7431214cddfac23f980536"),
    (DATASET, "dataset", "samples/detailed.parquet", "76b2d20def7946e1e3216b72a8acb83825c489c373b23ac514b77885ae275b37"),
    (DATASET, "dataset", "cadtests/abstract.parquet", "7ffa58d245c4975e4365bccd2acbaaf2c0622241223cf170bdc952a8e5563713"),
    (DATASET, "dataset", "cadtests/detailed.parquet", "470a47347653fbea969a9b8f1d415bb21cf6ee2a2c1ed46613752ef275b2773a"),
    (DATASET, "dataset", "README.md", "759a09f6597b74d18353be302b7a89b57b428d82f5de8a1c6ab7dd8211063485"),
    (GRADER, "grader", "LICENSE", "1d0dde41ece0f9620937f1a81a67e295ace0eae180c009d862006e8f3b288458"),
    (GRADER, "grader", "README.md", "9f4c2071080faa3ff60976a88b334ee74a39ae5b02a6257adac2bcbc996af1c4"),
    (GRADER, "grader", "pyproject.toml", "c48ab59f3bbdd8a1cca50f6a07a2a9cd8b3c8d21eafd06cb276231606e564b23"),
    (GRADER, "grader", "src/cadtestbench/__init__.py", "ea00373ccc2f57acef06ddcf4e0e6481f5bcad6d70a04f4f6652132542001ff1"),
    (GRADER, "grader", "src/cadtestbench/__main__.py", "3407f7a395a0c24a41bf61c2d89971e3f67e95bd92eb6af8fdd68408c883f499"),
    (GRADER, "grader", "src/cadtestbench/cli.py", "550304678613eb92aad93f220a453f535b080f8642c4b853fea1530d3c8f15fd"),
    (GRADER, "grader", "src/cadtestbench/constants.py", "6ba27a7fe9190011bb4574448ebd8ffa5797886dd47b9395ed51b63e540cef1b"),
    (GRADER, "grader", "src/cadtestbench/data_source.py", "ba06a15dfe5a292a3a3463ad56a777f9fba8e47e3280cd9fedecaabc443f48f6"),
    (GRADER, "grader", "src/cadtestbench/loaders/__init__.py", "aac3e2daf6d783a0688389225c1b5ff6277c95a7186d50259253a66b710c5f85"),
    (GRADER, "grader", "src/cadtestbench/loaders/cadtestbench_loader.py", "e4e42329ff9dac282e2073250bbb1a77a10d3fa9164d95adb4cb0ddf4df99e77"),
    (GRADER, "grader", "src/cadtestbench/metrics/__init__.py", "d2f630617ed425f16234e407271fd1b83b69db6765b336072e981612e10a3f78"),
    (GRADER, "grader", "src/cadtestbench/metrics/cadtest.py", "39dbdc3e44245f2c0972fd2cfbc2e64e261a77ef11ddf568d702854f65ad1c90"),
    (GRADER, "grader", "src/cadtestbench/metrics/interface.py", "fb9f5a1f1921fed2692d4e85bfc9f32870f0607eb47e935ac9b4555b6c4dcab0"),
    (GRADER, "grader", "src/cadtestbench/runner.py", "982d14ae945609bd26abb92326ccc3b7bd37db390ea2748009a91c6129b70dd2"),
)
PACKAGES = ["cadquery==2.8.0", "cadquery-ocp==7.9.3.1.1", "numpy==2.4.6", "trimesh==5.2.0", "datasets==5.2.0", "pyarrow==26.0.1"]
"""The grader's stated dependencies (its pyproject.toml), at the versions the first fetch got."""
HELPER = Path(__file__).with_name("_in_venv.py")

FORM = """

Write the model as one Python file that uses CadQuery (`import cadquery as cq`). Build the geometry in a function `create_cad()` that returns the model, and assign `final_result = create_cad()` at module level. Reply with the whole file in one fenced block that opens with ```python."""
"""How the benchmark's README says an answer is written."""


def in_venv(name: str, folder: Path, mode: str, request: dict, timeout: float, sandboxed: bool = True) -> subprocess.CompletedProcess:
    """Run one mode of the helper in a grader environment on the host, in the sandbox unless the run was told to do
    without: isolated, UTF-8, offline for Hugging Face, with the benchmark's folder to read, and with the request sent
    in on stdin with the helper itself. What it prints on stdout is the mode's result as JSON."""
    program = HELPER.read_text(encoding="utf-8") + f"\nsys.exit(main({mode!r}, json.loads({json.dumps(request)!r})))\n"
    env = {"EXAM_DATA": sandbox.DATA, "PYTHONUTF8": "1", "HF_HUB_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1"}
    return sandbox.run([f"{sandbox.ENV}/bin/python", "-I", "-X", "utf8", "-"], {sandbox.ENV: host.env(name), sandbox.DATA: host.where(folder, name)},
                       env, timeout, input=program, sandboxed=sandboxed)


def given(done: subprocess.CompletedProcess) -> dict | None:
    """What a mode of the helper gave back, or None when it printed no JSON object."""
    try:
        found = json.loads(done.stdout)
    except (ValueError, RecursionError):
        return None
    return found if isinstance(found, dict) else None


class CadTestBench(Adapter):
    name = "cadtestbench"
    about = "a text requirement in, a CadQuery script out; every executable test of the task must pass"

    def fetch(self, folder: Path) -> dict:
        sources = [data.Source(f"{base}/{path}", f"{part}/{path}", digest) for base, part, path, digest in FILES]
        manifest = data.fetch(folder, sources, VERSION)
        host.mirror(folder, self.name)
        host.make_env(self.name, PACKAGES)
        done = in_venv(self.name, folder, "samples", {}, 300, self.sandboxed)
        if done.returncode != 0 or given(done) is None:
            raise RuntimeError(f"could not read the prompts: {done.stderr.strip()[-500:]}")
        (folder / "samples.json").write_text(json.dumps(given(done), indent=0, sort_keys=True), encoding="utf-8")
        return manifest

    def _samples(self, folder: Path) -> dict[str, dict[str, str]]:
        return json.loads((folder / "samples.json").read_text(encoding="utf-8"))

    def tasks(self, folder: Path) -> list[str]:
        return sorted(f"{partition}/{sample}" for partition, rows in self._samples(folder).items() for sample in rows)

    def prompt(self, folder: Path, task: str) -> str:
        partition, sample = task.split("/")
        return self._samples(folder)[partition][sample].strip() + FORM

    def answer(self, reply: str) -> str | None:
        return code_block(reply)

    def grade(self, folder: Path, task: str, answer: str | None, timeout: float) -> Grade:
        if answer is None:
            return Grade("no_answer", 0.0, {"why": "the reply has no fenced python block"})
        partition, sample = task.split("/")
        began = time.monotonic()
        try:
            done = in_venv(self.name, folder, "cadtestbench", {"partition": partition, "sample": sample, "answer": answer}, timeout, self.sandboxed)
        except subprocess.TimeoutExpired:
            done = subprocess.CompletedProcess([], 124, "", "")
        if done.returncode == 124:
            return Grade("grader_error", 0.0, {"why": f"the grader did not finish within {timeout:.0f} s"}, time.monotonic() - began)
        found = given(done) or {}
        if done.returncode != 0 or found.get("exit") or not found.get("summary"):
            return Grade("grader_error", 0.0, {"why": "the grader wrote no result", "exit": found.get("exit") or done.returncode,
                                               "said": done.stderr[-2000:]}, time.monotonic() - began)
        return read(found["summary"], time.monotonic() - began)


def read(result: dict, seconds: float = 0.0) -> Grade:
    """The grade in one sample's summary.json, as the benchmark's own aggregate reads it:
    invalid when the script did not run, a pass when every test passed."""
    metric = (result.get("metrics") or {}).get("cadtest") or {}
    meta = metric.get("metadata") or {}
    summary = meta.get("summary") or {}
    total, passed = summary.get("total_cadtests", 0), summary.get("passed", 0)
    detail = {"passed": passed, "total": total, "rs": summary.get("rs"), "categories": summary.get("category_breakdown"),
              "model_error": meta.get("model_error"), "evaluation_error": summary.get("evaluation_error"),
              "failed": [{"id": t.get("id"), "category": t.get("category"), "message": t.get("message")}
                         for t in meta.get("cadtests") or [] if t.get("status") != "pass"]}
    if not summary or summary.get("evaluation_error") not in (None, "model_load_error"):
        return Grade("grader_error", 0.0, {**detail, "why": result.get("error_message") or metric.get("error")}, seconds)
    if summary.get("model_compile_error") or summary.get("evaluation_error"):
        return Grade("invalid", 0.0, detail, seconds)
    return Grade("pass" if total > 0 and passed == total else "wrong", passed / total if total else 0.0, detail, seconds)


ADAPTER = CadTestBench()
