"""The grid: what a deck asks of each part of a design, and the answer to each. Trusted.

A deck (docs/deck.md) holds rows, types, a grid and rules. A row is one equation or one
table of a standard (petra/deck.py). A type is a kind of part: its fields, and the loads a
card may put on it. The grid lists, for each type, every mechanism a part of that type must
answer for. A rule answers one mechanism of one type: it binds the inputs of rows to the
fields of a part and states an inequality.

For a design whose parts are all of a deck's types, this module makes one cell for each
answer and writes the files of docs/format.md:

    proved          a rule's inequality holds for every value the card and the design allow
    refuted         it fails at a point they allow
    not_applicable  the deck says the mechanism cannot arise for this part, and why
    waived          the card waives the mechanism on the part
    open            anything else: no rule, a rule that reads what the card does not give,
                    a value outside a rule's range, or an inequality neither proved nor refuted

No cell has a default. The verdict is PASS only when no cell is refuted or open and at
least one is proved.

petra-verify reads the deck's file, the card and the design and works out every cell and
every tape again (kernel/Petra/Deck.lean and Grid.lean). proofs.json carries no tape: for a
proved cell it holds the partition this module found, and for a refuted one the point, each
input named by its label. `checked` compares the kernel's cells with this module's, one by
one, so what this module decides alone is what a report says of a cell beyond its state:
the reason, the ratio and the words.
"""
from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from . import deck as rows
from . import export
from .deck import NONE, RowError, Vector, anchored, dimension, only, quantity, replaced, show
from .ir import Bound, Component, Design, Fixed, ParamRef, Ref, Span, Text
from .kernel import (Abs, Add, Const, Div, Exp, Interval, KernelArithmeticError, Ln, Max, Min, Mul, Neg, Pi, PowInt, Sqrt, Sym,
                     enclose)
from .models.base import ComponentError

FORMAT = "petra-rules/0"
DECKS = Path(__file__).resolve().parent / "decks"
STATES = ("proved", "refuted", "not_applicable", "waived", "open")
MAX_CHOICES = 4096
"""The most ways a pick may order what it compares, as in kernel/Petra/Tape.lean."""
MAX_LEAVES = 256
"""The most leaves a partition may have before the search for a proof stops."""
MAX_CORNERS = 6
"""A refuting point is looked for at the corners of the box while no more inputs than this have a range."""
MAX_NAME = 64
"""The most bytes a name may print in that a cell prints whole, as in kernel/Petra/Files.lean:
the name of a part, a load case, a mechanism, a field, a load, a joined part and a `let`, and a rule's id."""
UNREAD = "unread"
"""The mechanism of the cell of a field that nothing reads. No line of the grid has this name."""


class DeckError(ValueError):
    """A deck that does not hold together: an unknown key, a rule that names a row or a
    field the deck lacks, or dimensions that do not agree."""


# --- a deck ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Field:
    """One field of a type or one load on it. A quantity has `dim`, a key has `keys`, and a
    reference has `type`, the type of the parts it names, and `names`, what a rule calls
    each of them in order. Only the card states a `signed` quantity. A `whole` quantity is
    a count. `least` is the least value a quantity may take, in SI."""

    name: str
    what: str
    dim: Vector | None = None
    keys: tuple[str, ...] = ()
    type: str | None = None
    names: tuple[str, ...] = ()
    signed: bool = False
    whole: bool = False
    least: Fraction | None = None


@dataclass(frozen=True)
class Type:
    name: str
    what: str
    fields: Mapping[str, Field]
    loads: Mapping[str, Field]


@dataclass(frozen=True)
class Ask:
    """One line of the grid: a mechanism every part of the type answers for. `excused` is
    why the mechanism cannot arise, and holds when `unless` does, or always when there is
    no `unless`."""

    type: str
    mechanism: str
    what: str
    anchor: Mapping[str, str]
    unless: tuple | None = None
    excused: str | None = None


@dataclass(frozen=True)
class Applied:
    """A row with its inputs bound: a quantity to an expression, a key to a selector."""

    row: rows.Row
    quantities: Mapping[str, Any]
    keys: Mapping[str, tuple]


@dataclass(frozen=True)
class Rule:
    """An answer to one mechanism of one type: `low <= high`, read where every `where`
    holds. The expressions are kernel terms over names: a field, `part.field`, a `let`
    name, `load NAME`, or `@n` for the n-th row the rule applies."""

    id: str
    type: str
    mechanism: str
    anchor: Mapping[str, str]
    says: str
    when: tuple | None
    lets: Mapping[str, Any]
    where: tuple[tuple[Any, Any, str], ...]
    low: Any
    high: Any
    applied: Mapping[str, Applied]


@dataclass(frozen=True, eq=False)
class Deck:
    """`text` is the deck's file as it was read, which the kernel reads again, and `hash` its hash."""

    name: str
    hash: str
    rows: Mapping[str, rows.Row]
    types: Mapping[str, Type]
    asks: tuple[Ask, ...]
    rules: tuple[Rule, ...]
    text: str = ""


def _anchor(a: Mapping[str, str]) -> str:
    parts = [a["standard"], a["clause"], *(f"{word} {a[key]}" for key, word in (("equation", "equation"), ("table", "Table")) if a.get(key))]
    return " ".join(parts[:2]) + "".join(f", {p}" for p in parts[2:])


def _long(name: Any) -> bool:
    """Whether the kernel would print this name in more than MAX_NAME bytes, counted as
    `printed` in kernel/Petra/Files.lean counts them: two for a quote, a backslash and a
    line end, six for any other control character, and the bytes of its UTF-8 otherwise."""
    return isinstance(name, str) and sum(2 if c in '"\\\n\r' else 6 if c < " " else len(c.encode("utf-8", "surrogatepass")) for c in name) > MAX_NAME


def _name(name: Any) -> bool:
    """Whether this can name a field, a load, a joined part or a `let`: letters, digits and
    `_`, as the language writes a name, and at most MAX_NAME of them. So `a.Fy` is always a
    field of a joined part, and no name reads as a number, a load or a row."""
    return isinstance(name, str) and name.isascii() and name.isidentifier() and not _long(name)


