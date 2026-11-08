"""Block shear pilot (docs/plan.md §6 P8): a lower-bound limit analysis of a bolted plate,
stated as one R1 goal, against AISC 360-22 §J4.3 Eq. J4-5. Trusted builder: stdlib only.

The plate is the corner of a larger plate. A group of `rows` x `cols` bolts sits near two
free edges: the end edge the bolts push toward (Lev from row 1) and the side edge (Leh
from column 1). The plate is held along its two far edges, `margin` beyond the outer row
and the outer column. This is the coped beam of Commentary Fig. C-J4.2, and the deck's
blocks (`checks.block_paths`) are its blocks: the first k rows from the end edge and the
first j columns from the side edge.

The goal says a statically admissible stress field carries the bolt group force that J4.3
allows, inside a yield surface. If R1 proves it, that force is at most the plate's plastic
collapse load (the lower-bound theorem of limit analysis). If R1 refutes it, the force
exceeds this mesh's lower bound.

Plane stress, per unit thickness: the field's load and J4.3's Rn both scale with t, so one
statement covers every thickness. The mesh is the Clough-Tocher split of a macro mesh, so
the solver can write exact fields from an Airy stress function. Its elements are
linear-stress triangles (Sloan 1988): every triangle has its own stresses at its three
corners, and every row is exact rational.

- Equilibrium: div(sigma) = 0 in each triangle, 2 rows.
- Continuity: the traction across each interior edge, at both ends, 4 rows.
- Free edges and the free half of each hole: zero traction at both ends of each edge.
- Bearing: the bolt presses on the half-hole facing the end edge with a uniform pressure
  p_k, a variable of its own, so the traction there is -p_k n. The hole is a 16-sided
  polygon that circumscribes the standard hole, so the meshed plate lies inside the real
  one. Uniform pressure on a half-hole symmetric about the bolt's row line has no
  transverse resultant and no torque about the bolt.
- Load: the bolts' forces sum to J4.3's group strength.
- Moment: the shares put that force through the group's centroid (a concentric group).
  Otherwise the shares are free.
- Yield: at every corner of every triangle, (q, tau) lies in a 16-gon inscribed in the
  circle of radius rho, and (p, rho) lies in a 9-chord polygon inscribed in the
  half-ellipse p^2 + 3 rho^2 <= sigma0^2. Here p and q are the mean and half-difference of
  the normal stresses, and von Mises reads p^2 + 3 (q^2 + tau^2) <= sigma0^2. Both
  polygons have rational vertices on their curves, so the rows imply von Mises and the
  bound stays a lower bound.

Every row except the yield rows is homogeneous of degree one in length, and the yield
rows hold no length. So the mesh is in inches, the plate's SI lengths over the inch, which
keeps the rationals small; the unit of length cancels.

Each variable's bound is implied by the yield rows: |sigma_n| <= 2 sigma0 / sqrt 3 and
|tau| <= sigma0 / sqrt 3 on the von Mises ellipsoid. The bounds cut nothing from the
feasible set. They are there so a Farkas ray never pushes along an unbounded variable.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from fractions import Fraction as Q
from math import ceil

from ...kernel import Add, Const, Expr, Matrix, Mul, RangeHyp, Statement, Sym
from ...kernel.rules.r1_linear import LinearFeasible
from ...premises import registry_label
from ...units import CUSTOMARY
from ..base import model_spec

INCH = CUSTOMARY["inch"][0]

Point = tuple[Q, Q]


def _turn(p: Point, quarter: int) -> Point:
    x, y = p
    return ((x, y), (-y, x), (-x, -y), (y, -x))[quarter]


def _four(base: tuple[Point, ...]) -> tuple[Point, ...]:
    """`base` and its three quarter turns: one quadrant's points made a full circle, in order."""
    return tuple(_turn(p, quarter) for quarter in range(4) for p in base)


# --- The yield surface ---------------------------------------------------------------------

