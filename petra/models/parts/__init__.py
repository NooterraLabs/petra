"""Domain: physical parts and the assemblies they make. Trusted. docs/parts.md is the design.

Two component kinds: `part` (a mesh, its material and how it is made) and `assembly`
(parts placed together, with the path each takes in, the screws that hold them, gaps and
press fits). `exact` decides every geometric question on exact rational coordinates;
`engine` measures each assembly once; `build` states each rule as an R4 goal over the
measures and the tolerance premises; `rules.RULES` is the one table of checks, and
coverage, failure modes and builders derive from it.
"""
from .domain import DOMAIN

__all__ = ["DOMAIN"]
