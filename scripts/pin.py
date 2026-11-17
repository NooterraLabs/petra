"""Name the deck of rules in each card of the folders given, by the hash of the deck as it is.

    python scripts/pin.py examples corpus/cases          write the line into each card that needs it
    python scripts/pin.py --check examples corpus/cases  exit 1 when a card names another hash, or none

A card names the deck its owner has the design checked against: `rules "NAME" "HASH"` in
its card block (docs/reference.md). The hash is of the deck's file, so every edit of a deck
leaves the cards of this repository naming the deck before it, and `petra check` refuses
them. This script names the new one. It is for the cards kept here as examples and cases,
whose owner is this repository. A card that somebody issued is theirs to change: its owner
looks at what changed in the deck and names it again, or does not.

A card that the script cannot write the line into, for the way its card block is laid out,
is printed with the line to write by hand, and the script exits 1 in both forms.

A card gets the line when a design of its folder with the same stem, or any design of the
folder when none has its stem, has a part of a deck's type. A card with the words
`pin kept as written` in a comment is left as it is: the cases that name no deck, or
another, say so that way.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from petra import grid

KEPT = "pin kept as written"
PART = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)[ \t]+[A-Za-z_][A-Za-z0-9_]*[ \t]*\{", re.MULTILINE)


def deck_of(card: Path) -> grid.Deck | None:
    """The deck that has a kind of part of the card's design, or None."""
    kinds = grid.kinds()
    beside = [card.with_suffix(".petra")] if card.with_suffix(".petra").is_file() else sorted(card.parent.glob("*.petra"))
    for design in beside:
        for kind in PART.findall(design.read_text(encoding="utf-8")):
            if kind in kinds:
                return kinds[kind]
    return None


def pinned(text: str, deck: grid.Deck) -> str | None:
    """The card's text with the deck named in its card block (grid.pinned), or None for a text with no card block."""
    try:
        return grid.pinned(text, deck)
    except ValueError:
        return None


def main(argv: list[str]) -> int:
    check = argv[:1] == ["--check"]
    roots = argv[1:] if check else argv
    if not roots:
        print("usage: python scripts/pin.py [--check] FOLDER...", file=sys.stderr)
        return 64
    stale = changed = 0
    for root in roots:
        for card in sorted(Path(root).rglob("*.card")):
            text = card.read_text(encoding="utf-8")
            deck = deck_of(card)
            if deck is None or KEPT in text:
                continue
            new = pinned(text, deck)
            if new == text:
                continue
            if new is None:      # a card this script cannot write the line into is stale all the same, and is said to be
                stale += 1
                print(f"{card}: does not name {deck.name} {deck.hash}, and is laid out so that this script cannot write the line: write `{grid.rules_line(deck)}` into its card block")
            elif check:
                stale += 1
                print(f"{card}: does not name {deck.name} {deck.hash}")
            else:
                card.write_text(new, encoding="utf-8", newline="\n")
                changed += 1
    if not check:
        print(f"{changed} cards named the deck again")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
