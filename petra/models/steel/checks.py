"""What each limit state checks on each connection kind. Trusted physics.

A Ctx wraps one StatementBuilder for one (requirement, load case). GEOMETRY[kind](ctx)
turns the typed Conn into the parts every limit state reads, as kernel Exprs over
hypotheses: bolted interfaces (a bolt group and the plies it passes through), weld
groups, plates in flexure, elements in tension, copes and concentrated forces.
GENERATORS[mode](ctx, geo) lists the Checks of that mode; build.py turns each Check into
one term of the obligation's AllNonpositive goal. ROWS[row id](ctx, geo) states a model's
validity row over the same geometry.

Sign conventions: every shear connection carries the beam's reaction V downward. Bolts
push the connecting element down (its bottom edge is the tearout edge) and push the beam
web up (its top edge, or the cope, is). A Ply records the direction its bolts push it.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Callable, Iterator, Mapping

from ... import mechanics as M
from ...ir import Design, Fixed, Input
from ...kernel import Abs, Expr, Interval, Max, Min, Sqrt, Sym
from ...mechanics import add, c, div, mul, sq, sub
from ...registry import Registry
from ...units import DIMENSIONLESS, Quantity
from ..base import StatementBuilder
from . import geometry as G
from . import limits as L
from .geometry import HOLE_DIMS
from .lower import SHAPE_GROUP, AngleSpec, Bolts, Conn, Cope, Geo, Member, PlateSpec, TeeSpec, Weld


# --- Context -------------------------------------------------------------------------------------

class Ctx:
    """One statement's builder plus what every check reads."""

    def __init__(self, conn: Conn, design: Design, registry: Registry, case: str) -> None:
        self.conn, self.design, self.registry, self.case = conn, design, registry, case
        self.sb = StatementBuilder(design, registry)
        self.lrfd = conn.basis == "lrfd"

    def geo(self, value: Geo, name: str) -> Expr:
        if isinstance(value, Input):
            return self.sb.input(value)
        return self.sb.value(value, f"{self.conn.name}.{name}")

    def attr(self, key: str) -> Expr:
        return self.geo(self.conn.attrs[key], key)

    def opt(self, key: str) -> Expr | None:
        return self.attr(key) if key in self.conn.attrs else None

    def count(self, key: str, n: int) -> Expr:
        """A whole-number design fact as a point hypothesis "dsg:<design>.<conn>.<key>"."""
        return self.sb.value(Fixed(Quantity(Interval(Fraction(n), Fraction(n)), DIMENSIONLESS)), f"{self.conn.name}.{key}")

    def const(self, name: str) -> Sym:
        return self.sb.constant(name)

    def shape(self, shape: str, prop: str) -> Sym:
        return self.sb.constant(f"{SHAPE_GROUP}.{shape}.{prop}")

    def mat(self, grade: str, prop: str) -> Expr:
        return self.sb.registry(grade, prop)

    def load(self, field_name: str) -> Expr | None:
        """The load case's signed bound on this connection's field, or None."""
        case = self.design.loads.get(self.case)
        entry = next((e for e in case.entries if e.target == (self.conn.name,) and e.field == field_name), None) if case else None
        if entry is None:
            return None
        return self.sb.input(entry.value) if isinstance(entry.value, Input) else self.sb.param(self.design.params[entry.value.name])

    def secondary(self, field_name: str) -> Expr:
        """A load field other than the kind's primary one: zero when the case omits it."""
        found = self.load(field_name)
        return c(0) if found is None else found

    def factor(self, group: str, suffix: str) -> Sym:
        return self.const(f"{group}.{'phi' if self.lrfd else 'omega'}{suffix}")

    def available(self, rn: Expr, group: str, suffix: str) -> Expr:
        """phi Rn (LRFD) or Rn / Omega (ASD)."""
        f = self.factor(group, suffix)
        return mul(f, rn) if self.lrfd else div(rn, f)

    def required(self, demand: Expr, group: str, suffix: str) -> Expr:
        """The nominal strength a demand needs: Ru / phi (LRFD) or Omega Ra (ASD)."""
        f = self.factor(group, suffix)
        return div(demand, f) if self.lrfd else mul(f, demand)

    def hole(self, ply: str) -> str:
        return self.conn.get("holes").get(ply, "std")


@dataclass(frozen=True)
class Check:
    """One term: |demand| <= u * available. `demand` is a vector whose magnitude is the
    demand (one component for a scalar). `capacity` is the nominal strength, made available
    with the factor group (phi or Omega + suffix), or already available, or a geometric
    limit, when `group` is None. The term is excused where any guard is <= 0. `what` names
    it in reports and `unit` says how they print its numbers."""

    what: str
    demand: tuple[Expr, ...]
    capacity: Expr
    group: str | None
    suffix: str
    guards: tuple[Expr, ...]
    unit: str           # how reports print demand and capacity: kip, kip-in, kip/in, in or 1


# --- Geometry ---------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Ply:
    """One connected part a bolt group passes through.

    count: elements of this ply each bolt passes through (bearing and tearout multiply by it).
    sections: gross shear sections of the ply that share the interface's force (two for an
    end plate or a tee flange, which carry half the reaction each side of the web).
    edge: from the extreme row, in the direction the bolts push, to a free edge (None: none).
    side: from the outer column to the free side edge (the block's tension plane).
    depth: one section's gross length along the bolt line (None: no shear check).
    columns: bolt columns one element of the ply holds."""

    name: str
    grade: str
    t: Expr
    count: int
    sections: int
    hole: str
    direction: str
    edge: Expr | None
    side: Expr | None
    depth: Expr | None
    columns: int
    edges_min: tuple[tuple[str, Expr], ...]
    block: bool


@dataclass(frozen=True)
class Prying:
    name: str                   # the flange that bends: "tee flange", "support flange"
    b: Expr                     # bolt line to the face of the stem (the web, for a support flange)
    a: Expr                     # bolt line to the flange edge
    p: tuple[tuple[str, Expr], ...]   # (which bolts, tributary flange length per bolt), Manual Figure 9-4
    t: Expr                     # flange thickness
    grade: str
    hole: str                   # the flange's hole type


@dataclass(frozen=True)
class Interface:
    name: str
    bolts: Bolts
    rows: int
    cols: int
    pitch: Expr
    gauge: Expr | None
    planes: int                 # shear planes through each bolt
    plies: tuple[Ply, ...]
    shear: Expr | None          # force the group carries in the plane of the plies
    eccentricity: Expr | None   # of the shear from the group centroid, in the plies' plane
    tension: Expr | None # total bolt tension
    clearances: tuple[tuple[str, Expr], ...]
    prying: tuple[Prying, ...]

    @property
    def n(self) -> int:
        return self.rows * self.cols


@dataclass(frozen=True)
class WeldGroup:
    name: str
    weld: Weld
    size: Expr
    length: Expr
    lines: int
    force: Expr
    eccentricity: Expr | None
    thinner: Expr               # thinner part joined (J2.2b minimum size)
    base: tuple[tuple[str, str, Expr, int], ...]   # (part, grade, thickness, fusion lines loading it at one place)
    bearing: bool       # a seat's two weld lines, its vertical leg bearing on the support below them
    ret: Expr | None     # returns at both ends of the line, toward the load: a C-shaped group
    edge: Expr | None    # a lapped part whose edge the fillet runs along (J2.2b maximum size)
    end_loaded: bool    # the force enters at the lines' end (Commentary J2.2b): J2.2b(d) applies


@dataclass(frozen=True)
class Flexure:
    name: str
    grade: str
    t: Expr
    depth: Expr
    moment: Expr
    rows: int
    pitch: Expr
    hole: Expr                  # net hole width dh + 1/16 in


@dataclass(frozen=True)
class Bracket:
    """A bracket plate (Manual Part 15, Fig. 15-2): depth a at the support section A-A, the
    load at arm e from A-A, and a shaped plate's sloped free edge projecting b from A-A
    (None: a rectangular plate, its free edge square to A-A)."""
    grade: str
    t: Expr
    a: Expr
    b: Expr | None
    e: Expr
    force: Expr


@dataclass(frozen=True)
class Tension:
    name: str
    grade: str
    gross: Expr
    net: Expr
    force: Expr


@dataclass(frozen=True)
class CopeGeo:
    flanges: str
    d: Expr
    dc: Expr                    # the top cope's depth
    dcb: Expr | None            # the bottom cope's depth when both flanges are coped
    c: Expr
    tw: Expr
    bf: Expr
    tf: Expr
    grade: str
    moment_arm: Expr
    force: Expr

    @property
    def hc(self) -> Expr:
        """The depth of web the copes leave."""
        return sub(self.d, self.dc) if self.dcb is None else sub(sub(self.d, self.dc), self.dcb)


@dataclass(frozen=True)
class Concentrated:
    """A concentrated force on a W member's flange (J10)."""

    shape: str
    grade: str
    force: Expr
    lb: Expr
    end_distance: Expr | None   # from the member end; None: interior
    tensile: bool
    pair: bool
    restrained: bool | None     # J10.4: loaded flange restrained against rotation; None: not stated
    unbraced: Expr | None
    below_yield: bool
    panel_shear: Expr | None
    axial: Expr | None
    name: str        # its checks read "<name> web: ..." and "<name> flange: ..."


@dataclass(frozen=True)
class Seat:
    grade: str
    t: Expr
    length: Expr                # along the beam's width
    setback: Expr
    lb: Expr
    force: Expr


@dataclass(frozen=True)
class Stiffener:
    grade: str
    t: Expr
    width: Expr
    length: Expr
    force: Expr
    beam_grade: str
    beam_tw: Expr
    seat_grade: str     # the seat plate's, which bears on the stiffener's fitted top edge


@dataclass(frozen=True)
class SinglePlate:
    """What the Manual's single-plate rules read."""

    form: str
    grade: str
    tp: Expr
    tw: Expr
    d_bolt: Expr
    weld_size: Expr
    a: Expr
    depth: Expr
    rows: int
    cols: int
    pitch: Expr
    gauge: Expr | None
    bolts: Bolts
    force: Expr
    plate_edge: Expr        # Leh on the plate
    beam_edge: Expr         # Leh on the beam web
    sides: int | None       # fillets per joint line of the plate-to-support weld


@dataclass
class Geometry:
    interfaces: list[Interface]
    welds: list[WeldGroup]
    flexures: list[Flexure]
    tensions: list[Tension]
    web_shear: list[tuple[str, str, Expr, Expr]]   # (name, grade, Agv, V): gross shear only
    net_shear: list[tuple[str, str, Expr, Expr]]   # (name, grade, Anv, V): its net section
    cope: CopeGeo | None
    forces: list[Concentrated]
    seat: Seat | None
    stiffener: Stiffener | None
    single_plate: SinglePlate | None
    bracket: Bracket | None

    @staticmethod
    def empty() -> Geometry:
        """A kind's geometry function starts here and adds what the connection has."""
        return Geometry(interfaces=[], welds=[], flexures=[], tensions=[], web_shear=[], net_shear=[], cope=None,
                        forces=[], seat=None, stiffener=None, single_plate=None, bracket=None)


def bolt_dims(ctx: Ctx, bolts: Bolts, hole: str) -> tuple[Expr, Expr, Expr]:
    """(d, hole dimension along the force, hole dimension across it), from Table J3.3."""
    g = f"bolt_us.{bolts.size}"
    along, across = HOLE_DIMS[hole]
    return ctx.const(f"{g}.d"), ctx.const(f"{g}.{along}"), ctx.const(f"{g}.{across}")