SHEAR_CIRCLE = _four(((Q(1), Q(0)), (Q(12, 13), Q(5, 13)), (Q(119, 169), Q(120, 169)), (Q(5, 13), Q(12, 13))))
"""Sixteen rational points on the unit circle, in order of angle, about 22.5 degrees apart.
Their chords bound a 16-gon inscribed in the circle."""

MERIDIAN = (
    (Q(1), Q(0)), (Q(97, 103), Q(20, 103)), (Q(313, 409), Q(152, 409)), (Q(1, 2), Q(1, 2)),
    (Q(59, 302), Q(171, 302)), (Q(-59, 302), Q(171, 302)), (Q(-1, 2), Q(1, 2)),
    (Q(-313, 409), Q(152, 409)), (Q(-97, 103), Q(20, 103)), (Q(-1), Q(0)),
)
"""Ten rational points (p, rho) on p^2 + 3 rho^2 = 1 with rho >= 0, from (1, 0) over the
top to (-1, 0), through uniaxial tension (1/2, 1/2) and compression. Their nine chords
bound a polygon inscribed in the half-ellipse."""

NORMAL_BOUND = Q(231, 200)
"""Above 2/sqrt 3, the largest normal stress on the von Mises ellipsoid, over sigma0."""
SHEAR_BOUND = Q(289, 500)
"""Above 1/sqrt 3, the largest shear stress on the von Mises ellipsoid, over sigma0."""


@dataclass(frozen=True)
class YieldRow:
    """coefficients . (sigma_xx, sigma_yy, tau, rho) + slack = rhs sigma0, slack >= 0.
    `slack` is the slack's largest value given the other variables' bounds, over sigma0."""

    sxx: Q
    syy: Q
    txy: Q
    rho: Q
    rhs: Q
    slack: Q


def yield_rows() -> tuple[YieldRow, ...]:
    """The 16 chords of SHEAR_CIRCLE scaled by rho, then the 9 chords of MERIDIAN.

    A chord of the unit circle from v to w is n . u <= h with n = v + w and
    h = 1 + v . w, since n . v = n . w = h. With q = (sxx - syy)/2 the row is
    2 (n_q q + n_t tau - h rho) <= 0. A meridian chord from P1 to P2, taken counter-clockwise,
    has outward normal (rho2 - rho1, p1 - p2); with p = (sxx + syy)/2 its row is
    2 (n_p p + n_r rho) <= 2 (n . P1) sigma0."""
    rows = []
    for k, (a, b) in enumerate(SHEAR_CIRCLE):
        c, d = SHEAR_CIRCLE[(k + 1) % len(SHEAR_CIRCLE)]
        nq, nt, h = a + c, b + d, 1 + a * c + b * d
        rows.append(YieldRow(nq, -nq, 2 * nt, -2 * h, Q(0),
                             2 * h * SHEAR_BOUND + 2 * abs(nq) * NORMAL_BOUND + 2 * abs(nt) * SHEAR_BOUND))
    for (p1, r1), (p2, r2) in zip(MERIDIAN, MERIDIAN[1:]):
        n_p, n_r = r2 - r1, p1 - p2
        level = n_p * p1 + n_r * r1
        rows.append(YieldRow(n_p, n_p, Q(0), 2 * n_r, 2 * level,
                             2 * level + 2 * abs(n_p) * NORMAL_BOUND + 2 * abs(n_r) * SHEAR_BOUND))
    return tuple(rows)


YIELD = yield_rows()

# --- The hole -------------------------------------------------------------------------------

HOLE_TANGENTS = _four(((Q(99, 101), Q(20, 101)), (Q(91, 109), Q(60, 109)), (Q(60, 109), Q(91, 109)), (Q(20, 101), Q(99, 101))))
"""The hole polygon's 16 tangent directions u_k, rational unit vectors near (k + 1/2) 22.5
degrees, symmetric about both axes. Edge k lies on u_k . (x - centre) = r, tangent to the
hole, so the polygon circumscribes it."""

