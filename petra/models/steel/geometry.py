"""Where a connection's parts sit, and the fits that follow. Trusted.

A connection's attribute lines draw its parts. This module places them in one frame per
connection, in exact rationals (kernel Exprs over the design's hypotheses), along three
axes:

  depth   down from the beam's top. The beam web is flat between its fillets, from kdes
          to d - kdes (the shapes table's detailing value; Manual Part 1 tabulates the
          flat depth T = d - 2 kdes). A plate, angle or tee bolted to the web spans Lev
          above its top row to Lev below its bottom row, its holes dh/2 either side (dh
          the hole's size along the force). A cope removes the flange it cuts, so a part
          the cope runs past is free at that flange, and the holes stop at the cut. A
          seat's vertical leg runs down from its heel.
  out     out from the support face along the beam. The beam end stands at the bolt line
          less the beam's end distance (a seat's beam end at its setback); a cope starts
          there, or at the setback where that is farther out, and runs its length; a part
          reaches its far edge (a plate's a + (columns - 1) g + Leh, an angle's leg on the
          beam, a tee's stem, d/2 of its parent).
  across  across the support face, from one edge of the room on it. A flange is bf wide; a
          column's web is flat for d - 2 kdes between its fillets (beyond them stand the
          flanges). A pair of bolt lines is centred on the member at gauge g; a part placed
          by the lines alone (a single angle, a plate set on edge, a bracket's bolt
          columns) goes wherever it fits best, so it needs only its width.

A Span is a part's extent on one axis, a Room where spans must lie; each containment is a
Fit, `need <= have` in inches, excused where any guard is <= 0. `fits(ctx)` gives a
connection's fits in two lists: the beam side and the beam against the support
(beam_fit), and the support's face (flange_fit or web_fit, by the face). Every support
connected on its web is read as a column whose flanges the beam passes between, a premise
web_fit's model states. A fit that is plain geometry cites "geometry"; one that reads the
flat web cites Manual Part 1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from ...kernel import Expr, Max
from ...mechanics import add, c, div, mul, sub
from . import limits as L
from .lower import AngleSpec, Bolts, Conn, Cope, Geo, Member, PlateSpec, TeeSpec, Weld

HOLE_DIMS = {
    "std": ("std", "std"), "ovs": ("ovs", "ovs"), "ssl": ("ssl_w", "ssl_l"), "lsl": ("lsl_w", "lsl_l"),
    "ssl_parallel": ("ssl_l", "ssl_w"), "lsl_parallel": ("lsl_l", "lsl_w"),
}
"""Hole type -> (dimension along the vertical force, across it). A slot named plainly runs
across the force (perpendicular); `_parallel` runs along it (Table J3.3)."""

ALONG, ACROSS = 0, 1
"""Index into HOLE_DIMS: a hole's size down the depth axis, and across the face."""

FLAT = "Manual Part 1"
PLAIN = "geometry"


class Reads(Protocol):
    """What the fits read of a statement's builder (checks.Ctx)."""

    conn: Conn

    def geo(self, value: Geo, name: str) -> Expr: ...

    def attr(self, key: str) -> Expr: ...

    def shape(self, shape: str, prop: str) -> Expr: ...

    def const(self, name: str) -> Expr: ...

    def hole(self, ply: str) -> str: ...


@dataclass(frozen=True)
class Span:
    """A part's extent on one axis, from lo to hi, its ends named for reports."""

    part: str           # "plate", "bolt holes"
    lo_end: str         # "top edge"
    hi_end: str         # "bottom edge"
    lo: Expr
    hi: Expr


@dataclass(frozen=True)
class Room:
    """Where spans on one axis must lie, from lo to hi."""

    what: str           # "the beam's flat web"
    lo: Expr
    hi: Expr
    cite: str


@dataclass(frozen=True)
class Fit:
    """One containment: `need <= have`, in inches, excused where any guard is <= 0."""

    what: str
    need: Expr
    have: Expr
    guards: tuple[Expr, ...]


