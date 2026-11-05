"""Physics-consistency checker for decks. Untrusted: a finding can only add an open item
needing RegistryInconsistent (models.base) for entries a design uses, never remove one,
so a bug here cannot produce a false PASS. `lola registry check` runs it on a deck;
tests/test_registry_consistency.py runs it on the shipped deck and on corrupted copies.

Each Relation is a physical law or a standard's defining formula, written as two kernel
Exprs over the record values of one entry (and the constants). The checker encloses
both sides with kernel.enclose and flags the entry when the enclosures differ by more
than the relation's tolerance. Because the comparison uses rigorous enclosures, a finding
is itself a certified disagreement.

v0 relations (each catches a class of corrupted record):
  bolt.stress_area       As      == (pi/4)((d2 + d3)/2)^2              tol 0.5 %
  bolt.proof_load        Fp      == Sp * As                            tol 0.5 %
  bolt.class_ratio       Rp02/Rm == second digit of class / 10         tol 2 %
  cable.resistance       R20     in [rho20/A, 1.10 * rho20/A]           (IEC 60228 allowance)
  cable.k_factor         k       == sqrt(qc (beta+20)/rho20 ln((beta+tf)/(beta+ti)))  tol 1 %
  material.shear_modulus G       == E / (2 (1 + nu))                   tol 2 %
  material.yield_order   fy      <= fu
  section.area           A       == (pi/4)(D^2 - (D - 2t)^2)           tol 0.5 %
  breaker.conventional   I_t     == 1.45 In, I_nt == 1.13 In           exact
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Callable

from ..kernel import Expr, Interval
from .deck import Deck, DeckRecord


@dataclass(frozen=True)
class Relation:
    id: str
    applies_to: str                         # entry kind prefix: "bolt.", "cable.", ...
    lhs: Callable[[Deck, str], Expr]        # build the Expr for one entry id
    rhs: Callable[[Deck, str], Expr]
    rel_tol: Fraction
    kind: str = "eq"                        # "eq", "le", or "within"


@dataclass(frozen=True)
class Finding:
    entry: str
    relation: str
    lhs: Interval
    rhs: Interval
    message: str


RELATIONS: tuple[Relation, ...] = ()
"""TODO: the v0 relations listed in the module docstring."""


def check_deck(deck: Deck, relations: tuple[Relation, ...] = RELATIONS) -> tuple[Finding, ...]:
    """Every finding, sorted by entry. Deterministic."""
    raise NotImplementedError


def corrupt(deck: Deck, entry: str, prop: str, factor: Fraction) -> Deck:
    """Test helper: scale one record. tests/test_registry_consistency.py corrupts one record per
    relation and asserts check_deck reports exactly that entry and relation."""
    raise NotImplementedError


def flagged_entries(findings: tuple[Finding, ...]) -> frozenset[str]:
    raise NotImplementedError


def _record(deck: Deck, entry: str, prop: str) -> DeckRecord:
    raise NotImplementedError
