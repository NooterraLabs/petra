"""A card and a design as the kernel reads them:
`python -m petra.export FILE.petra [--card FILE.card] --out DIR`.

Writes four files into DIR (docs/format.md):

    card.json     what the asker owns: the load cases, every bound, the claims, the waivers
    design.json   what the designer owns: every quantity written in a component block
    deck.json     the registry values the proofs read, and the domains of petra/decks/core.json
    proofs.json   one cell per obligation, with the proof of each that has one

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

from .ir import Component, Design, Fixed, Input, ParamRef, Ref, Vec
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


def card(design: Design, inputs: list[Input]) -> dict[str, Any]:
    """What the card states. An input's name is the stem of its premise label, and `inputs`
    is every signed bound the models hold (pipeline.signed_inputs). A load or an ambient
    that reads a param is an input with no `by`."""
    cases = {id(e.value): load.name for load in design.loads.values() for e in load.entries}
    claims = [{"name": c.name, "subject": ".".join(c.qoi.path), "quantity": c.qoi.name, "rel": c.rel.value,
               "cases": list(c.under), "bound": _quantity(c.bound)} for c in design.claims]
    unsigned = [(f"{load.name}.{'.'.join(e.target)}.{e.field}", load.name, e.value)
                for load in design.loads.values() for e in load.entries if isinstance(e.value, ParamRef)]
    if isinstance(design.ambient, ParamRef):
        unsigned.append(("ambient", None, design.ambient))
    return {"format": "petra-card/0", "name": design.name, "environment": design.environment, "cases": sorted(design.loads),
            "inputs": [{"name": i.name, **({"case": cases[id(i)]} if id(i) in cases else {}), "by": i.signature.owner, **_quantity(i.range)}
                       for i in inputs]
                      + [{"name": name, **({"case": case} if case else {}), **_quantity(design.params[ref.name].range)}
                         for name, case, ref in unsigned],
            "claims": claims,
            "waivers": [{"subject": ".".join(w.subject), "mechanism": w.mode, "by": w.owner, "reason": w.reason} for w in design.waivers]}


def design_file(design: Design, card_hash: str) -> dict[str, Any]:
    """What the designer wrote: every number in a component block, and the params."""
    return {"format": "petra-design/0", "name": design.name, "card": card_hash,
            "quantities": [q for c in design.components.values() for q in written(c)],
            "params": [{"name": p.name, **_quantity(p.range)} for p in design.params.values()]}


def tape(statement: Any) -> dict[str, Any] | None:
    """A statement of the interval rule as numbered nodes, each built from earlier ones, or
    None for a statement of another shape. An input is a hypothesis of the statement: its
    premise label and its range."""
    from .kernel import Abs, Add, Const, Div, Exp, Ln, Max, Min, Mul, Neg, Pi, PowInt, RangeHyp, Sqrt, Sym
    from .kernel.rules.r4_enclosure import AllNonpositive

    if not isinstance(statement.goal, AllNonpositive) or not all(isinstance(h, RangeHyp) for h in statement.hyps):
        return None
    index = {h.sym: i for i, h in enumerate(statement.hyps)}
    many = {Add: "add", Mul: "mul", Min: "min", Max: "max"}
    one = {Neg: "neg", Sqrt: "sqrt", Ln: "ln", Exp: "exp", Abs: "abs"}
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


class _Proofs:
    """The evidence the Python kernel accepted, by statement hash."""

    def __init__(self) -> None:
        self.items: dict[str, tuple[Any, Any]] = {}

    def record(self, statement: Any, statement_hash: str, evidence: Any, source: str) -> None:
        self.items[statement_hash] = (statement, evidence)


def cells(report: Any, proofs: _Proofs) -> list[dict[str, Any]]:
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
    return "sha256:" + hashlib.sha256(data.encode("utf-8")).hexdigest()


def export(path: str, out: Path, physics: bool = True, card_path: str | None = None) -> None:
    """Write card.json, design.json and deck.json, then proofs.json when `physics`. The
    first three need no solver, so the kernel can refuse an ill-formed design before any
    physics runs."""
    from .lang import load_design
    from .pipeline import check_design, lower_components, signed_inputs
    from .registry import build_registry
    from .solvers import SolverSource

    def write(name: str, body: str) -> None:
        (out / name).write_text(body, encoding="utf-8", newline="\n")

    registry = build_registry()
    design = load_design(path, registry, card_path)
    inputs = sorted(signed_inputs(design, lower_components(design, registry)), key=lambda i: i.name)
    out.mkdir(parents=True, exist_ok=True)
    card_text = text(card(design, inputs))
    write("card.json", card_text)
    write("design.json", text(design_file(design, sha256(card_text))))
    found: list[dict[str, Any]] = []
    if physics:
        proofs = _Proofs()
        found = cells(check_design(design, registry, (SolverSource(),), sink=proofs, path=path), proofs)
        write("proofs.json", text({"format": "petra-proofs/0", "cells": found}))
    write("deck.json", text(deck(registry, found)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m petra.export", description=__doc__.split("\n")[0])
    parser.add_argument("file", help="the design, a .petra file")
    parser.add_argument("--card", metavar="FILE", help="the card the design answers; default the .card file beside the design")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--no-physics", action="store_true", help="write no proofs.json")
    args = parser.parse_args(argv)
    from .repair import INPUT_ERRORS

    try:
        export(args.file, args.out, physics=not args.no_physics, card_path=args.card)
    except (*INPUT_ERRORS, OSError) as exc:
        print(f"petra: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
