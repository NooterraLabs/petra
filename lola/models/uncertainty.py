"""Domain: a demand against a capacity, with the demand known only by range and mean or
by sampled tests. Trusted; footprint premises "model:uncertain.*@<hash>".

Component kind `demand`. Attribute lines, one per line inside the block:

    capacity <signed bound>        the capacity the demand is compared with

The capacity bound is named "<demand>.capacity". Load field: force on `<demand>`, a
signed range with a signed mean. Probability claim paths: `P(<demand>.utilisation > u)`
with method RangeMean, and `P(fail <demand> at <level>)` with method FromTests. The
domain states no worst-case claim and has no coverage rules: what probability is
acceptable is the requirement owner's claim.

  P(demand / capacity > u) <= p under a load known by range and mean    -> R5 MomentBound
      RandomVar(x, lo = in:<load> lo hyp, hi = in:<load> hi hyp)
      MomentConstraint(fn = x, lo = mean hyp, hi = mean hyp)
      fail = x - u * capacity, with capacity a RangeHyp over its signed bound
      model "uncertain.moment": no distribution assumed; only support and mean.

  P(fail at level) <= eps with confidence c, from n trials with k failures -> R6
      BinomialTail(n = trials hyp, k = failures hyp, eps = p, beta = 1 - c)
      premises: the tests record (measured, label in:<design>.tests.<name>) and
      model "uncertain.scenario": trials are i.i.d. draws at or above the claimed
      level (validated_model; its validity text says what makes a test count).
      The claim's level must be <= the tested level; otherwise the requirement is a
      gap needing NoRuleForQuantity, since a test at 30 kN says nothing about 35 kN.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..ir import Component, Design, FromTests, Input, RangeMean, Span
from ..registry import Registry
from .base import (
    NO_PORTS,
    DomainSpec,
    Elaborated,
    FailureMode,
    Feature,
    ModelSpec,
    Ports,
    Requirement,
)

# --- Typed model, produced by lower_demand -------------------------------------------


@dataclass(frozen=True, slots=True)
class Demand:
    name: str
    capacity: Input
    span: Span


def lower_demand(component: Component, design: Design, registry: Registry) -> Demand:
    """Parse the attribute line in the module docstring. Rejects (ComponentError): a
    missing or repeated capacity, a capacity without the dimension of force, a load
    field other than force, a probability claim whose qoi is not utilisation, and an
    ordinary (non-probability) claim on the demand."""
    raise NotImplementedError


# --- Modes, model premises -----------------------------------------------------------

RANGE_MEAN = FailureMode("uncertain.range_mean")
TESTED = FailureMode("uncertain.tested")

MODELS: Mapping[FailureMode, ModelSpec] = {}
"""TODO: "uncertain.moment" and "uncertain.scenario"."""

# --- Elaboration -------------------------------------------------------------------------


def build_range_mean(req: Requirement, demand: Demand, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """Gap needing NeedsInputBound when the load has no signed mean."""
    raise NotImplementedError


def build_tested(req: Requirement, demand: Demand, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    raise NotImplementedError


def features(demand: Demand, design: Design, registry: Registry) -> tuple[Feature, ...]:
    """None in v0: a demand has no material and no contact."""
    return ()


def ports(demand: Demand, registry: Registry) -> Ports:
    return NO_PORTS


DOMAIN = DomainSpec(
    name="uncertainty",
    kinds={"demand": lower_demand},
    builders={RANGE_MEAN: build_range_mean, TESTED: build_tested},
    unmodelled=frozenset(),
    qois={},
    probability={RangeMean: RANGE_MEAN, FromTests: TESTED},
    coverage=(),
    models=MODELS,
    features=features,
    ports=ports,
)
