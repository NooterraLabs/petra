"""Port contracts: assume-guarantee checks on connections, compiled to R4 statements.
Trusted. Cross-domain: it reads only the Ports every domain's `ports` hook returns.

A port side is a pair of optional bound builders. For a connection a <-> b and a port
quantity q, every guarantee of one end must sit inside the matching assumption of the
other end:

    AllNonpositive([ g_hi - a_hi,  a_lo - g_lo ])      (only the sides both ends state)

The guarantee may be a model Expr (a wire's steady temperature) or a rating hyp; the
assumption is usually a rating hyp. An assumption with no guarantee from the other end
is a Gap needing NoRuleForQuantity ("nothing guarantees temperature at
lighting.t1.wire"), so an unconnected or unmodelled port cannot pass silently. The
inclusion itself is ordinary R4 evidence, which makes a contract FAIL a PointWitness at
the worst-case input.
"""
from __future__ import annotations

from typing import Mapping

from ..ir import Design
from ..registry import Registry
from .base import Connection, Elaborated, PortRef, PortSpec


def contract_obligations(design: Design, connections: tuple[Connection, ...], specs: Mapping[PortRef, PortSpec], registry: Registry) -> tuple[Elaborated, ...]:
    """One obligation per (connection, direction, quantity) with a stated assumption.
    Requirement mode is base.PORT_CONTRACT, origin CoverageOrigin("port.contract"),
    subject (component, element, port)."""
    raise NotImplementedError
