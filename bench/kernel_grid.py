"""The grid against the kernel, on generated designs.

    python bench/kernel_grid.py [--count N] [--decks N] [--seed S] [--jobs J] [--keep DIR]

petra/grid.py and petra-verify each work out the cells of a design checked against a deck
of rules. This makes N designs, has both check each one, and counts the designs they
differ on. A difference is a bug in one of the two.

A design is of one of three decks: the deck that ships, with its `lap` and `plate`,
STRIPS, the deck made up for tests/test_grid.py, or OPS, made up here so that every
operator of the rule language is in a rule: powers, roots, exp and ln, conditions joined
by and, or and not, a table with bands closed at the lower end, every way to bind a key,
a key of a joined part, and a range that reads a load. A design's numbers are drawn from
the ends of the decks' bands, their listed
values and the edges of their cases and ranges, and from near them. Its loads are
points or ranges, in no, one or two load cases, and its card waives some mechanisms or none.
About two designs in five of the first two decks are then damaged in a way the grid
refuses: a missing or unknown line, a wrong unit, a strength the design writes, a given
of another part, a load the type does not take, and so on. Of the others, one in forty
has a load case with a `/` in its name, which both refuse, and one in forty a card whose
name is 200 bytes, the most both take for a design with parts, or 201.

For each design that the language reads, the files are written without asking the grid
(grid.bundle with no answers), so the kernel sees a refused design too. Then:

    the grid refuses it     the kernel must find it ILL-FORMED
    the grid checks it      the kernel must list the same cells in the same order, each with
                            the same subject, mechanism, entry and state, give the same
                            verdict, and print the hash of the deck's file

`--decks N` also makes N damaged decks. Each is one of the three decks with one or two
changes: a text swapped for another text of the deck or for an odd one, a key or an item
dropped, doubled, moved or renamed, a `where` with no item, two rules of one line whose
ids end alike, a line named `unread`, or a wide row that a rule applies 9 times or 1,000
times, which is within the steps a deck may take to read or over them. An honest design
of that deck is then checked against it. The grid's `read_deck` must refuse exactly the decks the kernel finds ill formed, and
where both read the deck they must agree on the design as above.

Exits 0 when no case differs, and 1 otherwise. `--keep DIR` writes the texts and the files
of each case that differs.
"""
from __future__ import annotations

import argparse
import tempfile
import subprocess
import collections
import copy
import dataclasses
import json
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from petra import grid, verify  # noqa: E402
from petra.lang import parse_design  # noqa: E402
from petra.models.base import ComponentError  # noqa: E402
from petra.repair import INPUT_ERRORS  # noqa: E402

SIGNED = 'signed "t@example.org" source "generated"'
MADE_UP = {"standard": "a deck made up for the bench", "clause": "1"}


def _takes(*names: str) -> list[dict]:
    return [{"name": name, "dim": "length" if name in "abx" else "dimensionless", "what": name,
             "range": ["1 mm", "100 mm"] if name in "abx" else ["0.1", "10"]} for name in names]


