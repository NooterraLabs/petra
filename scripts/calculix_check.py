"""P2's CalculiX spot check (docs/plan.md, P2; docs/calculix_check.md): does a finite element
model of a passing steel design's governing element carry the design strength Petra
certified for it? Untrusted tooling: nothing here changes a verdict.

    python scripts/calculix_check.py check FILE.petra [--size 0.25]
        Model the element of the design whose in-scope limit state governs, run CalculiX
        twice (yield and rupture) and print the comparison.
    python scripts/calculix_check.py sample [--log docs/in_the_loop_log.jsonl]
                                            [--out docs/calculix_check_log.jsonl]
        The same for each loop optimum the plane model covers, first at --screen 0.5 in,
        then again at --size 0.25 in for a close call. Resumable: a task already in --out
        is skipped.
    python scripts/calculix_check.py validate
        Three plain plates against their hand solutions: pure shear, four-point bending
        and a cantilever.
    python scripts/calculix_check.py converge TASK [TASK ...]
        One optimum's two runs at three mesh sizes.
    python scripts/calculix_check.py report [--out docs/calculix_check_log.jsonl]
        The tables docs/calculix_check.md quotes, from the sample's log.

CalculiX runs where `ccx` is on PATH, else over ssh on --host (default $PETRA_CCX_HOST,
then ubuntu@oracle-vm), in batches, --workers jobs at a time.

The model. The element is a flat plate in its own plane: a shear tab, one angle leg, a
tee stem, half a tee flange or end plate, or a bracket plate. It is meshed as one layer
of 20-node bricks (C3D20R), t thick, with uz = 0 on one face, which is in-plane plane
stress. Holes are dh across, bolts are rigid. Small displacements, displacement control.

    yield run     elastic-perfectly-plastic at Fy; each bolt bonded to its whole hole in the
                  direction it pushes, so no net section can form a mechanism. Capacity: the
                  largest load of the run, which ends on the plateau. Judges J4.2(a) gross
                  shear yielding and J4.5 flexural yielding.
    rupture run   Fy to a plastic strain of 0.01, linear to Fu at 0.15, flat after; each bolt
                  bears on the 120 degrees of its hole facing the way it pushes. Capacity:
                  the largest load before any hole stretches 0.25 in, the deformation J3.11a's
                  bearing strength is based on. Judges J4.2(b) shear rupture, J4.3 block
                  shear, J3.11a bearing and tearout of the element's holes, J4.5 flexural
                  rupture, and J2.4(a) base metal rupture of the element along its weld.

Fy and Fu are the specified minima Petra reads. A design is flagged when copies x the FE
capacity is below Petra's design strength (phi Rn, or Rn / Omega) of the governing limit
state the run judges, with every strength expressed as the connection load at which the
check reaches 1. The ratio reported is the FE capacity over that state's nominal Rn. A
yield-run flag points to the model when the FE capacity reaches (1 - BAND) R_int, the
circle through the von Mises shear strength and the flexural strength; any other flag
points to the deck.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from fractions import Fraction
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from petra import build_registry  # noqa: E402
from petra.kernel import Interval, enclose  # noqa: E402
from petra.kernel.rules.r4_enclosure import AllNonpositive  # noqa: E402
from petra.lang import parse_design  # noqa: E402
from petra.mechanics import c, div, sub  # noqa: E402
from petra.models.steel import calc  # noqa: E402
from petra.models.steel.checks import GEOMETRY, Ctx, bolt_dims  # noqa: E402
from petra.models.steel.domain import required  # noqa: E402
from petra.registry.steel import INCH, KSI  # noqa: E402

E_KSI = 29000.0
NU = 0.3
STRAIN_HARDENING = 0.01     # plastic strain where the rupture run's plateau at Fy ends
STRAIN_ULTIMATE = 0.15      # plastic strain where it reaches Fu
ELONGATION = 0.25           # in: the hole elongation J3.11a's bearing strength is based on
ARC = 60.0                  # degrees either side of the push: where a bolt bears on its hole
SIZE = 0.25                 # in: the element edge of a judged run (docs/calculix_check.md)
SCREEN = 0.5                # in: the sample's first pass; a close call is run again at SIZE
NEAR = 0.05                 # a close call: an FE capacity this near a line that decides a verdict
VON_MISES = 1 / (0.6 * math.sqrt(3))   # Fy / sqrt(3), von Mises yield in shear, over AISC's 0.6 Fy
BAND = 0.03                 # the model's own shortfall in pure shear, from the validation
HOST = os.environ.get("PETRA_CCX_HOST", "ubuntu@oracle-vm")
LOG = ROOT / "docs" / "in_the_loop_log.jsonl"
OUT = ROOT / "docs" / "calculix_check_log.jsonl"

JUDGED = {
    # Petra mode -> (the run that judges it, its resistance factor's registry group, suffix)
    "shear_yield": ("yield", "aisc360.j4_2", "_y"),
    "flexural_yield": ("yield", "aisc360.j4_5", "_y"),
    "shear_rupture": ("rupture", "aisc360.j4_2", "_r"),
    "block_shear": ("rupture", "aisc360.j4_3", ""),
    "flexural_rupture": ("rupture", "aisc360.j4_5", "_r"),
    "weld_base_metal": ("rupture", "aisc360.j4_2", "_r"),
    "bolts": ("rupture", "rcsc2025.s5_3", ""),
}
RUNS = ("yield", "rupture")
# Every other mode is out of the model's scope; docs/calculix_check.md says why for each.


# --- What Petra certified -------------------------------------------------------------------------

@dataclass(frozen=True)
class State:
    """One limit state of one element, as Petra checked it. `design` is phi Rn (LRFD) or
    Rn / Omega (ASD) and `nominal` is Rn, both as the connection load, in kip, at which the
    check reaches utilisation 1. Every steel demand is linear in the load, so that load is
    the design's load over the check's utilisation. For a bolt group, `summed` is the Rn of
    the element's bearing and tearout summed over its bolts, as a concentric group's is."""

    mode: str
    what: str
    run: str
    utilisation: float
    design: float
    nominal: float
    summed: float | None = None


@dataclass(frozen=True)
class Element:
    """A connection element as a flat plate in its own plane, in inches, kips and ksi.

    The plate is the rectangle [x0, x1] x [y0, y1], with holes of diameter dh at
    holes[i], each with the unit vector bears[i] from its centre to where its bolt bears.
    `support` and `load` say where it is held and where it is pushed:
      ("edge", "bolts")  held along x = x0, the bolts push it down (vertical shear plies)
      ("bolts", "edge")  held by its bolts, the edge x = x1 pushed down (a bolted bracket)
      ("edge", "edge")   held along x = x0, the edge x = x1 pushed down (a welded bracket)
    `clamp`: the loaded edge is also held in x (a plain plate in pure shear).
    `copies`: elements like it that share the connection's load (two angles, two halves)."""

    task: str
    kind: str
    name: str
    grade: str
    fy: float
    fu: float
    t: float
    x0: float
    x1: float
    y0: float
    y1: float
    dh: float
    holes: tuple[tuple[float, float], ...]
    bears: tuple[tuple[float, float], ...]
    support: str
    load: str
    copies: int
    basis: str
    demand: float
    states: tuple[State, ...] = ()
    clamp: bool = False

    @property
    def utilisation(self) -> float:
        return max((s.utilisation for s in self.states), default=0.0)


