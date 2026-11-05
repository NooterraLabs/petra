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

Steady temperature (IEC 60287-style heat balance, single conductor, steady state):
    theta - Ta = I^2 R20 (1 + alpha (theta - 20)) T,        T = T1 + T4  [K m / W]
    T1 = rho_T / (2 pi) ln(D / d)                            insulation
    T4 = 1 / (pi D h)                                        surface to air, clipped direct
Linear in theta, so with a = I^2 R20 T:
    theta = (Ta + a (1 - 20 alpha)) / (1 - a alpha)          valid while a alpha < 1
R4 goal: AllNonpositive([theta - theta_max, a*alpha - 1]). The second expression is the
thermal-runaway side condition; the kernel also rejects the division if it fails.

Short circuit (IEC 60949 adiabatic):  I2t_let_through - k^2 S^2 <= 0, with k derived from
copper constants (registry), and I_fault - I_cn <= 0 (breaker breaking capacity).

Voltage drop:  2 L I R20 (1 + alpha (theta_max - 20)) - limit * V <= 0  (conservative:
conductor at its maximum temperature).

Overload protection (IEC 60364-4-43 433.1 as a sanctioned premise): I_B <= I_n and
theta(I = I_n, Ta) <= theta_max, i.e. I_n <= I_z without computing I_z.

Current through a wire comes from the consumer's signed load case on the same series
path, never from a default. Ambient comes from the design's signed ambient, or else the
environment class's ambient range; with neither, the obligation is a gap needing
NeedsInputBound.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Union

from ..ir import Component, Design, Input, Span, Value
from ..kernel import Expr
from ..registry import Registry
from ..units import Quantity
from .base import (
    Connection,
    CoverageRule,
    Criterion,
    DomainSpec,
    Elaborated,
    FailureMode,
    Feature,
    FeatureKind,
    ModelSpec,
    Ports,
    Requirement,
    StatementBuilder,
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
class Consumer:
    name: str


CircuitElement = Union[Supply, Breaker, Wire, Terminal, Consumer]


@dataclass(frozen=True, slots=True)
class Circuit:
    name: str
    elements: Mapping[str, CircuitElement]
    connections: tuple[Connection, ...]
    span: Span


def lower_circuit(component: Component, design: Design, registry: Registry) -> Circuit:
    """Parse the attribute lines in the module docstring. Rejects (ComponentError):
    duplicate element names, a connection to an unknown element or port, a series cable
    without area and insulation, registry ids of the wrong kind, a load field other than
    current on a consumer, and a claim qoi not in QOIS."""
    raise NotImplementedError


# --- Modes, quantities, model premises -----------------------------------------------

STEADY_TEMPERATURE = FailureMode("wire.steady_temperature")
SHORT_CIRCUIT = FailureMode("wire.short_circuit")
VOLTAGE_DROP = FailureMode("wire.voltage_drop")
OVERLOAD_PROTECTION = FailureMode("wire.overload_protection")

MODELS: Mapping[FailureMode, ModelSpec] = {}
"""TODO: "wire.thermal" (steady temperature, overload protection, port temperature
guarantee), "wire.adiabatic" (short circuit), "wire.drop" (voltage drop)."""

QOIS: Mapping[str, FailureMode] = {
    "temperature": STEADY_TEMPERATURE,
    "voltage_drop": VOLTAGE_DROP,
    "fault_withstand": SHORT_CIRCUIT,
    "overload_protection": OVERLOAD_PROTECTION,
}

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
    raise NotImplementedError


def steady_temperature(sb: StatementBuilder, circuit: Circuit, wire: Wire, current: Expr, ambient: Expr) -> tuple[Expr, Expr]:
    """(theta expression, runaway side condition). Shared by the thermal obligation, the
    overload check, and the wire's port temperature guarantee, so all three use one
    derivation."""
    raise NotImplementedError


def build_steady_temperature(req: Requirement, circuit: Circuit, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    raise NotImplementedError


def build_short_circuit(req: Requirement, circuit: Circuit, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """Gap needing NeedsInputBound when the supply has no signed prospective fault current."""
    raise NotImplementedError


def build_voltage_drop(req: Requirement, circuit: Circuit, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    raise NotImplementedError


def build_overload_protection(req: Requirement, circuit: Circuit, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    raise NotImplementedError


# --- Coverage ------------------------------------------------------------------------

CONDUCTOR = FeatureKind("wire.conductor")


def features(circuit: Circuit, design: Design, registry: Registry) -> tuple[Feature, ...]:
    """One CONDUCTOR feature per wire (conductor and insulation materials, energy
    {ELECTRICAL, THERMAL}), one CONTACT_PAIR per connection between two materials (wire
    conductor against terminal body), plus the environment."""
    raise NotImplementedError


def _is_conductor(feature: Feature, registry: Registry) -> bool:
    raise NotImplementedError


def _default_criterion(mode: FailureMode, feature: Feature) -> Criterion | None:
    """Conductor at or below the insulation's theta_max, fault withstand and overload
    protection hold, voltage drop at most 5 %."""
    raise NotImplementedError


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
    """
    raise NotImplementedError


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
