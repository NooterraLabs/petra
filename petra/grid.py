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
    waived          the card waives the mechanism on the part, the cell would be open without that,
                    and the deck has no rule for the part or a completion of what is left out holds
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
import sys
from dataclasses import dataclass, field, replace
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping

from . import deck as rows
from . import export
from .deck import NONE, RowError, Vector, anchored, dimension, only, quantity, replaced, show
from .ir import Bound, Component, Design, Fixed, ParamRef, Ref, Span, Stated, Text
from .kernel import (MAX_ARGUMENT, Abs, Add, Const, Cos, Div, Exp, Interval, KernelArithmeticError, Ln, Max, Min, Mul, Neg, Pi, PowInt, Sqrt,
                     Sym, enclose)
from .kernel import PRECISION_BITS as PREC
from .models.base import ComponentError

FORMAT = "petra-rules/0"
DECKS = Path(__file__).resolve().parent / "decks"
STATES = ("proved", "refuted", "not_applicable", "waived", "open")
MAX_CHOICES = 4096
"""The most ways a pick may order what it compares, as in kernel/Petra/Tape.lean."""
MAX_ORDERS = 1024
"""The most orders the conditions of one pick may hold between them, as in kernel/Petra/Tape.lean.
A deck whose rule could write a pick of more is refused when it is read."""
MAX_LEAVES = 256
"""The most leaves a partition may have before the search for a proof stops."""
MAX_CORNERS = 6
"""A refuting point is looked for at every corner of the box while no more inputs than this have a range, and past that at one."""
MAX_CLIMB = 65_536
"""The most nodes the climb to that one corner walks, over every time it walks the tape: a tape
of n nodes is walked MAX_CLIMB // n times at most. A round of the climb walks the tape twice
for each ranged input, and it may take a round for each, so without this bound its time grew
as the cube of their number."""
MAX_WORK = 20_000_000_000
"""The work the kernel spends on the proofs of a design (`MAX_WORK` in kernel/Petra/Tape.lean). The
search walks a tape no more often than this pays for the exponentials of a walk (`_walks`)."""
MAX_NAME = 64
"""The most bytes a name may print in that a cell prints whole, as in kernel/Petra/Files.lean:
the name of a part, a load case, a mechanism, a field, a load, a joined part and a `let`, and a rule's id."""
UNREAD = "unread"
"""The mechanism of the cell of a field or a load that nothing reads. No line of the grid has this name."""
WAIVED = "open but for the waiver: "
"""What the kernel's reason of a waived cell starts with. The reason the cell had while it was open follows."""
UNRESTED = "the waiver does not rest this cell: "
"""What the kernel's reason of an open cell of a waived line starts with, when the waiver does not rest it."""
MAX_COMPLETIONS = 64
"""The most completions of what a part and a case leave out that the search tries for one
cell, as witnesses for a waiver or, for a rule with an inequality, as refutations."""
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
    # A `least` is not under the floor of its dimension where that floor holds for the quantity, as type rule 4 holds a load of the card:
    # one under zero always, and one at zero unless the quantity may be negative. A completion of a load left out goes down to its `least`.
    floor = _floor(dim)
    if least is not None and floor is not None and (may_be != "negative" or floor[1] < 0) and least < floor[1]:
        raise DeckError(f"field {name}: its least, {least} in SI units, is under {floor[1]}, the floor of a {floor[0]}, and no card states a value under it")
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


def _signs(kind: Type, types: Mapping[str, Type]) -> dict[str, tuple[str, str]]:
    """The names of a rule that say `may_be`, each with what it says and the name a message
    gives it: a field of the type, a field of a part it joins, and a load."""
    out = {f"load {f.name}": (f.may_be, f.name) for f in kind.loads.values() if f.may_be}
    for f in kind.fields.values():
        if f.type is None:
            if f.may_be:
                out[f.name] = (f.may_be, f.name)
            continue
        for part in f.names:
            out |= {f"{part}.{g.name}": (g.may_be, f"{part}.{g.name}") for g in types[f.type].fields.values() if g.type is None and g.may_be}
    return out


def _may_be(term: Any, signs: Mapping[str, tuple[str, str]]) -> tuple[str, str] | None:
    """What `may_be` lets a term be, and the name that says it, as mayBe in
    kernel/Petra/Deck.lean finds it: a name that says it, a power other than zero of one, or a
    root of one. An even power of one that may be under zero is at least zero. Any other term
    is None: a sum, a product, a quotient and a row are not looked into."""
    if isinstance(term, Sym):
        return signs.get(term.name)
    if isinstance(term, PowInt) and term.exponent != 0:
        found = _may_be(term.base, signs)
        return ("zero", found[1]) if found is not None and found[0] == "negative" and term.exponent % 2 == 0 else found
    if isinstance(term, Sqrt):
        return _may_be(term.arg, signs)
    return None


def _no_value(term: Any, signs: Mapping[str, tuple[str, str]]) -> None:
    """Refuses a quotient by a quantity that `may_be` lets be zero, a root of one it lets be
    under zero, and a logarithm of either, anywhere in the term, as mayBeChecked in
    kernel/Petra/Deck.lean does: at that value of the field the term has no value, for every
    part."""
    if isinstance(term, Div) and (found := _may_be(term.den, signs)) is not None:
        raise RowError(f"it divides by {found[1]}, which its `may_be` lets be zero")
    if isinstance(term, Sqrt) and (found := _may_be(term.arg, signs)) is not None and found[0] == "negative":
        raise RowError(f"it takes the root of {found[1]}, which its `may_be` lets be under zero")
    if isinstance(term, Ln) and (found := _may_be(term.arg, signs)) is not None:
        raise RowError(f"it takes the logarithm of {found[1]}, which its `may_be` lets be zero")
    for inner in (term.args if isinstance(term, (Add, Mul, Min, Max)) else (term.num, term.den) if isinstance(term, Div)
                  else (term.base,) if isinstance(term, PowInt) else (term.arg,) if isinstance(term, (Neg, Abs, Sqrt, Ln, Exp, Cos)) else ()):
        _no_value(inner, signs)


