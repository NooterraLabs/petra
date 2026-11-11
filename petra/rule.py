"""Rules as data: whether to admit the rules that answer a mechanism. Untrusted.

A rule of a deck binds rows to the fields of a part and states an inequality (docs/deck.md).
A row passes an acceptance check before it enters a deck (petra/deck.py). This module is
that check for rules. A task holds the types, the rows and the mechanisms to answer. A
transcription holds the rules written for the task and, where a mechanism cannot arise,
why. For each mechanism the check reports:

    units       its rules load: each row input bound once and to its dimension, both sides
                of one dimension, a line of the grid that can arise (grid.read_deck)
    examples    they reproduce each worked example given for the mechanism
    reach       over the sampled parts they answer, hold at one and fail at another, and
                leave no range and no argument of a min or a max unused
    direction   more of a load the task calls adverse turns no failing part into a holding one
    alike       parts the task calls alike may change places and the answer stays
    second      a transcription made without sight of this one gives every sampled part
                the same answer

and for the transcription as a whole, `reads`: something reads every field and every load.

    python -m petra.rule TASK.json RULES.json [--second RULES.json] [--examples FILE.json]

A part is sampled as a point: each key a name, each quantity and each load one value. A
rule's two sides at a point come from the tape that petra/grid.py writes for it, so the
check reads a rule as `petra check` does. For that it calls grid.py's reader, its tape
writer and what it knows a rule reads, private names among them, and changes none of it.
Nothing here decides a verdict: the check decides what may enter a deck, and the kernel
reads the deck's file itself.
"""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import math
import random
import sys
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from . import deck as rows
from . import grid
from .deck import NONE, ROUNDED, Check, RowError, Vector, close, quantity, show
from .grid import DeckError
from .kernel import Div, Interval, KernelArithmeticError, Pi, PowInt, Sym, enclose

TASK = "petra-rule-task/0"
PARTS = 96
"""How many parts the check samples for a mechanism, spread over every combination of the type's keys."""
PARTNERS = 32
"""How many of them get a partner: the same part with other sizes and loads. Between the two
the check looks for the place where an answer changes."""
TURNS = 1
"""How many such places it looks for between each two ways a transcription treats a part."""
STEPS = 24
"""How many times it halves the way between two parts to find one. The two sides then lie
within a part in ten million of the way."""
TRIED = 32
"""How many sampled parts `direction` and `alike` each try."""
FAR = 64
"""How far past its range a load or a size is moved to see an answer turn: to this many
times the top, and to this part of the bottom."""


# --- a task, a transcription, a worked example ---------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Task:
    """What two transcribers are given: `body` is a deck with no rule and no `unless`, and
    `deck` is that deck read. `spans` gives, for each type, the range to sample each
    quantity and each load in, by the name a rule reads it under: `pitch`, `a.Fy`,
    `load pull`. `keys` gives each type's keys the same way, with their names. `adverse`
    names the loads of a type that never help, and `alike` the joined parts of a type that
    may change places."""

    name: str
    body: Mapping[str, Any]
    deck: grid.Deck
    spans: Mapping[str, Mapping[str, tuple[Fraction, Fraction]]]
    keys: Mapping[str, Mapping[str, tuple[str, ...]]]
    adverse: Mapping[str, frozenset[str]]
    alike: Mapping[str, tuple[tuple[str, ...], ...]]

    @property
    def mechanisms(self) -> list[str]:
        return [a.mechanism for a in self.deck.asks]


@dataclass(frozen=True)
class Transcription:
    """The rules written for a task, the mechanisms that cannot arise, each with `why` and
    perhaps `when`, and the mechanisms left out, each with why."""

    rules: tuple[Mapping[str, Any], ...]
    unless: Mapping[str, Mapping[str, Any]]
    left_out: Mapping[str, str]


@dataclass(frozen=True)
class Worked:
    """A worked example of a mechanism in print: a part as a point, which `side` of the
    inequality the source prints (`left`, `right` or `ratio`), the printed value in SI with
    its dimension, and how near a reproduction must come."""

    anchor: str
    part: Mapping[str, Any]
    side: str
    gives: Fraction
    dim: Vector
    within: Fraction
    printed: str


def _names(deck: grid.Deck, kind: str) -> tuple[dict[str, tuple[str, ...]], dict[str, grid.Field], dict[str, grid.Field]]:
    """What a rule of the type may read, by the name it reads it under: the keys with their
    names, the quantities, and the loads as `load NAME`."""
    keys: dict[str, tuple[str, ...]] = {}
    sizes: dict[str, grid.Field] = {}

    def add(prefix: str, of: str) -> None:
        for f in deck.types[of].fields.values():
            if f.type is not None:
                for alias in f.names:
                    add(f"{alias}.", f.type)
            elif f.keys:
                keys[prefix + f.name] = f.keys
            else:
                sizes[prefix + f.name] = f

    add("", kind)
    return keys, sizes, {f"load {f.name}": f for f in deck.types[kind].loads.values()}


