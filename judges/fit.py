"""The outside judge: which conditions a design violates that Petra's models never name.

`judge(design, registry)` reads a parsed design (petra.lang.parse_design) and returns a
Judgement: every violated condition, with a stable id from CONDITIONS and a one-line reason
with its numbers, and what it could not decide. It computes geometry and loads itself and
imports nothing from petra.models (tests/test_absurd_judge.py holds it to that), so P1's
geometric model is scored against it, not against itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from petra.ir import Design
from petra.registry import Registry

from . import bolt, circuit, steel, truss, uncertainty

_STEEL_BEAM = ("shear_tab", "double_angle", "single_angle", "shear_tee")


@dataclass(frozen=True)
class Condition:
    id: str
    kinds: tuple[str, ...]
    meaning: str


CONDITIONS: Mapping[str, Condition] = MappingProxyType({c.id: c for c in (
    Condition("steel.beam_side.depth", (*_STEEL_BEAM, "shear_end_plate"),
              "the part on the beam web lies between its flanges, d - 2 tf, unless a cope clears it; an end plate's "
              "welds fit the web between the flanges and copes"),
    Condition("steel.beam_side.fillet", (*_STEEL_BEAM, "shear_end_plate"),
              "a part that clears the beam's flanges also clears its fillets, lying on the flat web, d - 2 kdes"),
    Condition("steel.beam_side.bolts_in_web", _STEEL_BEAM,
              "every beam-side bolt hole lies in the beam's flat web, or in the web a cope leaves"),
    Condition("steel.beam_side.seat_bearing", ("seated", "stiffened_seat"),
              "the beam end lands on its seat: the setback is less than the seat's projection"),
    Condition("steel.support_side.flange_width",
              (*_STEEL_BEAM, "shear_end_plate", "seated", "stiffened_seat", "bolt_bracket", "weld_bracket", "hanger"),
              "bolts and welds on a support flange lie on it, every bolt hole clear of the support's web"),
    Condition("steel.support_side.web_width",
              (*_STEEL_BEAM, "shear_end_plate", "seated", "stiffened_seat", "bolt_bracket", "weld_bracket"),
              "parts and welds on a support web fit between its flanges, d - 2 tf, and bolt holes lie on its flat "
              "web, d - 2 kdes"),
    Condition("steel.support_side.web_fillet",
              (*_STEEL_BEAM, "shear_end_plate", "seated", "stiffened_seat", "bolt_bracket", "weld_bracket"),
              "a part or weld that fits between a support web's flanges also clears its fillets, d - 2 kdes"),
    Condition("steel.support_side.leg_length", ("seated",),
              "a seat's bolt holes lie on its vertical leg, below the outstanding leg"),
    Condition("steel.beam_vs_support.web_clearance",
              (*_STEEL_BEAM, "shear_end_plate", "seated", "stiffened_seat"),
              "a beam whose end lies between a support's flanges has a flange no wider than d - 2 tf between them"),
    Condition("steel.beam_vs_support.beam_end", _STEEL_BEAM,
              "the beam end, where its bolt line and end distance put it, stands clear of the support face and the "
              "parts on it"),
    Condition("circuit.terminal.conductor_area", ("circuit",),
              "every conductor clamped in a terminal lies in the terminal's conductor range"),
    Condition("truss.self_weight", ("truss",),
              "a collapse-factor claim that holds on the design's loads still holds with the members' weight added"),
    Condition("bolt.tension.separation", ("joint",),
              "a tension claim that holds while the plates stay clamped still holds once the force opens the joint "
              "and each bolt carries its whole share, F / n"),
    Condition("uncertain.capacity.tested", ("demand",),
              "a probability claim that holds at the stated capacity still holds at the level where the design's own "
              "tests broke a part, when that level lies below the capacity"),
)})

JUDGED_KINDS = (*steel.READERS, "circuit", "truss", "joint", "demand")
"""The component kinds the judge reads."""


@dataclass(frozen=True)
class Violation:
    id: str
    subject: str
    reason: str


@dataclass(frozen=True)
class Judgement:
    violations: tuple[Violation, ...]
    undecided: tuple[str, ...]

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(v.id for v in self.violations)


def judge(design: Design, registry: Registry) -> Judgement:
    violations: list[Violation] = []
    undecided: list[str] = []
    for name, component in design.components.items():
        if component.kind in steel.READERS:
            try:
                found = steel.facts(component, design)
            except steel.Missing as e:
                undecided.append(f"{name}: {e}")
                continue
        elif component.kind == "circuit":
            found, notes = circuit.facts(component, design, registry)
            undecided += notes
        elif component.kind == "truss":
            found, notes = truss.facts(component, design)
            undecided += notes
        elif component.kind == "joint":
            found, notes = bolt.facts(component, design, registry)
            undecided += notes
        elif component.kind == "demand":
            found, notes = uncertainty.facts(component, design)
            undecided += notes
        else:
            continue
        for fact in found:
            verdict = fact.check()
            if verdict is None:
                continue
            cid, reason = verdict
            if component.kind not in CONDITIONS[cid].kinds:
                raise RuntimeError(f"{cid} raised on a {component.kind}, which CONDITIONS does not list")
            violations.append(Violation(cid, getattr(fact, "subject", name), reason))
    return Judgement(tuple(violations), tuple(undecided))