def _compared(cond: tuple | None) -> Iterator[Any]:
    """The terms that a condition of a row's case compares."""
    if cond is None:
        return
    if cond[0] in ("le", "lt", "ge", "gt"):
        yield from cond[1:]
    else:
        for inner in cond[1:]:
            yield from _compared(inner)


def _refuse_no_value(kind: Type, types: Mapping[str, Type], lets: Mapping[str, Any], sides: list[Any], applied: Mapping[str, Any]) -> None:
    """Every term a rule reads, through `_no_value`. A name of `let` and an input of a row the
    rule applies stand for what they are bound to, as the kernel's steps hand those on: a
    quotient by an input bound to a field that may be zero is a quotient by the field."""
    signs = _signs(kind, types)
    for name, term in lets.items():
        _no_value(term, signs)
        if (found := _may_be(term, signs)) is not None:
            signs[name] = found
    for term in sides:
        _no_value(term, signs)
    for use in applied.values():
        if isinstance(use, Cased):
            terms = [*use.named.quantities.values(), *use.branches.values()]
        else:
            terms = [*use.quantities.values(), *(q for selector in use.keys.values() if selector[0] == "named" for q in selector[1].quantities.values())]
        for term in terms:
            _no_value(term, signs)
        if isinstance(use, Applied):
            inside = {name: found for name, term in use.quantities.items() if (found := _may_be(term, signs)) is not None}
            for case in use.row.cases:
                for term in (case.expr, *_compared(case.when)):
                    _no_value(term, inside)


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


def _over_orders(count: int) -> str:
    """Why a deck is refused that would write a pick of `count` orders, past MAX_ORDERS, in the kernel's words."""
    return f"a pick of the rule's tape would compare {count} orders, over the budget of {MAX_ORDERS} for one pick"


def _place_orders(axis: rows.Axis) -> list[int]:
    """The orders of the condition that a quantity is at each place of a side: two for a listed value, one for each end of a band."""
    return [2] * len(axis.at) if axis.at else [1 if hi is None else 2 for _, hi in axis.bands]


def _named_orders(row: rows.Row) -> int:
    """The orders of the conditions under which the quantities are at the cells of a row that gives a name, the empty ones left out."""
    places = [_place_orders(axis) for axis in row.table.axes] + [[0]]
    return sum(places[0][i] + places[1][j] for i, line in enumerate(row.table.cells) for j, cell in enumerate(line) if cell is not None)


def _cond_orders(cond: Any) -> int:
    """The orders a condition of a row's case or of a tape's pick compares."""
    if cond is None:
        return 0
    if cond[0] in ("and", "or"):
        return sum(map(_cond_orders, cond[1] if isinstance(cond[1], list) else cond[1:]))
    return _cond_orders(cond[1]) if cond[0] == "not" else 1


