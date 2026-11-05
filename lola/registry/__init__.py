"""The makeable set: materials, parts, processes, environments, computed from physics
plus a short list of constants."""
from __future__ import annotations

from .catalog import build_registry
from .consistency import Finding, check_deck
from .deck import Deck, build_deck, read_deck, write_deck
from .model import (
    Constant,
    Corrosivity,
    Derived,
    Environment,
    Material,
    OutsideMakeableSet,
    Part,
    PartKind,
    Process,
    ProcessKind,
    Property,
    Registry,
    Stated,
)