def read_task(body: Mapping[str, Any], folder: Path | None = None) -> Task:
    """A task from its JSON: `format`, `name`, `about`, `rows` or `rows_from`, the path or
    the paths of files that hold rows, from the task's folder, `types` and `asks`. A type is
    written as in a deck, and each quantity and each load has a `range` besides. A load may
    be `adverse`, and a type may list the joined parts that are `alike`. An ask is a line of
    the grid with no `unless`. Raises DeckError."""
    try:
        if body.get("format") != TASK or set(body) - {"format", "name", "about", "rows", "rows_from", "types", "asks"} or ("rows" in body) == ("rows_from" in body):
            raise DeckError(f"a task has format {TASK}, name, about, types, asks, and one of rows and rows_from")
        files = body.get("rows_from", [])
        found = body["rows"] if "rows" in body else [row for name in ([files] if isinstance(files, str) else files)
                                                     for row in json.loads(((folder or Path()) / name).read_text(encoding="utf-8"))["rows"]]
        types = [{**{k: v for k, v in t.items() if k != "alike"},
                  "fields": [{k: v for k, v in f.items() if k != "range"} for f in t["fields"]],
                  "loads": [{k: v for k, v in f.items() if k not in ("range", "adverse")} for f in t.get("loads", [])]} for t in body["types"]]
        asked = [a["mechanism"] for a in body["asks"]]
        if any("unless" in a for a in body["asks"]) or len(set(asked)) != len(asked):
            raise DeckError("a task asks each mechanism once and gives no `unless`: a transcription says what cannot arise")
        plain = {"format": grid.FORMAT, "name": str(body["name"]), "about": str(body.get("about", "")), "rows": found, "types": types, "grid": list(body["asks"]), "rules": []}
        deck = grid.read_deck(json.dumps(plain))
        ranges: dict[tuple[str, str], tuple[Fraction, Fraction]] = {}
        adverse: dict[str, frozenset[str]] = {}
        alike: dict[str, tuple[tuple[str, ...], ...]] = {}
        for t in body["types"]:
            kind = deck.types[t["type"]]
            for f, known, name in [(f, kind.fields[f["name"]], f["name"]) for f in t["fields"]] + [(f, kind.loads[f["name"]], f"load {f['name']}") for f in t.get("loads", [])]:
                if known.dim is None:
                    if "range" in f:
                        raise DeckError(f"{kind.name}.{f['name']}: only a quantity has a range")
                    continue
                if "range" not in f:
                    raise DeckError(f"{kind.name}.{f['name']}: a task gives each quantity and each load a `range` to sample it in")
                (lo, lo_dim), (hi, hi_dim) = (quantity(str(end), f"the range of {kind.name}.{f['name']}") for end in f["range"])
                least = known.least if known.least is not None else Fraction(0)
                inside = lo >= least if name.startswith("load ") else lo > 0 and lo >= least
                if {lo_dim, hi_dim} != {known.dim} or not lo <= hi or not inside or (known.whole and lo.denominator * hi.denominator != 1):
                    raise DeckError(f"{kind.name}.{f['name']}: its range is two {show(known.dim)} values a part may have, the lower first")
                ranges[kind.name, name] = (lo, hi)
            adverse[kind.name] = frozenset(f["name"] for f in t.get("loads", []) if f.get("adverse"))
            joined = {alias: f.type for f in kind.fields.values() if f.type is not None for alias in f.names}
            alike[kind.name] = tuple(tuple(group) for group in t.get("alike", []))
            if any(len(group) < 2 or None in {joined.get(alias) for alias in group} or len({joined[alias] for alias in group}) != 1 for group in alike[kind.name]):
                raise DeckError(f"{kind.name}: `alike` lists groups of two or more joined parts of one type, by the names of `as`")
        spans = {}
        for kind in deck.types.values():
            aliases = {alias: f.type for f in kind.fields.values() if f.type is not None for alias in f.names}
            _, sizes, loads = _names(deck, kind.name)
            spans[kind.name] = {name: ranges[aliases[name.partition(".")[0]], name.partition(".")[2]] if "." in name else ranges[kind.name, name] for name in (*sizes, *loads)}
        return Task(plain["name"], plain, deck, spans, {kind: _names(deck, kind)[0] for kind in deck.types}, adverse, alike)
    except DeckError:
        raise
    except RowError as exc:
        raise DeckError(f"task: {exc}") from None
    except (KeyError, TypeError, AttributeError, ValueError, OSError) as exc:
        raise DeckError(f"not a task ({type(exc).__name__}: {exc})") from None


def read_transcription(body: Mapping[str, Any]) -> Transcription:
    """A transcription from its JSON: `rules`, each as a deck holds a rule; `unless`, a list
    of `{"mechanism", "why"}` and perhaps `when`; and `left_out`, a list of
    `{"mechanism", "why"}`. A deck is read as one too: its rules, and the `unless` of its
    grid. Any other key, such as who wrote it and from what, is the transcriber's note."""
    try:
        if not isinstance(body["rules"], list) or not all(isinstance(r, dict) for r in body["rules"]):
            raise DeckError("not a transcription: `rules` is a list of rules")
        if "grid" in body:
            return Transcription(tuple(body["rules"]), {a["mechanism"]: dict(a["unless"]) for a in body["grid"] if "unless" in a}, {})
        unless = {u["mechanism"]: {k: u[k] for k in ("why", "when") if k in u} for u in body.get("unless", [])}
        if not all(isinstance(u.get("why"), str) and u["why"] for u in unless.values()):
            raise DeckError("not a transcription: each `unless` says why, in words")
        return Transcription(tuple(body["rules"]), unless, {x["mechanism"]: str(x["why"]) for x in body.get("left_out", [])})
    except (KeyError, TypeError, AttributeError) as exc:
        raise DeckError(f"not a transcription ({type(exc).__name__}: {exc})") from None


def worked(body: Mapping[str, Any], task: Task, mechanism: str) -> Worked:
    """A worked example from its JSON: `anchor`; `given`, each field the source states by the
    name a rule reads it under; `loads`; `side`, which is `left`, `right` or `ratio`;
    `gives`, the printed value with its unit; and `within` when the print warrants another
    bound than the row check's."""
    try:
        kind = next(a.type for a in task.deck.asks if a.mechanism == mechanism)
        keys, sizes, loads = _names(task.deck, kind)
        part: dict[str, Any] = {}
        for name, text in {**body.get("given", {}), **{f"load {k}": v for k, v in body.get("loads", {}).items()}}.items():
            if name in keys:
                if str(text) not in keys[name]:
                    raise RowError(f"{name} = {text} is not one of {', '.join(keys[name])}")
                part[name] = str(text)
                continue
            known = sizes.get(name) or loads.get(name)
            if known is None:
                raise RowError(f"a {kind} has no {name}: it has {', '.join((*keys, *sizes, *loads))}")
            part[name], dim = quantity(str(text), name)
            if dim != known.dim:
                raise RowError(f"{name} = {text} is not a {show(known.dim)}")
        printed, side = str(body["gives"]), body["side"]
        gives, dim = quantity(printed, "the printed value")
        if side not in ("left", "right", "ratio") or gives == 0 or (side == "ratio" and dim != NONE):
            raise RowError("`side` is left, right or ratio, and `gives` is not zero and for a ratio a plain number")
        digits = len(printed.split()[0].partition(".")[2])
        last = Fraction(1, 2 * 10 ** digits) / abs(Fraction(printed.split()[0].replace(",", "")))
        within = quantity(body["within"], "within")[0] if "within" in body else max(ROUNDED, last)
        return Worked(str(body["anchor"]), part, side, gives, dim, within, printed)
    except RowError as exc:
        raise DeckError(f"{mechanism}: example: {exc}") from None
    except (KeyError, TypeError, ValueError, ZeroDivisionError, StopIteration) as exc:
        raise DeckError(f"{mechanism}: not an example ({type(exc).__name__}: {exc})") from None


# --- a rule at a point -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Tape:
    """The tape grid.py writes for a rule on a part with given keys: its nodes, a constant
    as a Fraction, the name each input reads, the two sides, each range, and the row behind
    each pick. `raw` is the tape as grid.py wrote it."""

    nodes: tuple
    raw: tuple
    labels: tuple[str, ...]
    low: int
    high: int
    where: tuple[tuple[int, int, str], ...]
    picks: Mapping[int, str]


class _Unsure(Exception):
    """Two enclosed values too near to order. The caller asks grid.enclosures."""


def _lifted(x: Any) -> Interval:
    return x if isinstance(x, Interval) else Interval.point(x)


