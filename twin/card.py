"""Parse a card and the design that answers it into components and load entries.

The twin's own reader, written from the language reference and the example pairs. The card
(NAME.card) holds what is asked: the load cases, each `given` bound, and the params a load
reads. The design (NAME.petra) holds the components and its own params, and a component's
line reads a bound the card gives as `given NAME`. The reader keeps what the steel checks
need: each component's attribute lines and each load entry's range. Quantities are exact
fractions in inches, kips and ksi.
"""

import re
from dataclasses import dataclass
from fractions import Fraction

_LBF_N = Fraction("4.4482216152605")
_IN_MM = Fraction("25.4")
_KIP_N = 1000 * _LBF_N
_MM = 1 / _IN_MM
_N = 1 / _KIP_N
_PA = _N / (1000 * _MM) ** 2

UNITS = {
    "inch": ("length", Fraction(1)),
    "ft": ("length", Fraction(12)),
    "mm": ("length", _MM),
    "cm": ("length", 10 * _MM),
    "m": ("length", 1000 * _MM),
    "km": ("length", 1000000 * _MM),
    "inch2": ("area", Fraction(1)),
    "mm2": ("area", _MM**2),
    "m2": ("area", (1000 * _MM) ** 2),
    "kip": ("force", Fraction(1)),
    "kips": ("force", Fraction(1)),
    "lbf": ("force", Fraction(1, 1000)),
    "N": ("force", _N),
    "kN": ("force", 1000 * _N),
    "MN": ("force", 1000000 * _N),
    "ksi": ("stress", Fraction(1)),
    "psi": ("stress", Fraction(1, 1000)),
    "Pa": ("stress", _PA),
    "kPa": ("stress", 1000 * _PA),
    "MPa": ("stress", 1000000 * _PA),
    "GPa": ("stress", 1000000000 * _PA),
    "kip_in": ("moment", Fraction(1)),
    "kip_ft": ("moment", Fraction(12)),
    "Nm": ("moment", _N * 1000 * _MM),
    "J": ("moment", _N * 1000 * _MM),
    "%": ("ratio", Fraction(1, 100)),
}


class CardError(ValueError):
    """A card or a design the reader cannot read. The message names the file and the line."""


@dataclass(frozen=True)
class Quantity:
    value: Fraction
    dim: str


@dataclass(frozen=True)
class Component:
    kind: str
    name: str
    lines: dict
    line_numbers: dict


@dataclass(frozen=True)
class LoadEntry:
    case: str
    target: str
    field: str
    lo: Quantity
    hi: Quantity


@dataclass(frozen=True)
class Pair:
    """A card and the design that answers it: the design's components, the card's loads."""

    components: tuple
    loads: tuple
    params: dict  # name -> (lo, hi) Quantities of each `param NAME in [lo, hi]`, in either file


_TOKEN = re.compile(
    r"""\s*(?:
    (?P<string>"(?:\\.|[^"\\])*")
  | (?P<number>[+-]?\d+(?:\.\d+)?(?:/\d+)?)(?P<unit>%|[A-Za-z][A-Za-z0-9_]*)?
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)
  | (?P<punct>->|--|<=|>=|[{}\[\](),:<>%])
    )""",
    re.VERBOSE,
)

_SIGNATURE_WORDS = {"signed", "measured"}
_BOUND_WORDS = {"in", "mean", "source"} | _SIGNATURE_WORDS
_IGNORED_BLOCKS = {"card", "tests"}
_IGNORED_LINES = {"ambient", "claim", "waive"}
_CARD_WORDS = {"load", "given"} | _IGNORED_BLOCKS | _IGNORED_LINES


def _strip_comment(line):
    out, in_string, escaped = [], False, False
    for ch in line:
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out)


def _tokens(text, at):
    pos, out = 0, []
    text = text.rstrip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise CardError(f"{at}: cannot read {text[pos:]!r}")
        pos = m.end()
        if m.group("string") is not None:
            out.append(("string", m.group("string")[1:-1]))
        elif m.group("number") is not None:
            out.append(("number", Fraction(m.group("number"))))
            if m.group("unit"):
                out.append(("ident", m.group("unit")))
        elif m.group("ident") is not None:
            out.append(("ident", m.group("ident")))
        else:
            out.append(("punct", m.group("punct")))
    return _attach_units(out)


def _attach_units(tokens):
    out, i = [], 0
    while i < len(tokens):
        kind, value = tokens[i]
        if kind == "number":
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None
            if nxt and nxt[0] in ("ident", "punct") and nxt[1] in UNITS:
                dim, scale = UNITS[nxt[1]]
                out.append(("qty", Quantity(value * scale, dim)))
                i += 2
                continue
            out.append(("qty", Quantity(value, "count")))
        else:
            out.append((kind, value))
        i += 1
    return out