def _registry():
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = build_registry()
    return _REGISTRY


_REGISTRY = None


def _numbers(ctx: Ctx, exprs: dict[str, object]) -> dict[str, Fraction]:
    """Each Expr's value, with every hypothesis at the top of its range (a load at its
    largest; the design's dimensions are points)."""
    statement = ctx.sb.finish(AllNonpositive(tuple(exprs.values())))
    box = {h.sym: Interval(h.hi, h.hi) for h in statement.hyps}
    return {k: enclose(e, box).hi for k, e in exprs.items()}


def _inch(x: Fraction) -> float:
    return float(x / INCH)


def _ksi(x: Fraction) -> float:
    return float(x / KSI)


def _bolt_line(kind: str, ply: str) -> Callable[[Ctx], object] | None:
    """The distance from the line an element is held along to its first bolt column:
    the weld line, an angle's heel, a tee's flange face, or the face of the web or stem
    that half an end plate or tee flange is welded to. None: not a modelled element."""
    def attr(key):
        return lambda ctx: ctx.attr(key)

    def half_gauge_less(member_key: str):
        def get(ctx):
            member = ctx.conn.attrs[member_key]
            shape = member.parent if member_key == "tee" else member.shape
            return sub(div(ctx.attr("support_gauge"), c(2)), div(ctx.shape(shape, "tw"), c(2)))
        return get

    return {
        ("shear_tab", "plate"): attr("bolt_line"),
        ("double_angle", "angles"): attr("beam_gauge"),
        ("single_angle", "angle"): attr("beam_gauge"),
        ("double_angle", "angles outstanding"): half_gauge_less("beam"),
        ("single_angle", "angle outstanding"): attr("support_gauge"),
        ("shear_tee", "tee stem"): attr("bolt_line"),
        ("shear_tee", "tee flange"): half_gauge_less("tee"),
        ("shear_end_plate", "end plate"): half_gauge_less("beam"),
    }.get((kind, ply))


def _geometries(task: str, conn, design, registry) -> list[Element]:
    """Every element of the connection the plane model covers, without its states."""
    case = next(iter(design.loads))
    ctx = Ctx(conn, design, registry, case)
    geo = GEOMETRY[conn.kind](ctx)
    v = ctx.load("shear")
    if v is None:
        return []
    common = dict(task=task, kind=conn.kind, basis=conn.basis)
    out = []
    if conn.kind in ("shear_tab", "double_angle", "single_angle", "shear_tee", "shear_end_plate"):
        plies = [(itf, ply, _bolt_line(conn.kind, ply.name)) for itf in geo.interfaces for ply in itf.plies]
        plies = [(itf, ply, line) for itf, ply, line in plies if line is not None]
        exprs: dict[str, object] = {"v": v}
        for k, (itf, ply, line) in enumerate(plies):
            _, along, across = bolt_dims(ctx, itf.bolts, ply.hole, itf.oriented)
            exprs.update({f"{k}.t": ply.t, f"{k}.lev": ply.edge, f"{k}.side": ply.side, f"{k}.s": itf.pitch,
                          f"{k}.xb": line(ctx), f"{k}.g": itf.gauge if itf.gauge is not None else c(0),
                          f"{k}.along": along, f"{k}.across": across,
                          f"{k}.fy": ctx.mat(ply.grade, "fy"), f"{k}.fu": ctx.mat(ply.grade, "fu")})
        n = _numbers(ctx, exprs)
        for k, (itf, ply, _) in enumerate(plies):
            if n[f"{k}.along"] != n[f"{k}.across"]:
                continue
            lev, s, g, xb = (_inch(n[f"{k}.{key}"]) for key in ("lev", "s", "g", "xb"))
            cols = [xb + j * g for j in range(ply.columns)]
            rows = [lev + i * s for i in range(itf.rows)]
            out.append(Element(name=ply.name, grade=ply.grade, fy=_ksi(n[f"{k}.fy"]), fu=_ksi(n[f"{k}.fu"]), t=_inch(n[f"{k}.t"]),
                               x0=0.0, x1=cols[-1] + _inch(n[f"{k}.side"]), y0=0.0, y1=2 * lev + (itf.rows - 1) * s,
                               dh=_inch(n[f"{k}.along"]), holes=tuple((x, y) for y in rows for x in cols),
                               bears=((0.0, -1.0),) * (len(rows) * len(cols)), support="edge", load="bolts",
                               copies=ply.sections, demand=float(n["v"] / calc.KIP), **common))
    elif conn.kind == "bolt_bracket":
        itf = geo.interfaces[0]
        ply = itf.plies[0]
        _, along, _ = bolt_dims(ctx, itf.bolts, ply.hole, itf.oriented)
        n = _numbers(ctx, {"t": ply.t, "lev": ply.edge, "side": ply.side, "s": itf.pitch, "g": itf.gauge, "e": ctx.attr("eccentricity"),
                           "along": along, "fy": ctx.mat(ply.grade, "fy"), "fu": ctx.mat(ply.grade, "fu"), "v": v})
        lev, s, g, e = (_inch(n[k]) for k in ("lev", "s", "g", "e"))
        cols = [j * g for j in range(itf.cols)]
        rows = [lev + i * s for i in range(itf.rows)]
        holes = tuple((x, y) for y in rows for x in cols)
        centre = (sum(cols) / len(cols), sum(rows) / len(rows))
        out.append(Element(name=ply.name, grade=ply.grade, fy=_ksi(n["fy"]), fu=_ksi(n["fu"]), t=_inch(n["t"]),
                           x0=-_inch(n["side"]), x1=centre[0] + e, y0=0.0, y1=2 * lev + (itf.rows - 1) * s, dh=_inch(n["along"]),
                           holes=holes, bears=elastic_bearing(holes, centre, e), support="bolts", load="edge", copies=1,
                           demand=float(n["v"] / calc.KIP), **common))
    elif conn.kind == "weld_bracket":
        plate = conn.attrs["plate"]
        n = _numbers(ctx, {"t": ctx.geo(plate.thickness, "plate.thickness"), "l": ctx.attr("weld_length"),
                           "e": ctx.attr("eccentricity"), "fy": ctx.mat(plate.grade, "fy"), "fu": ctx.mat(plate.grade, "fu"), "v": v})
        out.append(Element(name="bracket plate", grade=plate.grade, fy=_ksi(n["fy"]), fu=_ksi(n["fu"]), t=_inch(n["t"]),
                           x0=0.0, x1=_inch(n["e"]), y0=0.0, y1=_inch(n["l"]), dh=0.0, holes=(), bears=(), support="edge",
                           load="edge", copies=1, demand=float(n["v"] / calc.KIP), **common))
    return out


