"""The parts domain, derived from RULES. Trusted.

Every table the DomainSpec holds comes from the one table in rules.py: a failure mode per
rule (its id is the rule's), a builder per modelled rule, one coverage rule per demanded
row, and an unmodelled mode per row with no builder. Nothing here names a rule by hand.
"""
from __future__ import annotations

from typing import Any

from ...ir import Design
from ...registry import Registry
from ..base import NO_PORTS, CoverageRule, DomainSpec, EnergyDomain, FailureMode, Feature, FeatureKind, Ports
from . import build
from .lower import ASSEMBLY_GRAMMAR, PART_GRAMMAR, Assembly, PartDesign, lower_assembly, lower_part
from .rules import RULES, Applies, Evaluator, Rule

_MECH = frozenset({EnergyDomain.MECHANICAL})


def mode(rule: Rule) -> FailureMode:
    return FailureMode(rule.id)


def _applies(rule: Rule, feature: Feature, registry: Registry) -> bool:
    if rule.applies is Applies.POLYMER:
        return feature.kind.startswith("parts.part") and registry.material(feature.materials[0]).family == "polymer"
    return feature.kind == rule.applies.value


def coverage_rule(rule: Rule) -> CoverageRule:
    return CoverageRule(rule.id, lambda feature, registry, rule=rule: _applies(rule, feature, registry),
                        (mode(rule),), lambda mode, feature: None, rule.text)


def features(model: Any, design: Design, registry: Registry) -> tuple[Feature, ...]:
    """A part names itself, by its process kind, and each declared hole. An assembly names
    each placed part, each mover, each fastener, each gap line and each press."""
    env = design.environment
    if isinstance(model, PartDesign):
        kind = model.kind.value if model.kind is not None else "bought"
        out = [Feature((model.name,), FeatureKind(f"parts.part.{kind}"), (model.material,),
                       frozenset({EnergyDomain.MECHANICAL, EnergyDomain.THERMAL}), env)]
        for h in model.holes:
            out.append(Feature((model.name, h.id), FeatureKind("parts.hole"), (model.material,), _MECH, env))
            if h.role == "insert":
                out.append(Feature((model.name, h.id), FeatureKind("parts.hole.insert"), (model.material,), _MECH, env))
        return tuple(out)
    asm: Assembly = model
    out = []
    for n, p in enumerate(asm.places):
        out.append(Feature((asm.name, p.body.name), FeatureKind("parts.body"), (p.body.material,), _MECH, env))
        if n:
            out.append(Feature((asm.name, p.body.name), FeatureKind("parts.mover"), (p.body.material,), _MECH, env))
    for f in asm.fastens:
        out.append(Feature((asm.name, f.id), FeatureKind("parts.fasten"), (registry.parts[f.screw].material,), _MECH, env))
    for g in asm.gaps:
        out.append(Feature((asm.name, f"{g.a}~{g.b}"), FeatureKind("parts.gap"), (), _MECH, env))
    for p in asm.presses:
        out.append(Feature((asm.name, p.id), FeatureKind("parts.press"), (), _MECH, env))
    return tuple(out)


def ports(model: Any, registry: Registry) -> Ports:
    """No ports: parts exchange no port quantities in v0."""
    return NO_PORTS


def build_domain() -> DomainSpec:
    modelled = {mode(r): build.build for r in RULES if r.evaluator is not Evaluator.UNMODELLED}
    return DomainSpec(
        name="parts",
        kinds={"part": lower_part, "assembly": lower_assembly},
        builders=modelled,
        unmodelled=frozenset(mode(r) for r in RULES if r.evaluator is Evaluator.UNMODELLED),
        qois={"mass": FailureMode("parts.mass"), "cg_x": FailureMode("parts.cg"), "cg_y": FailureMode("parts.cg"),
              "cg_z": FailureMode("parts.cg")},
        probability={},
        coverage=tuple(coverage_rule(r) for r in RULES if r.applies is not Applies.CLAIM),
        models=build.mode_models(),
        features=features,
        ports=ports,
        grammars={"part": PART_GRAMMAR, "assembly": ASSEMBLY_GRAMMAR},
    )


DOMAIN = build_domain()
