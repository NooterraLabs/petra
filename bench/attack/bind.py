"""The binding by hash (docs/format.md, type rules 5 and 9 to 11, "run.json" and "Reading a
verdict"; docs/deck.md, "The run a deck is bound to").

A card names the deck of rules it is checked against, by the deck's name and the hash of its
file, deck.json names the same deck, and a deck is read only with the record of its acceptance
run, whose `deck` is that hash and whose `gate` has a letter in it. The card also names its
owner, and each input and statement of it a `source` and a `kind`.

Two things here. What an honest owner and an honest exporter write: the deck a card names
(`pin`) and the run a deck is read with (`run_for`), the shipped record for the deck that ships
and a record made up here for any other deck, whose `gate` says that no gate ran. The readers
read nothing of a run but its format, its `deck` and its `gate`, so a made-up record binds a
made-up deck as the shipped record binds the shipped deck, and the cases the attacker makes
still reach the cells. And what the attacker holds of the binding on every input it judges:
no verdict is PASS for files whose card names another deck than the file `--rules` names, and
the `bundle` and the `hashes` the kernel prints are those of the files it was handed.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DECKS = ROOT / "petra" / "decks"
RUN = "petra-run/0"
GATE = "none: a deck the attacker made up"
"""The gate of a run made up here: no gate ran on such a deck, and the record says so in words."""

AUTO = "auto"
"""The run of a draft that is the honest one for its deck (`run_for`). None is a draft with no run."""

FILES = ("card", "design", "deck", "rules", "run", "proofs")
"""The six files of a verdict, in the order of its `hashes` and of the lines its `bundle` hashes."""


def sha(text: str | bytes) -> str:
    """`sha256:HEX` of the bytes of a file, as the kernel hashes it: of the bytes as they are."""
    data = text if isinstance(text, bytes) else text.encode("utf-8", "surrogatepass")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def deck_hash(text: str) -> str:
    """The hash of a deck's file as Petra works it out (petra/export.py, `sha256`)."""
    from petra import export
    return export.sha256(text)


def name_of(text: str) -> str:
    """The name a deck's file gives itself, or the empty text for one that is no deck or names none in a text."""
    try:
        body = json.loads(text)
    except ValueError:
        return ""
    name = body.get("name") if isinstance(body, dict) else None
    return name if isinstance(name, str) else ""


def pin(text: str) -> tuple[str, str]:
    """What an honest owner names in the card for the deck whose file is `text`: its name and its hash."""
    return name_of(text), deck_hash(text)


def text(body: Any) -> str:
    """A file as Petra writes one (petra/export.py)."""
    from petra import export
    return export.text(body)


def made_up_run(deck: str, gate: Any = GATE) -> str:
    """A record of a run for the deck whose file is `deck`, with no line checked: what the readers read of a run is its
    format, its `deck` and its `gate`, so this binds a deck made up here as the shipped record binds the shipped deck."""
    return text({"format": RUN, "deck": deck_hash(deck), "gate": gate})


@lru_cache(maxsize=None)
def _shipped() -> dict[str, str]:
    out = {}
    for path in sorted(DECKS.glob("*.run.json")):
        deck = path.with_name(path.name[:-len(".run.json")] + ".json")
        if deck.is_file():
            out[deck.read_text(encoding="utf-8")] = path.read_text(encoding="utf-8")
    return out


def shipped_run(text: str) -> str | None:
    """The record beside a deck of petra/decks whose file is `text`, or None for a text that is no shipped deck."""
    return _shipped().get(text)


def run_for(text: str) -> str:
    """The run an honest exporter hands with the deck: the shipped record of a shipped deck, and one made up for any other."""
    return shipped_run(text) or made_up_run(text)


def resolve(text: str, run: str | None) -> str | None:
    return run_for(text) if run == AUTO else run


# --- what is held of every verdict

def bundle(files: dict[str, str | bytes]) -> tuple[dict[str, str | None], str]:
    """The `hashes` and the `bundle` a verdict of these files must print (format.md, "Reading a verdict")."""
    hashes = {name: (sha(files[name]) if name in files else None) for name in FILES}
    lines = "".join(f"{name} {hashes[name] or 'none'}\n" for name in FILES)
    return hashes, sha(lines)


