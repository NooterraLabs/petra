"""Twin elaborator for the steel-connection deck. Tooling: it cannot change a verdict.

A second, independent implementation of the deck's limit states (docs/steel_connections.md
section 8, "twin elaborator, written independently from the same sources"). It reads the
method statements in vocab.py, the grammar in lower.py, the load paths in path.py and the
numbers in the registry, and evaluates every check in plain float arithmetic at the upper
end of each load interval. It never imports checks, limits, build, calc or domain, nor the
mechanics layer under them (petra/mechanics), so a disagreement with the deck is a
disagreement of translation, which tests/test_steel_twin.py records, and a slip in a
shared formula cannot agree with itself (tests/test_mechanics.py holds the imports).

Units: inches, kips, ksi throughout. Every number the registry holds is read from it.

Readings. Where a method statement leaves a choice open, the reading taken here is stated
in a comment beside the code with the source that supports it. The force on a beam-end
shear connection acts downward on the beam, so:
  - holes in the beam web bear on their upper edge (tearout toward the top flange or cope),
  - holes in an element bolted to the beam web (plate, angle leg, tee stem) bear on their
    lower edge (tearout toward the element's bottom edge),
  - holes in an element bolted to the support (angle outstanding leg, tee flange, end
    plate, seat leg, bracket plate) bear on their upper edge (tearout toward its top edge),
  - holes in the support itself have no free edge in the force direction.
This is the edge assignment the Companion v16 uses throughout Part II (Examples II.A-1A,
II.A-11A, II.A-17A, II.A-28A, II.A-30: "the edge bolt" is the bottom bolt in the plate or
beam-side leg and the top bolt in the support-side leg or end plate).
"""
from __future__ import annotations

import itertools
import math
from fractions import Fraction
from typing import Callable, Iterable, Mapping

from ...ir import Design, Fixed, Input, ParamRef
from ...registry import Registry
from ...registry.steel import INCH, KIP, KSI
from .lower import KIND_SPECS, AngleSpec, Bolts, Conn, Cope, Member, PlateSpec, TeeSpec, Weld, lower_conn
from .path import ROLE_LIMITS, path

UNCHECKED = ("load_path", "j10_stiffeners")
"""Modes that require() can list but that have no check (unmodelled in v1.0)."""

SIXTEENTH = 1.0 / 16.0
UNDERRUN = 0.25
"""Inches a beam may arrive short (Manual Part 10). The Companion's strength checks take
it off the beam web's end distance (II.A-4's block shear, Ant = leh - 1/4 in) and add it to
a seat's setback (II.A-12A, II.A-14: lb = W - setback - underrun); its edge limits and its
cope arm (II.A-4: e = c + setback = 4-1/2 in) use the lengths as detailed."""


# --- Unit conversion and registry access -------------------------------------------------

def _inch(x: Fraction) -> float:
    return float(x / INCH)


def _kip(x: Fraction) -> float:
    return float(x / KIP)


def _ksi(x: Fraction) -> float:
    return float(x / KSI)


class _Reg:
    """The registry's numbers in customary units."""

    def __init__(self, registry: Registry) -> None:
        self.r = registry

    def const(self, name: str) -> float:
        c = self.r.constants[name]
        v = c.value.lo
        scale = {"m": INCH, "Pa": KSI, "N": KIP, "1": Fraction(1), "m2": INCH * INCH}[c.unit]
        return float(v / scale)

    def stated(self, entry: str, prop: str) -> float:
        p = self.r.materials[entry].props[prop]
        return _ksi(p.value.lo)

    def steel(self, grade: str) -> tuple[float, float]:
        return self.stated(grade, "fy"), self.stated(grade, "fu")

    @property
    def E(self) -> float:
        return self.const("aisc360.E")

    def w_shape(self, shape: str) -> dict[str, float]:
        out = {p: self.const(f"aisc_shapes_v16.{shape}.{p}") for p in ("d", "bf", "tf", "tw", "kdes")}
        out["A"] = self.const(f"aisc_shapes_v16.{shape}.A")
        return out

    def angle(self, shape: str) -> tuple[float, float, float]:
        """(long leg, short leg, thickness)."""
        return tuple(self.const(f"aisc_shapes_v16.{shape}.{p}") for p in ("d", "b", "t"))  # type: ignore[return-value]

    def bolt(self, size: str, prop: str) -> float:
        return self.const(f"bolt_us.{size}.{prop}")


# Resistance and safety factors by limit state, as registry constant names (phi, Omega).
FACTORS: Mapping[str, tuple[str, str]] = {
    "bolt": ("rcsc2025.s5_1.phi", "rcsc2025.s5_1.omega"),            # J3.7 shear and tension
    "bearing": ("rcsc2025.s5_3.phi", "rcsc2025.s5_3.omega"),         # J3.11 bearing and tearout
    "slip_std": ("rcsc2025.s5_4.phi_std", "rcsc2025.s5_4.omega_std"),
    "slip_ovs": ("rcsc2025.s5_4.phi_ovs", "rcsc2025.s5_4.omega_ovs"),
    "slip_lsl": ("rcsc2025.s5_4.phi_lsl", "rcsc2025.s5_4.omega_lsl"),
    "weld": ("aisc360.j2_4.phi", "aisc360.j2_4.omega"),
    "tension_yield": ("aisc360.j4_1.phi_y", "aisc360.j4_1.omega_y"),
    "tension_rupture": ("aisc360.j4_1.phi_r", "aisc360.j4_1.omega_r"),
    "shear_yield": ("aisc360.j4_2.phi_y", "aisc360.j4_2.omega_y"),
    "shear_rupture": ("aisc360.j4_2.phi_r", "aisc360.j4_2.omega_r"),
    "block_shear": ("aisc360.j4_3.phi", "aisc360.j4_3.omega"),
    "compression": ("aisc360.j4_4.phi", "aisc360.j4_4.omega"),
    "flexure_yield": ("aisc360.j4_5.phi_y", "aisc360.j4_5.omega_y"),  # also F11 buckling, cope, seat
    "flexure_rupture": ("aisc360.j4_5.phi_r", "aisc360.j4_5.omega_r"),
    "j7": ("aisc360.j7.phi", "aisc360.j7.omega"),
    "j10_1": ("aisc360.j10_1.phi", "aisc360.j10_1.omega"),
    "j10_2": ("aisc360.j10_2.phi", "aisc360.j10_2.omega"),
    "j10_3": ("aisc360.j10_3.phi", "aisc360.j10_3.omega"),
    "j10_4": ("aisc360.j10_4.phi", "aisc360.j10_4.omega"),
    "j10_5": ("aisc360.j10_5.phi", "aisc360.j10_5.omega"),
    "j10_6": ("aisc360.j10_6.phi", "aisc360.j10_6.omega"),
}


# --- Small pure helpers ------------------------------------------------------------------

def _ratio(demand: float, available: float) -> float:
    if demand <= 0:
        return 0.0
    if available <= 0:
        return math.inf
    return demand / available


def _level_ratio(required: float, provided: float) -> float:
    """Ranked requirement (joint levels): 0 when nothing is required."""
    if required <= 0:
        return 0.0
    return math.inf if provided <= 0 else required / provided


def table_j2_4(t: float, reg: _Reg) -> float:
    """Table J2.4 minimum fillet size for the thinner part joined, t."""
    if t <= reg.const("aisc360.j2_2b.t1"):
        return reg.const("aisc360.j2_2b.w1")
    if t <= reg.const("aisc360.j2_2b.t2"):
        return reg.const("aisc360.j2_2b.w2")
    if t <= reg.const("aisc360.j2_2b.t3"):
        return reg.const("aisc360.j2_2b.w3")
    return reg.const("aisc360.j2_2b.w4")


def rect_net_z(t: float, depth: float, holes_y: Iterable[float], hole: float) -> float:
    """Plastic section modulus of a rectangular plate (t x depth) bending about its
    strong axis, less a column of holes of width `hole` (B4.3b width) centred at
    `holes_y` (measured from mid-depth). Exact for a symmetric hole pattern: the plastic
    neutral axis stays at mid-depth and each hole removes the first moment of its own
    area about it; a hole straddling the axis removes t (y^2 + h^2/4)."""
    z = t * depth * depth / 4.0
    for y in holes_y:
        y = abs(y)
        if y >= hole / 2:
            z -= t * hole * y
        else:
            z -= t * (y * y + hole * hole / 4.0)
    return z


def f11_mn(fy: float, E: float, t: float, depth: float, lb: float, cb: float) -> float:
    """AISC 360-22 Section F11 for a rectangular bar bent about its major axis:
    F11.1 yielding Mn = Mp = Fy Z <= 1.5 Fy Sx; F11.2 lateral-torsional buckling by
    Lb d / t^2 against 0.08 E / Fy and 1.9 E / Fy (Eqs F11-2 to F11-4)."""
    z = t * depth * depth / 4.0
    s = t * depth * depth / 6.0
    mp = min(fy * z, 1.5 * fy * s)
    my = fy * s
    ratio = lb * depth / (t * t)
    if ratio <= 0.08 * E / fy:
        return mp
    if ratio <= 1.9 * E / fy:
        return min(cb * (1.52 - 0.274 * ratio * fy / E) * my, mp)        # F11-3
    fcr = 1.9 * E * cb / ratio                                          # F11-4
    return min(fcr * s, mp)


def tee_section(bf: float, tf: float, tw: float, h: float) -> tuple[float, float]:
    """(elastic S to the stem tip, plastic Z) of a tee of total depth h: a flange bf x tf
    and a stem tw x (h - tf), fillets neglected (vocab: cope_buckling, "the tee's fillets
    are neglected")."""
    hs = h - tf
    af, aw = bf * tf, tw * hs
    a = af + aw
    # centroid from the flange's outer face
    yc = (af * tf / 2 + aw * (tf + hs / 2)) / a
    i = bf * tf ** 3 / 12 + af * (yc - tf / 2) ** 2 + tw * hs ** 3 / 12 + aw * (tf + hs / 2 - yc) ** 2
    s = i / max(yc, h - yc)
    # plastic neutral axis: equal areas
    if af >= a / 2:
        yp = (a / 2) / bf
        z = bf * yp ** 2 / 2 + bf * (tf - yp) ** 2 / 2 + aw * (tf - yp + hs / 2)
    else:
        yp = tf + (a / 2 - af) / tw          # inside the stem, from the flange face
        z = af * (yp - tf / 2) + tw * (yp - tf) ** 2 / 2 + tw * (h - yp) ** 2 / 2
    return s, z


# --- The connection's geometry, read from the Conn --------------------------------------

class _Ctx:
    def __init__(self, conn: Conn, design: Design, registry: Registry, case: str) -> None:
        self.conn = conn
        self.design = design
        self.reg = _Reg(registry)
        self.case = case
        self.lrfd = conn.basis == "lrfd"
        self.out: dict[str, list[tuple[str, float]]] = {}
        self.ranged: set[tuple[Fraction, Fraction]] = set()
        self.ends: dict[tuple[Fraction, Fraction], int] = {}

    # values
    def geo(self, value: object) -> float:
        """A design length in inches. A toleranced or parametric length must hold over its
        whole range: it is taken at the end `ends` names (0 low, 1 high), else at the
        middle, and recorded in `ranged` so `utilisations` can visit every end."""
        if isinstance(value, Fixed):
            iv = value.quantity.value
        elif isinstance(value, Input):
            iv = value.range.value
        elif isinstance(value, ParamRef):
            iv = self.design.params[value.name].range.value
        else:
            raise TypeError(f"{value!r} is not a length")
        if iv.lo == iv.hi:
            return _inch(iv.lo)
        key = (iv.lo, iv.hi)
        self.ranged.add(key)
        end = self.ends.get(key)
        return _inch((iv.lo + iv.hi) / 2 if end is None else (iv.lo, iv.hi)[end])

    def get(self, key: str, default: float | None = None) -> float | None:
        v = self.conn.get(key)
        return default if v is None else self.geo(v)

    def need(self, key: str) -> float:
        return self.geo(self.conn.attrs[key])

    def load(self, field: str) -> float:
        """The upper end of the load interval on this connection, in kips (0 if absent)."""
        case = self.design.loads[self.case]
        for e in case.entries:
            if e.target == (self.conn.name,) and e.field == field:
                rng = e.value.range if isinstance(e.value, Input) else self.design.params[e.value.name].range
                return _kip(rng.value.hi)
        return 0.0

    def avail(self, rn: float, limit: str) -> float:
        phi, omega = FACTORS[limit]
        return rn * self.reg.const(phi) if self.lrfd else rn / self.reg.const(omega)

    def add(self, mode: str, what: str, u: float) -> None:
        self.out.setdefault(mode, []).append((what, u))

    def check(self, mode: str, what: str, demand: float, rn: float, limit: str) -> None:
        self.add(mode, what, _ratio(demand, self.avail(rn, limit)))


