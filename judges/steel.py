"""Steel connection fit: do the parts a design's attribute lines draw fit together?

An outside judge for the steel deck (docs/plan.md §4 and P1). It reads the design IR and
the shapes table and computes the geometry itself, from the meanings in
docs/steel_glossary.md. It imports nothing from petra.models.

Frame, in inches: y runs down from the beam's top; x runs out from the support face along
the beam; widths run across the support face. Every support is read as a column, so a
beam framing to its web enters between its flanges.

Two depths bound a part against a web: between the flanges (d - 2 tf), where solid steel
stops it, and the flat web (d - 2 kdes), past which it rides up the web-to-flange fillets.
A part that clears the flanges but not the fillets gets a fillet condition of its own, so
the counts keep a part off the beam apart from one that needs a clipped corner. A bolt
hole must lie in the flat web, since its head and nut cannot seat on a fillet. A cope
frees a part's edge only where it cuts at least as deep as the steel the edge would meet:
tf for the flange, k for the fillet. AISC 360-22 defines k as the distance from the
flange's outer face to the web toe of the fillet, so a shallower cut leaves fillet below it.

A fillet weld along a part's edge lays its leg on the face beyond that edge, so a weld at
a part's toe, tip or end needs its leg's width of face past the part. The Manual asks more:
the Companion's Examples K.2 and K.3 take a shelf of twice the weld size from AISC Manual
Figure 8-13. The judge takes the leg, the least a weld of the stated size needs.

Each ply's hole has the size Table J3.3 gives its declared type; a ply the `holes` line
does not name has standard holes. A slot named plainly runs across the force, which runs
down the depth axis (along a hanger's rows), so its length lies across the support's face;
one named `_parallel` runs along the force.

A toleranced length is an interval, and a condition is violated when it fails anywhere in
the box, since the design claims every value in it. Where the lines leave a dimension
open (a bracket's bolt group position, a single angle's offset from the column's centre,
the beam end before its bolt line), the judge takes the reading most favourable to the
design, so a flag holds under every reading: the beam end and its cope as far out as the
lines allow, a symmetric group centred on the column, a one-sided group placed anywhere
on the face.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Callable

from petra.ir import Bound, Component, Design, Fixed, ParamRef, Ref

from . import shapes
from .shapes import W

INCH = Fraction(254, 10000)
"""One inch in metres: the IR stores lengths in SI."""

Found = tuple[str, str] | None
"""A fact's verdict: None when it fits, else (condition id, one-line reason)."""


@dataclass(frozen=True)
class Iv:
    """A closed interval of inches."""

    lo: Fraction
    hi: Fraction

    def __add__(self, other: Iv | Fraction | int) -> Iv:
        o = iv(other)
        return Iv(self.lo + o.lo, self.hi + o.hi)

    __radd__ = __add__

    def __sub__(self, other: Iv | Fraction | int) -> Iv:
        o = iv(other)
        return Iv(self.lo - o.hi, self.hi - o.lo)

    def __rsub__(self, other: Fraction | int) -> Iv:
        return iv(other) - self

    def __mul__(self, k: Fraction | int) -> Iv:
        return Iv(self.lo * k, self.hi * k) if k >= 0 else Iv(self.hi * k, self.lo * k)

    __rmul__ = __mul__

    def __truediv__(self, k: Fraction | int) -> Iv:
        return self * (Fraction(1) / Fraction(k))

    def text(self) -> str:
        return f"{_num(self.lo)} in" if self.lo == self.hi else f"[{_num(self.lo)}, {_num(self.hi)}] in"


def iv(x: Iv | Fraction | int) -> Iv:
    return x if isinstance(x, Iv) else Iv(Fraction(x), Fraction(x))


def _num(x: Fraction) -> str:
    return f"{float(x):.3f}".rstrip("0").rstrip(".")


def _in(x: Fraction) -> str:
    return iv(x).text()


class Missing(Exception):
    """A line the judge reads is absent or unreadable: the design is not one the deck's
    grammar accepts, so the judge decides nothing about it."""


# --- Facts: one record per thing that must fit ------------------------------------------------


