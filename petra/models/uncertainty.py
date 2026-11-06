"""Domain: a demand against a capacity, with the demand known only by range and mean or
by sampled tests. Trusted; footprint premises "model:uncertain.*@<hash>".

Component kind `demand`. Attribute lines, one per line inside the block:

    capacity <signed bound>        the capacity the demand is compared with

The capacity bound is named "<demand>.capacity" and must be a positive force, so that
utilisation = force / capacity > u is the same event as force - u * capacity > 0. Load
field: force on `<demand>`, a signed range with a signed mean. Probability claim paths:
`P(<demand>.utilisation > u)` with method RangeMean, and `P(fail <demand> at <level>)`
with method FromTests. The domain states no worst-case claim and has no coverage rules:
what probability is acceptable is the requirement owner's claim.

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

import sys
from dataclasses import dataclass
from typing import Callable, Mapping

from ..ir import Bound, Component, Design, Exceeds, FailsAt, FromTests, Input, ParamRef, RangeMean, Span
from ..kernel import Add, Const, Mul, Neg, Sym
from ..kernel.rules.r5_moment import MomentBound, MomentConstraint, RandomVar
from ..kernel.rules.r6_scenario import BinomialTail
from ..registry import Registry
from ..units import DIMENSIONLESS, FORCE, Dim, format_quantity
from .base import (
    NO_PORTS,
    ComponentError,
    DomainSpec,
    Elaborated,
    FailureMode,
    Feature,
    Gap,
    ModelSpec,
    NeedsInputBound,
    NoRuleForQuantity,
    Obligation,
    Ports,
    Requirement,
    StatementBuilder,
    model_spec,
)

# --- Typed model, produced by lower_demand -------------------------------------------


@dataclass(frozen=True, slots=True)
class Demand:
    name: str
    capacity: Input
    span: Span


def lower_demand(component: Component, design: Design, registry: Registry) -> Demand:
    """Parse the attribute line in the module docstring. Rejects (ComponentError): a
    missing or repeated capacity, a capacity that is not a positive signed force or that
    carries a mean, any other attribute, a load field other than force, a probability
    claim whose qoi is not utilisation or whose threshold has a dimension, a tests record
    or tested failure that is not on the demand itself, and an ordinary
    (non-probability) claim on the demand."""
    problems: list[str] = []
    name = component.name
    capacities: list[Input] = []
    for attr in component.attrs:
        say = _reporter(problems, attr.span, f"{name}.{attr.key}")
        if attr.key != "capacity":
            say("unknown attribute; a demand takes capacity")
            continue
        bound = attr.args[0] if len(attr.args) == 1 else None
        if not (isinstance(bound, Bound) and bound.range.dim == FORCE):
            say("needs one signed force bound")
        elif bound.range.value.lo <= 0:
            say("a capacity is a positive force")
        elif bound.mean is not None:
            say("a capacity takes no mean; only the load's mean enters a probability bound")
        else:
            capacities.append(Input(f"{name}.capacity", bound.range, bound.signature, bound.kind, bound.span))
    given = sum(attr.key == "capacity" for attr in component.attrs)
    if given != 1:
        _reporter(problems, component.span, name)(f"a demand has exactly one capacity line, not {given}")
    _check_references(name, design, problems)
    if problems:
        raise ComponentError(tuple(problems))
    return Demand(name, capacities[0], component.span)


Say = Callable[[str], None]


def _reporter(problems: list[str], span: Span, what: str) -> Say:
    return lambda message: problems.append(f"{span.path}:{span.line}:{span.col}: {what}: {message}")


def _check_references(demand: str, design: Design, problems: list[str]) -> None:
    for case in design.loads.values():
        say = _reporter(problems, case.span, f"load {case.name}")
        for entry in case.entries:
            if entry.target[0] != demand:
                continue
            if entry.target != (demand,) or entry.field != "force":
                say(f"{'.'.join(entry.target)} {entry.field}: a demand's load is a force on the demand itself, as in `on {demand} force ...`")
            elif _dim(entry.value, design) != FORCE:
                say(f"{demand}: force needs a force range")
    for claim in design.claims:
        if claim.qoi.path[0] == demand:
            _reporter(problems, claim.span, f"claim {claim.name}")(
                f"a demand takes probability claims only, as in P({demand}.utilisation > 1) <= p under <load>")
    for claim in design.probability_claims:
        say = _reporter(problems, claim.span, f"claim {claim.name}")
        event = claim.event
        if isinstance(event, Exceeds) and event.qoi.path[0] == demand:
            if event.qoi.path != (demand,) or event.qoi.name != "utilisation":
                say(f"a probability claim on a demand bounds {demand}.utilisation")
            elif event.threshold.dim != DIMENSIONLESS:
                say("utilisation is compared with a fraction of the capacity")
        elif isinstance(event, FailsAt) and event.subject[0] == demand:
            tests = design.tests.get(claim.method.tests)
            if event.subject != (demand,):
                say(f"a tested failure is a failure of {demand} itself, as in P(fail {demand} at <level>)")
            elif event.level.dim != FORCE:
                say("the failure level is a force")
            elif tests is not None and tests.subject != (demand,):
                say(f"tests {tests.name} load {'.'.join(tests.subject)}, so they say nothing about {demand}")
    for tests in design.tests.values():
        if tests.subject[0] != demand:
            continue
        say = _reporter(problems, tests.span, f"tests {tests.name}")
        if tests.subject != (demand,):
            say(f"tests load {demand} itself, as in `on {demand} trials ...`")
        elif tests.level.dim != FORCE:
            say("the test level is a force")


def _dim(value: Input | ParamRef, design: Design) -> Dim:
    return value.range.dim if isinstance(value, Input) else design.params[value.name].range.dim


# --- Modes, model premises -----------------------------------------------------------

RANGE_MEAN = FailureMode("uncertain.range_mean")
TESTED = FailureMode("uncertain.tested")

MOMENT_MODEL = model_spec(
    sys.modules[__name__], "uncertain.moment",
    "P(force > u x capacity) bounded over every probability distribution of the force with its signed range "
    "and signed mean, by moment-problem duality; no distribution is assumed",
    "every use the claim covers draws its force from one distribution whose support lies in the signed range and "
    "whose mean is the signed mean; the capacity lies in its signed range, so the bound, which holds at every "
    "capacity in that range, holds however the capacity varies between uses",
    "petra-maintainers", "Markov's inequality; moment-problem duality as in Bertsimas and Popescu (2005), "
    "optimal inequalities in probability theory",
)

SCENARIO_MODEL = model_spec(
    sys.modules[__name__], "uncertain.scenario",
    "one-sided binomial confidence bound: if the failure probability at the claimed level were eps or more, "
    "k or fewer failures in n trials would have probability at most 1 - c",
    "the trials are independent; each loads a part representative of those the claim covers at or above the "
    "claimed level; every failure in the trials is recorded",
    "petra-maintainers", "Clopper and Pearson (1934), confidence limits for the binomial, Biometrika 26",
)

MODELS: Mapping[FailureMode, ModelSpec] = {RANGE_MEAN: MOMENT_MODEL, TESTED: SCENARIO_MODEL}

# --- Elaboration -------------------------------------------------------------------------


def build_range_mean(req: Requirement, demand: Demand, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """Gap needing NeedsInputBound when the load has no signed mean.

    The threshold enters at its lower end, which gives the larger event. The threshold
    and p are the owner's claim, not premises, so both enter as constants."""
    criterion = req.criterion
    case = criterion.load
    force = next((e.value for e in design.loads[case].entries if e.target == (demand.name,)), None)
    if not isinstance(force, Input) or force.mean is None:
        field = "force" if force is None else "force.mean"
        return (Gap(req, (NeedsInputBound((case, demand.name), field, "N"),)),)
    u = criterion.threshold.value.lo
    sb = StatementBuilder(design, registry)
    load, mean, capacity = sb.input(force), sb.mean(force), sb.input(demand.capacity)
    x = f"{demand.name}.force"
    goal = MomentBound(
        random=(RandomVar(x, load, load),),
        moments=(MomentConstraint(Sym(x), mean, mean),),
        fail=Add((Sym(x), Neg(Mul((Const(u), capacity))))),
        p=criterion.p,
    )
    return (Obligation(req, sb.finish(goal), MOMENT_MODEL,
                       f"the force on {demand.name} exceeds {u} times its capacity with probability at most {criterion.p} "
                       f"under {case}, for every distribution with the signed range and mean"),)


def build_tested(req: Requirement, demand: Demand, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    criterion = req.criterion
    record = design.tests[criterion.tests]
    level = criterion.threshold
    tested_at = format_quantity(record.level, "kN")
    if level.value.hi > record.level.value.lo:
        return (Gap(req, (NoRuleForQuantity(
            f"P(fail {demand.name} at {format_quantity(level, 'kN')})",
            f"tests {record.name} loaded {demand.name} at {tested_at}, which says nothing about a higher load"),)),)
    sb = StatementBuilder(design, registry)
    trials, failures = sb.tests(record)
    goal = BinomialTail(trials, failures, Const(criterion.p), Const(1 - criterion.confidence))
    return (Obligation(req, sb.finish(goal), SCENARIO_MODEL,
                       f"{demand.name} fails at {format_quantity(level, 'kN')} with probability at most {criterion.p} "
                       f"at confidence {criterion.confidence}, from {record.failures} failures in {record.trials} "
                       f"trials at {tested_at}"),)


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
