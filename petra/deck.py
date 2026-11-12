"""Rules as data: a row of a deck, what it means, and whether to admit it. Untrusted.

A row is one equation or one table of a standard written as data (docs/deck.md): what it
gives, what it takes, each with a dimension, and either its expression, by case where the
standard splits it, or its cells. This module reads a row, checks its dimensions,
evaluates it exactly, and runs the acceptance check a row passes before it enters a deck:

    units        every sum, comparison, result and cell has one dimension
    examples     the row reproduces each worked example given with it
    continuity   where two cases meet they give one value, unless the row says those two jump
    shape        for a table: it rises or falls along each side the row says it does
    second       a transcription made without sight of this one gives the same values

    python -m petra.deck ROWS.json [--examples FILE.json] [--second ROWS.json]

A row proves nothing by itself. A rule of a deck binds it to the parts of a design
(petra/grid.py), and the kernel reads the deck's rows a second time to write the tape of
each rule itself (kernel/Petra/Deck.lean).
"""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import random
import re
import sys
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Iterator, Mapping

from .kernel import (Abs, Add, Const, Cos, Div, Exp, Interval, KernelArithmeticError, Ln, Max, Min, Mul, Neg, Pi, PowInt, Sqrt, Sym, enclose)
from .units import (AREA, CURRENT, DIMENSIONLESS, ENERGY, FORCE, LENGTH, MASS, POWER, RESISTANCE, STRESS, TEMPERATURE, TIME, VOLTAGE, Dim,
                    UnitError, parse_quantity)

Vector = tuple[Fraction, ...]
"""A dimension as exponents of (m, kg, s, A, degC). A square root halves them, so they are fractions."""

BASES = ("m", "kg", "s", "A", "degC")
NAMED: Mapping[str, Dim] = {"dimensionless": DIMENSIONLESS, "length": LENGTH, "area": AREA, "force": FORCE, "stress": STRESS, "mass": MASS,
                            "time": TIME, "temperature": TEMPERATURE, "energy": ENERGY, "moment": ENERGY, "current": CURRENT,
                            "voltage": VOLTAGE, "power": POWER, "resistance": RESISTANCE}
"""The dimension names a row may write. `moment` is a force times a length, as energy is."""

ROW_KEYS = frozenset({"id", "anchor", "gives", "takes", "is", "cases", "jumps", "table"})
SAMPLES = 96
"""How many points the continuity and second checks try. A row of a standard has a handful
of inputs, and two different formulas of that size agree on this many points by accident
about never."""
CLOSE = Fraction(1, 10 ** 9)
"""Two values this near, relative to the larger, are one value: a square root, a logarithm
and an exponential are enclosed and not exact."""
MEET = Fraction(1, 100)
"""Two cases meet when they differ by at most this where one hands over to the other. A
standard's constants are rounded, so its cases meet to a few parts in a thousand."""
ROUNDED = Fraction(1, 200)
"""A worked example reproduces within this, or within half a unit of its last printed
digit when that is more: an example rounds what it carries from line to line."""


class RowError(ValueError):
    """Data that is not a row: a missing or unknown key, an operator the language lacks, or
    a name the row does not take."""


def only(body: Any, allowed: tuple[str, ...], what: str) -> None:
    """Refuse a key that an object of a deck does not have. A key that was skipped would be a
    misspelled one, read as if it were left out, so its default would stand in its place."""
    if not isinstance(body, dict):
        raise RowError(f"{what} is not an object")
    unknown = sorted(set(body) - set(allowed))
    if unknown:
        raise RowError(f"{what}: {', '.join(unknown)} is not a key here: it has {', '.join(allowed)}")


ANCHOR_KEYS = ("standard", "clause", "equation", "table", "page")


def anchored(body: Any, what: str) -> dict[str, str]:
    """The anchor of a row, a grid line or a rule: `standard` and `clause`, each a text that
    is not empty, and `equation`, `table` and `page` where given, each a text."""
    only(body, ANCHOR_KEYS, what)
    if not all(isinstance(v, str) for v in body.values()) or not body.get("standard") or not body.get("clause"):
        raise RowError(f"{what} names its standard and its clause, and what it names is text")
    return dict(body)


def replaced(body: Any) -> bool:
    """Whether a text or a key holds U+FFFD or half a surrogate pair. The kernel's JSON
    reader reads the half as U+FFFD, so it refuses a file that holds either (docs/format.md)."""
    if isinstance(body, str):
        return any(c == "�" or "\ud800" <= c <= "\udfff" for c in body)
    if isinstance(body, dict):
        return any(replaced(k) or replaced(v) for k, v in body.items())
    return isinstance(body, list) and any(map(replaced, body))


def _vector(dim: Dim) -> Vector:
    return tuple(Fraction(getattr(dim, base)) for base in BASES)


NONE = _vector(DIMENSIONLESS)