@dataclass(frozen=True)
class OnBeamWeb:
    """A part against the beam web spans [top, bottom] down from the beam's top. It must lie
    between the flanges, and on the flat web, at each flange where no cope that runs past
    the part (`past_top`, `past_bottom`: its depth) cuts that deep. An end plate's position
    is not drawn (top is None): its welds, `length` long, must fit the web the copes leave."""

    what: str
    beam: W
    top: Iv | None
    bottom: Iv | None
    length: Iv
    past_top: Iv | None
    past_bottom: Iv | None
    cope_top: Iv | None       # an end plate's web starts below a top cope
    cope_bottom: Iv | None

    def check(self) -> Found:
        b = self.beam
        if self.top is None:
            for limit, cid, edge in (("between its flanges", "steel.beam_side.depth", b.tf),
                                     ("on its flat web", "steel.beam_side.fillet", b.kdes)):
                left = iv(b.d) - _below(self.cope_top, edge) - _below(self.cope_bottom, edge)
                if self.length.hi > left.lo:
                    return cid, f"{self.what} {self.length.text()} long; the {b.label} leaves {left.text()} {limit}"
            return None
        for cid, depth, where in (("steel.beam_side.depth", b.tf, "inside its flange"),
                                  ("steel.beam_side.fillet", b.kdes, "on its fillet, off the flat web")):
            if not _clears(self.past_top, depth) and self.top.lo < depth:
                return cid, (f"{self.what} top edge {self.top.text()} below the {b.label}'s top, {where} ({_in(depth)})"
                             + _shallow(self.past_top))
            if not _clears(self.past_bottom, depth) and self.bottom.hi > b.d - depth:
                return cid, (f"{self.what} bottom edge {self.bottom.text()} below the {b.label}'s top, {where} "
                             f"(from {_in(b.d - depth)})" + _shallow(self.past_bottom))
        return None


def _below(cut: Iv | None, edge: Fraction) -> Iv:
    """How far the steel the web loses at a flange reaches: the flange and its fillet to
    `edge`, or a cope's cut where that lies deeper."""
    return iv(edge) if cut is None else Iv(max(cut.lo, edge), max(cut.hi, edge))


def _clears(cut: Iv | None, depth: Fraction) -> bool:
    """A cope `cut` deep removes the steel to `depth` everywhere in the box."""
    return cut is not None and cut.lo >= depth


def _shallow(cut: Iv | None) -> str:
    return "" if cut is None else f", and the cope above it cuts only {cut.text()} deep"


@dataclass(frozen=True)
class BoltsInWeb:
    """The beam-side bolt holes span [top, bottom] and must lie in the flat web the copes
    leave."""

    beam: str
    top: Iv
    bottom: Iv
    band_top: Iv
    band_bottom: Iv

    def check(self) -> Found:
        cid = "steel.beam_side.bolts_in_web"
        if self.top.lo < self.band_top.hi:
            return cid, (f"top bolt hole reaches {self.top.text()} below the {self.beam}'s top, above its flat web, "
                         f"which starts at {self.band_top.text()}")
        if self.bottom.hi > self.band_bottom.lo:
            return cid, (f"bottom bolt hole reaches {self.bottom.text()} below the {self.beam}'s top, past its flat web, "
                         f"which ends at {self.band_bottom.text()}")
        return None


@dataclass(frozen=True)
class SeatBearing:
    """The beam end, `setback` off the support face, must land on a seat projecting
    `projection` from it."""

    what: str
    setback: Iv
    projection: Iv

    def check(self) -> Found:
        if self.setback.hi >= self.projection.lo:
            return "steel.beam_side.seat_bearing", (f"beam end {self.setback.text()} off the support face, past the "
                                                    f"{self.what}, which projects {self.projection.text()}")
        return None


