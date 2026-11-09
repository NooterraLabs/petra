"""The parts layer's adversarial gate: `python scripts/parts_gate.py [--n 300] [--seed 1]
[--workers 4] [--log PATH]`.

Generates designs the parts rules should pass, in five families (a lid screwed to a base,
a board dropped into a tray, a peg pressed into a block, a heat-set insert in a printed
part, a milled block with mass claims), and asks two things of each, as
scripts/steel_gate.py and scripts/metamorphic.py ask of the steel deck.

Metamorphic: every obligation keeps its outcome when the whole design turns 90 or 180
degrees about z, when each mesh frame moves and its placement moves back, when the
assembly moves, when flat edges of every mesh are split at their midpoints, when the
triangles are reordered, when each triangle starts at its next corner, when every
coordinate is written with six decimals, and when the first part's frame moves 10^5 mm
with one corner 1e-13 mm out, near the 2^60 the exact evaluator holds, and when every
length doubles where every bound is signed or linear in length. Turning by 90 degrees
leaves out the build-volume rules, whose machine axes do not turn with the part.

Planted: a mutation that breaks the design never comes back PASS, read as every modelled
obligation certified. An unmodelled rule's gap is left out, since it is open whatever the
design. The plants move a part into another, thin a wall past what its rule needs, swap a
screw for the next size, loosen a press, shrink or shorten an insert's hole, grow a part
into its neighbour's allowance, nest a void or an outward shell in a solid part, and move
a broken design's first frame as far as the frame relation does.

A generated design that does not pass is counted, not failed, since a FAIL may be
conservative. Untrusted tooling that never changes a verdict. Exits 1 when a relation
breaks, a plant passes or a design crashes the checker.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field, replace
from fractions import Fraction
from multiprocessing import Pool
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import petra  # noqa: E402
from petra.models.parts import engine, lower, mesh  # noqa: E402
from petra.models.parts.rules import RULE_BY_ID, Evaluator  # noqa: E402
from tests.parts_meshes import ascii_stl, blind_block, box, flipped, pin, plate, tray, tube  # noqa: E402

Q = Fraction
HEAD = 'petra 0\ndesign "t" {\n  owner "a@b.c"\n  environment indoor_dry\n}\n'
SIGNED = 'signed "a@b.c" source "gate"'
AL, PETG, PC = "aluminium.6061_T6", "polymer.petg", "polymer.pc"
MILL, FDM = "process.mill.al6061_3axis", "process.print.fdm_petg_0_4"
COS = Q("0.99518")          # cos(pi / 32) = 0.995185, rounded down: a 32-gon's sides over its corners
GROW = Q("1.0102")          # a circumscribed 32-gon's corners over its radius, rounded up
UNMODELLED = frozenset(r.id for r in RULE_BY_ID.values() if r.evaluator is Evaluator.UNMODELLED)
EXTENT = frozenset({"print.volume", "powder.volume", "sheet.bed"})
AXES = {"top": (0, 0, 1), "bottom": (0, 0, -1), "right": (1, 0, 0), "left": (-1, 0, 0), "back": (0, 1, 0),
        "front": (0, -1, 0)}
NAMES = {v: k for k, v in AXES.items()}
# The registry's ISO 4762 and ISO 10642 rows: d, pitch, head diameter least and greatest.
SCREWS = {("M2_5", "shcs"): ("2.5", "0.45", "4.3", "4.5"), ("M3", "shcs"): ("3", "0.5", "5.3", "5.5"),
          ("M4", "shcs"): ("4", "0.7", "6.75", "7"), ("M3", "csk"): ("3", "0.5", "5.5", "6.72"),
          ("M4", "csk"): ("4", "0.7", "7.5", "8.96")}
LENGTHS = ((6, Q("0.25")), (8, Q("0.3")), (10, Q("0.3")), (12, Q("0.35")), (16, Q("0.35")), (20, Q("0.45")))
# The registry's heat-set inserts: hole least and greatest, length, wall.
INSERTS = {"insert.M3x5_7": ("3.9", "4.1", "5.7", "1.6"), "insert.M3x4": ("3.9", "4.1", "4", "1.6"),
           "insert.M4x8_1": ("5.5", "5.7", "8.1", "2")}


# --- Designs --------------------------------------------------------------------------------


@dataclass
class Hole:
    id: str
    at: tuple
    along: str
    diameter: Q
    role: str
    extra: str = ""


@dataclass
class Part:
    name: str
    tris: list
    material: str
    process: str | None = None
    tolerance: Q | None = None
    holes: list = field(default_factory=list)
    mass: tuple | None = None           # (least, greatest), g
    cg: tuple | None = None             # mm, in the part's own frame
    finish: str | None = None


@dataclass
class Design:
    family: str
    parts: list
    places: list = field(default_factory=list)      # (name, offset)
    inserts: list = field(default_factory=list)     # (name, axis name, travel)
    lines: list = field(default_factory=list)       # fasten and press lines, as written
    claims: list = field(default_factory=list)
    facts: dict = field(default_factory=dict)       # what the plants need to know


def num(q, places: int = 0) -> str:
    """An exact decimal, with at least `places` decimals."""
    q = Q(q)
    k = max(next(k for k in range(0, 40) if (q * 10 ** k).denominator == 1), places)
    n = int(q * 10 ** k)
    digits = str(abs(n)).rjust(k + 1, "0")
    text = digits[:-k] + "." + digits[-k:] if k else digits
    return ("-" if n < 0 else "") + text


def _point(p) -> str:
    return f"({num(p[0])} mm, {num(p[1])} mm, {num(p[2])} mm)"


def render(d: Design, tmp: str, places: int = 0) -> str:
    out = []
    for p in d.parts:
        path, sha = ascii_stl(Path(tmp) / f"{p.name}.stl", [tuple(tuple(num(c, places) for c in v) for v in t)
                                                            for t in p.tris])
        lines = [f'  mesh "{str(path.resolve()).replace(chr(92), "/")}" sha256 "{sha}" units mm', f"  material {p.material}"]
        if p.process:
            lines.append(f"  process {p.process}")
        if p.tolerance is not None:
            lines.append(f"  tolerance in [{num(p.tolerance)} mm, {num(p.tolerance)} mm] {SIGNED}")
        if p.cg is not None:
            lines.append(f"  cg {_point(p.cg)}")
        if p.mass is not None:
            lines.append(f"  mass in [{num(p.mass[0])} g, {num(p.mass[1])} g] {SIGNED}")
        if p.finish:
            lines.append(f"  finish {p.finish}")
        for h in p.holes:
            lines.append(f"  hole {h.id} at {_point(h.at)} along {h.along} diameter {num(h.diameter)} mm {h.role}{h.extra}")
        out.append(f"part {p.name} {{\n" + "\n".join(lines) + "\n}\n")
    if d.places:
        body = [f"  place {n} at {_point(o)} facing top front" for n, o in d.places]
        body += [f"  insert {n} along {a} from {num(t)} mm" for n, a, t in d.inserts]
        body += [f"  {line}" for line in d.lines]
        out.append("assembly a {\n" + "\n".join(body) + "\n}\n")
    out += [c + "\n" for c in d.claims]
    return "".join(out)


def outcomes(text: str, tmp: str) -> dict | str:
    """Each obligation's outcome by requirement, or the input error."""
    out = petra.check(HEAD + text, path=f"{tmp}/t.petra", repair=False)
    if out["status"] == "INPUT_ERROR":
        return "error: " + str(out["error"])
    return {ob["requirement"]: ob["outcome"] for v in out["verdicts"] for ob in v["obligations"]}