def _field(body: Mapping[str, Any], load: bool = False) -> Field:
    allowed = {"name", "what", "dim", "least"} if load else {"name", "what", "dim", "least", "one_of", "type", "as", "signed", "whole"}
    only(body, tuple(sorted(allowed)), f"field {body.get('name')!r}")
    if sum(key in body for key in ("dim", "one_of", "type")) != 1 or not (isinstance(body.get("what"), str) and body["what"]) or not _name(body.get("name")):
        raise DeckError(f"field {body.get('name')!r}: it has a name of letters, digits and _, `what`, a text, and one of `dim`, `one_of` and `type`, and may have {', '.join(sorted(allowed))}")
    name = body["name"]
    only(body, ("name", "what", "one_of") if "one_of" in body else ("name", "what", "type", "as") if "type" in body
         else ("name", "what", "dim", "least", "signed", "whole"), f"field {name}")
    if "one_of" in body:
        keys = tuple(str(k) for k in body["one_of"])
        if not keys or len(set(keys)) != len(keys):
            raise DeckError(f"field {name}: `one_of` is a list of different names")
        return Field(name, body["what"], keys=keys)
    if "type" in body:
        names = tuple(body.get("as", [name]))
        if not names or len(set(names)) != len(names) or not all(map(_name, names)):
            raise DeckError(f"field {name}: `as` names each part once, in letters, digits and _")
        return Field(name, body["what"], type=str(body["type"]), names=names)
    dim = dimension(body["dim"])
    least = None
    if "least" in body:
        least, least_dim = quantity(str(body["least"]), f"the least value of {name}")
        if least_dim != dim:
            raise DeckError(f"field {name}: its least value is a {show(least_dim)}, and the field is a {show(dim)}")
    whole = bool(body.get("whole"))
    if whole and dim != NONE:
        raise DeckError(f"field {name}: a count is a plain number")
    return Field(name, body["what"], dim=dim, signed=bool(body.get("signed")), whole=whole, least=least)


def _named(items: list, what: str, name: Callable[[Any], str]) -> dict[str, Any]:
    out = {name(i): i for i in items}
    if len(out) != len(items):
        raise DeckError(f"two {what} have one name")
    return out


class _Binder(rows._Reader):
    """The expressions of one rule. Adds to a row's language `["load", NAME]`, a load on
    the part, and `["row", ID, {INPUT: ...}]`, a row of the deck with each quantity it
    takes bound to an expression and each key to a key field, to `["key", NAME]`, or to
    `["by", FIELD, {its key: the row's key}]`."""

    def __init__(self, deck_rows: Mapping[str, rows.Row], kind: Type, types: Mapping[str, Type]) -> None:
        names: dict[str, rows.Input] = {}
        for f in kind.fields.values():
            if f.type is None:
                names[f.name] = rows.Input(dim=f.dim) if f.dim is not None else rows.Input(keys=f.keys)
                continue
            for part in f.names:
                for g in types[f.type].fields.values():
                    if g.type is None:
                        names[f"{part}.{g.name}"] = rows.Input(dim=g.dim) if g.dim is not None else rows.Input(keys=g.keys)
        super().__init__(names)
        self.rows, self.loads, self.applied = deck_rows, kind.loads, {}

    def expr(self, node: Any) -> tuple[Any, Vector]:
        if isinstance(node, list) and node[:1] == ["load"] and len(node) == 2:
            if node[1] not in self.loads:
                raise RowError(f"the type takes no load {node[1]!r}")
            return Sym(f"load {node[1]}"), self.loads[node[1]].dim
        if isinstance(node, list) and node[:1] == ["row"] and len(node) == 3:
            return self.apply(*node[1:])
        return super().expr(node)

    def apply(self, row_id: Any, binds: Any) -> tuple[Any, Vector]:
        if row_id not in self.rows or not isinstance(binds, dict):
            raise RowError(f"{row_id!r} is not a row of the deck, or its inputs are not an object")
        row = self.rows[row_id]
        if set(binds) != set(row.takes):
            raise RowError(f"{row_id} takes {', '.join(row.takes)}, and the rule binds {', '.join(binds) or 'nothing'}")
        quantities, keys = {}, {}
        for name, takes in row.takes.items():
            if takes.keys:
                keys[name] = self.key(binds[name], takes.keys, f"{row_id}: {name}")
                continue
            quantities[name], dim = self.expr(binds[name])
            if dim != takes.dim:
                self.problems.append(f"{row_id}: {name} is a {show(takes.dim)}, and the rule binds a {show(dim)}")
        name = f"@{len(self.applied)}"
        self.applied[name] = Applied(row, quantities, keys)
        return Sym(name), row.dim

    def key(self, node: Any, known: tuple[str, ...], what: str) -> tuple:
        def of(name: Any) -> tuple[str, ...]:
            if not isinstance(name, str) or name not in self.takes or not self.takes[name].keys:
                raise RowError(f"{what}: {name!r} is not a key field")
            return self.takes[name].keys

        if isinstance(node, str):
            if not set(of(node)) <= set(known):
                raise RowError(f"{what}: {node} has names the row lacks: {', '.join(sorted(set(of(node)) - set(known)))}")
            return ("field", node, {k: k for k in of(node)})
        if isinstance(node, list) and node[:1] == ["key"] and len(node) == 2 and node[1] in known:
            return ("field", None, {None: node[1]})
        if isinstance(node, list) and node[:1] == ["by"] and len(node) == 3 and isinstance(node[2], dict):
            if set(node[2]) != set(of(node[1])) or not set(node[2].values()) <= set(known):
                raise RowError(f"{what}: `by` gives one of the row's names for each name of {node[1]}")
            return ("field", node[1], dict(node[2]))
        raise RowError(f"{what}: a key is bound to a key field, to [\"key\", NAME] with one of {', '.join(known)}, or to [\"by\", FIELD, {{...}}]")

    def static(self, node: Any) -> tuple:
        """A condition on what a part is, not on how large: `["is", FIELD, NAME]`,
        `["loaded", LOAD]`, and `and`, `or`, `not` of these."""
        if isinstance(node, list) and node[:1] == ["is"] and len(node) == 3:
            if node[1] not in self.takes or node[2] not in self.takes[node[1]].keys or "." in node[1]:
                raise RowError(f"{node!r}: `is` names a key field of the type and one of its names")
            return ("is", node[1], node[2])
        if isinstance(node, list) and node[:1] == ["loaded"] and len(node) == 2 and node[1] in self.loads:
            return ("loaded", node[1])
        if isinstance(node, list) and node[:1] == ["not"] and len(node) == 2:
            return ("not", self.static(node[1]))
        if isinstance(node, list) and node[:1] in (["and"], ["or"]) and len(node) > 1:
            return (node[0], *(self.static(n) for n in node[1:]))
        raise RowError(f"{node!r} is not a condition on a part: write is, loaded, and, or, not")


