"""Syntax tree -> Design IR. The parse boundary: every check that makes the IR
trustworthy happens here and nowhere downstream.

Checks here (design level; the language knows no domain):
- every component kind is a key of models.KINDS, so a typo is an input error naming the
  registered kinds;
- component, load, tests, param and claim names are unique; "coverage" is reserved as a
  claim name because the report uses it for the requirements no claim made;
- every load entry, tests record and claim path starts with a declared component; every
  `under` and `from` names a declared load or tests block; a ParamRef names a param;
- every quantity parses to an exact Quantity (units.parse_quantity); every bound outside
  a family carries a signature;
- every waiver mode is a key of models.MODES;
- probability-claim method and event agree (RangeMean with Exceeds, FromTests with
  FailsAt).
All problems in one file are collected and raised together as a LoweringError.

Checks in the owning domain's lowerer (models.base.DomainSpec.kinds), raised as
ComponentError and reported the same way: attribute names and shapes, local name
resolution (nodes, elements, ports), registry references of the right kind (LoLa never
substitutes a default part), unit dimensions per slot, load fields and claim qois.
"""
from __future__ import annotations

from ..ir import Design
from ..verdict import COVERAGE_ENTRY
from .syntax import File


class LoweringError(ValueError):
    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


RESERVED_CLAIMS: frozenset[str] = frozenset({COVERAGE_ENTRY})


def lower(file: File, registry: object) -> Design:
    raise NotImplementedError
