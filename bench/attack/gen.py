"""The generator: designs and cards written from the grammar of docs/format.md and docs/deck.md.

A draft is a pair of texts and the deck they go with. Three ways to make one:

  fresh   a design for each type of a deck, written from the deck's own fields: every line a
          type asks, a given for each signed field, loads for the loads a type takes, and
          waivers for the lines of its grid. Numbers come from what the deck itself writes
          (band edges, constants, ranges), at and around them.
  corpus  a pair of the repository's corpus or examples, changed in one to three places.
  hunt    a pair with one number moved to where a reader changes its answer: found by halving
          between two values that the Python reader answers differently, and written at the
          point, a little under it and a little over it.

What the generator writes is held to what a deck needs of its parts (docs/deck.md, "What a
type needs"): a part that breaks a need is ILL-FORMED and says little, so a draft that breaks
one is made again. A small share is damaged on purpose, so that the refusals are read too.
"""
from __future__ import annotations

import math
import random
import re
import time
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Callable

from . import deckinfo, spec as S, units
from .deckinfo import Info, F
from .spec import Q, Spec

ROOT = Path(__file__).resolve().parents[2]

WORDS = {"in", "mean", "signed", "measured", "source", "param", "given", "card", "ambient", "load", "waive", "tests", "claim", "on", "is", "by", "reason", "petra", "owner", "environment"}
NAMES = ["a", "b", "x", "p1", "tab", "strap", "splice", "plate_1", "_z", "B2", "joint", "A", "lap_main", "q9", "ab", "a_", "Z", "pp", "k"]
CASES = ["gravity", "wind", "storm", "a", "ab", "B", "_x", "a1", "a_", "service", "dead", "live", "seismic", "z"]
REASONS = ['"it is a test"', '"snug-tight bolts"', '"a reason with \\"quotes\\""', '"café"', '"back\\\\slash"', '"nämn"', '"a long reason ' + "x" * 150 + '"']
OWNERS = ["t@example.org", "s.engineer@example.org", "a.b@c.d", "x@y.z"]
DEFAULT_RANGE: dict[units.Dim, tuple[float, float]] = {units.NONE: (0.1, 10), units.TEMPERATURE: (-40, 200)}


@dataclass
class Draft:
    recipe: str
    spec: Spec | None
    deck: dict
    deck_name: str
    deck_text: str                  # the file the kernel reads as rules.json
    base_text: str | None = None    # a deck that loads, to read the design with when deck_text does not
    files: dict[str, str] | None = None
    notes: list[str] = field(default_factory=list)
    damaged: bool = False

    def texts(self) -> tuple[str, str]:
        return self.spec.texts() if self.spec else ("", "")


# --- numbers

def simplest_between(lo: Fraction, hi: Fraction) -> Fraction:
    """The fraction of least denominator in [lo, hi], by the continued-fraction walk."""
    if lo > hi:
        lo, hi = hi, lo
    if lo <= 0 <= hi:
        return Fraction(0)
    if hi < 0:
        return -simplest_between(-hi, -lo)
    fl = lo.numerator // lo.denominator
    if Fraction(fl) == lo:
        return lo
    if fl < hi.numerator // hi.denominator:
        return Fraction(fl + 1)
    rest = simplest_between(1 / (hi - fl), 1 / (lo - fl))
    return fl + 1 / rest


def nearby(rng: random.Random, x: Fraction, calm: int = 0) -> Fraction:
    """The value, or one beside it: at it, a hair either side, a tenth, and the simple multiples that standards use. `calm` makes it likelier to stay at the value."""
    k = rng.choice(["same"] * (6 + calm) + ["hair"] * 3 + ["pct", "tenth", "x2", "half", "three_halves", "two_thirds", "8/3", "24", "12", "1/3", "x10"])
    if k == "same":
        return x
    if k == "hair":
        return x * (1 + rng.choice([-1, 1]) * Fraction(1, rng.choice([10 ** 3, 10 ** 6, 2 ** 30])))
    return x * {"pct": Fraction(rng.choice([99, 101, 98, 102]), 100), "tenth": Fraction(rng.choice([9, 11]), 10), "x2": Fraction(2), "half": Fraction(1, 2),
                "three_halves": Fraction(3, 2), "two_thirds": Fraction(2, 3), "8/3": Fraction(8, 3), "24": Fraction(24), "12": Fraction(12), "1/3": Fraction(1, 3), "x10": Fraction(10)}[k]


def pick_unit(rng: random.Random, info: Info, dim: units.Dim) -> str:
    if dim == units.NONE:
        return ""
    used = info.used.get(dim)
    if used and rng.random() < 0.7:
        return rng.choice(used[:3])
    options = units.spellings(dim)
    return rng.choice(options) if options else ""