def _rule(body: Mapping[str, Any], deck_rows: Mapping[str, rows.Row], types: Mapping[str, Type]) -> Rule:
    where = body.get("id")
    try:
        only(body, ("id", "type", "mechanism", "anchor", "says", "when", "let", "where", "le"), "a rule")
        if not isinstance(where, str) or _long(where):
            raise RowError(f"a rule has id, of at most {MAX_NAME} characters, type, mechanism, anchor, says, le, and may have when, let and where")
        anchor = anchored(body["anchor"], "anchor")
        for w in body.get("where", []):
            only(w, ("le", "why"), "where")
        if not body.get("says") or "where" in body and not body["where"]:
            raise RowError("a rule says what it states, and a `where` has at least one item")
        binder = _Binder(deck_rows, types[body["type"]], types)
        lets = {}
        for name, node in body.get("let", {}).items():
            if name in binder.takes or not _name(name) or name == "pi":
                raise RowError(f"`let` names {name}, which is a field, an earlier name or no name of letters, digits and _")
            lets[name], dim = binder.expr(node)
            binder.takes[name] = rows.Input(dim=dim)

        def pair(nodes: Any, what: str) -> tuple[Any, Any]:
            (low, low_dim), (high, high_dim) = (binder.expr(n) for n in nodes)
            if low_dim != high_dim:
                binder.problems.append(f"{what} compares a {show(low_dim)} with a {show(high_dim)}")
            return low, high

        low, high = pair(body["le"], "`le`")
        ranges = tuple((*pair(w["le"], "`where`"), str(w["why"])) for w in body.get("where", []))
        when = binder.static(body["when"]) if "when" in body else None
        if binder.problems:
            raise RowError("; ".join(dict.fromkeys(binder.problems)))
        return Rule(where, body["type"], body["mechanism"], anchor, body["says"], when, lets, ranges, low, high, binder.applied)
    except RowError as exc:
        raise DeckError(f"rule {where}: {exc}") from None
    except (KeyError, TypeError, ValueError) as exc:
        raise DeckError(f"rule {where}: not a rule ({type(exc).__name__}: {exc})") from None


def read_deck(text: str) -> Deck:
    """A deck from the text of its file. Raises DeckError for one that does not hold together."""
    try:
        body = json.loads(text)
        only(body, ("format", "name", "about", "rows", "types", "grid", "rules"), "a deck")
        if body.get("format") != FORMAT or replaced(body):
            raise DeckError(f"a deck has format {FORMAT}, name, about, rows, types, grid and rules, and no text of it holds U+FFFD or half a surrogate pair")
        found = [rows.read(r) for r in body["rows"]]
        wrong = [f"{r.id}: {p}" for r in found for p in r.problems]
        if wrong:
            raise DeckError("; ".join(wrong))
        deck_rows = _named(found, "rows", lambda r: r.id)
        for t in body["types"]:
            only(t, ("type", "what", "fields", "loads"), f"type {t.get('type')!r}")
        types = _named([Type(t["type"], t["what"], _named([_field(f) for f in t["fields"]], "fields", lambda f: f.name),
                             _named([_field(f, True) for f in t.get("loads", [])], "loads", lambda f: f.name)) for t in body["types"]],
                       "types", lambda t: t.name)
        for t in types.values():
            joined = [name for f in t.fields.values() for name in f.names]
            for f in t.fields.values():
                if f.type is not None and (f.type not in types or any(g.type for g in types[f.type].fields.values()) or len(set(joined)) != len(joined)):
                    raise DeckError(f"{t.name}.{f.name}: it names parts of a type the deck has, whose own fields name no parts, each by a name of its own")
        asks = []
        for a in body["grid"]:
            unless = a.get("unless")
            only(a, ("type", "mechanism", "what", "anchor", "unless"), f"grid {a.get('mechanism')}")
            anchor = anchored(a["anchor"], f"grid {a.get('mechanism')}: anchor")
            if unless is not None:
                only(unless, ("why", "when"), f"grid {a.get('mechanism')}: unless")
            if a["type"] not in types or _long(a["mechanism"]) or a["mechanism"] == UNREAD:
                raise DeckError(f"grid {a.get('mechanism')}: a line has a type of the deck, mechanism, of at most {MAX_NAME} characters and not `{UNREAD}`, what, anchor and may have unless")
            when = _Binder(deck_rows, types[a["type"]], types).static(unless["when"]) if unless is not None and "when" in unless else None
            asks.append(Ask(a["type"], a["mechanism"], a["what"], anchor, when, str(unless["why"]) if unless is not None else None))
        if len({(a.type, a.mechanism) for a in asks}) != len(asks):
            raise DeckError("the grid asks one mechanism of one type twice")
        rules = tuple(_rule(r, deck_rows, types) for r in body["rules"])
        asked = {(a.type, a.mechanism): a for a in asks}
        for r in rules:
            if (r.type, r.mechanism) not in asked or asked[r.type, r.mechanism].unless is None and asked[r.type, r.mechanism].excused is not None:
                raise DeckError(f"rule {r.id}: the grid does not ask {r.mechanism} of {r.type}, or says it never arises")
        _named(list(rules), "rules", lambda r: r.id)
        if len({(r.type, r.mechanism, r.id.rpartition("/")[2]) for r in rules}) != len(rules):
            raise DeckError("two rules for one line of the grid have ids that end alike after the last /, so their cells would have one entry")
        return Deck(str(body["name"]), export.sha256(text), deck_rows, types, tuple(asks), rules, text)
    except RowError as exc:
        raise DeckError(str(exc)) from None
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise DeckError(f"not a deck ({type(exc).__name__}: {exc})") from None


