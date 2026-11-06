"""Baseline agent. Untrusted.

Policy: enumerate hole choices in ascending cost order (the order each Hole lists them),
by the sum of the per-hole ranks, after pruning choices that cannot fit the task (a
breaker rated below the draw, a terminal that does not take the cable or the breaker's
current). For each candidate, check it locally with the library first and the solvers
second; submit the first that passes, with a certificate for every piece of evidence the
library did not supply. With no pass it submits its best candidate, UNKNOWN before FAIL.

After a PASS, widen the solved design into a family and certify it into the library, so
later tasks near this one reuse it. A circuit family takes the current up to the
breaker rating, the run up to the length a 3 % drop allows at that current, and the full
ambient class; a bolt family takes the force up to four times the task's. When a wide
box does not certify, a narrower one is tried, down to the task's own numbers.

The agent's own local check is advisory: the environment re-checks the submission.
"""
from __future__ import annotations

import contextlib
import itertools
import math
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable, Iterator, Mapping

from .. import __version__
from ..certs import CertificateFile, encode_certificate
from ..kernel import Evidence, Statement
from ..lang import parse_design
from ..library import Library, certify_family
from ..pipeline import Report, check_design
from ..registry import Registry, build_registry
from ..solvers import SolverSource
from ..verdict import STATUS, Discharged
from .env import LolaEnv, Submission
from .tasks import Box, Task, family_text, fill, registry_value

_PREFERENCE = {"PASS": 0, "MARGINAL": 1, "UNKNOWN": 2, "FAIL": 3}
_DROP_MARGIN = Fraction(95, 100)
"""The family's run stops at 95 % of the length a 3 % drop allows at the hottest
conductor, so the solver is not asked to prove a bound with no slack."""


@dataclass(frozen=True)
class AgentStats:
    tasks: int
    passed: int
    library_hits: int
    families_added: int

    def render(self) -> str:
        """"solved <passed>/<tasks> episodes (library hits <h>, families added <f>)"."""
        return f"solved {self.passed}/{self.tasks} episodes (library hits {self.library_hits}, families added {self.families_added})"


class _Collected:
    """Sink: every piece of evidence the kernel accepted in a local check."""

    def __init__(self) -> None:
        self.items: list[tuple[str, Statement, Evidence, str]] = []

    def record(self, statement: Statement, statement_hash: str, evidence: Evidence, source: str) -> None:
        self.items.append((statement_hash, statement, evidence, source))


class _Memo:
    """Source: evidence accepted earlier in the same act, by statement hash. Candidates
    share most statements (a cable's temperature claim does not depend on the
    terminal), so a refutation the solver found once is not searched for again."""

    name = "memo"

    def __init__(self) -> None:
        self.evidence: dict[str, Evidence] = {}

    def offer(self, statement: Statement, statement_hash: str) -> Iterable[Evidence]:
        found = self.evidence.get(statement_hash)
        return () if found is None else (found,)


