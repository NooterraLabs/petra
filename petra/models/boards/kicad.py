"""Read a KiCad 6, 7, 8 or 9 board file into one typed record. Trusted; the boundary for
.kicad_pcb files.

The record holds facts from the file only. Lengths are exact rationals in millimetres read
from the file's decimals, in KiCad's board frame: x to the right and y down, the board seen
from its top face. docs/boards.md says what is read, what is refused, and what a board file
cannot tell the enclosure deck.

A footprint's children are stored in the footprint's own frame, relative to its anchor and
before its rotation. KiCad mirrors a footprint's children when it flips the footprint to the
bottom face and stores them as they then lie, so one transform, `plane.place`, takes every
child to the board on either face. Mirroring a bottom footprint again would be the mistake.
A pad's angle in the file is its orientation on the board, the footprint's angle included.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from pathlib import Path

from . import plane
from .features import EDGE, HOLES, THICKNESS, Feature, Premise, Rule, classify, mounting, premises
from .plane import Arc, Bounds, Circle, Item, Loop, Point, Segment, ShapeError, Spot
from .sexpr import BoardError, Expr, Symbol, number, parse

FORMATS: dict[int, int] = {20211014: 6, 20221018: 7, 20240108: 8, 20241229: 9}
"""The board file version each KiCad release series writes, and the series. Each is the last
version of a development cycle in KiCad's pcbnew/pcb_io/kicad_sexpr/pcb_io_kicad_sexpr.h on
the 9.0 branch (reported). A nightly build writes a version between them, which is refused."""


class Side(Enum):
    TOP = "top"
    BOTTOM = "bottom"


_COPPER = {"F.Cu": Side.TOP, "B.Cu": Side.BOTTOM}
_COURTYARD = {Side.TOP: "F.CrtYd", Side.BOTTOM: "B.CrtYd"}
_FAB = {Side.TOP: "F.Fab", Side.BOTTOM: "B.Fab"}
_BOARD_SHAPES = {"gr_line", "gr_arc", "gr_circle", "gr_rect", "gr_poly", "gr_curve", "bezier"}
_FOOTPRINT_SHAPES = {"fp_line", "fp_arc", "fp_circle", "fp_rect", "fp_poly", "fp_curve"}


class PadKind(Enum):
    SMD = "smd"
    CONNECT = "connect"
    THROUGH_HOLE = "through-hole"
    NPTH = "npth"
    MOUNTING_HOLE = "mounting hole"


_PAD_TYPES = {"smd": (PadKind.SMD, False), "connect": (PadKind.CONNECT, False),
              "thru_hole": (PadKind.THROUGH_HOLE, True), "np_thru_hole": (PadKind.NPTH, False)}


@dataclass(frozen=True)
class Thickness:
    """The board's thickness, mm, and where the file states it: "setup.stackup" when the
    stackup's layers carry thicknesses, else "general.thickness"."""

    value: Fraction
    source: str


@dataclass(frozen=True)
class Placement:
    """A footprint's anchor on the board and its rotation in degrees, as stored."""

    at: Point
    angle: Fraction

    def spot(self, local: Point) -> Spot:
        return plane.place(local, self.at, self.angle)


@dataclass(frozen=True)
class Drill:
    """A drilled hole, `width` along the pad's x axis and `height` along its y axis. A round
    hole has both equal to its diameter; an oval one is a slot of those sizes."""

    width: Fraction
    height: Fraction
    oval: bool


@dataclass(frozen=True)
class Pad:
    """A pad as stored, and its anchor on the board. The anchor is the hole's centre; the
    copper sits at `offset` from it in the pad's frame. A drilled pad of a mounting-hole
    footprint is a MOUNTING_HOLE, and `plated` keeps whether the file made it thru_hole."""

    number: str
    kind: PadKind
    plated: bool
    shape: str
    local: Point
    angle: Fraction
    size: tuple[Fraction, Fraction]
    drill: Drill | None
    offset: Point
    at: Spot
    properties: frozenset[str]