# --- Bolts ------------------------------------------------------------------------------

class Ply:
    """One connected element a bolt column passes through, as the bearing and tearout
    check sees it: thickness, Fu, hole type, multiplicity (two angles), the direction it
    tears in, and the distance from the first bolt in that direction to the free edge it
    tears toward (None when there is no edge in that direction)."""

    def __init__(self, name: str, t: float, fu: float, hole: str, edge: float | None, down: bool,
                 count: int = 1) -> None:
        self.name, self.t, self.fu, self.hole, self.edge, self.count = name, t, fu, hole, edge, count
        self.down = down    # tears toward its bottom edge (else toward its top edge)
        # A part loaded downward that the bolts hold up (a plate welded to the beam, an
        # angle or tee leg on the support, a seat) tears up; a part that holds the bolts up
        # (a tab welded to the support, the support itself) tears down.


class BoltSet:
    """A bolt group: `rows` x `cols` bolts, pitch s and gauge g, through `plies`."""

    def __init__(self, ctx: _Ctx, bolts: Bolts, rows: int, cols: int, s: float, g: float,
                 plies: list[Ply], planes: int, eccentricity: float | None, label: str) -> None:
        self.ctx, self.b, self.rows, self.cols, self.s, self.g = ctx, bolts, rows, cols, s, g
        self.plies, self.planes, self.e, self.label = plies, planes, eccentricity, label
        reg = ctx.reg
        self.d = reg.bolt(bolts.size, "d")
        self.ab = math.pi * self.d ** 2 / 4.0
        mat = bolts.group
        self.fnt = reg.stated(mat, "Fnt")
        fnv_x = reg.r.materials[mat].props.get("Fnv_X")
        self.fnv = reg.stated(mat, "Fnv_X") if bolts.threads == "excluded" and fnv_x is not None else reg.stated(mat, "Fnv_N")
        if bolts.fillers != "none":
            self.fnv *= 0.85        # J5.2(a)'s least factor: the grammar gives no filler thickness
        self.n = rows * cols

    # hole dimension along the force (vertical) and across it (horizontal), J3.3
    def hole_dims(self, hole: str) -> tuple[float, float]:
        r = self.ctx.reg
        size = self.b.size
        std = r.bolt(size, "std")
        return {
            "std": (std, std),
            "ovs": (r.bolt(size, "ovs"), r.bolt(size, "ovs")),
            "ssl": (r.bolt(size, "ssl_w"), r.bolt(size, "ssl_l")),           # slot across the force
            "ssl_parallel": (r.bolt(size, "ssl_l"), r.bolt(size, "ssl_w")),
            "lsl": (r.bolt(size, "lsl_w"), r.bolt(size, "lsl_l")),
            "lsl_parallel": (r.bolt(size, "lsl_l"), r.bolt(size, "lsl_w")),
        }[hole]

    def bearing_rn(self, ply: Ply, row: int) -> float:
        """J3.11a nominal bearing or tearout strength of one bolt hole in `ply`, row
        counted from the ply's free edge in the force direction (0 = the edge bolt)."""
        hv, _ = self.hole_dims(ply.hole)
        if row == 0:
            lc = None if ply.edge is None else ply.edge - hv / 2
        else:
            lc = self.s - hv
        deformation = self.ctx.conn.attrs.get("deformation", "considered")
        t, fu, d = ply.t, ply.fu, self.d
        if ply.hole == "lsl":
            # J3.11a(2): long slot perpendicular to the force, Eqs J3-6e and J3-6f
            bear, tear = 2.0 * d * t * fu, (None if lc is None else 1.0 * lc * t * fu)
        elif deformation == "not_considered":
            bear, tear = 3.0 * d * t * fu, (None if lc is None else 1.5 * lc * t * fu)   # J3-6b, J3-6d
        else:
            bear, tear = 2.4 * d * t * fu, (None if lc is None else 1.2 * lc * t * fu)   # J3-6a, J3-6c
        rn = bear if tear is None else min(bear, tear)
        return rn * ply.count

    def bolt_available(self, plies_rows: Mapping[str, int]) -> float:
        """Effective available strength of one bolt (J3.7 User Note): the least of its
        shear strength and its bearing or tearout strength in each ply."""
        ctx = self.ctx
        shear = ctx.avail(self.fnv * self.ab * self.planes, "bolt")
        out = shear
        for ply in self.plies:
            out = min(out, ctx.avail(self.bearing_rn(ply, plies_rows[ply.name]), "bearing"))
        return out

    def positions(self) -> list[tuple[int, int, float, float]]:
        """(row from bottom, column from the support, x, y) about the centroid."""
        out = []
        for i in range(self.rows):
            for j in range(self.cols):
                out.append((i, j, (j - (self.cols - 1) / 2) * self.g, (i - (self.rows - 1) / 2) * self.s))
        return out

    def row_from_edge(self, ply: Ply, i: int) -> int:
        """Row index counted from the ply's free edge: plies tearing downward count from
        the bottom row, plies tearing upward from the top row."""
        return i if ply.down else self.rows - 1 - i

    def elastic_forces(self, p: float) -> list[tuple[int, int, float, float]]:
        """Manual Part 7 elastic method: (row, col, fx, fy) on each bolt for a vertical
        force p at eccentricity e from the centroid, measured toward the side away from
        column 0 when positive. Direct shear p/n plus the torsional share M r / J."""
        e = self.e or 0.0
        pts = self.positions()
        j = sum(x * x + y * y for _, _, x, y in pts)
        m = p * e
        out = []
        for i, c, x, y in pts:
            fx = m * y / j if j > 0 else 0.0
            fy = p / self.n + (m * x / j if j > 0 else 0.0)
            out.append((i, c, fx, fy))
        return out

    def check_bolts(self, p: float, what: str) -> None:
        ctx = self.ctx
        strengths = []
        for i, c, _, _ in self.positions():
            rows = {ply.name: self.row_from_edge(ply, i) for ply in self.plies}
            strengths.append(self.bolt_available(rows))
        if self.e is None:
            ctx.add("bolts", f"{self.label}: bolt shear, bearing and tearout summed over the group", _ratio(p, sum(strengths)))
        else:
            rmax = max(math.hypot(fx, fy) for _, _, fx, fy in self.elastic_forces(p))
            ctx.add("bolts", f"{self.label}: most loaded bolt by the elastic method against the weakest bolt",
                    _ratio(rmax, min(strengths)))

    def block_demand(self, p: float, rows: Iterable[int], cols: Iterable[int]) -> float:
        rows, cols = set(rows), set(cols)
        if self.e is None:
            return p * len(rows) * len(cols) / self.n
        fx = fy = 0.0
        for i, c, x, y in self.elastic_forces(p):
            if i in rows and c in cols:
                fx += x
                fy += y
        return math.hypot(fx, fy)

    def max_force(self, p: float) -> float:
        if self.e is None:
            return p / self.n
        return max(math.hypot(fx, fy) for _, _, fx, fy in self.elastic_forces(p))

    def elastic_moment_coefficient(self) -> float:
        """C' of the elastic method for a pure moment: M = rn C', C' = sum r^2 / r_max."""
        pts = self.positions()
        j = sum(x * x + y * y for _, _, x, y in pts)
        rmax = max(math.hypot(x, y) for _, _, x, y in pts)
        return j / rmax


# --- Shared element checks ----------------------------------------------------------------

def _holes(conn: Conn, ply: str) -> str:
    return conn.attrs.get("holes", {}).get(ply, "std")


def shear_yield(ctx: _Ctx, element: str, v: float, fy: float, agv: float) -> None:
    ctx.check("shear_yield", f"{element}: shear yielding of the gross section (J4.2a)", v, 0.6 * fy * agv, "shear_yield")


def shear_rupture(ctx: _Ctx, element: str, v: float, fu: float, anv: float) -> None:
    ctx.check("shear_rupture", f"{element}: shear rupture of the net section (J4.2b)", v, 0.6 * fu * anv, "shear_rupture")


def block_shear(ctx: _Ctx, element: str, group: BoltSet, p: float, t: float, fy: float, fu: float, hole: str,
                lev: float, leh: float, down: bool, cols_from_edge: list[int], planes: int = 1) -> None:
    """J4.3 over every block of the first k rows (from the free edge the ply tears toward)
    and the first j columns (from its free side edge): one shear plane through the block's
    inner column, one tension plane from it to the side edge. `cols_from_edge` lists the
    group's column indices in order from the side edge. `planes` multiplies the areas
    (two angles). Ubs = 1 for a block of one column, 0.5 for more (vocab block_shear)."""
    hv, hh = group.hole_dims(hole)
    hv1, hh1 = hv + SIXTEENTH, hh + SIXTEENTH
    for k in range(1, group.rows + 1):
        rows = list(range(k)) if down else list(range(group.rows - k, group.rows))
        for jn in range(1, len(cols_from_edge) + 1):
            agv = (lev + (k - 1) * group.s) * t * planes
            anv = agv - (k - 0.5) * hv1 * t * planes
            ant = (leh + (jn - 1) * group.g - (jn - 0.5) * hh1) * t * planes
            ubs = 1.0 if jn == 1 else 0.5
            rn = min(0.6 * fu * anv + ubs * fu * ant, 0.6 * fy * agv + ubs * fu * ant)
            demand = group.block_demand(p, rows, cols_from_edge[:jn])
            ctx.check("block_shear", f"{element}: block of {k} row(s) and {jn} column(s) (J4.3)", demand, rn, "block_shear")


def edges(ctx: _Ctx, element: str, t: float, size: str, named: Mapping[str, float]) -> None:
    """J3.5 minimum and J3.6 maximum edge distances of one element."""
    emin = ctx.reg.bolt(size, "edge_min")
    lim_t = ctx.reg.const("aisc360.j3_6.edge_t") * t
    lim = ctx.reg.const("aisc360.j3_6.edge_max")
    for name, e in named.items():
        ctx.add("edge_min", f"{element}: {name} edge distance at least Table J3.4's (J3.5)", _ratio(emin, e))
        ctx.add("edge_max", f"{element}: {name} edge distance at most 12 t (J3.6)", _ratio(e, lim_t))
        ctx.add("edge_max", f"{element}: {name} edge distance at most 6 in (J3.6)", _ratio(e, lim))


def spacing(ctx: _Ctx, label: str, bolts: Bolts, thinner: float, named: Mapping[str, float]) -> None:
    d = ctx.reg.bolt(bolts.size, "d")
    ratio = ctx.reg.const("aisc360.j3_4.spacing_ratio")
    weathering = ctx.conn.attrs.get("weathering", "no") == "yes"
    k_t = ctx.reg.const("aisc360.j3_6.weathering_pitch_t" if weathering else "aisc360.j3_6.pitch_t")
    k_max = ctx.reg.const("aisc360.j3_6.weathering_pitch_max" if weathering else "aisc360.j3_6.pitch_max")
    for name, s in named.items():
        ctx.add("spacing_min", f"{label}: {name} at least 2-2/3 d (J3.4)", _ratio(ratio * d, s))
        ctx.add("spacing_max", f"{label}: {name} at most the thickness multiple (J3.6)", _ratio(s, k_t * thinner))
        ctx.add("spacing_max", f"{label}: {name} at most the absolute limit (J3.6)", _ratio(s, k_max))


