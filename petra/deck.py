"""Rules as data: a row of a deck, what it means, and whether to admit it. Untrusted.

A row is one equation of a standard written as data (docs/deck.md): what it gives, what it
takes, each with a dimension, and its expression, by case where the standard splits it.
This module reads a row, checks its dimensions, evaluates it exactly, and runs the
acceptance check a row passes before it enters a deck:

    units        every sum, comparison and result has one dimension
    examples     the row reproduces each worked example given with it
    continuity   where two cases meet they give one value, unless the row says those two jump
    second       a transcription made without sight of this one gives the same values

    python -m petra.deck ROWS.json [--examples FILE.json] [--second ROWS.json]

The kernel does not read rows yet, so a row proves nothing by itself: it is the formula a
deck will bind a proof to.
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
import re
import sys
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Iterator, Mapping

from .kernel import (Abs, Add, Const, Div, Exp, Interval, KernelArithmeticError, Ln, Max, Min, Mul, Neg, Pi, PowInt, Sqrt, Sym, enclose)
from .units import (AREA, CURRENT, DIMENSIONLESS, ENERGY, FORCE, LENGTH, MASS, POWER, RESISTANCE, STRESS, TEMPERATURE, TIME, VOLTAGE, Dim,
                    UnitError, parse_quantity)

Vector = tuple[Fraction, ...]
"""A dimension as exponents of (m, kg, s, A, degC). A square root halves them, so they are fractions."""

BASES = ("m", "kg", "s", "A", "degC")
NAMED: Mapping[str, Dim] = {"dimensionless": DIMENSIONLESS, "length": LENGTH, "area": AREA, "force": FORCE, "stress": STRESS, "mass": MASS,
                            "time": TIME, "temperature": TEMPERATURE, "energy": ENERGY, "moment": ENERGY, "current": CURRENT,
                            "voltage": VOLTAGE, "power": POWER, "resistance": RESISTANCE}
"""The dimension names a row may write. `moment` is a force times a length, as energy is."""

ROW_KEYS = frozenset({"id", "anchor", "gives", "takes", "is", "cases", "jumps"})
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
        if name not in NAMED or not re.fullmatch(r"-?\d+", power or "1"):
            raise RowError(f"{text!r} is not a dimension: it is {', '.join(NAMED)}, with ^N, * and /")
        out = tuple(a + sign * int(power or 1) * b for a, b in zip(out, _vector(NAMED[name])))
    return out


def show(v: Vector) -> str:
    for name, dim in NAMED.items():
        if _vector(dim) == v:
            return name
    return " ".join(f"{base}^{power}" for base, power in zip(BASES, v) if power)


def quantity(text: str, what: str) -> tuple[Fraction, Vector]:
    """`0.75 inch` as an exact SI value and its dimension. A number alone has none."""
    number, _, unit = str(text).strip().partition(" ")
    try:
        q = parse_quantity(number.replace(",", ""), unit.strip() or None)
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
    dim: Vector
    lo: Fraction
    hi: Fraction


@dataclass(frozen=True)
class Row:
    """One equation. `problems` are its dimension errors, found when it was read."""

    id: str
    anchor: Mapping[str, str]
    gives: str
    dim: Vector
    takes: Mapping[str, Input]
    cases: tuple[Case, ...]
    jumps: Mapping[frozenset, str]      # two case numbers, from 0, to why they do not meet
    problems: tuple[str, ...]


@dataclass(frozen=True)
class Example:
    """A worked use of a row in print: the inputs, the printed result and how near a
    reproduction must come, all in SI, with the result as printed for messages."""

    anchor: str
    given: Mapping[str, Fraction]
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
        if len(set(dims)) > 1:
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
                return Sym(node), self.takes[node].dim
            try:
                return Const(Fraction(node)), NONE
            except (ValueError, ZeroDivisionError):
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
        if op in ("exp", "ln") and len(terms) == 1:
            self.bare(op, dims[0])
            return (Exp if op == "exp" else Ln)(terms[0]), NONE
        raise RowError(f"{op!r} with {len(args)} arguments is not in the language")

    def power(self, base: Any, exponent: Any) -> tuple[Any, Vector]:
        """A whole power, a half power as a power of the root, and any other as
        exp(exponent ln base), which needs a base that is a plain number."""
        term, dim = self.expr(base)
        if isinstance(exponent, str) and exponent not in self.takes and exponent != "pi":
            try:
                n = Fraction(exponent)
            except (ValueError, ZeroDivisionError):
                raise RowError(f"{exponent!r} is not a number, and the row does not take it") from None
            scaled = tuple(a * n for a in dim)
            if n.denominator <= 2:
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
    if unknown or ("is" in body) == ("cases" in body):
        raise RowError(f"{where}: a row has {', '.join(sorted(ROW_KEYS))}, with one of `is` and `cases`" + (f"; not {', '.join(unknown)}" if unknown else ""))
    try:
        anchor, gives = dict(body["anchor"]), body["gives"]
        takes = {}
        for t in body["takes"]:
            dim = dimension(t["dim"])
            (lo, lo_dim), (hi, hi_dim) = (quantity(end, f"the range of {t['name']}") for end in t["range"])
            if {lo_dim, hi_dim} != {dim} or not lo <= hi:
                raise RowError(f"the range of {t['name']} is two {show(dim)} values, the lower first")
            takes[t["name"]] = Input(dim, lo, hi)
        if len(takes) != len(body["takes"]) or not anchor.get("standard") or not anchor.get("clause"):
            raise RowError("an input is named twice, or the anchor lacks its standard or its clause")
        reader = _Reader(takes)
        written = body["cases"] if "cases" in body else [{"is": body["is"]}]
        cases = []
        for n, case in enumerate(written):
            if set(case) - {"when", "is"} or "is" not in case or ("when" not in case and n != len(written) - 1):
                raise RowError("a case has `when` and `is`, and only the last may leave `when` out")
            when = reader.cond(case["when"]) if "when" in case else None
            cases.append(Case(when, *reader.expr(case["is"])))
        jumps = {frozenset(n - 1 for n in j["cases"]): str(j["why"]) for j in body.get("jumps", [])}
        if any(len(pair) != 2 or not pair <= set(range(len(cases))) for pair in jumps) or not all(jumps.values()):
            raise RowError("a jump names two of the row's cases by number, from 1, and says why")
        out = dimension(gives["dim"])
        problems = reader.problems + [f"case {n + 1} gives a {show(c.dim)}, and the row gives a {show(out)}" for n, c in enumerate(cases) if c.dim != out]
        return Row(where, anchor, str(gives["name"]), out, takes, tuple(cases), jumps, tuple(dict.fromkeys(problems)))
    except RowError as exc:
        raise RowError(f"{where}: {exc}") from None
    except (KeyError, TypeError, ValueError) as exc:
        raise RowError(f"{where}: not a row ({type(exc).__name__}: {exc})") from None


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


def value(row: Row, point: Mapping[str, Fraction], case: int | None = None) -> Fraction | None:
    """What the row gives at the point, by `case` or by the one that holds there. None where
    it gives nothing: no case holds, or the expression is undefined."""
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


def points(row: Row, seed: int, count: int = SAMPLES) -> list[dict[str, Fraction]]:
    """Points inside the ranges of the row's inputs, spread evenly on a log scale."""
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
        given = {}
        for name, i in row.takes.items():
            if name not in body["given"]:
                raise RowError(f"it does not give {name}, which the row reads")
            given[name], dim = quantity(body["given"][name], name)
            if dim != i.dim:
                raise RowError(f"{name} = {body['given'][name]} is not a {show(i.dim)}")
        printed = str(body["gives"])
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
        if got is None or abs(got - e.gives) > e.within * abs(e.gives):
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


