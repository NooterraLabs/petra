"""The board reader against KiCad itself: `python scripts/kicad_oracle.py ORACLE_DIR [--out DIR]
[--workers 4] [--board SUBSTRING ...]`.

ORACLE_DIR holds one folder per repository and in it one folder per board, each with the
board as `board.kicad_pcb` and what KiCad made of it: `k10.json` (and `k7.json` for KiCad 6
and 7 files), KiCad's own pcbnew reading in integer nanometres, written by
`scripts/kicad_oracle_dump.py` inside KiCad's Python; `drill/*.drl`, Excellon from
`kicad-cli pcb export drill`; `gerber/*.gbr`, Gerber X2 with pad attributes from
`kicad-cli pcb export gerbers`; `pos.csv` from `kicad-cli pcb export pos`; and optionally
`committed/`, drill files the board's own repository ships.

For every board Petra reads, each footprint's side, anchor and angle, each pad's place,
angle, drill, offset and copper, each via, and the thickness are compared with KiCad's
reading. Each drilled hole is matched to an Excellon hit or slot and each pad's copper to a
Gerber flash. Points sampled on the true outline (KiCad's Edge.Cuts shapes, the same with
each board-level arc on the circle through its written points, and the Edge.Cuts Gerber)
and on the true courtyards must lie between the reader's inner and outer polygons, and
within the stated deviation of both. Writes kicad_oracle_log.jsonl to DIR, ORACLE_DIR by
default, and prints a table of checks. Untrusted tooling.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from fractions import Fraction
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from petra.models.boards import plane  # noqa: E402
from petra.models.boards.kicad import Courtyard, PadKind, Side, read_board  # noqa: E402
from petra.models.boards.sexpr import BoardError  # noqa: E402

NM = Fraction(1, 10 ** 6)
KICAD_ROUND = Fraction(1, 10 ** 6)
"""KiCad holds lengths as integer nanometres, so its reading of a turned point is off by up to
half a nanometre on each axis. One nanometre covers it."""


def nm(v) -> Fraction:
    return Fraction(int(v)) * NM


def pt(v) -> tuple[Fraction, Fraction]:
    return nm(v[0]), nm(v[1])


def dist(a, b) -> float:
    return math.hypot(float(a[0] - b[0]), float(a[1] - b[1]))


def angle_diff(a, b) -> float:
    d = (float(a) - float(b)) % 360.0
    return min(d, 360.0 - d)


class Log:
    def __init__(self, board: str):
        self.board = board
        self.rows: list[dict] = []
        self.compared: Counter = Counter()
        self.worst: dict[str, float] = defaultdict(float)

    def check(self, check: str, item: str, ok: bool, reader, kicad, error: float | None = None, note: str = ""):
        self.compared[check] += 1
        if error is not None:
            self.worst[check] = max(self.worst[check], error)
        if not ok:
            self.rows.append({"board": self.board, "check": check, "item": item, "reader": str(reader),
                              "kicad": str(kicad), "error_mm": error, "note": note})


def pad_kind_expected(attr_names, plated_file: bool) -> set:
    a = attr_names[0] if attr_names else ""
    return {"PAD_ATTRIB_PTH": {PadKind.THROUGH_HOLE, PadKind.MOUNTING_HOLE},
            "PAD_ATTRIB_SMD": {PadKind.SMD}, "PAD_ATTRIB_CONN": {PadKind.CONNECT},
            "PAD_ATTRIB_NPTH": {PadKind.NPTH, PadKind.MOUNTING_HOLE}}.get(a, set())


def compare_footprints(log: Log, board, k: dict, tag: str):
    kf = k["footprints"]
    if len(kf) != len(board.footprints):
        log.check(f"{tag} footprint count", "board", False, len(board.footprints), len(kf))
        return
    for f, g in zip(board.footprints, kf):
        name = f"{f.reference}"
        if f.reference != g["ref"]:
            log.check(f"{tag} footprint order", name, False, f.reference, g["ref"])
            continue
        side = "F.Cu" if f.side is Side.TOP else "B.Cu"
        log.check(f"{tag} footprint side", name, (f.side is Side.BOTTOM) == g["flipped"],
                  side, f"{g['layer']} flipped={g['flipped']}")
        e = dist(f.placement.at, pt(g["at"]))
        log.check(f"{tag} footprint anchor", name, e <= float(KICAD_ROUND), plane.show(f.placement.at),
                  plane.show(pt(g["at"])), e)
        d = angle_diff(f.placement.angle, g["angle"])
        log.check(f"{tag} footprint angle", name, d < 1e-9, float(f.placement.angle), g["angle"], None)
        if len(f.pads) != len(g["pads"]):
            log.check(f"{tag} pad count", name, False, len(f.pads), len(g["pads"]))
            continue
        for p, q in zip(f.pads, g["pads"]):
            item = f"{f.reference}.{p.number} ({'bottom' if f.side is Side.BOTTOM else 'top'}, fp {float(f.placement.angle):g} deg)"
            if p.number != q["number"]:
                log.check(f"{tag} pad order", item, False, p.number, q["number"])
                continue
            log.check(f"{tag} pad kind", item, p.kind in pad_kind_expected(q["attr_names"], p.plated),
                      p.kind.value, q["attr_names"])
            e = dist(p.at.point, pt(q["at"]))
            log.check(f"{tag} pad place (hole centre)", item, e <= float(p.at.error + KICAD_ROUND),
                      plane.show(p.at.point), plane.show(pt(q["at"])), e)
            d = angle_diff(p.angle, q["angle"])
            log.check(f"{tag} pad angle (absolute)", item, d < 1e-6, float(p.angle), q["angle"],
                      note=f"KiCad relative angle {q.get('fp_rel_angle')}")
            if p.drill:
                oval = "PAD_DRILL_SHAPE_OBLONG" in q["drill_shape_names"]
                ok = (nm(q["drill"][0]) == p.drill.width and nm(q["drill"][1]) == p.drill.height
                      and (oval == p.drill.oval or p.drill.width == p.drill.height))
                log.check(f"{tag} pad drill", item, ok, (float(p.drill.width), float(p.drill.height), p.drill.oval),
                          (q["drill"], q["drill_shape_names"]),
                          max(abs(float(nm(q["drill"][0]) - p.drill.width)), abs(float(nm(q["drill"][1]) - p.drill.height))))
            elif q["drill"][0] and p.kind not in (PadKind.SMD, PadKind.CONNECT):
                log.check(f"{tag} pad drill", item, False, None, q["drill"])
            log.check(f"{tag} pad offset", item, pt(q["offset"]) == p.offset, plane.show(p.offset), plane.show(pt(q["offset"])),
                      dist(p.offset, pt(q["offset"])))
            copper = plane.place(p.offset, p.at.point, p.angle)
            e = dist(copper.point, pt(q["shape_pos"]))
            log.check(f"{tag} pad copper", item, e <= float(copper.error + p.at.error + 2 * KICAD_ROUND),
                      plane.show(copper.point), plane.show(pt(q["shape_pos"])), e)


def compare_vias(log: Log, board, k: dict, tag: str):
    kv = k["vias"]
    if len(kv) != len(board.vias):
        log.check(f"{tag} via count", "board", False, len(board.vias), len(kv))
        return
    for v, w in zip(board.vias, kv):
        through = w["type_names"] and any("THROUGH" in n for n in w["type_names"])
        ok = v.at == pt(w["at"]) and v.drill == nm(w["drill"]) and v.through == bool(through)
        log.check(f"{tag} via", plane.show(v.at), ok, (plane.show(v.at), float(v.drill), v.through),
                  (plane.show(pt(w["at"])), w["drill"], w["type_names"]), dist(v.at, pt(w["at"])))


def arc_samples(center, radius, a0, sweep, n):
    return [(center[0] + radius * math.cos(a0 + sweep * i / n), center[1] + radius * math.sin(a0 + sweep * i / n))
            for i in range(n + 1)]


def shape_samples(s: dict) -> list[tuple[float, float]]:
    """Points on a KiCad shape's centre line, in mm, from KiCad's own reading."""
    f = lambda v: (v[0] * 1e-6, v[1] * 1e-6)
    kind = s["kind"]
    if kind in ("Line", "Segment"):
        a, b = f(s["start"]), f(s["end"])
        return [(a[0] + (b[0] - a[0]) * i / 16, a[1] + (b[1] - a[1]) * i / 16) for i in range(17)]
    if kind in ("Rect", "Rectangle"):
        corners = [f(c) for c in s.get("corners") or []]
        if not corners:
            (x0, y0), (x1, y1) = f(s["start"]), f(s["end"])
            corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        out = []
        for a, b in zip(corners, corners[1:] + corners[:1]):
            out += [(a[0] + (b[0] - a[0]) * i / 16, a[1] + (b[1] - a[1]) * i / 16) for i in range(16)]
        return out
    if kind == "Circle":
        c, r = f(s["center"]), s["radius"] * 1e-6
        return arc_samples(c, r, 0.0, 2 * math.pi, 256)
    if kind == "Arc":
        c, r = f(s["center"]), s["radius"] * 1e-6
        a0 = math.atan2(f(s["start"])[1] - c[1], f(s["start"])[0] - c[0])
        am = math.atan2(f(s["mid"])[1] - c[1], f(s["mid"])[0] - c[0])
        a1 = math.atan2(f(s["end"])[1] - c[1], f(s["end"])[0] - c[0])
        ccw = (a1 - a0) % (2 * math.pi)
        sweep = ccw if (am - a0) % (2 * math.pi) <= ccw else ccw - 2 * math.pi
        return arc_samples(c, r, a0, sweep, 256)
    if kind in ("Polygon", "Poly"):
        out = []
        for o in s["poly"]:
            arcs = [a for a in o.get("arcs", []) if "error" not in a]
            circles = [(f(a["center"]), a["radius"] * 1e-6) for a in arcs]

            def on_arc(p):
                return any(abs(math.dist(p, c) - r) < 1e-3 for c, r in circles)

            pts = [f(p) for p in o["outline"]]
            for a, b in zip(pts, pts[1:] + pts[:1]):
                # KiCad keeps an arc in a polygon as points up to 0.5 um off the circle, and
                # chords between them: neither is the edge. The arc is sampled below.
                if on_arc(a) and on_arc(b):
                    continue
                out += [(a[0] + (b[0] - a[0]) * i / 8, a[1] + (b[1] - a[1]) * i / 8) for i in range(8)]
            for a in arcs:
                out += shape_samples({"kind": "Arc", **a})
        return out
    return []


def poly_measure(x: np.ndarray, poly) -> tuple[np.ndarray, np.ndarray]:
    """For points x (m, 2): the distance to the polygon's boundary and whether each lies
    inside it, in floats. A point nearer the boundary than float error decides nothing here:
    its distance is then far below any slack reported."""
    p = np.array([(float(a), float(b)) for a, b in poly])
    a, b = np.roll(p, 1, axis=0), p
    d = b - a
    dd = np.maximum((d * d).sum(axis=1), 1e-300)
    rel = x[:, None, :] - a[None, :, :]
    t = np.clip((rel * d[None]).sum(axis=2) / dd[None], 0.0, 1.0)
    proj = a[None] + t[..., None] * d[None]
    dist = np.sqrt(((x[:, None, :] - proj) ** 2).sum(axis=2)).min(axis=1)
    ay, by = a[None, :, 1], b[None, :, 1]
    y = x[:, 1:2]
    cond = (ay > y) != (by > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        xint = a[None, :, 0] + (y - ay) * (b[None, :, 0] - a[None, :, 0]) / (by - ay)
    inside = (cond & (x[:, 0:1] < xint)).sum(axis=1) % 2 == 1
    return dist, inside


def bracket(log: Log, check: str, item: str, bounds_list, samples, slack: float):
    """Each true point lies in the closed outer polygon and outside the open inner polygon of
    one of the loops, and within each loop's deviation of both polygons' boundaries."""
    worst_out, worst_dev, first_bad, first_dev = 0.0, 0.0, None, None
    pts = np.array(samples, dtype=float)
    for lo in range(0, len(pts), 1000):
        x = pts[lo:lo + 1000]
        outs, devs = [], []
        for b in bounds_list:
            d_out, in_out = poly_measure(x, b.outer)
            d_in, in_in = poly_measure(x, b.inner)
            outs.append(np.maximum(np.where(in_out, 0.0, d_out), np.where(in_in, d_in, 0.0)))
            devs.append(np.maximum(d_in, d_out) - float(b.deviation))
        outs, devs = np.array(outs), np.array(devs)
        best = np.lexsort((devs, outs), axis=0)[0] if len(bounds_list) > 1 else np.zeros(len(x), dtype=int)
        out = outs[best, np.arange(len(x))]
        dev = devs[best, np.arange(len(x))]
        i, j = int(out.argmax()), int(dev.argmax())
        if out[i] > worst_out:
            worst_out, first_bad = float(out[i]), tuple(x[i])
        if dev[j] > worst_dev:
            worst_dev, first_dev = float(dev[j]), tuple(x[j])
    log.check(check + " bracketed", item, worst_out <= slack, "inner/outer polygons",
              f"true point ({first_bad[0]:.6f}, {first_bad[1]:.6f}) outside by {worst_out:.3g} mm" if first_bad else "",
              worst_out)
    log.check(check + " within deviation", item, worst_dev <= slack, "deviation",
              f"true point ({first_dev[0]:.6f}, {first_dev[1]:.6f}) strays {worst_dev:.3g} mm past it" if first_dev else "",
              worst_dev)


_GR_ARC = re.compile(r"\(gr_arc\s*\(start ([-\d.]+) ([-\d.]+)\)\s*\(mid ([-\d.]+) ([-\d.]+)\)\s*\(end ([-\d.]+) ([-\d.]+)\)"
                     r"[\s\S]*?\(layer \"?Edge\.Cuts\"?\)")


def written_arc_samples(a, m, e):
    """Points on the exact circle through an arc's written start, mid and end."""
    (ax, ay), (bx, by), (cx, cy) = a, m, e
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    c = (float(ux), float(uy))
    a0, am, a1 = (math.atan2(float(p[1]) - c[1], float(p[0]) - c[0]) for p in (a, m, e))
    ccw = (a1 - a0) % (2 * math.pi)
    sweep = ccw if (am - a0) % (2 * math.pi) <= ccw else ccw - 2 * math.pi
    return arc_samples(c, math.dist(c, (float(ax), float(ay))), a0, sweep, 256)