def _values(tape: _Tape, box: list[Fraction]) -> tuple[list[Any], dict[int, int]]:
    """Each node of the tape at a point, and the case each pick chose. A value is a Fraction
    while it is exact, an Interval once a root, a logarithm, an exponential or pi encloses
    it, and a string, the reason, where it has none. It is what grid.enclosures gives over
    a box of points, about three times sooner; tests/test_rules_accept.py compares the two."""
    v: list[Any] = []
    chose: dict[int, int] = {}

    def holds(cond: Any) -> bool:
        if cond is None:
            return True
        if cond[0] == "not":
            return not holds(cond[1])
        if cond[0] in ("and", "or"):
            return (all if cond[0] == "and" else any)([holds(c) for c in cond[1]])
        a, b = v[cond[1]], v[cond[2]]
        if isinstance(a, Fraction) and isinstance(b, Fraction):
            return a <= b if cond[0] == "le" else a < b
        a, b = _lifted(a), _lifted(b)
        if a.hi < b.lo or (cond[0] == "le" and a.hi <= b.lo):
            return True
        if a.lo > b.hi or (cond[0] == "lt" and a.lo >= b.hi):
            return False
        raise _Unsure

    def step(n: int, node: tuple) -> Any:
        kind = node[0]
        if kind == "c":
            return node[1]
        if kind == "s":
            return box[node[1]]
        if kind == "pick":
            missing = next((v[i] for cond, _ in node[1] for pair in grid._atoms(cond) for i in pair if isinstance(v[i], str)), None)
            first = next((k for k, (cond, _) in enumerate(node[1]) if holds(cond)), None) if missing is None else None
            if first is None:
                return missing or "no case of the pick holds somewhere in the box"
            chose[n] = first
            return v[node[1][first][1]]
        ids = [] if kind == "pi" else node[1] if kind in grid._MANY else [node[1]] if kind in grid._ONE or kind == "pow" else list(node[1:])
        args = [v[i] for i in ids]
        missing = next((a for a in args if isinstance(a, str)), None)
        if missing is not None:
            return missing
        if all(isinstance(a, Fraction) for a in args):
            if kind == "add":
                return sum(args, Fraction(0))
            if kind == "mul":
                return math.prod(args, start=Fraction(1))
            if kind in ("min", "max"):
                return (min if kind == "min" else max)(args)
            if kind in ("neg", "abs"):
                return -args[0] if kind == "neg" else abs(args[0])
            if kind == "div" and args[1] != 0:
                return args[0] / args[1]
            if kind == "pow":
                return args[0] ** node[2]
        names = [Sym(str(k)) for k in range(len(args))]
        term = (Pi() if kind == "pi" else grid._MANY[kind](tuple(names)) if kind in grid._MANY else grid._ONE[kind](names[0]) if kind in grid._ONE
                else Div(*names) if kind == "div" else PowInt(names[0], node[2]))
        return enclose(term, {str(k): _lifted(a) for k, a in enumerate(args)})

    try:
        for n, node in enumerate(tape.nodes):
            try:
                v.append(step(n, node))
            except KernelArithmeticError as exc:
                v.append(f"node {n}: {exc}")
    except _Unsure:
        return grid.enclosures([list(node) for node in tape.raw], [Interval.point(x) for x in box]), {}
    return v, chose


def _middle(x: Any) -> Fraction:
    return x.midpoint() if isinstance(x, Interval) else x


def _is(cond: tuple | None, point: Mapping[str, Any]) -> bool:
    """Whether a condition on what a part is holds for a point, as grid._static has it for a part."""
    if cond is None:
        return True
    if cond[0] == "is":
        return point.get(cond[1]) == cond[2]
    if cond[0] == "loaded":
        return f"load {cond[1]}" in point
    if cond[0] == "not":
        return not _is(cond[1], point)
    return (all if cond[0] == "and" else any)(_is(c, point) for c in cond[1:])


def _loaded(cond: tuple | None) -> Iterator[str]:
    """The loads a condition on a part asks about."""
    if cond is not None and cond[0] == "loaded":
        yield f"load {cond[1]}"
    elif cond is not None and cond[0] != "is":
        for inner in cond[1:]:
            yield from _loaded(inner)


@dataclass(frozen=True)
class Said:
    """What one rule says of one part: that its inequality `holds` or `fails`, with the two
    sides in SI, or `nothing`, with why. `kind` is the kind of nothing: the part is outside
    the rule's `range`, a row has no `value` there, or the part carries no `load` the rule
    reads. `mark` tells apart two parts that the rule treats differently: the case each
    row reads, and the range that fails."""

    rule: str
    state: str
    why: str = ""
    kind: str = ""
    low: Fraction | None = None
    high: Fraction | None = None
    mark: tuple = ()

    @property
    def ratio(self) -> Fraction | None:
        """The left side over the right, where the right is above zero, as a report prints it."""
        return self.low / self.high if self.high is not None and self.high > 0 else None


@dataclass(frozen=True)
class Answer:
    """What a transcription says of one mechanism for one part, as one of the four things a
    design can get from it: the mechanism `cannot arise`; it `fails`, when a rule that holds
    for the part fails; it is `open`, when none fails and one says nothing, or no rule is
    for a part like this; it `holds`, when every rule does. `petra check` gives each rule a
    cell, and a refuted cell outweighs an open one. `kind` is why it is open: `no rule`, or
    the kind of nothing its first silent rule says."""

    state: str
    why: str = ""
    said: tuple[Said, ...] = ()
    kind: str = ""

    @property
    def label(self) -> str:
        """The state for a count, with an open answer by its kind."""
        return {"": self.state, "no rule": "no rule", "range": "out of range", "value": "no value", "load": "no load"}[self.kind]

    @property
    def settled(self) -> bool:
        return self.state in ("holds", "fails")

    @property
    def ratio(self) -> Fraction | None:
        """The largest ratio among the rules that hold or fail, when each states one. Two
        rules for two plates and one rule with their minimum give the same."""
        found = [s.ratio for s in self.said if s.state != "nothing"]
        return max(found) if found and None not in found else None

    @property
    def governing(self) -> Said | None:
        """The rule with the largest ratio, or the first to fail or to hold when one states none."""
        found = [s for s in self.said if s.state != "nothing"]
        if not found:
            return None
        return max(found, key=lambda s: s.ratio) if self.ratio is not None else next((s for s in found if s.state == "fails"), found[0])

    @property
    def mark(self) -> tuple:
        """How the transcription treats the part, leaving out whether an inequality holds:
        two parts with one mark read the same cases of the same rows under the same rules.
        Where an inequality turns from holding to failing the ratio is 1 on both sides, and
        comparing the ratio at every part already covers that."""
        return ("settled" if self.settled else self.state, tuple((s.rule, s.kind, s.mark) for s in self.said))