def elastic_bearing(holes: tuple[tuple[float, float], ...], centre: tuple[float, float], e: float) -> tuple[tuple[float, float], ...]:
    """Where each bolt of a bracket bears on its hole: opposite the force the plate puts on
    it under a downward load at arm e from the group's centre, by the elastic method (the
    plate turns about the centre and drops)."""
    n = len(holes)
    polar = sum((x - centre[0]) ** 2 + (y - centre[1]) ** 2 for x, y in holes)
    out = []
    for x, y in holes:
        dx, dy = x - centre[0], y - centre[1]
        fx, fy = e * dy / polar, -1.0 / n - e * dx / polar
        size = math.hypot(fx, fy)
        out.append((-fx / size, -fy / size))
    return tuple(out)


def _factor(registry, group: str, suffix: str, lrfd: bool) -> float:
    name = f"{group}.{'phi' if lrfd else 'omega'}{suffix}"
    return float(registry.constants[name].value.lo)


def _ply_limits(part, ply: str) -> float | None:
    found = [lim.capacity for lim in part.limits if lim.what == f"bearing on the {ply}"
             or lim.what.startswith((f"tearout of the {ply} to ", f"tearout of the {ply} along "))]
    return min(found) if found else None


def _owner(mode: str, what: str) -> str:
    """The element a check is about: the text before the colon, or for a weld's base metal,
    the part named after it."""
    head, _, rest = what.partition(": ")
    if mode == "weld_base_metal":
        return rest.split(" base metal")[0]
    return head


def _states(conn, design, registry, names: set[str], v_top: float) -> dict[str, list[State]]:
    lrfd = conn.basis == "lrfd"
    out: dict[str, list[State]] = {name: [] for name in names}
    for mode in required(conn, design):
        if mode not in JUDGED:
            continue
        run, group, suffix = JUDGED[mode]
        factor = _factor(registry, group, suffix, lrfd)

        def nominal(design_load: float, factor: float = factor) -> float:
            return design_load / factor if lrfd else design_load * factor

        for case in design.loads:
            for value in calc.values(conn, design, registry, mode, case):
                if value.excused or value.demand <= 0 or value.unit == "1":
                    continue
                if mode == "bolts":
                    concentric = "summed over the group" in value.what
                    # an eccentric group holds C times its weakest bolt, so the element's
                    # weakest bearing or tearout holds C times that
                    coefficient = value.capacity / min(part.capacity for part in value.parts) \
                        if "C times the weakest bolt" in value.what else None
                    for name in names:
                        caps = [(part.count, _ply_limits(part, name)) for part in value.parts]
                        caps = [(k, cap) for k, cap in caps if cap is not None]
                        if not caps:
                            continue
                        summed = sum(k * cap for k, cap in caps)
                        weakest = min(cap for _, cap in caps)
                        capacity = summed if concentric else weakest if coefficient is None else coefficient * weakest
                        design_load = v_top * capacity / value.demand
                        out[name].append(State(mode, f"{value.what.split(':')[0]}: bearing and tearout of the {name}", run,
                                               v_top / design_load, design_load, nominal(design_load), nominal(summed)))
                    continue
                name = _owner(mode, value.what)
                if name not in out:
                    continue
                design_load = v_top / value.utilisation
                out[name].append(State(mode, value.what, run, value.utilisation, design_load, nominal(design_load)))
    return out


def elements(text: str, task: str = "design") -> list[Element]:
    """Every element of the design's connection that the plane model covers, with the
    in-scope limit states Petra checked on it, most utilised first."""
    registry = _registry()
    design = parse_design(text, f"<{task}>", registry)
    out = []
    for name in design.components:
        conn = calc.connection(design, name, registry)
        found = _geometries(task, conn, design, registry)
        if not found:
            continue
        states = _states(conn, design, registry, {el.name for el in found}, found[0].demand)
        out += [replace(el, states=tuple(sorted(states[el.name], key=lambda s: -s.utilisation))) for el in found]
    return sorted(out, key=lambda el: -el.utilisation)


# --- The mesh -------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Mesh:
    """Eight-node quadrilaterals in the element's plane: xy (n, 2) in inches, and quads
    (m, 8): four corners counter-clockwise, then the mid-sides of edges 1-2, 2-3, 3-4, 4-1."""

    xy: np.ndarray
    quads: np.ndarray

    def area(self) -> float:
        """The area the quads cover, their sides read through the mid-side nodes."""
        ring = self.quads[:, [0, 4, 1, 5, 2, 6, 3, 7]]
        x, y = self.xy[ring, 0], self.xy[ring, 1]
        return float(0.5 * np.sum(x * np.roll(y, -1, axis=1) - np.roll(x, -1, axis=1) * y))


def _lines(lo: float, hi: float, centres: Iterable[float], h: float) -> list[float]:
    found = sorted({lo, hi, *(p for x in centres for p in (x - h, x + h))})
    out = [found[0]]
    for x in found[1:]:
        if x - out[-1] > 1e-9:
            out.append(x)
    return out


def _half(el: Element) -> float:
    """Half the side of the square block around each hole: room for the hole and a ring
    around it, inside the plate and clear of its neighbours."""
    r = el.dh / 2
    xs, ys = sorted({x for x, _ in el.holes}), sorted({y for _, y in el.holes})
    gaps = [b - a for a, b in zip(xs, xs[1:])] + [b - a for a, b in zip(ys, ys[1:])]
    edges = [x - el.x0 for x in xs] + [el.x1 - x for x in xs] + [y - el.y0 for y in ys] + [el.y1 - y for y in ys]
    h = min([2 * r, *(g / 2 for g in gaps), *edges])
    if h < 1.15 * r:
        raise ValueError(f"{el.task} {el.name}: no room for a ring of elements around the holes")
    return h