def finest_bounds(lp):
    for t in (plane.TOLERANCE, plane.TOLERANCE / 10, plane.TOLERANCE / 100):
        try:
            return plane.bounds(lp, t)
        except plane.ShapeError as err:
            last = err
    raise last


def compare_outline(log: Log, board, k: dict, gerber_edge: list, text: str):
    """KiCad draws an arc about a centre it computes and rounds, up to 0.063 um from the exact
    one, so its arc and its Gerber can stray from the circle through the written points by
    tens of nanometres. The reader bounds
    the written circle. The third check swaps each board-level arc for its written circle,
    which tells KiCad's rounding apart from a reader error."""
    loops = [board.outline.boundary, *board.outline.cutouts]
    bounds = [finest_bounds(lp) for lp in loops]
    kicad_loops = sum(1 + len(o["holes"]) for o in k["outline"])
    log.check("outline loop count", "board", kicad_loops == len(loops), len(loops), kicad_loops)
    shapes = [s for s in k["edge_shapes"]] + [g for f in k["footprints"] for g in f["graphics"] if g["layer"] == "Edge.Cuts"]
    pts = [p for s in shapes for p in shape_samples(s)]
    bracket(log, "outline (KiCad Edge.Cuts shapes)", "board", bounds, pts, 2e-6)
    if gerber_edge:
        bracket(log, "outline (Edge.Cuts Gerber)", "board", bounds, gerber_edge, 2e-6)
    arcs = {}
    for m in _GR_ARC.finditer(text):
        n = [Fraction(v) for v in m.groups()]
        arcs[(n[0], n[1], n[4], n[5])] = ((n[0], n[1]), (n[2], n[3]), (n[4], n[5]))
    pts = []
    for s in shapes:
        if s["kind"] == "Arc":
            a, e = pt(s["start"]), pt(s["end"])
            arc = arcs.get((*a, *e)) or arcs.get((*e, *a))
            if arc:
                pts += written_arc_samples(*arc)
                continue
        pts += shape_samples(s)
    bracket(log, "outline (KiCad shapes, written arcs)", "board", bounds, pts, 2e-6)


