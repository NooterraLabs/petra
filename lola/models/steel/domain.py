"""Coverage and the DomainSpec of the steel deck. Trusted.

Limit-state completeness is set inclusion: `required(conn, design)` lists, from the
connection's kind and the few facts that switch limit states on (bolted or welded sides,
a cope, the single-plate form, slip-critical bolts, the load fields the design states),
every mode the connection must satisfy. `features` reports one feature per required mode
and the coverage rule for that mode demands it, so every requirement id names its mode
once ("st1/steel.block_shear/coverage.steel.block_shear"). Each mode's builder must then
produce at least one check, or the requirement is a Gap: the deck never passes a mode it
was required to check and did not.
"""
from __future__ import annotations

from fractions import Fraction

from ...ir import Design, Rel
from ...kernel import Interval
from ...registry import Registry
from ...units import DIMENSIONLESS, Quantity
from ..base import (
    CONTACT_PAIR,
    NO_PORTS,
    CoverageRule,
    Criterion,
    DomainSpec,
    EnergyDomain,
    FailureMode,
    Feature,
    FeatureKind,
    Ports,
)
from .build import BUILDERS
from .lower import KIND_SPECS, Bolts, Conn, lower_conn
from .vocab import LOAD_PATH, MODELS, MODES, QOIS, STIFFENED_FORCE, UNMODELLED

MAKE = ("spacing_min", "edge_min", "spacing_max", "edge_max", "hole_use", "joint_type")
PLY = ("shear_yield", "shear_rupture", "block_shear")
WELDED = ("weld", "weld_base_metal", "fillet_size")
BEAM_BEARING = ("web_local_yielding", "web_crippling")

SHEAR_KINDS = ("shear_tab", "double_angle", "single_angle", "shear_tee", "shear_end_plate", "seated", "stiffened_seat")


def _fields(conn: Conn, design: Design) -> set[str]:
    return {e.field for case in design.loads.values() for e in case.entries if e.target == (conn.name,)}


def required(conn: Conn, design: Design) -> tuple[str, ...]:
    """Every mode the connection must satisfy, in a fixed order, each once."""
    kind, fields = conn.kind, _fields(conn, design)
    bolted_support = conn.get("support_side") == "bolted"
    welded_support = conn.get("support_side") == "welded"
    modes: list[str] = []
    if kind == "shear_tab":
        modes += ["bolts", *PLY, "flexural_yield", "flexural_rupture", *WELDED, *MAKE, "clearance"]
        modes += ["ductility"] if conn.get("form", "conventional") == "conventional" else ["plate_buckling", "extended_ductility"]
    elif kind in ("double_angle", "single_angle"):
        modes += ["bolts", *PLY, *MAKE, "clearance"] + (list(WELDED) if welded_support else [])
    elif kind == "shear_tee":
        modes += ["bolts", *PLY, "flexural_yield", "flexural_rupture", *MAKE, "clearance"] + (list(WELDED) if welded_support else [])
    elif kind == "shear_end_plate":
        modes += ["bolts", *PLY, *WELDED, *MAKE, "clearance"]
    elif kind == "seated":
        modes += ["seat_flexure", "shear_yield", *BEAM_BEARING]
        modes += ["bolts", *MAKE, "clearance"] if bolted_support else list(WELDED)
    elif kind == "stiffened_seat":
        modes += ["bearing", "compression", *WELDED, *BEAM_BEARING]
    elif kind == "flange_force":
        modes += ["web_local_yielding"]
        if conn.attrs["force_kind"] == "tensile":
            modes += ["flange_local_bending"]
        else:
            modes += ["web_crippling"]
            if conn.get("pair", "single") == "double":
                modes += ["web_compression_buckling"]
            elif "flange_restrained" in conn.attrs and "unbraced_length" in conn.attrs:
                modes += ["web_sidesway_buckling"]
        if "panel_shear" in fields:
            modes += ["panel_zone"]
    elif kind == "bolt_bracket":
        modes += ["bolts", *PLY, *MAKE]
    elif kind == "weld_bracket":
        modes += list(WELDED)
    elif kind == "hanger":
        modes += ["bolt_tension", "prying", "tension_yield", "tension_rupture", *MAKE, "clearance"]
        if "shear" in fields:
            modes += ["bolts", "bolt_combined"]
    bolts = conn.get("bolts")
    if isinstance(bolts, Bolts) and bolts.joint == "slip_critical" and "bolts" in modes:
        modes += ["slip"]
    if conn.get("cope") is not None:
        modes += ["cope_buckling"]
    if kind in SHEAR_KINDS and "axial" in fields:
        modes += ["load_path"]
    return tuple(dict.fromkeys(modes))


REQUIRES = "steel.requires."


def features(conn: Conn, design: Design, registry: Registry) -> tuple[Feature, ...]:
    """One feature per required mode (kind "steel.requires.<mode>"), naming the parts'
    materials, and one CONTACT_PAIR per bolt group and the steel it passes through. Steel
    grades and bolt groups state no anodic index, so the galvanic rule finds no dissimilar
    pair among them."""
    materials = tuple(dict.fromkeys(_materials(conn)))
    energy = frozenset({EnergyDomain.MECHANICAL})
    subject = (conn.name,)
    out = [Feature(subject, FeatureKind(f"{REQUIRES}{mode}"), materials, energy, design.environment) for mode in required(conn, design)]
    bolts = conn.get("bolts")
    if isinstance(bolts, Bolts):
        contact = frozenset({EnergyDomain.MECHANICAL, EnergyDomain.CHEMICAL})
        steels = dict.fromkeys(v.grade for v in conn.attrs.values() if isinstance(getattr(v, "grade", None), str))
        out += [Feature(subject, CONTACT_PAIR, (bolts.group, s), contact, design.environment) for s in steels]
    return tuple(out)


def _materials(conn: Conn):
    for value in conn.attrs.values():
        for name in ("grade", "group", "electrode"):
            found = getattr(value, name, None)
            if isinstance(found, str):
                yield found


def _requires(short: str):
    kind = f"{REQUIRES}{short}"
    return lambda feature, registry: feature.kind == kind


_ONE = Quantity(Interval(Fraction(1), Fraction(1)), DIMENSIONLESS)


def _default(mode: FailureMode, feature: Feature) -> Criterion | None:
    """Utilisation <= 1 for every modelled mode; None for an unmodelled one."""
    return None if mode in UNMODELLED else Criterion(Rel.LE, _ONE)


_ALL = {**MODES, "load_path": LOAD_PATH, "j10_stiffeners": STIFFENED_FORCE}

COVERAGE: tuple[CoverageRule, ...] = tuple(
    CoverageRule(id=f"steel.{short}", when=_requires(short), demands=(mode,), default=_default,
                 note=f"every connection whose kind or details carry {short.replace('_', ' ')} checks it")
    for short, mode in _ALL.items()
)


def ports(conn: Conn, registry: Registry) -> Ports:
    """No ports in v1.0: a connection meets the world through its signed loads."""
    return NO_PORTS


DOMAIN = DomainSpec(
    name="steel",
    kinds={kind: lower_conn for kind in KIND_SPECS},
    builders=BUILDERS,
    unmodelled=UNMODELLED,
    qois=QOIS,
    probability={},
    coverage=COVERAGE,
    models=MODELS,
    features=features,
    ports=ports,
)