def _mode(requirement: str) -> str:
    return requirement.split("/")[1]


def _held(got: dict) -> list[str]:
    """The modelled obligations a design does not certify."""
    return sorted(k for k, o in got.items() if o != "certified" and _mode(k) not in UNMODELLED)


def passes(got) -> bool:
    return isinstance(got, dict) and not _held(got)


# --- Geometry on exact triangles -------------------------------------------------------------


def _q(tris):
    return [tuple(tuple(c if isinstance(c, Q) else Q(str(c)) for c in v) for v in t) for t in tris]


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _normal(t):
    return _cross(_sub(t[1], t[0]), _sub(t[2], t[0]))


def _up(x: float) -> Q:
    """A rational at or above the float x, with room for its rounding."""
    return Q(math.ceil(x * 1.000001 * 10 ** 9) + 1, 10 ** 9)


def volume(tris) -> Q:
    return sum(sum(n * c for n, c in zip(_cross(a, b), c3)) for a, b, c3 in tris) / 6


def shell(tris, a: Q) -> Q:
    """At least the volume within `a` of the surface: area times a, plus 4 a^2 per unit of
    edge and 5 a^3 per corner, the same bound the parts layer takes, over every edge
    rather than its bent ones only."""
    area = sum(_up(math.sqrt(sum(float(x) ** 2 for x in _normal(t))) / 2) for t in tris)
    edges = {frozenset((t[m], t[(m + 1) % 3])) for t in tris for m in range(3)}
    ridge = sum(_up(math.sqrt(sum(float(x - y) ** 2 for x, y in zip(*e)))) for e in edges)
    corners = len({v for t in tris for v in t})
    return area * a + 4 * ridge * a * a + 5 * corners * a ** 3