class Reading:
    """A transcription read against a task. For each mechanism the task asks: its line of
    the grid with the transcription's `unless`, and its rules, or in `wrong` why they do
    not load. `stray` lists what the transcription says of a mechanism the task does not ask."""

    def __init__(self, task: Task, said: Transcription) -> None:
        self.task, self.said = task, said
        self.asks: dict[str, grid.Ask] = {}
        self.rules: dict[str, tuple[grid.Rule, ...]] = {}
        self.wrong: dict[str, str] = {}
        self._tapes: dict[tuple, Any] = {}
        self._answers: dict[tuple, Answer] = {}
        self._loads: dict[int, tuple[str, ...]] = {}
        for mechanism in task.mechanisms:
            self._load(mechanism)
        asked = set(task.mechanisms)
        ids = [r.get("id") for r in said.rules]
        self.stray = [f"rule {r.get('id')} answers {r.get('mechanism')}, which the task does not ask" for r in said.rules if r.get("mechanism") not in asked]
        self.stray += [f"{m} is not a mechanism the task asks" for m in (*said.unless, *said.left_out) if m not in asked]
        self.stray += [f"two rules have the id {i}" for i in sorted({i for i in ids if ids.count(i) > 1}, key=str)]

    def _load(self, mechanism: str) -> None:
        """Reads the mechanism's rules as a deck: the task's types and grid, this line's
        `unless`, and the rows these rules name. So a rule loads here when a deck with it loads."""
        mine = [r for r in self.said.rules if r.get("mechanism") == mechanism]
        named = {node[1] for r in mine for _, node in places(r) if isinstance(node, list) and node[:1] == ["row"] and len(node) == 3 and isinstance(node[1], str)}
        lines = [{**a, "unless": self.said.unless[mechanism]} if a["mechanism"] == mechanism and mechanism in self.said.unless else a for a in self.task.body["grid"]]
        self.rules[mechanism] = ()
        self.wrong.pop(mechanism, None)
        try:
            deck = grid.read_deck(json.dumps({**self.task.body, "rows": [r for r in self.task.body["rows"] if r["id"] in named], "grid": lines, "rules": mine}))
            self.asks[mechanism] = next(a for a in deck.asks if a.mechanism == mechanism)
            self.rules[mechanism] = deck.rules
        except DeckError as exc:
            self.asks[mechanism] = next(a for a in self.task.deck.asks if a.mechanism == mechanism)
            self.wrong[mechanism] = str(exc)

    def with_rules(self, mechanism: str, rules: list[Mapping[str, Any]], unless: Mapping[str, Any] | None = None) -> "Reading":
        """This reading with one mechanism's rules, and perhaps its `unless`, replaced. The other mechanisms are not read again."""
        kept = [r for r in self.said.rules if r.get("mechanism") != mechanism]
        excused = {**{m: u for m, u in self.said.unless.items() if m != mechanism}, **({mechanism: unless} if unless is not None else {})}
        out = object.__new__(Reading)
        out.task, out.said = self.task, Transcription((*kept, *rules), excused, self.said.left_out)
        out.asks, out.rules, out.wrong, out.stray = dict(self.asks), dict(self.rules), dict(self.wrong), list(self.stray)
        out._tapes, out._answers, out._loads = {}, {}, {}
        out._load(mechanism)
        return out

    def answers(self, mechanism: str) -> bool:
        """Whether the transcription says anything of the mechanism: a rule, or that it cannot arise."""
        return bool(self.rules[mechanism]) or self.asks[mechanism].excused is not None or mechanism in self.wrong

    def reads(self, mechanism: str) -> set[str]:
        """Every name the mechanism's rules and its `unless` read: fields, and loads as `load NAME`."""
        ask = self.asks[mechanism]
        found = set(grid._keys(ask.unless)) | set(_loaded(ask.unless))
        for rule in self.rules[mechanism]:
            found |= grid._reads(rule) | set(_loaded(rule.when))
        return found

    def _loads_of(self, rule: grid.Rule) -> tuple[str, ...]:
        if id(rule) not in self._loads:
            self._loads[id(rule)] = tuple(sorted(name for name in grid._reads(rule) if name.startswith("load ")))
        return self._loads[id(rule)]

    def _tape(self, rule: grid.Rule, point: Mapping[str, Any]) -> _Tape | str:
        """The rule's tape for a part with the point's keys, or why it has none: a table with no cell for them."""
        deck = self.task.deck
        kind = deck.types[rule.type]
        at = (id(rule), tuple(point.get(name, options[0]) for name, options in self.task.keys[rule.type].items()))
        if at not in self._tapes:
            blank = Interval.point(Fraction(0))
            joined, values = {}, {}
            for f in kind.fields.values():
                if f.type is not None:
                    values[f.name] = f.names
                    for alias in f.names:
                        inner = {g.name: point.get(f"{alias}.{g.name}", g.keys[0]) if g.keys else grid.Value(f"{alias}.{g.name}", blank) for g in deck.types[f.type].fields.values()}
                        joined[alias] = grid.Part(alias, deck.types[f.type], inner, {})
                else:
                    values[f.name] = point.get(f.name, f.keys[0]) if f.keys else grid.Value(f.name, blank)
            part = grid.Part("", kind, values, {name[5:]: {"": grid.Value(name, blank)} for name in self._loads_of(rule)})
            tape = grid._Tape()
            env = grid._env(tape, rule, part, joined, "")
            try:
                where = tuple((tape.emit(a, env), tape.emit(b, env), why) for a, b, why in rule.where)
                low, high = tape.emit(rule.low, env), tape.emit(rule.high, env)
                nodes = tuple(("c", Fraction(n[1])) if n[0] == "c" else tuple(n) for n in tape.nodes)
                self._tapes[at] = _Tape(nodes, tuple(tuple(n) for n in tape.nodes), tuple(i.label for i in tape.inputs), low, high, where, dict(tape.picks))
            except grid.NoValue as exc:
                self._tapes[at] = str(exc)
        return self._tapes[at]

    def says(self, rule: grid.Rule, point: Mapping[str, Any]) -> Said:
        missing = [name[5:] for name in self._loads_of(rule) if name not in point]
        if missing:
            return Said(rule.id, "nothing", f"the part carries no {' and no '.join(missing)}, which the rule reads", "load")
        tape = self._tape(rule, point)
        if isinstance(tape, str):
            return Said(rule.id, "nothing", tape, "value")
        v, chose = _values(tape, [point[label] for label in tape.labels])
        mark = tuple(sorted(chose.items()))

        def lacking(*ids: int) -> Said | None:
            reason = next((v[i] for i in ids if isinstance(v[i], str)), None)
            if reason is None:
                return None
            origin = v.index(reason)
            return Said(rule.id, "nothing", f"{tape.picks[origin]} gives no value here" if origin in tape.picks else reason, "value", mark=mark)

        for low, high, why in tape.where:
            if lacking(low, high) is not None:
                return lacking(low, high)
            if _middle(v[low]) > _middle(v[high]):
                return Said(rule.id, "nothing", f"outside its range: {why}", "range", mark=(*mark, why))
        if lacking(tape.low, tape.high) is not None:
            return lacking(tape.low, tape.high)
        low, high = _middle(v[tape.low]), _middle(v[tape.high])
        return Said(rule.id, "holds" if low <= high else "fails", low=low, high=high, mark=mark)

    def answer(self, mechanism: str, point: Mapping[str, Any], keep: bool = True) -> Answer:
        """What the transcription says of the mechanism for the part at this point. It is
        kept for the next time the point is asked about, unless `keep` is false."""
        at = (mechanism, tuple((name, x) if type(x) is str else (name, x.numerator, x.denominator) for name, x in point.items()))
        if at not in self._answers:
            ask = self.asks[mechanism]
            if ask.excused is not None and _is(ask.unless, point):
                found = Answer("cannot arise", ask.excused)
            else:
                said = tuple(self.says(r, point) for r in self.rules[mechanism] if _is(r.when, point))
                silent = next((s for s in said if s.state == "nothing"), None)
                if not said:
                    found = Answer("open", "no rule answers for a part like this one", (), "no rule")
                elif any(s.state == "fails" for s in said):
                    found = Answer("fails", "", said)
                else:
                    found = Answer("open", silent.why, said, silent.kind) if silent is not None else Answer("holds", "", said)
            if not keep:
                return found
            self._answers[at] = found
        return self._answers[at]