def _w(ctx: Ctx, member: Member) -> dict[str, Expr]:
    return {p: ctx.shape(member.shape, p) for p in ("d", "tw", "tf", "bf", "kdes", "A")}


def _face_t(member: Member, props: Mapping[str, Expr]) -> Expr:
    return props["tf"] if member.face == "flange" else props["tw"]


def _support_ply(ctx: Ctx) -> Ply:
    support: Member = ctx.conn.attrs["support"]
    t = _face_t(support, _w(ctx, support))
    return Ply(f"support {support.face}", support.grade, t, 1, 1, ctx.hole("support"), "down", None, None, None, 1, block=False, edges_min=())


def _underrun(ctx: Ctx) -> Sym:
    """The 1/4 in a beam may be delivered short (Manual Part 10). As the Companion does, the
    strength checks take it off the beam web's end distance and add it to a seat's setback;
    the dimensional limits (Table J3.4, J3.6, the Manual's 2d) and a cope's arm e = c +
    setback (Manual Part 9; Companion II.A-4 takes e = 4-1/2 in at a 1/2 in setback) take
    the lengths as detailed."""
    return ctx.const("aisc_manual.p10.underrun")


def _beam_web_ply(ctx: Ctx, beam: Member, props: Mapping[str, Expr], columns: int) -> Ply:
    """The beam web the bolts push up. Its free edge is the top of the beam, or the
    cope's horizontal edge; block shear applies only when coped (an uncoped web's top
    bolt would have to tear through the flange). The block's tension plane runs to the
    beam end less the underrun; the end's edge distance limits take it as detailed."""
    top, beam_edge = ctx.attr("top"), ctx.attr("beam_edge")
    side = sub(beam_edge, _underrun(ctx))
    cope: Cope | None = ctx.conn.get("cope")
    d = props["d"]
    if cope is None:
        return Ply("beam web", beam.grade, props["tw"], 1, 1, ctx.hole("beam"), "up", top, side, d, columns,
                   (("beam end", beam_edge),), block=False)
    dc = ctx.geo(cope.depth, "cope.depth")
    depth = sub(d, dc) if cope.flanges == "top" else sub(sub(d, dc), _bottom_cope(ctx, cope, dc))
    edge = sub(top, dc)
    return Ply("beam web", beam.grade, props["tw"], 1, 1, ctx.hole("beam"), "up", edge, side, depth, columns,
               (("beam end", beam_edge), ("cope", edge)), block=True)


def _bottom_cope(ctx: Ctx, cope: Cope, dc: Expr) -> Expr:
    return dc if cope.bottom is None else ctx.geo(cope.bottom, "cope.bottom_depth")


def _cope(ctx: Ctx, out: Geometry, beam: Member, props: Mapping[str, Expr], v: Expr) -> None:
    """The coped section, loaded by the reaction at the support face: its moment arm is
    the cope length plus the setback (Manual Part 9, e = c + setback)."""
    cope: Cope | None = ctx.conn.get("cope")
    if cope is None:
        return
    dc, cl = ctx.geo(cope.depth, "cope.depth"), ctx.geo(cope.length, "cope.length")
    dcb = None if cope.flanges == "top" else _bottom_cope(ctx, cope, dc)
    # a coped beam of lower.SET_BACK states its setback; an end plate's beam is welded to the plate
    arm = add(cl, ctx.attr("setback")) if "setback" in ctx.conn.attrs else cl
    out.cope = CopeGeo(cope.flanges, props["d"], dc, dcb, cl, props["tw"], props["bf"], props["tf"], beam.grade, arm, v)


def _support_clearances(support: Member, sp: Mapping[str, Expr], gauge: Expr) -> tuple[tuple[str, Expr], ...]:
    """Room to tighten the support-side bolts: from a bolt on the flange to the column web
    (gauge/2 - tw/2), or from a bolt on the web to the column flanges ((d - 2 tf - gauge)/2)."""
    if support.face == "flange":
        return (("support web", sub(div(gauge, c(2)), div(sp["tw"], c(2)))),)
    return (("support flanges", div(sub(sub(sp["d"], mul(c(2), sp["tf"])), gauge), c(2))),)


def _length(ctx: Ctx, rows: int) -> tuple[Expr, Expr, Expr]:
    """(pitch, vertical edge distance, element length 2 lev + (rows - 1) s)."""
    s, lev = ctx.attr("pitch"), ctx.attr("edge_vertical")
    return s, lev, add(mul(c(2), lev), mul(c(rows - 1), s))


def geometry_shear_tab(ctx: Ctx) -> Geometry:
    conn = ctx.conn
    beam: Member = conn.attrs["beam"]
    bp = _w(ctx, beam)
    plate: PlateSpec = conn.attrs["plate"]
    bolts: Bolts = conn.attrs["bolts"]
    rows, cols = conn.attrs["rows"], conn.get("columns")
    s, lev, depth = _length(ctx, rows)
    leh, a = ctx.attr("plate_edge"), ctx.attr("bolt_line")
    g = ctx.attr("gauge") if cols > 1 else None
    tp = ctx.geo(plate.thickness, "plate.thickness")
    v = ctx.load("shear")
    plate_ply = Ply("plate", plate.grade, tp, 1, 1, ctx.hole("plate"), "down", lev, leh, depth, cols,
                    (("plate top and bottom", lev), ("plate side", leh)), block=True)
    e = ctx.opt("eccentricity")
    if e is None:
        e = a if cols == 1 else add(a, div(mul(c(cols - 1), g), c(2)))
    support: Member = conn.attrs["support"]
    t_support = _face_t(support, _w(ctx, support))
    out = Geometry.empty()
    out.interfaces.append(Interface("beam side", bolts, rows, cols, s, g, 1, (plate_ply, _beam_web_ply(ctx, beam, bp, cols)),
                                    v, e, clearances=(("support face", a),), tension=None, prying=()))
    weld: Weld = conn.attrs["weld"]
    w = ctx.geo(weld.size, "weld.size")
    out.welds.append(WeldGroup("plate to support", weld, w, depth, weld.sides, v, None, Min((tp, t_support)),
                               (("plate", plate.grade, tp, weld.sides), (f"support {support.face}", support.grade, t_support, 1)), bearing=False, ret=None, edge=None, end_loaded=False))
    d_bolt, dh_v, _ = bolt_dims(ctx, bolts, ctx.hole("plate"))
    out.flexures.append(Flexure("plate", plate.grade, tp, depth, mul(v, a), rows, s, L.hole_net(ctx.const, dh_v)))
    out.single_plate = SinglePlate(conn.get("form"), plate.grade, tp, bp["tw"], d_bolt, w, a, depth,
                                   rows, cols, s, g, bolts, v, leh, ctx.attr("beam_edge"), weld.sides)
    _cope(ctx, out, beam, bp, v)
    return out


def _angle_legs(ctx: Ctx, angle: AngleSpec) -> tuple[Expr, Expr, Expr]:
    """(beam-side leg, outstanding leg, thickness)."""
    long, short, t = (ctx.shape(angle.shape, p) for p in ("d", "b", "t"))
    out, beam_leg = (long, short) if angle.outstanding == "long" else (short, long)
    return beam_leg, out, t


def geometry_angles(ctx: Ctx) -> Geometry:
    """double_angle and single_angle."""
    conn = ctx.conn
    double = conn.kind == "double_angle"
    key = "angles" if double else "angle"
    n_ang = 2 if double else 1
    beam: Member = conn.attrs["beam"]
    bp = _w(ctx, beam)
    angle: AngleSpec = conn.attrs[key]
    bolts: Bolts = conn.attrs["bolts"]
    rows = conn.attrs["rows"]
    s, lev, length = _length(ctx, rows)
    gb = ctx.attr("beam_gauge")
    beam_leg, out_leg, ta = _angle_legs(ctx, angle)
    v = ctx.load("shear")
    toe = sub(beam_leg, gb)
    angle_ply = Ply(key, angle.grade, ta, n_ang, n_ang, ctx.hole(key), "down", lev, toe, length, 1,
                    (("angle top and bottom", lev), ("angle toe", toe)), block=True)
    out = Geometry.empty()
    out.interfaces.append(Interface("beam side", bolts, rows, 1, s, None, n_ang, (angle_ply, _beam_web_ply(ctx, beam, bp, 1)),
                                    v, None if double else gb, clearances=(("outstanding leg", sub(gb, ta)),), tension=None, prying=()))
    support: Member = conn.attrs["support"]
    sp = _w(ctx, support)
    if conn.attrs["support_side"] == "bolted":
        gs = ctx.attr("support_gauge")
        # double: gs spans the two bolt lines across the web; single: gs is heel to bolt line.
        heel = sub(div(gs, c(2)), div(bp["tw"], c(2))) if double else gs
        toe_s = sub(out_leg, heel)
        legs = Ply(f"{key} outstanding", angle.grade, ta, 1, n_ang, ctx.hole(key), "up", lev, toe_s, length, 1,
                   (("outstanding top and bottom", lev), ("outstanding toe", toe_s)), block=True)
        ecc = None if double else add(gs, div(bp["tw"], c(2)))
        across = gs if double else mul(c(2), add(gs, div(bp["tw"], c(2))))
        out.interfaces.append(Interface("support side", bolts, rows, n_ang, s, gs if double else None, 1, (legs, _support_ply(ctx)),
                                        v, ecc, clearances=_support_clearances(support, sp, across), tension=None, prying=()))
        if not double:
            # One angle's support leg carries V at e from its bolt line: it bends (Manual Part 10).
            _, dh_v, _ = bolt_dims(ctx, bolts, ctx.hole(key))
            out.flexures.append(Flexure(f"{key} outstanding", angle.grade, ta, length, mul(v, ecc), rows, s, L.hole_net(ctx.const, dh_v)))
    else:
        weld: Weld = conn.attrs["support_weld"]
        w = ctx.geo(weld.size, "support_weld.size")
        t_sup = _face_t(support, sp)
        # Welds B: each angle's line carries its share at the outstanding leg's width from
        # the weld (Manual Table 10-2); one angle carries the reaction at the beam web's
        # centre, tw/2 farther (Companion II.A-29: al + xl = kl + tw/2).
        e = out_leg if double else add(out_leg, div(bp["tw"], c(2)))
        out.welds.append(WeldGroup(f"{key} to support", weld, w, length, n_ang, v, e, Min((ta, t_sup)),
                                   ((key, angle.grade, ta, 1), (f"support {support.face}", support.grade, t_sup, 1)), bearing=False, ret=None, edge=None, end_loaded=False))
    _cope(ctx, out, beam, bp, v)
    return out


