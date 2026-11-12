"""The type rules of docs/format.md, read a second time in Python. Untrusted.

The kernel in kernel/ is the authority on whether a design is well formed. This module
applies the same rules to the same data, so that the two can be compared on every design
and so that `petra check` can refuse a design on a machine that has no kernel binary. A
bug here costs a refusal or a difference from the kernel, which the corpus run reports.
"""
from __future__ import annotations

import re
from fractions import Fraction
from typing import Any, Mapping

DESIGN_KEYS = frozenset({"format", "name", "card", "quantities", "params", "parts"})
BASES = ("m", "kg", "s", "A", "degC")
NAMED = {"dimensionless": (0, 0, 0, 0, 0), "length": (1, 0, 0, 0, 0), "area": (2, 0, 0, 0, 0), "force": (1, 1, -2, 0, 0),
         "stress": (-1, 1, -2, 0, 0), "mass": (0, 1, 0, 0, 0), "time": (0, 0, 1, 0, 0), "temperature": (0, 0, 0, 0, 1),
         "energy": (2, 1, -2, 0, 0), "moment": (2, 1, -2, 0, 0), "current": (0, 0, 0, 1, 0), "voltage": (2, 1, -3, -1, 0),
         "power": (2, 1, -3, 0, 0), "resistance": (2, 1, -3, -2, 0), "I2t": (0, 0, 1, 2, 0), "resistance per length": (1, 1, -3, -2, 0)}
"""Each name a file may give a dimension, as its exponents of metre, kilogram, second,
ampere and degree Celsius: `dimNamed` in kernel/Petra/Quantity.lean."""


def dimension(name: Any) -> tuple[int, ...] | None:
    """The exponents a file's `dim` names, or None when it names no dimension: a name of
    NAMED, or the exponents that are not zero, as in `m^3 s^-1`. Two names are one dimension
    when these are equal, so `m^1`, `length` and `m^1 kg^0` are one."""
    if not isinstance(name, str):
        return None
    if name in NAMED:
        return NAMED[name]
    out = [0] * len(BASES)
    for token in name.split(" "):
        found = re.fullmatch(r"(m|kg|s|A|degC)\^(-?[0-9]+)", token, re.ASCII)
        if not found:
            return None
        out[BASES.index(found[1])] += int(found[2])
    return tuple(out)


def _under(value: str, floor: Mapping[str, Any]) -> bool:
    x, least = Fraction(value), Fraction(floor["min"])      # a floor's `min` is a text in a file, and a fraction when `domains` made the floor
    return x < least or (floor["strict"] and x == least)


def domains(card: Mapping[str, Any], design: Mapping[str, Any], deck: Mapping[str, Any], sign: Any = None) -> list[str]:
    """Each size and each signed bound that lies under the floor of its domain. A floor is
    found by the exponents of its dimension and not by the name a file spells it with, and
    of two floors of one dimension the tighter one holds.

    `sign(part, field, load)` is what a deck of rules says with `may_be` of a field of a
    part, or of a load on it: `zero`, `negative` or None. A number for a field that says
    either is not held to the floor of a size, since its field has a floor of its own. A
    bound for a field or a load that may be negative is not held to a floor of its dimension
    that is at zero or above, and is still held to one under zero."""
    out: list[str] = []
    size, floors = deck["domains"]["size"], deck["domains"]["input"]
    for q in design["quantities"]:
        if q["role"] == "size" and _under(q["lo"], size) and not (sign and sign(q["entity"], q["line"], False)):
            out.append(f"design: {q['entity']}: {q['line']} {q['field']} is {q['lo']} in SI units, and a size is more than {size['min']}")
    for i in card["inputs"]:
        dim = dimension(i["dim"])
        if dim is None:
            out.append(f"card: {i['name']} is a {i['dim']}, which is not a dimension")
            continue
        found = [(Fraction(floor["min"]), bool(floor["strict"]), name) for name, floor in floors.items() if isinstance(floor, Mapping) and dimension(name) == dim]
        if not found:
            continue
        least, strict, name = max(found)
        its = None if sign is None else sign(i["on"], i["field"], True) if "on" in i and "field" in i else sign(*str(i["name"]).rpartition(".")[::2], False)
        if _under(i["lo"], {"min": least, "strict": strict}) and not (its == "negative" and least >= 0):
            out.append(f"card: {i['name']} goes down to {i['lo']} in SI units, and a {name} is {'more than' if strict else 'at least'} {least}")
    return out


def findings(card: Mapping[str, Any], design: Mapping[str, Any], deck: Mapping[str, Any], card_hash: str | None = None, sign: Any = None) -> list[str]:
    """Each type rule the card and the design break, in the order the rules are listed, after
    the one shape rule a text of the two can break. `card_hash` is the hash of the card
    file's bytes, when the caller read a file. `sign` is what a deck of rules says with
    `may_be` of a field or of a load of a part (`domains`)."""
    from .deck import replaced

    out: list[str] = [f"{name}: a text of it holds U+FFFD, the replacement character" for name, body in (("card", card), ("design", design)) if replaced(body)]
    if card_hash is not None and design["card"] != card_hash:
        out.append(f"design: it answers card {design['card']}, and the card given is {card_hash}")
    out += [f"design: a design cannot state {key}" for key in sorted(set(design) - DESIGN_KEYS)]
    out += domains(card, design, deck, sign)
    out += [f"card: the bound {i['name']} names nobody" for i in card["inputs"] if i.get("by") == ""]
    out += [f"card: what it states of {s.get('name')} names nobody" for s in card.get("states", []) if not s.get("by")]
    out += [f"card: the waiver of {w['mechanism']} on {w['subject']} names nobody" for w in card["waivers"] if not w.get("by")]
    return out


def require(design: Any, registry: Any) -> None:
    """Raise ComponentError for a parsed design that breaks a domain rule, or whose card
    leaves a load or the ambient to a param. `petra check` calls this before any physics
    runs. A family's card does leave them to params, and `petra certify-family` takes it."""
    import json

    from . import export
    from .models.base import ComponentError
    from .pipeline import lower_components, signed_inputs

    inputs = list(signed_inputs(design, lower_components(design, registry)))
    deck = json.loads(export.CORE.read_text(encoding="utf-8"))
    card = export.card(design, inputs)
    found = [f"card: {i['name']} reads a param, so nobody signed it; `petra certify-family` takes a family"
             for i in card["inputs"] if "by" not in i]
    found += domains(card, export.design_file(design, ""), deck)
    found += [f"card: the bound {i['name']} names nobody" for i in card["inputs"] if i.get("by") == ""]
    if found:
        raise ComponentError(tuple(f"{design.path}: {line}" for line in found))