BEARING = range(4, 12)
"""The edges whose tangent points face the end edge (90 to 270 degrees): the half-hole the
bolt bears on."""

SQUARE_SIDE = Q(2, 5)
"""Where the O-grid's rays from vertices 1, 3, 5, ... meet the side of the bolt's box,
as a fraction of the half-side (near tan 22.5 degrees). Any rational keeps the mesh exact."""


def _meet(u: Point, v: Point) -> Point:
    """The point x with u . x = 1 and v . x = 1."""
    det = u[0] * v[1] - u[1] * v[0]
    return ((v[1] - u[1]) / det, (u[0] - v[0]) / det)


HOLE_VERTICES = tuple(_meet(HOLE_TANGENTS[k - 1], HOLE_TANGENTS[k]) for k in range(len(HOLE_TANGENTS)))
"""The unit polygon's vertices: vertex k joins edges k - 1 and k, near k 22.5 degrees."""

SQUARE = _four(((Q(1), Q(0)), (Q(1), SQUARE_SIDE), (Q(1), Q(1)), (SQUARE_SIDE, Q(1))))
"""Where the O-grid's 16 rays meet the unit box, in the order of HOLE_VERTICES."""


# --- The plate and J4.3 ---------------------------------------------------------------------


@dataclass(frozen=True)
class Plate:
    """A plate corner holding a rows x cols bolt group. Lengths in metres, exact.

    pitch: between rows, along the push. gauge: between columns (unused for one column).
    lev: row 1 to the end edge the bolts push toward. leh: column 1 to the side edge.
    margin: the outer row and column to the held edges. grade: a registry steel grade.
    bolt: a registry bolt entry ("bolt_us.3_4"), whose standard hole the plate has."""

    rows: int
    cols: int
    pitch: Q
    gauge: Q
    lev: Q
    leh: Q
    margin: Q
    grade: str
    bolt: str


@dataclass(frozen=True)
class Block:
    """One of J4.3's blocks, per unit thickness, lengths in inches. `rupture` and `yield_`
    are Eq. J4-5's two branches in Pa in (stress times inches). `group` is the bolt group
    force at which this block reaches Rn under the deck's equal shares, Rn n / (k j)."""

    k: int
    j: int
    agv: Q
    anv: Q
    ant: Q
    ubs: Q
    rupture: Q
    yield_: Q
    group: Q


@dataclass(frozen=True)
class Claim:
    """J4.3's nominal strength of the bolt group: the least `group` over the blocks.
    It equals cfy Fy + cfu Fu (inches), the governing block's governing branch."""

    blocks: tuple[Block, ...]
    governing: Block
    branch: str
    cfy: Q
    cfu: Q
    force: Q
    fy: Q
    fu: Q


def _value(interval) -> Q:
    if interval.lo != interval.hi:
        raise ValueError(f"the pilot needs an exact registry value, not {interval}")
    return interval.lo


def material(plate: Plate, registry) -> tuple[Q, Q]:
    entry = f"steel.{plate.grade}"
    return _value(registry.property(entry, "fy").value), _value(registry.property(entry, "fu").value)


def constant(registry, name: str) -> Q:
    return _value(registry.constants[name].value)


def hole_diameter(plate: Plate, registry) -> Q:
    """The standard hole, in inches."""
    return constant(registry, f"{plate.bolt}.std") / INCH


