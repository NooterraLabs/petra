"""What a deck says about the designs it takes, read from the deck's JSON and from nothing else.

The generator writes a part for each type of a deck, a line for each field, a card for each
signed field and a load for each load. It reads the types out of the deck as docs/deck.md
describes them, so it needs no knowledge of one deck, and a deck that was changed gets
designs of its own types.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterator

from . import units
from .units import Dim

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class F:
    name: str
    kind: str                      # "quantity", "key" or "joins"
    dim: Dim | None = None
    one_of: list[str] = field(default_factory=list)
    whole: bool = False
    signed: bool = False
    optional: bool = False
    may_be: str | None = None
    least: Fraction | None = None
    type: str | None = None
    names: list[str] = field(default_factory=list)


@dataclass
class T:
    name: str
    fields: list[F]
    loads: list[F]
    needs: list[dict]
    mechanisms: list[str]


@dataclass
class Info:
    deck: dict
    types: dict[str, T]
    pool: dict[Dim, list[Fraction]]
    used: dict[Dim, list[str]]     # the units the deck writes a dimension in, most used first
    unruled: dict[str, list[str]] = field(default_factory=dict)      # the lines of the grid that no rule answers, by type

    def roots(self) -> list[str]:
        """The types no other type joins: a design starts from one of them."""
        joined = {f.type for t in self.types.values() for f in t.fields if f.type}
        return [n for n in self.types if n not in joined] or list(self.types)


def _field(body: dict) -> F:
    least = units.si(body["least"]) if isinstance(body.get("least"), str) else None
    if "one_of" in body:
        # A key is the card's to state unless the deck says `chosen`, with why: the design writes only a chosen key.
        return F(body["name"], "key", None, list(body["one_of"]), signed="chosen" not in body, optional=bool(body.get("optional")))
    if "type" in body:
        return F(body["name"], "joins", type=body["type"], names=list(body.get("as", [])))
    return F(body["name"], "quantity", units.dim_of(body.get("dim", "")), whole=bool(body.get("whole")), signed=bool(body.get("signed")),
             optional=bool(body.get("optional")), may_be=body.get("may_be"), least=least)


def values(node: Any) -> Iterator[tuple[Fraction, str]]:
    """Every number with a unit, and every plain number, that a deck's JSON writes as a value."""
    if isinstance(node, str):
        p = units.parse_value(node)
        if p is not None:
            try:
                units.factor(p[1])
                yield p
            except KeyError:
                pass
    elif isinstance(node, list):
        if len(node) == 3 and node[0] == "q" and all(isinstance(x, str) for x in node):
            p = units.parse_value(f"{node[1]} {node[2]}".strip())
            if p is not None:
                try:
                    units.factor(p[1])
                    yield p
                except KeyError:
                    pass
            return
        for x in node:
            yield from values(x)
    elif isinstance(node, dict):
        for k, x in node.items():
            if k in ("what", "says", "why", "chosen", "about", "name", "id", "anchor", "mechanism"):
                continue
            yield from values(x)


def read(deck: dict) -> Info:
    types: dict[str, T] = {}
    mechs: dict[str, list[str]] = {}
    for line in deck.get("grid", []):
        mechs.setdefault(line.get("type", ""), []).append(line.get("mechanism", ""))
    for t in deck.get("types", []):
        types[t["type"]] = T(t["type"], [_field(f) for f in t.get("fields", [])], [_field(f) for f in t.get("loads", [])],
                             list(t.get("needs", [])), mechs.get(t["type"], []))
    pool: dict[Dim, list[Fraction]] = {}
    used: dict[Dim, dict[str, int]] = {}
    for n, u in values({k: deck[k] for k in ("rows", "types", "rules") if k in deck}):
        d = units.factor(u)[1]
        x = n * units.factor(u)[0]
        if x != 0 and x not in pool.setdefault(d, []):
            pool[d].append(x)
        if u:
            used.setdefault(d, {}).setdefault(u, 0)
            used[d][u] += 1
    ruled = {(r.get("type"), r.get("mechanism")) for r in deck.get("rules", [])}
    unruled = {n: [m for m in t.mechanisms if (n, m) not in ruled] for n, t in types.items()}
    return Info(deck, types, pool, {d: sorted(c, key=lambda u: -c[u]) for d, c in used.items()}, unruled)


def load_deck(name: str) -> dict:
    """A shipped deck by name, `aisc360`."""
    return json.loads((ROOT / "petra" / "decks" / f"{name}.json").read_text(encoding="utf-8"))


def seeds() -> dict[str, dict]:
    """The decks to start from: the one that ships, and the decks the repository's own benches made up to reach every operator.

    Each is a dict of a deck's JSON. A made-up deck is left out when its module does not import here."""
    found = {"aisc360": load_deck("aisc360")}
    try:
        from bench import kernel_grid
        found["ops"] = json.loads(json.dumps(kernel_grid.OPS))
        found["kit"] = json.loads(json.dumps(kernel_grid.KIT))
    except Exception:       # noqa: BLE001 a bench that does not import is a seed less, never a stop
        pass
    try:
        from tests.test_grid import STRIPS
        found["strips"] = json.loads(json.dumps(STRIPS))
    except Exception:       # noqa: BLE001
        pass
    return found
