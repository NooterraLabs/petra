"""A design and its card as data, read from the language of docs/reference.md and written back.

The generator changes a `Spec` and never a text, so what it writes parses: a number is a
`Q` with its own spelling of the unit, a line of a part is a field and a value, and a card is
givens, loads and waivers. `read` takes the pair of texts of the corpus; `Spec.texts` writes
the pair.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from fractions import Fraction

from . import units


@dataclass
class Q:
    """A number in a unit, written as the language writes it: `0.375 inch`, `3/4in`, `45 kip`, or a plain `3`."""

    value: Fraction
    unit: str = ""
    style: str = "auto"
    glue: str = " "

    def si(self) -> Fraction:
        return self.value * units.factor(self.unit)[0]

    def text(self) -> str:
        n = units.number_text(self.value, self.style)
        return n + (self.glue + self.unit if self.unit else "")

    def in_unit(self, unit: str) -> "Q":
        """The same quantity written in another unit of its dimension."""
        return Q(self.si() / units.factor(unit)[0], unit, self.style, self.glue)

    def of_si(self, x: Fraction) -> "Q":
        """A quantity of the same unit and spelling with this SI value."""
        return Q(x / units.factor(self.unit)[0], self.unit, self.style, self.glue)


Value = "Q | str"

_QTY = re.compile(r"([+-]?\d+(?:\.\d+|/\d+)?)\s*([A-Za-z%][A-Za-z0-9_/%^]*)?")


def q_of(text: str) -> Q | None:
    """A `Q` from text such as `0.75 inch`, or None when the text is not one number with a unit."""
    m = _QTY.fullmatch(text.strip())
    if not m:
        return None
    unit = m.group(2) or ""
    try:
        units.factor(unit)
        n = Fraction(m.group(1))
    except (KeyError, ZeroDivisionError):
        return None
    glue = " " if re.search(r"\s", text.strip()[len(m.group(1)):len(m.group(1)) + 1]) else ""
    style = "frac" if "/" in m.group(1) else "dec" if "." in m.group(1) else "auto"
    return Q(n, unit, style, glue)


@dataclass
class Part:
    type: str
    name: str
    lines: list[list] = field(default_factory=list)       # [field, Value]

    def get(self, name: str):
        return next((v for f, v in self.lines if f == name), None)

    def put(self, name: str, value) -> None:
        for line in self.lines:
            if line[0] == name:
                line[1] = value
                return
        self.lines.append([name, value])


@dataclass
class Given:
    name: str
    form: str = "in"                      # "in" a range, "is" an exact key or count
    lo: Q | None = None
    hi: Q | None = None
    mean: Q | None = None
    exact: str = ""                       # what `is` states: a word, a quoted text or a number
    sig: str = 'signed "t@example.org" source "attack"'


@dataclass
class Entry:
    part: str
    load: str
    lo: Q
    hi: Q
    sig: str | None = None


@dataclass
class Load:
    case: str
    entries: list[Entry] = field(default_factory=list)
    sig: str | None = 'signed "t@example.org" source "attack"'


@dataclass
class Waiver:
    mechanism: str
    subject: str
    by: str = '"t@example.org"'
    reason: str = '"attack"'


@dataclass
class Spec:
    card_name: str = "attack"
    owner: str = "t@example.org"
    environment: str | None = None
    parts: list[Part] = field(default_factory=list)
    givens: list[Given] = field(default_factory=list)
    loads: list[Load] = field(default_factory=list)
    waivers: list[Waiver] = field(default_factory=list)
    card_more: list[str] = field(default_factory=list)       # whole lines the card gains after its waivers
    design_more: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)           # what was done to make it, in words

    def copy(self) -> "Spec":
        return copy.deepcopy(self)

    def part(self, name: str) -> Part | None:
        return next((p for p in self.parts if p.name == name), None)

    # --- writing

    def card_text(self) -> str:
        out = ["petra 0", "", f'card "{self.card_name}" {{', f'  owner "{self.owner}"']
        if self.environment:
            out.append(f"  environment {self.environment}")
        out += ["}", ""]
        for g in self.givens:
            if g.form == "is":
                out.append(f"given {g.name} is {g.exact} {g.sig}".rstrip())
            else:
                mean = f" mean {g.mean.text()}" if g.mean else ""
                out.append(f"given {g.name} in [{g.lo.text()}, {g.hi.text()}]{mean} {g.sig}".rstrip())
        for ld in self.loads:
            out += ["", f"load {ld.case} {{"]
            for e in ld.entries:
                out.append(f"  on {e.part} {e.load} in [{e.lo.text()}, {e.hi.text()}]" + (f" {e.sig}" if e.sig else ""))
            if ld.sig:
                out.append(f"  {ld.sig}")
            out.append("}")
        if self.waivers:
            out.append("")
        for w in self.waivers:
            out.append(f"waive {w.mechanism} on {w.subject} by {w.by} reason {w.reason}")
        out += self.card_more
        return "\n".join(out) + "\n"

    def design_text(self) -> str:
        out = ["petra 0", "", *self.design_more]
        for p in self.parts:
            out.append(f"{p.type} {p.name} {{")
            for f, v in p.lines:
                out.append(f"  {f} {v.text() if isinstance(v, Q) else v}")
            out += ["}", ""]
        return "\n".join(out) + "\n"

    def texts(self) -> tuple[str, str]:
        return self.card_text(), self.design_text()


# --- reading

def _strip(line: str) -> str:
    """A line without its comment: a `#` outside quotes starts one."""
    out, quoted, i = [], False, 0
    while i < len(line):
        c = line[i]
        if quoted and c == "\\" and i + 1 < len(line):
            out.append(line[i:i + 2])
            i += 2
            continue
        if c == '"':
            quoted = not quoted
        if c == "#" and not quoted:
            break
        out.append(c)
        i += 1
    return "".join(out).strip()


_SIG = re.compile(r'((?:signed|measured) "(?:[^"\\]|\\.)*" source "(?:[^"\\]|\\.)*")\s*$')
_RANGE = re.compile(r"\[\s*([^,\]]+?)\s*,\s*([^\]]+?)\s*\]")


def read(card: str, design: str) -> Spec | None:
    """The spec of a pair of texts, or None when the pair holds something this reading does not keep: a claim, a family, a test."""
    s = Spec()
    lines = [_strip(l) for l in card.splitlines()]
    i = 0
    while i < len(lines):
        l = lines[i]
        i += 1
        if not l or l.startswith("petra "):
            continue
        m = re.fullmatch(r'card "((?:[^"\\]|\\.)*)" \{', l)
        if m:
            s.card_name = m.group(1)
            while i < len(lines) and lines[i] != "}":
                o = re.fullmatch(r'owner "((?:[^"\\]|\\.)*)"', lines[i])
                e = re.fullmatch(r"environment (\S+)", lines[i])
                if o:
                    s.owner = o.group(1)
                elif e:
                    s.environment = e.group(1)
                elif lines[i]:
                    return None
                i += 1
            i += 1
            continue
        m = re.fullmatch(r'given (\S+) is (\S+|"(?:[^"\\]|\\.)*")\s*(.*)', l)
        if m:
            s.givens.append(Given(m.group(1), "is", exact=m.group(2), sig=m.group(3)))
            continue
        m = re.fullmatch(r"given (\S+) in (\[.+?\])(?: mean (\S+(?: [A-Za-z%][^ ]*)?))? ?(.*)", l)
        if m:
            r = _RANGE.fullmatch(m.group(2))
            lo, hi = (q_of(r.group(1)), q_of(r.group(2))) if r else (None, None)
            mean = q_of(m.group(3)) if m.group(3) else None
            if lo is None or hi is None or (m.group(3) and mean is None):
                return None
            s.givens.append(Given(m.group(1), "in", lo, hi, mean, sig=m.group(4)))
            continue
        m = re.fullmatch(r"load (\w+) \{", l)
        if m:
            ld = Load(m.group(1), sig=None)
            while i < len(lines) and lines[i] != "}":
                e = re.fullmatch(r"on (\S+) (\w+) in (\[.+?\])\s*(.*)", lines[i])
                if e:
                    r = _RANGE.fullmatch(e.group(3))
                    lo, hi = (q_of(r.group(1)), q_of(r.group(2))) if r else (None, None)
                    if lo is None or hi is None:
                        return None
                    ld.entries.append(Entry(e.group(1), e.group(2), lo, hi, e.group(4) or None))
                elif _SIG.fullmatch(lines[i]):
                    ld.sig = lines[i]
                elif lines[i]:
                    return None
                i += 1
            i += 1
            s.loads.append(ld)
            continue
        m = re.fullmatch(r"waive (\S+) on (\S+) by (\"(?:[^\"\\]|\\.)*\") reason (\"(?:[^\"\\]|\\.)*\")", l)
        if m:
            s.waivers.append(Waiver(*m.groups()))
            continue
        return None
    lines = [_strip(l) for l in design.splitlines()]
    i = 0
    while i < len(lines):
        l = lines[i]
        i += 1
        if not l or l.startswith("petra "):
            continue
        m = re.fullmatch(r"(\w+) (\w+) \{", l)
        if not m:
            return None
        p = Part(m.group(1), m.group(2))
        while i < len(lines) and lines[i] != "}":
            if lines[i]:
                f, _, v = lines[i].partition(" ")
                p.lines.append([f, q_of(v) or v.strip()])
            i += 1
        i += 1
        s.parts.append(p)
    return s


def quantities(s: Spec):
    """Every number a spec writes, as (holder, key, Q): the handle by which a number is changed."""
    for p in s.parts:
        for line in p.lines:
            if isinstance(line[1], Q):
                yield p, line, line[1]
    for g in s.givens:
        for k in ("lo", "hi", "mean"):
            if getattr(g, k) is not None:
                yield g, k, getattr(g, k)
    for ld in s.loads:
        for e in ld.entries:
            yield e, "lo", e.lo
            yield e, "hi", e.hi
