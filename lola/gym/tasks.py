"""Task generators from parametric requirements. Untrusted.

A task is a .lola file with everything the requirement owner signs (loads, ambient,
claims, environment) and holes the agent must fill with makeable-set choices. The
kernel's verdict is the whole reward. v0 has no efficiency term: one would have to be a
kernel-checked claim, and v0 has no design-limit claims (an open question in the
rationale).

Domains are named by their lola.models.DOMAINS key. GENERATORS maps a domain name to its
generator; a name outside models.DOMAINS is refused at import, so the gym cannot drift
from the domain registry.

v0 generators:
  circuit   consumer draw in [0, I] with I in {6..32} A, run length in [5, 50] m,
            ambient sub-range of [0, 45] degC, signed fault level. Holes: cable, breaker,
            terminal.
  truss     span in [3, 8] m, panel count in {2, 3, 4}, signed node loads. Holes: one
            section per member group.
  bolt      external force range and mean, environment class. Holes: bolt size, class,
            coating, count.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from ..models import DOMAINS
from ..registry import Registry


@dataclass(frozen=True)
class Hole:
    name: str                 # "w1.cable"
    kind: str                 # registry PartKind or "material"
    choices: tuple[str, ...]  # makeable-set ids the agent may pick from


@dataclass(frozen=True)
class Task:
    id: str                   # "circuit-000042", seed-derived, stable
    domain: str               # a key of lola.models.DOMAINS
    template: str             # .lola text with {{hole}} markers
    holes: tuple[Hole, ...]


Generator = Callable[[int, Registry], Task]
"""(seed, registry) -> task. Deterministic in its arguments."""


def generate_circuit(seed: int, registry: Registry) -> Task:
    raise NotImplementedError


def generate_truss(seed: int, registry: Registry) -> Task:
    raise NotImplementedError


def generate_bolt(seed: int, registry: Registry) -> Task:
    raise NotImplementedError


GENERATORS: Mapping[str, Generator] = {
    "circuit": generate_circuit,
    "truss": generate_truss,
    "bolt": generate_bolt,
}
if not set(GENERATORS) <= set(DOMAINS):
    raise RuntimeError(f"gym generators for unregistered domains: {sorted(set(GENERATORS) - set(DOMAINS))}")


def generate(domain: str, seed: int, registry: Registry) -> Task:
    """Deterministic in (domain, seed, registry). Raises KeyError naming GENERATORS for a
    domain without a generator."""
    raise NotImplementedError


def fill(task: Task, choices: dict[str, str]) -> str:
    """Substitute choices into the template. Rejects a choice outside the hole's list."""
    raise NotImplementedError
