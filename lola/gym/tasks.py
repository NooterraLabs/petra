"""Task generators from parametric requirements. Untrusted.

A task is a .lola file with everything the requirement owner signs (loads, ambient,
claims, environment, waivers) and holes the agent must fill with makeable-set choices.
The kernel's verdict is the whole reward. v0 has no efficiency term: one would have to be
a kernel-checked claim, and v0 has no design-limit claims (an open question in the
rationale).

Domains are named by their lola.models.DOMAINS key. GENERATORS maps a domain name to its
generator; a name outside models.DOMAINS is refused at import, so the gym cannot drift
from the domain registry.

v0 generators:
  circuit   consumer draw in [0, I] with I in {6..32} A, run length in [5, 50] m, an
            ambient sub-range of the indoor_dry class [5, 40] degC, a signed fault level
            up to 6 kA. Holes: breaker, cable, terminal.
  bolt      torque range, external force range [0, F], plate material and environment
            class, with the owner's plate-bearing waiver (v0 has no bearing model).
            Holes: bolt (size and class; zinc-plated parts are left out, since lowering
            refuses coatings), count.

Each hole lists its choices in ascending cost order: cables by area, breakers by rating,
terminals by current rating, bolts by proof capacity. `Task.given` records the owner's
numbers, so an agent can widen a solved task into a family (`family_text`).

generate_truss is not wired into GENERATORS: the truss elaborator is a stub in v0.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Mapping

from ..kernel import Interval, enclose, free_syms
from ..models import DOMAINS
from ..registry import PartKind, Registry

OWNER = "gym.owner@example.org"
AGENT = "gym.agent@example.org"


@dataclass(frozen=True)
class Hole:
    name: str                 # "w1.cable"
    kind: str                 # registry PartKind value, or "count"
    choices: tuple[str, ...]  # makeable-set ids (or counts) the agent may pick from, cheapest first


@dataclass(frozen=True)
class Task:
    id: str                   # "circuit-000042", seed-derived, stable
    domain: str               # a key of lola.models.DOMAINS
    template: str             # .lola text with {{hole}} markers
    holes: tuple[Hole, ...]
    given: tuple[tuple[str, str], ...] = ()   # the owner's numbers and ids, as written in the template


Generator = Callable[[int, Registry], Task]
"""(seed, registry) -> task. Deterministic in its arguments."""

Box = Mapping[str, tuple[Fraction, Fraction]]
"""Family parameter name -> (lo, hi), in the unit the domain's family text gives it."""

CIRCUIT_CURRENTS = (6, 8, 10, 13, 16, 20, 25, 32)
TORQUES = ((20, 25), (40, 50), (80, 100))
BOLT_COUNTS = ("1", "2", "3", "4")


def registry_value(registry: Registry, entry: str, prop: str) -> Interval:
    """An enclosure of a registry property, derived ones included. For ordering and
    pruning only: nothing trusted reads it."""
    expr = registry.expand(entry, prop)
    return enclose(expr, {key: registry.fact(key).value for key in free_syms(expr)})


def _parts(registry: Registry, kind: PartKind, cost: Callable[[str], Fraction], keep: Callable[[str], bool] = lambda pid: True) -> tuple[str, ...]:
    return tuple(sorted((pid for pid, part in registry.parts.items() if part.kind is kind and keep(pid)), key=lambda pid: (cost(pid), pid)))


def generate_circuit(seed: int, registry: Registry) -> Task:
    rng = random.Random(f"lola-gym/circuit/{seed}")
    lo = rng.randint(5, 25)
    given = {
        "task": f"circuit-{seed:06d}",
        "current": str(rng.choice(CIRCUIT_CURRENTS)),
        "length": str(rng.randint(5, 50)),
        "fault": str(rng.randint(1, 6)),
        "ambient_lo": str(lo),
        "ambient_hi": str(rng.randint(max(lo, 30), 40)),
        "voltage": "230",
        "environment": "indoor_dry",
    }
    holes = (
        Hole("cb1.part", PartKind.BREAKER.value, _parts(registry, PartKind.BREAKER, lambda p: registry_value(registry, p, "In").lo)),
        Hole("w1.cable", PartKind.CABLE.value, _parts(registry, PartKind.CABLE, lambda p: registry.parts[p].fixes["area"].lo,
                                                      lambda p: registry.parts[p].series is not None)),
        Hole("t1.part", PartKind.TERMINAL.value, _parts(registry, PartKind.TERMINAL, lambda p: registry_value(registry, p, "current_max").lo)),
    )
    return Task(given["task"], "circuit", _circuit_text(given, {h.name: f"{{{{{h.name}}}}}" for h in holes}, None), holes, tuple(given.items()))


