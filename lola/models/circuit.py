"""Domain: wire circuits. Trusted physics; footprint premises "model:wire.*@<hash>".

Component kind `circuit`. Attribute lines, one per line inside the block:

    supply <name> voltage <V> [fault_current <signed bound>]
    breaker <name> part <registry breaker id>
    wire <name> cable <registry cable id> [area <value> insulation <value>]
         length <value> install <registry install process id>
    terminal <name> part <registry terminal id>
    consumer <name>
    connect <element>.<port> -> <element>.<port>

A <value> is a quantity or `param <name>`. A cable id names a size ("cable.cu_pvc_2_5")
or a series ("cable.cu_pvc"); a series needs `area` and `insulation`. Load field:
current on `<circuit>.<consumer>`. Claim path: `<circuit>.<wire>.<qoi>`.

Ports, as (upstream, downstream): supply (-, out), breaker (in, out), wire (a, b),
terminal (wire, out), consumer (in, -). A connection runs from a downstream port to an
upstream port, every element sits on one radial path from a supply to a consumer, and a
path has at most one breaker, upstream of its wires.

Steady temperature (IEC 60287-style heat balance, single conductor, steady state):
    theta - Ta = I^2 R20 (1 + alpha (theta - 20)) T,        T = T1 + T4  [K m / W]
    T1 = rho_T / (2 pi) ln(D / d)                            insulation (registry)
    T4 = 1 / (pi D h)                                        surface to air, clipped direct
Linear in theta, so with a = I^2 R20 T:
    theta = (Ta + a (1 - 20 alpha)) / (1 - a alpha)          valid while a alpha < 1
R4 goal: AllNonpositive([theta - theta_max, a*alpha - 1]). The second expression is the
thermal-runaway side condition, so a runaway design fails with a witness. The divisor is
written (sqrt(1 - a alpha))^2, whose enclosure is undefined unless 1 - a alpha >= 0, so
theta alone (a port guarantee) can never pass where the plain quotient turns negative.

Short circuit (IEC 60949 adiabatic):  I2t_let_through - u k^2 S^2 <= 0, with k derived from
copper constants (registry), and I_fault - u I_cn <= 0 (breaker breaking capacity).

Voltage drop at a wire's far end, summed over every wire from the supply to it:
    sum 2 L I R20 (1 + alpha (theta_max - 20)) - u V <= 0
(conservative: every conductor at its maximum temperature; u the claimed or default
fraction of V). Summing makes the last wire's check the drop at the consumer.

Overload protection (IEC 60364-4-43 433.1): I_B <= u I_n, theta(I_n / u) <= theta_max
(I_n <= I_z) and theta(I_2 / (1.45 u)) <= theta_max (I_2 <= 1.45 I_z), with I_2 the
breaker's conventional tripping current, all without computing I_z. The 1.45 is the
sanctioned registry constant OVERLOAD_FACTOR, so it is a hypothesis of the statement.

fault_withstand and overload_protection are utilisations: a claim bounds them by u, and
coverage by 1. Every wire criterion is an upper bound; a GE claim is a gap.

Current through a wire comes from the consumer's signed load case on the same series
path, never from a default: a load case that acts on the circuit but not on that
consumer leaves the wire's current unsigned, so the obligation is a gap. Ambient comes
from the design's signed ambient, or else the environment class's ambient range; with
neither, the obligation is a gap needing NeedsInputBound.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType
from typing import Callable, Mapping, Union

from ..ir import Arg, Bound, Component, Design, Exceeds, Fixed, Input, ParamRef, Punct, Ref, Rel, Span, Value
from ..kernel import Add, Const, Div, Expr, Interval, Max, Min, Mul, Neg, Pi, PowInt, Sqrt, Sym
from ..kernel.rules.r4_enclosure import AllNonpositive
from ..registry import OutsideMakeableSet, PartKind, ProcessKind, Registry
from ..units import AREA, CURRENT, DIMENSIONLESS, LENGTH, TEMPERATURE, VOLTAGE, Dim, Quantity
from .base import (
    CONTACT_PAIR,
    ComponentError,
    Connection,
    CoverageRule,
    Criterion,
    DomainSpec,
    Elaborated,
    EnergyDomain,
    FailureMode,
    Feature,
    FeatureKind,
    Gap,
    GapNeed,
    ModelSpec,
    NeedsInputBound,
    NoRuleForQuantity,
    Obligation,
    PortQuantity,
    PortRef,
    PortSpec,
    Ports,
    Requirement,
    Side,
    StatementBuilder,
    model_spec,
)

# --- Typed model, produced by lower_circuit -------------------------------------------


@dataclass(frozen=True, slots=True)
class Supply:
    name: str
    voltage: Quantity
    fault_current: Input | None   # prospective fault current, signed; None -> NeedsInputBound


@dataclass(frozen=True, slots=True)
class Breaker:
    name: str
    part: str


@dataclass(frozen=True, slots=True)
class Wire:
    """`cable` names a size ("cable.cu_pvc_2_5") or a series ("cable.cu_pvc"). A series
    needs `area` and `insulation`; a family sets them to ParamRefs."""

    name: str
    cable: str          # registry part id, kind CABLE
    length: Value
    install: str        # registry process id, e.g. "install.clipped_direct"
    area: Value | None = None
    insulation: Value | None = None


@dataclass(frozen=True, slots=True)
class Terminal:
    name: str
    part: str


@dataclass(frozen=True, slots=True)
class Draw:
    """A consumer's signed current in one load case."""

    case: str
    current: Input | ParamRef