@dataclass(frozen=True)
class Courtyard:
    """A footprint's courtyard on one board face: its loops in the footprint's frame, exact,
    each loop's bounds on the board, and the bounds on the board of the part's room on that
    face, the convex hull of the courtyard and of every shape the face's Fab layer draws."""

    face: Side
    loops: tuple[Loop, ...]
    board: tuple[Bounds, ...]
    room: Bounds


@dataclass(frozen=True)
class NoCourtyard:
    """No usable courtyard on a face: "absent", or what is wrong with the drawn one."""

    face: Side
    reason: str


@dataclass(frozen=True)
class Footprint:
    reference: str
    value: str
    library: str
    side: Side
    placement: Placement
    attributes: frozenset[str]
    pads: tuple[Pad, ...]
    courtyards: tuple[Courtyard | NoCourtyard, Courtyard | NoCourtyard]
    marks: tuple[Rule, ...]
    missing: tuple[Premise, ...]

    def courtyard(self, face: Side) -> Courtyard | NoCourtyard:
        return self.courtyards[0 if face is Side.TOP else 1]

    @property
    def features(self) -> frozenset[Feature]:
        return frozenset(m.feature for m in self.marks)


@dataclass(frozen=True)
class Via:
    """A via: its centre, drill size, and whether it passes through the whole board. A blind
    or micro via ends inside the board."""

    at: Point
    drill: Fraction
    through: bool


@dataclass(frozen=True)
class Outline:
    """The Edge.Cuts loops: one boundary holding every cutout, no cutout inside another."""

    boundary: Loop
    cutouts: tuple[Loop, ...]


@dataclass(frozen=True)
class Board:
    path: str
    sha256: str
    version: int
    kicad: int
    outline: Outline
    thickness: Thickness | None
    footprints: tuple[Footprint, ...]
    vias: tuple[Via, ...]
    missing: tuple[Premise, ...]

    def leads(self) -> tuple[tuple[Footprint, Pad], ...]:
        """Each plated through-hole pad outside a mounting hole: where a lead passes through."""
        return tuple((f, p) for f in self.footprints for p in f.pads if p.kind is PadKind.THROUGH_HOLE)


def read_board(path: Path | str) -> Board:
    """Read a .kicad_pcb file. Raises BoardError for a file Petra refuses."""
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise BoardError(str(path), f"cannot be read: {exc.strerror or exc}") from None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise BoardError(str(path), "is not UTF-8 text") from None
    return parse_board(text, str(path), hashlib.sha256(data).hexdigest())


def parse_board(text: str, path: str = "<text>", sha256: str = "") -> Board:
    """Read the text of a .kicad_pcb file. Raises BoardError."""
    root = parse(text, path)
    if root.head != "kicad_pcb":
        raise BoardError(path, f"is not a KiCad board: its list is ({root.head} ...)")
    stated = root.one("version")
    words = stated.words() if stated else ()
    version = int(words[0]) if words and words[0].isdigit() else None
    if version not in FORMATS:
        raise BoardError(path, f"has version {words[0] if words else 'none'}; Petra reads the board files of "
                               f"KiCad 6, 7, 8 and 9, versions {', '.join(map(str, FORMATS))}")
    kicad = FORMATS[version]
    footprints = tuple(_footprint(e, kicad, path) for e in root.lists("footprint"))
    thickness = _thickness(root, path)
    vias = tuple(_via(e, path) for e in root.lists("via"))
    drilled = vias or any(p.drill for f in footprints for p in f.pads)
    missing = (THICKNESS, EDGE) + ((HOLES,) if drilled else ())
    return Board(path, sha256 or hashlib.sha256(text.encode("utf-8")).hexdigest(), version, kicad,
                 _outline(root, path), thickness, footprints, vias, missing)


def _layer(e: Expr) -> str | None:
    found = e.one("layer")
    return str(found.args[0]) if found and found.args else None


def _point(e: Expr, name: str, path: str) -> Point:
    found = e.one(name)
    if found is None or len(found.args) < 2:
        raise BoardError(path, f"line {e.line}: ({e.head} ...) needs ({name} x y)")
    return number(found.args[0], path, found), number(found.args[1], path, found)


