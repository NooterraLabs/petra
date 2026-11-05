"""Baseline agent. Untrusted.

Policy: enumerate hole choices in ascending cost order (smallest cable, lowest breaker
rating that covers the draw, smallest section). For each candidate, check it locally
with the library first and the solvers second; submit the first that passes. After a
PASS, widen the solved design into a family (current up to the breaker rating, length
up to the voltage-drop limit, the full ambient class) and certify it into the library,
so later tasks near this one reuse it.

The agent's own local check is advisory: the environment re-checks the submission.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..library import Library
from .env import Submission
from .tasks import Task


@dataclass(frozen=True)
class AgentStats:
    tasks: int
    passed: int
    library_hits: int
    families_added: int

    def render(self) -> str:
        """"solved <passed>/<tasks> episodes (library hits <h>, families added <f>)"."""
        raise NotImplementedError


class BaselineAgent:
    def __init__(self, library: Library, registry: object | None = None, max_candidates: int = 64) -> None:
        raise NotImplementedError

    def act(self, task: Task) -> Submission:
        raise NotImplementedError

    def learn(self, task: Task, submission: Submission, reward: float) -> None:
        """On reward 1.0, certify the widened family and add it to the library."""
        raise NotImplementedError

    def stats(self) -> AgentStats:
        raise NotImplementedError


def run_episodes(domains: tuple[str, ...], episodes: int, seed: int, library_root: str | None) -> AgentStats:
    """`lola gym` entry point. Episode i draws domain domains[i % len(domains)] with seed
    seed + i. With no library_root the library lives in a temporary directory."""
    raise NotImplementedError
