"""One adapter for each benchmark: fetch it, list its tasks, give a task's prompt, grade an answer.

An adapter knows a benchmark's file format and how its grader is called. It knows nothing
of what a task asks: no task id, no task text and no expected value is written in one.
It says whether its grader executes code the model wrote (`executes`), and such a grader
is started through bench/exam/sandbox.py and no other way.

A grade has the benchmark's own score and pass condition, and one of these outcomes, which
are the only thing of a grade that a summary prints:

    pass           the answer met the benchmark's pass condition
    wrong          the answer ran and the grader failed it
    invalid        the grader could not build or run the answer
    no_answer      the reply held nothing the grader takes
    grader_error   the grader itself failed, or ran past its time limit

`--benchmark` takes a name of REGISTRY, or MODULE:NAME for an adapter that lives elsewhere,
which is how the tests bring their toy benchmark.
"""
from __future__ import annotations

import importlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

OUTCOMES = ("pass", "wrong", "invalid", "no_answer", "grader_error")

_FENCED = re.compile(r"^```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\r?\n(.*?)^```[ \t]*$", re.M | re.S)


@dataclass(frozen=True)
class Grade:
    outcome: str                 # one of OUTCOMES
    score: float                 # the benchmark's own score, from 0 to 1
    detail: dict = field(default_factory=dict)      # what the grader said; it stays in the record
    seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise ValueError(f"{self.outcome!r} is not an outcome")

    @property
    def passed(self) -> bool:
        return self.outcome == "pass"

    def to_dict(self) -> dict:
        return {**asdict(self), "passed": self.passed}


class Adapter:
    """What the harness asks of a benchmark. `folder` is the benchmark's own folder under
    the data folder, and nothing of a benchmark is read from anywhere else."""

    name: str = ""
    about: str = ""
    """One general line: what goes in and what comes back."""
    executes: bool = True
    """Whether the grader executes code the model wrote. Such a grader runs in the sandbox (bench/exam/sandbox.py), and
    a run refuses to start when there is none. An adapter that says nothing is taken to execute it."""
    sandboxed: bool = True
    """False when the run was told to grade outside the sandbox (--no-sandbox). A run sets it before it fetches or grades."""

    def fetch(self, folder: Path) -> dict:
        """Bring the benchmark's files into the folder, and make its grader's environment.
        Returns what SOURCE.json holds: the URLs, the version and the hashes."""
        raise NotImplementedError

    def version(self, folder: Path) -> dict:
        """The version the files in the folder were fetched at, for the record."""
        from bench.exam.data import manifest
        found = manifest(folder)
        return found["version"] if found else {}

    def tasks(self, folder: Path) -> list[str]:
        """Every task id, in an order that does not change."""
        raise NotImplementedError

    def prompt(self, folder: Path, task: str) -> str:
        """What the benchmark hands the agent for the task, with how to write the answer."""
        raise NotImplementedError

    def answer(self, reply: str) -> str | None:
        """The part of a reply that the grader takes, or None when there is none."""
        return reply.strip() or None

    def feedback(self, folder: Path, task: str, answer: str | None, timeout: float) -> str | None:
        """What the benchmark itself shows an agent between attempts, or None when it
        defines nothing. It is never the grader's result."""
        return None

    def grade(self, folder: Path, task: str, answer: str | None, timeout: float) -> Grade:
        """The benchmark's own grader on the answer."""
        raise NotImplementedError


def code_block(reply: str, languages: tuple[str, ...] = ("python", "py", "")) -> str | None:
    """The last fenced block of a reply in one of the languages, or None. A block with no
    language counts only when the reply has no block that names one of them."""
    blocks = [(language.lower(), body) for language, body in _FENCED.findall(reply)]
    named = [body for language, body in blocks if language and language in languages]
    bare = [body for language, body in blocks if not language and "" in languages]
    found = named or bare
    return found[-1].strip() + "\n" if found and found[-1].strip() else None


def load(name: str) -> Adapter:
    if ":" in name:
        module, attribute = name.split(":", 1)
        return getattr(importlib.import_module(module), attribute)
    if name not in REGISTRY:
        raise KeyError(f"no benchmark named {name!r}: there is {', '.join(sorted(REGISTRY))}")
    module, attribute = REGISTRY[name].split(":")
    return getattr(importlib.import_module(module), attribute)


REGISTRY: dict[str, str] = {
    "cadtestbench": "bench.exam.adapters.cadtestbench:ADAPTER",
    "cadsilentfailure": "bench.exam.adapters.cadsilentfailure:ADAPTER",
}