JOINT_LEVEL = {"snug": "rcsc2025.joint_level.snug", "pretensioned": "rcsc2025.joint_level.pretensioned",
               "slip_critical": "rcsc2025.joint_level.slip_critical"}
NEEDS_SLIP = ("ovs", "ssl_parallel", "lsl_parallel")


def joint_type(ctx: _Ctx, label: str, bolts: Bolts, holes: Iterable[str], tension: bool) -> None:
    """RCSC 4.1/4.2 and J3.2 (vocab joint_type): at least snug-tight; Group 150 and 200
    bolts in tension pretensioned. The holes that need a slip-critical joint are hole_use's."""
    reg = ctx.reg
    need = "snug"
    if tension and bolts.group in ("bolt_group.150", "bolt_group.200"):
        need = "pretensioned"
    ctx.add("joint_type", f"{label}: the joint is at least {need}",
            _level_ratio(reg.const(JOINT_LEVEL[need]), reg.const(JOINT_LEVEL[bolts.joint])))


def hole_use(ctx: _Ctx, element: str, hole: str, bolts: Bolts) -> None:
    """J3.3: oversized holes and slots parallel to the force only in slip-critical joints."""
    reg = ctx.reg
    need = "slip_critical" if hole in NEEDS_SLIP else "snug"
    ctx.add("hole_use", f"{element}: {hole} holes in a joint of the type they need (J3.3)",
            _level_ratio(reg.const(JOINT_LEVEL[need]), reg.const(JOINT_LEVEL[bolts.joint])))


def long_slots(ctx: _Ctx, label: str, holes: Iterable[str]) -> None:
    """J3.3(f): long-slotted holes in only one of the connected parts at a faying surface.
    The parts are the plies the bolt group passes through; the count of plies with long
    slots (either direction) against the registry's limit."""
    count = sum(1 for h in holes if h in ("lsl", "lsl_parallel"))
    ctx.add("hole_use", f"{label}: long slots in at most one part at the faying surface (J3.3)",
            _ratio(count, ctx.reg.const("aisc360.j3_3.long_slot_plies")))


def clearance(ctx: _Ctx, label: str, bolts: Bolts, provided: float, what: str) -> None:
    """Manual Part 7 tightening clearance: half the heavy hex nut's width across corners,
    F / sqrt(3), plus the socket allowance, from the bolt's centre to the obstruction."""
    f = ctx.reg.bolt(bolts.size, "nut_F")
    need = f / math.sqrt(3.0) + ctx.reg.const("aisc_manual.clearance.socket")
    ctx.add("clearance", f"{label}: room to tighten, clear of {what}", _ratio(need, provided))


def slip(ctx: _Ctx, label: str, group: BoltSet, p: float, holes: Iterable[str], tension: float = 0.0) -> None:
    """J3.9 Eq J3-4 per bolt, with ksc of Eq J3-5 when tension acts, the resistance
    factor of the worst hole type among the plies (J3.9(a)-(c)). An eccentric group's
    most loaded bolt (elastic method) is compared with one bolt's resistance."""
    reg, b = ctx.reg, group.b
    holes = list(holes)
    if any(h in ("lsl", "lsl_parallel") for h in holes):
        limit = "slip_lsl"
    elif any(h in ("ovs", "ssl_parallel") for h in holes):
        limit = "slip_ovs"
    else:
        limit = "slip_std"
    mu = reg.const("rcsc2025.s5_4.mu_a" if b.surface == "class_a" else "rcsc2025.s5_4.mu_b")
    du = reg.const("rcsc2025.s5_4.Du")
    hf = reg.const("rcsc2025.s5_4.hf_two" if b.fillers == "two" else "rcsc2025.s5_4.hf_one")
    tb = reg.bolt(b.size, "Tm_g120" if b.group == "bolt_group.120" else "Tm_g150")
    ksc = 1.0
    if tension > 0:
        t = tension if ctx.lrfd else 1.5 * tension
        ksc = max(1.0 - t / (du * tb * group.n), 0.0)
    rn = mu * du * hf * tb * group.planes * ksc
    ctx.check("slip", f"{label}: slip resistance per bolt (J3.9)", group.max_force(p), rn, limit)


def fillet_capacity_per_inch(ctx: _Ctx, weld: Weld) -> float:
    """Available strength of one fillet per inch, Eq J2-4 with kds = 1:
    0.60 FEXX times the throat 0.707 w (Table J2.5)."""
    fexx = ctx.reg.stated(weld.electrode, "FEXX")
    w = ctx.geo(weld.size)
    return ctx.avail(0.6 * fexx * w / math.sqrt(2.0), "weld")


def base_metal(ctx: _Ctx, element: str, q: float, fu: float, t: float, label: str) -> None:
    """J2.4(a) with J4.2(b): the base metal along a fusion face in shear rupture,
    0.60 Fu t per inch, against the weld force per inch it carries."""
    ctx.check("weld_base_metal", f"{label}: {element} base metal in shear rupture along the weld (J2.4a)", q,
              0.6 * fu * t, "shear_rupture")


def fillet_size(ctx: _Ctx, label: str, weld: Weld, thinner: float, length: float) -> None:
    w = ctx.geo(weld.size)
    ctx.add("fillet_size", f"{label}: minimum fillet size for the thinner part (J2.2b, Table J2.4)",
            _ratio(table_j2_4(thinner, ctx.reg), w))
    ctx.add("fillet_size", f"{label}: fillet at least four times its size long (J2.2b)",
            _ratio(ctx.reg.const("aisc360.j2_2b.length_ratio") * w, length))


def lines_out_of_plane(p: float, e: float, length: float, lines: int) -> float:
    """Elastic method on weld line properties for `lines` parallel vertical lines of
    `length` in the support's face, the force p parallel to them at an out-of-plane
    eccentricity e: direct shear p / (lines L) and bending M c / I with I = lines L^3/12
    per unit throat, combined at the line's end. For one line this is also the in-plane
    result for a force at e in the line's plane (6 M / L^2 either way)."""
    fv = p / (lines * length)
    fb = p * e * (length / 2) / (lines * length ** 3 / 12.0)
    return math.hypot(fv, fb)


def c_shape_in_plane(p: float, e: float, length: float, ret: float) -> float:
    """Elastic method (Manual Part 8, Companion Example II.A-27) on a C-shaped weld: a
    vertical line of `length` with returns `ret` at both ends toward the load, the
    force p vertical at e from the vertical line. Centroid xl = ret^2 / (2 ret + L) from
    the vertical line; Ip = Ix + Iy per unit throat; the most stressed points are the
    returns' tips, where the torsional and direct vertical components add."""
    kl = ret
    total = length + 2 * kl
    xl = kl * kl / total
    ex = e - xl
    ix = length ** 3 / 12.0 + 2 * kl * (length / 2) ** 2
    iy = 2 * (kl ** 3 / 12.0 + kl * (kl / 2 - xl) ** 2) + length * xl ** 2
    ip = ix + iy
    m = p * ex
    best = 0.0
    for cx, cy in ((kl - xl, length / 2), (-xl, length / 2)):
        rx = m * cy / ip
        ry = p / total + m * cx / ip
        best = max(best, math.hypot(rx, ry))
    return best


# --- J10 -------------------------------------------------------------------------------

def j10_web_yielding(ctx: _Ctx, element: str, member: dict, fy: float, lb: float, force: float, at_end: bool) -> None:
    k, tw = member["kdes"], member["tw"]
    if at_end:
        ctx.check("web_local_yielding", f"{element}: web local yielding within d of the member end (J10.2)", force,
                  fy * tw * (2.5 * k + lb), "j10_2")
    else:
        ctx.check("web_local_yielding", f"{element}: web local yielding away from the member end (J10.2)", force,
                  fy * tw * (5 * k + lb), "j10_2")


def j10_crippling(ctx: _Ctx, element: str, member: dict, fy: float, lb: float, force: float, at_end: bool) -> None:
    d, tw, tf = member["d"], member["tw"], member["tf"]
    root = math.sqrt(ctx.reg.E * fy * tf / tw)
    r = (tw / tf) ** 1.5
    if not at_end:
        rn = 0.80 * tw * tw * (1 + 3 * (lb / d) * r) * root                     # J10-4
    elif lb / d <= 0.2:
        rn = 0.40 * tw * tw * (1 + 3 * (lb / d) * r) * root                     # J10-5a
    else:
        rn = 0.40 * tw * tw * (1 + (4 * lb / d - 0.2) * r) * root               # J10-5b
    ctx.check("web_crippling", f"{element}: web local crippling (J10.3)", force, rn, "j10_3")


# --- Kinds ------------------------------------------------------------------------------

def _support(ctx: _Ctx) -> tuple[dict, float, float, float, str]:
    """The support member: (shape props, Fy, Fu, thickness of the connected face, face)."""
    sup: Member = ctx.conn.attrs["support"]
    s = ctx.reg.w_shape(sup.shape)
    fy, fu = ctx.reg.steel(sup.grade)
    return s, fy, fu, (s["tf"] if sup.face == "flange" else s["tw"]), sup.face


def _support_clearance(ctx: _Ctx, g_half: float, sup: dict, face: str) -> tuple[float, str]:
    """Distance from a support-side bolt at g_half from the support's centreline to the
    obstruction on the far side of the connected face: the web of a column connected on
    its flange, or a flange of a member connected on its web."""
    if face == "flange":
        return g_half - sup["tw"] / 2, "the support web"
    return (sup["d"] - 2 * sup["tf"]) / 2 - g_half, "the support flanges"


