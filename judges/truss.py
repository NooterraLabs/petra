"""Truss self-weight: does a collapse-factor claim survive the weight of the members?

Petra's truss model loads only the nodes. The judge re-solves the plastic collapse factor
as its own linear program (scipy, floats: this is a judge, not the trusted path), once
with the design's loads and once with each member's weight added, half at each end node,
and flags a claim that holds without the weight and fails with it.

    maximise lambda  subject to  sum_j N_j u_jn + lambda P_n + G_n = 0  at every free DOF,
                                 -Nb_j <= N_j <= A_j fy_j,  lambda >= 0

u_jn is member j's unit vector from node n toward its other end, P the design's loads and
G the members' weight. The weight is taken at its characteristic value, unfactored, while
lambda multiplies only the design's loads. The least lambda over a load box lies at a
vertex, since the set of loads the truss carries is convex and contains G, so the judge
takes every vertex of every case the claim names.

Every value the judge picks is the one most favourable to the design, so a flag holds
under any reasonable reading: E = 210 GPa (EN 1993-1-1 3.2.6), fy the grade's nominal for
t <= 16 mm (EN 10025-2: S355 -> 355 MPa), buckling curve a (alpha = 0.21, EN 1993-1-1
Table 6.1, the most favourable curve a tube can take), gamma_M1 = 1, and steel weighing
77.0 kN/m3 (EN 1991-1-1 Table A.4, the low end). Sections are read from their ids, CHS
D x t in mm.
"""
from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

from petra.ir import Component, Design, Fixed, Input, ParamRef, Punct, Ref, Rel, Vec

E = 210e9
ALPHA = 0.21
UNIT_WEIGHT = 77.0e3
MAX_ENTRIES = 12
"""Load entries per case past which the 2^k vertices are not enumerated."""


@dataclass(frozen=True)
class Member:
    a: str
    b: str
    area: float
    inertia: float
    fy: float


@dataclass(frozen=True)
class Frame:
    nodes: dict[str, tuple[float, float]]
    fixed: dict[str, tuple[bool, bool]]    # node -> (x restrained, y restrained)
    members: dict[str, Member]


class Unread(Exception):
    """A line the judge cannot read as the truss grammar gives it."""


def _chs(section: str) -> tuple[float, float]:
    """"chs.60_3x3_2" -> (A, I) in m2 and m4 for D 60.3 mm, t 3.2 mm."""
    match = re.fullmatch(r"chs\.([0-9_]+)x([0-9_]+)", section)
    if match is None:
        raise Unread(f"{section} is not a CHS id the judge reads")
    d, t = (float(g.replace("_", ".")) / 1000 for g in match.groups())
    inner = d - 2 * t
    return math.pi / 4 * (d**2 - inner**2), math.pi / 64 * (d**4 - inner**4)


def _fy(material: str) -> float:
    match = re.fullmatch(r"steel\.S([0-9]+)", material)
    if match is None:
        raise Unread(f"{material} is not an EN 10025 S grade the judge reads")
    return float(match.group(1)) * 1e6


def _id(arg: object) -> str:
    if not isinstance(arg, Ref):
        raise Unread(f"{arg} is not an id")
    return ".".join(arg.parts)


def read(component: Component) -> Frame:
    lines = [(a.key, a.args) for a in component.attrs]
    default = {key: _id(args[0]) for key, args in lines if key in ("material", "section")}
    nodes, fixed, members = {}, {}, {}
    for key, args in lines:
        if key == "node":
            name, at = _id(args[0]), args[2]
            if not isinstance(at, Vec):
                raise Unread(f"node {name} has no coordinates")
            nodes[name] = tuple(float(q.value.lo) for q in at.items)
            support = _id(args[4]) if len(args) >= 5 else None
            fixed[name] = {None: (False, False), "pinned": (True, True), "roller_x": (False, True),
                           "roller_y": (True, False)}[support]
        elif key == "member":
            name = _id(args[0])
            ends = [_id(a) for a in args[1:5] if not isinstance(a, Punct)]
            options = {_id(a): _id(b) for a, b in zip(args[5::2], args[6::2])}
            area, inertia = _chs(options.get("section", default.get("section", "")))
            members[name] = Member(ends[0], ends[1], area, inertia, _fy(options.get("material", default.get("material", ""))))
    return Frame(nodes, fixed, members)


def _length(frame: Frame, m: Member) -> float:
    (xa, ya), (xb, yb) = frame.nodes[m.a], frame.nodes[m.b]
    return math.hypot(xb - xa, yb - ya)