@dataclass(frozen=True)
class Fits:
    beam: tuple[Fit, ...]      # beam_fit
    face: tuple[Fit, ...]      # flange_fit or web_fit, by the support's face


def hole_size(ctx: Reads, bolts: Bolts, ply: str, axis: int) -> Expr:
    """A hole's size in `ply` along the force (ALONG) or across it (ACROSS), Table J3.3."""
    return ctx.const(f"bolt_us.{bolts.size}.{HOLE_DIMS[ctx.hole(ply)][axis]}")


def _w(ctx: Reads, member: Member) -> dict[str, Expr]:
    return {p: ctx.shape(member.shape, p) for p in ("d", "tw", "tf", "bf", "kdes")}


def inside(owner: str, span: Span, room: Room, free_lo: tuple[Expr, ...], free_hi: tuple[Expr, ...]) -> tuple[Fit, Fit]:
    """The span lies in the room: its low end at or past the room's, its high end short of
    the room's, each excused by its own guards."""
    return (Fit(f"{owner}: {span.lo_end} on {room.what} ({room.cite})", room.lo, span.lo, free_lo),
            Fit(f"{owner}: {span.hi_end} on {room.what} ({room.cite})", span.hi, room.hi, free_hi))


def across(owner: str, what: str, width: Expr, room: Room) -> Fit:
    """Something placed wherever it fits best across the face (or centred on it), from one
    edge of the room: its width within the room's, which runs from 0."""
    return Fit(f"{owner}: {what} within {room.what} ({room.cite})", width, room.hi, ())


# --- The beam side ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Cut:
    """The copes as the depth axis sees them: each cut's depth (None: that flange is not
    coped)."""

    top: Expr | None
    bottom: Expr | None


def _cut(ctx: Reads) -> Cut:
    cope: Cope | None = ctx.conn.get("cope")
    if cope is None:
        return Cut(None, None)
    dc = ctx.geo(cope.depth, "cope.depth")
    if cope.flanges == "top":
        return Cut(dc, None)
    return Cut(dc, dc if cope.bottom is None else ctx.geo(cope.bottom, "cope.bottom_depth"))


def _past(ctx: Reads, reach: Expr, end: Expr) -> Expr:
    """<= 0 where the cope runs past the part's far edge, `reach` out from the support face.
    The beam end stands `end` out; the cope starts there, or at the setback where that is
    farther out (a coped beam states its setback), the reading most favourable to the cope
    reaching past the part, and runs its length."""
    cope: Cope = ctx.conn.attrs["cope"]
    start = Max((ctx.attr("setback"), end)) if "setback" in ctx.conn.attrs else end
    return sub(reach, add(start, ctx.geo(cope.length, "cope.length")))


def _band(beam: Mapping[str, Expr], cut: Cut) -> Room:
    """The flat web the copes leave: below the fillet and any top cut, above the fillet and
    any bottom cut."""
    k = beam["kdes"]
    lo = k if cut.top is None else Max((k, cut.top))
    hi = sub(beam["d"], k if cut.bottom is None else Max((k, cut.bottom)))
    return Room("the flat web the copes leave" if cut.top is not None else "the flat web", lo, hi, FLAT)


def _freed(beam: Mapping[str, Expr], depth: Expr | None, past: Expr | None) -> tuple[Expr, ...]:
    """A part's edge at a coped flange is free where the cut clears the fillet (depth >=
    kdes) and the cope runs past the part."""
    return () if depth is None or past is None else (Max((sub(beam["kdes"], depth), past)),)


