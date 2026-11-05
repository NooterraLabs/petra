"""The certificate-rule registry: the one place that lists the rules.

To add a rule (continuum FE, reduced basis, a neural surrogate): write
`kernel/rules/<module>.py` with its goal, evidence and lemma types, its check functions
and one `RULE = RuleSpec(...)`, add `RULE` to `_REGISTERED`, and write
`lola/solvers/<module>.py`. Nothing in check.py or codec.py changes. Every table below is
derived from `_REGISTERED`, and the solver for a rule is found by its module name.

The typing aliases at the bottom are written out for readers and static checkers.
tests/test_structure.py fails when an alias and the registry disagree.
"""
from __future__ import annotations

from dataclasses import fields
from types import MappingProxyType
from typing import Mapping, Union

from . import r1_linear, r2_definite, r3_hypercircle, r4_enclosure, r5_moment, r6_scenario
from .base import Fault, Invalid, Lemma, RuleSpec, TooWeak

_REGISTERED: tuple[RuleSpec, ...] = (
    r1_linear.RULE,
    r2_definite.RULE,
    r3_hypercircle.RULE,
    r4_enclosure.RULE,
    r5_moment.RULE,
    r6_scenario.RULE,
)


def _index(registered: tuple[RuleSpec, ...]) -> tuple[Mapping, ...]:
    rules: dict[str, RuleSpec] = {}
    goal_rule: dict[type, RuleSpec] = {}
    proof_rule: dict[type, RuleSpec] = {}
    refutation_rule: dict[type, RuleSpec] = {}
    lemmas: dict[type, Lemma] = {}
    tags: dict[str, type] = {}
    module_of: dict[str, str] = {}

    def claim(table: dict, key: object, value: object, what: str) -> None:
        if key in table:
            raise RuntimeError(f"{what} {key!r} is registered twice")
        table[key] = value

    for spec in registered:
        claim(rules, spec.id, spec, "rule")
        claim(goal_rule, spec.goal, spec, "goal")
        for t in spec.proofs:
            claim(proof_rule, t, spec, "proof evidence")
        for t in spec.refutations:
            claim(refutation_rule, t, spec, "refutation evidence")
        for lemma in spec.lemmas:
            claim(lemmas, lemma.defines, lemma, "quantity")
        for tag, cls in spec.tags:
            claim(tags, tag, cls, "tag")
        tagged = {cls for _, cls in spec.tags}
        named = {spec.goal, *spec.proofs, *spec.refutations}
        named |= {t for lemma in spec.lemmas for t in (lemma.defines, lemma.evidence)}
        if not named <= tagged:
            raise RuntimeError(f"{spec.id} names untagged types {sorted(c.__name__ for c in named - tagged)}")
        if (spec.refute is None) != (not spec.refutations):
            raise RuntimeError(f"{spec.id}: refute must be given exactly when refutations are")
        if any("point" not in {f.name for f in fields(t)} for t in spec.refutations):
            raise RuntimeError(f"{spec.id}: every refutation type needs a point field, which check.py reads")
        module_of[spec.id] = spec.goal.__module__.rsplit(".", 1)[-1]
    return tuple(MappingProxyType(t) for t in (rules, goal_rule, proof_rule, refutation_rule, lemmas, tags, module_of))


RULES, GOAL_RULE, PROOF_RULE, REFUTATION_RULE, LEMMAS, TAGS, MODULE_OF = _index(_REGISTERED)
"""RULES: rule id -> spec. GOAL_RULE, PROOF_RULE, REFUTATION_RULE: term class -> spec.
LEMMAS: QuantityDef class -> lemma. TAGS: JSON tag -> class for every class a rule
declares (codec.py adds the core term language). MODULE_OF: rule id -> module name, such
as "r4_enclosure"; lola.solvers has a module of the same name."""

# --- Typing aliases for readers. Derived tables above are the source of truth. ---------

Goal = Union[
    r1_linear.LinearFeasible,
    r2_definite.GramPositiveDefinite,
    r3_hypercircle.MinimizerBound,
    r4_enclosure.AllNonpositive,
    r5_moment.MomentBound,
    r6_scenario.BinomialTail,
]
ProofEvidence = Union[
    r1_linear.FeasiblePoints,
    r2_definite.LDLFactor,
    r3_hypercircle.Hypercircle,
    r4_enclosure.Enclosure,
    r5_moment.MomentDual,
    r6_scenario.Arithmetic,
]
RefutationEvidence = Union[
    r1_linear.FarkasRay,
    r2_definite.NegativeDirection,
    r3_hypercircle.HypercircleViolation,
    r4_enclosure.PointWitness,
]
QuantityDef = Union[r3_hypercircle.MinimizerComponent]
"""Quantities a DefinedHyp may name."""
LemmaEvidence = Union[r3_hypercircle.HypercircleFields]
"""What DefinedRange.proof may hold."""

__all__ = [
    "GOAL_RULE",
    "LEMMAS",
    "MODULE_OF",
    "PROOF_RULE",
    "REFUTATION_RULE",
    "RULES",
    "TAGS",
    "Fault",
    "Goal",
    "Invalid",
    "Lemma",
    "LemmaEvidence",
    "ProofEvidence",
    "QuantityDef",
    "RefutationEvidence",
    "RuleSpec",
    "TooWeak",
]