@dataclass(frozen=True, slots=True)
class Consumer:
    name: str
    draws: tuple[Draw, ...] = ()


CircuitElement = Union[Supply, Breaker, Wire, Terminal, Consumer]


@dataclass(frozen=True, slots=True)
class Circuit:
    """`ambient` and `environment` repeat the design's, so port guarantees, which see
    only the model, read the same ambient as the builders."""

    name: str
    elements: Mapping[str, CircuitElement]
    connections: tuple[Connection, ...]
    span: Span
    ambient: Input | ParamRef | None = None
    environment: str | None = None


PORTS: Mapping[type, tuple[str | None, str | None]] = {
    Supply: (None, "out"),
    Breaker: ("in", "out"),
    Wire: ("a", "b"),
    Terminal: ("wire", "out"),
    Consumer: ("in", None),
}
"""Element kind -> (upstream port, downstream port)."""

CABLE_PARAMS: Mapping[str, Dim] = {"area": AREA, "insulation": LENGTH}
"""The series parameters a size fixes and a series cable takes from the design."""


def lower_circuit(component: Component, design: Design, registry: Registry) -> Circuit:
    """Parse the attribute lines in the module docstring. Rejects (ComponentError):
    duplicate element names, a connection to an unknown element or port, a series cable
    without area and insulation, registry ids of the wrong kind, a load field other than
    current on a consumer, and a claim qoi not in QOIS."""
    problems: list[str] = []
    name = component.name
    elements: dict[str, CircuitElement] = {}
    links = []
    for attr in component.attrs:
        say = _reporter(problems, attr.span, f"{name}.{attr.key}")
        if attr.key == "connect":
            links.append(attr)
            continue
        reader = _READERS.get(attr.key)
        head = attr.args[0] if attr.args else None
        if reader is None:
            say(f"unknown attribute; a circuit takes {', '.join(sorted([*_READERS, 'connect']))}")
        elif not (isinstance(head, Ref) and len(head.parts) == 1):
            say("starts with the element's name")
        elif head.parts[0] in elements:
            say(f"element '{head.parts[0]}' is declared twice")
        else:
            element = reader(f"{name}.{head.parts[0]}", head.parts[0], attr.args[1:], design, registry, say)
            if element is not None:
                elements[head.parts[0]] = element
    connections = tuple(c for c in (_connection(name, a, elements, problems) for a in links) if c is not None)
    draws = _draws(name, design, elements, problems)
    elements = {n: Consumer(n, draws.get(n, ())) if isinstance(e, Consumer) else e for n, e in elements.items()}
    _check_references(name, design, elements, problems)
    circuit = Circuit(name, MappingProxyType(elements), connections, component.span, design.ambient, design.environment)
    if not problems:
        problems += _walk(circuit)[1]
    if problems:
        raise ComponentError(tuple(problems))
    return circuit


Say = Callable[[str], None]


def _reporter(problems: list[str], span: Span, what: str) -> Say:
    return lambda message: problems.append(f"{span.path}:{span.line}:{span.col}: {what}: {message}")


def _options(args: tuple[Arg, ...], allowed: frozenset[str], say: Say) -> dict[str, Arg]:
    """Keyword-value pairs: `voltage 230 V fault_current in [...] signed ...`."""
    found: dict[str, Arg] = {}
    if len(args) % 2:
        say("expects keyword-value pairs")
    for key, value in zip(args[::2], args[1::2]):
        word = key.parts[0] if isinstance(key, Ref) and len(key.parts) == 1 else None
        if word not in allowed:
            say(f"expects one of {', '.join(sorted(allowed))}")
        elif word in found:
            say(f"gives {word} twice")
        else:
            found[word] = value
    return found


def _registry_id(arg: Arg | None) -> str | None:
    return ".".join(arg.parts) if isinstance(arg, Ref) else None


def _part(arg: Arg | None, kind: PartKind, registry: Registry, say: Say) -> str | None:
    pid = _registry_id(arg)
    if pid is None:
        say(f"needs a registry {kind.value} id")
        return None
    try:
        registry.part(pid, kind)
    except OutsideMakeableSet as e:
        say(str(e))
        return None
    return pid


def _value(arg: Arg | None, dim: Dim, what: str, design: Design, say: Say) -> Value | None:
    if isinstance(arg, Fixed) and arg.quantity.dim == dim:
        return arg
    if isinstance(arg, ParamRef) and arg.name in design.params and design.params[arg.name].range.dim == dim:
        return arg
    say(f"{what} needs a quantity or param of the right dimension")
    return None