OPS = {
    "format": "petra-rules/0", "name": "bench-ops", "about": "Made up for bench/kernel_grid.py. It is no standard, and its numbers mean nothing.",
    "rows": [
        {"id": "ops/cases", "anchor": MADE_UP, "gives": {"name": "y", "dim": "dimensionless", "what": "three cases"}, "takes": _takes("a", "b"),
         "cases": [{"when": ["and", ["ge", "a", "b"], ["not", ["lt", "a", ["q", "10", "mm"]]]], "is": ["pow", ["div", "a", "b"], "2"]},
                   {"when": ["or", ["lt", "a", "b"], ["le", "a", ["q", "5", "mm"]]], "is": ["pow", ["div", "a", "b"], "-1"]},
                   {"is": ["div", ["abs", ["sub", "a", "b"]], ["max", "a", "b", ["q", "1", "mm"]]]}]},
        {"id": "ops/roots", "anchor": MADE_UP, "gives": {"name": "y", "dim": "length", "what": "roots and half powers"}, "takes": _takes("a", "b"),
         "is": ["add", ["sqrt", ["mul", "a", "b"]], ["pow", ["mul", "a", "b"], "1/2"], ["mul", ["pow", ["div", "a", "b"], "3/2"], "b"], ["neg", ["min", "a", "b"]]]},
        {"id": "ops/exp", "anchor": MADE_UP, "gives": {"name": "y", "dim": "dimensionless", "what": "exp, ln and the powers that need them"}, "takes": _takes("r", "s"),
         "is": ["add", ["pow", "r", "0.3"], ["pow", "r", "s"], ["exp", ["neg", "r"]], ["ln", ["add", "r", "1"]], ["pow", "pi", "0"], ["pow", "r", "-3/2"]]},
        {"id": "ops/table", "anchor": MADE_UP, "gives": {"name": "F", "dim": "force", "what": "a table with bands closed at the lower end"},
         "takes": [*_takes("x"), {"name": "grade", "one_of": ["low", "mid", "high"], "what": "a key"}],
         "table": {"down": {"by": "x", "bands": [["0 mm", "10 mm"], ["10 mm", "20 mm"], ["20 mm", None]], "closed": "lower"}, "across": {"by": "grade"},
                   "unit": "kN", "cells": [["1", "2", None], ["3", "4", "5"], ["6000 N", "7", "8"]]}},
    ],
    "types": [
        {"type": "cap", "what": "an end of a bar", "fields": [
            {"name": "t", "dim": "length", "what": "its thickness"}, {"name": "finish", "one_of": ["low", "high"], "what": "a key whose names are the table's"}]},
        {"type": "bar", "what": "a bar", "fields": [
            {"name": "a", "dim": "length", "what": "a length"}, {"name": "b", "dim": "length", "what": "another"},
            {"name": "r", "dim": "dimensionless", "signed": True, "what": "a ratio the card states"}, {"name": "s", "dim": "dimensionless", "what": "an exponent"},
            {"name": "grade", "one_of": ["soft", "hard"], "what": "a key"}, {"name": "caps", "type": "cap", "as": ["left", "right"], "what": "its two ends"}],
         "loads": [{"name": "push", "dim": "force", "what": "a force of either sign"}, {"name": "twist", "dim": "moment", "least": "0 Nm", "what": "a moment"}]}],
    "grid": [{"type": "bar", "mechanism": f"bar.{name}", "what": name, "anchor": MADE_UP, **more} for name, more in (
        ("cases", {}), ("roots", {}), ("exp", {}), ("table", {}), ("key", {}), ("moment", {}), ("caps", {}),
        ("idle", {"unless": {"when": ["or", ["not", ["loaded", "push"]], ["and", ["is", "grade", "hard"], ["loaded", "twist"]]], "why": "made up"}}))],
    "rules": [
        {"id": "ops/cases", "type": "bar", "mechanism": "bar.cases", "anchor": MADE_UP, "says": "made up",
         "le": [["row", "ops/cases", {"a": "a", "b": "b"}], "1.5"]},
        {"id": "ops/roots", "type": "bar", "mechanism": "bar.roots", "anchor": MADE_UP, "says": "made up", "let": {"both": ["row", "ops/roots", {"a": "a", "b": "b"}]},
         "le": ["both", ["mul", "2.5", "b"]]},
        {"id": "ops/exp", "type": "bar", "mechanism": "bar.exp", "anchor": MADE_UP, "says": "made up", "where": [{"le": ["s", "4"], "why": "made up"}],
         "le": [["row", "ops/exp", {"r": "r", "s": "s"}], "5.2"]},
        {"id": "ops/table", "type": "bar", "mechanism": "bar.table", "anchor": MADE_UP, "says": "made up",
         "when": ["or", ["is", "grade", "soft"], ["not", ["loaded", "twist"]]],
         "le": [["abs", ["load", "push"]], ["row", "ops/table", {"x": "a", "grade": ["by", "grade", {"soft": "low", "hard": "high"}]}]]},
        {"id": "ops/key", "type": "bar", "mechanism": "bar.key", "anchor": MADE_UP, "says": "made up",
         "where": [{"le": [["abs", ["load", "push"]], ["q", "6.5", "kN"]], "why": "made up"}, {"le": ["a", ["q", "40", "mm"]], "why": "made up"}],
         "le": [["load", "push"], ["row", "ops/table", {"x": ["max", "a", "b"], "grade": ["key", "mid"]}]]},
        {"id": "ops/caps", "type": "bar", "mechanism": "bar.caps", "anchor": MADE_UP, "says": "made up",
         "le": [["load", "push"], ["add", ["row", "ops/table", {"x": "left.t", "grade": "left.finish"}],
                                  ["row", "ops/table", {"x": ["add", "right.t", "b"], "grade": ["by", "right.finish", {"low": "high", "high": "mid"}]}]]]},
        {"id": "ops/moment", "type": "bar", "mechanism": "bar.moment", "anchor": MADE_UP, "says": "made up",
         "le": [["load", "twist"], ["mul", ["load", "push"], "a"]]},
    ],
}


@dataclass
class Draft:
    """A design and its card before they are text. A line is a field and what follows it."""

    name: str
    parts: list[tuple[str, str, list[list[str]]]] = field(default_factory=list)      # type, name, lines
    givens: dict[str, str] = field(default_factory=dict)                             # name -> "[lo, hi]"
    loads: dict[str, list[str]] = field(default_factory=dict)                        # case -> entries
    waivers: list[tuple[str, str]] = field(default_factory=list)                     # mechanism, subject
    card_more: list[str] = field(default_factory=list)
    design_more: list[str] = field(default_factory=list)
    damage: list[str] = field(default_factory=list)

    def lines(self, part: str) -> list[list[str]]:
        return next(lines for _, name, lines in self.parts if name == part)

    def texts(self) -> tuple[str, str]:
        design = ["petra 0", "", *self.design_more]
        for kind, name, lines in self.parts:
            design += [f"{kind} {name} {{", *(f"  {key} {value}" for key, value in lines), "}", ""]
        card = ["petra 0", "", f'card "{self.name}" {{', '  owner "t@example.org"', "}", "", *self.card_more]
        card += [f"given {name} in {bound} {SIGNED}" for name, bound in self.givens.items()]
        for case, entries in self.loads.items():
            card += ["", f"load {case} {{", *(f"  {e}" for e in entries), f"  {SIGNED}", "}"]
        card += ["", *(f'waive {mechanism} on {subject} by "t@example.org" reason "generated"' for mechanism, subject in self.waivers)]
        return "\n".join(card) + "\n", "\n".join(design) + "\n"


def near(rng: random.Random, value: float, unit: str) -> str:
    """The value, or one a little under or over it, as a design writes it."""
    return f"{round(value * rng.choice([1, 1, 1, 0.999, 1.001, 0.9, 1.1]), 6):g} {unit}"


def spread(rng: random.Random, value: str) -> str:
    """A bound: the point, or a range that ends on it or straddles it."""
    number, unit = value.split()
    x = float(number)
    lo, hi = rng.choice([(x, x), (x, x), (x * 0.8, x), (x, x * 1.25), (x * 0.9, x * 1.1)])
    return f"[{round(lo, 6):g} {unit}, {round(hi, 6):g} {unit}]"


