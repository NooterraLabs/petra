"""Domain: pin-jointed 2D trusses. Trusted physics; appears in footprints as the
validated_model premises "model:truss.*@<hash>".

Component kind `truss`. Attribute lines, one per line inside the block:

    material <registry material id>                default for every member
    section <registry section id>                  default for every member
    node <name> at (<x>, <y>) [support pinned|roller_x|roller_y]     lengths, exact
    member <name>: <node> -- <node> [section <id>] [material <id>]

Load fields: fx and fy on `<truss>.<node>`. Claim paths: `<truss>.<qoi>` and
`<truss>.member(<member>).<qoi>`.

Everything is written in force densities q_i = N_i / L_i, because with rational node
coordinates the equilibrium matrix in force densities is exact:

    sum over members at node n of  q_i (x_other - x_n)  +  f_n  =  0     (free DOFs only)

so B has entries x_j - x_i, y_j - y_i, and lengths enter only through L_i^2 (rational)
and Sqrt(L_i^2) inside capacity Exprs, which the kernel encloses rigorously.

Mapping onto kernel goals:
  plastic collapse   R1  LinearFeasible: B q = lambda f(h);  -C_i/L_i <= q_i <= T_i/L_i
                         T_i = A_i fy_i ;  C_i = min(A_i fy_i, pi^2 E_i I_i / L_i^2)
                         mechanism FAIL = FarkasRay (virtual displacement rates).
  elastic response   R3  QuadraticProblem(B, f(h), w_i = L_i^3 / (E_i A_i))
                         (complementary energy sum N^2 L/(EA) = sum q^2 L^3/(EA)).
                         stress = q_i L_i / A_i ; strain = q_i L_i / (E_i A_i).
  global stability   R2  GramPositiveDefinite over free DOFs:
                         sum_i (E_i A_i / L_i^3) d_i d_i^T             (material stiffness)
                       + sum_i (lam * q_i) H_i H_i^T                    (geometric, H = [I; -I])
                         lam is a scope parameter over [0, lambda_req]; q_i are DefinedHyps
                         naming the elastic minimiser components (R3 lemma in the evidence).
  member buckling    R4  AllNonpositive: -(q_i L_i) - pi^2 E_i I_i / L_i^2 <= 0, with q_i a
                         DefinedHyp, one obligation per member so a FAIL names the member.
  small strain       R3  ComponentBound strain_i in [-eps_max, eps_max]: the elastic model's
                         validity range, checked rather than stated.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from typing import Mapping

from ..ir import Component, Design, Span
from ..kernel import Matrix
from ..kernel.rules.r3_hypercircle import QuadraticProblem
from ..registry import Registry
from .base import (
    NO_PORTS,
    CoverageRule,
    Criterion,
    DomainSpec,
    Elaborated,
    FailureMode,
    Feature,
    FeatureKind,
    ModelSpec,
    Ports,
    Requirement,
    StatementBuilder,
)

# --- Typed model, produced by lower_truss ------------------------------------------


class Support(Enum):
    FREE = "free"
    PINNED = "pinned"
    ROLLER_X = "roller_x"   # moves along x, restrained in y
    ROLLER_Y = "roller_y"   # moves along y, restrained in x


@dataclass(frozen=True, slots=True)
class Node:
    name: str
    x: Fraction   # metres, exact
    y: Fraction
    support: Support


@dataclass(frozen=True, slots=True)
class Member:
    name: str
    start: str
    end: str
    section: str    # registry part id, kind SECTION
    material: str   # registry material id


@dataclass(frozen=True, slots=True)
class Truss:
    name: str
    nodes: tuple[Node, ...]
    members: tuple[Member, ...]
    span: Span


def lower_truss(component: Component, design: Design, registry: Registry) -> Truss:
    """Parse the attribute lines in the module docstring. Rejects (ComponentError):
    duplicate names, a member naming an unknown node, a zero-length member, a node with
    no member, coordinates that are not exact lengths, registry ids of the wrong kind, a
    load field other than fx and fy, a load on an unknown node, and a claim qoi not in
    QOIS."""
    raise NotImplementedError


# --- Modes, quantities, model premises -----------------------------------------------

PLASTIC_COLLAPSE = FailureMode("truss.plastic_collapse")
GLOBAL_STABILITY = FailureMode("truss.global_stability")
MEMBER_BUCKLING = FailureMode("truss.member_buckling")
ELASTIC_STRESS = FailureMode("truss.elastic_stress")
COMPLIANCE = FailureMode("truss.compliance")
SMALL_STRAIN = FailureMode("truss.small_strain")

MODELS: Mapping[FailureMode, ModelSpec] = {}
"""TODO: model_spec(...) per mode:
  PLASTIC_COLLAPSE -> "truss.plastic"   rigid-perfectly-plastic, small displacements,
                      compression capacity capped by Euler load (no imperfection
                      knock-down in v0: open question in the design)
  ELASTIC_STRESS, COMPLIANCE, SMALL_STRAIN -> "truss.elastic"
                      linear elastic, small strain (|eps| <= 0.002), pinned joints
  GLOBAL_STABILITY -> "truss.stability"  linear prebuckling, force-density geometric
                      stiffness
  MEMBER_BUCKLING  -> "truss.euler"     pin-ended prismatic Euler column