def on_beam_web(ctx: Reads, part: str, reach: Expr, end: Expr) -> list[Fit]:
    """A part bolted to the beam web, `reach` out from the support face, on a beam whose end
    stands `end` out: the part and the beam's holes on the flat web."""
    conn = ctx.conn
    beam = _w(ctx, conn.attrs["beam"])
    rows = conn.attrs["rows"]
    top, s, lev = ctx.attr("top"), ctx.attr("pitch"), ctx.attr("edge_vertical")
    last = add(top, mul(c(rows - 1), s))
    dh = hole_size(ctx, conn.attrs["bolts"], "beam", ALONG)
    cut = _cut(ctx)
    past = None if cut.top is None else _past(ctx, reach, end)
    web = Room("the beam's flat web", beam["kdes"], sub(beam["d"], beam["kdes"]), FLAT)
    body = Span(part, "top edge", "bottom edge", sub(top, lev), add(last, lev))
    holes = Span("bolt holes", "top bolt hole", "bottom bolt hole", sub(top, div(dh, c(2))), add(last, div(dh, c(2))))
    return [*inside(part, body, web, _freed(beam, cut.top, past), _freed(beam, cut.bottom, past)),
            *inside("beam web", holes, _band(beam, cut), (), ())]


def end_plate_welds(ctx: Reads) -> Fit:
    """An end plate's welds, placed wherever they fit best down the web: their length
    within the flat web the copes leave."""
    conn = ctx.conn
    beam = _w(ctx, conn.attrs["beam"])
    weld: Weld = conn.attrs["weld"]
    w = ctx.geo(weld.size, "weld.size")
    rows, s, lev = conn.attrs["rows"], ctx.attr("pitch"), ctx.attr("edge_vertical")
    length = sub(add(mul(c(rows - 1), s), mul(c(2), lev)), mul(c(2), w))
    band = _band(beam, _cut(ctx))
    return Fit(f"beam web: the end plate's welds within {band.what} ({FLAT})", length, sub(band.hi, band.lo), ())


def beam_end(what: str, need: Expr, have: Expr) -> Fit:
    """The beam end, where its bolt line and end distance put it, stands clear of the support."""
    return Fit(f"beam web: {what} ({PLAIN})", need, have, ())


def lands(ctx: Reads, on: str, projection: Expr) -> Fit:
    """A seated beam's end, its setback as detailed out from the support face, lands on a
    seat projecting `projection`: strictly short of its edge."""
    return Fit(f"beam web: the beam end, at its setback, lands on the {on} ({PLAIN})",
               add(ctx.attr("setback"), ctx.const(L.STRICT)), projection, ())


# --- The support's face ------------------------------------------------------------------------------


def face_room(ctx: Reads) -> tuple[str, dict[str, Expr], Room]:
    """(face, the support's dimensions, the room across it): a flange's width, or the flat
    of a column's web between its fillets."""
    support: Member = ctx.conn.attrs["support"]
    sp = _w(ctx, support)
    if support.face == "flange":
        return "flange", sp, Room("the flange's width", c(0), sp["bf"], PLAIN)
    return "web", sp, Room("the web's flat between its fillets", c(0), sub(sp["d"], mul(c(2), sp["kdes"])), FLAT)


def pair(ctx: Reads, owner: str, gauge: Expr, bolts: Bolts) -> list[Fit]:
    """Two bolt lines centred on the support at `gauge`: their holes on the face and, on a
    flange, clear of the web behind it."""
    face, sp, room = face_room(ctx)
    dh = hole_size(ctx, bolts, "support", ACROSS)
    out = [across(owner, "the bolt lines' holes", add(gauge, dh), room)]
    if face == "flange":
        out.append(Fit(f"{owner}: the bolt lines' holes clear of the web between them ({PLAIN})", sp["tw"], sub(gauge, dh), ()))
    return out


def part_on_web(ctx: Reads, owner: str, what: str, width: Expr) -> list[Fit]:
    """A part's body across the face: on a web it stands between the fillets; on a flange it
    may overhang the tips, so it needs nothing."""
    face, _, room = face_room(ctx)
    return [across(owner, what, width, room)] if face == "web" else []


