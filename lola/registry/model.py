"""Makeable-set types. Trusted: elaborators read properties from these records.

A property is either Derived (a kernel Expr over named constants and definitional
rationals) or Stated (a value that cannot be derived, such as a breaker's rated current
or a property-class minimum, with its full provenance). Nothing in a verdict reads a
cached number for a derivable property: the builder expands the derivation, so the
footprint names the constants.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Union

from ..kernel import Expr, Interval
from ..premises import Tag


@dataclass(frozen=True)
class Constant:
    """One entry of the short constants list. Its premise label is "reg:const.<name>"."""

    name: str
    value: Interval
    unit: str
    tag: Tag
    owner: str
    source: str
    statement: str


@dataclass(frozen=True)
class Derived:
    """expr mentions Sym("const.<name>") for constants and Sym("self.<param>") for the
    parameters of a series entry (a cable series' area). Nothing else. Definitional
    numbers (a designation's nominal diameter) are Const."""

    expr: Expr
    unit: str
    note: str = ""


@dataclass(frozen=True)
class Stated:
    """A rating or a sanctioned minimum. Label "reg:<entry>.<prop>"."""

    value: Interval
    unit: str
    tag: Tag
    owner: str
    standard: str
    conditions: str


Property = Union[Derived, Stated]


class PartKind(Enum):
    SECTION = "section"
    CABLE = "cable"
    BREAKER = "breaker"
    TERMINAL = "terminal"
    BOLT = "bolt"


class ProcessKind(Enum):
    INSTALL = "install"     # cable installation method: sets the external thermal resistance
    COATING = "coating"     # zinc plating, anodising: sets surface galvanic class
    WELD = "weld"           # heat-affected zone strength reduction
    CUT = "cut"


class Corrosivity(Enum):
    """ISO 9223 atmospheric corrosivity categories."""

    C1 = "C1"
    C2 = "C2"
    C3 = "C3"
    C4 = "C4"
    C5 = "C5"
    CX = "CX"


@dataclass(frozen=True)
class Material:
    id: str                       # "steel.S355"
    family: str                   # "steel", "aluminium", "copper", "pvc"
    standard: str                 # "EN 10025-2:2019"
    props: Mapping[str, Property]  # fy, fu, E, nu, G, density, anodic_index, ...


@dataclass(frozen=True)
class Part:
    id: str                       # "bolt.M12_8_8_zn"
    kind: PartKind
    designation: str              # "ISO 4014 M12x1.75 8.8, zinc plated"
    material: str
    props: Mapping[str, Property]
    process: str | None = None    # coating or treatment applied by the maker
    series: str | None = None     # size entries: the series entry they instantiate
    fixes: Mapping[str, Interval] = field(default_factory=dict)  # series param -> value


@dataclass(frozen=True)
class PropertyEffect:
    """How a process changes a material property near where it acts:
    new = factor * old within `zone`. Example: MIG weld on 6061-T6, fy factor 0.5 within
    25 mm of the weld toe."""

    material_family: str
    prop: str
    factor: Property
    zone: str


@dataclass(frozen=True)
class Process:
    id: str
    kind: ProcessKind
    props: Mapping[str, Property]
    effects: tuple[PropertyEffect, ...] = ()
    shape_limits: Mapping[str, Interval] = field(default_factory=dict)


@dataclass(frozen=True)
class Environment:
    id: str
    ambient: Stated               # ambient temperature class, degC
    corrosivity: Corrosivity
    wet: bool


class OutsideMakeableSet(LookupError):
    """A design referenced an id the registry does not hold. Lowering reports it as an
    error; it never becomes a guessed default."""


@dataclass(frozen=True)
class Registry:
    constants: Mapping[str, Constant]
    materials: Mapping[str, Material]
    parts: Mapping[str, Part]
    processes: Mapping[str, Process]
    environments: Mapping[str, Environment]

    def material(self, id: str) -> Material:
        raise NotImplementedError

    def part(self, id: str, kind: PartKind) -> Part:
        raise NotImplementedError

    def process(self, id: str) -> Process:
        raise NotImplementedError

    def environment(self, id: str) -> Environment:
        raise NotImplementedError

    def property(self, entry_id: str, prop: str) -> Property:
        """Look up a property on a material, part or process by entry id."""
        raise NotImplementedError