class BaselineAgent:
    def __init__(self, library: Library, registry: Registry | None = None, max_candidates: int = 64) -> None:
        self.library = library
        self.registry = registry if registry is not None else build_registry()
        self.max_candidates = max_candidates
        self._tasks = 0
        self._passed = 0
        self._hits = 0
        self._added = 0

    def act(self, task: Task) -> Submission:
        best: tuple[int, dict[str, str], tuple[dict, ...], int] | None = None
        memo = _Memo()
        for choices in itertools.islice(self._candidates(task), self.max_candidates):
            report, certificates = self._check(task, choices, memo)
            status = STATUS[type(report.verdict)]
            hits = sum(1 for o in report.outcomes if isinstance(o, Discharged) and o.source == Library.name)
            if best is None or _PREFERENCE[status] < best[0]:
                best = (_PREFERENCE[status], choices, certificates, hits)
            if status == "PASS":
                break
        if best is None:
            return Submission({h.name: h.choices[0] for h in task.holes}, ())
        self._hits += best[3]
        return Submission(best[1], best[2])

    def learn(self, task: Task, submission: Submission, reward: float) -> None:
        """On reward 1.0, certify the widened family and add it to the library."""
        self._tasks += 1
        if reward != 1.0:
            return
        self._passed += 1
        before = self.library.stats()["families"]
        for box in self._widenings(task, submission.choices):
            design = parse_design(family_text(task, submission.choices, box), f"{task.id}.family.petra", self.registry)
            if not certify_family(design, self.registry, self.library).skipped:
                break
        self._added += self.library.stats()["families"] - before

    def stats(self) -> AgentStats:
        return AgentStats(self._tasks, self._passed, self._hits, self._added)

    def _check(self, task: Task, choices: Mapping[str, str], memo: _Memo) -> tuple[Report, tuple[dict, ...]]:
        path = f"{task.id}.petra"
        design = parse_design(fill(task, choices), path, self.registry)
        sink = _Collected()
        report = check_design(design, self.registry, (memo, self.library, SolverSource()), sink=sink, path=path)
        memo.evidence.update((h, e) for h, _, e, source in sink.items if source != Library.name)
        producer = {"source": "gym.baseline", "petra": __version__}
        certificates = tuple(encode_certificate(CertificateFile(h, s, e, producer)) for h, s, e, source in sink.items if source != Library.name)
        return report, certificates

    def _candidates(self, task: Task) -> Iterator[dict[str, str]]:
        allowed = [tuple(c for c in hole.choices if self._fits(task, hole.name, c)) for hole in task.holes]
        for ranks in sorted(itertools.product(*(range(len(a)) for a in allowed)), key=lambda r: (sum(r), r)):
            choices = {hole.name: allowed[i][r] for i, (hole, r) in enumerate(zip(task.holes, ranks))}
            if self._compatible(task, choices):
                yield choices

    def _fits(self, task: Task, hole: str, choice: str) -> bool:
        if task.domain == "circuit" and hole == "cb1.part":
            return self._value(choice, "In") >= Fraction(dict(task.given)["current"])
        return True

    def _compatible(self, task: Task, choices: Mapping[str, str]) -> bool:
        if task.domain != "circuit":
            return True
        terminal, area = choices["t1.part"], self.registry.parts[choices["w1.cable"]].fixes["area"].lo
        return (self._value(terminal, "conductor_min") <= area <= self._value(terminal, "conductor_max")
                and self._value(terminal, "current_max") >= self._value(choices["cb1.part"], "In"))

    def _value(self, entry: str, prop: str) -> Fraction:
        return registry_value(self.registry, entry, prop).lo

    def _widenings(self, task: Task, choices: Mapping[str, str]) -> Iterator[Box]:
        given = dict(task.given)
        if task.domain == "bolt":
            force = Fraction(given["force"])
            for factor in (4, 2, 1):
                yield {"fa": (Fraction(0), factor * force)}
            return
        current, length = Fraction(given["current"]), Fraction(given["length"])
        own = (Fraction(given["ambient_lo"]), Fraction(given["ambient_hi"]))
        environment = self.registry.environment(given["environment"]).ambient.value
        seen: list[Box] = []
        for draw in (self._value(choices["cb1.part"], "In"), current):
            run = max(length, self._run_limit(choices["w1.cable"], Fraction(given["voltage"]), draw))
            for ambient in ((environment.lo, environment.hi), own):
                box = {"draw": (Fraction(0), draw), "run": (Fraction(0), run), "amb": ambient}
                if box not in seen:
                    seen.append(box)
                    yield box

    def _run_limit(self, cable: str, voltage: Fraction, current: Fraction) -> Fraction:
        """Whole metres of run whose 3 % drop holds at `current` with the conductor at its
        rated temperature, less the margin."""
        resistance = (registry_value(self.registry, cable, "R20").hi
                      * (1 + registry_value(self.registry, cable, "alpha").hi * (registry_value(self.registry, cable, "theta_max").hi - 20)))
        return Fraction(math.floor(_DROP_MARGIN * Fraction(3, 100) * voltage / (2 * current * resistance)))


def run_episodes(domains: tuple[str, ...], episodes: int, seed: int, library_root: str | None) -> AgentStats:
    """`petra gym` entry point. Episode i draws domain domains[i % len(domains)] with seed
    seed + i. With no library_root the library lives in a temporary directory."""
    if not domains:
        raise ValueError("the gym needs at least one domain")
    registry = build_registry()
    with contextlib.ExitStack() as stack:
        root = library_root if library_root is not None else stack.enter_context(tempfile.TemporaryDirectory())
        library = Library(root)
        agent = BaselineAgent(library, registry)
        for i in range(episodes):
            env = LolaEnv(domains[i % len(domains)], seed + i, library, registry)
            task = env.reset()
            submission = agent.act(task)
            reward, _ = env.step(submission)
            agent.learn(task, submission, reward)
        return agent.stats()