def split_flat_edges(tris, rng, count=3):
    """Split up to `count` edges between two coplanar triangles facing the same way at their
    midpoints: the same solid, more triangles."""
    tris = list(tris)
    for _ in range(count):
        owners = {}
        for n, t in enumerate(tris):
            for m in range(3):
                owners[(t[m], t[(m + 1) % 3])] = n
        flat = []
        for (p, q), n in owners.items():
            o = owners.get((q, p))
            if o is None or o < n:
                continue
            a, b = _normal(tris[n]), _normal(tris[o])
            if _cross(a, b) == (0, 0, 0) and sum(x * y for x, y in zip(a, b)) > 0:
                flat.append((p, q, n, o))
        if not flat:
            break
        p, q, n, o = rng.choice(sorted(flat, key=str))
        mid = tuple((x + y) / 2 for x, y in zip(p, q))
        new = [t for k, t in enumerate(tris) if k not in (n, o)]
        for t in (tris[n], tris[o]):
            m = next(m for m in range(3) if {t[m], t[(m + 1) % 3]} == {p, q})
            a, b, c = t[m], t[(m + 1) % 3], t[(m + 2) % 3]
            new += [(a, mid, c), (mid, b, c)]
        tris = new
    return tris


# --- Families ---------------------------------------------------------------------------------


