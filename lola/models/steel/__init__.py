"""Domain: steel connections checked against AISC 360-22 Chapter J. Trusted physics in
lower, limits, checks, build, vocab and domain; their source is the model premise's hash.

The catalogue (component kinds), the attribute grammar and the load fields are in
lower.py; the failure modes, model premises and validity rows in vocab.py; the clause
formulas in limits.py; what each limit state checks on each kind in checks.py; coverage
in domain.py. docs/steel_connections.md is the specification.
"""
from .domain import DOMAIN

__all__ = ["DOMAIN"]