@dataclass(frozen=True)
class OnFace:
    """Something on the support face, `span` across. A bolt span runs to its holes' far
    edges and must lie on the face (on a web, its flat part); a pair straddling a flange's
    web leaves `gap` between their holes, which must clear the web. A weld must lie on the
    face; a part may overhang a flange, but on a web it sits between the flanges and,
    clear of the fillets, on the flat web."""

    what: str
    role: str            # "bolt" | "weld" | "part"
    span: Iv
    face: str            # "flange" | "web"
    support: W
    gap: Iv | None = None

    def check(self) -> Found:
        s = self.support
        if self.face == "flange":
            cid = "steel.support_side.flange_width"
            if self.gap is not None and self.gap.lo < s.tw:
                return cid, f"{self.what}'s holes straddle the {s.label}'s {_in(s.tw)} web with {self.gap.text()} between them"
            if self.role != "part" and self.span.hi > s.bf:
                return cid, f"{self.what}: {self.span.text()} across, wider than the {s.label}'s {_in(s.bf)} flange"
            return None
        between, flat = s.d - 2 * s.tf, s.d - 2 * s.kdes
        if self.role == "bolt" and self.span.hi > flat:
            return "steel.support_side.web_width", f"{self.what}: {self.span.text()} across, wider than the {s.label}'s {_in(flat)} flat web"
        if self.role != "bolt" and self.span.hi > between:
            return "steel.support_side.web_width", f"{self.what}: {self.span.text()} across, wider than the {_in(between)} between the {s.label}'s flanges"
        if self.role != "bolt" and self.span.hi > flat:
            return "steel.support_side.web_fillet", f"{self.what}: {self.span.text()} across, wider than the {s.label}'s {_in(flat)} flat web"
        return None


@dataclass(frozen=True)
class GroupOnFace:
    """A bracket's bolt columns, `cols` at gauge `g`, whose position across the face the
    lines leave open: some placement must put every column's holes on the face (on a
    flange, each clear of the web behind it), and on a web the plate, `width` across, must
    fit between the flanges and then the fillets."""

    cols: int
    g: Iv
    hole: Iv
    width: Iv
    face: str
    support: W

    def check(self) -> Found:
        s, r = self.support, self.hole.hi / 2
        if self.face == "web":
            group = (self.cols - 1) * self.g + 2 * r
            plate = OnFace("bracket plate", "part", self.width, "web", s).check()
            return OnFace(f"{self.cols} bolt columns", "bolt", group, "web", s).check() or plate
        lo, hi = s.tw / 2 + r, s.bf / 2 - r
        if all(_placed(self.cols, g, lo, hi) for g in (self.g.lo, self.g.hi)):
            return None
        return "steel.support_side.flange_width", (f"no placement puts {self.cols} bolt columns at {self.g.text()} on the "
                                                   f"{s.label}'s {_in(s.bf)} flange with every hole clear of its {_in(s.tw)} web")


def _placed(cols: int, g: Fraction, lo: Fraction, hi: Fraction) -> bool:
    """Columns at x0 + j g, j < cols, all with |x| in [lo, hi]: all on one side, or m on the
    left and the rest on the right with the pair straddling the web at -p and g - p."""
    if hi < lo:
        return False
    if (cols - 1) * g <= hi - lo:
        return True
    for m in range(1, cols):
        p_lo, p_hi = max(lo, (cols - m) * g - hi), min(hi - (m - 1) * g, g - lo)
        if p_lo <= p_hi:
            return True
    return False


@dataclass(frozen=True)
class LegBolts:
    """A seat's support bolts, holes spanning [top, bottom] down from its heel, must lie on
    its vertical leg below the outstanding leg's thickness."""

    seat: str
    top: Iv
    bottom: Iv
    thickness: Iv
    leg: Iv

    def check(self) -> Found:
        cid = "steel.support_side.leg_length"
        if self.top.lo < self.thickness.hi:
            return cid, f"top bolt hole reaches {self.top.text()} below the {self.seat}'s heel, into its {self.thickness.text()} outstanding leg"
        if self.bottom.hi > self.leg.lo:
            return cid, f"bottom bolt hole reaches {self.bottom.text()} below the {self.seat}'s heel, off its {self.leg.text()} vertical leg"
        return None


@dataclass(frozen=True)
class BeamInWeb:
    """A beam framing to a support web, its end `end` out from the web face, must pass
    between the flanges while the end lies inside their tips."""

    beam: W
    support: W
    end: Iv

    def check(self) -> Found:
        b, s = self.beam, self.support
        tips, clear = (s.bf - s.tw) / 2, s.d - 2 * s.tf
        if self.end.hi < tips and b.bf > clear:
            return "steel.beam_vs_support.web_clearance", (
                f"the {b.label}'s {_in(b.bf)} flange is wider than the {_in(clear)} between the {s.label}'s flanges, "
                f"and its end, {self.end.text()} out, lies inside their tips at {_in(tips)}")
        return None