def compare_courtyards(log: Log, board, k: dict):
    for f, g in zip(board.footprints, k["footprints"]):
        if f.reference != g["ref"]:
            continue
        for face, key, layer in ((Side.TOP, "F", "F.CrtYd"), (Side.BOTTOM, "B", "B.CrtYd")):
            yard = f.courtyard(face)
            kc = g["courtyard"].get(key)
            k_has = isinstance(kc, list) and len(kc) > 0
            item = f"{f.reference} {face.value} ({'bottom' if f.side is Side.BOTTOM else 'top'} part, {float(f.placement.angle):g} deg)"
            if not isinstance(yard, Courtyard):
                log.check("courtyard read", item, not k_has, f"NoCourtyard: {yard.reason}", "KiCad has one" if k_has else "none")
                continue
            log.check("courtyard read", item, k_has, "Courtyard", "KiCad has none")
            shapes = [s for s in g["graphics"] if s["layer"] == layer]
            pts = [p for s in shapes for p in shape_samples(s)]
            if pts:
                bracket(log, "courtyard", item, yard.board, pts, 2e-6)


_EXC_TOOL = re.compile(r"^T(\d+)C([\d.]+)")
_EXC_HIT = re.compile(r"^(?:T(\d+))?X(-?[\d.]+)Y(-?[\d.]+)(?:G85X(-?[\d.]+)Y(-?[\d.]+))?$")


