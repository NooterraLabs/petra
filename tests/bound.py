"""What a test needs of the binding by hash (docs/format.md, type rules 9 to 11): a made-up
deck with a run that names its hash, and a card that names the deck.

A deck made up for a test went through no gate, and the run made here says so in its
`gate`. The readers hold a run to the deck's hash and to a gate named in words, and read
nothing else of it, so such a run binds a made-up deck as a real one binds the deck that
ships. That the run of the shipped deck is a real one is tests/test_deck_rules.py's to hold.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Callable

from petra import export, grid

GATE = "none: a deck made up for a test"
OWNER = "t@example.org"
SOURCE = "test"


def run_of(deck: str, gate: str = GATE) -> str:
    """The file of a run that names the hash of the deck whose text is `deck`."""
    return export.text({"format": grid.RUN, "deck": export.sha256(deck), "gate": gate})


def read(deck: str) -> grid.Deck:
    """The deck of the text, bound to a run made up for it: one a design may be checked against."""
    return grid.read_deck(deck, run_of(deck))


def card(text: str, deck: grid.Deck) -> str:
    """The card's text with the deck named in its card block."""
    return grid.pinned(text, deck)


def card_of(text: str, deck: grid.Deck) -> str:
    """The card's text with the deck named in its card block, or the text as it is when it has no
    card block: a test of a card that a reader refuses for that keeps its fault."""
    try:
        return grid.pinned(text, deck)
    except ValueError:
        return text


def card_for(card: str, design: str, path: str = "made-up.petra") -> str:
    """The card's text with the deck named that has the types of the design's parts, among the
    decks `grid.decks` gives (the shipped ones, or the one a test patches in), as `petra kinds`
    tells a card's owner to name it. A pair that does not read, or whose parts are of no deck's
    type, comes back as it is, so a test of a refusal keeps its fault."""
    import petra.lang

    try:
        deck = grid.owner(petra.lang.parse_design(card, design, path))
    except Exception:      # noqa: BLE001: whatever refuses the pair refuses it again where the test reads it
        return card
    return card if deck is None else card_of(card, deck)


def pin(rules: str) -> dict[str, Any]:
    """What card.json and deck.json hold under `rules` for the deck of rules whose text is
    `rules`: its name, as the deck says it, and the hash of its file. The name of a text that
    is no deck is the empty text."""
    try:
        body = json.loads(rules)
        name = body.get("name", "") if isinstance(body, dict) else ""
    except ValueError:
        name = ""
    return {"name": name, "hash": export.sha256(rules)}


def card_json(card: dict, rules: str | None = None) -> dict:
    """A copy of a card.json, as a dict, brought to the format of a card of a deck's design: an
    `owner`, `rules` naming the deck whose text is `rules` when one is given, and a `source` and
    a `kind` on each input and each statement of `states`. A key the card already has is left
    as it is, so a test that writes one of them wrong keeps it."""
    out = copy.deepcopy(card)
    if not isinstance(out, dict):
        return out
    out.setdefault("owner", OWNER)
    if rules is not None:
        out.setdefault("rules", pin(rules))
    for key in ("inputs", "states"):
        items = out.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    item.setdefault("source", SOURCE)
                    item.setdefault("kind", "signed")
    return out


def sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def rebound(files: dict[str, str], dump: Callable[[Any], str] = export.text) -> dict[str, str]:
    """The files of a bundle with what binds them worked out again from the deck of rules and
    the card as they are: the card and deck.json name the deck of rules, the run names its
    hash, and design.json names the card's. For a test that changed the rules or the card of an
    honest bundle and wants the rest to answer them, as the card's owner and an honest exporter
    would write them. Without `rules` only the design's hash of the card is worked out again."""
    out = dict(files)
    if "rules" in out:
        held = pin(out["rules"])
        card = json.loads(out["card"])
        card["rules"] = held
        out["card"] = dump(card)
        deck = json.loads(out["deck"])
        deck["rules"] = held
        out["deck"] = dump(deck)
        out["run"] = run_of(out["rules"])
    design = json.loads(out["design"])
    design["card"] = sha(out["card"])
    out["design"] = dump(design)
    return out


def with_rules(files: dict[str, str], rules: str) -> dict[str, str]:
    """The files of a bundle with its deck of rules replaced by the text `rules`, and the rest
    bound to it (`rebound`): what a test of what the kernel makes of another deck hands it."""
    return rebound({**files, "rules": rules})
