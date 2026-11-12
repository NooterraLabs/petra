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
    waived          the card waives the mechanism on the part, and the cell would be open without that
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
import math
from dataclasses import dataclass, field, replace
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from . import deck as rows
from . import export
from .deck import NONE, RowError, Vector, anchored, dimension, only, quantity, replaced, show
from .ir import Bound, Component, Design, Fixed, ParamRef, Ref, Span, Stated, Text
from .kernel import (Abs, Add, Const, Cos, Div, Exp, Interval, KernelArithmeticError, Ln, Max, Min, Mul, Neg, Pi, PowInt, Sqrt, Sym,
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
"""The mechanism of the cell of a field or a load that nothing reads. No line of the grid has this name."""
WAIVED = "open but for the waiver: "
"""What the kernel's reason of a waived cell starts with. The reason the cell had while it was open follows."""
UNRESTED = "the waiver rests no cell that an inequality could answer: "
"""What the kernel's reason of an open cell of a waived line starts with, when the waiver does not rest it."""
UNSTATED = "unstated"
"""The word a design writes for an `optional` field that the part's record does not state, as in kernel/Petra/Deck.lean."""


class _Unstated:
    """What a part has for a field it leaves unstated: no value, and no default. It is equal to no name of a key."""

    def __repr__(self) -> str:
        return UNSTATED


NOT_STATED = _Unstated()
MAX_READ = 1_000_000
"""The most steps reading a deck may take, as in kernel/Petra/Files.lean."""
MAX_TITLE = 200
"""The most bytes the name of a card may print in, for a design checked against a deck."""
MAX_REASON = 200
"""The bytes of a reason that the kernel prints (`MAX_TEXT` in kernel/Petra/Files.lean)."""
MAX_BITS = 65_536
"""The most bits a number of a need may have, as in kernel/Petra/Tape.lean. A need with a
longer one is not decided, and its part is refused."""
MAX_TRIED = 4096
"""The most combinations of the names of its keys at which reading a deck tries what a rule requires, as in kernel/Petra/Deck.lean."""
MAX_TRYING = 1_000_000
"""The most that reading one deck spends on trying its requirements: for each rule tried, its
combinations times the sizes of its `requires` and of its `when`. A rule past it is not tried."""
LOADED = ("`loaded` is no condition: a condition is over keys, which are the same under every load case. "
          "A card states a load in each case, as zero where there is none, and a rule reads it there")
"""What a deck that asks `loaded` is refused with, as in kernel/Petra/Deck.lean. The condition
held when some load case of the card put the load on the part, and a rule that reads loads
has a cell for each case: so one case could switch a rule or a line off under every other."""


class DeckError(ValueError):
    """A deck that does not hold together: an unknown key, a rule that names a row or a
    field the deck lacks, or dimensions that do not agree."""


# --- a deck ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Field:
    """One field of a type or one load on it. A quantity has `dim`, a key has `keys`, and a
    reference has `type`, the type of the parts it names, and `names`, what a rule calls
    each of them in order. Only the card states a `signed` quantity. A `whole` quantity is
    a count. `least` is the least value a quantity may take, in SI. `may_be` is `zero` for a
    quantity that may be zero and `negative` for one of any sign: with neither, a quantity of
    a part is more than zero. A part may leave an `optional` quantity or key unstated."""

    name: str
    what: str
    dim: Vector | None = None
    keys: tuple[str, ...] = ()
    type: str | None = None
    names: tuple[str, ...] = ()
    signed: bool = False
    whole: bool = False
    least: Fraction | None = None
    may_be: str | None = None
    optional: bool = False


@dataclass(frozen=True)
class Need:
    """What a type needs of its fields for a part of it to be a part at all: `low` at most
    `high`, or under it when `strict`. A side is `("c", number)`, `("field", name)`,
    `("add", sides)`, `("mul", sides)`, `("neg", side)` or `("div", side, side)`, which
    exact fractions decide."""

    strict: bool
    low: tuple
    high: tuple
    why: str


@dataclass(frozen=True)
class Type:
    name: str
    what: str
    fields: Mapping[str, Field]
    loads: Mapping[str, Field]
    needs: tuple[Need, ...] = ()


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
class Named:
    """A row that gives a name, with each quantity it takes bound to an expression."""

    row: rows.Row
    quantities: Mapping[str, Any]


@dataclass(frozen=True)
class Applied:
    """A row with its inputs bound: a quantity to an expression, and a key to a selector,
    which is `("field", FIELD, {its name: the row's})` or `("named", Named)`."""

    row: rows.Row
    quantities: Mapping[str, Any]
    keys: Mapping[str, tuple]


@dataclass(frozen=True)
class Cased:
    """`["case", ["row", ID, {...}], {NAME: ...}]`: for each name the row gives, the
    expression that is the value where the row gives that name."""

    named: Named
    branches: Mapping[str, Any]


@dataclass(frozen=True)
class Rule:
    """An answer to one mechanism of one type: `low <= high`, read where every `where`
    holds. The expressions are kernel terms over names: a field, `part.field`, a `let`
    name, `load NAME`, or `@n` for the n-th row the rule applies. A rule with `requires`
    states that condition over keys and no inequality: it has no sides, no names and no range.
    A `strict` rule states `low < high`: its `lt` in place of `le`."""

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
    requires: tuple | None = None
    strict: bool = False


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


def _long(name: Any, most: int = MAX_NAME) -> bool:
    """Whether the kernel would print this name in more than `most` bytes, counted as
    `printed` in kernel/Petra/Files.lean counts them: two for a quote, a backslash and a
    line end, six for any other control character, and the bytes of its UTF-8 otherwise."""
    return isinstance(name, str) and sum(2 if c in '"\\\n\r' else 6 if c < " " else len(c.encode("utf-8", "surrogatepass")) for c in name) > most


def _size(value: Any) -> int:
    """The size of a JSON value: one, for a list or an object the sizes of what it holds as
    well, and for a text two, and one more for each 8 characters."""
    if isinstance(value, str):
        return 2 + len(value) // 8
    return 1 + sum(map(_size, value.values() if isinstance(value, dict) else value)) if isinstance(value, (dict, list)) else 1


def _steps(body: Mapping[str, Any]) -> int:
    """The steps reading the deck takes, as `readingSteps` in kernel/Petra/Deck.lean counts
    them (docs/deck.md, "The size of a deck"): the size of the file, and the size of a row
    again for each `["row", ID, ...]` inside a rule, which reads the row again."""
    sizes: dict[str, int] = {}
    for row in body["rows"] if isinstance(body.get("rows"), list) else []:
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            sizes.setdefault(row["id"], _size(row))

    def again(value: Any) -> int:
        if isinstance(value, list):
            own = sizes.get(value[1], 0) if len(value) == 3 and value[0] == "row" and isinstance(value[1], str) else 0
            return own + sum(map(again, value))
        return sum(map(again, value.values())) if isinstance(value, dict) else 0

    return _size(body) + (sum(map(again, body["rules"])) if isinstance(body.get("rules"), list) else 0)


def _name(name: Any) -> bool:
    """Whether this can name a field, a load, a joined part or a `let`: letters, digits and
    `_`, as the language writes a name, and at most MAX_NAME of them. So `a.Fy` is always a
    field of a joined part, and no name reads as a number, a load or a row."""
    return isinstance(name, str) and name.isascii() and name.isidentifier() and not _long(name)


def _field(body: Mapping[str, Any], load: bool = False) -> Field:
    allowed = {"name", "what", "dim", "least", "may_be"} if load else {"name", "what", "dim", "least", "one_of", "type", "as", "signed", "whole", "may_be", "optional"}
    only(body, tuple(sorted(allowed)), f"field {body.get('name')!r}")
    if sum(key in body for key in ("dim", "one_of", "type")) != 1 or not (isinstance(body.get("what"), str) and body["what"]) or not _name(body.get("name")):
        raise DeckError(f"field {body.get('name')!r}: it has a name of letters, digits and _, `what`, a text, and one of `dim`, `one_of` and `type`, and may have {', '.join(sorted(allowed))}")
    name = body["name"]
    only(body, ("name", "what", "one_of", "optional", "signed") if "one_of" in body else ("name", "what", "type", "as") if "type" in body
         else ("name", "what", "dim", "least", "signed", "whole", "may_be", "optional"), f"field {name}")
    # A part may leave an `optional` field unstated. The flag is true or false, as the kernel reads it, and it is the design that says what
    # a record leaves out: only the card states a signed field, so a field is not both.
    optional = body.get("optional", False)
    if any(not isinstance(body.get(flag, False), bool) for flag in ("optional", "signed", "whole")):
        raise DeckError(f"field {name}: `optional`, `signed` and `whole` are each true or false")
    if (optional and body.get("signed")) or (optional and UNSTATED in body.get("one_of", ())):
        raise DeckError(f"field {name}: a field is `signed` or `optional`, and not both, and a key that may be left unstated has no name `{UNSTATED}`")
    if "one_of" in body:
        keys = tuple(str(k) for k in body["one_of"])
        if not keys or len(set(keys)) != len(keys):
            raise DeckError(f"field {name}: `one_of` is a list of different names")
        return Field(name, body["what"], keys=keys, optional=optional, signed=body.get("signed", False))
    if "type" in body:
        names = tuple(body.get("as", [name]))
        if not names or not all(map(_name, names)) or len(set(names)) != len(names):
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
    # `may_be` says how low the quantity may go by its sign, and a `least` beside it agrees: none with zero, and one under zero with negative.
    may_be = body.get("may_be")
    if "may_be" in body and (may_be not in ("zero", "negative") or (load and may_be == "zero") or (least is not None and (may_be == "zero" or least >= 0))):
        raise DeckError(f"field {name}: `may_be` is zero or negative, and negative alone for a load; a quantity that may be zero has no `least`, and with negative a `least` is under zero")
    return Field(name, body["what"], dim=dim, signed=bool(body.get("signed")), whole=whole, least=least, may_be=may_be, optional=optional)


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
        if isinstance(node, list) and node[:1] == ["case"] and len(node) == 3 and isinstance(node[2], dict):
            return self.case(node[1], node[2])
        return super().expr(node)

    def named(self, node: Any, what: str) -> Named:
        """`["row", ID, {INPUT: ...}]` with a row that gives a name, each of its quantities bound."""
        if not (isinstance(node, list) and node[:1] == ["row"] and len(node) == 3 and isinstance(node[1], str) and node[1] in self.rows and isinstance(node[2], dict)):
            raise RowError(f"{what}: a name comes from [\"row\", ID, {{...}}] with a row of the deck that gives a name")
        row = self.rows[node[1]]
        if not row.names:
            raise RowError(f"{what}: {node[1]} gives a quantity, and a name comes from a row that gives a name")
        if set(node[2]) != set(row.takes):
            raise RowError(f"{node[1]} takes {', '.join(row.takes)}, and the rule binds {', '.join(node[2]) or 'nothing'}")
        quantities = {}
        for name, takes in row.takes.items():
            quantities[name], dim = self.expr(node[2][name])
            if dim != takes.dim:
                self.problems.append(f"{node[1]}: {name} is a {show(takes.dim)}, and the rule binds a {show(dim)}")
        return Named(row, quantities)

    def case(self, key: Any, branches: Mapping[str, Any]) -> tuple[Any, Vector]:
        """The expression of the name that a row gives, with an expression for each name the
        row gives and for no other."""
        named = self.named(key, "`case`")
        if set(branches) != set(named.row.names):
            raise RowError(f"`case` has an expression for each of {', '.join(named.row.names)}, and for no other name")
        found = {name: self.expr(branches[name]) for name in named.row.names}
        dims = [dim for _, dim in found.values()]
        if any(dim != dims[0] for dim in dims[1:]):
            self.problems.append("`case` of different dimensions")
        name = f"@{len(self.applied)}"
        self.applied[name] = Cased(named, {n: term for n, (term, _) in found.items()})
        return Sym(name), dims[0]

    def apply(self, row_id: Any, binds: Any) -> tuple[Any, Vector]:
        if row_id not in self.rows or not isinstance(binds, dict):
            raise RowError(f"{row_id!r} is not a row of the deck, or its inputs are not an object")
        row = self.rows[row_id]
        if row.names:
            raise RowError(f"{row_id} gives a name, and a name is read by a key of a row or by a `case`")
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

        if isinstance(node, list) and node[:1] == ["row"]:      # the name that a row gives: each of its names is a name of the key
            named = self.named(node, what)
            if not set(named.row.names) <= set(known):
                raise RowError(f"{what}: {named.row.id} gives names the key lacks: {', '.join(sorted(set(named.row.names) - set(known)))}")
            return ("named", named)
        if isinstance(node, str):
            if not set(of(node)) <= set(known):
                raise RowError(f"{what}: {node} has names the row lacks: {', '.join(sorted(set(of(node)) - set(known)))}")
            return ("field", node, {k: k for k in of(node)})
        if isinstance(node, list) and node[:1] == ["key"] and len(node) == 2 and node[1] in known:
            return ("field", None, {None: node[1]})
        if isinstance(node, list) and node[:1] == ["by"] and len(node) == 3 and isinstance(node[2], dict):
            if set(node[2]) != set(of(node[1])) or not all(isinstance(its, str) for its in node[2].values()) or not set(node[2].values()) <= set(known):
                raise RowError(f"{what}: `by` gives one of the row's names for each name of {node[1]}")
            return ("field", node[1], dict(node[2]))
        raise RowError(f"{what}: a key is bound to a key field, to [\"key\", NAME] with one of {', '.join(known)}, or to [\"by\", FIELD, {{...}}]")

    def static(self, node: Any) -> tuple:
        """A condition on what a part is, not on how large: `["is", FIELD, NAME]`, and `and`,
        `or`, `not` of these. FIELD is a key field of the type, or `PART.FIELD` for a key
        field of a part the type joins, by the name its `as` gives that part. The name of a
        field that joins several parts is no part's name. A condition is over keys alone,
        which are the same under every load case: one that asks `loaded` is refused."""
        if isinstance(node, list) and node[:1] == ["is"] and len(node) == 3:
            if not isinstance(node[1], str) or node[1] not in self.takes or node[2] not in self.takes[node[1]].keys:
                raise RowError(f"{node!r}: `is` names a key field of the type, or of one part it joins by the name `as` gives it, and one of the key's names")
            return ("is", node[1], node[2])
        if isinstance(node, list) and node[:1] == ["loaded"]:
            raise RowError(LOADED)
        if isinstance(node, list) and node[:1] == ["not"] and len(node) == 2:
            return ("not", self.static(node[1]))
        if isinstance(node, list) and node[:1] in (["and"], ["or"]) and len(node) > 1:
            return (node[0], *(self.static(n) for n in node[1:]))
        raise RowError(f"{node!r} is not a condition on a part: write is, and, or, not")


def _exact(node: Any, takes: Mapping[str, rows.Input], free: frozenset = frozenset()) -> tuple[tuple, Vector]:
    """A side of a need and its dimension: a number, a constant with its unit, a quantity
    field of the type or of a part it joins, and add, sub, mul, neg and div. A quotient
    divides by a field, which is more than zero for every part, or by a number that is not
    zero. `free` holds the fields that say `may_be`, which may be zero and are no divisor.
    Anything else is refused: exact fractions decide a need."""
    if isinstance(node, str):
        if node == "pi":
            raise RowError("a need has no pi: exact fractions decide a need")
        if node in takes:
            if takes[node].keys:
                raise RowError(f"{node} is a key, and a need compares quantities")
            return ("field", node), takes[node].dim
        try:
            return ("c", rows.parse_quantity(node, None).value.lo), NONE
        except ValueError:
            raise RowError(f"{node[:40]!r} is not a number, and no quantity field has that name") from None
    if not isinstance(node, list) or not node or not isinstance(node[0], str):
        raise RowError(f"{node!r} is not an expression: write a number, a name or [operator, ...]")
    op, args = node[0], node[1:]
    if op == "q" and len(args) == 2 and all(isinstance(a, str) for a in args):
        value, dim = quantity(f"{args[0]} {args[1]}", "a constant")
        return ("c", value), dim
    parts = [_exact(a, takes, free) for a in args] if op in ("add", "mul", "sub", "neg", "div") else []
    sides, dims = tuple(p[0] for p in parts), [p[1] for p in parts]
    if op in ("add", "sub") and any(d != dims[0] for d in dims[1:]):
        raise RowError(f"{op} of different dimensions")
    if op == "add" and sides:
        return ("add", sides), dims[0]
    if op == "mul" and sides:
        return ("mul", sides), tuple(map(sum, zip(*dims)))
    if op == "sub" and len(sides) == 2:
        return ("add", (sides[0], ("neg", sides[1]))), dims[0]
    if op == "neg" and len(sides) == 1:
        return ("neg", sides[0]), dims[0]
    if op == "div" and len(sides) == 2:
        if sides[1][0] not in ("field", "c") or sides[1] == ("c", 0) or (sides[1][0] == "field" and sides[1][1] in free):
            raise RowError("a need divides by a field that is more than zero or by a number that is not zero, and by nothing else: so exact fractions decide the quotient, and a field that says `may_be` may be zero")
        return ("div", *sides), tuple(a - b for a, b in zip(*dims))
    raise RowError(f"{op!r} with {len(args)} arguments is not in a need: it has add, sub, mul, neg, and div by a field or by a number")


def _fields(side: tuple) -> Iterator[str]:
    """The fields a side of a need names, each as often as it names it."""
    if side[0] == "field":
        yield side[1]
    elif side[0] != "c":
        for inner in (side[1] if side[0] in ("add", "mul") else side[1:]):
            yield from _fields(inner)


def _need(body: Any, takes: Mapping[str, rows.Input], free: frozenset = frozenset()) -> Need:
    """One need of a type: `{"le": [a, b], "why": "..."}` or `{"lt": [a, b], "why": "..."}`.
    Its two sides have one dimension, and it names at least one field and each field once:
    the range of a side that reads each quantity once is exactly what the four operations
    on the ends of their ranges give, so the need is decided and not only enclosed."""
    only(body, ("le", "lt", "why"), "a need")
    if ("le" in body) == ("lt" in body) or not (isinstance(body.get("why"), str) and body["why"]):
        raise RowError("it has `le` or `lt`, and not both, and says why in a text that is not empty")
    strict = "lt" in body
    (low, low_dim), (high, high_dim) = (_exact(side, takes, free) for side in body["lt" if strict else "le"])
    named = [*_fields(low), *_fields(high)]
    if low_dim != high_dim or not named or len(set(named)) != len(named):
        raise RowError("it compares two sides of one dimension, and names at least one field and each field once, so that exact fractions decide it")
    return Need(strict, low, high, body["why"])


def _weight(cond: tuple | None) -> int:
    """The size of a condition, as `Static.size` in kernel/Petra/Deck.lean: 1 for an `is`, and 1 more than its members for `and`, `or` and `not`."""
    return 0 if cond is None else 1 if cond[0] == "is" else 1 + sum(map(_weight, cond[1:]))


def _over(cond: tuple | None, point: Mapping[str, str]) -> bool:
    """Whether a condition holds when `point` gives each key it names the name it has. No condition holds."""
    if cond is None:
        return True
    if cond[0] == "is":
        return point[cond[1]] == cond[2]
    if cond[0] == "not":
        return not _over(cond[1], point)
    return (all if cond[0] == "and" else any)(_over(c, point) for c in cond[1:])


def _combinations(names: list[str], takes: Mapping[str, rows.Input]) -> int:
    """How many combinations the names of these keys make, or some number over MAX_TRIED when they make more than that."""
    total = 1
    for name in names:
        total = total if total > MAX_TRIED else total * len(takes[name].keys)
    return total


def _tried(names: list[str], takes: Mapping[str, rows.Input], requires: tuple, when: tuple | None, unless: tuple | None = None) -> tuple[int, int]:
    """What a requirement is at every combination of the names of the keys `names`: at how many of them its rule
    answers, which is where `when` holds and `unless` does not, and at how many of those what it requires holds."""
    answers = holds = 0
    for choice in itertools.product(*(takes[name].keys for name in names)):
        point = dict(zip(names, choice))
        if _over(when, point) and not (unless is not None and _over(unless, point)):
            answers += 1
            holds += _over(requires, point)
    return answers, holds


def _rule(body: Mapping[str, Any], deck_rows: Mapping[str, rows.Row], types: Mapping[str, Type]) -> Rule:
    where = body.get("id")
    try:
        only(body, ("id", "type", "mechanism", "anchor", "says", "when", "let", "where", "le", "lt", "requires"), "a rule")
        if not isinstance(where, str) or _long(where):
            raise RowError(f"a rule has id, of at most {MAX_NAME} characters, type, mechanism, anchor, says, one of le, lt and requires, and may have when, let and where")
        if sum(key in body for key in ("le", "lt", "requires")) != 1:
            raise RowError("a rule has one of `le`, `lt` and `requires`: an inequality, a strict one, or a condition over keys")
        anchor = anchored(body["anchor"], "anchor")
        for w in body.get("where", []):
            only(w, ("le", "why"), "where")
        if not body.get("says") or "where" in body and not body["where"]:
            raise RowError("a rule says what it states, and a `where` has at least one item")
        binder = _Binder(deck_rows, types[body["type"]], types)
        if "requires" in body:
            if {"let", "where"} & set(body):
                raise RowError("a rule with `requires` has no `le`, no `lt`, no `let` and no `where`: it states a condition over keys, and no inequality")
            when = binder.static(body["when"]) if "when" in body else None
            return Rule(where, body["type"], body["mechanism"], anchor, body["says"], when, {}, (), None, None, {}, binder.static(body["requires"]))
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

        strict = "lt" in body
        low, high = pair(body["lt" if strict else "le"], "`lt`" if strict else "`le`")
        ranges = tuple((*pair(w["le"], "`where`"), str(w["why"])) for w in body.get("where", []))
        when = binder.static(body["when"]) if "when" in body else None
        if binder.problems:
            raise RowError("; ".join(dict.fromkeys(binder.problems)))
        return Rule(where, body["type"], body["mechanism"], anchor, body["says"], when, lets, ranges, low, high, binder.applied, strict=strict)
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
        if _steps(body) > MAX_READ:
            raise DeckError(f"reading this deck takes {_steps(body)} steps, over the budget of {MAX_READ}: a value of the file is one step, a text two or more, and a rule that applies a row takes the row's steps again")
        found = [rows.read(r) for r in body["rows"]]
        wrong = [f"{r.id}: {p}" for r in found for p in r.problems]
        if wrong:
            raise DeckError("; ".join(wrong))
        deck_rows = _named(found, "rows", lambda r: r.id)
        for t in body["types"]:
            only(t, ("type", "what", "fields", "loads", "needs"), f"type {t.get('type')!r}")
            if not isinstance(t.get("type"), str):
                raise DeckError(f"type {t.get('type')!r}: the name of a type is a text")
            if "needs" in t and not (isinstance(t["needs"], list) and t["needs"]):
                raise DeckError(f"type {t['type']}: `needs` has at least one item: a type that needs nothing leaves it out")
        types = _named([Type(t["type"], t["what"], _named([_field(f) for f in t["fields"]], "fields", lambda f: f.name),
                             _named([_field(f, True) for f in t.get("loads", [])], "loads", lambda f: f.name)) for t in body["types"]],
                       "types", lambda t: t.name)
        for t in types.values():
            joined = [name for f in t.fields.values() for name in f.names]
            for f in t.fields.values():
                if f.type is not None and (f.type not in types or any(g.type for g in types[f.type].fields.values()) or len(set(joined)) != len(joined)):
                    raise DeckError(f"{t.name}.{f.name}: it names parts of a type the deck has, whose own fields name no parts, each by a name of its own")
        # What each type needs of its fields, read once every type is known: a need may name a field of a part the type joins.
        for t in body["types"]:
            try:
                kind = types[t["type"]]
                free = frozenset({f.name for f in kind.fields.values() if f.may_be}
                                 | {f"{part}.{g.name}" for f in kind.fields.values() if f.type is not None for part in f.names for g in types[f.type].fields.values() if g.may_be})
                needs = tuple(_need(n, _Binder({}, kind, types).takes, free) for n in t.get("needs", []))
            except RowError as exc:
                raise DeckError(f"type {t['type']}: a need: {exc}") from None
            types[t["type"]] = Type(*(getattr(types[t["type"]], name) for name in ("name", "what", "fields", "loads")), needs)
        asks = []
        for a in body["grid"]:
            unless = a.get("unless")
            only(a, ("type", "mechanism", "what", "anchor", "unless"), f"grid {a.get('mechanism')}")
            anchor = anchored(a["anchor"], f"grid {a.get('mechanism')}: anchor")
            if unless is not None:
                only(unless, ("why", "when"), f"grid {a.get('mechanism')}: unless")
            if not isinstance(a["type"], str) or not isinstance(a["mechanism"], str) or a["type"] not in types or _long(a["mechanism"]) or a["mechanism"] == UNREAD:
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
        # A requirement that no part can break, or that no part can meet, is a fault of the deck. Each is tried at every combination of the
        # names of the keys that it and its `when` name, in the order of the rules, within MAX_TRIED for a rule and MAX_TRYING for the deck.
        spent, named = 0, {}
        for r in rules:
            if r.requires is None:
                continue
            if r.type not in named:
                named[r.type] = _Binder({}, types[r.type], types).takes
            names = list(dict.fromkeys([*_keys(r.when), *_keys(r.requires)]))
            total = _combinations(names, named[r.type])
            cost = total * (_weight(r.requires) + _weight(r.when))
            if total <= MAX_TRIED and spent + cost <= MAX_TRYING:
                spent += cost
                answers, holds = _tried(names, named[r.type], r.requires, r.when)
                if not answers or holds in (0, answers):
                    raise DeckError(f"rule {r.id}: " + ("its `when` holds for no combination of the names of its keys, so the rule answers for no part" if not answers
                                                        else f"what it requires holds for {'every' if holds else 'no'} combination of the names of its keys at which it answers, "
                                                             f"so no part can {'break' if holds else 'meet'} it"))
        return Deck(str(body["name"]), export.sha256(text), deck_rows, types, tuple(asks), rules, text)
    except (RowError, DeckError) as exc:
        raise DeckError(str(exc)) from None
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        # A ValueError that is none of the two above is the JSON reader's: text that is not
        # JSON, or a whole number of more digits than Python turns into a number.
        raise DeckError(f"not a deck ({type(exc).__name__}: {str(exc)[:200]})") from None


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
    """The parts, and the load cases of the card in the order of their names: every case
    the card states, whether it puts a load on a part or not."""

    parts: Mapping[str, Part]
    cases: tuple[str, ...] = ()


def _at(span: Span) -> str:
    return f"{span.path}:{span.line}:{span.col}"


@lru_cache(maxsize=None)
def _floors() -> tuple[tuple[str, Vector, Fraction, bool], ...]:
    """The floors that petra/decks/core.json gives the dimensions: the name, the dimension, the floor and whether it is strict."""
    from . import wellformed

    listed = json.loads(export.CORE.read_text(encoding="utf-8"))["domains"]["input"]
    return tuple((name, tuple(map(Fraction, wellformed.dimension(name))), Fraction(floor["min"]), bool(floor["strict"]))
                 for name, floor in listed.items() if isinstance(floor, dict))


def _floor(dim: Vector) -> tuple[str, Fraction, bool] | None:
    """The floor of a dimension in the core domains, the tighter one when two names are one dimension, or None when it has none."""
    found = [(name, least, strict) for name, its, least, strict in _floors() if its == dim]
    return max(found, key=lambda f: (f[1], f[2])) if found else None


def _quantity(f: Field, kind: str, arg: Any, name: str, design: Design, say: Callable[[str], None]) -> Value | None:
    if isinstance(arg, ParamRef):
        return say("reads a param, and a family is not checked against a deck yet")
    if isinstance(arg, Stated):      # what the card states exactly: a whole number for a count, read as a given is
        if not f.whole or arg.whole is None:
            return say("is a count, and the card states a name for it" if f.whole else "is stated exactly by the card, and a quantity that is no count reads a bound: `given NAME in [...]`")
        if arg.name != name:
            return say(f"reads `given {arg.name}`, and a part reads only what the card states for it: `given {name}`")
        if (f.may_be is None and arg.whole <= 0) or (f.may_be == "zero" and arg.whole < 0):
            return say("is not more than zero" if f.may_be is None else "is under zero, and its field may be zero and not under it")
        if f.least is not None and arg.whole < f.least:
            return say(f"is under {float(f.least):g}, the least a {kind} has: {f.what}")
        return Value(f"in:{design.name}.{name}", Interval.point(Fraction(arg.whole)))
    if not isinstance(arg, (Fixed, Bound)):
        return say(f"is a {show(f.dim)}: write a number with its unit, or `given NAME`")
    q = arg.quantity if isinstance(arg, Fixed) else arg.range
    if rows._vector(q.dim) != f.dim:
        return say(f"is a {show(f.dim)}, not a {show(rows._vector(q.dim))}")
    if f.may_be is None and q.value.lo <= 0:
        return say("is not more than zero")
    if f.may_be == "zero" and q.value.lo < 0:
        return say("is under zero, and its field may be zero and not under it")
    if f.least is not None and q.value.lo < f.least:
        return say(f"is under {float(f.least):g} in SI units, the least a {kind} has: {f.what}")
    # A number that may be negative is still held to a floor of its dimension that is under zero, as a bound of the card is.
    floor = _floor(f.dim) if f.may_be == "negative" and isinstance(arg, Fixed) else None
    if floor is not None and floor[1] < 0 and (q.value.lo < floor[1] or (floor[2] and q.value.lo == floor[1])):
        return say(f"goes down to {q.value.lo} in SI units, and a {floor[0]} is {'more than' if floor[2] else 'at least'} {floor[1]}")
    if isinstance(arg, Bound):
        if f.whole:
            return say("is a count: the design writes a whole number, or the card states one exactly with `given NAME is N`, and not as a bound")
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
    problems += [f"{design.path}: the name of the card is at most {MAX_TITLE} characters for a design checked against a deck"] * _long(design.name, MAX_TITLE)
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
            elif [a.parts for a in attr.args if isinstance(a, Ref)] == [(UNSTATED,)] and len(attr.args) == 1 and (f.optional or not f.keys):
                # The one word `unstated` leaves an optional field unstated. On a key that is not optional it is a name like any other, below.
                if f.optional:
                    values[attr.key] = NOT_STATED
                else:
                    say("is left unstated, and its field is not `optional`: it must be stated")
            elif len(attr.args) != 1:
                say("takes one value")
            elif f.keys:
                arg = attr.args[0]
                word = arg.value if isinstance(arg, Text) else arg.parts[0] if isinstance(arg, Ref) and len(arg.parts) == 1 else None
                if isinstance(arg, (Stated, Bound)):      # a key that the card states: the name is the card's, and it is one of the key's names
                    if arg.name != f"{c.name}.{attr.key}":
                        say(f"reads `given {arg.name}`, and a part reads only what the card states for it: `given {c.name}.{attr.key}`")
                    elif isinstance(arg, Bound) or arg.key is None:
                        say(f"is a key, which the card states with a name: `given {arg.name} is <name> signed ...`")
                    elif arg.key not in f.keys:
                        say(f"is one of: {', '.join(f.keys)}; the card states {arg.key[:MAX_NAME]!r}")
                    else:
                        values[attr.key] = arg.key
                elif f.signed and word is not None:
                    say(f"is for the card to state: write `{attr.key} given {c.name}.{attr.key}`, with `given {c.name}.{attr.key} is <name> signed ...` in the card")
                elif word not in f.keys:
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
    # An environment that no cell reads would leave a verdict that looks as if it held there: it is refused, as an ambient is.
    unread = [("a claim", design.claims), ("a probability claim", design.probability_claims), ("a tests record", design.tests),
              ("an ambient", design.ambient), ("an environment", design.environment), ("a param", design.params)]
    problems += [f"{design.path}: the card or the design states {what}, which a deck does not read yet" for what, there in unread if there]
    if not problems:      # what the types need is asked of a design that breaks nothing else, so every field is there and above zero
        problems += [f"{_at(design.components[p.name].span)}: {p.name} {broken}" for p in parts.values() for broken in _unmet(p, parts)]
    if problems:
        raise ComponentError(tuple(problems))
    return Parts({name: Part(name, p.type, p.values, loads[name]) for name, p in parts.items()}, tuple(sorted(design.loads)))


class _Undecided(Exception):
    """A need that exact fractions do not decide for a part, with the kernel's reason."""


def _bits(x: Fraction) -> int:
    """The bits of the longer of a fraction's two numbers, as `ratBits` in kernel/Petra/Tape.lean."""
    return max(abs(x.numerator).bit_length(), x.denominator.bit_length())


def _span(side: tuple, value: Callable[[str], Interval]) -> tuple[Fraction, Fraction]:
    """The least and the most a side of a need reaches over the ranges of its fields, by
    the four operations on the ends. The side reads each field once, so this is the range
    of its values and no wider. It takes the steps `Exact.range` of kernel/Petra/Grid.lean
    takes, in its order, and stops where it stops: at a sum, a product or a quotient with
    a number of more than MAX_BITS bits, and at a quotient by a range that holds zero,
    which a signed field may have."""
    def fits(lo: Fraction, hi: Fraction) -> tuple[Fraction, Fraction]:
        if max(_bits(lo), _bits(hi)) > MAX_BITS:
            raise _Undecided(f"a value has more than {MAX_BITS} bits")
        return lo, hi

    def times(a: tuple[Fraction, Fraction], b: tuple[Fraction, Fraction]) -> tuple[Fraction, Fraction]:
        ends = (a[0] * b[0], a[0] * b[1], a[1] * b[0], a[1] * b[1])
        return fits(min(ends), max(ends))

    if side[0] == "c":
        return side[1], side[1]
    if side[0] == "field":
        return value(side[1]).lo, value(side[1]).hi
    if side[0] == "neg":
        lo, hi = _span(side[1], value)
        return -hi, -lo
    if side[0] == "add":
        lo = hi = Fraction(0)
        for inner in side[1]:
            a, b = _span(inner, value)
            lo, hi = fits(lo + a, hi + b)
        return lo, hi
    if side[0] == "mul":
        found = (Fraction(1), Fraction(1))
        for inner in side[1]:
            found = times(found, _span(inner, value))
        return found
    over, under = _span(side[1], value), _span(side[2], value)
    if under[0] <= 0 <= under[1]:
        raise _Undecided("division by an interval that contains 0")
    return times(over, (1 / under[1], 1 / under[0]))


def _unmet(part: Part, parts: Mapping[str, Part]) -> Iterator[str]:
    """Each need of its type that the part breaks or that is not decided for it. A need
    holds when the most its left side reaches is at most the least its right side reaches,
    or under it for `lt`: for every value the card and the design allow. A number of more
    than 256 bits is not printed, as the kernel prints none."""
    def shown(x: Fraction) -> str:
        return str(x) if _bits(x) <= 256 else f"a number of {_bits(x)} bits"

    for n, need in enumerate(part.type.needs, 1):
        if _lacking(part, parts, [*_fields(need.low), *_fields(need.high)]) is not None:
            continue      # a need that names a field the part leaves unstated is not decided, and does not refuse the part
        try:
            (low, most), (least, high) = (_span(side, lambda name: _field_of(part, parts, name).range) for side in (need.low, need.high))
        except _Undecided as why:
            yield f"need {n} of a {part.type.name} is not decided: {why}"
            continue
        if not (most < least if need.strict else most <= least):
            yield (f"breaks need {n} of a {part.type.name}: its left side, {'' if low == most else 'up to '}{shown(most)}, is not {'under' if need.strict else 'at most'} "
                   f"its right side, {'' if least == high else 'down to '}{shown(least)}, in SI units: {need.why}")


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
        one = {Neg: "neg", Sqrt: "sqrt", Ln: "ln", Exp: "exp", Cos: "cos", Abs: "abs"}
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

    def places(self, axis: rows.Axis, x: int) -> list[tuple[int, Any]]:
        """Each place of a side that a quantity reads, with the condition that node `x` is there."""
        if axis.at:
            return [(n, ["and", [["le", x, self.const(v)], ["le", self.const(v), x]]]) for n, v in enumerate(axis.at)]
        out = []
        for n, (lo, hi) in enumerate(axis.bands):
            ends = [["lt" if axis.upper else "le", self.const(lo), x], *([["le" if axis.upper else "lt", x, self.const(hi)]] if hi is not None else [])]
            out.append((n, ends[0] if len(ends) == 1 else ["and", ends]))
        return out

    def named(self, row: rows.Row, quantities: Mapping[str, int]) -> list[tuple[str, Any]]:
        """For a row that gives a name: each cell that holds one, in order, with the
        condition that the quantities are at the cell. An empty cell gives nothing, so at
        such a cell and outside every band no condition holds."""
        sides = [self.places(axis, quantities[axis.by]) for axis in row.table.axes]
        out = []
        for i, down in sides[0]:
            for j, across in (sides[1] if len(sides) == 2 else [(0, None)]):
                if row.table.cells[i][j] is not None:
                    out.append((row.table.cells[i][j], down if across is None else ["and", [down, across]]))
        return out

    def row(self, row: rows.Row, quantities: Mapping[str, int], keys: Mapping[str, Any]) -> int:
        """The row's value with each quantity it takes at a node, and each key at a name or,
        for a key that a row names, at each name that row can give with its condition."""
        if row.table is None:
            return self.pick([(None if c.when is None else self.cond(c.when, quantities.__getitem__), self.emit(c.expr, quantities.__getitem__))
                              for c in row.cases], row.id)
        table = row.table

        def places(axis: rows.Axis) -> list[tuple[int, Any]]:
            if axis.keys:
                at = keys[axis.by]
                return [(axis.keys.index(at), None)] if isinstance(at, str) else [(axis.keys.index(name), cond) for name, cond in at]
            return self.places(axis, quantities[axis.by])

        across = places(table.axes[1]) if len(table.axes) == 2 else [(0, None)]

        def line(i: int) -> int | None:
            there = [(c, self.const(table.cells[i][j])) for j, c in across if table.cells[i][j] is not None]
            return self.pick(there, row.id) if there else None

        return self.pick([(c, line(i)) for i, c in places(table.axes[0]) if line(i) is not None], row.id)


def _field_of(part: Part, parts: Mapping[str, Part], name: str) -> Any:
    """What the part has for a field as a rule names it: `width`, or `a.Fy` for a field of
    the part it joins under the name `a`."""
    if "." not in name:
        return part.values[name]
    alias, _, inner = name.partition(".")
    for f in part.type.fields.values():
        if alias in f.names and f.type is not None:
            return parts[part.values[f.name][f.names.index(alias)]].values[inner]
    raise KeyError(name)


def _lacking(part: Part, parts: Mapping[str, Part], names: Any) -> str | None:
    """The first of these fields, as a rule names them, that the part or the part it joins
    leaves unstated: `PART.FIELD`, with the name of the part that has the field."""
    for name in names:
        if _field_of(part, parts, name) is NOT_STATED:
            alias, dot, inner = name.partition(".")
            owner = next(part.values[f.name][f.names.index(alias)] for f in part.type.fields.values() if f.type is not None and alias in f.names) if dot else part.name
            return f"{owner}.{inner if dot else name}"
    return None


def _lacks_quantity(part: Part, parts: Mapping[str, Part], names: Any) -> bool:
    """Whether one of these fields that the part, or the part it joins, leaves unstated is a
    quantity, as Part.lacksQuantity in kernel/Petra/Grid.lean decides it. A rule's inequality
    could then answer for the part whatever value it has, so a waiver does not rest its cells."""
    for name in names:
        if _field_of(part, parts, name) is NOT_STATED:
            alias, dot, inner = name.partition(".")
            owner = next(parts[part.values[f.name][f.names.index(alias)]] for f in part.type.fields.values() if f.type is not None and alias in f.names) if dot else part
            if owner.type.fields[inner if dot else name].dim is not None:
                return True
    return False


def _unstated_why(field: str, reader: str) -> str:
    """What a cell says when its rule, or the `unless` of its line, reads a field the part leaves unstated, in the kernel's words."""
    return f"{field} is unstated: its maker states none, and {reader} reads it"


def _env(tape: _Tape, rule: Rule, part: Part, parts: Mapping[str, Part], case: str | None) -> Callable[[str], int]:
    """What each name of a rule's expressions is on the tape, for one part and one load case."""
    memo: dict[str, int] = {}

    def field_of(name: str) -> Any:
        return _field_of(part, parts, name)

    def find(name: str) -> int:
        if name not in memo:
            if name.startswith("load "):
                memo[name] = tape.input(part.loads[name[5:]][case])
            elif name in rule.applied:
                a = rule.applied[name]

                def named(n: Named) -> list[tuple[str, Any]]:
                    return tape.named(n.row, {q: tape.emit(e, find) for q, e in n.quantities.items()})

                if isinstance(a, Cased):
                    found = named(a.named)
                    values = {n: tape.emit(e, find) for n, e in a.branches.items()}
                    memo[name] = tape.pick([(cond, values[n]) for n, cond in found], a.named.row.id)
                else:
                    quantities = {q: tape.emit(e, find) for q, e in a.quantities.items()}
                    keys = {k: named(how[1]) if how[0] == "named" else how[2][field_of(how[1]) if how[1] is not None else None] for k, how in a.keys.items()}
                    memo[name] = tape.row(a.row, quantities, keys)
            elif name in rule.lets:
                memo[name] = tape.emit(rule.lets[name], find)
            else:
                memo[name] = tape.input(field_of(name))
        return memo[name]

    return find


# --- the interval rule, a second time ----------------------------------------------------------------


class _Failed(Exception):
    pass


_ONE = {"neg": Neg, "abs": Abs, "sqrt": Sqrt, "ln": Ln, "exp": Exp, "cos": Cos}
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


def _read(node: list) -> list[int]:
    """The nodes that a node other than a pick reads."""
    if node[0] in ("c", "s", "pi"):
        return []
    return node[1] if node[0] in _MANY else [node[1]] if node[0] in _ONE or node[0] == "pow" else node[1:]


def _silent(nodes: list[list], roots: list[int], box: list[Interval], outside: bool) -> bool:
    """Whether a root says nothing at any point of the box, as Tape.silent in
    kernel/Petra/Tape.lean decides it: it has no value anywhere because a row gives nothing
    there, or, with `outside`, it is above zero all over the box. A node has no value
    anywhere when it reads one that has none anywhere, and a pick when a node it compares has
    none anywhere, or when in every way of ordering what it compares no case holds or the
    first that holds has none anywhere."""
    v, void = enclosures(nodes, box), []
    for n, node in enumerate(nodes):
        if not isinstance(v[n], str):
            void.append(False)
        elif node[0] != "pick":
            void.append(any(void[i] for i in _read(node)))
        else:
            pairs = list(dict.fromkeys(pair for cond, _ in node[1] for pair in _atoms(cond)))
            ends = [i for pair in pairs for i in pair]
            if any(void[i] or isinstance(v[i], str) for i in ends):
                void.append(any(void[i] for i in ends))
                continue
            options = [[0] if a == b else [s for s, possible in ((-1, v[a].lo < v[b].hi), (0, v[a].lo <= v[b].hi and v[b].lo <= v[a].hi), (1, v[a].hi > v[b].lo)) if possible]
                       for a, b in pairs]
            void.append(math.prod(map(len, options)) <= MAX_CHOICES and all(
                next((void[value] for cond, value in node[1] if _holds(cond, dict(zip(pairs, way)))), True) for way in itertools.product(*options)))
    return any(void[r] or (outside and isinstance(v[r], Interval) and v[r].lo > 0) for r in roots)


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
    least the right side does, when both are known and the right side is above zero.
    `waivable` says that a waiver of the line may rest the cell while it is open: no
    inequality could answer it."""

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
    waivable: bool = False

    @property
    def body(self) -> dict[str, Any]:
        out = {"subject": self.subject, "mechanism": self.mechanism, "entry": self.entry, "state": self.state, **self.proof}
        return {**out, **({"why": self.why} if self.state in ("open", "not_applicable") else {}), **({"rule": self.rule} if self.rule else {})}


def _static(cond: tuple | None, part: Part, parts: Mapping[str, Part]) -> bool:
    """Whether a condition holds for a part. An `is` reads a key of the part, or of the
    part it joins under a name. The answer rests on the keys of the design alone, so it is
    the same under every load case of the card."""
    if cond is None:
        return True
    if cond[0] == "is":
        return _field_of(part, parts, cond[1]) == cond[2]
    if cond[0] == "not":
        return not _static(cond[1], part, parts)
    return (all if cond[0] == "and" else any)(_static(c, part, parts) for c in cond[1:])


def _applies(rule: Rule, part: Part, parts: Mapping[str, Part]) -> bool:
    """Whether a rule answers for a part: its `when` holds, or names a key that the part
    leaves unstated. Nothing then says that the rule does not apply, and its cells are open."""
    return _lacking(part, parts, _keys(rule.when)) is not None or _static(rule.when, part, parts)


def _names(term: Any) -> Iterator[str]:
    if isinstance(term, Sym):
        yield term.name
    for inner in (getattr(term, "args", None) or [getattr(term, name) for name in ("arg", "num", "den", "base") if hasattr(term, name)]):
        yield from _names(inner)


def _keys(cond: tuple | None) -> Iterator[str]:
    """The key fields a condition on a part reads."""
    if cond is not None and cond[0] == "is":
        yield cond[1]
    elif cond is not None:
        for inner in cond[1:]:
            yield from _keys(inner)


def _tables(applied: Applied | Cased) -> Iterator[tuple[rows.Row, Mapping[str, Any]]]:
    """Each row that one use of a row or of a `case` reads, with the expressions its
    quantities are bound to: the row itself, and each row that gives one of its keys a name."""
    if isinstance(applied, Cased):
        yield applied.named.row, applied.named.quantities
        return
    yield applied.row, applied.quantities
    for how in applied.keys.values():
        if how[0] == "named":
            yield how[1].row, how[1].quantities


def _reads(rule: Rule) -> set[str]:
    """What a rule reads, through the rows it applies and the names it defines: each field
    as the rule names it, `width` or `a.Fy`, and each load as `load NAME`."""
    found, seen = {*_keys(rule.when), *_keys(rule.requires)}, set()
    todo = [name for term in (rule.low, rule.high, *(t for w in rule.where for t in w[:2])) if term is not None for name in _names(term)]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        if name in rule.applied:
            todo += [n for _, quantities in _tables(rule.applied[name]) for e in quantities.values() for n in _names(e)]
            if isinstance(rule.applied[name], Cased):
                todo += [n for e in rule.applied[name].branches.values() for n in _names(e)]
            else:
                found |= {how[1] for how in rule.applied[name].keys.values() if how[0] == "field" and how[1] is not None}
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


def _answers(rule: Rule, ask: Ask, part: Part, parts: Mapping[str, Part], cases: tuple[str, ...] = ()) -> Iterator[Cell]:
    """The cells of one rule on one part. A rule that reads no load has one. A rule that
    reads loads has one for each of `cases`, the load cases of the card, and under a case
    that does not put every load it reads on the part its cell is open: a load the card
    does not state is not taken as zero. Before a cell comes one that proves the rule's
    range, where it has one."""
    tail, anchor = rule.id.rpartition("/")[2], _anchor(rule.anchor)

    def cell(entry: str, state: str, why: str = "", **more: Any) -> Cell:
        return Cell(part.name, rule.mechanism, entry, state, rule.says, anchor, why, rule.id, **more)

    # A rule that reads a field the part leaves unstated has no answer: each cell it would give is open. It reads the field in a side, in
    # its `where`, in its `when` or in its `requires`. The kernel names the first such field the rule reads, and this names the first by name.
    named = _reads(rule)
    fields = sorted(name for name in named if not name.startswith("load "))
    lacks = _lacking(part, parts, fields)
    if lacks is not None:
        # A waiver rests these cells when the part leaves keys alone unstated. With a quantity left out the inequality could still be answered.
        keys = not _lacks_quantity(part, parts, fields)
        single = rule.requires is not None or not cases or not any(name.startswith("load ") for name in named)
        for entry in [tail] if single else [f"{tail}/{case}" for case in cases]:
            yield cell(entry, "open", _unstated_why(lacks, "the rule"), waivable=keys)
        return

    if rule.requires is not None:
        # One cell, with no tape and no hint: proved when the condition over keys holds for the part, and refuted when not.
        if _static(rule.requires, part, parts):
            yield cell(tail, "proved")
            return
        # The keys are named while they fit in the reason the kernel prints, and the rest are counted, as in Grid.lean.
        asked, has, said = list(dict.fromkeys(_keys(rule.requires))), "", 0
        for name in asked:
            one = f"{name} is {_field_of(part, parts, name)[:MAX_REASON]}"
            if said and len(f"{has}, {one}".encode("utf-8", "surrogatepass")) > MAX_REASON - 56:
                break
            has += f"{', ' if said else ''}{one}"
            said += 1
        yield cell(tail, "refuted", f"the part is not what the rule requires: {has}{f' and {len(asked) - said} more' if said < len(asked) else ''}")
        return

    def tape_of(pairs: list[tuple[Any, Any]], case: str | None, strict: bool = False) -> tuple[_Tape, list[int], list[tuple[int, int]]]:
        """The tape with a root for each pair: the first side less the second, which is at most
        zero where the pair is in order. A strict root is the pick that is -1 where the first
        side is under the second and 1 elsewhere: it is at most zero on a box only where the
        first side is under the second all over it, and above zero at a point only where it
        is not under it there."""
        tape = _Tape()
        env = _env(tape, rule, part, parts, case)
        sides = [(tape.emit(low, env), tape.emit(high, env)) for low, high in pairs]
        if strict:
            return tape, [tape.node("pick", [[["lt", low, high], tape.const(Fraction(-1))], [None, tape.const(Fraction(1))]]) for low, high in sides], sides
        return tape, [tape.node("add", [low, tape.node("neg", high)]) for low, high in sides], sides

    reads = sorted(name[5:] for name in _reads(rule) if name.startswith("load "))
    if reads and not cases:
        yield cell(tail, "open", f"the card puts no {' and no '.join(reads)} on {part.name}, which the rule reads", waivable=True)
        return
    for case in cases if reads else [None]:
        entry = tail if case is None else f"{tail}/{case}"
        missing = [name for name in reads if case not in part.loads.get(name, {})]
        if missing:
            yield cell(entry, "open", f"case {case} puts no {' and no '.join(missing)} on {part.name}, which the rule reads", waivable=True)
            continue
        try:
            if rule.where:
                tape, roots, _ = tape_of([w[:2] for w in rule.where], case)
                box, labels = [i.range for i in tape.inputs], [i.label for i in tape.inputs]
                partition = _partition(tape.nodes, roots, box, [MAX_LEAVES], labels)
                if partition is None:
                    # A range that holds nowhere in the box leaves the rule nothing to say, and a waiver rests the cell. One that may hold somewhere does not.
                    v = enclosures(tape.nodes, box)
                    outside = next(why for (_, _, why), r in zip(rule.where, roots) if not (isinstance(v[r], Interval) and v[r].hi <= 0))
                    yield cell(entry, "open", f"the rule holds only where {outside}, and that is not proved for {part.name}", waivable=_silent(tape.nodes, roots, box, True))
                    continue
                yield Cell(part.name, rule.mechanism, f"{entry}/where", "proved", "; ".join(w[2] for w in rule.where), anchor, "", rule.id,
                           proof={"partition": partition})
            tape, roots, sides = tape_of([(rule.low, rule.high)], case, rule.strict)
        except NoValue as exc:
            # A tape that cannot be written is a row with nothing for the part's key: no inequality could answer the cell.
            yield cell(entry, "open", str(exc), waivable=True)
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
            # An open cell that a row has no value for anywhere in the box is one a waiver rests. One whose inequality is left undecided is not.
            v, silent = enclosures(tape.nodes, box), _silent(tape.nodes, roots, box, False)
            if isinstance(v[roots[0]], str):
                origin = v.index(v[roots[0]])
                yield cell(entry, "open", (f"{tape.picks[origin]} gives no value at what {part.name} has: " if origin in tape.picks else "") + v[roots[0]], waivable=silent)
            else:
                yield cell(entry, "open", "neither proved over the ranges the card gives nor refuted at a corner of them", waivable=silent)


def cells(design: Design, deck: Deck, found: Parts) -> list[Cell]:
    """Every cell of the design: for each part, each mechanism the grid asks of its type.

    A waiver rests a cell that would be open and that no inequality could answer, and no
    other: the line has no rule for the part, a load case leaves out a load the rule reads, a
    row gives nothing for the part, the rule holds nowhere in the ranges, or the part leaves
    a key unstated and no quantity. The cells of a line are made as if the card waived
    nothing. Where it waives the line on the part, each of them that is open and `waivable`
    becomes `waived`, and says what was open. A cell that a rule proved stays proved, and the
    waiver was not needed for it. A cell that a rule refuted stays refuted: no waiver hides a
    refutation, and a card written before a deck gained a rule does not switch the rule off.
    A cell whose rule is left undecided stays open, and says that the waiver does not rest it."""
    out: list[Cell] = []
    waived = {(w.subject[0], w.mode): w for w in reversed(design.waivers)}      # the first waiver of a line on a part, as the kernel takes it
    for part in found.parts.values():
        for ask in (a for a in deck.asks if a.type == part.type.name):
            anchor, line = _anchor(ask.anchor), []
            if (lacks := _lacking(part, found.parts, _keys(ask.unless))) is not None:
                # The `unless` reads a key that is unstated, so nothing says whether the mechanism can arise: the line is open, and no rule of it is run.
                line.append(Cell(part.name, ask.mechanism, "", "open", ask.what, anchor, _unstated_why(lacks, "the `unless` of the line"), waivable=True))
            elif ask.excused is not None and _static(ask.unless, part, found.parts):
                line.append(Cell(part.name, ask.mechanism, "", "not_applicable", ask.what, anchor, ask.excused))
            else:
                rules = [r for r in deck.rules if (r.type, r.mechanism) == (ask.type, ask.mechanism) and _applies(r, part, found.parts)]
                line += [c for r in rules for c in _answers(r, ask, part, found.parts, found.cases)]
                if not rules:
                    line.append(Cell(part.name, ask.mechanism, "", "open", ask.what, anchor,
                                     f"the deck has no rule for it{' on a part like this one' if any(r.mechanism == ask.mechanism for r in deck.rules) else ''}", waivable=True))
            w = waived.get((part.name, ask.mechanism))
            out += line if w is None else [c if c.state != "open" else replace(c, state="waived", why=f"by {w.owner}: {w.reason}; {WAIVED}{c.why}") if c.waivable
                                           else replace(c, why=f"{UNRESTED}{c.why}") for c in line]
    return out + _unread(deck, found)


def _unread(deck: Deck, found: Parts) -> list[Cell]:
    """An open cell for each quantity and each key that no rule or grid line reads for its
    part, and for each load that no rule reads, once for each case that puts it on the
    part. A value nothing reads is a value nothing checks: a plate that no joint joins
    would pass at any thickness, and a joint whose rules read its shear alone would pass
    under any tension. A load is read by an expression of a rule that applies to the part
    it is on, and by nothing else. The cells are listed part by part: the part's fields in the order of
    its type, and then its loads in the order of their names and of their cases' names."""
    read: set[tuple[str, str]] = set()
    for part in found.parts.values():
        names = {alias: part.values[f.name][n] for f in part.type.fields.values() if f.type is not None for n, alias in enumerate(f.names)}
        fields = {name for a in deck.asks if a.type == part.type.name for name in _keys(a.unless)}
        fields |= {name for r in deck.rules if r.type == part.type.name and _applies(r, part, found.parts) for name in _reads(r)}
        for name in fields:
            alias, dot, inner = name.partition(".")
            read.add((names[alias], inner) if dot else (part.name, name))
    out = []
    for part in found.parts.values():
        out += [Cell(part.name, UNREAD, f.name, "open", f.what, "", f"no rule of the deck reads {part.name}.{f.name}, so nothing checks it")
                for f in part.type.fields.values() if f.type is None and (part.name, f.name) not in read and part.values[f.name] is not NOT_STATED]
        out += [Cell(part.name, UNREAD, f"{load}/{case}", "open", part.type.loads[load].what, "",
                     f"no rule of the deck reads the load {load} that case {case} puts on {part.name}, so nothing checks it")
                for load in sorted(part.loads) if (part.name, f"load {load}") not in read for case in sorted(part.loads[load])]
    return out


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
            said = (c.why if c.state in ("open", "not_applicable", "waived") else ": ".join(filter(None, (c.what, c.why))) if c.state == "refuted"
                    else c.what if c.entry.endswith("/where") else "")
            out.append(f"  {f'{c.subject}/{c.mechanism}':<{wide}}  {c.state.replace('_', ' '):<14}  {ratio:>6}  "
                       + ": ".join(part for part in (c.entry, said) if part) + (f" ({c.anchor})" if c.anchor else ""))
        pending = [c for c in self.cells if c.state == "open"]
        if pending:
            out.append(f"open       {len(pending)} cells: each needs a rule, an input, or `waive MECHANISM on PART by \"<owner>\" reason \"<why>\"` "
                       "in the card, which rests only a cell that no inequality could answer")
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
    def sign(part: str, name: str, load: bool) -> str | None:
        """What the type of a part says with `may_be` of a field, or of a load."""
        its = found.parts.get(part)
        return getattr((its.type.loads if load else its.type.fields).get(name), "may_be", None) if its is not None else None

    broken = wellformed.findings(*(json.loads(files[name]) for name in ("card", "design", "deck")), sign=sign)
    if broken:
        raise ComponentError(tuple(f"{design.path}: {b}" for b in broken))
    return Report(design.name, design.path, deck, tuple(answers)), files
