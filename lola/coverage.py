"""Coverage: which failure modes a design must address. Trusted policy.

Each domain declares its own coverage rules on its DomainSpec; models.COVERAGE joins
them in registry order. This module adds the cross-domain rules, which read only the
features every domain reports, and turns rules and claims into requirements. Every
generated requirement is discharged by a certificate or a named waiver; otherwise its
entry is UNKNOWN and names what it needs. The table as a whole is one judged premise,
"cov:<sha256 of RULES>", owned by the LoLa maintainers, and appears in every footprint.
A coverage table is a judgement about what can go wrong, so LoLa says so rather than
hiding it.

v0 rules (the domain rules live in their modules):
  truss.axial_member     every truss member      -> plastic collapse (lambda >= 1),
                                                    member buckling, global stability
  truss.elastic_claim    any elastic claim       -> small strain (model validity)
  wire.conductor         every wire              -> steady temperature (theta <= insulation
                                                    theta_max), short circuit, overload
                                                    protection, voltage drop (<= 5 %)
  bolt.tension           every bolted joint      -> bolt tension (proof load)
  bolt.bearing           every bolted joint      -> plate bearing           (unmodelled)
  galvanic.contact       contact pair with anodic index difference > 0.15 V in a wet
                         environment or corrosivity >= C3, or in an undeclared
                         environment (conservative) -> galvanic corrosion  (unmodelled)

There is no design-level gap. A design without an environment class is still checked:
builders that need the environment report NeedsInputBound on their own requirement, and
the galvanic rule treats an undeclared environment as wet.

A domain's rules see only that domain's features; the cross-domain rules see every
feature. A domain rule demands only its own modes, and the subject's domain elaborates
them, so a foreign match could only yield a requirement nobody can build.

Claims are never waived: a claim is what the owner asked LoLa to check. A waiver that
names a claimed (mode, subject) matches nothing, and the pipeline warns about it.
"""
from __future__ import annotations

import hashlib
import inspect
from fractions import Fraction
from functools import cache

from .ir import Claim, Design, Exceeds, FromTests, ProbabilityClaim, Rel
from .kernel import Interval, enclose
from .models import COVERAGE, KINDS  # KINDS: component kind -> owning DomainSpec
from .models.base import (
    CONTACT_PAIR,
    GALVANIC_CORROSION,
    ClaimOrigin,
    CoverageOrigin,
    CoverageRule,
    Criterion,
    DomainSpec,
    FailureMode,
    Feature,
    ProbabilityCriterion,
    Requirement,
)
from .premises import Label, Premise, Tag
from .registry import Corrosivity, Registry, Stated

GALVANIC_LIMIT = Fraction(3, 20)
"""Volts. MIL-STD-889C's anodic-index spread for harsh (wet or corrosive) service."""

_CORROSIVE = frozenset({Corrosivity.C3, Corrosivity.C4, Corrosivity.C5, Corrosivity.CX})


def _anodic_index(material: str, registry: Registry) -> Interval | None:
    """None for a material with no anodic index: polymers and ceramics are not electrodes."""
    prop = registry.material(material).props.get("anodic_index")
    if prop is None:
        return None
    if isinstance(prop, Stated):
        return prop.value
    return enclose(prop.expr, {f"const.{name}": c.value for name, c in registry.constants.items()})


def _galvanic_applies(feature: Feature, registry: Registry) -> bool:
    """CONTACT_PAIR whose registry anodic indices differ by more than 0.15 V, in a wet or
    >= C3 environment, or in an undeclared one."""
    if feature.kind != CONTACT_PAIR or len(set(feature.materials)) < 2:
        return False
    indices = [_anodic_index(m, registry) for m in feature.materials]
    if any(i is None for i in indices):
        return False
    if max(i.hi for i in indices) - min(i.lo for i in indices) <= GALVANIC_LIMIT:
        return False
    if feature.environment is None:
        return True
    environment = registry.environment(feature.environment)
    return environment.wet or environment.corrosivity in _CORROSIVE


def _no_criterion(mode: FailureMode, feature: Feature) -> Criterion | None:
    return None


GALVANIC_CONTACT = CoverageRule(
    id="galvanic.contact",
    when=_galvanic_applies,
    demands=(GALVANIC_CORROSION,),
    default=_no_criterion,
    note="dissimilar metals in contact in a wet or corrosive environment",
)

CROSS_DOMAIN: tuple[CoverageRule, ...] = (GALVANIC_CONTACT,)

RULES: tuple[CoverageRule, ...] = CROSS_DOMAIN + COVERAGE
"""The whole table the coverage premise hashes."""


@cache
def table_premise() -> Premise:
    """The judged premise for RULES, label "cov:<hash>". The hash covers every rule's id,
    demands and note, and the source of every module that decides when a rule applies,
    so editing a predicate or a threshold changes the label."""
    digest = hashlib.sha256()
    modules = []
    for rule in RULES:
        digest.update(f"{rule.id}|{','.join(m.id for m in rule.demands)}|{rule.note}\n".encode("utf-8"))
        for decides in (rule.when, rule.default):
            module = inspect.getmodule(decides)
            if module not in modules:
                modules.append(module)
    for module in modules:
        digest.update(inspect.getsource(module).encode("utf-8"))
    return Premise(
        Label(f"cov:{digest.hexdigest()[:16]}"),
        Tag.JUDGED,
        "lola-maintainers",
        "LoLa coverage table v0: lola/coverage.py and each domain's coverage rules",
        f"every failure mode a v0 design must address is demanded by one of {', '.join(r.id for r in RULES)}",
    )


def _domain(design: Design, subject: tuple[str, ...]) -> DomainSpec:
    return KINDS[design.components[subject[0]].kind]