def quantity(rng: random.Random, info: Info, f: F, anchor: Fraction | None = None) -> Q:
    """A value for a quantity field: from what the deck writes, at or beside it, in a unit of the field's dimension, above its floor."""
    dim = f.dim or units.NONE
    if f.whole:
        low = int(f.least) if f.least is not None else 1
        n = rng.choice([low, low, low + 1, low + 1, low + 2, 3, 4, 6, 8, 12, 14, 20, 30, 100])
        return Q(Fraction(max(n, low)), "")
    unit = pick_unit(rng, info, dim)
    pool = info.pool.get(dim, [])
    if f.least is not None:
        floor, strict = f.least, False
    elif f.may_be == "negative":
        floor, strict = (Fraction(-5463, 20) if dim == units.TEMPERATURE else None), False
    else:
        floor, strict = Fraction(0), f.may_be is None
    x = Fraction(1)
    for _ in range(8):
        if anchor is not None and rng.random() < 0.8:
            x = nearby(rng, anchor, calm=14)
        elif pool and rng.random() < 0.8:
            x = nearby(rng, rng.choice(pool))
        else:
            lo, hi = DEFAULT_RANGE.get(dim, (0.01, 100))
            x = Fraction(10 ** rng.uniform(math.log10(abs(lo) + 1e-3), math.log10(abs(hi) + 1e-3))).limit_denominator(1000)
            if lo < 0 and rng.random() < 0.3:
                x = -x
            x *= units.factor(unit)[0] if dim not in (units.NONE, units.TEMPERATURE) else 1
        if dim == units.TEMPERATURE and x < Fraction(-5463, 20):
            continue
        if floor is None or x > floor or (x == floor and not strict):
            break
    else:
        x = (floor or Fraction(0)) + abs(x) + Fraction(1, 1000)
    return Q(x / units.factor(unit)[0], unit, rng.choice(["auto", "auto", "frac", "dec"]), rng.choice([" ", " ", " ", ""] if unit and unit[0].isalpha() else [" "]))


def word(name: str, rng: random.Random) -> str:
    """A key's name as a line writes it: bare when it is a plain name, quoted when it has a space, and sometimes quoted for no reason."""
    plain = re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) and name not in WORDS
    return name if plain and rng.random() < 0.8 else '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def signature(rng: random.Random) -> str:
    return f'signed "{rng.choice(OWNERS)}" source "{rng.choice(["calc C-12", "ASTM A36", "a source, with a comma", "test"])}"'


# --- needs

def _interval(node, part: S.Part, spec: Spec, info: Info, joined: dict[str, S.Part]):
    """The range of a need's side over the part's numbers, or None when a number is not there."""
    if isinstance(node, str):
        if re.fullmatch(r"[+-]?\d+(?:\.\d+|/\d+)?", node):
            v = Fraction(node)
            return v, v
        target, _, name = node.rpartition(".")
        owner = joined.get(target) if target else part
        if owner is None:
            return None
        v = owner.get(name)
        if isinstance(v, Q):
            x = v.si()
            return x, x
        if isinstance(v, str) and v.startswith("given "):
            g = next((g for g in spec.givens if g.name == v[6:].strip()), None)
            if g and g.form == "in":
                return g.lo.si(), g.hi.si()
            if g and g.form == "is":
                q = S.q_of(g.exact)
                return (q.si(), q.si()) if q else None
        return None
    if isinstance(node, list) and node:
        op, args = node[0], node[1:]
        if op == "q":
            x = units.si(f"{args[0]} {args[1]}".strip())
            return (x, x) if x is not None else None
        sides = [_interval(a, part, spec, info, joined) for a in args]
        if any(s is None for s in sides):
            return None
        if op == "add":
            return sum(s[0] for s in sides), sum(s[1] for s in sides)
        if op == "sub":
            return sides[0][0] - sides[1][1], sides[0][1] - sides[1][0]
        if op == "neg":
            return -sides[0][1], -sides[0][0]
        if op == "mul":
            lo, hi = Fraction(1), Fraction(1)
            for a, b in sides:
                c = [lo * a, lo * b, hi * a, hi * b]
                lo, hi = min(c), max(c)
            return lo, hi
        if op == "div" and sides[1][0] > 0:
            c = [sides[0][0] / sides[1][0], sides[0][0] / sides[1][1], sides[0][1] / sides[1][0], sides[0][1] / sides[1][1]]
            return min(c), max(c)
    return None