def _input(name: str, bound: Bound) -> Input:
    return Input(name, bound.range, bound.signature, bound.kind, bound.span, bound.mean)


def _supply(path: str, name: str, args, design: Design, registry: Registry, say: Say) -> Supply | None:
    opts = _options(args, frozenset({"voltage", "fault_current"}), say)
    voltage, fault = opts.get("voltage"), opts.get("fault_current")
    if not (isinstance(voltage, Fixed) and voltage.quantity.dim == VOLTAGE):
        say("needs voltage <quantity in V>")
        return None
    if fault is not None and not (isinstance(fault, Bound) and fault.range.dim == CURRENT):
        say("fault_current needs a signed current bound")
        return None
    return Supply(name, voltage.quantity, None if fault is None else _input(f"{path}.fault_current", fault))


def _breaker(path: str, name: str, args, design: Design, registry: Registry, say: Say) -> Breaker | None:
    part = _part(_options(args, frozenset({"part"}), say).get("part"), PartKind.BREAKER, registry, say)
    return None if part is None else Breaker(name, part)


def _terminal(path: str, name: str, args, design: Design, registry: Registry, say: Say) -> Terminal | None:
    part = _part(_options(args, frozenset({"part"}), say).get("part"), PartKind.TERMINAL, registry, say)
    return None if part is None else Terminal(name, part)


def _consumer(path: str, name: str, args, design: Design, registry: Registry, say: Say) -> Consumer | None:
    if args:
        say("a consumer takes no options")
    return Consumer(name)


def _wire(path: str, name: str, args, design: Design, registry: Registry, say: Say) -> Wire | None:
    opts = _options(args, frozenset({"cable", "length", "install", *CABLE_PARAMS}), say)
    cable = _part(opts.get("cable"), PartKind.CABLE, registry, say)
    length = _value(opts.get("length"), LENGTH, "length", design, say)
    install = _registry_id(opts.get("install"))
    process = registry.processes.get(install) if install is not None else None
    if process is None or process.kind is not ProcessKind.INSTALL or "h" not in process.props:
        say("install needs a registry install process with a surface heat-transfer coefficient h")
    params = {p: opts.get(p) for p in CABLE_PARAMS}
    if cable is not None and registry.parts[cable].series is None:
        params = {p: _value(v, CABLE_PARAMS[p], p, design, say) for p, v in params.items()}
    elif cable is not None and any(v is not None for v in params.values()):
        say(f"{cable} is a size, which fixes {' and '.join(CABLE_PARAMS)}")
    if cable is None or length is None or process is None or None in params.values() and registry.parts[cable].series is None:
        return None
    return Wire(name, cable, length, install, params["area"], params["insulation"])


_READERS = {"supply": _supply, "breaker": _breaker, "wire": _wire, "terminal": _terminal, "consumer": _consumer}


def _connection(circuit: str, attr, elements: Mapping[str, CircuitElement], problems: list[str]) -> Connection | None:
    say = _reporter(problems, attr.span, f"{circuit}.connect")
    args = attr.args
    if not (len(args) == 3 and args[1] == Punct("->") and all(isinstance(a, Ref) and len(a.parts) == 2 for a in (args[0], args[2]))):
        say("reads `connect <element>.<port> -> <element>.<port>`")
        return None
    ends = []
    for ref, side, role in ((args[0], 1, "downstream"), (args[2], 0, "upstream")):
        element, port = ref.parts
        if element not in elements:
            say(f"'{element}' is not an element of {circuit}")
            return None
        expected = PORTS[type(elements[element])][side]
        if port != expected:
            say(f"{element}.{port} is not the {role} port of {element}" + (f"; use {element}.{expected}" if expected else ""))
            return None
        ends.append(PortRef(circuit, element, port))
    return Connection(ends[0], ends[1], attr.span)


def _draws(circuit: str, design: Design, elements: Mapping[str, CircuitElement], problems: list[str]) -> dict[str, tuple[Draw, ...]]:
    found: dict[str, list[Draw]] = {}
    for case in design.loads.values():
        say = _reporter(problems, case.span, f"load {case.name}")
        for entry in case.entries:
            if entry.target[0] != circuit:
                continue
            target = ".".join(entry.target)
            if len(entry.target) != 2 or not isinstance(elements.get(entry.target[1]), Consumer):
                say(f"{target}: a circuit load acts on one of its consumers")
            elif entry.field != "current":
                say(f"{target}: a consumer's load field is current, not {entry.field}")
            elif isinstance(entry.value, Input) and entry.value.range.dim != CURRENT:
                say(f"{target}: current needs a current range")
            elif isinstance(entry.value, ParamRef) and design.params[entry.value.name].range.dim != CURRENT:
                say(f"{target}: param {entry.value.name} is not a current")
            else:
                found.setdefault(entry.target[1], []).append(Draw(case.name, entry.value))
    return {name: tuple(draws) for name, draws in found.items()}


