"""The type rules of docs/format.md, read a second time in Python. Untrusted.

The kernel in kernel/ is the authority on whether a design is well formed. This module
applies the same rules to the same data, so that the two can be compared on every design
and so that `petra check` can refuse a design on a machine that has no kernel binary. A
bug here costs a refusal or a difference from the kernel, which the corpus run reports.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Any, Mapping

DESIGN_KEYS = frozenset({"format", "name", "card", "quantities", "params"})


def _under(value: str, floor: Mapping[str, Any]) -> bool:
    x, least = Fraction(value), Fraction(floor["min"])
    return x < least or (floor["strict"] and x == least)


def domains(card: Mapping[str, Any], design: Mapping[str, Any], deck: Mapping[str, Any]) -> list[str]:
    """Each size and each signed bound that lies under the floor of its domain."""
    out: list[str] = []
    size, floors = deck["domains"]["size"], deck["domains"]["input"]
    for q in design["quantities"]:
        if q["role"] == "size" and _under(q["lo"], size):
            out.append(f"design: {q['entity']}: {q['line']} {q['field']} is {q['lo']} in SI units, and a size is more than {size['min']}")
    for i in card["inputs"]:
        floor = floors.get(i["dim"])
        if isinstance(floor, Mapping) and _under(i["lo"], floor):
            out.append(f"card: {i['name']} goes down to {i['lo']} in SI units, and a {i['dim']} is "
                       f"{'more than' if floor['strict'] else 'at least'} {floor['min']}")
    return out


def findings(card: Mapping[str, Any], design: Mapping[str, Any], deck: Mapping[str, Any], card_hash: str | None = None) -> list[str]:
    """Each type rule the card and the design break, in the order the rules are listed.
    `card_hash` is the hash of the card file's bytes, when the caller read a file."""
    out: list[str] = []
    if card_hash is not None and design["card"] != card_hash:
        out.append(f"design: it answers card {design['card']}, and the card given is {card_hash}")
    out += [f"design: a design cannot state {key}" for key in sorted(set(design) - DESIGN_KEYS)]
    out += domains(card, design, deck)
    out += [f"card: the waiver of {w['mechanism']} on {w['subject']} names nobody" for w in card["waivers"] if not w.get("by")]
    return out


def require(design: Any, registry: Any) -> None:
    """Raise ComponentError for a parsed design that breaks a domain rule. `petra check`
    calls this before any physics runs. The rules on waivers and loads wait until a card
    is a file of its own, since a .petra file still holds both."""
    import json

    from . import export
    from .models.base import ComponentError
    from .pipeline import lower_components, signed_inputs

    inputs = list(signed_inputs(design, lower_components(design, registry)))
    deck = json.loads(export.CORE.read_text(encoding="utf-8"))
    found = domains(export.card(design, inputs), export.design_file(design, ""), deck)
    if found:
        raise ComponentError(tuple(f"{design.path}: {line}" for line in found))