class _Beam:
    """The supported beam's web at the connection."""

    def __init__(self, ctx: _Ctx) -> None:
        beam: Member = ctx.conn.attrs["beam"]
        self.shape = ctx.reg.w_shape(beam.shape)
        self.fy, self.fu = ctx.reg.steel(beam.grade)
        self.d, self.tw = self.shape["d"], self.shape["tw"]
        cope: Cope | None = ctx.conn.get("cope")
        self.cope = cope
        if cope is None:
            self.dct = self.dcb = 0.0
            self.c = 0.0
        else:
            self.dct = ctx.geo(cope.depth)
            self.dcb = (ctx.geo(cope.bottom) if cope.bottom is not None else self.dct) if cope.flanges == "both" else 0.0
            self.c = ctx.geo(cope.length)
        self.h = self.d - self.dct - self.dcb      # remaining web depth at the cope

    def top_edge(self, top: float) -> float | None:
        """Distance from the top bolt to the edge its hole tears toward in the web: the
        cope's horizontal cut for a coped beam (top - dct, with `top` measured from the
        beam's top), none for an uncoped beam, whose top bolt cannot tear out through the
        flange (path.py, role "web")."""
        return None if self.cope is None else top - self.dct

    def web_checks(self, ctx: _Ctx, v: float, rows: int, hole: str | None, group: BoltSet | None) -> None:
        """Shear yielding of the beam web's gross section (d - copes) tw (Companion II.A-6,
        II.A-28A: Agv = hc tw), and with bolts its net section through one line of holes."""
        shear_yield(ctx, "beam web", v, self.fy, self.h * self.tw)
        if group is not None and hole is not None:
            hv, _ = group.hole_dims(hole)
            shear_rupture(ctx, "beam web", v, self.fu, (self.h - rows * (hv + SIXTEENTH)) * self.tw)

    def cope_buckling(self, ctx: _Ctx, v: float, setback: float) -> None:
        """Manual Part 9: the moment at the cope face, R (c + setback) (vocab: e = c +
        setback), against Mn of the coped section.
        Top cope only: the remaining tee (Eqs 9-14 to 9-20), lambda = hc / tw,
        lambda_p = 0.475 sqrt(k1 E / Fy), k1 = f k >= 1.61 with
          f = 2 c/d (c/d <= 1) or 1 + c/d (c/d > 1),
          k = 2.2 (hc/c)^1.65 (c/hc <= 1) or 2.2 hc/c (c/hc > 1);
        Mn = Mp (lambda <= lambda_p), Mp - (Mp - My)(lambda/lambda_p - 1) (to 2 lambda_p),
        Fcr Sc with Fcr = 0.903 E k1 / lambda^2 above (Manual Eqs 9-10 to 9-13).
        Both flanges coped: Section F11 on the remaining web as a rectangular bar,
        d = hc, Lb = c, Cb = [3 + ln(Lb/d)] (1 - dct/d) >= 1.84 with d the full depth (Manual
        Eq 9-21; Companion II.A-7 prints 1.94 for c = 9.5 in, d = 16.0 in, dct = 3.5 in)."""
        if self.cope is None:
            return
        e = self.c + setback
        m = v * e
        E = ctx.reg.E
        fy = self.fy
        if self.cope.flanges == "top":
            hc, c, d, tw = self.h, self.c, self.d, self.tw
            f = 2 * c / d if c / d <= 1.0 else 1 + c / d
            k = 2.2 * (hc / c) ** 1.65 if c / hc <= 1.0 else 2.2 * hc / c
            k1 = max(f * k, 1.61)
            sc, zc = tee_section(self.shape["bf"], self.shape["tf"], tw, hc)
            mp, my = fy * zc, fy * sc
            lam = hc / tw
            lam_p = 0.475 * math.sqrt(k1 * E / fy)
            if lam <= lam_p:
                mn = mp
            elif lam <= 2 * lam_p:
                mn = mp - (mp - my) * (lam / lam_p - 1)
            else:
                mn = 0.903 * E * k1 / lam ** 2 * sc
        else:
            hc = self.h
            cb = max((3 + math.log(self.c / self.d)) * (1 - self.dct / self.d), 1.84)
            mn = f11_mn(fy, E, self.tw, hc, self.c, cb)
        ctx.check("cope_buckling", "beam web: flexural yielding and local buckling at the cope (Manual Part 9)", m, mn,
                  "flexure_yield")


def _beam_web_ply(ctx: _Ctx, beam: _Beam, top: float) -> Ply:
    return Ply("beam", beam.tw, beam.fu, _holes(ctx.conn, "beam"), beam.top_edge(top), down=False)


def _shear_tab(ctx: _Ctx, modes: set[str]) -> None:
    conn = ctx.conn
    v = ctx.load("shear")
    beam = _Beam(ctx)
    sup, sfy, sfu, st, face = _support(ctx)
    plate: PlateSpec = conn.attrs["plate"]
    tp = ctx.geo(plate.thickness)
    pfy, pfu = ctx.reg.steel(plate.grade)
    bolts: Bolts = conn.attrs["bolts"]
    n, s = conn.attrs["rows"], ctx.need("pitch")
    nc = conn.attrs.get("columns", 1)
    g = ctx.get("gauge", 0.0) if nc > 1 else 0.0
    lev, leh_p, a, leh_b, top = (ctx.need(k) for k in ("edge_vertical", "plate_edge", "bolt_line", "beam_edge", "top"))
    length = 2 * lev + (n - 1) * s
    setback = ctx.get("setback", a - leh_b)
    # Bolt group eccentricity: the declared eccentricity, else the distance from the weld
    # line to the group's centroid, a + (cols - 1) g / 2 (Companion II.A-19A: e = 9 + 3/2);
    # for one column e = a, the deck's stated choice for a conventional tab.
    e = ctx.get("eccentricity", a + (nc - 1) * g / 2)
    hp, hb = _holes(conn, "plate"), _holes(conn, "beam")
    plate_ply = Ply("plate", tp, pfu, hp, lev, down=True)
    web_ply = _beam_web_ply(ctx, beam, top)
    group = BoltSet(ctx, bolts, n, nc, s, g, [plate_ply, web_ply], 1, e, "beam side")
    weld: Weld = conn.attrs["weld"]
    w = ctx.geo(weld.size)

    # plate
    hv_p, _ = group.hole_dims(hp)
    shear_yield(ctx, "plate", v, pfy, length * tp)
    shear_rupture(ctx, "plate", v, pfu, (length - n * (hv_p + SIXTEENTH)) * tp)
    # plate blocks tear downward to the bottom edge and out to the plate's free side edge;
    # columns counted from that edge (the farthest from the support first)
    block_shear(ctx, "plate", group, v, tp, pfy, pfu, hp, lev, leh_p, True, list(range(nc - 1, -1, -1)))
    edges(ctx, "plate", tp, bolts.size, {"plate top and bottom": lev, "plate side": leh_p})
    hole_use(ctx, "plate", hp, bolts)
    # beam web
    beam.web_checks(ctx, v, n, hb, group)
    web_edges = {"beam end": leh_b}
    if beam.cope is not None:
        web_edges["cope"] = top - beam.dct
        # the coped web's blocks tear upward to the cope and out to the beam end; columns
        # counted from the beam end (the support side first)
        block_shear(ctx, "beam web", group, v, beam.tw, beam.fy, beam.fu, hb, top - beam.dct, leh_b - UNDERRUN, False,
                    list(range(nc)))
        beam.cope_buckling(ctx, v, setback)
    edges(ctx, "beam web", beam.tw, bolts.size, web_edges)
    hole_use(ctx, "beam web", hb, bolts)
    # bolts
    group.check_bolts(v, "beam side")
    pitch_names = {"pitch": s, **({"gauge": g} if nc > 1 else {})}
    spacing(ctx, "beam side", bolts, min(tp, beam.tw), pitch_names)
    joint_type(ctx, "beam side", bolts, (hp, hb), tension=False)
    long_slots(ctx, "beam side", (hp, hb))
    clearance(ctx, "beam side", bolts, a, "the support face")
    if bolts.joint == "slip_critical":
        slip(ctx, "beam side", group, v, (hp, hb))
    # plate flexure at the bolt line nearest the support, M = V a (Companion II.A-19A:
    # Mr = Vu a, a to the first bolt line); rupture on the net section through that line
    m = v * a
    ctx.check("flexural_yield", "plate: flexural yielding of the gross section (J4.5)", m, pfy * tp * length ** 2 / 4,
              "flexure_yield")
    ys = [(i - (n - 1) / 2) * s for i in range(n)]
    znet = rect_net_z(tp, length, ys, hv_p + SIXTEENTH)
    ctx.check("flexural_rupture", "plate: flexural rupture of the net section through the bolt holes (J4.5)", m,
              pfu * znet, "flexure_rupture")
    form = conn.attrs.get("form", "conventional")
    if form == "conventional":
        # Manual Part 10 (vocab ductility): t <= d/2 + 1/16 for the plate or the beam web
        # (either suffices, so the thinner one), weld >= 5/8 tp
        d = group.d
        ctx.add("ductility", "plate: plate or beam web at most d/2 + 1/16 in thick", _ratio(min(tp, beam.tw), d / 2 + SIXTEENTH))
        ctx.add("ductility", "plate: fillet at least 5/8 of the plate thickness", _ratio(5 / 8 * tp, w))
        # Companion II.A-17A: Leh >= 2d on the plate and on the beam web
        ctx.add("ductility", "plate: Leh at least 2d", _ratio(2 * d, leh_p))
        ctx.add("ductility", "beam web: Leh at least 2d", _ratio(2 * d, leh_b))
    else:
        # Section F11 with Lb = a, Cb = 1.84, against M = V a at the weld line (Companion
        # II.A-19A: Mr = Vu a with a = 9 in)
        mn = f11_mn(pfy, ctx.reg.E, tp, length, a, 1.84)
        ctx.check("plate_buckling", "plate: lateral-torsional buckling (F11)", m, mn, "flexure_yield")
        # Manual Part 10 extended configuration (Companion II.A-19A, Manual Eq 10-8):
        # (Vr/Vc)^2 + (Mr/Mc)^2 <= 1 with Vc the plate's shear yielding and Mc its
        # flexural yielding. Reported as the factor on the load that reaches the curve,
        # sqrt of the left side, so it scales with the load like every other utilisation.
        vc = ctx.avail(0.6 * pfy * length * tp, "shear_yield")
        mc = ctx.avail(pfy * tp * length ** 2 / 4, "flexure_yield")
        ctx.add("flexural_yield", "plate: shear and flexural yielding interaction (Manual Eq 10-8)",
                math.hypot(v / vc, m / mc))
        cprime = group.elastic_moment_coefficient()
        mmax = group.fnv / 0.90 * group.ab * cprime                 # Manual Eq 10-7, elastic C'
        tmax = 6 * mmax / (pfy * length ** 2)                       # Manual Eq 10-6
        ctx.add("extended_ductility", "plate: at most tmax", _ratio(tp, tmax))
        ctx.add("extended_ductility", "plate: fillet at least 5/8 of the plate thickness", _ratio(5 / 8 * tp, w))
    # weld: fillets on `sides` faces of the plate along its length, longitudinal shear
    q = fillet_capacity_per_inch(ctx, weld)
    ctx.add("weld", "plate to support: fillet welds in longitudinal shear (J2.4)", _ratio(v, q * length * weld.sides))
    per_fillet = v / (weld.sides * length)
    # the plate carries every fillet on it (Manual Eq 9-3 basis); the support face carries
    # each fillet separately (Companion II.A-17A: tmin = 3.09 D / Fu for the column flange)
    base_metal(ctx, "plate", per_fillet * weld.sides, pfu, tp, "plate to support")
    base_metal(ctx, f"support {face}", per_fillet, sfu, st, "plate to support")
    fillet_size(ctx, "plate to support", weld, min(tp, st), length)


def _angles_geometry(ctx: _Ctx, spec: AngleSpec) -> tuple[float, float, float]:
    """(leg on the beam web, leg on the support, thickness). `outstanding` names the leg
    that lies on the support."""
    long, short, t = ctx.reg.angle(spec.shape)
    out = long if spec.outstanding == "long" else short
    beam_leg = short if spec.outstanding == "long" else long
    return beam_leg, out, t