def lap(rng: random.Random, n: int) -> Draft:
    """A lap of the deck that ships, or two, with the plates they join."""
    d = Draft(f"lap-{n}")
    for k in range(rng.choice([1, 1, 1, 2])):
        suffix = "" if k == 0 else str(k + 1)
        tab, strap, splice = f"tab{suffix}", f"strap{suffix}", f"splice{suffix}"
        diameter = rng.choice([0.5, 0.625, 0.75, 0.75, 0.875, 1, 1.125, 1.25, 0.7, 0.7501])
        count = rng.choice([2, 3, 3, 4, 6, 14, 20])
        holes = rng.choice(["standard", "standard", "standard", "oversize"])
        surface = rng.choice(["protected", "protected", "weathering"])
        # Table J3.4 asks this end and side distance of the bolt, and Table J3.5 adds to it for an oversize hole.
        asked = {0.5: 0.75, 0.625: 0.875, 0.75: 1, 0.875: 1.125, 1: 1.25, 1.125: 1.5, 1.25: 1.625}.get(diameter, 1)
        asked += 0 if holes == "standard" else 0.0625 if diameter <= 0.875 else 0.125
        thin = 1.0
        for plate in (tab, strap):
            nominal = rng.choice([0.125, 0.25, 0.375, 0.375, 0.5, 0.75, 1])
            thin = min(thin, nominal)
            thickness = near(rng, nominal, "inch")
            lines = [["thickness", thickness], ["width", near(rng, rng.choice([4, 6, 8]), "inch")],
                     ["Fy", f"given {plate}.Fy"], ["Fu", f"given {plate}.Fu"]]
            if rng.random() < 0.2:      # a thickness the card bounds, so a proof holds over a range
                lines[0][1] = f"given {plate}.thickness"
                d.givens[f"{plate}.thickness"] = spread(rng, thickness)
            d.parts.append(("plate", plate, lines))
            d.givens[f"{plate}.Fy"] = rng.choice(["[36 ksi, 36 ksi]", "[36 ksi, 50 ksi]", "[50 ksi, 50 ksi]"])
            d.givens[f"{plate}.Fu"] = rng.choice(["[58 ksi, 58 ksi]", "[58 ksi, 65 ksi]", "[65 ksi, 65 ksi]"])
        # The pitch sits on and near what the rules turn on: 2 2/3 diameters (J3.4), the greatest spacing of the thinner
        # plate and its cap (J3.6: 24 thicknesses and 12 inch, or 14 and 7 for weathering steel), and a line of 38 inch,
        # past which note c of Table J3.2 lowers the shear stress.
        most = min(24 * thin, 12) if surface == "protected" else min(14 * thin, 7)
        pitch = rng.choice([near(rng, 3, "inch"), near(rng, 2.5, "inch"), near(rng, 38 / (count - 1), "inch"), f"{38 / (count - 1):.12g} inch",
                            near(rng, 8 / 3 * diameter, "inch"), f"{8 * diameter / 3:.12g} inch", near(rng, most, "inch"), f"{most:g} inch"])
        lines = [
            ["fastener", rng.choice(['"Group 120"', '"Group 120"', '"Group 144"', '"Group 150"'])],
            ["threads", rng.choice(["included", "excluded", '"included"'])],
            ["diameter", f"{diameter:g} inch"],
            ["holes", holes],
            ["count", str(count)],
            ["pitch", pitch],
            ["end", rng.choice([near(rng, asked, "inch"), near(rng, 1.5, "inch"), f"{asked:g} inch"])],
            ["side", rng.choice([near(rng, asked, "inch"), near(rng, 1.5, "inch"), near(rng, 3, "inch"), f"{asked:g} inch"])],
            ["surface", surface],
            ["joins", f"{tab} {strap}"]]
        for at in (5, 7):      # a pitch or a side distance the card bounds: a range may reach over a limit, or over the two cases of note c
            if rng.random() < 0.12:
                d.givens[f"{splice}.{lines[at][0]}"] = spread(rng, lines[at][1])
                lines[at][1] = f"given {splice}.{lines[at][0]}"
        d.parts.append(("lap", splice, lines))
        # Of a 6 inch by 3/8 inch A36 plate with one 13/16 inch hole 3 inch from its side: 0.9 Fy Ag is 72.9 kip, its net
        # section ruptures at 83.6 kip and a block tears out at 87.4 kip. Three 3/4 inch Group 120 bolts carry 53.68 kip.
        for case in rng.choice([[], ["gravity"], ["gravity"], ["gravity"], ["gravity", "wind"]]):
            top = rng.choice([near(rng, 72.9, "kip"), near(rng, 53.676, "kip"), near(rng, 45, "kip"), near(rng, 20, "kip"), near(rng, 150, "kip"),
                              near(rng, 83.6, "kip"), near(rng, 87.36, "kip")])
            bound = f"[{top}, {top}]" if rng.random() < 0.3 else f"[0 kip, {top}]"
            d.loads.setdefault(case, []).append(f"on {splice} pull in {bound}")
        # The lines the deck has no rule for, which a card waives to pass, and some lines that have rules, which a waiver hides.
        open_lines = ["lap.tightening", "lap.hole_use", "lap.max_edge_distance", "lap.ply_flexure"]
        waived = rng.choice([[], open_lines, open_lines, open_lines, rng.sample(open_lines, 2), ["lap.strength", "lap.slip"], open_lines + ["lap.end_distance"],
                             open_lines + ["lap.spread", "lap.block_shear"]])
        d.waivers += [(m, splice) for m in waived]
    return d