"""

QOIS: Mapping[str, FailureMode] = {
    "collapse_factor": PLASTIC_COLLAPSE,
    "stability_factor": GLOBAL_STABILITY,
    "stress": ELASTIC_STRESS,
    "compliance": COMPLIANCE,
    "buckling_utilisation": MEMBER_BUCKLING,
}
"""Claimable quantities. `frame.collapse_factor >= 1.5`, `frame.member(m3).stress <= 200 MPa`."""

# --- Elaboration -------------------------------------------------------------------------


@dataclass(frozen=True)
class TrussGeometry:
    """Exact geometry derived once per truss. Pure function of the typed model."""

    dofs: tuple[tuple[str, str], ...]            # (node, "x"|"y") for free DOFs, in order
    B: Matrix                                    # len(dofs) x len(members), force-density form
    diff: tuple[tuple[Fraction, Fraction], ...]  # (x_end - x_start, y_end - y_start) per member
    length_sq: tuple[Fraction, ...]
    material_dir: tuple[Matrix, ...]             # d_i embedded in free DOFs, n x 1
    geometric_dir: tuple[Matrix, ...]            # [I; -I] embedded in free DOFs, n x 2


def geometry(truss: Truss) -> TrussGeometry:
    """TODO: index free DOFs (PINNED fixes x and y, ROLLER_X fixes y, ROLLER_Y fixes x);
    build B column i from member i's difference vector at its two nodes, rows of fixed
    DOFs dropped."""
    raise NotImplementedError


def load_vector(truss: Truss, design: Design, sb: StatementBuilder, under: tuple[str, ...], factor: Fraction) -> tuple:
    """f(h) over free DOFs: each signed load field (fx, fy) on a node becomes an input hyp,
    scaled by `factor`. A load case with no signed range for a field it names is a gap
    needing NeedsInputBound, returned as None by the caller's check."""
    raise NotImplementedError


def elastic_problem(truss: Truss, design: Design, sb: StatementBuilder, under: tuple[str, ...]) -> QuadraticProblem:
    """The one QuadraticProblem for this truss and load set. R3 goals and every DefinedHyp
    use this exact term, so their definitions are equal by hash."""
    raise NotImplementedError


def build_plastic_collapse(req: Requirement, truss: Truss, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    raise NotImplementedError


def build_elastic(req: Requirement, truss: Truss, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """Stress, compliance and small-strain requirements all become MinimizerBound goals
    on elastic_problem; the small-strain bound is attached to every elastic obligation."""
    raise NotImplementedError


def build_global_stability(req: Requirement, truss: Truss, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """A statically indeterminate truss whose lemma ranges lose too much correlation is
    still stated; a solver that cannot prove it leaves NeedsCertificate."""
    raise NotImplementedError


def build_member_buckling(req: Requirement, truss: Truss, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    raise NotImplementedError


# --- Coverage ------------------------------------------------------------------------

AXIAL_MEMBER = FeatureKind("truss.axial_member")
ELASTIC_CLAIM = FeatureKind("truss.elastic_claim")


def features(truss: Truss, design: Design, registry: Registry) -> tuple[Feature, ...]:
    """One AXIAL_MEMBER feature per member (its material, energy {MECHANICAL}), one
    ELASTIC_CLAIM feature per elastic claim on the truss, plus the environment. Trusses
    report no contact pairs in v0."""
    raise NotImplementedError


def _is_axial_member(feature: Feature, registry: Registry) -> bool:
    raise NotImplementedError


def _is_elastic_claim(feature: Feature, registry: Registry) -> bool:
    raise NotImplementedError


def _default_criterion(mode: FailureMode, feature: Feature) -> Criterion | None:
    """Collapse and stability factor >= 1, buckling utilisation <= 1, strain within the
    elastic model's validity range."""
    raise NotImplementedError


COVERAGE: tuple[CoverageRule, ...] = (
    CoverageRule(
        id="truss.axial_member",
        when=_is_axial_member,
        demands=(PLASTIC_COLLAPSE, MEMBER_BUCKLING, GLOBAL_STABILITY),
        default=_default_criterion,
        note="every axial member can yield, buckle, or destabilise the frame",
    ),
    CoverageRule(
        id="truss.elastic_claim",
        when=_is_elastic_claim,
        demands=(SMALL_STRAIN,),
        default=_default_criterion,
        note="an elastic result holds only inside the small-strain range",
    ),
)


def ports(truss: Truss, registry: Registry) -> Ports:
    """No ports in v0. Trusses connect to the world through supports and signed loads."""
    return NO_PORTS


DOMAIN = DomainSpec(
    name="truss",
    kinds={"truss": lower_truss},
    builders={
        PLASTIC_COLLAPSE: build_plastic_collapse,
        ELASTIC_STRESS: build_elastic,
        COMPLIANCE: build_elastic,
        SMALL_STRAIN: build_elastic,
        GLOBAL_STABILITY: build_global_stability,
        MEMBER_BUCKLING: build_member_buckling,
    },
    unmodelled=frozenset(),
    qois=QOIS,
    probability={},
    coverage=COVERAGE,
    models=MODELS,
    features=features,
    ports=ports,
)
