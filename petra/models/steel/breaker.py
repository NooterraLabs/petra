"""The breaker for the steel deck's gate (docs/steel_connections.md §8, §9 item 7). Tooling:
nothing here changes a verdict.

An optimiser that hunts for a false PASS: a design the deck passes and an independent
check fails. Each run starts from a passing generated design and climbs: it raises the
loads, nudges one length by 1/16 to 1/2 in, or swaps a fillet or plate size, keeps a move
when the deck still passes and the oracle's worst utilisation does not fall, and records
any point where the oracle's utilisation passes 1 while the deck says PASS. The oracle is
the twin elaborator by default (twin.py, written apart from the deck), any function from a
card's text and a design's to utilisations by mode otherwise. A raised load is an edit to
the card, and every other move an edit to the design. The budget is fixed in deck
evaluations, and every run is logged: its start, its steps, its best point and what it found.
"""
from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Callable

from ...lang import parse_design
from ...pipeline import check_design
from ...registry import Registry
from ...solvers import SolverSource
from ...verdict import STATUS
from ..base import ComponentError
from .generate import PLATES, WELDS, Generated

Oracle = Callable[[str, str], dict[str, float]]
"""(card, design) -> utilisation by mode."""
SLACK = 1e-6
"""The oracle computes in floats: past 1 + SLACK is a fail."""

STEPS = tuple(Fraction(n, 16) for n in (1, 2, 4, 8))
NUDGED = ("pitch", "edge_vertical", "plate_edge", "bolt_line", "beam_edge", "top", "beam_gauge", "support_gauge", "gauge",
          "eccentricity", "weld_length", "weld_return", "free_edge", "tee_gauge", "plate_width", "seat_length", "setback",
          "stiffener_width", "stiffener_length", "bearing_length", "distance", "unbraced_length")


@dataclass
class Run:
    base: str
    kind: str
    seed: int
    evaluations: int = 0
    accepted: int = 0
    best: float = 0.0                    # the oracle's worst utilisation at the best passing point
    best_mode: str = ""
    best_hash: str = ""
    found: list[dict] = field(default_factory=list)   # false PASSes: the card, the text, the oracle's modes past 1

    def log(self) -> dict:
        return {"base": self.base, "kind": self.kind, "seed": self.seed, "evaluations": self.evaluations,
                "accepted": self.accepted, "best": round(self.best, 6), "best_mode": self.best_mode,
                "best_hash": self.best_hash, "false_pass": [{"hash": f["hash"], "modes": f["modes"]} for f in self.found]}


def twin_oracle(registry: Registry) -> Oracle:
    from . import twin

    def oracle(card: str, text: str) -> dict[str, float]:
        return twin.utilisations_of(parse_design(card, text, "breaker.petra", registry), registry, "gate")["c1"]
    return oracle


def deck_status(card: str, text: str, registry: Registry) -> str:
    try:
        design = parse_design(card, text, "breaker.petra", registry)
        return STATUS[type(check_design(design, registry, (SolverSource(),)).verdict)]
    except ComponentError:
        return "REJECTED"


def _digest(card: str, text: str) -> str:
    return hashlib.sha256(card.encode() + b"\0" + text.encode()).hexdigest()[:16]


def _move(card: str, text: str, rng: random.Random) -> tuple[str, str] | None:
    """One random move from the card and the design `text`, or None when the move does not
    apply."""
    roll = rng.random()
    if roll < 0.45:
        factor = Fraction(rng.randint(101, 108), 100)

        def raised(m: re.Match) -> str:
            return f"  on c1 {m.group(1)} in [0 kip, {float(Fraction(m.group(2)) * factor):.3f} kip]"
        return re.sub(r"^  on c1 (\w+) in \[0 kip, ([0-9.]+) kip\]$", raised, card, flags=re.M), text
    if roll < 0.85:
        keys = [k for k in NUDGED if re.search(rf"^  {k} [0-9.]+ inch$", text, re.M)]
        if not keys:
            return None
        key = rng.choice(keys)
        old = Fraction(re.search(rf"^  {key} ([0-9.]+) inch$", text, re.M).group(1))
        new = old + rng.choice(STEPS) * rng.choice((-1, 1))
        if new <= 0:
            return None
        return card, re.sub(rf"^  {key} [0-9.]+ inch$", f"  {key} {float(new):g} inch", text, count=1, flags=re.M)
    if roll < 0.93:
        m = re.search(r"^  (weld|support_weld) (.*)size ([0-9.]+) inch(.*)$", text, re.M)
        if not m:
            return None
        return card, text.replace(m.group(0), f"  {m.group(1)} {m.group(2)}size {rng.choice(WELDS)} inch{m.group(4)}", 1)
    m = re.search(r"^  (plate|stiffener) (\S+) thickness ([0-9.]+) inch$", text, re.M)
    if not m:
        return None
    return card, text.replace(m.group(0), f"  {m.group(1)} {m.group(2)} thickness {rng.choice(PLATES)} inch", 1)


def run(g: Generated, registry: Registry, oracle: Oracle, budget: int, seed: int) -> Run:
    """Climb from `g` for `budget` deck evaluations."""
    rng = random.Random(f"breaker:{seed}:{g.name}")
    out = Run(g.name, g.kind, seed)
    at = (g.card, g.text)
    u = oracle(*at)
    out.best, out.best_mode = max(((v, m) for m, v in u.items()), default=(0.0, ""))
    out.best_hash = _digest(*at)
    while out.evaluations < budget:
        moved = _move(*at, rng)
        if moved is None or moved == at:
            continue
        out.evaluations += 1
        if deck_status(*moved, registry) != "PASS":
            continue
        try:
            u = oracle(*moved)
        except (ComponentError, KeyError, ValueError, ZeroDivisionError):
            continue
        past = sorted(m for m, v in u.items() if v > 1 + SLACK)
        if past:
            out.found.append({"hash": _digest(*moved), "modes": past, "card": moved[0], "text": moved[1]})
        worst, mode = max(((v, m) for m, v in u.items()), default=(0.0, ""))
        if worst >= out.best:
            at, out.best, out.best_mode, out.best_hash = moved, worst, mode, _digest(*moved)
            out.accepted += 1
    return out
