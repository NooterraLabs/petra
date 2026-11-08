"""The typed view of one process preset with a design's overrides in place. Trusted.

The registry owns every preset row; lowering owns the overrides; `deck` is the one place
they merge, and nothing else builds a Deck. Each row keeps the label of the premise it
came from, "reg:<preset>.<row>" or the override's "in:<design>.<part>.override.<row>", so
the footprint names exactly the rows a verdict rests on.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal, Mapping

from ...ir import Input
from ...kernel import Interval
from ...registry import ProcessKind, Registry
from .space import Cut, Profile


class Worse(Enum):
    """Which end of a row's interval is the pessimistic one for the rule that reads it."""

    HIGH = "high"            # a larger radius, holder, tolerance or minimum is harder to meet
    LOW = "low"              # a shorter reach or a smaller build volume is harder to meet


@dataclass(frozen=True)
class Row:
    value: Interval
    unit: str
    label: str
    worse: Worse


@dataclass(frozen=True)
class Tool:
    """One cutter of a mill or router deck, or a laser's beam (radius half the kerf)."""

    id: str
    radius: Row
    corner: Row              # 0 flat, == radius ball
    reach: Row               # length below the holder
    holder_radius: Row
    standard: bool           # tool.<id> rows are standard, special.<id> rows are not

    def body(self, end: Literal["pess", "opt"]) -> Profile:
        """The tool as a profile: its radius down to its reach, its holder beyond, at the
        pessimistic or optimistic end of every row."""
        raise NotImplementedError

    def cut(self, end: Literal["pess", "opt"]) -> Cut:
        raise NotImplementedError


@dataclass(frozen=True)
class Override:
    """One preset row the design replaces: `override <row> in [lo, hi] signed "<owner>"
    source "<why>"`. Only lower.py builds one, after checking the preset holds the row and
    the bound has the row's unit."""

    row: str                 # "tool.t2.reach"
    bound: Input             # signed or measured; its label is "in:<design>.<part>.override.<row>"


@dataclass(frozen=True)
class Deck:
    preset: str
    kind: ProcessKind
    rows: Mapping[str, Row]  # every row of the preset, overridden where the design says
    tools: tuple[Tool, ...]


def deck(registry: Registry, preset: str, overrides: tuple[Override, ...]) -> Deck:
    """The preset's rows with the overrides in place. Memoised on (preset, overrides)."""
    raise NotImplementedError