def dimension(text: str) -> Vector:
    """`force`, `length^3` or `force/length`: names of NAMED with whole powers, multiplied
    or divided from left to right."""
    out, sign = NONE, 1
    for token in re.split(r"([*/])", text.replace(" ", "")):
        if token in "*/" and token:
            sign = 1 if token == "*" else -1
            continue
        name, _, power = token.partition("^")
        if name not in NAMED or not re.fullmatch(r"-?[0-9]+", power or "1"):
            raise RowError(f"{text!r} is not a dimension: it is {', '.join(NAMED)}, with ^N, * and /")
        out = tuple(a + sign * int(power or 1) * b for a, b in zip(out, _vector(NAMED[name])))
    return out


def show(v: Vector) -> str:
    for name, dim in NAMED.items():
        if _vector(dim) == v:
            return name
    return " ".join(f"{base}^{power}" for base, power in zip(BASES, v) if power)


BLANK = " \t\r\n"
"""What is dropped around a value and around its unit, as the kernel drops it (kernel/Petra/Quantity.lean, `strip`)."""


def quantity(text: str, what: str) -> tuple[Fraction, Vector]:
    """`0.75 inch` as an exact SI value and its dimension. A number alone has none. A comma
    is read only between thousands, as in 29,000: a decimal is written with a point. A
    whole number and a fraction, `1 1/8 inch`, is their sum, as a standard prints it."""
    mixed = re.fullmatch(r"([0-9]+) ([0-9]+)/([0-9]+)( .*)?", str(text).strip(BLANK), re.DOTALL)
    if mixed and int(mixed[3]):
        whole, top, bottom = (int(mixed[n]) for n in (1, 2, 3))
        text = f"{whole * bottom + top}/{bottom}{mixed[4] or ''}"
    number, _, unit = str(text).strip(BLANK).partition(" ")
    if "," in number and not re.fullmatch(r"[+-]?[0-9]{1,3}(,[0-9]{3})+(\.[0-9]+)?", number):
        raise RowError(f"{what}: {number!r} has a comma that is not between thousands; write a decimal with a point")
    try:
        q = parse_quantity(number.replace(",", ""), unit.strip(BLANK) or None)
    except UnitError as exc:
        raise RowError(f"{what}: {exc}") from None
    return q.value.lo, _vector(q.dim)


@dataclass(frozen=True)
class Case:
    when: tuple | None      # a condition, or None for the case that holds otherwise
    expr: Any
    dim: Vector


@dataclass(frozen=True)
class Input:
    """A quantity with its dimension and the range a design's value falls in, or a key:
    one of a few names, such as a grade or a hole type, which only a table reads."""

    dim: Vector | None = None
    lo: Fraction = Fraction(0)
    hi: Fraction = Fraction(0)
    keys: tuple[str, ...] = ()

    @property
    def kind(self) -> tuple:
        """What another transcription's input must share to be this one: the dimension, or
        for a key how many names it has. Two transcribers name a key's values in their own
        words, so a key's names are matched by their order, which is the standard's."""
        return ("key", len(self.keys)) if self.keys else ("quantity", self.dim)


@dataclass(frozen=True)
class Axis:
    """One side of a table: the input it reads and the places along it. A key has one
    place for each of its names. A quantity is read in `bands`, each holding its upper end
    and not its lower when `upper`, and the other way round when not, or at the listed
    values `at` and nowhere else. The last band has no upper end when the standard gives
    it none."""

    by: str
    keys: tuple[str, ...] = ()
    bands: tuple[tuple[Fraction, Fraction | None], ...] = ()
    upper: bool = True
    at: tuple[Fraction, ...] = ()

    @property
    def places(self) -> int:
        return len(self.keys or self.at or self.bands)

    def place(self, x: Any) -> int | None:
        if self.keys or self.at:
            listed = self.keys or self.at
            return listed.index(x) if x in listed else None
        for n, (lo, hi) in enumerate(self.bands):
            if (lo < x if self.upper else lo <= x) and (hi is None or (x <= hi if self.upper else x < hi)):
                return n
        return None

    def probes(self) -> list[Any]:
        """Values that reach every place and each side of every band's ends, and for a
        list of values one between each two, where the table gives nothing."""
        if self.keys:
            return list(self.keys)
        if self.at:
            return [*self.at, *((a + b) / 2 for a, b in zip(self.at, self.at[1:]))]
        out: list[Fraction] = []
        for lo, hi in self.bands:
            width = (hi - lo) if hi is not None else abs(lo) or Fraction(1)
            out += [lo, lo + width / 1000, lo + width / 2, *([hi - width / 1000, hi] if hi is not None else [lo + 3 * width])]
        return list(dict.fromkeys(out))


@dataclass(frozen=True)
class Table:
    """Cells by place: `cells[down][across]`, with one column when the table has one side.
    None is a cell the standard leaves empty."""

    axes: tuple[Axis, ...]
    cells: tuple[tuple[Fraction | None, ...], ...]
    rises: frozenset
    falls: frozenset

    def cell(self, point: Mapping[str, Any]) -> Fraction | None:
        at = [axis.place(point[axis.by]) for axis in self.axes]
        return None if None in at else self.cells[at[0]][at[1] if len(at) == 2 else 0]

    def lines(self, side: int) -> list[tuple[Fraction | None, ...]]:
        """The cells in the lines that run along one side: columns along the first, rows
        along the second."""
        return list(self.cells) if side == 1 else list(zip(*self.cells))


