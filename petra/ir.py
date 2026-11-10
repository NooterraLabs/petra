"""Design IR: the typed, unit-normalised, name-resolved form of a .petra file.

Produced only by petra.lang.lower (the parse boundary). Units are SI (degC for
temperature), every input bound carries a signature, and every design-level name
resolves. Physics is absent: the IR says what was drawn, not what it means.

Components are generic. A component block is a kind, a name and a list of attribute
lines whose arguments are already typed (quantities, signed bounds, references). The
language knows no component kind. The domain that registers a kind in petra.models parses
the attributes into its own typed model and validates every reference that targets the
component (see models.base.DomainSpec.kinds). Adding a domain never edits this file.

Invariants encoded here:
- An input bound cannot exist without a Signature (owner and source), so the checker
  cannot invent one. A missing bound is a missing field, which elaborators report as
  an UNKNOWN obligation needing that bound.
- A Value is either Fixed or a ParamRef to a declared Param; a design with any ParamRef
  is a family.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from typing import Mapping, Union

from .units import Quantity


@dataclass(frozen=True, slots=True)
class Span:
    path: str
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class Signature:
    owner: str
    source: str


class InputKind(Enum):
    ASSUMED = "assumed"
    MEASURED = "measured"


@dataclass(frozen=True, slots=True)
class Input:
    """A bound signed by its owner. `mean` is optional extra information (R5). `name` is
    the label stem: "<component>.<field>" for a component attribute, "<load>.<target
    path>.<field>" for a load entry."""

    name: str
    range: Quantity
    signature: Signature
    kind: InputKind
    span: Span
    mean: Quantity | None = None


@dataclass(frozen=True, slots=True)
class Param:
    name: str
    range: Quantity
    span: Span


@dataclass(frozen=True, slots=True)
class Fixed:
    quantity: Quantity


@dataclass(frozen=True, slots=True)
class ParamRef:
    name: str


Value = Union[Fixed, ParamRef]

# --- Generic components ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Ref:
    """An identifier or dotted name as written: a local name (A), a word the domain reads
    as a keyword (at, support, count), a registry id (steel.S355), or a port (w1.b)."""

    parts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Text:
    value: str


@dataclass(frozen=True, slots=True)
class Vec:
    """A tuple literal: `(1.5 m, 2 m)`."""

    items: tuple[Quantity, ...]


@dataclass(frozen=True, slots=True)
class Punct:
    """One of ":", "--", "->". Domains use them to read `member m: A -- B` and
    `connect a.out -> b.in`."""

    text: str


@dataclass(frozen=True, slots=True)
class Bound:
    """`given NAME` inside a component block: the bound the card states under that name,
    `in [lo, hi] unit [mean q] signed|measured "owner" source "where"`. The owning domain
    names it and turns it into an Input."""

    range: Quantity
    signature: Signature
    kind: InputKind
    span: Span
    mean: Quantity | None = None


Arg = Union[Fixed, ParamRef, Bound, Ref, Text, Vec, Punct]
"""One typed argument of an attribute line. A bare number with a unit is Fixed; `param
NAME` is a ParamRef."""


@dataclass(frozen=True, slots=True)
class Attr:
    """One line inside a component block: `node A at (0 m, 0 m) support pinned` is
    Attr("node", (Ref(("A",)), Ref(("at",)), Vec(...), Ref(("support",)), Ref(("pinned",))))."""

    key: str
    args: tuple[Arg, ...]
    span: Span


@dataclass(frozen=True, slots=True)
class Component:
    """A component block as written: `truss frame { ... }`. `kind` is a key of
    models.KINDS; lowering rejects any other kind."""

    kind: str
    name: str
    attrs: tuple[Attr, ...]
    span: Span


# --- Loads, claims, evidence, waivers ----------------------------------------


@dataclass(frozen=True, slots=True)
class LoadEntry:
    """One signed load component on one target. Field names are domain vocabulary
    (fx, fy on truss nodes, current on consumers, force on joints and demands), checked
    by the domain that owns the target's component. A family may give a ParamRef instead
    of a signed Input."""

    target: tuple[str, ...]
    field: str
    value: Union[Input, ParamRef]


@dataclass(frozen=True, slots=True)
class LoadCase:
    """Loads that act together. Every entry's Input carries the block's signature."""

    name: str
    entries: tuple[LoadEntry, ...]
    span: Span


class Rel(Enum):
    LE = "<="
    GE = ">="


@dataclass(frozen=True, slots=True)
class QoiRef:
    """`frame.collapse_factor` -> path ("frame",), name "collapse_factor".
    `frame.member(m3).stress` -> path ("frame", "m3"), name "stress"."""

    path: tuple[str, ...]
    name: str


@dataclass(frozen=True, slots=True)
class Claim:
    name: str
    qoi: QoiRef
    rel: Rel
    bound: Quantity
    under: tuple[str, ...]   # load case names; empty means every load case on the subject
    signature: Signature | None
    span: Span
    margin: Quantity | None = None   # a positive point in the bound's dimension; see models.base.Criterion


@dataclass(frozen=True, slots=True)
class RangeMean:
    """R5: distribution-free bound from the load's range and mean."""


@dataclass(frozen=True, slots=True)
class FromTests:
    """R6: scenario bound from a `tests` declaration."""

    tests: str
    confidence: Fraction


ProbMethod = Union[RangeMean, FromTests]


@dataclass(frozen=True, slots=True)
class Exceeds:
    """The event qoi > threshold, under a load known by range and mean."""

    qoi: QoiRef
    threshold: Quantity
    under: str


@dataclass(frozen=True, slots=True)
class FailsAt:
    """The event "subject fails when loaded at level", observed by tests."""

    subject: tuple[str, ...]
    level: Quantity


Event = Union[Exceeds, FailsAt]


@dataclass(frozen=True, slots=True)
class ProbabilityClaim:
    """P(event) <= p. RangeMean pairs with Exceeds, FromTests with FailsAt; lowering
    rejects the other pairings."""

    name: str
    event: Event
    p: Fraction
    method: ProbMethod
    span: Span


@dataclass(frozen=True, slots=True)
class Tests:
    name: str
    subject: tuple[str, ...]
    trials: int
    failures: int
    level: Quantity
    signature: Signature
    span: Span


@dataclass(frozen=True, slots=True)
class Waiver:
    mode: str                 # FailureMode id, checked at lowering against models.MODES
    subject: tuple[str, ...]
    owner: str
    reason: str
    span: Span


@dataclass(frozen=True, slots=True)
class Design:
    name: str
    owner: str
    path: str
    environment: str | None          # registry environment id; None -> no environment class
    ambient: Union[Input, ParamRef, None]
    components: Mapping[str, Component]
    loads: Mapping[str, LoadCase]
    claims: tuple[Claim, ...]
    probability_claims: tuple[ProbabilityClaim, ...]
    tests: Mapping[str, Tests]
    waivers: tuple[Waiver, ...]
    params: Mapping[str, Param]

    @property
    def is_family(self) -> bool:
        return bool(self.params)