def bracket_columns(ctx: Reads, owner: str) -> list[Fit]:
    """A bracket's bolt columns, `columns` at gauge g, placed by the lines nowhere in
    particular. On a web they and the plate need its flat. On a flange some placement must
    put every hole on the flange and clear of the web: all columns on one side, (columns -
    1) g + dh <= (bf - tw)/2; failing that, a split straddling the web, which needs g >= tw
    + dh, (columns - 1) g + dh <= bf and (ceil(columns/2) - 1) g + dh <= (bf - tw)/2 (the
    larger part, ceil(columns/2) columns, on one side)."""
    conn = ctx.conn
    face, sp, room = face_room(ctx)
    columns = conn.attrs["columns"]
    g = ctx.attr("gauge")
    dh = hole_size(ctx, conn.attrs["bolts"], "support", ACROSS)
    group = add(mul(c(columns - 1), g), dh)
    if face == "web":
        plate = add(mul(c(columns - 1), g), mul(c(2), ctx.attr("plate_edge")))
        return [across(owner, "the bracket's bolt columns", group, room), across(owner, "the bracket plate", plate, room)]
    side = div(sub(sp["bf"], sp["tw"]), c(2))
    straddle = ()
    if columns > 1:
        larger = (columns + 1) // 2
        straddle = (Max((sub(add(sp["tw"], dh), g), sub(group, sp["bf"]), sub(add(mul(c(larger - 1), g), dh), side))),)
    return [Fit(f"{owner}: some placement of the bracket's bolt columns puts every hole on the flange, clear of the web "
                f"({PLAIN})", group, side, straddle)]


def welds_across(ctx: Reads, owner: str, what: str, width: Expr) -> list[Fit]:
    """Welds on the face, placed wherever they fit best: on a flange or a web's flat."""
    _, _, room = face_room(ctx)
    return [across(owner, what, width, room)]


def beam_between_flanges(ctx: Reads, owner: str, end: Expr) -> list[Fit]:
    """A beam framing to a column's web passes between its flanges, unless its end, `end`
    out from the web, lies at or past the flange tips (bf - tw)/2 out."""
    face, sp, _ = face_room(ctx)
    if face != "web":
        return []
    beam = _w(ctx, ctx.conn.attrs["beam"])
    tips = div(sub(sp["bf"], sp["tw"]), c(2))
    return [Fit(f"{owner}: the beam's flange passes between the column's flanges ({PLAIN})", beam["bf"],
                sub(sp["d"], mul(c(2), sp["tf"])), (sub(tips, end),))]


def seat_leg(ctx: Reads, vertical: Expr, t: Expr) -> list[Fit]:
    """A seat's bolt holes on its vertical leg, down from the heel: the top one below the
    outstanding leg's thickness, the bottom one on the leg."""
    conn = ctx.conn
    rows, s, lev = conn.attrs["rows"], ctx.attr("pitch"), ctx.attr("edge_vertical")
    dh = hole_size(ctx, conn.attrs["bolts"], "angle", ALONG)
    holes = Span("bolt holes", "top bolt hole", "bottom bolt hole", sub(lev, div(dh, c(2))),
                 add(add(lev, mul(c(rows - 1), s)), div(dh, c(2))))
    return list(inside("seat angle", holes, Room("its vertical leg, below the outstanding leg", t, vertical, PLAIN), (), ()))


# --- The kinds ------------------------------------------------------------------------------------------


def _support_face(ctx: Reads) -> str:
    return f"support {ctx.conn.attrs['support'].face}"


def _angle_legs(ctx: Reads, angle: AngleSpec) -> tuple[Expr, Expr, Expr]:
    """(leg on the beam or the vertical leg, outstanding leg, thickness)."""
    long, short, t = (ctx.shape(angle.shape, p) for p in ("d", "b", "t"))
    return (short, long, t) if angle.outstanding == "long" else (long, short, t)


def _weld_size(ctx: Reads, key: str) -> tuple[Expr, Weld]:
    weld: Weld = ctx.conn.attrs[key]
    return ctx.geo(weld.size, f"{key}.size"), weld