def _placement(e: Expr, path: str) -> Placement:
    at = e.one("at")
    if at is None or len(at.args) < 2:
        raise BoardError(path, f"line {e.line}: ({e.head} ...) needs (at x y)")
    angle = number(at.args[2], path, at) if len(at.args) > 2 else Fraction(0)
    return Placement((number(at.args[0], path, at), number(at.args[1], path, at)), angle)


def _thickness(root: Expr, path: str) -> Thickness | None:
    general = root.one("general")
    stated = general.one("thickness") if general else None
    value = number(stated.args[0] if stated.args else None, path, stated) if stated else None
    setup = root.one("setup")
    stack = setup.one("stackup") if setup else None
    layers = [number(t.args[0] if t.args else None, path, t)
              for layer in (stack.lists("layer") if stack else ()) for t in layer.lists("thickness")]
    if layers:
        total = sum(layers, Fraction(0))
        if value is not None and value != total:
            raise BoardError(path, f"states a thickness of {float(value)} mm in (general ...) and stackup layers that "
                                   f"sum to {float(total)} mm, and Petra cannot tell which one the board is made to")
        return Thickness(total, "setup.stackup")
    return Thickness(value, "general.thickness") if value is not None else None


def _shape(e: Expr, path: str) -> tuple[list[Item], list[tuple[Item, ...]]]:
    """The open items and the closed runs one graphic item draws."""
    if e.head in ("gr_curve", "fp_curve", "bezier"):
        raise ShapeError(f"line {e.line}: a bezier curve, which Petra does not read")
    kind = e.head[3:]
    if kind == "line":
        return [Segment(_point(e, "start", path), _point(e, "end", path))], []
    if kind == "arc":
        return [Arc(_point(e, "start", path), _point(e, "mid", path), _point(e, "end", path))], []
    if kind == "circle":
        return [], [(Circle(_point(e, "center", path), _point(e, "end", path)),)]
    if kind == "rect":
        (x0, y0), (x1, y1) = _point(e, "start", path), _point(e, "end", path)
        if x0 == x1 or y0 == y1:
            raise ShapeError(f"line {e.line}: a rectangle with no area")
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        return [], [tuple(Segment(a, b) for a, b in zip(corners, corners[1:] + corners[:1]))]
    return [], [_poly(e, path)]


def _poly(e: Expr, path: str) -> tuple[Item, ...]:
    """A polygon's points joined in order and closed, an (arc ...) entry drawn as its arc."""
    pts = e.one("pts")
    if pts is None:
        raise BoardError(path, f"line {e.line}: ({e.head} ...) needs (pts ...)")
    items: list[Item] = []
    first = at = None
    for node in pts.args:
        if isinstance(node, Expr) and node.head == "xy" and len(node.args) >= 2:
            begin = end = (number(node.args[0], path, node), number(node.args[1], path, node))
            arc = None
        elif isinstance(node, Expr) and node.head == "arc":
            arc = Arc(_point(node, "start", path), _point(node, "mid", path), _point(node, "end", path))
            begin, end = arc.start, arc.end
        else:
            raise BoardError(path, f"line {e.line}: (pts ...) holds only (xy x y) and (arc ...)")
        if at is not None and at != begin:
            items.append(Segment(at, begin))
        if arc is not None:
            items.append(arc)
        first = begin if first is None else first
        at = end
    if at is not None and at != first:
        items.append(Segment(at, first))
    if not items:
        raise ShapeError(f"line {e.line}: a polygon with no area")
    return tuple(items)


def _map(item: Item, f) -> Item:
    if isinstance(item, Segment):
        return Segment(f(item.start), f(item.end))
    if isinstance(item, Arc):
        return Arc(f(item.start), f(item.mid), f(item.end))
    return Circle(f(item.center), f(item.through))