def j4_3(plate: Plate, registry) -> Claim:
    """AISC 360-22 Eq. J4-5 over the deck's blocks (checks.block_paths, gen_block_shear):
    Agv = Lev + (k - 1) s, Anv = Agv - (k - 1/2) dn, Ant = Leh + (j - 1) g - (j - 1/2) dn,
    with dn the hole plus B4.3b's allowance, and Ubs = 1 for one column, the registry's
    nonuniform value otherwise (Commentary Fig. C-J4.2)."""
    fy, fu = material(plate, registry)
    shear = constant(registry, "aisc360.j4_3.shear")
    dn = hole_diameter(plate, registry) + constant(registry, "aisc360.b4_3b.hole_allowance") / INCH
    s, g, lev, leh = (v / INCH for v in (plate.pitch, plate.gauge, plate.lev, plate.leh))
    n = plate.rows * plate.cols
    blocks = []
    for k in range(1, plate.rows + 1):
        for j in range(1, plate.cols + 1):
            agv = lev + (k - 1) * s
            anv = agv - Q(2 * k - 1, 2) * dn
            ant = leh + (j - 1) * g - Q(2 * j - 1, 2) * dn
            ubs = Q(1) if j == 1 else constant(registry, "aisc360.j4_3.ubs_nonuniform")
            rupture = shear * fu * anv + ubs * fu * ant
            yield_ = shear * fy * agv + ubs * fu * ant
            blocks.append(Block(k, j, agv, anv, ant, ubs, rupture, yield_, min(rupture, yield_) * n / (k * j)))
    governing = min(blocks, key=lambda b: (b.group, b.k, b.j))
    scale = Q(n, governing.k * governing.j)
    if governing.rupture <= governing.yield_:
        branch, cfy, cfu = "rupture", Q(0), scale * (shear * governing.anv + governing.ubs * governing.ant)
    else:
        branch, cfy, cfu = "yield", scale * shear * governing.agv, scale * governing.ubs * governing.ant
    return Claim(tuple(blocks), governing, branch, cfy, cfu, governing.group, fy, fu)


def bearing(plate: Plate, registry) -> Q:
    """The plate's J3.11(a) bearing and tearout strength summed over the group, deformation
    at service load a design consideration, per unit thickness (Pa in): each bolt gives
    min(1.2 lc Fu, 2.4 d Fu), lc the clear distance toward the end edge. Context for the
    report: J4.3 governs the plate's bolt checks when its force is the smaller."""
    _, fu = material(plate, registry)
    hole = hole_diameter(plate, registry)
    d = constant(registry, f"{plate.bolt}.d") / INCH
    tear = constant(registry, "aisc360.j3_11a.tearout_considered")
    bear = constant(registry, "aisc360.j3_11a.bearing_considered")
    total = Q(0)
    for i in range(plate.rows):
        lc = (plate.lev / INCH - hole / 2) if i == 0 else (plate.pitch / INCH - hole)
        total += plate.cols * min(tear * lc * fu, bear * d * fu)
    return total


# --- The mesh -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Discretization:
    """rings: O-grid layers between a hole and its box. cell: the largest side of a plain
    cell, inches. box: the largest half-side of a bolt's box, inches."""

    rings: int
    cell: Q
    box: Q


@dataclass(frozen=True)
class Mesh:
    """Lengths in inches, origin at the corner of the two free edges, x toward the far end,
    y away from the side edge. `micro` holds the Clough-Tocher split of `macro`: macro
    triangle m gives micro triangles 3m, 3m+1, 3m+2 = (a, b, g), (b, c, g), (c, a, g), with g
    its centroid. Every triangle is counter-clockwise. `holes` maps a hole edge (sorted
    vertex pair) to (bolt, polygon edge k). `contact` holds the macro triangles of the first
    O-grid layer next to each bearing half-hole."""

    points: tuple[Point, ...]
    macro: tuple[tuple[int, int, int], ...]
    micro: tuple[tuple[int, int, int], ...]
    bolts: tuple[Point, ...]
    radius: Q
    width: Q
    length: Q
    breadth: Q
    holes: dict
    contact: frozenset

    def kind(self, a: int, b: int) -> tuple:
        """("free",), ("held",) or ("hole", bolt, k) for a boundary edge."""
        (xa, ya), (xb, yb) = self.points[a], self.points[b]
        if (xa == 0 and xb == 0) or (ya == 0 and yb == 0):
            return ("free",)
        if (xa == self.length and xb == self.length) or (ya == self.breadth and yb == self.breadth):
            return ("held",)
        bolt, k = self.holes[(min(a, b), max(a, b))]
        return ("hole", bolt, k)