def generate_truss(seed: int, registry: Registry) -> Task:
    raise NotImplementedError("the truss elaborator is a stub in v0, so the gym has no truss tasks yet")


def generate_bolt(seed: int, registry: Registry) -> Task:
    rng = random.Random(f"lola-gym/bolt/{seed}")
    torque = rng.choice(TORQUES)
    given = {
        "task": f"bolt-{seed:06d}",
        "torque_lo": str(torque[0]),
        "torque_hi": str(torque[1]),
        "force": str(rng.randint(2, 30) * 2),
        "plate": rng.choice(("steel.S355", "aluminium.6061_T6")),
        "thickness": str(rng.choice((8, 10, 12, 16))),
        "environment": rng.choice(("indoor_dry", "outdoor_c3")),
    }

    def capacity(pid: str) -> Fraction:
        stress = "Sp" if "Sp" in registry.parts[pid].props else "Rp02_min"
        return registry_value(registry, pid, stress).lo * registry_value(registry, pid, "As").lo

    holes = (
        Hole("j.bolt", PartKind.BOLT.value, _parts(registry, PartKind.BOLT, capacity, lambda p: not p.endswith("_zn"))),
        Hole("j.count", "count", BOLT_COUNTS),
    )
    return Task(given["task"], "bolt", _bolt_text(given, {h.name: f"{{{{{h.name}}}}}" for h in holes}, None), holes, tuple(given.items()))


GENERATORS: Mapping[str, Generator] = {
    "circuit": generate_circuit,
    "bolt": generate_bolt,
}
if not set(GENERATORS) <= set(DOMAINS):
    raise RuntimeError(f"gym generators for unregistered domains: {sorted(set(GENERATORS) - set(DOMAINS))}")


def generate(domain: str, seed: int, registry: Registry) -> Task:
    """Deterministic in (domain, seed, registry). Raises KeyError naming GENERATORS for a
    domain without a generator."""
    if domain not in GENERATORS:
        raise KeyError(f"no gym generator for domain {domain!r}; GENERATORS has {', '.join(sorted(GENERATORS))}")
    return GENERATORS[domain](seed, registry)


def fill(task: Task, choices: Mapping[str, str]) -> str:
    """Substitute choices into the template. Rejects a missing or extra hole and a choice
    outside the hole's list."""
    _check(task, choices)
    text = task.template
    for hole in task.holes:
        text = text.replace(f"{{{{{hole.name}}}}}", choices[hole.name])
    return text


def family_text(task: Task, choices: Mapping[str, str], box: Box) -> str:
    """A family design around a solved task: the holes fixed to `choices`, the owner's
    widenable inputs replaced by params over `box`, everything else as the task has it.
    Circuit params: draw (A), run (m), amb (degC). Bolt params: fa (kN)."""
    _check(task, choices)
    params = _FAMILY_PARAMS[task.domain]
    if set(box) != set(params):
        raise ValueError(f"a {task.domain} family box sets exactly {', '.join(sorted(params))}")
    return _TEXT[task.domain](dict(task.given), dict(choices), box)


def _check(task: Task, choices: Mapping[str, str]) -> None:
    names = {h.name for h in task.holes}
    if set(choices) != names:
        raise ValueError(f"{task.id}: choices must fill exactly the holes {', '.join(sorted(names))}")
    for hole in task.holes:
        if choices[hole.name] not in hole.choices:
            raise ValueError(f"{task.id}: {choices[hole.name]!r} is not a choice for {hole.name}")