def _check_references(circuit: str, design: Design, elements: Mapping[str, CircuitElement], problems: list[str]) -> None:
    for claim in design.claims:
        if claim.qoi.path[0] != circuit:
            continue
        say = _reporter(problems, claim.span, f"claim {claim.name}")
        mode = QOIS.get(claim.qoi.name)
        if len(claim.qoi.path) != 2 or not isinstance(elements.get(claim.qoi.path[1]), Wire):
            say("a circuit claim names one of its wires, as in lighting.w1.temperature")
        elif mode is None:
            say(f"unknown wire quantity '{claim.qoi.name}'; known: {', '.join(sorted(QOIS))}")
        elif claim.bound.dim != CRITERION_DIMS[mode]:
            say(f"{claim.qoi.name} is bounded by a {'temperature' if mode is STEADY_TEMPERATURE else 'fraction'}")
    for claim in design.probability_claims:
        path = claim.event.qoi.path if isinstance(claim.event, Exceeds) else claim.event.subject
        if path[0] == circuit:
            _reporter(problems, claim.span, f"claim {claim.name}")("v0 states no probability claim on a circuit")
    for tests in design.tests.values():
        if tests.subject[0] == circuit:
            _reporter(problems, tests.span, f"tests {tests.name}")("v0 reads no tests records on a circuit")
    for waiver in design.waivers:
        if waiver.subject[0] == circuit and len(waiver.subject) > 1 and waiver.subject[1] not in elements:
            _reporter(problems, waiver.span, "waiver")(f"'{waiver.subject[1]}' is not an element of {circuit}")


# --- Modes, quantities, model premises -----------------------------------------------

STEADY_TEMPERATURE = FailureMode("wire.steady_temperature")
SHORT_CIRCUIT = FailureMode("wire.short_circuit")
VOLTAGE_DROP = FailureMode("wire.voltage_drop")
OVERLOAD_PROTECTION = FailureMode("wire.overload_protection")

_MODULE = sys.modules[__name__]
_MAINTAINERS = "lola-maintainers"

THERMAL = model_spec(
    _MODULE, "wire.thermal",
    "steady heat balance of one PVC-insulated copper conductor: insulation T1 plus surface-to-air T4 = 1/(pi D h), "
    "conductor resistance linear in temperature",
    "steady state; one cable clipped direct in still air with no grouping or solar gain; no thermal runaway, "
    "which the statement itself checks; the wire carries its consumer's current",
    _MAINTAINERS, "IEC 60287-1-1 and IEC 60287-2-1 heat balance; IEC 60364-4-43:2008 433.1 overload conditions",
)
ADIABATIC = model_spec(
    _MODULE, "wire.adiabatic",
    "adiabatic short-circuit heating I2t <= k^2 S^2, k from IEC 60949 between theta_max and theta_sc; the breaker's "
    "let-through I2t at its rated breaking capacity bounds every fault up to that capacity",
    "no heat is lost to the insulation during the fault; the conductor starts at theta_max; an "
    "energy-limiting breaker",
    _MAINTAINERS, "IEC 60949:1988; IEC 60364-4-43:2008 434.5.2",
    unchecked=("the fault is cleared within 5 s (IEC 60364-4-43:2008 434.5.2); no breaker operating time is in the "
               "registry, so nothing states it",),
)
DROP = model_spec(
    _MODULE, "wire.drop",
    "voltage drop 2 L I R20 (1 + alpha (theta_max - 20)) per wire, conductor at its maximum operating temperature, "
    "summed over the wires in series from the supply",
    "each wire a single-phase go-and-return run of length L; resistive load; conductor reactance neglected",
    _MAINTAINERS, "IEC 60364-5-52:2009 Annex G",
)
SERIES = model_spec(
    _MODULE, "wire.series",
    "radial series path: every element between a supply and its consumer carries the consumer's current",
    "one consumer per path; no leakage and no parallel path",
    _MAINTAINERS, "Kirchhoff's current law on a radial circuit",
)

MODELS: Mapping[FailureMode, ModelSpec] = {
    STEADY_TEMPERATURE: THERMAL,
    OVERLOAD_PROTECTION: THERMAL,
    SHORT_CIRCUIT: ADIABATIC,
    VOLTAGE_DROP: DROP,
}
"""SERIES is not listed: it backs only the current a wire guarantees at its ports."""

QOIS: Mapping[str, FailureMode] = {
    "temperature": STEADY_TEMPERATURE,
    "voltage_drop": VOLTAGE_DROP,
    "fault_withstand": SHORT_CIRCUIT,
    "overload_protection": OVERLOAD_PROTECTION,
}

CRITERION_DIMS: Mapping[FailureMode, Dim] = {
    STEADY_TEMPERATURE: TEMPERATURE,
    VOLTAGE_DROP: DIMENSIONLESS,
    SHORT_CIRCUIT: DIMENSIONLESS,
    OVERLOAD_PROTECTION: DIMENSIONLESS,
}
"""What a criterion bounds: a temperature, or a fraction (of V, or a utilisation)."""