def breaks(spec: Spec, info: Info) -> list[tuple[S.Part, dict]]:
    """The needs of the deck's types that a part of the spec breaks, by the exact rule of docs/deck.md. A need it cannot work out is not counted."""
    out = []
    for p in spec.parts:
        t = info.types.get(p.type)
        if not t:
            continue
        joined: dict[str, S.Part] = {}
        for f in t.fields:
            if f.kind == "joins":
                v = p.get(f.name)
                names = v.split() if isinstance(v, str) else []
                joined = {a: spec.part(n) for a, n in zip(f.names, names) if spec.part(n)}
        for need in t.needs:
            key = "lt" if "lt" in need else "le"
            if key not in need:
                continue
            a, b = (_interval(s, p, spec, info, joined) for s in need[key])
            if a is not None and b is not None and not (a[1] < b[0] if key == "lt" else a[1] <= b[0]):
                out.append((p, need))
    return out


# --- fresh designs

def pname(rng: random.Random, used: set[str], hint: str) -> str:
    for _ in range(20):
        n = hint if not used and rng.random() < 0.6 else rng.choice([hint, hint + str(len(used) + 1), *NAMES])
        if rng.random() < 0.03:
            n = "p" + "x" * rng.choice([62, 63])
        if n not in used and n not in WORDS:
            used.add(n)
            return n
    n = f"{hint}{len(used)}_{rng.randrange(1000)}"
    used.add(n)
    return n


ANCHORS: dict[tuple[str, str], list[Fraction]] = {}
"""What the corpus writes for a field of a type, in SI: a fresh design starts from these as often as from the deck's own numbers."""


def _quantity_line(rng, info, spec, part, f, signed_card=True):
    given_name = f"{part.name}.{f.name}"
    anchors = ANCHORS.get((part.type, f.name))
    anchor = rng.choice(anchors) if anchors and rng.random() < 0.6 else None
    if f.signed or rng.random() < 0.1:
        v = quantity(rng, info, f, anchor)
        if f.whole:
            spec.givens.append(S.Given(given_name, "is", exact=units.number_text(v.value), sig=signature(rng)))
        else:
            w = v
            lo, hi = rng.choice([(w, w)] * 7 + [(w.of_si(w.si() * Fraction(4, 5)), w), (w, w.of_si(w.si() * Fraction(5, 4))), (w.of_si(w.si() * Fraction(9, 10)), w.of_si(w.si() * Fraction(11, 10)))])
            if f.least is not None and lo.si() < f.least:
                lo = w
            spec.givens.append(S.Given(given_name, "in", lo, hi, sig=signature(rng)))
        part.lines.append([f.name, f"given {given_name}"])
    elif f.optional and rng.random() < 0.3:
        part.lines.append([f.name, "unstated"])
    else:
        part.lines.append([f.name, quantity(rng, info, f, anchor)])


def build_part(rng: random.Random, info: Info, spec: Spec, tname: str, used: set[str], depth: int = 0) -> S.Part:
    t = info.types[tname]
    p = S.Part(tname, pname(rng, used, tname))
    spec.parts.append(p)
    lines: list[list] = []
    p.lines = lines
    for f in t.fields:
        if f.kind == "quantity":
            _quantity_line(rng, info, spec, p, f)
        elif f.kind == "key":
            if f.optional and rng.random() < 0.25:
                lines.append([f.name, "unstated"])
            elif f.signed or rng.random() < 0.06:
                name = rng.choice(f.one_of)
                spec.givens.append(S.Given(f"{p.name}.{f.name}", "is", exact=word(name, rng), sig=signature(rng)))
                lines.append([f.name, f"given {p.name}.{f.name}"])
            else:
                lines.append([f.name, word(rng.choice(f.one_of), rng)])
        else:
            names = []
            for _ in f.names or ["a"]:
                names.append(build_part(rng, info, spec, f.type, used, depth + 1).name if depth < 3 and f.type in info.types else "missing")
            lines.append([f.name, " ".join(names)])
    # build_part appended the joined parts after p; the design lists a part before the parts that follow it, in any order
    return p


