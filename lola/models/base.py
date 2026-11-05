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

import dataclasses
import hashlib
import inspect
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from types import ModuleType
from typing import Any, Callable, Mapping, NewType, Union

from ..ir import Component, Design, Fixed, Input, Param, ParamRef, QoiRef, Rel, Span, Tests, Value
from ..kernel import GOAL_RULE, LEMMAS, DefinedHyp, Expr, Goal, Hyp, Interval, QuantityDef, RangeHyp, Statement, Sym
from ..premises import Label, Premise, Tag, constant_label, design_label, input_label, param_label, registry_label
from ..registry import Derived, Registry, Stated
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
        return Premise(
            Label(f"model:{self.id}@{self.source_hash}"),
            Tag.VALIDATED_MODEL,
            self.owner,
            self.source,
            f"{self.form}; valid when {self.validity}",
        )


def model_spec(module: ModuleType, id: str, form: str, validity: str, owner: str, source: str) -> ModelSpec:
    """Build a ModelSpec whose source_hash covers the module's source text."""
    source_hash = hashlib.sha256(inspect.getsource(module).encode("utf-8")).hexdigest()[:16]
    return ModelSpec(id, form, validity, owner, source, source_hash)


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
        """Stable id: "<subject>/<mode>/<origin>", such as
        "frame.diag_ad/truss.member_buckling/coverage.truss.axial_member". Used in reports."""
        if isinstance(self.origin, ClaimOrigin):
            origin = f"claim.{self.origin.claim}"
        else:
            origin = f"coverage.{self.origin.rule}"
        return f"{'.'.join(self.subject)}/{self.mode.id}/{origin}"


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
whose path starts with the component's name. Raises ComponentError.