def second(row: Row, other: Row, seed: int = 0) -> Check:
    """Whether `other` gives what `row` gives at every sample point and on both sides of
    every meeting of either's cases, under some renaming of its inputs that keeps their
    dimensions."""
    if row.dim != other.dim or sorted(i.dim for i in row.takes.values()) != sorted(i.dim for i in other.takes.values()):
        return Check("second", "fail", f"it takes {', '.join(row.takes)} and gives a {show(row.dim)}; the other takes {', '.join(other.takes)} and gives a {show(other.dim)}")
    here = points(row, seed) + [p for _, _, lo, hi in meetings(row, seed) for p in (lo, hi)]
    there = [p for _, _, lo, hi in meetings(other, seed) for p in (lo, hi)]
    first_miss = ""
    for renaming in _renamings(row, other):
        back = {b: a for a, b in renaming.items()}
        at = here + [{back[name]: x for name, x in p.items()} for p in there]
        mine = [value(row, p) for p in at]
        miss = next((p for p, v in zip(at, mine) if not close(v, value(other, {renaming[name]: x for name, x in p.items()}))), None)
        if miss is None:
            renamed = {a: b for a, b in renaming.items() if a != b}
            return Check("second", "pass", f"{len(at)} points" + (f", reading {', '.join(f'{a} as {b}' for a, b in renamed.items())}" if renamed else ""))
        if not first_miss:
            theirs = value(other, {renaming[name]: x for name, x in miss.items()})
            mine_there = value(row, miss)
            ratio = "one of them gives nothing" if theirs is None or mine_there is None or not mine_there else f"the other gives {float(theirs / mine_there):.4f} of it"
            first_miss = f"at {', '.join(f'{k}={float(v):.5g}' for k, v in miss.items())} (SI) {ratio}"
    return Check("second", "fail", first_miss)


def _renamings(row: Row, other: Row) -> Iterator[dict[str, str]]:
    """Each way to read the other's inputs as this row's that keeps every dimension: the
    one that keeps the names first, when they are the same names."""
    if set(row.takes) == set(other.takes) and all(row.takes[n].dim == other.takes[n].dim for n in row.takes):
        yield {name: name for name in row.takes}
        return
    by_dim: dict[Vector, list[str]] = {}
    for name, i in other.takes.items():
        by_dim.setdefault(i.dim, []).append(name)
    groups = [[n for n, i in row.takes.items() if i.dim == dim] for dim in by_dim]
    for choice in itertools.islice(itertools.product(*(itertools.permutations(names) for names in by_dim.values())), 5040):
        yield {a: b for mine, theirs in zip(groups, choice) for a, b in zip(mine, theirs)}


def accept(row: Row, examples: list[Example], other: Row | None = None, seed: int = 0) -> list[Check]:
    """The acceptance check on one row. A row is admitted when no part fails; the parts
    that are `none` say how much stands behind it."""
    checks = [units(row), reproduces(row, examples), continuous(row, seed)]
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