@dataclass(frozen=True)
class BeamEnd:
    """The beam end, where the bolt line and the beam's end distance put it, must stand
    clear of what sits on the support face."""

    end: Iv
    clear: Iv
    what: str

    def check(self) -> Found:
        if self.end.lo < self.clear.hi:
            return "steel.beam_vs_support.beam_end", (f"beam end {self.end.text()} out from the support face, inside the "
                                                      f"{self.what}, which reaches {self.clear.text()}")
        return None


Fact = OnBeamWeb | BoltsInWeb | SeatBearing | OnFace | GroupOnFace | LegBolts | BeamInWeb | BeamEnd


# --- Reading the attribute lines ---------------------------------------------------------------


class Reading:
    """One steel component's lines, read by the judge's own parser of the grammar."""

    def __init__(self, component: Component, design: Design):
        self.kind, self.name, self.design = component.kind, component.name, design
        self.lines = {a.key: a.args for a in component.attrs}

    def has(self, key: str) -> bool:
        return key in self.lines

    def args(self, key: str) -> tuple:
        if key not in self.lines:
            raise Missing(f"no `{key}` line")
        return self.lines[key]

    def _length(self, arg: object, what: str) -> Iv:
        if isinstance(arg, Fixed):
            value = arg.quantity.value
        elif isinstance(arg, Bound):
            value = arg.range.value
        elif isinstance(arg, ParamRef) and arg.name in self.design.params:
            value = self.design.params[arg.name].range.value
        else:
            raise Missing(f"`{what}` is not a length")
        return Iv(value.lo / INCH, value.hi / INCH)

    def length(self, key: str) -> Iv:
        return self._length(self.args(key)[0], key)

    def opt(self, key: str) -> Iv | None:
        return self.length(key) if self.has(key) else None

    def count(self, key: str, absent: int | None = None) -> int:
        if not self.has(key) and absent is not None:
            return absent
        arg = self.args(key)[0]
        if not isinstance(arg, Fixed):
            raise Missing(f"`{key}` is not a count")
        return int(arg.quantity.value.lo)

    def word(self, key: str, i: int = 0) -> str:
        args = self.args(key)
        if len(args) <= i or not isinstance(args[i], Ref):
            raise Missing(f"`{key}` has no word at {i}")
        return ".".join(args[i].parts)

    def keyword(self, key: str, word: str) -> object | None:
        args = self.args(key)
        for a, b in zip(args[1::2], args[2::2]):
            if isinstance(a, Ref) and a.parts == (word,):
                return b
        return None

    def kw_length(self, key: str, word: str) -> Iv:
        value = self.keyword(key, word)
        if value is None:
            raise Missing(f"`{key}` has no {word}")
        return self._length(value, f"{key} {word}")

    def w(self, key: str) -> W:
        shape = shapes.w(self.word(key))
        if shape is None:
            raise Missing(f"{self.word(key)} is not in the shapes table")
        return shape

    def face(self) -> str:
        return self.word("support", 1)

    def angle(self, key: str) -> tuple[shapes.Angle, Fraction, Fraction]:
        """(angle, its leg on the beam or vertical, its outstanding leg)."""
        a = shapes.angle(self.word(key))
        out = self.keyword(key, "outstanding")
        if a is None or not isinstance(out, Ref):
            raise Missing(f"`{key}` is not an angle with an outstanding leg")
        return (a, a.short, a.long) if out.parts == ("long",) else (a, a.long, a.short)

    def tee(self) -> shapes.Tee:
        t = shapes.tee(self.word("tee"))
        if t is None:
            raise Missing(f"{self.word('tee')} is not cut from a W in the shapes table")
        return t

    def hole(self, ply: str, across: bool) -> Iv:
        """The hole in `ply`, its size across the support's face or down the depth axis:
        Table J3.3 for the type the `holes` line declares for the ply, standard where it
        names none. A plain slot's length lies across the face; a `_parallel` slot's runs
        down the depth axis."""
        kind = self.hole_types().get(ply, "std")
        parallel = kind.endswith("_parallel")
        d = self.kw_length("bolts", "diameter")
        lo, hi = (_j33(x, kind.removesuffix("_parallel")) for x in (d.lo, d.hi))
        i = 1 if across != parallel else 0
        return Iv(lo[i], hi[i])

    def hole_types(self) -> dict[str, str]:
        """Each ply the `holes` line names -> its hole type."""
        if not self.has("holes"):
            return {}
        args = self.args("holes")
        words = [".".join(a.parts) for a in args if isinstance(a, Ref)]
        if len(words) != len(args) or len(words) % 2:
            raise Missing("`holes` is not a list of plies and hole types")
        return dict(zip(words[0::2], words[1::2]))

    def weld(self, key: str) -> tuple[Iv, int]:
        sides = self.keyword(key, "sides")
        return self.kw_length(key, "size"), int(sides.quantity.value.lo) if isinstance(sides, Fixed) else 1

    def cope(self) -> tuple[str, Iv, Iv, Iv] | None:
        """(flanges, top depth, length, bottom depth) or None."""
        if not self.has("cope"):
            return None
        depth = self.kw_length("cope", "depth")
        bottom = self.kw_length("cope", "bottom_depth") if self.keyword("cope", "bottom_depth") is not None else depth
        return self.word("cope"), depth, self.kw_length("cope", "length"), bottom