def _angle_kind(ctx: _Ctx, modes: set[str], double: bool) -> None:
    conn = ctx.conn
    v = ctx.load("shear")
    beam = _Beam(ctx)
    sup, sfy, sfu, st, face = _support(ctx)
    key = "angles" if double else "angle"
    spec: AngleSpec = conn.attrs[key]
    leg_b, leg_o, t = _angles_geometry(ctx, spec)
    afy, afu = ctx.reg.steel(spec.grade)
    count = 2 if double else 1
    bolts: Bolts = conn.attrs["bolts"]
    n, s = conn.attrs["rows"], ctx.need("pitch")
    lev, leh_b, top, gb = (ctx.need(k) for k in ("edge_vertical", "beam_edge", "top", "beam_gauge"))
    length = 2 * lev + (n - 1) * s
    ha, hb, hs = _holes(conn, key), _holes(conn, "beam"), _holes(conn, "support")
    # Beam side. Double angles: the bolts in double shear through two angles (each a ply
    # bearing half), concentric (Companion II.A-1A). A single angle: single shear, the
    # group eccentric by the beam-side gauge from the support face (vocab: elastic method).
    angle_ply = Ply(key, t, afu, ha, lev, down=True, count=count)
    web_ply = _beam_web_ply(ctx, beam, top)
    e_beam = None if double else gb
    group_b = BoltSet(ctx, bolts, n, 1, s, 0.0, [angle_ply, web_ply], 2 if double else 1, e_beam, "beam side")
    hv_a, _ = group_b.hole_dims(ha)
    shear_yield(ctx, key, v, afy, count * length * t)
    shear_rupture(ctx, key, v, afu, count * (length - n * (hv_a + SIXTEENTH)) * t)
    block_shear(ctx, key, group_b, v, t, afy, afu, ha, lev, leg_b - gb, True, [0], planes=count)
    edges(ctx, key, t, bolts.size, {"angle top and bottom": lev, "angle toe": leg_b - gb})
    hole_use(ctx, key, ha, bolts)
    beam.web_checks(ctx, v, n, hb, group_b)
    web_edges = {"beam end": leh_b}
    setback = ctx.get("setback", 0.5)
    if beam.cope is not None:
        web_edges["cope"] = top - beam.dct
        block_shear(ctx, "beam web", group_b, v, beam.tw, beam.fy, beam.fu, hb, top - beam.dct, leh_b - UNDERRUN, False, [0])
        beam.cope_buckling(ctx, v, setback)
    edges(ctx, "beam web", beam.tw, bolts.size, web_edges)
    hole_use(ctx, "beam web", hb, bolts)
    group_b.check_bolts(v, "beam side")
    spacing(ctx, "beam side", bolts, min(t, beam.tw), {"pitch": s})
    joint_type(ctx, "beam side", bolts, (ha, hb), tension=False)
    long_slots(ctx, "beam side", (ha, hb))
    clearance(ctx, "beam side", bolts, gb - t, "the outstanding leg")
    if bolts.joint == "slip_critical":
        slip(ctx, "beam side", group_b, v, (ha, hb))
    if conn.get("support_side") == "bolted":
        g = ctx.need("support_gauge")
        # Double angles: support_gauge runs across the two bolt lines, so each angle's
        # gauge from its heel is (g - tw)/2 (lower.py). One angle: heel to bolt line.
        ga = (g - beam.tw) / 2 if double else g
        out_ply = Ply(key, t, afu, ha, lev, down=False)
        sup_ply = Ply("support", st, sfu, hs, None, down=True)
        # Single angle: the support-side group is eccentric by g + tw/2 (Companion
        # II.A-28A, e = 1-3/4 + 0.300/2), elastic method; double angles concentric.
        e_sup = None if double else ga + beam.tw / 2
        group_s = BoltSet(ctx, bolts, n, count, s, g, [out_ply, sup_ply], 1, e_sup, "support side")
        el = f"{key} outstanding"
        shear_yield(ctx, el, v, afy, count * length * t)
        shear_rupture(ctx, el, v, afu, count * (length - n * (hv_a + SIXTEENTH)) * t)
        # each angle's leg tears upward to its top edge and out to its toe; for double
        # angles both legs together against the whole force, one column each
        if double:
            one = BoltSet(ctx, bolts, n, 1, s, 0.0, [out_ply, sup_ply], 1, None, "support side")
            block_shear(ctx, el, one, v, t, afy, afu, ha, lev, leg_o - ga, False, [0], planes=2)
        else:
            block_shear(ctx, el, group_s, v, t, afy, afu, ha, lev, leg_o - ga, False, [0])
        edges(ctx, el, t, bolts.size, {"outstanding top and bottom": lev, "outstanding toe": leg_o - ga})
        hole_use(ctx, el, ha, bolts)
        hole_use(ctx, f"support {face}", hs, bolts)
        group_s.check_bolts(v, "support side")
        names = {"pitch": s, **({"gauge": g} if double else {})}
        spacing(ctx, "support side", bolts, min(t, st), names)
        joint_type(ctx, "support side", bolts, (ha, hs), tension=False)
        long_slots(ctx, "support side", (ha, hs))
        g_half = g / 2 if double else ga + beam.tw / 2
        prov, what = _support_clearance(ctx, g_half, sup, face)
        clearance(ctx, "support side", bolts, prov, what)
        if bolts.joint == "slip_critical":
            slip(ctx, "support side", group_s, v, (ha, hs))
        if not double:
            # the support leg bends under V e, e = g + tw/2 (Companion II.A-28A), gross
            # and net through its bolt line
            m = v * e_sup
            ctx.check("flexural_yield", f"{el}: flexural yielding of the gross section (J4.5)", m,
                      afy * t * length ** 2 / 4, "flexure_yield")
            ys = [(i - (n - 1) / 2) * s for i in range(n)]
            ctx.check("flexural_rupture", f"{el}: flexural rupture of the net section through the bolt holes (J4.5)", m,
                      afu * rect_net_z(t, length, ys, hv_a + SIXTEENTH), "flexure_rupture")
    else:
        weld: Weld = conn.attrs["support_weld"]
        # Each angle's outstanding leg welded along its toe, one line per angle carrying
        # V/count at the leg's width from the load (Companion II.A-2A: ex = 4 in = the
        # outstanding leg, k = 0). A single angle's load acts at the beam web's centre,
        # e = leg + tw/2.
        e = leg_o if double else leg_o + beam.tw / 2
        f = lines_out_of_plane(v, e, length, count)
        q = fillet_capacity_per_inch(ctx, weld)
        ctx.add("weld", f"{key} to support: most stressed point of the welds by the elastic method (J2.4)", _ratio(f, q))
        base_metal(ctx, key, f, afu, t, f"{key} to support")
        base_metal(ctx, f"support {face}", f, sfu, st, f"{key} to support")
        fillet_size(ctx, f"{key} to support", weld, min(t, st), length)


def _shear_tee(ctx: _Ctx, modes: set[str]) -> None:
    conn = ctx.conn
    v = ctx.load("shear")
    beam = _Beam(ctx)
    sup, sfy, sfu, st, face = _support(ctx)
    tee: TeeSpec = conn.attrs["tee"]
    parent = ctx.reg.w_shape(tee.parent)
    tfy, tfu = ctx.reg.steel(tee.grade)
    dt, bf, tf, tws = parent["d"] / 2, parent["bf"], parent["tf"], parent["tw"]
    bolts: Bolts = conn.attrs["bolts"]
    n, s = conn.attrs["rows"], ctx.need("pitch")
    lev, a, leh_b, top = (ctx.need(k) for k in ("edge_vertical", "bolt_line", "beam_edge", "top"))
    length = 2 * lev + (n - 1) * s
    hst, hfl, hb, hs = (_holes(conn, p) for p in ("stem", "flange", "beam", "support"))
    # beam side: the stem's group eccentric by a, the face of the support to the bolt
    # line (Companion II.A-30: "the bolts through the tee stem ... the eccentric moment
    # Rr a"), elastic method
    e = ctx.get("eccentricity", a)
    stem_ply = Ply("stem", tws, tfu, hst, lev, down=True)
    web_ply = _beam_web_ply(ctx, beam, top)
    group_b = BoltSet(ctx, bolts, n, 1, s, 0.0, [stem_ply, web_ply], 1, e, "beam side")
    hv_st, _ = group_b.hole_dims(hst)
    toe = dt - a
    shear_yield(ctx, "tee stem", v, tfy, length * tws)
    shear_rupture(ctx, "tee stem", v, tfu, (length - n * (hv_st + SIXTEENTH)) * tws)
    block_shear(ctx, "tee stem", group_b, v, tws, tfy, tfu, hst, lev, toe, True, [0])
    edges(ctx, "tee stem", tws, bolts.size, {"stem top and bottom": lev, "stem toe": toe})
    hole_use(ctx, "tee stem", hst, bolts)
    m = v * a
    ctx.check("flexural_yield", "tee stem: flexural yielding of the gross section (J4.5)", m, tfy * tws * length ** 2 / 4,
              "flexure_yield")
    ys = [(i - (n - 1) / 2) * s for i in range(n)]
    ctx.check("flexural_rupture", "tee stem: flexural rupture of the net section through the bolt holes (J4.5)", m,
              tfu * rect_net_z(tws, length, ys, hv_st + SIXTEENTH), "flexure_rupture")
    beam.web_checks(ctx, v, n, hb, group_b)
    web_edges = {"beam end": leh_b}
    setback = ctx.get("setback", 0.5)
    if beam.cope is not None:
        web_edges["cope"] = top - beam.dct
        block_shear(ctx, "beam web", group_b, v, beam.tw, beam.fy, beam.fu, hb, top - beam.dct, leh_b - UNDERRUN, False, [0])
        beam.cope_buckling(ctx, v, setback)
    edges(ctx, "beam web", beam.tw, bolts.size, web_edges)
    hole_use(ctx, "beam web", hb, bolts)
    group_b.check_bolts(v, "beam side")
    spacing(ctx, "beam side", bolts, min(tws, beam.tw), {"pitch": s})
    joint_type(ctx, "beam side", bolts, (hst, hb), tension=False)
    long_slots(ctx, "beam side", (hst, hb))
    clearance(ctx, "beam side", bolts, a - tf, "the tee flange")
    if bolts.joint == "slip_critical":
        slip(ctx, "beam side", group_b, v, (hst, hb))
    if conn.get("support_side") == "bolted":
        g = ctx.need("support_gauge")
        fl_edge = (bf - g) / 2
        fl_ply = Ply("flange", tf, tfu, hfl, lev, down=False)
        sup_ply = Ply("support", st, sfu, hs, None, down=True)
        group_s = BoltSet(ctx, bolts, n, 2, s, g, [fl_ply, sup_ply], 1, None, "support side")
        hv_f, _ = group_s.hole_dims(hfl)
        # the flange carries the force to its two bolt lines on two shear planes
        # (Companion II.D-1: Agv = (2 flanges) l tf)
        shear_yield(ctx, "tee flange", v, tfy, 2 * length * tf)
        shear_rupture(ctx, "tee flange", v, tfu, 2 * (length - n * (hv_f + SIXTEENTH)) * tf)
        one = BoltSet(ctx, bolts, n, 1, s, 0.0, [fl_ply, sup_ply], 1, None, "support side")
        block_shear(ctx, "tee flange", one, v, tf, tfy, tfu, hfl, lev, fl_edge, False, [0], planes=2)
        edges(ctx, "tee flange", tf, bolts.size, {"flange top and bottom": lev, "flange side": fl_edge})
        hole_use(ctx, "tee flange", hfl, bolts)
        hole_use(ctx, f"support {face}", hs, bolts)
        group_s.check_bolts(v, "support side")
        spacing(ctx, "support side", bolts, min(tf, st), {"pitch": s, "gauge": g})
        joint_type(ctx, "support side", bolts, (hfl, hs), tension=False)
        long_slots(ctx, "support side", (hfl, hs))
        prov, what = _support_clearance(ctx, g / 2, sup, face)
        clearance(ctx, "support side", bolts, prov, what)
        if bolts.joint == "slip_critical":
            slip(ctx, "support side", group_s, v, (hfl, hs))
    else:
        weld: Weld = conn.attrs["support_weld"]
        # the flange welded along both tips, each line carrying V/2 at bf/2 from the stem
        # (the tee's analogue of the double angle's welds B, Companion II.A-31 uses the
        # same Manual Table 10-2)
        f = lines_out_of_plane(v, bf / 2, length, 2)
        q = fillet_capacity_per_inch(ctx, weld)
        ctx.add("weld", "tee flange to support: most stressed point of the welds by the elastic method (J2.4)", _ratio(f, q))
        base_metal(ctx, "tee flange", f, tfu, tf, "tee flange to support")
        base_metal(ctx, f"support {face}", f, sfu, st, "tee flange to support")
        fillet_size(ctx, "tee flange to support", weld, min(tf, st), length)