@dataclass(frozen=True)
class Row:
    """One equation, with `cases`, or one table. `problems` are its dimension errors,
    found when it was read. A row that gives a name has `names`, the names in the
    standard's order, a table whose cells are those names, and no `dim`."""

    id: str
    anchor: Mapping[str, str]
    gives: str
    dim: Vector | None
    takes: Mapping[str, Input]
    cases: tuple[Case, ...]
    jumps: Mapping[frozenset, str]      # two case numbers, from 0, to why they do not meet
    problems: tuple[str, ...]
    table: Table | None = None
    names: tuple[str, ...] = ()


@dataclass(frozen=True)
class Example:
    """A worked use of a row in print: the inputs, the printed result and how near a
    reproduction must come, all in SI, with the result as printed for messages."""

    anchor: str
    given: Mapping[str, Any]      # a quantity in SI, or a key's name
    gives: Fraction
    within: Fraction
    printed: str


@dataclass(frozen=True)
class Check:
    """One part of the acceptance check on one row: `pass`, `fail`, or `none` when there
    was nothing to check, which is a weaker row and not a wrong one."""

    name: str
    outcome: str
    detail: str = ""


class _Reader:
    """Expressions and conditions of one row, as kernel terms with their dimensions."""

    def __init__(self, takes: Mapping[str, Input]) -> None:
        self.takes = takes
        self.problems: list[str] = []

    def same(self, op: str, dims: list[Vector]) -> Vector:
        # Each is compared with the first. A set of them would be keyed by their exponents,
        # which a deck writes as whole numbers of any length, and Python hashes a whole number
        # by its remainder: a deck could give many dimensions one hash.
        if any(d != dims[0] for d in dims[1:]):
            self.problems.append(f"{op} of {' and '.join(show(d) for d in dims)}")
        return dims[0]

    def bare(self, op: str, dim: Vector) -> None:
        if dim != NONE:
            self.problems.append(f"{op} of a {show(dim)}, which must be a plain number")

    def expr(self, node: Any) -> tuple[Any, Vector]:
        if isinstance(node, str):
            if node == "pi":
                return Pi(), NONE
            if node in self.takes:
                if self.takes[node].keys:
                    raise RowError(f"{node} is a key, and only a table reads a key")
                return Sym(node), self.takes[node].dim
            try:
                return Const(parse_quantity(node, None).value.lo), NONE
            except ValueError:
                raise RowError(f"{node!r} is not a number, and the row does not take it") from None
        if not isinstance(node, list) or not node or not isinstance(node[0], str):
            raise RowError(f"{node!r} is not an expression: write a number, a name or [operator, ...]")
        op, args = node[0], node[1:]
        if op == "q" and len(args) == 2:
            value, dim = quantity(f"{args[0]} {args[1]}", "a constant")
            return Const(value), dim
        if op == "pow" and len(args) == 2:
            return self.power(*args)
        parts = [self.expr(a) for a in args]
        terms, dims = [p[0] for p in parts], [p[1] for p in parts]
        many = {"add": Add, "min": Min, "max": Max}
        one = {"neg": Neg, "abs": Abs}
        if op in many and terms:
            return many[op](tuple(terms)), self.same(op, dims)
        if op == "sub" and len(terms) == 2:
            return Add((terms[0], Neg(terms[1]))), self.same(op, dims)
        if op == "mul" and terms:
            return Mul(tuple(terms)), tuple(map(sum, zip(*dims)))
        if op == "div" and len(terms) == 2:
            return Div(*terms), tuple(a - b for a, b in zip(*dims))
        if op in one and len(terms) == 1:
            return one[op](terms[0]), dims[0]
        if op == "sqrt" and len(terms) == 1:
            return Sqrt(terms[0]), tuple(a / 2 for a in dims[0])
        if op in ("exp", "ln", "cos") and len(terms) == 1:
            self.bare(op, dims[0])
            return {"exp": Exp, "ln": Ln, "cos": Cos}[op](terms[0]), NONE
        raise RowError(f"{op!r} with {len(args)} arguments is not in the language")

    def power(self, base: Any, exponent: Any) -> tuple[Any, Vector]:
        """A whole power, a half power as a power of the root, and any other as
        exp(exponent ln base), which needs a base that is a plain number. A whole or a half
        power is at most 64, the largest the kernel raises a node to (kernel/Petra/Tape.lean)."""
        term, dim = self.expr(base)
        if isinstance(exponent, str) and exponent not in self.takes and exponent != "pi":
            try:
                n = parse_quantity(exponent, None).value.lo
            except ValueError:
                raise RowError(f"{exponent!r} is not a number, and the row does not take it") from None
            scaled = tuple(a * n for a in dim)
            if n.denominator <= 2:
                if abs(n.numerator) > 64:
                    raise RowError(f"the power {n} is over 64, the largest whole or half power")
                root = term if n.denominator == 1 else Sqrt(term)
                raised = PowInt(root, abs(n.numerator))
                return (raised if n > 0 else Div(Const(Fraction(1)), raised)), scaled
            self.bare(f"the power {n}", dim)
            return Exp(Mul((Const(n), Ln(term)))), scaled
        by, by_dim = self.expr(exponent)
        self.bare("an exponent", by_dim)
        self.bare("a power with an exponent that varies", dim)
        return Exp(Mul((by, Ln(term)))), NONE

    def cond(self, node: Any) -> tuple:
        if not isinstance(node, list) or not node:
            raise RowError(f"{node!r} is not a condition")
        op, args = node[0], node[1:]
        if op in ("le", "lt", "ge", "gt") and len(args) == 2:
            (a, da), (b, db) = self.expr(args[0]), self.expr(args[1])
            self.same(op, [da, db])
            return (op, a, b)
        if op in ("and", "or") and args:
            return (op, *(self.cond(a) for a in args))
        if op == "not" and len(args) == 1:
            return (op, self.cond(args[0]))
        raise RowError(f"{op!r} with {len(args)} arguments is not a condition")


