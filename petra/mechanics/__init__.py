"""Mechanics as exact kernel expressions, independent of any design code.

This is the general layer under every code Petra checks. A design code (AISC 360, EN 1993,
VDI 2230) decides which mechanical quantity governs a limit state. It then factors or caps
that quantity with the numbers it prints, each a registry row. The mechanics underneath
is the same in every code: the properties of a section, how an eccentric force is shared
among a group of bolts or along a weld, and when a plate buckles. It is written once,
here. A code is a thin layer on top; petra/models/steel/limits.py is AISC's.

tests/test_mechanics.py holds this boundary:
- Nothing here imports a domain (petra.models), the registry or units, so no module here
  can read a code's number or depend on a unit system.
- No function takes a registry lookup.
- Every numeric literal is an integer from geometry or statics: the 4 of pi d^2 / 4, the
  twelfths of a moment of inertia, the 12 of a plate's flexural rigidity. A decimal is a
  fitted or printed number, and belongs to a code.
- No function has a default argument.
- Each formula is checked against the physics it states, by brute force: integration
  over the section, a sum over the bolts, a weld cut into short segments, a plate solved
  by finite differences. None is checked against a code's worked example.
"""
from __future__ import annotations

import os

from .algebra import add, c, div, mul, power, sq, sub
from .bolt_groups import corner_radius, elastic_block_force, elastic_bolt_force, polar_moment
from .sections import (circle_area, hex_corner, rectangle_elastic_modulus, rectangle_elastic_thickness,
                       rectangle_net_plastic_modulus, rectangle_plastic_modulus, right_triangle, tee_moduli)
from .stability import plate_buckling_stress
from .weld_groups import elastic_weld_c, elastic_weld_line, fillet_throat

MODULES = ("algebra", "sections", "bolt_groups", "weld_groups", "stability")
"""The layer's modules, in the order a model premise's source hash reads them."""

SOURCES = tuple(os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py") for name in MODULES)
"""Their paths, which a domain that builds on the layer adds to its premise's source hash
(petra/models/steel/vocab.py), so that a change to the mechanics changes that domain's
premise labels."""

__all__ = [
    "MODULES", "SOURCES",
    "add", "c", "div", "mul", "power", "sq", "sub",
    "circle_area", "hex_corner", "rectangle_elastic_modulus", "rectangle_elastic_thickness",
    "rectangle_net_plastic_modulus", "rectangle_plastic_modulus", "right_triangle", "tee_moduli",
    "corner_radius", "elastic_block_force", "elastic_bolt_force", "polar_moment",
    "elastic_weld_c", "elastic_weld_line", "fillet_throat",
    "plate_buckling_stress",
]
