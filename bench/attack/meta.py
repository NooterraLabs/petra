"""Metamorphic pairs: a change to an input and what must follow from it, with no oracle.

Each relation is checked against the pages before it is trusted. A relation the pages do not
promise is narrowed to where they do, or left out, and `PROMISES` says where each stands.

  units      A number written in another unit of its dimension is the same number. The
             reader writes the same files for `3/4 inch`, `19.05 mm` and `0.01905 m`
             (reference.md, "Units"). The attacker checks the files byte for byte, and checks
             the SI value of each number against its own table of factors, written from the
             definitions and not from `petra/units.py`.
  rename     A part named another name: the same verdict and the same cells under the new
             name (format.md, Parts 1). Not a card's case names: cells are in the order of
             the cases' names, so a case renamed may move its cells.
  reorder    The lines of a part, the parts' givens, the load blocks and the waivers in
             another order: the same verdict and the same cells, as a set (format.md: cells
             are made "for each part in the design's order", so the order of parts is kept,
             and `joins a b` is never swapped: the pages say it is another design).
  load_up    A load raised, nothing else changed, never turns FAIL into PASS; lowered, never
             PASS into FAIL. The pages do not promise it for a deck in which a rule can read
             a load on the side of its limit, or in a condition. It holds where every rule
             reads a load as its whole left side (`pull <= capacity`), which `load_monotone`
             tests on the deck's JSON, and is checked there and nowhere else.
  stronger   A plate made thicker, or its steel stronger, with nothing else changed, does not
             turn PASS into FAIL unless a rule says why. Held to the deck that ships, whose
             rules the attacker read: every one of them is a strength that grows with the
             thickness and the stresses, or a limit that does. A mutated deck may have a
             rule that says why, so it is not held.
  respell    A deck's value written another way (a decimal, a fraction, a whole number and a
             fraction, thousands with commas, another unit) or its rules and rows in another
             order: the same verdict and the same cells (deck.md, "A value with its unit").
  json       A file in another JSON spelling: the same verdict and cells (format.md reads no
             order of keys, and hashes are printed and not part of a cell).
  hints      Any hint at all leaves each proved, refuted or not applicable cell as it was or
             open, and the cells the same (format.md, "Cells from a deck of rules").
"""
from __future__ import annotations

import random
import re
from fractions import Fraction
from typing import Any

from . import spec as S, units
from .readers import Diff, Judged
from .spec import Q, Spec

PROMISES = {
    "units": "reference.md, Units: a unit is a factor and nothing more",
    "rename": "format.md, Parts 1 and Cells: a part's name is its identity and nothing else",
    "reorder": "format.md, Parts and Cells: the cells are the same set, and each cell's state does not depend on the order of the lines",
    "load_up": "no page: held only for a deck where every rule reads a load as the whole of its left side",
    "stronger": "no page: held only for the deck that ships, whose rules are strengths that grow with thickness and stress",
    "respell": "deck.md, A value with its unit: a value is its number and its unit",
    "json": "format.md, Numbers: a file is JSON, and no order of keys is read",
    "hints": "format.md, Cells from a deck of rules: a hint can leave a cell open and can do nothing else",
}

BASE = {units.NONE: "", units.LENGTH: "m", units.AREA: "m2", units.FORCE: "N", units.STRESS: "Pa", units.ENERGY: "J", units.MASS: "kg", units.TIME: "s",
        units.CURRENT: "A", units.VOLTAGE: "V", units.POWER: "W", units.RESISTANCE: "ohm", units.TEMPERATURE: "degC"}


# --- what a relation needs to know of a deck

def load_monotone(deck: dict) -> bool:
    """True when every rule that reads a load reads it as the whole of the left side of its inequality, or as a positive multiple of it, and nowhere else.

    Then a rule can only go from holding to failing as the load rises, and no rule can start to hold."""
    for r in deck.get("rules", []):
        if "requires" in r:
            continue
        key = "le" if "le" in r else "lt" if "lt" in r else None
        if key is None:
            return False
        left, right = r[key]
        rest = {k: v for k, v in r.items() if k not in (key, "id", "says", "anchor", "type", "mechanism")}
        if _mentions_load(rest) or _mentions_load(right) or _mentions_load(r.get("let")):
            return False
        if _mentions_load(left):
            ok = (isinstance(left, list) and left[0] == "load") or (
                isinstance(left, list) and left[0] == "mul" and len(left) == 3 and isinstance(left[1], str) and re.fullmatch(r"\d+(?:\.\d+|/\d+)?", left[1]) and Fraction(left[1]) > 0
                and isinstance(left[2], list) and left[2][0] == "load")
            if not ok:
                return False
    return True