def read_excellon(path: Path) -> tuple[list[dict], Fraction]:
    """The hits of a decimal-format Excellon file in mm, KiCad's frame, and half the unit of
    its last written decimal, in mm."""
    tools, hits, tool, places = {}, [], None, 0
    plated = "-NPTH" not in path.name
    text = path.read_text(errors="replace")
    unit = Fraction(254, 10) if re.search(r"^INCH", text, re.M) else Fraction(1)
    for line in text.splitlines():
        line = line.strip()
        m = _EXC_TOOL.match(line)
        if m:
            tools[m.group(1)] = Fraction(m.group(2)) * unit
            continue
        if re.fullmatch(r"T\d+", line):
            tool = line[1:]
            continue
        m = _EXC_HIT.match(line)
        if m:
            if m.group(1):
                tool = m.group(1)
            nums = [g for g in m.groups()[1:] if g is not None]
            places = max([places] + [len(n.split(".")[1]) if "." in n else 0 for n in nums])
            a = (Fraction(m.group(2)) * unit, -Fraction(m.group(3)) * unit)
            b = (Fraction(m.group(4)) * unit, -Fraction(m.group(5)) * unit) if m.group(4) else None
            hits.append({"at": a, "end": b, "d": tools[tool], "plated": plated, "file": path.name,
                         "dtol": Fraction(1, 2000) if unit == 1 else Fraction(254, 200000)})
    return hits, Fraction(1, 10 ** max(places, 3)) / 2 * unit


