"""Makeable-set types. Trusted: elaborators read properties from these records.

A property is either Derived (a kernel Expr over named constants and other properties of
the same entry) or Stated (a value that cannot be derived, such as a breaker's rated
current or a property-class minimum, with its full provenance). Nothing in a verdict reads
a cached number for a derivable property: `Registry.expand` turns a property into an Expr
whose every symbol is a premise key, so the footprint names the constants.

Premise keys. `Registry.fact(key)` resolves each one, and its premise label is "reg:<key>":
    "const.<name>"         a Constant
    "<entry>.<prop>"       a Stated property, on the entry that defines it
    "<environment>.ambient"
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Mapping, Union

from ..kernel import Abs, Add, Const, Div, Exp, Expr, Interval, Ln, Max, Min, Mul, Neg, Pi, PowInt, Sqrt, Sym
from ..premises import ALLOWED_TAGS, LabelKind, Tag


def _require_provenance(what: str, tag: Tag, owner: str, source: str) -> None:
    if tag not in ALLOWED_TAGS[LabelKind.REGISTRY]:
        raise ValueError(f"{what}: a registry value is sanctioned, measured or judged, not {tag.value}")
    if not owner.strip() or not source.strip():
        raise ValueError(f"{what}: a registry value needs an owner and a source")


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

    def __post_init__(self) -> None:
        _require_provenance(f"constant {self.name}", self.tag, self.owner, self.source)


@dataclass(frozen=True)
class Derived:
    """expr mentions Sym("const.<name>") for a constant and Sym("self.<prop>") for another
    property of the entry being expanded: on a series entry, a parameter its sizes fix or
    a family sets (a cable's area); on any entry, a property it defines (a bolt's Sp).
    Nothing else. Definitional numbers (the 20 degC of rho20) are Const. `note` names the
    formula's source."""

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

    def __post_init__(self) -> None:
        _require_provenance(f"stated value ({self.conditions})", self.tag, self.owner, self.standard)


Property = Union[Derived, Stated]


class PartKind(Enum):
    SECTION = "section"
    CABLE = "cable"
    BREAKER = "breaker"
    TERMINAL = "terminal"
    BOLT = "bolt"


class ProcessKind(Enum):
    INSTALL = "install"     # cable installation method: sets the external thermal resistance
    COATING = "coating"     # zinc plating, anodising: replaces the surface material
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
    designation: str              # "M12x1.75 property class 8.8, zinc plated"
    material: str
    props: Mapping[str, Property]
    process: str | None = None    # coating or treatment applied by the maker
    series: str | None = None     # size entries: the series entry they instantiate
    fixes: Mapping[str, Interval] = field(default_factory=dict)  # series param -> value


@dataclass(frozen=True)
class PropertyEffect:
    """How a process changes a material property near where it acts:
    new = factor * old within `zone`. Example: MIG weld on 6061-T6, fy factor 0.48 within
    30 mm of the weld."""

    material_family: str
    prop: str
    factor: Property
    zone: str


@dataclass(frozen=True)
class Process:
    """A COATING names `surface`, the registry material it leaves exposed, so whatever
    touches a coated part touches that material. No other kind names one."""

    id: str
    kind: ProcessKind
    props: Mapping[str, Property]
    effects: tuple[PropertyEffect, ...] = ()
    shape_limits: Mapping[str, Interval] = field(default_factory=dict)
    surface: str | None = None

    def __post_init__(self) -> None:
        if (self.kind is ProcessKind.COATING) != (self.surface is not None):
            raise ValueError(f"process {self.id}: a coating names its surface material and no other process does")


@dataclass(frozen=True)
class Environment:
    id: str
    ambient: Stated               # ambient temperature class, degC
    corrosivity: Corrosivity
    wet: bool


class OutsideMakeableSet(LookupError):
    """A design referenced an id the registry does not hold. Lowering reports it as an
    error; it never becomes a guessed default."""


Entry = Union[Material, Part, Process]