def strips(rng: random.Random, n: int) -> Draft:
    """A strip of the test deck with its two pads."""
    d = Draft(f"strips-{n}")
    for pad in ("p1", "p2"):
        d.parts.append(("pad", pad, [["area", rng.choice(["50 mm2", "60 mm2", "60 mm2", "60.001 mm2", "150 mm2", near(rng, 60, "mm2")])]]))
    width = rng.choice(["0.5 mm", "1 mm", "1 mm", "1.001 mm", "2 mm", "2.0001 mm", "5 mm", near(rng, 1, "mm"), near(rng, 2, "mm")])
    screw, fit = rng.choice(["3 mm", "3 mm", "4 mm", "3.5 mm", "3.0001 mm"]), rng.choice(["close", "close", "free"])
    lines = [["width", width], ["T", "given s.T"], ["gap", "given s.gap"], ["screw", screw],
             ["hole", rng.choice(["3.2 mm", "3.2 mm", "3.6 mm", "4.3 mm", "3.1 mm", "5 mm", near(rng, 3.2, "mm"), near(rng, 3.1, "mm")])],
             ["fit", fit], ["turns", rng.choice(["1", "2", "2", "3"])], ["lands", "p1 p2"]]
    d.givens["s.T"] = rng.choice(["[20 degC, 30 degC]", "[30 degC, 40 degC]", "[30 degC, 50 degC]", "[40 degC, 40 degC]",
                                  "[40.001 degC, 50 degC]", "[39.999 degC, 40.001 degC]", "[45 degC, 45 degC]"])
    d.givens["s.gap"] = rng.choice(["[0.5 mm, 0.6 mm]", "[1 mm, 3 mm]", "[2 mm, 2 mm]", "[0.1 mm, 3.9 mm]", "[1.5 mm, 2.5 mm]", "[1 mm, 5 mm]"])
    if rng.random() < 0.25:      # a width the card bounds: it may straddle a band
        lines[0][1] = "given s.width"
        d.givens["s.width"] = rng.choice(["[0.5 mm, 1 mm]", "[1 mm, 1 mm]", "[0.9 mm, 1.1 mm]", "[1 mm, 2 mm]", "[0.5 mm, 5 mm]", "[2 mm, 3 mm]"])
    if rng.random() < 0.15:
        lines[3][1] = "given s.screw"
        d.givens["s.screw"] = rng.choice(["[3 mm, 3 mm]", "[3 mm, 4 mm]", "[4 mm, 4 mm]"])
    d.parts.append(("strip", "s", lines))
    for case in rng.choice([[], ["run"], ["run"], ["run"], ["run", "surge"]]):
        top = rng.choice(["0.5 A", "1 A", "1.5 A", "2 A", "2 A", "2.01 A", "3 A", "4 A", "6 A", near(rng, 2, "A")])
        d.loads[case] = [f"on s current in {f'[{top}, {top}]' if rng.random() < 0.3 else f'[0 A, {top}]'}"]
    d.waivers = [(m, "s") for m in rng.choice([["strip.creep"], ["strip.creep"], [], ["strip.creep", "strip.heat"], ["strip.creep", "strip.tide", "strip.spark"]])]
    return d


def ops(rng: random.Random, n: int) -> Draft:
    """A bar of OPS: its lengths on and near the ends of the bands and the edges of the cases."""
    d = Draft(f"ops-{n}")
    length = ["5 mm", "5 mm", "10 mm", "10 mm", "10.001 mm", "9.999 mm", "20 mm", "20.5 mm", "1 mm", "50 mm"]
    lines = [["a", rng.choice(length)], ["b", rng.choice(length)], ["r", "given bar.r"], ["s", rng.choice(["1", "2", "0.5", "4", "4.001", "5", "1/3"])],
             ["grade", rng.choice(["soft", "hard"])]]
    d.givens["bar.r"] = rng.choice(["[1, 1]", "[1.2, 1.2]", "[2, 2]", "[0.5, 0.5]", "[1, 1.2]", "[0.9, 1.3]", "[1/3, 1/3]", "[0.999, 1.001]"])
    for k in (0, 1):
        if rng.random() < 0.3:      # a length the card bounds: it may straddle a case or a band
            d.givens[f"bar.{lines[k][0]}"] = rng.choice(["[5 mm, 10 mm]", "[10 mm, 10 mm]", "[9 mm, 11 mm]", "[10 mm, 20 mm]", "[19 mm, 21 mm]", "[4 mm, 6 mm]", "[1 mm, 50 mm]"])
            lines[k][1] = f"given bar.{lines[k][0]}"
    for cap in ("c1", "c2"):
        d.parts.append(("cap", cap, [["t", rng.choice(length)], ["finish", rng.choice(["low", "high"])]]))
    d.parts.append(("bar", "bar", [*lines, ["caps", "c1 c2"]]))
    for case in rng.choice([[], ["one"], ["one"], ["one", "two"], ["one", "two"]]):
        entries = []
        if rng.random() < 0.85:
            entries.append(f"on bar push in {rng.choice(['[0 kN, 1 kN]', '[-2 kN, 2 kN]', '[3 kN, 3 kN]', '[-6 kN, -6 kN]', '[0 kN, 6.001 kN]', '[4 kN, 5 kN]', '[7 kN, 9 kN]'])}")
        if rng.random() < 0.5:
            entries.append(f"on bar twist in {rng.choice(['[0 Nm, 5 Nm]', '[30 Nm, 30 Nm]', '[0 Nm, 100 Nm]', '[20 Nm, 60 Nm]'])}")
        if entries:
            d.loads[case] = entries
    d.waivers = [(m, "bar") for m in rng.choice([[], [], ["bar.idle"], ["bar.exp", "bar.cases"]])]
    return d