def compare_drills(log: Log, board, files: list[Path], prefix: str = ""):
    hits, grid = [], Fraction(0)
    for p in files:
        h, g = read_excellon(p)
        hits += h
        grid = max(grid, g)
    if not hits and not any(p.drill for f in board.footprints for p in f.pads) and not board.vias:
        return
    index = defaultdict(list)
    for i, h in enumerate(hits):
        c = h["at"] if h["end"] is None else ((h["at"][0] + h["end"][0]) / 2, (h["at"][1] + h["end"][1]) / 2)
        index[(round(float(c[0]), 2), round(float(c[1]), 2))].append(i)
    used = set()

    def near(c):
        key = (round(float(c[0]), 2), round(float(c[1]), 2))
        found = []
        for dx in (-0.01, 0, 0.01):
            for dy in (-0.01, 0, 0.01):
                found += index.get((round(key[0] + dx, 2), round(key[1] + dy, 2)), [])
        return found

    for f in board.footprints:
        for p in f.pads:
            if not p.drill:
                continue
            item = f"{f.reference}.{p.number} ({'bottom' if f.side is Side.BOTTOM else 'top'}, pad {float(p.angle):g} deg)"
            slot = p.drill.width != p.drill.height
            if slot:
                radius = min(p.drill.width, p.drill.height) / 2
                half = max(p.drill.width, p.drill.height) / 2 - radius
                axis = (half, Fraction(0)) if p.drill.width > p.drill.height else (Fraction(0), half)
                ends = [plane.place(axis, p.at.point, p.angle), plane.place((-axis[0], -axis[1]), p.at.point, p.angle)]
            best = None
            for i in near(p.at.point):
                h = hits[i]
                c = h["at"] if h["end"] is None else ((h["at"][0] + h["end"][0]) / 2, (h["at"][1] + h["end"][1]) / 2)
                e = dist(c, p.at.point)
                # Two pads may share a place (reversible footprints): each takes its own hit.
                if best is None or (i in used, e) < (best[1] in used, best[0]):
                    best = (e, i)
            if best is None:
                log.check(prefix + "hole in Excellon", item, False, plane.show(p.at.point), "no hit within 0.02 mm")
                continue
            e, i = best
            used.add(i)
            h = hits[i]
            tol = float(p.at.error + 2 * grid)
            log.check(prefix + "hole place vs Excellon", item, e <= tol, plane.show(p.at.point), plane.show(h["at"]), e)
            want = min(p.drill.width, p.drill.height)
            log.check(prefix + "hole size vs Excellon", item, abs(h["d"] - want) <= h["dtol"], float(want), float(h["d"]),
                      abs(float(h["d"] - want)), note="tool sizes are rounded to the file's decimals")
            if slot:
                if h["end"] is None:
                    log.check(prefix + "slot vs Excellon", item, False, "slot", "round hit")
                else:
                    e2 = min(max(dist(ends[0].point, h["at"]), dist(ends[1].point, h["end"])),
                             max(dist(ends[1].point, h["at"]), dist(ends[0].point, h["end"])))
                    log.check(prefix + "slot vs Excellon", item, e2 <= tol + float(ends[0].error),
                              f"{plane.show(ends[0].point)}-{plane.show(ends[1].point)}",
                              f"{plane.show(h['at'])}-{plane.show(h['end'])}", e2)
            want_plated = p.plated
            log.check(prefix + "hole plating vs Excellon", item, h["plated"] == want_plated, want_plated, h["file"])
    for v in board.vias:
        best = None
        for i in near(v.at):
            e = dist(hits[i]["at"], v.at)
            if best is None or (i in used, e) < (best[1] in used, best[0]):
                best = (e, i)
        if best is None:
            log.check(prefix + "via in Excellon", plane.show(v.at), False, plane.show(v.at), "no hit")
            continue
        used.add(best[1])
        log.check(prefix + "via place vs Excellon", plane.show(v.at), best[0] <= float(2 * grid), plane.show(v.at),
                  plane.show(hits[best[1]]["at"]), best[0])
    extra = [h for i, h in enumerate(hits) if i not in used]
    log.check(prefix + "Excellon holes the reader lacks", "board", not extra, 0,
              f"{len(extra)}: " + ", ".join(f"{plane.show(h['at'])} d{float(h['d']):g}" for h in extra[:6]))


