"""A card and a design as the kernel reads them:
`python -m petra.export FILE.petra [--card FILE.card] --out DIR`.

Writes the files of docs/format.md into DIR:

    card.json     what the asker owns: the owner, the deck of rules it names, the load cases,
                  every bound with its signer, source and kind, the claims, the waivers
    design.json   what the designer owns: the parts as written, and every quantity in them
    deck.json     the domains of petra/decks/core.json, and the name and hash of the rules
    rules.json    the deck of rules whose types the parts are, as it ships
    run.json      the record of the acceptance run that deck is bound to, as it ships
    proofs.json   the hints the Python reader found for the cells the kernel works out

With --no-physics the design is written as it stands, with no proofs.json and without
asking the grid whether the deck's types take it: the kernel reads the parts itself and
says. A design none of whose parts is of a deck's type has no files: there is no deck of
rules to write, and no type that says what its lines are. The command then writes nothing,
says so, and exits 2, the code of the UNKNOWN that `petra check` gives such a design.

`python -m petra.export --card-only FILE.card --out DIR` writes card.json from the card
with no design, and prints its hash. card.json holds nothing the design chooses, so this
is how an asker works out the hash of their own card.

Untrusted. It reads the two files through the language, so a bug here gives the kernel the
wrong files, and the kernel's verdict is about the files it was given. A load or an
ambient that reads a param is an input nobody signed, and goes into card.json with no `by`,
which the kernel refuses. Exits 3 when the language or a deck's types refuse the pair, as
`petra check` does, for a file it cannot write and for a usage error, and then leaves no file
of this run behind.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterator

from .ir import Bound, Component, Design, Fixed, Input, InputKind, ParamRef, Ref, Stated, Text, Vec
from .kernel import Interval
from .units import Quantity, dimension_name

CORE = Path(__file__).resolve().parent / "decks" / "core.json"


def number(x: Fraction) -> str:
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


def _range(value: Interval) -> dict[str, str]:
    return {"lo": number(value.lo), "hi": number(value.hi)}


def _quantity(q: Quantity) -> dict[str, str]:
    return {"dim": dimension_name(q.dim), **_range(q.value)}


def written(component: Component) -> Iterator[dict[str, Any]]:
    """Every quantity a component block states, with its kind, component, line and field.
    The field is the word before the number, or the line's key when no word comes between.
    A number alone is a size, and a number in a tuple is a position."""
    for attr in component.attrs:
        field = attr.key
        for arg in attr.args:
            where = {"type": component.kind, "entity": component.name, "line": attr.key, "field": field}
            if isinstance(arg, Ref):
                field = arg.parts[-1]
            elif isinstance(arg, Fixed):
                yield {**where, "role": "size", **_quantity(arg.quantity)}
            elif isinstance(arg, Vec):
                for item in arg.items:
                    yield {**where, "role": "position", **_quantity(item)}


def parts(design: Design) -> list[dict[str, Any]]:
    """Every component block as written, for a design checked against a deck of rules: its
    name, its type and its lines in order. An argument is a number in SI, the name of a
    given, a word or a quoted text. This knows no deck: the kernel reads what each line
    means from the field of the deck that it names. An argument of any other kind is
    written as `other`, which no field takes."""
    def arg(a: Any) -> dict[str, Any]:
        if isinstance(a, Fixed):
            return {"number": _quantity(a.quantity)}
        if isinstance(a, (Bound, Stated)):
            return {"given": a.name}
        if isinstance(a, Ref) and len(a.parts) == 1:
            return {"word": a.parts[0]}
        return {"text": a.value} if isinstance(a, Text) else {"other": type(a).__name__}

    return [{"name": c.name, "type": c.kind, "lines": [{"field": attr.key, "args": [arg(a) for a in attr.args]} for attr in c.attrs]}
            for c in design.components.values()]


def read_inputs(design: Design) -> list[Input]:
    """Every signed bound of the card of a design of a deck's types, by name: each given
    under the name the card gives it, each load, and the ambient. It reads them from what
    the card states and from no component, so card.json is the same for every design that
    answers the card. This knows no deck."""
    given = [Input(a.name, a.range, a.signature, a.kind, a.span, a.mean) for a in design.givens.values()]
    loads = [e.value for case in design.loads.values() for e in case.entries if isinstance(e.value, Input)]
    # card.json has no place for a mean, and a card that states one is not written as the card without it: every way to
    # these files refuses it, as `petra check` does.
    stated = [i.name for i in given + loads if i.mean is not None]
    if stated:
        from .files import ComponentError
        raise ComponentError(tuple(f"{design.path}: {name} states a mean, which a deck does not read yet" for name in stated))
    return sorted(given + loads + ([design.ambient] if isinstance(design.ambient, Input) else []), key=lambda i: i.name)


def card(design: Design, inputs: list[Input], placed: bool = False) -> dict[str, Any]:
    """What the card states. `inputs` is every signed bound of the card (`read_inputs`), each
    under its name there. A load or an ambient that reads a param is an input with no `by`.
    With `placed`, as every caller here asks, a load also says the part it is `on` and which
    `field` it is, and the card names its tests records and its probability claims: the
    kernel takes a load on a part only with the deck that has the part's type. A card that states a key or a whole number exactly, with
    `given NAME is ...`, has them in `states`, in the order of their names: each with its
    `name`, who signed it as `by`, and `key`, the name, or `whole`, the number as a text.
    A card that states none has no `states`, so its card.json is what it was before a card
    could state one."""
    cases = {id(e.value): {"case": load.name, **({"on": ".".join(e.target), "field": e.field} if placed else {})}
             for load in design.loads.values() for e in load.entries}
    claims = [{"name": c.name, "subject": ".".join(c.qoi.path), "quantity": c.qoi.name, "rel": c.rel.value,
               "cases": list(c.under), "bound": _quantity(c.bound)} for c in design.claims]
    unsigned = [(f"{load.name}.{'.'.join(e.target)}.{e.field}", cases[id(e.value)], e.value)
                for load in design.loads.values() for e in load.entries if isinstance(e.value, ParamRef)]
    if isinstance(design.ambient, ParamRef):
        unsigned.append(("ambient", {}, design.ambient))
    def signed(item: Any) -> dict[str, str]:
        # Who answers for the value, where it is from and how it was had: all three are the card's, under its hash.
        return {"by": item.signature.owner, **({"source": item.signature.source, "kind": "measured" if item.kind is InputKind.MEASURED else "signed"} if placed else {})}

    return {"format": "petra-card/0", "name": design.name, "environment": design.environment, "cases": sorted(design.loads),
            **({"owner": design.owner} if placed else {}),
            **({"rules": {"name": design.rules[0], "hash": design.rules[1]}} if placed and design.rules is not None else {}),
            "inputs": [{"name": i.name, **cases.get(id(i), {}), **signed(i), **_quantity(i.range)} for i in inputs]
                      + [{"name": name, **case, **_quantity(design.params[ref.name].range)} for name, case, ref in unsigned],
            "claims": claims,
            **({"tests": sorted(design.tests), "probability_claims": [c.name for c in design.probability_claims]} if placed else {}),
            **({"states": [{"name": s.name, **signed(s), **({"key": s.key} if s.whole is None else {"whole": str(s.whole)})}
                           for _, s in sorted(design.states.items())]} if placed and design.states else {}),
            "waivers": [{"subject": ".".join(w.subject), "mechanism": w.mode, "by": w.owner, "reason": w.reason} for w in design.waivers]}


def design_file(design: Design, card_hash: str, deck: bool = False) -> dict[str, Any]:
    """What the designer wrote: every number in a component block, and the params. For a
    design checked against a deck of rules, also the parts as written."""
    return {"format": "petra-design/0", "name": design.name, "card": card_hash,
            "quantities": [q for c in design.components.values() for q in written(c)],
            "params": [{"name": p.name, **_quantity(p.range)} for p in design.params.values()],
            **({"parts": parts(design)} if deck else {})}


def text(body: dict[str, Any]) -> str:
    return json.dumps(body, indent=1, sort_keys=True) + "\n"


def sha256(data: str) -> str:
    """The hash of a text as UTF-8 with LF line ends, so a file's hash does not change
    with the line ends a checkout gave it."""
    return "sha256:" + hashlib.sha256(data.replace("\r\n", "\n").encode("utf-8")).hexdigest()


class NoDeck(ValueError):
    """No shipped deck of rules has the design's kinds of part, so there are no files to write."""


