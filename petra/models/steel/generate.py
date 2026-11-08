"""Generated connections for the steel deck's gate (docs/steel_connections.md §9 items 4 to
8). Tooling: nothing here changes a verdict.

`generate(n, seed, registry)` yields designs across the eleven kinds, round-robin, each a
.petra source with one connection named c1 and one load case "gate". Geometry is drawn
from the registry's shapes, the shop deck's stock plates and the grammar's options (slotted
and oversized holes, two bolt columns, copes at one or both flanges, welded or bolted
support sides, forces near a member's end, deformation and weathering). About one design
in five states one length as a toleranced bound (+-1/16 in), so the claim covers a box.

Most samples follow a detailer's rules: edges from 1-1/4 in, gauges that fit the flange,
fillets no smaller than Table J2.4's minimum for the thinner part, a shear tab no thicker
than d/2 + 1/16 in, stiffeners within their width-to-thickness limit, Group 150 bolts in
tension pretensioned; and the parts fit (docs/steel_connections.md, fit of the drawn
parts): the top row far enough down that the part clears the beam's flange and fillet,
rows that end above the bottom fillet, a beam framed to a column's web narrow enough to
pass between its flanges, parts, welds and bolt lines within the face they sit on, a seat's
holes on its vertical leg. Each rule allows for the toleranced lengths and the largest hole
the sample can draw. Such a sample whose geometry the deck still fails is drawn again.
One sample in `FREE` (a "free" one) ignores the rules and keeps whatever geometry it
draws, so some designs fail on geometry and their FAIL must carry a witness (§9 item 8).

A design in `CYCLIC` (drawn from its own stream, so the rest of the sample is unchanged)
names cycles in its gate case (Appendix 3): nSR from `CYCLE_COUNTS`, past and short of
Section 3.1's 20,000 and the categories' thresholds, as [0, n] or [n, n]. Its loads are
then the cyclic load as well, their width the range and their top the peak, and its bolts
are pretensioned unless the sample is free (a snug-tight joint under a cyclic load fails
joint_type). Only connections whose fatigue details all have an encoded category are
cyclic: a detail that owes the unmodelled fatigue_detail would leave the design UNKNOWN,
so such a draw keeps its static load alone.

Loads carry a margin. The deck's own utilisations fix the scale: the governing check that
the load changes lands at 1 - delta k (target "pass") or 1 + delta k (target "fail"), k
drawn from [1, 4], delta = 0.02, found by secant steps because u is not linear in the
load. A secondary load (a hanger's shear, a column's panel shear) keeps a fixed ratio to
the primary. Checks the load does not change (spacing, edges, fillet sizes, clearance,
ductility) decide `expected` on their own: a design whose geometry fails is a FAIL
whatever its load. A sample the deck's lowering rejects, or whose margin the scaling
cannot reach, is drawn again; `Generated.redraws` counts the draws.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Iterator

from ...lang import parse_design
from ...registry import Registry
from ...registry.steel import INCH
from ..base import ComponentError
from . import calc
from .cyclic import UNENCODED
from .domain import required
from .fatigue import GENERATORS
from .lower import CYCLES, KIND_SPECS, tee_parent

DELTA = Fraction(1, 50)
TOLERANCE = Fraction(1, 16)
FREE = 0.15
EDGE = Fraction(5, 4)

BEAMS = ("W12x26", "W14x22", "W16x26", "W16x31", "W18x35", "W18x50", "W21x44", "W21x62", "W24x55", "W24x76",
         "W27x84", "W30x90")
SUPPORTS = ("W14x90", "W12x65", "W14x61", "W12x50", "W12x40", "W10x49")
ANGLES = ("L4x3_1_2x5_16", "L4x3_1_2x3_8", "L4x4x5_16", "L4x4x3_8", "L5x3_1_2x3_8", "L4x4x1_2")
SEATS = ("L6x4x1_2", "L6x4x3_4", "L7x4x1_2")
TEES = ("WT6x20", "WT6x25", "WT7x26_5", "WT8x25", "WT9x25", "WT5x22_5")
HANGER_TEES = ("WT6x17_5", "WT9x25", "WT8x25", "WT7x26_5", "WT6x25")
HANGER_SUPPORTS = ("W18x50", "W21x57", "W24x76", "W21x62", "W18x35", "W16x31")
PLATES = ("0.25", "0.3125", "0.375", "0.4375", "0.5")
WELDS = ("0.1875", "0.25", "0.3125", "0.375")
HOLES = ("std", "ovs", "ssl", "lsl", "ssl_parallel", "lsl_parallel")
SIGNATURE = 'signed "gate@petra.dev" source "steel gate generator"'
CYCLIC = 0.25
CYCLE_COUNTS = (10_000, 20_000, 30_000, 100_000, 500_000, 2_000_000, 10_000_000, 100_000_000, 200_000_000)


@dataclass(frozen=True)
class Generated:
    name: str
    kind: str
    target: str               # "pass" | "fail": the load margin's side
    expected: str             # "PASS" | "FAIL": FAIL as well when a geometry check fails
    text: str
    toleranced: bool
    free: bool                # drawn without the detailer's rules
    redraws: int
    utilisation: float        # the deck's governing load-dependent utilisation, as calc.values reads it
    governing: str            # its mode
    geometry: float           # the deck's governing utilisation over checks the load does not change
    cycles: tuple[int, int] | None = None     # the gate case's cycles interval, when it is cyclic


def _inch(x) -> str:
    return f"{Fraction(x).numerator / Fraction(x).denominator:g} inch"


def _quarter(x: Fraction) -> Fraction:
    """Down to a quarter inch."""
    return Fraction(math.floor(x * 4), 4)


def _quarter_up(x: Fraction) -> Fraction:
    """Up to a quarter inch."""
    return Fraction(math.ceil(x * 4), 4)


def hole_max(d: Fraction) -> Fraction:
    """The largest hole a rule-following sample draws for bolt diameter d, along or across
    the force: a short slot's length, d + 1/4 in up to 7/8 in bolts and d + 5/16 in for 1 in
    (Table J3.3)."""
    return d + Fraction(5, 16)


def min_fillet(t: Fraction) -> Fraction:
    """Table J2.4: the least fillet for the thinner part joined."""
    for limit, size in ((Fraction(1, 4), Fraction(1, 8)), (Fraction(1, 2), Fraction(3, 16)), (Fraction(3, 4), Fraction(1, 4))):
        if t <= limit:
            return size
    return Fraction(5, 16)


class _Sampler:
    def __init__(self, rng: random.Random, registry: Registry):
        self.rng, self.registry = rng, registry
        self.free = rng.random() < FREE
        self.cyclic = False                                    # bolts pretensioned unless free
        self.lines: list[str] = []
        self.lengths: list[tuple[int, str, Fraction]] = []    # (line index, key, value) a tolerance may widen
        self.secondary: list[tuple[str, Fraction]] = []        # (load field, ratio to the primary)

    def pick(self, options):
        return self.rng.choice(tuple(options))

    def chance(self, p: float) -> bool:
        return self.rng.random() < p

    def line(self, text: str) -> None:
        self.lines.append(f"  {text}")

    def length(self, key: str, value, widen: bool = False) -> None:
        if widen:
            self.lengths.append((len(self.lines), key, Fraction(value)))
        self.line(f"{key} {_inch(value)}")

    def dim(self, shape: str, prop: str) -> Fraction:
        parent = tee_parent(shape) if shape.startswith("WT") else shape
        return self.registry.constants[f"aisc_shapes_v16.{parent}.{prop}"].value.lo / INCH

    def has(self, shape: str) -> bool:
        parent = tee_parent(shape) if shape.startswith("WT") else shape
        prop = "t" if shape.startswith("L") else "d"
        return f"aisc_shapes_v16.{parent}.{prop}" in self.registry.constants

    def bolts(self, joint: bool = True, tension: bool = False, d: str | None = None) -> tuple[Fraction, str]:
        d = d or self.pick(("0.75", "0.875", "1"))
        group = self.pick(("bolt_group.120", "bolt_group.150"))
        threads = self.pick(("included", "excluded"))
        kind = "snug"
        if joint and self.chance(0.2):
            kind = "slip_critical"
        elif joint and (self.chance(0.3) or tension and group == "bolt_group.150" and not self.free):
            kind = "pretensioned"
        if kind == "snug" and self.cyclic and not self.free:
            kind = "pretensioned"       # a joint under a cyclic load is (J3.2, RCSC 4.2)
        extra = {"snug": "", "pretensioned": " joint pretensioned",
                 "slip_critical": f" joint slip_critical surface {self.pick(('class_a', 'class_b'))}"}[kind]
        if kind == "slip_critical" and self.chance(0.2):
            extra += " fillers one"
        self.line(f"bolts {group} diameter {d} inch threads {threads}{extra}")
        return Fraction(d), kind

    def holes(self, plies: tuple[str, ...], joint: str) -> None:
        """Mostly standard holes; one ply slotted across the force now and then, and an
        oversized or parallel-slotted ply in a slip-critical joint."""
        if not plies:
            return
        if self.free:
            if self.chance(0.4):
                self.line(f"holes {self.pick(plies)} {self.pick(HOLES)}")
            return
        if joint == "slip_critical" and self.chance(0.4):
            self.line(f"holes {self.pick(plies)} {self.pick(('ovs', 'ssl_parallel'))}")
        elif self.chance(0.15):
            self.line(f"holes {self.pick(plies)} ssl")

    def options(self, *, deformation: bool = True, weathering: bool = True, setback: bool = False,
                coped: bool = False) -> None:
        if deformation and self.chance(0.2):
            self.line(f"deformation {self.pick(('considered', 'not_considered'))}")
        if weathering and self.chance(0.1):
            self.line("weathering yes")
        if setback:
            if self.chance(0.3):
                self.length("setback", self.pick(("0.5", "0.75")))
            elif coped:
                self.length("setback", "0.5")    # a coped beam states its setback (lower.SET_BACK)

    def rows(self, room: Fraction) -> int:
        """Rows at a 3 in pitch whose span, 3 (n - 1), is at most `room`; two at least."""
        most = max(2, min(8, int(room // 3) + 1))
        n = self.rng.randint(2, most)
        self.line(f"rows {n}")
        return n

    def beam_rows(self, beam: str, top: Fraction, lev: Fraction) -> int:
        """Rows whose part ends above the beam's bottom fillet: top + 3 (n - 1) + Lev <= d -
        kdes, Lev at its toleranced most."""
        return self.rows(self.dim(beam, "d") - self.dim(beam, "kdes") - top - lev - TOLERANCE)

    def beam(self, options=BEAMS) -> str:
        shape = self.pick(s for s in options if self.has(s))
        self.line(f"beam {shape} grade steel.A992")
        return shape

    def support(self, faces=("flange", "web"), options=SUPPORTS, beam: str | None = None) -> tuple[str, str]:
        """A support and its face; a beam framed to a column's web passes between its
        flanges (d - 2 tf at least the beam's bf)."""
        face = self.pick(faces)
        shape = self.pick(s for s in options if self.has(s) and (
            self.free or beam is None or face == "flange" or self.dim(s, "d") - 2 * self.dim(s, "tf") >= self.dim(beam, "bf")))
        self.line(f"support {shape} {face} grade steel.A992")
        return shape, face

    def width(self, support: tuple[str, str]) -> Fraction:
        """The room across the face: a flange's width, or a web's flat between its fillets."""
        shape, face = support
        return self.dim(shape, "bf") if face == "flange" else self.dim(shape, "d") - 2 * self.dim(shape, "kdes")

    def face_t(self, support: tuple[str, str]) -> Fraction:
        return self.dim(support[0], "tf" if support[1] == "flange" else "tw")

    def cope(self, depth: Fraction, top: Fraction, rows: int) -> bool:
        if not self.chance(0.25):
            return False
        room = top - (0 if self.free else EDGE)
        depths = [x for x in (Fraction(1), Fraction(3, 2), Fraction(2)) if x <= room] or [Fraction(1)]
        dc = self.pick(depths)
        length = self.pick((Fraction(3), Fraction(4), Fraction(6)))
        below = depth - top - 3 * (rows - 1) - (0 if self.free else EDGE)
        if self.chance(0.3) and below >= 1:
            bottom = self.pick([x for x in (Fraction(1), Fraction(3, 2), Fraction(2)) if x <= below])
            self.line(f"cope both depth {_inch(dc)} length {_inch(length)} bottom_depth {_inch(bottom)}")
        else:
            self.line(f"cope top depth {_inch(dc)} length {_inch(length)}")
        return True

    def weld(self, key: str = "weld", sides: int | None = None, least: Fraction = Fraction(0),
             most: Fraction | None = None) -> Fraction:
        sizes = [w for w in WELDS if self.free or least <= Fraction(w) <= (most if most is not None else Fraction(w))] \
            or [w for w in WELDS if Fraction(w) >= least] or [WELDS[-1]]
        size = self.pick(sizes)
        self.line(f"{key} electrode.E70 size {size} inch" + (f" sides {sides}" if sides is not None else ""))
        return Fraction(size)


def _top(s: _Sampler, beam: str, lev: Fraction) -> Fraction:
    """The top row, deep enough that the part, Lev above it at its toleranced most, clears
    the beam's flange and fillet (kdes)."""
    top = Fraction(s.pick(("2.5", "3", "3.5")))
    if not s.free:
        top = max(top, _quarter_up(s.dim(beam, "kdes") + lev + TOLERANCE))
    s.length("top", top)
    return top


def _shear_tab(s: _Sampler) -> None:
    beam = s.beam()
    extended = s.chance(0.25)
    support = s.support(("web",) if extended else ("flange", "web"), beam=beam)
    grade = s.pick(("A36", "A572_50"))
    d = s.pick(("0.75", "0.875"))
    tp = Fraction(s.pick(t for t in PLATES if s.free or extended or Fraction(t) <= Fraction(d) / 2 + TOLERANCE))
    s.line(f"plate steel.{grade} thickness {_inch(tp)}")
    _, joint = s.bolts(d=d)
    s.holes(("plate", "beam"), joint)
    lev = Fraction(s.pick(("1.25", "1.5")))
    top = _top(s, beam, lev)
    rows = s.beam_rows(beam, top, lev)
    columns = 2 if extended and s.chance(0.4) else 1
    if columns == 2:
        s.line("columns 2")
        s.length("gauge", 3)
    s.length("pitch", 3)
    s.length("edge_vertical", lev, widen=True)
    two_d = 2 * Fraction(d)         # a conventional plate's Leh >= 2d (Manual Part 10)
    s.length("plate_edge", s.pick(x for x in ("1.5", "2") if s.free or extended or Fraction(x) >= two_d), widen=True)
    s.length("bolt_line", s.pick(("6", "7.5", "9")) if extended else s.pick(("3", "3.5")))
    s.length("beam_edge", s.pick(x for x in ("1.5", "1.75", "2") if s.free or extended or Fraction(x) >= two_d),
             widen=True)
    s.weld(sides=2, least=max(Fraction(5, 8) * tp, min_fillet(min(tp, s.face_t(support)))))
    if extended:
        s.line("form extended")
    coped = s.cope(s.dim(beam, "d"), top, rows)
    s.options(setback=True, coped=coped)


def _angle_fits(s: _Sampler, shape: str, outstanding: str, double: bool, bolted: bool, beam: str,
                support: tuple[str, str]) -> bool:
    """The angles' support side fits the face, for any toe, hole and weld the sample can
    draw: welds at the toes within it; bolt lines (gauge from the heel at the 1-1/4 in toe)
    within it; on a web, the outstanding legs on its flat too."""
    long, short = s.dim(shape, "d"), s.dim(shape, "b")
    out = long if outstanding == "long" else short
    tw, room = s.dim(beam, "tw"), s.width(support)
    legs = 2 * out + tw if double else out + tw
    if not bolted:
        least = min_fillet(min(s.dim(shape, "t"), s.face_t(support)))
        return legs + (2 if double else 1) * least <= room
    heel = max(Fraction(3, 2), out - EDGE)
    bolt_lines = 2 * heel + tw + hole_max(Fraction(1)) if double else tw + heel + hole_max(Fraction(1)) / 2
    return bolt_lines <= room and (support[1] == "flange" or legs <= room)


def _angles(s: _Sampler, double: bool) -> None:
    beam = s.beam()
    support = s.support(("flange", "web"), beam=beam)
    bolted = s.chance(0.7)
    choices = [(a, o) for a in ANGLES if s.has(a) for o in ("long", "short")]
    fitting = [c for c in choices if s.free or _angle_fits(s, *c, double, bolted, beam, support)]
    shape, outstanding = s.pick(fitting or choices)
    long, short, t = s.dim(shape, "d"), s.dim(shape, "b"), s.dim(shape, "t")
    out_leg, beam_leg = (long, short) if outstanding == "long" else (short, long)
    s.line(f"{'angles' if double else 'angle'} {shape} grade steel.A36 outstanding {outstanding}")
    d, joint = s.bolts()
    s.holes(("angles" if double else "angle", "beam", "support"), joint)
    lev = Fraction(s.pick(("1.25", "1.5")))
    top = _top(s, beam, lev)
    rows = s.beam_rows(beam, top, lev)
    s.length("pitch", 3)
    s.length("edge_vertical", lev, widen=True)
    toe = Fraction(s.pick(("1.25", "1.5")))
    gauge = Fraction(s.pick(("2", "2.25", "2.5"))) if s.free else max(Fraction(3, 2), beam_leg - toe)
    # the beam end stands clear of the support face: its end distance within the beam gauge
    s.length("beam_edge", s.pick(x for x in ("1.5", "1.75") if s.free or Fraction(x) + TOLERANCE <= gauge), widen=True)
    s.length("beam_gauge", gauge)
    if bolted:
        s.line("support_side bolted")
        heel = max(Fraction(3, 2), out_leg - toe)
        gauge = 2 * heel + s.dim(beam, "tw") if double else heel
        s.length("support_gauge", Fraction(s.pick(("5.5", "2.5"))) if s.free else _quarter(gauge))
    else:
        s.line("support_side welded")
        # the welds at the toes within the face
        legs = 2 * out_leg + s.dim(beam, "tw") if double else out_leg + s.dim(beam, "tw")
        s.weld("support_weld", least=min_fillet(min(t, s.face_t(support))), most=(s.width(support) - legs) / (2 if double else 1))
    coped = s.cope(s.dim(beam, "d"), top, rows)
    s.options(setback=True, coped=coped)


def _shear_tee(s: _Sampler) -> None:
    beam = s.beam()
    support = s.support(("flange", "web"), beam=beam)
    bolted = s.chance(0.7)
    room = s.width(support)
    # the tee's flange on a web's flat, its tip welds within the face
    fitting = [t for t in TEES if s.has(t) and (s.free or (
        s.dim(t, "bf") + 2 * Fraction(WELDS[-1]) <= room if not bolted else support[1] == "flange" or s.dim(t, "bf") <= room))]
    tee = s.pick(fitting or [t for t in TEES if s.has(t)])
    s.line(f"tee {tee} grade steel.A992")
    d, joint = s.bolts()
    s.holes(("stem", "flange", "beam", "support"), joint)
    lev = Fraction(s.pick(("1.25", "1.5")))
    top = _top(s, beam, lev)
    rows = s.beam_rows(beam, top, lev)
    s.length("pitch", 3)
    s.length("edge_vertical", lev, widen=True)
    depth, tw = s.dim(tee, "d") / 2, s.dim(tee, "tw")
    toe = min(12 * tw, Fraction(6)) - Fraction(1, 4)
    line = Fraction(s.pick(("3", "3.5"))) if s.free else max(Fraction(3), _quarter(depth - toe) + Fraction(1, 4))
    s.length("bolt_line", line)
    s.length("beam_edge", s.pick(("1.5", "1.75")), widen=True)
    if bolted:
        s.line("support_side bolted")
        room = s.dim(tee, "bf") - 2 * EDGE
        gauges = [g for g in (Fraction(7, 2), Fraction(4), Fraction(11, 2)) if s.free or g <= room] or [Fraction(7, 2)]
        s.length("support_gauge", s.pick(gauges))
    else:
        s.line("support_side welded")
        s.weld("support_weld", least=min_fillet(min(s.dim(tee, "tf"), s.face_t(support))))
    coped = s.cope(s.dim(beam, "d"), top, rows)
    s.options(setback=True, coped=coped)


def _end_plate(s: _Sampler) -> None:
    beam = s.beam()
    support = s.support(("flange", "web"), beam=beam)
    tp = Fraction(s.pick(("0.25", "0.3125", "0.375")))
    s.line(f"plate steel.A36 thickness {_inch(tp)}")
    gauge = Fraction(s.pick(("3.5", "5.5")))
    # on a web, the plate on its flat
    widths = [w for w in (Fraction(7), Fraction(8), Fraction(9)) if s.free or (
        w - gauge >= 2 * EDGE and (support[1] == "flange" or w <= s.width(support)))]
    s.length("plate_width", s.pick(widths or [Fraction(7)]))
    d, joint = s.bolts()
    s.holes(("plate", "support"), joint)
    lev = Fraction(s.pick(("1.25", "1.5")))
    # the welds, 3 (n - 1) + 2 Lev - 2 w long, on the flat web
    s.rows(s.dim(beam, "d") - 2 * s.dim(beam, "kdes") - 2 * (lev + TOLERANCE))
    s.length("pitch", 3)
    s.length("edge_vertical", lev, widen=True)
    s.length("support_gauge", gauge)
    s.weld(sides=2, least=min_fillet(min(tp, s.dim(beam, "tw"))))
    s.options(setback=True)


def _seated(s: _Sampler) -> None:
    beam = s.beam(("W12x26", "W14x22", "W16x26", "W16x31", "W18x35"))
    support = s.support(("flange", "web"), beam=beam)
    seat = s.pick(a for a in SEATS if s.has(a))
    s.line(f"angle {seat} grade steel.A36 outstanding short")
    bolted = s.chance(0.6)
    room = s.width(support)
    # the seat on a web's flat, its end welds within the face
    lengths = [x for x in (Fraction(6), Fraction(8)) if s.free or (
        x + 2 * Fraction(WELDS[-1]) <= room if not bolted else support[1] == "flange" or x <= room)]
    length = s.pick(lengths or [Fraction(6)])
    s.length("seat_length", length)
    s.length("setback", s.pick(("0.5", "0.75")))
    if bolted:
        s.line("support_side bolted")
        d, joint = s.bolts(joint=False)
        s.holes(("angle", "support"), joint)
        s.line("rows 2")
        s.length("pitch", 3)
        # the top hole below the outstanding leg: Lev - 1/16 - dh/2 >= t
        t = s.dim(seat, "t")
        levs = [x for x in ("1.25", "1.5", "1.75") if s.free or Fraction(x) - TOLERANCE - hole_max(d) / 2 >= t]
        s.length("edge_vertical", s.pick(levs or ["1.75"]), widen=True)
        gauges = [g for g in (Fraction(7, 2), Fraction(11, 2)) if s.free or length - g >= 2 * EDGE]
        s.length("support_gauge", s.pick(gauges))
    else:
        s.line("support_side welded")
        s.weld("support_weld", least=min_fillet(min(s.dim(seat, "t"), s.face_t(support))))
    s.line(f"top_angle {s.pick(('L4x4x1_4', 'L4x4x5_16'))} grade steel.A36 outstanding long")
    s.options(weathering=True)


def _stiffened_seat(s: _Sampler) -> None:
    beam = s.beam(("W18x35", "W18x50", "W21x44", "W21x62", "W24x55"))
    support = s.support(("flange",))
    tp = Fraction(s.pick(("0.375", "0.5")))
    # Either grade for either plate: the seat plate bears on the stiffener's edge at its own Fy (J7).
    s.line(f"plate {s.pick(('steel.A36', 'steel.A572_50'))} thickness {_inch(tp)}")
    # limit: 0.56 sqrt(29000 / Fy), a little under
    grade, fy, limit = s.pick((("steel.A36", 36, Fraction(1589, 100)), ("steel.A572_50", 50, Fraction(1348, 100))))
    pairs = [(w, t) for w in (Fraction(4), Fraction(5), Fraction(6)) for t in (Fraction(3, 8), Fraction(1, 2), Fraction(5, 8))
             if s.free or w / t <= limit and t >= s.dim(beam, "tw") * 50 / fy]     # ts >= tw Fyb / Fys
    width, ts = s.pick(pairs)
    s.line(f"stiffener {grade} thickness {_inch(ts)}")
    s.length("stiffener_width", width)
    s.length("stiffener_length", s.pick(("10", "12", "14")))
    s.length("setback", s.pick(("0.5", "0.75")))
    s.weld(sides=2, least=min_fillet(min(ts, s.face_t(support))))
    s.line("top_angle L4x4x1_4 grade steel.A36 outstanding long")


def _flange_force(s: _Sampler) -> None:
    member = s.pick(m for m in SUPPORTS if s.has(m))
    s.line(f"member {member} grade steel.A992")
    s.length("bearing_length", s.pick(("0.5", "4", "6", "10")))
    force = s.pick(("compressive", "tensile"))
    if s.chance(0.3):
        s.line("location end")
        s.length("distance", s.pick(("2", "4", "8", "16")))
        s.line("end_twist restrained")      # a free end needs J10.7's stiffeners, which leave it UNKNOWN
    else:
        s.line("location interior")
    s.line(f"force_kind {force}")
    if force == "compressive" and s.chance(0.3):
        s.line("pair double")
    else:
        if force == "compressive":
            s.line(f"flange_restrained {s.pick(('yes', 'no'))}")
            s.length("unbraced_length", s.pick(("60", "120", "144")))
        if s.chance(0.3):
            s.line(f"moment_at_force {s.pick(('below_yield', 'at_yield'))}")
        elif force == "compressive":
            s.line("moment_at_force below_yield")     # J10.4 reads it (lower._check_kind)
    # The panel zone is demanded at every flange force and reads both (build.NEEDS).
    s.secondary.append(("panel_shear", Fraction(s.pick(("0", "0.5", "1", "2")))))
    s.secondary.append(("axial", Fraction(s.pick(("0", "0.5", "2")))))


def _bolt_bracket(s: _Sampler) -> None:
    tp = Fraction(s.pick(("0.5", "0.625", "0.75")))
    s.line(f"plate steel.A36 thickness {_inch(tp)}")
    s.support(("flange",))
    d, joint = s.bolts()
    s.holes(("plate", "support"), joint)
    rows = s.rng.randint(2, 6)
    s.line(f"rows {rows}")
    s.line(f"columns {s.pick((1, 2))}")
    s.length("pitch", 3)
    s.length("gauge", s.pick(("3", "4", "5.5")))
    s.length("eccentricity", s.pick(("6", "8", "12")))
    s.length("edge_vertical", s.pick(("1.5", "2")), widen=True)
    s.length("plate_edge", s.pick(("1.5", "2")), widen=True)
    if s.chance(0.4):
        s.length("free_edge", s.pick(("6", "8", "10")))
    s.options(weathering=True)


def _weld_bracket(s: _Sampler) -> None:
    tp = Fraction(s.pick(("0.5", "0.625", "0.75")))
    s.line(f"plate steel.A36 thickness {_inch(tp)}")
    support = s.support(("flange",))
    lapped = s.chance(0.5)
    least = min_fillet(min(tp, s.face_t(support)))
    sizes = [w for w in WELDS if s.free or least <= Fraction(w) <= tp - TOLERANCE]
    s.line(f"weld electrode.E70 size {s.pick(sizes or WELDS)} inch sides {1 if lapped else 2}")
    s.length("weld_length", s.pick(("8", "10", "12", "14")))
    if lapped:
        s.length("weld_return", s.pick(("2", "3")))
    s.length("eccentricity", s.pick(("5", "6", "8", "10")))
    if s.chance(0.4):
        s.length("free_edge", s.pick(("6", "8")))


def _hanger(s: _Sampler) -> None:
    tee = s.pick(t for t in HANGER_TEES if s.has(t))
    s.line(f"tee {tee} grade steel.A992")
    support, _ = s.support(("flange",), HANGER_SUPPORTS)
    d, joint = s.bolts(tension=True)
    s.holes(("flange", "support"), joint)
    s.line("rows 2")
    s.length("pitch", s.pick(("3", "4", "5")))
    room = min(s.dim(tee, "bf"), s.dim(support, "bf")) - 2 * EDGE
    gauges = [g for g in (Fraction(7, 2), Fraction(4), Fraction(11, 2)) if s.free or g <= room] or [Fraction(7, 2)]
    s.length("tee_gauge", s.pick(gauges))
    s.length("edge_vertical", s.pick(("1.5", "2")), widen=True)
    s.options(deformation=False)
    if s.chance(0.3):
        s.secondary.append(("shear", Fraction(s.pick(("0.1", "0.3", "0.5")))))


SAMPLERS: dict[str, Callable[[_Sampler], None]] = {
    "shear_tab": _shear_tab,
    "double_angle": lambda s: _angles(s, True),
    "single_angle": lambda s: _angles(s, False),
    "shear_tee": _shear_tee,
    "shear_end_plate": _end_plate,
    "seated": _seated,
    "stiffened_seat": _stiffened_seat,
    "flange_force": _flange_force,
    "bolt_bracket": _bolt_bracket,
    "weld_bracket": _weld_bracket,
    "hanger": _hanger,
}


def _decimal(x: Fraction) -> str:
    return f"{x.numerator // x.denominator}.{(x.numerator % x.denominator) * 1000 // x.denominator:03d}"


def source(name: str, kind: str, basis: str, lines: list[str], load: Fraction,
           secondary: tuple[tuple[str, Fraction], ...] = (), cycles: tuple[int, int] | None = None) -> str:
    """The design's text with the primary load [0, load], each secondary [0, ratio load],
    and the cycles interval when the case is cyclic."""
    loads = [(KIND_SPECS[kind].loads[0], load), *((f, _load(float(r * load))) for f, r in secondary)]
    body, on = "\n".join(lines), "".join(f"  on c1 {f} in [0 kip, {_decimal(x)} kip]\n" for f, x in loads)
    if cycles is not None:
        on += f"  on c1 {CYCLES} in [{cycles[0]}, {cycles[1]}]\n"
    return (f'petra 0\n\ndesign "{name}" {{\n  owner "gate@petra.dev"\n}}\n\n{kind} c1 {{\n  basis {basis}\n{body}\n}}\n\n'
            f"load gate {{\n{on}  {SIGNATURE}\n}}\n")


def checks(text: str, registry: Registry) -> dict[tuple[str, int], calc.Value]:
    """Every check of c1 the deck generates, by (mode, index), with its numbers."""
    design = parse_design(text, "gate.petra", registry)
    conn = calc.connection(design, "c1", registry)
    out = {}
    for mode in required(conn, design):
        if mode in GENERATORS:
            for i, v in enumerate(calc.values(conn, design, registry, mode, "gate")):
                out[(mode, i)] = v
    return out


def _worst(values: dict, keys) -> tuple[float, str]:
    found = [(values[k].utilisation, k[0]) for k in keys if not values[k].excused]
    return max(found, default=(0.0, ""))


def _load(x: float) -> Fraction:
    return max(Fraction(1, 1000), Fraction(round(x * 1000), 1000))


def scale(build: Callable[[Fraction], str], goal: Fraction, registry: Registry):
    """The load at which the deck's governing load-dependent check reaches `goal`, found
    by secant steps on log u against log P: u is not linear in P (a seat's moment arm
    grows with its bearing length, and is nil until the bearing passes the critical
    section). A check is load-dependent when its demand differs between any two loads
    tried, the final one included. Returns (load, strength u, its mode, geometry u) or None."""
    ref = Fraction(10)
    seen: dict[Fraction, dict] = {}

    def loaded() -> set:
        first = next(iter(seen.values()))
        return {k for k in first if len({values[k].demand for values in seen.values()}) > 1}

    def at(p: Fraction) -> tuple[float, str]:
        if p not in seen:
            seen[p] = checks(build(p), registry)
        return _worst(seen[p], loaded())

    at(ref)
    p0, p1 = ref, 2 * ref
    u0, _ = at(p0)
    u1, mode = at(p1)
    for _ in range(12):
        if u1 <= 0:
            return None
        if abs(u1 / float(goal) - 1) < 0.003:
            break
        slope = min(3.0, max(0.5, math.log(u1 / u0) / math.log(float(p1 / p0)))) if u0 > 0 and u1 != u0 else 1.0
        p = _load(float(p1) * (float(goal) / u1) ** (1 / slope))
        if p == p1:
            break
        p0, u0 = p1, u1
        p1 = p
        u1, mode = at(p1)
    u1, mode = at(p1)
    fixed = [k for k in seen[p1] if k not in loaded()]
    return p1, u1, mode, _worst(seen[p1], fixed)[0]


def _widen(lines: list[str], s: _Sampler) -> bool:
    if not s.lengths or s.rng.random() >= 0.2:
        return False
    index, key, value = s.pick(s.lengths)
    lo, hi = value - TOLERANCE, value + TOLERANCE
    lines[index] = f"  {key} in [{_inch(lo)}, {_inch(hi)}] {SIGNATURE}"
    return True


def _encoded(text: str, registry: Registry) -> bool:
    """Every fatigue mode the cyclic design owes has checks (none is fatigue_detail)."""
    design = parse_design(text, "gate.petra", registry)
    return not set(required(calc.connection(design, "c1", registry), design)) & set(UNENCODED)


def generate(n: int, seed: int, registry: Registry, start: int = 0) -> Iterator[Generated]:
    """Designs `start` to `start + n - 1` of the stream for `seed`; each index has its own
    random stream, so a slice is the same whoever draws it."""
    kinds = tuple(SAMPLERS)
    for i in range(start, start + n):
        rng = random.Random(f"{seed}:{i}")
        cyc = random.Random(f"{seed}:{i}:cycles")
        drawn = cyc.choice(CYCLE_COUNTS)
        wanted = (cyc.choice((0, drawn)), drawn) if cyc.random() < CYCLIC else None
        kind = kinds[i % len(kinds)]
        name = f"gate-{seed}-{i:05d}"
        redraws = 0
        while True:
            s = _Sampler(rng, registry)
            s.cyclic = wanted is not None
            SAMPLERS[kind](s)
            lines, secondary = list(s.lines), tuple(s.secondary)
            toleranced = _widen(lines, s)
            basis = rng.choice(("lrfd", "asd"))
            target = "pass" if rng.random() < 0.75 else "fail"
            k = Fraction(rng.randint(100, 400), 100)
            goal = 1 - DELTA * k if target == "pass" else 1 + DELTA * k
            try:
                cycles = wanted if wanted and _encoded(source(name, kind, basis, lines, Fraction(10), secondary, wanted),
                                                       registry) else None
                found = scale(lambda load: source(name, kind, basis, lines, load, secondary, cycles), goal, registry)
            except ComponentError:
                found = None
            ok = (found is not None and (found[1] <= 1 - DELTA if target == "pass" else found[1] >= 1 + DELTA)
                  and (s.free or found[3] <= 1))
            if not ok:
                redraws += 1
                continue
            load, u, mode, geometry = found
            expected = "FAIL" if target == "fail" or geometry > 1 else "PASS"
            yield Generated(name, kind, target, expected, source(name, kind, basis, lines, load, secondary, cycles),
                            toleranced, s.free, redraws, u, mode, geometry, cycles)
            break