def geometry_tee(ctx: Ctx) -> Geometry:
    conn = ctx.conn
    beam: Member = conn.attrs["beam"]
    bp = _w(ctx, beam)
    tee: TeeSpec = conn.attrs["tee"]
    bolts: Bolts = conn.attrs["bolts"]
    rows = conn.attrs["rows"]
    s, lev, length = _length(ctx, rows)
    a = ctx.attr("bolt_line")
    tp = {p: ctx.shape(tee.parent, p) for p in ("d", "tw", "tf", "bf")}
    v = ctx.load("shear")
    toe = sub(div(tp["d"], c(2)), a)
    stem = Ply("tee stem", tee.grade, tp["tw"], 1, 1, ctx.hole("stem"), "down", lev, toe, length, 1,
               (("stem top and bottom", lev), ("stem toe", toe)), block=True)
    out = Geometry.empty()
    out.interfaces.append(Interface("beam side", bolts, rows, 1, s, None, 1, (stem, _beam_web_ply(ctx, beam, bp, 1)), v,
                                    ctx.opt("eccentricity") or a, clearances=(("tee flange", sub(a, tp["tf"])),), tension=None, prying=()))
    support: Member = conn.attrs["support"]
    sp = _w(ctx, support)
    if conn.attrs["support_side"] == "bolted":
        gs = ctx.attr("support_gauge")
        side = div(sub(tp["bf"], gs), c(2))
        flange = Ply("tee flange", tee.grade, tp["tf"], 1, 2, ctx.hole("flange"), "up", lev, side, length, 1,
                     (("flange top and bottom", lev), ("flange side", side)), block=True)
        out.interfaces.append(Interface("support side", bolts, rows, 2, s, gs, 1, (flange, _support_ply(ctx)), v, None,
                                        clearances=_support_clearances(support, sp, gs), tension=None, prying=()))
    else:
        weld: Weld = conn.attrs["support_weld"]
        w = ctx.geo(weld.size, "support_weld.size")
        t_sup = _face_t(support, sp)
        # The flange-tip welds as Manual Table 10-2 welds B (Companion II.A-31): each line
        # carries R/2 at half the flange width from the stem.
        out.welds.append(WeldGroup("tee flange to support", weld, w, length, 2, v, div(tp["bf"], c(2)), Min((tp["tf"], t_sup)),
                                   (("tee flange", tee.grade, tp["tf"], 1), (f"support {support.face}", support.grade, t_sup, 1)), bearing=False, ret=None, edge=None, end_loaded=False))
    _, dh_v, _ = bolt_dims(ctx, bolts, ctx.hole("stem"))
    out.flexures.append(Flexure("tee stem", tee.grade, tp["tw"], length, mul(v, a), rows, s, L.hole_net(ctx.const, dh_v)))
    _cope(ctx, out, beam, bp, v)
    return out


def geometry_end_plate(ctx: Ctx) -> Geometry:
    conn = ctx.conn
    beam: Member = conn.attrs["beam"]
    bp = _w(ctx, beam)
    plate: PlateSpec = conn.attrs["plate"]
    bolts: Bolts = conn.attrs["bolts"]
    rows = conn.attrs["rows"]
    s, lev, length = _length(ctx, rows)
    gs, width = ctx.attr("support_gauge"), ctx.attr("plate_width")
    tp = ctx.geo(plate.thickness, "plate.thickness")
    v = ctx.load("shear")
    side = div(sub(width, gs), c(2))
    plate_ply = Ply("end plate", plate.grade, tp, 1, 2, ctx.hole("plate"), "up", lev, side, length, 1,
                    (("plate top and bottom", lev), ("plate side", side)), block=True)
    support: Member = conn.attrs["support"]
    sp = _w(ctx, support)
    out = Geometry.empty()
    out.interfaces.append(Interface("support side", bolts, rows, 2, s, gs, 1, (plate_ply, _support_ply(ctx)), v, None,
                                    clearances=_support_clearances(support, sp, gs), tension=None, prying=()))
    weld: Weld = conn.attrs["weld"]
    w = ctx.geo(weld.size, "weld.size")
    weld_length = sub(length, mul(c(2), w))
    out.welds.append(WeldGroup("end plate to beam web", weld, w, weld_length, weld.sides, v, None, Min((tp, bp["tw"])),
                               (("beam web", beam.grade, bp["tw"], weld.sides), ("end plate", plate.grade, tp, 1)), bearing=False, ret=None, edge=None, end_loaded=False))
    # The welded web yields in shear over its depth less the copes (Companion II.A-5:
    # Agv = (d - dc) tw); the weld's own length is the plane of weld_base_metal.
    out.web_shear.append(("beam web", beam.grade, mul(bp["tw"], _web_depth(ctx, bp)), v))
    _cope(ctx, out, beam, bp, v)
    return out


def _web_depth(ctx: Ctx, props: Mapping[str, Expr]) -> Expr:
    cope: Cope | None = ctx.conn.get("cope")
    if cope is None:
        return props["d"]
    dc = ctx.geo(cope.depth, "cope.depth")
    return sub(props["d"], dc) if cope.flanges == "top" else sub(sub(props["d"], dc), _bottom_cope(ctx, cope, dc))


def geometry_seated(ctx: Ctx) -> Geometry:
    conn = ctx.conn
    beam: Member = conn.attrs["beam"]
    angle: AngleSpec = conn.attrs["angle"]
    vertical, outstanding, ta = _angle_legs(ctx, angle)
    seat_length = ctx.attr("seat_length")
    setback = add(ctx.attr("setback"), _underrun(ctx))
    v = ctx.load("shear")
    lb = sub(outstanding, setback)
    support: Member = conn.attrs["support"]
    sp = _w(ctx, support)
    out = Geometry.empty()
    out.forces.append(Concentrated(beam.shape, beam.grade, v, lb, c(0), False, False, None, None, True, name="beam", panel_shear=None, axial=None))
    out.seat = Seat(angle.grade, ta, seat_length, setback, lb, v)
    out.web_shear.append(("seat angle", angle.grade, mul(seat_length, ta), v))
    if conn.attrs["support_side"] == "bolted":
        bolts: Bolts = conn.attrs["bolts"]
        rows = conn.attrs["rows"]
        s, lev = ctx.attr("pitch"), ctx.attr("edge_vertical")
        gs = ctx.attr("support_gauge")
        side = div(sub(seat_length, gs), c(2))
        # The beam pushes the seat down and the bolts hold it up: each bolt bears up on the
        # vertical leg, which tears toward its top edge from the top row (as the end plate
        # and the tee flange do). The support's bolts bear down on it (_support_ply).
        seat_ply = Ply("seat angle", angle.grade, ta, 1, 1, ctx.hole("angle"), "up", lev, None, None, 1,
                       (("seat leg top", lev), ("seat leg side", side)), block=False)
        out.interfaces.append(Interface("seat to support", bolts, rows, 2, s, gs, 1, (seat_ply, _support_ply(ctx)), v, None,
                                        clearances=_support_clearances(support, sp, gs), tension=None, prying=()))
    else:
        weld: Weld = conn.attrs["support_weld"]
        w = ctx.geo(weld.size, "support_weld.size")
        t_sup = _face_t(support, sp)
        arm = add(setback, div(lb, c(2)))
        out.welds.append(WeldGroup("seat to support", weld, w, vertical, 2, v, arm, Min((ta, t_sup)),
                                   (("seat angle", angle.grade, ta, 1), (f"support {support.face}", support.grade, t_sup, 1)),
                                   bearing=True, ret=None, edge=None, end_loaded=False))
    return out


def geometry_stiffened_seat(ctx: Ctx) -> Geometry:
    conn = ctx.conn
    beam: Member = conn.attrs["beam"]
    stiff: PlateSpec = conn.attrs["stiffener"]
    width, length = ctx.attr("stiffener_width"), ctx.attr("stiffener_length")
    ts = ctx.geo(stiff.thickness, "stiffener.thickness")
    setback = add(ctx.attr("setback"), _underrun(ctx))
    v = ctx.load("shear")
    support: Member = conn.attrs["support"]
    t_sup = _face_t(support, _w(ctx, support))
    out = Geometry.empty()
    out.forces.append(Concentrated(beam.shape, beam.grade, v, sub(width, setback), c(0), False, False, None, None, True, name="beam", panel_shear=None, axial=None))
    weld: Weld = conn.attrs["weld"]
    w = ctx.geo(weld.size, "weld.size")
    out.welds.append(WeldGroup("stiffener to support", weld, w, length, weld.sides, v, mul(ctx.const("aisc_manual.t10_8.eccentricity"), width), Min((ts, t_sup)),
                               (("stiffener", stiff.grade, ts, weld.sides), (f"support {support.face}", support.grade, t_sup, 1)),
                               end_loaded=True, bearing=False, ret=None, edge=None))
    seat: PlateSpec = conn.attrs["plate"]
    out.stiffener = Stiffener(stiff.grade, ts, width, length, v, beam.grade, _w(ctx, beam)["tw"], seat.grade)
    return out


def geometry_flange_force(ctx: Ctx) -> Geometry:
    conn = ctx.conn
    member: Member = conn.attrs["member"]
    end = conn.attrs["location"] == "end"
    out = Geometry.empty()
    out.forces.append(Concentrated(
        member.shape, member.grade, ctx.load("force"), ctx.attr("bearing_length"),
        ctx.attr("distance") if end else None, conn.attrs["force_kind"] == "tensile", conn.get("pair") == "double",
        None if "flange_restrained" not in conn.attrs else conn.attrs["flange_restrained"] == "yes",
        ctx.opt("unbraced_length"), conn.get("moment_at_force") == "below_yield",
        ctx.secondary("panel_shear"), ctx.secondary("axial"), name="member"))
    return out


def geometry_bolt_bracket(ctx: Ctx) -> Geometry:
    conn = ctx.conn
    plate: PlateSpec = conn.attrs["plate"]
    bolts: Bolts = conn.attrs["bolts"]
    rows, cols = conn.attrs["rows"], conn.attrs["columns"]
    s, lev, depth = _length(ctx, rows)
    g, e, leh = ctx.attr("gauge"), ctx.attr("eccentricity"), ctx.attr("plate_edge")
    tp = ctx.geo(plate.thickness, "plate.thickness")
    ply = Ply("bracket plate", plate.grade, tp, 1, 1, ctx.hole("plate"), "down", lev, leh, depth, cols,
              (("plate top and bottom", lev), ("plate side", leh)), block=True)
    v = ctx.load("shear")
    out = Geometry.empty()
    out.interfaces.append(Interface("bracket bolts", bolts, rows, cols, s, g, 1, (ply, _support_ply(ctx)), v, e, tension=None, clearances=(), prying=()))
    # Section A-A runs down the bolt column nearest the load (Manual Part 15).
    arm = sub(e, mul(c(Fraction(cols - 1, 2)), g))
    _, dh_v, _ = bolt_dims(ctx, bolts, ply.hole)
    out.flexures.append(Flexure("bracket plate", plate.grade, tp, depth, mul(v, arm), rows, s, L.hole_net(ctx.const, dh_v)))
    out.bracket = Bracket(plate.grade, tp, depth, ctx.opt("free_edge"), arm, v)
    return out


def geometry_weld_bracket(ctx: Ctx) -> Geometry:
    conn = ctx.conn
    plate: PlateSpec = conn.attrs["plate"]
    support: Member = conn.attrs["support"]
    t_sup = _face_t(support, _w(ctx, support))
    weld: Weld = conn.attrs["weld"]
    w = ctx.geo(weld.size, "weld.size")
    tp = ctx.geo(plate.thickness, "plate.thickness")
    length, e, v = ctx.attr("weld_length"), ctx.attr("eccentricity"), ctx.load("shear")
    ret = ctx.attr("weld_return") if "weld_return" in conn.attrs else None
    out = Geometry.empty()
    # Both fillets of a plate set on edge load it at one place; a lapped plate's single
    # C-shaped fillet runs along its edges.
    out.welds.append(WeldGroup("bracket weld", weld, w, length, weld.sides, v, e, Min((tp, t_sup)),
                               (("bracket plate", plate.grade, tp, weld.sides), (f"support {support.face}", support.grade, t_sup, 1)),
                               ret=ret, edge=None if ret is None else tp, bearing=False, end_loaded=False))
    # Section A-A is at the weld line, or past the returns where the plate leaves the support.
    arm = e if ret is None else sub(e, ret)
    out.web_shear.append(("bracket plate", plate.grade, mul(length, tp), v))
    out.flexures.append(Flexure("bracket plate", plate.grade, tp, length, mul(v, arm), 0, c(0), c(0)))
    out.bracket = Bracket(plate.grade, tp, length, ctx.opt("free_edge"), arm, v)
    return out


