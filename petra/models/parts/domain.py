"""The parts domain, derived from RULES. Trusted.

Every table a DomainSpec holds comes from the one table in rules.py: a failure mode per
rule (its id is the rule's), one builder for all of them, one coverage rule per row, and
the preset rows each process kind must hold. Nothing here names a rule by hand.

The scaffold defines `build_domain` and no module-level DOMAIN. A DOMAIN in this package
must be registered in petra/models/__init__.py (tests/test_domain_registry.py), and
registering a domain whose builders raise would break every check. Registration is the
last step of the build order in docs/parts.md.
"""
from __future__ import annotations

from typing import Any, Mapping

from ...ir import Design
from ...registry import ProcessKind, Registry
from ..base import CoverageRule, DomainSpec, FailureMode, Feature, FeatureKind, Ports
from .rules import RULES, Applies, Rule

PART = FeatureKind("parts.part")           # one per part block; materials: its material; environment: none
PCB = FeatureKind("parts.pcb")             # one per pcb block
PLACED = FeatureKind("parts.placed")       # one per (assembly, body) and one per pair of placed bodies
DECLARED = FeatureKind("parts.declared")   # one per hole, seat, fasten, insert, access, gap, guard and opening line


def mode(rule: Rule) -> FailureMode:
    """The failure mode of one rule; its id is the rule's id."""
    raise NotImplementedError


def coverage_rule(rule: Rule) -> CoverageRule:
    """The coverage rule for one row. A part rule applies to a PART feature whose preset
    has the rule's process kind; a fit rule applies to the feature its `applies` names.
    A costlier rule applies only where its budget row exists in the preset or the
    design. The default criterion is the rule's bound row, read by build.bound."""
    raise NotImplementedError


def features(model: Any, design: Design, registry: Registry) -> tuple[Feature, ...]:
    """The features of one typed model (PartDesign, PcbDesign or Assembly). An assembly's
    features name its placed pairs and declared lines; a part's name the part. Each
    pair of placed bodies of different materials is also a CONTACT_PAIR when the exact
    evaluator finds them touching, so the galvanic rule in petra/coverage.py sees it."""
    raise NotImplementedError


def ports(model: Any, registry: Registry) -> Ports:
    """No ports: parts exchange no port quantities in v0."""
    raise NotImplementedError


def absent(model: Any, design: Design) -> Mapping[FailureMode, str]:
    """Why each parts mode coverage does not demand cannot arise: a part with no process
    owes no fabrication rule; a board placed in no assembly owes no fit rule."""
    raise NotImplementedError


def check_presets(registry: Registry) -> tuple[str, ...]:
    """Every preset of each parts process kind holds exactly the rows rules.rows_read(kind)
    names, each with its unit and its Worse end. Returns the problems; the registry's
    consistency check reports them, so a preset missing a row fails at load, not inside
    a verdict."""
    raise NotImplementedError


def applies_to(applies: Applies) -> FeatureKind:
    """The feature kind a rule's `applies` matches: PART for a process kind, PLACED for a
    pair or keep-out, DECLARED for a line."""
    raise NotImplementedError


def rules_for(process: ProcessKind) -> tuple[Rule, ...]:
    """The rules a part made by `process` owes, in RULES order."""
    return tuple(r for r in RULES if r.applies.process is process)


def build_domain() -> DomainSpec:
    """The DomainSpec: kinds part, pcb and assembly with their lowerers and grammars;
    builders build.build for every rule's mode; unmodelled none; qois none in v0; no
    probability methods; coverage one rule per row; models from build.models() by each
    rule's evaluator; features, ports and absent above."""
    raise NotImplementedError
