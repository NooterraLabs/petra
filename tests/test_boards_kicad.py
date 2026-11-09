"""The KiCad board reader on boards written here by hand: each version header, arcs and
circles in the outline, cutouts, a footprint at 0, 90, 37.5 and 270 degrees and on the
bottom face, a through-hole connector, mounting holes, a missing courtyard, a missing
stackup and every refusal. Metamorphic relations move or flip the file and want the record
to follow. An independent second reading (tests/board_second_reading.py) places every pad
of every board here again. The solids are checked against exact volumes and the parts
layer's own surface check.

Run with `python -m unittest tests.test_boards_kicad`.
"""
from __future__ import annotations

import hashlib
import math
import tempfile
import unittest
from fractions import Fraction as F
from functools import lru_cache
from pathlib import Path

from petra.models.boards import plane
from petra.models.boards.features import EDGE, HEIGHT, HOLES, PROTRUSION, RULES, THICKNESS, Feature
from petra.models.boards.kicad import (FORMATS, Courtyard, NoCourtyard, PadKind, Placement, Side, Via,
                                       parse_board, read_board)
from petra.models.boards.plane import Arc, Bounds, Circle, Segment, Spot
from petra.models.boards.sexpr import BoardError
from petra.models.boards.solid import Errs, board_solid, hole, keepout
from petra.models.parts.exact import surface_problem
from tests.board_second_reading import _parse as second_parse
from tests.board_second_reading import _Quoted, pad_board_positions

V6, V7, V8, V9 = 20211014, 20221018, 20240108, 20241229
VERSION = {6: V6, 7: V7, 8: V8, 9: V9}
PI_LO, PI_HI = F("3.14159265358979"), F("3.14159265358980")


# --- Writing boards ---------------------------------------------------------------------