def read(body: Any) -> Row:
    """A row from its JSON. Raises RowError for data that is not a row. Dimension errors
    do not raise: they are the row's `problems`, which the units check reports."""
    if not isinstance(body, dict) or not isinstance(body.get("id"), str):
        raise RowError("a row is an object with an id")
    where = body["id"]
    unknown = sorted(set(body) - ROW_KEYS)
    if unknown or sum(key in body for key in ("is", "cases", "table")) != 1:
        raise RowError(f"{where}: a row has {', '.join(sorted(ROW_KEYS))}, with one of `is`, `cases` and `table`" + (f"; not {', '.join(unknown)}" if unknown else ""))
    try:
        anchor, gives = anchored(body["anchor"], "anchor"), body["gives"]
        only(gives, ("name", "dim", "what", "one_of"), "gives")
        if ("one_of" in gives) == ("dim" in gives):
            raise RowError("`gives` has `dim`, for a quantity, or `one_of`, for a name, and not both")
        takes = {}
        for t in body["takes"]:
            only(t, ("name", "what", "one_of") if "one_of" in t else ("name", "what", "dim", "range"), str(t.get("name")))
            if not isinstance(t.get("name"), str):
                raise RowError("an input has a name, a text")
            if "one_of" in t:
                keys = tuple(str(k) for k in t["one_of"])
                if len(set(keys)) != len(keys) or not keys or "dim" in t or "range" in t:
                    raise RowError(f"{t['name']} is a key: it has `one_of`, a list of different names, and no `dim` or `range`")
                takes[t["name"]] = Input(keys=keys)
                continue
            dim = dimension(t["dim"])
            (lo, lo_dim), (hi, hi_dim) = (quantity(end, f"the range of {t['name']}") for end in t["range"])
            if {lo_dim, hi_dim} != {dim} or not lo <= hi:
                raise RowError(f"the range of {t['name']} is two {show(dim)} values, the lower first")
            takes[t["name"]] = Input(dim, lo, hi)
        if len(takes) != len(body["takes"]):
            raise RowError("an input is named twice")
        if "one_of" in gives:
            names = gives["one_of"]
            if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names) or len(set(names)) != len(names):
                raise RowError("the `one_of` of `gives` is a list of different names")
            if "table" not in body or "jumps" in body or any(i.keys for i in takes.values()):
                raise RowError("a row that gives a name is a table with no jumps, and takes quantities and no key: its sides read them in `bands` or `at`")
            problems = []
            table = _naming(body["table"], takes, tuple(names), problems)
            return Row(where, anchor, str(gives["name"]), None, takes, (), {}, tuple(dict.fromkeys(problems)), table, tuple(names))
        if "table" in body:
            if "jumps" in body:
                raise RowError("a table has no jumps: it steps at every band")
            problems: list[str] = []
            table = _table(body["table"], takes, dimension(gives["dim"]), problems)
            return Row(where, anchor, str(gives["name"]), dimension(gives["dim"]), takes, (), {}, tuple(dict.fromkeys(problems)), table)
        if any(i.keys for i in takes.values()):
            raise RowError("an equation takes no key: only a table reads one")
        reader = _Reader(takes)
        written = body["cases"] if "cases" in body else [{"is": body["is"]}]
        cases = []
        for n, case in enumerate(written):
            only(case, ("when", "is"), f"case {n + 1}")
            if "is" not in case or ("when" not in case and n != len(written) - 1):
                raise RowError("a case has `when` and `is`, and only the last may leave `when` out")
            when = reader.cond(case["when"]) if "when" in case else None
            cases.append(Case(when, *reader.expr(case["is"])))
        for j in body.get("jumps", []):
            only(j, ("cases", "why"), "a jump")
        jumps = {}
        for j in body.get("jumps", []):
            # A number of a jump is one of the row's cases before it is a key. A file could list
            # whole numbers that share a hash, and a table keyed by them would cost the square
            # of their count.
            ends = [n - 1 for n in j["cases"]]
            if not all(isinstance(n, (int, float)) and 0 <= n < len(cases) and n == int(n) for n in ends) or len({int(n) for n in ends}) != 2 or not str(j["why"]):
                raise RowError("a jump names two of the row's cases by number, from 1, and says why")
            jumps[frozenset(int(n) for n in ends)] = str(j["why"])
        out = dimension(gives["dim"])
        problems = reader.problems + [f"case {n + 1} gives a {show(c.dim)}, and the row gives a {show(out)}" for n, c in enumerate(cases) if c.dim != out]
        return Row(where, anchor, str(gives["name"]), out, takes, tuple(cases), jumps, tuple(dict.fromkeys(problems)))
    except RowError as exc:
        raise RowError(f"{where}: {exc}") from None
    except (KeyError, TypeError, ValueError) as exc:
        raise RowError(f"{where}: not a row ({type(exc).__name__}: {exc})") from None