def mesh(el: Element, size: float) -> Mesh:
    """A structured mesh: the plate cut by lines either side of each hole into blocks, each
    block an n x m grid, and each hole's block an O-grid from the hole to the block's square."""
    pts: list[np.ndarray] = []
    quads: list[np.ndarray] = []

    def patch(lattice: np.ndarray) -> None:
        """A (2n+1, 2m+1, 2) lattice of points -> n x m quads."""
        base = sum(len(p) for p in pts)
        nu, nv = lattice.shape[0], lattice.shape[1]
        pts.append(lattice.reshape(-1, 2))
        idx = base + np.arange(nu * nv).reshape(nu, nv)
        for a in range(0, nu - 1, 2):
            for b in range(0, nv - 1, 2):
                corners = [idx[a, b], idx[a + 2, b], idx[a + 2, b + 2], idx[a, b + 2]]
                mids = [idx[a + 1, b], idx[a + 2, b + 1], idx[a + 1, b + 2], idx[a, b + 1]]
                quads.append(np.array(corners + mids))

    if not el.holes:
        nx, ny = max(1, math.ceil((el.x1 - el.x0) / size - 1e-9)), max(1, math.ceil((el.y1 - el.y0) / size - 1e-9))
        u = np.linspace(el.x0, el.x1, 2 * nx + 1)
        v = np.linspace(el.y0, el.y1, 2 * ny + 1)
        patch(np.stack(np.meshgrid(u, v, indexing="ij"), axis=-1))
    else:
        h = _half(el)
        r = el.dh / 2
        xs, ys = sorted({x for x, _ in el.holes}), sorted({y for _, y in el.holes})
        xl, yl = _lines(el.x0, el.x1, xs, h), _lines(el.y0, el.y1, ys, h)
        quarter = max(2, math.ceil(2 * h / size - 1e-9))
        ring = max(2, math.ceil((h - r) / size * 1.5 - 1e-9))

        def divisions(lines: list[float], centres: list[float]) -> list[int]:
            out = []
            for a, b in zip(lines, lines[1:]):
                hole = any(abs((a + b) / 2 - x) < 1e-9 and abs(b - a - 2 * h) < 1e-9 for x in centres)
                out.append(quarter if hole else max(1, math.ceil((b - a) / size - 1e-9)))
            return out

        dx, dy = divisions(xl, xs), divisions(yl, ys)
        centres = {(round(x, 9), round(y, 9)) for x, y in el.holes}
        for i, (xa, xb) in enumerate(zip(xl, xl[1:])):
            for j, (ya, yb) in enumerate(zip(yl, yl[1:])):
                key = (round((xa + xb) / 2, 9), round((ya + yb) / 2, 9))
                if key in centres and abs(xb - xa - 2 * h) < 1e-9 and abs(yb - ya - 2 * h) < 1e-9:
                    cx, cy = (xa + xb) / 2, (ya + yb) / 2
                    # four patches, each from a quarter of the circle to one side of the square
                    corners = [(xb, ya), (xb, yb), (xa, yb), (xa, ya)]
                    for k in range(4):
                        p0, p1 = corners[k], corners[(k + 1) % 4]
                        theta0 = -math.pi / 4 + k * math.pi / 2
                        s = np.linspace(0.0, 1.0, 2 * quarter + 1)
                        w = np.linspace(0.0, 1.0, 2 * ring + 1) ** 1.4
                        theta = theta0 + s * math.pi / 2
                        arc = np.stack([cx + r * np.cos(theta), cy + r * np.sin(theta)], axis=-1)
                        side = np.stack([p0[0] + s * (p1[0] - p0[0]), p0[1] + s * (p1[1] - p0[1])], axis=-1)
                        patch(arc[:, None, :] + w[None, :, None] * (side - arc)[:, None, :])
                else:
                    u = np.linspace(xa, xb, 2 * dx[i] + 1)
                    v = np.linspace(ya, yb, 2 * dy[j] + 1)
                    patch(np.stack(np.meshgrid(u, v, indexing="ij"), axis=-1))

    raw = np.concatenate(pts)
    keys, first, inverse = np.unique(np.round(raw, 7), axis=0, return_index=True, return_inverse=True)
    xy = raw[first]
    q = inverse.reshape(-1)[np.array(quads)]
    # counter-clockwise corners
    x, y = xy[q[:, :4], 0], xy[q[:, :4], 1]
    signed = np.sum(x * np.roll(y, -1, axis=1) - np.roll(x, -1, axis=1) * y, axis=1)
    flip = signed < 0
    q[flip] = q[flip][:, [0, 3, 2, 1, 7, 6, 5, 4]]
    return Mesh(xy, q)


# --- The CalculiX input ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Job:
    name: str
    element: Element
    run: str
    size: float
    travel: float          # in: how far the loaded nodes are pushed
    inp: str
    nodes: int


def travel(el: Element) -> float:
    """How far the run pushes: far enough past the elongation limit, or onto the plateau."""
    if el.load == "bolts":
        return 0.4
    if el.support == "bolts":
        cx = sum(x for x, _ in el.holes) / len(el.holes)
        cy = sum(y for _, y in el.holes) / len(el.holes)
        reach = max(math.hypot(x - cx, y - cy) for x, y in el.holes)
        return 0.4 * (el.x1 - cx) / reach
    return 0.05 * (el.x1 - el.x0)


def _set(name: str, ids: Iterable[int]) -> list[str]:
    ids = list(ids)
    out = [f"*NSET, NSET={name}"]
    out += [", ".join(str(i) for i in ids[k:k + 16]) for k in range(0, len(ids), 16)]
    return out


def _solid(el: Element, size: float, title: str) -> tuple[list[str], Mesh, Callable[[int], list[int]]]:
    """The element meshed and extruded to one layer of C3D20R, t thick: the *NODE and
    *ELEMENT lines, the plane mesh, and a map from a plane node to the 3D nodes through
    the thickness above it (1-based ids)."""
    m = mesh(el, size)
    n2 = len(m.xy)
    corner = np.zeros(n2, dtype=bool)
    corner[m.quads[:, :4].reshape(-1)] = True

    def column(k: int) -> list[int]:
        return [k + 1, n2 + k + 1] + ([2 * n2 + k + 1] if corner[k] else [])

    lines = ["*HEADING", title, "*NODE, NSET=NALL"]
    for k, (x, y) in enumerate(m.xy):
        lines.append(f"{k + 1}, {x:.9g}, {y:.9g}, 0")
    for k, (x, y) in enumerate(m.xy):
        lines.append(f"{n2 + k + 1}, {x:.9g}, {y:.9g}, {el.t:.9g}")
    for k in np.flatnonzero(corner):
        x, y = m.xy[k]
        lines.append(f"{2 * n2 + k + 1}, {x:.9g}, {y:.9g}, {el.t / 2:.9g}")
    lines.append("*ELEMENT, TYPE=C3D20R, ELSET=EALL")
    for e, q in enumerate(m.quads):
        b = [int(i) + 1 for i in q]
        top = [i + n2 for i in b]
        mid = [2 * n2 + i for i in b[:4]]
        nodes = b[:4] + top[:4] + b[4:] + top[4:] + mid
        lines.append(f"{e + 1}, " + ", ".join(str(i) for i in nodes[:15]) + ",")
        lines.append(", ".join(str(i) for i in nodes[15:]))
    lines += _set("NSYM", range(1, n2 + 1))
    return lines, m, column


def _material(el: Element, run: str) -> list[str]:
    if run == "yield":
        plastic = [(el.fy, 0.0), (el.fy, 10.0)]
    else:
        plastic = [(el.fy, 0.0), (el.fy, STRAIN_HARDENING), (el.fu, STRAIN_ULTIMATE), (el.fu, 10.0)]
    return (["*MATERIAL, NAME=STEEL", "*ELASTIC", f"{E_KSI}, {NU}", "*PLASTIC"] + [f"{s:.9g}, {e:.9g}" for s, e in plastic]
            + ["*SOLID SECTION, ELSET=EALL, MATERIAL=STEEL", "*BOUNDARY", "NSYM, 3, 3"])