def cards(rng: random.Random, info: Info, spec: Spec) -> None:
    """Loads and waivers of a spec's parts."""
    rng_cases = rng.choice([0, 1, 1, 1, 2, 3])
    names = rng.sample(CASES, k=min(rng_cases, len(CASES)))
    for case in names:
        ld = S.Load(case, [], signature(rng) if rng.random() < 0.9 else None)
        for p in spec.parts:
            t = info.types.get(p.type)
            if not t:
                continue
            for lf in t.loads:
                if rng.random() < 0.8:
                    anchors = ANCHORS.get((p.type, "load:" + lf.name))
                    hi = quantity(rng, info, F(lf.name, "quantity", lf.dim, least=None, may_be="zero"), rng.choice(anchors) if anchors and rng.random() < 0.7 else None)
                    lo = hi.of_si(Fraction(0)) if rng.random() < 0.6 else hi.of_si(hi.si() * Fraction(rng.choice([0, 1, 1, 9, 5]), rng.choice([1, 1, 10, 10, 10])))
                    if lo.si() > hi.si():
                        lo = hi
                    ld.entries.append(S.Entry(p.name, lf.name, lo, hi, signature(rng) if ld.sig is None else None))
        if ld.entries or rng.random() < 0.2:
            spec.loads.append(ld)
    style = rng.choice(["unruled", "unruled", "unruled", "random", "none", "all"])
    for p in spec.parts:
        t = info.types.get(p.type)
        if not t or not t.mechanisms or style == "none":
            continue
        if style == "all":
            chosen = list(t.mechanisms)
        elif style == "unruled":
            chosen = list(info.unruled.get(p.type, []))
            if rng.random() < 0.3:
                chosen += rng.sample(t.mechanisms, k=rng.randint(1, min(2, len(t.mechanisms))))
        else:
            chosen = rng.sample(t.mechanisms, k=rng.randint(1, len(t.mechanisms)))
        for m in dict.fromkeys(chosen):
            spec.waivers.append(S.Waiver(m, p.name, f'"{rng.choice(OWNERS)}"', rng.choice(REASONS)))
    spec.owner = rng.choice(OWNERS)
    spec.card_name = rng.choice(["attack", "lap-splice", "a", "card_1", "x" * 50])


def fresh(rng: random.Random, info: Info) -> Spec:
    spec = Spec()
    used: set[str] = set()
    root = rng.choice(info.roots())
    for _ in range(rng.choice([1, 1, 1, 2])):
        build_part(rng, info, spec, root, used)
    # a part comes before the parts that join it only when it is the first one built: write the joiner last, as the corpus does
    spec.parts.sort(key=lambda p: 0 if p.type not in info.roots() else 1)
    cards(rng, info, spec)
    repair(rng, info, spec)
    return spec


def repair(rng: random.Random, info: Info, spec: Spec, tries: int = 12) -> bool:
    """Scale the numbers of a part that breaks a need, the left side's down and the right side's up, until none does. False when it did not come right."""
    for _ in range(tries):
        bad = breaks(spec, info)
        if not bad:
            return True
        p, need = rng.choice(bad)
        key = "lt" if "lt" in need else "le"
        t = info.types[p.type]
        joined: dict[str, S.Part] = {}
        for f in t.fields:
            if f.kind == "joins":
                v = p.get(f.name)
                joined = {a: spec.part(n) for a, n in zip(f.names, (v.split() if isinstance(v, str) else [])) if spec.part(n)}
        left, right = (_interval(s, p, spec, info, joined) for s in need[key])
        sides = [_names(s) for s in need[key]]
        names = [(n, 0) for n in sides[0]] + [(n, 1) for n in sides[1]]
        if not names or left is None or right is None:
            return False
        name, side = rng.choice(names)
        target, _, fname = name.rpartition(".")
        owner = joined.get(target) if target else p
        f = next((f for f in info.types[owner.type].fields if f.name == fname), None) if owner else None
        if f is None or f.kind != "quantity" or f.whole:
            continue
        if right[0] > 0 and left[1] > 0:
            ratio = Fraction(rng.randint(30, 99), 100) * right[0] / left[1] if side == 0 else Fraction(rng.randint(101, 300), 100) * left[1] / right[0]
        else:
            ratio = rng.choice([Fraction(1, 2), Fraction(2)])
        v = owner.get(fname)
        if isinstance(v, Q):
            owner.put(fname, v.of_si(v.si() * ratio))
        elif isinstance(v, str) and v.startswith("given "):
            g = next((g for g in spec.givens if g.name == v[6:].strip()), None)
            if g and g.form == "in":
                g.lo, g.hi = g.lo.of_si(g.lo.si() * ratio), g.hi.of_si(g.hi.si() * ratio)
    return not breaks(spec, info)


def _names(node) -> list[str]:
    if isinstance(node, str):
        return [] if re.fullmatch(r"[+-]?\d+(?:\.\d+|/\d+)?", node) else [node]
    if isinstance(node, list) and node and node[0] != "q":
        return [n for a in node[1:] for n in _names(a)]
    return []


# --- changing a pair of the corpus

def corpus_specs() -> list[tuple[str, Spec]]:
    found = []
    for folder in ("corpus/cases/deck", "examples/deck"):
        for path in sorted((ROOT / folder).glob("*.petra")):
            card = path.with_suffix(".card")
            if card.is_file():
                s = S.read(card.read_text(encoding="utf-8"), path.read_text(encoding="utf-8"))
                if s:
                    found.append((f"{folder}/{path.name}", s))
    return found