def _picks(applied: Mapping[str, Applied | Cased], where: tuple) -> int:
    """The most orders a pick of the rule's tape compares for any part, as `push` in kernel/Petra/Deck.lean counts them when it reads
    the rule: the cases of an equation, the places of a table down or across, the cells of a row that gives a name, and the `where`."""
    most = len(where)
    for a in applied.values():
        if isinstance(a, Cased):
            most = max(most, _named_orders(a.named.row))
        elif a.row.table is None:
            most = max(most, 0 if a.row.cases[0].when is None else sum(_cond_orders(c.when) for c in a.row.cases))
        else:
            for axis in a.row.table.axes:
                how = a.keys.get(axis.by) if axis.keys else None
                most = max(most, _named_orders(how[1].row) if how is not None and how[0] == "named" else 0 if axis.keys else sum(_place_orders(axis)))
    return most


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
        if (most := _picks(binder.applied, ranges)) > MAX_ORDERS:
            raise RowError(_over_orders(most))
        _refuse_no_value(types[body["type"]], types, lets, [low, high, *(term for a, b, _ in ranges for term in (a, b))], binder.applied)
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
    problems += [f"{_at(x.span)}: a load case is not named where: an entry that ends in /where is the range of a rule" for x in design.loads.values() if x.name == "where"]
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
        """The first case that holds. A lone case that holds otherwise is its value. With no case it is a pick that has no value
        anywhere, as the kernel writes a table that gives nothing for the part and an equation with no case: the tape is still
        written, so a `case` whose branch for one name reads such a table has a value where the row gives another name. A pick
        holds at most MAX_ORDERS orders, as the kernel's `pickOf` does, and reading the deck refuses a rule that could write more."""
        if cases and cases[0][0] is None:
            return cases[0][1]
        if (count := sum(_cond_orders(c) for c, _ in cases)) > MAX_ORDERS:
            raise NoValue(_over_orders(count))
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
    a pick reads only what it compares and the cases some ordering chooses. An exponential
    has none once the exponentials of the walk take more work than MAX_WORK (`_charged`),
    which the kernel could not pay for on any box. A walk of a tape with a hundred
    exponentials of some 65,000 took Python minutes, and now takes it seconds."""
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

    seen: set[Fraction] = set()
    spent = 0
    for n, node in enumerate(nodes):
        if node[0] == "exp" and (spent := spent + _charged(v[node[1]], seen)) > MAX_WORK:
            v.append(f"node {n}: the exponentials of the tape take more than the {MAX_WORK} units of work the kernel spends on a design")
            continue
        try:
            v.append(step(node))
        except _Failed as exc:
            v.append(str(exc))
        except KernelArithmeticError as exc:
            v.append(f"node {n}: {exc}")
    return v


def _partition(nodes: list[list], roots: list[int], box: list[Interval], budget: list[int], labels: list[str],
               refuting: list[list[Fraction]] | None = None) -> Any:
    """A partition on whose every leaf every root is at most zero, or None when the search
    finds none within its budget. Splits the input with the widest range, at its middle,
    and names it by its label, as proofs.json does for the kernel. Given `refuting`, the
    search also tries the middle of each box it does not prove, and stops at the first where
    the first root is above zero, which it puts there. The budget is held to the walks that
    `_walks` allows over the box, two for each box where the search tries the middle."""
    v = enclosures(nodes, box)
    if all(isinstance(v[r], Interval) and v[r].hi <= 0 for r in roots):
        return "leaf"
    budget[0] = min(budget[0], _walks(nodes, v) // (1 if refuting is None else 2))
    if refuting is not None and budget[0] > 0 and _above(nodes, roots[0], middle := [x.midpoint() for x in box]):
        refuting.append(middle)
        return None
    budget[0] -= 1
    widest = max(range(len(box)), key=lambda k: box[k].width(), default=None)
    if widest is None or box[widest].width() == 0 or budget[0] <= 0:
        return None
    cut = box[widest].midpoint()
    halves = []
    for half in (Interval(box[widest].lo, cut), Interval(cut, box[widest].hi)):
        found = _partition(nodes, roots, [*box[:widest], half, *box[widest + 1:]], budget, labels, refuting)
        if found is None:
            return None
        halves.append(found)
    return {"input": labels[widest], "at": export.number(cut), "below": halves[0], "above": halves[1]}


def _nowhere(nodes: list[list], roots: list[int], box: list[Interval]) -> int | None:
    """The first root that is above zero at every point of the box, as Tape.above in
    kernel/Petra/Tape.lean finds it: its enclosure over the whole box has a lower end above
    zero. For the tape of a rule's `where`, such a root says that the rule holds nowhere in
    the box."""
    v = enclosures(nodes, box)
    return next((k for k, r in enumerate(roots) if isinstance(v[r], Interval) and v[r].lo > 0), None)


def _exp_work(x: Fraction) -> int:
    """The work `expWork` in kernel/Petra/Tape.lean charges for the first enclosure of the exponential of an end `x`, of 128 bits.
    The time of an exponential grows as the square of its end: Python takes two seconds for an end of 65,536, whose work is 3.1
    billion units, and MAX_WORK pays for six."""
    c = math.ceil(abs(x))
    s = c.bit_length() + 1
    q = PREC + 32 + 2 * s + 2 * c
    wide, words = q // 64 + 1, (abs(x.numerator).bit_length() + x.denominator.bit_length()) // 64 + 1
    return (max(32, 2 * q // q.bit_length()) * (10000 + 54 * wide + 20 * words + wide * words // 3) + (s + 16) * wide * wide // 4) * 17 // 10


def _charged(x: Any, seen: set[Fraction]) -> int:
    """The work of an exponential of the enclosure `x` on a walk that has computed the ends `seen`, which then has its ends too:
    the work of each end it has not computed, as the kernel's caches keep the ends it has. Nothing for an end of zero, and for an
    enclosure that has no exponential."""
    if not isinstance(x, Interval) or x.lo < -MAX_ARGUMENT or x.hi > MAX_ARGUMENT:
        return 0
    ends = {x.lo, x.hi} - seen - {0}
    seen |= ends
    return sum(map(_exp_work, ends))


def _walks(nodes: list[list], v: list[Any]) -> int:
    """How many times the search may walk the tape over a box where its nodes have the enclosures `v`: as many as MAX_WORK pays
    for the exponentials of a walk (`_charged`). It pays for three walks of a tape with an exponential from -65,536 to 65,536, and
    for 1,385 of one from -1,000 to 1,000, more than the 256 leaves of a partition or the 64 corners of a box take. A tape with no
    exponential is walked as often as the search's other bounds allow."""
    seen: set[Fraction] = set()
    cost = sum(_charged(v[node[1]], seen) for node in nodes if node[0] == "exp")
    return MAX_WORK // cost if cost else MAX_WORK


def _height(nodes: list[list], root: int, point: list[Fraction]) -> Fraction | None:
    """The least the root may be at a point, or None where it has no value."""
    at = enclosures(nodes, [Interval.point(x) for x in point])[root]
    return at.lo if isinstance(at, Interval) else None


def _above(nodes: list[list], root: int, point: list[Fraction]) -> bool:
    return (height := _height(nodes, root, point)) is not None and height > 0