def geometry_hanger(ctx: Ctx) -> Geometry:
    conn = ctx.conn
    tee: TeeSpec = conn.attrs["tee"]
    bolts: Bolts = conn.attrs["bolts"]
    rows = conn.attrs["rows"]
    s, lev, length = _length(ctx, rows)
    gt = ctx.attr("tee_gauge")
    tp = {p: ctx.shape(tee.parent, p) for p in ("tw", "tf", "bf")}
    t = ctx.load("tension")
    b = div(sub(gt, tp["tw"]), c(2))
    a = div(sub(tp["bf"], gt), c(2))
    flange = Ply("tee flange", tee.grade, tp["tf"], 1, 2, ctx.hole("flange"), "down", lev, a, None, 1,
                 (("flange top and bottom", lev), ("flange side", a)), block=False)
    # The support's flange bends about its web under the same bolts, by the same T-stub
    # model (the Companion checks it so in II.C-1 and notes in II.D-1 that the thicker
    # flange need not be checked): its b and a run from the gauge to its web and edge.
    support: Member = conn.attrs["support"]
    sp = _w(ctx, support)
    b_s, a_s = div(sub(gt, sp["tw"]), c(2)), div(sub(sp["bf"], gt), c(2))
    hold = Ply("support flange", support.grade, sp["tf"], 1, 1, ctx.hole("support"), "down", None, None, None, 1,
               (("flange side", a_s),), block=False)
    out = Geometry.empty()
    out.interfaces.append(Interface("hanger bolts", bolts, rows, 2, s, gt, 1, (flange, hold), ctx.secondary("shear"),
                                    None, tension=t, clearances=(("tee stem", b),),
                                    prying=(Prying("tee flange", b, a, _tributaries(ctx, rows, lev, s, b), tp["tf"], tee.grade,
                                                   flange.hole),
                                            Prying("support flange", b_s, a_s, _tributaries(ctx, rows, lev, s, b_s), sp["tf"],
                                                   support.grade, hold.hole))))
    gross = mul(tp["tw"], length)
    out.tensions.append(Tension("tee stem", tee.grade, gross, gross, t))
    # The bolts' tension reaches the stem through the flange in shear either side of it:
    # two gross sections the flange's length long, and two net through the line of holes.
    _, dh_v, _ = bolt_dims(ctx, bolts, flange.hole)
    out.web_shear.append(("tee flange", tee.grade, mul(c(2), length, tp["tf"]), t))
    out.net_shear.append(("tee flange", tee.grade, mul(c(2), sub(length, mul(c(rows), L.hole_net(ctx.const, dh_v))), tp["tf"]), t))
    return out


def _tributaries(ctx: Ctx, rows: int, edge: Expr, pitch: Expr, b: Expr) -> tuple[tuple[str, Expr], ...]:
    """The flange length each bolt's prying acts on, by Manual Figure 9-4 as Companion
    II.D-1 reads it: at most 1.75 b either side of the bolt, an end bolt min(le, 1.75 b) +
    min(s/2, 1.75 b), an inner bolt 2 min(s/2, 1.75 b), a single row 2 min(le, 1.75 b).
    The support's flange takes the tee's edge and pitch with its own b (the Companion
    checks a column flange by the angles' procedure in II.C-1)."""
    cap = mul(ctx.const("aisc_manual.p9.tributary"), b)
    end = Min((edge, cap))
    if rows == 1:
        return (("the bolts", mul(c(2), end)),)
    half = Min((div(pitch, c(2)), cap))
    out = (("the end bolts", add(end, half)),)
    if rows > 2:
        out += (("the inner bolts", mul(c(2), half)),)
    return out


GEOMETRY: Mapping[str, Callable[[Ctx], Geometry]] = {
    "shear_tab": geometry_shear_tab,
    "double_angle": geometry_angles,
    "single_angle": geometry_angles,
    "shear_tee": geometry_tee,
    "shear_end_plate": geometry_end_plate,
    "seated": geometry_seated,
    "stiffened_seat": geometry_stiffened_seat,
    "flange_force": geometry_flange_force,
    "bolt_bracket": geometry_bolt_bracket,
    "weld_bracket": geometry_weld_bracket,
    "hanger": geometry_hanger,
}


# --- Bolt groups ---------------------------------------------------------------------------------------

def _fnv(ctx: Ctx, bolts: Bolts) -> Expr:
    group = ctx.registry.materials[bolts.group]
    prop = "Fnv_X" if bolts.threads == "excluded" and "Fnv_X" in group.props else "Fnv_N"
    fnv = ctx.mat(bolts.group, prop)
    # J5.2(a): through fillers over 1/4 in a bolt keeps 1 - 0.4 (t - 1/4) of its shear strength,
    # never less than 0.85. The grammar declares fillers, not their thickness, so a declared
    # filler takes the floor, which is the least the factor can be.
    return fnv if bolts.fillers == "none" else mul(ctx.const("aisc360.j5_2.floor"), fnv)


def _coefficients(ctx: Ctx, hole: str) -> tuple[Expr, Expr]:
    """J3.11a: a long slot perpendicular to the force has its own coefficients; otherwise
    the design says whether deformation at the hole is a design consideration."""
    bearing, tearout = L.BEARING["lsl_perpendicular" if hole == "lsl" else ctx.conn.get("deformation")]
    return ctx.const(bearing), ctx.const(tearout)


@dataclass(frozen=True)
class BoltStrength:
    """One limit state of one bolt, named for reports: its shear, or its bearing or tearout
    in one ply, with the clear distance lc a tearout runs (None for the others)."""

    what: str
    lc: Expr | None
    available: Expr


def bolt_strengths(ctx: Ctx, itf: Interface, row: str) -> tuple[BoltStrength, ...]:
    """The available strengths of one bolt in row "only", "top", "bottom" or "middle": its
    shear strength and, in each ply, its bearing and its tearout strength. Tearout runs to
    the free edge from the extreme row in the push direction, else to the next hole."""
    d = ctx.const(f"bolt_us.{itf.bolts.size}.d")
    out = [BoltStrength("bolt shear", None, ctx.available(L.bolt_shear(_fnv(ctx, itf.bolts), d, c(itf.planes)), "rcsc2025.s5_1", suffix=""))]
    for ply in itf.plies:
        _, dh_v, _ = bolt_dims(ctx, itf.bolts, ply.hole)
        fu = ctx.mat(ply.grade, "fu")
        kb, kt = _coefficients(ctx, ply.hole)
        out.append(BoltStrength(f"bearing on the {ply.name}", None,
                                ctx.available(mul(c(ply.count), L.bearing(d, ply.t, fu, kb)), "rcsc2025.s5_3", suffix="")))
        extreme = row == "only" or row == ("bottom" if ply.direction == "down" else "top")
        if extreme and ply.edge is None:
            continue
        lc = sub(ply.edge, div(dh_v, c(2))) if extreme else sub(itf.pitch, dh_v)
        out.append(BoltStrength(f"tearout of the {ply.name} to {'its edge' if extreme else 'the next hole'}", lc,
                                ctx.available(mul(c(ply.count), L.tearout(lc, ply.t, fu, kt)), "rcsc2025.s5_3", suffix="")))
    return tuple(out)


def _per_bolt(ctx: Ctx, itf: Interface, row: str) -> Expr:
    """Available strength of one bolt: the least of its bolt_strengths."""
    return Min(tuple(s.available for s in bolt_strengths(ctx, itf, row)))


def bolt_rows(itf: Interface) -> tuple[tuple[str, int], ...]:
    """(row kind, how many rows of that kind) per column."""
    if itf.rows == 1:
        return (("only", 1),)
    return (("top", 1), ("bottom", 1)) + ((("middle", itf.rows - 2),) if itf.rows > 2 else ())


def weakest_bolt(ctx: Ctx, itf: Interface) -> Expr:
    found = [_per_bolt(ctx, itf, r) for r, _ in bolt_rows(itf)]
    return found[0] if len(found) == 1 else Min(tuple(found))


def group_total(ctx: Ctx, itf: Interface) -> Expr:
    """Sum over the bolts of their available strengths (J3.7 with J3.11a)."""
    per_column = add(*(mul(c(k), _per_bolt(ctx, itf, r)) if k > 1 else _per_bolt(ctx, itf, r) for r, k in bolt_rows(itf)))
    return mul(c(itf.cols), per_column) if itf.cols > 1 else per_column


def _elastic(itf: Interface, force: Expr) -> tuple[Expr, Expr]:
    g = itf.gauge if itf.gauge is not None else c(0)
    return M.elastic_bolt_force(force, itf.eccentricity, c(itf.n), itf.rows, itf.cols, itf.pitch, g)