def _axes(body: Mapping[str, Any], takes: Mapping[str, Input], problems: list[str]) -> tuple[Axis, ...]:
    """The sides of a table: `down` and, for a table with two sides, `across`. Each input
    of the row is read by one of them, and by one only."""
    def axis(a: Mapping[str, Any]) -> Axis:
        name, i = a["by"], takes[a["by"]]
        if i.keys:
            only(a, ("by",), f"{name} is a key, so its side of the table has `by` alone")
            return Axis(name, keys=i.keys)
        only(a, ("by", "bands", "closed") if "bands" in a else ("by", "at"), f"the side that reads {name}")
        if ("bands" in a) == ("at" in a) or a.get("closed", "upper") not in ("upper", "lower"):
            raise RowError(f"the side that reads {name} has `bands` with `closed` upper or lower, or `at`")
        written = [x for band in a.get("bands", [a.get("at")]) for x in band]
        ends = [None if x is None else quantity(x, f"the side that reads {name}") for x in written]
        if any(end is not None and end[1] != i.dim for end in ends):
            problems.append(f"the side that reads {name} is not all {show(i.dim)}")
        values = [None if end is None else end[0] for end in ends]
        if "at" in a:
            # Each value is above the one before it, which says both that they are in order and
            # that each is there once. A set of them would be keyed by numbers the deck chooses.
            if any(x is None for x in values) or any(not lo < hi for lo, hi in zip(values, values[1:])):
                raise RowError(f"the values {name} is read at are in order, each once")
            return Axis(name, at=tuple(values))
        bands = tuple(zip(values[::2], values[1::2]))
        open_end = None in values[:-1] or any(len(band) != 2 for band in a["bands"])
        if open_end or any(hi is not None and lo >= hi for lo, hi in bands) or any(a_hi > b_lo for (_, a_hi), (b_lo, _) in zip(bands, bands[1:])):
            raise RowError(f"the bands of {name} are pairs, the lower end first, in order and none over another; only the last may have no upper end")
        return Axis(name, bands=bands, upper=a.get("closed", "upper") == "upper")

    axes = (axis(body["down"]), *([axis(body["across"])] if "across" in body else []))
    if sorted(a.by for a in axes) != sorted(takes):
        raise RowError("each input of a table is read by one of its sides, and by one only")
    return axes


def _naming(body: Mapping[str, Any], takes: Mapping[str, Input], names: tuple[str, ...], problems: list[str]) -> Table:
    """A table whose cells are names, for a row that gives one of `names`: the sides of any
    table, each read by a quantity, and `cells`, each one of the names or None where the
    standard gives none. It has no `unit` and neither rises nor falls: a name has no size."""
    only(body, ("down", "across", "cells"), "a table that gives a name")
    axes = _axes(body, takes, problems)
    known = set(names)
    lines = body["cells"] if len(axes) == 2 else [[c] for c in body["cells"]]
    cells = tuple(tuple(line) for line in lines)
    if any(c is not None and not (isinstance(c, str) and c in known) for line in cells for c in line):
        raise RowError(f"a cell of a table that gives a name is one of {', '.join(names)}, or null")
    if len(cells) != axes[0].places or any(len(line) != (axes[1].places if len(axes) == 2 else 1) for line in cells):
        raise RowError(f"the cells are {axes[0].places} lines" + (f" of {axes[1].places}" if len(axes) == 2 else "") + ", one for each place")
    # Every name the row gives is the name of a cell. A name that no cell holds is one no part can have, and a `case`
    # would still have to give it an expression, which nothing could reach.
    held = {c for line in cells for c in line if c is not None}
    lost = [n for n in names if n not in held]
    if lost:
        raise RowError(f"no cell holds {lost[0][:200]!r}, which `one_of` lists: each name the row gives is the name of a cell" + (f", and {len(lost) - 1} more are of none" if lost[1:] else ""))
    return Table(axes, cells, frozenset(), frozenset())


