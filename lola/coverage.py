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
"""
from __future__ import annotations

from .ir import Design
from .models import COVERAGE, KINDS  # KINDS: component kind -> owning DomainSpec
from .models.base import GALVANIC_CORROSION, CoverageRule, Criterion, FailureMode, Feature, Requirement
from .premises import Premise
from .registry import Registry


def _galvanic_applies(feature: Feature, registry: Registry) -> bool:
    """CONTACT_PAIR whose registry anodic indices differ by more than 0.15 V, in a wet or
    >= C3 environment, or in an undeclared one."""
    raise NotImplementedError


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


def table_premise() -> Premise:
    """The judged premise for RULES, label "cov:<hash>"."""
    raise NotImplementedError


def claim_requirements(design: Design, models: dict[str, object]) -> tuple[Requirement, ...]:
    """One requirement per claim and probability claim, keyed by the component the path
    starts with (`models` maps component name -> typed model). A claim's mode comes from
    the owning domain's `qois`; a probability claim's mode from its `probability` table,
    keyed by the method's class. The lowerers already rejected unknown qois."""
    raise NotImplementedError


def generate(design: Design, models: dict[str, object], registry: Registry) -> tuple[Requirement, ...]:
    """Claim requirements, then coverage requirements from every component's features
    (the owning DomainSpec's `features` hook) matched against RULES. A coverage
    requirement on the same (subject, mode) as a claim is dropped when the claim's
    criterion is at least as strict, and kept otherwise."""
    raise NotImplementedError


def apply_waivers(requirements: tuple[Requirement, ...], design: Design) -> tuple[tuple[Requirement, ...], tuple[tuple[Requirement, Premise], ...]]:
    """Split requirements into (still to discharge, waived). A waiver matches on exact
    (mode id, subject) and becomes a judged premise "waive:<design>.<mode>.<subject>"
    naming its owner and reason. A waiver that matches nothing is reported by the pipeline
    as a warning, so a stale waiver cannot hide a renamed subject."""
    raise NotImplementedError


__all__ = ["CROSS_DOMAIN", "GALVANIC_CONTACT", "RULES", "apply_waivers", "claim_requirements", "generate", "table_premise"]