def learn_anchors(specs: list[tuple[str, Spec]]) -> None:
    """Remember the numbers of the corpus by type and field."""
    for _, s in specs:
        types = {p.name: p.type for p in s.parts}
        for ld in s.loads:
            for e in ld.entries:
                if e.hi.si() > 0 and e.part in types:
                    ANCHORS.setdefault((types[e.part], "load:" + e.load), []).append(e.hi.si())
        for p in s.parts:
            for f, v in p.lines:
                x = None
                if isinstance(v, Q):
                    x = v.si()
                elif isinstance(v, str) and v.startswith("given "):
                    g = next((g for g in s.givens if g.name == v[6:].strip()), None)
                    if g and g.form == "in":
                        x = (g.lo.si() + g.hi.si()) / 2
                if x is not None and x > 0:
                    ANCHORS.setdefault((p.type, f), []).append(x)


def collapse(spec: Spec) -> Spec:
    """The spec with each bound of the card a point, so that the Python reader answers it in a few milliseconds and not a few seconds."""
    s = spec.copy()
    for g in s.givens:
        if g.form == "in" and g.lo is not None:
            g.lo = g.hi = g.lo.of_si((g.lo.si() + g.hi.si()) / 2)
            g.mean = None
    return s


def _numbers(spec: Spec) -> list[tuple]:
    return list(S.quantities(spec))


def m_nudge(rng, info, spec):
    items = [i for i in _numbers(spec) if i[2].unit or True]
    if not items:
        return "nothing to move"
    holder, key, q = rng.choice(items)
    new = nearby(rng, q.si())
    if q.si() == 0:
        new = Fraction(rng.choice([0, 1, 1, 2]))
    q2 = q.of_si(new)
    _set(holder, key, q2)
    return f"a number moved to {q2.text()}"


def _set(holder, key, q):
    """Put a number where it stands. A range keeps its ends in order: moving one end past the other moves the other with it."""
    if isinstance(key, list):
        key[1] = q
        return
    setattr(holder, key, q)
    if key in ("lo", "hi") and getattr(holder, "lo", None) is not None and getattr(holder, "hi", None) is not None and holder.lo.si() > holder.hi.si():
        if key == "lo":
            holder.hi = holder.hi.of_si(q.si())
        else:
            holder.lo = holder.lo.of_si(q.si())


def m_unit(rng, info, spec):
    items = [i for i in _numbers(spec) if i[2].unit]
    if not items:
        return "no unit to change"
    holder, key, q = rng.choice(items)
    options = [u for u in units.spellings(units.factor(q.unit)[1]) if u != q.unit] or [q.unit]
    q2 = q.in_unit(rng.choice(options))
    _set(holder, key, q2)
    return f"a unit of {q.text()} written as {q2.text()}"


def m_key(rng, info, spec):
    p = rng.choice(spec.parts)
    t = info.types.get(p.type)
    keys = [f for f in (t.fields if t else []) if f.kind == "key"]
    if not keys:
        return "no key"
    f = rng.choice(keys)
    if isinstance(p.get(f.name), str) and p.get(f.name).startswith("given "):
        g = next((g for g in spec.givens if g.name == p.get(f.name)[6:].strip()), None)
        if g:
            g.exact = word(rng.choice(f.one_of), rng)
            return f"the card states {f.name} of {p.name} as {g.exact}"
    p.put(f.name, word(rng.choice(f.one_of), rng))
    return f"{p.name}.{f.name} is {p.get(f.name)}"


def m_waiver(rng, info, spec):
    p = rng.choice(spec.parts)
    t = info.types.get(p.type)
    mechs = t.mechanisms if t else []
    if spec.waivers and rng.random() < 0.4:
        spec.waivers.pop(rng.randrange(len(spec.waivers)))
        return "a waiver dropped"
    if not mechs:
        return "no mechanism"
    spec.waivers.append(S.Waiver(rng.choice(mechs), p.name, f'"{rng.choice(OWNERS)}"', rng.choice(REASONS)))
    return "a waiver added"