def _bound(tokens, at):
    """Read `in [lo, hi]` from the front of tokens and return (lo, hi)."""
    if len(tokens) < 6 or tokens[0] != ("ident", "in") or tokens[1] != ("punct", "["):
        raise CardError(f"{at}: expected a bound `in [lo, hi]`")
    lo, comma, hi, close = tokens[2], tokens[3], tokens[4], tokens[5]
    if lo[0] != "qty" or hi[0] != "qty" or comma != ("punct", ",") or close != ("punct", "]"):
        raise CardError(f"{at}: malformed range")
    return lo[1], hi[1]


def _args(tokens, given, read, at):
    """A component line's arguments, with each `given NAME` as one ("bound", (lo, hi)) token:
    the bound the card gives under that name. A design states no bound of its own."""
    out, i = [], 0
    while i < len(tokens):
        if tokens[i] == ("ident", "given"):
            name = tokens[i + 1][1] if i + 1 < len(tokens) and tokens[i + 1][0] == "ident" else None
            if name is None:
                raise CardError(f"{at}: `given` is followed by the name of a bound the card gives")
            if name not in given:
                raise CardError(f"{at}: the card gives no bound named {name}")
            read.add(name)
            out.append(("bound", given[name]))
            i += 2
            continue
        if tokens[i][0] == "ident" and tokens[i][1] in _BOUND_WORDS:
            raise CardError(f"{at}: a design states no bound; the card gives it and the line reads `given NAME`")
        out.append(tokens[i])
        i += 1
    return tuple(out)


def _read(text, file, given=None):
    """One file's components, load entries, params and given bounds. `file` is "card" or
    "design" and settles which of them the file may hold. `given` is what the card gives a
    design, which reads every one of them."""
    components, loads, params, givens, read = [], [], {}, {}, set()
    block = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        at = f"{file} line {lineno}"
        toks = _tokens(_strip_comment(raw), at)
        if not toks:
            continue
        if block is None:
            if toks[0] == ("ident", "petra"):
                continue
            head = toks[0][1]
            if file == "design" and head in _CARD_WORDS:
                raise CardError(f"{at}: `{head}` belongs in the card")
            if toks[-1] == ("punct", "{"):
                if head in _IGNORED_BLOCKS:
                    block = ("ignored", None)
                elif head == "load":
                    block = ("load", toks[1][1])
                elif file == "card":
                    raise CardError(f"{at}: a card holds no component block; `{head}` belongs in the design")
                else:
                    if len(toks) != 3 or toks[1][0] != "ident":
                        raise CardError(f"{at}: expected `KIND NAME {{`")
                    block = ("component", Component(head, toks[1][1], {}, {}))
                continue
            if head in _IGNORED_LINES:
                continue
            if head in ("param", "given") and len(toks) > 2 and toks[1][0] == "ident":
                (params if head == "param" else givens)[toks[1][1]] = _bound(toks[2:], at)
                continue
            raise CardError(f"{at}: unexpected {head!r} outside a block")
        if toks == [("punct", "}")]:
            if block[0] == "component":
                components.append(block[1])
            block = None
            continue
        kind, owner = block
        if kind == "ignored":
            continue
        if kind == "load":
            if toks[0][1] in _SIGNATURE_WORDS:
                continue
            if toks[0] != ("ident", "on") or len(toks) < 4:
                raise CardError(f"{at}: a load entry starts with `on TARGET FIELD`")
            lo, hi = _bound(toks[3:], at)
            loads.append(LoadEntry(owner, toks[1][1], toks[2][1], lo, hi))
            continue
        key = toks[0][1]
        if key in owner.lines:
            raise CardError(f"{at}: `{key}` appears twice in {owner.name}")
        owner.lines[key] = _args(toks[1:], given or {}, read, at)
        owner.line_numbers[key] = lineno
    if block is not None:
        raise CardError(f"{file}: unclosed block at end of file")
    unread = sorted(set(given or ()) - read)
    if unread:
        raise CardError(f"card: no component reads the given {', '.join(unread)}")
    return components, loads, params, givens


def parse(card, design):
    """Read the text of a card and of the design that answers it."""
    _, loads, params, givens = _read(card, "card")
    components, _, own, _ = _read(design, "design", givens)
    twice = sorted(params.keys() & own.keys())
    if twice:
        raise CardError(f"design: param {twice[0]} is declared in the card too")
    return Pair(tuple(components), tuple(loads), {**params, **own})