def _shear_end_plate(ctx: _Ctx, modes: set[str]) -> None:
    conn = ctx.conn
    v = ctx.load("shear")
    beam = _Beam(ctx)
    sup, sfy, sfu, st, face = _support(ctx)
    plate: PlateSpec = conn.attrs["plate"]
    tp = ctx.geo(plate.thickness)
    pfy, pfu = ctx.reg.steel(plate.grade)
    width = ctx.need("plate_width")
    bolts: Bolts = conn.attrs["bolts"]
    n, s = conn.attrs["rows"], ctx.need("pitch")
    lev, g = ctx.need("edge_vertical"), ctx.need("support_gauge")
    length = 2 * lev + (n - 1) * s
    side = (width - g) / 2
    hp, hs = _holes(conn, "plate"), _holes(conn, "support")
    weld: Weld = conn.attrs["weld"]
    w = ctx.geo(weld.size)
    # Companion II.A-11A: "the effective weld length equals the end-plate length minus
    # twice the weld size"
    lw = length - 2 * w
    # beam web: gross shear yielding (welded web: no holes)
    shear_yield(ctx, "beam web", v, beam.fy, beam.h * beam.tw)
    if beam.cope is not None:
        beam.cope_buckling(ctx, v, ctx.get("setback", tp))
    q = fillet_capacity_per_inch(ctx, weld)
    ctx.add("weld", "end plate to beam web: fillet welds in longitudinal shear (J2.4)", _ratio(v, q * lw * weld.sides))
    per_fillet = v / (weld.sides * lw)
    # the beam web lies between the fillets and carries them all; the end plate carries
    # each fillet on its face separately
    base_metal(ctx, "beam web", per_fillet * weld.sides, beam.fu, beam.tw, "end plate to beam web")
    base_metal(ctx, "end plate", per_fillet, pfu, tp, "end plate to beam web")
    fillet_size(ctx, "end plate to beam web", weld, min(tp, beam.tw), lw)
    plate_ply = Ply("plate", tp, pfu, hp, lev, down=False)
    sup_ply = Ply("support", st, sfu, hs, None, down=True)
    group = BoltSet(ctx, bolts, n, 2, s, g, [plate_ply, sup_ply], 1, None, "support side")
    hv, _ = group.hole_dims(hp)
    # two vertical shear planes, one per bolt line (Companion II.A-11A: Agv = 2 l t)
    shear_yield(ctx, "end plate", v, pfy, 2 * length * tp)
    shear_rupture(ctx, "end plate", v, pfu, 2 * (length - n * (hv + SIXTEENTH)) * tp)
    one = BoltSet(ctx, bolts, n, 1, s, 0.0, [plate_ply, sup_ply], 1, None, "support side")
    block_shear(ctx, "end plate", one, v, tp, pfy, pfu, hp, lev, side, False, [0], planes=2)
    edges(ctx, "end plate", tp, bolts.size, {"plate top and bottom": lev, "plate side": side})
    hole_use(ctx, "end plate", hp, bolts)
    hole_use(ctx, f"support {face}", hs, bolts)
    group.check_bolts(v, "support side")
    spacing(ctx, "support side", bolts, min(tp, st), {"pitch": s, "gauge": g})
    joint_type(ctx, "support side", bolts, (hp, hs), tension=False)
    long_slots(ctx, "support side", (hp, hs))
    prov, what = _support_clearance(ctx, g / 2, sup, face)
    clearance(ctx, "support side", bolts, prov, what)
    if bolts.joint == "slip_critical":
        slip(ctx, "support side", group, v, (hp, hs))


def _seat_bearing(ctx: _Ctx, beam_shape: dict, fy: float, lb: float, r: float) -> None:
    """The beam web on its seat: J10.2 and J10.3 both at the member end (the governing
    case) and away from it."""
    for at_end in (False, True):
        j10_web_yielding(ctx, "beam web", beam_shape, fy, lb, r, at_end)
        j10_crippling(ctx, "beam web", beam_shape, fy, lb, r, at_end)


def _required_bearing(ctx: _Ctx, member: dict, fy: float, r: float) -> float:
    """The bearing length the reaction needs at the member end (Manual Table 10-5 practice,
    Companion II.A-12A): the least lb at which J10-3 and the crippling strength of J10-5a/b
    carry it, not less than kdes. Each strength is linear in lb, so each solves directly."""
    d, tw, tf, k = member["d"], member["tw"], member["tf"], member["kdes"]
    need_y = r / ctx.avail(1.0, "j10_2")
    need_c = r / ctx.avail(1.0, "j10_3")
    by_yielding = need_y / (fy * tw) - 2.5 * k
    unit = 0.40 * tw * tw * math.sqrt(ctx.reg.E * fy * tf / tw)
    x = (need_c / unit - 1) / (tw / tf) ** 1.5
    by_crippling = min(x * d / 3, (x + 0.2) * d / 4)        # J10-5a for lb/d <= 0.2, J10-5b above
    return max(by_yielding, by_crippling, k)


def seat_weld(r: float, e: float, length: float) -> float:
    """Force per inch at the top of a seat angle's two vertical welds, its leg bearing on
    the support below them (Manual Table 10-6 form, Companion II.A-16):
    R sqrt(L^2 + 20.25 e^2) / (2 L^2)."""
    return r * math.sqrt(length * length + 20.25 * e * e) / (2 * length * length)


def _seated(ctx: _Ctx, modes: set[str]) -> None:
    conn = ctx.conn
    r = ctx.load("shear")
    beam: Member = conn.attrs["beam"]
    bshape = ctx.reg.w_shape(beam.shape)
    bfy, _ = ctx.reg.steel(beam.grade)
    sup, sfy, sfu, st, face = _support(ctx)
    spec: AngleSpec = conn.attrs["angle"]
    long, short, t = ctx.reg.angle(spec.shape)
    # `outstanding` names the leg that carries the seat (lower.py)
    out = short if spec.outstanding == "short" else long
    vert = long if spec.outstanding == "short" else short
    afy, afu = ctx.reg.steel(spec.grade)
    ls = ctx.need("seat_length")
    sb = ctx.need("setback") + UNDERRUN              # Companion II.A-12A: the setback and the underrun
    lb = out - sb                                    # the bearing the seat offers: leg less setback
    _seat_bearing(ctx, bshape, bfy, lb, r)
    # seat flexure: the reaction at the middle of the bearing length the beam needs (vocab
    # seat_flexure, Manual Table 10-5), the critical section the judged offset beyond the
    # angle thickness from the back of the angle
    need = min(lb, _required_bearing(ctx, bshape, bfy, r))
    e = sb + need / 2 - (t + ctx.reg.const("aisc_manual.seat.critical_offset"))
    ctx.check("seat_flexure", "seat angle: flexural yielding of the outstanding leg at its critical section", r * max(e, 0.0),
              afy * ls * t * t / 4, "flexure_yield")
    shear_yield(ctx, "seat angle", r, afy, ls * t)
    if conn.get("support_side") == "bolted":
        bolts: Bolts = conn.attrs["bolts"]
        n, s, lev, g = conn.attrs["rows"], ctx.need("pitch"), ctx.need("edge_vertical"), ctx.need("support_gauge")
        side = (ls - g) / 2
        ha, hs = _holes(conn, "angle"), _holes(conn, "support")
        # the seat leg's top bolt is edge_vertical below the top of the angle, which the
        # deck names an edge ("seat leg top edge"); the seat bears down on its bolts
        leg_ply = Ply("angle", t, afu, ha, lev, down=False)
        sup_ply = Ply("support", st, sfu, hs, None, down=True)
        group = BoltSet(ctx, bolts, n, 2, s, g, [leg_ply, sup_ply], 1, None, "seat to support")
        edges(ctx, "seat angle", t, bolts.size, {"seat leg top": lev, "seat leg side": side})
        hole_use(ctx, "seat angle", ha, bolts)
        hole_use(ctx, f"support {face}", hs, bolts)
        group.check_bolts(r, "seat to support")
        # J3.4/J3.6 between rows only when there are two or more (the deck likewise)
        spacing(ctx, "seat to support", bolts, min(t, st), {**({"pitch": s} if n > 1 else {}), "gauge": g})
        joint_type(ctx, "seat to support", bolts, (ha, hs), tension=False)
        long_slots(ctx, "seat to support", (ha, hs))
        prov, what = _support_clearance(ctx, g / 2, sup, face)
        clearance(ctx, "seat to support", bolts, prov, what)
        if bolts.joint == "slip_critical":
            slip(ctx, "seat to support", group, r, (ha, hs))
    else:
        weld: Weld = conn.attrs["support_weld"]
        # welded along both vertical edges of the vertical leg; the reaction at the middle
        # of the bearing the seat offers (Companion II.A-16: e = setback + (leg - setback)/2),
        # by the Manual's seat-weld form (vocab weld)
        e_w = sb + lb / 2
        f = seat_weld(r, e_w, vert)
        q = fillet_capacity_per_inch(ctx, weld)
        ctx.add("weld", "seat to support: most stressed point of the welds by the elastic method (J2.4)", _ratio(f, q))
        base_metal(ctx, "seat angle", f, afu, t, "seat to support")
        base_metal(ctx, f"support {face}", f, sfu, st, "seat to support")
        fillet_size(ctx, "seat to support", weld, min(t, st), vert)


def _stiffened_seat(ctx: _Ctx, modes: set[str]) -> None:
    conn = ctx.conn
    r = ctx.load("shear")
    beam: Member = conn.attrs["beam"]
    bshape = ctx.reg.w_shape(beam.shape)
    bfy, _ = ctx.reg.steel(beam.grade)
    sup, sfy, sfu, st, face = _support(ctx)
    stiff: PlateSpec = conn.attrs["stiffener"]
    ts = ctx.geo(stiff.thickness)
    sfy_s, sfu_s = ctx.reg.steel(stiff.grade)
    width, lst = ctx.need("stiffener_width"), ctx.need("stiffener_length")
    sb = ctx.need("setback") + UNDERRUN
    lb = width - sb                 # Companion II.A-14: lb = W - setback - underrun
    _seat_bearing(ctx, bshape, bfy, lb, r)
    clip = ctx.reg.const("aisc_manual.seat.stiffener_clip")
    ctx.check("bearing", "stiffener: bearing on its fitted top edge (J7)", r, 1.8 * sfy_s * (width - clip) * ts, "j7")
    ctx.check("compression", "stiffener: compressive yielding of its section under the seat (J4.4)", r, sfy_s * width * ts,
              "compression")
    # vocab compression: the Manual's width-to-thickness limit, so the stiffener yields
    # before it buckles locally
    ctx.add("compression", "stiffener: width-to-thickness at most 0.56 sqrt(E / Fy) (Manual Part 10)",
            _ratio(width / ts, 0.56 * math.sqrt(ctx.reg.E / sfy_s)))
    # Companion II.A-14: the stiffener at least as thick as the beam web, scaled by the yield stresses
    ctx.add("compression", "stiffener: at least tw Fy,beam / Fy,stiffener thick (Manual Part 10)",
            _ratio(bshape["tw"] * bfy / sfy_s, ts))
    weld: Weld = conn.attrs["weld"]
    # Two fillets along the stiffener's length, the reaction out of their plane at 0.8 W
    # from the support face (Manual Table 10-8's eccentricity). Table 10-8 also counts
    # 0.2 L returns under the seat plate (it reproduces Companion II.A-14's 139 kips only
    # with them); the grammar declares no returns, so the two lines alone, conservatively.
    f = lines_out_of_plane(r, 0.8 * width, lst, weld.sides)
    q = fillet_capacity_per_inch(ctx, weld)
    ctx.add("weld", "stiffener to support: most stressed point of the welds by the elastic method (J2.4)", _ratio(f, q))
    # The reaction enters the stiffener's welds at their top end, as at a bearing stiffener,
    # which Commentary J2.2b names end-loaded: past 100 w only J2.2b(d)'s effective length
    # counts, beta l with beta = 1.2 - 0.002 l / w (Eq J2-1), and 180 w past 300 w.
    w = ctx.geo(weld.size)
    if lst > 100 * w:
        effective = 180 * w if lst > 300 * w else (1.2 - 0.002 * lst / w) * lst
        ctx.add("weld", "stiffener to support: the welds over their end-loaded effective length (J2.2b(d))",
                _ratio(lines_out_of_plane(r, 0.8 * width, effective, weld.sides), q))
    base_metal(ctx, "stiffener", f * weld.sides, sfu_s, ts, "stiffener to support")
    base_metal(ctx, f"support {face}", f, sfu, st, "stiffener to support")
    fillet_size(ctx, "stiffener to support", weld, min(ts, st), lst)