def m_load(rng, info, spec):
    if spec.loads and rng.random() < 0.5:
        ld = rng.choice(spec.loads)
        if ld.entries and rng.random() < 0.5:
            ld.entries.pop(rng.randrange(len(ld.entries)))
            return "a load entry dropped"
        ld.case = rng.choice(CASES) if rng.random() < 0.6 else ld.case + "x"
        return f"a case renamed {ld.case}"
    for p in rng.sample(spec.parts, k=len(spec.parts)):
        t = info.types.get(p.type)
        if t and t.loads:
            lf = rng.choice(t.loads)
            hi = quantity(rng, info, F(lf.name, "quantity", lf.dim, may_be="zero"))
            case = rng.choice(CASES)
            ld = next((l for l in spec.loads if l.case == case), None)
            if ld is None:
                ld = S.Load(case, [], signature(rng))
                spec.loads.append(ld)
            if not any(e.part == p.name and e.load == lf.name for e in ld.entries):
                ld.entries.append(S.Entry(p.name, lf.name, hi.of_si(Fraction(0)), hi))
            return f"a load of {hi.text()} on {p.name} in {case}"
    return "no load"


def m_range(rng, info, spec):
    gs = [g for g in spec.givens if g.form == "in"]
    if not gs:
        return "no given"
    g = rng.choice(gs)
    w = rng.choice(["point", "widen", "narrow", "up"])
    mid = (g.lo.si() + g.hi.si()) / 2
    if w == "point":
        g.lo = g.hi = g.lo.of_si(mid)
    elif w == "widen":
        g.lo, g.hi = g.lo.of_si(g.lo.si() * Fraction(9, 10)), g.hi.of_si(g.hi.si() * Fraction(11, 10))
    elif w == "narrow":
        g.lo, g.hi = g.lo.of_si(mid), g.hi
    else:
        g.hi = g.hi.of_si(g.hi.si() * 2)
    return f"the bound of {g.name}: {w}"


def m_given(rng, info, spec):
    """A number a part writes becomes a bound the card gives."""
    p = rng.choice(spec.parts)
    items = [l for l in p.lines if isinstance(l[1], Q) and not units.dim_of("dimensionless") is None and l[1].unit]
    if not items:
        return "no number"
    line = rng.choice(items)
    q = line[1]
    name = f"{p.name}.{line[0]}"
    if any(g.name == name for g in spec.givens):
        return "already given"
    lo, hi = rng.choice([(q, q), (q.of_si(q.si() * Fraction(9, 10)), q), (q, q.of_si(q.si() * Fraction(11, 10)))])
    spec.givens.append(S.Given(name, "in", lo, hi, sig=signature(rng)))
    line[1] = f"given {name}"
    return f"{name} is a bound of the card"


def m_unstated(rng, info, spec):
    for p in rng.sample(spec.parts, k=len(spec.parts)):
        t = info.types.get(p.type)
        opts = [f for f in (t.fields if t else []) if f.optional]
        if opts:
            f = rng.choice(opts)
            p.put(f.name, "unstated")
            return f"{p.name}.{f.name} is unstated"
    return "no optional field"


def m_copy_part(rng, info, spec):
    """Another of the same type, as the design repeats a lap."""
    p = rng.choice([p for p in spec.parts if p.type in info.roots()] or spec.parts)
    used = {q.name for q in spec.parts}
    new = S.Part(p.type, pname(rng, used, p.name), [list(l) for l in p.lines])
    t = info.types.get(p.type)
    for f in (t.fields if t else []):
        v = p.get(f.name)
        if f.kind == "joins" and isinstance(v, str):
            names = []
            for n in v.split():
                src = spec.part(n)
                if src is None:
                    names.append(n)
                    continue
                c = S.Part(src.type, pname(rng, used, src.name), [list(l) for l in src.lines])
                for l in c.lines:
                    if isinstance(l[1], str) and l[1].startswith("given "):
                        old = l[1][6:].strip()
                        g = next((g for g in spec.givens if g.name == old), None)
                        l[1] = f"given {c.name}.{l[0]}"
                        if g:
                            spec.givens.append(S.Given(f"{c.name}.{l[0]}", g.form, g.lo, g.hi, g.mean, g.exact, g.sig))
                spec.parts.append(c)
                names.append(c.name)
            new.put(f.name, " ".join(names))
    for l in new.lines:
        if isinstance(l[1], str) and l[1].startswith("given "):
            old = l[1][6:].strip()
            g = next((g for g in spec.givens if g.name == old), None)
            l[1] = f"given {new.name}.{l[0]}"
            if g and not any(x.name == l[1][6:] for x in spec.givens):
                spec.givens.append(S.Given(f"{new.name}.{l[0]}", g.form, g.lo, g.hi, g.mean, g.exact, g.sig))
    spec.parts.append(new)
    for ld in spec.loads:
        for e in [e for e in ld.entries if e.part == p.name]:
            if rng.random() < 0.5:
                ld.entries.append(S.Entry(new.name, e.load, e.lo, e.hi, e.sig))
    return f"a second {p.type}, {new.name}"