# --- parts to try ----------------------------------------------------------------------------------------


def places(node: Any, path: tuple = ()) -> Iterator[tuple[tuple, Any]]:
    """Every node of a JSON tree with the path that reaches it."""
    yield path, node
    for key, child in (enumerate(node) if isinstance(node, list) else node.items() if isinstance(node, dict) else ()):
        yield from places(child, (*path, key))


def put(tree: Any, path: tuple, new: Any) -> Any:
    """The tree with the node at the path replaced. The tree itself is not changed."""
    if not path:
        return new
    out = list(tree) if isinstance(tree, list) else dict(tree)
    out[path[0]] = put(tree[path[0]], path[1:], new)
    return out


@dataclass(frozen=True)
class Parts:
    """The parts tried for one mechanism: `base`, spread over the type's keys and ranges,
    and for the first of them a `partner`, the same part with other sizes and loads.
    `fixed` names the quantities a partner keeps: a count, and a size read at listed values."""

    kind: str
    base: tuple[Mapping[str, Any], ...]
    partners: tuple[Mapping[str, Any], ...]
    fixed: frozenset[str]
    said: str

    @property
    def pairs(self) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
        return list(zip(self.base, self.partners))


def _marks(readings: list[Reading], mechanism: str) -> dict[str, tuple[tuple[Fraction, ...], tuple[Fraction, ...]]]:
    """For each quantity that a rule binds straight to the side of a table: the values the
    table lists, where it gives a line for each listed value, and the values on and beside
    the ends of its bands and between its listed values. A table read at listed values gives
    nothing elsewhere, so a part must sit on them."""
    listed: dict[str, set[Fraction]] = collections.defaultdict(set)
    beside: dict[str, set[Fraction]] = collections.defaultdict(set)
    for reading in readings:
        for rule in reading.rules[mechanism]:
            for applied in rule.applied.values():
                for axis in applied.row.table.axes if applied.row.table is not None else ():
                    term = applied.quantities.get(axis.by)
                    while isinstance(term, Sym) and term.name in rule.lets:
                        term = rule.lets[term.name]
                    if isinstance(term, Sym) and not term.name.startswith(("@", "load ")):
                        listed[term.name] |= set(axis.at)
                        beside[term.name] |= {x for x in axis.probes() if x > 0 and x not in axis.at}
    return {name: (tuple(sorted(listed[name])), tuple(sorted(beside[name] - listed[name]))) for name in {*listed, *beside}}


def parts(task: Task, mechanism: str, readings: list[Reading], seed: int = 0, count: int = PARTS) -> Parts:
    """Parts of the mechanism's type as points: every combination of its keys, with and
    without each load that a rule or an `unless` asks to be `loaded`; each quantity spread
    over its range on a log scale, a count over its whole numbers, and a quantity that a
    rule binds to the side of a table on and beside that side's ends."""
    maybe = sorted({name for r in readings for cond in (r.asks[mechanism].unless, *(rule.when for rule in r.rules[mechanism])) for name in _loaded(cond)})
    return _sampled(task, mechanism, tuple(sorted(_marks(readings, mechanism).items())), tuple(maybe), seed, count)


@lru_cache(maxsize=64)
def _sampled(task: Task, mechanism: str, marked: tuple, maybe: tuple[str, ...], seed: int, count: int) -> Parts:
    kind = next(a.type for a in task.deck.asks if a.mechanism == mechanism)
    keys, sizes, loads = _names(task.deck, kind)
    spans, marks = task.spans[kind], dict(marked)
    rng = random.Random(f"{seed}/{task.name}/{mechanism}")
    combos = list(itertools.product(*([(name, k) for k in options] for name, options in keys.items()), *([(name, True), (name, False)] for name in maybe)))
    said = ""
    if len(combos) > count:
        said = f", {count} of the {len(combos)} combinations of its keys"
        combos = rng.sample(combos, count)

    def draw(name: str, marked: bool = True) -> Fraction:
        lo, hi = spans[name]
        listed, beside = marks.get(name, ((), ()))
        if name in sizes and sizes[name].whole:
            return Fraction(rng.randint(math.ceil(lo), math.floor(hi)))
        if marked and listed:
            return rng.choice(listed) if not beside or rng.random() < 15 / 16 else rng.choice(beside)
        if marked and beside and rng.random() < 1 / 4:
            return rng.choice(beside)
        if lo <= 0 or lo == hi:
            return lo + (hi - lo) * Fraction(rng.randrange(1001), 1000)
        return Fraction(f"{float(lo) * (float(hi) / float(lo)) ** rng.random():.5g}")

    base: list[dict[str, Any]] = []
    for combo in itertools.islice(itertools.cycle(combos), max(count, len(combos))):
        point: dict[str, Any] = {name: value for name, value in combo if not isinstance(value, bool)}
        absent = {name for name, value in combo if value is False}
        base.append({**point, **{name: draw(name) for name in (*sizes, *loads) if name not in absent}})
    for name, (listed, beside) in sorted(marks.items()):
        found = [*listed, *beside]
        for n, x in zip(rng.sample(range(len(base)), min(len(found), len(base))), found):
            base[n][name] = x
    fixed = {name for name in sizes if sizes[name].whole or marks.get(name, ((), ()))[0]}
    partners = [{name: x if isinstance(x, str) or name in fixed else draw(name, False) for name, x in point.items()} for point in base[:PARTNERS]]
    return Parts(kind, tuple(base), tuple(partners), frozenset(fixed), said)


def _between(a: Fraction, b: Fraction) -> Fraction:
    """A value about half way between two, in twelve digits, so that halving many times does not make long fractions."""
    if a == b:
        return a
    mid = Fraction(f"{(float(a) + float(b)) / 2:.12g}")
    return mid if min(a, b) < mid < max(a, b) else (a + b) / 2


def _along(answer: Callable[..., Answer], point: Mapping[str, Any], name: str, far: Fraction) -> list[Mapping[str, Any]]:
    """The parts on each side of the place where the answer stops holding or stops failing
    as one size or one load of the part moves to `far`, or none where it does not."""
    first, lo, hi = answer(point), point, {**point, name: far}
    if not first.settled or answer(hi).state == first.state:
        return []
    for _ in range(STEPS):
        mid = {**lo, name: _between(lo[name], hi[name])}
        if answer(mid, False).state == first.state:
            lo = mid
        else:
            hi = mid
    return [lo, hi]