_FMT = re.compile(r"%FSLAX(\d)(\d)Y(\d)(\d)\*%")


def read_gerber(path: Path):
    """Flashes with their X2 pad attribute, and points sampled on every draw."""
    text = path.read_text()
    m = _FMT.search(text)
    dec = int(m.group(2)) if m else 6
    scale = 10 ** dec
    x = y = 0
    mode, aperture_pad, flashes, draws = "G01", None, [], []
    for raw in re.split(r"\*", text.replace("\n", "")):
        tok = raw.strip().lstrip("%")
        if tok.startswith("TO.P,"):
            parts = tok[5:].split(",")
            aperture_pad = (parts[0], parts[1] if len(parts) > 1 else "")
            continue
        if tok.startswith("TD"):
            aperture_pad = None
            continue
        for g in re.findall(r"G0?([123])(?=\D|$)", tok):
            mode = "G0" + g
        mm = re.search(r"X(-?\d+)", tok)
        my = re.search(r"Y(-?\d+)", tok)
        mi = re.search(r"I(-?\d+)", tok)
        mj = re.search(r"J(-?\d+)", tok)
        md = re.search(r"D0?([123])$", tok)
        if not md or tok[:2] in ("AD", "AM", "FS", "MO", "LP", "TA", "TF", "TO"):
            continue
        nx = int(mm.group(1)) / scale if mm else x
        ny = int(my.group(1)) / scale if my else y
        d = md.group(1)
        if d == "3":
            flashes.append(((nx, -ny), aperture_pad))
        elif d == "1":
            if mode == "G01":
                draws += [(x + (nx - x) * i / 16, -(y + (ny - y) * i / 16)) for i in range(17)]
            else:
                ci, cj = (int(mi.group(1)) / scale if mi else 0.0), (int(mj.group(1)) / scale if mj else 0.0)
                cx, cy = x + ci, y + cj
                r = math.hypot(x - cx, y - cy)
                a0, a1 = math.atan2(y - cy, x - cx), math.atan2(ny - cy, nx - cx)
                if mode == "G03":
                    sweep = (a1 - a0) % (2 * math.pi) or 2 * math.pi
                else:
                    sweep = -((a0 - a1) % (2 * math.pi) or 2 * math.pi)
                draws += [(px, -py) for px, py in arc_samples((cx, cy), r, a0, sweep, 128)]
        x, y = nx, ny
    return flashes, draws