def export(path: str, out: Path, physics: bool = True, card_path: str | None = None) -> None:
    """Write card.json, design.json, deck.json, rules.json and run.json of the design at
    `path` into `out`, and proofs.json when `physics`. Raises NoDeck for a design none of whose parts is
    of a deck's type, and writes nothing."""
    from . import grid, verify
    from .lang import load_design

    design = load_design(path, card_path)
    rules = grid.owner(design)
    if rules is None:
        raise NoDeck(verify.no_deck(c.kind for c in design.components.values()))
    # Without physics the files are the design as written, and the kernel says whether the deck's types take it.
    files = grid.check(design, rules)[1] if physics else grid.bundle(design, rules)
    out.mkdir(parents=True, exist_ok=True)
    wrote: list[Path] = []
    try:
        for name, body in files.items():
            (out / f"{name}.json").write_text(body, encoding="utf-8", newline="\n")
            wrote.append(out / f"{name}.json")
    except OSError:      # a file that cannot be written: take back the ones that were, so a refusal leaves no half of a bundle
        for path in wrote:
            path.unlink(missing_ok=True)
        raise


def card_only(card_path: str, out: Path) -> str:
    """Write card.json from a card with no design, and give its hash: the hash the kernel
    prints for the card of any design of a deck's types that answers this card. Such a
    card.json holds nothing a design chooses: each given under the card's own name for it,
    and each load with the part and the field the card puts it on."""
    from .lang import load_card

    design = load_card(card_path)
    body = text(card(design, read_inputs(design), placed=True))
    out.mkdir(parents=True, exist_ok=True)
    (out / "card.json").write_text(body, encoding="utf-8", newline="\n")
    return sha256(body)


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error, which this command keeps for a design no deck has."""

    def error(self, message: str):
        self.print_usage(sys.stderr)
        self.exit(3, f"{self.prog}: error: {message}\n")


def main(argv: list[str] | None = None) -> int:
    """The command, printing through petra.files.guarded as every command of Petra does."""
    from .files import guarded

    return guarded(_main, sys.argv[1:] if argv is None else list(argv), "petra.export")


def _main(argv: list[str]) -> int:
    parser = _Parser(prog="python -m petra.export", description=__doc__.split("\n")[0])
    parser.add_argument("file", nargs="?", help="the design, a .petra file")
    parser.add_argument("--card", metavar="FILE", help="the card the design answers; default the .card file beside the design")
    parser.add_argument("--card-only", metavar="FILE", help="a card with no design: write its card.json alone and print its hash")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--no-physics", action="store_true", help="write no proofs.json")
    args = parser.parse_args(argv)
    if (args.file is None) == (args.card_only is None) or (args.card_only and (args.card or args.no_physics)):
        parser.error("give a design, or --card-only FILE with no design, no --card and no --no-physics")
    from . import grid
    from .pipeline import INPUT_ERRORS

    try:
        if args.card_only:
            print(card_only(args.card_only, args.out))
        else:
            export(args.file, args.out, physics=not args.no_physics, card_path=args.card)
    except NoDeck as exc:
        print(f"petra: nothing written: {exc}", file=sys.stderr)
        return 2
    except (*INPUT_ERRORS, OSError) as exc:
        print(f"petra: {exc}", file=sys.stderr)
        return 3
    except grid.DeckError as exc:      # a deck of the folder that does not hold together or has no run beside it: no file of the design
        print(f"petra: nothing written: the decks of this Petra do not read: {exc}", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