def dec(x) -> str:
    """An exact decimal as KiCad writes one."""
    if isinstance(x, str):
        return x
    if isinstance(x, float):
        raise TypeError(f"write {x} as a string: a float is a binary fraction, not the decimal it shows")
    x = F(x)
    k = 0
    while (x * 10 ** k).denominator != 1:
        k += 1
    digits = str(abs(x.numerator * 10 ** k // x.denominator)).rjust(k + 1, "0")
    text = digits if k == 0 else (digits[:-k] + "." + digits[-k:]).rstrip("0").rstrip(".")
    return "-" + text if x < 0 else text


def xy(p) -> str:
    return f"{dec(p[0])} {dec(p[1])}"


def at(p, angle=0) -> str:
    return f"(at {xy(p)}{' ' + dec(angle) if F(angle) else ''})"


STROKE = "(stroke (width 0.05) (type default))"


def line(a, b, layer="Edge.Cuts", kind="gr"):
    return f'({kind}_line (start {xy(a)}) (end {xy(b)}) {STROKE} (layer "{layer}"))'


def arc(a, m, b, layer="Edge.Cuts", kind="gr"):
    return f'({kind}_arc (start {xy(a)}) (mid {xy(m)}) (end {xy(b)}) {STROKE} (layer "{layer}"))'


def circle(c, e, layer="Edge.Cuts", kind="gr"):
    return f'({kind}_circle (center {xy(c)}) (end {xy(e)}) {STROKE} (fill none) (layer "{layer}"))'


def rect(a, b, layer="Edge.Cuts", kind="gr"):
    return f'({kind}_rect (start {xy(a)}) (end {xy(b)}) {STROKE} (fill none) (layer "{layer}"))'


def poly(points, layer, kind="fp"):
    return f'({kind}_poly (pts {" ".join(f"(xy {xy(p)})" for p in points)}) {STROKE} (fill none) (layer "{layer}"))'


def box_outline(x0, y0, x1, y1):
    c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [line(c[i], c[(i + 1) % 4]) for i in range(4)]


ROUNDED = [line((5, 0), (55, 0)), arc((55, 0), (59, 2), (60, 5)), line((60, 5), (60, 35)),
           arc((60, 35), (58, 39), (55, 40)), line((55, 40), (5, 40)), arc((5, 40), (1, 38), (0, 35)),
           line((0, 35), (0, 5)), arc((0, 5), (2, 1), (5, 0))]
"""60 by 40 mm with corners of radius 5. Each arc's mid is the corner's centre plus a 3-4-5
triangle, so it lies on the circle exactly."""

STACKUP = ('(setup (stackup (layer "F.SilkS" (type "Top Silk Screen")) '
           '(layer "F.Mask" (type "Top Solder Mask") (thickness 0.01)) '
           '(layer "F.Cu" (type "copper") (thickness 0.035)) '
           '(layer "dielectric 1" (type "core") (thickness 1.51) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02)) '
           '(layer "B.Cu" (type "copper") (thickness 0.035)) '
           '(layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01)) '
           '(layer "B.SilkS" (type "Bottom Silk Screen")) (copper_finish "None") (dielectric_constraints no)) '
           '(pad_to_mask_clearance 0))')


def pcb(*items, version=V9, thickness="1.6", stackup=STACKUP) -> str:
    lines = [f'(kicad_pcb (version {version}) (generator "pcbnew")']
    if thickness:
        lines.append(f"  (general (thickness {thickness}))")
    lines.append('  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))')
    if stackup:
        lines.append("  " + stackup)
    lines += ["  " + i for i in items]
    return "\n".join(lines) + "\n)\n"


def fields(kicad, ref, value):
    font = "(effects (font (size 1 1) (thickness 0.15)))"
    if kicad >= 8:
        return [f'(property "Reference" "{ref}" (at 0 -3 0) (layer "F.SilkS") {font})',
                f'(property "Value" "{value}" (at 0 3 0) (layer "F.Fab") {font})']
    return [f'(fp_text reference "{ref}" (at 0 -3) (layer "F.SilkS") {font})',
            f'(fp_text value "{value}" (at 0 3) (layer "F.Fab") {font})']


def footprint(library, ref, value, where, angle=0, children=(), layer="F.Cu", kicad=9):
    body = "\n    ".join(fields(kicad, ref, value) + list(children))
    return f'(footprint "{library}" (layer "{layer}")\n    {at(where, angle)}\n    {body})'


PROBE_PADS = (("1", (1, 0)), ("2", (0, 2)), ("3", (F(-3, 2), F(-1, 2))))
PROBE_YARD = ((F(-5, 2), -1), (2, -1), (2, 3), (F(-5, 2), 3))
"""An asymmetric part: no rotation or mirror maps its pads or courtyard onto themselves."""


def probe(ref, where, angle=0, bottom=False, kicad=9):
    """The probe part. On the bottom face its children are stored mirrored, as KiCad stores
    a flipped footprint, and `angle` is the angle as stored."""
    s, side = (-1, "B") if bottom else (1, "F")
    children = [poly([(x, s * y) for x, y in PROBE_YARD], f"{side}.CrtYd")]
    children += [f'(pad "{n}" smd rect {at((x, s * y), angle)} (size 1 0.6) '
                 f'(layers "{side}.Cu" "{side}.Paste" "{side}.Mask"))' for n, (x, y) in PROBE_PADS]
    return footprint("Package_SO:Probe", ref, "probe", where, angle, children, f"{side}.Cu", kicad)


def connector(ref="J1", where=(8, 20), angle=90, kicad=9):
    """A 1x3 pin header. Pad 3 has an oval drill 1 mm wide along the pad's x axis and 1.6 mm
    along its y axis."""
    return footprint("Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical", ref, "Conn_01x03", where, angle, [
        rect(("-1.8", "-1.8"), ("1.8", "6.9"), "F.CrtYd", "fp"),
        f'(pad "1" thru_hole rect {at((0, 0), angle)} (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask"))',
        f'(pad "2" thru_hole oval {at((0, "2.54"), angle)} (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask"))',
        f'(pad "3" thru_hole oval {at((0, "5.08"), angle)} (size 1.7 2.4) (drill oval 1 1.6) (layers "*.Cu" "*.Mask"))',
    ], kicad=kicad)


def mounting(ref="H1", where=(54, 6), plated=False, kicad=9):
    pad = ('(pad "1" thru_hole circle (at 0 0) (size 6.4 6.4) (drill 3.2) (layers "*.Cu" "*.Mask"))' if plated
           else '(pad "" np_thru_hole circle (at 0 0) (size 3.2 3.2) (drill 3.2) (layers "*.Cu" "*.Mask"))')
    library = "MountingHole:MountingHole_3.2mm_M3_Pad" if plated else "MountingHole:MountingHole_3.2mm_M3"
    return footprint(library, ref, "MountingHole", where, 0, [circle((0, 0), ("3.45", 0), "F.CrtYd", "fp"), pad], kicad=kicad)


VIA = '(via (at 35 35) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net 0))'


def rich(kicad=9) -> str:
    """The board most tests read: the rounded outline, a rectangular and a round cutout, the
    probe at four angles and on the bottom face, the connector, a mounting hole and a via."""
    return pcb(*ROUNDED, rect((20, 10), (26, 14)), circle((50, 30), (52, 30)),
               probe("U1", (10, 10), 0, kicad=kicad), probe("U2", (30, 25), 90, kicad=kicad),
               probe("U3", (40, 12), "37.5", kicad=kicad), probe("U4", (15, 30), 270, kicad=kicad),
               probe("U5", (45, 20), 0, bottom=True, kicad=kicad), connector(kicad=kicad), mounting(kicad=kicad),
               VIA, version=VERSION[kicad])


@lru_cache(maxsize=None)
def read(text: str):
    return parse_board(text, "test.kicad_pcb")


def part(board, ref):
    return next(f for f in board.footprints if f.reference == ref)


# --- Rewriting boards (the metamorphic relations) ---------------------------------------

POINTS = {"start", "mid", "end", "center", "xy"}


def write(node) -> str:
    if isinstance(node, list):
        return "(" + " ".join(write(n) for n in node) + ")"
    if isinstance(node, _Quoted):
        return '"' + node.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return node


def tree(text):
    return second_parse(text)[0]


def kicad_turn(q: int, p):
    """KiCad's rotation by 90q degrees: x' = x cos + y sin, y' = -x sin + y cos."""
    x, y = F(p[0]), F(p[1])
    for _ in range(q % 4):
        x, y = y, -x
    return x, y


def motion(q, t):
    return lambda p: (kicad_turn(q, p)[0] + F(t[0]), kicad_turn(q, p)[1] + F(t[1]))


def _points(node, f):
    if not isinstance(node, list):
        return node
    if node and node[0] in POINTS and not isinstance(node[0], _Quoted):
        return [node[0], *map(dec, f((node[1], node[2]))), *node[3:]]
    return [_points(n, f) for n in node]


def _at(node, f=None, turn=0):
    x, y = (F(node[1]), F(node[2]))
    if f:
        x, y = f((x, y))
    angle = (F(node[3]) if len(node) > 3 else F(0)) + turn
    return ["at", dec(x), dec(y)] + ([dec(angle)] if angle else [])


def move(text: str, q: int, t) -> str:
    """Every item of the board turned by 90q degrees about the origin, then moved by t. A
    footprint's children keep their places in its frame; its angle and its pads' angles,
    which KiCad stores as orientations on the board, gain 90q."""
    f, out = motion(q, t), []
    root = tree(text)
    for item in root[1:]:
        head = item[0] if isinstance(item, list) else None
        if head and head.startswith("gr_"):
            item = _points(item, f)
        elif head == "via":
            item = [_at(c, f) if isinstance(c, list) and c[0] == "at" else c for c in item]
        elif head == "footprint":
            item = [_at(c, f, 90 * q) if isinstance(c, list) and c[0] == "at"
                    else [_at(d, None, 90 * q) if isinstance(d, list) and d[0] == "at" else d for d in c]
                    if isinstance(c, list) and c[0] == "pad" else c for c in item]
        out.append(item)
    return write([root[0], *out])


def _swap(s):
    if isinstance(s, _Quoted) and s[:2] in ("F.", "B."):
        return _Quoted(("B." if s[0] == "F" else "F.") + s[2:])
    return s


def _mirror(node):
    if not isinstance(node, list):
        return _swap(node)
    if node and node[0] == "at":
        return ["at", node[1], dec(-F(node[2]))] + ([dec(-F(node[3]))] if len(node) > 3 else [])
    if node and (node[0] in POINTS or node[0] == "offset"):
        return [node[0], node[1], dec(-F(node[2])), *node[3:]]
    return [_mirror(n) for n in node]


def flip(text: str, ref: str) -> str:
    """The footprint `ref` flipped to the other face the way KiCad flips top to bottom: its
    layers swap, every child is mirrored in the footprint's x axis, and its angle and its
    pads' angles change sign."""
    root = tree(text)

    def flipped(fp):
        return [fp[0]] + [_at(c, None, -2 * (F(c[3]) if len(c) > 3 else 0)) if isinstance(c, list) and c[0] == "at"
                          else ["layer", _swap(c[1])] if isinstance(c, list) and c[0] == "layer" else _mirror(c)
                          for c in fp[1:]]

    out = [flipped(i) if isinstance(i, list) and i[0] == "footprint" and _ref(i) == ref else i for i in root]
    return write(out)


def _ref(fp):
    for c in fp:
        if isinstance(c, list) and len(c) > 2 and c[0] in ("property", "fp_text") and c[1] in ("Reference", "reference"):
            return c[2]
    return None


def board_texts():
    """Every board read in these tests that Petra accepts, for the second reading."""
    texts = {f"rich v{k}": rich(k) for k in (6, 7, 8, 9)}
    texts.update({f"moved {q} {t}": move(rich(), q, t) for q, t in MOTIONS})
    texts.update({f"flipped {r}": flip(rich(), r) for r in ("U1", "U2", "U3", "U4", "U5", "J1")})
    texts.update(EXTRA)
    return texts


MOTIONS = ((1, (0, 0)), (0, ("12.345", "-6.789")), (2, ("-3.5", "100.25")), (3, (7, 8)))

EXTRA = {
    "kicad-rounded": pcb(line((3, 0), (37, 0)), arc((37, 0), ("39.12132", "0.87868"), (40, 3)),
                         line((40, 3), (40, 30)), line((40, 30), (0, 30)), line((0, 30), (0, 3)),
                         arc((0, 3), ("0.87868", "0.87868"), (3, 0)), probe("U1", (20, 15), "-12.25")),
    "offset drill": pcb(*box_outline(0, 0, 30, 20), footprint("Connector:Offset", "J9", "x", (10, 10), 0, [
        '(pad "1" thru_hole oval (at 1 2) (size 2 1.5) (drill 1 (offset 0.25 0)) (layers "*.Cu" "*.Mask"))'])),
}


# --- Tests ------------------------------------------------------------------------------


class Versions(unittest.TestCase):
    def test_each_version_header_reads(self):
        for kicad in (6, 7, 8, 9):
            with self.subTest(kicad=kicad):
                board = read(rich(kicad))
                self.assertEqual((board.version, board.kicad), (VERSION[kicad], kicad))
                self.assertEqual([f.reference for f in board.footprints], ["U1", "U2", "U3", "U4", "U5", "J1", "H1"])
                self.assertEqual(part(board, "J1").value, "Conn_01x03")
        self.assertEqual(FORMATS, {V6: 6, V7: 7, V8: 8, V9: 9})

    def test_the_four_versions_give_one_record(self):
        boards = [read(rich(k)) for k in (6, 7, 8, 9)]
        for board in boards[1:]:
            self.assertEqual(board.footprints, boards[0].footprints)
            self.assertEqual(board.outline, boards[0].outline)

    def test_other_versions_are_refused(self):
        for version in ("20221017", "20240107", "20250101", "20200101", "6", "abc"):
            with self.subTest(version=version):
                with self.assertRaisesRegex(BoardError, "has version"):
                    read(pcb(*box_outline(0, 0, 10, 10), version=version))
        with self.assertRaisesRegex(BoardError, "has version none"):
            read('(kicad_pcb (generator "pcbnew") (general (thickness 1.6)))')

    def test_fields_must_match_the_version(self):
        with self.assertRaisesRegex(BoardError, r'KiCad 8 footprint names its reference in one \(property "Reference"'):
            read(pcb(*box_outline(0, 0, 30, 30), probe("U1", (10, 10), kicad=7), version=V8))
        with self.assertRaisesRegex(BoardError, r"KiCad 7 footprint names its reference in one \(fp_text reference"):
            read(pcb(*box_outline(0, 0, 30, 30), probe("U1", (10, 10), kicad=9), version=V7))

    def test_a_locked_text_reads_its_text(self):
        """KiCad 6 and 7 write a locked text with the word before the text, as in
        (fp_text reference locked "J1" ...), and a quoted "locked" is a text like any other."""
        for kicad in (6, 7):
            with self.subTest(kicad=kicad):
                locked = connector(kicad=kicad).replace('reference "J1"', 'reference locked "J1"')
                locked = locked.replace('value "Conn_01x03"', 'value locked "Conn_01x03"')
                (j1,) = read(pcb(*box_outline(0, 0, 30, 30), locked, version=VERSION[kicad])).footprints
                self.assertEqual((j1.reference, j1.value), ("J1", "Conn_01x03"))
                self.assertEqual(j1.marks, part(read(rich(kicad)), "J1").marks)
                named = connector(kicad=kicad).replace('reference "J1"', 'reference "locked"')
                (fp,) = read(pcb(*box_outline(0, 0, 30, 30), named, version=VERSION[kicad])).footprints
                self.assertEqual(fp.reference, "locked")


class Outline(unittest.TestCase):
    def test_arcs_are_kept_exact(self):
        boundary = read(rich()).outline.boundary
        arcs = [i for i in boundary.items if isinstance(i, Arc)]
        self.assertEqual(len(arcs), 4)
        mids = {i.mid for i in arcs} | {i.mid for i in map(_reversed, arcs)}
        self.assertTrue({(F(59), F(2)), (F(58), F(39)), (F(1), F(38)), (F(2), F(1))} <= mids)
        self.assertEqual(plane.center(Arc((F(55), F(0)), (F(59), F(2)), (F(60), F(5)))), (F(55), F(5)))

    def test_arc_bounds_err_on_their_named_sides(self):
        lp = read(rich()).outline.boundary
        b = plane.bounds(lp)
        self.assertLessEqual(b.deviation, plane.TOLERANCE)
        for mid in ((59, 2), (58, 39), (1, 38), (2, 1)):
            p = (F(mid[0]), F(mid[1]))
            self.assertEqual(plane.where(p, b.outer), 1, "a point of an arc lies inside the outer polygon")
            self.assertEqual(plane.where(p, b.inner), -1, "and outside the inner one")
            for polygon in (b.inner, b.outer):
                self.assertLessEqual(_dist2(p, polygon), b.deviation ** 2)
        for corner in ((0, 0), (60, 0), (60, 40), (0, 40)):
            self.assertEqual(plane.where((F(corner[0]), F(corner[1])), b.outer), -1)
        far = F(0)
        for k in range(41):
            t = F(k, 40)
            u, v = 5 * (1 - t * t) / (1 + t * t), 5 * 2 * t / (1 + t * t)  # a rational point of the circle
            for p in ((55 + u, 5 - v), (55 + u, 35 + v), (5 - u, 35 + v), (5 - u, 5 - v)):
                self.assertLessEqual(plane.where(p, b.inner), 0)
                self.assertGreaterEqual(plane.where(p, b.outer), 0)
                far = max(far, _dist2(p, b.inner), _dist2(p, b.outer))
        self.assertLessEqual(far, b.deviation ** 2, "164 exact points of the arcs lie within the deviation")
        self.assertGreater(far, (b.deviation / 2) ** 2, "and the deviation is not loose by half")
        true = 2400 - 100 + 25 * PI_LO, 2400 - 100 + 25 * PI_HI
        self.assertLess(plane.area2(b.inner) / 2, true[0])
        self.assertLess(true[1], plane.area2(b.outer) / 2)

    def test_each_path_strays_no_further_than_it_says(self):
        """The chord and tangent paths of one quarter-turn bend, each against 41 exact points
        of its arc: none lies further from the path than the path's own deviation, and some
        lie further than half of it."""
        (bend,) = plane._bends(Arc((F(55), F(0)), (F(59), F(2)), (F(60), F(5))))
        for name, (pts, dev) in (("chord", plane._chord(bend, plane.TOLERANCE)), ("tangent", plane._tangent(bend, plane.TOLERANCE))):
            with self.subTest(name):
                path = [bend.start, *pts, bend.end]
                far = F(0)
                for k in range(41):
                    t = F(k, 40)
                    p = (55 + 5 * (1 - t * t) / (1 + t * t), 5 - 10 * t / (1 + t * t))
                    far = max(far, min(plane.point_segment2(p, a, b) for a, b in zip(path, path[1:])))
                self.assertLessEqual(far, dev ** 2)
                self.assertGreater(far, (dev / 2) ** 2)

    def test_a_concave_arc(self):
        """A half-disc notch of radius 5 bites into the top edge, so its arc turns against
        the loop: the inner polygon takes its tangent path and the outer its chord path."""
        board = read(pcb(line((0, 0), (20, 0)), arc((20, 0), (25, 5), (30, 0)), line((30, 0), (50, 0)),
                         line((50, 0), (50, 30)), line((50, 30), (0, 30)), line((0, 30), (0, 0))))
        b = plane.bounds(board.outline.boundary)
        self.assertLess(plane.area2(b.inner) / 2, 1500 - F(25, 2) * PI_HI)
        self.assertLess(1500 - F(25, 2) * PI_LO, plane.area2(b.outer) / 2)
        for p in ((F(28), F(4)), (F(21), F(3))):
            self.assertEqual((plane.where(p, b.inner), plane.where(p, b.outer)), (-1, 1), p)
        self.assertEqual((plane.where((F(25), F(5)), b.inner), plane.where((F(25), F(5)), b.outer)), (0, 0),
                         "both polygons pass through the ends of each quarter-turn bend")
        self.assertFalse(plane.inside((F(25), F("4.9")), board.outline.boundary))
        self.assertTrue(plane.inside((F(25), F("5.1")), board.outline.boundary))
        solid = board_solid(board, Errs.UNDER)
        self.assertLess(solid.mesh.volume(), (1500 - F(25, 2) * PI_HI) * F("1.6"))

    def test_a_round_board_and_kicads_rounded_mids(self):
        board = read(pcb(circle((0, 0), (20, 0))))
        self.assertEqual(board.outline.boundary.items, (Circle((F(0), F(0)), (F(20), F(0))),))
        b = plane.bounds(board.outline.boundary)
        self.assertLess(plane.area2(b.inner) / 2, 400 * PI_LO)
        self.assertLess(400 * PI_HI, plane.area2(b.outer) / 2)
        board = read(EXTRA["kicad-rounded"])
        self.assertEqual(sum(isinstance(i, Arc) for i in board.outline.boundary.items), 2)

    def test_items_in_any_order_and_direction_make_one_loop(self):
        shuffled = [ROUNDED[i] for i in (3, 0, 6, 1, 5, 7, 2, 4)]
        shuffled[1] = line((55, 0), (5, 0))
        shuffled[3] = arc((60, 5), (59, 2), (55, 0))
        a, b = read(rich()).outline.boundary, read(pcb(*shuffled)).outline.boundary
        for p in ((30, 20), ("0.5", "0.5"), ("59.9", "39.9"), (1, 1), (61, 20), ("59.5", "1.2"), (57, 2), (3, 38)):
            p = (F(p[0]), F(p[1]))
            self.assertEqual(plane.inside(p, a), plane.inside(p, b), p)

    def test_cutouts(self):
        outline = read(rich()).outline
        self.assertEqual(len(outline.cutouts), 2)
        square, hole_ = outline.cutouts
        self.assertEqual(len(square.items), 4)
        self.assertEqual(hole_.items, (Circle((F(50), F(30)), (F(52), F(30))),))
        self.assertTrue(plane.inside((F(23), F(12)), square))
        self.assertTrue(plane.inside((F(23), F(12)), outline.boundary))
        self.assertFalse(plane.inside((F(23), F(15)), square))

    def test_footprint_edge_cuts_join_the_outline(self):
        text = pcb(*box_outline(0, 0, 30, 20), footprint("Slot:Cut", "X1", "slot", (10, 10), 90,
                                                          [rect((-1, -2), (1, 2), "Edge.Cuts", "fp")]))
        outline = read(text).outline
        self.assertEqual(len(outline.cutouts), 1)
        corners = {s.start for s in outline.cutouts[0].items}
        self.assertEqual(corners, {(F(8), F(11)), (F(8), F(9)), (F(12), F(9)), (F(12), F(11))},
                         "turned 90 degrees, the 2 by 4 slot lies 4 wide and 2 tall")


def _reversed(a: Arc) -> Arc:
    return Arc(a.end, a.mid, a.start)


def _dist2(p, polygon):
    return min(plane.point_segment2(p, polygon[i - 1], polygon[i]) for i in range(len(polygon)))


def _hull(points):
    """The convex hull, counter-clockwise, by the gift-wrapping walk: written here apart from
    the reader's own."""
    pts = sorted(set(points))
    hull, at = [], pts[0]
    while True:
        hull.append(at)
        nxt = pts[0] if pts[0] != at else pts[1]
        for q in pts:
            turn = (nxt[0] - at[0]) * (q[1] - at[1]) - (nxt[1] - at[1]) * (q[0] - at[0])
            if turn < 0 or (turn == 0 and plane.point_segment2(nxt, at, q) == 0 and q != at):
                nxt = q
        at = nxt
        if at == hull[0]:
            return tuple(hull)


class Footprints(unittest.TestCase):
    EXPECT = {  # pad positions worked by hand from x' = X + x cos + y sin, y' = Y - x sin + y cos
        0: ((11, 20), (10, 22), ("8.5", "19.5")),
        90: ((10, 19), (12, 20), ("9.5", "21.5")),
        270: ((10, 21), (8, 20), ("10.5", "18.5")),
    }

    def placed(self, angle, bottom=False):
        board = read(pcb(*box_outline(0, 0, 30, 40), probe("U1", (10, 20), angle, bottom)))
        return board.footprints[0]

    def test_quarter_turns(self):
        for angle, expect in self.EXPECT.items():
            with self.subTest(angle=angle):
                fp = self.placed(angle)
                self.assertEqual(fp.placement, Placement((F(10), F(20)), F(angle)))
                self.assertEqual([p.at for p in fp.pads], [Spot((F(x), F(y)), F(0)) for x, y in expect])
                self.assertEqual([p.angle for p in fp.pads], [F(angle)] * 3)

    def test_quarter_turn_courtyards_are_exact(self):
        yard = self.placed(90).courtyard(Side.TOP)
        self.assertIsInstance(yard, Courtyard)
        (b,) = yard.board
        self.assertEqual(b.deviation, 0)
        self.assertEqual(set(b.outer), {(F(9), F("22.5")), (F(9), F(18)), (F(13), F(18)), (F(13), F("22.5"))})
        self.assertEqual(set(b.inner), set(b.outer))

    def test_thirty_seven_and_a_half_degrees(self):
        fp = self.placed("37.5")
        c, s = math.cos(math.radians(37.5)), math.sin(math.radians(37.5))
        for pad, (_, (x, y)) in zip(fp.pads, PROBE_PADS):
            want = (10 + x * c + y * s, 20 - x * s + y * c)
            self.assertLess(pad.at.error, F(1, 10 ** 8))
            self.assertLess(math.dist(want, tuple(map(float, pad.at.point))), float(pad.at.error) + 1e-12)
        (b,) = fp.courtyard(Side.TOP).board
        self.assertLess(b.deviation, F(1, 10 ** 6))
        holds(self, b, [plane.place(p, (F(10), F(20)), F("37.5")) for p in _yard_points()], F(18))

    def test_the_bottom_face_mirrors(self):
        for angle in (0, 90, 270):
            with self.subTest(angle=angle):
                top, bottom = self.placed(angle), self.placed(-angle, bottom=True)
                self.assertIs(bottom.side, Side.BOTTOM)
                self.assertEqual([p.at.point for p in bottom.pads], [(x, 40 - y) for x, y in (p.at.point for p in top.pads)],
                                 "KiCad stores a bottom footprint mirrored, so the reader must not mirror it again")
                self.assertIsInstance(bottom.courtyard(Side.TOP), NoCourtyard)
                (tb,), (bb,) = top.courtyard(Side.TOP).board, bottom.courtyard(Side.BOTTOM).board
                self.assertEqual(set(bb.outer), {(x, 40 - y) for x, y in tb.outer})
        top, bottom = self.placed("37.5"), self.placed("-37.5", bottom=True)
        for p, q in zip(top.pads, bottom.pads):
            gap = math.dist(tuple(map(float, q.at.point)), (float(p.at.point[0]), 40 - float(p.at.point[1])))
            self.assertLess(gap, float(p.at.error + q.at.error) + 1e-12)

    def test_seen_from_below_a_bottom_part_is_the_top_part(self):
        """Seen from below, x runs the other way. The bottom probe seen from below and the top
        probe seen from above put their pads at the same places about the anchor, turned by
        180 degrees, because KiCad's flip mirrors in y and the view mirrors in x."""
        top, bottom = self.placed(0), self.placed(0, bottom=True)
        for p, q in zip(top.pads, bottom.pads):
            dp = (p.at.point[0] - 10, p.at.point[1] - 20)
            dq = (q.at.point[0] - 10, q.at.point[1] - 20)
            self.assertEqual((-dq[0], dq[1]), (-dp[0], -dp[1]))

    def test_a_missing_courtyard(self):
        text = pcb(*box_outline(0, 0, 30, 30), footprint("Resistor_SMD:R_0603", "R1", "10k", (10, 10), 0, [
            '(pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu" "F.Paste" "F.Mask"))']))
        fp = read(text).footprints[0]
        self.assertEqual(fp.courtyards, (NoCourtyard(Side.TOP, "absent"), NoCourtyard(Side.BOTTOM, "absent")))
        with self.assertRaisesRegex(BoardError, "R1 has no courtyard on its top face: absent"):
            keepout(read(text), fp, 0, 1, Errs.OVER)

    def test_a_broken_courtyard_is_no_courtyard(self):
        text = pcb(*box_outline(0, 0, 30, 30), footprint("Resistor_SMD:R_0603", "R1", "10k", (10, 10), 0, [
            line((-1, -1), (1, -1), "F.CrtYd", "fp"), line((1, -1), (1, 1), "F.CrtYd", "fp")]))
        yard = read(text).footprints[0].courtyard(Side.TOP)
        self.assertIsInstance(yard, NoCourtyard)
        self.assertIn("is open", yard.reason)


def _yard_points():
    corners = list(PROBE_YARD)
    mids = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(corners, corners[1:] + corners[:1])]
    return [(F(x), F(y)) for x, y in corners + mids]


def holds(test, b: Bounds, spots, area):
    """The bounds hold each spot, a point of the true boundary known to within its error, on
    the right sides and within the deviation, and the true area lies between theirs."""
    for spot in spots:
        test.assertEqual(plane.where(spot.point, b.outer), 1)
        test.assertEqual(plane.where(spot.point, b.inner), -1)
        for polygon in (b.inner, b.outer):
            d2 = _dist2(spot.point, polygon)
            test.assertGreater(d2, spot.error ** 2)
            test.assertLessEqual(d2, (b.deviation + spot.error) ** 2)
    test.assertLess(plane.area2(b.inner) / 2, area)
    test.assertLess(area, plane.area2(b.outer) / 2)


class Holes(unittest.TestCase):
    def test_a_through_hole_connector(self):
        board = read(rich())
        j1 = part(board, "J1")
        self.assertEqual([p.kind for p in j1.pads], [PadKind.THROUGH_HOLE] * 3)
        self.assertEqual([p.at.point for p in j1.pads], [(F(8), F(20)), (F("10.54"), F(20)), (F("13.08"), F(20))])
        self.assertEqual([(f.reference, p.number) for f, p in board.leads()], [("J1", "1"), ("J1", "2"), ("J1", "3")])
        self.assertEqual(j1.pads[2].drill.width, 1)
        self.assertEqual(j1.pads[2].drill.height, F("1.6"))
        self.assertTrue(j1.pads[2].drill.oval)
        self.assertEqual(j1.features, {Feature.CONNECTOR})
        self.assertEqual({r.field for r in j1.marks}, {"library", "reference"})
        self.assertEqual([p.name for p in j1.missing], ["height", "lead protrusion", "mating direction"])

    def test_an_oval_drill_is_a_slot_along_its_long_axis(self):
        pad = part(read(rich()), "J1").pads[2]
        b = hole(pad)
        ends = [(F("13.08") + d, F(20)) for d in (F("-0.8"), F("0.8"))] + [(F("13.08"), F(20) + d) for d in (F("-0.5"), F("0.5"))]
        holds(self, b, [Spot(p, F(0)) for p in ends], PI_LO / 4 + F("0.6"))
        self.assertLess(PI_HI / 4 + F("0.6"), plane.area2(b.outer) / 2)

    def test_a_mounting_hole(self):
        for plated in (False, True):
            with self.subTest(plated=plated):
                h1 = read(pcb(*box_outline(0, 0, 30, 30), mounting(where=(10, 10), plated=plated))).footprints[0]
                (pad,) = h1.pads
                self.assertEqual((pad.kind, pad.plated), (PadKind.MOUNTING_HOLE, plated))
                self.assertEqual(pad.drill.width, F("3.2"))
                self.assertEqual(h1.features, {Feature.MOUNTING_HOLE})
                self.assertEqual([p.name for p in h1.missing], ["fastener"])

    def test_npth_pegs_are_not_leads(self):
        text = pcb(*box_outline(0, 0, 30, 30), footprint("Connector_USB:USB_C", "J2", "USB_C", (15, 15), 0, [
            '(pad "" np_thru_hole circle (at -2.89 -6.1) (size 0.65 0.65) (drill 0.65) (layers "*.Cu" "*.Mask"))',
            '(pad "A1" smd rect (at -3.2 -7.7) (size 0.6 1.15) (layers "F.Cu" "F.Paste" "F.Mask"))']))
        board = read(text)
        self.assertEqual([p.kind for p in board.footprints[0].pads], [PadKind.NPTH, PadKind.SMD])
        self.assertEqual(board.leads(), ())
        self.assertEqual(board.missing, (THICKNESS, EDGE, HOLES))

    def test_a_drill_offset_moves_the_copper_not_the_hole(self):
        (pad,) = read(EXTRA["offset drill"]).footprints[0].pads
        self.assertEqual(pad.at.point, (F(11), F(12)))
        self.assertEqual(pad.offset, (F("0.25"), F(0)))
        self.assertEqual((pad.drill.width, pad.drill.height, pad.drill.oval), (F(1), F(1), False))

    def test_vias(self):
        self.assertEqual(read(rich()).vias, (Via((F(35), F(35)), F("0.3"), True),))
        blind = read(pcb(*box_outline(0, 0, 10, 10), '(via blind (at 5 5) (size 0.4) (drill 0.2) (layers "F.Cu" "In1.Cu"))'))
        self.assertFalse(blind.vias[0].through)


class Features(unittest.TestCase):
    def test_marks_and_premises(self):
        text = pcb(*box_outline(0, 0, 50, 50),
                   footprint("TestPoint:TestPoint_Pad_D1.0mm", "TP1", "TP", (5, 5), 0, [
                       '(pad "1" smd circle (at 0 0) (size 1 1) (layers "F.Cu" "F.Mask"))']),
                   footprint("Fiducial:Fiducial_1mm", "FID1", "x", (5, 10), 0, [
                       '(pad "1" smd circle (at 0 0) (size 1 1) (property pad_prop_testpoint) (layers "F.Cu" "F.Mask"))']),
                   footprint("LED_SMD:LED_0603_1608Metric", "D1", "red", (10, 5), 0, [
                       '(pad "1" smd roundrect (at -0.79 0) (size 0.95 0.8) (layers "F.Cu" "F.Paste" "F.Mask"))']),
                   footprint("Button_Switch_SMD:SW_SPST_PTS645", "SW1", "reset", (15, 5), 0, [
                       '(pad "1" smd rect (at -3 -2) (size 1 1) (layers "F.Cu" "F.Paste" "F.Mask"))']),
                   footprint("Resistor_SMD:R_0603", "R1", "10k", (20, 5), 0, [
                       '(pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu" "F.Paste" "F.Mask"))']),
                   footprint("Logo:Logo", "G1", "logo", (25, 5), 0, []))
        board = read(text)
        want = {"TP1": {Feature.TEST_POINT}, "FID1": {Feature.TEST_POINT}, "D1": {Feature.LED},
                "SW1": {Feature.SWITCH}, "R1": set(), "G1": set()}
        self.assertEqual({f.reference: set(f.features) for f in board.footprints}, want)
        self.assertEqual([p.name for p in part(board, "D1").missing], ["height", "light path"])
        self.assertEqual([p.name for p in part(board, "R1").missing], ["height", "access"],
                         "nothing marks R1, so the deck must say it needs no way through the enclosure")
        self.assertEqual(part(board, "G1").missing, (), "a footprint with no pads has no body to measure")
        self.assertNotIn(PROTRUSION, part(board, "SW1").missing)

    def test_the_library_id_marks_what_the_reference_misses(self):
        """Footprint names from real boards (measured, docs/kicad_oracle.md's boards) whose
        references carry no class letter Petra knows: an LED named D, reset and power switches
        named RST, RSW, BUT and POWER, a USB socket named USB and headers named COM and UART."""
        want = {
            ("Daylight:LED_PLCC_2835_Handsoldering", "D1"): {Feature.LED},
            ("OLIMEX_LEDs-FP:LED_0603_KA", "CHARGING1"): {Feature.LED},
            ("kbd:SW_SPST_B3U-1000P", "RST1"): {Feature.SWITCH},
            ("kbd:ResetSW", "RSW1"): {Feature.SWITCH},
            ("OLIMEX_Buttons-FP:YTS-A016-X", "BUT1"): {Feature.SWITCH},
            ("Kailh:SPDT_C128955", "POWER1"): {Feature.SWITCH},
            ("SofleKeyboard-footprint:TACT_SWITCH_TVBP06", "RSW2"): {Feature.SWITCH},
            ("OLIMEX_Connectors-FP:USB2.0_TYPE-C(A40-00119-A52-12)", "USB1"): {Feature.CONNECTOR},
            ("kit-dev-coldfire:PinHeader_1x03_P2.54mm_Vertical", "COM1"): {Feature.CONNECTOR},
            ("kit-dev-coldfire:PinHeader_2x04_P2.54mm_Vertical", "UART1"): {Feature.CONNECTOR},
            ("ceoloide:battery_connector_jst_ph_2", "JST1"): {Feature.CONNECTOR},
            ("Resistor_SMD:R_0603_1608Metric", "R1"): set(),
            ("Package_DFN_QFN:VQFN-24-1EP_4x4mm_P0.5mm", "U1"): set(),
        }
        pad = '(pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu" "F.Mask"))'
        board = read(pcb(*box_outline(0, 0, 50, 50), *(footprint(lib, ref, "x", (25, 25), 0, [pad]) for lib, ref in want)))
        self.assertEqual({(f.library, f.reference): set(f.features) for f in board.footprints}, want)
        for f in board.footprints:
            self.assertEqual("access" in [p.name for p in f.missing], not f.features, f.reference)

    def test_a_reference_letter_alone_removes_no_premise(self):
        """KiCad's MountingHole symbols are named H, and so is a standoff that stands 5 mm off
        the board. The letter adds the fastener premise and takes away neither height nor lead
        protrusion. The library id of a mounting hole takes them away."""
        hole = '(pad "1" thru_hole circle (at 0 0) (size 6 6) (drill 3.2) (layers "*.Cu" "*.Mask"))'
        board = read(pcb(*box_outline(0, 0, 30, 30),
                         footprint("Mounting_Wuerth:Mounting_Wuerth_WA-SMSI-M3_H5mm_9774050360", "H1", "x", (8, 8), 0, [hole]),
                         footprint("footprints:MountingHole_3.2mm_M3_Pad", "H2", "x", (20, 20), 0, [hole])))
        standoff, mount = board.footprints
        self.assertEqual([p.name for p in standoff.missing], ["height", "lead protrusion", "fastener"])
        self.assertEqual([p.name for p in mount.missing], ["fastener"])
        self.assertEqual([p.kind for p in mount.pads], [PadKind.MOUNTING_HOLE])

    def test_every_rule_names_its_source(self):
        for rule in RULES:
            self.assertRegex(rule.source, r"^(reported|recalled), ")


class Thickness(unittest.TestCase):
    def test_from_the_stackup(self):
        t = read(rich()).thickness
        self.assertEqual((t.value, t.source), (F("1.6"), "setup.stackup"))

    def test_a_missing_stackup(self):
        board = read(pcb(*box_outline(0, 0, 10, 10), stackup=None))
        self.assertEqual((board.thickness.value, board.thickness.source), (F("1.6"), "general.thickness"))

    def test_the_thickness_as_made_is_always_a_premise(self):
        """A stated thickness is the drawn one. The board maker's is a range the deck must give,
        so a slot sized to the stated 1.6 mm cannot pass on the file alone."""
        for text in (rich(), pcb(*box_outline(0, 0, 10, 10), stackup=None),
                     pcb(*box_outline(0, 0, 10, 10), thickness=None, stackup=None)):
            board = read(text)
            self.assertEqual(board.missing[:2], (THICKNESS, EDGE))
            self.assertIn("range", THICKNESS.what)

    def test_no_thickness_at_all(self):
        board = read(pcb(*box_outline(0, 0, 10, 10), thickness=None, stackup=None))
        self.assertIsNone(board.thickness)
        self.assertEqual(board.missing, (THICKNESS, EDGE))
        with self.assertRaisesRegex(BoardError, "states no thickness"):
            board_solid(board, Errs.OVER)
        self.assertEqual(board_solid(board, Errs.OVER, thickness=F("1.2")).mesh.volume(), 120)

    def test_a_stackup_alone(self):
        board = read(pcb(*box_outline(0, 0, 10, 10), thickness=None))
        self.assertEqual((board.thickness.value, board.thickness.source), (F("1.6"), "setup.stackup"))

    def test_two_stated_thicknesses_are_refused_by_their_values(self):
        """KiCad's own demo boards state 1.6002 mm in (general ...) and stackups that sum to
        1.6 mm (measured, docs/kicad_oracle.md), so KiCad does not keep the two equal. The
        refusal stands and names both values as the file writes them."""
        with self.assertRaises(BoardError) as caught:
            parse_board(pcb(*box_outline(0, 0, 10, 10), thickness="1.6002"), "demo.kicad_pcb")
        message = str(caught.exception)
        self.assertIn("1.6002 mm in (general ...) and stackup layers that sum to 1.6 mm", message)
        self.assertNotIn("KiCad keeps", message)


def refusals():
    box = box_outline(0, 0, 30, 30)
    return {
        "unclosed string": ('(kicad_pcb (version 20241229) (generator "pcbnew))', "a string is not closed"),
        "stray close": ("(kicad_pcb (version 20241229)))", "a ')' closes nothing"),
        "unclosed open": ("(kicad_pcb (version 20241229)", "a '(' is never closed"),
        "two lists": ("(kicad_pcb (version 20241229)) (kicad_pcb)", "exactly one top-level list"),
        "not a board": ("(kicad_sch (version 20231120))", "is not a KiCad board"),
        "exponent": (pcb(line(("1e1", 0), (30, 0)), *box[1:]), "needs a decimal number"),
        "no outline": (pcb(), "draws no board outline"),
        "open outline": (pcb(*box[:3]), "is open"),
        "branching outline": (pcb(*box, line((0, 0), (30, 30))), "branches"),
        "self-crossing": (pcb(line((0, 0), (10, 10)), line((10, 10), (10, 0)), line((10, 0), (0, 10)),
                              line((0, 10), (0, 0))), "crosses or touches itself"),
        "two boards": (pcb(*box, *box_outline(40, 0, 50, 10)), "none of them holds all the others"),
        "nested cutouts": (pcb(*box, rect((5, 5), (25, 25)), rect((10, 10), (15, 15))), "inside another cutout"),
        "cutout touches edge": (pcb(*box, rect((0, 5), (5, 10))), "two loops meet"),
        "bezier": (pcb(*box, '(gr_curve (pts (xy 5 5) (xy 6 6) (xy 7 6) (xy 8 5)) (layer "Edge.Cuts"))'), "bezier"),
        "straight arc": (pcb(*box[:3], arc((0, 30), (0, 15), (0, 0))), "three points on one line"),
        "zero circle": (pcb(*box, circle((10, 10), (10, 10))), "radius 0"),
        "zero line": (pcb(*box, line((5, 5), (5, 5))), "starts and ends at"),
        "flat rect": (pcb(*box, rect((5, 5), (5, 9))), "no area"),
        "turned edge cut": (pcb(*box, footprint("Slot:Cut", "X1", "x", (10, 10), "37.5",
                                                [rect((-1, -1), (1, 1), "Edge.Cuts", "fp")])), "no exact board coordinates"),
        "footprint layer": (pcb(*box, probe("U1", (10, 10)).replace('(layer "F.Cu")', '(layer "F.SilkS")', 1)), "lies on F.SilkS"),
        "no reference": (pcb(*box, probe("U1", (10, 10)).replace('"Reference"', '"Ref"')), "names its reference"),
        "two references": (pcb(*box, probe("U1", (10, 10)).replace('(property "Value" "probe"', '(property "Reference" "U9"')),
                           "and this one has 2"),
        "reference without text": (pcb(*box, probe("U1", (10, 10), kicad=7).replace('reference "U1" ', 'reference locked '),
                                       version=V7), "names its reference"),
        "pad type": (pcb(*box, probe("U1", (10, 10)).replace("smd rect", "surface rect", 1)), "is none of smd"),
        "pad without drill": (pcb(*box, footprint("Connector:X", "J1", "x", (10, 10), 0, [
            '(pad "1" thru_hole circle (at 0 0) (size 1.7 1.7) (layers "*.Cu"))'])), "needs a (drill"),
        "pad without size": (pcb(*box, footprint("Connector:X", "J1", "x", (10, 10), 0, [
            '(pad "1" smd circle (at 0 0) (layers "F.Cu"))'])), "needs (size w h)"),
        "footprint without at": (pcb(*box, probe("U1", (10, 10)).replace("(at 10 10)", "", 1)), "needs (at x y)"),
        "thickness disagrees": (pcb(*box, thickness="1.2"), "1.2 mm in (general ...)"),
        "via without drill": (pcb(*box, '(via (at 5 5) (size 0.6) (layers "F.Cu" "B.Cu"))'), "a via needs (drill d)"),
    }


class Refusals(unittest.TestCase):
    def test_each_malformed_file_is_refused(self):
        for name, (text, fragment) in refusals().items():
            with self.subTest(name):
                with self.assertRaises(BoardError) as caught:
                    parse_board(text, "bad.kicad_pcb")
                self.assertIn(fragment, str(caught.exception))
                self.assertTrue(str(caught.exception).startswith("bad.kicad_pcb: "))

    def test_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.kicad_pcb"
            good.write_bytes(rich().encode("utf-8"))
            board = read_board(good)
            self.assertEqual(board.sha256, hashlib.sha256(good.read_bytes()).hexdigest())
            self.assertEqual(board.footprints, read(rich()).footprints)
            bad = Path(tmp) / "bad.kicad_pcb"
            bad.write_bytes(b"(kicad_pcb (version 20241229) (generator \"\xff\"))")
            with self.assertRaisesRegex(BoardError, "is not UTF-8 text"):
                read_board(bad)
            with self.assertRaisesRegex(BoardError, "cannot be read"):
                read_board(Path(tmp) / "absent.kicad_pcb")


class Metamorphic(unittest.TestCase):
    def test_a_rigid_motion_moves_every_output(self):
        base = read(rich())
        for q, t in MOTIONS:
            with self.subTest(q=q, t=t):
                f = motion(q, t)
                moved = read(move(rich(), q, t))
                self.assertEqual(_drawn(moved.outline.boundary.items), _drawn(_map(i, f) for i in base.outline.boundary.items))
                self.assertEqual([_drawn(c.items) for c in moved.outline.cutouts],
                                 [_drawn(_map(i, f) for i in c.items) for c in base.outline.cutouts])
                self.assertEqual(moved.vias, tuple(Via(f(v.at), v.drill, v.through) for v in base.vias))
                self.assertEqual((moved.thickness, moved.missing), (base.thickness, base.missing))
                for a, b in zip(base.footprints, moved.footprints, strict=True):
                    self.assertEqual(b.placement, Placement(f(a.placement.at), a.placement.angle + 90 * q))
                    self.assertEqual((b.reference, b.side, b.marks, b.missing), (a.reference, a.side, a.marks, a.missing))
                    for p, r in zip(a.pads, b.pads, strict=True):
                        self.assertEqual(r.at, Spot(f(p.at.point), p.at.error), "exact even at 37.5 degrees")
                        self.assertEqual((r.angle, r.local, r.drill, r.kind), (p.angle + 90 * q, p.local, p.drill, p.kind))
                    self._courtyards(a, b, f, q)

    def _courtyards(self, a, b, f, q):
        for face in Side:
            ya, yb = a.courtyard(face), b.courtyard(face)
            if isinstance(ya, NoCourtyard):
                self.assertEqual(yb, ya)
            elif a.placement.angle % 90 == 0:
                self.assertEqual(yb.board, tuple(Bounds(tuple(map(f, x.inner)), tuple(map(f, x.outer)), x.deviation)
                                                 for x in ya.board))
            else:
                self.assertEqual(yb.loops, ya.loops)
                spots = [plane.place(p, b.placement.at, b.placement.angle) for p in _yard_points()]
                holds(self, yb.board[0], spots, F(18))

    def test_the_solids_bracket_the_true_volume_after_a_motion(self):
        area = 2300 - 24 - F("0.6")  # outline less the square cutout and the slot's straight part
        pis = 25 - 4 - F(1, 2) - F(1, 4) - F("2.56") - F("0.0225")  # pi times: corners, round cutout, holes, via
        for text in (rich(), move(rich(), 1, (0, 0)), move(rich(), 3, (7, 8))):
            board = read(text)
            over, under = board_solid(board, Errs.OVER), board_solid(board, Errs.UNDER)
            self.assertLess(under.mesh.volume(), (area + pis * PI_LO) * F("1.6"))
            self.assertLess((area + pis * PI_HI) * F("1.6"), over.mesh.volume())

    def test_flipping_twice_gives_back_the_original(self):
        base = read(rich())
        for ref in ("U1", "U2", "U3", "U4", "U5", "J1", "H1"):
            with self.subTest(ref=ref):
                once, twice = read(flip(rich(), ref)), read(flip(flip(rich(), ref), ref))
                a, b = part(base, ref), part(once, ref)
                self.assertEqual(part(twice, ref), a)
                self.assertIsNot(b.side, a.side)
                y = a.placement.at[1]
                for p, r in zip(a.pads, b.pads, strict=True):
                    mirror = (p.at.point[0], 2 * y - p.at.point[1])
                    if a.placement.angle % 90 == 0:
                        self.assertEqual(r.at.point, mirror)
                    else:
                        self.assertLess(math.dist(tuple(map(float, r.at.point)), tuple(map(float, mirror))),
                                        float(p.at.error + r.at.error) + 1e-12)
                ya, yb = a.courtyard(a.side), b.courtyard(b.side)
                self.assertIsInstance(yb, Courtyard)
                if a.placement.angle % 90 == 0 and ref != "H1":
                    self.assertEqual(set(yb.board[0].outer), {(x, 2 * y - z) for x, z in ya.board[0].outer})
                self.assertIsInstance(b.courtyard(a.side), NoCourtyard)


def _drawn(items):
    """The drawn items as a set, whatever their order and direction."""
    out = set()
    for i in items:
        if isinstance(i, Segment):
            out.add(("line", frozenset((i.start, i.end))))
        elif isinstance(i, Arc):
            out.add(("arc", frozenset((i.start, i.end)), i.mid))
        else:
            out.add(("circle", i.center, i.through))
    return out


def _map(item, f):
    if isinstance(item, Segment):
        return Segment(f(item.start), f(item.end))
    if isinstance(item, Arc):
        return Arc(f(item.start), f(item.mid), f(item.end))
    return Circle(f(item.center), f(item.through))


class SecondReading(unittest.TestCase):
    def test_every_pad_lands_where_the_second_reading_puts_it(self):
        texts = board_texts()
        self.assertGreaterEqual(len(texts), 16)
        count = 0
        for name, text in texts.items():
            with self.subTest(name):
                second = pad_board_positions(text)
                mine, seen = {}, {}
                for fp in read(text).footprints:
                    for pad in fp.pads:
                        seen[(fp.reference, pad.number)] = seen.get((fp.reference, pad.number), 0) + 1
                        n = seen[(fp.reference, pad.number)]
                        mine[(fp.reference, pad.number if n == 1 else f"{pad.number}#{n}")] = pad.at
                self.assertEqual(set(mine), set(second))
                for key, spot in mine.items():
                    gap = math.dist(tuple(map(float, spot.point)), second[key])
                    self.assertLessEqual(gap, float(spot.error) + 1e-9, key)
                    count += 1
        self.assertGreater(count, 250)


class Solids(unittest.TestCase):
    def test_a_polygon_board_with_a_cutout_is_exact(self):
        board = read(pcb(*box_outline(0, 0, 40, 30), rect((15, 10), (20, 14))))
        for errs in Errs:
            with self.subTest(errs=errs):
                solid = board_solid(board, errs)
                self.assertEqual((solid.mesh.volume(), solid.deviation), (1888, 0))
                self.assertEqual(solid.mesh.bounds(), ((0, -30, 0), (40, 0, F("1.6"))), "y flips; z runs up from the bottom face")
                self.assertIsNone(surface_problem(solid.mesh))

    def test_a_round_board_with_a_round_hole(self):
        board = read(pcb(circle((0, 0), (20, 0)), mounting(where=(5, 0))))
        over, under = board_solid(board, Errs.OVER), board_solid(board, Errs.UNDER)
        true = (400 - F("2.56")) * F("1.6")
        self.assertLess(under.mesh.volume(), true * PI_LO)
        self.assertLess(true * PI_HI, over.mesh.volume())
        self.assertLess(over.mesh.volume() - under.mesh.volume(), 2 * over.deviation * 2 * PI_HI * (20 + F("1.6")) * F("1.6"))
        coarse = board_solid(board, Errs.UNDER, tolerance=F(1, 10))
        self.assertIsNone(surface_problem(coarse.mesh))
        self.assertGreater(board_solid(board, Errs.OVER, holes=False).mesh.volume(), over.mesh.volume())
        with self.assertRaisesRegex(ValueError, "an UNDER solid cuts every hole"):
            board_solid(board, Errs.UNDER, holes=False)

    def test_keepouts(self):
        board = read(rich())
        for ref, face, z in (("U2", Side.TOP, (F("1.6"), F("6.6"))), ("U5", Side.BOTTOM, (-5, 0))):
            with self.subTest(ref=ref):
                (prism,) = keepout(board, part(board, ref), 0, 5, Errs.OVER)
                self.assertEqual((prism.low, prism.high), z)
                self.assertEqual(prism.mesh.volume(), 18 * 5)
                self.assertIsNone(surface_problem(prism.mesh))
        (prism,) = keepout(board, part(board, "U2"), 0, 5, Errs.UNDER)
        self.assertEqual(prism.mesh.bounds(), ((29, F("-27.5"), F("1.6")), (33, -23, F("6.6"))),
                         "the courtyard spans x 29 to 33 and y 23 to 27.5 on the board, and y flips")
        (over,), (under,) = (keepout(board, part(board, "U3"), 1, 2, e) for e in (Errs.OVER, Errs.UNDER))
        self.assertLess(under.mesh.volume(), 18)
        self.assertLess(18, over.mesh.volume())
        (j1,) = keepout(board, part(board, "J1"), 0, 3, Errs.OVER, face=Side.TOP)
        self.assertEqual(j1.mesh.volume(), F("3.6") * F("8.7") * 3)
        with self.assertRaisesRegex(BoardError, "no courtyard on its bottom face"):
            keepout(board, part(board, "J1"), 0, 3, Errs.OVER, face=Side.BOTTOM)
        with self.assertRaisesRegex(ValueError, "a keep-out runs"):
            keepout(board, part(board, "U2"), 2, 1, Errs.OVER)

    BODY = (rect((-2, -2), (2, 2), "F.CrtYd", "fp"), rect((-1, -1), (1, 5), "F.Fab", "fp"),
            circle((0, -3), (1, -3), "F.Fab", "fp"), arc((-2, 2), (-3, 3), (-2, 4), "F.Fab", "fp"),
            line((-9, 0), (-8, 0), "B.Fab", "fp"))
    """A part whose Fab body overhangs its courtyard, as the JST SH connectors and the board-edge
    capacitor of KiCad's StickHub demo do (measured, docs/kicad_oracle.md's boards). The true
    room on the top face spans x -3 to 2 and y -4 to 5 about the anchor. The B.Fab line belongs
    to the bottom face."""

    def test_a_keepout_holds_the_body_the_fab_layer_draws(self):
        board = read(pcb(*box_outline(0, 0, 40, 40), footprint("Connector_JST:Body", "J1", "x", (20, 20), 0, self.BODY)))
        for errs, sign in ((Errs.OVER, 1), (Errs.UNDER, -1)):
            with self.subTest(errs=errs):
                (prism,) = keepout(board, board.footprints[0], 0, 1, errs)
                (x0, my0, z0), (x1, my1, z1) = prism.mesh.bounds()
                beyond = (17 - x0, 16 + my1, x1 - 22, -my0 - 25)
                self.assertTrue(all(0 <= sign * b <= prism.deviation for b in beyond), (beyond, prism.deviation))
                self.assertEqual((z0, z1), (F("1.6"), F("2.6")))
                self.assertIsNone(surface_problem(prism.mesh))

    def test_a_turned_keepout_holds_the_body_the_fab_layer_draws(self):
        """Exact points of the courtyard and the Fab shapes, placed with their error, lie inside
        the OVER keep-out on its own face, turned and on the bottom face as KiCad stores it."""
        on_circle = [(s * F(a, 5), t * F(b, 5)) for a, b in ((3, 4), (4, 3), (5, 0), (0, 5)) for s in (1, -1) for t in (1, -1)]
        body = ([(F(x), F(y)) for x in (-2, 0, 2) for y in (-2, 0, 2)] + [(F(x), F(y)) for x in (-1, 1) for y in (-1, 5)]
                + [(x, y - 3) for x, y in on_circle] + [(x - 2, y + 3) for x, y in on_circle if x <= 0])
        base = pcb(*box_outline(0, 0, 40, 40), footprint("Connector_JST:Body", "J1", "x", (20, 20), "37.5", self.BODY))
        for name, text, mirror, angle in (("37.5", base, 1, F("37.5")), ("flipped", flip(base, "J1"), -1, F("-37.5"))):
            with self.subTest(name):
                fp = read(text).footprints[0]
                over, under = (keepout(read(text), fp, 0, 1, e)[0] for e in (Errs.OVER, Errs.UNDER))
                room = _hull([(x, y) for x, y, _ in map(over.mesh.point, range(len(over.mesh.vertices)))])
                for x, y in body:
                    spot = plane.place((x, mirror * y), (F(20), F(20)), angle)
                    p = (spot.point[0], -spot.point[1])
                    self.assertEqual(plane.where(p, room), 1, (x, y))
                    self.assertGreater(_dist2(p, room), spot.error ** 2)
                for k in range(len(under.mesh.vertices)):
                    self.assertGreaterEqual(plane.where(under.mesh.point(k)[:2], room), 0)

    def test_each_solid_has_its_own_identity(self):
        """A mesh's path and sha256 name it. Two solids that differ in height, face, footprint,
        thickness or holes are two meshes, each with its own name."""
        board = read(rich())
        u2 = part(board, "U2")
        meshes = [keepout(board, u2, 0, 5, Errs.OVER)[0].mesh, keepout(board, u2, 0, 10, Errs.OVER)[0].mesh,
                  keepout(board, u2, 1, 6, Errs.OVER)[0].mesh, keepout(board, part(board, "U1"), 0, 5, Errs.OVER)[0].mesh,
                  keepout(board, u2, 0, 5, Errs.OVER, thickness=2)[0].mesh, board_solid(board, Errs.OVER).mesh,
                  board_solid(board, Errs.OVER, thickness=2).mesh, board_solid(board, Errs.OVER, holes=False).mesh]
        self.assertEqual(len({m.path for m in meshes}), len(meshes), [m.path for m in meshes])
        self.assertEqual(len({m.sha256 for m in meshes}), len(meshes))
        again = keepout(read(rich()), u2, 0, 5, Errs.OVER)[0].mesh
        self.assertEqual((again.path, again.sha256), (meshes[0].path, meshes[0].sha256), "the same solid, the same name")

    def test_two_footprints_with_one_reference(self):
        """Sofle v2 names 29 references twice, a reversible part drawn once per face (measured,
        docs/kicad_oracle.md's boards). The record keeps both, and their keep-outs are two
        meshes with two names."""
        board = read(pcb(*box_outline(0, 0, 40, 40), probe("SW1", (10, 10)), probe("SW1", (30, 30)),
                         probe("SW1", (10, 10), bottom=True)))
        self.assertEqual([f.reference for f in board.footprints], ["SW1"] * 3)
        meshes = [keepout(board, f, 0, 5, Errs.OVER)[0].mesh for f in board.footprints]
        self.assertEqual(len({m.path for m in meshes}), 3, [m.path for m in meshes])
        self.assertEqual(len({m.sha256 for m in meshes}), 3)

    def test_voids_that_meet_are_refused(self):
        edge = pcb(*box_outline(0, 0, 30, 30), mounting(where=("1.2", 15)))
        with self.assertRaisesRegex(BoardError, "reach the bounds of the board's edge"):
            board_solid(read(edge), Errs.UNDER)
        two = pcb(*box_outline(0, 0, 30, 30), mounting("H1", where=(10, 10)), mounting("H2", where=(13, 10)))
        with self.assertRaisesRegex(BoardError, "the hole of pad  of H1 and the hole of pad  of H2 meet"):
            board_solid(read(two), Errs.OVER)


if __name__ == "__main__":
    unittest.main()