def compare_flashes(log: Log, board, gerber_dir: Path):
    pads = defaultdict(list)
    for p in gerber_dir.glob("*.gbr"):
        if not re.search(r"%TF\.FileFunction,Copper,L\d+,(Top|Bot)\*%", p.read_text(errors="replace")[:2000]):
            continue
        flashes, _ = read_gerber(p)
        for at, key in flashes:
            if key:
                pads[key].append(at)
    if not pads:
        return
    for f in board.footprints:
        for p in f.pads:
            if p.kind is PadKind.NPTH or (p.kind is PadKind.MOUNTING_HOLE and not p.plated):
                continue
            got = pads.get((f.reference, p.number))
            if not got:
                continue
            copper = plane.place(p.offset, p.at.point, p.angle)
            c = (float(copper.point[0]), float(copper.point[1]))
            e = min(math.hypot(c[0] - a[0], c[1] - a[1]) for a in got)
            item = f"{f.reference}.{p.number} ({'bottom' if f.side is Side.BOTTOM else 'top'}, pad {float(p.angle):g} deg)"
            log.check("pad copper vs Gerber flash", item, e <= 2e-6 + float(copper.error + p.at.error), plane.show(copper.point),
                      "nearest flash", e)


def compare_pos(log: Log, board, pos: Path) -> None:
    rows = list(csv.DictReader(pos.open()))
    by_ref = defaultdict(list)
    for r in rows:
        by_ref[r["Ref"]].append(r)
    taken = set()
    for f in board.footprints:
        side = "top" if f.side is Side.TOP else "bottom"
        # Reversible footprints come in pairs with one reference at one place, one per side:
        # a row on the footprint's own side is its row, and each row serves one footprint.
        for r in sorted(by_ref.get(f.reference, []), key=lambda r: r["Side"] != side):
            x, y = Fraction(r["PosX"]), -Fraction(r["PosY"])
            e = dist((x, y), f.placement.at)
            if e > 2e-6 or id(r) in taken:
                continue
            taken.add(id(r))
            log.check("pos side", f.reference, r["Side"] == side, side, r["Side"])
            break
        else:
            if by_ref.get(f.reference):
                log.check("pos place", f.reference, False, plane.show(f.placement.at), [(r["PosX"], r["PosY"]) for r in by_ref[f.reference]])