def damage(rng: random.Random, d: Draft) -> None:
    """Change the draft in one way that the grid may refuse. Some of these the language
    refuses first, and a few leave a design the grid still checks."""
    kind, part, lines = rng.choice([p for p in d.parts if p[2]])
    line = rng.choice(lines)
    joint = next(p for p in d.parts if p[0] in ("lap", "strip"))
    plate = next(p for p in d.parts if p[0] in ("plate", "pad"))
    load = "pull" if joint[0] == "lap" else "current"
    unit = "kip" if joint[0] == "lap" else "A"

    def drop_given(value: str) -> None:
        if value.startswith("given "):
            d.givens.pop(value.split()[1], None)

    def missing() -> None:
        lines.remove(line)
        drop_given(line[1])

    def unknown() -> None:
        lines.append(rng.choice([["colour", "red"], ["colour", "5 mm"], ["depth", '"deep"']]))

    def twice() -> None:
        lines.append(list(line))

    def design_states() -> None:
        signed = [l for _, _, ls in d.parts for l in ls if l[0] in ("Fy", "Fu", "T", "gap")]
        if signed:
            chosen = rng.choice(signed)
            drop_given(chosen[1])
            chosen[1] = {"Fy": "36 ksi", "Fu": "58 ksi", "T": "25 degC", "gap": "0.5 mm"}[chosen[0]]

    def swapped() -> None:
        for _, name, ls in d.parts:
            fields = {l[0]: l for l in ls}
            for a, b in (("Fy", "Fu"), ("T", "gap")):
                if a in fields and b in fields and fields[a][1].startswith("given") and fields[b][1].startswith("given"):
                    fields[a][1], fields[b][1] = fields[b][1], fields[a][1]
                    return

    def other_part() -> None:
        # A plate reads the bound of the other plate, which then reads nothing of its own.
        plates = [(name, [l for l in ls if l[0] == "Fy"]) for k, name, ls in d.parts if k == "plate"]
        if len(plates) >= 2 and plates[0][1]:
            (a, la), (b, _) = plates[0], plates[1]
            d.givens.pop(f"{a}.Fy", None)
            la[0][1] = f"given {b}.Fy"

    def wrong_unit() -> None:
        line[1] = rng.choice(["5 kip", "5 A", "3 mm2", "2", "7 degC"])
        drop_given(line[1])

    def not_positive() -> None:
        sized = [l for _, _, ls in d.parts for l in ls if l[1][:1].isdigit() and " " in l[1]]
        if sized:
            chosen = rng.choice(sized)
            chosen[1] = rng.choice(["0 ", "-1 "]) + chosen[1].split()[1]

    def given_not_positive() -> None:
        if d.givens:
            name = rng.choice(sorted(d.givens))
            unit_of = d.givens[name].rstrip("]").split()[-1]
            d.givens[name] = rng.choice([f"[0 {unit_of}, 5 {unit_of}]", f"[-2 {unit_of}, 5 {unit_of}]", "[1 kg, 2 kg]"])

    def bad_key() -> None:
        keys = [l for _, _, ls in d.parts for l in ls if l[0] in ("fastener", "threads", "holes", "surface", "fit")]
        if keys:
            rng.choice(keys)[1] = rng.choice(["huge", '"Group 200"', "A307", "a.b", "3 mm", "close free", "(1 mm, 2 mm)", "tab"])

    def bad_count() -> None:
        counts = [l for _, _, ls in d.parts for l in ls if l[0] in ("count", "turns")]
        if counts:
            chosen = rng.choice(counts)
            chosen[1] = rng.choice(["2.5", "1", "0", "3 mm", f"given {joint[1]}.{chosen[0]}", "5/2", "4/2"])
            if chosen[1].startswith("given"):
                d.givens[f"{joint[1]}.{chosen[0]}"] = "[2, 3]"

    def bad_joins() -> None:
        for refs in [l for l in joint[2] if l[0] in ("joins", "lands") and len(l[1].split()) == 2]:
            first, second = refs[1].split()
            refs[1] = rng.choice([first, f"{first} {first}", f"{first} {joint[1]}", f"{first} nobody", f"{first} {second} {first}",
                                  f'{first} "{second}"', f"{second} {first}", f"{first}.x {second}"])

    def joined_twice() -> None:
        name = joint[1] + "b"
        copied = [[k, v.replace(f"given {joint[1]}.", f"given {name}.")] for k, v in joint[2]]
        d.parts.append((joint[0], name, copied))
        for given in [g for g in d.givens if g.startswith(joint[1] + ".")]:
            d.givens[given.replace(joint[1] + ".", name + ".", 1)] = d.givens[given]

    def stray() -> None:
        copied = [[k, v.replace(f"given {plate[1]}.", "given spare.")] for k, v in plate[2]]
        d.parts.append((plate[0], "spare", copied))
        for given in [g for g in d.givens if g.startswith(plate[1] + ".")]:
            d.givens[given.replace(plate[1] + ".", "spare.", 1)] = d.givens[given]

    def bad_load() -> None:
        entry = rng.choice([f"on {plate[1]} {load} in [0 {unit}, 1 {unit}]", f"on {joint[1]} push in [0 {unit}, 1 {unit}]",
                            f"on {joint[1]} {load} in [0 mm, 4 mm]", f"on {joint[1]} {load} in [-1 {unit}, 1 {unit}]",
                            f"on nobody {load} in [0 {unit}, 1 {unit}]", f"on {joint[1]}.end {load} in [0 {unit}, 1 {unit}]"])
        d.loads[rng.choice(["gravity", "run", "extra"])] = [entry]

    def bad_waiver() -> None:
        mechanism = "lap.spacing" if joint[0] == "lap" else "strip.creep"
        d.waivers.append(rng.choice([(mechanism, plate[1]), (mechanism, "nobody"), ("strip.creep" if joint[0] == "lap" else "lap.spacing", joint[1])]))

    def claim() -> None:
        d.card_more.append(rng.choice([f"claim limit: {joint[1]}.{load} <= 2 {unit}", f"ambient in [10 degC, 40 degC] {SIGNED}"]))

    def param() -> None:
        sized = [l for l in plate[2] if l[0] in ("width", "area") and len(l[1].split()) == 2]
        if sized:
            d.design_more += [f"param w in [5 {sized[0][1].split()[-1]}, 7 {sized[0][1].split()[-1]}]", ""]
            sized[0][1] = "param w"

    def two_values() -> None:
        if not line[1].startswith("given") and line[0] not in ("joins", "lands"):
            line[1] = f"{line[1]} {line[1]}"

    def no_value() -> None:
        drop_given(line[1])
        line[1] = ""

    def given_twice() -> None:
        signed = [l for l in lines if l[1].startswith("given ")]
        if signed:
            lines.append([rng.choice(["width", "hole", "thickness", "screw"]), signed[0][1]])

    ways = [missing, unknown, twice, design_states, swapped, other_part, wrong_unit, not_positive, given_not_positive, bad_key, bad_count,
            bad_joins, joined_twice, stray, bad_load, bad_waiver, claim, param, two_values, no_value, given_twice]
    way = rng.choice(ways)
    way()
    d.damage.append(way.__name__)