OVERLOAD_FACTOR = "iec60364_4_43.overload_factor"
"""The registry constant behind I_2 <= 1.45 I_z. A criterion of the standard rather than a
property of any part, so the builder reads it with sb.constant."""

# --- Elaboration -------------------------------------------------------------------------


@dataclass(frozen=True)
class SeriesPath:
    """supply -> breaker -> wires/terminals -> consumer, in connection order."""

    supply: str
    breaker: str | None
    elements: tuple[str, ...]
    consumer: str


def topology(circuit: Circuit) -> tuple[SeriesPath, ...]:
    """Series paths from the connection list. A wire with no upstream breaker still gets
    its thermal obligation; overload protection on it is a gap (NoRuleForQuantity, "no
    protective device")."""
    return _walk(circuit)[0]


def _walk(circuit: Circuit) -> tuple[tuple[SeriesPath, ...], list[str]]:
    """The paths, and what stops the circuit being radial: a port joined twice (other
    than a supply's out), a chain that ends short of a consumer, an element on no path,
    a second breaker on a path, or a wire upstream of its breaker."""
    problems: list[str] = []
    next_of: dict[str, list[str]] = {}
    joined: dict[PortRef, int] = {}
    for c in circuit.connections:
        next_of.setdefault(c.a.element, []).append(c.b.element)
        for end in (c.a, c.b):
            joined[end] = joined.get(end, 0) + 1
    for end, n in joined.items():
        if n > 1 and not isinstance(circuit.elements[end.element], Supply):
            problems.append(f"{circuit.name}: {end.element}.{end.port} is connected {n} times; v0 circuits are radial")
    paths, seen = [], set()
    for name, supply in circuit.elements.items():
        if not isinstance(supply, Supply):
            continue
        seen.add(name)
        for first in next_of.get(name, []):
            chain, at = [], first
            while at not in seen and not isinstance(circuit.elements[at], Consumer) and len(next_of.get(at, [])) == 1:
                seen.add(at)
                chain.append(at)
                at = next_of[at][0]
            if at in seen or not isinstance(circuit.elements[at], Consumer):
                problems.append(f"{circuit.name}: the path from {name} through {at} does not end at a consumer")
                continue
            seen.add(at)
            breakers = [e for e in chain if isinstance(circuit.elements[e], Breaker)]
            wires = [i for i, e in enumerate(chain) if isinstance(circuit.elements[e], Wire)]
            if len(breakers) > 1:
                problems.append(f"{circuit.name}: v0 models one breaker per path, not {', '.join(breakers)}")
            elif breakers and wires and wires[0] < chain.index(breakers[0]):
                problems.append(f"{circuit.name}: {chain[wires[0]]} is upstream of {breakers[0]}, which cannot protect it")
            rest = tuple(e for e in chain if e not in breakers)
            paths.append(SeriesPath(name, breakers[0] if breakers else None, rest, at))
    for name in circuit.elements:
        if name not in seen:
            problems.append(f"{circuit.name}: {name} is not on a path from a supply to a consumer")
    return tuple(paths), problems


def _path_of(circuit: Circuit, wire: str) -> SeriesPath:
    return next(p for p in topology(circuit) if wire in p.elements)


@dataclass(frozen=True)
class _Cable:
    """A wire's cable inside one statement: its series entry and the hypotheses for the
    series parameters. A size fixes them (design values named after the size, the
    StatementBuilder's convention); a series cable takes them from the design."""

    sb: StatementBuilder
    series: str
    params: Mapping[str, Sym]

    def __getitem__(self, prop: str) -> Expr:
        if prop in self.params:
            return self.params[prop]
        return self.sb.registry(self.series, prop, series=self.params)


def _cable(sb: StatementBuilder, circuit: Circuit, wire: Wire, registry: Registry) -> _Cable:
    part = registry.part(wire.cable, PartKind.CABLE)
    if part.series is None:
        values = {p: sb.value(getattr(wire, p), f"{circuit.name}.{wire.name}.{p}") for p in CABLE_PARAMS}
        return _Cable(sb, wire.cable, values)
    values = {p: sb.value(Fixed(Quantity(v, CABLE_PARAMS[p])), f"{wire.cable}.{p}") for p, v in part.fixes.items()}
    return _Cable(sb, part.series, values)


def steady_temperature(sb: StatementBuilder, circuit: Circuit, wire: Wire, current: Expr, ambient: Expr, registry: Registry) -> tuple[Expr, Expr]:
    """(theta expression, runaway side condition). Shared by the thermal obligation, the
    overload check, and the wire's port temperature guarantee, so all three use one
    derivation."""
    cable = _cable(sb, circuit, wire, registry)
    alpha = cable["alpha"]
    t4 = Div(Const(Fraction(1)), Mul((Pi(), cable["outer_diameter"], sb.registry(wire.install, "h"))))
    a = Mul((PowInt(current, 2), cable["R20"], Add((cable["T1"], t4))))
    a_alpha = Mul((a, alpha))
    rise = Mul((a, Add((Const(Fraction(1)), Neg(Mul((Const(Fraction(20)), alpha)))))))
    theta = Div(Add((ambient, rise)), PowInt(Sqrt(Add((Const(Fraction(1)), Neg(a_alpha)))), 2))
    return theta, Add((a_alpha, Const(Fraction(-1))))


