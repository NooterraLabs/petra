"""Gym-style environment. The reward is a function of the kernel's verdict only.

    env = LolaEnv("circuit", seed=7, library=Library(path))
    task = env.reset()
    reward, report = env.step(Submission(choices, certificates))

step() fills the task's holes with the submitted choices, re-elaborates the design, and
checks it with exactly two evidence sources: the agent's certificates and the shared
library. It never runs a solver for the agent, so an agent is rewarded only for evidence
it produced or reused. The agent submits choices rather than text, so it cannot rewrite
the owner's loads or claims.

Reward: PASS 1.0, UNKNOWN 0.0, FAIL -1.0 (a FAIL means the agent submitted a design the
premises refute). The report goes back for learning. A FAIL needs refutation evidence,
which only the submission or the library supplies, so an agent that withholds it gets
UNKNOWN instead; no reward above 0 is reachable without a PASS.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Iterable

from ..certs import decode_certificate
from ..kernel import Evidence, Statement
from ..lang import parse_design
from ..library import Library
from ..pipeline import Report, check_design
from ..registry import Registry, build_registry
from ..verdict import STATUS
from .tasks import GENERATORS, Task, fill, generate


@dataclass(frozen=True)
class Submission:
    choices: dict[str, str]
    certificates: tuple[dict, ...]     # certs.CertificateFile JSON envelopes


REWARD = {"PASS": 1.0, "UNKNOWN": 0.0, "FAIL": -1.0}


class _Submitted:
    """The agent's certificates as an evidence source, keyed by the hash each envelope
    proves it belongs to. An envelope that does not decode is set aside with its reason,
    so it costs the agent that evidence and nothing else."""

    name = "submission"

    def __init__(self, certificates: Iterable[object]) -> None:
        self._evidence: dict[str, list[Evidence]] = {}
        self.rejected: list[str] = []
        for i, obj in enumerate(certificates):
            try:
                cert = decode_certificate(obj)  # type: ignore[arg-type]
            except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
                self.rejected.append(f"submitted certificate {i} ignored: {exc}")
                continue
            self._evidence.setdefault(cert.statement_hash, []).append(cert.evidence)

    def offer(self, statement: Statement, statement_hash: str) -> Iterable[Evidence]:
        return tuple(self._evidence.get(statement_hash, ()))


class LolaEnv:
    def __init__(self, domain: str, seed: int, library: Library, registry: Registry | None = None) -> None:
        """`domain` is a key of tasks.GENERATORS. The k-th reset draws the task for seed
        seed + k."""
        if domain not in GENERATORS:
            raise KeyError(f"no gym generator for domain {domain!r}; GENERATORS has {', '.join(sorted(GENERATORS))}")
        self.domain = domain
        self.seed = seed
        self.library = library
        self.registry = registry if registry is not None else build_registry()
        self._resets = 0
        self._task: Task | None = None

    def reset(self) -> Task:
        self._task = generate(self.domain, self.seed + self._resets, self.registry)
        self._resets += 1
        return self._task

    def step(self, submission: Submission) -> tuple[float, Report]:
        """Raises RuntimeError before reset() and ValueError for choices that do not fill
        the task's holes from their lists."""
        if self._task is None:
            raise RuntimeError("call reset() before step()")
        path = f"{self._task.id}.lola"
        design = parse_design(fill(self._task, submission.choices), path, self.registry)
        submitted = _Submitted(submission.certificates)
        report = check_design(design, self.registry, (submitted, self.library), path=path)
        if submitted.rejected:
            report = dataclasses.replace(report, warnings=(*report.warnings, *submitted.rejected))
        return REWARD[STATUS[type(report.verdict)]], report
