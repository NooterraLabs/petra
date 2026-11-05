"""Shared types for domains and elaborators. Trusted.

A domain is one module under lola/models that ends with `DOMAIN = DomainSpec(...)`. The
spec names everything the domain owns: its component kinds and their lowerers, its
failure modes and their builders, its claimable quantities, its coverage rules, its
model premises, and its feature and port hooks. lola/models/__init__.py lists the four
specs once and derives every lookup table from them.

An elaborator (a builder) is a pure function from (requirement, typed model, design,
registry) to obligations. Each obligation is a kernel Statement plus the ModelSpec whose
validated_model premise it rests on. Builders never call solvers and never see evidence:
they decide what must be true, not whether it is. When a requirement cannot become a
statement, the builder returns a Gap whose typed needs say what is missing.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from types import ModuleType
from typing import Any, Callable, Mapping, NewType, Union

from ..ir import Component, Design, Input, Param, QoiRef, Rel, Span, Value
from ..kernel import Expr, Goal, QuantityDef, Statement, Sym
from ..premises import Premise
from ..registry import Registry
from ..units import Quantity

# --- Failure modes ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FailureMode:
    """One way a design can fail, named by a dotted id such as "truss.plastic_collapse".
    The domain that declares a mode owns it. models.MODES joins every domain's modes with
    the cross-domain modes below. Waivers name modes by id."""

    id: str


PORT_CONTRACT = FailureMode("port.contract")
"""Built by models.contracts from the ports every domain declares, not by a builder."""

GALVANIC_CORROSION = FailureMode("corrosion.galvanic")
"""Demanded by the cross-domain coverage rule in lola/coverage.py on contact pairs from
any domain. No v0 model builds it."""

CROSS_DOMAIN_MODES: tuple[FailureMode, ...] = (PORT_CONTRACT, GALVANIC_CORROSION)
CROSS_DOMAIN_UNMODELLED: frozenset[FailureMode] = frozenset({GALVANIC_CORROSION})


@dataclass(frozen=True)
class ModelSpec:
    """The validated_model premise for one elaborator function.

    `source_hash` is the sha256 of the elaborator module's source text, computed at import
    by `model_spec`, so editing the physics changes the premise label, the family key, and
    every footprint that relies on it.
    """

    id: str                 # "truss.plastic"
    form: str               # "rigid-perfectly-plastic pin-jointed 2D truss, small displacements"
    validity: str           # "joints are frictionless pins; members prismatic; ..."
    owner: str
    source: str             # standard or textbook the form comes from
    source_hash: str

    def premise(self) -> Premise:
        raise NotImplementedError


def model_spec(module: ModuleType, id: str, form: str, validity: str, owner: str, source: str) -> ModelSpec:
    """Build a ModelSpec whose source_hash covers the module's source text.
    TODO: hashlib.sha256(inspect.getsource(module).encode()).hexdigest()[:16]."""
    raise NotImplementedError


# --- Requirements -------------------------------------------------------------


@dataclass(frozen=True)
class ClaimOrigin:
    claim: str


@dataclass(frozen=True)
class CoverageOrigin:
    """A coverage rule id, or "port.contract" for an obligation built from a connection."""

    rule: str


Origin = Union[ClaimOrigin, CoverageOrigin]


@dataclass(frozen=True)
class Criterion:
    """What must hold for the mode. Claims give rel and bound. Coverage rules give the
    mode's default criterion (for example load factor >= 1, utilisation <= 1)."""

    rel: Rel
    bound: Quantity


@dataclass(frozen=True)
class ProbabilityCriterion:
    threshold: Quantity | None       # None for a FailsAt event
    p: Fraction
    load: str | None
    tests: str | None
    confidence: Fraction | None


@dataclass(frozen=True)
class Requirement:
    """One (subject, mode, criterion) the design must satisfy, from a claim or a coverage
    rule. `qoi` is set for claims so the elaborator can pick the claimed quantity.
    `criterion` is None for a mode with no numeric criterion, such as an unmodelled one."""

    subject: tuple[str, ...]
    mode: FailureMode
    criterion: Union[Criterion, ProbabilityCriterion, None]
    origin: Origin
    under: tuple[str, ...] = ()
    qoi: QoiRef | None = None

    @property
    def id(self) -> str:
        """Stable id: "<subject>/<mode>/<origin>". Used in reports and cert file names."""
        raise NotImplementedError


# --- What an open requirement needs ----------------------------------------------
#
# Every UNKNOWN names its open items, and each item names what it needs as typed data,
# so a gym agent can act on it and a report can print it. An obligation closes when any
# one certificate for its statement checks. A gap closes when every need it lists is met.


