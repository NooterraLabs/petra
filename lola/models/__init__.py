"""The domain registry: the one place that lists the physics domains.

`_REGISTERED` names the four v0 domains and the steel-connection deck. Every lookup table the rest of LoLa needs is
derived from it here, so a domain is one module under lola/models ending in
`DOMAIN = DomainSpec(...)` plus one entry below. Domain implementers fill in their own
module and never edit this file.

`_index` refuses a registry that would make a table ambiguous or let a domain reach
another domain's modes, so a bad DomainSpec fails at import, not inside a verdict.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from . import bolt, circuit, steel, truss, uncertainty
from .base import CROSS_DOMAIN_MODES, CROSS_DOMAIN_UNMODELLED, CoverageRule, DomainSpec, FailureMode

_REGISTERED: tuple[DomainSpec, ...] = (truss.DOMAIN, circuit.DOMAIN, bolt.DOMAIN, uncertainty.DOMAIN, steel.DOMAIN)


def _index(registered: tuple[DomainSpec, ...]) -> tuple:
    domains: dict[str, DomainSpec] = {}
    kinds: dict[str, DomainSpec] = {}
    modes: dict[str, FailureMode] = {m.id: m for m in CROSS_DOMAIN_MODES}
    unmodelled: set[FailureMode] = set(CROSS_DOMAIN_UNMODELLED)
    coverage: list[CoverageRule] = []
    for spec in registered:
        if spec.name in domains:
            raise RuntimeError(f"domain {spec.name!r} is registered twice")
        domains[spec.name] = spec
        for kind in spec.kinds:
            if kind in kinds:
                raise RuntimeError(f"component kind {kind!r} is claimed by {kinds[kind].name!r} and {spec.name!r}")
            kinds[kind] = spec
        if set(spec.builders) & spec.unmodelled:
            raise RuntimeError(f"{spec.name}: a mode cannot be both built and unmodelled")
        for mode in spec.modes:
            if mode.id in modes:
                raise RuntimeError(f"failure mode {mode.id!r} is declared twice")
            modes[mode.id] = mode
        reached = set(spec.qois.values()) | set(spec.probability.values()) | set(spec.models)
        reached |= {m for rule in spec.coverage for m in rule.demands}
        if not reached <= spec.modes:
            raise RuntimeError(f"{spec.name} refers to modes it does not declare: {sorted(m.id for m in reached - spec.modes)}")
        unmodelled |= spec.unmodelled
        coverage.extend(spec.coverage)
    return (
        MappingProxyType(domains),
        MappingProxyType(kinds),
        MappingProxyType(modes),
        frozenset(unmodelled),
        tuple(coverage),
    )


DOMAINS, KINDS, MODES, UNMODELLED, COVERAGE = _index(_REGISTERED)
"""DOMAINS: domain name -> spec. KINDS: component kind -> owning spec. MODES: mode id ->
mode, for every domain mode and the cross-domain modes in models.base. UNMODELLED: modes
no builder elaborates. COVERAGE: every domain's coverage rules, in registry order
(lola/coverage.py adds the cross-domain rules)."""


__all__ = ["COVERAGE", "DOMAINS", "KINDS", "MODES", "UNMODELLED", "DomainSpec", "FailureMode"]
