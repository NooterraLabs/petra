"""Domain: physical parts and the assemblies they make. Trusted. docs/parts.md is the design.

Three component kinds: `part` (a mesh with an optional process), `pcb` (a KiCad board) and
`assembly` (parts and boards placed together). Two evaluators answer every geometric
question. `exact` decides any question about one placement (interference, clearance, an
insertion path, a seat, a declared hole, a face's slope) on exact rational coordinates.
`grid` decides any question about every placement (where a cutter, a pull or a ball can
reach) on a three-valued cell grid that counts doubt against the part. `rules.RULES` is
the one table of checks, and coverage, failure modes and preset rows derive from it.

This package is a scaffold. Its bodies raise NotImplementedError, so it declares no
DOMAIN yet: tests/test_domain_registry.py requires every declared DOMAIN to be
registered, and registration waits for the first working lowerer.
"""