def turns(answer: Callable[..., Answer], pairs: list[tuple[Mapping[str, Any], Mapping[str, Any]]]) -> list[Mapping[str, Any]]:
    """Parts on each side of a place where the answer changes, found by halving the way
    between two parts that differ in sizes and loads alone: TURNS places for each two ways
    the transcription treats a part."""
    seen: collections.Counter = collections.Counter()
    out: list[Mapping[str, Any]] = []
    for lo, hi in pairs:
        first, last = answer(lo), answer(hi)
        between = frozenset((first.mark, last.mark))
        if first.mark == last.mark or seen[between] >= TURNS:
            continue
        seen[between] += 1
        for _ in range(STEPS):
            mid = {name: x if isinstance(x, str) else _between(x, hi[name]) for name, x in lo.items()}
            if answer(mid, False).mark == first.mark:
                lo = mid
            else:
                hi = mid
        out += [lo, hi]
    return out


# --- the acceptance check ----------------------------------------------------------------------------------


def _shown(point: Mapping[str, Any], names: list[str]) -> str:
    """A part for a message: what the mechanism reads of it, in SI, and `no pull` for a load it does not carry."""
    return ", ".join(f"no {name[5:]}" if name not in point else f"{name.removeprefix('load ')}={point[name]}" if isinstance(point[name], str)
                     else f"{name.removeprefix('load ')}={float(point[name]):.6g}" for name in names if name in point or name.startswith("load ")) + " (SI)"


def _told(found: Answer) -> str:
    if found.state == "cannot arise":
        return f"says it cannot arise ({found.why})"
    if found.kind == "no rule":
        return "has no rule for a part like it"
    if found.state == "open":
        silent = next(s for s in found.said if s.state == "nothing")
        return f"says nothing ({silent.rule}: {silent.why})"
    g = found.governing
    return found.state + (f" at {float(found.ratio):.6g}" if found.ratio is not None else "") + f" ({g.rule}: {float(g.low):.6g} against {float(g.high):.6g})"


def _order(reading: Reading, mechanism: str, *others: Reading) -> list[str]:
    """The names the mechanism reads in any of the readings, in the order of the type's fields."""
    kind = reading.asks[mechanism].type
    read = set().union(*(r.reads(mechanism) for r in (reading, *others)))
    return [name for group in _names(reading.task.deck, kind) for name in group if name in read]


def units(mine: Reading, mechanism: str) -> Check:
    if mechanism in mine.wrong:
        return Check("units", "fail", mine.wrong[mechanism])
    count = len(mine.rules[mechanism])
    return Check("units", "pass", f"{count} rule{'s' if count != 1 else ''}" + (", and an `unless`" if mine.asks[mechanism].excused is not None else ""))


def _side_dim(mine: Reading, body: Mapping[str, Any]) -> Vector:
    """The dimension of a rule's two sides."""
    binder = grid._Binder(mine.task.deck.rows, mine.task.deck.types[body["type"]], mine.task.deck.types)
    for name, node in body.get("let", {}).items():
        binder.takes[name] = rows.Input(dim=binder.expr(node)[1])
    return binder.expr(body["le"][0])[1]


def reproduces(mine: Reading, mechanism: str, examples: list[Worked]) -> Check:
    """Whether the mechanism's rules reproduce each worked example: the left or the right
    side of the rule with the largest ratio, or that ratio. An example gives what its
    source states, so a rule that reads a field the example lacks does not reproduce it."""
    if not examples:
        return Check("examples", "none", "no worked example")
    bodies = {r["id"]: r for r in mine.said.rules if r.get("mechanism") == mechanism}
    rules, spans = mine.rules[mechanism], mine.task.spans[mine.asks[mechanism].type]
    misses = []
    for e in examples:
        lacks = (set(grid._keys(mine.asks[mechanism].unless)) | {n for r in rules for n in grid._keys(r.when)}) - set(e.part)
        lacks = lacks or {n for r in rules if _is(r.when, e.part) for n in grid._reads(r)} - set(e.part)
        # A source may print a strength and no load. The side it prints is then worked out under two loads, and must not move.
        loads_only = bool(lacks) and e.side != "ratio" and all(n.startswith("load ") for n in lacks)
        found = [mine.answer(mechanism, {**e.part, **{n: spans[n][1] / k for n in lacks}}) for k in ((1, 2) if loads_only else (1,))] if loads_only or not lacks else []
        got = [None if a.governing is None else a.ratio if e.side == "ratio" else a.governing.low if e.side == "left" else a.governing.high for a in found]
        if not found or (loads_only and got[0] != got[1]):
            misses.append(f"{e.anchor}: the rules read {', '.join(sorted(n.removeprefix('load ') for n in lacks))}, which the example does not give")
            continue
        governing = found[0].governing
        if governing is None:
            misses.append(f"{e.anchor}: for this part the transcription {_told(found[0])}")
        elif e.side != "ratio" and _side_dim(mine, bodies[governing.rule]) != e.dim:
            misses.append(f"{e.anchor}: prints a {show(e.dim)}, and the sides of {governing.rule} are a {show(_side_dim(mine, bodies[governing.rule]))}")
        elif got[0] is None or abs(got[0] - e.gives) > e.within * abs(e.gives):
            misses.append(f"{e.anchor}: prints {e.printed} for the {e.side}{' side' if e.side != 'ratio' else ''}, and {governing.rule} gives "
                          + ("no ratio" if got[0] is None else f"{float(got[0] / e.gives):.4f} of it"))
    return Check("examples", "fail" if misses else "pass", "; ".join(misses) or f"{len(examples)} reproduced")


def _unused(mine: Reading, mechanism: str, tried: Parts) -> list[str]:
    """Each argument of a `min` or a `max` that could be struck from a rule with no answer
    changing at a sampled part: nothing that was sampled shows what it is there for."""
    before = [mine.answer(mechanism, p) for p in tried.base]
    bodies = [r for r in mine.said.rules if r.get("mechanism") == mechanism]
    out = []
    for body in bodies:
        for path, node in places(body):
            if not (isinstance(node, list) and node[:1] in (["min"], ["max"]) and len(node) > 2 and path[0] in ("le", "let", "where")):
                continue
            for n in range(1, len(node)):
                kept = node[1:n] + node[n + 1:]
                cut = mine.with_rules(mechanism, [put(body, path, kept[0] if len(kept) == 1 else [node[0], *kept]) if r is body else r for r in bodies],
                                      mine.said.unless.get(mechanism))
                after = [cut.answer(mechanism, p) for p in tried.base]
                if mechanism not in cut.wrong and all(a.state == b.state and close(a.ratio, b.ratio) for a, b in zip(before, after)):
                    out.append(f"{body['id']}: {json.dumps(node[n])[:60]} never decides its {node[0]} in {' '.join(str(step) for step in path[:2])}")
    return out


