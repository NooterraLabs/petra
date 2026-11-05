"""Gym-style environment. The reward is a function of the kernel's verdict only.

    env = LolaEnv("circuit", seed=7, library=Library(path))
    task = env.reset()
    reward, report = env.step(Submission(design_text, certificates))

step() parses the submitted text, re-elaborates it, and checks it with exactly two
evidence sources: the agent's certificates and the shared library. It never runs a
solver for the agent, so an agent is rewarded only for evidence it produced or reused.
The submitted text must equal fill(task, choices) for some legal choices, so the agent
cannot rewrite the owner's loads or claims.

Reward: PASS 1.0, UNKNOWN 0.0, FAIL -1.0 (a FAIL means the agent submitted a design the
premises refute). The report goes back for learning.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..library import Library
from ..pipeline import Report
from .tasks import Task


@dataclass(frozen=True)
class Submission:
    choices: dict[str, str]
    certificates: tuple[dict, ...]     # certs.CertificateFile JSON envelopes


REWARD = {"PASS": 1.0, "UNKNOWN": 0.0, "FAIL": -1.0}


class LolaEnv:
    def __init__(self, domain: str, seed: int, library: Library, registry: object | None = None) -> None:
        """`domain` is a key of tasks.GENERATORS."""
        raise NotImplementedError

    def reset(self) -> Task:
        raise NotImplementedError

    def step(self, submission: Submission) -> tuple[float, Report]:
        raise NotImplementedError