@dataclass(frozen=True, slots=True)
class NeedsCertificate:
    """No source offered evidence for this statement. A certificate whose statement hash
    matches closes it. `lola explain` prints the statement."""

    statement_hash: str
    rule: str
    describe: str


@dataclass(frozen=True, slots=True)
class CertificateRejected:
    """Evidence from `source` failed an exact check (kernel Invalid): wrong shape, an
    equality that does not hold, or tampering."""

    statement_hash: str
    rule: str | None
    source: str
    reason: str


@dataclass(frozen=True, slots=True)
class CertificateTooWeak:
    """Evidence from `source` passed every exact check but proved less than the goal
    (kernel TooWeak). A finer partition or a sharper field may close it."""

    statement_hash: str
    rule: str | None
    source: str
    reason: str


@dataclass(frozen=True, slots=True)
class NeedsInputBound:
    """A signed bound on this input is missing, such as the prospective fault current at
    a supply or the design's ambient temperature. Only its owner can supply it. LoLa
    never invents one."""

    target: tuple[str, ...]
    field: str
    unit: str


@dataclass(frozen=True, slots=True)
class NoRuleForQuantity:
    """The subject's domain cannot state this quantity in this form: GE on a temperature,
    stability of an indeterminate truss, a tested failure level above the level tested.
    A different claim or a different design closes it."""

    qoi: str
    reason: str


@dataclass(frozen=True, slots=True)
class NoModel:
    """No v0 elaborator builds `mode`, so no certificate can discharge it. A waiver on
    (mode, subject) can: `waive <mode> on <subject> by "<owner>" reason "<why>"`. So can a
    design change that stops coverage demanding the mode."""

    mode: FailureMode
    subject: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RegistryInconsistent:
    """The deck consistency checker flagged a record this statement uses. A corrected
    record closes it."""

    entry: str
    relation: str
    message: str


Need = Union[
    NeedsCertificate,
    CertificateRejected,
    CertificateTooWeak,
    NeedsInputBound,
    NoRuleForQuantity,
    NoModel,
    RegistryInconsistent,
]
GapNeed = Union[NeedsInputBound, NoRuleForQuantity, NoModel]
"""The needs an elaborator can report. The others come from evidence and the deck."""


# --- Elaboration results --------------------------------------------------------


@dataclass(frozen=True)
class Obligation:
    requirement: Requirement
    statement: Statement
    model: ModelSpec
    describe: str          # one sentence for reports: what the statement means physically


@dataclass(frozen=True)
class Gap:
    """A requirement that could not become a statement. Always UNKNOWN. `needs` is
    non-empty and says what to supply."""

    requirement: Requirement
    needs: tuple[GapNeed, ...]


Elaborated = Union[Obligation, Gap]


# --- Coverage vocabulary ------------------------------------------------------------


class EnergyDomain(Enum):
    MECHANICAL = "mechanical"
    THERMAL = "thermal"
    ELECTRICAL = "electrical"
    CHEMICAL = "chemical"


FeatureKind = NewType("FeatureKind", str)
"""A domain names its own feature kinds ("truss.axial_member"). Only the kinds that
cross-domain rules read are defined here."""

CONTACT_PAIR = FeatureKind("contact_pair")
"""Two materials in contact. Every domain reports its contact pairs so the galvanic rule
in lola/coverage.py sees them all."""


@dataclass(frozen=True)
class Feature:
    """Produced by each domain's `features` hook. Coverage rules match on features only,
    so a rule never reads a typed model."""

    subject: tuple[str, ...]
    kind: FeatureKind
    materials: tuple[str, ...]           # registry material ids
    energy: frozenset[EnergyDomain]
    environment: str | None


@dataclass(frozen=True)
class CoverageRule:
    """`when(feature, registry)` decides whether the rule applies; each demanded mode then
    gets one requirement on the feature's subject with criterion `default(mode, feature)`
    (None for a mode with no numeric criterion)."""

    id: str
    when: Callable[[Feature, Registry], bool]
    demands: tuple[FailureMode, ...]
    default: Callable[[FailureMode, Feature], Union[Criterion, None]]
    note: str


# --- Ports ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PortRef:
    component: str
    element: str
    port: str


@dataclass(frozen=True, slots=True)
class Connection:
    a: PortRef
    b: PortRef
    span: Span


class PortQuantity(Enum):
    CURRENT = "current"
    TEMPERATURE = "temperature"
    VOLTAGE = "voltage"
    FORCE = "force"


BoundBuilder = Callable[["StatementBuilder"], Expr]