# --- The kinds: what each one's lines draw ------------------------------------------------------


def _beam_web(r: Reading, beam: W, what: str, reach: Iv, start: Iv) -> list[Fact]:
    """A part bolted to the beam web from `top`, and its bolts. A coped flange frees the
    part's edge on that side when the cope, starting `start` out, runs past the part's
    `reach` and cuts deep enough; the bolts need flat web below the cope either way."""
    n, s, lev, top = r.count("rows"), r.length("pitch"), r.length("edge_vertical"), r.length("top")
    hole = r.hole("beam", across=False)
    cope = r.cope()
    top_cut = cope[1] if cope else None
    bottom_cut = cope[3] if cope and cope[0] == "both" else None
    covered = cope is not None and start.hi + cope[2].hi >= reach.lo
    last = top + s * (n - 1)
    return [
        OnBeamWeb(what, beam, top - lev, last + lev, s * (n - 1) + 2 * lev, top_cut if covered else None,
                  bottom_cut if covered else None, None, None),
        BoltsInWeb(beam.label, top - hole / 2, last + hole / 2, _below(top_cut, beam.kdes),
                   iv(beam.d) - _below(bottom_cut, beam.kdes)),
    ]


J3_3: dict[Fraction, tuple[Fraction, Fraction, Fraction, Fraction]] = {
    Fraction(1, 2): (Fraction(9, 16), Fraction(5, 8), Fraction(11, 16), Fraction(5, 4)),
    Fraction(5, 8): (Fraction(11, 16), Fraction(13, 16), Fraction(7, 8), Fraction(25, 16)),
    Fraction(3, 4): (Fraction(13, 16), Fraction(15, 16), Fraction(1), Fraction(15, 8)),
    Fraction(7, 8): (Fraction(15, 16), Fraction(17, 16), Fraction(9, 8), Fraction(35, 16)),
    Fraction(1): (Fraction(9, 8), Fraction(5, 4), Fraction(21, 16), Fraction(5, 2)),
}
"""AISC 360-22 Table J3.3, in inches, by bolt diameter: the standard hole's diameter (each
slot's width), the oversized hole's diameter, the short slot's length, the long slot's."""


