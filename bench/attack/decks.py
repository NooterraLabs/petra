"""Changes to a deck that keep it a deck, and changes that must not change what it says.

A deck is JSON, and docs/deck.md names every key it has and every form a value takes. A change
here is one the pages allow: a value moved to the next one, a bound made strict, a band's end
shifted, a line of the grid dropped, a rule copied, or a value written another way. Of these,
two kinds are relations: a value respelled (a fraction as a decimal, an inch as 25.4 mm, a
whole number with commas) and a list of rules or rows in another order must not change what a
design gets (`relation` below), and the rest are changes of what the deck says.
"""
from __future__ import annotations

import copy
import random
import re
from fractions import Fraction
from typing import Any, Iterator

from . import units
from .gen import nearby

Path = tuple


def leaves(node: Any, path: Path = ()) -> Iterator[tuple[Any, Any, Path]]:
    """(container, key, path) of every string in a deck's JSON that is a value, with its unit or without."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("what", "says", "why", "about", "name", "id", "anchor", "mechanism", "type", "as", "by", "one_of", "dim", "format", "unit"):
                continue
            if isinstance(v, str):
                yield node, k, path + (k,)
            else:
                yield from leaves(v, path + (k,))
    elif isinstance(node, list):
        if len(node) == 3 and node[0] == "q":
            yield node, 1, path + (1,)
            return
        if node and node[0] in ("row", "key", "by", "load", "case"):
            return
        for i, v in enumerate(node):
            if isinstance(v, str):
                yield node, i, path + (i,)
            else:
                yield from leaves(v, path + (i,))


def value_leaves(deck: dict) -> list[tuple[Any, Any, Path]]:
    out = []
    for parent, key, path in leaves(deck):
        text = parent[key]
        if isinstance(parent, list) and parent and parent[0] == "q" and key == 1:
            out.append((parent, key, path))
        elif isinstance(text, str) and re.match(r"[+-]?\d", text) and units.parse_value(text) is not None:
            out.append((parent, key, path))
    return out


def _unit_of(parent, key) -> str:
    if isinstance(parent, list) and parent and parent[0] == "q":
        return parent[2]
    return units.parse_value(parent[key])[1] if units.parse_value(parent[key]) else ""


def spell(rng: random.Random, n: Fraction, unit: str) -> str:
    """A value as a deck writes it, in one of the forms the pages list: decimal, fraction, a whole number and a fraction, thousands with commas."""
    forms = ["frac", "dec", "dec"]
    if n.denominator != 1 and n > 0 and n.numerator > n.denominator:
        forms.append("mixed")
    if n.denominator == 1 and abs(n) >= 1000:
        forms.append("comma")
    f = rng.choice(forms)
    if f == "mixed":
        whole, rest = divmod(n.numerator, n.denominator)
        text = f"{whole} {rest}/{n.denominator}"
    elif f == "comma":
        text = f"{n.numerator:,}"
    elif f == "dec":
        text = units.number_text(n, "dec")
    else:
        text = units.number_text(n, "frac")
    return text + (" " + unit if unit else "")


def _set_value(parent, key, n: Fraction, unit: str, rng: random.Random) -> None:
    if isinstance(parent, list) and parent and parent[0] == "q":
        parent[1], parent[2] = spell(rng, n, ""), unit
    else:
        parent[key] = spell(rng, n, unit)


def _value(parent, key) -> tuple[Fraction, str]:
    if isinstance(parent, list) and parent and parent[0] == "q":
        return units.parse_value(parent[1])[0], parent[2]
    return units.parse_value(parent[key])


# --- the changes. Each takes a deck (changed in place), and returns what it did, or None when it found nothing to do.

def op_nudge(rng, deck):
    items = value_leaves(deck)
    if not items:
        return None
    parent, key, path = rng.choice(items)
    n, unit = _value(parent, key)
    new = nearby(rng, n) if n != 0 else Fraction(rng.choice([0, 1]))
    if rng.random() < 0.3:
        new = n + rng.choice([-1, 1]) * Fraction(1, rng.choice([1, 10, 100, 1000]))
    _set_value(parent, key, new, unit, rng)
    return f"{'.'.join(map(str, path[-3:]))} moved from {n} to {new} {unit}"


def op_respell(rng, deck):
    """A value written another way: the same number, in another form or in another unit of its dimension."""
    items = [i for i in value_leaves(deck)]
    if not items:
        return None
    parent, key, path = rng.choice(items)
    n, unit = _value(parent, key)
    if unit and rng.random() < 0.5:
        try:
            f, d = units.factor(unit)
        except KeyError:
            return None
        options = [u for u in units.spellings(d) if u != unit and "^" not in u]
        if options:
            u2 = rng.choice(options)
            n, unit = n * f / units.factor(u2)[0], u2
    _set_value(parent, key, n, unit, rng)
    return f"{'.'.join(map(str, path[-3:]))} written as {parent[key] if not (isinstance(parent, list) and parent[0] == 'q') else parent[1] + ' ' + parent[2]}"


def op_le_lt(rng, deck):
    cands = [r for r in deck.get("rules", []) if "le" in r or "lt" in r]
    cands += [n for t in deck.get("types", []) for n in t.get("needs", []) if "le" in n or "lt" in n]
    if not cands:
        return None
    r = rng.choice(cands)
    old, new = ("le", "lt") if "le" in r else ("lt", "le")
    r[new] = r.pop(old)
    return f"{r.get('id', 'a need')}: {old} made {new}"


def _conds(node: Any) -> Iterator[list]:
    if isinstance(node, list):
        if node and node[0] in ("le", "lt", "ge", "gt", "and", "or", "not", "min", "max"):
            yield node
        for x in node:
            yield from _conds(x)
    elif isinstance(node, dict):
        for x in node.values():
            yield from _conds(x)


def op_operator(rng, deck):
    swaps = {"le": "lt", "lt": "le", "ge": "gt", "gt": "ge", "and": "or", "or": "and", "min": "max", "max": "min"}
    found = [c for c in _conds({"rows": deck.get("rows", []), "rules": deck.get("rules", [])})]
    if not found:
        return None
    c = rng.choice(found)
    old = c[0]
    c[0] = swaps[old]
    return f"an operator {old} made {c[0]}"


def op_closed(rng, deck):
    sides = []
    for row in deck.get("rows", []):
        t = row.get("table")
        if t:
            for s in ("down", "across"):
                if isinstance(t.get(s), dict) and "bands" in t[s]:
                    sides.append((row["id"], t[s]))
    if not sides:
        return None
    rid, side = rng.choice(sides)
    old = side.get("closed", "upper")
    side["closed"] = "lower" if old == "upper" else "upper"
    return f"{rid}: bands closed at the {side['closed']} end"


def op_band(rng, deck):
    sides = [(row["id"], row["table"][s]) for row in deck.get("rows", []) if row.get("table") for s in ("down", "across") if isinstance(row["table"].get(s), dict) and "bands" in row["table"][s]]
    if not sides:
        return None
    rid, side = rng.choice(sides)
    bands = side["bands"]
    i = rng.randrange(len(bands))
    j = rng.choice([0, 1])
    v = bands[i][j]
    if not isinstance(v, str) or units.parse_value(v) is None:
        return None
    n, unit = units.parse_value(v)
    new = n * rng.choice([Fraction(101, 100), Fraction(99, 100), Fraction(1001, 1000), Fraction(2), Fraction(1, 2)])
    shared = [(a, b) for a in range(len(bands)) for b in (0, 1) if bands[a][b] == v]
    for a, b in shared:                  # a band's end is usually the next band's start: move both, or the bands overlap
        bands[a][b] = spell(rng, new, unit)
    return f"{rid}: a band end {v} moved to {bands[i][j]}"


def op_drop_rule(rng, deck):
    if not deck.get("rules"):
        return None
    r = deck["rules"].pop(rng.randrange(len(deck["rules"])))
    return f"rule {r.get('id')} dropped"


def op_drop_line(rng, deck):
    if not deck.get("grid"):
        return None
    g = deck["grid"].pop(rng.randrange(len(deck["grid"])))
    return f"the line {g.get('mechanism')} dropped from the grid"


def op_dup_rule(rng, deck):
    if not deck.get("rules"):
        return None
    r = copy.deepcopy(rng.choice(deck["rules"]))
    r["id"] = r["id"] + "-copy" if rng.random() < 0.8 else r["id"]
    if "le" in r and rng.random() < 0.5:
        r["lt"] = r.pop("le")
    deck["rules"].append(r)
    return f"rule {r['id']} copied"


def op_swap_sides(rng, deck):
    by: dict[tuple, list[dict]] = {}
    for r in deck.get("rules", []):
        if "le" in r:
            by.setdefault((r.get("type"), r.get("mechanism")), []).append(r)
    groups = [g for g in by.values() if len(g) > 1]
    if not groups:
        return None
    a, b = rng.sample(rng.choice(groups), 2)
    a["le"][1], b["le"][1] = b["le"][1], a["le"][1]
    return f"the right sides of {a['id']} and {b['id']} swapped"


def op_flag(rng, deck):
    fields = [f for t in deck.get("types", []) for f in t.get("fields", [])]
    if not fields:
        return None
    f = rng.choice(fields)
    flag = rng.choice(["optional", "signed", "least", "may_be"])
    if flag == "least":
        if "dim" not in f:
            return None
        f["least"] = rng.choice(["1 mm", "0.5 inch", "2", "1 kip", "1 ksi"])
    elif flag == "may_be":
        if "dim" not in f:
            return None
        f["may_be"] = rng.choice(["zero", "negative"])
    else:
        f[flag] = not f.get(flag, False)
    return f"{f['name']}: {flag} changed"


def op_need(rng, deck):
    types = [t for t in deck.get("types", []) if t.get("needs")]
    if not types:
        return None
    t = rng.choice(types)
    if rng.random() < 0.5 and len(t["needs"]) > 1:
        t["needs"].pop(rng.randrange(len(t["needs"])))
        return f"a need of {t['type']} dropped"
    n = rng.choice(t["needs"])
    if "le" in n:
        n["le"][0] = ["mul", rng.choice(["2", "3", "3/2", "1/2"]), n["le"][0]] if isinstance(n["le"][0], str) else n["le"][0]
    return f"a need of {t['type']} scaled"


def op_when(rng, deck):
    """A key's name in a `when`, an `unless` or a `requires` changed to another name of the key."""
    keys = {}
    for t in deck.get("types", []):
        for f in t.get("fields", []):
            if "one_of" in f:
                keys[f["name"]] = f["one_of"]
    cands = []
    for node in _conds({"g": deck.get("grid", []), "r": deck.get("rules", [])}) if False else []:
        pass

    def walk(n):
        if isinstance(n, list):
            if len(n) == 3 and n[0] == "is" and n[1] in keys:
                cands.append(n)
            for x in n:
                walk(x)
        elif isinstance(n, dict):
            for x in n.values():
                walk(x)
    walk(deck.get("grid", []))
    walk(deck.get("rules", []))
    if not cands:
        return None
    n = rng.choice(cands)
    old = n[2]
    n[2] = rng.choice(keys[n[1]])
    return f"a condition on {n[1]}: {old} made {n[2]}"