@lru_cache(maxsize=None)
def decks() -> tuple[Deck, ...]:
    """The decks that ship with Petra: each file of petra/decks whose format is FORMAT."""
    found = []
    for path in sorted(DECKS.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        if json.loads(text).get("format") == FORMAT:
            try:
                found.append(read_deck(text))
            except DeckError as exc:
                raise DeckError(f"{path.name}: {exc}") from None
    types = [t for d in found for t in d.types]
    if len(set(types)) != len(types):
        raise DeckError("two decks have a type of one name")
    return tuple(found)


def kinds() -> dict[str, Deck]:
    """Each type a design may use as a component kind, and the deck that has it."""
    return {name: d for d in decks() for name in d.types}


def mechanisms() -> frozenset[str]:
    return frozenset(a.mechanism for d in decks() for a in d.asks)


def owner(design: Design) -> Deck | None:
    """The deck whose types the design's components are, or None for a design of the
    models' kinds. A design of both, or of two decks, is refused."""
    known = kinds()
    found = {known.get(c.kind) for c in design.components.values()}
    if found <= {None}:
        return None
    if len(found) > 1:
        names = sorted(c.name for c in design.components.values() if known.get(c.kind) is None)
        raise ComponentError((f"{design.path}: a design is checked against one deck, and this one has parts of "
                              f"{' and '.join(sorted(d.name if d else 'the built-in models' for d in found))}"
                              + (f" ({', '.join(names)} are the models')" if names else ""),))
    return found.pop()


# --- a design as parts -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Value:
    """A quantity as a tape reads it: the label of its premise and its range in SI."""

    label: str
    range: Interval


@dataclass(frozen=True)
class Part:
    """A component of a deck's type: each field's Value, key or the names of the parts it joins."""

    name: str
    type: Type
    values: Mapping[str, Any]
    loads: Mapping[str, Mapping[str, Value]]      # load field -> load case -> its value


@dataclass(frozen=True)
class Parts:
    parts: Mapping[str, Part]


def _at(span: Span) -> str:
    return f"{span.path}:{span.line}:{span.col}"


def _quantity(f: Field, kind: str, arg: Any, name: str, design: Design, say: Callable[[str], None]) -> Value | None:
    if isinstance(arg, ParamRef):
        return say("reads a param, and a family is not checked against a deck yet")
    if not isinstance(arg, (Fixed, Bound)):
        return say(f"is a {show(f.dim)}: write a number with its unit, or `given NAME`")
    q = arg.quantity if isinstance(arg, Fixed) else arg.range
    if rows._vector(q.dim) != f.dim:
        return say(f"is a {show(f.dim)}, not a {show(rows._vector(q.dim))}")
    if q.value.lo <= 0:
        return say("is not more than zero")
    if f.least is not None and q.value.lo < f.least:
        return say(f"is under {float(f.least):g} in SI units, the least a {kind} has: {f.what}")
    if isinstance(arg, Bound):
        if f.whole:
            return say("is a count, which the design writes as a whole number")
        if arg.name != name:
            return say(f"reads `given {arg.name}`, and a part reads only the bound the card gives for it: `given {name}`")
        return Value(f"in:{design.name}.{name}", q.value)
    if f.signed:
        return say(f"is for the card to state: write `{f.name} given {name}`, with `given {name} in [...] signed ...` in the card")
    if f.whole and (q.value.lo != q.value.hi or q.value.lo.denominator != 1):
        return say("is a count: a whole number")
    return Value(f"dsg:{design.name}.{name}", q.value)


def read_parts(design: Design, deck: Deck) -> Parts:
    """The design's components as parts of the deck's types, with the card's loads on them.
    Raises ComponentError with every problem: an unknown or repeated line, a missing
    field, a wrong unit or name, a quantity only the card may state, a load the type does
    not take, and anything of the card a deck does not read yet."""
    problems: list[str] = []
    parts: dict[str, Part] = {}
    problems += [f"{_at(x.span)}: the name of a part and of a load case is at most {MAX_NAME} characters, and {x.name[:MAX_NAME]}... is longer"
                 for x in (*design.components.values(), *design.loads.values()) if _long(x.name)]
    problems += [f"{_at(x.span)}: the name of a load case holds no /, and {x.name} has one" for x in design.loads.values() if "/" in x.name]
    for c in design.components.values():
        kind, values = deck.types[c.kind], {}
        for attr in c.attrs:
            def say(message: str, attr=attr) -> None:
                problems.append(f"{_at(attr.span)}: {c.name}.{attr.key} {message}")

            f = kind.fields.get(attr.key)
            if f is None:
                say(f"is not a line of a {kind.name}, which has: {', '.join(kind.fields)}")
            elif attr.key in values:
                say("is given twice")
            elif f.type is not None:
                named = [a.parts[0] for a in attr.args if isinstance(a, Ref) and len(a.parts) == 1]
                others = {n: design.components[n].kind for n in named if n in design.components}
                if len(named) != len(attr.args) or len(named) != len(f.names) or len(set(named)) != len(named) or set(others.values()) != {f.type} or len(others) != len(named):
                    say(f"names {len(f.names)} different {f.type} parts of this design")
                else:
                    values[attr.key] = tuple(named)
            elif len(attr.args) != 1:
                say("takes one value")
            elif f.keys:
                arg = attr.args[0]
                word = arg.value if isinstance(arg, Text) else arg.parts[0] if isinstance(arg, Ref) and len(arg.parts) == 1 else None
                if word not in f.keys:
                    say(f"is one of: {', '.join(repr(k) if ' ' in k else k for k in f.keys)}" + (" (in quotes)" if any(" " in k for k in f.keys) else ""))
                else:
                    values[attr.key] = word
            else:
                found = _quantity(f, kind.name, attr.args[0], f"{c.name}.{attr.key}", design, say)
                if found is not None:
                    values[attr.key] = found
        missing = [name for name in kind.fields if name not in values and not any(a.key == name for a in c.attrs)]
        if missing:
            problems.append(f"{_at(c.span)}: {c.name} lacks {', '.join(missing)}")
        parts[c.name] = Part(c.name, kind, values, {})
    loads: dict[str, dict[str, dict[str, Value]]] = {name: {} for name in parts}
    for case in design.loads.values():
        for e in case.entries:
            part = parts.get(e.target[0]) if len(e.target) == 1 else None
            f = part.type.loads.get(e.field) if part else None
            where = f"{_at(case.span)}: load {case.name}: {'.'.join(e.target)} {e.field}"
            if f is None:
                problems.append(f"{where}: " + (f"a {part.type.name} takes: {', '.join(part.type.loads) or 'no load'}" if part else "a load is put on a part"))
            elif isinstance(e.value, ParamRef):
                problems.append(f"{where} reads a param, and a family is not checked against a deck yet")
            elif rows._vector(e.value.range.dim) != f.dim:
                problems.append(f"{where} is a {show(f.dim)}")
            elif f.least is not None and e.value.range.value.lo < f.least:
                problems.append(f"{where} is at least {float(f.least):g} in SI units: {f.what}")
            else:
                loads[part.name].setdefault(e.field, {})[case.name] = Value(f"in:{design.name}.{e.value.name}", e.value.range.value)
    joined: dict[str, list[str]] = {}
    for p in parts.values():
        for f in p.type.fields.values():
            for other in p.values.get(f.name, ()) if f.type is not None else ():
                joined.setdefault(other, []).append(p.name)
    problems += [f"{design.path}: {name} is joined by {' and '.join(by)}, and a deck has no rule yet for a part that two others load"
                 for name, by in joined.items() if len(by) > 1]
    asked = {(a.type, a.mechanism) for a in deck.asks}
    for w in design.waivers:
        part = parts.get(w.subject[0]) if len(w.subject) == 1 else None
        if part is None or (part.type.name, w.mode) not in asked:
            problems.append(f"{_at(w.span)}: waive {w.mode} on {'.'.join(w.subject)}: the deck asks "
                            + (f"of a {part.type.name}: {', '.join(a.mechanism for a in deck.asks if a.type == part.type.name) or 'nothing'}" if part else "only of a part"))
    unread = [("a claim", design.claims), ("a probability claim", design.probability_claims), ("a tests record", design.tests),
              ("an ambient", design.ambient), ("a param", design.params)]
    problems += [f"{design.path}: the card or the design states {what}, which a deck does not read yet" for what, there in unread if there]
    if problems:
        raise ComponentError(tuple(problems))
    return Parts({name: Part(name, p.type, p.values, loads[name]) for name, p in parts.items()})


# --- a tape ----------------------------------------------------------------------------------------


class NoValue(Exception):
    """Something a rule reads has no value for this part: the reason, for the cell's `why`."""


class _Tape:
    """The nodes of docs/format.md, each built once from earlier ones."""

    def __init__(self) -> None:
        self.inputs: list[Value] = []
        self.nodes: list[list] = []
        self.seen: dict[str, int] = {}
        self.picks: dict[int, str] = {}      # a pick node -> the row it reads

    def node(self, *node: Any) -> int:
        key = json.dumps(node)
        if key not in self.seen:
            self.seen[key] = len(self.nodes)
            self.nodes.append(list(node))
        return self.seen[key]

    def const(self, x: Fraction) -> int:
        return self.node("c", export.number(x))

    def input(self, value: Value) -> int:
        if value not in self.inputs:
            self.inputs.append(value)
        return self.node("s", self.inputs.index(value))

    def emit(self, e: Any, env: Callable[[str], int]) -> int:
        many = {Add: "add", Mul: "mul", Min: "min", Max: "max"}
        one = {Neg: "neg", Sqrt: "sqrt", Ln: "ln", Exp: "exp", Abs: "abs"}
        if isinstance(e, Const):
            return self.const(e.value)
        if isinstance(e, Sym):
            return env(e.name)
        if isinstance(e, Pi):
            return self.node("pi")
        if type(e) in many:
            return self.node(many[type(e)], [self.emit(x, env) for x in e.args])
        if type(e) in one:
            return self.node(one[type(e)], self.emit(e.arg, env))
        if isinstance(e, Div):
            return self.node("div", self.emit(e.num, env), self.emit(e.den, env))
        if isinstance(e, PowInt):
            return self.node("pow", self.emit(e.base, env), e.exponent)
        raise TypeError(type(e).__name__)

    def cond(self, c: tuple, env: Callable[[str], int]) -> list:
        if c[0] in ("and", "or"):
            return [c[0], [self.cond(x, env) for x in c[1:]]]
        if c[0] == "not":
            return ["not", self.cond(c[1], env)]
        a, b = self.emit(c[1], env), self.emit(c[2], env)
        return {"le": ["le", a, b], "lt": ["lt", a, b], "ge": ["le", b, a], "gt": ["lt", b, a]}[c[0]]

    def pick(self, cases: list[tuple[Any, int]], what: str) -> int:
        """The first case that holds. A lone case that holds otherwise is its value."""
        if not cases:
            raise NoValue(f"{what} gives nothing here")
        if cases[0][0] is None:
            return cases[0][1]
        at = self.node("pick", [[c, v] for c, v in cases])
        self.picks.setdefault(at, what)
        return at

    def row(self, row: rows.Row, quantities: Mapping[str, int], keys: Mapping[str, str]) -> int:
        """The row's value with each quantity it takes at a node and each key at a name."""
        if row.table is None:
            return self.pick([(None if c.when is None else self.cond(c.when, quantities.__getitem__), self.emit(c.expr, quantities.__getitem__))
                              for c in row.cases], row.id)
        table = row.table

        def places(axis: rows.Axis) -> list[tuple[int, Any]]:
            if axis.keys:
                return [(axis.keys.index(keys[axis.by]), None)]
            x = quantities[axis.by]
            if axis.at:
                return [(n, ["and", [["le", x, self.const(v)], ["le", self.const(v), x]]]) for n, v in enumerate(axis.at)]
            out = []
            for n, (lo, hi) in enumerate(axis.bands):
                ends = [["lt" if axis.upper else "le", self.const(lo), x], *([["le" if axis.upper else "lt", x, self.const(hi)]] if hi is not None else [])]
                out.append((n, ends[0] if len(ends) == 1 else ["and", ends]))
            return out

        across = places(table.axes[1]) if len(table.axes) == 2 else [(0, None)]

        def line(i: int) -> int | None:
            there = [(c, self.const(table.cells[i][j])) for j, c in across if table.cells[i][j] is not None]
            return self.pick(there, row.id) if there else None

        return self.pick([(c, line(i)) for i, c in places(table.axes[0]) if line(i) is not None], row.id)


def _env(tape: _Tape, rule: Rule, part: Part, parts: Mapping[str, Part], case: str | None) -> Callable[[str], int]:
    """What each name of a rule's expressions is on the tape, for one part and one load case."""
    memo: dict[str, int] = {}

    def field_of(name: str) -> Any:
        if "." not in name:
            return part.values[name]
        alias, _, inner = name.partition(".")
        for f in part.type.fields.values():
            if alias in f.names and f.type is not None:
                return parts[part.values[f.name][f.names.index(alias)]].values[inner]
        raise KeyError(name)

    def find(name: str) -> int:
        if name not in memo:
            if name.startswith("load "):
                memo[name] = tape.input(part.loads[name[5:]][case])
            elif name in rule.applied:
                a = rule.applied[name]
                keys = {k: by[field_of(f) if f is not None else None] for k, (_, f, by) in a.keys.items()}
                memo[name] = tape.row(a.row, {q: tape.emit(e, find) for q, e in a.quantities.items()}, keys)
            elif name in rule.lets:
                memo[name] = tape.emit(rule.lets[name], find)
            else:
                memo[name] = tape.input(field_of(name))
        return memo[name]

    return find


# --- the interval rule, a second time ----------------------------------------------------------------


class _Failed(Exception):
    pass


_ONE = {"neg": Neg, "abs": Abs, "sqrt": Sqrt, "ln": Ln, "exp": Exp}
_MANY = {"add": Add, "mul": Mul, "min": Min, "max": Max}


def _atoms(cond: Any) -> Iterator[tuple[int, int]]:
    if cond is None:
        return
    if cond[0] in ("le", "lt"):
        yield min(cond[1:]), max(cond[1:])
    else:
        for inner in (cond[1] if cond[0] in ("and", "or") else [cond[1]]):
            yield from _atoms(inner)


def _holds(cond: Any, order: Mapping[tuple[int, int], int]) -> bool:
    if cond is None:
        return True
    op = cond[0]
    if op == "not":
        return not _holds(cond[1], order)
    if op in ("and", "or"):
        return (all if op == "and" else any)(_holds(c, order) for c in cond[1])
    i, j = cond[1], cond[2]
    sign = order[min(i, j), max(i, j)] * (1 if i <= j else -1)
    return sign <= 0 if op == "le" else sign < 0


def enclosures(nodes: list[list], box: list[Interval]) -> list[Any]:
    """The enclosure of each node over the box, or the reason it has none, as a string. The
    rule is kernel/Petra/Tape.lean's: a node that reads a node with no value has none, and
    a pick reads only what it compares and the cases some ordering chooses."""
    v: list[Any] = []

    def get(i: int) -> Interval:
        if isinstance(v[i], str):
            raise _Failed(v[i])
        return v[i]

    def op(term: Any, ids: list[int]) -> Interval:
        return enclose(term, {str(k): get(i) for k, i in enumerate(ids)})

    def step(node: list) -> Interval:
        kind = node[0]
        if kind == "c":
            return Interval.point(Fraction(node[1]))
        if kind == "s":
            return box[node[1]]
        if kind == "pi":
            return enclose(Pi(), {})
        if kind in _MANY:
            return op(_MANY[kind](tuple(Sym(str(k)) for k in range(len(node[1])))), node[1])
        if kind in _ONE:
            return op(_ONE[kind](Sym("0")), [node[1]])
        if kind == "div":
            return op(Div(Sym("0"), Sym("1")), node[1:])
        if kind == "pow":
            return op(PowInt(Sym("0"), node[2]), [node[1]])
        pairs: dict[tuple[int, int], list[int]] = {}
        for cond, _ in node[1]:
            for a, b in _atoms(cond):
                if (a, b) not in pairs:
                    x, y = get(a), get(b)
                    pairs[a, b] = [0] if a == b else [s for s, possible in ((-1, x.lo < y.hi), (0, x.lo <= y.hi and y.lo <= x.hi), (1, x.hi > y.lo)) if possible]
        ways = 1
        for outcomes in pairs.values():
            ways *= len(outcomes)
        if ways > MAX_CHOICES:
            raise _Failed(f"a pick with more than {MAX_CHOICES} ways to order what it compares")
        chosen = set()
        for choice in itertools.product(*pairs.values()):
            order = dict(zip(pairs, choice))
            first = next((n for n, (cond, _) in enumerate(node[1]) if _holds(cond, order)), None)
            if first is None:
                raise _Failed("no case of the pick holds somewhere in the box")
            chosen.add(first)
        found = [get(node[1][n][1]) for n in sorted(chosen)]
        return Interval(min(x.lo for x in found), max(x.hi for x in found))

    for n, node in enumerate(nodes):
        try:
            v.append(step(node))
        except _Failed as exc:
            v.append(str(exc))
        except KernelArithmeticError as exc:
            v.append(f"node {n}: {exc}")
    return v


def _partition(nodes: list[list], roots: list[int], box: list[Interval], budget: list[int], labels: list[str]) -> Any:
    """A partition on whose every leaf every root is at most zero, or None when the search
    finds none within its budget. Splits the input with the widest range, at its middle,
    and names it by its label, as proofs.json does for the kernel."""
    v = enclosures(nodes, box)
    if all(isinstance(v[r], Interval) and v[r].hi <= 0 for r in roots):
        return "leaf"
    budget[0] -= 1
    widest = max(range(len(box)), key=lambda k: box[k].width(), default=None)
    if widest is None or box[widest].width() == 0 or budget[0] <= 0:
        return None
    cut = box[widest].midpoint()
    halves = []
    for half in (Interval(box[widest].lo, cut), Interval(cut, box[widest].hi)):
        found = _partition(nodes, roots, [*box[:widest], half, *box[widest + 1:]], budget, labels)
        if found is None:
            return None
        halves.append(found)
    return {"input": labels[widest], "at": export.number(cut), "below": halves[0], "above": halves[1]}


def _refuting(nodes: list[list], root: int, box: list[Interval]) -> list[Fraction] | None:
    """A corner of the box, or its middle, where the root is above zero."""
    ranged = [k for k, x in enumerate(box) if x.width() > 0]
    corners = itertools.product(*((x.lo, x.hi) if x.width() > 0 else (x.lo,) for x in box)) if len(ranged) <= MAX_CORNERS else []
    for point in itertools.chain(corners, [tuple(x.midpoint() for x in box)]):
        at = enclosures(nodes, [Interval.point(x) for x in point])[root]
        if isinstance(at, Interval) and at.lo > 0:
            return list(point)
    return None


# --- cells -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Cell:
    """One answer. `body` is the cell as proofs.json holds it: a hint, which the kernel
    tries on the tape it writes itself. `proof` is the partition of a proved cell or the
    point of a refuted one. `ratio` is the most the left side of the rule reaches over the
    least the right side does, when both are known and the right side is above zero."""

    subject: str
    mechanism: str
    entry: str
    state: str
    what: str
    anchor: str
    why: str = ""
    rule: str | None = None
    ratio: float | None = None
    proof: Mapping[str, Any] = field(default_factory=dict)

    @property
    def body(self) -> dict[str, Any]:
        out = {"subject": self.subject, "mechanism": self.mechanism, "entry": self.entry, "state": self.state, **self.proof}
        return {**out, **({"why": self.why} if self.state in ("open", "not_applicable") else {}), **({"rule": self.rule} if self.rule else {})}


def _static(cond: tuple | None, part: Part) -> bool:
    if cond is None:
        return True
    if cond[0] == "is":
        return part.values[cond[1]] == cond[2]
    if cond[0] == "loaded":
        return bool(part.loads.get(cond[1]))
    if cond[0] == "not":
        return not _static(cond[1], part)
    return (all if cond[0] == "and" else any)(_static(c, part) for c in cond[1:])


def _names(term: Any) -> Iterator[str]:
    if isinstance(term, Sym):
        yield term.name
    for inner in (getattr(term, "args", None) or [getattr(term, name) for name in ("arg", "num", "den", "base") if hasattr(term, name)]):
        yield from _names(inner)


def _keys(cond: tuple | None) -> Iterator[str]:
    """The key fields a condition on a part reads."""
    if cond is not None and cond[0] == "is":
        yield cond[1]
    elif cond is not None and cond[0] != "loaded":
        for inner in cond[1:]:
            yield from _keys(inner)


def _reads(rule: Rule) -> set[str]:
    """What a rule reads, through the rows it applies and the names it defines: each field
    as the rule names it, `width` or `a.Fy`, and each load as `load NAME`."""
    found, seen = set(_keys(rule.when)), set()
    todo = [name for term in (rule.low, rule.high, *(t for w in rule.where for t in w[:2])) for name in _names(term)]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        if name in rule.applied:
            todo += [n for e in rule.applied[name].quantities.values() for n in _names(e)]
            found |= {f for _, f, _ in rule.applied[name].keys.values() if f is not None}
        elif name in rule.lets:
            todo += list(_names(rule.lets[name]))
        else:
            found.add(name)
    return found


def _ratio(nodes: list[list], low: int, high: int, box: list[Interval]) -> float | None:
    v = enclosures(nodes, box)
    if isinstance(v[low], Interval) and isinstance(v[high], Interval) and v[high].lo > 0:
        return float(v[low].hi / v[high].lo)
    return None


def _answers(rule: Rule, ask: Ask, part: Part, parts: Mapping[str, Part]) -> Iterator[Cell]:
    """The cells of one rule on one part: one for each load case the rule reads a load of,
    and before it one that proves the rule's range, where it has one."""
    tail, anchor = rule.id.rpartition("/")[2], _anchor(rule.anchor)

    def cell(entry: str, state: str, why: str = "", **more: Any) -> Cell:
        return Cell(part.name, rule.mechanism, entry, state, rule.says, anchor, why, rule.id, **more)

    def tape_of(pairs: list[tuple[Any, Any]], case: str | None) -> tuple[_Tape, list[int], list[tuple[int, int]]]:
        tape = _Tape()
        env = _env(tape, rule, part, parts, case)
        sides = [(tape.emit(low, env), tape.emit(high, env)) for low, high in pairs]
        return tape, [tape.node("add", [low, tape.node("neg", high)]) for low, high in sides], sides

    reads = {name[5:] for name in _reads(rule) if name.startswith("load ")}
    missing = sorted(name for name in reads if not part.loads.get(name))
    if missing:
        yield cell(tail, "open", f"the card puts no {' and no '.join(missing)} on {part.name}, which the rule reads")
        return
    cases = sorted(set.intersection(*(set(part.loads[name]) for name in reads))) if reads else [None]
    if not cases:
        yield cell(tail, "open", f"no load case puts {' and '.join(sorted(reads))} on {part.name} together")
    for case in cases:
        entry = tail if case is None else f"{tail}/{case}"
        try:
            if rule.where:
                tape, roots, _ = tape_of([w[:2] for w in rule.where], case)
                box, labels = [i.range for i in tape.inputs], [i.label for i in tape.inputs]
                partition = _partition(tape.nodes, roots, box, [MAX_LEAVES], labels)
                if partition is None:
                    v = enclosures(tape.nodes, box)
                    outside = next(why for (_, _, why), r in zip(rule.where, roots) if not (isinstance(v[r], Interval) and v[r].hi <= 0))
                    yield cell(entry, "open", f"the rule holds only where {outside}, and that is not proved for {part.name}")
                    continue
                yield Cell(part.name, rule.mechanism, f"{entry}/where", "proved", "; ".join(w[2] for w in rule.where), anchor, "", rule.id,
                           proof={"partition": partition})
            tape, roots, sides = tape_of([(rule.low, rule.high)], case)
        except NoValue as exc:
            yield cell(entry, "open", str(exc))
            continue
        box, labels = [i.range for i in tape.inputs], [i.label for i in tape.inputs]
        partition = _partition(tape.nodes, roots, box, [1], labels)
        point = None if partition is not None else _refuting(tape.nodes, roots[0], box)
        if partition is None and point is None:
            partition = _partition(tape.nodes, roots, box, [MAX_LEAVES], labels)
        if partition is not None:
            yield cell(entry, "proved", ratio=_ratio(tape.nodes, *sides[0], box), proof={"partition": partition})
        elif point is not None:
            yield cell(entry, "refuted", ratio=_ratio(tape.nodes, *sides[0], [Interval.point(x) for x in point]),
                       proof={"point": {label: export.number(x) for label, x in zip(labels, point)}})
        else:
            v = enclosures(tape.nodes, box)
            if isinstance(v[roots[0]], str):
                origin = v.index(v[roots[0]])
                yield cell(entry, "open", (f"{tape.picks[origin]} gives no value at what {part.name} has: " if origin in tape.picks else "") + v[roots[0]])
            else:
                yield cell(entry, "open", "neither proved over the ranges the card gives nor refuted at a corner of them")


def cells(design: Design, deck: Deck, found: Parts) -> list[Cell]:
    """Every cell of the design: for each part, each mechanism the grid asks of its type."""
    out: list[Cell] = []
    waived = {(w.subject[0], w.mode): w for w in design.waivers}
    for part in found.parts.values():
        for ask in (a for a in deck.asks if a.type == part.type.name):
            anchor = _anchor(ask.anchor)
            if (part.name, ask.mechanism) in waived:
                w = waived[part.name, ask.mechanism]
                out.append(Cell(part.name, ask.mechanism, "", "waived", ask.what, anchor, f"by {w.owner}: {w.reason}"))
            elif ask.excused is not None and _static(ask.unless, part):
                out.append(Cell(part.name, ask.mechanism, "", "not_applicable", ask.what, anchor, ask.excused))
            else:
                rules = [r for r in deck.rules if (r.type, r.mechanism) == (ask.type, ask.mechanism) and _static(r.when, part)]
                out += [c for r in rules for c in _answers(r, ask, part, found.parts)]
                if not rules:
                    out.append(Cell(part.name, ask.mechanism, "", "open", ask.what, anchor,
                                    f"the deck has no rule for it{' on a part like this one' if any(r.mechanism == ask.mechanism for r in deck.rules) else ''}"))
    return out + _unread(deck, found)


def _unread(deck: Deck, found: Parts) -> list[Cell]:
    """An open cell for each quantity and each key that no rule or grid line reads for its
    part. A value nothing reads is a value nothing checks: a plate that no joint joins
    would pass at any thickness."""
    read: set[tuple[str, str]] = set()
    for part in found.parts.values():
        names = {alias: part.values[f.name][n] for f in part.type.fields.values() if f.type is not None for n, alias in enumerate(f.names)}
        fields = {name for a in deck.asks if a.type == part.type.name for name in _keys(a.unless)}
        fields |= {name for r in deck.rules if r.type == part.type.name and _static(r.when, part) for name in _reads(r)}
        for name in fields:
            alias, dot, inner = name.partition(".")
            read.add((names[alias], inner) if dot else (part.name, name))
    return [Cell(part.name, "unread", f.name, "open", f.what, "", f"no rule of the deck reads {part.name}.{f.name}, so nothing checks it")
            for part in found.parts.values() for f in part.type.fields.values() if f.type is None and (part.name, f.name) not in read]


# --- the files, the kernel and the report ------------------------------------------------------------


def bundle(design: Design, deck: Deck, answers: list[Cell] | None = None) -> dict[str, str]:
    """The text of the files of docs/format.md: the card, the design with its parts as
    written, the deck of domains, `rules`, which is the deck's own file, and with `answers`
    the hints of proofs.json. None of the first four needs this module to have accepted
    the design: the kernel reads the parts from them itself."""
    card = export.text(export.card(design, export.read_inputs(design), placed=True))
    core = json.loads(export.CORE.read_text(encoding="utf-8"))["domains"]
    return {"card": card, "design": export.text(export.design_file(design, export.sha256(card), deck=True)),
            "deck": export.text({"format": "petra-deck/0", "domains": core, "constants": [], "rules": {"name": deck.name, "hash": deck.hash}}),
            "rules": deck.text,
            **({} if answers is None else {"proofs": export.text({"format": "petra-proofs/0", "cells": [c.body for c in answers]})})}


def verdict(answers: list[Cell]) -> str:
    """FAIL with a refuted cell, UNKNOWN with an open cell or with nothing proved, else PASS."""
    states = {c.state for c in answers}
    return "FAIL" if "refuted" in states else "UNKNOWN" if "open" in states or "proved" not in states else "PASS"


@dataclass(frozen=True)
class Report:
    """A design checked against a deck: its cells, and the verdict they give."""

    name: str
    path: str
    deck: Deck
    cells: tuple[Cell, ...]

    @property
    def status(self) -> str:
        return verdict(list(self.cells))

    def counts(self) -> dict[str, int]:
        return {state: sum(c.state == state for c in self.cells) for state in STATES}

    def to_json(self) -> dict[str, Any]:
        return {"file": self.path, "design": self.name, "status": self.status, "deck": {"name": self.deck.name, "hash": self.deck.hash},
                "counts": self.counts(),
                "cells": [{"subject": c.subject, "mechanism": c.mechanism, "entry": c.entry, "state": c.state, "what": c.what,
                           "anchor": c.anchor, "why": c.why, "rule": c.rule, "ratio": c.ratio} for c in self.cells]}

    def render(self) -> str:
        return "\n".join(self.lines())

    def lines(self) -> list[str]:
        counts = self.counts()
        out = [f"{self.name}: {self.status}",
               f"rules      {self.deck.hash}  {self.deck.name}",
               "cells      " + ", ".join(f"{counts[s]} {s.replace('_', ' ')}" for s in STATES)]
        wide = max((len(f"{c.subject}/{c.mechanism}") for c in self.cells), default=0)
        for c in self.cells:
            ratio = "" if c.ratio is None else f"{c.ratio:.3g}"
            said = c.why if c.state in ("open", "not_applicable", "waived") else c.what if c.state == "refuted" or c.entry.endswith("/where") else ""
            out.append(f"  {f'{c.subject}/{c.mechanism}':<{wide}}  {c.state.replace('_', ' '):<14}  {ratio:>6}  "
                       + ": ".join(part for part in (c.entry, said) if part) + (f" ({c.anchor})" if c.anchor else ""))
        pending = [c for c in self.cells if c.state == "open"]
        if pending:
            out.append(f"open       {len(pending)} cells: each needs a rule, an input, or `waive MECHANISM on PART by \"<owner>\" reason \"<why>\"` in the card")
        return out


@dataclass(frozen=True)
class Checked:
    """What `petra check` gives for a design checked against a deck, with the members of
    repair.Checked that its callers read. `kernel` is what petra-verify said of the files,
    or None when there is none to run."""

    path: str
    report: Report
    card: str
    hashes: Mapping[str, str]
    kernel: Mapping[str, Any] | None
    error: None = None
    repair: None = None

    @property
    def status(self) -> str:
        return self.report.status

    def to_json(self) -> dict[str, Any]:
        return {**self.report.to_json(), "card": self.card, "hashes": dict(self.hashes), "path": "rules", "kernel": self.kernel, "repair": None}

    def text(self) -> str:
        from . import verify

        proofs = sum(bool(c.proof) for c in self.report.cells)
        kernel = verify.NO_KERNEL if self.kernel is None else f"petra-verify checked {proofs} of {proofs} proofs and gives the same verdict"
        out = self.report.lines()
        path = ("rules: the kernel worked out every cell from the rules deck" if self.kernel is not None
                else "rules: the Python grid worked out every cell from the rules deck, and no kernel checked it")
        return "\n".join([*out[:2], f"card      {self.hashes['card']}  {self.card}", f"design     {self.hashes['design']}  {self.path}",
                          f"kernel     {kernel}", f"path       {path}", *out[2:]])


def checked(design: Design, deck: Deck, card: str, text: str, card_path: str) -> Checked:
    """Check the design against the deck and have the kernel check the files, when there is
    a kernel to run. The kernel reads the deck's file and works out every cell itself, so
    the two list the same cells in the same order with the same states, or one of them has
    a bug: that raises verify.Disagreement, which no caller catches."""
    from . import verify

    report, files = check(design, deck)
    kernel, said = verify.binary(), None
    if kernel is not None:
        said = verify.ask(kernel, files)
        if said["verdict"] == "ILL-FORMED":
            raise ComponentError(verify.refusal(design.path, said))
        differ = verify.differs([(c.subject, c.mechanism, c.entry, c.state) for c in report.cells], report.status, deck.hash, said)
        if differ:
            raise verify.Disagreement(f"{design.path}: petra-verify gives {said['verdict']} and the grid {report.status}: {differ}")
        said = {"verdict": said["verdict"], "checked": sum(bool(c.proof) for c in report.cells), "hashes": said["hashes"], "cells_from": said["cells_from"]}
    return Checked(design.path, report, card_path, {"card": export.sha256(card), "design": export.sha256(text)}, said)


def check(design: Design, deck: Deck) -> tuple[Report, dict[str, str]]:
    """The report of a design whose parts are of the deck's types, and the files behind it.
    Raises ComponentError for a design or a card the deck's types or the type rules refuse."""
    from . import wellformed

    found = read_parts(design, deck)
    answers = cells(design, deck, found)
    files = bundle(design, deck, answers)
    broken = wellformed.findings(*(json.loads(files[name]) for name in ("card", "design", "deck")))
    if broken:
        raise ComponentError(tuple(f"{design.path}: {b}" for b in broken))
    return Report(design.name, design.path, deck, tuple(answers)), files