def _j33(d: Fraction, kind: str) -> tuple[Fraction, Fraction]:
    """(width, length) of a `kind` hole for a bolt `d` across; a round hole's are its
    diameter twice. Table J3.3's last row covers bolts from 1-1/8 in: d + 1/8, d + 5/16,
    (d + 1/8) by (d + 3/8), (d + 1/8) by 2.5 d. Below 1 in a standard hole is d + 1/16."""
    row = J3_3.get(d)
    if row is None and d >= Fraction(9, 8):
        row = (d + Fraction(1, 8), d + Fraction(5, 16), d + Fraction(3, 8), Fraction(5, 2) * d)
    std = row[0] if row is not None else d + (Fraction(1, 16) if d < 1 else Fraction(1, 8))
    if kind == "std":
        return std, std
    if row is None:
        raise Missing(f"Table J3.3 has no {kind} hole for a {_num(d)} in bolt")
    sizes = {"ovs": (row[1], row[1]), "ssl": (std, row[2]), "lsl": (std, row[3])}
    if kind not in sizes:
        raise Missing(f"`holes` names {kind}, which is not a hole type")
    return sizes[kind]


def _beam_to_web(beam: W, support: W, face: str, end: Iv) -> list[Fact]:
    return [BeamInWeb(beam, support, end)] if face == "web" else []


def _pair(what: str, gauge: Iv, hole: Iv, face: str, support: W) -> OnFace:
    """Two bolt lines `gauge` apart, centred on the column."""
    return OnFace(what, "bolt", gauge + hole, face, support, gauge - hole)


def _start(r: Reading, end: Iv) -> Iv:
    """Where the beam end, and so a cope, starts: the lines' setback, or the bolt line less
    the beam's end distance, whichever lies farther out."""
    setback = r.opt("setback")
    return end if setback is None else Iv(max(setback.lo, end.lo), max(setback.hi, end.hi))


def shear_tab(r: Reading) -> list[Fact]:
    beam, support, face = r.w("beam"), r.w("support"), r.face()
    a, edge, leh = r.length("bolt_line"), r.length("beam_edge"), r.length("plate_edge")
    cols = r.count("columns", absent=1)
    span = r.length("gauge") * (cols - 1) if cols > 1 else iv(0)
    tp = r.kw_length("plate", "thickness")
    w, sides = r.weld("weld")
    end = a - edge
    return [*_beam_web(r, beam, "plate", a + span + leh, _start(r, end)),
            BeamEnd(end, iv(0), "support face"),
            OnFace("plate and its welds", "weld", tp + w * sides, face, support),
            *_beam_to_web(beam, support, face, end)]


def angles(r: Reading) -> list[Fact]:
    double = r.kind == "double_angle"
    beam, support, face = r.w("beam"), r.w("support"), r.face()
    angle, beam_leg, out_leg = r.angle("angles" if double else "angle")
    end = r.length("beam_gauge") - r.length("beam_edge")
    legs = iv(2 * out_leg + beam.tw) if double else iv(out_leg + beam.tw)
    if r.word("support_side") == "welded":
        # A weld at each toe lays its leg on the face past the toe.
        w, _ = r.weld("support_weld")
        items = [OnFace("support welds at the outstanding legs' toes", "weld", legs + w * (2 if double else 1), face, support)]
    elif double:
        items = [_pair("support bolt lines", r.length("support_gauge"), r.hole("support", across=True), face, support),
                 OnFace("outstanding legs", "part", legs, face, support)]
    else:
        # One angle beside the beam web, placed anywhere: from the web's far face to the hole's far edge.
        items = [OnFace("beam web and support bolt line", "bolt",
                        beam.tw + r.length("support_gauge") + r.hole("support", across=True) / 2, face, support),
                 OnFace("beam web and outstanding leg", "part", legs, face, support)]
    return [*_beam_web(r, beam, "angles" if double else "angle", iv(beam_leg), _start(r, end)),
            BeamEnd(end, iv(0), "support face"),
            *items,
            *_beam_to_web(beam, support, face, end)]


def shear_tee(r: Reading) -> list[Fact]:
    beam, support, face, tee = r.w("beam"), r.w("support"), r.face(), r.tee()
    end = r.length("bolt_line") - r.length("beam_edge")
    flange = iv(tee.parent.bf)
    if r.word("support_side") == "bolted":
        items = [_pair("support bolt lines", r.length("support_gauge"), r.hole("support", across=True), face, support),
                 OnFace("tee flange", "part", flange, face, support)]
    else:
        w, _ = r.weld("support_weld")
        items = [OnFace("support welds at the tee flange tips", "weld", flange + 2 * w, face, support)]
    return [*_beam_web(r, beam, "tee stem", iv(tee.depth), _start(r, end)),
            BeamEnd(end, iv(tee.parent.tf), f"{tee.label}'s flange"),
            *items,
            *_beam_to_web(beam, support, face, end)]