def _refuting(nodes: list[list], root: int, box: list[Interval]) -> list[Fraction] | None:
    """A point of the box where the root is above zero: a corner of it while no more inputs
    than MAX_CORNERS have a range, and past that the corner the root climbs to; and then its
    middle. The climb starts at the middle and sets each ranged input in turn to the end of
    its range where the root is higher, the others held, until a round moves none, there
    have been as many rounds as ranged inputs, or it has walked MAX_CLIMB nodes; it stops
    where it is then. The climb, and the points tried, are each held to the walks that
    `_walks` allows over the box. Where the root has no value it is lowest."""
    ranged = [k for k, x in enumerate(box) if x.width() > 0]
    middle, allowed = [x.midpoint() for x in box], _walks(nodes, enclosures(nodes, box))
    if len(ranged) <= MAX_CORNERS:
        corners = [list(p) for p in itertools.product(*((x.lo, x.hi) if x.width() > 0 else (x.lo,) for x in box))]
    else:
        point, walks = list(middle), min(MAX_CLIMB // max(len(nodes), 1), allowed)
        for _ in ranged:
            moved = False
            for k in ranged:
                if walks < 2:
                    break
                walks -= 2
                low, high = (_height(nodes, root, [*point[:k], end, *point[k + 1:]]) for end in (box[k].lo, box[k].hi))
                end = box[k].hi if low is None or (high is not None and high >= low) else box[k].lo
                moved, point[k] = moved or end != point[k], end
            if not moved or walks < 2:
                break
        corners = [point]
    return next((point for point in [*corners, middle][:allowed] if _above(nodes, root, point)), None)


def _searched(nodes: list[list], roots: list[int], box: list[Interval]) -> list[Fraction] | None:
    """A point of the box where the first root is above zero: one that `_refuting` finds, or
    else the middle of a box that the search for a proof of the roots cannot prove."""
    if (point := _refuting(nodes, roots[0], box)) is not None:
        return point
    found: list[list[Fraction]] = []
    _partition(nodes, roots, box, [MAX_LEAVES], [""] * len(box), found)
    return next(iter(found), None)


# --- cells -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Cell:
    """One answer. `body` is the cell as proofs.json holds it: a hint, which the kernel
    tries on the tape it writes itself. `proof` is the partition of a proved cell or the
    point of a refuted one. `ratio` is the most the left side of the rule reaches over the
    least the right side does, when both are known and the right side is above zero.
    `waivable` says that a waiver of the line may rest the cell while it is open: the deck
    has no rule for the part, or `completion` makes the rule hold. That is the names of the
    unstated keys and the values of the left-out loads, as `(keys, loads)`, each key
    `(PART, FIELD, NAME)` and each load `(PART, LOAD, CASE, VALUE)`. `hints` are the hints
    the cell gives proofs.json when they are not its `body` alone: one for each completion
    of a refuted cell, or the one with the completion of a waivable cell. `waiver` is who
    signed the waiver a waived cell rests on, and why."""

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
    waiver: tuple[str, str] | None = None
    completion: tuple[tuple, tuple] | None = None
    hints: tuple[Mapping[str, Any], ...] | None = None

    @property
    def body(self) -> dict[str, Any]:
        out = {"subject": self.subject, "mechanism": self.mechanism, "entry": self.entry, "state": self.state, **self.proof}
        return {**out, **({"why": self.why} if self.state in ("open", "not_applicable") else {}), **({"rule": self.rule} if self.rule else {})}


def _completion_body(keys: Iterable[tuple[str, str, str]], loads: Iterable[tuple[str, str, str, Fraction]]) -> dict[str, list]:
    """A completion as proofs.json holds it."""
    return {"keys": [list(k) for k in keys], "loads": [[p, load, case, export.number(x)] for p, load, case, x in loads]}


def _unsaid(part: Part, parts: Mapping[str, Part], names: Iterable[str]) -> list[tuple[str, str, tuple[str, ...]]]:
    """The keys of these fields, as a rule names them, that the part or the part it joins
    leaves unstated, each once in the order of the names: the part that has it, the field
    and the names the key may take."""
    found: list[tuple[str, str, tuple[str, ...]]] = []
    for name in names:
        if _field_of(part, parts, name) is not NOT_STATED:
            continue
        alias, dot, inner = name.partition(".")
        owner = next(parts[part.values[f.name][f.names.index(alias)]] for f in part.type.fields.values() if f.type is not None and alias in f.names) if dot else part
        field = owner.type.fields[inner if dot else name]
        if field.keys and not any((o, f) == (owner.name, field.name) for o, f, _ in found):
            found.append((owner.name, field.name, field.keys))
    return found


def _completed(part: Part, parts: Mapping[str, Part], keys: Iterable[tuple[str, str, str]],
               loads: Iterable[tuple[str, str, str, Fraction]]) -> tuple[Part, dict[str, Part]]:
    """The part and the parts with each key of a completion named, and each of its loads put
    on the part as one value, labelled `put:CASE.PART.LOAD` as Completion.onto in
    kernel/Petra/Grid.lean labels it."""
    changed = dict(parts)
    for owner, field, name in keys:
        changed[owner] = replace(changed[owner], values={**changed[owner].values, field: name})
    for on, load, case, x in loads:
        p = changed[on]
        changed[on] = replace(p, loads={**p.loads, load: {**p.loads.get(load, {}), case: Value(f"put:{case}.{on}.{load}", Interval.point(x))}})
    return changed[part.name], changed


def _choices(unsaid: list[tuple[str, str, tuple[str, ...]]], prefer: Mapping[Any, Any]) -> Iterator[tuple[tuple[str, str, str], ...]]:
    """The combinations of the names of the keys, the names that `prefer` holds first."""
    ordered = [sorted(names, key=lambda n: n != prefer.get((owner, field))) for owner, field, names in unsaid]
    for combo in itertools.product(*ordered):
        yield tuple((owner, field, name) for (owner, field, _), name in zip(unsaid, combo))


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
    """The demand over the capacity, for the report: none where the capacity may be zero or under, or the ratio is past the largest
    float, as a pull of 10^99 kip on a plate of 10^-98 inch is."""
    v = enclosures(nodes, box)
    if isinstance(v[low], Interval) and isinstance(v[high], Interval) and v[high].lo > 0:
        q = v[low].hi / v[high].lo
        return float(q) if abs(q) <= sys.float_info.max else None
    return None


def _refusal(rule: Rule, part: Part, parts: Mapping[str, Part]) -> str:
    """Why a part is not what a rule requires, as Part.refusal in kernel/Petra/Grid.lean says
    it: each key the rule names and the name the part has for it, or `unstated`, named while
    they fit in the reason the kernel prints, and the rest counted."""
    asked, has, said = list(dict.fromkeys(_keys(rule.requires))), "", 0
    for name in asked:
        one = f"{name} is {str(_field_of(part, parts, name))[:MAX_REASON]}"
        if said and len(f"{has}, {one}".encode("utf-8", "surrogatepass")) > MAX_REASON - 56:
            break
        has += f"{', ' if said else ''}{one}"
        said += 1
    return f"the part is not what the rule requires: {has}{f' and {len(asked) - said} more' if said < len(asked) else ''}"


def _listed(names: list[str]) -> str:
    """Loads for a reason, as the kernel lists them: the first four, and how many more."""
    return " and no ".join(names[:4]) + (f" and {len(names) - 4} more" if len(names) > 4 else "")


def _least(load: Field) -> Fraction:
    """The value a completion first tries for a load: its `least`, or zero, and not under the floor of its dimension where that floor
    holds for the load, as Completion.fits in kernel/Petra/Grid.lean holds it. A deck whose `least` is under that floor does not load."""
    floor, least = _floor(load.dim), load.least if load.least is not None else Fraction(0)
    return least if floor is None or (load.may_be == "negative" and floor[1] >= 0) else max(least, floor[1])


def _incomplete(rule: Rule, part: Part, parts: Mapping[str, Part], unsaid: list[tuple[str, str, tuple[str, ...]]], missing: list[str],
                case: str, waived: bool, prefer: dict[Any, Any], pending: Cell, tape_of: Callable[..., tuple[_Tape, list[int], list]]) -> Cell:
    """The cell of a rule for a part that leaves the keys of `unsaid` unstated, or under the
    load case `case` that leaves out the loads of `missing`, as `incomplete` in
    kernel/Petra/Grid.lean settles it from the hints this cell gives. `case` is empty for a
    card with no load case, and `pending` is the open cell.

    It is refuted when no load is left out and, under each combination of the names of the
    keys, the rule answers for the part and fails: its `requires` does not hold, or the
    search finds a point that refutes its tape there, which is a hint with that combination.
    The combinations are tried while there are at most MAX_TRIED for a rule with `requires`
    and MAX_COMPLETIONS for one with an inequality.

    On a line the card waives, it is otherwise open with the first of at most MAX_COMPLETIONS
    completions that is a witness: under it the rule does not answer, its `requires` holds,
    or the search proves its tape. The names and the values that `prefer` holds come first,
    and a load takes its `least`, or zero. `prefer` gains the witness. The tape a point refutes,
    for a rule with a `where`, is the rule's inside the `where` and -1 outside it. A witness
    for such a rule shows the `where` holds nowhere in the box, or proves it and the rule over
    the whole box."""
    def gated(on: Part, among: Mapping[str, Part]) -> tuple[_Tape, list[int], list]:
        return tape_of([(rule.low, rule.high)], case, rule.strict, [w[:2] for w in rule.where], on, among)

    base = {k: v for k, v in pending.body.items() if k != "why"}
    if not missing and math.prod(len(names) for _, _, names in unsaid) <= (MAX_TRIED if rule.requires is not None else MAX_COMPLETIONS):
        hints = []
        for keys in _choices(unsaid, {}):
            on, among = _completed(part, parts, keys, ())
            if not _static(rule.when, on, among):
                break
            if rule.requires is not None:
                if _static(rule.requires, on, among):
                    break
                continue
            try:
                tape, roots, _ = gated(on, among)
            except NoValue:
                break
            if (point := _searched(tape.nodes, roots, [i.range for i in tape.inputs])) is None:
                break
            hints.append({**base, "state": "refuted", "point": {i.label: export.number(x) for i, x in zip(tape.inputs, point)},
                          "completion": _completion_body(keys, ())})
        else:
            return replace(pending, state="refuted", why=_refusal(rule, part, parts) if rule.requires is not None else "", hints=tuple(hints) or None)
    if not waived:
        return pending
    loads = tuple((part.name, load, case, prefer.get((part.name, load, case), _least(part.type.loads[load]))) for load in missing)
    for keys in itertools.islice(_choices(unsaid, prefer), MAX_COMPLETIONS):
        on, among = _completed(part, parts, keys, loads)
        hint = {**pending.body, "completion": _completion_body(keys, loads)}
        found = not _static(rule.when, on, among)
        if not found and rule.requires is not None:
            found = _static(rule.requires, on, among)
        elif not found:
            # A witness meets what a complete cell must: a `where` that holds nowhere in the box, or a partition that proves the `where`
            # and the rule over the whole box, as the `/where` cell and the rule's cell are proved.
            try:
                if rule.where:
                    tape, roots, _ = tape_of([w[:2] for w in rule.where], case, False, (), on, among)
                    found = _nowhere(tape.nodes, roots, [i.range for i in tape.inputs]) is not None
                if not found:
                    tape, roots, _ = tape_of([(rule.low, rule.high)], case, rule.strict, (), on, among, [w[:2] for w in rule.where])
            except NoValue:
                continue
            if not found and (partition := _partition(tape.nodes, roots, [i.range for i in tape.inputs], [MAX_LEAVES], [i.label for i in tape.inputs])) is not None:
                hint["partition"], found = partition, True
        if found:
            prefer.update({(owner, f): name for owner, f, name in keys} | {(p, load, c): x for p, load, c, x in loads})
            return replace(pending, waivable=True, completion=(keys, loads), hints=(hint,))
    return pending


def _answers(rule: Rule, ask: Ask, part: Part, parts: Mapping[str, Part], cases: tuple[str, ...] = (), waived: bool = False,
             prefer: dict[Any, Any] | None = None) -> Iterator[Cell]:
    """The cells of one rule on one part. A rule that reads no load has one. A rule that
    reads loads has one for each of `cases`, the load cases of the card, or one when the card
    has none. Under a case that does not put every load it reads on the part, and for a part
    that leaves a key it reads unstated, its cell is incomplete (`_incomplete`): a load the
    card does not state is not taken as zero. Before a cell comes one that proves the rule's
    range, where it has one. `waived` says that the card waives the line on the part, and
    `prefer` holds the names and the values that the cells before these were completed with."""
    tail, anchor = rule.id.rpartition("/")[2], _anchor(rule.anchor)
    prefer = {} if prefer is None else prefer

    def cell(entry: str, state: str, why: str = "", **more: Any) -> Cell:
        return Cell(part.name, rule.mechanism, entry, state, rule.says, anchor, why, rule.id, **more)

    # A rule that reads a field the part leaves unstated has no answer of its own. It reads the field in a side, in its `where`, in its
    # `when` or in its `requires`. The kernel names the first such field the rule reads, and this names the first by name. With a quantity
    # left unstated each cell the rule would give is open, and no waiver rests it: no hint names a value for a quantity.
    named = _reads(rule)
    fields = sorted(name for name in named if not name.startswith("load "))
    reads = sorted(name[5:] for name in named if name.startswith("load "))
    lacks, unsaid = _lacking(part, parts, fields), []
    if lacks is not None:
        if _lacks_quantity(part, parts, fields):
            single = rule.requires is not None or not cases or not reads
            for entry in [tail] if single else [f"{tail}/{case}" for case in cases]:
                yield cell(entry, "open", _unstated_why(lacks, "the rule"))
            return
        unsaid = _unsaid(part, parts, fields)

    def tape_of(pairs: list[tuple[Any, Any]], case: str | None, strict: bool = False, within: list[tuple[Any, Any]] = (),
                on: Part = part, among: Mapping[str, Part] = parts, first: list[tuple[Any, Any]] = ()) -> tuple[_Tape, list[int], list[tuple[int, int]]]:
        """The tape with a root for each pair: the first side less the second, which is at most
        zero where the pair is in order. A strict root is the pick that is -1 where the first
        side is under the second and 1 elsewhere: it is at most zero on a box only where the
        first side is under the second all over it, and above zero at a point only where it
        is not under it there. With `within`, the pairs of a `where`, a root is the pick that is
        that root where each pair of `within` is in order and -1 elsewhere: it is above zero at
        a point only inside the `where`, where the pair is out of order. With `first`, the pairs
        of a `where` too, the tape has a root for each of them before the others, as for `le`,
        and a partition that proves it proves the `where` and the rule over the whole box. `on`
        and `among` are the part and the parts, as a completion has them."""
        tape = _Tape()
        env = _env(tape, rule, on, among, case)
        ahead = [tape.node("add", [tape.emit(low, env), tape.node("neg", tape.emit(high, env))]) for low, high in first]
        sides = [(tape.emit(low, env), tape.emit(high, env)) for low, high in pairs]
        gate = ["and", [["le", tape.emit(low, env), tape.emit(high, env)] for low, high in within]]
        if strict:
            roots = [tape.node("pick", [[["lt", low, high], tape.const(Fraction(-1))], [None, tape.const(Fraction(1))]]) for low, high in sides]
        else:
            roots = [tape.node("add", [low, tape.node("neg", high)]) for low, high in sides]
        if within:
            roots = [tape.node("pick", [[gate, root], [None, tape.const(Fraction(-1))]]) for root in roots]
        return tape, ahead + roots, sides

    for case in cases if reads and cases else [None]:
        entry = tail if case is None else f"{tail}/{case}"
        missing = reads if case is None else [name for name in reads if case not in part.loads.get(name, {})]
        if unsaid or missing:
            why = (_unstated_why(lacks, "the rule") if unsaid else f"the card puts no {_listed(missing)} on {part.name}, which the rule reads" if case is None
                   else f"case {case} puts no {_listed(missing)} on {part.name}, which the rule reads")
            yield _incomplete(rule, part, parts, unsaid, missing, case or "", waived, prefer, cell(entry, "open", why), tape_of)
            continue
        if rule.requires is not None:
            # One cell, with no tape and no hint: proved when the condition over keys holds for the part, and refuted when not.
            yield cell(tail, "proved") if _static(rule.requires, part, parts) else cell(tail, "refuted", _refusal(rule, part, parts))
            continue
        try:
            if rule.where:
                tape, roots, _ = tape_of([w[:2] for w in rule.where], case)
                box, labels = [i.range for i in tape.inputs], [i.label for i in tape.inputs]
                partition = _partition(tape.nodes, roots, box, [MAX_LEAVES], labels)
                if partition is None:
                    # A point inside the range where the rule fails refutes it, as the tape whose root is the rule's inside the `where` and
                    # -1 outside it shows there. The kernel tries no partition of that tape: it proves nothing of a part that may be outside.
                    try:
                        gated = tape_of([(rule.low, rule.high)], case, rule.strict, [w[:2] for w in rule.where])
                    except NoValue:
                        gated = None
                    if gated is not None and (point := _searched(gated[0].nodes, gated[1], [i.range for i in gated[0].inputs])) is not None:
                        yield cell(entry, "refuted", ratio=_ratio(gated[0].nodes, *gated[2][0], [Interval.point(x) for x in point]),
                                   proof={"point": {i.label: export.number(x) for i, x in zip(gated[0].inputs, point)}})
                        continue
                    # A range that holds nowhere in the box is a part the deck has no rule for, and a waiver rests the cell. One that may
                    # hold somewhere does not. As the kernel, this looks only on a line the card waives.
                    if waived and (k := _nowhere(tape.nodes, roots, box)) is not None:
                        yield cell(entry, "open", f"the rule holds only where {rule.where[k][2]}, and that holds nowhere in the ranges for {part.name}", waivable=True)
                        continue
                    v = enclosures(tape.nodes, box)
                    outside = next(why for (_, _, why), r in zip(rule.where, roots) if not (isinstance(v[r], Interval) and v[r].hi <= 0))
                    yield cell(entry, "open", f"the rule holds only where {outside}, and that is not proved for {part.name}")
                    continue
                yield Cell(part.name, rule.mechanism, f"{entry}/where", "proved", "; ".join(w[2] for w in rule.where), anchor, "", rule.id,
                           proof={"partition": partition})
            tape, roots, sides = tape_of([(rule.low, rule.high)], case, rule.strict)
        except NoValue as exc:
            # A tape that cannot be written leaves the cell open, and a waiver does not rest it: the deck must cover the part.
            yield cell(entry, "open", str(exc))
            continue
        box, labels = [i.range for i in tape.inputs], [i.label for i in tape.inputs]
        partition = _partition(tape.nodes, roots, box, [1], labels)
        point = None if partition is not None else _refuting(tape.nodes, roots[0], box)
        if partition is None and point is None:
            found: list[list[Fraction]] = []
            partition = _partition(tape.nodes, roots, box, [MAX_LEAVES], labels, found)
            point = next(iter(found), None)
        if partition is not None:
            yield cell(entry, "proved", ratio=_ratio(tape.nodes, *sides[0], box), proof={"partition": partition})
        elif point is not None:
            yield cell(entry, "refuted", ratio=_ratio(tape.nodes, *sides[0], [Interval.point(x) for x in point]),
                       proof={"point": {label: export.number(x) for label, x in zip(labels, point)}})
        else:
            # An open cell stays open under a waiver, whether its inequality is left undecided or a table has no value for the part.
            v = enclosures(tape.nodes, box)
            if isinstance(v[roots[0]], str):
                origin = v.index(v[roots[0]])
                yield cell(entry, "open", (f"{tape.picks[origin]} gives no value at what {part.name} has: " if origin in tape.picks else "") + v[roots[0]])
            else:
                yield cell(entry, "open", "neither proved over the ranges the card gives nor refuted at a point of them the search tried")


def cells(design: Design, deck: Deck, found: Parts) -> list[Cell]:
    """Every cell of the design: for each part, each mechanism the grid asks of its type.

    A waiver rests a cell that would be open for which the deck has no rule, or that a
    completion of what the part and the card leave out makes hold, and no other: the line
    has no rule for the part, the rule holds nowhere in the ranges, or the cell is
    incomplete and has a witness (`_incomplete`). The cells of a line are made as if the card
    waived nothing. Where it waives the line on the part, each of them that is open and
    `waivable` becomes `waived`, and says what was open, while its completion names each key
    and each load as the completions of the cells rested before it do. A cell that a rule
    proved stays proved, and the waiver was not needed for it. A cell that a rule refuted
    stays refuted: no waiver hides a refutation, and a card written before a deck gained a
    rule does not switch the rule off. Any other open cell stays open, and says that the
    waiver does not rest it."""
    out: list[Cell] = []
    waived = {(w.subject[0], w.mode): w for w in reversed(design.waivers)}      # the first waiver of a line on a part, as the kernel takes it
    fixed: dict[Any, Any] = {}      # each key and each load the rested cells' completions name, as the kernel's fixedKeys and fixedLoads
    for part in found.parts.values():
        for ask in (a for a in deck.asks if a.type == part.type.name):
            anchor, line, prefer = _anchor(ask.anchor), [], dict(fixed)
            w = waived.get((part.name, ask.mechanism))
            if (lacks := _lacking(part, found.parts, _keys(ask.unless))) is not None:
                # The `unless` reads a key that is unstated, so nothing says whether the mechanism can arise: the line is open, and no rule of it
                # is run. On a line the card waives, a completion under which the `unless` holds is a witness.
                pending = Cell(part.name, ask.mechanism, "", "open", ask.what, anchor, _unstated_why(lacks, "the `unless` of the line"))
                unsaid = _unsaid(part, found.parts, list(dict.fromkeys(_keys(ask.unless))))
                for keys in itertools.islice(_choices(unsaid, prefer), MAX_COMPLETIONS) if w is not None else ():
                    if _static(ask.unless, *_completed(part, found.parts, keys, ())):
                        pending = replace(pending, waivable=True, completion=(keys, ()), hints=({**pending.body, "completion": _completion_body(keys, ())},))
                        break
                line.append(pending)
            elif ask.excused is not None and _static(ask.unless, part, found.parts):
                line.append(Cell(part.name, ask.mechanism, "", "not_applicable", ask.what, anchor, ask.excused))
            else:
                rules = [r for r in deck.rules if (r.type, r.mechanism) == (ask.type, ask.mechanism) and _applies(r, part, found.parts)]
                line += [c for r in rules for c in _answers(r, ask, part, found.parts, found.cases, w is not None, prefer)]
                if not rules:
                    line.append(Cell(part.name, ask.mechanism, "", "open", ask.what, anchor,
                                     f"the deck has no rule for it{' on a part like this one' if any(r.mechanism == ask.mechanism for r in deck.rules) else ''}", waivable=True))
            if w is None:
                out += line
                continue
            for c in line:
                named = {} if c.completion is None else {(owner, f): name for owner, f, name in c.completion[0]} | {(p, load, case): x for p, load, case, x in c.completion[1]}
                if c.state != "open":
                    out.append(c)
                elif c.waivable and all(fixed.get(k, v) == v for k, v in named.items()):
                    fixed.update(named)
                    out.append(replace(c, state="waived", why=f"by {w.owner}: {w.reason}; {WAIVED}{c.why}", waiver=(w.owner, w.reason)))
                else:
                    out.append(replace(c, why=f"{UNRESTED}{c.why}"))
    return out + _unread(deck, found, fixed)


def _unread(deck: Deck, found: Parts, fixed: Mapping[Any, Any] | None = None) -> list[Cell]:
    """An open cell for each quantity and each key that no rule or grid line reads for its
    part, and for each load that no rule reads, once for each case that puts it on the
    part. A value nothing reads is a value nothing checks: a plate that no joint joins
    would pass at any thickness, and a joint whose rules read its shear alone would pass
    under any tension. A load is read by an expression of a rule that applies to the part
    it is on, and by nothing else. The cells are listed part by part: the part's fields in the order of
    its type, and then its loads in the order of their names and of their cases' names.

    What is read is worked out under `fixed`, the completions of the cells the waivers rest,
    as the kernel works it out: a design that leaves out what a waiver answers for reads what
    the design that states it reads."""
    keys = [(*k, v) for k, v in (fixed or {}).items() if len(k) == 2]
    loads = [(*k, v) for k, v in (fixed or {}).items() if len(k) == 3]
    if keys or loads:
        found = replace(found, parts=_completed(next(iter(found.parts.values())), found.parts, keys, loads)[1])
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
            **({} if answers is None else {"proofs": export.text({"format": "petra-proofs/0",
                                                                  "cells": [h for c in answers for h in (c.hints if c.hints is not None else (c.body,))]})})}