def _flange_force(ctx: _Ctx, modes: set[str]) -> None:
    conn = ctx.conn
    member: Member = conn.attrs["member"]
    m = ctx.reg.w_shape(member.shape)
    fy, _ = ctx.reg.steel(member.grade)
    E = ctx.reg.E
    force = ctx.load("force")
    lb = ctx.need("bearing_length")
    end = conn.attrs["location"] == "end"
    dist = ctx.get("distance") if end else None
    d, tw, tf, bf, k = m["d"], m["tw"], m["tf"], m["bf"], m["kdes"]
    h = d - 2 * k            # clear distance between flanges less the fillets (J10.4)
    j10_web_yielding(ctx, "member web", m, fy, lb, force, end and dist <= d)
    if conn.attrs["force_kind"] == "tensile":
        # J10.1, halved within 10 tf of the end. The exemption for a load narrower than
        # 0.15 bf across the flange is not taken (vocab flange_local_bending): the bearing
        # length runs along the member, and no width across the flange is declared.
        rn = 6.25 * fy * tf * tf * (0.5 if end and dist < 10 * tf else 1.0)
        ctx.check("flange_local_bending", "member flange: flange local bending (J10.1)", force, rn, "j10_1")
    else:
        j10_crippling(ctx, "member web", m, fy, lb, force, end and dist < d / 2)
        if conn.attrs.get("pair", "single") == "double":
            rn = 24 * tw ** 3 * math.sqrt(E * fy) / h * (0.5 if end and dist < d / 2 else 1.0)    # J10-8
            ctx.check("web_compression_buckling", "member web: web compression buckling (J10.5)", force, rn, "j10_5")
        elif "flange_restrained" in conn.attrs and "unbraced_length" in conn.attrs:
            lbr = ctx.need("unbraced_length")
            ratio = (h / tw) / (lbr / bf)
            cr = ctx.reg.const("aisc360.j10_4.cr_at_my" if conn.get("moment_at_force") == "at_yield"
                               else "aisc360.j10_4.cr_below_my")
            base = cr * tw ** 3 * tf / h ** 2
            if conn.attrs["flange_restrained"] == "yes":
                rn = base * (1 + 0.4 * ratio ** 3) if ratio <= 2.3 else None       # J10-6
            else:
                rn = base * (0.4 * ratio ** 3) if ratio <= 1.7 else None           # J10-7
            if rn is None:
                ctx.add("web_sidesway_buckling", "member web: does not apply (J10.4)", 0.0)
            else:
                ctx.check("web_sidesway_buckling", "member web: web sidesway buckling (J10.4)", force, rn, "j10_4")
    if "panel_zone" in modes:
        vp = ctx.load("panel_shear")
        pr = abs(ctx.load("axial"))
        py = fy * m["A"]
        alpha = 1.0 if ctx.lrfd else 1.6
        rn = 0.6 * fy * d * tw
        if alpha * pr > 0.4 * py:
            rn *= 1.4 - alpha * pr / py                                              # J10-10
        ctx.check("panel_zone", "member web: panel-zone shear (J10.6)", vp, rn, "j10_6")


def _bracket_edge(ctx: _Ctx, p: float, depth: float, b: float, t: float, fy: float, e_aa: float) -> None:
    """Manual Part 15 (Companion II.A-22, II.A-23): section B-B of a shaped bracket,
    normal to its sloped free edge. theta = atan(b/a), a' = a / cos theta (Eq 15-17),
    b' = a sin theta. Shear yielding Vn = 0.60 Fy t b' (Eq 15-7) against P sin theta;
    N = P cos theta, M = P e - N b'/2 (Eqs 15-8, 15-9) against Nc = phi Fcr t b' and
    Mc = phi Fcr t b'^2/4 (Eqs 15-11, 15-12), N/Nc + M/Mc <= 1 (Eq 15-10), Fcr = Q Fy
    with lambda = (b'/t) sqrt(Fy) / (5 sqrt(475 + 1120 (b'/a')^2)) (Eq 15-18) and
    Q = 1 (lambda <= 0.70), 1.34 - 0.486 lambda (to 1.41), 1.30 / lambda^2 above."""
    theta = math.atan2(b, depth)
    a_p = depth / math.cos(theta)
    b_p = depth * math.sin(theta)
    v = p * math.sin(theta)
    ctx.check("bracket_edge", "bracket plate: shear yielding of section B-B", v, 0.6 * fy * t * b_p, "shear_yield")
    lam = (b_p / t) * math.sqrt(fy) / (5 * math.sqrt(475 + 1120 * (b_p / a_p) ** 2))
    # vocab bracket_edge: the Manual's Q is continuous to 0.9998 at lambda = 0.70, taken
    # in the least-of form Q = min(1, 1.34 - 0.486 lambda) up to lambda = 1.41
    if lam <= 1.41:
        q = min(1.0, 1.34 - 0.486 * lam)
    else:
        q = 1.30 / lam ** 2
    fcr = q * fy
    n = p * math.cos(theta)
    m = abs(p * e_aa - n * b_p / 2)
    nc = ctx.avail(fcr * t * b_p, "flexure_yield")
    mc = ctx.avail(fcr * t * b_p ** 2 / 4, "flexure_yield")
    ctx.add("bracket_edge", "bracket plate: normal force and moment on section B-B", n / nc + m / mc)


def _bolt_bracket(ctx: _Ctx, modes: set[str]) -> None:
    conn = ctx.conn
    p = ctx.load("shear")
    sup, sfy, sfu, st, face = _support(ctx)
    plate: PlateSpec = conn.attrs["plate"]
    tp = ctx.geo(plate.thickness)
    pfy, pfu = ctx.reg.steel(plate.grade)
    bolts: Bolts = conn.attrs["bolts"]
    n, nc = conn.attrs["rows"], conn.attrs["columns"]
    s, g, e, lev, leh = (ctx.need(k) for k in ("pitch", "gauge", "eccentricity", "edge_vertical", "plate_edge"))
    depth = 2 * lev + (n - 1) * s
    hp, hs = _holes(conn, "plate"), _holes(conn, "support")
    # The plate bears down on its bolts (the hole's upper edge), so it tears toward its
    # top edge; the support flange has no edge. Columns: 0 is the one farthest from the
    # load (beside the plate's back edge, plate_edge), e measured from the centroid
    # toward the load.
    plate_ply = Ply("plate", tp, pfu, hp, lev, down=False)
    sup_ply = Ply("support", st, sfu, hs, None, down=True)
    group = BoltSet(ctx, bolts, n, nc, s, g, [plate_ply, sup_ply], 1, e, "bracket bolts")
    hv, _ = group.hole_dims(hp)
    shear_yield(ctx, "bracket plate", p, pfy, depth * tp)
    shear_rupture(ctx, "bracket plate", p, pfu, (depth - n * (hv + SIXTEENTH)) * tp)
    block_shear(ctx, "bracket plate", group, p, tp, pfy, pfu, hp, lev, leh, False, list(range(nc)))
    edges(ctx, "bracket plate", tp, bolts.size, {"plate top and bottom": lev, "plate side": leh})
    hole_use(ctx, "bracket plate", hp, bolts)
    hole_use(ctx, f"support {face}", hs, bolts)
    # Section A-A through the bolt column nearest the load, M = P (e - (cols-1) g/2)
    # (Companion II.A-22: Mu = Pu e with e from section A-A)
    e_aa = e - (nc - 1) * g / 2
    m = p * e_aa
    ctx.check("flexural_yield", "bracket plate: flexural yielding of the gross section (J4.5)", m, pfy * tp * depth ** 2 / 4,
              "flexure_yield")
    ys = [(i - (n - 1) / 2) * s for i in range(n)]
    ctx.check("flexural_rupture", "bracket plate: flexural rupture of the net section through the bolt holes (J4.5)", m,
              pfu * rect_net_z(tp, depth, ys, hv + SIXTEENTH), "flexure_rupture")
    group.check_bolts(p, "bracket bolts")
    # spacing between rows and between columns only where there are two or more of them
    spacing(ctx, "bracket bolts", bolts, min(tp, st), {**({"pitch": s} if n > 1 else {}), **({"gauge": g} if nc > 1 else {})})
    joint_type(ctx, "bracket bolts", bolts, (hp, hs), tension=False)
    long_slots(ctx, "bracket bolts", (hp, hs))
    if bolts.joint == "slip_critical":
        slip(ctx, "bracket bolts", group, p, (hp, hs))
    _bracket_plate(ctx, p, depth, tp, pfy, e_aa)


def _bracket_plate(ctx: _Ctx, p: float, depth: float, t: float, fy: float, e_aa: float) -> None:
    """A shaped bracket's section B-B (Manual Part 15); a rectangular one's lateral-torsional
    buckling as a cantilever from section A-A to the load, Section F11 with Lb = e_aa and
    Cb = 1.0, which Section F1(c) gives a cantilever whose free end is unbraced."""
    if ctx.conn.get("free_edge") is not None:
        _bracket_edge(ctx, p, depth, ctx.need("free_edge"), t, fy, e_aa)
    else:
        ctx.check("plate_buckling", "bracket plate: lateral-torsional buckling (F11)", p * e_aa,
                  f11_mn(fy, ctx.reg.E, t, depth, e_aa, 1.0), "flexure_yield")


def _weld_bracket(ctx: _Ctx, modes: set[str]) -> None:
    conn = ctx.conn
    p = ctx.load("shear")
    sup, sfy, sfu, st, face = _support(ctx)
    plate: PlateSpec = conn.attrs["plate"]
    tp = ctx.geo(plate.thickness)
    pfy, pfu = ctx.reg.steel(plate.grade)
    weld: Weld = conn.attrs["weld"]
    length, e = ctx.need("weld_length"), ctx.need("eccentricity")
    ret = ctx.get("weld_return")
    # Section A-A lies at the weld nearest the load (vocab flexural_yield): the weld line
    # for a plate square to the support, the returns' tips for a C-shaped weld, kl from
    # its vertical line (Companion II.A-23: e = 8-1/4 in to section A-A where the load is
    # al + xl = 11-1/4 in from the vertical weld with kl = 3 in). The declared
    # eccentricity is the load's distance from the weld group's vertical line.
    e_aa = e if ret is None else e - ret
    shear_yield(ctx, "bracket plate", p, pfy, length * tp)
    ctx.check("flexural_yield", "bracket plate: flexural yielding of the gross section (J4.5)", p * e_aa,
              pfy * tp * length ** 2 / 4, "flexure_yield")
    q = fillet_capacity_per_inch(ctx, weld)
    if ret is None:
        # a plate square to the support face, fillets on `sides` faces along its edge;
        # the moment P e bends the weld lines out of their plane
        f = lines_out_of_plane(p, e, length, weld.sides)
        plate_q = f * weld.sides
    else:
        # a plate lapped on the support face, one C-shaped fillet: in-plane elastic method
        f = c_shape_in_plane(p, e, length, ret)
        plate_q = f
    ctx.add("weld", "bracket weld: most stressed point of the welds by the elastic method (J2.4)", _ratio(f, q))
    base_metal(ctx, "bracket plate", plate_q, pfu, tp, "bracket weld")
    base_metal(ctx, f"support {face}", f, sfu, st, "bracket weld")
    fillet_size(ctx, "bracket weld", weld, min(tp, st), length)
    if ret is not None:
        # a lapped plate is welded along its own edges: J2.2b(b) maximum size, t below
        # 1/4 in, t - 1/16 in otherwise (vocab fillet_size: the edge limit applies to lap
        # joints)
        w = ctx.geo(weld.size)
        wmax = tp if tp < ctx.reg.const("aisc360.j2_2b.edge_t") else tp - ctx.reg.const("aisc360.j2_2b.edge_less")
        ctx.add("fillet_size", "bracket weld: maximum fillet size along the plate's edge (J2.2b(b))", _ratio(w, wmax))
    _bracket_plate(ctx, p, length, tp, pfy, e_aa)