def run_board(folder: str) -> dict:
    folder = Path(folder)
    name = f"{folder.parent.name}/{folder.name}"
    log = Log(name)
    started = time.time()
    text = (folder / "board.kicad_pcb").read_text(encoding="utf-8", errors="replace")
    m = re.search(r"\(version (\d+)\)", text)
    summary = {"board": name, "version": int(m.group(1)) if m else None}
    try:
        board = read_board(folder / "board.kicad_pcb")
    except BoardError as err:
        summary["refused"] = str(err).replace(str(folder / "board.kicad_pcb"), "board.kicad_pcb")
        summary["seconds"] = round(time.time() - started, 1)
        return {"summary": summary, "rows": [], "compared": {}, "worst": {}}
    except Exception as err:
        summary["crashed"] = f"{type(err).__name__}: {err}"
        return {"summary": summary, "rows": [], "compared": {}, "worst": {}}
    summary.update(footprints=len(board.footprints), pads=sum(len(f.pads) for f in board.footprints), vias=len(board.vias),
                   cutouts=len(board.outline.cutouts), thickness=str(board.thickness.value) if board.thickness else None,
                   bottom=sum(f.side is Side.BOTTOM for f in board.footprints),
                   odd_angles=sum(1 for f in board.footprints if f.placement.angle % 90),
                   bottom_odd_angles=sum(1 for f in board.footprints if f.placement.angle % 90 and f.side is Side.BOTTOM),
                   ovals=sum(1 for f in board.footprints for p in f.pads if p.drill and p.drill.width != p.drill.height),
                   offsets=sum(1 for f in board.footprints for p in f.pads if p.offset != (0, 0)),
                   arcs=sum(1 for lp in [board.outline.boundary, *board.outline.cutouts] for i in lp.items
                            if not isinstance(i, plane.Segment)))
    for tag, fname in (("k10", "k10.json"), ("k7", "k7.json")):
        path = folder / fname
        if not path.exists():
            continue
        k = json.loads(path.read_text())
        compare_footprints(log, board, k, tag)
        compare_vias(log, board, k, tag)
        if board.thickness is not None:
            log.check(f"{tag} thickness", "board", board.thickness.value == nm(k["thickness"]),
                      f"{board.thickness.value} ({board.thickness.source})", nm(k["thickness"]),
                      abs(float(board.thickness.value - nm(k["thickness"]))))
        if tag == "k10":
            gerber_edge = []
            for p in (folder / "gerber").glob("*Edge_Cuts*.gbr"):
                gerber_edge += read_gerber(p)[1]
            try:
                compare_outline(log, board, k, gerber_edge, text)
            except Exception as err:
                log.check("outline compare crashed", "board", False, "", f"{type(err).__name__}: {err}")
            compare_courtyards(log, board, k)
    if (folder / "drill").exists():
        compare_drills(log, board, sorted((folder / "drill").glob("*.drl")))
    committed = folder / "committed"
    if committed.exists():
        groups = defaultdict(list)
        for p in committed.iterdir():
            groups[p.name.rsplit("__", 1)[0]].append(p)
        trials = []
        for group, files in sorted(groups.items()):
            trial = Log(name)
            compare_drills(trial, board, sorted(files), "committed ")
            trials.append((sum(trial.compared.values()) - len(trial.rows), group, trial))
        if trials:
            _, group, best = max(trials, key=lambda t: t[0])
            for row in best.rows:
                row["note"] = (row["note"] + f" committed files {group}").strip()
            log.rows += best.rows
            log.compared.update(best.compared)
            for k, v in best.worst.items():
                log.worst[k] = max(log.worst[k], v)
            summary["committed"] = group
    if (folder / "gerber").exists():
        compare_flashes(log, board, folder / "gerber")
    if (folder / "pos.csv").exists():
        compare_pos(log, board, folder / "pos.csv")
    summary["seconds"] = round(time.time() - started, 1)
    return {"summary": summary, "rows": log.rows, "compared": dict(log.compared), "worst": dict(log.worst)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("oracle")
    ap.add_argument("--out", default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--board", nargs="*", default=[])
    args = ap.parse_args(argv)
    folders = sorted(p.parent.as_posix() for p in Path(args.oracle).glob("*/*/board.kicad_pcb"))
    if args.board:
        folders = [f for f in folders if any(s in f for s in args.board)]
    with Pool(args.workers) as pool:
        results = pool.map(run_board, folders, chunksize=1)
    out = Path(args.out) if args.out else Path(args.oracle)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "kicad_oracle_log.jsonl").open("w") as fh:
        for r in results:
            fh.write(json.dumps({"summary": r["summary"], "compared": r["compared"], "worst": r["worst"]}) + "\n")
            for row in r["rows"]:
                fh.write(json.dumps(row) + "\n")
    compared, bad, worst = Counter(), Counter(), defaultdict(float)
    for r in results:
        compared.update(r["compared"])
        for row in r["rows"]:
            bad[row["check"]] += 1
        for k, v in r["worst"].items():
            worst[k] = max(worst[k], v)
    for r in results:
        s = r["summary"]
        print(json.dumps(s))
    print()
    for check in sorted(compared):
        print(f"{check:55s} compared {compared[check]:7d}  disagree {bad[check]:6d}  worst {worst.get(check, 0):.3g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
