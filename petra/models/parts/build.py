"""Turns the engine's answers into obligations the kernel checks. Trusted.

One builder serves every rule. It reads the rule's row in RULES, the engine's answer for
(rule, subject), and the deck rows the rule's bound names, and states R4 goals only.

    EXACT     PASS: the measure's exact value against the bound, with the bound's row as a
              RangeHyp. FAIL: the same goal refuted, beside a witness lemma that restates
              the witness's geometry from the vertex coordinates it names, as point
              hypotheses labelled dsg:<design>.<part>.v<i>. A crossing is five vertices
              and four signed volumes; a near pair is two features and one squared
              distance.
    DECLARED  the whole check is the statement: hole diameters, positions, thread lengths
              and opening widths as design values, tolerances as RangeHyps.
    GRID      PASS states the Bracket's hi end, FAIL its lo end, each beside the stencil
              and extreme lemmas of sketch_b. A Bracket that straddles the bound states
              nothing; the builder returns a Gap needing UnresolvedGeometry, because
              refuting the hi end would not refute the design.

Squares keep every goal rational: a distance d against a bound c is stated as
d^2 - c^2 with d^2 an exact sum of squares.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ...ir import Design
from ...kernel import Q, Statement
from ...registry import Registry
from ..base import Elaborated, ModelSpec, Requirement, StatementBuilder
from .deck import Deck
from .rules import Evaluator, Rule
from .space import Answer, Crossing, Near


@dataclass(frozen=True, slots=True)
class UnresolvedGeometry:
    """The engine could not decide this rule: a grid Bracket still straddles its bound at
    the solver's finest cell, or two exact bodies touch in a way the contact rule does not
    classify (edge on edge across a face, say). A changed part closes it. Joins GapNeed in
    base.py, and verdict.py's match, when the domain registers."""

    rule: str
    reason: str
    h: Q | None              # the finest cell side tried, mm; None for an exact contact
    cells: int               # unsure cells, 0 for an exact contact
    witness: str             # the worst unsure cell or the two triangles, as text


@dataclass(frozen=True)
class Statements:
    """What one rule states for one subject: the main goal and the lemmas its model's
    validity rows need, in the model's row order."""

    main: Statement
    lemmas: tuple[Statement, ...]


def models() -> Mapping[Evaluator, ModelSpec]:
    """One ModelSpec per evaluator, each hashing the source of every module it trusts:
    EXACT hashes mesh, space and exact; DECLARED hashes lower and build; GRID hashes
    grid, reach and engine (the solver budget included). The GRID model has the
    validity rows parts.stencils and parts.extreme; the EXACT model has parts.witness."""
    raise NotImplementedError


def bound(sb: StatementBuilder, rule: Rule, decks: tuple[Deck, ...], design: Design) -> Any:
    """The rule's bound as a kernel Expr: its row read from each deck (the stricter end
    across decks, by the row's Worse), labelled reg:<preset>.<row> or the override's in:
    label; or a design value for a gap line's stated length; or zero when `rule.bound`
    is None."""
    raise NotImplementedError


def state(rule: Rule, answer: Answer, decks: tuple[Deck, ...], design: Design, registry: Registry) -> Statements | None:
    """The statements for one answer, or None when the answer decides nothing (a Bracket
    straddling the bound, an unclassified contact)."""
    raise NotImplementedError


def crossing_lemma(sb: StatementBuilder, crossing: Crossing, design: Design) -> Statement:
    """The witness lemma for an overlap: the edge's end points lie strictly on opposite
    sides of the face's plane, and the crossing point lies strictly inside the face, as
    four signed volumes over the five vertices."""
    raise NotImplementedError


def near_lemma(sb: StatementBuilder, near: Near, design: Design) -> Statement:
    """The witness lemma for a gap FAIL: the two named features lie at the stated squared
    distance, from their vertex coordinates."""
    raise NotImplementedError


def build(requirement: Requirement, model: Any, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """The builder for every parts mode. Reads the rule from requirement.mode, runs the
    engine through its memo, and returns one Obligation with its validity obligations,
    or one Gap. Coverage demands a costlier rule only where a budget exists
    (domain.py); its Cost reaches the readout from the engine's Run either way."""
    raise NotImplementedError