def _floor(x: Q, step: str) -> Q:
    return (x // Q(step)) * Q(step)


def _ceil(x: Q, step: str) -> Q:
    return -((-x) // Q(step)) * Q(step)


def stack(rng: random.Random) -> Design:
    """A lid screwed into a base: a clear hole sized for the shank, a countersink when the
    head is countersunk, and a tapped or formed hole inside the thread's pitch diameter."""
    size, head = rng.choice(sorted(SCREWS))
    d, pitch, _, head_hi = (Q(x) for x in SCREWS[(size, head)])
    role = rng.choice(["tap", "form"])
    k = Q(3, 2) if role == "tap" else Q(2)
    t_b = rng.choice([Q("0.01"), Q("0.02"), Q("0.03")])
    milled = rng.random() < 0.5
    a_l = Q("0.13") if milled else Q("0.05")
    r_b = _floor((d - Q(13, 20) * pitch) / 2 - t_b - Q("0.03"), "0.01")
    r_l = _ceil((GROW * d / 2 + a_l + t_b + Q("0.1")) / COS, "0.01")
    sink = _ceil((GROW * head_hi / 2 + a_l + t_b + Q("0.05")) / COS, "0.01") if head == "csk" else None
    lid_h = max(rng.choice([2, 3, 4]), int(sink - r_l) + 2 if sink else 0)
    fits = [(n, h) for n, h in LENGTHS if n - h - lid_h >= k * d + 1]
    length, half = fits[0] if rng.random() < 0.7 or len(fits) == 1 else fits[1]
    base_h = int(length + half - lid_h) + 2 + rng.choice([0, 1, 3])
    side = int(head_hi) + 10 + 2 * rng.choice([0, 1, 2])
    c = (Q(side, 2) + Q(rng.choice([-1, 0, 1]), 2), Q(side, 2))
    base = Part("base", _q(plate((0, 0, 0), (side, side, base_h), c, num(r_b))), AL, None, t_b,
                [Hole("h", (c[0], c[1], Q(base_h)), "bottom", 2 * r_b, role)])
    extra = f" countersink {num(2 * sink)} mm" if sink else ""
    lid = Part("lid", _q(plate((0, 0, 0), (side, side, lid_h), c, num(r_l), sink=num(sink) if sink else None)), AL,
               MILL if milled else None, None if milled else a_l,
               [Hole("h", (c[0], c[1], Q(lid_h)), "bottom", 2 * r_l, "clear", extra)])
    screw = f"screw.{size}x{length}_{head}"
    return Design("stack", [base, lid], [("base", (Q(0),) * 3), ("lid", (Q(0), Q(0), Q(base_h)))],
                  [("lid", "bottom", Q(20))], [f"fasten f {screw} through lid.h into base.h"], [],
                  {"size": size, "head": head, "side": side, "c": c, "base_h": base_h, "d": d, "r_b": r_b})


def enclosure(rng: random.Random) -> Design:
    """A board dropped into a tray with room on every side beyond both allowances, and mass
    and centre-of-mass claims with room around their bounds."""
    printed = rng.random() < 0.5
    w, dd, h = rng.choice([40, 50, 60, 80]), rng.choice([30, 40, 50]), rng.choice([15, 20, 30])
    wall, floor = rng.choice([Q(2), Q("2.5"), Q(3)]), rng.choice([Q(2), Q(3)])
    a = Q("0.5") if printed else Q("0.13")
    room = a + Q("0.4") + Q(rng.choice([0, 1, 2]), 2)
    bw, bd = w - 2 * wall - 2 * room - rng.choice([0, 2, 4]), dd - 2 * wall - 2 * room - rng.choice([0, 2])
    tris = _q(tray((0, 0, 0), (w, dd, h), wall, floor))
    case = Part("case", tris, PETG if printed else AL, FDM if printed else MILL)
    m = Q(rng.choice([5, 8, 12]))
    board = Part("board", _q(box((0, 0, 0), (bw, bd, "1.6"))), PC, None, Q("0.1"), mass=(m, m + 1),
                 cg=(bw / 2, bd / 2, Q("0.8")))
    vol, sh = volume(tris), shell(tris, a)
    dens = Q(128, 100000) if printed else Q(27, 10000)       # g/mm3, the registry's greatest
    claims = [f"claim light: a.mass <= {num(_ceil((vol + sh) * dens * Q(102, 100) + m + 2, '0.1'))} g"]
    if not printed:
        lower = (vol - sh) * dens * Q(98, 100) + m
        claims.append(f"claim heavy: a.mass >= {num(_floor(lower, '0.1'))} g")
        claims.append(f"claim low: a.cg_z <= {h + 2} mm")
    return Design("enclosure", [case, board], [("case", (Q(0),) * 3), ("board", (wall + room, wall + room, floor))],
                  [("board", "bottom", Q(h + 5))], [], claims, {"bd": bd, "wall": wall, "w": w})


def press(rng: random.Random) -> Design:
    """A peg pressed into a block, both 32-gons in phase, with an interference range around
    what the meshes give over both tolerances."""
    r_h = rng.choice([Q("1.5"), Q(2), Q("2.5"), Q(3)])
    delta = rng.choice([Q("0.012"), Q("0.015"), Q("0.02")])
    t = rng.choice([Q("0.001"), Q("0.002"), Q("0.0025")])
    r_p = r_h + delta
    thick = rng.choice([6, 8, 10])
    least = 2 * delta * COS - 4 * t
    most = 2 * (r_p - COS * r_h) + 4 * t
    lo, hi = _floor(least - Q("0.002"), "0.001"), _ceil(most + Q("0.002"), "0.001")
    side = int(2 * r_h) + 12
    c = (Q(side, 2), Q(side, 2))
    block = Part("block", _q(plate((0, 0, 0), (side, side, thick), c, num(r_h))), AL, None, t,
                 [Hole("h", (c[0], c[1], Q(thick)), "bottom", 2 * _floor(COS * r_h, "0.001"), "press")])
    peg = Part("peg", _q(pin(c, num(r_p), 0, thick)), AL, None, t)
    return Design("press", [block, peg], [("block", (Q(0),) * 3), ("peg", (Q(0),) * 3)], [("peg", "bottom", Q(10))],
                  [f"press p peg into block.h diameter {num(2 * r_p)} mm interference {num(lo)} mm to {num(hi)} mm"], [],
                  {"r_p": r_p, "c": c, "side": side, "thick": thick})


def _insert_mesh(f: dict, r: Q, edge: Q | None = None, short: bool = False):
    """The insert family's part: a plate with a through hole, a block with a blind one or a
    standoff, `edge` mm of wall on one side when given, too short for the insert when
    `short`. Returns its triangles and the height of the hole's mouth."""
    c, side, thick, depth = f["c"], f["side"], f["thick"], f["depth"]
    if short:
        depth, thick = int(f["length"]) - 1, (thick if f["shape"] == "blind" else int(f["length"]) - 1)
    if f["shape"] == "standoff":
        return tube(c, num(r), num(r + edge if edge is not None else f["r_out"]), 0, thick), thick
    hi = (c[0] + r + edge if edge is not None else side, side, thick)
    if f["shape"] == "blind":
        return blind_block((0, 0, 0), hi, c, num(r), depth), thick
    return plate((0, 0, 0), hi, c, num(r)), thick


def insert(rng: random.Random) -> Design:
    """A heat-set insert in a printed plate, blind block or standoff, held to a signed
    0.01 mm, its hole in the catalogue's range less the preset's shrink."""
    kind = rng.choice(sorted(INSERTS))
    h_min, h_max, length, wall = (Q(x) for x in INSERTS[kind])
    r = min(_ceil((h_min + Q("0.22")) / (2 * COS) + Q("0.004"), "0.005"), _floor((h_max + Q("0.08")) / 2 - Q("0.002"), "0.005"))
    shape = rng.choice(["plate", "blind", "standoff"])
    side = int(2 * (r + wall)) + 6 + 2 * rng.choice([0, 1])
    f = {"kind": kind, "r": r, "shape": shape, "length": length, "side": side, "c": (Q(side, 2), Q(side, 2)),
         "thick": int(length) + 2 + rng.choice([0, 2]), "depth": None, "r_out": None}
    if shape == "blind":
        f["thick"], f["depth"] = int(length) + 4, int(length) + 1 + rng.choice([0, 1])
    elif shape == "standoff":
        f["r_out"] = _ceil((r + Q("0.02") + wall + Q("0.3")) / COS, "0.01")
        f["c"] = (f["r_out"] + 2, f["r_out"] + 2)
    tris, top = _insert_mesh(f, r)
    extra = f" depth {f['depth']} mm" if f["depth"] else ""
    hole = Hole("h", (f["c"][0], f["c"][1], Q(top)), "bottom", _floor(2 * COS * r, "0.01"), f"insert {kind}", extra)
    return Design("insert", [Part("p", _q(tris), PETG, FDM, Q("0.01"), [hole])], facts=f)


def solid(rng: random.Random) -> Design:
    """A milled block, anodized or bare, with mass claims around its bound over the
    tolerance and the coat."""
    w, dd = Q(rng.choice([5, 8, 12, 20, 30])), Q(rng.choice([5, 8, 12, 20, 30]))
    h = Q(rng.choice([3, 5, 8, 12]))
    finish = rng.choice([None, "process.anodize_ii"])
    tris = _q(box((0, 0, 0), (w, dd, h)))
    sh = shell(tris, Q("0.13") + (Q("0.0125") if finish else 0))
    upper = (volume(tris) + sh) * Q(27, 10000) + (2 * Q(4, 1000) * sh if finish else 0)
    lower = (volume(tris) - sh) * Q(27, 10000)
    claims = [f"claim light: p.mass <= {num(_ceil(upper * Q(102, 100) + Q('0.1'), '0.01'))} g"]
    heavy = lower > Q("0.2")
    if heavy:
        claims.append(f"claim heavy: p.mass >= {num(_floor(lower * Q(98, 100), '0.01'))} g")
    return Design("solid", [Part("p", tris, AL, MILL, finish=finish)], claims=claims,
                  facts={"size": (w, dd, h), "heavy": heavy})


FAMILIES: dict[str, Callable[[random.Random], Design]] = {
    "stack": stack, "enclosure": enclosure, "press": press, "insert": insert, "solid": solid}


# --- Relations ---------------------------------------------------------------------------------


def _turned(d: Design, f) -> Design:
    parts = [replace(p, tris=[tuple(f(v) for v in t) for t in p.tris],
                     holes=[replace(h, at=f(h.at), along=NAMES[f(AXES[h.along])]) for h in p.holes],
                     cg=None if p.cg is None else f(p.cg)) for p in d.parts]
    return replace(d, parts=parts, places=[(n, f(o)) for n, o in d.places],
                   inserts=[(n, NAMES[f(AXES[a])], t) for n, a, t in d.inserts])


def _moved(point, by):
    return tuple(c + b for c, b in zip(point, by))


def _frames_moved(d: Design) -> Design:
    by = (Q("7.25"), Q("-3.5"), Q("1.75"))
    parts = [replace(p, tris=[tuple(_moved(v, by) for v in t) for t in p.tris],
                     holes=[replace(h, at=_moved(h.at, by)) for h in p.holes],
                     cg=None if p.cg is None else _moved(p.cg, by)) for p in d.parts]
    return replace(d, parts=parts, places=[(n, _moved(o, tuple(-b for b in by))) for n, o in d.places])


def _each_mesh(d: Design, f) -> Design:
    return replace(d, parts=[replace(p, tris=f(p.tris)) for p in d.parts])


def _scaled(d: Design) -> Design | None:
    """Every length doubled: meshes, holes, places, travels, signed tolerances and every
    length a line states, with each mass claim times 8. Defined only where every bound is
    signed or linear in length, the press family and a bare solid block, whose mill's
    0.13 mm becomes a signed 0.26 mm and whose mill rules, which have no model, drop out."""
    if d.family == "solid" and d.parts[0].finish is None:
        d = replace(d, parts=[replace(d.parts[0], process=None, tolerance=Q("0.13"))])
    elif d.family != "press":
        return None

    def two(v):
        return tuple(2 * c for c in v)

    def lengths(text):
        return re.sub(r"(-?\d+(?:\.\d+)?) mm", lambda m: f"{num(2 * Q(m.group(1)))} mm", text)

    parts = [replace(p, tris=[tuple(two(v) for v in t) for t in p.tris],
                     tolerance=None if p.tolerance is None else 2 * p.tolerance,
                     holes=[replace(h, at=two(h.at), diameter=2 * h.diameter, extra=lengths(h.extra)) for h in p.holes],
                     cg=None if p.cg is None else two(p.cg)) for p in d.parts]
    claims = [re.sub(r"(-?\d+(?:\.\d+)?) g\b", lambda m: f"{num(8 * Q(m.group(1)))} g", c) for c in d.claims]
    return replace(d, parts=parts, places=[(n, two(o)) for n, o in d.places],
                   inserts=[(n, a, 2 * t) for n, a, t in d.inserts], lines=[lengths(x) for x in d.lines], claims=claims)


# name -> (design, rng) -> (variant, decimals to write, rules left out) or None when it does not apply
RELATIONS: dict[str, Callable] = {
    "turn_90": lambda d, rng: (_turned(d, lambda p: (-p[1], p[0], p[2])), 0, EXTENT),
    "turn_180": lambda d, rng: (_turned(d, lambda p: (-p[0], -p[1], p[2])), 0, frozenset()),
    "move_frames": lambda d, rng: (_frames_moved(d), 0, frozenset()),
    "move_assembly": lambda d, rng: (replace(d, places=[(n, _moved(o, (Q("13.5"), Q("-8.25"), Q(0))))
                                                        for n, o in d.places]), 0, frozenset()) if d.places else None,
    "split_edges": lambda d, rng: (_each_mesh(d, lambda t: split_flat_edges(t, rng)), 0, frozenset()),
    "reorder": lambda d, rng: (_each_mesh(d, lambda t: rng.sample(t, len(t))), 0, frozenset()),
    "next_corner": lambda d, rng: (_each_mesh(d, lambda t: [(b, c, a) for a, b, c in t]), 0, frozenset()),
    "decimals": lambda d, rng: (d, 6, frozenset()),
    "far_frame": lambda d, rng: (_far(d), 0, frozenset()),
    "scale_2": lambda d, rng: None if _scaled(d) is None else (_scaled(d), 0, UNMODELLED),
}


# --- Plants ------------------------------------------------------------------------------------


def _part(d: Design, name: str) -> Part:
    return next(p for p in d.parts if p.name == name)


def _swap(d: Design, part: Part) -> Design:
    return replace(d, parts=[part if p.name == part.name else p for p in d.parts])


def _into(d: Design, by: tuple) -> Design:
    """The last placed part moved by `by`, into its neighbour."""
    name = d.places[-1][0]
    return replace(d, places=[(n, _moved(o, by) if n == name else o) for n, o in d.places])


def _far(d: Design) -> Design:
    """The first part's mesh frame moved 10^5 mm along x and its placement moved back, with
    the corner farthest along x pushed 1e-13 mm farther out: 13 decimals, the most the
    reader holds, on a 10^5 mm coordinate, 1.0e18 units against the 2^60 = 1.15e18 the
    exact evaluator holds."""
    p, by = d.parts[0], (Q(10 ** 5), Q(0), Q(0))
    corner = max((v for t in p.tris for v in t), key=lambda v: (v[0], v))
    pushed = {corner: (corner[0] + Q(1, 10 ** 13), corner[1], corner[2])}
    part = replace(p, tris=[tuple(_moved(pushed.get(v, v), by) for v in t) for t in p.tris],
                   holes=[replace(h, at=_moved(h.at, by)) for h in p.holes],
                   cg=None if p.cg is None else _moved(p.cg, by))
    back = tuple(-c for c in by)
    return replace(_swap(d, part), places=[(n, _moved(o, back) if n == p.name else o) for n, o in d.places])


def _stack_wall(d: Design) -> Design:
    """The base cut 0.1 mm inside the thread's crest on one side."""
    f = d.facts
    edge = f["c"][0] + f["d"] / 2 - Q("0.1")
    return _swap(d, replace(_part(d, "base"), tris=_q(plate((0, 0, 0), (edge, f["side"], f["base_h"]), f["c"], num(f["r_b"])))))


def _stack_size(d: Design) -> Design | None:
    """The screw swapped for the next size up, or M4 for M3."""
    f = d.facts
    to = {"M2_5": "M3", "M3": "M4", "M4": "M3"}[f["size"]]
    if (to, f["head"]) not in SCREWS:
        return None
    return replace(d, lines=[line.replace(f"screw.{f['size']}x", f"screw.{to}x") for line in d.lines])


def _grow(d: Design) -> Design:
    """The board grown to 0.2 mm of the walls in x."""
    f = d.facts
    bw = f["w"] - 2 * f["wall"] - Q("0.4")
    board = replace(_part(d, "board"), tris=_q(box((0, 0, 0), (bw, f["bd"], "1.6"))), cg=(bw / 2, f["bd"] / 2, Q("0.8")))
    d = _swap(d, board)
    return replace(d, places=[(n, (f["wall"] + Q("0.2"), o[1], o[2]) if n == "board" else o) for n, o in d.places])


def _loose(d: Design) -> Design:
    """The block's hole opened past the peg."""
    f = d.facts
    tris = plate((0, 0, 0), (f["side"], f["side"], f["thick"]), f["c"], num(f["r_p"] + Q("0.01")))
    return _swap(d, replace(_part(d, "block"), tris=_q(tris)))


def _insert_plant(d: Design, dr: Q = Q(0), edge: Q | None = None, short: bool = False) -> Design:
    p = _part(d, "p")
    tris, top = _insert_mesh(d.facts, d.facts["r"] + dr, edge, short)
    hole = replace(p.holes[0], at=(p.holes[0].at[0], p.holes[0].at[1], Q(top)))
    return _swap(d, replace(p, tris=_q(tris), holes=[hole]))


def _nested(d: Design, outward: bool) -> Design:
    """A void a tenth of the block's least side in from each face, or the same box facing
    out, a second solid inside the first."""
    w, dd, h = d.facts["size"]
    m = min(w, dd, h) / 10
    inner = _q(box((m, m, m), (w - m, dd - m, h - m)))
    p = d.parts[0]
    return _swap(d, replace(p, tris=p.tris + (inner if outward else flipped(inner))))


PLANTS: dict[str, dict[str, Callable[[Design], Design | None]]] = {
    "stack": {"into": lambda d: _into(d, (0, 0, -1)), "thin_wall": _stack_wall, "next_size": _stack_size,
              "push": lambda d: _far(_into(d, (0, 0, -1)))},
    "enclosure": {"into": lambda d: _into(d, (0, 0, -1)), "grow": _grow, "push": lambda d: _far(_into(d, (0, 0, -1)))},
    "press": {"into": lambda d: _into(d, (1, 0, 0)), "loose": _loose, "push": lambda d: _far(_into(d, (1, 0, 0)))},
    "insert": {"thin_wall": lambda d: _insert_plant(d, edge=Q("0.8")),
               "small_hole": lambda d: _insert_plant(d, dr=Q("-0.1")),
               "short": lambda d: _insert_plant(d, short=True),
               "push": lambda d: _far(_insert_plant(d, dr=Q("-0.1")))},
    "solid": {"void": lambda d: _nested(d, False) if d.facts["heavy"] else None,
              "shell": lambda d: _nested(d, True),
              "push": lambda d: _far(_nested(d, False)) if d.facts["heavy"] else None},
}


# --- Running ------------------------------------------------------------------------------------


def _differs(base: dict, new, skip) -> list[str]:
    if isinstance(new, str):
        return [new[:300]]
    keys = sorted(set(base) | set(new))
    return [f"{k}: {base.get(k)} -> {new.get(k)}" for k in keys if _mode(k) not in skip and base.get(k) != new.get(k)]


def _check(design: Design, places: int = 0):
    """The design's outcomes, with the layer's memos emptied after, since a worker checks
    thousands of designs and each memo holds its meshes."""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            return outcomes(render(design, tmp, places), tmp)
    finally:
        for memo in (engine._BORES, engine._LAYOUTS, engine._SURFACES, lower._PART_MEMO, lower._SURFACE, mesh._PARSED):
            memo.clear()


def assess(seed: int, index: int, relations=None, plants=None) -> dict:
    """One generated design, its relations and its plants."""
    rng = random.Random(seed * 1_000_003 + index)
    family = sorted(FAMILIES)[index % len(FAMILIES)]
    design = FAMILIES[family](rng)
    row = {"index": index, "family": family, "relations": {}, "broken": {}, "refused": [], "plants": {}, "passed": []}
    base = _check(design)
    if isinstance(base, str):
        row.update(base="error", error=base[:300])
        return row
    row["base"] = "pass" if passes(base) else "held"
    if row["base"] == "held":
        row["held"] = _held(base)
    for name in RELATIONS if relations is None else relations:
        made = RELATIONS[name](design, rng)
        if made is None:
            continue
        variant, places, skip = made
        got = _check(variant, places)
        if name == "far_frame" and isinstance(got, str) and "past the 2^60" in got:
            row["refused"].append(name)     # a refusal at the scale limit is allowed, and counted
            continue
        diff = _differs(base, got, skip)
        row["relations"][name] = not diff
        if diff:
            row["broken"][name] = diff
    if row["base"] == "held":
        return row
    for name, plant in PLANTS[family].items():
        mutant = None if plants is not None and name not in plants else plant(design)
        if mutant is None:
            continue
        got = _check(mutant)
        row["plants"][name] = "input error" if isinstance(got, str) else (_held(got) or "PASS")
        if passes(got):
            row["passed"].append(name)
    return row


def _job(job):
    seed, index = job
    try:
        return assess(seed, index)
    except Exception as e:  # noqa: BLE001 - a crash is a finding, reported with its design
        return {"index": index, "family": sorted(FAMILIES)[index % len(FAMILIES)], "base": "crash", "error": repr(e)[:300],
                "relations": {}, "broken": {}, "refused": [], "plants": {}, "passed": []}


def summarise(rows: list[dict]) -> dict:
    runs = Counter(name for r in rows for name in r["relations"])
    broken = Counter(name for r in rows for name in r["broken"])
    planted = Counter(name for r in rows for name in r["plants"])
    passed = Counter(name for r in rows for name in r["passed"])
    caught = Counter(_mode(k) if "/" in k else k for r in rows for v in r["plants"].values() if v != "PASS"
                     for k in ([v] if isinstance(v, str) else v))
    return {"designs": len(rows),
            "bases": dict(sorted(Counter(f"{r['family']} {r['base']}" for r in rows).items())),
            "held_by": dict(Counter(_mode(k) for r in rows for k in r.get("held", ())).most_common()),
            "relations": {k: f"{runs[k] - broken[k]} of {runs[k]} held" for k in sorted(runs)},
            "refused_at_the_limit": dict(Counter(name for r in rows for name in r["refused"])),
            "plants": {k: f"{planted[k] - passed[k]} of {planted[k]} caught" for k in sorted(planted)},
            "caught_by": dict(caught.most_common()),
            "broken": sum(broken.values()), "passed": sum(passed.values()),
            "crashes": sum(1 for r in rows if r["base"] == "crash"), "errors": sum(1 for r in rows if r["base"] == "error")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="the parts layer's adversarial gate")
    parser.add_argument("--n", type=int, default=300)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--log", type=Path, default=None, help="write every row with a finding as JSON lines")
    args = parser.parse_args(argv)
    start = time.time()
    rows = []
    with Pool(args.workers) as pool:
        for done, row in enumerate(pool.imap_unordered(_job, [(args.seed, i) for i in range(args.n)]), 1):
            rows.append(row)
            if done % 10 == 0:
                print(f"{done} designs, {time.time() - start:.0f} s", flush=True)
    rows.sort(key=lambda r: r["index"])
    summary = summarise(rows)
    summary["seconds"] = round(time.time() - start)
    print(json.dumps(summary, indent=1))
    if args.log is not None:
        found = [r for r in rows if r["broken"] or r["passed"] or r["base"] != "pass"]
        args.log.write_text("".join(json.dumps(r, default=str) + "\n" for r in found), encoding="utf-8")
    return 1 if summary["broken"] or summary["passed"] or summary["crashes"] or summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