def shear_tab(ctx: Reads) -> Fits:
    conn = ctx.conn
    owner = _support_face(ctx)
    a, leh_b, leh_p = ctx.attr("bolt_line"), ctx.attr("beam_edge"), ctx.attr("plate_edge")
    columns = conn.get("columns")
    span = mul(c(columns - 1), ctx.attr("gauge")) if columns > 1 else c(0)
    end = sub(a, leh_b)
    plate: PlateSpec = conn.attrs["plate"]
    w, weld = _weld_size(ctx, "weld")
    tp = ctx.geo(plate.thickness, "plate.thickness")
    beam = [*on_beam_web(ctx, "plate", add(add(a, span), leh_p), end),
            beam_end("the beam's end distance at most the bolt line's distance from the support face, so the beam end "
                     "stands clear of it", leh_b, a)]
    face = [*welds_across(ctx, owner, "the plate and its welds", add(tp, mul(c(weld.sides), w))),
            *beam_between_flanges(ctx, owner, end)]
    return Fits(tuple(beam), tuple(face))


def angles(ctx: Reads) -> Fits:
    conn = ctx.conn
    double = conn.kind == "double_angle"
    key = "angles" if double else "angle"
    owner = _support_face(ctx)
    beam_leg, out_leg, _ = _angle_legs(ctx, conn.attrs[key])
    tw = ctx.shape(conn.attrs["beam"].shape, "tw")
    gb, leh_b = ctx.attr("beam_gauge"), ctx.attr("beam_edge")
    end = sub(gb, leh_b)
    legs = add(mul(c(2), out_leg), tw) if double else add(out_leg, tw)
    whose = "angles'" if double else "angle's"
    beam = [*on_beam_web(ctx, key, beam_leg, end),
            beam_end(f"the beam's end distance at most the {whose} beam gauge, so the beam end stands clear of the "
                     "support face", leh_b, gb)]
    if conn.attrs["support_side"] == "bolted":
        bolts: Bolts = conn.attrs["bolts"]
        gs = ctx.attr("support_gauge")
        if double:
            face = [*pair(ctx, owner, gs, bolts), *part_on_web(ctx, owner, "the outstanding legs", legs)]
        else:
            # one angle beside the beam web: from the web's far face to its hole's far edge
            dh = hole_size(ctx, bolts, "support", ACROSS)
            face = [across(owner, "the beam web and the angle's bolt line", add(add(tw, gs), div(dh, c(2))), face_room(ctx)[2]),
                    *part_on_web(ctx, owner, "the beam web and the outstanding leg", legs)]
    else:
        w, _ = _weld_size(ctx, "support_weld")
        toes = add(legs, mul(c(2), w)) if double else add(legs, w)
        face = welds_across(ctx, owner, "the welds at the outstanding legs' toes", toes)
    return Fits(tuple(beam), (*face, *beam_between_flanges(ctx, owner, end)))


def shear_tee(ctx: Reads) -> Fits:
    conn = ctx.conn
    owner = _support_face(ctx)
    tee: TeeSpec = conn.attrs["tee"]
    tp = {p: ctx.shape(tee.parent, p) for p in ("d", "tf", "bf")}
    a, leh_b = ctx.attr("bolt_line"), ctx.attr("beam_edge")
    end = sub(a, leh_b)
    beam = [*on_beam_web(ctx, "tee stem", div(tp["d"], c(2)), end),
            beam_end("the beam's end distance and the tee flange's thickness at most the bolt line's distance, so the "
                     "beam end stands clear of the tee flange", add(leh_b, tp["tf"]), a)]
    if conn.attrs["support_side"] == "bolted":
        face = [*pair(ctx, owner, ctx.attr("support_gauge"), conn.attrs["bolts"]),
                *part_on_web(ctx, owner, "the tee flange", tp["bf"])]
    else:
        w, _ = _weld_size(ctx, "support_weld")
        face = welds_across(ctx, owner, "the welds at the tee flange's tips", add(tp["bf"], mul(c(2), w)))
    return Fits(tuple(beam), (*face, *beam_between_flanges(ctx, owner, end)))