def reach(mine: Reading, mechanism: str, tried: Parts, unused: bool = True) -> Check:
    """Whether the sampled parts put the mechanism's rules to work. It fails when the rules
    answer no part, or fail every part they answer: a rule that no part in the task's
    ranges can meet is wrong, or the ranges are. It is `none`, with what was not seen, when
    a rule holds at every part, a range holds at every part, or an argument of a min or a
    max never decides: the task's ranges are then too narrow to show what that is for."""
    found = [mine.answer(mechanism, p) for p in tried.base]
    states = collections.Counter(a.label for a in found)
    count = f"{len(found)} parts{tried.said}: " + ", ".join(f"{n} {state}" for state, n in sorted(states.items()))
    if not mine.rules[mechanism]:
        return Check("reach", "pass", count)
    said = [s for a in found for s in a.said]
    silent = sorted({r.id for r in mine.rules[mechanism]} - {s.rule for s in said if s.state != "nothing"})
    if silent:
        why = collections.Counter(s.why for s in said if s.rule in silent).most_common(1)
        return Check("reach", "fail", f"{', '.join(silent)} answers none of {count}" + (f"; mostly: {why[0][0]}" if why else "; its `when` holds for none"))
    if not states["holds"]:
        return Check("reach", "fail", f"it fails every part it answers, of {count}")
    notes = [f"{r.id} holds at every sampled part it answers" for r in mine.rules[mechanism] if not any(s.rule == r.id and s.state == "fails" for s in said)]
    notes += [f"{r.id}: its range holds at every sampled part ({why})" for r in mine.rules[mechanism] for _, _, why in r.where
              if not any(s.rule == r.id and s.kind == "range" and s.mark[-1:] == (why,) for s in said)]
    notes += _unused(mine, mechanism, tried) if unused else []
    return Check("reach", "none" if notes else "pass", "; ".join([*notes, count]) + ("; widen the task's ranges to see these" if notes else ""))


def direction(mine: Reading, mechanism: str, tried: Parts) -> Check:
    """Whether more of a load that the task calls adverse ever helps: a part that fails
    under less of it and holds under more. Swapped sides do that."""
    read = set().union(*(grid._reads(r) for r in mine.rules[mechanism]))
    loads = sorted(f"load {name}" for name in mine.task.adverse.get(tried.kind, ()) if f"load {name}" in read)
    if not loads:
        return Check("direction", "none", "its rules read no load that the task calls adverse")
    names, told = _order(mine, mechanism), 0
    for load in loads:
        lo, hi = mine.task.spans[tried.kind][load]
        for p in [p for p in tried.base if load in p][:TRIED]:
            found = [(x, mine.answer(mechanism, {**p, load: x})) for x in sorted({lo, p[load], hi * FAR})]
            settled = [(x, a) for x, a in found if a.settled]
            told += len(settled) > 1
            for (x, a), (y, b) in itertools.combinations(settled, 2):
                if a.state == "fails" and b.state == "holds":
                    return Check("direction", "fail", f"more {load[5:]} helps: at {_shown(p, names)} it {_told(a)} with {load[5:]}={float(x):.6g} and {_told(b)} with {load[5:]}={float(y):.6g}")
    if not told:
        return Check("direction", "none", "no sampled part has an answer under two values of the load")
    return Check("direction", "pass", f"more {' or '.join(load[5:] for load in loads)} turned no failing part into a holding one, at {told} parts")


def alike(mine: Reading, mechanism: str, tried: Parts) -> Check:
    """Whether the answer stays when two parts that the task calls alike change places. A
    rule that reads one plate's thickness with the other plate's strength does not."""
    read = {name.partition(".")[0] for name in mine.reads(mechanism) if "." in name}
    pairs = [pair for group in mine.task.alike.get(tried.kind, ()) for pair in itertools.combinations(group, 2) if read & set(pair)]
    if not pairs:
        return Check("alike", "none", "its rules read no parts that the task calls alike")
    names = _order(mine, mechanism)
    for a, b in pairs:
        swap = {a: b, b: a}
        for p in tried.base[:TRIED]:
            q = {(f"{swap[name.partition('.')[0]]}.{name.partition('.')[2]}" if name.partition(".")[0] in swap and "." in name else name): x for name, x in p.items()}
            x, y = mine.answer(mechanism, p), mine.answer(mechanism, q)
            if x.state != y.state or (x.settled and not close(x.ratio, y.ratio)):
                return Check("alike", "fail", f"with {a} and {b} changed places the answer changes: at {_shown(p, names)} it {_told(x)}, and changed round it {_told(y)}")
    return Check("alike", "pass", f"{' and '.join(f'{a} and {b}' for a, b in pairs)} changed places at {min(TRIED, len(tried.base))} parts")


def _differs(a: Answer, b: Answer) -> str:
    """What two answers differ on, in the order a reader would look."""
    if "cannot arise" in (a.state, b.state):
        return "whether it can arise"
    kind = a.kind or b.kind
    return {"": "whether the inequality holds", "no rule": "which parts a rule answers for", "range": "the range a rule holds in", "load": "the load a rule reads",
            "value": "where a row gives a value"}[kind]


def second(mine: Reading, other: Reading, mechanism: str, tried: Parts) -> Check:
    """Whether the other transcription gives each part the same answer for the mechanism:
    that it cannot arise, that it is open, or that the inequality holds or fails. Why an
    answer is open is not compared: a part that one leaves to no rule and the other puts
    outside a rule's range gets an open cell from both. Parts are the sampled ones, their
    partners, and the parts on each side of every place found where either transcription
    treats a part another way.

    Where both hold or both fail, the largest ratio of each is compared too, or the two
    sides where neither states a ratio. Equal ratios at every part mean one inequality.
    Unequal ratios may still be one inequality written two ways, as `a <= b` and
    `a - b <= 0` are. So from each of the first TRIED such parts the check moves one load,
    or failing that one size, until either transcription stops holding or stops failing,
    and asks that the other do so at the same place. It fails the two when fewer than half
    of these parts have such a place: they cannot be told the same."""
    if mechanism in other.wrong:
        return Check("second", "fail", f"the other transcription does not load: {other.wrong[mechanism]}")
    if not other.answers(mechanism):
        why = other.said.left_out.get(mechanism)
        return Check("second", "none", "the other transcription leaves it out" + (f": {why}" if why else ""))
    names = _order(mine, mechanism, other)
    ask = [lambda p, keep=True: mine.answer(mechanism, p, keep), lambda p, keep=True: other.answer(mechanism, p, keep)]

    def compared(points: list[Mapping[str, Any]]) -> tuple[list[tuple], list[tuple]]:
        differ, forms = [], []
        for p in points:
            a, b = ask[0](p), ask[1](p)
            if a.state != b.state:
                differ.append((_differs(a, b), p, a, b))
            elif a.settled and not (close(a.ratio, b.ratio) and (a.ratio is not None or (close(a.governing.low, b.governing.low) and close(a.governing.high, b.governing.high)))):
                forms.append((p, a, b))
        return differ, forms

    points = [*tried.base, *tried.partners, *(p for f in ask for p in turns(f, tried.pairs))]
    differ, forms = compared(points)
    settled = sum(ask[0](p).settled and ask[1](p).settled for p in points)
    said = f"{len(points)} parts{tried.said}"
    counts = len(mine.rules[mechanism]), len(other.rules[mechanism])
    passed = said + (f", which hold or fail at {settled}" if settled else "") + (f", {counts[0]} rule{'s' if counts[0] != 1 else ''} against {counts[1]}" if counts[0] != counts[1] else "")
    ratios = f"another ratio at {len(forms)} of the {settled} parts that hold or fail"
    if not differ and forms:
        spans = mine.task.spans[tried.kind]
        axes = [n for n in names if n.startswith("load ")] + [n for n in names if n in spans and not n.startswith("load ") and n not in tried.fixed]
        turned = 0
        for p, _, _ in forms[:TRIED]:
            beside = next((found for name in axes if name in p for far in (spans[name][1] * FAR, spans[name][0] / FAR) for f in ask if (found := _along(f, p, name, far))), [])
            turned += bool(beside)
            differ += compared(beside)[0]
        p, a, b = forms[0]
        shown = f"at {_shown(p, names)} this one {_told(a)} and the other {_told(b)}"
        if not differ and 2 * turned < min(TRIED, len(forms)):
            return Check("second", "fail", f"the two give {ratios}, and from {turned} of the first {min(TRIED, len(forms))} a load or a size was found that turns either answer, "
                                           f"too few to tell whether the two are one inequality: {shown}")
        if not differ:
            return Check("second", "pass", f"{passed}; the two write the inequality in different forms: they give {ratios}, "
                                           f"and from {turned} of the first {min(TRIED, len(forms))} each turns at the same place: {shown}")
    if differ:
        kinds = collections.Counter(d[0] for d in differ)
        what, p, a, b = next(d for d in differ if d[0] == kinds.most_common(1)[0][0])
        count = f"{len(differ)} part{'s' if len(differ) != 1 else ''}" if forms else f"{len(differ)} of {said}"
        return Check("second", "fail", f"the two give another answer at {count}, " + ", ".join(f"{n} on {kind}" for kind, n in kinds.most_common()) + (f", and {ratios}" if forms else "")
                     + f". At {_shown(p, names)} this one {_told(a)} and the other {_told(b)}")
    return Check("second", "pass", passed)


