"""A formalizer run for rules: two transcriptions of the rules for a task, the worked
examples, and how much of a wrong rule the acceptance check catches.

    python bench/formalizer/rules.py [--task rules_task.json] [--rules DECK.json] [--second rules_b.json] [--examples FILE.json] [--no-damage]

It prints the acceptance check of petra/rule.py on the first transcription with the other
as its second. Then it damages each admitted rule one change at a time, as `mutations`
lists, and counts the damaged rules that the check refuses with no second transcription,
by the part of the check that refuses and by the kind of damage. A damaged rule that
gives every sampled part the answer the original gives is not a wrong rule and is left out.

The check is petra/rule.py and not this script, so that a deck's own tests can run it.
What is here is the damage and the tally, which only a measurement needs.
RULES_TRANSCRIBE.md briefs a transcriber of rules, and RULES_COLLECT.md a collector of
worked examples.

The files default to the first run's, of 2026-11-11. The task, rules_task.json, is the lap
of AISC 360-22: the types and the grid of petra/decks/aisc360.json over that deck's rows.
The first transcription is the four rules that deck ships. The second, rules_b.json, was
written by a language model from its memory of the standard and from the rows' own
descriptions, with no copy of the standard, before it read the first: it had seen the
deck's types, grid and rows, and what docs/deck.md shows of the rules. The run has no
worked example, since it had no source to take one from.

The two agree at every part tried, on the three mechanisms with rules, the four that
cannot arise and the eight left out. Of 157 wrong rules made by one change the check with
no second transcription refused 115: 86 of them by `alike` alone, which sees a change to
one of the lap's two plates and not to the other, and 29 by another part of the check.
docs/deck.md, "The first run", has the table.
"""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterator, Mapping

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from petra import rule  # noqa: E402

PARTS = ("units", "examples", "reach", "direction", "alike", "reads")
KINDS = ("other part", "similar field", "factor", "min for max", "term dropped", "where dropped", "key column", "other load", "other row",
         "when inverted", "sides swapped", "turned round")
"""The kinds of damage, each a way a transcriber errs: a field of the other joined part; the
wrong one of two fields of one dimension, as Fy for Fu; a number a tenth off, or a power one
off; a min for a max; an argument of a sum, a product, a min or a max left out; a range left
out; a key bound to the wrong column of a table; the load of another kind; the row of another
equation with the same kinds of input; a `when` turned into its opposite; the two sides of
the inequality or of a range changed places; a difference or a quotient turned round."""


def _number(node: Any) -> Fraction | None:
    if not isinstance(node, str):
        return None
    try:
        return Fraction(node)
    except (ValueError, ZeroDivisionError):
        return None