def shear_end_plate(ctx: Reads) -> Fits:
    conn = ctx.conn
    owner = _support_face(ctx)
    plate: PlateSpec = conn.attrs["plate"]
    face = [*pair(ctx, owner, ctx.attr("support_gauge"), conn.attrs["bolts"]),
            *part_on_web(ctx, owner, "the end plate", ctx.attr("plate_width")),
            *beam_between_flanges(ctx, owner, ctx.geo(plate.thickness, "plate.thickness"))]
    return Fits((end_plate_welds(ctx),), tuple(face))


def seated(ctx: Reads) -> Fits:
    conn = ctx.conn
    owner = _support_face(ctx)
    vertical, out_leg, t = _angle_legs(ctx, conn.attrs["angle"])
    length = ctx.attr("seat_length")
    if conn.attrs["support_side"] == "bolted":
        face = [*pair(ctx, owner, ctx.attr("support_gauge"), conn.attrs["bolts"]),
                *part_on_web(ctx, owner, "the seat angle", length), *seat_leg(ctx, vertical, t)]
    else:
        w, _ = _weld_size(ctx, "support_weld")
        face = welds_across(ctx, owner, "the welds at the seat angle's ends", add(length, mul(c(2), w)))
    return Fits((lands(ctx, "seat's outstanding leg", out_leg),),
                (*face, *beam_between_flanges(ctx, owner, ctx.attr("setback"))))


def stiffened_seat(ctx: Reads) -> Fits:
    conn = ctx.conn
    owner = _support_face(ctx)
    stiffener: PlateSpec = conn.attrs["stiffener"]
    w, weld = _weld_size(ctx, "weld")
    ts = ctx.geo(stiffener.thickness, "stiffener.thickness")
    face = [*welds_across(ctx, owner, "the stiffener and its welds", add(ts, mul(c(weld.sides), w))),
            *beam_between_flanges(ctx, owner, ctx.attr("setback"))]
    return Fits((lands(ctx, "stiffener", ctx.attr("stiffener_width")),), tuple(face))


def bolt_bracket(ctx: Reads) -> Fits:
    return Fits((), tuple(bracket_columns(ctx, _support_face(ctx))))


def weld_bracket(ctx: Reads) -> Fits:
    conn = ctx.conn
    owner = _support_face(ctx)
    w, weld = _weld_size(ctx, "weld")
    if "weld_return" in conn.attrs:
        return Fits((), tuple(welds_across(ctx, owner, "the C-shaped weld's returns", add(ctx.attr("weld_return"), w))))
    plate: PlateSpec = conn.attrs["plate"]
    tp = ctx.geo(plate.thickness, "plate.thickness")
    return Fits((), tuple(welds_across(ctx, owner, "the plate and its welds", add(tp, mul(c(weld.sides), w)))))


def hanger(ctx: Reads) -> Fits:
    conn = ctx.conn
    return Fits((), tuple(pair(ctx, _support_face(ctx), ctx.attr("tee_gauge"), conn.attrs["bolts"])))


def flange_force(ctx: Reads) -> Fits:
    """No beam or connecting part is drawn: nothing to fit."""
    return Fits((), ())


KINDS = {
    "shear_tab": shear_tab,
    "double_angle": angles,
    "single_angle": angles,
    "shear_tee": shear_tee,
    "shear_end_plate": shear_end_plate,
    "seated": seated,
    "stiffened_seat": stiffened_seat,
    "flange_force": flange_force,
    "bolt_bracket": bolt_bracket,
    "weld_bracket": weld_bracket,
    "hanger": hanger,
}


def fits(ctx: Reads) -> Fits:
    """The connection's fits: the beam's, and its support face's."""
    return KINDS[ctx.conn.kind](ctx)