MUTATIONS: list[tuple[int, Callable]] = [(5, m_nudge), (2, m_unit), (2, m_key), (2, m_waiver), (3, m_load), (2, m_range), (1, m_given), (1, m_unstated), (1, m_copy_part)]


def mutate_corpus(rng: random.Random, info: Info, spec: Spec) -> Spec:
    s = spec.copy()
    for _ in range(rng.choice([1, 1, 2, 2, 3])):
        fn = rng.choices([m for _, m in MUTATIONS], [w for w, _ in MUTATIONS])[0]
        s.notes.append(fn(rng, info, s))
    repair(rng, info, s, tries=6)
    return s


# --- damage the language refuses, and the refusals the readers must agree on

def damage(rng: random.Random, info: Info, spec: Spec) -> str:
    s = rng.choice(["drop_line", "extra_line", "dup_line", "wrong_unit", "bad_given", "env", "bad_case", "waive_unknown", "neg", "zero", "giant", "tab_name", "dup_name", "unknown_type_field"])
    p = rng.choice(spec.parts)
    if s == "drop_line" and p.lines:
        p.lines.pop(rng.randrange(len(p.lines)))
    elif s == "extra_line":
        p.lines.append(["extra", "1 mm"])
    elif s == "dup_line" and p.lines:
        p.lines.append(list(rng.choice(p.lines)))
    elif s == "wrong_unit":
        items = [i for i in _numbers(spec) if i[2].unit]
        if items:
            h, k, q = rng.choice(items)
            _set(h, k, Q(q.value, rng.choice(["kN", "s", "mm2", "ksi", "degC", "A"]), q.style, q.glue))
    elif s == "bad_given" and spec.givens:
        spec.givens[0].name = spec.givens[0].name + "z"
    elif s == "env":
        spec.environment = "steel.A992"
    elif s == "bad_case" and spec.loads:
        spec.loads[0].case = "where"
    elif s == "waive_unknown":
        spec.waivers.append(S.Waiver("lap.nothing", p.name))
    elif s == "neg":
        items = [i for i in _numbers(spec) if i[2].unit]
        if items:
            h, k, q = rng.choice(items)
            _set(h, k, q.of_si(-abs(q.si())))
    elif s == "zero":
        items = [i for i in _numbers(spec) if i[2].unit]
        if items:
            h, k, q = rng.choice(items)
            _set(h, k, q.of_si(Fraction(0)))
    elif s == "giant":
        items = [i for i in _numbers(spec) if i[2].unit]
        if items:
            h, k, q = rng.choice(items)
            _set(h, k, q.of_si(q.si() * 10 ** rng.choice([6, 40, 400])))
    elif s == "tab_name":
        p.name = p.name + "\t"
    elif s == "dup_name" and len(spec.parts) > 1:
        spec.parts[1].name = spec.parts[0].name
    elif s == "unknown_type_field":
        p.type = p.type + "x"
    return s


# --- hunting the point where a reader changes its answer

def probe_factory(deck_text: str):
    """A function from a spec to what the Python reader says of it: the verdict and the state of every cell, or the first words of its refusal."""
    from unittest import mock
    from petra import grid
    from petra.lang import parse_design
    from petra.models.base import ComponentError
    from petra.registry import build_registry
    from petra.repair import INPUT_ERRORS
    deck = grid.read_deck(deck_text)
    registry = build_registry()

    def probe(spec: Spec):
        from .readers import Timeout, alarm
        card, design = spec.texts()
        with mock.patch.object(grid, "decks", lambda: (deck,)):
            try:
                with alarm(4):
                    parsed = parse_design(card, design, "probe.petra", registry)
                    if grid.owner(parsed) is None:
                        return ("none",)
                    report, _ = grid.check(parsed, deck)
            except INPUT_ERRORS as exc:
                return ("refused", re.sub(r"[\d./]+", "#", str(exc))[:50])
            except Timeout:
                return ("slow",)
            except Exception as exc:        # noqa: BLE001
                return ("crash", type(exc).__name__)
        return (report.verdict, tuple((c.subject, c.mechanism, c.entry, c.state) for c in report.cells))

    return probe


def _at(spec: Spec, i: int) -> tuple:
    return list(S.quantities(spec))[i]