def prying_available(ctx: _Ctx, bolts: Bolts, b_per_bolt: float, tf: float, fu: float, tw: float, bf: float,
                     g: float, p: float, hole: float) -> float:
    """Manual Part 9 prying (vocab prying; Companion II.D-1): available tension per bolt
    B Q, b = (g - tw)/2, a = (bf - g)/2, b' = b - d/2, a' = min(a + d/2, 1.25 b + d/2),
    rho = b'/a', delta = 1 - d'/p, tc = sqrt(4 B b' / (phi p Fu)) (LRFD; Omega for ASD),
    alpha' = [(tc/t)^2 - 1] / (delta (1 + rho)), Q = 1 (alpha' < 0),
    (t/tc)^2 (1 + delta alpha') (0 <= alpha' <= 1), (t/tc)^2 (1 + delta) (alpha' > 1)."""
    d = ctx.reg.bolt(bolts.size, "d")
    b = (g - tw) / 2
    a = (bf - g) / 2
    bp = b - d / 2
    ap = min(a + d / 2, 1.25 * b + d / 2)
    rho = bp / ap
    delta = 1 - hole / p
    phi, omega = FACTORS["flexure_yield"]
    if ctx.lrfd:
        tc = math.sqrt(4 * b_per_bolt * bp / (ctx.reg.const(phi) * p * fu))
    else:
        tc = math.sqrt(4 * ctx.reg.const(omega) * b_per_bolt * bp / (p * fu))
    alpha = ((tc / tf) ** 2 - 1) / (delta * (1 + rho))
    if alpha < 0:
        q = 1.0
    elif alpha <= 1:
        q = (tf / tc) ** 2 * (1 + delta * alpha)
    else:
        q = (tf / tc) ** 2 * (1 + delta)
    return b_per_bolt * q


def _hanger(ctx: _Ctx, modes: set[str]) -> None:
    conn = ctx.conn
    t_load = ctx.load("tension")
    v = ctx.load("shear")
    sup, sfy, sfu, st, face = _support(ctx)
    tee: TeeSpec = conn.attrs["tee"]
    parent = ctx.reg.w_shape(tee.parent)
    tfy, tfu = ctx.reg.steel(tee.grade)
    bf, tf, tws = parent["bf"], parent["tf"], parent["tw"]
    bolts: Bolts = conn.attrs["bolts"]
    n, s, g, lev = conn.attrs["rows"], ctx.need("pitch"), ctx.need("tee_gauge"), ctx.need("edge_vertical")
    length = 2 * lev + (n - 1) * s
    nb = 2 * n
    hf, hs = _holes(conn, "flange"), _holes(conn, "support")
    # the stem in tension over the tee's length (no holes in it: An = Ag, and no 0.85 Ag
    # limit, which J4.1 sets for bolted splice plates only)
    ctx.check("tension_yield", "tee stem: tensile yielding of the gross section (J4.1a)", t_load, tfy * length * tws,
              "tension_yield")
    ctx.check("tension_rupture", "tee stem: tensile rupture of the net section (J4.1b)", t_load, tfu * length * tws,
              "tension_rupture")
    fl_ply = Ply("flange", tf, tfu, hf, lev, down=True)
    sup_ply = Ply("support", st, sfu, hs, None, down=True)
    group = BoltSet(ctx, bolts, n, 2, s, g, [fl_ply, sup_ply], 1, None, "hanger bolts")
    hv, _ = group.hole_dims(hf)
    # the flange carries the stem's tension to its two bolt lines on two shear planes
    # (Companion II.D-1: Agv = (2 flanges) l tf, Anv = 2 (l - n (dh + 1/16)) tf)
    shear_yield(ctx, "tee flange", t_load, tfy, 2 * length * tf)
    shear_rupture(ctx, "tee flange", t_load, tfu, 2 * (length - n * (hv + SIXTEENTH)) * tf)
    fl_edge = (bf - g) / 2
    edges(ctx, "tee flange", tf, bolts.size, {"flange top and bottom": lev, "flange side": fl_edge})
    # the bolts pass through the support's flange at the tee's gauge, centred on its web
    # (vocab prying): its edge distance runs from the gauge line to its flange tip
    edges(ctx, f"support {face}", st, bolts.size, {"flange side": (sup["bf"] - g) / 2})
    hole_use(ctx, "tee flange", hf, bolts)
    hole_use(ctx, f"support {face}", hs, bolts)
    b_avail = ctx.avail(group.fnt * group.ab, "bolt")
    b_prying = b_avail
    if "bolt_combined" in modes:
        # Manual Part 9, Companion II.A-1B: with shear, prying works from F'nt Ab (Eq J3-3)
        frv_p = v / (nb * group.ab)
        phi, omega = FACTORS["bolt"]
        if ctx.lrfd:
            fnt_s = 1.3 * group.fnt - group.fnt / (ctx.reg.const(phi) * group.fnv) * frv_p
        else:
            fnt_s = 1.3 * group.fnt - ctx.reg.const(omega) * group.fnt / group.fnv * frv_p
        b_prying = ctx.avail(min(fnt_s, group.fnt) * group.ab, "bolt")
    per_bolt = t_load / nb
    ctx.add("bolt_tension", "hanger bolts: bolt tension (J3.7)", _ratio(per_bolt, b_avail))
    # tributary length per bolt (Manual Figure 9-4, Companion II.D-1):
    # an end row min(le, 1.75 b) + min(s/2, 1.75 b), an inner row 2 min(s/2, 1.75 b)
    b = (g - tws) / 2

    def tributaries(b: float) -> list[float]:
        out = []
        for i in range(n):
            if n == 1:
                out.append(2 * min(lev, 1.75 * b))
            elif i in (0, n - 1):
                out.append(min(lev, 1.75 * b) + min(s / 2, 1.75 * b))
            else:
                out.append(2 * min(s / 2, 1.75 * b))
        return out

    worst = min(prying_available(ctx, bolts, b_prying, tf, tfu, tws, bf, g, p, hv) for p in tributaries(b))
    ctx.add("prying", "hanger bolts: bolt tension with prying of the tee flange (Manual Part 9; Kulak 17.5)",
            _ratio(per_bolt, worst))
    # vocab prying: the support's flange under the same bolts by the same T-stub model,
    # bending about the support's web (Companion II.C-1 checks a column flange so)
    hsv, _ = group.hole_dims(hs)
    b_s = (g - sup["tw"]) / 2
    worst_s = min(prying_available(ctx, bolts, b_prying, st, sfu, sup["tw"], sup["bf"], g, p, hsv)
                  for p in tributaries(b_s))
    ctx.add("prying", "hanger bolts: bolt tension with prying of the support flange (Manual Part 9; Kulak 17.5)",
            _ratio(per_bolt, worst_s))
    spacing(ctx, "hanger bolts", bolts, min(tf, st), {"pitch": s, "gauge": g})
    joint_type(ctx, "hanger bolts", bolts, (hf, hs), tension=t_load > 0)
    long_slots(ctx, "hanger bolts", (hf, hs))
    clearance(ctx, "hanger bolts", bolts, b, "the tee stem")
    if "bolt_combined" in modes:
        # shear along the tee's length: the end row tears toward the flange's end edge
        group.check_bolts(v, "hanger bolts")
        frv = v / (nb * group.ab)
        ft = t_load / (nb * group.ab)
        phi_v = ctx.avail(group.fnv, "bolt")
        phi_t = ctx.avail(group.fnt, "bolt")
        if frv <= 0.3 * phi_v or ft <= 0.3 * phi_t:
            # J3.8 User Note: combined stress need not be investigated
            ctx.add("bolt_combined", "hanger bolts: combined stress not investigated (J3.8)", 0.0)
        else:
            phi, omega = FACTORS["bolt"]
            if ctx.lrfd:
                fnt_p = 1.3 * group.fnt - group.fnt / (ctx.reg.const(phi) * group.fnv) * frv       # J3-3a
            else:
                fnt_p = 1.3 * group.fnt - ctx.reg.const(omega) * group.fnt / group.fnv * frv       # J3-3b
            fnt_p = min(fnt_p, group.fnt)
            ctx.add("bolt_combined", "hanger bolts: combined tension and shear (J3.8)",
                    _ratio(ft * group.ab, ctx.avail(fnt_p * group.ab, "bolt")))
    if bolts.joint == "slip_critical" and "slip" in modes:
        slip(ctx, "hanger bolts", group, v, (hf, hs), tension=t_load)


KINDS: Mapping[str, Callable[[_Ctx, set[str]], None]] = {
    "shear_tab": _shear_tab,
    "double_angle": lambda ctx, modes: _angle_kind(ctx, modes, True),
    "single_angle": lambda ctx, modes: _angle_kind(ctx, modes, False),
    "shear_tee": _shear_tee,
    "shear_end_plate": _shear_end_plate,
    "seated": _seated,
    "stiffened_seat": _stiffened_seat,
    "flange_force": _flange_force,
    "bolt_bracket": _bolt_bracket,
    "weld_bracket": _weld_bracket,
    "hanger": _hanger,
}


# --- Entry points -----------------------------------------------------------------------

def modes_owed(conn: Conn, design: Design) -> tuple[str, ...]:
    """The modes the connection's load path demands (path.py's roles), in path order,
    from the load fields any case puts on it."""
    fields = {e.field for case in design.loads.values() for e in case.entries if e.target == (conn.name,)}
    out: list[str] = []
    for link in path(conn, fields):
        for mode in ROLE_LIMITS[link.role]:
            if mode not in out:
                out.append(mode)
    return tuple(out)


def checks(conn: Conn, design: Design, registry: Registry, case: str) -> dict[str, list[tuple[str, float]]]:
    """Every check the twin makes, by mode: (what, utilisation)."""
    ctx = _Ctx(conn, design, registry, case)
    modes = set(modes_owed(conn, design))
    KINDS[conn.kind](ctx, modes)
    return {m: v for m, v in ctx.out.items() if m in modes}


MAX_RANGED = 6
"""The most ranged lengths whose 2^k combinations of ends `utilisations` visits."""


def utilisations(conn: Conn, design: Design, registry: Registry, case: str) -> dict[str, float]:
    """The governing utilisation of every mode the connection owes that has a check:
    the largest demand / available over the mode's checks, at the upper end of each load
    interval of `case` on the connection, and over the middle and every combination of
    ends of the ranged lengths (a toleranced length must hold over its whole range)."""
    modes = set(modes_owed(conn, design))
    first = _Ctx(conn, design, registry, case)
    KINDS[conn.kind](first, modes)
    runs = [first.out]
    ranged = sorted(first.ranged)
    if len(ranged) > MAX_RANGED:
        raise ValueError(f"{len(ranged)} ranged lengths: the twin visits the ends of at most {MAX_RANGED}")
    for ends in (itertools.product((0, 1), repeat=len(ranged)) if ranged else ()):
        ctx = _Ctx(conn, design, registry, case)
        ctx.ends = dict(zip(ranged, ends))
        KINDS[conn.kind](ctx, modes)
        runs.append(ctx.out)
    return {m: max((u for out in runs for _, u in out.get(m, ())), default=0.0)
            for m in modes_owed(conn, design) if m not in UNCHECKED}


def utilisations_of(design: Design, registry: Registry, case: str) -> dict[str, dict[str, float]]:
    """utilisations for every steel connection of the design, by connection name."""
    out: dict[str, dict[str, float]] = {}
    for name, component in design.components.items():
        if component.kind in KIND_SPECS:
            conn = lower_conn(component, design, registry)
            out[name] = utilisations(conn, design, registry, case)
    return out