def _current(sb: StatementBuilder, draw: Draw) -> Sym:
    return sb.input(draw.current) if isinstance(draw.current, Input) else sb.value(draw.current, draw.case)


def _ambient(sb: StatementBuilder, circuit: Circuit) -> Sym:
    if isinstance(circuit.ambient, Input):
        return sb.input(circuit.ambient)
    if isinstance(circuit.ambient, ParamRef):
        return sb.value(circuit.ambient, "ambient")
    return sb.registry(circuit.environment, "ambient")


def _has_ambient(circuit: Circuit) -> bool:
    return circuit.ambient is not None or circuit.environment is not None


def _times(factor: Fraction, e: Expr) -> Expr:
    return e if factor == 1 else Mul((Const(factor), e))


def _over(e: Expr, factor: Fraction) -> Expr:
    return e if factor == 1 else Div(e, Const(factor))


def _minus(a: Expr, b: Expr) -> Expr:
    return Add((a, Neg(b)))


@dataclass(frozen=True)
class _Setting:
    """What every wire obligation reads: the wire, its path, and the draws it is checked
    under (one obligation per load case)."""

    wire: Wire
    path: SeriesPath
    draws: tuple[Draw, ...]
    bound: Fraction | None   # the criterion's upper bound; None: the cable's own limit


def _setting(req: Requirement, circuit: Circuit, design: Design, qoi: str, ambient: bool) -> _Setting | Gap:
    """The common preamble, or the gap that stops it: a GE criterion, a missing draw in a
    load case the requirement is checked under, or a missing ambient."""
    wire = circuit.elements[req.subject[1]]
    path = _path_of(circuit, wire.name)
    criterion = req.criterion
    if isinstance(criterion, Criterion) and criterion.rel is Rel.GE:
        return Gap(req, (NoRuleForQuantity(qoi, f"a wire's {qoi} is bounded from above only"),))
    consumers = [e for e in circuit.elements.values() if isinstance(e, Consumer)]
    cases = req.under or tuple(dict.fromkeys(d.case for c in consumers for d in c.draws))
    by_case = {d.case: d for d in circuit.elements[path.consumer].draws}
    needs: list[GapNeed] = []
    if not cases or any(case not in by_case for case in cases):
        needs.append(NeedsInputBound((circuit.name, path.consumer), "current", "A"))
    if ambient and not _has_ambient(circuit):
        needs.append(NeedsInputBound((design.name,), "ambient", "degC"))
    if needs:
        return Gap(req, tuple(needs))
    bound = criterion.bound.value.lo if isinstance(criterion, Criterion) else None
    return _Setting(wire, path, tuple(by_case[c] for c in cases), bound)