def flips(rng: random.Random, spec: Spec, i: int, probe, steps: int = 64) -> list[tuple[Fraction, Fraction, Fraction]]:
    """Where moving one number of the spec changes the Python reader's answer. Each is (a, b, s): the answer is one at `a`, another at `b`, and `s` is the simplest fraction between them."""
    q = _at(spec, i)[2]
    x0 = q.si()
    pts = sorted({x for x in [x0 * Fraction(2) ** k for k in range(-5, 6)] + [x0 * Fraction(rng.randint(1, 40), rng.randint(1, 40)) for _ in range(6)] if x > 0})
    out: list[tuple[Fraction, Fraction, Fraction]] = []

    def at(x: Fraction):
        spec2 = spec.copy()
        h, k, q2 = _at(spec2, i)
        _set(h, k, Q(x / units.factor(q.unit)[0], q.unit, "frac", q.glue))
        return probe(spec2)

    limit = time.monotonic() + 25
    seen = [(x, at(x)) for x in pts]
    for (xa, ra), (xb, rb) in zip(seen, seen[1:]):
        if ra == rb or len(out) >= 2 or time.monotonic() > limit:
            continue
        a, b = xa, xb
        for _ in range(steps):
            if time.monotonic() > limit:
                break
            mid = (a + b) / 2
            if at(mid) == ra:
                a = mid
            else:
                b = mid
            if (b - a) < abs(b) * Fraction(1, 2 ** 56):
                break
        out.append((a, b, simplest_between(a, b)))
    return out


def hunt(rng: random.Random, info: Info, base: Spec, probe) -> list[tuple[Spec, str]]:
    """Variants of the spec with one number at, under and over a point where the Python reader's answer changes."""
    items = [i for i, (_, _, q) in enumerate(S.quantities(base)) if q.value != 0 and (q.unit or q.value > 1)]
    rng.shuffle(items)
    out: list[tuple[Spec, str]] = []
    base = collapse(base)
    for i in items[:4]:
        q = _at(base, i)[2]
        for a, b, s in flips(rng, base, i, probe):
            # a value near the point is written with the fewest digits that lie on the same side of it
            under = simplest_between(a * (1 - Fraction(1, 2 ** 30)), a)
            over = simplest_between(b, b * (1 + Fraction(1, 2 ** 30)))
            for label, x in (("under", under), ("at", s), ("over", over), ("hair under", simplest_between(s * (1 - Fraction(1, 2 ** 40)), s * (1 - Fraction(1, 2 ** 44)))),
                             ("hair over", simplest_between(s * (1 + Fraction(1, 2 ** 44)), s * (1 + Fraction(1, 2 ** 40))))):
                spec2 = base.copy()
                h, k, _ = _at(spec2, i)
                _set(h, k, Q(x / units.factor(q.unit)[0], q.unit, "frac", q.glue))
                spec2.notes.append(f"a number {label} the point {units.number_text(s)} where the answer changes")
                out.append((spec2, label))
        if out:
            break
    return out


def climb(rng: random.Random, spec: Spec, probe, probes: int = 18) -> Spec:
    """Move numbers of the spec, one at a time by a simple factor, while the Python reader refutes fewer cells.

    Independent draws break rules that tie two numbers (a pitch against a diameter), so a fresh design fails nearly every time. This leaves a design that passes, or fails one rule by a little, which is where the readers' comparisons are decided. It probes a copy with each bound of the card a point, which the reader answers in milliseconds, and applies what it keeps to the design as it was."""
    work = collapse(spec)
    n = len(list(S.quantities(work)))
    if not n:
        return spec

    def score(r) -> float:
        if r[0] in ("refused", "crash", "none"):
            return 10 ** 6
        refuted = sum(1 for c in r[1] if c[3] == "refuted")
        return refuted + 0.01 * sum(1 for c in r[1] if c[3] == "open")

    best = score(probe(work))
    kept: list[tuple[int, Fraction]] = []
    limit = time.monotonic() + 6
    for _ in range(probes):
        if best < 0.5 or time.monotonic() > limit:
            break
        i = rng.randrange(n)
        h, k, q = _at(work, i)
        if q.value == 0 or (not q.unit and q.value == q.value.__floor__() and q.value < 50 and rng.random() < 0.7):
            continue
        f = rng.choice([Fraction(1, 2), Fraction(2, 3), Fraction(3, 4), Fraction(4, 3), Fraction(3, 2), Fraction(2), Fraction(8, 3), Fraction(3), Fraction(1, 3), Fraction(10), Fraction(1, 10), Fraction(11, 10), Fraction(9, 10)])
        old = q
        _set(h, k, q.of_si(q.si() * f))
        s = score(probe(work))
        if s <= best:
            best = s
            kept.append((i, f))
        else:
            _set(h, k, old)
    out = spec.copy()
    for i, f in kept:
        h, k, q = _at(out, i)
        _set(h, k, q.of_si(q.si() * f))
    if kept:
        out.notes.append(f"{len(kept)} numbers moved toward a design that holds")
    return out