def card_names(card: str | bytes) -> tuple[Any, Any] | None:
    """The deck card.json names under `rules`, as (name, hash), or None when it names none that reads."""
    try:
        body = json.loads(card)
        held = body.get("rules") if isinstance(body, dict) else None
        return (held.get("name"), held.get("hash")) if isinstance(held, dict) else None
    except ValueError:
        return None


def held_of(files: dict[str, str], kernel: dict | None) -> list:
    """What the binding asks of the kernel's word on files: the hashes and the bundle are of the files it
    was handed, and a PASS is of files whose card names the deck of rules that was read, by its name and
    the hash of its bytes."""
    from .readers import Diff
    if not kernel or "verdict" not in kernel:
        return []
    out = []
    hashes, whole = bundle(files)
    said = kernel.get("hashes") or {}
    wrong = [n for n in FILES if said.get(n, "absent") != hashes[n]]
    if wrong:
        out.append(Diff("bundle", "kernel", f"the kernel prints hashes of {wrong} that are not of the files it was handed", key=f"hashes|{wrong}"))
    elif kernel.get("bundle") != whole:
        out.append(Diff("bundle", "kernel", f"the kernel prints the bundle {kernel.get('bundle')} and the six lines of its hashes hash to {whole}", key="bundle"))
    if kernel["verdict"] == "PASS":
        rules = files.get("rules")
        named = card_names(files.get("card", ""))
        read = (name_of(rules) if isinstance(rules, str) else None, sha(rules) if rules is not None else None)
        if named is None or tuple(named) != read:
            out.append(Diff("bind", "kernel", f"PASS for a card that names the deck {named} and the rules {read}", key="pass-other-deck"))
    return out


def held_by_grid(parsed: Any, deck: Any, verdict: str) -> list:
    """A PASS of the Python reader is of a card that names the deck it read."""
    from .readers import Diff
    if verdict == "PASS" and (parsed.rules != (deck.name, deck.hash) or not deck.run):
        return [Diff("bind", "grid", f"PASS for a card that names {parsed.rules} against the deck {deck.name} {deck.hash}" + ("" if deck.run else " read with no run"), key="grid-pass-other-deck")]
    return []


# --- what a recipe of the binding expects

def expected(extra: dict, j: Any) -> list:
    """What a draft of the binding recipe expects (Draft.extra["bind"]): `refuse` is a refusal by the kernel with a
    finding of one of `rules` (each `RULE` or `FILE:RULE`), and by the Python reader whenever it was asked; `read`
    is no finding of the binding at all. The comparison of the kernel and the grid is the runner's as for any input."""
    from .readers import Diff
    want = extra.get("bind")
    if not want:
        return []
    what = want.get("what", "")
    kernel = j.verdict.get("kernel")
    if kernel is None:
        return []           # no reader was asked, or the language refused the text, which is the grid's refusal
    found = [(f.get("file"), f.get("rule")) for f in j.findings]
    if want.get("expect") == "refuse":
        out = []
        if kernel != "ILL-FORMED":
            out.append(Diff("bind", "kernel", f"{what}: the kernel gives {kernel}, and type rule {want.get('rules')} refuses it", key=f"bind|{what}|{kernel}"))
        elif want.get("rules") and not any(r in want["rules"] or f"{f}:{r}" in want["rules"] for f, r in found):
            out.append(Diff("bind", "kernel", f"{what}: the kernel refuses it with {sorted(set(found))[:4]} and not {want['rules']}", key=f"bind|{what}|rules|{sorted({r for _, r in found})[:3]}"))
        if j.verdict.get("grid") not in (None, "REFUSED"):
            out.append(Diff("bind", "grid", f"{what}: the grid gives {j.verdict['grid']}, and the binding refuses it", key=f"bind|{what}|grid|{j.verdict['grid']}"))
        return out
    if want.get("expect") == "read":
        bad = [(f, r) for f, r in found if r in ("types.9", "types.10", "types.11") or f == "run" or (f == "card" and r == "types.5")]
        if bad:
            return [Diff("bind", "kernel", f"{what}: an honest binding written another way, and the kernel refuses it with {bad[:3]}", key=f"bind|{what}|read|{sorted({r for _, r in bad})}")]
    return []