def draft(seed: int, n: int) -> Draft:
    rng = random.Random(f"{seed}/{n}")
    d = rng.choice([lap, lap, strips, strips, ops])(rng, n)
    for _ in range(0 if d.name.startswith("ops") else rng.choice([0, 0, 0, 1, 1, 2])):
        damage(rng, d)
    return d


ODD = ["", "pi", "2", "x.y", "load pull", "load current", "@0", "1e3", " 5", "1_000", "+5", "-0", "1/0", "3/4", "1,000", "1 1/2", "0.5", "-3", "7/2", "100",
       "length", "force", "area", "dimensionless", "length^2", "force/length", "mm", "A", "kN", "upper", "lower", "a", "b", "near", "far", "fit", "close",
       "unread", "odd�", "١ ١/٢ mm", "5 mm ", "length^٢"]
"""Texts to put where a deck has another: numbers the two readers might read apart, and names that are something else too."""
KEYS = ["note", "what", "dim", "type", "as", "least", "unless", "when", "closed", "at", "bands", "one_of", "range", "jumps", "unit", "rises", "falls",
        "let", "where", "loads", "across", "table", "is", "cases"]


def damaged(rng: random.Random, body: dict) -> list[str]:
    """Change the deck in one or two ways, and say how. A text stays a text and a list a
    list: the kernel is known to refuse a number where a text goes, and Python to take it."""
    def walk(node: object, path: tuple = ()):
        yield path, node
        for key, value in (node.items() if isinstance(node, dict) else enumerate(node) if isinstance(node, list) else ()):
            yield from walk(value, (*path, key))

    def put(path: tuple, value: object) -> None:
        parent = body
        for step in path[:-1]:
            parent = parent[step]
        parent[path[-1]] = value

    done = []
    for _ in range(rng.choice([1, 1, 2])):
        nodes = list(walk(body))
        texts = [(path, v) for path, v in nodes if isinstance(v, str) and path and path[-1] not in ("about", "page")]
        dicts = [v for _, v in nodes if isinstance(v, dict) and v]
        lists = [v for _, v in nodes if isinstance(v, list) and v]
        way = rng.choice(["another text", "another text", "another text", "an odd text", "an odd text", "a key less", "an item less", "an item twice",
                          "items in another order", "a key renamed", "a key more", "a where with no item", "two rules that end alike", "a line named unread",
                          "a wide row applied"])
        rules = [r for r in body["rules"] if isinstance(r, dict)] if isinstance(body.get("rules"), list) else []
        if way == "a wide row applied" and rules and isinstance(body.get("rows"), list):
            # A row of 1,000 names, about 2,000 steps, that names of `let` apply and nothing reads, so the steps to read the deck are all that
            # changes: 9 times is far within the million, and 1,000 times is over it.
            times = rng.choice([9, 1000])
            body["rows"].append({"id": "bench/wide", "anchor": MADE_UP, "gives": {"name": "y", "dim": "dimensionless"},
                                 "takes": [{"name": "x", "dim": "dimensionless", "range": ["1", "2"]}], "is": ["add"] + ["x"] * 1000})
            chosen = rng.choice(rules)
            chosen["let"] = {**(chosen["let"] if isinstance(chosen.get("let"), dict) else {}),
                             **{f"wide{i}": ["row", "bench/wide", {"x": "1"}] for i in range(times)}}
            way = f"a wide row applied {times} times"
        elif way == "a wide row applied":
            continue
        elif way == "a where with no item" and rules:
            rng.choice(rules)["where"] = []
        elif way == "two rules that end alike" and rules:
            chosen = copy.deepcopy(rng.choice(rules))
            body["rules"].append({**chosen, "id": "other/" + str(chosen.get("id")).rpartition("/")[2]})
        elif way == "a line named unread" and rules:
            # The line and its rules take the name together, so the name is all that is wrong.
            old = rng.choice(rules).get("mechanism")
            for item in [*rules, *(a for a in body.get("grid", []) if isinstance(a, dict))]:
                if item.get("mechanism") == old:
                    item["mechanism"] = "unread"
        elif way in ("a where with no item", "two rules that end alike", "a line named unread"):
            continue
        elif way == "another text":
            put(rng.choice(texts)[0], rng.choice(texts)[1])
        elif way == "an odd text":
            put(rng.choice(texts)[0], rng.choice(ODD))
        elif way == "a key less":
            chosen = rng.choice(dicts)
            chosen.pop(rng.choice(sorted(chosen)))
        elif way == "an item less":
            chosen = rng.choice(lists)
            chosen.pop(rng.randrange(len(chosen)))
        elif way == "an item twice":
            chosen = rng.choice(lists)
            chosen.append(copy.deepcopy(rng.choice(chosen)))
        elif way == "items in another order":
            rng.shuffle(rng.choice(lists))
        elif way == "a key renamed":
            chosen = rng.choice(dicts)
            chosen[rng.choice(KEYS)] = chosen.pop(rng.choice(sorted(chosen)))
        else:
            rng.choice(dicts)[rng.choice(KEYS)] = rng.choice([rng.choice(texts)[1], rng.choice(ODD)])
        done.append(way)
    return done


