"""Decks: the makeable set exported as JSON records. Untrusted.

A deck is what a manufacturer or a shop would publish (the PDK analogue): every property
evaluated to an interval, plus the published table values from the standards (IEC 60228
maximum resistances, ISO 898-1 stress areas, the k = 115 of IEC 60364-5-54) recorded
next to them. Verdicts never read a deck for a derivable property; the consistency
checker reads decks to catch corrupted or wrong records, and a third-party deck's Stated
ratings enter a check only after the checker passes them.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..kernel import Interval
from .model import Registry


@dataclass(frozen=True)
class DeckRecord:
    entry: str
    prop: str
    value: Interval
    unit: str
    provenance: str          # "derived", "stated:<standard>", "published:<standard table>"


@dataclass(frozen=True)
class Deck:
    format: str              # "lola-deck/0"
    records: tuple[DeckRecord, ...]

    def get(self, entry: str, prop: str) -> DeckRecord | None:
        raise NotImplementedError


def build_deck(registry: Registry) -> Deck:
    """Evaluate every property with kernel.enclose and add the published records."""
    raise NotImplementedError


def write_deck(deck: Deck, path: str) -> None:
    raise NotImplementedError


def read_deck(path: str) -> Deck:
    """Strict parse; rationals in kernel canonical form."""
    raise NotImplementedError
