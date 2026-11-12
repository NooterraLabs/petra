"""A card and a design as the kernel reads them:
`python -m petra.export FILE.petra [--card FILE.card] --out DIR`.

Writes four files into DIR (docs/format.md):

    card.json     what the asker owns: the load cases, every bound, the claims, the waivers
    design.json   what the designer owns: every quantity written in a component block
    deck.json     the registry values the proofs read, and the domains of petra/decks/core.json
    proofs.json   one cell per obligation, with the proof of each that has one

For a design whose parts are of a deck of rules it writes a fifth, rules.json, the deck's
file as it ships. design.json then holds the parts as written, and proofs.json holds hints.
With --no-physics such a design is written as it stands, without asking the grid whether
the deck's types take it: the kernel reads the parts itself and says.

`python -m petra.export --card-only FILE.card --out DIR` writes card.json from the card
with no design, and prints its hash. For a design of a deck's types card.json holds nothing
the design chooses, so this is how an asker works out the hash of their own card.

Untrusted. It reads the two files through the language and the models, so a bug here
gives the kernel the wrong files, and the kernel's verdict is about the files it was given.
A load or an ambient that reads a param is an input nobody signed, and goes into card.json
with no `by`, which the kernel refuses. Exits 3 when the language or a model refuses the
pair, as `petra check` does, and then writes nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterator

from .ir import Bound, Component, Design, Fixed, Input, ParamRef, Ref, Stated, Text, Vec
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
    return sorted(given + loads + ([design.ambient] if isinstance(design.ambient, Input) else []), key=lambda i: i.name)


def card(design: Design, inputs: list[Input], placed: bool = False) -> dict[str, Any]:
    """What the card states. An input's name is the stem of its premise label, and `inputs`
    is every signed bound the models hold (pipeline.signed_inputs). A load or an ambient
    that reads a param is an input with no `by`. With `placed`, for a design checked
    against a deck of rules, a load also says the part it is `on` and which `field` it is,
    and the card names its tests records and its probability claims, which the other
    designs' cards leave out. A card that states a key or a whole number exactly, with
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
    return {"format": "petra-card/0", "name": design.name, "environment": design.environment, "cases": sorted(design.loads),
            "inputs": [{"name": i.name, **cases.get(id(i), {}), "by": i.signature.owner, **_quantity(i.range)} for i in inputs]
                      + [{"name": name, **case, **_quantity(design.params[ref.name].range)} for name, case, ref in unsigned],
            "claims": claims,
            **({"tests": sorted(design.tests), "probability_claims": [c.name for c in design.probability_claims]} if placed else {}),
            **({"states": [{"name": s.name, "by": s.signature.owner, **({"key": s.key} if s.whole is None else {"whole": str(s.whole)})}
                           for _, s in sorted(design.states.items())]} if placed and design.states else {}),
            "waivers": [{"subject": ".".join(w.subject), "mechanism": w.mode, "by": w.owner, "reason": w.reason} for w in design.waivers]}


def design_file(design: Design, card_hash: str, deck: bool = False) -> dict[str, Any]:
    """What the designer wrote: every number in a component block, and the params. For a
    design checked against a deck of rules, also the parts as written."""
    return {"format": "petra-design/0", "name": design.name, "card": card_hash,
            "quantities": [q for c in design.components.values() for q in written(c)],
            "params": [{"name": p.name, **_quantity(p.range)} for p in design.params.values()],
            **({"parts": parts(design)} if deck else {})}