_STATE: dict[str, object] = {}


def _decks() -> dict[str, grid.Deck]:
    if not _STATE:
        from petra.registry import build_registry
        from tests.test_grid import CARD, DESIGN, STRIPS

        path = ROOT / "examples" / "deck" / "lap_unknown.petra"
        _STATE["registry"] = build_registry()
        _STATE["lap"] = next(d for d in grid.decks() if "lap" in d.types)
        _STATE["strips"] = grid.read_deck(json.dumps(STRIPS))
        _STATE["ops"] = grid.read_deck(json.dumps(OPS))
        _STATE["honest"] = {"lap": (path.with_suffix(".card").read_text(encoding="utf-8"), path.read_text(encoding="utf-8")),
                            "strips": (CARD, DESIGN), "ops": ops(random.Random(5), 0).texts()}
    return _STATE      # type: ignore[return-value]


def judge(card: str, design: str, name: str, rules: str | None = None, slash: bool = False) -> tuple[str, str, list[str], dict[str, str], dict]:
    """What the grid and the kernel make of a pair: an outcome, a line that says what
    differs, what each cell is for a design both checked (its mechanism and state, with
    `split` for a proof whose partition is not one leaf), the files and the kernel's word.
    The design is read with its own deck. With `rules`, both then check it against that
    text in place of the deck. With `slash`, the first load case is renamed to hold a `/`
    once the language has read it: the language writes no such name, and a card.json can."""
    decks = _decks()
    deck = decks[name.partition("-")[0]]
    with mock.patch.object(grid, "decks", lambda: (deck,)):
        try:
            parsed = parse_design(card, design, f"{name}.petra", decks["registry"])
            if grid.owner(parsed) is None:
                return "the language refuses it", "", [], {}, {}
        except INPUT_ERRORS:
            return "the language refuses it", "", [], {}, {}
        if slash and parsed.loads:
            first = next(iter(parsed.loads))
            renamed = {(f"{k}/where" if k == first else k): (dataclasses.replace(v, name=f"{k}/where") if k == first else v) for k, v in parsed.loads.items()}
            parsed = dataclasses.replace(parsed, loads=renamed)
        files = {**grid.bundle(parsed, deck), **({} if rules is None else {"rules": rules})}
        report, mine = None, "the design"
        try:
            deck = deck if rules is None else grid.read_deck(rules)
            report, files = grid.check(parsed, deck)
        except grid.DeckError as exc:
            mine, refusal = "the deck", str(exc)
        except ComponentError as exc:
            refusal = str(exc)
        except Exception as exc:      # noqa: BLE001: a crash of the grid is a difference to report, not the end of the run
            return f"DIFFER: the grid crashes on {'the design' if isinstance(deck, grid.Deck) and deck.text == rules else 'the deck'}", f"{type(exc).__name__}: {exc}", [], files, {}
    said = verify.ask(_STATE["kernel"], files)      # type: ignore[arg-type]
    third = twin(files, said)
    if third:
        return f"DIFFER: {third[0]}", third[1], [], files, said
    its = "the deck" if any(f["file"] == "rules" for f in said["findings"]) else "the design"
    if report is None and said["verdict"] == "ILL-FORMED":
        outcome, detail = (f"both refuse {mine}", "") if mine == its else (f"DIFFER: the grid refuses {mine} and the kernel {its}", refusal)
    elif report is None:
        outcome, detail = f"DIFFER: the grid refuses {mine} and the kernel does not", refusal
    elif said["verdict"] == "ILL-FORMED":
        outcome, detail = f"DIFFER: the kernel refuses {its} and the grid does not", "; ".join(f"{f['item']}: {f['why']}" for f in said["findings"])
    else:
        detail = verify.differs([(c.subject, c.mechanism, c.entry, c.state) for c in report.cells], report.status, deck.hash, said)
        outcome = "DIFFER: the cells differ" if detail else f"both give {report.status}"
    kinds = [] if report is None else [f"{c.mechanism if c.mechanism == 'unread' else c.mechanism + ('/where' if c.entry.endswith('/where') else '')} {c.state}"
                                       + (" split" if isinstance(c.proof.get("partition"), dict) else "") for c in report.cells]
    return outcome, detail, kinds, files, said