def _mentions_load(node: Any) -> bool:
    if isinstance(node, list):
        return (len(node) == 2 and node[0] == "load") or any(_mentions_load(x) for x in node)
    if isinstance(node, dict):
        return any(_mentions_load(x) for x in node.values())
    return False


# --- changes of a spec

def to_si(spec: Spec) -> Spec:
    """Every number of the spec in the base unit of its dimension, by the attacker's own table."""
    s = spec.copy()
    for holder, key, q in S.quantities(s):
        dim = units.factor(q.unit)[1]
        base = BASE.get(dim)
        if base is not None and q.unit != base:
            _set(holder, key, Q(q.si(), base, "frac", q.glue))
    return s


def other_units(rng: random.Random, spec: Spec) -> Spec:
    s = spec.copy()
    for holder, key, q in S.quantities(s):
        if q.unit:
            options = units.spellings(units.factor(q.unit)[1])
            _set(holder, key, q.in_unit(rng.choice(options)) if options else q)
    return s


def _set(holder, key, q) -> None:
    if isinstance(key, list):
        key[1] = q
    else:
        setattr(holder, key, q)


def renamed(rng: random.Random, spec: Spec) -> tuple[Spec, dict[str, str]]:
    """The spec with each part under another name, everywhere the name is written."""
    s = spec.copy()
    new = {}
    for p in s.parts:
        n = rng.choice(["w", "z9", "part_", "Q", "m_" + str(len(new)), "x" * rng.choice([1, 40, 63])])
        while n in new.values() or any(n == q.name for q in s.parts):
            n += "_"
        new[p.name] = n
    for old, n in new.items():
        for p in s.parts:
            for line in p.lines:
                v = line[1]
                if isinstance(v, str):
                    if v.startswith("given "):
                        g = v[6:].strip()
                        line[1] = "given " + (n + g[len(old):] if g.startswith(old + ".") and g.split(".")[0] == old else g)
                    elif line[0] == "joins" or " " in v and all(w in new for w in v.split()):
                        line[1] = " ".join(new.get(w, w) for w in v.split())
    for p in s.parts:
        for line in p.lines:
            if isinstance(line[1], str) and line[1].startswith("given "):
                g = line[1][6:].strip()
                head, _, tail = g.partition(".")
                line[1] = f"given {new.get(head, head)}.{tail}"
    for g in s.givens:
        head, _, tail = g.name.partition(".")
        g.name = f"{new.get(head, head)}.{tail}"
    for ld in s.loads:
        for e in ld.entries:
            e.part = new.get(e.part, e.part)
    for w in s.waivers:
        w.subject = new.get(w.subject, w.subject)
    for p in s.parts:
        p.name = new[p.name] if p.name in new else p.name
    return s, new


def shuffled(rng: random.Random, spec: Spec) -> Spec:
    s = spec.copy()
    for p in s.parts:
        rng.shuffle(p.lines)
    rng.shuffle(s.givens)
    rng.shuffle(s.loads)
    for ld in s.loads:
        rng.shuffle(ld.entries)
    rng.shuffle(s.waivers)
    return s


def scaled_loads(spec: Spec, factor: Fraction) -> Spec | None:
    s = spec.copy()
    n = 0
    for ld in s.loads:
        for e in ld.entries:
            e.lo, e.hi = e.lo.of_si(e.lo.si() * factor), e.hi.of_si(e.hi.si() * factor)
            n += 1
    return s if n else None