def verdict(answers: list[Cell]) -> str:
    """The kernel's verdict: FAIL with a refuted cell, UNKNOWN with an open cell or with nothing proved, else PASS. A cell
    whose entry ends in `/where` proves a rule's range and not the rule, so it is not the one proved cell a PASS needs."""
    states = {c.state for c in answers}
    proved = any(c.state == "proved" and not c.entry.endswith("/where") for c in answers)
    return "FAIL" if "refuted" in states else "UNKNOWN" if "open" in states or not proved else "PASS"


PASS_WAIVED = "PASS_WAIVED"
"""What `petra check` says of a design whose verdict is PASS and a cell of which rests on a
waiver: it passes what the deck could check, and the ones who signed the waivers answer for
the rest. The kernel says PASS and lists the waivers."""


@dataclass(frozen=True)
class Report:
    """A design checked against a deck: its cells, and the verdict they give."""

    name: str
    path: str
    deck: Deck
    cells: tuple[Cell, ...]

    @property
    def verdict(self) -> str:
        """The verdict as the kernel gives it, which the two readings are held to."""
        return verdict(list(self.cells))

    @property
    def status(self) -> str:
        """The verdict, with PASS_WAIVED for a PASS that rests a cell on a waiver."""
        return PASS_WAIVED if self.verdict == "PASS" and self.waived() else self.verdict

    def waived(self) -> list[dict[str, str]]:
        """Each waiver that a cell rests on, once, in the order the cells first rest on it, as the kernel lists them."""
        found: dict[tuple[str, str], tuple[str, str]] = {}
        for c in self.cells:
            if c.state == "waived" and c.waiver is not None:
                found.setdefault((c.subject, c.mechanism), c.waiver)
        return [{"subject": s, "mechanism": m, "by": by, "reason": reason} for (s, m), (by, reason) in found.items()]

    def counts(self) -> dict[str, int]:
        return {state: sum(c.state == state for c in self.cells) for state in STATES}

    def completions(self) -> list[dict[str, list] | None]:
        """For each cell, the completion a waived cell rests on, as proofs.json and the kernel's verdict write it, or None. The
        signer of the waiver answers for it, so the report prints it with the cell."""
        return [_completion_body(*c.completion) if c.state == "waived" and c.completion is not None else None for c in self.cells]

    def to_json(self) -> dict[str, Any]:
        return {"file": self.path, "design": self.name, "status": self.status, "deck": {"name": self.deck.name, "hash": self.deck.hash},
                "counts": self.counts(), "waived": self.waived(),
                "cells": [{"subject": c.subject, "mechanism": c.mechanism, "entry": c.entry, "state": c.state, "what": c.what,
                           "anchor": c.anchor, "why": c.why, "rule": c.rule, "ratio": c.ratio, **({"completion": done} if done else {})}
                          for c, done in zip(self.cells, self.completions())]}

    def render(self) -> str:
        return "\n".join(self.lines())

    def lines(self) -> list[str]:
        counts = self.counts()
        out = [f"{self.name}: {self.status}",
               f"rules      {self.deck.hash}  {self.deck.name}",
               "cells      " + ", ".join(f"{counts[s]} {s.replace('_', ' ')}" for s in STATES)]
        wide = max((len(f"{c.subject}/{c.mechanism}") for c in self.cells), default=0)
        for c, done in zip(self.cells, self.completions()):
            ratio = "" if c.ratio is None else f"{c.ratio:.3g}"
            said = (c.why if c.state in ("open", "not_applicable", "waived") else ": ".join(filter(None, (c.what, c.why))) if c.state == "refuted"
                    else c.what if c.entry.endswith("/where") else "")
            if done:
                said += "; rested where " + " and ".join([*(f"{p}.{f} is {name}" for p, f, name in done["keys"]),
                                                          *(f"{p}.{load} is {x} in SI units" + (f" in case {case}" if case else "") for p, load, case, x in done["loads"])])
            out.append(f"  {f'{c.subject}/{c.mechanism}':<{wide}}  {c.state.replace('_', ' '):<14}  {ratio:>6}  "
                       + ": ".join(part for part in (c.entry, said) if part) + (f" ({c.anchor})" if c.anchor else ""))
        waivers = self.waived()
        if waivers:
            out.append(f"waived     {counts['waived']} cells rest on {len(waivers)} waivers"
                       + (", so the design passes what the deck could check and each signer answers for the rest" if self.status == PASS_WAIVED else ""))
            out += [f"  {w['subject']}/{w['mechanism']}  by {w['by']}: {w['reason']}" for w in waivers]
        pending = [c for c in self.cells if c.state == "open"]
        if pending:
            out.append(f"open       {len(pending)} cells: each needs a rule, an input, or `waive MECHANISM on PART by \"<owner>\" reason \"<why>\"` "
                       "in the card, which rests only a cell the deck has no rule for, or one that holds under a completion of what is left out")
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
        return "\n".join([*out[:2], f"card       {self.hashes['card']}  {self.card}", f"design     {self.hashes['design']}  {self.path}",
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
        differ = verify.differs([(c.subject, c.mechanism, c.entry, c.state) for c in report.cells], report.verdict, deck.hash, said, report.waived(),
                               report.completions())
        if differ:
            raise verify.Disagreement(f"{design.path}: petra-verify gives {said['verdict']} and the grid {report.verdict}: {differ}")
        said = {"verdict": said["verdict"], "checked": sum(bool(c.proof) for c in report.cells), "hashes": said["hashes"], "cells_from": said["cells_from"],
                "waived": said["waived"]}
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