def _area2(a: Point, b: Point, c: Point) -> Q:
    return (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])


def _lines(lo: Q, hi: Q, centres: list[Q], half: Q, cell: Q) -> tuple[list[Q], set[tuple[Q, Q]]]:
    """Grid lines from lo to hi: each bolt box's sides, and plain spans cut into pieces no
    longer than `cell`. Returns the lines and the set of box spans."""
    boxes = {(c - half, c + half) for c in centres}
    marks = sorted({lo, hi} | {e for span in boxes for e in span})
    lines = [marks[0]]
    for u, v in zip(marks, marks[1:]):
        pieces = 1 if (u, v) in boxes else max(1, ceil((v - u) / cell))
        lines += [u + (v - u) * Q(m, pieces) for m in range(1, pieces + 1)]
    return lines, boxes


def build_mesh(plate: Plate, registry, disc: Discretization) -> Mesh:
    s, g, lev, leh, margin = (v / INCH for v in (plate.pitch, plate.gauge, plate.lev, plate.leh, plate.margin))
    radius = hole_diameter(plate, registry) / 2
    xs = [lev + i * s for i in range(plate.rows)]
    ys = [leh + j * g for j in range(plate.cols)]
    length, breadth = xs[-1] + margin, ys[-1] + margin
    half = min([lev, leh, margin, disc.box] + ([s / 2] if plate.rows > 1 else []) + ([g / 2] if plate.cols > 1 else []))
    if max(abs(v[0]) for v in HOLE_VERTICES) * radius >= half:
        raise ValueError("the hole polygon does not fit in its box")
    xlines, xboxes = _lines(Q(0), length, xs, half, disc.cell)
    ylines, yboxes = _lines(Q(0), breadth, ys, half, disc.cell)

    index: dict[Point, int] = {}
    points: list[Point] = []

    def at(p: Point) -> int:
        if p not in index:
            index[p] = len(points)
            points.append(p)
        return index[p]

    macro: list[tuple[int, int, int]] = []

    def triangle(a: Point, b: Point, c: Point) -> None:
        area = _area2(a, b, c)
        if area == 0:
            raise ValueError("a degenerate triangle")
        macro.append((at(a), at(b), at(c)) if area > 0 else (at(a), at(c), at(b)))

    bolts = tuple((x, y) for x in xs for y in ys)
    # Every column's line y = y_j runs along mesh edges, through the fans' centres, so the
    # solver can cut the plate there (blockshear_solve: the Airy function's branch cuts).
    side_points: set[Point] = {(x, y) for x in xlines for y in ys}
    holes: dict[tuple[int, int], tuple[int, int]] = {}
    contact: set[int] = set()
    layers = disc.rings + 1
    for bolt, (cx, cy) in enumerate(bolts):
        ring = [[(cx + radius * vx + (half * sx - radius * vx) * Q(m, layers), cy + radius * vy + (half * sy - radius * vy) * Q(m, layers))
                 for (vx, vy), (sx, sy) in zip(HOLE_VERTICES, SQUARE)] for m in range(layers + 1)]
        side_points |= {p for k, p in enumerate(ring[-1]) if k % 4 != 2}
        n = len(HOLE_VERTICES)
        for m in range(layers):
            for k in range(n):
                a, b, c, d = ring[m][k], ring[m][(k + 1) % n], ring[m + 1][(k + 1) % n], ring[m + 1][k]
                if k in BEARING:
                    contact |= {len(macro), len(macro) + 1}
                triangle(a, d, c)
                triangle(a, c, b)
        for k in range(n):
            a, b = at(ring[0][k]), at(ring[0][(k + 1) % n])
            holes[(min(a, b), max(a, b))] = (bolt, k)

    for x0, x1 in zip(xlines, xlines[1:]):
        for y0, y1 in zip(ylines, ylines[1:]):
            if (x0, x1) in xboxes and (y0, y1) in yboxes:
                continue
            bottom = sorted([(x, y) for x, y in side_points if y == y0 and x0 < x < x1])
            right = sorted([(x, y) for x, y in side_points if x == x1 and y0 < y < y1], key=lambda p: p[1])
            top = sorted([(x, y) for x, y in side_points if y == y1 and x0 < x < x1], reverse=True)
            left = sorted([(x, y) for x, y in side_points if x == x0 and y0 < y < y1], key=lambda p: -p[1])
            loop = [(x0, y0), *bottom, (x1, y0), *right, (x1, y1), *top, (x0, y1), *left]
            centre = ((x0 + x1) / 2, (y0 + y1) / 2)
            for a, b in zip(loop, loop[1:] + loop[:1]):
                triangle(centre, a, b)

    micro = []
    for a, b, c in macro:
        pa, pb, pc = points[a], points[b], points[c]
        gid = at(((pa[0] + pb[0] + pc[0]) / 3, (pa[1] + pb[1] + pc[1]) / 3))
        micro += [(a, b, gid), (b, c, gid), (c, a, gid)]
    width = (HOLE_VERTICES[BEARING.start][1] - HOLE_VERTICES[BEARING.stop % len(HOLE_VERTICES)][1]) * radius
    return Mesh(tuple(points), tuple(macro), tuple(micro), bolts, radius, width, length, breadth, holes, frozenset(contact))