def stronger(rng: random.Random, spec: Spec) -> Spec | None:
    """Each plate thicker by a few percent, or each stress higher, and nothing else changed. A bound the card gives is raised at both ends."""
    s = spec.copy()
    which = rng.choice(["thickness", "Fy", "Fu", "all"])
    f = Fraction(rng.choice([101, 110, 150, 200]), 100)
    n = 0
    for p in s.parts:
        if p.type != "plate":
            continue
        for line in p.lines:
            if line[0] in ("thickness", "Fy", "Fu") and (which in ("all", line[0])):
                v = line[1]
                if isinstance(v, Q):
                    line[1] = v.of_si(v.si() * f)
                    n += 1
                elif isinstance(v, str) and v.startswith("given "):
                    g = next((g for g in s.givens if g.name == v[6:].strip()), None)
                    if g and g.form == "in":
                        g.lo, g.hi = g.lo.of_si(g.lo.si() * f), g.hi.of_si(g.hi.si() * f)
                        n += 1
    return s if n else None


# --- the checks

def same(a: Judged, b: Judged, what: str, rename: dict[str, str] | None = None, ordered: bool = True) -> list[Diff]:
    """The verdict and the cells of two judged inputs are the same, up to the names a rename changed and, when not `ordered`, the order of cells."""
    ka, kb = a.verdict.get("kernel"), b.verdict.get("kernel")
    if ka is None or kb is None:
        return []
    if ka != kb:
        return [Diff("relation", what, f"{ka} and then {kb}", key=f"{what}|{ka}|{kb}|{_which(a, b, rename)}")]
    if ka == "ILL-FORMED":
        return []
    ca = [(rename.get(c[0], c[0]) if rename else c[0], c[1], c[2], c[3]) for c in a.cells]
    cb = [(c[0], c[1], c[2], c[3]) for c in b.cells]
    if not ordered:
        ca, cb = sorted(ca), sorted(cb)
    if ca != cb:
        first = next(((x, y) for x, y in zip(ca, cb) if x != y), (len(ca), len(cb)))
        return [Diff("relation", what, f"the cells differ: {first[0]} and then {first[1]}", key=f"{what}|cells|{[(x[1], x[3], y[3]) for x, y in zip(ca, cb) if x != y][:2]}")]
    return []


def _which(a: Judged, b: Judged, rename) -> str:
    sa = {(c[1], c[2]): c[3] for c in a.cells}
    sb = {(c[1], c[2]): c[3] for c in b.cells}
    return ",".join(sorted({k[0] for k in sa if sb.get(k) != sa[k]}))[:60]


def load_check(base: Judged, child: Judged, up: bool) -> list[Diff]:
    """Raising loads must not turn FAIL into PASS."""
    kb, kc = base.verdict.get("kernel"), child.verdict.get("kernel")
    if (kb, kc) == ("FAIL", "PASS") and up or (kb, kc) == ("PASS", "FAIL") and not up:
        fresh = sorted({c[1] for c in (child.cells if not up else base.cells) if c[3] == "refuted"})
        return [Diff("relation", "load_up", f"{kb} and then {kc} when the loads went {'up' if up else 'down'}", key=f"load|{kb}|{kc}|{up}|{fresh[:3]}")]
    return []


def stronger_check(base: Judged, child: Judged) -> list[Diff]:
    kb, kc = base.verdict.get("kernel"), child.verdict.get("kernel")
    if (kb, kc) == ("PASS", "FAIL"):
        gone = sorted({c[1] + "/" + c[2].split("/")[0] for c in child.cells if c[3] == "refuted"})
        return [Diff("relation", "stronger", f"a plate made thicker or stronger turns {kb} into {kc}: refuted {gone[:4]}", key=f"stronger|{gone[:3]}")]
    return []


def hints_check(honest: Judged, got: Judged) -> list[Diff]:
    from .files import sound
    if honest.verdict.get("kernel") in (None, "ILL-FORMED") or got.verdict.get("kernel") is None:
        return []
    if got.verdict["kernel"] == "ILL-FORMED":
        return []            # a hint the shape rules refuse refuses the files whole, which the pages say
    why = sound(honest.cells, got.cells)
    if why:
        return [Diff("relation", "hints", why, key=f"hints|{re.sub(r'[a-z0-9_.]+/', '', why)[:50]}")]
    if honest.verdict["kernel"] == "FAIL" and got.verdict["kernel"] == "PASS":
        return [Diff("relation", "hints", "FAIL turned PASS by other hints", key="hints|fail-pass")]
    return []
