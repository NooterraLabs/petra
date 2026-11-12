"""The grid against the kernel, on generated designs.

    python bench/kernel_grid.py [--count N] [--decks N] [--seed S] [--jobs J] [--keep DIR]

petra/grid.py and petra-verify each work out the cells of a design checked against a deck
of rules. This makes N designs, has both check each one, and counts the designs they
differ on. A difference is a bug in one of the two.

A design is of one of four decks: the deck that ships, with its `lap` and `plate`,
STRIPS, the deck made up for tests/test_grid.py, OPS and KIT. OPS is made up here so that every
operator of the rule language is in a rule: powers, roots, exp and ln, cos at zero, at a
quarter and a half turn, across a multiple of pi, of tiny and of long fractions, at the edge
of its domain and as a sine, conditions joined
by and, or and not, a table with bands closed at the lower end, every way to bind a key,
a key of a joined part, and a range that reads a load. Its bar takes three loads and its cap
one: a rule that reads two of them, a rule that reads the third for some bars and not for
others, and a load on a cap that no rule reads. OPS also has what the deck for lifting
beams asked of the language (docs/deck.md): a length to the fourth power, written in mm^4,
cm^4, m^4 and inch^4 in a design, a card and the deck; a `when` and an `unless` on a key of
a joined part; a rule that requires a condition over keys, which holds for some bars and
fails for others; a row that gives a name by the bands of two quantities, read by a key of
a table and by a `case`, with bars inside its bands, on their ends, outside them and at its
empty cell; and what a cap and a bar need of their fields, which about one bar in five
breaks.

KIT is made up here for what three more families asked (docs/deck.md): a key and a count
that the card states with `is`, given, missing, written by the design, of the wrong kind
and under its floor; a waiver for a line whose rules prove, for one whose rules refute,
for one with no rule and for one that cannot arise, and for every line at once; each unit
read since 2026-11-11 in a design, a card or the deck, on and beside the edges of the
rules; a quantity and a key that a cell may leave unstated, read by a rule, by a `when`,
by an `unless`, by a need and by nothing; quantities at zero and under it, a count that
may be zero as a divisor, and a load of either sign; and rules that state `lt` with
numbers exactly on their limit. Three of its rigs in five are calm, with numbers that keep
every rule, so that a rig may pass when its card waives the one line that has no rule.
One rig in three is then damaged in a way the grid refuses, or the language before it.

A design's numbers are drawn from
the ends of the decks' bands, their listed
values and the edges of their cases and ranges, and from near them. Its loads are
points or ranges, in no, one or two load cases, and its card waives some mechanisms or none.
A case may put some of the loads a rule reads on a part and not the others, put a load on
one part and none on another, or put none on any: each rule that reads a load then has an
open cell under that case. And a card may put a load on a part that no rule reads there,
which is an open cell named `unread`.
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

`--decks N` also makes N damaged decks. Each is one of the four decks with one or two
changes: a text swapped for another text of the deck or for an odd one, a key or an item
dropped, doubled, moved or renamed, a `where` with no item, two rules of one line whose
ids end alike, a line named `unread`, a `when`, an `unless` or a `requires` that asks
`loaded`, which is no condition, a row that gives a name that none of its cells holds,
a requirement that no part can break or no part can meet, a mark on a field with a value
it may or may not take there (`optional`, `signed`, `whole`, `may_be`, `least`), `lt` for
`le` or both at once, or a wide row that a rule applies 9 times or 1,000
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
from fractions import Fraction
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from petra import grid, verify  # noqa: E402
from petra.kernel import Interval, i_cos  # noqa: E402
from petra.lang import parse_design  # noqa: E402
from petra.models.base import ComponentError  # noqa: E402
from petra.repair import INPUT_ERRORS  # noqa: E402

SIGNED = 'signed "t@example.org" source "generated"'
MADE_UP = {"standard": "a deck made up for the bench", "clause": "1"}


def _takes(*names: str) -> list[dict]:
    return [{"name": name, "dim": "length" if name in "abx" else "dimensionless", "what": name,
             "range": ["1 mm", "100 mm"] if name in "abx" else ["0.1", "10"]} for name in names]


def _exact(x: Fraction) -> str:
    """A number as a deck writes it, with nothing rounded."""
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


STEP = Fraction(1, 2 ** 96)
"""One step of the grid that the kernel rounds a cosine to."""
COS_1 = i_cos(Interval.point(Fraction(1)))
"""The two points of the grid around cos 1. A rule of OPS states each as a limit, and one
states the point a step inside: a kernel whose cosine ends one step off settles those cells
another way than the grid."""
LONG = Fraction(10 ** 300 + 7, 9 * 10 ** 299 + 1)
"""A fraction near 10/9 whose numerator and denominator each have 300 digits."""
COS_LONG = i_cos(Interval.point(LONG))


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
        {"id": "ops/class", "anchor": MADE_UP, "gives": {"name": "grade", "one_of": ["low", "mid", "high"], "what": "a name by the bands of two quantities"},
         "takes": [*_takes("x"), {"name": "i", "dim": "length^4", "what": "i", "range": ["1 mm^4", "10000 mm^4"]}],
         "table": {"down": {"by": "x", "bands": [["0 mm", "10 mm"], ["10 mm", "20 mm"], ["20 mm", "40 mm"]], "closed": "lower"},
                   "across": {"by": "i", "bands": [["0 mm^4", "1000 mm^4"], ["1000 mm^4", None]]},
                   "cells": [["low", "mid"], ["mid", None], ["high", "high"]]}},
        {"id": "ops/modulus", "anchor": MADE_UP, "gives": {"name": "S", "dim": "length^3", "what": "a length to the fourth over a length"},
         "takes": [{"name": "i", "dim": "length^4", "what": "i", "range": ["1 mm^4", "1 cm^4"]}, {"name": "c", "dim": "length", "what": "c", "range": ["1 mm", "100 mm"]}],
         "is": ["div", "i", "c"]},
        {"id": "ops/turn", "anchor": MADE_UP, "gives": {"name": "y", "dim": "dimensionless", "what": "the cosine of a number of half turns"}, "takes": _takes("s"),
         "is": ["cos", ["mul", "pi", "s"]]},
        {"id": "ops/sine", "anchor": MADE_UP, "gives": {"name": "y", "dim": "dimensionless", "what": "a sine, as the cosine of a quarter turn less the angle"},
         "takes": _takes("r"), "is": ["cos", ["sub", ["div", "pi", "2"], "r"]]},
    ],
    "types": [
        {"type": "cap", "what": "an end of a bar", "fields": [
            {"name": "t", "dim": "length", "what": "its thickness"}, {"name": "finish", "one_of": ["low", "high"], "what": "a key whose names are the table's"},
            {"name": "i", "dim": "length^4", "least": "1 mm^4", "what": "a length to the fourth power"}],
         "loads": [{"name": "press", "dim": "force", "least": "0 N", "what": "a force that no rule reads"}],
         "needs": [{"le": [["q", "400", "mm^4"], "i"], "why": "made up: at least 400 mm^4"}]},
        {"type": "bar", "what": "a bar", "fields": [
            {"name": "a", "dim": "length", "what": "a length"}, {"name": "b", "dim": "length", "what": "another"},
            {"name": "r", "dim": "dimensionless", "signed": True, "what": "a ratio the card states"}, {"name": "s", "dim": "dimensionless", "what": "an exponent"},
            {"name": "grade", "one_of": ["soft", "hard"], "what": "a key"}, {"name": "caps", "type": "cap", "as": ["left", "right"], "what": "its two ends"}],
         "loads": [{"name": "push", "dim": "force", "what": "a force of either sign"}, {"name": "twist", "dim": "moment", "least": "0 Nm", "what": "a moment"},
                   {"name": "drag", "dim": "force", "least": "0 N", "what": "a force that a rule reads for a hard bar and none for a soft one"}],
         "needs": [{"lt": ["left.t", ["mul", "8", "a"]], "why": "made up: the left cap is under 8 times as thick as the bar is long"},
                   {"le": [["div", ["sub", "right.t", ["q", "100", "mm"]], "b"], ["div", "r", "1/1000"]], "why": "made up: a quotient by a field"}]}],
    "grid": [{"type": "bar", "mechanism": f"bar.{name}", "what": name, "anchor": MADE_UP, **more} for name, more in (
        ("cases", {}), ("roots", {}), ("exp", {}), ("table", {}), ("key", {}), ("moment", {}), ("caps", {}), ("drag", {}),
        ("idle", {"unless": {"when": ["or", ["not", ["is", "left.finish", "low"]], ["and", ["is", "grade", "hard"], ["is", "right.finish", "high"]]], "why": "made up"}}),
        ("named", {}), ("cased", {}), ("left", {}), ("alike", {}), ("modulus", {}),
        ("cos", {}), ("cosin", {}), ("cosfloor", {}), ("turn", {}), ("sine", {}), ("zero", {}), ("tiny", {}), ("edge", {}), ("long", {}),
        ("right", {"unless": {"when": ["and", ["is", "right.finish", "low"], ["not", ["is", "left.finish", "low"]]], "why": "made up: a key of a joined part"}}))],
    "rules": [
        {"id": "ops/cases", "type": "bar", "mechanism": "bar.cases", "anchor": MADE_UP, "says": "made up",
         "le": [["row", "ops/cases", {"a": "a", "b": "b"}], "1.5"]},
        {"id": "ops/roots", "type": "bar", "mechanism": "bar.roots", "anchor": MADE_UP, "says": "made up", "let": {"both": ["row", "ops/roots", {"a": "a", "b": "b"}]},
         "le": ["both", ["mul", "2.5", "b"]]},
        {"id": "ops/exp", "type": "bar", "mechanism": "bar.exp", "anchor": MADE_UP, "says": "made up", "where": [{"le": ["s", "4"], "why": "made up"}],
         "le": [["row", "ops/exp", {"r": "r", "s": "s"}], "5.2"]},
        {"id": "ops/table", "type": "bar", "mechanism": "bar.table", "anchor": MADE_UP, "says": "made up",
         "when": ["or", ["is", "grade", "soft"], ["not", ["is", "right.finish", "low"]]],
         "le": [["abs", ["load", "push"]], ["row", "ops/table", {"x": "a", "grade": ["by", "grade", {"soft": "low", "hard": "high"}]}]]},
        {"id": "ops/key", "type": "bar", "mechanism": "bar.key", "anchor": MADE_UP, "says": "made up",
         "where": [{"le": [["abs", ["load", "push"]], ["q", "6.5", "kN"]], "why": "made up"}, {"le": ["a", ["q", "40", "mm"]], "why": "made up"}],
         "le": [["load", "push"], ["row", "ops/table", {"x": ["max", "a", "b"], "grade": ["key", "mid"]}]]},
        {"id": "ops/caps", "type": "bar", "mechanism": "bar.caps", "anchor": MADE_UP, "says": "made up",
         "le": [["load", "push"], ["add", ["row", "ops/table", {"x": "left.t", "grade": "left.finish"}],
                                  ["row", "ops/table", {"x": ["add", "right.t", "b"], "grade": ["by", "right.finish", {"low": "high", "high": "mid"}]}]]]},
        {"id": "ops/moment", "type": "bar", "mechanism": "bar.moment", "anchor": MADE_UP, "says": "made up",
         "le": [["load", "twist"], ["mul", ["load", "push"], "a"]]},
        {"id": "ops/drag", "type": "bar", "mechanism": "bar.drag", "anchor": MADE_UP, "says": "made up",
         "when": ["is", "grade", "hard"], "le": [["load", "drag"], ["q", "2", "kN"]]},
        # A key of a table that a row names by the bands of two quantities, and the expression of that name.
        {"id": "ops/named", "type": "bar", "mechanism": "bar.named", "anchor": MADE_UP, "says": "made up",
         "le": [["abs", ["load", "push"]], ["row", "ops/table", {"x": "b", "grade": ["row", "ops/class", {"x": "a", "i": "left.i"}]}]]},
        {"id": "ops/cased", "type": "bar", "mechanism": "bar.cased", "anchor": MADE_UP, "says": "made up",
         "le": [["case", ["row", "ops/class", {"x": "b", "i": "right.i"}],
                 {"low": ["mul", "a", "2"], "mid": ["row", "ops/roots", {"a": "a", "b": "b"}], "high": ["sub", "a", ["q", "1", "mm"]]}], ["q", "30", "mm"]]},
        # A condition on keys of the joined parts, a rule that requires, and a unit with a power.
        {"id": "ops/left", "type": "bar", "mechanism": "bar.left", "anchor": MADE_UP, "says": "made up",
         "when": ["and", ["is", "left.finish", "high"], ["not", ["is", "right.finish", "high"]]], "le": ["left.t", ["mul", "2", "right.t"]]},
        {"id": "ops/alike", "type": "bar", "mechanism": "bar.alike", "anchor": MADE_UP, "says": "made up",
         "when": ["is", "grade", "hard"], "requires": ["or", ["is", "left.finish", "low"], ["is", "right.finish", "high"]]},
        {"id": "ops/modulus", "type": "bar", "mechanism": "bar.modulus", "anchor": MADE_UP, "says": "made up",
         "le": [["row", "ops/modulus", {"i": "left.i", "c": "a"}], ["q", "0.15", "cm^3"]]},
        # The cosine. Its limits are points of the grid: the upper point of cos 1, the point a step under it, which a
        # ratio of 1 neither keeps nor breaks, and the lower point, as the least the cosine may be.
        {"id": "ops/cos", "type": "bar", "mechanism": "bar.cos", "anchor": MADE_UP, "says": "made up", "le": [["cos", "r"], _exact(COS_1.hi)]},
        {"id": "ops/cosin", "type": "bar", "mechanism": "bar.cosin", "anchor": MADE_UP, "says": "made up", "le": [["cos", "r"], _exact(COS_1.hi - STEP)]},
        {"id": "ops/cosfloor", "type": "bar", "mechanism": "bar.cosfloor", "anchor": MADE_UP, "says": "made up", "le": [_exact(COS_1.lo), ["cos", "r"]]},
        # An angle at a quarter turn, a half turn and a whole one, where the kernel's pi does not say on which side of
        # the turn an end lies: at a quarter turn the cosine is within a step of zero on both sides.
        {"id": "ops/turn", "type": "bar", "mechanism": "bar.turn", "anchor": MADE_UP, "says": "made up", "le": [["row", "ops/turn", {"s": "s"}], _exact(STEP)]},
        {"id": "ops/sine", "type": "bar", "mechanism": "bar.sine", "anchor": MADE_UP, "says": "made up", "le": [["row", "ops/sine", {"r": "r"}], "0.85"]},
        # At zero the cosine is 1 and no more, an angle of 10^-30 has one within a step of 1, and one of 65,536 is the
        # largest that has a cosine: a ratio over 1 is past it, and a range that reaches over 1 is too.
        {"id": "ops/zero", "type": "bar", "mechanism": "bar.zero", "anchor": MADE_UP, "says": "made up", "le": ["1", ["cos", ["sub", "r", "r"]]]},
        {"id": "ops/tiny", "type": "bar", "mechanism": "bar.tiny", "anchor": MADE_UP, "says": "made up",
         "le": [_exact(1 - STEP), ["cos", ["div", "r", "1" + "0" * 30]]]},
        {"id": "ops/edge", "type": "bar", "mechanism": "bar.edge", "anchor": MADE_UP, "says": "made up", "le": [["cos", ["mul", "r", "65536"]], "1"]},
        {"id": "ops/long", "type": "bar", "mechanism": "bar.long", "anchor": MADE_UP, "says": "made up",
         "le": [["cos", ["mul", "r", _exact(LONG)]], _exact(COS_LONG.hi)]},
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
    environment: str | None = None                                                   # a registry id, which no deck reads yet

    def lines(self, part: str) -> list[list[str]]:
        return next(lines for _, name, lines in self.parts if name == part)

    def texts(self) -> tuple[str, str]:
        design = ["petra 0", "", *self.design_more]
        for kind, name, lines in self.parts:
            design += [f"{kind} {name} {{", *(f"  {key} {value}" for key, value in lines), "}", ""]
        stated = [f"  environment {self.environment}"] if self.environment else []
        card = ["petra 0", "", f'card "{self.name}" {{', '  owner "t@example.org"', *stated, "}", "", *self.card_more]
        # A given is a bound, `[lo, hi]`, or what follows its name as written: `in [lo, hi]`, or `is NAME` for what the card states exactly.
        card += [f"given {name} {bound if bound.startswith(('in ', 'is ')) else 'in ' + bound} {SIGNED}" for name, bound in self.givens.items()]
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
        if rng.random() < 0.08:      # a case of the card that puts no pull on this lap, or on any
            d.loads.setdefault("storm", [])
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
    if rng.random() < 0.08:      # a case of the card that puts no current on the strip
        d.loads["idle"] = []
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
        # A length to the fourth power, in several units, on and beside the end of a band of ops/class at 1000 mm^4. One in
        # sixteen is under the 400 mm^4 that a cap needs, and a thick left cap on a short bar breaks what a bar needs.
        fourth = rng.choice(["500 mm^4", "500 mm^4", "1000 mm^4", "1000 mm^4", "1000.001 mm^4", "0.1 cm^4", "2000 mm^4", "0.2 cm^4", "0.0024025 inch^4",
                             "999.999 mm^4", "400 mm^4", "0.0000000005 m^4", "1500 mm^4", "700 mm^4", "399.999 mm^4", "5000 mm^4",
                             "800 mm^4", "1200 mm^4", "0.09 cm^4", "999 mm^4", "1001 mm^4", "3000 mm^4", "450 mm^4", "600 mm^4"])
        if rng.random() < 0.2:      # a bound of the card, which may reach over the end of the band or under what the cap needs
            d.givens[f"{cap}.i"] = rng.choice(["[900 mm^4, 1000 mm^4]", "[900 mm^4, 1100 mm^4]", "[1000 mm^4, 1000 mm^4]", "[0.1 cm^4, 0.2 cm^4]", "[390 mm^4, 500 mm^4]", "[400 mm^4, 800 mm^4]"])
            fourth = f"given {cap}.i"
        d.parts.append(("cap", cap, [["t", rng.choice(length)], ["finish", rng.choice(["low", "high"])], ["i", fourth]]))
    d.parts.append(("bar", "bar", [*lines, ["caps", rng.choice(["c1 c2", "c1 c2", "c2 c1"])]]))
    for case in rng.choice([[], ["one"], ["one"], ["one", "two"], ["one", "two"]]):
        entries = []
        if rng.random() < 0.85:
            entries.append(f"on bar push in {rng.choice(['[0 kN, 1 kN]', '[-2 kN, 2 kN]', '[3 kN, 3 kN]', '[-6 kN, -6 kN]', '[0 kN, 6.001 kN]', '[4 kN, 5 kN]', '[7 kN, 9 kN]'])}")
        if rng.random() < 0.5:
            entries.append(f"on bar twist in {rng.choice(['[0 Nm, 5 Nm]', '[30 Nm, 30 Nm]', '[0 Nm, 100 Nm]', '[20 Nm, 60 Nm]', '[0 Nm, 0 Nm]'])}")
        if rng.random() < 0.3:      # read by ops/drag for a hard bar, and by nothing for a soft one
            entries.append(f"on bar drag in {rng.choice(['[0 kN, 1 kN]', '[2 kN, 2 kN]', '[0 kN, 3 kN]', '[0 N, 0 N]'])}")
        if rng.random() < 0.15:      # no rule reads a load on a cap
            entries.append(f"on {rng.choice(['c1', 'c2'])} press in {rng.choice(['[0 N, 1 N]', '[5 kN, 5 kN]'])}")
        if entries or rng.random() < 0.5:      # a case with no load in it is still a case of the card
            d.loads[case] = entries
    d.waivers = [(m, "bar") for m in rng.choice([[], [], ["bar.idle"], ["bar.exp", "bar.cases"]])]
    return d


def _kit_field(name: str, **more: object) -> dict:
    return {"name": name, "what": name, **more}


def _kit_rule(name: str, mechanism: str, **body: object) -> dict:
    return {"id": f"kit/{name}", "type": "rig" if mechanism.startswith("rig.") else "cell", "mechanism": mechanism, "anchor": MADE_UP, "says": "made up", **body}


KIT = {
    "format": "petra-rules/0", "name": "bench-kit", "about": "Made up for bench/kernel_grid.py. It is no standard, and its numbers mean nothing.",
    "rows": [
        {"id": "kit/pace", "anchor": MADE_UP, "gives": {"name": "v", "dim": "length/time", "what": "a pace by the duty"},
         "takes": [{"name": "duty", "one_of": ["light", "heavy"], "what": "the duty"}],
         "table": {"down": {"by": "duty"}, "unit": "km/h", "cells": ["36", "15 m/s"]}}],
    "types": [
        {"type": "cell", "what": "a cell of a rig", "fields": [
            _kit_field("low", dim="temperature", may_be="negative", least="-40 degC"), _kit_field("spare", dim="dimensionless", whole=True, may_be="zero"),
            _kit_field("station", dim="length", may_be="negative"), _kit_field("resistance", dim="resistance", optional=True),
            _kit_field("limit", dim="dimensionless/time", optional=True), _kit_field("seal", one_of=["none", "full"], optional=True),
            _kit_field("maker", one_of=["a", "b"], optional=True), _kit_field("mass", dim="mass")],
         "needs": [{"le": ["low", ["q", "60", "degC"]], "why": "made up: a field that may be negative, in a need"}]},
        {"type": "rig", "what": "a rig of two cells", "fields": [
            _kit_field("duty", one_of=["light", "heavy"], signed=True), _kit_field("count", dim="dimensionless", whole=True, signed=True, least="2"),
            _kit_field("mode", one_of=["day", "night"]), _kit_field("speed", dim="dimensionless/time"), _kit_field("pace", dim="length/time"),
            _kit_field("charge", dim="current*time"), _kit_field("run", dim="time"), _kit_field("reach", dim="length"), _kit_field("density", dim="mass/length^3"),
            _kit_field("rate", dim="force/length"), _kit_field("torque", dim="moment"), _kit_field("power", dim="power"),
            _kit_field("cells", type="cell", **{"as": ["front", "rear"]})],
         "loads": [_kit_field("air", dim="temperature"), _kit_field("shift", dim="length", may_be="negative"), _kit_field("weight", dim="mass", least="0 g")],
         "needs": [{"le": [["add", "front.station", "rear.station"], "reach"], "why": "made up: two stations that may be behind the datum"},
                   {"lt": ["speed", ["mul", "4", "front.limit"]], "why": "made up: a limit that a cell may leave unstated"}]}],
    "grid": [{"type": "rig" if name.startswith("rig.") else "cell", "mechanism": name, "what": name, "anchor": MADE_UP, **more} for name, more in (
        ("rig.class", {}), ("rig.count", {}), ("rig.cold", {}), ("rig.speed", {}),
        ("rig.sealed", {"unless": {"when": ["is", "rear.seal", "full"], "why": "made up: a key that a cell may leave unstated"}}),
        ("rig.share", {}), ("rig.centre", {}), ("rig.energy", {}), ("rig.dense", {}), ("rig.stiff", {}), ("rig.twist", {}), ("rig.heat", {}), ("rig.carry", {}),
        ("rig.bare", {}), ("rig.night", {"unless": {"when": ["is", "mode", "day"], "why": "made up"}}),
        ("cell.mass", {}), ("cell.temp", {}), ("cell.spare", {}), ("cell.limit", {}), ("cell.ohm", {}), ("cell.sealed", {}))],
    "rules": [
        # A key and a count that the card states: in a `when`, a `requires`, a key of a table, and as a number.
        _kit_rule("class", "rig.class", when=["is", "duty", "heavy"], requires=["is", "mode", "day"]),
        _kit_rule("count", "rig.count", lt=[["mul", "count", ["q", "2", "oz"]], ["q", "0.5", "lb"]]),
        _kit_rule("pace", "rig.sealed", le=["pace", ["row", "kit/pace", {"duty": "duty"}]]),
        _kit_rule("carry", "rig.carry", le=[["load", "weight"], ["mul", "count", ["q", "10", "lb"]]]),
        # Quantities at and under zero, a quotient by a count that may be zero, and a load of either sign.
        _kit_rule("cold", "rig.cold", le=["front.low", ["load", "air"]]),
        _kit_rule("share", "rig.share", le=[["div", "reach", "front.spare"], ["q", "1", "mile"]]),
        _kit_rule("centre", "rig.centre", le=[["abs", ["add", "front.station", "rear.station", ["load", "shift"]]], ["q", "1", "ft"]]),
        # A quantity and a key that a cell may leave unstated: in a side, in a `when` and in the `unless` of rig.sealed.
        _kit_rule("speed", "rig.speed", lt=["speed", "front.limit"]),
        _kit_rule("heat", "rig.heat", when=["is", "rear.seal", "none"], le=[["mul", "rear.resistance", ["q", "1", "A"], ["q", "1", "A"]], "power"]),
        # The units, and `lt` beside `le` on their edges.
        _kit_rule("energy", "rig.energy", le=[["mul", "charge", ["q", "1", "V"]], ["mul", "power", "run"]]),
        _kit_rule("dense", "rig.dense", le=["density", ["q", "2", "g/cm3"]]),
        _kit_rule("stiff", "rig.stiff", le=[["q", "1", "N/mm"], "rate"]),
        _kit_rule("twist", "rig.twist", lt=["torque", ["q", "1", "lbf_ft"]]),
        _kit_rule("mass", "cell.mass", le=["mass", ["q", "1", "lb"]]),
        # Each field of a cell read by a rule of the cell itself, so that a rig that states them all has no field that nothing reads.
        _kit_rule("temp", "cell.temp", le=["low", ["q", "30", "degC"]]),
        _kit_rule("spare", "cell.spare", le=["spare", "3"]),
        _kit_rule("limit", "cell.limit", le=[["q", "1", "Hz"], "limit"]),
        _kit_rule("ohm", "cell.ohm", lt=["resistance", ["q", "100", "kohm"]]),
        _kit_rule("sealed", "cell.sealed", when=["is", "maker", "a"], requires=["is", "seal", "none"])],
}
"""A deck for what three more families asked of the language: a key and a count that the
card states, quantities at and under zero, fields a part may leave unstated, the units read
since 2026-11-11, and rules that state `lt`. `rig.bare` has no rule, for a waiver to rest."""


KIT_SEED = 485
"""The seed of the rig that a damaged KIT deck is checked with (`_decks`): a calm rig that
carries its three loads in two cases, 28 of whose cells are proved, with one line, the one
that has no rule, left open."""


def kit(rng: random.Random, n: int) -> Draft:
    """A rig of KIT with its two cells: its numbers on and beside the edges of its rules, in
    the units read since 2026-11-11, with fields left unstated, at zero and under it, and a
    card that states its duty and its count and waives lines that have rules and lines that
    have none."""
    d = Draft(f"kit-{n}")
    # Three rigs in five are calm: each number is one that keeps every rule, but for one in twelve. The others take any value of the
    # lists, which go on to the edges of the rules and past them, so nearly all of those fail somewhere.
    calm = rng.random() < 0.6

    def pick(values: list[str], keep: int = 2) -> str:
        """One of the values. The first `keep` of a list keep every rule that reads them."""
        return rng.choice(values[:keep] if calm and rng.random() < 0.92 else values)

    for name in ("c1", "c2"):
        d.parts.append(("cell", name, [
            ["low", pick(["-10 degC", "-40 degC", "-35/9 degC", "0 degC", "5 degC", "25 degC", "31 degC"])],
            ["spare", pick(["1", "2", "3", "0", "4"])],
            ["station", pick(["-5 mm", "0 mm", "5 mm", "-0.5 ft", "-1 ft", "100 mm"])],
            ["resistance", pick(["20 mohm", "0.5 ohm", "unstated", "40 ohm", "1.2 kohm", "101 kohm"])],
            ["limit", pick(["150 Hz", "200 Hz", "9001 rpm", "unstated", "9000 rpm", "149 Hz", "9000.001 rpm", "59 rpm"])],
            ["seal", pick(["none", "none", "full", "unstated"])],
            ["maker", pick(["a", "a", "b", "unstated"])],
            ["mass", pick(["400 g", "16 oz", "1 lb", "453.59237 g", "17 oz", "0.5 kg", "453.6 g"])]]))
    duty, count, mode = rng.choice(["light", "heavy"]), pick(["2", "3", "4", "5"]), pick(["day", "day", "night"])
    lines = [
        ["duty", "given rig.duty"], ["count", "given rig.count"], ["mode", mode],
        ["speed", pick(["100 Hz", "60 rpm", "8999.999 rpm", "9000 rpm", "150 Hz", "149.9 Hz", "151 Hz"])],
        ["pace", pick(["5 m/s", "10 m/s", "36 km/h", "19 knot", "22 mph", "36.1 km/h", "20 knot", "23 mph", "15 m/s", "54 km/h", "54.001 km/h", "29 knot", "30 knot"])],
        ["charge", pick(["2200 mAh", "2.2 Ah", "5 Ah", "13333 mAh", "13334 mAh", "40 Ah", "10 A2s"])],
        ["run", pick(["12 min", "0.2 h", "1 h", "11 min", "660000 ms", "30 s"])],
        ["reach", pick(["0.5 mile", "1 km", "100 ft", "1 mile", "1609.344 m", "1609.345 m", "2 mile", "3 mile"])],
        ["density", pick(["1.6 g/cm3", "2 g/cm3", "2000 kg/m3", "2000.1 kg/m3", "7.85 g/cm3"])],
        ["rate", pick(["3 N/mm", "1 N/mm", "1.001 N/mm", "0.999 N/mm"])],
        ["torque", pick(["11 lbf_in", "1 Nm", "11.999 lbf_in", "12 lbf_in", "1 lbf_ft", "2 Nm", "0.001 kip_ft"])],
        ["power", pick(["1.2 kW", "1200 W", "40 W", "0.04 kW", "10 mW"])],
        ["cells", rng.choice(["c1 c2", "c1 c2", "c2 c1"])]]
    # The charge is no charge in A2s, a current squared for a time: such a design is refused for its dimension.
    d.givens["rig.duty"], d.givens["rig.count"] = f"is {duty}", f"is {count}"
    if rng.random() < 0.3:      # a key that the type leaves to either, stated by the card
        lines[2][1], d.givens["rig.mode"] = "given rig.mode", f"is {mode}"
    if rng.random() < 0.2:      # a pace the card bounds, which may straddle the limit of its duty
        lines[4][1], d.givens["rig.pace"] = "given rig.pace", rng.choice(["in [9 m/s, 10 m/s]", "in [36 km/h, 36 km/h]", "in [30 km/h, 40 km/h]", "in [14 m/s, 15 m/s]", "in [19 knot, 30 knot]"])
    if rng.random() < 0.15:     # a count of spares the card states for a cell, and a low temperature it bounds
        d.lines("c1")[1][1], d.givens["c1.spare"] = "given c1.spare", rng.choice(["is 0", "is 2", "is 1"])
    if rng.random() < 0.15:
        d.lines("c2")[0][1], d.givens["c2.low"] = "given c2.low", rng.choice(["in [-10 degC, 0 degC]", "in [-40 degC, -40 degC]", "in [-20 degC, 30 degC]"])
    d.parts.append(("rig", "rig", lines))
    for case in rng.choice([["calm"], ["calm", "gale"]] if calm else [[], ["calm"], ["calm"], ["calm", "gale"], ["calm", "gale"]]):
        entries = []
        if calm or rng.random() < 0.85:
            entries.append(f"on rig air in {pick(['[-10 degC, 40 degC]', '[-35/9 degC, 590/9 degC]', '[5 degC, 25 degC]', '[0 degC, 0 degC]', '[-20 degC, 0 degC]', '[-40 degC, -40 degC]'])}")
        if calm or rng.random() < 0.7:
            entries.append(f"on rig shift in {pick(['[-2 mm, 2 mm]', '[0 mm, 0 mm]', '[-0.5 ft, 0.5 ft]', '[-1 ft, -1 ft]', '[1 ft, 1 ft]', '[-400 mm, -300 mm]'])}")
        if calm or rng.random() < 0.6:
            entries.append(f"on rig weight in {pick(['[0 g, 20 lb]', '[0 g, 0 g]', '[0 oz, 320 oz]', '[0 lb, 40 lb]', '[30 lb, 30 lb]', '[40.001 lb, 41 lb]'])}")
        if entries or rng.random() < 0.5:
            d.loads[case] = entries
    # A waiver for a line with no rule, for lines whose rules prove, refute or have no answer, for a line that cannot arise, and for all at once.
    every = [a["mechanism"] for a in KIT["grid"] if a["type"] == "rig"]
    d.waivers = [(m, "rig") for m in rng.choice([[], [], ["rig.bare"], ["rig.bare", "rig.night"], ["rig.speed", "rig.count"], ["rig.cold", "rig.carry", "rig.centre"],
                                                 ["rig.sealed", "rig.heat", "rig.share"], every, every, rng.sample(every, 5)])]
    if rng.random() < 0.1:
        d.waivers.append(("cell.mass", rng.choice(["c1", "c2"])))
    return d


def kit_damage(rng: random.Random, d: Draft) -> None:
    """Change a draft of KIT in one way that the grid may refuse: a field of the card's that
    the design writes, a statement the key lacks or of the wrong kind, a field that is not
    optional left unstated, a number at or under zero where its field does not permit it,
    and a unit of another dimension. Some of these the language refuses first."""
    rig, cell = d.lines("rig"), d.lines(rng.choice(["c1", "c2"]))
    line = {l[0]: l for l in rig}

    def design_writes() -> None:
        which = rng.choice(["duty", "count"])
        line[which][1] = d.givens.pop(f"rig.{which}")[3:]

    def design_writes_too() -> None:      # the card states it as well: the language refuses a statement that no part reads
        line["duty"][1] = "light"

    def not_stated() -> None:      # the language refuses a given the card does not state
        d.givens.pop(rng.choice(["rig.duty", "rig.count"]))

    def wrong_statement() -> None:
        which = rng.choice(["duty", "count"])
        d.givens[f"rig.{which}"] = rng.choice(["is medium", "is 3", 'is "light "', "in [2, 3]", "in [4, 4]"] if which == "duty"
                                               else ["is four", 'is "4"', "is 1", "is 0", "is -3", "in [4, 4]", "in [2, 3]", "is heavy"])

    def other_statement() -> None:      # the rig reads what the card states for another part, and the card states nothing for the rig
        d.givens["c1.duty"] = d.givens.pop("rig.duty")
        line["duty"][1] = "given c1.duty"

    def bound_as_statement() -> None:
        line["power"][1], d.givens["rig.power"] = "given rig.power", rng.choice(["is 40", "is forty"])

    def must_be_stated() -> None:
        chosen = rng.choice([line["speed"], line["mode"], line["cells"], cell[0], cell[7], cell[1]])
        chosen[1] = rng.choice(["unstated", "unstated", '"unstated"'])

    def unstated_twice() -> None:
        rng.choice([cell[3], cell[4], cell[5]])[1] = rng.choice(["unstated unstated", '"unstated"', "unstated 5 Hz", "none unstated"])

    def under_zero() -> None:
        chosen, value = rng.choice([(cell[7], "0 g"), (cell[7], "-1 lb"), (line["reach"], "0 mile"), (line["reach"], "-1 ft"), (cell[1], "-1"), (cell[0], "-300 degC"),
                                    (cell[0], "-41 degC"), (cell[0], "-273.15 degC"), (line["speed"], "0 rpm"), (line["run"], "-1 min"), (line["power"], "0 kW")])
        chosen[1] = value

    def load_under_floor() -> None:
        d.loads[rng.choice(["calm", "extra"])] = [rng.choice(["on rig weight in [-1 lb, 1 lb]", "on rig air in [-274 degC, 0 degC]", "on rig shift in [-1 mile, 1 mile]",
                                                              "on rig air in [-273.15 degC, 0 degC]", "on c1 weight in [0 g, 1 g]"])]

    def wrong_dimension() -> None:
        chosen, value = rng.choice([(line["speed"], "5 m/s"), (line["pace"], "5 Hz"), (line["charge"], "5 A"), (line["run"], "5 rpm"), (line["density"], "5 kg"),
                                    (line["rate"], "5 N"), (line["torque"], "5 lbf"), (line["power"], "5 Ah"), (line["reach"], "5 mph"), (cell[7], "5 lbf")])
        chosen[1] = value

    def no_such_unit() -> None:      # the language refuses these
        rng.choice([line["speed"], line["pace"], line["run"], cell[0]])[1] = rng.choice(["5 K", "5 degF", "5 kph", "5 m / s", "5 hr", "5 kg/m^3", "5 mm/s"])

    way = rng.choice([design_writes, design_writes, design_writes_too, not_stated, wrong_statement, wrong_statement, other_statement, bound_as_statement, must_be_stated,
                      must_be_stated, unstated_twice, under_zero, under_zero, load_under_floor, wrong_dimension, no_such_unit])
    way()
    d.damage.append(way.__name__)


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

    def environment() -> None:
        d.environment = rng.choice(["indoor_dry", "marine_c5"])

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
            bad_joins, joined_twice, stray, bad_load, bad_waiver, claim, environment, param, two_values, no_value, given_twice]
    way = rng.choice(ways)
    way()
    d.damage.append(way.__name__)


def draft(seed: int, n: int) -> Draft:
    rng = random.Random(f"{seed}/{n}")
    d = rng.choice([lap, lap, strips, strips, ops, kit, kit])(rng, n)
    if d.name.startswith("kit"):
        for _ in range(rng.choice([0, 0, 0, 1, 1])):
            kit_damage(rng, d)
        return d
    for _ in range(0 if d.name.startswith("ops") else rng.choice([0, 0, 0, 1, 1, 2])):
        damage(rng, d)
    return d


ODD = ["", "pi", "2", "x.y", "load pull", "load current", "@0", "1e3", " 5", "1_000", "+5", "-0", "1/0", "3/4", "1,000", "1 1/2", "0.5", "-3", "7/2", "100",
       "length", "force", "area", "dimensionless", "length^2", "force/length", "mm", "A", "kN", "upper", "lower", "a", "b", "near", "far", "fit", "close",
       "unread", "odd�", "١ ١/٢ mm", "5 mm ", "length^٢",
       "length^4", "mm^4", "5 mm^4", "5 mm^3", "5 mm^2", "5 mm^5", "5 mm^1", "5 mm^04", "5 kN^2", "5 mm^٤", "1 inch^4", "0 mm^4", "left.finish", "right.i", "left.t",
       "caps.finish", "left", "caps", "low", "high", "mid", "grade", "ops/class", "ops/table", "0", "0/5", "requires", "case", "row", "key", "by",
       "zero", "negative", "positive", "unstated", "optional", "signed", "true", "5 rpm", "150 Hz", "3 m/s", "3 m / s", "36 km/h", "2200 mAh", "1 Ah", "12 min", "1 h",
       "1 lb", "16 oz", "1 mile", "2 g/cm3", "2000 kg/m3", "1 N/mm", "1 lbf_ft", "12 lbf_in", "1.2 kW", "5 K", "5 degF", "-10 degC", "0 degC", "0 g", "-1 mm", "0 rpm",
       "rpm", "m/s", "mAh", "min", "h", "K", "lt", "le", "dimensionless/time", "current*time", "length/time", "mass/length^3", "force/length", "temperature",
       "front.limit", "rear.seal", "front.spare", "duty", "count", "mode", "light", "heavy", "day", "night", "full", "none", "kit/pace"]
"""Texts to put where a deck has another: numbers the two readers might read apart, and names that are something else too."""
KEYS = ["note", "what", "dim", "type", "as", "least", "unless", "when", "closed", "at", "bands", "one_of", "range", "jumps", "unit", "rises", "falls",
        "let", "where", "loads", "across", "table", "is", "cases", "needs", "requires", "le", "lt", "why", "gives", "down", "cells",
        "may_be", "optional", "signed", "whole"]


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
                          "a wide row applied", "a condition that asks loaded", "a name no cell holds", "a requirement no part can break",
                          "a flag on a field", "a flag on a field", "le for lt"])
        rules = [r for r in body["rules"] if isinstance(r, dict)] if isinstance(body.get("rules"), list) else []
        naming = [r for r in body["rows"] if isinstance(r, dict) and isinstance(r.get("gives"), dict) and isinstance(r["gives"].get("one_of"), list)] if isinstance(body.get("rows"), list) else []
        if way == "a name no cell holds" and naming:
            # A row gives one name more, which none of its cells holds. Each `case` over the row gets an expression for it, the one of
            # another name, so the name itself is what is wrong: no part can have it, and both refuse the row.
            row = rng.choice(naming)
            row["gives"]["one_of"] = [*row["gives"]["one_of"], "spare"]
            for _, node in nodes:
                if isinstance(node, list) and len(node) == 3 and node[0] == "case" and isinstance(node[1], list) and node[1][:2] == ["row", row.get("id")] and isinstance(node[2], dict) and node[2]:
                    node[2]["spare"] = copy.deepcopy(next(iter(node[2].values())))
            done.append(way)
            continue
        if way == "a name no cell holds":
            continue
        requiring = [r for r in rules if "requires" in r]
        if way == "a requirement no part can break" and requiring:
            # What a rule requires, or its opposite; what its `when` says already; or both at once. Each is empty, and both refuse the deck.
            chosen = rng.choice(requiring)
            old = chosen["requires"]
            chosen["requires"] = rng.choice([["or", old, ["not", old]], ["and", old, ["not", old]], chosen.get("when", ["or", old, ["not", old]])])
            done.append(way)
            continue
        fields = [f for t in body.get("types", []) if isinstance(t, dict) for f in [*t.get("fields", []), *t.get("loads", [])] if isinstance(f, dict)] if isinstance(body.get("types"), list) else []
        if way == "a flag on a field" and fields:
            # One of the marks a field may carry, with a value it may or may not take there: both readers hold a flag to true or false,
            # `may_be` to its two words, and each to the fields it belongs on.
            key, value = rng.choice([("optional", True), ("optional", False), ("optional", "yes"), ("optional", 1), ("signed", True), ("signed", "true"), ("signed", 0),
                                     ("may_be", "zero"), ("may_be", "negative"), ("may_be", "positive"), ("may_be", True), ("may_be", None),
                                     ("least", "0 mm"), ("least", "-1 degC"), ("whole", True)])
            rng.choice(fields)[key] = value
            done.append(way)
            continue
        if way == "le for lt" and rules:
            # A rule that states `le` states `lt`, or the other way round, or both: the cells of an honest design may change, and both read it alike.
            chosen = rng.choice(rules)
            if "le" in chosen and rng.random() < 0.7:
                chosen["lt"] = chosen.pop("le")
            elif "lt" in chosen and rng.random() < 0.7:
                chosen["le"] = chosen.pop("lt")
            else:
                chosen["lt"] = chosen.get("le", chosen.get("lt", ["1", "2"]))
                chosen["le"] = chosen["lt"]
            done.append(way)
            continue
        if way in ("a requirement no part can break", "a flag on a field", "le for lt"):
            continue
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
        elif way == "a condition that asks loaded" and rules:
            # `loaded` is no condition any more: alone, joined to the condition that was there, in a `requires` or in an `unless`.
            asks = ["loaded", rng.choice(["push", "twist", "drag", "current", "pull", "nobody"])]
            lines = [a for a in body.get("grid", []) if isinstance(a, dict)] if isinstance(body.get("grid"), list) else []
            where = rng.choice(["when", "when", "requires", "unless"])
            if where == "unless" and lines:
                rng.choice(lines)["unless"] = {"when": asks, "why": "made up"}
            else:
                chosen = rng.choice(rules)
                key = "requires" if where == "requires" and "requires" in chosen else "when"
                old = chosen.get(key)
                chosen[key] = asks if old is None else rng.choice([asks, ["and", old, asks], ["or", ["not", asks], old], ["not", asks]])
        elif way in ("a where with no item", "two rules that end alike", "a line named unread", "a condition that asks loaded"):
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
        _STATE["kit"] = grid.read_deck(json.dumps(KIT))
        _STATE["honest"] = {"lap": (path.with_suffix(".card").read_text(encoding="utf-8"), path.read_text(encoding="utf-8")),
                            # A seed whose bar keeps every need and carries its loads, so that nine of the ten lines its
                            # rules answer are proved or refuted, and a damaged deck has something to change.
                            "strips": (CARD, DESIGN), "ops": ops(random.Random(101), 0).texts(),
                            # A seed whose rig keeps its needs, states every field its rules read and carries its three loads.
                            "kit": kit(random.Random(KIT_SEED), 0).texts()}
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
        name = rng.choice(["strips", "strips", "ops", "ops", "lap", "kit", "kit"])
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