def _buckling(m: Member, length: float) -> float:
    """N_b = chi A fy, EN 1993-1-1 6.3.1.2 with gamma_M1 = 1."""
    squash = m.area * m.fy
    slenderness = math.sqrt(squash / (math.pi**2 * E * m.inertia / length**2))
    phi = 0.5 * (1 + ALPHA * (slenderness - 0.2) + slenderness**2)
    return min(1.0, 1 / (phi + math.sqrt(phi**2 - slenderness**2))) * squash


def collapse_factor(frame: Frame, loads: dict[tuple[str, str], float], weight: bool) -> float:
    dofs = [(n, axis) for n in frame.nodes for axis, held in zip("xy", frame.fixed[n]) if not held]
    row = {dof: i for i, dof in enumerate(dofs)}
    names = list(frame.members)
    a_eq = np.zeros((len(dofs), len(names) + 1))
    b_eq = np.zeros(len(dofs))
    bounds = []
    for j, name in enumerate(names):
        m = frame.members[name]
        length = _length(frame, m)
        for here, there in ((m.a, m.b), (m.b, m.a)):
            (x0, y0), (x1, y1) = frame.nodes[here], frame.nodes[there]
            for axis, delta in (("x", x1 - x0), ("y", y1 - y0)):
                if (here, axis) in row:
                    a_eq[row[(here, axis)], j] += delta / length
            if weight and (here, "y") in row:
                b_eq[row[(here, "y")]] += UNIT_WEIGHT * m.area * length / 2
        bounds.append((-_buckling(m, length), m.area * m.fy))
    for (node, axis), value in loads.items():
        if (node, axis) in row:
            a_eq[row[(node, axis)], -1] += value
    bounds.append((0, None))
    cost = np.zeros(len(names) + 1)
    cost[-1] = -1
    result = linprog(cost, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if result.status == 3:
        return math.inf
    if result.status != 0:
        return 0.0
    return float(-result.fun)


def _range(value: object, design: Design) -> tuple[float, float]:
    if isinstance(value, Input):
        v = value.range.value
    elif isinstance(value, ParamRef) and value.name in design.params:
        v = design.params[value.name].range.value
    elif isinstance(value, Fixed):
        v = value.quantity.value
    else:
        raise Unread(f"load value {value} is not a range")
    return float(v.lo), float(v.hi)


@dataclass(frozen=True)
class SelfWeight:
    subject: str
    bound: float
    without: float
    with_weight: float

    def check(self) -> tuple[str, str] | None:
        if self.without >= self.bound and self.with_weight < self.bound - 1e-9:
            carried = "" if self.with_weight > 0 else ": the truss cannot carry its own weight"
            return "truss.self_weight", (f"collapse factor {self.with_weight:.4g} with the members' weight, below the claimed "
                    f"{self.bound:g} (without it {self.without:.4g}){carried}")
        return None


def facts(component: Component, design: Design) -> tuple[list[SelfWeight], list[str]]:
    try:
        frame = read(component)
    except Unread as e:
        return [], [f"{component.name}: {e}"]
    out, undecided = [], []
    for claim in design.claims:
        if claim.qoi.path != (component.name,) or claim.qoi.name != "collapse_factor" or claim.rel is not Rel.GE:
            continue
        bound = float(claim.bound.value.lo)
        cases = claim.under or tuple(design.loads)
        for case in cases:
            entries = [(e.target[1], e.field[-1], _range(e.value, design)) for e in design.loads[case].entries
                       if e.target[0] == component.name and len(e.target) == 2 and e.field in ("fx", "fy")]
            subject = f"{component.name} claim {claim.name} under {case}"
            if not entries or len(entries) > MAX_ENTRIES:
                undecided.append(f"{subject}: {len(entries)} load entries, outside what the judge enumerates")
                continue
            worst = [math.inf, math.inf]
            for corner in itertools.product(*((lo, hi) for _, _, (lo, hi) in entries)):
                loads: dict[tuple[str, str], float] = {}
                for (node, axis, _), value in zip(entries, corner):
                    loads[(node, axis)] = loads.get((node, axis), 0.0) + value
                for i, weight in enumerate((False, True)):
                    worst[i] = min(worst[i], collapse_factor(frame, loads, weight))
            if worst[0] < bound:
                undecided.append(f"{subject}: the judge's own collapse factor without self-weight, {worst[0]:.4g}, is "
                                 f"already below {bound:g}, so it cannot isolate the weight")
                continue
            out.append(SelfWeight(subject, bound, worst[0], worst[1]))
    return out, undecided