def shear_end_plate(r: Reading) -> list[Fact]:
    beam, support, face = r.w("beam"), r.w("support"), r.face()
    n, s, lev = r.count("rows"), r.length("pitch"), r.length("edge_vertical")
    w, _ = r.weld("weld")
    cope = r.cope()
    welds = s * (n - 1) + 2 * lev - 2 * w
    return [OnBeamWeb("end plate welds", beam, None, None, welds, None, None,
                      cope[1] if cope else None, cope[3] if cope and cope[0] == "both" else None),
            _pair("support bolt lines", r.length("support_gauge"), r.hole("support", across=True), face, support),
            OnFace("end plate", "part", r.length("plate_width"), face, support),
            *_beam_to_web(beam, support, face, r.kw_length("plate", "thickness"))]


def seated(r: Reading) -> list[Fact]:
    beam, support, face = r.w("beam"), r.w("support"), r.face()
    angle, vertical, out_leg = r.angle("angle")
    setback, length = r.length("setback"), r.length("seat_length")
    facts: list[Fact] = [SeatBearing("seat's outstanding leg", setback, iv(out_leg))]
    if r.word("support_side") == "bolted":
        n, s, lev, hole = r.count("rows"), r.length("pitch"), r.length("edge_vertical"), r.hole("angle", across=False)
        facts += [LegBolts(angle.label, lev - hole / 2, lev + s * (n - 1) + hole / 2, iv(angle.t), iv(vertical)),
                  _pair("support bolt lines", r.length("support_gauge"), r.hole("support", across=True), face, support),
                  OnFace("seat angle", "part", length, face, support)]
    else:
        w, _ = r.weld("support_weld")
        facts.append(OnFace("seat welds at the angle's ends", "weld", length + 2 * w, face, support))
    return facts + _beam_to_web(beam, support, face, setback)


def stiffened_seat(r: Reading) -> list[Fact]:
    beam, support, face = r.w("beam"), r.w("support"), r.face()
    setback = r.length("setback")
    w, sides = r.weld("weld")
    return [SeatBearing("stiffener", setback, r.length("stiffener_width")),
            OnFace("stiffener and its welds", "weld", r.kw_length("stiffener", "thickness") + w * sides, face, support),
            *_beam_to_web(beam, support, face, setback)]


def bolt_bracket(r: Reading) -> list[Fact]:
    cols, g, leh = r.count("columns"), r.length("gauge"), r.length("plate_edge")
    return [GroupOnFace(cols, g, r.hole("support", across=True), g * (cols - 1) + 2 * leh, r.face(), r.w("support"))]


def weld_bracket(r: Reading) -> list[Fact]:
    support, face = r.w("support"), r.face()
    w, sides = r.weld("weld")
    if r.has("weld_return"):
        return [OnFace("C-shaped weld's returns", "weld", r.length("weld_return") + w, face, support)]
    return [OnFace("plate and its welds", "weld", r.kw_length("plate", "thickness") + w * sides, face, support)]


def hanger(r: Reading) -> list[Fact]:
    if r.face() != "flange":
        raise Missing("a hanger hangs from a support flange")
    return [_pair("bolt lines", r.length("tee_gauge"), r.hole("support", across=True), "flange", r.w("support"))]


def flange_force(r: Reading) -> list[Fact]:
    return []


READERS: dict[str, Callable[[Reading], list[Fact]]] = {
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

UNDRAWN: dict[str, str] = {
    "flange_force": "no beam or connecting part is drawn, and `distance` does not say whether it reaches the force's "
                    "centre or its near edge, so where the bearing sits on the member is not decided",
    "stiffened_seat": "the seat plate's width across the support is not drawn; only the stiffener's fit is judged",
    "seated": "the top angle's position and length are not drawn; only the seat's fit is judged",
}
"""What each kind's lines leave undrawn, which the judge therefore cannot judge."""


def facts(component: Component, design: Design) -> list[Fact]:
    return READERS[component.kind](Reading(component, design))