def mutations(body: Mapping[str, Any], task: rule.Task) -> Iterator[tuple[str, str, dict]]:
    """(the kind of damage, what was changed, the damaged rule), one change each."""
    deck = task.deck
    kind = deck.types[body["type"]]
    keys, sizes, loads = rule._names(deck, kind.name)
    aliases = {alias: f.type for f in kind.fields.values() if f.type is not None for alias in f.names}

    def at(path: tuple) -> Any:
        node: Any = body
        for step in path:
            node = node[step]
        return node

    for path, node in rule.places(body):
        if not path or path[0] not in ("le", "let", "where") or "why" in path:
            continue
        parent = at(path[:-1])
        head = parent[0] if isinstance(parent, list) and parent else None
        said = " ".join(str(step) for step in path[:2])
        side = path[:-1] == ("le",) or (len(path) == 4 and path[0] == "where" and path[2] == "le")
        operand = side or isinstance(parent, dict) or (head not in ("q", "load", "key", "by", "row") and path[-1] != 0)

        def damaged(new: Any, kind_of: str, what: str) -> tuple[str, str, dict]:
            return kind_of, f"{what} in {said}", rule.put(body, path, new)

        if isinstance(node, str) and node in sizes and operand:
            prefix, dot, inner = node.rpartition(".")
            for other in aliases:
                if dot and other != prefix and aliases[other] == aliases[prefix]:
                    yield damaged(f"{other}.{inner}", "other part", f"{node} becomes {other}.{inner}")
            for other in sizes:
                if other != node and other.rpartition(".")[0] == prefix and sizes[other].dim == sizes[node].dim:
                    yield damaged(other, "similar field", f"{node} becomes {other}")
        x = _number(node)
        if x is not None and (operand or (head == "q" and path[-1] == 1)):
            if head == "pow" and path[-1] == 2:
                yield damaged(str(x + 1), "factor", f"exponent {node} plus one")
            elif x not in (0, 1):
                yield damaged(str(x * Fraction(11, 10)), "factor", f"{node} up a tenth")
                yield damaged(str(x * Fraction(9, 10)), "factor", f"{node} down a tenth")
        if not isinstance(node, list) or not node:
            continue
        op, args = node[0], node[1:]
        if op in ("min", "max"):
            yield damaged(["max" if op == "min" else "min", *args], "min for max", f"{op} becomes the other")
        if op in ("min", "max", "add", "mul") and len(args) >= 2:
            for n in range(len(args)):
                kept = args[:n] + args[n + 1:]
                yield damaged(kept[0] if len(kept) == 1 else [op, *kept], "term dropped", f"{op} loses argument {n + 1}")
        if op in ("sub", "div") and len(args) == 2:
            yield damaged([op, args[1], args[0]], "turned round", f"{op} turned round")
        if op == "load" and len(args) == 1:
            for other, f in loads.items():
                if other != f"load {args[0]}" and f"load {args[0]}" in loads and f.dim == loads[f"load {args[0]}"].dim:
                    yield damaged(["load", other[5:]], "other load", f"load {args[0]} becomes {other[5:]}")
        if op == "row" and len(args) == 2 and args[0] in deck.rows and isinstance(args[1], dict):
            row = deck.rows[args[0]]
            for name, takes in row.takes.items():
                bound = args[1].get(name)
                if not takes.keys or bound is None:
                    continue
                following = {k: takes.keys[(n + 1) % len(takes.keys)] for n, k in enumerate(takes.keys)}
                if isinstance(bound, str) and bound in keys:
                    yield damaged([op, args[0], {**args[1], name: ["by", bound, {k: following[k] for k in keys[bound]}]}], "key column", f"{name} of {args[0]} reads the next column")
                elif isinstance(bound, list) and bound[:1] == ["key"]:
                    yield damaged([op, args[0], {**args[1], name: ["key", following[bound[1]]]}], "key column", f"{name} of {args[0]} reads the next column")
                elif isinstance(bound, list) and bound[:1] == ["by"]:
                    for k, to in bound[2].items():
                        if following[to] != to:
                            yield damaged([op, args[0], {**args[1], name: ["by", bound[1], {**bound[2], k: following[to]}]}], "key column", f"{name} of {args[0]} reads the next column for {k}")
                    for (k, to), (j, other) in itertools.combinations(bound[2].items(), 2):
                        if to != other:
                            yield damaged([op, args[0], {**args[1], name: ["by", bound[1], {**bound[2], k: other, j: to}]}], "key column", f"{name} of {args[0]}: {k} and {j} change columns")
            for other in deck.rows.values():
                mine, theirs = ([n for n, i in sorted(r.takes.items(), key=lambda item: str(item[1].kind))] for r in (row, other))
                if other.id != row.id and other.dim == row.dim and [row.takes[n].kind for n in mine] == [other.takes[n].kind for n in theirs] and set(args[1]) == set(mine):
                    yield damaged([op, other.id, {b: args[1][a] for a, b in zip(mine, theirs)}], "other row", f"{row.id} becomes {other.id}")
    if "when" in body:
        yield "when inverted", "`when` becomes its opposite", {**body, "when": ["not", body["when"]]}
    yield "sides swapped", "the two sides of `le` change places", {**body, "le": [body["le"][1], body["le"][0]]}
    for n, w in enumerate(body.get("where", [])):
        ranges = list(body["where"])
        yield "where dropped", f"range {n + 1} left out", {k: v for k, v in {**body, "where": ranges[:n] + ranges[n + 1:]}.items() if k != "where" or v}
        yield "sides swapped", f"the two sides of range {n + 1} change places", {**body, "where": ranges[:n] + [{**w, "le": [w["le"][1], w["le"][0]]}] + ranges[n + 1:]}


