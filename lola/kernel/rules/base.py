"""What a certificate rule declares, and how a rule says no.

Each rule module ends with one `RULE = RuleSpec(...)`. The spec is the only place the
rule's types, JSON tags, lemmas and check functions are named. `rules/__init__.py` lists
the specs in `_REGISTERED` and derives every other table from them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Union

from ..evaluate import Box


@dataclass(frozen=True, slots=True)
class Invalid:
    """The evidence fails an exact check: wrong shape, an equality that does not hold, a
    split point outside its cell, a point outside the box. Tampered evidence lands here."""

    reason: str


@dataclass(frozen=True, slots=True)
class TooWeak:
    """The evidence passes every exact check, but the bound it yields misses the goal: a
    leaf whose enclosure crosses 0, a hypercircle sphere wider than the claimed range. A
    finer partition or a sharper field may succeed, so a solver or an agent can act on it."""

    reason: str


Fault = Union[Invalid, TooWeak]
"""What a rule function returns instead of None when the evidence does not check."""

Check = Callable[[Any, Any, Box], Union[Fault, None]]
"""(goal, evidence body, box) -> None when the evidence proves or refutes the goal.

check.py builds the box. For `prove` it holds every RangeHyp over its range and every
DefinedHyp over the range its lemma proved there, and the rule must show the goal holds
at every point of it. For `refute` it holds every RangeHyp fixed at the evidence point
and every DefinedHyp over the range its lemma proved at that point, and the rule must
show the goal fails at every point of it. Either way each symbol ranges over its whole
interval, independently of the others, so a rule never rests on one representative
value of an interval it is given."""


def _binds_nothing(goal: Any) -> frozenset[str]:
    return frozenset()


@dataclass(frozen=True, slots=True)
class Lemma:
    """A quantity a DefinedHyp may name, and the rule's proof of a range for it.

    `defines` is a QuantityDef variant. `evidence` is the type `DefinedRange.proof` must
    have for it. `prove(definition, defined_range, box)` returns None when the range holds
    at every point of `box`, which check.py builds from the RangeHyps alone: their ranges
    for a proof, the evidence point for a refutation."""

    defines: type
    evidence: type
    prove: Callable[[Any, Any, Box], Union[Fault, None]]


@dataclass(frozen=True, slots=True)
class RuleSpec:
    """One certificate rule.

    - `id` is the JSON spelling ("R1") and the rule id every footprint report prints.
    - `goal` is the rule's Goal variant. `proofs` and `refutations` are its evidence body
      types. `check` attempts `prove` for a proof body and `refute` for a refutation body.
    - `tags` gives the JSON tag of every term class the rule module defines. Every type
      named in this spec must appear in it.
    - `lemmas` lists the QuantityDef variants this rule can prove ranges for.
    - `binds(goal)` returns the symbols the goal binds itself, such as R5's random
      variables, which are not hypotheses of the statement.

    `refute` is None exactly when `refutations` is empty.
    """

    id: str
    goal: type
    proofs: tuple[type, ...]
    refutations: tuple[type, ...]
    tags: tuple[tuple[str, type], ...]
    lemmas: tuple[Lemma, ...]
    prove: Check
    refute: Check | None
    binds: Callable[[Any], frozenset[str]] = _binds_nothing