def _table(body: Mapping[str, Any], takes: Mapping[str, Input], out: Vector, problems: list[str]) -> Table:
    """A table from its JSON: `down` and, for a table with two sides, `across`, each an
    axis; `cells`; the `unit` of a cell that states none; and `rises` and `falls`."""
    only(body, ("down", "across", "cells", "unit", "rises", "falls"), "table")
    axes = _axes(body, takes, problems)
    unit = body.get("unit")

    def cell(text: Any) -> Fraction | None:
        if text is None:
            return None
        written = str(text).strip(BLANK)
        value, dim = quantity(written if " " in written or unit is None else f"{written} {unit}", "a cell")
        if dim != out:
            problems.append(f"a cell is a {show(dim)}, and the row gives a {show(out)}")
        return value

    lines = body["cells"] if len(axes) == 2 else [[c] for c in body["cells"]]
    cells = tuple(tuple(cell(c) for c in line) for line in lines)
    if len(cells) != axes[0].places or any(len(line) != (axes[1].places if len(axes) == 2 else 1) for line in cells):
        raise RowError(f"the cells are {axes[0].places} lines" + (f" of {axes[1].places}" if len(axes) == 2 else "") + ", one for each place")
    sides = [a.by for a in axes]
    # Each name is a side of the table, of which there are two at most, before any set is
    # made of them: a list of whole numbers that share a hash would make a slow set.
    if not all(isinstance(side, str) and side in sides for side in (*body.get("rises", []), *body.get("falls", []))):
        raise RowError("`rises` and `falls` name sides of the table, and no side is in both")
    rises, falls = frozenset(body.get("rises", [])), frozenset(body.get("falls", []))
    if rises & falls:
        raise RowError("`rises` and `falls` name sides of the table, and no side is in both")
    return Table(axes, cells, rises, falls)


# --- what a row means ------------------------------------------------------------------------------


def _holds(cond: tuple, box: Mapping[str, Interval]) -> bool | None:
    """Whether the condition holds at the point, or None where an enclosure cannot tell."""
    op = cond[0]
    if op == "not":
        inner = _holds(cond[1], box)
        return None if inner is None else not inner
    if op in ("and", "or"):
        found = [_holds(c, box) for c in cond[1:]]
        decides = op == "or"
        return decides if decides in found else None if None in found else not decides
    a, b = enclose(cond[1], box), enclose(cond[2], box)
    if op in ("ge", "gt"):
        a, b, op = b, a, {"ge": "le", "gt": "lt"}[op]
    if a.hi < b.lo or (op == "le" and a.hi <= b.lo):
        return True
    return False if a.lo > b.hi or (op == "lt" and a.lo >= b.hi) else None


def active(row: Row, point: Mapping[str, Fraction]) -> int | None:
    """The case that holds at the point, or None where no case does or none can be told."""
    box = {name: Interval(x, x) for name, x in point.items()}
    try:
        for n, case in enumerate(row.cases):
            holds = True if case.when is None else _holds(case.when, box)
            if holds is None:
                return None
            if holds:
                return n
    except KernelArithmeticError:
        pass
    return None


def value(row: Row, point: Mapping[str, Any], case: int | None = None) -> Fraction | None:
    """What the row gives at the point, by `case` or by the one that holds there. None where
    it gives nothing: no case holds, the expression is undefined, or a table has no cell
    there or an empty one."""
    if row.table is not None:
        return row.table.cell(point)
    n = active(row, point) if case is None else case
    if n is None:
        return None
    try:
        return enclose(row.cases[n].expr, {name: Interval(x, x) for name, x in point.items()}).midpoint()
    except KernelArithmeticError:
        return None


def close(a: Fraction | None, b: Fraction | None, within: Fraction = CLOSE) -> bool:
    if a is None or b is None:
        return a is b
    return abs(a - b) <= within * max(abs(a), abs(b))


def points(row: Row, seed: int, count: int = SAMPLES) -> list[dict[str, Any]]:
    """Points inside the ranges of the row's inputs, spread evenly on a log scale. For a
    table, every place of it instead, with each side of every band's ends."""
    if row.table is not None:
        return [dict(zip((a.by for a in row.table.axes), at)) for at in itertools.product(*(a.probes() for a in row.table.axes))]
    rng = random.Random(f"{seed}/{row.id}")

    def draw(i: Input) -> Fraction:
        if i.lo <= 0 or i.lo == i.hi:
            return i.lo + (i.hi - i.lo) * Fraction(rng.randrange(1001), 1000)
        return Fraction(f"{float(i.lo) * (float(i.hi) / float(i.lo)) ** rng.random():.5g}")

    return [{name: draw(i) for name, i in row.takes.items()} for _ in range(count)]


def meetings(row: Row, seed: int) -> Iterator[tuple[int, int, dict[str, Fraction], dict[str, Fraction]]]:
    """Places where one case hands over to another, found by bisection between two sample
    points that different cases hold at: (the case on one side, the case on the other,
    a point on the first side, a point on the other side), the two points next to each
    other."""
    if row.table is not None:
        return
    sample = [(p, active(row, p)) for p in points(row, seed)]
    seen: dict[tuple[int, int], int] = {}
    for (p, i), (q, j) in itertools.combinations(sample, 2):
        if i is None or j is None or i == j or seen.get((min(i, j), max(i, j)), 0) >= 4:
            continue
        seen[(min(i, j), max(i, j))] = seen.get((min(i, j), max(i, j)), 0) + 1
        lo, hi, other = p, q, j
        for _ in range(48):
            mid = {name: (lo[name] + hi[name]) / 2 for name in lo}
            at = active(row, mid)
            if at == i:
                lo = mid
            elif at is None:
                break
            else:
                hi, other = mid, at
        yield i, other, lo, hi


# --- the acceptance check ---------------------------------------------------------------------------


def units(row: Row) -> Check:
    return Check("units", "fail" if row.problems else "pass", "; ".join(row.problems))


