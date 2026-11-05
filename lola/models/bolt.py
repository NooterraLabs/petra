"""Domain: bolted joints. Trusted physics; footprint premises "model:bolt.*@<hash>".

Component kind `joint`. Attribute lines, one per line inside the block:

    bolt <registry bolt id> count <n>
    plate <registry material id> thickness <value> [process <registry process id>]
    torque <signed bound>
    nut_factor <signed bound>
    load_share <signed bound>

Load field: force on `<joint>`. Claim path: `<joint>.<qoi>`.

Bolt tension (simplified VDI 2230 load sharing, concentric axial load):
    F_bolt = F_V + Phi * F_A / n,      F_V = T / (K d)         (torque-tension relation)
    goal  F_bolt - u * Sp * As <= 0    (u = claimed utilisation, default 1 = proof load)
T is the signed tightening torque range, K the nut factor (measured or judged input),
Phi the joint load factor (judged input), F_A the signed external load, n the bolt count.
As and Sp*As come from the registry derivations (ISO 898-1, ISO 724), Sp from the
property class as a sanctioned premise.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..ir import Component, Design, Input, Span, Value
from ..kernel import Expr
from ..registry import Registry
from .base import (
    NO_PORTS,
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

# --- Typed model, produced by lower_joint --------------------------------------------


@dataclass(frozen=True, slots=True)
class Plate:
    material: str
    thickness: Value
    process: str | None = None   # e.g. "process.zinc_plate"; changes surface/galvanic class


@dataclass(frozen=True, slots=True)
class BoltedJoint:
    name: str
    bolt: str            # registry part id, kind BOLT (thread + property class + coating)
    count: int
    plates: tuple[Plate, ...]
    torque: Input | None
    nut_factor: Input | None
    load_share: Input | None   # joint load factor Phi (VDI 2230 notation)
    span: Span


def lower_joint(component: Component, design: Design, registry: Registry) -> BoltedJoint:
    """Parse the attribute lines in the module docstring. Names the bounds
    "<joint>.torque", "<joint>.nut_factor" and "<joint>.load_share". Rejects
    (ComponentError): a missing or repeated bolt line, fewer than two plates, registry ids
    of the wrong kind, a load field other than force, and a claim qoi not in QOIS."""
    raise NotImplementedError


# --- Modes, quantities, model premises -----------------------------------------------

TENSION = FailureMode("bolt.tension")
PLATE_BEARING = FailureMode("bolt.plate_bearing")

MODELS: Mapping[FailureMode, ModelSpec] = {}
"""TODO: "bolt.tension" (torque-tension with nut factor; linear load sharing Phi; no
prying; no thermal preload change)."""

QOIS: Mapping[str, FailureMode] = {
    "bolt_tension": TENSION,
    "tension_utilisation": TENSION,
}

# --- Elaboration -------------------------------------------------------------------------


def bolt_force(sb: StatementBuilder, joint: BoltedJoint, external: Expr) -> Expr:
    """F_V + Phi * external / n as an Expr over input and registry hyps."""
    raise NotImplementedError


def build_tension(req: Requirement, joint: BoltedJoint, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """Gap needing NeedsInputBound for each of torque, nut_factor, load_share that is None."""
    raise NotImplementedError


# --- Coverage ------------------------------------------------------------------------

BOLTED_JOINT = FeatureKind("bolt.joint")


def features(joint: BoltedJoint, design: Design, registry: Registry) -> tuple[Feature, ...]:
    """One BOLTED_JOINT feature for the joint, and one CONTACT_PAIR per pair of materials
    in contact (bolt against each plate, plate against plate), each with its process
    applied, plus the environment. The galvanic rule in lola/coverage.py reads the pairs."""
    raise NotImplementedError


def _is_joint(feature: Feature, registry: Registry) -> bool:
    raise NotImplementedError


def _default_criterion(mode: FailureMode, feature: Feature) -> Criterion | None:
    """Tension utilisation <= 1 (proof load). None for PLATE_BEARING, which is unmodelled."""
    raise NotImplementedError


COVERAGE: tuple[CoverageRule, ...] = (
    CoverageRule(
        id="bolt.tension",
        when=_is_joint,
        demands=(TENSION,),
        default=_default_criterion,
        note="every bolt stays below its proof load",
    ),
    CoverageRule(
        id="bolt.bearing",
        when=_is_joint,
        demands=(PLATE_BEARING,),
        default=_default_criterion,
        note="every plate carries the bolt's bearing load",
    ),
)


def ports(joint: BoltedJoint, registry: Registry) -> Ports:
    return NO_PORTS


DOMAIN = DomainSpec(
    name="bolt",
    kinds={"joint": lower_joint},
    builders={TENSION: build_tension},
    unmodelled=frozenset({PLATE_BEARING}),
    qois=QOIS,
    probability={},
    coverage=COVERAGE,
    models=MODELS,
    features=features,
    ports=ports,
)