def op_expr(rng, deck):
    """A number inside an expression moved, or an operator of the same arity swapped for another."""
    nums = []

    def walk(n, parent=None, idx=None):
        if isinstance(n, str) and parent is not None and re.fullmatch(r"\d+(?:\.\d+|/\d+)?", n) and not (isinstance(parent, list) and parent and parent[0] in ("row", "q", "key", "by", "load", "case")):
            nums.append((parent, idx))
        elif isinstance(n, list):
            for i, x in enumerate(n):
                walk(x, n, i)
        elif isinstance(n, dict):
            for k, x in n.items():
                if k in ("what", "says", "why", "about", "id", "anchor", "name", "dim", "type", "mechanism", "as", "one_of", "unit", "by"):
                    continue
                walk(x, n, k)
    walk(deck.get("rows", []))
    walk(deck.get("rules", []))
    if not nums:
        return None
    parent, idx = rng.choice(nums)
    old = Fraction(parent[idx])
    new = nearby(rng, old) if old != 0 else Fraction(1)
    parent[idx] = units.number_text(new, "frac") if new.denominator != 1 else str(new.numerator)
    return f"a number {old} of an expression moved to {parent[idx]}"


def op_reorder(rng, deck):
    key = rng.choice(["rules", "rows", "grid", "types"])
    if len(deck.get(key, [])) < 2:
        return None
    rng.shuffle(deck[key])
    return f"{key} in another order"


# (weight, operator, kind): kind "relation" means the deck still says the same.
OPS = [(6, op_nudge, "change"), (4, op_respell, "relation"), (2, op_le_lt, "change"), (3, op_operator, "change"), (2, op_closed, "change"), (3, op_band, "change"),
       (1, op_drop_rule, "change"), (1, op_drop_line, "change"), (1, op_dup_rule, "change"), (1, op_swap_sides, "change"), (1, op_flag, "change"),
       (1, op_need, "change"), (2, op_when, "change"), (4, op_expr, "change"), (2, op_reorder, "relation")]


def mutate(rng: random.Random, deck: dict, ops: int | None = None) -> tuple[dict, list[str], str]:
    """A changed copy of the deck, what was done, and "relation" when every change leaves what the deck says as it was."""
    d = copy.deepcopy(deck)
    notes: list[str] = []
    kind = "relation"
    for _ in range(ops or rng.choice([1, 1, 1, 2, 3])):
        _, fn, k = rng.choices(OPS, [w for w, _, _ in OPS])[0]
        note = fn(rng, d)
        if note:
            notes.append(note)
            if k == "change":
                kind = "change"
    return d, notes, kind if notes else "change"