def deck(el: Element, run: str, size: float, name: str | None = None) -> Job:
    """The CalculiX input for one run of one element."""
    lines, m, column = _solid(el, size, f"Petra CalculiX check: {el.task} {el.name}, {run} run, size {size} in")
    on = lambda x, at: abs(x - at) < 1e-7  # noqa: E731
    fixed, loaded, eqs, far = [], [], [], []
    hole_nodes = []
    for (hx, hy), (bx, by) in zip(el.holes, el.bears):
        dist = np.hypot(m.xy[:, 0] - hx, m.xy[:, 1] - hy)
        rim = np.flatnonzero(np.abs(dist - el.dh / 2) < 1e-6)
        cosine = ((m.xy[rim, 0] - hx) * bx + (m.xy[rim, 1] - hy) * by) / (el.dh / 2)
        arc = rim if run == "yield" else rim[cosine >= math.cos(math.radians(ARC)) - 1e-9]
        hole_nodes.append((arc, (bx, by)))
        far.append(int(rim[np.argmin(cosine)]) + 1)
    if el.support == "edge":
        fixed = [i for k in np.flatnonzero([on(x, el.x0) for x in m.xy[:, 0]]) for i in column(k)]
    if el.load == "edge":
        loaded = [i for k in np.flatnonzero([on(x, el.x1) for x in m.xy[:, 0]]) for i in column(k)]
    else:
        loaded = [i for arc, _ in hole_nodes for k in arc for i in column(k)]
    lines += _set("NFIX", fixed) if fixed else []
    lines += _set("NLOAD", loaded)
    if far:
        lines += _set("NFAR", far)
    bolted = [i for arc, _ in hole_nodes for k in arc for i in column(k)]
    if el.support == "bolts" and run == "yield":
        lines += _set("NBOLT", bolted)
    if el.support == "bolts" and run == "rupture":
        for arc, (bx, by) in hole_nodes:
            for i in (i for k in arc for i in column(k)):
                eqs += ["*EQUATION", "2", f"{i}, 2, {by:.12g}, {i}, 1, {bx:.12g}"] if abs(by) > 1e-12 else ["*BOUNDARY", f"{i}, 1, 1"]
    lines += _material(el, run)
    if fixed:
        lines += ["NFIX, 1, 2"]
    if el.support == "bolts" and run == "yield":
        lines += ["NBOLT, 1, 2"]
    if el.clamp:
        lines += ["NLOAD, 1, 1"]
    lines += eqs
    push = travel(el)
    lines += ["*STEP, INC=2000", "*STATIC", "0.01, 1.0, 1e-7, 0.02", "*BOUNDARY", f"NLOAD, 2, 2, {-push:.9g}",
              "*NODE PRINT, NSET=NLOAD, TOTALS=ONLY", "RF"]
    if far:
        lines += ["*NODE PRINT, NSET=NFAR", "U"]
    lines += ["*END STEP", ""]
    job = name or re.sub(r"[^A-Za-z0-9]+", "_", f"{el.task}_{el.name}_{run}_{size}").strip("_")
    return Job(job, el, run, size, push, "\n".join(lines), _count(lines))


def _count(lines: list[str]) -> int:
    """The nodes a deck declares."""
    return lines.index("*ELEMENT, TYPE=C3D20R, ELSET=EALL") - lines.index("*NODE, NSET=NALL") - 1


# --- Running CalculiX -----------------------------------------------------------------------------

class Unreachable(RuntimeError):
    """No ccx on PATH and no answer from the host."""