@dataclass(frozen=True)
class Side:
    lo: BoundBuilder | None
    hi: BoundBuilder | None
    model: ModelSpec | None      # set when the bound comes from an elaborator, not a rating


@dataclass(frozen=True)
class PortSpec:
    ref: PortRef
    assumes: Mapping[PortQuantity, Side]
    guarantees: Mapping[PortQuantity, Side]


@dataclass(frozen=True)
class Ports:
    """What a component exposes to port contracts: its port specs and the connections it
    declares between ports."""

    specs: tuple[PortSpec, ...]
    connections: tuple[Connection, ...]


NO_PORTS = Ports(specs=(), connections=())


# --- Domains ---------------------------------------------------------------------


class ComponentError(ValueError):
    """Raised by a lowerer for a component or a reference to it that is malformed: an
    unknown node, a wrong unit, a registry id of the wrong kind, an unknown qoi or load
    field. The pipeline collects every problem and reports an input error."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


Lowerer = Callable[[Component, Design, Registry], Any]
"""(component, design, registry) -> the domain's typed model for the component. Validates
the attributes and every load entry, claim, probability claim, tests record and waiver
whose path starts with the component's name. Raises ComponentError."""

Builder = Callable[[Requirement, Any, Design, Registry], tuple[Elaborated, ...]]
"""(requirement, typed model, design, registry) -> obligations and gaps."""


@dataclass(frozen=True)
class DomainSpec:
    """One physics domain. Declared once, at the bottom of its module, as DOMAIN.

    - `kinds`: component kind -> lowerer. The .lola block keyword is the kind.
    - `builders`: failure mode -> builder, for every mode the domain can elaborate.
    - `unmodelled`: modes the domain declares but cannot build. Requiring one yields a Gap
      needing NoModel unless a waiver covers it.
    - `qois`: claimable quantity name -> the mode that bounds it.
    - `probability`: probability method class (ir.RangeMean, ir.FromTests) -> the mode
      that bounds a probability claim on this domain's components.
    - `coverage`: the domain's coverage rules. They demand only the domain's own modes.
    - `models`: mode -> ModelSpec, the validated_model premise of its builder.
    - `features(model, design, registry)` and `ports(model, registry)`: the hooks coverage
      and port contracts read.
    """

    name: str
    kinds: Mapping[str, Lowerer]
    builders: Mapping[FailureMode, Builder]
    unmodelled: frozenset[FailureMode]
    qois: Mapping[str, FailureMode]
    probability: Mapping[type, FailureMode]
    coverage: tuple[CoverageRule, ...]
    models: Mapping[FailureMode, ModelSpec]
    features: Callable[[Any, Design, Registry], tuple[Feature, ...]]
    ports: Callable[[Any, Registry], Ports]

    @property
    def modes(self) -> frozenset[FailureMode]:
        return frozenset(self.builders) | self.unmodelled


# --- Statement builder ----------------------------------------------------------------


class StatementBuilder:
    """Local, single-use builder for one statement.

    The only ways to introduce a hypothesis are the typed methods below, each of which
    needs a source that carries provenance: a registry property, a signed Input, a design
    value, a Param, or a QuantityDef. There is deliberately no method that turns a bare
    number into a RangeHyp, so an elaborator cannot invent an input bound.

    `finish` sorts hyps by symbol and drops hyps the goal does not mention, so the kernel's
    "every hyp is used" rule always holds for builder output.
    """

    def __init__(self, design: Design, registry: Registry) -> None:
        raise NotImplementedError

    def registry(self, entry_id: str, prop: str) -> Expr:
        """A registry property as a kernel Expr.

        A Stated property (a rating, a property-class minimum) becomes one RangeHyp
        labelled "reg:<entry>.<prop>". A Derived property becomes its derivation, with
        each constant it uses as a RangeHyp labelled "reg:const.<name>", so the footprint
        names copper's resistivity rather than a cached resistance number.
        """
        raise NotImplementedError

    def input(self, inp: Input) -> Sym:
        """RangeHyp labelled "in:<design>.<input>"."""
        raise NotImplementedError

    def value(self, v: Value, name: str) -> Sym:
        """Fixed -> RangeHyp labelled "dsg:<design>.<name>" (point range). ParamRef ->
        RangeHyp labelled "par:<design>.<param>". Model inputs are always hyps, never
        inlined constants, so a concrete statement and its family have the same shape."""
        raise NotImplementedError

    def param(self, p: Param) -> Sym:
        raise NotImplementedError

    def defined(self, name: str, definition: QuantityDef) -> Sym:
        raise NotImplementedError

    def finish(self, goal: Goal) -> Statement:
        raise NotImplementedError
