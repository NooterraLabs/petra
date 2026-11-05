"""Generate the makeable set from physics plus constants.py. Trusted.

Each generator maps a short series from the constants list to registry entries whose
derivable properties are Derived expressions. Adding a size means adding one number to
a series in constants.py, never a row of computed values.

Examples of derivations:
  cable R20'            = const.cu.rho20 / A                          (A = nominal area)
  cable k (adiabatic)   = sqrt(const.cu.qc * (const.cu.beta + 20) / const.cu.rho20
                               * ln((const.cu.beta + theta_f) / (const.cu.beta + theta_i)))
  bolt As               = (pi/4) * ((d2 + d3) / 2)^2,  d2, d3 from ISO 724 coefficients
  bolt proof load Fp    = Sp(class) * As
  CHS area A            = (pi/4) * (D^2 - (D - 2t)^2)
  CHS second moment I   = (pi/64) * (D^4 - (D - 2t)^4)
  steel G               = E / (2 (1 + nu))
"""
from __future__ import annotations

from typing import Mapping

from .model import Environment, Material, Part, Process, Registry


def build_registry() -> Registry:
    """The default makeable set. Pure; same output every call."""
    raise NotImplementedError


def structural_steels() -> Mapping[str, Material]:
    raise NotImplementedError


def aluminium_alloys() -> Mapping[str, Material]:
    raise NotImplementedError


def conductors_and_insulation() -> Mapping[str, Material]:
    raise NotImplementedError


def chs_sections() -> Mapping[str, Part]:
    raise NotImplementedError


def cables() -> Mapping[str, Part]:
    """A series entry per insulation ("cable.cu_pvc") whose props are Derived over two
    series parameters, Sym("self.area") and Sym("self.insulation"), plus one size entry
    per IEC 60228 size ("cable.cu_pvc_2_5") that fixes both. Props: R20, alpha,
    theta_max, theta_sc, k, conductor_diameter, outer_diameter.

    The StatementBuilder expands a size entry through the series derivation with area
    and insulation as point hyps, so a concrete wire and the series family produce the
    same statement shape and the library can match them."""
    raise NotImplementedError


def breakers() -> Mapping[str, Part]:
    """IEC 60898-1 MCBs. Props: In (stated), I_nt = 1.13 In and I_t = 1.45 In (derived
    from the IEC 60898-1 constants), let-through I2t at rated breaking capacity (stated,
    energy-limiting class 3 maximum)."""
    raise NotImplementedError


def terminals() -> Mapping[str, Part]:
    """Props: temperature_max (stated rating, e.g. 75 degC to UL 486A-B / IEC 60998),
    current_max, conductor size range."""
    raise NotImplementedError


def metric_bolts() -> Mapping[str, Part]:
    raise NotImplementedError


def processes() -> Mapping[str, Process]:
    """Install methods (external thermal resistance per metre), coatings, welds."""
    raise NotImplementedError


def environments() -> Mapping[str, Environment]:
    """indoor_dry (C1), outdoor_c3 (C3), marine_c5 (C5, wet)."""
    raise NotImplementedError
