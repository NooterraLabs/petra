"""Coverage and the DomainSpec of the steel deck. Trusted.

Limit-state completeness is set inclusion: `required(conn, design)` lists every mode the
connection must satisfy: the union of the limit states of the elements on its load path
(path.py). The kind and a few facts decide the path: bolted or welded sides, a cope, the
single-plate form, slip-critical bolts, the load fields the design states. `features`
reports one feature per required mode and the coverage rule for that mode demands it, so
every requirement id names its mode once ("st1/steel.block_shear/coverage.steel.block_shear"). Each mode's builder must then
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
from .absent import reasons
from .build import BUILDERS
from .lower import KIND_SPECS, Bolts, Conn, grammar, lower_conn
from .path import ROLE_LIMITS, path
from .vocab import LOAD_PATH, MODELS, MODES, QOIS, STIFFENED_FORCE, UNMODELLED

def _fields(conn: Conn, design: Design) -> set[str]:
    return {e.field for case in design.loads.values() for e in case.entries if e.target == (conn.name,)}


def required(conn: Conn, design: Design) -> tuple[str, ...]:
    """Every mode the connection must satisfy: the limit states of every element on its
    load path (path.py), in path order, each once."""
    return tuple(dict.fromkeys(mode for link in path(conn, _fields(conn, design)) for mode in ROLE_LIMITS[link.role]))


REQUIRES = "steel.requires."


def features(conn: Conn, design: Design, registry: Registry) -> tuple[Feature, ...]:
    """One feature per required mode (kind "steel.requires.<mode>"), naming the parts'
    materials, and one CONTACT_PAIR per bolt group and the steel it passes through. Steel
    grades and bolt groups are all plain carbon or low-alloy steel with one anodic index, so
    the galvanic rule finds no dissimilar pair among them."""
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


def absent(conn: Conn, design: Design) -> dict[FailureMode, str]:
    """Each mode of the domain the connection does not owe (`required`), and why it cannot
    arise for it (absent.py). A mode with no reason there is left out, so the readout says
    it is not demanded, and tests/test_steel_coverage.py fails."""
    owed = set(required(conn, design))
    why = reasons(conn)
    return {mode: why[short] for short, mode in _ALL.items() if short not in owed and short in why}


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
    grammars={kind: grammar(kind) for kind in KIND_SPECS},
    absent=absent,
)