def reads(mine: Reading) -> Check:
    """Whether something reads every key, every quantity and every load of each type the
    task asks about, in the names a rule reads them under. `petra check` leaves a design
    open at a field nothing reads."""
    unread = []
    for kind in dict.fromkeys(a.type for a in mine.task.deck.asks):
        read = set().union(*(mine.reads(m) for m in mine.task.mechanisms if mine.asks[m].type == kind))
        unread += [f"{kind}.{name.removeprefix('load ')}" for group in _names(mine.task.deck, kind) for name in group if name not in read]
    if not unread:
        return Check("reads", "pass", "every field and every load is read")
    open_ = [m for m in mine.task.mechanisms if not mine.answers(m) or m in mine.wrong]
    return Check("reads", "fail", f"nothing reads {', '.join(unread)}" + (f"; {len(open_)} mechanisms have no rule that loads, and one of them may" if open_ else ""))


@dataclass(frozen=True)
class Line:
    """The check on one mechanism: `admitted` when no part fails, `refused` when one does,
    and `left out` when the transcription says nothing of it."""

    mechanism: str
    state: str
    rules: tuple[str, ...]
    checks: tuple[Check, ...]
    note: str = ""


def checks(mine: Reading, mechanism: str, examples: list[Worked], tried: Parts, unused: bool = True) -> list[Check]:
    """The parts of the check that need no second transcription."""
    if mechanism in mine.wrong:
        return [units(mine, mechanism)]
    if not mine.rules[mechanism]:
        return [units(mine, mechanism), reproduces(mine, mechanism, examples)] if examples else [units(mine, mechanism)]
    return [units(mine, mechanism), reproduces(mine, mechanism, examples), reach(mine, mechanism, tried, unused), direction(mine, mechanism, tried), alike(mine, mechanism, tried)]


def accept(mine: Reading, examples: Mapping[str, list[Worked]] | None = None, other: Reading | None = None, seed: int = 0) -> tuple[list[Line], Check]:
    """The acceptance check on a transcription: a line for each mechanism the task asks, and
    `reads` for the whole. A mechanism is admitted when no part of its check fails. The
    parts that are `none` say how much stands behind it."""
    lines = []
    for mechanism in mine.task.mechanisms:
        ids = tuple(r.id for r in mine.rules[mechanism])
        if not mine.answers(mechanism):
            theirs = "" if other is None else "the other transcription answers it" if other.answers(mechanism) else "the other transcription leaves it out too"
            lines.append(Line(mechanism, "left out", ids, (), "; ".join(x for x in (mine.said.left_out.get(mechanism, ""), theirs) if x)))
            continue
        tried = parts(mine.task, mechanism, [mine, *([other] if other is not None else [])], seed)
        found = checks(mine, mechanism, (examples or {}).get(mechanism, []), tried)
        if mechanism not in mine.wrong:
            found.append(second(mine, other, mechanism, tried) if other is not None else Check("second", "none", "no second transcription"))
        excused, partly = mine.asks[mechanism].excused, mine.said.left_out.get(mechanism)
        notes = [f"cannot arise{' for some parts' if mine.asks[mechanism].unless is not None else ''}: {excused}"] if excused is not None else []
        lines.append(Line(mechanism, "refused" if any(c.outcome == "fail" for c in found) else "admitted", ids, tuple(found), "; ".join([*notes, *([f"left out: {partly}"] if partly else [])])))
    return lines, reads(mine)


def load(task: Task, path: str) -> Reading:
    return Reading(task, read_transcription(json.loads(Path(path).read_text(encoding="utf-8"))))


def render(lines: list[Line], whole: Check, stray: list[str]) -> list[str]:
    out = []
    for line in lines:
        out.append(f"{line.mechanism}: {'REFUSED' if line.state == 'refused' else line.state}" + (f"  {', '.join(line.rules)}" if line.rules else "") + (f"  ({line.note})" if line.note else ""))
        out += [f"  {c.name:<10} {c.outcome:<5} {c.detail}" for c in line.checks]
    out.append(f"{whole.name:<12} {whole.outcome:<5} {whole.detail}")
    return out + [f"stray        {s}" for s in stray]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m petra.rule", description="Run the acceptance check on the rules written for a task.")
    parser.add_argument("task", help="a JSON file: the types, the rows and the mechanisms to answer")
    parser.add_argument("rules", help="a transcription, or a deck, whose rules and `unless` are read as one")
    parser.add_argument("--second", help="a second transcription of the same task, to compare")
    parser.add_argument("--examples", help='worked examples, a JSON file {"examples": {MECHANISM: [...]}}')
    args = parser.parse_args(argv)
    try:
        task = read_task(json.loads(Path(args.task).read_text(encoding="utf-8")), Path(args.task).parent)
        mine, other = load(task, args.rules), load(task, args.second) if args.second else None
        given = json.loads(Path(args.examples).read_text(encoding="utf-8"))["examples"] if args.examples else {}
        lines, whole = accept(mine, {m: [worked(e, task, m) for e in found] for m, found in given.items()}, other)
    except (DeckError, OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"petra.rule: {exc}", file=sys.stderr)
        return 3
    print("\n".join(render(lines, whole, mine.stray)))
    return 1 if whole.outcome == "fail" or mine.stray or any(line.state == "refused" for line in lines) else 0


if __name__ == "__main__":
    sys.exit(main())