def measure(first: rule.Reading, examples: Mapping[str, list[rule.Worked]], admitted: list[str], seed: int = 0) -> tuple[list[str], dict[str, collections.Counter]]:
    """Damages each rule of each admitted mechanism and runs the check on it with no second
    transcription. Gives a line for each rule, and for each kind of damage how many wrong
    rules it made and how many each part of the check refused."""
    lines, kinds = [], {kind: collections.Counter() for kind in KINDS}
    task = first.task
    for mechanism in admitted:
        bodies = [r for r in first.said.rules if r.get("mechanism") == mechanism]
        for body in bodies:
            counts: collections.Counter = collections.Counter()
            passed = []
            for kind, what, damaged in mutations(body, task):
                wrong = first.with_rules(mechanism, [damaged if r is body else r for r in bodies], first.said.unless.get(mechanism))
                if mechanism not in wrong.wrong and rule.second(first, wrong, mechanism, rule.parts(task, mechanism, [first, wrong], seed)).outcome == "pass":
                    counts["same"] += 1
                    continue
                found = rule.checks(wrong, mechanism, examples.get(mechanism, []), rule.parts(task, mechanism, [wrong], seed), unused=False)
                failed = {c.name for c in found if c.outcome == "fail"} | ({"reads"} if rule.reads(wrong).outcome == "fail" else set())
                for tally in (counts, kinds[kind]):
                    tally.update(["wrong", *failed, *(["any"] if failed else []), *(f"only {name}" for name in failed if len(failed) == 1)])
                if not failed:
                    passed.append(f"{what} ({kind})")
            by = ", ".join(f"{name} {counts[name]}" for name in PARTS if counts[name])
            shown = "; ".join(passed[:8]) + (f"; and {len(passed) - 8} more" if len(passed) > 8 else "")
            lines.append(f"  {body['id']}: {counts['wrong']} wrong rules, {counts['any']} refused" + (f" ({by})" if by else "") + f", {counts['same']} the same as the rule"
                         + (f"; passed: {shown}" if passed else ""))
    return lines, kinds


def table(kinds: Mapping[str, collections.Counter]) -> list[str]:
    """The tally as a table: a line for each kind of damage that made a wrong rule, and the
    total. `alike` sees a change made to one of two like parts and not to the other, which
    is what one change at a time makes. A transcriber who errs the same way for both is not
    seen by it, so the last line counts what the other parts refuse."""
    total: collections.Counter = collections.Counter()
    for tally in kinds.values():
        total.update(tally)
    head = f"  {'damage':<14} {'wrong':>5} {'refused':>12} " + " ".join(f"{name:>9}" for name in PARTS)

    def line(name: str, tally: collections.Counter) -> str:
        share = f"{tally['any']} ({tally['any'] / tally['wrong']:.0%})" if tally["wrong"] else "0"
        return f"  {name:<14} {tally['wrong']:>5} {share:>12} " + " ".join(f"{tally[part]:>9}" for part in PARTS)

    alone = ", ".join(f"{name} {total[f'only {name}']}" for name in PARTS if total[f"only {name}"])
    others = total["any"] - total["only alike"]
    return [head, *(line(kind, tally) for kind, tally in kinds.items() if tally["wrong"]), line("all", total), f"  refused by one part of the check and no other: {alone or 'none'}",
            f"  refused by a part other than `alike`: {others}" + (f" ({others / total['wrong']:.0%})" if total["wrong"] else "")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].replace("\n", " "))
    parser.add_argument("--task", default=str(HERE / "rules_task.json"))
    parser.add_argument("--rules", default=str(HERE.parent.parent / "petra" / "decks" / "aisc360.json"), help="the first transcription, or a deck")
    parser.add_argument("--second", default=str(HERE / "rules_b.json"))
    parser.add_argument("--examples")
    parser.add_argument("--no-damage", action="store_true", help="run the acceptance check and stop")
    args = parser.parse_args(argv)
    task = rule.read_task(json.loads(Path(args.task).read_text(encoding="utf-8")), Path(args.task).parent)
    first, other = rule.load(task, args.rules), rule.load(task, args.second)
    given = json.loads(Path(args.examples).read_text(encoding="utf-8"))["examples"] if args.examples else {}
    examples = {m: [rule.worked(e, task, m) for e in found] for m, found in given.items()}
    lines, whole = rule.accept(first, examples, other)
    print("\n".join(rule.render(lines, whole, first.stray)))
    states = collections.Counter(line.state for line in lines)
    print(f"\n{len(lines)} mechanisms: " + ", ".join(f"{n} {state}" for state, n in sorted(states.items())))
    for name in ("units", "examples", "reach", "direction", "alike", "second"):
        outcomes = collections.Counter(c.outcome for line in lines for c in line.checks if c.name == name)
        print(f"  {name:<10} " + ", ".join(f"{n} {outcome}" for outcome, n in sorted(outcomes.items())))
    if args.no_damage:
        return 0
    print("\nDamaged rules that the check refuses with no second transcription")
    by_rule, kinds = measure(first, examples, [line.mechanism for line in lines if line.state == "admitted" and line.rules])
    print("\n".join(by_rule))
    print()
    print("\n".join(table(kinds)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
