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

import sys
from typing import Mapping

from ..ir import Design, QoiRef
from ..kernel import Add, Expr, Neg
from ..kernel.rules.r4_enclosure import AllNonpositive
from ..registry import Registry
from .base import (
    PORT_CONTRACT,
    Connection,
    CoverageOrigin,
    Elaborated,
    Gap,
    NoRuleForQuantity,
    Obligation,
    PortQuantity,
    PortRef,
    PortSpec,
    Requirement,
    Side,
    StatementBuilder,
    model_spec,
)

CONTRACT = model_spec(
    sys.modules[__name__], "port.contract",
    "interval inclusion of a guaranteed port quantity in the assumption of the port it connects to",
    "the connection is the only path for the quantity between the two ports; both sides describe the same "
    "quantity at the same point",
    "lola-maintainers", "assume-guarantee contracts (Benveniste et al., Contracts for System Design, 2018)",
)
"""The premise of a contract whose guarantee and assumption are both ratings. A
guarantee computed by an elaborator rests on that elaborator's model instead."""

ORIGIN = CoverageOrigin("port.contract")


def _path(ref: PortRef) -> str:
    return f"{ref.component}.{ref.element}.{ref.port}"


def _minus(a: Expr, b: Expr) -> Expr:
    return Add((a, Neg(b)))


def contract_obligations(design: Design, connections: tuple[Connection, ...], specs: Mapping[PortRef, PortSpec], registry: Registry) -> tuple[Elaborated, ...]:
    """One obligation per (connection, direction, quantity) with a stated assumption.
    Requirement mode is base.PORT_CONTRACT, origin CoverageOrigin("port.contract"),
    subject (component, element, port)."""
    out: list[Elaborated] = []
    for connection in connections:
        for assumer, guarantor in ((connection.a, connection.b), (connection.b, connection.a)):
            assumed = specs[assumer].assumes if assumer in specs else {}
            given = specs[guarantor].guarantees if guarantor in specs else {}
            for quantity, need in assumed.items():
                if need.lo is None and need.hi is None:
                    continue
                out.append(_contract(design, registry, assumer, guarantor, quantity, need, given.get(quantity)))
    return tuple(out)


def _contract(design: Design, registry: Registry, assumer: PortRef, guarantor: PortRef, quantity: PortQuantity,
              need: Side, given: Side | None) -> Elaborated:
    subject = (assumer.component, assumer.element, assumer.port)
    req = Requirement(subject, PORT_CONTRACT, None, ORIGIN, (), QoiRef(subject, quantity.value))
    missing = [end for end in ("lo", "hi") if getattr(need, end) is not None and (given is None or getattr(given, end) is None)]
    if missing:
        side = " and ".join({"lo": "a lower", "hi": "an upper"}[end] for end in missing)
        return Gap(req, (NoRuleForQuantity(quantity.value, f"nothing guarantees {side} bound on {quantity.value} at {_path(assumer)} from {_path(guarantor)}"),))
    sb = StatementBuilder(design, registry)
    exprs = []
    if need.hi is not None:
        exprs.append(_minus(given.hi(sb), need.hi(sb)))
    if need.lo is not None:
        exprs.append(_minus(need.lo(sb), given.lo(sb)))
    model = given.model or need.model or CONTRACT
    describe = f"the {quantity.value} {_path(guarantor)} guarantees lies within what {_path(assumer)} is rated for"
    return Obligation(req, sb.finish(AllNonpositive(tuple(exprs))), model, describe)