def twin(files: dict[str, str], said: dict) -> tuple[str, str] | None:
    """What differs between the kernel and the third reading named by PETRA_TWIN, a checker
    written from docs/format.md and docs/deck.md alone (bench/twin/verify.mjs), or None when
    they agree or no third reading is named. They must give one verdict, and for a design
    both read, the same cells in the same order."""
    script = os.environ.get("PETRA_TWIN")
    if not script:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        command = ["node", script]
        for name, body in files.items():
            Path(tmp, f"{name}.json").write_text(body, encoding="utf-8", newline="\n")
            command += [f"--{name}", str(Path(tmp, f"{name}.json"))]
        done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL)
    try:
        its = json.loads(done.stdout)
    except ValueError:
        return "the third reading gives no verdict", (done.stderr or done.stdout)[-300:]
    if its["verdict"] != said["verdict"]:
        why = "; ".join(str(f.get("why", f)) for f in its.get("findings", []))[:300] or "; ".join(f"{f['item']}: {f['why']}" for f in said["findings"])[:300]
        return f"the kernel gives {said['verdict']} and the third reading {its['verdict']}", why
    if said["verdict"] == "ILL-FORMED":
        return None
    mine = [(c["subject"], c["mechanism"], c["entry"], c["state"]) for c in said["cells"]]
    theirs = [(c["subject"], c["mechanism"], c["entry"], c["state"]) for c in its["cells"]]
    if mine != theirs:
        first = next((f"kernel {a}, third reading {b}" for a, b in zip(mine, theirs) if a != b), f"{len(mine)} cells against {len(theirs)}")
        return "the kernel's cells and the third reading's differ", first
    return None


def compare(seed: int, n: int, decks: bool, keep: str | None = None) -> tuple[str, str, list[str], list[str]]:
    """What became of case `n`: the outcome, what differs, what was damaged and the cells.
    A case is a generated design against its deck, or with `decks` an honest design against
    a damaged deck."""
    if decks:
        rng = random.Random(f"deck/{seed}/{n}")
        name = rng.choice(["strips", "strips", "ops", "ops", "lap"])
        body = json.loads(_decks()[name].text)      # type: ignore[union-attr]
        done = damaged(rng, body)
        (card, design), rules = _decks()["honest"][name], json.dumps(body)      # type: ignore[index]
    else:
        d = draft(seed, n)
        (card, design), name, done, rules = d.texts(), d.name, d.damage, None
    # One undamaged design in forty has a load case with a `/` in its name, and one in forty a card whose name is as
    # long as the kernel takes for a design with parts, 200 bytes, or one byte longer.
    slash = not decks and not done and bool(d.loads) and random.Random(f"slash/{seed}/{n}").randrange(40) == 0
    title = random.Random(f"title/{seed}/{n}")
    if not decks and not done and title.randrange(40) == 0:
        long = title.choice([200, 201])
        card = card.replace(f'card "{d.name}"', f'card "{d.name}{"n" * (long - len(d.name))}"', 1)
        done = [f"a card named in {long} bytes"]
    done = [*done, *(["a case named with a /"] if slash else [])]
    outcome, detail, kinds, files, said = judge(card, design, name, rules, slash)
    if keep and outcome.startswith("DIFFER"):
        out = Path(keep, f"deck-{name}-{n}" if decks else name)
        out.mkdir(parents=True, exist_ok=True)
        for file, text in {**{f"{k}.json": v for k, v in files.items()}, "design.petra": design, "design.card": card,
                           "kernel.json": json.dumps(said, indent=1), "difference.txt": f"{outcome}\n{detail}\n{done}\n"}.items():
            (out / file).write_text(text, encoding="utf-8", newline="\n")
    return outcome, detail, done, kinds


def _work(args: tuple[int, int, int, bool, str | None, str]) -> list[tuple[int, str, str, list[str], list[str]]]:
    seed, start, stop, decks, keep, kernel = args
    _decks()
    _STATE["kernel"] = kernel
    return [(n, *compare(seed, n, decks, keep)) for n in range(start, stop)]


def run(what: str, count: int, seed: int, jobs: int, decks: bool, keep: str | None, kernel: str) -> int:
    """Run `count` cases, print what became of them, and give how many differ."""
    step = max(1, min(50, count // (4 * jobs) or 1))
    chunks = [(seed, a, min(a + step, count), decks, keep, kernel) for a in range(0, count, step)]
    outcomes: collections.Counter[str] = collections.Counter()
    by_damage: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    differ: list[str] = []
    cells: collections.Counter[str] = collections.Counter()
    with ProcessPoolExecutor(jobs) as pool:
        for found in pool.map(_work, chunks):
            for n, outcome, detail, done, kinds in found:
                outcomes[outcome] += 1
                cells.update(kinds)
                for way in done or ["undamaged"]:
                    by_damage[way][outcome.split(":")[0] if outcome.startswith("DIFFER") else outcome] += 1
                if outcome.startswith("DIFFER"):
                    differ.append(f"{what} {n} ({', '.join(done) or 'undamaged'}): {outcome}: {detail}")
    for line in differ[:40]:
        print(line)
    print(f"{count} {what}s, seed {seed}")
    for outcome, k in sorted(outcomes.items()):
        print(f"  {k:6}  {outcome}")
    print("by damage (a case damaged twice counts under both):")
    for way, counts in sorted(by_damage.items()):
        print(f"  {way:<22} " + ", ".join(f"{k} {outcome}" for outcome, k in sorted(counts.items())))
    if not decks:
        print("cells of the designs both checked:")
        for kind, k in sorted(cells.items()):
            print(f"  {k:6}  {kind}")
    compared = sum(k for outcome, k in outcomes.items() if outcome != "the language refuses it")
    print(f"{compared} {what}s compared, {len(differ)} differ")
    return len(differ)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--count", type=int, default=5000, help="how many designs to make")
    parser.add_argument("--decks", type=int, default=0, metavar="N", help="how many damaged decks to make")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    parser.add_argument("--keep", metavar="DIR", help="write the files of each case that differs")
    args = parser.parse_args()
    kernel = verify.binary()
    if kernel is None:
        print("no petra-verify is built here and PETRA_VERIFY names none", file=sys.stderr)
        return 2
    differ = run("design", args.count, args.seed, args.jobs, False, args.keep, kernel) if args.count else 0
    differ += run("deck", args.decks, args.seed, args.jobs, True, args.keep, kernel) if args.decks else 0
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main())