@dataclass
class Ccx:
    """Runs batches of CalculiX inputs, here when `ccx` is on PATH, else on `host` over ssh."""

    host: str | None = HOST
    workers: int = 2
    local: str | None = field(default_factory=lambda: shutil.which("ccx"))

    def _ssh(self, command: str, stdin: bytes = b"", timeout: float = 6 * 3600) -> bytes:
        args = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=30", "-o", "ServerAliveInterval=30", self.host, command]
        last = ""
        for attempt in range(4):
            done = subprocess.run(args, input=stdin, capture_output=True, timeout=timeout)
            if done.returncode != 255:
                if done.returncode != 0:
                    raise RuntimeError(f"ssh {self.host}: {done.stderr.decode(errors='replace')[-400:]}")
                return done.stdout
            last = done.stderr.decode(errors="replace").strip()
            time.sleep(10 * (attempt + 1))
        raise Unreachable(f"ssh {self.host}: {last}")

    def reachable(self) -> bool:
        if self.local:
            return True
        if not self.host:
            return False
        try:
            return b"ccx" in self._ssh("command -v ccx", timeout=120)
        except (Unreachable, RuntimeError, subprocess.TimeoutExpired):
            return False

    def run(self, jobs: list[Job]) -> dict[str, str]:
        """Each job's .dat text and the tail of its .sta, by name."""
        if self.local:
            return self._run_here(jobs)
        if not self.host:
            raise Unreachable("no ccx on PATH and no host")
        return self._run_there(jobs)

    def _run_here(self, jobs: list[Job]) -> dict[str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            for job in jobs:
                Path(tmp, f"{job.name}.inp").write_text(job.inp)
            env = dict(os.environ, OMP_NUM_THREADS="1", CCX_NPROC_EQUATION_SOLVER="1")

            def one(job: Job) -> None:
                with open(Path(tmp, f"{job.name}.log"), "w") as log:
                    subprocess.run([self.local, "-i", job.name], cwd=tmp, env=env, stdout=log, stderr=subprocess.STDOUT)

            with ThreadPoolExecutor(self.workers) as pool:
                list(pool.map(one, jobs))
            return {job.name: _read(Path(tmp), job.name) for job in jobs}

    def _run_there(self, jobs: list[Job]) -> dict[str, str]:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for job in jobs:
                data = job.inp.encode()
                info = tarfile.TarInfo(f"{job.name}.inp")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        where = f"calculix_check/{uuid.uuid4().hex[:12]}"
        command = (f"set -e; mkdir -p ~/{where}; cd ~/{where}; tar -xzf -; "
                   f"ls *.inp | sed 's/[.]inp$//' | xargs -P {self.workers} -I{{}} sh -c "
                   f"'OMP_NUM_THREADS=1 CCX_NPROC_EQUATION_SOLVER=1 ccx -i {{}} > {{}}.log 2>&1 || true'; "
                   f"tar -czf - *.dat *.sta *.log; cd ~; rm -rf ~/{where}")
        out = self._ssh(command, stdin=buffer.getvalue())
        with tempfile.TemporaryDirectory() as tmp:
            with tarfile.open(fileobj=io.BytesIO(out), mode="r:gz") as tar:
                for member in tar.getmembers():
                    if member.isfile() and "/" not in member.name:
                        Path(tmp, member.name).write_bytes(tar.extractfile(member).read())
            return {job.name: _read(Path(tmp), job.name) for job in jobs}


def _read(where: Path, name: str) -> str:
    dat, sta, log = (where / f"{name}.{ext}" for ext in ("dat", "sta", "log"))
    text = dat.read_text(errors="replace") if dat.exists() else ""
    tail = sta.read_text(errors="replace").strip().splitlines()[-1:] if sta.exists() else []
    errors = [line for line in (log.read_text(errors="replace").splitlines() if log.exists() else []) if "ERROR" in line]
    return text + "\n#STA " + " ".join(tail) + "".join(f"\n#ERR {e}" for e in errors[:5])


# --- Reading the results --------------------------------------------------------------------------

@dataclass(frozen=True)
class Curve:
    """A run's history: at each converged increment, the fraction of the push done, the
    load on the loaded nodes (kip, positive) and the largest hole elongation (in)."""

    time: tuple[float, ...]
    load: tuple[float, ...]
    elongation: tuple[float, ...]
    complete: bool
    errors: tuple[str, ...]

    def capacity(self, run: str) -> tuple[float, float]:
        """(capacity, the fraction of the push at which it is reached). The rupture run
        stops counting where a hole first stretches ELONGATION."""
        best, at = 0.0, 0.0
        for t, p, d in zip(self.time, self.load, self.elongation):
            if run == "rupture" and d > ELONGATION:
                break
            if p > best:
                best, at = p, t
        return best, at

    def resolved(self, run: str) -> bool:
        """The run went far enough to measure its capacity: to the end of its push, or for
        the rupture run, past the elongation limit."""
        return self.complete or (run == "rupture" and any(d > ELONGATION for d in self.elongation))

    def plateau(self) -> float:
        """How much the load grew over the last fifth of the run, as a share of the last load."""
        if not self.load:
            return math.nan
        last = self.time[-1]
        earlier = [p for t, p in zip(self.time, self.load) if t <= 0.8 * last]
        return (self.load[-1] - (earlier[-1] if earlier else 0.0)) / self.load[-1]


_HEADER = re.compile(r"^\s*(total force|forces|displacements)\s.*?for set (\S+) and time\s+(\S+)", re.I)


def _blocks(text: str) -> dict[tuple[str, str], dict[float, list[list[float]]]]:
    """The .dat file's printed blocks: (what, node set) -> time -> rows of numbers."""
    out: dict[tuple[str, str], dict[float, list[list[float]]]] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        found = _HEADER.match(lines[i])
        i += 1
        if not found:
            continue
        rows: list[list[float]] = []
        while i < len(lines) and not _HEADER.match(lines[i]) and not lines[i].lstrip().startswith("#"):
            parts = lines[i].split()
            if parts:
                try:
                    rows.append([float(p) for p in parts])
                except ValueError:
                    break
            elif rows:
                break
            i += 1
        out.setdefault((found.group(1).lower(), found.group(2).upper()), {})[float(found.group(3))] = rows
    return out


def parse(text: str, job: Job) -> Curve:
    blocks = _blocks(text)
    loads = {t: abs(rows[0][1]) for t, rows in blocks.get(("total force", "NLOAD"), {}).items() if rows}
    far = blocks.get(("displacements", "NFAR"), {})
    el = job.element
    order = {nid: k for k, nid in enumerate(_far_ids(job))}
    times = sorted(loads)
    elongation = []
    for t in times:
        worst = 0.0
        for nid, ux, uy, *_ in far.get(t, []):
            bx, by = el.bears[order[int(nid)]]
            bolt = (job.travel * t * bx, job.travel * t * by) if el.load == "bolts" else (0.0, 0.0)
            worst = max(worst, bx * (bolt[0] - ux) + by * (bolt[1] - uy))
        elongation.append(worst)
    complete = bool(times) and abs(times[-1] - 1.0) < 1e-6
    errors = tuple(re.findall(r"^#ERR (.*)$", text, re.M))
    return Curve(tuple(times), tuple(loads[t] for t in times), tuple(elongation), complete, errors)


def _far_ids(job: Job) -> list[int]:
    found = re.search(r"\*NSET, NSET=NFAR\n(.*?)\n\*", job.inp, re.S)
    if not found:
        return []
    return [int(x) for x in re.split(r"[,\s]+", found.group(1).strip()) if x]


# --- Comparing --------------------------------------------------------------------------------------

def arm(el: Element) -> float:
    """How far the load acts from the section the element bends about: the bolt group's
    centre from the held edge, the loaded edge from the held edge, or the loaded edge
    from the bracket's last bolt column."""
    if el.load == "bolts":
        return sum(x for x, _ in el.holes) / len(el.holes) - el.x0
    if el.support == "bolts":
        return el.x1 - max(x for x, _ in el.holes)
    return el.x1 - el.x0


def reference(el: Element) -> dict:
    """R_int, the yield run's reference capacity (docs/calculix_check.md): Manual Eq 10-5's
    circle through the von Mises shear strength and the flexural strength, in kip of
    connection load. A term Petra has no check for is the plate's own, and says so."""
    shear = [s.nominal for s in el.states if s.mode == "shear_yield"]
    flexure = [s.nominal for s in el.states if s.mode == "flexural_yield"]
    depth = el.y1 - el.y0
    vn = min(shear) if shear else el.copies * 0.6 * el.fy * el.t * depth
    mn = min(flexure) if flexure else el.copies * el.fy * el.t * depth ** 2 / 4 / arm(el)
    return {"r_int": 1 / math.hypot(1 / (VON_MISES * vn), 1 / mn), "shear": vn, "flexure": mn,
            "shear_from": "petra" if shear else "plate", "flexure_from": "petra" if flexure else "plate"}


def compare(el: Element, curves: dict[str, Curve]) -> dict:
    """Each run's FE capacity against the governing state it judges, and for a flag, the
    way it points: "model" when the yield run reaches (1 - BAND) R_int, "unresolved" when
    the run stopped before it could measure its capacity, else "deck"."""
    out = {}
    for run in RUNS:
        curve = curves[run]
        capacity, at = curve.capacity(run)
        fe = el.copies * capacity
        states = [s for s in el.states if s.run == run]
        entry = {"fe": fe, "at": at * travel(el), "complete": curve.complete, "resolved": curve.resolved(run),
                 "plateau": curve.plateau(), "increments": len(curve.time), "errors": list(curve.errors)}
        if run == "yield" and states:
            entry["reference"] = reference(el)
        if states:
            gov = min(states, key=lambda s: s.design)
            flagged = fe < gov.design
            direction = None
            if flagged and not entry["resolved"]:
                direction = "unresolved"
            elif flagged:
                explained = run == "yield" and fe >= (1 - BAND) * entry["reference"]["r_int"]
                direction = "model" if explained else "deck"
            entry.update(governing=gov.what, mode=gov.mode, design=gov.design, nominal=gov.nominal,
                         ratio=fe / gov.nominal, margin=fe / gov.design, flagged=flagged, direction=direction,
                         below_demand=fe < el.demand,
                         ratios={s.what: fe / s.nominal for s in states})
        out[run] = entry
    return out


def check_elements(found: list[Element], ccx: Ccx, size: float) -> list[dict]:
    jobs = [deck(el, run, size) for el in found for run in RUNS]
    results = ccx.run(jobs)
    out = []
    for el in found:
        curves = {job.run: parse(results[job.name], job) for job in jobs if job.element is el}
        out.append({"task": el.task, "kind": el.kind, "element": el.name, "copies": el.copies, "basis": el.basis,
                    "demand": el.demand, "size": size, "nodes": max(j.nodes for j in jobs if j.element is el),
                    "fy": el.fy, "fu": el.fu, "t": el.t, "states": [asdict(s) for s in el.states],
                    "runs": compare(el, curves),
                    "curves": {run: {k: [float(f"{x:.5g}") for x in getattr(c, k)] for k in ("time", "load", "elongation")}
                               for run, c in curves.items()}})
    return out


# --- Commands ---------------------------------------------------------------------------------------

def _summary(row: dict) -> str:
    lines = [f"{row['task']} {row['kind']}: {row['element']} x{row['copies']}, demand {row['demand']:.1f} kip, "
             f"{row['nodes']} nodes at size {row['size']} in"]
    for run, entry in row["runs"].items():
        if "governing" not in entry:
            lines.append(f"  {run}: FE {entry['fe']:.1f} kip, no state judged")
            continue
        flag = f"FLAG, points to the {entry['direction']}" if entry["flagged"] else "ok"
        ref = f"  R_int {entry['reference']['r_int']:.1f}" if "reference" in entry else ""
        lines.append(f"  {run:8s} FE {entry['fe']:7.1f} kip  design {entry['design']:7.1f}  nominal {entry['nominal']:7.1f}{ref}  "
                     f"FE/Rn {entry['ratio']:.3f}  {flag}  ({entry['governing']})"
                     + ("" if entry["complete"] else "  [run incomplete]"))
    return "\n".join(lines)


def close_call(row: dict) -> bool:
    """A finer mesh could change the verdict: some run stopped early, or its FE capacity is
    within NEAR of its design strength, or for a yield flag, of (1 - BAND) R_int."""
    for e in row["runs"].values():
        if "design" not in e:
            continue
        if not e["resolved"] or abs(e["margin"] - 1) < NEAR:
            return True
        if e["flagged"] and "reference" in e and abs(e["fe"] / ((1 - BAND) * e["reference"]["r_int"]) - 1) < NEAR:
            return True
    return False


def cmd_check(args) -> int:
    found = elements(Path(args.file).read_text(encoding="utf-8"), Path(args.file).stem)
    if not found:
        print("no element of this design is in the plane model's scope")
        return 1
    chosen = found if args.all else found[:1]
    for row in check_elements(chosen, Ccx(args.host, args.workers), args.size):
        print(_summary(row))
    return 0


def optima(path: Path) -> list[tuple[str, str]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [(r["task"], r["optimum"]) for r in rows if r.get("optimum")]


def cmd_sample(args) -> int:
    out = Path(args.out)
    done = {json.loads(line)["task"] for line in out.read_text(encoding="utf-8").splitlines()} if out.exists() else set()
    todo = []
    for task, text in optima(Path(args.log)):
        if task in done or (args.tasks and task not in args.tasks):
            continue
        found = elements(text, task)
        if found:
            todo.append(found[0])
    print(f"{len(todo)} designs to check, {len(done)} already in {out}")
    ccx = Ccx(args.host, args.workers)
    for k in range(0, len(todo), args.batch):
        start = time.time()
        batch = todo[k:k + args.batch]
        rows = check_elements(batch, ccx, args.screen)
        again = {row["task"] for row in rows if close_call(row)} if args.screen != args.size else set()
        if again:
            fine = {row["task"]: row for row in check_elements([el for el in batch if el.task in again], ccx, args.size)}
            rows = [dict(fine[row["task"]], screen={"size": row["size"], "fe": {run: e["fe"] for run, e in row["runs"].items()}})
                    if row["task"] in fine else row for row in rows]
        with out.open("a", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
                print(_summary(row))
        print(f"batch of {len(rows)}, {len(again)} run again at {args.size} in, in {time.time() - start:.0f} s", flush=True)
    return 0


def plain(name: str, depth: float, width: float, t: float, clamp: bool) -> Element:
    """A plain A36 plate held along x = 0 and pushed down along x = width."""
    return Element(task=name, kind="plain", name="plate", grade="steel.A36", fy=36.0, fu=58.0, t=t, x0=0.0, x1=width,
                   y0=0.0, y1=depth, dh=0.0, holes=(), bears=(), support="edge", load="edge", copies=1, basis="lrfd",
                   demand=0.0, clamp=clamp)


VALIDATION = {
    # name -> (plate, hand solution in kip, what the hand solution is)
    "shear": (plain("shear", 12.0, 1.5, 0.5, True), 36.0 / math.sqrt(3) * 12.0 * 0.5,
              "12 in deep, 1.5 in long, 1/2 in plate, both ends held in x: Fy / sqrt(3) d t"),
    "cantilever": (plain("cantilever", 6.0, 24.0, 0.5, False), 36.0 * 0.5 * 6.0 ** 2 / 4 / 24.0,
                   "6 in deep, 24 in long, 1/2 in plate welded along one end: Fy t d^2 / 4 / L"),
}
BENDING_MP = 36.0 * 0.5 * 6.0 ** 2 / 4


def bending(size: float) -> tuple[Job, dict[int, float]]:
    """Half of a 6 in deep, 60 in long, 1/2 in A36 plate in four-point bending: held up on its
    bottom edge within 1 in of x = 0, pushed down on its top edge within 1/2 in of x = 24,
    and held in x along x = 30, its plane of symmetry. The moment there is constant and
    shear-free, and is read from the reactions: the hand solution is Mp = Fy t d^2 / 4.
    Returns the job and the height above mid-depth of each node on the symmetry plane."""
    el = plain("bending", 6.0, 30.0, 0.5, False)
    lines, m, column = _solid(el, size, f"Petra CalculiX check: four-point bending, size {size} in")
    x, y = m.xy[:, 0], m.xy[:, 1]
    mid = np.flatnonzero(np.abs(x - 30.0) < 1e-7)
    support = np.flatnonzero((np.abs(y) < 1e-7) & (x <= 1.0 + 1e-7))
    load = np.flatnonzero((np.abs(y - 6.0) < 1e-7) & (np.abs(x - 24.0) <= 0.5 + 1e-7))
    lines += _set("NMID", [i for k in mid for i in column(k)])
    lines += _set("NSUP", [i for k in support for i in column(k)])
    lines += _set("NLOAD", [i for k in load for i in column(k)])
    lines += _material(el, "yield") + ["NMID, 1, 1", "NSUP, 2, 2"]
    lines += ["*STEP, INC=2000", "*STATIC", "0.01, 1.0, 1e-7, 0.02", "*BOUNDARY", "NLOAD, 2, 2, -0.8",
              "*NODE PRINT, NSET=NLOAD, TOTALS=ONLY", "RF", "*NODE PRINT, NSET=NMID", "RF", "*END STEP", ""]
    arms = {i: float(y[k] - 3.0) for k in mid for i in column(k)}
    return Job(f"validate_bending_{size}", el, "yield", size, 0.8, "\n".join(lines), _count(lines)), arms


def moment(text: str, arms: dict[int, float]) -> float:
    """The largest moment, in kip-in, the symmetry plane's reactions carry over the run."""
    found = _blocks(text).get(("forces", "NMID"), {})
    return max((abs(sum(r[1] * arms[int(r[0])] for r in rows)) for rows in found.values()), default=0.0)


def cmd_validate(args) -> int:
    ccx = Ccx(args.host, args.workers)
    jobs = [deck(el, "yield", size, f"validate_{name}_{size}") for name, (el, _, _) in VALIDATION.items() for size in args.sizes]
    benders = {size: bending(size) for size in args.sizes}
    results = ccx.run(jobs + [job for job, _ in benders.values()])
    print("| Case | Size (in) | Nodes | FE | Hand | FE / hand | Plateau gain |")
    print("|---|---|---|---|---|---|---|")
    for job in jobs:
        name = job.name.split("_")[1]
        _, hand, _ = VALIDATION[name]
        curve = parse(results[job.name], job)
        fe, _ = curve.capacity("yield")
        print(f"| {name} | {job.size} | {job.nodes} | {fe:.2f} kip | {hand:.2f} kip | {fe / hand:.4f} | {curve.plateau():.4f} |"
              + ("" if curve.complete else " incomplete"))
    for size, (job, arms) in benders.items():
        fe = moment(results[job.name], arms)
        curve = parse(results[job.name], job)
        print(f"| bending | {size} | {job.nodes} | {fe:.2f} kip-in | {BENDING_MP:.2f} kip-in | {fe / BENDING_MP:.4f} | "
              f"{curve.plateau():.4f} |" + ("" if curve.complete else " incomplete"))
    return 0


def cmd_converge(args) -> int:
    ccx = Ccx(args.host, args.workers)
    texts = dict(optima(Path(args.log)))
    print("| Task | Element | Size (in) | Nodes | Yield FE (kip) | Rupture FE (kip) |")
    print("|---|---|---|---|---|---|")
    for task in args.tasks:
        el = elements(texts[task], task)[0]
        for size in args.sizes:
            row = check_elements([el], ccx, size)[0]
            y, r = row["runs"]["yield"], row["runs"]["rupture"]
            print(f"| {task} | {el.name} | {size} | {row['nodes']} | {y['fe']:.2f} | {r['fe']:.2f} |", flush=True)
    return 0


def _spread(found: list[float]) -> str:
    q = statistics.quantiles(found, n=10, method="inclusive") if len(found) > 1 else [found[0]] * 9
    return (f"{len(found)} | {min(found):.3f} | {q[0]:.3f} | {statistics.median(found):.3f} | {q[-1]:.3f} | "
            f"{max(found):.3f}")


def summed_bolts(row: dict, text: str) -> tuple[str, float] | None:
    """For a design whose rupture run is governed by an eccentric bolt group: the state that
    governs, and its Rn, when the group's bearing and tearout are summed over its bolts as a
    concentric group's are. The model pushes every bolt alike, so this is the strength it
    tests. A diagnostic after the fact, not part of the criterion."""
    entry = row["runs"]["rupture"]
    if entry.get("mode") != "bolts" or "summed over the group" in entry["governing"]:
        return None
    el = next(e for e in elements(text, row["task"]) if e.name == row["element"])
    nominals = [(s.what, s.summed if s.mode == "bolts" else s.nominal) for s in el.states if s.run == "rupture"]
    return min(nominals, key=lambda wn: wn[1])


def cmd_report(args) -> int:
    rows = [json.loads(line) for line in Path(args.out).read_text(encoding="utf-8").splitlines() if line.strip()]
    kinds: dict[str, int] = {}
    for row in rows:
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
    print(f"{len(rows)} designs: " + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
          + f". {sum('screen' in r for r in rows)} were run again at the finer size.\n")
    print("Flags\n")
    print("| Task | Kind | Basis | Run | Governing state | FE / Rn | FE / design | FE / R_int | Points to |")
    print("|---|---|---|---|---|---|---|---|---|")
    for row in rows:
        for run, e in row["runs"].items():
            if e.get("flagged"):
                ref = f"{e['fe'] / e['reference']['r_int']:.3f}" if "reference" in e else ""
                print(f"| {row['task']} | {row['kind']} | {row['basis'].upper()} | {run} | {e['governing']} | {e['ratio']:.3f} | "
                      f"{e['margin']:.3f} | {ref} | {e['direction']} |")
    print("\nFE / Rn of the governing state\n")
    print("| Run | Basis | Governing mode | n | min | p10 | median | p90 | max |")
    print("|---|---|---|---|---|---|---|---|---|")
    groups: dict[tuple[str, str, str], list[float]] = {}
    for row in rows:
        for run, e in row["runs"].items():
            if "governing" in e:
                for key in ((run, "all", "all"), (run, row["basis"], e["mode"])):
                    groups.setdefault(key, []).append(e["ratio"])
    for (run, basis, mode), found in sorted(groups.items(), key=lambda kv: (RUNS.index(kv[0][0]), kv[0][1] != "all", kv[0])):
        print(f"| {run} | {basis.upper() if basis != 'all' else 'all'} | {mode} | {_spread(found)} |")

    print("\nYield run: FE / R_int\n")
    print("| Kind | n | min | p10 | median | p90 | max |")
    print("|---|---|---|---|---|---|---|")
    by_kind: dict[str, list[float]] = {}
    for row in rows:
        e = row["runs"]["yield"]
        if "reference" in e:
            for key in ("all", row["kind"]):
                by_kind.setdefault(key, []).append(e["fe"] / e["reference"]["r_int"])
    for kind, found in sorted(by_kind.items(), key=lambda kv: (kv[0] != "all", kv[0])):
        print(f"| {kind} | {_spread(found)} |")

    texts = dict(optima(Path(args.log)))
    summed = [(row, summed_bolts(row, texts[row["task"]])) for row in rows]
    summed = [(row, found) for row, found in summed if found]
    if summed:
        print("\nEccentric bolt groups: rupture FE against the bolts summed\n")
        print("| Task | Kind | Basis | FE / Rn, eccentric | Governing state, bolts summed | FE / Rn, bolts summed |")
        print("|---|---|---|---|---|---|")
        for row, (what, rn) in summed:
            e = row["runs"]["rupture"]
            print(f"| {row['task']} | {row['kind']} | {row['basis'].upper()} | {e['ratio']:.3f} | {what} | {e['fe'] / rn:.3f} |")
        print(f"\nFE / Rn, bolts summed: n | min | p10 | median | p90 | max = {_spread([r['runs']['rupture']['fe'] / f[1] for r, f in summed])}")

    print("\nEvery design\n")
    print("| Task | Kind | Element | Basis | Size (in) | Yield state | Yield FE / Rn | Rupture state | Rupture FE / Rn | Flag |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for row in rows:
        y, r = row["runs"]["yield"], row["runs"]["rupture"]
        flags = ", ".join(f"{run}, {e['direction']}" for run, e in row["runs"].items() if e.get("flagged"))
        print(f"| {row['task']} | {row['kind']} | {row['element']} | {row['basis'].upper()} | {row['size']} | "
              f"{y.get('mode', '')} | {y.get('ratio', math.nan):.3f} | {r.get('mode', '')} | {r.get('ratio', math.nan):.3f} | {flags} |")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--workers", type=int, default=2)
    sub_ = parser.add_subparsers(dest="command", required=True)
    p = sub_.add_parser("check")
    p.add_argument("file")
    p.add_argument("--size", type=float, default=SIZE)
    p.add_argument("--all", action="store_true", help="every element the model covers, not only the governing one")
    p = sub_.add_parser("sample")
    p.add_argument("--log", default=str(LOG))
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--size", type=float, default=SIZE)
    p.add_argument("--screen", type=float, default=SCREEN)
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--tasks", nargs="*")
    p = sub_.add_parser("validate")
    p.add_argument("--sizes", type=float, nargs="+", default=[0.5, 0.25, 0.125])
    p = sub_.add_parser("converge")
    p.add_argument("tasks", nargs="+")
    p.add_argument("--log", default=str(LOG))
    p.add_argument("--sizes", type=float, nargs="+", default=[0.5, 0.35, 0.25])
    p = sub_.add_parser("report")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--log", default=str(LOG))
    args = parser.parse_args(argv)
    return {"check": cmd_check, "sample": cmd_sample, "validate": cmd_validate, "converge": cmd_converge,
            "report": cmd_report}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