# --- The statement --------------------------------------------------------------------------


@dataclass(frozen=True)
class Flow:
    """The yield stress sigma0 = factor x the grade's `prop` ("fy" or "fu")."""

    prop: str
    factor: Q


CONTACTS = ("bearing", "confined")
"""How a bolt hands its force to the plate. Both press the half-hole facing the end edge
with a uniform pressure p_k and leave the other half free (frictionless contact).

bearing: plane stress everywhere. A free hole surface carries a normal stress of at most
2 sigma0 / sqrt 3, so a bolt delivers at most (2 / sqrt 3) sigma0 w t, w the hole's
width across the push.

confined: in the contact zone, every O-grid cell on the bearing half of the bolt's box,
the bolt confines the steel through its thickness, so the stress across the thickness equals
the in-plane mean stress. Von Mises then limits only the in-plane shear, 3 (q^2 + tau^2)
<= sigma0^2, and the mean stress is free up to CONFINED_BOUND. That is the premise behind
J3.11's bearing strength of 2.4 d t Fu. It moves the limit from the bearing to the
block's planes, which pass outside the zone or through it with their shear still
limited."""

CONFINED_BOUND = Q(5)
"""The largest normal stress in the contact zone, over sigma0: above J3.11's 2.4 Fu / Fy
for every grade the pilot uses (3.9 for A36)."""

SHEAR_CAP = MERIDIAN[4][1]
"""171/302, the meridian polygon's top chord: rho <= SHEAR_CAP sigma0 lies inside
sqrt(q^2 + tau^2) <= sigma0 / sqrt 3."""


def confined_rows() -> tuple[YieldRow, ...]:
    """The 16 shear chords, then the cap rho <= SHEAR_CAP sigma0 in each of the 9 meridian
    rows' places, so every corner has as many rows as YIELD."""
    shear = [YieldRow(y.sxx, y.syy, y.txy, y.rho, y.rhs,
                      -y.rho * SHEAR_BOUND + 2 * abs(y.sxx) * CONFINED_BOUND + abs(y.txy) * SHEAR_BOUND)
             for y in YIELD[:len(SHEAR_CIRCLE)]]
    cap = YieldRow(Q(0), Q(0), Q(0), Q(2), 2 * SHEAR_CAP, 2 * SHEAR_CAP)
    return tuple(shear) + (cap,) * (len(YIELD) - len(SHEAR_CIRCLE))