def example(body: Mapping[str, Any], row: Row) -> Example:
    """A worked example for `row` from its JSON: `anchor`, `given` (input name to quantity),
    `gives` (the printed result with its unit) and, when the print warrants it, `within`.
    A quantity the source states and the row does not read is left out: the row then
    reproduces the result only if it was right not to read it."""
    try:
        given: dict[str, Any] = {}
        for name, i in row.takes.items():
            if name not in body["given"]:
                raise RowError(f"it does not give {name}, which the row reads")
            if i.keys:
                given[name] = str(body["given"][name])
                if given[name] not in i.keys:
                    raise RowError(f"{name} = {given[name]} is not one of {', '.join(i.keys)}")
                continue
            given[name], dim = quantity(body["given"][name], name)
            if dim != i.dim:
                raise RowError(f"{name} = {body['given'][name]} is not a {show(i.dim)}")
        printed = str(body["gives"])
        if row.names:      # a row that gives a name: the example prints the name
            if printed not in row.names:
                raise RowError(f"an example gives one of the names the row gives: {', '.join(row.names)}")
            return Example(str(body["anchor"]), given, printed, Fraction(0), printed)
        gives, dim = quantity(printed, "the result")
        if dim != row.dim or gives == 0:
            raise RowError("an example gives a result of the row's dimension that is not zero")
        digits = len(printed.split()[0].partition(".")[2])
        last = Fraction(1, 2 * 10 ** digits) / abs(Fraction(printed.split()[0].replace(",", "")))
        within = quantity(body["within"], "within")[0] if "within" in body else max(ROUNDED, last)
        return Example(str(body["anchor"]), given, gives, within, printed)
    except RowError as exc:
        raise RowError(f"{row.id}: example: {exc}") from None
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise RowError(f"{row.id}: not an example ({type(exc).__name__}: {exc})") from None


def reproduces(row: Row, examples: list[Example]) -> Check:
    if not examples:
        return Check("examples", "none", "no worked example")
    misses = []
    for e in examples:
        got = value(row, e.given)
        if row.names:
            misses += [f"{e.anchor}: prints {e.printed}, and the row gives {got or 'nothing'}"] * (got != e.gives)
        elif got is None or abs(got - e.gives) > e.within * abs(e.gives):
            ratio = "nothing" if got is None else f"{float(got / e.gives):.4f} of it"
            misses.append(f"{e.anchor}: prints {e.printed}, and the row gives {ratio}")
    return Check("examples", "fail" if misses else "pass", "; ".join(misses) or f"{len(examples)} reproduced")


def continuous(row: Row, seed: int = 0) -> Check:
    if len(row.cases) == 1:
        return Check("continuity", "pass", "one case")
    found = list(meetings(row, seed))
    if not found:
        return Check("continuity", "none", f"no two of {SAMPLES} sample points fell in different cases: widen the ranges")
    gaps: dict[frozenset, Fraction] = {}
    for i, j, at, _ in found:
        a, b = value(row, at, i), value(row, at, j)
        if a is not None and b is not None:
            gap = abs(a - b) / max(abs(a), abs(b)) if a != b else Fraction(0)
            gaps[frozenset((i, j))] = max(gap, gaps.get(frozenset((i, j)), Fraction(0)))
    said = [f"cases {' and '.join(str(n + 1) for n in sorted(pair))} " + (f"differ by {float(gap):.2%}" if gap > MEET else f"meet within {float(gap):.3%}")
            + (", as the row says" if pair in row.jumps and gap > MEET else "") for pair, gap in sorted(gaps.items(), key=lambda g: sorted(g[0]))]
    unsaid = any(gap > MEET and pair not in row.jumps for pair, gap in gaps.items())
    return Check("continuity", "fail" if unsaid else "pass", "; ".join(said))


def shape(row: Row) -> Check:
    """Whether a table runs as its row says: never down along a side it rises on, never up
    along one it falls on. A cell misread by a digit or taken from the next line often
    breaks the run."""
    table = row.table
    if not (table.rises or table.falls):
        return Check("shape", "none", "the row does not say how the table runs")
    for side, axis in enumerate(table.axes):
        sign = 1 if axis.by in table.rises else -1 if axis.by in table.falls else 0
        for n, line in enumerate(table.lines(side)):
            filled = [(place, x) for place, x in enumerate(line) if x is not None]
            for (a, x), (b, y) in zip(filled, filled[1:]):
                if sign * (y - x) < 0:
                    return Check("shape", "fail", f"along {axis.by} the table {'rises' if sign > 0 else 'falls'}, and in line {n + 1} place {b + 1} "
                                                  f"is {'under' if sign > 0 else 'over'} place {a + 1}")
    return Check("shape", "pass", f"runs as said along {', '.join(sorted(table.rises | table.falls))}")