def tape(statement: Any) -> dict[str, Any] | None:
    """A statement of the interval rule as numbered nodes, each built from earlier ones, or
    None for a statement of another shape. An input is a hypothesis of the statement: its
    premise label and its range."""
    from .kernel import Abs, Add, Const, Cos, Div, Exp, Ln, Max, Min, Mul, Neg, Pi, PowInt, RangeHyp, Sqrt, Sym
    from .kernel.rules.r4_enclosure import AllNonpositive

    if not isinstance(statement.goal, AllNonpositive) or not all(isinstance(h, RangeHyp) for h in statement.hyps):
        return None
    index = {h.sym: i for i, h in enumerate(statement.hyps)}
    many = {Add: "add", Mul: "mul", Min: "min", Max: "max"}
    one = {Neg: "neg", Sqrt: "sqrt", Ln: "ln", Exp: "exp", Cos: "cos", Abs: "abs"}
    nodes: list[list[Any]] = []
    seen: dict[int, int] = {}

    def emit(e: Any) -> int:
        if id(e) in seen:
            return seen[id(e)]
        if isinstance(e, Const):
            node: list[Any] = ["c", number(e.value)]
        elif isinstance(e, Sym):
            node = ["s", index[e.name]]
        elif isinstance(e, Pi):
            node = ["pi"]
        elif type(e) in many:
            node = [many[type(e)], [emit(x) for x in e.args]]
        elif type(e) in one:
            node = [one[type(e)], emit(e.arg)]
        elif isinstance(e, Div):
            node = ["div", emit(e.num), emit(e.den)]
        elif isinstance(e, PowInt):
            node = ["pow", emit(e.base), e.exponent]
        else:
            raise TypeError(type(e).__name__)
        seen[id(e)] = len(nodes)
        nodes.append(node)
        return seen[id(e)]

    roots = [emit(e) for e in statement.goal.exprs]
    return {"inputs": [{"label": h.label, "lo": number(h.lo), "hi": number(h.hi)} for h in statement.hyps], "nodes": nodes, "roots": roots}


def _partition(node: Any, index: dict[str, int]) -> Any:
    from .kernel import Leaf

    if isinstance(node, Leaf):
        return "leaf"
    return {"input": index[node.sym], "at": number(node.at), "below": _partition(node.left, index), "above": _partition(node.right, index)}


class Proofs:
    """The evidence the Python kernel accepted, by statement hash. An evidence sink that
    also passes each piece on to `sink`, when there is one."""

    def __init__(self, sink: Any = None) -> None:
        self.items: dict[str, tuple[Any, Any]] = {}
        self.sink = sink

    def record(self, statement: Any, statement_hash: str, evidence: Any, source: str) -> None:
        self.items[statement_hash] = (statement, evidence)
        if self.sink is not None:
            self.sink.record(statement, statement_hash, evidence, source)


def cells(report: Any, proofs: Proofs) -> list[dict[str, Any]]:
    """One cell per obligation the coverage rules demand, and one per mode they excuse."""
    from .kernel.rules.r4_enclosure import Enclosure, PointWitness

    states = {"certified": "proved", "refuted": "refuted", "waived": "waived"}
    out: list[dict[str, Any]] = []
    body = report.to_json()
    for verdict in body["verdicts"]:
        for o in verdict["obligations"]:
            subject, mechanism, entry = o["requirement"].split("/", 2)
            cell: dict[str, Any] = {"subject": subject, "mechanism": mechanism, "entry": entry,
                                    "state": states.get(o["outcome"], "open"), "rule": o["rule"]}
            found = proofs.items.get(o["statement_hash"])
            given = None if found is None or found[1].defined else tape(found[0])
            if given is not None:
                index = {h.sym: i for i, h in enumerate(found[0].hyps)}
                proof = found[1].body
                if cell["state"] == "proved" and isinstance(proof, Enclosure):
                    cell |= {"tape": given, "partition": _partition(proof.partition, index)}
                elif cell["state"] == "refuted" and isinstance(proof, PointWitness):
                    point = dict(proof.point)
                    cell |= {"tape": given, "point": [number(point[h.sym]) for h in found[0].hyps], "which": proof.which}
            if cell["state"] == "open":
                cell["why"] = "; ".join(o["needs"]) or o["note"] or o["outcome"]
            out.append(cell)
    for u in body["unchecked"]:
        out.append({"subject": u["subject"], "mechanism": u["mode"], "entry": "", "state": "not_applicable", "why": u["reason"]})
    return out


def deck(registry: Any, found: list[dict[str, Any]]) -> dict[str, Any]:
    """The domains of petra/decks/core.json, and the registry values the proofs read."""
    labels = sorted({i["label"] for c in found if "tape" in c for i in c["tape"]["inputs"] if i["label"].startswith("reg:")})
    constants = [{"label": label, **_range(registry.fact(label[len("reg:"):]).value)} for label in labels]
    return {"format": "petra-deck/0", "domains": json.loads(CORE.read_text(encoding="utf-8"))["domains"], "constants": constants}