@dataclass(frozen=True)
class Registry:
    constants: Mapping[str, Constant]
    materials: Mapping[str, Material]
    parts: Mapping[str, Part]
    processes: Mapping[str, Process]
    environments: Mapping[str, Environment]

    def material(self, id: str) -> Material:
        if id not in self.materials:
            raise OutsideMakeableSet(f"{id} is not a registry material")
        return self.materials[id]

    def part(self, id: str, kind: PartKind) -> Part:
        if id not in self.parts:
            raise OutsideMakeableSet(f"{id} is not a registry part")
        part = self.parts[id]
        if part.kind is not kind:
            raise OutsideMakeableSet(f"{id} is a {part.kind.value}, not a {kind.value}")
        return part

    def process(self, id: str) -> Process:
        if id not in self.processes:
            raise OutsideMakeableSet(f"{id} is not a registry process")
        return self.processes[id]

    def surface(self, material: str, process: str | None) -> str:
        """The registry material a part or plate of `material` shows to what touches it:
        the coating's surface material under a COATING process, otherwise `material`."""
        found = self.process(process) if process is not None else None
        if found is None or found.kind is not ProcessKind.COATING:
            return self.material(material).id
        return self.material(found.surface).id

    def environment(self, id: str) -> Environment:
        if id not in self.environments:
            raise OutsideMakeableSet(f"{id} is not a registry environment")
        return self.environments[id]

    def property(self, entry_id: str, prop: str) -> Property:
        """Look up a property on a material, part or process by entry id. A size entry
        inherits every property of its series that it does not define itself. An
        environment's one property is its ambient class, "<environment>.ambient"."""
        if entry_id in self.environments and prop == "ambient":
            return self.environments[entry_id].ambient
        return self._find(entry_id, prop)[1]

    def expand(self, entry_id: str, prop: str, params: Mapping[str, Expr] | None = None) -> Expr:
        """The property as an Expr whose every symbol is a premise key (see `fact`), apart
        from symbols the caller passes in `params`.

        A Stated property becomes Sym("<entry>.<prop>"). In a Derived property,
        Sym("const.<name>") stays, and Sym("self.<p>") becomes params[p] when given,
        otherwise the expansion of property p of the same entry. A family passes the
        parameters its series leaves open: expand("cable.cu_pvc", "R20", {"area": a}).
        """
        return self._expand(entry_id, prop, params or {}, ())

    def fact(self, key: str) -> Constant | Stated:
        """The constant or stated value behind the premise label "reg:<key>"."""
        if key.startswith("const.") and key[len("const."):] in self.constants:
            return self.constants[key[len("const."):]]
        entry_id, _, prop = key.rpartition(".")
        if entry_id in self.environments and prop == "ambient":
            return self.environments[entry_id].ambient
        found = self._entry(entry_id).props.get(prop) if self._has_entry(entry_id) else None
        if not isinstance(found, Stated):
            raise OutsideMakeableSet(f"{key} names no registry constant or stated value")
        return found

    def _has_entry(self, entry_id: str) -> bool:
        return entry_id in self.materials or entry_id in self.parts or entry_id in self.processes

    def _entry(self, entry_id: str) -> Entry:
        for table in (self.materials, self.parts, self.processes):
            if entry_id in table:
                return table[entry_id]
        raise OutsideMakeableSet(f"{entry_id} is not a registry material, part or process")

    def _find(self, entry_id: str, prop: str) -> tuple[str, Property]:
        """(id of the entry that defines prop, the property)."""
        entry = self._entry(entry_id)
        if prop in entry.props:
            return entry_id, entry.props[prop]
        series = getattr(entry, "series", None)
        if series is not None and prop in self.parts[series].props:
            return series, self.parts[series].props[prop]
        raise OutsideMakeableSet(f"{entry_id} has no property {prop}")

    def _expand(self, entry_id: str, prop: str, params: Mapping[str, Expr], stack: tuple[str, ...]) -> Expr:
        if prop in stack:
            raise ValueError(f"{entry_id}: derivation cycle {' -> '.join(stack + (prop,))}")
        owner, found = self._find(entry_id, prop)
        if isinstance(found, Stated):
            return Sym(f"{owner}.{prop}")

        def resolve(name: str) -> Expr:
            if name.startswith("const."):
                if name[len("const."):] not in self.constants:
                    raise OutsideMakeableSet(f"{owner}.{prop} names unknown constant {name}")
                return Sym(name)
            if name.startswith("self."):
                param = name[len("self."):]
                if param in params:
                    return params[param]
                return self._expand(entry_id, param, params, stack + (prop,))
            raise ValueError(f"{owner}.{prop}: derivation names {name}, which is neither const.* nor self.*")

        return map_syms(found.expr, resolve)


def map_syms(expr: Expr, fn: Callable[[str], Expr]) -> Expr:
    """Replace every Sym in expr by fn(name). Walks dataclass fields, so it covers every
    Expr variant without naming one."""
    if isinstance(expr, Sym):
        return fn(expr.name)
    changes = {}
    for f in dataclasses.fields(expr):
        value = getattr(expr, f.name)
        if isinstance(value, tuple):
            changes[f.name] = tuple(map_syms(v, fn) for v in value)
        elif dataclasses.is_dataclass(value):
            changes[f.name] = map_syms(value, fn)
    return dataclasses.replace(expr, **changes) if changes else expr


def render(expr: Expr) -> str:
    """Infix text with every compound operand in parentheses. Deck provenance strings
    ("derived:<formula>") and `petra explain` print expressions with it."""
    match expr:
        case Const(value=v):
            return str(v)
        case Sym(name=name):
            return name
        case Pi():
            return "pi"
        case Add(args=args):
            text = _operand(args[0]) if args else "0"
            for a in args[1:]:
                text += f" - {_operand(a.arg)}" if isinstance(a, Neg) else f" + {_operand(a)}"
            return text
        case Mul(args=args):
            return " * ".join(_operand(a) for a in args) if args else "1"
        case Neg(arg=a):
            return f"-{_operand(a)}"
        case Div(num=n, den=d):
            return f"{_operand(n)} / {_operand(d)}"
        case PowInt(base=b, exponent=k):
            return f"{_operand(b)}^{k}"
        case Sqrt(arg=a) | Ln(arg=a) | Exp(arg=a) | Abs(arg=a):
            return f"{type(expr).__name__.lower()}({render(a)})"
        case Min(args=args) | Max(args=args):
            return f"{type(expr).__name__.lower()}({', '.join(render(a) for a in args)})"
    raise TypeError(f"{type(expr).__name__} is not an expression")


def _operand(expr: Expr) -> str:
    text = render(expr)
    return f"({text})" if isinstance(expr, (Add, Mul, Div, Neg)) else text