def _claim_requirement(claim: Claim, design: Design) -> Requirement:
    mode = _domain(design, claim.qoi.path).qois[claim.qoi.name]
    return Requirement(claim.qoi.path, mode, Criterion(claim.rel, claim.bound), ClaimOrigin(claim.name), claim.under, claim.qoi)


def _probability_requirement(claim: ProbabilityClaim, design: Design) -> Requirement:
    event, method = claim.event, claim.method
    if isinstance(event, Exceeds):
        subject, under, qoi, threshold, load = event.qoi.path, (event.under,), event.qoi, event.threshold, event.under
    else:
        subject, under, qoi, threshold, load = event.subject, (), None, None, None
    tests, confidence = (method.tests, method.confidence) if isinstance(method, FromTests) else (None, None)
    mode = _domain(design, subject).probability[type(method)]
    criterion = ProbabilityCriterion(threshold, claim.p, load, tests, confidence)
    return Requirement(subject, mode, criterion, ClaimOrigin(claim.name), under, qoi)


def claim_requirements(design: Design, models: dict[str, object]) -> tuple[Requirement, ...]:
    """One requirement per claim and probability claim, in source order, keyed by the
    component the path starts with (`models` maps component name -> typed model). A
    claim's mode comes from the owning domain's `qois`; a probability claim's mode from
    its `probability` table, keyed by the method's class. The lowerers already rejected
    unknown qois."""
    stated = sorted((*design.claims, *design.probability_claims), key=lambda c: (c.span.line, c.span.col))
    return tuple(
        _claim_requirement(c, design) if isinstance(c, Claim) else _probability_requirement(c, design)
        for c in stated
    )


def _covers_loads(under: tuple[str, ...], component: str, design: Design) -> bool:
    """A requirement with no load cases is checked under every load case on its
    component, so a claim covers it only when the claim does too."""
    acting = {case.name for case in design.loads.values() if any(e.target[0] == component for e in case.entries)}
    return not under or acting <= set(under)


def _settles(claim: Requirement, demanded: Requirement, design: Design) -> bool:
    """True when the claim's requirement implies the coverage requirement: the same
    subject and mode, the same relation and dimension, a bound at least as strict over
    its whole range, and every load case the coverage requirement is checked under."""
    k, c = claim.criterion, demanded.criterion
    if claim.subject != demanded.subject or claim.mode != demanded.mode:
        return False
    if not (isinstance(k, Criterion) and isinstance(c, Criterion)) or k.rel is not c.rel or k.bound.dim != c.bound.dim:
        return False
    if k.rel is Rel.LE:
        stricter = k.bound.value.hi <= c.bound.value.lo
    else:
        stricter = k.bound.value.lo >= c.bound.value.hi
    return stricter and _covers_loads(claim.under, demanded.subject[0], design)


def generate(design: Design, models: dict[str, object], registry: Registry) -> tuple[Requirement, ...]:
    """Claim requirements, then coverage requirements from every component's features
    (the owning DomainSpec's `features` hook) matched against the cross-domain rules and
    the owning domain's rules, in component, feature, rule and demand order, each once.
    A coverage requirement on the same (subject, mode) as a claim is dropped when the
    claim's criterion is at least as strict, and kept otherwise.

    A rule that demands one mode on one subject with two different criteria (its
    default read the features apart) raises ValueError: the two requirements would share
    an id, and a report could not tell them apart."""
    claims = claim_requirements(design, models)
    demanded: dict[str, Requirement] = {}
    for name, model in models.items():
        spec = KINDS[design.components[name].kind]
        for feature in spec.features(model, design, registry):
            for rule in CROSS_DOMAIN + spec.coverage:
                if not rule.when(feature, registry):
                    continue
                for mode in rule.demands:
                    req = Requirement(feature.subject, mode, rule.default(mode, feature), CoverageOrigin(rule.id))
                    if demanded.setdefault(req.id, req) != req:
                        raise ValueError(f"coverage rule {rule.id} demands {mode.id} on {'.'.join(feature.subject)} with two different criteria")
    kept = [r for r in demanded.values() if not any(_settles(c, r, design) for c in claims)]
    return claims + tuple(kept)


def apply_waivers(requirements: tuple[Requirement, ...], design: Design) -> tuple[tuple[Requirement, ...], tuple[tuple[Requirement, Premise], ...]]:
    """Split requirements into (still to discharge, waived). A waiver matches a coverage
    requirement on exact (mode id, subject) and becomes a judged premise
    "waive:<design>.<mode>.<subject>" naming its owner and reason. A waiver that matches
    nothing is reported by the pipeline as a warning, so a stale waiver cannot hide a
    renamed subject."""
    remaining: list[Requirement] = []
    waived: list[tuple[Requirement, Premise]] = []
    for req in requirements:
        waiver = None
        if isinstance(req.origin, CoverageOrigin):
            waiver = next((w for w in design.waivers if w.mode == req.mode.id and w.subject == req.subject), None)
        if waiver is None:
            remaining.append(req)
            continue
        subject = ".".join(waiver.subject)
        premise = Premise(
            Label(f"waive:{design.name}.{waiver.mode}.{subject}"),
            Tag.JUDGED,
            waiver.owner,
            f"waiver at {waiver.span.path}:{waiver.span.line}",
            f"{waiver.mode} on {subject} needs no check: {waiver.reason}",
        )
        waived.append((req, premise))
    return tuple(remaining), tuple(waived)


__all__ = ["CROSS_DOMAIN", "GALVANIC_CONTACT", "RULES", "apply_waivers", "claim_requirements", "generate", "table_premise"]