def build_steady_temperature(req: Requirement, circuit: Circuit, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    s = _setting(req, circuit, design, "temperature", ambient=True)
    if isinstance(s, Gap):
        return (s,)
    out = []
    for draw in s.draws:
        sb = StatementBuilder(design, registry)
        theta, runaway = steady_temperature(sb, circuit, s.wire, _current(sb, draw), _ambient(sb, circuit), registry)
        limit = _cable(sb, circuit, s.wire, registry)["theta_max"] if s.bound is None else Const(s.bound)
        what = "its insulation's maximum operating temperature" if s.bound is None else f"{float(s.bound):g} degC"
        out.append(Obligation(req, sb.finish(AllNonpositive((_minus(theta, limit), runaway))), THERMAL,
                              f"{circuit.name}.{s.wire.name} runs at or below {what} under {draw.case}"))
    return tuple(out)


def build_short_circuit(req: Requirement, circuit: Circuit, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """Gap needing NeedsInputBound when the supply has no signed prospective fault current."""
    wire = circuit.elements[req.subject[1]]
    path = _path_of(circuit, wire.name)
    supply = circuit.elements[path.supply]
    criterion = req.criterion
    needs: list[GapNeed] = []
    if isinstance(criterion, Criterion) and criterion.rel is Rel.GE:
        needs.append(NoRuleForQuantity("fault_withstand", "a wire's fault_withstand is bounded from above only"))
    if supply.fault_current is None:
        needs.append(NeedsInputBound((circuit.name, supply.name), "fault_current", "A"))
    if path.breaker is None:
        needs.append(NoRuleForQuantity("fault_withstand", f"no protective device upstream of {circuit.name}.{wire.name} limits the let-through energy"))
    if needs:
        return (Gap(req, tuple(needs)),)
    u = criterion.bound.value.lo if isinstance(criterion, Criterion) else Fraction(1)
    breaker = circuit.elements[path.breaker].part
    sb = StatementBuilder(design, registry)
    cable = _cable(sb, circuit, wire, registry)
    withstand = Mul((PowInt(cable["k"], 2), PowInt(cable["area"], 2)))
    exprs = (
        _minus(sb.registry(breaker, "I2t"), _times(u, withstand)),
        _minus(sb.input(supply.fault_current), _times(u, sb.registry(breaker, "Icn"))),
    )
    return (Obligation(req, sb.finish(AllNonpositive(exprs)), ADIABATIC,
                       f"{circuit.name}.{wire.name} survives the energy {path.breaker} lets through, and {path.breaker} breaks the fault"),)


def build_voltage_drop(req: Requirement, circuit: Circuit, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    s = _setting(req, circuit, design, "voltage_drop", ambient=False)
    if isinstance(s, Gap):
        return (s,)
    supply = circuit.elements[s.path.supply]
    u = Fraction(1, 20) if s.bound is None else s.bound
    upstream = s.path.elements[: s.path.elements.index(s.wire.name) + 1]
    wires = [circuit.elements[e] for e in upstream if isinstance(circuit.elements[e], Wire)]
    out = []
    for draw in s.draws:
        sb = StatementBuilder(design, registry)
        current = _current(sb, draw)
        drops = tuple(_wire_drop(sb, circuit, w, current, registry) for w in wires)
        drop = drops[0] if len(drops) == 1 else Add(drops)
        volts = sb.value(Fixed(supply.voltage), f"{circuit.name}.{supply.name}.voltage")
        out.append(Obligation(req, sb.finish(AllNonpositive((_minus(drop, _times(u, volts)),))), DROP,
                              f"the far end of {circuit.name}.{s.wire.name} is at most {float(u * 100):g} % below "
                              f"{supply.name}'s voltage under {draw.case}"))
    return tuple(out)


def _wire_drop(sb: StatementBuilder, circuit: Circuit, wire: Wire, current: Expr, registry: Registry) -> Expr:
    cable = _cable(sb, circuit, wire, registry)
    hot = Mul((cable["R20"], Add((Const(Fraction(1)), Mul((cable["alpha"], Add((cable["theta_max"], Const(Fraction(-20))))))))))
    return Mul((Const(Fraction(2)), sb.value(wire.length, f"{circuit.name}.{wire.name}.length"), current, hot))


def build_overload_protection(req: Requirement, circuit: Circuit, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    s = _setting(req, circuit, design, "overload_protection", ambient=True)
    if isinstance(s, Gap):
        return (s,)
    if s.path.breaker is None:
        return (Gap(req, (NoRuleForQuantity("overload_protection", f"no protective device upstream of {circuit.name}.{s.wire.name}"),)),)
    u = Fraction(1) if s.bound is None else s.bound
    breaker = circuit.elements[s.path.breaker].part
    out = []
    for draw in s.draws:
        sb = StatementBuilder(design, registry)
        rated = sb.registry(breaker, "In")
        tripping = sb.registry(breaker, "I_t")
        ambient = _ambient(sb, circuit)
        theta_max = _cable(sb, circuit, s.wire, registry)["theta_max"]
        exprs = [_minus(_current(sb, draw), _times(u, rated))]
        for current in (_over(rated, u), Div(tripping, _times(u, sb.constant(OVERLOAD_FACTOR)))):
            theta, runaway = steady_temperature(sb, circuit, s.wire, current, ambient, registry)
            exprs += [_minus(theta, theta_max), runaway]
        out.append(Obligation(req, sb.finish(AllNonpositive(tuple(exprs))), THERMAL,
                              f"{s.path.breaker} protects {circuit.name}.{s.wire.name} against overload under {draw.case} (I_B <= I_n <= I_z, I_2 <= 1.45 I_z)"))
    return tuple(out)


# --- Coverage ------------------------------------------------------------------------

CONDUCTOR = FeatureKind("wire.conductor")


def _part_of(element: CircuitElement) -> str | None:
    match element:
        case Wire():
            return element.cable
        case Breaker() | Terminal():
            return element.part
    return None


def features(circuit: Circuit, design: Design, registry: Registry) -> tuple[Feature, ...]:
    """One CONDUCTOR feature per wire (its conductor material, energy {ELECTRICAL,
    THERMAL}), one CONTACT_PAIR per connection between two parts (wire conductor against
    terminal body, each part's exposed surface by Registry.surface), plus the
    environment. A v0 cable part names only its conductor material, so no insulation
    material reaches coverage."""
    found = [
        Feature((circuit.name, e.name), CONDUCTOR, (registry.parts[e.cable].material,),
                frozenset({EnergyDomain.ELECTRICAL, EnergyDomain.THERMAL}), design.environment)
        for e in circuit.elements.values() if isinstance(e, Wire)
    ]
    for c in circuit.connections:
        parts = [_part_of(circuit.elements[end.element]) for end in (c.a, c.b)]
        if None not in parts:
            found.append(Feature((circuit.name, c.a.element, c.b.element), CONTACT_PAIR,
                                 tuple(registry.surface(registry.parts[p].material, registry.parts[p].process) for p in parts),
                                 frozenset({EnergyDomain.ELECTRICAL, EnergyDomain.CHEMICAL}), design.environment))
    return tuple(found)


def _is_conductor(feature: Feature, registry: Registry) -> bool:
    return feature.kind == CONDUCTOR


def _fraction(x: Fraction) -> Quantity:
    return Quantity(Interval(x, x), DIMENSIONLESS)


_DEFAULTS: Mapping[FailureMode, Criterion] = {
    SHORT_CIRCUIT: Criterion(Rel.LE, _fraction(Fraction(1))),
    OVERLOAD_PROTECTION: Criterion(Rel.LE, _fraction(Fraction(1))),
    VOLTAGE_DROP: Criterion(Rel.LE, _fraction(Fraction(1, 20))),
}


def _default_criterion(mode: FailureMode, feature: Feature) -> Criterion | None:
    """Conductor at or below the insulation's theta_max, fault withstand and overload
    protection hold, voltage drop at most 5 %. Steady temperature has no fixed number:
    None tells its builder to read the cable's theta_max from the registry."""
    return _DEFAULTS.get(mode)


COVERAGE: tuple[CoverageRule, ...] = (
    CoverageRule(
        id="wire.conductor",
        when=_is_conductor,
        demands=(STEADY_TEMPERATURE, SHORT_CIRCUIT, OVERLOAD_PROTECTION, VOLTAGE_DROP),
        default=_default_criterion,
        note="every wire must survive its steady current, a fault, and an overload, and deliver its voltage",
    ),
)


def ports(circuit: Circuit, registry: Registry) -> Ports:
    """PortSpecs (see models.base) and the circuit's connections:
      wire.a / wire.b   guarantee TEMPERATURE <= steady_temperature(...)  (model bound)
                        guarantee CURRENT     in consumer's signed range
      terminal.wire     assume    TEMPERATURE <= rating temperature_max   (stated)
                        assume    CURRENT     <= rating current_max       (stated)
      breaker.out       guarantee CURRENT     <= I_n is NOT claimed: a breaker does not
                        bound steady current below I_n; overload protection covers it.
    A wire whose consumer has no signed draw guarantees nothing, and with no ambient it
    guarantees no temperature, so a terminal on it is a gap rather than a pass.
    """
    specs = []
    for path in topology(circuit):
        draws = circuit.elements[path.consumer].draws
        for name in path.elements:
            element = circuit.elements[name]
            if isinstance(element, Wire):
                given = _wire_guarantees(circuit, element, draws, registry)
                specs += [PortSpec(PortRef(circuit.name, name, port), {}, given) for port in PORTS[Wire]]
            elif isinstance(element, Terminal):
                specs.append(PortSpec(PortRef(circuit.name, name, "wire"), _terminal_assumptions(element.part), {}))
    return Ports(tuple(specs), circuit.connections)


def _drawn(op: type, draws: tuple[Draw, ...]) -> Callable[[StatementBuilder], Expr]:
    def build(sb: StatementBuilder) -> Expr:
        currents = tuple(_current(sb, d) for d in draws)
        return currents[0] if len(currents) == 1 else op(currents)
    return build


def _wire_guarantees(circuit: Circuit, wire: Wire, draws: tuple[Draw, ...], registry: Registry) -> dict[PortQuantity, Side]:
    if not draws:
        return {}
    most = _drawn(Max, draws)
    given = {PortQuantity.CURRENT: Side(_drawn(Min, draws), most, SERIES)}
    if _has_ambient(circuit):
        def hottest(sb: StatementBuilder) -> Expr:
            return steady_temperature(sb, circuit, wire, most(sb), _ambient(sb, circuit), registry)[0]
        given[PortQuantity.TEMPERATURE] = Side(None, hottest, THERMAL)
    return given


def _rating(part: str, prop: str) -> Callable[[StatementBuilder], Expr]:
    return lambda sb: sb.registry(part, prop)


def _terminal_assumptions(part: str) -> dict[PortQuantity, Side]:
    return {
        PortQuantity.TEMPERATURE: Side(None, _rating(part, "temperature_max"), None),
        PortQuantity.CURRENT: Side(None, _rating(part, "current_max"), None),
    }


DOMAIN = DomainSpec(
    name="circuit",
    kinds={"circuit": lower_circuit},
    builders={
        STEADY_TEMPERATURE: build_steady_temperature,
        SHORT_CIRCUIT: build_short_circuit,
        VOLTAGE_DROP: build_voltage_drop,
        OVERLOAD_PROTECTION: build_overload_protection,
    },
    unmodelled=frozenset(),
    qois=QOIS,
    probability={},
    coverage=COVERAGE,
    models=MODELS,
    features=features,
    ports=ports,
)