def _outline(root: Expr, path: str) -> Outline:
    """The Edge.Cuts loops of the board and of its footprints."""
    open_items: list[Item] = []
    runs: list[tuple[Item, ...]] = []
    try:
        for e in root.items:
            if not isinstance(e, Expr):
                continue
            if e.head in _BOARD_SHAPES and _layer(e) == "Edge.Cuts":
                items, closed = _shape(e, path)
                open_items += items
                runs += closed
            elif e.head == "footprint":
                shapes = [s for s in e.items if isinstance(s, Expr) and s.head in _FOOTPRINT_SHAPES
                          and _layer(s) == "Edge.Cuts"]
                if not shapes:
                    continue
                placement = _placement(e, path)
                if plane.turn(placement.angle)[2]:
                    raise BoardError(path, f"line {e.line}: a footprint draws on Edge.Cuts and is turned by "
                                           f"{placement.angle} degrees, so its outline has no exact board coordinates")
                f = lambda p, placement=placement: placement.spot(p).point
                for s in shapes:
                    items, closed = _shape(s, path)
                    open_items += [_map(i, f) for i in items]
                    runs += [tuple(_map(i, f) for i in run) for run in closed]
        if not open_items and not runs:
            raise BoardError(path, "draws no board outline on Edge.Cuts")
        loops = [plane.loop(run) for run in plane.chain(open_items) + runs]
        problem = plane.meeting(loops)
        if problem:
            raise ShapeError(problem)
        outer = [lp for lp in loops if all(plane.inside(plane.start(m), lp) for m in loops if m is not lp)]
        if len(outer) != 1:
            raise ShapeError(f"holds {len(loops)} loops and none of them holds all the others: Petra reads one board")
        cutouts = tuple(lp for lp in loops if lp is not outer[0])
        for a in cutouts:
            for b in cutouts:
                if a is not b and plane.inside(plane.start(a), b):
                    raise ShapeError(f"the cutout through {plane.show(plane.start(a))} lies inside another cutout")
        return Outline(outer[0], cutouts)
    except ShapeError as err:
        raise BoardError(path, f"Edge.Cuts: {err}") from None


def _field(e: Expr, kicad: int, name: str, path: str) -> str:
    """A footprint's reference or value: an (fp_text reference [locked] "J1" ...) in KiCad 6 and
    7, whose parser takes a bare `locked` before the text (measured on Sofle v2 and on a board
    KiCad 7 wrote, docs/kicad_oracle.md), and a (property "Reference" "J1" ...) from KiCad 8 on (version
    20230620, "PCB Fields", reported)."""
    if kicad >= 8:
        texts = [p.args[1:] for p in e.lists("property") if p.args and p.args[0] == name]
        form = f'(property "{name}" ...)'
    else:
        texts = [t.args[1:] for t in e.lists("fp_text") if t.args and t.args[0] == name.lower()]
        texts = [a[1:] if a and isinstance(a[0], Symbol) and a[0] == "locked" else a for a in texts]
        form = f"(fp_text {name.lower()} ...)"
    if len(texts) != 1:
        raise BoardError(path, f"line {e.line}: a KiCad {kicad} footprint names its {name.lower()} in one {form}, "
                               f"and this one has {len(texts)}")
    if not texts[0] or isinstance(texts[0][0], Expr):
        raise BoardError(path, f"line {e.line}: a footprint names its {name.lower()} in a {form} with no text")
    return str(texts[0][0])


def _footprint(e: Expr, kicad: int, path: str) -> Footprint:
    library = str(e.args[0]) if e.args and not isinstance(e.args[0], Expr) else ""
    layer = _layer(e)
    if layer not in _COPPER:
        raise BoardError(path, f"line {e.line}: a footprint lies on {layer}, and Petra reads F.Cu and B.Cu")
    placement = _placement(e, path)
    reference = _field(e, kicad, "Reference", path)
    value = _field(e, kicad, "Value", path)
    attr = e.one("attr")
    pad_lists = e.lists("pad")
    properties = [frozenset(w for p in pad.lists("property") for w in p.words()) for pad in pad_lists]
    marks = classify(reference, library, frozenset().union(*properties))
    pads = tuple(_pad(p, props, placement, mounting(marks), path) for p, props in zip(pad_lists, properties))
    courtyards = (_courtyard(e, Side.TOP, placement, path), _courtyard(e, Side.BOTTOM, placement, path))
    return Footprint(reference, value, library, _COPPER[layer], placement,
                     frozenset(attr.words()) if attr else frozenset(), pads, courtyards, marks,
                     premises(marks, bool(pads), any(p.drill for p in pads)))