def _number(q: Fraction) -> str:
    if q.denominator != 1:
        raise ValueError(f"family bounds are whole numbers, not {q}")
    return str(q.numerator)


def _params(box: Box, units: Mapping[str, str]) -> list[str]:
    return [f"param {name} in [{_number(lo)} {units[name]}, {_number(hi)} {units[name]}]" for name, (lo, hi) in sorted(box.items())]


def _circuit_text(g: Mapping[str, str], parts: Mapping[str, str], box: Box | None) -> str:
    source = f'source "gym task {g["task"]}"'
    if box is None:
        params = []
        ambient = f'ambient in [{g["ambient_lo"]} degC, {g["ambient_hi"]} degC] signed "{OWNER}" {source}'
        length, draw, owner = f'length {g["length"]} m', f'current in [0 A, {g["current"]} A]', OWNER
    else:
        params = [*_params(box, _FAMILY_PARAMS["circuit"]), ""]
        ambient, length, draw, owner = "ambient param amb", "length param run", "current param draw", AGENT
    title = g["task"] if box is None else f'family-{g["task"]}'
    return "\n".join([
        "lola 0",
        "",
        f'design "gym-{title}" {{',
        f'  owner "{owner}"',
        f'  environment {g["environment"]}',
        "}",
        "",
        *params,
        ambient,
        "",
        "circuit c {",
        f'  supply mains voltage {g["voltage"]} V fault_current in [0 kA, {g["fault"]} kA] signed "{OWNER}" {source}',
        f'  breaker cb1 part {parts["cb1.part"]}',
        f'  wire w1 cable {parts["w1.cable"]} {length} install install.clipped_direct',
        f'  terminal t1 part {parts["t1.part"]}',
        "  consumer load",
        "",
        "  connect mains.out -> cb1.in",
        "  connect cb1.out -> w1.a",
        "  connect w1.b -> t1.wire",
        "  connect t1.out -> load.in",
        "}",
        "",
        "load demand {",
        f"  on c.load {draw}",
        f'  signed "{owner}" {source}',
        "}",
        "",
        "claim hot:  c.w1.temperature <= 70 degC under demand",
        "claim drop: c.w1.voltage_drop <= 3 % under demand",
        "",
    ])


def _bolt_text(g: Mapping[str, str], parts: Mapping[str, str], box: Box | None) -> str:
    source = f'source "gym task {g["task"]}"'
    if box is None:
        params, force, owner = [], f'force in [0 kN, {g["force"]} kN]', OWNER
    else:
        params, force, owner = [*_params(box, _FAMILY_PARAMS["bolt"]), ""], "force param fa", AGENT
    title = g["task"] if box is None else f'family-{g["task"]}'
    plate = f'  plate {g["plate"]} thickness {g["thickness"]} mm'
    return "\n".join([
        "lola 0",
        "",
        f'design "gym-{title}" {{',
        f'  owner "{owner}"',
        f'  environment {g["environment"]}',
        "}",
        "",
        *params,
        "joint j {",
        f'  bolt {parts["j.bolt"]} count {parts["j.count"]}',
        plate,
        plate,
        f'  torque in [{g["torque_lo"]} Nm, {g["torque_hi"]} Nm] signed "{OWNER}" {source}',
        f'  nut_factor in [0.16, 0.22] measured "{OWNER}" {source}',
        f'  load_share in [0.10, 0.25] signed "{OWNER}" {source}',
        "}",
        "",
        "load service {",
        f"  on j {force}",
        f'  signed "{owner}" {source}',
        "}",
        "",
        f'waive bolt.plate_bearing on j by "{OWNER}" reason "plate bearing checked by hand in the joint calculation"',
        "",
        "claim tension: j.tension_utilisation <= 0.9 under service",
        "",
    ])


_FAMILY_PARAMS: Mapping[str, Mapping[str, str]] = {
    "circuit": {"amb": "degC", "draw": "A", "run": "m"},
    "bolt": {"fa": "kN"},
}
_TEXT = {"circuit": _circuit_text, "bolt": _bolt_text}