def second(row: Row, other: Row, seed: int = 0) -> Check:
    """Whether `other` gives what `row` gives at every sample point and on both sides of
    every meeting of either's cases, under some renaming of its inputs that keeps their
    dimensions."""
    kinds = collections.Counter(i.kind for i in row.takes.values())

    def gives(r: Row) -> str:
        return f"one of {len(r.names)} names" if r.names else f"a {show(r.dim)}"

    def at_place(r: Row, v: Any) -> Any:
        """A name as its place among the names its row gives: two transcribers name them in
        their own words, so they are matched by their order, which is the standard's."""
        return r.names.index(v) if r.names and v is not None else v

    if row.dim != other.dim or len(row.names) != len(other.names) or kinds != collections.Counter(i.kind for i in other.takes.values()) or (row.table is None) != (other.table is None):
        return Check("second", "fail", f"it takes {', '.join(row.takes)} and gives {gives(row)}; the other takes {', '.join(other.takes)} and gives {gives(other)}")
    here = points(row, seed) + [p for _, _, lo, hi in meetings(row, seed) for p in (lo, hi)]
    there = [p for _, _, lo, hi in meetings(other, seed) for p in (lo, hi)] + (points(other, seed) if other.table is not None else [])
    first_miss = ""
    for renaming in _renamings(row, other):
        back = {b: a for a, b in renaming.items()}
        at = here + [_carried(p, back, other, row) for p in there]
        mine = [at_place(row, value(row, p)) for p in at]
        miss = next((p for p, v in zip(at, mine) if not close(v, at_place(other, value(other, _carried(p, renaming, row, other))))), None)
        if miss is None:
            renamed = {a: b for a, b in renaming.items() if a != b}
            return Check("second", "pass", f"{len(at)} points" + (f", reading {', '.join(f'{a} as {b}' for a, b in renamed.items())}" if renamed else ""))
        if not first_miss:
            theirs = value(other, _carried(miss, renaming, row, other))
            mine_there = value(row, miss)
            ratio = ("one of them gives nothing" if theirs is None or mine_there is None or not mine_there
                     else f"this one gives {mine_there} and the other {theirs}" if row.names else f"the other gives {float(theirs / mine_there):.4f} of it")
            where = ", ".join(f"{k}={v}" if isinstance(v, str) else f"{k}={float(v):.5g}" for k, v in miss.items())
            first_miss = f"at {where} (SI) {ratio}"
    return Check("second", "fail", first_miss)


def _carried(point: Mapping[str, Any], names: Mapping[str, str], src: Row, dst: Row) -> dict[str, Any]:
    """A point of `src` as a point of `dst`: each input under its name there, and each key's
    name as the name in the same place of the other's list."""
    out = {}
    for name, x in point.items():
        keys = src.takes[name].keys
        out[names[name]] = dst.takes[names[name]].keys[keys.index(x)] if keys else x
    return out


def _renamings(row: Row, other: Row) -> Iterator[dict[str, str]]:
    """Each way to read the other's inputs as this row's that keeps every dimension: the
    one that keeps the names first, when they are the same names."""
    if set(row.takes) == set(other.takes) and all(row.takes[n].kind == other.takes[n].kind for n in row.takes):
        yield {name: name for name in row.takes}
        return
    # The inputs of each kind, under a text of the kind: a kind holds the exponents of a
    # dimension, which are numbers a deck chooses, and a table is keyed by none of those.
    by_dim: dict[str, list[str]] = {}
    for name, i in other.takes.items():
        by_dim.setdefault(repr(i.kind), []).append(name)
    groups = [[n for n, i in row.takes.items() if repr(i.kind) == kind] for kind in by_dim]
    for choice in itertools.islice(itertools.product(*(itertools.permutations(names) for names in by_dim.values())), 5040):
        yield {a: b for mine, theirs in zip(groups, choice) for a, b in zip(mine, theirs)}


def accept(row: Row, examples: list[Example], other: Row | None = None, seed: int = 0) -> list[Check]:
    """The acceptance check on one row. A row is admitted when no part fails; the parts
    that are `none` say how much stands behind it."""
    checks = [units(row), reproduces(row, examples), continuous(row, seed) if row.table is None else shape(row)]
    return checks + [second(row, other, seed) if other is not None else Check("second", "none", "no second transcription")]


def load(path: str) -> dict[str, Row]:
    with open(path, encoding="utf-8") as fh:
        rows = [read(body) for body in json.load(fh)["rows"]]
    if len({r.id for r in rows}) != len(rows):
        raise RowError(f"{path}: two rows have one id")
    return {r.id: r for r in rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m petra.deck", description="Run the acceptance check on each row of a file.")
    parser.add_argument("rows", help='a JSON file {"rows": [...]}')
    parser.add_argument("--examples", help='worked examples, a JSON file {"examples": {ROW ID: [...]}}')
    parser.add_argument("--second", help="a second transcription of the same rows, to compare")
    args = parser.parse_args(argv)
    try:
        rows = load(args.rows)
        others = load(args.second) if args.second else {}
        worked = json.load(open(args.examples, encoding="utf-8"))["examples"] if args.examples else {}
        failed = 0
        for row in rows.values():
            checks = accept(row, [example(e, row) for e in worked.get(row.id, [])], others.get(row.id))
            failed += any(c.outcome == "fail" for c in checks)
            print(f"{row.id}: {'REFUSED' if any(c.outcome == 'fail' for c in checks) else 'admitted'}")
            for c in checks:
                print(f"  {c.name:<11} {c.outcome:<5} {c.detail}")
    except (RowError, OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"petra.deck: {exc}", file=sys.stderr)
        return 3
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