CONFINED = confined_rows()


@dataclass(frozen=True)
class Pilot:
    """One statement and what a solver needs to read it. Column layout: three stresses
    (sxx, syy, tau) per triangle corner, corner c = 3 t + a; then rho per corner; then
    one slack per corner per yield row; then each bolt's pressure p_k. `zone` holds the
    corners in the contact zone, whose rows are CONFINED (contact "confined")."""

    plate: Plate
    claim: Claim
    flow: Flow
    contact: str
    mesh: Mesh
    statement: Statement
    load_row: int
    corners: int
    rho: int
    slack: int
    pressure: int
    zone: frozenset

    def table(self, corner: int) -> tuple[YieldRow, ...]:
        return CONFINED if corner in self.zone else YIELD


def _scaled(coefficient: Q, sym: Sym) -> Expr:
    return sym if coefficient == 1 else Mul((Const(coefficient), sym))


def statement(plate: Plate, registry, disc: Discretization, flow: Flow, contact: str) -> Pilot:
    if contact not in CONTACTS:
        raise ValueError(f"contact must be one of {CONTACTS}, not {contact}")
    claim = j4_3(plate, registry)
    mesh = build_mesh(plate, registry, disc)
    tris = mesh.micro
    corners = 3 * len(tris)
    rho, slack = 3 * corners, 4 * corners
    pressure = slack + corners * len(YIELD)
    columns = pressure + len(mesh.bolts)

    sym = {"fy": Sym("fy"), "fu": Sym("fu")}
    sigma0 = _scaled(flow.factor, sym[flow.prop])
    zone = frozenset(9 * m + c for m in mesh.contact for c in range(9)) if contact == "confined" else frozenset()
    rows: list[dict[int, Q]] = []
    rhs: list[Expr] = []

    def row(entries: dict[int, Q], b: Expr = Const(Q(0))) -> int:
        rows.append({j: v for j, v in entries.items() if v != 0})
        rhs.append(b)
        return len(rows) - 1

    def stress(t: int, a: int) -> int:
        return 3 * (3 * t + a)

    for t, tri in enumerate(tris):
        p = [mesh.points[v] for v in tri]
        ex, ey = {}, {}
        for a in range(3):
            b, c = p[(a + 1) % 3], p[(a + 2) % 3]
            dx, dy = b[1] - c[1], c[0] - b[0]       # 2 Area grad N_a
            col = stress(t, a)
            ex[col] = ex.get(col, Q(0)) + dx
            ex[col + 2] = ex.get(col + 2, Q(0)) + dy
            ey[col + 2] = ey.get(col + 2, Q(0)) + dx
            ey[col + 1] = ey.get(col + 1, Q(0)) + dy
        row(ex)
        row(ey)

    sides: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for t, tri in enumerate(tris):
        for a in range(3):
            u, v = tri[a], tri[(a + 1) % 3]
            sides.setdefault((min(u, v), max(u, v)), []).append((t, a))

    def traction(t: int, a: int, nx: Q, ny: Q, sign: int) -> tuple[dict[int, Q], dict[int, Q]]:
        col = stress(t, a)
        return ({col: sign * nx, col + 2: sign * ny}, {col + 2: sign * nx, col + 1: sign * ny})

    for key, owners in sorted(sides.items()):
        t, a = owners[0]
        tri = tris[t]
        (x0, y0), (x1, y1) = mesh.points[tri[a]], mesh.points[tri[(a + 1) % 3]]
        nx, ny = y1 - y0, x0 - x1        # outward from t: right of the counter-clockwise side
        if len(owners) == 2:
            t2, a2 = owners[1]
            tri2 = tris[t2]
            for end, local in ((tri[a], a), (tri[(a + 1) % 3], (a + 1) % 3)):
                local2 = tri2.index(end)
                for first, second in zip(traction(t, local, nx, ny, 1), traction(t2, local2, nx, ny, -1)):
                    row({**first, **second})
            continue
        kind = mesh.kind(*key)
        if kind[0] == "held":
            continue
        bearing_bolt = kind[1] if kind[0] == "hole" and kind[2] in BEARING else None
        for local in (a, (a + 1) % 3):
            for component, entries in enumerate(traction(t, local, nx, ny, 1)):
                if bearing_bolt is not None:
                    entries[pressure + bearing_bolt] = (nx, ny)[component]
                row(entries)

    for corner in range(corners):
        for r, y in enumerate(CONFINED if corner in zone else YIELD):
            row({3 * corner: y.sxx, 3 * corner + 1: y.syy, 3 * corner + 2: y.txy, rho + corner: y.rho,
                 slack + corner * len(YIELD) + r: Q(1)}, _scaled(y.rhs, sigma0) if y.rhs else Const(Q(0)))

    load_terms = [_scaled(c, sym[p]) for p, c in (("fy", claim.cfy), ("fu", claim.cfu)) if c != 0]
    load_row = row({pressure + k: mesh.width for k in range(len(mesh.bolts))},
                   load_terms[0] if len(load_terms) == 1 else Add(tuple(load_terms)))
    centroid = sum(y for _, y in mesh.bolts) / len(mesh.bolts)
    if any(y != centroid for _, y in mesh.bolts):
        row({pressure + k: y - centroid for k, (_, y) in enumerate(mesh.bolts)})

    entries = tuple((i, j, v) for i, r in enumerate(rows) for j, v in sorted(r.items()))
    lower: list[Expr | None] = []
    upper: list[Expr | None] = []
    for corner in range(corners):
        normal = CONFINED_BOUND if corner in zone else NORMAL_BOUND
        for bound in (normal, normal, SHEAR_BOUND):
            lower.append(_scaled(-bound, sigma0))
            upper.append(_scaled(bound, sigma0))
    lower += [Const(Q(0))] * corners
    upper += [_scaled(SHEAR_BOUND, sigma0)] * corners
    for corner in range(corners):
        for y in CONFINED if corner in zone else YIELD:
            lower.append(Const(Q(0)))
            upper.append(_scaled(y.slack, sigma0))
    lower += [Const(Q(0))] * len(mesh.bolts)
    upper += [_scaled(NORMAL_BOUND if contact == "bearing" else CONFINED_BOUND + SHEAR_BOUND, sigma0)] * len(mesh.bolts)

    goal = LinearFeasible(Matrix(len(rows), columns, entries), tuple(rhs), tuple(lower), tuple(upper))
    used = {flow.prop} | {p for p, c in (("fy", claim.cfy), ("fu", claim.cfu)) if c != 0}
    value = {"fy": claim.fy, "fu": claim.fu}
    hyps = tuple(RangeHyp(p, value[p], value[p], registry_label(f"steel.{plate.grade}", p)) for p in sorted(used))
    return Pilot(plate, claim, flow, contact, mesh, Statement(hyps, goal), load_row, corners, rho, slack, pressure, zone)


MODEL = model_spec(
    sys.modules[__name__], "steel.blockshear_lower_bound",
    "a statically admissible plane-stress field in linear-stress triangles, inside polygons inscribed in von Mises, "
    "carrying the bolt group's force; the lower-bound theorem of limit analysis",
    "rigid-perfectly-plastic steel at the flow stress; plane stress, except that the confined contact lets the bolt "
    "confine the steel through its thickness in the contact zone; small displacements; rigid bolts that fill "
    "their holes and bear with uniform pressure on the half-hole facing the end edge; a concentric group; the "
    "plate held along its two far edges; holes undamaged (no B4.3b allowance in the plate)",
    "petra-maintainers",
    "Sloan, Lower bound limit analysis using finite elements and linear programming, IJNAMG 12 (1988); "
    "AISC 360-22 Section J4.3 Eq. J4-5",
)