def text(body: dict[str, Any]) -> str:
    return json.dumps(body, indent=1, sort_keys=True) + "\n"


def sha256(data: str) -> str:
    """The hash of a text as UTF-8 with LF line ends, so a file's hash does not change
    with the line ends a checkout gave it."""
    return "sha256:" + hashlib.sha256(data.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def bundle(design: Design, registry: Any, report: Any = None, proofs: Proofs | None = None) -> dict[str, str]:
    """The text of each file the kernel reads, by its name in docs/format.md: `card`,
    `design` and `deck`, and `proofs` when there is a report with the evidence behind it."""
    from .pipeline import lower_components, signed_inputs

    inputs = sorted(signed_inputs(design, lower_components(design, registry)), key=lambda i: i.name)
    card_text = text(card(design, inputs))
    out = {"card": card_text, "design": text(design_file(design, sha256(card_text)))}
    found = [] if report is None else cells(report, proofs)
    out["deck"] = text(deck(registry, found))
    if report is not None:
        out["proofs"] = text({"format": "petra-proofs/0", "cells": found})
    return out


def export(path: str, out: Path, physics: bool = True, card_path: str | None = None) -> None:
    """Write card.json, design.json and deck.json, then proofs.json when `physics`. The
    first three need no solver, so the kernel can refuse an ill-formed design before any
    physics runs. A design of a deck of rules gets rules.json too."""
    from .lang import load_design
    from .pipeline import check_design
    from .registry import build_registry
    from .solvers import SolverSource

    from . import grid

    registry = build_registry()
    design = load_design(path, registry, card_path)
    rules = grid.owner(design)
    if rules is not None:
        # Without physics the files are the design as written, and the kernel says whether the deck's types take it.
        files = grid.check(design, rules)[1] if physics else grid.bundle(design, rules)
        out.mkdir(parents=True, exist_ok=True)
        for name, body in files.items():
            if physics or name != "proofs":
                (out / f"{name}.json").write_text(body, encoding="utf-8", newline="\n")
        return
    proofs = Proofs()
    report = check_design(design, registry, (SolverSource(),), sink=proofs, path=path) if physics else None
    out.mkdir(parents=True, exist_ok=True)
    for name, body in bundle(design, registry, report, proofs).items():
        (out / f"{name}.json").write_text(body, encoding="utf-8", newline="\n")


def card_only(card_path: str, out: Path) -> str:
    """Write card.json from a card with no design, and give its hash: the hash the kernel
    prints for the card of any design of a deck's types that answers this card. Such a
    card.json holds nothing a design chooses: each given under the card's own name for it,
    and each load with the part and the field the card puts it on. For a design of the
    models' kinds card.json takes names from the design, and its hash is another."""
    from .lang import load_card

    design = load_card(card_path)
    body = text(card(design, read_inputs(design), placed=True))
    out.mkdir(parents=True, exist_ok=True)
    (out / "card.json").write_text(body, encoding="utf-8", newline="\n")
    return sha256(body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m petra.export", description=__doc__.split("\n")[0])
    parser.add_argument("file", nargs="?", help="the design, a .petra file")
    parser.add_argument("--card", metavar="FILE", help="the card the design answers; default the .card file beside the design")
    parser.add_argument("--card-only", metavar="FILE", help="a card with no design: write its card.json alone and print its hash")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--no-physics", action="store_true", help="write no proofs.json")
    args = parser.parse_args(argv)
    if (args.file is None) == (args.card_only is None) or (args.card_only and (args.card or args.no_physics)):
        parser.error("give a design, or --card-only FILE with no design, no --card and no --no-physics")
    from .repair import INPUT_ERRORS

    try:
        if args.card_only:
            print(card_only(args.card_only, args.out))
        else:
            export(args.file, args.out, physics=not args.no_physics, card_path=args.card)
    except (*INPUT_ERRORS, OSError) as exc:
        print(f"petra: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