def _pad(e: Expr, properties: frozenset[str], placement: Placement, mount: bool, path: str) -> Pad:
    if len(e.args) < 3:
        raise BoardError(path, f"line {e.line}: a pad needs a number, a type and a shape")
    kind, plated = _PAD_TYPES.get(str(e.args[1]), (None, False))
    if kind is None:
        raise BoardError(path, f"line {e.line}: pad type {e.args[1]} is none of smd, connect, thru_hole and np_thru_hole")
    at = _placement(e, path)
    size = e.one("size")
    if size is None or len(size.args) < 2:
        raise BoardError(path, f"line {e.line}: a pad needs (size w h)")
    drill, offset = None, (Fraction(0), Fraction(0))
    stated = e.one("drill")
    if stated is not None:
        sizes = [number(w, path, stated) for w in stated.args if not isinstance(w, Expr) and w != "oval"]
        if stated.one("offset") is not None:
            offset = _point(stated, "offset", path)
        if sizes and sizes[0] > 0 and kind not in (PadKind.SMD, PadKind.CONNECT):
            drill = Drill(sizes[0], sizes[-1], "oval" in stated.words())
    if kind in (PadKind.THROUGH_HOLE, PadKind.NPTH) and drill is None:
        raise BoardError(path, f"line {e.line}: a {e.args[1]} pad needs a (drill ...) of positive size")
    if mount and drill is not None:
        kind = PadKind.MOUNTING_HOLE
    return Pad(str(e.args[0]), kind, plated, str(e.args[2]), at.at, at.angle,
               (number(size.args[0], path, size), number(size.args[1], path, size)), drill, offset,
               placement.spot(at.at), properties)


def _drawn(e: Expr, layer: str, path: str) -> tuple[list[Item], list[tuple[Item, ...]]] | None:
    """The open items and the closed runs a footprint draws on one layer, or None for none."""
    shapes = [s for s in e.items if isinstance(s, Expr) and s.head in _FOOTPRINT_SHAPES and _layer(s) == layer]
    drawn = [_shape(s, path) for s in shapes]
    return ([i for items, _ in drawn for i in items], [r for _, runs in drawn for r in runs]) if shapes else None


def _courtyard(e: Expr, face: Side, placement: Placement, path: str) -> Courtyard | NoCourtyard:
    """The courtyard on one face, and the room: a part's body may reach past its courtyard,
    as 37 of 4,119 footprints on real boards draw it on the Fab layer (measured,
    docs/kicad_oracle.md's boards), so the room holds both."""
    try:
        drawn = _drawn(e, _COURTYARD[face], path)
        if drawn is None:
            return NoCourtyard(face, "absent")
        open_items, runs = drawn
        loops = tuple(plane.loop(run) for run in plane.chain(open_items) + runs)
        problem = plane.meeting(loops) or next((f"a loop through {plane.show(plane.start(a))} lies inside another"
                                                for a in loops for b in loops
                                                if a is not b and plane.inside(plane.start(a), b)), None)
        if problem:
            raise ShapeError(problem)
        local = [plane.bounds(lp) for lp in loops]
        fab_items, fab_runs = _drawn(e, _FAB[face], path) or ([], [])
        room = plane.enclose(local, fab_items + [i for run in fab_runs for i in run])
        return Courtyard(face, loops, tuple(plane.moved(b, placement.at, placement.angle) for b in local),
                         plane.moved(room, placement.at, placement.angle))
    except ShapeError as err:
        return NoCourtyard(face, str(err))


def _via(e: Expr, path: str) -> Via:
    drill = e.one("drill")
    if drill is None or not drill.args:
        raise BoardError(path, f"line {e.line}: a via needs (drill d)")
    return Via(_placement(e, path).at, number(drill.args[0], path, drill), not {"blind", "micro"} & set(e.words()))