The model keeps every signed bound it names from an attribute as an ir.Input, anywhere in
its dataclasses, tuples or mappings. The pipeline's premise book finds each one there, so
"in:<design>.<component>.<field>" resolves to its owner and source with no other
declaration."""

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
    needs a source that carries provenance: a registry property or constant, a signed
    Input (its range, its mean), a tests record, a design value, a Param, or a QuantityDef. There is
    deliberately no method that turns a bare number into a RangeHyp, so an elaborator
    cannot invent an input bound. Each method refuses an argument of any other type.

    One label always means one symbol. Asking twice for the same source returns the same
    symbol; giving one symbol two meanings raises ValueError.

    `finish` sorts hyps by symbol and drops hyps the goal does not mention, so the kernel's
    "every hyp is used" rule always holds for builder output.
    """

    def __init__(self, design: Design, registry: Registry) -> None:
        self._design = design
        self._registry = registry
        self._hyps: dict[str, Hyp] = {}
        self._finished = False

    def registry(self, entry_id: str, prop: str, series: Mapping[str, Sym] | None = None) -> Expr:
        """A registry property as a kernel Expr.

        A Stated property (a rating, a property-class minimum) becomes one RangeHyp
        labelled "reg:<entry>.<prop>". A Derived property becomes its derivation, with
        each constant it uses as a RangeHyp labelled "reg:const.<name>", so the footprint
        names copper's resistivity rather than a cached resistance number.

        A size entry ("cable.cu_pvc_2_5") that does not hold `prop` itself reads it from
        its series ("cable.cu_pvc"), and the label names the entry that holds it. Each
        series parameter Sym("self.<p>") in a derivation becomes the entry's fixed value
        as a point hyp labelled "dsg:<design>.<entry>.<p>" (a chosen size is the design),
        or else the hypothesis the caller binds in `series`, which a family uses to give
        a ParamRef. A parameter that is neither fixed nor bound, or both, raises ValueError.

        Any other Sym("self.<p>") names another property of the same entry and expands the
        same way, recursively: a cable's T1 names its outer diameter, which names its
        conductor diameter, which names the area. A derivation that reaches its own
        property again raises ValueError naming the cycle.
        """
        self._open()
        if not isinstance(entry_id, str) or not isinstance(prop, str):
            raise TypeError("a registry property is named by an entry id and a property name")
        bound = dict(series or {})
        for name, sym in bound.items():
            if not (isinstance(sym, Sym) and sym.name in self._hyps):
                raise TypeError(f"series parameter {name} must be bound to a hypothesis of this builder")
        return self._property(entry_id, prop, bound, ())

    def constant(self, name: str) -> Sym:
        """RangeHyp labelled "reg:const.<name>": a number a standard fixes that is no
        entry's property, such as the 1.45 of IEC 60364-4-43's I2 <= 1.45 Iz. The
        registry's Constant carries its tag, owner and source."""
        self._open()
        if not isinstance(name, str):
            raise TypeError("a registry constant is named by its name")
        return self._constant(name, "the elaborator")

    def input(self, inp: Input) -> Sym:
        """RangeHyp labelled "in:<design>.<input>"."""
        if not isinstance(inp, Input):
            raise TypeError("an input hypothesis needs a signed Input")
        return self._range(inp.name, inp.range.value, input_label(self._design.name, inp.name))

    def mean(self, inp: Input) -> Sym:
        """RangeHyp labelled "in:<design>.<input>.mean", the signed mean of a load (R5).
        Raises ValueError when the input has none; the builder reports NeedsInputBound."""
        if not isinstance(inp, Input):
            raise TypeError("a mean hypothesis needs a signed Input")
        if inp.mean is None:
            raise ValueError(f"{inp.name} has no signed mean")
        name = f"{inp.name}.mean"
        return self._range(name, inp.mean.value, input_label(self._design.name, name))

    def tests(self, record: Tests) -> tuple[Sym, Sym]:
        """(trials, failures) of a signed tests record (R6), as point RangeHyps labelled
        "in:<design>.tests.<name>.trials" and "in:<design>.tests.<name>.failures"."""
        if not isinstance(record, Tests):
            raise TypeError("test counts need a signed Tests record")

        def count(field: str, n: int) -> Sym:
            name = f"tests.{record.name}.{field}"
            return self._range(name, Interval(Fraction(n), Fraction(n)), input_label(self._design.name, name))

        return count("trials", record.trials), count("failures", record.failures)

    def value(self, v: Value, name: str) -> Sym:
        """Fixed -> RangeHyp labelled "dsg:<design>.<name>" (point range). ParamRef ->
        the param's hypothesis (see `param`), shared by every value that names it. Model
        inputs are always hyps, never inlined constants, so a concrete statement and its
        family have the same shape."""
        if isinstance(v, ParamRef):
            return self.param(self._design.params[v.name])
        if not isinstance(v, Fixed):
            raise TypeError("a design value is a Fixed quantity or a ParamRef")
        return self._range(name, v.quantity.value, design_label(self._design.name, name))

    def param(self, p: Param) -> Sym:
        """RangeHyp labelled "par:<design>.<param>" over the param's declared range."""
        if not isinstance(p, Param):
            raise TypeError("a scope parameter hypothesis needs a declared Param")
        return self._range(p.name, p.range.value, param_label(self._design.name, p.name))

    def defined(self, name: str, definition: QuantityDef) -> Sym:
        """DefinedHyp: `name` equals the quantity `definition` names. Its range comes from
        a lemma in the evidence, never from the statement."""
        if type(definition) not in LEMMAS:
            raise TypeError(f"{type(definition).__name__} is not a quantity a lemma can prove")
        return self._add(DefinedHyp(name, definition))

    def finish(self, goal: Goal) -> Statement:
        self._open()
        spec = GOAL_RULE.get(type(goal))
        if spec is None:
            raise TypeError(f"{type(goal).__name__} is not a registered goal")
        used = _syms(goal) - spec.binds(goal)
        for name in tuple(used):
            hyp = self._hyps.get(name)
            if isinstance(hyp, DefinedHyp):
                used |= _syms(hyp.definition)
        unbound = used - set(self._hyps)
        if unbound:
            raise ValueError(f"the goal mentions symbols no hypothesis introduces: {sorted(unbound)}")
        self._finished = True
        return Statement(tuple(self._hyps[name] for name in sorted(used)), goal)

    def _property(self, entry_id: str, prop: str, bound: Mapping[str, Sym], expanding: tuple[str, ...]) -> Expr:
        if prop in expanding:
            raise ValueError(f"{entry_id}: derivation cycle {' -> '.join((*expanding, prop))}")
        holder = self._holder(entry_id, prop)
        fixes = self._registry.parts[entry_id].fixes if entry_id in self._registry.parts else {}
        found = self._registry.property(holder, prop)
        if isinstance(found, Stated):
            return self._range(f"{holder}.{prop}", found.value, registry_label(holder, prop))
        if not isinstance(found, Derived):
            raise TypeError(f"{holder}.{prop} is neither Stated nor Derived")
        replace: dict[str, Expr] = {}
        for name in sorted(_syms(found.expr)):
            namespace, _, rest = name.partition(".")
            if namespace == "const":
                replace[name] = self._constant(rest, f"{holder}.{prop}")
            elif namespace != "self":
                raise ValueError(f"the derivation of {holder}.{prop} names {name}, which is neither const.* nor self.*")
            elif rest in bound and rest in fixes:
                raise ValueError(f"{entry_id} fixes {rest}, so it cannot also be bound")
            elif rest in bound:
                replace[name] = bound[rest]
            elif rest in fixes:
                replace[name] = self._range(f"{entry_id}.{rest}", fixes[rest], design_label(self._design.name, f"{entry_id}.{rest}"))
            elif self._holds(entry_id, rest):
                replace[name] = self._property(entry_id, rest, bound, (*expanding, prop))
            else:
                raise ValueError(f"{entry_id}.{prop} needs series parameter {rest}, which is neither fixed nor bound")
        return _substitute(found.expr, replace)

    def _holder(self, entry_id: str, prop: str) -> str:
        part = self._registry.parts.get(entry_id)
        return part.series if part is not None and part.series is not None and prop not in part.props else entry_id

    def _holds(self, entry_id: str, prop: str) -> bool:
        try:
            self._registry.property(self._holder(entry_id, prop), prop)
        except LookupError:
            return False
        return True

    def _constant(self, name: str, needed_by: str) -> Sym:
        constant = self._registry.constants.get(name)
        if constant is None:
            raise ValueError(f"{needed_by} names constant {name}, which the registry does not hold")
        return self._range(f"const.{name}", constant.value, constant_label(name))

    def _range(self, sym: str, value: Interval, label: str) -> Sym:
        return self._add(RangeHyp(sym, value.lo, value.hi, label))

    def _add(self, hyp: Hyp) -> Sym:
        self._open()
        held = self._hyps.setdefault(hyp.sym, hyp)
        if held != hyp:
            raise ValueError(f"symbol {hyp.sym} already means {held}, so it cannot also mean {hyp}")
        return Sym(hyp.sym)

    def _open(self) -> None:
        if self._finished:
            raise RuntimeError("a StatementBuilder builds exactly one statement")


def _syms(term: object) -> frozenset[str]:
    if isinstance(term, Sym):
        return frozenset((term.name,))
    if isinstance(term, tuple):
        return frozenset().union(*map(_syms, term))
    if dataclasses.is_dataclass(term) and not isinstance(term, type):
        return frozenset().union(*(_syms(getattr(term, f.name)) for f in dataclasses.fields(term)))
    return frozenset()


def _substitute(term: Any, replace: Mapping[str, Expr]) -> Any:
    if isinstance(term, Sym):
        return replace.get(term.name, term)
    if isinstance(term, tuple):
        return tuple(_substitute(t, replace) for t in term)
    if dataclasses.is_dataclass(term) and not isinstance(term, type):
        return dataclasses.replace(term, **{f.name: _substitute(getattr(term, f.name), replace) for f in dataclasses.fields(term)})
    return term