def gen_bolts(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for itf in geo.interfaces:
        if itf.shear is None:
            continue
        if itf.eccentricity is not None:
            out.append(Check(f"{itf.name}: most loaded bolt by the elastic method against the weakest bolt (J3.7, J3.11a)",
                             _elastic(itf, itf.shear), weakest_bolt(ctx, itf), group=None, suffix="", guards=(), unit="kip"))
        else:
            out.append(Check(f"{itf.name}: bolt shear, bearing and tearout summed over the group (J3.7, J3.11a)",
                             (itf.shear,), group_total(ctx, itf), group=None, suffix="", guards=(), unit="kip"))
    return out


def gen_slip(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for itf in geo.interfaces:
        b = itf.bolts
        if b.joint != "slip_critical" or itf.shear is None:
            continue
        g = f"bolt_us.{b.size}"
        tb = ctx.const(f"{g}.Tm_g120" if b.group == "bolt_group.120" else f"{g}.Tm_g150")
        mu = ctx.const(f"rcsc2025.s5_4.mu_{'a' if b.surface == 'class_a' else 'b'}")
        du = ctx.const("rcsc2025.s5_4.Du")
        hf = ctx.const(f"rcsc2025.s5_4.hf_{'two' if b.fillers == 'two' else 'one'}")
        ksc = c(1) if itf.tension is None else L.slip_ksc(div(itf.tension, c(itf.n)), du, tb, None if ctx.lrfd else ctx.const("aisc360.j3_10.ksc_asd"))
        holes = {p.hole for p in itf.plies}
        suffix = "_lsl" if holes & {"lsl", "lsl_parallel"} else "_ovs" if holes & {"ovs", "ssl_parallel"} else "_std"
        per_bolt = ctx.available(L.slip(mu, du, hf, tb, c(itf.planes), ksc), "rcsc2025.s5_4", suffix)
        if itf.eccentricity is not None:
            out.append(Check(f"{itf.name}: slip at the most loaded bolt (J3.9, elastic method)", _elastic(itf, itf.shear), per_bolt, group=None, suffix="", guards=(), unit="kip"))
        else:
            out.append(Check(f"{itf.name}: slip of the group (J3.9)", (itf.shear,), mul(c(itf.n), per_bolt), group=None, suffix="", guards=(), unit="kip"))
    return out


def gen_bolt_tension(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for itf in geo.interfaces:
        if itf.tension is None:
            continue
        d = ctx.const(f"bolt_us.{itf.bolts.size}.d")
        out.append(Check(f"{itf.name}: bolt tension (J3.7)", (div(itf.tension, c(itf.n)),),
                         L.bolt_tension(ctx.mat(itf.bolts.group, "Fnt"), d), "rcsc2025.s5_1", suffix="", guards=(), unit="kip"))
    return out


def _fnt_prime(ctx: Ctx, itf: Interface) -> tuple[Expr, Expr, Expr, Expr]:
    """(frv, Fnt, Fnv, F'nt) of a group in tension and shear, Eqs J3-3a/b."""
    ab = L.bolt_area(ctx.const(f"bolt_us.{itf.bolts.size}.d"))
    frv = div(itf.shear, mul(c(itf.n * itf.planes), ab))
    fnt, fnv = ctx.mat(itf.bolts.group, "Fnt"), _fnv(ctx, itf.bolts)
    return frv, fnt, fnv, L.combined_fnt(ctx.const, fnt, fnv, frv, ctx.factor("rcsc2025.s5_1", suffix=""), ctx.lrfd)


def gen_bolt_combined(ctx: Ctx, geo: Geometry) -> list[Check]:
    """J3.8, in any joint: J3.9 has slip-critical joints checked for the bearing-type
    limit states as well as for slip."""
    out = []
    for itf in geo.interfaces:
        if itf.tension is None or itf.shear is None:
            continue
        ab = L.bolt_area(ctx.const(f"bolt_us.{itf.bolts.size}.d"))
        frt = div(itf.tension, mul(c(itf.n), ab))
        frv, fnt, fnv, fnt_prime = _fnt_prime(ctx, itf)
        exempt = ctx.const("aisc360.j3_8.exemption")
        small_v = sub(frv, mul(exempt, ctx.available(fnv, "rcsc2025.s5_1", suffix="")))
        small_t = sub(frt, mul(exempt, ctx.available(fnt, "rcsc2025.s5_1", suffix="")))
        out.append(Check(f"{itf.name}: tension per bolt under combined tension and shear (J3.8)", (mul(frt, ab),),
                         mul(fnt_prime, ab), "rcsc2025.s5_1", guards=(small_v, small_t), suffix="", unit="kip"))
    return out


# --- Plies --------------------------------------------------------------------------------------------

def _plies(geo: Geometry) -> Iterator[tuple[Interface, Ply]]:
    for itf in geo.interfaces:
        for ply in itf.plies:
            yield itf, ply


def gen_shear_yield(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for itf, ply in _plies(geo):
        if ply.depth is None or itf.shear is None:
            continue
        agv = mul(c(ply.sections), ply.depth, ply.t)
        out.append(Check(f"{ply.name}: shear yielding of the gross section (J4.2a)", (itf.shear,),
                         L.shear_yield(ctx.const, ctx.mat(ply.grade, "fy"), agv), "aisc360.j4_2", "_y", guards=(), unit="kip"))
    for name, grade, agv, v in geo.web_shear:
        out.append(Check(f"{name}: shear yielding of the gross section (J4.2a)", (v,), L.shear_yield(ctx.const, ctx.mat(grade, "fy"), agv),
                         "aisc360.j4_2", "_y", guards=(), unit="kip"))
    return out


def gen_shear_rupture(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for itf, ply in _plies(geo):
        if ply.depth is None or itf.shear is None:
            continue
        _, dh_v, _ = bolt_dims(ctx, itf.bolts, ply.hole)
        anv = mul(c(ply.sections), sub(ply.depth, mul(c(itf.rows), L.hole_net(ctx.const, dh_v))), ply.t)
        out.append(Check(f"{ply.name}: shear rupture of the net section (J4.2b)", (itf.shear,),
                         L.shear_rupture(ctx.const, ctx.mat(ply.grade, "fu"), anv), "aisc360.j4_2", "_r", guards=(), unit="kip"))
    for name, grade, anv, v in geo.net_shear:
        out.append(Check(f"{name}: shear rupture of the net section (J4.2b)", (v,), L.shear_rupture(ctx.const, ctx.mat(grade, "fu"), anv),
                         "aisc360.j4_2", "_r", guards=(), unit="kip"))
    return out


def block_paths(rows: int, columns: int) -> list[tuple[int, int]]:
    """Every block bounded by the free edges: the first k rows from the edge in the push
    direction and the first j columns from the free side, for k in 1..rows, j in 1..columns.
    The shear planes run along the j-th column's holes from row k to the edge; the tension
    plane runs from row k's holes to the side edge."""
    return [(k, j) for k in range(1, rows + 1) for j in range(1, columns + 1)]


def gen_block_shear(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for itf, ply in _plies(geo):
        if not ply.block or ply.edge is None or ply.side is None or itf.shear is None:
            continue
        _, dh_v, dh_h = bolt_dims(ctx, itf.bolts, ply.hole)
        net_v, net_h = L.hole_net(ctx.const, dh_v), L.hole_net(ctx.const, dh_h)
        fy, fu = ctx.mat(ply.grade, "fy"), ctx.mat(ply.grade, "fu")
        gauge = itf.gauge if itf.gauge is not None else c(0)
        for k, j in block_paths(itf.rows, ply.columns):
            agv = mul(add(ply.edge, mul(c(k - 1), itf.pitch)), ply.t)
            anv = sub(agv, mul(c(Fraction(2 * k - 1, 2)), net_v, ply.t))
            ant = mul(sub(add(ply.side, mul(c(j - 1), gauge)), mul(c(Fraction(2 * j - 1, 2)), net_h)), ply.t)
            ubs = c(1) if j == 1 else ctx.const("aisc360.j4_3.ubs_nonuniform")
            # A concentric group shares the force equally. An eccentric one loads the block
            # with the elastic method's resultant over the block's bolts; a block holding
            # every bolt carries the applied force itself.
            if itf.eccentricity is None or (k == itf.rows and j == itf.cols):
                share: tuple[Expr, ...] = (div(mul(itf.shear, c(k * j)), c(itf.n)),)
            else:
                share = M.elastic_block_force(itf.shear, itf.eccentricity, c(itf.n), itf.rows, itf.cols, itf.pitch, gauge,
                                              k, min(j, itf.cols))
            out.append(Check(f"{ply.name}: block of {k} row(s) and {j} column(s) (J4.3)", share,
                             mul(c(ply.count), L.block_shear(ctx.const, fy, fu, agv, anv, ant, ubs)), "aisc360.j4_3", suffix="", guards=(), unit="kip"))
    return out


def gen_tension_yield(ctx: Ctx, geo: Geometry) -> list[Check]:
    return [Check(f"{t.name}: tensile yielding of the gross section (J4.1a)", (t.force,),
                  L.tension_yield(ctx.mat(t.grade, "fy"), t.gross), "aisc360.j4_1", "_y", guards=(), unit="kip") for t in geo.tensions]


def gen_tension_rupture(ctx: Ctx, geo: Geometry) -> list[Check]:
    return [Check(f"{t.name}: tensile rupture of the net section (J4.1b)", (t.force,),
                  L.tension_rupture(ctx.mat(t.grade, "fu"), t.net), "aisc360.j4_1", "_r", guards=(), unit="kip") for t in geo.tensions]


def gen_flexural_yield(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = [Check(f"{f.name}: flexural yielding of the gross section (J4.5)", (f.moment,),
                 L.flexural_yield(ctx.mat(f.grade, "fy"), M.rectangle_plastic_modulus(f.t, f.depth)), "aisc360.j4_5", "_y", unit="kip-in", guards=())
           for f in geo.flexures]
    sp = geo.single_plate
    if sp is not None and sp.form == "extended":
        # Manual Eq 10-8: (Vr/Vc)^2 + (Mr/Mc)^2 <= 1, Vc by shear yielding of the plate and Mc
        # the least of yielding and both F11 branches (the least is exact or errs low).
        vc = ctx.available(L.shear_yield(ctx.const, ctx.mat(sp.grade, "fy"), mul(sp.depth, sp.tp)), "aisc360.j4_2", "_y")
        _, inelastic, elastic = _extended_ltb(ctx, sp)
        mc = ctx.available(Min((inelastic, elastic)), "aisc360.j4_5", "_y")
        out.append(Check("plate: shear and flexural yielding interaction (Manual Eq 10-8)",
                         (div(sp.force, vc), div(mul(sp.force, sp.a), mc)), c(1), unit="1", group=None, suffix="", guards=()))
    return out


def gen_flexural_rupture(ctx: Ctx, geo: Geometry) -> list[Check]:
    return [Check(f"{f.name}: flexural rupture of the net section through the bolt holes (J4.5)", (f.moment,),
                  L.flexural_rupture(ctx.mat(f.grade, "fu"), M.rectangle_net_plastic_modulus(f.t, f.depth, f.rows, f.pitch, f.hole)),
                  "aisc360.j4_5", "_r", unit="kip-in", guards=())
            for f in geo.flexures if f.rows > 0]


# --- Welds ------------------------------------------------------------------------------------------------

def _weld_points(ctx: Ctx, wg: WeldGroup) -> tuple[tuple[str, tuple[Expr, ...]], ...]:
    """Force per unit length at the most stressed point of the group's lines, named where
    a C-shaped group has two candidates."""
    if wg.eccentricity is None:
        return (("", (div(wg.force, mul(c(wg.lines), wg.length)),)),)
    if wg.bearing:
        return (("", L.seat_weld_line(ctx.const, wg.force, wg.eccentricity, wg.length)),)
    if wg.ret is not None:
        fx, tip, heel = M.elastic_weld_c(wg.force, wg.eccentricity, wg.length, wg.ret)
        return ((", at the return tips", (fx, tip)), (", at the heel corners", (fx, heel)))
    return (("", M.elastic_weld_line(wg.force, wg.eccentricity, wg.length, c(wg.lines))),)


def _weld_checks(ctx: Ctx, fexx: Expr, wg: WeldGroup, over: str, guards: tuple[Expr, ...]) -> list[Check]:
    if wg.eccentricity is None:
        rn = mul(c(wg.lines), L.fillet_line(ctx.const, fexx, wg.size, wg.length))
        return [Check(f"{wg.name}: fillet welds in longitudinal shear{over} (J2.4)", (wg.force,), rn, "aisc360.j2_4",
                      guards=guards, suffix="", unit="kip")]
    return [Check(f"{wg.name}: most stressed point of the welds by the elastic method{where}{over} (J2.4)",
                  force, L.fillet_per_length(ctx.const, fexx, wg.size), "aisc360.j2_4", guards=guards, unit="kip/in", suffix="")
            for where, force in _weld_points(ctx, wg)]


def gen_weld(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for wg in geo.welds:
        fexx = ctx.mat(wg.weld.electrode, "FEXX")
        out += _weld_checks(ctx, fexx, wg, "", ())
        if wg.end_loaded:
            # J2.2b(d): an end-loaded fillet longer than 100 w counts only its effective
            # length (Eq J2-1); at or below 100 w that is its length, and the check is excused.
            effective = replace(wg, length=L.end_loaded_length(ctx.const, wg.length, wg.size))
            beyond = sub(wg.length, mul(ctx.const("aisc360.j2_2b.end_loaded_ratio"), wg.size))
            out += _weld_checks(ctx, fexx, effective, ", over the end-loaded effective length of Eq J2-1", (beyond,))
    return out


def gen_weld_base_metal(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for wg in geo.welds:
        for where, per_length in _weld_points(ctx, wg):
            for part, grade, t, faces in wg.base:
                demand = tuple(mul(c(faces), f) if faces > 1 else f for f in per_length)
                out.append(Check(f"{wg.name}: {part} base metal in shear rupture along the weld{where} (J2.4a)", demand,
                                 L.base_metal_per_length(ctx.const, ctx.mat(grade, "fu"), t), "aisc360.j4_2", "_r", unit="kip/in", guards=()))
    return out


def gen_fillet_size(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    t1, t2, t3 = (ctx.const(f"aisc360.j2_2b.{row}") for row in ("t1", "t2", "t3"))
    w1, w2, w3, w4 = (ctx.const(f"aisc360.j2_2b.{row}") for row in ("w1", "w2", "w3", "w4"))
    for wg in geo.welds:
        for wmin, guard in L.min_fillet(wg.thinner, t1, t2, t3, w1, w2, w3, w4):
            out.append(Check(f"{wg.name}: minimum fillet size for the thinner part (J2.2b, Table J2.4)", (wmin,), wg.size,
                             guards=() if guard is None else (guard,), unit="in", group=None, suffix=""))
        out.append(Check(f"{wg.name}: fillet at least four times its size long (J2.2b)",
                         (mul(ctx.const("aisc360.j2_2b.length_ratio"), wg.size),), wg.length, unit="in", group=None, suffix="", guards=()))
        if wg.edge is not None:
            # J2.2b(b): along an edge thinner than 1/4 in, at most its thickness; otherwise
            # at most 1/16 in less. The boundary t = 1/4 in belongs to the second.
            edge_t = ctx.const("aisc360.j2_2b.edge_t")
            out.append(Check(f"{wg.name}: maximum fillet size along the edge of a part under 1/4 in (J2.2b(b))", (wg.size,),
                             wg.edge, guards=(sub(edge_t, wg.edge),), unit="in", group=None, suffix=""))
            out.append(Check(f"{wg.name}: maximum fillet size along the edge of a part at least 1/4 in thick (J2.2b(b))",
                             (wg.size,), sub(wg.edge, ctx.const("aisc360.j2_2b.edge_less")),
                             guards=(add(sub(wg.edge, edge_t), ctx.const(L.STRICT)),), unit="in", group=None, suffix=""))
    return out


# --- Makeability of bolt patterns ---------------------------------------------------------------------

def gen_spacing_min(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for itf in geo.interfaces:
        need = mul(ctx.const("aisc360.j3_4.spacing_ratio"), ctx.const(f"bolt_us.{itf.bolts.size}.d"))
        if itf.rows > 1:
            out.append(Check(f"{itf.name}: pitch at least 2-2/3 d (J3.4)", (need,), itf.pitch, unit="in", group=None, suffix="", guards=()))
        if itf.cols > 1 and itf.gauge is not None:
            out.append(Check(f"{itf.name}: gauge at least 2-2/3 d (J3.4)", (need,), itf.gauge, unit="in", group=None, suffix="", guards=()))
    return out


def gen_edge_min(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for itf in geo.interfaces:
        need = ctx.const(f"bolt_us.{itf.bolts.size}.edge_min")
        for ply in itf.plies:
            for what, e in ply.edges_min:
                out.append(Check(f"{ply.name}: {what} edge distance at least Table J3.4's (J3.5)", (need,), e, unit="in", group=None, suffix="", guards=()))
    return out


def gen_spacing_max(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    weathering = ctx.conn.get("weathering") == "yes"
    ratio, cap = ("aisc360.j3_6.weathering_pitch_t", "aisc360.j3_6.weathering_pitch_max") if weathering else \
                 ("aisc360.j3_6.pitch_t", "aisc360.j3_6.pitch_max")
    # J3.6 limits the longitudinal spacing, the pitch along a bolt line; the gauge across
    # the force is not limited by it (Commentary J3.6).
    for itf in (i for i in geo.interfaces if i.rows > 1):
        thinner = Min(tuple(p.t for p in itf.plies))
        out.append(Check(f"{itf.name}: pitch at most the thickness multiple (J3.6)", (itf.pitch,), mul(ctx.const(ratio), thinner), unit="in", group=None, suffix="", guards=()))
        out.append(Check(f"{itf.name}: pitch at most the absolute limit (J3.6)", (itf.pitch,), ctx.const(cap), unit="in", group=None, suffix="", guards=()))
    return out


def gen_edge_max(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for itf in geo.interfaces:
        for ply in itf.plies:
            for what, e in ply.edges_min:
                out.append(Check(f"{ply.name}: {what} edge distance at most 12 t (J3.6)", (e,),
                                 mul(ctx.const("aisc360.j3_6.edge_t"), ply.t), unit="in", group=None, suffix="", guards=()))
                out.append(Check(f"{ply.name}: {what} edge distance at most 6 in (J3.6)", (e,), ctx.const("aisc360.j3_6.edge_max"), unit="in", group=None, suffix="", guards=()))
    return out


JOINT_LEVEL = {"snug": 0, "pretensioned": 1, "slip_critical": 2}
HOLE_LEVEL = {"std": "snug", "ssl": "snug", "lsl": "snug", "ovs": "slip_critical", "ssl_parallel": "slip_critical",
              "lsl_parallel": "slip_critical"}
"""The least joint type each hole type is permitted in (J3.3): oversized holes and slots
parallel to the force only in slip-critical joints."""


def _joint_level(ctx: Ctx, bolts: Bolts) -> Expr:
    return ctx.count("joint_level", JOINT_LEVEL[bolts.joint])


def gen_hole_use(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for itf in geo.interfaces:
        level = _joint_level(ctx, itf.bolts)
        for ply in itf.plies:
            out.append(Check(f"{ply.name}: {ply.hole} holes in a joint of the type they need (J3.3)",
                             (ctx.const(f"rcsc2025.joint_level.{HOLE_LEVEL[ply.hole]}"),), level, unit="1", group=None, suffix="", guards=()))
        long = sum(1 for p in itf.plies if p.hole in ("lsl", "lsl_parallel"))
        if long:
            out.append(Check(f"{itf.name}: long slots in at most one part at the faying surface (J3.3)",
                             (ctx.count(f"{itf.name.replace(' ', '_')}.long_slotted_plies", long),),
                             ctx.const("aisc360.j3_3.long_slot_plies"), unit="1", group=None, suffix="", guards=()))
    return out


def gen_joint_type(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for itf in geo.interfaces:
        level = _joint_level(ctx, itf.bolts)
        out.append(Check(f"{itf.name}: the joint is at least snug-tight (RCSC 4.1)", (ctx.const("rcsc2025.joint_level.snug"),), level, unit="1", group=None, suffix="", guards=()))
        if itf.tension is not None and itf.bolts.group in ("bolt_group.150", "bolt_group.200"):
            out.append(Check(f"{itf.name}: Group 150 or 200 bolts in tension are pretensioned (RCSC 4.2)",
                             (ctx.const("rcsc2025.joint_level.pretensioned"),), level, unit="1", group=None, suffix="", guards=()))
    return out


def gen_clearance(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for itf in geo.interfaces:
        nut = ctx.const(f"bolt_us.{itf.bolts.size}.nut_F")
        need = add(M.hex_corner(nut), ctx.const("aisc_manual.clearance.socket"))
        for what, distance in itf.clearances:
            out.append(Check(f"{itf.name}: room to tighten, clear of the {what} (Manual Part 7)", (need,), distance, unit="in", group=None, suffix="", guards=()))
    return out


# --- Copes and single plates ----------------------------------------------------------------------

def gen_cope_buckling(ctx: Ctx, geo: Geometry) -> list[Check]:
    """Manual Part 9 (16th ed.). A top cope: the tee left by the cope, Mn by Eqs 9-10 and
    9-11 for lambda = hc/tw <= 2 lambda_p and by elastic local buckling above, each branch
    guarded by its range. Both flanges coped: Section F11 on the web left between the
    copes, Lb = c and Cb by Eq 9-21, F11-3 and F11-4 guarded by theirs."""
    cg = geo.cope
    if cg is None:
        return []
    fy = ctx.mat(cg.grade, "fy")
    e = ctx.const("aisc360.E")
    m = (mul(cg.force, cg.moment_arm),)
    hc = cg.hc
    if cg.flanges == "top":
        sc, zc = M.tee_moduli(hc, cg.tw, cg.bf, cg.tf)
        k1 = L.cope_k1(ctx.const, hc, cg.c, cg.d)
        lam, lam_p = div(hc, cg.tw), L.cope_lambda_p(ctx.const, k1, e, fy)
        twice = mul(c(2), lam_p)
        return [
            Check("beam web: flexural yielding and local buckling at the cope face, lambda <= 2 lambda_p (Manual Part 9)",
                  m, L.cope_inelastic(mul(fy, zc), mul(fy, sc), lam, lam_p), "aisc360.j4_5", "_y",
                  (add(sub(twice, lam), ctx.const(L.STRICT_RATIO)),), unit="kip-in"),
            Check("beam web: elastic local buckling at the cope face, lambda > 2 lambda_p (Manual Part 9)",
                  m, L.cope_elastic(e, ctx.const("aisc360.nu"), k1, lam, sc), "aisc360.j4_5", "_y",
                  (sub(lam, twice),), unit="kip-in"),
        ]
    cb = L.double_cope_cb(ctx.const, cg.c, cg.d, cg.dc)
    x, inelastic, elastic = L.bar_ltb(ctx.const, e, fy, cb, cg.c, hc, cg.tw)
    limit = mul(ctx.const("aisc360.f11.inelastic_limit"), div(e, fy))
    return [
        Check("beam web: lateral-torsional buckling of the doubly coped web, Lb d/t^2 <= 1.9 E/Fy (F11, Manual Eq 9-21)",
              m, inelastic, "aisc360.j4_5", "_y", (add(sub(limit, x), ctx.const(L.STRICT_RATIO)),), unit="kip-in"),
        Check("beam web: lateral-torsional buckling of the doubly coped web, Lb d/t^2 > 1.9 E/Fy (F11, Manual Eq 9-21)",
              m, elastic, "aisc360.j4_5", "_y", (sub(x, limit),), unit="kip-in"),
    ]


def _extended_ltb(ctx: Ctx, sp: SinglePlate) -> tuple[Expr, Expr, Expr]:
    """Manual Part 10, extended single-plate connections: the plate's lateral-torsional
    buckling by Section F11 with Cb = 1.84 and Lb = a, the weld line to the first bolt line."""
    cb = ctx.const("aisc_manual.p10.extended_cb")
    return L.bar_ltb(ctx.const, ctx.const("aisc360.E"), ctx.mat(sp.grade, "fy"), cb, sp.a, sp.depth, sp.tp)


def gen_plate_buckling(ctx: Ctx, geo: Geometry) -> list[Check]:
    """Section F11's lateral-torsional buckling of a plate bent about its major axis: an
    extended single plate (Manual Part 10), and a rectangular bracket plate. The bracket is
    a cantilever from section A-A, where the support holds it, to the load at its free end:
    Lb is the arm from A-A to the load and Cb = 1 (F1(c)), nothing taken to brace that end.
    A shaped bracket's free edge is Manual Part 15's (gen_bracket_edge)."""
    sp, br = geo.single_plate, geo.bracket
    if sp is not None and sp.form == "extended":
        x, inelastic, elastic = _extended_ltb(ctx, sp)
        return _ltb_checks(ctx, "plate", "Cb = 1.84, Manual Part 10", sp.grade, x, inelastic, elastic, mul(sp.force, sp.a))
    if br is not None and br.b is None:
        fy = ctx.mat(br.grade, "fy")
        x, inelastic, elastic = L.bar_ltb(ctx.const, ctx.const("aisc360.E"), fy, ctx.const("aisc360.f1.cantilever_cb"),
                                          br.e, br.a, br.t)
        return _ltb_checks(ctx, "bracket plate", "Cb = 1 for a cantilever by F1(c), J4.5", br.grade, x, inelastic, elastic,
                           mul(br.force, br.e))
    return []


def _ltb_checks(ctx: Ctx, name: str, cb: str, grade: str, x: Expr, inelastic: Expr, elastic: Expr, moment: Expr) -> list[Check]:
    """Eq F11-3's check where Lb d/t^2 <= 1.9 E/Fy and Eq F11-4's above, each capped by Mp."""
    limit = mul(ctx.const("aisc360.f11.inelastic_limit"), div(ctx.const("aisc360.E"), ctx.mat(grade, "fy")))
    return [
        Check(f"{name}: lateral-torsional buckling, Lb d/t^2 <= 1.9 E/Fy (F11, {cb})", (moment,), inelastic,
              "aisc360.j4_5", "_y", (add(sub(limit, x), ctx.const(L.STRICT_RATIO)),), unit="kip-in"),
        Check(f"{name}: lateral-torsional buckling, Lb d/t^2 > 1.9 E/Fy (F11, {cb})", (moment,), elastic,
              "aisc360.j4_5", "_y", (sub(x, limit),), unit="kip-in"),
    ]


def gen_ductility(ctx: Ctx, geo: Geometry) -> list[Check]:
    sp = geo.single_plate
    if sp is None or sp.form != "conventional":
        return []
    return [
        Check("plate: plate or beam web at most d/2 + 1/16 in thick (Manual Part 10)", (Min((sp.tp, sp.tw)),),
              add(div(sp.d_bolt, c(2)), ctx.const("aisc_manual.p10.ductile_allowance")), unit="in", group=None, suffix="",
              guards=()),
        Check("plate: fillet at least 5/8 of the plate thickness (Manual Part 10)", (mul(ctx.const("aisc_manual.p10.weld_ratio"), sp.tp),), sp.weld_size, unit="in", group=None, suffix="", guards=()),
        *(Check(f"{what}: horizontal edge distance at least 2d (Manual Part 10)",
                (mul(ctx.const("aisc_manual.p10.edge_ratio"), sp.d_bolt),), leh, unit="in", group=None, suffix="", guards=())
          for what, leh in (("plate", sp.plate_edge), ("beam web", sp.beam_edge))),
    ]


def gen_extended_ductility(ctx: Ctx, geo: Geometry) -> list[Check]:
    """Manual Part 10, extended single plate: the fillet at least 5/8 tp, and tp at most
    tmax = 6 Mmax / (Fy L^2), Mmax = (Fnv / 0.90) Ab C', C' = Ip / r_max for the bolt group
    under pure moment (elastic)."""
    sp = geo.single_plate
    if sp is None or sp.form != "extended":
        return []
    g = sp.gauge if sp.gauge is not None else c(0)
    n = sp.rows * sp.cols
    ip = M.polar_moment(c(n), sp.rows, sp.cols, sp.pitch, g)
    rmax = M.corner_radius(sp.rows, sp.cols, sp.pitch, g)
    mmax = mul(div(_fnv(ctx, sp.bolts), ctx.const("aisc_manual.p10.fnv_divisor")), L.bolt_area(sp.d_bolt), div(ip, rmax))
    # the thickness at which the plate's yield moment Fy t L^2 / 6 reaches Mmax
    tmax = M.rectangle_elastic_thickness(mmax, ctx.mat(sp.grade, "fy"), sp.depth)
    return [
        Check("plate: fillet at least 5/8 of the plate thickness (Manual Part 10)", (mul(ctx.const("aisc_manual.p10.weld_ratio"), sp.tp),), sp.weld_size, unit="in", group=None, suffix="", guards=()),
        Check("plate: no thicker than tmax, so it yields before the bolts fracture (Manual Part 10)", (sp.tp,), tmax, unit="in", group=None, suffix="", guards=()),
    ]


# --- Seats ----------------------------------------------------------------------------------------

def _required_bearing(ctx: Ctx, f: Concentrated) -> Expr:
    """The bearing length an end reaction needs (Manual Part 10, unstiffened seats): the
    least lb at which web local yielding (Eq J10-3) and web crippling at the end (Eqs J10-5a
    and J10-5b) carry the reaction, but not less than k. Each strength rises linearly in lb,
    so each inverts in closed form; the crippling strength is the larger of 5a and 5b, so
    its inverse is the smaller of theirs. The seat's flexure arm uses this length; the J10
    checks at the available length show it fits on the seat."""
    d, tw, tf, k = (ctx.shape(f.shape, p) for p in ("d", "tw", "tf", "kdes"))
    fy, e = ctx.mat(f.grade, "fy"), ctx.const("aisc360.E")
    yielding = sub(div(ctx.required(f.force, "aisc360.j10_2", suffix=""), mul(fy, tw)), mul(ctx.const("aisc360.j10_2.end"), k))
    ratio = div(tw, tf)
    unit = mul(ctx.const("aisc360.j10_3.end"), sq(tw), Sqrt(div(mul(e, fy, tf), tw)))      # 0.40 tw^2 sqrt(E Fy tf / tw)
    excess = div(sub(div(ctx.required(f.force, "aisc360.j10_3", suffix=""), unit), c(1)), mul(ratio, Sqrt(ratio)))
    short = div(mul(excess, d), ctx.const("aisc360.j10_3.bearing"))                         # J10-5a solved for lb
    long = div(mul(add(excess, ctx.const("aisc360.j10_3.long_offset")), d), ctx.const("aisc360.j10_3.long_bearing"))  # J10-5b
    return Max((yielding, Min((short, long)), k))


def gen_seat_flexure(ctx: Ctx, geo: Geometry) -> list[Check]:
    seat = geo.seat
    if seat is None:
        return []
    beam = geo.forces[0]
    lb = Min((seat.lb, _required_bearing(ctx, beam)))
    arm = sub(add(seat.setback, div(lb, c(2))), add(seat.t, ctx.const("aisc_manual.seat.critical_offset")))
    return [Check("seat angle: flexural yielding of the outstanding leg at its critical section (Manual Part 10)",
                  (mul(seat.force, arm),), L.flexural_yield(ctx.mat(seat.grade, "fy"), M.rectangle_plastic_modulus(seat.length, seat.t)),
                  "aisc360.j4_5", "_y", unit="kip-in", guards=())]


def gen_bearing(ctx: Ctx, geo: Geometry) -> list[Check]:
    st = geo.stiffener
    if st is None:
        return []
    apb = mul(sub(st.width, ctx.const("aisc_manual.seat.stiffener_clip")), st.t)
    # J7 gives the bearing strength of the surfaces in contact: the stiffener's fitted top
    # edge and the seat plate on it, each of which yields locally at its own Fy.
    return [Check("stiffener: bearing on its fitted top edge (J7)", (st.force,), L.bearing_milled(ctx.const, ctx.mat(st.grade, "fy"), apb),
                  "aisc360.j7", suffix="", guards=(), unit="kip"),
            Check("seat plate: bearing on the stiffener's fitted top edge (J7)", (st.force,),
                  L.bearing_milled(ctx.const, ctx.mat(st.seat_grade, "fy"), apb), "aisc360.j7", suffix="", guards=(), unit="kip")]


def gen_compression(ctx: Ctx, geo: Geometry) -> list[Check]:
    st = geo.stiffener
    if st is None:
        return []
    limit = mul(ctx.const("aisc360.b4_1a.case1"), Sqrt(div(ctx.const("aisc360.E"), ctx.mat(st.grade, "fy"))))
    return [Check("stiffener: compressive yielding of its section under the seat (J4.4)", (st.force,),
                  L.compression(ctx.mat(st.grade, "fy"), mul(st.width, st.t)), "aisc360.j4_4", suffix="", guards=(), unit="kip"),
            Check("stiffener: width-to-thickness at most 0.56 sqrt(E / Fy), so it yields before it buckles locally "
                  "(Manual Part 10)", (div(st.width, st.t),), limit, unit="1", group=None, suffix="", guards=()),
            Check("stiffener: at least the beam web's thickness times Fy of the beam over Fy of the stiffener "
                  "(Manual Part 10)", (mul(st.beam_tw, div(ctx.mat(st.beam_grade, "fy"), ctx.mat(st.grade, "fy"))),), st.t,
                  unit="in", group=None, suffix="", guards=())]


# --- Bracket plates (Manual Part 15) ------------------------------------------------------------------

def gen_bracket_edge(ctx: Ctx, geo: Geometry) -> list[Check]:
    """A shaped bracket's free-edge section B-B: shear yielding (Manual Eq 15-7), and the
    normal force and moment on it with the edge's local buckling (Eqs 15-8 to 15-18), one
    check per branch of Q, the boundary lambda = 1.41 belonging to the stocky branch."""
    br = geo.bracket
    if br is None or br.b is None:
        return []
    sin, cos, a1, b1 = L.bracket_section(br.a, br.b)
    fy = ctx.mat(br.grade, "fy")
    out = [Check("bracket plate: shear yielding of the free-edge section B-B (Manual Eq 15-7)", (mul(br.force, sin),),
                 L.shear_yield(ctx.const, fy, mul(br.t, b1)), "aisc360.j4_2", "_y", guards=(), unit="kip")]
    lam = L.bracket_lambda(ctx.const, a1, b1, br.t, fy)
    # N = P cos theta and M = P e - N b'/2 = P (e - cos theta b'/2): the force is factored
    # out so the interaction is linear in it, which interval enclosure keeps tight.
    lever = sub(br.e, div(mul(cos, b1), c(2)))
    slender = ctx.const("aisc_manual.p15.lambda_slender")
    for q, guard, which in ((L.bracket_q_stocky(ctx.const, lam), add(sub(slender, lam), ctx.const(L.STRICT_RATIO)), "lambda <= 1.41"),
                            (L.bracket_q_slender(ctx.const, lam), sub(lam, slender), "lambda > 1.41")):
        fcr = mul(q, fy)
        nc = ctx.available(mul(fcr, br.t, b1), "aisc360.j4_4", suffix="")
        mc = ctx.available(mul(fcr, M.rectangle_plastic_modulus(br.t, b1)), "aisc360.j4_5", "_y")
        out.append(Check(f"bracket plate: normal force and moment on the free-edge section B-B with its local buckling, "
                         f"{which} (Manual Eqs 15-8 to 15-18)", (mul(br.force, add(div(cos, nc), div(Max((lever, sub(c(0), lever))), mc))),), c(1),
                         guards=(guard,), unit="1", group=None, suffix=""))
    return out


# --- J10 --------------------------------------------------------------------------------------------------

def gen_web_local_yielding(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for f in geo.forces:
        d, tw, k = (ctx.shape(f.shape, p) for p in ("d", "tw", "kdes"))
        fy = ctx.mat(f.grade, "fy")
        out.append(Check(f"{f.name} web: web local yielding away from the member end (J10.2)", (f.force,),
                         L.web_local_yielding(ctx.const, fy, tw, k, f.lb, False), "aisc360.j10_2", suffix="", guards=(), unit="kip"))
        if f.end_distance is not None:
            # Eq J10-3 applies where the force is at most d from the end; excused beyond d.
            out.append(Check(f"{f.name} web: web local yielding within d of the member end (J10.2)", (f.force,),
                             L.web_local_yielding(ctx.const, fy, tw, k, f.lb, True), "aisc360.j10_2",
                             guards=(add(sub(d, f.end_distance), ctx.const(L.STRICT)),), suffix="", unit="kip"))
    return out


def _end_crippling(short: Expr, long: Expr) -> Expr:
    """Eq J10-5a applies for lb/d <= 0.2 and J10-5b above. They meet at lb/d = 0.2 and the
    one that applies is the larger (3x >= 4x - 0.2 exactly when x <= 0.2), so the end
    strength is their maximum."""
    return Max((short, long))


def gen_web_crippling(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for f in geo.forces:
        if f.tensile:
            continue
        d, tw, tf = (ctx.shape(f.shape, p) for p in ("d", "tw", "tf"))
        e, fy = ctx.const("aisc360.E"), ctx.mat(f.grade, "fy")
        out.append(Check(f"{f.name} web: web local crippling away from the member end (J10.3)", (f.force,),
                         L.web_crippling(ctx.const, e, fy, tw, tf, d, f.lb, "interior"), "aisc360.j10_3", suffix="", guards=(), unit="kip"))
        if f.end_distance is not None:
            end = _end_crippling(L.web_crippling(ctx.const, e, fy, tw, tf, d, f.lb, "end_short"),
                                 L.web_crippling(ctx.const, e, fy, tw, tf, d, f.lb, "end_long"))
            # Eqs J10-5 apply where the force is less than d/2 from the end; excused from d/2 on.
            out.append(Check(f"{f.name} web: web local crippling within d/2 of the member end (J10.3)", (f.force,), end, "aisc360.j10_3",
                             guards=(sub(div(d, c(2)), f.end_distance),), suffix="", unit="kip"))
    return out


def gen_flange_local_bending(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for f in geo.forces:
        if not f.tensile:
            continue
        tf = ctx.shape(f.shape, "tf")
        rn = L.flange_local_bending(ctx.const, ctx.mat(f.grade, "fy"), tf)
        out.append(Check(f"{f.name} flange: flange local bending (J10.1)", (f.force,), rn, "aisc360.j10_1", suffix="", guards=(), unit="kip"))
        if f.end_distance is not None:
            # Halved where the force is less than 10 tf from the end; excused from 10 tf on.
            out.append(Check(f"{f.name} flange: flange local bending within 10 tf of the member end (J10.1)", (f.force,), div(rn, c(2)),
                             "aisc360.j10_1", guards=(sub(mul(ctx.const("aisc360.j10_1.end_distance"), tf), f.end_distance),), suffix="", unit="kip"))
    return out


def gen_web_sidesway_buckling(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for f in geo.forces:
        if f.tensile or f.pair or f.restrained is None or f.unbraced is None:
            continue
        d, tw, tf, bf, k = (ctx.shape(f.shape, p) for p in ("d", "tw", "tf", "bf", "kdes"))
        h = sub(d, mul(c(2), k))
        cr = ctx.const("aisc360.j10_4.cr_below_my" if f.below_yield else "aisc360.j10_4.cr_at_my")
        rn, r = L.web_sidesway(ctx.const, cr, tw, tf, h, f.unbraced, bf, f.restrained)
        limit = ctx.const("aisc360.j10_4.restrained_limit" if f.restrained else "aisc360.j10_4.unrestrained_limit")
        # The limit state does not apply where r exceeds the limit; excused beyond it.
        out.append(Check(f"{f.name} web: web sidesway buckling where its slenderness ratio makes it apply (J10.4)", (f.force,), rn,
                         "aisc360.j10_4", guards=(add(sub(limit, r), ctx.const(L.STRICT_RATIO)),), suffix="", unit="kip"))
    return out


def gen_web_compression_buckling(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for f in geo.forces:
        if f.tensile or not f.pair:
            continue
        d, tw, k = (ctx.shape(f.shape, p) for p in ("d", "tw", "kdes"))
        h = sub(d, mul(c(2), k))
        rn = L.web_compression_buckling(ctx.const, ctx.const("aisc360.E"), ctx.mat(f.grade, "fy"), tw, h)
        out.append(Check(f"{f.name} web: web compression buckling (J10.5)", (f.force,), rn, "aisc360.j10_5", suffix="", guards=(), unit="kip"))
        if f.end_distance is not None:
            # Halved where the pair is less than d/2 from the end; excused from d/2 on.
            out.append(Check(f"{f.name} web: web compression buckling within d/2 of the member end (J10.5)", (f.force,), div(rn, c(2)),
                             "aisc360.j10_5", guards=(sub(div(d, c(2)), f.end_distance),), suffix="", unit="kip"))
    return out


def gen_panel_zone(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for f in geo.forces:
        if f.panel_shear is None:
            continue
        d, tw, area = (ctx.shape(f.shape, p) for p in ("d", "tw", "A"))
        fy = ctx.mat(f.grade, "fy")
        alpha = c(1) if ctx.lrfd else ctx.const("aisc360.j10_6.alpha_asd")
        # build.NEEDS has the case give the axial force; tension or compression, its magnitude
        pr = Abs(f.axial) if f.axial is not None else c(0)
        rn = L.panel_zone(ctx.const, fy, d, tw, pr, mul(fy, area), alpha)
        out.append(Check(f"{f.name} web: panel-zone web shear (J10.6)", (f.panel_shear,), rn, "aisc360.j10_6", suffix="", guards=(), unit="kip"))
    return out


# --- Prying -----------------------------------------------------------------------------------------------

def gen_prying(ctx: Ctx, geo: Geometry) -> list[Check]:
    out = []
    for itf in geo.interfaces:
        if itf.tension is None:
            continue
        d = ctx.const(f"bolt_us.{itf.bolts.size}.d")
        # Manual Part 9: under shear as well, B is the tension J3.8 leaves the bolt, F'nt Ab
        # (Companion II.A-1B); F'nt is Fnt wherever J3.8 exempts a small shear stress
        if itf.shear is None:
            fnt = ctx.mat(itf.bolts.group, "Fnt")
        else:
            *_, fnt = _fnt_prime(ctx, itf)
        b_avail = ctx.available(L.bolt_tension(fnt, d), "rcsc2025.s5_1", suffix="")
        phi = ctx.const("aisc360.j4_5.phi_y") if ctx.lrfd else div(c(1), ctx.const("aisc360.j4_5.omega_y"))
        for pr in itf.prying:
            # delta = 1 - d'/p: the hole takes its length along the flange, the direction p runs
            # (a parallel slot's length)
            _, dh_along, _ = bolt_dims(ctx, itf.bolts, pr.hole)
            for which, p in pr.p:
                avail = L.prying_available(ctx.const, b_avail, d, dh_along, p, pr.b, pr.a, pr.t, ctx.mat(pr.grade, "fu"), phi)
                out.append(Check(f"{itf.name}: bolt tension with prying of the {pr.name} at {which} (Manual Part 9, "
                                 "Figure 9-4; Kulak 17.5)", (div(itf.tension, c(itf.n)),), avail, group=None, suffix="", guards=(), unit="kip"))
    return out


# --- Fit of the drawn parts ----------------------------------------------------------------------------

def _fit(fit: G.Fit) -> Check:
    return Check(fit.what, (fit.need,), fit.have, unit="in", group=None, suffix="", guards=fit.guards)


def gen_beam_fit(ctx: Ctx, geo: Geometry) -> list[Check]:
    return [_fit(f) for f in G.fits(ctx).beam]


def _face_fits(ctx: Ctx, face: str) -> list[Check]:
    support = ctx.conn.get("support")
    if not isinstance(support, Member) or support.face != face:
        return []
    return [_fit(f) for f in G.fits(ctx).face]


def gen_flange_fit(ctx: Ctx, geo: Geometry) -> list[Check]:
    return _face_fits(ctx, "flange")


def gen_web_fit(ctx: Ctx, geo: Geometry) -> list[Check]:
    return _face_fits(ctx, "web")


GENERATORS: Mapping[str, Callable[[Ctx, Geometry], list[Check]]] = {
    "bolts": gen_bolts, "slip": gen_slip, "bolt_tension": gen_bolt_tension, "bolt_combined": gen_bolt_combined,
    "shear_yield": gen_shear_yield, "shear_rupture": gen_shear_rupture, "block_shear": gen_block_shear,
    "tension_yield": gen_tension_yield, "tension_rupture": gen_tension_rupture,
    "flexural_yield": gen_flexural_yield, "flexural_rupture": gen_flexural_rupture,
    "weld": gen_weld, "weld_base_metal": gen_weld_base_metal, "fillet_size": gen_fillet_size,
    "spacing_min": gen_spacing_min, "edge_min": gen_edge_min, "spacing_max": gen_spacing_max, "edge_max": gen_edge_max,
    "hole_use": gen_hole_use, "joint_type": gen_joint_type, "clearance": gen_clearance,
    "cope_buckling": gen_cope_buckling, "plate_buckling": gen_plate_buckling, "ductility": gen_ductility,
    "extended_ductility": gen_extended_ductility, "seat_flexure": gen_seat_flexure, "bearing": gen_bearing,
    "compression": gen_compression,
    "web_local_yielding": gen_web_local_yielding, "web_crippling": gen_web_crippling,
    "flange_local_bending": gen_flange_local_bending, "web_sidesway_buckling": gen_web_sidesway_buckling,
    "web_compression_buckling": gen_web_compression_buckling, "panel_zone": gen_panel_zone, "prying": gen_prying,
    "bracket_edge": gen_bracket_edge,
    "beam_fit": gen_beam_fit, "flange_fit": gen_flange_fit, "web_fit": gen_web_fit,
}


# --- Validity rows -------------------------------------------------------------------------------------------

def _row_cope_length(ctx: Ctx, geo: Geometry) -> tuple[tuple[Expr, ...], str]:
    cg = geo.cope
    return (sub(cg.c, mul(ctx.const("aisc_manual.p9.cope_length"), cg.d)),), "the cope is no longer than twice the beam depth"


def _row_cope_depth(ctx: Ctx, geo: Geometry) -> tuple[tuple[Expr, ...], str]:
    cg = geo.cope
    half = mul(ctx.const("aisc_manual.p9.cope_depth"), cg.d)
    exprs = (sub(cg.dc, half),) if cg.dcb is None else (sub(cg.dc, half), sub(cg.dcb, half))
    return exprs, "each cope is no deeper than half the beam"


def _row_conventional_a(ctx: Ctx, geo: Geometry) -> tuple[tuple[Expr, ...], str]:
    return ((sub(geo.single_plate.a, ctx.const("aisc_manual.p10.conventional_a")),),
            "the bolt line is no farther than 3.5 in from the weld line")


def _row_conventional_rows(ctx: Ctx, geo: Geometry) -> tuple[tuple[Expr, ...], str]:
    return ((sub(ctx.count("rows", geo.single_plate.rows), ctx.const("aisc_manual.p10.conventional_rows")),),
            "the plate has no more than 12 bolt rows")


def _row_both_faces(ctx: Ctx, geo: Geometry) -> tuple[tuple[Expr, ...], str]:
    """Manual Part 10's single-plate configurations weld the plate on both faces, which their
    five-eighths rule sizes; a plate welded on one face is outside them."""
    return (sub(c(2), c(geo.single_plate.sides)),), "the plate is welded to the support on both faces"


def _row_bolt_clear_of_stem(ctx: Ctx, geo: Geometry) -> tuple[tuple[Expr, ...], str]:
    itf = next(i for i in geo.interfaces if i.prying)
    d = ctx.const(f"bolt_us.{itf.bolts.size}.d")
    return (tuple(sub(div(d, c(2)), pr.b) for pr in itf.prying),
            "each bolt line lies outside the web it bends about (the tee's stem, the support's web) by more than half a bolt diameter")


ROWS: Mapping[str, Callable[[Ctx, Geometry], tuple[tuple[Expr, ...], str]]] = {
    "steel.cope_buckling.cope_length": _row_cope_length,
    "steel.cope_buckling.cope_depth": _row_cope_depth,
    "steel.ductility.conventional_a": _row_conventional_a,
    "steel.ductility.conventional_rows": _row_conventional_rows,
    "steel.ductility.both_faces": _row_both_faces,
    "steel.extended_ductility.both_faces": _row_both_faces,
    "steel.prying.bolt_clear_of_stem": _row_bolt_clear_of_stem,
}
"""Each validity row's statement: expressions that are all <= 0 where the model applies."""
